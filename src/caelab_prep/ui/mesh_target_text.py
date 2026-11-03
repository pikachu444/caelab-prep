"""Shared RAD target review text for membership edits and mesh changes."""


def _declaration_text(labels, declaration, coefficients):
    lines = []
    if coefficients:
        before, after = coefficients["before"], coefficients["after"]
        lines.extend((f"Native {after['quantity']} direction: {after['native_direction']}; per-node scale: {after['scale']}",
                      f"Curve: {labels.get(after['curve_ref']['card_id'], 'Native curve')}",
                      f"Native frame: {labels.get(after['frame_ref']['card_id'], after['frame_ref']['card_id']) if after['frame_ref'] else 'Global'}",
                      f"Global direction axis: {after['global_unit_axis']}",
                      f"Unevaluated multiplier sum: {before['summed_multiplier']} → {after['summed_multiplier']}",
                      "Time function/scaling and application-point moments are not evaluated. Values are not redistributed."))
    if "velocity" in declaration:
        lines.append(f"Declared initial velocity in its native frame: {declaration['velocity']}")
        frame = declaration.get("coordinate_system_id")
        lines.append(f"Velocity frame: {labels.get(frame, frame) if frame else 'Global'}")
    if "translations" in declaration:
        lines.append(f"Fixed translation components: {declaration['translations']}; rotations: {declaration['rotations']}")
    if "main_surface_id" in declaration:
        lines.append("Contact references are checked; gap, activation, penetration and force are not evaluated.")
    return lines


def target_review_text(session, plan, *, group_heading=True):
    labels = {card["id"]: f"{card['title'] or card['keyword']} [{card['keyword']}]" for card in session.list_cards()}

    def members(refs):
        if not refs: return "None"
        by_source = {}
        for ref in refs:
            source = plan["resource_names"].get(ref["resource_id"], ref["resource_id"])
            label = labels.get(ref["local_id"], f"{ref['entity_kind']} {ref['local_id']}")
            by_source.setdefault(source, []).append(label)
        return "; ".join(f"{source}: {', '.join(values)}" for source, values in by_source.items())

    def diagnostics(rows):
        result = []
        for row in rows:
            prefix = f"Node {row['node_id']}: " if "node_id" in row else ""
            message = row.get("message", row.get("code", "Unverified mechanical fields"))
            if "axis" in row: message += f"; axis {row['axis']}"
            result.append(prefix + message)
            result.extend(diagnostics(row.get("diagnostics", [])))
        return result

    if group_heading:
        lines = [labels.get(plan["group_ref"]["local_id"], plan["title"]), "",
                 f"Current members ({len(plan['before'])}): {members(plan['before'])}",
                 f"Proposed members ({len(plan['after'])}): {members(plan['after'])}",
                 f"Added: {members(plan['added'])}", f"Removed: {members(plan['removed'])}", "",
                 "Target references and mechanical fields are checked. Physical response, constraint sufficiency "
                 "and initial-state consistency are not evaluated.",
                 "Geometry is unchanged; this is not a mesh quality retest.", "", "Affected conditions"]
    else:
        lines = ["Projected target references and mechanical fields are checked. Physical response, constraint sufficiency and initial-state consistency are not evaluated.", "Affected conditions"]
    if not plan["conditions"]:
        lines.append("No condition in the supported reference profile targets this group." if group_heading
                     else "No affected conditions in the supported reference profile.")
    for condition in plan["conditions"]:
        lines.extend(("", labels.get(condition["reference"]["local_id"], condition["keyword"])))
        for role in condition["roles"]:
            lines.extend((f"{role['role'].title()} — {labels.get(role['group_ref']['local_id'], role['member_kind'])}",
                          f"  Current members: {members(role['before'])}", f"  Proposed members: {members(role['after'])}",
                          f"  Expanded nodes: {len(role['before_nodes'])} → {len(role['after_nodes'])}",
                          f"  Current nodes: {members(role['before_nodes'])}", f"  Proposed nodes: {members(role['after_nodes'])}"))
        for phase, caption in (("before", "Current"), ("after", "Proposed")):
            support = condition[phase + "_support"]
            lines.append(f"{caption} field applicability: {support['status']}")
            lines.extend("  " + text for text in diagnostics(support["diagnostics"]))
            lines.extend("  " + text for text in diagnostics(condition["reference_checks"][phase]))
        lines.extend(_declaration_text(labels, condition["declaration"], condition.get("load_coefficients")))
    if plan["initial_velocity_overlaps"]:
        lines.extend(("", "Overlapping initial velocity targets", "Effective initial state and momentum are not evaluated; native record order matters."))
        for overlap in plan["initial_velocity_overlaps"]:
            lines.extend((" / ".join(labels.get(card, card) for card in overlap["conditions"]),
                          f"Current overlap: {members(overlap['before_nodes'])}",
                          f"Proposed overlap: {members(overlap['after_nodes'])}",
                          "Stored positions before the edit (ordering across INCLUDE files is not evaluated):"))
            for position in overlap["source_positions"]:
                source = plan["resource_names"].get(position["resource_id"], position["resource_id"])
                lines.append(f"  {source}: header line {position['card_start'] + 1}")
    return "\n".join(lines)


