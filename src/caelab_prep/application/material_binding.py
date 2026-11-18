"""PREP01 live material binding: non-mutating prepare and single-transaction commit."""
from __future__ import annotations

from copy import copy
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import difflib
import hashlib
import math
import time
from uuid import uuid4

from ..cae_core import PrepError
from ..radioss.deck import DeckResource
from ..radioss.modeling import curve_points
from .contracts import ObjectRef

SUPPORTED_EXPORTERS = ("radioss_law1_elastic_v1", "radioss_prony_visco_v1")
DEFAULT_PLAN_TTL_SECONDS = 60.0

_MASS_SI = {
    "kg": Decimal("1"),
    "g": Decimal("0.001"),
    "Mg": Decimal("1000"),
    "t": Decimal("1000"),
}
_LENGTH_SI = {
    "m": Decimal("1"),
    "cm": Decimal("0.01"),
    "mm": Decimal("0.001"),
}
_TIME_SI = {
    "s": Decimal("1"),
    "ms": Decimal("0.001"),
    "mus": Decimal("0.000001"),
    "us": Decimal("0.000001"),
    "µs": Decimal("0.000001"),
}
_STRESS_SI = {
    "Pa": Decimal("1"),
    "kPa": Decimal("1000"),
    "MPa": Decimal("1000000"),
    "GPa": Decimal("1000000000"),
}
_DENSITY_SI = {
    "kg/m³": Decimal("1"),
    "kg/m^3": Decimal("1"),
    "kg/m3": Decimal("1"),
    "g/cm³": Decimal("1000"),
    "g/cm^3": Decimal("1000"),
    "g/cm3": Decimal("1000"),
    "Mg/mm³": Decimal("1000000000000"),
    "Mg/mm^3": Decimal("1000000000000"),
    "Mg/mm3": Decimal("1000000000000"),
    "t/mm³": Decimal("1000000000000"),
    "t/mm^3": Decimal("1000000000000"),
    "t/mm3": Decimal("1000000000000"),
    "kg/mm³": Decimal("1000000000"),
    "kg/mm^3": Decimal("1000000000"),
    "kg/mm3": Decimal("1000000000"),
    "Mg/m³": Decimal("1000"),
    "Mg/m^3": Decimal("1000"),
    "Mg/m3": Decimal("1000"),
    "t/m³": Decimal("1000"),
    "t/m^3": Decimal("1000"),
    "t/m3": Decimal("1000"),
    "g/mm³": Decimal("1000000"),
    "g/mm^3": Decimal("1000000"),
    "g/mm3": Decimal("1000000"),
}
_DIMENSIONLESS = {"", "1", "dimensionless", "ratio", "-"}
_UNIT_SYSTEMS = {
    "mm-Mg-s": ("Mg", "mm", "s"),
    "mm-t-s": ("Mg", "mm", "s"),
    "m-kg-s": ("kg", "m", "s"),
    "SI": ("kg", "m", "s"),
    "mm-kg-s": ("kg", "mm", "s"),
    "mm-g-ms": ("g", "mm", "ms"),
    "mm-kg-ms": ("kg", "mm", "ms"),
    "cm-g-s": ("g", "cm", "s"),
}

_MATERIAL_ALIASES = {
    "young_modulus": "young_modulus",
    "E": "young_modulus",
    "E0": "young_modulus",
    "e0": "young_modulus",
    "poisson_ratio": "poisson_ratio",
    "nu": "poisson_ratio",
    "density": "density",
    "rho": "density",
    "RHO_I": "density",
}


@dataclass(frozen=True)
class _PreparedMaterialPlan:
    plan_id: str
    document_id: str
    document_epoch: str
    revision: int
    exporter_id: str
    target: ObjectRef
    states: dict[str, dict]
    baseline_tokens: dict[str, str]
    object_ids: tuple[str, ...]
    candidate_hashes: dict[str, str]
    expires_at: float


