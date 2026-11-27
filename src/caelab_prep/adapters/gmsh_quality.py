"""Metrics on the current Gmsh mesh, aggregated by family and CAD volume.

Straight-edge angles use primary nodes. Jacobian estimates and quadrature
use the full isoparametric map, including midside nodes on curved geometry.
"""
from itertools import combinations

import numpy as np


_TRI = ((0, 1, 2),)
_QUAD = ((0, 1, 2, 3),)
_TET = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
_HEX = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
        (2, 3, 7, 6), (3, 0, 4, 7))
_WEDGE = ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5))
_PYRAMID = ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4))
FAMILIES = {2: ("tri3", _TRI), 3: ("quad4", _QUAD), 4: ("tet4", _TET),
            5: ("hex8", _HEX), 6: ("wedge6", _WEDGE), 7: ("pyramid5", _PYRAMID),
            9: ("tri6", _TRI), 11: ("tet10", _TET), 16: ("quad8", _QUAD),
            17: ("hex20", _HEX)}

_TET_CORNERS = ((0, 1, 2, 3), (1, 0, 3, 2), (2, 0, 1, 3), (3, 0, 2, 1))
_HEX_CORNERS = ((0, 1, 3, 4), (1, 2, 0, 5), (2, 3, 1, 6), (3, 0, 2, 7),
                (4, 7, 5, 0), (5, 4, 6, 1), (6, 5, 7, 2), (7, 6, 4, 3))
_WEDGE_CORNERS = ((0, 1, 2, 3), (1, 2, 0, 4), (2, 0, 1, 5),
                  (3, 5, 4, 0), (4, 3, 5, 1), (5, 4, 3, 2))
_PYRAMID_BASE = ((0, 1, 3, 4), (1, 2, 0, 4), (2, 3, 1, 4), (3, 0, 2, 4))
_CORNERS = {_TET: _TET_CORNERS, _HEX: _HEX_CORNERS, _WEDGE: _WEDGE_CORNERS,
            _PYRAMID: _PYRAMID_BASE}


def _corner_jacobians(points, faces):
    if faces in _CORNERS:
        values = []
        for c, i, j, k in _CORNERS[faces]:
            a, b, d = (_unit(points[:, n] - points[:, c]) for n in (i, j, k))
            values.append(np.sum(np.cross(a, b) * d, axis=1))
        return np.min(values, axis=0)
    polygon = points[:, faces[0]]
    directions = _unit(np.roll(polygon, -1, axis=1) - polygon)
    turns = np.cross(np.roll(directions, 1, axis=1), directions)
    # A concave or folded corner can reverse relative to the area normal.
    normal = _unit(np.cross(polygon[:, 1] - polygon[:, 0], polygon[:, 2] - polygon[:, 0]) +
                   (np.cross(polygon[:, 2] - polygon[:, 0], polygon[:, 3] - polygon[:, 0])
                    if len(faces[0]) == 4 else 0))
    return np.min(np.sum(turns * normal[:, None, :], axis=-1), axis=1)


def _unit(vector):
    length = np.linalg.norm(vector, axis=-1, keepdims=True)
    if np.any(length == 0) or not np.isfinite(length).all():
        raise ValueError("Degenerate mesh edge or face normal in quality inventory")
    return vector / length


def _angles(a, b):
    return np.rad2deg(np.arccos(np.clip(np.sum(a * b, axis=-1), -1, 1)))


def _corner_metrics(points, faces):
    """Face skew is equiangular skew. Dihedrals use outward area normals."""
    normals = []
    skew = np.zeros(len(points))
    edges = set()
    for face in faces:
        polygon = points[:, face]
        side = np.roll(polygon, -1, axis=1) - polygon
        tangents = _unit(side)
        angles = _angles(tangents, -np.roll(tangents, 1, axis=1))
        ideal = 180 - 360 / len(face)
        skew = np.maximum(skew, np.maximum((angles - ideal) / (180 - ideal),
                                           (ideal - angles) / ideal).max(axis=1))
        normals.append(_unit(np.cross(side[:, 0], polygon[:, 2] - polygon[:, 0]) +
                             (np.cross(polygon[:, 2] - polygon[:, 0], polygon[:, 3] - polygon[:, 0])
                              if len(face) == 4 else 0)))
        edges.update(tuple(sorted((a, b))) for a, b in zip(face, face[1:] + face[:1]))
    lengths = np.stack([np.linalg.norm(points[:, a] - points[:, b], axis=1)
                        for a, b in sorted(edges)], axis=1)
    dihedrals = [180 - _angles(normals[i], normals[j]) for i, j in combinations(range(len(faces)), 2)
                 if len(set(faces[i]) & set(faces[j])) == 2]
    return float((lengths.max(1) / lengths.min(1)).max()), float(skew.max()), (
        min(float(a.min()) for a in dihedrals) if dihedrals else None)


