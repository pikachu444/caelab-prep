"""Resolved correspondence must retain supported mechanical target fields."""
import pytest

from caelab_prep.cae_core import PrepError
from test_group_member_review import state
from test_node_moves import opened, updates


def stale_group(session, group):
    preview = session.plan_node_move(updates(session, {1: (-.1, 0., 0.)}), length_unit="mm")
    session.apply_node_move(preview["plan_id"])
    return session.mesh_relationships()["stale_targets"][group]["mesh_revision"]


def contact(session):
    secondary = session.create_node_group("Secondary", [1])["card_id"]
    main = session.create_surface("Main", [session.resolve_part_reference(9)["card_id"]])["card_id"]
    condition = session.create_contact("TYPE7", secondary, main, .2)["card_id"]
    return secondary, main, condition


@pytest.mark.parametrize("reviewed", [False, True])
@pytest.mark.parametrize("family", ["BCS", "TYPE7"])
def test_reconnection_rejects_existing_but_unattached_target(family, reviewed):
    session = opened("beam_shell_tet")
    if family == "TYPE7":
        group, _, _ = contact(session)
    else:
        group = session.create_node_group("Fixed target", [1])["card_id"]
        session.create_boundary_condition("BCS", group, [True]*3, [False]*3)
    revision = stale_group(session, group)
    # Node6 defines BEAM orientation; it is not a mechanical endpoint/cell node.
    target = session.resolve_entity_reference("node", 6)["reference"]
    request = {group: {"mesh_revision": revision, "mapping": {1: target}}}
    before = state(session)
    with pytest.raises(PrepError) as error:
        (session.plan_mesh_reconnection if reviewed else session.reconnect_mesh_targets)(request)
    assert error.value.code == ("unsupported_contact_targets" if family == "TYPE7" else "unsupported_condition_dof")
    assert state(session) == before


@pytest.mark.parametrize("reviewed", [False, True])
def test_inactive_bcs_rotation_warning_is_not_an_unattached_node(reviewed):
    session = opened("beam_shell_tet")
    group = session.create_node_group("BCS target", [1])["card_id"]
    bcs = session.create_boundary_condition("Native ignored rotations", group, [True]*3, [True]*3)["card_id"]
    revision = stale_group(session, group)
    target = session.resolve_entity_reference("node", 7)["reference"]
    request = {group: {"mesh_revision": revision, "mapping": {1: target}}}
    if reviewed:
        preview = session.plan_mesh_reconnection(request)
        session.apply_mesh_reconnection(preview["plan_id"])
    else:
        session.reconnect_mesh_targets(request)
    support = session.condition_support(bcs)
    assert support["status"] == "unverified"
    assert support["diagnostics"] and all(row["code"] == "inactive_rotation" for row in support["diagnostics"])


def test_contact_secondary_is_checked_while_the_main_role_remains_stale():
    session = opened("beam_shell_tet")
    secondary, main, _ = contact(session)
    revision = stale_group(session, secondary)
    preview = session.plan_mesh_reconnection({secondary: {"mesh_revision": revision,
        "mapping": {1: session.resolve_entity_reference("node", 7)["reference"]}}})
    assert main in preview["remaining_stale_groups"] and secondary not in preview["remaining_stale_groups"]
    session.apply_mesh_reconnection(preview["plan_id"])
    assert main in session.mesh_relationships()["stale_targets"]


def test_membership_review_cannot_move_contact_to_an_unattached_node():
    session = opened("beam_shell_tet")
    secondary, _, _ = contact(session)
    before = state(session)
    preview = session.plan_group_members(secondary, [6])
    assert not preview["admissible"] and preview["blocked"]
    assert any(check["code"] == "unsupported_contact_attachment"
        for row in preview["conditions"] for check in row["reference_checks"]["after"])
    with pytest.raises(PrepError): session.apply_group_members(preview["plan_id"])
    assert state(session) == before
