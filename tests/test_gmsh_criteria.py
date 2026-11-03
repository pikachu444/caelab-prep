"""CAD sizing units plus two dependency-gated actual SDK integration cases."""
import hashlib
from importlib.util import find_spec
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from caelab_prep.adapters import gmsh_backend as backend
from caelab_prep.adapters import gmsh_worker as worker
from caelab_prep.application.meshing_criteria import MeshingCriteria
from caelab_prep.cae_core.errors import PrepError
from test_gmsh_adapter import cad  # existing independent OCP fixture, two shapes


ENTITY = "00000000-0000-4000-8000-000000000001"


@pytest.mark.parametrize("suffix", ["STEP", "stp", "iges", "igs"])
@pytest.mark.parametrize("declaration", [None, "mm"])
def test_normalized_cad_coordinate_units_are_always_mm(suffix, declaration):
    assert backend.cad_coordinate_length_unit("source." + suffix, declaration) == "mm"


@pytest.mark.parametrize("suffix", ["brep", "brp", "xao"])
@pytest.mark.parametrize("declaration", ["mm", "cm", "m"])
def test_unitless_cad_requires_an_explicit_coordinate_declaration(suffix, declaration):
    assert backend.cad_coordinate_length_unit("source." + suffix, declaration) == declaration


@pytest.mark.parametrize("source,declaration", [
    ("source.step", "m"), ("source.stp", "cm"), ("source.iges", "m"), ("source.igs", "cm"),
    ("source.brep", None), ("source.brp", None), ("source.xao", None),
    ("source.step", "unknown"), ("source.brep", "unknown"), ("source.xao", True),
    ("source.stl", "mm"), ("source.geo", "mm"), ("source", "mm"), (None, "mm"),
])
def test_invalid_or_contradictory_coordinate_units_do_not_load_sdk(source, declaration, monkeypatch):
    monkeypatch.setitem(sys.modules, "gmsh", SimpleNamespace(initialize=lambda **k: pytest.fail("Pure unit helper loaded SDK")))
    with pytest.raises(PrepError) as error:
        backend.cad_coordinate_length_unit(source, declaration)
    assert error.value.code == "cad_coordinate_unit"


@pytest.mark.parametrize("suffix,expected", [(".step", "mm"), (".stp", "mm"), (".iges", "mm"),
    (".igs", "mm"), (".brep", "unknown"), (".brp", "unknown"), (".xao", "unknown")])
def test_worker_identity_keeps_legacy_unknown_units_without_forcing_a_declaration(suffix, expected):
    fake = SimpleNamespace(model=SimpleNamespace(getPhysicalGroups=lambda: [],
        addPhysicalGroup=lambda dim, tags: 1, setPhysicalName=lambda *args: None))
    _, _, unit, _ = worker._identity(fake, [1], [], suffix)
    assert unit == expected


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "part.xao"
    path.write_bytes(b"Not opened: request validation precedes SDK loading")
    return path


@pytest.mark.parametrize("minimum", [0, -1, 1.6, True, False, float("nan"), float("inf"), -float("inf"), "bad", 10**1000])
def test_invalid_minimum_is_rejected_before_job_or_sdk(source, tmp_path, monkeypatch, minimum):
    monkeypatch.setattr(backend.subprocess, "Popen", lambda *a, **k: pytest.fail("Invalid request launched a worker"))
    monkeypatch.setitem(sys.modules, "gmsh", SimpleNamespace(initialize=lambda **k: pytest.fail("Invalid request initialized SDK")))
    with pytest.raises(backend.GmshBackendError) as host_error:
        backend.GmshBackend().generate(source, tmp_path / "host", 1.5, minimum_mesh_size=minimum)
    assert host_error.value.code == "invalid_request" and not (tmp_path / "host").exists()
    with pytest.raises(worker.WorkerFailure) as worker_error:
        worker.generate({"source": str(source), "output_dir": str(tmp_path / "worker"),
                         "mesh_size": 1.5, "dimension": 3, "minimum_mesh_size": minimum})
    assert worker_error.value.code == "invalid_request" and not (tmp_path / "worker").exists()


