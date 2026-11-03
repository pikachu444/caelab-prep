"""Reusable standalone mesh admission, independent of CAD, Qt and solvers.

MSH 2.2/4.1 ASCII contains no reliable length-unit declaration. Import requires
an explicit source unit; adoption requires the same working unit and never
rescales coordinates implicitly. Source physical groups become sets. Disjoint
combinations of top-dimensional group membership become parts, retaining overlap
without duplicating elements. Ungrouped entities remain explicit separate parts.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from itertools import combinations
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import UUID, uuid4, uuid5

from ..cae_core.errors import PrepError
from .mesh_candidates import (AssetDigest, CellInventory, MeshCell, MeshGroup,
    MeshPart, NativeMesh, QualityLimits, QualityReport, _nodes, _quality, _sha)


@dataclass(frozen=True)
class ImportedMeshCandidate:
    mesh_uuid: str
    length_unit: str
    dimension: int
    nodes: tuple
    cells: tuple[MeshCell, ...]
    parts: tuple[MeshPart, ...]
    groups: tuple[MeshGroup, ...]
    inventory: tuple[CellInventory, ...]
    quality: QualityReport
    assets: tuple[AssetDigest, ...]
    format_version: str
    geometry_resource_uuid: None = None

    @property
    def manifest_path(self):
        return next(asset.path for asset in self.assets if asset.kind == "metadata")

    def to_native_mesh(self, *, length_unit=None):
        if length_unit is not None and length_unit != self.length_unit:
            raise PrepError("unit_mismatch", "Source units cannot be changed by relabeling; import with the correct source unit.")
        if not self.quality.passed:
            raise PrepError("mesh_quality", "The whole import is blocked by unsupported or invalid elements.",
                            {"element_ids": list(self.quality.problem_ids), "unsupported_ids": list(self.quality.unsupported_ids)})
        physical = tuple(cell for cell in self.cells if cell.dimension == self.dimension)
        used = {node for cell in physical for node in cell.node_ids}
        return NativeMesh(self.nodes, physical, self.parts, self.length_unit, None,
                          self.mesh_uuid, self.dimension, self.inventory, len(self.cells) - len(physical),
                          tuple(node.id for node in self.nodes if node.id not in used), self.assets,
                          "standalone_msh", self.groups)


def _read_in_worker(path, *, cancel_event=None, timeout=60.0):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PrepError("invalid_request", "Mesh inspection timeout must be finite and positive.")
    if cancel_event is not None and cancel_event.is_set():
        raise PrepError("cancelled", "Mesh import was cancelled.")
    process = subprocess.Popen([sys.executable, "-m", "caelab_prep.adapters.msh_worker", str(path)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    started = time.monotonic()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise PrepError("cancelled", "Mesh import was cancelled.", {"pid": process.pid})
            if time.monotonic() - started >= timeout:
                raise PrepError("import_timeout", "Mesh inspection exceeded its time limit.", {"pid": process.pid})
            try:
                stdout, stderr = process.communicate(timeout=min(.05, timeout))
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            result = json.loads(stdout)
        except (ValueError, TypeError):
            raise PrepError("invalid_mesh", "The mesh reader did not produce a valid result.", {"stderr": stderr[-2000:]}) from None
        if process.returncode or not result.get("ok"):
            raise PrepError("invalid_mesh", result.get("error", "Mesh inspection failed."))
        if cancel_event is not None and cancel_event.is_set():
            raise PrepError("cancelled", "Mesh import was cancelled.", {"pid": process.pid})
        return result["mesh"]
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate(timeout=3)


def import_standalone_mesh(source, output_dir, *, length_unit, cancel_event=None, timeout=60.0,
                           element_profile="linear"):
    """Capture a user MSH and return a reviewable candidate; change no document."""
    if length_unit not in ("mm", "cm", "m"):
        raise PrepError("unknown_length_unit", "Declare the MSH source length unit: mm, cm or m.")
    if element_profile not in ("linear", "straight_tet10"):
        raise PrepError("unsupported_mesh", "Choose the linear or explicit straight_tet10 import profile.")
    if not str(output_dir).strip():
        raise PrepError("invalid_request", "Choose a directory to retain the imported mesh assets.")
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".msh":
        raise PrepError("invalid_request", "Choose a standalone .msh file.")
    if cancel_event is not None and cancel_event.is_set():
        raise PrepError("cancelled", "Mesh import was cancelled.")
    identifier = str(uuid4())
    folder = Path(output_dir).expanduser().resolve() / ("msh-" + identifier)
    folder.mkdir(parents=True, exist_ok=False)
    captured = folder / "input.msh"
    shutil.copyfile(source, captured)
    # The copied bytes, not a mutable original path, are the import's source.
    digest = _sha(captured)
    data = _read_in_worker(captured, cancel_event=cancel_event, timeout=timeout)
    metadata = folder / "metadata.json"
    manifest = {"schema": "caelab.standalone-msh", "version": 1, "mesh_uuid": identifier,
                "length_unit": length_unit, "name": source.stem, "format_version": data["format_version"],
                "element_profile": element_profile,
                "source": {"path": str(captured), "original_path": str(source), "sha256": digest}}
    metadata.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assets = (AssetDigest("msh", str(captured), digest), AssetDigest("metadata", str(metadata), _sha(metadata)))
    return _candidate(data, manifest, assets)


def read_imported_mesh(path, *, cancel_event=None, timeout=60.0):
    """Reopen a standalone import using only its real MSH and manifest."""
    metadata = Path(path).expanduser().resolve()
    try:
        manifest = json.loads(metadata.read_text(encoding="utf-8"))
        if manifest["schema"] != "caelab.standalone-msh" or type(manifest["version"]) is not int or manifest["version"] != 1:
            raise ValueError("Unsupported import manifest")
        UUID(manifest["mesh_uuid"])
        if manifest["length_unit"] not in ("mm", "cm", "m"):
            raise ValueError("An explicit source length unit is required")
        if "original_path" in manifest["source"] and (not isinstance(manifest["source"]["original_path"], str) or not manifest["source"]["original_path"].strip()):
            raise ValueError("The original source path must be a nonempty string")
        source = Path(manifest["source"]["path"])
        digest = _sha(source)
        if digest != manifest["source"]["sha256"]:
            raise PrepError("candidate_changed", "Captured MSH bytes changed after import.")
        data = _read_in_worker(source, cancel_event=cancel_event, timeout=timeout)
        if manifest["format_version"] != data["format_version"]:
            raise ValueError("MSH version differs from its import manifest")
        assets = (AssetDigest("msh", str(source), digest), AssetDigest("metadata", str(metadata), _sha(metadata)))
        return _candidate(data, manifest, assets)
    except PrepError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PrepError("invalid_candidate", f"Invalid standalone mesh candidate: {exc}") from exc


def _candidate(data, manifest, assets):
    nodes = _nodes(data["nodes"])
    profile = manifest.get("element_profile", "linear")
    if profile not in ("linear", "straight_tet10"):
        raise PrepError("unsupported_mesh", "Unsupported standalone element profile.")
    dimension = max(block["dimension"] for block in data["blocks"])
    if dimension not in (2, 3):
        raise PrepError("unsupported_mesh", "Import physical triangle3 surfaces or tetra4 solids; standalone 1D models are not supported.")
    group_names = {(group["dimension"], group["tag"]): group["name"] for group in data["physical_groups"]}
    namespace = UUID(manifest["mesh_uuid"])
    part_cells, part_names, all_cells = defaultdict(list), {}, []
    group_elements, group_nodes = defaultdict(set), defaultdict(set)
    for block in data["blocks"]:
        dim, tag, physical = block["dimension"], block["entity_tag"], tuple(block["physical_tags"])
        identity = "physical:" + ",".join(map(str, physical)) if physical else f"entity:{tag}"
        owner = str(uuid5(namespace, f"{dim}:{identity}")) if dim == dimension else None
        if owner:
            part_names[owner] = (" / ".join(group_names[(dim, value)] for value in physical)
                                 if physical else f"Ungrouped entity {tag}")
        for identifier, connectivity in zip(block["ids"], block["connectivity"]):
            cell = MeshCell(identifier, dim, block["element_type"], block["element_name"], block["order"], tuple(connectivity), owner)
            all_cells.append(cell)
            if owner: part_cells[owner].append(identifier)
            for group in physical:
                group_nodes[(dim, group)].update(connectivity)
                if owner: group_elements[(dim, group)].add(identifier)
    # 4.1 can define a physical point through its node classification even when
    # no explicit point element was written. Keep that node group as well.
    entity_groups = {(entry["dimension"], entry["tag"]): entry["physical_tags"] for entry in data["entities"]}
    for identifier, entity in data["node_entities"].items():
        if entity[0] == 0:
            for group in entity_groups.get(tuple(entity), ()):
                group_nodes[(0, group)].add(int(identifier))
    physical_cells = [cell for cell in all_cells if cell.dimension == dimension]
    quadratic = profile == "straight_tet10"
    if quadratic and (dimension != 3 or any(cell.kind != "tetra10" for cell in physical_cells)):
        raise PrepError("unsupported_mesh", "The straight_tet10 profile requires only Tet10 physical solids; mixed families are not supported.")
    used = {identifier for cell in physical_cells for identifier in cell.node_ids}
    topology = [(cell.dimension, tuple(sorted(cell.node_ids))) for cell in all_cells]
    if len(topology) != len(set(topology)):
        raise PrepError("duplicate_elements", "Duplicate element connectivity is ambiguous; the whole import is rejected.")
    # Lower-dimensional records may annotate actual physical-cell boundaries;
    # they must not silently turn a mixed shell/solid or beam model into one body.
    if quadratic or all(cell.kind in ("triangle3", "tetra4") for cell in physical_cells):
        if quadratic:
            facets, edges, edge_midpoints = _quadratic_boundaries(physical_cells)
        else:
            facets = {tuple(sorted(face)) for cell in physical_cells for face in combinations(cell.node_ids, dimension)}
            edges = {tuple(sorted(edge)) for cell in physical_cells for edge in combinations(cell.node_ids, 2)}
        for cell in all_cells:
            valid = (set(cell.node_ids) <= used if cell.dimension == 0 else
                     tuple(sorted(cell.node_ids)) in edges if cell.dimension == 1 else
                     tuple(sorted(cell.node_ids)) in facets if cell.dimension == 2 else True)
            if quadratic and cell.dimension == 1 and valid:
                valid = len(cell.node_ids) == 3 and edge_midpoints.get(tuple(sorted(cell.node_ids[:2]))) == cell.node_ids[2]
            if quadratic and cell.dimension == 2 and valid:
                corners = cell.node_ids[:3]
                valid = all(edge_midpoints.get(tuple(sorted((corners[a], corners[b])))) == midpoint
                            for (a, b), midpoint in zip(((0, 1), (1, 2), (2, 0)), cell.node_ids[3:]))
            if cell.dimension < dimension and not valid:
                raise PrepError("mixed_dimension_mesh", "A lower-dimensional element is not a boundary of the adopted physical mesh.", {"element_id": cell.id})
    groups = []
    for (dim, tag), name in sorted(group_names.items()):
        kind = "element" if dim == dimension else "node"
        members = group_elements[(dim, tag)] if kind == "element" else group_nodes[(dim, tag)]
        if not members:
            raise PrepError("empty_physical_group", f"Physical group {dim}:{tag} ({name}) has no supported members.")
        if kind == "node" and not members <= used:
            raise PrepError("invalid_group", f"Physical group {dim}:{tag} includes nodes outside the physical mesh.")
        groups.append(MeshGroup(f"physical:{dim}:{tag}", f"[{dim}:{tag}] {name}", kind, tuple(sorted(members))))
    parts = tuple(MeshPart(key, dimension, index + 1, part_names[key], tuple(ids))
                  for index, (key, ids) in enumerate(part_cells.items()))
    limits = QualityLimits(minimum_tetrahedron=.5) if quadratic else QualityLimits()
    quality = _quality(nodes, all_cells, limits, straight_tet10=quadratic)
    lower_types = (8, 15) if quadratic else (1, 15)
    unsupported_lower = tuple(cell.id for cell in all_cells if cell.dimension < 2 and cell.element_type not in lower_types)
    quality = replace(quality, unsupported_ids=quality.unsupported_ids + unsupported_lower)
    counts = Counter((cell.dimension, cell.element_type, cell.element_name, cell.order,
                      "physical" if cell.dimension == dimension else "boundary_annotation",
                      cell.kind is not None and (quadratic or cell.order == 1) if cell.dimension >= 2 else cell.element_type in lower_types) for cell in all_cells)
    inventory = tuple(CellInventory(dim, typ, name, order, count, role, supported)
                      for (dim, typ, name, order, role, supported), count in sorted(counts.items()))
    return ImportedMeshCandidate(str(namespace), manifest["length_unit"], dimension, nodes, tuple(all_cells),
                                 parts, tuple(groups), inventory, quality, assets, data["format_version"])


def _quadratic_boundaries(cells):
    from .tet10_geometry import GMSH_EDGES
    shared, inverse, facets, edges = {}, {}, set(), set()
    corners = {node for cell in cells for node in cell.node_ids[:4]}
    for cell in cells:
        nodes, midsides = cell.node_ids, {}
        for (a, b), midpoint in zip(GMSH_EDGES, nodes[4:]):
            edge = tuple(sorted((nodes[a], nodes[b])))
            if (midpoint in corners or edge in shared and shared[edge] != midpoint
                    or midpoint in inverse and inverse[midpoint] != edge):
                raise PrepError("nonconforming_tet10", "Tet10 edges require one shared midpoint ID and distinct corner IDs.")
            shared[edge], inverse[midpoint], midsides[edge] = midpoint, edge, midpoint
            edges.add(tuple(sorted((*edge, midpoint))))
        for face in combinations(nodes[:4], 3):
            facets.add(tuple(sorted((*face, *(midsides[tuple(sorted(edge))] for edge in combinations(face, 2))))))
    return facets, edges, shared


def validate_imported_mesh(native):
    """Re-read immutable source bytes immediately before the existing command."""
    if (native.geometry_resource_uuid is not None or not isinstance(native.assets, tuple)
            or any(not isinstance(asset, AssetDigest) for asset in native.assets) or len(native.assets) != 2
            or {asset.kind for asset in native.assets} != {"msh", "metadata"}):
        raise PrepError("invalid_native_mesh", "Standalone mesh adoption requires its MSH and import manifest, with no CAD identity.")
    for asset in native.assets:
        if not isinstance(asset, AssetDigest) or _sha(asset.path) != asset.sha256:
            raise PrepError("candidate_changed", "A standalone mesh asset changed after review.")
    metadata = next(asset.path for asset in native.assets if asset.kind == "metadata")
    canonical = read_imported_mesh(metadata).to_native_mesh()
    if native != canonical:
        raise PrepError("invalid_native_mesh", "Mesh values or physical groups differ from the captured MSH.")
    return canonical
