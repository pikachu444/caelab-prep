"""Comprehensive D23 (6 existing mesh edits x 2 multi-resource #include decks) and D25 (split_triangle_edge) tests."""
from __future__ import annotations

from dataclasses import replace
import json
from math import dist
from pathlib import Path
import shutil
from zipfile import ZipFile

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


def _roundtrip_save_reconnect_and_export(session, tmp_path, tag, *, replacements=None, expected_groups=None, expect_stale=True):
    original_groups, original_conditions = _target_facts(session)
    groups_after = {**original_groups, **(expected_groups or {})}
    assert bool(session.mesh_relationships()["stale_targets"]) == expect_stale
    proj_path = tmp_path / f"{tag}.caeprep"
    session.save_project(str(proj_path))

    # Reopen in a completely fresh PrepSession to verify persisted deltas + stale targets
    reopened = PrepSession()
    reopened.open_project(str(proj_path))
    assert reopened.mesh_relationships()["stale_targets"] == session.mesh_relationships()["stale_targets"]
    assert _mesh_facts(reopened) == _mesh_facts(session)
    assert _target_facts(reopened) == _target_facts(session)
    if expect_stale:
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

    # 6. Prepared INCLUDE replacement and size-controlled Gmsh patch adoption.
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
        from caelab_prep.adapters.gmsh_backend import GmshBackend
        from caelab_prep.application.mesh_candidates import read_mesh_candidate

        mat41 = _card_by_prefix(s6, "/MAT/LAW1/41")
        prop21 = _card_by_prefix(s6, "/PROP/SHELL/21")
        plate = (Path(__file__).resolve().parents[1] /
                 "docs/mesher-evidence/2026-11-02/midsurface/results/plate/candidate.brep")
        backend = GmshBackend()
        meshes, max_edges = [], []
        for size in (10.0, 2.5):
            generated = backend.generate(plate, tmp_path / "gmsh_plate", mesh_size=size, dimension=2)
            assert generated["recipe"]["effective_maximum_mesh_size"] == pytest.approx(size)
            mesh = read_mesh_candidate(generated).to_native_mesh(length_unit="mm")
            coordinates = {node.id: node.xyz for node in mesh.nodes}
            assert {cell.kind for cell in mesh.elements} == {"triangle3"}
            max_edges.append(max(dist(coordinates[a], coordinates[b]) for cell in mesh.elements
                                 for a, b in zip(cell.node_ids, cell.node_ids[1:] + cell.node_ids[:1])))
            meshes.append(mesh)
        coarse, fine = meshes
        assert len(fine.nodes) > len(coarse.nodes)
        assert len(fine.elements) > len(coarse.elements)
        assert 0 < max_edges[1] < max_edges[0]

        before_cells = {cell["id"]: cell for cell in s6.mesh_view()["cells"]}
        before_targets = _target_facts(s6)
        adopted = s6.adopt_mesh_candidate(fine, material_id=mat41["id"], property_id=prop21["id"], name="Adopted Plate")
        after_cells = {cell["id"]: cell for cell in s6.mesh_view()["cells"]}
        assert len(after_cells) == len(before_cells) + len(fine.elements)
        assert {identifier: after_cells[identifier] for identifier in before_cells} == before_cells
        for cell in fine.elements:
            native = after_cells[adopted["element_id_map"][cell.id]]
            assert tuple(native["nodes"]) == tuple(adopted["node_id_map"][node] for node in cell.node_ids)
        s6.undo()
        assert {cell["id"]: cell for cell in s6.mesh_view()["cells"]} == before_cells
        s6.redo()
        assert {cell["id"]: cell for cell in s6.mesh_view()["cells"]} == after_cells
        assert _target_facts(s6) == before_targets
        _roundtrip_save_reconnect_and_export(s6, tmp_path, "deck_b_gmsh_adoption", expect_stale=False)

        # Start from the original ID namespace for the independently prepared INCLUDE.
        s6 = PrepSession()
        s6.open_rad(starter)
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


def _nested_include_deck(source, layout, separator, *, filename="nodes.inc", uppercase=False):
    from caelab_prep.radioss.modeling import material_block, shell_block

    sibling = f"mesh/{filename}"
    owner = filename if layout in ("sibling-claimed", "root-shared") else sibling
    xyz = {1: (3, 1, 0), 2: (13, 1, 0), 3: (3, 11, 0)}
    units = f"{'Mg':>20}{'mm':>20}{'s':>20}\n"
    begin = "/BEGIN\nNested source\n      2024         0\n" + units * 2
    header = (begin + material_block(41, "Steel", 7.8e-9, 210000, .3) + shell_block(21, "Shell", 1)
              + f"/PART/9\nPanel\n{21:10}{41:10}{0:10}\n")
    picked = {"sibling-claimed": sibling, "root-claimed": filename}.get(layout)
    root_refs = ["mesh/first.inc"]
    if picked:
        root_refs.append(picked)
    elif layout == "root-shared":
        root_refs.append(filename)
    spell = str.upper if uppercase else str
    starter = _write(source / "nested_0000.rad",
                     header + "".join(f"#include {spell(path)}\n" for path in root_refs) + "/END\n")
    _write(source / "mesh/first.inc",
           f"/SH3N/9\r\n{_tri_line(77, 1, 2, 3)}\r\n#include{separator}\"{spell(filename)}\"\r\n")
    _write(source / owner, "/NODE\n" + "".join(_node_line(node, *point) + "\n" for node, point in xyz.items()))
    expected_points = {node: (point, (owner,)) for node, point in xyz.items()}
    if picked:
        _write(source / picked, f"/NODE\n{_node_line(4, 83, 1, 0)}\n")
        expected_points[4] = ((83, 1, 0), (picked,))
    if layout == "root-directory":
        (source / filename).mkdir(parents=True)
    expected = (expected_points, {("mesh/first.inc", "SH3N", 77): ((1, 2, 3), None, 9, None)})
    return starter, begin, owner, expected


