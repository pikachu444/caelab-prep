"""Pure ASCII MSH geometry and TET4 checks; no SDK, Qt or solver execution."""
from dataclasses import FrozenInstanceError, asdict
import json
import math

import pytest

from caelab_prep.application import surface_tet
from caelab_prep.application.surface_tet import load_closed_surface, smooth_tet4, tetra_metrics
from caelab_prep.cae_core.errors import PrepError


REGULAR = ((0., 0., 0.), (1., 0., 0.), (.5, math.sqrt(3) / 2, 0.),
           (.5, math.sqrt(3) / 6, math.sqrt(2 / 3)))
TET_FACES = ((1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1))
CUBE = ((0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.),
        (0., 0., 1.), (1., 0., 1.), (1., 1., 1.), (0., 1., 1.))
CUBE_FACES = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
              (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))


def write_surface(tmp_path, points=REGULAR, facets=TET_FACES, *, version="2.2", extra=(), groups=None):
    ids = tuple(11 + 20 * index for index in range(len(points)))
    triangle_ids = tuple(503 + 10 * index for index in range(len(facets)))
    groups = [(2, 7, "Original boundary")] if groups is None else groups
    lines = ["$MeshFormat", version + " 0 8", "$EndMeshFormat", "$PhysicalNames", str(len(groups))]
    lines += [f'{dim} {tag} "{name}"' for dim, tag, name in groups]
    lines += ["$EndPhysicalNames"]
    physical = [tag for dim, tag, _ in groups if dim == 2 and tag != 99]
    if version == "4.1":
        lines += ["$Entities", "0 0 1 0", "1 -2 -2 -2 2 2 2 " + str(len(physical))
                  + " " + " ".join(map(str, physical)) + " 0", "$EndEntities"]
    lines += ["$Nodes"]
    if version == "2.2":
        lines.append(str(len(ids)))
        lines += [str(identifier) + " " + " ".join(map(repr, point)) for identifier, point in zip(ids, points)]
    else:
        lines += [f"1 {len(ids)} {min(ids)} {max(ids)}", f"2 1 0 {len(ids)}", " ".join(map(str, ids))]
        lines += [" ".join(map(repr, point)) for point in points]
    lines += ["$EndNodes", "$Elements"]
    if version == "2.2":
        lines.append(str(len(facets) + len(extra)))
        lines += [f"{identifier} 2 2 {physical[0] if physical else 0} 1 " + " ".join(str(ids[i]) for i in face)
                  for identifier, face in zip(triangle_ids, facets)]
        lines += [f"{9001 + i} {typ} 0 " + " ".join(str(ids[n]) for n in conn) for i, (typ, conn) in enumerate(extra)]
    else:
        assert not extra
        lines += [f"1 {len(facets)} {min(triangle_ids)} {max(triangle_ids)}", f"2 1 2 {len(facets)}"]
        lines += [str(identifier) + " " + " ".join(str(ids[i]) for i in face) for identifier, face in zip(triangle_ids, facets)]
    lines += ["$EndElements"]
    path = tmp_path / "surface.msh"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, ids, triangle_ids


@pytest.mark.parametrize("version", ["2.2", "4.1"])
@pytest.mark.parametrize("points,facets,volume", [(REGULAR, TET_FACES, math.sqrt(2) / 12), (CUBE, CUBE_FACES, 1.)])
def test_closed_sparse_surface_preserves_ids_groups_orientation_and_source(tmp_path, version, points, facets, volume):
    source, ids, triangle_ids = write_surface(tmp_path, points, facets, version=version)
    before = source.read_bytes()
    result = load_closed_surface(source, length_unit="mm")
    assert result.node_ids == ids and result.coordinates == points
    assert result.triangle_ids == triangle_ids
    assert result.triangles == tuple(tuple(ids[i] for i in face) for face in facets)
    assert result.signed_volume == pytest.approx(volume)
    assert result.physical_groups[0].triangle_ids == triangle_ids
    assert result.length_unit == "mm" and source.read_bytes() == before
    json.dumps(asdict(result), allow_nan=False)
    with pytest.raises(FrozenInstanceError):
        result.physical_groups[0].name = "changed"


