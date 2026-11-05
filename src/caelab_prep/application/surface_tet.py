"""Pure closed-TRI admission and conservative, boundary-fixed TET4 smoothing.

Intersection predicates use exact rational values of the original binary floats.
The local 1e-12 degeneracy guard matches the existing tri/tet admission baseline;
it is a numerical guard, not a solver criterion or a shape-quality target.
"""
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, product
import math
from pathlib import Path

from ..adapters.msh_worker import read_msh
from ..cae_core.errors import PrepError


MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_NODES = 100_000
MAX_TRIANGLES = 200_000
MAX_PAIRS = 250_000
MAX_TETRAHEDRA = 200_000
MAX_SMOOTH_ITERATIONS = 100
RELATIVE_DEGENERACY = 1e-12
QUALITY_ROUNDOFF = 1e-12
MAX_SURFACE_EDGE_ASPECT = 4
_CORNER_J_DIRECTIONS = tuple(tuple(value / math.sqrt(sum(v * v for v in direction)) for value in direction)
                             for direction in product((-1, 0, 1), repeat=3) if any(direction))


@dataclass(frozen=True)
class SurfaceGroup:
    dimension: int
    tag: int
    name: str
    triangle_ids: tuple[int, ...]


@dataclass(frozen=True)
class ClosedSurface:
    node_ids: tuple[int, ...]
    coordinates: tuple[tuple[float, float, float], ...]
    triangle_ids: tuple[int, ...]
    triangles: tuple[tuple[int, int, int], ...]
    length_unit: str
    signed_volume: float
    physical_groups: tuple[SurfaceGroup, ...]


def _fail(code, message, **details):
    raise PrepError(code, message, details)


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _fraction_point(point):
    return tuple(Fraction.from_float(value) for value in point)


def _aspect_measure(squared_ratio):
    # Normalize the dimensionless ratio before sqrt, without overflowing the
    # squared coordinate lengths or an otherwise representable aspect ratio.
    exponent = (squared_ratio.numerator.bit_length() - squared_ratio.denominator.bit_length()) // 2
    scaled = squared_ratio / Fraction(2) ** (2 * exponent)
    try:
        return math.ldexp(math.sqrt(float(scaled)), exponent)
    except OverflowError:
        return "exceeds floating-point range"


def _project(point, axis):
    return tuple(value for index, value in enumerate(point) if index != axis)


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _inside(point, triangle, axis):
    p = _project(point, axis)
    tri = tuple(_project(value, axis) for value in triangle)
    signs = [_cross2(_sub(tri[(i + 1) % 3], tri[i]), _sub(p, tri[i])) for i in range(3)]
    return all(value >= 0 for value in signs) or all(value <= 0 for value in signs)


def _on_segment(point, a, b):
    edge, offset = _sub(b, a), _sub(point, a)
    return not any(_cross(edge, offset)) and 0 <= _dot(offset, edge) <= _dot(edge, edge)


def _segment_crossings(p, q, a, b, axis):
    """Exact intersections of two coplanar segments, including collinear ends."""
    p2, a2 = _project(p, axis), _project(a, axis)
    r, s = _sub(_project(q, axis), p2), _sub(_project(b, axis), a2)
    denominator = _cross2(r, s)
    offset = _sub(a2, p2)
    if denominator:
        t, u = _cross2(offset, s) / denominator, _cross2(offset, r) / denominator
        if 0 <= t <= 1 and 0 <= u <= 1:
            return [tuple(x + t * (y - x) for x, y in zip(p, q))]
        return []
    if _cross2(offset, r):
        return []
    return [point for point in (p, q, a, b) if _on_segment(point, p, q) and _on_segment(point, a, b)]


def _segment_triangle(p, q, triangle, normal):
    dp, dq = (_dot(normal, _sub(point, triangle[0])) for point in (p, q))
    if dp > 0 and dq > 0 or dp < 0 and dq < 0:
        return []
    axis = max(range(3), key=lambda i: abs(normal[i]))
    if dp == dq == 0:
        points = [point for point in (p, q) if _inside(point, triangle, axis)]
        for i in range(3):
            points.extend(_segment_crossings(p, q, triangle[i], triangle[(i + 1) % 3], axis))
        return points
    t = dp / (dp - dq)
    point = tuple(x + t * (y - x) for x, y in zip(p, q))
    return [point] if _inside(point, triangle, axis) else []


