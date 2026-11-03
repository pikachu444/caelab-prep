"""Raw CAD/probe unit contracts and three dependency-gated actual SDK CI cases."""
import hashlib
from copy import deepcopy
from importlib.util import find_spec
import json
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from caelab_prep.adapters import gmsh_backend as backend
from caelab_prep.adapters import gmsh_worker as worker
from caelab_prep.adapters.gmsh_geometry import cylinder_probe_shape, plan_cylinder_material_probe
from test_surface_tet_backend import Process
from test_gmsh_adapter import cad  # existing independent OCP fixture, two shapes


RESOURCE = "00000000-0000-4000-8000-000000000001"
FACE1 = "00000000-0000-4000-8000-000000000002"
FACE2 = "00000000-0000-4000-8000-000000000003"
VOLUME = "00000000-0000-4000-8000-000000000004"
FACE3 = "00000000-0000-4000-8000-000000000005"


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


def probe_geometry(*, axis_sign=1, translation=(0., 0., 0.)):
    """A closed axis-aligned cylinder's raw GI1 subset, without SDK objects."""
    x, y, z = translation
    face = {"uuid": FACE1, "geometry_type": "Cylinder",
        "analytic_properties": {"reals": [x, y, z, 0., 0., float(axis_sign), 2.]},
        "bbox": [x-2, y-2, z, x+2, y+2, z+3],
        "parametric_bounds": {"minimum": [0., 0. if axis_sign == 1 else -3.],
                              "maximum": [math.tau, 3. if axis_sign == 1 else 0.]},
        "samples": [{"xyz": [x-2, y, z+1.5], "trim_count": 1}],
        "orientation_by_volume": [{"volume_uuid": VOLUME, "sign": -1}],
        "curve_loops": [{"backend_tag": 41, "curve_tags": [11, 13, -12, -13]}]}
    top = {"uuid": FACE2, "geometry_type": "Plane", "bbox": [x-2,y-2,z+3,x+2,y+2,z+3],
        "analytic_properties": {"reals": [0., 0., 2., -2*(z+3)]}}
    bottom = {"uuid": FACE3, "geometry_type": "Plane", "bbox": [x-2,y-2,z,x+2,y+2,z],
        "analytic_properties": {"reals": [0., 0., -1., z]}}
    curves = [{"backend_tag": tag, "geometry_type": "Circle", "length": 2*math.tau,
        "parametric_bounds": {"minimum": [0.], "maximum": [math.tau]},
        "endpoints": [{"backend_tag": 201, "xyz": [x+2,y,z+3]}]*2 if tag == 11 else []}
        for tag in (11, 12)]
    curves.append({"backend_tag": 13, "geometry_type": "Line", "adjacent_surface_uuids": [FACE1]})
    volumes = [{"uuid": VOLUME, "backend_tag": 5, "surface_uuids": [FACE1, FACE2, FACE3]}]
    return [face, top, bottom], volumes, curves



def test_shared_pure_shape_and_plan_preserve_raw_geometry_and_match_worker_query_positions():
    geometry = probe_geometry(); surfaces, volumes, curves = geometry
    baseline = deepcopy(geometry)
    shape = cylinder_probe_shape(surfaces[0], *geometry, 1e-8, "mm")
    assert shape == {"eligible": True, "reason": None, "volume_uuid": VOLUME,
                     "axis_index": 2, "axis_point": [0., 0., 0.], "radius": 2.}
    plan = plan_cylinder_material_probe(surfaces[0], *geometry, 1e-8, "mm")
    assert plan["status"] == "ready" and plan["reason"] is None
    assert plan["radial_material_side"] is None
    assert all(plan[label]["inside_count"] is None for label in ("plus", "minus"))
    observed, calls = run_fake_probe(*geometry)
    for key in ("epsilon", "geometry_tolerance", "numerical_margin", "clearance_lower_estimate"):
        assert observed[0][key] == plan[key]
    for label, call in zip(("plus", "minus"), calls):
        assert observed[0][label]["xyz"] == plan[label]["xyz"] == call["xyz"]
        assert observed[0][label]["signed_radial_residual"] == plan[label]["signed_radial_residual"]
    assert geometry == baseline
    json.dumps(plan, allow_nan=False)


