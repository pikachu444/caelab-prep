import json
import os
from pathlib import Path
import subprocess
import sys


def call(*arguments):
    result = subprocess.run([sys.executable, "-m", "caelab_prep", *map(str, arguments)],
                            capture_output=True, text=True)
    return result.returncode, json.loads(result.stdout)


def test_cli_supported_edit_survives_a_new_process(tmp_path):
    source = Path(__file__).parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"
    original = source.read_bytes()
    code, cards = call("fields", source)
    assert code == 0
    header = next(card["keyword"] for card in cards if card["keyword"].startswith("/MAT/"))
    project = tmp_path / "edited.caeprep"
    code, saved = call("edit", source, "--card", header, "--field", "young_modulus",
                       "--value", "205000", "--output", project)
    assert code == 0, saved
    code, fields = call("fields", project, "--card", header)
    assert code == 0
    assert next(field["value"] for field in fields if field["name"] == "young_modulus") == 205000
    output = tmp_path / "edited_0000.rad"
    code, exported = call("export", project, "--output", output)
    assert code == 0, exported
    assert b"205000" in output.read_bytes()
    assert source.read_bytes() == original


def test_cli_invalid_edit_does_not_write_a_project(tmp_path):
    source = Path(__file__).parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"
    output = tmp_path / "invalid.caeprep"
    code, result = call("edit", source, "--card", "/not/a/card", "--field", "young_modulus",
                        "--value", "0", "--output", output)
    assert code != 0 and "error" in result
    assert not output.exists()


def test_cli_structured_error_survives_ascii_stdout(tmp_path):
    source = Path(__file__).parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"
    output = tmp_path / "invalid.caeprep"
    result = subprocess.run(
        [sys.executable, "-m", "caelab_prep", "edit", str(source),
         "--card", "/MAT/PLAS_TAB/1", "--field", "young_modulus", "--value", "0",
         "--output", str(output)], capture_output=True, text=True,
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
    )
    assert result.returncode == 1
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "invalid_value" and error["message"]
    assert not output.exists()


def test_cli_persisted_cases_are_reopened_and_export_distinct_conditions(tmp_path):
    from caelab_prep.application import PrepSession
    from test_condition_workflow import _base_model, _create_conditions

    source = _base_model(tmp_path / "source")
    session = PrepSession(); session.open_rad(str(source))
    refs = _create_conditions(session)
    document = tmp_path / "cases.caeprep"
    session.save_project(str(document))
    code, created = call("case", document, "create", "--name", "Load case", "--end-time", 2,
                         "--output-interval", .25, "--time-unit", "ms", "--condition", refs["load"],
                         "--condition", refs["bcs"], "--output", document)
    assert code == 0, created
    first = created["operation"]["case_id"]
    code, copied = call("case", document, "copy", "--case-id", first, "--name", "Velocity case", "--output", document)
    assert code == 0, copied
    second = copied["operation"]["case_id"]
    code, updated = call("case", document, "update", "--case-id", second, "--end-time", 4,
                         "--condition", refs["velocity"], "--condition", refs["bcs"], "--output", document)
    assert code == 0, updated
    code, cases = call("case", document, "list")
    assert code == 0 and cases["active_case_id"] == second
    assert [item["name"] for item in cases["cases"]] == ["Load case", "Velocity case"]
    outputs = [tmp_path / "a" / "load_0000.rad", tmp_path / "b" / "velocity_0000.rad"]
    for case_id, output in zip((first, second), outputs):
        code, exported = call("case", document, "export", "--case-id", case_id, "--output", output)
        assert code == 0, exported
    assert b"/CLOAD/81" in outputs[0].read_bytes() and b"/INIVEL/TRA/89" not in outputs[0].read_bytes()
    assert b"/CLOAD/81" not in outputs[1].read_bytes() and b"/INIVEL/TRA/89" in outputs[1].read_bytes()
    assert "\n0.002\n" in outputs[0].with_name("load_0001.rad").read_text()
    assert "\n0.004\n" in outputs[1].with_name("velocity_0001.rad").read_text()


def test_cli_case_requires_explicit_activation_and_rejects_export_overrides(tmp_path):
    document = tmp_path / "new.caeprep"
    code, result = call("new", "--name", "Explicit case", "--mass", "Mg", "--length", "mm", "--time", "s", "--output", document)
    assert code == 0, result
    before = document.read_bytes()
    code, result = call("case", document, "create", "--name", "Ambiguous", "--end-time", 1,
                        "--output-interval", .1, "--time-unit", "s", "--output", document)
    assert code == 1 and "--no-conditions" in result["error"]["message"]
    assert document.read_bytes() == before
    output = tmp_path / "must-not-exist_0000.rad"
    code, result = call("case", document, "export", "--end-time", 10, "--output", output)
    assert code == 1 and "saved case settings" in result["error"]["message"]
    assert not output.exists()
