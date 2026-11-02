from pathlib import Path
import os
import subprocess
import json
import re

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.rad_provider import RadProvider
from caelab_prep.application.contracts import OperationRequest, SetProperties
from caelab_prep.cae_core import PrepError

MODELS = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies"


def opened(name="beam_shell_tet"):
    session = PrepSession(); session.open_rad(MODELS / name / "model_0000.rad")
    return session


def test_incident_fields_combine_and_orientation_node_is_not_a_beam_endpoint():
    session = opened()
    nodes = {value["node_id"]: value for value in session.dof_support([1,2,3,5,6,7])["nodes"]}
    assert len(nodes[1]["rotation_basis"]) == 2
    assert nodes[2]["formulations"] == ["BEAM", "SHELL"] and len(nodes[2]["rotation_basis"]) == 3
    assert nodes[3]["formulations"] == ["SHELL", "TETRA4"] and len(nodes[3]["rotation_basis"]) == 2
    assert nodes[5]["formulations"] == ["BEAM"] and len(nodes[5]["rotation_basis"]) == 3
    assert nodes[6]["translations"] is False and nodes[6]["diagnostics"][0]["code"] == "no_mechanical_attachment"
    assert nodes[7]["translations"] and nodes[7]["rotation_basis"] == []
    other = opened("truss_shell_hex")
    nodes = {value["node_id"]: value for value in other.dof_support([1,8,9])["nodes"]}
    assert nodes[1]["rotation_basis"] == [] and nodes[9]["rotation_basis"] == []
    assert nodes[8]["formulations"] == ["BRICK", "SHELL", "TRUSS"] and len(nodes[8]["rotation_basis"]) == 2


def test_each_group_member_checked_and_fixed_inactive_rotation_is_not_native_invalid():
    session = opened()
    beam = session.create_node_group("Beam", [2,5])["card_id"]
    mixed = session.create_node_group("Beam and pure solid", [2,7])["card_id"]
    curve = session.create_curve("Moment", [(0,0), (1,1)])["card_id"]
    session.create_load("Beam moment", beam, curve, "ZZ", 1)
    before = session.describe()
    with pytest.raises(PrepError) as error: session.create_load("Unsupported solid moment", mixed, curve, "ZZ", 1)
    assert error.value.code == "unsupported_condition_dof" and session.describe() == before
    assert error.value.details["nodes"][0]["node_id"] == 7
    # /BCS permits all-fixed flags; lack of active stiffness is information,
    # not proof that the native constraint syntax is invalid.
    bcs = session.create_boundary_condition("Fixed all", mixed, [True]*3, [True]*3)["card_id"]
    assert session.condition_values(bcs)["rotations"] == [True]*3
    assert session.condition_support(bcs)["diagnostics"][0]["node_id"] == 7


def test_tilted_shell_rotation_subspace_is_not_global_xyz_assumption(tmp_path):
    source = MODELS / "beam_shell_tet"
    copied = tmp_path / "model_0000.rad"; copied.write_bytes((source / "model_0000.rad").read_bytes())
    lines = (source / "mesh.inc").read_text().splitlines()
    # Rotate all source nodes 90 degrees about X: original XY shell becomes XZ.
    for index,line in enumerate(lines):
        if line[:10].strip().isdigit() and len(line) >= 70:
            x,y,z = [float(line[start:start+20]) for start in (10,30,50)]
            lines[index] = line[:10] + f"{x:20g}{-z:20g}{y:20g}"
    (tmp_path / "mesh.inc").write_text("\n".join(lines)+"\n")
    session = PrepSession(); session.open_rad(copied)
    group = session.create_node_group("Shell only", [1])["card_id"]
    curve = session.create_curve("Moment", [(0,0), (1,1)])["card_id"]
    session.create_load("Global Z tangent moment", group, curve, "ZZ", 1)
    with pytest.raises(PrepError): session.create_load("Global Y drilling moment", group, curve, "YY", 1)


def test_q4_drilling_flag_is_not_advertised_as_supported_rotation(tmp_path):
    source = MODELS / "beam_shell_tet"
    raw = (source / "model_0000.rad").read_bytes()
    raw = raw.replace(b"        24         1         2         2", b"         1         1         2         1")
    (tmp_path / "model_0000.rad").write_bytes(raw)
    (tmp_path / "mesh.inc").write_bytes((source / "mesh.inc").read_bytes())
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    node = session.dof_support([1])["nodes"][0]
    assert node["status"] == "unverified" and not node["rotation_basis"]
    assert "Drilling stiffness" in node["diagnostics"][0]["reason"]