@pytest.mark.parametrize("layout", ("sibling-claimed", "root-claimed", "sibling-only", "root-directory"))
@pytest.mark.parametrize("separator,uppercase", ((" ", False), ("\r\n", True)), ids=("inline", "quoted-two-line-uppercase"))
@pytest.mark.parametrize("filename", ("nodes.inc", "sets/nodes.inc"))
def test_d23_nested_include_lookup_agrees_in_native_and_independent_source(tmp_path, layout, separator, uppercase, filename):
    starter, begin, owner, expected_native = _nested_include_deck(
        tmp_path / "source", layout, separator, filename=filename, uppercase=uppercase)
    native = PrepSession()
    native.open_rad(starter)
    assert _mesh_facts(native) == expected_native
    native_project = tmp_path / "native.caeprep"
    native.save_project(native_project)
    native.open_project(native_project)
    assert _mesh_facts(native) == expected_native
    native_output = tmp_path / "native-export/native_0000.rad"
    native.export_rad(native_output)
    native.open_rad(native_output)
    assert _mesh_facts(native) == expected_native

    destination = PrepSession()
    destination.open_rad(_write(tmp_path / "destination/base_0000.rad", begin + "/END\n"))
    plan = destination.plan_import_source(starter)
    expected_points = expected_native[0]
    assert (plan["node_count"], plan["element_count"], plan["collisions"]) == (len(expected_points), 1, [])
    destination.import_source(plan["plan_id"])
    paths = {item["original_path"]: item["logical_path"] for item in plan["source"]["files"]}
    expected_import = ({node: (point, (paths[path[0]],)) for node, (point, path) in expected_points.items()},
                       {(paths["mesh/first.inc"], "SH3N", 77): ((1, 2, 3), None, 9, paths[starter.name])})
    assert _mesh_facts(destination) == expected_import
    project = tmp_path / "combined.caeprep"
    destination.save_project(project)
    destination.open_project(project)
    output = tmp_path / "export/combined_0000.rad"
    destination.export_rad(output)
    quote = '"' if separator != " " else ''
    assert (output.parent / paths["mesh/first.inc"]).read_bytes().endswith(
        f"#include{separator}{quote}{paths[owner]}{quote}\r\n".encode("ascii"))
    exported = PrepSession()
    exported.open_rad(output)
    assert _mesh_facts(exported) == expected_import


@pytest.mark.parametrize("shadow", ("starter", "engine", "existing-file"))
def test_d23_export_preserves_sibling_binding_when_destination_shadows_it(tmp_path, shadow):
    filename = {"starter": "export_0000.rad", "engine": "export_0001.rad", "existing-file": "nodes.inc"}[shadow]
    starter, _, owner, expected = _nested_include_deck(tmp_path / "source", "sibling-only", "\r\n", filename=filename)
    session = PrepSession()
    session.open_rad(starter)
    assert _mesh_facts(session) == expected
    output = tmp_path / "out/export_0000.rad"
    if shadow == "existing-file":
        unrelated = _write(output.parent / filename, f"/NODE\n{_node_line(88, 83, 0, 0)}\n")
    session.export_solver_inputs(output, end_time=.01, output_interval=.001)
    if shadow == "existing-file":
        assert unrelated.read_bytes() == f"/NODE\n{_node_line(88, 83, 0, 0)}\n".encode("ascii")
    assert (output.parent / "mesh/first.inc").read_bytes().endswith(f'#include\r\n"{owner}"\r\n'.encode("ascii"))
    reopened = PrepSession()
    reopened.open_rad(output)
    assert _mesh_facts(reopened) == expected
    assert not reopened.diagnostics()


@pytest.mark.parametrize("solver_inputs", (False, True), ids=("starter", "solver-inputs"))
@pytest.mark.parametrize("filename", ("nodes.inc", "sets/nodes.inc"))
def test_d23_export_rejects_unrelated_sibling_of_root_bound_include(tmp_path, solver_inputs, filename):
    starter, _, _, expected = _nested_include_deck(tmp_path / "source", "root-shared", "\r\n",
                                                   filename=filename, uppercase=True)
    session = PrepSession()
    session.open_rad(starter)
    assert _mesh_facts(session) == expected
    output = tmp_path / "out/export_0000.rad"
    unrelated = _write(output.parent / "mesh" / filename, f"/NODE\n{_node_line(88, 83, 0, 0)}\n")
    original = unrelated.read_bytes()
    with pytest.raises(PrepError) as error:
        if solver_inputs:
            session.export_solver_inputs(output, end_time=.01, output_interval=.001)
        else:
            session.export_rad(output)
    assert error.value.code == "include_output_collision"
    assert set(path for path in output.parent.rglob("*") if path.is_file()) == {unrelated}
    assert unrelated.read_bytes() == original


@pytest.mark.parametrize("solver_inputs", (False, True), ids=("starter", "solver-inputs"))
def test_d23_export_checks_sibling_of_rewritten_include(tmp_path, solver_inputs):
    filename = "assembly_0000.rad"
    starter, _, _, expected = _nested_include_deck(
        tmp_path / "source", "sibling-only", "\r\n", filename=filename)
    starter.write_bytes(starter.read_bytes().replace(b"/END", f"#include mesh/{filename}\n/END".encode("ascii")))
    session = PrepSession()
    session.open_rad(starter)
    assert _mesh_facts(session) == expected
    output = tmp_path / "out" / filename
    unrelated = _write(output.parent / "mesh/mesh" / filename, f"/NODE\n{_node_line(88, 83, 0, 0)}\n")
    original = unrelated.read_bytes()
    with pytest.raises(PrepError) as error:
        if solver_inputs:
            session.export_solver_inputs(output, end_time=.01, output_interval=.001)
        else:
            session.export_rad(output)
    assert error.value.code == "include_output_collision"
    assert set(path for path in output.parent.rglob("*") if path.is_file()) == {unrelated}
    assert unrelated.read_bytes() == original


@pytest.mark.parametrize("reverse", (False, True))
def test_d23_ambiguous_directives_do_not_claim_root_for_each_other(tmp_path, reverse):
    paths = ("a/first.inc", "b/second.inc")
    directives = "".join(f"#include {path}\n" for path in (reversed(paths) if reverse else paths))
    starter = _write(tmp_path / "source/model_0000.rad", f"/BEGIN\nDeck\n{directives}/END\n")
    source = starter.parent
    _write(source / "nodes.inc", f"/NODE\n{_node_line(1, 1, 0, 0)}\n")
    for index, path in enumerate(paths, 81):
        _write(source / path, '#include\n"nodes.inc"\n')
        _write((source / path).with_name("nodes.inc"), f"/NODE\n{_node_line(index, index, 0, 0)}\n")
    session = PrepSession()
    session.open_rad(starter)
    assert _mesh_facts(session)[0] == {1: ((1, 0, 0), ("nodes.inc",))}
    assert not session.diagnostics()
    project = tmp_path / "ambiguous.caeprep"
    session.save_project(project)
    session.open_project(project)
    assert session.mesh_view()["node_ids"] == (1,)


def test_d23_later_include_wave_sees_new_unambiguous_claims(tmp_path):
    source = tmp_path / "source"
    starter = _write(source / "starter_0000.rad", "/BEGIN\nWaves\n#include a/first.inc\n/END\n")
    _write(source / "a/first.inc", "#include outer.inc\n")
    _write(source / "a/outer.inc", "# unused alternate\n")
    _write(source / "outer.inc", "#include nodes.inc\n#include mesh/first.inc\n")
    _write(source / "mesh/first.inc", "#include nodes.inc\n")
    _write(source / "nodes.inc", f"/NODE\n{_node_line(1, 1, 0, 0)}\n")
    _write(source / "mesh/nodes.inc", f"/NODE\n{_node_line(100, 2, 0, 0)}\n")
    session = PrepSession()
    session.open_rad(starter)
    expected = {1: ((1, 0, 0), ("nodes.inc",)), 100: ((2, 0, 0), ("mesh/nodes.inc",))}
    assert _mesh_facts(session)[0] == expected
    project = tmp_path / "waves.caeprep"
    session.save_project(project)
    session.open_project(project)
    output = tmp_path / "out/export_0000.rad"
    session.export_rad(output)
    session.open_rad(output)
    assert _mesh_facts(session)[0] == expected


