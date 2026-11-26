"""Structured L, T and ring recipes through Gmsh, project and Radioss readback."""

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
from importlib.util import find_spec
import json
from pathlib import Path

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.structured_geometry import CONTRACT, validate_recipe
from caelab_prep.application.structured_mesh import (
    fork_vertex_recipe,
    generate_structured_mesh,
    read_recipe_input,
)
from caelab_prep.cae_core.errors import PrepError
from test_structured_adoption import _native, _session, _state


def _square(x, y):
    return [(x, y), (x + 2, y), (x + 2, y + 2), (x, y + 2)]


def _vertex_id(point):
    x, y = point
    return f"{x},{y}"


def _recipe(mode, quads, divisions=(2, 2)):
    spec = dict(mode=mode, unit="cm" if mode == "quad" else "mm",
                vertices={_vertex_id(p): [*p, 0] for quad in quads for p in quad},
                patches=[dict(id=f"patch-{i + 1}", corners=[_vertex_id(p) for p in quad],
                              divisions=list(divisions)) for i, quad in enumerate(quads)])
    if mode == "hex":
        spec.update(vector=[.25, .125, 2], layers=2)
    return spec


L = [_square(0, 0), _square(2, 0), _square(0, 2)]
T = [_square(0, 2), _square(2, 2), _square(4, 2), _square(2, 0)]
OUTER = [(0, 0), (6, 0), (6, 6), (0, 6)]
INNER = [(2, 2), (4, 2), (4, 4), (2, 4)]
RING = [[OUTER[i], OUTER[(i + 1) % 4], INNER[(i + 1) % 4], INNER[i]] for i in range(4)]

QUAD_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0))
HEX_FACES = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def _assert_mesh(spec, candidate, counts2d, interface_edges):
    cells2d, nodes2d, shared2d = counts2d
    layers = spec.get("layers", 1)
    solid = spec["mode"] == "hex"
    planes = layers + 1 if solid else 1
    elements, active_nodes, shared_nodes = cells2d * layers, nodes2d * planes, shared2d * planes
    interface_cells = 2 * len(interface_edges) * layers
    metrics = json.loads(candidate.quality.details_json)
    assert candidate.backend_version == "4.15.2"
    assert candidate.quality.passed
    assert candidate.quality.minimum_signed_jacobian > 0
    if solid:
        assert candidate.quality.minimum_scaled_jacobian >= CONTRACT["hex_min_sampled_scaled_jacobian"]
        assert candidate.quality.maximum_edge_aspect_ratio <= CONTRACT["hex_max_edge_aspect_ratio"]
    else:
        assert candidate.quality.minimum_scaled_jacobian >= CONTRACT["quad_min_corner_signed_scaled_jacobian"]
        assert candidate.quality.maximum_edge_aspect_ratio <= CONTRACT["quad_max_edge_aspect_ratio"]
    assert metrics["elements"] == elements
    assert metrics["active_nodes"] == active_nodes
    assert metrics["shared_nodes"] == shared_nodes
    assert metrics["shared_boundary_cells"] == interface_cells
    assert metrics["hanging_nodes"] == 0

    native = candidate.to_native_mesh()
    assert native.length_unit == spec["unit"]
    assert [part.name for part in native.parts] == [patch["id"] for patch in spec["patches"]]
    assert len(native.nodes) == len({node.xyz for node in native.nodes}) == active_nodes
    assert len(native.elements) == len({frozenset(cell.node_ids) for cell in native.elements}) == elements
    assert not native.unused_node_ids

    nodes_by_part, sides = defaultdict(set), defaultdict(list)
    for cell in native.elements:
        assert len(cell.node_ids) == (8 if solid else 4)
        nodes_by_part[cell.part_uuid].update(cell.node_ids)
        for indices in HEX_FACES if solid else QUAD_EDGES:
            side = frozenset(cell.node_ids[i] for i in indices)
            sides[side].append(cell.part_uuid)
    assert all(len(owners) <= 2 for owners in sides.values())
    interfaces = [side for side, owners in sides.items() if len(set(owners)) == 2]
    assert len(interfaces) == interface_cells
    uses = Counter(node for ids in nodes_by_part.values() for node in ids)
    shared = {node for node, uses in uses.items() if uses >= 2}
    assert shared == set().union(*interfaces)
    assert len(shared) == shared_nodes
    xyz = {node.id: node.xyz for node in native.nodes}
    # Each declared interface is split in two, then swept by the same vector as its patches.
    expected = set()
    for edge in interface_edges:
        a, b = (spec["vertices"][_vertex_id(p)] for p in edge)
        for k in range(planes):
            offset = [k / layers * v for v in spec.get("vector", (0, 0, 0))]
            for s in (0, .5, 1):
                expected.add(tuple((1 - s) * x + s * y + z for x, y, z in zip(a, b, offset)))
    assert len(expected) == shared_nodes
    for point in expected:
        wanted = pytest.approx(point, abs=metrics["coordinate_tolerance"])
        assert sum(xyz[n] == wanted for n in shared) == 1
    return native, nodes_by_part, metrics


