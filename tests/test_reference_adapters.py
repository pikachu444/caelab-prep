"""Exercise reference composition through the same two real host interfaces."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import subprocess
import sys
import textwrap
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget, QToolBar

from caelab_prep.application.session import PrepSession
from caelab_prep.ui.gallery import GalleryWindow
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES

pytestmark = pytest.mark.usefixtures("qt_widgets")


def pump():
    for _ in range(3):
        QApplication.processEvents()


def native(key):
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
    window = MainWindow(session, presentation=key, enable_viewport=False)
    window._allow_close = True
    card = next(c for c in session.list_cards() if c["keyword"].startswith("/MAT/"))
    assert window.select_card(card["id"])
    return window


@pytest.mark.parametrize("key", PROFILES)
def test_same_adapter_composes_gallery_and_native_workspaces(key):
    gallery = GalleryWindow(presentation=key)
    rad = native(key)
    gallery._allow_close = True
    for window in (gallery, rad):
        window.resize(1320, 800)
        window.show()
    pump()
    assert gallery.reference_adapter is rad.reference_adapter
    for window in (gallery, rad):
        b = window.reference_bindings
        assert b.editor is window.property_editor
        assert b.tree.selected_ref() is not None
        assert b.model_dock.width() >= 170
        if key in ("comsol", "beidprep"):
            assert b.properties_dock.isVisible()
            assert b.properties_dock.geometry().left() > b.model_dock.geometry().left()
            assert abs(b.properties_dock.geometry().top() - b.model_dock.geometry().top()) < 5
        if key in ("prepomax", "abaqus", "nfx", "meshfree"):
            assert b.dialog is not None
            assert b.properties_dock.isHidden()
            window.edit_properties_action.trigger()
            pump()
            assert b.dialog.isVisible() and b.editor.isVisible()
            b.dialog.reject()
        if key == "prepomax":
            assert b.messages_dock.isVisible()
        window.close()


def test_hypermesh_scalar_finishes_into_existing_history():
    window = GalleryWindow(presentation="hypermesh")
    window._allow_close = True
    material = next(n.ref for n in window.session.tree_nodes() if n.ref.kind == "material")
    window.select_ref(material)
    window.show()
    pump()
    editor = window.field_editors["young_modulus"]
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "205000")
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    pump()
    value = lambda: next(p.value for p in window.session.properties(material) if p.name == "young_modulus")
    assert value() == 205000
    window.undo_action.trigger()
    pump()
    assert value() == 210000
    assert window.apply_button.isVisible()
    window.select_ref(next(n.ref for n in window.session.tree_nodes() if n.ref.kind == "curve"))
    assert window.apply_button.isHidden()
    window.close()


def test_inline_vector_has_explicit_apply_and_one_undo_for_all_components():
    window = GalleryWindow(presentation="hypermesh")
    window._allow_close = True
    material = next(n.ref for n in window.session.tree_nodes() if n.ref.kind == "material")
    window.select_ref(material)
    window.show()
    pump()
    before = window.session.describe()["revision"]
    vector = window.field_editors["direction"]
    for editor, value in zip(vector.editors, ("2", "3", "4")):
        editor.setFocus()
        editor.selectAll()
        QTest.keyClicks(editor, value)
        QTest.keyClick(editor, Qt.Key.Key_Tab)
    pump()
    direction = lambda: next(p.value for p in window.session.properties(material) if p.name == "direction")
    assert window.apply_button.isVisible() and window.revert_button.isVisible()
    assert window.session.describe()["revision"] == before
    assert direction() == [1, 0, 0]
    window.apply_button.click()
    pump()
    assert direction() == [2, 3, 4]
    window.undo_action.trigger()
    pump()
    assert direction() == [1, 0, 0]
    assert not window.session.describe()["can_undo"]
    window.close()


@pytest.mark.parametrize("key", ["prepomax", "abaqus", "nfx", "meshfree"])
def test_gallery_dialog_rejects_invalid_input_and_cancel_restores_value(key):
    window = GalleryWindow(presentation=key)
    window._allow_close = True
    material = next(n.ref for n in window.session.tree_nodes() if n.ref.kind == "material")
    window.select_ref(material)
    window.show()
    window.edit_properties_action.trigger()
    pump()
    dialog = window.property_dialog
    revision = window.session.describe()["revision"]
    window.field_editors["young_modulus"].setText("1e")
    ok = next(b for b in dialog.findChildren(QPushButton) if b.text() == "OK")
    ok.click()
    pump()
    assert dialog.isVisible()
    assert window.session.describe()["revision"] == revision
    dialog.reject()
    pump()
    assert float(window.field_editors["young_modulus"].text()) == 210000
    assert window.session.describe()["revision"] == revision
    window.close()


def test_curve_layouts_offer_side_by_side_and_switchable_pages():
    hm = GalleryWindow(presentation="hypermesh")
    ab = GalleryWindow(presentation="abaqus")
    for window in (hm, ab):
        window._allow_close = True
        window.show()
    pump()
    assert hm.curve_table.isVisible() and hm.plot.isVisible()
    assert hm.curve_table.mapTo(hm, hm.curve_table.rect().topLeft()).x() < hm.plot.mapTo(hm, hm.plot.rect().topLeft()).x()
    pages = ab.reference_bindings.curve_pages
    assert isinstance(pages, QTabWidget)
    pages.setCurrentIndex(0)
    pump()
    assert ab.curve_table.isVisible() and not ab.plot.isVisible()
    pages.setCurrentIndex(1)
    pump()
    assert ab.plot.isVisible() and not ab.curve_table.isVisible()
    hm.close()
    ab.close()


@pytest.mark.parametrize("key", ["prepomax", "abaqus", "nfx", "meshfree"])
def test_native_dialog_cancel_and_ok_use_real_document_history(key):
    window = native(key)
    window.show()
    window.edit_properties_action.trigger()
    pump()
    dialog = window.property_dialog
    before = window.session.describe()["revision"]
    editor = window.field_editors["young_modulus"]
    original = float(editor.text())
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "205000")
    QTest.keyClick(editor, Qt.Key.Key_Tab)
    pump()
    assert window.session.describe()["revision"] == before
    dialog.reject()
    pump()
    assert float(window.field_editors["young_modulus"].text()) == original
    assert window.session.describe()["revision"] == before
    window.edit_properties_action.trigger()
    window.field_editors["young_modulus"].setText("205000")
    ok = next(b for b in dialog.findChildren(QPushButton) if b.text() == "OK")
    ok.click()
    pump()
    assert not dialog.isVisible()
    assert float(window.field_editors["young_modulus"].text()) == 205000
    window.undo_action.trigger()
    pump()
    assert float(window.field_editors["young_modulus"].text()) == original
    window.close()


@pytest.mark.parametrize("key", ("naksha", "prepomax"))
def test_global_view_rows_keep_actions_and_source_panel_geometry(key):
    window = native(key)
    window.resize(1320, 840)
    window.show()
    pump()
    b = window.reference_bindings
    tools = b.selection_tools
    assert tools.parent() is window
    assert window.toolBarArea(tools) == Qt.ToolBarArea.TopToolBarArea
    assert tools.geometry().top() > window.document_toolbar.geometry().top()
    assert tools.geometry().left() < b.model_dock.geometry().right()
    assert tools.geometry().width() >= window.width() - 5
    assert tools.actions()[:3] == [window.fit_action, window.iso_action, window.edges_action]
    assert window.pick_mode.parent() is tools
    if key == "naksha":
        contextual = window.findChild(QToolBar, "referenceContextCommands")
        assert window.document_toolbar.iconSize().width() == 16
        assert contextual.geometry().top() > window.document_toolbar.geometry().top()
        assert tools.geometry().top() > contextual.geometry().top()
        assert window.open_rad_action in window.document_toolbar.actions()
        fraction = b.model_dock.height() / (b.model_dock.height() + b.properties_dock.height())
        assert .52 < fraction < .62
        window.resizeDocks([b.model_dock, b.properties_dock], [350, 300], Qt.Orientation.Vertical)
        pump()
        user_height = b.model_dock.height()
        window.hide()
        window.show()
        pump()
        assert abs(b.model_dock.height() - user_height) < 5
    else:
        assert b.messages_dock.isVisible()
        assert b.messages_dock.geometry().left() >= b.model_dock.geometry().right()
        assert b.model_dock.geometry().bottom() >= b.messages_dock.geometry().bottom() - 2
    window.close()


def test_naksha_history_actions_use_small_quick_bar_instead_of_context_ribbon():
    window = native("naksha")
    window.show()
    pump()
    quick = window.document_toolbar
    assert quick.iconSize().width() == 16
    assert quick.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert window.undo_action in quick.actions() and window.redo_action in quick.actions()
    assert quick.widgetForAction(window.undo_action).defaultAction() is window.undo_action
    assert quick.widgetForAction(window.redo_action).defaultAction() is window.redo_action
    assert quick.actions().index(window.save_action) < quick.actions().index(window.undo_action)
    context = window.findChild(QToolBar, "referenceContextCommands")
    tabs = context.findChild(QTabWidget, "referenceCommands")
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Materials"]
    window.close()


def test_naksha_property_draft_survives_user_resize_and_reshow():
    window = native("naksha")
    window.resize(1320, 840)
    window.show()
    pump()
    editor = window.field_editors["density"]
    revision = window.session.describe()["revision"]
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "1e")
    window.resizeDocks([window.model_dock, window.properties_dock], [300, 350], Qt.Orientation.Vertical)
    pump()
    user_height = window.model_dock.height()
    window.hide()
    window.show()
    pump()
    assert abs(window.model_dock.height() - user_height) < 5
    assert window.field_editors["density"] is editor and editor.text() == "1e"
    assert window.session.describe()["revision"] == revision
    window.close()


def test_independent_host_installs_adapter_without_application_or_concrete_hosts():
    code = textwrap.dedent('''
        import importlib.abc, sys
        class ForbidHosts(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                blocked = ("caelab_prep.application", "caelab_prep.radioss",
                           "caelab_prep.ui.catalogue", "caelab_prep.ui.gallery",
                           "caelab_prep.ui.main_window", "caelab_prep.ui.materials_workspace",
                           "caelab_prep.ui.reference_workspace", "vtk", "vtkmodules")
                if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
                    raise AssertionError("Forbidden presentation dependency: " + fullname)
        sys.meta_path.insert(0, ForbidHosts())
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import (QApplication, QMainWindow, QDockWidget, QTreeView,
            QToolBar, QWidget, QVBoxLayout, QSplitter, QPushButton)
        from caelab_prep.ui.reference_components import ADAPTERS, ReferenceBindings
        from caelab_prep.ui.widgets import PropertyEditor
        app = QApplication([])
        host = QMainWindow()
        host.resize(1200, 800)
        tree, editor = QTreeView(), PropertyEditor()
        panel = QWidget()
        QVBoxLayout(panel).addWidget(editor)
        def dock(title, widget, area):
            item = QDockWidget(title, host)
            item.setWidget(widget)
            host.addDockWidget(area, item)
            return item
        model = dock("Objects", tree, Qt.LeftDockWidgetArea)
        properties = dock("Properties", panel, Qt.LeftDockWidgetArea)
        messages = dock("Output", QWidget(), Qt.BottomDockWidgetArea)
        toolbar = QToolBar(host)
        host.addToolBar(toolbar)
        views = QToolBar()
        view_action = QAction("Fit", host)
        views.addAction(view_action)
        table, plot = QWidget(), QWidget()
        curves = QSplitter()
        curves.addWidget(table)
        curves.addWidget(plot)
        viewport = QWidget()
        layout = QVBoxLayout(viewport)
        layout.addWidget(views)
        layout.addWidget(curves)
        host.setCentralWidget(viewport)
        edit = QAction("Edit", host)
        calls = []
        bindings = ReferenceBindings(host, tree, model, properties, messages, editor,
            toolbar, {"Document": (QAction("Open", host),), "History": (), "Material": (edit,)},
            lambda: calls.append("apply") or True, lambda: calls.append("revert"),
            table, plot, curves, curve_surface=curves, selection_tools=views, viewport=viewport)
        ADAPTERS["prepomax"].install(bindings)
        host.show()
        app.processEvents()
        assert views.parent() is host and views.actions()[0] is view_action
        edit.trigger()
        app.processEvents()
        assert bindings.dialog.isVisible() and editor.isVisible()
        next(button for button in bindings.dialog.findChildren(QPushButton) if button.text() == "OK").click()
        assert calls == ["apply"] and not bindings.dialog.isVisible()
        edit.trigger()
        bindings.dialog.reject()
        assert calls == ["apply", "revert"]
        host.close()
    ''')
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_nfx_curve_table_and_plot_are_simultaneously_visible_in_both_hosts():
    neutral = GalleryWindow(presentation="nfx")
    rad = native("nfx")
    neutral._allow_close = True
    curve = next(node.ref for node in neutral.session.tree_nodes() if node.ref.kind == "curve")
    neutral.select_ref(curve)
    card = next(c for c in rad.session.list_cards() if c["keyword"].startswith("/FUNCT/"))
    rad.select_card(card["id"])
    for window in (neutral, rad):
        window.show()
    rad.property_dialog.open()
    pump()
    for window in (neutral, rad):
        bindings = window.reference_bindings
        assert bindings.table.isVisible() and bindings.plot.isVisible()
        assert bindings.table.mapTo(window, bindings.table.rect().topLeft()).y() != bindings.plot.mapTo(window, bindings.plot.rect().topLeft()).y()
    rad.property_dialog.reject()
    neutral.close()
    rad.close()
