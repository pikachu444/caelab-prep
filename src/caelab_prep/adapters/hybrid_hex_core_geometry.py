"""Geometry and incidence checks for the uniform Cartesian hex-core worker."""

from collections import defaultdict, deque
from itertools import product
import math

from ..cae_core.errors import PrepError


CORNERS = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
           (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
DIRECTIONS = ((0, 0, -1), (0, 0, 1), (0, -1, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0))
HEX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
CELL_FACES = {
    4: ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)),
    5: HEX_FACES,
    7: ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)),
}
MAX_GRID_VOXELS = 100_000


def require(condition, message):
    if not condition:
        raise PrepError("hybrid_hex_core", message)


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scale(a, factor):
    return tuple(value * factor for value in a)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])


def use_ids(nodes, indices):
    return tuple(nodes[i] for i in indices)


def opposite(a, b):
    rev = b[::-1]
    return any(a == rev[i:] + rev[:i] for i in range(len(rev)))


def same_cycle(a, b):
    return opposite(a, b[::-1])


def _face_edges(face):
    return zip(face, face[1:] + face[:1])


def _shell_topology(faces):
    edge_faces = defaultdict(list)
    vertex_link = defaultdict(lambda: defaultdict(list))
    for index, face in enumerate(faces):
        for u, v in _face_edges(face):
            edge_faces[tuple(sorted((u, v)))].append((index, u, v))
        for i, v in enumerate(face):
            a, b = face[i-1], face[(i+1) % len(face)]
            vertex_link[v][a].append(b)
            vertex_link[v][b].append(a)
    bad_nodes = set()
    neighbours = [[] for _ in faces]
    for edge, incident in edge_faces.items():
        if len(incident) != 2 or incident[0][1:] != incident[1][1:][::-1]:
            bad_nodes.update(edge)
            continue
        a, b = (item[0] for item in incident)
        neighbours[a].append(b)
        neighbours[b].append(a)
    for vertex, link in vertex_link.items():
        if any(len(items) != 2 for items in link.values()):
            bad_nodes.add(vertex)
            continue
        if len(_connected(next(iter(link)), link.__getitem__)) != len(link):
            bad_nodes.add(vertex)
    return bad_nodes, neighbours


def _connected(start, neighbours):
    seen = {start}
    todo = deque([start])
    while todo:
        for node in neighbours(todo.popleft()):
            if node not in seen:
                seen.add(node)
                todo.append(node)
    return seen


def shell_components(faces, description):
    require(bool(faces), f"{description} is empty.")
    bad_nodes, neighbours = _shell_topology(faces)
    require(not bad_nodes, f"{description} is not an oriented two-manifold at nodes {sorted(bad_nodes)[:8]}.")
    outstanding = set(range(len(faces)))
    components = []
    while outstanding:
        component = _connected(min(outstanding), neighbours.__getitem__)
        components.append([faces[i] for i in sorted(component)])
        outstanding.difference_update(component)
    return components


def signed_shell_volume(faces, nodes):
    origin = nodes[faces[0][0]]
    return math.fsum(
        dot(sub(nodes[a], origin), cross(sub(nodes[b], origin), sub(nodes[c], origin))) / 6
        for a, b, c in faces
    )


def _largest_core_component(cubes):
    remaining = set(cubes)
    best = set()
    while remaining:
        start = min(remaining)
        component = _connected(start, lambda p: (q for d in DIRECTIONS if (q := add(p, d)) in cubes))
        if len(component) > len(best):
            best = component
        remaining.difference_update(component)
    return best


def _grid_faces(cubes):
    faces = []
    for cube in sorted(cubes):
        vertices = tuple(add(cube, shift) for shift in CORNERS)
        for direction, indices in zip(DIRECTIONS, HEX_FACES):
            if add(cube, direction) not in cubes:
                faces.append((direction, use_ids(vertices, indices)))
    return faces


