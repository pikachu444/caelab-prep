"""Persisted alternatives, independent native presence checks and fresh-process reopen."""
from copy import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_condition_workflow import _base_model, _card, _create_conditions, _i, _r


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
        assert manifest["version"] == 6 and len(manifest["analysis_cases"]["cases"]) == 2
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


@pytest.mark.parametrize(("rows", "diagnostic"), (
    ((101, 101, 205), None), ((101, 0, 205), None), ((0, 0), "invalid_reference"),
    ((101, -205), "invalid_native_id"), ((101, 99999), "dangling_reference"), ((101, 205), "ambiguous_reference"),
))
def test_imported_node_group_validation_preserves_native_rows(tmp_path, rows, diagnostic):
    source = _base_model(tmp_path / "input", newline=b"\r\n")
    block = f"/GRNOD/NODE/47\r\nUnreferenced nodes\r\n{_i(*rows)}\r\n".encode()
    source.write_bytes(source.read_bytes().replace(b"/END", block + b"/END"))
    if diagnostic == "ambiguous_reference":
        mesh = source.with_name("mesh.inc")
        mesh.write_bytes(mesh.read_bytes().replace(b"/NODE\r\n", f"/NODE\r\n{_i(205)}{_r(10, 0, 0)}\r\n".encode()))
    session = PrepSession()
    session.open_rad(source)
    group = _card(session, "/GRNOD/NODE/47")["id"]
    case = session.create_analysis_case("Imported group", [], 1, .5, "s")["case_id"]
    target = tmp_path / "out/case_0000.rad"
    if diagnostic:
        assert session.group_members(group)["diagnostics"][0]["code"] == diagnostic
        for validate in (lambda: session.validate_analysis_case(case), lambda: session.export_analysis_case(target, case)):
            with pytest.raises(PrepError) as error:
                validate()
            assert error.value.code == "invalid_reference"
            assert error.value.details["diagnostics"][0]["code"] == diagnostic
        assert not target.parent.exists()
        return
    assert session.group_members(group)["member_ids"] == [101, 205]
    session.validate_analysis_case(case)
    session.export_analysis_case(target, case)
    assert block in target.read_bytes()
    before = snapshot(session)
    for bad_ids, error_code in (([101, 101], "invalid_reference"), ([101, 0], "invalid_native_id")):
        for edit in (lambda: session.create_node_group("Strict edit", bad_ids),
                     lambda: session.set_group_members(group, bad_ids)):
            with pytest.raises(PrepError) as error:
                edit()
            assert error.value.code == error_code
    assert snapshot(session) == before


def test_case_validation_scans_raw_node_ids_once_across_many_groups(tmp_path):
    count, groups = 20_000, 96
    units = f"{'Mg':>20}{'mm':>20}{'s':>20}\n"
    starter = tmp_path / "many_0000.rad"
    starter.write_text("/BEGIN\nMany groups\n      2025         0\n" + units * 2 + "#include nodes.inc\n"
                       + "".join(f"/GRNOD/NODE/{i}\nNode {i}\n{i:10d}\n" for i in range(1, groups + 1)) + "/END\n")
    (tmp_path / "nodes.inc").write_text("/NODE\n" + "".join(_i(i) + _r(i, 0, 0) + "\n" for i in range(1, count + 1)))
    session = PrepSession()
    session.open_rad(starter)
    case = session.create_analysis_case("Warm validation", [], 1, .5, "s")["case_id"]
    session.mesh_view()
    owner = next(resource for resource in session._deck_resources() if resource.name == "nodes.inc")

    class TrackedNodeRows(list):
        reads = 0

        def __getitem__(self, index):
            if isinstance(index, int) and index > 0:
                self.reads += 1
            return super().__getitem__(index)

    owner.lines = tracked = TrackedNodeRows(owner.lines)
    session.validate_analysis_case(case)
    assert tracked.reads == count
    session.validate_analysis_case(case)
    assert tracked.reads == count

    node_card, = owner.cards
    replacement = "/NODE\n" + _i(count + 1) + _r(1, 0, 0) + "\n" + "".join(owner.lines[2:])
    session.dispatcher.execute(owner.id, owner.replaced_state(node_card.id, replacement), "Replace node IDs", kind="structure")
    with pytest.raises(PrepError) as error:
        session.validate_analysis_case(case)
    assert error.value.details["diagnostics"][0]["code"] == "dangling_reference"
    session.undo()
    session.validate_analysis_case(case)


