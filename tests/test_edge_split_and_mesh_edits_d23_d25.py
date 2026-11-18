"""Comprehensive D23 (6 existing mesh edits x 2 multi-resource #include decks) and D25 (split_triangle_edge) tests."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

import pytest

from caelab_prep.application import mesh_edit_candidates as edits
from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError, SelectionRef
from caelab_prep.radioss import DeckResource


_SH3N_ANGLE_THICKNESS = {101: (17.5, 2.75), 102: (-32.5, 4.25)}
_SH3N_TRAILING = {101: "  ", 102: f"{0:>10d}   "}
_SH3N_TAILS = {parent: f"{'':20}{angle:>20g}{thickness:>20g}" + _SH3N_TRAILING[parent]
               for parent, (angle, thickness) in _SH3N_ANGLE_THICKNESS.items()}


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("latin1"))
    return path


def _node_line(nid: int, x: float, y: float, z: float) -> str:
    return f"{nid:10d}{x:20.12g}{y:20.12g}{z:20.12g}"


def _tri_line(eid: int, n1: int, n2: int, n3: int) -> str:
    return f"{eid:10d}{n1:10d}{n2:10d}{n3:10d}"


def _quad_line(eid: int, n1: int, n2: int, n3: int, n4: int) -> str:
    return f"{eid:10d}{n1:10d}{n2:10d}{n3:10d}{n4:10d}"


def _tet_line(eid: int, n1: int, n2: int, n3: int, n4: int) -> str:
    return f"{eid:10d}{n1:10d}{n2:10d}{n3:10d}{n4:10d}"


def _build_deck_multi_include(root_dir: Path) -> Path:
    """Deck A: multi-#include model (nodes.inc + shells_a.inc + shells_b.inc) with full conditions."""
    _write(
        root_dir / "nodes.inc",
        "\n".join(
            [
                "/NODE",
                _node_line(1, 0.0, 0.0, 0.0),
                _node_line(2, 10.0, 0.0, 0.0),
                _node_line(3, 10.0, 10.0, 0.0),
                _node_line(4, 0.0, 10.0, 0.0),
                _node_line(5, 20.0, 0.0, 0.0),
                _node_line(6, 20.0, 10.0, 0.0),
                # Solid tet node
                _node_line(7, 5.0, 5.0, 10.0),
                # Component B triangle nodes (11, 12, 14), with node 11 matching node 2 within merge tolerance
                _node_line(11, 10.05, 0.0, 0.0),
                _node_line(12, 20.0, 0.0, 10.0),
                _node_line(14, 10.05, 10.0, 0.0),
                # Component B planar quad shell nodes (15..18) at z=10
                _node_line(15, 10.0, 0.0, 10.0),
                _node_line(16, 20.0, 0.0, 10.0),
                _node_line(17, 20.0, 10.0, 10.0),
                _node_line(18, 10.0, 10.0, 10.0),
                "",
            ]
        ),
    )
    _write(
        root_dir / "shells_a.inc",
        "\n".join(
            [
                "/SH3N/1",
                _tri_line(101, 1, 2, 3) + _SH3N_TAILS[101] + "\r",
                _tri_line(102, 1, 3, 4) + _SH3N_TAILS[102],
                _tri_line(103, 2, 5, 6),
                _tri_line(104, 2, 6, 3),
                "/TETRA4/3",
                _tet_line(301, 1, 2, 4, 7),
                "",
            ]
        ),
    )
    _write(
        root_dir / "shells_b.inc",
        "\n".join(
            [
                "/SHELL/2",
                _quad_line(201, 15, 16, 17, 18),
                "/SH3N/2",
                _tri_line(202, 11, 12, 14),
                "",
            ]
        ),
    )
    starter = _write(
        root_dir / "deck_a_0000.rad",
        "\n".join(
            [
                "#RADIOSS STARTER",
                "/BEGIN",
                "Multi-include D23/D25 Plate Deck A",
                "      2024         0",
                "                  Mg                  mm                   s",
                "                  Mg                  mm                   s",
                "/MAT/LAW1/1",
                "Steel S355",
                "            7.85e-09",
                "              210000                 0.3",
                "/MAT/LAW1/2",
                "Aluminum 6061",
                "             2.7e-09",
                "               70000                0.33",
                "/PROP/SHELL/1",
                "Shell 2mm",
                "        24         1         2         2                                       1",
                "                   0                   0                   0                   0               0.015",
                "         0                             2            0.833333                   2         0",
                "/PROP/SHELL/2",
                "Shell 3mm",
                "        24         1         2         2                                       1",
                "                   0                   0                   0                   0               0.015",
                "         0                             3            0.833333                   2         0",
                "/PROP/SOLID/3",
                "Solid Tet",
                "         1         4         0         0         0         0      1000         1                   0",
                "                 1.1                0.05                 0.1                   0                   0",
                "                   0                   0                   0                   0                   0",
                "/PART/1",
                "Main SH3N Plate",
                "         1         1         0",
                "/PART/2",
                "Partner Shell Plate",
                "         2         2         0",
                "/PART/3",
                "Support Tet Block",
                "         3         1         0",
                "/PART/4",
                "Transfer SH3N Target Part",
                "         2         1         0",
                "/SKEW/FIX/1",
                "Global Frame",
                "                   0                   0                   0",
                "                   0                   1                   0",
                "                   0                   0                   1",
                "/FUNCT/1",
                "Load Curve",
                "                   0                   0",
                "                   1                 100",
                "/GRNOD/NODE/10",
                "BC Support Nodes",
                "         1         4",
                "/GRNOD/NODE/11",
                "Load Tip Nodes",
                "         5         6         7",
                "/GRNOD/NODE/12",
                "Merge Contact Nodes",
                "         2        11",
                "/GRSH3N/SH3N/13",
                "Split Target Group",
                "       101       102",
                "/SURF/PART/14",
                "Partner Surface",
                "         2",
                "/BCS/20",
                "Clamp Left",
                "   111 000         0        10",
                "/CLOAD/21",
                "Tip Load",
                "         1         Z         1         0        11                               1                   1",
                "/INIVEL/TRA/22",
                "Initial Velocity",
                "                   0                   0                -100        11         1",
                "/INTER/TYPE7/23",
                "Plate Contact",
                "        12        14      1000         0         1                   0      1000         0         0",
                "                   1                   0                   0                             0",
                "                   0               1e+30                 0.4                   0         1         3",
                "                   1                 0.2                   0                   0               1e+30",
                "       000                            1000                0.05                   1                 0.2",
                "         0         0                   0         2         0         0                   1         0",
                "#include nodes.inc",
                "#include shells_a.inc",
                "#include shells_b.inc",
                "/END",
                "",
            ]
        ),
    )
    return starter


def _build_deck_mixed_assembly(root_dir: Path) -> Path:
    """Deck B: derived from mixed-assemblies beam_shell_tet with SH3N/SHELL/BEAM/TETRA4 + conditions."""
    src_dir = Path(__file__).resolve().parents[1] / "scripts" / "evaluation" / "models" / "mixed-assemblies" / "beam_shell_tet"
    shutil.copytree(src_dir, root_dir, dirs_exist_ok=True)
    # Enrich model_0000.rad with an alternate shell PART, SH3N group, BCS, and CLOAD, and add SH3N to mesh.inc
    mesh_inc = root_dir / "mesh.inc"
    orig_mesh_text = mesh_inc.read_text(encoding="latin1")
    extra_nodes = (
        "\n".join(
            [
                _node_line(15, 0.0, 20.0, 0.0),
                _node_line(16, 20.0, 20.0, 0.0),
                _node_line(17, 10.05, 10.0, 0.0),
            ]
        )
        + "\n"
    )
    orig_mesh_text = orig_mesh_text.replace("/SHELL/9\n", extra_nodes + "/SHELL/9\n", 1)
    mesh_inc.write_text(
        orig_mesh_text
        + "\n/SH3N/9\n"
        + _tri_line(81, 1, 2, 3)
        + "\n"
        + _tri_line(82, 1, 3, 4)
        + "\n"
        + _tri_line(83, 17, 16, 15)
        + "\n",
        encoding="latin1",
    )
    model_path = root_dir / "model_0000.rad"
    text = model_path.read_text(encoding="latin1")
    extra_cards = "\n".join(
        [
            "/PART/12",
            "Reassign Target Shell Part",
            "        21        41         0",
            "/FUNCT/1",
            "Load ramp",
            "                   0                   0",
            "                   1                  50",
            "/GRNOD/NODE/30",
            "Fixed Edge",
            "         1         4",
            "/GRNOD/NODE/31",
            "Loaded Tip",
            "         2         3",
            "/GRSH3N/SH3N/32",
            "Primary Triangles",
            "        81        82",
            "/SURF/PART/33",
            "Shell Part Surface",
            "         9",
            "/BCS/40",
            "Edge BCS",
            "   111 111         0        30",
            "/CLOAD/41",
            "Tip CLOAD",
            "         1         Z         0         0        31                               1                   1",
            "",
        ]
    )
    text = text.replace("#include mesh.inc", extra_cards + "#include mesh.inc")
    model_path.write_text(text, encoding="latin1")
    return model_path


