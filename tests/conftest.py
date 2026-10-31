"""Own Qt test objects until they are destroyed, before application shutdown."""

import pytest


@pytest.fixture(scope="session")
def qt_app():
    # Import lazily: the document/CLI CI environment does not install Qt.
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application
    assert QThreadPool.globalInstance().waitForDone(5000), "Qt file workers did not finish"
    application.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def qt_widgets(qt_app):
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from shiboken6 import isValid

    existing = set(qt_app.topLevelWidgets())
    yield qt_app

    pool = QThreadPool.globalInstance()
    assert pool.waitForDone(5000), "Qt file workers did not finish before widget cleanup"
    qt_app.processEvents()
    assert pool.activeThreadCount() == 0, "A file callback started an unfinished Qt worker"
    owned = [widget for widget in qt_app.topLevelWidgets() if widget not in existing]
    for widget in owned:
        if isValid(widget):
            if hasattr(widget, "_allow_close"):
                widget._allow_close = True
            widget.close()
            widget.deleteLater()
    # processEvents() alone does not process DeferredDelete outside app.exec().
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(not isValid(widget) for widget in owned), "Test-owned Qt widgets survived teardown"
