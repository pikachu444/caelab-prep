"""RAD-specific interpretation of the solver-neutral editor contract.

The existing session owns raw cards, native validation, history and v1 files.
This adapter only describes supported values and translates editor commands.
"""

from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import math
import re

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

CREATE_OPERATIONS = {
    "material.create": ("Create material", "create_material"),
    "section.create": ("Create shell section", "create_shell_property"),
    "solid_section.create": ("Create solid section", "create_solid_property"),
    "coordinate_system.create": ("Create fixed coordinate system", "create_coordinate_system"),
    "curve.create": ("Create load curve", "create_curve"),
    "group.create": ("Create node group", "create_node_group"),
    "element_group.create": ("Create element group", "create_element_group"),
    "surface.create": ("Create shell surface", "create_surface"),
    "constraint.create": ("Create boundary condition", "create_boundary_condition"),
    "load.create": ("Create per-node load", "create_load"),
    "velocity.create": ("Create initial velocity", "create_initial_velocity"),
    "contact.create": ("Create TYPE7 contact", "create_contact"),
}
MODEL_OPERATIONS = (*CREATE_OPERATIONS, "object.edit", "object.copy", "object.delete", "part.assign")

_GENERATED_ENTITY = re.compile(
    r"(?:(?P<label>.+): )?caelab:(?P<kind>surface|volume):"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def display_title(title):
    """Hide the producer's exact validation suffix only in display projections."""
    match = _GENERATED_ENTITY.fullmatch(str(title))
    return (match.group("label") or f"CAD {match.group('kind').lower()}") if match else str(title)


class RadProvider:
    """Expose a PrepSession without making shared widgets understand RAD."""

    def __init__(self, session):
        self.session = session
        self._part_properties_cache = None

    def describe(self):
        return self.session.describe()

    def ref_for_card(self, card):
        return ObjectRef(self.describe()["document_id"], card["resource_id"], card["id"],
                         "rad-card", native_scope=card["keyword"])

    def tree_nodes(self):
        if not self.describe().get("document_id"):
            return ()
        return tuple(TreeNode(self.ref_for_card(card), display_title(card.get("title") or card["keyword"]),
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

    def properties(self, ref, draft_values=None):
        # A PART inspector and both action surfaces query identical assignments
        # during one refresh. Cache only this small immutable-value contract, not
        # group memberships or draft-dependent condition/unit specifications.
        with self.session._lock:
            document = self.session._require()
            stamp = (self.session._document_epoch, document.id, document.revision, ref)
            if self._part_properties_cache and self._part_properties_cache[0] == stamp:
                return tuple(replace(spec, unit_context=deepcopy(spec.unit_context))
                             for spec in self._part_properties_cache[1])
            specs = self._draft_specs(self._native_properties(ref), draft_values)
            context = self.unit_context(ref)
            words = self._card(ref)["keyword"].upper().split("/")
            result = self._display_specs(specs, context, words)
            if len(words) in (3, 4) and words[1] == "PART" and words[2].isdigit():
                self._part_properties_cache = (stamp, tuple(replace(spec, unit_context=deepcopy(spec.unit_context)) for spec in result))
            else:
                self._part_properties_cache = None
            return result

    @staticmethod
    def _draft_specs(specs, draft_values):
        # Only an explicitly supported discriminator changes a field contract.
        # Numeric values stay native so querying a draft cannot reinterpret them.
        if isinstance(draft_values, dict) and "direction" in draft_values:
            return tuple(replace(spec, value=draft_values["direction"]) if spec.name == "direction" else spec
                         for spec in specs)
        return specs

    @staticmethod
    def _display_specs(specs, context, words):
        if words[1] == "CLOAD":
            direction = next((spec.value for spec in specs if spec.name == "direction"), None)
            quantity = "force" if direction in ("X", "Y", "Z") else "moment" if direction in ("XX", "YY", "ZZ") else None
            specs = tuple(replace(spec, unit_context={**spec.unit_context, "quantity": quantity})
                          if spec.name == "scale" else spec for spec in specs)
        units = context.get("global")
        override_index = 4 if words[1] in ("MAT", "PROP", "INIVEL", "INTER") else 3 if words[1] == "CLOAD" else None
        override = override_index is not None and len(words) > override_index
        if not units or override:
            reason = "Per-card unit override is preserved; display conversion is unavailable." if override else "The input unit system is not declared."
            return tuple(replace(spec, unit_context={**spec.unit_context, "display_conversion": "unavailable", "reason": reason}) for spec in specs)
        scales = {"mass": {"Mg": 1000., "kg": 1., "g": .001},
                  "length": {"m": 1., "cm": .01, "mm": .001},
                  "time": {"s": 1., "ms": .001, "mus": 1e-6}}
        if any(units.get(key) not in values for key, values in scales.items()):
            return tuple(replace(spec, unit_context={**spec.unit_context, "display_conversion": "unavailable", "reason": "Input unit symbols are not supported for conversion."}) for spec in specs)
        mass, length, time = (scales[key][units[key]] for key in ("mass", "length", "time"))
        m, l, t = (units[key] for key in ("mass", "length", "time"))
        dimensions = {
            "density": (mass / length**3, f"{m}/{l}³", {"kg/m³": 1., "g/cm³": 1000., "Mg/mm³": 1e12}),
            "young_modulus": (mass / (length*time**2), f"{m}/({l}·{t}²)", {"Pa": 1., "MPa": 1e6, "GPa": 1e9}),
            "thickness": (length, l, {"mm": .001, "cm": .01, "m": 1.}),
            "velocity": (length/time, f"{l}/{t}", {"mm/s": .001, "m/s": 1., "mm/ms": 1.}),
        }
        if words[1] == "CLOAD":
            direction = next((spec.value for spec in specs if spec.name == "direction"), None)
            if direction in ("X", "Y", "Z"):
                dimensions["scale"] = (mass*length/time**2, f"{m}·{l}/{t}²", {"N": 1., "kN": 1000.})
            elif direction in ("XX", "YY", "ZZ"):
                dimensions["scale"] = (mass*length**2/time**2, f"{m}·{l}²/{t}²", {"N·mm": .001, "N·m": 1.})
        result = []
        for spec in specs:
            if spec.name not in dimensions:
                if spec.name == "points":
                    spec = replace(spec, unit_context={**spec.unit_context, "display_conversion": "unavailable", "reason": "FUNCT axes have no declared physical dimension; values remain in the input deck basis."})
                result.append(spec); continue
            native_si, native_label, choices_si = dimensions[spec.name]
            # Prefer a familiar equivalent unit, keeping the native numeric value.
            native_label = next((label for label, factor in choices_si.items() if math.isclose(factor, native_si, rel_tol=1e-12)), native_label)
            conversion = {native_label: 1.}
            conversion.update({label: float(format(factor/native_si, ".15g")) for label, factor in choices_si.items()})
            result.append(replace(spec, unit=native_label, unit_choices=tuple(conversion), unit_scales=tuple(conversion.items()),
                                  unit_context={**spec.unit_context, **context, "display_conversion": "available", "native_unit": native_label}))
        return tuple(result)

    def _native_properties(self, ref):
        card = self._card(ref)
        fields = self.session.card_fields(card["id"])
        values = {field["name"]: field["value"] for field in fields}
        context = self.unit_context(ref)
        words = card["keyword"].upper().split("/")
        if tuple(words[1:3]) == ("SKEW", "FIX"):
            values = self.session.coordinate_system_values(card["id"])
            return self._coordinate_fields(values)
        if self._group_kind(card) and callable(getattr(self.session, "group_members", None)):
            membership = self.session.group_members(card["id"])
            status = (PropertySpec("relationship_status", "Target relationship", "; ".join(item["message"] for item in membership["diagnostics"]),
                                   kind="text", editable=False),) if membership["diagnostics"] else ()
            if membership["kind"] == "node":
                return (PropertySpec("node_ids", "Native node IDs", tuple(membership["member_ids"]), kind="integer_list"), *status)
            return (self._element_members_field(membership["members"]), *status)
        if len(words) in (3, 4) and words[1] == "PART" and words[2].isdigit():
            summary = self.session.part_summary(ref)
            return (PropertySpec("part_id", "Native part ID", summary["part_id"], editable=False),
                    PropertySpec("element_count", "Displayed elements", summary["element_count"], editable=False),
                    *self._assignment_fields(card))
        if (card["keyword"].upper().startswith("/FUNCT/") and fields
                and set(values) == {f"point_{i}_{axis}" for i in range(len(fields) // 2) for axis in ("x", "y")}):
            points = tuple((values[f"point_{i}_x"], values[f"point_{i}_y"])
                           for i in range(len(fields) // 2))
            return (PropertySpec("points", "Curve points", points, kind="table",
                                 unit="input deck", components=("X", "Y"), unit_context=context, minimum_rows=2),)
        if self._condition_kind(card):
            fields = tuple(replace(field, unit_context=context,
                                 coordinate_frame="native skew reference in card" if field.name == "velocity" else field.coordinate_frame)
                         for field in self._condition_fields(self._condition_kind(card), self.session.condition_values(card["id"])))
            try:
                support = self.session.condition_support(card["id"])
                status = support["status"]
                if support.get("diagnostics"):
                    status += ": " + ", ".join(sorted({item.get("code", "field applicability unknown") for item in support["diagnostics"]}))
            except PrepError as exc: status = exc.message
            return (*fields, PropertySpec("component_support", "Target mechanical fields", status, kind="text", editable=False))
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
        units = context.get("global") or self.session._model_resource(None).unit_context().get("global")
        return {**context, "global": dict(units) if units else None}

    def submit(self, command):
        if not isinstance(command, SetProperties):
            raise PrepError("invalid_command", "A SetProperties command is required.")
        if type(command.expected_revision) is not int:
            raise PrepError("revision_conflict", "An integer document revision is required.")
        self._card(command.target)
        specs = {spec.name: spec for spec in self.properties(command.target, command.values)}
        if not isinstance(command.values, dict) or not command.values:
            raise PrepError("invalid_value", "At least one supported property is required.")
        if not isinstance(command.units, dict):
            raise PrepError("invalid_unit", "Property units must be a mapping.")
        if set(command.values) - specs.keys() or set(command.units) - command.values.keys():
            raise PrepError("field_not_writable", "This RAD property is preserved read-only.")
        converted = self._native_values(specs, command.values, command.units)
        command = replace(command, values=converted, units={name: specs[name].unit for name in command.units})
        if set(command.values) <= {"material", "property"}:
            for name, unit in command.units.items():
                if unit != specs[name].unit:
                    raise PrepError("invalid_unit", "Object references do not have display units.")
            values = {name: command.values.get(name, specs[name].value)
                      for name in ("material", "property")}
            return self.execute_operation(OperationRequest(
                "part.assign", values, command.target.document_id,
                command.expected_revision, command.target))
        for name in command.values:
            if not specs[name].editable:
                raise PrepError("field_not_writable", "This property is read-only.")
        expected = {"expected_revision": command.expected_revision,
                    "expected_document_id": command.target.document_id}
        if set(command.values) == {"points"}:
            return self.session.set_curve_points(command.target.object_id, command.values["points"], **expected)
        if self._group_kind(self._card(command.target)):
            key = "node_ids" if self._group_kind(self._card(command.target)) == "node" else "element_refs"
            return self.session.set_group_members(command.target.object_id, command.values[key], **expected)
        if self._card(command.target)["keyword"].upper().startswith("/SKEW/FIX/"):
            return self.session.set_coordinate_system_values(command.target.object_id, command.values, **expected)
        if self._condition_kind(self._card(command.target)):
            values = dict(command.values)
            for name, value in values.items():
                if specs[name].kind == "reference":
                    values[name] = None if name == "coordinate_system_id" and value is None else self._card(value)["id"]
            return self.session.set_condition_values(command.target.object_id, values, **expected)
        fields = {}
        for name, value in command.values.items():
            if name == "velocity":
                if not isinstance(value, (tuple, list)) or len(value) != 3:
                    raise PrepError("invalid_value", "Initial velocity requires X, Y and Z values.")
                fields.update(zip(("vx", "vy", "vz"), value))
            else:
                fields[name] = value
        return self.session.set_fields(command.target.object_id, fields,
                                       expected_revision=command.expected_revision,
                                       expected_document_id=command.target.document_id,
                                       expected_resource_id=command.target.resource_id)

    @staticmethod
    def _native_values(specs, values, units):
        if not isinstance(units, dict) or set(units) - set(values):
            raise PrepError("invalid_unit", "Units must name submitted fields only.")
        converted = dict(values)
        for name, value in converted.items():
            spec = specs[name]
            unit = units.get(name, spec.unit)
            choices = dict(spec.unit_scales)
            if choices:
                if unit not in choices:
                    raise PrepError("invalid_unit", "This display unit does not match the field dimension.", {"field": name})
                def convert(item):
                    try:
                        if isinstance(item, bool): raise ValueError()
                        number = float(Decimal(str(item)) * Decimal(str(choices[unit])))
                        if not math.isfinite(number): raise ValueError()
                        return number
                    except (ValueError, TypeError, OverflowError, InvalidOperation):
                        raise PrepError("invalid_value", "Enter finite values before changing units or applying.", {"field": name}) from None
                if spec.kind == "vector":
                    if not isinstance(value, (tuple, list)) or len(value) != len(spec.components):
                        raise PrepError("invalid_value", "The vector has an invalid component count.", {"field": name})
                    numbers = tuple(convert(item) for item in value)
                    converted[name] = tuple(old if isinstance(old, (int, float)) and math.isclose(item, old, rel_tol=1e-14, abs_tol=0) else item
                                            for item, old in zip(numbers, spec.value))
                else:
                    number = convert(value)
                    converted[name] = spec.value if isinstance(spec.value, (int, float)) and math.isclose(number, spec.value, rel_tol=1e-14, abs_tol=0) else number
            elif unit != spec.unit:
                raise PrepError("invalid_unit", "This field has no verified display-unit conversion.", {"field": name})
        return converted

    @staticmethod
    def _creatable_card(card):
        words = card["keyword"].upper().split("/")
        return (len(words) >= 4 and
                ((words[1] == "MAT" and words[2] in ("LAW1", "ELAST", "LAW36", "PLAS_TAB")) or
                 (words[1] == "PROP" and words[2] in ("SHELL", "TYPE1", "SOLID", "TYPE14")) or
                 tuple(words[1:3]) in (("GRNOD", "NODE"), ("GRSH3N", "SH3N"), ("GRSHEL", "SHEL"), ("GRBRIC", "BRIC"), ("GRBEAM", "BEAM"), ("GRTRUS", "TRUS"),
                                      ("SURF", "PART"), ("INIVEL", "TRA"), ("INTER", "TYPE7")))) or (
                    len(words) >= 3 and words[1] in ("FUNCT", "BCS", "CLOAD") and words[2].isdigit())

    @staticmethod
    def _group_kind(card):
        words = card["keyword"].upper().split("/")
        family = tuple(words[1:3])
        return "node" if family == ("GRNOD", "NODE") else "element" if family in (
            ("GRSH3N", "SH3N"), ("GRSHEL", "SHEL"), ("GRBRIC", "BRIC"), ("GRBEAM", "BEAM"), ("GRTRUS", "TRUS")) else None

    def _element_members_field(self, value=None):
        cells = self.session.mesh_view()["cells"]
        refs = tuple({"resource_id": cell["resource_id"], "entity_kind": "element", "local_id": cell["id"]}
                     for cell in cells)
        if value is None:
            selection = self.session.selection()
            value = selection["refs"] if selection["kind"] == "element" else ()
        names = {card["resource_id"]: card["resource_name"] for card in self.session.list_cards()}
        return PropertySpec("element_refs", "Element members", tuple(value), kind="references", choices=refs,
            choice_labels=tuple(f"Element {cell['id']} · {names.get(cell['resource_id'], cell['resource_id'])} · {cell['type']}"
                                for cell in cells), unit_context={"reference_kind": "mesh-element"})

    @staticmethod
    def _condition_kind(card):
        words = card["keyword"].upper().split("/")
        if len(words) >= 3 and words[2].isdigit():
            return {"BCS": "constraint", "CLOAD": "load"}.get(words[1])
        if tuple(words[1:3]) == ("INIVEL", "TRA"):
            return "velocity"
        if tuple(words[1:3]) == ("INTER", "TYPE7"):
            return "contact"
        return None

    def _reference_field(self, name, label, prefixes, value=None, *, multiple=False):
        cards = [card for card in self.session.list_cards()
                 if any(card["keyword"].upper().startswith(prefix) for prefix in prefixes)]
        # Surface EXT/ALL are separate capabilities; this form selects plain shell surfaces.
        if name == "main_surface_id":
            cards = [card for card in cards if card["keyword"].split("/")[3].isdigit()]
        refs = tuple(self.ref_for_card(card) for card in cards)
        current = tuple(ref for ref in refs if ref.object_id in (value or ())) if multiple else next(
            (ref for ref in refs if ref.object_id == value), None)
        return PropertySpec(name, label, current, kind="references" if multiple else "reference",
                            choices=refs if multiple else (None, *refs), choice_labels=(
                                () if multiple else ("Select an object",)) + tuple(
                                f"{card['title'] or card['keyword']}  [{card['keyword']}]" for card in cards))

    def _condition_fields(self, kind, values=None):
        values = values or {}
        group = lambda name="group_id", label="Node group": self._reference_field(
            name, label, ("/GRNOD/NODE/",), values.get(name))
        frame = self._reference_field("coordinate_system_id", "Coordinate system", ("/SKEW/FIX/",), values.get("coordinate_system_id"))
        frame = replace(frame, choice_labels=("Global Cartesian", *frame.choice_labels[1:]))
        if kind == "constraint":
            return (group(), frame, *(PropertySpec(name, label, tuple(values.get(name, (False, False, False))),
                    kind="bool_vector", components=("X", "Y", "Z")) for name, label in
                    (("translations", "Fixed translations"), ("rotations", "Fixed rotations"))))
        if kind == "load":
            return (group(), frame, self._reference_field("curve_id", "Load curve", ("/FUNCT/",), values.get("curve_id")),
                    PropertySpec("direction", "Direction", values.get("direction", "Z"), kind="choice",
                                 choices=("X", "Y", "Z", "XX", "YY", "ZZ")),
                    PropertySpec("scale", "Load scale at each node", values.get("scale", 1.0), unit="input deck"))
        if kind == "velocity":
            return (PropertySpec("velocity", "Initial velocity", tuple(values.get("velocity", (0., 0., 0.))),
                                 kind="vector", unit="input deck", components=("X", "Y", "Z")), group(), frame)
        if kind == "contact":
            friction_label = "Friction function scale" if values.get("friction_is_scale", False) else "Friction coefficient"
            return (group("secondary_group_id", "Secondary node group"),
                    self._reference_field("main_surface_id", "Main shell surface", ("/SURF/PART/",), values.get("main_surface_id")),
                    PropertySpec("friction", friction_label, values.get("friction", 0.0), minimum=0))
        return ()

    @staticmethod
    def _coordinate_fields(values=None):
        values = values or {}
        return tuple(PropertySpec(name, label, tuple(values.get(name, default)), kind="vector", components=("X", "Y", "Z"),
                                  unit="input deck" if name == "origin" else "")
                     for name, label, default in (("origin", "Origin", (0.,0.,0.)), ("y_axis", "Local Y direction", (0.,1.,0.)),
                                                  ("z_axis", "Local Z direction", (0.,0.,1.))))

    def available_operations(self, target=None):
        if not self.describe().get("document_id"):
            return ()
        keys = [key for key, (_, method) in CREATE_OPERATIONS.items() if callable(getattr(self.session, method, None))]
        if target is not None:
            card = self._card(target)
            if self._creatable_card(card):
                keys.extend(("object.copy", "object.delete"))
            if any(field.editable for field in self.properties(target)):
                keys.append("object.edit")
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
                               card["keyword"].upper().split("/")[2] in ("SHELL", "TYPE1", "SOLID", "TYPE14", "BEAM", "TYPE3", "TRUSS", "TYPE2"))]
            else:
                candidates = [card for card in candidates if card["id"] == current_id or
                              card["keyword"].upper().split("/")[2] in ("LAW1", "ELAST", "LAW36", "PLAS_TAB")]
            refs = tuple(self.ref_for_card(card) for card in candidates)
            current = next((ref for ref in refs if ref.object_id == current_id), None)
            fields.append(PropertySpec(
                name, label, current, kind="reference", group="Part assignment",
                choices=(None, *refs), choice_labels=("Select an object", *(
                    f"{card['title'] or card['keyword']}  [{card['keyword']}]" for card in candidates))))
        return tuple(fields)

    def operation_spec(self, key, target=None, draft_values=None):
        with self.session._lock:
            if key not in self.available_operations(target):
                raise PrepError("operation_unavailable", "This operation is not available for the selected object.")
            state = self.describe()
            fields = ()
            title = ""
            description = "The input deck units remain unchanged. Verified display units are converted back when Apply commits."
            if key in CREATE_OPERATIONS:
                title = CREATE_OPERATIONS[key][0]
                fields = (PropertySpec("name", "Name", "New " + key.split(".")[0], kind="text"),
                          PropertySpec("native_id", "ID (0 = automatic)", 0, kind="integer", minimum=0))
                if key == "material.create":
                    fields += (PropertySpec("density", "Density", 0.0, unit="input deck", minimum=0),
                               PropertySpec("young_modulus", "Young's modulus", 0.0, unit="input deck", minimum=0),
                               PropertySpec("poisson_ratio", "Poisson's ratio", 0.3, minimum=-1, maximum=0.5))
                elif key == "section.create":
                    fields += (PropertySpec("thickness", "Shell thickness", 0.0, unit="input deck", minimum=0),)
                elif key == "solid_section.create":
                    fields += (PropertySpec("element_family", "Element formulation", "tetra4", kind="choice",
                                            choices=("tetra4", "tetra10", "hexa8"),
                                            choice_labels=("Linear Tet4", "Straight Tet10 (LAW1)", "Linear Hex8")),)
                    description += " Choose Tet10 for a prepared straight-edge quadratic tetrahedral mesh. Use a separate part for each element family."
                elif key == "coordinate_system.create":
                    fields += self._coordinate_fields()
                    description += " Static Cartesian SKEW only. X is Y cross Z; Y is orthogonalized. No node positions are moved."
                elif key == "curve.create":
                    fields += (PropertySpec("points", "Curve points", ((0., 0.), (1., 1.)), kind="table",
                                            components=("X", "Y"), unit="input deck", minimum_rows=2),)
                    description += " X values must strictly increase; values outside the range are linearly extrapolated."
                elif key == "group.create":
                    selection = self.session.selection()
                    selected = tuple(selection["ids"]) if selection["kind"] == "node" else ()
                    fields += (PropertySpec("node_ids", "Native node IDs", selected, kind="integer_list"),)
                elif key == "element_group.create":
                    fields += (self._element_members_field(),)
                    description += " Explicit element members must share one native family: beams, trusses, triangles, quadrilaterals, or solids."
                elif key == "surface.create":
                    fields += (self._reference_field("part_ids", "Shell parts", ("/PART/",), multiple=True),)
                    description += " Select nonempty shell or triangular shell parts. Solid faces require another surface type."
                else:
                    fields += self._condition_fields(key.split(".")[0])
                    if key == "load.create":
                        description += " The scaled curve is applied to EACH node; the group resultant is multiplied by node count."
                    if key == "contact.create":
                        description += " TYPE7 uses a secondary node group, main shell surface, shell-thickness gap and constant Coulomb friction."
            elif key == "object.edit":
                title = "Edit object"
                fields = tuple(field for field in self.properties(target, draft_values) if field.editable)
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
                title = "Assign material and section"
                fields = self._assignment_fields(card)
                description = f"Apply both references to {card['title'] or card['keyword']} in one Undo step."
            if key in CREATE_OPERATIONS:
                family = {"material.create": "/MAT/LAW1/0", "section.create": "/PROP/SHELL/0",
                          "solid_section.create": "/PROP/SOLID/0", "velocity.create": "/INIVEL/TRA/0",
                          "load.create": "/CLOAD/0"}.get(key, "/UNSPECIFIED")
                context = self.session._model_resource(None).unit_context()
                fields = self._display_specs(self._draft_specs(fields, draft_values), context, family.split("/"))
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
            spec = self.operation_spec(request.key, request.target, request.values)
            if set(request.values) != {field.name for field in spec.fields}:
                raise PrepError("invalid_value", "Supply exactly the fields in the operation form.")
            values = dict(request.values)
            if not isinstance(request.units, dict):
                raise PrepError("invalid_unit", "Units must be a field-to-unit mapping.")
            expected = {"expected_revision": request.expected_revision,
                        "expected_document_id": request.document_id}
            if request.key in CREATE_OPERATIONS:
                values = self._native_values({field.name: field for field in spec.fields}, values, request.units)
                native_id = values.pop("native_id")
                if type(native_id) is not int or native_id < 0:
                    raise PrepError("invalid_value", "The native ID must be a nonnegative integer.", {"field": "native_id"})
                for field in spec.fields:
                    if field.kind == "reference":
                        values[field.name] = None if field.name == "coordinate_system_id" and values[field.name] is None else self._card(values[field.name])["id"]
                    elif field.kind == "references":
                        if not isinstance(values[field.name], (list, tuple)):
                            raise PrepError("invalid_reference", "Choose a list of object references.")
                        if field.unit_context.get("reference_kind") != "mesh-element":
                            values[field.name] = [self._card(ref)["id"] for ref in values[field.name]]
                method = getattr(self.session, CREATE_OPERATIONS[request.key][1])
                result = method(**values, native_id=native_id or None, **expected)
            elif request.key == "object.edit":
                result = self.submit(SetProperties(request.target, values, request.expected_revision, request.units))
            elif request.key == "object.copy":
                self._native_values({field.name: field for field in spec.fields}, values, request.units)
                result = self.session.copy_card(request.target.object_id, **values, **expected)
            elif request.key == "object.delete":
                self._native_values({}, values, request.units)
                result = self.session.delete_card(request.target.object_id, **expected)
            elif request.key == "part.assign":
                self._native_values({field.name: field for field in spec.fields}, values, request.units)
                for name, category in (("material", "Materials"), ("property", "Properties")):
                    card = self._card(values[name])
                    if card["category"] != category:
                        raise PrepError("invalid_reference", f"Choose a {name} object.", {"field": name})
                result = self.session.assign_part(request.target.object_id,
                    material_id=values["material"].object_id,
                    property_id=values["property"].object_id, **expected)
            object_id = result.get("card_id")
            if object_id is None and request.key in ("part.assign", "object.edit"):
                object_id = request.target.object_id
            card = next((item for item in self.session.list_cards() if item["id"] == object_id), None)
            return {**result, "object": self.ref_for_card(card) if card else None}

    def undo(self):
        return self.session.undo()

    def target_roles(self, target):
        card = self._card(target)
        return tuple((role["key"], role["label"]) for role in
                     self.session.condition_targets(card["id"])["roles"])

    def select_target(self, target, role):
        card = self._card(target)
        return self.session.select_condition_target(card["id"], role)

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
