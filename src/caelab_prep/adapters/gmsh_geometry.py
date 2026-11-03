"""Pure bounded CAD cylinder witness policy shared by producer and readers.

No Gmsh/Qt imports, geometry mutation, or feature classification occurs here.
"""
from __future__ import annotations

import math
import sys


def _probe_support(face):
    """Only exact basis-aligned analytic supports; leave raw values untouched."""
    values = face["analytic_properties"]["reals"]
    if not all(math.isfinite(value) for value in values):
        return None
    if face["geometry_type"] == "Plane" and len(values) == 4:
        nonzero = [i for i, value in enumerate(values[:3]) if value != 0]
        if len(nonzero) != 1:
            return None
        axis = nonzero[0]; scale = abs(values[axis])
        if scale < sys.float_info.min:
            return None
        offset = values[3] / scale
        if values[3] != 0 and (offset == 0 or abs(offset) < sys.float_info.min):
            return None
        return ("plane", axis, values[axis] / scale, offset) if math.isfinite(offset) else None
    if face["geometry_type"] == "Cylinder" and len(values) == 7:
        nonzero = [i for i, value in enumerate(values[3:6]) if value != 0]
        if len(nonzero) == 1 and abs(values[3 + nonzero[0]]) == 1 and values[6] >= sys.float_info.min:
            return "cylinder", nonzero[0], tuple(values[:3]), values[6]
    return None


def _probe_full_period(bounds):
    low, high = bounds["minimum"][0], bounds["maximum"][0]
    span = high - low
    allowance = 4096 * math.ulp(max(abs(low), abs(high), math.tau))
    return (math.isfinite(span) and span > 0 and allowance < math.tau / 64
            and abs(span - math.tau) <= allowance)


def cylinder_probe_shape(face, surfaces, volumes, curves, tolerance, unit):
    """Check the bounded GI2 raw shape without SDK queries or input mutation.

    All entities are GI1 JSON dictionaries; the three collections are lists of
    those dictionaries. Tags are local to this inspection. Success does not
    establish clearance or material side: use plan_cylinder_material_probe next.
    """
    row = {"eligible": False, "reason": None, "volume_uuid": None}
    def reject(reason):
        row["reason"] = reason
        return row
    if unit not in ("mm", "cm", "m"):
        return reject("unknown_coordinate_unit")
    uses = face["orientation_by_volume"]
    if len(uses) != 1:
        return reject("single_owning_volume_required")
    row["volume_uuid"] = uses[0]["volume_uuid"]
    volume = next((v for v in volumes if v["uuid"] == row["volume_uuid"]), None)
    if volume is None or face["uuid"] not in volume["surface_uuids"]:
        return reject("owning_volume_boundary_unresolved")
    support = _probe_support(face)
    if support is None or support[0] != "cylinder":
        return reject("unsupported_cylinder_axis_or_radius")
    if not face["samples"] or face["samples"][0]["trim_count"] != 1:
        return reject("trim_sample_not_confirmed")
    if not _probe_full_period(face["parametric_bounds"]):
        return reject("full_cylinder_period_required")
    loops = face["curve_loops"]
    if len(loops) != 1:
        return reject("two_circles_and_repeated_seam_required")
    occurrences = [abs(tag) for tag in loops[0]["curve_tags"]]
    unique = set(occurrences); by_curve = {c["backend_tag"]: c for c in curves}
    if len(occurrences) != 4 or len(unique) != 3 or not unique <= by_curve.keys():
        return reject("two_circles_and_repeated_seam_required")
    circles = [by_curve[tag] for tag in unique if by_curve[tag]["geometry_type"] == "Circle" and occurrences.count(tag) == 1]
    seams = [by_curve[tag] for tag in unique if by_curve[tag]["geometry_type"] == "Line" and occurrences.count(tag) == 2]
    if len(circles) != 2 or len(seams) != 1 or seams[0]["adjacent_surface_uuids"] != [face["uuid"]]:
        return reject("two_circles_and_repeated_seam_required")
    for circle in circles:
        ends = circle["endpoints"]
        if (not _probe_full_period(circle["parametric_bounds"])
                or not (len(ends) == 0 or len(ends) == 2 and ends[0]["backend_tag"] == ends[1]["backend_tag"])):
            return reject("closed_full_circle_required")
    for identity in volume["surface_uuids"]:
        other = next((surface for surface in surfaces if surface["uuid"] == identity), None)
        if other is None or _probe_support(other) is None:
            return reject("unsupported_boundary_geometry")
    if any(not math.isfinite(circle["length"]) or circle["length"] < sys.float_info.min for circle in circles):
        return reject("circle_length_radius_mismatch")
    _, axis, origin, radius = support
    return {"eligible": True, "reason": None, "volume_uuid": row["volume_uuid"],
            "axis_index": axis, "axis_point": list(origin), "radius": radius}


