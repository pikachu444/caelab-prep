"""Pure/fake material-oriented blend classification; no native CAD evidence."""
from copy import deepcopy
import hashlib
import json
import math
from uuid import uuid4

import pytest

from caelab_prep.adapters import gmsh_worker
from caelab_prep.adapters.gmsh_geometry import BLEND_PROBE_POLICY
from caelab_prep.application.geometry_features import recognize_cylindrical_blends
from caelab_prep.application.geometry_inspection import read_geometry_inspection
from caelab_prep.cae_core.errors import PrepError
from test_blend_backend import blend_scene, membership


def blend_evidence(tmp_path, *, cusp=False, axis_sign=1):
    surfaces, volumes, curves = blend_scene(cusp=cusp, axis_sign=axis_sign)
    identities = {row["uuid"]: str(uuid4()) for row in [*surfaces, *volumes]}
    for tag, face in enumerate(surfaces, 1):
        face.update(uuid=identities[face["uuid"]], backend_tag=tag,
                    center=face["samples"][0]["xyz"], normal_basis="gmsh_face_oriented_no_volume_sign",
                    sampling_status="unverified")
        face["samples"][0]["uv"] = [0., 0.]
        for use in face["orientation_by_volume"]:
            use["volume_uuid"] = identities[use["volume_uuid"]]
    for volume in volumes:
        volume.update(uuid=identities[volume["uuid"]], bbox=[0., 0., 0., 12., 8., 3.],
                      surface_uuids=[identities[value] for value in volume["surface_uuids"]])
    for curve in curves:
        curve["adjacent_surface_uuids"] = [identities[value] for value in curve["adjacent_surface_uuids"]]
        points = [row["xyz"] for row in curve["endpoints"]]
        curve["bbox"] = [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)]
    sdk, calls = membership(cusp=cusp)
    probes = gmsh_worker._blend_material_side_probes(sdk, surfaces, volumes, curves, 1e-8, "mm")
    assert len(calls) == 6  # Fake membership only, never an SDK execution.
    source, xao, metadata = (tmp_path / name for name in ("source.step", "geometry.xao", "metadata.json"))
    source.write_bytes(b"synthetic blend reader source, not native CAD")
    xao.write_bytes(b"synthetic blend reader XAO, not native CAD")
    data = {"schema_version": 1, "source_kind": "cad_geometry_inspection",
        "backend": {"name": "gmsh", "version": "fake"},
        "geometry_resource_uuid": str(uuid4()), "geometry_revision": 1, "length_unit": "mm",
        "source": {"path": str(source), "captured_path": str(source),
                   "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "assets": {"xao": str(xao), "metadata": str(metadata)}, "sdk_error_count": 0,
        "geometry_tolerance": 1e-8, "surfaces": surfaces, "volumes": volumes, "curves": curves,
        "blend_probe_policy": deepcopy(BLEND_PROBE_POLICY), "blend_material_side_probes": probes}
    return data, metadata


def persist(data, metadata):
    metadata.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    return read_geometry_inspection(metadata)


@pytest.mark.parametrize("axis_sign", [1, -1])
@pytest.mark.parametrize("cusp", [False, True])
def test_oriented_material_normals_distinguish_the_same_tangent_shape(tmp_path, cusp, axis_sign):
    data, metadata = blend_evidence(tmp_path, cusp=cusp, axis_sign=axis_sign)
    before = deepcopy(data)
    inspection = persist(data, metadata)
    report = recognize_cylindrical_blends(inspection, length_tolerance=1e-6)
    assert report["modifications"] == 0 and data == before
    assert report["assets"] and report["geometry_resource_uuid"] == data["geometry_resource_uuid"]
    joins = (report["unclassified"][0] if cusp else report["features"][0])["tangent_edges"]
    assert len(joins) == 2
    assert [join["signed_normal_dot"] for join in joins] == ([-1., -1.] if cusp else [1., 1.])
    if cusp:
        assert report["features"] == [] and report["unclassified"][0]["reason"] == "material_normals_not_g1"
    else:
        feature, = report["features"]
        assert feature["kind"] == "cylindrical_blend_candidate" and feature["radius"] == 1
        assert feature["qualification"] == "candidate" and feature["axial_range"] == [0., 3.]
        assert len(feature["end_arcs"]) == 2 and all(len(arc["endpoints"]) == 2 for arc in feature["end_arcs"])
        assert all(join["angle_radians"] == 0 for join in joins)


@pytest.mark.parametrize("threshold,count", [(0, 0), (.999999, 0), (1., 1), (2., 1), (None, 1)])
def test_radius_threshold_is_inclusive_without_geometry_changes(tmp_path, threshold, count):
    data, metadata = blend_evidence(tmp_path)
    report = recognize_cylindrical_blends(persist(data, metadata), length_tolerance=1e-6, radius_threshold=threshold)
    assert len(report["features"]) == count and report["modifications"] == 0
    if not count:
        assert report["unclassified"][0]["reason"] == "radius_above_threshold"


def test_missing_material_observations_cannot_be_replaced_by_raw_normals(tmp_path):
    data, metadata = blend_evidence(tmp_path)
    data.pop("blend_material_side_probes"); data.pop("blend_probe_policy")
    report = recognize_cylindrical_blends(persist(data, metadata), length_tolerance=1e-6)
    assert report["features"] == [] and report["unclassified"][0]["reason"] == "material_side_unverified"


@pytest.mark.parametrize("field,value", [("length_tolerance", 0), ("length_tolerance", True),
    ("angular_tolerance", 0), ("angular_tolerance", math.pi/2), ("angular_tolerance", 1e-7),
    ("angular_tolerance", float("nan")), ("radius_threshold", -1), ("radius_threshold", True),
    ("radius_threshold", float("inf")), ("radius_threshold", 10**1000)])
def test_invalid_tolerances_and_thresholds_fail_at_boundary(tmp_path, field, value):
    data, metadata = blend_evidence(tmp_path)
    kwargs = {"length_tolerance": 1e-6, field: value}
    with pytest.raises(PrepError):
        recognize_cylindrical_blends(persist(data, metadata), **kwargs)


@pytest.mark.parametrize("mutation", ["policy", "missing_policy", "sign", "bool_sign", "equal_counts",
    "position", "same_position", "residual", "margin", "reference", "duplicate", "wrong_volume",
    "unsupported_shape", "false_indeterminate"])
def test_reader_rejects_forged_generic_material_observations(tmp_path, mutation):
    data, metadata = blend_evidence(tmp_path)
    probe = data["blend_material_side_probes"][0]
    if mutation == "policy": data["blend_probe_policy"]["angular_tolerance_radians"] = .1
    if mutation == "missing_policy": data.pop("blend_probe_policy")
    if mutation == "sign": probe["material_normal_sign"] *= -1
    if mutation == "bool_sign": probe["material_normal_sign"] = True
    if mutation == "equal_counts": probe["plus"]["inside_count"] = probe["minus"]["inside_count"]
    if mutation == "position": probe["plus"]["xyz"][0] += .001
    if mutation == "same_position": probe["minus"]["xyz"] = list(probe["plus"]["xyz"])
    if mutation == "residual": probe["plus"]["signed_surface_residual"] *= -1
    if mutation == "margin": probe["numerical_margin"] = 0
    if mutation == "reference": probe["normal_reference"] = "plane_normal"
    if mutation == "duplicate": data["blend_material_side_probes"].append(deepcopy(probe))
    if mutation == "wrong_volume": probe["volume_uuid"] = str(uuid4())
    if mutation == "unsupported_shape": data["surfaces"][0]["geometry_type"] = "Cone"
    if mutation == "false_indeterminate": probe["status"] = "indeterminate"
    with pytest.raises(PrepError):
        persist(data, metadata)


def test_reader_retains_an_explicit_indeterminate_but_classifier_does_not_accept_it(tmp_path):
    data, metadata = blend_evidence(tmp_path)
    data["blend_material_side_probes"][1].update(status="indeterminate", material_normal_sign=None, reason="query_failed")
    report = recognize_cylindrical_blends(persist(data, metadata), length_tolerance=1e-6)
    assert report["features"] == [] and report["unclassified"][0]["reason"] == "material_side_unverified"
