"""Qt entry point joining the preserved Prep adapter and new workspace."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QSettings, Qt, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QLabel, QMenu

from .shell import FileTask as _FileTask
from .prep_controller import PrepController
from .prep_workspace import PrepWorkspace


class MainWindow(PrepController, PrepWorkspace, QMainWindow):
    """One native document window; model ownership remains in PrepSession."""

    operationFinished = Signal(str, bool)
    selectionChanged = Signal(dict)
    _sessionEvent = Signal(object)
    LAYOUT_VERSION = 4

    def __init__(self, session=None, *, enable_viewport: bool = True, presentation=None, settings=None):
        super().__init__()
        self.presentation = presentation
        self._live_control = None
        if session is None:
            from ..application.session import PrepSession
            session = PrepSession()
        self.initialize_controller(
            session, file_dialog=lambda: QFileDialog, message_box=lambda: QMessageBox,
            task_factory=lambda *args, **kwargs: _FileTask(*args, **kwargs))
        self._settings = settings if settings is not None else QSettings("CAELab", "Prep" + ("-" + presentation if presentation else ""))
        self._register_commands()
        from .reference_workspace import _edit_action, configure_native
        self.edit_properties_action = _edit_action(self)
        self.build_workspace(enable_viewport=enable_viewport)
        configure_native(self, presentation or "beidprep", native_commands=presentation in (None, "beidprep"))
        geometry = self._settings.value("windowGeometry")
        state = self._settings.value("windowState")
        geometry_restored = bool(geometry) and self.restoreGeometry(geometry)
        if not geometry_restored:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        restored = bool(state) and self.restoreState(state, self.LAYOUT_VERSION)
        self._initial_sidebar_pending = not restored
        self._automatic_sidebar = not restored
        if not restored:
            self.messages_dock.setVisible(bool(presentation and self.reference_adapter.docks.output))
            self._sizing_initial_sidebar = True
            try:
                self._size_initial_sidebar()
            finally:
                self._sizing_initial_sidebar = False
        self._sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = self.session.subscribe(self._sessionEvent.emit)
        self.refresh_document(rebuild_viewport=bool(self._summary().get("document_id")))
        self._live_control = None
        self._live_label = QLabel("Live control: off")
        self.statusBar().addPermanentWidget(self._live_label)
        menu = QMenu("&Automation", self.menuBar())
        self.menuBar().addMenu(menu)
        self.automation_menu = menu
        self.start_live_action = menu.addAction("Start live control…", self._start_live_dialog)
        self.stop_live_action = menu.addAction("Stop live control", self.stop_live_ipc)
        self.stop_live_action.setEnabled(False)

    def _start_live_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "New live-control connection file", "prep-connection.json", "Connection file (*.json)")
        if path:
            try: self.start_live_ipc(path)
            except Exception as exc: self._show_error(exc)

    def start_live_ipc(self, descriptor_path):
        """Explicitly share this owner; a connection file contains its local credential."""
        from .live_control import LiveControl
        if self._live_control is not None and self._live_control.status()["status"] != "closed":
            raise ValueError("Live control is already running; stop it before starting another endpoint.")
        self._live_control = LiveControl(self, descriptor_path)
        self._live_control.changed.connect(self._live_status_changed)
        self._live_status_changed({})
        return self.live_ipc_status()

    def live_ipc_status(self):
        return self._live_control.status() if self._live_control else {"status": "closed"}

    def _live_status_changed(self, _):
        state = self.live_ipc_status()
        active = state["status"] != "closed"
        text = f"Live control: {state['host']}:{state['port']}" if active else "Live control: off"
        if state["status"] == "stopping": text = "Live control: stopping worker…"
        elif state.get("active_jobs"): text += " · meshing"
        self._live_label.setText(text)
        self._live_label.setToolTip(state.get("descriptor_path", ""))
        self.start_live_action.setEnabled(not active); self.stop_live_action.setEnabled(active)

    def stop_live_ipc(self):
        result = self._live_control.close() if self._live_control else True
        self._live_status_changed({})
        return result

    def closeEvent(self, event):
        if getattr(self, "_live_control", None) and self._live_control.status().get("active_jobs"):
            self.stop_live_ipc()
            self.statusBar().showMessage("Stopping the live mesh worker. Close after it has stopped.")
            event.ignore(); return
        super().closeEvent(event)
        if event.isAccepted(): self.stop_live_ipc()

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_sidebar_pending:
            self._sizing_initial_sidebar = True
            try:
                self._size_initial_sidebar()
            finally:
                self._sizing_initial_sidebar = False
            self._initial_sidebar_pending = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_automatic_sidebar", False):
            self._sizing_initial_sidebar = True
            try:
                self._size_initial_sidebar()
            finally:
                self._sizing_initial_sidebar = False

    def event(self, event):
        if (event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and getattr(self, "_automatic_sidebar", False)):
            # QMainWindow owns dock separators; preserve the first manual drag.
            x, y = event.position().x(), event.position().y()
            panels = sorted((dock.geometry() for dock in (self.model_dock, self.properties_dock)
                             if dock.isVisible() and not dock.isFloating()), key=lambda rect: rect.left())
            for rect in panels:
                if rect.top() <= y <= rect.bottom() and rect.right() < x <= rect.right() + 8:
                    self._automatic_sidebar = False
                    break
        return super().event(event)

    def resizeDocks(self, docks, sizes, orientation):
        if not getattr(self, '_sizing_initial_sidebar', False):
            self._automatic_sidebar = False
        super().resizeDocks(docks, sizes, orientation)


def run(session=None, argv=None):
    app = QApplication.instance() or QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("CAELab Prep")
    app.setOrganizationName("CAELab")
    window = MainWindow(session)
    window.show()
    return app.exec()
