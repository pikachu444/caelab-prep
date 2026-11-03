"""Fresh-process public Gmsh SDK worker. Native logs go to stderr; stdout is JSON.

Example: python -m caelab_prep.adapters.gmsh_worker --source part.step
         --output-dir new-assets --mesh-size 2 --dimension 3

Only this module imports Gmsh, and only while executing a job. See
``gmsh_backend`` for the result schema and identity/units contract.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
import math
import os
from pathlib import Path
import re
import sys
import uuid


class WorkerFailure(RuntimeError):
    def __init__(self, code, message, **details):
        self.code = code
        self.details = details
        super().__init__(message)


def _uuid(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise WorkerFailure("identity_error", "Malformed persisted CAELab entity identity") from exc


def _identity(gmsh, surfaces, volumes, extension):
    from .gmsh_backend import _MM_COORDINATE_FORMATS
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
    if extension in _MM_COORDINATE_FORMATS:
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


def _import_cad(gmsh, source):
    """Load the captured CAD into a fresh model; never transform source topology."""
    gmsh.model.add("caelab-cad")
    if source.suffix.lower() == ".xao":
        gmsh.open(str(source))
    else:
        gmsh.model.occ.importShapes(str(source))
    gmsh.model.occ.synchronize()


def _checked_cad_identity(gmsh, surfaces, volumes, extension, expected_unit):
    identity = _identity(gmsh, surfaces, volumes, extension)
    unit = identity[2]
    if expected_unit is not None and unit in ("mm", "cm", "m") and expected_unit != unit:
        raise WorkerFailure("unit_mismatch", "CAD coordinate unit differs from the expected criteria unit",
                            expected_coordinate_length_unit=expected_unit, actual_coordinate_length_unit=unit)
    return identity


def _entity_closure(gmsh, entity):
    """Collect the actual CAD boundary identities, including curves and points."""
    found, pending = set(), [entity]
    while pending:
        item = pending.pop()
        if item[0] == 0:
            continue
        for dim, tag in gmsh.model.getBoundary([item], combined=False, oriented=False):
            child = (int(dim), int(tag))
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def _prepare_interfaces(gmsh, policy, extension):
    """Change fresh geometry only; never guess old face UUIDs after a boolean.

    OCC fragment makes interfaces conformal. Its returned source-to-result map
    must preserve each input volume one-to-one: overlapping/split/merged source
    parts are rejected instead of inventing an ownership mapping.
    """
    originals = [(int(dim), int(tag)) for dim, tag in gmsh.model.getEntities(3)]
    before = {tag: float(gmsh.model.occ.getMass(dim, tag)) for dim, tag in originals}
    mapping = {tag: tag for _, tag in originals}
    operation = "none"
    if policy == "conformal":
        if extension == ".xao":
            raise WorkerFailure("topology_identity", "Prepare conformal topology from fresh CAD, then remesh XAO with preserve")
        if len(originals) > 1:
            output, correspondence = gmsh.model.occ.fragment(originals[:1], originals[1:])
            gmsh.model.occ.synchronize()
            if len(correspondence) != len(originals):
                raise WorkerFailure("topology_mapping", "Fragment did not return complete original volume ownership")
            targets = []
            for original, entities in zip(originals, correspondence):
                volume_tags = [int(tag) for dim, tag in entities if dim == 3]
                if len(volume_tags) != 1:
                    raise WorkerFailure("topology_mapping", "Conformal preparation would split or remove an original volume")
                mapping[original[1]] = volume_tags[0]
                targets.extend(volume_tags)
            if len(set(targets)) != len(originals) or set(targets) != {int(tag) for dim, tag in output if dim == 3}:
                raise WorkerFailure("topology_mapping", "Conformal preparation has ambiguous or merged volume ownership")
            for old, new in mapping.items():
                after = float(gmsh.model.occ.getMass(3, new))
                if before[old] <= 0 or not math.isclose(before[old], after, rel_tol=1e-8, abs_tol=0):
                    raise WorkerFailure("topology_mapping", "Conformal preparation changed an original part volume")
            operation = "occ.fragment"
    volumes = [int(tag) for _, tag in gmsh.model.getEntities(3)]
    closures = {tag: _entity_closure(gmsh, (3, tag)) for tag in volumes}
    if policy == "independent":
        for index, left in enumerate(volumes):
            if any(closures[left] & closures[right] for right in volumes[index + 1:]):
                raise WorkerFailure("shared_topology", "Independent mode is a preflight check; the input shares CAD boundaries and must be separated explicitly")
    return {"operation": operation,
            "source_volume_map": [{"source_backend_tag": old, "backend_tag": new,
                                   "source_volume": before[old]} for old, new in mapping.items()]}, closures


def _apply_local_sizes(gmsh, local_sizes, identities, global_size, *, minimum_mesh_size=None):
    """Entity-restricted Constant fields; a Min field combines refinements.

    Public Gmsh 4.15.2 Constant/IncludeBoundary supports surfaces and volumes.
    Global min/max must not clamp local refinements back to the global size.
    """
    if not local_sizes:
        return []
    by_uuid = {identifier: entity for entity, identifier in identities.items()}
    fields, applied = [], []
    for identifier, size in local_sizes.items():
        entity = by_uuid.get(identifier)
        if entity is None:
            raise WorkerFailure("sizing_reference", f"Local sizing entity is absent from this XAO: {identifier}")
        dim, tag = entity
        field = gmsh.model.mesh.field.add("Constant")
        gmsh.model.mesh.field.setNumbers(field, "SurfacesList" if dim == 2 else "VolumesList", [tag])
        gmsh.model.mesh.field.setNumber(field, "IncludeBoundary", 1)
        gmsh.model.mesh.field.setNumber(field, "VIn", size)
        gmsh.model.mesh.field.setNumber(field, "VOut", global_size)
        fields.append(field)
        applied.append({"entity_uuid": identifier, "dimension": dim, "backend_tag": tag, "size": size,
                        "include_boundary": True})
    minimum = gmsh.model.mesh.field.add("Min")
    gmsh.model.mesh.field.setNumbers(minimum, "FieldsList", fields)
    gmsh.model.mesh.field.setAsBackgroundMesh(minimum)
    if minimum_mesh_size is None:
        gmsh.option.setNumber("Mesh.MeshSizeMin", min(local_sizes.values()))
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    return applied


def _check_mesh_interfaces(gmsh, closures, blocks, identities, policy):
    """Check actual shared node identity, not merely coincident coordinates."""
    node_sets = {}
    for tag in closures:
        node_sets[tag] = {node for block in blocks if block["dimension"] == 3
                         and block["entity_uuid"] == identities[(3, tag)] for conn in block["connectivity"] for node in conn}
    checks, tags = [], sorted(closures)
    for index, left in enumerate(tags):
        for right in tags[index + 1:]:
            common = node_sets[left] & node_sets[right]
            boundaries = closures[left] & closures[right]
            expected = set()
            for dim, tag in boundaries:
                ids, _, _ = gmsh.model.mesh.getNodes(dim, tag, includeBoundary=True)
                expected.update(int(value) for value in ids)
            if common != expected:
                raise WorkerFailure("interface_mesh", "Volume mesh nodes do not match their shared CAD boundaries")
            if policy == "independent" and common:
                raise WorkerFailure("interface_mesh", "Independent volumes unexpectedly share mesh node IDs")
            shared_surfaces = [identities[(dim, tag)] for dim, tag in sorted(boundaries) if dim == 2]
            facets = {tuple(sorted(conn)) for block in blocks if block["dimension"] == 2
                      and block["entity_uuid"] in shared_surfaces for conn in block["connectivity"]}
            if facets:
                for volume in (left, right):
                    faces = {tuple(sorted(face)) for block in blocks if block["dimension"] == 3
                             and block["entity_uuid"] == identities[(3, volume)]
                             for conn in block["connectivity"] for face in combinations(conn, 3)}
                    if not facets <= faces:
                        raise WorkerFailure("interface_mesh", "A shared surface facet is not a tetrahedron face on both adjacent parts")
            checks.append({"volume_uuids": [identities[(3, left)], identities[(3, right)]],
                           "shared_node_count": len(common),
                           "shared_surface_uuids": shared_surfaces,
                           "shared_facets_verified": len(facets)})
    return checks


def _cyclic(nodes):
    nodes = tuple(nodes)
    return min(nodes[i:] + nodes[:i] for i in range(len(nodes)))


def _sdk_nodes(gmsh):
    identifiers, coordinates, _ = gmsh.model.mesh.getNodes()
    ids, xyz = [int(value) for value in identifiers], [float(value) for value in coordinates]
    if (len(ids) != len(set(ids)) or len(xyz) != 3 * len(ids)
            or any(value < 1 for value in ids) or not all(math.isfinite(value) for value in xyz)):
        raise WorkerFailure("mesh_inventory", "Malformed generated node inventory")
    return dict(zip(ids, [tuple(xyz[i:i + 3]) for i in range(0, len(xyz), 3)]))


def _sdk_blocks(gmsh, dimension, expected_type):
    blocks = []
    for _, tag in gmsh.model.getEntities(dimension):
        types, id_arrays, connectivity = gmsh.model.mesh.getElements(dimension, tag)
        for typ, ids, conn in zip(types, id_arrays, connectivity):
            name, dim, order, count, _, _ = gmsh.model.mesh.getElementProperties(int(typ))
            if int(typ) != expected_type or int(dim) != dimension:
                raise WorkerFailure("mesh_inventory", "Unexpected generated element family", element_type=int(typ), dimension=dimension)
            flat = [int(value) for value in conn]
            if len(flat) != int(count) * len(ids):
                raise WorkerFailure("mesh_inventory", "Malformed generated connectivity")
            blocks.append({"dimension": dimension, "entity_tag": int(tag), "physical_tags": [],
                "element_type": int(typ), "element_name": name, "order": int(order),
                "nodes_per_element": int(count), "ids": [int(value) for value in ids],
                "connectivity": [flat[i:i + count] for i in range(0, len(flat), count)]})
    return blocks


def _elements(blocks):
    result = {}
    for block in blocks:
        for identifier, conn in zip(block["ids"], block["connectivity"]):
            if identifier in result:
                raise WorkerFailure("mesh_inventory", "Repeated generated element ID", element_id=identifier)
            result[identifier] = tuple(conn)
    return result


def _surface_boundary(surface, nodes, blocks):
    expected = dict(zip(surface.node_ids, surface.coordinates))
    changed = [identifier for identifier, xyz in expected.items() if nodes.get(identifier) != tuple(xyz)]
    facets = _elements(blocks)
    original = {identifier: _cyclic(conn) for identifier, conn in zip(surface.triangle_ids, surface.triangles)}
    actual = {identifier: _cyclic(conn[:3]) for identifier, conn in facets.items()}
    if changed or actual != original:
        raise WorkerFailure("boundary_changed", "The SDK changed original boundary coordinates or oriented facets",
            changed_node_ids=changed, missing_triangle_ids=sorted(original.keys() - actual.keys()),
            extra_triangle_ids=sorted(actual.keys() - original.keys()),
            changed_triangle_ids=sorted(identifier for identifier in original.keys() & actual.keys() if original[identifier] != actual[identifier]))
    return {"original_nodes_exact": True, "original_oriented_facets_exact": True,
            "boundary_nodes": len(expected), "boundary_triangles": len(original)}


def _elevation_mapping(before_triangles, before_tets, after_triangles, after_tets):
    """Match exact node topology, never coordinates, before restoring SDK tags."""
    rows = []
    for dimension, before, after, count in ((2, before_triangles, after_triangles, 3),
                                            (3, before_tets, after_tets, 4)):
        def key(conn):
            corners = tuple(conn[:count])
            return _cyclic(corners) if dimension == 2 else corners
        old_by_topology = {key(conn): identifier for identifier, conn in before.items()}
        new_by_topology = {key(conn): identifier for identifier, conn in after.items()}
        if (len(old_by_topology) != len(before) or len(new_by_topology) != len(after)
                or old_by_topology.keys() != new_by_topology.keys()):
            raise WorkerFailure("affine_tet10", "Elevation changed or ambiguously duplicated parent topology",
                                dimension=dimension)
        rows.extend({"dimension": dimension, "parent_id": identifier,
                     "elevated_id": new_by_topology[topology], "restored_id": identifier}
                    for topology, identifier in old_by_topology.items())
    if (len({row["parent_id"] for row in rows}) != len(rows)
            or len({row["elevated_id"] for row in rows}) != len(rows)):
        raise WorkerFailure("affine_tet10", "Elevation has ambiguous cross-dimension element IDs")
    return rows


def _volume_inventory(gmsh, nodes, boundary_blocks, volume_blocks):
    return {"entities": [{"dimension": int(dim), "tag": int(tag), "type": gmsh.model.getType(dim, tag)}
                         for dim, tag in gmsh.model.getEntities(3)],
            "nodes": {"ids": list(nodes), "coordinates": list(nodes.values())},
            "blocks": boundary_blocks + volume_blocks}


def _tet_topology(surface, tetrahedra):
    faces = {}
    for identifier, conn in tetrahedra.items():
        for face in ((conn[0], conn[2], conn[1]), (conn[0], conn[1], conn[3]),
                     (conn[1], conn[2], conn[3]), (conn[2], conn[0], conn[3])):
            faces.setdefault(tuple(sorted(face)), []).append((identifier, _cyclic(face)))
    invalid = [list(key) for key, rows in faces.items() if len(rows) > 2
               or len(rows) == 2 and rows[0][1] != _cyclic(rows[1][1][::-1])]
    boundary = {key: rows[0][1] for key, rows in faces.items() if len(rows) == 1}
    expected = {tuple(sorted(conn)): _cyclic(conn) for conn in surface.triangles}
    if invalid or boundary != expected:
        raise WorkerFailure("mesh_topology", "Tet4 boundary or interior face incidence differs from the closed source",
                            invalid_faces=invalid, missing_boundary_faces=[list(key) for key in expected.keys() - boundary.keys()],
                            extra_boundary_faces=[list(key) for key in boundary.keys() - expected.keys()])
    return {"boundary_faces_exact": True, "interior_faces_oppositely_oriented": True,
            "boundary_faces": len(boundary), "interior_faces": sum(len(rows) == 2 for rows in faces.values())}


def _metrics(nodes, tetrahedra, parameters, tetra_metrics):
    rows = []
    for identifier, conn in tetrahedra.items():
        values = tetra_metrics(tuple(nodes[node] for node in conn[:4]))
        if any(values[key] is not None and not math.isfinite(values[key]) for key in ("signed_volume", "corner_scaled_jacobian", "edge_aspect_ratio")):
            raise WorkerFailure("mesh_quality", "Nonfinite tetrahedron metrics", element_id=identifier)
        if not values.get("problem") and any(values[key] is None for key in ("signed_volume", "corner_scaled_jacobian", "edge_aspect_ratio")):
            raise WorkerFailure("mesh_quality", "Undefined tetrahedron metrics without a problem diagnostic", element_id=identifier)
        rows.append({"id": identifier, **values})
    if not rows:
        raise WorkerFailure("mesh_inventory", "The worker generated no tetrahedra")
    failed = [row["id"] for row in rows if row.get("problem") or row["signed_volume"] <= 0
              or row["corner_scaled_jacobian"] < parameters["minimum_scaled_jacobian"]
              or row["edge_aspect_ratio"] > parameters["maximum_edge_aspect_ratio"]]
    return {"passed": not failed, "failed_ids": failed, "cells": rows,
        "minimum_corner_scaled_jacobian": min((row["corner_scaled_jacobian"] for row in rows if row["corner_scaled_jacobian"] is not None), default=None),
        "maximum_edge_aspect_ratio": max((row["edge_aspect_ratio"] for row in rows if row["edge_aspect_ratio"] is not None), default=None),
        "total_signed_volume": math.fsum(row["signed_volume"] for row in rows) if all(row["signed_volume"] is not None for row in rows) else None}


def _affine_midpoints(nodes, tetrahedra, triangles, order):
    if order == 1:
        return {"required": False, "passed": True, "edge_midpoints": [], "maximum_midpoint_error": 0.}
    from ..application.tet10_geometry import certify_straight_tet10
    edges, inverse, maximum = {}, {}, 0.
    for cells, pairs, arity, offset in ((tetrahedra, ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3)), 10, 4),
                                      (triangles, ((0, 1), (1, 2), (2, 0)), 6, 3)):
        for identifier, conn in cells.items():
            if len(conn) != arity:
                raise WorkerFailure("affine_tet10", "Incorrect elevated element arity", element_id=identifier)
            for index, (a, b) in enumerate(pairs, offset):
                edge, midpoint = tuple(sorted((conn[a], conn[b]))), conn[index]
                if (edge in edges and edges[edge] != midpoint) or (midpoint in inverse and inverse[midpoint] != edge):
                    raise WorkerFailure("affine_tet10", "An edge does not have one shared midpoint", edge=edge)
                expected = tuple(x / 2 + y / 2 for x, y in zip(nodes[edge[0]], nodes[edge[1]]))
                for actual, value in zip(nodes[midpoint], expected):
                    error = abs(actual - value); maximum = max(maximum, error)
                    if error > 8 * math.ulp(value):
                        raise WorkerFailure("affine_tet10", "A high-order node is not an affine edge midpoint",
                                            edge=edge, midpoint=midpoint, error=error, allowed=8 * math.ulp(value))
                edges[edge], inverse[midpoint] = midpoint, edge
    certificates = [{"id": identifier, **certify_straight_tet10(tuple(nodes[node] for node in conn),
        ordering="gmsh", ulp_budget=8)} for identifier, conn in tetrahedra.items()]
    failed = [row["id"] for row in certificates if not row["certified_positive"] or not row["midpoint_within_ulp_budget"]]
    return {"required": True, "passed": not failed, "certified_positive": all(row["certified_positive"] for row in certificates),
        "midpoint_within_ulp_budget": all(row["midpoint_within_ulp_budget"] for row in certificates),
        "failed_ids": failed, "certificates": certificates, "edge_midpoints": [
        {"edge": list(edge), "node_id": identifier} for edge, identifier in sorted(edges.items())],
        "maximum_midpoint_error": maximum, "midpoint_rule": "absolute error <= 8 * ulp(expected midpoint coordinate)"}


def _serialization(expected_nodes, expected_blocks, written):
    nodes = dict(zip(written["nodes"]["ids"], map(tuple, written["nodes"]["coordinates"])))
    if nodes.keys() != expected_nodes.keys():
        raise WorkerFailure("serialization_changed", "Written MSH changed the node IDs")
    maximum, ratio = 0., 0.
    for identifier, xyz in expected_nodes.items():
        for expected, actual in zip(xyz, nodes[identifier]):
            error, allowed = abs(expected - actual), 8 * math.ulp(expected)
            maximum = max(maximum, error); ratio = max(ratio, error / math.ulp(expected))
            if not math.isfinite(actual) or error > allowed:
                raise WorkerFailure("serialization_changed", "Written MSH coordinates exceeded the declared 8-ULP bound",
                    node_id=identifier, expected=expected, actual=actual, error=error if math.isfinite(error) else None, allowed=allowed)
    def inventory(blocks):
        return {(block["dimension"], identifier): (block["element_type"], block["order"], tuple(conn))
                for block in blocks for identifier, conn in zip(block["ids"], block["connectivity"])}
    if inventory(expected_blocks) != inventory(written["blocks"]):
        raise WorkerFailure("serialization_changed", "Written MSH changed the full element inventory or connectivity")
    return nodes, {"passed": True, "coordinate_rule": "absolute error <= 8 * ulp(expected coordinate)",
                   "maximum_absolute_coordinate_error": maximum, "maximum_coordinate_error_ulps": ratio,
                   "node_ids_exact": True, "element_inventory_exact": True}


def _preserve_msh_coordinates(path, nodes):
    """Replace only ASCII MSH4.1 coordinate tokens with exact SDK roundtrips.

    Gmsh 4.15.2 writes %.16g. Independent endpoint rounding can violate the
    midpoint gate near cancellation even when each coordinate meets 8 ULP.
    Tags, block headers, whitespace and every other section remain byte exact.
    """
    original = path.read_bytes()
    if not re.search(rb"(?m)^\$MeshFormat\r?\n4\.1 0 8\r?\n\$EndMeshFormat\r?$", original):
        raise WorkerFailure("serialization_changed", "Coordinate preservation requires ASCII MSH 4.1")
    sections = list(re.finditer(rb"(?ms)^\$Nodes\r?\n(.*?)^\$EndNodes\r?$", original))
    if len(sections) != 1:
        raise WorkerFailure("serialization_changed", "Expected exactly one MSH Nodes section")
    section = sections[0]
    tokens = list(re.finditer(rb"\S+", section[1]))
    cursor, replacements, seen = 0, [], set()
    def integer():
        nonlocal cursor
        token = tokens[cursor][0]
        cursor += 1
        if not re.fullmatch(rb"[0-9]+", token):
            raise ValueError("Expected a nonnegative MSH integer")
        return int(token)
    try:
        blocks, total, minimum, maximum = (integer() for _ in range(4))
        if total != len(nodes) or minimum != min(nodes) or maximum != max(nodes):
            raise ValueError("MSH Nodes header differs from SDK inventory")
        for _ in range(blocks):
            dimension, tag, parametric, count = (integer() for _ in range(4))
            if dimension > 3 or tag < 1 or parametric != 0:
                raise ValueError("Unsupported or parametric MSH Nodes block")
            identifiers = [integer() for _ in range(count)]
            for identifier in identifiers:
                if identifier not in nodes or identifier in seen:
                    raise ValueError("Missing, extra or repeated MSH node ID")
                seen.add(identifier)
                for value in nodes[identifier]:
                    token = tokens[cursor]
                    cursor += 1
                    actual = float(token[0])
                    if not math.isfinite(actual) or abs(actual - value) > 8 * math.ulp(value):
                        raise ValueError("Original MSH coordinate exceeds the 8-ULP serialization bound")
                    replacements.append((section.start(1) + token.start(), section.start(1) + token.end(),
                                         repr(float(value)).encode("ascii")))
        if seen != nodes.keys() or cursor != len(tokens):
            raise ValueError("MSH Nodes section does not exactly match SDK inventory")
    except (ValueError, IndexError, OverflowError) as exc:
        raise WorkerFailure("serialization_changed", str(exc)) from exc
    chunks, start = [], 0
    for left, right, value in replacements:
        chunks.extend((original[start:left], value)); start = right
    chunks.append(original[start:])
    preserved = b"".join(chunks)
    temporary = path.with_suffix(".msh.precision.tmp")
    with temporary.open("xb") as stream:
        stream.write(preserved)
    temporary.replace(path)
    return {"coordinate_encoding": "authoritative SDK repr(float) roundtrip",
            "noncoordinate_bytes_preserved": True, "nodes": len(seen),
            "gmsh_ascii_sha256": hashlib.sha256(original).hexdigest(),
            "preserved_ascii_sha256": hashlib.sha256(preserved).hexdigest()}


def _generate_surface_volume(request):
    from .gmsh_backend import _surface_parameters, GmshBackendError
    try:
        parameters = _surface_parameters(request["mesh_size"], length_unit=request["length_unit"],
            **{key: request[key] for key in ("element_order", "smoothing_iterations", "relaxation",
                "minimum_scaled_jacobian", "maximum_edge_aspect_ratio", "volume_optimizer") if key in request})
        if request.get("dimension", 3) != 3:
            raise GmshBackendError("invalid_request", "Surface volume generation requires dimension 3")
    except (GmshBackendError, KeyError) as exc:
        raise WorkerFailure("invalid_request", str(exc)) from exc
    source, out = Path(request["source"]).resolve(), Path(request["output_dir"]).resolve()
    if not source.is_file() or source.suffix.lower() != ".msh":
        raise WorkerFailure("invalid_request", "A captured closed tri3 MSH is required")
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if request.get("source_sha256", digest) != digest:
        raise WorkerFailure("source_changed", "The captured surface bytes changed before generation")
    out.mkdir(parents=True, exist_ok=True)
    msh, metadata = out / "mesh.msh", out / "metadata.json"
    if msh.exists() or metadata.exists():
        raise WorkerFailure("invalid_request", "Surface volume output assets already exist")
    try:
        from ..application.surface_tet import load_closed_surface, tetra_metrics, smooth_tet4
        surface = load_closed_surface(source, length_unit=parameters["length_unit"])
    except Exception as exc:
        raise WorkerFailure(getattr(exc, "code", "invalid_surface"), str(exc), **getattr(exc, "details", {})) from exc
    try:
        import gmsh
    except Exception as exc:
        raise WorkerFailure("dependency_error", f"Gmsh SDK is unavailable: {exc}") from exc
    if getattr(gmsh, "__version__", None) != "4.15.2" or not getattr(gmsh, "libpath", None):
        raise WorkerFailure("dependency_error", "Surface volume generation requires the Gmsh 4.15.2 SDK")
    options = {"General.NumThreads": 1, "Mesh.MeshSizeMin": parameters["mesh_size"],
        "Mesh.MeshSizeMax": parameters["mesh_size"], "Mesh.ElementOrder": 1, "Mesh.Algorithm3D": 1,
        "Mesh.MeshOnlyEmpty": 1, "Mesh.Renumber": 0, "Mesh.Optimize": 1,
        "Mesh.OptimizeNetgen": 0, "Mesh.Smoothing": 0, "Mesh.HighOrderOptimize": 0,
        "Mesh.SecondOrderLinear": 1, "Mesh.SaveAll": 1, "Mesh.Binary": 0, "Mesh.MshFileVersion": 4.1}
    try:
        gmsh.initialize(readConfigFiles=False, interruptible=False)
        gmsh.option.setNumber("General.Terminal", 1); gmsh.logger.start()
        for name, value in options.items(): gmsh.option.setNumber(name, value)
        gmsh.model.add("caelab-closed-tri-surface")
        tag = gmsh.model.addDiscreteEntity(2)
        gmsh.model.mesh.addNodes(2, tag, list(surface.node_ids), [value for xyz in surface.coordinates for value in xyz])
        gmsh.model.mesh.addElementsByType(tag, 2, list(surface.triangle_ids), [node for tri in surface.triangles for node in tri])
        loop = gmsh.model.geo.addSurfaceLoop([tag])
        volume = gmsh.model.geo.addVolume([loop]); gmsh.model.geo.synchronize()
        gmsh.model.mesh.generate(3)
        nodes = _sdk_nodes(gmsh)
        boundary_blocks, volume_blocks = _sdk_blocks(gmsh, 2, 2), _sdk_blocks(gmsh, 3, 4)
        boundary = _surface_boundary(surface, nodes, boundary_blocks)
        tetrahedra = _elements(volume_blocks)
        topology = _tet_topology(surface, tetrahedra)
        before = _metrics(nodes, tetrahedra, parameters, tetra_metrics)
        if any(row.get("problem") or row["signed_volume"] <= 0 for row in before["cells"]):
            raise WorkerFailure("mesh_topology", "Generated Tet4 contains invalid cells", element_ids=[row["id"] for row in before["cells"] if row.get("problem") or row["signed_volume"] <= 0])
        optimization = {"method": parameters["volume_optimizer"],
            "context": "fresh geo-created volume after Delaunay/default Gmsh optimization and before interior Laplacian",
            "before": _volume_inventory(gmsh, nodes, boundary_blocks, volume_blocks),
            "quality_before": before, "boundary_before": boundary, "topology_before": topology,
            "netgen": {"performed": parameters["volume_optimizer"] == "netgen", "force": False,
                       "niter": 1, "dim_tags": [[3, int(volume)]]}}
        if parameters["volume_optimizer"] == "netgen":
            gmsh.model.mesh.optimize("Netgen", force=False, niter=1, dimTags=[(3, volume)])
            nodes = _sdk_nodes(gmsh)
            boundary_blocks, volume_blocks = _sdk_blocks(gmsh, 2, 2), _sdk_blocks(gmsh, 3, 4)
            tetrahedra = _elements(volume_blocks)
            optimization["after"] = _volume_inventory(gmsh, nodes, boundary_blocks, volume_blocks)
            optimization["quality_after"] = _metrics(nodes, tetrahedra, parameters, tetra_metrics)
            try:
                boundary = _surface_boundary(surface, nodes, boundary_blocks)
                topology = _tet_topology(surface, tetrahedra)
                if any(row.get("problem") or row["signed_volume"] <= 0 for row in optimization["quality_after"]["cells"]):
                    raise WorkerFailure("mesh_topology", "Netgen produced invalid Tet4 cells",
                        element_ids=[row["id"] for row in optimization["quality_after"]["cells"]
                                     if row.get("problem") or row["signed_volume"] <= 0])
            except WorkerFailure as exc:
                optimization["failure"] = {"code": exc.code, "message": str(exc), "details": exc.details}
                evidence = out / "volume-optimization.json"
                with evidence.open("x", encoding="utf-8") as stream:
                    json.dump(optimization, stream, allow_nan=False)
                raise WorkerFailure(exc.code, str(exc), **exc.details, optimization_evidence=str(evidence)) from exc
            optimization.update(boundary_after=boundary, topology_after=topology)
            before = optimization["quality_after"]
        else:
            optimization.update(after=optimization["before"], quality_after=before,
                                boundary_after=boundary, topology_after=topology)
        ids = tuple(nodes)
        moved, smoothing = smooth_tet4(ids, tuple(nodes.values()), tuple(tetrahedra.values()), surface.node_ids,
            iterations=parameters["smoothing_iterations"], relaxation=parameters["relaxation"])
        if len(moved) != len(ids):
            raise WorkerFailure("smoothing_contract", "The smoother changed the node inventory")
        moved = dict(zip(ids, map(tuple, moved)))
        _surface_boundary(surface, moved, boundary_blocks)
        for identifier, xyz in moved.items():
            if xyz != nodes[identifier]: gmsh.model.mesh.setNode(identifier, list(xyz), [])
        nodes = _sdk_nodes(gmsh)
        if nodes != moved:
            raise WorkerFailure("smoothing_contract", "The SDK did not retain the accepted interior coordinates")
        _surface_boundary(surface, nodes, boundary_blocks)
        after = _metrics(nodes, tetrahedra, parameters, tetra_metrics)
        if any(row.get("problem") or row["signed_volume"] <= 0 for row in after["cells"]):
            raise WorkerFailure("mesh_topology", "Smoothing produced nonpositive Tet4 cells")
        elevation = {"performed": False, "element_id_mapping": []}
        if parameters["element_order"] == 2:
            parent_triangles = _elements(boundary_blocks)
            parent_nodes = nodes
            gmsh.model.mesh.setOrder(2)
            elevated_nodes = _sdk_nodes(gmsh)
            if any(elevated_nodes.get(identifier) != xyz for identifier, xyz in parent_nodes.items()):
                raise WorkerFailure("affine_tet10", "Elevation changed original parent node IDs or coordinates")
            mapping = _elevation_mapping(parent_triangles, tetrahedra,
                _elements(_sdk_blocks(gmsh, 2, 9)), _elements(_sdk_blocks(gmsh, 3, 11)))
            if any(row["parent_id"] != row["elevated_id"] for row in mapping):
                gmsh.model.mesh.renumberElements([row["elevated_id"] for row in mapping],
                                                [row["restored_id"] for row in mapping])
            elevation = {"performed": True, "element_id_mapping": mapping,
                         "matching": "oriented cyclic triangle corners and exact ordered tetrahedron corners"}
        order = parameters["element_order"]
        boundary_blocks = _sdk_blocks(gmsh, 2, 2 if order == 1 else 9)
        volume_blocks = _sdk_blocks(gmsh, 3, 4 if order == 1 else 11)
        final_tets = _elements(volume_blocks)
        if {identifier: conn[:4] for identifier, conn in final_tets.items()} != tetrahedra:
            raise WorkerFailure("affine_tet10", "Elevation changed parent Tet4 IDs or corners")
        nodes = _sdk_nodes(gmsh)
        _surface_boundary(surface, nodes, boundary_blocks)
        affine = _affine_midpoints(nodes, final_tets, _elements(boundary_blocks), order)
        gmsh.write(str(msh))
        from .msh_worker import read_msh
        written = read_msh(msh)
        if written["format_version"] != "4.1":
            raise WorkerFailure("serialization_changed", "Surface volume output must be ASCII MSH 4.1")
        _, original_serialization = _serialization(nodes, boundary_blocks + volume_blocks, written)
        encoding = _preserve_msh_coordinates(msh, nodes)
        written = read_msh(msh)
        written_nodes, serialization = _serialization(nodes, boundary_blocks + volume_blocks, written)
        serialization.update(**encoding, gmsh_original=original_serialization)
        written_boundary = [block for block in written["blocks"] if block["dimension"] == 2]
        written_tets = _elements([block for block in written["blocks"] if block["dimension"] == 3])
        written_boundary_report = _surface_boundary(surface, written_nodes, written_boundary)
        written_topology = _tet_topology(surface, written_tets)
        affine_written = _affine_midpoints(written_nodes, written_tets, _elements(written_boundary), order)
        quality = _metrics(written_nodes, written_tets, parameters, tetra_metrics)
        messages = list(gmsh.logger.get())
        errors = [message for message in messages if message.startswith("Error:")]
        if errors: raise WorkerFailure("sdk_error", "Gmsh logged errors", errors=errors)
        with source.open("rb") as stream:
            unchanged = hashlib.file_digest(stream, "sha256").hexdigest() == digest
        if not unchanged:
            raise WorkerFailure("source_changed", "The captured surface changed during generation")
        result = {"schema_version": 1, "source_kind": "surface_tet",
            "status": "quality_passed" if quality["passed"] and affine_written["passed"] else "quality_failed",
            "backend": {"name": "gmsh", "version": gmsh.__version__},
            "mesh_uuid": str(uuid.uuid4()), "length_unit": parameters["length_unit"],
            "source": {"path": request.get("original_source", str(source)), "captured_path": str(source), "sha256": digest},
            "assets": {"source": str(source), "msh": str(msh), "metadata": str(metadata)},
            "source_surface": asdict(surface), "mesh": {"nodes": written["nodes"], "blocks": written["blocks"]},
            "recipe": {**parameters, "algorithm3d": "delaunay", "smoothing_method": "interior_laplacian", "options": options,
                "quality_definitions": {"corner_scaled_jacobian": "surface_tet.tetra_metrics.corner_scaled_jacobian",
                    "edge_aspect_ratio": "maximum corner edge length / minimum corner edge length"}},
            "generation": {"laplacian": smoothing, "elevation": elevation,
                "volume_optimization": optimization,
                "gmsh_optimization": {"enabled": True, "method": "Gmsh default tetrahedral optimization"},
                "inventory": [{"dimension": block["dimension"], "element_type": block["element_type"], "order": block["order"], "count": len(block["ids"])} for block in written["blocks"]],
                "before_smoothing": before, "after_smoothing": after, "sdk_messages": messages},
            "topology": {**written_boundary_report, **written_topology, "positive_parent_volumes": True,
                         "sdk": {**boundary, **topology},
                         "written": {**written_boundary_report, **written_topology}},
            "quality": quality, "affine": {**affine_written, "sdk_maximum_midpoint_error": affine["maximum_midpoint_error"]},
            "serialization": serialization, "diagnostics": [], "sdk_error_count": 0}
        temporary = metadata.with_suffix(".json.tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False)
        temporary.replace(metadata)
        return result
    except WorkerFailure:
        raise
    except Exception as exc:
        raise WorkerFailure(getattr(exc, "code", "sdk_error"), str(exc), **getattr(exc, "details", {})) from exc
    finally:
        if gmsh.isInitialized(): gmsh.finalize()


def _geometry_values(values, count, field):
    try:
        result = [float(value) for value in values]
        if (count is not None and len(result) != count) or not all(math.isfinite(value) for value in result):
            raise ValueError()
    except (TypeError, ValueError, OverflowError) as exc:
        raise WorkerFailure("invalid_geometry", "Malformed or nonfinite SDK geometry values", field=field) from exc
    return result


def _geometry_tag(value):
    try:
        result = int(value)
        if isinstance(value, bool) or result != value or result == 0:
            raise ValueError()
    except (TypeError, ValueError, OverflowError) as exc:
        raise WorkerFailure("invalid_geometry", "Malformed SDK topology tag") from exc
    return result


def _analytic_properties(gmsh, dimension, tag, kind):
    integers, reals = gmsh.model.getEntityProperties(dimension, tag)
    raw_integers = []
    for value in integers:
        number = int(value)
        if isinstance(value, bool) or number != value:
            raise WorkerFailure("invalid_geometry", "Malformed analytic integer properties")
        raw_integers.append(number)
    raw_reals = _geometry_values(reals, None, "analytic_properties")
    layouts = {"Plane": (4, "plane_cartesian_coefficients"),
               "Cylinder": (7, "axis_point_xyz_direction_xyz_radius"),
               "Cone": (8, "axis_point_xyz_direction_xyz_radius_semiangle"),
               "Sphere": (4, "center_xyz_radius"),
               "Torus": (8, "axis_point_xyz_direction_xyz_major_minor_radii")}
    expected = layouts.get(kind) if dimension == 2 else None
    if expected and len(raw_reals) != expected[0]:
        raise WorkerFailure("invalid_geometry", "Analytic properties differ from the pinned SDK layout", geometry_type=kind)
    return {"integers": raw_integers, "reals": raw_reals,
            "layout": expected[1] if expected else None,
            "interpretation_source": "Gmsh 4.15.2 OCCFace::geomProperties; curve/other properties remain uninterpreted"}


def _geometry_bounds(gmsh, dimension, tag):
    low, high = gmsh.model.getParametrizationBounds(dimension, tag)
    low = _geometry_values(low, dimension, "parametric_bounds.minimum")
    high = _geometry_values(high, dimension, "parametric_bounds.maximum")
    if any(a > b for a, b in zip(low, high)):
        raise WorkerFailure("invalid_geometry", "Reversed SDK parametric bounds")
    return {"minimum": low, "maximum": high}


def _inspect_geometry(request):
    from .gmsh_backend import _FORMATS
    supported = {"source_kind", "source", "original_source", "source_sha256", "output_dir",
                 "expected_coordinate_length_unit"}
    unknown = sorted(request.keys() - supported)
    if unknown:
        raise WorkerFailure("unsupported_criteria", "Geometry inspection does not generate or configure a mesh", criteria=unknown)
    expected = request.get("expected_coordinate_length_unit")
    if expected is not None and expected not in ("mm", "cm", "m"):
        raise WorkerFailure("invalid_request", "Expected coordinate length unit must be mm, cm or m")
    try:
        source, out = Path(request["source"]).resolve(), Path(request["output_dir"]).resolve()
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkerFailure("invalid_request", "Inspection needs a CAD input and output directory") from exc
    if not source.is_file() or source.suffix.lower() not in _FORMATS:
        raise WorkerFailure("invalid_request", "Choose a supported existing CAD input")
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if request.get("source_sha256", digest) != digest:
        raise WorkerFailure("source_changed", "Captured CAD changed before inspection")
    out.mkdir(parents=True, exist_ok=True)
    xao, metadata = out / "geometry.xao", out / "metadata.json"
    if xao.exists() or metadata.exists():
        raise WorkerFailure("invalid_request", "Inspection output assets already exist")
    try:
        import gmsh
    except Exception as exc:
        raise WorkerFailure("dependency_error", f"Gmsh SDK is unavailable: {exc}") from exc
    if getattr(gmsh, "__version__", None) != "4.15.2" or not getattr(gmsh, "libpath", None):
        raise WorkerFailure("dependency_error", "Geometry inspection requires the Gmsh 4.15.2 SDK")
    try:
        gmsh.initialize(readConfigFiles=False, interruptible=False)
        gmsh.option.setNumber("General.Terminal", 1); gmsh.logger.start()
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        _import_cad(gmsh, source)
        surface_tags = [int(tag) for _, tag in gmsh.model.getEntities(2)]
        volume_tags = [int(tag) for _, tag in gmsh.model.getEntities(3)]
        if not surface_tags:
            raise WorkerFailure("geometry_error", "Inspection requires CAD surfaces")
        resource, revision, unit, identities = _checked_cad_identity(
            gmsh, surface_tags, volume_tags, source.suffix.lower(), expected)
        tolerance = _geometry_values([gmsh.option.getNumber("Geometry.Tolerance")], 1, "Geometry.Tolerance")[0]
        if tolerance < 0:
            raise WorkerFailure("invalid_geometry", "Negative SDK geometry tolerance")
        orientations = {tag: [] for tag in surface_tags}
        volumes = []
        for tag in volume_tags:
            members = []
            for dim, signed in gmsh.model.getBoundary([(3, tag)], combined=False, oriented=True):
                if dim != 2 or abs(int(signed)) not in orientations:
                    raise WorkerFailure("invalid_geometry", "Volume references an unknown boundary surface")
                signed = _geometry_tag(signed)
                members.append(identities[(2, abs(signed))])
                orientations[abs(signed)].append({"volume_uuid": identities[(3, tag)], "sign": 1 if signed > 0 else -1})
            volumes.append({"uuid": identities[(3, tag)], "backend_tag": tag,
                "physical_group_name": f"caelab:volume:{identities[(3, tag)]}",
                "bbox": _geometry_values(gmsh.model.getBoundingBox(3, tag), 6, "volume.bbox"),
                "volume": _geometry_values([gmsh.model.occ.getMass(3, tag)], 1, "volume.volume")[0],
                "surface_uuids": members})
        surfaces = []
        curve_tags = {int(tag) for _, tag in gmsh.model.getEntities(1)}
        for tag in surface_tags:
            kind = gmsh.model.getType(2, tag)
            bounds = _geometry_bounds(gmsh, 2, tag)
            loop_tags, loops = gmsh.model.occ.getCurveLoops(tag)
            if len(loop_tags) != len(loops):
                raise WorkerFailure("invalid_geometry", "SDK loop tags and memberships differ")
            loop_rows = []
            for loop, members in zip(loop_tags, loops):
                members = [_geometry_tag(value) for value in members]
                if any(abs(value) not in curve_tags for value in members):
                    raise WorkerFailure("invalid_geometry", "Surface loop references an unknown curve")
                loop_rows.append({"backend_tag": _geometry_tag(loop), "curve_tags": members})
            uv = [a / 2 + b / 2 for a, b in zip(bounds["minimum"], bounds["maximum"])]
            xyz = _geometry_values(gmsh.model.getValue(2, tag, uv), 3, "sample.xyz")
            normal = _geometry_values(gmsh.model.getNormal(tag, uv), 3, "sample.face_normal")
            count = int(gmsh.model.isInside(2, tag, uv, parametric=True))
            if count not in (0, 1):
                raise WorkerFailure("invalid_geometry", "Single-point trim query returned an invalid count")
            surfaces.append({"uuid": identities[(2, tag)], "backend_tag": tag,
                "physical_group_name": f"caelab:surface:{identities[(2, tag)]}", "geometry_type": kind,
                "area": _geometry_values([gmsh.model.occ.getMass(2, tag)], 1, "surface.area")[0],
                "bbox": _geometry_values(gmsh.model.getBoundingBox(2, tag), 6, "surface.bbox"),
                "center": _geometry_values(gmsh.model.occ.getCenterOfMass(2, tag), 3, "surface.center"),
                "orientation_by_volume": orientations[tag], "curve_loops": loop_rows,
                "analytic_properties": _analytic_properties(gmsh, 2, tag, kind), "parametric_bounds": bounds,
                "samples": [{"uv": uv, "xyz": xyz, "face_normal": normal, "trim_count": count}],
                "sampling_status": "unverified", "normal_basis": "gmsh_face_oriented_no_volume_sign"})
        curves = []
        for tag in sorted(curve_tags):
            kind = gmsh.model.getType(1, tag)
            adjacent, _ = gmsh.model.getAdjacencies(1, tag)
            adjacent_refs = []
            for face in adjacent:
                face = abs(_geometry_tag(face))
                if face not in orientations:
                    raise WorkerFailure("invalid_geometry", "Curve references an unknown adjacent surface")
                adjacent_refs.append(identities[(2, face)])
            endpoints = []
            for dim, vertex in gmsh.model.getBoundary([(1, tag)], combined=False, oriented=False):
                if dim != 0:
                    raise WorkerFailure("invalid_geometry", "Curve boundary is not a vertex")
                vertex = _geometry_tag(vertex)
                endpoints.append({"backend_tag": vertex,
                    "xyz": _geometry_values(gmsh.model.getValue(0, abs(vertex), []), 3, "endpoint.xyz")})
            curves.append({"backend_tag": tag, "geometry_type": kind,
                "bbox": _geometry_values(gmsh.model.getBoundingBox(1, tag), 6, "curve.bbox"),
                "length": _geometry_values([gmsh.model.occ.getMass(1, tag)], 1, "curve.length")[0],
                "parametric_bounds": _geometry_bounds(gmsh, 1, tag),
                "analytic_properties": _analytic_properties(gmsh, 1, tag, kind),
                "endpoints": endpoints, "adjacent_surface_uuids": adjacent_refs})
        gmsh.write(str(xao))
        messages = list(gmsh.logger.get())
        errors = [message for message in messages if message.startswith("Error:")]
        if errors:
            raise WorkerFailure("sdk_error", "Gmsh logged inspection errors", errors=errors)
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise WorkerFailure("source_changed", "Captured CAD changed during inspection")
        result = {"schema_version": 1, "source_kind": "cad_geometry_inspection",
            "source": {"path": request.get("original_source", str(source)), "sha256": digest, "captured_path": str(source)},
            "backend": {"name": "gmsh", "version": gmsh.__version__}, "geometry_resource_uuid": resource,
            "geometry_revision": revision, "length_unit": unit, "assets": {"xao": str(xao), "metadata": str(metadata)},
            "expected_coordinate_length_unit": expected, "geometry_tolerance": tolerance,
            "surfaces": surfaces, "volumes": volumes, "curves": curves,
            "topology_semantics": {"curve_loop_tags": "inspection-local; no persistent UUIDs",
                "curve_loops": "SDK ordered curve IDs; outer/inner roles and orientation are not inferred",
                "samples": "UV bounds midpoint; trim includes IN or ON, boundary clearance unverified; no volume probes or feature classification"},
            "diagnostics": [{"severity": "warning", "code": "sdk_warning", "message": message}
                            for message in messages if message.startswith("Warning:")], "sdk_error_count": 0}
        temporary = metadata.with_suffix(".json.tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False)
        temporary.replace(metadata)
        return result
    except WorkerFailure:
        raise
    except Exception as exc:
        raise WorkerFailure("sdk_error", str(exc)) from exc
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()


def generate(request):
    unimplemented = sorted({"washer_rim_divisions", "washer_width", "washer_layers",
                            "fillet_suppression_threshold"} & request.keys())
    if unimplemented:
        raise WorkerFailure("unsupported_criteria", "CAD criteria are not implemented", criteria=unimplemented)
    if request.get("source_kind") == "cad_geometry_inspection":
        return _inspect_geometry(request)
    if request.get("source_kind") not in (None, "cad") and "expected_coordinate_length_unit" in request:
        raise WorkerFailure("unsupported_criteria", "Coordinate unit expectations are supported only for CAD generation")
    if request.get("source_kind") == "closed_tri_surface":
        if "minimum_mesh_size" in request:
            raise WorkerFailure("unsupported_criteria", "minimum_mesh_size is supported only for CAD generation")
        return _generate_surface_volume(request)
    if request.get("source_kind") not in (None, "cad"):
        raise WorkerFailure("invalid_request", "Unknown source kind")
    supported = {"source_kind", "source", "original_source", "source_sha256", "output_dir",
                 "mesh_size", "minimum_mesh_size", "dimension", "interface_policy", "local_sizes",
                 "expected_coordinate_length_unit"}
    unknown = sorted(request.keys() - supported)
    if unknown:
        raise WorkerFailure("unsupported_criteria", "CAD criteria are not implemented", criteria=unknown)
    source = Path(request["source"]).resolve()
    out = Path(request["output_dir"]).resolve()
    try:
        size = float(request["mesh_size"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise WorkerFailure("invalid_request", "Invalid mesh size") from exc
    dimension = request["dimension"]
    policy = request.get("interface_policy", "preserve")
    local_sizes = request.get("local_sizes", {})
    expected_unit = request.get("expected_coordinate_length_unit")
    if expected_unit is not None and expected_unit not in ("mm", "cm", "m"):
        raise WorkerFailure("invalid_request", "Expected coordinate length unit must be mm, cm or m")
    if isinstance(request["mesh_size"], bool) or not math.isfinite(size) or size <= 0 or isinstance(dimension, bool) or dimension not in (2, 3):
        raise WorkerFailure("invalid_request", "Invalid mesh size or dimension")
    if policy not in ("preserve", "conformal", "independent") or not isinstance(local_sizes, dict):
        raise WorkerFailure("invalid_request", "Invalid interface policy or local sizing mapping")
    if local_sizes and source.suffix.lower() != ".xao":
        raise WorkerFailure("invalid_request", "Local sizing requires persisted XAO entity identities")
    for identifier, value in local_sizes.items():
        if _uuid(identifier) != identifier or type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= size:
            raise WorkerFailure("invalid_request", "Invalid local refinement size or entity UUID")
    from .gmsh_backend import _cad_minimum_size, GmshBackendError
    try:
        minimum = _cad_minimum_size(size, request.get("minimum_mesh_size"), local_sizes)
    except GmshBackendError as exc:
        raise WorkerFailure(exc.code, str(exc)) from exc
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
        gmsh.logger.start()
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        gmsh.option.setNumber("Mesh.MeshSizeMin", size if minimum is None else minimum)
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.option.setNumber("Mesh.SaveAll", 1)
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        _import_cad(gmsh, source)
        preparation, closures = _prepare_interfaces(gmsh, policy, source.suffix.lower())
        surface_tags = [int(tag) for _, tag in gmsh.model.getEntities(2)]
        volume_tags = [int(tag) for _, tag in gmsh.model.getEntities(3)]
        if not surface_tags or dimension == 3 and not volume_tags:
            raise WorkerFailure("geometry_error", "Input does not contain geometry suitable for the requested mesh dimension")
        resource_uuid, revision, unit, entity_uuids = _checked_cad_identity(
            gmsh, surface_tags, volume_tags, source.suffix.lower(), expected_unit)
        applied_sizes = _apply_local_sizes(gmsh, local_sizes, entity_uuids, size, minimum_mesh_size=minimum)
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
        interface_checks = _check_mesh_interfaces(gmsh, closures, blocks, entity_uuids, policy) if dimension == 3 else []
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
        sdk_messages = list(gmsh.logger.get())
        sdk_errors = [message for message in sdk_messages if message.startswith("Error:")]
        if sdk_errors:
            raise WorkerFailure("sdk_error", "Gmsh logged errors: " + "; ".join(sdk_errors[-5:]))
        coordinates = [float(x) for x in xyz]
        diagnostics = []
        if unit == "unknown":
            diagnostics.append({"severity": "warning", "code": "unknown_length_unit",
                                "message": "BREP/external XAO units are not declared; the caller must assign consistent units before solver export."})
        sdk_sizes = {name: float(gmsh.option.getNumber(name)) for name in ("Mesh.MeshSizeMin", "Mesh.MeshSizeMax")}
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
            "recipe": {"global_size": size, "dimension": dimension, "interface_policy": policy,
                       "expected_coordinate_length_unit": expected_unit,
                       "minimum_mesh_size": minimum,
                       "effective_minimum_mesh_size": sdk_sizes["Mesh.MeshSizeMin"],
                       "effective_maximum_mesh_size": sdk_sizes["Mesh.MeshSizeMax"],
                       "minimum_mesh_size_origin": "explicit" if minimum is not None else "derived_local" if local_sizes else "legacy_target",
                       "sdk_size_options": sdk_sizes,
                       "size_bound_semantics": "SDK sizing bounds; not a guarantee on every output element edge",
                       "independent_is_preflight_only": True, "local_sizes": applied_sizes,
                       "topology_preparation": preparation,
                       "local_size_rule": "Minimum of global and entity targets, including entity boundaries; shared boundaries may refine adjacent parts"},
            "interface_checks": interface_checks,
            "sdk_error_count": len(sdk_errors),
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
            if exc.details: response["error"]["details"] = exc.details
        except Exception as exc:
            response = {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}}
        protocol.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
        protocol.flush()
        protocol.close()
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
