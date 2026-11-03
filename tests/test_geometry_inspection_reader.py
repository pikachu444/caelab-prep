"""Geometry-only evidence cannot become a mesh or mutable document resource."""
import hashlib
import json
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
