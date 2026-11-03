"""Surface-volume request/process and inventory guards; these tests run no SDK."""
import json
import math
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from caelab_prep.adapters import gmsh_backend as transport
from caelab_prep.adapters import gmsh_worker as worker


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "surface.msh"
    path.write_bytes(b"captured source bytes for transport tests\n")
    return path


@pytest.mark.parametrize("values", [
    {"length_unit": "unknown"}, {"element_order": True}, {"element_order": 3},
    {"smoothing_iterations": -1}, {"smoothing_iterations": 101}, {"smoothing_iterations": True},
    {"relaxation": 0}, {"relaxation": 1.1}, {"minimum_scaled_jacobian": 0},
    {"minimum_scaled_jacobian": .49}, {"minimum_scaled_jacobian": 1.1},
    {"minimum_scaled_jacobian": float("nan")}, {"maximum_edge_aspect_ratio": .9},
    {"maximum_edge_aspect_ratio": 4.1},
    {"maximum_edge_aspect_ratio": float("inf")}, {"mesh_size": True}, {"mesh_size": 0},
    {"volume_optimizer": "unknown"}, {"volume_optimizer": True},
])
def test_invalid_surface_requests_launch_no_process(source, tmp_path, monkeypatch, values):
    monkeypatch.setattr(transport.subprocess, "Popen", lambda *a, **k: pytest.fail("invalid input launched a worker"))
    parameters = {"length_unit": "mm", "mesh_size": 1., **values}
    with pytest.raises(transport.GmshBackendError) as error:
        transport.GmshBackend().generate_surface_volume(source, tmp_path / "jobs", **parameters)
    assert error.value.code == "invalid_request" and not (tmp_path / "jobs").exists()


class Process:
    pid = 4321

    def __init__(self, response, *, exit_code=0, running=False, kill_required=False):
        self.response, self.exit_code = response, exit_code
        self.returncode = None if running else exit_code
        self.terminated = self.killed = False
        self.kill_required = kill_required

    def communicate(self, timeout):
        if self.kill_required and not self.killed:
            raise subprocess.TimeoutExpired("owned worker", timeout)
        self.returncode = self.exit_code
        return json.dumps(self.response), "worker diagnostic"

    def poll(self): return self.returncode
    def terminate(self): self.terminated = True
    def kill(self): self.killed = True


def test_capture_and_common_process_runner_keep_cad_contract(source, tmp_path, monkeypatch):
    seen = []
    def start(argv, **kwargs):
        request = json.loads(Path(argv[-1]).read_text())
        seen.append((argv, kwargs, request))
        assert Path(request["source"]).read_bytes() == source.read_bytes()
        result = {"schema_version": 1}
        if request.get("source_kind") == "closed_tri_surface": result["source_kind"] = "surface_tet"
        else: result["geometry_resource_uuid"] = "existing CAD result unchanged"
        return Process({"ok": True, "result": result})
    monkeypatch.setattr(transport.subprocess, "Popen", start)
    backend = transport.GmshBackend()
    first = backend.generate_surface_volume(source, tmp_path / "jobs", .7, length_unit="cm", element_order=2)
    backend.generate_surface_volume(source, tmp_path / "jobs", .7, length_unit="cm")
    assert first == {"schema_version": 1, "source_kind": "surface_tet"}
    request = seen[0][2]
    assert request["element_order"] == 2 and request["length_unit"] == "cm"
    assert request["minimum_scaled_jacobian"] == .5 and request["maximum_edge_aspect_ratio"] == 4.
    assert request["smoothing_iterations"] == 2 and request["relaxation"] == .5
    assert request["volume_optimizer"] == "netgen"
    assert seen[0][1]["cwd"] != seen[1][1]["cwd"]
    assert seen[0][0][1:3] == ["-m", "caelab_prep.adapters.gmsh_worker"]
    assert request["source_sha256"] == transport.hashlib.sha256(source.read_bytes()).hexdigest()
    cad = source.with_suffix(".step"); cad.write_bytes(source.read_bytes())
    actual = backend.generate(cad, tmp_path / "jobs", 1., dimension=2)
    assert actual["geometry_resource_uuid"] == "existing CAD result unchanged"
    assert "source_kind" not in seen[-1][2]
    assert seen[-1][2]["interface_policy"] == "preserve" and seen[-1][2]["local_sizes"] == {}


