"""Actual Qt layout at the supported narrow size, without claiming VTK rendering."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QTabWidget, QToolButton

from caelab_prep.ui.main_window import MainWindow
from test_modeling_workflow import user_model

pytestmark = pytest.mark.usefixtures("qt_widgets")


def pump():
    for _ in range(5):
        QApplication.processEvents()


@pytest.mark.parametrize("profile", ("hypermesh", "naksha", "comsol", "beidprep"))
def test_narrow_inline_part_fields_fit_without_horizontal_scroll(user_model, profile):
    session = user_model[0]
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True
    try:
        window.resize(960, 640)
        window.show()
        part = next(card for card in session.list_cards() if card["keyword"] == "/PART/903")
        window.select_card(part["id"])
        pump()
        panel = window.property_editor
        assert (window.width(), window.height()) == (960, 640)
        assert window.viewport_frame.width() >= 100
        assert panel.scroll.horizontalScrollBar().maximum() == 0
        for name, editor in panel.editors.items():
            # Vertical scrolling is deliberate in a short inspector. Every
            # scalar/reference must remain horizontally visible after scroll.
            panel.scroll.ensureWidgetVisible(editor)
            pump()
            origin = editor.mapTo(panel.scroll.viewport(), QPoint())
            assert origin.x() >= 0, (name, origin.x())
            assert origin.x() + editor.width() <= panel.scroll.viewport().width(), name
            if hasattr(editor, "currentText"):
                assert editor.currentText()
                assert editor.toolTip() == editor.currentText()
        numbers = [editor.text() for editor in panel.editors.values() if hasattr(editor, "text")]
        assert "903" in numbers and "1" in numbers
        assert session.describe()["revision"] == 0
    finally:
        window.close()
        window.deleteLater()


def test_narrow_command_groups_offer_full_action_names_and_expand_when_wide(user_model):
    window = MainWindow(user_model[0], presentation="beidprep", enable_viewport=False)
    window._allow_close = True
    try:
        window.resize(960, 640)
        window.show()
        pump()
        tabs = window.findChild(QTabWidget, "referenceCommands")
        page = tabs.currentWidget()
        groups = page.findChildren(QToolButton, "referenceGroupMenu")
        collapsed = [button for button in groups if button.isVisible()]
        assert collapsed, "The crowded MODEL commands need a reachable group menu"
        for button in collapsed:
            assert button.width() >= button.sizeHint().width()
            assert button.menu().actions()
            assert all(action.text() for action in button.menu().actions())
        # Each original command remains either a full direct button or an
        # entry in its named group menu, never a squeezed unreadable label.
        for group in page.findChildren(type(groups[0].parentWidget()), "referenceCommandGroup"):
            if group.menu_button.isVisible():
                assert not group.buttons.isVisible()
            else:
                assert group.buttons.isVisible()
                for button in group.buttons.findChildren(QToolButton):
                    assert button.width() >= button.sizeHint().width()
        window.resize(1920, 1080)
        pump()
        assert not any(button.isVisible() for button in groups)
    finally:
        window.close()
        window.deleteLater()
