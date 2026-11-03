"""Pure, bounded wire checks over one Gmsh geometry inspection.

Tags are local to the input. This is neither a CAD kernel nor cross-import
topology matching. Unsupported or malformed wires return None.
"""
from collections import Counter
import math


def four_edge_cycle(curve_tags, curves_by_tag):
    """Return four distinct edges/vertices forming one simple topology cycle."""
    try:
        if (not isinstance(curve_tags, (list, tuple)) or len(curve_tags) != 4
                or any(type(tag) is not int or tag == 0 for tag in curve_tags)
                or len(set(map(abs, curve_tags))) != 4):
            return None
        vertices, edges, degrees = {}, {}, Counter()
        for signed in curve_tags:
            tag = abs(signed)
            curve = curves_by_tag[tag]
            if type(curve["backend_tag"]) is not int or curve["backend_tag"] != tag or len(curve["endpoints"]) != 2:
                return None
            pair = []
            for endpoint in curve["endpoints"]:
                identity, coordinates = endpoint["backend_tag"], endpoint["xyz"]
                if (type(identity) is not int or identity <= 0 or len(coordinates) != 3
                        or any(type(value) not in (int, float) for value in coordinates)):
                    return None
                point = tuple(float(value) for value in coordinates)
                if not all(math.isfinite(value) for value in point):
                    return None
                if identity in vertices and vertices[identity] != point:
                    return None
                vertices[identity] = point
                degrees[identity] += 1
                pair.append(identity)
            if pair[0] == pair[1] or vertices[pair[0]] == vertices[pair[1]]:
                return None
            edges[tag] = tuple(pair)
        if (len(vertices) != 4 or set(degrees.values()) != {2}
                or len({tuple(sorted(pair)) for pair in edges.values()}) != 4):
            return None
        return {"vertices": vertices, "edges": edges}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def rectangular_wire(curve_tags, curves_by_tag, plane_axis, plane_coordinate, tolerance):
    """Require a single axis-aligned four-Line perimeter in the given plane."""
    try:
        if (type(plane_axis) is not int or plane_axis not in (0, 1, 2)
                or type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance <= 0
                or type(plane_coordinate) not in (int, float) or not math.isfinite(plane_coordinate)):
            return None
        cycle = four_edge_cycle(curve_tags, curves_by_tag)
        if cycle is None or any(curves_by_tag[tag]["geometry_type"] != "Line" for tag in cycle["edges"]):
            return None
        vertices, edges = cycle["vertices"], cycle["edges"]
        axes = [axis for axis in range(3) if axis != plane_axis]
        if any(abs(point[plane_axis] - plane_coordinate) > tolerance for point in vertices.values()):
            return None
        low = [min(point[axis] for point in vertices.values()) for axis in axes]
        high = [max(point[axis] for point in vertices.values()) for axis in axes]
        if any(b - a <= 2 * tolerance for a, b in zip(low, high)):
            return None
        corners = {}
        for identity, point in vertices.items():
            corner = []
            for axis, a, b in zip(axes, low, high):
                if abs(point[axis] - a) <= tolerance: corner.append(0)
                elif abs(point[axis] - b) <= tolerance: corner.append(1)
                else: return None
            corners[identity] = tuple(corner)
        if set(corners.values()) != {(0, 0), (0, 1), (1, 0), (1, 1)}:
            return None
        if any(sum(a != b for a, b in zip(corners[first], corners[second])) != 1 for first, second in edges.values()):
            return None
        lengths = [b - a for a, b in zip(low, high)]
        area, perimeter = math.prod(lengths), 2 * math.fsum(lengths)
        if not math.isfinite(area) or not math.isfinite(perimeter):
            return None
        return {**cycle, "plane_axis": plane_axis, "plane_coordinate": plane_coordinate,
                "plane_axes": axes, "minimum": low, "maximum": high, "area": area, "perimeter": perimeter}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _dot(first, second):
    return math.fsum(a * b for a, b in zip(first, second))


def _cross(first, second):
    a, b, c = first
    x, y, z = second
    return (b * z - c * y, c * x - a * z, a * y - b * x)


