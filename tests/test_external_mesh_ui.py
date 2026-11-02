"""Shared import UI uses real worker/files and one native command in eight hosts."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_import import ImportMeshDialog, import_projection
from caelab_prep.ui.reference_profiles import PROFILES
from test_external_mesh import external_input, gmsh_sdk, session_for, state, SHELL_MSH

pytestmark = pytest.mark.usefixtures("qt_widgets", "gmsh_sdk")


def pump():
    for _ in range(3): QApplication.processEvents()


def wait_task(dialog):
    end = time.monotonic() + 10
    while dialog._task is not None and time.monotonic() < end:
        QTest.qWait(10)
    pump()
    assert dialog._task is None


def prepare(dialog, source, tmp_path):
    dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "ui-imports"))
    dialog.length.setCurrentIndex(dialog.length.findData("mm"))
    QTest.mouseClick(dialog.inspect_button, Qt.MouseButton.LeftButton)
    wait_task(dialog)
    assert dialog.candidate is not None, dialog.error.text()


@pytest.mark.parametrize("profile", PROFILES)
def test_import_review_cancel_adopt_undo_and_reopen_in_each_host(external_input, tmp_path, profile):
    from caelab_prep.application import PrepSession
    source, dimension = external_input
    session, material, section = session_for(dimension)
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True; window.resize(960, 640); window.show(); pump()
    assert window.mesh_import.action.isEnabled()
    mesh_menu = next(action.menu() for action in window.menuBar().actions() if action.text().replace("&", "") == "Mesh")
    assert window.mesh_import.action in mesh_menu.actions()
    before = state(session)
    dialog = ImportMeshDialog(session, window, enable_viewport=False); dialog.resize(900, 560); dialog.show(); pump()
    prepare(dialog, source, tmp_path)
    assert state(session) == before
    assert dialog.inventory.rowCount() >= 2 and dialog.groups.rowCount() == 4
    assert dialog.quality.rowCount() >= 2 and dialog.adopt_button.isEnabled()
    assert "boundary" in dialog.summary.text()
    projection = import_projection(dialog.candidate)
    assert projection["document_id"] != session.describe()["document_id"]
    assert None not in projection["resource_revisions"] and len(projection["cells"]) == 2
    QTest.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton); pump()
    assert not dialog.isVisible() and state(session) == before
    # Reopening the shared UI is an independent user action, with a fresh draft.
    dialog = ImportMeshDialog(session, window, enable_viewport=False); dialog.show(); pump()
    prepare(dialog, source, tmp_path)
    dialog.material.setCurrentIndex(dialog.material.findData(material))
    dialog.section.setCurrentIndex(dialog.section.findData(section))
    QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton); wait_task(dialog)
    assert dialog.result is not None, dialog.error.text()
    assert not dialog.isVisible() and session.describe()["element_count"] == 2
    assert session.describe()["revision"] == before[0] + 1
    assert len(dialog.result["group_id_map"]) == 4
    pump(); assert window.model_tree.model().rowCount() > 0
    session.undo(); assert state(session)[1] == before[1]
    session.redo(); assert session.describe()["element_count"] == 2
    saved = tmp_path / (profile + ".caeprep"); session.save_project(saved)
    reopened = PrepSession(); reopened.open_project(saved)
    assert reopened.describe()["element_count"] == 2
    for key, identifier in dialog.result["group_id_map"].items():
        assert reopened.group_members(identifier)["member_ids"]
    window.close()


def test_import_ui_requires_units_rejects_invalid_inventory_and_stale_adoption(tmp_path):
    source = tmp_path / "input.msh"; source.write_text(SHELL_MSH)
    session, material, section = session_for(2)
    dialog = ImportMeshDialog(session, enable_viewport=False); dialog.show(); pump()
    dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "imports"))
    before = state(session)
    QTest.mouseClick(dialog.inspect_button, Qt.MouseButton.LeftButton)
    assert dialog._task is None and "length unit" in dialog.error.text() and state(session) == before
    prepare(dialog, source, tmp_path)
    dialog.material.setCurrentIndex(dialog.material.findData(material)); dialog.section.setCurrentIndex(dialog.section.findData(section))
    session.create_material("Concurrent edit", 1e-9, 100000, .2)
    changed = state(session)
    QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton); wait_task(dialog)
    assert dialog.isVisible() and dialog.result is None and dialog.error.text()
    assert state(session) == changed
    source.write_text(SHELL_MSH.replace("501 2 2 11 1 11 31 51", "501 3 2 11 1 11 31 151 51"))
    prepare(dialog, source, tmp_path)
    assert not dialog.adopt_button.isEnabled() and "Blocked" in dialog.summary.text()
    assert state(session) == changed
    dialog.reject()
