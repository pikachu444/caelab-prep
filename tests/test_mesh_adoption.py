"""Real CAD/Gmsh candidates cross the native modeling boundary unchanged.

The optional SDK fixture builds fresh surface, cylinder and two-solid models.
Expected coordinates/connectivity come from the independently inspected MSH;
the exported deck is read with a small fixed-width oracle, not DeckResource.
"""
from __future__ import annotations

from dataclasses import replace
import csv
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_mesh_candidates import real_candidate


def _session(native, length="mm"):
    session = PrepSession()
    session.new_document("Independent mesh adoption", {"mass": "Mg", "length": length, "time": "s"})
    material = session.create_material("Steel", 7.8e-9, 210000, .3, native_id=41)["card_id"]
    section = (session.create_shell_property("Thin sheet", .1, native_id=207) if native.dimension == 2
               else session.create_solid_property("Linear tetra", native_id=207))["card_id"]
    return session, material, section


def _state(session):
    return session.describe()["revision"], tuple((c["id"], session.card_text(c["id"])) for c in session.list_cards())


def _native(raw):
    nodes, cells, parts = {}, {}, {}
    keyword, rows = None, []
    def consume():
        if keyword == "/NODE":
            for row in rows:
                identifier = int(row[:10])
                assert identifier not in nodes
                nodes[identifier] = tuple(float(row[i:i+20]) for i in (10, 30, 50))
        elif keyword and keyword.startswith(("/SH3N/", "/TETRA4/")):
            count = 3 if keyword.startswith("/SH3N/") else 4
            part = int(keyword.split("/")[2])
            for row in rows:
                identifier = int(row[:10])
                assert identifier not in cells
                cells[identifier] = (part, tuple(int(row[i:i+10]) for i in range(10, 10*(count+1), 10)))
        elif keyword and keyword.startswith("/PART/"):
            parts[int(keyword.split("/")[2])] = (int(rows[1][:10]), int(rows[1][10:20]))
    for line in raw.decode("latin1").splitlines():
        if line.startswith("/"):
            consume(); keyword, rows = line, []
        elif line.strip() and not line.lstrip().startswith("#"):
            rows.append(line)
    consume()
    return nodes, cells, parts


def test_real_candidates_adopt_map_append_undo_save_and_export(real_candidate, tmp_path):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    before = _state(session)
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section,
                                            expected_revision=session.describe()["revision"])
    assert session.describe()["element_count"] == len(native.elements)
    assert len(adopted["part_ids"]) == len(native.parts)
    session.undo()
    assert _state(session)[1] == before[1]
    session.redo()
    assert all(any(c["id"] == identifier for c in session.list_cards()) for identifier in adopted["part_ids"])
    first_cards = {c["id"]: session.card_text(c["id"]) for c in session.list_cards()}
    second = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert set(second["node_id_map"].values()).isdisjoint(adopted["node_id_map"].values())
    assert set(second["element_id_map"].values()).isdisjoint(adopted["element_id_map"].values())
    assert all(session.card_text(identifier) == raw for identifier, raw in first_cards.items())
    session.undo()
    assert session.describe()["element_count"] == len(native.elements)
    project = tmp_path / "working.caeprep"
    session.save_project(str(project))
    relocated = tmp_path / "relocated" / "model.caeprep"
    relocated.parent.mkdir(); shutil.copy2(project, relocated)
    reopened = PrepSession(); reopened.open_project(str(relocated))
    output = tmp_path / "export" / "candidate_0000.rad"
    reopened.export_rad(str(output))
    nodes, cells, parts = _native(output.read_bytes())
    assert len(nodes) == len(native.nodes) and len(cells) == len(native.elements)
    assert set(parts.values()) == {(207, 41)}
    part_native = {source: int(next(c["keyword"] for c in reopened.list_cards() if c["id"] == target).split("/")[2])
                   for source, target in adopted["part_id_map"].items()}
    for node in native.nodes:
        assert nodes[adopted["node_id_map"][node.id]] == pytest.approx(node.xyz, rel=1e-12, abs=1e-12)
    for element in native.elements:
        assert cells[adopted["element_id_map"][element.id]] == (
            part_native[element.part_uuid], tuple(adopted["node_id_map"][node] for node in element.node_ids))


def test_unit_mismatch_and_wrong_property_are_atomic(real_candidate):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native, "m")
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert error.value.code == "unit_mismatch" and _state(session) == before
    session, material, section = _session(native)
    wrong = (session.create_solid_property("Wrong solid") if native.dimension == 2 else
             session.create_shell_property("Wrong shell", .1))["card_id"]
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=wrong)
    assert error.value.code == "incompatible_property" and _state(session) == before


def test_changed_native_value_and_condition_referenced_replacement_are_rejected(real_candidate):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    altered = replace(native, nodes=(replace(native.nodes[0], xyz=(999., 0., 0.)), *native.nodes[1:]))
    before = _state(session)
    with pytest.raises(PrepError):
        session.adopt_mesh_candidate(altered, material_id=material, property_id=section)
    assert _state(session) == before
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    group = session.create_node_group("Referenced mesh", list(adopted["node_id_map"].values()))["card_id"]
    session.create_initial_velocity("Uniform speed", group, [2.5, 0, 0])
    before = _state(session)
    with pytest.raises(PrepError):
        session.adopt_mesh_candidate(native, material_id=material, property_id=section,
                                    replace_part_ids=adopted["part_ids"])
    assert _state(session) == before


