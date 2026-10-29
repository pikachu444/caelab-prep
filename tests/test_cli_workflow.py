import json
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
