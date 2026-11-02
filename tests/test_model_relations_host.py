"""Native host routes to canonical source, mesh and local-coordinate commands."""
import importlib.util
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_conditions_ui import apply_operation
from test_modeling_ui import pump
from test_source_models_ui import model, prepare, state
from test_prepared_replacement_ui import prepared_file, preview, choose_group, link

pytestmark = pytest.mark.usefixtures("qt_widgets")
MIXED = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies/beam_shell_tet/model_0000.rad"


def native_rendering():
    return QApplication.platformName() == "xcb" and importlib.util.find_spec("vtk") is not None


def window_for(session, profile=None, *, render=False):
    window = MainWindow(session, presentation=profile, enable_viewport=render)
    window._allow_close = True
    window.resize(1440, 900)
    window.show()
    pump()
    return window


def menu(window, title):
    return next(action.menu() for action in window.menuBar().actions()
                if action.text().replace("&", "") == title)


def capture(window, name):
    folder = os.environ.get("CAELAB_RELATIONS_HOST_CAPTURE_DIR")
    if folder:
        assert QApplication.platformName() == "xcb"
        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        pump()
        assert window.screen().grabWindow(int(window.winId())).save(str(path / (name + ".png")))
        (path / (name + ".json")).write_text(json.dumps({
            "platform": QApplication.platformName(), "profile": window.presentation,
            "state": window.session.describe(),
            "renderer": window.viewport._widget.GetRenderWindow().GetClassName() if window.viewport else None,
            "scope": "Linux Qt widget events; not Windows or original-product comparison"}, indent=2))


@pytest.mark.parametrize("profile", PROFILES)
def test_all_profiles_expose_same_relationship_commands_and_local_coordinate_reference(profile, tmp_path):
    session = PrepSession()
    session.open_rad(MIXED)
    group = session.create_node_group("Beam nodes", [2, 5])["card_id"]
    curve = session.create_curve("Force history", [(0, 0), (1, 1)])["card_id"]
    window = window_for(session, profile, render=native_rendering())
    assert window.source_models_action in menu(window, "File").actions()
    assert window.prepared_mesh_action in menu(window, "Mesh").actions()
    assert window.modeling.actions["coordinate_system.create"] in menu(window, "Selection").actions()
    window.source_models_action.trigger()
    assert window.source_models_dialog.isVisible() and not window.source_models_dialog.isModal()
    previous = window.source_models_dialog
    assert window.open_source_models() is previous
    previous.reject()
    assert window.source_models_dialog is None
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(previous)
    window.prepared_mesh_action.trigger()
    assert window.prepared_mesh_dialog.isVisible() and window.prepared_mesh_dialog.resource.count() == 1
    window.prepared_mesh_dialog.reject()
    assert window.prepared_mesh_dialog is None

    apply_operation(window, "coordinate_system.create", dict(
        name="Local X follows global Y", native_id=43, origin=(1, 2, 3),
        y_axis=(-1, 0, 0), z_axis=(0, 0, 1)))
    card = lambda keyword: next(card for card in session.list_cards() if card["keyword"] == keyword)
    ref = lambda identifier: window.provider.ref_for_card(next(card for card in session.list_cards() if card["id"] == identifier))
    coordinate = window.provider.ref_for_card(card("/SKEW/FIX/43"))
    assert session.coordinate_systems()[1]["axes"][0] == [0, 1, 0]
    apply_operation(window, "load.create", dict(name="Local force", native_id=81,
        group_id=ref(group), curve_id=ref(curve), direction="X", scale=2, coordinate_system_id=coordinate))
    load = card("/CLOAD/81")
    assert session.condition_values(load["id"])["coordinate_system_id"] == coordinate.object_id
    row = session.card_text(load["id"]).splitlines()[2]
    assert int(row[20:30]) == 43 and row[10:20].strip() == "X" and float(row[80:100]) == 2
    assert window.select_card(load["id"])
    assert window.property_editor.editors["coordinate_system_id"].currentData() == coordinate
    window.undo_action.trigger()
    pump()
    assert not any(card["keyword"] == "/CLOAD/81" for card in session.list_cards())
    window.redo_action.trigger()
    pump()
    assert session.condition_values(load["id"])["coordinate_system_id"] == coordinate.object_id
    path = tmp_path / (profile + ".caeprep")
    session.save_project(path)
    restored = PrepSession()
    restored.open_project(path)
    assert restored.condition_values(load["id"])["coordinate_system_id"] == coordinate.object_id
    assert window.select_card(load["id"])
    window.edit_properties_action.trigger()
    if window.viewport:
        assert not window.viewport._render_failed
    capture(window, profile + "-local-coordinate")
    window.close()


def test_source_import_menu_refreshes_real_document_tree_renderer_and_undo(tmp_path):
    first, second = model(tmp_path / "base"), model(tmp_path / "source", offset=20)
    session = PrepSession()
    session.open_rad(first)
    window = window_for(session, "hypermesh", render=native_rendering())
    original = session.document.tokens()
    window.source_models_action.trigger()
    dialog = window.source_models_dialog
    prepare(dialog, second)
    dialog.reviewed.setChecked(True)
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
    pump()
    assert dialog.result and session.describe()["element_count"] == 2
    assert window._last_presented_revision == session.document.revision
    assert len([card for card in window._card_refs.values() if card.native_scope.startswith("/PART/")]) == 2
    if window.viewport:
        assert window.viewport._grid.GetNumberOfCells() == 2
        assert not window.viewport._render_failed
    capture(window, "source-imported-host")
    dialog.reject()
    window.fit_action.trigger()
    capture(window, "source-imported-model")
    window.source_models_action.trigger()
    dialog = window.source_models_dialog
    window.undo_action.trigger()
    pump()
    assert session.document.tokens() == original and dialog.sources_model.rowCount() == 0
    if window.viewport:
        assert window.viewport._grid.GetNumberOfCells() == 1
    window.redo_action.trigger()
    pump()
    assert dialog.sources_model.rowCount() == 1 and session.describe()["element_count"] == 2
    window.close()
    assert window.source_models_dialog is None


