"""Explicit old-link removal stays separate from missing maps and coalescence."""
import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_group_member_review import related, state
from test_node_moves import MODELS, opened, updates


def moved(session, group):
    preview = session.plan_node_move(updates(session, {1: (-.1, 0., 0.)}), length_unit="mm")
    session.apply_node_move(preview["plan_id"])
    return session.mesh_relationships()["stale_targets"][group]["mesh_revision"]


def node_request(session, members=(1, 2)):
    group, load, bcs, velocity = related(session, list(members))
    revision = moved(session, group)
    ref = session.resolve_entity_reference("node", 2)["reference"]
    return group, load, bcs, velocity, {group: {"mesh_revision": revision, "mapping": {2: ref}, "drop_members": [1]}}


def test_reviewed_drop_preserves_declarations_until_one_apply_undo_and_v6(tmp_path):
    session = opened("beam_shell_tet")
    group, load, bcs, velocity, request = node_request(session)
    declarations = {card: session.card_text(card) for card in (load, bcs, velocity)}
    before = state(session); events = []; session.subscribe(events.append)
    review = session.plan_mesh_reconnection(request)
    assert state(session) == before and not events
    row, = review["links"]
    assert row["dropped_old_native_ids"] == [1] and row["dropped_count"] == 1
    assert row["coalesced_count"] == 0 and row["proposed_native_ids"] == [2]
    coefficients = next(c for c in review["conditions"] if c["condition_id"] == load)["load_coefficients"]
    assert coefficients["before"]["summed_multiplier"] == [6., 0., 0.]
    assert coefficients["after"]["summed_multiplier"] == [3., 0., 0.]
    review["links"][0]["proposed_native_ids"] = []
    session.apply_mesh_reconnection(review["plan_id"])
    assert len(events) == 1 and session.document.revision == before[0] + 1
    assert session.group_members(group)["member_ids"] == [2]
    assert all(session.card_text(card) == text for card, text in declarations.items())
    assert all(session.condition_support(card)["status"] == "supported" for card in declarations)
    after = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == after[1:]
    target = tmp_path / "dropped.caeprep"; session.save_project(target)
    restored = PrepSession(); restored.open_project(target)
    assert restored.group_members(group)["member_ids"] == [2] and not restored.mesh_relationships()["stale_targets"]
    restored.export_rad(tmp_path / "dropped_0000.rad")


def test_drop_requires_sealed_review_and_does_not_mean_incomplete_mapping():
    session = opened("beam_shell_tet")
    group, _, _, _, request = node_request(session)
    before = state(session)
    with pytest.raises(PrepError) as error: session.reconnect_mesh_targets(request)
    assert error.value.code == "review_required" and state(session) == before
    request[group].pop("drop_members")
    with pytest.raises(PrepError) as error: session.plan_mesh_reconnection(request)
    assert error.value.code == "incomplete_reference_mapping" and state(session) == before


@pytest.mark.parametrize("bad", ["bool", "duplicate", "unknown", "string", "none", "overlap", "empty", "invalid_target"])
def test_invalid_or_empty_drop_never_changes_the_model(bad):
    session = opened("beam_shell_tet")
    group, _, _, _, request = node_request(session)
    if bad == "bool": request[group]["drop_members"] = [True]
    if bad == "duplicate": request[group]["drop_members"] = [1, 1]
    if bad == "unknown": request[group]["drop_members"] = [999]
    if bad == "string": request[group]["drop_members"] = ["1"]
    if bad == "none": request[group]["drop_members"] = None
    if bad == "overlap": request[group]["drop_members"] = [1, 2]
    if bad == "empty": request[group].update(mapping={}, drop_members=[1, 2])
    if bad == "invalid_target": request[group]["mapping"][2] = {"resource_id": "wrong", "entity_kind": "node", "local_id": 2}
    before = state(session)
    with pytest.raises(PrepError): session.plan_mesh_reconnection(request)
    assert state(session) == before


