"""Candidate admission checks, including three freshly generated CAD models.

SDK tests use the same public backend as the application and independent MSH
inspection. They skip explicitly when the optional Gmsh/OCP dependencies cannot
initialize; pure numerical and rejection checks always run.
"""
from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from caelab_prep.adapters.gmsh_backend import GmshBackend
from caelab_prep.application.mesh_candidates import (
    CellInventory, MeshCandidate, MeshCell, MeshNode, QualityLimits, _quality,
    read_mesh_candidate, tetrahedron_quality, triangle_quality, validate_native_mesh,
)
from caelab_prep.cae_core.errors import PrepError


def test_candidate_module_does_not_import_native_or_gui_libraries():
    script = "import sys; import caelab_prep.application.mesh_candidates; assert not {'gmsh', 'vtk', 'PySide6'} & sys.modules.keys()"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


TRIANGLE = ((0., 0., 0.), (1., 0., 0.), (.5, math.sqrt(3) / 2, 0.))
TETRAHEDRON = (*TRIANGLE, (.5, math.sqrt(3) / 6, math.sqrt(2 / 3)))


@pytest.mark.parametrize("scale", [1e-8, 1., 1e8])
def test_mean_ratio_is_one_for_equilateral_cells_and_scale_invariant(scale):
    tri = [tuple(scale * (v + 3) for v in point) for point in TRIANGLE]
    tet = [tuple(scale * (v + 3) for v in point) for point in TETRAHEDRON]
    assert triangle_quality(tri)[0] == pytest.approx(1)
    q, volume, normalized = tetrahedron_quality(tet)
    assert q == pytest.approx(1)
    assert volume == pytest.approx(math.sqrt(2) / 12 * scale ** 3)
    assert normalized > 0


@pytest.mark.parametrize("value", [-1, 1.1, float("nan"), float("inf"), True, "0.1"])
def test_invalid_threshold_is_structured_error(value):
    with pytest.raises(PrepError, match="Quality thresholds"):
        QualityLimits(minimum_triangle=value)


def synthetic_candidate(points, cell, limits=None):
    nodes = tuple(MeshNode(i + 1, point) for i, point in enumerate(points))
    return MeshCandidate("geometry", 1, "mesh", 1, "mm", cell.dimension,
                         nodes, (cell,), (), (), _quality(nodes, (cell,), limits or QualityLimits()), (), "test")


@pytest.mark.parametrize("points, connectivity, problem", [
    (TETRAHEDRON, (1, 3, 2, 4), "inverted"),
    ((*TRIANGLE, (.5, .2, 0.)), (1, 2, 3, 4), "degenerate"),
    ((*TRIANGLE, (.5, .2, .001)), (1, 2, 3, 4), "below_quality_limit"),
])
def test_invalid_tetrahedra_are_inspectable_but_cannot_be_adopted(points, connectivity, problem):
    candidate = synthetic_candidate(points, MeshCell(13, 3, 4, "Tetrahedron 4", 1, connectivity, "part"))
    result = candidate.quality.cells[0]
    assert result.problem == problem
    if problem == "inverted":
        assert result.q == pytest.approx(1)  # q alone must never authorize inversion.
        assert result.signed_measure < 0
    with pytest.raises(PrepError) as error:
        candidate.to_native_mesh()
    assert error.value.code == "mesh_quality"
    assert error.value.details["element_ids"] == [13]


def test_unsupported_quad_is_counted_and_blocks_native_conversion():
    candidate = synthetic_candidate(((0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)),
                                    MeshCell(27, 2, 3, "Quadrilateral 4", 1, (1, 2, 3, 4), "part"))
    assert candidate.quality.unsupported_ids == (27,)
    with pytest.raises(PrepError) as error:
        candidate.to_native_mesh()
    assert error.value.details["unsupported_ids"] == [27]


def test_free_shell_mixed_with_solids_is_not_discarded_as_a_boundary():
    candidate = synthetic_candidate(TETRAHEDRON, MeshCell(9, 3, 4, "Tetrahedron 4", 1, (1, 2, 3, 4), "part"))
    candidate = replace(candidate, inventory=(CellInventory(2, 2, "Triangle 3", 1, 1, "shell", True),))
    with pytest.raises(PrepError) as error:
        candidate.to_native_mesh()
    assert error.value.code == "mixed_dimension_mesh"


