"""Transfinite meshing of prepared curvilinear OCC blocks and layered prisms."""
import math
from collections import defaultdict


def configure_blocks(gmsh, mesh_size, edge_seeds):
    """Propagate signed bias around opposite edges and across shared block faces."""
    model = gmsh.model
    dims = lambda d: [tag for _, tag in model.getEntities(d)]

    def boundary(dim, tag):
        return [i for _, i in model.getBoundary([(dim, tag)], oriented=False, combined=False)]

    surfaces = dims(2)
    solids = dims(3)
    if not solids or any(len(boundary(3, tag)) != 6 for tag in solids):
        raise ValueError("Partition the CAD into six-face sweep blocks before mapped meshing")
    edges = dims(1)
    if set(edge_seeds) - set(edges):
        raise ValueError("An edge seed refers to a curve outside this CAD import")
    ends = {}
    for edge in edges:
        nodes = boundary(1, edge)
        if len(set(nodes)) != 2:
            raise ValueError(f"Closed or collapsed guide curve {edge} requires a block partition")
        u, _ = model.getParametrizationBounds(1, edge)
        first = model.getValue(1, edge, u)
        ends[edge] = sorted(nodes, key=lambda n: math.dist(first, model.getValue(0, n, [])))
    neighbors = defaultdict(list)
    for face in surfaces:
        rim = boundary(2, face)
        if len(set(rim)) != 4 or len(rim) != 4:
            raise ValueError(f"Face {face} needs four distinct block edges")
        for edge in rim:
            opposite = [e for e in rim if set(ends[e]).isdisjoint(ends[edge])]
            if len(opposite) != 1:
                raise ValueError(f"Ambiguous opposite edge on face {face}")
            other = opposite[0]
            pair = {ends[edge][0], ends[other][0]}
            same_direction = any(set(ends[e]) == pair for e in rim)
            neighbors[edge].append((other, 1 if same_direction else -1))
    settings = {}
    for start in edges:
        if start in settings:
            continue
        orientation, pending, twisted = {start: 1}, [start], False
        while pending:
            edge = pending.pop()
            for other, sign in neighbors[edge]:
                required = sign * orientation[edge]
                if other in orientation:
                    twisted |= orientation[other] != required
                else:
                    orientation[other] = required
                    pending.append(other)
        prescribed = []
        for edge, direction in orientation.items():
            if edge in edge_seeds:
                n, mode, value = edge_seeds[edge]
                prescribed.append((n, mode, value ** direction if mode == "Progression" else value))
        if prescribed:
            n, mode, factor = prescribed[0]
            if any((n, mode) != entry[:2] or not math.isclose(factor, entry[2]) for entry in prescribed):
                raise ValueError(f"Incompatible seeds on shared or opposite curves {sorted(orientation)}")
            if twisted and mode == "Progression" and factor != 1:
                raise ValueError("Asymmetric progression cannot close around an orientation-reversing loop")
        else:
            n = max(1, math.ceil(max(model.occ.getMass(1, e) for e in orientation) / mesh_size))
            mode, factor = "Progression", 1.0
        for edge, direction in orientation.items():
            coef = factor ** direction if mode == "Progression" else factor
            model.mesh.setTransfiniteCurve(edge, n + 1, mode, coef)
            settings[edge] = (n, mode, coef)
    for face in surfaces:
        model.mesh.setTransfiniteSurface(face)
        model.mesh.setRecombine(2, face)
    for solid in solids:
        model.mesh.setTransfiniteVolume(solid)
    return {str(edge): list(seed) for edge, seed in sorted(settings.items())}


def configure_curvature(gmsh, samples, gradient, minimum, maximum):
    """Bound target growth away from curved CAD faces using a distance threshold."""
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", samples)
    curved = [tag for _, tag in gmsh.model.getEntities(2) if gmsh.model.getType(2, tag) != "Plane"]
    if gradient is not None and curved:
        fields = gmsh.model.mesh.field
        distance = fields.add("Distance")
        fields.setNumbers(distance, "SurfacesList", curved)
        threshold = fields.add("Threshold")
        for key, value in {"InField": distance, "SizeMin": minimum, "SizeMax": maximum,
                           "DistMin": 0, "DistMax": (maximum - minimum) / gradient}.items():
            fields.setNumber(threshold, key, value)
        fields.setAsBackgroundMesh(threshold)
    return curved


def _equivalent_sweep_faces(occ, original, swept):
    """Use trimmed face intersections to retain a bijection to the imported CAD."""
    def faces(solid):
        _, loops = occ.getSurfaceLoops(solid)
        return {int(tag): occ.getMass(2, int(tag)) for loop in loops for tag in loop}

    source = faces(original)
    target = faces(swept)
    if len(source) != len(target):
        raise ValueError("The wall sweep changes the CAD face partition")
    correspondence = {}
    for tag, area in source.items():
        matches = []
        for candidate, other_area in target.items():
            if not math.isclose(area, other_area, rel_tol=1e-9):
                continue
            common, _ = occ.intersect(occ.copy([(2, tag)]), occ.copy([(2, candidate)]))
            try:
                overlap = sum(occ.getMass(2, face) for dim, face in common if dim == 2)
            finally:
                occ.remove(common, recursive=True)
            if math.isclose(area, overlap, rel_tol=1e-9):
                matches.append(candidate)
        if len(matches) != 1 or matches[0] in correspondence.values():
            raise ValueError(f"The wall sweep cannot preserve the trimmed region of CAD face {tag}")
        correspondence[tag] = matches[0]
    return correspondence


def configure_prismatic_layers(gmsh, request):
    """Certify the selected planar source sweep against the original OCC material."""
    model, occ = gmsh.model, gmsh.model.occ
    volumes = model.getEntities(3)
    face = request["face"]
    vector = request["vector"]
    if len(volumes) != 1 or (2, face) not in model.getBoundary(volumes, oriented=False):
        raise ValueError("Select a face of a single closed prismatic CAD solid")
    if model.getType(2, face) != "Plane":
        raise ValueError("This prismatic boundary layer requires a planar starting face")
    normal = model.getNormal(face, [0, 0])
    if abs(sum(n*v for n, v in zip(normal, vector))) < (1 - 1e-9) * math.hypot(*vector):
        raise ValueError("The layer vector must be normal to the selected wall")
    exact = occ.getMass(*volumes[0])
    source = occ.copy([(2, face)])
    heights = request["heights"]
    generated = occ.extrude(source, *vector, numElements=[1] * len(heights), heights=heights, recombine=True)
    swept = [entity for entity in generated if entity[0] == 3]
    if len(swept) != 1:
        raise ValueError("Could not construct the complete prismatic sweep")
    intersection, _ = occ.intersect(occ.copy(volumes), occ.copy(swept))
    overlap = sum(occ.getMass(*entity) for entity in intersection if entity[0] == 3)
    swept_mass = occ.getMass(*swept[0])
    if exact <= 0 or max(abs(exact-overlap), abs(swept_mass-overlap)) > 1e-9 * exact:
        raise ValueError("Wall extrusion does not match the complete CAD solid within OCC volume tolerance")
    face_map = _equivalent_sweep_faces(occ, volumes[0][1], swept[0][1])
    occ.remove(intersection + volumes, recursive=True)
    occ.synchronize()
    return {"original_volume": exact, "verified_overlap": overlap, "source_face": face,
            "source_to_mesh_face_tags": face_map,
            "layer_vector": vector, "normalized_heights": heights}
