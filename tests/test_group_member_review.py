"""Group review uses two actual mixed native inputs and existing group commands."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from caelab_prep.cae_core import PrepError
from test_node_moves import opened, updates


def state(session):
    return (session.document.revision, {resource.id: resource.render() for resource in session._deck_resources()},
            session._relations_resource().snapshot())


def related(session, members):
    group = session.create_node_group("Explicit reviewed targets", members)["card_id"]
    curve = session.create_curve("Native time curve", [(0, 0), (1, 1)])["card_id"]
    load = session.create_load("Per-node X load", group, curve, "X", 3)["card_id"]
    boundary = session.create_boundary_condition("Fixed translations", group, [True]*3, [False]*3)["card_id"]
    velocity = session.create_initial_velocity("Declared initial vector", group, [1, 0, 0])["card_id"]
    return group, load, boundary, velocity


@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
def test_membership_review_one_publish_undo_codec_and_native_group_rows(name, tmp_path):
    session = opened(name)
    group, load, boundary, velocity = related(session, [2])
    originals = {resource.id: resource.raw for resource in session._deck_resources()}
    conditions = {card: session.card_text(card) for card in (load, boundary, velocity)}
    before = state(session)
    events = []
    session.subscribe(events.append)
    preview = session.plan_group_members(group, [2, 5])
    assert preview["admissible"] and not preview["blocked"]
    assert [ref["local_id"] for ref in preview["added"]] == [5] and not preview["removed"]
    assert len(preview["conditions"]) == 3
    coefficients = next(row["load_coefficients"] for row in preview["conditions"] if row["reference"]["local_id"] == load)
    assert coefficients["before"]["target_count"] == 1 and coefficients["after"]["target_count"] == 2
    assert coefficients["before"]["summed_multiplier"] == [3, 0, 0]
    assert coefficients["after"]["summed_multiplier"] == [6, 0, 0]
    assert coefficients["after"]["value_basis"] == "unevaluated_native_curve_multiplier"
    assert not events and state(session) == before
    # The returned DTO is not an editable command or the private candidate.
    preview["after"][0]["local_id"] = 9
    session.apply_group_members(preview["plan_id"], expected_revision=before[0], expected_document_id=session.document.id)
    assert len(events) == 1 and session.document.revision == before[0] + 1
    assert session.group_members(group)["member_ids"] == [2, 5]
    after = state(session)
    assert after[2] == before[2], "Membership review must not create geometry generations/stale targets"
    assert all(session.card_text(card) == text for card, text in conditions.items())
    assert all(resource.raw == originals[resource.id] for resource in session._deck_resources())
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == after[1:]
    project = tmp_path / "reviewed.caeprep"
    session.save_project(project)
    code = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(Path(sys.argv[1]).with_name('reviewed_0000.rad'))
print(json.dumps({'members':s.group_members(sys.argv[2])['member_ids'],'support':s.condition_support(sys.argv[3])['status'],'relations':s._relations_resource().snapshot()}))
"""
    result = json.loads(subprocess.check_output([sys.executable, "-c", code, str(project), group, load], text=True))
    assert result == {"members": [2, 5], "support": "supported", "relations": after[2]}
    lines = (tmp_path / "reviewed_0000.rad").read_text(encoding="latin1").splitlines()
    keyword = session.card_text(group).splitlines()[0]
    row = lines.index(keyword)
    assert tuple(int(lines[row+2][i:i+10]) for i in (0, 10)) == (2, 5)


def test_same_count_moment_retarget_to_tetra_is_visible_and_blocked():
    session = opened("beam_shell_tet")
    group = session.create_node_group("Moment carriers", [2, 5])["card_id"]
    curve = session.create_curve("Moment curve", [(0, 0), (1, 1)])["card_id"]
    load = session.create_load("Native per-node moment", group, curve, "XX", 3)["card_id"]
    before = state(session)
    preview = session.plan_group_members(group, [2, 7])
    assert not preview["admissible"]
    row = next(row for row in preview["conditions"] if row["reference"]["local_id"] == load)
    assert row["before_support"]["status"] == "supported"
    assert row["after_support"]["status"] == "unverified"
    assert any(diagnostic["node_id"] == 7 for diagnostic in row["after_support"]["diagnostics"])
    assert row["load_coefficients"]["before"]["target_count"] == row["load_coefficients"]["after"]["target_count"] == 2
    with pytest.raises(PrepError) as error:
        session.apply_group_members(preview["plan_id"])
    assert error.value.code == "unsupported_group_members" and state(session) == before