def test_unknown_units_require_an_explicit_assignment_and_known_units_cannot_be_relabeled():
    candidate = synthetic_candidate(TRIANGLE, MeshCell(9, 2, 2, "Triangle 3", 1, (1, 2, 3), "part"))
    unknown = replace(candidate, length_unit="unknown")
    with pytest.raises(PrepError) as error:
        unknown.to_native_mesh()
    assert error.value.code == "unknown_length_unit"
    assigned = unknown.to_native_mesh(length_unit="cm")
    assert assigned.length_unit == "cm" and assigned.nodes == candidate.nodes
    with pytest.raises(PrepError) as error:
        candidate.to_native_mesh(length_unit="m")
    assert error.value.code == "unit_mismatch"


@pytest.fixture(scope="module", params=["surface", "cylinder", "two-solids"])
def real_candidate(request, tmp_path_factory):
    check = subprocess.run([sys.executable, "-c", "import gmsh; gmsh.initialize(interruptible=False); gmsh.finalize()"],
                           capture_output=True, text=True, timeout=30)
    if check.returncode:
        pytest.skip("Gmsh SDK/native dependencies unavailable: " + check.stderr[-300:])
    pytest.importorskip("OCP")
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound

    directory = tmp_path_factory.mktemp("candidate-" + request.param)
    if request.param == "surface":
        shape = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 0, 10, 0, 7).Face()
        dimension = 2
    elif request.param == "cylinder":
        shape = BRepPrimAPI_MakeCylinder(3, 7).Shape()
        dimension = 3
    else:
        shape = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(shape)
        builder.Add(shape, BRepPrimAPI_MakeBox(5, 4, 3).Shape())
        builder.Add(shape, BRepPrimAPI_MakeBox(gp_Pnt(8, 1, 0), 4, 3, 5).Shape())
        dimension = 3
    source = directory / (request.param + ".step")
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert int(writer.Write(str(source))) == 1
    BRepTools.Write_s(shape, str(source.with_suffix(".brep")))
    result = GmshBackend().generate(source, directory / "assets", 1.8, dimension=dimension)
    candidate = read_mesh_candidate(result)
    return request.param, result, candidate


def test_three_real_cad_candidates_have_complete_inventory_and_native_parts(real_candidate):
    name, result, candidate = real_candidate
    assert candidate.quality.passed, candidate.quality.problem_ids
    assert read_mesh_candidate(result["assets"]["metadata"]) == candidate
    native = candidate.to_native_mesh()
    assert validate_native_mesh(native) == native
    assert len(native.nodes) == result["counts"]["nodes"]
    assert len(native.elements) == result["counts"]["elements"]
    assert len(candidate.cells) == sum(item.count for item in candidate.inventory)
    assert {item.dimension for item in candidate.inventory} == set(range(candidate.dimension + 1))
    assert native.omitted_boundary_cells == len(candidate.cells) - len(native.elements)
    assert native.omitted_boundary_cells > 0
    assert {cell.kind for cell in native.elements} == {"triangle3" if name == "surface" else "tetra4"}
    assert len(native.parts) == (2 if name == "two-solids" else 1)
    assert {cell.part_uuid for cell in native.elements} == {part.uuid for part in native.parts}
    assert set(cell.id for cell in native.elements) == {value for part in native.parts for value in part.element_ids}
    assert {asset.kind for asset in candidate.assets} == {"source", "metadata", "msh", "xao"}
    assert all(len(asset.sha256) == 64 for asset in candidate.assets)
    if candidate.dimension == 3:
        assert any(item.role == "boundary_facet" for item in candidate.inventory)
        with pytest.raises(PrepError) as error:
            candidate.to_native_mesh(dimension=2)
        assert error.value.code == "mesh_dimension"


def test_forged_native_values_and_assets_cannot_bypass_admission(real_candidate):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    bad_node = replace(native.nodes[0], xyz=(999., 999., 999.))
    for forged in (replace(native, nodes=(bad_node, *native.nodes[1:])),
                   replace(native, parts=()), replace(native, elements=native.elements[1:]),
                   replace(native, assets=()),
                   replace(native, assets=(replace(native.assets[0], sha256="0" * 64), *native.assets[1:]))):
        with pytest.raises(PrepError) as error:
            validate_native_mesh(forged)
        assert error.value.code in ("invalid_native_mesh", "candidate_changed")


def _write_altered_metadata(result, tmp_path, mutate):
    altered = json.loads(json.dumps(result))
    path = tmp_path / "altered-metadata.json"
    altered["assets"]["metadata"] = str(path)
    mutate(altered)
    path.write_text(json.dumps(altered), encoding="utf-8")
    return path


