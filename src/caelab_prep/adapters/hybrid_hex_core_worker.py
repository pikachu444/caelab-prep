"""Isolated Gmsh 4.15.2 worker for a single closed OCC solid."""

from collections import defaultdict, deque
from itertools import chain
import json
import math
from pathlib import Path
import sys

from ..cae_core.errors import PrepError
from .hybrid_hex_core_geometry import (add, audit_faces, build_core, cross, dot,
                                       require, scale, select_core,
                                       shell_components, signed_shell_volume, sub)


def _coordinates(model):
    tags, values, _ = model.mesh.getNodes()
    nodes = {int(tag): tuple(float(v) for v in values[i:i+3])
             for tag, i in zip(tags, range(0, len(values), 3))}
    require(len(nodes) == len(tags) and all(math.isfinite(v) for p in nodes.values() for v in p),
            "Gmsh returned duplicate IDs or nonfinite coordinates.")
    return nodes


def _connectivity(model, dimension, tag, expected_type, width):
    types, ids, lists = model.mesh.getElements(dimension, tag)
    require(tuple(types) == (expected_type,), f"Entity {dimension}:{tag} has unexpected cell types {list(types)}.")
    values = [int(value) for value in lists[0]]
    require(len(values) == len(ids[0]) * width and len(ids[0]), f"Entity {dimension}:{tag} lacks complete cells.")
    return [tuple(values[i:i+width]) for i in range(0, len(values), width)]


def _orient_cad_triangles(skin, nodes):
    """Orient across indexed edges, then distinguish exterior and void loops."""
    edges = defaultdict(list)
    for index, (a, b, c) in enumerate(skin):
        normal = cross(sub(nodes[b], nodes[a]), sub(nodes[c], nodes[a]))
        require(len({a, b, c}) == 3 and dot(normal, normal) > 0,
                f"CAD boundary triangle {index} has zero area.")
        for u, v in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((u, v)))].append((index, u < v))
    adjacent = defaultdict(list)
    for edge, owners in edges.items():
        require(len(owners) == 2, f"CAD boundary edge {edge} has {len(owners)} owners.")
        (a, a_forward), (b, b_forward) = owners
        flip = a_forward == b_forward
        adjacent[a].append((b, flip))
        adjacent[b].append((a, flip))
    reverse = {}
    for index in range(len(skin)):
        if index in reverse:
            continue
        todo = deque([index])
        reverse[index] = False
        while todo:
            current = todo.popleft()
            for neighbour, flip in adjacent[current]:
                orientation = reverse[current] ^ flip
                if neighbour in reverse:
                    require(reverse[neighbour] == orientation, f"CAD skin is nonorientable at facet {neighbour}.")
                else:
                    reverse[neighbour] = orientation
                    todo.append(neighbour)
    oriented = [face[::-1] if reverse[i] else face for i, face in enumerate(skin)]
    shells = shell_components(oriented, "CAD boundary")
    shells.sort(key=lambda faces: abs(signed_shell_volume(faces, nodes)), reverse=True)
    for index, shell in enumerate(shells):
        volume = signed_shell_volume(shell, nodes)
        require(math.isfinite(volume) and volume != 0, f"CAD boundary shell {index} has zero or invalid volume.")
        if (volume > 0) != (index == 0):
            shells[index] = [face[::-1] for face in shell]
    return shells

def _cad_skin(gmsh, source, request):
    model = gmsh.model
    model.add("CAD")
    gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
    model.occ.importShapes(str(source), highestDimOnly=False)
    model.occ.synchronize()
    volumes = model.getEntities(3)
    require(len(volumes) == 1, "Hex core requires one closed OCC solid.")
    from .gmsh_worker import _entity_closure
    owned = _entity_closure(gmsh, volumes[0])
    require(all(entity in owned for dim in (0, 1, 2) for entity in model.getEntities(dim)),
            "The CAD input contains unowned faces, curves or points.")
    gmsh.option.setNumber("Mesh.MeshSizeMax", request["boundary_size"])
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 24)
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    generate_checked(gmsh, 2)
    return read_solid_skin(gmsh, volumes[0][1], request)


