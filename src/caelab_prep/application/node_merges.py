"""Explicit native node merges; target reconnection remains a separate command."""
from dataclasses import asdict
from uuid import uuid4

from ..cae_core import PrepError
from . import mesh_edit_candidates as edits
from .native_mesh_edit import native_mesh_edit_states, project_native_mesh_edit


class NodeMergeCommands:
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
                states = native_mesh_edit_states(self, candidate, layout_error_code="unsupported_merge_layout")
                conditions, overlaps, blocked, correspondences, coalescences = project_native_mesh_edit(self, candidate, states)
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
            change = self.dispatcher.execute_many(native_mesh_edit_states(self, candidate, layout_error_code="unsupported_merge_layout"),
                "Merge explicitly mapped native nodes", expected_revision=self.document.revision, kind="structure")
            if getattr(self, "_node_merge_plan", None) is plan:
                self._node_merge_plan = None
            return {**self.describe(), "change": change.to_dict(), "mesh_relationships": self.mesh_relationships()}

    def cancel_node_merge(self, plan_id):
        with self._lock:
            plan = getattr(self, "_node_merge_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._node_merge_plan = None
