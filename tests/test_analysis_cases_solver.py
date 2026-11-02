"""Opt-in physical check: two saved cases produce different initial momentum.

Uses the same CAELAB_STARTER/ENGINE/TH_TO_CSV contract as solver_generation.
No solver executable is downloaded or simulated by this test.
"""
import csv
import json
import os
from pathlib import Path
import subprocess

import pytest

from caelab_prep.application import PrepSession
from test_condition_workflow import _base_model


@pytest.mark.skipif(not (os.environ.get("CAELAB_STARTER") and os.environ.get("CAELAB_ENGINE")),
                    reason="Explicit CAELAB_STARTER/CAELAB_ENGINE required.")
def test_two_saved_cases_have_distinct_native_physics(tmp_path):
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / "source")))
    group = session.create_node_group("All nodes", [101,205,309,411,501,605,709,811])["card_id"]
    guide = session.create_boundary_condition("Guide X", group, [False,True,True], [True,True,True])["card_id"]
    slow = session.create_initial_velocity("Slow", group, [2.5,0,0])["card_id"]
    fast = session.create_initial_velocity("Fast", group, [5,0,0])["card_id"]
    curve = session.create_curve("Constant", [(0,1), (2e-4,1)])["card_id"]
    load = session.create_load("Per node force", group, curve, "X", 1e-7)["card_id"]
    case_a = session.create_analysis_case("Slow loaded", [guide, slow, load], 100, 10, "mus")["case_id"]
    case_b = session.create_analysis_case("Fast free", [guide, fast], 200, 20, "mus")["case_id"]
    project = tmp_path / "cases.prep"; session.save_project(str(project))
    session = PrepSession(); session.open_project(str(project))
    installation = Path(os.environ.get("G3_OPENCOURANT_PATH", str(Path(os.environ["CAELAB_STARTER"]).resolve().parents[1])))
    environment = dict(os.environ, OPENCOURANT_PATH=str(installation), RAD_CFG_PATH=str(installation/"hm_cfg_files"),
                       RAD_H3D_PATH=str(installation/"extlib/h3d/lib/linux64"), OMP_NUM_THREADS="1", OMP_STACKSIZE="400m")
    environment["LD_LIBRARY_PATH"] = os.pathsep.join([str(installation/"extlib/hm_reader/linux64"),str(installation/"extlib/h3d/lib/linux64")])
    converter = os.environ.get("CAELAB_TH_TO_CSV", str(installation/"exec/th_to_csv_linux64_gf"))
    reports = []
    for case, speed, force, end in ((case_a,2.5,8e-7,1e-4),(case_b,5,0,2e-4)):
        folder = tmp_path / ("slow" if case == case_a else "fast")
        session.select_analysis_case(case)
        result = session.export_analysis_case(str(folder/"motion_0000.rad"))
        engine = Path(result["engine_path"])
        (folder/"engine-as-generated.rad").write_bytes(engine.read_bytes())
        # Observation only: preserve the generated file separately.
        engine.write_bytes(engine.read_bytes() + f"/TFILE/4\n{end/10}\n".encode())
        for executable, args, label in ((os.environ["CAELAB_STARTER"], ["-i","motion_0000.rad","-np","1"],"starter"),
            (os.environ["CAELAB_ENGINE"], ["-i","motion_0001.rad"],"engine"), (converter,["motionT01"],"converter")):
            run = subprocess.run([executable,*args],cwd=folder,env={**environment,"PWD":str(folder)},capture_output=True,text=True,timeout=30)
            (folder/(label+".stdout.log")).write_text(run.stdout+run.stderr)
            assert run.returncode == 0, run.stdout+run.stderr
            if label == "starter": assert "0 ERROR(S)" in run.stdout and "0 WARNING(S)" in run.stdout
            if label in ("starter","engine"): assert "NORMAL TERMINATION" in run.stdout
        with (folder/"motionT01.csv").open() as stream: rows = list(csv.DictReader(stream))
        # Two 10x10 plates, thickness .1, density 7.8e-9 Mg/mm3.
        mass = 2*100*.1*7.8e-9
        assert len(rows) >= 8 and float(rows[-1]["time"]) >= .8*end
        for row in rows:
            assert float(row["MASS"]) == pytest.approx(mass,rel=1e-5)
            assert float(row["X-MOMENTUM"]) == pytest.approx(mass*speed+force*float(row["time"]),rel=1e-5)
        assert float(rows[0]["KINETIC ENERGY"]) == pytest.approx(.5*mass*speed**2,rel=1e-5)
        reports.append({"case_id":case,"speed":speed,"total_force":force,"end_time":end,"mass":mass,
                        "initial_momentum":float(rows[0]["X-MOMENTUM"]),"row_count":len(rows)})
    (tmp_path/"case-physics.json").write_text(json.dumps(reports,indent=2)+"\n")
    assert reports[1]["initial_momentum"] == pytest.approx(2*reports[0]["initial_momentum"],rel=1e-5)