def test_source_host_refuses_draft_busy_conflict_and_invalidates_stale_preview(tmp_path):
    first, second = model(tmp_path / "base"), model(tmp_path / "source")
    session = PrepSession()
    session.open_rad(first)
    window = window_for(session, "hypermesh")
    baseline = state(session)
    window.modeling.actions["coordinate_system.create"].trigger()
    window.source_models_action.trigger()
    window.prepared_mesh_action.trigger()
    assert window.source_models_dialog is None and window.prepared_mesh_dialog is None
    assert state(session) == baseline and window.modeling.active
    window.modeling.cancel()
    window._busy = True
    window._refresh_actions()
    assert not window.source_models_action.isEnabled() and not window.prepared_mesh_action.isEnabled()
    assert window.open_source_models() is None and state(session) == baseline
    window._busy = False
    window._refresh_actions()

    window.source_models_action.trigger()
    dialog = window.source_models_dialog
    prepare(dialog, second)
    dialog.reviewed.setChecked(True)
    window.modeling.actions["coordinate_system.create"].trigger()
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
    assert state(session) == baseline and "draft_pending" in dialog.status.text()
    window.modeling.cancel()
    session.create_node_group("Intervening edit", [1])
    pump()
    current = state(session)
    assert dialog._plan is None and not dialog.apply_import()
    assert state(session) == current

    material = next(card for card in session.list_cards() if card["keyword"] == "/MAT/LAW1/41")
    assert window.select_card(material["id"])
    editor = window.field_editors["young_modulus"]
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "1e")
    session.new_document("Replacement", {"mass": "Mg", "length": "mm", "time": "s"})
    pump()
    assert window._replacement_conflict and window.file_edits.has_draft()
    assert window.open_prepared_mesh() is None and not dialog.apply_import()
    assert session.describe()["element_count"] == 0 and editor.text() == "1e"
    window._discard_pending_edits()
    window.close()


def test_prepared_mesh_menu_updates_geometry_staleness_reconnection_and_history(tmp_path):
    session = PrepSession()
    session.open_rad(MIXED)
    group = session.create_node_group("Affected nodes", [1, 2])["card_id"]
    window = window_for(session, "beidprep", render=native_rendering())
    original = session.mesh_view()["points"][0]
    window.prepared_mesh_action.trigger()
    dialog = window.prepared_mesh_dialog
    preview(dialog, prepared_file(tmp_path))
    dialog.replacement_reviewed.setChecked(True)
    QTest.mouseClick(dialog.replace_button, Qt.MouseButton.LeftButton)
    pump()
    moved = session.mesh_view()["points"][0]
    assert tuple(moved) == tuple(value + 2 for value in original)
    assert group in session.mesh_relationships()["stale_targets"]
    if window.viewport:
        assert tuple(window.viewport._grid.GetPoint(0)) == tuple(moved)
        assert not window.viewport._render_failed
    choose_group(dialog, group)
    for identifier in (1, 2):
        reference = link(dialog, identifier, identifier)
        assert reference["entity_kind"] == "node" and reference["local_id"] == identifier
    dialog.reconnect_reviewed.setChecked(True)
    QTest.mouseClick(dialog.reconnect_button, Qt.MouseButton.LeftButton)
    pump()
    assert not session.mesh_relationships()["stale_targets"]
    window.undo_action.trigger()
    pump()
    assert group in session.mesh_relationships()["stale_targets"]
    window.undo_action.trigger()
    pump()
    assert session.mesh_view()["points"][0] == original
    assert not session.mesh_relationships()["stale_targets"]
    if window.viewport:
        assert tuple(window.viewport._grid.GetPoint(0)) == tuple(original)
    window.close()
    assert window.prepared_mesh_dialog is None


def test_instance_metadata_refreshes_host_history_via_canonical_session_event():
    session = PrepSession(); session.open_rad(MIXED)
    window = window_for(session, "hypermesh", render=native_rendering())
    view = session.mesh_view(); grid = window.viewport._grid if window.viewport else None
    window.source_models_action.trigger()
    dialog = window.source_models_dialog
    dialog.tabs.setCurrentIndex(2)
    revision = session.document.revision
    dialog.instance_name.setText("Reference without placement")
    dialog.instance_acknowledged.setChecked(True)
    QTest.mouseClick(dialog.create_instance_button, Qt.MouseButton.LeftButton)
    pump()
    assert session.document.revision == revision + 1
    assert window._last_presented_revision == session.document.revision
    assert window.undo_action.isEnabled() and dialog.instances_model.rowCount() == 1
    assert session.mesh_view()["cells"] is view["cells"]
    if window.viewport: assert window.viewport._grid is grid
    window.undo_action.trigger(); pump()
    assert session.instance_references() == [] and dialog.instances_model.rowCount() == 0
    assert window._last_presented_revision == session.document.revision
    window.redo_action.trigger(); pump()
    assert len(session.instance_references()) == 1 and dialog.instances_model.rowCount() == 1
    dialog.instances_table.selectRow(0)
    QTest.mouseClick(dialog.delete_instance_button, Qt.MouseButton.LeftButton)
    pump()
    assert session.instance_references() == [] and window._last_presented_revision == session.document.revision
    window.close()
