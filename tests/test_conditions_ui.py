"""Real G2 controls, provider transactions and independent native export checks."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from types import MethodType
from PySide6.QtCore import Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_condition_workflow import model, _block, _card, _create_conditions
from test_modeling_ui import enter, click_apply, pump, wait_file

pytestmark = pytest.mark.usefixtures("qt_widgets")


def fill_operation(window, values):
    panel = window.modeling.panel
    for name, value in values.items():
        spec = panel.editor.specs[name]
        editor = panel.editor.editors[name]
        if spec.kind in ("reference", "choice"):
            index = editor.findData(value)
            assert index >= 0
            editor.setCurrentIndex(index)
        elif spec.kind == "references":
            for index in range(editor.list.count()):
                item = editor.list.item(index)
                item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in value
                                   else Qt.CheckState.Unchecked)
        elif spec.kind == "bool_vector":
            for checkbox, checked in zip(editor.editors, value):
                checkbox.setChecked(checked)
        elif spec.kind == "vector":
            for component, number in zip(editor.editors, value):
                component.setFocus(); component.selectAll()
                QTest.keyClicks(component, str(number))
        elif spec.kind == "table":
            QApplication.clipboard().setText("\n".join(",".join(map(str, row)) for row in value))
            editor.table.setFocus()
            QTest.keyClick(editor.table, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        elif spec.kind == "integer_list":
            enter(panel, name, ", ".join(map(str, value)))
        else:
            enter(panel, name, value)


def apply_operation(window, key, values):
    before = window.session.describe()["revision"]
    assert window.modeling.actions[key].isEnabled(), key
    window.modeling.actions[key].trigger(); pump()
    assert window.modeling.active, key
    fill_operation(window, values)
    assert window.session.describe()["revision"] == before
    click_apply(window)
    assert not window.modeling.active, window.modeling.panel.error.text()
    assert window.session.describe()["revision"] == before + 1


@pytest.mark.parametrize("profile", PROFILES)
def test_all_approaches_create_edit_reference_and_export_conditions(model, tmp_path, profile):
    session, source = model
    geometry = (source.parent / "mesh.inc").read_bytes()
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    ref = lambda keyword: window.provider.ref_for_card(_card(session, keyword))

    apply_operation(window, "group.create", dict(name="UI fixed nodes", native_id=47,
                                                  node_ids=(101, 205, 309, 411)))
    apply_operation(window, "group.create", dict(name="UI moving nodes", native_id=59,
                                                  node_ids=(501, 605, 709, 811)))
    apply_operation(window, "curve.create", dict(name="UI load curve", native_id=63,
                                                  points=((0, 0), (.002, 1))))
    apply_operation(window, "surface.create", dict(name="UI lower surface", native_id=71,
                                                    part_ids=(ref("/PART/902"),)))
    apply_operation(window, "constraint.create", dict(name="UI boundary", native_id=83,
                      group_id=ref("/GRNOD/NODE/47"), translations=(True, True, True), rotations=(True, True, True)))
    apply_operation(window, "load.create", dict(name="UI load", native_id=81,
                      group_id=ref("/GRNOD/NODE/59"), curve_id=ref("/FUNCT/63"), direction="Z", scale=-.01))
    apply_operation(window, "velocity.create", dict(name="UI velocity", native_id=89,
                      group_id=ref("/GRNOD/NODE/59"), velocity=(0, 0, -1000)))
    apply_operation(window, "contact.create", dict(name="UI contact", native_id=97,
                      secondary_group_id=ref("/GRNOD/NODE/59"), main_surface_id=ref("/SURF/PART/71"), friction=.17))

    curve = ref("/FUNCT/63")
    assert window.select_card(curve.object_id)
    apply_operation(window, "object.edit", dict(points=((0, 0), (.0005, .75), (.002, 1))))
    assert window.select_card(curve.object_id)
    apply_operation(window, "object.copy", dict(name="Alternate load curve"))
    copied = next(card for card in session.list_cards() if card["title"] == "Alternate load curve")
    copied_ref = window.provider.ref_for_card(copied)
    load = ref("/CLOAD/81")
    assert window.select_card(load.object_id)
    apply_operation(window, "object.edit", dict(curve_id=copied_ref))
    assert session.condition_values(load.object_id)["curve_id"] == copied_ref.object_id
    assert window.select_card(copied_ref.object_id)
    revision = session.describe()["revision"]
    window.modeling.actions["object.delete"].trigger(); click_apply(window)
    assert window.modeling.active and session.describe()["revision"] == revision
    window.modeling.panel.cancel_button.click(); pump()
    assert window.select_card(load.object_id)
    apply_operation(window, "object.edit", dict(curve_id=curve))
    assert window.select_card(copied_ref.object_id)
    apply_operation(window, "object.delete", {})

    velocity = ref("/INIVEL/TRA/89")
    assert window.select_card(velocity.object_id)
    apply_operation(window, "object.edit", dict(velocity=(0, 0, -1200)))
    window.undo_action.trigger(); pump()
    assert tuple(session.condition_values(velocity.object_id)["velocity"]) == (0, 0, -1000)
    window.redo_action.trigger(); pump()
    assert tuple(session.condition_values(velocity.object_id)["velocity"]) == (0, 0, -1200)
    project = tmp_path / (profile + ".caeprep")
    assert window.save_project_file(project); wait_file(window)
    reopened = PrepSession(); reopened.open_project(project)
    assert tuple(reopened.condition_values(velocity.object_id)["velocity"]) == (0, 0, -1200)
    target = tmp_path / profile / "conditions_0000.rad"
    window.export_rad_file(target); wait_file(window)
    raw = target.read_bytes()
    assert (target.parent / "mesh.inc").read_bytes() == geometry
    points = _block(raw, "/FUNCT/63")[1:]
    assert [(float(row[:20]), float(row[20:40])) for row in points] == [(0, 0), (.0005, .75), (.002, 1)]
    row = _block(raw, "/CLOAD/81")[1]
    assert int(row[:10]) == 63 and row[10:20].strip() == "Z" and int(row[40:50]) == 59
    assert float(row[80:100]) == -.01
    row = _block(raw, "/BCS/83")[1]
    assert row[:10] == "   111 111" and int(row[20:30]) == 47
    row = _block(raw, "/INIVEL/TRA/89")[1]
    assert [float(row[i:i+20]) for i in (0, 20, 40)] == [0, 0, -1200]
    assert int(row[60:70]) == 59
    contact = _block(raw, "/INTER/TYPE7/97")
    assert (int(contact[1][:10]), int(contact[1][10:20])) == (59, 71)
    assert float(contact[4][20:40]) == .17


def test_invalid_existing_scalar_blocks_save_without_discard_or_widget_error(model, tmp_path):
    session = model[0]
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    assert window.select_card(_card(session, "/MAT/ELAST/17")["id"])
    editor = window.field_editors["young_modulus"]
    editor.setFocus(); editor.selectAll(); QTest.keyClicks(editor, "1e")
    assert not window.save_project_file(tmp_path / "invalid.caeprep")
    assert session.describe()["revision"] == 0 and editor.text() == "1e"
    assert not (tmp_path / "invalid.caeprep").exists()


def test_condition_draft_preserves_typed_values_across_external_change_and_invalid_save(model, tmp_path):
    session = model[0]
    created = _create_conditions(session)
    window = MainWindow(session, presentation="hypermesh", enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    assert window.select_card(created["bcs"])
    before = session.describe()["revision"]
    window.field_editors["translations"].editors[0].setChecked(False)
    window.field_editors["group_id"].setCurrentIndex(0)  # incomplete typed reference
    assert session.describe()["revision"] == before and window._text_drafts()
    session.set_field(_card(session, "/MAT/ELAST/17")["id"], "young_modulus", 205000)
    pump()
    assert not window.field_editors["translations"].editors[0].isChecked()
    assert window.field_editors["group_id"].currentData() is None
    assert not window.save_project_file(tmp_path / "invalid-condition.caeprep")
    assert session.describe()["revision"] == before + 1
    assert not window.field_editors["translations"].editors[0].isChecked()
    assert window.field_editors["group_id"].currentData() is None
    window._discard_pending_edits(); pump()
    assert all(editor.isChecked() for editor in window.field_editors["translations"].editors)
    assert window.field_editors["group_id"].currentData().object_id == created["fixed"]
    assert session.describe()["revision"] == before + 1


def test_condition_targets_drive_real_node_and_element_highlights_and_keep_contact_role(model, monkeypatch):
    from test_viewport_visibility import viewport as dataset_viewport
    from caelab_prep.ui import viewport as module
    production_viewport = module.MeshViewport

    class DataViewport(QWidget):
        entityPicked = Signal(dict)
        diagnostic = Signal(str)
        _selection_cell_indices = production_viewport._selection_cell_indices
        _selection_node_indices = production_viewport._selection_node_indices

        def __init__(self, parent=None):
            super().__init__(parent)
            self.pipeline = dataset_viewport()
            self.pipeline.isometric_view = MethodType(production_viewport.isometric_view, self.pipeline)

        def set_mesh(self, data, *, reset_camera=True):
            self.pipeline.set_mesh(data, reset_camera=reset_camera)

        def set_selection(self, selection):
            self.pipeline.set_selection(selection)

        def show_all_parts(self):
            self.pipeline.show_all_parts()

        def hide_parts(self, parts):
            self.pipeline.hide_parts(parts)

        def fit_selection(self, selection):
            return self.pipeline.fit_selection(selection)

        def shutdown(self):
            pass

    monkeypatch.setattr(module, "MeshViewport", DataViewport)
    session = model[0]
    created = _create_conditions(session)
    alternate = session.create_surface("Upper surface", [_card(session, "/PART/903")["id"]], native_id=72)["card_id"]
    window = MainWindow(session, presentation="hypermesh", enable_viewport=True)
    window._allow_close = True
    window.show(); pump()
    assert window.select_card(created["bcs"])
    pump()
    assert session.selection()["kind"] == "node" and set(session.selection()["ids"]) == {101, 205, 309, 411}
    mapper = window.viewport.pipeline._highlight.GetMapper(); mapper.Update()
    assert mapper.GetInput().GetNumberOfPoints() == 4
    assert window.select_card(created["contact"])
    pump()
    assert set(session.selection()["ids"]) == {501, 605, 709, 811}
    selector = window.target_role_selector
    assert selector.isVisible() and selector.isEnabled()
    selector.setCurrentIndex(selector.findData("main_elements")); pump()
    assert session.selection()["kind"] == "element" and session.selection()["ids"] == [7001]
    assert session.active_object().object_id == created["contact"]
    mapper = window.viewport.pipeline._highlight.GetMapper(); mapper.Update()
    assert mapper.GetInput().GetNumberOfCells() == 1
    window.fit_selected_action.trigger(); pump()
    assert window.viewport.pipeline._renderer.GetActiveCamera().GetFocalPoint() == (5, 5, 0)
    alternate_ref = window.provider.ref_for_card(next(c for c in session.list_cards() if c["id"] == alternate))
    apply_operation(window, "object.edit", dict(main_surface_id=alternate_ref))
    assert session.selection()["active_target_role"] == "main_elements"
    assert session.selection()["ids"] == [9007]
    window.undo_action.trigger(); pump()
    assert session.selection()["active_target_role"] == "main_elements" and session.selection()["ids"] == [7001]


@pytest.mark.parametrize("target_kind,field", (("load", "curve_id"), ("part", "material")))
def test_invalid_inline_reference_is_a_guarded_draft(model, tmp_path, target_kind, field):
    session = model[0]
    created = _create_conditions(session)
    target = created["load"] if target_kind == "load" else _card(session, "/PART/902")["id"]
    window = MainWindow(session, presentation="hypermesh", enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    assert window.select_card(target)
    before = session.describe()["revision"]
    combo = window.field_editors[field]
    combo.setCurrentIndex(0)
    combo.activated.emit(0); pump()
    assert session.describe()["revision"] == before
    assert window._text_drafts()
    assert not window.save_project_file(tmp_path / "invalid-reference.caeprep")
    assert session.describe()["revision"] == before
    assert window.field_editors[field].currentData() is None
