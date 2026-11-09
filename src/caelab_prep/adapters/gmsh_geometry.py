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


CONICAL_PROBE_POLICY = {
    "length_tolerance_mm": 1e-6,
    "angular_tolerance_radians": 1e-6,
    "scope": "axis_aligned_finite_quarter_cone_trapezoidal_supports",
    "radius_metric": "max_finite_principal_radius",
}


def _conical_support(face):
    """Expanded analytic math only: callers must explicitly opt into its planner."""
    values = face["analytic_properties"]["reals"]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        return None
    if face["geometry_type"] == "Plane" and len(values) == 4:
        norm = math.hypot(*values[:3])
        if not math.isfinite(norm) or norm < sys.float_info.min:
            return None
        normal = tuple(value/norm for value in values[:3]); offset = values[3]/norm
        if (not math.isfinite(offset) or values[3] != 0 and abs(offset) < sys.float_info.min
                or any(value != 0 and abs(unit) < sys.float_info.min for value, unit in zip(values[:3], normal))):
            return None
        return "plane3", normal, offset
    if face["geometry_type"] == "Cone" and len(values) == 8:
        nonzero = [i for i, value in enumerate(values[3:6]) if value != 0]
        alpha = values[7]
        if (len(nonzero) != 1 or abs(values[3+nonzero[0]]) != 1 or values[6] < 0
                or not 1e-6 <= abs(alpha) < math.pi/2):
            return None
        cosine, sine = math.cos(alpha), math.sin(alpha)
        if cosine < 1e-6:
            return None
        return "cone", nonzero[0], tuple(values[:3]), values[6], values[3+nonzero[0]], alpha, cosine, sine
    return _probe_support(face)


def _cone_coordinates(support, xyz):
    axis, origin = support[1:3]
    radial = tuple(xyz[i]-origin[i] if i != axis else 0. for i in range(3))
    return radial, math.hypot(*radial), (xyz[axis]-origin[axis])*support[4]


def _support_scale_values(support):
    if support[0] == "plane":return [support[3]]
    if support[0] == "plane3":return [support[2]]
    return [*support[2], support[3]]


def _support_residual(support, xyz):
    if support[0] == "plane":
        return support[2] * xyz[support[1]] + support[3]
    if support[0] == "plane3":
        return math.fsum(n*p for n,p in zip(support[1],xyz)) + support[2]
    if support[0] == "cone":
        _, rho, z = _cone_coordinates(support,xyz)
        return math.fsum(((rho-support[3])*support[6],-z*support[7]))
    return math.hypot(*(xyz[i] - support[2][i] for i in range(3) if i != support[1])) - support[3]


def analytic_signed_residual(face, xyz):
    """Return an unoriented analytic signed residual; this does not grant eligibility."""
    try:
        support = _conical_support(face)
        if support is None or len(xyz) != 3 or not all(math.isfinite(value) for value in xyz):
            return None
        value = _support_residual(support, xyz)
        return value if math.isfinite(value) else None
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def _support_unit_normal(support, xyz):
    kind = support[0]
    if kind == "plane":return tuple(support[2] if i == support[1] else 0. for i in range(3))
    if kind == "plane3":return support[1]
    if kind == "cone":
        radial, rho, _ = _cone_coordinates(support,xyz)
        if not math.isfinite(rho) or rho < sys.float_info.min:return None
        return tuple(support[6]*value/rho - (support[7]*support[4] if i == support[1] else 0.)
                     for i,value in enumerate(radial))
    radial = tuple(xyz[i]-support[2][i] if i != support[1] else 0. for i in range(3))
    rho = math.hypot(*radial)
    return tuple(value/rho for value in radial) if math.isfinite(rho) and rho >= sys.float_info.min else None


def analytic_unit_normal(face, xyz):
    """Unoriented analytic reference normal; never a raw face/volume-sign product."""
    try:
        support = _conical_support(face)
        if support is None or len(xyz) != 3 or not all(math.isfinite(v) for v in xyz):return None
        normal = _support_unit_normal(support,xyz)
        return normal if normal is not None and all(math.isfinite(v) for v in normal) else None
    except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
        return None


