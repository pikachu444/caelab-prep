"""Real SDK integration checks; CAD generation is confined to test code."""
from __future__ import annotations

import json
from itertools import combinations
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
from statistics import median

import pytest

from caelab_prep.adapters.gmsh_backend import (
    BackendTimeoutError, CancelledError, DependencyError, GmshBackend, GmshBackendError,
)


def require_sdk():
    result = subprocess.run([sys.executable, "-c", "import gmsh;gmsh.initialize(interruptible=False);gmsh.finalize()"],
                            capture_output=True, text=True)
    if result.returncode:
        pytest.skip("Gmsh SDK/native dependencies unavailable: " + result.stderr[-300:])


@pytest.fixture(params=["plate-with-hole", "cylinder"])
def cad(tmp_path, request):
    require_sdk()
    pytest.importorskip("OCP")
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.BRepTools import BRepTools
    if request.param == "plate-with-hole":
        shape = BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(12, 8, 3).Shape(),
                               BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(6, 4, -1), gp_Dir(0, 0, 1)), 1, 5).Shape()).Shape()
    else:
        shape = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(-2, 3, 1), gp_Dir(0, 0, 1)), 3, 7).Shape()
    path = tmp_path / (request.param + ".step")
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert int(writer.Write(str(path))) == 1
    BRepTools.Write_s(shape, str(path.with_suffix(".brep")))
    return path


def test_adapter_import_does_not_load_native_sdk():
    result = subprocess.run([sys.executable, "-c", "import sys;import caelab_prep.adapters.gmsh_backend;assert 'gmsh' not in sys.modules"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("size", [0, -1, float("nan"), float("inf"), True])
def test_invalid_size_rejected_before_job(tmp_path, size):
    source = tmp_path / "part.step"
    source.write_text("not opened because request is invalid")
    with pytest.raises(GmshBackendError) as error:
        GmshBackend().generate(source, tmp_path / "outputs", size)
    assert error.value.code == "invalid_request"
    assert not (tmp_path / "outputs").exists()


def test_real_cad_mesh_assets_and_xao_identity(cad, tmp_path):
    backend = GmshBackend()
    first = backend.generate(cad, tmp_path / "assets", 1.8)
    assert first["counts"]["nodes"] > 0
    assert first["counts"]["elements"] > 0
    assert first["length_unit"] == "mm"
    assert len(first["volumes"]) == 1
    assert first["surfaces"]
    node_ids = set(first["mesh"]["nodes"]["ids"])
    for surface in first["surfaces"]:
        assert surface["node_ids"] and set(surface["node_ids"]) <= node_ids
        assert surface["facet_ids"]
        assert surface["orientation_by_volume"]
    for path in first["assets"].values():
        assert Path(path).is_file() and Path(path).stat().st_size > 0
    persisted = json.loads(Path(first["assets"]["metadata"]).read_text())
    assert persisted == first
    second = backend.generate(first["assets"]["xao"], tmp_path / "assets", 1.2)
    assert first["geometry_resource_uuid"] == second["geometry_resource_uuid"]
    assert first["geometry_revision"] == second["geometry_revision"]
    assert {s["uuid"] for s in first["surfaces"]} == {s["uuid"] for s in second["surfaces"]}
    assert {v["uuid"] for v in first["volumes"]} == {v["uuid"] for v in second["volumes"]}
    assert second["length_unit"] == "mm"
    assert first["mesh_uuid"] != second["mesh_uuid"]
    assert first["counts"]["nodes"] != second["counts"]["nodes"]
    assert first["assets"]["xao"] != second["assets"]["xao"]
    independent = backend.generate(cad, tmp_path / "assets", 1.8)
    assert independent["geometry_resource_uuid"] != first["geometry_resource_uuid"]


def test_brep_units_remain_unknown(cad, tmp_path):
    result = GmshBackend().generate(cad.with_suffix(".brep"), tmp_path / "assets", 2.0)
    assert result["length_unit"] == "unknown"
    assert any(d["code"] == "unknown_length_unit" for d in result["diagnostics"])


def test_missing_sdk_is_structured_error(cad, tmp_path, monkeypatch):
    import caelab_prep.adapters.gmsh_backend as module
    monkeypatch.setenv("PYTHONPATH", str(Path(module.__file__).resolve().parents[2]))
    # Run the actual worker without installed site packages, independently of
    # whether the developer normally has the optional Gmsh SDK installed.
    real_popen = subprocess.Popen
    def isolated_python(command, *args, **kwargs):
        return real_popen([command[0], "-S", *command[1:]], *args, **kwargs)
    monkeypatch.setattr(module.subprocess, "Popen", isolated_python)
    with pytest.raises(DependencyError) as error:
        GmshBackend().generate(cad, tmp_path / "assets", 1.8)
    assert error.value.code == "dependency_error"


def test_real_worker_timeout_is_reaped(cad, tmp_path):
    with pytest.raises(BackendTimeoutError) as error:
        GmshBackend(timeout=0.001).generate(cad, tmp_path / "assets", 1.0)
    assert error.value.details["returncode"] is not None
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(error.value.details["pid"], 0)


def test_real_worker_cancel_is_reaped(cad, tmp_path):
    event = threading.Event()
    timer = threading.Timer(0.02, event.set)
    timer.start()
    try:
        with pytest.raises(CancelledError) as error:
            GmshBackend().generate(cad, tmp_path / "assets", 1.0, cancel_event=event)
        assert error.value.details["returncode"] is not None
        if os.name == "posix":
            with pytest.raises(ProcessLookupError):
                os.kill(error.value.details["pid"], 0)
    finally:
        timer.cancel()


def _touching_cad(directory, kind):
    """Fixed normal cases, two harder/holdout cases, and one unsupported input."""
    require_sdk()
    pytest.importorskip("OCP")
    from OCP.BRep import BRep_Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TopoDS import TopoDS_Compound
    if kind == "curved-boundary":
        first = BRepPrimAPI_MakeCylinder(2, 2).Shape()
        second = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 2), gp_Dir(0, 0, 1)), 2, 3).Shape()
    else:
        first = BRepPrimAPI_MakeBox(4, 3, 2).Shape()
        location, dimensions = {
            "full-x": ((4, 0, 0), (4, 3, 2)),
            "full-y": ((0, 3, 0), (4, 3, 2)),
            "full-z": ((0, 0, 2), (4, 3, 2)),
            "partial-face": ((4, 1, .5), (2, 1, 1)),
            "overlap": ((2, 0, 0), (4, 3, 2)),
        }[kind]
        second = BRepPrimAPI_MakeBox(gp_Pnt(*location), *dimensions).Shape()
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    builder.Add(compound, first)
    builder.Add(compound, second)
    path = directory / (kind + ".step")
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    assert int(writer.Write(str(path))) == 1
    return path


