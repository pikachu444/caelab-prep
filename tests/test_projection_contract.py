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