def test_local_below_explicit_minimum_rejected_at_both_boundaries(source, tmp_path, monkeypatch):
    monkeypatch.setattr(backend.subprocess, "Popen", lambda *a, **k: pytest.fail("Contradiction launched a worker"))
    with pytest.raises(backend.GmshBackendError, match="below minimum_mesh_size"):
        backend.GmshBackend().generate(source, tmp_path / "host", 1.5,
            minimum_mesh_size=.25, local_sizes={ENTITY: .2})
    with pytest.raises(worker.WorkerFailure, match="below minimum_mesh_size"):
        worker.generate({"source": str(source), "output_dir": str(tmp_path / "worker"), "mesh_size": 1.5,
                         "dimension": 3, "minimum_mesh_size": .25, "local_sizes": {ENTITY: .2}})
    assert not (tmp_path / "host").exists() and not (tmp_path / "worker").exists()


@pytest.mark.parametrize("criterion", ["washer_rim_divisions", "fillet_suppression_threshold", "unknown_criterion"])
def test_unimplemented_criteria_are_explicitly_rejected(source, tmp_path, criterion):
    with pytest.raises(TypeError):
        backend.GmshBackend().generate(source, tmp_path / "host", 1.5, **{criterion: 2})
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source": str(source), "output_dir": str(tmp_path / "worker"),
                         "mesh_size": 1.5, "dimension": 3, criterion: 2})
    assert error.value.code == "unsupported_criteria" and error.value.details["criteria"] == [criterion]
    assert not (tmp_path / "worker").exists()


def test_cad_minimum_does_not_extend_surface_volume_recipe(source, tmp_path):
    with pytest.raises(TypeError):
        backend.GmshBackend().generate_surface_volume(source, tmp_path / "host", 1.5,
                                                     length_unit="mm", minimum_mesh_size=.25)
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": "closed_tri_surface", "minimum_mesh_size": .25})
    assert error.value.code == "unsupported_criteria"


@pytest.mark.parametrize("criterion", ["washer_rim_divisions", "fillet_suppression_threshold",
                                      "washer_width", "washer_layers"])
def test_reserved_unimplemented_criteria_cannot_be_ignored_by_surface_dispatch(criterion):
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": "closed_tri_surface", criterion: 2})
    assert error.value.code == "unsupported_criteria" and error.value.details["criteria"] == [criterion]


def _fake_worker_context(monkeypatch, *, known_unit="mm"):
    values, events, field_calls = {}, [], []
    def set_number(key, value): values[key] = value; events.append(("set", key, value))
    def get_number(key): events.append(("get", key)); return values[key]
    class Fields:
        next_id = 0
        def add(self, kind): self.next_id += 1; field_calls.append(("add", kind)); return self.next_id
        def setNumbers(self, *args): field_calls.append(("numbers", *args))
        def setNumber(self, *args): field_calls.append(("number", *args))
        def setAsBackgroundMesh(self, tag): field_calls.append(("background", tag))
    class Mesh:
        field = Fields()
        def generate(self, dimension): events.append(("generate", dimension))
        def getNodes(self, *args, **kwargs): return [1, 2, 3, 4], [0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1.], []
        def getElements(self, dim, tag): return ([2], [[11]], [[1, 3, 2]]) if dim == 2 else ([4], [[12]], [[1, 2, 3, 4]])
        def getElementProperties(self, typ): return ("Triangle", 2, 1, 3, [], 3) if typ == 2 else ("Tetrahedron", 3, 1, 4, [], 4)
    fake = SimpleNamespace(__version__="4.15.2", libpath="mock only; no native SDK loaded",
        initialize=lambda **kwargs: None, isInitialized=lambda: True, finalize=lambda: events.append(("finalize",)),
        logger=SimpleNamespace(start=lambda: None, get=lambda: []),
        option=SimpleNamespace(setNumber=set_number, getNumber=get_number, setString=lambda *args: None),
        open=lambda path: None, write=lambda path: Path(path).write_bytes(b"mock CAD asset"),
        model=SimpleNamespace(add=lambda name: None, mesh=Mesh(), getEntities=lambda dim: [(dim, 1)],
            getBoundary=lambda *args, **kwargs: [(2, 1)], getType=lambda *args: "Plane",
            getBoundingBox=lambda *args: [0., 0., 0., 1., 1., 1.],
            occ=SimpleNamespace(synchronize=lambda: None, getMass=lambda dim, tag: .5 if dim == 2 else 1/6,
                                getCenterOfMass=lambda *args: [1/3, 1/3, 0.])))
    monkeypatch.setitem(sys.modules, "gmsh", fake)
    monkeypatch.setattr(worker, "_prepare_interfaces", lambda *args: ({"operation": "none"}, {}))
    monkeypatch.setattr(worker, "_identity", lambda *args: (
        "00000000-0000-4000-8000-000000000010", 1, known_unit, {(2, 1): ENTITY, (3, 1): "00000000-0000-4000-8000-000000000002"}))
    monkeypatch.setattr(worker, "_check_mesh_interfaces", lambda *args: [])
    requests = []
    def actual_worker(self, request, *args): requests.append(request); return worker.generate(request)
    monkeypatch.setattr(backend.GmshBackend, "_run", actual_worker)
    return requests, events, field_calls


