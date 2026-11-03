"""Explicit element ownership changes through existing native states and targets."""
from dataclasses import asdict, replace
from uuid import uuid4

from ..cae_core import PrepError
from . import mesh_edit_candidates as edits
from .native_mesh_edit import native_mesh_edit_states, project_native_mesh_edit


class PartReassignmentCommands:
    def _part_reassignment_snapshot(self, targets):
        snapshot = self._mesh_edit_snapshot()
        parts = dict(snapshot._parts)
        # Coarse routing follows the existing PART assignment family boundary.
        # Actual fields/formulations are checked on moved cells by node_support
        # in the rendered trial, including for a previously empty target PART.
        families = {"SHELL": ("SHELL", "SH3N"), "TYPE1": ("SHELL", "SH3N"),
                    "BEAM": ("BEAM",), "TYPE3": ("BEAM",), "TRUSS": ("TRUSS",), "TYPE2": ("TRUSS",),
                    "SOLID": ("TETRA4", "BRICK"), "TYPE14": ("TETRA4", "BRICK")}
        for ref in sorted(set(targets)):
            owner, card, _ = self._unique_card(ref.local_id, "PART")
            if owner.id != ref.resource_id:
                raise PrepError("invalid_part_assignment", "The target PART belongs to a different resource.")
            assignment = self.part_assignments(ref.local_id)
            if assignment["diagnostics"]:
                raise PrepError("invalid_part_assignment", "Resolve the target PART material/property references first.")
            prop_owner = self._find_card(assignment["property_id"])
            family = prop_owner.card(assignment["property_id"]).keyword.upper().strip("/").split("/")[1]
            if family not in families:
                raise PrepError("unsupported_part_profile", "The target PART property family is outside the native ownership profile.")
            parts[ref] = edits.Part(ref, card.id, families[family], card.keyword)
        return replace(snapshot, parts=tuple(parts.values()))

    def plan_part_reassignment(self, assignments, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            try:
                if not isinstance(assignments, (list, tuple)) or not assignments:
                    raise PrepError("invalid_part_assignment", "Choose explicit element-to-PART assignments.")
                mapping = {}
                for row in assignments:
                    if not isinstance(row, dict) or set(row) != {"element", "part"}:
                        raise PrepError("invalid_part_assignment", "Each assignment requires a scoped element and PART reference.")
                    if any(not isinstance(row[key], dict) or set(row[key]) != {"resource_id", "entity_kind", "local_id"} for key in row):
                        raise PrepError("invalid_part_assignment", "Each reference requires resource, kind and local identity.")
                    element, part = edits.Ref(**row["element"]), edits.Ref(**row["part"])
                    if element in mapping or part.entity_kind != "part":
                        raise PrepError("invalid_part_assignment", "Use one exact PART decision per element.")
                    mapping[element] = part
                targets = tuple(sorted(set(mapping.values())))
                snapshot = self._part_reassignment_snapshot(targets)
                candidate = edits.reassign_parts(snapshot, mapping)
                states = native_mesh_edit_states(self, candidate, layout_error_code="unsupported_part_move_layout")
                conditions, overlaps, blocked, correspondences, _ = project_native_mesh_edit(self, candidate, states)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc), {"details": exc.details}) from exc
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise PrepError("invalid_part_assignment", "The native ownership assignment could not be resolved.", {"reason": str(exc)}) from exc
            plan_id = str(uuid4())
            self._part_reassignment_plan = (plan_id, candidate, not blocked, targets)
            return {"plan_id": plan_id, "document_id": self.document.id, "revision": self.document.revision,
                "document_epoch": self._document_epoch,
                "cells": [{"reference": asdict(cell.ref), "family": cell.family,
                    "before": asdict(snapshot._cells[cell.ref]), "proposed": asdict(cell),
                    "before_assignment": self.part_assignments(snapshot._cells[cell.ref].part.local_id),
                    "proposed_assignment": self.part_assignments(cell.part.local_id)} for cell in candidate.cell_updates],
                "quality_before": [asdict(row) for row in candidate.quality_before],
                "quality_after": [asdict(row) for row in candidate.quality_after],
                "conditions": conditions, "initial_velocity_overlaps": overlaps, "projected_memberships": correspondences,
                "impacts": [asdict(row) for row in candidate.impacts],
                "stale_targets": states[self._relations_resource().id]["stale_targets"], "admissible": not blocked, "blocked": blocked,
                "resource_names": {r.id: self._paths.get(r.id, r.id) for r in self._deck_resources()},
                "scope": "Explicit ownership transfer; native element ID/source, coordinates, connectivity and row suffix stay unchanged. Target material/property and contact segments may change mass, stiffness, momentum, energy and response. Original targets stay stale; no physical equivalence is certified."}

    def apply_part_reassignment(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_part_reassignment_plan", None)
            if plan is None or plan[0] != plan_id:
                raise PrepError("stale_mesh_candidate", "Prepare a fresh PART ownership preview.")
            _, candidate, admissible, targets = plan
            try:
                candidate.assert_current(self._mesh_edit_stamp(), self._part_reassignment_snapshot(targets).digest)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            if not admissible:
                raise PrepError("unsupported_part_targets", "The new ownership has unsupported condition targets; inspect the preview.")
            change = self.dispatcher.execute_many(native_mesh_edit_states(self, candidate, layout_error_code="unsupported_part_move_layout"),
                "Move selected elements to PART", expected_revision=self.document.revision, kind="structure")
            if getattr(self, "_part_reassignment_plan", None) is plan:
                self._part_reassignment_plan = None
            return {**self.describe(), "change": change.to_dict(), "mesh_relationships": self.mesh_relationships()}

    def cancel_part_reassignment(self, plan_id):
        with self._lock:
            plan = getattr(self, "_part_reassignment_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._part_reassignment_plan = None
