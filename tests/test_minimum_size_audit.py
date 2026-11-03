"""Topological edge measurements on existing DTOs, with no SDK or mesh edits."""
from copy import deepcopy
import json
import math

import pytest

from caelab_prep.application.mesh_candidates import MeshCell, MeshNode
from caelab_prep.application.minimum_size_audit import audit_minimum_edges
from caelab_prep.cae_core.errors import PrepError


POINTS = {
    "line": ((0., 0., 0.), (1., 0., 0.)),
    "tri": ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.)),
    "quad": ((0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)),
    "tet": ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)),
    "hex": ((0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.),
            (0., 0., 1.), (1., 0., 1.), (1., 1., 1.), (0., 1., 1.)),
}
SIGNATURES = {"line": (1, 1, 1), "tri": (2, 2, 1), "quad": (2, 3, 1), "tet": (3, 4, 1), "hex": (3, 5, 1)}


def mesh(family, points=None):
    points = POINTS[family] if points is None else points
    nodes = tuple(MeshNode(11 + 20 * i, point) for i, point in enumerate(points))
    dim, typ, order = SIGNATURES[family]
    return nodes, (MeshCell(503, dim, typ, family, order, tuple(node.id for node in nodes), None),)


@pytest.mark.parametrize("family,edge_count", [("line", 1), ("tri", 3), ("quad", 4), ("tet", 6), ("hex", 12)])
def test_real_linear_topologies_measure_only_their_edges(family, edge_count):
    nodes, cells = mesh(family)
    report = audit_minimum_edges(nodes, cells, 1.)
    assert report["passed"] and report["problem"] is None
    assert report["cells"][0]["edge_count"] == edge_count
    assert report["cells"][0]["min_length"] == 1.
    assert report["below_minimum_ids"] == report["cleanup_candidate_ids"] == []
    assert report["modifications"] == 0


def test_convex_thin_quad_short_diagonal_is_not_a_mesh_edge():
    points = ((0., 0., 0.), (1., .1, 0.), (2., 0., 0.), (1., -.1, 0.))
    assert math.dist(points[1], points[3]) < .25
    nodes, cells = mesh("quad", points)
    report = audit_minimum_edges(nodes, cells, .25)
    assert report["passed"] and report["cells"][0]["edge_count"] == 4
    assert report["cells"][0]["min_length"] == pytest.approx(math.sqrt(1.01))
    assert report["cells"][0]["short_edges"] == []


@pytest.mark.parametrize("family", ["line", "tri", "quad", "tet", "hex"])
def test_actual_short_edge_is_a_target_without_modification(family):
    points = (POINTS[family][0], (.1, 0., 0.), *POINTS[family][2:])
    nodes, cells = mesh(family, points)
    before = deepcopy((nodes, cells))
    report = audit_minimum_edges(nodes, cells, .25)
    assert not report["passed"] and report["problem"] == "below_minimum"
    assert report["below_minimum_ids"] == report["cleanup_candidate_ids"] == [503]
    assert report["cells"][0]["short_edges"] == [{"node_ids": [11, 31], "length": .1}]
    assert report["modifications"] == 0 and (nodes, cells) == before


@pytest.mark.parametrize("minimum,passed", [(.25, True), (math.nextafter(.25, 0.), True),
                                          (math.nextafter(.25, math.inf), False)])
def test_threshold_is_exact_actual_float_distance_without_slack(minimum, passed):
    nodes, cells = mesh("line", ((0., 0., 0.), (.25, 0., 0.)))
    report = audit_minimum_edges(nodes, cells, minimum)
    assert report["passed"] is passed and report["cells"][0]["min_length"] == .25


@pytest.mark.parametrize("dim,typ,order,arity", [(3, 999, 1, 4), (3, 11, 2, 10), (2, 9, 2, 6), (1, 8, 2, 3)])
def test_unsupported_full_inventory_is_retained_and_blocks_whole_audit(dim, typ, order, arity):
    nodes = tuple(MeshNode(11 + i, (float(i), 0., 0.)) for i in range(arity))
    cells = (MeshCell(503, 1, 1, "Line", 1, (11, 12), None),
             MeshCell(901, dim, typ, "Source family", order, tuple(node.id for node in nodes), None))
    report = audit_minimum_edges(nodes, cells, .25)
    assert not report["passed"] and report["unsupported_ids"] == [901]
    assert len(report["cells"]) == len(cells)
    unsupported = report["cells"][1]
    assert (unsupported["dimension"], unsupported["element_type"], unsupported["order"]) == (dim, typ, order)
    assert unsupported["node_ids"] == list(cells[1].node_ids)
    assert unsupported["min_length"] is None and unsupported["edge_count"] == 0
    assert unsupported["short_edges"] == [] and report["cleanup_candidate_ids"] == []
    json.dumps(report, allow_nan=False)


