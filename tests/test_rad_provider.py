from dataclasses import replace
from pathlib import Path

import pytest

from caelab_prep.application.contracts import DocumentSession, OperationRequest, SetProperties
from caelab_prep.application.rad_provider import RadProvider
from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError


INPUTS = Path(__file__).resolve().parents[1] / "examples/rad"


def opened(name="shell_panels_0000.rad"):
    session = PrepSession()
    session.open_rad(INPUTS / name)
    return session, RadProvider(session)


def node(provider, keyword):
    return next(item for item in provider.tree_nodes() if item.ref.native_scope == keyword)


def test_element_group_picker_qualifies_same_file_shell_and_quad_ids(tmp_path):
    source = tmp_path / "shared_0000.rad"
    raw = (INPUTS / "shell_panels_0000.rad").read_bytes().split(b"/PRESERVED/EDITOR/91", 1)[0]
    raw = raw.replace(b"\n/SHELL/1", b"\n/QUAD/1", 1).replace(b"\n         5        10", b"\n         1        10", 1)
    source.write_bytes(raw + b"/END\n")
    session = PrepSession()
    session.open_rad(source)
    provider = RadProvider(session)
    spec = provider.operation_spec("element_group.create")
    field = next(field for field in spec.fields if field.name == "element_refs")
    choices = {ref["formulation"]: (ref, label) for ref, label in zip(field.choices, field.choice_labels)
               if ref["local_id"] == 1}
    assert set(choices) == {"SHELL", "QUAD"}
    for family, keyword in (("SHELL", "/GRSHEL/SHEL/987"), ("QUAD", "/GRQUAD/QUAD/987")):
        ref, label = choices[family]
        assert f"({family})" in label
        result = provider.execute_operation(OperationRequest(
            "element_group.create", {"name": family, "native_id": 987, "element_refs": [ref]},
            session.document.id, session.document.revision))
        group = node(provider, keyword).ref
        assert group.object_id == result["card_id"]
        assert session.group_members(group.object_id)["members"] == [ref]
        other = choices["QUAD" if family == "SHELL" else "SHELL"][0]
        with pytest.raises(PrepError) as error:
            provider.submit(SetProperties(group, {"element_refs": [other]}, session.document.revision))
        assert error.value.code == "incompatible_group"
        provider.submit(SetProperties(group, {"element_refs": [ref]}, session.document.revision))


def test_element_group_picker_rejects_shared_id_within_one_native_family(tmp_path):
    source = tmp_path / "shared_solids_0000.rad"
    raw = (INPUTS / "shell_panels_0000.rad").read_bytes().replace(b"\r\n", b"\n").split(b"\n/SHELL/1\n", 1)[0]
    brick = "".join(f"{value:10d}" for value in (201, 1, 2, 5, 4, 10, 11, 14, 13))
    tetra = "".join(f"{value:10d}" for value in (201, 1, 2, 5, 10))
    source.write_bytes(raw + f"\n/BRICK/1\n{brick}\n/TETRA4/2\n{tetra}\n/END\n".encode())
    session = PrepSession()
    session.open_rad(source)
    provider = RadProvider(session)
    field = next(field for field in provider.operation_spec("element_group.create").fields
                 if field.name == "element_refs")
    choices = [ref for ref in field.choices if ref["local_id"] == 201]
    assert {ref["formulation"] for ref in choices} == {"BRICK", "TETRA4"}
    revision = session.document.revision
    for ref in choices:
        with pytest.raises(PrepError) as error:
            provider.execute_operation(OperationRequest(
                "element_group.create", {"name": "Shared solid ID", "native_id": 987, "element_refs": [ref]},
                session.document.id, revision))
        assert error.value.code == "ambiguous_reference"
    assert session.document.revision == revision
    assert all(item.ref.native_scope != "/GRBRIC/BRIC/987" for item in provider.tree_nodes())


