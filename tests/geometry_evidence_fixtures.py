"""Synthetic analytic inspection fixtures; no native CAD or SDK execution."""
import hashlib
from copy import deepcopy
from uuid import uuid4


def material_inspection_data(tmp_path, geometry, *, probe_rows, policies):
    """Give synthetic analytic rows real UUIDs/assets for the evidence reader."""
    surfaces, volumes, curves = deepcopy(geometry)
    probes = deepcopy(probe_rows)
    identities = {row["uuid"]: str(uuid4()) for row in [*surfaces, *volumes]}
    for tag, face in enumerate(surfaces, 1):
        face.update(uuid=identities[face["uuid"]], backend_tag=tag,
                    center=face["samples"][0]["xyz"], normal_basis="gmsh_face_oriented_no_volume_sign",
                    sampling_status="unverified")
        face["samples"][0]["uv"] = [0., 0.]
        for use in face["orientation_by_volume"]:
            use["volume_uuid"] = identities[use["volume_uuid"]]
    for volume in volumes:
        members = [face for face in surfaces if face["uuid"] in [identities[value] for value in volume["surface_uuids"]]]
        volume.update(uuid=identities[volume["uuid"]],
            bbox=[min(face["bbox"][i] for face in members) for i in range(3)] +
                 [max(face["bbox"][i+3] for face in members) for i in range(3)],
            surface_uuids=[identities[value] for value in volume["surface_uuids"]])
    for curve in curves:
        curve["adjacent_surface_uuids"] = [identities[value] for value in curve["adjacent_surface_uuids"]]
        points = [row["xyz"] for row in curve["endpoints"]]
        curve["bbox"] = [min(p[i] for p in points) for i in range(3)] + [max(p[i] for p in points) for i in range(3)]
    for rows in probes.values():
        for row in rows:
            for key in ("surface_uuid", "volume_uuid"):
                row[key] = identities.get(row[key], row[key])
    source, xao, metadata = (tmp_path / name for name in ("source.step", "geometry.xao", "metadata.json"))
    source.write_bytes(b"synthetic analytic reader source, not native CAD")
    xao.write_bytes(b"synthetic analytic reader XAO, not native CAD")
    data = {"schema_version": 1, "source_kind": "cad_geometry_inspection",
        "backend": {"name": "gmsh", "version": "fake"},
        "geometry_resource_uuid": str(uuid4()), "geometry_revision": 1, "length_unit": "mm",
        "source": {"path": str(source), "captured_path": str(source),
                   "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "assets": {"xao": str(xao), "metadata": str(metadata)}, "sdk_error_count": 0,
        "geometry_tolerance": 1e-8, "surfaces": surfaces, "volumes": volumes, "curves": curves,
        **deepcopy(policies), **probes}
    return data, metadata
