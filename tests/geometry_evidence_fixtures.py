"""Shared synthetic inspection fixtures; no native CAD or SDK execution."""
import hashlib
import json
import math

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
