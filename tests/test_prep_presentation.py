"""Prep presentation keeps navigation and validation attached to real objects."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPersistentModelIndex

from caelab_prep.application.session import PrepSession
from caelab_prep.ui.main_window import MainWindow

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