def test_structured_worker_failure_details_reach_the_caller(source, tmp_path, monkeypatch):
    process = Process({"ok": False, "error": {"code": "boundary_changed", "message": "original vertex changed",
        "details": {"changed_node_ids": [101]}}}, exit_code=1)
    monkeypatch.setattr(transport.subprocess, "Popen", lambda *a, **k: process)
    with pytest.raises(transport.GmshBackendError) as error:
        transport.GmshBackend().generate_surface_volume(source, tmp_path / "jobs", 1, length_unit="m")
    assert error.value.code == "boundary_changed" and error.value.details["worker_details"] == {"changed_node_ids": [101]}


def test_cancelled_request_never_starts_a_process(source, tmp_path, monkeypatch):
    cancel = threading.Event(); cancel.set()
    monkeypatch.setattr(transport.subprocess, "Popen", lambda *a, **k: pytest.fail("cancelled input started a worker"))
    with pytest.raises(transport.CancelledError):
        transport.GmshBackend().generate_surface_volume(source, tmp_path / "jobs", 1, length_unit="mm", cancel_event=cancel)


@pytest.mark.parametrize("reason", ["cancel", "timeout"])
def test_running_worker_is_terminated_killed_and_reaped(source, tmp_path, monkeypatch, reason):
    process = Process({}, running=True, kill_required=True)
    cancel = threading.Event()
    def start(*a, **k):
        if reason == "cancel": cancel.set()
        return process
    monkeypatch.setattr(transport.subprocess, "Popen", start)
    ticks = iter((0., 2.))
    monkeypatch.setattr(transport.time, "monotonic", lambda: next(ticks))
    expected = transport.CancelledError if reason == "cancel" else transport.BackendTimeoutError
    with pytest.raises(expected):
        transport.GmshBackend(timeout=1).generate_surface_volume(source, tmp_path / "jobs", 1, length_unit="mm", cancel_event=cancel)
    assert process.terminated and process.killed and process.returncode is not None


def test_surface_request_cannot_return_a_cad_candidate(source, tmp_path, monkeypatch):
    monkeypatch.setattr(transport.GmshBackend, "_run", lambda *a: {"schema_version": 1, "geometry_resource_uuid": "CAD"})
    with pytest.raises(transport.GmshBackendError) as error:
        transport.GmshBackend().generate_surface_volume(source, tmp_path / "jobs", 1, length_unit="mm")
    assert error.value.code == "worker_protocol_error"


@pytest.mark.parametrize("parameters", [{"length_unit": "unknown"},
    {"minimum_scaled_jacobian": .49}, {"maximum_edge_aspect_ratio": 4.1}, {"volume_optimizer": "unknown"}])
def test_worker_rejects_bad_surface_request_before_loading_sdk(parameters):
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind": "closed_tri_surface", "mesh_size": 1, "length_unit": "mm", **parameters})
    assert error.value.code == "invalid_request"


def surface():
    return SimpleNamespace(node_ids=(101, 907, 43, 6201),
        coordinates=((0., 0., 0.), (2., 0., 0.), (0., 2., 0.), (0., 0., 2.)),
        triangle_ids=(31, 71, 91, 141),
        triangles=((101, 43, 907), (101, 907, 6201), (907, 43, 6201), (43, 101, 6201)))


def block(dimension, typ, order, ids, conn):
    return {"dimension": dimension, "element_type": typ, "order": order,
            "ids": list(ids), "connectivity": list(conn)}


def test_exact_oriented_boundary_and_volume_faces_allow_only_cyclic_rotation():
    source = surface(); nodes = dict(zip(source.node_ids, source.coordinates))
    rotated = tuple(conn[1:] + conn[:1] for conn in source.triangles)
    worker._surface_boundary(source, nodes, [block(2, 2, 1, source.triangle_ids, rotated)])
    assert worker._tet_topology(source, {601: source.node_ids})["boundary_faces_exact"]
    with pytest.raises(worker.WorkerFailure):
        worker._surface_boundary(source, nodes, [block(2, 2, 1, source.triangle_ids, tuple(conn[::-1] for conn in rotated))])
    nodes[101] = (math.nextafter(0., 1.), 0., 0.)
    with pytest.raises(worker.WorkerFailure):
        worker._surface_boundary(source, nodes, [block(2, 2, 1, source.triangle_ids, rotated)])


