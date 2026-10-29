import json
from pathlib import Path
import shutil
import zipfile

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application import session as session_module
from caelab_prep.cae_core import PrepError


FIXTURE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"


def test_saved_project_is_independent_and_preserves_patch_ids_and_savepoint(tmp_path):
    originals = tmp_path / "original"; originals.mkdir()
    source = originals / "a.rad"; shutil.copyfile(FIXTURE, source)
    session = PrepSession(); session.open_rad(str(source))
    material = next(c for c in session.list_cards() if c["keyword"] == "/MAT/PLAS_TAB/1")
    session.set_field(material["id"], "young_modulus", 205000)
    project = tmp_path / "a.caeprep"; session.save_project(str(project))
    assert not session.describe()["dirty"]
    session.set_field(material["id"], "young_modulus", 200000)
    session.undo()
    assert not session.describe()["dirty"] and session.describe()["revision"] == 3
    shutil.rmtree(originals)
    reopened = PrepSession(); reopened.open_project(str(project))
    assert reopened.describe()["document_id"] == session.describe()["document_id"]
    assert reopened.card_fields(material["id"])[1]["value"] == 205000
    reopened.export_rad(str(tmp_path / "out.rad"))
    assert b"205000.0" in (tmp_path / "out.rad").read_bytes()
    with zipfile.ZipFile(project) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert z.read(manifest["resources"][0]["raw_member"]) == FIXTURE.read_bytes()


