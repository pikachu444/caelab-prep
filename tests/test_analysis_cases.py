"""Persisted alternatives, independent native presence checks and fresh-process reopen."""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_condition_workflow import _base_model, _create_conditions


@pytest.fixture
def model(tmp_path):
    source = _base_model(tmp_path / "input", newline=b"\r\n")
    session = PrepSession(); session.open_rad(str(source))
    refs = _create_conditions(session)
    return session, refs, source


def create(session, refs, name="Load case", **changes):
    values = dict(name=name, condition_ids=[refs["bcs"], refs["load"], refs["contact"]],
                  end_time=2, output_interval=.25, time_unit="ms")
    values.update(changes)
    return session.create_analysis_case(**values)["case_id"]


def snapshot(session):
    return session.document.tokens(), session.document.revision, session.document.dirty


def test_two_cases_undo_save_fresh_process_and_independent_exports(model, tmp_path):
    session, refs, source = model
    first = create(session, refs)
    second = create(session, refs, "Velocity case", condition_ids=[refs["bcs"], refs["velocity"], refs["contact"]], end_time=4)
    session.select_analysis_case(first)
    assert session.analysis_case()["id"] == first
    revision = session.document.revision
    session.set_analysis_case(second, {"end_time": 3, "output_interval": .5})
    assert session.document.revision == revision + 1
    session.undo(); assert session.analysis_case(second)["end_time"] == 4
    session.redo(); assert session.analysis_case(second)["end_time"] == 3
    native_before = {card["id"]: session.card_text(card["id"]) for card in session.list_cards()}
    project = tmp_path / "cases.prep"
    session.save_project(str(project)); assert not session.document.dirty
    with zipfile.ZipFile(project) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["version"] == 3 and len(manifest["analysis_cases"]["cases"]) == 2
    code = ("from caelab_prep.application import PrepSession; import json,sys; "
            "s=PrepSession();s.open_project(sys.argv[1]);print(json.dumps(s.analysis_cases()));"
            "s.export_analysis_case(sys.argv[2]);s.export_analysis_case(sys.argv[3],sys.argv[4])")
    a = tmp_path / "a" / "load_0000.rad"; b = tmp_path / "b" / "velocity_0000.rad"
    result = subprocess.run([sys.executable, "-c", code, str(project), str(a), str(b), second], check=True, capture_output=True, text=True)
    reopened = json.loads(result.stdout)
    assert reopened["active_case_id"] == first and [c["id"] for c in reopened["cases"]] == [first, second]
    assert b"/CLOAD/81\r\n" in a.read_bytes() and b"/INIVEL/TRA/89" not in a.read_bytes()
    assert b"/CLOAD/81" not in b.read_bytes() and b"/INIVEL/TRA/89\r\n" in b.read_bytes()
    assert (a.parent / "mesh.inc").read_bytes() == (source.parent / "mesh.inc").read_bytes()
    assert "\n0.002\n/ANIM/DT\n0 0.00025\n" in a.with_name("load_0001.rad").read_text()
    assert "\n0.003\n/ANIM/DT\n0 0.0005\n" in b.with_name("velocity_0001.rad").read_text()
    assert native_before == {card["id"]: session.card_text(card["id"]) for card in session.list_cards()}
    assert not session.document.dirty


def test_empty_activation_and_selection_copy_delete_are_explicit(model):
    session, refs, _ = model
    case = create(session, refs, condition_ids=[])
    assert len(session.validate_analysis_case(case)["inactive_condition_ids"]) == 4
    copied = session.copy_analysis_case(case)["case_id"]
    assert copied != case and session.analysis_case(copied)["condition_ids"] == []
    session.delete_analysis_case(copied)
    assert session.analysis_cases()["active_case_id"] is None
    with pytest.raises(PrepError, match="Choose an existing"): session.analysis_case()
    session.undo(); assert session.analysis_case()["id"] == copied
    session.select_analysis_case(None)
    assert session.analysis_cases()["active_case_id"] is None
    session.undo(); assert session.analysis_case()["id"] == copied


@pytest.mark.parametrize("values", [
    {"name": ""}, {"name": "bad\nname"}, {"condition_ids": None}, {"condition_ids": ["99"]},
    {"end_time": 0}, {"end_time": True}, {"end_time": float("nan")}, {"end_time": 10**400}, {"output_interval": 3},
    {"time_unit": "unknown"}, {"time_unit": {}}, {"unrecognised": 12},
])
def test_invalid_case_batch_is_atomic(model, values):
    session, refs, _ = model
    case = create(session, refs)
    before = snapshot(session)
    with pytest.raises(PrepError): session.set_analysis_case(case, {"name": "Changed", **values})
    assert snapshot(session) == before


