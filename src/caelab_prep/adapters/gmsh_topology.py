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
