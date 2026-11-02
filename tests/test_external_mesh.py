"""Independent, CAD-less MSH inputs exercise inventory through native output."""
from dataclasses import replace
from pathlib import Path
import threading

import pytest

from caelab_prep.adapters.msh_worker import read_msh
from caelab_prep.application import PrepSession
from caelab_prep.application.external_mesh import import_standalone_mesh, read_imported_mesh
from caelab_prep.cae_core.errors import PrepError


SHELL_MSH = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
4
2 11 "Left sheet"
2 22 "Right sheet"
1 31 "Supported edge"
0 41 "Anchor"
$EndPhysicalNames
$Nodes
6
11 0 0 0
31 1 0 0
51 0 1 0
101 3 0 0
131 4 0 0
151 3 1 0
$EndNodes
$Elements
4
501 2 2 11 1 11 31 51
901 2 2 22 2 101 131 151
1201 1 2 31 3 11 31
1501 15 2 41 4 11
$EndElements
"""

SOLID_MSH = """$MeshFormat
4.1 0 8
$EndMeshFormat
$PhysicalNames
4
3 7 "Upper block"
3 8 "Lower block"
3 9 "All blocks"
2 41 "Interface nodes"
$EndPhysicalNames
$Entities
0 0 1 2
12 0 0 0 1 1 0 1 41 0
31 0 0 0 1 1 1 2 7 9 1 12
32 0 0 -1 1 1 0 2 8 9 1 -12
$EndEntities
$Nodes
1 5 10 50
3 31 0 5
10 20 30 40 50
0 0 0
1 0 0
0 1 0
0 0 1
0 0 -1
$EndNodes
$Elements
3 3 401 403
2 12 2 1
401 10 20 30
3 31 4 1
402 10 20 30 40
3 32 4 1
403 10 30 20 50
$EndElements
"""


@pytest.fixture
def gmsh_sdk():
    from importlib.util import find_spec
    if find_spec("gmsh") is None:
        pytest.skip("The standalone importer requires optional caelab-prep[cad] Gmsh SDK")


@pytest.fixture(params=[("sheets", SHELL_MSH, 2), ("blocks", SOLID_MSH, 3)])
def external_input(tmp_path, request, gmsh_sdk):
    name, text, dimension = request.param
    source = tmp_path / (name + ".msh")
    source.write_text(text, encoding="utf-8")
    return source, dimension


def session_for(dimension, length="mm"):
    session = PrepSession()
    session.new_document("External user mesh", {"mass": "Mg", "length": length, "time": "s"})
    material = session.create_material("Steel", 7.8e-9, 210000, .3)["card_id"]
    section = (session.create_shell_property("Shell", .2) if dimension == 2 else session.create_solid_property("Solid"))["card_id"]
    return session, material, section


def state(session):
    return session.describe()["revision"], tuple((c["id"], session.card_text(c["id"])) for c in session.list_cards())


def test_cadless_formats_preserve_full_inventory_groups_and_units(external_input, tmp_path):
    source, dimension = external_input
    raw = source.read_bytes()
    candidate = import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    assert candidate.dimension == dimension and candidate.geometry_resource_uuid is None
    assert candidate.quality.passed and len(candidate.parts) == 2
    assert sum(item.count for item in candidate.inventory) == (4 if dimension == 2 else 3)
    assert len(candidate.groups) == 4
    assert {asset.kind for asset in candidate.assets} == {"msh", "metadata"}
    assert {path.name for path in Path(candidate.manifest_path).parent.iterdir()} == {"input.msh", "metadata.json"}
    native = candidate.to_native_mesh()
    assert native.source_kind == "standalone_msh" and native.geometry_resource_uuid is None
    assert len(native.elements) == 2
    assert native.omitted_boundary_cells == (2 if dimension == 2 else 1)
    assert read_imported_mesh(candidate.manifest_path) == candidate
    assert source.read_bytes() == raw
    if dimension == 3:
        all_blocks = next(group for group in native.groups if group.key == "physical:3:9")
        assert all_blocks.member_ids == (402, 403)
        interface = next(group for group in native.groups if group.key == "physical:2:41")
        assert interface.kind == "node" and interface.member_ids == (10, 20, 30)
    with pytest.raises(PrepError, match="relabel"):
        candidate.to_native_mesh(length_unit="m")


def test_native_adoption_one_undo_collisions_group_members_and_reopen(external_input, tmp_path):
    from test_mesh_adoption import _native
    source, dimension = external_input
    candidate = import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    mesh = candidate.to_native_mesh()
    session, material, section = session_for(dimension)
    before = state(session)
    adopted = session.adopt_mesh_candidate(mesh, material_id=material, property_id=section,
        expected_document_id=session.describe()["document_id"], expected_revision=before[0])
    assert session.describe()["revision"] == before[0] + 1
    assert len(adopted["part_ids"]) == 2
    assert set(adopted["group_id_map"]) == {group.key for group in mesh.groups}
    for group in mesh.groups:
        members = session.group_members(adopted["group_id_map"][group.key])
        mapping = adopted["node_id_map"] if group.kind == "node" else adopted["element_id_map"]
        assert set(members["member_ids"]) == {mapping[value] for value in group.member_ids}
    first = state(session)[1]
    session.undo(); assert state(session)[1] == before[1]
    session.redo(); assert state(session)[1] == first
    again = session.adopt_mesh_candidate(mesh, material_id=material, property_id=section)
    assert set(again["node_id_map"].values()).isdisjoint(adopted["node_id_map"].values())
    assert set(again["element_id_map"].values()).isdisjoint(adopted["element_id_map"].values())
    assert all(session.card_text(key) == text for key, text in first)
    session.undo()
    output = tmp_path / "working.caeprep"; session.save_project(output)
    reopened = PrepSession(); reopened.open_project(output)
    exported = tmp_path / "export" / "import_0000.rad"; reopened.export_rad(exported)
    nodes, elements, parts = _native(exported.read_bytes())
    assert len(nodes) == len(mesh.nodes) and len(elements) == 2 and len(parts) == 2
    for node in mesh.nodes: assert nodes[adopted["node_id_map"][node.id]] == pytest.approx(node.xyz)
    for cell in mesh.elements:
        assert elements[adopted["element_id_map"][cell.id]][1] == tuple(adopted["node_id_map"][n] for n in cell.node_ids)
    for group in mesh.groups:
        assert reopened.group_members(adopted["group_id_map"][group.key])["member_ids"]
    native_reopened = PrepSession(); native_reopened.open_rad(exported)
    assert native_reopened.describe()["element_count"] == 2
    assert len([card for card in native_reopened.list_cards() if card["keyword"].startswith(("/GRNOD/", "/GRSH3N/", "/GRBRIC/"))]) == 4


@pytest.mark.parametrize("change,match", [
    (lambda text: text.replace("2.2 0 8", "2.2 1 8"), "ASCII"),
    (lambda text: text.replace("2.2 0 8", "4.0 0 8"), "Supported format"),
    (lambda text: text.replace("31 1 0 0", "11 1 0 0"), "duplicate node"),
    (lambda text: text.replace("901 2 2", "501 2 2"), "Duplicate ID"),
    (lambda text: text.replace("11 31 51", "11 31 999"), "missing node"),
    (lambda text: text.replace("31 1 0 0", "31 nan 0 0"), "finite"),
    (lambda text: text.replace("$EndElements", ""), "Missing"),
    (lambda text: text + "$Periodic\n0\n$EndPeriodic\n", "Unsupported MSH section"),
    (lambda text: text + "$NodeData\n0\n$EndNodeData\n", "Unsupported MSH section"),
    (lambda text: text.replace('2 22 "Right sheet"', '2 11 "Right sheet"'), "physical group"),
    (lambda text: text.replace("501 2 2 11 1", "501 2 3 11 1 0"), "Partitioned"),
])
def test_malformed_input_is_never_partially_accepted(tmp_path, change, match):
    source = tmp_path / "invalid.msh"; source.write_text(change(SHELL_MSH))
    with pytest.raises(ValueError, match=match): read_msh(source)


@pytest.mark.usefixtures("gmsh_sdk")
def test_unsupported_inventory_quality_and_free_shell_are_blocked(tmp_path):
    source = tmp_path / "quad.msh"
    source.write_text(SHELL_MSH.replace("501 2 2 11 1 11 31 51", "501 3 2 11 1 11 31 151 51"))
    candidate = import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    assert sum(item.count for item in candidate.inventory) == 4
    assert candidate.quality.unsupported_ids == (501,)
    with pytest.raises(PrepError) as error: candidate.to_native_mesh()
    assert error.value.code == "mesh_quality"
    source.write_text(SOLID_MSH.replace("401 10 20 30", "401 10 40 50"))
    with pytest.raises(PrepError) as error: import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    assert error.value.code == "mixed_dimension_mesh"
    source.write_text(SOLID_MSH.replace("403 10 30 20 50", "403 10 20 30 50"))
    candidate = import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    assert 403 in candidate.quality.problem_ids
    with pytest.raises(PrepError): candidate.to_native_mesh()


def test_cancel_invalid_units_changed_asset_and_forged_groups_are_atomic(external_input, tmp_path):
    source, dimension = external_input
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(PrepError) as error:
        import_standalone_mesh(source, tmp_path / "imports", length_unit="mm", cancel_event=cancelled)
    assert error.value.code == "cancelled" and not (tmp_path / "imports").exists()
    with pytest.raises(PrepError) as error: import_standalone_mesh(source, tmp_path / "imports", length_unit="unknown")
    assert error.value.code == "unknown_length_unit"
    candidate = import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    mesh = candidate.to_native_mesh()
    session, material, section = session_for(dimension, length="m")
    before = state(session)
    with pytest.raises(PrepError) as error: session.adopt_mesh_candidate(mesh, material_id=material, property_id=section)
    assert error.value.code == "unit_mismatch" and state(session) == before
    session, material, section = session_for(dimension)
    before = state(session)
    forged = replace(mesh, groups=(replace(mesh.groups[0], member_ids=(99999,)), *mesh.groups[1:]))
    with pytest.raises(PrepError) as error: session.adopt_mesh_candidate(forged, material_id=material, property_id=section)
    assert error.value.code == "invalid_native_mesh" and state(session) == before
    source_copy = next(asset.path for asset in mesh.assets if asset.kind == "msh")
    Path(source_copy).write_text(Path(source_copy).read_text() + "\n")
    with pytest.raises(PrepError) as error: session.adopt_mesh_candidate(mesh, material_id=material, property_id=section)
    assert error.value.code == "candidate_changed" and state(session) == before


@pytest.mark.usefixtures("gmsh_sdk")
def test_empty_declared_physical_group_and_corrupt_41_count_fail(tmp_path):
    source = tmp_path / "invalid.msh"
    source.write_text(SHELL_MSH.replace('0 41 "Anchor"', '0 42 "Missing anchor"'))
    with pytest.raises(PrepError) as error: import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    assert error.value.code == "empty_physical_group"
    source.write_text(SOLID_MSH.replace("1 5 10 50", "1 6 10 50"))
    with pytest.raises(ValueError, match="Node count"): read_msh(source)
    # A valid top-cell-only MSH can retain physical surface declarations while
    # omitting its boundary elements. Their missing membership is not guessed.
    source.write_text(SOLID_MSH.replace("3 3 401 403", "2 2 402 403")
                      .replace("2 12 2 1\n401 10 20 30\n", ""))
    with pytest.raises(PrepError) as error: import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    assert error.value.code == "empty_physical_group" and "41" in str(error.value)
    source.write_text(SOLID_MSH.replace(SOLID_MSH.split("$Entities\n")[1].split("$EndEntities")[0], "0 0 0 0\n"))
    with pytest.raises(ValueError, match="absent entity"): read_msh(source)


@pytest.mark.parametrize("interruption", ["cancelled", "import_timeout"])
def test_interrupted_real_reader_is_terminated_and_reaped(tmp_path, monkeypatch, interruption):
    from caelab_prep.application import external_mesh
    source = tmp_path / "source.msh"; source.write_text(SHELL_MSH)
    event = threading.Event()
    processes = []
    real_popen = external_mesh.subprocess.Popen

    def observe_start(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        if interruption == "cancelled": event.set()
        return process

    monkeypatch.setattr(external_mesh.subprocess, "Popen", observe_start)
    with pytest.raises(PrepError) as error:
        external_mesh._read_in_worker(source, cancel_event=event,
                                      timeout=1e-9 if interruption == "import_timeout" else 60)
    assert error.value.code == interruption
    assert len(processes) == 1 and processes[0].poll() is not None


def test_import_cli_runs_in_independent_processes_and_keeps_source(external_input, tmp_path):
    from test_modeling_commands import cli
    source, dimension = external_input
    session, material, section = session_for(dimension)
    original = tmp_path / "before.caeprep"; session.save_project(original)
    before = original.read_bytes(), source.read_bytes()
    saved = tmp_path / "after.caeprep"
    code, result = cli("import-mesh", original, source, "--assets", tmp_path / "cli-assets",
        "--length-unit", "mm", "--material", material, "--property", section, "--output", saved)
    assert code == 0, result
    assert len(result["adoption"]["group_id_map"]) == 4 and Path(result["manifest"]).is_file()
    assert (original.read_bytes(), source.read_bytes()) == before
    native = tmp_path / "cli-native" / "user_0000.rad"
    code, result = cli("export", saved, "--output", native)
    assert code == 0, result
    code, result = cli("inspect", native)
    assert code == 0 and result["element_count"] == 2
    failed = tmp_path / "must-not-exist.caeprep"
    code, result = cli("import-mesh", original, source, "--assets", tmp_path / "cli-assets",
        "--length-unit", "m", "--material", material, "--property", section, "--output", failed)
    assert code == 1 and not failed.exists()
    assert (original.read_bytes(), source.read_bytes()) == before