def read_solid_skin(gmsh, solid, request):
    """Read one solid's portion of the active OCC model's complete triangle skin."""
    model = gmsh.model
    mass = model.occ.getMass(3, solid)
    require(math.isfinite(mass) and mass > 0, "CAD solid does not have positive volume.")
    boundary = model.getBoundary([(3, solid)], oriented=True)
    require(all(dim == 2 for dim, _ in boundary) and len(boundary) == len({abs(tag) for _, tag in boundary}),
            "CAD solid face ownership is ambiguous.")
    skin_by_face = {}
    # CAD face tags carry ownership. Mesh triangle winding is recovered by
    # edge adjacency since OCC face signs alone do not orient discrete triangles.
    for _, tag in boundary:
        skin_by_face[abs(tag)] = _connectivity(model, 2, abs(tag), 2, 3)
    skin = list(chain.from_iterable(skin_by_face.values()))
    xyz = _coordinates(model)
    nodes = {identifier: xyz[identifier] for identifier in set(chain.from_iterable(skin))}
    require(len(nodes) == len(set(nodes.values())), "CAD skin contains coincident node IDs.")
    shells = _orient_cad_triangles(skin, nodes)
    for shell in shells[1:]:
        require(_inside_plc(nodes[shell[0][0]], shells[0], nodes), "An inner CAD shell is outside its exterior.")
    oriented = {tuple(sorted(face)): face for face in chain.from_iterable(shells)}
    require(len(oriented) == len(skin), "CAD skin contains duplicate triangles.")
    skin_by_face = {tag: [oriented[tuple(sorted(face))] for face in triangles]
                    for tag, triangles in skin_by_face.items()}
    skin_volume = math.fsum(signed_shell_volume(facets, nodes) for facets in shells)
    require(abs(skin_volume - mass) / mass <= request["relative_volume_tolerance"],
            f"Faceted CAD volume {skin_volume:.9g} departs from OCC volume {mass:.9g}. Reduce boundary size.")
    return solid, mass, nodes, skin_by_face, shells, skin_volume


def _inside_plc(point, faces, nodes):
    """Classify relative to oriented triangular shells using signed solid angle."""
    def angle(face):
        a, b, c = (sub(nodes[node], point) for node in face)
        la, lb, lc = (math.sqrt(dot(v, v)) for v in (a, b, c))
        numerator = dot(a, cross(b, c))
        denominator = la*lb*lc + dot(a, b)*lc + dot(b, c)*la + dot(c, a)*lb
        return 2 * math.atan2(numerator, denominator)
    return abs(math.fsum(angle(face) for face in faces) - 4*math.pi) < 1e-5


def _add_nodes(model, dim, tag, ids, nodes):
    if ids:
        model.mesh.addNodes(dim, tag, ids, list(chain.from_iterable(nodes[i] for i in ids)))


def generate_checked(gmsh, dimension):
    gmsh.logger.start()
    try:
        gmsh.model.mesh.generate(dimension)
        errors = [line for line in gmsh.logger.get() if line.startswith("Error")]
    except Exception as error:
        raise PrepError("hybrid_hex_core", f"Gmsh {dimension}D meshing failed: {error}") from error
    finally:
        gmsh.logger.stop()
    require(not errors, f"Gmsh {dimension}D meshing reported errors: {' | '.join(errors[:4])}")