def test_written_mesh_has_an_explicit_eight_ulp_coordinate_limit():
    expected = {101: (1., 0., -2.)}; blocks = [block(3, 4, 1, [71], [(101, 2, 3, 4)])]
    written = {"nodes": {"ids": [101], "coordinates": [[1 + 8 * math.ulp(1.), 0., -2.]]}, "blocks": blocks}
    _, report = worker._serialization(expected, blocks, written)
    assert report["maximum_coordinate_error_ulps"] == 8
    written["nodes"]["coordinates"][0][0] = 1 + 9 * math.ulp(1.)
    with pytest.raises(worker.WorkerFailure) as error: worker._serialization(expected, blocks, written)
    assert error.value.code == "serialization_changed"
    written["nodes"]["coordinates"][0][0] = 1.
    written["blocks"] = [block(3, 4, 1, [71], [(101, 2, 4, 3)])]
    with pytest.raises(worker.WorkerFailure): worker._serialization(expected, blocks, written)


def test_sdk_repr_coordinates_preserve_cancelling_midpoint_and_other_bytes(tmp_path):
    from caelab_prep.adapters.msh_worker import read_msh
    # These binary64 endpoints reproduce the actual sphere failure's %.16g
    # triplet; the failed job did not retain its exact pre-write SDK values.
    nodes = {12395: (.11676322026583953, 0., 0.), 12464: (-.10175253449149277, 1., 0.),
             801: (0., 0., 1.), 902: (1., 0., 0.)}
    corners = tuple(nodes)
    pairs = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))
    for midpoint, (a, b) in enumerate(pairs, 13492):
        nodes[midpoint] = tuple(x / 2 + y / 2 for x, y in zip(nodes[corners[a]], nodes[corners[b]]))
    conn = corners + tuple(range(13492, 13498))
    assert worker._affine_midpoints(nodes, {17780: conn}, {}, 2)["passed"]
    prefix = b"$MeshFormat\r\n4.1 0 8\r\n$EndMeshFormat\r\n$Nodes\r\n"
    suffix = b"$EndNodes\r\n$Elements\r\n1 1 17780 17780\r\n3 1 11 1\r\n17780 " + " ".join(map(str, conn)).encode() + b"\r\n$EndElements\r\n"
    header = b"2 10 801 13497\r\n2 1 0 4\r\n" + " ".join(map(str, corners)).encode() + b"\r\n"
    body = b"".join((" ".join(format(x, ".16g") for x in nodes[n]) + "\r\n").encode() for n in corners)
    mid_header = b"3 1 0 6\r\n13492 13493 13494 13495 13496 13497\r\n"
    body2 = b"".join((" ".join(format(x, ".16g") for x in nodes[n]) + "\r\n").encode() for n in range(13492, 13498))
    path = tmp_path / "precision.msh"
    original = prefix + header + body + mid_header + body2 + suffix
    path.write_bytes(original)
    before = read_msh(path)
    rounded = dict(zip(before["nodes"]["ids"], map(tuple, before["nodes"]["coordinates"])))
    with pytest.raises(worker.WorkerFailure, match="affine edge midpoint"):
        worker._affine_midpoints(rounded, {17780: conn}, {}, 2)
    report = worker._preserve_msh_coordinates(path, nodes)
    after = read_msh(path)
    preserved = dict(zip(after["nodes"]["ids"], map(tuple, after["nodes"]["coordinates"])))
    assert preserved == nodes and worker._affine_midpoints(preserved, {17780: conn}, {}, 2)["passed"]
    assert before["blocks"] == after["blocks"] and before["nodes"]["ids"] == after["nodes"]["ids"]
    actual = path.read_bytes()
    assert actual.startswith(prefix + header) and actual.endswith(suffix) and mid_header in actual
    assert report["noncoordinate_bytes_preserved"] and report["nodes"] == 10


@pytest.mark.parametrize("change", ["parametric", "extra_id", "duplicate_id", "missing_id", "extra_token"])
def test_sdk_coordinate_preservation_rejects_unexpected_nodes_layout(tmp_path, change):
    path = tmp_path / "bad.msh"
    text = "$MeshFormat\n4.1 0 8\n$EndMeshFormat\n$Nodes\n1 2 101 907\n2 1 0 2\n101 907\n1 0 0\n2 0 0\n$EndNodes\n"
    if change == "parametric": text = text.replace("2 1 0 2", "2 1 1 2")
    if change == "extra_id": text = text.replace("101 907\n", "101 908\n")
    if change == "duplicate_id": text = text.replace("101 907\n", "101 101\n")
    if change == "missing_id": text = text.replace("2 1 0 2", "2 1 0 1")
    if change == "extra_token": text = text.replace("$EndNodes", "123\n$EndNodes")
    original = text.encode(); path.write_bytes(original)
    with pytest.raises(worker.WorkerFailure) as error:
        worker._preserve_msh_coordinates(path, {101: (1., 0., 0.), 907: (2., 0., 0.)})
    assert error.value.code == "serialization_changed" and path.read_bytes() == original