BLEND_PROBE_POLICY = {
    "length_tolerance_mm": 1e-6,
    "angular_tolerance_radians": 1e-6,
    "scope": "axis_aligned_quarter_cylinder_rectangular_supports",
}


def _support_residual(support, xyz):
    if support[0] == "plane":
        return support[2] * xyz[support[1]] + support[3]
    return math.hypot(*(xyz[i] - support[2][i] for i in range(3) if i != support[1])) - support[3]


def analytic_signed_residual(face, xyz):
    """Return the normalized Plane/Cylinder signed residual, or None if unsupported."""
    try:
        support = _probe_support(face)
        if support is None or len(xyz) != 3 or not all(math.isfinite(value) for value in xyz):
            return None
        value = _support_residual(support, xyz)
        return value if math.isfinite(value) else None
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def _material_plan_row(face, tolerance):
    return {"surface_uuid": face["uuid"], "volume_uuid": None, "status": "indeterminate", "reason": None,
        "normal_reference": {"Plane": "plane_normal", "Cylinder": "cylinder_radial"}.get(face["geometry_type"]),
        "material_normal_sign": None,
        "plus": {"xyz": None, "inside_count": None, "signed_surface_residual": None},
        "minus": {"xyz": None, "inside_count": None, "signed_surface_residual": None},
        "epsilon": None, "geometry_tolerance": tolerance, "numerical_margin": None,
        "clearance_lower_estimate": None}


def _analytic_material_plan(face, surfaces, volumes, tolerance, unit, *, circles=()):
    row = _material_plan_row(face, tolerance)
    def reject(reason):
        row["reason"] = reason
        return row
    def positive(value):
        return math.isfinite(value) and value >= sys.float_info.min
    if unit not in ("mm", "cm", "m"):
        return reject("unknown_coordinate_unit")
    uses = face["orientation_by_volume"]
    if len(uses) != 1:
        return reject("single_owning_volume_required")
    row["volume_uuid"] = uses[0]["volume_uuid"]
    volume = next((v for v in volumes if v["uuid"] == row["volume_uuid"]), None)
    if volume is None or face["uuid"] not in volume["surface_uuids"]:
        return reject("owning_volume_boundary_unresolved")
    support = _probe_support(face)
    if support is None:
        return reject("unsupported_analytic_support")
    if not face["samples"] or face["samples"][0]["trim_count"] != 1:
        return reject("trim_sample_not_confirmed")
    p = tuple(face["samples"][0]["xyz"])
    if len(p) != 3:
        return reject("invalid_sample_coordinates")
    neighbors = []
    scale_values = [*p, *face["bbox"]]
    scale_values.extend([support[3]] if support[0] == "plane" else [*support[2], support[3]])
    by_surface = {surface["uuid"]: surface for surface in surfaces}
    for identity in volume["surface_uuids"]:
        if identity == face["uuid"]:
            continue
        other = by_surface.get(identity)
        geometry = _probe_support(other) if other else None
        if geometry is None:
            return reject("unsupported_boundary_geometry")
        neighbors.append(geometry); scale_values.extend(other["bbox"])
        scale_values.extend([geometry[3]] if geometry[0] == "plane" else [*geometry[2], geometry[3]])
    if not neighbors:
        return reject("boundary_clearance_unavailable")
    if not all(math.isfinite(value) for value in scale_values):
        return reject("nonfinite_geometry_scale")
    margin = 4096 * math.ulp(max(abs(value) for value in scale_values))
    row["numerical_margin"] = margin
    if not positive(margin) or not math.isfinite(tolerance) or tolerance < 0:
        return reject("numerical_margin_unavailable")
    if support[0] == "cylinder":
        _, axis, origin, radius = support
        circumference = math.tau * radius
        if not positive(circumference) or any(not positive(c["length"]) or abs(c["length"] - circumference) > margin for c in circles):
            return reject("circle_length_radius_mismatch")
        radial = [p[i] - origin[i] if i != axis else 0. for i in range(3)]
        rho = math.hypot(*radial)
        if not positive(rho) or abs(rho - radius) > margin:
            return reject("sample_not_on_cylinder")
        direction = [value / rho for value in radial]
    else:
        residual = _support_residual(support, p)
        if not math.isfinite(residual) or abs(residual) > margin:
            return reject("sample_not_on_plane")
        direction = [support[2] if i == support[1] else 0. for i in range(3)]
    distances = []
    for geometry in neighbors:
        lower = abs(_support_residual(geometry, p)) - margin
        if not positive(lower):
            return reject("no_positive_boundary_clearance")
        distances.append(lower)
    clearance = min(distances)
    epsilon = min(support[3] / 64, clearance / 64) if support[0] == "cylinder" else clearance / 64
    row.update(clearance_lower_estimate=clearance, epsilon=epsilon)
    floor = max(128 * tolerance, margin)
    if not positive(epsilon) or not positive(floor) or not epsilon > floor:
        return reject("offset_below_safety_floor")
    for label, sign in (("plus", 1), ("minus", -1)):
        position = [value + sign * epsilon * delta for value, delta in zip(p, direction)]
        if not all(math.isfinite(value) for value in position):
            return reject("nonfinite_offset")
        movement = math.dist(p, position)
        residual = _support_residual(support, position)
        row[label].update(xyz=position, signed_surface_residual=residual if math.isfinite(residual) else None)
        if (not positive(movement) or not movement < clearance / 16 or not math.isfinite(residual)
                or sign * residual < floor):
            return reject("offset_displacement_or_radial_residual_unsafe")
    row["status"] = "ready"
    return row


