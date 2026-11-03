"""Delete native elements through the shared pending list and existing target editor."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_group_member_review import related, state
from test_modeling_ui import pump
from test_node_moves import MODELS, opened
from test_prepared_replacement_ui import choose_group, link

pytestmark = pytest.mark.usefixtures("qt_widgets")


def open_delete(session, profile=None):
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    action = window.element_deletion_action
    menu = next(menu for menu in window.menuBar().findChildren(QMenu) if menu.title() == "&Mesh")
    assert action.isEnabled() and action in menu.actions()
    action.trigger(); pump()
    dialog = window.element_deletion_dialog
    assert dialog and dialog.isVisible()
    return window, dialog


@pytest.mark.parametrize("name,remaining", [("beam_shell_tet", 7), ("truss_shell_hex", 8)])
@pytest.mark.parametrize("profile", PROFILES)
def test_each_presentation_explicit_orphan_deletion_cancel_apply_undo_v6(name, remaining, profile, tmp_path):
    session = opened(name); session.select_entity("element", 78)
    before = state(session); window, dialog = open_delete(session, profile)
    assert dialog.table.rowCount() == 1 and dialog.orphan_policy.currentData() is None
    dialog.orphan_policy.setCurrentIndex(dialog.orphan_policy.findData("delete_new"))
    dialog.preview_button.click(); pump()
    assert dialog._plan and dialog._plan["admissible"], dialog.status.text()
    assert "pre-existing orphan nodes are preserved" in dialog.preview.toPlainText()
    assert "physical response is not certified" in dialog.preview.toPlainText()
    assert not dialog.apply_button.isEnabled() and state(session) == before
    QTest.keyClick(dialog, Qt.Key.Key_Escape); pump()
    assert window.element_deletion_dialog is None and state(session) == before
    assert getattr(session, "_element_deletion_plan", None) is None
    window.element_deletion_action.trigger(); pump(); dialog = window.element_deletion_dialog
    dialog.orphan_policy.setCurrentIndex(dialog.orphan_policy.findData("delete_new"))
    dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton); pump()
    assert session.document.revision == before[0]+1 and session.describe()["element_count"] == 2
    assert session.describe()["node_count"] == remaining and dialog.table.rowCount() == 0
    assert not dialog.apply_button.isEnabled() and dialog._plan is None
    dialog.close_button.click(); pump()
    after = state(session)
    window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
    window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
    path = tmp_path / "deleted-ui.caeprep"; session.save_project(path)
    restored = PrepSession(); restored.open_project(path)
    assert restored.describe()["element_count"] == 2 and restored.describe()["node_count"] == remaining
    assert window.close()


def test_policy_is_explicit_and_change_cancels_preview_without_mutation():
    session = opened("beam_shell_tet"); session.select_entity("element", 78)
    before = state(session); window, dialog = open_delete(session)
    dialog.preview_button.click(); assert dialog._plan is None and state(session) == before
    dialog.orphan_policy.setCurrentIndex(dialog.orphan_policy.findData("keep"))
    dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    assert dialog._plan and dialog.apply_button.isEnabled()
    dialog.orphan_policy.setCurrentIndex(dialog.orphan_policy.findData("delete_new"))
    assert dialog._plan is None and not dialog.apply_button.isEnabled() and not dialog.reviewed.isChecked()
    assert getattr(session, "_element_deletion_plan", None) is None and "policy changed" in dialog.status.text()
    assert state(session) == before
    dialog.close_button.click(); assert window.close()


def test_shared_list_accumulates_two_sources_and_remove_invalidates_preview():
    session = opened("beam_shell_tet")
    session.import_source(session.plan_import_source(MODELS / "truss_shell_hex" / "model_0000.rad")["plan_id"])
    refs = [c.ref for c in session._mesh_edit_snapshot().cells if c.family in ("BEAM", "TRUSS")]
    session.select_entity("element", refs[0].local_id)
    before = state(session); window, dialog = open_delete(session)
    session.select_entity("element", refs[1].local_id); dialog.use_selection_button.click()
    dialog.use_selection_button.click(); assert dialog.table.rowCount() == 2
    assert {dialog.table.item(row, 2).text() for row in range(2)} == {"BEAM", "TRUSS"}
    dialog.orphan_policy.setCurrentIndex(dialog.orphan_policy.findData("keep"))
    dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    assert len(dialog._plan["removed_cells"]) == 2
    dialog.table.selectRow(1); dialog.remove_button.click()
    assert dialog.table.rowCount() == 1 and dialog._plan is None and not dialog.apply_button.isEnabled()
    session.select_entity("node", 1); dialog.use_selection_button.click()
    assert dialog.table.rowCount() == 1 and "only elements" in dialog.status.text()
    assert state(session) == before
    dialog.close_button.click(); assert window.close()


def test_deletion_then_actual_drop_editor_recovers_original_conditions(tmp_path):
    session = opened("truss_shell_hex")
    group, load, bcs, velocity = related(session, [4, 9]); session.select_entity("element", 78)
    declarations = {c: session.card_text(c) for c in (load, bcs, velocity)}
    window, dialog = open_delete(session)
    dialog.orphan_policy.setCurrentIndex(dialog.orphan_policy.findData("delete_new"))
    dialog.preview_button.click(); assert dialog._plan["admissible"]
    assert "[6.0, 0.0, 0.0] → [3.0, 0.0, 0.0]" in dialog.preview.toPlainText()
    dialog.reviewed.setChecked(True); dialog.apply_button.click(); pump()
    assert session.group_members(group)["member_ids"] == [4, 9]
    assert session.condition_support(load)["status"] == "stale"
    dialog.close_button.click(); pump()
    window.prepared_mesh_action.trigger(); pump(); reconnect = window.prepared_mesh_dialog
    choose_group(reconnect, group); link(reconnect, 4, 4)
    reconnect.reconnect_table.selectRow(reconnect.reconnect_model.rows.index(9)); reconnect.drop_member_button.click()
    assert reconnect.prepare_reconnection(), reconnect.status.text()
    reconnect.reconnect_reviewed.setChecked(True); reconnect.reconnect_button.click(); pump()
    assert session.group_members(group)["member_ids"] == [4] and not session.mesh_relationships()["stale_targets"]
    assert all(session.card_text(c) == text for c, text in declarations.items())
    session.export_rad(tmp_path / "recovered-ui_0000.rad")
    reconnect.close_button.click(); assert window.close()


def test_model_change_or_active_draft_blocks_old_delete_preview():
    session = opened("beam_shell_tet"); session.select_entity("element", 78)
    window, dialog = open_delete(session)
    dialog.orphan_policy.setCurrentIndex(dialog.orphan_policy.findData("keep"))
    dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    window.modeling.actions["material.create"].trigger(); pump(); before = state(session)
    dialog.apply_change(); assert state(session) == before and window.modeling.active
    window.modeling.cancel(); dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    session.create_curve("External", [(0, 0), (1, 1)]); pump()
    assert not dialog.preview_button.isEnabled() and not dialog.orphan_policy.isEnabled()
    dialog.table.selectRow(0); assert not dialog.remove_button.isEnabled()
    before = state(session); dialog.apply_change(); assert state(session) == before
    dialog.close_button.click(); assert window.close()
