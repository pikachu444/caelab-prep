import json
from pathlib import Path
import zipfile
import subprocess
import sys

import pytest

from caelab_prep.adapters.solidcraft_source import prepare_solidcraft_step
from caelab_prep.cae_core import PrepError


def design(path, *, format="solidcraft/46", member="document.json"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("container.json", json.dumps({"format": "solidcraft-container/1"}))
        archive.writestr(member, json.dumps({"format": format, "name": "Preflight fixture", "params": [], "features": []}))
    return path


def executable(tmp_path):
    # Never executed: preparation must only capture identity and fixed argv.
    path = tmp_path / "declared-cad.exe"
    path.write_bytes(b"non-executable preparation fixture")
    return path


def test_preparation_captures_source_fixed_argv_and_does_not_clobber(tmp_path):
    source = design(tmp_path / "saved.sc")
    raw = source.read_bytes()
    exe = executable(tmp_path)
    first = prepare_solidcraft_step(exe, source, tmp_path / "jobs", declared_version="0.29.0")
    second = prepare_solidcraft_step(exe, source, tmp_path / "jobs", declared_version="0.29.0")
    assert first.step_path.parent != second.step_path.parent
    assert first.captured_design.read_bytes() == raw == source.read_bytes()
    assert first.argv == (str(exe), "run", "--in", str(first.captured_design), "--out", str(first.step_path), "--quiet", "--param-check", "strict")
    receipt = json.loads((first.step_path.parent / "preparation.json").read_text())
    assert receipt["execution_status"] == "unexecuted" and receipt["authoritative_format_validation"] == "unexecuted"
    assert receipt["declared_producer"] == "SolidCraft" and receipt["expected_step_length_unit"] == "mm"
    assert not first.step_path.exists()


@pytest.mark.parametrize("bad", ["script", "future", "escape"])
def test_scripts_newer_formats_and_unsafe_members_are_rejected_before_staging(tmp_path, bad):
    source = tmp_path / "input.sc"
    if bad == "script":
        source.write_text('{"commands":[{"cmd":"file.export","args":{"path":"elsewhere"}}]}')
    elif bad == "future":
        design(source, format="solidcraft/999")
    else:
        design(source, member="../document.json")
    with pytest.raises(PrepError) as error:
        prepare_solidcraft_step(executable(tmp_path), source, tmp_path / "jobs", declared_version="fixture")
    assert error.value.code == "invalid_cad_source" and not (tmp_path / "jobs").exists()


def test_changed_inputs_and_incomplete_step_fail_without_open_document_mutation(tmp_path):
    source = design(tmp_path / "input.sc")
    exe = executable(tmp_path)
    job = prepare_solidcraft_step(exe, source, tmp_path / "jobs", declared_version="fixture")
    job.step_path.write_bytes(b"not a STEP file")
    with pytest.raises(PrepError) as error:
        job.validate_step()
    assert error.value.code == "invalid_cad_result"
    job.captured_design.write_bytes(b"changed")
    with pytest.raises(PrepError) as error:
        job.validate_step()
    assert error.value.code == "stale_cad_source"


@pytest.mark.parametrize("missing", ["executable", "captured_design"])
def test_missing_captured_input_has_structured_error(tmp_path, missing):
    job = prepare_solidcraft_step(executable(tmp_path), design(tmp_path / "input.sc"),
                                 tmp_path / "jobs", declared_version="fixture")
    getattr(job, missing).unlink()
    with pytest.raises(PrepError) as error:
        job.validate_step()
    assert error.value.code == "stale_cad_source"


def test_real_gmsh_handoff_reads_supplied_step_not_solidcraft_execution(tmp_path):
    gmsh = pytest.importorskip("gmsh")
    from caelab_prep.application.mesh_candidates import validate_native_mesh
    job = prepare_solidcraft_step(executable(tmp_path), design(tmp_path / "input.sc"),
                                 tmp_path / "jobs", declared_version="preflight-fixture")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("Independent STEP fixture")
        gmsh.model.occ.addBox(0, 0, 0, 10, 10, 10)
        gmsh.model.occ.synchronize()
        gmsh.write(str(job.step_path))
    finally:
        gmsh.finalize()
    from caelab_prep.application import PrepSession
    session = PrepSession()
    session.new_document("Supplied STEP", {"mass": "Mg", "length": "mm", "time": "s"})
    material = session.create_material("Steel", 7.8e-9, 210000, .3)["card_id"]
    section = session.create_solid_property("Solid")["card_id"]
    initial_project = tmp_path / "initial-owner.caeprep"
    session.save_project(initial_project)
    handoff = job.generate_mesh_candidate(session, tmp_path / "candidates", 5.0)
    candidate = handoff.candidate
    assert candidate.dimension == 3 and candidate.quality.passed and candidate.length_unit == "mm"
    native = candidate.to_native_mesh()
    assert validate_native_mesh(native) == native
    assert job.receipt()["execution_status"] == "unexecuted"
    revision = session.document.revision
    tokens = session.document.tokens()
    result = job.adopt_supplied_step(session, handoff, material_id=material, property_id=section)
    assert session.document.revision == revision + 1 and result["node_id_map"]
    source_card = next(card for card in session.list_cards() if card["keyword"] == "/NODE")
    text = session.card_text(source_card["id"])
    assert '"verification":"unverified"' in text and handoff.step_sha256 in text and job.design_sha256 in text
    project = tmp_path / "declared-source.caeprep"
    session.save_project(project)
    code = "import sys;from caelab_prep.application import PrepSession;s=PrepSession();s.open_project(sys.argv[1]);print(''.join(s.card_text(c['id']) for c in s.list_cards() if c['keyword']=='/NODE'))"
    reopened_text = subprocess.check_output([sys.executable, "-c", code, str(project)], text=True)
    assert '"verification":"unverified"' in reopened_text and handoff.step_sha256 in reopened_text
    destination = tmp_path / "export_0000.rad"
    session.export_rad(destination)
    assert handoff.step_sha256 in destination.read_text()
    session.undo()
    assert session.document.tokens() == tokens
    session.redo()
    assert job.design_sha256 in session.card_text(source_card["id"])
    # A candidate started for an older owner revision may not adopt into its new state.
    session.create_curve("Unrelated edit during meshing", [(0, 0), (1, 1)])
    before = session.document.tokens(), session.describe()
    with pytest.raises(PrepError) as error:
        job.adopt_supplied_step(session, handoff, material_id=material, property_id=section)
    assert error.value.code == "revision_conflict" and before == (session.document.tokens(), session.describe())
    session.new_document("Different owner", {"mass": "Mg", "length": "mm", "time": "s"})
    session.open_project(initial_project)
    assert session.document.id == handoff.document_id and session.document.revision == handoff.revision
    before = session.document.tokens(), session.describe()
    with pytest.raises(PrepError) as error:
        job.adopt_supplied_step(session, handoff, material_id=material, property_id=section)
    assert error.value.code == "document_epoch_conflict" and before == (session.document.tokens(), session.describe())
