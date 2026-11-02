"""B2 references remain distinct from source archives and native geometry."""
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError

MODELS = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies"


def assembly():
    session = PrepSession(); session.open_rad(MODELS / "beam_shell_tet/model_0000.rad")
    plan = session.plan_import_source(MODELS / "truss_shell_hex/model_0000.rad")
    session.import_source(plan["plan_id"])
    return session, plan["source"]["id"]


def test_repeated_reference_identity_history_payload_sharing_and_new_process_reopen(tmp_path):
    session, source_id = assembly()
    view = session.mesh_view(); raw = {r.id:r.raw for r in session._deck_resources()}
    events = []; session.subscribe(events.append)
    before = session.document.revision
    first = session.create_instance_reference("Repeated source", source_id)["instance_id"]
    second = session.create_instance_reference("Repeated source", source_id)["instance_id"]
    base = session.create_instance_reference("Base reference")["instance_id"]
    rows = session.instance_references()
    assert first != second and rows[0]["source_id"] == rows[1]["source_id"] == source_id
    assert rows[0]["resource_ids"] == rows[1]["resource_ids"]
    assert rows[2]["id"] == base and rows[2]["source_id"] is None
    assert {row["status"] for row in rows} == {"not-expanded"}
    assert session.document.revision == before + 3 and len(events) == 3
    assert len(session.source_models()) == 1
    assert session.mesh_view()["cells"] is view["cells"] and len(view["cells"]) == 6
    assert all(r.raw is raw[r.id] for r in session._deck_resources())
    rows[0]["resource_ids"].clear()
    assert session.instance_references()[0]["resource_ids"]
    project = tmp_path / "instances.caeprep"; session.save_project(project)
    script = "import json,sys;from caelab_prep.application import PrepSession;s=PrepSession();s.open_project(sys.argv[1]);print(json.dumps(s.instance_references()))"
    actual = json.loads(subprocess.check_output([sys.executable,"-c",script,str(project)], text=True))
    assert actual == session.instance_references()
    session.delete_instance_reference(second)
    assert [row["id"] for row in session.instance_references()] == [first,base]
    session.undo(); assert session.instance_references() == actual
    session.redo(); assert [row["id"] for row in session.instance_references()] == [first,base]


def test_unexpanded_reference_blocks_all_native_exports_without_omitting_it(tmp_path):
    session, source_id = assembly()
    identifier = session.create_instance_reference("Not native geometry", source_id)["instance_id"]
    case = session.create_analysis_case("No conditions", [], 1e-6, 5e-7, "s")["case_id"]
    for export in (lambda path: session.export_rad(path),
                   lambda path: session.export_solver_inputs(path, 1e-6, 5e-7),
                   lambda path: session.export_analysis_case(path,case)):
        path = tmp_path / "blocked_0000.rad"
        with pytest.raises(PrepError) as error: export(path)
        assert error.value.code == "unexpanded_instances" and not path.exists()
    session.delete_instance_reference(identifier)
    session.export_analysis_case(tmp_path/"restored_0000.rad",case)
    assert (tmp_path/"restored_0000.rad").exists()


def test_wrong_source_and_second_compound_failure_leave_all_state_unchanged():
    session, source_id = assembly()
    before = session.create_instance_reference("Existing", source_id)["instance_id"]
    session.undo()
    tokens = session.document.tokens(); revision = session.document.revision
    events = []; session.subscribe(events.append)
    for arguments in ({"name":"wrong source", "source_id":str(uuid4())}, {"name":"wrong type", "source_id":[]},
                      {"name":"cross source", "source_id":source_id, "resource_ids":[session._root_id]}):
        with pytest.raises(PrepError): session.create_instance_reference(**arguments)
        assert session.document.tokens() == tokens and session.document.revision == revision
    with pytest.raises(PrepError):
        session.execute_many([
            {"operation":"create_instance_reference", "arguments":{"name":"candidate", "source_id":source_id}},
            {"operation":"delete_instance_reference", "arguments":{"instance_id":str(uuid4())}}])
    assert session.document.tokens() == tokens and session.document.revision == revision
    assert session.instance_references() == [] and session.dispatcher.can_redo and events == []
    session.redo(); assert session.instance_references()[0]["id"] == before


def test_invalid_saved_source_reference_is_rejected_without_replacing_document(tmp_path):
    session, source_id = assembly()
    session.create_instance_reference("Preserved",source_id)
    path = tmp_path / "valid.caeprep"; session.save_project(path)
    with ZipFile(path) as archive: files = {name:archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files["manifest.json"])
    record = next(iter(manifest["model_relations"]["instances"].values()))
    record["resource_ids"] = [session._root_id]
    files["manifest.json"] = json.dumps(manifest).encode()
    bad = tmp_path / "invalid.caeprep"
    with ZipFile(bad,"w") as archive:
        for name, data in files.items(): archive.writestr(name,data)
    tokens = session.document.tokens(); document_id = session.document.id
    with pytest.raises(PrepError): session.open_project(bad)
    assert session.document.id == document_id and session.document.tokens() == tokens


def test_source_archive_v4_migrates_but_current_format_requires_relations(tmp_path):
    session, _ = assembly()
    original = tmp_path / "current.caeprep"; session.save_project(original)
    with ZipFile(original) as archive: files = {name:archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files["manifest.json"])
    assert manifest["version"] == 5
    del manifest["model_relations"]
    def archive_as(path, version):
        manifest["version"] = version
        with ZipFile(path,"w") as archive:
            for name,data in files.items():
                archive.writestr(name,json.dumps(manifest).encode() if name == "manifest.json" else data)
    legacy = tmp_path / "source-v4.caeprep"; archive_as(legacy,4)
    restored = PrepSession(); restored.open_project(legacy)
    assert restored.source_models() == session.source_models() and restored.instance_references() == []
    assert restored.describe()["element_count"] == 6 and not restored.document.dirty
    converted = tmp_path / "converted-v5.caeprep"; restored.save_project(converted)
    with ZipFile(converted) as archive:
        saved = json.loads(archive.read("manifest.json"))
    assert saved["version"] == 5 and saved["model_relations"]["instances"] == {}
    invalid = tmp_path / "missing-current-state.caeprep"; archive_as(invalid,5)
    identity, tokens = restored.document.id, restored.document.tokens()
    with pytest.raises(PrepError): restored.open_project(invalid)
    assert restored.document.id == identity and restored.document.tokens() == tokens
    manifest["model_relations"] = None
    archive_as(invalid, 5)
    with pytest.raises(PrepError): restored.open_project(invalid)
    assert restored.document.id == identity and restored.document.tokens() == tokens
