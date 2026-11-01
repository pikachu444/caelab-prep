"""Exercise real operation controls and exported user-model values across views."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from types import MethodType
import pytest
from PySide6.QtCore import Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from caelab_prep.application.session import PrepSession
from caelab_prep.ui.comparison import ComparisonWindow
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_modeling_workflow import user_model  # shared independent, nonsequential INCLUDE input

pytestmark = pytest.mark.usefixtures("qt_widgets")


def pump():
    for _ in range(3):
        QApplication.processEvents()


def wait_file(window):
    until = time.monotonic() + 8
    while window._busy and time.monotonic() < until:
        QApplication.processEvents()
        time.sleep(.005)
    pump()
    assert not window._busy
    assert window.operation_state.status == "succeeded"


def enter(panel, name, value):
    editor = panel.editor.editors[name]
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, str(value))


def click_apply(window):
    QTest.mouseClick(window.modeling.panel.apply_button, Qt.MouseButton.LeftButton)
    pump()


def card(session, keyword):
    return next(c for c in session.list_cards() if c["keyword"] == keyword)


@pytest.mark.parametrize("key", PROFILES)
def test_all_native_approaches_create_assign_copy_safe_delete_refusal_and_export(user_model, tmp_path, key):
    session, _, _, geometry_bytes, _ = user_model
    window = MainWindow(session, presentation=key, enable_viewport=False)
    window._allow_close = True
    window.show()
    pump()
    op = window.modeling
    op.actions["material.create"].trigger()
    pump()
    assert op.active and op.panel.isVisible()
    assert bool(getattr(window, "property_dialog", None)) == (key in ("prepomax", "abaqus", "nfx", "meshfree"))
    for name, value in {"name": "UI steel", "native_id": 41, "density": 7.91e-9,
                        "young_modulus": 203456, "poisson_ratio": .287}.items():
        enter(op.panel, name, value)
    assert session.describe()["revision"] == 0
    click_apply(window)
    assert not op.active and session.describe()["revision"] == 1
    material = window.provider.ref_for_card(card(session, "/MAT/LAW1/41"))

    op.actions["section.create"].trigger()
    for name, value in {"name": "UI shell", "native_id": 207, "thickness": 2.375}.items():
        enter(op.panel, name, value)
    click_apply(window)
    section = window.provider.ref_for_card(card(session, "/PROP/SHELL/207"))
    assert session.describe()["revision"] == 2

    assert window.select_card(card(session, "/PART/902")["id"])
    op.actions["part.assign"].trigger()
    for name, ref in (("material", material), ("property", section)):
        combo = op.panel.editor.editors[name]
        combo.setCurrentIndex(combo.findData(ref))
    click_apply(window)
    assert not op.active, op.panel.error.text()
    assert session.describe()["revision"] == 3
    assert session.part_assignments(card(session, "/PART/902")["id"])["property_id"] == section.object_id
    window.undo_action.trigger(); pump()
    assert session.part_assignments(card(session, "/PART/902")["id"])["property_id"] != section.object_id
    window.redo_action.trigger(); pump()

    assert window.select_card(section.object_id)
    op.actions["object.copy"].trigger()
    enter(op.panel, "name", "Independent section")
    click_apply(window)
    copied = next(c for c in session.list_cards() if c["title"] == "Independent section")
    assert copied["id"] != section.object_id
    assert window.select_card(copied["id"])
    op.actions["object.delete"].trigger()
    revision = session.describe()["revision"]
    click_apply(window)
    # Unknown native cards can reference this material/property: the UI must
    # retain the failed delete draft and the provider must not guess safety.
    assert op.active and "unverified" in op.panel.error.text().lower()
    assert session.describe()["revision"] == revision
    assert any(c["id"] == copied["id"] for c in session.list_cards())
    QTest.mouseClick(op.panel.cancel_button, Qt.MouseButton.LeftButton); pump()

    assert window.save_project_file(tmp_path / (key + ".caeprep"))
    wait_file(window)
    reopened = PrepSession(); reopened.open_project(tmp_path / (key + ".caeprep"))
    assert reopened.part_assignments(card(reopened, "/PART/902")["id"])["material_id"] == material.object_id
    exported = tmp_path / key / "ui_0000.rad"
    window.export_rad_file(exported); wait_file(window)
    assert (exported.parent / "geometry.inc").read_bytes() == geometry_bytes
    lines = exported.read_text().splitlines()
    part_start = lines.index("/PART/902")
    assignment = lines[part_start + 2]
    assert int(assignment[:10]) == 207 and int(assignment[10:20]) == 41
    material_start = lines.index("/MAT/LAW1/41")
    assert float(lines[material_start + 3][:20]) == 203456


@pytest.mark.parametrize("key", PROFILES)
def test_known_only_document_delete_and_history_in_each_approach(user_model, key):
    _, inputs, *_ = user_model
    root = inputs / "assembly_0000.rad"
    opaque = b"/FUTURE/OPAQUE/77\r\nUntouched unsupported block  \r\n  9.876D+05  opaque  \r\n"
    root.write_bytes(root.read_bytes().replace(opaque, b""))
    session = PrepSession(); session.open_rad(root)
    window = MainWindow(session, presentation=key, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    assert window.select_card(card(session, "/PROP/SHELL/19")["id"])
    op = window.modeling
    op.actions["object.copy"].trigger()
    enter(op.panel, "name", "Independent known-only section")
    click_apply(window)
    copied = next(c for c in session.list_cards() if c["title"] == "Independent known-only section")
    assert window.select_card(copied["id"])
    op.actions["object.delete"].trigger()
    click_apply(window)
    assert not op.active, op.panel.error.text()
    assert not any(c["id"] == copied["id"] for c in session.list_cards())
    window.undo_action.trigger(); pump()
    assert any(c["id"] == copied["id"] for c in session.list_cards())
    window.redo_action.trigger(); pump()
    assert not any(c["id"] == copied["id"] for c in session.list_cards())


def test_operation_draft_blocks_navigation_save_and_preserves_invalid_and_stale_input(user_model, tmp_path):
    session = user_model[0]
    comparison = ComparisonWindow(session, native=True, enable_viewport=False)
    comparison._allow_close = True
    comparison.show(); pump()
    window = comparison.active_view
    op = window.modeling
    op.actions["material.create"].trigger()
    enter(op.panel, "name", "Retained new material")
    enter(op.panel, "density", "1e")
    assert not window.save_project_file(tmp_path / "not-created.caeprep")
    assert not comparison.select_profile("comsol")
    assert not window.select_card(card(session, "/PART/902")["id"])
    click_apply(window)
    assert op.active and session.describe()["revision"] == 0
    assert op.panel.editor.editors["density"].text() == "1e"
    for name, value in {"density": 7.8e-9, "young_modulus": 200000}.items():
        enter(op.panel, name, value)
    # Independent API edit invalidates this operation's original revision.
    session.set_field(card(session, "/MAT/ELAST/00017")["id"], "young_modulus", 72000)
    pump()
    click_apply(window)
    assert op.active and session.describe()["revision"] == 1
    assert op.panel.editor.editors["name"].text() == "Retained new material"
    assert "changed" in op.panel.error.text().lower()
    QTest.mouseClick(op.panel.cancel_button, Qt.MouseButton.LeftButton); pump()
    assert not op.active and comparison.select_profile("comsol")
    assert not any(c["title"] == "Retained new material" for c in session.list_cards())


@pytest.mark.parametrize("answer", (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard))
def test_close_operation_draft_cancel_keeps_input_discard_does_not_create(user_model, monkeypatch, answer):
    session = user_model[0]
    window = MainWindow(session, enable_viewport=False)
    window.show(); pump()
    window.modeling.actions["material.create"].trigger()
    enter(window.modeling.panel, "name", "Uncommitted")
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: answer)
    window.close(); pump()
    assert session.describe()["revision"] == 0
    assert window.isVisible() == (answer == QMessageBox.StandardButton.Cancel)
    assert window.modeling.active == (answer == QMessageBox.StandardButton.Cancel)
    assert not any(c["title"] == "Uncommitted" for c in session.list_cards())


def test_native_multiselect_display_actions_and_all_approach_switches(user_model, monkeypatch):
    # Production VTK datasets/camera/selection, with Render deliberately disabled.
    # This checks the GUI-to-pipeline contract, not pixels or driver acceptance.
    from test_viewport_visibility import viewport as dataset_viewport
    from caelab_prep.ui import viewport as viewport_module
    production_viewport = viewport_module.MeshViewport

    class DataViewport(QWidget):
        entityPicked = Signal(dict)
        diagnostic = Signal(str)
        _selection_cell_indices = viewport_module.MeshViewport._selection_cell_indices
        _selection_node_indices = viewport_module.MeshViewport._selection_node_indices

        def __init__(self, parent=None):
            super().__init__(parent)
            self.pipeline = dataset_viewport()
            self.pipeline.isometric_view = MethodType(production_viewport.isometric_view, self.pipeline)

        def set_mesh(self, data, *, reset_camera=True):
            self.pipeline.set_mesh(data, reset_camera=reset_camera)

        def set_selection(self, selection):
            self.pipeline.set_selection(selection)

        def hide_parts(self, parts):
            self.pipeline.hide_parts(parts)

        def show_all_parts(self):
            self.pipeline.show_all_parts()

        def fit_selection(self, selection):
            return self.pipeline.fit_selection(selection)

        def shutdown(self):
            pass

    monkeypatch.setattr(viewport_module, "MeshViewport", DataViewport)
    session = user_model[0]
    comparison = ComparisonWindow(session, native=True, enable_viewport=True)
    comparison._allow_close = True
    comparison.show(); pump()
    window = comparison.active_view
    parts = tuple(window.provider.ref_for_card(card(session, keyword))
                  for keyword in ("/PART/902", "/PART/903"))

    def click_part(ref, modifier=Qt.KeyboardModifier.NoModifier):
        index = window.model_tree._indices[ref].index()
        window.model_tree.scrollTo(index)
        QTest.mouseClick(window.model_tree.viewport(), Qt.MouseButton.LeftButton, modifier,
                         window.model_tree.visualRect(index).center())
        pump()

    click_part(parts[0])
    click_part(parts[1], Qt.KeyboardModifier.ControlModifier)
    assert set(window.model_tree.selected_refs()) == set(parts)
    assert set(session.selected_objects()) == set(parts)
    assert session.active_object() == parts[1]
    assert set(session.selection()["ids"]) == {7001, 9007}
    assert not window.modeling.actions["part.assign"].isEnabled()  # no fake batch assignment
    window.hide_selected_action.trigger(); pump()
    assert window.viewport.pipeline._visible_grid.GetNumberOfCells() == 0
    assert set(session.selection()["ids"]) == {7001, 9007}
    window.show_all_action.trigger(); pump()
    assert window.viewport.pipeline._visible_grid.GetNumberOfCells() == 2

    # A single part drives isolate and selection-fit; geometry lives in another INCLUDE.
    click_part(parts[0])
    window.isolate_action.trigger(); pump()
    assert window.viewport.pipeline._visible_grid.GetNumberOfCells() == 1
    window.fit_selected_action.trigger(); pump()
    assert window.viewport.pipeline._renderer.GetActiveCamera().GetFocalPoint() == (1, .5, 0)
    # Public multi-selection from another client must update every tree without
    # profile activation reissuing a single-object selection command.
    session.select_objects(parts, active=parts[1]); pump()
    for key in (*PROFILES, "hypermesh"):
        assert comparison.select_profile(key)
        pump()
        window = comparison.active_view
        assert set(window.model_tree.selected_refs()) == set(parts)
        assert session.active_object() == parts[1]
        assert set(session.selection()["ids"]) == {7001, 9007}
        assert window.viewport.pipeline._visible_grid.GetNumberOfCells() == 1, (key, window._display_state.hidden,
                                                                               window.viewport.pipeline._hidden_parts)
        assert window.show_all_action.isEnabled()
        assert not any("Mesh display failed" in window.messages.topLevelItem(i).text(1)
                       for i in range(window.messages.topLevelItemCount()))
    window.show_all_action.trigger(); pump()
    assert all(view.viewport.pipeline._visible_grid.GetNumberOfCells() == 2 for view in comparison.views.values())
    click_part(parts[1], Qt.KeyboardModifier.ControlModifier)
    assert session.selected_objects() == (parts[0],) and session.active_object() == parts[0]
    click_part(parts[0], Qt.KeyboardModifier.ControlModifier)
    assert session.selected_objects() == () and session.active_object() is None
    assert session.selection()["ids"] == []
    session.select_objects(parts, active=parts[1]); pump()
    window.modeling.actions["material.create"].trigger(); pump()
    click_part(parts[0])
    assert window.modeling.active and set(window.model_tree.selected_refs()) == set(parts)
    assert set(session.selected_objects()) == set(parts)
    window.modeling.panel.cancel_button.click(); pump()
    assert session.describe()["revision"] == 0 and not session.describe()["dirty"]


@pytest.mark.parametrize("key", PROFILES)
def test_operation_controls_remain_reachable_at_960_by_640(user_model, key):
    comparison = ComparisonWindow(user_model[0], native=True, enable_viewport=False)
    comparison._allow_close = True
    comparison.resize(960, 640)
    comparison.show()
    assert comparison.select_profile(key)
    pump()
    window = comparison.active_view
    window.modeling.actions["material.create"].trigger(); pump()
    panel = window.modeling.panel
    assert comparison.width() == 960 and comparison.height() == 640
    dialog = getattr(window, "property_dialog", None)
    if dialog is not None:
        assert dialog.height() <= 600
    if key == "comsol":
        assert panel.editor.scroll.horizontalScrollBar().maximum() == 0
    for button in (panel.apply_button, panel.cancel_button):
        assert button.isVisible() and button.visibleRegion().contains(button.rect().center())
    # The scroll area must expose every draft field without moving the action row.
    for name in ("name", "native_id", "density", "young_modulus", "poisson_ratio"):
        editor = panel.editor.editors[name]
        panel.editor.scroll.ensureWidgetVisible(editor)
        pump()
        assert editor.visibleRegion().contains(editor.rect().center()), (key, name)
    QTest.mouseClick(panel.cancel_button, Qt.MouseButton.LeftButton); pump()
    assert not window.modeling.active
