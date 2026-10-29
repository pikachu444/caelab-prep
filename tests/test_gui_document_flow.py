"""Real Qt field/document integration, independently of GPU availability.

These tests do not claim a rendered 3D view. The VTK path is checked separately.
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from threading import Event, Thread

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QMessageBox, QWidget

from caelab_prep.application.session import PrepSession
from caelab_prep.ui.main_window import MainWindow


FIXTURE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"


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