def _model_state(session):
    return _state(session)[1], {rid: resource.snapshot() for rid, resource in session.document.resources.items()}


@pytest.mark.parametrize("mode", ["quad", "hex"])
@pytest.mark.parametrize("quads,divisions,counts,edges,corner", [
    pytest.param(L, (2, 2), (12, 21, 5), [((2, 0), (2, 2)), ((0, 2), (2, 2))], (2, 2), id="L-bracket"),
    pytest.param(T, (2, 2), (16, 27, 7), [((2, 2), (2, 4)), ((4, 2), (4, 4)), ((2, 2), (4, 2))],
                 (2, 2), id="T-gusset"),
    pytest.param(RING, (3, 2), (24, 36, 12), list(zip(OUTER, INNER)), (2, 2), id="hollow-ring"),
])
def test_multipatch_round_trip(mode, quads, divisions, counts, edges, corner, tmp_path, record_property):
    if find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable")
    spec = _recipe(mode, quads, divisions)
    original = tmp_path / "original.json"
    original.write_text(json.dumps(spec), encoding="utf-8")
    base, source = read_recipe_input(original)
    layers = spec.get("layers", 1)
    planes = layers + 1 if mode == "hex" else 1
    admission = validate_recipe(base)["expectation"]
    assert admission["elements"] == counts[0] * layers
    assert admission["active_nodes"] == counts[1] * planes
    assert admission["shared_nodes"] == counts[2] * planes
    assert admission["shared_boundary_cells"] == 2 * len(edges) * layers
    assets = tmp_path / "assets"
    candidate = generate_structured_mesh(base, assets, recipe_path=original)
    _, _, metrics = _assert_mesh(base, candidate, counts, edges)
    record_property("original_mesh", json.dumps(metrics))

    vertex = _vertex_id(corner)
    moved = [corner[0] + .125, corner[1] + .25, 0]
    destination = tmp_path / "fork.json"
    assert fork_vertex_recipe(base, source, destination, vertex_edits={vertex: moved}) == str(destination.resolve())
    fork, fork_digest = read_recipe_input(destination)
    assert base == spec
    assert fork == dict(spec, vertices={**spec["vertices"], vertex: moved})
    assert fork_digest.sha256 != source.sha256
    edited = generate_structured_mesh(fork, assets, recipe_path=destination)
    native, nodes_by_part, metrics = _assert_mesh(fork, edited, counts, edges)
    record_property("fork_mesh", json.dumps(metrics))
    matches = [n.id for n in native.nodes if n.xyz == pytest.approx(moved)]
    assert len(matches) == 1
    assert all(n.xyz != pytest.approx([*corner, 0]) for n in native.nodes)
    assert {part.name for part in native.parts if matches[0] in nodes_by_part[part.uuid]} == {
        patch["id"] for patch in spec["patches"] if vertex in patch["corners"]
    }

    session, material, section = _session(native, native.length_unit)
    before = _model_state(session)
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    project = tmp_path / "fork.caeprep"
    session.save_project(project)
    reopened = PrepSession()
    reopened.open_project(project)
    assert reopened.document.id == session.document.id
    assert reopened.document.revision == session.document.revision
    assert _model_state(reopened) == _model_state(session)
    archived, = reopened.structured_mesh_recipes()
    extracted = reopened.export_structured_recipe(archived["id"], tmp_path / "extracted")
    assert Path(extracted["recipe_path"]).read_bytes() == destination.read_bytes()
    session.undo()
    assert _model_state(session) == before

    starter = tmp_path / "fork_0000.rad"
    reopened.export_solver_inputs(starter, end_time=.01, output_interval=.001)
    raw = starter.read_bytes()
    nodes, cells, parts, _ = _native(raw)
    keywords = raw.splitlines()
    assert sum(line.startswith(b"/PART/") for line in keywords) == len(parts) == len(quads)
    family = b"/BRICK/" if mode == "hex" else b"/SHELL/"
    other_family = b"/SHELL/" if mode == "hex" else b"/BRICK/"
    assert any(line.startswith(family) for line in keywords)
    assert all(not line.startswith(other_family) for line in keywords)
    assert len(nodes) == counts[1] * planes
    assert len(cells) == counts[0] * layers
    part_ids = {card["id"]: int(card["keyword"].split("/")[2])
                for card in reopened.list_cards() if card["keyword"].startswith("/PART/")}
    for node in native.nodes:
        assert nodes[adopted["node_id_map"][node.id]] == pytest.approx(node.xyz, rel=1e-12, abs=1e-12)
    for cell in native.elements:
        assert cells[adopted["element_id_map"][cell.id]] == (
            part_ids[adopted["part_id_map"][cell.part_uuid]],
            tuple(adopted["node_id_map"][node] for node in cell.node_ids),
        )
    readback = PrepSession()
    readback.open_rad(starter)
    assert readback.describe()["element_count"] == counts[0] * layers
    assert readback._model_resource(None).unit_context()["global"]["length"] == spec["unit"]
    assert readback._solver_work_units()["length"] == spec["unit"]
    assert sha256(original.read_bytes()).hexdigest() == source.sha256


