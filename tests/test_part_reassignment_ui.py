"""The existing native element list owns PART transfer and the shared history."""
from dataclasses import asdict

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_group_member_review import state
from test_modeling_ui import pump
from test_part_reassignment import empty_target, two_sources
from test_node_moves import MODELS, opened

pytestmark = pytest.mark.usefixtures("qt_widgets")


def open_ownership(session, profile=None):
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    action = window.part_reassignment_action
    menu = next(m for m in window.menuBar().findChildren(QMenu) if m.title() == "&Mesh")
    assert action.isEnabled() and action in menu.actions()
    action.trigger(); pump()
    dialog = window.part_reassignment_dialog
    assert dialog and dialog.isVisible()
    return window, dialog


def choose_target(dialog, target):
    index = dialog.target_part.findData(asdict(target))
    assert index > 0
    dialog.target_part.setCurrentIndex(index); pump()


@pytest.mark.parametrize("first", ["beam_shell_tet", "truss_shell_hex"])
@pytest.mark.parametrize("profile", PROFILES)
def test_each_presentation_explicit_part_review_cancel_apply_undo_and_v6(first, profile, tmp_path):
    session, (source, target) = two_sources(first)
    session.select_entity("element", source.ref.local_id)
    before = state(session); window, dialog = open_ownership(session, profile)
    assert dialog.target_part.currentData() is None and dialog.table.rowCount() == 1
    choose_target(dialog, target.part)
    dialog.preview_button.click(); pump()
    assert dialog._plan and dialog._plan["admissible"], dialog.status.text()
    text = dialog.preview.toPlainText()
    assert "Element ownership" in text and "MAT " in text and "PROP " in text
    assert "Stored shell angle and element thickness overrides stay unchanged" in text
    assert "no physical equivalence is certified" in text
    assert dialog.reviewed.isChecked() and dialog.apply_button.isEnabled() and state(session) == before
    dialog.reviewed.setChecked(False)
    assert not dialog.apply_button.isEnabled()
    dialog.apply_change()
    assert state(session) == before and dialog._plan is None
    dialog.preview_button.click()
    assert dialog.reviewed.isChecked() and dialog.apply_button.isEnabled()
    QTest.keyClick(dialog, Qt.Key.Key_Escape); pump()
    assert window.part_reassignment_dialog is None and state(session) == before
    assert getattr(session, "_part_reassignment_plan", None) is None
    window.part_reassignment_action.trigger(); pump(); dialog = window.part_reassignment_dialog
    choose_target(dialog, target.part); dialog.preview_button.click()
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton); pump()
    assert session.document.revision == before[0]+1 and dialog.table.rowCount() == 0 and not dialog.apply_button.isEnabled()
    changed = next(c for c in session._mesh_edit_snapshot().cells if c.ref == source.ref)
    assert changed.part == target.part and changed.nodes == source.nodes
    dialog.close_button.click(); pump(); after = state(session)
    window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
    window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
    project = tmp_path / "ownership-ui.caeprep"; session.save_project(project)
    reopened = PrepSession(); reopened.open_project(project)
    assert next(c for c in reopened._mesh_edit_snapshot().cells if c.ref == source.ref).part == target.part
    assert window.close()


def test_no_implicit_target_and_target_change_cancels_review_preserving_pending_rows():
    session, (source, target) = two_sources(); session.select_entity("element", source.ref.local_id)
    before = state(session); window, dialog = open_ownership(session)
    dialog.preview_button.click(); assert dialog._plan is None and "explicitly" in dialog.status.text()
    choose_target(dialog, target.part); dialog.preview_button.click()
    assert dialog.apply_button.isEnabled()
    choose_target(dialog, source.part)
    assert dialog._plan is None and getattr(session, "_part_reassignment_plan", None) is None
    assert not dialog.reviewed.isChecked() and not dialog.apply_button.isEnabled() and dialog.table.rowCount() == 1
    assert "Target PART changed" in dialog.status.text() and state(session) == before
    dialog.close_button.click(); assert window.close()


