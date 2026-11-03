"""Explicit native row edits from the two fixed mixed inputs; no GUI/solver claim."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_group_member_review import related, state
from test_node_moves import MODELS, opened, updates


def request(session, source, keeper):
    refs = {value: session.resolve_entity_reference("node", value)["reference"] for value in (source, keeper)}
    pair = {"source": refs[source], "keeper": refs[keeper]}
    return [pair], [{**pair, "cross_parts": True, "contacts": [], "cross_resources": False}]


def plan(session, source, keeper, tolerance=20.):
    pairs, permissions = request(session, source, keeper)
    return session.plan_node_merge(pairs, tolerance=tolerance, length_unit="mm", approvals=permissions)


@pytest.mark.parametrize("name,source,keeper,family,nodes,orientation", [
    ("beam_shell_tet", 6, 8, "BEAM", [2, 5], 8),
    ("truss_shell_hex", 9, 4, "TRUSS", [8, 4], None),
])
def test_native_merge_one_publish_undo_v6_and_new_process_export(name, source, keeper, family, nodes, orientation, tmp_path):
    session = opened(name)
    before = state(session)
    originals = {r.id: r.raw for r in session._deck_resources()}
    events = []; session.subscribe(events.append)
    review = plan(session, source, keeper)
    assert review["admissible"] and not review["stale_targets"]
    assert state(session) == before and not events
    assert review["quality_after"] and not review["conditions"]
    review["cells"][0]["proposed"]["nodes"] = []  # The public DTO is not the sealed command.
    session.apply_node_merge(review["plan_id"], expected_revision=before[0])
    assert len(events) == 1 and session.document.revision == before[0] + 1
    snapshot = session._mesh_edit_snapshot()
    assert source not in {n.ref.local_id for n in snapshot.nodes}
    assert len(snapshot.nodes) == 8 and len(snapshot.cells) == 3
    cell = next(c for c in snapshot.cells if c.family == family)
    assert [r.local_id for r in cell.nodes] == nodes
    assert (cell.orientation_node.local_id if cell.orientation_node else None) == orientation
    assert {r.id: r.raw for r in session._deck_resources()} == originals
    after = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == after[1:]
    project = tmp_path / "merged.caeprep"; session.save_project(project)
    code = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(Path(sys.argv[1]).with_name('merged_0000.rad'))
p=s._mesh_edit_snapshot()
print(json.dumps({'nodes':[n.ref.local_id for n in p.nodes], 'cells':len(p.cells)}))
"""
    result = json.loads(subprocess.check_output([sys.executable, "-c", code, str(project)], text=True))
    assert source not in result["nodes"] and len(result["nodes"]) == 8 and result["cells"] == 3
    reopened = PrepSession(); reopened.open_rad(tmp_path / "merged_0000.rad")
    exported = next(c for c in reopened._mesh_edit_snapshot().cells if c.family == family)
    assert [r.local_id for r in exported.nodes] == nodes
    assert (exported.orientation_node.local_id if exported.orientation_node else None) == orientation