def _part_nodes(result, volume):
    return {node for block in result["mesh"]["element_blocks"] if block["entity_uuid"] == volume["uuid"]
            for conn in block["connectivity"] for node in conn}


@pytest.mark.parametrize("kind", ["full-x", "full-y", "full-z", "partial-face", "curved-boundary", "overlap"])
def test_conformal_recipe_fixed_cad_matrix(tmp_path, kind):
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    source = _touching_cad(tmp_path, kind)
    if kind == "overlap":
        with pytest.raises(GmshBackendError) as error:
            GmshBackend().generate(source, tmp_path / "assets", 1., interface_policy="conformal")
        assert error.value.code == "topology_mapping"
        return
    result = GmshBackend().generate(source, tmp_path / "assets", 1., interface_policy="conformal")
    candidate = read_mesh_candidate(result)
    assert candidate.quality.passed, candidate.quality.problem_ids
    assert len(candidate.to_native_mesh().parts) == 2
    assert result["recipe"]["topology_preparation"]["operation"] == "occ.fragment"
    mapping = result["recipe"]["topology_preparation"]["source_volume_map"]
    assert len(mapping) == len({item["backend_tag"] for item in mapping}) == 2
    assert result["sdk_error_count"] == 0
    surfaces = [s for s in result["surfaces"] if len(s["orientation_by_volume"]) == 2]
    assert len(surfaces) == 1
    surface = surfaces[0]
    assert {item["sign"] for item in surface["orientation_by_volume"]} == {-1, 1}
    left, right = result["volumes"]
    common = _part_nodes(result, left) & _part_nodes(result, right)
    assert common == set(surface["node_ids"])
    assert result["interface_checks"][0]["shared_node_count"] == len(common) > 0
    facets = {tuple(sorted(conn)) for block in result["mesh"]["element_blocks"]
              if block["entity_uuid"] == surface["uuid"] for conn in block["connectivity"]}
    for volume in (left, right):
        tetra_faces = {tuple(sorted(face)) for block in result["mesh"]["element_blocks"]
                       if block["entity_uuid"] == volume["uuid"]
                       for conn in block["connectivity"] for face in combinations(conn, 3)}
        assert facets <= tetra_faces
    coordinates = [tuple(round(value, 9) for value in point) for point in result["mesh"]["nodes"]["coordinates"]]
    assert len(coordinates) == len(set(coordinates)), "Conformal interface must not duplicate coincident node IDs"


