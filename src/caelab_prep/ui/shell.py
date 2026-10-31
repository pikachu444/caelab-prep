"""Small composable shell pieces with app-owned state and renderer injection."""

from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, Signal
from PySide6.QtGui import QPainter

from PySide6.QtWidgets import QDockWidget, QFrame, QHBoxLayout, QLabel, QMessageBox, QSizePolicy, QToolButton, QVBoxLayout

from ..application.contracts import OperationState


class FileEditCoordinator:
    """Ask before replacing/closing; only Save finishes and validates drafts."""

    def __init__(self, parent, *, has_draft, finish, discard, is_dirty, save, capture=None, restore=None):
        self.parent = parent
        self.has_draft = has_draft
        self.finish = finish
        self.discard = discard
        self.is_dirty = is_dirty
        self.save = save
        self.capture = capture
        self.restore = restore
        self.choosing = False
        self._save_draft = None

    def guard(self, continuation):
        if not (self.is_dirty() or self.has_draft()):
            continuation()
            return True
        self.choosing = True
        try:
            answer = QMessageBox.question(
                self.parent, "Unsaved changes", "Save changes before continuing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
        finally:
            self.choosing = False
        if answer == QMessageBox.StandardButton.Discard:
            self.discard()
            continuation()
            return True
        if answer == QMessageBox.StandardButton.Save:
            self._save_draft = self.capture() if self.capture else None
            if not self.finish():
                self.save_failed()
                return False
            def saved():
                self._save_draft = None
                continuation()
            if self.save(saved) is False:
                self.save_failed()
        return False

    def save_failed(self):
        if self._save_draft is not None and self.restore:
            self.restore(self._save_draft)
        self._save_draft = None


class _FileSignals(QObject):
    complete = Signal(object)
    failed = Signal(object)
    stateChanged = Signal(object)


class FileTask(QRunnable):
    """Run one non-cancellable file operation; sessions retain file ownership."""

    def __init__(self, function, *, operation_id="", artifacts=()):
        super().__init__()
        self.function = function
        self.signals = _FileSignals()
        self.operation_id = operation_id or str(uuid4())
        self.artifacts = tuple(str(path) for path in artifacts)
        self.state = OperationState(self.operation_id, "running")

    def run(self):
        self.signals.stateChanged.emit(self.state)
        try:
            result = self.function()
        except Exception as exc:
            error = {"code": getattr(exc, "code", "file_operation_failed"), "message": str(exc)}
            self.state = OperationState(self.operation_id, "failed", error=error)
            self.signals.stateChanged.emit(self.state)
            self.signals.failed.emit(exc)
        else:
            artifacts = self.artifacts
            if isinstance(result, dict):
                artifacts = artifacts or tuple(str(result[key]) for key in ("saved_path", "exported_path") if result.get(key))
            self.state = OperationState(self.operation_id, "succeeded", artifacts=artifacts)
            self.signals.stateChanged.emit(self.state)
            self.signals.complete.emit(result)


def create_dock(window, name, title, widget, area, menu=None):
    dock = QDockWidget(title, window)
    dock.setObjectName(name)
    dock.setWidget(widget)
    dock.setMinimumWidth(160)
    dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
    window.addDockWidget(area, dock)
    if menu is not None:
        menu.addAction(dock.toggleViewAction())
    return dock


class _ViewContext(QLabel):
    """Keep optional view metadata readable without setting the workspace width."""

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(min(hint.width(), 280), hint.height())

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)


class ViewportFrame(QFrame):
    """A shared title/context frame for an injected plot or mesh renderer."""

    def __init__(self, content, title="", context="", parent=None):
        super().__init__(parent)
        self.setObjectName("viewportFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.bar = QFrame()
        self.bar.setObjectName("viewportBar")
        self.header = QHBoxLayout(self.bar)
        header = self.header
        header.setContentsMargins(8, 3, 6, 3)
        header.setSpacing(6)
        self.title = QLabel(title)
        self.title.setObjectName("groupTitle")
        self.context = _ViewContext(context)
        self.context.setObjectName("propertySubtitle")
        self.context.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.context.setToolTip(context)
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.context)
        layout.addWidget(self.bar)
        layout.addWidget(content, 1)

    def add_action(self, action):
        """Place a host-owned command beside the active view's title."""
        button = QToolButton(self.bar)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(16, 16))
        self.header.addWidget(button)
        return button
