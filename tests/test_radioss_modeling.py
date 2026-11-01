"""Structural-state regression: identities, untouched bytes and failed command isolation."""
from copy import deepcopy
import json
from pathlib import Path
import zipfile

import pytest

from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.radioss import DeckResource

SOURCE = Path(__file__).resolve().parents[1] / "examples/rad/shell_panels_0000.rad"


def opened(path=SOURCE):
    session = PrepSession()
    session.open_rad(path)
    return session


def known_only(tmp_path):
    path = tmp_path / "known.rad"
    text = SOURCE.read_bytes().split(b"/PRESERVED/EDITOR/91", 1)[0] + b"/END\n"
    path.write_bytes(text)
    return opened(path)


def lookup(session, keyword):
    return next(card for card in session.list_cards() if card["keyword"] == keyword)


def test_structural_undo_keeps_original_and_created_card_identities():
    session = opened()
    before = {card["id"]: card["keyword"] for card in session.list_cards()}
    material = lookup(session, "/MAT/LAW1/2")
    unknown = lookup(session, "/PRESERVED/EDITOR/91")
    untouched = session.card_text(unknown["id"])
    created = session.create_material("새 강재", 7.8e-9, 195000, .29, native_id=20)
    assert lookup(session, "/MAT/LAW1/20")["title"] == "새 강재"
    assert all(lookup(session, keyword)["id"] == identifier for identifier, keyword in before.items())
    session.set_field(material["id"], "young_modulus", 200000)
    session.undo()
    session.undo()
    assert session.document.resources[material["resource_id"]].render() == SOURCE.read_bytes()
    assert not session.describe()["dirty"]
    session.redo()
    assert lookup(session, "/MAT/LAW1/20")["id"] == created["card_id"]
    session.redo()
    assert session.card_text(unknown["id"]) == untouched
    assert next(field["value"] for field in session.card_fields(material["id"]) if field["name"] == "young_modulus") == 200000


def test_copy_uses_current_patched_values_and_changes_only_header_and_requested_title(tmp_path):
    session = known_only(tmp_path)
    original = lookup(session, "/PROP/SHELL/2")
    session.set_field(original["id"], "thickness", 3.75)
    text = session.card_text(original["id"])
    copied = session.copy_card(original["id"], native_id=40, name="Copied section")
    copied_text = session.card_text(copied["card_id"])
    assert copied_text.splitlines()[2:] == text.splitlines()[2:]
    assert copied_text.splitlines()[:2] == ["/PROP/SHELL/40", "Copied section"]
    session.delete_card(copied["card_id"])
    with pytest.raises(PrepError): session.card_fields(copied["card_id"])
    session.undo()
    assert session.card_text(copied["card_id"]) == copied_text
    session.redo()
    assert session.card_text(original["id"]) == text


def test_v1_patch_document_is_read_without_migration_of_original_bytes(tmp_path):
    resource = DeckResource(SOURCE.read_bytes())
    material = next(card for card in resource.cards if card.keyword == "/MAT/LAW1/1")
    from uuid import uuid4
    manifest = {"format": "caelab-prep-project", "version": 1, "document_id": str(uuid4()),
        "name": "Legacy", "revision": 7, "root_id": resource.id, "source_paths": [],
        "resources": [{"id": resource.id, "kind": resource.kind, "name": "legacy.rad",
          "logical_path": "legacy.rad", "raw_member": f"raw/{resource.id}.rad",
          "patches": {material.id: {"young_modulus": 185000}}}]}
    path = tmp_path / "legacy.caeprep"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr(f"raw/{resource.id}.rad", resource.raw)
    session = PrepSession()
    session.open_project(path)
    assert session.describe()["revision"] == 7 and not session.describe()["dirty"]
    assert next(item["value"] for item in session.card_fields(material.id) if item["name"] == "young_modulus") == 185000
    created = session.create_shell_property("New shell", 2.2)
    session.save_project(tmp_path / "new.caeprep")
    check = PrepSession()
    check.open_project(tmp_path / "new.caeprep")
    assert lookup(check, "/PROP/SHELL/4")["id"] == created["card_id"]
    assert check.document.resources[resource.id].raw == resource.raw


