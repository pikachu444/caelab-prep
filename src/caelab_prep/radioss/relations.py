"""Initial mechanical-field support for the first mixed Radioss profile.

This is an editor applicability check, not equation numbering or a proof of
stiffness/coupling. Beam orientation nodes are not mechanical endpoints. Shell
rotations are represented as a subspace; no-drilling shells do not acquire a
third rotation merely because a UI has three checkboxes.

Native definitions: Altair Radioss 2024 reference pages beam_starter_r.htm,
prop_type3_beam_starter_r.htm, prop_type1_shell_starter_r.htm,
prop_type14_solid_starter_r.htm, skew_fix_starter_r.htm and cload_starter_r.htm.
"""
import math

from ..cae_core import PrepError
from .deck import number
from .modeling import native_identity, real, title, integer

AXES = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def dot(a, b): return sum(x * y for x, y in zip(a, b))
def subtract(a, b): return tuple(x - y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def unit(value):
    length = math.sqrt(dot(value, value))
    if not math.isfinite(length) or length <= 1e-12: raise PrepError("invalid_coordinate_system", "Coordinate directions must be finite, nonzero and independent.")
    return tuple(item / length for item in value)


def basis(vectors):
    result = []
    for vector in vectors:
        residual = tuple(vector)
        for axis in result: residual = subtract(residual, tuple(dot(residual, axis) * v for v in axis))
        if dot(residual, residual) > 1e-20: result.append(unit(residual))
    return result


def contained(vector, axes):
    residual = tuple(vector)
    for axis in basis(axes): residual = subtract(residual, tuple(dot(residual, axis) * v for v in axis))
    return dot(residual, residual) <= 1e-16


def _vector(values):
    if not isinstance(values, (tuple, list)) or len(values) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise PrepError("invalid_coordinate_system", "Use three finite vector components.")
    return tuple(float(v) for v in values)


def frame_from_vectors(origin, y_axis, z_axis):
    origin, y, z = _vector(origin), _vector(y_axis), unit(_vector(z_axis))
    x = unit(cross(y, z)); y = unit(cross(z, x))
    return {"origin": list(origin), "axes": [list(x), list(y), list(z)], "kind": "fixed-cartesian"}


def frame_block(identifier, name, origin, y_axis, z_axis, *, newline="\n"):
    integer(identifier); frame_from_vectors(origin, y_axis, z_axis)
    return newline.join([f"/SKEW/FIX/{identifier}", title(name), *("".join(real(v) for v in row) for row in (origin, y_axis, z_axis)), ""])


def coordinate_frame(resources, native_id=0):
    if native_id == 0: return {"native_id": 0, "card_id": None, "resource_id": None, "origin": [0., 0., 0.], "axes": [list(v) for v in AXES], "kind": "global-cartesian"}
    matches = [(resource, card) for resource in resources for card in resource.cards if native_identity(card.keyword) == ("SKEW", native_id)]
    if len(matches) != 1: raise PrepError("invalid_reference", "The coordinate system must resolve uniquely.", {"native_id": native_id})
    resource, card = matches[0]
    if card.keyword.upper() != f"/SKEW/FIX/{native_id}" or len(card.data) != 4:
        raise PrepError("unsupported_coordinate_system", "Only fixed Cartesian SKEW without a unit override is supported.")
    lines = resource.render().decode("latin1").splitlines()
    try:
        vectors = [[number(lines[index][col:col+20]) for col in (0, 20, 40)] for index in card.data[1:]]
        return {**frame_from_vectors(*vectors), "native_id": native_id, "card_id": card.id, "resource_id": resource.id}
    except (ValueError, IndexError): raise PrepError("invalid_coordinate_system", "Malformed fixed Cartesian coordinate system.") from None


def node_support(resources, projection, node_ids):
    requested = set(node_ids)
    result = {value: {"node_id": value, "translations": False, "rotation_basis": [], "formulations": [], "diagnostics": []} for value in requested}
    # Only requested-node descriptors are allocated. The immutable geometry is
    # shared; no dense node×DOF table or element clone is constructed.
    cards = {}; lines_by_resource = {}; parts = {}; props = {}
    shell_defaults_present = any(card.keyword.upper().split("/")[1] == "DEF_SHELL" for resource in resources for card in resource.cards)
    for resource in resources:
        lines_by_resource[resource.id] = resource.render().decode("latin1").splitlines()
        for card in resource.cards:
            cards[card.id] = (resource, card)
            identity = native_identity(card.keyword)
            if identity:
                if identity[0] == "PART": parts.setdefault(identity[1], []).append((resource, card))
                if identity[0] == "PROP": props.setdefault(identity[1], []).append((resource, card))
    points = dict(zip(projection["node_ids"], projection["points"]))
    for cell in projection["cells"]:
        targets = requested.intersection(cell["nodes"])
        if not targets: continue
        family = cell.get("formulation")
        rotations = {identifier: [] for identifier in targets}
        try:
            if len(parts.get(cell["part_id"], ())) != 1: raise ValueError("PART assignment is unresolved")
            owner, part = parts[cell["part_id"]][0]
            prop_id = int(lines_by_resource[owner.id][part.data[1]][:10])
            if len(props.get(prop_id, ())) != 1: raise ValueError("Property assignment is unresolved")
            owner, prop = props[prop_id][0]
            rows = [lines_by_resource[owner.id][index] for index in prop.data]
            pair = "/".join(prop.keyword.upper().strip("/").split("/")[:2])
            if family == "TRUSS" and pair in ("PROP/TRUSS", "PROP/TYPE2"):
                if float(rows[1][:20]) <= 0: raise ValueError("Truss area is invalid")
            elif family == "BEAM" and pair in ("PROP/BEAM", "PROP/TYPE3"):
                if int(rows[1][10:20].strip() or "0") != 1: raise ValueError("Only explicit small-strain beam Ismstr=1 is supported")
                if any(number(rows[3][start:start+20]) <= 0 for start in (0,20,40,60)): raise ValueError("Beam area/inertias must be positive")
                flags = rows[4][:10].rjust(10)
                bits = flags[3:6] + flags[7:10]
                if len(bits) != 6 or set(bits) - {"0", "1"}: raise ValueError("Explicit beam end-release flags are required")
                element_owner, element_card = cards[cell["card_id"]]
                row = next(lines_by_resource[element_owner.id][index] for index in element_card.data if int(lines_by_resource[element_owner.id][index][:10]) == cell["id"])
                orientation = int(row[30:40].strip() or "0")
                n1, n2 = cell["nodes"]
                x = unit(subtract(points[n2], points[n1]))
                if orientation in (0,n1,n2):
                    toward_y = AXES[2] if abs(dot(x,AXES[1])) >= 1-1e-12 else AXES[1]
                else: toward_y = subtract(points[orientation], points[n1])
                z = unit(cross(x, toward_y)); y = unit(cross(z, x))
                for identifier in targets:
                    released = bits[0:3] if identifier == n1 else bits[3:6]
                    rotations[identifier] = [axis for bit, axis in zip(released, (x,y,z)) if bit == "0"]
            elif family in ("SHELL", "SH3N") and pair in ("PROP/SHELL", "PROP/TYPE1"):
                shell = int(rows[1][:10].strip() or "0"); tri = int(rows[1][20:30].strip() or "0")
                drill = int(rows[1][30:40].strip() or "0"); integration = int(rows[3][:10].strip() or "0")
                if not shell_defaults_present:
                    shell, tri, drill = shell or 1, tri or 2, drill or 2
                if (family == "SHELL" and shell not in (1,2,3,4,12,24)) or (family == "SH3N" and tri not in (1,2)) or drill not in (1,2):
                    raise ValueError("Shell formulation/drilling defaults must be explicit and supported")
                if family == "SHELL" and drill == 1 and shell not in (12,24):
                    raise ValueError("Drilling stiffness is only documented for QBAT/QEPH quadrilaterals and standard triangles")
                if integration != 1:
                    a,b,c = (points[node] for node in cell["nodes"][:3])
                    x = unit(subtract(b,a)); z = unit(cross(x, subtract(c,a))); y = unit(cross(z,x))
                    for identifier in targets: rotations[identifier] = [x,y,z] if drill == 1 else [x,y]
            elif family in ("BRICK", "TETRA4", "TETRA10") and pair in ("PROP/SOLID", "PROP/TYPE14"):
                if family == "BRICK" and int(rows[1][:10].strip() or "0") != 1: raise ValueError("Only linear brick Isolid=1 is supported")
                if family == "TETRA4" and int(rows[1][60:70].strip() or "0") != 1000: raise ValueError("Only linear tetra4 Itetra4=1000 is supported")
                if family == "TETRA10" and tuple(int(rows[1][start:start + 10].strip() or "0") for start in (10, 20, 40)) != (4, 0, 1000):
                    raise ValueError("Only Lagrangian Tet10 Itetra10=1000 and Ismstr=4 are supported")
            else: raise ValueError("Element/property formulation is outside the supported mechanical profile")
        except (KeyError, ValueError, IndexError, StopIteration, PrepError) as exc:
            for identifier in targets: result[identifier]["diagnostics"].append({"code": "dof_support_unknown", "element_id": cell["id"], "reason": str(exc)})
            continue
        for identifier in targets:
            result[identifier]["translations"] = True
            result[identifier]["rotation_basis"].extend(rotations[identifier])
            result[identifier]["formulations"].append(family)
    for identifier, support in result.items():
        if identifier not in points: support["diagnostics"].append({"code": "missing_node"})
        elif not support["translations"] and not support["diagnostics"]: support["diagnostics"].append({"code": "no_mechanical_attachment"})
        support["rotation_basis"] = [list(v) for v in basis(support["rotation_basis"])]
        support["formulations"] = sorted(set(support["formulations"]))
        support["status"] = "unverified" if support["diagnostics"] else "supported"
    return [result[identifier] for identifier in node_ids]


def validate_components(resources, projection, node_ids, *, translations=(False,False,False), rotations=(False,False,False), native_skew_id=0, enforce=True):
    frame = coordinate_frame(resources, native_skew_id)
    supports = node_support(resources, projection, node_ids)
    failures = []
    for support in supports:
        if support["diagnostics"] or (any(translations) and not support["translations"]):
            failures.append(support); continue
        for enabled, axis in zip(rotations, frame["axes"]):
            if enabled and not contained(axis, support["rotation_basis"]):
                failures.append({"node_id": support["node_id"], "code": "inactive_rotation", "axis": axis,
                                 "rotation_basis": support["rotation_basis"]}); break
    if failures and enforce:
        raise PrepError("unsupported_condition_dof", "Every target node must support the requested components in the selected coordinate system.", {"nodes": failures})
    return {"coordinate_system": frame, "nodes": supports, "diagnostics": failures,
            "status": "unverified" if failures else "supported"}
