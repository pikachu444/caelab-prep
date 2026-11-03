"""Read geometry evidence without creating mesh candidates or changing documents."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from .mesh_candidates import AssetDigest, _positive, _sha, _uuid
from ..cae_core.errors import PrepError


@dataclass(frozen=True)
class GeometryInspection:
    geometry_resource_uuid: str
    geometry_revision: int
    length_unit: str
    assets: tuple[AssetDigest, ...]
    _payload_json: str

    def to_dict(self):
        """Return a detached copy; callers cannot change the inspected evidence."""
        return json.loads(self._payload_json)

    def verify_assets(self):
        for asset in self.assets:
            if _sha(asset.path) != asset.sha256:
                raise PrepError("geometry_inspection_changed", "Geometry inspection assets changed after reading.",
                                {"kind": asset.kind, "path": asset.path})


def _invalid(message):
    raise PrepError("invalid_geometry_inspection", message)


def _vector(value, count):
    if (not isinstance(value, list) or len(value) != count
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        _invalid("Expected finite geometry coordinates or parameter bounds.")


def _array(value):
    if not isinstance(value, list):
        _invalid("Geometry collections must be JSON arrays.")
    return value


def _rows(value):
    rows = _array(value)
    if any(not isinstance(row, dict) for row in rows):
        _invalid("Geometry records must be JSON objects.")
    return rows


def _entities(rows, *, persistent):
    tags, identities = {}, set()
    for row in _rows(rows):
        tag = _positive(row["backend_tag"], "Geometry backend tag")
        if tag in tags:
            _invalid("Geometry entity tags must be unique within a dimension.")
        tags[tag] = row
        if persistent:
            identity = _uuid(row["uuid"])
            if identity in identities:
                _invalid("Geometry entity UUIDs must be unique.")
            identities.add(identity)
        _vector(row["bbox"], 6)
        if not isinstance(row.get("geometry_type", ""), str):
            _invalid("Geometry entity types must be explicit strings.")
    return tags, identities


def _topology(data):
    surfaces, surface_ids = _entities(data["surfaces"], persistent=True)
    volumes, volume_ids = _entities(data["volumes"], persistent=True)
    curves, _ = _entities(data["curves"], persistent=False)
    if not surfaces or surface_ids & volume_ids:
        _invalid("An inspection needs surfaces and unambiguous entity identities.")
    uses = set()
    loop_uses = set()
    for surface in surfaces.values():
        identity = surface["uuid"]
        _vector(surface["center"], 3)
        for use in _rows(surface["orientation_by_volume"]):
            if use["volume_uuid"] not in volume_ids or type(use["sign"]) is not int or use["sign"] not in (-1, 1):
                _invalid("Surface volume-use references and raw signs must resolve.")
            pair = identity, use["volume_uuid"]
            if pair in uses:
                _invalid("Duplicate surface volume uses are ambiguous.")
            uses.add(pair)
        for loop in _rows(surface["curve_loops"]):
            _positive(loop["backend_tag"], "Curve loop tag")
            for tag in _array(loop["curve_tags"]):
                if type(tag) is not int or abs(tag) not in curves:
                    _invalid("Every curve-loop reference must resolve in this inspection.")
                loop_uses.add((identity, abs(tag)))
        if surface["normal_basis"] != "gmsh_face_oriented_no_volume_sign" or surface["sampling_status"] != "unverified":
            _invalid("Raw face samples cannot claim material-outward or feature verification.")
        for sample in _rows(surface["samples"]):
            _vector(sample["uv"], 2)
            _vector(sample["xyz"], 3)
            _vector(sample["face_normal"], 3)
            if type(sample["trim_count"]) is not int or sample["trim_count"] not in (0, 1):
                _invalid("A single raw sample needs its explicit trim membership count.")
    boundaries = set()
    for volume in volumes.values():
        members = _array(volume["surface_uuids"])
        if not members or len(set(members)) != len(members):
            _invalid("Each volume needs a nonempty boundary with no duplicate surface references.")
        for identity in members:
            if identity not in surface_ids:
                _invalid("Every volume boundary reference must resolve.")
            boundaries.add((identity, volume["uuid"]))
    if boundaries != uses:
        _invalid("Volume boundaries and surface volume-use references disagree.")
    adjacencies = set()
    for tag, curve in curves.items():
        for identity in _array(curve["adjacent_surface_uuids"]):
            if identity not in surface_ids:
                _invalid("Every curve adjacency must resolve to an inspected surface.")
            adjacencies.add((identity, tag))
        for endpoint in _rows(curve["endpoints"]):
            _positive(endpoint["backend_tag"], "Curve endpoint tag")
            _vector(endpoint["xyz"], 3)
    if adjacencies != loop_uses:
        _invalid("Curve adjacency and surface loops disagree.")


def read_geometry_inspection(source) -> GeometryInspection:
    """Validate metadata and stable assets; raw observations remain unverified.

    Curve/loop tags are local to this inspection. UUIDs and revisions do not
    imply matching topology across separate imports. No MSH or FE model exists.
    """
    try:
        if isinstance(source, dict):
            data = json.loads(json.dumps(source, allow_nan=False))
            metadata = Path(data["assets"]["metadata"]).expanduser().resolve()
            metadata_bytes = metadata.read_bytes()
            if json.loads(metadata_bytes) != data:
                _invalid("Worker result differs from its persisted geometry inspection.")
        else:
            metadata = Path(source).expanduser().resolve()
            metadata_bytes = metadata.read_bytes()
            data = json.loads(metadata_bytes)
        payload = json.dumps(data, allow_nan=False)
        if (type(data["schema_version"]) is not int or data["schema_version"] != 1
                or data["source_kind"] != "cad_geometry_inspection" or data["backend"]["name"] != "gmsh"
                or set(data["assets"]) != {"xao", "metadata"}
                or {"mesh", "mesh_uuid", "mesh_revision"} & data.keys()):
            _invalid("Expected geometry-only inspection schema version 1.")
        if Path(data["assets"]["metadata"]).expanduser().resolve() != metadata:
            _invalid("Metadata path does not identify the file being read.")
        paths = {"source": Path(data["source"]["captured_path"]).expanduser().resolve(),
                 "xao": Path(data["assets"]["xao"]).expanduser().resolve(), "metadata": metadata}
        if len(set(paths.values())) != len(paths):
            _invalid("Source, XAO and metadata assets must be distinct files.")
        assets = tuple(AssetDigest(kind, str(path), _sha(path)) for kind, path in paths.items())
        if assets[2].sha256 != hashlib.sha256(metadata_bytes).hexdigest():
            _invalid("Geometry metadata changed while it was being read.")
        if assets[0].sha256 != data["source"]["sha256"]:
            _invalid("Captured geometry does not match the recorded source hash.")
        identity = _uuid(data["geometry_resource_uuid"])
        revision = _positive(data["geometry_revision"], "Geometry revision")
        if data["length_unit"] not in ("mm", "unknown"):
            _invalid("Unsupported inspected geometry length unit.")
        if type(data["sdk_error_count"]) is not int or data["sdk_error_count"] != 0:
            _invalid("Geometry inspection contains native SDK errors.")
        _topology(data)
        result = GeometryInspection(identity, revision, data["length_unit"], assets, payload)
        result.verify_assets()
        return result
    except PrepError:
        raise
    except (KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
        raise PrepError("invalid_geometry_inspection", f"Cannot read geometry inspection: {exc}") from exc
