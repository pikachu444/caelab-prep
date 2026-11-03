"""Review independent RAD sources and explicit shared nodes before one commit."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QScrollArea, QTableView, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from ..cae_core import PrepError
from .shell import FileTask


class _TableModel(QAbstractTableModel):
    """Keep large correspondence tables virtual; do not allocate cell widgets."""

    def __init__(self, headers, parent=None):
        super().__init__(parent)
        self.headers, self.rows = headers, []

    def replace(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section] if orientation == Qt.Orientation.Horizontal else section + 1
        return None

    def value(self, row, column):
        return self.rows[row][column]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return str(self.value(index.row(), index.column()))
        return None


class _NativeMapModel(_TableModel):
    def __init__(self, parent=None):
        super().__init__(("Entity namespace", "Original ID", "Working ID", "Relationship"), parent)
        self.shared, self.collisions = set(), set()

    def show_source(self, source=None, collisions=()):
        source = source or {}
        self.shared = set(source.get("shared_nodes", ()))
        self.collisions = {tuple(item) for item in collisions}
        self.replace(source.get("id_map", []))

    def value(self, row, column):
        namespace, original, mapped = self.rows[row]
        if column < 3:
            return (namespace, original, mapped)[column]
        if namespace == "NODE" and original in self.shared:
            return "Explicitly shared"
        if (namespace, original) in self.collisions:
            return "Collision — renumbered"
        return "Renumbered" if original != mapped else "Independent ID preserved"


def _table(model, name):
    table = QTableView()
    table.setObjectName(name)
    table.setModel(model)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setDefaultSectionSize(24)
    for index in range(model.columnCount()):
        table.setColumnWidth(index, 150)
    return table


class SourceModelsDialog(QDialog):
    """The host supplies current draft/busy guards and refreshes on ``imported``.

    Planning reads and snapshots files on the existing file worker. Closing this
    dialog discards the review; the non-cancellable read may finish without ever
    importing. Only Apply invokes the session's atomic import on the GUI thread.
    """

    imported = Signal(object)
    changed = Signal(object)
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None, *, has_draft=None, is_busy=None):
        super().__init__(parent)
        self.session = session
        self.has_draft = has_draft or (lambda: False)
        self.is_busy = is_busy or (lambda: False)
        self.result = None
        self._plan = None
        self._source_ids = []
        self._shared = {}
        self._task = None
        self._jobs = []
        self._generation = 0
        self._task_generation = None
        self._closing = self._committing = self._entry_dirty = False
        self._sources = []
        self._instances = []
        self._instance_query_stamp = self._instance_review = self._instance_selected_review = None
        self.instance_result = None
        self._unsubscribed = False
        self.setObjectName("sourceModelsDialog")
        self.setWindowTitle("Source models")
        self.resize(980, 720)
        self.setMinimumSize(640, 480)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_import_tab()
        self._build_sources_tab()
        self._build_instances_tab()
        self.status = QLabel()
        self.status.setObjectName("sourceModelsStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.reviewed = QCheckBox("I reviewed the ID changes and any shared-node links")
        self.reviewed.setObjectName("sourceMappingReviewed")
        actions.addWidget(self.reviewed, 1)
        self.apply_button = QPushButton("Apply import")
        self.apply_button.setObjectName("sourceImportApply")
        self.close_button = QPushButton("Close")
        actions.addWidget(self.apply_button)
        actions.addStretch()
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
        self.source.textChanged.connect(self._source_changed)
        self.reviewed.toggled.connect(self._sync_apply)
        self.apply_button.clicked.connect(self.apply_import)
        self.close_button.clicked.connect(self.reject)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.sessionEvent.connect(self._session_changed)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.destroyed.connect(self._unsubscribe)
        self.finished.connect(self._finished)
        self.refresh()
        self._sync_apply()

    def _build_import_tab(self):
        page = QWidget()
        column = QVBoxLayout(page)
        row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setObjectName("sourceImportPath")
        self.source.setAccessibleName("Independent RAD source file")
        self.source.setPlaceholderText("Choose an independent RAD model")
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self.browse_source)
        self.preview_button = QPushButton("Prepare preview")
        self.preview_button.setObjectName("sourceImportPreview")
        self.preview_button.clicked.connect(self.prepare_preview)
        row.addWidget(self.source, 1)
        row.addWidget(self.browse_button)
        row.addWidget(self.preview_button)
        column.addLayout(row)
        self.policy = QLabel("Input and working units must match the open model. Unsupported cards, unresolved INCLUDEs and different or undeclared units block import. Original files remain unchanged.")
        self.policy.setWordWrap(True)
        column.addWidget(self.policy)
        self.summary = QLabel("Choose a source and prepare its native ID correspondence before importing.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("sourceImportSummary")
        column.addWidget(self.summary)
        self.preview_tabs = QTabWidget()
        self.native_model = _NativeMapModel(self)
        self.native_table = _table(self.native_model, "sourceNativeMapping")
        self.preview_tabs.addTab(self.native_table, "Native IDs")
        self.files_model = _TableModel(("Original file", "Working file"), self)
        self.files_table = _table(self.files_model, "sourceOriginalFiles")
        self.preview_tabs.addTab(self.files_table, "Source files")
        self.preview_tabs.addTab(self._mapping_editor(), "Shared nodes")
        column.addWidget(self.preview_tabs, 1)
        self.tabs.addTab(page, "Import source")

    def _mapping_editor(self):
        page = QWidget()
        column = QVBoxLayout(page)
        hint = QLabel("Nodes stay independent unless you add a link below. Choose a source node and an existing resource-qualified node. The preview checks their coordinates in the agreed units; equal coordinates or equal IDs never create a link automatically.")
        hint.setWordWrap(True)
        column.addWidget(hint)
        form = QFormLayout()
        self.source_node = QLineEdit()
        self.source_node.setObjectName("sourceOriginalNode")
        self.destination_node = QLineEdit()
        self.destination_node.setObjectName("sourceExistingNodeSearch")
        self.destination_node.setPlaceholderText("Exact existing node ID")
        form.addRow("Original source node ID", self.source_node)
        lookup = QHBoxLayout()
        lookup.addWidget(self.destination_node, 1)
        self.find_node_button = QPushButton("Find node")
        self.find_node_button.clicked.connect(self.find_existing_node)
        lookup.addWidget(self.find_node_button)
        self.use_selection_button = QPushButton("Use selected node")
        self.use_selection_button.clicked.connect(self.use_selected_node)
        lookup.addWidget(self.use_selection_button)
        form.addRow("Existing node", lookup)
        self.destination_choice = QComboBox()
        self.destination_choice.setObjectName("sourceExistingNodeChoice")
        self.destination_choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.destination_choice.setMinimumContentsLength(24)
        form.addRow("Resource-qualified target", self.destination_choice)
        column.addLayout(form)
        buttons = QHBoxLayout()
        self.add_mapping_button = QPushButton("Add shared-node link")
        self.add_mapping_button.clicked.connect(self.add_shared_node)
        self.clear_entry_button = QPushButton("Clear entry")
        self.clear_entry_button.clicked.connect(self.clear_mapping_entry)
        self.remove_mapping_button = QPushButton("Remove selected link")
        self.remove_mapping_button.clicked.connect(self.remove_shared_node)
        for button in (self.add_mapping_button, self.clear_entry_button, self.remove_mapping_button):
            buttons.addWidget(button)
        buttons.addStretch()
        column.addLayout(buttons)
        self.shared_model = _TableModel(("Original source node", "Existing node", "Existing resource"), self)
        self.shared_table = _table(self.shared_model, "sourceSharedNodes")
        column.addWidget(self.shared_table, 1)
        self.source_node.textChanged.connect(self._entry_changed)
        self.destination_node.textChanged.connect(self._search_changed)
        return page

    def _build_sources_tab(self):
        page = QWidget()
        column = QVBoxLayout(page)
        heading = QLabel("Imported sources — the base model is not an imported-source archive. Original bytes and each native ID correspondence are saved with the work document.")
        heading.setWordWrap(True)
        column.addWidget(heading)
        self.sources_model = _TableModel(("Source name", "Files", "Native IDs", "Shared nodes", "Source identity"), self)
        self.sources_table = _table(self.sources_model, "importedSources")
        self.sources_table.setMaximumHeight(180)
        column.addWidget(self.sources_table)
        details = QTabWidget()
        self.archive_native_model = _NativeMapModel(self)
        details.addTab(_table(self.archive_native_model, "storedNativeMapping"), "Stored native IDs")
        self.archive_files_model = _TableModel(("Original file", "Working file"), self)
        details.addTab(_table(self.archive_files_model, "storedOriginalFiles"), "Stored source files")
        column.addWidget(details, 1)
        self.refresh_button = QPushButton("Refresh imported sources")
        self.refresh_button.clicked.connect(self.refresh)
        column.addWidget(self.refresh_button)
        self.sources_table.selectionModel().currentRowChanged.connect(self._source_selected)
        self.tabs.addTab(page, "Imported sources")

    def _build_instances_tab(self):
        page = QWidget()
        column = QVBoxLayout(page)
        notice = QLabel("Instance references are metadata only: no placement, geometry duplication or native expansion is performed. Imported source archives remain separate records. Any not-expanded reference blocks native export until it is removed.")
        notice.setWordWrap(True)
        column.addWidget(notice)
        self.instances_model = _TableModel(("Reference name", "Referenced source", "Status", "Resources", "Instance identity"), self)
        self.instances_table = _table(self.instances_model, "instanceReferences")
        for index, width in enumerate((200, 300, 120, 80)):
            self.instances_table.setColumnWidth(index, width)
        self.instances_table.setMaximumHeight(180)
        column.addWidget(self.instances_table)
        self.instance_root = QLabel("Select a reference to inspect its resource identities.")
        self.instance_root.setWordWrap(True)
        column.addWidget(self.instance_root)
        self.instance_resources_model = _TableModel(("Referenced resource", "Resource identity"), self)
        resources = _table(self.instance_resources_model, "instanceReferencedResources")
        resources.setColumnWidth(0, 450)
        column.addWidget(resources, 1)
        form = QFormLayout()
        self.instance_name = QLineEdit()
        self.instance_name.setObjectName("instanceReferenceName")
        self.instance_name.setPlaceholderText("Name for a reference; no mesh will be created")
        form.addRow("New reference name", self.instance_name)
        self.instance_source = QComboBox()
        self.instance_source.setObjectName("instanceReferenceSource")
        self.instance_source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.instance_source.setMinimumContentsLength(24)
        form.addRow("Source (all its resources)", self.instance_source)
        column.addLayout(form)
        self.instance_acknowledged = QCheckBox("I understand this unexpanded reference will block native export")
        self.instance_acknowledged.setObjectName("instanceReferenceAcknowledged")
        column.addWidget(self.instance_acknowledged)
        row = QHBoxLayout()
        self.create_instance_button = QPushButton("Create reference")
        self.create_instance_button.clicked.connect(self.create_instance_reference)
        self.clear_instance_button = QPushButton("Clear entry")
        self.clear_instance_button.clicked.connect(self.clear_instance_entry)
        self.delete_instance_button = QPushButton("Delete selected reference")
        self.delete_instance_button.clicked.connect(self.delete_instance_reference)
        row.addWidget(self.create_instance_button)
        row.addWidget(self.clear_instance_button)
        row.addStretch()
        row.addWidget(self.delete_instance_button)
        column.addLayout(row)
        self.instance_name.textChanged.connect(self._instance_input_changed)
        self.instance_source.currentIndexChanged.connect(self._instance_input_changed)
        self.instance_acknowledged.toggled.connect(self._acknowledge_instance)
        self.instances_table.selectionModel().currentRowChanged.connect(self._instance_selected)
        self.tabs.addTab(page, "Instance references")

    def _tab_changed(self, index):
        self.reviewed.setVisible(index != 2)
        self.apply_button.setVisible(index != 2)

    def _current_instance_stamp(self):
        current = self.session.describe()
        return tuple(current[key] for key in ("document_id", "revision", "document_epoch"))

    def _instance_source_label(self, identifier):
        if identifier is None:
            return "Base model"
        source = next((item for item in self._sources if item["id"] == identifier), None)
        return f"Imported source: {source['name']} ({identifier})" if source else f"Unresolved source ({identifier})"

    def _instance_input_changed(self):
        self._instance_review = None
        self.instance_acknowledged.setChecked(False)
        self._sync_instance_actions()

    def _acknowledge_instance(self, checked):
        self._instance_review = (self._current_instance_stamp(), self.instance_name.text().strip(),
                                 self.instance_source.currentData()) if checked else None
        self._sync_instance_actions()

    def clear_instance_entry(self):
        self.instance_name.clear()
        self.instance_source.setCurrentIndex(0)
        self._instance_input_changed()

    def _sync_instance_actions(self):
        if not hasattr(self, "create_instance_button"):
            return
        idle = self._task is None and not self._closing
        self.create_instance_button.setEnabled(bool(idle and self._instance_review and self.instance_name.text().strip()))
        self.delete_instance_button.setEnabled(bool(idle and self._instance_selected_review))

    def _refresh_instances(self):
        stamp = self._current_instance_stamp()
        changed = stamp != self._instance_query_stamp
        selected = self._instance_selected_review[1] if self._instance_selected_review and not changed else None
        source = self.instance_source.currentData()
        self.instance_source.blockSignals(True)
        self.instance_source.clear()
        self.instance_source.addItem("Base model", None)
        for item in self._sources:
            self.instance_source.addItem(self._instance_source_label(item["id"]), item["id"])
        self.instance_source.setCurrentIndex(max(0, self.instance_source.findData(source)))
        self.instance_source.blockSignals(False)
        if changed:
            self._instance_input_changed()
        self._instance_query_stamp = stamp
        self._instances = self.session.instance_references()
        self.instances_model.replace([(item["name"], self._instance_source_label(item["source_id"]), item["status"],
            len(item["resource_ids"]), item["id"]) for item in self._instances])
        self._instance_selected_review = None
        self.instance_resources_model.replace([])
        self.instance_root.setText("Select a reference to inspect its resource identities.")
        if selected:
            index = next((index for index, item in enumerate(self._instances) if item["id"] == selected), None)
            if index is not None:
                self.instances_table.selectRow(index)
        self._sync_instance_actions()

    def _instance_selected(self, current, previous):
        self._instance_selected_review = None
        if current.isValid() and current.row() < len(self._instances):
            record = self._instances[current.row()]
            self._instance_selected_review = (self._instance_query_stamp, record["id"])
            self.instance_root.setText(f"Root resource: {self._resource_label(record['root_resource_id'])}")
            self.instance_resources_model.replace([(getattr(self.session.document.resources.get(rid), "name", rid), rid)
                                                   for rid in record["resource_ids"]])
        self._sync_instance_actions()

    def _check_instance_review(self, stamp):
        self._guard()
        if self._closing or self._task is not None:
            raise PrepError("review_required", "Finish the source preview or open a new dialog before changing references.")
        if stamp != self._current_instance_stamp():
            self._refresh_instances()
            raise PrepError("stale_reference", "The document changed. Review the instance reference again.")

    def create_instance_reference(self):
        try:
            if self._instance_review is None:
                raise PrepError("review_required", "Name the reference, choose its source and acknowledge the native export restriction.")
            stamp, name, source = self._instance_review
            self._check_instance_review(stamp)
            self._committing = True
            try:
                self.instance_result = self.session.create_instance_reference(name, source,
                    expected_document_id=stamp[0], expected_revision=stamp[1])
            finally:
                self._committing = False
            self._invalidate()
            self.clear_instance_entry()
            self.refresh()
            index = next(index for index, item in enumerate(self._instances) if item["id"] == self.instance_result["instance_id"])
            self.instances_table.selectRow(index)
            self.changed.emit(self.instance_result)
            self.status.setText("Reference metadata created. Geometry is unchanged; native export is blocked while this reference exists.")
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def delete_instance_reference(self):
        try:
            if self._instance_selected_review is None:
                raise PrepError("review_required", "Select the current reference to delete.")
            stamp, identifier = self._instance_selected_review
            self._check_instance_review(stamp)
            self._committing = True
            try:
                self.instance_result = self.session.delete_instance_reference(identifier,
                    expected_document_id=stamp[0], expected_revision=stamp[1])
            finally:
                self._committing = False
            self._invalidate()
            self.refresh()
            self.changed.emit(self.instance_result)
            self.status.setText("Reference metadata deleted. Undo restores it; referenced geometry remains unchanged.")
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def _guard(self):
        if self.has_draft():
            raise PrepError("draft_pending", "Finish or discard the open model's draft before changing source models or references.")
        if self.is_busy():
            raise PrepError("owner_busy", "Wait for the open model's current operation before changing source models or references.")

    def _show_error(self, error):
        code = getattr(error, "code", "source_import_failed")
        self.status.setText(f"{getattr(error, 'message', str(error))} [{code}]")

    def _invalidate(self, message=None):
        self._generation += 1
        self._plan = None
        if hasattr(self, "reviewed"):
            self.reviewed.setChecked(False)
            self._sync_apply()
        if message:
            self.status.setText(message)

    def _source_changed(self):
        self._source_ids = []
        self._shared.clear()
        self._refresh_shared()
        self.clear_mapping_entry()
        self.native_model.show_source()
        self.files_model.replace([])
        self._invalidate("Source changed. Prepare a new preview.")

    def _entry_changed(self):
        self._entry_dirty = bool(self.source_node.text().strip() or self.destination_node.text().strip())
        if hasattr(self, "apply_button"):
            self._sync_apply()

    def _search_changed(self):
        self.destination_choice.clear()
        self._entry_changed()

    def clear_mapping_entry(self):
        self.source_node.clear()
        self.destination_node.clear()
        self.destination_choice.clear()
        self._entry_dirty = False
        if hasattr(self, "apply_button"):
            self._sync_apply()

    @staticmethod
    def _node_id(text):
        text = text.strip()
        if not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 9999999999:
            raise PrepError("invalid_reference", "Enter a positive native node ID.")
        return int(text)

    def _resource_label(self, resource_id):
        resource = self.session.document.resources.get(resource_id)
        return f"{getattr(resource, 'name', resource_id)} ({resource_id})"

    def _offer_node(self, reference):
        projection = self.session.mesh_view()
        if (set(reference) != {"resource_id", "entity_kind", "local_id"}
                or reference["entity_kind"] != "node"
                or projection["node_resources"].get(reference["local_id"]) != (reference["resource_id"],)):
            raise PrepError("invalid_reference", "Choose a uniquely resolved existing node.")
        self.destination_choice.clear()
        self.destination_choice.addItem(
            f"Node {reference['local_id']} — {self._resource_label(reference['resource_id'])}", dict(reference))

    def find_existing_node(self):
        try:
            identifier = self._node_id(self.destination_node.text())
            resources = self.session.mesh_view()["node_resources"].get(identifier, ())
            if len(resources) != 1:
                raise PrepError("invalid_reference", "That existing node is missing or belongs to more than one resource.")
            self._offer_node({"resource_id": resources[0], "entity_kind": "node", "local_id": identifier})
            self.status.setText("Review the resource-qualified target, then add the shared-node link.")
        except Exception as exc:
            self.destination_choice.clear()
            self._show_error(exc)

    def use_selected_node(self):
        try:
            references = self.session.selection()["refs"]
            if len(references) != 1:
                raise PrepError("invalid_reference", "Select exactly one existing node in the model.")
            self.destination_node.setText(str(references[0]["local_id"]))
            self._offer_node(references[0])
        except Exception as exc:
            self.destination_choice.clear()
            self._show_error(exc)

    def add_shared_node(self):
        try:
            self._guard()
            identifier = self._node_id(self.source_node.text())
            if not any(row[0] == "NODE" and row[1] == identifier for row in self._source_ids):
                raise PrepError("invalid_reference", "Prepare this source first and choose one of its original NODE IDs.")
            reference = self.destination_choice.currentData()
            if not isinstance(reference, dict):
                raise PrepError("invalid_reference", "Find or select an existing node before adding the link.")
            self._offer_node(reference)
            self._shared[identifier] = dict(reference)
            self.clear_mapping_entry()
            self._refresh_shared()
            self._invalidate("Shared-node links changed. Prepare a new preview to validate them.")
        except Exception as exc:
            self._show_error(exc)

    def _refresh_shared(self):
        self.shared_model.replace([(original, reference["local_id"], self._resource_label(reference["resource_id"]))
                                   for original, reference in sorted(self._shared.items())])

    def remove_shared_node(self):
        index = self.shared_table.currentIndex()
        if index.isValid():
            del self._shared[self.shared_model.rows[index.row()][0]]
            self._refresh_shared()
            self._invalidate("Shared-node links changed. Prepare a new preview to validate them.")

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Independent RAD source", "", "Radioss decks (*.rad);;All files (*)")
        if path:
            self.source.setText(path)

    def prepare_preview(self):
        if self._task is not None or self._closing:
            return False
        try:
            self._guard()
            if self._entry_dirty:
                raise PrepError("draft_pending", "Add or clear the unfinished shared-node entry before preparing the preview.")
            path = self.source.text().strip()
            if not path:
                raise PrepError("invalid_source", "Choose an independent RAD source file.")
            self._invalidate()
            shared = {key: dict(value) for key, value in self._shared.items()}
            self._task_generation = self._generation
            self._task = FileTask(lambda: self.session.plan_import_source(path, shared_node_map=shared))
            self._jobs.append(self._task)
            self._task.signals.complete.connect(self._planned)
            self._task.signals.failed.connect(self._planning_failed)
            self._set_planning(True)
            self.status.setText("Reading source files and preparing native ID correspondence…")
            QThreadPool.globalInstance().start(self._task)
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def _set_planning(self, active):
        for widget in (self.source, self.browse_button, self.preview_button, self.source_node,
                       self.destination_node, self.find_node_button, self.use_selection_button,
                       self.add_mapping_button, self.remove_mapping_button, self.clear_entry_button):
            widget.setEnabled(not active)
        self._sync_apply()
        self._sync_instance_actions()

    def _planned(self, plan):
        self._task = None
        if self._closing:
            self._release_subscription()
            return
        self._set_planning(False)
        if self._task_generation != self._generation:
            self._invalidate("The source or model changed during preparation. Prepare again.")
            return
        current = self.session.describe()
        if any(plan[key] != current[key] for key in ("document_id", "revision", "document_epoch")):
            self._invalidate("The open model changed during preparation. Prepare a new preview.")
            return
        self._plan = plan
        self._source_ids = plan["source"]["id_map"]
        self.native_model.show_source(plan["source"], plan["collisions"])
        self.files_model.replace([(item["original_path"], item["logical_path"]) for item in plan["source"]["files"]])
        self.summary.setText(f"{plan['source']['name']} · {len(plan['source']['files'])} source files · "
            f"{plan['node_count']} nodes · {plan['element_count']} elements\n"
            f"{len(plan['collisions'])} native ID collisions will be renumbered; "
            f"{len(plan['source']['shared_nodes'])} nodes explicitly shared. Original bytes are archived unchanged.")
        self.status.setText("Preview ready. Review all ID changes and shared-node links before Apply.")
        self._sync_apply()

    def _planning_failed(self, error):
        self._task = None
        if self._closing:
            self._release_subscription()
        else:
            self._set_planning(False)
            self._invalidate()
            self._show_error(error)

    def _sync_apply(self):
        self.apply_button.setEnabled(bool(self._plan and self.reviewed.isChecked()
            and self._task is None and not self._entry_dirty and not self._closing))

    def apply_import(self):
        try:
            self._guard()
            if self._task is not None or self._closing or self._entry_dirty:
                raise PrepError("draft_pending", "Finish the source preview and shared-node entry before applying.")
            if self._plan is None or not self.reviewed.isChecked():
                raise PrepError("review_required", "Prepare and review the native ID changes before applying.")
            self._committing = True
            try:
                plan = self._plan
                self.result = self.session.import_source(plan["plan_id"], expected_revision=plan["revision"],
                                                        expected_document_id=plan["document_id"])
            finally:
                self._committing = False
            self._invalidate()
            self.imported.emit(self.result)
            self.refresh()
            self.tabs.setCurrentIndex(1)
            self.status.setText("Source imported. Undo restores the complete previous model.")
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def refresh(self):
        """Reload the actual archived-source query without committing a draft."""
        self._sources = self.session.source_models()
        self.sources_model.replace([(item["name"], len(item["files"]), len(item["id_map"]),
            len(item["shared_nodes"]), item["id"]) for item in self._sources])
        if self._sources:
            self.sources_table.selectRow(len(self._sources) - 1)
        else:
            self.archive_native_model.show_source()
            self.archive_files_model.replace([])
        self._refresh_instances()

    def _source_selected(self, current, previous):
        if not current.isValid() or current.row() >= len(self._sources):
            return
        source = self._sources[current.row()]
        self.archive_native_model.show_source(source)
        self.archive_files_model.replace([(item["original_path"], item["logical_path"]) for item in source["files"]])

    def _session_changed(self, event):
        if self._closing or self._committing:
            return
        if self._plan is not None:
            current = self.session.describe()
            if any(self._plan[key] != current[key] for key in ("document_id", "revision", "document_epoch")):
                self._invalidate("The open model changed. Prepare and review a new source preview.")
        self.refresh()

    def _release_subscription(self):
        if not self._unsubscribed:
            self._unsubscribe()
            self._unsubscribed = True

    def _finished(self, _):
        self._closing = True
        self._plan = None
        self._sync_apply()
        self._instance_review = self._instance_selected_review = None
        self._sync_instance_actions()
        # Planning uses a separate session snapshot. The host may delete this
        # closed dialog while the read finishes; Qt disconnects its callbacks.
        self._release_subscription()


class _ReconnectModel(_TableModel):
    """Only the selected stale group's members are presented, without widgets."""

    def __init__(self, parent=None):
        super().__init__(("Old native ID", "Explicit current target", "Review"), parent)
        self.mapping = {}
        self.labels = {}
        self.dropped = frozenset()

    def show_members(self, members, mapping, labels, *, dropped=()):
        self.mapping, self.labels = mapping, labels
        self.dropped = frozenset(dropped)
        self.replace(members)

    def value(self, row, column):
        identifier = self.rows[row]
        if column == 0:
            return identifier
        if column == 1:
            if identifier in self.dropped:
                return "Remove old membership"
            return self.labels.get(identifier, "")
        if identifier in self.dropped:
            return "Explicit Drop"
        return "Explicit link" if identifier in self.mapping else "Needs current target"


