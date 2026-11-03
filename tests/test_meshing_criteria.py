"""Criteria persistence and actual execution inputs are separate contracts."""
import json

import pytest

from caelab_prep.application.meshing_criteria import MeshingCriteria
from caelab_prep.application.mesh_candidates import MeshCell, MeshNode
from caelab_prep.cae_core.errors import PrepError


def test_roundtrip_keeps_independent_sizes_and_does_not_rewrite_on_load(tmp_path):
    criteria = MeshingCriteria("mm", 1.5, .25)
    path = tmp_path/"criteria.json"; criteria.save(path)
    original = path.read_bytes()
    loaded = MeshingCriteria.load(path)
    assert loaded == criteria
    assert path.read_bytes() == original
    assert loaded.gmsh_kwargs(source_path="source.step") == {
        "mesh_size": 1.5, "minimum_mesh_size": .25, "expected_coordinate_length_unit": "mm"}


@pytest.mark.parametrize("change", [
    {"target_size": True}, {"minimum_size": False}, {"target_size": "1.5"},
    {"target_size": float("inf")}, {"minimum_size": float("nan")},
    {"target_size": 10**400},
    {"minimum_size": 0}, {"minimum_size": 2}, {"length_unit": "unknown"},
    {"washer_rim_divisions": True}, {"washer_rim_divisions": 2},
    {"washer_width": 0}, {"washer_layers": False}, {"washer_layers": 0},
    {"fillet_suppression_threshold": -1}, {"fillet_suppression_threshold": float("inf")},
])
def test_invalid_criteria_are_rejected_at_the_boundary(change):
    with pytest.raises(PrepError) as exc:
        MeshingCriteria(**{"length_unit": "mm", "target_size": 1.5, "minimum_size": .25, **change})
    assert exc.value.code == "invalid_meshing_criteria"


@pytest.mark.parametrize("unit", ["cm", "m"])
def test_step_criteria_must_use_the_actual_normalized_mm_coordinates(unit):
    with pytest.raises(PrepError) as exc:
        MeshingCriteria(unit, 1.5, .25).gmsh_kwargs(source_path="source.step")
    assert exc.value.code == "criteria_unit_mismatch"


@pytest.mark.parametrize("suffix", ["step", "stp", "iges", "igs"])
def test_normalized_cad_does_not_accept_a_contradictory_coordinate_declaration(suffix):
    with pytest.raises(PrepError):
        MeshingCriteria("cm", 1.5, .25).gmsh_kwargs(
            source_path=f"source.{suffix}", declared_coordinate_length_unit="cm")


@pytest.mark.parametrize("suffix", ["brep", "brp", "xao"])
def test_unitless_cad_requires_a_matching_explicit_coordinate_unit(suffix):
    profile = MeshingCriteria("cm", 1.5, .25)
    with pytest.raises(PrepError):
        profile.gmsh_kwargs(source_path=f"source.{suffix}")
    with pytest.raises(PrepError):
        profile.gmsh_kwargs(source_path=f"source.{suffix}", declared_coordinate_length_unit="unknown")
    with pytest.raises(PrepError, match="must match"):
        profile.gmsh_kwargs(source_path=f"source.{suffix}", declared_coordinate_length_unit="mm")
    assert profile.gmsh_kwargs(source_path=f"source.{suffix}", declared_coordinate_length_unit="cm") == {
        "mesh_size": 1.5, "minimum_mesh_size": .25, "expected_coordinate_length_unit": "cm"}


def test_unknown_cad_format_is_not_given_a_coordinate_unit_by_declaration():
    with pytest.raises(PrepError):
        MeshingCriteria("mm", 1.5, .25).gmsh_kwargs(
            source_path="source.stl", declared_coordinate_length_unit="mm")


@pytest.mark.parametrize("feature_request", [{"washer_rim_divisions": 20}, {"fillet_suppression_threshold": .1},
                                    {"fillet_suppression_threshold": 0}, {"washer_width": .5, "washer_layers": 2}])
def test_persisted_feature_requests_are_not_claimed_as_applied(tmp_path, feature_request):
    criteria = MeshingCriteria("mm", 1.5, .25, **feature_request)
    path = tmp_path/"requested.json"; criteria.save(path)
    loaded = MeshingCriteria.load(path)
    assert loaded == criteria
    with pytest.raises(PrepError) as exc:
        loaded.gmsh_kwargs(source_path="source.step")
    assert exc.value.code == "unsupported_meshing_criteria"
    assert set(exc.value.details["fields"]) == set(feature_request)


@pytest.mark.parametrize("change", [{"unexpected": 1}, {"version": True}, {"version": 2}, {"schema": "other"}])
def test_unknown_fields_and_versions_are_not_ignored(change):
    with pytest.raises(PrepError):
        MeshingCriteria.from_dict({**MeshingCriteria("mm", 1.5, .25).to_dict(), **change})


def test_duplicate_json_fields_are_not_last_value_wins(tmp_path):
    path = tmp_path/"duplicate.json"
    text = json.dumps(MeshingCriteria("mm", 1.5, .25).to_dict()).replace('"target_size": 1.5', '"target_size": 1.5, "target_size": 10')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PrepError, match="Duplicate criteria field"):
        MeshingCriteria.load(path)


def test_output_minimum_flags_actual_short_edge_without_cleanup():
    nodes = (MeshNode(1, (0., 0., 0.)), MeshNode(2, (.1, 0., 0.)), MeshNode(3, (0., 1., 0.)))
    cells = (MeshCell(11, 2, 2, "Triangle 3", 1, (1, 2, 3), None),)
    report = MeshingCriteria("mm", 1.5, .25).audit_minimum_edges(nodes, cells, coordinate_length_unit="mm")
    assert report["criterion"] == "minimum_edge_length" and report["length_unit"] == "mm"
    assert not report["passed"] and report["cleanup_candidate_ids"] == [11]
    assert report["modifications"] == 0 and nodes[1].xyz == (.1, 0., 0.)


def test_output_audit_requires_the_same_explicit_unit():
    with pytest.raises(PrepError) as exc:
        MeshingCriteria("mm", 1.5, .25).audit_minimum_edges((), (), coordinate_length_unit="cm")
    assert exc.value.code == "criteria_unit_mismatch"
