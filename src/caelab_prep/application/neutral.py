"""Editable material/curve document; independent of any native solver format."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4
import zipfile

from ..cae_core import CommandDispatcher, Document, PrepError
from .contracts import ObjectRef, PropertySpec, SetProperties, TreeNode
from .storage import read_container, write_container


def finite(value):
    try:
        if isinstance(value, bool):
            raise ValueError()
        number = float(value)
        if not math.isfinite(number):
            raise ValueError()
        return number
    except (TypeError, ValueError, OverflowError):
        raise PrepError("invalid_value", "A finite number is required.") from None


def validate_points(points):
    if not isinstance(points, (list, tuple)) or not points:
        raise PrepError("invalid_value", "A curve needs at least one point.")
    result = []
    for row in points:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise PrepError("invalid_value", "Each curve point needs X and Y.")
        result.append([finite(row[0]), finite(row[1])])
    if any(right[0] <= left[0] for left, right in zip(result, result[1:])):
        raise PrepError("invalid_value", "Curve X coordinates must increase strictly.")
    return result


class MaterialCurveResource:
    kind = "material-curves"

    def __init__(self, state, resource_id=None):
        self.id = resource_id or str(uuid4())
        self.restore(state)

    def snapshot(self):
        return deepcopy(self._state)

    def restore(self, state):
        if not isinstance(state, dict) or set(state) != {"material", "curves"}:
            raise PrepError("invalid_project", "Invalid material/curve payload.")
        material = state["material"]
        required = {"name", "density", "young_modulus", "poisson_ratio", "direction"}
        if not isinstance(material, dict) or not required <= material.keys() or set(material) - required - {"reference_curve"}:
            raise PrepError("invalid_project", "Invalid material fields.")
        if not isinstance(material["name"], str) or not material["name"].strip():
            raise PrepError("invalid_value", "A material name is required.")
        density, modulus, poisson = (finite(material[key]) for key in ("density", "young_modulus", "poisson_ratio"))
        if density <= 0 or modulus <= 0 or not -1 < poisson < .5:
            raise PrepError("invalid_value", "Density and modulus must be positive; -1 < Poisson ratio < 0.5.")
        direction = material["direction"]
        if not isinstance(direction, (tuple, list)) or len(direction) != 3:
            raise PrepError("invalid_value", "A vector needs three components.")
        direction = [finite(value) for value in direction]
        curves = state["curves"]
        if not isinstance(curves, dict) or not curves:
            raise PrepError("invalid_project", "A curve document needs curves.")
        validated = {}
        for key, curve in curves.items():
            if not isinstance(key, str) or not isinstance(curve, dict) or set(curve) != {"name", "points", "x_unit", "y_unit"}:
                raise PrepError("invalid_project", "Invalid curve fields.")
            if not all(isinstance(curve[field], str) for field in ("name", "x_unit", "y_unit")) or not curve["name"].strip():
                raise PrepError("invalid_project", "Invalid curve metadata.")
            validated[key] = {**curve, "points": validate_points(curve["points"])}
        reference = material.get("reference_curve")
        if reference is not None and (not isinstance(reference, str) or reference not in validated):
            raise PrepError("invalid_reference", "The material's associated curve does not exist.")
        self._state = {"material": {**material, "density": density, "young_modulus": modulus,
                                   "poisson_ratio": poisson, "direction": direction,
                                   "reference_curve": reference}, "curves": validated}

    def state_token(self):
        return hashlib.sha256(json.dumps(self._state, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class MaterialCurveCodec:
    format = "caelab-material-curves"
    version = 2

    @classmethod
    def encode(cls, document):
        resource = next(iter(document.resources.values()))
        manifest = {"format": cls.format, "version": cls.version, "document_id": document.id,
                    "revision": document.revision, "name": document.name, "resource_id": resource.id}
        return manifest, {"material-curves.json": json.dumps(resource.snapshot(), ensure_ascii=False, allow_nan=False).encode()}

    @classmethod
    def decode(cls, manifest, members):
        if manifest.get("format") != cls.format or type(manifest.get("version")) is not int or manifest["version"] not in (1, cls.version):
            raise PrepError("project_version", "Unsupported material/curve document version.")
        for key in ("document_id", "resource_id"):
            if not isinstance(manifest[key], str):
                raise ValueError("invalid document identifier")
            UUID(manifest[key])
        if type(manifest["revision"]) is not int or manifest["revision"] < 0 or not isinstance(manifest["name"], str):
            raise ValueError("invalid document metadata")
        if set(members) != {"material-curves.json"}:
            raise ValueError("unexpected document payload")
        resource = MaterialCurveResource(json.loads(members["material-curves.json"]), manifest["resource_id"])
        document = Document(manifest["name"], id=manifest["document_id"], revision=manifest["revision"])
        document.resources[resource.id] = resource
        return document


class CurveSession:
    """A small real document host, also exercised by the component gallery."""

    def __init__(self, state=None):
        self._lock = RLock()
        self._listeners = []
        if state is None:
            state = {
            "material": {"name": "구조용 강재 — 긴 한글 재료 이름", "density": 7850,
                         "young_modulus": 210000, "poisson_ratio": .3, "direction": [1, 0, 0]},
            "curves": {
                "plastic": {"name": "Plastic response", "x_unit": "1", "y_unit": "MPa",
                            "points": [[0, 250], [.02, 310], [.08, 390], [.18, 450]]},
                "load": {"name": "Loading history", "x_unit": "s", "y_unit": "N",
                         "points": [[0, 0], [.1, 2000], [.4, 5000], [1, 0]]}}}
        resource = MaterialCurveResource(state)
        document = Document("Material and curves")
        document.resources[resource.id] = resource
        document.mark_saved()
        self._install(document)

    def _install(self, document):
        if hasattr(self, "document") and self.document.id == document.id:
            document.revision = max(document.revision, self.document.revision + 1)
        self.document = document
        self._document_epoch = str(uuid4())
        self.dispatcher = CommandDispatcher(document)
        self.dispatcher.subscribe(lambda change: self._notify(change.kind, change=change.to_dict()))
        self._selected = None

    @property
    def resource(self):
        return next(iter(self.document.resources.values()))

    def _notify(self, kind, **details):
        event = {"kind": kind, "document_id": self.document.id, "revision": self.document.revision,
                 "document_epoch": self._document_epoch, **details}
        for listener in tuple(self._listeners):
            try:
                listener(dict(event))
            except Exception:
                continue

    def subscribe(self, listener):
        with self._lock:
            self._listeners.append(listener)
        def unsubscribe():
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)
        return unsubscribe

    def describe(self):
        with self._lock:
            return {"document_id": self.document.id, "revision": self.document.revision,
                    "name": self.document.name, "dirty": self.document.dirty,
                    "project_path": self.document.save_state.path,
                    "can_undo": self.dispatcher.can_undo, "can_redo": self.dispatcher.can_redo,
                    "active_object": asdict(self._selected) if self._selected else None,
                    "document_epoch": self._document_epoch,
                    "capabilities": {"undo": True, "save": True, "curve_edit": True, "solver_execution": False}}

    def tree_nodes(self):
        with self._lock:
            state = self.resource.snapshot()
            def ref(key, kind):
                return ObjectRef(self.document.id, self.resource.id, key, kind)
            return [TreeNode(ref("material", "material"), state["material"]["name"], "Materials", "material")] + [
                TreeNode(ref(key, "curve"), curve["name"], "Curves", "curve") for key, curve in state["curves"].items()]

    def _validate_target(self, target):
        if not isinstance(target, ObjectRef) or target.document_id != self.document.id:
            raise PrepError("document_conflict", "The target document has been replaced.")
        if target.resource_id != self.resource.id or target not in [node.ref for node in self.tree_nodes()]:
            raise PrepError("invalid_reference", "The target object does not exist.")

    def properties(self, target):
        with self._lock:
            self._validate_target(target)
            state = self.resource.snapshot()
            if target.kind == "curve":
                curve = state["curves"][target.object_id]
                return [PropertySpec("name", "Name", curve["name"], kind="text"),
                        PropertySpec("points", "Curve points", curve["points"], kind="table", group="Curve",
                                     unit=curve["y_unit"], components=(curve["x_unit"], curve["y_unit"]))]
            material = state["material"]
            candidates = tuple(node for node in self.tree_nodes() if node.ref.kind == "curve")
            selected = next((node.ref for node in candidates if node.ref.object_id == material["reference_curve"]), None)
            return [PropertySpec("name", "Name", material["name"], kind="text"),
                    PropertySpec("density", "Density", material["density"], unit="kg/m³", unit_choices=("kg/m³", "g/cm³"), group="Elastic material", minimum=0,
                                 unit_scales=(("kg/m³", 1), ("g/cm³", 1000))),
                    PropertySpec("young_modulus", "Young's modulus", material["young_modulus"], unit="MPa", unit_choices=("MPa", "GPa"), group="Elastic material", minimum=0,
                                 unit_scales=(("MPa", 1), ("GPa", 1000))),
                    PropertySpec("poisson_ratio", "Poisson's ratio", material["poisson_ratio"], unit="1", group="Elastic material", minimum=-1, maximum=.5),
                    PropertySpec("direction", "Material direction", material["direction"], kind="vector", unit="1", components=("X", "Y", "Z"), group="Orientation"),
                    PropertySpec("reference_curve", "Associated curve", selected, kind="reference",
                                 group="Reference (not a constitutive law)", choices=(None,) + tuple(node.ref for node in candidates),
                                 choice_labels=("No curve",) + tuple(node.label for node in candidates))]

    def submit(self, command):
        with self._lock:
            if not isinstance(command, SetProperties):
                raise PrepError("invalid_command", "A SetProperties command is required.")
            self._validate_target(command.target)
            if type(command.expected_revision) is not int or command.expected_revision != self.document.revision:
                raise PrepError("revision_conflict", "The document changed. Reload current values.")
            if not isinstance(command.values, dict) or not command.values or not isinstance(command.units, dict):
                raise PrepError("invalid_command", "A nonempty value mapping is required.")
            specs = {spec.name: spec for spec in self.properties(command.target)}
            if set(command.values) - specs.keys() or set(command.units) - command.values.keys():
                raise PrepError("field_not_writable", "Unknown field or unit target.")
            state = self.resource.snapshot()
            values = state["material"] if command.target.kind == "material" else state["curves"][command.target.object_id]
            for name, value in command.values.items():
                spec = specs[name]
                unit = command.units.get(name, spec.unit)
                allowed = spec.unit_choices or (spec.unit,)
                if unit not in allowed:
                    raise PrepError("invalid_unit", "The unit does not match this field.", {"field": name, "unit": unit})
                if spec.kind == "number":
                    value = finite(value)
                    if unit == "GPa": value *= 1000
                    if unit == "g/cm³": value *= 1000
                elif spec.kind == "reference":
                    if value is not None:
                        self._validate_target(value)
                        if value.kind != "curve":
                            raise PrepError("invalid_reference", "Select an existing curve.")
                        value = value.object_id
                values[name] = deepcopy(value)
            # Validate before Dispatcher receives a state; no partial edits escape.
            candidate = MaterialCurveResource(state, self.resource.id).snapshot()
            self.dispatcher.execute(self.resource.id, candidate, "Edit " + ", ".join(command.values),
                                    object_ids=(command.target.object_id,), expected_revision=command.expected_revision)
            return self.describe()

    def curve_points(self, target):
        with self._lock:
            self._validate_target(target)
            if target.kind != "curve":
                raise PrepError("invalid_reference", "Select a curve.")
            return self.resource.snapshot()["curves"][target.object_id]["points"]

    def set_curve_points(self, target, points, expected_revision):
        return self.submit(SetProperties(target, {"points": points}, expected_revision))

    def select(self, target):
        with self._lock:
            if target is not None:
                self._validate_target(target)
            self._selected = target
            self._notify("selection")
            return target

    def selection(self):
        return self._selected

    def active_object(self):
        with self._lock:
            return self._selected

    def undo(self):
        with self._lock:
            self.dispatcher.undo()
            return self.describe()

    def redo(self):
        with self._lock:
            self.dispatcher.redo()
            return self.describe()

    def save_project(self, path):
        with self._lock:
            target = Path(path).expanduser().resolve()
            manifest, members = MaterialCurveCodec.encode(self.document)
            try:
                write_container(target, manifest, members)
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                raise PrepError("project_write_error", "Could not save the material/curve document.", {"reason": str(exc)}) from exc
            self.document.mark_saved(str(target))
            self._notify("save")
            return {**self.describe(), "saved_path": str(target)}

    def open_project(self, path):
        with self._lock:
            source = Path(path).expanduser().resolve()
            try:
                manifest, members = read_container(source)
                document = MaterialCurveCodec.decode(manifest, members)
            except PrepError:
                raise
            except (OSError, ValueError, KeyError, TypeError, UnicodeError, zipfile.BadZipFile) as exc:
                raise PrepError("invalid_project", "Could not open the material/curve document.", {"reason": str(exc)}) from exc
            document.mark_saved(str(source))
            self._install(document)
            self._notify("document")
            return self.describe()
