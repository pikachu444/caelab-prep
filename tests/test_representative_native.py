"""Runner/oracle regression only; these small fixtures are not a solver run."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/evaluation/representative_native.py"
spec = importlib.util.spec_from_file_location("representative_native", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def small_input(path):
    units = "".join(f"{value:>20}" for value in ("Mg", "mm", "s"))
    rows = ["#RADIOSS STARTER", "/BEGIN", "Small independent oracle fixture", f"{2024:10}{0:10}", units, units,
            "/MAT/LAW1/41", "Steel", f"{7.8e-9:20g}", f"{210000:20g}{.3:20g}",
            "/PROP/SOLID/207", "Linear tetrahedron", "".join(f"{value:10}" for value in (1,4,0,0,0,0,1000,1))+f"{0:20g}",
            "".join(f"{value:20g}" for value in (1.1,.05,.1,0,0)), "".join(f"{0:20g}" for _ in range(5)),
            "/NODE", "# original provenance"]
    for identifier, xyz in enumerate(((0,0,0),(1,0,0),(0,1,0),(0,0,1)), 1):
        rows.append(f"{identifier:10}"+"".join(f"{value:20g}" for value in xyz))
    rows += ["/PART/1", "Body", f"{207:10}{41:10}{0:10}", "/TETRA4/1", f"{11:10}{1:10}{2:10}{3:10}{4:10}",
             "/GRNOD/NODE/47", "Every node", "".join(f"{value:10}" for value in (1,2,3,4)),
             "/FUNCT/63", "Inactive curve", f"{0:20g}{0:20g}", f"{1e-5:20g}{1:20g}",
             "/BCS/83", "Guide", "   011 111"+f"{0:10}{47:10}",
             "/INIVEL/TRA/89", "Motion", f"{2.5:20g}{0:20g}{0:20g}{47:10}{0:10}", "/END"]
    path.write_text("\n".join(rows)+"\n", encoding="latin1")
    return path


def test_oracle_excludes_only_titles_comments_and_line_endings(tmp_path):
    path = small_input(tmp_path / "input.rad")
    expected = runner.native_oracle(path)
    assert expected["nodes"] == expected["group_count"] == 4
    assert expected["elements"] == expected["parts"] == 1
    assert expected["mass_Mg"] == pytest.approx(7.8e-9/6)
    original = path.read_text()
    path.write_bytes(original.replace("Body", "Another title").replace("# original provenance", "# new UUID").replace("\n", "\r\n").encode())
    assert runner.native_oracle(path)["semantic_sha256"] == expected["semantic_sha256"]


@pytest.mark.parametrize("change", ["coordinates", "elastic_modulus", "fixed_columns"])
def test_semantic_hash_detects_native_values_and_column_positions(tmp_path, change):
    path = small_input(tmp_path / "input.rad")
    before = runner.native_oracle(path)["semantic_sha256"]
    raw = path.read_text()
    if change == "coordinates":
        raw = raw.replace(f"{2:10}{1:20g}{0:20g}{0:20g}", f"{2:10}{1.0000001:20.9g}{0:20g}{0:20g}")
    elif change == "elastic_modulus":
        raw = raw.replace(f"{210000:20g}{.3:20g}", f"{210001:20g}{.3:20g}")
    else:
        raw = raw.replace(f"{1000:10}{1:10}{0:20g}", f"{0:10}{1000:10}{1:20g}")
    path.write_text(raw)
    assert runner.native_oracle(path)["semantic_sha256"] != before


@pytest.mark.parametrize("change", ["truncated_group", "frame", "active_load", "units"])
def test_wrong_conditions_are_rejected_before_native_execution(tmp_path, change):
    path = small_input(tmp_path / "input.rad")
    raw = path.read_text()
    if change == "truncated_group":
        raw = raw.replace("Every node\n"+"".join(f"{value:10}" for value in (1,2,3,4)), "Every node\n"+f"{1:10}{2:10}{3:10}")
    elif change == "frame":
        raw = raw.replace("   011 111"+f"{0:10}{47:10}", "   011 111"+f"{7:10}{47:10}")
    elif change == "active_load":
        raw = raw.replace("/END", "/CLOAD/81\nUnexpected active load\n/END")
    else:
        raw = raw.replace(f"{'mm':>20}", f"{'m':>20}", 1)
    path.write_text(raw)
    with pytest.raises(ValueError):
        runner.native_oracle(path)


def test_partial_good_history_never_implies_normal_termination(tmp_path):
    csv = tmp_path / "partial.csv"
    csv.write_text("time,MASS,X-MOMENTUM,Y-MOMENTUM,Z-MOMENTUM,KINETIC ENERGY,INTERNAL ENERGY,EXTERNAL WORK\n0,1,2.5,0,0,3.125,0,0\n0.000004,1,2.5,0,0,3.125,0,0\n")
    result = runner.history_oracle(csv, {"mass_Mg": 1, "initial_momentum_Mg_mm_s": 2.5, "initial_energy_N_mm": 3.125})
    assert result["within_limits"] is True
    assert result["history_reaches_expected_window"] is False
    assert result["normal_termination_inferred"] is False


@pytest.mark.parametrize("directive", ["#include extra.rad", "#ENDDATA", "  # Include extra.rad"])
def test_native_directives_are_not_discarded_as_provenance_comments(tmp_path, directive):
    path = small_input(tmp_path / "input.rad")
    path.write_text(path.read_text().replace("/NODE", directive+"\n/NODE"))
    with pytest.raises(ValueError, match="directives"):
        runner.native_oracle(path)


def test_starter_magic_is_required_even_though_other_comments_are_excluded(tmp_path):
    path = small_input(tmp_path / "input.rad")
    path.write_text(path.read_text().replace("#RADIOSS STARTER", "# arbitrary comment"))
    with pytest.raises(ValueError, match="magic"):
        runner.native_oracle(path)


@pytest.mark.parametrize("times", [[9e-6]*8, [0, 0, 9e-6], [0, 9e-6, 8e-6], [0, 11e-6]])
def test_history_requires_initial_advancing_times_within_case_window(tmp_path, times):
    path = tmp_path / "history.csv"
    path.write_text("time,MASS,X-MOMENTUM,Y-MOMENTUM,Z-MOMENTUM,KINETIC ENERGY,INTERNAL ENERGY,EXTERNAL WORK\n"+
                    "".join(f"{value},1,2.5,0,0,3.125,0,0\n" for value in times))
    with pytest.raises(ValueError):
        runner.history_oracle(path, {"mass_Mg": 1, "initial_momentum_Mg_mm_s": 2.5, "initial_energy_N_mm": 3.125})


@pytest.mark.parametrize("text,normal,zero", [
    (" NORMAL TERMINATION\n 0 ERROR(S)\n 0 WARNING(S)\n", True, True),
    ("ABNORMAL TERMINATION\n0 ERROR(S)\n0 WARNING(S)\n", False, True),
    ("NORMAL TERMINATION\n10 ERROR(S)\n0 WARNING(S)\n", True, False),
    ("NORMAL TERMINATION\n0 ERROR(S)\n10 WARNING(S)\n", True, False),
    ("ERROR TERMINATION\nNORMAL TERMINATION\n", False, False),
    ("normal-looking output without native summary", False, False),
])
def test_termination_gates_do_not_accept_substring_false_positives(text, normal, zero):
    result = runner.termination_receipt(text)
    assert result["normal_termination"] is normal
    assert result["zero_error_warning_summary"] is zero


@pytest.mark.skipif(os.name != "posix", reason="The diagnostic runner targets Linux CI")
def test_process_failure_preserves_original_returncode_output_and_hash(tmp_path):
    log = tmp_path / "process.log"
    result = runner.run_process([sys.executable, "-c", "print('NORMAL TERMINATION'); raise SystemExit(3)"], tmp_path, dict(os.environ), log, time.monotonic()+5)
    assert result["returncode"] == 3 and result["normal_termination"] is True
    assert result["log_sha256"] == runner.sha(log) and result["binary_sha256"] == runner.sha(sys.executable)


@pytest.mark.skipif(os.name != "posix", reason="The diagnostic runner targets Linux CI")
def test_process_budget_terminates_and_reaps_process(tmp_path):
    log = tmp_path / "timeout.log"
    result = runner.run_process([sys.executable, "-c", "import time; print('started',flush=True); time.sleep(10)"], tmp_path, dict(os.environ), log, time.monotonic()+.2)
    assert result["timed_out"] and result["returncode"] < 0 and result["seconds"] < 3
    assert "started" in log.read_text()


def test_published_reference_identifies_original_gui_input_without_large_assets():
    reference = json.loads(runner.REFERENCE.read_text())
    assert reference["source_sha256"] == runner.SOURCE_SHA
    assert reference["oracle"]["nodes"] == reference["oracle"]["group_count"] == 16645
    assert reference["oracle"]["elements"] == 64308 and reference["oracle"]["parts"] == 18
    assert reference["original_gui_sha256"]["assembly_0000.rad"] == "53d5439ed04b12c99886a9d3746a6e69983a4d5d1d0bf33f5ef8a7c0484c88f2"


def test_missing_binary_preflight_is_recorded_as_failure(tmp_path):
    runner.write_json(tmp_path / "prepare.json", {"status": "prepared", "semantic_match": True})
    with pytest.raises(ValueError, match="binaries"):
        runner.run(tmp_path, tmp_path / "missing-solver", budget=1)
    report = json.loads((tmp_path / "native-run.json").read_text())
    assert report["status"] == "failed" and "binaries" in report["error"]
    assert not report["variants"] and report["native_seconds"] >= 0
