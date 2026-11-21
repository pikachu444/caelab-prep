"""Independent IDs, original bytes and atomic native/case relationships."""
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from uuid import uuid4
import zipfile

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.radioss.modeling import material_block, shell_block, solid_block
from test_condition_workflow import _base_model, _card, _i


def model(folder, *, offset=0):
    folder.mkdir()
    starter = folder / "same_0000.rad"
    starter.write_bytes(("/BEGIN\nSame name\n      2024         0\n" + f"{'Mg':>20}{'mm':>20}{'s':>20}\n" * 2
        + material_block(41, "Same steel", 7.8e-9, 210000, .3) + shell_block(21, "Same shell", 1)
        + "/PART/9\nSame part\n" + f"{21:10}{41:10}{0:10}\n#include mesh.inc\n/END\n").encode())
    nodes = [(1, 0 + offset, 0), (2, 10 + offset, 0), (3, 10 + offset, 10), (4, 0 + offset, 10)]
    (folder / "mesh.inc").write_bytes(("# untouched source comment  \n/NODE\n" + "".join(f"{i:10}{x:20g}{y:20g}{0:20g}\n" for i, x, y in nodes)
        + "/SHELL/9\n" + "".join(f"{i:10}" for i in (77, 1, 2, 3, 4)) + "\n#enddata\n# trailing bytes  \n").encode())
    return starter


def test_sources_with_same_ids_remain_independent_and_archive_survives_fresh_process(tmp_path):
    first, second = model(tmp_path / "first"), model(tmp_path / "second")
    original = {path.name: path.read_bytes() for path in second.parent.iterdir()}
    session = PrepSession(); session.open_rad(first)
    events = []; session.subscribe(events.append)
    plan = session.plan_import_source(second)
    assert session.document.revision == 0 and not session.document.dirty and events == []
    assert {tuple(item) for item in plan["collisions"]} >= {("NODE", 1), ("MAT", 41), ("PART", 9), ("E:SHELL", 77)}
    result = session.import_source(plan["plan_id"])
    assert session.describe()["node_count"] == 8 and session.describe()["element_count"] == 2
    assert session.document.revision == 1 and len(events) == 1
    view = session.mesh_view()
    assert view["points"][:4] == view["points"][4:]  # Same geometry does not imply shared identity.
    source_id = result["source_model_id"]
    archive = session.document.resources[source_id]
    for item in archive.metadata["files"]:
        assert archive.files[item["original_resource_id"]] == original[item["original_path"]]
    snapshot = session.source_models()
    project = tmp_path / "assembly.caeprep"; session.save_project(project)
    script = "from caelab_prep.application import PrepSession; import json,sys; s=PrepSession(); s.open_project(sys.argv[1]); print(json.dumps({'sources':s.source_models(),'count':s.describe()['node_count']}))"
    reopened = json.loads(subprocess.check_output([sys.executable, "-c", script, str(project)], text=True))
    assert reopened == {"sources": snapshot, "count": 8}
    output = tmp_path / "export" / "assembly_0000.rad"; session.export_rad(output)
    check = PrepSession(); check.open_rad(output)
    assert check.describe()["node_count"] == 8 and check.describe()["element_count"] == 2
    assert not any(item["code"].startswith("duplicate") for item in check.diagnostics())
    session.undo()
    assert session.source_models() == [] and session.describe()["node_count"] == 4
    session.redo()
    assert session.source_models() == snapshot and session.document.resources[source_id] is archive


def test_explicit_shared_node_is_single_entity_and_unmapped_nodes_stay_distinct(tmp_path):
    first, second = model(tmp_path / "first"), model(tmp_path / "second")
    session = PrepSession(); session.open_rad(first)
    reference = session.select_entity("node", 1)["refs"][0]
    plan = session.plan_import_source(second, shared_node_map={1: reference})
    session.import_source(plan["plan_id"])
    cells = session.mesh_view()["cells"]
    assert set(cells[0]["nodes"]) & set(cells[1]["nodes"]) == {1}
    assert session.describe()["node_count"] == 7
    session.undo()
    shifted = model(tmp_path / "shifted", offset=1)
    with pytest.raises(PrepError, match="identical coordinates"):
        session.plan_import_source(shifted, shared_node_map={1: reference})
    assert session.describe()["node_count"] == 4


@pytest.mark.parametrize("variant", ("title-only-deleted", "all-zero-deleted", "underscore-retained", "underscore-corrected",
                                     "underscore-deleted", "underscore-node", "underscore-connectivity",
                                     "padded-with-title-only", "hybrid", "pass14-padded", "pass14-underscore-zero",
                                     "pass14-new-underscore-zero", "pass14-recreated-padding-card",
                                     "older-unquoted-padded", "older-quoted-padded", "pre-v5-explicit",
                                     "v5-host-v4-archive-explicit", "mixed-archive-unrecorded"))