@pytest.mark.parametrize("write", ("restore", "field"))
def test_create_node_group_reads_current_raw_ids_after_nonstructural_change(tmp_path, write):
    starter = tmp_path / "nodes_0000.rad"
    starter.write_text(f"/BEGIN\nRaw IDs\n/NODE\n{_i(101)}{_r(0, 0, 0)}\n/END\n")
    session = PrepSession()
    session.open_rad(starter)
    group = session.create_node_group("Original", [101])["card_id"]
    assert session.group_members(group)["member_ids"] == [101]
    owner = session._model_resource(None)
    card = _card(session, "/NODE")
    edit = owner.replaced_state(card["id"], f"/NODE\n{_i(9101)}{_r(0, 0, 0)}\n")
    if write == "restore":
        owner.restore(edit)
    else:
        session.dispatcher.execute(owner.id, edit, "Change native node ID")
    before = snapshot(session)
    with pytest.raises(PrepError) as error:
        session.create_node_group("Missing old ID", [101])
    assert error.value.code == "dangling_reference"
    assert snapshot(session) == before
    current = session.create_node_group("New ID", [9101])["card_id"]
    assert session.group_members(current)["member_ids"] == [9101]


@pytest.mark.parametrize("write", ("restore", "field"))
@pytest.mark.parametrize("first_reader", ("group", "projection"))
def test_nonstructural_dispatch_refreshes_node_ownership_after_renumber(tmp_path, write, first_reader):
    source = _base_model(tmp_path / "input")
    source.write_bytes(source.read_bytes().replace(b"#include mesh.inc\n", source.with_name("mesh.inc").read_bytes()))
    session = PrepSession()
    session.open_rad(source)
    group = session.create_node_group("Renumbered", [101, 205])["card_id"]
    case = session.create_analysis_case("Native renumbering", [], .01, .001, "s")["case_id"]
    initial = session.mesh_view()
    assert session.group_members(group)["member_ids"] == [101, 205]
    owner = session._model_resource(None)
    candidate = copy(owner)
    for card_id in (_card(session, "/NODE")["id"], _card(session, "/SHELL/902")["id"], group):
        before = session.card_text(card_id)
        candidate.restore(candidate.replaced_state(card_id, before.replace(_i(101), _i(9101))))
    if write == "restore":
        owner.restore(candidate.snapshot())
    else:
        session.dispatcher.execute(owner.id, candidate.snapshot(), "Renumber node and its references")

    if first_reader == "projection":
        assert 9101 in session.mesh_view()["node_resources"]
    resolved = session.group_members(group)
    assert resolved["diagnostics"] == [] and resolved["member_ids"] == [9101, 205]
    assert [item["resource_id"] for item in resolved["members"]] == [owner.id, owner.id]
    view = session.mesh_view()
    assert 101 not in view["node_resources"] and len(view["cells"]) == 2
    assert view["projection_revision"] == initial["projection_revision"] + 1
    assert session.mesh_view()["projection_revision"] == view["projection_revision"]
    target = tmp_path / "out/case_0000.rad"
    session.export_analysis_case(target, case)
    reopened = PrepSession()
    reopened.open_rad(target)
    exported_group = _card(reopened, "/GRNOD/NODE/1")["id"]
    assert reopened.group_members(exported_group)["member_ids"] == [9101, 205]


@pytest.mark.parametrize("literal", ("0_0", "1_01"))
def test_native_group_and_import_reject_integer_fields_with_underscores(tmp_path, literal):
    source = _base_model(tmp_path / "input")
    group_text = f"/GRNOD/NODE/47\nMalformed target\n{101:10d}{literal:>10}{205:10d}\n".encode()
    source.write_bytes(source.read_bytes().replace(b"/END", group_text + b"/END"))
    session = PrepSession()
    session.open_rad(source)
    group_id = _card(session, "/GRNOD/NODE/47")["id"]
    owner = session._model_resource(None)
    with pytest.raises(PrepError, match="fixed-width integer list") as error:
        session._integer_members(owner, owner.card(group_id))
    assert error.value.code == "invalid_reference"
    assert session.group_members(group_id)["diagnostics"][0]["code"] == "invalid_reference"
    case = session.create_analysis_case("Malformed group", [], .01, .001, "s")["case_id"]
    output = tmp_path / "out/case_0000.rad"
    with pytest.raises(PrepError) as error:
        session.export_analysis_case(output, case)
    assert error.value.code == "invalid_reference" and not output.parent.exists()
    destination = PrepSession()
    destination.open_rad(_base_model(tmp_path / "destination"))
    with pytest.raises(PrepError) as error:
        destination.plan_import_source(source)
    assert error.value.code == "unsupported_source_profile"


@pytest.mark.parametrize(("member", "diagnostic"), ((0, "dangling_reference"), (-201, "invalid_reference"),
                                                    (99999, "dangling_reference")))
def test_case_rejects_empty_or_unresolved_solid_group(tmp_path, member, diagnostic):
    source = _base_model(tmp_path / "input")
    group = f"/GRBRIC/BRIC/47\nUnreferenced solids\n{_i(member)}\n".encode()
    source.write_bytes(source.read_bytes().replace(b"/END", group + b"/END"))
    session = PrepSession()
    session.open_rad(source)
    case = session.create_analysis_case("Imported solids", [], 1, .5, "s")["case_id"]
    output = tmp_path / "out/case_0000.rad"
    with pytest.raises(PrepError) as error:
        session.export_analysis_case(output, case)
    assert error.value.code == "invalid_reference"
    assert error.value.details["diagnostics"][0]["code"] == diagnostic
    assert not output.parent.exists()


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
