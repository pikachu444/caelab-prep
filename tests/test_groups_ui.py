"""T4 group controls use qualified selected entities and one membership command."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt

from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_condition_workflow import model, _block, _card
from test_conditions_ui import apply_operation, fill_operation
from test_modeling_ui import enter, click_apply, pump, wait_file

pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.mark.parametrize("profile", PROFILES)
def test_each_approach_builds_and_edits_node_and_element_memberships(model, tmp_path, profile):
    session, source = model
    mesh_bytes = (source.parent / "mesh.inc").read_bytes()
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()

    session.select_entity("element", 7001); pump()
    selected = tuple(session.selection()["refs"])
    window.modeling.actions["element_group.create"].trigger(); pump()
    panel = window.modeling.panel
    assert panel.editor.editors["element_refs"].value() == selected
    enter(panel, "name", "First element group"); enter(panel, "native_id", 73)
    click_apply(window)
    assert not window.modeling.active, panel.error.text()
    first = _card(session, "/GRSHEL/SHEL/73")["id"]
    assert session.group_members(first)["member_ids"] == [7001]
    assert session.selection()["kind"] == "element" and session.selection()["ids"] == [7001]

    session.select_entity("element", 9007); pump()
    selected_other = tuple(session.selection()["refs"])
    apply_operation(window, "element_group.create", dict(name="Other element group", native_id=74))
    other = _card(session, "/GRSHEL/SHEL/74")["id"]
    other_bytes = session.card_text(other)
    assert session.group_members(other)["member_ids"] == [9007]
    assert window.select_card(first)
    before = session.describe()["revision"]
    window.modeling.actions["object.edit"].trigger(); pump()
    members = panel.editor.editors["element_refs"]
    for index in range(members.list.count()):
        members.list.item(index).setCheckState(Qt.CheckState.Unchecked)
    click_apply(window)
    assert window.modeling.active and members.value() == ()
    assert session.describe()["revision"] == before
    fill_operation(window, {"element_refs": selected + selected_other})
    click_apply(window)
    assert not window.modeling.active, panel.error.text()
    assert session.describe()["revision"] == before + 1
    assert session.group_members(first)["member_ids"] == [7001, 9007]
    assert set(session.selection()["ids"]) == {7001, 9007}
    assert session.card_text(other) == other_bytes
    window.undo_action.trigger(); pump()
    assert session.group_members(first)["member_ids"] == [7001] and session.selection()["ids"] == [7001]
    assert session.card_text(other) == other_bytes
    window.redo_action.trigger(); pump()
    assert set(session.selection()["ids"]) == {7001, 9007}

    session.select_entity("node", 101); pump()
    window.modeling.actions["group.create"].trigger(); pump()
    assert panel.editor.editors["node_ids"].value() == (101,)
    fill_operation(window, dict(name="Node group", native_id=57, node_ids=(101, 205)))
    click_apply(window)
    assert not window.modeling.active, panel.error.text()
    node_group = _card(session, "/GRNOD/NODE/57")["id"]
    assert session.group_members(node_group)["member_ids"] == [101, 205]
    assert window.select_card(node_group)
    apply_operation(window, "object.edit", {"node_ids": (309, 411)})
    assert session.group_members(node_group)["member_ids"] == [309, 411]
    assert set(session.selection()["ids"]) == {309, 411}
    assert session.card_text(other) == other_bytes
    target = tmp_path / profile / "groups_0000.rad"
    window.export_rad_file(target); wait_file(window)
    assert (target.parent / "mesh.inc").read_bytes() == mesh_bytes
    raw = target.read_bytes()
    for keyword, expected in (("/GRSHEL/SHEL/73", [7001, 9007]),
                              ("/GRSHEL/SHEL/74", [9007]), ("/GRNOD/NODE/57", [309, 411])):
        rows = _block(raw, keyword)[1:]
        assert [int(row[offset:offset+10]) for row in rows
                for offset in range(0, len(row.rstrip()), 10)] == expected
