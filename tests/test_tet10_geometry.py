import math

import pytest

from caelab_prep.application.tet10_geometry import (
    GMSH_EDGES, NATIVE_EDGES, certify_straight_tet10, native_tet10_nodes,
)


def affine(corners, edges=GMSH_EDGES):
    return tuple(corners) + tuple(tuple((a+b)/2 for a, b in zip(corners[i], corners[j])) for i, j in edges)


@pytest.mark.parametrize("scale", [1e-100, 1., 1e100])
@pytest.mark.parametrize("order,edges", [("gmsh", GMSH_EDGES), ("radioss", NATIVE_EDGES)])
def test_affine_geometry_certified_over_entire_element(scale, order, edges):
    corners = ((0., 0., 0.), (scale, 0., 0.), (0., scale, 0.), (0., 0., scale))
    result = certify_straight_tet10(affine(corners, edges), ordering=order)
    assert result["certified_positive"] and result["midpoint_within_ulp_budget"]
    assert result["relative_perturbation_bound"] == 0


def test_small_real_serialization_residual_is_included_in_certificate():
    points = list(affine(((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.))))
    points[4] = (math.nextafter(.5, 1), 0., 0.)
    result = certify_straight_tet10(points)
    assert result["certified_positive"] and result["midpoint_within_ulp_budget"]
    assert 0 < result["relative_perturbation_bound"] < 1
    assert result["maximum_midpoint_residual"] > 0


def test_curved_geometry_cannot_pass_only_because_parent_is_valid():
    points = list(affine(((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.))))
    points[4] = (10., 0., 0.)
    result = certify_straight_tet10(points)
    assert not result["certified_positive"] and not result["midpoint_within_ulp_budget"]
    assert result["reason"] == "positivity_not_certified"


def test_positive_mapping_does_not_imply_straight_profile():
    points = list(affine(((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.))))
    points[4] = (.50001, 0., 0.)
    result = certify_straight_tet10(points)
    assert result["certified_positive"]
    assert not result["midpoint_within_ulp_budget"]


def test_inverted_corner_geometry_is_never_certified():
    points = affine(((0., 0., 0.), (0., 1., 0.), (1., 0., 0.), (0., 0., 1.)))
    assert certify_straight_tet10(points)["reason"] == "parent_not_positive"


def test_finite_extreme_coordinates_fail_certificate_without_report_overflow():
    corners = ((-1e308, 0., 0.), (-1e308, 1., 0.), (-1e308, 0., 1.), (0., 0., 0.))
    points = list(corners) + [tuple(a/2+b/2 for a, b in zip(corners[i], corners[j])) for i, j in GMSH_EDGES]
    points[4] = (1e308, .5, 0.)
    result = certify_straight_tet10(points)
    assert not result["certified_positive"]
    assert not result["midpoint_within_ulp_budget"]
    assert result["maximum_midpoint_residual"] is None


def test_native_order_conversion_keeps_the_same_midpoint_edge_roles():
    ids = tuple(range(1, 11))
    converted = native_tet10_nodes(ids)
    assert converted == (1, 2, 3, 4, 5, 6, 7, 8, 10, 9)
    original_edges = {frozenset(edge): node for edge, node in zip(GMSH_EDGES, ids[4:])}
    native_edges = {frozenset(edge): node for edge, node in zip(NATIVE_EDGES, converted[4:])}
    assert original_edges == native_edges


@pytest.mark.parametrize("bad", [[], [(0, 0, 0)] * 9, [(0, 0, float('nan'))] * 10,
                                 [(True, 0, 0)] * 10])
def test_invalid_coordinates_rejected(bad):
    with pytest.raises(ValueError):
        certify_straight_tet10(bad)
