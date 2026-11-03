"""Structured division drafts reuse generation, source protection and one adoption."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest

from caelab_prep.application import PrepSession
from caelab_prep.application import structured_mesh
from caelab_prep.application.mesh_candidates import AssetDigest
from caelab_prep.cae_core.errors import PrepError
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog
from caelab_prep.ui.reference_profiles import PROFILES
from test_mesh_workflow_ui import choose, pump_until
from test_structured_adoption import _native
from test_structured_mesh_ui import _model

pytestmark = pytest.mark.usefixtures("qt_widgets")


def _case(case_id):
    path = Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json"
    return next(case for case in json.loads(path.read_text(encoding="utf-8")) if case["id"] == case_id)


def _source(tmp_path, recipe, name="original recipe.json"):
    path = tmp_path / name
    path.write_text(json.dumps(recipe), encoding="utf-8")
    return path


@pytest.mark.parametrize("case_id", ["Q-N3", "Q-D2", "H-N3", "H-D2"])
@pytest.mark.parametrize("profile", PROFILES)
def test_every_presentation_edits_ordered_divisions_and_cancels_without_history(case_id, profile, tmp_path):
    recipe = _case(case_id)["input"]
    source = _source(tmp_path, recipe)
    original = source.read_bytes()
    session, _, _ = _model(recipe["unit"], 3 if recipe["mode"] == "hex" else 2)
    before = session.describe()
    window = MainWindow(session, enable_viewport=False, presentation=profile)
    window._allow_close = True
    failures = []

    def operate():
        dialog = window.mesh_workflow.dialog
        try:
            choose(dialog.source_kind, "structured_recipe")
            dialog.source.setText(str(source))
            QTest.mouseClick(dialog.load_divisions_button, Qt.MouseButton.LeftButton)
            patches = recipe.get("patches", [recipe])
            assert [[edit.numeric_value() for edit in row] for row in dialog.division_edits] == [p["divisions"] for p in patches]
            assert dialog.divisions.horizontalHeaderItem(1).text() == "Edge 1–2"
            assert dialog.layers.isHidden() == (recipe["mode"] != "hex")
            if recipe["mode"] == "hex": assert dialog.layers.numeric_value() == recipe["layers"]
            dialog.division_edits[0][0].setText("1.5")
            assert not dialog.generate() and "whole number" in dialog.error.text()
            assert not dialog.adopt_button.isEnabled() and dialog._task is None
            assert dialog.source.text() == str(source)
            assert session.describe() == before and source.read_bytes() == original
        except Exception as exc:
            failures.append(exc)
        finally:
            dialog.reject()

    QTimer.singleShot(0, operate)
    window.mesh_workflow.mesh_action.trigger()
    assert not failures, failures
    assert session.describe() == before and source.read_bytes() == original
    assert window.close()


@pytest.mark.parametrize("case_id,divisions,layers,elements,nodes", [
    ("Q-N3", [[18, 10]], None, 180, 209),
    ("Q-D2", [[12, 6], [9, 6]], None, 126, 154),
    ("H-N3", [[10, 6]], 6, 360, 539),
    ("H-D2", [[8, 6], [7, 6]], 8, 720, 1008),
])
def test_edited_real_candidate_protects_original_at_publish_and_v6_reopen(case_id, divisions, layers, elements, nodes, tmp_path):
    pytest.importorskip("gmsh")
    recipe = _case(case_id)["input"]
    source = _source(tmp_path, recipe)
    original = source.read_bytes()
    expected = deepcopy(recipe)
    for patch, counts in zip(expected.get("patches", [expected]), divisions):
        patch["divisions"] = counts
    if layers is not None: expected["layers"] = layers
    session, material, section = _model(recipe["unit"], 3 if layers is not None else 2)
    before = session.describe()
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    dialog.show(); choose(dialog.source_kind, "structured_recipe")
    dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "assets"))
    assert dialog.load_divisions()
    for row, counts in zip(dialog.division_edits, divisions):
        for edit, count in zip(row, counts): edit.setText(str(count))
    if layers is not None: dialog.layers.setText(str(layers))
    assert dialog.generate(); pump_until(dialog)
    candidate = dialog.candidate
    assert candidate is not None, dialog.error.text()
    assert len(candidate.to_native_mesh().elements) == elements
    assert len(candidate.nodes) == nodes
    assert json.loads(candidate.recipe_json) == expected
    assets = {asset.kind: asset for asset in candidate.assets}
    assert len(assets) == 5 and assets["source_recipe"].path == str(source.resolve())
    assert json.loads(Path(assets["recipe"].path).read_text(encoding="utf-8")) == expected
    assert candidate.quality.passed and dialog.adopt_button.isEnabled()
    assert source.read_bytes() == original and session.describe() == before
    if layers is not None:
        assert candidate.quality.measure == pytest.approx(_case(case_id)["expectation"]["measure"])
        dialog.layers.setText("-")
        assert dialog.candidate is None and not dialog.adopt_button.isEnabled()
        assert dialog.quality.rowCount() == 0 and "Passed" not in dialog.summary.text()
        assert not dialog.generate() and dialog._task is None
        dialog.present_candidate(candidate)
        assert dialog.candidate is candidate and dialog.layers.numeric_value() == layers
    if case_id == "H-D2":
        by_part = [[cell.node_ids for cell in candidate.to_native_mesh().elements if cell.part_uuid == part.uuid]
                   for part in candidate.parts]
        assert len(by_part) == 2
        assert len(set(sum(by_part[0], ())) & set(sum(by_part[1], ()))) == 63
        sides = ((0,1,2,3), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7))
        faces = [{frozenset(cell[i] for i in side) for cell in cells for side in sides} for cells in by_part]
        assert len(faces[0] & faces[1]) == 48
    dialog.division_edits[0][0].setText("-")
    assert dialog.candidate is None and not dialog.adopt_button.isEnabled()
    assert dialog.quality.rowCount() == 0 and "Passed" not in dialog.summary.text()
    assert not dialog.generate() and dialog._task is None

    # A different loaded draft must not leak into a reopened saved candidate.
    other = _source(tmp_path, recipe, "other recipe.json")
    dialog.source.setText(str(other)); assert dialog.load_divisions()
    dialog.division_edits[0][0].setText("3")
    assert dialog.open_candidate(candidate.manifest_path); pump_until(dialog)
    assert dialog.source.text() == str(source.resolve())
    assert [[edit.numeric_value() for edit in row] for row in dialog.division_edits] == divisions
    if layers is not None: assert dialog.layers.numeric_value() == layers
    assert dialog.candidate == candidate
    observed = []
    project = tmp_path / "published.caeprep"

    def at_publish(event):
        if event["kind"] != "structure" or event.get("change", {}).get("label") != "Adopt mesh candidate": return
        for write in (session.save_project, session.export_rad):
            with pytest.raises(PrepError) as error: write(source)
            observed.append(error.value.code)
        session.save_project(project)

    session.subscribe(at_publish)
    choose(dialog.material, material); choose(dialog.section, section)
    assert dialog.adopt(); pump_until(dialog)
    assert dialog.result is not None, dialog.error.text()
    assert observed == ["source_overwrite", "source_overwrite"]
    assert session.describe()["revision"] == before["revision"] + 1
    assert session.describe()["element_count"] == elements
    session.undo(); assert session.describe()["element_count"] == 0
    session.redo(); assert session.describe()["element_count"] == elements
    reopened = PrepSession(); reopened.open_project(project)
    assert reopened.describe()["element_count"] == elements
    for write in (reopened.save_project, reopened.export_rad):
        with pytest.raises(PrepError) as error: write(source)
        assert error.value.code == "source_overwrite"
    output = tmp_path / "edited_0000.rad"
    reopened.export_rad(output)
    native_nodes, native_elements, _, _ = _native(output.read_bytes())
    assert len(native_nodes) == nodes and len(native_elements) == elements
    assert source.read_bytes() == original
    dialog.reject()


@pytest.mark.parametrize("change", ["shared", "budget", "zero", "upper"])
@pytest.mark.parametrize("case_id", ["Q-D2", "H-D2"])
def test_invalid_division_draft_starts_no_worker(change, case_id, tmp_path):
    recipe = _case(case_id)["input"]
    source = _source(tmp_path, recipe)
    session, _, _ = _model(recipe["unit"])
    before = session.describe()
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    choose(dialog.source_kind, "structured_recipe"); dialog.source.setText(str(source))
    dialog.output.setText(str(tmp_path / "assets")); assert dialog.load_divisions()
    if change == "shared": dialog.division_edits[0][1].setText(str(recipe["patches"][0]["divisions"][1] + 1))
    elif change == "budget":
        for row in dialog.division_edits:
            for edit in row: edit.setText("10000")
    else: dialog.division_edits[0][0].setText("0" if change == "zero" else "10001")
    assert not dialog.generate() and dialog._task is None
    assert dialog.error.text() and not dialog.adopt_button.isEnabled()
    assert not (tmp_path / "assets").exists() and session.describe() == before
    choose(dialog.source_kind, "cad_gmsh")
    assert dialog._seed_recipe is None and dialog.divisions.isHidden()
    dialog.reject()


@pytest.mark.parametrize("change", ["unit", "geometry", "hash", "hex"])
def test_original_provenance_cannot_admit_other_recipe_changes(change, monkeypatch, tmp_path):
    recipe = _case("Q-N3")["input"]
    source = _source(tmp_path, recipe)
    _, origin = structured_mesh.read_recipe_input(source)
    edited = deepcopy(recipe); edited["divisions"] = [18, 10]
    if change == "unit": edited["unit"] = "mm"
    elif change == "geometry":
        edited["corners"] = [[x + 1, y, z] for x, y, z in edited["corners"]]
    elif change == "hash": origin = AssetDigest(origin.kind, origin.path, "0" * 64)
    else: edited.update(mode="hex", vector=[6.4, -4.8, 6], layers=2)
    monkeypatch.setattr(structured_mesh, "_child", lambda *a, **k: pytest.fail("invalid provenance launched a worker"))
    with pytest.raises(PrepError) as error:
        structured_mesh.generate_structured_mesh(edited, tmp_path / "assets", source_recipe=origin)
    assert error.value.code in ("invalid_recipe", "candidate_changed")
    assert not (tmp_path / "assets").exists()


def test_original_change_after_load_is_rejected_without_generation(monkeypatch, tmp_path):
    recipe = _case("Q-N3")["input"]
    source = _source(tmp_path, recipe)
    session, _, _ = _model(recipe["unit"])
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    choose(dialog.source_kind, "structured_recipe"); dialog.source.setText(str(source))
    dialog.output.setText(str(tmp_path / "assets")); assert dialog.load_divisions()
    dialog.division_edits[0][0].setText("18")
    source.write_text(json.dumps(recipe) + "\n", encoding="utf-8")
    monkeypatch.setattr(structured_mesh, "_child", lambda *a, **k: pytest.fail("stale input launched a worker"))
    assert dialog.generate(); pump_until(dialog)
    assert dialog.candidate is None and "changed after review" in dialog.error.text()
    assert not (tmp_path / "assets").exists()
    dialog.reject()


@pytest.mark.parametrize("case_id", ["Q-N3", "Q-D2", "H-N3", "H-D2"])
@pytest.mark.parametrize("change", ["unit", "geometry", "identity"])
def test_reopened_candidate_checks_original_recipe_before_sdk(case_id, change, monkeypatch, tmp_path):
    from uuid import uuid4
    recipe = _case(case_id)["input"]
    source = deepcopy(recipe)
    if change == "unit": source["unit"] = "mm" if source["unit"] == "cm" else "cm"
    elif change == "geometry":
        if "vertices" in source:
            source["vertices"] = {key: [x + 1, y, z] for key, (x, y, z) in source["vertices"].items()}
        else: source["corners"] = [[x + 1, y, z] for x, y, z in source["corners"]]
    elif "patches" in source: source["patches"][0]["id"] = "different patch"
    else: source["name"] = "different patch"
    paths = {"recipe": _source(tmp_path, recipe, "snapshot.json"),
             "source_recipe": _source(tmp_path, source, "provenance.json"),
             "msh": tmp_path / "mesh.msh", "sdk": tmp_path / "sdk.json"}
    paths["msh"].write_bytes(b"unused: provenance is rejected first")
    paths["sdk"].write_text("{}", encoding="utf-8")
    assets = {key: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for key, path in paths.items()}
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"schema": "caelab.structured-recipe", "version": 1,
                                   "mesh_uuid": str(uuid4()), "assets": assets}), encoding="utf-8")
    monkeypatch.setattr(structured_mesh, "_child", lambda *a, **k: pytest.fail("wrong provenance launched an SDK reader"))
    with pytest.raises(PrepError) as error:
        structured_mesh.read_structured_mesh_candidate(metadata)
    assert error.value.code == "invalid_recipe"


def test_original_change_during_generation_cannot_publish_manifest(monkeypatch, tmp_path):
    recipe = _case("Q-N3")["input"]
    source = _source(tmp_path, recipe)
    _, origin = structured_mesh.read_recipe_input(source)
    edited = deepcopy(recipe); edited["divisions"] = [18, 10]
    calls = []
    def replace_source(module, *args, **kwargs):
        calls.append(module)
        source.write_text(json.dumps(recipe) + "\n", encoding="utf-8")
    monkeypatch.setattr(structured_mesh, "_child", replace_source)
    with pytest.raises(PrepError) as error:
        structured_mesh.generate_structured_mesh(edited, tmp_path / "assets", source_recipe=origin)
    assert error.value.code == "candidate_changed"
    assert calls == ["caelab_prep.application.structured_mesh_worker"]
    assert not list((tmp_path / "assets").rglob("metadata.json"))


@pytest.mark.parametrize("text", ["", "1.5", "0", "10001", "10000"])
def test_invalid_hex_layers_keep_draft_and_start_no_worker(text, tmp_path):
    recipe = _case("H-N3")["input"]
    source = _source(tmp_path, recipe)
    session, _, _ = _model(recipe["unit"], 3)
    before = session.describe()
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    choose(dialog.source_kind, "structured_recipe"); dialog.source.setText(str(source))
    dialog.output.setText(str(tmp_path / "assets")); assert dialog.load_divisions()
    dialog.layers.setText(text)
    assert not dialog.generate() and dialog._task is None and dialog.error.text()
    assert dialog.layers.text() == text and not (tmp_path / "assets").exists()
    assert session.describe() == before and not dialog.adopt_button.isEnabled()
    choose(dialog.source_kind, "cad_gmsh")
    assert dialog.layers.isHidden() and dialog.layers.text() == ""
    dialog.reject()


@pytest.mark.parametrize("case_id", ["H-N3", "H-D2"])
@pytest.mark.parametrize("change", ["vector", "mode"])
def test_hex_original_vector_and_mode_cannot_change(case_id, change, monkeypatch, tmp_path):
    recipe = _case(case_id)["input"]
    source = _source(tmp_path, recipe)
    _, origin = structured_mesh.read_recipe_input(source)
    edited = deepcopy(recipe); edited["layers"] += 1
    if change == "vector": edited["vector"] = [value * 1.1 for value in edited["vector"]]
    else:
        edited["mode"] = "quad"; del edited["vector"]; del edited["layers"]
    monkeypatch.setattr(structured_mesh, "_child", lambda *a, **k: pytest.fail("changed source geometry launched a worker"))
    with pytest.raises(PrepError) as error:
        structured_mesh.generate_structured_mesh(edited, tmp_path / "assets", source_recipe=origin)
    assert error.value.code == "invalid_recipe" and not (tmp_path / "assets").exists()


@pytest.mark.parametrize("case_id", ["H-N3", "H-D2"])
def test_loaded_layers_escape_restores_loaded_value_and_source_change_clears_it(case_id, tmp_path):
    recipe = _case(case_id)["input"]
    source = _source(tmp_path, recipe)
    session, _, _ = _model(recipe["unit"], 3)
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    choose(dialog.source_kind, "structured_recipe"); dialog.source.setText(str(source))
    assert dialog.load_divisions()
    dialog.layers.setText(str(recipe["layers"] + 1))
    QTest.keyClick(dialog.layers, Qt.Key.Key_Escape)
    assert dialog.layers.text() == str(recipe["layers"])
    dialog.source.clear()
    QTest.keyClick(dialog.layers, Qt.Key.Key_Escape)
    assert dialog.layers.text() == "" and dialog._seed_recipe is None
    assert dialog.candidate is None and not dialog.adopt_button.isEnabled()
    dialog.reject()
