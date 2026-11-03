"""Native element deletion reuses sparse candidates, reviewed targets and history."""
from dataclasses import asdict
from uuid import uuid4
import shutil

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_group_member_review import related, state
from test_node_moves import MODELS, opened


def element(session, identifier=78):
    return session.resolve_entity_reference("element", identifier)["reference"]


@pytest.mark.parametrize("name,orphans", [("beam_shell_tet", [5, 6]), ("truss_shell_hex", [9])])
@pytest.mark.parametrize("policy", ["keep", "delete_new"])
def test_native_delete_one_publish_preserves_other_cells_undo_v6_and_export(name, orphans, policy, tmp_path):
    session = opened(name)
    before = state(session); source = {r.id: r.raw for r in session._deck_resources()}
    original = session._mesh_edit_snapshot(); ref = element(session)
    events = []; session.subscribe(events.append)
    review = session.plan_element_deletion([ref], orphan_policy=policy)
    assert review["admissible"] and state(session) == before and not events
    assert [r["local_id"] for r in review["new_orphans"]] == orphans
    assert [r["local_id"] for r in review["removed_nodes"]] == (orphans if policy == "delete_new" else [])
    assert len(review["removed_cells"]) == 1 and review["quality_before"] and not review["quality_after"]
    review["removed_cells"].clear(); review["removed_nodes"].clear()
    session.apply_element_deletion(review["plan_id"])
    assert len(events) == 1 and session.document.revision == before[0]+1
    after = session._mesh_edit_snapshot()
    assert after.cells == tuple(c for c in original.cells if c.ref.local_id != 78)
    assert after.nodes == tuple(n for n in original.nodes if policy == "keep" or n.ref.local_id not in orphans)
    assert {r.id: r.raw for r in session._deck_resources()} == source
    changed = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == changed[1:]
    path = tmp_path / "deleted.caeprep"; session.save_project(path)
    restored = PrepSession(); restored.open_project(path)
    out = tmp_path / "deleted_0000.rad"; restored.export_rad(out)
    native = PrepSession(); native.open_rad(out)
    assert len(native._mesh_edit_snapshot().nodes) == len(after.nodes) and len(native.mesh_view()["cells"]) == 2


def test_deleted_member_trial_is_only_a_proposal_then_explicit_drop_recovers(tmp_path):
    session = opened("truss_shell_hex")
    group, load, bcs, velocity = related(session, [4, 9])
    declarations = {c: session.card_text(c) for c in (load, bcs, velocity, group)}
    before = state(session)
    review = session.plan_element_deletion([element(session)], orphan_policy="delete_new")
    assert review["admissible"] and group in review["stale_targets"] and state(session) == before
    row = next(c for c in review["conditions"] if c["reference"]["local_id"] == load)
    assert row["load_coefficients"]["before"]["summed_multiplier"] == [6., 0., 0.]
    assert row["load_coefficients"]["after"]["summed_multiplier"] == [3., 0., 0.]
    session.apply_element_deletion(review["plan_id"])
    assert all(session.card_text(c) == raw for c, raw in declarations.items())
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    stale = session.mesh_relationships()["stale_targets"][group]
    final = session.plan_mesh_reconnection({group: {"mesh_revision": stale["mesh_revision"],
        "mapping": {4: session.resolve_entity_reference("node", 4)["reference"]}, "drop_members": [9]}})
    session.apply_mesh_reconnection(final["plan_id"])
    assert session.group_members(group)["member_ids"] == [4]
    assert all(session.card_text(c) == raw for c, raw in declarations.items() if c != group)
    session.export_rad(tmp_path / "recovered_0000.rad")


def test_kept_orphan_and_surviving_node_lost_rotation_block_apply():
    for name, node, direction in [("truss_shell_hex", 9, "X"), ("beam_shell_tet", 2, "ZZ")]:
        session = opened(name)
        group = session.create_node_group("Mechanical target", [node])["card_id"]
        curve = session.create_curve("Curve", [(0, 0), (1, 1)])["card_id"]
        session.create_load("Component", group, curve, direction, 3)
        before = state(session)
        review = session.plan_element_deletion([element(session)], orphan_policy="keep")
        assert not review["admissible"] and review["blocked"] and state(session) == before
        with pytest.raises(PrepError): session.apply_element_deletion(review["plan_id"])
        assert state(session) == before


