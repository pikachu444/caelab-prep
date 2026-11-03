"""Offscreen Qt consumers of prepared Tet10; no VTK renderer or solver run."""
import json
import os
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from caelab_prep.application import PrepSession
from caelab_prep.application import external_mesh
from caelab_prep.application.tet10_geometry import native_tet10_nodes
from caelab_prep.radioss.deck import DeckResource
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_import import ImportMeshDialog, import_projection
from caelab_prep.ui.reference_profiles import PROFILES
from test_external_mesh import state
from test_external_mesh_ui import pump, wait_task
from test_prepared_tet10 import fixture, model, sdk


pytestmark = pytest.mark.usefixtures("qt_widgets", "sdk")


def inspect(dialog, source, output, *, explicit=True):
    dialog.source.setText(str(source)); dialog.output.setText(str(output))
    dialog.length.setCurrentIndex(dialog.length.findData("mm"))
    if explicit:
        dialog.element_profile.setCurrentIndex(dialog.element_profile.findData("straight_tet10"))
    QTest.mouseClick(dialog.inspect_button, Qt.MouseButton.LeftButton)
    assert not dialog.element_profile.isEnabled() and dialog.cancel_button.isEnabled()
    wait_task(dialog)
    assert dialog.candidate is not None, dialog.error.text()


@pytest.mark.parametrize("presentation", PROFILES)
def test_explicit_tet10_inspect_adopt_single_undo_and_v6_reopen(tmp_path, monkeypatch, presentation):
    source = tmp_path / "prepared.msh"; ids = fixture(source); original = source.read_bytes()
    session, material, section = model()
    window = MainWindow(session, presentation=presentation, enable_viewport=False)
    window._allow_close = True; window.resize(960, 640); window.show(); pump()
    dialog = ImportMeshDialog(session, window, enable_viewport=False); dialog.show(); pump()
    assert window.mesh_import.action.isEnabled() and dialog.element_profile.currentData() == "linear"
    calls, importer = [], external_mesh.import_standalone_mesh
    def import_actual(*args, **kwargs):
        calls.append(kwargs["element_profile"])
        return importer(*args, **kwargs)
    monkeypatch.setattr(external_mesh, "import_standalone_mesh", import_actual)
    before = state(session)
    inspect(dialog, source, tmp_path / "imports")
    assert calls == ["straight_tet10"] and state(session) == before
    assert dialog.candidate.quality.passed and dialog.adopt_button.isEnabled()
    assert dialog.inventory.rowCount() == 2 and dialog.groups.rowCount() >= 2 and dialog.quality.rowCount() >= 1
    projection = import_projection(dialog.candidate)
    assert len(projection["cells"]) == 1 and projection["cells"][0]["type"] == "tetra10"
    assert tuple(projection["cells"][0]["nodes"]) == native_tet10_nodes(ids)
    assert tuple(dialog.candidate.cells[0].node_ids) == ids  # source Gmsh order is immutable
    assert projection["document_id"] != session.describe()["document_id"]
    dialog.material.setCurrentIndex(dialog.material.findData(material))
    dialog.section.setCurrentIndex(dialog.section.findData(section))
    QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton); wait_task(dialog)
    assert dialog.result is not None, dialog.error.text()
    assert not dialog.isVisible() and session.describe()["revision"] == before[0] + 1
    assert session.describe()["node_count"] == 10 and session.describe()["element_count"] == 1
    expected = tuple(dialog.result["node_id_map"][node] for node in native_tet10_nodes(ids))
    assert session.mesh_view()["cells"][0]["nodes"] == expected  # native projection is not swapped again
    session.undo(); assert state(session)[1] == before[1] and not session.mesh_view()["cells"]
    session.redo(); assert session.mesh_view()["cells"][0]["nodes"] == expected
    project = tmp_path / (presentation + ".caeprep"); session.save_project(project)
    with zipfile.ZipFile(project) as archive:
        assert json.loads(archive.read("manifest.json"))["version"] == 6
    reopened = PrepSession(); reopened.open_project(project)
    assert reopened.mesh_view()["cells"][0]["nodes"] == expected
    assert reopened.describe()["element_count"] == 1 and source.read_bytes() == original
    for group in dialog.result["group_id_map"].values():
        assert reopened.group_members(group)["member_ids"]
    window.close()


def test_default_profile_blocks_tet10_and_changing_profile_invalidates_review(tmp_path):
    source = tmp_path / "prepared.msh"; fixture(source)
    session, _, _ = model(); before = state(session)
    dialog = ImportMeshDialog(session, enable_viewport=False); dialog.show(); pump()
    inspect(dialog, source, tmp_path / "imports", explicit=False)
    assert not dialog.candidate.quality.passed and not dialog.adopt_button.isEnabled()
    assert "Blocked" in dialog.summary.text() and dialog.element_profile.currentData() == "linear"
    dialog.element_profile.setCurrentIndex(dialog.element_profile.findData("straight_tet10"))
    assert dialog.candidate is None and not dialog.adopt_button.isEnabled()
    assert all(table.rowCount() == 0 for table in (dialog.inventory, dialog.groups, dialog.quality))
    assert "Inspect again" in dialog.summary.text() and "LAW1" in dialog.profile_hint.text()
    inspect(dialog, source, tmp_path / "imports")
    assert dialog.candidate.quality.passed
    dialog.element_profile.setCurrentIndex(0)
    assert dialog.candidate is None and not dialog.adopt_button.isEnabled() and state(session) == before
    dialog.reject()