def _find_card_id(session: PrepSession, prefix: str) -> str:
    upper = prefix.upper()
    matches = [c["id"] for c in session.list_cards() if c["keyword"].upper().startswith(upper)]
    assert len(matches) == 1, f"Expected unique card for {prefix}, got {matches}"
    return matches[0]


def _card_by_prefix(session: PrepSession, prefix: str) -> dict:
    upper = prefix.upper()
    matches = [c for c in session.list_cards() if c["keyword"].upper().startswith(upper)]
    assert len(matches) == 1, f"Expected unique card for {prefix}, got {matches}"
    return matches[0]


def _cell_ref(session: PrepSession, eid: int) -> dict:
    matches = [cell for cell in session.mesh_view()["cells"] if cell["id"] == eid]
    assert len(matches) == 1, f"Expected single element {eid}, got {matches}"
    return {"resource_id": matches[0]["resource_id"], "entity_kind": "element", "local_id": eid}


def _node_ref(session: PrepSession, nid: int, resource_id: str | None = None) -> dict:
    rids = session.mesh_view()["node_resources"][nid]
    rid = resource_id or rids[0]
    assert rid in rids
    return {"resource_id": rid, "entity_kind": "node", "local_id": nid}


def _reconnect_stale(session, replacements):
    """Use fixture-specified changes and resolve retained members by exact ID."""
    stale = session.mesh_relationships()["stale_targets"]
    keywords = {row["id"]: row["keyword"] for row in session.list_cards()}
    assert set(replacements) <= {keywords[group_id] for group_id in stale}
    direct, review = {}, {}
    for group_id, record in stale.items():
        keyword = keywords[group_id]
        overrides = replacements.get(keyword, {})
        assert set(overrides) <= set(record["members"])
        family = record["family"]
        mapping, dropped, node_ids = {}, [], []
        for old in record["members"]:
            target = overrides.get(old, record.get("parent_to_children", {}).get(old, old))
            if target is None:
                dropped.append(old)
            elif family == "SURF/PART":
                mapping[old] = session.resolve_part_reference(target)["card_id"]
            elif family == "GRNOD/NODE":
                mapping[old] = session.resolve_entity_reference("node", target)["reference"]
                node_ids.append(target)
            elif isinstance(target, list):
                mapping[old] = [SelectionRef(**session.resolve_entity_reference("element", child)["reference"])
                                for child in target]
            else:
                mapping[old] = session.resolve_entity_reference("element", target)["reference"]
        assert mapping, f"{keyword} lost all members"
        entry = {"mesh_revision": record["mesh_revision"], "mapping": mapping}
        if dropped:
            entry["drop_members"] = dropped
        if len(node_ids) != len(set(node_ids)):
            entry["coalesce_duplicates"] = True
        (review if set(entry) - {"mesh_revision", "mapping"} else direct)[group_id] = entry

    if direct:
        session.reconnect_mesh_targets(direct)
    if review:
        plan = session.plan_mesh_reconnection(review)
        session.apply_mesh_reconnection(plan["plan_id"])


def _mesh_facts(session):
    view = session.mesh_view()
    sources = {rid: (None if rid == session._root_id else path) for rid, path in session._paths.items()}
    nodes = {nid: (tuple(xyz), tuple(sources[rid] for rid in view["node_resources"][nid]))
             for nid, xyz in zip(view["node_ids"], view["points"])}
    beam_orientations = {}
    for resource in session._deck_resources():
        lines = resource.render().decode("latin1").splitlines()
        for card in resource.cards:
            if card.keyword.startswith("/BEAM/"):
                for line in (lines[row] for row in card.data):
                    beam_orientations[resource.id, int(line[:10])] = int(line[30:40].strip() or 0)
    cells = {(sources[c["resource_id"]], c["formulation"], c["id"]):
             (tuple(c["nodes"]), beam_orientations.get((c["resource_id"], c["id"])),
              c["part_id"], sources[c["part_ref"]["resource_id"]])
             for c in view["cells"]}
    return nodes, cells


def _target_facts(session):
    groups, conditions = {}, {}
    cards = session.list_cards()
    keywords = {card["id"]: card["keyword"] for card in cards}
    for row in cards:
        keyword = row["keyword"]
        if keyword.startswith(("/GR", "/SURF/PART/")):
            resource = session._find_card(row["id"])
            groups[keyword] = session._integer_members(resource, resource.card(row["id"]))
        elif keyword.startswith(("/BCS/", "/CLOAD/", "/INIVEL/TRA/", "/INTER/TYPE7/")):
            values = session.condition_values(row["id"])
            assert values["diagnostics"] == []
            conditions[keyword] = {key: keywords.get(value, value) if isinstance(value, str) else value
                                   for key, value in values.items() if key not in ("card_id", "resource_id")}
    return groups, conditions


def _roundtrip_save_reconnect_and_export(session, tmp_path, tag, *, replacements=None, expected_groups=None):
    original_groups, original_conditions = _target_facts(session)
    groups_after = {**original_groups, **(expected_groups or {})}
    assert session.mesh_relationships()["stale_targets"], f"{tag}: expected stale targets before save"
    proj_path = tmp_path / f"{tag}.caeprep"
    session.save_project(str(proj_path))

    # Reopen in a completely fresh PrepSession to verify persisted deltas + stale targets
    reopened = PrepSession()
    reopened.open_project(str(proj_path))
    assert reopened.mesh_relationships()["stale_targets"] == session.mesh_relationships()["stale_targets"]
    assert _mesh_facts(reopened) == _mesh_facts(session)
    assert _target_facts(reopened) == _target_facts(session)
    with pytest.raises(PrepError) as export_block:
        reopened.export_rad(str(tmp_path / f"blocked_{tag}_0000.rad"))
    assert export_block.value.code == "stale_mesh_targets"

    _reconnect_stale(reopened, replacements or {})
    assert reopened.mesh_relationships()["stale_targets"] == {}
    assert _mesh_facts(reopened) == _mesh_facts(session)
    assert _target_facts(reopened) == (groups_after, original_conditions)

    out_dir = tmp_path / f"export_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = reopened.export_solver_inputs(str(out_dir / f"{tag}_0000.rad"), end_time=0.01, output_interval=0.002)
    assert Path(out["starter_path"]).is_file()
    assert Path(out["engine_path"]).is_file()
    # Fresh PrepSession must cleanly re-open exported Starter deck
    verify = PrepSession()
    verify.open_rad(out["starter_path"])
    assert _mesh_facts(verify) == _mesh_facts(reopened)
    assert _target_facts(verify) == (groups_after, original_conditions)
    return verify


