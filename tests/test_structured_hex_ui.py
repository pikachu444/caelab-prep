"""The same native mesh dialog consumes explicit sweep candidates."""

import importlib.util
import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from caelab_prep.ui.mesh_workflow import MeshCandidateDialog, candidate_projection
from caelab_prep.ui.reference_profiles import PROFILES
from test_mesh_workflow_ui import choose, pump_until
from test_structured_hex_adoption import sweep
from test_structured_mesh_ui import _model, exercise_presentation_adoption

pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.mark.parametrize("profile", PROFILES)
def test_sweep_each_presentation_uses_same_candidate_and_one_history(sweep, profile, monkeypatch, tmp_path):
    exercise_presentation_adoption(sweep, profile, monkeypatch, tmp_path)


@pytest.mark.parametrize("case_id", ["H-N3", "H-D2"])
def test_generate_sweep_reports_volume_and_preserves_source_on_close(case_id, tmp_path):
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable")
    cases = json.loads((Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json").read_text(encoding="utf-8"))
    case = next(row for row in cases if row["id"] == case_id)
    source = tmp_path / "original sweep.json"
    source.write_text(json.dumps(case["input"]), encoding="utf-8")
    original = source.read_bytes()
    session, _, _ = _model(case["input"]["unit"], 3)
    shell = session.create_shell_property("Unrelated shell", .2)["card_id"]
    before = session.describe()
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.show(); choose(dialog.source_kind, "structured_recipe")
    dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "assets"))
    QTest.mouseClick(dialog.generate_button, Qt.MouseButton.LeftButton)
    pump_until(dialog)
    assert dialog.candidate is not None, dialog.error.text()
    assert dialog.candidate.dimension == 3 and dialog.adopt_button.isEnabled()
    projection = candidate_projection(dialog.candidate)
    assert len(projection["cells"]) == case["expectation"]["elements"]
    assert all(cell["type"] == "hexahedron" and len(cell["nodes"]) == 8 for cell in projection["cells"])
    assert dialog.quality.item(2, 1).text() == f"Volume ({case['input']['unit']}^3)"
    assert float(dialog.quality.item(2, 2).text()) == pytest.approx(case["expectation"]["measure"])
    assert "0.25" in dialog.quality.item(0, 3).text() and "10" in dialog.quality.item(1, 3).text()
    assert dialog.section.findData(shell) < 0
    assert not dialog.preview_mode.isVisible() and not dialog.dimension.isVisible()
    assert session.describe() == before and source.read_bytes() == original
    dialog.reject()
    assert session.describe() == before and source.read_bytes() == original
