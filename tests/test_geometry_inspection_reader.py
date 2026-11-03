"""Geometry-only evidence cannot become a mesh or mutable document resource."""
import hashlib
import json
import math
from uuid import uuid4

import pytest

from caelab_prep.application.geometry_inspection import read_geometry_inspection
from caelab_prep.application.mesh_candidates import read_mesh_candidate
from caelab_prep.cae_core.errors import PrepError


@pytest.fixture
def evidence(tmp_path):
    source, xao, metadata = (tmp_path / name for name in ("source.step", "geometry.xao", "metadata.json"))
    source.write_bytes(b"self-authored reader fixture, not actual CAD")
    xao.write_bytes(b"self-authored XAO placeholder, no SDK verification")
    surface, volume = str(uuid4()), str(uuid4())
    data = {"schema_version": 1, "source_kind": "cad_geometry_inspection",
            "backend": {"name": "gmsh", "version": "fixture"},
            "geometry_resource_uuid": str(uuid4()), "geometry_revision": 1, "length_unit": "mm",
            "source": {"path": str(source), "captured_path": str(source),
                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
            "assets": {"xao": str(xao), "metadata": str(metadata)}, "sdk_error_count": 0,
            "surfaces": [{"uuid": surface, "backend_tag": 1, "bbox": [0, 0, 0, 1, 1, 1],
                          "center": [.5, .5, .5], "geometry_type": "Cylinder",
                          "orientation_by_volume": [{"volume_uuid": volume, "sign": -1}],
                          "curve_loops": [{"backend_tag": 1, "curve_tags": [1, -1]}],
                          "normal_basis": "gmsh_face_oriented_no_volume_sign", "sampling_status": "unverified",
                          "samples": [{"uv": [0, .5], "xyz": [1, 0, .5], "face_normal": [1, 0, 0], "trim_count": 1}]}],
            "volumes": [{"uuid": volume, "backend_tag": 1, "bbox": [0, 0, 0, 1, 1, 1],
                         "surface_uuids": [surface]}],
            "curves": [{"backend_tag": 1, "geometry_type": "Circle", "bbox": [0, 0, 0, 1, 1, 0],
                        "adjacent_surface_uuids": [surface], "endpoints": []}]}
    return data, metadata


def persist(data, metadata):
    metadata.write_text(json.dumps(data), encoding="utf-8")


def test_reads_detached_geometry_evidence_and_rechecks_every_asset(evidence):
    data, metadata = evidence
    persist(data, metadata)
    inspection = read_geometry_inspection(data)
    assert inspection.geometry_resource_uuid == data["geometry_resource_uuid"]
    assert inspection.geometry_revision == 1 and inspection.length_unit == "mm"
    assert {asset.kind for asset in inspection.assets} == {"source", "xao", "metadata"}
    detached = inspection.to_dict()
    detached["surfaces"][0]["samples"][0]["face_normal"][0] = -999
    assert inspection.to_dict() == data
    inspection.verify_assets()
    assert read_geometry_inspection(metadata).to_dict() == data
    with pytest.raises(PrepError):
        read_mesh_candidate(data)


@pytest.mark.parametrize("kind", ["source", "xao", "metadata"])
def test_any_asset_change_invalidates_the_retained_inspection(evidence, kind):
    data, metadata = evidence
    persist(data, metadata)
    inspection = read_geometry_inspection(data)
    path = next(asset.path for asset in inspection.assets if asset.kind == kind)
    from pathlib import Path
    Path(path).write_bytes(b"changed")
    with pytest.raises(PrepError) as exc:
        inspection.verify_assets()
    assert exc.value.code == "geometry_inspection_changed"


@pytest.mark.parametrize("change", [
    lambda d: d.update(source_kind="cad"),
    lambda d: d.update(mesh_uuid=str(uuid4())),
    lambda d: d["assets"].update(msh="pretend.msh"),
    lambda d: d.update(sdk_error_count=1),
    lambda d: d["source"].update(sha256="0" * 64),
    lambda d: d["surfaces"][0]["curve_loops"][0].update(curve_tags=[99]),
    lambda d: d["curves"][0].update(adjacent_surface_uuids=[]),
    lambda d: d["volumes"][0].update(surface_uuids=[]),
    lambda d: d["surfaces"][0]["orientation_by_volume"][0].update(sign=True),
    lambda d: d["surfaces"][0].update(sampling_status="verified"),
    lambda d: d["surfaces"][0].update(normal_basis="material_outward"),
    lambda d: d["surfaces"][0]["samples"][0].update(trim_count=True),
    lambda d: d["surfaces"][0]["samples"][0].update(face_normal=[float("nan"), 0, 0]),
    lambda d: d["surfaces"][0].update(samples={}),
    lambda d: d["surfaces"][0].update(samples=""),
    lambda d: d["surfaces"][0].update(samples=[None]),
    lambda d: d["curves"][0].update(endpoints={}),
    lambda d: d["curves"][0].update(endpoints=""),
    lambda d: d["curves"][0].update(endpoints=[[]]),
    lambda d: d["surfaces"][0].update(orientation_by_volume={}),
    lambda d: d["surfaces"][0].update(curve_loops=""),
    lambda d: d["surfaces"][0]["curve_loops"][0].update(curve_tags={}),
    lambda d: d["curves"][0].update(adjacent_surface_uuids=""),
])
def test_malformed_or_overclaimed_geometry_evidence_is_rejected(evidence, change):
    data, metadata = evidence
    change(data)
    persist(data, metadata)
    with pytest.raises(PrepError):
        read_geometry_inspection(metadata)


def test_dict_must_match_the_actual_metadata_file(evidence):
    data, metadata = evidence
    persist(data, metadata)
    data["geometry_revision"] = 2
    with pytest.raises(PrepError, match="differs"):
        read_geometry_inspection(data)


def test_metadata_replacement_between_parse_and_hash_is_rejected(evidence, monkeypatch):
    from caelab_prep.application import geometry_inspection as reader
    data, metadata = evidence
    persist(data, metadata)
    original_sha = reader._sha

    def replacing_sha(path):
        if path == metadata:
            replacement = {**data, "geometry_revision": 2}
            persist(replacement, metadata)
        return original_sha(path)

    monkeypatch.setattr(reader, "_sha", replacing_sha)
    with pytest.raises(PrepError, match="changed while"):
        read_geometry_inspection(metadata)


def test_volume_without_a_boundary_is_not_a_valid_geometry_inspection(evidence):
    data, metadata = evidence
    data["volumes"][0]["surface_uuids"] = []
    data["surfaces"][0]["orientation_by_volume"] = []
    persist(data, metadata)
    with pytest.raises(PrepError, match="nonempty boundary"):
        read_geometry_inspection(metadata)


def test_duplicate_volume_boundaries_are_not_hidden_by_set_comparison(evidence):
    data, metadata = evidence
    data["volumes"][0]["surface_uuids"] *= 2
    persist(data, metadata)
    with pytest.raises(PrepError, match="duplicate surface"):
        read_geometry_inspection(metadata)


@pytest.fixture
def material_evidence(evidence):
    from caelab_prep.adapters.gmsh_geometry import plan_cylinder_material_probe
    from test_geometry_inspection import probe_geometry
    data, metadata = evidence
    surfaces, volumes, curves = probe_geometry()
    cylinder, top, bottom = surfaces
    volume = volumes[0]["uuid"]
    for index, surface in enumerate(surfaces, 1):
        surface["backend_tag"] = index
        surface["center"] = [(a + b) / 2 for a, b in zip(surface["bbox"][:3], surface["bbox"][3:])]
        surface.setdefault("orientation_by_volume", [{"volume_uuid": volume, "sign": 1}])
        surface.setdefault("samples", [])
        surface.update(normal_basis="gmsh_face_oriented_no_volume_sign", sampling_status="unverified")
    cylinder["samples"][0].update(uv=[math.pi, 1.5], face_normal=[-1., 0., 0.])
    top["curve_loops"] = [{"backend_tag": 42, "curve_tags": [11]}]
    bottom["curve_loops"] = [{"backend_tag": 43, "curve_tags": [12]}]
    for index, curve in enumerate(curves):
        curve["bbox"] = cylinder["bbox"][:]
        curve.setdefault("endpoints", [])
        if index < 2:
            curve["adjacent_surface_uuids"] = [cylinder["uuid"], surfaces[index + 1]["uuid"]]
    volumes[0]["bbox"] = cylinder["bbox"][:]
    data.update(surfaces=surfaces, volumes=volumes, curves=curves)
    data["geometry_tolerance"] = 1e-8
    plan = plan_cylinder_material_probe(cylinder, surfaces, volumes, curves, 1e-8, "mm")
    assert plan["status"] == "ready"
    plan.update(status="observed", reason=None, radial_material_side="inward_side_is_material")
    plan["plus"]["inside_count"], plan["minus"]["inside_count"] = 0, 1
    data["cylinder_material_side_probes"] = [plan]
    return data, metadata


def test_observed_material_side_retains_both_raw_counts_and_the_margins(material_evidence):
    data, metadata = material_evidence
    persist(data, metadata)
    assert read_geometry_inspection(metadata).to_dict() == data


@pytest.mark.parametrize("change", [
    lambda d: d["cylinder_material_side_probes"][0]["plus"].update(inside_count=1),
    lambda d: d["cylinder_material_side_probes"][0]["plus"].update(inside_count=True),
    lambda d: d["cylinder_material_side_probes"][0]["minus"].update(signed_radial_residual=.01),
    lambda d: d["cylinder_material_side_probes"][0]["plus"].update(xyz=[1., 0., .5]),
    lambda d: d["cylinder_material_side_probes"][0].update(epsilon=1e-12),
    lambda d: d["cylinder_material_side_probes"][0].update(numerical_margin=1.),
    lambda d: d["cylinder_material_side_probes"][0].update(volume_uuid=str(uuid4())),
    lambda d: d["cylinder_material_side_probes"].append(d["cylinder_material_side_probes"][0].copy()),
    lambda d: d.update(length_unit="unknown"),
    lambda d: d["surfaces"][0]["parametric_bounds"]["maximum"].__setitem__(0, math.pi),
    lambda d: d["surfaces"][0].pop("analytic_properties"),
    lambda d: d["curves"][0]["parametric_bounds"]["maximum"].__setitem__(0, math.pi),
    lambda d: d["cylinder_material_side_probes"][0]["minus"].update(xyz=d["cylinder_material_side_probes"][0]["plus"]["xyz"][:]),
    lambda d: d["cylinder_material_side_probes"][0]["plus"].update(signed_radial_residual=.5),
])
def test_partial_or_contradictory_material_side_observations_are_rejected(material_evidence, change):
    data, metadata = material_evidence
    change(data)
    persist(data, metadata)
    with pytest.raises(PrepError):
        read_geometry_inspection(metadata)


def large_coordinate_plan(data):
    from caelab_prep.adapters.gmsh_geometry import plan_cylinder_material_probe
    cylinder, top, bottom = data["surfaces"]
    base, radius = 1e12, 36.
    point = [radius / math.sqrt(2), radius / math.sqrt(2), base]
    cylinder["analytic_properties"]["reals"] = [0., 0., base, 0., 0., 1., radius]
    cylinder["samples"][0]["xyz"] = point
    cylinder["parametric_bounds"] = {"minimum": [0., -100.], "maximum": [math.tau, 100.]}
    cylinder["bbox"] = [-radius, -radius, base - 100., radius, radius, base + 100.]
    for surface, z, sign in ((top, base + 100., 1.), (bottom, base - 100., -1.)):
        surface["analytic_properties"]["reals"] = [0., 0., sign, -sign * z]
        surface["bbox"] = [-radius, -radius, z, radius, radius, z]
    for curve in data["curves"][:2]:
        curve["length"] = math.tau * radius
        curve["bbox"] = cylinder["bbox"][:]
        for endpoint in curve["endpoints"]:
            endpoint["xyz"] = [radius, 0., base + 100.]
    data["volumes"][0]["bbox"] = cylinder["bbox"][:]
    plan = plan_cylinder_material_probe(cylinder, data["surfaces"], data["volumes"], data["curves"], 1e-8, "mm")
    assert plan["status"] == "ready" and plan["numerical_margin"] == .5
    assert plan["epsilon"] == .5625
    return plan, point


def test_coordinate_margin_cannot_turn_one_near_tangent_point_into_opposite_sides(material_evidence):
    data, metadata = material_evidence
    plan, point = large_coordinate_plan(data)
    plan.update(status="observed", radial_material_side="outward_side_is_material")
    shared = [point[0] + .1, point[1] - .1, point[2] + .49]
    plan["plus"].update(xyz=shared[:], inside_count=1)
    plan["minus"].update(xyz=shared[:], inside_count=0)
    data["cylinder_material_side_probes"] = [plan]
    persist(data, metadata)
    with pytest.raises(PrepError, match="Stored probe coordinates"):
        read_geometry_inspection(metadata)


def test_reported_zero_margin_cannot_lower_the_computed_safety_floor(material_evidence):
    data, metadata = material_evidence
    plan, point = large_coordinate_plan(data)
    plan.update(status="observed", radial_material_side="outward_side_is_material", numerical_margin=0.)
    for side, sign, count in (("plus", 1, 1), ("minus", -1, 0)):
        radial = (36. + sign * .07) / math.sqrt(2)
        plan[side].update(xyz=[radial, radial, point[2]], inside_count=count)
    data["cylinder_material_side_probes"] = [plan]
    persist(data, metadata)
    with pytest.raises(PrepError):
        read_geometry_inspection(metadata)