@pytest.mark.parametrize("deck_kind", ("deck_a", "deck_b"))
def test_d23_six_existing_mesh_edits_end_to_end_across_two_multiresource_decks(tmp_path: Path, deck_kind: str):
    """Exercise all 6 existing mesh edits across two multi-resource #include decks end-to-end."""
    deck_dir = tmp_path / deck_kind
    starter = _build_deck_multi_include(deck_dir) if deck_kind == "deck_a" else _build_deck_mixed_assembly(deck_dir)

    # 1. node_move: preview -> impact -> cancel -> apply -> 1 undo/redo -> save/reopen -> reconnect -> export
    s1 = PrepSession()
    s1.open_rad(str(starter))
    rev0 = s1.document.revision
    tip_node = 5 if deck_kind == "deck_a" else 2
    nref = _node_ref(s1, tip_node)
    pts = dict(zip(s1.mesh_view()["node_ids"], s1.mesh_view()["points"]))
    orig_xyz = tuple(pts[tip_node])
    moved_xyz = [orig_xyz[0] + 1.25, orig_xyz[1], orig_xyz[2]]
    move_plan = s1.plan_node_move([{"reference": nref, "position": moved_xyz}], length_unit="mm")
    assert move_plan["impacts"] and move_plan["stale_targets"]
    assert s1.document.revision == rev0
    s1.cancel_node_move(move_plan["plan_id"])
    assert s1.document.revision == rev0

    move_plan = s1.plan_node_move([{"reference": nref, "position": moved_xyz}], length_unit="mm")
    s1.apply_node_move(move_plan["plan_id"], expected_revision=s1.document.revision, expected_document_id=s1.document.id)
    assert s1.document.revision == rev0 + 1
    s1.undo()
    assert s1.document.revision == rev0 + 2
    assert dict(zip(s1.mesh_view()["node_ids"], s1.mesh_view()["points"]))[tip_node] == orig_xyz
    s1.redo()
    assert _mesh_facts(s1)[0][tip_node][0] == tuple(moved_xyz)
    _roundtrip_save_reconnect_and_export(s1, tmp_path, f"{deck_kind}_move")

    # 2. node_merge: preview -> approvals -> cancel -> apply -> 1 undo/redo -> save/reopen -> reconnect -> export
    s2 = PrepSession()
    s2.open_rad(str(starter))
    rev0 = s2.document.revision
    if deck_kind == "deck_a":
        src_nid, keep_nid = 11, 2
        contact_id = _find_card_id(s2, "/INTER/TYPE7/23")
        contact_ref = {"resource_id": s2._root_id, "entity_kind": "condition", "local_id": contact_id}
        approvals = ({"source": _node_ref(s2, src_nid), "keeper": _node_ref(s2, keep_nid),
                      "cross_resources": False, "cross_parts": True, "contacts": [contact_ref]},)
        tol = 0.2
    else:
        src_nid, keep_nid = 17, 3
        approvals = ({"source": _node_ref(s2, src_nid), "keeper": _node_ref(s2, keep_nid),
                      "cross_resources": False, "cross_parts": True, "contacts": []},)
        tol = 0.2
    merge_plan = s2.plan_node_merge(
        [{"source": _node_ref(s2, src_nid), "keeper": _node_ref(s2, keep_nid)}],
        tolerance=tol, length_unit="mm", approvals=approvals,
    )
    original_nodes, original_cells = _mesh_facts(s2)
    assert merge_plan["admissible"]
    assert s2.document.revision == rev0
    s2.cancel_node_merge(merge_plan["plan_id"])
    merge_plan = s2.plan_node_merge(
        [{"source": _node_ref(s2, src_nid), "keeper": _node_ref(s2, keep_nid)}],
        tolerance=tol, length_unit="mm", approvals=approvals,
    )
    s2.apply_node_merge(merge_plan["plan_id"], expected_revision=s2.document.revision, expected_document_id=s2.document.id)
    assert src_nid not in s2.mesh_view()["node_ids"]
    s2.undo()
    assert src_nid in s2.mesh_view()["node_ids"]
    s2.redo()
    assert src_nid not in s2.mesh_view()["node_ids"]
    expected_cells = {ref: (tuple(keep_nid if node == src_nid else node for node in nodes),
                             keep_nid if orientation == src_nid else orientation, part_id, part_src)
                      for ref, (nodes, orientation, part_id, part_src) in original_cells.items()}
    assert _mesh_facts(s2) == ({nid: xyz for nid, xyz in original_nodes.items() if nid != src_nid}, expected_cells)
    _roundtrip_save_reconnect_and_export(s2, tmp_path, f"{deck_kind}_merge",
        replacements={"/GRNOD/NODE/12": {11: 2}} if deck_kind == "deck_a" else {},
        expected_groups={"/GRNOD/NODE/12": [2]} if deck_kind == "deck_a" else {})

    # 3. element_deletion: preview -> cancel -> apply -> 1 undo/redo -> save/reopen -> reconnect -> export
    s3 = PrepSession()
    s3.open_rad(str(starter))
    original_nodes, original_cells = _mesh_facts(s3)
    rev0 = s3.document.revision
    del_eid = 104 if deck_kind == "deck_a" else 82
    del_plan = s3.plan_element_deletion([_cell_ref(s3, del_eid)], orphan_policy="keep")
    assert del_plan["admissible"]
    s3.cancel_element_deletion(del_plan["plan_id"])
    assert s3.document.revision == rev0
    del_plan = s3.plan_element_deletion([_cell_ref(s3, del_eid)], orphan_policy="keep")
    s3.apply_element_deletion(del_plan["plan_id"], expected_revision=s3.document.revision, expected_document_id=s3.document.id)
    assert all(c["id"] != del_eid for c in s3.mesh_view()["cells"])
    s3.undo()
    assert any(c["id"] == del_eid for c in s3.mesh_view()["cells"])
    s3.redo()
    assert _mesh_facts(s3) == (original_nodes, {ref: cell for ref, cell in original_cells.items() if ref[2] != del_eid})
    _roundtrip_save_reconnect_and_export(s3, tmp_path, f"{deck_kind}_delete",
        replacements={"/GRSH3N/SH3N/32": {82: None}} if deck_kind == "deck_b" else {},
        expected_groups={"/GRSH3N/SH3N/32": [81]} if deck_kind == "deck_b" else {})

    # 4. shell_normal_flip: preview -> cancel -> apply -> 1 undo/redo -> save/reopen -> reconnect -> export
    s4 = PrepSession()
    s4.open_rad(str(starter))
    flip_eid = 101 if deck_kind == "deck_a" else 81
    before_nodes = next(c["nodes"] for c in s4.mesh_view()["cells"] if c["id"] == flip_eid)
    flip_plan = s4.plan_shell_normal_flip([_cell_ref(s4, flip_eid)])
    assert flip_plan["admissible"]
    s4.cancel_shell_normal_flip(flip_plan["plan_id"])
    flip_plan = s4.plan_shell_normal_flip([_cell_ref(s4, flip_eid)])
    s4.apply_shell_normal_flip(flip_plan["plan_id"], expected_revision=s4.document.revision, expected_document_id=s4.document.id)
    after_nodes = next(c["nodes"] for c in s4.mesh_view()["cells"] if c["id"] == flip_eid)
    assert tuple(after_nodes) == (before_nodes[0], before_nodes[2], before_nodes[1])
    s4.undo()
    assert next(c["nodes"] for c in s4.mesh_view()["cells"] if c["id"] == flip_eid) == before_nodes
    s4.redo()
    assert next(c["nodes"] for c in s4.mesh_view()["cells"] if c["id"] == flip_eid) == after_nodes
    _roundtrip_save_reconnect_and_export(s4, tmp_path, f"{deck_kind}_flip")

    # 5. part_reassignment: preview -> cancel -> apply -> 1 undo/redo -> save/reopen -> reconnect -> export
    s5 = PrepSession()
    s5.open_rad(str(starter))
    original_nodes, original_cells = _mesh_facts(s5)
    reassign_eid = 103 if deck_kind == "deck_a" else 82
    target_part_card = _card_by_prefix(s5, "/PART/4" if deck_kind == "deck_a" else "/PART/12")
    part_ref = {"resource_id": target_part_card["resource_id"], "entity_kind": "part", "local_id": target_part_card["id"]}
    part_plan = s5.plan_part_reassignment([{"element": _cell_ref(s5, reassign_eid), "part": part_ref}])
    assert part_plan["admissible"]
    s5.cancel_part_reassignment(part_plan["plan_id"])
    part_plan = s5.plan_part_reassignment([{"element": _cell_ref(s5, reassign_eid), "part": part_ref}])
    s5.apply_part_reassignment(part_plan["plan_id"], expected_revision=s5.document.revision, expected_document_id=s5.document.id)
    assert next(c["part_id"] for c in s5.mesh_view()["cells"] if c["id"] == reassign_eid) == (4 if deck_kind == "deck_a" else 12)
    s5.undo()
    assert next(c["part_id"] for c in s5.mesh_view()["cells"] if c["id"] == reassign_eid) != (4 if deck_kind == "deck_a" else 12)
    s5.redo()
    target_part = 4 if deck_kind == "deck_a" else 12
    expected_cells = {ref: (*cell[:2], target_part, None) if ref[2] == reassign_eid else cell
                      for ref, cell in original_cells.items()}
    assert _mesh_facts(s5) == (original_nodes, expected_cells)
    _roundtrip_save_reconnect_and_export(s5, tmp_path, f"{deck_kind}_part")

    # 6. size_remesh / replacement + CAD candidate adoption on multi-resource include deck:
    s6 = PrepSession()
    s6.open_rad(str(starter))
    if deck_kind == "deck_a":
        target_inc_id = next(r_id for r_id, p in s6._paths.items() if p.endswith("shells_b.inc"))
        fine_inc = _write(
            tmp_path / "fine_shells_b.inc",
            "\n".join(
                [
                    "/SHELL/2",
                    _quad_line(501, 15, 16, 17, 18),
                    "/SH3N/2",
                    _tri_line(502, 11, 12, 17),
                    _tri_line(503, 11, 17, 14),
                    "",
                ]
            ),
        )
        remesh_plan = s6.plan_mesh_replacement(target_inc_id, str(fine_inc))
        assert remesh_plan["element_count"] == len(s6.mesh_view()["cells"]) + 1
        s6.replace_prepared_mesh(remesh_plan["plan_id"], expected_revision=s6.document.revision, expected_document_id=s6.document.id)
        assert any(c["id"] == 503 for c in s6.mesh_view()["cells"])
        s6.undo()
        assert all(c["id"] != 503 for c in s6.mesh_view()["cells"])
        s6.redo()
        assert any(c["id"] == 503 for c in s6.mesh_view()["cells"])
        _roundtrip_save_reconnect_and_export(s6, tmp_path, f"{deck_kind}_remesh")
    else:
        # Exercise real Gmsh structured remesh adoption AND include mesh replacement on Deck B
        from caelab_prep.application.structured_mesh import generate_structured_mesh

        mat41 = _card_by_prefix(s6, "/MAT/LAW1/41")
        prop21 = _card_by_prefix(s6, "/PROP/SHELL/21")
        spec = {
            "mode": "quad",
            "unit": "mm",
            "corners": [[0.0, 0.0, 20.0], [10.0, 0.0, 20.0], [10.0, 10.0, 20.0], [0.0, 10.0, 20.0]],
            "divisions": [4, 4],
            "name": "Gmsh Structured Remesh",
        }
        cand = generate_structured_mesh(spec, tmp_path / "gmsh_structured_cand")
        before_cells = len(s6.mesh_view()["cells"])
        adopted = s6.adopt_mesh_candidate(cand.to_native_mesh(), material_id=mat41["id"], property_id=prop21["id"], name="Adopted Plate")
        assert len(s6.mesh_view()["cells"]) == before_cells + 16
        s6.undo()
        assert len(s6.mesh_view()["cells"]) == before_cells
        s6.redo()
        assert len(s6.mesh_view()["cells"]) == before_cells + 16

        # Now replace mesh.inc with finer SH3N mesh via plan_mesh_replacement -> replace_prepared_mesh -> roundtrip
        mesh_inc_id = next(r_id for r_id, p in s6._paths.items() if p.endswith("mesh.inc"))
        fine_mesh_inc = _write(
            tmp_path / "fine_mesh_b.inc",
            "\n".join(
                [
                    "/NODE",
                    _node_line(1, 0, 0, 0),
                    _node_line(2, 10, 0, 0),
                    _node_line(3, 10, 10, 0),
                    _node_line(4, 0, 10, 0),
                    _node_line(5, 20, 0, 0),
                    _node_line(6, 10, 0, 10),
                    _node_line(7, 10, 10, 10),
                    _node_line(8, 20, 10, 0),
                    _node_line(9, 10, 20, 0),
                    _node_line(15, 0.0, 20.0, 0.0),
                    _node_line(16, 20.0, 20.0, 0.0),
                    _node_line(17, 10.05, 10.0, 0.0),
                    _node_line(100, 5.0, 5.0, 0.0),
                    "/SHELL/9",
                    _quad_line(77, 1, 2, 3, 4),
                    "/BEAM/10",
                    "        78         2         5         6",
                    "/TETRA4/11",
                    _tet_line(79, 3, 8, 9, 7),
                    "/SH3N/9",
                    _tri_line(581, 1, 2, 100),
                    _tri_line(582, 2, 3, 100),
                    _tri_line(583, 3, 4, 100),
                    _tri_line(584, 4, 1, 100),
                    _tri_line(585, 17, 16, 15),
                    "",
                ]
            ),
        )
        remesh_plan = s6.plan_mesh_replacement(mesh_inc_id, str(fine_mesh_inc))
        assert remesh_plan["stale_targets"]
        s6.replace_prepared_mesh(remesh_plan["plan_id"], expected_revision=s6.document.revision, expected_document_id=s6.document.id)
        assert any(c["id"] == 584 for c in s6.mesh_view()["cells"])
        s6.undo()
        assert all(c["id"] != 584 for c in s6.mesh_view()["cells"])
        s6.redo()
        assert any(c["id"] == 584 for c in s6.mesh_view()["cells"])
        exported = _roundtrip_save_reconnect_and_export(s6, tmp_path, f"{deck_kind}_remesh",
            replacements={"/GRSH3N/SH3N/32": {81: [581, 582], 82: [583, 584]}},
            expected_groups={"/GRSH3N/SH3N/32": [581, 582, 583, 584]})
        group = _target_facts(exported)[0]["/GRSH3N/SH3N/32"]
        snapshot = exported._mesh_edit_snapshot()
        by_id = {cell.ref.local_id: cell for cell in snapshot.cells}
        areas = []
        for native_id in group:
            a, b, c = (snapshot._nodes[node].xyz for node in by_id[native_id].nodes)
            areas.append(edits.cross(edits.sub(b, a), edits.sub(c, a))[2] / 2)
        assert areas == [25.0] * 4
        assert sum(areas) == 100.0


