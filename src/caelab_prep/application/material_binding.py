"""Prepare and commit calibrated elastic values in the live document owner."""
from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from decimal import Decimal
from difflib import unified_diff
from hashlib import sha256
import math
import re
import sys
import time
from uuid import uuid4

from ..cae_core import PrepError
from ..radioss.modeling import native_identity
from .contracts import ObjectRef

_PROFILE_ID = "radioss_law1_elastic_v1"
_PROFILE_REVISION = 1
DEFAULT_PLAN_TTL_SECONDS = 60.0

_MASS_SI = {"kg": Decimal("1"), "g": Decimal("0.001"), "Mg": Decimal("1000"), "t": Decimal("1000")}
_LENGTH_SI = {"m": Decimal("1"), "cm": Decimal("0.01"), "mm": Decimal("0.001")}
_TIME_SI = {"s": Decimal("1"), "ms": Decimal("0.001"), "mus": Decimal("0.000001")}
_STRESS_SI = {"Pa": Decimal("1"), "kPa": Decimal("1000"), "MPa": Decimal("1e6"), "GPa": Decimal("1e9")}
_DIMENSIONLESS = {"", "1", "dimensionless", "ratio", "-"}
_ALIASES = {
    "E": "young_modulus", "young_modulus": "young_modulus",
    "nu": "poisson_ratio", "poisson_ratio": "poisson_ratio",
    "rho": "density", "density": "density",
}


@dataclass(frozen=True)
class _PreparedMaterialPlan:
    handle: dict
    resource_id: str
    card_id: str
    state: dict
    baseline_token: str
    baseline_hash: str
    candidate_hash: str
    evaluation_digest: str
    deadline: float


def _unit_scale(field, unit):
    if field == "poisson_ratio" and unit in _DIMENSIONLESS:
        return Decimal(1)
    if field == "young_modulus":
        if unit in _STRESS_SI:
            return _STRESS_SI[unit]
        match = re.fullmatch(r"([^/]+)/\(([^*]+)\*([^*^]+)\^?2\)", unit)
        if match:
            mass, length, seconds = match.groups()
            if mass in _MASS_SI and length in _LENGTH_SI and seconds in _TIME_SI:
                return _MASS_SI[mass] / (_LENGTH_SI[length] * _TIME_SI[seconds] ** 2)
    if field == "density":
        match = re.fullmatch(r"([^/]+)/([^/^]+)\^?3", unit)
        if match:
            mass, length = match.groups()
            if mass in _MASS_SI and length in _LENGTH_SI:
                return _MASS_SI[mass] / _LENGTH_SI[length] ** 3
    raise PrepError("invalid_unit", "Supply a unit matching the calibrated field dimension.", {"field": field, "unit": unit})


def _deck_scales(units):
    try:
        mass, length, seconds = _MASS_SI[units["mass"]], _LENGTH_SI[units["length"]], _TIME_SI[units["time"]]
    except (TypeError, KeyError):
        raise PrepError("invalid_units", "Declare both supported /BEGIN mass, length and time rows.") from None
    return {"density": mass / length ** 3, "young_modulus": mass / (length * seconds ** 2),
            "poisson_ratio": Decimal(1)}