def reconnection_review_text(session, plan):
    """Use stored old IDs at a stale boundary, without inventing old geometry."""
    labels = {card["id"]: f"{card['title'] or card['keyword']} [{card['keyword']}]" for card in session.list_cards()}
    drops = any(row.get("dropped_old_native_ids") for row in plan["links"])
    ownership = "ownership" if drops else "node ownership"
    lines = ["Final explicit targets and member removals" if drops else "Final explicit node targets", f"Old entries below are stored native IDs; historical {ownership} and geometry are not reconstructed.",
             "Repeated targets form one member only with your explicit permission. Native condition values stay unchanged.", plan["before_basis"]]
    for row in plan["links"]:
        counts = (f"{row['dropped_count']} explicitly removed; {row['coalesced_count']} repeated links coalesced."
                  if row.get("dropped_old_native_ids") else f"{row['collapsed_count']} collapsed links.")
        lines.extend(("", labels.get(row["group_id"], row["group_id"]),
            f"{row['old_link_count']} old links → {row['unique_target_count']} unique current targets; {counts}"))
        if row.get("dropped_old_native_ids"):
            lines.append(f"Remove these old IDs from the group: {row['dropped_old_native_ids']}")
        lines.append(f"Current card declaration: {row['current_declared_native_ids']} → final set: {row['proposed_native_ids']}")
        if row["current_declared_native_ids"] != row["old_native_ids"]:
            lines.append(f"Current card declaration differs from saved old links: {row['old_native_ids']}")
        for link in row["mapping"]:
            target = link["target"]
            if isinstance(target, dict):
                resource = session.document.resources[target["resource_id"]]
                lines.append(f"Old ID {link['old_native_id']} → {target['entity_kind']} {target['local_id']} in {resource.name} ({resource.id})")
            else:
                resource = session._find_card(target)
                lines.append(f"Old ID {link['old_native_id']} → {labels.get(target, target)} in {resource.name} ({resource.id})")
    lines.extend(("", "Affected conditions"))
    for row in plan["conditions"]:
        lines.extend(("", labels.get(row["condition_id"], row["keyword"])))
        for role in row["roles"]:
            lines.append(f"{role['role'].title()} — {labels.get(role['group_id'], role['group_id'])}: stored IDs {role['old_declared_native_ids']} → proposed IDs {role['proposed_native_ids']}"
                         + ("; final targets still unreviewed" if role["pending_after"] else ""))
            if role["current_declared_native_ids"] != role["old_declared_native_ids"]:
                lines.append(f"  Current card declaration differs from saved old links: {role['current_declared_native_ids']}")
        lines.append(f"Field applicability: {row['before_support']['status']} → {row['after_support']['status']}")
        lines.extend(_declaration_text(labels, row["declaration"], row.get("load_coefficients")))
    lines.extend(("", "Initial velocity intersections of declared native IDs", plan["overlap_scope"]))
    for row in plan["initial_velocity_overlaps"]:
        lines.append(" / ".join(labels.get(card, card) for card in row["conditions"]))
        lines.append(f"Stored overlap: {row['old_declared_native_ids']} → proposed overlap: {row['proposed_declared_native_ids']}")
        for declaration in row["declarations"]:
            lines.append(labels.get(declaration["condition_id"], declaration["condition_id"]))
            lines.extend(_declaration_text(labels, declaration, None))
        for position in row["source_positions"]:
            resource = session.document.resources[position["resource_id"]]
            lines.append(f"  {resource.name}: header line {position['before_card_start'] + 1} → {position['after_card_start'] + 1}")
    lines.extend(("Native record order matters; INCLUDE expansion order, effective initial state and momentum are not evaluated.",
                  f"Unresolved initial velocity groups: {', '.join(labels.get(group, group) for group in plan['unresolved_initial_velocity_groups']) or 'None'}",
                  f"Remaining stale groups: {', '.join(labels.get(group, group) for group in plan['remaining_stale_groups']) or 'None'}", plan["scope"]))
    return "\n".join(lines)

