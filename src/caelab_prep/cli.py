"""Independent-session CLI over the same application API used by the desktop UI.

This is not an IPC client for an already open desktop document.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
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
    print(json.dumps(value, ensure_ascii=True, indent=2,
                     default=lambda item: asdict(item) if is_dataclass(item) else str(item)))


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
    compare = commands.add_parser("compare", help="Compare program-specific working views of one document")
    compare.add_argument("path", nargs="?", help="Neutral working document; use --rad for a native RAD/project")
    compare.add_argument("--rad", action="store_true", help="Use the existing RAD document/provider")
    compare.add_argument("--no-3d", action="store_true", help="Disable VTK (layout inspection only)")
    commands.add_parser("catalogue", help="Open the developer component catalogue (no VTK required)")
    inspect = commands.add_parser("inspect", help="Read a RAD/project in an independent session")
    inspect.add_argument("path")
    new = commands.add_parser("new", help="Create an empty document with explicit working units")
    new.add_argument("--name", required=True)
    new.add_argument("--mass", required=True, choices=("Mg", "kg", "g"))
    new.add_argument("--length", required=True, choices=("mm", "cm", "m"))
    new.add_argument("--time", required=True, choices=("s", "ms"))
    new.add_argument("--output", required=True)
    adopt = commands.add_parser("adopt", help="Validate a Gmsh candidate and adopt its native mesh")
    adopt.add_argument("path")
    adopt.add_argument("--candidate", required=True, help="Persisted metadata.json")
    adopt.add_argument("--material", required=True, help="Material card UUID or exact native header")
    adopt.add_argument("--property", required=True, help="Shell/solid property UUID or exact native header")
    adopt.add_argument("--replace-part", action="append", default=[], help="Exact owned PART UUID/header to replace; repeat for multiple parts")
    adopt.add_argument("--length-unit", choices=("mm", "cm", "m"), help="Explicit declaration for a candidate with unknown CAD units; no coordinate conversion")
    adopt.add_argument("--minimum-triangle", type=float, default=.1)
    adopt.add_argument("--minimum-tetrahedron", type=float, default=.1)
    adopt.add_argument("--output", required=True)
    schema = commands.add_parser("fields", help="List native cards or query an editable card")
    schema.add_argument("path")
    schema.add_argument("--card", help="Project card ID or exact unique native header")
    edit = commands.add_parser("edit", help="Edit a supported native field and save a project")
    edit.add_argument("path")
    edit.add_argument("--card", required=True, help="Project card ID or exact unique native header")
    edit.add_argument("--field", required=True)
    edit.add_argument("--value", required=True)
    edit.add_argument("--output", required=True)
    model = commands.add_parser("model", help="Create, duplicate, delete or assign objects through the GUI's command API")
    model.add_argument("path")
    from .application.rad_provider import MODEL_OPERATIONS
    model.add_argument("operation", choices=MODEL_OPERATIONS)
    model.add_argument("--target", help="Target card ID or exact unique native header")
    model.add_argument("--set", dest="values", action="append", default=[], metavar="FIELD=VALUE",
                       help="Set a form value; lists/tables/vectors use JSON, references use card IDs/headers or reference objects")
    model.add_argument("--unit", action="append", default=[], metavar="FIELD=UNIT",
                       help="Display unit for an explicitly supplied --set value; converted to native units on Apply")
    model.add_argument("--describe", action="store_true", help="Print the current operation form without changing the document")
    model.add_argument("--output", help="Save the resulting working document")
    export = commands.add_parser("export", help="Export native RAD and resolved dependencies")
    export.add_argument("path")
    export.add_argument("--output", required=True)
    export.add_argument("--engine", action="store_true", help="Generate a companion Engine file; --output must end in _0000.rad")
    export.add_argument("--end-time", type=float)
    export.add_argument("--output-interval", type=float, help="Animation interval in the declared working time unit")
    mesh = commands.add_parser("mesh", help="Generate independent CAD/mesh candidate assets")
    mesh.add_argument("source")
    mesh.add_argument("--output", required=True)
    mesh.add_argument("--size", required=True, type=float)
    mesh.add_argument("--dimension", type=int, choices=(2, 3), default=3)
    mesh.add_argument("--local-size", action="append", default=[], metavar="UUID=SIZE",
                      help="Refine a persisted XAO surface/volume UUID; repeat for multiple entities")
    mesh.add_argument("--interface-policy", choices=("preserve", "conformal", "independent"), default="preserve")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "compare":
            from PySide6.QtWidgets import QApplication
            from .ui.comparison import ComparisonWindow
            if args.rad:
                session = _session(args.path) if args.path else None
                if session is None:
                    from .application.session import PrepSession
                    session = PrepSession()
            else:
                from .application.neutral import CurveSession
                session = CurveSession()
                if args.path:
                    session.open_project(args.path)
            app = QApplication.instance() or QApplication(sys.argv[:1])
            window = ComparisonWindow(session, native=args.rad, enable_viewport=not args.no_3d)
            window.show()
            return app.exec()
        if args.command == "catalogue":
            from PySide6.QtWidgets import QApplication, QMainWindow
            from .ui.catalogue import CatalogueWidget
            from .ui.theme import STYLESHEET

            app = QApplication.instance() or QApplication(sys.argv[:1])
            window = QMainWindow()
            window.setWindowTitle("CAELab Components — Developer catalogue")
            window.setStyleSheet(STYLESHEET)
            window.setCentralWidget(CatalogueWidget())
            window.resize(1120, 760)
            window.show()
            return app.exec()
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

            local_sizes = {}
            for text in args.local_size:
                identifier, separator, value = text.partition("=")
                if not separator or identifier in local_sizes:
                    raise ValueError("Each --local-size must specify a unique UUID=SIZE")
                local_sizes[identifier] = float(value)
            _print(GmshBackend().generate(args.source, args.output, args.size, dimension=args.dimension,
                                         interface_policy=args.interface_policy, local_sizes=local_sizes))
            return 0
        if args.command == "new":
            from .application.session import PrepSession
            session = PrepSession()
            session.new_document(args.name, {"mass": args.mass, "length": args.length, "time": args.time})
            _print(session.save_project(args.output))
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
        elif args.command == "model":
            from .application.contracts import ObjectRef, OperationRequest
            from .application.rad_provider import RadProvider

            provider = RadProvider(session)
            def reference(identifier):
                card_id = _resolve_card(session, identifier)
                return provider.ref_for_card(next(card for card in session.list_cards() if card["id"] == card_id))
            target = reference(args.target) if args.target else None
            spec = provider.operation_spec(args.operation, target)
            if args.describe:
                if args.values or args.unit or args.output:
                    raise ValueError("--describe cannot be combined with changes or --output")
                _print(spec)
                return 0
            if not args.output:
                raise ValueError("--output is required when changing a working document")
            fields = {item.name: item for item in spec.fields}
            values = {name: item.value for name, item in fields.items()}
            assigned = set()
            for text in args.values:
                name, separator, encoded = text.partition("=")
                if not separator or name not in fields or name in assigned:
                    raise ValueError("Each --set must name one supported field exactly once")
                assigned.add(name)
                try:
                    value = json.loads(encoded)
                except json.JSONDecodeError:
                    value = encoded
                if fields[name].kind == "reference":
                    value = reference(value) if isinstance(value, str) else ObjectRef(**value) if isinstance(value, dict) else value
                elif fields[name].kind == "references":
                    if not isinstance(value, list):
                        raise ValueError("Multiple references require a JSON list")
                    if fields[name].unit_context.get("reference_kind") != "mesh-element":
                        value = [reference(item) if isinstance(item, str) else ObjectRef(**item) if isinstance(item, dict) else item
                                 for item in value]
                values[name] = value
            units = {}
            for item in args.unit:
                name, separator, unit = item.partition("=")
                if not separator or name not in assigned or name in units:
                    raise ValueError("Each --unit must name an explicitly supplied --set field exactly once")
                units[name] = unit
            result = provider.execute_operation(OperationRequest(spec.key, values, spec.document_id,
                                                                  spec.expected_revision, spec.target, units))
            _print({"operation": result, "saved": session.save_project(args.output)})
        elif args.command == "export":
            if args.engine:
                if args.end_time is None or args.output_interval is None:
                    raise ValueError("Engine export requires --end-time and --output-interval")
                _print(session.export_solver_inputs(args.output, args.end_time, args.output_interval))
            else:
                if args.end_time is not None or args.output_interval is not None:
                    raise ValueError("Time controls require --engine")
                _print(session.export_rad(args.output))
        elif args.command == "adopt":
            from .application.mesh_candidates import QualityLimits, read_mesh_candidate
            limits = QualityLimits(minimum_triangle=args.minimum_triangle, minimum_tetrahedron=args.minimum_tetrahedron)
            candidate = read_mesh_candidate(args.candidate, quality_limits=limits)
            native = candidate.to_native_mesh(length_unit=args.length_unit)
            state = session.describe()
            result = session.adopt_mesh_candidate(native, material_id=_resolve_card(session, args.material),
                property_id=_resolve_card(session, args.property),
                replace_part_ids=[_resolve_card(session, part) for part in args.replace_part] or None,
                expected_revision=state["revision"], expected_document_id=state["document_id"])
            _print({"adoption": result, "quality": candidate.quality, "saved": session.save_project(args.output)})
        return 0
    except Exception as exc:
        error = exc.to_dict() if callable(getattr(exc, "to_dict", None)) else {
            "code": type(exc).__name__, "message": str(exc)
        }
        _print({"error": error})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