def test_invalid_structure_restore_is_atomic_and_preserves_raw():
    session = opened()
    resource = next(iter(session.document.resources.values()))
    session.create_material("M", 1, 100, .3)
    before = resource.snapshot()
    rendered = resource.render()
    bad = deepcopy(before)
    bad["created"][0]["text"] += "/NODE\n"
    with pytest.raises(PrepError): resource.restore(bad)
    assert resource.snapshot() == before and resource.render() == rendered
    bad = deepcopy(before)
    bad["deleted"] = [resource.cards[0].id]
    with pytest.raises(PrepError): resource.restore(bad)
    assert resource.snapshot() == before and resource.raw == SOURCE.read_bytes()


def test_part_assignments_return_uuid_targets_and_dependents(tmp_path):
    session = known_only(tmp_path)
    part = lookup(session, "/PART/1")
    old_material = lookup(session, "/MAT/LAW1/1")
    section = lookup(session, "/PROP/SHELL/1")
    assignments = session.part_assignments(part["id"])
    assert assignments["material_id"] == old_material["id"]
    assert assignments["property_id"] == section["id"]
    assert assignments["native_material_id"] == assignments["native_property_id"] == 1
    assert session.card_dependents(old_material["id"])[0]["id"] == part["id"]
    new_material = session.create_material("New", 1, 100, .3)
    session.assign_part(part["id"], material_id=new_material["card_id"])
    assert session.part_assignments(part["id"])["material_id"] == new_material["card_id"]
    assert not session.card_dependents(old_material["id"])
    session.delete_card(old_material["id"])
    assert session.part_assignments(part["id"])["material_id"] == new_material["card_id"]
    session.undo()
    session.undo()
    assert session.part_assignments(part["id"])["material_id"] == old_material["id"]


def test_delete_selected_new_card_clears_selection_and_stale_ref(tmp_path):
    from caelab_prep.application.contracts import ObjectRef
    session = known_only(tmp_path)
    result = session.create_material("Selected", 1, 100, .3)
    card = next(c for c in session.list_cards() if c["id"] == result["card_id"])
    ref = ObjectRef(session.document.id, card["resource_id"], card["id"], "rad-card", card["keyword"])
    session.activate_object(ref)
    session.delete_card(card["id"])
    assert session.active_object() is None
    with pytest.raises(PrepError): session.activate_object(ref)
    session.undo()
    session.activate_object(ref)
    assert session.active_object() == ref


def test_native_ids_cannot_bypass_uuid_reference_command():
    session = opened()
    part = lookup(session, "/PART/1")
    before = session.describe()
    with pytest.raises(PrepError): session.set_field(part["id"], "material_id", 1234)
    assert session.describe() == before


def test_multiple_parts_select_union_once_and_invalid_target_keeps_selection():
    from dataclasses import replace
    from caelab_prep.application.contracts import ObjectRef
    session = opened()
    def ref(keyword):
        card = lookup(session, keyword)
        return ObjectRef(session.document.id, card["resource_id"], card["id"], "rad-card", card["keyword"])
    first, second = ref("/PART/1"), ref("/PART/2")
    events = []
    session.subscribe(events.append)
    result = session.select_objects((first, second, first), active=second)
    assert session.selected_objects() == (first, second)
    assert session.active_object() == second
    expected = {cell["id"] for cell in session.mesh_view()["cells"] if cell["part_id"] in (1, 2)}
    assert set(result["ids"]) == expected
    assert len(events) == 1 and events[0]["kind"] == "selection"
    before = session.selection()
    for bad in ((first, replace(second, document_id="stale")), (first, ref("/MAT/LAW1/1"))):
        with pytest.raises(PrepError): session.select_objects(bad, active=first)
        assert session.selection() == before and len(events) == 1
    with pytest.raises(PrepError): session.select_objects((first,), active=second)
    assert session.selection() == before and len(events) == 1
    session.select_objects((), active=None)
    assert not session.selection()["refs"] and not session.selected_objects()
    assert session.active_object() is None and len(events) == 2