def test_shared_list_accumulates_sources_and_reports_already_owned_rows():
    session, (source, target) = two_sources(); session.select_entity("element", source.ref.local_id)
    before = state(session); window, dialog = open_ownership(session)
    session.select_entity("element", target.ref.local_id); dialog.use_selection_button.click()
    dialog.use_selection_button.click(); assert dialog.table.rowCount() == 2
    choose_target(dialog, target.part); dialog.preview_button.click()
    assert len(dialog._plan["cells"]) == 1 and dialog._plan["unchanged_elements"] == [asdict(target.ref)]
    assert "Already in chosen PART, unchanged" in dialog.preview.toPlainText()
    dialog.table.selectRow(1); dialog.remove_button.click()
    assert dialog.table.rowCount() == 1 and dialog._plan is None and not dialog.apply_button.isEnabled()
    session.select_entity("node", 1); dialog.use_selection_button.click()
    assert dialog.table.rowCount() == 1 and "only elements" in dialog.status.text() and state(session) == before
    dialog.close_button.click(); assert window.close()


def test_existing_empty_part_is_a_typed_picker_target(tmp_path):
    session, source, target = empty_target(tmp_path); session.select_entity("element", source.ref.local_id)
    window, dialog = open_ownership(session)
    choose_target(dialog, target)
    assert "PART 900" in dialog.target_part.currentText() and "Empty shell target" in dialog.target_part.toolTip()
    dialog.preview_button.click(); assert dialog._plan and dialog._plan["admissible"], dialog.status.text()
    dialog.reviewed.setChecked(True); dialog.apply_button.click(); pump()
    assert next(c for c in session._mesh_edit_snapshot().cells if c.ref == source.ref).part == target
    dialog.close_button.click(); assert window.close()


def test_draft_and_document_change_block_old_ownership_and_disable_options():
    session, (source, target) = two_sources(); session.select_entity("element", source.ref.local_id)
    window, dialog = open_ownership(session)
    choose_target(dialog, target.part); dialog.preview_button.click()
    window.modeling.actions["material.create"].trigger(); pump(); before = state(session)
    dialog.apply_change(); assert state(session) == before and window.modeling.active
    window.modeling.cancel(); dialog.preview_button.click()
    session.create_curve("External", [(0, 0), (1, 1)]); pump()
    assert not dialog.preview_button.isEnabled() and not dialog.target_part.isEnabled()
    dialog.table.selectRow(0); assert not dialog.remove_button.isEnabled()
    before = state(session); dialog.apply_change(); assert state(session) == before
    dialog.close_button.click(); assert window.close()


@pytest.mark.parametrize("bad,diagnostic", [("duplicate", "unique"), ("malformed", "positive")])
def test_raw_part_errors_are_diagnosed_by_preview_without_breaking_picker(tmp_path, bad, diagnostic):
    original = opened("beam_shell_tet")
    part = original.resolve_part_reference(9)["card_id"]
    block = original.card_text(part).splitlines(keepends=True)
    if bad == "malformed":
        block[0] = "/PART/900\n"; block[2] = "bad\n"
    base = MODELS / "beam_shell_tet"
    path = tmp_path / "model_0000.rad"
    path.write_bytes((base / "model_0000.rad").read_bytes().replace(b"/END", "".join(block).encode("latin1")+b"/END"))
    (tmp_path / "mesh.inc").write_bytes((base / "mesh.inc").read_bytes())
    session = PrepSession(); session.open_rad(path); session.select_entity("element", 77)
    window = MainWindow(session, enable_viewport=False); window._allow_close = True; window.show(); pump()
    before = state(session)
    dialog = window.open_part_reassignment(); pump()
    assert dialog and dialog.isVisible()
    dialog.target_part.setCurrentIndex(1); dialog.preview_button.click(); pump()
    assert dialog._plan is None and not dialog.apply_button.isEnabled() and diagnostic in dialog.status.text()
    assert state(session) == before
    dialog.close_button.click(); assert window.close()
