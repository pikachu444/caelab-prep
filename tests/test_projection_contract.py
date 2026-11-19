import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.rad_provider import RadProvider
from caelab_prep.cae_core import PrepError
from caelab_prep.radioss import deck
from test_condition_workflow import _base_model, _card, _i, _r

FIXTURE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"


def test_geometry_is_nested_readonly_shared_and_mutable_copy_is_explicit():
    session = PrepSession(); session.open_rad(FIXTURE)
    first, again = session.mesh_view(), session.mesh_view()
    assert first is not again
    for key in ("points", "node_ids", "cells", "node_resources", "diagnostics"):
        assert first[key] is again[key]
    for change in (lambda: first["points"][0].__setitem__(0, 77),
                   lambda: first["cells"][0].__setitem__("id", 77),
                   lambda: first["cells"][0]["part_ref"].__setitem__("resource_id", "other"),
                   lambda: first["node_resources"].__setitem__(1, ("other",))):
        with pytest.raises((TypeError, AttributeError)): change()
    detached = session.mesh_view(mutable=True)
    assert json.loads(json.dumps(detached))["node_ids"] == list(first["node_ids"])
    detached["points"][0][0] = 77
    detached["cells"][0]["nodes"].clear()
    assert session.mesh_view()["points"][0][0] == first["points"][0][0]
    assert session.mesh_view()["cells"][0]["nodes"]


def test_scalar_stamps_change_without_geometry_allocation_and_structure_invalidates():
    session = PrepSession(); session.open_rad(FIXTURE)
    first = session.mesh_view()
    material = next(card for card in session.list_cards() if card["keyword"] == "/MAT/PLAS_TAB/1")
    session.set_field(material["id"], "young_modulus", 190000)
    scalar = session.mesh_view()
    assert scalar["cells"] is first["cells"] and scalar["points"] is first["points"]
    assert scalar["revision"] == first["revision"] + 1
    assert scalar["resource_revisions"] != first["resource_revisions"]
    assert scalar["projection_revision"] == first["projection_revision"]
    session.create_node_group("Selection", [first["node_ids"][0]])
    structure = session.mesh_view()
    assert structure["cells"] is not scalar["cells"]
    assert structure["projection_revision"] > scalar["projection_revision"]
    session.undo()
    assert session.mesh_view()["cells"] is not structure["cells"]
    epoch = session.mesh_view()["document_epoch"]
    session.open_rad(FIXTURE)
    assert session.mesh_view()["document_epoch"] != epoch


@pytest.mark.parametrize("write", ("restore", "field"))
def test_selection_prunes_node_renumbered_by_nonstructural_write(tmp_path, write):
    source = tmp_path / "nodes_0000.rad"
    source.write_text(f"/BEGIN\nRaw IDs\n/NODE\n{_i(101)}{_r(0, 0, 0)}\n/END\n")
    session = PrepSession()
    session.open_rad(source)
    picked = session.select_entity("node", 101)
    assert picked["ids"] == [101]
    owner = session._model_resource(None)
    state = owner.replaced_state(_card(session, "/NODE")["id"], f"/NODE\n{_i(9101)}{_r(0, 0, 0)}\n")
    if write == "restore":
        owner.restore(state)
    else:
        session.dispatcher.execute(owner.id, state, "Renumber selected node")
        assert session.document.selection.ids == ()
    resolved = session.selection()
    assert resolved["ids"] == [] and resolved["refs"] == []
    assert resolved["projection_revision"] == picked["projection_revision"] + 1
    assert session.select_entity("node", 9101)["ids"] == [9101]


