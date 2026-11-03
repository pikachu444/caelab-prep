"""Declared memberships at a stale boundary; no invented historical geometry."""
from copy import deepcopy

from .group_members import _velocity_overlap_pairs


def reconnection_review(session, trial, links):
    selected = {row["group_id"] for row in links}
    stale_before = session._relations_resource().snapshot()["stale_targets"]
    stale_after = trial._relations_resource().snapshot()["stale_targets"]
    conditions, velocities, unresolved_velocity = [], [], []

    def members(owner, identifier, *, saved=False):
        resource = owner._find_card(identifier)
        card = resource.card(identifier)
        if saved and identifier in stale_before:
            return list(stale_before[identifier]["members"]), stale_before[identifier]["family"]
        return owner._integer_members(resource, card), "/".join(card.keyword.upper().strip("/").split("/")[:2])

    for resource in session._deck_resources():
        for card in resource.cards:
            family = "/".join(card.keyword.upper().strip("/").split("/")[:2])
            if family.split("/")[0] not in ("BCS", "CLOAD", "INIVEL", "INTER"):
                continue
            values = session.condition_values(card.id)
            proposed = trial.condition_values(card.id)
            groups = {key: values[key] for key in ("group_id", "secondary_group_id", "main_surface_id") if key in values}
            if family == "INIVEL/TRA":
                group = values["group_id"]
                old_ids, _ = members(session, group, saved=True); new_ids, _ = members(trial, group)
                new_resource = trial._find_card(card.id); new_card = new_resource.card(card.id)
                velocities.append((card.id, set(old_ids), set(new_ids),
                    {"resource_id": resource.id, "before_card_start": card.start, "after_card_start": new_card.start,
                     "scope": "within resource; INCLUDE expansion order not evaluated"}))
                if group in stale_after: unresolved_velocity.append(group)
            if not selected.intersection(groups.values()):
                continue
            roles = []
            for key, group in groups.items():
                before_ids, group_family = members(session, group, saved=True)
                current_ids, _ = members(session, group)
                after_ids, _ = members(trial, group)
                roles.append({"role": {"group_id": "group", "secondary_group_id": "secondary", "main_surface_id": "main"}[key],
                    "group_id": group, "family": group_family, "old_declared_native_ids": before_ids,
                    "current_declared_native_ids": current_ids,
                    "proposed_native_ids": after_ids, "pending_after": group in stale_after})
            row = {"condition_id": card.id, "keyword": card.keyword, "roles": roles, "declaration": values,
                   "before_support": session.condition_support(card.id), "after_support": trial.condition_support(card.id)}
            if family.split("/")[0] == "CLOAD":
                # Old links remain declared even when the old node no longer exists.
                # Coefficients depend on that stored cardinality, not live survivors.
                old_ids, _ = members(session, values["group_id"], saved=True)
                after_ids, _ = members(trial, proposed["group_id"])
                row["load_coefficients"] = {"before": session._mesh_load_coefficients(card.id, set(old_ids)),
                                            "after": trial._mesh_load_coefficients(card.id, set(after_ids))}
            conditions.append(row)
    changed = {row["condition_id"] for row in conditions}
    overlaps = [{"conditions": [first[0], second[0]], "old_declared_native_ids": sorted(before),
                 "proposed_declared_native_ids": sorted(after), "source_positions": [first[3], second[3]],
                 "declarations": [{"condition_id": identifier, **{key: session.condition_values(identifier)[key]
                    for key in ("velocity", "coordinate_system_id")}} for identifier in (first[0], second[0])],
                 "effective_initial_state": "not_evaluated; native record order matters"}
                for first, second, before, after in _velocity_overlap_pairs(velocities, changed)]
    return deepcopy({"links": links, "conditions": conditions, "initial_velocity_overlaps": overlaps,
        "before_basis": "Before coefficients and intersections use saved pre-mesh memberships for stale groups, current declarations for other groups. Current card declarations are reported separately; historical geometry is unavailable.",
        "unresolved_initial_velocity_groups": sorted(set(unresolved_velocity)),
        "remaining_stale_groups": sorted(stale_after),
        "overlap_scope": "Declared native IDs only. Final targets of remaining stale groups are unreviewed; an empty overlap list does not establish absence of overlap.",
        "scope": "Final explicit mapping and CLOAD/INIVEL field applicability; not historical geometry, full BCS/contact physics or effective initial state."})
