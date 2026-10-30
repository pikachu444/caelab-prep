"""Real Qt field/document integration, independently of GPU availability.

These tests do not claim a rendered 3D view. The VTK path is checked separately.
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from threading import Event, Thread

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPersistentModelIndex, QSettings, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QMessageBox, QWidget

from caelab_prep.application.session import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.widgets import CurvePlot, CurveTable, ModelTree, NumericEdit, PropertyEditor, VectorEdit


FIXTURE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples/rad"


def application(tmp_path):
    app = QApplication.instance() or QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return app


def wait_operation(window, timeout=10):
    until = time.monotonic() + timeout
    while window._busy and time.monotonic() < until:
        QApplication.processEvents()
        QTest.qWait(5)
    assert not window._busy, "GUI file operation did not finish"
    QApplication.processEvents()


def material_card(session):
    return next(card for card in session.list_cards() if card["keyword"].startswith("/MAT/"))


def young_modulus(session, card_id):
    return next(field["value"] for field in session.card_fields(card_id) if field["name"] == "young_modulus")


def edit_young_modulus(window, value):
    editor = window.field_editors["young_modulus"]
    assert isinstance(editor, QLineEdit)
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, str(value))
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()


def test_real_field_undo_project_reopen_and_export(tmp_path):
    app = application(tmp_path)
    window = MainWindow(enable_viewport=False)
    reopened = None
    try:
        window.show()
        window.open_rad_file(FIXTURE)
        wait_operation(window)
        assert window.session.describe()["node_count"] == 8
        card_id = material_card(window.session)["id"]
        assert window.select_card(card_id)
        edit_young_modulus(window, 205000)
        assert young_modulus(window.session, card_id) == 205000
        assert window.session.describe()["dirty"]
        assert window.undo_action.isEnabled()
        window.undo_action.trigger()
        assert young_modulus(window.session, card_id) == 210000
        window.redo_action.trigger()
        assert young_modulus(window.session, card_id) == 205000

        project = tmp_path / "edited.caeprep"
        window.save_project_file(project)
        wait_operation(window)
        assert project.is_file()
        assert not window.session.describe()["dirty"]

        reopened = MainWindow(enable_viewport=False)
        reopened.open_project_file(project)
        wait_operation(reopened)
        assert young_modulus(reopened.session, card_id) == 205000
        export = tmp_path / "edited_0000.rad"
        reopened.export_rad_file(export)
        wait_operation(reopened)
        independent = PrepSession()
        independent.open_rad(export)
        assert young_modulus(independent, material_card(independent)["id"]) == 205000
        assert independent.describe()["node_count"] == 8
        bcs = next(card for card in independent.list_cards() if card["keyword"].startswith("/BCS/"))
        flags = {field["name"]: field["value"] for field in independent.card_fields(bcs["id"])}
        assert all(flags[name] for name in ["tx", "ty", "tz", "rx", "ry", "rz"])
    finally:
        for widget in [window, reopened]:
            if widget:
                widget._allow_close = True
                widget.close()
                widget.deleteLater()
        app.processEvents()


def test_cancelled_replacement_and_save_preserve_edits(tmp_path, monkeypatch):
    app = application(tmp_path)
    window = MainWindow(enable_viewport=False)
    try:
        window.show()
        window.open_rad_file(FIXTURE)
        wait_operation(window)
        card_id = material_card(window.session)["id"]
        window.select_card(card_id)
        edit_young_modulus(window, 199000)
        before = window.session.describe()
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel)
        window.open_rad_file(FIXTURE)
        assert window.session.describe()["document_id"] == before["document_id"]
        assert young_modulus(window.session, card_id) == 199000
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
        window.save_project_dialog(force_new=True)
        assert window.session.describe()["dirty"]
        assert young_modulus(window.session, card_id) == 199000
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_unfinished_number_survives_other_field_and_blocks_navigation(tmp_path):
    app = application(tmp_path)
    window = MainWindow(enable_viewport=False)
    try:
        window.show()
        window.open_rad_file(FIXTURE)
        wait_operation(window)
        card_id = material_card(window.session)["id"]
        window.select_card(card_id)
        density = window.field_editors["density"]
        density.setFocus()
        QTest.keyClick(density, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(density, "1e")
        edit_young_modulus(window, 205000)
        assert window.field_editors["density"].text() == "1e"
        assert window.field_editors["density"].isModified()
        assert young_modulus(window.session, card_id) == 205000
        project = tmp_path / "invalid.caeprep"
        window.save_project_file(project)
        assert not project.exists()
        other = next(card for card in window.session.list_cards() if card["id"] != card_id)
        assert not window.select_card(other["id"])
        revision = window.session.describe()["revision"]
        window.undo_action.trigger()
        assert window.session.describe()["revision"] == revision
        assert window.field_editors["density"].text() == "1e"
        assert window.messages.topLevelItemCount() > 0
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_file_operation_prevents_concurrent_document_actions(tmp_path, monkeypatch):
    app = application(tmp_path)
    window = MainWindow(enable_viewport=False)
    release = Event()
    started = Event()
    try:
        window.show()
        window.open_rad_file(FIXTURE)
        wait_operation(window)
        card_id = material_card(window.session)["id"]
        window.select_card(card_id)
        edit_young_modulus(window, 205000)
        save = window.session.save_project

        def held_save(path):
            started.set()
            assert release.wait(5), "test did not release file operation"
            return save(path)

        monkeypatch.setattr(window.session, "save_project", held_save)
        revision = window.session.describe()["revision"]
        window.save_project_file(tmp_path / "held.caeprep")
        assert started.wait(1)
        assert window._busy
        assert not window.model_tree.isEnabled()
        assert not window._form_host.isEnabled()
        assert not window.undo_action.isEnabled()
        assert not window._commit_field("young_modulus", 199000)
        assert not window.select_card(card_id)
        window.undo_action.trigger()
        window.open_rad_file(FIXTURE)
        window.close()
        assert window.isVisible()
        assert window.session.describe()["revision"] == revision
        release.set()
        wait_operation(window)
        assert window.model_tree.isEnabled()
        assert window.undo_action.isEnabled()
        assert young_modulus(window.session, card_id) == 205000
    finally:
        release.set()
        wait_operation(window)
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_preopened_session_paths_projection_and_external_events(tmp_path, monkeypatch):
    """Projection wiring is a stub here; actual VTK pixels/picks are separate."""
    app = application(tmp_path)

    class ProjectionProbe(QWidget):
        entityPicked = Signal(dict)
        diagnostic = Signal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.projection = None
            self.current_selection = None

        def set_mesh(self, projection):
            self.projection = projection

        def set_selection(self, selection):
            self.current_selection = selection

        def shutdown(self):
            pass

    from caelab_prep.ui import viewport
    monkeypatch.setattr(viewport, "MeshViewport", ProjectionProbe)
    session = PrepSession()
    session.open_rad(FIXTURE)
    project = tmp_path / "startup.caeprep"
    session.save_project(project)
    window = MainWindow(session)
    try:
        assert window._project_path == project
        assert len(window.viewport.projection["cells"]) == 2
        card_id = material_card(session)["id"]
        window.select_card(card_id)
        command = Thread(target=lambda: session.set_field(card_id, "young_modulus", 205000))
        command.start()
        command.join()
        app.processEvents()

        assert float(window.field_editors["young_modulus"].text()) == 205000
        assert window.undo_action.isEnabled()
        window._entity_picked({"kind": "element", "id": 1})
        approved = session.selection()
        assert approved["ids"] == [1]
        assert window.viewport.current_selection == approved
        window._entity_picked({"kind": "element", "id": -999})
        assert window.viewport.current_selection == approved
        window._entity_picked({"kind": "node", "id": 2})
        assert window.viewport.current_selection["kind"] == "node"
        window._entity_picked({"kind": None})
        assert window.viewport.current_selection["ids"] == []
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_scalar_uses_common_controls_and_keeps_tree_state(tmp_path):
    app = application(tmp_path)
    session = PrepSession()
    session.open_rad(EXAMPLES / "shell_panels_0000.rad")
    window = MainWindow(session, enable_viewport=False)
    try:
        window.show()
        assert isinstance(window.model_tree, ModelTree)
        assert isinstance(window.property_editor, PropertyEditor)
        target = material_card(session)["id"]
        assert window.select_card(target)
        app.processEvents()
        index = QPersistentModelIndex(window.model_tree.currentIndex())
        model = window.model_tree.model()
        collapsed = next(model.index(row, 0) for row in range(model.rowCount())
                         if model.index(row, 0).data() == "Parts")
        window.model_tree.collapse(collapsed)
        scroll = window.model_tree.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        position = scroll.value()
        editor = window.field_editors["young_modulus"]
        assert isinstance(editor, NumericEdit)
        editor.setText("199000")
        editor.setModified(True)
        assert window._commit_text("young_modulus", editor)
        assert index.isValid()
        assert window.model_tree.currentIndex() == index
        assert not window.model_tree.isExpanded(collapsed)
        assert scroll.value() == position
        assert young_modulus(session, target) == 199000
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("filename", ["shell_panels_0000.rad", "solid_blocks_0000.rad"])
def test_shared_curve_vector_atomic_edits_and_file_roundtrip(tmp_path, filename):
    app = application(tmp_path)
    session = PrepSession()
    session.open_rad(EXAMPLES / filename)
    window = MainWindow(session, enable_viewport=False)
    try:
        window.show()
        curve = next(card for card in session.list_cards() if card["keyword"] == "/FUNCT/1")
        velocity = next(card for card in session.list_cards() if card["keyword"] == "/INIVEL/TRA/1")
        window.select_card(curve["id"])
        assert isinstance(window.curve_table, CurveTable)
        assert isinstance(window.curve_plot, CurvePlot)
        original = window.curve_table.points()
        with pytest.raises(ValueError):
            window.curve_table.paste_text("0 1\n1 NaN\n2 3")
        assert not window.select_card(velocity["id"])
        assert session.describe()["revision"] == 0
        assert window.curve_table.paste_text_buffer == "0 1\n1 NaN\n2 3"
        window.curve_table.revert()
        points = ((0., 10.), (.1, 40.), (.3, 90.))
        window.curve_table.paste_text("0 10\n.1 40\n.3 90")
        assert session.describe()["revision"] == 0
        assert window.curve_plot._points == original
        window.curve_table.apply_button.click()
        assert session.describe()["revision"] == 1
        assert window.curve_plot._points == points
        window.undo_action.trigger()
        assert window.curve_table.points() == original
        assert not session.describe()["can_undo"]
        window.redo_action.trigger()
        assert window.curve_table.points() == points

        window.select_card(velocity["id"])
        vector = window.property_editor.editors["velocity"]
        assert isinstance(vector, VectorEdit)
        revision = session.describe()["revision"]
        for editor, value in zip(vector.editors, (10, 20, -30)):
            editor.setText(str(value))
            editor.setModified(True)
        assert session.describe()["revision"] == revision
        window.apply_vector_button.click()
        assert session.describe()["revision"] == revision + 1
        assert [field["value"] for field in session.card_fields(velocity["id"])] == [10, 20, -30]
        window.undo_action.trigger()
        assert [field["value"] for field in session.card_fields(velocity["id"])] == [0, 0, -100]
        window.redo_action.trigger()
        project = tmp_path / "edited.caeprep"
        window.save_project_file(project)
        wait_operation(window)
        reopened = PrepSession()
        reopened.open_project(project)
        assert [field["value"] for field in reopened.card_fields(velocity["id"])] == [10, 20, -30]
        output = tmp_path / "export/model_0000.rad"
        window.export_rad_file(output)
        wait_operation(window)
        independent = PrepSession()
        independent.open_rad(output)
        exported_velocity = next(card for card in independent.list_cards() if card["keyword"] == "/INIVEL/TRA/1")
        assert [field["value"] for field in independent.card_fields(exported_velocity["id"])] == [10, 20, -30]
        exported_curve = next(card for card in independent.list_cards() if card["keyword"] == "/FUNCT/1")
        assert tuple(field["value"] for field in independent.card_fields(exported_curve["id"])) == (0, 10, .1, 40, .3, 90)
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_external_curve_change_preserves_draft_and_rejects_stale_apply(tmp_path):
    app = application(tmp_path)
    session = PrepSession()
    session.open_rad(EXAMPLES / "shell_panels_0000.rad")
    window = MainWindow(session, enable_viewport=False)
    try:
        window.show()
        curve = next(card for card in session.list_cards() if card["keyword"] == "/FUNCT/1")
        window.select_card(curve["id"])
        window.curve_table.paste_text("0 5\n.1 6\n.3 7")
        command = Thread(target=lambda: session.set_field(curve["id"], "point_1_y", 55))
        command.start()
        command.join()
        app.processEvents()
        assert window.curve_table.points() == ((0, 5), (.1, 6), (.3, 7))
        assert window._editor_revision == 0
        window.curve_table.apply_button.click()
        assert session.describe()["revision"] == 1
        assert window.curve_table.has_draft()
        assert not window._finish_pending_edits()
        assert session.card_fields(curve["id"])[3]["value"] == 55
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_failed_file_operations_keep_document_drafts_and_actions(tmp_path):
    app = application(tmp_path)
    source = tmp_path / "user path 한글/model_0000.rad"
    source.parent.mkdir()
    source.write_bytes(FIXTURE.read_bytes())
    session = PrepSession()
    session.open_rad(source)
    window = MainWindow(session, enable_viewport=False)
    events = []
    window.operationFinished.connect(lambda operation, success: events.append((operation, success)))
    try:
        window.show()
        card_id = material_card(session)["id"]
        window.select_card(card_id)
        original = session.describe()
        window.open_rad_file(tmp_path / "missing.rad")
        wait_operation(window)
        assert events[-1] == ("Open Radioss deck", False)
        assert window.operation_state.status == "failed"
        assert not window.operation_state.cancellable
        corrupt = tmp_path / "corrupt.caeprep"
        corrupt.write_bytes(b"not a ZIP project")
        window.open_project_file(corrupt)
        wait_operation(window)
        assert events[-1] == ("Open project", False)
        window.export_rad_file(source)
        wait_operation(window)
        assert events[-1] == ("Export Radioss deck", False)
        window.save_project_file(source)
        wait_operation(window)
        assert events[-1] == ("Save project", False)
        assert window.operation_state.status == "failed"
        assert session.describe()["document_id"] == original["document_id"]
        assert session.describe()["revision"] == original["revision"]
        assert window._selected_card_id == card_id
        assert window.save_action.isEnabled()
        assert window.model_tree.isEnabled()
        assert source.read_bytes() == FIXTURE.read_bytes()
        editor = window.field_editors["young_modulus"]
        editor.setText("1e")
        editor.setModified(True)
        window.save_project_file(tmp_path / "blocked.caeprep")
        assert not (tmp_path / "blocked.caeprep").exists()
        assert window.field_editors["young_modulus"].text() == "1e"
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_save_flushes_active_curve_cell_editor_before_file_task(tmp_path):
    app = application(tmp_path)
    session = PrepSession()
    session.open_rad(EXAMPLES / "shell_panels_0000.rad")
    window = MainWindow(session, enable_viewport=False)
    try:
        window.show()
        curve = next(card for card in session.list_cards() if card["keyword"] == "/FUNCT/1")
        window.select_card(curve["id"])
        grid = window.curve_table.table
        grid.setCurrentCell(0, 1)
        grid.editItem(grid.item(0, 1))
        app.processEvents()
        editor = grid.findChild(QLineEdit)
        assert editor is not None
        editor.setFocus()
        QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(editor, "99")
        # The delegate still owns the text here; no Enter or focus loss.
        assert session.describe()["revision"] == 0
        project = tmp_path / "active-cell.caeprep"
        window.save_project_file(project)
        wait_operation(window)
        reopened = PrepSession()
        reopened.open_project(project)
        assert reopened.card_fields(curve["id"])[1]["value"] == 99
        assert session.describe()["revision"] == 1
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()


def test_external_document_replacement_keeps_visible_draft_until_reload(tmp_path, monkeypatch):
    app = application(tmp_path)
    session = PrepSession()
    session.open_rad(EXAMPLES / "shell_panels_0000.rad")
    window = MainWindow(session, enable_viewport=False)
    try:
        window.show()
        card_id = material_card(session)["id"]
        window.select_card(card_id)
        editor = window.field_editors["young_modulus"]
        editor.setText("206000")
        editor.setModified(True)
        previous_document = session.describe()["document_id"]
        session.open_rad(EXAMPLES / "solid_blocks_0000.rad")
        app.processEvents()
        assert session.describe()["document_id"] != previous_document
        assert window.field_editors["young_modulus"].text() == "206000"
        assert window._replacement_conflict
        assert not window._commit_text("young_modulus", editor)
        assert session.describe()["revision"] == 0
        window._entity_picked({"kind": "node", "id": 101})
        assert session.selection()["ids"] == []
        window.save_project_file(tmp_path / "blocked.caeprep")
        assert not (tmp_path / "blocked.caeprep").exists()
        assert not window.save_action.isEnabled()
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel)
        window._reload_properties()
        assert window._replacement_conflict
        assert window.field_editors["young_modulus"].text() == "206000"
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
        window._reload_properties()
        assert not window._replacement_conflict
        assert window._last_presented_document == session.describe()["document_id"]
        assert not window.field_editors
        assert window.save_action.isEnabled()
    finally:
        window._allow_close = True
        window.close()
        window.deleteLater()
        app.processEvents()