def test_written_boundary_rejects_one_ulp_even_within_serialization_budget():
    source = surface(); expected = dict(zip(source.node_ids, source.coordinates))
    triangles = [block(2, 2, 1, source.triangle_ids, source.triangles)]
    written = {"nodes": {"ids": list(expected), "coordinates": list(expected.values())}, "blocks": triangles}
    written["nodes"]["coordinates"][0] = (math.nextafter(0., 1.), 0., 0.)
    nodes, report = worker._serialization(expected, triangles, written)
    assert report["passed"] and report["maximum_coordinate_error_ulps"] == 1
    with pytest.raises(worker.WorkerFailure, match="original boundary"):
        worker._surface_boundary(source, nodes, triangles)


def test_affine_tet10_keeps_gmsh_edge_order_and_shared_tri6_midpoints():
    source = surface(); nodes = dict(zip(source.node_ids, source.coordinates))
    edges = ((101, 907), (907, 43), (43, 101), (101, 6201), (43, 6201), (907, 6201))
    for midpoint, edge in enumerate(edges, 11):
        nodes[midpoint] = tuple(a / 2 + b / 2 for a, b in zip(nodes[edge[0]], nodes[edge[1]]))
    tets = {601: source.node_ids + (11, 12, 13, 14, 15, 16)}
    triangles = {31: (101, 43, 907, 13, 12, 11)}
    report = worker._affine_midpoints(nodes, tets, triangles, 2)
    assert report["passed"] and len(report["edge_midpoints"]) == 6
    with pytest.raises(worker.WorkerFailure):
        worker._affine_midpoints(nodes, tets, {31: (101, 43, 907, 11, 12, 13)}, 2)


def test_quality_records_all_failing_ids_without_discarding_cells():
    parameters = {"minimum_scaled_jacobian": .5, "maximum_edge_aspect_ratio": 4.}
    def metrics(points): return {"signed_volume": 1., "corner_scaled_jacobian": .4, "edge_aspect_ratio": 5., "problem": None}
    report = worker._metrics(dict(zip(surface().node_ids, surface().coordinates)), {71: surface().node_ids, 72: surface().node_ids}, parameters, metrics)
    assert not report["passed"] and report["failed_ids"] == [71, 72] and len(report["cells"]) == 2
    def degenerate(points): return {"signed_volume": 0., "corner_scaled_jacobian": None, "edge_aspect_ratio": None, "problem": "degenerate"}
    report = worker._metrics(dict(zip(surface().node_ids, surface().coordinates)), {71: surface().node_ids}, parameters, degenerate)
    assert report["failed_ids"] == [71]
    json.dumps(report, allow_nan=False)


def test_elevation_mapping_uses_unique_oriented_topology_not_element_tags():
    rows = worker._elevation_mapping({503: (101, 138, 175)}, {951: (101, 138, 175, 657)},
        {978: (138, 175, 101, 1, 2, 3)}, {1006: (101, 138, 175, 657, 1, 2, 3, 4, 5, 6)})
    assert rows == [
        {"dimension": 2, "parent_id": 503, "elevated_id": 978, "restored_id": 503},
        {"dimension": 3, "parent_id": 951, "elevated_id": 1006, "restored_id": 951}]


@pytest.mark.parametrize("triangles,tets", [
    ({978: (101, 175, 138)}, {1006: (101, 138, 175, 657)}),
    ({978: (101, 138, 175)}, {1006: (138, 101, 175, 657)}),
    ({978: (101, 138, 175), 979: (138, 175, 101)}, {1006: (101, 138, 175, 657)}),
    ({978: (101, 138, 175)}, {978: (101, 138, 175, 657)}),
])
def test_elevation_mapping_rejects_changed_or_ambiguous_topology(triangles, tets):
    with pytest.raises(worker.WorkerFailure, match="Elevation"):
        worker._elevation_mapping({503: (101, 138, 175)}, {951: (101, 138, 175, 657)}, triangles, tets)


@pytest.mark.parametrize("order,optimizer,damage", [(1, "gmsh", None), (1, "netgen", None),
    (2, "netgen", None), (1, "netgen", "node"), (1, "netgen", "triangle"), (1, "netgen", "tet")])