def _tet_fill(gmsh, nodes, shells, algorithm):
    model = gmsh.model
    model.add(f"annulus-{algorithm}")
    try:
        loops = []
        for i, shell in enumerate(shells, 1):
            surface = model.addDiscreteEntity(2, i)
            boundary_ids = sorted(set(chain.from_iterable(shell)))
            _add_nodes(model, 2, surface, boundary_ids, nodes)
            model.mesh.addElementsByType(surface, 2, [], list(chain.from_iterable(shell)))
            loops.append(model.geo.addSurfaceLoop([surface]))
        volume = model.geo.addVolume(loops)
        model.geo.synchronize()
        gmsh.option.setNumber("Mesh.Algorithm3D", algorithm)
        gmsh.option.setNumber("Mesh.MeshOnlyEmpty", 1)
        generate_checked(gmsh, 3)
        all_nodes = _coordinates(model)
        for i, shell in enumerate(shells, 1):
            expected = {tuple(sorted(face)) for face in shell}
            actual = _connectivity(model, 2, i, 2, 3)
            observed = {tuple(sorted(face)) for face in actual}
            require(len(actual) == len(shell) and expected == observed,
                    f"Tet fill changed fixed shell {i}: {len(expected-observed)} missing and "
                    f"{len(observed-expected)} new facets.")
            required_ids = set(chain.from_iterable(shell))
            require(all(all_nodes.get(i) == nodes[i] for i in required_ids),
                    f"Tet fill moved original nodes in fixed shell {i}.")
        tets = _connectivity(model, 3, volume, 4, 4)
        return all_nodes, tets
    finally:
        model.remove()


def _cell_quality(gmsh, ids_by_type, minimum, min_tet_sicn, expected_volume):
    from .gmsh_quality import FAMILIES, inspect_mesh_quality

    try:
        measured = inspect_mesh_quality(gmsh)["by_type"]
    except ValueError as error:
        raise PrepError("hybrid_hex_core", str(error)) from error
    physical = {FAMILIES[family][0]: len(ids) for family, ids in ids_by_type.items()}
    require(set(measured) == {*physical, "tri3"}, "In-memory hybrid family inventory changed before quality checks.")
    quality = {}
    for name, count in physical.items():
        row = measured[name]
        require(row["count"] == count, f"Unexpected number of {name} cells in the quality inventory.")
        floors = {
            "min_scaled_jacobian": minimum,
            "min_sdk_scaled_jacobian": 0.,
            "min_sicn": min_tet_sicn if name == "tet4" else 0.,
            "min_det_jacobian": 0.,
        }
        for metric, floor in floors.items():
            worst = row[metric]
            require(worst > 0 and worst >= floor,
                    f"{name} worst {metric}={worst:.6g} is below the quality floor {floor:.6g}.")
        require(not row["invalid_element_ids"],
                f"{name} has invalid cells {row['invalid_element_ids'][:8]}.")
        quality[name] = {
            "count": count,
            "minimum_scaled_jacobian": row["min_scaled_jacobian"],
            "minimum_sdk_scaled_jacobian": row["min_sdk_scaled_jacobian"],
            "minimum_sicn": row["min_sicn"],
            "minimum_determinant": row["min_det_jacobian"],
            "volume": row["measure"],
            "max_edge_aspect_ratio": row["max_edge_aspect_ratio"],
            "max_face_skewness": row["max_face_skewness"],
            "min_dihedral_degrees": row["min_dihedral_degrees"],
        }
    # Enforce cell volume against the fixed PL skin independently of CAD chord error.
    volume = math.fsum(row["volume"] for row in quality.values())
    require(math.isclose(volume, expected_volume, rel_tol=1e-8, abs_tol=0),
            f"Cell volume {volume:.9g} differs from fixed CAD skin volume {expected_volume:.9g}.")
    return quality, volume

def _final_model(gmsh, nodes, cells, skin_by_face, request, skin_volume):
    model = gmsh.model
    model.add("hex-core")
    used = set()
    next_element = 1
    for face_tag, triangles in sorted(skin_by_face.items()):
        surface = model.addDiscreteEntity(2, face_tag)
        ids = set(chain.from_iterable(triangles)) - used
        _add_nodes(model, 2, surface, sorted(ids), nodes)
        used.update(ids)
        model.mesh.addElementsByType(surface, 2, list(range(next_element, next_element+len(triangles))),
                                     list(chain.from_iterable(triangles)))
        next_element += len(triangles)
    solid = model.addDiscreteEntity(3, 1, sorted(skin_by_face))
    _add_nodes(model, 3, solid, sorted(nodes.keys() - used), nodes)
    ids_by_type = {}
    for family, element_nodes in sorted(cells.items()):
        ids = ids_by_type[family] = list(range(next_element, next_element+len(element_nodes)))
        model.mesh.addElementsByType(solid, family, ids, list(chain.from_iterable(element_nodes)))
        next_element += len(ids)
    quality, volume = _cell_quality(gmsh, ids_by_type,
                                    request["min_scaled_jacobian"], request.get("min_tet_sicn", .08), skin_volume)
    groups = model.addPhysicalGroup(3, [solid], 1)
    model.setPhysicalName(3, groups, "CAD solid")
    return quality, volume, ids_by_type


