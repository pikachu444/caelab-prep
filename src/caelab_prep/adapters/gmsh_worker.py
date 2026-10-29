"""Fresh-process public Gmsh SDK worker. Native logs go to stderr; stdout is JSON.

Example: python -m caelab_prep.adapters.gmsh_worker --source part.step
         --output-dir new-assets --mesh-size 2 --dimension 3

Only this module imports Gmsh, and only while executing a job. See
``gmsh_backend`` for the result schema and identity/units contract.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid


class WorkerFailure(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _uuid(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise WorkerFailure("identity_error", "Malformed persisted CAELab entity identity") from exc


def _identity(gmsh, surfaces, volumes, extension):
    resource_uuid, revision, unit = str(uuid.uuid4()), 1, "unknown"
    by_entity = {}
    anchor = None
    for dim, group in gmsh.model.getPhysicalGroups():
        name = gmsh.model.getPhysicalName(dim, group)
        if not name.startswith("caelab:"):
            continue
        parts = name.split(":")
        members = [int(x) for x in gmsh.model.getEntitiesForPhysicalGroup(dim, group)]
        if len(parts) == 6 and parts[1] == "geometry":
            if anchor is not None:
                raise WorkerFailure("identity_error", "Multiple persisted geometry resource identities")
            resource_uuid = _uuid(parts[2])
            try:
                revision = int(parts[3].removeprefix("r"))
            except ValueError as exc:
                raise WorkerFailure("identity_error", "Invalid geometry revision") from exc
            if revision < 1 or parts[4] != "unit" or parts[5] not in ("mm", "unknown"):
                raise WorkerFailure("identity_error", "Invalid geometry identity metadata")
            unit = parts[5]
            anchor = (dim, group)
        elif len(parts) == 3 and parts[1] in ("surface", "volume"):
            expected = 2 if parts[1] == "surface" else 3
            if dim != expected or len(members) != 1:
                raise WorkerFailure("identity_error", "Persisted identity must reference exactly one entity")
            key = (dim, members[0])
            if key in by_entity:
                raise WorkerFailure("identity_error", "Ambiguous persisted entity identity")
            by_entity[key] = _uuid(parts[2])
    if extension in (".step", ".stp", ".iges", ".igs"):
        unit = "mm"
    uuids = list(by_entity.values())
    if len(set(uuids)) != len(uuids):
        raise WorkerFailure("identity_error", "One UUID refers to multiple geometry entities")
    for dim, tag in [(2, x) for x in surfaces] + [(3, x) for x in volumes]:
        key = (dim, tag)
        if key not in by_entity:
            entity_uuid = str(uuid.uuid4())
            by_entity[key] = entity_uuid
            kind = "surface" if dim == 2 else "volume"
            group = gmsh.model.addPhysicalGroup(dim, [tag])
            gmsh.model.setPhysicalName(dim, group, f"caelab:{kind}:{entity_uuid}")
    if anchor is None:
        dim, members = (3, volumes) if volumes else (2, surfaces)
        group = gmsh.model.addPhysicalGroup(dim, members)
        gmsh.model.setPhysicalName(dim, group, f"caelab:geometry:{resource_uuid}:r{revision}:unit:{unit}")
    return resource_uuid, revision, unit, by_entity


def generate(request):
    source = Path(request["source"]).resolve()
    out = Path(request["output_dir"]).resolve()
    size = float(request["mesh_size"])
    dimension = request["dimension"]
    if not math.isfinite(size) or size <= 0 or dimension not in (2, 3):
        raise WorkerFailure("invalid_request", "Invalid mesh size or dimension")
    if not source.is_file():
        raise WorkerFailure("invalid_request", "CAD input does not exist")
    if source.suffix.lower() not in {".step", ".stp", ".brep", ".brp", ".iges", ".igs", ".xao"}:
        raise WorkerFailure("invalid_request", "Unsupported CAD input format")
    out.mkdir(parents=True, exist_ok=True)
    # Direct CLI invocation also refuses to overwrite existing asset files.
    for name in ("geometry.xao", "mesh.msh", "metadata.json"):
        if (out / name).exists():
            raise WorkerFailure("invalid_request", f"Output asset already exists: {name}")
    try:
        import gmsh
    except Exception as exc:
        raise WorkerFailure("dependency_error", f"Gmsh SDK or its native dependencies are unavailable: {exc}") from exc
    if not getattr(gmsh, "libpath", None):
        raise WorkerFailure("dependency_error", "Gmsh Python module is present but its native shared library was not found")
    try:
        try:
            gmsh.initialize(interruptible=False)
        except (AttributeError, OSError) as exc:
            raise WorkerFailure("dependency_error", f"Gmsh native library cannot initialize: {exc}") from exc
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        gmsh.option.setNumber("Mesh.MeshSizeMin", size)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.option.setNumber("Mesh.SaveAll", 1)
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.model.add("caelab-cad")
        if source.suffix.lower() == ".xao":
            gmsh.open(str(source))
        else:
            gmsh.model.occ.importShapes(str(source))
        gmsh.model.occ.synchronize()
        surface_tags = [int(tag) for _, tag in gmsh.model.getEntities(2)]
        volume_tags = [int(tag) for _, tag in gmsh.model.getEntities(3)]
        if not surface_tags or dimension == 3 and not volume_tags:
            raise WorkerFailure("geometry_error", "Input does not contain geometry suitable for the requested mesh dimension")
        resource_uuid, revision, unit, entity_uuids = _identity(gmsh, surface_tags, volume_tags, source.suffix.lower())
        gmsh.model.mesh.generate(dimension)
        node_ids, xyz, _ = gmsh.model.mesh.getNodes()
        if not len(node_ids):
            raise WorkerFailure("mesh_error", "Gmsh produced no nodes")
        blocks = []
        for dim, tags in [(2, surface_tags), (3, volume_tags)]:
            for tag in tags:
                types, ids_list, connectivity_list = gmsh.model.mesh.getElements(dim, tag)
                for typ, ids, conn in zip(types, ids_list, connectivity_list):
                    name, _, order, count, _, _ = gmsh.model.mesh.getElementProperties(int(typ))
                    flat = [int(x) for x in conn]
                    blocks.append({"dimension": dim, "entity_uuid": entity_uuids[(dim, tag)],
                                   "element_type": int(typ), "element_name": name, "order": int(order),
                                   "nodes_per_element": int(count), "ids": [int(x) for x in ids],
                                   "connectivity": [flat[i:i+count] for i in range(0, len(flat), count)]})
        if not any(b["dimension"] == dimension and b["ids"] for b in blocks):
            raise WorkerFailure("mesh_error", "No elements generated for the requested dimension")
        by_uuid = {}
        for block in blocks:
            by_uuid.setdefault(block["entity_uuid"], []).extend(block["ids"])
        orientations = {tag: [] for tag in surface_tags}
        volumes = []
        for tag in volume_tags:
            boundaries = gmsh.model.getBoundary([(3, tag)], combined=False, oriented=True)
            surface_ids = []
            for dim, signed in boundaries:
                if dim == 2:
                    surface_ids.append(entity_uuids[(2, abs(signed))])
                    orientations[abs(signed)].append({"volume_uuid": entity_uuids[(3, tag)],
                                                       "sign": 1 if signed > 0 else -1})
            volumes.append({"uuid": entity_uuids[(3, tag)], "backend_tag": tag,
                            "physical_group_name": f"caelab:volume:{entity_uuids[(3, tag)]}",
                            "bbox": [float(x) for x in gmsh.model.getBoundingBox(3, tag)],
                            "volume": float(gmsh.model.occ.getMass(3, tag)),
                            "surface_uuids": surface_ids, "element_ids": by_uuid.get(entity_uuids[(3, tag)], [])})
        surfaces = []
        for tag in surface_tags:
            selected, _, _ = gmsh.model.mesh.getNodes(2, tag, includeBoundary=True)
            entity_uuid = entity_uuids[(2, tag)]
            surfaces.append({"uuid": entity_uuid, "backend_tag": tag,
                             "physical_group_name": f"caelab:surface:{entity_uuid}",
                             "bbox": [float(x) for x in gmsh.model.getBoundingBox(2, tag)],
                             "area": float(gmsh.model.occ.getMass(2, tag)),
                             "center": [float(x) for x in gmsh.model.occ.getCenterOfMass(2, tag)],
                             "geometry_type": gmsh.model.getType(2, tag),
                             "node_ids": sorted({int(x) for x in selected}),
                             "facet_ids": by_uuid.get(entity_uuid, []),
                             "orientation_by_volume": orientations[tag]})
        xao, msh, metadata = out / "geometry.xao", out / "mesh.msh", out / "metadata.json"
        gmsh.write(str(xao))
        gmsh.write(str(msh))
        coordinates = [float(x) for x in xyz]
        diagnostics = []
        if unit == "unknown":
            diagnostics.append({"severity": "warning", "code": "unknown_length_unit",
                                "message": "BREP/external XAO units are not declared; the caller must assign consistent units before solver export."})
        result = {
            "schema_version": 1, "backend": {"name": "gmsh", "version": gmsh.__version__},
            "geometry_resource_uuid": resource_uuid, "geometry_revision": revision,
            "mesh_uuid": str(uuid.uuid4()), "mesh_revision": 1, "length_unit": unit,
            "source": {"path": request.get("original_source", str(source)),
                       "sha256": request.get("source_sha256") or hashlib.sha256(source.read_bytes()).hexdigest(),
                       "captured_path": str(source)},
            "assets": {"xao": str(xao), "msh": str(msh), "metadata": str(metadata)},
            "surfaces": surfaces, "volumes": volumes,
            "mesh": {"nodes": {"ids": [int(x) for x in node_ids],
                               "coordinates": [coordinates[i:i+3] for i in range(0, len(coordinates), 3)]},
                     "element_blocks": blocks},
            "counts": {"nodes": len(node_ids), "elements": sum(len(b["ids"]) for b in blocks if b["dimension"] == dimension),
                       "surface_facets": sum(len(b["ids"]) for b in blocks if b["dimension"] == 2),
                       "surfaces": len(surfaces), "volumes": len(volumes)},
            "diagnostics": diagnostics,
            "identity_policy": "XAO named groups preserve geometry/entity UUIDs within this resource; backend tags and node IDs are session/mesh-local. New external CAD imports get new identities. No automatic cross-revision remapping is performed.",
        }
        temporary = metadata.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(metadata)
        return result
    except WorkerFailure:
        raise
    except Exception as exc:
        raise WorkerFailure("sdk_error", str(exc)) from exc
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--mesh-size", type=float)
    parser.add_argument("--dimension", type=int, default=3)
    args = parser.parse_args(argv)
    if args.request:
        try:
            request = json.loads(args.request.read_text(encoding="utf-8"))
        except Exception as exc:
            request = None
            failure = {"code": "invalid_request", "message": str(exc)}
    elif args.source is not None and args.output_dir is not None and args.mesh_size is not None:
        request = {"source": str(args.source), "output_dir": str(args.output_dir),
                   "mesh_size": args.mesh_size, "dimension": args.dimension}
    else:
        parser.error("provide --request or --source, --output-dir and --mesh-size")
    # Native libraries can write directly to fd 1: redirect it, not only Python print.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    with contextlib.redirect_stdout(sys.stderr):
        try:
            if request is None:
                response = {"ok": False, "error": failure}
            else:
                response = {"ok": True, "result": generate(request)}
        except WorkerFailure as exc:
            response = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
        except Exception as exc:
            response = {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}}
        protocol.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
        protocol.flush()
        protocol.close()
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