def test_first_pick_rejects_geometry_moved_in_another_include(tmp_path):
    source = _base_model(tmp_path / "input")
    mesh = source.with_name("mesh.inc")
    nodes, cells = mesh.read_bytes().split(b"/SHELL/902", 1)
    mesh.write_bytes(b"/SHELL/902" + cells)
    source.with_name("nodes.inc").write_bytes(nodes)
    source.write_bytes(source.read_bytes().replace(b"#include mesh.inc", b"#include nodes.inc\n#include mesh.inc"))
    session = PrepSession()
    session.open_rad(source)
    original = session.mesh_view()
    element = original["cells"][0]
    owner = session.document.resources[original["node_resources"][101][0]]
    assert owner.id != element["resource_id"]

    def pick(view):
        return {**{key: view[key] for key in ("document_id", "document_epoch", "revision", "projection_revision")},
                "kind": "element", "id": element["id"], "resource_id": element["resource_id"],
                "resource_revision": view["resource_revisions"][element["resource_id"]]}

    candidate = pick(original)
    positions = {str(node_id): (x + 100, y, z) for node_id, (x, y, z) in zip(original["node_ids"], original["points"])}
    owner.restore(owner.node_positions_state(positions))
    with pytest.raises(PrepError) as error:
        session.select_pick(candidate)
    assert error.value.code == "stale_pick"
    updated = session.mesh_view()
    assert updated["projection_revision"] == original["projection_revision"] + 1
    assert updated["points"][0][0] == original["points"][0][0] + 100
    assert session.select_pick(pick(updated))["ids"] == [element["id"]]


def test_selected_node_is_cleared_when_a_second_owner_appears(tmp_path):
    source = tmp_path / "nodes_0000.rad"
    source.write_text("/BEGIN\nShared native ID\n#include first.inc\n#include second.inc\n/END\n")
    (tmp_path / "first.inc").write_text(f"/NODE\n{_i(2)}{_r(0, 0, 0)}\n")
    (tmp_path / "second.inc").write_text(f"/NODE\n{_i(1)}{_r(1, 0, 0)}\n")
    session = PrepSession()
    session.open_rad(source)
    assert session.select_entity("node", 1)["ids"] == [1]
    first = next(resource for resource in session._deck_resources() if resource.name == "first.inc")
    card, = first.cards
    first.restore(first.replaced_state(card.id, f"/NODE\n{_i(1)}{_r(0, 0, 0)}\n"))
    assert session.selection()["ids"] == []
    with pytest.raises(PrepError) as error:
        session.select_entity("node", 1)
    assert error.value.code == "ambiguous_selection"


@pytest.mark.parametrize(("formulation", "duplicate_family", "survives"),
                         (("SHELL", "SHELL", False), (None, "QUAD", False), ("SHELL", "QUAD", True)))
def test_shell_selection_accounts_for_display_omitted_duplicates(tmp_path, formulation, duplicate_family, survives):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "input"))
    mesh = session.document.resources[_card(session, "/SHELL/902")["resource_id"]]

    def pick():
        projection = session.mesh_view()
        return {key: projection[key] for key in ("document_id", "document_epoch", "revision", "projection_revision")} | {
            "kind": "element", "id": 7001, "resource_id": mesh.id,
            "resource_revision": projection["resource_revisions"][mesh.id], "formulation": formulation,
        }

    picked = session.select_pick(pick())
    assert picked["ids"] == [7001]
    state, _ = mesh.inserted_state(f"/{duplicate_family}/903\n{_i(7001, 501, 605, 709, 999999)}\n")
    session.dispatcher.execute(mesh.id, state, "Add element with missing node")
    assert sum(cell["id"] == 7001 for cell in session.mesh_view()["cells"]) == 1
    selected = session.selection()
    if survives:
        assert selected["ids"] == [7001]
        assert session.select_pick(pick())["refs"][0]["formulation"] == "SHELL"
    else:
        assert selected["ids"] == [] and selected["active_object"] is None
        with pytest.raises(PrepError) as error:
            session.select_pick(pick())
        assert error.value.code == "ambiguous_selection"
        if formulation is None:
            ref, = picked["refs"]
            field = RadProvider(session)._element_members_field([ref])
            assert field.value == (ref,) and ref not in field.choices


