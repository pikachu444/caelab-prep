"""Pure/fake Cone recognition and reader evidence; no native SDK execution."""
from copy import deepcopy
import math
from uuid import uuid4

import pytest

from caelab_prep.adapters import gmsh_worker
from caelab_prep.adapters.gmsh_geometry import CONICAL_PROBE_POLICY, BLEND_PROBE_POLICY
from caelab_prep.application.geometry_features import recognize_conical_blends, recognize_geometry_features
from caelab_prep.cae_core.errors import PrepError
from geometry_evidence_fixtures import material_inspection_data
from test_conical_backend import conical_scene, conical_membership
from test_cylindrical_blends import persist


def cone_evidence(tmp_path, *, cusp=False, axis_sign=1, origin_shift=0., plane_scale=1.):
    geometry = conical_scene(cusp=cusp, axis_sign=axis_sign, origin_shift=origin_shift, plane_scale=plane_scale)
    sdk, calls = conical_membership(cusp=cusp)
    rows = gmsh_worker._conical_material_side_probes(sdk, *geometry, 1e-8, "mm")
    assert len(rows) == 3 and len(calls) == 6  # Independent analytic fake, not native material queries.
    return material_inspection_data(tmp_path, geometry,
        probe_rows={"conical_material_side_probes": rows},
        policies={"conical_probe_policy": CONICAL_PROBE_POLICY})


@pytest.mark.parametrize("cusp", [False, True])
@pytest.mark.parametrize("axis_sign", [1, -1])
def test_material_g1_distinguishes_conical_blend_and_cusp(tmp_path, cusp, axis_sign):
    data, metadata = cone_evidence(tmp_path, cusp=cusp, axis_sign=axis_sign)
    before = deepcopy(data)
    inspection = persist(data, metadata)
    report = recognize_conical_blends(inspection, length_tolerance=1e-6)
    assert report["modifications"] == 0 and data == before
    assert report["geometry_resource_uuid"] == inspection.geometry_resource_uuid and report["assets"]
    item, = report["unclassified"] if cusp else report["features"]
    assert len(item["tangent_edges"]) == 2
    assert [row["signed_normal_dot"] for row in item["tangent_edges"]] == pytest.approx([-1., -1.] if cusp else [1., 1.])
    if cusp:
        assert not report["features"] and item["reason"] == "material_normals_not_g1"
    else:
        assert item["kind"] == "conical_blend_candidate" and item["qualification"] == "candidate"
        assert item["radius"] == pytest.approx(7.5)
        assert item["radius_metric"] == "max_finite_principal_radius"
        assert item["cross_section_radius_range"] == pytest.approx([3., 6.])
        assert item["finite_principal_radius_range"] == pytest.approx([3.75, 7.5])
        assert sorted(arc["radius"] for arc in item["end_arcs"]) == pytest.approx([3., 6.])
        assert item["axial_range"] == [4., 8.]


@pytest.mark.parametrize("threshold,count", [(0., 0), (3., 0), (4., 0), (7.49, 0),
    (math.nextafter(7.5, math.inf), 1), (None, 1)])
def test_threshold_uses_maximum_principal_radius_and_not_ref_or_section_radius(tmp_path, threshold, count):
    data, metadata = cone_evidence(tmp_path)
    inspection = persist(data, metadata)
    report = recognize_conical_blends(inspection, length_tolerance=1e-6, radius_threshold=threshold)
    assert len(report["features"]) == count
    if not count:
        assert report["unclassified"][0]["reason"] == "radius_above_threshold"
    else:
        radius = report["features"][0]["radius"]
        assert len(recognize_conical_blends(inspection, length_tolerance=1e-6, radius_threshold=radius)["features"]) == 1
        below = recognize_conical_blends(inspection, length_tolerance=1e-6,
            radius_threshold=math.nextafter(radius, -math.inf))
        assert not below["features"] and below["unclassified"][0]["reason"] == "radius_above_threshold"


