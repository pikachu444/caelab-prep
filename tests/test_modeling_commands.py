"""The public modeling form and independent-session CLI share real commands."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.contracts import OperationRequest
from caelab_prep.application.rad_provider import RadProvider
from caelab_prep.cae_core import PrepError

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "examples/rad/shell_panels_0000.rad"


def cli(*args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run([sys.executable, "-m", "caelab_prep.cli", *map(str, args)],
                            capture_output=True, text=True, env=env, timeout=30)
    return result.returncode, json.loads(result.stdout)


def test_cli_create_assign_reopen_native_relations(tmp_path):
    stage1, stage2, stage3 = (tmp_path / name for name in ("material.caeprep", "section.caeprep", "assigned.caeprep"))
    code, result = cli("model", MODEL, "material.create", "--set", "name=User steel", "--set", "native_id=41",
                       "--set", "density=7.91e-9", "--set", "young_modulus=203456", "--set", "poisson_ratio=0.287",
                       "--output", stage1)
    assert code == 0, result
    assert result["operation"]["object"]["native_scope"] == "/MAT/LAW1/41"
    code, result = cli("model", stage1, "section.create", "--set", "name=Thin sheet", "--set", "native_id=207",
                       "--set", "thickness=2.375", "--output", stage2)
    assert code == 0, result
    code, result = cli("model", stage2, "part.assign", "--target", "/PART/2", "--set", "material=/MAT/LAW1/41",
                       "--set", "property=/PROP/SHELL/207", "--output", stage3)
    assert code == 0, result
    native = tmp_path / "export" / "assembly_0000.rad"
    code, result = cli("export", stage3, "--output", native)
    assert code == 0, result
    # Fixed-width PART oracle, independent of the provider's own reference query.
    lines = native.read_text().splitlines()
    assignment = lines[lines.index("/PART/2") + 2]
    assert int(assignment[:10]) == 207 and int(assignment[10:20]) == 41
    other = lines[lines.index("/PART/1") + 2]
    assert (int(other[:10]), int(other[10:20])) == (1, 1)


def test_operation_snapshot_rejects_stale_and_replaced_document_without_mutation():
    session = PrepSession(); session.open_rad(str(MODEL))
    provider = RadProvider(session)
    spec = provider.operation_spec("material.create")
    values = {field.name: field.value for field in spec.fields}
    values.update(name="New material", density=7.8e-9, young_modulus=210000, poisson_ratio=.3)
    request = OperationRequest(spec.key, values, spec.document_id, spec.expected_revision)
    created = provider.execute_operation(request)
    before = session.describe()
    with pytest.raises(PrepError) as error:
        provider.execute_operation(request)
    assert error.value.code == "revision_conflict" and session.describe() == before
    assert provider.properties(created["object"])
    session.open_rad(str(MODEL))
    before = session.describe()
    with pytest.raises(PrepError) as error:
        provider.execute_operation(replace(request, expected_revision=before["revision"]))
    assert error.value.code == "document_conflict" and session.describe() == before


def test_cli_describe_and_invalid_form_do_not_create_output(tmp_path):
    code, form = cli("model", MODEL, "material.create", "--describe")
    assert code == 0 and form["key"] == "material.create"
    assert {field["name"] for field in form["fields"]} >= {"density", "young_modulus", "poisson_ratio"}
    output = tmp_path / "invalid.caeprep"
    code, result = cli("model", MODEL, "material.create", "--set", "density=1", "--set", "density=2", "--output", output)
    assert code == 1 and "error" in result and not output.exists()
