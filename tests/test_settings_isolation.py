"""Exercise the opt-in CLI with separate processes and temporary preferences."""

import os
import subprocess
import sys

import pytest


PROBE = r'''
import sys
from pathlib import Path
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDockWidget
from caelab_prep.cli import main

mode, path, phase = sys.argv[1:]
app = QApplication([])

def check_and_close():
    try:
        window, = [w for w in app.topLevelWidgets() if w.isVisible() and w.parent() is None]
        assert Path(window._settings.fileName()).resolve() == Path(path).resolve()
        assert window._settings.format() == QSettings.Format.IniFormat
        assert not window._settings.fallbacksEnabled()
        dock = window.findChildren(QDockWidget)[0]
        if phase == 'write':
            assert dock.isVisible()
            dock.hide()
            window.resize(1031, 719)
        else:
            assert not dock.isVisible()
            assert window.height() == 719, window.size()
        assert window.close()
        assert window._settings.status() == QSettings.Status.NoError
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)

QTimer.singleShot(150, check_and_close)
QTimer.singleShot(15000, lambda: app.exit(2))
arguments = [mode, '--settings-file', path]
if mode == 'gui':
    arguments.append('--no-3d')
raise SystemExit(main(arguments))
'''


@pytest.mark.parametrize("mode,keys", [
    ("gui", ("windowGeometry", "windowState")),
    ("gallery", ("geometry", "layout")),
])
def test_cli_isolated_layout_survives_new_process(tmp_path, mode, keys):
    pytest.importorskip("PySide6")
    settings_path = tmp_path / "한글 settings" / f"{mode}.ini"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    for phase in ("write", "read"):
        result = subprocess.run(
            [sys.executable, "-c", PROBE, mode, str(settings_path), phase],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert settings_path.is_file()
    contents = settings_path.read_text(encoding="utf-8")
    assert all(key + "=" in contents for key in keys)


@pytest.mark.parametrize("mode", ["gui", "gallery"])
def test_cli_invalid_settings_file_fails_without_opening_a_window(tmp_path, mode):
    pytest.importorskip("PySide6")
    arguments = [mode, "--settings-file", str(tmp_path)]
    if mode == "gui":
        arguments.append("--no-3d")
    result = subprocess.run(
        [sys.executable, "-m", "caelab_prep", *arguments],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 1
    assert "Settings file cannot be read/written" in result.stdout
