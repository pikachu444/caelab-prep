"""Explicit file-backed preferences for an isolated desktop run."""

from pathlib import Path

from PySide6.QtCore import QSettings


def file_settings(path):
    if path is None:
        return None
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    settings = QSettings(str(target), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    if not settings.isWritable() or settings.status() != QSettings.Status.NoError:
        raise ValueError(f"Settings file cannot be read/written: {target}")
    return settings
