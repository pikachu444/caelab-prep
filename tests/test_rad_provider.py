from dataclasses import replace
from pathlib import Path

import pytest

from caelab_prep.application.contracts import DocumentSession, SetProperties
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


def test_rad_provider_scalar_contract_and_native_unit_context():
    session, provider = opened()
    assert isinstance(provider, DocumentSession)
    target = node(provider, "/MAT/LAW1/1").ref
    specs = {spec.name: spec for spec in provider.properties(target)}
    assert specs["young_modulus"].unit == "input deck"
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
    ("/FUNCT/1", {"points": ((0, 10), (.1, 20))}),
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
    if change == "unit": units = {"young_modulus": "Pa"}
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
    assert provider.properties(target)[0].unit_context == {"basis": "input_deck", "global": None, "unit_id": "77"}
    with pytest.raises(PrepError) as error:
        provider.submit(SetProperties(target, {"density": 1}, 0, None))
    assert error.value.code == "invalid_unit"
    assert session.describe()["revision"] == 0
