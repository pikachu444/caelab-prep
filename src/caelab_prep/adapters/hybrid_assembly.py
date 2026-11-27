"""Conformal hybrid assemblies sharing one fragmented OCC surface triangulation."""
from collections import defaultdict
from itertools import chain
from pathlib import Path

from .gmsh_worker import _prepare_interfaces
from .hybrid_hex_core_geometry import audit_faces, require, same_cycle
from .hybrid_hex_core_worker import _coordinates, generate_checked, mesh_solid, read_solid_skin


def assemble(gmsh, part_results, all_skin_ids):
    """Renumber only private nodes. Shared identifiers originate on the common CAD skin."""
    next_node = max(all_skin_ids) + 1
    nodes, faces, owners = {}, {}, defaultdict(list)
    part_cells, part_boundaries, reports = {}, {}, {}
    for solid, part in part_results:
        local_skin = part["skin_by_face"]
        skin_nodes = set(chain.from_iterable(chain.from_iterable(local_skin.values())))
        remap = {}
        for n, xyz in part["nodes"]:
            if n in skin_nodes:
                require(n not in nodes or nodes[n] == xyz, f"CAD interface node {n} moved on part {solid}")
                allocated = n
            else:
                allocated = next_node
                next_node += 1
            nodes[allocated] = xyz
            remap[n] = allocated
        part_boundaries[solid] = []
        for face, tris in local_skin.items():
            orientation = 1
            if face in faces:
                old = {tuple(sorted(tri)): tri for tri in faces[face]}
                require(len(owners[face]) == 1 and len(old) == len(tris)
                        and all(tuple(sorted(t)) in old and same_cycle(old[tuple(sorted(t))], t[::-1])
                                for t in tris), f"Shared CAD surface {face} has inconsistent oriented triangles")
                orientation = -1
            else:
                faces[face] = tris
            owners[face].append(solid)
            part_boundaries[solid].append(orientation * face)
        part_cells[solid] = {typ: [tuple(remap[n] for n in row) for row in rows]
                             for typ, _, rows in part["cells"]}
        reports[solid] = {key: part[key] for key in ("quality", "cad_volume", "mesh_volume",
                          "faceted_volume", "tet_algorithm", "face_audit", "fallback_reason", "core_audit")}
    combined = defaultdict(list)
    for typed in part_cells.values():
        for typ, rows in typed.items():
            combined[typ].extend(rows)
    exterior = [tri for face, triangles in faces.items() if len(owners[face]) == 1 for tri in triangles]
    require(len(nodes) == len(set(nodes.values())), "Unexpected coincident IDs in conformal hybrid assembly")
    audit = audit_faces(nodes, combined, exterior)
    model = gmsh.model
    model.add("hybrid-assembly")
    used, next_cell, blocks = set(), 1, []
    def add_nodes(dim, tag, required):
        ids = sorted(required - used)
        if ids:
            model.mesh.addNodes(dim, tag, ids, list(chain.from_iterable(nodes[n] for n in ids)))
            used.update(ids)
    for face, tris in sorted(faces.items()):
        model.addDiscreteEntity(2, face)
        add_nodes(2, face, set(chain.from_iterable(tris)))
        model.mesh.addElementsByType(face, 2, list(range(next_cell, next_cell + len(tris))),
                                     list(chain.from_iterable(tris)))
        next_cell += len(tris)
    for solid, typed in sorted(part_cells.items()):
        model.addDiscreteEntity(3, solid, part_boundaries[solid])
        add_nodes(3, solid, {n for rows in typed.values() for row in rows for n in row})
        for typ, rows in sorted(typed.items()):
            ids = list(range(next_cell, next_cell + len(rows)))
            model.mesh.addElementsByType(solid, typ, ids, list(chain.from_iterable(rows)))
            blocks.append([solid, typ, ids, rows])
            next_cell += len(rows)
        model.setPhysicalName(3, model.addPhysicalGroup(3, [solid]), f"CAD solid {solid}")
    require(used == nodes.keys(), "Unused nodes in merged hybrid assembly")
    return dict(nodes=sorted(nodes.items()), blocks=blocks, parts=reports, face_audit=audit,
                surfaces={tag: {"owners": owners[tag], "triangles": tris} for tag, tris in faces.items()})


def generate_assembly(request):
    import gmsh
    source = Path(request["source"])
    gmsh.initialize(readConfigFiles=False, interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setNumber("Mesh.Renumber", 0)
        gmsh.option.setNumber("Mesh.SaveAll", 1)
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.option.setNumber("Mesh.Binary", 0)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        model = gmsh.model
        model.add("assembly-cad")
        model.occ.importShapes(str(source), highestDimOnly=False)
        model.occ.synchronize()
        preparation, closures = _prepare_interfaces(gmsh, "conformal", source.suffix.lower())
        solids = sorted(closures)
        require(solids, "Provide closed OCC solids for an assembly")
        owned = {s for closure in closures.values() for s in closure}
        require(all(entity in owned for dim in (0, 1, 2) for entity in model.getEntities(dim)),
                "Assembly contains unowned lower-dimensional CAD entities")
        gmsh.option.setNumber("Mesh.MeshSizeMax", request["boundary_size"])
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 24)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        generate_checked(gmsh, 2)
        all_ids = _coordinates(model).keys()
        def parts():
            for solid in solids:
                model.setCurrent("assembly-cad")
                part = mesh_solid(gmsh, read_solid_skin(gmsh, solid, request), request)
                model.remove()
                yield solid, part
        result = assemble(gmsh, parts(), all_ids)
        output = Path(request["output_dir"]) / "mesh.msh"
        gmsh.write(str(output))
        return {**result, "schema_version": 1, "backend_version": gmsh.__version__,
                "mesh_path": str(output), "preparation": preparation}
    finally:
        gmsh.finalize()
