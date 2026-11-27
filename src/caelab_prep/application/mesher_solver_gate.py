"""Native element admissibility for the generated mesh connection.

The verified family is only one prerequisite for a structural solve. This
boundary does not handle user-authored solver inputs or choose formulations.
"""
from collections import defaultdict
import math
from pathlib import Path

from ..cae_core.errors import PrepError
from .tet10_geometry import native_tet10_nodes


# (Gmsh type, dimension, order, full node count). The tested OpenCourant wedge
# keyword selects a thick shell, so an ordinary wedge has no entry here.
_CCX = {(4, 3, 1, 4): "C3D4", (5, 3, 1, 8): "C3D8", (6, 3, 1, 6): "C3D6",
        (11, 3, 2, 10): "C3D10", (2, 2, 1, 3): "S3", (3, 2, 1, 4): "S4"}
_RAD = {(4, 3, 1, 4): "/TETRA4", (5, 3, 1, 8): "/BRICK",
        (2, 2, 1, 3): "/SH3N", (3, 2, 1, 4): "/SHELL"}
_PROFILES = {("calculix", "2.21"): _CCX, ("opencourant", "20261011"): _RAD,
             ("openradioss", "2472f27484c2f19c2300d9c18d522b297ce818eb"): _RAD}


def require_generated_mesh_support(mesh, *, solver, version):
    """Validate the entire physical connectivity before opening an export file."""
    profile = _PROFILES.get((solver, version))
    if profile is None or not mesh.elements:
        raise PrepError("solver_element_unsupported", f"No generated-mesh profile for {solver} {version}, or empty mesh.")
    kinds = set()
    for cell in mesh.elements:
        key = (cell.element_type, cell.dimension, cell.order, len(cell.node_ids))
        if key not in profile or len(set(cell.node_ids)) != len(cell.node_ids):
            raise PrepError("solver_element_unsupported",
                            f"{solver} {version} cannot export element {cell.id} ({cell.element_name}, Gmsh {cell.element_type}).")
        kinds.add(profile[key])
    return tuple(sorted(kinds))


def _ccx_coordinate(value):
    """Use maximum available precision within ccx 2.21's 20-character input field."""
    for precision in range(17, 0, -1):
        token = format(value, f".{precision}g")
        if len(token) <= 20:
            return token
    raise PrepError("invalid_candidate", "Coordinate cannot be encoded in a CalculiX input field.")


def write_calculix_mesh_include(candidate, destination, *, version="2.21"):
    """Write nodes and native elements with one ELSET per owning physical part.

    The caller supplies materials, sections, loads, steps and compatible units.
    Return the mapping from part UUID to the set name to use in that deck.
    """
    mesh = candidate.to_native_mesh()
    require_generated_mesh_support(mesh, solver="calculix", version=version)
    by_id = {node.id: node.xyz for node in mesh.nodes}
    if (len(by_id) != len(mesh.nodes) or any(type(i) is not int or i <= 0 or len(p) != 3
            or not all(map(math.isfinite, p)) for i, p in by_id.items())):
        raise PrepError("invalid_candidate", "Generated nodes require distinct positive IDs and finite coordinates.")
    part_sets = {part.uuid: f"PART_{index}" for index, part in enumerate(mesh.parts, 1)}
    membership = {part.uuid: set(part.element_ids) for part in mesh.parts}
    if len(part_sets) != len(mesh.parts):
        raise PrepError("invalid_candidate", "Duplicate mesh part identifier.")
    groups = defaultdict(list)
    seen = set()
    for cell in mesh.elements:
        if (cell.id in seen or type(cell.id) is not int or cell.id <= 0
                or cell.id not in membership.get(cell.part_uuid, ())
                or any(n not in by_id for n in cell.node_ids)):
            raise PrepError("invalid_candidate", "Missing or duplicate element, node or part reference.")
        membership[cell.part_uuid].remove(cell.id)
        seen.add(cell.id)
        keyword = _CCX[(cell.element_type, cell.dimension, cell.order, len(cell.node_ids))]
        ordered = native_tet10_nodes(cell.node_ids) if keyword == "C3D10" else cell.node_ids
        groups[(part_sets[cell.part_uuid], keyword)].append((cell.id, *ordered))
    if any(membership.values()):
        raise PrepError("invalid_candidate", "A source part contains extra or ambiguous elements.")
    lines = [f"** CAELab mesh coordinates in {mesh.length_unit}", "*NODE"]
    encoded = {}
    for node, point in by_id.items():
        fields = tuple(map(_ccx_coordinate, point))
        if encoded.setdefault(fields, point) != point:
            raise PrepError("invalid_candidate", "Distinct mesh coordinates coincide at CalculiX field precision.")
        lines.append(f"{node}, " + ", ".join(fields))
    for (name, keyword), elements in groups.items():
        lines.append(f"*ELEMENT, TYPE={keyword}, ELSET={name}")
        lines.extend(", ".join(map(str, row)) for row in elements)
    with Path(destination).open("x", encoding="ascii", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    return part_sets