def test_wrong_tet4_section_keeps_source_project_and_document_unchanged(tmp_path):
    source = tmp_path / "prepared.msh"; fixture(source)
    session, material, _ = model(); wrong = session.create_solid_property("Existing Tet4 section")["card_id"]
    project = tmp_path / "existing.caeprep"; session.save_project(project)
    source_bytes, project_bytes, before = source.read_bytes(), project.read_bytes(), state(session)
    dialog = ImportMeshDialog(session, enable_viewport=False); dialog.show(); pump()
    inspect(dialog, source, tmp_path / "imports")
    dialog.material.setCurrentIndex(dialog.material.findData(material))
    dialog.section.setCurrentIndex(dialog.section.findData(wrong))
    QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton); wait_task(dialog)
    assert dialog.isVisible() and dialog.result is None and dialog.error.text()
    assert state(session) == before and not session.mesh_view()["cells"]
    assert source.read_bytes() == source_bytes and project.read_bytes() == project_bytes
    dialog.reject()


def test_explicit_profile_uses_existing_inspection_cancellation(tmp_path):
    source = tmp_path / "prepared.msh"; fixture(source)
    session, _, _ = model(); before = state(session)
    dialog = ImportMeshDialog(session, enable_viewport=False); dialog.show(); pump()
    dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "imports"))
    dialog.length.setCurrentIndex(dialog.length.findData("mm")); dialog.element_profile.setCurrentIndex(1)
    QTest.mouseClick(dialog.inspect_button, Qt.MouseButton.LeftButton)
    assert not dialog.element_profile.isEnabled()
    QTest.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton); wait_task(dialog)
    assert dialog._cancel.is_set() and dialog.candidate is None and not dialog.adopt_button.isEnabled()
    assert dialog.element_profile.isEnabled() and state(session) == before
    dialog.reject()


def test_reopened_same_document_epoch_rejects_previous_import_review(tmp_path, monkeypatch):
    source = tmp_path / "prepared.msh"; fixture(source)
    session, material, section = model()
    project = tmp_path / "saved-A.caeprep"; session.save_project(project)
    source_bytes, project_bytes = source.read_bytes(), project.read_bytes()
    dialog = ImportMeshDialog(session, enable_viewport=False); dialog.show(); pump()
    inspect(dialog, source, tmp_path / "imports")
    dialog.material.setCurrentIndex(dialog.material.findData(material))
    dialog.section.setCurrentIndex(dialog.section.findData(section))
    stamp, reviewed = dict(dialog._stamp), state(session)
    session.new_document("Temporary B", {"mass": "Mg", "length": "mm", "time": "s"})
    session.open_project(project)
    current = session.describe()
    assert current["document_id"] == stamp["document_id"] and current["revision"] == stamp["revision"]
    assert current["document_epoch"] != stamp["document_epoch"] and state(session) == reviewed
    assert material in {card["id"] for card in session.list_cards()}
    assert section in {card["id"] for card in session.list_cards()}
    errors, adopt = [], session.adopt_mesh_candidate
    def actual_adopt(*args, **kwargs):
        try:
            return adopt(*args, **kwargs)
        except Exception as error:
            errors.append(error.code)
            raise
    monkeypatch.setattr(session, "adopt_mesh_candidate", actual_adopt)
    before = state(session)
    QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton); wait_task(dialog)
    assert errors == ["document_epoch_conflict"]
    assert dialog.result is None and dialog.isVisible() and "reopened" in dialog.error.text()
    assert state(session) == before and not session.mesh_view()["cells"]
    assert session.describe()["document_epoch"] == current["document_epoch"]
    assert source.read_bytes() == source_bytes and project.read_bytes() == project_bytes
    dialog.reject()


@pytest.mark.parametrize("presentation", PROFILES)
def test_common_solid_section_form_creates_explicit_tet10_in_one_undo(presentation):
    session = PrepSession()
    session.new_document("UI solid section", {"mass": "Mg", "length": "mm", "time": "s"})
    window = MainWindow(session, presentation=presentation, enable_viewport=False)
    window._allow_close = True; window.resize(960, 640); window.show(); pump()
    before = state(session)
    window.modeling.actions["solid_section.create"].trigger(); pump()
    panel = window.modeling.panel
    assert window.modeling.active and panel.isVisible() and panel.apply_button.text() == "Create"
    combo = panel.editor.editors["element_family"]
    assert combo.currentData() == "tetra4"
    assert [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())] == [
        ("Linear Tet4", "tetra4"), ("Straight Tet10 (LAW1)", "tetra10")]
    name = panel.editor.editors["name"]
    name.setFocus(); name.selectAll(); QTest.keyClicks(name, "UI prepared Tet10 section")
    combo.setCurrentIndex(combo.findData("tetra10")); pump()
    assert panel.editor.editors["element_family"].currentData() == "tetra10"
    QTest.mouseClick(panel.apply_button, Qt.MouseButton.LeftButton); pump()
    assert not window.modeling.active, panel.error.text()
    assert session.describe()["revision"] == before[0] + 1
    created = next(card for card in session.list_cards() if card["keyword"].startswith("/PROP/SOLID/"))
    deck = DeckResource(session.card_text(created["id"]).encode("latin1"))
    card = next(card for card in deck.cards if card.keyword.startswith("/PROP/SOLID/"))
    native_row = deck.lines[card.data[1]]
    assert tuple(int(native_row[start:start + 10]) for start in (10, 20, 40)) == (4, 0, 1000)
    session.undo(); assert state(session)[1] == before[1]
    window.close()