def test_drop_count_and_repeated_target_count_are_separate():
    session = opened("beam_shell_tet")
    group, _, _, _, request = node_request(session, (1, 2, 3))
    ref = session.resolve_entity_reference("node", 2)["reference"]
    request[group].update(mapping={1: ref, 2: ref}, drop_members=[3], coalesce_duplicates=True)
    review = session.plan_mesh_reconnection(request); row, = review["links"]
    assert row["dropped_old_native_ids"] == [3] and row["dropped_count"] == row["coalesced_count"] == 1
    assert row["old_link_count"] == 3 and row["unique_target_count"] == 1
    session.apply_mesh_reconnection(review["plan_id"])
    assert session.group_members(group)["member_ids"] == [2]


@pytest.mark.parametrize("family", ["BCS", "TYPE7"])
def test_drop_keeps_final_attachment_guards_active(family):
    session = opened("beam_shell_tet")
    group = session.create_node_group("Final target", [1, 2])["card_id"]
    if family == "BCS":
        session.create_boundary_condition("BCS", group, [True]*3, [False]*3)
    else:
        main = session.create_surface("Main", [session.resolve_part_reference(9)["card_id"]])["card_id"]
        session.create_contact("TYPE7", group, main, .2)
    revision = moved(session, group); before = state(session)
    request = {group: {"mesh_revision": revision, "mapping": {2: session.resolve_entity_reference("node", 6)["reference"]}, "drop_members": [1]}}
    with pytest.raises(PrepError) as error: session.plan_mesh_reconnection(request)
    assert error.value.code == ("unsupported_contact_targets" if family == "TYPE7" else "unsupported_condition_dof")
    assert state(session) == before


@pytest.mark.parametrize("kind", ["element", "part"])
def test_typed_non_node_drop_uses_the_same_reviewed_transaction(kind):
    session = opened("beam_shell_tet")
    session.import_source(session.plan_import_source(MODELS / "truss_shell_hex" / "model_0000.rad")["plan_id"])
    shells = [cell for cell in session._mesh_edit_snapshot().cells if cell.family == "SHELL"]
    if kind == "element":
        refs = [{"resource_id": c.ref.resource_id, "entity_kind": "element", "local_id": c.ref.local_id} for c in shells]
        group = session.create_element_group("Two source shells", refs)["card_id"]
        identifiers = [c.ref.local_id for c in shells]; retained = refs[1]
    else:
        group = session.create_surface("Two source PARTs", [c.part.local_id for c in shells])["card_id"]
        identifiers = [session.part_assignments(c.part.local_id)["native_part_id"] for c in shells]
        retained = shells[1].part.local_id
    revision = moved(session, group); before = state(session)
    request = {group: {"mesh_revision": revision, "mapping": {identifiers[1]: retained}, "drop_members": [identifiers[0]]}}
    review = session.plan_mesh_reconnection(request)
    assert state(session) == before and review["links"][0]["dropped_old_native_ids"] == [identifiers[0]]
    session.apply_mesh_reconnection(review["plan_id"])
    if kind == "element":
        assert session.group_members(group)["member_ids"] == [identifiers[1]]
    else:
        assert session.card_text(group).splitlines()[2].strip() == str(identifiers[1])
    session.undo(); assert state(session)[1:] == before[1:]


@pytest.mark.parametrize("change", ["revision", "epoch"])
def test_drop_preview_is_stale_after_source_context_changes(change):
    session = opened("beam_shell_tet")
    _, _, _, _, request = node_request(session)
    review = session.plan_mesh_reconnection(request)
    if change == "revision": session.create_curve("External", [(0, 0), (1, 1)])
    else: session._document_epoch += ":changed"
    before = state(session)
    with pytest.raises(PrepError): session.apply_mesh_reconnection(review["plan_id"])
    assert state(session) == before