def _finite_decimal(value, *, field_name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PrepError("invalid_value", f"Numeric value required for '{field_name}'.", {"field": field_name})
    number = float(value)
    if not math.isfinite(number):
        raise PrepError("invalid_value", f"Finite numeric value required for '{field_name}'.", {"field": field_name})
    try:
        return Decimal(repr(number))
    except InvalidOperation:
        raise PrepError("invalid_value", f"Invalid numeric value for '{field_name}'.", {"field": field_name}) from None


def _parse_system_triple(units_dict):
    if {"mass", "length", "time"} <= set(units_dict):
        m, l, t = units_dict["mass"], units_dict["length"], units_dict["time"]
        if m not in _MASS_SI or l not in _LENGTH_SI or t not in _TIME_SI:
            raise PrepError("invalid_unit", "Unsupported mass/length/time system unit symbol.", {"units": units_dict})
        return m, l, t
    if "unit_system" in units_dict:
        triple = _UNIT_SYSTEMS.get(units_dict["unit_system"])
        if triple is None:
            raise PrepError("invalid_unit", "Unsupported named unit system.", {"unit_system": units_dict["unit_system"]})
        return triple
    return None


def _resolve_density_si(unit_str):
    if not isinstance(unit_str, str):
        raise PrepError("invalid_unit", "Density unit must be a non-empty string.")
    cleaned = unit_str.strip()
    if cleaned in _DENSITY_SI:
        return _DENSITY_SI[cleaned]
    normalized = cleaned.replace("³", "^3").replace(" ", "")
    if normalized in _DENSITY_SI:
        return _DENSITY_SI[normalized]
    if "/" in normalized:
        num, den = normalized.split("/", 1)
        if den.endswith("^3") or den.endswith("3"):
            len_sym = den[:-2] if den.endswith("^3") else den[:-1]
            if num in _MASS_SI and len_sym in _LENGTH_SI:
                return _MASS_SI[num] / (_LENGTH_SI[len_sym] ** 3)
    raise PrepError("invalid_unit", f"Unsupported density unit '{unit_str}'.", {"unit": unit_str})


def _resolve_stress_si(unit_str):
    if not isinstance(unit_str, str):
        raise PrepError("invalid_unit", "Stress/modulus unit must be a non-empty string.")
    cleaned = unit_str.strip()
    if cleaned in _STRESS_SI:
        return _STRESS_SI[cleaned]
    normalized = cleaned.replace("·", "*").replace("²", "^2").replace(" ", "")
    # Support deck-style composite forms like Mg/(mm*s^2)
    if "/(" in normalized and normalized.endswith(")"):
        mass_part, rest = normalized.split("/(", 1)
        rest = rest[:-1]
        if "*" in rest:
            len_part, time_part = rest.split("*", 1)
            if (time_part.endswith("^2") or time_part.endswith("2")) and mass_part in _MASS_SI and len_part in _LENGTH_SI:
                t_sym = time_part[:-2] if time_part.endswith("^2") else time_part[:-1]
                if t_sym in _TIME_SI:
                    return _MASS_SI[mass_part] / (_LENGTH_SI[len_part] * (_TIME_SI[t_sym] ** 2))
    raise PrepError("invalid_unit", f"Unsupported stress/modulus unit '{unit_str}'.", {"unit": unit_str})


def _resolve_time_si(unit_str):
    if not isinstance(unit_str, str) or unit_str.strip() not in _TIME_SI:
        raise PrepError("invalid_unit", f"Unsupported time unit '{unit_str}'.", {"unit": unit_str})
    return _TIME_SI[unit_str.strip()]


def _resolve_field_unit(units_dict, *, field_keys, quantity_key, dimension, work_scales):
    for key in (*field_keys, quantity_key):
        if key in units_dict:
            spec = units_dict[key]
            if dimension == "dimensionless":
                if not isinstance(spec, str) or spec.strip() not in _DIMENSIONLESS:
                    raise PrepError("invalid_unit", f"Field '{field_keys[0]}' is dimensionless.", {"unit": spec})
                return Decimal("1"), spec.strip()
            if dimension == "density":
                return _resolve_density_si(spec), spec.strip()
            if dimension == "stress":
                return _resolve_stress_si(spec), spec.strip()
            if dimension == "time":
                return _resolve_time_si(spec), spec.strip()
    triple = _parse_system_triple(units_dict)
    if triple is not None:
        m, l, t = triple
        if dimension == "dimensionless":
            return Decimal("1"), "1"
        if dimension == "density":
            return _MASS_SI[m] / (_LENGTH_SI[l] ** 3), f"{m}/{l}³"
        if dimension == "stress":
            return _MASS_SI[m] / (_LENGTH_SI[l] * (_TIME_SI[t] ** 2)), f"{m}/({l}·{t}²)"
        if dimension == "time":
            return _TIME_SI[t], t
    if dimension == "dimensionless":
        if units_dict:
            return Decimal("1"), "1"
    raise PrepError("invalid_units", f"Explicit unit is required for '{field_keys[0]}'; units are never guessed.", {"field": field_keys[0]})


def _work_scales(work_units):
    mass = _MASS_SI.get(work_units.get("mass"))
    length = _LENGTH_SI.get(work_units.get("length"))
    t_scale = _TIME_SI.get(work_units.get("time"))
    if mass is None or length is None or t_scale is None:
        raise PrepError("invalid_units", "Document solver work units are outside the supported Radioss profile.", {"work_units": work_units})
    return {
        "density": mass / (length ** 3),
        "stress": mass / (length * (t_scale ** 2)),
        "time": t_scale,
    }


def _convert(value, *, src_si, dst_si, field_name):
    dec = _finite_decimal(value, field_name=field_name)
    converted = float(dec * src_si / dst_si)
    if not math.isfinite(converted):
        raise PrepError("invalid_value", f"Converted value for '{field_name}' overflows finite range.", {"field": field_name})
    return converted


def _curve_replaced_state(resource: DeckResource, card_id: str, points) -> dict:
    card = resource.card(card_id)
    words = card.keyword.upper().split("/")
    if len(words) < 2 or words[1] != "FUNCT" or len(card.data) < 2:
        raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "Only standard /FUNCT curves with numeric rows are supported.")
    rows = curve_points(points)
    card_text = "".join(resource.lines[card.start:card.stop])
    lines = card_text.splitlines(keepends=True)
    point_rows = {index - card.start for index in card.data[1:]}
    result, cursor = [], 0
    last = max(point_rows)
    for index, line in enumerate(lines):
        if index not in point_rows:
            result.append(line)
        elif cursor < len(rows):
            ending = "\r\n" if line.endswith("\r\n") else "\r" if line.endswith("\r") else "\n"
            result.append(rows[cursor] + ending)
            cursor += 1
        if index == last:
            result.extend(row + resource.newline for row in rows[cursor:])
            cursor = len(rows)
    return resource.replaced_state(card_id, "".join(result))