def test_fixed_coordinates_keep_native_reference_and_values_through_provider_undo_export(tmp_path):
    session = opened(); provider = RadProvider(session)
    spec = provider.operation_spec("coordinate_system.create")
    values = {field.name: field.value for field in spec.fields}
    values.update(name="Local X points global Y", native_id=43, origin=(1,2,3), y_axis=(-1,0,0), z_axis=(0,0,1))
    frame = provider.execute_operation(OperationRequest(spec.key, values, spec.document_id, spec.expected_revision))["object"]
    group = session.create_node_group("Beam", [2,5])["card_id"]
    curve = session.create_curve("Load", [(0,0), (1,1)])["card_id"]
    load = session.create_load("Local X force", group, curve, "X", 2, coordinate_system_id=frame.object_id)["card_id"]
    assert session.condition_support(load)["coordinate_system"]["axes"][0] == [0,1,0]
    raw = session.card_text(load).splitlines()[2]
    assert int(raw[20:30]) == 43 and raw[10:20].strip() == "X" and float(raw[80:100]) == 2
    target = provider.ref_for_card(next(item for item in session.list_cards() if item["id"] == load))
    fields = {field.name: field for field in provider.properties(target)}
    assert fields["coordinate_system_id"].value == frame
    revision = session.document.revision
    provider.submit(SetProperties(target, {"coordinate_system_id": None}, revision))
    assert session.condition_values(load)["coordinate_system_id"] is None
    session.undo(); assert session.condition_values(load)["coordinate_system_id"] == frame.object_id
    project = tmp_path / "mixed.caeprep"; session.save_project(project)
    restored = PrepSession(); restored.open_project(project)
    assert restored.coordinate_systems()[1]["axes"][0] == [0,1,0]
    assert restored.condition_values(load)["coordinate_system_id"] == frame.object_id
    exported = tmp_path / "out" / "mixed_0000.rad"; restored.export_rad(exported)
    checked = PrepSession(); checked.open_rad(exported)
    assert checked.coordinate_systems()[1]["axes"][0] == [0,1,0]


def test_related_frame_and_group_edits_validate_final_candidate_atomically():
    session=opened()
    group=session.create_node_group("Shell only",[1])["card_id"]
    curve=session.create_curve("Moment",[(0,0),(1,1)])["card_id"]
    frame=session.create_coordinate_system("Axes",[0,0,0],[0,1,0],[0,0,1])["card_id"]
    load=session.create_load("Moment",group,curve,"XX",1,coordinate_system_id=frame)["card_id"]
    before=(session.document.tokens(),session.document.revision)
    rotated={"y_axis":[-1,0,0],"z_axis":[0,1,0]}
    for action in (lambda:session.set_coordinate_system_values(frame,rotated),lambda:session.set_group_members(group,[7])):
        with pytest.raises(PrepError) as error:action()
        assert error.value.code=="dependent_condition_invalid"
        assert (session.document.tokens(),session.document.revision)==before
    events=[];session.subscribe(events.append)
    session.execute_many([{"operation":"set_coordinate_system_values","arguments":{"card_id":frame,"values":rotated}},
                          {"operation":"set_condition_values","arguments":{"card_id":load,"values":{"direction":"YY"}}}],expected_revision=before[1])
    assert session.condition_support(load)["status"]=="supported"
    assert session.document.revision==before[1]+1 and len(events)==1
    session.undo();assert session.document.tokens()==before[0]


@pytest.mark.parametrize("orientation",[0,2,5])
def test_optional_beam_orientation_uses_documented_global_reference(orientation,tmp_path):
    source=MODELS/"beam_shell_tet"
    (tmp_path/"model_0000.rad").write_bytes((source/"model_0000.rad").read_bytes())
    mesh=(source/"mesh.inc").read_text().replace(f"{78:10}{2:10}{5:10}{6:10}",f"{78:10}{2:10}{5:10}{orientation:10}")
    (tmp_path/"mesh.inc").write_text(mesh)
    session=PrepSession();session.open_rad(tmp_path/"model_0000.rad")
    assert len(session.dof_support([5])["nodes"][0]["rotation_basis"])==3
    destination=opened("truss_shell_hex")
    destination.import_source(destination.plan_import_source(tmp_path/"model_0000.rad")["plan_id"])