def test_overlapping_physical_groups_preserve_facet_membership(tmp_path):
    path, _, facets = write_surface(tmp_path, version="4.1", groups=[(2, 7, "Boundary"), (2, 8, "Shared")])
    result = load_closed_surface(path, length_unit="cm")
    assert [group.tag for group in result.physical_groups] == [7, 8]
    assert all(group.triangle_ids == facets for group in result.physical_groups)


@pytest.mark.parametrize("kind,expected", [
    ("open", "surface_not_manifold"), ("nonmanifold", "surface_not_manifold"),
    ("inconsistent", "surface_orientation"), ("inward", "surface_orientation"),
    ("duplicate", "duplicate_surface_facets"), ("zero_area", "degenerate_surface_facet"),
    ("unused", "unused_surface_nodes"), ("same_coordinates", "duplicate_surface_coordinates"),
    ("disconnected", "surface_disconnected"), ("pinched_vertex", "surface_vertex_link"),
    ("self_intersection", "surface_self_intersection"), ("coplanar_overlap", "surface_self_intersection"),
])
def test_invalid_surface_is_rejected_without_repairs(tmp_path, kind, expected):
    points, faces = list(REGULAR), list(TET_FACES)
    if kind == "open": faces.pop()
    elif kind == "nonmanifold": points, faces = list(CUBE), [*CUBE_FACES, (0, 1, 6)]
    elif kind == "inconsistent": faces[0] = faces[0][::-1]
    elif kind == "inward": faces = [face[::-1] for face in faces]
    elif kind == "duplicate": faces.append(faces[0][::-1])
    elif kind == "zero_area": points[3] = (.5, 0., 0.)
    elif kind == "unused": points.append((5., 5., 5.))
    elif kind == "same_coordinates": points.append(points[0])
    elif kind in ("disconnected", "pinched_vertex"):
        if kind == "disconnected":
            points += [tuple(value + 3 for value in point) for point in REGULAR]
            faces += [tuple(i + 4 for i in face) for face in TET_FACES]
        else:
            points += [(-1., 0., 0.), (-.5, -math.sqrt(3) / 2, 0.), (-.5, -math.sqrt(3) / 6, -math.sqrt(2 / 3))]
            remap = {0: 0, 1: 4, 2: 5, 3: 6}
            faces += [tuple(remap[i] for i in face) for face in TET_FACES]
    else:
        points, faces = list(CUBE), list(CUBE_FACES)
        if kind == "self_intersection": points[6] = (-.4, -.3, -.2)
        else: points[4:] = [(x + .2, y + .3, 0.) for x, y, _ in points[4:]]
    path, _, _ = write_surface(tmp_path, points, faces)
    before = path.read_bytes()
    with pytest.raises(PrepError) as error:
        load_closed_surface(path, length_unit="mm")
    assert error.value.code == expected
    assert path.read_bytes() == before


@pytest.mark.parametrize("typ,conn", [(1, (0, 1)), (15, (0,)), (4, (0, 1, 2, 3))])
def test_every_non_tri_record_blocks_the_whole_surface(tmp_path, typ, conn):
    path, _, _ = write_surface(tmp_path, extra=[(typ, conn)])
    with pytest.raises(PrepError) as error:
        load_closed_surface(path, length_unit="mm")
    assert error.value.code == "unsupported_surface_inventory"


@pytest.mark.parametrize("typ,arity", [(9, 6), (11, 10)])
def test_higher_order_records_are_not_linearized_or_dropped(tmp_path, typ, arity):
    points = (*REGULAR, *((2. + i, 2., 2.) for i in range(arity - 4)))
    path, _, _ = write_surface(tmp_path, points, extra=[(typ, tuple(range(arity)))])
    with pytest.raises(PrepError) as error:
        load_closed_surface(path, length_unit="mm")
    assert error.value.code == "unsupported_surface_inventory"