def test_quad_property_only_provider_edits_preserve_existing_law3(tmp_path):
    source = tmp_path / "ale_0000.rad"
    raw = (INPUTS / "shell_panels_0000.rad").read_bytes()
    raw = raw.split(b"/PRESERVED/EDITOR/91", 1)[0]
    source.write_bytes(raw.replace(b"\n/SHELL/1", b"\n/QUAD/1", 1).replace(b"/MAT/LAW1/1", b"/MAT/LAW3/1", 1) + b"/END\n")
    session = PrepSession()
    session.open_rad(source)
    provider = RadProvider(session)
    part = node(provider, "/PART/1").ref
    material = node(provider, "/MAT/LAW3/1").ref
    for action in ("inspector", "operation", "full-operation"):
        card = session.create_solid_property(f"Solid {action}")["card_id"]
        prop = next(item.ref for item in provider.tree_nodes() if item.ref.object_id == card)
        revision = session.document.revision
        if action == "inspector":
            provider.submit(SetProperties(part, {"property": prop}, revision))
        else:
            values = {"property": prop}
            if action == "full-operation":
                values["material"] = material
            provider.execute_operation(OperationRequest("part.assign", values, part.document_id, revision, part))
        assignments = session.part_assignments(part.object_id)
        assert (assignments["material_id"], assignments["property_id"]) == (material.object_id, card)


def test_rad_provider_scalar_contract_and_native_unit_context():
    session, provider = opened()
    assert isinstance(provider, DocumentSession)
    target = node(provider, "/MAT/LAW1/1").ref
    specs = {spec.name: spec for spec in provider.properties(target)}
    assert specs["young_modulus"].unit == "MPa"
    assert provider.unit_context(target)["global"] == {"mass": "Mg", "length": "mm", "time": "s"}
    provider.submit(SetProperties(target, {"young_modulus": 199000}, 0))
    assert provider.properties(target)[1].value == 199000
    assert session.describe()["revision"] == 1
    provider.undo()
    assert provider.properties(target)[1].value == 209000
    assert not session.describe()["can_undo"]
    provider.redo()
    assert provider.properties(target)[1].value == 199000


def test_vector_and_existing_curve_table_each_have_one_undo():
    session, provider = opened()
    velocity = node(provider, "/INIVEL/TRA/1").ref
    curve = node(provider, "/FUNCT/1").ref
    provider.submit(SetProperties(velocity, {"velocity": (10, 20, -30)}, 0))
    assert [field["value"] for field in session.card_fields(velocity.object_id)] == [10, 20, -30]
    provider.undo()
    assert provider.properties(velocity)[0].value == (0, 0, -100)
    assert not session.describe()["can_undo"]
    before = provider.properties(curve)[0].value
    points = ((0, 10), (.1, 40), (.3, 90))
    provider.submit(SetProperties(curve, {"points": points}, session.describe()["revision"]))
    assert provider.properties(curve)[0].value == points
    provider.undo()
    assert provider.properties(curve)[0].value == before
    assert not session.describe()["can_undo"]


@pytest.mark.parametrize("keyword,values", [
    ("/INIVEL/TRA/1", {"velocity": (10, 20, float("nan"))}),
    ("/INIVEL/TRA/1", {"velocity": (10, 20)}),
    ("/FUNCT/1", {"points": ((0, 10), (.1, 20), (.3, float("inf")))}),
    ("/FUNCT/1", {"points": ((0, 10), (0, 20))}),
])
def test_invalid_vector_or_table_never_commits_valid_prefix(keyword, values):
    session, provider = opened()
    target = node(provider, keyword).ref
    before = session.card_text(target.object_id)
    with pytest.raises(PrepError):
        provider.submit(SetProperties(target, values, 0))
    assert session.card_text(target.object_id) == before
    assert session.describe()["revision"] == 0
    assert not session.describe()["can_undo"]