@pytest.mark.parametrize(("family", "connectivity"), (("SH4N", _i(501, 605, 709, 811)),
                                                    ("SHELL", _i(501, 605, 709) + " " * 10)),
                         ids=("shell-alias", "malformed-shell-connectivity"))
def test_qualified_shell_selection_rejects_same_family_duplicates(tmp_path, family, connectivity):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "input"))
    mesh = session.document.resources[_card(session, "/SHELL/902")["resource_id"]]
    picked, = session.select_entity("element", 7001, resource_id=mesh.id, formulation="SHELL")["refs"]
    state, _ = mesh.inserted_state(f"/{family}/903\n{_i(7001)}{connectivity}\n")
    session.dispatcher.execute(mesh.id, state, "Add a repeated native element ID")

    projection = session.mesh_view()
    if family == "SHELL":
        assert sum(cell["id"] == 7001 for cell in projection["cells"]) == 1
        assert [item["code"] for item in projection["diagnostics"]] == ["element_display_parse"]
    assert session.selection()["refs"] == []
    pick = {key: projection[key] for key in ("document_id", "document_epoch", "revision", "projection_revision")} | {
        "kind": "element", "id": 7001, "formulation": "SHELL", "resource_id": mesh.id,
        "resource_revision": projection["resource_revisions"][mesh.id],
    }
    with pytest.raises(PrepError) as error:
        session.select_pick(pick)
    assert error.value.code == "ambiguous_selection"
    with pytest.raises(PrepError) as error:
        session.create_element_group("Ambiguous shells", [picked], native_id=987)
    assert error.value.code == "ambiguous_reference"
    assert not any(card["keyword"] == "/GRSHEL/SHEL/987" for card in session.list_cards())


def test_unqualified_shell_pick_is_cleared_when_quad_uses_same_id(tmp_path):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "input"))
    selection = session.select_entity("element", 7001)
    assert selection["active_object"] and "formulation" not in selection["refs"][0]
    mesh = session.document.resources[selection["refs"][0]["resource_id"]]
    state, _ = mesh.inserted_state(f"/QUAD/903\n{_i(7001, 501, 605, 709, 811)}\n")
    session.dispatcher.execute(mesh.id, state, "Add same-ID quad")
    resolved = session.selection()
    assert resolved["ids"] == [] and resolved["active_object"] is None and resolved["selected_objects"] == []
    with pytest.raises(PrepError) as error:
        session.select_entity("element", 7001, resource_id=mesh.id)
    assert error.value.code == "ambiguous_selection"


@pytest.mark.parametrize("same_card", (False, True))
def test_malformed_tetra10_still_participates_in_native_id_resolution(tmp_path, same_card):
    source = tmp_path / "tetra10_0000.rad"
    nodes = "".join(f"{_i(node)}{_r(node, 0, 0)}\n" for node in range(1, 11))
    connectivity = _i(*range(1, 11))
    valid_rows = f"{_i(401)}\n{connectivity}\n{_i(402)}\n{connectivity}\n"
    malformed_rows = f"{_i(401)}\n{_i(*range(1, 10))}{' ' * 10}\n"
    source.write_text(f"/BEGIN\nTETRA10\n/NODE\n{nodes}/TETRA10/1\n{valid_rows}/END\n")
    session = PrepSession()
    session.open_rad(source)
    card = _card(session, "/TETRA10/1")
    owner = session.document.resources[card["resource_id"]]
    selected, = session.select_entity("element", 401, resource_id=owner.id, formulation="TETRA10")["refs"]
    if same_card:
        state = owner.replaced_state(card["id"], "/TETRA10/1\n" + malformed_rows + valid_rows)
    else:
        state, _ = owner.inserted_state("/TETRA10/1\n" + malformed_rows)
    session.dispatcher.execute(owner.id, state, "Add malformed duplicate TETRA10")

    projection = session.mesh_view()
    assert [cell["id"] for cell in projection["cells"]] == [401, 402]
    assert [entry["code"] for entry in projection["diagnostics"]] == ["element_display_parse"]
    assert not session.selection()["refs"]
    pick = {key: projection[key] for key in ("document_id", "document_epoch", "revision", "projection_revision")} | {
        "kind": "element", "id": 401, "formulation": "TETRA10", "resource_id": owner.id,
        "resource_revision": projection["resource_revisions"][owner.id],
    }
    with pytest.raises(PrepError) as error:
        session.select_pick(pick)
    assert error.value.code == "ambiguous_selection"
    with pytest.raises(PrepError) as error:
        session.create_element_group("Repeated TETRA10", [selected], native_id=990)
    assert error.value.code == "ambiguous_reference"
    assert not any(card["keyword"] == "/GRBRIC/BRIC/990" for card in session.list_cards())


