"""Validated Gmsh candidates; no Qt, solver or native SDK imports in the host.

MSH parsing stays in the official SDK in an isolated process. Its complete cell
inventory is checked against the existing worker's JSON projection. Tri3/tet4
mean-ratio metrics follow the explicit P7a/C contract in execution-stages.md;
signed tetrahedral volume is checked separately and never silently repaired.
Gmsh API: https://gmsh.info/doc/texinfo/#Namespace-gmsh_002fmodel_002fmesh
Metric background: https://github.com/sandialabs/verdict (SAND2007-2853).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from ..cae_core.errors import PrepError


@dataclass(frozen=True)
class QualityLimits:
    minimum_triangle: float = 0.1
    minimum_tetrahedron: float = 0.1
    relative_degeneracy: float = 1e-12

    def __post_init__(self):
        for value in (self.minimum_triangle, self.minimum_tetrahedron):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise PrepError("invalid_quality_limit", "Quality thresholds must be finite and between 0 and 1.")
        if (type(self.relative_degeneracy) not in (int, float)
                or not math.isfinite(self.relative_degeneracy) or not 0 < self.relative_degeneracy < 1):
            raise PrepError("invalid_quality_limit", "A positive relative degeneracy tolerance below 1 is required.")


@dataclass(frozen=True)
class MeshNode:
    id: int
    xyz: tuple[float, float, float]


@dataclass(frozen=True)
class MeshCell:
    id: int
    dimension: int
    element_type: int
    element_name: str
    order: int
    node_ids: tuple[int, ...]
    part_uuid: str | None

    @property
    def kind(self):
        return {(2, 2, 1, 3): "triangle3", (3, 4, 1, 4): "tetra4"}.get(
            (self.dimension, self.element_type, self.order, len(self.node_ids)))


@dataclass(frozen=True)
class MeshPart:
    uuid: str
    dimension: int
    backend_tag: int
    name: str
    element_ids: tuple[int, ...]
    boundary_uuids: tuple[str, ...] = ()
    volume_orientations: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class CellInventory:
    dimension: int
    element_type: int
    element_name: str
    order: int
    count: int
    role: str
    supported: bool


@dataclass(frozen=True)
class CellQuality:
    element_id: int
    kind: str
    q: float
    signed_measure: float
    problem: str | None


@dataclass(frozen=True)
class QualityReport:
    limits: QualityLimits
    cells: tuple[CellQuality, ...]
    unsupported_ids: tuple[int, ...]

    @property
    def passed(self):
        return not self.unsupported_ids and all(item.problem is None for item in self.cells)

    @property
    def problem_ids(self):
        return tuple(item.element_id for item in self.cells if item.problem) + self.unsupported_ids

    def minimum(self, kind):
        return min((item.q for item in self.cells if item.kind == kind), default=None)


@dataclass(frozen=True)
class AssetDigest:
    kind: str
    path: str
    sha256: str


@dataclass(frozen=True)
class NativeMesh:
    """Solver-neutral physical cells, with the complete source inventory.

    omitted_boundary_cells counts every excluded lower-dimensional cell,
    including geometric edges/vertices. All source nodes are retained and any
    node unused by the selected physical elements is explicitly listed.
    """
    nodes: tuple[MeshNode, ...]
    elements: tuple[MeshCell, ...]
    parts: tuple[MeshPart, ...]
    length_unit: str
    geometry_resource_uuid: str
    mesh_uuid: str
    dimension: int
    inventory: tuple[CellInventory, ...]
    omitted_boundary_cells: int
    unused_node_ids: tuple[int, ...]
    assets: tuple[AssetDigest, ...]


@dataclass(frozen=True)
class MeshCandidate:
    geometry_resource_uuid: str
    geometry_revision: int
    mesh_uuid: str
    mesh_revision: int
    length_unit: str
    dimension: int
    nodes: tuple[MeshNode, ...]
    cells: tuple[MeshCell, ...]
    parts: tuple[MeshPart, ...]
    inventory: tuple[CellInventory, ...]
    quality: QualityReport
    assets: tuple[AssetDigest, ...]
    backend_version: str

    def to_native_mesh(self, dimension: int | None = None, *, length_unit: str | None = None) -> NativeMesh:
        dimension = self.dimension if dimension is None else dimension
        if type(dimension) is not int or dimension != self.dimension:
            raise PrepError("mesh_dimension", "Use the candidate's generated dimension; solid boundary facets are not shell elements.")
        unit = self.length_unit if length_unit is None else length_unit
        if unit not in ("mm", "m", "cm"):
            raise PrepError("unknown_length_unit", "Assign mm, cm or m explicitly before adopting this mesh.")
        if self.length_unit != "unknown" and unit != self.length_unit:
            raise PrepError("unit_mismatch", "Changing the declared unit requires coordinate conversion, not relabeling.")
        if not self.quality.passed:
            raise PrepError("mesh_quality", "The mesh has unsupported, inverted, degenerate or poor-quality elements.",
                            {"element_ids": list(self.quality.problem_ids),
                             "unsupported_ids": list(self.quality.unsupported_ids)})
        if self.dimension == 3 and any(item.role == "shell" for item in self.inventory):
            raise PrepError("mixed_dimension_mesh", "Free shell surfaces coexist with solids; mixed-dimensional adoption needs an explicit part policy.")
        elements = tuple(cell for cell in self.cells if cell.dimension == dimension)
        if not elements:
            raise PrepError("empty_mesh", "The candidate has no elements in its generated dimension.")
        used = {identifier for cell in elements for identifier in cell.node_ids}
        return NativeMesh(self.nodes, elements, tuple(part for part in self.parts if part.dimension == dimension),
                          unit, self.geometry_resource_uuid, self.mesh_uuid, dimension, self.inventory,
                          sum(cell.dimension < dimension for cell in self.cells),
                          tuple(node.id for node in self.nodes if node.id not in used), self.assets)


def _positive(value, label):
    if type(value) is not int or value <= 0:
        raise PrepError("invalid_candidate", f"{label} must be a positive integer.")
    return value


def _uuid(value):
    if not isinstance(value, str):
        raise PrepError("invalid_candidate", "Geometry and mesh identities must be UUID strings.")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise PrepError("invalid_candidate", "Malformed geometry or mesh UUID.") from exc


def _sha(path):
    try:
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        raise PrepError("candidate_asset", f"Cannot read candidate asset: {path}") from exc


def _nodes(data):
    ids, coordinates = data["ids"], data["coordinates"]
    if len(ids) != len(coordinates) or not ids:
        raise PrepError("invalid_candidate", "Node IDs and coordinates must have equal, nonzero length.")
    result = []
    for identifier, xyz in zip(ids, coordinates):
        _positive(identifier, "Node ID")
        if len(xyz) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in xyz):
            raise PrepError("invalid_candidate", "Every node needs three finite coordinates.")
        result.append(MeshNode(identifier, tuple(float(value) for value in xyz)))
    if len({node.id for node in result}) != len(result):
        raise PrepError("invalid_candidate", "Duplicate node IDs.")
    return tuple(result)


def triangle_quality(points):
    """Return q, unsigned area, and area divided by the longest edge squared."""
    edges = [_sub(points[j], points[i]) for i, j in ((0, 1), (1, 2), (2, 0))]
    scale = max((math.hypot(*edge) for edge in edges), default=0)
    if not scale:
        return 0.0, 0.0, 0.0
    a, b = (_scale(_sub(points[i], points[0]), scale) for i in (1, 2))
    area_scaled = math.hypot(*_cross(a, b)) / 2
    denominator = sum(sum(v * v for v in _scale(edge, scale)) for edge in edges)
    return min(1.0, 4 * math.sqrt(3) * area_scaled / denominator), area_scaled * scale * scale, area_scaled


def tetrahedron_quality(points):
    """Return mean ratio, signed volume, and scale-normalized signed volume.

    q uses |V| by definition; callers must reject V <= 0 independently.
    """
    edges = [_sub(points[j], points[i]) for i in range(4) for j in range(i + 1, 4)]
    scale = max((math.hypot(*edge) for edge in edges), default=0)
    if not scale:
        return 0.0, 0.0, 0.0
    a, b, c = (_scale(_sub(points[i], points[0]), scale) for i in (1, 2, 3))
    volume_scaled = sum(x * y for x, y in zip(a, _cross(b, c))) / 6
    denominator = sum(sum(v * v for v in _scale(edge, scale)) for edge in edges)
    q = min(1.0, 12 * (3 * abs(volume_scaled)) ** (2 / 3) / denominator)
    return q, volume_scaled * scale * scale * scale, volume_scaled


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _scale(vector, length):
    return tuple(value / length for value in vector)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _quality(nodes, cells, limits):
    coordinates = {node.id: node.xyz for node in nodes}
    results, unsupported = [], []
    for cell in cells:
        if cell.dimension < 2:
            continue  # Explicit geometric edge/vertex inventory, not physical cells.
        if cell.kind is None:
            unsupported.append(cell.id)
            continue
        points = [coordinates[identifier] for identifier in cell.node_ids]
        q, measure, normalized = triangle_quality(points) if cell.kind == "triangle3" else tetrahedron_quality(points)
        threshold = limits.minimum_triangle if cell.kind == "triangle3" else limits.minimum_tetrahedron
        problem = None
        if not all(math.isfinite(v) for v in (q, measure, normalized)):
            problem = "nonfinite_geometry"
        elif abs(normalized) <= limits.relative_degeneracy:
            problem = "degenerate"
        elif cell.kind == "tetra4" and normalized < 0:
            problem = "inverted"
        elif q < threshold:
            problem = "below_quality_limit"
        results.append(CellQuality(cell.id, cell.kind, q, measure, problem))
    return QualityReport(limits, tuple(results), tuple(unsupported))


def _inspect_msh(path):
    """Only the child process calls this; all MSH versions stay SDK-owned."""
    import gmsh
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(path))
        ids, xyz, _ = gmsh.model.mesh.getNodes()
        blocks = []
        for dimension, tag in gmsh.model.getEntities():
            types, ids_by_type, nodes_by_type = gmsh.model.mesh.getElements(dimension, tag)
            for typ, identifiers, connectivity in zip(types, ids_by_type, nodes_by_type):
                name, dim, order, count, _, _ = gmsh.model.mesh.getElementProperties(int(typ))
                flat = [int(value) for value in connectivity]
                blocks.append({"dimension": int(dim), "backend_tag": int(tag), "element_type": int(typ),
                               "element_name": name, "order": int(order), "nodes_per_element": int(count),
                               "ids": [int(value) for value in identifiers],
                               "connectivity": [flat[i:i + count] for i in range(0, len(flat), count)]})
        coordinates = [float(value) for value in xyz]
        groups = [{"dimension": int(dim), "name": gmsh.model.getPhysicalName(dim, tag),
                   "entities": [int(value) for value in gmsh.model.getEntitiesForPhysicalGroup(dim, tag)]}
                  for dim, tag in gmsh.model.getPhysicalGroups()]
        return {"nodes": {"ids": [int(value) for value in ids],
                          "coordinates": [coordinates[i:i + 3] for i in range(0, len(coordinates), 3)]},
                "element_blocks": blocks, "physical_groups": groups}
    finally:
        gmsh.finalize()


def _read_msh(path, timeout):
    environment = os.environ.copy()
    package_parent = str(Path(__file__).resolve().parents[2])
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [package_parent, environment.get("PYTHONPATH", "")]))
    try:
        process = subprocess.run([sys.executable, "-m", __name__, str(path)], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=timeout, env=environment)
    except subprocess.TimeoutExpired as exc:
        raise PrepError("candidate_timeout", "Independent MSH inspection timed out.") from exc
    try:
        response = json.loads(process.stdout)
    except ValueError as exc:
        raise PrepError("candidate_inspection", "Independent MSH inspection failed.",
                        {"exit_code": process.returncode, "stderr": process.stderr[-2000:]}) from exc
    if process.returncode or not response.get("ok"):
        raise PrepError("candidate_inspection", response.get("error", "Independent MSH inspection failed."),
                        {"exit_code": process.returncode})
    return response["mesh"]


def read_mesh_candidate(source: str | os.PathLike[str] | dict, *,
                        quality_limits: QualityLimits | None = None,
                        inspection_timeout: float = 60.0) -> MeshCandidate:
    """Read a worker result dict or its metadata.json; verify every MSH cell.

    The candidate is immutable and does not change any document. Invalid assets
    raise PrepError; poor/unsupported mesh quality remains inspectable and blocks
    to_native_mesh. Unknown CAD units remain unknown until explicit adoption.
    """
    if type(inspection_timeout) not in (int, float) or not math.isfinite(inspection_timeout) or inspection_timeout <= 0:
        raise PrepError("invalid_request", "Inspection timeout must be finite and positive.")
    limits = QualityLimits() if quality_limits is None else quality_limits
    if not isinstance(limits, QualityLimits):
        raise PrepError("invalid_request", "quality_limits must be QualityLimits.")
    try:
        if isinstance(source, dict):
            data = json.loads(json.dumps(source, allow_nan=False))
            metadata = Path(data["assets"]["metadata"]).resolve()
            if json.loads(metadata.read_text(encoding="utf-8")) != data:
                raise PrepError("candidate_mismatch", "Worker result differs from its persisted metadata.")
        else:
            metadata = Path(source).expanduser().resolve()
            data = json.loads(metadata.read_text(encoding="utf-8"))
        if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["backend"]["name"] != "gmsh":
            raise PrepError("candidate_version", "Expected Gmsh candidate schema version 1.")
        paths = {name: Path(data["assets"][name]).expanduser().resolve() for name in ("msh", "xao")}
        paths["metadata"] = metadata
        paths["source"] = Path(data["source"]["captured_path"]).expanduser().resolve()
        assets = tuple(AssetDigest(name, str(path), _sha(path)) for name, path in paths.items())
        if next(asset.sha256 for asset in assets if asset.kind == "source") != data["source"]["sha256"]:
            raise PrepError("candidate_mismatch", "Captured CAD content no longer matches its source hash.")
        identity = [_uuid(data[key]) for key in ("geometry_resource_uuid", "mesh_uuid")]
        revisions = [_positive(data[key], key) for key in ("geometry_revision", "mesh_revision")]
        unit = data["length_unit"]
        if unit not in ("mm", "unknown"):
            raise PrepError("invalid_candidate", "Unsupported candidate length-unit declaration.")
        nodes = _nodes(data["mesh"]["nodes"])
        independent = _read_msh(paths["msh"], inspection_timeout)
        observed = _nodes(independent["nodes"])
        if {node.id: node.xyz for node in nodes} != {node.id: node.xyz for node in observed}:
            raise PrepError("candidate_mismatch", "MSH node coordinates or IDs differ from metadata.")
        parts, by_entity, by_uuid = [], {}, {}
        for dimension, entries in ((2, data["surfaces"]), (3, data["volumes"])):
            for entry in entries:
                identifier = _uuid(entry["uuid"])
                tag = _positive(entry["backend_tag"], "Geometry tag")
                members = tuple(_positive(i, "Element ID") for i in entry["facet_ids" if dimension == 2 else "element_ids"])
                boundaries = tuple(_uuid(value) for value in entry.get("surface_uuids", ()))
                orientations = tuple((_uuid(item["volume_uuid"]), item["sign"]) for item in entry.get("orientation_by_volume", ()))
                if any(type(sign) is not int or sign not in (-1, 1) for _, sign in orientations):
                    raise PrepError("invalid_candidate", "Surface orientation signs must be -1 or 1.")
                part = MeshPart(identifier, dimension, tag, str(entry["physical_group_name"]), members, boundaries, orientations)
                if identifier in by_uuid or (dimension, tag) in by_entity or len(set(members)) != len(members):
                    raise PrepError("invalid_candidate", "Duplicate geometry identities or element memberships.")
                parts.append(part); by_uuid[identifier] = part; by_entity[(dimension, tag)] = part
        for part in parts:
            if any(value not in by_uuid or by_uuid[value].dimension != 2 for value in part.boundary_uuids):
                raise PrepError("invalid_candidate", "Volume references an unknown boundary surface.")
            if any(value not in by_uuid or by_uuid[value].dimension != 3 for value, _ in part.volume_orientations):
                raise PrepError("invalid_candidate", "Surface references an unknown volume.")
            if any(part.uuid not in by_uuid[value].boundary_uuids for value, _ in part.volume_orientations):
                raise PrepError("invalid_candidate", "Surface and volume adjacency are inconsistent.")
            if any(part.uuid not in {volume for volume, _ in by_uuid[value].volume_orientations}
                   for value in part.boundary_uuids):
                raise PrepError("invalid_candidate", "Volume and surface adjacency are inconsistent.")
        groups = {(group["dimension"], group["name"]): tuple(group["entities"])
                  for group in independent["physical_groups"]}
        anchor_dim = 3 if data["volumes"] else 2
        anchor_name = f"caelab:geometry:{identity[0]}:r{revisions[0]}:unit:{unit}"
        if set(groups.get((anchor_dim, anchor_name), ())) != {part.backend_tag for part in parts if part.dimension == anchor_dim}:
            raise PrepError("candidate_mismatch", "MSH geometry identity or unit differs from metadata.")
        for part in parts:
            expected_name = f"caelab:{'surface' if part.dimension == 2 else 'volume'}:{part.uuid}"
            if part.name != expected_name or groups.get((part.dimension, expected_name)) != (part.backend_tag,):
                raise PrepError("candidate_mismatch", "MSH entity identity differs from metadata.")
        node_ids = {node.id for node in nodes}
        metadata_cells = {}
        for block in data["mesh"]["element_blocks"]:
            part = by_uuid.get(block["entity_uuid"])
            if part is None or part.dimension != block["dimension"]:
                raise PrepError("invalid_candidate", "Element block has an invalid owning geometry entity.")
            for cell in _cells(block, part.uuid, node_ids):
                if cell.id in metadata_cells:
                    raise PrepError("invalid_candidate", "Duplicate element IDs in metadata.")
                metadata_cells[cell.id] = cell
        cells, seen = [], set()
        for block in independent["element_blocks"]:
            dimension = block["dimension"]
            part = by_entity.get((dimension, block["backend_tag"]))
            if dimension >= 2 and part is None:
                raise PrepError("candidate_mismatch", "MSH has an unrecorded surface or volume entity.")
            for cell in _cells(block, part.uuid if part else None, node_ids):
                if cell.id in seen:
                    raise PrepError("candidate_mismatch", "MSH contains duplicate element IDs.")
                seen.add(cell.id); cells.append(cell)
                if dimension >= 2 and metadata_cells.pop(cell.id, None) != cell:
                    raise PrepError("candidate_mismatch", "MSH element inventory or connectivity differs from metadata.", {"element_id": cell.id})
        if metadata_cells:
            raise PrepError("candidate_mismatch", "Metadata elements are absent from MSH.")
        physical = [cell for cell in cells if cell.dimension >= 2]
        if not physical:
            raise PrepError("empty_mesh", "The candidate contains no surface or volume elements.")
        topology = [(cell.dimension, tuple(sorted(cell.node_ids))) for cell in physical]
        if len(set(topology)) != len(topology):
            raise PrepError("invalid_candidate", "Duplicate physical element connectivity.")
        dimension = max(cell.dimension for cell in physical)
        for part in parts:
            actual = {cell.id for cell in physical if cell.part_uuid == part.uuid}
            if actual != set(part.element_ids):
                raise PrepError("candidate_mismatch", "Entity element membership differs from the complete mesh inventory.")
        counts = data["counts"]
        expected = {"nodes": len(nodes), "elements": sum(cell.dimension == dimension for cell in cells),
                    "surface_facets": sum(cell.dimension == 2 for cell in cells),
                    "surfaces": sum(part.dimension == 2 for part in parts), "volumes": sum(part.dimension == 3 for part in parts)}
        if any(type(counts[key]) is not int or counts[key] != value for key, value in expected.items()):
            raise PrepError("candidate_mismatch", "Declared candidate counts do not match the full mesh.")
        inventory = []
        def role_for(cell):
            boundary = (dimension == 3 and cell.dimension == 2
                        and by_uuid[cell.part_uuid].volume_orientations)
            return {0: "geometry_vertex", 1: "geometry_edge", 2: "boundary_facet" if boundary else "shell", 3: "solid"}[cell.dimension]
        counter = Counter((cell.dimension, cell.element_type, cell.element_name, cell.order,
                           cell.kind is not None, role_for(cell)) for cell in cells)
        for (dim, typ, name, order, supported, role), count in sorted(counter.items()):
            inventory.append(CellInventory(dim, typ, name, order, count, role, supported if dim >= 2 else True))
        # Detect replacement during inspection rather than accepting mixed assets.
        if any(_sha(asset.path) != asset.sha256 for asset in assets):
            raise PrepError("candidate_changed", "Candidate assets changed while being inspected.")
        return MeshCandidate(identity[0], revisions[0], identity[1], revisions[1], unit, dimension,
                             nodes, tuple(cells), tuple(parts), tuple(inventory), _quality(nodes, cells, limits),
                             assets, str(data["backend"]["version"]))
    except PrepError:
        raise
    except (KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
        raise PrepError("invalid_candidate", "Malformed candidate metadata or mesh data.", {"reason": str(exc)}) from exc


def validate_native_mesh(native_mesh: NativeMesh) -> NativeMesh:
    """Re-admit an untrusted public value immediately before document adoption.

    This is a Gmsh-candidate boundary, not a general hand-authored mesh importer.
    Original candidate assets are required. Reconstructing the neutral value
    from the hashed metadata and actual MSH verifies IDs, geometry, ownership,
    full inventory and default quality limits, including forged frozen values.
    A caller may request stricter limits earlier, but cannot lower the default
    q >= 0.1 admission baseline by constructing a NativeMesh directly.
    """
    if not isinstance(native_mesh, NativeMesh):
        raise PrepError("invalid_native_mesh", "Expected a verified Gmsh NativeMesh candidate.")
    assets = native_mesh.assets
    if (not isinstance(assets, tuple) or any(not isinstance(asset, AssetDigest) for asset in assets)
            or len(assets) != 4 or {asset.kind for asset in assets} != {"source", "metadata", "msh", "xao"}):
        raise PrepError("invalid_native_mesh", "The original candidate assets are required for adoption.")
    for asset in assets:
        if not isinstance(asset.path, str) or not isinstance(asset.sha256, str) or _sha(asset.path) != asset.sha256:
            raise PrepError("candidate_changed", "A candidate asset changed after validation.", {"asset": asset.kind})
    metadata = next(asset.path for asset in assets if asset.kind == "metadata")
    canonical = read_mesh_candidate(metadata).to_native_mesh(length_unit=native_mesh.length_unit)
    if native_mesh != canonical:
        raise PrepError("invalid_native_mesh", "Native mesh values differ from the verified candidate assets.")
    return canonical


def _cells(block, owner, node_ids):
    dimension = block["dimension"]
    if type(dimension) is not int or dimension not in (0, 1, 2, 3):
        raise PrepError("invalid_candidate", "Unsupported element dimension.")
    typ = _positive(block["element_type"], "Gmsh element type")
    count = _positive(block["nodes_per_element"], "Nodes per element")
    order = block["order"]
    if type(order) is not int or order < 0 or len(block["ids"]) != len(block["connectivity"]):
        raise PrepError("invalid_candidate", "Malformed element block.")
    for identifier, connectivity in zip(block["ids"], block["connectivity"]):
        _positive(identifier, "Element ID")
        conn = tuple(_positive(value, "Node reference") for value in connectivity)
        if len(conn) != count or len(set(conn)) != count or not set(conn) <= node_ids:
            raise PrepError("invalid_candidate", "Missing, duplicate or invalid element node references.", {"element_id": identifier})
        yield MeshCell(identifier, dimension, typ, str(block["element_name"]), order, conn, owner)


if __name__ == "__main__":
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    try:
        response = {"ok": True, "mesh": _inspect_msh(Path(sys.argv[1]))}
    except Exception as error:
        response = {"ok": False, "error": str(error)}
    protocol.write(json.dumps(response, allow_nan=False) + "\n"); protocol.flush()
    raise SystemExit(0 if response["ok"] else 1)