@pytest.mark.parametrize("kind", ["node", "element", "surface"])
def test_empty_projected_target_is_rejected_explicitly(kind):
    session = opened("truss_shell_hex")
    if kind == "node": session.create_node_group("Only orphan", [9])
    elif kind == "element": session.create_element_group("Only deleted", [element(session)])
    else:
        surface = session.create_surface("Last shell", [session.resolve_part_reference(9)["card_id"]])["card_id"]
        secondary = session.create_node_group("Secondary", [1])["card_id"]
        session.create_contact("Last main", secondary, surface, .2)
    before = state(session)
    with pytest.raises(PrepError) as error:
        session.plan_element_deletion([element(session, 77 if kind == "surface" else 78)], orphan_policy="delete_new")
    assert error.value.code == "empty_projected_target" and state(session) == before


@pytest.mark.parametrize("bad", ["empty", "node", "foreign", "bool", "duplicate", "policy"])
def test_invalid_selection_or_policy_does_not_mutate(bad):
    session = opened("beam_shell_tet"); ref = element(session)
    if bad == "node": ref["entity_kind"] = "node"
    if bad == "foreign": ref["resource_id"] = str(uuid4())
    if bad == "bool": ref["local_id"] = True
    before = state(session)
    with pytest.raises(PrepError):
        session.plan_element_deletion([] if bad == "empty" else [ref, ref] if bad == "duplicate" else [ref],
                                      orphan_policy="guess" if bad == "policy" else "keep")
    assert state(session) == before


@pytest.mark.parametrize("change", ["revision", "epoch", "token", "generation", "cancel"])
def test_changed_context_or_cancel_rejects_apply(change):
    session = opened("beam_shell_tet"); ref = element(session)
    review = session.plan_element_deletion([ref], orphan_policy="keep")
    if change == "revision": session.create_curve("Other", [(0, 0), (1, 1)])
    elif change == "epoch": session._document_epoch += ":changed"
    elif change == "token":
        owner = session.document.resources[ref["resource_id"]]
        owner.restore(owner.node_positions_state({"1": (0., 0., -.1)}))
    elif change == "generation":
        owner = session._relations_resource(); snapshot = owner.snapshot()
        snapshot["mesh_revisions"][ref["resource_id"]] = 99; owner.restore(snapshot)
    else: session.cancel_element_deletion(review["plan_id"])
    before = state(session)
    with pytest.raises(PrepError): session.apply_element_deletion(review["plan_id"])
    assert state(session) == before