def test_tetra10_resynchronizes_after_missing_connectivity(tmp_path):
    source = tmp_path / "tetra10_0000.rad"
    nodes = "".join(f"{_i(node)}{_r(node, 0, 0)}\n" for node in range(901, 911))
    connectivity = _i(*range(901, 911))
    source.write_text(f"/BEGIN\nTETRA10\n/NODE\n{nodes}/TETRA10/1\n{_i(401)}\n{connectivity}\n"
                      f"{_i(901)}\n{connectivity}\n/END\n")
    session = PrepSession()
    session.open_rad(source)
    owner = session.document.resources[_card(session, "/TETRA10/1")["resource_id"]]
    selected, = session.select_entity("element", 401, resource_id=owner.id, formulation="TETRA10")["refs"]
    state, _ = owner.inserted_state(f"/TETRA10/2\n{_i(777)}\n{_i(401)}\n{connectivity}\n")
    session.dispatcher.execute(owner.id, state, "Add a TETRA10 with missing connectivity")
    assert not session.selection()["refs"]
    assert 777 in session._projection_index["all_cells_by_id"]
    assert session.select_entity("element", 901, resource_id=owner.id, formulation="TETRA10")["ids"] == [901]
    projection = session.mesh_view()
    pick = {key: projection[key] for key in ("document_id", "document_epoch", "revision", "projection_revision")} | {
        "kind": "element", "id": 401, "formulation": "TETRA10", "resource_id": owner.id,
        "resource_revision": projection["resource_revisions"][owner.id],
    }
    with pytest.raises(PrepError) as error:
        session.select_pick(pick)
    assert error.value.code == "ambiguous_selection"
    with pytest.raises(PrepError) as error:
        session.create_element_group("Repeated TETRA10", [selected], native_id=990)
    assert error.value.code == "ambiguous_reference"


@pytest.mark.parametrize("layout", ("same-part-brick", "same-part-tet10", "cross-part-brick"))
def test_part_selection_checks_native_solid_namespace(tmp_path, layout):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "input"))
    mesh = session.document.resources[_card(session, "/SHELL/902")["resource_id"]]
    nodes = (101, 205, 309, 411, 501, 605, 709, 811)
    other_part = 903 if layout == "cross-part-brick" else 902
    blocks = [f"/TETRA4/902\n{_i(301, 101, 205, 309, 501)}\n"]
    if layout == "same-part-tet10":
        blocks.append(f"/NODE\n{_i(812)}{_r(8, 1, 2)}\n{_i(813)}{_r(9, 1, 2)}\n")
        blocks.append(f"/TETRA10/902\n{_i(301)}\n{_i(*nodes, 812, 813)}\n")
    else:
        blocks.append(f"/BRICK/{other_part}\n{_i(301, *nodes)}\n")
    state, _ = mesh.inserted_states(blocks)
    session.dispatcher.execute(mesh.id, state, "Add two elements in one solid namespace")
    with pytest.raises(PrepError) as error:
        session.select_entity("element", 301, resource_id=mesh.id)
    assert error.value.code == "ambiguous_selection"
    selected, = session.select_entity("element", 301, resource_id=mesh.id, formulation="TETRA4")["refs"]
    with pytest.raises(PrepError) as error:
        session.create_element_group("Ambiguous solids", [selected], native_id=990)
    assert error.value.code == "ambiguous_reference"
    for part_number in sorted({902, other_part}):
        part = _card(session, f"/PART/{part_number}")
        with pytest.raises(PrepError) as error:
            session.activate_object(RadProvider(session).ref_for_card(part))
        assert error.value.code == "ambiguous_selection"