def test_include_resources_are_loaded_and_portably_exported(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    root = inputs / "input.rad"
    root.write_bytes(b"/BEGIN\nModel\n      2025         0\n#include nodes.rad\n#include elements.rad\n/END\n")
    (inputs / "nodes.rad").write_text("/NODE\n" + "".join(f"{i:10d}{x:20g}{y:20g}{0:20g}\n" for i, x, y in [(21,0,0),(31,1,0),(41,1,1),(51,0,1)]))
    (inputs / "elements.rad").write_text("/SHELL/5\n" + "".join(f"{i:10d}" for i in [91,21,31,41,51]) + "\n")
    session = PrepSession(); session.open_rad(str(root))
    assert session.describe()["node_count"] == 4 and session.describe()["element_count"] == 1
    assert session.mesh_view()["cells"][0]["nodes"] == [21,31,41,51]
    project = tmp_path / "included.caeprep"; session.save_project(str(project))
    shutil.rmtree(inputs)
    reopened = PrepSession(); reopened.open_project(str(project))
    destination = tmp_path / "export" / "input.rad"
    reopened.export_rad(str(destination))
    assert (destination.parent / "nodes.rad").is_file()
    check = PrepSession(); check.open_rad(str(destination))
    assert check.describe()["element_count"] == 1


def test_bad_open_and_unresolved_include_do_not_silently_export(tmp_path):
    session = PrepSession(); session.open_rad(str(FIXTURE))
    identity = session.describe()["document_id"]
    bad = tmp_path / "bad.caeprep"; bad.write_bytes(b"not a zip")
    with pytest.raises(PrepError): session.open_project(str(bad))
    assert session.describe()["document_id"] == identity
    source = tmp_path / "missing.rad"; source.write_text("/BEGIN\nModel\n#include absent.rad\n/END\n")
    session.open_rad(str(source))
    assert session.describe()["diagnostics"][0]["unresolved_include"]
    # A caller changing its returned diagnostic must not change export guards.
    session.diagnostics()[0]["unresolved_include"] = False
    with pytest.raises(PrepError) as error: session.export_rad(str(tmp_path / "output.rad"))
    assert error.value.code == "unresolved_include"
    assert not (tmp_path / "output.rad").exists()


def test_original_input_cannot_be_overwritten(tmp_path):
    source = tmp_path / "source.rad"; shutil.copyfile(FIXTURE, source)
    session = PrepSession(); session.open_rad(str(source))
    with pytest.raises(PrepError): session.export_rad(str(source))
    with pytest.raises(PrepError): session.save_project(str(source))
    assert source.read_bytes() == FIXTURE.read_bytes()


def test_invalid_manifest_shape_is_structured_and_atomic(tmp_path):
    session = PrepSession(); session.open_rad(str(FIXTURE))
    identity = session.describe()["document_id"]
    bad = tmp_path / "array.caeprep"
    with zipfile.ZipFile(bad, "w") as z: z.writestr("manifest.json", "[]")
    with pytest.raises(PrepError) as error: session.open_project(str(bad))
    assert error.value.code == "invalid_project"
    assert session.describe()["document_id"] == identity


@pytest.mark.parametrize("location", ["document_id", "logical_path"])
def test_invalid_manifest_scalar_is_structured_and_atomic(tmp_path, location):
    session = PrepSession(); session.open_rad(str(FIXTURE))
    good = tmp_path / "good.caeprep"; session.save_project(str(good))
    before = session.describe()
    with zipfile.ZipFile(good) as z:
        contents = {name: z.read(name) for name in z.namelist()}
    manifest = json.loads(contents["manifest.json"])
    if location == "logical_path": manifest["resources"][0][location] = 7
    else: manifest[location] = 7
    contents["manifest.json"] = json.dumps(manifest).encode()
    bad = tmp_path / "bad.caeprep"
    with zipfile.ZipFile(bad, "w") as z:
        for name, content in contents.items(): z.writestr(name, content)
    with pytest.raises(PrepError): session.open_project(str(bad))
    assert session.describe() == before


def test_include_enddata_ignores_tail_but_preserves_all_bytes(tmp_path):
    inputs = tmp_path / "inputs"; inputs.mkdir()
    root_raw = b"/BEGIN\r\nModel\r\n#include active.rad\r\n/END\r\n"
    active = ("/NODE\r\n" + f"{17:10d}{1:20g}{2:20g}{3:20g}\r\n" +
              "  #ENDDATA\r\n#include never-read-by-solver.rad\r\n/NODE\r\n" +
              f"{99:10d}{9:20g}{9:20g}{9:20g}\r\n").encode()
    root = inputs / "root.rad"; root.write_bytes(root_raw)
    (inputs / "active.rad").write_bytes(active)
    session = PrepSession(); session.open_rad(str(root))
    assert session.mesh_view()["node_ids"] == [17]
    assert not any(d.get("unresolved_include") for d in session.diagnostics())
    assert len([c for c in session.list_cards() if c["keyword"] == "/NODE"]) == 1
    project = tmp_path / "a.caeprep"; session.save_project(str(project))
    shutil.rmtree(inputs)
    reopened = PrepSession(); reopened.open_project(str(project))
    assert reopened.mesh_view()["node_ids"] == [17]
    destination = tmp_path / "export" / "root.rad"
    reopened.export_rad(str(destination))
    assert destination.read_bytes() == root_raw
    assert (destination.parent / "active.rad").read_bytes() == active


def test_casefold_include_collisions_are_diagnosed_before_save(tmp_path):
    root = tmp_path / "root.rad"
    root.write_text("/BEGIN\nModel\n#include A.rad\n#include a.rad\n/END\n")
    (tmp_path / "A.rad").write_text("/NODE\n" + f"{1:10d}{0:20g}{0:20g}{0:20g}\n")
    if (tmp_path / "a.rad").exists():
        pytest.skip("Distinct casefold-colliding inputs require a case-sensitive filesystem")
    (tmp_path / "a.rad").write_text("/NODE\n" + f"{2:10d}{1:20g}{0:20g}{0:20g}\n")
    session = PrepSession(); session.open_rad(str(root))
    assert session.mesh_view()["node_ids"] == [1, 2]
    assert any(d["code"] == "project_path_collision" for d in session.diagnostics())
    destination = tmp_path / "collision.caeprep"
    with pytest.raises(PrepError) as error: session.save_project(str(destination))
    assert error.value.code == "project_path_collision" and not destination.exists()


def test_failed_project_sync_preserves_saved_file_and_unsaved_model(tmp_path, monkeypatch):
    session = PrepSession(); session.open_rad(str(FIXTURE))
    project = tmp_path / "a.caeprep"; session.save_project(str(project))
    saved_bytes = project.read_bytes()
    material = next(c for c in session.list_cards() if c["keyword"] == "/MAT/PLAS_TAB/1")
    session.set_field(material["id"], "young_modulus", 205000)
    before = session.describe()
    events = []; session.subscribe(events.append)

    def fail_sync(_descriptor):
        raise OSError("simulated storage sync failure")

    with monkeypatch.context() as patch:
        patch.setattr(session_module.os, "fsync", fail_sync)
        with pytest.raises(PrepError) as error: session.save_project(str(project))
    assert error.value.code == "project_write_error"
    assert project.read_bytes() == saved_bytes
    assert session.describe() == before and session.describe()["dirty"]
    assert events == [] and list(tmp_path.glob(".caeprep-*")) == []
    reopened = PrepSession(); reopened.open_project(str(project))
    assert reopened.card_fields(material["id"])[1]["value"] == 210000
