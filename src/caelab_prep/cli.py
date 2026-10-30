"""Independent-session CLI over the same application API used by the desktop UI.

This is not an IPC client for an already open desktop document.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _session(path: str):
    from .application.session import PrepSession

    session = PrepSession()
    if Path(path).suffix.lower() == ".caeprep":
        session.open_project(path)
    else:
        session.open_rad(path)
    return session


def _print(value):
    # JSON escapes keep machine output valid on legacy Windows pipe encodings.
    print(json.dumps(value, ensure_ascii=True, indent=2, default=str))


def _resolve_card(session, identifier):
    cards = session.list_cards()
    by_id = [card for card in cards if card["id"] == identifier]
    matches = by_id or [card for card in cards if card["keyword"] == identifier]
    if len(matches) != 1:
        raise ValueError("Use one exact card ID or a unique native keyword/header")
    return matches[0]["id"]


def parser():
    result = argparse.ArgumentParser(description="CAELab Prep native document editor")
    commands = result.add_subparsers(dest="command")
    gui = commands.add_parser("gui", help="Open the desktop editor")
    gui.add_argument("path", nargs="?")
    gallery = commands.add_parser("gallery", help="Open the shared Qt material/curve gallery (no VTK required)")
    gallery.add_argument("path", nargs="?", help="Neutral material/curve working document")
    inspect = commands.add_parser("inspect", help="Read a RAD/project in an independent session")
    inspect.add_argument("path")
    schema = commands.add_parser("fields", help="List native cards or query an editable card")
    schema.add_argument("path")
    schema.add_argument("--card", help="Project card ID or exact unique native header")
    edit = commands.add_parser("edit", help="Edit a supported native field and save a project")
    edit.add_argument("path")
    edit.add_argument("--card", required=True, help="Project card ID or exact unique native header")
    edit.add_argument("--field", required=True)
    edit.add_argument("--value", required=True)
    edit.add_argument("--output", required=True)
    export = commands.add_parser("export", help="Export native RAD and resolved dependencies")
    export.add_argument("path")
    export.add_argument("--output", required=True)
    mesh = commands.add_parser("mesh", help="Generate independent CAD/mesh candidate assets")
    mesh.add_argument("source")
    mesh.add_argument("--output", required=True)
    mesh.add_argument("--size", required=True, type=float)
    mesh.add_argument("--dimension", type=int, choices=(2, 3), default=3)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "gallery":
            from PySide6.QtWidgets import QApplication
            from .application.neutral import CurveSession
            from .ui.gallery import GalleryWindow

            app = QApplication.instance() or QApplication(sys.argv[:1])
            app.setApplicationName("CAELab Prep Gallery")
            session = CurveSession()
            if args.path:
                session.open_project(args.path)
            window = GalleryWindow(session=session)
            window.show()
            return app.exec()
        if args.command in (None, "gui"):
            from PySide6.QtWidgets import QApplication
            from .ui.main_window import MainWindow

            app = QApplication.instance() or QApplication(sys.argv[:1])
            app.setApplicationName("CAELab Prep")
            session = _session(args.path) if getattr(args, "path", None) else None
            window = MainWindow(session=session)
            window.show()
            return app.exec()
        if args.command == "mesh":
            from .adapters.gmsh_backend import GmshBackend

            _print(GmshBackend().generate(args.source, args.output, args.size, dimension=args.dimension))
            return 0
        session = _session(args.path)
        if args.command == "inspect":
            _print(session.describe())
        elif args.command == "fields":
            _print(session.card_fields(_resolve_card(session, args.card)) if args.card else session.list_cards())
        elif args.command == "edit":
            try:
                value = json.loads(args.value)
            except json.JSONDecodeError:
                value = args.value
            session.set_field(_resolve_card(session, args.card), args.field, value, expected_revision=session.describe()["revision"])
            _print(session.save_project(args.output))
        elif args.command == "export":
            _print(session.export_rad(args.output))
        return 0
    except Exception as exc:
        error = exc.to_dict() if callable(getattr(exc, "to_dict", None)) else {
            "code": type(exc).__name__, "message": str(exc)
        }
        _print({"error": error})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
