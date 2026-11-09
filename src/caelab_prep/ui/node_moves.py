"""Review absolute native coordinates before committing one mesh edit."""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView,
                              QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                              QTextBrowser, QVBoxLayout)

from ..cae_core import PrepError
from .widgets import NumericEdit


class NodeMoveDialog(QDialog):
    changed = Signal(object)
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None, *, has_draft=None, is_busy=None):
        super().__init__(parent)
        self.session = session
        self.has_draft = has_draft or (lambda: False)
        self.is_busy = is_busy or (lambda: False)
        self._plan = None
        self._refs = []
        self._stamp = self._current_stamp()
        self.setObjectName("nodeMoveDialog")
        self.setWindowTitle("Move nodes · absolute coordinates")
        self.resize(900, 680)
        self.setMinimumSize(640, 480)
        column = QVBoxLayout(self)
        explanation = QLabel("Move nodes by absolute coordinates in the input deck's length unit.")
        explanation.setWordWrap(True)
        column.addWidget(explanation)
        row = QHBoxLayout()
        self.resource = QComboBox()
        self.resource.setAccessibleName("Node source file")
        for resource in session._deck_resources():
            if resource.mesh_projection()["node_ids"]:
                self.resource.addItem(resource.name, resource.id)
        row.addWidget(self.resource, 1)
        self.identifiers = QLineEdit()
        self.identifiers.setPlaceholderText("Node IDs, e.g. 2, 5, 8")
        self.identifiers.setAccessibleName("Node IDs in chosen source file")
        row.addWidget(self.identifiers, 1)
        self.add_button = QPushButton("Add nodes")
        self.add_button.clicked.connect(self.add_nodes)
        row.addWidget(self.add_button)
        self.selected_button = QPushButton("Use selected nodes")
        self.selected_button.clicked.connect(self.use_selection)
        row.addWidget(self.selected_button)
        column.addLayout(row)
        units = session._model_resource(None).unit_context()["global"] or {}
        self.length_unit = units.get("length", "unknown")
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("absoluteNodeCoordinates")
        self.table.setHorizontalHeaderLabels(("Source", "Node", f"X ({self.length_unit})", f"Y ({self.length_unit})", f"Z ({self.length_unit})"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        column.addWidget(self.table, 2)
        self.preview = QTextBrowser()
        self.preview.setObjectName("nodeMoveImpactPreview")
        self.preview.setAccessibleName("Quality and reference impact preview")
        column.addWidget(self.preview, 1)
        self.status = QLabel("Choose a source file and add nodes, or use the current node selection.")
        self.status.setWordWrap(True)
        column.addWidget(self.status)
        self.reviewed = QCheckBox("I reviewed the coordinates, quality and affected targets")
        self.reviewed.toggled.connect(self._sync)
        column.addWidget(self.reviewed)
        row = QHBoxLayout()
        self.preview_button = QPushButton("Preview move")
        self.preview_button.clicked.connect(self.prepare_preview)
        self.clear_button = QPushButton("Clear rows")
        self.clear_button.clicked.connect(self.clear_rows)
        self.apply_button = QPushButton("Apply move")
        self.apply_button.clicked.connect(self.apply_move)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        for button in (self.clear_button, self.preview_button, self.apply_button):
            row.addWidget(button)
        row.addStretch()
        row.addWidget(self.close_button)
        column.addLayout(row)
        self.sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.finished.connect(self._finished)
        self.destroyed.connect(self._unsubscribe)
        self._sync()

    def _current_stamp(self):
        return self.session.document.id, self.session.document.revision, self.session._document_epoch

    def _guard(self):
        if self.is_busy() or self.has_draft():
            raise PrepError("model_busy", "Finish the active model operation or property draft first.")
        if self._current_stamp() != self._stamp:
            raise PrepError("stale_mesh_candidate", "The model changed. Close this editor and choose current nodes again.")

    def _invalidate(self):
        if self._plan:
            self.session.cancel_node_move(self._plan["plan_id"])
        self._plan = None
        self.reviewed.setChecked(False)
        self.preview.clear()
        self._sync()

    def _sync(self):
        self.apply_button.setEnabled(bool(self._plan and self.reviewed.isChecked()))

    def _add_refs(self, refs):
        self._guard()
        view = self.session.mesh_view()
        points = dict(zip(view["node_ids"], view["points"]))
        validated = []
        for ref in refs:
            identifier = ref["local_id"]
            if ref["entity_kind"] != "node" or view["node_resources"].get(identifier) != (ref["resource_id"],):
                raise PrepError("invalid_reference", "Every node must belong to the chosen source file.")
            if ref not in self._refs:
                validated.append((ref, points[identifier]))
        self._invalidate()
        for ref, xyz in validated:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._refs.append(dict(ref))
            resource = self.session.document.resources[ref["resource_id"]]
            for column, text in enumerate((resource.name, str(ref["local_id"]))):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
            for axis, value in enumerate(xyz):
                editor = NumericEdit(value, unit=self.length_unit)
                editor.setAccessibleName(f"Node {ref['local_id']} {'XYZ'[axis]} absolute coordinate")
                editor.textChanged.connect(self._invalidate)
                self.table.setCellWidget(row, axis + 2, editor)
        self.status.setText(f"{len(self._refs)} nodes. Edit coordinates, then preview the complete move.")

    def add_nodes(self):
        try:
            tokens = re.split(r"[\s,;]+", self.identifiers.text().strip())
            if not tokens or any(not token.isascii() or not token.isdecimal() or int(token) < 1 for token in tokens):
                raise PrepError("invalid_selection", "Enter positive node IDs separated by spaces or commas.")
            ids = [int(token) for token in tokens]
            if len(ids) != len(set(ids)):
                raise PrepError("invalid_selection", "List each node only once.")
            self._add_refs([{"resource_id": self.resource.currentData(), "entity_kind": "node", "local_id": value} for value in ids])
        except (PrepError, ValueError) as exc:
            self.status.setText(str(exc))

    def use_selection(self):
        try:
            refs = self.session.selection()["refs"]
            if not refs or any(ref["entity_kind"] != "node" for ref in refs):
                raise PrepError("invalid_selection", "Select nodes in the model before using this action.")
            self._add_refs(refs)
        except PrepError as exc:
            self.status.setText(str(exc))

    def clear_rows(self):
        self._invalidate()
        self.table.setRowCount(0)
        self._refs.clear()

    def prepare_preview(self):
        try:
            self._guard()
            self._invalidate()
            updates = [{"reference": ref, "position": [self.table.cellWidget(row, axis + 2).numeric_value() for axis in range(3)]}
                       for row, ref in enumerate(self._refs)]
            self._plan = self.session.plan_node_move(updates, length_unit=self.length_unit)
            count = len(self._plan["nodes"])
            lines = [f"{count} {'node' if count == 1 else 'nodes'} will move. No IDs or memberships will be changed.", "", "Affected element quality (before → after):"]
            metrics = {"normalized_length": "Line quality", "triangle_mean_ratio": "Triangle mean ratio",
                       "tet_mean_ratio": "Tetrahedron mean ratio", "quad_min_corner_scaled_jacobian": "Minimum corner Jacobian",
                       "hex_min_scaled_jacobian_27": "Minimum brick Jacobian (27 samples)"}
            old = {item["element"]["resource_id"] + ":" + str(item["element"]["local_id"]): item for item in self._plan["quality_before"]}
            for item in self._plan["quality_after"]:
                ref = item["element"]
                previous = old[ref["resource_id"] + ":" + str(ref["local_id"])]
                lines.append(f"Element {ref['local_id']}: {metrics[item['metric']]} {previous['value']:.6g} → {item['value']:.6g}")
                if item["metric"] == "normalized_length":
                    lines.append(f"    Length: {previous['signed_measure']:.6g} → {item['signed_measure']:.6g} {self.length_unit}")
            lines.extend(("", f"{len(self._plan['stale_targets'])} explicit target groups will require geometry review before native export."))
            for card_id in self._plan["stale_targets"]:
                card = self.session._find_card(card_id).card(card_id)
                lines.append(f"• {card.title or card.keyword}")
            lines.append("Moved load/constraint points and contact gaps require engineering review; this preview does not qualify their physical response.")
            self.preview.setPlainText("\n".join(lines))
            self.status.setText("Preview ready. Review every coordinate and affected target before applying.")
            self.reviewed.setChecked(True)
            self._sync()
        except (PrepError, ValueError) as exc:
            self.status.setText(str(exc))

    def apply_move(self):
        try:
            self._guard()
            if not self._plan or not self.reviewed.isChecked():
                raise PrepError("review_required", "Prepare and review a fresh preview first.")
            result = self.session.apply_node_move(self._plan["plan_id"], expected_revision=self._plan["revision"],
                                                  expected_document_id=self._plan["document_id"])
            self._plan = None
            self._stamp = self._current_stamp()
            self.reviewed.setChecked(False)
            self._sync()
            self.status.setText("Coordinates applied in one Undo. Use Mesh → Replace prepared mesh / reconnect targets… to review affected groups before export.")
            self.changed.emit(result)
        except PrepError as exc:
            self._invalidate()
            self.status.setText(str(exc))

    def _session_changed(self, event):
        if self._current_stamp() != self._stamp:
            self._invalidate()
            self.status.setText("The model changed. Close this editor and choose current nodes again.")

    def _finished(self, _):
        self._invalidate()
        self._unsubscribe()