def _support_clearance(support, xyz):
    if support[0] == "cone":
        _,rho,z = _cone_coordinates(support,xyz)
        # Both nappes: positive-nappe residual alone can miss a nearby other nappe.
        b = math.fsum((support[3]*support[6],z*support[7]))
        return abs(math.fsum((rho*support[6],-abs(b))))
    return abs(_support_residual(support,xyz))


def _material_plan_row(face, tolerance, *, conical_supports=False):
    return {"surface_uuid": face["uuid"], "volume_uuid": None, "status": "indeterminate", "reason": None,
        "normal_reference": {"Plane": "plane_normal", "Cylinder": "cylinder_radial"}.get(face["geometry_type"], "cone_radial_axial" if conical_supports and face["geometry_type"] == "Cone" else None),
        "material_normal_sign": None,
        "plus": {"xyz": None, "inside_count": None, "signed_surface_residual": None},
        "minus": {"xyz": None, "inside_count": None, "signed_surface_residual": None},
        "epsilon": None, "geometry_tolerance": tolerance, "numerical_margin": None,
        "clearance_lower_estimate": None}


def _analytic_material_plan(face, surfaces, volumes, tolerance, unit, *, circles=(), conical_supports=False):
    row = _material_plan_row(face, tolerance, conical_supports=conical_supports)
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
    if type(conical_supports) is not bool:return reject("invalid_conical_support_mode")
    support_reader = _conical_support if conical_supports else _probe_support
    support = support_reader(face)
    if support is None:
        return reject("unsupported_analytic_support")
    if not face["samples"] or face["samples"][0]["trim_count"] != 1:
        return reject("trim_sample_not_confirmed")
    p = tuple(face["samples"][0]["xyz"])
    if len(p) != 3:
        return reject("invalid_sample_coordinates")
    neighbors = []
    scale_values = [*p, *face["bbox"]]
    scale_values.extend(_support_scale_values(support))
    by_surface = {surface["uuid"]: surface for surface in surfaces}
    for identity in volume["surface_uuids"]:
        if identity == face["uuid"]:
            continue
        other = by_surface.get(identity)
        geometry = support_reader(other) if other else None
        if geometry is None:
            return reject("unsupported_boundary_geometry")
        neighbors.append(geometry); scale_values.extend(other["bbox"])
        scale_values.extend(_support_scale_values(geometry))
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
        radial_cap = radius/64
    elif support[0] == "cone":
        _,rho,z = _cone_coordinates(support,p)
        section = math.fsum((support[3]*support[6],z*support[7]))/support[6]
        if not positive(rho) or not positive(section):return reject("cone_sample_not_positive_nappe")
        residual = _support_residual(support,p)
        if not math.isfinite(residual) or abs(residual) > margin:return reject("sample_not_on_cone")
        direction = _support_unit_normal(support,p)
        if direction is None:return reject("cone_normal_unavailable")
        radial_cap = rho/64
    else:
        residual = _support_residual(support, p)
        if not math.isfinite(residual) or abs(residual) > margin:
            return reject("sample_not_on_plane")
        direction = _support_unit_normal(support,p)
        radial_cap = None
    distances = []
    for geometry in neighbors:
        lower = _support_clearance(geometry, p) - margin
        if not positive(lower):
            return reject("no_positive_boundary_clearance")
        distances.append(lower)
    clearance = min(distances)
    epsilon = min(radial_cap, clearance/64) if radial_cap is not None else clearance/64
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


def plan_analytic_material_probe(face, surfaces, volumes, tolerance, unit, *, conical_supports=False):
    """Plan two raw queries in local coordinate units, without classifying a feature."""
    try:
        return _analytic_material_plan(face, surfaces, volumes, tolerance, unit, conical_supports=conical_supports)
    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        row = _material_plan_row(face, tolerance, conical_supports=conical_supports)
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


