"""Review final many-to-one mappings; old links are not live-node counts."""
import json
from uuid import uuid4

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_group_member_review import related, state
from test_node_merges import plan
from test_node_moves import opened


def merged_group():
    session = opened("truss_shell_hex")
    group, load, bcs, velocity = related(session, [9, 4])
    merge = plan(session, 9, 4); session.apply_node_merge(merge["plan_id"])
    return session, group, load, bcs, velocity


def request(session, group, *, coalesce=True, second_target=4):
    stale = session.mesh_relationships()["stale_targets"][group]
    return {group: {"mesh_revision": stale["mesh_revision"], "coalesce_duplicates": coalesce,
        "mapping": {9: session.resolve_entity_reference("node", 4)["reference"],
                    4: session.resolve_entity_reference("node", second_target)["reference"]}}}


def test_review_uses_complete_old_links_and_one_atomic_coalescence_command(tmp_path):
    session, group, load, bcs, velocity = merged_group()
    before = state(session); declarations = {card: session.card_text(card) for card in (load, bcs, velocity)}
    targets = request(session, group)
    with pytest.raises(PrepError) as error: session.reconnect_mesh_targets(targets)
    assert error.value.code == "review_required" and state(session) == before
    review = session.plan_mesh_reconnection(targets)
    assert state(session) == before and len(session.mesh_view()["node_ids"]) == 8
    links = review["links"][0]
    assert links["old_native_ids"] == [9, 4]
    assert (links["old_link_count"], links["unique_target_count"], links["collapsed_count"]) == (2, 1, 1)
    row = next(row for row in review["conditions"] if row["condition_id"] == load)
    assert row["before_support"]["status"] == "stale" and row["after_support"]["status"] == "supported"
    coefficients = row["load_coefficients"]
    assert coefficients["before"]["target_count"] == 2 and coefficients["after"]["target_count"] == 1
    assert coefficients["before"]["summed_multiplier"] == [6, 0, 0]
    assert coefficients["after"]["summed_multiplier"] == [3, 0, 0]
    assert coefficients["after"]["value_basis"] == "unevaluated_native_curve_multiplier"
    review["links"][0]["mapping"][0]["target"]["local_id"] = 1
    json.dumps(review)
    events = []; session.subscribe(events.append)
    session.apply_mesh_reconnection(review["plan_id"], expected_revision=before[0])
    assert len(events) == 1 and session.document.revision == before[0] + 1
    assert session.group_members(group)["member_ids"] == [4]
    assert all(session.card_text(card) == text for card, text in declarations.items())
    assert session._relations_resource().snapshot()["mesh_revisions"] == before[2]["mesh_revisions"]
    after = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    session.redo(); assert state(session)[1:] == after[1:]
    project = tmp_path / "coalesced.caeprep"; session.save_project(project)
    reopened = PrepSession(); reopened.open_project(project)
    assert reopened.group_members(group)["member_ids"] == [4]
    reopened.export_rad(tmp_path / "coalesced_0000.rad")


@pytest.mark.parametrize("bad", ["no_opt_in", "wrong_owner", "missing_link", "bad_flag"])
def test_every_target_and_opt_in_are_checked_before_deduplication(bad):
    session, group, _, _, _ = merged_group(); targets = request(session, group)
    if bad == "no_opt_in": targets[group]["coalesce_duplicates"] = False
    elif bad == "wrong_owner": targets[group]["mapping"][4]["resource_id"] = str(uuid4())
    elif bad == "missing_link": del targets[group]["mapping"][9]
    else: targets[group]["coalesce_duplicates"] = 1
    before = state(session)
    with pytest.raises(PrepError): session.plan_mesh_reconnection(targets)
    assert state(session) == before


