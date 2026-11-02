"""Independent IDs, original bytes and atomic native/case relationships."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.radioss.modeling import material_block, shell_block


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


def test_v4_requires_source_registry_and_rejects_missing_archive_bytes(tmp_path):
    session = PrepSession(); session.open_rad(model(tmp_path / "source"))
    session.import_source(session.plan_import_source(model(tmp_path / "other"))["plan_id"])
    project = tmp_path / "good.caeprep"; session.save_project(project)
    with zipfile.ZipFile(project) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
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
