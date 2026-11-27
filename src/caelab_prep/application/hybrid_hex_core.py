"""Generate a verified, solver-neutral Cartesian core and tetrahedral annulus."""

from collections import Counter
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from uuid import uuid4, uuid5

from ..adapters.gmsh_backend import cad_coordinate_length_unit
from ..adapters.hybrid_hex_core_geometry import audit_faces, require
from ..adapters.msh_worker import read_msh
from ..cae_core.errors import PrepError
from .mesh_candidates import AssetDigest, CellInventory, MeshCell, MeshNode, MeshPart, NativeMesh, _sha


@dataclass(frozen=True)
class HybridHexCoreCandidate:
    native: NativeMesh
    mesh_path: Path
    report_path: Path
    quality: dict
    face_audit: dict
    core_audit: dict
    cad_volume: float
    mesh_volume: float
    backend_version: str
    fallback_reason: str | None

    def to_native_mesh(self, *, length_unit=None):
        return _verified_native(self.native, length_unit)


def _verified_native(native, length_unit):
    if length_unit is not None and length_unit != native.length_unit:
        raise PrepError("unit_mismatch", "The candidate's coordinate unit cannot be changed by relabeling.")
    if any(not Path(asset.path).is_file() or _sha(Path(asset.path)) != asset.sha256 for asset in native.assets):
        raise PrepError("candidate_changed", "A reviewed hybrid mesh asset changed.")
    return native


