"""Strict, CAD-independent preflight plus the shared Gmsh SDK MSH reader.

Format source: https://gmsh.info/doc/texinfo/#MSH-file-format and its legacy
version-2 section. Source preflight prevents duplicate IDs and extra sections
from disappearing through SDK normalization. Valid inputs are SDK-read and
compared against their complete source inventory before SDK values are returned.
The caller owns units, physical-group interpretation and document adoption.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import shlex
import sys


# Gmsh's documented element numbers. Unsupported physical families are retained
# for the candidate's complete inventory and rejected by the admission layer.
_TYPES = {
    1: (1, 1, 2, "Line 2"), 2: (2, 1, 3, "Triangle 3"),
    3: (2, 1, 4, "Quadrilateral 4"), 4: (3, 1, 4, "Tetrahedron 4"),
    5: (3, 1, 8, "Hexahedron 8"), 6: (3, 1, 6, "Prism 6"),
    7: (3, 1, 5, "Pyramid 5"), 8: (1, 2, 3, "Line 3"),
    9: (2, 2, 6, "Triangle 6"), 10: (2, 2, 9, "Quadrilateral 9"),
    11: (3, 2, 10, "Tetrahedron 10"), 12: (3, 2, 27, "Hexahedron 27"),
    13: (3, 2, 18, "Prism 18"), 14: (3, 2, 14, "Pyramid 14"),
    15: (0, 0, 1, "Point"), 16: (2, 2, 8, "Quadrilateral 8"),
    17: (3, 2, 20, "Hexahedron 20"), 18: (3, 2, 15, "Prism 15"),
    19: (3, 2, 13, "Pyramid 13"),
}


def _integer(value, *, minimum=0):
    number = int(value)
    if not value.lstrip("+").isdigit() or number < minimum:
        raise ValueError(f"Invalid integer {value!r}")
    return number


def _real(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("MSH coordinates must be finite")
    return number


class _Tokens:
    def __init__(self, lines):
        self.tokens = iter(" ".join(lines).split())

    def take(self, cast=str):
        try:
            return cast(next(self.tokens))
        except StopIteration:
            raise ValueError("Truncated MSH section") from None

    def end(self):
        if next(self.tokens, None) is not None:
            raise ValueError("Unexpected trailing MSH values")


def _sections(path):
    raw = Path(path).read_bytes()
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        raise ValueError("Only UTF-8/ASCII MSH 2.2 and 4.1 text files are supported; binary is unsupported") from None
    result, current, values = {}, None, []
    allowed = {"MeshFormat", "PhysicalNames", "Entities", "Nodes", "Elements", "Comments"}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if current is None:
            if not line.startswith("$") or line.startswith("$End"):
                raise ValueError("Expected an MSH section header")
            current = line[1:]
            if current not in allowed:
                raise ValueError(f"Unsupported MSH section ${current}; no data was imported")
            if current in result and current != "Comments":
                raise ValueError(f"Duplicate MSH section ${current}")
            values = []
        elif line == "$End" + current:
            result[current] = values
            current = None
        elif line.startswith("$") and current != "Comments":
            raise ValueError(f"Missing $End{current}")
        else:
            values.append(line)
    if current is not None:
        raise ValueError(f"Missing $End{current}")
    if not {"MeshFormat", "Nodes", "Elements"} <= result.keys():
        raise ValueError("MSH requires MeshFormat, Nodes and Elements sections")
    return result


def read_msh(path):
    """Preflight every source record; this function alone does not admit a mesh."""
    sections = _sections(path)
    header = " ".join(sections["MeshFormat"]).split()
    if len(header) != 3 or header[0] not in ("2.2", "4.1") or header[1:] != ["0", "8"]:
        raise ValueError("Supported format: Gmsh MSH 2.2 or 4.1 ASCII (file-type 0, data-size 8)")
    version = header[0]
    names = {}
    if "PhysicalNames" in sections:
        lines = sections["PhysicalNames"]
        count = _integer(lines[0]) if lines else -1
        if len(lines) != count + 1:
            raise ValueError("PhysicalNames count mismatch")
        for line in lines[1:]:
            values = shlex.split(line)
            if len(values) != 3:
                raise ValueError("Malformed physical name")
            dim, tag = _integer(values[0]), _integer(values[1], minimum=1)
            if dim > 3 or (dim, tag) in names or not values[2].strip() or any(ord(c) < 32 for c in values[2]):
                raise ValueError("Duplicate or invalid physical group")
            names[(dim, tag)] = values[2]
    entities = {}
    if "Entities" in sections:
        if version != "4.1":
            raise ValueError("Entities is supported only in MSH 4.1")
        stream = _Tokens(sections["Entities"])
        counts = [stream.take(_integer) for _ in range(4)]
        for dim, count in enumerate(counts):
            for _ in range(count):
                tag = stream.take(lambda x: _integer(x, minimum=1))
                for _ in range(3 if dim == 0 else 6): stream.take(_real)
                physical = [stream.take(lambda x: _integer(x, minimum=1)) for _ in range(stream.take(_integer))]
                if (dim, tag) in entities or len(physical) != len(set(physical)):
                    raise ValueError("Duplicate entity or physical group membership")
                boundary = [stream.take(int) for _ in range(stream.take(_integer))] if dim else []
                entities[(dim, tag)] = {"dimension": dim, "tag": tag, "physical_tags": physical, "boundary_tags": boundary}
        stream.end()
        for (dim, _), entity in entities.items():
            if any(tag == 0 or (dim - 1, abs(tag)) not in entities for tag in entity["boundary_tags"]):
                raise ValueError("Entity boundary references an absent lower-dimensional entity")
    node_ids, coordinates, node_entities = [], [], {}
    stream = _Tokens(sections["Nodes"])
    if version == "2.2":
        count = stream.take(_integer)
        for _ in range(count):
            node_ids.append(stream.take(lambda x: _integer(x, minimum=1)))
            coordinates.append([stream.take(_real) for _ in range(3)])
    else:
        block_count, count, minimum, maximum = [stream.take(_integer) for _ in range(4)]
        for _ in range(block_count):
            dim, tag, parametric, size = [stream.take(_integer) for _ in range(4)]
            if dim > 3 or tag < 1 or parametric != 0:
                raise ValueError("Invalid node entity or unsupported parametric node coordinates")
            if "Entities" in sections and (dim, tag) not in entities:
                raise ValueError("Node block references an absent entity")
            identifiers = [stream.take(lambda x: _integer(x, minimum=1)) for _ in range(size)]
            node_ids.extend(identifiers)
            for identifier in identifiers:
                node_entities[identifier] = (dim, tag)
                coordinates.append([stream.take(_real) for _ in range(3)])
        if len(node_ids) != count or not node_ids or (min(node_ids), max(node_ids)) != (minimum, maximum):
            raise ValueError("Node count or tag range mismatch")
    stream.end()
    if not node_ids or len(node_ids) != len(set(node_ids)):
        raise ValueError("Empty mesh or duplicate node IDs")
    valid_nodes = set(node_ids)
    blocks = {}
    element_ids = set()

    def add(identifier, typ, conn, dim=None, tag=0, physical=()):
        if typ not in _TYPES:
            raise ValueError(f"Unsupported element type {typ}; the entire input is rejected")
        actual_dim, order, arity, name = _TYPES[typ]
        if dim is not None and dim != actual_dim:
            raise ValueError("Element dimension disagrees with its type")
        if identifier in element_ids or identifier < 1 or len(conn) != arity or len(set(conn)) != arity or not set(conn) <= valid_nodes:
            raise ValueError(f"Duplicate ID, invalid connectivity or missing node in element {identifier}")
        element_ids.add(identifier)
        key = (actual_dim, tag, typ, tuple(sorted(physical)))
        block = blocks.setdefault(key, {"dimension": actual_dim, "entity_tag": tag, "element_type": typ,
            "element_name": name, "order": order, "nodes_per_element": arity, "physical_tags": list(key[-1]),
            "ids": [], "connectivity": []})
        block["ids"].append(identifier); block["connectivity"].append(conn)

    stream = _Tokens(sections["Elements"])
    if version == "2.2":
        count = stream.take(_integer)
        for _ in range(count):
            identifier, typ, tags_count = [stream.take(_integer) for _ in range(3)]
            tags = [stream.take(_integer) for _ in range(tags_count)]
            if tags_count > 2:
                raise ValueError("Partitioned or additional MSH 2.2 element tags are unsupported")
            if typ not in _TYPES:
                raise ValueError(f"Unsupported element type {typ}; the entire input is rejected")
            conn = [stream.take(lambda x: _integer(x, minimum=1)) for _ in range(_TYPES[typ][2])]
            add(identifier, typ, conn, tag=tags[1] if len(tags) > 1 else 0, physical=tags[:1] if tags and tags[0] else ())
    else:
        block_count, count, minimum, maximum = [stream.take(_integer) for _ in range(4)]
        for _ in range(block_count):
            dim, tag, typ, size = [stream.take(_integer) for _ in range(4)]
            if dim > 3 or tag < 1 or "Entities" in sections and (dim, tag) not in entities:
                raise ValueError("Element block references an invalid or absent entity")
            if typ not in _TYPES:
                raise ValueError(f"Unsupported element type {typ}; the entire input is rejected")
            physical = entities.get((dim, tag), {}).get("physical_tags", ())
            for _ in range(size):
                identifier = stream.take(lambda x: _integer(x, minimum=1))
                conn = [stream.take(lambda x: _integer(x, minimum=1)) for _ in range(_TYPES[typ][2])]
                add(identifier, typ, conn, dim, tag, physical)
        if len(element_ids) != count or not element_ids or (min(element_ids), max(element_ids)) != (minimum, maximum):
            raise ValueError("Element count or tag range mismatch")
    stream.end()
    if not element_ids:
        raise ValueError("MSH contains no elements")
    # Retain explicitly declared groups even if empty; admission reports them
    # instead of quietly dropping a requested set.
    group_keys = set(names) | {(block["dimension"], tag) for block in blocks.values() for tag in block["physical_tags"]}
    group_keys |= {(dim, tag) for (dim, _), entity in entities.items() for tag in entity["physical_tags"]}
    return {"format_version": version, "nodes": {"ids": node_ids, "coordinates": coordinates},
            "blocks": list(blocks.values()), "node_entities": {str(key): list(value) for key, value in node_entities.items()},
            "entities": list(entities.values()), "physical_groups": [
                {"dimension": dim, "tag": tag, "name": names.get((dim, tag), f"Physical {dim}:{tag}")}
                for dim, tag in sorted(group_keys)]}


def inspect_msh(path):
    """Reuse the CAD candidate's SDK reader without fabricating CAD provenance.

    Element/node IDs are compared to the captured file, never to pre-write SDK
    memory (Gmsh writers may renumber). Per-element MSH 2.2 physical tags and
    MSH 4.1 node classification remain explicit source metadata.
    """
    source = read_msh(path)
    try:
        from ..application.mesh_candidates import _inspect_msh
        sdk = _inspect_msh(path)
    except (ImportError, OSError) as error:
        raise ValueError("Standalone MSH inspection requires the Gmsh 4.15.2 SDK: install caelab-prep[cad] and its native libraries.") from error
    expected_nodes = dict(zip(source["nodes"]["ids"], source["nodes"]["coordinates"]))
    actual_nodes = dict(zip(sdk["nodes"]["ids"], sdk["nodes"]["coordinates"]))
    if (len(actual_nodes) != len(sdk["nodes"]["ids"]) or expected_nodes != actual_nodes):
        raise ValueError("Gmsh SDK node inventory differs from the captured MSH; no data was imported")

    def cell_map(blocks, entity_key):
        result = {}
        for block in blocks:
            for identifier, connectivity in zip(block["ids"], block["connectivity"]):
                if identifier in result:
                    raise ValueError("Gmsh SDK returned duplicate element IDs")
                result[identifier] = (block["dimension"], block[entity_key], block["element_type"],
                    block["order"], block["nodes_per_element"], tuple(connectivity))
        return result

    expected_cells = cell_map(source["blocks"], "entity_tag")
    actual_cells = cell_map(sdk["element_blocks"], "backend_tag")
    if expected_cells != actual_cells:
        raise ValueError("Gmsh SDK element inventory differs from the captured MSH; no data was imported")
    expected_groups = {(group["dimension"], group["tag"]): (group["name"], set())
                       for group in source["physical_groups"]}
    for record in [*source["entities"], *source["blocks"]]:
        entity = record.get("tag", record.get("entity_tag"))
        for tag in record["physical_tags"]:
            expected_groups[(record["dimension"], tag)][1].add(entity)
    actual_groups = {(group["dimension"], group["tag"]):
        (group["name"] or f"Physical {group['dimension']}:{group['tag']}", set(group["entities"]))
        for group in sdk["physical_groups"]}
    # A declared empty physical name has no SDK entity. Preserve that declaration
    # so admission reports the missing members explicitly, rather than dropping it.
    populated = {key: value for key, value in expected_groups.items() if value[1]}
    if actual_groups != populated:
        raise ValueError("Gmsh SDK physical-group inventory differs from the captured MSH; no data was imported")
    # Return SDK numerical data in stable source order. Source-owned group tags
    # avoid turning overlapping physical groups into duplicated physical cells.
    source["nodes"] = {"ids": list(expected_nodes), "coordinates": [actual_nodes[key] for key in expected_nodes]}
    sdk_cells = {identifier: (block, connectivity) for block in sdk["element_blocks"]
                 for identifier, connectivity in zip(block["ids"], block["connectivity"])}
    for block in source["blocks"]:
        sdk_block = sdk_cells[block["ids"][0]][0]
        block["element_name"] = sdk_block["element_name"]
        block["connectivity"] = [list(sdk_cells[key][1]) for key in block["ids"]]
    return source


if __name__ == "__main__":
    try:
        result = {"ok": True, "mesh": inspect_msh(sys.argv[1])}
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, allow_nan=False))
    raise SystemExit(0 if result["ok"] else 1)
