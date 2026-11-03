"""Actual Qt layout at the supported narrow size, without claiming VTK rendering."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
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
        window.setWindowState(Qt.WindowState.WindowNoState)
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
    window = MainWindow(user_model[0], presentation="hypermesh", enable_viewport=False)
    window._allow_close = True
    try:
        window.setWindowState(Qt.WindowState.WindowNoState)
        window.resize(960, 640)
        window.show()
        pump()
        tabs = window.findChild(QTabWidget, "referenceCommands")
        assert tabs is not None
        tabs.setCurrentIndex(next(index for index in range(tabs.count()) if tabs.tabText(index) == "Materials"))
        pump()
        page = tabs.currentWidget()
        groups = page.findChildren(QToolButton, "referenceGroupMenu")
        assert groups

        def assert_commands_reachable():
            for group in page.findChildren(type(groups[0].parentWidget()), "referenceCommandGroup"):
                buttons = group.buttons.findChildren(QToolButton)
                original = {button.defaultAction() for button in buttons}
                assert original and all(action.text() for action in original)
                if group.menu_button.isVisible():
                    assert not group.buttons.isVisible()
                    assert original <= set(group.menu_button.menu().actions())
                    visible = [group.menu_button]
                else:
                    assert group.buttons.isVisible()
                    visible = buttons
                for button in visible:
                    assert button.isVisible() and button.width() >= button.sizeHint().width()
                    position = button.mapTo(page, QPoint())
                    assert 0 <= position.x() and position.x() + button.width() <= page.width()
                    assert 0 <= position.y() and position.y() + button.height() <= page.height()

        assert window.size().width() == 960 and window.size().height() == 640
        assert_commands_reachable()
        # Exercise the reusable group's constrained state inside the 960 host;
        # different system fonts need not collapse at the same window width.
        minimum = page.layout().minimumSize().width()
        preferred = page.layout().sizeHint().width()
        assert minimum < preferred
        maximum = tabs.maximumWidth()
        chrome = tabs.width() - page.width()
        tabs.setMaximumWidth(chrome + minimum + (preferred - minimum) // 2)
        pump()
        assert (window.width(), window.height()) == (960, 640)
        assert minimum <= page.width() < preferred
        assert any(button.isVisible() for button in groups), "Constrained groups need a reachable menu"
        assert_commands_reachable()
        tabs.setMaximumWidth(maximum)
        window.resize(1920, 1080)
        pump()
        assert window.size().width() == 1920 and window.size().height() == 1080
        assert_commands_reachable()
        # Native font metrics can require more than 1920 px for every full label.
        wide = max(1920, window.width() + page.layout().sizeHint().width() - page.width())
        window.resize(wide, 1080)
        pump()
        assert not any(button.isVisible() for button in groups)
        assert_commands_reachable()
    finally:
        window.close()
        window.deleteLater()


def test_native_beid_commands_remain_reachable_through_menus_at_960(user_model):
    window = MainWindow(user_model[0], presentation="beidprep", enable_viewport=False)
    window._allow_close = True
    try:
        window.setWindowState(Qt.WindowState.WindowNoState)
        window.resize(960, 640)
        window.show()
        pump()
        assert (window.width(), window.height()) == (960, 640)
        menu_bar = window.menuBar()
        menus = {action.text().replace("&", ""): action.menu() for action in menu_bar.actions()}
        assert list(menus)[:6] == ["File", "Edit", "Model", "Mesh", "Conditions", "View"]
        model = window.modeling.actions
        expected = {
            "File": (window.mesh_workflow.new_action, window.open_rad_action, window.open_project_action,
                     window.source_models_action, window.save_action, window.save_as_action,
                     window.export_action, window.mesh_workflow.export_action, window.close_action),
            "Edit": (window.undo_action, window.redo_action, window.reload_properties_action),
            "Model": (window.edit_properties_action,) + tuple(model[key] for key in ("material.create", "section.create", "solid_section.create",
                          "group.create", "element_group.create", "surface.create", "coordinate_system.create",
                          "object.edit", "object.copy", "object.delete", "part.assign")),
            "Mesh": (window.mesh_import.action, window.mesh_workflow.mesh_action, window.node_move_action,
                     window.node_merge_action, window.prepared_mesh_action),
            "Conditions": tuple(model[key + ".create"] for key in
                                ("curve", "constraint", "load", "velocity", "contact"))
                          + (window.mesh_workflow.cases_action,),
            "View": (window.fit_action, window.fit_selected_action, window.iso_action,
                     *window.standard_view_actions, window.edges_action, window.hide_selected_action,
                     window.isolate_action, window.show_all_action),
        }
        for title, actions in expected.items():
            menu = menus[title]
            assert set(actions) <= set(menu.actions()), title
            assert all(action.text() and action.isVisible() for action in actions), title
            assert menu.menuAction().isVisible()
            assert menu_bar.contentsRect().contains(menu_bar.actionGeometry(menu.menuAction())), title
        buttons = {button.accessibleName(): button for button in window.document_toolbar.findChildren(QToolButton)}
        for title in ("Model", "Mesh", "Conditions"):
            button = buttons[title + " commands"]
            assert button.menu() is menus[title]
            assert button.isVisible() and button.width() >= button.sizeHint().width()
            position = button.mapTo(window.document_toolbar, QPoint())
            assert 0 <= position.x() and position.x() + button.width() <= window.document_toolbar.width()
            assert 0 <= position.y() and position.y() + button.height() <= window.document_toolbar.height()
    finally:
        window.close()
        window.deleteLater()
