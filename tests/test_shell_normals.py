"""Native winding edits through the existing document/relations/codec contracts."""
from uuid import uuid4

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_group_member_review import related, state
from test_node_moves import MODELS, opened


def shell_ref(session):
    return session.resolve_entity_reference("element", 77)["reference"]


def copied_model(tmp_path, *, triangular=False, tail="", property_id=21, extra="", warped=False):
    base = MODELS / "beam_shell_tet"
    root = (base / "model_0000.rad").read_text(encoding="latin1")
    root = root.replace(f"{21:10}{41:10}{0:10}", f"{property_id:10}{41:10}{0:10}", 1)
    root = root.replace("/END", extra + "/END")
    mesh = (base / "mesh.inc").read_text(encoding="latin1")
    if triangular:
        mesh = mesh.replace("/SHELL/9", "/SH3N/9")
    rows = mesh.splitlines(keepends=True)
    for index, row in enumerate(rows):
        if row[:10].strip() == "77":
            nodes = [1, 2, 3] if triangular else [1, 2, 3, 4]
            rows[index] = "".join(f"{value:10}" for value in [77, *nodes]) + tail + "\r\n"
        if warped and row[:10].strip() == "3":
            rows[index] = row[:50] + f"{1.:20g}" + "\r\n"
    (tmp_path / "mesh.inc").write_bytes("".join(rows).encode("latin1"))
    (tmp_path / "model_0000.rad").write_text(root, encoding="latin1")
    session = PrepSession(); session.open_rad(tmp_path / "model_0000.rad")
    return session


@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
def test_one_publish_sealed_preview_undo_v6_and_native_roundtrip(name, tmp_path):
    session = opened(name)
    before = state(session)
    source_bytes = {r.id: r.raw for r in session._deck_resources()}
    original = session._mesh_edit_snapshot()
    reference = shell_ref(session)
    prior = next(c for c in original.cells if c.ref.local_id == 77)
    events = []; session.subscribe(events.append)
    review = session.plan_shell_normal_flip([reference])
    assert review["admissible"] and review["quality_before"] and review["quality_after"]
    assert state(session) == before and not events
    assert len(review["cells"]) == 1 and not review["stale_targets"]
    review["cells"][0]["proposed"]["nodes"] = []  # DTO mutation cannot edit the sealed plan.
    session.apply_shell_normal_flip(review["plan_id"], expected_revision=before[0])
    assert len(events) == 1 and session.document.revision == before[0] + 1
    changed = session._mesh_edit_snapshot()
    expected_nodes = tuple(prior.nodes[index] for index in (0, 3, 2, 1))
    actual = next(c for c in changed.cells if c.ref == prior.ref)
    assert actual.nodes == expected_nodes and actual.part == prior.part
    assert changed.nodes == original.nodes
    assert [c for c in changed.cells if c.ref != prior.ref] == [c for c in original.cells if c.ref != prior.ref]
    assert {r.id: r.raw for r in session._deck_resources()} == source_bytes
    after = state(session)
    session.undo(); assert state(session)[1:] == before[1:]
    session.redo(); assert state(session)[1:] == after[1:]
    project = tmp_path / "reversed.caeprep"; session.save_project(project)
    restored = PrepSession(); restored.open_project(project)
    assert next(c for c in restored._mesh_edit_snapshot().cells if c.ref.local_id == 77).nodes == expected_nodes
    output = tmp_path / "reversed_0000.rad"; restored.export_rad(output)
    exported = PrepSession(); exported.open_rad(output)
    assert [n.local_id for n in next(c for c in exported._mesh_edit_snapshot().cells if c.ref.local_id == 77).nodes] == [n.local_id for n in expected_nodes]


