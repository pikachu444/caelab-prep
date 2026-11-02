"""Owned Windows native input/part-mass check; not contact response qualification."""
import ctypes
import argparse
from hashlib import file_digest
import json
import math
import os
from pathlib import Path
import re
import subprocess

from caelab_prep.application import PrepSession

repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--solver-root", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = args.solver_root.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
ctypes.windll.kernel32.SetErrorMode(2)  # This owned process: no loader error dialog.
summary = {"scope": "Windows Starter/Engine input read and stopped-model mass; no physical response qualification", "models": {}}
def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()
binaries = {stage: root / "exec" / (stage + "_win64.exe") for stage in ("starter", "engine")}
summary["executables"] = {stage: {"path": str(path), "sha256": sha(path)} for stage, path in binaries.items()}
for name in ("beam_shell_tet", "truss_shell_hex"):
    folder = out / name
    folder.mkdir(exist_ok=True)
    session = PrepSession()
    session.open_rad(repo / "scripts/evaluation/models/mixed-assemblies" / name / "model_0000.rad")
    mechanical = [node for node in session.mesh_view()["node_ids"] if node != 6 or name != "beam_shell_tet"]
    group = session.create_node_group("Mechanical nodes", mechanical)["card_id"]
    session.create_boundary_condition("All fixed", group, [True]*3, [True]*3)
    positions = {2: (11, 0, 0)} if name == "beam_shell_tet" else {5:(0,0,11),6:(10,0,11),7:(10,10,11),8:(0,10,11),9:(-10,10,11)}
    updates = [{"reference": session.resolve_entity_reference("node", node)["reference"], "position": xyz} for node, xyz in positions.items()]
    plan = session.plan_node_move(updates, length_unit="mm")
    session.apply_node_move(plan["plan_id"])
    for card_id, item in session.mesh_relationships()["stale_targets"].items():
        mapping = {node: session.resolve_entity_reference("node", node)["reference"] for node in item["members"]}
        session.reconnect_mesh_targets({card_id: {"mesh_revision": item["mesh_revision"], "mapping": mapping}})
    session.export_solver_inputs(folder / "moved_0000.rad", 1e-7, 5e-8)
    environment = dict(os.environ, OPENRADIOSS_PATH=str(root), OPENCOURANT_PATH=str(root),
                       RAD_CFG_PATH=str(root / "hm_cfg_files"), OMP_NUM_THREADS="1", OMP_STACKSIZE="400m", PWD=str(folder))
    record = summary["models"][name] = {"stages": {}}
    for stage, suffix in (("starter", "0000"), ("engine", "0001")):
        command = [str(binaries[stage]), "-i", "moved_" + suffix + ".rad"]
        if stage == "starter":
            command.extend(("-np", "1"))
        try:
            process = subprocess.run(command, cwd=folder, env=environment, capture_output=True, timeout=30)
            (folder / (stage + ".log")).write_bytes(process.stdout + process.stderr)
            text = (process.stdout + process.stderr).decode(errors="replace")
            record["stages"][stage] = {"returncode": process.returncode, "normal": bool(re.search(r"^\s*NORMAL TERMINATION\s*$", text, re.M))}
        except (OSError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.TimeoutExpired):
                (folder / (stage + ".log")).write_bytes((error.stdout or b"") + (error.stderr or b""))
            record["stages"][stage] = {"error": str(error), "normal": False}
        if not record["stages"][stage]["normal"] or record["stages"][stage].get("returncode") != 0:
            summary["status"] = "native_execution_failed"
            (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(json.dumps(summary, indent=2))
            raise SystemExit(1)
    listing = (folder / "moved_0000.out").read_text(errors="replace")
    masses = {int(match[1]):float(match[2]) for match in re.finditer(r"PART\s*:\s*(\d+),[^\n]*\n[^\n]*Mass[^\n]*\n\s*(\S+)", listing)}
    expected = {9:8.19e-7,10:7.02e-8,11:1.3e-6} if name == "beam_shell_tet" else {9:7.8e-7,10:7.8e-8,11:8.58e-6}
    record["masses"] = masses
    record["expected"] = expected
    assert set(masses) == set(expected) and all(math.isclose(masses[key], value, rel_tol=1e-8) for key, value in expected.items())
summary["status"] = "passed"
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
