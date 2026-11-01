"""Display-unit choices must reach the native provider without changing the deck basis."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_condition_workflow import model, _create_conditions, _card
from test_modeling_ui import enter, click_apply, pump
from test_conditions_ui import fill_operation

pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.mark.parametrize("profile", PROFILES)
def test_native_create_and_vector_edit_convert_selected_units_in_every_approach(model, profile):
    session = model[0]
    created = _create_conditions(session)
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    before = session.describe()["revision"]
    window.modeling.actions["material.create"].trigger(); pump()
    panel = window.modeling.panel
    panel.editor.unit_selectors["density"].setCurrentText("kg/m³")
    panel.editor.unit_selectors["young_modulus"].setCurrentText("GPa")
    for name, value in {"name": "Converted material", "native_id": 41, "density": 7800,
                        "young_modulus": 203.5, "poisson_ratio": .29}.items():
        enter(panel, name, value)
    assert session.describe()["revision"] == before
    click_apply(window)
    assert not window.modeling.active, panel.error.text()
    fields = {field["name"]: field["value"] for field in session.card_fields(_card(session, "/MAT/LAW1/41")["id"])}
    assert fields["density"] == pytest.approx(7.8e-9) and fields["young_modulus"] == 203500
    assert session.describe()["revision"] == before + 1

    assert window.select_card(created["velocity"])
    window.modeling.actions["object.edit"].trigger(); pump()
    vector = panel.editor.editors["velocity"]
    vector.editors[2].setText("1e")
    raw = tuple(editor.text() for editor in vector.editors)
    selector = panel.editor.unit_selectors["velocity"]
    selector.setCurrentText("m/s")
    assert selector.currentText() == "mm/s"
    assert tuple(editor.text() for editor in vector.editors) == raw
    assert session.describe()["revision"] == before + 1
    panel.cancel_button.click(); pump()

    window.modeling.actions["object.edit"].trigger(); pump()
    selector = panel.editor.unit_selectors["velocity"]
    selector.setCurrentText("m/s")
    vector = panel.editor.editors["velocity"]
    assert vector.numeric_value() == (0, 0, -1)
    vector.editors[2].setText("-1.25")
    click_apply(window)
    assert not window.modeling.active, panel.error.text()
    assert tuple(session.condition_values(created["velocity"])["velocity"]) == (0, 0, -1250)
    window.undo_action.trigger(); pump()
    assert tuple(session.condition_values(created["velocity"])["velocity"]) == (0, 0, -1000)
    window.redo_action.trigger(); pump()
    assert tuple(session.condition_values(created["velocity"])["velocity"]) == (0, 0, -1250)


def test_scalar_equal_numeric_value_in_different_unit_is_not_treated_as_no_change(model):
    session = model[0]
    window = MainWindow(session, presentation="hypermesh", enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    material = _card(session, "/MAT/ELAST/17")["id"]
    assert window.select_card(material)
    selector = window.property_editor.unit_selectors["young_modulus"]
    selector.setCurrentText("GPa")
    editor = window.field_editors["young_modulus"]
    assert float(editor.text()) == 210
    assert session.describe()["revision"] == 0
    editor.setFocus(); editor.selectAll(); QTest.keyClicks(editor, "210000")
    assert window._finish_pending_edits()
    fields = {field["name"]: field["value"] for field in session.card_fields(material)}
    assert fields["young_modulus"] == 210000000
    assert window.property_editor.unit_selectors["young_modulus"].currentText() == "GPa"


def test_native_vector_unit_and_raw_draft_survive_external_revision(model, tmp_path):
    session = model[0]
    created = _create_conditions(session)
    window = MainWindow(session, presentation="prepomax", enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    assert window.select_card(created["velocity"])
    window.property_editor.unit_selectors["velocity"].setCurrentText("m/s")
    vector = window.field_editors["velocity"]
    vector.editors[2].setFocus(); vector.editors[2].selectAll(); QTest.keyClicks(vector.editors[2], "-1.3")
    revision = session.describe()["revision"]
    session.set_field(_card(session, "/MAT/ELAST/17")["id"], "young_modulus", 205000)
    pump()
    assert window.property_editor.unit_selectors["velocity"].currentText() == "m/s"
    assert window.field_editors["velocity"].editors[2].text() == "-1.3"
    assert not window.save_project_file(tmp_path / "stale.caeprep")
    assert session.describe()["revision"] == revision + 1
    assert tuple(session.condition_values(created["velocity"])["velocity"]) == (0, 0, -1000)
    assert window.field_editors["velocity"].editors[2].text() == "-1.3"


@pytest.mark.parametrize("profile", PROFILES)
def test_new_document_menu_wires_real_workflow_in_every_approach(profile):
    session = PrepSession()
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    workflow = window.mesh_workflow
    assert workflow.new_action.isEnabled()
    assert not workflow.mesh_action.isEnabled() and not workflow.export_action.isEnabled()
    def complete_dialog():
        dialog = workflow.dialog
        dialog.name.setText("New engineering model")
        for key, value in {"mass": "Mg", "length": "mm", "time": "s"}.items():
            dialog.units[key].setCurrentIndex(dialog.units[key].findData(value))
        dialog.buttons.button(dialog.buttons.StandardButton.Ok).click()
    QTimer.singleShot(0, complete_dialog)
    workflow.new_action.trigger(); pump()
    assert session.describe()["document_id"] and session.describe()["name"] == "New engineering model"
    assert workflow.mesh_action.isEnabled() and workflow.export_action.isEnabled()


@pytest.mark.parametrize("profile", PROFILES)
def test_force_moment_context_requires_fresh_scale_and_keeps_each_quantity_draft(model, profile):
    session = model[0]
    created = _create_conditions(session)
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    window.modeling.actions["load.create"].trigger(); pump()
    panel = window.modeling.panel
    card_ref = lambda identifier: window.provider.ref_for_card(next(c for c in session.list_cards() if c["id"] == identifier))
    fill_operation(window, dict(name="Rotational load", native_id=151,
                                group_id=card_ref(created["moving"]), curve_id=card_ref(created["curve"]), scale=-.02))
    revision = session.describe()["revision"]
    panel.editor.editors["direction"].setCurrentText("XX"); pump()
    assert panel.editor.editors["scale"].text() == ""
    assert panel.editor.unit_selectors["scale"].property("unitChoiceRequired")
    click_apply(window)
    assert window.modeling.active and session.describe()["revision"] == revision
    panel.editor.unit_selectors["scale"].setCurrentText("N·m")
    enter(panel, "scale", "1e")
    panel.editor.editors["direction"].setCurrentText("Z"); pump()
    assert float(panel.editor.editors["scale"].text()) == -.02
    assert panel.editor.unit_selectors["scale"].currentText() == "N"
    panel.editor.editors["direction"].setCurrentText("XX"); pump()
    assert panel.editor.editors["scale"].text() == "1e"
    assert panel.editor.unit_selectors["scale"].currentText() == "N·m"
    enter(panel, "scale", .25)
    click_apply(window)
    assert not window.modeling.active, panel.error.text()
    load = _card(session, "/CLOAD/151")
    values = session.condition_values(load["id"])
    assert values["direction"] == "XX" and values["scale"] == 250
    assert session.describe()["revision"] == revision + 1

    assert window.select_card(load["id"])
    window.modeling.actions["object.edit"].trigger(); pump()
    panel.editor.editors["direction"].setCurrentText("Y"); pump()
    assert panel.editor.editors["scale"].text() == ""
    panel.editor.unit_selectors["scale"].setCurrentText("kN")
    enter(panel, "scale", .005)
    click_apply(window)
    assert not window.modeling.active, panel.error.text()
    values = session.condition_values(load["id"])
    assert values["direction"] == "Y" and values["scale"] == 5
    window.undo_action.trigger(); pump()
    values = session.condition_values(load["id"])
    assert values["direction"] == "XX" and values["scale"] == 250


@pytest.mark.parametrize("profile", ("hypermesh", "prepomax"))
def test_existing_inspector_dimension_switch_requires_explicit_value_and_unit(model, tmp_path, profile):
    session = model[0]
    created = _create_conditions(session)
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    assert window.select_card(created["load"])
    revision = session.describe()["revision"]
    window.property_editor.editors["direction"].setCurrentText("ZZ"); pump()
    assert session.describe()["revision"] == revision
    assert window.field_editors["scale"].text() == ""
    assert not window.save_project_file(tmp_path / "missing-scale.caeprep")
    assert session.describe()["revision"] == revision
    window.property_editor.unit_selectors["scale"].setCurrentText("N·m")
    window.field_editors["scale"].setText(".04")
    assert window._finish_pending_edits()
    values = session.condition_values(created["load"])
    assert values["direction"] == "ZZ" and values["scale"] == 40
    assert session.describe()["revision"] == revision + 1
    assert window.property_editor.unit_selectors["scale"].currentText() == "N·m"