def _finite_sector_sample_issue(point, axis, origin, vertices, line_ends, axial, length_tolerance):
    """Actual endpoint rays define the finite minor patch, independent of CAD u phase."""
    transverse = [index for index in range(3) if index != axis]
    rays = []
    for ends in line_ends:
        radial = [vertices[ends[0]][index]-origin[index] for index in transverse]
        norm = math.hypot(*radial)
        if not math.isfinite(norm) or norm < sys.float_info.min:
            return "strip_generatrix_wedge_unresolved"
        rays.append([value/norm for value in radial])
    determinant = math.fsum((rays[0][0]*rays[1][1], -rays[0][1]*rays[1][0]))
    if not math.isfinite(determinant) or abs(determinant) < sys.float_info.min:
        return "strip_generatrix_wedge_unresolved"
    orientation = math.copysign(1., determinant)
    radial = [point[index]-origin[index] for index in transverse]
    first_side = orientation*math.fsum((rays[0][0]*radial[1], -rays[0][1]*radial[0]))
    second_side = orientation*math.fsum((radial[0]*rays[1][1], -radial[1]*rays[1][0]))
    if (not axial[0]+length_tolerance < point[axis] < axial[1]-length_tolerance
            or not all(math.isfinite(value) and value > length_tolerance for value in (first_side,second_side))):
        return "strip_sample_outside_patch"
    return None


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
    issue = _finite_sector_sample_issue(face["samples"][0]["xyz"],axis,origin,vertices,line_ends,axial,length_tolerance)
    if issue:return reject(issue)
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



def _cone_section(support, world_coordinate):
    z = (world_coordinate-support[2][support[1]])*support[4]
    radius = math.fsum((support[3]*support[6],z*support[7]))/support[6]
    curvature_radius = radius/support[6]
    if not all(math.isfinite(value) and value >= sys.float_info.min for value in (radius,curvature_radius)):
        return None
    return radius,curvature_radius


