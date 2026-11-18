"""Comprehensive D23 (6 existing mesh edits x 2 multi-resource #include decks) and D25 (split_triangle_edge) tests."""
from __future__ import annotations

import math
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox

from caelab_prep.application import mesh_candidates as mc
from caelab_prep.application import mesh_edit_candidates as edits
from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.ui.main_window import MainWindow


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
                _tri_line(101, 1, 2, 3),
                _tri_line(102, 1, 3, 4),
                _tri_line(103, 2, 5, 6),
                _tri_line(104, 2, 6, 3),
                "/TETRA4/3",
                _tet_line(301, 1, 2, 3, 7),
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


def _reconnect_all_stale_auto(session: PrepSession, *, split_first_child_by_old_id: dict[int, int] | None = None,
                              node_remap: dict[int, int] | None = None, elem_remap: dict[int, int] | None = None):
    """Build explicit target reconnection mapping for any stale targets cleanly."""
    rel = session.mesh_relationships()
    stale = rel["stale_targets"]
    if not stale:
        return
    view = session.mesh_view()
    live_nodes = set(view["node_ids"])
    live_cells = {c["id"]: c for c in view["cells"]}
    part_cards = {int(c["keyword"].split("/")[2]): c["id"] for c in session.list_cards() if c["keyword"].upper().startswith("/PART/")}
    node_remap = node_remap or {}
    elem_remap = elem_remap or {}
    split_map = split_first_child_by_old_id or {}

    review_targets = {}
    direct_targets = {}
    for gid, info in stale.items():
        fam = info["family"]
        rev = info["mesh_revision"]
        old_members = list(info["members"])
        if fam == "SURF/PART":
            mapping = {}
            for pid in old_members:
                if any(c.get("part_id") == pid for c in view["cells"]):
                    mapping[pid] = part_cards[pid]
                elif part_cards:
                    live_pid = next(c["part_id"] for c in view["cells"] if c.get("part_id") in part_cards)
                    mapping[pid] = part_cards[live_pid]
            direct_targets[gid] = {"mesh_revision": rev, "mapping": mapping}
        elif fam == "GRNOD/NODE":
            mapping = {}
            dropped = []
            seen_targets = set()
            has_dup = False
            for nid in old_members:
                target_nid = node_remap.get(nid, nid)
                if target_nid in live_nodes:
                    ref = {"resource_id": view["node_resources"][target_nid][0], "entity_kind": "node", "local_id": target_nid}
                    mapping[nid] = ref
                    if target_nid in seen_targets:
                        has_dup = True
                    seen_targets.add(target_nid)
                else:
                    dropped.append(nid)
            assert mapping, f"Group {gid} lost all members unexpectedly"
            entry = {"mesh_revision": rev, "mapping": mapping}
            if dropped:
                entry["drop_members"] = dropped
            if has_dup:
                entry["coalesce_duplicates"] = True
            if dropped or has_dup:
                review_targets[gid] = entry
            else:
                direct_targets[gid] = {"mesh_revision": rev, "mapping": mapping}
        else:
            mapping = {}
            dropped = []
            for eid in old_members:
                target_eid = elem_remap.get(eid, split_map.get(eid, eid))
                if target_eid in live_cells:
                    cell = live_cells[target_eid]
                    mapping[eid] = {"resource_id": cell["resource_id"], "entity_kind": "element", "local_id": target_eid}
                else:
                    dropped.append(eid)
            if not mapping:
                form = fam.split("/")[1]
                compat = next(c for c in view["cells"] if c["formulation"] == form)
                for idx, eid in enumerate(old_members):
                    if idx == 0:
                        mapping[eid] = {"resource_id": compat["resource_id"], "entity_kind": "element", "local_id": compat["id"]}
                        dropped = [e for e in old_members if e != eid]
            if dropped:
                review_targets[gid] = {"mesh_revision": rev, "mapping": mapping, "drop_members": dropped}
            else:
                direct_targets[gid] = {"mesh_revision": rev, "mapping": mapping}

    if direct_targets:
        session.reconnect_mesh_targets(direct_targets, expected_revision=session.document.revision, expected_document_id=session.document.id)
    if review_targets:
        plan = session.plan_mesh_reconnection(review_targets, expected_revision=session.document.revision, expected_document_id=session.document.id)
        session.apply_mesh_reconnection(plan["plan_id"], expected_revision=session.document.revision, expected_document_id=session.document.id)


