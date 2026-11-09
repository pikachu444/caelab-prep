"""Explicit node pairs and engineering review use the existing native merge API."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget)

from ..cae_core import PrepError
from .mesh_target_text import target_review_text
from .widgets import NumericEdit


class NodeMergeDialog(QDialog):
    changed = Signal(object)
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None, *, has_draft=None, is_busy=None):
        super().__init__(parent)
        self.session = session
        self.has_draft, self.is_busy = has_draft or (lambda: False), is_busy or (lambda: False)
        self._stamp = self._current_stamp()
        self._plan, self._pairs, self._loading, self._closed = None, [], False, False
        self.length_unit = (session._model_resource(None).unit_context()["global"] or {}).get("length", "unknown")
        self.setObjectName("nodeMergeDialog"); self.setWindowTitle("Merge selected nodes")
        self.setMinimumSize(640, 480)
        area = self.screen().availableGeometry()
        self.resize(min(960, area.width() - 40), min(760, area.height() - 60))
        column = QVBoxLayout(self)
        introduction = QLabel("Merge explicit node pairs; keeper coordinates stay fixed.")
        introduction.setWordWrap(True); column.addWidget(introduction)
        self.tabs = QTabWidget(); column.addWidget(self.tabs, 1)
        page = QWidget(); body = QVBoxLayout(page)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page)
        self.tabs.addTab(scroll, "Node pairs")
        form = QFormLayout(); body.addLayout(form)
        self.sources, self.identifiers, self.selection_buttons = [], [], []
        for index, caption in enumerate(("Remove node", "Keep node")):
            row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
            source = QComboBox(); source.setAccessibleName(caption + " source file")
            source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            source.setMinimumContentsLength(12)
            source.currentTextChanged.connect(source.setToolTip)
            identifier = QLineEdit(); identifier.setPlaceholderText("Node ID")
            identifier.setAccessibleName(caption + " native ID"); identifier.setMaximumWidth(130)
            selected = QPushButton("Use selected")
            selected.setAccessibleName("Use selected " + caption.lower())
            selected.clicked.connect(lambda _, side=index: self.use_selection(side))
            layout.addWidget(source, 1); layout.addWidget(identifier); layout.addWidget(selected)
            self.sources.append(source); self.identifiers.append(identifier)
            self.selection_buttons.append(selected)
            form.addRow(caption, row)
            source.currentIndexChanged.connect(self._invalidate); identifier.textChanged.connect(self._invalidate)
        self._fill_sources()
        self.tolerance = NumericEdit(unit=self.length_unit)
        self.tolerance.setAccessibleName("Explicit merge tolerance in " + self.length_unit)
        self.tolerance.textChanged.connect(self._invalidate)
        form.addRow(f"Tolerance ({self.length_unit})", self.tolerance)
        buttons = QHBoxLayout()
        self.add_button = QPushButton("Add pair"); self.add_button.clicked.connect(self.add_pair)
        self.remove_button = QPushButton("Remove selected pair"); self.remove_button.clicked.connect(self.remove_pair)
        buttons.addWidget(self.add_button); buttons.addWidget(self.remove_button); buttons.addStretch(); body.addLayout(buttons)
        self.table = QTableWidget(0, 2)
        self.table.setObjectName("nodeMergePairs"); self.table.setHorizontalHeaderLabels(("Removed node", "Keeper"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().sectionResized.connect(self._fit_pairs_table)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        body.addWidget(self.table)
        self.boundaries = QGroupBox("Boundary permissions for the selected pair")
        boundary_layout = QVBoxLayout(self.boundaries)
        self.part_uses = QLabel(); self.part_uses.setWordWrap(True); self.part_uses.setTextFormat(Qt.TextFormat.PlainText)
        boundary_layout.addWidget(self.part_uses)
        self.cross_parts = QCheckBox("Allow crossing these PART uses")
        self.cross_resources = QCheckBox("Allow crossing the listed source-file boundary")
        boundary_layout.addWidget(self.cross_parts); boundary_layout.addWidget(self.cross_resources)
        contact_label = QLabel("Allow these exact contact boundaries:")
        boundary_layout.addWidget(contact_label)
        self.contacts = QListWidget(); self.contacts.setMaximumHeight(100)
        self.contacts.setWordWrap(True)
        self.contacts.setAccessibleName("Exact contact boundary permissions for selected pair")
        for card in session.list_cards():
            if card["keyword"].upper().startswith("/INTER/TYPE7/"):
                text = f"{card['title'] or card['keyword']} [{card['keyword']}]\n{self._source_label(card['resource_id'])}"
                item = QListWidgetItem(text, self.contacts)
                item.setToolTip(text)
                item.setData(Qt.ItemDataRole.UserRole, {"resource_id": card["resource_id"], "entity_kind": "condition", "local_id": card["id"]})
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
        contact_label.setVisible(self.contacts.count() > 0)
        self.contacts.setVisible(self.contacts.count() > 0)
        boundary_layout.addWidget(self.contacts); body.addWidget(self.boundaries); body.addStretch()
        self.table.itemSelectionChanged.connect(self._show_permissions)
        self.cross_parts.toggled.connect(self._permissions_changed)
        self.cross_resources.toggled.connect(self._permissions_changed)
        self.contacts.itemChanged.connect(self._permissions_changed)
        self.preview = QTextBrowser(); self.preview.setObjectName("nodeMergeImpactPreview")
        self.preview.setAccessibleName("Merge quality and projected condition targets")
        self.tabs.addTab(self.preview, "Review")
        self.status = QLabel("Add explicit pairs, enter a tolerance, then preview. No nearest-node search is performed.")
        self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True); column.addWidget(self.status)
        self.reviewed = QCheckBox("I reviewed this merge and its affected targets")
        self.reviewed.toggled.connect(self._sync); column.addWidget(self.reviewed)
        footer = QHBoxLayout()
        self.preview_button = QPushButton("Preview merge"); self.preview_button.clicked.connect(self.prepare_preview)
        self.apply_button = QPushButton("Apply merge"); self.apply_button.setObjectName("primaryAction")
        self.apply_button.clicked.connect(self.apply_merge)
        self.close_button = QPushButton("Close"); self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.preview_button); footer.addWidget(self.apply_button); footer.addStretch(); footer.addWidget(self.close_button)
        column.addLayout(footer)
        for button in (self.add_button, self.remove_button, self.preview_button, self.apply_button): button.setAutoDefault(False)
        self.sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.finished.connect(self._finished)
        self._show_permissions(); self._sync()

    def _source_label(self, rid):
        return self.session._paths.get(rid, self.session.document.resources[rid].name)

    def _fill_sources(self):
        for box in self.sources:
            current = box.currentData(); box.clear()
            for resource in self.session._deck_resources():
                if resource.mesh_projection()["node_ids"]:
                    box.addItem(self._source_label(resource.id), resource.id)
            if box.findData(current) >= 0: box.setCurrentIndex(box.findData(current))

    def _current_stamp(self):
        return self.session.document.id, self.session.document.revision, self.session._document_epoch

    def _guard(self):
        if self.is_busy() or self.has_draft():
            raise PrepError("model_busy", "Finish the active model operation or property draft first.")
        if self._current_stamp() != self._stamp:
            raise PrepError("stale_mesh_candidate", "The model changed. Close this editor and choose current nodes again.")

    def _invalidate(self, *_):
        if self._plan: self.session.cancel_node_merge(self._plan["plan_id"])
        self._plan = None
        if hasattr(self, "reviewed"):
            self.reviewed.setChecked(False); self.preview.clear(); self._sync()

    def _sync(self):
        self.reviewed.setEnabled(bool(self._plan and self._plan["admissible"]))
        self.apply_button.setEnabled(bool(self._plan and self._plan["admissible"] and self.reviewed.isChecked()))

    def use_selection(self, side):
        try:
            self._guard(); refs = self.session.selection()["refs"]
            if len(refs) != 1 or refs[0]["entity_kind"] != "node":
                raise PrepError("invalid_selection", "Select exactly one node for this side of the pair.")
            index = self.sources[side].findData(refs[0]["resource_id"])
            if index < 0: raise PrepError("invalid_reference", "The selected node source is unavailable.")
            self.sources[side].setCurrentIndex(index); self.identifiers[side].setText(str(refs[0]["local_id"]))
        except PrepError as exc: self.status.setText(exc.message)

    def add_pair(self):
        try:
            self._guard(); view = self.session.mesh_view(); points = dict(zip(view["node_ids"], view["points"]))
            refs = []
            for source, editor in zip(self.sources, self.identifiers):
                text = editor.text().strip()
                if not text.isascii() or not text.isdecimal() or int(text) < 1:
                    raise PrepError("invalid_reference", "Enter a positive native node ID for each chosen source.")
                identifier = int(text)
                if view["node_resources"].get(identifier) != (source.currentData(),):
                    raise PrepError("invalid_reference", "Each node must belong uniquely to its chosen source file.")
                refs.append({"resource_id": source.currentData(), "entity_kind": "node", "local_id": identifier})
            if refs[0] == refs[1] or any(pair["source"] == refs[0] for pair in self._pairs):
                raise PrepError("invalid_merge_map", "Choose distinct source and keeper nodes; list each removed node once.")
            context = f"Removed node {refs[0]['local_id']} in {self._source_label(refs[0]['resource_id'])}: {self._part_uses(refs[0])}\nKeeper node {refs[1]['local_id']} in {self._source_label(refs[1]['resource_id'])}: {self._part_uses(refs[1])}"
            self._invalidate()
            self._pairs.append({"source": refs[0], "keeper": refs[1], "cross_parts": False, "cross_resources": False, "contacts": []})
            row = self.table.rowCount(); self.table.insertRow(row)
            for column, ref in enumerate(refs):
                position = ", ".join(f"{x:.6g}" for x in points[ref["local_id"]])
                text = f"{self._source_label(ref['resource_id'])}\nNode {ref['local_id']} ({position} {self.length_unit})"
                item = QTableWidgetItem(text); item.setToolTip(text)
                if column == 0: item.setData(Qt.ItemDataRole.UserRole, context)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable); self.table.setItem(row, column, item)
            self._fit_pairs_table(); self.table.selectRow(row)
            for editor in self.identifiers: editor.clear()
            self.status.setText("Pair added. Review its boundary permissions, then preview the complete merge.")
        except PrepError as exc: self.status.setText(exc.message)

    def _part_uses(self, ref):
        labels = set()
        target = ref["resource_id"], ref["local_id"]
        for cell in self.session._mesh_edit_snapshot().cells:
            endpoint = any((node.resource_id, node.local_id) == target for node in cell.nodes)
            direction = cell.orientation_node is not None and (cell.orientation_node.resource_id, cell.orientation_node.local_id) == target
            if endpoint or direction:
                card = self.session._find_card(cell.part.local_id).card(cell.part.local_id)
                labels.add(f"{card.title or card.keyword} [{card.keyword}]" + (" (direction point)" if direction and not endpoint else ""))
        return "; ".join(sorted(labels)) or "No element or direction-point use"

    def _fit_pairs_table(self, *_):
        self.table.resizeRowsToContents()
        height = self.table.horizontalHeader().height() + 2 * self.table.frameWidth()
        height += sum(self.table.rowHeight(row) for row in range(self.table.rowCount()))
        self.table.setFixedHeight(max(76, min(240, height)))

    def remove_pair(self):
        try:
            self._guard(); row = self.table.currentRow()
            if row >= 0:
                self._invalidate(); self._pairs.pop(row); self.table.removeRow(row); self._show_permissions(); self._fit_pairs_table()
        except PrepError as exc: self.status.setText(exc.message)

    def _show_permissions(self):
        row = self.table.currentRow(); self._loading = True
        try:
            pair = self._pairs[row] if 0 <= row < len(self._pairs) else None
            self.boundaries.setEnabled(pair is not None)
            self.part_uses.setText(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) if pair else "Select a pair to review its boundaries.")
            self.cross_parts.setChecked(bool(pair and pair["cross_parts"]))
            self.cross_resources.setChecked(bool(pair and pair["cross_resources"]))
            for index in range(self.contacts.count()):
                item = self.contacts.item(index)
                item.setCheckState(Qt.CheckState.Checked if pair and item.data(Qt.ItemDataRole.UserRole) in pair["contacts"] else Qt.CheckState.Unchecked)
        finally: self._loading = False

    def _permissions_changed(self, *_):
        row = self.table.currentRow()
        if self._loading or not 0 <= row < len(self._pairs): return
        pair = self._pairs[row]
        pair.update(cross_parts=self.cross_parts.isChecked(), cross_resources=self.cross_resources.isChecked(),
            contacts=[self.contacts.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.contacts.count())
                      if self.contacts.item(i).checkState() == Qt.CheckState.Checked])
        self._invalidate()

    def prepare_preview(self):
        try:
            self._guard(); self._invalidate()
            if any(editor.text().strip() for editor in self.identifiers):
                raise PrepError("unadded_pair", "Add the entered node pair or clear its inputs before previewing.")
            mapping = [{"source": pair["source"], "keeper": pair["keeper"]} for pair in self._pairs]
            self._plan = self.session.plan_node_merge(mapping, tolerance=self.tolerance.numeric_value(),
                length_unit=self.length_unit, approvals=self._pairs, expected_revision=self._stamp[1], expected_document_id=self._stamp[0])
            plan = self._plan
            lines = [f"{len(plan['mapping'])} explicit pairs. Tolerance {plan['tolerance']:g} {self.length_unit}.",
                "Keeper coordinates stay fixed. This does not preserve beam frames, weld properties or physical response."]
            for pair in plan["mapping"]:
                lines.append(f"Remove node {pair['source']['local_id']} in {self._source_label(pair['source']['resource_id'])} → keeper {pair['keeper']['local_id']} in {self._source_label(pair['keeper']['resource_id'])}")
                lines.append(f"  Removed position: {pair['source_position']}; keeper position: {pair['keeper_position']} {self.length_unit}")
            lines.extend(("", "Native connections and direction nodes"))
            for cell in plan["cells"]:
                old, new = cell["before"], cell["proposed"]
                nodes = lambda value: [ref["local_id"] for ref in value["nodes"]]
                orientation = lambda value: value["orientation_node"]["local_id"] if value["orientation_node"] else "native default"
                lines.append(f"{self._source_label(cell['reference']['resource_id'])}: {cell['family']} {cell['reference']['local_id']}: {nodes(old)} → {nodes(new)}")
                if cell["family"] == "BEAM": lines.append(f"  Direction node: {orientation(old)} → {orientation(new)}; local frame may change.")
            lines.extend(("", "Affected element quality (current → proposed)"))
            old_quality = {(row["element"]["resource_id"], row["element"]["local_id"]): row for row in plan["quality_before"]}
            for row in plan["quality_after"]:
                ref = row["element"]; old = old_quality[ref["resource_id"], ref["local_id"]]
                lines.append(f"Element {ref['local_id']}: {row['metric'].replace('_', ' ')} {old['value']:.6g} → {row['value']:.6g}")
            for row in plan["membership_coalescences"]:
                lines.append(f"Projected node group: {row['old_link_count']} old links → {row['projected_unique_count']} unique targets. This set change requires explicit permission and a final reconnection preview after merge.")
            lines.extend(("", f"{len(plan['stale_targets'])} target groups require explicit reconnection before native export.",
                "The target changes below are projections only. Apply merge keeps the original target declarations stale.", "", target_review_text(self.session, plan, group_heading=False)))
            self.preview.setPlainText("\n".join(lines)); self.tabs.setCurrentIndex(1)
            self.status.setText("Review the complete merge before Apply." if plan["admissible"] else "Unsupported projected condition targets block Apply. Revise the node pairs.")
            self.reviewed.setChecked(plan["admissible"])
            self._sync()
        except (PrepError, ValueError) as exc: self.status.setText(str(getattr(exc, "message", exc)))

    def apply_merge(self):
        try:
            self._guard()
            if not self._plan or not self._plan["admissible"] or not self.reviewed.isChecked():
                raise PrepError("review_required", "Prepare and review a valid merge preview first.")
            result = self.session.apply_node_merge(self._plan["plan_id"], expected_revision=self._plan["revision"], expected_document_id=self._plan["document_id"])
            self._plan = None; self._stamp = self._current_stamp(); self._pairs.clear(); self.table.setRowCount(0)
            self._show_permissions(); self._fit_pairs_table(); self._fill_sources(); self._invalidate(); self.tabs.setCurrentIndex(0)
            self.status.setText("Merge applied in one Undo. Use Mesh → Replace prepared mesh / reconnect targets… for remaining target reviews.")
            self.changed.emit(result)
        except PrepError as exc:
            self._invalidate(); self.status.setText(exc.message)

    def _session_changed(self, _):
        if not self._closed and self._current_stamp() != self._stamp:
            self._invalidate(); self.preview_button.setEnabled(False)
            self.status.setText("The model changed. Close this editor and choose current nodes again.")

    def _finished(self, _):
        if not self._closed:
            self._closed = True; self._invalidate(); self._unsubscribe()
