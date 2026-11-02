"""Explicit native node merges; target reconnection remains a separate command."""
from copy import copy
from dataclasses import asdict
from uuid import uuid4

from ..cae_core import PrepError
from ..radioss.assembly import ELEMENTS
from ..radioss.modeling import integer
from . import mesh_edit_candidates as edits


class NodeMergeCommands:
    def _native_node_merge_states(self, candidate):
        removals = set(candidate.removed_nodes)
        updates = {cell.ref: cell for cell in candidate.cell_updates}
        states = {}
        for owner in self._deck_resources():
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
                    elif ref in updates:
                        cell = updates[ref]
                        if cell.family != family:
                            raise PrepError("invalid_mesh_candidate", "A merge cannot change element family.")
                        text = lines[row]
                        body = text.rstrip("\r\n")
                        ending = text[len(body):]
                        fields = [(index, node.local_id) for index, node in enumerate(cell.nodes, 1)]
                        if family == "BEAM" and cell.orientation_node is not None:
                            fields.append((3, cell.orientation_node.local_id))
                        for index, value in fields:
                            start = index * 10
                            body = body[:start].ljust(start) + integer(value) + body[start + 10:]
                        changed[row] = body + ending
                if changed:
                    text = "".join(changed.get(row, lines[row]) or "" for row in range(card.start, card.stop))
                    # Full-card replacement already rejects file directives. Do not
                    # bypass that source boundary or silently discard a directive.
                    replacements[card.id] = text
            for card_id, text in replacements.items():
                try:
                    resource.restore(resource.replaced_state(card_id, text))
                except PrepError as exc:
                    raise PrepError("unsupported_merge_layout", "The affected card layout is not supported by the existing native replacement contract.",
                                    {"resource_id": owner.id, "card_id": card_id, "reason": exc.message}) from exc
            if replacements:
                states[owner.id] = resource.snapshot()
        states[self._relations_resource().id] = self._mesh_edit_relations(candidate)
        return states

    def _project_node_merge(self, candidate, states):
        """Evaluate explicit future correspondence, without publishing it."""
        planned = self._planning_snapshot()
        for rid, state in states.items():
            if rid != self._relations_resource().id:
                planned.document.resources[rid].restore(state)
        planned._projection_cache = None
        planned._projection_index = {}
        mapping = dict(candidate.merge_map)
        correspondences, coalescences = [], []
        for group in candidate.base.sets:
            if group.member_kind != "node":
                continue
            mapped = tuple(mapping.get(ref, ref) for ref in group.members)
            proposed = tuple(dict.fromkeys(mapped))
            if len(proposed) != len(mapped):
                coalescences.append({"group_ref": asdict(group.ref), "old_link_count": len(mapped),
                    "projected_unique_count": len(proposed), "scope": "trial only; explicit reviewed coalescence is required at reconnection"})
            correspondences.append({"group_ref": asdict(group.ref),
                "mapping": [{"before": asdict(before), "proposed": asdict(after)} for before, after in zip(group.members, mapped)]})
            if proposed != group.members:
                owner, _, _, state = planned._group_members_state(group.ref.local_id, [asdict(ref) for ref in proposed])
                if state is not None:
                    owner.restore(state)
                    planned._projection_cache = None
                    planned._projection_index = {}
        after = planned._mesh_edit_snapshot()
        if ({node.ref: node.xyz for node in after.nodes} != {node.ref: node.xyz for node in candidate.iter_nodes()}
                or {cell.ref: cell for cell in after.cells} != {cell.ref: cell for cell in candidate.iter_cells()}):
            raise PrepError("native_merge_mismatch", "The rendered native nodes or elements do not match the reviewed merge candidate.")
        conditions, overlaps, blocked = self._group_member_conditions(candidate, planned, after_snapshot=after)
        return conditions, overlaps, blocked, correspondences, coalescences

    def plan_node_merge(self, mapping, *, tolerance, length_unit, approvals=(), expected_revision=None, expected_document_id=None):
        """Review exact scoped source/keeper pairs, not an automatic nearest search."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            try:
                if not isinstance(mapping, (list, tuple)) or not mapping:
                    raise PrepError("invalid_merge_map", "Provide explicit source and keeper references.")
                pairs = {}
                for row in mapping:
                    if not isinstance(row, dict) or set(row) != {"source", "keeper"}:
                        raise PrepError("invalid_merge_map", "Each pair requires exact source and keeper references.")
                    source, keeper = edits.Ref(**row["source"]), edits.Ref(**row["keeper"])
                    if source in pairs:
                        raise PrepError("invalid_merge_map", "Each source may appear only once.")
                    pairs[source] = keeper
                if not isinstance(approvals, (list, tuple)):
                    raise PrepError("invalid_merge_approval", "Provide exact per-pair boundary approvals.")
                permissions = []
                for row in approvals:
                    if not isinstance(row, dict) or set(row) != {"source", "keeper", "cross_parts", "contacts", "cross_resources"}:
                        raise PrepError("invalid_merge_approval", "Each boundary approval needs its exact pair, PART/resource flags and contact references.")
                    permissions.append(edits.MergeApproval(edits.Ref(**row["source"]), edits.Ref(**row["keeper"]),
                        row["cross_parts"], tuple(edits.Ref(**ref) for ref in row["contacts"]), row["cross_resources"]))
                candidate = edits.merge_nodes(self._mesh_edit_snapshot(), pairs, tolerance=tolerance,
                    length_unit=length_unit, approvals=tuple(permissions))
                states = self._native_node_merge_states(candidate)
                conditions, overlaps, blocked, correspondences, coalescences = self._project_node_merge(candidate, states)
            except edits.MeshEditError as exc:
                if exc.code == "component_boundary":
                    raise PrepError("part_boundary", "Cross-PART merge requires permission for this exact source and keeper pair.", {"details": exc.details}) from exc
                raise PrepError(exc.code, str(exc), {"details": exc.details}) from exc
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise PrepError("invalid_merge_map", "The native merge could not be resolved.", {"reason": str(exc)}) from exc
            plan_id = str(uuid4())
            self._node_merge_plan = (plan_id, candidate, not blocked)
            return {"plan_id": plan_id, "document_id": self.document.id, "revision": self.document.revision,
                "document_epoch": self._document_epoch, "length_unit": length_unit, "tolerance": tolerance,
                "mapping": [{"source": asdict(source), "keeper": asdict(keeper),
                             "source_position": list(candidate.base._nodes[source].xyz), "keeper_position": list(candidate.base._nodes[keeper].xyz)}
                            for source, keeper in candidate.merge_map],
                "cells": [{"reference": asdict(cell.ref), "family": cell.family,
                           "before": asdict(candidate.base._cells[cell.ref]), "proposed": asdict(cell)} for cell in candidate.cell_updates],
                "quality_before": [asdict(value) for value in candidate.quality_before],
                "quality_after": [asdict(value) for value in candidate.quality_after],
                "impacts": [asdict(value) for value in candidate.impacts], "conditions": conditions,
                "initial_velocity_overlaps": overlaps, "projected_correspondences": correspondences,
                "membership_coalescences": coalescences,
                "stale_targets": states[self._relations_resource().id]["stale_targets"],
                "admissible": not blocked, "blocked": blocked,
                "resource_names": {resource.id: self._paths.get(resource.id, resource.id) for resource in self._deck_resources()},
                "scope": "Explicit topology edit. Correspondence projections are not applied; local frames and physical response are not preserved by assertion."}

    def apply_node_merge(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_node_merge_plan", None)
            if plan is None or plan[0] != plan_id:
                raise PrepError("stale_mesh_candidate", "Prepare a fresh explicit merge preview.")
            _, candidate, admissible = plan
            try:
                candidate.assert_current(self._mesh_edit_stamp(), self._mesh_edit_snapshot().digest)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            if not admissible:
                raise PrepError("unsupported_merge_targets", "Inspect the projected condition targets before merging.")
            change = self.dispatcher.execute_many(self._native_node_merge_states(candidate),
                "Merge explicitly mapped native nodes", expected_revision=self.document.revision, kind="structure")
            if getattr(self, "_node_merge_plan", None) is plan:
                self._node_merge_plan = None
            return {**self.describe(), "change": change.to_dict(), "mesh_relationships": self.mesh_relationships()}

    def cancel_node_merge(self, plan_id):
        with self._lock:
            plan = getattr(self, "_node_merge_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._node_merge_plan = None