@pytest.mark.parametrize("change", ["unit", "document", "resource", "kind", "scope", "mesh", "revision", "value", "unknown"])
def test_rejected_command_never_changes_part_of_a_card(change):
    session, provider = opened()
    target = node(provider, "/MAT/LAW1/1").ref
    original = session.card_text(target.object_id)
    units = {}
    values = {"density": 8e-9, "young_modulus": 199000}
    revision = 0
    if change == "unit": units = {"young_modulus": "mm"}
    elif change == "document": target = replace(target, document_id="old-document")
    elif change == "resource": target = replace(target, resource_id="other-resource")
    elif change == "kind": target = replace(target, kind="curve")
    elif change == "scope": target = replace(target, native_scope="/MAT/LAW1/2")
    elif change == "mesh": target = replace(target, mesh_revision=0)
    elif change == "revision": revision = True
    elif change == "value": values["young_modulus"] = -1
    elif change == "unknown": values["invented"] = 1
    with pytest.raises(PrepError):
        provider.submit(SetProperties(target, values, revision, units))
    assert session.describe()["revision"] == 0
    assert not session.describe()["dirty"]
    actual = node(provider, "/MAT/LAW1/1").ref
    assert session.card_text(actual.object_id) == original


def test_include_solid_roundtrip_and_raw_unknown_preservation(tmp_path):
    session, provider = opened("solid_blocks_0000.rad")
    assert session.describe()["node_count"] == 16
    assert session.describe()["element_count"] == 2
    refs = {item.ref.resource_id for item in provider.tree_nodes()}
    assert len(refs) == 2
    unknown = node(provider, "/PRESERVED/EDITOR/91").ref
    raw = session.card_text(unknown.object_id)
    assert provider.properties(unknown) == ()
    material = node(provider, "/MAT/LAW1/22").ref
    provider.submit(SetProperties(material, {"young_modulus": 200000}, 0))
    project = tmp_path / "solid.caeprep"
    provider.save_project(project)
    reopened = RadProvider(PrepSession())
    reopened.open_project(project)
    assert reopened.properties(material)[1].value == 200000
    assert reopened.session.card_text(unknown.object_id) == raw
    output = tmp_path / "export/model_0000.rad"
    reopened.session.export_rad(output)
    assert (output.parent / "solid_geometry.inc").read_bytes() == (INPUTS / "solid_geometry.inc").read_bytes()
    independent = PrepSession()
    independent.open_rad(output)
    assert independent.describe()["node_count"] == 16
    assert independent.describe()["element_count"] == 2


def test_partial_funct_rows_do_not_get_renumbered_or_crash(tmp_path):
    source = tmp_path / "partial.rad"
    source.write_text("/FUNCT/1\nPartial row\n" + f"{0:20g}{'unreadable':>20}\n{1:20g}{2:20g}\n/END\n", encoding="ascii")
    session = PrepSession()
    session.open_rad(source)
    provider = RadProvider(session)
    specs = provider.properties(node(provider, "/FUNCT/1").ref)
    assert [spec.name for spec in specs] == ["point_0_x", "point_1_x", "point_1_y"]


def test_material_override_and_unknown_basis_remain_descriptive(tmp_path):
    source = tmp_path / "override.rad"
    source.write_text("/MAT/LAW1/12/77\nSteel\n" + f"{7.8e-9:20g}\n{210000:20g}{.3:20g}\n/END\n", encoding="ascii")
    session = PrepSession()
    session.open_rad(source)
    provider = RadProvider(session)
    target = node(provider, "/MAT/LAW1/12/77").ref
    context = provider.properties(target)[0].unit_context
    assert {key: context[key] for key in ("basis", "global", "unit_id")} == {"basis": "input_deck", "global": None, "unit_id": "77"}
    assert context["display_conversion"] == "unavailable"
    assert "override" in context["reason"]
    with pytest.raises(PrepError) as error:
        provider.submit(SetProperties(target, {"density": 1}, 0, None))
    assert error.value.code == "invalid_unit"
    assert session.describe()["revision"] == 0


def mesh_pick(session, kind="element", identifier=None):
    projection = session.mesh_view()
    cell = projection["cells"][0]
    resource = cell["resource_id"]
    return {key: projection[key] for key in ("document_id", "document_epoch", "revision", "projection_revision")} | {
        "kind": kind, "id": cell["id"] if identifier is None else identifier,
        "resource_id": resource, "resource_revision": projection["resource_revisions"][resource],
    }