def _intersects_beyond_shared(left, right, points):
    a, b = tuple(points[i] for i in left), tuple(points[i] for i in right)
    na, nb = _cross(_sub(a[1], a[0]), _sub(a[2], a[0])), _cross(_sub(b[1], b[0]), _sub(b[2], b[0]))
    shared = sorted(set(left) & set(right))
    for tri, origin, normal in ((a, b[0], nb), (b, a[0], na)):
        distances = [_dot(normal, _sub(point, origin)) for point in tri]
        if all(value > 0 for value in distances) or all(value < 0 for value in distances):
            return False
        nonzero = [value for value in distances if value]
        # Noncoplanar planes sharing an edge meet only on that edge. With one
        # shared vertex, a strict same-side remainder meets only at the vertex.
        if len(shared) == 2 and nonzero:
            return False
        if len(shared) == 1 and len(nonzero) == 2 and (all(v > 0 for v in nonzero) or all(v < 0 for v in nonzero)):
            return False
    allowed = tuple(points[i] for i in shared)
    for source, target, normal in ((a, b, nb), (b, a, na)):
        for i in range(3):
            for point in _segment_triangle(source[i], source[(i + 1) % 3], target, normal):
                if not allowed or (len(allowed) == 1 and point != allowed[0]):
                    return True
                if len(allowed) == 2 and not _on_segment(point, *allowed):
                    return True
    return False


def _check_intersections(triangles, coordinates, exact, triangle_ids):
    bounds = []
    for index, triangle in enumerate(triangles):
        xyz = [coordinates[node] for node in triangle]
        bounds.append((tuple(min(point[axis] for point in xyz) for axis in range(3)),
                       tuple(max(point[axis] for point in xyz) for axis in range(3)), index))
    active, checked = [], 0
    for lower, upper, index in sorted(bounds):
        remaining = []
        for old_lower, old_upper, other in active:
            checked += 1
            if checked > MAX_PAIRS:
                _fail("surface_pair_limit", "Surface intersection sweep exceeded its pair budget.", limit=MAX_PAIRS)
            if old_upper[0] < lower[0]:
                continue
            remaining.append((old_lower, old_upper, other))
            if any(old_upper[axis] < lower[axis] or upper[axis] < old_lower[axis] for axis in (1, 2)):
                continue
            if _intersects_beyond_shared(triangles[index], triangles[other], exact):
                _fail("surface_self_intersection", "Facets intersect beyond their shared vertex or edge.",
                      triangle_ids=[triangle_ids[other], triangle_ids[index]])
        remaining.append((lower, upper, index))
        active = remaining


def _check_topology(triangles):
    edges, links = defaultdict(list), defaultdict(lambda: defaultdict(set))
    for index, triangle in enumerate(triangles):
        for a, b in zip(triangle, (*triangle[1:], triangle[0])):
            edges[tuple(sorted((a, b)))].append((index, a, b))
        for i, vertex in enumerate(triangle):
            a, b = triangle[(i + 1) % 3], triangle[(i + 2) % 3]
            links[vertex][a].add(b)
            links[vertex][b].add(a)
    adjacency = defaultdict(set)
    for edge, uses in edges.items():
        if len(uses) != 2:
            _fail("surface_not_manifold", "Every surface edge must have exactly two incident facets.", edge=edge, count=len(uses))
        first, second = uses
        if first[1:] != second[1:][::-1]:
            _fail("surface_orientation", "The two uses of each surface edge must have opposite directions.", edge=edge)
        adjacency[first[0]].add(second[0])
        adjacency[second[0]].add(first[0])
    def reached(graph, start):
        seen, pending = set(), [start]
        while pending:
            value = pending.pop()
            if value not in seen:
                seen.add(value)
                pending.extend(graph[value] - seen)
        return seen
    for vertex, graph in links.items():
        if any(len(neighbors) != 2 for neighbors in graph.values()) or len(reached(graph, next(iter(graph)))) != len(graph):
            _fail("surface_vertex_link", "Each vertex link must be one cycle.", node_id=vertex)
    if len(reached(adjacency, 0)) != len(triangles):
        _fail("surface_disconnected", "Choose one edge-connected closed shell.")


