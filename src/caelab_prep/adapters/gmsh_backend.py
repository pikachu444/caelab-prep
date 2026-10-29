"""Process-isolated adapter for the public Gmsh SDK.

``generate`` returns a candidate resource, not an applied CAE model. Schema v1::

    {
      "schema_version": 1, "backend": {"name": "gmsh", "version": ...},
      "geometry_resource_uuid": UUID, "geometry_revision": 1,
      "mesh_uuid": UUID, "mesh_revision": 1, "length_unit": "mm" | "unknown",
      "source": {"path": ..., "sha256": ..., "captured_path": ...},
      "assets": {"xao": absolute_path, "msh": absolute_path,
                 "metadata": absolute_path},
      "surfaces": [{"uuid": UUID, "backend_tag": int,
          "physical_group_name": ..., "bbox": [xmin, ymin, zmin, xmax, ymax, zmax],
          "area": float, "center": [x,y,z], "node_ids": [...], "facet_ids": [...],
          "orientation_by_volume": [{"volume_uuid": UUID, "sign": -1 | 1}]}],
      "volumes": [{"uuid": UUID, "backend_tag": int, "bbox": [...],
                   "volume": float, "surface_uuids": [...], "element_ids": [...]}],
      "mesh": {"nodes": {"ids": [...], "coordinates": [[x,y,z], ...]},
               "element_blocks": [{"dimension": 2 | 3, "entity_uuid": UUID,
                 "element_type": int, "element_name": str, "order": int,
                 "nodes_per_element": int, "ids": [...], "connectivity": [[...]]}]},
      "counts": {"nodes": int, "elements": int, "surface_facets": int, ...},
      "diagnostics": [{"severity": ..., "code": ..., "message": ...}],
      "identity_policy": ...
    }

Entity UUIDs are persisted in named XAO physical groups. A fresh external CAD
import receives a new geometry resource; no cross-import topological matching is
claimed. Gmsh tags and remeshed node IDs are never persistent application IDs.
The files do not contain CAE material/load definitions. Importing this module
does not import Gmsh or load its native shared library.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
import uuid


class GmshBackendError(RuntimeError):
    """Structured failure from validation, process transport or the native SDK."""

    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


class DependencyError(GmshBackendError):
    pass


class CancelledError(GmshBackendError):
    pass


class BackendTimeoutError(GmshBackendError):
    pass


_FORMATS = {".step", ".stp", ".brep", ".brp", ".iges", ".igs", ".xao"}


def _stop(process: subprocess.Popen) -> tuple[str, str]:
    if process.poll() is None:
        process.terminate()
    try:
        return process.communicate(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate(timeout=3)


class GmshBackend:
    def __init__(self, *, timeout: float = 120.0):
        if isinstance(timeout, bool) or not math.isfinite(float(timeout)) or float(timeout) <= 0:
            raise GmshBackendError("invalid_request", "timeout must be finite and positive")
        self.timeout = float(timeout)

    def generate(self, source_path, output_dir, mesh_size, *, dimension=3, cancel_event=None) -> dict:
        """Import generic CAD and produce immutable, candidate geometry/mesh assets.

        ``mesh_size`` is in millimetres for STEP/IGES input (SDK normalization),
        and in the source geometry units for BREP/XAO. Unknown units are reported,
        never silently declared to be millimetres. Output is placed in a new child
        directory so that repeated jobs cannot overwrite earlier candidates.
        Cancellation/timeout terminate and reap the actual worker process.
        """
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise GmshBackendError("invalid_request", "CAD input does not exist", source=str(source))
        if source.suffix.lower() not in _FORMATS:
            raise GmshBackendError("invalid_request", "Unsupported CAD input format", source=str(source))
        if isinstance(dimension, bool) or dimension not in (2, 3):
            raise GmshBackendError("invalid_request", "dimension must be 2 or 3")
        try:
            size = float(mesh_size)
        except (TypeError, ValueError) as exc:
            raise GmshBackendError("invalid_request", "mesh_size must be finite and positive") from exc
        if isinstance(mesh_size, bool) or not math.isfinite(size) or size <= 0:
            raise GmshBackendError("invalid_request", "mesh_size must be finite and positive")
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError("cancelled", "Meshing cancelled before starting")
        destination = Path(output_dir).expanduser().resolve()
        if destination.exists() and not destination.is_dir():
            raise GmshBackendError("invalid_request", "output_dir is not a directory")
        destination.mkdir(parents=True, exist_ok=True)
        workdir = destination / ("gmsh-" + str(uuid.uuid4()))
        workdir.mkdir()
        captured = workdir / ("input" + source.suffix.lower())
        shutil.copyfile(source, captured)
        with captured.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        request = {"source": str(captured), "original_source": str(source), "source_sha256": digest,
                   "output_dir": str(workdir), "mesh_size": size, "dimension": int(dimension)}
        request_file = workdir / "request.json"
        request_file.write_text(json.dumps(request), encoding="utf-8")
        env = os.environ.copy()
        # Also support running a source checkout without globally installing it.
        package_parent = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_parent, env.get("PYTHONPATH", "")]))
        process = subprocess.Popen(
            [sys.executable, "-m", "caelab_prep.adapters.gmsh_worker", "--request", str(request_file)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            env=env, cwd=workdir,
        )
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    _, stderr = _stop(process)
                    raise CancelledError("cancelled", "Meshing cancelled", pid=process.pid,
                                         returncode=process.returncode, workdir=str(workdir), stderr=stderr[-8000:])
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _, stderr = _stop(process)
                    raise BackendTimeoutError("timeout", "Gmsh worker exceeded timeout", pid=process.pid,
                                              returncode=process.returncode, workdir=str(workdir), stderr=stderr[-8000:])
                try:
                    stdout, stderr = process.communicate(timeout=min(remaining, 0.05))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            if process.poll() is None:
                _stop(process)
            raise
        (workdir / "worker.log").write_text(stderr, encoding="utf-8")
        try:
            response = json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise GmshBackendError("worker_protocol_error", "Gmsh worker did not return a JSON result",
                                   returncode=process.returncode, workdir=str(workdir), stderr=stderr[-8000:]) from exc
        if not response.get("ok"):
            error = response.get("error", {})
            cls = DependencyError if error.get("code") == "dependency_error" else GmshBackendError
            raise cls(error.get("code", "worker_error"), error.get("message", "Gmsh worker failed"),
                      returncode=process.returncode, workdir=str(workdir), stderr=stderr[-8000:])
        if process.returncode != 0:
            raise GmshBackendError("worker_error", "Worker exited unsuccessfully after returning data",
                                   returncode=process.returncode, workdir=str(workdir))
        result = response.get("result")
        if not isinstance(result, dict) or result.get("schema_version") != 1:
            raise GmshBackendError("worker_protocol_error", "Unsupported worker result schema")
        return result
