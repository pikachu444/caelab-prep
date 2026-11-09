"""RAD membership impact review consumes the existing operation draft."""
from .mesh_target_text import target_review_text

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
        explanation = QLabel("Review current and proposed group targets before Apply.")
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
        return target_review_text(self.session, self.plan)

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
