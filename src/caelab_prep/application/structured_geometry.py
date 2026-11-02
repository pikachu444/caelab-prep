"""Pure geometry admission for explicit planar patches and straight sweeps.

The fixed gates apply only after exact source-lattice matching. Twenty-seven
Hex8 samples are not a validity proof for arbitrary trilinear elements. This
module imports no SDK, UI, evaluation script or solver implementation.
"""
from collections import Counter, defaultdict
import itertools
import json
import math
from ..cae_core.errors import PrepError

MAX_ELEMENTS = 250_000
MAX_NODES = 500_000
MAX_RECIPE_BYTES = 1024 * 1024
CONTRACT = {
    "coordinate_relative_tolerance": 1e-9, "relative_measure_tolerance": 1e-9,
    "quad_min_corner_signed_scaled_jacobian": .30, "quad_max_edge_aspect_ratio": 8,
    "hex_min_sampled_scaled_jacobian": .25, "hex_max_edge_aspect_ratio": 10,
    "hex_samples": (-1, 0, 1),
}
SIDES_Q=((0,1),(1,2),(2,3),(3,0))
SIDES_H=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
EDGES_H=SIDES_Q+((4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7))
SIGNS=((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))

def sub(a, b):
    return tuple((x - y for x, y in zip(a, b)))

def dot(a, b):
    return sum((x * y for x, y in zip(a, b)))

def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

def norm(a):
    return math.sqrt(dot(a, a))

def vec(v):
    if len(v) != 3 or any((type(x) not in (int, float) or not math.isfinite(x) for x in v)):
        raise ValueError('finite xyz required')
    return tuple(v)

def count(v):
    if type(v) is not int or not 1 <= v <= 10000:
        raise ValueError('divisions must be integer 1..10000')
    return v

def exact_keys(value, keys, optional=()):
    if not isinstance(value, dict):
        raise ValueError('recipe fields must be a JSON object')
    missing = set(keys) - value.keys()
    unknown = value.keys() - set(keys) - set(optional)
    if missing or unknown:
        raise ValueError('unsupported or missing recipe fields: ' + repr(dict(missing=sorted(missing), unknown=sorted(unknown))))

def _validate(spec):
    if not isinstance(spec, dict):
        raise ValueError('recipe must be a JSON object')
    fields = {'line': ('points', 'divisions'), 'arc': ('center', 'start', 'end', 'divisions'), 'quad': ('corners', 'divisions'), 'hex': ('corners', 'divisions', 'vector', 'layers')}
    if spec.get('mode') not in fields:
        raise ValueError('unsupported recipe mode')
    exact_keys(spec, ('mode', 'unit', *fields[spec['mode']]), ('name',))
    if 'name' in spec and (not isinstance(spec['name'], str)):
        raise ValueError('optional recipe name must be text')
    if spec.get('unit') not in ('mm', 'cm', 'm'):
        raise ValueError('explicit length unit required')
    mode = spec['mode']
    if mode == 'line':
        a, b = [vec(p) for p in spec['points']]
        n = count(spec['divisions'])
        length = norm(sub(b, a))
        if length <= 1e-10:
            raise ValueError('zero length')
        return dict(measure=length, expected=n)
    if mode == 'arc':
        c, a, b = [vec(spec[k]) for k in ('center', 'start', 'end')]
        u, v = (sub(a, c), sub(b, c))
        r = norm(u)
        rr = norm(v)
        if r <= 1e-10 or abs(rr - r) > r * 1e-09:
            raise ValueError('equal positive radii required')
        angle = math.acos(max(-1, min(1, dot(u, v) / (r * rr))))
        if not 1e-06 < angle < math.pi - 1e-06:
            raise ValueError('only unique short arc with angle below pi is supported')
        return dict(measure=r * angle, expected=count(spec['divisions']), angle=angle)
    if mode not in ('quad', 'hex'):
        raise ValueError('unsupported recipe')
    p = [vec(x) for x in spec['corners']]
    if len(p) != 4:
        raise ValueError('exactly four boundary-ordered corners required')
    n = cross(sub(p[1], p[0]), sub(p[3], p[0]))
    area0 = norm(n)
    scale = max((norm(sub(x, p[0])) for x in p))
    if area0 <= max(scale * scale * 1e-12, 1e-20):
        raise ValueError('degenerate face')
    if abs(dot(sub(p[2], p[0]), n)) > area0 * scale * 1e-10:
        raise ValueError('non-planar face outside supported scope')
    for i in range(4):
        if dot(cross(sub(p[(i + 1) % 4], p[i]), sub(p[(i + 2) % 4], p[(i + 1) % 4])), n) <= 0:
            raise ValueError('strict convex boundary order required')
    area = sum(dot(cross(sub(p[i], p[0]), sub(p[i + 1], p[0])), n) for i in (1, 2)) / (2 * area0)
    nx, ny = map(count, spec['divisions'])
    measure = area
    expected = nx * ny
    if mode == 'hex':
        v = vec(spec['vector'])
        height = dot(v, n) / area0
        if height <= scale * 1e-10:
            raise ValueError('positive extrusion along source normal required')
        measure *= height
        expected *= count(spec['layers'])
    return dict(measure=measure, expected=expected)