@pytest.mark.parametrize("operation", ("element_create", "quad_split", "tri_combine"))
def test_d23_prepared_topology_edit_roundtrip(tmp_path, operation):
    starter = _build_deck_multi_include(tmp_path)
    nodes = tmp_path / "nodes.inc"
    coords = {41: (30, 0, 10), 42: (40, 0, 10), 43: (40, 10, 10), 44: (30, 10, 10),
              45: (50, 0, 10), 46: (60, 0, 10), 47: (50, 10, 10)}
    with nodes.open("ab") as stream:
        stream.write("".join(_node_line(nid, *xyz) + "\n" for nid, xyz in coords.items()).encode("ascii"))
    starter.write_bytes(starter.read_bytes().replace(b"/BCS/20", b"/GRSHEL/SHEL/15\nRetained quad\n       203\n"
        b"/GRSH3N/SH3N/16\nRetained triangle\n       202\n/BCS/20"))

    quad = {("shells_b.inc", "SHELL", 201): ((15, 16, 17, 18), None, 2, None)}
    split = {("shells_b.inc", "SH3N", 204): ((15, 16, 17), None, 2, None),
             ("shells_b.inc", "SH3N", 205): ((15, 17, 18), None, 2, None)}
    created = {("shells_b.inc", "SH3N", 206): ((45, 46, 47), None, 2, None)}
    before, after = {"element_create": (quad, quad | created), "quad_split": (quad, split),
                     "tri_combine": (split, quad)}[operation]

    def write_geometry(path, edited):
        quads = [key for key in edited if key[1] == "SHELL"]
        triangles = [key for key in edited if key[1] == "SH3N"]
        return _write(path, "\n".join([
            "/SHELL/2", _quad_line(203, 41, 42, 43, 44), *(_quad_line(key[2], *edited[key][0]) for key in quads),
            "/SH3N/2", _tri_line(202, 11, 12, 14), *(_tri_line(key[2], *edited[key][0]) for key in triangles), ""]))

    original = write_geometry(tmp_path / "shells_b.inc", before)
    prepared = write_geometry(tmp_path / "prepared.inc", after)
    session = PrepSession()
    session.open_rad(starter)
    points, old_cells = _mesh_facts(session)
    assert {key: old_cells[key] for key in before} == before
    expected = {key: cell for key, cell in old_cells.items() if key not in before} | after
    plan = session.plan_mesh_replacement(_cell_ref(session, 203)["resource_id"], prepared)
    session.replace_prepared_mesh(plan["plan_id"])
    assert _mesh_facts(session) == (points, expected)
    session.undo()
    assert _mesh_facts(session) == (points, old_cells)
    session.redo()
    exported = _roundtrip_save_reconnect_and_export(session, tmp_path, operation)
    assert _mesh_facts(exported) == (points, expected)
    groups, conditions = _target_facts(exported)
    assert (groups["/GRSHEL/SHEL/15"], groups["/GRSH3N/SH3N/16"], groups["/SURF/PART/14"]) == ([203], [202], [2])
    assert conditions["/INTER/TYPE7/23"]["main_surface_id"] == "/SURF/PART/14"
    assert conditions["/CLOAD/21"]["group_id"] == "/GRNOD/NODE/11"
    assert groups["/GRNOD/NODE/11"] == [5, 6, 7]
    assert original.read_bytes() != prepared.read_bytes()


