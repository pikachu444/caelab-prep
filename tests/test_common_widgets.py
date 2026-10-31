"""Real Qt draft/input and document behavior; no GPU or solver required."""

import os
from pathlib import Path
import subprocess
import sys
import time
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QMainWindow, QMenu, QMessageBox, QToolBar

from caelab_prep.application.contracts import ActionSpec, SetProperties
from caelab_prep.application.neutral import CurveSession
from caelab_prep.ui.gallery import GalleryWindow
from caelab_prep.ui.widgets import CurveTable, ModelTree, NumericEdit, PropertyEditor, VectorEdit


@pytest.fixture
def app(tmp_path):
    instance = QApplication.instance() or QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    return instance


def wait_operation(window):
    deadline = time.monotonic() + 5
    while window._busy and time.monotonic() < deadline:
        QApplication.processEvents()
        QTest.qWait(5)
    assert not window._busy
    QApplication.processEvents()


def test_numeric_draft_keyboard_error_escape_and_finite_values(app):
    editor = NumericEdit(210000, unit="MPa")
    editor.show()
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "1e")
    assert editor.text() == "1e"
    with pytest.raises(ValueError):
        editor.numeric_value()
    assert editor.property("invalid") and editor.text() == "1e"
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert editor.text() == "210000" and not editor.property("invalid")
    for text in ("NaN", "inf", "-inf"):
        editor.setText(text)
        with pytest.raises(ValueError):
            editor.numeric_value()
        assert editor.text() == text
    editor.setText("2.1e5")
    assert editor.numeric_value() == 210000
    editor.close()


def test_vector_validates_together_and_keeps_invalid_component(app):
    editor = VectorEdit((1, 2, 3))
    editor.editors[0].setText("4")
    editor.editors[1].setText("1e")
    with pytest.raises(ValueError):
        editor.values()
    assert [e.text() for e in editor.editors] == ["4", "1e", "3"]
    editor.editors[1].setText("5")
    assert editor.values() == (4, 5, 3)


def test_paste_preview_is_atomic_and_one_apply_one_undo(app):
    session = CurveSession()
    target = next(n.ref for n in session.tree_nodes() if n.ref.kind == "curve")
    table = CurveTable()
    original = session.curve_points(target)
    table.set_points(original)
    revision = session.describe()["revision"]
    calls = []
    def commit(points):
        calls.append(points)
        session.set_curve_points(target, points, session.describe()["revision"])
        table.set_points(points)
    table.pointsEdited.connect(commit)
    table.paste_text("0\t260\n0.1\t400\n0.2\t460")
    assert session.curve_points(target) == original
    assert table.has_draft() and not calls
    assert table.apply_changes()
    assert len(calls) == 1
    assert session.describe()["revision"] == revision + 1
    assert not table.has_draft()
    session.undo()
    assert session.curve_points(target) == original
    before = table.draft_state()["cells"]
    with pytest.raises(ValueError):
        table.paste_text("0\t260\n0.1\tinvalid")
    assert table.draft_state()["cells"] == before
    assert table.paste_text_buffer.endswith("invalid")
    assert not table.apply_changes() and len(calls) == 1


def test_curve_widget_does_not_invent_provider_constraints(app):
    table = CurveTable()
    table.set_points(((2, 1),))
    assert table.points() == ((2., 1.),) and not table.has_draft()
    assert table.paste_text("2 1\n1 2\n1 3") == ((2., 1.), (1., 2.), (1., 3.))


def test_provider_tree_keeps_selection_and_collapsed_groups(app):
    session = CurveSession()
    tree = ModelTree()
    tree.set_nodes(session.tree_nodes())
    material = session.tree_nodes()[0].ref
    selected = []
    tree.nodeSelected.connect(selected.append)
    assert tree.select_ref(material)
    group = tree.model().index(1, 0)
    tree.setExpanded(group, False)
    tree.set_nodes(session.tree_nodes())
    assert tree.selected_ref() == material
    assert not tree.isExpanded(tree.model().index(1, 0))
    assert selected == [material]