def load_closed_surface(path, *, length_unit):
    """Read all MSH records and admit one outward, non-self-intersecting TRI3 shell."""
    if length_unit not in ("mm", "cm", "m"):
        _fail("unknown_length_unit", "Declare the source length unit explicitly: mm, cm or m.")
    try:
        source = Path(path).expanduser().resolve()
        if source.stat().st_size > MAX_INPUT_BYTES:
            _fail("surface_size_limit", "Surface file exceeds the byte limit.", limit=MAX_INPUT_BYTES)
        data = read_msh(source)
    except (OSError, ValueError, TypeError) as exc:
        raise PrepError("invalid_surface_mesh", "Cannot read the complete MSH surface.", {"reason": str(exc)}) from exc
    node_ids = tuple(data["nodes"]["ids"])
    xyz = tuple(tuple(float(value) for value in point) for point in data["nodes"]["coordinates"])
    triangle_ids, triangles, memberships = [], [], defaultdict(list)
    for block in data["blocks"]:
        if (block["dimension"], block["element_type"], block["order"], block["nodes_per_element"]) != (2, 2, 1, 3):
            _fail("unsupported_surface_inventory", "Every source cell must be a linear TRI3; no cells are discarded.")
        triangle_ids.extend(block["ids"])
        triangles.extend(tuple(conn) for conn in block["connectivity"])
        for tag in block["physical_tags"]:
            memberships[(2, tag)].extend(block["ids"])
    if len(node_ids) > MAX_NODES or len(triangles) > MAX_TRIANGLES:
        _fail("surface_size_limit", "Surface node or triangle limit exceeded.", max_nodes=MAX_NODES, max_triangles=MAX_TRIANGLES)
    if len(set(xyz)) != len(xyz):
        _fail("duplicate_surface_coordinates", "Distinct node IDs have identical coordinates; no welding is performed.")
    if {node for triangle in triangles for node in triangle} != set(node_ids):
        _fail("unused_surface_nodes", "Every source node must belong to the closed TRI3 shell.")
    if len({tuple(sorted(triangle)) for triangle in triangles}) != len(triangles):
        _fail("duplicate_surface_facets", "Duplicate facets are not repaired or discarded.")
    coordinates = dict(zip(node_ids, xyz))
    exact = {node: _fraction_point(point) for node, point in coordinates.items()}
    for identifier, triangle in zip(triangle_ids, triangles):
        a, b, c = (exact[node] for node in triangle)
        if not any(_cross(_sub(b, a), _sub(c, a))):
            _fail("degenerate_surface_facet", "A surface facet has zero area.", triangle_id=identifier)
        lengths_squared = [_dot(_sub(p, q), _sub(p, q)) for p, q in combinations((a, b, c), 2)]
        squared_ratio = max(lengths_squared) / min(lengths_squared)
        if squared_ratio > MAX_SURFACE_EDGE_ASPECT ** 2:
            _fail("surface_triangle_aspect", "Surface triangle aspect ratio exceeds tolerance",
                  triangle_id=identifier, edge_aspect_ratio=_aspect_measure(squared_ratio),
                  tolerance=float(MAX_SURFACE_EDGE_ASPECT))
    _check_topology(triangles)
    _check_intersections(triangles, coordinates, exact, triangle_ids)
    # Center exact coordinates before summing oriented pyramids; translation
    # cannot change closure or cancel a small volume far from the origin.
    center = tuple((min(p[i] for p in exact.values()) + max(p[i] for p in exact.values())) / 2 for i in range(3))
    centered = {node: _sub(point, center) for node, point in exact.items()}
    volume = sum(_dot(centered[a], _cross(centered[b], centered[c])) for a, b, c in triangles) / 6
    if volume <= 0:
        _fail("surface_orientation", "A closed shell must have positive outward signed volume; no reorientation is performed.")
    try:
        signed_volume = float(volume)
    except OverflowError:
        signed_volume = math.inf
    if not math.isfinite(signed_volume) or signed_volume == 0:
        _fail("surface_volume_range", "Surface volume is outside the finite floating-point output range.")
    groups = []
    for group in data["physical_groups"]:
        members = memberships[(group["dimension"], group["tag"])]
        if group["dimension"] != 2 or not members:
            _fail("invalid_surface_group", "Declared groups must contain surface triangles.", tag=group["tag"], dimension=group["dimension"])
        groups.append(SurfaceGroup(group["dimension"], group["tag"], group["name"], tuple(members)))
    return ClosedSurface(node_ids, xyz, tuple(triangle_ids), tuple(triangles), length_unit, signed_volume, tuple(groups))


