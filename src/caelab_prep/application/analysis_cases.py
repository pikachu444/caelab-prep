"""Persisted run alternatives; conditions remain owned by the native document.

A case is a separate resource so one case edit uses the same atomic command,
Undo and saved-state contract as native cards. It does not clone a solver deck.
"""
from copy import copy, deepcopy
from hashlib import sha256
import json
import math
from uuid import UUID, uuid4, uuid5

from ..cae_core import PrepError


TIME_SECONDS = {"s": 1.0, "ms": .001, "mus": .000001}


def condition_kind(keyword):
    words = keyword.upper().strip("/").split("/")
    if words[0] in ("BCS", "CLOAD"):
        return words[0]
    if tuple(words[:2]) in (("INIVEL", "TRA"), ("INTER", "TYPE7")):
        return "/".join(words[:2])
    return None


def checked_case(value):
    if not isinstance(value, dict) or set(value) != {"id", "name", "condition_ids", "end_time", "output_interval", "time_unit"}:
        raise PrepError("invalid_analysis_case", "A case needs a name, explicit active conditions, end time, output interval and time unit.")
    result = deepcopy(value)
    try:
        if not isinstance(result["id"], str): raise ValueError()
        UUID(result["id"])
    except (ValueError, TypeError, AttributeError):
        raise PrepError("invalid_analysis_case", "Invalid analysis case identity.") from None
    if not isinstance(result["name"], str) or not result["name"].strip() or len(result["name"]) > 100 or any(ord(c) < 32 for c in result["name"]):
        raise PrepError("invalid_analysis_case", "Use a nonempty case name of at most 100 characters without control characters.")
    refs = result["condition_ids"]
    if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs) or len(set(refs)) != len(refs):
        raise PrepError("invalid_analysis_case", "Active condition UUIDs must be an explicit list without duplicates; an empty list activates none.")
    for item in refs:
        try: UUID(item)
        except ValueError: raise PrepError("invalid_analysis_case", "A condition UUID is required.") from None
    if not isinstance(result["time_unit"], str) or result["time_unit"] not in TIME_SECONDS:
        raise PrepError("invalid_units", "Choose an explicit case time unit: s, ms or mus.")
    for key in ("end_time", "output_interval"):
        try:
            if type(result[key]) not in (int, float): raise ValueError()
            value = float(result[key])
            if not math.isfinite(value) or value <= 0: raise ValueError()
        except (ValueError, OverflowError):
            raise PrepError("invalid_analysis_case", "Case times must be finite positive numbers.", {"field": key})
        result[key] = value
    if result["output_interval"] > result["end_time"]:
        raise PrepError("invalid_analysis_case", "Output interval must not exceed the end time.")
    return result