@pytest.mark.parametrize("axis_sign,origin_shift,plane_scale", [(1, 2., 1.), (-1, 2., 1.), (1, 0., -7.), (1, 0., 1e100)])
def test_reparameterization_and_plane_coefficients_preserve_the_physical_candidate(tmp_path, axis_sign, origin_shift, plane_scale):
    data, metadata = cone_evidence(tmp_path, axis_sign=axis_sign, origin_shift=origin_shift, plane_scale=plane_scale)
    for face in data["surfaces"]:
        face["samples"][0]["face_normal"] = [123., -456., 789.]
        face["orientation_by_volume"][0]["sign"] *= -1
    feature, = recognize_conical_blends(persist(data, metadata), length_tolerance=1e-6)["features"]
    assert feature["radius"] == pytest.approx(7.5)
    assert [row["signed_normal_dot"] for row in feature["tangent_edges"]] == pytest.approx([1., 1.])


def test_missing_material_evidence_is_unclassified_in_the_combined_review(tmp_path):
    data, metadata = cone_evidence(tmp_path)
    data.pop("conical_probe_policy"); data.pop("conical_material_side_probes")
    inspection = persist(data, metadata)
    report = recognize_geometry_features(inspection, length_tolerance=1e-6)
    assert not report["features"]
    assert report["unclassified"][0]["reason"] == "material_side_unverified"
    assert report["conical_review"]["radius_threshold"] is None


@pytest.mark.parametrize("mutation", ["policy", "missing_policy", "sign", "bool_sign", "equal_counts",
    "same_position", "offset_position", "residual", "epsilon", "margin", "reference", "duplicate",
    "owner", "alpha_period", "zero_angle", "ref_radius", "indeterminate_sign", "cylinder_policy"])
def test_reader_rejects_inconsistent_or_cross_mode_cone_observations(tmp_path, mutation):
    data, metadata = cone_evidence(tmp_path)
    probe = data["conical_material_side_probes"][0]
    if mutation == "policy": data["conical_probe_policy"]["radius_metric"] = "ref_radius"
    if mutation == "missing_policy": data.pop("conical_probe_policy")
    if mutation == "sign": probe["material_normal_sign"] *= -1
    if mutation == "bool_sign": probe["material_normal_sign"] = True
    if mutation == "equal_counts": probe["plus"]["inside_count"] = probe["minus"]["inside_count"]
    if mutation == "same_position": probe["minus"]["xyz"] = list(probe["plus"]["xyz"])
    if mutation == "offset_position": probe["plus"]["xyz"][0] += .001
    if mutation == "residual": probe["plus"]["signed_surface_residual"] *= -1
    if mutation == "epsilon": probe["epsilon"] = 0.
    if mutation == "margin": probe["numerical_margin"] = 0.
    if mutation == "reference": probe["normal_reference"] = "cylinder_radial"
    if mutation == "duplicate": data["conical_material_side_probes"].append(deepcopy(probe))
    if mutation == "owner": probe["volume_uuid"] = str(uuid4())
    if mutation == "alpha_period": data["surfaces"][0]["analytic_properties"]["reals"][7] += math.tau
    if mutation == "zero_angle": data["surfaces"][0]["analytic_properties"]["reals"][7] = 0.
    if mutation == "ref_radius": data["surfaces"][0]["analytic_properties"]["reals"][6] = -3.
    if mutation == "indeterminate_sign": probe["status"] = "indeterminate"
    if mutation == "cylinder_policy":
        rows = data.pop("conical_material_side_probes"); data.pop("conical_probe_policy")
        data["blend_material_side_probes"] = rows; data["blend_probe_policy"] = deepcopy(BLEND_PROBE_POLICY)
    with pytest.raises(PrepError):
        persist(data, metadata)


def test_explicitly_indeterminate_support_cannot_complete_g1(tmp_path):
    data, metadata = cone_evidence(tmp_path)
    data["conical_material_side_probes"][1].update(status="indeterminate", material_normal_sign=None, reason="query_failed")
    report = recognize_conical_blends(persist(data, metadata), length_tolerance=1e-6)
    assert not report["features"] and report["unclassified"][0]["reason"] == "material_side_unverified"
