"""Prep presentation keeps navigation and validation attached to real objects."""

import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPersistentModelIndex, Qt
from PySide6.QtWidgets import QMessageBox, QToolBar, QWidget

from caelab_prep.application.session import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui import main_window

pytestmark = pytest.mark.usefixtures("qt_widgets")


def test_filter_preserves_active_object_and_invalid_input_stays_local():
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
    window = MainWindow(session, enable_viewport=False)
    card = next(card for card in session.list_cards() if card["keyword"].startswith("/MAT/"))
    assert window.select_card(card["id"])
    ref = window.model_tree.selected_ref()
    index = QPersistentModelIndex(window.model_tree.currentIndex())

    window.model_filter.setText("no matching model object")
    model = window.model_tree.model()
    assert all(window.model_tree.isRowHidden(row, model.index(row, 0).parent())
               for row in range(model.rowCount()))
    assert window.model_tree.selected_ref() == ref
    assert window.provider.active_object() == ref

    window.model_filter.clear()
    assert index.isValid()
    assert window.model_tree.selected_ref() == ref
    assert all(not window.model_tree.isRowHidden(row, model.index(row, 0).parent())
               for row in range(model.rowCount()))

    revision = session.describe()["revision"]
    editor = window.field_editors["density"]
    editor.setText("1e")
    editor.setModified(True)
    assert not window._commit_text("density", editor)
    assert window.property_editor.errors["density"].text()
    assert window.messages_dock.isHidden()
    assert session.describe()["revision"] == revision
    assert editor.text() == "1e"
    window.property_tabs.setCurrentIndex(1)
    assert not window._finish_pending_edits()
    assert window.property_tabs.currentIndex() == 0
    assert window.statusBar().currentMessage()
    assert editor.text() == "1e"
    assert session.describe()["revision"] == revision
    editor.setText(str(window._field_specs["density"]["value"]))
    editor.setModified(True)
    assert window._commit_text("density", editor)
    assert not window.property_editor.errors["density"].text()
    assert not editor.isModified()
    assert session.describe()["revision"] == revision