def _point_triangle_distance_squared(p, triangle):
    a, b, c = triangle
    ab, ac = sub(b, a), sub(c, a)
    n = cross(ab, ac)
    normal_squared = dot(n, n)
    require(normal_squared > 0, "A CAD boundary triangle has zero area.")
    segments = ((a, b), (b, c), (c, a))
    offset = sub(p, a)
    normal_distance = dot(n, offset)
    projection = sub(p, scale(n, normal_distance / normal_squared))
    if all(dot(n, cross(sub(v, u), sub(projection, u))) >= 0 for u, v in segments):
        return normal_distance**2 / normal_squared
    distances = []
    for u, v in segments:
        edge, delta = sub(v, u), sub(p, u)
        nearest = min(1., max(0., dot(delta, edge) / dot(edge, edge)))
        residual = sub(delta, scale(edge, nearest))
        distances.append(dot(residual, residual))
    return min(distances)


def _filter_skin_clearance(cubes, skin, nodes, origin, dimensions, pitch, clearance):
    if not cubes:
        return cubes, 0
    rejected = set()
    pad = clearance / pitch
    for facet in skin:
        triangle = tuple(nodes[i] for i in facet)
        spans = []
        for axis in range(3):
            relative = [(point[axis] - origin[axis]) / pitch - .5 for point in triangle]
            lower = max(0, math.ceil(min(relative) - pad))
            upper = min(dimensions[axis]-1, math.floor(max(relative) + pad))
            spans.append(range(lower, upper+1))
        for cube in product(*spans):
            if cube in cubes and cube not in rejected:
                center = add(origin, scale(add(cube, (.5, .5, .5)), pitch))
                if _point_triangle_distance_squared(center, triangle) <= clearance**2:
                    rejected.add(cube)
    return cubes - rejected, len(rejected)


def _quad_shell_volume(shell):
    origin = shell[0][0]
    return math.fsum(dot(sub(a, origin), cross(sub(b, origin), sub(c, origin))) / 6
                     for a, q, r, s in shell for b, c in ((q, r), (r, s)))


def _face_owner(direction, face):
    # A grid face lies at the owner's lower coordinate in its outward axis
    # for a negative normal, and at its upper coordinate for a positive one.
    return tuple(min(node[axis] for node in face) - max(0, direction[axis]) for axis in range(3))


def _opening_channel(cubes, faces, shells):
    """Find a shortest face-connected tunnel between exterior and void shells."""
    shell_order = sorted(shells, key=lambda shell: abs(_quad_shell_volume(shell)), reverse=True)
    owners = {face: _face_owner(direction, face) for direction, face in faces}
    exterior = sorted({owners[face] for face in shell_order[0]})
    target = {owners[face] for shell in shell_order[1:] for face in shell}
    queue = deque(exterior)
    parents = dict.fromkeys(exterior)
    while queue:
        cell = queue.popleft()
        if cell in target:
            channel = {cell}
            while parents[cell] is not None:
                cell = parents[cell]
                channel.add(cell)
            return channel
        for direction in DIRECTIONS:
            neighbour = add(cell, direction)
            if neighbour in cubes and neighbour not in parents:
                parents[neighbour] = cell
                queue.append(neighbour)
    raise PrepError("hybrid_hex_core", "Could not open a channel from the core exterior to an enclosed shell.")