def test_reopen_source_archive_with_legacy_node_group(tmp_path, variant):
    source = _base_model(tmp_path / "source")
    padded = variant in ("padded-with-title-only", "hybrid", "pass14-padded", "pass14-underscore-zero", "pass14-new-underscore-zero",
                         "pass14-recreated-padding-card", "older-unquoted-padded", "older-quoted-padded")
    empty = variant in ("padded-with-title-only", "hybrid", "title-only-deleted", "all-zero-deleted")
    identifiers = (101, 205) if empty or padded else (101, 101, 205)
    native_row = f"{_i(*identifiers)}\n".encode()
    groups = b"/GRNOD/NODE/47\nUnused target\n" + native_row
    if padded:
        groups += f"/GRNOD/NODE/48\nPadded target\n{_i(101, 0, 205)}\n".encode()
    if variant == "pass14-underscore-zero":
        groups += f"/BCS/71\nArchived fixity\n   100 000{_i(0, 48)}\n".encode()
    raw = source.read_bytes().replace(b"/END", groups + b"/END")
    if padded:
        raw = raw.replace(b"#include mesh.inc\n", b'#include\n"mesh.inc"\n')
    source.write_bytes(raw)
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "base"))
    plan = session.plan_import_source(source)
    ids = {(namespace, original): mapped for namespace, original, mapped in plan["source"]["id_map"]}
    session.import_source(plan["plan_id"])
    group_keyword = f'/GRNOD/NODE/{ids["GRNOD", 47]}'
    group = _card(session, group_keyword)["id"]
    expected = (ids["NODE", 101], ids["NODE", 205])
    if empty or variant.endswith("deleted"):
        session.delete_card(group)
    elif variant.endswith("corrected"):
        resource = session._find_card(group)
        corrected = f"{group_keyword}\nUnused target\n{_i(*expected)}\n"
        state = resource.replaced_state(group, corrected)
        session.dispatcher.execute(resource.id, state, "Normalize mapped group row", kind="structure")
    active_conditions = [_card(session, f'/BCS/{ids["BCS", 71]}')["id"]] if variant == "pass14-underscore-zero" else []
    case = session.create_analysis_case("Archive case", active_conditions, .01, .001, "s")["case_id"]
    saved = tmp_path / "saved.caeprep"
    session.save_project(saved)
    with zipfile.ZipFile(saved) as archive:
        payloads = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(payloads["manifest.json"])
    source_model, = manifest["source_models"]
    file = next(item for item in source_model["files"] if item["original_path"] == source.name)
    original_member = f'sources/{source_model["id"]}/{file["original_resource_id"]}.rad'
    mapped_member = next(item["raw_member"] for item in manifest["resources"] if item["id"] == file["resource_id"])
    # Reproduce the older writers' immutable originals and corresponding remaps.
    assert payloads[original_member].count(native_row) == 1
    if empty:
        legacy_row = f"{_i(0, 0)}\n".encode() if variant == "all-zero-deleted" else b""
    elif padded:
        legacy_row = native_row
    else:
        legacy_row = f"{101:10d}{'1_01':>10}{205:10d}\n".encode()
    payloads[original_member] = payloads[original_member].replace(native_row, legacy_row)
    file["sha256"] = sha256(payloads[original_member]).hexdigest()
    if empty:
        translated_row = f'{_i(*expected)}\n'.encode()
        assert payloads[mapped_member].count(translated_row) == 1
        payloads[mapped_member] = payloads[mapped_member].replace(translated_row, legacy_row)
    if variant in ("underscore-node", "underscore-connectivity", "hybrid", "pass14-padded", "pass14-new-underscore-zero"):
        mesh_file = next(item for item in source_model["files"] if item["original_path"] == "mesh.inc")
        mesh_member = f'sources/{source_model["id"]}/{mesh_file["original_resource_id"]}.rad'
        prefix = _i(7001).encode() if variant == "underscore-connectivity" else b""
        old = b"\n" + prefix + _i(101).encode()
        assert payloads[mesh_member].count(old) == 1
        changed = payloads[mesh_member].replace(old, b"\n" + prefix + f"{'1_01':>10}".encode())
        payloads[mesh_member] = changed
        mesh_file["sha256"] = sha256(changed).hexdigest()
        source.with_name("mesh.inc").write_bytes(changed)
        with pytest.raises(PrepError) as error:
            session.plan_import_source(source)
        assert error.value.code == "unsupported_source_profile"
    if variant in ("pass14-underscore-zero", "pass14-recreated-padding-card"):
        for member, first, last in ((original_member, 101, 205), (mapped_member, *expected)):
            numeric_row = f"{_i(first, 0, last)}\n".encode()
            assert payloads[member].count(numeric_row) == 1
            payloads[member] = payloads[member].replace(numeric_row, f"{first:10d}{'0_0':>10}{last:10d}\n".encode())
        file["sha256"] = sha256(payloads[original_member]).hexdigest()
        source.write_bytes(payloads[original_member])
        with pytest.raises(PrepError) as error:
            session.plan_import_source(source)
        assert error.value.code == "unsupported_source_profile"
    if variant.startswith("older-"):
        source_model.pop("include_bindings")
        manifest.pop("include_bindings")
    if variant == "older-unquoted-padded":
        mapped_mesh = next(item["logical_path"].encode() for item in source_model["files"]
                           if item["original_path"] == "mesh.inc")
        quoted = b'"' + mapped_mesh + b'"'
        assert payloads[mapped_member].count(quoted) == 1
        payloads[mapped_member] = payloads[mapped_member].replace(quoted, mapped_mesh)
    if variant in ("pre-v5-explicit", "v5-host-v4-archive-explicit", "mixed-archive-unrecorded"):
        archived_ids = {item["resource_id"] for item in source_model["files"]}
        if variant == "mixed-archive-unrecorded":
            source_model.pop("include_bindings")
            archived_ids = {source_model["root_resource_id"]}
        for resource in manifest["resources"]:
            if variant == "pre-v5-explicit" or resource["id"] in archived_ids:
                resource["state"]["state_version"] = 4
                assert not resource["state"].pop("retained_comments")
    payloads["manifest.json"] = json.dumps(manifest).encode()
    legacy = tmp_path / "pass13.caeprep"
    with zipfile.ZipFile(legacy, "w") as archive:
        for name, raw in payloads.items():
            archive.writestr(name, raw)

    if variant == "all-zero-deleted":
        with pytest.raises(PrepError, match="positive node ID") as error:
            session.open_project(legacy)
        assert error.value.code == "unsupported_source_profile"
        return
    if variant == "hybrid":
        with pytest.raises(PrepError) as error:
            session.open_project(legacy)
        assert error.value.code == "unsupported_source_profile"
        return
    if variant.startswith("older-"):
        with pytest.raises(PrepError) as error:
            session.open_project(legacy)
        assert error.value.code == "unsupported_source_profile"
        return
    if variant in ("pre-v5-explicit", "v5-host-v4-archive-explicit"):
        with pytest.raises(PrepError, match="cannot carry explicit source INCLUDE bindings") as error:
            session.open_project(legacy)
        assert error.value.code == "invalid_project"
        return
    if variant == "mixed-archive-unrecorded":
        with pytest.raises(PrepError, match="cannot mix v4 and v5 state versions") as error:
            session.open_project(legacy)
        assert error.value.code == "invalid_project"
        return
    session.open_project(legacy)
    if variant == "pass14-recreated-padding-card":
        original_group = _card(session, "/GRNOD/NODE/48")["id"]
        owner = session._find_card(original_group)
        original_text = session.card_text(original_group)
        session.delete_card(original_group)
        added = session.create_node_group("Replacement group", list(expected), native_id=48, resource_id=owner.id)["card_id"]
        assert added != original_group
        state = owner.replaced_state(added, original_text)
        session.dispatcher.execute(owner.id, state, "Copy the old padding to a new card", kind="structure")
        saved = tmp_path / "recreated-group.caeprep"
        session.save_project(saved)
        session.open_project(saved)
        assert [item["code"] for item in session.group_members(added)["diagnostics"]] == ["invalid_reference"]
        with pytest.raises(PrepError) as error:
            session.export_analysis_case(tmp_path / "reject/case_0000.rad", case)
        assert error.value.code == "invalid_reference"
        return
    if variant == "pass14-new-underscore-zero":
        owner = session._find_card(group)
        assert b"0_0" not in owner.render()
        added = session.create_node_group("New padding", list(expected), native_id=50, resource_id=owner.id)["card_id"]
        assert owner.card(added).keyword == "/GRNOD/NODE/50"
        line = f"{expected[0]:10d}{'0_0':>10}{expected[1]:10d}"
        state = owner.replaced_state(added, f"/GRNOD/NODE/50\nNew padding\n{line}\n")
        session.dispatcher.execute(owner.id, state, "Insert unarchived zero padding", kind="structure")
        changed = tmp_path / "new-padding.caeprep"
        session.save_project(changed)
        session.open_project(changed)
        assert [item["code"] for item in session.group_members(added)["diagnostics"]] == ["invalid_reference"]
        with pytest.raises(PrepError) as error:
            session.export_analysis_case(tmp_path / "reject/case_0000.rad", case)
        assert error.value.code == "invalid_reference"
        return
    view = session.mesh_view()
    assert len(view["node_ids"]) == 16 and len(view["cells"]) == 4
    if empty or variant.endswith("deleted"):
        assert not any(card["keyword"] == group_keyword for card in session.list_cards())
    else:
        assert session.group_members(group)["member_ids"] == list(expected)
        native_members = expected if padded or variant.endswith("corrected") else (expected[0], *expected)
        assert session.card_text(group).splitlines()[-1] == _i(*native_members)
    if variant == "pass14-underscore-zero":
        padded_group = _card(session, f'/GRNOD/NODE/{ids["GRNOD", 48]}')["id"]
        assert session.group_members(padded_group)["member_ids"] == list(expected)
        original_group = session.card_text(padded_group)
    target = tmp_path / "export/case_0000.rad"
    session.export_analysis_case(target, case)
    assert all(b"1_01" not in path.read_bytes() for path in target.parent.rglob("*") if path.is_file())
    if variant == "pass14-underscore-zero":
        assert session.card_text(padded_group) == original_group and "0_0" in original_group
        session.export_rad(tmp_path / "starter/starter_0000.rad")
        starter_check = PrepSession()
        starter_check.open_rad(tmp_path / "starter/starter_0000.rad")
        starter_group = _card(starter_check, f'/GRNOD/NODE/{ids["GRNOD", 48]}')["id"]
        assert starter_check.group_members(starter_group)["member_ids"] == list(expected)
        owner = session._find_card(padded_group)
        updated_members = (expected[0], ids["NODE", 309])
        amended = f"{updated_members[0]:10d}{'0_0':>10}{updated_members[1]:10d}"
        state = owner.replaced_state(padded_group, original_group.replace(original_group.splitlines()[-1], amended))
        session.dispatcher.execute(owner.id, state, "Edit beside the archived padding slot", kind="structure")
        assert session.group_members(padded_group)["member_ids"] == list(updated_members)
        saved = tmp_path / "amended-project.caeprep"
        session.save_project(saved)
        session.open_project(saved)
        updated = tmp_path / "amended/case_0000.rad"
        session.export_analysis_case(updated, case)
        check = PrepSession()
        check.open_rad(updated)
        edited_group = _card(check, "/GRNOD/NODE/48")["id"]
        assert check.group_members(edited_group)["member_ids"] == list(updated_members)
        assert check.card_text(edited_group).splitlines()[-1] == _i(updated_members[0], 0, updated_members[1])
        owner = session._find_card(padded_group)
        shifted = f"{'0_0':>10}{updated_members[0]:10d}{updated_members[1]:10d}"
        state = owner.replaced_state(padded_group, original_group.replace(original_group.splitlines()[-1], shifted))
        session.dispatcher.execute(owner.id, state, "Move the archived padding token to a different slot", kind="structure")
        assert [item["code"] for item in session.group_members(padded_group)["diagnostics"]] == ["invalid_reference"]
        host = session._model_resource(None)
        text = f"/GRNOD/NODE/97\nUnrelated host padding\n{101:10d}{'0_0':>10}{205:10d}\n"
        state, card_id = host.inserted_state(text)
        session.dispatcher.execute(host.id, state, "Add malformed group outside the archive", kind="structure")
        assert session.group_members(card_id)["diagnostics"][0]["code"] == "invalid_reference"
    session.open_rad(target)
    assert len(session.mesh_view()["node_ids"]) == 16 and len(session.mesh_view()["cells"]) == 4
    if padded:
        padded_keyword = f'/GRNOD/NODE/{ids["GRNOD", 48]}'
        padded_group = _card(session, padded_keyword)["id"]
        members = session.group_members(padded_group)
        assert members["member_ids"] == list(expected) and not members["diagnostics"]
        assert session.card_text(padded_group).splitlines()[-1] == _i(expected[0], 0, expected[1])
        if variant == "pass14-underscore-zero":
            condition = _card(session, f'/BCS/{ids["BCS", 71]}')["id"]
            reexport_case = session.create_analysis_case("Re-export", [condition], .01, .001, "s")["case_id"]
            session.export_analysis_case(tmp_path / "reexport/case_0000.rad", reexport_case)
    elif not variant.endswith("deleted"):
        assert session.group_members(_card(session, group_keyword)["id"])["member_ids"] == list(expected)


