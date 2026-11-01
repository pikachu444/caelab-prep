"""Compare actual documents, drafts and file results across UI approaches."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import time

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from caelab_prep.application.contracts import SetProperties
from caelab_prep.application.neutral import CurveSession
from caelab_prep.application.session import PrepSession
from caelab_prep.ui.comparison import ComparisonWindow
from caelab_prep.ui.reference_profiles import PROFILES

pytestmark = pytest.mark.usefixtures("qt_widgets")


def pump():
    for _ in range(3):
        QApplication.processEvents()


def wait_file(view):
    end = time.monotonic() + 8
    while view._busy and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(.005)
    assert not view._busy
    pump()


def value(session, ref, name):
    return next(p.value for p in session.properties(ref) if p.name == name)


@pytest.mark.parametrize("key", PROFILES)
def test_program_switch_keeps_same_material_values_reference_and_single_history(qt_widgets, key, tmp_path):
    session = CurveSession()
    material = session.tree_nodes()[0].ref
    curve = next(node.ref for node in session.tree_nodes() if node.ref.kind == "curve")
    window = ComparisonWindow(session)
    window._allow_close = True
    first = window.active_view
    assert first.select_ref(material)
    session.submit(SetProperties(material, {"reference_curve": curve}, session.describe()["revision"]))
    pump()
    assert window.select_profile(key)
    pump()
    view = window.active_view
    assert view.session is session and session.active_object() == material
    assert view._target == material
    assert view.field_editors["young_modulus"].text() == "210000.0"
    assert view.field_editors["reference_curve"].currentData() == curve
    view.field_editors["young_modulus"].setText("205000")
    assert view.apply_properties()
    assert value(session, material, "young_modulus") == 205000
    assert window.select_profile("comsol" if key != "comsol" else "hypermesh")
    pump()
    other = window.active_view
    assert other._target == material
    assert float(other.field_editors["young_modulus"].text()) == 205000
    other.undo_action.trigger();pump()
    assert value(session, material, "young_modulus") == 210000
    assert value(session, material, "reference_curve") == curve
    other.redo_action.trigger();pump()
    path = tmp_path / (key + ".caeprep")
    assert other.save_project_file(path)
    wait_file(other)
    reopened = CurveSession();reopened.open_project(path)
    ref = reopened.tree_nodes()[0].ref
    assert value(reopened, ref, "young_modulus") == 205000
    assert value(reopened, ref, "reference_curve").object_id == curve.object_id
    window.close()


def test_invalid_draft_blocks_variant_switch_without_losing_input_or_history(qt_widgets):
    window = ComparisonWindow()
    window._allow_close = True
    view = window.active_view
    material = view.session.tree_nodes()[0].ref
    view.select_ref(material)
    before = view.session.describe()["revision"]
    editor = view.field_editors["young_modulus"]
    editor.setText("1e")
    assert not window.select_profile("abaqus")
    assert window.active_view is view
    assert editor.text() == "1e"
    assert view.session.describe()["revision"] == before
    assert value(view.session, material, "young_modulus") == 210000
    view.reload_values()
    assert window.select_profile("abaqus")
    window.close()


def test_external_revision_keeps_draft_and_comparison_close_cancel(qt_widgets, monkeypatch):
    window = ComparisonWindow()
    view = window.active_view
    material = view.session.tree_nodes()[0].ref
    view.select_ref(material)
    view.field_editors["young_modulus"].setText("199000")
    view.session.submit(SetProperties(material, {"density": 7900}, view.session.describe()["revision"]))
    pump()
    assert not window.select_profile("prepomax")
    assert view.field_editors["young_modulus"].text() == "199000"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    window.show();window.close()
    assert window.isVisible()
    assert view.field_editors["young_modulus"].text() == "199000"
    window._allow_close = True
    window.close()


@pytest.mark.parametrize("key", PROFILES)
def test_native_views_keep_card_undo_and_real_export(qt_widgets, key, tmp_path):
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
    material = next(c for c in session.list_cards() if c["keyword"].startswith("/MAT/"))
    window = ComparisonWindow(session, native=True, enable_viewport=False)
    window._allow_close = True
    window.active_view.select_card(material["id"])
    assert window.select_profile(key)
    pump()
    view = window.active_view
    assert view.session is session and view._selected_card_id == material["id"]
    original = next(f["value"] for f in session.card_fields(material["id"]) if f["name"] == "young_modulus")
    editor = view.field_editors["young_modulus"]
    editor.setText("205000");editor.setModified(True)
    assert view._finish_pending_edits()
    view.undo_action.trigger();pump()
    assert next(f["value"] for f in session.card_fields(material["id"]) if f["name"] == "young_modulus") == original
    view.redo_action.trigger();pump()
    project = tmp_path / (key + ".caeprep")
    assert view.save_project_file(project)
    wait_file(view)
    reopened = PrepSession();reopened.open_project(project)
    output = tmp_path / "export" / "model_0000.rad"
    reopened.export_rad(output)
    actual = PrepSession();actual.open_rad(output)
    actual_card = next(c for c in actual.list_cards() if c["keyword"].startswith("/MAT/"))
    assert next(f["value"] for f in actual.card_fields(actual_card["id"]) if f["name"] == "young_modulus") == 205000
    assert actual.describe()["node_count"] == session.describe()["node_count"]
    window.close()


def test_native_dialog_defers_boolean_draft_and_cancel_restores_without_command(qt_widgets):
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad")
    window = ComparisonWindow(session, native=True, enable_viewport=False)
    window._allow_close = True
    window.select_profile("prepomax")
    view = window.active_view
    card = next(c for c in session.list_cards() if c["keyword"].startswith("/BCS/"))
    view.select_card(card["id"])
    before = session.describe()["revision"]
    view.property_dialog.open();pump()
    view.field_editors["tx"].setChecked(False)
    assert session.describe()["revision"] == before
    assert view._text_drafts()
    view.property_dialog.reject();pump()
    assert view.field_editors["tx"].isChecked()
    assert session.describe()["revision"] == before
    view.property_dialog.open();pump()
    view.field_editors["tx"].setChecked(False)
    view.field_editors["ty"].setChecked(False)
    assert view._finish_pending_edits()
    assert session.describe()["revision"] == before + 1
    session.undo();pump()
    assert view.field_editors["tx"].isChecked() and view.field_editors["ty"].isChecked()
    window.close()


@pytest.mark.parametrize("key", ("abaqus", "meshfree"))
def test_plot_page_preserves_and_validates_hidden_curve_draft_before_switch(qt_widgets, key):
    session = PrepSession()
    session.open_rad(Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad")
    window = ComparisonWindow(session, native=True, enable_viewport=False)
    window._allow_close = True
    window.select_profile(key)
    view = window.active_view
    curve = next(c for c in session.list_cards() if c["keyword"].startswith("/FUNCT/"))
    view.select_card(curve["id"])
    before = session.describe()["revision"]
    view.curve_table.table.item(1, 1).setText("333")
    view.reference_bindings.curve_pages.setCurrentIndex(1)
    assert view.curve_table.isHidden() and view._text_drafts()
    assert window.select_profile("comsol")
    assert session.describe()["revision"] == before + 1
    assert next(f["value"] for f in session.card_fields(curve["id"]) if f["name"] == "point_1_y") == 333
    assert window.select_profile(key)
    view.curve_table.table.item(1, 1).setText("1e")
    view.reference_bindings.curve_pages.setCurrentIndex(1)
    assert not window.select_profile("comsol")
    assert view.curve_table.table.item(1, 1).text() == "1e"
    assert next(f["value"] for f in session.card_fields(curve["id"]) if f["name"] == "point_1_y") == 333
    window.close()


def test_switch_to_new_and_existing_views_preserves_explicit_no_selection(qt_widgets):
    window = ComparisonWindow()
    window._allow_close = True
    session = window.session
    assert session.active_object() is None
    for key in ("abaqus", "hypermesh", "comsol"):
        session.select(None)
        assert window.select_profile(key)
        pump()
        assert session.active_object() is None
        assert window.active_view._target is None
        assert not window.active_view.field_editors
    window.close()


@pytest.mark.parametrize("native", (False, True))
def test_embedded_file_exit_closes_outer_window_and_cancel_keeps_editor(qt_widgets, monkeypatch, native):
    if native:
        session = PrepSession()
        session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
    else:
        session = CurveSession()
    window = ComparisonWindow(session, native=native, enable_viewport=False)
    window.show()
    view = window.active_view
    if native:
        view.select_card(next(c['id'] for c in session.list_cards() if c['keyword'].startswith('/MAT/')))
    else:
        view.select_ref(session.tree_nodes()[0].ref)
    editor = view.field_editors["young_modulus"]
    editor.setText("1e");editor.setModified(True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    view.close_action.trigger();pump()
    assert window.isVisible() and window.active_view.isVisible()
    assert editor.text() == "1e"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
    view.close_action.trigger();pump()
    assert not window.isVisible()