def test_mock_sdk_roundtrip_uses_real_source_reader_smoother_and_written_msh(tmp_path, monkeypatch, order, optimizer, damage):
    from test_surface_tet import write_surface
    from caelab_prep.application import surface_tet
    source, ids, triangle_ids = write_surface(tmp_path)
    original = source.read_bytes()
    events = []
    smooth = surface_tet.smooth_tet4
    def laplacian(*args, **kwargs):
        events.append("laplacian")
        return smooth(*args, **kwargs)
    monkeypatch.setattr(surface_tet, "smooth_tet4", laplacian)

    class Mesh:
        elevated = False
        def addNodes(self, dimension, tag, tags, xyz):
            self.nodes = dict(zip(tags, [tuple(xyz[i:i + 3]) for i in range(0, len(xyz), 3)]))
        def addElementsByType(self, tag, typ, tags, conn):
            self.triangles = dict(zip(tags, [tuple(conn[i:i + 3]) for i in range(0, len(conn), 3)]))
        def generate(self, dimension):
            events.append("generate")
            self.tets = {max(triangle_ids) + 1: tuple(ids)}
        def optimize(self, method, *, force, niter, dimTags):
            assert method == "Netgen" and force is False and niter == 1 and dimTags == [(3, 1)]
            events.append("netgen")
            if damage == "node":
                xyz = self.nodes[ids[0]]
                self.nodes[ids[0]] = (math.nextafter(xyz[0], math.inf), *xyz[1:])
            elif damage == "triangle":
                self.triangles[999999] = self.triangles.pop(triangle_ids[0])
            elif damage == "tet":
                self.tets = {eid: (conn[1], conn[0], *conn[2:]) for eid, conn in self.tets.items()}
        def getNodes(self): return list(self.nodes), [x for point in self.nodes.values() for x in point], []
        def getElements(self, dimension, tag):
            cells = self.triangles if dimension == 2 else self.tets
            typ = (9 if self.elevated else 2) if dimension == 2 else (11 if self.elevated else 4)
            return [typ], [list(cells)], [[node for conn in cells.values() for node in conn]]
        def getElementProperties(self, typ):
            dim, degree, count = {2: (2, 1, 3), 9: (2, 2, 6), 4: (3, 1, 4), 11: (3, 2, 10)}[typ]
            return "test SDK element", dim, degree, count, [], 3 if dim == 2 else 4
        def setNode(self, identifier, xyz, parameters): self.nodes[identifier] = tuple(xyz)
        def setOrder(self, degree):
            events.append("elevate")
            self.elevated = True
            pairs = ((0, 1), (1, 2), (2, 0), (0, 3), (2, 3), (1, 3))
            mids = {}
            for a, b in pairs:
                edge = tuple(sorted((ids[a], ids[b])))
                identifier = max(self.nodes) + 1
                self.nodes[identifier] = tuple(x / 2 + y / 2 for x, y in zip(self.nodes[edge[0]], self.nodes[edge[1]]))
                mids[edge] = identifier
            self.tets = {eid: conn + tuple(mids[tuple(sorted((conn[a], conn[b])))] for a, b in pairs)
                         for eid, conn in self.tets.items()}
            self.triangles = {eid: conn + tuple(mids[tuple(sorted((conn[a], conn[b])))] for a, b in ((0, 1), (1, 2), (2, 0)))
                              for eid, conn in self.triangles.items()}
            # Real Gmsh 4.15.2 setOrder assigns new tags despite Mesh.Renumber=0.
            self.triangles = {eid + 10000: conn for eid, conn in self.triangles.items()}
            self.tets = {eid + 10000: conn for eid, conn in self.tets.items()}
        def renumberElements(self, oldTags, newTags):
            mapping = dict(zip(oldTags, newTags))
            self.triangles = {mapping[eid]: conn for eid, conn in self.triangles.items()}
            self.tets = {mapping[eid]: conn for eid, conn in self.tets.items()}

    mesh, options = Mesh(), {}
    def write(path):
        node_ids = list(mesh.nodes); count = len(mesh.triangles) + len(mesh.tets)
        element_ids = list(mesh.triangles) + list(mesh.tets)
        lines = ["$MeshFormat", "4.1 0 8", "$EndMeshFormat", "$Entities", "0 0 1 1",
                 "1 -1 -1 -1 2 2 2 0 0", "1 -1 -1 -1 2 2 2 0 1 1", "$EndEntities", "$Nodes",
                 f"1 {len(node_ids)} {min(node_ids)} {max(node_ids)}", f"2 1 0 {len(node_ids)}",
                 " ".join(map(str, node_ids))]
        lines += [" ".join(map(repr, mesh.nodes[identifier])) for identifier in node_ids]
        lines += ["$EndNodes", "$Elements", f"2 {count} {min(element_ids)} {max(element_ids)}",
                  f"2 1 {9 if mesh.elevated else 2} {len(mesh.triangles)}"]
        lines += [str(eid) + " " + " ".join(map(str, conn)) for eid, conn in mesh.triangles.items()]
        lines += [f"3 1 {11 if mesh.elevated else 4} {len(mesh.tets)}"]
        lines += [str(eid) + " " + " ".join(map(str, conn)) for eid, conn in mesh.tets.items()]
        Path(path).write_text("\n".join(lines + ["$EndElements"]) + "\n", encoding="ascii")
    fake = SimpleNamespace(__version__="4.15.2", libpath="mock only, no native library loaded",
        initialize=lambda **kwargs: None, finalize=lambda: None, isInitialized=lambda: True,
        option=SimpleNamespace(setNumber=options.__setitem__),
        logger=SimpleNamespace(start=lambda: None, get=lambda: []), write=write,
        model=SimpleNamespace(mesh=mesh, add=lambda name: None, addDiscreteEntity=lambda dim: 1,
            getEntities=lambda dim: [(dim, 1)], getType=lambda dim, tag: "Volume", geo=SimpleNamespace(addSurfaceLoop=lambda tags: 1,
                addVolume=lambda loops: 1, synchronize=lambda: None)))
    monkeypatch.setitem(sys.modules, "gmsh", fake)
    monkeypatch.setattr(transport.GmshBackend, "_run", lambda self, request, *args: worker.generate(request))
    if damage:
        with pytest.raises(worker.WorkerFailure) as error:
            transport.GmshBackend().generate_surface_volume(source, tmp_path / "jobs", 1., length_unit="mm",
                                                            element_order=order, volume_optimizer=optimizer)
        assert error.value.code == ("mesh_topology" if damage == "tet" else "boundary_changed")
        assert events == ["generate", "netgen"]
        diagnostic = json.loads(Path(error.value.details["optimization_evidence"]).read_text())
        assert diagnostic["netgen"]["force"] is False and diagnostic["before"]["entities"][0]["type"] == "Volume"
        assert "after" in diagnostic and "failure" in diagnostic
        assert not list((tmp_path / "jobs").glob("*/metadata.json")) and source.read_bytes() == original
        return
    result = transport.GmshBackend().generate_surface_volume(source, tmp_path / "jobs", 1., length_unit="mm",
                                                            element_order=order, volume_optimizer=optimizer)
    assert result["source_kind"] == "surface_tet" and "geometry_resource_uuid" not in result
    assert set(result["assets"]) == {"source", "msh", "metadata"} and source.read_bytes() == original
    assert result["source_surface"]["physical_groups"][0]["triangle_ids"] == triangle_ids
    assert result["topology"]["original_nodes_exact"] and result["serialization"]["element_inventory_exact"]
    assert result["quality"]["passed"] and result["affine"]["passed"]
    assert result["status"] == "quality_passed"
    assert result["topology"]["sdk"]["original_nodes_exact"] and result["topology"]["written"]["original_nodes_exact"]
    assert result["serialization"]["maximum_coordinate_error_ulps"] == 0
    assert options["Mesh.Renumber"] == 0 and options["Mesh.MshFileVersion"] == 4.1
    assert options["Mesh.ElementOrder"] == 1 and options["Mesh.MeshOnlyEmpty"] == 1
    assert result["recipe"]["volume_optimizer"] == optimizer
    assert result["generation"]["volume_optimization"]["netgen"]["performed"] == (optimizer == "netgen")
    assert events == ["generate"] + (["netgen"] if optimizer == "netgen" else []) + ["laplacian"] + (["elevate"] if order == 2 else [])
    if order == 2:
        assert result["affine"]["certified_positive"] and result["affine"]["midpoint_within_ulp_budget"]
        assert [block["element_type"] for block in result["mesh"]["blocks"]] == [9, 11]
        rows = result["generation"]["elevation"]["element_id_mapping"]
        assert len(rows) == 5 and all(row["elevated_id"] == row["parent_id"] + 10000 for row in rows)
        assert all(row["restored_id"] == row["parent_id"] for row in rows)
    assert json.loads(Path(result["assets"]["metadata"]).read_text())["quality"]["passed"]
