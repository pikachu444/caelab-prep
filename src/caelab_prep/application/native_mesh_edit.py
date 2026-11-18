"""Existing native slot edits and trial target review shared by mesh commands."""
from copy import copy
from dataclasses import asdict

from ..cae_core import PrepError
from ..radioss.assembly import ELEMENTS
from ..radioss.modeling import integer, real
from ..radioss.relations import node_support
from . import mesh_edit_candidates as edits
from .mesh_relations import explicit_member_state


def _ensure_newline(text, newline):
    return text if text.endswith(("\r", "\n")) else text + newline


def _format_node_row(node, newline):
    return integer(node.ref.local_id) + "".join(real(value) for value in node.xyz) + newline


def _format_cell_row(cell, newline):
    parts = [integer(cell.ref.local_id), *(integer(node.local_id) for node in cell.nodes)]
    if cell.family == "BEAM" and cell.orientation_node is not None:
        parts.append(integer(cell.orientation_node.local_id))
    return "".join(parts) + newline


def native_mesh_edit_states(session, candidate, *, layout_error_code):
    removals = set(candidate.removed_nodes)
    removed_cells = set(candidate.removed_cells)
    updates = {cell.ref: cell for cell in candidate.cell_updates}
    added_nodes_by_res = {}
    for node in candidate.added_nodes:
        added_nodes_by_res.setdefault(node.ref.resource_id, []).append(node)
    added_cells_by_res = {}
    added_cells_by_ref = {}
    for cell in candidate.added_cells:
        added_cells_by_res.setdefault(cell.ref.resource_id, []).append(cell)
        added_cells_by_ref[cell.ref] = cell
    split_map = dict(candidate.split_cells)
    states = {}
    for owner in session._deck_resources():
        resource = copy(owner)
        replacements = {}
        transfers = {}
        extra_blocks = []
        emitted_added_cells = set()
        emitted_added_nodes = False
        node_card_ids = [c.id for c in owner.cards if c.keyword.upper().strip("/").split("/")[0] == "NODE"]
        target_node_card_id = node_card_ids[-1] if node_card_ids else None
        lines = owner.render().decode("latin1").splitlines(keepends=True)
        for card in owner.cards:
            family = card.keyword.upper().strip("/").split("/")[0]
            if family != "NODE" and family not in ELEMENTS:
                continue
            changed = {}
            moved_targets = []
            replaced_in_place = False
            for row in card.data:
                identifier = int(lines[row][:10])
                ref = edits.Ref(owner.id, "node" if family == "NODE" else "element", identifier)
                if family == "NODE":
                    if ref in removals:
                        changed[row] = None
                elif ref in removed_cells:
                    child_refs = split_map.get(ref)
                    if child_refs:
                        previous = candidate.base._cells[ref]
                        inline_children = [
                            added_cells_by_ref[cref]
                            for cref in child_refs
                            if (added_cells_by_ref[cref].ref.resource_id == owner.id
                                and added_cells_by_ref[cref].family == family
                                and added_cells_by_ref[cref].part == previous.part)
                        ]
                        if len(inline_children) == len(child_refs):
                            changed[row] = "".join(_format_cell_row(child, owner.newline) for child in inline_children)
                            emitted_added_cells.update(child_refs)
                            replaced_in_place = True
                        else:
                            changed[row] = None
                    else:
                        changed[row] = None
                elif ref in updates:
                    cell = updates[ref]
                    if cell.family != family:
                        raise PrepError("invalid_mesh_candidate", "A connectivity edit cannot change element family.")
                    text = lines[row]
                    body = text.rstrip("\r\n")
                    ending = text[len(body):]
                    previous = candidate.base._cells[ref]
                    fields = [(index, node.local_id) for index, node in enumerate(cell.nodes, 1)
                              if node != previous.nodes[index - 1]]
                    if family == "BEAM" and cell.orientation_node is not None and cell.orientation_node != previous.orientation_node:
                        fields.append((3, cell.orientation_node.local_id))
                    for index, value in fields:
                        start = index * 10
                        body = body[:start].ljust(start) + integer(value) + body[start + 10:]
                    if cell.part != previous.part:
                        target = session._part_native_references(cell.part.local_id)[2]["native_part_id"]
                        key = family, target
                        transfers.setdefault(key, []).append(body + (ending or owner.newline))
                        moved_targets.append(key)
                        changed[row] = None
                    else:
                        changed[row] = body + ending
            append_nodes = card.id == target_node_card_id and bool(added_nodes_by_res.get(owner.id))
            if changed or append_nodes:
                body_parts = []
                for row in range(card.start, card.stop):
                    piece = changed.get(row, lines[row]) if row in changed else lines[row]
                    if piece is not None and piece != "":
                        body_parts.append(piece)
                if append_nodes:
                    emitted_added_nodes = True
                    if body_parts:
                        body_parts[-1] = _ensure_newline(body_parts[-1], owner.newline)
                    body_parts.extend(_format_node_row(node, owner.newline) for node in added_nodes_by_res[owner.id])
                text = "".join(body_parts)
                empty = (not append_nodes and not replaced_in_place
                         and all(row in changed and changed[row] is None for row in card.data))
                if not empty:
                    text = _ensure_newline(text, owner.newline)
                # Full-card replacement already rejects file directives. Do not
                # bypass that source boundary or silently discard a directive.
                replacements[card.id] = (text, empty)
                if empty and moved_targets:
                    # Keep non-data source comments once when the old block
                    # becomes empty; directives still fail replacement below.
                    comments = [_ensure_newline(lines[index], owner.newline)
                                for index in range(card.start + 1, card.stop) if index not in card.data]
                    transfers[moved_targets[0]][0:0] = comments
        for card_id, (text, empty) in replacements.items():
            try:
                state = resource.replaced_state(card_id, text)
                resource.restore(resource.deleted_state(card_id) if empty else state)
            except PrepError as exc:
                raise PrepError(layout_error_code, "The affected card layout is not supported by the existing native replacement contract.",
                                {"resource_id": owner.id, "card_id": card_id, "reason": exc.message}) from exc
        if added_nodes_by_res.get(owner.id) and not emitted_added_nodes:
            extra_blocks.append(f"/NODE{owner.newline}" + "".join(
                _format_node_row(node, owner.newline) for node in added_nodes_by_res[owner.id]))
        for cell in added_cells_by_res.get(owner.id, ()):
            if cell.ref in emitted_added_cells:
                continue
            target = session._part_native_references(cell.part.local_id)[2]["native_part_id"]
            transfers.setdefault((cell.family, target), []).append(_format_cell_row(cell, owner.newline))
        if transfers or extra_blocks:
            blocks = extra_blocks + [f"/{family}/{part}{owner.newline}" + "".join(rows)
                                     for (family, part), rows in transfers.items()]
            state, _ = resource.inserted_states(blocks)
            resource.restore(state)
        if replacements or transfers or extra_blocks:
            states[owner.id] = resource.snapshot()
    states[session._relations_resource().id] = session._mesh_edit_relations(candidate)
    return states