def _candidate(gmsh, nodes, core_cells, shells, skin_by_face, request, skin_volume):
    errors = []
    skin = list(chain.from_iterable(skin_by_face.values()))
    # Both algorithms use the same approved fixed input and both face audits.
    for algorithm in (10, 1):
        try:
            all_nodes, tets = _tet_fill(gmsh, nodes, shells, algorithm)
            for i, point in nodes.items():
                require(i not in all_nodes or all_nodes[i] == point,
                        f"Tet fill collides with original non-skin node ID {i}.")
            final_nodes = all_nodes | nodes
            cells = {4: tets, **core_cells}
            paired = audit_faces(final_nodes, cells, skin)
            quality, volume, ids_by_type = _final_model(
                gmsh, final_nodes, cells, skin_by_face, request, skin_volume)
            return final_nodes, cells, ids_by_type, paired, quality, volume, algorithm
        except PrepError as error:
            errors.append(f"algorithm {algorithm}: {error}")
            if gmsh.model.getCurrent() == "hex-core":
                gmsh.model.remove()
    raise PrepError("hybrid_hex_core", "Gmsh constrained fill rejected. " + " | ".join(errors))


def verify_sdk_export(gmsh, mesh_path, result, *, assembly=False):
    """Reopen published SDK bytes and confirm every solid and boundary record."""
    gmsh.clear()
    gmsh.open(str(mesh_path))
    model = gmsh.model
    expected_nodes = dict(result["nodes"])
    actual_nodes = _coordinates(model)
    require(actual_nodes.keys() == expected_nodes.keys() and all(
        all(abs(a-b) <= 8*math.ulp(b) for a, b in zip(point, expected_nodes[i]))
        for i, point in actual_nodes.items()), "Gmsh MSH reopen changed node IDs or coordinates.")
    if assembly:
        cells = result["blocks"]
        skin = {i: surface["triangles"] for i, surface in result["surfaces"].items()}
        names = {i: f"CAD solid {i}" for i in result["parts"]}
    else:
        cells = [[1, *block] for block in result["cells"]]
        skin = result["skin_by_face"]
        names = {1: "CAD solid"}
    require(set(model.getEntities(3)) == {(3, i) for i in names}, "Gmsh MSH reopen changed solid owners.")
    require(set(model.getEntities(2)) == {(2, i) for i in skin}, "Gmsh MSH reopen changed CAD face tags.")
    found_groups = {}
    for dim, tag in model.getPhysicalGroups():
        require(dim == 3, f"Unexpected physical group dimension {dim}.")
        owner = list(map(int, model.getEntitiesForPhysicalGroup(dim, tag)))
        require(len(owner) == 1 and owner[0] not in found_groups, f"Unexpected physical group members {owner}.")
        found_groups[owner[0]] = model.getPhysicalName(dim, tag)
    require(found_groups == names, "Gmsh MSH reopen changed named physical groups.")
    for i, faces in skin.items():
        require(_connectivity(model, 2, i, 2, 3) == faces, f"Gmsh MSH reopen changed CAD face {i}.")
    actual_families = {(solid, int(family)) for solid in names for family in model.mesh.getElementTypes(3, solid)}
    require(actual_families == {(solid, family) for solid, family, _, _ in cells},
            "Gmsh MSH reopen changed the volume family inventory.")
    for solid, family, expected_ids, expected_cells in cells:
        ids, conn = model.mesh.getElementsByType(family, solid)
        require(list(ids) == expected_ids and list(conn) == list(chain.from_iterable(expected_cells)),
                f"Gmsh MSH reopen changed solid {solid} family {family} element IDs or connectivity.")


