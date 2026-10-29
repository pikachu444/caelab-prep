"""Native Radioss document editor over the public application session API."""

from __future__ import annotations

import math
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDoubleValidator, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDockWidget, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QScrollArea, QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from .theme import STYLESHEET, icon


def _field_label(field):
    """Presentation labels; values and their unit context remain solver-owned."""
    name = field["name"]
    labels = {
        "density": "Density", "young_modulus": "Young's modulus",
        "poisson_ratio": "Poisson's ratio", "friction": "Friction coefficient",
        "thickness": "Shell thickness", "vx": "Initial velocity X",
        "vy": "Initial velocity Y", "vz": "Initial velocity Z",
        "tx": "Translation X", "ty": "Translation Y", "tz": "Translation Z",
        "rx": "Rotation X", "ry": "Rotation Y", "rz": "Rotation Z",
    }
    if name in labels:
        return labels[name]
    parts = name.split("_")
    if len(parts) == 3 and parts[0] == "point" and parts[1].isdigit() and parts[2] in ("x", "y"):
        return f"Point {int(parts[1]) + 1} · {parts[2].upper()}"
    return str(field.get("label") or name.replace("_", " ").capitalize())


class _TaskSignals(QObject):
    complete = Signal(object)
    failed = Signal(object)


class _FileTask(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _TaskSignals()

    def run(self):
        try:
            result = self.function()
        except Exception as exc:
            self.signals.failed.emit(exc)
        else:
            self.signals.complete.emit(result)


class MainWindow(QMainWindow):
    """Presentation of one PrepSession; editing never bypasses its commands."""

    operationFinished = Signal(str, bool)
    selectionChanged = Signal(dict)
    _sessionEvent = Signal(object)

    def __init__(self, session=None, *, enable_viewport: bool = True):
        super().__init__()
        if session is None:
            from caelab_prep.application.session import PrepSession
            session = PrepSession()
        self.session = session
        self._busy = False
        self._active_task = None
        self._project_path = None
        self._source_path = None
        self._selected_card_id = None
        self._editor_revision = None
        self._updating = False
        self._allow_close = False
        self._closed = False
        self._last_presented_document = None
        self._last_presented_revision = -1
        self.field_editors = {}
        self._field_specs = {}
        self._settings = QSettings("CAELab", "Prep")
        self.setObjectName("caelabPrepWindow")
        self.setWindowTitle("CAELab Prep")
        self.resize(1320, 840)
        self.setMinimumSize(900, 600)
        self.setDockOptions(QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks)
        self.setStyleSheet(STYLESHEET)
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_viewport(enable_viewport)
        self._create_model_dock()
        self._create_properties_dock()
        self._create_messages_dock()
        self.resizeDocks([self.model_dock, self.properties_dock], [270, 330], Qt.Orientation.Horizontal)
        self.resizeDocks([self.messages_dock], [125], Qt.Orientation.Vertical)
        self._counts = QLabel()
        self._counts.setContentsMargins(8, 0, 10, 0)
        self.statusBar().addPermanentWidget(self._counts)
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(160)
        self._progress.setRange(0, 0)
        self._progress.hide()
        self.statusBar().addPermanentWidget(self._progress)
        geometry = self._settings.value("windowGeometry")
        state = self._settings.value("windowState")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state, 1)
        self._sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = self.session.subscribe(self._sessionEvent.emit)
        self.refresh_document(rebuild_viewport=bool(self._summary().get("document_id")))

    def _action(self, key, label, callback, shortcut=None, *, checkable=False):
        action = QAction(icon(key), label, self)
        if shortcut:
            action.setShortcut(shortcut)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        return action

    def _create_actions(self):
        self.open_rad_action = self._action("open", "Open Radioss deck…", self.open_rad_dialog, QKeySequence.StandardKey.Open)
        self.open_project_action = self._action("project", "Open project…", self.open_project_dialog, "Ctrl+Shift+O")
        self.save_action = self._action("save", "Save project", self.save_project_dialog, QKeySequence.StandardKey.Save)
        self.save_as_action = self._action("save", "Save project as…", lambda: self.save_project_dialog(force_new=True), QKeySequence.StandardKey.SaveAs)
        self.export_action = self._action("export", "Export Radioss deck…", self.export_rad_dialog, "Ctrl+E")
        self.undo_action = self._action("undo", "Undo", lambda: self._history("undo"), QKeySequence.StandardKey.Undo)
        self.redo_action = self._action("redo", "Redo", lambda: self._history("redo"), QKeySequence.StandardKey.Redo)
        self.reload_properties_action = self._action("card", "Reload properties", self._reload_properties, "Ctrl+R")
        self.fit_action = self._action("fit", "Fit model", self._fit, "F")
        self.iso_action = self._action("iso", "Isometric view", self._isometric, "0")
        self.edges_action = self._action("edges", "Show mesh edges", self._toggle_edges, checkable=True)
        self.edges_action.setChecked(True)

    def _create_menus(self):
        menu = self.menuBar().addMenu("&File")
        menu.addActions([self.open_rad_action, self.open_project_action])
        menu.addSeparator()
        menu.addActions([self.save_action, self.save_as_action, self.export_action])
        menu.addSeparator()
        quit_action = menu.addAction("Exit", self.close)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        edit = self.menuBar().addMenu("&Edit")
        edit.addActions([self.undo_action, self.redo_action])
        edit.addSeparator()
        edit.addAction(self.reload_properties_action)
        self._view_menu = self.menuBar().addMenu("&View")
        self._view_menu.addActions([self.fit_action, self.iso_action, self.edges_action])

    def _create_toolbar(self):
        toolbar = QToolBar("Document", self)
        toolbar.setObjectName("documentToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)
        toolbar.addActions([self.open_rad_action, self.open_project_action, self.save_action, self.export_action])
        toolbar.addSeparator()
        toolbar.addActions([self.undo_action, self.redo_action])
        toolbar.addSeparator()
        toolbar.addActions([self.fit_action, self.iso_action, self.edges_action])
        toolbar.addSeparator()
        label = QLabel("  Select  ")
        toolbar.addWidget(label)
        self.pick_mode = QComboBox()
        self.pick_mode.setObjectName("pickMode")
        self.pick_mode.addItems(["Elements", "Nodes"])
        self.pick_mode.currentIndexChanged.connect(self._pick_mode_changed)
        toolbar.addWidget(self.pick_mode)

    def _create_viewport(self, enabled):
        self.viewport = None
        if enabled:
            try:
                from .viewport import MeshViewport
                self.viewport = MeshViewport(self)
                self.viewport.entityPicked.connect(self._entity_picked)
                self.viewport.diagnostic.connect(self._append_message)
                self.setCentralWidget(self.viewport)
            except Exception as exc:
                label = QLabel(f"3D viewer could not start.\n{exc}")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setWordWrap(True)
                self.setCentralWidget(label)
        else:
            label = QLabel("3D viewer disabled for this session")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setCentralWidget(label)

    def _dock(self, name, title, widget, area):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        self._view_menu.addAction(dock.toggleViewAction())
        return dock

    def _create_model_dock(self):
        self.model_tree = QTreeWidget()
        self.model_tree.setObjectName("modelTree")
        self.model_tree.setHeaderHidden(True)
        self.model_tree.setIndentation(17)
        self.model_tree.setUniformRowHeights(True)
        self.model_tree.setAlternatingRowColors(False)
        self.model_tree.currentItemChanged.connect(self._card_selected)
        self.model_dock = self._dock("modelDock", "Model", self.model_tree, Qt.DockWidgetArea.LeftDockWidgetArea)

    def _create_properties_dock(self):
        panel = QWidget()
        panel.setAutoFillBackground(True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 15, 14, 12)
        layout.setSpacing(9)
        self.property_title = QLabel("Properties")
        self.property_title.setObjectName("propertyTitle")
        self.property_title.setWordWrap(True)
        self.property_subtitle = QLabel("Select an item in the model tree")
        self.property_subtitle.setObjectName("propertySubtitle")
        self.property_subtitle.setWordWrap(True)
        layout.addWidget(self.property_title)
        layout.addWidget(self.property_subtitle)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._form_host = QWidget()
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(0, 7, 0, 0)
        self._form.setHorizontalSpacing(12)
        self._form.setVerticalSpacing(12)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scroll.setWidget(self._form_host)
        layout.addWidget(scroll, 1)
        self.units_note = QLabel("Values retain the units declared by the input deck.\nA field is applied when you finish editing it.")
        self.units_note.setObjectName("unitsNote")
        self.units_note.setWordWrap(True)
        layout.addWidget(self.units_note)
        tabs = QTabWidget()
        tabs.addTab(panel, "Properties")
        self.raw_source = QPlainTextEdit()
        self.raw_source.setReadOnly(True)
        self.raw_source.setFont(QFont("Consolas", 10))
        self.raw_source.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        tabs.addTab(self.raw_source, "Card source")
        self.properties_dock = self._dock("propertiesDock", "Properties", tabs, Qt.DockWidgetArea.RightDockWidgetArea)
        self.properties_dock.setMinimumWidth(270)

    def _create_messages_dock(self):
        self.messages = QTreeWidget()
        self.messages.setObjectName("messages")
        self.messages.setColumnCount(2)
        self.messages.setHeaderLabels(["Level", "Message"])
        self.messages.setRootIsDecorated(False)
        self.messages.setColumnWidth(0, 90)
        self.messages.setWordWrap(True)
        self.messages_dock = self._dock("messagesDock", "Messages", self.messages, Qt.DockWidgetArea.BottomDockWidgetArea)

    def _summary(self):
        return self.session.describe()

    def _session_changed(self, event):
        """Session observers run on any caller thread; this slot is queued to Qt."""
        if self._closed or self._busy:
            return
        kind = event.get("kind")
        same_document = event.get("document_id") == self._last_presented_document
        if kind == "selection":
            if self.viewport:
                self.viewport.set_selection(self.session.selection())
            return
        if kind == "field" and same_document and event.get("revision", -1) <= self._last_presented_revision:
            return
        drafts = self._text_drafts() if same_document else {}
        draft_revision = self._editor_revision
        self.refresh_document(rebuild_viewport=kind == "document")
        self._restore_text_drafts(drafts)
        if drafts:
            self._editor_revision = draft_revision
            self._append_message("The model changed while a property edit was unfinished. Reload properties (Ctrl+R) to discard the draft and read current values.")

    def refresh_document(self, *, rebuild_viewport=False):
        """Refresh from the canonical session, also usable by an IPC coordinator."""
        if self._busy:
            return
        summary = self._summary()
        self._project_path = Path(summary["project_path"]) if summary.get("project_path") else None
        self._source_path = Path(summary["source_path"]) if summary.get("source_path") else None
        self._updating = True
        try:
            name = str(summary.get("name") or "Untitled")
            dirty = bool(summary.get("dirty"))
            self.setWindowTitle(f"{name}{' *' if dirty else ''} — CAELab Prep")
            self._refresh_tree()
            self._refresh_fields()
            self._refresh_actions(summary)
            self._counts.setText(f"{summary.get('node_count', 0):,} nodes  ·  {summary.get('element_count', 0):,} elements")
            self.messages.clear()
            for diagnostic in summary.get("diagnostics", []):
                if isinstance(diagnostic, dict):
                    level = str(diagnostic.get("severity", diagnostic.get("level", "Info"))).title()
                    message = str(diagnostic.get("message", diagnostic))
                else:
                    level, message = "Info", str(diagnostic)
                self.messages.addTopLevelItem(QTreeWidgetItem([level, message]))
            if rebuild_viewport and self.viewport is not None:
                try:
                    self.viewport.set_mesh(self.session.mesh_view())
                except Exception as exc:
                    self._append_message(f"Mesh display failed: {exc}", "Error")
            if self.viewport is not None and summary.get("document_id"):
                self.viewport.set_selection(self.session.selection())
            self._last_presented_document = summary.get("document_id")
            self._last_presented_revision = summary.get("revision", 0)
            self.statusBar().showMessage("Ready" if summary.get("document_id") else "Open a Radioss deck or a saved project")
        finally:
            self._updating = False

    def _refresh_actions(self, summary=None):
        summary = summary or self._summary()
        loaded = bool(summary.get("document_id"))
        for action in [self.open_rad_action, self.open_project_action]:
            action.setEnabled(not self._busy)
        for action in [self.save_action, self.save_as_action, self.export_action]:
            action.setEnabled(loaded and not self._busy)
        self.undo_action.setEnabled(bool(summary.get("can_undo")) and not self._busy)
        self.redo_action.setEnabled(bool(summary.get("can_redo")) and not self._busy)
        self.reload_properties_action.setEnabled(loaded and not self._busy)
        self._form_host.setEnabled(not self._busy)
        self.model_tree.setEnabled(not self._busy)
        if self.viewport:
            self.viewport.setEnabled(not self._busy)
        self.pick_mode.setEnabled(loaded and self.viewport is not None and not self._busy)
        for action in [self.fit_action, self.iso_action, self.edges_action]:
            action.setEnabled(loaded and self.viewport is not None)

    def _refresh_tree(self):
        previous = self._selected_card_id
        self.model_tree.blockSignals(True)
        self.model_tree.clear()
        if not self._summary().get("document_id"):
            self._selected_card_id = None
            self.model_tree.blockSignals(False)
            return
        categories = {}
        selected = None
        for card in self.session.list_cards():
            category = str(card.get("category") or "Other cards")
            if category not in categories:
                root = QTreeWidgetItem([category])
                root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                root.setExpanded(True)
                self.model_tree.addTopLevelItem(root)
                categories[category] = root
            title = str(card.get("title") or card.get("keyword") or "Card")
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, card["id"])
            item.setData(0, Qt.ItemDataRole.UserRole + 1, card)
            item.setToolTip(0, str(card.get("keyword", "")))
            category_lower = category.lower()
            symbol = "material" if "material" in category_lower else "constraint" if any(s in category_lower for s in ["constraint", "bound", "구속"]) else "card"
            item.setIcon(0, icon(symbol))
            categories[category].addChild(item)
            if card["id"] == previous:
                selected = item
        for root in categories.values():
            root.setExpanded(True)
        if selected:
            self.model_tree.setCurrentItem(selected)
        else:
            self._selected_card_id = None
        self.model_tree.blockSignals(False)

    def _card_selected(self, current, previous):
        if self._updating or self._busy:
            return
        target_id = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if not self._finish_pending_edits():
            self._focus_tree_card(self._selected_card_id)
            return
        self._selected_card_id = target_id
        self._focus_tree_card(target_id)
        self._refresh_fields()

    def _focus_tree_card(self, card_id):
        """Restore selection after a pending edit may have rebuilt the tree."""
        self.model_tree.blockSignals(True)
        found = False
        for i in range(self.model_tree.topLevelItemCount()):
            group = self.model_tree.topLevelItem(i)
            for j in range(group.childCount()):
                item = group.child(j)
                if item.data(0, Qt.ItemDataRole.UserRole) == card_id:
                    self.model_tree.setCurrentItem(item)
                    found = True
                    break
            if found:
                break
        self.model_tree.blockSignals(False)
        return found

    def select_card(self, card_id):
        """Select a model card through the same guarded interaction as the tree."""
        if self._busy or not self._finish_pending_edits():
            return False
        if not self._focus_tree_card(card_id):
            return False
        self._selected_card_id = card_id
        self._refresh_fields()
        return True

    def _clear_form(self):
        while self._form.rowCount():
            self._form.removeRow(0)
        self.field_editors = {}
        self._field_specs = {}

    def _refresh_fields(self):
        self._clear_form()
        if not self._selected_card_id:
            self.property_title.setText("Properties")
            self.property_subtitle.setText("Select an item in the model tree")
            self.raw_source.clear()
            return
        cards = {card["id"]: card for card in self.session.list_cards()}
        card = cards.get(self._selected_card_id)
        if card is None:
            self._selected_card_id = None
            return
        self.property_title.setText(str(card.get("title") or "Properties"))
        self.property_subtitle.setText(str(card.get("keyword") or ""))
        source = self.session.card_text(self._selected_card_id)
        if len(source) > 100_000:
            source = source[:100_000] + "\n… Card preview truncated; the full card is preserved in the document."
        self.raw_source.setPlainText(source)
        self._editor_revision = self._summary().get("revision")
        fields = self.session.card_fields(self._selected_card_id)
        units = fields[0].get("units", {}) if fields else {}
        unit_note = "Values use the input deck units; no unit conversion is applied."
        if units.get("unit_id") is not None:
            unit_note += f"\nMaterial unit system ID: {units['unit_id']} (card override)."
        elif units.get("global"):
            basis = units["global"]
            unit_note += "\nDeck basis: " + ", ".join(f"{key}: {value}" for key, value in basis.items()) + "."
        self.units_note.setText(unit_note + "\nA field is applied when you finish editing it.")
        if not fields:
            note = QLabel("This card is preserved in the deck.\nA property editor is not available for this card.")
            note.setWordWrap(True)
            self._form.addRow(note)
            return
        for field in fields:
            name = field["name"]
            value = field.get("value")
            field_type = field.get("type", "string")
            if field_type in ("bool", "boolean"):
                editor = QCheckBox("Fixed" if name in ("tx", "ty", "tz", "rx", "ry", "rz") else "Enabled")
                editor.setChecked(bool(value))
                editor.toggled.connect(lambda checked, n=name: self._commit_field(n, checked))
            elif field.get("options"):
                editor = QComboBox()
                for option in field["options"]:
                    if isinstance(option, dict):
                        editor.addItem(str(option.get("label", option.get("value"))), option.get("value"))
                    else:
                        editor.addItem(str(option), option)
                index = editor.findData(value)
                editor.setCurrentIndex(max(0, index))
                editor.activated.connect(lambda index, n=name, e=editor: self._commit_field(n, e.itemData(index)))
            else:
                editor = QLineEdit(str(value) if value is not None else "")
                editor.setObjectName("field_" + name)
                if field_type in ("float", "number"):
                    validator = QDoubleValidator(editor)
                    validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
                    editor.setValidator(validator)
                editor.editingFinished.connect(lambda n=name, e=editor: self._commit_text(n, e))
            editor.setEnabled(bool(field.get("writable", True)))
            editor.setToolTip(str(field.get("description", "Input deck units")))
            self.field_editors[name] = editor
            self._field_specs[name] = dict(field)
            label = QLabel(_field_label(field))
            label.setWordWrap(True)
            self._form.addRow(label, editor)

    def _commit_text(self, name, editor):
        if self._updating or not editor.isModified():
            return True
        spec = self._field_specs[name]
        try:
            text = editor.text().strip()
            field_type = spec.get("type")
            value = float(text) if field_type in ("float", "number") else int(text) if field_type in ("int", "integer") else text
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Enter a finite number")
        except (TypeError, ValueError) as exc:
            self._show_error(exc)
            return False
        return self._commit_field(name, value)

    def _commit_field(self, name, value):
        if self._updating or self._busy:
            return False
        spec = self._field_specs.get(name, {})
        if value == spec.get("value"):
            return True
        # A different editor may contain a validator's intermediate text ("1e").
        # Applying this field must not discard that unfinished user input.
        drafts = self._text_drafts(exclude=name)
        try:
            self.session.set_field(self._selected_card_id, name, value, expected_revision=self._editor_revision)
        except Exception as exc:
            self._show_error(exc)
            return False
        label = _field_label(spec) if spec else "Property"
        self.refresh_document()
        self._restore_text_drafts(drafts)
        self.statusBar().showMessage(f"{label} updated", 5000)
        return True

    def _text_drafts(self, *, exclude=None):
        return {key: editor.text() for key, editor in self.field_editors.items()
                if key != exclude and isinstance(editor, QLineEdit) and editor.isModified()}

    def _restore_text_drafts(self, drafts):
        for key, text in drafts.items():
            editor = self.field_editors.get(key)
            if isinstance(editor, QLineEdit):
                editor.setText(text)
                editor.setModified(True)

    def _reload_properties(self):
        if self._busy:
            return
        if self._text_drafts():
            answer = QMessageBox.question(self, "Unfinished input", "Discard unfinished property input and reload current model values?", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                return
        self._refresh_fields()

    def _finish_pending_edits(self):
        """A validator's intermediate text must never be silently discarded by Save."""
        for name in list(self.field_editors):
            editor = self.field_editors.get(name)
            if isinstance(editor, QLineEdit) and editor.isModified():
                if not self._commit_text(name, editor):
                    editor.setFocus()
                    return False
        return True

    def _history(self, command):
        if self._busy or not self._finish_pending_edits():
            return
        try:
            getattr(self.session, command)()
        except Exception as exc:
            self._show_error(exc)
            return
        self.refresh_document(rebuild_viewport=True)

    def _append_message(self, message, level="Warning"):
        self.messages.addTopLevelItem(QTreeWidgetItem([level, str(message)]))

    def _show_error(self, exc):
        message = str(getattr(exc, "message", str(exc)))
        self._append_message(message, "Error")
        self.messages_dock.show()
        self.statusBar().showMessage(message, 12000)

    def _start_task(self, label, function, on_success=None):
        if self._busy:
            return
        self._busy = True
        self._refresh_actions()
        self._progress.show()
        self.statusBar().showMessage(label + "…")
        task = _FileTask(function)
        self._active_task = task

        def done(result):
            self._busy = False
            self._active_task = None
            self._progress.hide()
            try:
                if on_success:
                    on_success(result)
                else:
                    self.refresh_document()
            except Exception as exc:
                self._refresh_actions()
                self._show_error(exc)
                self.operationFinished.emit(label, False)
            else:
                self.operationFinished.emit(label, True)

        def failed(exc):
            self._busy = False
            self._active_task = None
            self._progress.hide()
            self._refresh_actions()
            self._show_error(exc)
            self.operationFinished.emit(label, False)

        task.signals.complete.connect(done)
        task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)

    def _before_replace(self, continuation):
        if not self._finish_pending_edits():
            return
        if not self._summary().get("dirty"):
            continuation()
            return
        answer = QMessageBox.question(self, "Unsaved changes", "Save changes to the current project?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            self.save_project_dialog(on_saved=continuation)
        elif answer == QMessageBox.StandardButton.Discard:
            continuation()

    def open_rad_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Radioss deck", "", "Radioss decks (*.rad);;All files (*)")
        if filename:
            self.open_rad_file(filename)

    def open_rad_file(self, filename):
        if self._busy:
            return
        def loaded(_):
            self._source_path = Path(filename)
            self._project_path = None
            self._selected_card_id = None
            self.refresh_document(rebuild_viewport=True)
        self._before_replace(lambda: self._start_task("Open Radioss deck", lambda: self.session.open_rad(str(filename)), loaded))

    def open_project_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open CAELab Prep project", "", "CAELab Prep projects (*.caeprep);;All files (*)")
        if filename:
            self.open_project_file(filename)

    def open_project_file(self, filename):
        if self._busy:
            return
        def loaded(_):
            self._project_path = Path(filename)
            self._source_path = None
            self._selected_card_id = None
            self.refresh_document(rebuild_viewport=True)
        self._before_replace(lambda: self._start_task("Open project", lambda: self.session.open_project(str(filename)), loaded))

    def save_project_dialog(self, checked=False, *, force_new=False, on_saved=None):
        if self._busy:
            return
        if not self._finish_pending_edits():
            return
        path = None if force_new else self._project_path
        if path is None:
            default = self._source_path.with_suffix(".caeprep") if self._source_path else Path("model.caeprep")
            filename, _ = QFileDialog.getSaveFileName(self, "Save CAELab Prep project", str(default), "CAELab Prep projects (*.caeprep)")
            if not filename:
                return
            path = Path(filename)
            if not path.suffix:
                path = path.with_suffix(".caeprep")
        self.save_project_file(path, on_saved=on_saved)

    def save_project_file(self, filename, *, on_saved=None):
        if self._busy:
            return
        if not self._finish_pending_edits():
            return
        def saved(_):
            self._project_path = Path(filename)
            self.refresh_document()
            self.statusBar().showMessage("Project saved", 5000)
            if on_saved:
                on_saved()
        self._start_task("Save project", lambda: self.session.save_project(str(filename)), saved)

    def export_rad_dialog(self):
        if self._busy:
            return
        if not self._finish_pending_edits():
            return
        base = self._project_path or self._source_path or Path("model.rad")
        default = base.with_name(base.stem + "_export.rad")
        filename, _ = QFileDialog.getSaveFileName(self, "Export Radioss deck", str(default), "Radioss decks (*.rad)")
        if filename:
            self.export_rad_file(filename)

    def export_rad_file(self, filename):
        if self._busy:
            return
        if not self._finish_pending_edits():
            return
        def exported(_):
            self.refresh_document()
            self.statusBar().showMessage(f"Radioss deck exported to {filename}", 8000)
        self._start_task("Export Radioss deck", lambda: self.session.export_rad(str(filename)), exported)

    def _entity_picked(self, entity):
        if self._busy:
            return
        try:
            selection = self.session.select_entity(entity["kind"], entity["id"]) if entity.get("kind") else self.session.clear_selection()
        except Exception as exc:
            self._show_error(exc)
            return
        if self.viewport:
            self.viewport.set_selection(selection)
        self.selectionChanged.emit(selection)
        if not selection.get("ids"):
            self.statusBar().showMessage("Selection cleared")
            return
        text = f"{entity['kind'].capitalize()} {entity['id']}"
        if entity.get("part_id") is not None:
            text += f"  ·  Part {entity['part_id']}"
        self.statusBar().showMessage(text)

    def _pick_mode_changed(self, index):
        if self.viewport:
            self.viewport.set_pick_mode("node" if index else "element")

    def _fit(self):
        if self.viewport:
            self.viewport.fit_view()

    def _isometric(self):
        if self.viewport:
            self.viewport.isometric_view()

    def _toggle_edges(self, visible):
        if self.viewport:
            self.viewport.set_edges_visible(visible)

    def closeEvent(self, event: QCloseEvent):
        if self._busy:
            self.statusBar().showMessage("Wait for the current file operation to finish")
            event.ignore()
            return
        if not self._allow_close and not self._finish_pending_edits():
            event.ignore()
            return
        if not self._allow_close and self._summary().get("dirty"):
            answer = QMessageBox.question(self, "Unsaved changes", "Save changes before closing?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Save:
                event.ignore()
                self.save_project_dialog(on_saved=self._close_after_save)
                return
        self._settings.setValue("windowGeometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState(1))
        if self.viewport:
            self.viewport.shutdown()
        self._unsubscribe()
        self._closed = True
        event.accept()

    def _close_after_save(self):
        self._allow_close = True
        self.close()


def run(session=None, argv=None):
    app = QApplication.instance() or QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("CAELab Prep")
    app.setOrganizationName("CAELab")
    window = MainWindow(session)
    window.show()
    return app.exec()
