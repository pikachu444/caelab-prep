"""Reviewed CAD candidate replacement uses the existing stale-target contract."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_mesh_candidates import real_candidate
from test_mesh_adoption import _session, _native, _metadata_native


def referenced_model(candidate, *, moved=False):
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    old = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    if moved:
        plan = session.plan_node_move([{"reference": {"resource_id": session._root_id, "entity_kind": "node", "local_id": old["node_id_map"][node.id]},
                                       "position": [value + .01 for value in node.xyz]} for node in native.nodes], length_unit="mm")
        session.apply_node_move(plan["plan_id"])
    source_nodes = native.elements[0].node_ids[:2]
    members = [old["node_id_map"][node] for node in source_nodes]
    group = session.create_node_group("Old explicit nodes", members)["card_id"]
    condition = session.create_boundary_condition("Selected old nodes", group,
        [True, False, True], [False, False, False])["card_id"]
    return session, native, material, section, old, group, condition, members, source_nodes


def states(session):
    return {key: resource.snapshot() for key, resource in session.document.resources.items()}


def test_referenced_cad_plan_is_pure_sealed_and_one_undo(real_candidate, tmp_path):
    _, _, candidate = real_candidate
    session, native, material, section, old, group, condition, members, source_nodes = referenced_model(candidate)
    before, revision, paths, events = states(session), session.document.revision, set(session._source_paths), []
    raw_group, raw_condition = session.card_text(group), session.card_text(condition)
    session.subscribe(events.append)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    assert error.value.code == "mesh_replacement_in_use"
    plan = session.plan_cad_mesh_replacement(native, material_id=material, property_id=section,
                                            replace_part_ids=old["part_ids"])
    assert states(session) == before and session.document.revision == revision
    assert session._source_paths == paths and events == []
    assert plan["stale_targets"][group]["members"] == members
    assert plan["affected_conditions"] == [{"card_id": condition, "stale_target_ids": [group], "status": "stale"}]
    new_parts = list(plan["new_part_ids"])
    plan["new_part_ids"].clear(); plan["stale_targets"][group]["members"].clear()
    result = session.apply_cad_mesh_replacement(plan["plan_id"], expected_revision=revision,
                                               expected_document_id=plan["document_id"])
    assert session.document.revision == revision + 1 and result["part_ids"] == new_parts
    assert len(events) == 1 and session.card_text(group) == raw_group and session.card_text(condition) == raw_condition
    assert session.mesh_relationships()["stale_targets"][group]["members"] == members
    assert not set(members).intersection(session.mesh_view()["node_ids"])
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "blocked.rad")
    assert error.value.code == "stale_mesh_targets"
    applied = states(session)
    session.undo(); assert states(session) == before
    session.redo(); assert states(session) == applied
    project = tmp_path / "stale.caeprep"; session.save_project(project)
    reopened = PrepSession(); reopened.open_project(project)
    assert reopened.mesh_relationships()["stale_targets"][group]["members"] == members
    assert reopened.card_text(group) == raw_group and reopened.card_text(condition) == raw_condition
    with pytest.raises(PrepError) as error: reopened.export_rad(tmp_path / "still-blocked.rad")
    assert error.value.code == "stale_mesh_targets"
    mapping = {old_id: {"resource_id": reopened._root_id, "entity_kind": "node", "local_id": result["node_id_map"][source]}
               for old_id, source in zip(members, source_nodes)}
    reopened.reconnect_mesh_targets({group: {"mesh_revision": plan["mesh_revision"], "mapping": mapping}})
    assert reopened.mesh_relationships()["stale_targets"] == {}
    assert reopened.card_text(condition) == raw_condition
    output = tmp_path / "reconnected.rad"; reopened.export_rad(output)
    nodes, cells, parts = _native(output.read_bytes())
    assert len(nodes) == len(native.nodes) and len(cells) == len(native.elements) and len(parts) == len(native.parts)


def test_cancelled_cad_plan_cannot_publish(real_candidate):
    _, _, candidate = real_candidate
    session, native, material, section, old, *_ = referenced_model(candidate)
    before, revision = states(session), session.document.revision
    plan = session.plan_cad_mesh_replacement(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    session.cancel_cad_mesh_replacement(plan["plan_id"])
    with pytest.raises(PrepError) as error: session.apply_cad_mesh_replacement(plan["plan_id"])
    assert error.value.code == "stale_mesh_replacement_plan"
    assert states(session) == before and session.document.revision == revision


def test_moved_old_nodes_can_be_removed_without_dangling_position_overlays(real_candidate):
    _, _, candidate = real_candidate
    session, native, material, section, old, *_ = referenced_model(candidate, moved=True)
    before = states(session)
    assert before[session._root_id]["node_positions"]
    plan = session.plan_cad_mesh_replacement(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    result = session.apply_cad_mesh_replacement(plan["plan_id"])
    assert set(map(str, result["removed_node_ids"])).isdisjoint(session.document.resources[session._root_id].snapshot()["node_positions"])
    session.undo(); assert states(session) == before


@pytest.mark.parametrize("changed", ["revision", "resource", "epoch"])
def test_cad_plan_rejects_every_document_stamp_change(real_candidate, changed):
    _, _, candidate = real_candidate
    session, native, material, section, old, *_ = referenced_model(candidate)
    plan = session.plan_cad_mesh_replacement(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    if changed == "revision": session.create_material("Later material", 1e-9, 1000, .2)
    elif changed == "epoch": session._document_epoch = str(uuid4())
    else:
        root = session.document.resources[session._root_id]
        root.restore(root.inserted_state("/FUNCT/9901\nRaw change without revision\n                   0                   0\n")[0])
    before, revision, paths = states(session), session.document.revision, set(session._source_paths)
    with pytest.raises(PrepError) as error: session.apply_cad_mesh_replacement(plan["plan_id"])
    assert error.value.code == "stale_mesh_replacement_plan"
    assert states(session) == before and session.document.revision == revision and session._source_paths == paths


def test_candidate_change_and_publish_failure_preserve_model_and_source_paths(real_candidate, monkeypatch, tmp_path):
    _, _, candidate = real_candidate
    session, _, material, section, old, *_ = referenced_model(candidate)
    origin = tmp_path / "private-origin.step"; origin.write_bytes(b"private test path, never an original input")
    native, metadata, raw = _metadata_native(candidate, tmp_path, str(origin))
    plan = session.plan_cad_mesh_replacement(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    before, revision, paths = states(session), session.document.revision, set(session._source_paths)
    metadata.write_bytes(raw + b"\n")
    with pytest.raises(PrepError): session.apply_cad_mesh_replacement(plan["plan_id"])
    assert states(session) == before and session.document.revision == revision and session._source_paths == paths
    metadata.write_bytes(raw)
    seen = []
    def fail(*args, **kwargs):
        seen.append(str(origin.resolve()) in session._source_paths)
        raise RuntimeError("injected command publication failure")
    monkeypatch.setattr(session.dispatcher, "execute_many", fail)
    with pytest.raises(RuntimeError, match="injected"): session.apply_cad_mesh_replacement(plan["plan_id"])
    assert seen == [True] and states(session) == before
    assert session.document.revision == revision and session._source_paths == paths


@pytest.mark.parametrize("profile", ["BEAM", "TYPE3", "TRUSS", "TYPE2", "SKEW"])
def test_closed_reference_free_profiles_do_not_block_reviewed_replacement(real_candidate, profile):
    from caelab_prep.radioss import DeckResource
    _, _, candidate = real_candidate
    session, native, material, section, old, group, *_ = referenced_model(candidate)
    if profile == "SKEW":
        from caelab_prep.radioss.relations import frame_block
        text = frame_block(9901, "Fixed frame", [0,0,0], [0,1,0], [0,0,1])
    else:
        family = "beam_shell_tet" if profile in ("BEAM", "TYPE3") else "truss_shell_hex"
        source = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies" / family / "model_0000.rad"
        deck = DeckResource(source.read_bytes())
        card = next(card for card in deck.cards if card.keyword.startswith("/PROP/" + ("BEAM" if family == "beam_shell_tet" else "TRUSS")))
        text = "".join(deck.lines[card.start:card.stop]).replace(card.keyword, f"/PROP/{profile}/9901", 1)
    root = session.document.resources[session._root_id]
    state, ids = root.inserted_states([text]); session.dispatcher.execute(root.id, state, "Load known native profile")
    if profile == "SKEW":
        curve = session.create_curve("Load curve", [(0,0), (1,1)])["card_id"]
        session.create_load("Load in fixed frame", group, curve, "X", 2, coordinate_system_id=ids[0])
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    assert error.value.code == "mesh_replacement_in_use"
    before = states(session)
    plan = session.plan_cad_mesh_replacement(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    session.apply_cad_mesh_replacement(plan["plan_id"])
    assert session.card_text(ids[0]) == text
    session.undo(); assert states(session) == before


@pytest.mark.parametrize("kind", ["empty", "duplicate", "source_kind", "transform", "unknown", "foreign_elements"])
def test_unsupported_replacement_inputs_do_not_publish(real_candidate, kind):
    from caelab_prep.radioss import DeckResource
    _, _, candidate = real_candidate
    session, native, material, section, old, *_ = referenced_model(candidate)
    parts = old["part_ids"]
    if kind == "empty": parts = []
    elif kind == "duplicate": parts = parts * 2
    elif kind == "source_kind": native = replace(native, source_kind="standalone_msh")
    elif kind == "foreign_elements":
        part = session._find_card(parts[0]).card(parts[0]).keyword.split("/")[2]
        cell = native.elements[0]
        text = f"/TETRA4/{part}\n" + "".join(f"{value:10d}" for value in (9901, *(old["node_id_map"][node] for node in cell.node_ids))) + "\n"
        resource = DeckResource(text.encode(), is_include=True, name="foreign.inc")
        session.document.resources[resource.id] = resource
    else:
        root = session.document.resources[session._root_id]
        state, _ = root.inserted_state("/TRANSFORM/TRA/9901\nUnsupported transform\n" if kind == "transform" else "/UNKNOWN/9901\nUnmapped references\n")
        session.dispatcher.execute(root.id, state, "Load unsupported profile")
    before, revision, paths = states(session), session.document.revision, set(session._source_paths)
    with pytest.raises(PrepError):
        session.plan_cad_mesh_replacement(native, material_id=material, property_id=section, replace_part_ids=parts)
    assert states(session) == before and session.document.revision == revision and session._source_paths == paths


def test_contact_can_temporarily_lose_all_old_main_parts_until_explicit_reconnection(real_candidate, tmp_path):
    _, _, candidate = real_candidate
    if candidate.dimension != 2: pytest.skip("SURF/PART requires an actual shell candidate")
    session, native, material, section, old, group, _, members, source_nodes = referenced_model(candidate)
    main_source = native.elements[0].part_uuid
    surface = session.create_surface("One explicit old main PART", [old["part_id_map"][main_source]])["card_id"]
    contact = session.create_contact("Preserved contact", group, surface, .1)["card_id"]
    raw = session.card_text(contact)
    plan = session.plan_cad_mesh_replacement(native, material_id=material, property_id=section, replace_part_ids=old["part_ids"])
    assert set(plan["stale_targets"]) == {group, surface}
    result = session.apply_cad_mesh_replacement(plan["plan_id"])
    assert session.card_text(contact) == raw
    old_parts = plan["stale_targets"][surface]["members"]
    assert len(old_parts) == 1
    session.reconnect_mesh_targets({surface: {"mesh_revision": plan["mesh_revision"],
        "mapping": {old_parts[0]: result["part_id_map"][main_source]}}})
    assert set(session.mesh_relationships()["stale_targets"]) == {group}
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "pending-secondary.rad")
    assert error.value.code == "stale_mesh_targets"
    mapping = {old_id: {"resource_id": session._root_id, "entity_kind": "node", "local_id": result["node_id_map"][source]}
               for old_id, source in zip(members, source_nodes)}
    session.reconnect_mesh_targets({group: {"mesh_revision": plan["mesh_revision"], "mapping": mapping}})
    assert session.mesh_relationships()["stale_targets"] == {} and session.card_text(contact) == raw
    session.export_rad(tmp_path / "reconnected-contact.rad")
