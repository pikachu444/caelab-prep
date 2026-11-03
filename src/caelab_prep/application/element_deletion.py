"""Explicit native element deletion with the existing candidate and document owner."""
from dataclasses import asdict
from uuid import uuid4

from ..cae_core import PrepError
from . import mesh_edit_candidates as edits
from .native_mesh_edit import native_mesh_edit_states, project_native_mesh_edit


class ElementDeletionCommands:
    def plan_element_deletion(self, references, *, orphan_policy, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            try:
                if (not isinstance(references, (list, tuple)) or not references
                        or any(not isinstance(ref, dict) or set(ref) != {"resource_id", "entity_kind", "local_id"} for ref in references)):
                    raise PrepError("invalid_element_selection", "Choose explicit source-qualified element references.")
                snapshot = self._mesh_edit_snapshot()
                candidate = edits.delete_elements(snapshot, tuple(edits.Ref(**ref) for ref in references), orphan_policy=orphan_policy)
                states = native_mesh_edit_states(self, candidate, layout_error_code="unsupported_deletion_layout")
                conditions, overlaps, blocked, correspondences, _ = project_native_mesh_edit(self, candidate, states)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc), {"details": exc.details}) from exc
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise PrepError("invalid_element_selection", "The selected elements could not be resolved.", {"reason": str(exc)}) from exc
            plan_id = str(uuid4())
            self._element_deletion_plan = (plan_id, candidate, not blocked)
            return {"plan_id": plan_id, "document_id": self.document.id, "revision": self.document.revision,
                "document_epoch": self._document_epoch, "orphan_policy": candidate.orphan_policy,
                "removed_cells": [asdict(snapshot._cells[ref]) for ref in candidate.removed_cells],
                "removed_nodes": [asdict(ref) for ref in candidate.removed_nodes],
                "new_orphans": [asdict(ref) for ref in candidate.new_orphans],
                "quality_before": [asdict(row) for row in candidate.quality_before],
                "quality_after": [asdict(row) for row in candidate.quality_after],
                "impacts": [asdict(row) for row in candidate.impacts],
                "conditions": conditions, "initial_velocity_overlaps": overlaps, "projected_memberships": correspondences,
                "stale_targets": states[self._relations_resource().id]["stale_targets"], "admissible": not blocked, "blocked": blocked,
                "resource_names": {r.id: self._paths.get(r.id, r.id) for r in self._deck_resources()},
                "scope": "Explicit element deletion; keep or delete only newly orphaned nodes. Original targets remain stale. Mass, momentum, energy and contact segments may change; physical response is not certified."}

    def apply_element_deletion(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_element_deletion_plan", None)
            if plan is None or plan[0] != plan_id:
                raise PrepError("stale_mesh_candidate", "Prepare a fresh element deletion preview.")
            _, candidate, admissible = plan
            try:
                candidate.assert_current(self._mesh_edit_stamp(), self._mesh_edit_snapshot().digest)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            if not admissible:
                raise PrepError("unsupported_deletion_targets", "The surviving target proposal has unsupported mechanical fields; inspect the preview.")
            change = self.dispatcher.execute_many(
                native_mesh_edit_states(self, candidate, layout_error_code="unsupported_deletion_layout"),
                "Delete selected elements", expected_revision=self.document.revision, kind="structure")
            if getattr(self, "_element_deletion_plan", None) is plan:
                self._element_deletion_plan = None
            return {**self.describe(), "change": change.to_dict(), "mesh_relationships": self.mesh_relationships()}

    def cancel_element_deletion(self, plan_id):
        with self._lock:
            plan = getattr(self, "_element_deletion_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._element_deletion_plan = None