def _roundtrip_save_reconnect_and_export(session: PrepSession, tmp_path: Path, tag: str, **reconnect_kwargs):
    assert session.mesh_relationships()["stale_targets"], f"{tag}: expected stale targets before save"
    proj_path = tmp_path / f"{tag}.caeprep"
    session.save_project(str(proj_path))

    # Reopen in a completely fresh PrepSession to verify persisted deltas + stale targets
    reopened = PrepSession()
    reopened.open_project(str(proj_path))
    assert reopened.mesh_relationships()["stale_targets"] == session.mesh_relationships()["stale_targets"]
    with pytest.raises(PrepError) as export_block:
        reopened.export_rad(str(tmp_path / f"blocked_{tag}_0000.rad"))
    assert export_block.value.code == "stale_mesh_targets"

    _reconnect_all_stale_auto(reopened, **reconnect_kwargs)
    assert reopened.mesh_relationships()["stale_targets"] == {}

    out_dir = tmp_path / f"export_{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = reopened.export_solver_inputs(str(out_dir / f"{tag}_0000.rad"), end_time=0.01, output_interval=0.002)
    assert Path(out["starter_path"]).is_file()
    assert Path(out["engine_path"]).is_file()
    # Fresh PrepSession must cleanly re-open exported Starter deck
    verify = PrepSession()
    verify.open_rad(out["starter_path"])
    assert len(verify.mesh_view()["node_ids"]) == len(reopened.mesh_view()["node_ids"])
    assert len(verify.mesh_view()["cells"]) == len(reopened.mesh_view()["cells"])
    return reopened