@pytest.mark.parametrize("historical", (False, True), ids=("active-native", "ac0-import"))
def test_d23_import_preserves_writer_bindings_when_inventory_loses_a_candidate(tmp_path, historical):
    source = tmp_path / "source"
    units = f"{'Mg':>20}{'mm':>20}{'s':>20}\n"
    begin = "/BEGIN\nActive bindings\n      2025         0\n" + units * 2
    starter = _write(source / "starter_0000.rad", begin + "#include a/first.inc\n#include b/second.inc\n/END\n")
    _write(source / "a/first.inc", "#include nodes.inc\n")
    _write(source / "a/nodes.inc", "# not loaded\n")
    _write(source / "b/second.inc", "#include nodes.inc\n")
    _write(source / "b/extra.inc", "#include nodes.inc\n")
    _write(source / "nodes.inc", f"/NODE\n{_node_line(1, 1, 0, 0)}\n#include b/extra.inc\n")
    _write(source / "b/nodes.inc", f"/NODE\n{_node_line(88, 2, 0, 0)}\n")
    session = PrepSession()
    session.open_rad(_write(tmp_path / "base_0000.rad", begin + "/END\n"))
    plan = session.plan_import_source(starter)
    session.import_source(plan["plan_id"])
    files = {item["original_path"]: item for item in plan["source"]["files"]}
    second = files["b/second.inc"]
    root_nodes, sibling_nodes = (files[path]["logical_path"] for path in ("nodes.inc", "b/nodes.inc"))
    include = f"#include {root_nodes}\n"
    assert session.document.resources[second["resource_id"]].raw == include.encode()
    archive = tmp_path / "import.caeprep"
    session.save_project(archive)
    if historical:
        with ZipFile(archive) as project:
            members = {name: project.read(name) for name in project.namelist()}
        manifest = json.loads(members["manifest.json"])
        manifest["source_models"][0].pop("include_bindings")
        members["manifest.json"] = json.dumps(manifest).encode()
        include = f"#include {sibling_nodes}\n"
        members[f'raw/{second["resource_id"]}.rad'] = include.encode()
        archive = tmp_path / "ac0.caeprep"
        with ZipFile(archive, "w") as project:
            for name, data in members.items():
                project.writestr(name, data)
    session.open_project(archive)
    output = tmp_path / "out/model_0000.rad"
    session.export_rad(output)
    assert (output.parent / second["logical_path"]).read_text() == include
    session.open_rad(output)
    assert session.mesh_view()["node_ids"] == (1, 88)


@pytest.mark.parametrize("variant", ("original", "mixed-case", "mixed-qualification"))
def test_d23_exports_valid_nine_file_deck_without_early_qualification(tmp_path, variant):
    directory = tmp_path / "source"
    units = f"{'Mg':>20}{'mm':>20}{'s':>20}\n"
    begin = "/BEGIN\nNine files\n      2025         0\n" + units * 2
    files = {
        "start_0000.rad": begin + "#include pick.inc\n#include mesh/choose.inc\n#include b/second.inc\n#include a/first.inc\n/END\n",
        "pick.inc": "# root candidate\n",
        "mesh/choose.inc": "#include pick.inc\n",
        "mesh/pick.inc": "#include nodes.inc\n",
        "b/second.inc": "#include nodes.inc\n",
        "a/first.inc": "# ninth file\n",
        "nodes.inc": f"/NODE\n{_node_line(1, 1, 0, 0)}\n#include b/extra.inc\n",
        "b/extra.inc": "#include nodes.inc\n",
        "b/nodes.inc": f"/NODE\n{_node_line(88, 2, 0, 0)}\n",
    }
    expected = dict(files)
    node_ids = (1, 88)
    if variant == "mixed-case":
        files["mesh/choose.inc"] = expected["mesh/choose.inc"] = '#include "PiCk.InC"\n'
    elif variant == "mixed-qualification":
        files["start_0000.rad"] = files["start_0000.rad"].replace("/END", "#include c/first.inc\n#include d/second.inc\n/END")
        files.update({
            "c/first.inc": "#include claims.inc\n",
            "c/claims.inc": "# Unselected sibling keeps root in the deferred wave\n",
            "d/second.inc": "#include claims.inc\n",
            "d/extra.inc": "#include claims.inc\n",
            "claims.inc": f"/NODE\n{_node_line(101, 1, 1, 0)}\n#include d/extra.inc\n",
            "d/claims.inc": f"/NODE\n{_node_line(188, 2, 1, 0)}\n",
        })
        expected.update(files)
        del expected["c/claims.inc"]
        expected["d/extra.inc"] = "#include d/claims.inc\n"
        node_ids = (1, 88, 101, 188)
    for path, contents in files.items():
        _write(directory / path, contents)
    session = PrepSession()
    session.open_rad(directory / "start_0000.rad")
    case = session.create_analysis_case("Round trip", [], .01, .001, "s")["case_id"]
    project = tmp_path / "nine.caeprep"
    session.save_project(project)
    for reopened in (False, True):
        if reopened:
            session.open_project(project)
        for kind, method in (("starter", session.export_rad), ("case", lambda path: session.export_analysis_case(path, case))):
            output = tmp_path / f"{reopened}-{kind}" / "renamed_0000.rad"
            method(output)
            for path, contents in expected.items():
                if path != "start_0000.rad":
                    assert (output.parent / path).read_bytes() == contents.encode()
            loaded = PrepSession()
            loaded.open_rad(output)
            assert loaded.mesh_view()["node_ids"] == node_ids


def test_d23_export_preserves_active_binding_when_inventory_loses_an_unselected_candidate(tmp_path):
    source = tmp_path / "source"
    starter = _write(source / "starter_0000.rad", "/BEGIN\nActive bindings\n#include a/first.inc\n#include b/second.inc\n/END\n")
    _write(source / "a/first.inc", "#include nodes.inc\n")
    _write(source / "a/nodes.inc", "# not loaded\n")
    _write(source / "b/second.inc", "#include nodes.inc\n")
    _write(source / "b/extra.inc", "#include nodes.inc\n")
    _write(source / "nodes.inc", f"/NODE\n{_node_line(1, 1, 0, 0)}\n#include b/extra.inc\n")
    _write(source / "b/nodes.inc", f"/NODE\n{_node_line(88, 2, 0, 0)}\n")
    session = PrepSession()
    session.open_rad(starter)
    original = _mesh_facts(session)
    assert set(original[0]) == {1, 88}
    project = tmp_path / "active.caeprep"
    session.save_project(project)
    for label in ("active", "reopened"):
        if label == "reopened":
            session.open_project(project)
        output = tmp_path / label / "export_0000.rad"
        session.export_rad(output)
        assert (output.parent / "b/second.inc").read_bytes() == b"#include nodes.inc\n"
        assert (output.parent / "b/extra.inc").read_bytes() == b"#include b/nodes.inc\n"
        reparsed = PrepSession()
        reparsed.open_rad(output)
        assert _mesh_facts(reparsed) == original