def _coordinates(values, code):
    try:
        points = tuple(tuple(point) for point in values)
        if any(len(point) != 3 or any(type(v) not in (int, float) for v in point) for point in points):
            raise ValueError("Expected XYZ triples")
        return tuple(tuple(float(v) for v in point) for point in points)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PrepError(code, "Expected numeric XYZ coordinates.") from exc


def tetra_metrics(points):
    """Signed TET4 volume, Verdict corner scaled Jacobian, and longest/shortest edge."""
    points = _coordinates(points, "invalid_tetrahedron")
    if len(points) != 4:
        _fail("invalid_tetrahedron", "TET4 metrics require exactly four points; higher-order nodes cannot be ignored.")
    result = {"signed_volume": None, "corner_scaled_jacobian": None, "edge_aspect_ratio": None, "problem": None}
    if any(not math.isfinite(value) for point in points for value in point):
        return {**result, "problem": "nonfinite_geometry"}
    center = tuple(min(p[i] for p in points) / 2 + max(p[i] for p in points) / 2 for i in range(3))
    shifted = tuple(_sub(point, center) for point in points)
    scale = max(abs(value) for point in shifted for value in point)
    if not scale:
        return {**result, "signed_volume": 0.0, "corner_scaled_jacobian": 0.0, "problem": "degenerate"}
    normalized = tuple(tuple(value / scale for value in point) for point in shifted)
    lengths = {(i, j): math.dist(normalized[i], normalized[j]) for i, j in combinations(range(4), 2)}
    longest = max(lengths.values())
    local = tuple(tuple(value / longest for value in point) for point in normalized)
    lengths = {edge: value / longest for edge, value in lengths.items()}
    a, b, c = (_sub(local[i], local[0]) for i in (1, 2, 3))
    determinant = _dot(a, _cross(b, c))
    denominator = max(math.prod(lengths[tuple(sorted((i, j)))] for j in range(4) if i != j) for i in range(4))
    jacobian = math.sqrt(2) * determinant / denominator if denominator else 0.0
    shortest = min(lengths.values())
    aspect = 1 / shortest if shortest else None
    mantissa, exponent = math.frexp(scale)
    try:
        volume = math.ldexp(determinant / 6 * (mantissa * longest) ** 3, 3 * exponent)
    except OverflowError:
        volume = None
    problem = ("degenerate" if abs(determinant) <= RELATIVE_DEGENERACY or not shortest else
               "inverted" if determinant < 0 else None)
    if volume is None or not math.isfinite(volume) or determinant and volume == 0 or aspect is not None and not math.isfinite(aspect):
        volume = volume if volume is not None and math.isfinite(volume) else None
        aspect = aspect if aspect is not None and math.isfinite(aspect) else None
        problem = "nonfinite_measure"
    return {"signed_volume": volume, "corner_scaled_jacobian": jacobian,
            "edge_aspect_ratio": aspect, "problem": problem}


@dataclass
class _Tet4State:
    ids: tuple
    original: tuple
    cells: tuple
    fixed: frozenset
    points: dict
    neighbors: dict
    incident: dict
    metrics: list


