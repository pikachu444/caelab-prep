"""Explicit linear SH3N triangle edge split commands using native mesh contracts."""
from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4

from ..cae_core import PrepError, Selection, SelectionRef
from ..radioss.relations import node_support
from . import mesh_edit_candidates as edits
from .native_mesh_edit import mesh_edit_reference, native_mesh_edit_states, project_native_mesh_edit


class EdgeSplitCommands:
    def plan_triangle_edge_split(
        self,
        references,
        edge_nodes,
        *,
        new_node_id=None,
        new_element_ids=None,
        expected_revision=None,
        expected_document_id=None,
    ):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            try:
                if not isinstance(references, (list, tuple)) or not references:
                    raise PrepError("invalid_shell_selection", "Choose 1 or 2 explicit source-qualified SH3N elements.")
                if not isinstance(edge_nodes, (list, tuple)) or len(edge_nodes) != 2:
                    raise PrepError("invalid_edge", "Choose two explicit node references for the edge to split.")
                edge_refs = tuple(mesh_edit_reference(ref, kind="node", code="invalid_edge",
                    message="Invalid split edge node reference.") for ref in edge_nodes)
                if any(card.keyword.upper().startswith("/TRANSFORM") for resource in self._deck_resources() for card in resource.cards):
                    raise PrepError("unsupported_transform", "Edge splitting is not supported when active /TRANSFORM cards exist.")
                snapshot = self._mesh_edit_snapshot()
                elem_refs = tuple(mesh_edit_reference(ref, kind="element", snapshot=snapshot,
                    code="invalid_shell_selection", message="Each selected element needs its source, element kind and native ID.")
                    for ref in references)
                candidate = edits.split_triangle_edge(
                    snapshot,
                    elem_refs,
                    edge_refs,
                    new_node_id=new_node_id,
                    new_element_ids=new_element_ids,
                )
                selected = set(candidate.removed_cells)
                view = self.mesh_view()
                projection = {
                    **view,
                    "cells": [
                        cell
                        for cell in view["cells"]
                        if edits.Ref(cell["resource_id"], "element", cell["id"]) in selected
                    ],
                }
                nodes = sorted({node.local_id for ref in selected for node in snapshot._cells[ref].nodes})
                support = node_support(self._deck_resources(), projection, nodes)
                if len(projection["cells"]) != len(selected) or any(row["status"] != "supported" for row in support):
                    raise PrepError(
                        "unsupported_shell_profile",
                        "Resolve the selected SH3N property/formulation before splitting a triangle edge.",
                        {"node_support": support},
                    )
                states = native_mesh_edit_states(self, candidate, layout_error_code="unsupported_edge_split_layout")
                conditions, overlaps, blocked, correspondences, _ = project_native_mesh_edit(self, candidate, states)
            except PrepError:
                raise
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc), {"details": exc.details}) from exc
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                raise PrepError(
                    "invalid_edge_split",
                    "The selected native SH3N elements or edge could not be resolved.",
                    {"reason": str(exc)},
                ) from exc
            plan_id = str(uuid4())
            self._edge_split_plan = (plan_id, candidate, not blocked)
            return {
                "plan_id": plan_id,
                "document_id": self.document.id,
                "revision": self.document.revision,
                "document_epoch": self._document_epoch,
                "parent_elements": [asdict(ref) for ref in candidate.removed_cells],
                "edge_nodes": [asdict(ref) for ref in edge_refs],
                "added_nodes": [asdict(node) for node in candidate.added_nodes],
                "added_cells": [asdict(cell) for cell in candidate.added_cells],
                "split_cells": [
                    {"parent": asdict(parent), "children": [asdict(child) for child in children]}
                    for parent, children in candidate.split_cells
                ],
                "quality_before": [asdict(value) for value in candidate.quality_before],
                "quality_after": [asdict(value) for value in candidate.quality_after],
                "impacts": [asdict(value) for value in candidate.impacts],
                "conditions": conditions,
                "initial_velocity_overlaps": overlaps,
                "projected_memberships": correspondences,
                "stale_targets": deepcopy(states[self._relations_resource().id]["stale_targets"]),
                "admissible": not blocked,
                "blocked": blocked,
                "resource_names": {resource.id: self._paths.get(resource.id, resource.id) for resource in self._deck_resources()},
                "scope": "Explicit linear SH3N triangle edge split creating one midpoint node and two winding-preserving SH3N child elements per selected parent triangle.",
            }

    def apply_triangle_edge_split(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_edge_split_plan", None)
            if plan is None or plan[0] != plan_id:
                raise PrepError("stale_mesh_candidate", "Prepare a fresh triangle edge split preview.")
            _, candidate, admissible = plan
            try:
                candidate.assert_current(self._mesh_edit_stamp(), self._mesh_edit_snapshot().digest)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            if not admissible:
                raise PrepError("unsupported_edge_split_targets", "Resolve the affected condition targets before splitting triangle edges.")
            selection = self.document.selection
            remap_selection = self._active_target_role is None and not self._part_selection_active
            change = self.dispatcher.execute_many(
                native_mesh_edit_states(self, candidate, layout_error_code="unsupported_edge_split_layout"),
                "Split selected triangle edge",
                expected_revision=self.document.revision,
                kind="structure",
            )
            split_refs = {
                SelectionRef(parent.resource_id, "element", parent.local_id, formulation):
                    tuple(SelectionRef(child.resource_id, "element", child.local_id, "SH3N") for child in children)
                for parent, children in candidate.split_cells for formulation in (None, "SH3N")
            }
            if remap_selection and any(ref in split_refs for ref in selection.refs):
                refs = []
                for previous in selection.refs:
                    for ref in split_refs.get(previous, (previous,)):
                        native, displayed = self._matching_selection_cells(ref.local_id, ref.resource_id, ref.formulation)
                        if len(native) == len(displayed) == 1:
                            refs.append(self._element_selection_ref(displayed[0], formulation=previous.formulation))
                refs = tuple(refs)
                if refs:
                    self.document.selection = Selection("element", tuple(ref.local_id for ref in refs), refs)
                self._active_object = self._element_selection_owner(self.document, refs)
                self._selected_objects = (self._active_object,) if self._active_object is not None else ()
                self._notify("selection")
            if getattr(self, "_edge_split_plan", None) is plan:
                self._edge_split_plan = None
            return {**self.describe(), "change": change.to_dict(), "mesh_relationships": self.mesh_relationships()}

    def cancel_triangle_edge_split(self, plan_id):
        with self._lock:
            plan = getattr(self, "_edge_split_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._edge_split_plan = None
