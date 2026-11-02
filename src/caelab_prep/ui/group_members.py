"""RAD membership impact review consumes the existing operation draft."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout


class GroupMemberReviewDialog(QDialog):
    sessionEvent = Signal(dict)

    def __init__(self, session, plan, parent=None):
        super().__init__(parent)
        self.session, self.plan = session, plan
        self.result = None
        self._applying = False
        self._closed = False
        self.setObjectName("groupMemberReviewDialog")
        self.setWindowTitle("Preview group membership change")
        self.setMinimumSize(640, 480)
        screen = self.screen().availableGeometry()
        self.resize(min(900, screen.width() - 40), min(680, screen.height() - 60))
        layout = QVBoxLayout(self)
        explanation = QLabel("Review the current and proposed targets. Apply changes this membership once; "
                             "Cancel keeps the original draft and model. Geometry is unchanged.")
        explanation.setWordWrap(True); layout.addWidget(explanation)
        self.details = QTextBrowser()
        self.details.setPlainText(self._description())
        layout.addWidget(self.details, 1)
        self.error = QLabel(); self.error.setWordWrap(True); self.error.setObjectName("inputError")
        layout.addWidget(self.error)
        buttons = QHBoxLayout(); buttons.addStretch()
        self.apply_button = QPushButton("Apply reviewed membership")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.setEnabled(plan["admissible"])
        self.cancel_button = QPushButton("Cancel")
        buttons.addWidget(self.apply_button); buttons.addWidget(self.cancel_button); layout.addLayout(buttons)
        if not plan["admissible"]:
            self.error.setText("The proposed membership has unsupported condition targets. Inspect the details and revise the draft.")
        self.apply_button.clicked.connect(self.apply_review)
        self.cancel_button.clicked.connect(self.reject)
        self.sessionEvent.connect(self._session_changed)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.finished.connect(self._finished)

    def _description(self):
        plan = self.plan
        labels = {card["id"]: f"{card['title'] or card['keyword']} [{card['keyword']}]" for card in self.session.list_cards()}

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

        lines = [labels.get(plan["group_ref"]["local_id"], plan["title"]), "",
                 f"Current members ({len(plan['before'])}): {members(plan['before'])}",
                 f"Proposed members ({len(plan['after'])}): {members(plan['after'])}",
                 f"Added: {members(plan['added'])}", f"Removed: {members(plan['removed'])}", "",
                 "Target references and mechanical fields are checked. Physical response, constraint sufficiency "
                 "and initial-state consistency are not evaluated.",
                 "Geometry is unchanged; this is not a mesh quality retest.", "", "Affected conditions"]
        if not plan["conditions"]: lines.append("No condition in the supported reference profile targets this group.")
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

    def _session_changed(self, event):
        if self._applying or self._closed:
            return
        if any(event.get(key) != self.plan[key] for key in ("document_id", "revision", "document_epoch")):
            self.apply_button.setEnabled(False)
            self.error.setText("The model changed. Cancel this review, then reopen the group edit before preparing another preview.")
            self.session.cancel_group_members(self.plan["plan_id"])

    def apply_review(self):
        if not self.apply_button.isEnabled(): return False
        self._applying = True
        try:
            self.result = self.session.apply_group_members(self.plan["plan_id"],
                expected_revision=self.plan["revision"], expected_document_id=self.plan["document_id"])
            self.accept(); return True
        except Exception as exc:
            self.apply_button.setEnabled(False)
            self.error.setText(str(getattr(exc, "message", exc)))
            return False
        finally:
            self._applying = False

    def _finished(self, _):
        self._closed = True
        self.session.cancel_group_members(self.plan["plan_id"])
        self._unsubscribe()


def review_membership(host, spec, values):
    if spec.key != "object.edit" or spec.target is None:
        raise ValueError("Choose an existing node or element group.")
    key = "node_ids" if "node_ids" in values else "element_refs"
    plan = host.session.plan_group_members(spec.target.object_id, values[key],
        expected_revision=spec.expected_revision, expected_document_id=spec.document_id)
    dialog = None
    try:
        dialog = GroupMemberReviewDialog(host.session, plan, host.modeling.panel.window())
        host.modeling.membership_dialog = dialog
        dialog.exec()
        return dialog.result
    finally:
        host.session.cancel_group_members(plan["plan_id"])
        host.modeling.membership_dialog = None
        if dialog is not None: dialog.deleteLater()
