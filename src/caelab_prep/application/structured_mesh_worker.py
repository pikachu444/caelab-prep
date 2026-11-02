"""Isolated Gmsh compiler for explicit planar quad patches and straight hex sweeps.

Run with ``python -m caelab_prep.application.structured_mesh_worker input.json output_dir``.
The caller owns timeout/cancellation and subsequent candidate admission. This
worker writes an actual MSH plus a complete SDK receipt; it creates no CAD/XAO
provenance and never imports evaluation scripts or changes a model document.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

from ..cae_core.errors import PrepError
from .structured_geometry import MAX_RECIPE_BYTES, validate_recipe

SDK_VERSION = "4.15.2"


def _check(condition, message, code="structured_mesh_inventory"):
    if not condition:
        raise PrepError(code, message)


def _error(error):
    return {"code": getattr(error, "code", "structured_mesh_failed"),
            "message": str(error), "details": getattr(error, "details", {})}


def _object(pairs):
    result = {}
    for key, value in pairs:
        _check(key not in result, "Repeated JSON recipe field: " + key, "invalid_recipe")
        result[key] = value
    return result


def _constant(value):
    raise PrepError("invalid_recipe", "Recipe numbers must be finite: " + value)


def _build_geometry(gmsh, spec):
    """Shared topology is built only from explicit shared vertex IDs."""
    geo = gmsh.model.geo
    if "patches" in spec:
        vertices = {key: geo.addPoint(*point) for key, point in spec["vertices"].items()}
        edges, faces = {}, []
        for patch in spec["patches"]:
            ids, boundary = patch["corners"], []
            for index in range(4):
                a, b = ids[index], ids[(index + 1) % 4]
                key = tuple(sorted((a, b)))
                if key not in edges:
                    tag = geo.addLine(vertices[key[0]], vertices[key[1]])
                    geo.mesh.setTransfiniteCurve(tag, patch["divisions"][index % 2] + 1)
                    edges[key] = tag
                boundary.append(edges[key] if (a, b) == key else -edges[key])
            face = geo.addPlaneSurface([geo.addCurveLoop(boundary)])
            geo.mesh.setTransfiniteSurface(face, "Left", [vertices[key] for key in ids])
            geo.mesh.setRecombine(2, face)
            faces.append(face)
        names = [patch["id"] for patch in spec["patches"]]
    else:
        vertices = [geo.addPoint(*point) for point in spec["corners"]]
        edges = [geo.addLine(vertices[index], vertices[(index + 1) % 4]) for index in range(4)]
        for index, edge in enumerate(edges):
            geo.mesh.setTransfiniteCurve(edge, spec["divisions"][index % 2] + 1)
        face = geo.addPlaneSurface([geo.addCurveLoop(edges)])
        geo.mesh.setTransfiniteSurface(face, "Left", vertices)
        geo.mesh.setRecombine(2, face)
        faces, names = [face], [spec.get("name") or "explicit_source_1"]
    _check(len(set(names)) == len(names) and all(names), "Source patch names must be distinct and nonempty", "invalid_recipe")
    if spec["mode"] == "quad":
        entities = faces
    else:
        output = geo.extrude([(2, face) for face in faces], *spec["vector"], [spec["layers"]], [], True)
        entities = [int(tag) for dimension, tag in output if dimension == 3]
        _check(len(entities) == len(faces), "Extrusion did not produce one volume per source patch")
    geo.synchronize()
    if spec["mode"] == "hex":
        for face, entity in zip(faces, entities):
            boundary = {abs(int(tag)) for dimension, tag in gmsh.model.getBoundary([(3, entity)], oriented=False) if dimension == 2}
            _check(face in boundary, "Extruded volume order does not match the explicit source patch order")
    dimension = 2 if spec["mode"] == "quad" else 3
    for index, (entity, name) in enumerate(zip(entities, names)):
        gmsh.model.addPhysicalGroup(dimension, [entity], 110 + index, name)
    return names


def _inventory(gmsh, dimension):
    node_ids, coordinates, _ = gmsh.model.mesh.getNodes()
    ids = [int(value) for value in node_ids]
    _check(len(ids) == len(set(ids)) and all(value > 0 for value in ids), "SDK node IDs must be positive and unique")
    _check(len(coordinates) == 3 * len(ids), "Incomplete SDK coordinate inventory")
    nodes = {identifier: tuple(float(value) for value in coordinates[3 * index:3 * index + 3])
             for index, identifier in enumerate(ids)}
    _check(all(math.isfinite(value) for point in nodes.values() for value in point), "Nonfinite SDK coordinate")
    inventory, elements, top_ids, active_nodes = [], {}, set(), set()
    for kind, element_ids, connectivity in zip(*gmsh.model.mesh.getElements()):
        kind = int(kind)
        name, cell_dimension, order, arity, _, _ = gmsh.model.mesh.getElementProperties(kind)
        cell_dimension, order, arity = int(cell_dimension), int(order), int(arity)
        member_ids = [int(value) for value in element_ids]
        _check(0 <= cell_dimension <= dimension and arity > 0, "Unexpected SDK element dimension or arity")
        _check(len(connectivity) == arity * len(member_ids), "Incomplete SDK element connectivity")
        for index, identifier in enumerate(member_ids):
            connection = tuple(int(value) for value in connectivity[arity * index:arity * (index + 1)])
            _check(identifier > 0 and identifier not in elements, "Duplicate or invalid SDK element ID")
            _check(all(value in nodes for value in connection), "SDK connectivity references a missing node")
            elements[identifier] = (kind, connection)
            if cell_dimension == dimension:
                top_ids.add(identifier)
                active_nodes.update(connection)
        inventory.append({"type": kind, "dimension": cell_dimension, "order": order, "arity": arity,
                          "name": name, "count": len(member_ids), "element_ids": sorted(member_ids)})
    groups = []
    for group_dimension, tag in sorted(gmsh.model.getPhysicalGroups()):
        group_dimension, tag = int(group_dimension), int(tag)
        entities = sorted(int(value) for value in gmsh.model.getEntitiesForPhysicalGroup(group_dimension, tag))
        group_ids = []
        for entity in entities:
            for values in gmsh.model.mesh.getElements(group_dimension, entity)[1]:
                group_ids.extend(int(value) for value in values)
        _check(len(group_ids) == len(set(group_ids)), "Repeated element in a physical source group")
        groups.append({"dimension": group_dimension, "tag": tag, "name": gmsh.model.getPhysicalName(group_dimension, tag),
                       "entities": entities, "element_ids": sorted(group_ids), "count": len(group_ids)})
    return {"nodes": nodes, "elements": elements, "top_ids": top_ids, "active_nodes": active_nodes,
            "inventory": sorted(inventory, key=lambda item: item["type"]), "physical_groups": groups}


def _inventory_digest(snapshot):
    digest = hashlib.sha256()
    for identifier in sorted(snapshot["nodes"]):
        digest.update(f"n:{identifier}\n".encode())
    for identifier, (kind, connection) in sorted(snapshot["elements"].items()):
        digest.update(f"e:{identifier}:{kind}:{','.join(map(str, connection))}\n".encode())
    digest.update(json.dumps(snapshot["physical_groups"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def _validate_inventory(snapshot, spec, expected, names):
    dimension = expected["dimension"]
    kind, arity = (3, 4) if dimension == 2 else (5, 8)
    top = [item for item in snapshot["inventory"] if item["dimension"] == dimension]
    _check(top and all(item["type"] == kind and item["order"] == 1 and item["arity"] == arity for item in top),
           "Unexpected top-dimensional family; no triangle/tetrahedron fallback is admitted")
    _check(len(snapshot["top_ids"]) == expected["expected_elements"], "Generated element count differs from the recipe")
    _check(len(snapshot["active_nodes"]) == expected["expected_active_nodes"], "Generated active node count differs from the recipe")
    groups = snapshot["physical_groups"]
    _check([(item["dimension"], item["tag"], item["name"]) for item in groups]
           == [(dimension, 110 + index, name) for index, name in enumerate(names)], "Physical source groups changed")
    patches = spec.get("patches", [spec])
    used = set()
    for group, patch in zip(groups, patches):
        count = math.prod(patch["divisions"]) * (spec["layers"] if dimension == 3 else 1)
        members = set(group["element_ids"])
        _check(len(group["entities"]) == 1 and len(members) == count and not used.intersection(members),
               "Physical groups must partition the explicit source patches")
        used.update(members)
    _check(used == snapshot["top_ids"], "Physical groups do not cover the complete top-dimensional inventory")


def _compile(spec, expected, folder, report):
    import gmsh

    report["backend"] = {"name": "gmsh", "version": gmsh.__version__}
    _check(gmsh.__version__ == SDK_VERSION, "Structured recipes require Gmsh " + SDK_VERSION, "unsupported_sdk_version")
    initialized = logging = False
    try:
        gmsh.initialize([], readConfigFiles=False, interruptible=False)
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.logger.start()
        logging = True
        gmsh.model.add("explicit_structured_recipe")
        names = _build_geometry(gmsh, spec)
        dimension = expected["dimension"]
        gmsh.model.mesh.generate(dimension)
        generated = _inventory(gmsh, dimension)
        _validate_inventory(generated, spec, expected, names)
        report["source_patch_names"] = names
        report["generation_inventory"] = generated["inventory"]
        report["generation_inventory_sha256"] = _inventory_digest(generated)
        gmsh.option.setNumber("Mesh.SaveAll", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.option.setNumber("Mesh.Binary", 0)
        mesh_path = folder / "mesh.msh"
        gmsh.write(str(mesh_path))
        gmsh.clear()
        gmsh.open(str(mesh_path))
        reopened = _inventory(gmsh, dimension)
        _validate_inventory(reopened, spec, expected, names)
        inventory_digest = _inventory_digest(reopened)
        _check(inventory_digest == report["generation_inventory_sha256"], "MSH reopen changed the complete SDK inventory or source groups")
        coordinate_error = max(abs(a - b) for identifier, point in generated["nodes"].items()
                               for a, b in zip(point, reopened["nodes"][identifier]))
        tolerance = max(expected["scale"] * 1e-12, 1e-14)
        _check(coordinate_error <= tolerance, "MSH reopen changed generated coordinates")
        report.update(inventory=reopened["inventory"], inventory_sha256=inventory_digest,
            physical_groups=reopened["physical_groups"], reopened=True, coordinate_roundtrip_max_error=coordinate_error,
            counts={"nodes": len(reopened["nodes"]), "active_nodes": len(reopened["active_nodes"]),
                    "elements": len(reopened["top_ids"]), "top_elements": len(reopened["top_ids"]),
                    "all_elements": len(reopened["elements"]),
                    "boundary_elements": len(reopened["elements"]) - len(reopened["top_ids"])},
            mesh_sha256=hashlib.sha256(mesh_path.read_bytes()).hexdigest())
    finally:
        if logging:
            report["log"] = list(gmsh.logger.get())
            gmsh.logger.stop()
        if initialized:
            gmsh.finalize()


def run(input_path, output_dir):
    """Validate first, then compile in the caller-owned isolated worker process."""
    source = Path(input_path)
    raw = source.read_bytes()
    _check(len(raw) <= MAX_RECIPE_BYTES, "Recipe JSON exceeds the 1 MiB input limit", "invalid_recipe")
    try:
        spec = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PrepError("invalid_recipe", "Could not read structured recipe JSON: " + str(exc)) from exc
    _check(isinstance(spec, dict) and spec.get("mode") in ("quad", "hex"),
           "Only explicit quad patches and straight hex sweeps are supported", "unsupported_recipe")
    expected = validate_recipe(spec)
    folder = Path(output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    _check(not any((folder / name).exists() for name in ("mesh.msh", "sdk.json")),
           "Structured worker outputs already exist", "output_exists")
    report = {"schema_version": 1, "status": "running", "backend": {"name": "gmsh", "version": None},
              "source_sha256": hashlib.sha256(raw).hexdigest(), "mesh_sha256": None,
              "kind": spec["mode"], "unit": spec["unit"], "dimension": expected["dimension"],
              "expected_elements": expected["expected_elements"], "expected_active_nodes": expected["expected_active_nodes"],
              "reopened": False, "log": [], "errors": [], "warnings": []}
    started = time.monotonic()
    try:
        _compile(spec, expected, folder, report)
        report["errors"] = [line for line in report["log"] if re.match(r"\s*error\b", line, re.I)]
        report["warnings"] = [line for line in report["log"] if re.match(r"\s*warning\b", line, re.I)]
        _check(not report["errors"] and not report["warnings"], "Gmsh reported errors or warnings; candidate rejected", "sdk_diagnostic")
        report["status"] = "completed"
        return report
    except Exception as exc:
        report.update(status="failed", error=_error(exc))
        raise
    finally:
        report["errors"] = [line for line in report["log"] if re.match(r"\s*error\b", line, re.I)]
        report["warnings"] = [line for line in report["log"] if re.match(r"\s*warning\b", line, re.I)]
        report["seconds"] = time.monotonic() - started
        (folder / "sdk.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    # Native libraries can write to fd 1 directly. Keep it on stderr until the
    # process exits, including native teardown; only this saved fd is protocol.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    with contextlib.redirect_stdout(sys.stderr):
        try:
            _check(len(arguments) == 2, "Usage: structured_mesh_worker input.json output_dir", "invalid_arguments")
            response = {"ok": True, "report": run(arguments[0], arguments[1])}
        except Exception as exc:
            response = {"ok": False, "error": _error(exc)}
        protocol.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
        protocol.flush()
        protocol.close()
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
