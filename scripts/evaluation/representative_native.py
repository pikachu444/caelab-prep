"""Portable N11 native diagnostic; this is not a GUI or solver-fix claim.

Install the pinned project CAD extra (Gmsh 4.15.2), then::

  python scripts/evaluation/representative_native.py prepare --output evidence
  python scripts/evaluation/representative_native.py run --output evidence \
      --solver-root /path/to/OpenCourant --budget 120

The public STEP is bundled in the pinned Gmsh SDK wheel. Its hash is checked.
Preparation uses the production candidate/adoption/case APIs. Native runs use
the exact exported Engine first; a separate observation run adds only TFILE.
No solver is downloaded, patched or shimmed. Inputs, logs, hashes and partial
history remain evidence even on failure. Upload evidence/, not solver binaries.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback

SOURCE_SHA = "d40db2ed6f741d2955329f9751c7e3e0a14cbfeb4e11d8338cf110765b9042f9"
REFERENCE = Path(__file__).with_name("representative_native_reference.json")
SCOPE = "Public 18-body disconnected assembly; uniform X translation and Y/Z guide. No GUI, stress, contact, convergence or Windows claim."


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def code_receipt():
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, text=True, timeout=5)
        revision = result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        revision = None
    return {"checkout_revision": revision, "runner_sha256": sha(__file__), "reference_sha256": sha(REFERENCE)}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def native_oracle(path):
    """Independent fixed-width reader; does not use the production RAD parser.

    Semantic digest excludes only card titles and comments (UUID provenance).
    It includes every keyword, numeric field, connectivity and condition row.
    """
    blocks = {}
    current = None
    lines = Path(path).read_text(encoding="latin1").splitlines()
    check(bool(lines) and lines[0].strip() == "#RADIOSS STARTER", "Missing native Starter magic header")
    for line in lines:
        check(not re.match(r"\s*#\s*(?:include|enddata)\b", line, re.I),
              "File/include/enddata directives are outside this one-root diagnostic")
        if line.startswith("/"):
            check(line not in blocks, "Repeated native block")
            current = line
            blocks[current] = []
        elif current and line.strip() and not line.lstrip().startswith("#"):
            blocks[current].append(line)
    allowed = {"/BEGIN", "/END", "/NODE", "/GRNOD/NODE/47", "/FUNCT/63", "/BCS/83", "/INIVEL/TRA/89"}
    check(all(key in allowed or key.startswith(("/PART/", "/TETRA4/", "/MAT/LAW1/", "/PROP/SOLID/")) for key in blocks),
          "Unexpected native card: inactive load or unsupported model/control")
    check(allowed <= blocks.keys(), "Missing expected model/condition blocks")
    check(blocks["/BEGIN"][2].split() == blocks["/BEGIN"][3].split() == ["Mg", "mm", "s"], "Input/working units changed")
    nodes = {}
    for row in blocks["/NODE"]:
        identifier = int(row[:10])
        check(identifier > 0 and identifier not in nodes, "Invalid/duplicate node")
        nodes[identifier] = tuple(float(row[start:start+20]) for start in (10, 30, 50))
        check(all(math.isfinite(value) for value in nodes[identifier]), "Nonfinite node")
    parts = {int(key.split("/")[2]): (int(rows[1][:10]), int(rows[1][10:20]))
             for key, rows in blocks.items() if key.startswith("/PART/")}
    materials = {int(key.split("/")[3]): [float(rows[1][:20]), float(rows[2][:20]), float(rows[2][20:40])]
                 for key, rows in blocks.items() if key.startswith("/MAT/LAW1/")}
    cells, volumes = {}, {part: 0.0 for part in parts}
    for key, rows in blocks.items():
        if not key.startswith("/TETRA4/"):
            continue
        part = int(key.split("/")[2])
        check(part in parts, "Element has no PART")
        for row in rows:
            identifier = int(row[:10])
            connection = tuple(int(row[start:start+10]) for start in (10, 20, 30, 40))
            check(identifier > 0 and identifier not in cells and len(set(connection)) == 4, "Invalid/duplicate tetrahedron")
            cells[identifier] = (part, connection)
            points = [nodes[node] for node in connection]
            a, b, c = [tuple(point[i]-points[0][i] for i in range(3)) for point in points[1:]]
            volume = (a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0]) + a[2]*(b[0]*c[1]-b[1]*c[0])) / 6
            check(math.isfinite(volume) and volume > 0, "Nonpositive tetrahedral volume")
            volumes[part] += volume
    group = [int(row[start:start+10]) for row in blocks["/GRNOD/NODE/47"][1:] for start in range(0, len(row), 10) if row[start:start+10].strip()]
    check(len(group) == len(nodes) and len(set(group)) == len(group) and set(group) == set(nodes), "Group 47 must contain every physical node exactly once")
    bcs, velocity = blocks["/BCS/83"][1], blocks["/INIVEL/TRA/89"][1]
    check(bcs[3:6] == "011" and bcs[7:10] == "111" and int(bcs[10:20]) == 0 and int(bcs[20:30]) == 47, "BCS differs from the guided-translation case")
    check([float(velocity[start:start+20]) for start in (0, 20, 40)] == [2.5, 0, 0] and int(velocity[60:70]) == 47 and int(velocity[70:80]) == 0, "Initial velocity/group/frame changed")
    semantic = {}
    for key, rows in sorted(blocks.items()):
        data = rows if key == "/NODE" or key.startswith("/TETRA4/") else rows[1:]
        # Keep exact native field positions and decimal strings. In particular,
        # do not round regenerated coordinates to make a different mesh pass.
        semantic[key] = data
    digest = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    mass = sum(volumes[part] * materials[parts[part][1]][0] for part in parts)
    return {"semantic_sha256": digest, "nodes": len(nodes), "elements": len(cells), "parts": len(parts),
            "materials": materials, "part_assignments": parts, "volume_mm3_by_part": volumes,
            "group_count": len(group), "mass_Mg": mass, "speed_mm_s": 2.5,
            "initial_momentum_Mg_mm_s": mass * 2.5, "initial_energy_N_mm": .5 * mass * 2.5**2}


def bundled_source():
    distribution = metadata.distribution("gmsh")
    check(distribution.version == "4.15.2", "Use pinned Gmsh 4.15.2")
    matches = [distribution.locate_file(item) for item in distribution.files or ()
               if str(item).endswith("examples/boolean/as1-tu-203.stp")]
    check(len(matches) == 1, "Pinned Gmsh SDK asset missing; pass --source explicitly")
    return Path(matches[0])


def prepare(output, source=None, candidate_path=None):
    from caelab_prep.adapters.gmsh_backend import GmshBackend
    from caelab_prep.application import PrepSession
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {"scope": SCOPE, "status": "preparing", "source_sha256": SOURCE_SHA,
              "code": code_receipt(),
              "host": {"platform": platform.platform(), "python": sys.version}, "timings_seconds": {},
              "recipe": {"gmsh": "4.15.2", "size_mm": 4, "dimension": 3, "interface_policy": "independent", "threads": 1}}
    try:
        report["installed_gmsh"] = metadata.version("gmsh")
        check(report["installed_gmsh"] == "4.15.2", "Use pinned Gmsh 4.15.2")
        if candidate_path:
            candidate_path = Path(candidate_path).resolve()
            saved = json.loads(candidate_path.read_text())
            check(saved["source"]["sha256"] == SOURCE_SHA and saved["backend"]["version"] == "4.15.2", "Candidate source/version differs")
            check(saved["recipe"]["global_size"] == 4 and saved["recipe"]["dimension"] == 3
                  and saved["recipe"]["interface_policy"] == "independent" and not saved["recipe"]["local_sizes"], "Candidate recipe differs")
            result = candidate_path
            report["candidate_origin"] = "Explicit saved candidate; no fresh meshing claim"
        else:
            source = Path(source) if source else bundled_source()
            check(sha(source) == SOURCE_SHA, "Public STEP digest mismatch")
            result = GmshBackend(timeout=120).generate(source, output / "candidate", 4, dimension=3, interface_policy="independent")
            report["candidate_origin"] = "Fresh production Gmsh worker from pinned public STEP"
        report["timings_seconds"]["candidate_generation_or_lookup"] = time.monotonic()-started
        candidate = read_mesh_candidate(result)
        native = candidate.to_native_mesh()
        report["candidate_assets"] = [{"kind": asset.kind, "sha256": asset.sha256, "bytes": Path(asset.path).stat().st_size} for asset in native.assets]
        report["quality_min_tetra4"] = candidate.quality.minimum("tetra4")
        check((len(native.nodes), len(native.elements), len(native.parts)) == (16645, 64308, 18), "Mesh inventory differs from original GUI input")
        session = PrepSession()
        session.new_document("Public assembly N11 - independent translation", {"mass": "Mg", "length": "mm", "time": "s"})
        steel = session.create_material("Assembly steel", 7.8e-9, 210000, .3, native_id=41)["card_id"]
        solid = session.create_solid_property("Steel solid", native_id=207)["card_id"]
        aluminium = session.create_material("Assembly aluminium", 2.7e-9, 70000, .33, native_id=43)["card_id"]
        second = session.create_solid_property("Aluminium solid", native_id=209)["card_id"]
        adopted = session.adopt_mesh_candidate(native, material_id=steel, property_id=solid)
        session.assign_part(adopted["part_ids"][1], material_id=aluminium, property_id=second)
        group = session.create_node_group("All physical assembly nodes", session.mesh_view()["node_ids"], native_id=47)["card_id"]
        curve = session.create_curve("Inactive verification load curve", [(0, 0), (1e-5, 1)], native_id=63)["card_id"]
        bcs = session.create_boundary_condition("Guide uniform translation in X", group, [False, True, True], [True]*3, native_id=83)["card_id"]
        velocity = session.create_initial_velocity("Uniform 2.5 mm per s", group, [2.5, 0, 0], native_id=89)["card_id"]
        inactive = session.create_load("Defined but inactive load", group, curve, "X", 1e-7, native_id=81)["card_id"]
        case = session.create_analysis_case("Independent translation only", [bcs, velocity], 1e-5, 1e-6, "s")["case_id"]
        session.save_project(output / "assembly.caeprep")
        exported = session.export_analysis_case(output / "inputs" / "assembly_0000.rad", case)
        oracle = native_oracle(exported["starter_path"])
        reference = json.loads(REFERENCE.read_text())
        report.update(oracle=oracle, analysis_case=session.analysis_case(case), inactive_condition_id=inactive,
                      input_sha256={Path(path).name: sha(path) for path in exported["files"]},
                      original_gui_sha256=reference["original_gui_sha256"],
                      semantic_match=oracle["semantic_sha256"] == reference["oracle"]["semantic_sha256"])
        check(report["semantic_match"], "Native semantic digest differs from original GUI output; do not claim an identical reproduction")
        check(report["input_sha256"]["assembly_0001.rad"] == reference["original_gui_sha256"]["assembly_0001.rad"], "Generated Engine differs from original GUI Engine")
        report["status"] = "prepared"
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["timings_seconds"]["total_prepare"] = time.monotonic()-started
        write_json(output / "prepare.json", report)
    return report


def history_oracle(path, expected):
    with Path(path).open() as stream:
        rows = list(csv.DictReader(stream))
    check(bool(rows), "No history rows")
    errors = []
    previous = None
    for row in rows:
        values = {key: float(row[key]) for key in ("time", "MASS", "X-MOMENTUM", "Y-MOMENTUM", "Z-MOMENTUM", "KINETIC ENERGY", "INTERNAL ENERGY", "EXTERNAL WORK")}
        check(all(math.isfinite(value) for value in values.values()), "Nonfinite history")
        current = values["time"]
        check((previous is None and current == 0) or (previous is not None and current > previous),
              "History must start at zero and advance strictly")
        check(current <= 1e-5, "History exceeds the fixed case end time")
        previous = current
        errors.append({"time": values["time"],
            "mass_relative": abs(values["MASS"]-expected["mass_Mg"])/expected["mass_Mg"],
            "momentum_relative": abs(values["X-MOMENTUM"]-expected["initial_momentum_Mg_mm_s"])/expected["initial_momentum_Mg_mm_s"],
            "energy_relative": abs(values["KINETIC ENERGY"]+values["INTERNAL ENERGY"]-values["EXTERNAL WORK"]-expected["initial_energy_N_mm"])/expected["initial_energy_N_mm"]})
        check(values["Y-MOMENTUM"] == values["Z-MOMENTUM"] == 0, "Transverse momentum differs")
    maxima = {key: max(row[key] for row in errors) for key in ("mass_relative", "momentum_relative", "energy_relative")}
    return {"rows": len(rows), "max_time": max(row["time"] for row in errors), "max_errors": maxima,
            "within_limits": maxima["mass_relative"] < 1e-5 and maxima["momentum_relative"] < 1e-5 and maxima["energy_relative"] < 1e-4,
            "history_reaches_expected_window": len(rows) >= 8 and max(row["time"] for row in errors) >= .8e-5,
            "observations": errors, "normal_termination_inferred": False}


def run_process(command, cwd, environment, log, deadline):
    remaining = deadline-time.monotonic()
    check(remaining > 0, "Native diagnostic budget exhausted")
    started = time.monotonic()
    with Path(log).open("wb") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    text = Path(log).read_text(errors="replace")
    return {"argv": command, "returncode": process.returncode, "timed_out": timed_out,
            "seconds": time.monotonic()-started, **termination_receipt(text),
            "log_sha256": sha(log), "binary_sha256": sha(command[0])}


def termination_receipt(text):
    abnormal = bool(re.search(r"\b(?:ABNORMAL|ERROR)\s+TERMINATION\b", text))
    errors = [int(value) for value in re.findall(r"(?<!\d)(\d+)\s+ERROR\(S\)", text)]
    warnings = [int(value) for value in re.findall(r"(?<!\d)(\d+)\s+WARNING\(S\)", text)]
    return {"normal_termination": bool(re.search(r"^\s*NORMAL TERMINATION\s*$", text, re.M)) and not abnormal,
            "abnormal_termination": abnormal, "reported_error_counts": errors, "reported_warning_counts": warnings,
            "zero_error_warning_summary": bool(errors and warnings) and not any(errors+warnings)}


def run(output, solver_root, budget=120):
    check(math.isfinite(budget) and 0 < budget <= 120, "Native budget must be >0 and <=120 seconds")
    output, root = Path(output).resolve(), Path(solver_root).resolve()
    prepared = json.loads((output / "prepare.json").read_text())
    check(prepared["status"] == "prepared" and prepared["semantic_match"], "A verified prepared input is required")
    report = {"scope": SCOPE, "status": "running", "failure_cause": "unresolved", "budget_seconds": budget,
              "code": code_receipt(),
              "host": {"platform": platform.platform(), "python": sys.version, "pid": os.getpid()}, "variants": {}}
    binaries = {key: root / "exec" / name for key, name in (("starter", "starter_linux64_gf"), ("engine", "engine_linux64_gf"), ("converter", "th_to_csv_linux64_gf"))}
    environment = dict(os.environ)
    # Native SDK loader paths and shims from a development host are not carried
    # into this independent run. Use only the official package's loader recipe.
    environment.pop("LD_PRELOAD", None)
    environment.update(OPENCOURANT_PATH=str(root), OPENRADIOSS_PATH=str(root), RAD_CFG_PATH=str(root / "hm_cfg_files"),
        RAD_H3D_PATH=str(root / "extlib/h3d/lib/linux64"), OMP_NUM_THREADS="1", OMP_STACKSIZE="400m",
        LD_LIBRARY_PATH=os.pathsep.join(str(root / path) for path in ("extlib/hm_reader/linux64", "extlib/h3d/lib/linux64")))
    report["environment"] = {key: environment[key] for key in ("OPENCOURANT_PATH", "OPENRADIOSS_PATH", "RAD_CFG_PATH", "RAD_H3D_PATH", "OMP_NUM_THREADS", "OMP_STACKSIZE", "LD_LIBRARY_PATH")}
    report["ld_preload_removed"] = "LD_PRELOAD" in os.environ
    started = time.monotonic()
    deadline = started+budget
    try:
        check(all(path.is_file() and os.access(path, os.X_OK) for path in binaries.values()), "Explicit official solver binaries must be executable")
        for variant in ("exact", "observer"):
            folder = output / variant
            folder.mkdir(exist_ok=False)
            for name, expected in prepared["input_sha256"].items():
                source = output / "inputs" / name
                check(sha(source) == expected, "Prepared input changed after verification")
                shutil.copyfile(source, folder / name)
            engine = folder / "assembly_0001.rad"
            if variant == "observer":
                engine.write_bytes(engine.read_bytes()+b"/TFILE/4\n1e-6\n")
            result = {"input_sha256": {path.name: sha(path) for path in folder.glob("*.rad")}, "runs": [],
                      "observer_change": "TFILE only" if variant == "observer" else "none"}
            report["variants"][variant] = result
            environment["PWD"] = str(folder)
            for label, args in (("starter", ["-i", "assembly_0000.rad", "-np", "1"]), ("engine", ["-i", "assembly_0001.rad"])):
                record = run_process([str(binaries[label]), *args], folder, environment, folder / (label+".log"), deadline)
                record["accepted"] = record["returncode"] == 0 and record["normal_termination"] and (
                    label != "starter" or record["zero_error_warning_summary"])
                result["runs"].append({"stage": label, **record})
                write_json(output / "native-run.json", report)
                if not record["accepted"]:
                    break
            if variant == "observer" and (folder / "assemblyT01").is_file() and time.monotonic() < deadline:
                record = run_process([str(binaries["converter"]), "assemblyT01"], folder, environment, folder / "converter.log", deadline)
                result["runs"].append({"stage": "converter", **record})
                if record["returncode"] == 0 and (folder / "assemblyT01.csv").is_file():
                    result["history"] = history_oracle(folder / "assemblyT01.csv", prepared["oracle"])
            result["artifacts"] = {path.name: {"bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(folder.iterdir()) if path.is_file()}
            result["native_passed"] = all(any(r["stage"] == stage and r["accepted"] for r in result["runs"]) for stage in ("starter", "engine"))
            write_json(output / "native-run.json", report)
        history = report["variants"]["observer"].get("history", {})
        passed = all(value["native_passed"] for value in report["variants"].values()) and history.get("within_limits") and history.get("history_reaches_expected_window")
        report["status"] = "passed" if passed else "failed"
        if passed:
            report["failure_cause"] = "not determined; original host failure preserved, independent runner completed"
    except BaseException:
        report.update(status="failed", error=traceback.format_exc())
        raise
    finally:
        report["native_seconds"] = time.monotonic()-started
        report["budget_exceeded"] = report["native_seconds"] > budget
        if report["budget_exceeded"]:
            report["status"] = "failed"
            report["failure_cause"] = "diagnostic budget exhausted; original native failure cause remains unresolved"
        write_json(output / "native-run.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--output", required=True)
    inputs = prep.add_mutually_exclusive_group()
    inputs.add_argument("--source")
    inputs.add_argument("--candidate")
    native = commands.add_parser("run")
    native.add_argument("--output", required=True)
    native.add_argument("--solver-root", required=True)
    native.add_argument("--budget", type=float, default=120)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("input")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.output, args.source, args.candidate)
    elif args.command == "run":
        result = run(args.output, args.solver_root, args.budget)
    else:
        result = native_oracle(args.input)
    print(json.dumps(result, indent=2))
    return int(result.get("status") == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