@pytest.mark.parametrize("variant", ("legacy-map", "legacy-shell-group", "tampered-with-bindings",
                                    "forged-241-quad", "forged-987-quad", "forged-241-sh4n", "forged-987-sh4n",
                                    "forged-241-tetra", "forged-987-tetra"))
def test_legacy_quad_source_archive_recovers_the_native_solid_group(tmp_path, variant):
    starter, source = model(tmp_path / "base"), model(tmp_path / "source", offset=20)
    mesh = source.with_name("mesh.inc")
    family, namespace = {
        "sh4n": (b"/SH4N/9", "E:SHELL"), "tetra": (b"/TETRA/9", "E:SOLID"),
    }.get(variant.rsplit("-", 1)[-1], (b"/QUAD/9", "E:QUAD"))
    mesh.write_bytes(mesh.read_bytes().replace(b"/SHELL/9", family))
    if variant.startswith("forged-987-"):
        source.write_bytes(source.read_bytes().replace(b"#include mesh.inc", b'#include\n"mesh.inc"'))
    if variant == "legacy-shell-group":
        source.write_bytes(source.read_bytes().replace(
            b"/END", f"/GRQUAD/QUAD/48\nArchived solid group\n{_i(77)}\n/END".encode()))
    session = PrepSession()
    session.open_rad(starter)
    plan = session.plan_import_source(source)
    session.import_source(plan["plan_id"])
    identifier = next(mapped for ns, original, mapped in plan["source"]["id_map"] if (ns, original) == (namespace, 77))
    project = tmp_path / "modern.caeprep"
    session.save_project(project)
    with zipfile.ZipFile(project) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    source_model, = manifest["source_models"]
    if variant != "tampered-with-bindings":
        source_model.pop("include_bindings")
    entries = source_model["id_map"]
    if namespace == "E:QUAD":
        entries[entries.index([namespace, 77, identifier])][0] = "E:SHELL"
    if variant.startswith("forged-241-"):
        archived_ids = {item["resource_id"] for item in source_model["files"]}
        for deck in manifest["resources"]:
            if deck["id"] in archived_ids:
                deck["state"]["state_version"] = 4
                assert not deck["state"].pop("retained_comments")
    if variant.startswith("forged-987-"):
        mapped_mesh = next(item["logical_path"].encode() for item in source_model["files"]
                           if item["original_path"] == "mesh.inc")
        member = next(item["raw_member"] for item in manifest["resources"]
                      if item["id"] == source_model["root_resource_id"])
        quoted = b'"' + mapped_mesh + b'"'
        assert members[member].count(quoted) == 1
        members[member] = members[member].replace(quoted, mapped_mesh)
    if variant == "legacy-shell-group":
        entry = next(entry for entry in entries if entry[:2] == ["GRQUAD", 48])
        entry[0] = "GRSHEL"
        file = next(item for item in source_model["files"] if item["original_path"] == source.name)
        original = f'sources/{source_model["id"]}/{file["original_resource_id"]}.rad'
        mapped = next(item["raw_member"] for item in manifest["resources"] if item["id"] == file["resource_id"])
        for member in (original, mapped):
            assert members[member].count(b"/GRQUAD/QUAD/") == 1
            members[member] = members[member].replace(b"/GRQUAD/QUAD/", b"/GRSHEL/SHEL/")
        file["sha256"] = sha256(members[original]).hexdigest()
    members["manifest.json"] = json.dumps(manifest).encode()
    legacy = tmp_path / "legacy.caeprep"
    with zipfile.ZipFile(legacy, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)

    if variant == "tampered-with-bindings":
        with pytest.raises(PrepError) as error:
            session.open_project(legacy)
        assert error.value.code == "invalid_project"
        return
    if variant.startswith("forged-"):
        with pytest.raises(PrepError) as error:
            session.open_project(legacy)
        assert error.value.code in {"invalid_project", "unsupported_source_profile"}
        return
    session.open_project(legacy)
    ref = session.resolve_entity_reference("element", identifier)["reference"]
    group = session.create_element_group("Imported 2D solid", [ref])["card_id"]
    assert session.group_members(group)["members"] == [ref]
    assert session.card_text(group).startswith("/GRQUAD/QUAD/")