def _rendered_card_text(resource: DeckResource, card_id: str) -> str:
    rendered_lines = resource.render().decode("latin1").splitlines(keepends=True)
    probe = copy(resource)
    probe._parse_layout(rendered_lines, [card.id for card in resource.cards])
    card = probe.card(card_id)
    return "".join(rendered_lines[card.start:card.stop])


def _sample_prony_curve(terms, units_dict, work_scales, *, scale_stress=None):
    if not isinstance(terms, (list, tuple)) or not terms:
        raise PrepError("invalid_value", "Prony series requires at least one non-empty term.")
    converted_terms = []
    sum_g = 0.0
    tau_src_si, _ = _resolve_field_unit(units_dict, field_keys=("tau", "time"), quantity_key="time", dimension="time", work_scales=work_scales)
    for idx, term in enumerate(terms):
        if not isinstance(term, dict):
            raise PrepError("invalid_value", "Each Prony term must be a dict containing g and tau.")
        g_raw = term.get("g", term.get("g_i", term.get("k")))
        tau_raw = term.get("tau", term.get("tau_i"))
        if g_raw is None or tau_raw is None:
            raise PrepError("invalid_value", "Each Prony term requires relaxation weight and time constant.")
        g_val = float(_finite_decimal(g_raw, field_name=f"prony[{idx}].g"))
        tau_val = _convert(tau_raw, src_si=tau_src_si, dst_si=work_scales["time"], field_name=f"prony[{idx}].tau")
        if not (0.0 < g_val < 1.0) or tau_val <= 0.0:
            raise PrepError("invalid_value", "Prony weights must be in (0, 1) and relaxation times positive.")
        sum_g += g_val
        converted_terms.append((g_val, tau_val))
    if sum_g >= 1.0:
        raise PrepError("invalid_value", "Sum of Prony relaxation weights must be strictly less than 1.0.")
    min_tau = min(t for _, t in converted_terms)
    max_tau = max(t for _, t in converted_terms)
    lo = math.log10(min_tau * 0.1)
    hi = math.log10(max_tau * 10.0)
    steps = 10
    times = [0.0] + [10.0 ** (lo + (hi - lo) * i / (steps - 1)) for i in range(steps)]
    scale = 1.0 if scale_stress is None else scale_stress
    points = []
    for t_val in times:
        relax = (1.0 - sum_g) + sum(g_i * math.exp(-t_val / tau_i) for g_i, tau_i in converted_terms)
        points.append((t_val, scale * relax))
    return points


