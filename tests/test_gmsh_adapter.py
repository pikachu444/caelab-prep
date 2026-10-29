"""Real SDK integration checks; CAD generation is confined to test code."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading

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
