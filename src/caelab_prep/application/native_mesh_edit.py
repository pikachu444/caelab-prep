"""Existing native slot edits and trial target review shared by mesh commands."""
from copy import copy
from dataclasses import asdict

from ..cae_core import PrepError
from ..radioss.assembly import ELEMENTS
from ..radioss.modeling import integer
from . import mesh_edit_candidates as edits
from .mesh_relations import explicit_member_state


def native_mesh_edit_states(session, candidate, *, layout_error_code):
    removals = set(candidate.removed_nodes)
    removed_cells = set(candidate.removed_cells)
    updates = {cell.ref: cell for cell in candidate.cell_updates}
    states = {}
    for owner in session._deck_resources():
        resource = copy(owner)
        replacements = {}
        lines = owner.render().decode("latin1").splitlines(keepends=True)
        for card in owner.cards:
            family = card.keyword.upper().strip("/").split("/")[0]
            if family != "NODE" and family not in ELEMENTS:
                continue
            changed = {}
            for row in card.data:
                identifier = int(lines[row][:10])
                ref = edits.Ref(owner.id, "node" if family == "NODE" else "element", identifier)
                if family == "NODE":
                    if ref in removals: changed[row] = None
                elif ref in removed_cells:
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
                    changed[row] = body + ending
            if changed:
                text = "".join(changed.get(row, lines[row]) or "" for row in range(card.start, card.stop))
                # Full-card replacement already rejects file directives. Do not
                # bypass that source boundary or silently discard a directive.
                replacements[card.id] = (text, all(changed.get(row, lines[row]) is None for row in card.data))
        for card_id, (text, empty) in replacements.items():
            try:
                state = resource.replaced_state(card_id, text)
                resource.restore(resource.deleted_state(card_id) if empty else state)
            except PrepError as exc:
                raise PrepError(layout_error_code, "The affected card layout is not supported by the existing native replacement contract.",
                                {"resource_id": owner.id, "card_id": card_id, "reason": exc.message}) from exc
        if replacements:
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
    removed_nodes, removed_cells = set(candidate.removed_nodes), set(candidate.removed_cells)
    live_parts = {cell.part for cell in candidate.iter_cells()}
    correspondences, coalescences = [], []
    for group in candidate.base.sets:
        if group.member_kind != "node" and not removed_cells:
            continue
        dropped = tuple(ref for ref in group.members if (
            (group.member_kind == "node" and ref in removed_nodes and ref not in mapping)
            or (group.member_kind == "element" and ref in removed_cells)
            or (group.member_kind == "part" and ref not in live_parts)))
        mapped = tuple(mapping.get(ref, ref) for ref in group.members if ref not in dropped)
        proposed = tuple(dict.fromkeys(mapped))
        if dropped and not proposed:
            raise PrepError("empty_projected_target", "Deletion would leave an explicit target empty. Deleting its group or condition together is not supported.",
                            {"group_ref": asdict(group.ref), "dropped_members": [asdict(ref) for ref in dropped]})
        if len(proposed) != len(mapped):
            coalescences.append({"group_ref": asdict(group.ref), "old_link_count": len(mapped),
                "projected_unique_count": len(proposed), "scope": "trial only; explicit reviewed coalescence is required at reconnection"})
        row = {"group_ref": asdict(group.ref), "mapping": [
            {"before": asdict(ref), "proposed": asdict(mapping.get(ref, ref))} for ref in group.members if ref not in dropped]}
        if removed_cells:
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
    conditions, overlaps, blocked = session._group_member_conditions(candidate, planned, after_snapshot=after)
    return conditions, overlaps, blocked, correspondences, coalescences