class MaterialBindingManager:
    """Manage staged material/curve calibration prepare and single-commit apply."""

    def __init__(self, session, *, clock=time.monotonic, ttl_seconds: float = DEFAULT_PLAN_TTL_SECONDS):
        self.session = session
        self._clock = clock
        self._ttl_seconds = float(ttl_seconds)
        self._plans: dict[str, _PreparedMaterialPlan] = {}

    def _current_handle(self):
        desc = self.session.describe()
        return {key: desc[key] for key in ("document_id", "document_epoch", "revision")}

    def _validate_handle(self, handle):
        if not isinstance(handle, dict) or set(handle) != {"document_id", "document_epoch", "revision"}:
            raise PrepError("invalid_handle", "Send the complete document handle returned by document.describe.")
        current = self._current_handle()
        if handle.get("document_id") != current["document_id"] or handle.get("document_epoch") != current["document_epoch"]:
            raise PrepError("document_conflict", "The GUI document was replaced. Query its current handle.", {"actual": current})
        if type(handle.get("revision")) is not int or handle["revision"] != current["revision"]:
            raise PrepError("revision_conflict", "The GUI document changed. Query its current handle.", {"actual": current})
        return current

    def _resolve_target(self, raw_target, *, current_doc_id: str) -> tuple[ObjectRef, DeckResource, object]:
        if isinstance(raw_target, ObjectRef):
            ref = raw_target
        elif isinstance(raw_target, dict):
            try:
                ref = ObjectRef(**raw_target)
            except TypeError:
                raise PrepError("invalid_reference", "Send a valid typed ObjectRef for target.") from None
        else:
            raise PrepError("invalid_reference", "Send a valid typed ObjectRef for target.")
        if ref.document_id != current_doc_id:
            raise PrepError("document_conflict", "Target reference belongs to another document.")
        resource = self.session._find_card(ref.object_id)
        card = resource.card(ref.object_id)
        if ref.resource_id != resource.id or ref.native_scope != card.keyword:
            raise PrepError("invalid_reference", "Target reference resource or native keyword does not match current document.",
                            {"card_id": ref.object_id})
        return ref, resource, card

    def _resolve_card_spec_ref(self, entry: dict, *, current_doc_id: str) -> tuple[ObjectRef, DeckResource, object]:
        if "target" in entry:
            return self._resolve_target(entry["target"], current_doc_id=current_doc_id)
        if "card_id" in entry and isinstance(entry["card_id"], str):
            resource = self.session._find_card(entry["card_id"])
            card = resource.card(entry["card_id"])
            return ObjectRef(current_doc_id, resource.id, card.id, "rad-card", card.keyword), resource, card
        raise PrepError("invalid_reference", "Each card update entry requires a target ObjectRef or card_id.")

    def _verify_unit_environment(self, card):
        work_units = self.session._solver_work_units()
        scales = _work_scales(work_units)
        root = self.session._model_resource(None)
        input_units = root.unit_context()["global"]
        if input_units is not None and input_units != work_units:
            raise PrepError("unit_mismatch", "Input and working BEGIN unit rows differ; ambiguous conversion is rejected.",
                            {"input_units": input_units, "work_units": work_units})
        words = card.keyword.upper().split("/")
        if len(words) > 4 and words[1] == "MAT":
            raise PrepError("invalid_unit", "Per-card /MAT unit override is preserved; calibrated unit conversion is unavailable.",
                            {"card_id": card.id})
        return work_units, scales

    def _convert_material_fields(self, card, params: dict, units_dict: dict, work_scales: dict) -> dict[str, float]:
        if not isinstance(params, dict):
            raise PrepError("invalid_request", "Material parameters must be a JSON object.")
        if not isinstance(units_dict, dict) or not units_dict:
            raise PrepError("invalid_units", "Explicit parameter units dictionary is required and never guessed.")
        canonical = {}
        for key, raw_value in params.items():
            if key in ("prony_terms", "terms", "points"):
                continue
            target_name = _MATERIAL_ALIASES.get(key)
            if target_name is None:
                raise PrepError("unsupported_operation", f"Unsupported material parameter '{key}'.", {"parameter": key})
            if target_name in canonical:
                raise PrepError("invalid_request", f"Duplicate parameter alias for '{target_name}'.")
            canonical[target_name] = (key, raw_value)
        converted = {}
        for target_name, (orig_key, raw_value) in canonical.items():
            if target_name == "young_modulus":
                src_si, _ = _resolve_field_unit(
                    units_dict, field_keys=(orig_key, "young_modulus", "E", "modulus"), quantity_key="stress",
                    dimension="stress", work_scales=work_scales)
                val = _convert(raw_value, src_si=src_si, dst_si=work_scales["stress"], field_name=orig_key)
                if val <= 0:
                    raise PrepError("invalid_value", "Young modulus must be strictly positive.", {"field": orig_key})
                converted["young_modulus"] = val
            elif target_name == "density":
                src_si, _ = _resolve_field_unit(
                    units_dict, field_keys=(orig_key, "density", "rho", "RHO_I"), quantity_key="density",
                    dimension="density", work_scales=work_scales)
                val = _convert(raw_value, src_si=src_si, dst_si=work_scales["density"], field_name=orig_key)
                if val <= 0:
                    raise PrepError("invalid_value", "Density must be strictly positive.", {"field": orig_key})
                converted["density"] = val
            elif target_name == "poisson_ratio":
                _resolve_field_unit(
                    units_dict, field_keys=(orig_key, "poisson_ratio", "nu"), quantity_key="dimensionless",
                    dimension="dimensionless", work_scales=work_scales)
                val = float(_finite_decimal(raw_value, field_name=orig_key))
                if not (-1.0 < val < 0.5):
                    raise PrepError("invalid_value", "Poisson ratio must lie strictly in (-1, 0.5).", {"field": orig_key})
                converted["poisson_ratio"] = val
        return converted

    def _convert_curve_points(self, points, units_dict: dict, work_scales: dict) -> list[tuple[float, float]]:
        if not isinstance(units_dict, dict) or not units_dict:
            raise PrepError("invalid_units", "Explicit units are required for curve point conversion.")
        if not isinstance(points, (list, tuple)) or len(points) < 2:
            raise PrepError("invalid_curve", "A curve requires at least two X/Y points.")
        x_spec = next((units_dict[k] for k in ("x", "points_x", "curve_x", "time") if k in units_dict), None)
        y_spec = next((units_dict[k] for k in ("y", "points_y", "curve_y", "stress", "modulus") if k in units_dict), None)
        triple = _parse_system_triple(units_dict)
        if x_spec is None:
            if triple is not None:
                x_src_si = _TIME_SI[triple[2]]
            else:
                raise PrepError("invalid_units", "Explicit X-axis unit (e.g. 'x' or 'time') is required for curve points.")
        elif isinstance(x_spec, str) and x_spec.strip() in _DIMENSIONLESS:
            x_src_si = work_scales["time"]
        else:
            x_src_si = _resolve_time_si(x_spec)
        if y_spec is None:
            if triple is not None:
                m, l, t = triple
                y_src_si = _MASS_SI[m] / (_LENGTH_SI[l] * (_TIME_SI[t] ** 2))
            else:
                raise PrepError("invalid_units", "Explicit Y-axis unit (e.g. 'y' or 'stress') is required for curve points.")
        elif isinstance(y_spec, str) and y_spec.strip() in _DIMENSIONLESS:
            y_src_si = work_scales["stress"]
        else:
            y_src_si = _resolve_stress_si(y_spec)
        result = []
        for idx, pt in enumerate(points):
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise PrepError("invalid_curve", f"Curve point {idx} must be [x, y].")
            x_val = _convert(pt[0], src_si=x_src_si, dst_si=work_scales["time"], field_name=f"points[{idx}][0]")
            y_val = _convert(pt[1], src_si=y_src_si, dst_si=work_scales["stress"], field_name=f"points[{idx}][1]")
            result.append((x_val, y_val))
        curve_points(result)
        return result

    def prepare_apply(self, handle, target, exporter_id: str, parameters: dict, units: dict, cards=None) -> dict:
        with self.session._lock:
            current = self._validate_handle(handle)
            now = self._clock()
            for stale_id in [pid for pid, item in self._plans.items() if now > item.expires_at]:
                del self._plans[stale_id]
            if not isinstance(exporter_id, str) or exporter_id not in SUPPORTED_EXPORTERS:
                raise PrepError("UNSUPPORTED_ATOMIC_APPLY", f"Unsupported material exporter '{exporter_id}'.",
                                {"exporter_id": exporter_id, "supported": list(SUPPORTED_EXPORTERS)})
            if not isinstance(parameters, dict):
                raise PrepError("invalid_request", "Parameters must be a dictionary.")
            if not isinstance(units, dict) or not units:
                raise PrepError("invalid_units", "Explicit parameter units dictionary is required and never guessed.")
            target_ref, target_res, target_card = self._resolve_target(target, current_doc_id=current["document_id"])
            work_units, work_scales = self._verify_unit_environment(target_card)
            words = target_card.keyword.upper().split("/")
            if exporter_id == "radioss_law1_elastic_v1":
                if len(words) < 3 or words[1] != "MAT" or words[2] not in ("LAW1", "ELAST"):
                    raise PrepError("UNSUPPORTED_ATOMIC_APPLY",
                                    "Exporter radioss_law1_elastic_v1 requires a /MAT/LAW1 or /MAT/ELAST card target.",
                                    {"keyword": target_card.keyword})
                if not parameters and not cards:
                    raise PrepError("invalid_request", "Provide calibrated elastic parameters to apply.")
            else:
                if len(words) < 2 or words[1] not in ("MAT", "FUNCT"):
                    raise PrepError("UNSUPPORTED_ATOMIC_APPLY",
                                    "Exporter radioss_prony_visco_v1 requires a /MAT or /FUNCT card target.",
                                    {"keyword": target_card.keyword})
                if words[1] == "MAT" and (len(words) < 3 or words[2] not in ("LAW1", "ELAST", "LAW36", "PLAS_TAB")):
                    raise PrepError("UNSUPPORTED_ATOMIC_APPLY",
                                    "Target material card does not expose a supported scalar/tabular schema.",
                                    {"keyword": target_card.keyword})

            # Normalize additional card operations (companion /FUNCT curves or multi-resource /MAT updates)
            card_entries = []
            if cards is not None:
                if isinstance(cards, (list, tuple)):
                    card_entries = list(cards)
                elif isinstance(cards, dict):
                    card_entries = list(cards.values())
                else:
                    raise PrepError("invalid_request", "Companion cards specification must be a list or mapping.")

            working: dict[str, DeckResource] = {}
            baseline_texts: dict[str, str] = {}
            touched_order: list[tuple[str, str, str]] = []  # (resource_id, card_id, keyword)

            def get_working(res: DeckResource) -> DeckResource:
                if res.id not in working:
                    working[res.id] = copy(res)
                return working[res.id]

            def record_baseline(res: DeckResource, card_id: str, keyword: str):
                if card_id not in baseline_texts:
                    baseline_texts[card_id] = self.session.card_text(card_id)
                    touched_order.append((res.id, card_id, keyword))

            # Apply updates to primary target
            scalar_fields = self._convert_material_fields(target_card, parameters, units, work_scales)
            if words[1] == "MAT" and scalar_fields:
                record_baseline(target_res, target_card.id, target_card.keyword)
                wres = get_working(target_res)
                wres.restore(wres.fields_state(target_card.id, scalar_fields))
            elif words[1] == "FUNCT":
                if scalar_fields:
                    raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "Scalar elastic fields do not apply directly to a /FUNCT target.")
                pts = parameters.get("points")
                if pts is not None:
                    pts_conv = self._convert_curve_points(pts, units, work_scales)
                elif "prony_terms" in parameters or "terms" in parameters:
                    terms = parameters.get("prony_terms", parameters.get("terms"))
                    pts_conv = _sample_prony_curve(terms, units, work_scales)
                else:
                    pts_conv = None
                if pts_conv is not None:
                    record_baseline(target_res, target_card.id, target_card.keyword)
                    wres = get_working(target_res)
                    wres.restore(_curve_replaced_state(wres, target_card.id, pts_conv))

            # Route Prony/points onto companion cards
            pending_prony_terms = parameters.get("prony_terms", parameters.get("terms")) if words[1] == "MAT" else None
            pending_top_points = parameters.get("points") if words[1] == "MAT" else None
            prony_consumed = False
            for idx, entry in enumerate(card_entries):
                if not isinstance(entry, dict):
                    raise PrepError("invalid_request", f"Card update entry {idx} must be an object.")
                cref, cres, ccard = self._resolve_card_spec_ref(entry, current_doc_id=current["document_id"])
                self._verify_unit_environment(ccard)
                cwords = ccard.keyword.upper().split("/")
                entry_units = entry.get("units", units)
                if cwords[1] == "FUNCT":
                    if exporter_id == "radioss_law1_elastic_v1":
                        raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "Elastic LAW1 exporter cannot modify /FUNCT cards.")
                    if "points" in entry:
                        cpoints = self._convert_curve_points(entry["points"], entry_units, work_scales)
                    elif pending_top_points is not None and not prony_consumed:
                        cpoints = self._convert_curve_points(pending_top_points, entry_units, work_scales)
                        prony_consumed = True
                    elif pending_prony_terms is not None and not prony_consumed:
                        scale_y = scalar_fields.get("young_modulus")
                        cpoints = _sample_prony_curve(pending_prony_terms, entry_units, work_scales, scale_stress=scale_y)
                        prony_consumed = True
                    else:
                        raise PrepError("invalid_request", f"Companion /FUNCT card '{ccard.id}' has no curve points or Prony terms.")
                    record_baseline(cres, ccard.id, ccard.keyword)
                    wres = get_working(cres)
                    wres.restore(_curve_replaced_state(wres, ccard.id, cpoints))
                elif cwords[1] == "MAT":
                    cparams = entry.get("parameters", entry.get("fields", entry.get("values")))
                    if cparams is None:
                        raise PrepError("invalid_request", f"Card entry '{ccard.id}' requires parameters.")
                    cfields = self._convert_material_fields(ccard, cparams, entry_units, work_scales)
                    if not cwords[2] in ("LAW1", "ELAST", "LAW36", "PLAS_TAB"):
                        raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "Card material keyword is not writable.", {"keyword": ccard.keyword})
                    if exporter_id == "radioss_law1_elastic_v1" and cwords[2] not in ("LAW1", "ELAST"):
                        raise PrepError("UNSUPPORTED_ATOMIC_APPLY", "LAW1 exporter cannot update non-elastic material cards.")
                    if cfields:
                        record_baseline(cres, ccard.id, ccard.keyword)
                        wres = get_working(cres)
                        wres.restore(wres.fields_state(ccard.id, cfields))
                else:
                    raise PrepError("UNSUPPORTED_ATOMIC_APPLY", f"Unsupported card family '{ccard.keyword}' in material binding.")

            if pending_prony_terms is not None and not prony_consumed and not scalar_fields:
                raise PrepError("UNSUPPORTED_ATOMIC_APPLY",
                                "Prony terms require a companion /FUNCT curve in cards or a /FUNCT target.",
                                {"exporter_id": exporter_id})

            if not touched_order:
                raise PrepError("invalid_request", "No writable material or curve updates were specified.")

            states = {rid: res.snapshot() for rid, res in working.items()}
            baseline_tokens = {rid: self.session.document.resources[rid].state_token() for rid in working}
            # Validate on an isolated planning snapshot (zero live document mutation).
            planned = self.session._planning_snapshot()
            for rid, state in states.items():
                planned.document.resources[rid].restore(state)

            diffs = []
            baseline_hashes = {}
            candidate_hashes = {}
            card_summaries = []
            for rid, card_id, keyword in touched_order:
                before_text = baseline_texts[card_id]
                after_text = _rendered_card_text(working[rid], card_id)
                b_hash = hashlib.sha256(before_text.encode("latin1")).hexdigest()
                a_hash = hashlib.sha256(after_text.encode("latin1")).hexdigest()
                baseline_hashes[card_id] = b_hash
                candidate_hashes[card_id] = a_hash
                res_name = self.session._paths.get(rid, rid)
                diff_lines = list(difflib.unified_diff(
                    before_text.splitlines(keepends=True),
                    after_text.splitlines(keepends=True),
                    fromfile=f"{res_name}:{keyword} (before)",
                    tofile=f"{res_name}:{keyword} (after)",
                ))
                diffs.append("".join(diff_lines))
                card_summaries.append({
                    "resource_id": rid,
                    "resource_name": res_name,
                    "card_id": card_id,
                    "keyword": keyword,
                    "baseline_hash": b_hash,
                    "candidate_hash": a_hash,
                })

            plan_id = str(uuid4())
            object_ids = tuple(card_id for _, card_id, _ in touched_order)
            self._plans[plan_id] = _PreparedMaterialPlan(
                plan_id=plan_id,
                document_id=current["document_id"],
                document_epoch=current["document_epoch"],
                revision=current["revision"],
                exporter_id=exporter_id,
                target=target_ref,
                states=states,
                baseline_tokens=baseline_tokens,
                object_ids=object_ids,
                candidate_hashes=candidate_hashes,
                expires_at=now + self._ttl_seconds,
            )
            return {
                "plan_id": plan_id,
                "handle": current,
                "target": asdict(target_ref),
                "exporter_id": exporter_id,
                "admissible": True,
                "diff": "\n".join(part for part in diffs if part),
                "baseline_hashes": baseline_hashes,
                "candidate_hashes": candidate_hashes,
                "applied_cards": card_summaries,
                "work_units": work_units,
                "expires_in_seconds": int(self._ttl_seconds),
            }

    def commit_apply(self, handle, plan_id: str, expected_revision: int) -> dict:
        with self.session._lock:
            current = self._validate_handle(handle)
            if type(expected_revision) is not int or expected_revision != current["revision"]:
                raise PrepError("revision_conflict", "The GUI document changed. Query its current handle.",
                                {"expected": expected_revision, "actual": current["revision"]})
            if not isinstance(plan_id, str) or not plan_id:
                raise PrepError("stale_material_plan", "Provide a valid prepared plan_id.")
            plan = self._plans.get(plan_id)
            if plan is None:
                raise PrepError("stale_material_plan", "Material prepare plan not found or already consumed.",
                                {"plan_id": plan_id})
            if self._clock() > plan.expires_at:
                self._plans.pop(plan_id, None)
                raise PrepError("plan_expired", "Material prepare plan expired after 60 seconds; prepare a new plan.",
                                {"plan_id": plan_id})
            if (plan.document_id, plan.document_epoch, plan.revision) != (
                current["document_id"], current["document_epoch"], current["revision"]
            ):
                raise PrepError("revision_conflict", "Document handle changed since material.prepare_apply.",
                                {"actual": current})
            for rid, token in plan.baseline_tokens.items():
                resource = self.session.document.resources.get(rid)
                if resource is None or resource.state_token() != token:
                    raise PrepError("revision_conflict", "A target resource changed since material.prepare_apply.",
                                    {"resource_id": rid})
            change = self.session.dispatcher.execute_many(
                plan.states,
                "Apply calibrated material parameters",
                object_ids=plan.object_ids,
                expected_revision=expected_revision,
            )
            self._plans.pop(plan_id, None)
            applied_hashes = {}
            for card_id in plan.object_ids:
                after_text = self.session.card_text(card_id)
                applied_hashes[card_id] = hashlib.sha256(after_text.encode("latin1")).hexdigest()
            return {
                "status": "committed",
                "plan_id": plan_id,
                "exporter_id": plan.exporter_id,
                "target": asdict(plan.target),
                "handle": self._current_handle(),
                "changed": change is not None,
                "change": change.to_dict() if change is not None else None,
                "applied_hashes": applied_hashes,
                "applied_card_ids": list(plan.object_ids),
            }
