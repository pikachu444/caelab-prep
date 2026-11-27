"""Real CAD worker tests for wall layers, curved block maps and oriented seeding."""

from contextlib import contextmanager
import math

import pytest

from caelab_prep.adapters.gmsh_backend import GmshBackend, GmshBackendError


@contextmanager
def _model():
    gmsh = pytest.importorskip("gmsh")
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("verification")
        yield gmsh
    finally:
        gmsh.finalize()


def _drilled_plate(folder, *, split_lid=False):
    path = folder / "wall.brep"
    with _model() as gmsh:
        occ = gmsh.model.occ
        body = occ.addBox(-6, -5, 0, 12, 10, 2)
        bore = occ.addCylinder(0, 0, 0, 0, 0, 2, 2)
        plate, _ = occ.cut([(3, body)], [(3, bore)])
        if split_lid:
            partition = occ.addRectangle(-6, -5, 2, 2, 10)
            occ.fragment(plate, [(2, partition)])
        occ.synchronize()
        gmsh.write(str(path))
    with _model() as gmsh:
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        bottom, = [tag for _, tag in gmsh.model.getEntities(2)
                   if abs(gmsh.model.getBoundingBox(2, tag)[5]) < 1e-6]
    return path, bottom


def _wire(occ, coordinates):
    nodes = [occ.addPoint(*p) for p in coordinates]
    edges = [occ.addLine(a, b) for a, b in zip(nodes, nodes[1:] + nodes[:1])]
    return occ.addWire(edges, checkClosed=True)


def _curved_block(folder, *, loft):
    path = folder / "block.brep"
    radius = 19.
    with _model() as gmsh:
        occ = gmsh.model.occ
        if loft:
            wires = []
            for i in range(5):
                t = i / 4
                theta, twist, scale = math.pi * t / 3, .48 * t, 1 - .25 * t
                corners = []
                for u, v in ((-2, -1), (2, -1), (2, 1), (-2, 1)):
                    r = radius + scale * (u * math.cos(twist) - v * math.sin(twist))
                    z = 2*t + scale * (u * math.sin(twist) + v * math.cos(twist))
                    corners.append((r * math.cos(theta), r * math.sin(theta), z))
                wires.append(_wire(occ, corners))
            occ.addThruSections(wires, makeSolid=True)
        else:
            wire = _wire(occ, [(radius-2, 0, -1), (radius+2, 0, -1),
                               (radius+2, 0, 1), (radius-2, 0, 1)])
            wall = occ.addPlaneSurface([wire])
            occ.revolve([(2, wall)], 0, 0, 0, 0, 0, 1, math.pi/3)
        occ.synchronize()
        gmsh.write(str(path))
    return path


def _sectors(path):
    """Read the CAD curve tags as the worker sees them in a fresh OCC import."""
    with _model() as gmsh:
        model = gmsh.model
        model.occ.importShapes(str(path))
        model.occ.synchronize()
        curved = []
        for _, edge in model.getEntities(1):
            if model.getType(1, edge) == "Circle":
                lower, upper = model.getParametrizationBounds(1, edge)
                start = model.getValue(1, edge, lower)
                end = model.getValue(1, edge, upper)
                curved.append((edge, start[1] < end[1]))
        assert len(curved) == 4
    return curved


def _arc_lengths(path, edge):
    """Measure physical sub-arc lengths along the geometric path in the exported MSH."""
    with _model() as gmsh:
        gmsh.open(str(path))
        types, _, nodes = gmsh.model.mesh.getElements(1, edge)
        assert len(types) == 1
        _, _, _, width, _, _ = gmsh.model.mesh.getElementProperties(int(types[0]))
        corner_ids = {int(n) for element in nodes[0].reshape(-1, width) for n in element[:2]}
        xyz = [gmsh.model.mesh.getNode(n)[0] for n in corner_ids]
        radius = math.hypot(*xyz[0][:2])
        angles = sorted(math.atan2(p[1], p[0]) for p in xyz)
        return [radius * (b-a) for a, b in zip(angles, angles[1:])]