@pytest.mark.parametrize("duplicate", (False, True))
def test_surface_rejects_malformed_elements_across_parts(tmp_path, duplicate):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "input"))
    part = _card(session, "/PART/903")
    mesh = session.document.resources[_card(session, "/SHELL/902")["resource_id"]]
    identifier = 7001 if duplicate else 7002
    state, _ = mesh.inserted_states((
        f"/SH4N/903\n{_i(identifier, 101, 205, 309)}{' ' * 10}\n",
        f"/SH3N/903\n{_i(299, 101, 205, 309)}\n",
    ))
    session.dispatcher.execute(mesh.id, state, "Add a malformed shell and a valid triangle")
    with pytest.raises(PrepError) as error:
        session.create_surface("Shell surface", [part["id"]], native_id=987)
    assert error.value.code == ("ambiguous_selection" if duplicate else "incompatible_surface")


@pytest.mark.parametrize(("keyword", "code"), (("SH4N", "ambiguous_selection"), ("QUAD", "incompatible_surface")))
def test_part_commands_count_malformed_native_cells(tmp_path, keyword, code):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "input"))
    part = _card(session, "/PART/902")
    mesh = session.document.resources[_card(session, "/SHELL/902")["resource_id"]]
    state, _ = mesh.inserted_state(f"/{keyword}/902\n{_i(7001, 101, 205, 309)}{' ' * 10}\n")
    session.dispatcher.execute(mesh.id, state, "Add a malformed element to the shell PART")
    with pytest.raises(PrepError) as error:
        if keyword == "SH4N":
            session.activate_object(RadProvider(session).ref_for_card(part))
        else:
            session.create_surface("Shell surface", [part["id"]], native_id=987)
    assert error.value.code == code
    if keyword == "SH4N":
        with pytest.raises(PrepError) as error:
            session.create_surface("Ambiguous shell surface", [part["id"]], native_id=987)
        assert error.value.code == "ambiguous_selection"


@pytest.mark.parametrize("write", ("restore", "field"))
@pytest.mark.parametrize("multiple", (False, True), ids=("single-part", "multiple-parts"))
def test_selected_part_highlight_tracks_renumbered_element(tmp_path, write, multiple):
    session = PrepSession()
    session.open_rad(_base_model(tmp_path / "input"))
    provider = RadProvider(session)
    first = provider.ref_for_card(_card(session, "/PART/902"))
    if multiple:
        second = provider.ref_for_card(_card(session, "/PART/903"))
        assert session.select_objects([first, second], active=first)["ids"] == [7001, 9007]
    else:
        assert session.activate_object(first)["ids"] == [7001]
    shell = _card(session, "/SHELL/902")
    mesh = session.document.resources[shell["resource_id"]]
    state = mesh.replaced_state(shell["id"], f"/SHELL/902\n{_i(99, 101, 205, 309, 411)}\n")
    if write == "restore":
        mesh.restore(state)
    else:
        session.dispatcher.execute(mesh.id, state, "Renumber selected part element")
    assert session.selection()["ids"] == ([99, 9007] if multiple else [99])
    assert session.active_object() == first