@pytest.mark.parametrize("operation", ("split", "flip", "delete"))
@pytest.mark.parametrize("two_line", (False, True))
def test_d23_root_mesh_cards_preserve_trailing_include_and_comments(tmp_path, operation, two_line):
    starter = _build_deck_multi_include(tmp_path)
    nodes = tmp_path / "nodes.inc"
    shells = tmp_path / "shells_a.inc"
    node_block = nodes.read_bytes()
    shell_block, tet = shells.read_bytes().split(b"/TETRA4/3", 1)
    if operation == "delete":
        header, *rows = shell_block.splitlines(keepends=True)
        shell_block = header + rows[-1]
        tet = b"".join([header, *rows[:-1], b"/TETRA4/3", tet])
    else:
        tet = b"/TETRA4/3" + tet
    nodes.write_bytes(b"# Included node notes\n")
    shells.write_bytes(tet)
    nodes_include = b'#include\n"nodes.inc"\n' if two_line else b"#include nodes.inc\n"
    shells_include = b"#include\n\n# shell filename\nshells_a.inc\n" if two_line else b"#include shells_a.inc\n"
    directive = b"# trailing root shell comment\n" + shells_include
    base = starter.read_bytes().replace(b"#include nodes.inc\n#include shells_a.inc\n",
        node_block + nodes_include + shell_block + directive)
    starter.write_bytes(base)
    session = PrepSession()
    session.open_rad(starter)
    if operation == "split":
        plan = session.plan_triangle_edge_split([_cell_ref(session, 101), _cell_ref(session, 102)],
                                               (_node_ref(session, 1), _node_ref(session, 3)))
        session.apply_triangle_edge_split(plan["plan_id"])
        assert _node_ref(session, plan["added_nodes"][0]["ref"]["local_id"])["resource_id"] == session._root_id
    elif operation == "flip":
        plan = session.plan_shell_normal_flip([_cell_ref(session, 101)])
        session.apply_shell_normal_flip(plan["plan_id"])
        assert next(cell["nodes"] for cell in session.mesh_view()["cells"] if cell["id"] == 101) == (1, 3, 2)
    else:
        plan = session.plan_element_deletion([_cell_ref(session, 104)], orphan_policy="keep")
        session.apply_element_deletion(plan["plan_id"])
        assert not any(cell["id"] == 104 for cell in session.mesh_view()["cells"])
        assert not any(card.keyword == "/SH3N/1" for card in session._model_resource(None).cards)
    rendered = session._model_resource(None).render()
    assert rendered.count(directive) == 1
    assert rendered.count(nodes_include) == 1
    session.undo()
    assert session._model_resource(None).render() == base
    session.redo()
    expected = {"/GRSH3N/SH3N/13": [302, 303, 304, 305]} if operation == "split" else {}
    _roundtrip_save_reconnect_and_export(session, tmp_path, f"root_{operation}", expected_groups=expected)
    exported = tmp_path / f"export_root_{operation}" / f"root_{operation}_0000.rad"
    assert exported.read_bytes().count(directive) == 1
    assert starter.read_bytes() == base


@pytest.mark.parametrize("operation", ("split", "flip"))
@pytest.mark.parametrize("two_line", (False, True))
def test_d23_trailing_nested_includes_remain_file_owned_after_mesh_edit(tmp_path, operation, two_line):
    starter = _build_deck_multi_include(tmp_path)
    nodes = tmp_path / "nodes.inc"
    shells = tmp_path / "shells_a.inc"
    shell_block, tet = shells.read_bytes().split(b"/TETRA4/3", 1)
    node_directive = b'#include\n"node-notes.inc"\n' if two_line else b"#include node-notes.inc\n"
    tet_directive = b"#include\ntets.inc\n" if two_line else b"#include tets.inc\n"
    nested = tmp_path / "mesh" / "shells_a.inc"
    original = nodes.read_bytes() + node_directive + shell_block + tet_directive
    _write(nested, original.decode("ascii"))
    _write(nested.with_name("node-notes.inc"), "# Nested nodes source\n")
    _write(nested.with_name("tets.inc"), (b"/TETRA4/3" + tet).decode("ascii"))
    starter.write_bytes(starter.read_bytes().replace(b"#include nodes.inc\n#include shells_a.inc\n", b"#include mesh/shells_a.inc\n"))
    session = PrepSession()
    session.open_rad(starter)
    assert not session.mesh_view()["diagnostics"]
    owner = session._model_resource(_cell_ref(session, 101)["resource_id"])
    if operation == "split":
        plan = session.plan_triangle_edge_split([_cell_ref(session, 101), _cell_ref(session, 102)],
                                               (_node_ref(session, 1), _node_ref(session, 3)))
        session.apply_triangle_edge_split(plan["plan_id"])
        expected = {"/GRSH3N/SH3N/13": [302, 303, 304, 305]}
        assert _node_ref(session, plan["added_nodes"][0]["ref"]["local_id"])["resource_id"] == owner.id
    else:
        plan = session.plan_shell_normal_flip([_cell_ref(session, 101)])
        session.apply_shell_normal_flip(plan["plan_id"])
        expected = {}
    rendered = owner.render()
    assert rendered.count(node_directive) == rendered.count(tet_directive) == 1
    assert rendered.index(node_directive) < rendered.index(b"/SH3N/1") < rendered.index(tet_directive)
    tag = f"nested_{operation}"
    _roundtrip_save_reconnect_and_export(session, tmp_path, tag, expected_groups=expected)
    assert (tmp_path / f"export_{tag}" / "mesh" / nested.name).read_bytes() == rendered
    assert nested.read_bytes() == original


@pytest.mark.parametrize("origin", ("source", "reassigned", "removed_comment"))
def test_d23_delete_preserves_current_comments_after_replacement_and_reopen(tmp_path, origin):
    starter = _build_deck_multi_include(tmp_path)
    raw = starter.read_bytes()
    # This fixture deletes the only element supporting the secondary contact node.
    start = raw.index(b"/INTER/TYPE7/23\n")
    stop = raw.index(b"#include nodes.inc\n", start)
    starter.write_bytes(raw[:start] + raw[stop:])
    source_path = tmp_path / "shells_b.inc"
    original = source_path.read_bytes()
    if origin != "reassigned":
        original += b"# original flag\n"
        source_path.write_bytes(original)
    session = PrepSession()
    session.open_rad(starter)
    owner_id = _cell_ref(session, 202)["resource_id"]
    if origin == "reassigned":
        part = _card_by_prefix(session, "/PART/4")
        target = {"resource_id": part["resource_id"], "entity_kind": "part", "local_id": part["id"]}
        plan = session.plan_part_reassignment([{"element": _cell_ref(session, 202),
                                               "part": target}])
        session.apply_part_reassignment(plan["plan_id"])
        _reconnect_stale(session, {})
    owner = session._model_resource(owner_id)
    updated = b"" if origin == "removed_comment" else b"# updated flag\n"
    replacement = (owner.render() + updated if origin == "reassigned"
                   else owner.render().replace(b"# original flag\n", updated))
    prepared = tmp_path / "prepared.inc"
    prepared.write_bytes(replacement)
    plan = session.plan_mesh_replacement(owner_id, prepared)
    session.replace_prepared_mesh(plan["plan_id"])
    _reconnect_stale(session, {})
    assert session._model_resource(owner_id).render() == replacement
    plan = session.plan_element_deletion([_cell_ref(session, 202)], orphan_policy="keep")
    session.apply_element_deletion(plan["plan_id"])
    session.undo()
    assert session._model_resource(owner_id).render() == replacement
    session.redo()
    project = tmp_path / "deleted.caeprep"
    session.save_project(project)
    reopened = PrepSession()
    reopened.open_project(project)
    _reconnect_stale(reopened, {})
    out = tmp_path / "export" / "model_0000.rad"
    reopened.export_rad(out)
    rendered = out.with_name(source_path.name).read_bytes()
    assert b"# original flag" not in rendered
    assert rendered.count(b"# updated flag\n") == bool(updated)
    assert rendered == reopened._model_resource(owner_id).render()
    assert source_path.read_bytes() == original


@pytest.mark.parametrize("family", ("SHELL", "BRICK"))
def test_d25_unselected_quad_or_solid_face_diagonal_blocks_split(tmp_path, family):
    starter = _build_deck_multi_include(tmp_path)
    if family == "SHELL":
        neighbor = "/SHELL/2\n" + _quad_line(302, 1, 4, 3, 2) + "\n"
    else:
        with (tmp_path / "nodes.inc").open("ab") as stream:
            stream.write("".join(_node_line(nid, x, y, 5) + "\n" for nid, (x, y) in
                enumerate(((0, 0), (10, 0), (10, 10), (0, 10)), start=30)).encode("ascii"))
        neighbor = "/BRICK/3\n" + "".join(f"{i:10d}" for i in (302, 1, 2, 3, 4, 30, 31, 32, 33)) + "\n"
    with (tmp_path / "shells_a.inc").open("ab") as stream:
        stream.write(neighbor.encode("ascii"))
    session = PrepSession()
    session.open_rad(starter)
    with pytest.raises(PrepError) as error:
        session.plan_triangle_edge_split([_cell_ref(session, 101), _cell_ref(session, 102)],
                                         (_node_ref(session, 1), _node_ref(session, 3)))
    assert error.value.code == "EDGE_HAS_UNSELECTED_NEIGHBORS" and not session.document.dirty