class AnalysisCasesResource:
    kind = "analysis-cases"

    def __init__(self, document_id, state=None):
        self.id = str(uuid5(UUID(document_id), "caelab-prep-analysis-cases"))
        self._state = {"state_version": 1, "cases": [], "active_case_id": None}
        if state is not None: self.restore(state)

    def snapshot(self):
        return deepcopy(self._state)

    def prepare_state(self, state):
        candidate = copy(self)
        candidate.restore(state)
        return candidate.snapshot()

    def restore(self, state):
        if not isinstance(state, dict) or set(state) != {"state_version", "cases", "active_case_id"} or type(state["state_version"]) is not int or state["state_version"] != 1 or not isinstance(state["cases"], list):
            raise PrepError("invalid_analysis_case", "Unsupported analysis case state.")
        cases = [checked_case(item) for item in state["cases"]]
        ids = [item["id"] for item in cases]
        names = [item["name"].strip().casefold() for item in cases]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise PrepError("invalid_analysis_case", "Case identities and names must be distinct.")
        active = state["active_case_id"]
        if active is not None and (not isinstance(active, str) or active not in ids):
            raise PrepError("invalid_analysis_case", "The selected case does not exist.")
        self._state = {"state_version": 1, "cases": cases, "active_case_id": active}

    def state_token(self):
        return sha256(json.dumps(self._state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class AnalysisCaseCommands:
    """Session API; kept separate from Qt and presentation profiles."""

    def _cases_resource(self):
        return next(resource for resource in self._require().resources.values() if isinstance(resource, AnalysisCasesResource))

    def analysis_cases(self):
        with self._lock:
            state = self._cases_resource().snapshot()
            return {**state, "document_id": self.document.id, "revision": self.document.revision}

    def analysis_case(self, case_id=None):
        with self._lock:
            state = self.analysis_cases()
            target = case_id if case_id is not None else state["active_case_id"]
            case = next((item for item in state["cases"] if item["id"] == target), None)
            if case is None:
                raise PrepError("analysis_case_not_found", "Choose an existing analysis case.", {"case_id": target})
            return {**case, "document_id": self.document.id, "revision": self.document.revision}

    def analysis_case_conditions(self):
        """Condition choices include their existing native targets, without copying them."""
        with self._lock:
            result = []
            for card in self.list_cards():
                if condition_kind(card["keyword"]) is None: continue
                try: values = self.condition_values(card["id"])
                except PrepError as exc:
                    values = {"diagnostics": [{"code": exc.code, "message": exc.message}]}
                result.append({**card, "condition_kind": condition_kind(card["keyword"]), "values": values})
            return result

    def _validate_case_refs(self, case):
        for card_id in case["condition_ids"]:
            resource = self._find_card(card_id)
            if condition_kind(resource.card(card_id).keyword) is None:
                raise PrepError("invalid_reference", "An active case member must be a supported native condition.", {"card_id": card_id})

    def _commit_cases(self, state, label, case_id, expected_revision):
        resource = self._cases_resource()
        change = self.dispatcher.execute(resource.id, state, label, object_ids=(case_id,) if case_id else (),
                                         expected_revision=expected_revision, kind="analysis_case")
        return {**self.analysis_cases(), "case_id": case_id, "resource_id": resource.id,
                "change": change.to_dict() if change else None}

    def create_analysis_case(self, name, condition_ids, end_time, output_interval, time_unit, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            case = checked_case(dict(id=str(uuid4()), name=name, condition_ids=condition_ids,
                                     end_time=end_time, output_interval=output_interval, time_unit=time_unit))
            self._validate_case_refs(case)
            state = self._cases_resource().snapshot()
            state["cases"].append(case)
            state["active_case_id"] = case["id"]
            return self._commit_cases(state, "Create analysis case", case["id"], expected_revision)

    def set_analysis_case(self, case_id, values, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            if not isinstance(values, dict) or not values or set(values) - {"name", "condition_ids", "end_time", "output_interval", "time_unit"}:
                raise PrepError("invalid_analysis_case", "Choose editable case values.")
            current = self.analysis_case(case_id)
            current = {key: value for key, value in current.items() if key not in ("document_id", "revision")}
            case = checked_case({**current, **values})
            self._validate_case_refs(case)
            state = self._cases_resource().snapshot()
            state["cases"] = [case if item["id"] == case_id else item for item in state["cases"]]
            return self._commit_cases(state, "Edit analysis case", case_id, expected_revision)

    def copy_analysis_case(self, case_id, name=None, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            current = self.analysis_case(case_id)
            if name is None:
                names = {item["name"].strip().casefold() for item in self.analysis_cases()["cases"]}
                index = 1
                while True:
                    name = current["name"][:85] + f" copy {index}"
                    if name.casefold() not in names: break
                    index += 1
            return self.create_analysis_case(name, current["condition_ids"], current["end_time"],
                current["output_interval"], current["time_unit"], expected_revision=expected_revision,
                expected_document_id=expected_document_id)

    def delete_analysis_case(self, case_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            self.analysis_case(case_id)
            state = self._cases_resource().snapshot()
            state["cases"] = [item for item in state["cases"] if item["id"] != case_id]
            if state["active_case_id"] == case_id: state["active_case_id"] = None
            return self._commit_cases(state, "Delete analysis case", case_id, expected_revision)

    def select_analysis_case(self, case_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            if case_id is not None: self.analysis_case(case_id)
            state = self._cases_resource().snapshot()
            state["active_case_id"] = case_id
            return self._commit_cases(state, "Select analysis case", case_id, expected_revision)

    def validate_analysis_case(self, case_id=None):
        with self._lock:
            case = self.analysis_case(case_id)
            self._require_expanded_instances()
            stale = self._relations_resource().snapshot()["stale_targets"]
            if stale:
                raise PrepError("stale_mesh_targets", "Reconnect the explicit targets of the replaced mesh before case export.", {"targets": stale})
            self._validate_case_refs(case)
            # The activation scope is deliberately closed. Unknown physics or
            # sensor/activation cards must never silently survive as active.
            neutral_roots = {"BEGIN", "END", "NODE", "BEAM", "TRUSS", "SHELL", "SH3N", "TETRA4", "BRICK", "PART", "FUNCT", "UNIT"}
            neutral_pairs = {("MAT", "LAW1"), ("MAT", "ELAST"), ("MAT", "LAW36"), ("MAT", "PLAS_TAB"),
                ("PROP", "BEAM"), ("PROP", "TYPE3"), ("PROP", "TRUSS"), ("PROP", "TYPE2"), ("SKEW", "FIX"), ("PROP", "SHELL"), ("PROP", "TYPE1"), ("PROP", "SOLID"), ("PROP", "TYPE14"),
                ("GRNOD", "NODE"), ("GRSH3N", "SH3N"), ("GRSHEL", "SHEL"), ("GRBRIC", "BRIC"), ("GRBEAM", "BEAM"), ("GRTRUS", "TRUS"), ("SURF", "PART")}
            unsupported = []
            conditions = []
            for item in self.list_cards():
                words = item["keyword"].upper().strip("/").split("/")
                if condition_kind(item["keyword"]): conditions.append(item["id"])
                elif words[0] not in neutral_roots and tuple(words[:2]) not in neutral_pairs:
                    unsupported.append(item)
            if unsupported:
                raise PrepError("case_activation_scope_unknown", "Case export cannot prove the activation semantics of these native cards; source text is retained.", {"cards": unsupported})
            for card_id in case["condition_ids"]:
                self._unique_card(card_id)
                values = self.condition_values(card_id)
                if values.get("diagnostics"):
                    raise PrepError("invalid_reference", "An active condition has unresolved native targets.", {"card_id": card_id, "diagnostics": values["diagnostics"]})
                for key in ("group_id", "secondary_group_id"):
                    if key in values: self._group_reference(values[key])
                if "curve_id" in values: self._curve_reference(values["curve_id"])
                if "main_surface_id" in values: self._surface_reference(values["main_surface_id"])
            units = self._solver_work_units()
            factor = TIME_SECONDS[case["time_unit"]] / TIME_SECONDS[units["time"]]
            times = {key: case[key] * factor for key in ("end_time", "output_interval")}
            if any(not math.isfinite(value) or value <= 0 for value in times.values()):
                raise PrepError("invalid_analysis_case", "Case times cannot be represented in the solver working unit.")
            return {"case": case, "units": units, **times,
                    "inactive_condition_ids": [item for item in conditions if item not in case["condition_ids"]]}

    def export_analysis_case(self, path, case_id=None, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            checked = self.validate_analysis_case(case_id)
            result = self.export_solver_inputs(path, checked["end_time"], checked["output_interval"],
                                              _inactive_condition_ids=checked["inactive_condition_ids"])
            return {**result, "analysis_case": checked["case"], "inactive_condition_ids": checked["inactive_condition_ids"]}