@pytest.mark.parametrize("copies", (1, 9))
def test_d23_export_can_qualify_upstream_include_to_keep_all_nine_bindings(tmp_path, copies):
    units = f"{'Mg':>20}{'mm':>20}{'s':>20}\n"
    begin = "/BEGIN\nSelectively qualified\n      2025         0\n" + units * 2
    payloads, root_refs, node_ids = {}, [], []
    for i in range(copies):
        first, second = 100 * i + 1, 100 * i + 88
        node_ids.extend((first, second))
        root_refs.extend((f"mark{i}.inc", f"a/mark{i}.inc", f"b/branch{i}.inc"))
        payloads.update({
            f"mark{i}.inc": "# Marker\n",
            f"a/mark{i}.inc": f"#include nodes{i}.inc\n",
            f"b/branch{i}.inc": f"#include main{i}.inc\n",
            f"b/main{i}.inc": "# Unused alternative\n",
            f"main{i}.inc": f"#include c/gate{i}.inc\n#include nodes{i}.inc\n",
            f"c/gate{i}.inc": f"#include mark{i}.inc\n",
            f"c/mark{i}.inc": f"#include a/nodes{i}.inc\n",
            f"nodes{i}.inc": f"/NODE\n{_node_line(first, 1, 0, 0)}\n",
            f"a/nodes{i}.inc": f"/NODE\n{_node_line(second, 2, 0, 0)}\n",
        })
    source = tmp_path / "source"
    for relative, payload in payloads.items():
        _write(source / relative, payload)
    starter = _write(source / "starter_0000.rad", begin + "".join(f"#include {path}\n" for path in root_refs) + "/END\n")

    def bindings(session):
        return {("Starter" if owner == session._root_id else session._paths[owner], ordinal): session._paths[target]
                for (owner, ordinal), target in session._include_bindings.items()}

    session = PrepSession()
    session.open_rad(starter)
    expected = bindings(session)
    for i in range(copies):
        assert expected[f"a/mark{i}.inc", 0] == f"nodes{i}.inc"
        assert expected[f"c/gate{i}.inc", 0] == f"c/mark{i}.inc"
    case = session.create_analysis_case("Nested INCLUDE export", [], .01, .001, "s")["case_id"]
    project = tmp_path / "bound.caeprep"
    session.save_project(project)
    for label in ("active", "reopened"):
        if label == "reopened":
            session.open_project(project)
        for mode in ("native", "case"):
            output = tmp_path / label / mode / "renamed_0000.rad"
            if mode == "native":
                session.export_rad(output)
            else:
                session.export_analysis_case(output, case)
            for relative, payload in payloads.items():
                path = output.parent / relative
                if relative.startswith("b/main"):
                    assert not path.exists()
                else:
                    rendered = payload.replace("#include mark", "#include c/mark") if relative.startswith("c/gate") else payload
                    assert path.read_bytes() == rendered.encode()
            reopened = PrepSession()
            reopened.open_rad(output)
            assert bindings(reopened) == expected
            assert len(reopened._paths) == 1 + 8 * copies
            assert reopened.mesh_view()["node_ids"] == tuple(node_ids)


@pytest.mark.parametrize("diamond", (False, True), ids=("one-path", "two-paths"))
def test_d23_export_qualifies_coupled_include_waves(tmp_path, diamond):
    def directives(*paths):
        return "".join(f"#include {path}\n" for path in paths)

    marks = [f"mark{i}.inc" for i in range(9)]
    units = f"{'Mg':>20}{'mm':>20}{'s':>20}\n"
    begin = "/BEGIN\nCoupled INCLUDE waves\n      2025         0\n" + units * 2
    payloads = {"model_0000.rad": begin + directives(*marks, "a/early.inc", "b/branch.inc") + "/END\n",
                "a/early.inc": directives("nodes.inc"), "b/branch.inc": directives("main.inc"),
                "b/main.inc": "# Unused alternative\n",
                "main.inc": directives("c/gate.inc", "nodes.inc"),
                "nodes.inc": f"/NODE\n{_node_line(1, 1, 0, 0)}\n",
                "a/nodes.inc": f"/NODE\n{_node_line(88, 2, 0, 0)}\n",
                f"c/{marks[-1]}": directives("a/nodes.inc")}
    rewrites = {}
    for owner, mark in zip(("c/gate.inc", *(f"c/{mark}" for mark in marks[:-1])), marks):
        payloads[mark] = "# Root marker\n"
        payloads[owner] = directives(mark)
        rewrites[owner] = directives(f"c/{mark}")
    if diamond:
        payloads["model_0000.rad"] = payloads["model_0000.rad"].replace("/END", directives("d/side.inc") + "/END")
        payloads["d/side.inc"] = "# Sibling marker\n"
        payloads["nodes.inc"] += directives("d/probe.inc")
        payloads["d/probe.inc"] = directives("side.inc")
        payloads["side.inc"] = directives("c/decoy.inc")
        payloads["c/decoy.inc"] = directives("mark8.inc")
        rewrites["c/decoy.inc"] = directives("c/mark8.inc")
    source = tmp_path / "source"
    for path, content in payloads.items():
        _write(source / path, content)

    def bindings(session):
        return {(None if owner == session._root_id else session._paths[owner], ordinal): session._paths[target]
                for (owner, ordinal), target in session._include_bindings.items()}

    session = PrepSession()
    session.open_rad(source / "model_0000.rad")
    expected = bindings(session)
    assert expected["a/early.inc", 0] == "nodes.inc"
    if diamond:
        assert {owner for (owner, _), path in expected.items() if path == "c/mark8.inc"} == {"c/mark7.inc", "c/decoy.inc"}
    expected_file_count = 29 if diamond else 25
    assert len(session._paths) == expected_file_count
    case = session.create_analysis_case("Coupled INCLUDE export", [], .01, .001, "s")["case_id"]
    project = tmp_path / "bound.caeprep"
    session.save_project(project)
    for label in ("active", "reopened"):
        if label == "reopened":
            session.open_project(project)
        for mode in ("native", "solver", "case"):
            output = tmp_path / label / mode / "renamed_0000.rad"
            if mode == "native":
                session.export_rad(output)
            elif mode == "solver":
                session.export_solver_inputs(output, .01, .001)
            else:
                session.export_analysis_case(output, case)
            for owner, text in rewrites.items():
                assert (output.parent / owner).read_bytes() == text.encode()
            reopened = PrepSession()
            reopened.open_rad(output)
            assert bindings(reopened) == expected
            assert len(reopened._paths) == expected_file_count
            assert reopened.mesh_view()["node_ids"] == (1, 88)


