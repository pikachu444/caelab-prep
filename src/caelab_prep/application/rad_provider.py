"""RAD-specific interpretation of the solver-neutral editor contract.

The existing session owns raw cards, native validation, history and v1 files.
This adapter only describes supported values and translates editor commands.
"""

from __future__ import annotations

from .contracts import ObjectRef, PropertySpec, SetProperties, TreeNode
from ..cae_core.errors import PrepError


_LABELS = {
    "density": "Density", "young_modulus": "Young's modulus",
    "poisson_ratio": "Poisson's ratio", "friction": "Friction coefficient",
    "thickness": "Shell thickness", "tx": "Translation X fixed", "ty": "Translation Y fixed",
    "tz": "Translation Z fixed", "rx": "Rotation X fixed", "ry": "Rotation Y fixed", "rz": "Rotation Z fixed",
}


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
                              "material" if card.get("category") == "Materials" else "card",
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
        fields = {}
        for name, value in command.values.items():
            spec = specs[name]
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
