"""Explicit element ownership changes, independent of PART material assignment."""
from dataclasses import asdict
from uuid import uuid4

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.mesh_edit_candidates import Ref
from caelab_prep.cae_core import PrepError
from test_group_member_review import related, state
from test_node_moves import MODELS, opened


def two_sources(first="beam_shell_tet"):
    session = opened(first)
    second = "truss_shell_hex" if first == "beam_shell_tet" else "beam_shell_tet"
    session.import_source(session.plan_import_source(MODELS / second / "model_0000.rad")["plan_id"])
    shells = [c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL"]
    return session, shells


def request(cell, target):
    return [{"element": asdict(cell.ref), "part": asdict(target)}]


@pytest.mark.parametrize("first", ["beam_shell_tet", "truss_shell_hex"])
def test_part_ownership_preserves_identity_geometry_and_one_undo_v6_export(first, tmp_path):
    session, shells = two_sources(first); source, target = shells
    before = state(session); original = session._mesh_edit_snapshot()
    raw = {r.id: r.raw for r in session._deck_resources()}; events = []; session.subscribe(events.append)
    review = session.plan_part_reassignment(request(source, target.part))
    assert review["admissible"] and state(session) == before and not events
    assert review["cells"][0]["before"]["part"] == asdict(source.part)
    assert review["cells"][0]["proposed"]["part"] == asdict(target.part)
    review["cells"].clear()
    session.apply_part_reassignment(review["plan_id"])
    assert len(events) == 1 and session.document.revision == before[0]+1
    after = session._mesh_edit_snapshot(); changed = next(c for c in after.cells if c.ref == source.ref)
    assert changed.part == target.part and changed.nodes == source.nodes and changed.orientation_node == source.orientation_node
    assert after.nodes == original.nodes and all(c == original._cells[c.ref] for c in after.cells if c.ref != source.ref)
    assert {r.id: r.raw for r in session._deck_resources()} == raw
    assigned = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == assigned[1:]
    path = tmp_path / "ownership.caeprep"; session.save_project(path)
    restored = PrepSession(); restored.open_project(path)
    out = tmp_path / "ownership_0000.rad"; restored.export_rad(out)
    native = PrepSession(); native.open_rad(out)
    native_part = session.part_assignments(target.part.local_id)["native_part_id"]
    assert next(c for c in native.mesh_view()["cells"] if c["id"] == source.ref.local_id)["part_id"] == native_part


def test_incoming_resource_is_recorded_for_unchanged_target_surface_and_contact(tmp_path):
    session, shells = two_sources(); source, target = shells
    main = session.create_surface("Existing target PART main", [target.part.local_id])["card_id"]
    secondary = session.create_node_group("Incoming source secondary", [3])["card_id"]
    contact = session.create_contact("Incoming segments", secondary, main, .2)["card_id"]
    declarations = {c: session.card_text(c) for c in (main, secondary, contact)}
    before = state(session)
    review = session.plan_part_reassignment(request(source, target.part))
    assert review["admissible"] and state(session) == before
    dependency = review["stale_targets"][main]["mesh_dependencies"]
    assert source.ref.resource_id in dependency and target.ref.resource_id not in dependency
    row = next(c for c in review["conditions"] if c["reference"]["local_id"] == contact)
    role = next(r for r in row["roles"] if r["role"] == "main")
    assert len(role["before_nodes"]) == 4 and len(role["after_nodes"]) == 8
    session.apply_part_reassignment(review["plan_id"])
    assert all(session.card_text(c) == raw for c, raw in declarations.items())
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "pending_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    stale = session.mesh_relationships()["stale_targets"]
    mapping = {main: {"mesh_revision": stale[main]["mesh_revision"], "mapping": {
        session.part_assignments(target.part.local_id)["native_part_id"]: target.part.local_id}},
        secondary: {"mesh_revision": stale[secondary]["mesh_revision"], "mapping": {
            3: session.resolve_entity_reference("node", 3)["reference"]}}}
    session.reconnect_mesh_targets(mapping)
    assert not session.mesh_relationships()["stale_targets"] and session.card_text(contact) == declarations[contact]
    session.export_rad(tmp_path / "connected_0000.rad")


@pytest.mark.parametrize("bad", ["empty", "duplicate", "node", "unknown", "family", "no_change"])
def test_invalid_part_assignment_keeps_document(bad):
    session, shells = two_sources(); source, target = shells
    values = request(source, target.part)
    if bad == "empty": values = []
    elif bad == "duplicate": values *= 2
    elif bad == "node": values[0]["element"]["entity_kind"] = "node"
    elif bad == "unknown": values[0]["part"]["local_id"] = str(uuid4())
    elif bad == "family":
        other = next(c for c in session._mesh_edit_snapshot().cells if c.family == "BEAM")
        values = request(source, other.part)
    elif bad == "no_change": values = request(source, source.part)
    before = state(session)
    with pytest.raises(PrepError): session.plan_part_reassignment(values)
    assert state(session) == before


@pytest.mark.parametrize("change", ["revision", "epoch", "token", "generation", "cancel"])
def test_stale_or_cancelled_part_assignment_never_applies(change):
    session, shells = two_sources(); source, target = shells
    review = session.plan_part_reassignment(request(source, target.part))
    if change == "revision": session.create_curve("Other", [(0, 0), (1, 1)])
    elif change == "epoch": session._document_epoch += ":changed"
    elif change == "token":
        owner = session.document.resources[source.ref.resource_id]
        owner.restore(owner.node_positions_state({"1": (0., 0., -.1)}))
    elif change == "generation":
        owner = session._relations_resource(); value = owner.snapshot()
        value["mesh_revisions"][source.ref.resource_id] = 99; owner.restore(value)
    else: session.cancel_part_reassignment(review["plan_id"])
    before = state(session)
    with pytest.raises(PrepError): session.apply_part_reassignment(review["plan_id"])
    assert state(session) == before


def empty_target(tmp_path):
    session = opened("beam_shell_tet")
    source = next(c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL")
    block = session.card_text(source.part.local_id).splitlines(keepends=True)
    block[0] = "/PART/900\n"; block[1] = "Empty shell target\n"
    base = MODELS / "beam_shell_tet"
    (tmp_path / "mesh.inc").write_bytes((base / "mesh.inc").read_bytes())
    path = tmp_path / "model_0000.rad"
    path.write_bytes((base / "model_0000.rad").read_bytes().replace(b"/END", "".join(block).encode("latin1")+b"/END"))
    session = PrepSession(); session.open_rad(path)
    source = next(c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL")
    copied = session.resolve_part_reference(900)["card_id"]
    target = Ref(session._find_card(copied).id, "part", copied)
    return session, source, target


def test_empty_existing_part_uses_actual_property_and_preserves_full_element_row(tmp_path):
    session, source, target = empty_target(tmp_path)
    before = state(session)
    review = session.plan_part_reassignment(request(source, target))
    assert review["admissible"] and state(session) == before
    session.apply_part_reassignment(review["plan_id"])
    actual = next(c for c in session._mesh_edit_snapshot().cells if c.ref == source.ref)
    assert actual.part == target and actual.nodes == source.nodes
    session.undo(); assert state(session)[1:] == before[1:]


@pytest.mark.parametrize("family", ["SHELL", "BEAM"])
def test_owner_move_preserves_native_row_suffix_orientation_comments_and_crlf(tmp_path, family):
    session = opened("beam_shell_tet")
    cell = next(c for c in session._mesh_edit_snapshot().cells if c.family == family)
    root = (MODELS / "beam_shell_tet/model_0000.rad").read_bytes()
    block = session.card_text(cell.part.local_id).splitlines(keepends=True); block[0] = "/PART/900\r\n"
    root = root.replace(b"/END", "".join(block).encode("latin1")+b"/END")
    raw = (MODELS / "beam_shell_tet/mesh.inc").read_bytes().replace(b"\r\n", b"\n")
    original_row = next(r for r in raw.splitlines() if r[:10].strip() == str(cell.ref.local_id).encode())
    tail = f"{12.5:20g}{.25:20g}".encode() if family == "SHELL" else b""
    raw = raw.replace(original_row+b"\n", b"# Preserve row comment\n"+original_row+tail+b"\n").replace(b"\n", b"\r\n")
    (tmp_path / "mesh.inc").write_bytes(raw); path = tmp_path / "model_0000.rad"; path.write_bytes(root)
    session = PrepSession(); session.open_rad(path)
    cell = next(c for c in session._mesh_edit_snapshot().cells if c.family == family)
    target_id = session.resolve_part_reference(900)["card_id"]
    target = Ref(session._find_card(target_id).id, "part", target_id)
    owner = session.document.resources[cell.ref.resource_id]
    plan = session.plan_part_reassignment(request(cell, target)); session.apply_part_reassignment(plan["plan_id"])
    assert owner.render().count(b"# Preserve row comment\r\n") == 1
    assert original_row+tail+b"\r\n" in owner.render()
    assert f"/{family}/900\r\n".encode() in owner.render() and owner.raw == raw
    assert (tmp_path / "mesh.inc").read_bytes() == raw


def test_last_old_main_part_cannot_be_silently_replaced_by_the_new_part():
    session, shells = two_sources(); source, target = shells
    surface = session.create_surface("Old PART only", [source.part.local_id])["card_id"]
    group = session.create_node_group("Secondary", [3])["card_id"]
    session.create_contact("Old main", group, surface, .2)
    before = state(session)
    with pytest.raises(PrepError) as error: session.plan_part_reassignment(request(source, target.part))
    assert error.value.code == "empty_projected_target" and state(session) == before


def test_coarse_shell_family_does_not_accept_an_invalid_target_formulation(tmp_path):
    session = opened("beam_shell_tet")
    cell = next(c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL")
    assignment = session.part_assignments(cell.part.local_id)
    prop = session.card_text(assignment["property_id"]).splitlines(keepends=True)
    prop[0] = "/PROP/TYPE1/901\n"
    # The property is empty at input; trial cells must still reject Ishell999.
    prop[2] = f"{999:10}" + prop[2][10:]
    part = session.card_text(cell.part.local_id).splitlines(keepends=True)
    part[0] = "/PART/900\n"; part[2] = f"{901:10}" + part[2][10:]
    base = MODELS / "beam_shell_tet"
    path = tmp_path / "model_0000.rad"
    path.write_bytes((base / "model_0000.rad").read_bytes().replace(b"/END", "".join(prop+part).encode("latin1")+b"/END"))
    (tmp_path / "mesh.inc").write_bytes((base / "mesh.inc").read_bytes())
    session = PrepSession(); session.open_rad(path)
    cell = next(c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL")
    target_id = session.resolve_part_reference(900)["card_id"]
    before = state(session)
    with pytest.raises(PrepError) as error:
        session.plan_part_reassignment(request(cell, Ref(session._find_card(target_id).id, "part", target_id)))
    assert error.value.code == "unsupported_part_profile" and state(session) == before


def test_moved_element_does_not_bypass_nested_file_directives(tmp_path):
    base = MODELS / "beam_shell_tet"
    (tmp_path / "model_0000.rad").write_bytes((base / "model_0000.rad").read_bytes())
    raw = (base / "mesh.inc").read_bytes().replace(b"/BEAM/10", b'#include "extra.inc"\n/BEAM/10', 1)
    (tmp_path / "mesh.inc").write_bytes(raw); (tmp_path / "extra.inc").write_text("# Keep include\n", encoding="ascii")
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    session.import_source(session.plan_import_source(MODELS / "truss_shell_hex/model_0000.rad")["plan_id"])
    source, target = [c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL"]
    before = state(session)
    with pytest.raises(PrepError) as error: session.plan_part_reassignment(request(source, target.part))
    assert error.value.code == "unsupported_part_move_layout" and state(session) == before


def test_supported_beam_target_can_still_remove_a_loaded_rotational_component(tmp_path):
    session = opened("beam_shell_tet")
    source = next(c for c in session._mesh_edit_snapshot().cells if c.family == "BEAM")
    assignment = session.part_assignments(source.part.local_id)
    owner = session._find_card(assignment["property_id"]); card = owner.card(assignment["property_id"])
    prop = session.card_text(card.id).splitlines(keepends=True); prop[0] = "/PROP/TYPE3/901\n"
    row = card.data[4]-card.start
    prop[row] = "0001110111" + prop[row][10:]  # release every end rotation, preserve the other native fields
    part = session.card_text(source.part.local_id).splitlines(keepends=True)
    part[0] = "/PART/900\n"; part[2] = f"{901:10}" + part[2][10:]
    base = MODELS / "beam_shell_tet"; path = tmp_path / "model_0000.rad"
    path.write_bytes((base / "model_0000.rad").read_bytes().replace(b"/END", "".join(prop+part).encode("latin1")+b"/END"))
    (tmp_path / "mesh.inc").write_bytes((base / "mesh.inc").read_bytes())
    session = PrepSession(); session.open_rad(path)
    source = next(c for c in session._mesh_edit_snapshot().cells if c.family == "BEAM")
    target_id = session.resolve_part_reference(900)["card_id"]
    group = session.create_node_group("Beam end", [5])["card_id"]
    curve = session.create_curve("Moment curve", [(0, 0), (1, 1)])["card_id"]
    load = session.create_load("End moment", group, curve, "XX", 1)["card_id"]
    assert session.condition_support(load)["status"] == "supported"
    before = state(session)
    plan = session.plan_part_reassignment(request(source, Ref(session._find_card(target_id).id, "part", target_id)))
    assert not plan["admissible"] and any(r["condition_id"] == load for r in plan["blocked"])
    assert state(session) == before
    with pytest.raises(PrepError) as error: session.apply_part_reassignment(plan["plan_id"])
    assert error.value.code == "unsupported_part_targets" and state(session) == before