def test_d23_reopens_archive_whose_older_resolver_claimed_second_sibling(tmp_path):
    source = tmp_path / "source"
    starter = _write(source / "starter_0000.rad", "/BEGIN\nArchived claims\n#include a/first.inc\n#include a/second.inc\n/END\n")
    _write(source / "a/first.inc", "#include nodes.inc\n")
    _write(source / "a/second.inc", "#include a/nodes.inc\n")
    _write(source / "nodes.inc", f"/NODE\n{_node_line(1, 1, 0, 0)}\n")
    _write(source / "a/nodes.inc", f"/NODE\n{_node_line(88, 2, 0, 0)}\n")
    session = PrepSession()
    session.open_rad(starter)
    project = tmp_path / "prior.caeprep"
    session.save_project(project)
    with ZipFile(project) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    manifest.pop("include_bindings")
    second = next(item["raw_member"] for item in manifest["resources"] if item["logical_path"] == "a/second.inc")
    members[second] = b"#include nodes.inc\n"
    members["manifest.json"] = json.dumps(manifest).encode()
    legacy = tmp_path / "legacy.caeprep"
    with ZipFile(legacy, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    session.open_project(legacy)
    expected = {1: ((1, 0, 0), ("nodes.inc",)), 88: ((2, 0, 0), ("a/nodes.inc",))}
    assert _mesh_facts(session)[0] == expected
    output = tmp_path / "out/export_0000.rad"
    session.export_rad(output)
    session.open_rad(output)
    assert _mesh_facts(session)[0] == expected


def test_d23_nested_include_avoids_current_file_and_ancestor_shadows(tmp_path):
    starter = _write(tmp_path / "source_0000.rad", "/BEGIN\nAncestor test\n#include mesh/first.inc\n/END\n")
    _write(tmp_path / "mesh/first.inc", "#include first.inc\n#include source_0000.rad\n")
    _write(tmp_path / "first.inc", f"/NODE\n{_node_line(1, 1, 0, 0)}\n")
    _write(tmp_path / "mesh/source_0000.rad", f"/NODE\n{_node_line(2, 2, 0, 0)}\n")
    session = PrepSession()
    session.open_rad(starter)
    assert _mesh_facts(session)[0] == {1: ((1, 0, 0), ("first.inc",)), 2: ((2, 0, 0), ("mesh/source_0000.rad",))}
    assert not session.diagnostics()
    project = tmp_path / "ancestor.caeprep"
    session.save_project(project)
    session.open_project(project)
    assert not session.diagnostics()


@pytest.mark.parametrize("legacy_format", ("unchanged", "unquoted", "mixed-direct-inline", "tampered-direct-inline",
                                             "tampered-two-line", "direct-inline-only", "direct-inline-bare",
                                             "direct-inline-qualified-reached", "direct-inline-bare-reached",
                                             "inactive-line", "inactive-tight", "root-first", "root-first-resaved",
                                             "root-first-recorded", "ambiguous-inline", "ambiguous-resaved"))
def test_d23_reopens_legacy_quoted_two_line_source_archive(tmp_path, legacy_format):
    mixed = legacy_format in ("mixed-direct-inline", "tampered-direct-inline", "tampered-two-line")
    ambiguous = legacy_format.startswith("ambiguous-")
    root_first = ambiguous or legacy_format.startswith("root-first")
    inline_only = root_first or legacy_format.startswith("direct-inline-")
    already_reached = root_first or legacy_format.endswith("-reached")
    inactive = legacy_format.startswith("inactive-")
    inactive_text = b'#include"nodes.inc"\r\n' if legacy_format == "inactive-tight" else b'#include "nodes.inc"\r\n'
    name = "sets/nodes.inc" if legacy_format in ("direct-inline-only", "direct-inline-qualified-reached") else "nodes.inc"
    separator = " " if inline_only else "\r\n"
    starter, begin, owner, _ = _nested_include_deck(
        tmp_path / "source", "root-claimed" if mixed or inline_only or inactive or legacy_format == "unchanged" else "sibling-claimed",
        separator, filename=name)
    if ambiguous:
        starter.write_bytes(starter.read_bytes().replace(b"#include mesh/first.inc\n#include nodes.inc\n",
                            b"#include nodes.inc\n#include mesh/nodes.inc\n#include mesh/first.inc\n"))
    elif already_reached:
        starter.write_bytes(starter.read_bytes().replace(b"/END", f"#include mesh/{name}\n/END".encode()))
    if mixed or inline_only:
        nested = starter.parent / "mesh/first.inc"
        with nested.open("ab") as stream:
            stream.write(f"#include {name}\r\n".encode())
    if inactive:
        with (starter.parent / "mesh/first.inc").open("ab") as stream:
            stream.write(b'#enddata\r\n' + inactive_text)
    session = PrepSession()
    # An unrelated destination file with the same name must not acquire the old source INCLUDE.
    base = _write(tmp_path / "base/base_0000.rad", begin + "#include nodes.inc\n/END\n")
    _write(base.with_name("nodes.inc"), f"/NODE\n{_node_line(88, 83, 1, 0)}\n")
    session.open_rad(base)
    plan = session.plan_import_source(starter)
    session.import_source(plan["plan_id"])
    expected = _mesh_facts(session)
    archive = tmp_path / "modern.caeprep"
    session.save_project(archive)
    with ZipFile(archive) as project:
        members = {name: project.read(name) for name in project.namelist()}
    manifest = json.loads(members["manifest.json"])
    source_record = manifest["source_models"][0]
    if legacy_format != "root-first-recorded":
        source_record.pop("include_bindings")
    if not root_first or legacy_format in ("root-first", "ambiguous-inline"):
        manifest.pop("include_bindings")
    if legacy_format == "unchanged" or legacy_format == "mixed-direct-inline" or inactive or (inline_only and not root_first):
        # The sibling-first writer archived files in traversal order.
        files = source_record["files"]
        root_index = next(i for i, item in enumerate(files) if item["original_path"] == name)
        sibling = next(item for item in files if item["original_path"] == f"mesh/{name}")
        files.remove(sibling)
        files.insert(root_index, sibling)
    source_files = {item["original_path"]: item for item in plan["source"]["files"]}
    if legacy_format in ("root-first-resaved", "ambiguous-resaved"):
        nested_id = source_files["mesh/first.inc"]["resource_id"]
        root_nodes_id = source_files[name]["resource_id"]
        manifest["include_bindings"].extend([[nested_id, ordinal, root_nodes_id] for ordinal in range(2)])
    members["manifest.json"] = json.dumps(manifest).encode()
    mapped_path = source_files[owner]["logical_path"]
    mapped_member = f'raw/{source_files["mesh/first.inc"]["resource_id"]}.rad'
    replacement = '"nodes.inc"' if legacy_format != "unquoted" else mapped_path
    current = f'"{mapped_path}"\r\n'.encode("ascii")
    if not inline_only and legacy_format != "tampered-direct-inline":
        assert members[mapped_member].count(current) == 1
        members[mapped_member] = members[mapped_member].replace(current, f"{replacement}\r\n".encode("ascii"))
    if (mixed and legacy_format != "tampered-two-line") or inline_only:
        root_nodes = source_files[name]["logical_path"]
        inline = f"#include {root_nodes if already_reached else mapped_path}\r\n".encode("ascii")
        assert members[mapped_member].count(inline) == (2 if inline_only else 1)
        members[mapped_member] = members[mapped_member].replace(inline, f"#include {root_nodes}\r\n".encode("ascii"))
    if legacy_format == "inactive-line":
        root_nodes = source_files["nodes.inc"]["logical_path"]
        members[mapped_member] = members[mapped_member].replace(
            b'#enddata\r\n#include "nodes.inc"\r\n', f"#enddata\r\n#include {root_nodes}\r\n".encode())
        inactive_text = f"#include {root_nodes}\r\n".encode()
    legacy = tmp_path / "legacy.caeprep"
    with ZipFile(legacy, "w") as project:
        for member, contents in members.items():
            project.writestr(member, contents)
    if legacy_format.startswith("tampered-") or legacy_format == "ambiguous-inline":
        with pytest.raises(PrepError) as error:
            session.open_project(legacy)
        assert error.value.code == "invalid_project"
        if ambiguous:
            assert "Archived INCLUDE bindings are ambiguous" in error.value.message
        return
    session.open_project(legacy)
    assert _mesh_facts(session) == expected
    assert not session.diagnostics()
    output = tmp_path / "out/export_0000.rad"
    session.export_rad(output)
    if inline_only:
        exported_include = output.parent / source_files["mesh/first.inc"]["logical_path"]
        intended = source_files[name]["logical_path"] if root_first else mapped_path
        assert exported_include.read_bytes().count(f"#include {intended}\r\n".encode()) == 2
    if inactive:
        exported_include = output.parent / source_files["mesh/first.inc"]["logical_path"]
        assert exported_include.read_bytes().endswith(b"#enddata\r\n" + inactive_text)
    reopened = PrepSession()
    reopened.open_rad(output)
    assert _mesh_facts(reopened) == expected


@pytest.mark.parametrize("name", ("nodes.inc", "sets/nodes.inc"))
def test_d23_reopens_legacy_active_include_without_whitespace(tmp_path, name):
    starter, begin, owner, _ = _nested_include_deck(tmp_path / "source", "root-claimed", "", filename=name)
    session = PrepSession()
    session.open_rad(_write(tmp_path / "base_0000.rad", begin + "/END\n"))
    plan = session.plan_import_source(starter)
    session.import_source(plan["plan_id"])
    expected = _mesh_facts(session)
    modern = tmp_path / "modern.caeprep"
    session.save_project(modern)
    with ZipFile(modern) as project:
        members = {member: project.read(member) for member in project.namelist()}
    manifest = json.loads(members["manifest.json"])
    manifest.pop("include_bindings")
    record = manifest["source_models"][0]
    record.pop("include_bindings")
    files = record["files"]
    by_path = {item["original_path"]: item for item in files}
    files.remove(by_path[owner])
    files.insert(files.index(by_path[name]), by_path[owner])
    members["manifest.json"] = json.dumps(manifest).encode()
    mapped = f'raw/{by_path["mesh/first.inc"]["resource_id"]}.rad'
    # The direct-inline writer did not rewrite a directive without whitespace.
    rewritten = f'#include {by_path[owner]["logical_path"]}\r\n'.encode()
    assert members[mapped].count(rewritten) == 1
    members[mapped] = members[mapped].replace(rewritten, f'#include"{name}"\r\n'.encode())
    legacy = tmp_path / "legacy.caeprep"
    with ZipFile(legacy, "w") as project:
        for member, contents in members.items():
            project.writestr(member, contents)
    session.open_project(legacy)
    nested_id, intended_id = (by_path[path]["resource_id"] for path in ("mesh/first.inc", owner))
    assert session._include_bindings[nested_id, 0] == intended_id
    output = tmp_path / "out/export_0000.rad"
    session.export_rad(output)
    session.open_rad(output)
    ids = {path: rid for rid, path in session._paths.items()}
    assert session._include_bindings[ids[by_path["mesh/first.inc"]["logical_path"]], 0] == ids[by_path[owner]["logical_path"]]
    assert _mesh_facts(session) == expected


@pytest.mark.parametrize("nodes_path", ("nodes.inc", "sets/nodes.inc"))
@pytest.mark.parametrize("variant", ("tight", "two-line", "v4", "ambiguous-v5", "forged-v4"))
def test_d23_distinguishes_historical_include_writers(tmp_path, nodes_path, variant):
    source = tmp_path / "source"
    starter = _build_deck_multi_include(source)
    raw = starter.read_bytes()
    (source / nodes_path).parent.mkdir(parents=True, exist_ok=True)
    (source / nodes_path).write_bytes((source / "nodes.inc").read_bytes())
    starter.write_bytes(raw.replace(b"#include nodes.inc\n",
        f"#include {nodes_path}\n#include mesh/{nodes_path}\n#include mesh/first.inc\n".encode()))
    with_extra = variant in ("tight", "two-line")
    old_extra = '#include"extra.inc"\r\n' if variant == "tight" else '#include\r\n"extra.inc"\r\n' if with_extra else ""
    _write(source / "mesh/first.inc", f"#include {nodes_path}\n" * 2 + old_extra)
    _write(source / f"mesh/{nodes_path}", f"/NODE\n{_node_line(100, 83, 1, 0)}\n")
    if with_extra:
        _write(source / "mesh/extra.inc", "# Only accessible relative to the including file\n")
    base = _write(tmp_path / "base_0000.rad", raw.split(b"/MAT", 1)[0].decode() + "/END\n")
    session = PrepSession()
    session.open_rad(base)
    plan = session.plan_import_source(starter)
    session.import_source(plan["plan_id"])
    modern = tmp_path / "modern.caeprep"
    session.save_project(modern)
    with ZipFile(modern) as project:
        members = {member: project.read(member) for member in project.namelist()}
    manifest = json.loads(members["manifest.json"])
    manifest.pop("include_bindings")
    record = manifest["source_models"][0]
    record.pop("include_bindings")
    if variant in ("v4", "forged-v4"):
        for resource in manifest["resources"]:
            resource["state"]["state_version"] = 4
            assert not resource["state"].pop("retained_comments")
        if variant == "forged-v4":
            manifest["resources"][0]["state"]["created"].append({
                "id": "00000000-0000-4000-8000-000000000123", "comments": "# v5 only\n"})
    members["manifest.json"] = json.dumps(manifest).encode()
    by_path = {item["original_path"]: item for item in record["files"]}
    owner = by_path["mesh/first.inc"]
    mapped_member = f'raw/{owner["resource_id"]}.rad'
    # 8fe mapped both spaced inline directives by root path and left the
    # sibling-only operand in its original form.
    root_include = f'#include {by_path[nodes_path]["logical_path"]}\n'.encode()
    assert members[mapped_member].startswith(root_include * 2)
    members[mapped_member] = root_include * 2 + old_extra.encode()
    legacy = tmp_path / "legacy.caeprep"
    with ZipFile(legacy, "w") as project:
        for member, payload in members.items():
            project.writestr(member, payload)
    if variant == "ambiguous-v5":
        with pytest.raises(PrepError, match="Archived INCLUDE bindings are ambiguous") as error:
            session.open_project(legacy)
        assert error.value.code == "invalid_project"
        return
    if variant == "forged-v4":
        with pytest.raises(PrepError, match="Invalid created card block") as error:
            session.open_project(legacy)
        assert error.value.code == "invalid_project"
        return
    session.open_project(legacy)
    intended = f"mesh/{nodes_path}" if with_extra else nodes_path
    expected_paths = [intended, intended] + (["mesh/extra.inc"] if with_extra else [])
    assert [session._include_bindings[owner["resource_id"], ordinal] for ordinal in range(len(expected_paths))] == [
        by_path[path]["resource_id"] for path in expected_paths]
    assert len(session.mesh_view()["node_ids"]) == 15
    assert len(session.mesh_view()["cells"]) == 7
    facts = _mesh_facts(session)
    output = tmp_path / "out/export_0000.rad"
    session.export_rad(output)
    session.open_rad(output)
    ids = {path: rid for rid, path in session._paths.items()}
    assert [session._include_bindings[ids[owner["logical_path"]], ordinal] for ordinal in range(len(expected_paths))] == [
        ids[by_path[path]["logical_path"]] for path in expected_paths]
    assert _mesh_facts(session) == facts


def test_deck_preserves_validated_restore_version_until_next_restore():
    deck = DeckResource(b"/BEGIN\nLegacy\n/END\n")
    assert deck._restored_state_version == 5
    deck.restore({})
    assert deck._restored_state_version == 1
    state = deck.snapshot()
    assert state["state_version"] == 5
    old_state = {key: value for key, value in state.items() if key != "retained_comments"}
    old_state["state_version"] = 4
    assert deck.prepare_state(old_state) == state
    assert deck._restored_state_version == 1
    deck.restore(old_state)
    assert deck._restored_state_version == 4
    with pytest.raises(PrepError):
        deck.restore({**state, "patches": {"invalid": None}})
    assert deck._restored_state_version == 4 and deck.snapshot() == state


@pytest.mark.parametrize("invalid_version", (2.0, 3.0, 4.0, 5.0, True, False))
def test_deck_rejects_noninteger_state_versions_before_migration(invalid_version):
    deck = DeckResource(b"/BEGIN\nLegacy\n/END\n")
    deck.restore({})
    snapshot = deck.snapshot()
    state = {**snapshot, "state_version": invalid_version}
    for version, key in ((2, "replaced"), (3, "node_positions"), (4, "retained_comments")):
        if invalid_version <= version:
            state.pop(key)
    for restore in (deck.prepare_state, deck.restore):
        with pytest.raises(PrepError) as error:
            restore(state)
        assert error.value.code == "invalid_project"
        assert deck._restored_state_version == 1 and deck.snapshot() == snapshot


def test_deck_rejects_v5_comment_records_in_v4_state_atomically():
    deck = DeckResource(b"/BEGIN\nLegacy\n/END\n")
    deck.restore({})
    snapshot = deck.snapshot()
    forged = {key: value for key, value in snapshot.items() if key != "retained_comments"}
    forged.update(state_version=4, created=[{"id": "00000000-0000-4000-8000-000000000123", "comments": "# v5 only\n"}])
    for restore in (deck.prepare_state, deck.restore):
        with pytest.raises(PrepError) as error:
            restore(forged)
        assert error.value.code == "invalid_project"
        assert deck._restored_state_version == 1 and deck.snapshot() == snapshot


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


@pytest.mark.parametrize("family", ("SHELL", "BRICK", "QUAD", "SH4N", "TETRA"))
def test_d25_unselected_quad_or_solid_face_diagonal_blocks_split(tmp_path, family):
    starter = _build_deck_multi_include(tmp_path)
    if family in ("SHELL", "QUAD", "SH4N"):
        neighbor = f"/{family}/2\n" + _quad_line(302, 1, 4, 3, 2) + "\n"
    elif family == "TETRA":
        neighbor = "/TETRA/3\n" + _tet_line(302, 1, 3, 4, 7) + "\n"
    else:
        with (tmp_path / "nodes.inc").open("ab") as stream:
            stream.write("".join(_node_line(nid, x, y, 5) + "\n" for nid, (x, y) in
                enumerate(((0, 0), (10, 0), (10, 10), (0, 10)), start=30)).encode("ascii"))
        neighbor = "/BRICK/3\n" + "".join(f"{i:10d}" for i in (302, 1, 2, 3, 4, 30, 31, 32, 33)) + "\n"
    with (tmp_path / "shells_a.inc").open("ab") as stream:
        stream.write(neighbor.encode("ascii"))
    session = PrepSession()
    session.open_rad(starter)
    assert next(cell["formulation"] for cell in session.mesh_view()["cells"] if cell["id"] == 302) == family
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


def _pick_element(session, element_id, formulation="SH3N"):
    parent = _cell_ref(session, element_id)
    view = session.mesh_view()
    return session.select_pick({
        **{key: view[key] for key in ("document_id", "document_epoch", "revision", "projection_revision")},
        "kind": "element", "id": element_id, "formulation": formulation,
        "resource_id": parent["resource_id"],
        "resource_revision": view["resource_revisions"][parent["resource_id"]],
    })


@pytest.mark.parametrize("operation", ("split", "delete", "flip", "reassign"))
def test_mesh_planners_accept_formulation_qualified_picks(tmp_path, operation):
    session = PrepSession()
    session.open_rad(_build_deck_multi_include(tmp_path))
    picked, = _pick_element(session, 101)["refs"]
    part = _card_by_prefix(session, "/PART/4")
    part_ref = {"resource_id": part["resource_id"], "entity_kind": "part", "local_id": part["id"]}
    edge = (_node_ref(session, 1), _node_ref(session, 3))

    def plan(ref):
        if operation == "split":
            return session.plan_triangle_edge_split([ref, _cell_ref(session, 102)], edge)
        if operation == "delete":
            return session.plan_element_deletion([ref], orphan_policy="keep")
        if operation == "flip":
            return session.plan_shell_normal_flip([ref])
        return session.plan_part_reassignment([{"element": ref, "part": part_ref}])

    assert picked["formulation"] == "SH3N"
    assert plan(picked)["admissible"]
    assert plan({**picked, "formulation": None})["admissible"]
    for wrong in ("SHELL", 12):
        with pytest.raises(PrepError):
            plan({**picked, "formulation": wrong})
    if operation == "split":
        with pytest.raises(PrepError):
            session.plan_triangle_edge_split([picked, _cell_ref(session, 102)],
                                             ({**edge[0], "formulation": None}, edge[1]))
    elif operation == "reassign":
        with pytest.raises(PrepError):
            session.plan_part_reassignment([{"element": picked, "part": {**part_ref, "formulation": None}}])


@pytest.mark.parametrize(("family", "element_id"), (("SH4N", 201), ("TETRA", 301)))
def test_mesh_planners_accept_native_alias_from_viewport_pick(tmp_path, family, element_id):
    starter = _build_deck_multi_include(tmp_path)
    if family == "SH4N":
        mesh = tmp_path / "shells_b.inc"
        mesh.write_bytes(mesh.read_bytes().replace(b"/SHELL/2", b"/SH4N/2"))
    else:
        mesh = tmp_path / "shells_a.inc"
        mesh.write_bytes(mesh.read_bytes().replace(b"/TETRA4/3", b"/TETRA/3"))
        text = starter.read_bytes().replace(b"/PART/4\n", b"/PART/5\nSecond solid part\n"
                                           b"         3         1         0\n/PART/4\n")
        starter.write_bytes(text)
    session = PrepSession()
    session.open_rad(starter)
    picked, = _pick_element(session, element_id, family)["refs"]
    assert picked["formulation"] == family
    canonical = "SHELL" if family == "SH4N" else "TETRA4"
    selected = session.select_entity("element", element_id, resource_id=picked["resource_id"], formulation=canonical)
    assert selected["refs"] == [picked]
    deletion = session.plan_element_deletion([picked], orphan_policy="keep")
    assert [cell["ref"]["local_id"] for cell in deletion["removed_cells"]] == [element_id]
    if family == "SH4N":
        assert deletion["admissible"]
        assert session.plan_shell_normal_flip([picked])["admissible"]
    else:
        with pytest.raises(PrepError) as error:
            session.plan_shell_normal_flip([picked])
        assert error.value.code == "not_shell"
    part = _card_by_prefix(session, "/PART/4" if family == "SH4N" else "/PART/5")
    part_ref = {"resource_id": part["resource_id"], "entity_kind": "part", "local_id": part["id"]}
    assert session.plan_part_reassignment([{"element": picked, "part": part_ref}])["admissible"]


def test_case_export_round_trips_sh4n_and_tetra_keywords(tmp_path):
    starter = _build_deck_multi_include(tmp_path / "input")
    for include, before, after in (("shells_b.inc", b"/SHELL/2", b"/SH4N/2"),
                                   ("shells_a.inc", b"/TETRA4/3", b"/TETRA/3")):
        mesh = starter.parent / include
        mesh.write_bytes(mesh.read_bytes().replace(before, after))
    session = PrepSession()
    session.open_rad(starter)
    expected = _mesh_facts(session)
    case = session.create_analysis_case("Alias round trip", [], .01, .001, "s")["case_id"]
    output = tmp_path / "output/case_0000.rad"
    session.export_analysis_case(output, case)
    session.open_rad(output)
    assert _mesh_facts(session) == expected
    assert {"/SH4N/2", "/TETRA/3"} <= {card["keyword"] for card in session.list_cards()}


def test_reassigning_picked_split_children_updates_selection_owner(tmp_path):
    session = PrepSession()
    session.open_rad(_build_deck_multi_include(tmp_path))
    _pick_element(session, 101)
    split = session.plan_triangle_edge_split([_cell_ref(session, 101), _cell_ref(session, 102)],
                                             (_node_ref(session, 1), _node_ref(session, 3)))
    session.apply_triangle_edge_split(split["plan_id"])
    group_id = _find_card_id(session, "/GRSH3N/SH3N/13")
    stale = session.mesh_relationships()["stale_targets"]
    session.reconnect_mesh_targets({
        target: {"mesh_revision": record["mesh_revision"], "mapping":
                 {101: [302, 303], 102: [304, 305]} if target == group_id
                 else {member: _node_ref(session, member) for member in record["members"]}}
        for target, record in stale.items()
    })
    assert session.selection()["ids"] == [302, 303]
    assert session.active_object().native_scope == "/PART/1"
    part = _card_by_prefix(session, "/PART/4")
    destination = {"resource_id": part["resource_id"], "entity_kind": "part", "local_id": part["id"]}
    reassignment = session.plan_part_reassignment([
        {"element": ref, "part": destination} for ref in session.selection()["refs"]
    ])
    session.apply_part_reassignment(reassignment["plan_id"])
    assert session.selection()["ids"] == [302, 303]
    assert session.active_object().native_scope == "/PART/4"
    assert session.selected_objects() == (session.active_object(),)


@pytest.mark.parametrize("selection_source", ("entity", "pick", "part"))
def test_d25_edge_split_keeps_selected_triangles_part(tmp_path, selection_source):
    session = PrepSession()
    session.open_rad(_build_deck_multi_include(tmp_path))
    parent = _cell_ref(session, 101)
    if selection_source == "part":
        from caelab_prep.application.rad_provider import RadProvider
        session.activate_object(RadProvider(session).ref_for_card(_card_by_prefix(session, "/PART/1")))
    elif selection_source == "pick":
        _pick_element(session, 101)
    else:
        session.select_entity("element", 101)
    owner = session.active_object()
    assert owner.native_scope == "/PART/1"

    plan = session.plan_triangle_edge_split(
        [parent, _cell_ref(session, 102)], (_node_ref(session, 1), _node_ref(session, 3)))
    session.apply_triangle_edge_split(plan["plan_id"])

    selected = session.selection()
    if selection_source == "part":
        assert {302, 303, 304, 305} <= set(selected["ids"])
        assert {101, 102}.isdisjoint(selected["ids"])
    else:
        assert selected["ids"] == [302, 303]
        expected_family = "SH3N" if selection_source == "pick" else None
        assert [ref.get("formulation") for ref in selected["refs"]] == [expected_family] * 2
    assert session.active_object() == owner
    assert session.selected_objects() == (owner,)
    assert session.describe()["active_object"] == selected["active_object"]


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

        parent = _cell_ref(win.session, 101)
        win.session.select_entity("element", 101, resource_id=parent["resource_id"], formulation="SH3N")
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
