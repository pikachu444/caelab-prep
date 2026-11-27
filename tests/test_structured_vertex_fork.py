"""Shared-vertex forks cross the real meshing, project, and Starter boundaries."""

from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import pytest

from caelab_prep.application.structured_geometry import MAX_RECIPE_BYTES
from caelab_prep.application.structured_mesh import (
    fork_vertex_recipe,
    generate_structured_mesh,
    read_recipe_input,
)
from caelab_prep.cae_core.errors import PrepError
from test_structured_adoption import _native, _session, _state


def _case(case_id):
    path = Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json"
    return next(case for case in json.loads(path.read_text(encoding="utf-8")) if case["id"] == case_id)


def _source(folder, spec):
    path = folder / "original.json"
    path.write_bytes(json.dumps(spec, separators=(",", ":")).encode("utf-8"))
    return read_recipe_input(path)


def _shared_edit(base):
    # Move b toward a within the oblique source plane of both holdouts.
    a, b = (base["vertices"][key] for key in ("a", "b"))
    return {"b": [end + 0.05 * (start - end) for start, end in zip(a, b)]}


@pytest.mark.parametrize("case_id", ["Q-D2", "H-D2"])
def test_vertex_fork_preserves_base_and_source(case_id, tmp_path):
    spec = _case(case_id)["input"]
    base, source = _source(tmp_path, spec)
    edits = _shared_edit(base)
    destination = tmp_path / "fork.json"

    assert fork_vertex_recipe(base, source, destination, vertex_edits=edits) == str(destination.resolve())
    fork, digest = read_recipe_input(destination)
    expected = deepcopy(spec)
    expected["vertices"].update(edits)
    assert fork == expected
    assert base == spec
    assert digest.sha256 != source.sha256
    assert sha256(Path(source.path).read_bytes()).hexdigest() == source.sha256


@pytest.mark.parametrize("case_id", ["Q-D2", "H-D2"])
def test_forked_candidate_mesh_project_and_starter_round_trip(case_id, tmp_path):
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable")
    case = _case(case_id)
    base, source = _source(tmp_path, case["input"])
    edits = _shared_edit(base)
    vector = [1.05 * component for component in base["vector"]] if base["mode"] == "hex" else None
    path = fork_vertex_recipe(base, source, tmp_path / "fork.json", vertex_edits=edits, vector=vector)
    fork, _ = read_recipe_input(path)
    if vector is not None:
        assert fork["vector"] == vector
        assert fork["layers"] == base["layers"]
    candidate = generate_structured_mesh(fork, tmp_path / "assets", recipe_path=path)
    native = candidate.to_native_mesh()
    counts = [patch["divisions"] for patch in base["patches"]]
    elements = sum(nx * ny for nx, ny in counts) * base.get("layers", 1)
    assert len(native.elements) == elements == case["expectation"]["elements"]
    assert len(native.nodes) == case["expectation"]["active_nodes"]
    assert native.length_unit == base["unit"]
    assert candidate.quality.passed
    if base["mode"] == "hex":
        assert candidate.quality.minimum_scaled_jacobian >= 0.25
    else:
        assert candidate.quality.minimum_scaled_jacobian > 0.30

    assert len(native.parts) == 2
    left, right = [
        {node for cell in native.elements if cell.part_uuid == part.uuid for node in cell.node_ids}
        for part in native.parts
    ]
    assert len(left | right) == len(native.nodes)
    assert len(left & right) == case["expectation"]["shared_nodes"]
    assert any(node.id in left & right and node.xyz == pytest.approx(edits["b"]) for node in native.nodes)

    session, material, section = _session(native, native.length_unit)
    before = _state(session)[1]
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    project = tmp_path / "fork.caeprep"
    session.save_project(project)
    reopened = type(session)()
    reopened.open_project(project)
    assert _state(reopened)[1] == _state(session)[1]
    session.undo()
    assert _state(session)[1] == before

    starter = tmp_path / "fork_0000.rad"
    reopened.export_solver_inputs(starter, end_time=.01, output_interval=.001)
    nodes, cells, parts, _ = _native(starter.read_bytes())
    assert len(nodes) == len(native.nodes) and len(cells) == elements
    assert len(parts) == 2 and set(parts.values()) == {(207, 41)}
    part_ids = {card["id"]: int(card["keyword"].split("/")[2])
                for card in reopened.list_cards() if card["keyword"].startswith("/PART/")}
    for node in native.nodes:
        assert nodes[adopted["node_id_map"][node.id]] == pytest.approx(node.xyz, rel=1e-12, abs=1e-12)
    for cell in native.elements:
        assert cells[adopted["element_id_map"][cell.id]] == (
            part_ids[adopted["part_id_map"][cell.part_uuid]],
            tuple(adopted["node_id_map"][node] for node in cell.node_ids),
        )
    readback = type(session)()
    readback.open_rad(starter)
    assert readback.describe()["element_count"] == elements
    assert readback._model_resource(None).unit_context()["global"]["length"] == base["unit"]
    assert readback._solver_work_units()["length"] == base["unit"]
    assert sha256(Path(source.path).read_bytes()).hexdigest() == source.sha256


