"""Reach the real selection-mode menu without an OpenGL/VTK renderer."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolBar, QWidget

from caelab_prep.application import PrepSession
from caelab_prep.ui.comparison import ComparisonWindow
from caelab_prep.ui.reference_profiles import PROFILES

pytestmark = pytest.mark.usefixtures("qt_widgets")


def pump():
    for _ in range(3):
        QApplication.processEvents()


class ModeProbe(QWidget):
    """Observe the production mode callback, deliberately without a renderer."""

    def __init__(self, parent):
        super().__init__(parent)
        self.modes = []

    def set_pick_mode(self, mode):
        self.modes.append(mode)

    def set_selection(self, selection):
        pass

    def shutdown(self):
        pass


@pytest.mark.parametrize("profile", PROFILES)
def test_selection_type_menu_is_reachable_at_960_and_shares_combo_state(profile):
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
    comparison = ComparisonWindow(session, native=True, enable_viewport=False)
    comparison._allow_close = True
    comparison.resize(960, 640)
    comparison.show()
    assert comparison.select_profile(profile)
    pump()
    window = comparison.active_view
    menu = window.selection_type_menu
    assert not window.pick_mode.isEnabled() and not menu.isEnabled()
    part = next(c for c in session.list_cards() if c["keyword"].startswith("/PART/"))
    assert window.select_card(part["id"])
    pump()
    before = session.selection()
    revision = session.describe()["revision"]
    probe = ModeProbe(window)
    window.viewport = probe
    window._refresh_actions()
    assert window.pick_mode.isEnabled() and menu.isEnabled()
    assert comparison.size().width() == 960 and comparison.size().height() == 640
    toolbar = window.findChild(QToolBar, "modelViewCommands")
    assert toolbar is not None and toolbar.isAncestorOf(window.pick_mode)

    # Open the actual View menu and its submenu, then click the actual node item.
    bar = window.menuBar()
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton,
                     pos=bar.actionGeometry(window._view_menu.menuAction()).center())
    pump()
    assert window._view_menu.isVisible()
    window._view_menu.setActiveAction(menu.menuAction())
    QTest.keyClick(window._view_menu, Qt.Key.Key_Right)
    pump()
    assert menu.isVisible()
    elements, nodes = menu.actions()
    assert elements.isChecked() and not nodes.isChecked()
    QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(nodes).center())
    pump()
    assert window.pick_mode.currentText() == "Nodes" and nodes.isChecked()
    assert not elements.isChecked() and probe.modes == ["node"]
    assert session.selection() == before and session.describe()["revision"] == revision
    elements.trigger()
    assert window.pick_mode.currentText() == "Elements" and elements.isChecked()
    assert probe.modes == ["node", "element"]

    # Changes made through the retained toolbar control update the same menu.
    window.pick_mode.setCurrentIndex(1)
    pump()
    assert nodes.isChecked() and not elements.isChecked()
    assert probe.modes == ["node", "element", "node"]
    window.pick_mode.setEnabled(False)
    assert not menu.isEnabled() and not elements.isEnabled() and not nodes.isEnabled()
    elements.trigger()
    assert window.pick_mode.currentText() == "Nodes" and probe.modes[-1] == "node"
    window.pick_mode.setEnabled(True)
    assert menu.isEnabled() and elements.isEnabled() and nodes.isEnabled()
    assert session.selection() == before
