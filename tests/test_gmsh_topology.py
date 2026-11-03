"""Pure finite-wire checks shared by hole caps and cylindrical blend supports."""
from copy import deepcopy

import pytest

from caelab_prep.adapters.gmsh_topology import four_edge_cycle, rectangular_wire


@pytest.fixture
def curves():
    points = ((0., 0., 3.), (12., 0., 3.), (12., 8., 3.), (0., 8., 3.))
    return {index + 1: {"backend_tag": index + 1, "geometry_type": "Line", "endpoints": [
        {"backend_tag": vertex + 1, "xyz": list(points[vertex])} for vertex in (index, (index + 1) % 4)]}
        for index in range(4)}


def test_signed_or_reordered_tags_preserve_one_rectangle_without_mutation(curves):
    before = deepcopy(curves)
    wire = rectangular_wire([-3, 1, -4, 2], curves, 2, 3., 1e-6)
    assert wire["area"] == 96. and wire["perimeter"] == 40.
    assert wire["minimum"] == [0., 0.] and wire["maximum"] == [12., 8.]
    assert curves == before


def test_mixed_curved_cycle_is_topology_only_not_a_planar_rectangle(curves):
    curves[1]["geometry_type"] = "Circle"
    assert four_edge_cycle([1, 2, 3, 4], curves)
    assert rectangular_wire([1, 2, 3, 4], curves, 2, 3., 1e-6) is None


@pytest.mark.parametrize("mutate", [
    lambda c: c[2].update(endpoints=deepcopy(c[1]["endpoints"])),
    lambda c: c[1].update(backend_tag=True),
    lambda c: c[1]["endpoints"][0].update(backend_tag=True),
    lambda c: c[1]["endpoints"][0].update(xyz=[float("inf"), 0., 3.]),
    lambda c: c[1]["endpoints"][0].update(xyz=[0., 0.]),
    lambda c: c[1]["endpoints"][0].update(xyz=[99., 0., 3.]),
])
def test_malformed_or_disconnected_cycles_are_rejected(curves, mutate):
    mutate(curves)
    assert four_edge_cycle([1, 2, 3, 4], curves) is None


def test_duplicate_parallel_edge_components_do_not_form_a_cycle(curves):
    curves[2]["endpoints"] = deepcopy(curves[1]["endpoints"])
    curves[4]["endpoints"] = deepcopy(curves[3]["endpoints"])
    assert four_edge_cycle([1, 2, 3, 4], curves) is None


@pytest.mark.parametrize("tags,axis,coordinate,tolerance", [
    ([1, 2, 3, 3], 2, 3., 1e-6), ([True, 2, 3, 4], 2, 3., 1e-6),
    ([1, 2, 3, 4], True, 3., 1e-6), ([1, 2, 3, 4], 2, 0., 1e-6),
    ([1, 2, 3, 4], 2, 3., 0.), ([1, 2, 3, 4], 2, 3., True),
])
def test_rectangle_requires_a_resolvable_non_degenerate_plane(curves, tags, axis, coordinate, tolerance):
    assert rectangular_wire(tags, curves, axis, coordinate, tolerance) is None
