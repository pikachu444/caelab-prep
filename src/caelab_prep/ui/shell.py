"""Small composable shell pieces with app-owned state and renderer injection."""

from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, Signal

from PySide6.QtWidgets import QDockWidget, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ..application.contracts import OperationState


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
    window.addDockWidget(area, dock)
    if menu is not None:
        menu.addAction(dock.toggleViewAction())
    return dock


class ViewportFrame(QFrame):
    """A shared title/context frame for an injected plot or mesh renderer."""

    def __init__(self, content, title="", context="", parent=None):
        super().__init__(parent)
        self.setObjectName("viewportFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("viewportBar")
        header = QHBoxLayout(bar)
        header.setContentsMargins(10, 7, 10, 7)
        self.title = QLabel(title)
        self.title.setObjectName("groupTitle")
        self.context = QLabel(context)
        self.context.setObjectName("propertySubtitle")
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.context)
        layout.addWidget(bar)
        layout.addWidget(content, 1)