@pytest.mark.parametrize("first,second", [("beam_shell_tet", "truss_shell_hex"), ("truss_shell_hex", "beam_shell_tet")])
def test_two_mixed_assemblies_import_and_export_preserve_native_components(first, second, tmp_path):
    session = opened(first)
    source = MODELS / second / "model_0000.rad"
    plan = session.plan_import_source(source)
    session.import_source(plan["plan_id"])
    view = session.mesh_view()
    assert len(view["points"]) == 18 and len(view["cells"]) == 6
    assert {cell["formulation"] for cell in view["cells"]} == {"BEAM","TRUSS","SHELL","TETRA4","BRICK"}
    destination = tmp_path / "export" / "combined_0000.rad"; session.export_rad(destination)
    checked = PrepSession(); checked.open_rad(destination)
    assert checked.describe()["element_count"] == 6 and checked.describe()["node_count"] == 18
    assert not checked.diagnostics()


@pytest.mark.parametrize("first,second", [("beam_shell_tet", "truss_shell_hex"), ("truss_shell_hex", "beam_shell_tet")])
def test_mixed_sources_shared_definitions_conditions_and_cases_survive_reopen(first, second, tmp_path):
    session = opened(first)
    plan = session.plan_import_source(MODELS / second / "model_0000.rad")
    session.import_source(plan["plan_id"])
    cards = session.list_cards()
    base_parts = [item for item in cards if item["keyword"].startswith("/PART/") and item["resource_id"] == session._root_id]
    imported_root = plan["source"]["root_resource_id"]
    imported_parts = [item for item in cards if item["keyword"].startswith("/PART/") and item["resource_id"] == imported_root]
    base_material = session.part_assignments(base_parts[0]["id"])["material_id"]
    imported_material = session.part_assignments(imported_parts[0]["id"])["material_id"]
    assert len(base_parts) == len(imported_parts) == 3 and base_material != imported_material
    assert {session.part_assignments(part["id"])["material_id"] for part in base_parts} == {base_material}
    original_imported = session.card_text(imported_material)
    session.set_field(base_material, "young_modulus", 175000)
    assert session.card_text(imported_material) == original_imported
    alternate = session.create_material("Only this component", 8e-9, 190000, .29)["card_id"]
    session.assign_part(base_parts[1]["id"], material_id=alternate)
    assert session.part_assignments(base_parts[0]["id"])["material_id"] == base_material
    assert session.part_assignments(base_parts[1]["id"])["material_id"] == alternate
    assert session.part_assignments(imported_parts[1]["id"])["material_id"] == imported_material

    shell = next(part for part in base_parts if part["keyword"] == "/PART/9")
    shell_cell = next(cell for cell in session.mesh_view()["cells"] if cell["part_id"] == 9)
    group = session.create_node_group("Shared shell target", list(shell_cell["nodes"])[:2])["card_id"]
    surface = session.create_surface("Main surface", [shell["id"]])["card_id"]
    frame = session.create_coordinate_system("Condition axes", (1,2,3), (0,1,0), (0,0,1))["card_id"]
    curve = session.create_curve("Time history", [(0,0), (1,1)])["card_id"]
    load = session.create_load("Per-node load", group, curve, "Z", 3, coordinate_system_id=frame)["card_id"]
    velocity = session.create_initial_velocity("Initial translation", group, (1,0,0), coordinate_system_id=frame)["card_id"]
    fixed = session.create_boundary_condition("All flags retained", group, (True,)*3, (True,)*3)["card_id"]
    contact = session.create_contact("Connection", group, surface, .15)["card_id"]
    one = session.create_analysis_case("Static reference", [fixed,load,contact], 1e-6, 5e-7, "s")["case_id"]
    two = session.create_analysis_case("Velocity reference", [fixed,velocity,contact], 2e-6, 1e-6, "s")["case_id"]
    before = session.document.tokens(); revision = session.document.revision
    events = []; session.subscribe(events.append)
    session.execute_many([
        {"operation":"set_fields", "arguments":{"card_id":base_material,"values":{"young_modulus":180000}}},
        {"operation":"set_fields", "arguments":{"card_id":imported_material,"values":{"young_modulus":160000}}},
        {"operation":"set_analysis_case", "arguments":{"case_id":two,"values":{"condition_ids":[fixed,velocity]}}},
    ], expected_revision=revision)
    assert len(events) == 1 and session.document.revision == revision + 1
    assert contact in session.analysis_case(one)["condition_ids"] and contact not in session.analysis_case(two)["condition_ids"]
    session.undo(); assert session.document.tokens() == before
    session.redo()
    path = tmp_path / "mixed.caeprep"; session.save_project(path)
    reopened = PrepSession(); reopened.open_project(path)
    assert reopened.condition_values(load)["coordinate_system_id"] == frame
    assert reopened.condition_values(contact)["main_surface_id"] == surface
    assert reopened.condition_values(contact)["secondary_group_id"] == group
    assert reopened.analysis_cases() == session.analysis_cases()
    for case_id, active, inactive in ((one, (fixed,load,contact), (velocity,)), (two, (fixed,velocity), (load,contact))):
        destination = tmp_path / case_id / "case_0000.rad"
        reopened.export_analysis_case(destination,case_id)
        output = destination.read_text()
        for identifier in active:
            assert reopened._find_card(identifier).card(identifier).keyword + "\n" in output
        for identifier in inactive:
            assert reopened._find_card(identifier).card(identifier).keyword + "\n" not in output