def test_contact_roles_do_not_hide_a_change_with_constant_union():
    session = opened("truss_shell_hex")
    secondary = session.create_node_group("Secondary nodes", [9])["card_id"]
    main = session.create_surface("Main shell PART", [session.resolve_part_reference(9)["card_id"]])["card_id"]
    contact = session.create_contact("Explicit TYPE7 roles", secondary, main, .2)["card_id"]
    preview = session.plan_group_members(secondary, [8, 9])
    assert preview["admissible"]
    row = next(row for row in preview["conditions"] if row["reference"]["local_id"] == contact)
    roles = {role["role"]: role for role in row["roles"]}
    assert (len(roles["secondary"]["before_nodes"]), len(roles["secondary"]["after_nodes"])) == (1, 2)
    assert len(roles["main"]["before_nodes"]) == len(roles["main"]["after_nodes"]) == 4
    assert row["after_support"]["status"] == "not-applicable"
    session.apply_group_members(preview["plan_id"])
    assert session.group_members(secondary)["member_ids"] == [8, 9]


def test_new_initial_velocity_overlap_is_declared_without_inventing_momentum():
    session = opened("beam_shell_tet")
    group = session.create_node_group("First velocity group", [2])["card_id"]
    other = session.create_node_group("Second velocity group", [5])["card_id"]
    first = session.create_initial_velocity("First vector", group, [1, 0, 0])["card_id"]
    second = session.create_initial_velocity("Second vector", other, [0, 2, 0])["card_id"]
    vectors = {card: session.card_text(card) for card in (first, second)}
    preview = session.plan_group_members(group, [2, 5])
    assert preview["admissible"] and len(preview["initial_velocity_overlaps"]) == 1
    overlap = preview["initial_velocity_overlaps"][0]
    assert set(overlap["conditions"]) == {first, second}
    assert not overlap["before_nodes"] and [ref["local_id"] for ref in overlap["after_nodes"]] == [5]
    assert overlap["effective_initial_state"].startswith("not_evaluated")
    session.apply_group_members(preview["plan_id"])
    assert all(session.card_text(card) == text for card, text in vectors.items())


@pytest.mark.parametrize("change", ["revision", "epoch", "resource", "mesh_generation"])
def test_group_plan_rejects_changed_owner_state(change, tmp_path):
    session = opened("beam_shell_tet")
    group = session.create_node_group("CAS targets", [2])["card_id"]
    project = tmp_path / "same-document.caeprep"
    session.save_project(project)
    preview = session.plan_group_members(group, [2, 5])
    if change == "revision":
        session.create_curve("Independent command", [(0, 0), (1, 1)])
    elif change == "epoch":
        session.open_project(str(project))
        assert session.document.id == preview["document_id"]
        assert session.describe()["document_epoch"] != preview["document_epoch"]
    elif change == "resource":
        owner = session._find_card(group)
        text = session.card_text(group).replace("CAS targets", "Changed externally")
        owner.restore(owner.replaced_state(group, text))
    else:
        relations = session._relations_resource()
        updated = relations.snapshot()
        rid = next(resource.id for resource in session._deck_resources())
        updated["mesh_revisions"][rid] = updated["mesh_revisions"].get(rid, 0) + 1
        relations.restore(updated)
    before = state(session)
    with pytest.raises(PrepError) as error:
        session.apply_group_members(preview["plan_id"])
    assert error.value.code == "stale_mesh_candidate"
    assert state(session) == before


def test_group_review_does_not_clear_existing_geometry_review():
    session = opened("beam_shell_tet")
    group = session.create_node_group("Geometry review first", [2])["card_id"]
    plan = session.plan_node_move(updates(session, {2: (11, 0, 0)}), length_unit="mm")
    session.apply_node_move(plan["plan_id"])
    before = state(session)
    with pytest.raises(PrepError) as error:
        session.plan_group_members(group, [2, 5])
    assert error.value.code == "stale_mesh_targets"
    assert state(session) == before and before[2]["stale_targets"]