def test_drilled_wall_layers_reach_prescribed_depths(tmp_path):
    path, bottom = _drilled_plate(tmp_path)
    layers = {"face": bottom, "vector": (0, 0, 2), "heights": (.08, .28, .58, 1)}
    result = GmshBackend().generate(path, tmp_path / "candidate", 1, prismatic_layers=layers)
    stack = result["mesh"]["nodes"]["coordinates"]
    assert sorted({round(z, 7) for _, _, z in stack}) == [0, .16, .56, 1.16, 2]
    q = result["quality"]["by_type"]
    assert set(q) == {"tri3", "quad4", "wedge6"} and q["wedge6"]["min_det_jacobian"] > 0
    applied = result["recipe"]["advanced"]["applied"]["layers"]
    assert applied["verified_overlap"] == pytest.approx(2*(120-4*math.pi))
    assert set(applied["source_to_mesh_face_tags"].values()) == {s["backend_tag"] for s in result["surfaces"]}
    wall_tag = applied["source_to_mesh_face_tags"][str(bottom)]
    wall, = [s for s in result["surfaces"] if s["backend_tag"] == wall_tag]
    assert wall["area"] == pytest.approx(120-4*math.pi)
    assert abs(wall["center"][2]) < 1e-8
    assert q["wedge6"]["measure"] == pytest.approx(2*(120-4*math.pi), rel=.01)
    with pytest.raises(GmshBackendError, match="extrusion does not match"):
        GmshBackend().generate(path, tmp_path / "outside", 1,
                               prismatic_layers={**layers, "vector": (0, 0, -2)})


def test_layer_rejects_an_unrepresented_cad_face_partition(tmp_path):
    path, bottom = _drilled_plate(tmp_path, split_lid=True)
    with pytest.raises(GmshBackendError, match="changes the CAD face partition"):
        GmshBackend().generate(path, tmp_path / "candidate", 1,
                               prismatic_layers={"face": bottom, "vector": (0, 0, 2),
                                                 "heights": (.25, .5, 1)})


def test_ambiguous_seeds_and_unbounded_size_fields_rejected_before_capture(tmp_path):
    path = _curved_block(tmp_path, loft=False)
    seed = [4, "Progression", 1.]
    candidate = tmp_path / "invalid"
    with pytest.raises(GmshBackendError, match="Duplicate edge seed"):
        GmshBackend().generate(path, candidate, 1., structured_blocks=True,
                               edge_seeds={1: seed, "1": seed})
    with pytest.raises(GmshBackendError, match="growth distance"):
        GmshBackend().generate(path, candidate, 1., curvature_points=18,
                               minimum_mesh_size=.2, size_gradient=1e-320)
    assert not candidate.exists()


@pytest.mark.parametrize("bore_offset", [0., .4])
def test_revolved_partition_follows_trimmed_cad_on_an_offset_axis(tmp_path, bore_offset):
    from collections import Counter

    path = tmp_path / "flange.brep"
    with _model() as gmsh:
        occ = gmsh.model.occ
        base = occ.addCylinder(12, -11, 4, 0, 0, 3, 8)
        neck = occ.addCylinder(12, -11, 7, 0, 0, 5, 6)
        solid, _ = occ.fuse([(3, base)], [(3, neck)])
        hole = occ.addCylinder(12+bore_offset, -11, 3, 0, 0, 10, 2)
        occ.cut(solid, [(3, hole)])
        occ.synchronize()
        gmsh.write(str(path))
    settings = dict(structured_blocks=True, block_partition="revolved")
    if bore_offset:
        with pytest.raises(GmshBackendError, match="share one revolution axis"):
            GmshBackend().generate(path, tmp_path / "candidate", 1.5, **settings)
        return
    result = GmshBackend().generate(path, tmp_path / "candidate", 1.5, **settings)
    part = result["recipe"]["advanced"]["applied"]["partition"]
    assert part["axis_xy"] == pytest.approx([12, -11])
    assert part["axial_stations"] == pytest.approx([4, 7, 12])
    volume = math.pi * ((8**2-2**2)*3 + (6**2-2**2)*5)
    assert part["original_volume"] == pytest.approx(volume)
    assert part["partition_volume"] == pytest.approx(volume)
    assert part["meridional_bands"] == 3
    children, = part["source_to_block_tags"].values()
    assert len(children) == 12 and set(children) == {v["backend_tag"] for v in result["volumes"]}
    exterior = {s["backend_tag"] for s in result["surfaces"] if len(s["orientation_by_volume"]) == 1}
    assert Counter(n for faces in part["source_to_block_face_tags"].values() for n in faces) == Counter(exterior)