@pytest.mark.parametrize("tampered", (False, True))
def test_ac0_qualified_include_requires_its_shell_namespace_for_quad(tmp_path, tampered):
    source = model(tmp_path / "source", offset=20)
    root = source.parent
    bank = root / "bank"
    bank.mkdir()
    original_mesh = root / "mesh.inc"
    original_mesh.rename(bank / "mesh.inc")
    mesh = bank / "mesh.inc"
    mesh.write_bytes(mesh.read_bytes().replace(b"/SHELL/9", b"/QUAD/9"))
    (root / "nested/bank").mkdir(parents=True)
    (root / "nested/bank/mesh.inc").write_bytes(b"# Additional source\n")
    (root / "nested/bank/entry.inc").write_bytes(b"#include mesh.inc\n")
    (root / "nested/first.inc").write_bytes(b"#include bank/mesh.inc\n")
    source.write_bytes(source.read_bytes().replace(b"#include mesh.inc", b"#include bank/mesh.inc\n"
                                                    b"#include nested/first.inc\n#include nested/bank/entry.inc"))
    session = PrepSession()
    session.open_rad(model(tmp_path / "base"))
    session.import_source(session.plan_import_source(source)["plan_id"])
    saved = tmp_path / "modern.caeprep"
    session.save_project(saved)
    with zipfile.ZipFile(saved) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    source_model, = manifest["source_models"]
    source_model.pop("include_bindings")
    manifest.pop("include_bindings")
    files = {file["original_path"]: file for file in source_model["files"]}
    first = next(item["raw_member"] for item in manifest["resources"]
                 if item["id"] == files["nested/first.inc"]["resource_id"])
    # ac0a255 resolves the qualified operand to the import root. Later writers
    # bind this particular operand to the sibling, which entry.inc also reaches.
    assert files["nested/bank/mesh.inc"]["logical_path"].encode() in members[first]
    members[first] = members[first].replace(files["nested/bank/mesh.inc"]["logical_path"].encode(),
                                             files["bank/mesh.inc"]["logical_path"].encode())
    if not tampered:
        next(entry for entry in source_model["id_map"] if entry[:2] == ["E:QUAD", 77])[0] = "E:SHELL"
    members["manifest.json"] = json.dumps(manifest).encode()
    historical = tmp_path / "ac0.caeprep"
    with zipfile.ZipFile(historical, "w") as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    if tampered:
        with pytest.raises(PrepError) as error:
            session.open_project(historical)
        assert error.value.code == "invalid_project"
    else:
        session.open_project(historical)
        assert session.describe()["element_count"] == 2