def planar_trapezoid_wire(curve_tags, curves_by_tag, plane_normal, plane_offset,
                          axial_axis, axial_range, tolerance):
    """Check a convex four-line patch between two axial cap planes.

    The caller supplies a unit plane normal and its normalized offset. Raw
    loop ordering/signs do not determine winding; shared vertices do.
    """
    try:
        numeric = lambda value: type(value) in (int, float) and math.isfinite(value)
        if (not numeric(tolerance) or tolerance <= 0 or type(axial_axis) is not int or axial_axis not in (0, 1, 2)
                or len(plane_normal) != 3 or not all(numeric(v) for v in plane_normal)
                or abs(math.hypot(*plane_normal) - 1.) > 1e-12 or not numeric(plane_offset)
                or len(axial_range) != 2 or not all(numeric(v) for v in axial_range)
                or not 2 * tolerance < axial_range[1] - axial_range[0] < float("inf")):
            return None
        cycle = four_edge_cycle(curve_tags, curves_by_tag)
        if cycle is None or any(curves_by_tag[tag]["geometry_type"] != "Line" for tag in cycle["edges"]):
            return None
        vertices = cycle["vertices"]
        levels, adjacency = {}, {identity: [] for identity in vertices}
        for identity, point in vertices.items():
            residual = _dot(plane_normal, point) + plane_offset
            if not math.isfinite(residual) or abs(residual) > tolerance:
                return None
            matches = [i for i, value in enumerate(axial_range) if abs(point[axial_axis] - value) <= tolerance]
            if len(matches) != 1:
                return None
            levels[identity] = matches[0]
        if sorted(levels.values()) != [0, 0, 1, 1]:
            return None
        horizontal = 0
        for first, second in cycle["edges"].values():
            adjacency[first].append(second); adjacency[second].append(first)
            horizontal += levels[first] == levels[second]
        if horizontal != 2:
            return None
        order = [min(vertices)]
        previous = None
        while len(order) < 4:
            next_vertex = min(value for value in adjacency[order[-1]] if value != previous)
            previous = order[-1]
            if next_vertex in order:
                return None
            order.append(next_vertex)
        if order[0] not in adjacency[order[-1]]:
            return None
        origin = vertices[order[0]]
        local = [tuple(v - base for v, base in zip(vertices[identity], origin)) for identity in order]
        signed_area = _dot(plane_normal, tuple(math.fsum(values) / 2 for values in
            zip(_cross(local[1], local[2]), _cross(local[2], local[3]))))
        if not math.isfinite(signed_area):
            return None
        if signed_area < 0:
            order = [order[0], *reversed(order[1:])]
        points = [vertices[identity] for identity in order]
        edges = [tuple(b - a for a, b in zip(first, second)) for first, second in zip(points, points[1:] + points[:1])]
        lengths = [math.hypot(*edge) for edge in edges]
        perimeter = math.fsum(lengths)
        if (not all(math.isfinite(value) and value > 2 * tolerance for value in lengths)
                or not math.isfinite(perimeter) or abs(signed_area) <= tolerance * perimeter):
            return None
        turns = [_dot(_cross(edges[i], edges[(i+1) % 4]), plane_normal) for i in range(4)]
        if any(not math.isfinite(turn) or turn <= tolerance * (lengths[i] + lengths[(i+1) % 4])
               for i, turn in enumerate(turns)):
            return None
        return {**cycle, "ordered_vertices": points, "plane_normal": list(plane_normal),
                "plane_offset": plane_offset, "axial_axis": axial_axis, "axial_range": list(axial_range),
                "area": abs(signed_area), "perimeter": perimeter}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def point_in_planar_wire(wire, point, tolerance):
    """Check interior clearance on a wire returned by planar_trapezoid_wire."""
    try:
        if (len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
                or type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance <= 0):
            return False
        normal, points = wire["plane_normal"], wire["ordered_vertices"]
        if (len(points) != 4 or len(normal) != 3 or any(len(vertex) != 3 for vertex in points)
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       for value in [*normal, wire["plane_offset"], *(v for vertex in points for v in vertex)])
                or abs(math.hypot(*normal) - 1.) > 1e-12):
            return False
        residual = _dot(normal, point) + wire["plane_offset"]
        if not math.isfinite(residual) or abs(residual) > tolerance:
            return False
        for first, second in zip(points, points[1:] + points[:1]):
            edge = tuple(b - a for a, b in zip(first, second))
            offset = tuple(p - a for p, a in zip(point, first))
            clearance = _dot(_cross(edge, offset), normal) / math.hypot(*edge)
            if not math.isfinite(clearance) or clearance <= tolerance:
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return False