def test_replacement_overlay_is_compatible_with_v2_and_invalidates_cached_state_token(tmp_path):
    session = known_only(tmp_path)
    curve = session.create_curve("Measured curve", [(0, 0), (1, 1)])
    resource = session.document.resources[curve["resource_id"]]
    v2 = resource.snapshot()
    v2.pop("replaced")
    v2["state_version"] = 2
    restored = DeckResource(resource.raw, resource_id=resource.id)
    restored.restore(v2)
    assert restored.render() == resource.render()
    saved = resource.state_token()
    assert resource.state_token() == saved
    session.set_curve_points(curve["card_id"], [(0, 0), (.5, 2), (1, 1)])
    assert resource.state_token() != saved
    session.undo()
    assert resource.state_token() == saved
    session.redo()
    assert resource.state_token() != saved


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_original_curve_replacement_and_scalar_edits_preserve_card_identity(tmp_path, newline):
    source = tmp_path / "original.rad"
    source.write_bytes(("/BEGIN\nOriginal\n/FUNCT/4\nMeasured\n# retained comment\n" +
                      f"{0:20g}{0:20g}\n{1:20g}{1:20g}\n/END\n").replace("\n", newline).encode("ascii"))
    session = opened(source)
    card = lookup(session, "/FUNCT/4")
    resource = session.document.resources[card["resource_id"]]
    old = resource.render()
    session.set_curve_points(card["id"], [(0, 2), (.5, 3), (1, 1)])
    session.set_field(card["id"], "point_1_y", 6)
    assert lookup(session, "/FUNCT/4")["id"] == card["id"]
    assert next(f["value"] for f in session.card_fields(card["id"]) if f["name"] == "point_1_y") == 6
    session.undo()
    session.undo()
    assert resource.render() == old
    session.redo()
    assert "# retained comment" + newline in session.card_text(card["id"])
    assert len(resource.snapshot()["replaced"]) == 1


def test_scalar_curve_edit_cannot_bypass_order_validation(tmp_path):
    session = known_only(tmp_path)
    curve = session.create_curve("C", [(0, 0), (1, 1)])["card_id"]
    before = session.describe()["revision"], session.card_text(curve)
    with pytest.raises(PrepError, match="strictly increasing"):
        session.set_field(curve, "point_1_x", -1)
    assert (session.describe()["revision"], session.card_text(curve)) == before


def test_submodel_offsets_block_identity_changes_without_mutation(tmp_path):
    source = tmp_path / "scoped.rad"
    source.write_text("/BEGIN\nScoped\n/SUBMODEL/1\nScoped resource\n/END\n")
    session = opened(source)
    with pytest.raises(PrepError) as caught:
        session.create_curve("C", [(0, 0), (1, 1)])
    assert caught.value.code == "unsupported_submodel"
    assert session.describe()["revision"] == 0 and not session.describe()["dirty"]


def test_group_rejects_duplicate_native_node_inside_one_source(tmp_path):
    source = tmp_path / "nodes.rad"
    source.write_text("/BEGIN\nNodes\n/NODE\n" + (f"{42:10d}{0:20g}{0:20g}{0:20g}\n" * 2) + "/END\n")
    session = opened(source)
    with pytest.raises(PrepError) as caught:
        session.create_node_group("Ambiguous node", [42])
    assert caught.value.code == "ambiguous_reference"
    assert session.describe()["revision"] == 0


