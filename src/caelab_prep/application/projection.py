"""Read-only geometry payloads and an explicit mutable/JSON boundary.

Geometry is cached by the session's document epoch and projection revision.
Only the small view stamps are renewed after scalar commands. Consumers must
request ``mesh_view(mutable=True)`` when they need editable lists or JSON data.
"""
from collections.abc import Mapping
from types import MappingProxyType


def readonly(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: readonly(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(readonly(item) for item in value)
    return value


def mutable(value):
    """Materialize a detached JSON-compatible tree; never used for rendering."""
    if isinstance(value, Mapping):
        return {key: mutable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [mutable(item) for item in value]
    return value


def freeze_mesh_payload(*, points, node_ids, cells, diagnostics, node_resources, document_id):
    """Seal private projection-builder buffers exactly once, without copying dicts.

    Ownership requirement: cells, their node lists, points and node_resources
    must be fresh unpublished results from DeckResource.mesh_projection and
    the session merge. They must never be passed to another caller beforehand.
    This specialized boundary must NOT replace readonly for caller-owned data.
    """
    atom_keys = {"id", "type", "formulation", "part_id", "card_id", "resource_id"}
    sealed_cells = []
    for cell in cells:
        cell["nodes"] = tuple(cell["nodes"])
        for key, value in cell.items():
            if key in atom_keys:
                if value is not None and not isinstance(value, (str,int,float,bool)):
                    cell[key] = readonly(value)
            elif key == "part_ref" and isinstance(value, MappingProxyType):
                continue  # One verified read-only PART reference per component.
            elif key != "nodes": cell[key] = readonly(value)
        sealed_cells.append(MappingProxyType(cell))
    owners = {}
    for identifier, resource_ids in node_resources.items():
        key = tuple(resource_ids)
        node_resources[identifier] = owners.setdefault(key, key)
    return MappingProxyType({"points": tuple(tuple(point) for point in points), "node_ids": tuple(node_ids),
        "cells": tuple(sealed_cells), "diagnostics": readonly(diagnostics), "node_resources": MappingProxyType(node_resources),
        "document_id": document_id, "immutable_projection": True})
