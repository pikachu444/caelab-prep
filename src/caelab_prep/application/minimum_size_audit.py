"""Measure linear topological edges without modifying or cleaning a mesh.

Distances and the threshold use the caller's same length unit. Unsupported
orders stay explicit; corner chords are not measurements of curved edges.
"""
import math

from .mesh_candidates import MeshCell, MeshNode
from ..cae_core.errors import PrepError


_EDGES = {
    (1, 1, 1): ("line2", 2, ((0, 1),)),
    (2, 2, 1): ("tri3", 3, ((0, 1), (1, 2), (2, 0))),
    (2, 3, 1): ("quad4", 4, ((0, 1), (1, 2), (2, 3), (3, 0))),
    (3, 4, 1): ("tet4", 4, ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))),
    (3, 5, 1): ("hex8", 8, ((0, 1), (1, 2), (2, 3), (3, 0),
                            (4, 5), (5, 6), (6, 7), (7, 4),
                            (0, 4), (1, 5), (2, 6), (3, 7))),
}


def _invalid(message, **details):
    raise PrepError("invalid_minimum_size_input", message, details)


def audit_minimum_edges(nodes, cells, minimum_size):
    """Return a JSON-safe measurement report; cleanup candidates are IDs only.

    Malformed coordinates, identities and references raise PrepError. Finite
    coordinates whose edge distance overflows, and zero-length edges, produce
    explicit invalid cells. Threshold comparisons use the actual math.dist
    value with no tolerance: equality passes. No input state is changed.
    """
    if type(minimum_size) not in (int, float):
        raise PrepError("invalid_minimum_size", "Minimum size must be a finite positive length.")
    try:
        minimum = float(minimum_size)
    except OverflowError as exc:
        raise PrepError("invalid_minimum_size", "Minimum size must be a finite positive length.") from exc
    if not math.isfinite(minimum) or minimum <= 0:
        raise PrepError("invalid_minimum_size", "Minimum size must be a finite positive length.")
    try:
        source_nodes, source_cells = tuple(nodes), tuple(cells)
    except TypeError as exc:
        raise PrepError("invalid_minimum_size_input", "Expected MeshNode and MeshCell sequences.") from exc
    coordinates = {}
    for node in source_nodes:
        if not isinstance(node, MeshNode) or type(node.id) is not int or node.id <= 0:
            _invalid("Each node needs a MeshNode with a positive integer ID.")
        if node.id in coordinates:
            _invalid("Duplicate node IDs are ambiguous.", node_id=node.id)
        try:
            point = tuple(node.xyz)
            if len(point) != 3 or any(type(value) not in (int, float) for value in point):
                raise ValueError("Expected numeric XYZ triples")
            point = tuple(float(value) for value in point)
            if any(not math.isfinite(value) for value in point):
                raise ValueError("Expected finite XYZ coordinates")
        except (TypeError, ValueError, OverflowError) as exc:
            raise PrepError("invalid_minimum_size_input", "Node coordinates must be finite numeric XYZ triples.",
                            {"node_id": node.id}) from exc
        coordinates[node.id] = point
    records, seen = [], set()
    below, unsupported, invalid, skipped = [], [], [], []
    edge_bearing = 0
    for cell in source_cells:
        if not isinstance(cell, MeshCell) or type(cell.id) is not int or cell.id <= 0:
            _invalid("Each cell needs a MeshCell with a positive integer ID.")
        if cell.id in seen:
            _invalid("Duplicate cell IDs are ambiguous.", cell_id=cell.id)
        seen.add(cell.id)
        if (type(cell.dimension) is not int or cell.dimension not in (0, 1, 2, 3)
                or type(cell.element_type) is not int or cell.element_type <= 0
                or type(cell.order) is not int or cell.order < 0 or not isinstance(cell.element_name, str)):
            _invalid("Cell dimension, type, order and name must describe its source inventory.", cell_id=cell.id)
        try:
            connectivity = tuple(cell.node_ids)
        except TypeError as exc:
            raise PrepError("invalid_minimum_size_input", "Cell connectivity must contain node IDs.", {"cell_id": cell.id}) from exc
        if (not connectivity or any(type(node) is not int or node <= 0 for node in connectivity)
                or len(set(connectivity)) != len(connectivity)):
            _invalid("Cell node references must be distinct positive integer IDs.", cell_id=cell.id)
        missing = [node for node in connectivity if node not in coordinates]
        if missing:
            _invalid("Every source node reference must resolve.", cell_id=cell.id, missing_node_ids=missing)
        record = {"id": cell.id, "dimension": cell.dimension, "element_type": cell.element_type,
                  "element_name": cell.element_name, "order": cell.order, "node_ids": list(connectivity),
                  "family": None, "status": None, "min_length": None, "problem": None,
                  "edge_count": 0, "short_edges": [], "invalid_edges": []}
        records.append(record)
        signature = (cell.dimension, cell.element_type, cell.order)
        if signature == (0, 15, 0) and len(connectivity) == 1:
            record.update(family="point", status="skipped", problem="point_annotation")
            skipped.append(cell.id)
            continue
        spec = _EDGES.get(signature)
        if spec is None:
            record.update(status="unsupported", problem="unsupported_element_signature")
            unsupported.append(cell.id)
            continue
        family, arity, edges = spec
        if len(connectivity) != arity:
            _invalid("A supported linear cell has the wrong number of source nodes.",
                     cell_id=cell.id, expected_nodes=arity, actual_nodes=len(connectivity))
        record.update(family=family, status="measured", edge_count=len(edges))
        edge_bearing += 1
        lengths = []
        for first, second in edges:
            pair = [connectivity[first], connectivity[second]]
            length = math.dist(coordinates[pair[0]], coordinates[pair[1]])
            if not math.isfinite(length):
                record["invalid_edges"].append({"node_ids": pair, "length": None, "problem": "nonfinite_edge"})
                continue
            lengths.append(length)
            if length < minimum:
                record["short_edges"].append({"node_ids": pair, "length": length})
            if length == 0:
                record["invalid_edges"].append({"node_ids": pair, "length": 0.0, "problem": "zero_edge"})
        nonfinite = any(edge["problem"] == "nonfinite_edge" for edge in record["invalid_edges"])
        record["min_length"] = None if nonfinite else min(lengths)
        if record["short_edges"]:
            below.append(cell.id)
        if record["invalid_edges"]:
            record.update(status="invalid", problem="nonfinite_edge" if nonfinite else "zero_edge")
            invalid.append(cell.id)
        elif record["short_edges"]:
            record["problem"] = "below_minimum"
    problem = ("no_supported_edge_bearing_cells" if not edge_bearing else
               "unsupported_elements" if unsupported else "invalid_edge_measurements" if invalid else
               "below_minimum" if below else None)
    observed = [record["min_length"] for record in records if record["min_length"] is not None]
    return {"minimum_size": minimum, "passed": problem is None, "problem": problem,
            "cells": records, "supported_edge_bearing_cells": edge_bearing,
            "minimum_observed_length": min(observed) if observed else None,
            "below_minimum_ids": below, "cleanup_candidate_ids": list(below),
            "unsupported_ids": unsupported, "invalid_ids": invalid, "skipped_point_ids": skipped,
            "modifications": 0}
