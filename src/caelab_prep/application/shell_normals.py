"""Explicit shell winding changes using the existing native mesh contracts."""
from dataclasses import asdict
from uuid import uuid4

from ..cae_core import PrepError
from ..radioss.relations import node_support
from . import mesh_edit_candidates as edits
from .native_mesh_edit import native_mesh_edit_states, project_native_mesh_edit


class ShellNormalCommands:
    def plan_shell_normal_flip(self, references, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            try:
                if not isinstance(references, (list, tuple)) or not references:
                    raise PrepError("invalid_shell_selection", "Choose explicit source-qualified shell elements.")
                if any(not isinstance(ref, dict) or set(ref) != {"resource_id", "entity_kind", "local_id"}
                       for ref in references):
                    raise PrepError("invalid_shell_selection", "Each shell needs its source, element kind and native ID.")
                snapshot = self._mesh_edit_snapshot()
                candidate = edits.flip_shell_normals(snapshot, tuple(edits.Ref(**ref) for ref in references))
                selected = {cell.ref for cell in candidate.cell_updates}
                view = self.mesh_view()
                # Reuse the mechanical profile on the selected shells, including
                # their real PART/property assignment and explicit formulation.
                projection = {**view, "cells": [cell for cell in view["cells"]
                    if edits.Ref(cell["resource_id"], "element", cell["id"]) in selected]}
                nodes = sorted({node.local_id for cell in candidate.cell_updates for node in cell.nodes})
                support = node_support(self._deck_resources(), projection, nodes)
                if len(projection["cells"]) != len(selected) or any(row["status"] != "supported" for row in support):
                    raise PrepError("unsupported_shell_profile", "Resolve the selected shell property/formulation before reversing its winding.",
                                    {"node_support": support})
                states = native_mesh_edit_states(self, candidate, layout_error_code="unsupported_shell_flip_layout")
                conditions, overlaps, blocked, _, _ = project_native_mesh_edit(self, candidate, states)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc), {"details": exc.details}) from exc
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise PrepError("invalid_shell_selection", "The selected native shells could not be resolved.",
                                {"reason": str(exc)}) from exc
            plan_id = str(uuid4())
            self._shell_normal_plan = (plan_id, candidate, not blocked)
            return {"plan_id": plan_id, "document_id": self.document.id, "revision": self.document.revision,
                "document_epoch": self._document_epoch,
                "cells": [{"reference": asdict(cell.ref), "family": cell.family,
                           "before": asdict(candidate.base._cells[cell.ref]), "proposed": asdict(cell)}
                          for cell in candidate.cell_updates],
                "quality_before": [asdict(value) for value in candidate.quality_before],
                "quality_after": [asdict(value) for value in candidate.quality_after],
                "impacts": [asdict(value) for value in candidate.impacts],
                "conditions": conditions, "initial_velocity_overlaps": overlaps,
                "stale_targets": states[self._relations_resource().id]["stale_targets"],
                "admissible": not blocked, "blocked": blocked,
                "resource_names": {resource.id: self._paths.get(resource.id, resource.id) for resource in self._deck_resources()},
                "scope": "Explicit SH3N/planar SHELL winding reversal. In-plane axes also change. Thickness and stored angles, contact roles and load values are preserved; physical response is not certified."}

    def apply_shell_normal_flip(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_shell_normal_plan", None)
            if plan is None or plan[0] != plan_id:
                raise PrepError("stale_mesh_candidate", "Prepare a fresh shell orientation preview.")
            _, candidate, admissible = plan
            try:
                candidate.assert_current(self._mesh_edit_stamp(), self._mesh_edit_snapshot().digest)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            if not admissible:
                raise PrepError("unsupported_shell_targets", "Resolve the affected condition targets before reversing shells.")
            change = self.dispatcher.execute_many(
                native_mesh_edit_states(self, candidate, layout_error_code="unsupported_shell_flip_layout"),
                "Reverse selected shell winding", expected_revision=self.document.revision, kind="structure")
            if getattr(self, "_shell_normal_plan", None) is plan:
                self._shell_normal_plan = None
            return {**self.describe(), "change": change.to_dict(), "mesh_relationships": self.mesh_relationships()}

    def cancel_shell_normal_flip(self, plan_id):
        with self._lock:
            plan = getattr(self, "_shell_normal_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._shell_normal_plan = None
