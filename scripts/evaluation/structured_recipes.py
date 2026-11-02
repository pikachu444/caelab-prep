"""Bounded Gmsh 4.15.2 recipe experiment, not a product admission path."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import math
import sys
import time
from pathlib import Path

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
        raise ValueError('unsupported or missing recipe fields: '
                         + repr(dict(missing=sorted(missing), unknown=sorted(unknown))))


def validate(spec):
    if not isinstance(spec, dict):
        raise ValueError('recipe must be a JSON object')
    fields = {
        'line': ('points', 'divisions'),
        'arc': ('center', 'start', 'end', 'divisions'),
        'quad': ('corners', 'divisions'),
        'hex': ('corners', 'divisions', 'vector', 'layers'),
    }
    if spec.get('mode') not in fields:
        raise ValueError('unsupported recipe mode')
    exact_keys(spec, ('mode', 'unit', *fields[spec['mode']]), ('name',))
    if 'name' in spec and not isinstance(spec['name'], str):
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
    area = sum((dot(cross(p[i], p[(i + 1) % 4]), n) for i in range(4))) / (2 * area0)
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


def normalize(spec):
    """Two patches share topology only through explicit vertex IDs."""
    if not isinstance(spec, dict):
        raise ValueError('recipe must be a JSON object')
    if 'patches' not in spec:
        return [spec], validate(spec), None
    if spec.get('mode') not in ('quad', 'hex'):
        raise ValueError('shared patches require quad or hex mode')
    exact_keys(spec, ('mode', 'unit', 'vertices', 'patches',
                     *(('vector', 'layers') if spec['mode'] == 'hex' else ())), ('name',))
    patches = spec['patches']
    if len(patches) != 2:
        raise ValueError('this experiment supports exactly two adjacent patches')
    vertices = {key: vec(value) for key, value in spec['vertices'].items()}
    if any(not isinstance(key, str) or not key for key in vertices):
        raise ValueError('explicit nonempty vertex IDs required')
    for patch in patches:
        exact_keys(patch, ('id', 'corners', 'divisions'))
        if not isinstance(patch['id'], str) or not patch['id']:
            raise ValueError('explicit nonempty patch IDs required')
    if len({patch['id'] for patch in patches}) != 2:
        raise ValueError('distinct patch IDs required')
    singles, expectations, edges = [], [], {}
    for patch in patches:
        ids = patch['corners']
        if len(ids) != 4 or len(set(ids)) != 4:
            raise ValueError('four distinct explicit vertex IDs required')
        single = {key: value for key, value in spec.items()
                  if key not in ('vertices', 'patches')}
        single.update(corners=[vertices[key] for key in ids], divisions=patch['divisions'])
        expectations.append(validate(single))
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
    scale = max(norm(sub(v, p[0])) for single in singles for v in single['corners'])
    if any(abs(dot(sub(v, p[0]), normal)) > norm(normal) * scale * 1e-10
           for v in singles[1]['corners']):
        raise ValueError('the two source patches must be coplanar')
    q = singles[1]['corners']
    if dot(normal, cross(sub(q[1], q[0]), sub(q[3], q[0]))) <= 0:
        raise ValueError('patch normals must have the same orientation')
    a, b = [vertices[key] for key in sorted(edge)]
    side = []
    for single in singles:
        center = tuple(sum(v[i] for v in single['corners']) / 4 for i in range(3))
        side.append(dot(cross(sub(b, a), sub(center, a)), normal))
    if side[0] * side[1] >= 0:
        raise ValueError('patch interiors must lie on opposite sides of the shared edge')
    expected = dict(measure=sum(e['measure'] for e in expectations),
                    expected=sum(e['expected'] for e in expectations))
    return singles, expected, edges[edge][0]


def add_patches(gmsh, spec, singles):
    geo = gmsh.model.geo
    vertices = {key: geo.addPoint(*point) for key, point in spec['vertices'].items()}
    edges, faces = {}, []
    for patch, single in zip(spec['patches'], singles):
        ids = patch['corners']
        boundary = []
        for i in range(4):
            a, b = ids[i], ids[(i + 1) % 4]
            key = tuple(sorted((a, b)))
            if key not in edges:
                tag = geo.addLine(vertices[key[0]], vertices[key[1]])
                geo.mesh.setTransfiniteCurve(tag, single['divisions'][i % 2] + 1)
                edges[key] = tag
            boundary.append(edges[key] if (a, b) == key else -edges[key])
        face = geo.addPlaneSurface([geo.addCurveLoop(boundary)])
        geo.mesh.setTransfiniteSurface(face, 'Left', [vertices[key] for key in ids])
        geo.mesh.setRecombine(2, face)
        faces.append(face)
    if spec['mode'] == 'quad':
        return 2, faces
    output = geo.extrude([(2, face) for face in faces], *spec['vector'],
                         [spec['layers']], [], True)
    volumes = [tag for dim, tag in output if dim == 3]
    assert len(volumes) == 2
    return 3, volumes


def check_interface(gmsh, dim, top, shared_divisions, layers):
    """Read actual MSH element groups and compare complete boundary faces."""
    groups = []
    for group in (110, 111):
        elements = set()
        for entity in gmsh.model.getEntitiesForPhysicalGroup(dim, group):
            for ids in gmsh.model.mesh.getElements(dim, int(entity))[1]:
                elements.update(map(int, ids))
        groups.append(elements)
    assert groups[0] and groups[1] and not groups[0] & groups[1]
    assert groups[0] | groups[1] == {identifier for identifier, _ in top}
    indices = ([(0, 1), (1, 2), (2, 3), (3, 0)] if dim == 2 else
               [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    by_group = []
    for group in groups:
        boundary = Counter(tuple(sorted(nodes[i] for i in side))
                           for identifier, nodes in top if identifier in group
                           for side in indices)
        assert all(count in (1, 2) for count in boundary.values())
        by_group.append({face for face, count in boundary.items() if count == 1})
    common = by_group[0] & by_group[1]
    expected = shared_divisions * (layers if dim == 3 else 1)
    assert len(common) == expected, (len(common), expected)
    return dict(shared_boundary_count=len(common), expected=expected,
                group_elements=[len(group) for group in groups])

def run(spec, folder):
    import gmsh
    singles, expectation, shared_divisions = normalize(spec)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'input.json').write_text(json.dumps(spec, indent=2) + '\n')
    started = time.monotonic()
    gmsh.initialize(interruptible=False)
    gmsh.option.setNumber('General.Terminal', 0)
    gmsh.option.setNumber('General.NumThreads', 1)
    gmsh.logger.start()
    try:
        gmsh.model.add('explicit_recipe')
        geo = gmsh.model.geo
        mode = spec['mode']
        if mode == 'arc':
            # Gmsh's 1D integration tolerance controls transfinite curve seeds.
            # Keep the geometric gate fixed; improve backend integration accuracy.
            gmsh.option.setNumber('Mesh.LcIntegrationPrecision', 1e-12)
        entities = None
        if shared_divisions is not None:
            dim, entities = add_patches(gmsh, spec, singles)
        elif mode in ('line', 'arc'):
            if mode == 'line':
                a, b = [geo.addPoint(*p) for p in spec['points']]
                entity = geo.addLine(a, b)
            else:
                # Built-in InterpolateCurve differentiates with finite differences;
                # OCCT supplies the analytic curve derivative for arc-length seeds.
                # This is a bounded second recipe, with unchanged geometry gates.
                occ = gmsh.model.occ
                c, a, b = [occ.addPoint(*spec[k]) for k in ('center', 'start', 'end')]
                entity = occ.addCircleArc(a, c, b)
                occ.synchronize()
            if mode == 'arc':
                gmsh.model.mesh.setTransfiniteCurve(entity, spec['divisions'] + 1)
            else:
                geo.mesh.setTransfiniteCurve(entity, spec['divisions'] + 1)
            dim = 1
        else:
            pts = [geo.addPoint(*p) for p in spec['corners']]
            edges = [geo.addLine(pts[i], pts[(i + 1) % 4]) for i in range(4)]
            face = geo.addPlaneSurface([geo.addCurveLoop(edges)])
            nx, ny = spec['divisions']
            for i, e in enumerate(edges):
                geo.mesh.setTransfiniteCurve(e, (nx if i % 2 == 0 else ny) + 1)
            geo.mesh.setTransfiniteSurface(face, 'Left', pts)
            geo.mesh.setRecombine(2, face)
            entity = face
            dim = 2
            if mode == 'hex':
                out = geo.extrude([(2, face)], *spec['vector'], [spec['layers']], [], True)
                entity = next((t for d, t in out if d == 3))
                dim = 3
        geo.synchronize()
        for index, entity in enumerate(entities or [entity]):
            gmsh.model.addPhysicalGroup(dim, [entity], 110 + index, 'Explicit source ' + str(index + 1))
        gmsh.model.mesh.generate(dim)
        gmsh.option.setNumber('Mesh.SaveAll', 1)
        gmsh.option.setNumber('Mesh.MshFileVersion', 4.1)
        output = folder / 'mesh.msh'
        gmsh.write(str(output))
        logs = list(gmsh.logger.get())
        (folder / 'sdk.log').write_text('\n'.join(logs) + '\n')
        gmsh.clear()
        gmsh.open(str(output))
        ids, xyz, _ = gmsh.model.mesh.getNodes()
        nodes = {int(ids[i]): tuple((float(x) for x in xyz[3 * i:3 * i + 3])) for i in range(len(ids))}
        inventory = []
        top = []
        for typ, element_ids, flat in zip(*gmsh.model.mesh.getElements()):
            name, d, order, arity, _, _ = gmsh.model.mesh.getElementProperties(int(typ))
            inventory.append(dict(type=int(typ), dimension=d, order=order, arity=arity, name=name, count=len(element_ids)))
            if d == dim:
                top.extend(((int(e), [int(x) for x in flat[i * arity:(i + 1) * arity]]) for i, e in enumerate(element_ids)))
        assert len(top) == expectation['expected'], (len(top), expectation)
        expected_type = {'line': 1, 'arc': 1, 'quad': 3, 'hex': 5}[mode]
        assert all((r['type'] == expected_type for r in inventory if r['dimension'] == dim)), 'unexpected family; no fallback admitted'
        interface = (check_interface(gmsh, dim, top, shared_divisions, spec.get('layers', 1))
                     if shared_divisions is not None else None)
        measure = 0.0
        minimum_jacobian = None
        if dim == 1:
            lengths = [norm(sub(nodes[c[1]], nodes[c[0]])) for _, c in top]
            assert min(lengths) > 0
            measure = sum(lengths)
            incidence = Counter((n for _, c in top for n in c))
            assert sum((v == 1 for v in incidence.values())) == 2 and all((v in (1, 2) for v in incidence.values()))
        elif dim == 2:
            corners = singles[0]['corners']
            normal = cross(sub(corners[1], corners[0]), sub(corners[3], corners[0]))
            nlen = norm(normal)
            values = []
            for _, c in top:
                p = [nodes[n] for n in c]
                signed = sum((dot(cross(p[i], p[(i + 1) % 4]), normal) for i in range(4))) / (2 * nlen)
                assert signed > 0
                measure += signed
                for i in range(4):
                    values.append(dot(cross(sub(p[(i + 1) % 4], p[i]), sub(p[(i + 3) % 4], p[i])), normal) / nlen / 4)
            minimum_jacobian = min(values)
            assert minimum_jacobian > 0
        else:
            values = []
            signs = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
            for _, c in top:
                p = [nodes[n] for n in c]
                for xi in (-1.0, 0.0, 1.0):
                    for eta in (-1.0, 0.0, 1.0):
                        for zeta in (-1.0, 0.0, 1.0):
                            derivatives = [(sx * (1 + sy * eta) * (1 + sz * zeta) / 8, sy * (1 + sx * xi) * (1 + sz * zeta) / 8, sz * (1 + sx * xi) * (1 + sy * eta) / 8) for sx, sy, sz in signs]
                            cols = [tuple((sum((p[i][k] * derivatives[i][j] for i in range(8))) for k in range(3))) for j in range(3)]
                            determinant = dot(cols[0], cross(cols[1], cols[2]))
                            values.append(determinant)
                            if xi == eta == zeta == 0:
                                measure += 8 * determinant
            minimum_jacobian = min(values)
            assert minimum_jacobian > 0
        quality = list(gmsh.model.mesh.getElementQualities([e for e, _ in top], 'minSICN')) if dim >= 2 else []
        half_step = expectation.get('angle', 0.0) / (2 * expectation['expected'])
        tolerance = 1 - math.sin(half_step) / half_step + 1e-10 if mode == 'arc' else 1e-09
        assert abs(measure - expectation['measure']) / expectation['measure'] <= tolerance
        errors = [s for s in logs if s.lower().startswith('error')]
        assert not errors, errors
        report = dict(
            scope='one or two explicit planar patches; SDK experiment, no product adoption',
            version=gmsh.__version__, input=spec, expectation=expectation,
            inventory=inventory, interface=interface, measure=measure,
            min_signed_jacobian=minimum_jacobian,
            min_SICN=min(quality) if quality else None, errors=errors,
            geometry_kernel='OpenCASCADE' if mode == 'arc' else 'built-in',
            curve_integration_precision=gmsh.option.getNumber('Mesh.LcIntegrationPrecision'),
            warnings=[s for s in logs if s.lower().startswith('warning')],
            seconds=time.monotonic() - started,
            recipe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            input_sha256=hashlib.sha256((folder / 'input.json').read_bytes()).hexdigest(),
            mesh_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        )
        (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        return report
    finally:
        gmsh.finalize()
if __name__ == '__main__':
    report = run(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])
    print(json.dumps(report))