@pytest.mark.parametrize("scale", [1e-90, 1., 1e90])
def test_approved_profile_now_rejects_high_boundary_aspect_with_original_facet_id(tmp_path, scale):
    # The earlier packet retained this surface; the approved default profile
    # now requires input-boundary AR <= 4 before any volume generation.
    points = tuple((100 * x, y, z) for x, y, z in REGULAR)
    expected = max(math.dist(points[i], points[j]) for i, j in ((1, 2), (1, 3), (2, 3)))
    expected /= min(math.dist(points[i], points[j]) for i, j in ((1, 2), (1, 3), (2, 3)))
    path, _, triangle_ids = write_surface(tmp_path, tuple(tuple(v * scale for v in p) for p in points))
    before = path.read_bytes()
    with pytest.raises(PrepError) as error:
        load_closed_surface(path, length_unit="mm")
    assert error.value.code == "surface_triangle_aspect"
    assert error.value.message == "Surface triangle aspect ratio exceeds tolerance"
    assert error.value.details == {"triangle_id": triangle_ids[0], "edge_aspect_ratio": pytest.approx(expected), "tolerance": 4.}
    assert path.read_bytes() == before


def test_exact_boundary_aspect_four_is_accepted(tmp_path):
    # |AC| / |AB| = sqrt(32) / sqrt(2) = 4, using exact integer coordinates.
    points = ((0., 0., 0.), (1., 0., 1.), (4., 4., 0.), (0., 4., 4.))
    path, _, _ = write_surface(tmp_path, points)
    assert load_closed_surface(path, length_unit="mm").signed_volume == pytest.approx(32 / 6)


@pytest.mark.parametrize("groups", [[(1, 7, "Edges")], [(2, 99, "Empty")]])
def test_declared_empty_or_non_surface_group_is_not_lost(tmp_path, groups):
    path, _, _ = write_surface(tmp_path, groups=groups)
    with pytest.raises(PrepError) as error:
        load_closed_surface(path, length_unit="m")
    assert error.value.code == "invalid_surface_group"


@pytest.mark.parametrize("constant,value,expected", [("MAX_NODES", 3, "surface_size_limit"),
    ("MAX_TRIANGLES", 3, "surface_size_limit"), ("MAX_INPUT_BYTES", 1, "surface_size_limit"),
    ("MAX_PAIRS", 0, "surface_pair_limit")])
def test_admission_limits_are_explicit_errors(tmp_path, monkeypatch, constant, value, expected):
    path, _, _ = write_surface(tmp_path)
    monkeypatch.setattr(surface_tet, constant, value)
    with pytest.raises(PrepError) as error:
        load_closed_surface(path, length_unit="mm")
    assert error.value.code == expected


def test_unit_and_nonfinite_input_are_rejected(tmp_path):
    path, _, _ = write_surface(tmp_path)
    with pytest.raises(PrepError, match="Declare"):
        load_closed_surface(path, length_unit="unknown")
    path.write_text(path.read_text().replace("0.0 0.0 0.0", "nan 0.0 0.0", 1))
    with pytest.raises(PrepError) as error:
        load_closed_surface(path, length_unit="mm")
    assert error.value.code == "invalid_surface_mesh"


@pytest.mark.parametrize("scale", [1e-90, 1e-6, 1., 1e90])
def test_regular_metrics_are_scaled_and_translation_independent(scale):
    points = [tuple(scale * (value + 1024) for value in point) for point in REGULAR]
    result = tetra_metrics(points)
    assert result["problem"] is None
    assert result["corner_scaled_jacobian"] == pytest.approx(1., abs=1e-12)
    assert result["edge_aspect_ratio"] == pytest.approx(1., abs=1e-12)
    assert result["signed_volume"] == pytest.approx(math.sqrt(2) / 12 * scale ** 3, rel=1e-11, abs=0.)


