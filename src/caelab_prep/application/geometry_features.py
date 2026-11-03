"""Conservative hole and cylindrical blend candidates from analytic CAD evidence.

The first supported family is an axis-aligned full cylindrical wall ending in
planar disks or rectangular caps with one circular opening. Other trims remain
unclassified. This module does not query SDKs, alter B-Rep or configure meshing.
"""
from dataclasses import asdict
import math

from ..adapters.gmsh_topology import rectangular_wire
from ..adapters.gmsh_geometry import cylindrical_blend_shape
from .geometry_inspection import GeometryInspection
from ..cae_core.errors import PrepError


def _basis(vector):
    axes = [index for index, value in enumerate(vector) if value != 0]
    return axes[0] if len(axes) == 1 and abs(vector[axes[0]]) == 1 else None


def _rectangle(curve_tags, curves, axis, center, radius, tolerance):
    """Require four actual shared-vertex lines, not a bounding-box heuristic."""
    wire = rectangular_wire(curve_tags, curves, axis, center[axis], tolerance)
    if wire is None:
        return None
    if any(not a + radius + tolerance < center[index] < b - radius - tolerance
           for index, a, b in zip(wire["plane_axes"], wire["minimum"], wire["maximum"])):
        return None
    return wire["area"], wire["perimeter"]


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


def recognize_cylindrical_blends(inspection: GeometryInspection, *, length_tolerance,
                                 angular_tolerance=1e-6, radius_threshold=None):
    """Review material-oriented G1 joins in the first quarter-cylinder family.

    A connected analytic strip and rectangular supports make each signed normal
    constant along its shared generatrix. The result is a geometric candidate,
    not CAD history or permission to suppress an edge or alter the B-Rep.
    """
    if not isinstance(inspection, GeometryInspection):
        raise PrepError("geometry_feature_input", "Read a geometry inspection before recognizing features.")
    for value in (length_tolerance, angular_tolerance):
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and value > 0
        except OverflowError:
            valid = False
        if not valid:
            raise PrepError("geometry_feature_tolerance", "Declare finite positive length and angular tolerances.")
    if not 1e-6 <= angular_tolerance < math.pi / 2:
        raise PrepError("geometry_feature_tolerance", "Angular tolerance must be at least 1e-6 and below pi/2 radians.")
    if radius_threshold is not None:
        try:
            valid = type(radius_threshold) in (int, float) and math.isfinite(radius_threshold) and radius_threshold >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise PrepError("geometry_feature_threshold", "Declare a finite nonnegative radius threshold in mm.")
    inspection.verify_assets()
    data = inspection.to_dict()
    surfaces = {row["uuid"]: row for row in data["surfaces"]}
    curves = {row["backend_tag"]: row for row in data["curves"]}
    probes = {row["surface_uuid"]: row for row in data.get("blend_material_side_probes", [])}
    features, unclassified = [], []
    for face in surfaces.values():
        if face["geometry_type"] != "Cylinder":
            continue
        shape = cylindrical_blend_shape(face, data["surfaces"], data["volumes"], data["curves"],
            data["geometry_tolerance"], data["length_unit"], length_tolerance=length_tolerance,
            angular_tolerance=angular_tolerance)
        identity, reason = face["uuid"], shape["reason"]
        joins = []
        if shape["eligible"]:
            ids = [identity, *shape["support_surface_uuids"]]
            if any(probes.get(key, {}).get("status") != "observed"
                   or probes[key].get("volume_uuid") != shape["volume_uuid"]
                   or type(probes[key].get("material_normal_sign")) is not int
                   or probes[key]["material_normal_sign"] not in (-1, 1) for key in ids):
                reason = "material_side_unverified"
            else:
                axis, origin = shape["axis_index"], shape["axis_point"]
                for support_id, tag in zip(shape["support_surface_uuids"], shape["shared_line_tags"]):
                    ends = curves[tag]["endpoints"]
                    point = [a / 2 + b / 2 for a, b in zip(ends[0]["xyz"], ends[1]["xyz"])]
                    radial = [0. if i == axis else point[i] - origin[i] for i in range(3)]
                    radial_length = math.hypot(*radial)
                    cylinder_normal = [value / radial_length * probes[identity]["material_normal_sign"] for value in radial]
                    coefficients = surfaces[support_id]["analytic_properties"]["reals"][:3]
                    norm = math.hypot(*coefficients)
                    plane_normal = [value / norm * probes[support_id]["material_normal_sign"] for value in coefficients]
                    dot = max(-1., min(1., sum(a * b for a, b in zip(cylinder_normal, plane_normal))))
                    joins.append({"support_surface_uuid": support_id, "shared_line_tag": tag,
                        "point": point, "cylinder_material_normal": cylinder_normal,
                        "support_material_normal": plane_normal, "signed_normal_dot": dot,
                        "angle_radians": math.acos(dot)})
                if any(join["signed_normal_dot"] < math.cos(angular_tolerance) for join in joins):
                    reason = "material_normals_not_g1"
                elif radius_threshold is not None and shape["radius"] > radius_threshold:
                    reason = "radius_above_threshold"
        if reason:
            unclassified.append({"surface_uuid": identity, "reason": reason, "tangent_edges": joins})
            continue
        end_arcs = []
        for tag in shape["evidence"]["end_arc_tags"]:
            endpoints = [row["xyz"] for row in curves[tag]["endpoints"]]
            center = list(shape["axis_point"])
            center[shape["axis_index"]] = endpoints[0][shape["axis_index"]]
            end_arcs.append({"curve_tag": tag, "center": center, "endpoints": endpoints})
        features.append({"kind": "cylindrical_blend_candidate", "qualification": "candidate",
            "surface_uuid": identity, "volume_uuid": shape["volume_uuid"], "radius": shape["radius"],
            "axis_point": shape["axis_point"], "axis_direction": face["analytic_properties"]["reals"][3:6],
            "axial_range": shape["axial_range"], "end_arcs": end_arcs, "tangent_edges": joins,
            "shape_evidence": shape["evidence"], "material_side_evidence": [probes[key] for key in ids]})
    inspection.verify_assets()
    return {"geometry_resource_uuid": inspection.geometry_resource_uuid,
            "geometry_revision": inspection.geometry_revision, "length_unit": inspection.length_unit,
            "assets": [asdict(asset) for asset in inspection.assets], "length_tolerance": length_tolerance,
            "angular_tolerance_radians": angular_tolerance, "radius_threshold": radius_threshold,
            "features": features, "unclassified": unclassified, "modifications": 0,
            "scope": "mm axis-aligned quarter cylinders with rectangular supports and material-oriented G1 joins; candidates only"}
