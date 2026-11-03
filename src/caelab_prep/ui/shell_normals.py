"""Review selected native shell winding with the common document command."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout)

from ..cae_core import PrepError
from .mesh_target_text import target_review_text


class ShellNormalDialog(QDialog):
    changed = Signal(object)
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None, *, has_draft=None, is_busy=None):
        super().__init__(parent)
        self.session = session
        self.has_draft, self.is_busy = has_draft or (lambda: False), is_busy or (lambda: False)
        self._stamp = self._current_stamp()
        self._plan, self._references, self._closed = None, [], False
        self.setObjectName("shellNormalDialog"); self.setWindowTitle("Reverse shell normals")
        self.resize(780, 600); self.setMinimumSize(540, 420)
        body = QVBoxLayout(self)
        intro = QLabel("Reverse the winding of selected SH3N or planar SHELL elements. "
            "Element local axes also change; thickness and stored angle values stay unchanged.")
        intro.setWordWrap(True); body.addWidget(intro)
        selection = QHBoxLayout(); body.addLayout(selection)
        self.use_selection_button = QPushButton("Add selected elements")
        self.use_selection_button.clicked.connect(self.use_selection)
        self.remove_button = QPushButton("Remove selected rows")
        self.remove_button.clicked.connect(self.remove_selection)
        selection.addWidget(self.use_selection_button); selection.addWidget(self.remove_button); selection.addStretch()
        split = QSplitter(Qt.Orientation.Vertical); body.addWidget(split, 1)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(("Source file", "Element ID", "Type"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2): self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().hide(); split.addWidget(self.table)
        self.preview = QTextBrowser(); self.preview.setAccessibleName("Shell orientation and target review")
        split.addWidget(self.preview); split.setSizes([150, 300])
        self.status = QLabel("Select shell elements in the model, then use the selection and preview.")
        self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True); body.addWidget(self.status)
        self.reviewed = QCheckBox("I reviewed the orientation and affected target changes")
        self.reviewed.toggled.connect(self._sync); body.addWidget(self.reviewed)
        buttons = QHBoxLayout(); body.addLayout(buttons)
        self.preview_button = QPushButton("Preview reversal"); self.preview_button.clicked.connect(self.prepare_preview)
        self.apply_button = QPushButton("Apply reversal"); self.apply_button.setObjectName("primaryAction")
        self.apply_button.clicked.connect(self.apply_reversal)
        self.close_button = QPushButton("Close"); self.close_button.clicked.connect(self.reject)
        for button in (self.use_selection_button, self.remove_button, self.preview_button, self.apply_button): button.setAutoDefault(False)
        buttons.addWidget(self.preview_button); buttons.addWidget(self.apply_button)
        buttons.addStretch(); buttons.addWidget(self.close_button)
        self.sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.finished.connect(self._finished)
        self.table.itemSelectionChanged.connect(self._sync)
        self._sync()
        if session.selection()["refs"]: self.use_selection()

    def _current_stamp(self):
        return self.session.document.id, self.session.document.revision, self.session._document_epoch

    def _guard(self):
        if self.is_busy() or self.has_draft():
            raise PrepError("model_busy", "Finish the active model operation or property draft first.")
        if self._current_stamp() != self._stamp:
            raise PrepError("stale_mesh_candidate", "The model changed. Close this editor and choose current shells again.")

    def _invalidate(self):
        if self._plan: self.session.cancel_shell_normal_flip(self._plan["plan_id"])
        self._plan = None; self.preview.clear(); self.reviewed.setChecked(False); self._sync()

    def _sync(self):
        self.reviewed.setEnabled(bool(self._plan and self._plan["admissible"]))
        self.apply_button.setEnabled(bool(self._plan and self._plan["admissible"] and self.reviewed.isChecked()))
        current = not self._closed and self._current_stamp() == self._stamp
        self.remove_button.setEnabled(bool(self.table.selectionModel().selectedRows()) and current)

    def use_selection(self):
        try:
            self._guard(); self._invalidate()
            refs = self.session.selection()["refs"]
            if not refs or any(ref["entity_kind"] != "element" for ref in refs):
                raise PrepError("invalid_shell_selection", "Select only elements to add. The pending list is kept; mixed selections are not filtered.")
            keys = {(ref["resource_id"], ref["entity_kind"], ref["local_id"]) for ref in self._references}
            for ref in refs:
                key = ref["resource_id"], ref["entity_kind"], ref["local_id"]
                if key not in keys:
                    self._references.append(dict(ref)); keys.add(key)
            self.session.mesh_view()
            self.table.setRowCount(len(self._references))
            for row, ref in enumerate(self._references):
                source = self.session._paths.get(ref["resource_id"], ref["resource_id"])
                cells = [cell for cell in self.session._projection_index["cells_by_id"].get(ref["local_id"], ())
                         if cell["resource_id"] == ref["resource_id"]]
                family = cells[0].get("formulation", cells[0]["type"]) if len(cells) == 1 else "Unresolved"
                for column, text in enumerate((source, str(ref["local_id"]), family)):
                    item = QTableWidgetItem(text); item.setToolTip(text); self.table.setItem(row, column, item)
            self.status.setText(f"{len(self._references)} explicit elements. Preview checks shell type, quality and affected targets.")
        except PrepError as exc: self.status.setText(exc.message)

    def remove_selection(self):
        try:
            self._guard(); self._invalidate()
            for row in sorted((item.row() for item in self.table.selectionModel().selectedRows()), reverse=True):
                self._references.pop(row); self.table.removeRow(row)
            self.status.setText("Selection changed. Preview the remaining elements before Apply.")
        except PrepError as exc: self.status.setText(exc.message)

    def prepare_preview(self):
        try:
            self._guard(); self._invalidate()
            self._plan = self.session.plan_shell_normal_flip(self._references,
                expected_revision=self._stamp[1], expected_document_id=self._stamp[0])
            plan = self._plan
            lines = [f"{len(plan['cells'])} shells: connectivity and local axes change.",
                "Coordinates, PART, thickness and stored angles are preserved.", "", "Native connectivity (current → proposed)"]
            for cell in plan["cells"]:
                nodes = lambda value: [ref["local_id"] for ref in value["nodes"]]
                source = plan["resource_names"][cell["reference"]["resource_id"]]
                lines.append(f"{source}: {cell['family']} {cell['reference']['local_id']}: {nodes(cell['before'])} → {nodes(cell['proposed'])}")
            old_quality = {(row["element"]["resource_id"], row["element"]["local_id"]): row for row in plan["quality_before"]}
            lines.extend(("", "Element quality (current → proposed)"))
            for row in plan["quality_after"]:
                ref = row["element"]; old = old_quality[ref["resource_id"], ref["local_id"]]
                lines.append(f"Element {ref['local_id']}: {row['metric'].replace('_', ' ')} {old['value']:.6g} → {row['value']:.6g}")
            lines.extend(("", f"{len(plan['stale_targets'])} target groups require explicit reconnection before export.",
                "TYPE7 contact roles and values are preserved; reversal does not imply reversal of contact forces.",
                "", target_review_text(self.session, plan, group_heading=False)))
            self.preview.setPlainText("\n".join(lines))
            self.status.setText("Review the reversal before Apply." if plan["admissible"] else "Unsupported condition targets block Apply.")
            self._sync()
        except (PrepError, ValueError) as exc: self.status.setText(str(getattr(exc, "message", exc)))

    def apply_reversal(self):
        try:
            self._guard()
            if not self._plan or not self._plan["admissible"] or not self.reviewed.isChecked():
                raise PrepError("review_required", "Prepare and review a valid shell reversal first.")
            result = self.session.apply_shell_normal_flip(self._plan["plan_id"],
                expected_revision=self._plan["revision"], expected_document_id=self._plan["document_id"])
            self._plan = None; self._stamp = self._current_stamp(); self._references = []
            self.table.setRowCount(0); self._invalidate()
            self.status.setText("Reversal applied in one Undo. Use Mesh → Replace prepared mesh / reconnect targets… for pending target reviews.")
            self.changed.emit(result)
        except PrepError as exc:
            self._invalidate(); self.status.setText(exc.message)

    def _session_changed(self, _):
        if not self._closed and self._current_stamp() != self._stamp:
            self._invalidate(); self.preview_button.setEnabled(False); self.use_selection_button.setEnabled(False); self.remove_button.setEnabled(False)
            self.status.setText("The model changed. Close this editor and choose current shells again.")

    def _finished(self, *_):
        if not self._closed:
            self._closed = True; self._invalidate(); self._unsubscribe()
