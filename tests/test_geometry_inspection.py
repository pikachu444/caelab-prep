"""Raw CAD unit contracts and two dependency-gated actual SDK CI cases."""
import hashlib
from importlib.util import find_spec
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from caelab_prep.adapters import gmsh_backend as backend
from caelab_prep.adapters import gmsh_worker as worker
from test_surface_tet_backend import Process
from test_gmsh_adapter import cad  # existing independent OCP fixture, two shapes


RESOURCE = "00000000-0000-4000-8000-000000000001"
FACE1 = "00000000-0000-4000-8000-000000000002"
FACE2 = "00000000-0000-4000-8000-000000000003"
VOLUME = "00000000-0000-4000-8000-000000000004"


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "prepared.xao"
    path.write_bytes(b"Mock CAD source remains byte exact")
    return path


def fake_sdk(monkeypatch, *, unit="mm", trim_count=0):
    events = []
    groups = {1: (3, [5], f"caelab:geometry:{RESOURCE}:r2:unit:{unit}"),
              2: (2, [1], f"caelab:surface:{FACE1}"), 3: (2, [2], f"caelab:surface:{FACE2}"),
              4: (3, [5], f"caelab:volume:{VOLUME}")}
    def boundary(dim_tags, *, combined, oriented):
        assert combined is False
        dim, tag = dim_tags[0]
        if dim == 3:
            assert oriented is True
            return [(2, -1), (2, 2)]
        assert dim == 1 and oriented is False
        return {11: [(0, 201), (0, 201)], 12: [], 13: [(0, 202), (0, 203)]}[tag]
    def properties(dim, tag):
        if dim == 2:
            return ([], [0., 0., 0., 0., 0., 1., 2.]) if tag == 1 else ([], [0., 0., 1., -3.])
        return [], []
    def get_value(dim, tag, uv):
        if dim == 2:
            return [-2., 0., 1.5] if tag == 1 else [0., 0., 3.]
        assert dim == 0 and uv == []
        return {201: [2., 0., 0.], 202: [2., 0., 0.], 203: [2., 0., 3.]}[tag]
    def inside(dim, tag, uv, *, parametric):
        assert dim == 2 and parametric is True  # volume probes are forbidden in GI1
        events.append(("trim", tag, tuple(uv)))
        return 1 if tag == 1 else trim_count
    def write(path):
        assert Path(path).suffix == ".xao"
        events.append(("write_xao", str(path)))
        Path(path).write_bytes(b"mock exported CAD, no mesh")
    def fail_mesh(*args, **kwargs): pytest.fail("Geometry inspection attempted mesh generation or inventory")
    model = SimpleNamespace(add=lambda name: events.append(("model", name)),
        getPhysicalGroups=lambda: [(dim, tag) for tag, (dim, _, _) in groups.items()],
        getPhysicalName=lambda dim, tag: groups[tag][2],
        getEntitiesForPhysicalGroup=lambda dim, tag: groups[tag][1],
        getEntities=lambda dim: {1: [(1, 11), (1, 12), (1, 13)], 2: [(2, 1), (2, 2)], 3: [(3, 5)]}[dim],
        getBoundary=boundary, getEntityProperties=properties,
        getType=lambda dim, tag: ({1: "Cylinder", 2: "Plane"}[tag] if dim == 2 else "Circle" if tag != 13 else "Line"),
        getBoundingBox=lambda dim, tag: [-2., -2., 0., 2., 2., 3.],
        getParametrizationBounds=lambda dim, tag: ([0., 0.], [6., 3.]) if dim == 2 else ([0.], [6.]),
        getValue=get_value, getNormal=lambda tag, uv: [-1., 0., 0.] if tag == 1 else [0., 0., 1.],
        isInside=inside, getAdjacencies=lambda dim, tag: ([1, 2] if tag != 13 else [1], []),
        mesh=SimpleNamespace(generate=fail_mesh, getNodes=fail_mesh, getElements=fail_mesh),
        occ=SimpleNamespace(importShapes=lambda path: events.append(("import", path)),
            synchronize=lambda: events.append(("synchronize",)),
            getMass=lambda dim, tag: {1: 12., 2: 20., 3: 30.}[dim],
            getCenterOfMass=lambda dim, tag: [0., 0., 1.5],
            getCurveLoops=lambda tag: ([41], [[11, -12, 13, -13]]) if tag == 1 else ([42, 43], [[11], [-12]])))
    fake = SimpleNamespace(__version__="4.15.2", libpath="fake SDK; no native library",
        initialize=lambda **kwargs: events.append(("initialize", kwargs)),
        isInitialized=lambda: True, finalize=lambda: events.append(("finalize",)),
        open=lambda path: events.append(("open", path)), model=model, write=write,
        option=SimpleNamespace(setNumber=lambda *args: None, setString=lambda *args: None,
                               getNumber=lambda name: 1e-8),
        logger=SimpleNamespace(start=lambda: None, get=lambda: []))
    monkeypatch.setitem(sys.modules, "gmsh", fake)
    return fake, events


