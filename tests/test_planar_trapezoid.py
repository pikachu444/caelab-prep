"""Finite oblique support patches, independent of SDK UV parameter frames."""
from copy import deepcopy
import math

import pytest

from caelab_prep.adapters.gmsh_topology import planar_trapezoid_wire, point_in_planar_wire


def trapezoid(*, axis=2, normal_sign=1):
    def permute(values):
        result = list(values); result[2], result[axis] = result[axis], result[2]
        return result
    points = [permute(p) for p in ((3., 0., 4.), (3., -3., 4.), (6., -6., 8.), (6., 0., 8.))]
    normal = [normal_sign * v for v in permute((.8, 0., -.6))]
    curves = {10 * (i+1): {"backend_tag": 10 * (i+1), "geometry_type": "Line",
        "endpoints": [{"backend_tag": j+1, "xyz": points[j]} for j in (i, (i+1) % 4)]} for i in range(4)}
    return curves, normal, permute


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("normal_sign", [1, -1])
def test_shared_topology_resolves_winding_and_strict_interior_for_oblique_plane(axis, normal_sign):
    curves, normal, permute = trapezoid(axis=axis, normal_sign=normal_sign)
    before = deepcopy(curves)
    wire = planar_trapezoid_wire([-40, 20, -10, 30], curves, normal, 0., axis, [4., 8.], 1e-6)
    assert wire is not None and len(wire["ordered_vertices"]) == 4
    assert wire["area"] == pytest.approx(22.5)
    assert wire["perimeter"] == pytest.approx(14. + math.sqrt(34.))
    assert point_in_planar_wire(wire, permute((4.5, -2., 6.)), 1e-6)
    for point in ((4.5, 0., 6.), (4.5, -4.5, 6.), (4.5, 1., 6.),
                  (3., -1., 4.), (2.25, -1., 3.), (4.6, -2., 6.)):
        assert not point_in_planar_wire(wire, permute(point), 1e-6)
    assert curves == before


@pytest.mark.parametrize("mutation", ["circle", "off_plane", "range", "normal", "axis_bool",
    "crossed_sides", "duplicate", "nonfinite", "unresolved_width"])
def test_unsupported_or_malformed_trapezoids_are_not_patches(mutation):
    curves, normal, _ = trapezoid()
    offset, axis, axial = 0., 2, [4., 8.]
    if mutation == "circle": curves[10]["geometry_type"] = "Circle"
    if mutation == "off_plane": offset = .1
    if mutation == "range": axial = [5., 8.]
    if mutation == "normal": normal = [v / 2 for v in normal]
    if mutation == "axis_bool": axis = True
    if mutation == "duplicate": curves[20]["endpoints"][0] = deepcopy(curves[20]["endpoints"][1])
    if mutation == "nonfinite": curves[10]["endpoints"][0]["xyz"][0] = float("inf")
    if mutation == "unresolved_width":
        for curve in curves.values():
            for point in curve["endpoints"]:
                if point["xyz"][1] < 0: point["xyz"][1] = -1e-7
    if mutation == "crossed_sides":
        points = {point["backend_tag"]: deepcopy(point) for curve in curves.values() for point in curve["endpoints"]}
        for tag, ends in zip(curves, ((1, 2), (2, 4), (4, 3), (3, 1))):
            curves[tag]["endpoints"] = [deepcopy(points[i]) for i in ends]
    assert planar_trapezoid_wire([10, 20, 30, 40], curves, normal, offset, axis, axial, 1e-6) is None


@pytest.mark.parametrize("point", [[True, 0., 6.], [4.5, -2.], [float("nan"), -2., 6.], None])
def test_invalid_point_does_not_gain_interior_membership(point):
    curves, normal, _ = trapezoid()
    wire = planar_trapezoid_wire([10, 20, 30, 40], curves, normal, 0., 2, [4., 8.], 1e-6)
    assert not point_in_planar_wire(wire, point, 1e-6)


@pytest.mark.parametrize("vertices", [[], [[0., 0., 0.]], [[0., 0., 0.]] * 3,
    [[0., 0., float("nan")]] * 4])
def test_missing_or_nonfinite_wire_vertices_cannot_vacuously_accept_a_point(vertices):
    wire = {"plane_normal": [0., 0., 1.], "plane_offset": 0., "ordered_vertices": vertices}
    assert not point_in_planar_wire(wire, [0., 0., 0.], 1e-6)
