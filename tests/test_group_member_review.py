"""Group review uses two actual mixed native inputs and existing group commands."""
import json
import subprocess
import sys

import pytest

from caelab_prep.cae_core import PrepError
from test_node_moves import MODELS, opened, updates


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


def variant(session, tmp_path, replacements=(), *, lowercase=False):
    source = tmp_path / "variant_0000.rad"
    session.export_rad(source)
    raw = source.read_text(encoding="latin1")
    for before, after in replacements:
        before = before.replace("\r\n", "\n").replace("\r", "\n")
        after = after.replace("\r\n", "\n").replace("\r", "\n")
        assert before in raw
        raw = raw.replace(before, after, 1)
    if lowercase:
        raw = "".join(line.lower() if line.startswith("/") else line for line in raw.splitlines(keepends=True))
    source.write_text(raw, encoding="latin1", newline="")
    session.open_rad(str(source))


def titled(session, title):
    return next(card["id"] for card in session.list_cards() if card["title"] == title)


def element_model(first):
    second = "truss_shell_hex" if first == "beam_shell_tet" else "beam_shell_tet"
    session = opened(first)
    session.import_source(session.plan_import_source(MODELS / second / "model_0000.rad")["plan_id"])
    shells = [cell for cell in session.mesh_view()["cells"] if cell["formulation"] == "SHELL"]
    assert len(shells) == 2 and shells[0]["resource_id"] != shells[1]["resource_id"]
    refs = [session.resolve_entity_reference("element", cell["id"])["reference"] for cell in shells]
    group = session.create_element_group("Reviewed cross-source shell set", refs[:1])["card_id"]
    return session, group, refs


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


def test_lowercase_initial_velocity_cards_keep_overlap_diagnostics(tmp_path):
    session = opened("beam_shell_tet")
    first = session.create_node_group("First group", [2])["card_id"]
    second = session.create_node_group("Second group", [5])["card_id"]
    session.create_initial_velocity("First velocity", first, [1, 0, 0])
    session.create_initial_velocity("Second velocity", second, [0, 2, 0])
    variant(session, tmp_path, lowercase=True)
    preview = session.plan_group_members(titled(session, "First group"), [2, 5])
    assert preview["admissible"] and len(preview["initial_velocity_overlaps"]) == 1
    assert [ref["local_id"] for ref in preview["initial_velocity_overlaps"][0]["after_nodes"]] == [5]


def test_lowercase_bcs_keeps_native_inactive_rotation_policy(tmp_path):
    session = opened("truss_shell_hex")
    group = session.create_node_group("Constrained group", [9])["card_id"]
    session.create_boundary_condition("Inactive rotations", group, [True]*3, [True]*3)
    variant(session, tmp_path, lowercase=True)
    preview = session.plan_group_members(titled(session, "Constrained group"), [8, 9])
    assert preview["admissible"] and not preview["blocked"]
    assert preview["conditions"][0]["after_support"]["status"] == "unverified"
    assert all(row["code"] == "inactive_rotation" for row in preview["conditions"][0]["after_support"]["diagnostics"])


def test_imported_invalid_load_direction_is_not_a_supported_moment(tmp_path):
    session = opened("beam_shell_tet")
    group, load, _, _ = related(session, [2])
    before = session.card_text(load)
    lines = before.splitlines(keepends=True)
    lines[2] = lines[2][:10] + f"{'XY':>10}" + lines[2][20:]
    variant(session, tmp_path, [(before, "".join(lines))])
    load = titled(session, "Per-node X load")
    assert session.condition_values(load)["direction"] == "XY"
    assert session.condition_support(load)["status"] == "unverified"
    preview = session.plan_group_members(titled(session, "Explicit reviewed targets"), [2, 5])
    assert not preview["admissible"]
    with pytest.raises(PrepError):
        session.apply_group_members(preview["plan_id"])


def test_imported_solid_main_surface_is_not_approved_by_contact_not_applicable(tmp_path):
    session = opened("truss_shell_hex")
    group = session.create_node_group("Contact secondary", [9])["card_id"]
    surface = session.create_surface("Contact main", [session.resolve_part_reference(9)["card_id"]])["card_id"]
    session.create_contact("Imported TYPE7", group, surface, .2)
    before = session.card_text(surface)
    lines = before.splitlines(keepends=True)
    lines[2] = f"{11:10d}" + lines[2][10:]
    variant(session, tmp_path, [(before, "".join(lines))])
    before_state = state(session)
    preview = session.plan_group_members(titled(session, "Contact secondary"), [8, 9])
    assert not preview["admissible"]
    assert any(row["code"] == "incompatible_surface" for item in preview["blocked"] for row in item["diagnostics"])
    with pytest.raises(PrepError):
        session.apply_group_members(preview["plan_id"])
    assert state(session) == before_state


@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
def test_element_membership_preserves_source_identity_and_does_not_retarget_nodal_conditions(name, tmp_path):
    session, group, refs = element_model(name)
    nodal, load, boundary, velocity = related(session, [2])
    declarations = {card: session.card_text(card) for card in (nodal, load, boundary, velocity)}
    before = state(session)
    preview = session.plan_group_members(group, refs[1:])
    assert preview["admissible"] and not preview["conditions"]
    assert preview["before"] == refs[:1] and preview["after"] == refs[1:]
    assert preview["before"][0]["resource_id"] != preview["after"][0]["resource_id"]
    assert all(ref["entity_kind"] == "element" for ref in preview["after"])
    session.apply_group_members(preview["plan_id"])
    assert session.document.revision == before[0] + 1
    assert session.group_members(group)["members"] == refs[1:]
    assert all(session.card_text(card) == text for card, text in declarations.items())
    after = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == after[1:]
    project = tmp_path / "cross-source-members.caeprep"
    session.save_project(project)
    code = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(Path(sys.argv[1]).with_name('cross-source_0000.rad'))
print(json.dumps(s.group_members(sys.argv[2])['members']))
"""
    result = json.loads(subprocess.check_output([sys.executable, "-c", code, str(project), group], text=True))
    assert result == refs[1:]