def call_worker_direct(monkeypatch):
    monkeypatch.setattr(backend.GmshBackend, "_run", lambda self, request, *args: worker.generate(request))


@pytest.mark.parametrize("unit,expected", [("mm", "mm"), ("unknown", "cm"), ("mm", None)])
def test_geometry_inspection_retains_raw_identity_topology_and_samples_without_mesh(source, tmp_path, monkeypatch, unit, expected):
    _, events = fake_sdk(monkeypatch, unit=unit); call_worker_direct(monkeypatch)
    original = source.read_bytes()
    result = backend.GmshBackend().inspect_geometry(source, tmp_path / "jobs", expected_coordinate_length_unit=expected)
    assert result["source_kind"] == "cad_geometry_inspection" and result["schema_version"] == 1
    assert result["geometry_resource_uuid"] == RESOURCE and result["geometry_revision"] == 2
    assert result["length_unit"] == unit and result["expected_coordinate_length_unit"] == expected
    assert set(result["assets"]) == {"xao", "metadata"}
    assert not {"mesh_uuid", "mesh", "counts", "nodes", "msh"}.intersection(result)
    assert source.read_bytes() == original
    assert result["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert Path(result["source"]["captured_path"]).read_bytes() == original
    assert json.loads(Path(result["assets"]["metadata"]).read_text()) == result
    assert events[0] == ("initialize", {"readConfigFiles": False, "interruptible": False})
    assert any(event[0] == "open" for event in events) and events[-1] == ("finalize",)
    surface = result["surfaces"][0]
    assert surface["uuid"] == FACE1 and surface["orientation_by_volume"] == [{"volume_uuid": VOLUME, "sign": -1}]
    assert surface["analytic_properties"]["reals"] == [0., 0., 0., 0., 0., 1., 2.]
    assert surface["analytic_properties"]["layout"] == "axis_point_xyz_direction_xyz_radius"
    assert surface["curve_loops"] == [{"backend_tag": 41, "curve_tags": [11, -12, 13, -13]}]
    assert surface["samples"][0]["face_normal"] == [-1., 0., 0.]  # never multiplied by volume sign
    assert all(face["sampling_status"] == "unverified" for face in result["surfaces"])
    assert result["surfaces"][1]["samples"][0]["trim_count"] == 0
    assert result["volumes"][0]["surface_uuids"] == [FACE1, FACE2]
    curves = {curve["backend_tag"]: curve for curve in result["curves"]}
    assert not any("uuid" in curve for curve in curves.values())
    assert curves[11]["endpoints"][0] == curves[11]["endpoints"][1]
    assert curves[12]["endpoints"] == []
    assert curves[11]["adjacent_surface_uuids"] == [FACE1, FACE2]
    assert result["geometry_tolerance"] == 1e-8 and result["sdk_error_count"] == 0
    assert not list((tmp_path / "jobs").glob("**/*.msh"))


def test_trim_count_one_is_still_not_a_verified_interior_sample(source, tmp_path, monkeypatch):
    fake_sdk(monkeypatch, trim_count=1); call_worker_direct(monkeypatch)
    result = backend.GmshBackend().inspect_geometry(source, tmp_path / "jobs")
    assert result["surfaces"][1]["samples"][0]["trim_count"] == 1
    assert result["surfaces"][1]["sampling_status"] == "unverified"
    assert "IN or ON" in result["topology_semantics"]["samples"]


def test_step_uses_shared_occ_import_and_inspection_cannot_be_a_mesh_candidate(source, tmp_path, monkeypatch):
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    from caelab_prep.cae_core.errors import PrepError
    _, events = fake_sdk(monkeypatch); call_worker_direct(monkeypatch)
    step = source.with_suffix(".step"); step.write_bytes(source.read_bytes())
    result = backend.GmshBackend().inspect_geometry(step, tmp_path / "jobs")
    assert result["length_unit"] == "mm" and any(e[0] == "import" for e in events)
    assert not any(e[0] == "open" for e in events)
    with pytest.raises(PrepError) as error:
        read_mesh_candidate(result)
    assert error.value.code == "invalid_candidate"


def test_changed_capture_during_inspection_cannot_publish_metadata(source, tmp_path, monkeypatch):
    fake, events = fake_sdk(monkeypatch); call_worker_direct(monkeypatch)
    original = source.read_bytes()
    def changed_normal(tag, uv):
        capture = Path(next(event[1] for event in events if event[0] == "open"))
        capture.write_bytes(b"changed captured geometry")
        return [1., 0., 0.]
    fake.model.getNormal = changed_normal
    with pytest.raises(worker.WorkerFailure) as error:
        backend.GmshBackend().inspect_geometry(source, tmp_path / "jobs")
    assert error.value.code == "source_changed" and source.read_bytes() == original
    assert not list((tmp_path / "jobs").glob("*/metadata.json"))


def test_existing_inspection_output_is_not_overwritten(source, tmp_path):
    out = tmp_path / "outputs"; out.mkdir()
    xao = out / "geometry.xao"; xao.write_bytes(b"previous owned result")
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": "cad_geometry_inspection", "source": str(source), "output_dir": str(out)})
    assert error.value.code == "invalid_request" and xao.read_bytes() == b"previous owned result"


def test_restored_xao_unit_conflict_stops_inspection_before_output(source, tmp_path, monkeypatch):
    _, events = fake_sdk(monkeypatch); call_worker_direct(monkeypatch)
    with pytest.raises(worker.WorkerFailure) as error:
        backend.GmshBackend().inspect_geometry(source, tmp_path / "jobs", expected_coordinate_length_unit="cm")
    assert error.value.code == "unit_mismatch" and events[-1] == ("finalize",)
    assert not any(event[0] in ("trim", "write_xao") for event in events)
    assert not list((tmp_path / "jobs").glob("*/metadata.json"))


@pytest.mark.parametrize("mutant", ["normal", "analytic", "bounds", "loop", "adjacency", "trim_count"])
def test_malformed_or_nonfinite_sdk_evidence_cannot_be_persisted(source, tmp_path, monkeypatch, mutant):
    fake, events = fake_sdk(monkeypatch); call_worker_direct(monkeypatch)
    if mutant == "normal": fake.model.getNormal = lambda *args: [float("nan"), 0., 0.]
    if mutant == "analytic": fake.model.getEntityProperties = lambda *args: ([], [float("inf")])
    if mutant == "bounds": fake.model.getParametrizationBounds = lambda *args: ([0., 0.], [float("inf"), 3.])
    if mutant == "loop": fake.model.occ.getCurveLoops = lambda tag: ([41], [[999]])
    if mutant == "adjacency": fake.model.getAdjacencies = lambda *args: ([999], [])
    if mutant == "trim_count": fake.model.isInside = lambda *args, **kwargs: 2
    with pytest.raises(worker.WorkerFailure) as error:
        backend.GmshBackend().inspect_geometry(source, tmp_path / "jobs")
    assert error.value.code == "invalid_geometry" and events[-1] == ("finalize",)
    assert not list((tmp_path / "jobs").glob("*/metadata.json"))


@pytest.mark.parametrize("parameters", [{"expected_coordinate_length_unit": "unknown"}, {"mesh_size": 1.},
                                       {"washer_width": 2.}, {"unknown_criterion": 1}])
def test_worker_rejects_invalid_inspection_requests_before_sdk(source, tmp_path, parameters):
    with pytest.raises(worker.WorkerFailure):
        worker.generate({"source_kind": "cad_geometry_inspection", "source": str(source),
                         "output_dir": str(tmp_path / "jobs"), **parameters})
    assert not (tmp_path / "jobs").exists()


@pytest.mark.parametrize("bad", ["missing", "suffix", "unit"])
def test_host_rejects_invalid_input_before_capture_or_process(source, tmp_path, monkeypatch, bad):
    monkeypatch.setattr(backend.subprocess, "Popen", lambda *a, **k: pytest.fail("Invalid request started process"))
    path, kwargs = source, {}
    if bad == "missing": path = tmp_path / "missing.step"
    if bad == "suffix": path = source.with_suffix(".geo"); path.write_bytes(b"not executable input")
    if bad == "unit": kwargs["expected_coordinate_length_unit"] = True
    with pytest.raises(backend.GmshBackendError):
        backend.GmshBackend().inspect_geometry(path, tmp_path / "jobs", **kwargs)
    assert not (tmp_path / "jobs").exists()


def test_captured_source_hash_is_checked_before_sdk(source, tmp_path):
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": "cad_geometry_inspection", "source": str(source),
                         "output_dir": str(tmp_path / "jobs"), "source_sha256": "0" * 64})
    assert error.value.code == "source_changed" and not (tmp_path / "jobs").exists()


