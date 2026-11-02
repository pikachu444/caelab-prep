"""Shared RAD target review text for membership edits and mesh changes."""


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
        coefficients = condition.get("load_coefficients")
        declaration = condition["declaration"]
        if coefficients:
            before, after = coefficients["before"], coefficients["after"]
            lines.extend((f"Native {after['quantity']} direction: {after['native_direction']}; per-node scale: {after['scale']}",
                          f"Curve: {labels.get(after['curve_ref']['card_id'], 'Native curve')}",
                          f"Global direction axis: {after['global_unit_axis']}",
                          f"Unevaluated multiplier sum: {before['summed_multiplier']} → {after['summed_multiplier']}",
                          "Time function/scaling and application-point moments are not evaluated. Values are not redistributed."))
        if "velocity" in declaration:
            lines.append(f"Declared initial velocity in its native frame: {declaration['velocity']}")
        if "translations" in declaration:
            lines.append(f"Fixed translation components: {declaration['translations']}; rotations: {declaration['rotations']}")
        if "main_surface_id" in declaration:
            lines.append("Contact references are checked; gap, activation, penetration and force are not evaluated.")
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