def test_d23_detached_root_comment_stays_out_of_later_neighbor_edit():
    first = "/SH3N/1\n" + _tri_line(1, 1, 2, 3) + "\n"
    second = "/SH3N/2\n" + _tri_line(2, 1, 2, 3) + "\n"
    comment = "# Retain this source comment\n"
    raw = (first + second + comment + "/END\n").encode("ascii")
    resource = DeckResource(raw)
    neighbor, removed = resource.cards[:2]
    resource.restore(resource.deleted_state(removed.id))
    neighbor = resource.card(neighbor.id)
    text = "".join(resource.lines[neighbor.start:neighbor.stop])
    assert text == first
    changed = text.replace(_tri_line(1, 1, 2, 3), _tri_line(1, 1, 3, 2))
    resource.restore(resource.replaced_state(neighbor.id, changed))
    reopened = DeckResource(raw, resource_id=resource.id)
    reopened.restore(resource.snapshot())
    assert reopened.render() == (changed + comment + "/END\n").encode("ascii")


def test_d23_edge_case_include_without_trailing_newline_and_emptied_block_comment(tmp_path: Path):
    """Regression test for D23 native_mesh_edit fixes on EOF blocks lacking trailing newline."""
    _write(
        tmp_path / "nodes_eof.inc",
        "/NODE\n"
        + _node_line(1, 0, 0, 0) + "\n"
        + _node_line(2, 10, 0, 0) + "\n"
        + _node_line(3, 10, 10, 0) + "\n"
        + _node_line(4, 0, 10, 0)  # Intentionally omit trailing EOF newline
    )
    _write(
        tmp_path / "elems_eof.inc",
        "/SH3N/1\n"
        + _tri_line(50, 1, 2, 3) + "\n"
        + "# trailing comment at EOF without newline"
    )
    starter = _write(
        tmp_path / "eof_0000.rad",
        "\n".join(
            [
                "#RADIOSS STARTER",
                "/BEGIN",
                "EOF newline test",
                "      2024         0",
                "                  Mg                  mm                   s",
                "                  Mg                  mm                   s",
                "/MAT/LAW1/1",
                "Steel",
                "            7.85e-09",
                "              210000                 0.3",
                "/PROP/SHELL/1",
                "Shell",
                "        24         1         2         2                                       1",
                "                   0                   0                   0                   0               0.015",
                "         0                             2            0.833333                   2         0",
                "/PART/1",
                "Part 1",
                "         1         1         0",
                "/PART/2",
                "Part 2",
                "         1         1         0",
                "#include nodes_eof.inc",
                "#include elems_eof.inc",
                "/END",
                "",
            ]
        ),
    )
    s = PrepSession()
    s.open_rad(str(starter))
    elem_resource = s.document.resources[_cell_ref(s, 50)["resource_id"]]
    delete = s.plan_element_deletion([_cell_ref(s, 50)], orphan_policy="keep")
    s.apply_element_deletion(delete["plan_id"])
    assert elem_resource.render() == b"# trailing comment at EOF without newline\n"
    s.undo()
    assert elem_resource.render() == (tmp_path / "elems_eof.inc").read_bytes()
    p2 = _card_by_prefix(s, "/PART/2")
    plan = s.plan_part_reassignment([{"element": _cell_ref(s, 50), "part": {"resource_id": s._root_id, "entity_kind": "part", "local_id": p2["id"]}}])
    s.apply_part_reassignment(plan["plan_id"], expected_revision=s.document.revision, expected_document_id=s.document.id)
    assert next(c["part_id"] for c in s.mesh_view()["cells"] if c["id"] == 50) == 2
    assert elem_resource.render().count(b"# trailing comment at EOF without newline\n") == 1
    assert b"/SH3N/1" not in elem_resource.render()

    # Appending the midpoint also normalizes the unterminated NODE row.
    sp = s.plan_triangle_edge_split([_cell_ref(s, 50)], (_node_ref(s, 1), _node_ref(s, 2)))
    s.apply_triangle_edge_split(sp["plan_id"], expected_revision=s.document.revision, expected_document_id=s.document.id)
    assert len(s.mesh_view()["node_ids"]) == 5
    assert len(s.mesh_view()["cells"]) == 2


def test_d25_pure_split_triangle_edge_candidate_unit_and_rejections(tmp_path: Path):
    """D25 pure MeshEditCandidate tests: 1-tri split, 2-tri shared edge split, IDs, normals, rejections."""
    starter = _build_deck_multi_include(tmp_path)
    s = PrepSession()
    s.open_rad(str(starter))
    snapshot = s._mesh_edit_snapshot()

    e101 = edits.Ref(**_cell_ref(s, 101))
    e102 = edits.Ref(**_cell_ref(s, 102))
    e201 = edits.Ref(**_cell_ref(s, 201))  # SHELL quad
    n1 = edits.Ref(**_node_ref(s, 1))
    n2 = edits.Ref(**_node_ref(s, 2))
    n3 = edits.Ref(**_node_ref(s, 3))
    n4 = edits.Ref(**_node_ref(s, 4))

    # 1. Split 2 incident SH3N triangles sharing diagonal edge (n1, n3)
    cand2 = edits.split_triangle_edge(snapshot, (e101, e102), (n1, n3))
    assert len(cand2.added_nodes) == 1
    assert len(cand2.added_cells) == 4
    assert cand2.added_nodes[0].xyz == (5.0, 5.0, 0.0)
    assert cand2.added_nodes[0].ref.local_id not in {n.ref.local_id for n in snapshot.nodes}
    assert {c.ref.local_id for c in cand2.added_cells}.isdisjoint({c.ref.local_id for c in snapshot.cells})
    all_cells = list(cand2.iter_cells())
    assert len(all_cells) == len(snapshot.cells) + 2
    assert len(list(cand2.iter_nodes())) == len(snapshot.nodes) + 1
    for q in cand2.quality_after:
        assert q.metric == "triangle_mean_ratio" and q.value > 0.1 and not q.problems
    # Normal direction preserved (+Z) for all 4 children
    nodes_after = {n.ref: n.xyz for n in cand2.iter_nodes()}
    for c in cand2.added_cells:
        p0, p1, p2 = (nodes_after[r] for r in c.nodes)
        area_vec = edits.cross(edits.sub(p1, p0), edits.sub(p2, p0))
        assert area_vec[2] > 0.0
        assert c.part == snapshot._cells[e101].part

    # 2. Split a boundary edge with caller-supplied IDs.
    cand1 = edits.split_triangle_edge(snapshot, (e102,), (n3, n4), new_node_id=990, new_element_ids=(9001, 9002))
    assert cand1.added_nodes[0].ref.local_id == 990
    assert tuple(c.ref.local_id for c in cand1.added_cells) == (9001, 9002)
    assert cand1.added_nodes[0].xyz == (5.0, 10.0, 0.0)

    # 3. Structured MeshEditError rejections
    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(snapshot, (e201,), (edits.Ref(**_node_ref(s, 11)), edits.Ref(**_node_ref(s, 12))))
    assert err.value.code == "not_sh3n"

    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(snapshot, (e101,), (n1, n4))  # n4 not in e101
    assert err.value.code == "non_incident_edge"

    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(snapshot, (e101,), (n1, n1))
    assert err.value.code == "duplicate_edge_nodes"

    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(snapshot, (e102,), (n3, n4), new_node_id=1)
    assert err.value.code == "node_id_collision"

    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(snapshot, (e102,), (n3, n4), new_element_ids=(101, 999))
    assert err.value.code == "element_id_collision"

    for edge, neighbor in (((n1, n3), e102), ((n1, n2), edits.Ref(**_cell_ref(s, 301)))):
        with pytest.raises(edits.MeshEditError) as err:
            edits.split_triangle_edge(snapshot, (e101,), edge)
        assert err.value.code == "EDGE_HAS_UNSELECTED_NEIGHBORS"
        assert err.value.details == (neighbor,)

    for identifiers in ({"new_node_id": 2**31}, {"new_element_ids": (9001, 2**31)}):
        with pytest.raises(edits.MeshEditError) as err:
            edits.split_triangle_edge(snapshot, (e102,), (n3, n4), **identifiers)
        assert err.value.code == "native_id_overflow"
    max_id = 2**31 - 1
    boundary = edits.split_triangle_edge(snapshot, (e102,), (n3, n4), new_node_id=max_id, new_element_ids=(max_id - 1, max_id))
    assert boundary.added_nodes[0].ref.local_id == boundary.added_cells[-1].ref.local_id == max_id

    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(snapshot, (e101, e102, edits.Ref(**_cell_ref(s, 103))), (n1, n3))
    assert err.value.code == "invalid_edge_split_selection"

    # Degenerate zero-area triangle rejection
    deg_dir = tmp_path / "degenerate_tri"
    _write(
        deg_dir / "deg_0000.rad",
        "\n".join(
            [
                "#RADIOSS STARTER",
                "/BEGIN",
                "Degenerate tri",
                "      2024         0",
                "                  Mg                  mm                   s",
                "                  Mg                  mm                   s",
                "/MAT/LAW1/1",
                "Steel",
                "            7.85e-09",
                "              210000                 0.3",
                "/PROP/SHELL/1",
                "Shell",
                "        24         1         2         2                                       1",
                "                   0                   0                   0                   0               0.015",
                "         0                             2            0.833333                   2         0",
                "/PART/1",
                "Plate",
                "         1         1         0",
                "/NODE",
                _node_line(1, 0, 0, 0),
                _node_line(2, 5, 0, 0),
                _node_line(3, 10, 0, 0),  # Collinear -> zero area
                "/SH3N/1",
                _tri_line(1, 1, 2, 3),
                "/END",
                "",
            ]
        ),
    )
    sd = PrepSession()
    sd.open_rad(str(deg_dir / "deg_0000.rad"))
    dsnap = sd._mesh_edit_snapshot()
    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(dsnap, (edits.Ref(**_cell_ref(sd, 1)),), (edits.Ref(**_node_ref(sd, 1)), edits.Ref(**_node_ref(sd, 2))))
    assert err.value.code == "degenerate_triangle"