def _bde_wave_source(folder):
    source = _base_model(folder)
    mesh = folder / "mesh.inc"
    mesh.write_bytes(mesh.read_bytes().replace(b"/SHELL/903", b"/QUAD/903"))
    raw = source.read_bytes().replace(
        ("/PART/903\nUpper plate\n" + _i(19, 17, 0)).encode(),
        (solid_block(20, "QUAD property") + "/PART/903\nUpper plate\n" + _i(20, 17, 0)).encode(),
    )
    source.write_bytes(raw.replace(b"#include mesh.inc", b"#include mesh.inc\n#include top/start.inc\n"
                                  b"#include top/gate.inc\n#include top/dummy.inc\n#include deeper/c.inc"))
    includes = {
        "top/start.inc": "#include gate.inc\n#include dummy.inc\n",
        "top/gate.inc": "# First alternate\n",
        "top/dummy.inc": "# Second alternate\n",
        "deeper/c.inc": "# Third alternate\n",
        "gate.inc": "#include nodes.inc\n#include relay/route.inc\n",
        "nodes.inc": "# Root target\n",
        "relay/route.inc": "#include nodes.inc\n",
        "dummy.inc": "#include deeper/start.inc\n",
        "deeper/start.inc": "#include c.inc\n",
        "c.inc": "#include relay/nodes.inc\n",
        "relay/nodes.inc": "# Sibling target\n",
    }
    for name, contents in includes.items():
        include = folder / name
        include.parent.mkdir(parents=True, exist_ok=True)
        include.write_bytes(contents.encode())
    return source


@pytest.mark.parametrize("variant", ("stock", "case", "same-wave", "downstream"))
def test_ac0_repeated_operand_archive_requires_its_shell_namespace(tmp_path, variant):
    # ac0a255 wrote both bindings. The 8e85a669 writer collected only three
    # source files from the same disk layout, omitting sub/mesh.inc.
    fixture = Path(__file__).with_name("fixtures") / "ac0a255-quad-repeated-include.caeprep"
    with zipfile.ZipFile(fixture) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    source, = manifest["source_models"]
    files = {item["original_path"]: item for item in source["files"]}
    assert set(files) == {"conditions_0000.rad", "sub/chooser.inc", "mesh.inc", "sub/mesh.inc"}
    decks = {deck["id"]: deck for deck in manifest["resources"]}

    def original_member(record):
        return f'sources/{source["id"]}/{record["original_resource_id"]}.rad'

    def original(record, data):
        members[original_member(record)] = data
        record["sha256"] = sha256(data).hexdigest()

    def write_project(path):
        members["manifest.json"] = json.dumps(manifest).encode()
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)

    chooser = files["sub/chooser.inc"]
    assert members[original_member(chooser)] == b"#include mesh.inc\n#include mesh.inc\n"
    if variant == "case":
        original(chooser, b"#include mesh.inc\n#include MESH.INC\n")
    elif variant == "same-wave":
        filename = "sub/peer.inc"
        directory = f'sources/{source["id"]}'
        identifier = str(uuid4())
        peer = {"original_resource_id": str(uuid4()), "resource_id": identifier,
                "original_path": filename, "logical_path": f"{directory}/{filename}"}
        source["files"].insert(2, peer)
        original(peer, b"#include mesh.inc\n")
        raw_member = f"raw/{identifier}.rad"
        manifest["resources"].append({
            **decks[chooser["resource_id"]], "id": identifier, "name": peer["logical_path"],
            "logical_path": peer["logical_path"], "raw_member": raw_member,
        })
        members[raw_member] = f'#include {files["sub/mesh.inc"]["logical_path"]}\n'.encode()
        starter = files["conditions_0000.rad"]
        raw_starter = decks[starter["resource_id"]]["raw_member"]
        raw_directive = f'#include {chooser["logical_path"]}\n'.encode()
        members[raw_starter] = members[raw_starter].replace(
            raw_directive, raw_directive + f'#include {peer["logical_path"]}\n'.encode())
        original(starter, members[original_member(starter)].replace(
            b"#include sub/chooser.inc\n", b"#include sub/chooser.inc\n#include sub/peer.inc\n"))
    elif variant == "downstream":
        sibling = files["sub/mesh.inc"]
        original(sibling, members[original_member(sibling)] + b"#include mesh.inc\n")
        members[decks[sibling["resource_id"]]["raw_member"]] += f'#include {files["mesh.inc"]["logical_path"]}\n'.encode()

    project = tmp_path / "original.caeprep"
    write_project(project)
    session = PrepSession()
    session.open_project(project)
    projection = session.mesh_view()
    assert len(projection["node_ids"]) == 16 and len(projection["cells"]) == 4
    assert any(cell["id"] == 9009 and cell["formulation"] == "QUAD" for cell in projection["cells"])

    entry = next(entry for entry in source["id_map"] if entry == ["E:SHELL", 9007, 9009])
    entry[0] = "E:QUAD"
    forged = tmp_path / "forged.caeprep"
    write_project(forged)
    with pytest.raises(PrepError) as error:
        session.open_project(forged)
    assert error.value.code == "invalid_project"