def project_native_mesh_edit(session, candidate, states):
    """Evaluate explicit future correspondence, without publishing it."""
    planned = session._planning_snapshot()
    for rid, state in states.items():
        if rid != session._relations_resource().id:
            planned.document.resources[rid].restore(state)
    planned._projection_cache = None
    planned._projection_index = {}
    mapping = dict(candidate.merge_map)
    split_map = dict(candidate.split_cells)
    removed_nodes, removed_cells = set(candidate.removed_nodes), set(candidate.removed_cells)
    live_parts = {cell.part for cell in candidate.iter_cells()}
    part_changes = {cell.ref for cell in candidate.cell_updates if cell.part != candidate.base._cells[cell.ref].part}
    correspondences, coalescences = [], []
    for group in candidate.base.sets:
        if group.member_kind != "node" and not removed_cells and not part_changes:
            continue
        dropped = tuple(ref for ref in group.members if (
            (group.member_kind == "node" and ref in removed_nodes and ref not in mapping)
            or (group.member_kind == "element" and ref in removed_cells and ref not in split_map)
            or (group.member_kind == "part" and ref not in live_parts)))
        mapped = []
        mapping_rows = []
        for ref in group.members:
            if ref in dropped:
                continue
            if group.member_kind == "element" and ref in split_map:
                children = split_map[ref]
                mapped.extend(children)
                mapping_rows.append({"before": asdict(ref), "proposed": [asdict(child) for child in children]})
            else:
                target_ref = mapping.get(ref, ref)
                mapped.append(target_ref)
                mapping_rows.append({"before": asdict(ref), "proposed": asdict(target_ref)})
        proposed = tuple(dict.fromkeys(mapped))
        if dropped and not proposed:
            raise PrepError("empty_projected_target", "The mesh change would leave an explicit target empty. Deleting its group or condition together is not supported.",
                            {"group_ref": asdict(group.ref), "dropped_members": [asdict(ref) for ref in dropped]})
        if len(proposed) != len(mapped):
            coalescences.append({"group_ref": asdict(group.ref), "old_link_count": len(mapped),
                "projected_unique_count": len(proposed), "scope": "trial only; explicit reviewed coalescence is required at reconnection"})
        row = {"group_ref": asdict(group.ref), "mapping": mapping_rows}
        if removed_cells or part_changes:
            row.update(proposed_members=[asdict(ref) for ref in proposed], dropped_members=[asdict(ref) for ref in dropped],
                       scope="surviving membership proposal only; original declaration stays stale until explicit mapping/Drop")
        correspondences.append(row)
        if proposed != group.members:
            if group.member_kind == "part":
                owner = planned._find_card(group.ref.local_id)
                identifiers = planned._surface_part_ids([ref.local_id for ref in proposed])
                state = explicit_member_state(owner, group.ref.local_id, identifiers)
            else:
                owner, _, _, state = planned._group_members_state(group.ref.local_id, [asdict(ref) for ref in proposed])
            if state is not None:
                owner.restore(state)
                planned._projection_cache = None
                planned._projection_index = {}
    after = planned._mesh_edit_snapshot()
    if ({node.ref: node.xyz for node in after.nodes} != {node.ref: node.xyz for node in candidate.iter_nodes()}
            or {cell.ref: cell for cell in after.cells} != {cell.ref: cell for cell in candidate.iter_cells()}):
        raise PrepError("native_merge_mismatch", "The rendered native nodes or elements do not match the reviewed mesh candidate.")
    support_check_refs = part_changes | {cell.ref for cell in candidate.added_cells}
    if support_check_refs:
        view = planned.mesh_view()
        projection = {**view, "cells": [cell for cell in view["cells"]
            if edits.Ref(cell["resource_id"], "element", cell["id"]) in support_check_refs]}
        affected_cells_for_support = [cell for cell in (*candidate.cell_updates, *candidate.added_cells)
                                      if cell.ref in support_check_refs]
        nodes = sorted({node.local_id for cell in affected_cells_for_support for node in cell.nodes})
        support = node_support(planned._deck_resources(), projection, nodes)
        if len(projection["cells"]) != len(support_check_refs) or any(row["status"] != "supported" for row in support):
            raise PrepError("unsupported_part_profile", "The moved elements need a supported target PART/property/formulation.",
                            {"node_support": support})
    conditions, overlaps, blocked = session._group_member_conditions(candidate, planned, after_snapshot=after)
    return conditions, overlaps, blocked, correspondences, coalescences

