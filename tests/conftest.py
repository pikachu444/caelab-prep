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
def qt_settings(tmp_path, monkeypatch):
    from PySide6.QtCore import QSettings
    from caelab_prep.ui import gallery, main_window

    def isolated_settings(organization, application):
        path = tmp_path / "settings" / organization / (application + ".ini")
        settings = QSettings(str(path), QSettings.Format.IniFormat)
        settings.setFallbacksEnabled(False)
        return settings

    monkeypatch.setattr(gallery, "QSettings", isolated_settings)
    monkeypatch.setattr(main_window, "QSettings", isolated_settings)


@pytest.fixture
def qt_widgets(qt_app, qt_settings):
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from shiboken6 import isValid, ownedByPython

    existing = set(qt_app.topLevelWidgets())
    yield qt_app

    pool = QThreadPool.globalInstance()
    assert pool.waitForDone(5000), "Qt file workers did not finish before widget cleanup"
    qt_app.processEvents()
    assert pool.activeThreadCount() == 0, "A file callback started an unfinished Qt worker"
    owned = [widget for widget in qt_app.topLevelWidgets() if widget not in existing]
    # Window flags also include parent-owned menus and private combo popups.
    roots = [widget for widget in owned if widget.parent() is None and ownedByPython(widget)]
    for widget in roots:
        if isValid(widget):
            if hasattr(widget, "_allow_close"):
                widget._allow_close = True
            widget.close()
            widget.deleteLater()
    # processEvents() alone does not process DeferredDelete outside app.exec().
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert all(not isValid(widget) for widget in owned), "Test-owned Qt widgets survived teardown"