def _normalize(spec):
    """Two patches share topology only through explicit vertex IDs."""
    if not isinstance(spec, dict):
        raise ValueError('recipe must be a JSON object')
    if 'patches' not in spec:
        return ([spec], _validate(spec), None)
    if spec.get('mode') not in ('quad', 'hex'):
        raise ValueError('shared patches require quad or hex mode')
    exact_keys(spec, ('mode', 'unit', 'vertices', 'patches', *(('vector', 'layers') if spec['mode'] == 'hex' else ())), ('name',))
    patches = spec['patches']
    if len(patches) != 2:
        raise ValueError('this experiment supports exactly two adjacent patches')
    vertices = {key: vec(value) for key, value in spec['vertices'].items()}
    if any((not isinstance(key, str) or not key for key in vertices)):
        raise ValueError('explicit nonempty vertex IDs required')
    for patch in patches:
        exact_keys(patch, ('id', 'corners', 'divisions'))
        if not isinstance(patch['id'], str) or not patch['id']:
            raise ValueError('explicit nonempty patch IDs required')
    if len({patch['id'] for patch in patches}) != 2:
        raise ValueError('distinct patch IDs required')
    singles, expectations, edges = ([], [], {})
    for patch in patches:
        ids = patch['corners']
        if len(ids) != 4 or len(set(ids)) != 4:
            raise ValueError('four distinct explicit vertex IDs required')
        single = {key: value for key, value in spec.items() if key not in ('vertices', 'patches')}
        single.update(corners=[vertices[key] for key in ids], divisions=patch['divisions'])
        expectations.append(_validate(single))
        singles.append(single)
        for i in range(4):
            edge = frozenset((ids[i], ids[(i + 1) % 4]))
            edges.setdefault(edge, []).append(patch['divisions'][i % 2])
    shared = [edge for edge, counts in edges.items() if len(counts) == 2]
    if len(shared) != 1:
        raise ValueError('exactly one explicit shared edge required; coordinates are not merged')
    edge = shared[0]
    if set(patches[0]['corners']) & set(patches[1]['corners']) != edge:
        raise ValueError('patches may share only the declared edge vertices')
    if len(set(edges[edge])) != 1:
        raise ValueError('shared-edge division counts must agree')
    p = singles[0]['corners']
    normal = cross(sub(p[1], p[0]), sub(p[3], p[0]))
    scale = max((norm(sub(v, p[0])) for single in singles for v in single['corners']))
    if any((abs(dot(sub(v, p[0]), normal)) > norm(normal) * scale * 1e-10 for v in singles[1]['corners'])):
        raise ValueError('the two source patches must be coplanar')
    q = singles[1]['corners']
    if dot(normal, cross(sub(q[1], q[0]), sub(q[3], q[0]))) <= 0:
        raise ValueError('patch normals must have the same orientation')
    a, b = [vertices[key] for key in sorted(edge)]
    side = []
    for single in singles:
        center = tuple((sum((v[i] for v in single['corners'])) / 4 for i in range(3)))
        side.append(dot(cross(sub(b, a), sub(center, a)), normal))
    if side[0] * side[1] >= 0:
        raise ValueError('patch interiors must lie on opposite sides of the shared edge')
    expected = dict(measure=sum((e['measure'] for e in expectations)), expected=sum((e['expected'] for e in expectations)))
    return (singles, expected, edges[edge][0])