def _run_worker(source, stage, request, cancel_event, timeout):
    if cancel_event is not None and cancel_event.is_set():
        raise PrepError("cancelled", "Hybrid meshing was cancelled.")
    settings = stage / "request.json"
    settings.write_text(json.dumps(request), encoding="utf-8")
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (src, env.get("PYTHONPATH"))))
    deadline = time.monotonic() + timeout
    command = [sys.executable, "-B", "-m", "caelab_prep.adapters.hybrid_hex_core_worker",
               str(source), str(stage), str(settings)]
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env) as process:
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise PrepError("cancelled", "Hybrid meshing was cancelled.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PrepError("mesh_timeout", "Hybrid meshing exceeded its worker time limit.")
                try:
                    _, stderr = process.communicate(timeout=min(.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    try:
        report = json.loads((stage / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PrepError("hybrid_worker", "Hybrid worker did not produce a readable report.",
                        {"exit_code": process.returncode, "stderr": stderr[-2000:].decode("utf-8", "replace")}) from None
    if process.returncode or not report["ok"]:
        raise PrepError("hybrid_hex_core", report.get("error", "Hybrid worker rejected the mesh."))
    return report


def _check_export(output, report, *, assembly):
    """Tie the neutral representation to the published MSH records."""
    try:
        raw = read_msh(output)
    except (OSError, ValueError, OverflowError) as error:
        raise PrepError("hybrid_mesh_output", str(error)) from error
    require(raw["format_version"] == "4.1" and report["sdk_reopen_verified"],
            "Expected an SDK-verified MSH 4.1 artifact.")
    nodes = {i: tuple(xyz) for i, xyz in zip(raw["nodes"]["ids"], raw["nodes"]["coordinates"])}
    original = {i: tuple(xyz) for i, xyz in report.pop("nodes")}
    require(nodes.keys() == original.keys() and all(
        all(abs(a-b) <= 8*math.ulp(b) for a, b in zip(point, original[i])) for i, point in nodes.items()),
        "MSH round-trip changed node IDs or coordinates.")
    if assembly:
        inventory = report.pop("blocks")
        expected_skin = {int(face): Counter(map(tuple, surface.pop("triangles")))
                         for face, surface in report["surfaces"].items()}
        owners = {int(face): surface["owners"] for face, surface in report["surfaces"].items()}
        parts = {int(solid) for solid in report["parts"]}
        mapping = report["preparation"]["source_volume_map"]
        require({entry["backend_tag"] for entry in mapping} == parts and
                len({entry["source_backend_tag"] for entry in mapping}) == len(mapping) == len(parts),
                "Assembly source-to-mesh solid ownership must be one to one.")
        for entry in mapping:
            report["parts"][str(entry["backend_tag"])]["source_backend_tag"] = entry["source_backend_tag"]
        for face, surface in report["surfaces"].items():
            surface["triangle_count"] = sum(expected_skin[int(face)].values())
        report.pop("mesh_path")
    else:
        inventory = [[1, *cell] for cell in report.pop("cells")]
        expected_skin = {int(face): Counter(map(tuple, triangles))
                         for face, triangles in report.pop("skin_by_face").items()}
        owners = dict.fromkeys(expected_skin, [1])
        parts = {1}
    expected = {i: (solid, family, tuple(connectivity)) for solid, family, ids, elements in inventory
                for i, connectivity in zip(ids, elements)}
    observed = {}
    observed_skin = {}
    by_family = {}
    by_part = {}
    solid_groups = {}
    groups = {(group["dimension"], group["tag"]): group["name"] for group in raw["physical_groups"]}
    cad_names = {solid: f"CAD solid {solid}" if assembly else "CAD solid" for solid in parts}
    for block in raw["blocks"]:
        dim, family, conn = block["dimension"], block["element_type"], block["connectivity"]
        if dim == 3:
            solid, tags = block["entity_tag"], block["physical_tags"]
            require(solid in cad_names and len(tags) == 1 and groups.get((3, tags[0])) == cad_names[solid],
                    "MSH round-trip changed the solid owner.")
            require(solid_groups.setdefault(solid, tags[0]) == tags[0], "A solid has inconsistent physical groups.")
            observed.update({i: (solid, family, tuple(element)) for i, element in zip(block["ids"], conn)})
            by_family.setdefault(family, []).extend(map(tuple, conn))
            by_part.setdefault(solid, {}).setdefault(family, []).extend(map(tuple, conn))
        elif dim == 2 and family == 2:
            observed_skin[block["entity_tag"]] = Counter(map(tuple, conn))
        else:
            raise PrepError("hybrid_mesh_output", f"Unexpected MSH family {family} of dimension {dim}.")
    require(expected == observed and expected_skin == observed_skin,
            "MSH round-trip changed cell connectivity or CAD skin ownership.")
    require(solid_groups.keys() == parts and len(set(solid_groups.values())) == len(parts),
            "An assembly physical group owns more than one solid or is missing a solid.")
    skin = [triangle for face, facets in observed_skin.items() if len(owners[face]) == 1
            for triangle in facets.elements()]
    require(audit_faces(nodes, by_family, skin) == report["face_audit"], "MSH round-trip failed face audit.")
    if assembly:
        for solid, families in by_part.items():
            skin = [triangle if owners[face][0] == solid else triangle[::-1]
                    for face, facets in observed_skin.items() if solid in owners[face]
                    for triangle in facets.elements()]
            used = {identifier for elements in families.values() for cell in elements for identifier in cell}
            audit = audit_faces({identifier: nodes[identifier] for identifier in used}, families, skin)
            require(audit == report["parts"][str(solid)]["face_audit"],
                    f"MSH round-trip failed the face audit for solid {solid}.")
    return raw


def _native_mesh(raw, identifier, unit, assets, *, assembly):
    nodes = tuple(MeshNode(tag, tuple(xyz)) for tag, xyz in sorted(
        zip(raw["nodes"]["ids"], raw["nodes"]["coordinates"])))
    part_uuids = {}
    part_elements = {}
    elements = []
    inventory_counts = Counter()
    for block in raw["blocks"]:
        dim, typ, name, order = (block[k] for k in ("dimension", "element_type", "element_name", "order"))
        inventory_counts[(dim, typ, name, order)] += len(block["ids"])
        if dim == 3:
            tag = block["entity_tag"]
            part_uuid = part_uuids.setdefault(tag, str(uuid5(identifier, f"CAD solid {tag}")))
            part_elements.setdefault(tag, []).extend(block["ids"])
            elements.extend(MeshCell(i, dim, typ, name, order, tuple(conn), part_uuid)
                            for i, conn in zip(block["ids"], block["connectivity"]))
    elements.sort(key=lambda element: element.id)
    parts = tuple(MeshPart(part_uuids[tag], 3, tag, f"CAD solid {tag}" if assembly else "CAD solid",
                           tuple(sorted(part_elements[tag]))) for tag in sorted(part_uuids))
    inventory = tuple(CellInventory(dim, typ, name, order, count,
                                    "physical" if dim == 3 else "boundary", True)
                      for (dim, typ, name, order), count in sorted(inventory_counts.items()))
    omitted = sum(record.count for record in inventory if record.dimension == 2)
    return NativeMesh(nodes, tuple(elements), parts, unit, None, str(identifier), 3, inventory,
                      omitted, (), assets, "hybrid_assembly" if assembly else "hybrid_hex_core")


def generate_hybrid_hex_core(source, output_dir, *, length_unit, core_size,
                             boundary_size=None, safety_margin=0., min_scaled_jacobian=.025,
                             min_tet_sicn=.08, relative_volume_tolerance=.03,
                             allow_tet_fallback=False, cancel_event=None, timeout=120.):
    """Mesh a single closed STEP or BREP solid. Sizes use the normalized coordinate unit.

    STEP coordinates are normalized to mm. BREP coordinates require a declaration.
    With explicit fallback, a rejected hybrid can yield a fully audited Tet4 mesh.
    The output retains a source snapshot, request, MSH and verification report.
    """
    native, folder, report = _generate(source, output_dir, assembly=False, length_unit=length_unit,
        core_size=core_size, boundary_size=boundary_size, safety_margin=safety_margin,
        min_scaled_jacobian=min_scaled_jacobian, min_tet_sicn=min_tet_sicn,
        relative_volume_tolerance=relative_volume_tolerance, allow_tet_fallback=allow_tet_fallback,
        cancel_event=cancel_event, timeout=timeout)
    return HybridHexCoreCandidate(native, folder / "mesh.msh", folder / "report.json", report["quality"],
                                  report["face_audit"], report["core_audit"], report["cad_volume"],
                                  report["mesh_volume"], report["backend_version"], report["fallback_reason"])



def _generate(source, output_dir, *, assembly, length_unit, core_size,
              boundary_size, safety_margin, min_scaled_jacobian, min_tet_sicn,
              relative_volume_tolerance, allow_tet_fallback, cancel_event, timeout):
    source = Path(source).expanduser().resolve()
    if source.suffix.lower() not in (".step", ".stp", ".brep", ".brp") or not source.is_file():
        raise PrepError("invalid_hybrid_source", "Choose a readable STEP or BREP solid.")
    unit = cad_coordinate_length_unit(source, length_unit)
    if boundary_size is None:
        boundary_size = core_size
    numbers = {"core_size": core_size, "boundary_size": boundary_size, "safety_margin": safety_margin,
               "min_scaled_jacobian": min_scaled_jacobian, "min_tet_sicn": min_tet_sicn,
               "relative_volume_tolerance": relative_volume_tolerance, "timeout": timeout}
    for key, value in numbers.items():
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite or value < 0:
            raise PrepError("invalid_hybrid_request", f"{key} must be a finite nonnegative number.")
    if min(core_size, boundary_size, timeout) <= 0:
        raise PrepError("invalid_hybrid_request", "Core size, boundary size and timeout must be positive.")
    if max(min_scaled_jacobian, min_tet_sicn, relative_volume_tolerance) > 1:
        raise PrepError("invalid_hybrid_request", "Quality floors and relative volume tolerance must be at most one.")
    if type(allow_tet_fallback) is not bool:
        raise PrepError("invalid_hybrid_request", "Tet fallback requires an explicit boolean setting.")
    request = {**numbers, "length_unit": unit, "allow_tet_fallback": allow_tet_fallback, "assembly": assembly}
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    identifier = uuid4()
    folder = output_dir / f"hybrid-{identifier}"
    with TemporaryDirectory(prefix=".hybrid-", dir=output_dir) as temporary:
        stage = Path(temporary)
        snapshot = stage / f"source{source.suffix.lower()}"
        digest = _sha(source)
        shutil.copyfile(source, snapshot)
        if _sha(snapshot) != digest or _sha(source) != digest:
            raise PrepError("candidate_changed", "The CAD source changed while making a snapshot.")
        report = _run_worker(snapshot, stage, request, cancel_event, timeout)
        raw = _check_export(stage / "mesh.msh", report, assembly=assembly)
        if _sha(snapshot) != digest or _sha(source) != digest:
            raise PrepError("candidate_changed", "The CAD source changed during hybrid meshing.")
        if cancel_event is not None and cancel_event.is_set():
            raise PrepError("cancelled", "Hybrid meshing was cancelled.")
        artifact_names = {"source": snapshot.name, "request": "request.json",
                          "msh": "mesh.msh", "report": "report.json"}
        report["mesh_uuid"] = str(identifier)
        report["assets"] = {kind: {"name": name, "sha256": _sha(stage / name)}
                            for kind, name in artifact_names.items() if kind != "report"}
        (stage / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        assets = tuple(AssetDigest(kind, str(folder / name), _sha(stage / name))
                       for kind, name in artifact_names.items())
        native = _native_mesh(raw, identifier, unit, assets, assembly=assembly)
        stage.rename(folder)
    return native, folder, report
