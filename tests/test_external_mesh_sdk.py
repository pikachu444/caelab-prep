"""Real Gmsh SDK parity, including an equivalent independent mixed-family case.

The user's source files in another cloud session were unavailable. These files
reproduce the stated node/element/group identities; they are not those originals.
"""
from copy import deepcopy

import pytest

from caelab_prep.adapters.msh_worker import inspect_msh, read_msh
from caelab_prep.application import mesh_candidates
from caelab_prep.application.external_mesh import import_standalone_mesh
from caelab_prep.cae_core.errors import PrepError
from test_external_mesh import external_input, gmsh_sdk, SHELL_MSH

pytestmark = pytest.mark.usefixtures("gmsh_sdk")

MIXED22 = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
2
2 110 "Part_11"
2 220 "Part_22"
$EndPhysicalNames
$Nodes
7
101 0 0 0
102 1 0 0
103 0 1 0
201 2 0 0
202 3 0 0
203 3 1 0
204 2 1 0
$EndNodes
$Elements
2
110 2 2 110 11 101 102 103
220 3 2 220 22 201 202 203 204
$EndElements
"""

MIXED41 = """$MeshFormat
4.1 0 8
$EndMeshFormat
$PhysicalNames
2
2 110 "Part_11"
2 220 "Part_22"
$EndPhysicalNames
$Entities
0 0 2 0
11 0 0 0 1 1 0 1 110 0
22 2 0 0 3 1 0 1 220 0
$EndEntities
$Nodes
2 7 101 204
2 11 0 3
101 102 103
0 0 0
1 0 0
0 1 0
2 22 0 4
201 202 203 204
2 0 0
3 0 0
3 1 0
2 1 0
$EndNodes
$Elements
2 2 110 220
2 11 2 1
110 101 102 103
2 22 3 1
220 201 202 203 204
$EndElements
"""


@pytest.mark.parametrize("text", [MIXED22, MIXED41], ids=["ascii22", "ascii41"])
def test_mixed_triangle_quad_keeps_every_file_id_and_group_but_blocks_adoption(tmp_path, text):
    path = tmp_path / "independent-mixed.msh"; path.write_text(text)
    data = inspect_msh(path)
    assert set(data["nodes"]["ids"]) == {101, 102, 103, 201, 202, 203, 204}
    assert {(group["tag"], group["name"]) for group in data["physical_groups"]} == {(110, "Part_11"), (220, "Part_22")}
    assert {key: tuple(conn) for block in data["blocks"] for key, conn in zip(block["ids"], block["connectivity"])} == {
        110: (101, 102, 103), 220: (201, 202, 203, 204)}
    candidate = import_standalone_mesh(path, tmp_path / "assets", length_unit="mm")
    assert {(row.element_type, row.count) for row in candidate.inventory} == {(2, 1), (3, 1)}
    assert candidate.quality.unsupported_ids == (220,)
    assert {group.key for group in candidate.groups} == {"physical:2:110", "physical:2:220"}
    with pytest.raises(PrepError, match="whole import"): candidate.to_native_mesh()


def test_actual_sdk_duplicate_id_normalization_is_stopped_before_admission(tmp_path):
    path = tmp_path / "duplicate.msh"; path.write_text(SHELL_MSH.replace("901 2 2", "501 2 2"))
    # SDK 4.15.2 silently drops one physical cell and its group. This concrete
    # loss is why strict source preflight remains in front of the shared reader.
    sdk = mesh_candidates._inspect_msh(path)
    assert sum(len(block["ids"]) for block in sdk["element_blocks"]) == 3
    assert {group["name"] for group in sdk["physical_groups"]} == {"Anchor", "Supported edge", "Right sheet"}
    with pytest.raises(ValueError, match="Duplicate ID"): inspect_msh(path)


def test_sdk_written_41_is_compared_to_file_ids_not_prewrite_memory(tmp_path):
    import gmsh
    source = tmp_path / "before-write.msh"; source.write_text(MIXED22)
    written = tmp_path / "sdk-written41.msh"
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0); gmsh.open(str(source))
        gmsh.option.setNumber("Mesh.Binary", 0); gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.write(str(written))
    finally: gmsh.finalize()
    source_records = read_msh(written)
    candidate = import_standalone_mesh(written, tmp_path / "assets", length_unit="mm")
    assert {node.id for node in candidate.nodes} == set(source_records["nodes"]["ids"])
    assert {cell.id: cell.node_ids for cell in candidate.cells} == {
        key: tuple(conn) for block in source_records["blocks"] for key, conn in zip(block["ids"], block["connectivity"])}
    assert {group.name for group in candidate.groups} == {"[2:110] Part_11", "[2:220] Part_22"}
    assert sum(row.count for row in candidate.inventory) == 2 and not candidate.quality.passed


def test_ungrouped_entities_are_parts_and_do_not_get_invented_physical_sets(tmp_path):
    path = tmp_path / "ungrouped.msh"
    path.write_text(SHELL_MSH.replace('4\n2 11 "Left sheet"', '3').replace("501 2 2 11 1", "501 2 2 0 1"))
    candidate = import_standalone_mesh(path, tmp_path / "assets", length_unit="mm")
    assert candidate.quality.passed and len(candidate.parts) == 2
    assert {part.name for part in candidate.parts} == {"Ungrouped entity 1", "Right sheet"}
    assert len(candidate.groups) == 3 and "physical:2:11" not in {group.key for group in candidate.groups}
    assert {cell.id for cell in candidate.to_native_mesh().elements} == {501, 901}


@pytest.mark.parametrize("mismatch", ["node", "element", "group"])
def test_sdk_source_disagreement_rejects_the_whole_result(external_input, monkeypatch, mismatch):
    path, _ = external_input
    data = deepcopy(mesh_candidates._inspect_msh(path))
    if mismatch == "node": data["nodes"]["coordinates"][0][0] += 1
    elif mismatch == "element": data["element_blocks"][0]["connectivity"][0][0] += 1000
    else: data["physical_groups"][0]["name"] = "changed SDK group"
    monkeypatch.setattr(mesh_candidates, "_inspect_msh", lambda path: data)
    with pytest.raises(ValueError, match="differs from the captured MSH"): inspect_msh(path)