def test_sliver_orientation_degenerate_and_nonfinite_metrics_are_explicit():
    sliver = ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (.25, .25, 1e-7))
    result = tetra_metrics(sliver)
    assert result["problem"] is None and result["signed_volume"] > 0
    assert 0 < result["corner_scaled_jacobian"] < 1e-5
    inverse = tetra_metrics((REGULAR[1], REGULAR[0], *REGULAR[2:]))
    assert inverse["signed_volume"] < 0 and inverse["corner_scaled_jacobian"] < 0
    assert inverse["problem"] == "inverted"
    assert tetra_metrics(((0., 0., 0.),) * 4)["problem"] == "degenerate"
    assert tetra_metrics((*REGULAR[:3], (math.inf, 0., 0.)))["problem"] == "nonfinite_geometry"
    with pytest.raises(PrepError): tetra_metrics((*REGULAR, *REGULAR))


def star():
    ids = (11, 31, 71, 101, 501)
    coordinates = (*REGULAR, (.35, .18, .12))
    cells = tuple((ids[-1], *(ids[i] for i in face)) for face in TET_FACES)
    return ids, coordinates, cells, ids[:-1]


def test_laplacian_moves_interior_improves_metrics_and_keeps_boundary_and_connectivity():
    ids, points, cells, boundary = star()
    before = [tetra_metrics([dict(zip(ids, points))[i] for i in cell]) for cell in cells]
    moved, report = smooth_tet4(ids, points, cells, boundary)
    assert moved[:-1] == points[:-1] and moved[-1] != points[-1]
    after = [tetra_metrics([dict(zip(ids, moved))[i] for i in cell]) for cell in cells]
    assert all(value["problem"] is None and value["signed_volume"] > 0 for value in after)
    assert min(v["corner_scaled_jacobian"] for v in after) > min(v["corner_scaled_jacobian"] for v in before)
    assert max(v["edge_aspect_ratio"] for v in after) < max(v["edge_aspect_ratio"] for v in before)
    assert report["moves"] > 0 and report["iterations"] == 2 and report["interior_nodes"] == 1
    assert report["max_displacement"] == pytest.approx(math.dist(points[-1], moved[-1]))
    assert (ids, points, cells, boundary) == star()
    assert smooth_tet4(ids, points, cells, boundary) == (moved, report)
    json.dumps(report, allow_nan=False)


def test_zero_iterations_and_no_interior_report_actual_no_op():
    ids, points, cells, boundary = star()
    result, report = smooth_tet4(ids, points, cells, boundary, iterations=0)
    assert result == points and report["iterations"] == report["moves"] == report["max_displacement"] == 0
    result, report = smooth_tet4(ids[:4], points[:4], (ids[:4],), ids[:4], iterations=100)
    assert result == points[:4] and report["interior_nodes"] == report["iterations"] == report["moves"] == 0
    assert report["iterations_requested"] == 100


@pytest.mark.parametrize("change", ["iterations", "iteration_limit", "relaxation", "missing_boundary", "unknown_node", "inverted", "nonfinite"])
def test_smoothing_boundary_rejects_invalid_arguments(change):
    ids, points, cells, boundary = star()
    kwargs = {}
    if change == "iterations": kwargs["iterations"] = True
    elif change == "iteration_limit": kwargs["iterations"] = 101
    elif change == "relaxation": kwargs["relaxation"] = 0
    elif change == "missing_boundary": boundary = boundary[:-1]
    elif change == "unknown_node": cells = ((9999, *cells[0][1:]), *cells[1:])
    elif change == "inverted": cells = ((cells[0][1], cells[0][0], *cells[0][2:]), *cells[1:])
    else: points = (*points[:-1], (math.nan, 0., 0.))
    with pytest.raises(PrepError) as error:
        smooth_tet4(ids, points, cells, boundary, **kwargs)
    assert error.value.code == "invalid_smoothing"