def plan_analytic_material_probe(face, surfaces, volumes, tolerance, unit):
    """Plan two raw queries in local coordinate units, without classifying a feature."""
    try:
        return _analytic_material_plan(face, surfaces, volumes, tolerance, unit)
    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        row = _material_plan_row(face, tolerance)
        row["reason"] = "unrepresentable_probe_geometry: " + str(exc)
        return row


def plan_cylinder_material_probe(face, surfaces, volumes, curves, tolerance, unit):
    """Keep GI2 full-cylinder eligibility and its original raw keys and values."""
    shape = cylinder_probe_shape(face, surfaces, volumes, curves, tolerance, unit)
    if not shape["eligible"]:
        row = _material_plan_row(face, tolerance)
        row.update(volume_uuid=shape["volume_uuid"], reason=shape["reason"])
    else:
        by_curve = {curve["backend_tag"]: curve for curve in curves}
        tags = set(abs(tag) for tag in face["curve_loops"][0]["curve_tags"])
        circles = [by_curve[tag] for tag in tags if by_curve[tag]["geometry_type"] == "Circle"]
        try:
            row = _analytic_material_plan(face, surfaces, volumes, tolerance, unit, circles=circles)
        except (OverflowError, ValueError, ZeroDivisionError) as exc:
            row = _material_plan_row(face, tolerance)
            row["reason"] = "unrepresentable_probe_geometry: " + str(exc)
    row.pop("normal_reference"); row.pop("material_normal_sign")
    row["radial_material_side"] = None
    for side in ("plus", "minus"):
        row[side]["signed_radial_residual"] = row[side].pop("signed_surface_residual")
    return row


