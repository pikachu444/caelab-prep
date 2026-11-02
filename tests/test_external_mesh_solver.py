"""Opt-in solver oracle for the two independent, CAD-less MSH inputs.

Use the official OpenCourant release pinned by solver-smoke in prep-tests.yml
(OpenRadioss lineage). No solver, CAD source, mesh, or result is simulated here.
Set CAELAB_STARTER/CAELAB_ENGINE and optionally CAELAB_TH_TO_CSV explicitly.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.external_mesh import import_standalone_mesh
from test_external_mesh import SHELL_MSH, SOLID_MSH, gmsh_sdk, session_for
from test_mesh_adoption import _native


PINNED_COMMIT = "cb760c206e346eff12161a2268b134ef9d48a4ef"
pytestmark = pytest.mark.usefixtures("gmsh_sdk")


@pytest.mark.skipif(not (os.environ.get("CAELAB_STARTER") and os.environ.get("CAELAB_ENGINE")),
                    reason="Explicit CAELAB_STARTER/CAELAB_ENGINE required for the pinned real solver.")
@pytest.mark.parametrize("name,text,dimension,coordinates,connections,volume", [
    ("tri22", SHELL_MSH, 2,
     {11: (0, 0, 0), 31: (1, 0, 0), 51: (0, 1, 0),
      101: (3, 0, 0), 131: (4, 0, 0), 151: (3, 1, 0)},
     {501: (11, 31, 51), 901: (101, 131, 151)}, 2 * .5 * .2),
    ("tet41", SOLID_MSH, 3,
     {10: (0, 0, 0), 20: (1, 0, 0), 30: (0, 1, 0),
      40: (0, 0, 1), 50: (0, 0, -1)},
     {402: (10, 20, 30, 40), 403: (10, 30, 20, 50)}, 2 / 6),
], ids=("msh22-triangles", "msh41-tetrahedra"))
def test_imported_tri_and_tet_have_expected_mass_and_rigid_velocity(
        tmp_path, name, text, dimension, coordinates, connections, volume):
    """Check imported geometry and real time-history mass/momentum/energy.

    Volumes above are calculated directly from the independently written MSH
    coordinates: two half-unit-area triangles at thickness .2, or two unit
    tetrahedra of volume 1/6. Product parsers/writers do not define the oracle.
    A uniform 2.5 mm/s initial velocity without applied load gives a rigid
    translation, constant momentum and kinetic energy. This is not a stress
    convergence, contact, or general imported-element validation.
    """
    source = tmp_path / (name + ".msh")
    source.write_text(text, encoding="utf-8")
    original = source.read_bytes()
    candidate = import_standalone_mesh(source, tmp_path / "imports", length_unit="mm")
    native = candidate.to_native_mesh()
    assert candidate.geometry_resource_uuid is None and native.geometry_resource_uuid is None
    assert native.source_kind == "standalone_msh" and native.dimension == dimension
    assert {asset.kind for asset in candidate.assets} == {"msh", "metadata"}
    session, material, section = session_for(dimension)
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert len(adopted["part_ids"]) == 2 and len(adopted["group_id_map"]) == 4
    group = session.create_node_group("All imported physical nodes", list(adopted["node_id_map"].values()))["card_id"]
    session.create_boundary_condition("Guide global X", group, [False, True, True], [True, True, True])
    session.create_initial_velocity("Uniform imported-mesh speed", group, [2.5, 0, 0])
    project = tmp_path / "imported.prep"
    session.save_project(project)
    reopened = PrepSession(); reopened.open_project(project)
    end_time, sample_interval, speed = 1e-5, 1e-6, 2.5
    output = reopened.export_solver_inputs(tmp_path / "motion_0000.rad", end_time, sample_interval)

    # Native-file readback is independent of the product's deck reader.
    nodes, elements, parts = _native(Path(output["starter_path"]).read_bytes())
    assert len(nodes) == len(coordinates) and len(elements) == 2 and len(parts) == 2
    for identifier, xyz in coordinates.items():
        assert nodes[adopted["node_id_map"][identifier]] == pytest.approx(xyz)
    for identifier, connection in connections.items():
        assert elements[adopted["element_id_map"][identifier]][1] == tuple(
            adopted["node_id_map"][node] for node in connection)
    assert source.read_bytes() == original
    engine_file = Path(output["engine_path"])
    (tmp_path / "engine-as-generated.rad").write_bytes(engine_file.read_bytes())
    # Observation frequency only; retain the exact generated Engine separately.
    engine_file.write_bytes(engine_file.read_bytes() + b"/TFILE/4\n1e-6\n")

    starter = Path(os.environ["CAELAB_STARTER"])
    engine = Path(os.environ["CAELAB_ENGINE"])
    installation = Path(os.environ.get("G3_OPENCOURANT_PATH", str(starter.resolve().parents[1])))
    converter = Path(os.environ.get("CAELAB_TH_TO_CSV", str(installation / "exec/th_to_csv_linux64_gf")))
    executables = {"starter": starter, "engine": engine, "converter": converter}
    assert all(path.is_file() and os.access(path, os.X_OK) for path in executables.values())
    environment = dict(os.environ, PWD=str(tmp_path), OPENCOURANT_PATH=str(installation),
                       RAD_CFG_PATH=str(installation / "hm_cfg_files"),
                       RAD_H3D_PATH=str(installation / "extlib/h3d/lib/linux64"),
                       OMP_NUM_THREADS="1", OMP_STACKSIZE="400m")
    environment["LD_LIBRARY_PATH"] = os.pathsep.join([
        str(installation / "extlib/hm_reader/linux64"), str(installation / "extlib/h3d/lib/linux64")])
    stdout = {}
    for label, arguments in (("starter", ["-i", "motion_0000.rad", "-np", "1"]),
                             ("engine", ["-i", "motion_0001.rad"]),
                             ("converter", ["motionT01"])):
        run = subprocess.run([str(executables[label]), *arguments], cwd=tmp_path, env=environment,
                             capture_output=True, text=True, timeout=30)
        (tmp_path / (label + ".stdout.log")).write_text(run.stdout + run.stderr)
        assert run.returncode == 0, run.stdout + run.stderr
        stdout[label] = run.stdout
        if label in ("starter", "engine"):
            assert "NORMAL TERMINATION" in run.stdout
            assert "CommitID: " + PINNED_COMMIT in run.stdout
    assert "0 ERROR(S)" in stdout["starter"] and "0 WARNING(S)" in stdout["starter"]
    assert int(re.search(r"TOTAL NUMBER OF CYCLES\s*:\s*(\d+)", stdout["engine"])[1]) > 1

    with (tmp_path / "motionT01.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    mass = volume * 7.8e-9
    momentum, kinetic = mass * speed, .5 * mass * speed**2
    observations = []
    for row in rows:
        actual_mass = float(row["MASS"])
        actual_momentum = float(row["X-MOMENTUM"])
        balance = float(row["KINETIC ENERGY"]) + float(row["INTERNAL ENERGY"]) - float(row["EXTERNAL WORK"])
        observations.append({"time": float(row["time"]), "mass": actual_mass,
                             "momentum_x": actual_momentum, "energy_balance": balance,
                             "mass_relative_error": abs(actual_mass - mass) / mass,
                             "momentum_relative_error": abs(actual_momentum - momentum) / momentum,
                             "energy_relative_error": abs(balance - kinetic) / kinetic})
    report = {"input_format": candidate.format_version, "dimension": dimension,
              "source_sha256": hashlib.sha256(original).hexdigest(), "cad_source": None,
              "node_count": len(nodes), "element_count": len(elements), "part_count": len(parts),
              "expected_mass_Mg": mass, "speed_mm_s": speed, "expected_momentum_x": momentum,
              "expected_kinetic_energy": kinetic, "row_count": len(rows),
              "solver_commit": PINNED_COMMIT,
              "executables": {label: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                              for label, path in executables.items()},
              "ld_preload": environment.get("LD_PRELOAD", ""),
              "limits": {"mass_relative": 1e-5, "momentum_relative": 1e-5, "energy_relative": 1e-4},
              "observations": observations}
    (tmp_path / "imported-physics.json").write_text(json.dumps(report, indent=2) + "\n")
    assert len(rows) >= 8 and float(rows[-1]["time"]) >= .8 * end_time
    assert float(rows[0]["KINETIC ENERGY"]) == pytest.approx(kinetic, rel=1e-5, abs=0)
    for row in rows:
        assert float(row["MASS"]) == pytest.approx(mass, rel=1e-5, abs=0)
        assert float(row["X-MOMENTUM"]) == pytest.approx(momentum, rel=1e-5, abs=0)
        assert float(row["Y-MOMENTUM"]) == 0 and float(row["Z-MOMENTUM"]) == 0
        assert float(row["KINETIC ENERGY"]) == pytest.approx(kinetic, rel=1e-4, abs=0)
        balance = float(row["KINETIC ENERGY"]) + float(row["INTERNAL ENERGY"]) - float(row["EXTERNAL WORK"])
        assert balance == pytest.approx(kinetic, rel=1e-4, abs=0)
