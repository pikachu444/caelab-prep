"""Geometry-bound Washer control drafts; no mesh generation or document edits."""
from dataclasses import asdict
import math
from pathlib import Path

from .geometry_features import recognize_cylindrical_holes
from .geometry_inspection import GeometryInspection, read_geometry_inspection
from .meshing_criteria import MeshingCriteria
from .storage import read_json, write_json
from ..adapters.gmsh_topology import rectangular_wire
from ..cae_core.errors import PrepError


def create_washer_control_draft(inspection, criteria, *, hole_surface_uuid,
                                opening_surface_uuid, length_tolerance):
    """Bind explicit controls to one supported opening, with equal radial spacing.

    Width is the total radial extent from the hole boundary. A rectangular
    support clearance check does not qualify a generated Quad/Tria mesh.
    """
    if not isinstance(inspection, GeometryInspection):
        raise PrepError("washer_control_input", "Read a geometry inspection before configuring Washer controls.")
    if not isinstance(criteria, MeshingCriteria) or criteria.length_unit != "mm" or inspection.length_unit != "mm":
        raise PrepError("washer_control_unit", "Washer control drafts require mm criteria and inspection coordinates.")
    if (criteria.washer_element_family is None or criteria.washer_rim_divisions is None
            or criteria.washer_width is None or criteria.washer_layers not in (1, 2)):
        raise PrepError("washer_controls_incomplete", "Choose Quad/Tria, rim divisions, total radial width and one or two layers.")
    report = recognize_cylindrical_holes(inspection, length_tolerance=length_tolerance)
    feature = next((row for row in report["features"] if row["surface_uuid"] == hole_surface_uuid), None)
    opening = next((cap for cap in feature["caps"] if cap["surface_uuid"] == opening_surface_uuid
                    and cap["kind"] == "rectangular_opening"), None) if feature else None
    if opening is None:
        raise PrepError("washer_opening_unverified", "Select an actual rectangular opening of a recognized hole; closed disks and blends are unsupported.")
    data = inspection.to_dict()
    plane = next(row for row in data["surfaces"] if row["uuid"] == opening_surface_uuid)
    tags = next(loop["curve_tags"] for loop in plane["curve_loops"]
                if list(map(abs, loop["curve_tags"])) != [opening["circle_tag"]])
    axis = next(index for index, value in enumerate(feature["axis_direction"]) if value)
    wire = rectangular_wire(tags, {row["backend_tag"]: row for row in data["curves"]},
                            axis, opening["center"][axis], length_tolerance)
    radii = [feature["radius"] + criteria.washer_width * i / criteria.washer_layers
             for i in range(criteria.washer_layers + 1)]
    if any(not math.isfinite(r) for r in radii) or any(b - a <= length_tolerance for a, b in zip(radii, radii[1:])):
        raise PrepError("washer_width_unresolved", "Each requested radial layer must be resolved beyond the recognition tolerance.")
    if wire is None or any(not low + radii[-1] + length_tolerance < opening["center"][i] < high - radii[-1] - length_tolerance
                           for i, low, high in zip(wire["plane_axes"], wire["minimum"], wire["maximum"])):
        raise PrepError("washer_support_clearance", "The requested annular extent must remain inside the rectangular opening support.")
    inspection.verify_assets()
    return {"schema": "caelab.washer-control-draft", "version": 1,
        "inspection_metadata": next(asset.path for asset in inspection.assets if asset.kind == "metadata"),
        "geometry_resource_uuid": inspection.geometry_resource_uuid, "geometry_revision": inspection.geometry_revision,
        "assets": [asdict(asset) for asset in inspection.assets], "criteria": criteria.to_dict(),
        "hole_surface_uuid": hole_surface_uuid, "opening_surface_uuid": opening_surface_uuid,
        "opening_circle_tag": opening["circle_tag"], "opening_center": opening["center"],
        "length_tolerance": length_tolerance, "width_policy": "total_radial_width",
        "layer_spacing": "equal_radial_spacing", "radial_layer_radii": radii,
        "mesh_generation_supported": False, "modifications": 0}


def read_washer_control_draft(path):
    """Reopen against the original inspection, recomputing the target and extent."""
    try:
        data = read_json(Path(path))
        if not isinstance(data, dict) or data.get("schema") != "caelab.washer-control-draft" or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("Unsupported Washer control draft")
        if (type(data["geometry_revision"]) is not int or type(data["opening_circle_tag"]) is not int
                or type(data["modifications"]) is not int or data["modifications"] != 0
                or data["mesh_generation_supported"] is not False
                or any(type(value) not in (int, float) for key in ("opening_center", "radial_layer_radii") for value in data[key])):
            raise ValueError("Draft identifiers, geometry numbers and execution flags must retain their explicit JSON types")
        inspection = read_geometry_inspection(data["inspection_metadata"])
        expected = create_washer_control_draft(inspection, MeshingCriteria.from_dict(data["criteria"]),
            hole_surface_uuid=data["hole_surface_uuid"], opening_surface_uuid=data["opening_surface_uuid"],
            length_tolerance=data["length_tolerance"])
        if data != expected:
            raise ValueError("Washer controls or target evidence differ from the recomputed draft")
        return expected
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, StopIteration) as exc:
        raise PrepError("invalid_washer_control_draft", f"Cannot read Washer controls: {exc}") from exc


def save_washer_control_draft(path, inspection, criteria, **target):
    """Save one snapshot containing controls and target evidence, preserving CAD."""
    draft = create_washer_control_draft(inspection, criteria, **target)
    destination = Path(path).expanduser().resolve()
    protected = [Path(asset.path).resolve() for asset in inspection.assets]
    protected.append(Path(inspection.to_dict()["source"]["path"]).resolve())
    def validate_destination():
        if any(destination == asset or (destination.exists() and asset.exists() and destination.samefile(asset)) for asset in protected):
            raise PrepError("washer_control_overwrite", "Save the control draft separately from its source and inspection assets.")
        if destination.exists():
            try:
                previous = read_json(destination)
                own_draft = (isinstance(previous, dict) and previous.get("schema") == "caelab.washer-control-draft"
                             and type(previous.get("version")) is int and previous["version"] == 1)
            except (OSError, UnicodeError, ValueError):
                own_draft = False
            if not own_draft:
                raise PrepError("washer_control_overwrite", "Choose a new file or an existing Washer control draft; other files are preserved.")
        inspection.verify_assets()
    validate_destination()
    try:
        write_json(destination, draft, before_replace=validate_destination)
    except OSError as exc:
        raise PrepError("washer_control_io", f"Cannot save Washer controls: {exc}") from exc
    return draft