def test_independent_is_preflight_and_keeps_coincident_interfaces_disconnected(tmp_path):
    source = _touching_cad(tmp_path, "full-x")
    backend = GmshBackend()
    independent = backend.generate(source, tmp_path / "assets", 1., interface_policy="independent")
    left, right = independent["volumes"]
    assert not _part_nodes(independent, left) & _part_nodes(independent, right)
    coordinates = dict(zip(independent["mesh"]["nodes"]["ids"], independent["mesh"]["nodes"]["coordinates"]))
    by_part = [{tuple(round(value, 9) for value in coordinates[node]) for node in _part_nodes(independent, volume)}
               for volume in (left, right)]
    assert by_part[0] & by_part[1], "Coincident geometry must remain independently numbered"
    assert independent["recipe"]["independent_is_preflight_only"]
    shared = backend.generate(source, tmp_path / "assets", 1., interface_policy="conformal")
    with pytest.raises(GmshBackendError) as error:
        backend.generate(shared["assets"]["xao"], tmp_path / "assets", 1., interface_policy="independent")
    assert error.value.code == "shared_topology"
    with pytest.raises(GmshBackendError) as error:
        backend.generate(shared["assets"]["xao"], tmp_path / "assets", 1., interface_policy="conformal")
    assert error.value.code == "topology_identity"


def _edge_median(result, entity_uuid):
    coordinates = dict(zip(result["mesh"]["nodes"]["ids"], result["mesh"]["nodes"]["coordinates"]))
    return median(math.dist(coordinates[a], coordinates[b]) for block in result["mesh"]["element_blocks"]
                  if block["entity_uuid"] == entity_uuid for conn in block["connectivity"] for a, b in combinations(conn, 2))


@pytest.mark.parametrize("kind", ["full-x", "full-y", "full-z", "partial-face", "curved-boundary"])
@pytest.mark.parametrize("dimension", [2, 3])
def test_entity_local_size_changes_actual_target_density_preserving_uuid_and_interface(tmp_path, dimension, kind):
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    source = _touching_cad(tmp_path, kind)
    backend = GmshBackend()
    baseline = backend.generate(source, tmp_path / "assets", 1.4, interface_policy="conformal")
    target = (next(s for s in baseline["surfaces"] if len(s["orientation_by_volume"]) == 2)
              if dimension == 2 else baseline["volumes"][0])
    refined = backend.generate(baseline["assets"]["xao"], tmp_path / "assets", 1.4,
                               local_sizes={target["uuid"]: .45})
    assert refined["geometry_resource_uuid"] == baseline["geometry_resource_uuid"]
    assert {s["uuid"] for s in refined["surfaces"]} == {s["uuid"] for s in baseline["surfaces"]}
    assert {v["uuid"] for v in refined["volumes"]} == {v["uuid"] for v in baseline["volumes"]}
    before_count = sum(len(block["ids"]) for block in baseline["mesh"]["element_blocks"] if block["entity_uuid"] == target["uuid"])
    after_count = sum(len(block["ids"]) for block in refined["mesh"]["element_blocks"] if block["entity_uuid"] == target["uuid"])
    assert after_count > 2 * before_count
    assert _edge_median(refined, target["uuid"]) < .75 * _edge_median(baseline, target["uuid"])
    assert refined["recipe"]["local_sizes"][0]["entity_uuid"] == target["uuid"]
    assert refined["interface_checks"][0]["shared_node_count"] > 0
    assert refined["sdk_error_count"] == 0
    candidate = read_mesh_candidate(refined)
    assert candidate.quality.passed, candidate.quality.problem_ids
    assert len(candidate.to_native_mesh().parts) == 2


def test_stale_local_reference_is_rejected_by_worker(tmp_path):
    source = _touching_cad(tmp_path, "full-x")
    backend = GmshBackend()
    initial = backend.generate(source, tmp_path / "assets", 1.)
    with pytest.raises(GmshBackendError) as error:
        backend.generate(initial["assets"]["xao"], tmp_path / "assets", 1.,
                         local_sizes={"00000000-0000-4000-8000-000000000001": .5})
    assert error.value.code == "sizing_reference"