def add(a, b):
    return tuple((x + y for x, y in zip(a, b)))

def mul(k, a):
    return tuple((k * x for x in a))

def unit(a):
    return mul(1 / norm(a), a)

def distance(a, b):
    return norm(sub(a, b))

def cyclic(a):
    return min((tuple(a[i:] + a[:i]) for i in range(len(a))))

def source_patches(spec):
    if 'patches' in spec:
        return [(p['divisions'], [spec['vertices'][key] for key in p['corners']]) for p in spec['patches']]
    return [(spec['divisions'], spec['corners'])]

def expected_lattices(spec, expect):
    mode = spec['mode']
    if mode == 'line':
        a, b = spec['points']
        n = spec['divisions']
        return [[add(a, mul(i / n, sub(b, a))) for i in range(n + 1)]]
    if mode == 'arc':
        c = spec['center']
        u = unit(sub(spec['start'], c))
        w = unit(cross(u, sub(spec['end'], c)))
        v = cross(w, u)
        radius, theta = (expect['radius'], expect['angle'])
        n = spec['divisions']
        return [[add(c, add(mul(radius * math.cos(theta * i / n), u), mul(radius * math.sin(theta * i / n), v))) for i in range(n + 1)]]
    output = []
    for (nx, ny), p in source_patches(spec):
        layer_count = spec['layers'] if mode == 'hex' else 0
        points = []
        for k in range(layer_count + 1):
            for j in range(ny + 1):
                t = j / ny
                for i in range(nx + 1):
                    s = i / nx
                    point = add(add(mul((1 - s) * (1 - t), p[0]), mul(s * (1 - t), p[1])), add(mul(s * t, p[2]), mul((1 - s) * t, p[3])))
                    if layer_count:
                        point = add(point, mul(k / layer_count, spec['vector']))
                    points.append(point)
        output.append(points)
    return output