@pytest.mark.parametrize("minimum,locals_,effective,origin", [
    (None, {}, 1.5, "legacy_target"), (None, {ENTITY: .5}, .5, "derived_local"),
    (.25, {}, .25, "explicit"), (.25, {ENTITY: .5}, .25, "explicit"),
    (.5, {ENTITY: .5}, .5, "explicit"), (1.5, {}, 1.5, "explicit"),
])
def test_real_worker_option_sequence_and_metadata_with_fake_sdk(source, tmp_path, monkeypatch, minimum, locals_, effective, origin):
    requests, events, field_calls = _fake_worker_context(monkeypatch)
    result = backend.GmshBackend().generate(source, tmp_path / "jobs", 1.5,
        minimum_mesh_size=minimum, local_sizes=locals_)
    assert requests[0]["minimum_mesh_size"] == minimum
    recipe = result["recipe"]
    assert recipe["minimum_mesh_size"] == minimum and recipe["minimum_mesh_size_origin"] == origin
    assert recipe["effective_minimum_mesh_size"] == effective and recipe["effective_maximum_mesh_size"] == 1.5
    assert recipe["sdk_size_options"] == {"Mesh.MeshSizeMin": effective, "Mesh.MeshSizeMax": 1.5}
    assert events.index(("get", "Mesh.MeshSizeMin")) > events.index(("generate", 3))
    assert events.index(("get", "Mesh.MeshSizeMax")) > events.index(("generate", 3))
    if minimum is not None:
        assert [e[2] for e in events if e[:2] == ("set", "Mesh.MeshSizeMin")] == [minimum]
    if locals_:
        assert ("add", "Constant") in field_calls and ("add", "Min") in field_calls
        assert ("number", 1, "VIn", .5) in field_calls and ("number", 1, "VOut", 1.5) in field_calls
    assert set(result["assets"]) == {"xao", "msh", "metadata"}
    assert json.loads(Path(result["assets"]["metadata"]).read_text()) == result


@pytest.mark.parametrize("known_unit,expected_unit", [("mm", "cm"), ("mm", "mm"),
    ("unknown", "cm"), ("mm", None), ("cm", "m"), ("cm", "cm")])
def test_worker_checks_restored_unit_before_meshing_without_relabeling_unknown(source, tmp_path, monkeypatch, known_unit, expected_unit):
    original = source.read_bytes()
    requests, events, _ = _fake_worker_context(monkeypatch, known_unit=known_unit)
    if expected_unit is not None and known_unit != "unknown" and known_unit != expected_unit:
        with pytest.raises(worker.WorkerFailure) as error:
            backend.GmshBackend().generate(source, tmp_path / "jobs", 1.5,
                minimum_mesh_size=.25, expected_coordinate_length_unit=expected_unit)
        assert error.value.code == "unit_mismatch"
        assert error.value.details == {"expected_coordinate_length_unit": expected_unit,
                                      "actual_coordinate_length_unit": known_unit}
        assert ("generate", 3) not in events
        assert not list((tmp_path / "jobs").glob("*/mesh.msh"))
        assert not list((tmp_path / "jobs").glob("*/geometry.xao"))
        assert not list((tmp_path / "jobs").glob("*/metadata.json"))
    else:
        result = backend.GmshBackend().generate(source, tmp_path / "jobs", 1.5,
            minimum_mesh_size=.25, expected_coordinate_length_unit=expected_unit)
        assert ("generate", 3) in events and result["length_unit"] == known_unit
        assert result["recipe"]["expected_coordinate_length_unit"] == expected_unit
    if expected_unit is None:
        assert "expected_coordinate_length_unit" not in requests[0]
    else:
        assert requests[0]["expected_coordinate_length_unit"] == expected_unit
    assert source.read_bytes() == original


