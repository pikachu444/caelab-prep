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
from test_mesh_candidates import real_candidate

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


def test_cli_conditions_use_typed_refs_json_tables_and_real_reopened_native_output(tmp_path):
    from test_condition_workflow import _base_model, _block

    current = _base_model(tmp_path / "input")
    counter = 0

    def operation(key, values=None, target=None):
        nonlocal current, counter
        counter += 1
        output = tmp_path / f"step-{counter}.caeprep"
        args = ["model", current, key]
        if target:
            args.extend(("--target", target))
        for name, value in (values or {}).items():
            args.extend(("--set", name + "=" + json.dumps(value)))
        code, result = cli(*args, "--output", output)
        assert code == 0, result
        current = output
        return result["operation"]

    operation("group.create", dict(name="Support", native_id=47, node_ids=[101, 205, 309, 411]))
    operation("group.create", dict(name="Loaded", native_id=59, node_ids=[501, 605, 709, 811]))
    operation("curve.create", dict(name="Ramp", native_id=63, points=[[0, 0], [.002, 1]]))
    operation("surface.create", dict(name="Lower face", native_id=71, part_ids=["/PART/902"]))
    operation("constraint.create", dict(name="Support", native_id=83, group_id="/GRNOD/NODE/47",
                                         translations=[True, True, True], rotations=[True, True, True]))
    operation("load.create", dict(name="Each node load", native_id=81, group_id="/GRNOD/NODE/59",
                                   curve_id="/FUNCT/63", direction="Z", scale=-.01))
    operation("velocity.create", dict(name="Speed", native_id=89, group_id="/GRNOD/NODE/59", velocity=[0, 0, -1000]))
    operation("contact.create", dict(name="Impact", native_id=97, secondary_group_id="/GRNOD/NODE/59",
                                      main_surface_id="/SURF/PART/71", friction=.17))
    operation("object.edit", {"points": [[0, 0], [.0005, .75], [.002, 1]]}, "/FUNCT/63")
    duplicate = operation("object.copy", {"name": "Alternate ramp"}, "/FUNCT/63")
    duplicate_header = duplicate["object"]["native_scope"]
    operation("object.edit", {"curve_id": duplicate_header, "direction": "Y", "scale": -.025}, "/CLOAD/81")
    operation("object.edit", {"velocity": [12, -3, -456]}, "/INIVEL/TRA/89")
    native = tmp_path / "export" / "conditions_0000.rad"
    code, result = cli("export", current, "--output", native)
    assert code == 0, result
    raw = native.read_bytes()
    assert len(_block(raw, "/FUNCT/63")) == 4
    row = _block(raw, "/CLOAD/81")[1]
    assert int(row[:10]) == int(duplicate_header.split("/")[-1])
    assert row[10:20] == "         Y" and float(row[80:100]) == -.025
    velocity = _block(raw, "/INIVEL/TRA/89")[1]
    assert [float(velocity[i:i+20]) for i in (0, 20, 40)] == [12, -3, -456]
    # Invalid typed references and referenced-object deletion must leave no output.
    for key, target, changes in (("object.delete", duplicate_header, {}),
                                  ("load.create", None, {"group_id": "/SURF/PART/71", "curve_id": duplicate_header}),
                                  ("velocity.create", None, {"group_id": "/GRNOD/NODE/59", "velocity": [0, 1]})):
        rejected = tmp_path / "rejected.caeprep"
        args = ["model", current, key]
        if target:
            args.extend(("--target", target))
        for name, value in changes.items():
            args.extend(("--set", name + "=" + json.dumps(value)))
        code, result = cli(*args, "--output", rejected)
        assert code == 1 and "error" in result and not rejected.exists()


def test_cli_new_real_candidate_adoption_conditions_and_engine_export(real_candidate, tmp_path):
    name, source_result, candidate = real_candidate
    source = tmp_path / "empty.caeprep"
    code, result = cli("new", "--name", "Independent " + name, "--mass", "Mg", "--length", "mm",
                       "--time", "s", "--output", source)
    assert code == 0, result
    material = tmp_path / "material.caeprep"
    code, result = cli("model", source, "material.create", "--set", "native_id=41", "--set", "density=7.8e-9",
                       "--set", "young_modulus=210000", "--output", material)
    assert code == 0, result
    section = tmp_path / "section.caeprep"
    args = ["model", material, "section.create" if candidate.dimension == 2 else "solid_section.create",
            "--set", "native_id=207"]
    if candidate.dimension == 2:
        args.extend(("--set", "thickness=0.1"))
    code, result = cli(*args, "--output", section)
    assert code == 0, result
    current = tmp_path / "adopted.caeprep"
    prop = "/PROP/SHELL/207" if candidate.dimension == 2 else "/PROP/SOLID/207"
    code, result = cli("adopt", section, "--candidate", source_result["assets"]["metadata"],
                       "--material", "/MAT/LAW1/41", "--property", prop, "--output", current)
    assert code == 0, result
    assert result["quality"]["limits"]["minimum_tetrahedron"] == .1
    nodes = list(result["adoption"]["node_id_map"].values())
    grouped = tmp_path / "grouped.caeprep"
    code, result = cli("model", current, "group.create", "--set", "native_id=47",
                       "--set", "node_ids=" + json.dumps(nodes), "--output", grouped)
    assert code == 0, result
    conditioned = tmp_path / "conditioned.caeprep"
    code, result = cli("model", grouped, "velocity.create", "--set", "group_id=/GRNOD/NODE/47",
                       "--set", "velocity=[2.5,0,0]", "--output", conditioned)
    assert code == 0, result
    exported = tmp_path / "export" / "candidate_0000.rad"
    code, result = cli("export", conditioned, "--engine", "--end-time", "0.00001", "--output-interval", "0.000001",
                       "--output", exported)
    assert code == 0, result
    from test_mesh_adoption import _native
    native_nodes, native_elements, parts = _native(exported.read_bytes())
    assert len(native_nodes) == len(candidate.nodes)
    assert len(native_elements) == len(candidate.to_native_mesh().elements)
    assert set(parts.values()) == {(207, 41)}
    engine = exported.with_name("candidate_0001.rad").read_text().splitlines()
    assert engine[1] == "/RUN/candidate/1" and float(engine[2]) == 1e-5
    assert engine[3] == "/ANIM/DT" and list(map(float, engine[4].split())) == [0, 1e-6]
    rejected = tmp_path / "bad-quality.caeprep"
    code, result = cli("adopt", section, "--candidate", source_result["assets"]["metadata"],
                       "--material", "/MAT/LAW1/41", "--property", prop,
                       "--minimum-triangle", "1", "--minimum-tetrahedron", "1", "--output", rejected)
    assert code == 1 and result["error"]["code"] == "mesh_quality" and not rejected.exists()
    if name == "surface":
        identifier = source_result["surfaces"][0]["uuid"]
        code, refined = cli("mesh", source_result["assets"]["xao"], "--dimension", "2", "--size", "1.8",
                            "--interface-policy", "preserve", "--local-size", identifier + "=0.9",
                            "--output", tmp_path / "refined")
        assert code == 0, refined
        assert refined["counts"]["elements"] > source_result["counts"]["elements"]
        request = json.loads(Path(refined["assets"]["metadata"]).with_name("request.json").read_text())
        assert request["local_sizes"] == {identifier: .9} and request["interface_policy"] == "preserve"
