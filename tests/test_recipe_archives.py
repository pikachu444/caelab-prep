"""Adoption-time inputs survive without their external candidate directory."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.mesh_candidates import AssetDigest
from caelab_prep.application.recipe_archives import StructuredRecipeArchive, MAX_RECIPE_BYTES
from caelab_prep.application.structured_mesh import generate_structured_mesh, read_structured_mesh_candidate
from caelab_prep.cae_core import PrepError
from test_mesh_adoption import _session


def recipe(mode="quad"):
    value = {"mode": mode, "unit": "mm", "name": "Saved input", "corners": [[0,0,0],[2,0,0],[2,1,0],[0,1,0]], "divisions": [2,1]}
    if mode == "hex": value.update(vector=[0,0,2], layers=2)
    return value


def archive_resource(*, edited=True, mode="quad"):
    original = recipe(mode)
    current = deepcopy(original); current["divisions"] = [4,2]
    files = {"recipe": json.dumps(current, indent=2).encode()}
    if edited: files["source_recipe"] = (json.dumps(original) + "\n").encode()
    metadata = {"id": str(uuid4()), "mesh_uuid": str(uuid4()), "files": [
        {"role": role, "original_path": f"C:/private/{role}.json", "sha256": sha256(raw).hexdigest()} for role, raw in files.items()]}
    return StructuredRecipeArchive(metadata, files)


@pytest.fixture(scope="module", params=["Q-N3", "H-N3"])
def archived_candidate(request, tmp_path_factory):
    pytest.importorskip("gmsh")
    path = Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json"
    case = next(item for item in json.loads(path.read_text()) if item["id"] == request.param)
    return generate_structured_mesh(case["input"], tmp_path_factory.mktemp(request.param))


def resource_states(session):
    return {key: resource.snapshot() for key, resource in session.document.resources.items()}


def test_capture_uses_the_validated_bounded_bytes(tmp_path):
    path = tmp_path / "recipe.json"; raw = json.dumps(recipe()).encode(); path.write_bytes(raw)
    asset = AssetDigest("recipe", str(path), sha256(raw).hexdigest())
    native = SimpleNamespace(mesh_uuid=str(uuid4()), assets=(asset,))
    captured = StructuredRecipeArchive.capture(native)
    assert captured.files["recipe"] == raw
    path.write_bytes(raw+b"\n")
    with pytest.raises(PrepError) as error: StructuredRecipeArchive.capture(native)
    assert error.value.code == "candidate_changed"
    with pytest.raises(PrepError): captured.restore({"state_version": 2})


def test_adoption_adds_inputs_in_one_command_before_observer_save(archived_candidate, tmp_path):
    native = archived_candidate.to_native_mesh()
    session, material, section = _session(native, native.length_unit)
    before, revision = resource_states(session), session.document.revision
    observed = []
    def save(event):
        if event["kind"] == "structure":
            observed.append(session.structured_mesh_recipes())
            session.save_project(tmp_path / "observer.caeprep")
    unsubscribe = session.subscribe(save)
    session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    unsubscribe()
    assert session.document.revision == revision + 1 and len(observed) == 1 and len(observed[0]) == 1
    archives = session.structured_mesh_recipes()
    with zipfile.ZipFile(tmp_path / "observer.caeprep") as stored:
        manifest = json.loads(stored.read("manifest.json"))
        assert manifest["version"] == 6 and manifest["structured_recipes"] == [
            {key: archives[0][key] for key in ("id", "mesh_uuid", "files")}]
    after = resource_states(session)
    session.undo(); assert resource_states(session) == before and session.structured_mesh_recipes() == []
    session.redo(); assert resource_states(session) == after
    session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    twice = session.structured_mesh_recipes()
    assert len(twice) == 2 and twice[0]["id"] != twice[1]["id"]
    assert twice[0]["mesh_uuid"] == twice[1]["mesh_uuid"] == native.mesh_uuid


def test_saved_inputs_extract_after_private_external_assets_are_removed(archived_candidate, tmp_path, monkeypatch):
    from caelab_prep.application import structured_mesh
    copied = tmp_path / "private-assets"; copied.mkdir()
    manifest = json.loads(Path(archived_candidate.manifest_path).read_text())
    for role, item in manifest["assets"].items():
        path = copied / (role + Path(item["path"]).suffix)
        path.write_bytes(Path(item["path"]).read_bytes()); item["path"] = str(path)
    metadata = copied / "metadata.json"; metadata.write_text(json.dumps(manifest))
    native = read_structured_mesh_candidate(metadata).to_native_mesh()
    exact = {asset.kind: Path(asset.path).read_bytes() for asset in native.assets if asset.kind in ("recipe", "source_recipe")}
    session, material, section = _session(native, native.length_unit)
    session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    project = tmp_path / "self-contained.caeprep"; session.save_project(project)
    for path in copied.iterdir(): path.unlink()  # Only this test's flat private copies.
    def no_sdk(*args, **kwargs): raise AssertionError("Archive loading/extraction must not run the SDK")
    monkeypatch.setattr(structured_mesh, "_child", no_sdk)
    reopened = PrepSession(); reopened.open_project(project)
    records = reopened.structured_mesh_recipes(); assert len(records) == 1
    result = reopened.export_structured_recipe(records[0]["id"], tmp_path / "extracted")
    assert {role: Path(result[role+"_path"]).read_bytes() for role in exact} == exact
    reopened.export_rad(tmp_path / "still-native.rad")
    before = {path.name: path.read_bytes() for path in (tmp_path / "extracted").iterdir()}
    with pytest.raises(PrepError): reopened.export_structured_recipe(records[0]["id"], tmp_path / "extracted")
    assert {path.name: path.read_bytes() for path in (tmp_path / "extracted").iterdir()} == before


def test_archive_restore_failure_rolls_back_the_entire_adoption(archived_candidate, monkeypatch):
    native = archived_candidate.to_native_mesh()
    session, material, section = _session(native, native.length_unit)
    before, revision, paths = resource_states(session), session.document.revision, set(session._source_paths)
    attempted = []
    restore = StructuredRecipeArchive.restore
    def fail(self, state):
        if not attempted:
            attempted.append(len(session.document.resources[session._root_id].mesh_projection()["cells"]))
            raise RuntimeError("archive restore failed after root restore")
        return restore(self, state)
    monkeypatch.setattr(StructuredRecipeArchive, "restore", fail)
    with pytest.raises(RuntimeError, match="archive restore failed"):
        session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert attempted == [len(native.elements)]
    assert resource_states(session) == before and session.structured_mesh_recipes() == []
    assert session.document.revision == revision and session._source_paths == paths


@pytest.mark.parametrize("damage", ["registry", "duplicate", "collision", "missing", "digest", "oversize", "json", "edit"])
def test_bad_archive_cannot_replace_the_open_document(tmp_path, damage, monkeypatch):
    session = PrepSession(); session.new_document("Working", {"mass":"Mg", "length":"mm", "time":"s"})
    archive = archive_resource()
    session.dispatcher.execute_many({}, "Attach test input", additions=(archive,))
    source = tmp_path / "source.caeprep"; session.save_project(source)
    with zipfile.ZipFile(source) as stored:
        members = {name: stored.read(name) for name in stored.namelist()}
    manifest = json.loads(members.pop("manifest.json")); record = manifest["structured_recipes"][0]
    member = f"recipes/{archive.id}/recipe.json"
    if damage == "registry": manifest["structured_recipes"] = {}
    elif damage == "duplicate": record["files"] = [record["files"][0]] * 2
    elif damage == "collision":
        record["id"] = session._root_id
        for role in archive.files: members[f"recipes/{record['id']}/{role}.json"] = members[f"recipes/{archive.id}/{role}.json"]
    elif damage == "missing": members.pop(member)
    elif damage == "digest": record["files"][0]["sha256"] = "0" * 64
    else:
        value = deepcopy(recipe())
        if damage == "edit": value["unit"] = "cm"
        raw = b" " * (MAX_RECIPE_BYTES + 1) if damage == "oversize" else b'{"mode":NaN}' if damage == "json" else json.dumps(value).encode()
        members[member] = raw; record["files"][0]["sha256"] = sha256(raw).hexdigest()
    broken = tmp_path / "bad.caeprep"
    with zipfile.ZipFile(broken, "w", compression=zipfile.ZIP_DEFLATED) as stored:
        stored.writestr("manifest.json", json.dumps(manifest))
        for name, raw in members.items(): stored.writestr(name, raw)
    read = zipfile.ZipFile.read
    def bounded(self, name, *args, **kwargs):
        assert damage != "oversize" or name != member, "Oversized recipe was read before its limit check"
        return read(self, name, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "read", bounded)
    before, identity, revision = resource_states(session), session.document.id, session.document.revision
    with pytest.raises(PrepError): session.open_project(broken)
    assert resource_states(session) == before and session.document.id == identity and session.document.revision == revision


def test_legacy_document_has_no_recipe_registry(tmp_path):
    session = PrepSession(); session.new_document("Legacy", {"mass":"Mg", "length":"mm", "time":"s"})
    path = tmp_path / "legacy.caeprep"; session.save_project(path)
    with zipfile.ZipFile(path) as stored: members = {name:stored.read(name) for name in stored.namelist()}
    manifest=json.loads(members["manifest.json"]);manifest.pop("structured_recipes")
    with zipfile.ZipFile(path,"w") as stored:
        stored.writestr("manifest.json",json.dumps(manifest))
        for name,raw in members.items():
            if name!="manifest.json":stored.writestr(name,raw)
    session.open_project(path); assert session.structured_mesh_recipes() == []