def test_model_warning_is_visible_and_user_messages_layout_restores(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/rad/shell_panels_0000.rad"
    deck = tmp_path / "transformed.rad"
    deck.write_text(source.read_text(encoding="utf-8").replace("/END", "/TRANSFORM/1\nUnsupported display transform\n/END"), encoding="utf-8")
    session = PrepSession()
    session.open_rad(deck)
    assert any(item["code"] == "display_transform_not_applied" for item in session.describe()["diagnostics"])
    window = MainWindow(session, enable_viewport=False)
    assert not window.messages_dock.isHidden()
    window.close()

    clean = MainWindow(enable_viewport=False)
    assert not clean.messages_dock.isHidden()
    clean.close()


def test_host_injects_late_dialog_and_task_overrides(qt_widgets, monkeypatch, tmp_path):
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
    window = MainWindow(session, enable_viewport=False)
    opened, questions, tasks = [], [], []
    monkeypatch.setattr(main_window, "QFileDialog", SimpleNamespace(
        getOpenFileName=lambda *args: (opened.append(args[1]) or "", "")))
    window.open_project_dialog()
    assert opened == ["Open CAELab Prep project"]

    card = next(card for card in session.list_cards() if card["keyword"].startswith("/MAT/"))
    window.select_card(card["id"])
    editor = window.field_editors["density"]
    editor.setText("1e")
    editor.setModified(True)
    monkeypatch.setattr(main_window, "QMessageBox", SimpleNamespace(
        StandardButton=QMessageBox.StandardButton,
        question=lambda *args: questions.append(args[1]) or QMessageBox.StandardButton.Cancel))
    window._reload_properties()
    assert questions == ["Unfinished input"]
    assert editor.text() == "1e"
    window._discard_pending_edits()

    file_task = main_window._FileTask
    def observed_task(function, **kwargs):
        tasks.append(kwargs["operation_id"])
        return file_task(function, **kwargs)
    monkeypatch.setattr(main_window, "_FileTask", observed_task)
    path = tmp_path / "controller.caeprep"
    assert window.save_project_file(path)
    deadline = time.monotonic() + 5
    while window._busy and time.monotonic() < deadline:
        qt_widgets.processEvents()
    assert not window._busy
    assert tasks == ["Save project"]
    assert path.is_file()
    toolbar = window.findChild(QToolBar, "documentToolbar")
    assert toolbar.widgetForAction(window.save_action) is not None


def test_empty_session_has_no_model_errors_or_executable_model_commands(monkeypatch, tmp_path):
    session = PrepSession()
    model_accesses = []
    require = session._require
    def observed_require():
        model_accesses.append(True)
        return require()
    monkeypatch.setattr(session, "_require", observed_require)
    window = MainWindow(session, enable_viewport=False)
    class EmptyViewport(QWidget):
        def shutdown(self):
            pass
    window.viewport = EmptyViewport(window)
    window._refresh_actions()
    monkeypatch.setattr(main_window, "QFileDialog", SimpleNamespace(getOpenFileName=lambda *args: ("", "")))
    window.open_rad_action.trigger()
    window.open_project_action.trigger()
    window.model_filter.setText("part")
    window.property_tabs.setCurrentIndex(1)
    window._reload_properties()
    window.refresh_document(rebuild_viewport=True)
    for _ in range(2):
        window._entity_picked({"kind": None})
    window._history("undo")
    window._history("redo")
    assert window.save_project_dialog() is False
    assert window.save_project_file(tmp_path / "empty.caeprep") is False
    window.export_rad_dialog()
    window.export_rad_file(tmp_path / "empty.rad")
    assert not model_accesses
    assert window.messages.topLevelItemCount() == 0
    assert not window._busy
    assert not window.viewport.isEnabled()
    assert not window.pick_mode.isEnabled()
    assert window.viewport_frame.context.text() == "Open a deck or project"
    model = window.model_tree.model()
    assert model.headerData(0, Qt.Orientation.Horizontal) == "Name"
    assert model.headerData(2, Qt.Orientation.Horizontal) == "Card"
    assert window.model_tree.isColumnHidden(1)
    assert not window.model_tree.isColumnHidden(2)
    for key, action in window.actions.actions.items():
        assert action.isEnabled() == (key in {"file.new", "file.open", "file.open_project", "file.close"}), key
    assert window.document_toolbar.widgetForAction(window.open_rad_action).property("primaryCommand")


def test_short_command_labels_and_primary_state_survive_refresh():
    window = MainWindow(enable_viewport=False)
    toolbar = window.document_toolbar
    assert toolbar.widgetForAction(window.save_action).text() == "Save"
    session = window.session
    session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
    window.refresh_document()
    assert not toolbar.widgetForAction(window.open_rad_action).property("primaryCommand")
    assert not toolbar.widgetForAction(window.save_action).property("primaryCommand")
    card = next(card for card in session.list_cards() if card["keyword"].startswith("/MAT/"))
    window.select_card(card["id"])
    assert window._commit_field("young_modulus", 199000)
    assert toolbar.widgetForAction(window.save_action).property("primaryCommand")
    window._refresh_actions()
    viewbar = window.findChild(QToolBar, "modelViewCommands")
    assert toolbar.widgetForAction(window.save_action).text() == "Save"
    assert toolbar.widgetForAction(window.export_action).text() == "Export"
    assert viewbar.widgetForAction(window.fit_action).text() == "Fit"
    assert viewbar.widgetForAction(window.edges_action).text() == "Edges"
    assert window.save_action.text() == "Save project"
    assert window.fit_action.text() == "Fit model"
    assert not window.viewport_frame.context.text()


def test_wide_initial_sidebar_is_capped_and_later_resize_keeps_user_width(qt_widgets):
    window = MainWindow(enable_viewport=False)
    window.resize(2560, 1369)
    window.show()
    qt_widgets.processEvents()
    assert 410 <= window.model_dock.width() <= 430
    window.resizeDocks([window.model_dock], [380], Qt.Orientation.Horizontal)
    qt_widgets.processEvents()
    window.resize(2400, 1300)
    qt_widgets.processEvents()
    assert 370 <= window.model_dock.width() <= 390


def test_compact_material_inspector_fits_three_fields_and_unit_context(qt_widgets):
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/stiffened_panel_0000.rad")
    window = MainWindow(session, enable_viewport=False)
    card = next(card for card in session.list_cards() if card["keyword"].startswith("/MAT/"))
    window.select_card(card["id"])
    window.resize(960, 640)
    window.show()
    qt_widgets.processEvents()
    assert window.properties_dock.height() >= 290
    assert set(window.field_editors) == {"density", "young_modulus", "poisson_ratio"}
    assert window.property_editor.scroll.verticalScrollBar().maximum() == 0
    assert window.property_tabs.widget(0).verticalScrollBar().maximum() == 0
    assert window.units_note.isVisible()
    assert window.units_note.text()