@pytest.mark.parametrize("edits,message", [
    ({"missing": [0, 0, 0]}, "Unknown vertex ID"),
    ({"b": [19, -7, 26]}, "non-planar face"),
    ({"b": [10.2, -7, 18.4]}, "strict convex"),
    ({"b": [float("nan"), -7, 25]}, "Out of range float"),
    ({"b": [19, -7]}, "finite xyz"),
    ({}, "nonempty vertex edit"),
])
def test_invalid_vertex_edits_create_no_file(edits, message, tmp_path):
    base, source = _source(tmp_path, _case("Q-D2")["input"])
    destination = tmp_path / "fork.json"
    with pytest.raises(PrepError, match=message) as error:
        fork_vertex_recipe(base, source, destination, vertex_edits=edits)
    assert error.value.code == "invalid_recipe"
    assert not destination.exists()


def test_vertex_fork_refuses_existing_destination_and_original(tmp_path):
    base, source = _source(tmp_path, _case("Q-D2")["input"])
    destination = tmp_path / "fork.json"
    destination.write_bytes(b"existing recipe")
    for path in (destination, Path(source.path)):
        before = path.read_bytes()
        with pytest.raises(PrepError) as error:
            fork_vertex_recipe(base, source, path, vertex_edits=_shared_edit(base))
        assert error.value.code == "destination_exists"
        assert path.read_bytes() == before


def test_vertex_fork_refuses_stale_source_digest(tmp_path):
    base, source = _source(tmp_path, _case("Q-D2")["input"])
    path = Path(source.path)
    path.write_bytes(path.read_bytes() + b"\n")
    destination = tmp_path / "fork.json"
    with pytest.raises(PrepError) as error:
        fork_vertex_recipe(base, source, destination, vertex_edits=_shared_edit(base))
    assert error.value.code == "candidate_changed"
    assert not destination.exists()


def test_vertex_fork_refuses_single_patch(tmp_path):
    base, source = _source(tmp_path, _case("Q-N3")["input"])
    destination = tmp_path / "fork.json"
    with pytest.raises(PrepError) as error:
        fork_vertex_recipe(base, source, destination, vertex_edits={"b": [0, 0, 0]})
    assert error.value.code == "invalid_recipe"
    assert error.value.message == "Use fork_geometry_recipe for single-patch recipes."
    assert not destination.exists()


@pytest.mark.parametrize("case_id,vector,message", [
    ("Q-D2", [0, 0, 1], "no sweep vector"),
    ("H-D2", [-2.144, 0.608, -3.06], "positive extrusion"),
    ("H-D2", [0, 1], "finite xyz"),
])
def test_vertex_fork_refuses_invalid_sweep_vector(case_id, vector, message, tmp_path):
    base, source = _source(tmp_path, _case(case_id)["input"])
    destination = tmp_path / "fork.json"
    with pytest.raises(PrepError, match=message) as error:
        fork_vertex_recipe(base, source, destination, vertex_edits=_shared_edit(base), vector=vector)
    assert error.value.code == "invalid_recipe"
    assert not destination.exists()


def test_vertex_fork_refuses_oversize_serialization(tmp_path):
    spec = _case("Q-D2")["input"]
    spec["name"] = ""
    size = len(json.dumps(spec, separators=(",", ":")).encode("utf-8"))
    spec["name"] = "x" * (MAX_RECIPE_BYTES - size)
    base, source = _source(tmp_path, spec)
    assert Path(source.path).stat().st_size == MAX_RECIPE_BYTES
    destination = tmp_path / "fork.json"
    with pytest.raises(PrepError, match="serialized") as error:
        fork_vertex_recipe(base, source, destination, vertex_edits=_shared_edit(base))
    assert error.value.code == "invalid_recipe"
    assert not destination.exists()
