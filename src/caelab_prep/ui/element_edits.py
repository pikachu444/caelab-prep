"""One pending element list and review lifetime for actual native mesh commands."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout)

from ..cae_core import PrepError
from .mesh_target_text import target_review_text
from .widgets._editing import ReferenceComboBox


class NativeElementDialog(QDialog):
    changed = Signal(object)
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None, *, has_draft=None, is_busy=None):
        super().__init__(parent)
        self.session = session
        self.has_draft, self.is_busy = has_draft or (lambda: False), is_busy or (lambda: False)
        self._stamp = self._current_stamp()
        self._plan, self._references, self._closed = None, [], False
        self.setObjectName(self.object_name); self.setWindowTitle(self.window_title)
        self.resize(780, 600); self.setMinimumSize(540, 420)
        body = QVBoxLayout(self)
        intro = QLabel(self.introduction)
        intro.setWordWrap(True); body.addWidget(intro)
        self._options = self._build_options(body)
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
        self.preview = QTextBrowser(); self.preview.setAccessibleName(self.window_title + " and target review")
        split.addWidget(self.preview); split.setSizes([150, 300])
        self.status = QLabel("Select elements in the model, add them, review the options and preview.")
        self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True); body.addWidget(self.status)
        self.reviewed = QCheckBox(self.review_caption)
        self.reviewed.toggled.connect(self._sync); body.addWidget(self.reviewed)
        buttons = QHBoxLayout(); body.addLayout(buttons)
        self.preview_button = QPushButton(self.preview_caption); self.preview_button.clicked.connect(self.prepare_preview)
        self.apply_button = QPushButton(self.apply_caption); self.apply_button.setObjectName("primaryAction")
        self.apply_button.clicked.connect(self.apply_change)
        self.close_button = QPushButton("Close"); self.close_button.clicked.connect(self.reject)
        for button in (self.use_selection_button, self.remove_button, self.preview_button, self.apply_button): button.setAutoDefault(False)
        buttons.addWidget(self.preview_button); buttons.addWidget(self.apply_button)
        buttons.addStretch(); buttons.addWidget(self.close_button)
        self.sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.finished.connect(self._finished)
        self.table.itemSelectionChanged.connect(self._sync)
        for option in self._options: option.currentIndexChanged.connect(self._options_changed)
        self._sync()
        if session.selection()["refs"]: self.use_selection()

    def _current_stamp(self):
        return self.session.document.id, self.session.document.revision, self.session._document_epoch

    def _expected(self):
        return dict(expected_revision=self._stamp[1], expected_document_id=self._stamp[0])

    def _build_options(self, body):
        return []

    def _guard(self):
        if self.is_busy() or self.has_draft():
            raise PrepError("model_busy", "Finish the active model operation or property draft first.")
        if self._current_stamp() != self._stamp:
            raise PrepError("stale_mesh_candidate", "The model changed. Close this editor and choose current elements again.")

    def _invalidate(self):
        if self._plan: self._cancel_plan(self._plan["plan_id"])
        self._plan = None; self.preview.clear(); self.reviewed.setChecked(False); self._sync()

    def _sync(self):
        self.reviewed.setEnabled(bool(self._plan and self._plan["admissible"]))
        self.apply_button.setEnabled(bool(self._plan and self._plan["admissible"] and self.reviewed.isChecked()))
        current = not self._closed and self._current_stamp() == self._stamp
        self.remove_button.setEnabled(bool(self.table.selectionModel().selectedRows()) and current)

    def _options_changed(self):
        self._invalidate()
        self.status.setText(self.options_caption + " changed. Preview the pending elements again before Apply.")

    def use_selection(self):
        try:
            self._guard(); self._invalidate()
            refs = self.session.selection()["refs"]
            if not refs or any(ref["entity_kind"] != "element" for ref in refs):
                raise PrepError("invalid_element_selection", "Select only elements to add. The pending list is kept; mixed selections are not filtered.")
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
            self.status.setText(f"{len(self._references)} explicit elements. " + self.selection_hint)
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
            self._plan = self._plan_request()
            plan = self._plan
            self.preview.setPlainText(self._review_text(plan))
            self.status.setText("Review the proposed changes before Apply." if plan["admissible"] else "Unsupported condition targets block Apply.")
            self._sync()
        except (PrepError, ValueError) as exc: self.status.setText(str(getattr(exc, "message", exc)))

    def apply_change(self):
        try:
            self._guard()
            if not self._plan or not self._plan["admissible"] or not self.reviewed.isChecked():
                raise PrepError("review_required", "Prepare and review a valid element operation first.")
            result = self._apply_request()
            self._plan = None; self._stamp = self._current_stamp(); self._references = []
            self.table.setRowCount(0); self._invalidate()
            self.status.setText(self.result_caption +
                " applied in one Undo. Use Mesh → Replace prepared mesh / reconnect targets… for pending target reviews.")
            self.changed.emit(result)
        except PrepError as exc:
            self._invalidate(); self.status.setText(exc.message)

    def _session_changed(self, _):
        if not self._closed and self._current_stamp() != self._stamp:
            self._invalidate(); self.preview_button.setEnabled(False); self.use_selection_button.setEnabled(False); self.remove_button.setEnabled(False)
            for option in self._options: option.setEnabled(False)
            self.status.setText("The model changed. Close this editor and choose current elements again.")

    def _finished(self, *_):
        if not self._closed:
            self._closed = True; self._invalidate(); self._unsubscribe()


def deletion_review_text(session, plan):
    labels = {card["id"]: f"{card['title'] or card['keyword']} [{card['keyword']}]" for card in session.list_cards()}
    def reference(ref):
        source = plan["resource_names"].get(ref["resource_id"], ref["resource_id"])
        identity = labels.get(ref["local_id"], f"{ref['entity_kind']} {ref['local_id']}")
        return f"{identity} in {source}"

    lines = [f"Delete {len(plan['removed_cells'])} explicit elements.",
        "Only newly orphaned nodes are considered; pre-existing orphan nodes are preserved.",
        "New orphan policy: " + ("keep nodes" if plan["orphan_policy"] == "keep" else "delete only newly orphaned nodes"),
        "", "Elements to delete (source, family, native ID, connectivity)"]
    for cell in plan["removed_cells"]:
        nodes = [ref["local_id"] for ref in cell["nodes"]]
        orientation = cell["orientation_node"]
        lines.append(f"{reference(cell['ref'])}: {cell['family']}, nodes {nodes}"
                     + (f"; orientation-only node {orientation['local_id']}" if orientation else ""))
    lines.extend(("", f"Newly orphaned nodes ({len(plan['new_orphans'])})"))
    lines.extend(reference(ref) for ref in plan["new_orphans"])
    lines.append(f"Nodes to delete: {len(plan['removed_nodes'])}")
    lines.extend(("", "Quality of removed elements (surviving connectivity is unchanged)"))
    for row in plan["quality_before"]:
        lines.append(f"{reference(row['element'])}: {row['metric']} {row['value']:.6g}")
    lines.extend(("No quality improvement or physical equivalence is implied.", "", "Surviving target proposal (trial only)"))
    for row in plan["projected_memberships"]:
        if row["dropped_members"]:
            identifier = row["group_ref"]["local_id"]
            lines.append(f"{labels.get(identifier, identifier)}: remove " + "; ".join(reference(ref) for ref in row["dropped_members"]))
    lines.extend((f"{len(plan['stale_targets'])} original groups stay stale until explicit mapping/Drop in the reconnection editor.",
        "Original group membership and condition declarations are not changed by this deletion.", "",
        target_review_text(session, plan, group_heading=False), "", plan["scope"]))
    return "\n".join(lines)


def shell_review_text(session, plan):
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
        "", target_review_text(session, plan, group_heading=False)))
    return "\n".join(lines)


def ownership_review_text(session, plan):
    labels = {card["id"]: f"{card['title'] or card['keyword']} [{card['keyword']}]" for card in session.list_cards()}
    lines = [f"Move {len(plan['cells'])} explicit elements to the chosen PART.",
        "Native element ID/source, coordinates, connectivity, orientation and complete row suffix are preserved.",
        "Stored shell angle and element thickness overrides stay unchanged; target property thickness is not forced over them.",
        "Target assignments are checked for supported formulation and mechanical components; not all material values or solver behavior.",
        "", "Element ownership and native material/property references (current → proposed)"]
    for ref in plan["unchanged_elements"]:
        lines.append(f"Already in chosen PART, unchanged: element {ref['local_id']} in {plan['resource_names'][ref['resource_id']]}")
    for cell in plan["cells"]:
        ref = cell["reference"]; source = plan["resource_names"][ref["resource_id"]]
        lines.append(f"{source}: {cell['family']} {ref['local_id']}")
        for caption, value in (("Current", cell["before_assignment"]), ("Proposed", cell["proposed_assignment"])):
            owner = plan["resource_names"].get(value["resource_id"], value["resource_id"])
            lines.append(f"  {caption}: PART {value['native_part_id']} — {labels[value['card_id']]} in {owner}")
            lines.append(f"    MAT {value['native_material_id']} — {labels[value['material_id']]}")
            lines.append(f"    PROP {value['native_property_id']} — {labels[value['property_id']]}")
    lines.extend(("", "Coordinates and surviving connectivity are unchanged; no mesh quality improvement is implied.",
        f"{len(plan['stale_targets'])} original target groups stay stale until explicit mapping/Drop in the reconnection editor.",
        "Original group membership and condition values are not automatically changed.", "",
        target_review_text(session, plan, group_heading=False), "", plan["scope"]))
    return "\n".join(lines)


class ShellNormalDialog(NativeElementDialog):
    object_name = "shellNormalDialog"
    window_title = "Reverse shell normals"
    introduction = ("Reverse the winding of selected SH3N or planar SHELL elements. "
                    "Element local axes also change; thickness and stored angle values stay unchanged.")
    review_caption = "I reviewed the orientation and affected target changes"
    preview_caption, apply_caption, result_caption = "Preview reversal", "Apply reversal", "Reversal"
    selection_hint = "Preview checks shell type, quality and affected targets."

    def _plan_request(self):
        return self.session.plan_shell_normal_flip(self._references, **self._expected())

    def _apply_request(self):
        return self.session.apply_shell_normal_flip(self._plan["plan_id"], **self._expected())

    def _cancel_plan(self, identifier):
        self.session.cancel_shell_normal_flip(identifier)

    def _review_text(self, plan):
        return shell_review_text(self.session, plan)

    def apply_reversal(self):
        self.apply_change()


class ElementDeletionDialog(NativeElementDialog):
    object_name = "elementDeletionDialog"
    window_title = "Delete elements"
    introduction = ("Delete only the listed elements. Choose whether to keep or delete newly orphaned nodes; "
                    "pre-existing orphans are kept. Original target declarations remain pending explicit review.")
    review_caption = "I reviewed the deletions and affected targets"
    preview_caption, apply_caption, result_caption = "Preview deletion", "Apply deletion", "Deletion"
    selection_hint = "Preview checks deletion, new orphans and affected targets."
    options_caption = "Orphan policy"

    def _build_options(self, body):
        form = QFormLayout(); body.addLayout(form)
        self.orphan_policy = QComboBox()
        self.orphan_policy.addItem("Choose explicitly…", None)
        self.orphan_policy.addItem("Keep newly orphaned nodes", "keep")
        self.orphan_policy.addItem("Delete only newly orphaned nodes", "delete_new")
        form.addRow("Newly orphaned nodes", self.orphan_policy)
        return [self.orphan_policy]

    def _plan_request(self):
        return self.session.plan_element_deletion(self._references, orphan_policy=self.orphan_policy.currentData(), **self._expected())

    def _apply_request(self):
        return self.session.apply_element_deletion(self._plan["plan_id"], **self._expected())

    def _cancel_plan(self, identifier):
        self.session.cancel_element_deletion(identifier)

    def _review_text(self, plan):
        return deletion_review_text(self.session, plan)


class PartReassignmentDialog(NativeElementDialog):
    object_name = "partReassignmentDialog"
    window_title = "Move elements to PART"
    introduction = ("Move all listed elements to one explicitly chosen existing PART. Native element IDs, source files and row values stay unchanged. "
                    "The target material/property and contact segments can change; affected targets require explicit review.")
    review_caption = "I reviewed the ownership and affected targets"
    preview_caption, apply_caption, result_caption = "Preview ownership", "Apply ownership", "Ownership transfer"
    selection_hint = "Choose the target for every listed element, then preview native ownership and affected targets."
    options_caption = "Target PART"

    def _build_options(self, body):
        form = QFormLayout(); body.addLayout(form)
        self.target_part = ReferenceComboBox()
        self.target_part.addItem("Choose target PART explicitly…", None)
        for row in self.session.list_cards():
            if row["keyword"].upper().strip("/").split("/")[0] != "PART": continue
            owner, card, refs = self.session._part_native_references(row["id"])
            source = self.session._paths.get(owner.id, owner.name)
            label = f"PART {refs['native_part_id']} — {card.title or card.keyword} — {source}"
            self.target_part.addItem(label, {"resource_id": owner.id, "entity_kind": "part", "local_id": card.id})
            self.target_part.setItemData(self.target_part.count()-1, label, Qt.ItemDataRole.ToolTipRole)
        form.addRow("Target for all listed elements", self.target_part)
        return [self.target_part]

    def _plan_request(self):
        part = self.target_part.currentData()
        if part is None: raise PrepError("review_required", "Choose the target PART explicitly before previewing ownership.")
        return self.session.plan_part_reassignment([{"element": dict(ref), "part": dict(part)} for ref in self._references], **self._expected())

    def _apply_request(self):
        return self.session.apply_part_reassignment(self._plan["plan_id"], **self._expected())

    def _cancel_plan(self, identifier):
        self.session.cancel_part_reassignment(identifier)

    def _review_text(self, plan):
        return ownership_review_text(self.session, plan)
