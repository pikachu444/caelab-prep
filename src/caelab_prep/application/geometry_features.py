"""Conservative hole candidates from bounded analytic CAD evidence.

The first supported family is an axis-aligned full cylindrical wall ending in
planar disks or rectangular caps with one circular opening. Other trims remain
unclassified. This module does not query SDKs, alter B-Rep or configure meshing.
"""
from collections import Counter
from dataclasses import asdict
import math

from .geometry_inspection import GeometryInspection
from ..cae_core.errors import PrepError


def _basis(vector):
    axes = [index for index, value in enumerate(vector) if value != 0]
    return axes[0] if len(axes) == 1 and abs(vector[axes[0]]) == 1 else None


def _rectangle(curve_tags, curves, axis, center, radius, tolerance):
    """Require four actual shared-vertex lines, not a bounding-box heuristic."""
    if len(curve_tags) != 4 or len(set(map(abs, curve_tags))) != 4:
        return None
    vertices, degrees, edges = {}, Counter(), []
    for tag in curve_tags:
        curve = curves[abs(tag)]
        endpoints = curve["endpoints"]
        if curve["geometry_type"] != "Line" or len(endpoints) != 2:
            return None
        first, second = (point["backend_tag"] for point in endpoints)
        if first == second:
            return None
        for point in endpoints:
            vertex, xyz = point["backend_tag"], tuple(point["xyz"])
            if vertex in vertices and vertices[vertex] != xyz:
                return None
            vertices[vertex] = xyz
            degrees[vertex] += 1
        edges.append((first, second))
    if (len(vertices) != 4 or set(degrees.values()) != {2}
            or len({tuple(sorted(edge)) for edge in edges}) != 4):
        return None
    plane_axes = [index for index in range(3) if index != axis]
    if any(abs(point[axis] - center[axis]) > tolerance for point in vertices.values()):
        return None
    low = [min(point[index] for point in vertices.values()) for index in plane_axes]
    high = [max(point[index] for point in vertices.values()) for index in plane_axes]
    if any(not a + radius + tolerance < center[index] < b - radius - tolerance
           for index, a, b in zip(plane_axes, low, high)):
        return None
    corners = {}
    for vertex, point in vertices.items():
        corner = []
        for index, a, b in zip(plane_axes, low, high):
            if abs(point[index] - a) <= tolerance:
                corner.append(0)
            elif abs(point[index] - b) <= tolerance:
                corner.append(1)
            else:
                return None
        corners[vertex] = tuple(corner)
    if set(corners.values()) != {(0, 0), (0, 1), (1, 0), (1, 1)}:
        return None
    if any(sum(a != b for a, b in zip(corners[first], corners[second])) != 1 for first, second in edges):
        return None
    lengths = [b - a for a, b in zip(low, high)]
    return math.prod(lengths), 2 * sum(lengths)


def _cap(circle, cylinder, volume_uuid, surfaces, curves, axis, origin, radius, tolerance):
    adjacent = circle["adjacent_surface_uuids"]
    if len(adjacent) != 2 or len(set(adjacent)) != 2 or cylinder not in adjacent:
        return None
    cap = surfaces[next(identity for identity in adjacent if identity != cylinder)]
    if (cap["geometry_type"] != "Plane"
            or [use["volume_uuid"] for use in cap["orientation_by_volume"]] != [volume_uuid]):
        return None
    coefficients = cap["analytic_properties"]["reals"]
    if len(coefficients) != 4 or _basis(coefficients[:3]) != axis:
        return None
    center = list(origin)
    center[axis] = -coefficients[3] / coefficients[axis]
    for point in circle["endpoints"]:
        if abs(point["xyz"][axis] - center[axis]) > tolerance:
            return None
    loops = cap["curve_loops"]
    circular = [loop for loop in loops if list(map(abs, loop["curve_tags"])) == [circle["backend_tag"]]]
    if len(circular) != 1:
        return None
    disk_area = math.pi * radius * radius
    remaining = [loop for loop in loops if loop is not circular[0]]
    if not remaining:
        expected_area, perimeter, kind = disk_area, 2 * math.pi * radius, "closed_disk"
    elif len(remaining) == 1:
        rectangle = _rectangle(remaining[0]["curve_tags"], curves, axis, center, radius, tolerance)
        if rectangle is None:
            return None
        rectangle_area, perimeter = rectangle
        expected_area, kind = rectangle_area - disk_area, "rectangular_opening"
        perimeter += 2 * math.pi * radius
    else:
        return None
    if not math.isfinite(expected_area) or abs(cap["area"] - expected_area) > tolerance * (perimeter + tolerance):
        return None
    return {"surface_uuid": cap["uuid"], "circle_tag": circle["backend_tag"],
            "kind": kind, "center": center}