def _prepare_tet4(node_ids, coordinates, tetrahedra, boundary_node_ids, *, code="invalid_smoothing", metric_budget=None):
    try:
        ids, boundary = tuple(node_ids), tuple(boundary_node_ids)
        cells = tuple(tuple(cell) for cell in tetrahedra)
    except TypeError as exc:
        raise PrepError(code, "Expected node IDs, boundary IDs and four-node connectivities.") from exc
    xyz = _coordinates(coordinates, code)
    if (not ids or len(ids) != len(xyz) or len(ids) > MAX_NODES
            or any(type(i) is not int or i <= 0 for i in (*ids, *boundary))
            or len(set(ids)) != len(ids)
            or any(not math.isfinite(v) for p in xyz for v in p)):
        _fail(code, "Node identities, fixed nodes or coordinates are invalid.")
    known = set(ids)
    fixed = frozenset(boundary)
    if not fixed <= known:
        _fail(code, "Fixed node IDs must belong to the supplied mesh.")
    if (not cells or len(cells) > MAX_TETRAHEDRA
            or any(len(c) != 4 or any(type(i) is not int or i not in known for i in c) or len(set(c)) != 4 for c in cells)
            or len({tuple(sorted(c)) for c in cells}) != len(cells)):
        _fail(code, "Expected distinct TET4 connectivities using the supplied nodes.")
    points = dict(zip(ids, xyz))
    neighbors, incident, faces = defaultdict(set), defaultdict(list), defaultdict(int)
    for index, cell in enumerate(cells):
        for face in combinations(cell, 3):
            faces[tuple(sorted(face))] += 1
        for node in cell:
            neighbors[node].update(set(cell) - {node})
            incident[node].append(index)
    actual_boundary = {node for face, count in faces.items() if count == 1 for node in face}
    if set(neighbors) != set(ids) or any(count > 2 for count in faces.values()) or not actual_boundary <= fixed:
        _fail(code, "All nodes must be used, and every boundary-face node must be fixed.")
    metrics = []
    if metric_budget is None or len(cells) <= metric_budget:
        for index, cell in enumerate(cells):
            quality = tetra_metrics([points[node] for node in cell])
            if quality["problem"] is not None or quality["signed_volume"] <= 0:
                _fail(code, "The initial mesh must have positive, nondegenerate TET4 cells.", tetrahedron=index, problem=quality["problem"])
            metrics.append(quality)
    return _Tet4State(ids, xyz, cells, fixed, points, neighbors, incident, metrics)


def smooth_tet4(node_ids, coordinates, tetrahedra, boundary_node_ids, *, iterations=2, relaxation=.5):
    """Sequential ID-ordered Laplacian moves; seven attempts allow six halvings."""
    if type(iterations) is not int or not 0 <= iterations <= MAX_SMOOTH_ITERATIONS:
        _fail("invalid_smoothing", "Iterations must be a bounded nonnegative integer.")
    if type(relaxation) not in (int, float) or not math.isfinite(relaxation) or not 0 < relaxation <= 1:
        _fail("invalid_smoothing", "Relaxation must be finite and in (0, 1].")
    state = _prepare_tet4(node_ids, coordinates, tetrahedra, boundary_node_ids)
    ids, xyz, cells, fixed = state.ids, state.original, state.cells, state.fixed
    points, neighbors, incident, metrics = state.points, state.neighbors, state.incident, state.metrics
    interior = sorted(set(ids) - fixed)
    report = {"iterations_requested": iterations, "iterations": 0, "moves": 0, "rejected": 0,
              "interior_nodes": len(interior), "max_displacement": 0.0}
    for _ in range(iterations if interior else 0):
        report["iterations"] += 1
        for node in interior:
            current = points[node]
            adjacent = sorted(neighbors[node])
            mean = tuple(math.fsum(points[other][axis] / len(adjacent) for other in adjacent) for axis in range(3))
            if mean == current:
                continue
            affected = incident[node]
            before_j = min(metrics[index]["corner_scaled_jacobian"] for index in affected)
            before_ar = max(metrics[index]["edge_aspect_ratio"] for index in affected)
            accepted = False
            for halving in range(7):
                alpha = relaxation / 2 ** halving
                candidate = tuple((1 - alpha) * a + alpha * b for a, b in zip(current, mean))
                if candidate == current:
                    continue
                points[node] = candidate
                after = [tetra_metrics([points[n] for n in cells[index]]) for index in affected]
                if (all(value["problem"] is None for value in after)
                        and min(value["corner_scaled_jacobian"] for value in after) >= before_j - QUALITY_ROUNDOFF
                        and max(value["edge_aspect_ratio"] for value in after) <= before_ar + QUALITY_ROUNDOFF * max(1, before_ar)):
                    for index, value in zip(affected, after):
                        metrics[index] = value
                    report["moves"] += 1
                    accepted = True
                    break
            if not accepted:
                points[node] = current
                report["rejected"] += 1
    report["max_displacement"] = max(math.dist(original, points[node]) for node, original in zip(ids, xyz))
    return tuple(points[node] for node in ids), report