def test_points_are_explicit_annotations_and_no_edge_input_cannot_pass():
    nodes = (MeshNode(11, (0., 0., 0.)),)
    point = MeshCell(503, 0, 15, "Point", 0, (11,), None)
    report = audit_minimum_edges(nodes, (point,), .25)
    assert not report["passed"] and report["skipped_point_ids"] == [503]
    assert report["cells"][0]["status"] == "skipped"
    assert report["cells"][0]["problem"] == "point_annotation"
    assert not audit_minimum_edges((), (), .25)["passed"]
    assert not audit_minimum_edges(nodes, (), .25)["passed"]


@pytest.mark.parametrize("kind", ["missing_ref", "duplicate_node_id", "duplicate_cell_id", "repeated_ref",
                                  "wrong_arity", "nan", "infinite", "bad_xyz", "boolean_id"])
def test_invalid_input_is_an_explicit_prep_error(kind):
    nodes, cells = mesh("line")
    if kind == "missing_ref": cells = (MeshCell(503, 1, 1, "Line", 1, (11, 999), None),)
    elif kind == "duplicate_node_id": nodes += (MeshNode(nodes[0].id, (2., 0., 0.)),)
    elif kind == "duplicate_cell_id": cells += cells
    elif kind == "repeated_ref": cells = (MeshCell(503, 1, 1, "Line", 1, (11, 11), None),)
    elif kind == "wrong_arity": cells = (MeshCell(503, 1, 1, "Line", 1, (11,), None),)
    elif kind == "nan": nodes = (MeshNode(11, (math.nan, 0., 0.)), nodes[1])
    elif kind == "infinite": nodes = (MeshNode(11, (math.inf, 0., 0.)), nodes[1])
    elif kind == "bad_xyz": nodes = (MeshNode(11, (0., 0.)), nodes[1])
    else: nodes = (MeshNode(True, (0., 0., 0.)), nodes[1])
    before = deepcopy((nodes, cells))
    with pytest.raises(PrepError) as error:
        audit_minimum_edges(nodes, cells, .25)
    assert error.value.code == "invalid_minimum_size_input" and (nodes, cells) == before


@pytest.mark.parametrize("minimum", [True, 0, -1, math.nan, math.inf, "0.25", 10 ** 1000])
def test_minimum_must_be_nonboolean_finite_and_positive(minimum):
    nodes, cells = mesh("line")
    with pytest.raises(PrepError) as error:
        audit_minimum_edges(nodes, cells, minimum)
    assert error.value.code == "invalid_minimum_size"


@pytest.mark.parametrize("points,problem,minimum_length,below", [
    (((0., 0., 0.), (0., 0., 0.)), "zero_edge", 0., [503]),
    (((-1e308, 0., 0.), (1e308, 0., 0.)), "nonfinite_edge", None, []),
])
def test_invalid_edge_cells_fail_with_json_safe_measurements(points, problem, minimum_length, below):
    nodes, cells = mesh("line", points)
    report = audit_minimum_edges(nodes, cells, .25)
    assert not report["passed"] and report["invalid_ids"] == [503]
    assert report["cells"][0]["problem"] == problem
    assert report["cells"][0]["min_length"] == minimum_length
    assert report["below_minimum_ids"] == below and report["cleanup_candidate_ids"] == below
    assert report["modifications"] == 0
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("scale", [1e-90, 1., 1e90])
def test_measurement_scales_with_length_unit_and_does_not_mutate_dtos(scale):
    nodes, cells = mesh("tet", tuple(tuple(value * scale for value in point) for point in
                                    ((0., 0., 0.), (.1, 0., 0.), (0., 1., 0.), (0., 0., 1.))))
    original = deepcopy((nodes, cells))
    report = audit_minimum_edges(nodes, cells, .25 * scale)
    assert report["below_minimum_ids"] == report["cleanup_candidate_ids"] == [503]
    assert report["cells"][0]["min_length"] == pytest.approx(.1 * scale, rel=1e-14, abs=0.)
    assert (nodes, cells) == original
    report["cells"][0]["node_ids"].append(999)
    assert (nodes, cells) == original