@pytest.mark.parametrize("suffix", ("include-order", "directory-include", "qualified-order"))
def test_ac0_include_wave_archive_rejects_altered_quad_namespace(tmp_path, suffix):
    fixture = Path(__file__).with_name("fixtures") / f"ac0a255-quad-{suffix}.caeprep"
    session = PrepSession()
    session.open_project(fixture)
    with zipfile.ZipFile(fixture) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        source, = manifest["source_models"]
        order = [record["original_path"] for record in source["files"]]
        if suffix == "qualified-order":
            assert order == ["conditions_0000.rad", "a/first.inc", "sub/mesh.inc", "a/sub/mesh.inc"]
        else:
            leaf = suffix == "directory-include"
            assert len(order) == (8 if leaf else 7)
            assert order.index("trigger.inc") < order.index("mesh.inc")
            assert ("b/trigger.inc/leaf.inc" in order) is leaf
        entry = next(entry for entry in source["id_map"] if entry == ["E:SHELL", 9007, 9009])
        entry[0] = "E:QUAD"
        edited = tmp_path / "altered.caeprep"
        with zipfile.ZipFile(edited, "w") as project:
            for member in archive.namelist():
                payload = json.dumps(manifest).encode() if member == "manifest.json" else archive.read(member)
                project.writestr(member, payload)
    with pytest.raises(PrepError) as error:
        session.open_project(edited)
    assert error.value.code == "invalid_project"


@pytest.mark.parametrize("file_count", (79, 132, 41))
def test_8e85_reopens_signed_archive_with_delayed_includes(tmp_path, file_count):
    fixture = Path(__file__).with_name("fixtures") / f"8e85a669-signed-{file_count}-includes.caeprep"
    session = PrepSession()
    session.open_project(fixture)
    assert len(session.source_models()[0]["files"]) == file_count
    saved = tmp_path / "saved.caeprep"
    session.save_project(saved)
    session.open_project(saved)
    target = tmp_path / "export/case_0000.rad"
    session.export_analysis_case(target)
    session.open_rad(target)
    projection = session.mesh_view()
    assert len(projection["node_ids"]) == 16 and len(projection["cells"]) == 4
    group = _card(session, "/GRSHEL/SHEL/48")["id"]
    assert session.group_members(group)["member_ids"] == [9008]
    assert session.card_text(group).splitlines()[2] == _i(9008, 9009, -9009)


@pytest.mark.parametrize("tampered", (False, True))
def test_bde_frozen_include_wave_preserves_quad_namespace(tmp_path, tampered):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "base"))
    source = _bde_wave_source(tmp_path / "source")
    session.import_source(session.plan_import_source(source)["plan_id"])
    case = session.create_analysis_case("Legacy QUAD", [], .01, .001, "s")["case_id"]
    modern = tmp_path / "modern.caeprep"
    session.save_project(modern)
    with zipfile.ZipFile(modern) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    source_model, = manifest["source_models"]
    source_model.pop("include_bindings")
    manifest.pop("include_bindings")
    files = {file["original_path"]: file for file in source_model["files"]}
    assert len(files) == 13
    member = next(deck["raw_member"] for deck in manifest["resources"]
                  if deck["id"] == files["relay/route.inc"]["resource_id"])
    # The frozen wave binds route.inc to the root. This reaches the sibling
    # only later, through c.inc, unlike the modern wave and ac0a255 policies.
    sibling = files["relay/nodes.inc"]
    assert sibling["logical_path"].encode() in members[member]
    members[member] = members[member].replace(sibling["logical_path"].encode(), files["nodes.inc"]["logical_path"].encode())
    ordered = source_model["files"]
    ordered.remove(sibling)
    ordered.insert(ordered.index(files["c.inc"]) + 1, sibling)
    if tampered:
        next(entry for entry in source_model["id_map"] if entry[:2] == ["E:QUAD", 9007])[0] = "E:SHELL"
    members["manifest.json"] = json.dumps(manifest).encode()
    legacy = tmp_path / "bde.caeprep"
    with zipfile.ZipFile(legacy, "w") as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    if tampered:
        with pytest.raises(PrepError) as error:
            session.open_project(legacy)
        assert error.value.code == "invalid_project"
    else:
        session.open_project(legacy)
        target = tmp_path / "export/case_0000.rad"
        session.export_analysis_case(target, case)
        session.open_rad(target)
        assert len(session.mesh_view()["node_ids"]) == 16
        assert len(session.mesh_view()["cells"]) == 4