@pytest.mark.parametrize("quads, message", [
    pytest.param([*L[:2], _square(8, 8)], "one connected component", id="disconnected"),
    pytest.param([*L, L[0]], "non-manifold shared edge", id="non-manifold"),
    pytest.param([_square(2 * i, 0) for i in range(33)], "2 to 32 patches", id="too-many-patches"),
    pytest.param([*L, [(0, 0), (3, 0), (2, 2), (0, 3)]],
                 "only the declared edge vertices", id="shared-diagonal"),
    pytest.param([L[0], L[2], [(0, 0), (2, 0), (2, 2), (0, 3)]],
                 "only the declared edge vertices", id="three-shared-vertices"),
])
def test_invalid_patch_topology_creates_no_files(quads, message, tmp_path):
    with pytest.raises(PrepError, match=message) as error:
        generate_structured_mesh(_recipe("quad", quads), tmp_path / "assets")
    assert error.value.code == "invalid_recipe"
    assert not list(tmp_path.iterdir())


def test_mismatched_divisions_create_no_files(tmp_path):
    spec = _recipe("hex", L)
    spec["patches"][2]["divisions"][0] += 1
    with pytest.raises(PrepError, match="shared-edge division counts must agree"):
        generate_structured_mesh(spec, tmp_path / "assets")
    assert not list(tmp_path.iterdir())


def test_nonplanar_shared_vertex_fork_creates_no_files(tmp_path):
    original = tmp_path / "original.json"
    original.write_text(json.dumps(_recipe("hex", RING)), encoding="utf-8")
    base, source = read_recipe_input(original)
    before = deepcopy(base)
    with pytest.raises(PrepError, match="non-planar face"):
        fork_vertex_recipe(base, source, tmp_path / "fork.json", vertex_edits={"2,2": [2, 2, .25]})
    assert list(tmp_path.iterdir()) == [original]
    assert base == before
    assert sha256(original.read_bytes()).hexdigest() == source.sha256


@pytest.mark.parametrize("mode", ["quad", "hex"])
def test_maximum_patch_count_generates_mesh(mode, tmp_path):
    if find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable")
    spec = _recipe(mode, [_square(2 * i, 0) for i in range(32)], divisions=(1, 1))
    candidate = generate_structured_mesh(spec, tmp_path)
    native = candidate.to_native_mesh()
    assert len(native.parts) == 32
    assert len(native.elements) == 32 * spec.get("layers", 1)
    assert len(native.nodes) == 66 * (spec["layers"] + 1 if mode == "hex" else 1)