def test_final_mapping_can_differ_from_merge_projection():
    session, group, load, _, _ = merged_group()
    other = session.create_node_group("Current overlapping group", [4])["card_id"]
    session.create_initial_velocity("Other vector", other, [0, 2, 0])
    review = session.plan_mesh_reconnection(request(session, group, second_target=1))
    row = next(row for row in review["conditions"] if row["condition_id"] == load)
    assert row["load_coefficients"]["after"]["target_count"] == 2
    assert row["load_coefficients"]["after"]["summed_multiplier"] == [6, 0, 0]
    assert review["initial_velocity_overlaps"]
    assert {tuple(row["velocity"]) for row in review["initial_velocity_overlaps"][0]["declarations"]} == {(1, 0, 0), (0, 2, 0)}
    assert "empty overlap list" in review["overlap_scope"]
    session.apply_mesh_reconnection(review["plan_id"])
    assert session.group_members(group)["member_ids"] == [4, 1]


def test_empty_declared_overlap_does_not_clear_an_unresolved_velocity_group():
    session = opened("truss_shell_hex")
    group, _, _, _ = related(session, [9, 4])
    other = session.create_node_group("Unreviewed adjacent endpoint", [8])["card_id"]
    session.create_initial_velocity("Unknown final overlap", other, [0, 2, 0])
    session.apply_node_merge(plan(session, 9, 4)["plan_id"])
    review = session.plan_mesh_reconnection(request(session, group))
    assert review["initial_velocity_overlaps"] == []
    assert review["unresolved_initial_velocity_groups"] == [other]
    assert other in review["remaining_stale_groups"]
    assert "does not establish absence" in review["overlap_scope"]
    session.apply_mesh_reconnection(review["plan_id"])
    assert set(session.mesh_relationships()["stale_targets"]) == {other}


def test_saved_old_links_remain_the_review_basis_after_a_stale_card_edit():
    session, group, load, _, _ = merged_group()
    session.set_group_members(group, [4])
    review = session.plan_mesh_reconnection(request(session, group))
    row = next(row for row in review["conditions"] if row["condition_id"] == load)
    assert row["load_coefficients"]["before"]["target_count"] == 2
    assert row["load_coefficients"]["before"]["summed_multiplier"] == [6, 0, 0]
    role = row["roles"][0]
    assert role["old_declared_native_ids"] == [9, 4]
    assert role["current_declared_native_ids"] == [4]
    assert "saved pre-mesh memberships" in review["before_basis"]


def test_group_without_conditions_still_exposes_a_changed_current_declaration():
    from caelab_prep.ui.mesh_target_text import reconnection_review_text
    session = opened("truss_shell_hex")
    group = session.create_node_group("No condition references", [9, 4])["card_id"]
    session.apply_node_merge(plan(session, 9, 4)["plan_id"])
    session.set_group_members(group, [1, 4])
    review = session.plan_mesh_reconnection(request(session, group))
    assert review["conditions"] == []
    row = review["links"][0]
    assert row["current_declared_native_ids"] == [1, 4] and row["proposed_native_ids"] == [4]
    text = reconnection_review_text(session, review)
    assert "Current card declaration: [1, 4] → final set: [4]" in text


@pytest.mark.parametrize("change", ["revision", "epoch", "token", "generation"])
def test_reviewed_reconnection_cas_rejects_changed_inputs(change):
    session, group, _, _, _ = merged_group()
    review = session.plan_mesh_reconnection(request(session, group))
    if change == "revision": session.create_curve("Concurrent", [(0, 0), (1, 1)])
    elif change == "epoch": session._document_epoch = str(uuid4())
    elif change == "generation":
        resource = session._relations_resource(); value = resource.snapshot()
        owner = next(iter(value["mesh_revisions"])); value["mesh_revisions"][owner] += 1
        for stale in value["stale_targets"].values():
            if owner in stale.get("mesh_dependencies", {}):
                stale["mesh_dependencies"][owner] = value["mesh_revisions"][owner]
            if stale["mesh_resource_id"] == owner:
                stale["mesh_revision"] = value["mesh_revisions"][owner]
        resource.restore(value)
    else:
        rid = session.resolve_entity_reference("node", 1)["reference"]["resource_id"]
        resource = session.document.resources[rid]; resource.restore(resource.node_positions_state({"1": (0, 0, -.1)}))
    before = state(session)
    with pytest.raises(PrepError) as error: session.apply_mesh_reconnection(review["plan_id"])
    assert error.value.code == "stale_reference_mapping" and state(session) == before