def expected_cells(spec, lattices):
    if spec['mode'] in ('line', 'arc'):
        seq = lattices[0]
        return [[(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]]
    result = []
    for ((nx, ny), _), nodes in zip(source_patches(spec), lattices):
        plane = (nx + 1) * (ny + 1)
        layers = spec['layers'] if spec['mode'] == 'hex' else 1
        cells = []
        for k in range(layers):
            for j in range(ny):
                for i in range(nx):
                    a = k * plane + j * (nx + 1) + i
                    q = (a, a + 1, a + nx + 2, a + nx + 1)
                    if spec['mode'] == 'hex':
                        q = q + tuple((x + plane for x in q))
                    cells.append(tuple((nodes[x] for x in q)))
        result.append(cells)
    return result

def matching_lattices(spec, expect, nodes, active, delta):
    buckets = defaultdict(list)

    def key(p):
        return tuple((math.floor(x / delta) for x in p))
    for identifier in active:
        buckets[key(nodes[identifier])].append(identifier)
    out = []
    deviation = 0.0
    for lattice in expected_lattices(spec, expect):
        ids = []
        for point in lattice:
            base = key(point)
            matches = []
            for dx in itertools.product((-1, 0, 1), repeat=3):
                for identifier in buckets.get(tuple((base[k] + dx[k] for k in range(3))), ()):
                    error = distance(point, nodes[identifier])
                    if error <= delta:
                        matches.append((identifier, error))
            if not len(matches) == 1:
                raise PrepError('invalid_structured_mesh', str(('expected lattice point has missing/duplicate nodes', point, len(matches))))
            identifier, error = matches[0]
            ids.append(identifier)
            deviation = max(deviation, error)
        if not len(set(ids)) == len(ids):
            raise PrepError('invalid_structured_mesh', str('collapsed lattice'))
        out.append(ids)
    if not set().union(*map(set, out)) == active:
        raise PrepError('invalid_structured_mesh', str('unexpected active node'))
    return (out, deviation)

def topology(top, sides):
    occurrences = defaultdict(list)
    for eid, cell in top.items():
        for indices in sides:
            face = tuple((cell['nodes'][i] for i in indices))
            occurrences[tuple(sorted(face))].append((eid, face))
    adjacency = {eid: set() for eid in top}
    for face, rows in occurrences.items():
        if not len(rows) in (1, 2):
            raise PrepError('invalid_structured_mesh', str(('nonmanifold incidence', face, len(rows))))
        if len(rows) == 2:
            (a, x), (b, y) = rows
            if not a != b:
                raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
            if len(x) == 2:
                if not x == y[::-1]:
                    raise PrepError('invalid_structured_mesh', str(('edge ordering', x, y)))
            elif not cyclic(list(x)) == cyclic(list(y[::-1])):
                raise PrepError('invalid_structured_mesh', str(('face ordering', x, y)))
            adjacency[a].add(b)
            adjacency[b].add(a)
    reached = set()
    todo = [next(iter(top))]
    while todo:
        eid = todo.pop()
        if eid not in reached:
            reached.add(eid)
            todo.extend(adjacency[eid] - reached)
    if not len(reached) == len(top):
        raise PrepError('invalid_structured_mesh', str('multiple disconnected components'))
    return occurrences

def hex_jacobian(p, xi, eta, zeta):
    p = [sub(point, p[0]) for point in p]
    derivative = [(sx * (1 + sy * eta) * (1 + sz * zeta) / 8, sy * (1 + sx * xi) * (1 + sz * zeta) / 8, sz * (1 + sx * xi) * (1 + sy * eta) / 8) for sx, sy, sz in SIGNS]
    columns = [tuple((sum((p[i][k] * derivative[i][j] for i in range(8))) for k in range(3))) for j in range(3)]
    determinant = dot(columns[0], cross(columns[1], columns[2]))
    denom = math.prod((norm(col) for col in columns))
    if not denom > 0:
        raise PrepError('invalid_structured_mesh', str('degenerate Jacobian'))
    return (determinant, determinant / denom)

def _verify_records(case, nodes, elements, contract):
    spec, expect = (case['input'], case['expectation'])
    mode = spec['mode']
    dim = {'line': 1, 'arc': 1, 'quad': 2, 'hex': 3}[mode]
    typ, arity = {1: (1, 2), 2: (3, 4), 3: (5, 8)}[dim]
    if not max((e['dim'] for e in elements.values())) == dim:
        raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
    top = {eid: e for eid, e in elements.items() if e['dim'] == dim}
    if not len(top) == expect['elements']:
        raise PrepError('invalid_structured_mesh', str(('element count', len(top), expect['elements'])))
    if not all((e['type'] == typ and len(e['nodes']) == arity for e in top.values())):
        raise PrepError('invalid_structured_mesh', str('unexpected top-dimensional family/order'))
    active = set((n for cell in top.values() for n in cell['nodes']))
    if not len(active) == expect['active_nodes']:
        raise PrepError('invalid_structured_mesh', str(('active node count', len(active), expect['active_nodes'])))
    if mode == 'line':
        scale = distance(*spec['points'])
    elif mode == 'arc':
        scale = expect['radius']
    else:
        points = [point for _, p in source_patches(spec) for point in p]
        scale = max((distance(a, b) for a, b in itertools.combinations(points, 2)))
        if mode == 'hex':
            scale = max(scale, norm(spec['vector']))
    delta = contract['coordinate_relative_tolerance'] * scale
    lattice_ids, deviation = matching_lattices(spec, expect, nodes, active, delta)
    expected_by_patch = expected_cells(spec, lattice_ids)
    actual_by_nodes = {frozenset(cell['nodes']): eid for eid, cell in top.items()}
    if not len(actual_by_nodes) == len(top):
        raise PrepError('invalid_structured_mesh', str('duplicate cells'))
    group_ids = []
    for index, expected in enumerate(expected_by_patch):
        ids = set()
        for conn in expected:
            eid = actual_by_nodes.get(frozenset(conn))
            if not eid is not None:
                raise PrepError('invalid_structured_mesh', str(('missing expected lattice cell', conn)))
            actual = top[eid]['nodes']
            ids.add(eid)
            if not top[eid]['physical'] == (110 + index,):
                raise PrepError('invalid_structured_mesh', str(('wrong physical source', eid, top[eid]['physical'])))
            if dim == 1:
                if not actual == conn:
                    raise PrepError('invalid_structured_mesh', str(('line ordering', actual, conn)))
            elif dim == 2:
                if not cyclic(list(actual)) == cyclic(list(conn)):
                    raise PrepError('invalid_structured_mesh', str(('quad ordering', actual, conn)))
            else:
                wanted = {frozenset((conn[i] for i in side)) for side in SIDES_H}
                got = {frozenset((actual[i] for i in side)) for side in SIDES_H}
                if not wanted == got:
                    raise PrepError('invalid_structured_mesh', str(('Hex8 face ordering', eid)))
        group_ids.append(ids)
    if not set().union(*group_ids) == set(top):
        raise PrepError('invalid_structured_mesh', str('physical sources not exhaustive'))
    if len(group_ids) == 2:
        if not not group_ids[0] & group_ids[1]:
            raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
    report = dict(elements=len(top), active_nodes=len(active), all_msh_nodes=len(nodes), max_lattice_coordinate_error=deviation, coordinate_tolerance=delta, physical_group_cells=[len(s) for s in group_ids], hanging_nodes=0, connected_components=1)
    measure = 0.0
    min_jac = math.inf
    min_scaled = math.inf
    max_aspect = 0.0
    if dim == 1:
        incidence = Counter((n for cell in top.values() for n in cell['nodes']))
        if not (sorted(incidence.values()).count(1) == 2 and all((x in (1, 2) for x in incidence.values()))):
            raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
        measure = sum((distance(*(nodes[n] for n in cell['nodes'])) for cell in top.values()))
        expected_measure = expect.get('polyline_length', expect['measure'])
        if mode == 'arc':
            c = spec['center']
            r = expect['radius']
            u = unit(sub(spec['start'], c))
            w = unit(cross(u, sub(spec['end'], c)))
            v = cross(w, u)
            max_angle_error = max_radius_error = max_plane_error = 0.0
            for i, identifier in enumerate(lattice_ids[0]):
                p = sub(nodes[identifier], c)
                max_radius_error = max(max_radius_error, abs(norm(p) - r))
                max_plane_error = max(max_plane_error, abs(dot(p, w)))
                angle = math.atan2(dot(p, v), dot(p, u))
                max_angle_error = max(max_angle_error, abs(angle - expect['angle'] * i / spec['divisions']))
            if not (max_radius_error <= delta and max_plane_error <= delta):
                raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
            if not max_angle_error <= contract['angle_absolute_tolerance_radians']:
                raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
            report.update(radius_error=max_radius_error, plane_error=max_plane_error, angle_error=max_angle_error, analytic_arc_length=expect['measure'], analytic_chord_length=expected_measure, polyline_approximation_relative_error=abs(measure - expect['measure']) / expect['measure'])
    else:
        sides = SIDES_Q if dim == 2 else SIDES_H
        incidence = topology(top, sides)
        report.update(boundary_sides=sum((len(rows) == 1 for rows in incidence.values())), interior_sides=sum((len(rows) == 2 for rows in incidence.values())))
        if len(group_ids) == 2:
            shared = [face for face, rows in incidence.items() if len(rows) == 2 and (rows[0][0] in group_ids[0]) != (rows[1][0] in group_ids[0])]
            shared_nodes = set((n for face in shared for n in face))
            if not len(shared) == expect['shared_boundary_cells']:
                raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
            if not len(shared_nodes) == expect['shared_nodes']:
                raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
            if not set(lattice_ids[0]) & set(lattice_ids[1]) == shared_nodes:
                raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
            report.update(shared_boundary_cells=len(shared), shared_nodes=len(shared_nodes))
        normal = expect['source_normal']
        for cell in top.values():
            p = [nodes[n] for n in cell['nodes']]
            if dim == 2:
                measure += sum((dot(cross(sub(p[i], p[0]), sub(p[i + 1], p[0])), normal) / 2 for i in (1, 2)))
                for i in range(4):
                    u, v = (sub(p[(i + 1) % 4], p[i]), sub(p[(i - 1) % 4], p[i]))
                    determinant = dot(cross(u, v), normal)
                    min_jac = min(min_jac, determinant / 4)
                    min_scaled = min(min_scaled, determinant / (norm(u) * norm(v)))
                edges = SIDES_Q
            else:
                for location in itertools.product(contract['hex_samples'], repeat=3):
                    jac, scaled = hex_jacobian(p, *location)
                    min_jac = min(min_jac, jac)
                    min_scaled = min(min_scaled, scaled)
                for location in itertools.product((-1 / math.sqrt(3), 1 / math.sqrt(3)), repeat=3):
                    measure += hex_jacobian(p, *location)[0]
                edges = EDGES_H
            lengths = [distance(p[a], p[b]) for a, b in edges]
            if not min(lengths) > 0:
                raise PrepError('invalid_structured_mesh', str('Structured mesh invariant failed.'))
            max_aspect = max(max_aspect, max(lengths) / min(lengths))
        if not min_jac > 0:
            raise PrepError('invalid_structured_mesh', str(('nonpositive Jacobian', min_jac)))
        gate = contract['quad_min_corner_signed_scaled_jacobian' if dim == 2 else 'hex_min_sampled_scaled_jacobian']
        if not min_scaled >= gate:
            raise PrepError('invalid_structured_mesh', str(('scaled Jacobian gate', min_scaled, gate)))
        aspect_gate = contract['quad_max_edge_aspect_ratio' if dim == 2 else 'hex_max_edge_aspect_ratio']
        if not max_aspect <= aspect_gate:
            raise PrepError('invalid_structured_mesh', str(('edge aspect gate', max_aspect, aspect_gate)))
        report.update(min_signed_jacobian=min_jac, min_independent_scaled_jacobian=min_scaled, max_edge_aspect_ratio=max_aspect, scaled_jacobian_gate=gate)
        expected_measure = expect['measure']
    relative = abs(measure - expected_measure) / abs(expected_measure)
    if not relative <= contract['relative_measure_tolerance']:
        raise PrepError('invalid_structured_mesh', str(('analytic measure mismatch', measure, expected_measure, relative)))
    report.update(measure=measure, analytic_measure=expected_measure, relative_measure_error=relative)
    return report


def validate_recipe(spec):
    """Validate a bounded user recipe without generating or changing a model.

    Limits are explicit resource budgets, never silent division clamping. The
    recipe owns length units; there is no guessed CAD identity or unit.
    """
    try:
        if not isinstance(spec, dict) or spec.get('mode') not in ('quad', 'hex'):
            raise ValueError('Only planar quad patches and positive straight hex sweeps are supported.')
        # Reject NaN/Infinity before hashing or passing JSON to a child process.
        spec = json.loads(json.dumps(spec, allow_nan=False))
        singles, _, shared = _normalize(spec)
        if 'vertices' in spec and set(spec['vertices']) != {key for patch in spec['patches'] for key in patch['corners']}:
            raise ValueError('Unused source vertices are outside the recipe topology.')
        mode, dim = spec['mode'], 2 if spec['mode'] == 'quad' else 3
        counts = [single['divisions'] for single in singles]
        layers = spec['layers'] if dim == 3 else 1
        elements = sum(nx * ny for nx, ny in counts) * layers
        nodes2 = sum((nx + 1) * (ny + 1) for nx, ny in counts) - ((shared + 1) if shared is not None else 0)
        active_nodes = nodes2 * (layers + 1 if dim == 3 else 1)
        if elements > MAX_ELEMENTS or active_nodes > MAX_NODES:
            raise PrepError('recipe_budget', 'The structured recipe exceeds the explicit generation budget.',
                            {'elements': elements, 'active_nodes': active_nodes,
                             'max_elements': MAX_ELEMENTS, 'max_nodes': MAX_NODES})
        p = singles[0]['corners']
        normal = unit(cross(sub(p[1], p[0]), sub(p[3], p[0])))
        areas = [sum(dot(cross(sub(s['corners'][i], s['corners'][0]),
                             sub(s['corners'][i + 1], s['corners'][0])), normal) / 2
                     for i in (1, 2)) for s in singles]
        measure = sum(areas) * (dot(spec['vector'], normal) if dim == 3 else 1)
        points = [point for single in singles for point in single['corners']]
        scale = max(distance(a, b) for a, b in itertools.combinations(points, 2))
        if dim == 3:
            scale = max(scale, norm(spec['vector']))
        if not all(math.isfinite(x) and x > 0 for x in (scale, measure)):
            raise ValueError('Nonfinite or nonpositive analytic source measure.')
        expectation = dict(elements=elements, active_nodes=active_nodes, measure=measure,
                           source_normal=normal)
        if shared is not None:
            expectation.update(shared_boundary_cells=shared * layers,
                               shared_nodes=(shared + 1) * (layers + 1 if dim == 3 else 1))
        return dict(singles=tuple(singles), dimension=dim, expected_elements=elements,
                    expected_active_nodes=active_nodes, expected_measure=measure,
                    source_normal=normal, scale=scale, unit=spec['unit'],
                    kind='quad4' if dim == 2 else 'hex8', expectation=expectation)
    except PrepError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ZeroDivisionError) as exc:
        raise PrepError('invalid_recipe', str(exc)) from exc