def test_actual_solver_mass_velocity_force_and_energy_balance(real_candidate, tmp_path):
    """A small physical oracle: guided translation with a finite known force.

    CSV precision is six significant digits. Relative limits (mass/momentum
    1e-5, energy balance 1e-4) allow this output rounding and time integration;
    this is not a stress-convergence or nonlinear-contact validation.
    """
    installation = os.environ.get("G3_OPENCOURANT_PATH")
    if not installation:
        pytest.skip("Set G3_OPENCOURANT_PATH to run the real optional solver oracle.")
    installation = Path(installation)
    binaries = [installation / "exec" / name for name in
                ("starter_linux64_gf", "engine_linux64_gf", "th_to_csv_linux64_gf")]
    if not all(path.is_file() and os.access(path, os.X_OK) for path in binaries):
        pytest.skip("The Starter, Engine and TH converter executables are required.")
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    group = session.create_node_group("All physical nodes", list(adopted["node_id_map"].values()))["card_id"]
    session.create_boundary_condition("Guide in global X", group, [False, True, True], [True, True, True])
    session.create_initial_velocity("Uniform speed", group, [2.5, 0, 0])
    curve = session.create_curve("Constant per-node force", [(0, 1), (1e-5, 1)])["card_id"]
    session.create_load("Each node +1e-7 N", group, curve, "X", 1e-7)
    output = session.export_solver_inputs(str(tmp_path / "motion_0000.rad"), 1e-5, 1e-6)
    engine = Path(output["engine_path"])
    # Preserve the exact generated Engine. Add only observation frequency;
    # neither model definitions nor the integration controls are changed.
    (tmp_path / "engine-as-generated.rad").write_bytes(engine.read_bytes())
    engine.write_bytes(engine.read_bytes() + b"/TFILE/4\n1e-6\n")
    environment = dict(os.environ, PWD=str(tmp_path), OPENCOURANT_PATH=str(installation),
                       RAD_CFG_PATH=str(installation / "hm_cfg_files"),
                       RAD_H3D_PATH=str(installation / "extlib/h3d/lib/linux64"),
                       OMP_NUM_THREADS="1", OMP_STACKSIZE="400m")
    # Isolate the solver from the optional CAD SDK's native dependency bundle.
    # The verified solver launcher uses only its reader/H3D library paths.
    environment["LD_LIBRARY_PATH"] = os.pathsep.join([str(installation / "extlib/hm_reader/linux64"),
        str(installation / "extlib/h3d/lib/linux64")])
    outputs = []
    for executable, args, label in ((binaries[0], ["-i", "motion_0000.rad", "-np", "1"], "starter"),
                                     (binaries[1], ["-i", "motion_0001.rad"], "engine"),
                                     (binaries[2], ["motionT01"], "converter")):
        run = subprocess.run([str(executable), *args], cwd=tmp_path, env=environment,
                             capture_output=True, text=True, timeout=30)
        (tmp_path / (label + ".stdout.log")).write_text(run.stdout + run.stderr)
        assert run.returncode == 0, run.stdout + run.stderr
        outputs.append(run.stdout)
    assert "NORMAL TERMINATION" in outputs[0] and "0 ERROR(S)" in outputs[0] and "0 WARNING(S)" in outputs[0]
    assert "NORMAL TERMINATION" in outputs[1]
    assert int(re.search(r"TOTAL NUMBER OF CYCLES\s*:\s*(\d+)", outputs[1])[1]) > 1
    nodes, cells, _ = _native(Path(output["starter_path"]).read_bytes())
    assert len(nodes) == len(native.nodes) and len(cells) == len(native.elements)
    def difference(a, b): return tuple(x-y for x, y in zip(a, b))
    def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    def dot(a, b): return sum(x*y for x, y in zip(a, b))
    volume = 0.
    for _, connection in cells.values():
        points = [nodes[n] for n in connection]
        normal = cross(difference(points[1], points[0]), difference(points[2], points[0]))
        volume += (math.sqrt(dot(normal, normal)) / 2 * .1 if len(points) == 3 else
                   dot(normal, difference(points[3], points[0])) / 6)
    mass, speed, force = volume * 7.8e-9, 2.5, len(nodes) * 1e-7
    initial_ke, initial_px = .5 * mass * speed**2, mass * speed
    with (tmp_path / "motionT01.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) >= 8 and float(rows[-1]["time"]) >= .8e-5
    assert float(rows[0]["KINETIC ENERGY"]) == pytest.approx(initial_ke, rel=1e-5)
    for row in rows:
        assert float(row["MASS"]) == pytest.approx(mass, rel=1e-5)
        assert float(row["X-MOMENTUM"]) == pytest.approx(initial_px + force * float(row["time"]), rel=1e-5)
        assert float(row["Y-MOMENTUM"]) == 0 and float(row["Z-MOMENTUM"]) == 0
        balance = float(row["INTERNAL ENERGY"]) + float(row["KINETIC ENERGY"]) - float(row["EXTERNAL WORK"])
        assert balance == pytest.approx(initial_ke, rel=1e-4)