def test_unit_selection_converts_display_and_preserves_physical_value(app):
    session = CurveSession()
    material = session.tree_nodes()[0].ref
    editor = PropertyEditor()
    editor.set_fields(session.properties(material))
    unit = editor.unit_selectors["young_modulus"]
    unit.setCurrentText("GPa")
    assert float(editor.editors["young_modulus"].text()) == 210
    session.submit(SetProperties(material, editor.values(), session.describe()["revision"], editor.units()))
    assert next(p.value for p in session.properties(material) if p.name == "young_modulus") == 210000
    editor.editors["young_modulus"].setText("1e")
    unit.setCurrentText("MPa")
    assert unit.currentText() == "GPa" and editor.editors["young_modulus"].text() == "1e"


def test_gallery_real_values_vector_undo_save_reopen_and_stale_draft(app, tmp_path):
    window = GalleryWindow()
    window._allow_close = True
    try:
        material = window.session.tree_nodes()[0].ref
        assert window.select_ref(material)
        editor = window.field_editors["young_modulus"]
        editor.setText("205000")
        vector = window.field_editors["direction"]
        vector.editors[1].setText("2")
        assert window.apply_properties()
        props = {p.name: p.value for p in window.session.properties(material)}
        assert props["young_modulus"] == 205000 and props["direction"] == [1, 2, 0]
        window._history("undo")
        assert next(p.value for p in window.session.properties(material) if p.name == "young_modulus") == 210000
        window._history("redo")
        path = tmp_path / "materials.caeprep"
        assert window.save_project_file(path)
        wait_operation(window)
        assert window.operation_state.status == "succeeded"
        reopened = CurveSession()
        reopened.open_project(path)
        ref = reopened.tree_nodes()[0].ref
        assert next(p.value for p in reopened.properties(ref) if p.name == "young_modulus") == 205000
        window.field_editors["young_modulus"].setText("1e")
        assert not window.save_project_file(path)
        assert window.field_editors["young_modulus"].text() == "1e"
        assert not window.select_ref(next(n.ref for n in window.session.tree_nodes() if n.ref.kind == "curve"))
        window.field_editors["young_modulus"].setText("206000")
        revision = window.session.describe()["revision"]
        window.session.submit(SetProperties(material, {"density": 7800}, revision))
        QApplication.processEvents()
        assert window.field_editors["young_modulus"].text() == "206000"
        assert not window.apply_properties()
        assert next(p.value for p in window.session.properties(material) if p.name == "young_modulus") == 205000
    finally:
        window.close()


def test_gallery_external_document_replacement_keeps_draft_until_reload(app, tmp_path):
    other = CurveSession()
    path = tmp_path / "other.caeprep"
    other.save_project(path)
    window = GalleryWindow()
    window._allow_close = True
    try:
        old_ref = window._target
        window.field_editors["name"].setText("Pending name")
        window.session.open_project(path)
        QApplication.processEvents()
        assert window._target == old_ref
        assert window.field_editors["name"].text() == "Pending name"
        assert not window.apply_properties()
        window.reload_values()
        assert window._target.document_id == other.describe()["document_id"]
        assert window.field_editors["name"].text() != "Pending name"
        window.field_editors["name"].setText("Kept after save failure")
        assert window.save_project_file(tmp_path)
        wait_operation(window)
        assert window.operation_state.status == "failed"
        assert window.field_editors["name"].text() == "Kept after save failure"
        assert window.session.describe()["dirty"]
    finally:
        window.close()


