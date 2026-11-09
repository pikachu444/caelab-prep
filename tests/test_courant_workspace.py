"""Native command surfaces and explicit FORM/TEXT edits with isolated settings."""
import os
from pathlib import Path
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from caelab_prep.application.rad_provider import display_title
from caelab_prep.application.session import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.comparison import ComparisonWindow
from caelab_prep.ui.reference_profiles import PROFILES

pytestmark = pytest.mark.usefixtures("qt_widgets")
FIXTURE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"


def model_window(presentation=None, source=FIXTURE):
    session = PrepSession()
    session.open_rad(source)
    window = MainWindow(session, enable_viewport=False, presentation=presentation)
    material = next(card for card in session.list_cards() if card["keyword"].startswith("/MAT/"))
    assert window.select_card(material["id"])
    return window, material


def wait_file(window):
    deadline = time.monotonic() + 10
    while window._busy and time.monotonic() < deadline:
        QApplication.processEvents()
        QTest.qWait(5)
    assert not window._busy
    QApplication.processEvents()


@pytest.mark.parametrize("presentation", [None, "beidprep"])
def test_native_classification_and_adjacent_inspector(presentation):
    window, _ = model_window(presentation)
    menus = {action.text().replace("&", ""): action.menu() for action in window.menuBar().actions()}
    assert list(menus)[:6] == ["File", "Edit", "Model", "Mesh", "Conditions", "View"]
    model_actions = menus["Model"].actions()
    for key in ("material.create", "section.create", "part.assign"):
        assert window.modeling.actions[key] in model_actions
    assert window.document_toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert not window.findChildren(QLabel, "applicationBrand")
    assert window.property_tabs.tabText(0) == "FORM"
    assert window.property_tabs.tabText(1) == "TEXT"
    assert window.reference_adapter.docks.adjacent
    assert "OPENRADIOSS" not in window.document_state.text()
    assert window.document_state.isHidden()


def test_text_apply_one_undo_save_reopen_and_native_output(tmp_path):
    window, material = model_window()
    session = window.session
    before = session.card_text(material["id"])
    revision = session.describe()["revision"]
    assert window._begin_card_text()
    assert not window.property_editor.isEnabled()
    draft = window.raw_source.toPlainText().replace("210000", "205000", 1)
    window.raw_source.setPlainText(draft)
    assert not window.save_project_file(tmp_path / "blocked.caeprep")
    assert not (tmp_path / "blocked.caeprep").exists()
    assert window._apply_card_text()
    assert session.describe()["revision"] == revision + 1
    assert window.property_editor.isEnabled()
    assert window.property_editor.specs["young_modulus"].value == 205000
    applied = session.card_text(material["id"])
    assert "205000" in applied
    window.undo_action.trigger()
    assert session.card_text(material["id"]) == before
    window.redo_action.trigger()
    assert session.card_text(material["id"]) == applied
    path = tmp_path / "edited.caeprep"
    window.save_project_file(path)
    wait_file(window)
    reopened = PrepSession()
    reopened.open_project(path)
    assert reopened.card_text(material["id"]) == applied
    output = tmp_path / "edited_0000.rad"
    reopened.export_rad(output)
    native = PrepSession()
    native.open_rad(output)
    actual = next(card for card in native.list_cards() if card["keyword"] == material["keyword"])
    assert next(field["value"] for field in native.card_fields(actual["id"])
                if field["name"] == "young_modulus") == 205000


def test_invalid_text_and_external_replacement_preserve_draft():
    window, material = model_window()
    assert window._begin_card_text()
    text = window.raw_source.toPlainText().replace("210000", "badval", 1)
    window.raw_source.setPlainText(text)
    revision = window.session.describe()["revision"]
    assert not window._apply_card_text()
    assert window.raw_source.toPlainText() == text
    assert window.session.describe()["revision"] == revision
    other = next(card for card in window.session.list_cards() if card["keyword"].startswith("/PART/"))
    assert not window.select_card(other["id"])
    assert window._selected_card_id == material["id"]
    window.session.open_rad(FIXTURE)
    QApplication.processEvents()
    assert not window._apply_card_text()
    assert window.raw_source.toPlainText() == text
    window._cancel_card_text()
    assert window._card_text_draft is None
    assert not window._replacement_conflict


def test_edit_uses_full_card_instead_of_truncated_preview(tmp_path):
    source = tmp_path / "large.rad"
    text = FIXTURE.read_text(encoding="latin-1")
    text = text.replace("STEEL\n", "STEEL\n#" + "x" * 100_100 + "\n", 1)
    source.write_text(text, encoding="latin-1")
    window, material = model_window(source=source)
    assert "Preview truncated" in window.raw_source.toPlainText()
    assert window._begin_card_text()
    full = window.session.card_text(material["id"]).replace("\r\n", "\n")
    assert window.raw_source.toPlainText() == full
    assert "Preview truncated" not in window.raw_source.toPlainText()
    window._cancel_card_text()


def test_first_launch_maximizes_and_valid_geometry_is_restored(tmp_path):
    settings = QSettings(str(tmp_path / "layout.ini"), QSettings.Format.IniFormat)
    first = MainWindow(enable_viewport=False, settings=settings)
    assert first.isMaximized()
    first.setWindowState(Qt.WindowState.WindowNoState)
    first.resize(1100, 740)
    settings.setValue("windowGeometry", first.saveGeometry())
    restored = MainWindow(enable_viewport=False, settings=settings)
    assert not restored.isMaximized()


