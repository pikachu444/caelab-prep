"""Shared synthetic inspection fixtures; no native CAD or SDK execution."""
import hashlib
import json
import math
from copy import deepcopy
from uuid import uuid4

from caelab_prep.adapters.gmsh_geometry import plan_cylinder_material_probe
from caelab_prep.application.geometry_inspection import read_geometry_inspection


def write_hole_inspection(hole, tmp_path):
    """A synthetic geometry graph for UI state checks, not an actual CAD solid."""
    data = hole
    surfaces, curves = data["surfaces"], data["curves"]
    cylinder = surfaces[0]
    volume = cylinder["orientation_by_volume"][0]["volume_uuid"]
    for index, surface in enumerate(surfaces, 1):
        surface.update(backend_tag=index, normal_basis="gmsh_face_oriented_no_volume_sign", sampling_status="unverified")
        surface["bbox"] = [0., 0., 0., 12., 8., 3.]
        surface["center"] = [6., 4., 1.5]
        surface["samples"] = []
        for loop_index, loop in enumerate(surface["curve_loops"], 1): loop["backend_tag"] = 10 * index + loop_index
    cylinder["samples"] = [{"uv": [math.pi, 2.5], "xyz": [5., 4., 1.5], "face_normal": [1., 0., 0.], "trim_count": 1}]
    for curve in curves:
        curve.setdefault("endpoints", [{"backend_tag": 500, "xyz": [7., 4., 0.]},
                                       {"backend_tag": 501, "xyz": [7., 4., 3.]}])
        curve["bbox"] = [0., 0., 0., 12., 8., 3.]
        curve["adjacent_surface_uuids"] = [surface["uuid"] for surface in surfaces
            if any(curve["backend_tag"] in map(abs, loop["curve_tags"]) for loop in surface["curve_loops"])]
    data["volumes"] = [{"uuid": volume, "backend_tag": 1, "bbox": [0., 0., 0., 12., 8., 3.],
                        "surface_uuids": [surface["uuid"] for surface in surfaces]}]
    source, xao, metadata = (tmp_path / name for name in ("synthetic.step", "geometry.xao", "metadata.json"))
    source.write_bytes(b"Synthetic UI source, no actual CAD")
    xao.write_bytes(b"Synthetic UI XAO, no native inspection")
    data.update(schema_version=1, source_kind="cad_geometry_inspection", backend={"name": "gmsh", "version": "synthetic"},
                source={"path": str(source), "captured_path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                assets={"xao": str(xao), "metadata": str(metadata)}, sdk_error_count=0, geometry_tolerance=1e-8)
    plan = plan_cylinder_material_probe(cylinder, surfaces, data["volumes"], curves, 1e-8, "mm")
    assert plan["status"] == "ready"
    plan.update(status="observed", radial_material_side="outward_side_is_material")
    plan["plus"]["inside_count"], plan["minus"]["inside_count"] = 1, 0
    data["cylinder_material_side_probes"] = [plan]
    metadata.write_text(json.dumps(data), encoding="utf-8")
    return read_geometry_inspection(metadata)


def material_inspection_data(tmp_path, geometry, *, probe_rows, policies):
    """Give synthetic analytic rows real UUIDs/assets for the evidence reader."""
    surfaces, volumes, curves = deepcopy(geometry)
    probes = deepcopy(probe_rows)
    identities = {row["uuid"]: str(uuid4()) for row in [*surfaces, *volumes]}
    for tag, face in enumerate(surfaces, 1):
        face.update(uuid=identities[face["uuid"]], backend_tag=tag,
                    center=face["samples"][0]["xyz"], normal_basis="gmsh_face_oriented_no_volume_sign",
                    sampling_status="unverified")
        face["samples"][0]["uv"] = [0., 0.]
        for use in face["orientation_by_volume"]:
            use["volume_uuid"] = identities[use["volume_uuid"]]
    for volume in volumes:
        members = [face for face in surfaces if face["uuid"] in [identities[value] for value in volume["surface_uuids"]]]
        volume.update(uuid=identities[volume["uuid"]],
            bbox=[min(face["bbox"][i] for face in members) for i in range(3)] +
                 [max(face["bbox"][i+3] for face in members) for i in range(3)],
            surface_uuids=[identities[value] for value in volume["surface_uuids"]])
    for curve in curves:
        curve["adjacent_surface_uuids"] = [identities[value] for value in curve["adjacent_surface_uuids"]]
        points = [row["xyz"] for row in curve["endpoints"]]
        curve["bbox"] = [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)]
    for rows in probes.values():
        for row in rows:
            for key in ("surface_uuid", "volume_uuid"):
                row[key] = identities.get(row[key], row[key])
    source, xao, metadata = (tmp_path / name for name in ("source.step", "geometry.xao", "metadata.json"))
    source.write_bytes(b"synthetic analytic reader source, not native CAD")
    xao.write_bytes(b"synthetic analytic reader XAO, not native CAD")
    data = {"schema_version": 1, "source_kind": "cad_geometry_inspection",
        "backend": {"name": "gmsh", "version": "fake"},
        "geometry_resource_uuid": str(uuid4()), "geometry_revision": 1, "length_unit": "mm",
        "source": {"path": str(source), "captured_path": str(source),
                   "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "assets": {"xao": str(xao), "metadata": str(metadata)}, "sdk_error_count": 0,
        "geometry_tolerance": 1e-8, "surfaces": surfaces, "volumes": volumes, "curves": curves,
        **deepcopy(policies), **probes}
    return data, metadata