@pytest.mark.parametrize("first_reader", ("describe", "active_object", "selected_objects", "selection"))
@pytest.mark.parametrize("keyword", ("/GRNOD/NODE/1", "/MAT/LAW1/41"))
def test_selection_readers_agree_after_active_card_is_deleted(tmp_path, first_reader, keyword):
    session = PrepSession()
    if keyword.startswith("/MAT"):
        source = tmp_path / "material_0000.rad"
        source.write_text("/BEGIN\nMaterial\n/MAT/LAW1/41\nSteel\n             7.8e-9\n              210000                 0.3\n/END\n")
        session.open_rad(source)
    else:
        session.open_rad(_base_model(tmp_path / "input"))
        session.create_node_group("Target", [101])
    card = _card(session, keyword)
    ref = RadProvider(session).ref_for_card(card)
    assert session.activate_object(ref)["active_object"]["object_id"] == ref.object_id
    owner = session.document.resources[ref.resource_id]
    owner.restore(owner.deleted_state(ref.object_id))

    readers = {
        "describe": lambda: (session.describe()["active_object"], session.describe()["selected_objects"]),
        "active_object": session.active_object,
        "selected_objects": session.selected_objects,
        "selection": lambda: (session.selection()["active_object"], session.selection()["selected_objects"], session.selection()["ids"]),
    }
    expected = {"describe": (None, []), "active_object": None, "selected_objects": (), "selection": (None, [], [])}
    for name in (first_reader, *(name for name in readers if name != first_reader)):
        assert readers[name]() == expected[name]


def test_scalar_material_edits_reuse_structure_token_for_large_replaced_deck(tmp_path, monkeypatch):
    source = _base_model(tmp_path / "input")
    source.write_bytes(source.read_bytes().replace(b"#include mesh.inc\n", source.with_name("mesh.inc").read_bytes()))
    session = PrepSession()
    session.open_rad(source)
    owner = session._model_resource(None)
    expanded = "/NODE\n" + "".join(_i(i) + _r(i, 0, 0) + "\n" for i in range(1, 20_001))
    state = owner.replaced_state(_card(session, "/NODE")["id"], expanded)
    session.dispatcher.execute(owner.id, state, "Replace mesh nodes", kind="structure")
    original = session.mesh_view()
    assert len(original["node_ids"]) == 20_000
    material_card = _card(session, "/MAT/ELAST/17")
    material = material_card["id"]
    active = RadProvider(session).ref_for_card(material_card)
    session.activate_object(active)
    events = []
    session.subscribe(events.append)
    token = owner.structure_token()
    original_dumps, original_sha256 = deck.json.dumps, deck.hashlib.sha256
    structural_keys = {"created", "deleted", "replaced", "node_positions"}
    structural_payload = owner._raw_digest + original_dumps(
        {key: state[key] for key in structural_keys}, sort_keys=True).encode()
    serializations, hashes = [], []

    def tracked_dumps(value, *args, **kwargs):
        if isinstance(value, dict) and value.keys() == structural_keys:
            serializations.append(1)
        return original_dumps(value, *args, **kwargs)

    def tracked_sha256(value):
        if value == structural_payload:
            hashes.append(1)
        return original_sha256(value)

    monkeypatch.setattr(deck, "json", SimpleNamespace(dumps=tracked_dumps))
    monkeypatch.setattr(deck, "hashlib", SimpleNamespace(sha256=tracked_sha256))
    for index in range(41):
        session.set_fields(material, {"young_modulus": 190_000 + index})
    updated = session.mesh_view()
    assert updated["revision"] == original["revision"] + 41
    assert updated["projection_revision"] == original["projection_revision"]
    assert updated["points"] is original["points"] and owner.structure_token() == token
    assert (len(serializations), len(hashes)) == (0, 0)
    assert owner.structure_token() is token
    assert len(events) == 41 and all(event["kind"] == "field" for event in events)
    assert all(event["projection_revision"] == original["projection_revision"] for event in events)
    assert session.active_object() == active and session.selected_objects() == (active,)