@pytest.mark.skipif(not (os.environ.get("CAELAB_STARTER") and os.environ.get("CAELAB_ENGINE")),
                    reason="Explicit installed Starter and Engine are required.")
@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
def test_actual_mixed_native_inputs(name, tmp_path):
    """Native counts/relationships and short execution, not a coupling oracle."""
    session = opened(name)
    nodes = [node for node in session.mesh_view()["node_ids"] if node != 6 or name != "beam_shell_tet"]
    group = session.create_node_group("Mechanical nodes", nodes, native_id=59)["card_id"]
    session.create_boundary_condition("All fixed", group, [True]*3, [True]*3, native_id=83)
    output = session.export_solver_inputs(tmp_path / "mixed_0000.rad", 1e-7, 5e-8)
    starter = Path(os.environ["CAELAB_STARTER"]); engine = Path(os.environ["CAELAB_ENGINE"])
    installation = starter.resolve().parents[1]
    environment = dict(os.environ, PWD=str(tmp_path), OPENCOURANT_PATH=str(installation),
        RAD_CFG_PATH=str(installation / "hm_cfg_files"), RAD_H3D_PATH=str(installation / "extlib/h3d/lib/linux64"),
        OMP_NUM_THREADS="1", OMP_STACKSIZE="400m")
    environment["LD_LIBRARY_PATH"] = os.pathsep.join(str(installation / path) for path in ("extlib/hm_reader/linux64", "extlib/h3d/lib/linux64"))
    statuses = {}
    for label, executable, args in (("starter", starter, ["-i", "mixed_0000.rad", "-np", "1"]),
                                    ("engine", engine, ["-i", "mixed_0001.rad"])):
        run = subprocess.run([str(executable), *args], cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=30)
        text = run.stdout + run.stderr
        (tmp_path / (label + ".log")).write_text(text)
        normal = bool(re.search(r"^\s*NORMAL TERMINATION\s*$", text, re.M))
        statuses[label] = {"returncode": run.returncode, "normal": normal}
        (tmp_path / "native-summary.json").write_text(json.dumps(statuses, indent=2))
        assert run.returncode == 0 and normal, text
        if label == "starter":
            for kind in ("ERROR", "WARNING"):
                counts = re.findall(r"^\s*(\d+)\s+" + kind + r"\(S\)\s*$", text, re.M)
                assert counts and all(int(count) == 0 for count in counts), text
    listing = (tmp_path / "mixed_0000.out").read_text(errors="replace")
    expected = {"NUMNOD":9, "NPART":3, "NUMMAT":1, "NUMGEO":3, "NUMBCS":1, "NUMELS":1,
                "NUMELC":1, "NUMELP":int(name == "beam_shell_tet"), "NUMELT":int(name == "truss_shell_hex")}
    for key, count in expected.items():
        match = re.search(r"^\s*" + key + r":.*?\s(\d+)\s*$", listing, re.M)
        assert match and int(match[1]) == count, (key, match[1] if match else None)
    masses = {int(match[1]):float(match[2]) for match in re.finditer(r"PART\s*:\s*(\d+),[^\n]*\n[^\n]*Mass[^\n]*\n\s*(\S+)", listing)}
    assert masses == pytest.approx({9:100*7.8e-9, 10:10*7.8e-9,
                                   11:(1000/6 if name == "beam_shell_tet" else 1000)*7.8e-9}, rel=1e-8)
    statuses["expected_native_components"] = expected
    statuses["part_masses"] = masses
    statuses["formulations"] = sorted({cell["formulation"] for cell in session.mesh_view()["cells"]})
    statuses["native_files"] = sorted(path.name for path in tmp_path.iterdir())
    (tmp_path / "native-summary.json").write_text(json.dumps(statuses, indent=2))