def test_modified_coordinates_are_rejected_against_actual_msh(real_candidate, tmp_path):
    _, result, _ = real_candidate
    path = _write_altered_metadata(result, tmp_path, lambda d: d["mesh"]["nodes"]["coordinates"][0].__setitem__(0, 999))
    with pytest.raises(PrepError) as error:
        read_mesh_candidate(path)
    assert error.value.code == "candidate_mismatch"


def test_omitted_element_block_cannot_hide_msh_cells(real_candidate, tmp_path):
    _, result, _ = real_candidate
    path = _write_altered_metadata(result, tmp_path, lambda d: d["mesh"]["element_blocks"].pop())
    with pytest.raises(PrepError) as error:
        read_mesh_candidate(path)
    assert error.value.code == "candidate_mismatch"


def test_backend_result_must_match_persisted_metadata(real_candidate):
    _, result, _ = real_candidate
    altered = json.loads(json.dumps(result))
    altered["counts"]["nodes"] += 1
    with pytest.raises(PrepError) as error:
        read_mesh_candidate(altered)
    assert error.value.code == "candidate_mismatch"


def test_geometry_unit_declaration_is_checked_against_msh_identity(real_candidate, tmp_path):
    _, result, _ = real_candidate
    path = _write_altered_metadata(result, tmp_path, lambda d: d.__setitem__("length_unit", "unknown"))
    with pytest.raises(PrepError) as error:
        read_mesh_candidate(path)
    assert error.value.code == "candidate_mismatch"


def test_real_brep_remains_unknown_until_explicit_unit_assignment(real_candidate, tmp_path):
    _, result, original = real_candidate
    source = Path(result["source"]["path"]).with_suffix(".brep")
    brep_result = GmshBackend().generate(source, tmp_path / "brep-assets", 1.8, dimension=original.dimension)
    candidate = read_mesh_candidate(brep_result)
    assert candidate.length_unit == "unknown"
    with pytest.raises(PrepError) as error:
        candidate.to_native_mesh()
    assert error.value.code == "unknown_length_unit"
    assert candidate.to_native_mesh(length_unit="mm").length_unit == "mm"


def test_real_sdk_higher_order_cells_remain_in_inventory_and_block_adoption(real_candidate, tmp_path):
    _, result, _ = real_candidate
    # The production worker intentionally produces first order. Promote an
    # independent copy with the SDK to exercise admission of unsupported cells.
    msh = tmp_path / "quadratic.msh"
    inspection = tmp_path / "quadratic.json"
    script = '''
import json, sys, gmsh
from pathlib import Path
from caelab_prep.application.mesh_candidates import _inspect_msh
gmsh.initialize(interruptible=False)
gmsh.option.setNumber("General.Terminal", 0)
gmsh.open(sys.argv[1])
gmsh.model.mesh.setOrder(2)
gmsh.option.setNumber("Mesh.SaveAll", 1)
gmsh.option.setNumber("Mesh.Binary", 1)
gmsh.write(sys.argv[2])
gmsh.finalize()
Path(sys.argv[3]).write_text(json.dumps(_inspect_msh(sys.argv[2])))
'''
    process = subprocess.run([sys.executable, "-c", script, result["assets"]["msh"], str(msh), str(inspection)],
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    observed = json.loads(inspection.read_text())
    def update(data):
        data["assets"]["msh"] = str(msh)
        data["mesh"]["nodes"] = observed["nodes"]
        data["counts"]["nodes"] = len(observed["nodes"]["ids"])
        owners = {(dim, entity["backend_tag"]): entity["uuid"]
                  for dim, entities in ((2, data["surfaces"]), (3, data["volumes"])) for entity in entities}
        blocks = []
        for block in observed["element_blocks"]:
            if block["dimension"] >= 2:
                block = dict(block)
                block["entity_uuid"] = owners[(block["dimension"], block.pop("backend_tag"))]
                blocks.append(block)
        data["mesh"]["element_blocks"] = blocks
        for dimension, entities in ((2, data["surfaces"]), (3, data["volumes"])):
            for entity in entities:
                entity["facet_ids" if dimension == 2 else "element_ids"] = [
                    identifier for block in blocks if block["entity_uuid"] == entity["uuid"] for identifier in block["ids"]]
    metadata = _write_altered_metadata(result, tmp_path, update)
    candidate = read_mesh_candidate(metadata)
    assert any(item.order == 2 and not item.supported for item in candidate.inventory)
    assert len(candidate.cells) == sum(item.count for item in candidate.inventory)
    assert set(candidate.quality.unsupported_ids) == {cell.id for cell in candidate.cells if cell.dimension >= 2}
    with pytest.raises(PrepError) as error:
        candidate.to_native_mesh()
    assert error.value.code == "mesh_quality"