@pytest.mark.parametrize("distribution,factor", [("Progression", 1.25), ("Bump", .2)])
def test_arc_hex20_uses_requested_edge_distribution(tmp_path, distribution, factor):
    path = _curved_block(tmp_path, loft=False)
    edges = _sectors(path)
    source, forward = edges[0]
    intervals = 8
    result = GmshBackend().generate(path, tmp_path / "candidate", 1., structured_blocks=True,
                                    edge_seeds={source: [intervals, distribution, factor]},
                                    element_order=2)
    q = result["quality"]["by_type"]
    assert set(q) == {"quad8", "hex20"} and q["hex20"]["min_det_jacobian"] > 0
    assert q["hex20"]["measure"] == pytest.approx(8*19*math.pi/3, rel=.0004)
    for edge, _ in edges:
        lengths = _arc_lengths(result["assets"]["msh"], edge)
        assert len(lengths) == intervals
        if distribution == "Progression":
            desired = factor if forward else 1 / factor
            assert [b/a for a, b in zip(lengths, lengths[1:])] == pytest.approx(
                [desired] * (intervals-1), rel=1e-4)
        else:
            # Integrate the Gmsh 4.15.2 Bump density for a constant-speed arc.
            # The kth node divides that integral in the ratio k/intervals.
            beta = math.sqrt(1-factor)
            fractions = [(.5 + .5*math.tanh((2*k/intervals-1)*math.atanh(beta))/beta)
                         for k in range(intervals+1)]
            assert [length/sum(lengths) for length in lengths] == pytest.approx(
                [b-a for a, b in zip(fractions, fractions[1:])], abs=1e-5)
    if distribution == "Progression":
        with pytest.raises(GmshBackendError, match="Incompatible seeds"):
            GmshBackend().generate(path, tmp_path / "conflict", 1., structured_blocks=True,
                                   edge_seeds={source: [8, distribution, factor],
                                               edges[1][0]: [9, distribution, factor]})


def test_twisted_tapered_curved_block_and_curvature_tet10(tmp_path):
    path = _curved_block(tmp_path, loft=True)
    for settings, family in (({"structured_blocks": True}, "hex20"),
                             ({"curvature_points": 16, "size_gradient": .3,
                               "minimum_mesh_size": .5}, "tet10")):
        result = GmshBackend().generate(path, tmp_path / family, 1.8, element_order=2, **settings)
        q = result["quality"]
        assert q["by_type"][family]["min_det_jacobian"] > 0
        assert q["by_type"][family]["min_scaled_jacobian"] > 0
        assert q["by_type"][family]["min_sdk_scaled_jacobian"] > 0
        assert q["by_type"][family]["min_sicn"] > 0
        assert q["by_type"][family]["invalid_element_ids"] == []
        assert all(v["relative_error"] < .002 for v in q["by_volume"].values())
        if family == "tet10":
            recipe = result["recipe"]
            assert recipe["effective_minimum_mesh_size"] == .5
            assert recipe["effective_maximum_mesh_size"] == 1.8
            assert recipe["advanced"]["applied"]["curved_surfaces"]