@pytest.mark.parametrize(("unit", "side"), [("mm", 1e-3), ("m", 1e-6)])
def test_d25_micrometre_triangle_and_automatic_id_bounds(tmp_path, unit, side):
    s = PrepSession()
    s.open_rad(_build_deck_multi_include(tmp_path))
    snapshot = s._mesh_edit_snapshot()
    parent = snapshot._cells[edits.Ref(**_cell_ref(s, 101))]
    largest_id = 2**31 - 1
    nodes = tuple(edits.Node(ref, xyz) for ref, xyz in zip(parent.nodes, ((0, 0, 0), (side, 0, 0), (0, side, 0))))
    last_node = edits.Node(replace(parent.nodes[0], local_id=largest_id), (0, 0, side))
    parent = replace(parent, ref=replace(parent.ref, local_id=largest_id))
    snapshot = replace(snapshot, length_unit=unit, nodes=(*nodes, last_node), cells=(parent,), sets=(), uses=())

    candidate = edits.split_triangle_edge(snapshot, (parent.ref,), parent.nodes[:2])
    assert candidate.added_nodes[0].xyz == (side / 2, 0, 0)
    assert candidate.added_nodes[0].ref.local_id == 4
    assert tuple(cell.ref.local_id for cell in candidate.added_cells) == (1, 2)
    assert candidate.quality_before[0].value == pytest.approx(3**0.5 / 2)
    assert sum(row.signed_measure for row in candidate.quality_after) / side**2 == pytest.approx(0.5)


def test_d25_session_multiresource_edge_split_undo_save_reconnect_export(tmp_path: Path):
    """End-to-end session test for EdgeSplitCommands on multi-include deck."""
    starter = _build_deck_multi_include(tmp_path)
    s = PrepSession()
    s.open_rad(str(starter))
    rev0 = s.document.revision
    n_before = len(s.mesh_view()["node_ids"])
    c_before = len(s.mesh_view()["cells"])

    # Cancel test first
    plan = s.plan_triangle_edge_split([_cell_ref(s, 101), _cell_ref(s, 102)], (_node_ref(s, 1), _node_ref(s, 3)))
    assert len(plan["added_nodes"]) == 1
    assert len(plan["added_cells"]) == 4
    assert plan["admissible"] is True
    assert plan["stale_targets"]
    assert s.document.revision == rev0
    s.cancel_triangle_edge_split(plan["plan_id"])
    with pytest.raises(PrepError) as stale_apply:
        s.apply_triangle_edge_split(plan["plan_id"], expected_revision=rev0, expected_document_id=s.document.id)
    assert stale_apply.value.code == "stale_mesh_candidate"

    # Re-plan and apply in 1 atomic transaction
    plan = s.plan_triangle_edge_split([_cell_ref(s, 101), _cell_ref(s, 102)], (_node_ref(s, 1), _node_ref(s, 3)))
    new_node_id = plan["added_nodes"][0]["ref"]["local_id"]
    child_mapping = {pair["parent"]["local_id"]: pair["children"] for pair in plan["split_cells"]}
    child_ids = [ref["local_id"] for refs in child_mapping.values() for ref in refs]
    s.select_entity("element", 101)
    selection_events = []
    unsubscribe = s.subscribe(lambda _: selection_events.append(s.selection()["ids"]))
    res = s.apply_triangle_edge_split(plan["plan_id"], expected_revision=rev0, expected_document_id=s.document.id)
    unsubscribe()
    assert s.selection()["refs"] == child_mapping[101]
    assert all(101 not in ids for ids in selection_events)
    assert res["revision"] == rev0 + 1
    assert len(s.mesh_view()["node_ids"]) == n_before + 1
    assert new_node_id in s.mesh_view()["node_ids"]
    assert len(s.mesh_view()["cells"]) == c_before + 2  # 2 parents removed, 4 children added

    # Midpoint node was written to nodes.inc, child SH3N written to shells_a.inc
    nodes_inc_id = next(rid for rid, p in s._paths.items() if p.endswith("nodes.inc"))
    shells_a_id = next(rid for rid, p in s._paths.items() if p.endswith("shells_a.inc"))
    assert str(new_node_id) in s.document.resources[nodes_inc_id].render().decode("latin1")
    shells_a_lines = s.document.resources[shells_a_id].render().decode("latin1").splitlines(keepends=True)
    for parent, ending in ((101, "\r\n"), (102, "\n")):
        for child in child_mapping[parent]:
            row = next(line for line in shells_a_lines if line[:10].strip() == str(child["local_id"]))
            angle, thickness = _SH3N_ANGLE_THICKNESS[parent]
            assert row[40:60] == " " * 20
            assert row[60:80] == f"{angle:>20g}"
            assert row[80:100] == f"{thickness:>20g}"
            assert row[100:] == _SH3N_TRAILING[parent] + ending

    # 1 Undo restores both includes + relations atomically; 1 Redo restores split
    s.undo()
    assert not s.selection()["refs"]
    assert len(s.mesh_view()["node_ids"]) == n_before
    assert len(s.mesh_view()["cells"]) == c_before
    s.redo()
    assert len(s.mesh_view()["node_ids"]) == n_before + 1
    assert len(s.mesh_view()["cells"]) == c_before + 2

    group_id = _find_card_id(s, "/GRSH3N/SH3N/13")
    generation = s.mesh_relationships()["stale_targets"][group_id]["mesh_revision"]
    for invalid in ([], [child_mapping[101][0]] * 2, [child_mapping[101][0], _cell_ref(s, 201)]):
        with pytest.raises(PrepError):
            s.reconnect_mesh_targets({group_id: {"mesh_revision": generation, "mapping": {**child_mapping, 101: invalid}}})
        assert group_id in s.mesh_relationships()["stale_targets"]
    stored = s.mesh_relationships()["stale_targets"][group_id]["parent_to_children"]
    assert stored == {101: [302, 303], 102: [304, 305]}
    for mapping in ({101: 103, 102: 104}, {101: [103], 102: [104]}, {101: [304], 102: [302]},
                    {101: 302, 102: child_mapping[102]}):
        with pytest.raises(PrepError) as invalid_integer:
            s.reconnect_mesh_targets({group_id: {"mesh_revision": generation, "mapping": mapping}})
        assert invalid_integer.value.code == "invalid_reference"
    ref = child_mapping[102][0]
    alternate = {"resource_id": ref["resource_id"], "object_type": "element", "id": ref["local_id"]}
    mixed_refs = {101: [SelectionRef(**child_mapping[101][0]), 303], 102: (alternate, child_mapping[102][1])}
    link = s._prepare_mesh_reconnection({group_id: {"mesh_revision": generation, "mapping": mixed_refs}})[-1][0]
    assert link["mapping"] == [{"old_native_id": eid, "target": children} for eid, children in child_mapping.items()]

    exported = _roundtrip_save_reconnect_and_export(s, tmp_path, "d25_split", expected_groups={"/GRSH3N/SH3N/13": [302, 303, 304, 305]})
    assert _target_facts(exported)[0]["/GRSH3N/SH3N/13"] == child_ids
    exported_snapshot = exported._mesh_edit_snapshot()
    areas = [edits._quality(cell, exported_snapshot._nodes.__getitem__).signed_measure
             for cell in exported_snapshot.cells if cell.ref.local_id in child_ids]
    assert areas == pytest.approx([25, 25, 25, 25])
    assert sum(areas) == pytest.approx(sum(row["signed_measure"] for row in plan["quality_before"]))
    assert _mesh_facts(exported)[0][new_node_id] == ((5, 5, 0), ("nodes.inc",))

    # Reject /TRANSFORM deck
    tr_dir = tmp_path / "tr_deck"
    _write(
        tr_dir / "tr_0000.rad",
        starter.read_text(encoding="latin1").replace("/END", "/TRANSFORM/ROT/1\nRot\n         0                   0                   0                   0                   0\n/END"),
    )
    for fn in ("nodes.inc", "shells_a.inc", "shells_b.inc"):
        shutil.copy2(tmp_path / fn, tr_dir / fn)
    st = PrepSession()
    st.open_rad(str(tr_dir / "tr_0000.rad"))
    with pytest.raises(PrepError) as tr_err:
        st.plan_triangle_edge_split([_cell_ref(st, 101)], (_node_ref(st, 1), _node_ref(st, 2)))
    assert tr_err.value.code == "unsupported_transform"