def test_common_transport_and_dedicated_source_kind(source, tmp_path, monkeypatch):
    requests = []
    def start(argv, **kwargs):
        request = json.loads(Path(argv[-1]).read_text()); requests.append(request)
        assert Path(request["source"]).read_bytes() == source.read_bytes()
        return Process({"ok": True, "result": {"schema_version": 1, "source_kind": "cad_geometry_inspection"}})
    monkeypatch.setattr(backend.subprocess, "Popen", start)
    result = backend.GmshBackend().inspect_geometry(source, tmp_path / "jobs", expected_coordinate_length_unit="mm")
    assert result["source_kind"] == "cad_geometry_inspection"
    assert requests[0]["source_kind"] == "cad_geometry_inspection" and "mesh_size" not in requests[0]
    assert requests[0]["expected_coordinate_length_unit"] == "mm"
    monkeypatch.setattr(backend.GmshBackend, "_run", lambda *args: {"source_kind": "cad_gmsh", "mesh_uuid": "wrong"})
    with pytest.raises(backend.GmshBackendError) as error:
        backend.GmshBackend().inspect_geometry(source, tmp_path / "other")
    assert error.value.code == "worker_protocol_error"


@pytest.mark.parametrize("reason", ["before_start", "cancel", "timeout"])
def test_inspection_reuses_common_cancellation_timeout_and_reap(source, tmp_path, monkeypatch, reason):
    event = threading.Event()
    process = Process({}, running=True, kill_required=True)
    def start(*args, **kwargs):
        if reason == "cancel": event.set()
        return process
    monkeypatch.setattr(backend.subprocess, "Popen", start)
    if reason == "before_start":
        event.set()
        monkeypatch.setattr(backend.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Precancellation launched worker"))
    if reason == "timeout":
        ticks = iter((0., 2.)); monkeypatch.setattr(backend.time, "monotonic", lambda: next(ticks))
    error = backend.BackendTimeoutError if reason == "timeout" else backend.CancelledError
    with pytest.raises(error):
        backend.GmshBackend(timeout=1).inspect_geometry(source, tmp_path / "jobs", cancel_event=event)
    if reason != "before_start":
        assert process.terminated and process.killed and process.returncode is not None


@pytest.mark.skipif(find_spec("OCP") is None or find_spec("gmsh") is None,
                    reason="Actual CAD inspection integration requires existing OCP and Gmsh test dependencies")
def test_actual_geometry_inspection_preserves_cad_and_raw_topology_without_mesh(cad, tmp_path):
    """Run in CAD-worker CI; raw inspection is not shape-classification F1."""
    from caelab_prep.application.geometry_inspection import read_geometry_inspection
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    from caelab_prep.cae_core.errors import PrepError
    original = cad.read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    result = backend.GmshBackend().inspect_geometry(cad, tmp_path / "inspections",
                                                   expected_coordinate_length_unit="mm")
    assert result["schema_version"] == 1 and result["source_kind"] == "cad_geometry_inspection"
    assert result["length_unit"] == "mm" and result["expected_coordinate_length_unit"] == "mm"
    assert result["source"]["sha256"] == original_hash
    capture = Path(result["source"]["captured_path"])
    assert capture.read_bytes() == original
    assert set(result["assets"]) == {"xao", "metadata"}
    assert not {"mesh", "mesh_uuid", "mesh_revision", "nodes", "counts", "msh"}.intersection(result)
    paths = {"original": cad, "capture": capture, **{k: Path(v) for k, v in result["assets"].items()}}
    snapshot = {kind: path.read_bytes() for kind, path in paths.items()}
    assert snapshot["xao"] and snapshot["metadata"]
    inspected = read_geometry_inspection(result)
    assert inspected.to_dict() == result
    assert read_geometry_inspection(result["assets"]["metadata"]).to_dict() == result
    inspected.verify_assets()
    curve_tags = {curve["backend_tag"] for curve in result["curves"]}
    surface_ids = {surface["uuid"] for surface in result["surfaces"]}
    assert curve_tags and surface_ids and result["volumes"]
    assert any(surface["geometry_type"] == "Cylinder" for surface in result["surfaces"])
    for surface in result["surfaces"]:
        assert surface["geometry_type"] in ("Plane", "Cylinder")
        properties = surface["analytic_properties"]
        assert properties["layout"] == ("plane_cartesian_coefficients" if surface["geometry_type"] == "Plane"
                                         else "axis_point_xyz_direction_xyz_radius")
        assert len(properties["reals"]) == (4 if surface["geometry_type"] == "Plane" else 7)
        assert surface["sampling_status"] == "unverified"
        assert surface["normal_basis"] == "gmsh_face_oriented_no_volume_sign"
        assert len(surface["samples"]) == 1 and surface["samples"][0]["trim_count"] in (0, 1)
        for loop in surface["curve_loops"]:
            assert all(abs(tag) in curve_tags for tag in loop["curve_tags"])
    for curve in result["curves"]:
        assert "uuid" not in curve and set(curve["adjacent_surface_uuids"]) <= surface_ids
    assert not list(Path(result["assets"]["metadata"]).parent.glob("*.msh"))
    with pytest.raises(PrepError) as error:
        read_mesh_candidate(result)
    assert error.value.code == "invalid_candidate"
    assert {kind: path.read_bytes() for kind, path in paths.items()} == snapshot