def test_reference_name_staleness_and_deletion_guards(model):
    session, refs, _ = model
    first = create(session, refs)
    before = snapshot(session)
    for values in ({"condition_ids": [refs["curve"]]}, {"condition_ids": [refs["load"], refs["load"]]}):
        with pytest.raises(PrepError): session.set_analysis_case(first, values)
    with pytest.raises(PrepError): create(session, refs, name=" load CASE ")
    with pytest.raises(PrepError): session.set_analysis_case(first, {"name": "A"}, expected_revision=session.document.revision-1)
    with pytest.raises(PrepError): session.select_analysis_case(first, expected_document_id="wrong")
    with pytest.raises(PrepError) as error: session.delete_card(refs["load"])
    assert error.value.code == "card_in_use" and error.value.details["analysis_cases"][0]["id"] == first
    assert snapshot(session) == before


def test_export_revision_guard_rejects_before_any_file(model, tmp_path):
    session, refs, _ = model
    case = create(session, refs)
    revision = session.document.revision
    session.set_analysis_case(case, {"end_time": 3})
    output = tmp_path / "out" / "case_0000.rad"
    with pytest.raises(PrepError) as error:
        session.export_analysis_case(str(output), case, expected_revision=revision,
                                     expected_document_id=session.document.id)
    assert error.value.code == "revision_conflict" and not output.exists()


def test_inactive_condition_before_include_keeps_directive(tmp_path):
    source = _base_model(tmp_path / "input")
    original = source.read_bytes()
    # A native condition followed directly by an INCLUDE is one parser block.
    source.write_bytes(original.replace(b"#include mesh.inc", b"/BCS/71\nSupport\n   111 000         0        47\n#include mesh.inc"))
    session = PrepSession(); session.open_rad(str(source))
    case = session.create_analysis_case("Unconstrained", [], .001, .0005, "s")["case_id"]
    target = tmp_path / "out" / "case_0000.rad"
    session.export_analysis_case(str(target), case)
    assert b"#include mesh.inc" in target.read_bytes() and b"/BCS/71" not in target.read_bytes()
    assert (target.parent / "mesh.inc").exists()


def test_opaque_physics_blocks_case_output_but_preserves_document(tmp_path):
    source = _base_model(tmp_path / "input")
    source.write_bytes(source.read_bytes().replace(b"/END", b"/GRAV/72\nOpaque gravity\n123\n/END"))
    session = PrepSession(); session.open_rad(str(source))
    case = session.create_analysis_case("No supported conditions", [], 1, .5, "s")["case_id"]
    before = snapshot(session)
    target = tmp_path / "out" / "case_0000.rad"
    with pytest.raises(PrepError) as error: session.export_analysis_case(str(target), case)
    assert error.value.code == "case_activation_scope_unknown"
    assert error.value.details["cards"][0]["keyword"] == "/GRAV/72"
    assert not target.exists() and snapshot(session) == before


def test_engine_time_uses_working_not_input_units(model, tmp_path):
    session, refs, source = model
    # Reopen edited native source with input seconds, working milliseconds.
    raw = source.read_bytes(); row = f"{'Mg':>20}{'mm':>20}{'s':>20}".encode()
    index = raw.index(row) + len(row)
    raw = raw[:index] + raw[index:].replace(row, f"{'Mg':>20}{'mm':>20}{'ms':>20}".encode(), 1)
    alternate = source.parent / "work_0000.rad"; alternate.write_bytes(raw)
    session.open_rad(str(alternate))
    case = session.create_analysis_case("Seconds input", [], .002, .0005, "s")["case_id"]
    result = session.export_analysis_case(str(tmp_path / "out" / "case_0000.rad"), case)
    assert result["units"]["time"] == "ms" and result["end_time"] == 2
    assert "\n2.0\n/ANIM/DT\n0 0.5\n" in Path(result["engine_path"]).read_text()


def test_legacy_project_reopens_without_inventing_cases_and_bad_refs_do_not_replace_live(model, tmp_path):
    session, refs, _ = model
    create(session, refs)
    path = tmp_path / "original.prep"; session.save_project(str(path))
    with zipfile.ZipFile(path) as archive: members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    def emit(name, manifest):
        target = tmp_path / name
        with zipfile.ZipFile(target, "w") as archive:
            for key, value in members.items(): archive.writestr(key, json.dumps(manifest) if key == "manifest.json" else value)
        return target
    broken = json.loads(json.dumps(manifest))
    broken["analysis_cases"]["cases"][0]["condition_ids"] = [refs["curve"]]
    before = snapshot(session)
    with pytest.raises(PrepError): session.open_project(str(emit("broken.prep", broken)))
    assert snapshot(session) == before
    manifest["version"] = 2; manifest.pop("analysis_cases")
    session.open_project(str(emit("legacy.prep", manifest)))
    assert session.analysis_cases()["cases"] == [] and not session.document.dirty