@pytest.mark.parametrize("presentation", ("beidprep", "prepomax"))
def test_d25_triangle_edge_split_dialog_ui_and_screenshot(tmp_path: Path, presentation: str, request):
    pytest.importorskip("PySide6")
    request.getfixturevalue("qt_settings")
    from PySide6.QtWidgets import QApplication, QComboBox
    from caelab_prep.ui.main_window import MainWindow
    from caelab_prep.ui.element_edits import TriangleEdgeSplitDialog

    app = QApplication.instance() or QApplication([])
    starter = _build_deck_multi_include(tmp_path / presentation)
    win = MainWindow(enable_viewport=False, presentation=presentation)
    try:
        win.resize(1440, 900)
        win.session.open_rad(str(starter))
        win.refresh_document()
        app.processEvents()

        win.session.select_entity("element", 101)
        app.processEvents()

        assert hasattr(win, "edge_split_action") and win.edge_split_action.isEnabled()
        assert win.actions.action("mesh.split_triangle_edge") is win.edge_split_action
        assert win.edge_split_action in win.command_menus["Mesh"].actions()
        assert win.edge_split_action.statusTip()
        assert not win.edge_split_action.icon().isNull()
        win.edge_split_action.trigger()
        dialog = win.edge_split_dialog
        assert isinstance(dialog, TriangleEdgeSplitDialog)
        assert dialog.objectName() == "triangleEdgeSplitDialog"
        assert dialog.windowTitle() == "Split triangle edge"
        assert dialog.edge_selector.sizeAdjustPolicy() == QComboBox.SizeAdjustPolicy.AdjustToContents
        assert len(dialog._references) == 1
        assert dialog.edge_selector.count() == 3

        win.session.select_entity("element", 102)
        dialog.use_selection()
        app.processEvents()
        assert len(dialog._references) == 2
        assert dialog.edge_selector.count() == 1  # Shared edge 1 - 3
        assert dialog.edge_selector.currentData() is not None

        dialog.prepare_preview()
        assert dialog._plan is not None
        assert dialog._plan["admissible"] is True
        assert not dialog.reviewed.isChecked()
        assert not dialog.apply_button.isEnabled()
        dialog.reviewed.click()
        assert dialog.apply_button.isEnabled()
        dialog.prepare_preview()
        assert not dialog.reviewed.isChecked()
        assert not dialog.apply_button.isEnabled()
        dialog.reviewed.setChecked(True)
        assert dialog.apply_button.isEnabled()
        review = dialog.preview.toPlainText()
        assert "Split edge 1 – 3" in review
        assert "New midpoint node (mm)" in review
        assert "Stored thickness, shell angle and trailing fields are copied." in review
        assert "Triangle mean ratio and area (mm^2)" in review
        assert "Split Target Group [/GRSH3N/SH3N/13]" in review
        assert "triangle_mean_ratio" not in review
        child_ids = [[child["local_id"] for child in pair["children"]] for pair in dialog._plan["split_cells"]]

        if presentation == "beidprep":
            win.show()
            app.processEvents()
            for card_id in dialog._plan["stale_targets"]:
                keyword = win.session._find_card(card_id).card(card_id).keyword
                cursor = dialog.preview.document().find(keyword)
                assert not cursor.isNull()
                assert dialog.preview.viewport().rect().contains(dialog.preview.cursorRect(cursor))
            pixmap = dialog.grab()
            assert not pixmap.isNull()
            assert pixmap.save(str(tmp_path / "d25_prep_edge_split_dialog.png"))

        before_nodes = len(win.session.mesh_view()["node_ids"])
        dialog.apply_change()
        app.processEvents()
        assert len(win.session.mesh_view()["node_ids"]) == before_nodes + 1
        win.session.undo()
        app.processEvents()
        assert len(win.session.mesh_view()["node_ids"]) == before_nodes
        dialog.reject()
        win.session.redo()
        app.processEvents()

        reconnect = win.open_prepared_mesh()
        group_id = _find_card_id(win.session, "/GRSH3N/SH3N/13")
        reconnect.target_group.setCurrentIndex(reconnect.target_group.findData(group_id))
        for row, ids in enumerate(child_ids):
            reconnect.reconnect_table.selectRow(row)
            reconnect.current_target.setText(", ".join(map(str, ids)))
            reconnect.find_current_target()
            reconnect.add_link()
        assert not reconnect.reconnect_button.isEnabled()
        assert reconnect.prepare_reconnection()
        assert "2 old links → 4 unique current targets" in reconnect.reconnect_details.toPlainText()
        assert reconnect.apply_reconnection()
        assert _target_facts(win.session)[0]["/GRSH3N/SH3N/13"] == [child for ids in child_ids for child in ids]
    finally:
        win._allow_close = True
        win.close()
        app.processEvents()


def test_d25_dirty_close_cancel_keeps_dialog_and_preview(tmp_path, request):
    pytest.importorskip("PySide6")
    request.getfixturevalue("qt_settings")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from caelab_prep.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow(enable_viewport=False)
    timer = QTimer()
    try:
        win.session.open_rad(_build_deck_multi_include(tmp_path))
        win.session.set_field(_find_card_id(win.session, "/MAT/LAW1/1"), "young_modulus", 220000)
        assert win.session.document.dirty
        win.refresh_document()
        win.show()
        app.processEvents()

        win.session.select_entity("element", 102)
        dialog = win.open_edge_split()
        win.session.select_entity("element", 201)
        dialog.use_selection()
        assert dialog.status.text() == dialog.edge_selector.currentText() == dialog.no_common_edge
        dialog.table.selectRow(1)
        dialog.remove_selection()
        dialog.table.selectRow(0)
        dialog.remove_selection()
        assert dialog.status.text() == dialog.edge_selector.currentText() == dialog.selection_required

        win.session.select_entity("element", 101)
        dialog.use_selection()
        win.session.select_entity("element", 102)
        dialog.use_selection()
        dialog.prepare_preview()
        plan = dialog._plan
        review = dialog.preview.toPlainText()
        assert plan and not dialog.apply_button.isEnabled()
        dialog.reviewed.click()
        assert dialog.apply_button.isEnabled()

        prompts = []

        def cancel():
            prompt = QApplication.activeModalWidget()
            if isinstance(prompt, QMessageBox):
                prompts.append((prompt.windowTitle(), prompt.text()))
                prompt.done(int(QMessageBox.StandardButton.Cancel))
                timer.stop()

        timer.timeout.connect(cancel)
        timer.start(10)
        assert not win.close()
        app.processEvents()
        assert prompts == [("Unsaved changes", "Save changes before continuing?")]
        assert win.isVisible()
        assert win.edge_split_dialog is dialog and dialog.isVisible()
        assert dialog._plan is plan and dialog.preview.toPlainText() == review
        assert dialog.apply_button.isEnabled() and not dialog._closed
    finally:
        timer.stop()
        win._allow_close = True
        win.close()
        app.processEvents()
    assert win.edge_split_dialog is None