@pytest.mark.parametrize("field", ["partial_cylinder", "partial_circle", "large_cylinder_parameter", "large_circle_parameter"])
def test_shared_shape_and_plan_block_nonfull_or_unresolvable_periods(field):
    geometry = probe_geometry(); surfaces, volumes, curves = geometry
    bounds = surfaces[0]["parametric_bounds"] if "cylinder" in field else curves[0]["parametric_bounds"]
    if field.startswith("partial"):
        bounds["maximum"][0] = math.pi
    else:
        bounds["minimum"][0], bounds["maximum"][0] = 1e16, 1e16 + 6
    before = deepcopy(geometry)
    shape = cylinder_probe_shape(surfaces[0], *geometry, 1e-8, "mm")
    plan = plan_cylinder_material_probe(surfaces[0], *geometry, 1e-8, "mm")
    assert not shape["eligible"] and shape["reason"]
    assert plan["status"] == "indeterminate" and plan["reason"] == shape["reason"]
    rows, calls = run_fake_probe(*geometry)
    assert calls == [] and rows == [plan] and geometry == before


def run_fake_probe(surfaces, volumes, curves, *, counts=(1, 0), tolerance=1e-8, unit="mm"):
    calls, answers = [], iter(counts)
    def inside(dim, tag, xyz, *, parametric):
        assert dim == 3 and tag == 5 and parametric is False
        calls.append({"xyz": list(xyz), "parametric": parametric})
        answer = next(answers)
        if isinstance(answer, Exception): raise answer
        return answer
    sdk = SimpleNamespace(model=SimpleNamespace(isInside=inside,
        mesh=SimpleNamespace(generate=lambda *args: pytest.fail("Probe generated a mesh"))))
    return worker._cylinder_material_side_probes(sdk, surfaces, volumes, curves, tolerance, unit), calls


@pytest.mark.parametrize("counts,side", [((1,0), "outward_side_is_material"), ((0,1), "inward_side_is_material")])
def test_bounded_cylinder_probe_records_raw_single_point_queries_without_normal_flips(counts, side):
    geometry = probe_geometry(); original = deepcopy(geometry)
    rows, calls = run_fake_probe(*geometry, counts=counts)
    row = rows[0]
    assert row["status"] == "observed" and row["reason"] is None and row["radial_material_side"] == side
    assert len(calls) == 2 and geometry == original
    assert [row[k]["inside_count"] for k in ("plus", "minus")] == list(counts)
    assert row["plus"]["xyz"][0] < -2 and row["minus"]["xyz"][0] > -2
    margin = 4096*math.ulp(3.)
    assert row["numerical_margin"] == margin
    assert row["clearance_lower_estimate"] == 1.5-margin
    assert row["epsilon"] == (1.5-margin)/64
    floor = max(128*row["geometry_tolerance"], margin)
    assert row["plus"]["signed_radial_residual"] >= floor
    assert row["minus"]["signed_radial_residual"] <= -floor


def test_cylinder_axis_direction_flip_keeps_the_same_radial_witness():
    positive, _ = run_fake_probe(*probe_geometry(axis_sign=1))
    negative, _ = run_fake_probe(*probe_geometry(axis_sign=-1))
    assert positive == negative


@pytest.mark.parametrize("counts,reason", [((1,1), "ambiguous_equal_inside_counts"),
    ((0,0), "ambiguous_equal_inside_counts"), ((2,), "invalid_inside_count"),
    ((None,), "invalid_inside_count"), ((RuntimeError("SDK query failed"),), "volume_query_error")])
def test_ambiguous_or_unknown_volume_answers_are_indeterminate(counts, reason):
    rows, calls = run_fake_probe(*probe_geometry(), counts=counts)
    assert rows[0]["status"] == "indeterminate" and rows[0]["radial_material_side"] is None
    assert rows[0]["reason"].startswith(reason)
    assert len(calls) == (2 if len(counts) == 2 else 1)
    json.dumps(rows, allow_nan=False)


