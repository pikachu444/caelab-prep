"""Run the fixed F2 cases; failure or timeout exits nonzero.

Use an environment with the pinned Gmsh SDK installed. This script downloads
nothing and does not implement a product admission/native-export path.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

RECIPE_SHA256 = "8ebf10dc5f97536896744199993c7f3df6396f3b1da89461223b908bfabd954a"
LOCKED_INPUTS = {
    "contract.json": "80030ae1d2111ca2e2777235ac146241a000d406f0f2bdc455de55569548918d",
    "public-inputs.json": "47b68120a5293bde36451a5e85d88f70ef57cb151852499e301a0b8c387763ec",
    "holdout-inputs.json": "67577e6f3a2c20635b28046b92e291d34d1704f9fe8c0a12f3ab08c77a08a638",
}
ORACLE_SHA256 = "984efa88711ab8f298684539f8f3ce893bcefab16fa758e5c27f9c051560a6a8"
EXPECTED_REJECTIONS = {
    "L-U1": "unique short arc",
    "Q-U1": "strict convex",
    "H-U1": "unsupported or missing recipe fields",
}

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def child(case_path, folder, recipe_path, contract_path):
    from independent_oracle import verify
    case, contract = load(case_path), load(contract_path)
    assert digest(recipe_path) == RECIPE_SHA256, "recipe changed"
    module_spec = importlib.util.spec_from_file_location("frozen_f2_recipe", recipe_path)
    recipe = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(recipe)
    result = dict(case_id=case["id"], family=case["family"], category=case["category"],
                  holdout=case["holdout"], expected_supported=case["expectation"]["supported"],
                  recipe_sha256=digest(recipe_path), case_sha256=digest(case_path))
    started = time.monotonic()
    try:
        sdk = recipe.run(case["input"], folder / "output")
        result["recipe_completed"] = True
        result["sdk"] = {key: sdk[key] for key in (
            "version", "seconds", "min_SICN", "errors", "warnings", "inventory",
            "geometry_kernel", "curve_integration_precision")}
        assert case["expectation"]["supported"], "Unsupported input was silently accepted"
        result["oracle"] = verify(case, folder / "output/mesh.msh", contract)
        assert not sdk["errors"], sdk["errors"]
        assert not sdk["warnings"], ("Unreviewed SDK warning", sdk["warnings"])
        result.update(passed=True, status="supported_pass")
    except ValueError as error:
        result["exception"] = dict(type=type(error).__name__, message=str(error))
        correct = (not case["expectation"]["supported"]
                   and EXPECTED_REJECTIONS.get(case["id"], "!") in str(error)
                   and not (folder / "output/mesh.msh").exists()
                   and not (folder / "output/report.json").exists())
        result.update(passed=correct, status="unsupported_rejected" if correct else "unexpected_error")
        if not correct:
            result["traceback"] = traceback.format_exc()
    except Exception as error:
        result.update(passed=False, status="failure",
                      exception=dict(type=type(error).__name__, message=str(error)),
                      traceback=traceback.format_exc())
    result["child_seconds"] = time.monotonic() - started
    write(folder / "independent-result.json", result)

def run(args):
    bundle = Path(__file__).resolve().parent
    fixture_root, recipe_path, output = args.inputs.resolve(), args.recipe.resolve(), args.output.resolve()
    for filename, expected in LOCKED_INPUTS.items():
        assert digest(fixture_root / filename) == expected, (filename, "locked input/gate changed")
    assert digest(bundle / "independent_oracle.py") == ORACLE_SHA256, "locked oracle changed"
    assert digest(recipe_path) == RECIPE_SHA256, "recipe differs from the frozen second recipe"
    cases = load(fixture_root / "public-inputs.json") + load(fixture_root / "holdout-inputs.json")
    assert len(cases) == 18 and len({case["id"] for case in cases}) == 18
    for family in ("line_arc", "quad", "sweep_hex"):
        group = [case for case in cases if case["family"] == family]
        assert len(group) == 6 and sum(case["expectation"]["supported"] for case in group) == 5
    if args.cases:
        chosen = set(args.cases)
        assert chosen <= {case["id"] for case in cases}, "unknown case ID"
        cases = [case for case in cases if case["id"] in chosen]
    output.mkdir(parents=True, exist_ok=False)
    frozen = output / "recipe.py"
    shutil.copyfile(recipe_path, frozen)
    manifest = dict(recipe_sha256=RECIPE_SHA256, oracle_sha256=ORACLE_SHA256,
                    harness_sha256=digest(__file__), input_sha256=LOCKED_INPUTS,
                    selected_cases=[case["id"] for case in cases],
                    scope="Fixed F2 SDK recipe only; no product/native/Windows claim")
    write(output / "source-lock.json", manifest)
    results = []
    for case in cases:
        folder = output / case["id"]
        folder.mkdir()
        case_path = folder / "case.json"
        write(case_path, case)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--_child", str(case_path),
                 str(folder), str(frozen), str(fixture_root / "contract.json")],
                capture_output=True, text=True, timeout=30)
            elapsed = time.monotonic() - started
            (folder / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
            (folder / "stderr.txt").write_text(completed.stderr, encoding="utf-8")
            result_path = folder / "independent-result.json"
            result = load(result_path) if result_path.exists() else dict(case_id=case["id"], passed=False, status="process_failed")
            result.update(wall_seconds=elapsed, returncode=completed.returncode)
            if completed.returncode or elapsed > 30:
                result.update(passed=False, status="process_or_time_failure")
        except subprocess.TimeoutExpired:
            result = dict(case_id=case["id"], family=case["family"], passed=False,
                          status="timeout", wall_seconds=time.monotonic() - started)
        if "traceback" in result:
            # Public summary retains relative filenames; raw console is a separate artifact.
            result["traceback"] = result["traceback"].replace(str(bundle), "<harness>").replace(str(output), "<output>")
        write(folder / "independent-result.json", result)
        results.append(result)
        print(json.dumps({key: result.get(key) for key in ("case_id", "passed", "status", "wall_seconds", "exception")}), flush=True)
        write(output / "summary.json", dict(**manifest, all_passed=all(item["passed"] for item in results), results=results))
    return 0 if len(results) == len(cases) and all(item["passed"] for item in results) else 1

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--_child":
        child(*map(Path, sys.argv[2:]))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", help="Only explicitly named affected cases; default is all 18")
    return run(parser.parse_args())

if __name__ == "__main__":
    raise SystemExit(main())
