import json
from pathlib import Path
import subprocess
import sys

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError


MODELS = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies"


def opened(name):
    session = PrepSession()
    session.open_rad(MODELS / name / "model_0000.rad")
    return session


def updates(session, positions):
    return [{"reference": session.resolve_entity_reference("node", node)["reference"], "position": xyz}
            for node, xyz in positions.items()]


@pytest.mark.parametrize("name,positions", [
    ("beam_shell_tet", {2: (11, 0, 0)}),
    ("truss_shell_hex", {5: (0, 0, 11), 6: (10, 0, 11), 7: (10, 10, 11), 8: (0, 10, 11), 9: (-10, 10, 11)}),
])
def test_move_preview_one_publish_undo_save_reopen_and_review(name, positions, tmp_path):
    session = opened(name)
    before = {resource.id: resource.render() for resource in session._deck_resources()}
    original = {resource.id: resource.raw for resource in session._deck_resources()}
    group = session.create_node_group("Review moved attachment", [next(iter(positions))])["card_id"]
    session.create_boundary_condition("Fixed moved point", group, [True]*3, [True]*3)
    revision = session.document.revision
    events = []
    session.subscribe(events.append)
    plan = session.plan_node_move(updates(session, positions), length_unit="mm")
    assert not events and session.document.revision == revision
    assert group in plan["stale_targets"] and plan["quality_after"]
    session.apply_node_move(plan["plan_id"], expected_revision=revision)
    assert len(events) == 1 and session.document.revision == revision + 1
    view = session.mesh_view()
    moved = dict(zip(view["node_ids"], view["points"]))
    for node, xyz in positions.items():
        assert tuple(moved[node]) == xyz
    assert all(resource.raw == original[resource.id] for resource in session._deck_resources())
    with pytest.raises(PrepError) as error:
        session.export_rad(tmp_path / "blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    project = tmp_path / "moved.caeprep"
    session.save_project(project)
    code = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
s=PrepSession();s.open_project(sys.argv[1])
try:
    s.export_rad(Path(sys.argv[1]).with_name('should-be-blocked_0000.rad'))
except PrepError as error:
    assert error.code == 'stale_mesh_targets'
else:
    raise AssertionError('Reopened pending geometry review allowed export')
print(json.dumps({'mesh':s.mesh_view(mutable=True),'relations':s.mesh_relationships()}))
"""
    reopened = json.loads(subprocess.check_output([sys.executable, "-c", code, str(project)], text=True))
    assert reopened["mesh"]["points"] == [list(point) for point in view["points"]]
    for card_id, item in session.mesh_relationships()["stale_targets"].items():
        assert reopened["relations"]["stale_targets"][card_id] == item
    stale = session.mesh_relationships()["stale_targets"]
    mappings = {}
    for card_id, item in stale.items():
        assert item["reason"] == "geometry_review_required" and item["mesh_dependencies"]
        if item["family"] == "GRNOD/NODE":
            mapping = {node: session.resolve_entity_reference("node", node)["reference"] for node in item["members"]}
        else:
            raise AssertionError(item["family"])
        mappings[card_id] = {"mesh_revision": item["mesh_revision"], "mapping": mapping}
    session.reconnect_mesh_targets(mappings)
    session.export_rad(tmp_path / "accepted_0000.rad")
    session.undo()
    session.undo()
    # Group/condition creation precedes the move; node coordinates return to baseline.
    for resource in session._deck_resources():
        if resource.id != session._root_id:
            assert resource.render() == before[resource.id]
    session.redo()
    assert session.mesh_relationships()["stale_targets"]


@pytest.mark.parametrize("name,positions", [
    ("beam_shell_tet", {6: (15, 0, 0)}),
    ("truss_shell_hex", {5: (0, 0, 0), 6: (10, 0, 0), 7: (10, 10, 0), 8: (0, 10, 0), 9: (-10, 10, 0)}),
])
def test_bad_geometry_never_partially_changes_document(name, positions):
    session = opened(name)
    before = session.describe(), session.document.tokens()
    with pytest.raises(PrepError):
        session.plan_node_move(updates(session, positions), length_unit="mm")
    assert before == (session.describe(), session.document.tokens())


def test_cancel_units_epoch_and_invalid_coordinate_preserve_state(tmp_path):
    session = opened("beam_shell_tet")
    change = updates(session, {2: (11, 0, 0)})
    before = session.describe(), session.document.tokens()
    for unit in ("m", "unknown"):
        with pytest.raises(PrepError):
            session.plan_node_move(change, length_unit=unit)
    with pytest.raises(PrepError):
        session.plan_node_move([*change, {"reference": change[0]["reference"], "position": (float("nan"), 0, 0)}], length_unit="mm")
    plan = session.plan_node_move(change, length_unit="mm")
    session.cancel_node_move(plan["plan_id"])
    with pytest.raises(PrepError):
        session.apply_node_move(plan["plan_id"])
    assert before == (session.describe(), session.document.tokens())
    project = tmp_path / "same.caeprep"
    session.save_project(project)
    plan = session.plan_node_move(change, length_unit="mm")
    session.open_project(project)
    with pytest.raises(PrepError) as error:
        session.apply_node_move(plan["plan_id"])
    assert error.value.code == "stale_mesh_candidate"


def test_supported_load_is_rechecked_before_marking_review():
    session = opened("beam_shell_tet")
    group = session.create_node_group("Force points", [1, 2])["card_id"]
    curve = session.create_curve("Force", [(0, 1), (1, 1)])["card_id"]
    load = session.create_load("Force", group, curve, "Z", 3)["card_id"]
    before = session.condition_values(load)
    plan = session.plan_node_move(updates(session, {2: (11, 0, 0)}), length_unit="mm")
    session.apply_node_move(plan["plan_id"])
    assert session.condition_values(load) == before


def test_prepared_mesh_replacement_does_not_inherit_old_coordinate_overlays(tmp_path):
    from test_prepared_replacement import replacement
    session = opened("beam_shell_tet")
    plan = session.plan_node_move(updates(session, {2: (11, 0, 0)}), length_unit="mm")
    session.apply_node_move(plan["plan_id"])
    for card_id, item in session.mesh_relationships()["stale_targets"].items():
        mapping = {node: session.resolve_entity_reference("node", node)["reference"] for node in item["members"]}
        session.reconnect_mesh_targets({card_id: {"mesh_revision": item["mesh_revision"], "mapping": mapping}})
    mesh = next(resource for resource in session._deck_resources() if resource.id != session._root_id)
    next_plan = session.plan_mesh_replacement(mesh.id, replacement(tmp_path, True))
    session.replace_prepared_mesh(next_plan["plan_id"])
    points = dict(zip(session.mesh_view()["node_ids"], session.mesh_view()["points"]))
    assert tuple(points[2]) == (12, 2, 2)
    session.undo()
    points = dict(zip(session.mesh_view()["node_ids"], session.mesh_view()["points"]))
    assert tuple(points[2]) == (11, 0, 0)


def test_sparse_node_codec_keeps_unedited_bytes_and_rejects_scalar_patch_overlap():
    from caelab_prep.radioss import DeckResource
    raw = b"#source\r\n/NODE\r\n" + b"         7                   1                   2                   3 EXTRA\r\n#keep\r\n"
    resource = DeckResource(raw, is_include=True)
    state = resource.node_positions_state({"7": [4, 5, 6]})
    resource.restore(state)
    assert resource.raw == raw and resource.render().endswith(b" EXTRA\r\n#keep\r\n")
    card = resource.cards[0]
    bad = resource.snapshot()
    bad["patches"][card.id] = {"x": 999}
    with pytest.raises(PrepError):
        resource.restore(bad)
    assert resource.mesh_projection()["points"] == [[4, 5, 6]]
    resource.restore({"state_version": 3, "patches": {}, "created": [], "deleted": [], "replaced": {}})
    assert resource.render() == raw


def test_tilted_shell_rechecks_moment_support_against_new_geometry():
    session = opened("beam_shell_tet")
    group = session.create_node_group("Shell-only node", [1])["card_id"]
    curve = session.create_curve("Moment", [(0, 1), (1, 1)])["card_id"]
    session.create_load("Global X moment", group, curve, "XX", 1)
    session.mesh_view()  # Real owner cache must not leak into the planning trial.
    before = session.describe(), session.document.tokens()
    with pytest.raises(PrepError) as error:
        session.plan_node_move(updates(session, {2: (10, 0, 5), 3: (10, 10, 5)}), length_unit="mm")
    assert error.value.code == "dependent_condition_invalid"
    assert before == (session.describe(), session.document.tokens())


def test_coordinate_input_units_are_not_engine_work_units(tmp_path):
    source = MODELS / "beam_shell_tet"
    raw = (source / "model_0000.rad").read_text()
    rows = raw.splitlines(keepends=True)
    begin = rows.index("/BEGIN\n")
    rows[begin + 4] = f"{'Mg':>20}{'m':>20}{'s':>20}\n"
    (tmp_path / "model_0000.rad").write_text("".join(rows))
    (tmp_path / "mesh.inc").write_bytes((source / "mesh.inc").read_bytes())
    session = PrepSession()
    session.open_rad(tmp_path / "model_0000.rad")
    plan = session.plan_node_move(updates(session, {2: (11, 0, 0)}), length_unit="mm")
    assert plan["length_unit"] == "mm"
    with pytest.raises(PrepError) as error:
        session.plan_node_move(updates(session, {2: (11, 0, 0)}), length_unit="m")
    assert error.value.code == "unit_mismatch"


def test_independent_same_id_sources_move_by_owner_and_keep_archives(tmp_path):
    from test_source_models import model
    first, second = model(tmp_path / "first"), model(tmp_path / "second")
    session = PrepSession()
    session.open_rad(first)
    first_mesh = next(resource for resource in session._deck_resources() if resource.id != session._root_id)
    first_bytes = first_mesh.render()
    plan = session.plan_import_source(second)
    result = session.import_source(plan["plan_id"])
    archive = session.document.resources[result["source_model_id"]]
    original_archive = dict(archive.files)
    second_mesh = next(resource for resource in session._deck_resources() if resource.id != first_mesh.id and resource.mesh_projection()["node_ids"])
    second_ids = second_mesh.mesh_projection()["node_ids"]
    ref = {"resource_id": second_mesh.id, "entity_kind": "node", "local_id": second_ids[3]}
    node_move = session.plan_node_move([{"reference": ref, "position": (-1, 10, 0)}], length_unit="mm")
    session.apply_node_move(node_move["plan_id"])
    assert first_mesh.render() == first_bytes and archive.files == original_archive
    assert second_mesh.mesh_projection()["points"][3] == [-1, 10, 0]
    session.undo()
    # One request may affect multiple source generations, tracked together.
    group = session.create_node_group("Two source attachments", [1, second_ids[3]])["card_id"]
    request = updates(session, {1: (-1, 0, 0), second_ids[3]: (-1, 10, 0)})
    node_move = session.plan_node_move(request, length_unit="mm")
    session.apply_node_move(node_move["plan_id"])
    record = session.mesh_relationships()["stale_targets"][group]
    assert set(record["mesh_dependencies"]) == {first_mesh.id, second_mesh.id}
    project = tmp_path / "two-sources.caeprep"
    session.save_project(project)
    reopened = PrepSession()
    reopened.open_project(project)
    assert reopened.mesh_relationships()["stale_targets"][group] == record
    assert reopened.document.resources[archive.id].files == original_archive