@pytest.mark.parametrize("mutant", ["unknown_unit", "large_coords", "near_cap", "unsupported_boundary", "tilted_plane",
    "tilted_axis", "trim0", "partial_u", "partial_circle", "circle_length", "open_circle",
    "missing_seam", "shared_seam", "two_owners", "off_surface", "large_tolerance", "nonfinite", "underflow", "underflow_plane"])
def test_unsafe_geometry_never_queries_the_volume_or_changes_raw_values(mutant):
    surfaces, volumes, curves = probe_geometry()
    unit, tolerance = "mm", 1e-8
    if mutant == "unknown_unit": unit = "unknown"
    if mutant == "large_coords": surfaces, volumes, curves = probe_geometry(translation=(1e15, 0., 0.))
    if mutant == "near_cap": surfaces[0]["samples"][0]["xyz"][2] = 1e-7
    if mutant == "unsupported_boundary": surfaces[1]["geometry_type"] = "Torus"
    if mutant == "tilted_plane": surfaces[1]["analytic_properties"]["reals"] = [1., 1e-16, 0., 3.]
    if mutant == "tilted_axis": surfaces[0]["analytic_properties"]["reals"][3:6] = [1e-16, 0., 1.]
    if mutant == "trim0": surfaces[0]["samples"][0]["trim_count"] = 0
    if mutant == "partial_u": surfaces[0]["parametric_bounds"]["maximum"][0] = math.pi
    if mutant == "partial_circle": curves[0]["parametric_bounds"]["maximum"][0] = math.pi
    if mutant == "circle_length": curves[0]["length"] = math.tau
    if mutant == "open_circle": curves[0]["endpoints"][1] = {"backend_tag": 202, "xyz": [2.,0.,3.]}
    if mutant == "missing_seam": surfaces[0]["curve_loops"][0]["curve_tags"] = [11, -12, 13]
    if mutant == "shared_seam": curves[2]["adjacent_surface_uuids"].append(FACE2)
    if mutant == "two_owners": surfaces[0]["orientation_by_volume"].append({"volume_uuid": RESOURCE, "sign": 1})
    if mutant == "off_surface": surfaces[0]["samples"][0]["xyz"][0] = -2.1
    if mutant == "large_tolerance": tolerance = .1
    if mutant == "nonfinite": surfaces[1]["bbox"][0] = float("inf")
    if mutant == "underflow": surfaces[0]["analytic_properties"]["reals"][6] = 1e-320
    if mutant == "underflow_plane": surfaces[1]["analytic_properties"]["reals"] = [0., 0., 1e300, 1e-300]
    before = deepcopy((surfaces, volumes, curves))
    rows, calls = run_fake_probe(surfaces, volumes, curves, unit=unit, tolerance=tolerance)
    assert rows[0]["status"] == "indeterminate" and rows[0]["reason"] and calls == []
    assert (surfaces, volumes, curves) == before
    json.dumps(rows, allow_nan=False)


def test_imported_decimal_circle_period_and_negative_seam_occurrences_are_not_rewritten():
    geometry = probe_geometry(); surfaces, volumes, curves = geometry
    surfaces[0]["parametric_bounds"]["maximum"][0] = 6.28318530718
    before = deepcopy(geometry)
    rows, calls = run_fake_probe(*geometry)
    assert rows[0]["status"] == "observed" and len(calls) == 2 and geometry == before


@pytest.mark.parametrize("flag", [1, 0, None, "true"])
def test_probe_option_is_boolean_at_both_boundaries(source, tmp_path, flag):
    with pytest.raises(backend.GmshBackendError) as error:
        backend.GmshBackend().inspect_geometry(source, tmp_path/"jobs", probe_cylinder_material_side=flag)
    assert error.value.code == "invalid_request" and not (tmp_path/"jobs").exists()
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": "cad_geometry_inspection", "probe_cylinder_material_side": flag})
    assert error.value.code == "invalid_request"


@pytest.mark.parametrize("kind", [None, "cad", "closed_tri_surface", "structured_recipe"])
def test_noninspection_dispatch_rejects_even_false_probe_options(kind):
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": kind, "probe_cylinder_material_side": False})
    assert error.value.code == "unsupported_criteria"