def run(source, destination, request):
    import gmsh
    gmsh.initialize(readConfigFiles=False, interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.option.setNumber("Mesh.SaveAll", 1)
        gmsh.option.setNumber("Mesh.Renumber", 0)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.option.setNumber("Mesh.Binary", 0)
        solid_skin = _cad_skin(gmsh, source, request)
        result = mesh_solid(gmsh, solid_skin, request)
        mesh_path = destination / "mesh.msh"
        gmsh.write(str(mesh_path))
        verify_sdk_export(gmsh, mesh_path, result)
        result["sdk_reopen_verified"] = True
        return result
    finally:
        gmsh.finalize()


def mesh_solid(gmsh, solid_skin, request):
    """Mesh one pretriangulated solid, leaving its discrete result model active."""
    solid, mass, nodes, skin_by_face, shells, skin_volume = solid_skin
    skin = list(chain.from_iterable(shells))
    model = gmsh.model
    gmsh.option.setNumber("Mesh.Renumber", 0)
    reason = None
    metrics = {}
    try:
        bounds = model.getBoundingBox(3, solid)
        extent = max(b-a for a, b in zip(bounds[:3], bounds[3:]))
        tol = max(1e-7, extent * 1e-10, 64*math.ulp(max(map(abs, bounds))))
        pitch = request["core_size"]
        require(pitch >= 100 * tol, "Core pitch is too small relative to OCC/model tolerance.")
        origin, cubes, faces, metrics = select_core(
            model, solid, skin_by_face, skin, nodes, pitch, request["safety_margin"], tol)
        anchor = add(origin, scale(add(cubes[0], (.5, .5, .5)), pitch))
        require(_inside_plc(anchor, skin, nodes), "Hex core is outside the faceted CAD material.")
        hybrid_nodes = nodes.copy()
        core_cells, cavity = build_core(hybrid_nodes, origin, pitch, cubes, faces)
        require(len(shell_components(cavity, "Pyramid cavity")) == 1, "Pyramid cavity disconnected.")
        inner_volume = -signed_shell_volume(cavity, hybrid_nodes)
        expected = pitch**3 * (len(core_cells[5]) + len(core_cells[7])/12)
        require(math.isclose(inner_volume, expected, rel_tol=1e-8), "Pyramid cavity volume differs from its cell union.")
        require(inner_volume < skin_volume, "No positive volume remains for the tet annulus.")
        outcome = _candidate(gmsh, hybrid_nodes, core_cells, shells + [cavity],
                             skin_by_face, request, skin_volume)
    except PrepError as error:
        if not request["allow_tet_fallback"]:
            raise
        reason = str(error)
        outcome = _candidate(gmsh, nodes, {}, shells, skin_by_face, request, skin_volume)
    final_nodes, cells, ids_by_type, paired, quality, volume, algorithm = outcome

    return {"nodes": sorted(final_nodes.items()), "cells": [[family, ids_by_type[family], data]
            for family, data in sorted(cells.items())], "skin_by_face": skin_by_face,
            "quality": quality, "face_audit": paired, "core_audit": metrics, "cad_volume": mass,
            "faceted_volume": skin_volume, "mesh_volume": volume, "tet_algorithm": algorithm,
            "fallback_reason": reason, "backend_version": gmsh.__version__}


def main():
    source, folder, request_file = map(Path, sys.argv[1:])
    try:
        request = json.loads(request_file.read_text(encoding="utf-8"))
        if request.get("assembly", False):
            from .hybrid_assembly import generate_assembly
            result = generate_assembly({**request, "source": str(source), "output_dir": str(folder)})
            import gmsh
            gmsh.initialize(readConfigFiles=False, interruptible=False)
            try:
                gmsh.option.setNumber("General.Terminal", 0)
                verify_sdk_export(gmsh, folder / "mesh.msh", result, assembly=True)
                result["sdk_reopen_verified"] = True
            finally:
                gmsh.finalize()
        else:
            result = run(source, folder, request)
        result = {"ok": True, **result}
    except Exception as error:
        result = {"ok": False, "error": str(error)}
    (folder / "report.json").write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