def test_gallery_async_file_operation_locks_mutation_and_reports_artifact(app, tmp_path):
    session = CurveSession()
    save = session.save_project
    started, release = Event(), Event()
    def blocked_save(path):
        started.set()
        assert release.wait(5)
        return save(path)
    session.save_project = blocked_save
    window = GalleryWindow(session)
    window._allow_close = True
    try:
        path = tmp_path / "async.caeprep"
        assert window.save_project_file(path)
        assert started.wait(2)
        QApplication.processEvents()
        assert window._busy and not window.tree.isEnabled()
        assert not window.select_ref(session.tree_nodes()[0].ref)
        assert not window.apply_properties()
        release.set()
        wait_operation(window)
        assert window.operation_state.status == "succeeded"
        assert not window.operation_state.cancellable
        assert str(path) in window.operation_state.artifacts
        assert window.last_operation_result["saved_path"] == str(path)
        assert window.tree.isEnabled()
        assert window.select_ref(session.tree_nodes()[0].ref)
        assert window.open_project_file(path)
        wait_operation(window)
        assert window.operation_state.status == "succeeded"
        assert window._target.document_id == session.describe()["document_id"]
    finally:
        release.set()
        wait_operation(window)
        window.close()


def test_gallery_curve_apply_preserves_name_draft_without_false_revision_conflict(app):
    window = GalleryWindow()
    window._allow_close = True
    try:
        target = window._target
        window.field_editors["name"].setText("Pending curve title")
        points = window.session.curve_points(target)
        points[1][1] += 10
        assert window._commit_curve(points)
        assert window.field_editors["name"].text() == "Pending curve title"
        assert window.apply_properties()
        assert next(p.value for p in window.session.properties(target) if p.name == "name") == "Pending curve title"
        assert window.session.describe()["revision"] == 2
    finally:
        window.close()