def _add_back_core_cells(cubes, admissible):
    """Grow to a fixed point of single-voxel additions in sorted order."""
    frontier = {neighbour for cube in cubes for direction in DIRECTIONS
                if (neighbour := add(cube, direction)) in admissible and neighbour not in cubes}
    boundary = {tuple(sorted(face)): face for _, face in _grid_faces(cubes)}
    restored = 0
    while frontier:
        changed = False
        for cube in sorted(frontier):
            removed = {}
            inserted = []
            vertices = tuple(add(cube, shift) for shift in CORNERS)
            for indices in HEX_FACES:
                face = use_ids(vertices, indices)
                key = tuple(sorted(face))
                if key in boundary:
                    removed[key] = boundary.pop(key)
                else:
                    boundary[key] = face
                    inserted.append(key)
            faces = list(boundary.values())
            bad_nodes, adjacent = _shell_topology(faces)
            if bad_nodes or len(_connected(0, adjacent.__getitem__)) != len(faces):
                for key in inserted:
                    del boundary[key]
                boundary.update(removed)
                continue
            cubes.add(cube)
            changed = True
            restored += 1
            frontier.remove(cube)
            frontier.update(neighbour for direction in DIRECTIONS
                            if (neighbour := add(cube, direction)) in admissible and neighbour not in cubes)
        if not changed:
            break
    return restored

def select_core(model, solid, cad_faces, skin, nodes, pitch, safety_margin, kernel_tol):
    bbox = model.getBoundingBox(3, solid)
    origin = bbox[:3]
    dimensions = tuple(math.floor((upper - lower) / pitch) for lower, upper in zip(origin, bbox[3:]))
    require(all(n > 0 for n in dimensions), "The core pitch exceeds at least one CAD extent.")
    voxels = math.prod(dimensions)
    require(voxels <= MAX_GRID_VOXELS, f"Grid requires {voxels} voxels, beyond the {MAX_GRID_VOXELS} limit.")
    # Every point in a cube and its h=s/4 transition pyramids lies in
    # the cube's circumradius ball; certify that ball against CAD and PLC.
    clearance = math.sqrt(3) * pitch / 2 + safety_margin + kernel_tol
    require(math.isfinite(clearance), "CAD clearance is outside the supported numeric range.")
    face_bounds = [(tag, model.getBoundingBox(2, tag)) for tag in cad_faces]
    candidates = set()
    for cube in product(*(range(n) for n in dimensions)):
        center = add(origin, scale(add(cube, (.5, .5, .5)), pitch))
        if not model.isInside(3, solid, center):
            continue
        nearby = [tag for tag, box in face_bounds if all(
            lo - clearance <= value <= hi + clearance for lo, hi, value in zip(box[:3], box[3:], center))]
        point = model.occ.addPoint(*center)
        try:
            for tag in nearby:
                distance = model.occ.getDistance(0, point, 2, tag)[0]
                require(math.isfinite(distance) and distance >= 0, f"OCC distance failed for face {tag}.")
                if distance <= clearance:
                    break
            else:
                candidates.add(cube)
        finally:
            model.occ.remove([(0, point)])
    admissible, skin_trimmed = _filter_skin_clearance(candidates, skin, nodes, origin, dimensions, pitch, clearance)
    initial = _largest_core_component(admissible)
    require(initial, "No connected hexahedral core with the requested CAD clearance survives trimming.")
    cubes = initial.copy()
    component_trimmed = len(admissible) - len(cubes)
    pinch_trimmed = 0
    channel_trimmed = 0
    channels = 0
    while cubes:
        faces = _grid_faces(cubes)
        boundary = [face for _, face in faces]
        bad_nodes, _ = _shell_topology(boundary)
        if bad_nodes:
            touching = {sub(vertex, corner) for vertex in bad_nodes for corner in CORNERS}
            remaining = _largest_core_component(cubes - touching)
            pinch_trimmed += len(cubes) - len(remaining)
        else:
            shells = shell_components(boundary, "Hex core boundary")
            if len(shells) == 1:
                break
            channel = _opening_channel(cubes, faces, shells)
            channels += 1
            channel_trimmed += len(channel)
            after_opening = cubes - channel
            remaining = _largest_core_component(after_opening)
            component_trimmed += len(after_opening) - len(remaining)
        cubes = remaining
    seeded_from_single_cell = not cubes
    if seeded_from_single_cell:
        cubes = {min(initial)}
    restored = _add_back_core_cells(cubes, initial)
    faces = _grid_faces(cubes)
    metrics = {"grid_voxels": voxels, "cad_clear_voxels": len(candidates),
               "skin_trimmed": skin_trimmed, "component_trimmed": component_trimmed,
               "pinch_trimmed": pinch_trimmed, "channel_trimmed": channel_trimmed,
               "channels": channels, "restored_voxels": restored,
               "seeded_from_single_cell": seeded_from_single_cell,
               "core_voxels": len(cubes), "clearance": clearance}
    return origin, sorted(cubes), faces, metrics