def test_default_inspection_has_no_probe_field_and_opt_in_does_not_change_raw_samples(source, tmp_path, monkeypatch):
    _, events = fake_sdk(monkeypatch); call_worker_direct(monkeypatch)
    baseline = backend.GmshBackend().inspect_geometry(source, tmp_path/"before")
    assert "cylinder_material_side_probes" not in baseline
    opted = backend.GmshBackend().inspect_geometry(source, tmp_path/"after", probe_cylinder_material_side=True)
    assert baseline["surfaces"] == opted["surfaces"] and baseline["curves"] == opted["curves"]
    assert opted["cylinder_material_side_probes"][0]["status"] == "indeterminate"
    assert opted["cylinder_material_side_probes"][0]["reason"] == "full_cylinder_period_required"
    assert all(event[0] != "volume_query" for event in events)


def _assert_actual_geometry_inspection(cad, tmp_path):
    """Assert capture/raw evidence and pure candidate recognition without mesh."""
    from caelab_prep.application.geometry_features import recognize_cylindrical_holes
    from caelab_prep.application.geometry_inspection import read_geometry_inspection
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    from caelab_prep.cae_core.errors import PrepError
    original = cad.read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    result = backend.GmshBackend().inspect_geometry(cad, tmp_path / "inspections",
                                                   expected_coordinate_length_unit="mm",
                                                   probe_cylinder_material_side=True)
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
    recognized = recognize_cylindrical_holes(inspected, length_tolerance=1e-6)
    assert recognized["modifications"] == 0 and recognized["length_tolerance"] == 1e-6
    assert recognized["geometry_resource_uuid"] == result["geometry_resource_uuid"]
    assert recognized["geometry_revision"] == result["geometry_revision"]
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
    return result, recognized


@pytest.mark.skipif(find_spec("OCP") is None or find_spec("gmsh") is None,
                    reason="Actual CAD inspection integration requires existing OCP and Gmsh test dependencies")
def test_actual_geometry_inspection_preserves_cad_and_raw_topology_without_mesh(cad, tmp_path):
    """CI raw witness/candidate integration; this is not full feature-family F1."""
    result, recognized = _assert_actual_geometry_inspection(cad, tmp_path)
    observed = [probe for probe in result["cylinder_material_side_probes"] if probe["status"] == "observed"]
    assert len(observed) == 1
    if cad.stem == "plate-with-hole":
        assert len(recognized["features"]) == 1
        feature = recognized["features"][0]
        assert feature["kind"] == "through_hole_candidate" and feature["radius"] == pytest.approx(1., abs=1e-10)
        assert {cap["kind"] for cap in feature["caps"]} == {"rectangular_opening"}
        assert observed[0]["radial_material_side"] == "outward_side_is_material"
    else:
        assert cad.stem == "cylinder" and recognized["features"] == []
        assert observed[0]["radial_material_side"] == "inward_side_is_material"


@pytest.mark.skipif(find_spec("OCP") is None or find_spec("gmsh") is None,
                    reason="Actual CAD inspection integration requires existing OCP and Gmsh test dependencies")
def test_actual_geometry_inspection_blind_hole_candidate(tmp_path):
    """Generate this toy only in CAD-worker CI; no complete F1 qualification."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    shape = BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(12, 8, 3).Shape(),
                           BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(6, 4, 1), gp_Dir(0, 0, 1)), 1, 3).Shape()).Shape()
    cad = tmp_path / "blind-hole.step"
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    assert int(writer.Write(str(cad))) == 1
    result, recognized = _assert_actual_geometry_inspection(cad, tmp_path)
    assert len(result["surfaces"]) == 8 and len(result["volumes"]) == 1
    assert result["volumes"][0]["volume"] == pytest.approx(288-2*math.pi, abs=1e-9)
    assert len(recognized["features"]) == 1
    feature = recognized["features"][0]
    assert feature["kind"] == "blind_hole_candidate" and feature["radius"] == pytest.approx(1., abs=1e-10)
    assert {cap["kind"] for cap in feature["caps"]} == {"closed_disk", "rectangular_opening"}
    assert feature["material_side_evidence"]["radial_material_side"] == "outward_side_is_material"