def test_keyboard_save_in_active_table_cell_saves_visible_draft(app, tmp_path):
    window = GalleryWindow()
    window._allow_close = True
    try:
        path = tmp_path / "delegate-edit.caeprep"
        assert window.save_project_file(path)
        wait_operation(window)
        window.show()
        window.activateWindow()
        QApplication.processEvents()
        table = window.curve_table.table
        item = table.item(1, 1)
        table.setCurrentItem(item)
        table.editItem(item)
        QApplication.processEvents()
        editor = table.findChild(QLineEdit)
        assert editor is not None
        editor.setFocus()
        editor.selectAll()
        QTest.keyClicks(editor, "333")
        assert item.text() == "310.0"
        QTest.keyClick(editor, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        wait_operation(window)
        assert window.operation_state.status == "succeeded"
        reopened = CurveSession()
        reopened.open_project(path)
        ref = next(n.ref for n in reopened.tree_nodes() if n.ref.object_id == window._target.object_id)
        assert reopened.curve_points(ref)[1][1] == 333
        assert not window.curve_table.has_draft()
    finally:
        window.close()


def test_gallery_close_after_save_waits_for_async_completion(app, tmp_path, monkeypatch):
    path = tmp_path / "close-save.caeprep"
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    window = GalleryWindow()
    window.show()
    window.field_editors["name"].setText("Saved before close")
    window.close()
    assert window._busy and not window._closed
    wait_operation(window)
    assert window._closed and path.exists()
    reopened = CurveSession()
    reopened.open_project(path)
    assert any(node.label == "Saved before close" for node in reopened.tree_nodes())


def test_curve_rename_updates_plot_caption_without_discarding_table_draft(app):
    window = GalleryWindow()
    window._allow_close = True
    try:
        target = next(node.ref for node in window.session.tree_nodes() if node.ref.kind == "curve")
        assert window.select_ref(target)
        window.curve_table.table.item(1, 1).setText("333")
        window.field_editors["name"].setText("Renamed curve")
        assert window.apply_properties()
        assert window.viewport_frame.title.text() == "Renamed curve"
        assert window.curve_table.has_draft()
        assert window.curve_table.points()[1][1] == 333
        assert window.session.curve_points(target)[1][1] == 310
    finally:
        window.close()

def test_shared_qt_imports_do_not_load_rad_or_vtk():
    code = """
import importlib.abc, sys
class Fence(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('vtk','caelab_prep.radioss','caelab_prep.application.session','caelab_prep.application.rad_provider','caelab_prep.ui.main_window')):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Fence())
from caelab_prep.ui.gallery import GalleryWindow
from caelab_prep.ui.widgets import NumericEdit, CurvePlot
from caelab_prep.ui.shell import FileTask
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)


def test_action_registry_shares_identity_and_obeys_host_capability_context_and_state(app):
    from caelab_prep.ui.actions import ActionRegistry
    host = QMainWindow()
    registry = ActionRegistry(host)
    calls = []
    action = registry.register(ActionSpec("edit.apply", "Apply", "Ctrl+Return", "apply",
                                          icon="apply", contexts=("material",), checkable=True),
                               lambda checked: calls.append(checked))
    menu = host.menuBar().addMenu("Edit")
    toolbar = QToolBar(host)
    host.addToolBar(toolbar)
    menu.addAction(action)
    toolbar.addAction(action)
    assert menu.actions()[0] is toolbar.actions()[0] is registry.action("edit.apply")
    registry.refresh({"capabilities": {"apply": False}}, context="material")
    assert not action.isEnabled()
    registry.refresh({"capabilities": {"apply": True}}, context="curve")
    assert not action.isEnabled()
    registry.refresh({"capabilities": {"apply": True}}, context="material", busy=True)
    assert not action.isEnabled()
    registry.refresh({"capabilities": {"apply": True}}, context="material",
                     checked={"edit.apply": True})
    assert action.isEnabled() and action.isChecked()
    menu.actions()[0].trigger()
    assert calls == [False]
    assert not toolbar.actions()[0].isChecked()
    with pytest.raises(ValueError):
        registry.register(ActionSpec("edit.apply", "Duplicate"), lambda: None)
    host.close()


def test_gallery_reference_picker_applies_typed_candidate_undo_and_saves(app, tmp_path):
    window = GalleryWindow()
    window._allow_close = True
    try:
        material = next(node.ref for node in window.session.tree_nodes() if node.ref.kind == "material")
        assert window.select_ref(material)
        spec = next(spec for spec in window.session.properties(material) if spec.name == "reference_curve")
        picker = window.field_editors[spec.name]
        candidate = next(choice for choice in spec.choices if choice is not None and choice != spec.value)
        index = next(i for i in range(picker.count()) if picker.itemData(i) == candidate)
        picker.setCurrentIndex(index)
        assert window.apply_properties()
        assert next(p.value for p in window.session.properties(material) if p.name == spec.name) == candidate
        window._history("undo")
        assert window.field_editors[spec.name].currentData() == spec.value
        window._history("redo")
        path = tmp_path / "picked-reference.caeprep"
        assert window.save_project_file(path)
        wait_operation(window)
        reopened = CurveSession()
        reopened.open_project(path)
        assert next(p.value for p in reopened.properties(material) if p.name == spec.name) == candidate
    finally:
        window.close()


@pytest.mark.parametrize("window_kind", ["rad", "gallery"])
def test_shared_shell_clean_close_accepts_first_request(app, window_kind):
    if window_kind == "rad":
        from caelab_prep.ui.main_window import MainWindow
        window = MainWindow(enable_viewport=False)
    else:
        window = GalleryWindow()
    assert window.actions.action("file.save") is window.save_action
    assert any(window.save_action in menu.actions() for menu in window.findChildren(QMenu))
    assert any(window.save_action in toolbar.actions() for toolbar in window.findChildren(QToolBar))
    window.show()
    app.processEvents()
    assert window.close()
    assert not window.isVisible()


def test_catalogue_browsing_exposes_source_metadata_and_distinct_semantic_icons(app):
    from caelab_prep.ui.catalogue import CatalogueWidget
    from caelab_prep.ui.design import icon
    catalogue = CatalogueWidget()
    numeric = catalogue.scene
    numeric.editor.editors["young_modulus"].setText("199000")
    fallback = icon("card").pixmap(24, 24).toImage()
    for family in ("section", "load", "contact", "set", "select", "result", "job"):
        assert catalogue.select_asset("icon." + family)
        asset = catalogue.selected_asset()
        metadata = catalogue.metadata.toPlainText()
        assert asset.key == "icon." + family
        assert all(value in metadata for value in (asset.source_path, asset.purpose, asset.status, asset.provenance, asset.permission))
        assert icon(family).pixmap(24, 24).toImage() != fallback
        assert catalogue.scene is not numeric
    assert not catalogue.select_asset("missing")
    assert catalogue.select_asset("component.numeric")
    assert catalogue.scene is numeric
    assert numeric.editor.editors["young_modulus"].text() == "199000"
    catalogue.close()


def test_catalogue_numeric_and_curve_scenes_use_real_apply_error_and_undo(app):
    from caelab_prep.ui.catalogue import CatalogueWidget
    catalogue = CatalogueWidget()
    numeric = catalogue.scene
    assert not numeric.editor.editors["density"].isEnabled()
    initial = numeric.session.describe()
    assert not numeric.apply()
    assert numeric.session.describe() == initial
    assert numeric.editor.editors["poisson_ratio"].text() == "1e"
    numeric.editor.editors["poisson_ratio"].setText("0.28")
    numeric.apply_button.click()
    assert numeric.session.describe()["revision"] == initial["revision"] + 1
    assert next(p.value for p in numeric.session.properties(numeric.target) if p.name == "poisson_ratio") == .28
    numeric.undo_button.click()
    assert next(p.value for p in numeric.session.properties(numeric.target) if p.name == "poisson_ratio") == .3
    assert catalogue.select_asset("component.curve")
    curve = catalogue.scene
    original = curve.session.curve_points(curve.target)
    curve.table.paste_text("0 10\n.1 20\n.2 30")
    assert curve.session.curve_points(curve.target) == original
    curve.table.apply_button.click()
    assert curve.session.curve_points(curve.target) == [[0, 10], [.1, 20], [.2, 30]]
    assert curve.plot._points == ((0, 10), (.1, 20), (.2, 30))
    curve.undo_button.click()
    assert curve.session.curve_points(curve.target) == original
    catalogue.close()


@pytest.mark.parametrize("window_kind", ["rad", "gallery"])
def test_external_approved_selection_is_shown_after_draft_revert(app, monkeypatch, window_kind):
    if window_kind == "rad":
        from caelab_prep.application.session import PrepSession
        from caelab_prep.ui.main_window import MainWindow
        session = PrepSession()
        session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/shell_panels_0000.rad")
        window = MainWindow(session, enable_viewport=False)
        source = next(node.ref for node in window.provider.tree_nodes() if node.ref.native_scope == "/MAT/LAW1/1")
        destination = next(node.ref for node in window.provider.tree_nodes() if node.ref.native_scope == "/PART/2")
        window.select_card(source.object_id)
        tree = window.model_tree
        select = window.provider.select
        revert = window._reload_properties
    else:
        window = GalleryWindow()
        session = window.session
        source = next(node.ref for node in session.tree_nodes() if node.ref.kind == "material")
        destination = next(node.ref for node in session.tree_nodes() if node.ref.kind == "curve")
        window.select_ref(source)
        tree = window.tree
        select = session.select
        revert = window.reload_values
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    try:
        editor = window.field_editors["young_modulus"]
        editor.setText("1e")
        editor.setModified(True)
        select(destination)
        app.processEvents()
        assert tree.selected_ref() == source
        assert editor.text() == "1e"
        revert()
        app.processEvents()
        assert tree.selected_ref() == destination
        assert session.active_object() == destination
    finally:
        window._allow_close = True
        window.close()