def _conical_blend_shape(face, surfaces, volumes, curves, tolerance, unit, length_tolerance, angular_tolerance):
    from .gmsh_topology import four_edge_cycle,planar_trapezoid_wire,point_in_planar_wire
    row = {"eligible":False,"reason":None,"volume_uuid":None}
    def reject(reason):
        row["reason"]=reason
        return row
    if unit != "mm":return reject("unsupported_conical_unit")
    if (type(length_tolerance) not in (int,float) or not math.isfinite(length_tolerance) or length_tolerance < 1e-6
            or type(angular_tolerance) not in (int,float) or not math.isfinite(angular_tolerance)
            or not 1e-6 <= angular_tolerance < math.pi/2):
        return reject("invalid_conical_tolerances")
    uses=face["orientation_by_volume"]
    if len(uses)!=1:return reject("single_owning_volume_required")
    row["volume_uuid"]=uses[0]["volume_uuid"]
    volume=next((v for v in volumes if v["uuid"]==row["volume_uuid"]),None)
    if volume is None or face["uuid"] not in volume["surface_uuids"]:
        return reject("owning_volume_boundary_unresolved")
    support=_conical_support(face)
    if support is None or support[0]!="cone":return reject("unsupported_conical_surface")
    axis,origin=support[1:3];cosine=support[6]
    if not face["samples"] or face["samples"][0]["trim_count"]!=1:return reject("trim_sample_not_confirmed")
    point=face["samples"][0]["xyz"]
    residual=analytic_signed_residual(face,point)
    if residual is None or abs(residual)>length_tolerance:return reject("sample_not_on_cone")
    low_u,high_u=face["parametric_bounds"]["minimum"][0],face["parametric_bounds"]["maximum"][0]
    span=high_u-low_u
    if (not all(math.isfinite(v) for v in (low_u,high_u,span)) or not 0<span<math.pi
            or 4096*math.ulp(max(abs(low_u),abs(high_u),math.tau))>=angular_tolerance
            or abs(span-math.pi/2)>angular_tolerance):return reject("unsupported_conical_angular_span")
    loops=face["curve_loops"];by_curve={curve["backend_tag"]:curve for curve in curves}
    if len(loops)!=1:return reject("single_conical_strip_cycle_required")
    cycle=four_edge_cycle(loops[0]["curve_tags"],by_curve)
    if cycle is None:return reject("single_conical_strip_cycle_required")
    lines=sorted(tag for tag in cycle["edges"] if by_curve[tag]["geometry_type"]=="Line")
    arcs=sorted(tag for tag in cycle["edges"] if by_curve[tag]["geometry_type"]=="Circle")
    if len(lines)!=2 or len(arcs)!=2:return reject("two_generatrices_two_end_arcs_required")
    vertices=cycle["vertices"];line_ends=[];rays=[]
    for vertex in vertices.values():
        section=_cone_section(support,vertex[axis])
        if section is None or section[0]<=length_tolerance:return reject("conical_apex_or_wrong_nappe")
        if abs(_support_residual(support,vertex))>length_tolerance:return reject("strip_vertices_off_cone")
    for tag in lines:
        ends=sorted(cycle["edges"][tag],key=lambda identity:vertices[identity][axis])
        a,b=(vertices[identity] for identity in ends);height=b[axis]-a[axis]
        ra,rhoa,_=_cone_coordinates(support,a);rb,rhob,_=_cone_coordinates(support,b)
        if min(rhoa,rhob)<=length_tolerance:return reject("conical_apex_or_wrong_nappe")
        ua,ub=tuple(v/rhoa for v in ra),tuple(v/rhob for v in rb)
        length=by_curve[tag]["length"]
        if (height<=2*length_tolerance or not math.isfinite(length) or length<=0
                or abs(length-math.dist(a,b))>length_tolerance or abs(length-height/cosine)>length_tolerance
                or math.dist(ua,ub)>angular_tolerance
                or math.dist(ua,ub)*max(rhoa,rhob)>length_tolerance):return reject("shared_line_not_conical_generatrix")
        line_ends.append(ends);rays.append(ua)
    axial=[vertices[identity][axis] for identity in line_ends[0]]
    if any(abs(vertices[identity][axis]-expected)>length_tolerance for identity,expected in zip(line_ends[1],axial)):
        return reject("shared_lines_axial_range_mismatch")
    transverse=[index for index in range(3) if index!=axis]
    determinant=rays[0][transverse[0]]*rays[1][transverse[1]]-rays[0][transverse[1]]*rays[1][transverse[0]]
    ray_angle=math.atan2(abs(determinant),math.fsum(a*b for a,b in zip(rays[0],rays[1])))
    if abs(ray_angle-span)>angular_tolerance:return reject("conical_endpoint_phase_mismatch")
    issue=_finite_sector_sample_issue(point,axis,origin,vertices,line_ends,axial,length_tolerance)
    if issue:return reject(issue)
    end_sections=[]
    for coordinate in axial:
        section=_cone_section(support,coordinate)
        if section is None or section[0]<=length_tolerance:return reject("conical_apex_or_wrong_nappe")
        end_sections.append({"axial_coordinate":coordinate,"radius":section[0],"curvature_radius":section[1]})
    expected_pairs=[frozenset(pair) for pair in zip(*line_ends)]
    if {frozenset(cycle["edges"][tag]) for tag in arcs}!=set(expected_pairs):
        return reject("end_arcs_do_not_join_axial_ends")
    by_surface={surface["uuid"]:surface for surface in surfaces};ordered_arcs=[]
    for pair,section in zip(expected_pairs,end_sections):
        tag=next(tag for tag in arcs if frozenset(cycle["edges"][tag])==pair);curve=by_curve[tag]
        a,b=curve["parametric_bounds"]["minimum"][0],curve["parametric_bounds"]["maximum"][0];delta=b-a
        if (not all(math.isfinite(v) for v in (a,b,delta,curve["length"])) or not 0<delta<math.pi
                or 4096*math.ulp(max(abs(a),abs(b),math.tau))>=angular_tolerance
                or abs(delta-span)>angular_tolerance or curve["length"]<=0
                or abs(curve["length"]-section["radius"]*span)>length_tolerance):
            return reject("conical_end_arc_span_or_length_mismatch")
        adjacent=curve["adjacent_surface_uuids"]
        if len(adjacent)!=2 or len(set(adjacent))!=2 or face["uuid"] not in adjacent:
            return reject("conical_end_cap_unresolved")
        cap_id=next(identity for identity in adjacent if identity!=face["uuid"]);cap=by_surface.get(cap_id)
        cap_support=_probe_support(cap) if cap else None
        if (cap_support is None or cap_support[0]!="plane" or cap_support[1]!=axis
                or cap_id not in volume["surface_uuids"]
                or [use["volume_uuid"] for use in cap["orientation_by_volume"]]!=[row["volume_uuid"]]
                or abs(-cap_support[3]/cap_support[2]-section["axial_coordinate"])>length_tolerance):
            return reject("conical_end_cap_unresolved")
        ordered_arcs.append(tag)
    support_ids=[];trapezoids=[]
    for tag in lines:
        adjacent=by_curve[tag]["adjacent_surface_uuids"]
        if len(adjacent)!=2 or len(set(adjacent))!=2 or face["uuid"] not in adjacent:
            return reject("shared_line_adjacency_unresolved")
        identity=next(value for value in adjacent if value!=face["uuid"]);plane=by_surface.get(identity)
        geometry=_conical_support(plane) if plane else None
        if (geometry is None or geometry[0]!="plane3" or identity not in volume["surface_uuids"]
                or [use["volume_uuid"] for use in plane["orientation_by_volume"]]!=[row["volume_uuid"]]):
            return reject("unsupported_conical_support")
        normal,offset=geometry[1:3];a,b=(vertices[v] for v in cycle["edges"][tag])
        midpoint=[x/2+y/2 for x,y in zip(a,b)];cone_normal=analytic_unit_normal(face,midpoint)
        if (cone_normal is None or abs(math.fsum(x*y for x,y in zip(normal,cone_normal)))<math.cos(angular_tolerance)
                or any(abs(_support_residual(geometry,p))>length_tolerance for p in (a,b))):
            return reject("support_not_tangent_to_conical_generatrix")
        plane_loops=plane["curve_loops"]
        if len(plane_loops)!=1 or tag not in [abs(value) for value in plane_loops[0]["curve_tags"]]:
            return reject("single_trapezoidal_support_required")
        wire=planar_trapezoid_wire(plane_loops[0]["curve_tags"],by_curve,normal,offset,axis,axial,length_tolerance)
        if wire is None:return reject("single_trapezoidal_support_required")
        samples=plane["samples"]
        if not samples or samples[0]["trim_count"]!=1 or not point_in_planar_wire(wire,samples[0]["xyz"],length_tolerance):
            return reject("support_sample_outside_trapezoidal_patch")
        support_ids.append(identity)
        trapezoids.append({"surface_uuid":identity,"shared_line_tag":tag,
            **{key:wire[key] for key in ("plane_normal","plane_offset","ordered_vertices","area","perimeter","axial_range")}})
    if len(set(support_ids))!=2:return reject("two_distinct_conical_supports_required")
    radii=sorted(section["curvature_radius"] for section in end_sections)
    return {"eligible":True,"reason":None,"volume_uuid":row["volume_uuid"],"axis_index":axis,
        "axis_point":list(origin),"axis_direction":list(face["analytic_properties"]["reals"][3:6]),
        "semi_angle":support[5],"axial_range":axial,"end_sections":end_sections,
        "curvature_radius_range":radii,"radius":radii[-1],"support_surface_uuids":support_ids,
        "shared_line_tags":lines,"evidence":{"u_span":span,"end_arc_tags":ordered_arcs,"trapezoidal_supports":trapezoids}}


def conical_blend_shape(face, surfaces, volumes, curves, tolerance, unit, *, length_tolerance=1e-6,angular_tolerance=1e-6):
    """Bounded mm finite-quarter Cone shape; material/G1/threshold verdicts are separate."""
    try:
        return _conical_blend_shape(face,surfaces,volumes,curves,tolerance,unit,length_tolerance,angular_tolerance)
    except (KeyError,IndexError,TypeError,ValueError,OverflowError,ZeroDivisionError,StopIteration):
        return {"eligible":False,"reason":"malformed_conical_geometry","volume_uuid":None}
