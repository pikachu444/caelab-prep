"""Checks for build input and notice preservation without running a bundler."""

import importlib.util
import json
from pathlib import Path
import sys
import sysconfig
import subprocess

import pytest


spec = importlib.util.spec_from_file_location(
    "build_portable", Path(__file__).parents[1] / "scripts/packaging/build_portable.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_notices_keep_nested_files_with_the_same_basename(tmp_path):
    site = tmp_path / "environment"
    files = [Path("pkg.dist-info/licenses/LICENSE"), Path("pkg.dist-info/licenses/vendor/LICENSE")]
    for item, text in zip(files, ("package terms", "vendor terms")):
        path = site / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    class Distribution:
        metadata = {"Name": "pkg"}

        def locate_file(self, item):
            return site / item

    distribution = Distribution()
    distribution.files = files
    destination = tmp_path / "notices"
    records, missing = builder.collect_notices([distribution], destination, site)
    assert not missing
    assert len(records) == 2
    assert {p.read_text() for p in destination.rglob("LICENSE")} == {"package terms", "vendor terms"}
    assert len({record["sha256"] for record in records}) == 2


@pytest.mark.parametrize("mismatch", ["abi", "module"])
def test_dependency_inventory_rejects_wrong_runtime_or_global_fallback(tmp_path, monkeypatch, mismatch):
    environment = tmp_path / "environment"
    module = environment / "Lib/site-packages/PySide6/__init__.py"
    result = {"abi": sysconfig.get_config_var("SOABI"), "base_prefix": sys.base_prefix,
              "modules": {"PySide6": str(module)}, "distributions": {}}
    if mismatch == "abi":
        result["abi"] = "incompatible-python"
    else:
        result["modules"]["PySide6"] = str(tmp_path / "global/PySide6/__init__.py")
    monkeypatch.setattr(builder.subprocess, "check_output", lambda *args, **kwargs: json.dumps(result))
    with pytest.raises(ValueError, match="Python/ABI|selected dependency environment"):
        builder.dependency_inventory(environment)


def test_packaged_entry_routes_recipe_worker_and_preserves_json_error_protocol(tmp_path):
    source = tmp_path / "missing recipe.json"
    entry = Path(__file__).parents[1] / "scripts/packaging/prep_entry.py"
    result = subprocess.run(
        [sys.executable, str(entry), "-m", "caelab_prep.application.structured_mesh_worker",
         str(source), str(tmp_path / "output")], capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    response = json.loads(result.stdout)
    assert response["ok"] is False and response["error"]["code"] == "structured_mesh_failed"
    assert source.name in response["error"]["message"]
    assert not (tmp_path / "output").exists()