@pytest.mark.parametrize("deck_kind", ("deck_a", "deck_b"))
def test_d23_all_six_existing_mesh_edits_end_to_end_across_two_multiresource_decks(tmp_path: Path, deck_kind: str):
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
    assert math.isclose(dict(zip(s1.mesh_view()["node_ids"], s1.mesh_view()["points"]))[tip_node][0], moved_xyz[0])
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
    _roundtrip_save_reconnect_and_export(s2, tmp_path, f"{deck_kind}_merge", node_remap={src_nid: keep_nid})

    # 3. element_deletion: preview -> cancel -> apply -> 1 undo/redo -> save/reopen -> reconnect -> export
    s3 = PrepSession()
    s3.open_rad(str(starter))
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
    assert all(c["id"] != del_eid for c in s3.mesh_view()["cells"])
    _roundtrip_save_reconnect_and_export(s3, tmp_path, f"{deck_kind}_delete")

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
        _roundtrip_save_reconnect_and_export(s6, tmp_path, f"{deck_kind}_remesh", elem_remap={201: 501, 202: 502})
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
        _roundtrip_save_reconnect_and_export(s6, tmp_path, f"{deck_kind}_remesh", elem_remap={81: 581, 82: 582})


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
        + "# trailing comment before EOF row without newline\n"
        + _tri_line(50, 1, 2, 3)  # Emptied on reassign & lacks trailing EOF newline!
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
    p2 = _card_by_prefix(s, "/PART/2")
    plan = s.plan_part_reassignment([{"element": _cell_ref(s, 50), "part": {"resource_id": s._root_id, "entity_kind": "part", "local_id": p2["id"]}}])
    s.apply_part_reassignment(plan["plan_id"], expected_revision=s.document.revision, expected_document_id=s.document.id)
    assert next(c["part_id"] for c in s.mesh_view()["cells"] if c["id"] == 50) == 2

    # Also split edge on EOF without trailing newline in both nodes and elems!
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

    # 2. Split 1 boundary SH3N triangle edge (n1, n2) with caller-supplied explicit IDs
    cand1 = edits.split_triangle_edge(snapshot, (e101,), (n1, n2), new_node_id=990, new_element_ids=(9001, 9002))
    assert cand1.added_nodes[0].ref.local_id == 990
    assert tuple(c.ref.local_id for c in cand1.added_cells) == (9001, 9002)
    assert cand1.added_nodes[0].xyz == (5.0, 0.0, 0.0)

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
        edits.split_triangle_edge(snapshot, (e101,), (n1, n2), new_node_id=1)  # collision
    assert err.value.code == "node_id_collision"

    with pytest.raises(edits.MeshEditError) as err:
        edits.split_triangle_edge(snapshot, (e101,), (n1, n2), new_element_ids=(101, 999))  # collision
    assert err.value.code == "element_id_collision"

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
    first_child_101 = plan["split_cells"][0]["children"][0]["local_id"]
    first_child_102 = plan["split_cells"][1]["children"][0]["local_id"]
    res = s.apply_triangle_edge_split(plan["plan_id"], expected_revision=rev0, expected_document_id=s.document.id)
    assert res["revision"] == rev0 + 1
    assert len(s.mesh_view()["node_ids"]) == n_before + 1
    assert new_node_id in s.mesh_view()["node_ids"]
    assert len(s.mesh_view()["cells"]) == c_before + 2  # 2 parents removed, 4 children added

    # Midpoint node was written to nodes.inc, child SH3N written to shells_a.inc
    nodes_inc_id = next(rid for rid, p in s._paths.items() if p.endswith("nodes.inc"))
    shells_a_id = next(rid for rid, p in s._paths.items() if p.endswith("shells_a.inc"))
    assert str(new_node_id) in s.document.resources[nodes_inc_id].render().decode("latin1")
    shells_a_text = s.document.resources[shells_a_id].render().decode("latin1")
    assert str(first_child_101) in shells_a_text and str(first_child_102) in shells_a_text

    # 1 Undo restores both includes + relations atomically; 1 Redo restores split
    s.undo()
    assert len(s.mesh_view()["node_ids"]) == n_before
    assert len(s.mesh_view()["cells"]) == c_before
    s.redo()
    assert len(s.mesh_view()["node_ids"]) == n_before + 1
    assert len(s.mesh_view()["cells"]) == c_before + 2

    reopened = _roundtrip_save_reconnect_and_export(
        s, tmp_path, "d25_split", split_first_child_by_old_id={101: first_child_101, 102: first_child_102}
    )
    assert new_node_id in reopened.mesh_view()["node_ids"]

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
def test_d25_triangle_edge_split_dialog_ui_and_screenshot(tmp_path: Path, presentation: str):
    """Exercise TriangleEdgeSplitDialog across presentations and capture 1440x900 screenshot on beidprep."""
    from PySide6.QtGui import QFont, QFontDatabase
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
        assert hasattr(win, "open_edge_split")
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
        assert dialog.reviewed.isChecked() is True
        assert dialog.apply_button.isEnabled() is True
        assert "Split edge 1 – 3" in dialog.preview.toPlainText()

        if presentation == "beidprep":
            from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter

            font_path = Path("C:/Windows/Fonts/malgun.ttf")
            if font_path.is_file():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id >= 0:
                    family = QFontDatabase.applicationFontFamilies(font_id)[0]
                    app.setFont(QFont(family, 9))
            win.setWindowState(Qt.WindowState.WindowNoState)
            win.resize(1440, 900)
            win.show()
            dialog.show()
            dialog.adjustSize()
            dialog.resize(max(dialog.width(), 820), max(dialog.height(), 640))
            app.processEvents()
            screenshot_dir = Path(r"C:\Users\pikac\.gemini\antigravity\brain\9beddcd8-3baf-44f6-9560-2c07a847da3f")
            if screenshot_dir.is_dir():
                canvas = win.grab()
                dialog_pix = dialog.grab()
                painter = QPainter(canvas)
                x = max(0, (canvas.width() - dialog_pix.width()) // 2)
                y = max(0, (canvas.height() - dialog_pix.height()) // 2)
                painter.fillRect(x - 2, y - 2, dialog_pix.width() + 4, dialog_pix.height() + 4, QColor("#2a3242"))
                painter.drawPixmap(x, y, dialog_pix)
                painter.end()
                canvas.save(str(screenshot_dir / "d25_prep_edge_split_dialog.png"))

        before_nodes = len(win.session.mesh_view()["node_ids"])
        dialog.apply_change()
        app.processEvents()
        assert len(win.session.mesh_view()["node_ids"]) == before_nodes + 1
        win.session.undo()
        app.processEvents()
        assert len(win.session.mesh_view()["node_ids"]) == before_nodes
    finally:
        win._allow_close = True
        win.close()
        app.processEvents()
