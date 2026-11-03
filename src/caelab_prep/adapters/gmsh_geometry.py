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


def _plan_cylinder_material_probe(face, surfaces, volumes, curves, tolerance, unit):
    row = {"surface_uuid": face["uuid"], "volume_uuid": None, "status": "indeterminate", "reason": None,
        "radial_material_side": None, "plus": {"xyz": None, "inside_count": None, "signed_radial_residual": None},
        "minus": {"xyz": None, "inside_count": None, "signed_radial_residual": None},
        "epsilon": None, "geometry_tolerance": tolerance, "numerical_margin": None,
        "clearance_lower_estimate": None}
    def reject(reason):
        row["reason"] = reason
        return row
    def positive(value):
        return math.isfinite(value) and value >= sys.float_info.min
    shape = cylinder_probe_shape(face, surfaces, volumes, curves, tolerance, unit)
    row["volume_uuid"] = shape["volume_uuid"]
    if not shape["eligible"]:
        return reject(shape["reason"])
    volume = next(v for v in volumes if v["uuid"] == shape["volume_uuid"])
    support = _probe_support(face)
    by_curve = {curve["backend_tag"]: curve for curve in curves}
    tags = set(abs(tag) for tag in face["curve_loops"][0]["curve_tags"])
    circles = [by_curve[tag] for tag in tags if by_curve[tag]["geometry_type"] == "Circle"]
    p = tuple(face["samples"][0]["xyz"])
    _, axis, origin, radius = support
    neighbors = []
    scale_values = [*p, *origin, radius, *face["bbox"]]
    by_surface = {s["uuid"]: s for s in surfaces}
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
    circumference = math.tau * radius
    if not positive(circumference) or any(not positive(c["length"]) or abs(c["length"] - circumference) > margin for c in circles):
        return reject("circle_length_radius_mismatch")
    radial = [p[i] - origin[i] if i != axis else 0. for i in range(3)]
    rho = math.hypot(*radial)
    if not positive(rho) or abs(rho - radius) > margin:
        return reject("sample_not_on_cylinder")
    direction = [value / rho for value in radial]
    distances = []
    for geometry in neighbors:
        if geometry[0] == "plane":
            distance = abs(geometry[2] * p[geometry[1]] + geometry[3])
        else:
            distance = abs(math.hypot(*(p[i] - geometry[2][i] for i in range(3) if i != geometry[1])) - geometry[3])
        lower = distance - margin
        if not positive(lower):
            return reject("no_positive_boundary_clearance")
        distances.append(lower)
    clearance = min(distances); epsilon = min(radius / 64, clearance / 64)
    row.update(clearance_lower_estimate=clearance, epsilon=epsilon)
    floor = max(128 * tolerance, margin)
    if not positive(epsilon) or not positive(floor) or not epsilon > floor:
        return reject("offset_below_safety_floor")
    for label, sign in (("plus", 1), ("minus", -1)):
        position = [value + sign * epsilon * delta for value, delta in zip(p, direction)]
        if not all(math.isfinite(value) for value in position):
            return reject("nonfinite_offset")
        movement = math.dist(p, position)
        residual = math.hypot(*(position[i] - origin[i] for i in range(3) if i != axis)) - radius
        row[label].update(xyz=position, signed_radial_residual=residual if math.isfinite(residual) else None)
        if (not positive(movement) or not movement < clearance / 16 or not math.isfinite(residual)
                or sign * residual < floor):
            return reject("offset_displacement_or_radial_residual_unsafe")
    row["status"] = "ready"
    return row


def plan_cylinder_material_probe(face, surfaces, volumes, curves, tolerance, unit):
    """Return a pure bounded offset plan; ``ready`` authorizes two raw queries.

    Same GI1 dictionary/list inputs as cylinder_probe_shape. No SDK or feature
    classification occurs. ``inside_count`` remains None in both positions.
    """
    try:
        return _plan_cylinder_material_probe(face, surfaces, volumes, curves, tolerance, unit)
    except (OverflowError, ValueError, ZeroDivisionError) as exc:
        return {"surface_uuid": face["uuid"], "volume_uuid": None, "status": "indeterminate",
            "reason": "unrepresentable_probe_geometry: " + str(exc), "radial_material_side": None,
            "plus": {"xyz": None, "inside_count": None, "signed_radial_residual": None},
            "minus": {"xyz": None, "inside_count": None, "signed_radial_residual": None},
            "epsilon": None, "geometry_tolerance": tolerance, "numerical_margin": None,
            "clearance_lower_estimate": None}
