"""Reviewed CAD replacement and reuse of the existing typed reconnection UI."""
import os
import threading
import time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.application import PrepSession
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog
from caelab_prep.ui.source_models import PreparedMeshDialog
from test_mesh_candidates import real_candidate
from test_cad_mesh_replacement import referenced_model, states
from test_mesh_workflow_ui import choose, pump_until
from test_prepared_replacement_ui import choose_group, link

pytestmark = pytest.mark.usefixtures("qt_widgets")


def replacement_dialog(candidate):
    session, native, material, section, old, group, condition, members, source_nodes = referenced_model(candidate)
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.present_candidate(candidate)
    choose(dialog.material, material); choose(dialog.section, section)
    for row in range(dialog.replace.count()):
        if dialog.replace.item(row).data(Qt.ItemDataRole.UserRole) in old["part_ids"]:
            dialog.replace.item(row).setCheckState(Qt.CheckState.Checked)
    dialog.show(); QApplication.processEvents()
    return dialog, session, group, condition, members, source_nodes


def review(dialog):
    QTest.mouseClick(dialog.review_button, Qt.MouseButton.LeftButton); pump_until(dialog)
    assert dialog._replacement_plan is not None, dialog.error.text()


def test_review_apply_and_existing_reconnection_ui(real_candidate, tmp_path):
    _, _, candidate = real_candidate
    dialog, session, group, condition, members, source_nodes = replacement_dialog(candidate)
    before, revision = states(session), session.document.revision
    assert not dialog.adopt_button.isEnabled() and not dialog.adopt()
    review(dialog)
    assert states(session) == before and session.document.revision == revision
    assert "Old explicit nodes" in dialog.replacement_details.toPlainText()
    assert "Selected old nodes" in dialog.replacement_details.toPlainText()
    assert not dialog.adopt_button.isEnabled()
    dialog.replacement_reviewed.setChecked(True)
    assert dialog.adopt_button.isEnabled()
    QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton); pump_until(dialog)
    assert dialog.result is not None, dialog.error.text()
    assert session.document.revision == revision + 1 and group in session.mesh_relationships()["stale_targets"]
    replaced = states(session)
    session.undo(); assert states(session) == before
    session.redo(); assert states(session) == replaced
    reconnect = PreparedMeshDialog(session); reconnect.show(); QApplication.processEvents()
    choose_group(reconnect, group)
    assert reconnect._mapping == {} and not reconnect.reconnect_button.isEnabled()
    for old_node, source in zip(members, source_nodes):
        link(reconnect, old_node, dialog.result["node_id_map"][source])
    reconnect.reconnect_reviewed.setChecked(True)
    QTest.mouseClick(reconnect.reconnect_button, Qt.MouseButton.LeftButton)
    assert session.mesh_relationships()["stale_targets"] == {}, reconnect.status.text()
    project = tmp_path / "reconnected.caeprep"; session.save_project(project)
    reopened = PrepSession(); reopened.open_project(project)
    assert reopened.mesh_relationships()["stale_targets"] == {}
    assert reopened.card_text(condition) == session.card_text(condition)
    reopened.export_rad(tmp_path / "reconnected.rad")
    reconnect.reject()


@pytest.mark.parametrize("field", ["material", "replace", "size", "source", "length"])
def test_review_clears_when_replacement_input_changes(real_candidate, field):
    _, _, candidate = real_candidate
    dialog, session, *_ = replacement_dialog(candidate)
    before, revision = states(session), session.document.revision
    review(dialog); plan = dialog._replacement_plan
    dialog.replacement_reviewed.setChecked(True)
    if field == "material": dialog.material.setCurrentIndex(0)
    elif field == "replace": dialog.replace.item(0).setCheckState(Qt.CheckState.Unchecked)
    elif field == "size": dialog.size.setText("1.2")
    elif field == "source": dialog.source.setText("different-input.xao")
    else: choose(dialog.length, "cm")
    assert dialog._replacement_plan is None and not dialog.replacement_reviewed.isChecked()
    assert not dialog.replacement_details.toPlainText()
    assert session._cad_mesh_replacement_plan is None
    assert states(session) == before and session.document.revision == revision
    if field in ("size", "source"):
        assert dialog.candidate is None and dialog.quality.rowCount() == 0 and not dialog.adopt_button.isEnabled()
    dialog.reject()


@pytest.mark.parametrize("action", ["close", "cancel", "input", "document"])
def test_late_review_is_discarded_without_publication(real_candidate, monkeypatch, action):
    _, _, candidate = real_candidate
    dialog, session, *_ = replacement_dialog(candidate)
    ready, release = threading.Event(), threading.Event()
    original = session.plan_cad_mesh_replacement
    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        ready.set()
        assert release.wait(10)
        return result
    monkeypatch.setattr(session, "plan_cad_mesh_replacement", delayed)
    assert dialog.review_replacement()
    deadline = time.monotonic() + 10
    try:
        while not ready.is_set():
            assert time.monotonic() < deadline
            QTest.qWait(5)
        if action == "close": dialog.reject()
        elif action == "cancel": QTest.mouseClick(dialog.cancel_job, Qt.MouseButton.LeftButton)
        elif action == "input": dialog.material.setCurrentIndex(0)
        else: session.create_material("Concurrent material", 1e-9, 1000, .2)
        before, revision, paths = states(session), session.document.revision, set(session._source_paths)
    finally: release.set()
    pump_until(dialog)
    assert dialog._replacement_plan is None and session._cad_mesh_replacement_plan is None
    assert not dialog.replacement_reviewed.isChecked() and dialog.result is None
    assert states(session) == before and session.document.revision == revision and session._source_paths == paths
    dialog.reject()