def _material_fields(parameters, deck_scales):
    if not isinstance(parameters, dict) or not parameters:
        raise PrepError("invalid_request", "Provide calibrated elastic parameters with values and units.")
    fields = {}
    for key, entry in parameters.items():
        if key in ("prony_terms", "terms"):
            raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "Prony terms have no registered live material binding.")
        field = _ALIASES.get(key)
        if field is None or field in fields:
            raise PrepError("invalid_request", "Invalid or duplicate elastic parameter.", {"parameter": key})
        if not isinstance(entry, dict) or set(entry) != {"value", "unit"}:
            raise PrepError("invalid_request", "Each elastic parameter requires exactly a value and unit.", {"parameter": key})
        unit = entry["unit"]
        if not isinstance(unit, str):
            raise PrepError("invalid_unit", "A unit string is required.", {"field": field})
        unit = unit.replace(" ", "").replace("³", "^3").replace("²", "^2").replace("·", "*")
        factor = _unit_scale(field, unit) / deck_scales[field]
        try:
            value = entry["value"]
            if type(value) not in (int, float):
                raise ValueError()
            number = float(value)
            if not math.isfinite(number) or 0 < abs(number) < sys.float_info.min:
                raise ValueError()
            converted = float(Decimal(str(number)) * factor)
            if not math.isfinite(converted) or (number and abs(converted) < sys.float_info.min):
                raise ValueError()
        except (ValueError, OverflowError):
            raise PrepError("invalid_value", "Value and converted value must be finite and in the native numeric range.",
                            {"field": field}) from None
        fields[field] = converted
    return fields


def _card_hash(text):
    return sha256(text.encode("latin1")).hexdigest()