@pytest.mark.parametrize("triangular", [False, True])
def test_changes_only_connectivity_slots_preserving_element_tail_and_line_ending(tmp_path, triangular):
    tail = f"{12.5:20g}{.25:20g}"
    session = copied_model(tmp_path, triangular=triangular, tail=tail)
    reference = shell_ref(session)
    owner = session.document.resources[reference["resource_id"]]
    source = owner.render()
    review = session.plan_shell_normal_flip([reference])
    session.apply_shell_normal_flip(review["plan_id"])
    before = next(row for row in source.splitlines(keepends=True) if row[:10].strip() == b"77")
    after = next(row for row in owner.render().splitlines(keepends=True) if row[:10].strip() == b"77")
    prefix = 40 if triangular else 50
    assert before[prefix:] == after[prefix:] == (tail + "\r\n").encode("latin1")
    assert before[:10] == after[:10]
    assert after[10:prefix] == b"".join(f"{node:10}".encode() for node in ([1, 3, 2] if triangular else [1, 4, 3, 2]))
    assert owner.raw == source


def test_targets_remain_stale_until_explicit_identity_reconnection(tmp_path):
    session = opened("beam_shell_tet")
    group, load, bcs, velocity = related(session, [1, 2, 3, 4])
    declarations = {card: session.card_text(card) for card in (load, bcs, velocity)}
    review = session.plan_shell_normal_flip([shell_ref(session)])
    assert group in review["stale_targets"] and review["conditions"]
    assert all(row["after_support"]["status"] == "supported" for row in review["conditions"])
    session.apply_shell_normal_flip(review["plan_id"])
    assert all(session.card_text(card) == text for card, text in declarations.items())
    assert session.condition_support(load)["status"] == "stale"
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    project = tmp_path / "pending.caeprep"; session.save_project(project)
    restored = PrepSession(); restored.open_project(project)
    with pytest.raises(PrepError) as error: restored.export_rad(tmp_path / "still-blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    stale = session.mesh_relationships()["stale_targets"][group]
    session.reconnect_mesh_targets({group: {"mesh_revision": stale["mesh_revision"], "mapping": {
        node: session.resolve_entity_reference("node", node)["reference"] for node in stale["members"]}}})
    assert all(session.condition_support(card)["status"] == "supported" for card in declarations)
    session.export_rad(tmp_path / "reviewed_0000.rad")


@pytest.mark.parametrize("mutation", ["empty", "node", "foreign", "bool", "duplicate", "beam"])
def test_invalid_selection_never_changes_the_document(mutation):
    session = opened("beam_shell_tet")
    ref = shell_ref(session)
    if mutation == "node": ref["entity_kind"] = "node"
    if mutation == "foreign": ref["resource_id"] = str(uuid4())
    if mutation == "bool": ref["local_id"] = True
    if mutation == "beam": ref = session.resolve_entity_reference("element", 78)["reference"]
    before = state(session)
    with pytest.raises(PrepError):
        session.plan_shell_normal_flip([] if mutation == "empty" else [ref, ref] if mutation == "duplicate" else [ref])
    assert state(session) == before


@pytest.mark.parametrize("change", ["revision", "epoch", "token", "generation", "cancel"])
def test_apply_rejects_stale_or_cancelled_plan(change):
    session = opened("beam_shell_tet")
    review = session.plan_shell_normal_flip([shell_ref(session)])
    if change == "revision": session.create_material("Changed", density=1., young_modulus=1., poisson_ratio=.3)
    if change == "epoch": session._document_epoch = str(uuid4())
    if change == "token":
        resource = session.document.resources[shell_ref(session)["resource_id"]]
        resource.restore(resource.node_positions_state({"1": (0., 0., -.1)}))
    if change == "generation":
        relations = session._relations_resource(); value = relations.snapshot()
        value["mesh_revisions"][shell_ref(session)["resource_id"]] = 99
        relations.restore(value)
    if change == "cancel": session.cancel_shell_normal_flip(review["plan_id"])
    before = state(session)
    with pytest.raises(PrepError): session.apply_shell_normal_flip(review["plan_id"])
    assert state(session) == before


@pytest.mark.parametrize("bad", ["property", "warped", "pressure"])
def test_unsupported_profile_is_rejected_before_preview(tmp_path, bad):
    session = copied_model(tmp_path, property_id=23 if bad == "property" else 21,
        warped=bad == "warped", extra="/PLOAD/123\nUnsupported pressure\n" if bad == "pressure" else "")
    before = state(session)
    with pytest.raises(PrepError): session.plan_shell_normal_flip([shell_ref(session)])
    assert state(session) == before
