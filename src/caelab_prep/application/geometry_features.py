"""Conservative hole and blend candidates from analytic CAD evidence.

The first supported family is an axis-aligned full cylindrical wall ending in
planar disks or rectangular caps with one circular opening. Supported blend
strips are finite quarter cylinders or cones with verified planar supports.
This module does not query SDKs, alter B-Rep or configure meshing.
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


def _recognize_blends(inspection, *, length_tolerance, angular_tolerance, radius_threshold, conical):
    """Share observation, signed-G1 and provenance checks across supported strips."""
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
    if conical:
        from ..adapters.gmsh_geometry import conical_blend_shape
        shape_function, surface_type, probe_key = conical_blend_shape, "Cone", "conical_material_side_probes"
        kind, normal_key = "conical_blend_candidate", "cone_material_normal"
        scope = "mm axis-aligned finite quarter cones with trapezoidal supports; maximum finite principal radius and material-oriented G1; candidates only"
    else:
        shape_function, surface_type, probe_key = cylindrical_blend_shape, "Cylinder", "blend_material_side_probes"
        kind, normal_key = "cylindrical_blend_candidate", "cylinder_material_normal"
        scope = "mm axis-aligned quarter cylinders with rectangular supports and material-oriented G1 joins; candidates only"
    inspection.verify_assets()
    data = inspection.to_dict()
    surfaces = {row["uuid"]: row for row in data["surfaces"]}
    curves = {row["backend_tag"]: row for row in data["curves"]}
    probes = {row["surface_uuid"]: row for row in data.get(probe_key, [])}
    features, unclassified = [], []
    for face in surfaces.values():
        if face["geometry_type"] != surface_type:
            continue
        shape = shape_function(face, data["surfaces"], data["volumes"], data["curves"],
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
                from ..adapters.gmsh_geometry import analytic_unit_normal
                for support_id, tag in zip(shape["support_surface_uuids"], shape["shared_line_tags"]):
                    ends = curves[tag]["endpoints"]
                    point = [a / 2 + b / 2 for a, b in zip(ends[0]["xyz"], ends[1]["xyz"])]
                    reference = analytic_unit_normal(face, point)
                    support_reference = analytic_unit_normal(surfaces[support_id], point)
                    if reference is None or support_reference is None:
                        reason = "analytic_normal_unverified"
                        break
                    blend_normal = [value * probes[identity]["material_normal_sign"] for value in reference]
                    plane_normal = [value * probes[support_id]["material_normal_sign"] for value in support_reference]
                    dot = max(-1., min(1., math.fsum(a * b for a, b in zip(blend_normal, plane_normal))))
                    joins.append({"support_surface_uuid": support_id, "shared_line_tag": tag,
                        "point": point, normal_key: blend_normal,
                        "support_material_normal": plane_normal, "signed_normal_dot": dot,
                        "angle_radians": math.acos(dot)})
                if reason is None and any(join["signed_normal_dot"] < math.cos(angular_tolerance) for join in joins):
                    reason = "material_normals_not_g1"
                elif reason is None and radius_threshold is not None and shape["radius"] > radius_threshold:
                    reason = "radius_above_threshold"
        if reason:
            unclassified.append({"surface_uuid": identity, "reason": reason, "tangent_edges": joins})
            continue
        end_arcs = []
        for tag in shape["evidence"]["end_arc_tags"]:
            endpoints = [row["xyz"] for row in curves[tag]["endpoints"]]
            center = list(shape["axis_point"])
            center[shape["axis_index"]] = endpoints[0][shape["axis_index"]]
            arc = {"curve_tag": tag, "center": center, "endpoints": endpoints}
            if conical:
                section = min(shape["end_sections"], key=lambda row: abs(row["axial_coordinate"] - center[shape["axis_index"]]))
                arc.update(radius=section["radius"], curvature_radius=section["curvature_radius"])
            end_arcs.append(arc)
        feature = {"kind": kind, "qualification": "candidate",
            "surface_uuid": identity, "volume_uuid": shape["volume_uuid"], "radius": shape["radius"],
            "axis_point": shape["axis_point"], "axis_direction": face["analytic_properties"]["reals"][3:6],
            "axial_range": shape["axial_range"], "end_arcs": end_arcs, "tangent_edges": joins,
            "shape_evidence": shape["evidence"], "material_side_evidence": [probes[key] for key in ids]}
        if conical:
            feature.update(radius_metric="max_finite_principal_radius", semi_angle=shape["semi_angle"],
                finite_principal_radius_range=shape["curvature_radius_range"],
                cross_section_radius_range=sorted(row["radius"] for row in shape["end_sections"]))
        features.append(feature)
    inspection.verify_assets()
    return {"geometry_resource_uuid": inspection.geometry_resource_uuid,
            "geometry_revision": inspection.geometry_revision, "length_unit": inspection.length_unit,
            "assets": [asdict(asset) for asset in inspection.assets], "length_tolerance": length_tolerance,
            "angular_tolerance_radians": angular_tolerance, "radius_threshold": radius_threshold,
            "features": features, "unclassified": unclassified, "modifications": 0,
            "scope": scope}


def recognize_cylindrical_blends(inspection: GeometryInspection, *, length_tolerance,
                                 angular_tolerance=1e-6, radius_threshold=None):
    """Review signed G1 on connected quarter cylinders with rectangular supports.

    This yields geometric candidates, without inferring CAD history, authorizing
    edge suppression or changing the B-Rep.
    """
    return _recognize_blends(inspection, length_tolerance=length_tolerance,
        angular_tolerance=angular_tolerance, radius_threshold=radius_threshold, conical=False)


def recognize_conical_blends(inspection: GeometryInspection, *, length_tolerance,
                            angular_tolerance=1e-6, radius_threshold=None):
    """Review finite quarter cones using max(r/abs(cos(alpha))) as radius.

    Cross-section radii are reported separately. The result is a candidate;
    original CAD, active document and mesh are unchanged.
    """
    return _recognize_blends(inspection, length_tolerance=length_tolerance,
        angular_tolerance=angular_tolerance, radius_threshold=radius_threshold, conical=True)


def recognize_geometry_features(inspection: GeometryInspection, *, length_tolerance,
                                angular_tolerance=1e-6, blend_radius_threshold=None):
    """Combine the supported read-only reviews without querying the SDK."""
    report = recognize_cylindrical_holes(inspection, length_tolerance=length_tolerance)
    cylinders = recognize_cylindrical_blends(inspection, length_tolerance=length_tolerance,
        angular_tolerance=angular_tolerance, radius_threshold=blend_radius_threshold)
    cones = recognize_conical_blends(inspection, length_tolerance=length_tolerance,
        angular_tolerance=angular_tolerance, radius_threshold=blend_radius_threshold)
    report["features"].extend([*cylinders["features"], *cones["features"]])
    classified = {feature["surface_uuid"] for feature in report["features"]}
    cylinder_reasons = {row["surface_uuid"]: row["reason"] for row in cylinders["unclassified"]}
    report["unclassified"] = [{**row, "blend_reason": cylinder_reasons.get(row["surface_uuid"])}
        for row in report["unclassified"] if row["surface_uuid"] not in classified]
    report["unclassified"].extend(row for row in cones["unclassified"] if row["surface_uuid"] not in classified)
    report["hole_review"] = {"scope": report["scope"]}
    for key, review in (("blend_review", cylinders), ("conical_review", cones)):
        report[key] = {name: review[name] for name in ("scope", "radius_threshold", "angular_tolerance_radians")}
    report["scope"] = "Supported analytic hole and blend candidates; no CAD, document or mesh modifications"
    inspection.verify_assets()
    return report