def test_merge_preserves_original_targets_stale_until_explicit_reconnection(tmp_path):
    session = opened("truss_shell_hex")
    group, load, bcs, velocity = related(session, [9])
    declarations = {card: session.card_text(card) for card in (load, bcs, velocity)}
    before = state(session)
    review = plan(session, 9, 4)
    assert review["admissible"] and group in review["stale_targets"]
    assert all(c["after_support"]["status"] == "supported" for c in review["conditions"])
    assert state(session) == before
    session.apply_node_merge(review["plan_id"])
    assert session.group_members(group)["member_ids"] == [9]
    assert all(session.card_text(card) == text for card, text in declarations.items())
    assert session.condition_support(load)["status"] == "stale"
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    project = tmp_path / "pending.caeprep"; session.save_project(project)
    restored = PrepSession(); restored.open_project(project)
    with pytest.raises(PrepError) as error: restored.export_rad(tmp_path / "still-blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    target = session.resolve_entity_reference("node", 4)["reference"]
    stale = session.mesh_relationships()["stale_targets"][group]
    session.reconnect_mesh_targets({group: {"mesh_revision": stale["mesh_revision"], "mapping": {9: target}}})
    assert session.group_members(group)["member_ids"] == [4]
    assert all(session.condition_support(card)["status"] == "supported" for card in (load, bcs, velocity))
    session.export_rad(tmp_path / "reconnected_0000.rad")


def test_many_to_one_group_is_projected_without_changing_the_original_declaration():
    session = opened("truss_shell_hex")
    group = session.create_node_group("Requires coalescence", [9, 4])["card_id"]
    before = state(session)
    review = plan(session, 9, 4)
    assert review["admissible"] and state(session) == before
    row = review["membership_coalescences"][0]
    assert row["group_ref"]["local_id"] == group and (row["old_link_count"], row["projected_unique_count"]) == (2, 1)
    session.apply_node_merge(review["plan_id"])
    assert session.group_members(group)["member_ids"] == [9, 4]
    assert group in session.mesh_relationships()["stale_targets"]


def test_native_merge_preserves_an_earlier_sparse_coordinate_overlay():
    session = opened("beam_shell_tet")
    move = session.plan_node_move(updates(session, {7: (10., 10., 11.)}), length_unit="mm")
    session.apply_node_move(move["plan_id"])
    before = state(session)
    review = plan(session, 6, 8); session.apply_node_merge(review["plan_id"])
    assert next(n.xyz for n in session._mesh_edit_snapshot().nodes if n.ref.local_id == 7) == (10., 10., 11.)
    session.undo(); assert state(session)[1:] == before[1:]


@pytest.mark.parametrize("change", ["revision", "epoch", "token", "generation"])
def test_merge_cas_rejects_a_changed_owner_without_publishing(change):
    session = opened("truss_shell_hex")
    review = plan(session, 9, 4)
    if change == "revision": session.create_curve("Concurrent", [(0, 0), (1, 1)])
    elif change == "epoch": session._document_epoch = str(uuid4())
    elif change == "generation":
        resource = session._relations_resource(); value = resource.snapshot()
        owner = session.resolve_entity_reference("node", 9)["reference"]["resource_id"]
        value["mesh_revisions"][owner] = 1; resource.restore(value)
    else:
        owner = session.resolve_entity_reference("node", 1)["reference"]["resource_id"]
        resource = session.document.resources[owner]
        resource.restore(resource.node_positions_state({"1": (0., 0., -.1)}))
    before = state(session)
    with pytest.raises(PrepError) as error: session.apply_node_merge(review["plan_id"])
    assert error.value.code == "stale_mesh_candidate"
    assert state(session) == before


def test_merge_does_not_drop_file_directives_from_an_affected_card(tmp_path):
    folder = MODELS / "beam_shell_tet"
    for name in ("model_0000.rad", "mesh.inc"): shutil.copyfile(folder / name, tmp_path / name)
    mesh = tmp_path / "mesh.inc"
    mesh.write_bytes(mesh.read_bytes().replace(b"/SHELL/9", b'#include "extra.inc"\n/SHELL/9', 1))
    (tmp_path / "extra.inc").write_text("# Untouched empty include\n", encoding="ascii")
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    before = state(session)
    with pytest.raises(PrepError) as error: plan(session, 6, 8)
    assert error.value.code == "unsupported_merge_layout"
    assert state(session) == before


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_short_last_connectivity_field_keeps_next_element_and_line_ending(tmp_path, ending):
    folder = MODELS / "truss_shell_hex"
    for name in ("model_0000.rad", "mesh.inc"): shutil.copyfile(folder / name, tmp_path / name)
    mesh = tmp_path / "mesh.inc"
    raw = mesh.read_bytes().replace(b"\r\n", b"\n")
    original = f"{78:10d}{8:10d}{9:10d}\n".encode("ascii")
    short = f"{78:10d}{8:10d}9\n{80:10d}{6:10d}{3:10d}\n".encode("ascii")
    assert original in raw
    mesh.write_bytes(raw.replace(original, short, 1).replace(b"\n", ending))
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    assert len(session._mesh_edit_snapshot().cells) == 4
    review = plan(session, 9, 4); session.apply_node_merge(review["plan_id"])
    snapshot = session._mesh_edit_snapshot()
    assert len(snapshot.cells) == 4
    assert [ref.local_id for ref in next(c for c in snapshot.cells if c.ref.local_id == 80).nodes] == [6, 3]
    resource = next(r for r in session._deck_resources() if any(c.keyword == "/TRUSS/10" for c in r.cards))
    assert f"{78:10d}{8:10d}{4:10d}".encode("ascii") + ending + f"{80:10d}".encode("ascii") in resource.render()


@pytest.mark.parametrize("secondary_in_source", [True, False])
def test_cross_resource_contact_records_the_changed_other_role_dependency(secondary_in_source):
    session = opened("truss_shell_hex")
    source = session.resolve_entity_reference("node", 9)["reference"]
    session.import_source(session.plan_import_source(MODELS / "beam_shell_tet" / "model_0000.rad")["plan_id"])
    snapshot = session._mesh_edit_snapshot()
    shell = next(c for c in snapshot.cells if c.family == "SHELL" and c.ref.resource_id != source["resource_id"])
    keeper = {"resource_id": shell.nodes[0].resource_id, "entity_kind": "node", "local_id": shell.nodes[0].local_id}
    secondary_ref = source if secondary_in_source else {"resource_id": shell.nodes[1].resource_id,
        "entity_kind": "node", "local_id": shell.nodes[1].local_id}
    secondary = session.create_node_group("Reviewed secondary", [secondary_ref["local_id"]])["card_id"]
    main = session.create_surface("Other source main", [shell.part.local_id])["card_id"]
    contact = session.create_contact("Cross source pair", secondary, main, .2)["card_id"]
    pair = {"source": source, "keeper": keeper}
    approval = {**pair, "cross_parts": True, "contacts": [
        {"resource_id": session._find_card(contact).id, "entity_kind": "condition", "local_id": contact}], "cross_resources": True}
    before = state(session)
    # Deliberately selected remote pair; 100 mm is not a recommended merge tolerance.
    review = session.plan_node_merge([pair], tolerance=100., length_unit="mm", approvals=[approval])
    assert review["admissible"] and state(session) == before
    assert {secondary, main} <= review["stale_targets"].keys()
    assert review["stale_targets"][main]["mesh_dependencies"] == {source["resource_id"]: 1}
    row = next(c for c in review["conditions"] if c["reference"]["local_id"] == contact)
    roles = {r["role"]: r for r in row["roles"]}
    assert roles["secondary"]["before_nodes"] == [secondary_ref]
    assert roles["secondary"]["after_nodes"] == [keeper if secondary_in_source else secondary_ref]
    assert len(roles["main"]["before_nodes"]) == len(roles["main"]["after_nodes"]) == 4
    session.apply_node_merge(review["plan_id"])
    relationships = session.mesh_relationships()
    assert source["resource_id"] in relationships["mesh_revisions"]
    assert keeper["resource_id"] not in relationships["mesh_revisions"]


def test_projected_velocity_overlap_is_visible_without_changing_declarations():
    session = opened("truss_shell_hex")
    source = session.create_node_group("Moving group", [9])["card_id"]
    keeper = session.create_node_group("Existing group", [4])["card_id"]
    first = session.create_initial_velocity("First vector", source, [1, 0, 0])["card_id"]
    second = session.create_initial_velocity("Other vector", keeper, [0, 2, 0])["card_id"]
    before = state(session)
    review = plan(session, 9, 4)
    assert review["admissible"] and state(session) == before
    overlap = review["initial_velocity_overlaps"][0]
    assert set(overlap["conditions"]) == {first, second}
    assert overlap["before_nodes"] == []
    assert [r["local_id"] for r in overlap["after_nodes"]] == [4]
    assert "not_evaluated" in overlap["effective_initial_state"]


def test_shared_foreign_node_load_is_rechecked_when_its_element_plane_changes(tmp_path):
    shutil.copyfile(MODELS / "beam_shell_tet" / "model_0000.rad", tmp_path / "model_0000.rad")
    def row(identifier, xyz):
        return f"{identifier:10d}" + "".join(f"{value:20g}" for value in xyz) + "\n"
    # Source owns the changing SH3N and node2. Its unchanged loaded node1 and
    # keeper4 belong to the separate include; only the source generation changes.
    (tmp_path / "mesh.inc").write_text('#include "nodes.inc"\n/NODE\n' + row(2, (1, 0, 0))
        + f"/SH3N/9\n{77:10d}{1:10d}{2:10d}{3:10d}\n", encoding="ascii")
    (tmp_path / "nodes.inc").write_text("/NODE\n" + row(1, (0, 0, 0)) + row(3, (0, 1, 0))
        + row(4, (1, 0, .1)), encoding="ascii")
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    group = session.create_node_group("Unchanged foreign loaded node", [1])["card_id"]
    curve = session.create_curve("Moment history", [(0, 0), (1, 1)])["card_id"]
    load = session.create_load("Initially in-plane XX", group, curve, "XX", 1)["card_id"]
    assert session.condition_support(load)["status"] == "supported"
    pair, approvals = request(session, 2, 4); approvals[0]["cross_resources"] = True
    before = state(session)
    review = session.plan_node_merge(pair, tolerance=.2, length_unit="mm", approvals=approvals)
    assert not review["admissible"]
    assert group in review["stale_targets"]
    assert review["stale_targets"][group]["mesh_dependencies"] == {pair[0]["source"]["resource_id"]: 1}
    affected = next(c for c in review["conditions"] if c["reference"]["local_id"] == load)
    assert affected["before_support"]["status"] == "supported"
    assert affected["after_support"]["status"] != "supported"
    with pytest.raises(PrepError) as error: session.apply_node_merge(review["plan_id"])
    assert error.value.code == "unsupported_merge_targets" and state(session) == before


def test_two_deck_resources_prepare_atomically_and_keep_both_review_dependencies(tmp_path, monkeypatch):
    shutil.copyfile(MODELS / "beam_shell_tet" / "model_0000.rad", tmp_path / "model_0000.rad")
    def row(identifier, xyz):
        return f"{identifier:10d}" + "".join(f"{value:20g}" for value in xyz) + "\n"
    (tmp_path / "mesh.inc").write_text('#include "nodes.inc"\n'
        + f"/SH3N/9\n{77:10d}{1:10d}{2:10d}{3:10d}\n", encoding="ascii")
    (tmp_path / "nodes.inc").write_text("/NODE\n" + row(1, (0, 0, 0)) + row(2, (1, 0, 0))
        + row(3, (0, 1, 0)) + row(4, (1, 0, .1)), encoding="ascii")
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    group = session.create_node_group("Unchanged force target", [1])["card_id"]
    curve = session.create_curve("Force history", [(0, 0), (1, 1)])["card_id"]
    load = session.create_load("Global Z force", group, curve, "Z", 1)["card_id"]
    review = plan(session, 2, 4, tolerance=.2)
    assert review["admissible"]
    source_owner = session.resolve_entity_reference("node", 2)["reference"]["resource_id"]
    cell_owner = next(c.ref.resource_id for c in session._mesh_edit_snapshot().cells)
    assert source_owner != cell_owner
    assert review["stale_targets"][group]["mesh_dependencies"] == {source_owner: 1, cell_owner: 1}
    before = state(session); events = []; session.subscribe(events.append)
    def fail_preparation(_): raise PrepError("injected_prepare_failure", "second native resource preparation failed")
    with monkeypatch.context() as patch:
        patch.setattr(session.document.resources[source_owner], "prepare_state", fail_preparation)
        with pytest.raises(PrepError) as error: session.apply_node_merge(review["plan_id"])
        assert error.value.code == "injected_prepare_failure"
    assert state(session) == before and events == []
    session.apply_node_merge(review["plan_id"])
    assert len(events) == 1 and session.document.revision == before[0] + 1
    changed = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == changed[1:]
    stale = session.mesh_relationships()["stale_targets"][group]
    session.reconnect_mesh_targets({group: {"mesh_revision": stale["mesh_revision"], "mapping": {
        1: session.resolve_entity_reference("node", 1)["reference"]}}})
    assert session.condition_support(load)["status"] == "supported"
    output = tmp_path / "export" / "two-resources_0000.rad"
    output.parent.mkdir()
    session.export_rad(output)


@pytest.mark.parametrize('name,source,keeper,group_node,family,changed_column', [
    ('beam_shell_tet', 6, 8, 2, 'BEAM', 3),
    ('truss_shell_hex', 9, 4, 9, 'TRUSS', 2),
])
def test_sparse_native_ids_preserve_untouched_fields_bcs_contact_and_roundtrip(
        name, source, keeper, group_node, family, changed_column, tmp_path):
    aliases = {1: 101, 2: 8, 3: 909, 4: 4007, 5: 55, 6: 600001, 7: 3, 8: 8400, 9: 99}
    folder = tmp_path / name; folder.mkdir()
    root = folder / 'model_0000.rad'; shutil.copyfile(MODELS / name / root.name, root)
    lines = (MODELS / name / 'mesh.inc').read_text(encoding='ascii').splitlines()
    output, node_rows, keyword = [], [], ''
    for line in lines:
        if line.startswith('/'):
            if node_rows: output.extend(reversed(node_rows)); node_rows.clear()
            keyword = line.split('/')[1]
            output.append(line)
        elif line and not line.startswith('#') and keyword == 'NODE':
            node_rows.append(f'{aliases[int(line[:10])]:010d}' + line[10:])
        elif line and not line.startswith('#') and keyword in ('BEAM', 'TRUSS', 'SHELL', 'TETRA4', 'BRICK'):
            values = [int(line[i:i+10]) for i in range(0, len(line), 10)]
            output.append(f'{values[0]:010d}' + ''.join(f'{aliases[value]:010d}' for value in values[1:]))
        else: output.append(line)
    if node_rows: output.extend(reversed(node_rows))
    mesh = folder / 'mesh.inc'; mesh.write_text('\n'.join(output) + '\n', encoding='ascii', newline='')
    input_bytes = {path: path.read_bytes() for path in (root, mesh)}
    session = PrepSession(); session.open_rad(root)
    group, load, bcs, velocity = related(session, [aliases[group_node]])
    surface = session.create_surface('Original main side', [session.resolve_part_reference(9)['card_id']])['card_id']
    contact = session.create_contact('Original ordered contact', group, surface, .2)['card_id']
    declarations = {card: session.card_text(card) for card in (load, bcs, velocity, contact)}
    owner = next(resource for resource in session._deck_resources() if resource.is_include)
    card = next(card for card in owner.cards if card.keyword == f'/{family}/10')
    original_line = owner.render().decode('latin1').splitlines()[card.data[0]]
    pairs, approvals = request(session, aliases[source], aliases[keeper])
    if family == 'TRUSS':
        approvals[0]['contacts'] = [{'resource_id': session._find_card(contact).id,
            'entity_kind': 'condition', 'local_id': contact}]
    before = state(session); events = []; session.subscribe(events.append)
    review = session.plan_node_merge(pairs, tolerance=20., length_unit='mm', approvals=approvals)
    assert review['admissible'] and state(session) == before
    session.apply_node_merge(review['plan_id'])
    assert len(events) == 1 and session.document.revision == before[0] + 1
    changed_line = owner.render().decode('latin1').splitlines()[owner.card(card.id).data[0]]
    start = changed_column * 10
    assert changed_line[:start] == original_line[:start]
    assert changed_line[start:start+10] == f'{aliases[keeper]:10d}'
    assert changed_line[start+10:] == original_line[start+10:]
    assert set(session.mesh_view()['node_ids']) == set(aliases.values()) - {aliases[source]}
    assert all(session.card_text(card) == text for card, text in declarations.items())
    assert all(path.read_bytes() == raw for path, raw in input_bytes.items())
    after = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == after[1:]
    with pytest.raises(PrepError) as error: session.export_rad(folder / 'blocked_0000.rad')
    assert error.value.code == 'stale_mesh_targets'
    targets = {}
    for identifier, stale in session.mesh_relationships()['stale_targets'].items():
        mapping = {old: (session.resolve_part_reference(old)['card_id'] if stale['family'] == 'SURF/PART'
                    else session.resolve_entity_reference('node', aliases[keeper] if old == aliases[source] else old)['reference'])
                   for old in stale['members']}
        targets[identifier] = {'mesh_revision': stale['mesh_revision'], 'mapping': mapping}
    session.reconnect_mesh_targets(targets)
    assert all(session.card_text(card) == text for card, text in declarations.items())
    project = folder / 'sparse.caeprep'; session.save_project(project)
    exported = folder / 'export' / 'sparse_0000.rad'; exported.parent.mkdir()
    code = """import json,sys
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(sys.argv[2])
native=PrepSession();native.open_rad(sys.argv[2])
families=('/BCS/', '/CLOAD/', '/INIVEL/TRA/', '/INTER/TYPE7/')
def conditions(owner):
    return [[c['keyword'],owner.card_text(c['id'])] for c in owner.list_cards() if c['keyword'].startswith(families)]
def cells(owner):
    return [[c.family,c.ref.local_id,[n.local_id for n in c.nodes],
             c.orientation_node.local_id if c.orientation_node else None] for c in owner._mesh_edit_snapshot().cells]
print(json.dumps({'nodes':s.mesh_view()['node_ids'],'conditions':[s.card_text(c) for c in sys.argv[3:]],
    'export_nodes':native.mesh_view()['node_ids'],'export_conditions':conditions(native),
    'document_conditions':conditions(s),'export_cells':cells(native),'document_cells':cells(s)}))
"""
    reopened = json.loads(subprocess.check_output([sys.executable, '-X', 'utf8', '-c', code,
        str(project), str(exported), *declarations], text=True))
    assert set(reopened['nodes']) == set(aliases.values()) - {aliases[source]}
    assert reopened['conditions'] == list(declarations.values()) and exported.is_file()
    assert set(reopened['export_nodes']) == set(reopened['nodes'])
    assert reopened['export_conditions'] == reopened['document_conditions']
    assert reopened['export_cells'] == reopened['document_cells']
