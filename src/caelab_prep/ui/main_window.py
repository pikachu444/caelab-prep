"""Qt entry point joining the preserved Prep adapter and new workspace."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from .shell import FileTask as _FileTask
from .prep_controller import PrepController
from .prep_workspace import PrepWorkspace


class MainWindow(PrepController, PrepWorkspace, QMainWindow):
    """One native document window; model ownership remains in PrepSession."""

    operationFinished = Signal(str, bool)
    selectionChanged = Signal(dict)
    _sessionEvent = Signal(object)
    LAYOUT_VERSION = 3

    def __init__(self, session=None, *, enable_viewport: bool = True):
        super().__init__()
        if session is None:
            from ..application.session import PrepSession
            session = PrepSession()
        self.initialize_controller(
            session, file_dialog=lambda: QFileDialog, message_box=lambda: QMessageBox,
            task_factory=lambda *args, **kwargs: _FileTask(*args, **kwargs))
        self._settings = QSettings("CAELab", "Prep")
        self._register_commands()
        self.build_workspace(enable_viewport=enable_viewport)
        geometry = self._settings.value("windowGeometry")
        state = self._settings.value("windowState")
        if geometry:
            self.restoreGeometry(geometry)
        restored = bool(state) and self.restoreState(state, self.LAYOUT_VERSION)
        self._initial_sidebar_pending = not restored
        if not restored:
            self.messages_dock.hide()
            self._size_initial_sidebar()
        self._sessionEvent.connect(self._session_changed, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = self.session.subscribe(self._sessionEvent.emit)
        self.refresh_document(rebuild_viewport=bool(self._summary().get("document_id")))

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_sidebar_pending:
            self._size_initial_sidebar()
            self._initial_sidebar_pending = False


def run(session=None, argv=None):
    app = QApplication.instance() or QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("CAELab Prep")
    app.setOrganizationName("CAELab")
    window = MainWindow(session)
    window.show()
    return app.exec()