class PreparedMeshDialog(QDialog):
    """Review a prepared mesh replacement, then explicitly reconnect stale groups.

    ``changed`` reports one completed document command. The host supplies draft
    and busy guards and refreshes its model view when this signal is emitted.
    Closing a pending file read discards its result and never replaces a mesh.
    """

    changed = Signal(object)
    sessionEvent = Signal(dict)

    def __init__(self, session, parent=None, *, has_draft=None, is_busy=None):
        super().__init__(parent)
        self.session = session
        self.has_draft = has_draft or (lambda: False)
        self.is_busy = is_busy or (lambda: False)
        self.last_result = None
        self._plan = self._task = None
        self._reconnect_plan = None
        self._jobs = []
        self._generation = 0
        self._closing = self._committing = self._refreshing = False
        self._unsubscribed = False
        self._stamp = None
        self._relations = {}
        self._mapping, self._labels = {}, {}
        self._dropped = set()
        self._cards = {}
        self.setObjectName("preparedMeshDialog")
        self.setWindowTitle("Prepared mesh and stale targets")
        self.resize(1020, 760)
        self.setMinimumSize(680, 500)
        column = QVBoxLayout(self)
        self.tabs = QTabWidget()
        column.addWidget(self.tabs, 1)
        self._build_replacement_tab()
        self._build_reconnection_tab()
        self.conditions_model = _TableModel(("Affected condition", "Stale target groups"), self)
        self.tabs.addTab(_table(self.conditions_model, "staleMeshConditions"), "Affected conditions")
        self.reconnect_details = QTextBrowser()
        self.reconnect_details.setObjectName("reconnectionReview")
        self.tabs.addTab(self.reconnect_details, "Reconnection review")
        column.addWidget(self.reconnect_controls)
        self.tabs.currentChanged.connect(lambda index: self.reconnect_controls.setVisible(index in (1, 3)))
        self.reconnect_controls.hide()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setObjectName("preparedMeshStatus")
        column.addWidget(self.status)
        row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh mesh relationships")
        self.refresh_button.clicked.connect(self.refresh)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        row.addWidget(self.refresh_button)
        row.addStretch()
        row.addWidget(self.close_button)
        column.addLayout(row)
        self.resource.currentIndexChanged.connect(self._replacement_changed)
        self.source.textChanged.connect(self._replacement_changed)
        self.sessionEvent.connect(self._session_changed)
        self._unsubscribe = session.subscribe(self.sessionEvent.emit)
        self.destroyed.connect(self._unsubscribe)
        self.finished.connect(self._finished)
        self.refresh()

    def _build_replacement_tab(self):
        page = QWidget()
        column = QVBoxLayout(page)
        policy = QLabel("Replace one existing mesh-only INCLUDE using a prepared file with the same component headers. This does not generate a mesh. Every affected group or surface becomes stale, even when native IDs are unchanged. Reconnect targets before analysis export.")
        policy.setWordWrap(True)
        column.addWidget(policy)
        form = QFormLayout()
        self.resource = QComboBox()
        self.resource.setObjectName("preparedMeshResource")
        self.resource.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.resource.setMinimumContentsLength(24)
        form.addRow("Existing INCLUDE", self.resource)
        row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setObjectName("preparedMeshPath")
        self.source.setPlaceholderText("Choose a prepared mesh-only INCLUDE")
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self.browse_source)
        self.preview_button = QPushButton("Prepare preview")
        self.preview_button.clicked.connect(self.prepare_preview)
        row.addWidget(self.source, 1)
        row.addWidget(self.browse_button)
        row.addWidget(self.preview_button)
        form.addRow("Prepared file", row)
        column.addLayout(form)
        self.summary = QLabel("Prepare a preview to review the affected target groups before replacing the mesh.")
        self.summary.setWordWrap(True)
        column.addWidget(self.summary)
        self.targets_model = _TableModel(("Target group", "Family", "Old members", "New mesh revision"), self)
        self.targets_table = _table(self.targets_model, "replacementStaleTargets")
        self.targets_table.setColumnWidth(0, 360)
        column.addWidget(self.targets_table, 1)
        row = QHBoxLayout()
        self.replacement_reviewed = QCheckBox("I reviewed the replacement and targets that will become stale")
        self.replacement_reviewed.toggled.connect(self._sync_actions)
        self.replace_button = QPushButton("Apply replacement")
        self.replace_button.clicked.connect(self.apply_replacement)
        row.addWidget(self.replacement_reviewed, 1)
        row.addWidget(self.replace_button)
        column.addLayout(row)
        self.tabs.addTab(page, "Replace prepared mesh")

    def _build_reconnection_tab(self):
        page = QWidget()
        column = QVBoxLayout(page)
        self.relationship_status = QLabel()
        self.relationship_status.setWordWrap(True)
        column.addWidget(self.relationship_status)
        self.target_group = QComboBox()
        self.target_group.setObjectName("staleMeshTarget")
        self.target_group.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.target_group.setMinimumContentsLength(24)
        self.target_group.currentIndexChanged.connect(self._group_changed)
        column.addWidget(self.target_group)
        hint = QLabel("Decide every old member: add an exact current target or explicitly Drop its membership. Drop preserves the mesh entity. Keep at least one current target and preview any removal before Apply. Same numbers are never filled automatically; other groups remain stale.")
        hint.setWordWrap(True)
        column.addWidget(hint)
        self.reconnect_model = _ReconnectModel(self)
        self.reconnect_table = _table(self.reconnect_model, "explicitMeshReconnection")
        header = self.reconnect_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for index in (0, 2):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.reconnect_table.setMinimumHeight(130)
        self.reconnect_table.selectionModel().currentRowChanged.connect(self._member_changed)
        column.addWidget(self.reconnect_table, 1)
        form = QFormLayout()
        row = QHBoxLayout()
        self.current_target = QLineEdit()
        self.current_target.setObjectName("reconnectCurrentId")
        self.current_target.setPlaceholderText("Exact current node, element or PART ID")
        self.current_target.textChanged.connect(self._target_edited)
        self.find_target_button = QPushButton("Find current target")
        self.find_target_button.clicked.connect(self.find_current_target)
        row.addWidget(self.current_target, 1)
        row.addWidget(self.find_target_button)
        form.addRow("Current native ID", row)
        self.target_choice = QComboBox()
        self.target_choice.setObjectName("reconnectTypedTarget")
        self.target_choice.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.target_choice.setMinimumContentsLength(24)
        form.addRow("Typed target", self.target_choice)
        column.addLayout(form)
        row = QHBoxLayout()
        self.link_button = QPushButton("Add explicit link")
        self.link_button.clicked.connect(self.add_link)
        self.remove_link_button = QPushButton("Clear selected decision")
        self.remove_link_button.clicked.connect(self.remove_link)
        self.clear_entry_button = QPushButton("Clear entry")
        self.clear_entry_button.clicked.connect(self._clear_entry)
        self.drop_member_button = QPushButton("Drop selected old member")
        self.drop_member_button.setToolTip("Remove this old membership after final preview and Apply; preserve its mesh entity.")
        self.drop_member_button.clicked.connect(self.drop_member)
        row.addWidget(self.link_button)
        row.addWidget(self.remove_link_button)
        row.addWidget(self.clear_entry_button)
        row.addWidget(self.drop_member_button)
        row.addStretch()
        column.addLayout(row)
        self.reconnect_table.selectionModel().selectionChanged.connect(lambda *_: self._sync_actions())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Reconnect stale targets")
        self.reconnect_controls = QWidget()
        controls = QVBoxLayout(self.reconnect_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        self.coalesce_targets = QCheckBox("Allow repeated node targets to form one set")
        self.coalesce_targets.toggled.connect(lambda _: self._invalidate_reconnection())
        controls.addWidget(self.coalesce_targets)
        self.link_counts = QLabel()
        self.link_counts.setWordWrap(True)
        controls.addWidget(self.link_counts)
        row = QHBoxLayout()
        self.reconnect_preview_button = QPushButton("Preview final mapping")
        self.reconnect_preview_button.clicked.connect(self.prepare_reconnection)
        row.addWidget(self.reconnect_preview_button)
        self.reconnect_reviewed = QCheckBox("Mapping reviewed")
        self.reconnect_reviewed.toggled.connect(self._sync_actions)
        self.reconnect_button = QPushButton("Apply reconnection")
        self.reconnect_button.clicked.connect(self.apply_reconnection)
        row.addWidget(self.reconnect_reviewed, 1)
        row.addWidget(self.reconnect_button)
        controls.addLayout(row)

    def _guard(self):
        if self._closing:
            raise PrepError("review_closed", "Open a new mesh review before applying changes.")
        if self.has_draft():
            raise PrepError("draft_pending", "Finish or discard the open model's draft before changing its mesh.")
        if self.is_busy():
            raise PrepError("owner_busy", "Wait for the open model's current operation before changing its mesh.")

    def _show_error(self, error):
        self.status.setText(f"{getattr(error, 'message', str(error))} [{getattr(error, 'code', 'mesh_review_failed')}]")

    def _current_stamp(self):
        state = self.session.describe()
        return tuple(state[key] for key in ("document_id", "revision", "document_epoch"))

    def _check_stamp(self):
        if self._current_stamp() != self._stamp:
            self.refresh()
            raise PrepError("stale_reference_mapping", "The model changed. Review its current mesh relationships again.")

    def _card_label(self, identifier):
        card = self._cards.get(identifier, {})
        return f"{card.get('keyword', '')} {card.get('title', '')} ({identifier})".strip()

    def _resource_label(self, identifier):
        resource = self.session.document.resources.get(identifier)
        return f"{getattr(resource, 'name', identifier)} ({identifier})"

    def _replacement_changed(self):
        if self._refreshing:
            return
        self._generation += 1
        self._plan = None
        self.replacement_reviewed.setChecked(False)
        self.targets_model.replace([])
        if hasattr(self, "status"):
            self.status.setText("Replacement input changed. Prepare a new preview.")
        self._sync_actions()

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Prepared mesh INCLUDE", "", "Mesh includes (*.inc *.rad);;All files (*)")
        if path:
            self.source.setText(path)

    def prepare_preview(self):
        if self._task is not None:
            return False
        try:
            self._guard()
            resource, path = self.resource.currentData(), self.source.text().strip()
            if not resource or not path:
                raise PrepError("invalid_mesh_replacement", "Choose an existing INCLUDE and its prepared mesh file.")
            self._replacement_changed()
            self._task_generation = self._generation
            self._task = FileTask(lambda: self.session.plan_mesh_replacement(resource, path))
            self._jobs.append(self._task)
            self._task.signals.complete.connect(self._planned)
            self._task.signals.failed.connect(self._planning_failed)
            self._set_planning(True)
            self.status.setText("Reading the prepared mesh and identifying stale target groups…")
            QThreadPool.globalInstance().start(self._task)
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def _set_planning(self, active):
        for widget in (self.resource, self.source, self.browse_button, self.preview_button):
            widget.setEnabled(not active)
        self._sync_actions()

    def _planned(self, plan):
        self._task = None
        if self._closing:
            self._release_subscription()
            return
        self._set_planning(False)
        stamp = tuple(plan[key] for key in ("document_id", "revision", "document_epoch"))
        if self._task_generation != self._generation or stamp != self._current_stamp():
            self._replacement_changed()
            self.status.setText("The model or replacement input changed. Prepare a new preview.")
            return
        self._plan = plan
        self.targets_model.replace([(self._card_label(key), value["family"], len(value["members"]), value["mesh_revision"])
                                    for key, value in plan["stale_targets"].items()])
        self.summary.setText(f"{plan['source']['name']} · resulting model: {plan['node_count']} nodes, "
            f"{plan['element_count']} elements · mesh revision {plan['mesh_revision']}\n"
            f"{len(plan['stale_targets'])} target groups will become stale. Replacement and stale markers form one Undo.")
        self.status.setText("Preview ready. Review the replacement and affected target groups before Apply.")
        self._sync_actions()

    def _planning_failed(self, error):
        self._task = None
        if self._closing:
            self._release_subscription()
        else:
            self._set_planning(False)
            self._replacement_changed()
            self._show_error(error)

    def apply_replacement(self):
        try:
            self._guard()
            if self._task is not None or self._plan is None or not self.replacement_reviewed.isChecked():
                raise PrepError("review_required", "Prepare and review the replacement before applying it.")
            plan = self._plan
            self._committing = True
            try:
                self.last_result = self.session.replace_prepared_mesh(plan["plan_id"],
                    expected_revision=plan["revision"], expected_document_id=plan["document_id"])
            finally:
                self._committing = False
            self.refresh()
            self.changed.emit(self.last_result)
            self.tabs.setCurrentIndex(1)
            self.status.setText("Mesh replaced. Review every stale target before analysis export.")
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def refresh(self):
        """Reload current stale markers, keeping mappings only for the same handle."""
        stamp = self._current_stamp()
        changed = stamp != self._stamp
        self._cards = {card["id"]: card for card in self.session.list_cards()}
        self._relations = self.session.mesh_relationships()
        current_resource = self.resource.currentData()
        self._refreshing = True
        self.resource.clear()
        for identifier, resource in self.session.document.resources.items():
            if getattr(resource, "is_include", False):
                self.resource.addItem(self._resource_label(identifier), identifier)
        index = self.resource.findData(current_resource)
        if index >= 0:
            self.resource.setCurrentIndex(index)
        self._refreshing = False
        self._stamp = stamp
        if changed:
            self._replacement_changed()
            self.target_group.blockSignals(True)
            self.target_group.clear()
            for identifier, stale in self._relations["stale_targets"].items():
                self.target_group.addItem(f"{self._card_label(identifier)} — {stale['family']}", identifier)
            self.target_group.blockSignals(False)
            self._group_changed()
        self.conditions_model.replace([(self._card_label(item["card_id"]), ", ".join(self._card_label(key) for key in item["stale_target_ids"]))
                                       for item in self._relations["conditions"]])
        self.relationship_status.setText(f"{len(self._relations['stale_targets'])} stale target groups; "
            f"{len(self._relations['conditions'])} affected conditions. Stale markers survive Save and reopen. "
            "Condition highlighting and analysis export remain blocked until their targets are reconnected.")
        self._sync_actions()

    def _group(self):
        return self._relations.get("stale_targets", {}).get(self.target_group.currentData())

    def _group_changed(self):
        had_links = bool(self._mapping or self._dropped)
        self._mapping, self._labels = {}, {}
        self._dropped.clear()
        self._invalidate_reconnection(reset_permission=True)
        self._clear_entry()
        group = self._group()
        self.reconnect_model.show_members(group["members"] if group else [], self._mapping, self._labels, dropped=self._dropped)
        if self.reconnect_model.rowCount():
            self.reconnect_table.selectRow(0)
        if had_links and hasattr(self, "status"):
            self.status.setText("The previous mapping review was cleared. No reconnection was committed.")
        self._sync_actions()

    def _member_changed(self, current, previous):
        self._clear_entry()

    def _clear_entry(self):
        self.current_target.clear()
        self.target_choice.clear()
        self._sync_actions()

    def _target_edited(self):
        self.target_choice.clear()
        self._invalidate_reconnection()

    def _invalidate_reconnection(self, *, reset_permission=False):
        if self._reconnect_plan is not None:
            self.session.cancel_mesh_reconnection(self._reconnect_plan["plan_id"])
        self._reconnect_plan = None
        if hasattr(self, "reconnect_details"):
            self.reconnect_details.clear()
        if reset_permission:
            self.coalesce_targets.blockSignals(True)
            self.coalesce_targets.setChecked(False)
            self.coalesce_targets.blockSignals(False)
        self.reconnect_reviewed.setChecked(False)
        self._sync_actions()

    def _reconnection_request(self):
        group = self._group()
        value = {"mesh_revision": group["mesh_revision"], "mapping": dict(self._mapping)}
        if self.coalesce_targets.isChecked():
            value["coalesce_duplicates"] = True
        if self._dropped:
            value["drop_members"] = [identifier for identifier in group["members"] if identifier in self._dropped]
        return {self.target_group.currentData(): value}

    def _complete_reconnection(self, group):
        return bool(group and self._mapping and not (set(self._mapping) & self._dropped)
                    and (set(self._mapping) | self._dropped) == set(group["members"]))

    def _selected_old_member(self):
        selected = self.reconnect_table.selectionModel().selectedRows()
        if len(selected) != 1:
            raise PrepError("invalid_reference", "Select one old member row first.")
        return self.reconnect_model.rows[selected[0].row()]

    def prepare_reconnection(self):
        from .mesh_target_text import reconnection_review_text
        try:
            self._guard(); self._check_stamp(); self._invalidate_reconnection()
            group = self._group()
            if (self._task is not None or not self._complete_reconnection(group)
                    or self.current_target.text().strip()):
                raise PrepError("review_required", "Map or explicitly Drop every old member, keep a current target and clear the unfinished entry before previewing.")
            self._reconnect_plan = self.session.plan_mesh_reconnection(self._reconnection_request(),
                expected_document_id=self._stamp[0], expected_revision=self._stamp[1])
            self.reconnect_details.setPlainText(reconnection_review_text(self.session, self._reconnect_plan))
            self.tabs.setCurrentIndex(3)
            self.status.setText("Review the final mapping, condition multipliers and unresolved targets before Apply.")
            self._sync_actions()
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def find_current_target(self):
        try:
            self._check_stamp()
            group = self._group()
            if not group or not self.reconnect_table.currentIndex().isValid():
                raise PrepError("invalid_reference", "Select an old member in a stale target group first.")
            identifier = SourceModelsDialog._node_id(self.current_target.text())
            if group["family"] == "SURF/PART":
                reference = self.session.resolve_part_reference(identifier)["card_id"]
                label = self._card_label(reference)
            else:
                kind = "node" if group["family"] == "GRNOD/NODE" else "element"
                reference = self.session.resolve_entity_reference(kind, identifier)["reference"]
                label = f"{kind.title()} {identifier} — {self._resource_label(reference['resource_id'])}"
            self.target_choice.clear()
            self.target_choice.addItem(label, reference)
            self.status.setText("Review the typed current target, then add this explicit link.")
        except Exception as exc:
            self.target_choice.clear()
            self._show_error(exc)

    def add_link(self):
        try:
            self._guard()
            self._check_stamp()
            identifier = self._selected_old_member()
            reference = self.target_choice.currentData()
            if reference is None:
                raise PrepError("invalid_reference", "Select an old member and find its current target first.")
            self._dropped.discard(identifier)
            self._mapping[identifier] = dict(reference) if isinstance(reference, dict) else reference
            self._labels[identifier] = self.target_choice.currentText()
            self.reconnect_model.show_members(self._group()["members"], self._mapping, self._labels, dropped=self._dropped)
            self._invalidate_reconnection(reset_permission=True)
            self._clear_entry()
            self.status.setText("Explicit link added to this review. The model is unchanged until Apply reconnection.")
        except Exception as exc:
            self._show_error(exc)

    def remove_link(self):
        try:
            self._guard(); self._check_stamp()
            identifier = self._selected_old_member()
            self._mapping.pop(identifier, None)
            self._labels.pop(identifier, None)
            self._dropped.discard(identifier)
            self.reconnect_model.show_members(self._group()["members"], self._mapping, self._labels, dropped=self._dropped)
            self._invalidate_reconnection(reset_permission=True)
            self._clear_entry()
            self.status.setText("Decision cleared. Map or explicitly Drop this old member again.")
        except Exception as exc:
            self._show_error(exc)

    def drop_member(self):
        try:
            self._guard(); self._check_stamp()
            identifier = self._selected_old_member()
            self._mapping.pop(identifier, None); self._labels.pop(identifier, None)
            self._dropped.add(identifier)
            self.reconnect_model.show_members(self._group()["members"], self._mapping, self._labels, dropped=self._dropped)
            self._invalidate_reconnection(reset_permission=True); self._clear_entry()
            self.status.setText(f"Old member {identifier} will be removed from this group after final review.")
        except Exception as exc:
            self._show_error(exc)

    def _sync_actions(self):
        if not hasattr(self, "reconnect_button"):
            return
        idle = self._task is None and not self._closing
        self.replace_button.setEnabled(bool(idle and self._plan and self.replacement_reviewed.isChecked()))
        group = self._group()
        complete = self._complete_reconnection(group)
        node_group = bool(group and group["family"] == "GRNOD/NODE")
        self.coalesce_targets.setEnabled(node_group)
        unique = len({(value["resource_id"], value["entity_kind"], value["local_id"]) if isinstance(value, dict) else value
                      for value in self._mapping.values()})
        repeated = unique < len(self._mapping)
        required = repeated or self.coalesce_targets.isChecked() or bool(self._dropped)
        if self._dropped:
            pending = len(group["members"]) - len(self._mapping) - len(self._dropped) if group else 0
            counts = f"{len(self._mapping)} mapped + {len(self._dropped)} dropped; {pending} pending → {unique} unique current targets. "
            note = "Keep at least one current target." if not unique else "Member removal requires a final preview."
        else:
            counts = f"{len(self._mapping)} / {len(group['members']) if group else 0} old links mapped → {unique} unique current targets. "
            note = "Other stale groups remain unreviewed."
        self.link_counts.setText(counts + ("Repeated targets require explicit permission and a final preview." if repeated else note))
        selected = len(self.reconnect_table.selectionModel().selectedRows()) == 1
        self.drop_member_button.setEnabled(bool(idle and group and selected))
        self.remove_link_button.setEnabled(bool(idle and group and selected))
        self.reconnect_preview_button.setEnabled(bool(idle and complete and (node_group or self._dropped) and not self.current_target.text().strip()))
        self.reconnect_button.setEnabled(bool(idle and complete and (not required or self._reconnect_plan)
                                             and self.reconnect_reviewed.isChecked()
                                             and not self.current_target.text().strip()))

    def apply_reconnection(self):
        try:
            self._guard()
            self._check_stamp()
            group = self._group()
            if (self._task is not None or not self._complete_reconnection(group)
                    or self.current_target.text().strip() or not self.reconnect_reviewed.isChecked()):
                raise PrepError("review_required", "Explicitly decide every old member, retain a current target and review the group before applying.")
            request = self._reconnection_request()
            if (self.coalesce_targets.isChecked() or self._dropped) and self._reconnect_plan is None:
                raise PrepError("review_required", "Preview and review this final coalescence or member removal before applying.")
            self._committing = True
            try:
                if self._reconnect_plan is not None:
                    self.last_result = self.session.apply_mesh_reconnection(self._reconnect_plan["plan_id"],
                        expected_document_id=self._stamp[0], expected_revision=self._stamp[1])
                else:
                    self.last_result = self.session.reconnect_mesh_targets(request,
                        expected_document_id=self._stamp[0], expected_revision=self._stamp[1])
            finally:
                self._committing = False
            self.refresh()
            self.changed.emit(self.last_result)
            self.status.setText("The reviewed group was reconnected in one command. Other stale groups still require review.")
            return True
        except Exception as exc:
            self._show_error(exc)
            return False

    def _session_changed(self, event):
        if not self._closing and not self._committing:
            self.refresh()

    def _release_subscription(self):
        if not self._unsubscribed:
            self._unsubscribe()
            self._unsubscribed = True

    def _finished(self, _):
        self._closing = True
        self._invalidate_reconnection(reset_permission=True)
        self._plan = None
        self._mapping.clear()
        self._dropped.clear()
        self._sync_actions()
        self._release_subscription()
