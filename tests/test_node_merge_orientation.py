"""Merge candidates only; no native merge command or GUI coverage."""
from dataclasses import replace

import pytest

from caelab_prep.application import mesh_edit_candidates as edits
from test_node_moves import opened


def beam_snapshot():
    session = opened("beam_shell_tet")
    return session, session._mesh_edit_snapshot()


def node(snapshot, identifier):
    return next(value.ref for value in snapshot.nodes if value.ref.local_id == identifier)


@pytest.mark.parametrize("source_id,keeper_id", [(6, 2), (2, 6)])
def test_merge_cannot_silently_replace_explicit_beam_plane_with_default(source_id, keeper_id):
    session, snapshot = beam_snapshot()
    if source_id == 2:
        # Isolate the real BEAM row: the full mixed model also makes a warped shell
        # for this endpoint mapping, which would hide the independent frame defect.
        snapshot = replace(snapshot, cells=tuple(cell for cell in snapshot.cells if cell.family == "BEAM"))
    before = {resource.id: resource.render() for resource in session._deck_resources()}
    digest = snapshot.digest
    source, keeper = node(snapshot, source_id), node(snapshot, keeper_id)
    # 10 mm is this fixture pair's distance, not a recommended merge tolerance.
    with pytest.raises(edits.MeshEditError) as error:
        edits.merge_nodes(snapshot, {source: keeper}, tolerance=10., length_unit="mm",
                          approvals=(edits.MergeApproval(source, keeper, cross_components=True),))
    assert error.value.code == "beam_orientation_change"
    assert snapshot.digest == digest
    assert {resource.id: resource.render() for resource in session._deck_resources()} == before


def test_merge_keeps_existing_beam_default_mode_eligible():
    _, snapshot = beam_snapshot()
    beam = next(cell for cell in snapshot.cells if cell.family == "BEAM")
    # This existing native default mode is valid; the new guard targets a transition.
    original_default = replace(beam, orientation_node=beam.nodes[0])
    snapshot = replace(snapshot, cells=tuple(original_default if cell is beam else cell for cell in snapshot.cells))
    source, keeper = node(snapshot, 6), node(snapshot, 2)
    candidate = edits.merge_nodes(snapshot, {source: keeper}, tolerance=10., length_unit="mm",
                                 approvals=(edits.MergeApproval(source, keeper, cross_components=True),))
    assert candidate.cell_updates == ()
    assert candidate.removed_nodes == (source,)
    assert next(cell for cell in candidate.iter_cells() if cell.family == "BEAM").orientation_node == keeper


def test_merge_explicit_nonendpoint_orientation_remains_eligible():
    _, snapshot = beam_snapshot()
    source, keeper = node(snapshot, 6), node(snapshot, 8)
    candidate = edits.merge_nodes(snapshot, {source: keeper}, tolerance=20., length_unit="mm",
                                 approvals=(edits.MergeApproval(source, keeper, cross_components=True),))
    beam = next(cell for cell in candidate.cell_updates if cell.family == "BEAM")
    assert beam.orientation_node == keeper and keeper not in beam.nodes
    assert all(not quality.problems for quality in candidate.quality_after)
    # Eligibility is not a statement that the old local frame is preserved.
