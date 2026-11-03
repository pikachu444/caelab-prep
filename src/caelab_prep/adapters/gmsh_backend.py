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


def _surface_parameters(mesh_size, *, length_unit, element_order=1, smoothing_iterations=2,
                        relaxation=.5, minimum_scaled_jacobian=.5, maximum_edge_aspect_ratio=4.,
                        volume_optimizer="netgen"):
    values = {}
    for name, raw in (("mesh_size", mesh_size), ("relaxation", relaxation),
                      ("minimum_scaled_jacobian", minimum_scaled_jacobian),
                      ("maximum_edge_aspect_ratio", maximum_edge_aspect_ratio)):
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise GmshBackendError("invalid_request", f"{name} must be finite") from exc
        if isinstance(raw, bool) or not math.isfinite(value):
            raise GmshBackendError("invalid_request", f"{name} must be finite")
        values[name] = value
    if (length_unit not in ("mm", "cm", "m") or type(element_order) is not int or element_order not in (1, 2)
            or type(smoothing_iterations) is not int or not 0 <= smoothing_iterations <= 100
            or values["mesh_size"] <= 0 or not 0 < values["relaxation"] <= 1
            or not .5 <= values["minimum_scaled_jacobian"] <= 1
            or not 1 <= values["maximum_edge_aspect_ratio"] <= 4
            or volume_optimizer not in ("netgen", "gmsh")):
        raise GmshBackendError("invalid_request", "Invalid surface volume units, order, smoothing or quality targets")
    return {**values, "length_unit": length_unit, "element_order": element_order,
            "smoothing_iterations": smoothing_iterations, "volume_optimizer": volume_optimizer, "dimension": 3}


class GmshBackend:
    def __init__(self, *, timeout: float = 120.0):
        if isinstance(timeout, bool) or not math.isfinite(float(timeout)) or float(timeout) <= 0:
            raise GmshBackendError("invalid_request", "timeout must be finite and positive")
        self.timeout = float(timeout)

    def generate(self, source_path, output_dir, mesh_size, *, dimension=3, cancel_event=None,
                 interface_policy="preserve", local_sizes=None) -> dict:
        """Import generic CAD and produce immutable, candidate geometry/mesh assets.

        ``mesh_size`` is in millimetres for STEP/IGES input (SDK normalization),
        and in the source geometry units for BREP/XAO. Unknown units are reported,
        never silently declared to be millimetres. Output is placed in a new child
        directory so that repeated jobs cannot overwrite earlier candidates.
        Cancellation/timeout terminate and reap the actual worker process.

        ``interface_policy`` is ``preserve`` (keep input topology), ``conformal``
        (fragment a new external multi-solid import before assigning UUIDs), or
        ``independent`` (preflight only: reject any shared topology/nodes; never
        detach or merge entities). Conformal preparation is not performed on
        persisted XAO identities. Already prepared XAO uses ``preserve``.
        ``local_sizes`` maps persisted XAO surface/volume UUIDs to target sizes;
        target refinement includes entity boundaries and may affect neighbours.
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
        if interface_policy not in ("preserve", "conformal", "independent"):
            raise GmshBackendError("invalid_request", "Unknown interface policy")
        if interface_policy == "conformal" and source.suffix.lower() == ".xao":
            raise GmshBackendError("topology_identity", "Use preserve for prepared XAO; conformal preparation requires a fresh external CAD import")
        sizes = {}
        if local_sizes is not None:
            if not isinstance(local_sizes, dict) or local_sizes and source.suffix.lower() != ".xao":
                raise GmshBackendError("invalid_request", "local_sizes requires a mapping of persisted XAO entity UUIDs to sizes")
            for identifier, requested_size in local_sizes.items():
                try:
                    key, value = str(uuid.UUID(identifier)), float(requested_size)
                except (ValueError, TypeError, AttributeError) as exc:
                    raise GmshBackendError("invalid_request", "local_sizes requires valid UUIDs and finite positive sizes") from exc
                if isinstance(requested_size, bool) or not math.isfinite(value) or value <= 0:
                    raise GmshBackendError("invalid_request", "Local mesh size must be finite and positive")
                if value > size:
                    raise GmshBackendError("invalid_request", "Local refinement size cannot exceed the global target size")
                if key in sizes:
                    raise GmshBackendError("invalid_request", "Duplicate local sizing entity")
                sizes[key] = value
        workdir, captured, digest = self._capture(source, output_dir, cancel_event)
        request = {"source": str(captured), "original_source": str(source), "source_sha256": digest,
                   "output_dir": str(workdir), "mesh_size": size, "dimension": int(dimension),
                   "interface_policy": interface_policy, "local_sizes": sizes}
        return self._run(request, workdir, cancel_event)

    def generate_surface_volume(self, source_path, output_dir, mesh_size, *, length_unit,
                                element_order=1, smoothing_iterations=2, relaxation=.5,
                                minimum_scaled_jacobian=.5, maximum_edge_aspect_ratio=4.,
                                volume_optimizer="netgen", cancel_event=None):
        """Capture a closed tri3 MSH and generate an unapplied volume diagnostic.

        A completed job returns ``status=quality_passed|quality_failed``; failed
        target values and every failing cell remain in the output evidence.
        Neither status admits a mesh into a document or qualifies a native or
        solver element. Structural, SDK and serialization failures raise errors.
        """
        parameters = _surface_parameters(mesh_size, length_unit=length_unit, element_order=element_order,
            smoothing_iterations=smoothing_iterations, relaxation=relaxation,
            minimum_scaled_jacobian=minimum_scaled_jacobian, maximum_edge_aspect_ratio=maximum_edge_aspect_ratio,
            volume_optimizer=volume_optimizer)
        source = Path(source_path).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".msh":
            raise GmshBackendError("invalid_request", "Choose a closed triangle surface .msh input")
        workdir, captured, digest = self._capture(source, output_dir, cancel_event)
        request = {**parameters, "source_kind": "closed_tri_surface", "source": str(captured),
                   "original_source": str(source), "source_sha256": digest, "output_dir": str(workdir)}
        result = self._run(request, workdir, cancel_event)
        if result.get("source_kind") != "surface_tet":
            raise GmshBackendError("worker_protocol_error", "Worker returned a different candidate source kind")
        return result

    def _capture(self, source, output_dir, cancel_event):
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
        return workdir, captured, digest

    def _run(self, request, workdir, cancel_event):
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
                      returncode=process.returncode, workdir=str(workdir), stderr=stderr[-8000:],
                      **({"worker_details": error["details"]} if error.get("details") else {}))
        if process.returncode != 0:
            raise GmshBackendError("worker_error", "Worker exited unsuccessfully after returning data",
                                   returncode=process.returncode, workdir=str(workdir))
        result = response.get("result")
        if not isinstance(result, dict) or result.get("schema_version") != 1:
            raise GmshBackendError("worker_protocol_error", "Unsupported worker result schema")
        return result