def recognize_cylindrical_holes(inspection: GeometryInspection, *, length_tolerance):
    """Return reviewable through/blind candidates in the stated narrow family.

    A local radial material-side witness is required; raw normal and volume
    sign are never multiplied. Detection does not authorize defeaturing or
    washer generation, infer design history, or change an active document.
    """
    if not isinstance(inspection, GeometryInspection):
        raise PrepError("geometry_feature_input", "Read a geometry inspection before recognizing features.")
    try:
        length_tolerance = float(length_tolerance) if type(length_tolerance) in (int, float) else float("nan")
    except OverflowError:
        length_tolerance = float("inf")
    if not math.isfinite(length_tolerance) or length_tolerance <= 0:
        raise PrepError("geometry_feature_tolerance", "Declare a finite positive tolerance in the inspected length unit.")
    inspection.verify_assets()
    data = inspection.to_dict()
    surfaces = {row["uuid"]: row for row in data["surfaces"]}
    curves = {row["backend_tag"]: row for row in data["curves"]}
    probes = {row["surface_uuid"]: row for row in data.get("cylinder_material_side_probes", [])}
    features, unclassified = [], []
    for surface in surfaces.values():
        if surface["geometry_type"] != "Cylinder":
            continue
        identity = surface["uuid"]
        reason = None
        probe = probes.get(identity)
        if inspection.length_unit == "unknown":
            reason = "unknown_coordinate_unit"
        elif probe is None or probe["status"] != "observed":
            reason = "material_side_unverified"
        elif probe["radial_material_side"] != "outward_side_is_material":
            reason = "exterior_cylindrical_wall"
        if reason:
            unclassified.append({"surface_uuid": identity, "reason": reason})
            continue
        properties = surface["analytic_properties"]["reals"]
        axis = _basis(properties[3:6]) if len(properties) == 7 else None
        radius = properties[6] if len(properties) == 7 else 0
        tags = {abs(tag) for loop in surface["curve_loops"] for tag in loop["curve_tags"]}
        circles = [curves[tag] for tag in sorted(tags) if curves[tag]["geometry_type"] == "Circle"]
        if axis is None or radius <= 0 or len(circles) != 2:
            unclassified.append({"surface_uuid": identity, "reason": "unsupported_cylindrical_trim"})
            continue
        caps = [_cap(circle, identity, probe["volume_uuid"], surfaces, curves,
                     axis, properties[:3], radius, length_tolerance) for circle in circles]
        if any(cap is None for cap in caps) or abs(caps[0]["center"][axis] - caps[1]["center"][axis]) <= length_tolerance:
            unclassified.append({"surface_uuid": identity, "reason": "opening_or_cap_unverified"})
            continue
        openings = sum(cap["kind"] == "rectangular_opening" for cap in caps)
        if openings == 0:
            unclassified.append({"surface_uuid": identity, "reason": "enclosed_cylindrical_cavity"})
            continue
        features.append({"kind": "through_hole_candidate" if openings == 2 else "blind_hole_candidate",
                         "surface_uuid": identity, "volume_uuid": probe["volume_uuid"], "radius": radius,
                         "axis_point": properties[:3], "axis_direction": properties[3:6], "caps": caps,
                         "qualification": "candidate", "material_side_evidence": probe})
    inspection.verify_assets()
    return {"geometry_resource_uuid": inspection.geometry_resource_uuid,
            "geometry_revision": inspection.geometry_revision, "length_unit": inspection.length_unit,
            "assets": [asdict(asset) for asset in inspection.assets], "length_tolerance": length_tolerance,
            "features": features, "unclassified": unclassified, "modifications": 0,
            "scope": "axis-aligned full cylinders with planar disks or one-hole rectangular caps; candidates only"}
