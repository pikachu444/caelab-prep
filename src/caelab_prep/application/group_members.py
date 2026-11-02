"""Explicit group-membership review; the existing native edit owns publication."""
from dataclasses import asdict
from uuid import uuid4

from ..cae_core import PrepError
from . import mesh_edit_candidates as edits


def _refs(values):
    return [asdict(value) for value in sorted(values)]


class GroupMemberCommands:
    def plan_group_members(self, card_id, members, *, expected_revision=None, expected_document_id=None):
        """Review a node/element set in the existing closed mesh-edit profile."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            try:
                snapshot = self._mesh_edit_snapshot()
                owner, card, _, state = self._group_members_state(card_id, members)
                if state is None:
                    raise PrepError("no_change", "The group membership is unchanged.")
                planned = self._planning_snapshot()
                planned.document.resources[owner.id].restore(state)
                planned._projection_cache = None
                planned._projection_index = {}
                membership = planned.group_members(card_id)
                if membership["diagnostics"]:
                    raise PrepError("incomplete_mesh_references", "The proposed group cannot be resolved completely.",
                                    {"diagnostics": membership["diagnostics"]})
                proposed = tuple(edits.Ref(**ref) for ref in membership["members"])
                group_ref = edits.Ref(owner.id, "set", card_id)
                candidate = edits.reassign_set(snapshot, group_ref, proposed)
                conditions, overlaps, blocked = self._group_member_conditions(candidate, planned)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc), {"details": exc.details}) from exc
            except (KeyError, ValueError, TypeError, IndexError) as exc:
                raise PrepError("invalid_group_members", "The membership preview could not be resolved.", {"reason": str(exc)}) from exc
            old = snapshot._sets[group_ref].members
            plan_id = str(uuid4())
            self._group_member_plan = (plan_id, candidate, not blocked)
            return {"plan_id": plan_id, "document_id": self.document.id, "revision": self.document.revision,
                    "document_epoch": self._document_epoch, "group_ref": asdict(group_ref),
                    "native_family": "/".join(card.keyword.upper().strip("/").split("/")[:2]),
                    "title": card.title, "before": _refs(old), "after": _refs(proposed),
                    "added": _refs(set(proposed) - set(old)), "removed": _refs(set(old) - set(proposed)),
                    "impacts": [asdict(impact) for impact in candidate.impacts],
                    "conditions": conditions, "initial_velocity_overlaps": overlaps,
                    "admissible": not blocked, "blocked": blocked,
                    "geometry": "unchanged; no quality retest or mesh generation change",
                    "resource_names": {resource.id: self._paths.get(resource.id, resource.id) for resource in self._deck_resources()},
                    "scope": "explicit membership review; not physical response or constraint sufficiency"}

    def _group_member_conditions(self, candidate, planned):
        snapshot = candidate.base
        changes = {group.ref: group for group in candidate.set_updates}
        affected = {impact.target for impact in candidate.impacts}
        groups = {group.ref.local_id: group for group in snapshot.sets}

        def nodes(group, after):
            group = changes.get(group.ref, group) if after else group
            return edits._members_as_nodes(snapshot, group)

        conditions, blocked, velocities = [], [], []
        for use in snapshot.uses:
            owner = self._find_card(use.ref.local_id)
            card = owner.card(use.ref.local_id)
            family = "/".join(card.keyword.upper().strip("/").split("/")[:2])
            values = self.condition_values(card.id)
            if family == "INIVEL/TRA":
                group = groups[values["group_id"]]
                velocities.append((card.id, nodes(group, False), nodes(group, True),
                    {"resource_id": owner.id, "card_start": card.start,
                     "scope": "within resource; INCLUDE expansion order not evaluated"}))
            if use.ref not in affected:
                continue
            roles = []
            for key, role in (("group_id", "group"), ("secondary_group_id", "secondary"), ("main_surface_id", "main")):
                if key not in values:
                    continue
                group = groups[values[key]]
                after_group = changes.get(group.ref, group)
                before_nodes, after_nodes = nodes(group, False), nodes(group, True)
                roles.append({"role": role, "group_ref": asdict(group.ref), "member_kind": group.member_kind,
                              "before": _refs(group.members), "after": _refs(after_group.members),
                              "before_nodes": _refs(before_nodes), "after_nodes": _refs(after_nodes)})
            before_support = self.condition_support(card.id)
            after_support = planned.condition_support(card.id)
            after_values = planned.condition_values(card.id)
            failures = after_support["diagnostics"]
            bcs_inactive_only = family.startswith("BCS/") and failures and all(
                diagnostic.get("code") == "inactive_rotation" for diagnostic in failures)
            diagnostics = list(after_values["diagnostics"])
            if after_support["status"] not in ("supported", "not-applicable") and not bcs_inactive_only:
                diagnostics.extend(failures)
            reference_checks = {"before": [], "after": []}
            if family == "INTER/TYPE7":
                for phase, session, declaration in (("before", self, values), ("after", planned, after_values)):
                    for role, check, target in (("secondary", session._group_reference, declaration["secondary_group_id"]),
                                                ("main", session._surface_reference, declaration["main_surface_id"])):
                        try: check(target)
                        except PrepError as exc:
                            reference_checks[phase].append({"role": role, "code": exc.code, "message": exc.message})
                diagnostics.extend(reference_checks["after"])
            row = {"reference": asdict(use.ref), "keyword": card.keyword, "title": card.title,
                   "declaration": values, "roles": roles, "before_support": before_support,
                   "after_support": after_support, "reference_checks": reference_checks}
            if use.kind == "load":
                old_nodes = set().union(*(nodes(groups[ref.local_id], False) for ref in use.targets))
                new_nodes = set().union(*(nodes(groups[ref.local_id], True) for ref in use.targets))
                try:
                    row["load_coefficients"] = {"before": self._mesh_load_coefficients(card.id, old_nodes),
                                                "after": planned._mesh_load_coefficients(card.id, new_nodes)}
                except PrepError as exc:
                    row["load_coefficients"] = None
                    diagnostic = {"code": exc.code, "message": exc.message, "field": "direction"}
                    if diagnostic not in diagnostics: diagnostics.append(diagnostic)
            if diagnostics:
                blocked.append({"condition_id": card.id, "keyword": card.keyword, "diagnostics": diagnostics})
            conditions.append(row)
        changed_conditions = {row["reference"]["local_id"] for row in conditions}
        overlaps = []
        for index, first in enumerate(velocities):
            for second in velocities[index + 1:]:
                if not {first[0], second[0]} & changed_conditions:
                    continue
                before, after = first[1] & second[1], first[2] & second[2]
                if before or after:
                    overlaps.append({"conditions": [first[0], second[0]], "before_nodes": _refs(before),
                                     "after_nodes": _refs(after), "source_positions": [first[3], second[3]],
                                     "effective_initial_state": "not_evaluated; native record order matters"})
        return conditions, overlaps, blocked

    def apply_group_members(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_group_member_plan", None)
            if plan is None or plan[0] != plan_id:
                raise PrepError("stale_mesh_candidate", "Prepare a fresh group membership preview.")
            _, candidate, admissible = plan
            try:
                candidate.assert_current(self._mesh_edit_stamp(), self._mesh_edit_snapshot().digest)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            if not admissible:
                raise PrepError("unsupported_group_members", "The proposed membership has unsupported condition targets; inspect the preview diagnostics.")
            group = candidate.set_updates[0]
            result = self.set_group_members(group.ref.local_id, [asdict(ref) for ref in group.members],
                expected_revision=self.document.revision, expected_document_id=self.document.id)
            # A synchronous subscriber may already have prepared the next review.
            if getattr(self, "_group_member_plan", None) is plan:
                self._group_member_plan = None
            return result

    def cancel_group_members(self, plan_id):
        with self._lock:
            plan = getattr(self, "_group_member_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._group_member_plan = None