def test_typed_element_and_part_survivor_proposal_then_one_explicit_reconnection(tmp_path):
    session = opened("beam_shell_tet")
    session.import_source(session.plan_import_source(MODELS / "truss_shell_hex" / "model_0000.rad")["plan_id"])
    shells = [c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL"]
    group = session.create_element_group("Two shells", [asdict(c.ref) for c in shells])["card_id"]
    surface = session.create_surface("Two main PARTs", [c.part.local_id for c in shells])["card_id"]
    secondary = session.create_node_group("Surviving solid node", [3])["card_id"]
    contact = session.create_contact("Main loses one PART", secondary, surface, .2)["card_id"]
    original = {c: session.card_text(c) for c in (group, surface, secondary, contact)}
    part_ids = [session.part_assignments(c.part.local_id)["native_part_id"] for c in shells]
    review = session.plan_element_deletion([asdict(shells[0].ref)], orphan_policy="keep")
    assert review["admissible"] and len(review["projected_memberships"]) == 3
    impact = next(r for r in review["impacts"] if r["target"]["local_id"] == surface)
    assert impact["projected_cardinality_after_mapping"] == 1
    for identifier, old_ref, new_ref in [(group, shells[0].ref, shells[1].ref), (surface, shells[0].part, shells[1].part)]:
        row = next(r for r in review["projected_memberships"] if r["group_ref"]["local_id"] == identifier)
        assert row["dropped_members"] == [asdict(old_ref)] and row["proposed_members"] == [asdict(new_ref)]
    session.apply_element_deletion(review["plan_id"])
    assert all(session.card_text(c) == raw for c, raw in original.items())
    stale = session.mesh_relationships()["stale_targets"]
    requests = {group: {"mapping": {shells[1].ref.local_id: asdict(shells[1].ref)}, "drop_members": [shells[0].ref.local_id]},
        surface: {"mapping": {part_ids[1]: shells[1].part.local_id}, "drop_members": [part_ids[0]]},
        secondary: {"mapping": {3: session.resolve_entity_reference("node", 3)["reference"]}}}
    for card, request in requests.items(): request["mesh_revision"] = stale[card]["mesh_revision"]
    final = session.plan_mesh_reconnection(requests); session.apply_mesh_reconnection(final["plan_id"])
    assert not session.mesh_relationships()["stale_targets"] and session.card_text(contact) == original[contact]
    assert not session._contact_reference_checks(session.condition_values(contact))
    output = tmp_path / "typed_0000.rad"; session.export_rad(output)
    native = PrepSession(); native.open_rad(output)
    assert native.describe()["element_count"] == 5


def test_two_source_element_deletion_is_one_publish_and_undo():
    session = opened("beam_shell_tet")
    session.import_source(session.plan_import_source(MODELS / "truss_shell_hex" / "model_0000.rad")["plan_id"])
    selected = [asdict(c.ref) for c in session._mesh_edit_snapshot().cells if c.family in ("BEAM", "TRUSS")]
    before = state(session); events = []; session.subscribe(events.append)
    review = session.plan_element_deletion(selected, orphan_policy="delete_new")
    assert review["admissible"] and len(review["new_orphans"]) == 3
    session.apply_element_deletion(review["plan_id"])
    assert len(events) == 1 and session.describe()["element_count"] == 4 and session.describe()["node_count"] == 15
    session.undo(); assert state(session)[1:] == before[1:]


def test_partial_element_card_preserves_other_rows_comments_and_existing_orphans(tmp_path):
    base = MODELS / "truss_shell_hex"
    for name in ("model_0000.rad", "mesh.inc"): shutil.copyfile(base / name, tmp_path / name)
    mesh = tmp_path / "mesh.inc"; raw = mesh.read_bytes().replace(b"\r\n", b"\n")
    raw = raw.replace(b"/SHELL/9", (f"{1000:10}{30:20g}{30:20g}{30:20g}\n/SHELL/9").encode())
    original = f"{78:10}{8:10}{9:10}\n".encode()
    unchanged = b"# Preserve this row and the short last field\n" + f"{80:10}{6:10}3\n".encode()
    raw = raw.replace(original, original+unchanged).replace(b"\n", b"\r\n")
    mesh.write_bytes(raw)
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    ref = element(session); owner = session.document.resources[ref["resource_id"]]
    review = session.plan_element_deletion([ref], orphan_policy="delete_new")
    assert [n["local_id"] for n in review["new_orphans"]] == [9]
    session.apply_element_deletion(review["plan_id"])
    assert unchanged.replace(b"\n", b"\r\n") in owner.render() and b"/TRUSS/10\r\n" in owner.render()
    assert 1000 in session.mesh_view()["node_ids"] and 9 not in session.mesh_view()["node_ids"]
    assert owner.raw == raw and mesh.read_bytes() == raw


def test_deleting_last_card_row_still_rejects_a_nested_file_directive(tmp_path):
    base = MODELS / "beam_shell_tet"
    for name in ("model_0000.rad", "mesh.inc"): shutil.copyfile(base / name, tmp_path / name)
    mesh = tmp_path / "mesh.inc"
    mesh.write_bytes(mesh.read_bytes().replace(b"/TETRA4/11", b'#include "extra.inc"\n/TETRA4/11', 1))
    (tmp_path / "extra.inc").write_text("# Keep this include\n", encoding="ascii")
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad"); before = state(session)
    with pytest.raises(PrepError) as error: session.plan_element_deletion([element(session)], orphan_policy="keep")
    assert error.value.code == "unsupported_deletion_layout" and state(session) == before