class MaterialBindingManager:
    def __init__(self, session, *, clock=time.monotonic, ttl_seconds=DEFAULT_PLAN_TTL_SECONDS):
        self.session = session
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._plans: dict[str, _PreparedMaterialPlan] = {}
        self._expired_plan_ids: set[str] = set()

    def _current_handle(self):
        desc = self.session.describe()
        return {key: desc[key] for key in ("document_id", "document_epoch", "revision")}

    def _validate_handle(self, handle):
        if not isinstance(handle, dict) or set(handle) != {"document_id", "document_epoch", "revision"}:
            raise PrepError("invalid_handle", "Send the complete document handle returned by document.describe.")
        current = self._current_handle()
        if handle["document_id"] != current["document_id"] or handle["document_epoch"] != current["document_epoch"]:
            raise PrepError("document_conflict", "The GUI document was replaced. Query its current handle.", {"actual": current})
        if type(handle["revision"]) is not int or handle["revision"] != current["revision"]:
            raise PrepError("revision_conflict", "The GUI document changed. Query its current handle.", {"actual": current})
        return current

    def _resolve_target(self, target, document_id):
        if isinstance(target, dict):
            try:
                target = ObjectRef(**target)
            except TypeError:
                raise PrepError("invalid_reference", "Send a valid typed material card reference.") from None
        if (not isinstance(target, ObjectRef) or target.kind != "rad-card" or target.mesh_revision is not None
                or not all(isinstance(value, str) for value in
                           (target.document_id, target.resource_id, target.object_id, target.native_scope))):
            raise PrepError("invalid_reference", "Send the RAD card reference returned by document.cards.")
        if target.document_id != document_id:
            raise PrepError("document_conflict", "The material reference belongs to another document.")
        resource, card = self.session._object_card(target)
        identity = native_identity(card.keyword)
        words = card.keyword.upper().split("/")
        if identity is None or identity[0] != "MAT" or words[2] not in ("LAW1", "ELAST"):
            raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "This profile requires a /MAT/LAW1 or /MAT/ELAST card.")
        if len(words) != 4:
            raise PrepError("invalid_unit", "Per-card material unit overrides are outside the live binding profile.")
        if identity[1] < 1 or len(self.session._native_matches(*identity)) != 1:
            raise PrepError("invalid_reference", "The target needs a unique positive native material ID.")
        return resource, card

    def _expire_plans(self, now):
        for plan_id, plan in list(self._plans.items()):
            if now >= plan.deadline:
                self._expired_plan_ids.add(plan_id)
                del self._plans[plan_id]

    def prepare_apply(self, handle, target, profile_id, profile_revision, parameters, curves, evaluation_digest):
        with self.session._lock:
            current = self._validate_handle(handle)
            if profile_id != _PROFILE_ID or type(profile_revision) is not int or profile_revision != _PROFILE_REVISION:
                raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "The requested profile and revision have no registered live binding.")
            if not isinstance(curves, (list, tuple)):
                raise PrepError("invalid_request", "Curves must be a sequence.")
            if curves:
                raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "Elastic material binding does not accept companion curves.")
            if not isinstance(evaluation_digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", evaluation_digest):
                raise PrepError("invalid_request", "Supply the evaluation SHA-256 as 64 hexadecimal digits.")
            self.session._check_model_edit(current["revision"], current["document_id"])
            resource, card = self._resolve_target(target, current["document_id"])
            input_units = self.session._model_resource(None).unit_context()["global"]
            work_units = self.session._solver_work_units()
            deck_scales = _deck_scales(input_units)
            _deck_scales(work_units)
            if input_units != work_units:
                raise PrepError("unit_mismatch", "Input and working /BEGIN unit rows must agree for this profile.")

            before = self.session.card_text(card.id)
            fields = _material_fields(parameters, deck_scales)
            candidate = copy(resource)
            candidate.restore(resource.fields_state(card.id, fields))
            after = "".join(candidate.render().decode("latin1").splitlines(keepends=True)[card.start:card.stop])
            baseline_hash, candidate_hash = _card_hash(before), _card_hash(after)
            now = self._clock()
            expires_at = time.time() + self._ttl_seconds
            self._expire_plans(now)
            plan_id = str(uuid4())
            self._plans[plan_id] = _PreparedMaterialPlan(current.copy(), resource.id, card.id, candidate.snapshot(),
                                                        resource.state_token(), baseline_hash, candidate_hash,
                                                        evaluation_digest, now + self._ttl_seconds)
            diff = "".join(unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile=f"{card.keyword} (before)", tofile=f"{card.keyword} (after)"))
            return {"plan_id": plan_id, "handle": current, "baseline_hashes": {card.id: baseline_hash},
                    "candidate_hashes": {card.id: candidate_hash},
                    "changes_preview": [{"card_id": card.id, "keyword": card.keyword,
                                         "resource_name": self.session._paths[resource.id], "diff": diff}],
                    "expires_at": expires_at, "supported": True, "reason_codes": [],
                    "work_units": work_units, "expires_in_seconds": self._ttl_seconds,
                    "evaluation_digest": evaluation_digest}

    def commit_apply(self, plan_id, handle, candidate_hashes):
        with self.session._lock:
            current = self._validate_handle(handle)
            if not isinstance(plan_id, str) or not plan_id:
                raise PrepError("stale_material_plan", "Provide a valid prepared plan ID.")
            self._expire_plans(self._clock())
            if plan_id in self._expired_plan_ids:
                raise PrepError("plan_expired", "The material plan expired. Prepare a new plan.")
            plan = self._plans.get(plan_id)
            if plan is None:
                raise PrepError("stale_material_plan", "Material plan was not found or was already committed.")
            if plan.handle != current:
                raise PrepError("revision_conflict", "The document changed after material preparation.", {"actual": current})
            if candidate_hashes != {plan.card_id: plan.candidate_hash}:
                raise PrepError("hash_mismatch", "Candidate hashes differ from the prepared material plan.")
            resource = self.session._model_resource(plan.resource_id)
            if resource.state_token() != plan.baseline_token or _card_hash(self.session.card_text(plan.card_id)) != plan.baseline_hash:
                raise PrepError("revision_conflict", "The target resource changed after material preparation.")

            change = self.session.dispatcher.execute_many(
                {plan.resource_id: plan.state}, "Apply calibrated material parameters",
                object_ids=(plan.card_id,), expected_revision=handle["revision"], kind="values")
            del self._plans[plan_id]
            return {"status": "committed", "handle_after": self._current_handle(),
                    "command_id": f"{current['document_epoch']}:{change.revision}" if change else None,
                    "applied_hashes": {plan.card_id: _card_hash(self.session.card_text(plan.card_id))},
                    "evaluation_digest": plan.evaluation_digest, "reason_codes": [],
                    "change": change.to_dict() if change else None}