@pytest.mark.parametrize("writer", ("241", "987", "quoted", "current"))
def test_archive_signed_element_exclusions_follow_writer_support(tmp_path, writer):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "base"))
    source = _base_model(tmp_path / "source")
    raw = source.read_bytes().replace(b"/END", f"/GRSHEL/SHEL/48\nSource shells\n{_i(7001, 9007, -9007)}\n/END".encode())
    if writer == "987":
        raw = raw.replace(b"#include mesh.inc", b'#include\n"mesh.inc"')
    source.write_bytes(raw)
    plan = session.plan_import_source(source)
    ids = {(namespace, original): mapped for namespace, original, mapped in plan["source"]["id_map"]}
    session.import_source(plan["plan_id"])
    modern = tmp_path / "modern.caeprep"
    session.save_project(modern)
    with zipfile.ZipFile(modern) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    source_model, = manifest["source_models"]
    if writer != "current":
        source_model.pop("include_bindings")
        manifest.pop("include_bindings")
    if writer == "241":
        archived_ids = {item["resource_id"] for item in source_model["files"]}
        for deck in manifest["resources"]:
            if deck["id"] in archived_ids:
                deck["state"]["state_version"] = 4
                assert not deck["state"].pop("retained_comments")
    if writer == "987":
        path = next(item["logical_path"].encode() for item in source_model["files"] if item["original_path"] == "mesh.inc")
        root = next(deck["raw_member"] for deck in manifest["resources"] if deck["id"] == source_model["root_resource_id"])
        assert b'"' + path + b'"' in members[root]
        members[root] = members[root].replace(b'"' + path + b'"', path)
    members["manifest.json"] = json.dumps(manifest).encode()
    candidate = tmp_path / "candidate.caeprep"
    with zipfile.ZipFile(candidate, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    if writer in ("241", "987"):
        with pytest.raises(PrepError) as error:
            session.open_project(candidate)
        assert error.value.code in {"unsupported_source_profile", "invalid_project"}
        return
    session.open_project(candidate)
    group = _card(session, "/GRSHEL/SHEL/48")["id"]
    assert session.group_members(group)["member_ids"] == [ids["E:SHELL", 7001]]
    assert _i(-ids["E:SHELL", 9007]) in session.card_text(group)


@pytest.mark.parametrize("repeated_operand", (False, True), ids=("seven-files", "eleven-files"))
def test_8e85_signed_archive_replays_fallback_include_traversal(tmp_path, repeated_operand):
    # Written by 8e85a669 with an empty source_paths list. The unused
    # a/door/marker.inc on disk delayed door/marker.inc by one INCLUDE wave.
    name = "8e85a669-signed-repeated-include" if repeated_operand else "8e85a669-signed-includes"
    fixture = Path(__file__).with_name("fixtures") / f"{name}.caeprep"
    with zipfile.ZipFile(fixture) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        source, = manifest["source_models"]
        assert len(source["files"]) == (11 if repeated_operand else 7)
        operands = {"b/entry.inc": b"#include mesh.inc\n", "door/marker.inc": b"#include mesh.inc\n"}
        if repeated_operand:
            operands["door/marker.inc"] += b"#include sub/alternate.inc\n"
            operands["sub/chooser.inc"] = b"#include dups.inc\n#include dups.inc\n"
            operands["sub/alternate.inc"] = b"#include dups.inc\n"
        for path, expected in operands.items():
            record = next(item for item in source["files"] if item["original_path"] == path)
            assert archive.read(f'sources/{source["id"]}/{record["original_resource_id"]}.rad') == expected

    def assert_group(session):
        projection = session.mesh_view()
        assert len(projection["node_ids"]) == 16
        assert len(projection["cells"]) == 4
        group = _card(session, "/GRSHEL/SHEL/48")["id"]
        membership = session.group_members(group)
        assert membership["member_ids"] == [9008] and not membership["diagnostics"]
        assert session.card_text(group).splitlines()[2] == _i(9008, 9009, -9009)

    def assert_bindings(session):
        ids = {item["original_path"]: item["resource_id"] for item in source["files"]}
        assert session._include_bindings[ids["b/entry.inc"], 0] == ids["mesh.inc"]
        assert session._include_bindings[ids["door/marker.inc"], 0] == ids["door/mesh.inc"]
        if repeated_operand:
            assert session._include_bindings[ids["sub/chooser.inc"], 0] == ids["dups.inc"]
            assert session._include_bindings[ids["sub/chooser.inc"], 1] == ids["sub/dups.inc"]
            assert session._include_bindings[ids["sub/alternate.inc"], 0] == ids["sub/dups.inc"]

    session = PrepSession()
    session.open_project(fixture)
    assert_group(session)
    assert_bindings(session)
    for name in ("first", "second"):
        saved = tmp_path / f"{name}.caeprep"
        session.save_project(saved)
        session.open_project(saved)
        assert_group(session)
        assert_bindings(session)
    target = tmp_path / "export/case_0000.rad"
    session.export_analysis_case(target)
    session.open_rad(target)
    assert_group(session)


def test_stale_or_unsupported_import_has_no_partial_commit(tmp_path):
    first, second = model(tmp_path / "first"), model(tmp_path / "second")
    session = PrepSession(); session.open_rad(first)
    plan = session.plan_import_source(second)
    material = next(item for item in session.list_cards() if item["keyword"] == "/MAT/LAW1/41")
    session.set_field(material["id"], "young_modulus", 190000)
    with pytest.raises(PrepError) as error: session.import_source(plan["plan_id"])
    assert error.value.code == "stale_import_plan" and session.source_models() == []
    second.write_bytes(second.read_bytes().replace(b"/END", b"/UNKNOWN/17\npayload\n/END"))
    with pytest.raises(PrepError) as error: session.plan_import_source(second)
    assert error.value.code == "unsupported_source_profile" and session.document.revision == 1


def test_compound_native_and_case_edit_validates_all_before_single_commit(tmp_path):
    source = model(tmp_path / "source")
    session = PrepSession(); session.open_rad(source)
    material = next(item for item in session.list_cards() if item["keyword"] == "/MAT/LAW1/41")
    case = session.create_analysis_case("First", [], 1, .1, "ms")["case_id"]
    revision = session.document.revision
    events = []; session.subscribe(events.append)
    original_bytes = session.document.resources[material["resource_id"]].raw
    commands = [{"operation": "set_fields", "arguments": {"card_id": material["id"], "values": {"young_modulus": 190000}}},
                {"operation": "set_analysis_case", "arguments": {"case_id": case, "values": {"end_time": -1}}}]
    with pytest.raises(PrepError): session.execute_many(commands, expected_revision=revision)
    assert session.document.revision == revision and not events
    assert session.card_fields(material["id"])[1]["value"] == 210000
    commands[1]["arguments"]["values"]["end_time"] = 2
    result = session.execute_many(commands, expected_revision=revision)
    assert result["revision"] == revision + 1 and len(events) == 1
    assert len(events[0]["change"]["resource_ids"]) == 2
    assert session.card_fields(material["id"])[1]["value"] == 190000
    assert session.analysis_case(case)["end_time"] == 2
    assert session.document.resources[material["resource_id"]].raw is original_bytes
    session.undo()
    assert session.card_fields(material["id"])[1]["value"] == 210000 and session.analysis_case(case)["end_time"] == 1


@pytest.mark.parametrize("version", [4, 5])
def test_source_formats_require_registry_and_reject_missing_archive_bytes(tmp_path, version):
    session = PrepSession(); session.open_rad(model(tmp_path / "source"))
    session.import_source(session.plan_import_source(model(tmp_path / "other"))["plan_id"])
    project = tmp_path / "good.caeprep"; session.save_project(project)
    with zipfile.ZipFile(project) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"]); manifest["version"] = version
    members["manifest.json"] = json.dumps(manifest).encode()
    for kind in ("registry", "payload"):
        altered = dict(members)
        if kind == "registry":
            manifest = json.loads(altered["manifest.json"]); del manifest["source_models"]
            altered["manifest.json"] = json.dumps(manifest).encode()
        else:
            del altered[next(name for name in altered if name.startswith("sources/"))]
        bad = tmp_path / f"{kind}.caeprep"
        with zipfile.ZipFile(bad, "w") as archive:
            for name, raw in altered.items(): archive.writestr(name, raw)
        before = session.describe()
        with pytest.raises(PrepError): session.open_project(bad)
        assert session.describe() == before


def test_standard_type7_import_maps_targets_and_never_treats_scale_as_id(tmp_path):
    source = model(tmp_path / "source")
    edited = PrepSession(); edited.open_rad(source)
    group = edited.create_node_group("Secondary", [1,2], native_id=59)["card_id"]
    part = next(card for card in edited.list_cards() if card["keyword"] == "/PART/9")
    surface = edited.create_surface("Main", [part["id"]], native_id=71)["card_id"]
    edited.create_contact("Contact", group, surface, .17, native_id=97)
    native = tmp_path / "with-contact" / "model_0000.rad"; edited.export_rad(native)
    session = PrepSession(); session.open_rad(model(tmp_path / "base"))
    plan = session.plan_import_source(native); session.import_source(plan["plan_id"])
    contact = next(card for card in session.list_cards() if card["keyword"] == "/INTER/TYPE7/97")
    values = session.condition_values(contact["id"])
    assert values["friction"] == .17 and values["diagnostics"] == []
    # A temperature friction function must never silently acquire an unmapped ID.
    text = native.read_text().splitlines(keepends=True)
    index = next(i for i,line in enumerate(text) if line.startswith("/INTER/TYPE7/")) + 7
    body = text[index].rstrip("\n")
    text[index] = body[:60] + f"{63:10}" + " "*20 + body[90:] + "\n"
    native.write_text("".join(text))
    with pytest.raises(PrepError) as error: session.plan_import_source(native)
    assert error.value.code == "unsupported_source_profile"


def test_source_planning_does_not_hold_live_owner_lock_and_rechecks_revision(tmp_path, monkeypatch):
    first,second=model(tmp_path/"first"),model(tmp_path/"second")
    session=PrepSession();session.open_rad(first)
    entered,released,edited=Event(),Event(),Event(); errors=[]
    original=Path.read_bytes
    def delayed(path):
        if path == second:
            entered.set()
            if not released.wait(3): raise RuntimeError("test input was not released")
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",delayed)
    def prepare():
        try:session.plan_import_source(second)
        except Exception as exc:errors.append(exc)
    worker=Thread(target=prepare);worker.start();assert entered.wait(1)
    material=next(card for card in session.list_cards() if card["keyword"]=="/MAT/LAW1/41")
    def change():
        session.set_field(material["id"],"young_modulus",190000);edited.set()
    edit=Thread(target=change);edit.start()
    try:assert edited.wait(1),"Live edit waited for background source parsing"
    finally:released.set();worker.join(3);edit.join(3)
    assert len(errors)==1 and isinstance(errors[0],PrepError) and errors[0].code=="stale_import_plan"
    assert session.document.revision==1 and session.source_models()==[]
