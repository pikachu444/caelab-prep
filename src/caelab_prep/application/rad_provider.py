"""RAD-specific interpretation of the solver-neutral editor contract.

The existing session owns raw cards, native validation, history and v1 files.
This adapter only describes supported values and translates editor commands.
"""

from __future__ import annotations

from .contracts import ObjectRef, OperationRequest, OperationSpec, PropertySpec, SetProperties, TreeNode
from ..cae_core.errors import PrepError


_LABELS = {
    "density": "Density", "young_modulus": "Young's modulus",
    "poisson_ratio": "Poisson's ratio", "friction": "Friction coefficient",
    "thickness": "Shell thickness", "tx": "Translation X fixed", "ty": "Translation Y fixed",
    "tz": "Translation Z fixed", "rx": "Rotation X fixed", "ry": "Rotation Y fixed", "rz": "Rotation Z fixed",
}

_ICONS = {"Materials": "material", "Properties": "section", "Parts": "part", "Nodes": "select",
          "Elements": "mesh", "Constraints": "constraint", "Contacts": "contact", "Curves": "curve",
          "Groups": "set", "Loads": "load", "Initial conditions": "vector"}


class RadProvider:
    """Expose a PrepSession without making shared widgets understand RAD."""

    def __init__(self, session):
        self.session = session

    def describe(self):
        return self.session.describe()

    def ref_for_card(self, card):
        return ObjectRef(self.describe()["document_id"], card["resource_id"], card["id"],
                         "rad-card", native_scope=card["keyword"])

    def tree_nodes(self):
        if not self.describe().get("document_id"):
            return ()
        return tuple(TreeNode(self.ref_for_card(card), str(card.get("title") or card["keyword"]),
                              str(card.get("category") or "Other cards"),
                              _ICONS.get(card.get("category"), "card"),
                              f"{card['keyword']}\n{card['resource_name']}")
                     for card in self.session.list_cards())

    def _card(self, ref):
        if not isinstance(ref, ObjectRef) or ref.kind != "rad-card":
            raise PrepError("invalid_reference", "A RAD card reference is required.")
        if ref.document_id != self.describe().get("document_id"):
            raise PrepError("invalid_reference", "The card belongs to another document.")
        card = next((card for card in self.session.list_cards()
                     if card["id"] == ref.object_id and card["resource_id"] == ref.resource_id), None)
        if card is None or ref.native_scope != card["keyword"] or ref.mesh_revision is not None:
            raise PrepError("invalid_reference", "The referenced RAD card is no longer available.")
        return card

    def properties(self, ref):
        card = self._card(ref)
        fields = self.session.card_fields(card["id"])
        values = {field["name"]: field["value"] for field in fields}
        context = self.unit_context(ref)
        words = card["keyword"].upper().split("/")
        if len(words) in (3, 4) and words[1] == "PART" and words[2].isdigit():
            summary = self.session.part_summary(ref)
            return (PropertySpec("part_id", "Native part ID", summary["part_id"], editable=False),
                    PropertySpec("element_count", "Displayed elements", summary["element_count"], editable=False),
                    *self._assignment_fields(card))
        if (card["keyword"].upper().startswith("/FUNCT/") and fields
                and set(values) == {f"point_{i}_{axis}" for i in range(len(fields) // 2) for axis in ("x", "y")}):
            points = tuple((values[f"point_{i}_x"], values[f"point_{i}_y"])
                           for i in range(len(fields) // 2))
            return (PropertySpec("points", "Existing curve points", points, kind="table",
                                 unit="input deck", components=("X", "Y"), unit_context=context),)
        if card["keyword"].upper().startswith("/INIVEL/TRA/") and all(n in values for n in ("vx", "vy", "vz")):
            return (PropertySpec("velocity", "Initial velocity", tuple(values[n] for n in ("vx", "vy", "vz")),
                                 kind="vector", unit="input deck", components=("X", "Y", "Z"),
                                 unit_context=context, coordinate_frame="native skew reference in card"),)
        return tuple(PropertySpec(field["name"], _LABELS.get(field["name"], field["label"]),
                                  field["value"], kind="bool" if field["type"] == "bool" else "number",
                                  unit="" if field["type"] == "bool" or field["name"] in ("poisson_ratio", "friction") else "input deck",
                                  editable=field.get("writable", True), minimum=field.get("minimum"),
                                  maximum=field.get("maximum"), unit_context=context) for field in fields)

    def unit_context(self, ref):
        """Native context is descriptive; it never implies a conversion rule."""
        card = self._card(ref)
        context = card.get("units", {})
        return {**context, "global": dict(context["global"]) if context.get("global") else None}

    def submit(self, command):
        if not isinstance(command, SetProperties):
            raise PrepError("invalid_command", "A SetProperties command is required.")
        if type(command.expected_revision) is not int:
            raise PrepError("revision_conflict", "An integer document revision is required.")
        self._card(command.target)
        specs = {spec.name: spec for spec in self.properties(command.target)}
        if not isinstance(command.values, dict) or not command.values:
            raise PrepError("invalid_value", "At least one supported property is required.")
        if not isinstance(command.units, dict):
            raise PrepError("invalid_unit", "Property units must be a mapping.")
        if set(command.values) - specs.keys() or set(command.units) - command.values.keys():
            raise PrepError("field_not_writable", "This RAD property is preserved read-only.")
        if set(command.values) <= {"material", "property"}:
            for name, unit in command.units.items():
                if unit != specs[name].unit:
                    raise PrepError("invalid_unit", "Object references do not have display units.")
            values = {name: command.values.get(name, specs[name].value)
                      for name in ("material", "property")}
            return self.execute_operation(OperationRequest(
                "part.assign", values, command.target.document_id,
                command.expected_revision, command.target))
        fields = {}
        for name, value in command.values.items():
            spec = specs[name]
            if not spec.editable:
                raise PrepError("field_not_writable", "This property is read-only.")
            if name in command.units and command.units[name] != spec.unit:
                raise PrepError("invalid_unit", "RAD values retain the input deck units; conversion is unavailable.")
            if name == "velocity":
                if not isinstance(value, (tuple, list)) or len(value) != 3:
                    raise PrepError("invalid_value", "Initial velocity requires X, Y and Z values.")
                fields.update(zip(("vx", "vy", "vz"), value))
            elif name == "points":
                if not isinstance(value, (tuple, list)) or len(value) != len(spec.value):
                    raise PrepError("invalid_value", "Only the existing FUNCT rows can be edited.")
                for i, point in enumerate(value):
                    if not isinstance(point, (tuple, list)) or len(point) != 2:
                        raise PrepError("invalid_value", "Each curve row requires X and Y values.")
                    fields.update({f"point_{i}_x": point[0], f"point_{i}_y": point[1]})
            else:
                fields[name] = value
        return self.session.set_fields(command.target.object_id, fields,
                                       expected_revision=command.expected_revision,
                                       expected_document_id=command.target.document_id,
                                       expected_resource_id=command.target.resource_id)

    @staticmethod
    def _creatable_card(card):
        words = card["keyword"].upper().split("/")
        return (len(words) >= 4 and
                ((words[1] == "MAT" and words[2] in ("LAW1", "ELAST")) or
                 (words[1] == "PROP" and words[2] in ("SHELL", "TYPE1"))))

    def available_operations(self, target=None):
        if not self.describe().get("document_id"):
            return ()
        keys = ["material.create", "section.create"]
        if target is not None:
            card = self._card(target)
            if self._creatable_card(card):
                keys.extend(("object.copy", "object.delete"))
            if card["category"] == "Parts":
                keys.append("part.assign")
        return tuple(keys)

    def _assignment_fields(self, part):
        assignments = self.session.part_assignments(part["id"])
        cards = self.session.list_cards()
        fields = []
        for name, label, category in (("material", "Material", "Materials"),
                                      ("property", "Section", "Properties")):
            current_id = assignments.get(name + "_id")
            candidates = [card for card in cards if card["category"] == category]
            if name == "property":
                candidates = [card for card in candidates
                              if card["id"] == current_id or
                              (len(card["keyword"].split("/")) > 2 and
                               card["keyword"].upper().split("/")[2] in ("SHELL", "TYPE1"))]
            refs = tuple(self.ref_for_card(card) for card in candidates)
            current = next((ref for ref in refs if ref.object_id == current_id), None)
            fields.append(PropertySpec(
                name, label, current, kind="reference", group="Part assignment",
                choices=(None, *refs), choice_labels=("Select an object", *(
                    f"{card['title'] or card['keyword']}  [{card['keyword']}]" for card in candidates))))
        return tuple(fields)

    def operation_spec(self, key, target=None):
        with self.session._lock:
            if key not in self.available_operations(target):
                raise PrepError("operation_unavailable", "This operation is not available for the selected object.")
            state = self.describe()
            fields = ()
            title = ""
            description = "Values use the input deck's unit system. No automatic unit conversion is applied."
            if key in ("material.create", "section.create"):
                title = "Create material" if key == "material.create" else "Create shell section"
                fields = (PropertySpec("name", "Name", "New material" if key == "material.create" else "New section", kind="text"),
                          PropertySpec("native_id", "ID (0 = automatic)", 0, kind="integer", minimum=0))
                if key == "material.create":
                    fields += (PropertySpec("density", "Density", 0.0, unit="input deck", minimum=0),
                               PropertySpec("young_modulus", "Young's modulus", 0.0, unit="input deck", minimum=0),
                               PropertySpec("poisson_ratio", "Poisson's ratio", 0.3, minimum=-1, maximum=0.5))
                else:
                    fields += (PropertySpec("thickness", "Shell thickness", 0.0, unit="input deck", minimum=0),)
            elif key == "object.copy":
                card = self._card(target)
                title = "Duplicate object"
                fields = (PropertySpec("name", "Name", (card["title"] or card["keyword"]) + " copy", kind="text"),)
                description = "Create an independent object with a new native ID. Existing part assignments remain unchanged."
            elif key == "object.delete":
                card = self._card(target)
                title = "Delete object"
                dependents = self.session.card_dependents(card["id"])
                description = f"Delete {card['title'] or card['keyword']}. "
                if dependents:
                    description += "Referenced by: " + ", ".join(item["keyword"] for item in dependents) + ". Reassign these objects first."
                else:
                    description += "The command checks references before changing the model. Undo restores the object."
            elif key == "part.assign":
                card = self._card(target)
                title = "Assign material and shell section"
                fields = self._assignment_fields(card)
                description = f"Apply both references to {card['title'] or card['keyword']} in one Undo step."
            return OperationSpec(key, title, fields, state["document_id"], state["revision"],
                                 target, key == "object.delete", description)

    def execute_operation(self, request):
        if not isinstance(request, OperationRequest) or not isinstance(request.values, dict):
            raise PrepError("invalid_command", "An OperationRequest with named values is required.")
        with self.session._lock:
            state = self.describe()
            if not isinstance(request.document_id, str) or request.document_id != state.get("document_id"):
                raise PrepError("document_conflict", "The target document has been replaced.")
            if type(request.expected_revision) is not int or request.expected_revision != state["revision"]:
                raise PrepError("revision_conflict", "The model changed. Cancel this draft and read the current values.")
            spec = self.operation_spec(request.key, request.target)
            if set(request.values) != {field.name for field in spec.fields}:
                raise PrepError("invalid_value", "Supply exactly the fields in the operation form.")
            values = dict(request.values)
            expected = {"expected_revision": request.expected_revision,
                        "expected_document_id": request.document_id}
            if request.key in ("material.create", "section.create"):
                native_id = values.pop("native_id")
                if type(native_id) is not int or native_id < 0:
                    raise PrepError("invalid_value", "The native ID must be a nonnegative integer.", {"field": "native_id"})
                method = self.session.create_material if request.key == "material.create" else self.session.create_shell_property
                result = method(**values, native_id=native_id or None, **expected)
            elif request.key == "object.copy":
                result = self.session.copy_card(request.target.object_id, **values, **expected)
            elif request.key == "object.delete":
                result = self.session.delete_card(request.target.object_id, **expected)
            else:
                for name, category in (("material", "Materials"), ("property", "Properties")):
                    card = self._card(values[name])
                    if card["category"] != category:
                        raise PrepError("invalid_reference", f"Choose a {name} object.", {"field": name})
                result = self.session.assign_part(request.target.object_id,
                    material_id=values["material"].object_id,
                    property_id=values["property"].object_id, **expected)
            object_id = result.get("card_id")
            if object_id is None and request.key == "part.assign":
                object_id = request.target.object_id
            card = next((item for item in self.session.list_cards() if item["id"] == object_id), None)
            return {**result, "object": self.ref_for_card(card) if card else None}

    def undo(self):
        return self.session.undo()

    def redo(self):
        return self.session.redo()

    def save_project(self, path):
        return self.session.save_project(path)

    def open_project(self, path):
        return self.session.open_project(path)

    def subscribe(self, listener):
        return self.session.subscribe(listener)

    def select(self, target):
        return self.session.activate_object(target)

    def select_many(self, targets, active=None):
        return self.session.select_objects(targets, active=active)

    def active_object(self):
        return self.session.active_object()