@pytest.mark.parametrize("field,bad", [
    ("document_id", "other"), ("document_epoch", "other"), ("revision", -1),
    ("projection_revision", -1), ("resource_id", "other"), ("resource_revision", -1),
    ("id", True), ("kind", "card"),
])
def test_qualified_pick_rejects_stale_or_invalid_identity_without_changing_selection(field, bad):
    session, provider = opened()
    candidate = mesh_pick(session)
    approved = session.select_pick(candidate)
    with pytest.raises(PrepError):
        session.select_pick(candidate | {field: bad})
    assert session.selection() == approved


def test_pick_from_previous_presentation_is_rejected_after_same_ids_are_reopened(tmp_path):
    session, provider = opened()
    path = tmp_path / "same-document.caeprep"
    session.save_project(path)
    candidate = mesh_pick(session)
    session.open_project(path)
    current = mesh_pick(session)
    assert current["document_id"] == candidate["document_id"]
    assert current["resource_id"] == candidate["resource_id"]
    assert current["id"] == candidate["id"]
    before = session.select_pick(current)
    with pytest.raises(PrepError):
        session.select_pick(candidate)
    assert session.selection() == before
    with pytest.raises(PrepError):
        session.select_pick(candidate | {"kind": None})
    assert session.selection() == before
    assert before["ids"] == [current["id"]]


@pytest.mark.parametrize("filename,scope,duplicate_scope", [
    ("shell_panels_0000.rad", "/PART/2", None), ("solid_blocks_0000.rad", "/PART/22", None),
    ("shell_panels_0000.rad", "/PART/1", "/PART/01"),
])
def test_part_activation_shares_typed_target_and_existing_native_mesh_relation(tmp_path, filename, scope, duplicate_scope):
    session, provider = opened(filename)
    if duplicate_scope:
        source = tmp_path / "duplicate-parts.rad"
        source.write_bytes((INPUTS / filename).read_bytes().replace(
            b"/END", (duplicate_scope + "\nDuplicate Part\n         1         1         0\n/END").encode("ascii")))
        session.open_rad(source)
    target = node(provider, scope).ref
    if duplicate_scope:
        before = session.selection()
        with pytest.raises(PrepError) as error:
            provider.select(target)
        assert error.value.code == "ambiguous_selection"
        assert session.selection() == before and provider.active_object() is None
        return
    provider.select(target)
    assert provider.active_object() == session.active_object() == target
    part_id = int(scope.rsplit("/", 1)[1])
    related = [cell for cell in session.mesh_view()["cells"] if cell["part_id"] == part_id]
    assert related
    assert set(session.selection()["ids"]) == {cell["id"] for cell in related}
    assert {ref["resource_id"] for ref in session.selection()["refs"]} == {cell["resource_id"] for cell in related}
    specs = {spec.name: spec for spec in provider.properties(target)}
    assert not specs["part_id"].editable and not specs["element_count"].editable
    assert specs["material"].kind == specs["property"].kind == "reference"
    assert specs["material"].editable and specs["property"].editable
    assert specs["material"].value.document_id == target.document_id
    before = session.selection()
    with pytest.raises(PrepError):
        provider.select(replace(target, resource_id="missing-resource"))
    assert session.selection() == before and provider.active_object() == target


def test_qualified_pick_keeps_canonical_invalid_and_ambiguous_id_rejection(tmp_path):
    source = tmp_path / "duplicate-nodes.rad"
    included = tmp_path / "duplicate.inc"
    # A second native resource reuses an existing node ID; its provenance must not
    # silently turn the session's ambiguous canonical ID into an approved pick.
    included.write_text("/NODE\n" + f"{1:10d}{0:20g}{0:20g}{0:20g}\n/END\n", encoding="ascii")
    source.write_bytes((INPUTS / "shell_panels_0000.rad").read_bytes().replace(
        b"/END", b"#include duplicate.inc\n/END"))
    session = PrepSession()
    session.open_rad(source)
    before = session.selection()
    for candidate in (mesh_pick(session, "node", True), mesh_pick(session, "node", -999)):
        with pytest.raises(PrepError) as error:
            session.select_pick(candidate)
        assert error.value.code == "invalid_selection"
        assert session.selection() == before
    candidate = mesh_pick(session, "node", 1)
    with pytest.raises(PrepError) as error:
        session.select_pick(candidate)
    assert error.value.code == "ambiguous_selection"
    assert session.selection() == before
