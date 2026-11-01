"""Expose an ordinary native window for independent CUA input, with isolated settings.

This launcher sends no input and captures no images. Use the supported computer-use
runtime for both. The JSON observations are read-only supporting evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", choices=("prep", "gallery"), default="prep")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scale", choices=("1", "1.5", "2"), default="1")
    parser.add_argument("--width", type=int, default=1320)
    parser.add_argument("--height", type=int, default=840)
    parser.add_argument("--path", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Native Windows evidence requires Windows")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import QByteArray, QSettings, QTimer, qVersion
    from PySide6.QtWidgets import QApplication, QDockWidget
    from caelab_prep.ui import gallery, main_window

    def json_value(value):
        if isinstance(value, QByteArray):
            return {"QByteArray_hex": bytes(value.toHex()).decode()}
        if is_dataclass(value):
            return asdict(value)
        return str(value)

    def write(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                             default=json_value), encoding="utf-8")

    def native_snapshot():
        result = {}
        for name in ("Prep", "ComponentGallery"):
            settings = QSettings(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
                                 "CAELab", name)
            result[name] = {"file": settings.fileName(),
                            "values": {key: json_value(settings.value(key))
                                       for key in settings.allKeys()}}
        return result

    before = native_snapshot()
    write("native-settings-before.json", before)
    settings_stores = []

    def isolated_settings(organization, name):
        settings_dir = output / "settings"
        settings_dir.mkdir(exist_ok=True)
        path = settings_dir / f"{organization}-{name}.ini"
        settings = QSettings(str(path), QSettings.Format.IniFormat)
        settings.setFallbacksEnabled(False)
        assert Path(settings.fileName()).resolve().is_relative_to(output)
        settings_stores.append(settings.fileName())
        return settings

    main_window.QSettings = isolated_settings
    gallery.QSettings = isolated_settings
    app = QApplication([])
    if args.app == "gallery":
        from caelab_prep.application.neutral import CurveSession
        session = CurveSession()
        if args.path:
            session.open_project(args.path)
        window = gallery.GalleryWindow(session)
    else:
        from caelab_prep.application.session import PrepSession
        session = PrepSession()
        if args.path:
            if args.path.suffix.lower() == ".caeprep":
                session.open_project(args.path)
            else:
                session.open_rad(args.path)
        window = main_window.MainWindow(session)
    window.resize(args.width, args.height)
    window.show()
    window.move(window.screen().availableGeometry().topLeft())

    manifest = {"pid": os.getpid(), "app": args.app, "platform": app.platformName(),
                "pyside": pyside_version, "qt": qVersion(), "scale_factor": args.scale,
                "scaling_scope": "QT_SCALE_FACTOR only; OS display DPI unchanged",
                "input": "External supported CUA; launcher injects no input",
                "captures": "External supported CUA; no QWidget.grab or compositing",
                "settings_stores": settings_stores}
    write("launcher.json", manifest)

    def observe():
        editors = {}
        for name, editor in window.field_editors.items():
            if callable(getattr(editor, "text", None)):
                editors[name] = {"text": editor.text(), "visible": editor.isVisible(),
                                 "enabled": editor.isEnabled()}
        selected = getattr(window, "_selected_card_id", None)
        fields = session.card_fields(selected) if selected and args.app == "prep" else None
        tree = getattr(window, "model_tree", None) or getattr(window, "tree", None)
        snapshot = {"title": window.windowTitle(), "summary": session.describe(),
                    "selected_card": selected, "selected_ref": tree.selected_ref() if tree else None,
                    "card_fields": fields, "editors": editors,
                    "logical_size": [window.width(), window.height()],
                    "device_pixel_ratio": window.devicePixelRatioF(),
                    "frame_fits_screen": window.screen().availableGeometry().contains(window.frameGeometry()),
                    "docks": [{"name": dock.objectName(), "visible": dock.isVisible(),
                               "floating": dock.isFloating(), "area": window.dockWidgetArea(dock).value}
                              for dock in window.findChildren(QDockWidget)]}
        write("observed-state.json", snapshot)

    timer = QTimer(window)
    timer.timeout.connect(observe)
    timer.start(1000)
    observe()
    code = app.exec()
    after = native_snapshot()
    write("native-settings-after.json", after)
    manifest.update(exit_code=code, native_settings_unchanged=before == after)
    write("launcher.json", manifest)
    return code if before == after else 3


if __name__ == "__main__":
    raise SystemExit(main())