def build_core(nodes, origin, pitch, cubes, faces):
    vertex_ids = {}
    cells = {5: [], 7: []}
    next_id = max(nodes) + 1
    for cube in cubes:
        hex_nodes = []
        for corner in CORNERS:
            vertex = add(cube, corner)
            if vertex not in vertex_ids:
                vertex_ids[vertex] = next_id
                nodes[next_id] = add(origin, scale(vertex, pitch))
                next_id += 1
            hex_nodes.append(vertex_ids[vertex])
        cells[5].append(tuple(hex_nodes))
    # Bases point out of the core. Within an adjacent empty cube, each
    # pyramid is contained in the disjoint pyramidal region of its source face.
    cavity = []
    for direction, face in faces:
        base = tuple(vertex_ids[corner] for corner in face)
        center = tuple(math.fsum(nodes[i][axis] for i in base) / 4 for axis in range(3))
        nodes[next_id] = add(center, scale(direction, pitch / 4))
        cells[7].append((*base, next_id))
        cavity.extend((v, u, next_id) for u, v in _face_edges(base))
        next_id += 1
    return cells, cavity


def audit_faces(nodes, cells, skin):
    require(len(nodes) == len(set(nodes.values())), "Coincident node IDs exist in the hybrid mesh.")
    expected = {tuple(sorted(face)): face for face in skin}
    require(len(expected) == len(skin), "Prescribed CAD skin contains duplicate triangles.")
    owners = defaultdict(list)
    used = set()
    for family, elements in cells.items():
        seen = set()
        for element in elements:
            key = tuple(sorted(element))
            require(len(set(element)) == len(element) and key not in seen,
                    f"Duplicate connectivity in element family {family}, nodes {element}.")
            seen.add(key)
            used.update(element)
            for indices in CELL_FACES[family]:
                face = use_ids(element, indices)
                owners[tuple(sorted(face))].append((family, face))
    require(used == nodes.keys(), "The hybrid mesh contains unused or unregistered physical node IDs.")
    skin_count = 0
    quad_pairs = 0
    transition_triangles = 0
    for key, found in owners.items():
        if key in expected:
            require(len(found) == 1 and found[0][0] == 4 and same_cycle(expected[key], found[0][1]),
                    f"Prescribed CAD facet {key} lacks its correctly oriented tetrahedral owner.")
            skin_count += 1
            continue
        require(len(found) == 2, f"Internal face {key} has {len(found)} owners.")
        (family_a, a), (family_b, b) = found
        require(opposite(a, b), f"Internal face {key} has conflicting winding.")
        pair = {family_a, family_b}
        if len(key) == 4:
            require(pair in ({5}, {5, 7}), f"Quad face {key} has unsupported owners {pair}.")
            quad_pairs += pair == {5, 7}
        else:
            require(pair in ({4}, {4, 7}), f"Triangle face {key} has unsupported owners {pair}.")
            transition_triangles += pair == {4, 7}
    require(skin_count == len(expected), "Prescribed CAD skin was not fully recovered.")
    require(quad_pairs == len(cells.get(7, ())) and transition_triangles == 4 * quad_pairs,
            "Hex-to-pyramid and pyramid-to-tet face counts disagree.")
    return {"external_triangle_faces": skin_count, "hex_pyramid_faces": quad_pairs,
            "pyramid_tet_faces": transition_triangles}