def validate_structured_mesh(spec, coordinates, cells):
    """Check the full physical mesh against the recipe and fixed quality gates.

    cells are (source element ID, zero-based source patch index, node-ID tuple).
    Every supplied coordinate must be used by the physical mesh. The caller
    separately accounts for lower-dimensional SDK records in its full inventory.
    """
    admission = validate_recipe(spec)
    try:
        if not isinstance(coordinates, dict) or not coordinates:
            raise ValueError('Physical coordinates must be a nonempty ID mapping.')
        nodes = {}
        for identifier, point in coordinates.items():
            if type(identifier) is not int or identifier <= 0:
                raise ValueError('Source node IDs must be positive integers.')
            nodes[identifier] = vec(point)
        dim, arity, typ = (2, 4, 3) if admission['dimension'] == 2 else (3, 8, 5)
        elements = {}
        for identifier, patch, conn in cells:
            if (type(identifier) is not int or identifier <= 0 or identifier in elements
                    or type(patch) is not int or not 0 <= patch < len(admission['singles'])):
                raise ValueError('Invalid or duplicate element/source patch identity.')
            if (len(conn) != arity or any(type(n) is not int or n not in nodes for n in conn)
                    or len(set(conn)) != arity):
                raise ValueError('Invalid physical element connectivity.')
            elements[identifier] = dict(type=typ, dim=dim, nodes=tuple(conn), physical=(110 + patch,))
        if {n for e in elements.values() for n in e['nodes']} != set(nodes):
            raise ValueError('Unexpected unused physical node.')
        case = dict(input=spec, expectation=admission['expectation'])
        result = _verify_records(case, nodes, elements, CONTRACT)
        result['kind'] = admission['kind']
        return result
    except PrepError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ZeroDivisionError) as exc:
        raise PrepError('invalid_structured_mesh', str(exc)) from exc