def _measures(mesh, typ, tag):
    local, weights = mesh.getIntegrationPoints(typ, "Gauss5")
    _, det, _ = mesh.getJacobians(typ, local, tag)
    return np.asarray(det).reshape(-1, len(weights)) @ weights


def inspect_mesh_quality(gmsh, *, cad_volumes=None, measure_gradation=False):
    """Inspect every surface/volume element. Unknown types and empty CAD solids fail."""
    mesh = gmsh.model.mesh
    ids, xyz, _ = mesh.getNodes()
    order = np.argsort(ids)
    tags = np.asarray(ids)[order]
    coordinates = np.asarray(xyz).reshape(-1, 3)[order]
    by_type = {}
    adjacent_sizes = {}
    max_size_ratio, adjacent_pairs = 1., 0
    for dim in (2, 3):
        for typ in map(int, mesh.getElementTypes(dim)):
            if typ not in FAMILIES:
                raise ValueError(f"Unsupported dimension-{dim} Gmsh family {typ} in quality inventory")
            name, faces = FAMILIES[typ]
            elements, connection = mesh.getElementsByType(typ)
            count = len(elements)
            points = coordinates[np.searchsorted(tags, connection)].reshape(count, -1, 3)
            aspect, skew, angle = _corner_metrics(points, faces)
            sj = _corner_jacobians(points, faces)
            sdk_sj = np.asarray(mesh.getElementQualities(elements, "minSJ"))
            sicn = np.asarray(mesh.getElementQualities(elements, "minSICN"))
            determinant = np.asarray(mesh.getElementQualities(elements, "minDetJac"))
            measure = _measures(mesh, typ, -1)
            if not all(np.isfinite(values).all() for values in (sj, sdk_sj, sicn, determinant, measure)):
                raise ValueError(f"Nonfinite Jacobian or measure for {name}")
            invalid = (sj <= 0) | (sdk_sj <= 0) | (sicn <= 0) | (determinant <= 0) | (measure <= 0)
            if measure_gradation and dim == 3 and not invalid.any():
                for row, length in zip(np.asarray(connection).reshape(count, -1), np.cbrt(measure)):
                    for face in faces:
                        key = tuple(sorted(int(row[i]) for i in face))
                        neighbor = adjacent_sizes.pop(key, None)
                        if neighbor is None:
                            adjacent_sizes[key] = length
                        else:
                            adjacent_pairs += 1
                            max_size_ratio = max(max_size_ratio, length / neighbor, neighbor / length)
            by_type[name] = {"count": count, "min_scaled_jacobian": float(sj.min()),
                             "min_sdk_scaled_jacobian": float(sdk_sj.min()), "min_sicn": float(sicn.min()),
                             "min_det_jacobian": float(determinant.min()),
                             "invalid_element_ids": [int(i) for i in elements[invalid]],
                             "max_edge_aspect_ratio": aspect, "max_face_skewness": skew,
                             "min_dihedral_degrees": angle, "measure": float(measure.sum())}
    volumes = {}
    for tag, exact in (cad_volumes or {}).items():
        families = mesh.getElementTypes(3, tag)
        if not len(families) or not np.isfinite(exact) or exact <= 0:
            raise ValueError(f"Missing positive volume or mesh on CAD solid {tag}")
        volume = sum(float(_measures(mesh, int(typ), tag).sum()) for typ in families)
        volumes[str(tag)] = {"cad_volume": exact, "mesh_volume": volume,
                             "relative_error": abs(volume - exact) / exact}
    report = {"by_type": by_type, "by_volume": volumes,
            "jacobian_metric": "Minimum signed unit-edge corner determinant (base corners for pyramids, "
                               "area-normal component for faces); SDK minSJ, minSICN and adaptive minDetJac",
            "measure_rule": "Gauss5 on the full Gmsh element map",
            "angle_metric": "primary-node chord angles and area-weighted quad normals"}
    if measure_gradation:
        report["observed_gradation"] = {"shared_faces": adjacent_pairs,
            "max_adjacent_volume_length_ratio": float(max_size_ratio) if adjacent_pairs else None}
    return report