def test_beidprep_resizes_after_show_and_preserves_manual_dock_widths():
    window, _ = model_window()
    window._allow_close = True
    window.setWindowState(Qt.WindowState.WindowNoState)
    window.resize(960, 640); window.show(); QApplication.processEvents()
    window.resize(1440, 900); QApplication.processEvents()
    assert window.model_dock.width() >= 170
    assert window.properties_dock.geometry().left() > window.model_dock.geometry().left()
    assert window.model_dock.width() + window.properties_dock.width() <= .32 * window.width()
    assert window.viewport_frame.width() >= .70 * window.width()
    from PySide6.QtCore import QPoint
    rect = window.model_dock.geometry()
    separator = QPoint(rect.right() + 1, rect.center().y())
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=separator)
    QTest.mouseMove(window, separator + QPoint(30, 0))
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=separator + QPoint(30, 0))
    assert not window._automatic_sidebar
    window.resizeDocks([window.model_dock, window.properties_dock], [280, 300], Qt.Orientation.Horizontal)
    QApplication.processEvents()
    widths = window.model_dock.width(), window.properties_dock.width()
    window.resize(1600, 900); QApplication.processEvents()
    assert (window.model_dock.width(), window.properties_dock.width()) == widths
    window.close()


def test_old_dock_state_resets_but_current_manual_layout_restores(tmp_path):
    settings = QSettings(str(tmp_path / "dock-version.ini"), QSettings.Format.IniFormat)
    first = MainWindow(enable_viewport=False, settings=settings)
    first.setWindowState(Qt.WindowState.WindowNoState)
    first.show(); first.resize(1440, 900); QApplication.processEvents()
    first.resizeDocks([first.model_dock, first.properties_dock], [350, 400], Qt.Orientation.Horizontal)
    QApplication.processEvents()
    geometry, old, current = first.saveGeometry(), first.saveState(3), first.saveState(4)
    first.close()
    settings.setValue("windowGeometry", geometry)
    settings.setValue("windowState", old)
    reset = MainWindow(enable_viewport=False, settings=settings)
    reset.show(); reset.resize(1440, 900); QApplication.processEvents()
    assert reset._automatic_sidebar and reset.viewport_frame.width() >= reset.width() * .70
    reset.close()
    settings.setValue("windowGeometry", geometry)
    settings.setValue("windowState", current)
    restored = MainWindow(enable_viewport=False, settings=settings)
    restored.resize(1440, 900); restored.show(); QApplication.processEvents()
    assert not restored._automatic_sidebar
    assert restored.model_dock.width() == 350 and restored.properties_dock.width() == 400
    restored.close()


def test_generated_uuid_hidden_without_changing_arbitrary_names():
    suffix = "caelab:surface:159aa420-d6a4-4a35-b096-a085d72372ca"
    assert display_title("Bracket: " + suffix) == "Bracket"
    assert display_title(suffix) == "CAD surface"
    for title in ("user UUID 159aa420-d6a4-4a35-b096-a085d72372ca", suffix + " notes", "bracket"):
        assert display_title(title) == title


def test_tree_visibility_uses_host_palette_without_selection_or_history_change():
    window, material = model_window()
    part = next(card for card in window.session.list_cards() if card["keyword"] == "/PART/1")
    ref = window.provider.ref_for_card(part)
    key = (ref.resource_id, ref.native_scope)

    class Viewport(QWidget):
        def part_colors(self):
            return {key: "#6b9cc2"}

        def show_all_parts(self):
            self.hidden = ()

        def hide_parts(self, refs):
            self.hidden = refs

    viewport = Viewport(window)
    window.viewport = viewport
    window._refresh_tree_appearances()
    model = window.model_tree.model()
    item = next(model.item(row).child(child) for row in range(model.rowCount())
                for child in range(model.item(row).rowCount())
                if model.item(row).child(child).data(Qt.ItemDataRole.UserRole) == ref)
    visible = item.index().siblingAtColumn(3)
    assert visible.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    assert item.index().siblingAtColumn(4).data(Qt.ItemDataRole.DecorationRole).name() == "#6b9cc2"
    revision = window.session.describe()["revision"]
    window.model_tree.visibilityRequested.emit(ref, False)
    assert key in viewport.hidden
    assert visible.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert window._selected_card_id == material["id"]
    assert window.session.describe()["revision"] == revision
    window.viewport = None


def test_text_draft_blocks_switch_and_cancel_releases_all_eight_presentations():
    session = PrepSession()
    session.open_rad(FIXTURE)
    comparison = ComparisonWindow(session, native=True, enable_viewport=False)
    material = next(card for card in session.list_cards() if card["keyword"].startswith("/MAT/"))
    assert comparison.active_view.select_card(material["id"])
    revision = session.describe()["revision"]
    for key in PROFILES:
        assert comparison.select_profile(key)
        view = comparison.active_view
        assert view._begin_card_text()
        draft = view.raw_source.toPlainText().replace("210000", "badval", 1)
        view.raw_source.setPlainText(draft)
        other = "beidprep" if key != "beidprep" else "hypermesh"
        assert not comparison.select_profile(other)
        assert comparison.active_view is view
        assert view.raw_source.toPlainText() == draft
        view._cancel_card_text()
        assert comparison.select_profile(other)
    assert session.describe()["revision"] == revision
