"""Shared Qt entry points consume real recipe assets; no OS/VTK claims."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from caelab_prep.application import PrepSession
from caelab_prep.cae_core.errors import PrepError
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog, candidate_projection
from caelab_prep.ui.reference_profiles import PROFILES
from test_mesh_workflow_ui import choose, pump_until
from test_structured_adoption import quad, _native

pytestmark = pytest.mark.usefixtures("qt_widgets")


def _model(unit):
    session = PrepSession()
    session.new_document("User quad model", {"mass": "Mg", "length": unit, "time": "s"})
    material = session.create_material("User material", 7.8e-9, 210000, .3)["card_id"]
    section = session.create_shell_property("User shell", .1)["card_id"]
    return session, material, section


@pytest.mark.parametrize("case_id", ["Q-N3", "Q-D2"])
def test_real_recipe_generation_preview_and_close_do_not_edit_document(case_id, tmp_path):
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable")
    inputs = Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json"
    case = next(item for item in json.loads(inputs.read_text(encoding="utf-8")) if item["id"] == case_id)
    source = tmp_path / "user recipe.json"
    source.write_text(json.dumps(case["input"]), encoding="utf-8")
    original = source.read_bytes()
    session, material, section = _model(case["input"]["unit"])
    before = session.describe()
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.show()
    choose(dialog.source_kind, "structured_recipe")
    dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "assets"))
    assert dialog.size.isHidden() and dialog.policy.isHidden() and dialog.replace.isHidden()
    assert not dialog.length.isEnabled()
    QTest.mouseClick(dialog.generate_button, Qt.MouseButton.LeftButton)
    assert not dialog.source_kind.isEnabled() and not any(button.isEnabled() for button in dialog._browse_buttons)
    pump_until(dialog)
    assert dialog.candidate is not None, dialog.error.text()
    assert len(dialog.candidate.to_native_mesh().elements) == case["expectation"]["elements"]
    assert "scaled Jacobian" in dialog.summary.text()
    assert dialog.length.currentData() == case["input"]["unit"] and not dialog.length.isEnabled()
    assert dialog.quality.item(0, 1).text() == "Min scaled Jacobian"
    assert float(dialog.quality.item(0, 2).text()) == pytest.approx(dialog.candidate.quality.minimum_scaled_jacobian, rel=1e-5)
    projection = candidate_projection(dialog.candidate)
    assert all(cell["type"] == "quad" for cell in projection["cells"])
    assert set(projection["resource_revisions"]) == {dialog.candidate.mesh_uuid}
    assert dialog.candidate.geometry_resource_uuid is None
    assert Path(next(asset.path for asset in dialog.candidate.assets if asset.kind == "recipe")) == source.resolve()
    assert session.describe() == before and source.read_bytes() == original
    if os.environ.get("CAELAB_STRUCTURED_CAPTURE_DIR"):
        folder = Path(os.environ["CAELAB_STRUCTURED_CAPTURE_DIR"])
        folder.mkdir(parents=True, exist_ok=True)
        dialog.resize(960, 640); QApplication.processEvents()
        assert dialog.grab().save(str(folder / (case_id + "-source-offscreen-no3d.png")))
    dialog.reject()
    assert session.describe() == before
    session.adopt_mesh_candidate(dialog.candidate.to_native_mesh(), material_id=material, property_id=section)
    adopted = session.describe()
    for write in (session.save_project, session.export_rad):
        with pytest.raises(PrepError) as error:
            write(source)
        assert error.value.code == "source_overwrite"
        assert source.read_bytes() == original and session.describe() == adopted


@pytest.mark.parametrize("profile", PROFILES)
def test_each_presentation_opens_same_recipe_adoption_with_one_history(quad, profile, monkeypatch, tmp_path):
    case, native = quad
    session, material, section = _model(native.length_unit)
    window = MainWindow(session, enable_viewport=False, presentation=profile)
    window._allow_close = True
    window.show()
    before = session.describe()["revision"]
    metadata = next(asset.path for asset in native.assets if asset.kind == "metadata")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (metadata, "Candidate metadata (*.json)"))
    failures, results = [], []

    def operate():
        dialog = window.mesh_workflow.dialog
        try:
            assert dialog.session is session
            choose(dialog.source_kind, "structured_recipe")
            QTest.mouseClick(dialog.open_button, Qt.MouseButton.LeftButton)
            pump_until(dialog)
            assert dialog.candidate is not None, dialog.error.text()
            assert session.describe()["revision"] == before
            choose(dialog.material, material); choose(dialog.section, section)
            QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton)
            pump_until(dialog)
            assert dialog.result is not None, dialog.error.text()
            results.append(dialog.result)
        except Exception as exc:
            failures.append(exc)
            dialog.reject()

    QTimer.singleShot(0, operate)
    window.mesh_workflow.mesh_action.trigger()
    assert not failures, failures
    assert len(results) == 1
    assert session.describe()["revision"] == before + 1
    assert session.describe()["element_count"] == case["expectation"]["elements"]
    session.undo(); assert session.describe()["element_count"] == 0
    session.redo(); assert session.describe()["element_count"] == case["expectation"]["elements"]
    project, output = tmp_path / "quad.caeprep", tmp_path / "quad_0000.rad"
    session.save_project(project)
    saved = subprocess.run([sys.executable, "-m", "caelab_prep", "export", str(project), "--output", str(output)],
                           capture_output=True, text=True, timeout=30)
    assert saved.returncode == 0, saved.stdout + saved.stderr
    nodes, elements, parts, groups = _native(output.read_bytes())
    assert len(nodes) == case["expectation"]["active_nodes"]
    assert len(elements) == case["expectation"]["elements"]
    assert len(parts) == len(native.parts)
    assert sum(name.startswith("/GRSHEL/SHEL/") for name in groups) == len(native.parts)
    assert window.close()


def test_same_document_reopen_invalidates_prepared_adoption(quad, tmp_path):
    _, native = quad
    session, material, section = _model(native.length_unit)
    project = tmp_path / "same.caeprep"
    session.save_project(project)
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.show(); choose(dialog.source_kind, "structured_recipe")
    dialog.open_candidate(next(asset.path for asset in native.assets if asset.kind == "metadata"))
    pump_until(dialog)
    choose(dialog.material, material); choose(dialog.section, section)
    stamp = session.describe()
    session.open_project(project)
    current = session.describe()
    assert current["document_id"] == stamp["document_id"] and current["revision"] > stamp["revision"]
    assert current["document_epoch"] != stamp["document_epoch"]
    assert dialog.adopt(); pump_until(dialog)
    assert dialog.result is None and dialog.candidate is None
    assert not dialog.adopt_button.isEnabled() and dialog.error.text()
    assert session.describe() == current
    dialog.reject()


@pytest.mark.parametrize("contents,message", [
    ("[]", "planar quad recipe"),
    ('{"mode":"hex"}', "planar quad recipe"),
    ('{"mode":"quad","mode":"quad"}', "Repeated JSON field"),
    (" " * 1_048_577, "1 MiB"),
], ids=["array", "unsupported-family", "duplicate-keys", "oversize"])
def test_invalid_recipe_then_source_switch_recovers_without_model_edit(tmp_path, contents, message):
    source = tmp_path / "invalid.json"
    source.write_text(contents, encoding="utf-8")
    session, _, _ = _model("mm")
    before = session.describe()
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.show(); choose(dialog.source_kind, "structured_recipe")
    assert dialog.form.labelForField(dialog.local_entity).text() == "Patch"
    assert "3D preview is disabled" in dialog.pick_hint.text()
    dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "assets"))
    assert dialog.generate(); pump_until(dialog)
    assert dialog.candidate is None and message in dialog.error.text() and not dialog.adopt_button.isEnabled()
    assert not (tmp_path / "assets").exists()
    choose(dialog.source_kind, "cad_gmsh")
    assert not dialog.size.isHidden() and dialog.size.isEnabled()
    assert not dialog.replace.isHidden() and not dialog.adopt_button.isEnabled()
    assert session.describe() == before
    dialog.reject()


def test_cancel_running_recipe_worker_reaps_owned_process_and_preserves_model(quad, monkeypatch, tmp_path):
    from caelab_prep.application import structured_mesh

    _, native = quad
    source = next(asset.path for asset in native.assets if asset.kind == "recipe")
    original = Path(source).read_bytes()
    session, _, _ = _model(native.length_unit)
    before = session.describe()
    processes = []
    popen = structured_mesh.subprocess.Popen

    def record_process(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(structured_mesh.subprocess, "Popen", record_process)
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.show(); choose(dialog.source_kind, "structured_recipe")
    dialog.source.setText(source); dialog.output.setText(str(tmp_path / "cancelled-assets"))
    QTest.mouseClick(dialog.generate_button, Qt.MouseButton.LeftButton)
    deadline = time.monotonic() + 5
    while not any(process.poll() is None for process in processes) and dialog._task is not None and time.monotonic() < deadline:
        QApplication.processEvents(); time.sleep(.005)
    assert any(process.poll() is None for process in processes), "No running owned worker was observed; cancellation was not tested"
    QTest.mouseClick(dialog.cancel_job, Qt.MouseButton.LeftButton)
    pump_until(dialog)
    assert all(process.poll() is not None for process in processes)
    assert dialog.candidate is None and not dialog.adopt_button.isEnabled()
    assert session.describe() == before and Path(source).read_bytes() == original
    dialog.reject()