def _corner_j_summary(metrics):
    try:
        total_volume = math.fsum(value["signed_volume"] for value in metrics)
    except OverflowError:
        total_volume = None
    if total_volume is not None and not math.isfinite(total_volume):
        total_volume = None
    return {"minimum_corner_scaled_jacobian": min(value["corner_scaled_jacobian"] for value in metrics),
            "maximum_edge_aspect_ratio": max(value["edge_aspect_ratio"] for value in metrics),
            "minimum_signed_volume": min(value["signed_volume"] for value in metrics),
            "total_signed_volume": total_volume,
            "total_signed_volume_problem": "nonfinite_measure" if total_volume is None else None,
            "failed_tetrahedron_indices": [i for i, value in enumerate(metrics) if value["corner_scaled_jacobian"] < .5]}


def improve_tet4_corner_j(node_ids, coordinates, tetrahedra, boundary_node_ids, *, iterations=2,
                          initial_step=.1, max_evaluations=100000):
    """Bounded 26-direction search for the minimum incident corner J.

    Every tetra_metrics call, including initial validation, consumes budget.
    Failed cells are zero-based input connectivity indices, never invented IDs.
    iterations counts completed sweeps; passes_started also includes a partial
    sweep. rejected counts full node polls accepting no move. Only fully
    evaluated candidates may be committed when a trial exhausts the budget.
    """
    if type(iterations) is not int or not 0 <= iterations <= 20:
        _fail("invalid_corner_j", "Corner-J iterations must be an integer in [0, 20].")
    if type(initial_step) not in (int, float) or not math.isfinite(initial_step) or initial_step <= 0:
        _fail("invalid_corner_j", "Initial step must be a finite positive local edge fraction.")
    if type(max_evaluations) is not int or not 0 < max_evaluations <= 1_000_000:
        _fail("invalid_corner_j", "Metric evaluation budget must be an integer in [1, 1000000].")
    state = _prepare_tet4(node_ids, coordinates, tetrahedra, boundary_node_ids,
                         code="invalid_corner_j", metric_budget=max_evaluations)
    interior = sorted(set(state.ids) - state.fixed)
    report = {"method": "targeted_interior_corner_j/1", "status": None, "stop_reason": None,
              "iterations_requested": iterations, "initial_step": initial_step, "max_evaluations": max_evaluations,
              "iterations": 0, "passes_started": 0, "metrics_calls": len(state.metrics),
              "moves": 0, "rejected": 0, "complete_trials": 0, "partial_trials_discarded": 0,
              "invalid_trials": 0, "non_improving_trials": 0, "unrepresentable_trials": 0,
              "interior_nodes": len(interior), "input_validated": bool(state.metrics),
              "before": None, "after": None, "all_boundary_bad_tetrahedron_indices": None,
              "cell_index_basis": "zero_based_input_tetrahedra", "max_displacement": 0.0,
              "minimum_scaled_jacobian": .5, "maximum_edge_aspect_ratio": 4.0}
    if not state.metrics:
        report.update(status="budget_exhausted", stop_reason="initial_validation_budget")
        return state.original, report
    if any(value["edge_aspect_ratio"] > 4 for value in state.metrics):
        _fail("invalid_corner_j", "The initial mesh must already satisfy edge aspect ratio <= 4.")
    report["before"] = _corner_j_summary(state.metrics)
    failed = set(report["before"]["failed_tetrahedron_indices"])
    report["all_boundary_bad_tetrahedron_indices"] = [i for i in sorted(failed) if set(state.cells[i]) <= state.fixed]
    if not failed:
        report.update(status="target_met", stop_reason="initial_target_met")
    elif not interior:
        report.update(status="no_interior", stop_reason="all_nodes_fixed")
    elif report["metrics_calls"] == max_evaluations:
        report.update(status="budget_exhausted", stop_reason="trial_budget")
    for _ in range(iterations if report["status"] is None else 0):
        report["passes_started"] += 1
        pass_moves = 0
        for node in interior:
            affected = state.incident[node]
            before_j = min(state.metrics[index]["corner_scaled_jacobian"] for index in affected)
            if before_j >= .5:
                continue
            current = state.points[node]
            edges = {tuple(sorted(edge)) for index in affected for edge in combinations(state.cells[index], 2)}
            minimum_edge = min(math.dist(state.points[a], state.points[b]) for a, b in edges)
            accepted, exhausted = False, False
            for halving in range(7):
                step = minimum_edge * initial_step / 2 ** halving
                best, best_j, representable = None, before_j, False
                for direction in _CORNER_J_DIRECTIONS:
                    candidate = tuple(value + step * delta for value, delta in zip(current, direction))
                    if candidate == current:
                        report["unrepresentable_trials"] += 1
                        continue
                    representable = True
                    quality = []
                    for index in affected:
                        if report["metrics_calls"] >= max_evaluations:
                            exhausted = True
                            break
                        values = [candidate if vertex == node else state.points[vertex] for vertex in state.cells[index]]
                        quality.append(tetra_metrics(values))
                        report["metrics_calls"] += 1
                    if exhausted:
                        if quality:
                            report["partial_trials_discarded"] += 1
                        break
                    report["complete_trials"] += 1
                    valid = all(value["problem"] is None and value["signed_volume"] > 0
                                and value["edge_aspect_ratio"] <= 4 for value in quality)
                    if not valid:
                        report["invalid_trials"] += 1
                        continue
                    trial_j = min(value["corner_scaled_jacobian"] for value in quality)
                    if trial_j <= before_j:
                        report["non_improving_trials"] += 1
                    elif trial_j > best_j:
                        best, best_j = (candidate, quality), trial_j
                if best is not None:
                    state.points[node], quality = best
                    for index, value in zip(affected, quality):
                        state.metrics[index] = value
                        if value["corner_scaled_jacobian"] < .5:
                            failed.add(index)
                        else:
                            failed.discard(index)
                    report["moves"] += 1
                    pass_moves += 1
                    accepted = True
                if exhausted:
                    if not failed:
                        report.update(status="target_met", stop_reason="target_met_at_budget")
                    else:
                        report.update(status="budget_exhausted", stop_reason="incident_trial_budget")
                    break
                if accepted or not representable:
                    break
            if not accepted and not exhausted:
                report["rejected"] += 1
            if exhausted:
                break
            if not failed:
                report.update(status="target_met", stop_reason="target_met_at_budget"
                              if report["metrics_calls"] == max_evaluations else "target_met")
                break
        else:
            report["iterations"] += 1
            if not pass_moves:
                report.update(status="stalled_finite_stencil", stop_reason="zero_accepted_full_sweep")
        if report["status"] is not None:
            break
        if report["metrics_calls"] == max_evaluations:
            report.update(status="budget_exhausted", stop_reason="trial_budget")
            break
    if report["status"] is None:
        report.update(status="iteration_limit", stop_reason="iteration_limit")
    report["after"] = _corner_j_summary(state.metrics)
    report["max_displacement"] = max(math.dist(point, state.points[node]) for node, point in zip(state.ids, state.original))
    return tuple(state.points[node] for node in state.ids), report
