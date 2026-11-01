"""Opt-in external solver checks; no automatic solver download or substitution.

Set CAELAB_STARTER, CAELAB_ENGINE (and optionally CAELAB_TH_TO_CSV).
The Gmsh/OCP SDK must also be installed for the three fresh CAD fixtures.
"""
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess

import pytest

from test_mesh_adoption import _native, _session
from test_mesh_candidates import real_candidate


@pytest.mark.skipif(not (os.environ.get("CAELAB_STARTER") and os.environ.get("CAELAB_ENGINE")),
                    reason="Set CAELAB_STARTER and CAELAB_ENGINE explicitly to run the optional real solver oracle.")
def test_actual_solver_mass_velocity_force_and_energy_balance(real_candidate, tmp_path):
    """A small physical oracle: guided translation with a finite known force.

    CSV precision is six significant digits. Relative limits (mass/momentum
    1e-5, energy balance 1e-4) allow this output rounding and time integration;
    this is not a stress-convergence or nonlinear-contact validation.
    """
    starter, engine_path = os.environ.get("CAELAB_STARTER"), os.environ.get("CAELAB_ENGINE")
    installation = Path(os.environ.get("G3_OPENCOURANT_PATH", str(Path(starter).resolve().parents[1])))
    converter = os.environ.get("CAELAB_TH_TO_CSV", str(installation / "exec" / "th_to_csv_linux64_gf"))
    binaries = [Path(starter), Path(engine_path), Path(converter)]
    assert all(path.is_file() and os.access(path, os.X_OK) for path in binaries), (
        "The explicitly configured Starter, Engine and TH converter must be executable: " + str(binaries))
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
    report = {"node_count": len(nodes), "element_count": len(cells), "mass": mass,
              "initial_velocity_x": speed, "per_node_force_x": 1e-7, "initial_kinetic_energy": initial_ke,
              "row_count": len(rows), "limits": {"mass_relative": 1e-5, "momentum_relative": 1e-5,
                                                   "energy_balance_relative": 1e-4},
              "observations": []}
    for row in rows:
        time = float(row["time"])
        expected_px = initial_px + force * time
        balance = float(row["INTERNAL ENERGY"]) + float(row["KINETIC ENERGY"]) - float(row["EXTERNAL WORK"])
        report["observations"].append({"time": time,
            "mass_relative_error": abs(float(row["MASS"]) - mass) / mass,
            "momentum_relative_error": abs(float(row["X-MOMENTUM"]) - expected_px) / expected_px,
            "energy_balance_relative_error": abs(balance - initial_ke) / initial_ke})
    (tmp_path / "physical-oracle.json").write_text(json.dumps(report, indent=2) + "\n")
    assert len(rows) >= 8 and float(rows[-1]["time"]) >= .8e-5
    assert float(rows[0]["KINETIC ENERGY"]) == pytest.approx(initial_ke, rel=1e-5)
    for row in rows:
        assert float(row["MASS"]) == pytest.approx(mass, rel=1e-5)
        assert float(row["X-MOMENTUM"]) == pytest.approx(initial_px + force * float(row["time"]), rel=1e-5)
        assert float(row["Y-MOMENTUM"]) == 0 and float(row["Z-MOMENTUM"]) == 0
        balance = float(row["INTERNAL ENERGY"]) + float(row["KINETIC ENERGY"]) - float(row["EXTERNAL WORK"])
        assert balance == pytest.approx(initial_ke, rel=1e-4)
