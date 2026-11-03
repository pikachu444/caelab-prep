"""Synthetic analytic feature cases; these are not native CAD execution evidence."""
import json
import math
from uuid import uuid4

import pytest

from caelab_prep.application.geometry_features import recognize_cylindrical_holes
from caelab_prep.application.geometry_inspection import GeometryInspection
from caelab_prep.cae_core.errors import PrepError


@pytest.fixture
def hole():
    volume, cylinder = str(uuid4()), str(uuid4())
    surfaces = [{"uuid": cylinder, "geometry_type": "Cylinder",
                 "analytic_properties": {"reals": [6., 4., -1., 0., 0., 1., 1.]},
                 "parametric_bounds": {"minimum": [0., 1.], "maximum": [2 * math.pi, 4.]},
                 "orientation_by_volume": [{"volume_uuid": volume, "sign": -1}],
                 "curve_loops": [{"curve_tags": [1, 3, -2, -3]}]}]
    curves = [{"backend_tag": 3, "geometry_type": "Line", "adjacent_surface_uuids": [cylinder]}]
    for index, z in enumerate((0., 3.), 1):
        cap = str(uuid4())
        circle = {"backend_tag": index, "geometry_type": "Circle",
                  "parametric_bounds": {"minimum": [0.], "maximum": [2 * math.pi]},
                  "length": 2 * math.pi, "adjacent_surface_uuids": [cylinder, cap],
                  "endpoints": [{"backend_tag": index, "xyz": [7., 4., z]}] * 2}
        curves.append(circle)
        outer = []
        corners = [[0., 0., z], [12., 0., z], [12., 8., z], [0., 8., z]]
        for edge in range(4):
            tag = 10 * index + edge
            outer.append(tag)
            curves.append({"backend_tag": tag, "geometry_type": "Line",
                           "endpoints": [{"backend_tag": 10 * index + vertex, "xyz": corners[vertex]}
                                         for vertex in (edge, (edge + 1) % 4)]})
        surfaces.append({"uuid": cap, "geometry_type": "Plane",
                         "analytic_properties": {"reals": [0., 0., 1., -z]}, "area": 96. - math.pi,
                         "orientation_by_volume": [{"volume_uuid": volume, "sign": 1}],
                         "curve_loops": [{"curve_tags": [index]}, {"curve_tags": outer}]})
    return {"geometry_resource_uuid": str(uuid4()), "geometry_revision": 1, "length_unit": "mm",
            "surfaces": surfaces, "curves": curves,
            "cylinder_material_side_probes": [{"surface_uuid": cylinder, "volume_uuid": volume,
                                               "status": "observed", "radial_material_side": "outward_side_is_material"}]}


def recognize(data):
    # This hand-built snapshot exercises pure analytic decisions, not the reader or SDK.
    inspection = GeometryInspection(data["geometry_resource_uuid"], data["geometry_revision"],
                                    data["length_unit"], (), json.dumps(data))
    return recognize_cylindrical_holes(inspection, length_tolerance=1e-6)


def test_two_rectangular_openings_and_local_cavity_side_give_one_through_candidate(hole):
    before = json.dumps(hole)
    report = recognize(hole)
    assert report["modifications"] == 0 and report["unclassified"] == []
    feature, = report["features"]
    assert feature["kind"] == "through_hole_candidate" and feature["radius"] == 1
    assert feature["surface_uuid"] == hole["surfaces"][0]["uuid"]
    assert [cap["kind"] for cap in feature["caps"]] == ["rectangular_opening"] * 2
    assert feature["qualification"] == "candidate" and json.dumps(hole) == before


def close_cap(cap):
    cap["curve_loops"] = cap["curve_loops"][:1]
    cap["area"] = math.pi


def test_one_closed_disk_and_one_opening_give_a_blind_candidate(hole):
    close_cap(hole["surfaces"][1])
    feature, = recognize(hole)["features"]
    assert feature["kind"] == "blind_hole_candidate"
    assert feature["caps"][0]["kind"] == "closed_disk"


def test_two_closed_disks_are_an_enclosed_cavity_not_a_hole(hole):
    for cap in hole["surfaces"][1:]:
        close_cap(cap)
    report = recognize(hole)
    assert report["features"] == []
    assert report["unclassified"][0]["reason"] == "enclosed_cylindrical_cavity"


@pytest.mark.parametrize("side", ["inward_side_is_material", None])
def test_a_cylinder_without_local_cavity_side_is_not_a_hole(hole, side):
    probe = hole["cylinder_material_side_probes"][0]
    probe["radial_material_side"] = side
    if side is None:
        probe["status"] = "indeterminate"
    assert recognize(hole)["features"] == []


def test_missing_probe_is_not_replaced_by_raw_normal_or_volume_sign(hole):
    hole["cylinder_material_side_probes"] = []
    hole["surfaces"][0]["samples"] = [{"face_normal": [-1., 0., 0.], "trim_count": 1}]
    assert recognize(hole)["unclassified"][0]["reason"] == "material_side_unverified"


def test_unknown_units_do_not_establish_radius_or_tolerance(hole):
    hole["length_unit"] = "unknown"
    assert recognize(hole)["unclassified"][0]["reason"] == "unknown_coordinate_unit"


def test_axis_reversal_and_shift_along_the_same_axis_preserve_the_candidate(hole):
    hole["surfaces"][0]["analytic_properties"]["reals"][2:6] = [200., 0., 0., -1.]
    assert recognize(hole)["features"][0]["kind"] == "through_hole_candidate"


def test_two_disconnected_double_edges_do_not_form_a_rectangular_opening(hole):
    lines = [row for row in hole["curves"] if row["backend_tag"] in (10, 11, 12, 13)]
    lines[1]["endpoints"] = lines[0]["endpoints"]
    lines[3]["endpoints"] = lines[2]["endpoints"]
    assert recognize(hole)["features"] == []


@pytest.mark.parametrize("change", [
    lambda d: d["surfaces"][1].update(area=95.),
    lambda d: d["surfaces"][1]["analytic_properties"].update(reals=[0., 0., 1., -2.]),
    lambda d: d["surfaces"][1]["curve_loops"][1].update(curve_tags=[10, 10, 12, 13]),
    lambda d: d["surfaces"][1]["orientation_by_volume"][0].update(volume_uuid=str(uuid4())),
    lambda d: d["surfaces"][1]["curve_loops"].append({"curve_tags": [1]}),
    lambda d: d["curves"][2].update(geometry_type="Ellipse"),
    lambda d: d["surfaces"][0]["analytic_properties"].update(reals=[6., 4., -1., .6, .8, 0., 1.]),
    lambda d: d["surfaces"][0]["analytic_properties"]["reals"].__setitem__(6, 4.),
])
def test_unqualified_caps_or_trims_stay_unclassified(hole, change):
    change(hole)
    assert recognize(hole)["features"] == []


@pytest.mark.parametrize("tolerance", [True, 0., -1., float("nan"), float("inf"), 10**400])
def test_feature_length_tolerance_is_explicit_and_positive(hole, tolerance):
    inspection = GeometryInspection(hole["geometry_resource_uuid"], 1, "mm", (), json.dumps(hole))
    with pytest.raises(PrepError):
        recognize_cylindrical_holes(inspection, length_tolerance=tolerance)
