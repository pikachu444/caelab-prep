"""Shared Qt action and reviewed native winding edits; no OS/VTK render."""
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
from test_shell_normals import copied_model

pytestmark = pytest.mark.usefixtures("qt_widgets")


def open_flip(session, profile=None):
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    action = window.shell_normal_action
    assert action.isEnabled()
    menu = next(menu for menu in window.menuBar().findChildren(QMenu) if menu.title() == "&Mesh")
    assert action in menu.actions()
    action.trigger(); pump()
    dialog = window.shell_normal_dialog
    assert dialog is not None and dialog.isVisible()
    return window, dialog


@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
@pytest.mark.parametrize("profile", PROFILES)
def test_each_presentation_selection_review_cancel_apply_undo_and_save(name, profile, tmp_path):
    session = opened(name); session.select_entity("element", 77)
    before = state(session)
    original = next(c for c in session._mesh_edit_snapshot().cells if c.ref.local_id == 77)
    window, dialog = open_flip(session, profile)
    try:
        assert dialog.table.rowCount() == 1 and dialog.table.item(0, 1).text() == "77"
        dialog.preview_button.click(); pump()
        assert dialog._plan and dialog._plan["admissible"], dialog.status.text()
        assert "local axes" in dialog.preview.toPlainText() and "TYPE7" in dialog.preview.toPlainText()
        assert not dialog.apply_button.isEnabled() and state(session) == before
        QTest.keyClick(dialog, Qt.Key.Key_Escape); pump()
        assert window.shell_normal_dialog is None and state(session) == before
        window.shell_normal_action.trigger(); pump(); dialog = window.shell_normal_dialog
        dialog.preview_button.click(); dialog.reviewed.setChecked(True)
        assert dialog.apply_button.isEnabled()
        QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton); pump()
        assert session.document.revision == before[0] + 1, dialog.status.text()
        assert not dialog.apply_button.isEnabled() and dialog.table.rowCount() == 0
        actual = next(c for c in session._mesh_edit_snapshot().cells if c.ref.local_id == 77)
        assert actual.nodes == tuple(original.nodes[i] for i in (0, 3, 2, 1))
        after = state(session)
        dialog.close_button.click(); pump()
        window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
        window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
        project = tmp_path / "reversed-ui.caeprep"; session.save_project(project)
        restored = PrepSession(); restored.open_project(project)
        assert next(c for c in restored._mesh_edit_snapshot().cells if c.ref.local_id == 77).nodes == actual.nodes
    finally:
        window.close(); pump()


def test_triangular_shell_uses_the_same_action(tmp_path):
    session = copied_model(tmp_path, triangular=True); session.select_entity("element", 77)
    window, dialog = open_flip(session)
    try:
        dialog.preview_button.click(); dialog.reviewed.setChecked(True); dialog.apply_button.click(); pump()
        shell = next(c for c in session._mesh_edit_snapshot().cells if c.ref.local_id == 77)
        assert shell.family == "SH3N" and [n.local_id for n in shell.nodes] == [1, 3, 2]
    finally:
        window.close(); pump()


def test_collects_two_source_selections_without_replacing_the_pending_list():
    session = opened("beam_shell_tet")
    session.import_source(session.plan_import_source(MODELS / "truss_shell_hex" / "model_0000.rad")["plan_id"])
    shells = [cell for cell in session._mesh_edit_snapshot().cells if cell.family == "SHELL"]
    session.select_entity("element", shells[0].ref.local_id)
    before = state(session); window, dialog = open_flip(session)
    try:
        session.select_entity("element", shells[1].ref.local_id); dialog.use_selection_button.click(); pump()
        assert dialog.table.rowCount() == 2
        dialog.use_selection_button.click(); assert dialog.table.rowCount() == 2
        assert {ref["resource_id"] for ref in dialog._references} == {cell.ref.resource_id for cell in shells}
        assert all(dialog.table.item(row, 2).text() == "SHELL" for row in range(2))
        dialog.preview_button.click(); assert len(dialog._plan["cells"]) == 2 and state(session) == before
        dialog.table.selectRow(1); dialog.remove_button.click()
        assert dialog.table.rowCount() == 1 and dialog._plan is None and not dialog.apply_button.isEnabled()
        session.select_entity("node", 1); dialog.use_selection_button.click()
        assert dialog.table.rowCount() == 1 and dialog._references[0]["resource_id"] == shells[0].ref.resource_id
        dialog.preview_button.click(); dialog.reviewed.setChecked(True); dialog.apply_button.click(); pump()
        assert session.document.revision == before[0] + 1
        current = {cell.ref: cell for cell in session._mesh_edit_snapshot().cells}
        assert current[shells[0].ref].nodes == tuple(shells[0].nodes[i] for i in (0, 3, 2, 1))
        assert current[shells[1].ref] == shells[1]
    finally:
        window.close(); pump()


@pytest.mark.parametrize("kind,identifier", [("node", 1), ("element", 78)])
def test_unsupported_selection_is_not_silently_filtered(kind, identifier):
    session = opened("beam_shell_tet"); session.select_entity(kind, identifier)
    before = state(session); window, dialog = open_flip(session)
    try:
        dialog.preview_button.click(); pump()
        assert dialog._plan is None and not dialog.apply_button.isEnabled()
        assert state(session) == before and dialog.status.text()
    finally:
        window.close(); pump()


def test_external_change_and_busy_draft_block_reviewed_apply():
    session = opened("beam_shell_tet"); session.select_entity("element", 77)
    window, dialog = open_flip(session)
    try:
        dialog.preview_button.click(); dialog.reviewed.setChecked(True)
        window.modeling.actions["material.create"].trigger(); pump()
        assert window.modeling.active
        before = state(session); dialog.apply_reversal()
        assert state(session) == before and window.modeling.active and not dialog.apply_button.isEnabled()
        window.modeling.cancel(); dialog.prepare_preview(); dialog.reviewed.setChecked(True)
        session.create_curve("External edit", [(0, 0), (1, 1)])
        before = state(session); dialog.apply_reversal()
        assert state(session) == before and "model changed" in dialog.status.text().lower()
        pump(); assert not dialog.preview_button.isEnabled()
    finally:
        window.close(); pump()


def test_target_preview_and_export_staleness_use_existing_contract():
    session = opened("beam_shell_tet")
    group, load, _, _ = related(session, [1, 2, 3, 4]); session.select_entity("element", 77)
    window, dialog = open_flip(session)
    try:
        dialog.preview_button.click(); pump()
        text = dialog.preview.toPlainText()
        assert "explicit reconnection before export" in text and "Current nodes" in text and "Proposed nodes" in text
        dialog.reviewed.setChecked(True); dialog.apply_button.click(); pump()
        assert group in session.mesh_relationships()["stale_targets"]
        assert session.condition_support(load)["status"] == "stale"
    finally:
        window.close(); pump()