@pytest.mark.parametrize("value", [True, "unknown", "", []])
def test_invalid_expected_coordinate_unit_rejects_before_job_or_sdk(source, tmp_path, monkeypatch, value):
    monkeypatch.setattr(backend.subprocess, "Popen", lambda *a, **k: pytest.fail("Invalid unit launched worker"))
    with pytest.raises(backend.GmshBackendError) as error:
        backend.GmshBackend().generate(source, tmp_path / "jobs", 1.5, expected_coordinate_length_unit=value)
    assert error.value.code == "invalid_request" and not (tmp_path / "jobs").exists()
    with pytest.raises(worker.WorkerFailure) as worker_error:
        worker.generate({"source": str(source), "output_dir": str(tmp_path / "worker"), "mesh_size": 1.5,
                         "dimension": 3, "expected_coordinate_length_unit": value})
    assert worker_error.value.code == "invalid_request" and not (tmp_path / "worker").exists()


@pytest.mark.parametrize("source_kind", ["closed_tri_surface", "structured_recipe"])
def test_non_cad_dispatch_explicitly_rejects_coordinate_unit_expectations(source_kind):
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": source_kind, "expected_coordinate_length_unit": "mm"})
    assert error.value.code == "unsupported_criteria"


@pytest.mark.skipif(find_spec("OCP") is None or find_spec("gmsh") is None,
                    reason="Actual CAD criteria integration requires existing OCP and Gmsh test dependencies")
def test_persisted_profile_reaches_actual_sdk_and_audits_complete_output(cad, tmp_path):
    """Run in CAD-worker CI; this is sizing wiring, not feature recognition F1."""
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    source_hash = hashlib.sha256(cad.read_bytes()).hexdigest()
    criteria_file = tmp_path / "minimum.criteria.json"
    criteria = MeshingCriteria("mm", 1.5, .25)
    criteria.save(criteria_file)
    restored = MeshingCriteria.load(criteria_file)
    assert restored == criteria
    kwargs = restored.gmsh_kwargs(source_path=cad)
    result = backend.GmshBackend().generate(cad, tmp_path / "assets", **kwargs)
    recipe = result["recipe"]
    assert recipe["global_size"] == 1.5 and recipe["minimum_mesh_size"] == .25
    assert recipe["minimum_mesh_size_origin"] == "explicit"
    assert recipe["expected_coordinate_length_unit"] == "mm"
    assert recipe["effective_minimum_mesh_size"] == .25 and recipe["effective_maximum_mesh_size"] == 1.5
    assert recipe["sdk_size_options"] == {"Mesh.MeshSizeMin": .25, "Mesh.MeshSizeMax": 1.5}
    assert result["source"]["sha256"] == source_hash and result["sdk_error_count"] == 0
    assert hashlib.sha256(Path(result["source"]["captured_path"]).read_bytes()).hexdigest() == source_hash
    msh = Path(result["assets"]["msh"])
    assert msh.is_file() and msh.stat().st_size > 0 and Path(result["assets"]["xao"]).is_file()
    mesh_bytes = msh.read_bytes()
    candidate = read_mesh_candidate(result)  # existing independent native SDK reader
    assert {cell.dimension for cell in candidate.cells} == {0, 1, 2, 3}
    audit = restored.audit_minimum_edges(candidate.nodes, candidate.cells, coordinate_length_unit="mm")
    assert len(audit["cells"]) == len(candidate.cells)
    assert {row["id"] for row in audit["cells"]} == {cell.id for cell in candidate.cells}
    point_ids = {cell.id for cell in candidate.cells if cell.dimension == 0}
    assert point_ids and set(audit["skipped_point_ids"]) == point_ids
    assert audit["supported_edge_bearing_cells"] == len(candidate.cells) - len(point_ids)
    assert audit["unsupported_ids"] == audit["invalid_ids"] == []
    assert audit["passed"] and audit["below_minimum_ids"] == []
    assert audit["modifications"] == 0 and audit["minimum_observed_length"] >= .25
    # Only these fixed inputs are checked. SDK targets are not universal edge bounds.
    assert msh.read_bytes() == mesh_bytes and hashlib.sha256(cad.read_bytes()).hexdigest() == source_hash
