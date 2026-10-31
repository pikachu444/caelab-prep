"""Executable Qt-only material/curve workspace using the shared host contracts."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                              QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QToolBar,
                              QVBoxLayout, QWidget)

from ..application.contracts import ActionSpec, SetProperties
from ..application.neutral import CurveSession
from .actions import ActionRegistry
from .shell import FileEditCoordinator, FileTask, ViewportFrame, create_dock
from .theme import STYLESHEET
from .widgets import CurvePlot, CurveTable, ModelTree, PropertyEditor


class GalleryWindow(QMainWindow):
    """A real second provider consumer and reusable engineering component gallery."""

    _sessionEvent = Signal(object)
    operationFinished = Signal(str, bool)

    def __init__(self, session=None):
        super().__init__()
        self.session = session or CurveSession()
        self._target = None
        self._curve_ref = None
        self._revision = self.session.describe()["revision"]
        self._document_id = self.session.describe()["document_id"]
        self._document_epoch = self.session.describe().get("document_epoch")
        self._baseline = {}
        self._selecting = False
        self._closed = False
        self._busy = False
        self._active_task = None
        self.operation_state = None
        self.last_operation_result = None
        self._pending_selection = False
        self._allow_close = False
        self.actions = ActionRegistry(self)
        self.file_edits = FileEditCoordinator(
            self, has_draft=lambda: self._property_draft() or self.curve_table.has_draft(),
            finish=self._finish_drafts, discard=self.reload_values,
            is_dirty=lambda: bool(self.session.describe()["dirty"]),
            save=lambda continuation: self.save_dialog(on_success=continuation),
            capture=self._capture_drafts, restore=self._restore_drafts)
        self._settings = QSettings("CAELab", "ComponentGallery")
        self.setObjectName("caelabGallery")
        self.setWindowTitle("CAELab Materials — Composition workspace")
        self.resize(1280, 800)
        self.setMinimumSize(800, 560)
        self.setStyleSheet(STYLESHEET)
        self.setDockOptions(QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks)
        self._build_actions()
        self._build_workspace()
        self._sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = self.session.subscribe(self._sessionEvent.emit)
        geometry = self._settings.value("geometry")
        layout = self._settings.value("layout")
        if geometry:
            self.restoreGeometry(geometry)
        if layout:
            self.restoreState(layout, 1)
        self._refresh_tree()
        curves = [node.ref for node in self.session.tree_nodes() if node.ref.kind == "curve"]
        if curves:
            self.select_ref(curves[0])
        self._update_status()

    def _build_actions(self):
        def register(key, label, callback, shortcut="", *, icon="", capability="", contexts=()):
            return self.actions.register(ActionSpec(key, label, shortcut=shortcut, icon=icon,
                                         capability=capability, contexts=contexts), callback)
        self.open_action = register("file.open", "Open material document…", self.open_dialog, QKeySequence.StandardKey.Open, icon="open")
        self.save_action = register("file.save", "Save material document", self.save_dialog, QKeySequence.StandardKey.Save, icon="save", capability="save")
        self.save_as_action = register("file.save_as", "Save material document as…", lambda: self.save_dialog(force_new=True), QKeySequence.StandardKey.SaveAs, icon="save", capability="save")
        self.undo_action = register("edit.undo", "Undo", lambda: self._history("undo"), QKeySequence.StandardKey.Undo, icon="undo", capability="undo")
        self.redo_action = register("edit.redo", "Redo", lambda: self._history("redo"), QKeySequence.StandardKey.Redo, icon="redo", capability="undo")
        self.reload_action = register("edit.reload", "Revert drafts / reload values", self.reload_values, "Ctrl+R", icon="card")
        self.apply_action = register("edit.apply", "Apply properties", self.apply_properties, "Ctrl+Return", icon="apply", contexts=("object",))
        self.addAction(self.apply_action)
        self.unsupported_action = register("analysis.run", "Run solver — unavailable for this provider", lambda: None, icon="mesh", capability="solver_execution")
        self.catalogue_action = register("view.catalogue", "Browse component catalogue", self._show_catalogue, "Ctrl+Shift+G", icon="card")
        self.close_action = register("file.close", "Exit", self.close, QKeySequence.StandardKey.Quit, icon="card")
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addActions([self.open_action, self.save_action, self.save_as_action])
        file_menu.addSeparator()
        file_menu.addAction(self.close_action)
        edit = self.menuBar().addMenu("&Edit")
        edit.addActions([self.undo_action, self.redo_action, self.reload_action])
        self.view_menu = self.menuBar().addMenu("&View")
        self.view_menu.addAction(self.catalogue_action)
        toolbar = QToolBar("Document", self)
        toolbar.setObjectName("galleryDocumentToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.addActions([self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addActions([self.undo_action, self.redo_action])
        toolbar.addSeparator()
        toolbar.addAction(self.unsupported_action)
        toolbar.addSeparator()
        toolbar.addAction(self.catalogue_action)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.widgetForAction(self.catalogue_action).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

    def _build_workspace(self):
        self.tree = ModelTree()
        self.tree.nodeSelected.connect(self._select_target)
        self.model_dock = create_dock(self, "galleryObjects", "Model", self.tree,
                                      Qt.DockWidgetArea.LeftDockWidgetArea, self.view_menu)
        property_body = QWidget()
        layout = QVBoxLayout(property_body)
        layout.setContentsMargins(0, 0, 0, 8)
        self.properties = PropertyEditor()
        self.property_editor = self.properties
        layout.addWidget(self.properties, 1)
        row = QHBoxLayout()
        row.setContentsMargins(10, 0, 10, 0)
        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(self.reload_action.trigger)
        self.reload_action.changed.connect(lambda: self.revert_button.setEnabled(self.reload_action.isEnabled()))
        self.apply_button = QPushButton("Apply properties")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.clicked.connect(self.apply_action.trigger)
        self.apply_action.changed.connect(lambda: self.apply_button.setEnabled(self.apply_action.isEnabled()))
        row.addWidget(self.revert_button)
        row.addWidget(self.apply_button)
        layout.addLayout(row)
        self.properties_dock = create_dock(self, "galleryProperties", "Properties", property_body,
                                           Qt.DockWidgetArea.RightDockWidgetArea, self.view_menu)
        self.curve_table = CurveTable()
        self.curve_table.pointsEdited.connect(self._commit_curve)
        self.plot = CurvePlot()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.plot)
        splitter.addWidget(self.curve_table)
        splitter.setSizes([350, 250])
        self.viewport_frame = ViewportFrame(splitter, "Material curve", "Composition example · material and curve editing")
        self.setCentralWidget(self.viewport_frame)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumBlockCount(200)
        self.messages.setAccessibleName("Operation messages")
        self.messages.setPlainText("Material and curve composition example\nSelect a material or curve. Apply validates the entire draft; Undo restores one edit.\nBrowse component catalogue to inspect reusable controls and their states.")
        self.messages_dock = create_dock(self, "galleryMessages", "Messages", self.messages,
                                        Qt.DockWidgetArea.BottomDockWidgetArea, self.view_menu)
        self._build_asset_inspector()
        self.resizeDocks([self.model_dock, self.properties_dock], [260, 330], Qt.Orientation.Horizontal)
        self.resizeDocks([self.messages_dock], [95], Qt.Orientation.Vertical)
        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)

    def _build_asset_inspector(self):
        from .catalogue import CatalogueWidget
        self.catalogue = CatalogueWidget()
        self.assets_dock = create_dock(self, "galleryAssets", "Component catalogue", self.catalogue,
                                       Qt.DockWidgetArea.RightDockWidgetArea, self.view_menu)
        self.tabifyDockWidget(self.properties_dock, self.assets_dock)
        self.assets_dock.hide()

    def _show_catalogue(self):
        self.assets_dock.show()
        self.assets_dock.raise_()
        self.resizeDocks([self.assets_dock], [640], Qt.Orientation.Horizontal)

    @property
    def field_editors(self):
        return self.properties.editors

    def _refresh_tree(self):
        self.tree.set_nodes(self.session.tree_nodes())

    def select_ref(self, ref):
        if self._busy:
            return False
        self.tree.select_ref(ref)
        if self._target != ref and self.tree.selected_ref() == ref:
            self._select_target(ref)
        return self._target == ref

    def _select_target(self, ref):
        if self._busy or self._selecting or ref == self._target:
            return
        old = self._target
        if old is not None and not self._finish_drafts():
            self._selecting = True
            self.tree.select_ref(old)
            self._selecting = False
            return
        self._target = ref
        self.session.select(ref)
        self._load_properties()
        self._sync_curve_context()
        self.curve_table.setEnabled(ref.kind == "curve")
        self._update_status()

    def _load_properties(self):
        if self._target is None:
            return
        specs = self.session.properties(self._target)
        node = next(node for node in self.session.tree_nodes() if node.ref == self._target)
        self.properties.set_fields([spec for spec in specs if spec.kind != "table"],
                                   title=node.label, subtitle=f"{self._target.kind.capitalize()} properties")
        self._revision = self.session.describe()["revision"]
        self._document_id = self.session.describe()["document_id"]
        self._document_epoch = self.session.describe().get("document_epoch")
        self._baseline = self.properties.raw_values()
        self._baseline_units = self.properties.units()

    def _load_curve(self):
        if self._curve_ref is None:
            self.curve_table.set_points(())
            self.plot.set_points(())
            self.viewport_frame.title.setText("No associated curve")
            return
        spec = next(spec for spec in self.session.properties(self._curve_ref) if spec.kind == "table")
        axes = spec.components or ("X", "Y")
        self.curve_table.set_points(self.session.curve_points(self._curve_ref), headers=axes)
        self.plot.set_points(self.session.curve_points(self._curve_ref), x_label=f"X [{axes[0]}]", y_label=f"Y [{axes[1]}]")
        node = next(node for node in self.session.tree_nodes() if node.ref == self._curve_ref)
        self.viewport_frame.title.setText(node.label)

    def _sync_curve_context(self):
        if self._target is None:
            self._curve_ref = None
        elif self._target.kind == "curve":
            self._curve_ref = self._target
        else:
            self._curve_ref = next((spec.value for spec in self.session.properties(self._target)
                                    if spec.name == "reference_curve"), None)
        self._load_curve()

    def _property_draft(self):
        return self.properties.raw_values() != self._baseline or self.properties.units() != getattr(self, "_baseline_units", {})

    def _capture_drafts(self):
        same_document = self.session.describe().get("document_epoch") == self._document_epoch
        return (self._target, self.properties.raw_values(), self.properties.units(), dict(self._baseline),
                dict(getattr(self, "_baseline_units", {})), self.curve_table.draft_state(), self._pending_selection,
                self.session.curve_points(self._curve_ref) if self._curve_ref is not None and same_document else None)

    def _restore_drafts(self, draft):
        target, values, units, baseline, baseline_units, curve, pending, points = draft
        if self._target != target:
            self._target = target
            self.tree.blockSignals(True)
            self.tree.select_ref(target)
            self.tree.blockSignals(False)
            self._load_properties()
            self._sync_curve_context()
        self._baseline, self._baseline_units = baseline, baseline_units
        self._pending_selection = pending
        for name, unit in units.items():
            self.properties.unit_selectors[name].setCurrentText(unit)
        for name, value in values.items():
            editor = self.properties.editors.get(name)
            if hasattr(editor, "setText"):
                editor.setText(value)
            elif hasattr(editor, "editors"):
                for child, text in zip(editor.editors, value):
                    child.setText(text)
            elif hasattr(editor, "setChecked"):
                editor.setChecked(value)
            elif hasattr(editor, "findData"):
                editor.setCurrentIndex(editor.findData(value))
        if points is not None:
            self.curve_table.set_points(points)
        self.curve_table.restore_draft(curve)

    def _consume_pending_selection(self):
        if not self._pending_selection or self._property_draft() or self.curve_table.has_draft():
            return
        self._pending_selection = False
        self._target = self.session.active_object()
        self.tree.blockSignals(True)
        if self._target is not None:
            self.tree.select_ref(self._target)
            self._load_properties()
        else:
            self.tree.clearSelection()
            self.tree.selectionModel().clearCurrentIndex()
            self.properties.set_fields(())
            self._baseline = {}
            self._baseline_units = {}
        self.tree.blockSignals(False)
        self._sync_curve_context()
        self.curve_table.setEnabled(self._target is not None and self._target.kind == "curve")
        self._refresh_actions()

    def _failure(self, exc):
        message = str(exc)
        self.messages.appendPlainText(message)
        self.status.setText(message)

    def apply_properties(self):
        if self._busy:
            return False
        if self._target is None or not self._property_draft():
            self._consume_pending_selection()
            return True
        try:
            values = self.properties.values()
            self.session.submit(SetProperties(self._target, values, self._revision, self.properties.units()))
        except Exception as exc:
            self._failure(exc)
            return False
        self._load_properties()
        self._refresh_tree()
        if self._target.kind != "curve":
            self._sync_curve_context()
        elif self._curve_ref is not None:
            node = next(node for node in self.session.tree_nodes() if node.ref == self._curve_ref)
            self.viewport_frame.title.setText(node.label)
        self._update_status()
        self._consume_pending_selection()
        return True

    def _commit_curve(self, points):
        if self._busy or self._curve_ref is None:
            return False
        # One complete table is one command; the host owns its Undo boundary.
        try:
            self.session.set_curve_points(self._curve_ref, points, self._revision)
        except Exception as exc:
            self._failure(exc)
            return False
        self._revision = self.session.describe()["revision"]
        self._load_curve()
        if not self._property_draft():
            self._load_properties()
        self._update_status()
        self._consume_pending_selection()
        return True

    def _finish_drafts(self):
        if not self.apply_properties():
            return False
        if self.curve_table.has_draft():
            try:
                return self._commit_curve(self.curve_table.points())
            except ValueError as exc:
                self._failure(exc)
                return False
        return True

    def reload_values(self):
        if self._busy:
            return
        description = self.session.describe()
        if (description["document_id"] != self._document_id
                or description.get("document_epoch") != self._document_epoch):
            self._target = None
            self._curve_ref = None
            self._pending_selection = False
            self._refresh_tree()
            self.select_ref(self.session.tree_nodes()[0].ref)
            return
        self._load_properties()
        self._sync_curve_context()
        self._consume_pending_selection()
        self._update_status()

    def _history(self, method):
        if self._busy or not self._finish_drafts():
            return
        try:
            getattr(self.session, method)()
        except Exception as exc:
            self._failure(exc)
            return
        self.reload_values()
        self._refresh_tree()

    def _session_changed(self, event):
        if self._closed or self._busy:
            return
        description = self.session.describe()
        if event.get("kind") == "selection":
            selected = self.session.active_object()
            if selected != self._target:
                if self._property_draft() or self.curve_table.has_draft():
                    self._pending_selection = True
                    self.status.setText("Selection changed. Apply or revert the current draft to show the selected object.")
                    return
                self._pending_selection = True
                self._consume_pending_selection()
        replaced = (description["document_id"] != self._document_id
                    or description.get("document_epoch") != self._document_epoch)
        if replaced or description["revision"] != self._revision:
            if self._property_draft() or self.curve_table.has_draft():
                self.status.setText("Document changed elsewhere. Draft retained; revert/reload before applying.")
                self.undo_action.setEnabled(description["can_undo"])
                self.redo_action.setEnabled(description["can_redo"])
                return
            if replaced:
                self.reload_values()
                return
            self.reload_values()
            self._refresh_tree()
        self._update_status()

    def _update_status(self):
        if self._busy:
            return
        description = self.session.describe()
        dirty = " · Modified" if description["dirty"] else ""
        self.setWindowTitle(f"{description['name']}{dirty} — CAELab Materials · Composition workspace")
        self.status.setText(f"Revision {description['revision']}{dirty}    Qt-only material / curve provider")
        self._refresh_actions(description)

    def _refresh_actions(self, description=None):
        self.actions.refresh(description or self.session.describe(), busy=self._busy,
                             context="object" if self._target is not None else "")

    def _set_busy(self, busy):
        self._busy = busy
        for widget in (self.tree, self.properties, self.curve_table, self.apply_button, self.revert_button):
            widget.setEnabled(not busy)
        if not busy:
            self.curve_table.setEnabled(self._target is not None and self._target.kind == "curve")
        self._refresh_actions()
        if not busy:
            self._update_status()

    def _operation_changed(self, state):
        self.operation_state = state
        if state.status == "running":
            self.status.setText("File operation in progress…")
        elif state.status == "succeeded":
            self.messages.appendPlainText("File operation succeeded" + (": " + ", ".join(state.artifacts) if state.artifacts else ""))
        elif state.error:
            self.messages.appendPlainText(state.error["message"])

    def _start_file_operation(self, label, function, on_success=None, *, artifacts=()):
        if self._busy:
            return False
        task = FileTask(function, artifacts=artifacts)
        self._active_task = task
        self.operation_state = task.state
        self.last_operation_result = None
        self._set_busy(True)
        self.status.setText(label + "…")
        def done(result):
            self.last_operation_result = result
            self._active_task = None
            self._set_busy(False)
            if on_success:
                on_success()
            self.operationFinished.emit(label, True)
        def failed(exc):
            self._active_task = None
            self._set_busy(False)
            self.file_edits.save_failed()
            self._failure(exc)
            self.operationFinished.emit(label, False)
        task.signals.stateChanged.connect(self._operation_changed, Qt.ConnectionType.QueuedConnection)
        task.signals.complete.connect(done, Qt.ConnectionType.QueuedConnection)
        task.signals.failed.connect(failed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)
        return True

    def save_dialog(self, *, force_new=False, on_success=None):
        if self._busy:
            return False
        path = None if force_new else self.session.describe().get("project_path")
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save material document", "materials.caeprep", "CAE Prep document (*.caeprep)")
        if not path:
            return False
        return self.save_project_file(path, on_success=on_success)

    def save_project_file(self, path, *, on_success=None):
        if self._busy or not self._finish_drafts():
            return False
        return self._start_file_operation("Save material document", lambda: self.session.save_project(path),
                                          on_success, artifacts=(path,))

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open material document", "", "CAE Prep document (*.caeprep)")
        if path:
            self.open_project_file(path)

    def open_project_file(self, path):
        if self._busy:
            return False
        return self.file_edits.guard(lambda: self._start_file_operation(
            "Open material document", lambda: self.session.open_project(path),
            self._opened_document, artifacts=(path,)))

    def _opened_document(self):
        self._target = None
        self._curve_ref = None
        self._pending_selection = False
        self._baseline = {}
        self.properties.set_fields(())
        self.curve_table.set_points(())
        self._refresh_tree()
        self.select_ref(self.session.tree_nodes()[0].ref)

    def closeEvent(self, event):
        if self._busy:
            self.status.setText("Wait for the file operation to finish before closing")
            event.ignore()
            return
        if not self._allow_close:
            deciding = True
            def continue_close():
                self._allow_close = True
                if not deciding:
                    self.close()
            proceed = self.file_edits.guard(continue_close)
            deciding = False
            if not proceed:
                event.ignore()
                return
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("layout", self.saveState(1))
        self._closed = True
        self._unsubscribe()
        event.accept()


def main():
    app = QApplication.instance() or QApplication([])
    window = GalleryWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