def cylindrical_blend_shape(face, surfaces, volumes, curves, tolerance, unit, *,
                            length_tolerance=1e-6, angular_tolerance=1e-6):
    """Check one mm quarter-cylinder strip and connected rectangular supports.

    This shape gate deliberately admits both rounded-box and cusp geometry.
    Material-oriented G1 continuity must be reviewed from separate raw probes.
    """
    from .gmsh_topology import four_edge_cycle, rectangular_wire
    row = {"eligible": False, "reason": None, "volume_uuid": None}
    def reject(reason):
        row["reason"] = reason
        return row
    if unit != "mm":
        return reject("unsupported_blend_unit")
    if (type(length_tolerance) not in (int, float) or not math.isfinite(length_tolerance) or length_tolerance < 1e-6
            or type(angular_tolerance) not in (int, float) or not math.isfinite(angular_tolerance) or angular_tolerance < 1e-6):
        return reject("invalid_blend_tolerances")
    uses = face["orientation_by_volume"]
    if len(uses) != 1:
        return reject("single_owning_volume_required")
    row["volume_uuid"] = uses[0]["volume_uuid"]
    volume = next((v for v in volumes if v["uuid"] == row["volume_uuid"]), None)
    if volume is None or face["uuid"] not in volume["surface_uuids"]:
        return reject("owning_volume_boundary_unresolved")
    support = _probe_support(face)
    if support is None or support[0] != "cylinder":
        return reject("unsupported_blend_cylinder")
    _, axis, origin, radius = support
    if not face["samples"] or face["samples"][0]["trim_count"] != 1:
        return reject("trim_sample_not_confirmed")
    sample_residual = analytic_signed_residual(face, face["samples"][0]["xyz"])
    if sample_residual is None or abs(sample_residual) > length_tolerance:
        return reject("sample_not_on_cylinder")
    low_u, high_u = face["parametric_bounds"]["minimum"][0], face["parametric_bounds"]["maximum"][0]
    span = high_u - low_u
    if (not all(math.isfinite(v) for v in (low_u, high_u, span)) or not 0 < span < math.pi
            or 4096*math.ulp(max(abs(low_u), abs(high_u), math.tau)) >= angular_tolerance
            or abs(span - math.pi/2) > angular_tolerance):
        return reject("unsupported_blend_angular_span")
    loops = face["curve_loops"]
    if len(loops) != 1:
        return reject("single_strip_cycle_required")
    by_curve = {curve["backend_tag"]: curve for curve in curves}
    cycle = four_edge_cycle(loops[0]["curve_tags"], by_curve)
    if cycle is None:
        return reject("single_strip_cycle_required")
    lines = sorted(tag for tag in cycle["edges"] if by_curve[tag]["geometry_type"] == "Line")
    arcs = sorted(tag for tag in cycle["edges"] if by_curve[tag]["geometry_type"] == "Circle")
    if len(lines) != 2 or len(arcs) != 2:
        return reject("two_lines_two_end_arcs_required")
    vertices = cycle["vertices"]
    if any(abs(_support_residual(support, point)) > length_tolerance for point in vertices.values()):
        return reject("strip_vertices_off_cylinder")
    line_ends = []
    for tag in lines:
        ends = sorted(cycle["edges"][tag], key=lambda identity: vertices[identity][axis])
        a, b = (vertices[identity] for identity in ends)
        height = b[axis] - a[axis]
        if (height <= 2*length_tolerance or any(abs(a[i]-b[i]) > length_tolerance for i in range(3) if i != axis)
                or not math.isfinite(by_curve[tag]["length"]) or abs(by_curve[tag]["length"]-height) > length_tolerance):
            return reject("shared_line_not_generatrix")
        line_ends.append(ends)
    axial = [vertices[identity][axis] for identity in line_ends[0]]
    if any(abs(vertices[identity][axis]-expected) > length_tolerance
           for identity, expected in zip(line_ends[1], axial)):
        return reject("shared_lines_axial_range_mismatch")
    # The stored trim count cannot override a point outside this finite patch.
    # Use the actual endpoint rays, without inferring the CAD surface's u frame.
    transverse = [index for index in range(3) if index != axis]
    rays = []
    for ends in line_ends:
        radial = [vertices[ends[0]][index]-origin[index] for index in transverse]
        norm = math.hypot(*radial)
        if not math.isfinite(norm) or norm < sys.float_info.min:
            return reject("strip_generatrix_wedge_unresolved")
        rays.append([value/norm for value in radial])
    determinant = math.fsum((rays[0][0]*rays[1][1], -rays[0][1]*rays[1][0]))
    if not math.isfinite(determinant) or abs(determinant) < sys.float_info.min:
        return reject("strip_generatrix_wedge_unresolved")
    orientation = math.copysign(1., determinant)
    point = face["samples"][0]["xyz"]
    radial = [point[index]-origin[index] for index in transverse]
    first_side = orientation*math.fsum((rays[0][0]*radial[1], -rays[0][1]*radial[0]))
    second_side = orientation*math.fsum((radial[0]*rays[1][1], -radial[1]*rays[1][0]))
    if (not axial[0]+length_tolerance < point[axis] < axial[1]-length_tolerance
            or not all(math.isfinite(value) and value > length_tolerance for value in (first_side,second_side))):
        return reject("strip_sample_outside_patch")
    expected_arc_ends = {frozenset(pair) for pair in zip(*line_ends)}
    if {frozenset(cycle["edges"][tag]) for tag in arcs} != expected_arc_ends:
        return reject("end_arcs_do_not_join_axial_ends")
    for tag in arcs:
        curve = by_curve[tag]
        arc_low, arc_high = curve["parametric_bounds"]["minimum"][0], curve["parametric_bounds"]["maximum"][0]
        delta = arc_high - arc_low
        if (not all(math.isfinite(v) for v in (arc_low, arc_high, delta)) or not 0 < delta < math.pi
                or 4096*math.ulp(max(abs(arc_low),abs(arc_high),math.tau)) >= angular_tolerance
                or abs(delta-span) > angular_tolerance
                or not math.isfinite(curve["length"]) or abs(curve["length"]-radius*span) > length_tolerance):
            return reject("end_arc_span_or_length_mismatch")
    by_surface = {surface["uuid"]: surface for surface in surfaces}
    support_ids, rectangles, plane_axes = [], [], []
    for tag in lines:
        adjacent = by_curve[tag]["adjacent_surface_uuids"]
        if len(adjacent) != 2 or len(set(adjacent)) != 2 or face["uuid"] not in adjacent:
            return reject("shared_line_adjacency_unresolved")
        identity = next(value for value in adjacent if value != face["uuid"])
        plane = by_surface.get(identity)
        geometry = _probe_support(plane) if plane else None
        if (geometry is None or geometry[0] != "plane" or geometry[1] == axis
                or [use["volume_uuid"] for use in plane["orientation_by_volume"]] != [row["volume_uuid"]]
                or identity not in volume["surface_uuids"]):
            return reject("unsupported_blend_support")
        if (abs(abs(_support_residual(geometry, origin))-radius) > length_tolerance
                or any(abs(_support_residual(geometry, vertices[v])) > length_tolerance for v in cycle["edges"][tag])):
            return reject("support_not_tangent_at_shared_line")
        plane_loops = plane["curve_loops"]
        if len(plane_loops) != 1 or tag not in [abs(value) for value in plane_loops[0]["curve_tags"]]:
            return reject("single_rectangular_support_required")
        coordinate = -geometry[3]/geometry[2]
        rectangle = rectangular_wire(plane_loops[0]["curve_tags"], by_curve, geometry[1], coordinate, length_tolerance)
        if rectangle is None:
            return reject("single_rectangular_support_required")
        samples = plane["samples"]
        if not samples or samples[0]["trim_count"] != 1:
            return reject("support_trim_sample_unconfirmed")
        point = samples[0]["xyz"]
        if (len(point) != 3 or not all(math.isfinite(value) for value in point)
                or abs(_support_residual(geometry, point)) > length_tolerance
                or any(not a+length_tolerance < point[i] < b-length_tolerance
                       for i,a,b in zip(rectangle["plane_axes"],rectangle["minimum"],rectangle["maximum"]))):
            return reject("support_sample_outside_rectangular_patch")
        support_ids.append(identity);plane_axes.append(geometry[1])
        rectangles.append({"surface_uuid": identity,"shared_line_tag": tag,
            **{key:rectangle[key] for key in ("plane_axis","plane_coordinate","plane_axes","minimum","maximum","area","perimeter")}})
    if len(set(support_ids)) != 2 or len(set(plane_axes)) != 2:
        return reject("two_orthogonal_supports_required")
    return {"eligible": True,"reason": None,"volume_uuid": row["volume_uuid"],
        "axis_index": axis,"axis_point": list(origin),"radius": radius,
        "support_surface_uuids": support_ids,"shared_line_tags": lines,"axial_range": axial,
        "evidence": {"u_span":span,"end_arc_tags":arcs,"rectangular_supports":rectangles}}