def test_condition_target_roles_follow_reference_edit_and_undo(tmp_path):
    from caelab_prep.application.contracts import ObjectRef
    session = known_only(tmp_path)
    a = session.create_node_group("Secondary", [10, 11, 12])["card_id"]
    surface_a = session.create_surface("Main A", [lookup(session, "/PART/1")["id"]])["card_id"]
    surface_b = session.create_surface("Main B", [lookup(session, "/PART/2")["id"]])["card_id"]
    contact = session.create_contact("Contact", a, surface_a, .1)
    card = next(item for item in session.list_cards() if item["id"] == contact["card_id"])
    target = ObjectRef(session.describe()["document_id"], card["resource_id"], card["id"], "rad-card", card["keyword"])
    session.activate_object(target)
    assert session.selection()["kind"] == "node" and session.selection()["ids"] == [10, 11, 12]
    session.select_condition_target(card["id"], "main_elements")
    assert session.selection()["kind"] == "element" and session.selection()["ids"] == [1, 2, 3, 4]
    events = []
    session.subscribe(events.append)
    session.set_condition_values(card["id"], {"main_surface_id": surface_b})
    assert len(events) == 1 and events[0]["kind"] == "structure"
    assert session.selection()["ids"] == [5, 6, 7, 8]
    assert session.selection()["active_target_role"] == "main_elements"
    session.undo()
    assert session.selection()["ids"] == [1, 2, 3, 4]
    assert session.active_object() == target


def test_unchanged_condition_values_do_not_reformat_original_native_bytes(tmp_path):
    session = known_only(tmp_path)
    card = lookup(session, "/INIVEL/TRA/1")
    original = session.card_text(card["id"])
    current = session.condition_values(card["id"])
    result = session.set_condition_values(card["id"], {"velocity": tuple(current["velocity"]), "group_id": current["group_id"]})
    assert result["change"] is None
    assert session.card_text(card["id"]) == original and session.describe()["revision"] == 0


def test_element_group_membership_is_typed_atomic_and_selected_after_edit(tmp_path):
    from caelab_prep.application.contracts import ObjectRef
    session = known_only(tmp_path)
    owner = session.describe()["document_id"]
    cells = session.mesh_view()["cells"]
    refs = [dict(resource_id=cell["resource_id"], entity_kind="element", local_id=cell["id"]) for cell in cells]
    group = session.create_element_group("Selected quads", refs[:3], native_id=97)
    card = next(item for item in session.list_cards() if item["id"] == group["card_id"])
    assert card["keyword"] == "/GRSHEL/SHEL/97"
    target = ObjectRef(owner, card["resource_id"], card["id"], "rad-card", card["keyword"])
    session.activate_object(target)
    assert session.selection()["ids"] == [1, 2, 3]
    before = session.card_text(card["id"])
    session.set_group_members(card["id"], refs[3:])
    assert session.group_members(card["id"])["members"] == refs[3:]
    assert session.selection()["ids"] == list(range(4, 13))
    session.undo()
    assert session.card_text(card["id"]) == before and session.selection()["ids"] == [1, 2, 3]
    duplicate = session.copy_card(card["id"], native_id=99)
    assert session.group_members(duplicate["card_id"])["member_ids"] == [1, 2, 3]
    session.delete_card(duplicate["card_id"])
    session.undo()
    assert session.group_members(duplicate["card_id"])["member_ids"] == [1, 2, 3]
    old = session.describe()["revision"], session.card_text(card["id"])
    for invalid in ([1, 2], [refs[0], refs[0]], [{**refs[0], "entity_kind": "node"}], [{**refs[0], "local_id": 999999}]):
        with pytest.raises(PrepError): session.set_group_members(card["id"], invalid)
        assert (session.describe()["revision"], session.card_text(card["id"])) == old


def test_node_group_rows_can_be_edited_without_changing_group_identity(tmp_path):
    session = known_only(tmp_path)
    group = lookup(session, "/GRNOD/NODE/1")
    before = session.card_text(group["id"])
    session.set_group_members(group["id"], list(range(1, 16)))
    assert session.group_members(group["id"])["member_ids"] == list(range(1, 16))
    assert len(session.card_text(group["id"]).splitlines()) == 4
    session.undo()
    assert session.card_text(group["id"]) == before
