"""Real candidate adoption through Qt; rendering is verified separately."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.application import PrepSession
from caelab_prep.ui.mesh_workflow import NewDocumentDialog, MeshCandidateDialog, SolverExportDialog, candidate_projection
from test_mesh_candidates import real_candidate, synthetic_candidate, TETRAHEDRON, MeshCell

pytestmark = pytest.mark.usefixtures("qt_widgets")


def pump_until(dialog):
    end = time.monotonic() + 15
    while dialog._task is not None and time.monotonic() < end:
        QApplication.processEvents(); time.sleep(.005)
    QApplication.processEvents()
    assert dialog._task is None


def choose(box, value):
    index = box.findData(value)
    assert index >= 0
    box.setCurrentIndex(index)


def setup_session(dimension):
    session = PrepSession()
    dialog = NewDocumentDialog(session)
    dialog.name.setText("User CAD project")
    assert not dialog.apply() and not session.describe().get("document_id")
    for key, unit in (("mass", "Mg"), ("length", "mm"), ("time", "s")): choose(dialog.units[key], unit)
    assert dialog.apply()
    material = session.create_material("User steel", 7.8e-9, 210000, .3)["card_id"]
    section = (session.create_shell_property("User shell", .1) if dimension == 2 else session.create_solid_property("User solid"))["card_id"]
    return session, material, section


def test_new_candidate_ui_adopt_undo_reopen_and_solver_export(real_candidate, tmp_path):
    _, metadata, candidate = real_candidate
    session, material, section = setup_session(candidate.dimension)
    revision = session.describe()["revision"]
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.show()
    dialog.open_candidate(metadata["assets"]["metadata"]); pump_until(dialog)
    assert session.describe()["revision"] == revision
    assert dialog.candidate == candidate and dialog.adopt_button.isEnabled()
    assert "lower-dimensional" in dialog.summary.text()
    choose(dialog.material, material); choose(dialog.section, section)
    QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton); pump_until(dialog)
    assert dialog.result is not None, dialog.error.text()
    assert session.describe()["revision"] == revision + 1
    assert session.describe()["element_count"] == len(candidate.to_native_mesh().elements)
    session.undo(); assert session.describe()["element_count"] == 0
    session.redo()
    path = tmp_path / "adopted.caeprep"; session.save_project(str(path))
    reopened = PrepSession(); reopened.open_project(str(path))
    export = SolverExportDialog(reopened)
    export.path.setText(str(tmp_path / "run" / "user_0000.rad"))
    export.end.setText("1e"); export.interval.setText("1e-6")
    assert not export.apply() and not (tmp_path / "run").exists()
    export.end.setText("1e-4"); assert export.apply(), export.error.text()
    assert (tmp_path / "run" / "user_0001.rad").is_file()


def test_candidate_cancel_invalid_quality_stale_doc_and_preview_stamp(real_candidate):
    _, _, candidate = real_candidate
    session, material, section = setup_session(candidate.dimension)
    original = session.describe()["revision"]
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.present_candidate(candidate); dialog.reject()
    assert session.describe()["revision"] == original and session.describe()["element_count"] == 0
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.present_candidate(candidate)
    choose(dialog.material, material); choose(dialog.section, section)
    session.create_material("Concurrent material", 1e-9, 1000, .2)
    assert dialog.adopt(); pump_until(dialog)
    assert dialog.result is None and dialog.error.text()
    assert session.describe()["element_count"] == 0
    projection = candidate_projection(candidate)
    assert projection["document_id"] != session.describe()["document_id"]
    assert len(projection["cells"]) == len(candidate.to_native_mesh().elements)
    class Preview:
        def set_mesh(self, value): self.projection = value
        def set_selection(self, value): self.selection = value
    dialog.viewport = Preview(); dialog.present_candidate(candidate)
    dialog.quality.selectRow(0); QApplication.processEvents()
    selection = dialog.viewport.selection
    assert selection["document_id"] == candidate.mesh_uuid
    assert selection["refs"][0]["local_id"] == int(dialog.quality.item(0, 0).text())
    if candidate.dimension == 3:
        boundary = next(cell for cell in candidate.cells if cell.dimension == 2 and cell.kind == "triangle3")
        dialog.preview_mode.setCurrentIndex(1)
        dialog.pick_entity({"document_id": candidate.mesh_uuid, "id": boundary.id})
        assert dialog.local_entity.currentData() == boundary.part_uuid
        assert dialog.viewport.selection["ids"]
        assert all(cell["type"] == "triangle3" for cell in dialog.viewport.projection["cells"])
    invalid = synthetic_candidate(TETRAHEDRON, MeshCell(13, 3, 4, "Tetrahedron 4", 1, (1, 3, 2, 4), "part"))
    dialog.present_candidate(invalid)
    assert not dialog.adopt_button.isEnabled()
    assert "inverted" in dialog.quality.item(0, 3).text()
    dialog.reject()


def test_cancel_generation_keeps_existing_model_and_reaps_worker(tmp_path):
    from caelab_prep.adapters.gmsh_backend import CancelledError
    entered = []
    class BlockingBackend:
        def generate(self, *args, cancel_event, **kwargs):
            entered.append(True)
            assert cancel_event.wait(5)
            raise CancelledError("cancelled", "Generation cancelled")
    session, _, _ = setup_session(2)
    before = session.describe()
    dialog = MeshCandidateDialog(session, enable_viewport=False, backend=BlockingBackend())
    dialog.source.setText(str(tmp_path / "source.step")); dialog.output.setText(str(tmp_path)); dialog.size.setText("2")
    assert dialog.generate()
    dialog.reject(); pump_until(dialog)
    assert entered and dialog.result is None and not dialog.isVisible()
    assert session.describe() == before
