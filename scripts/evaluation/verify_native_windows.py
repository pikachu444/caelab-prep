"""Bounded self-app Windows Qt/QTest evidence; never controls another application.

Run exercise and then restore in separate processes with the same scale/output.
QT_SCALE_FACTOR tests application scaling, not a change to OS monitor DPI.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback


def desktop_name():
    if os.name != "nt":
        raise RuntimeError("Native validation requires Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                ctypes.c_void_p, wintypes.DWORD,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    desktop = user32.OpenInputDesktop(0, False, 1)  # DESKTOP_READOBJECTS only.
    if not desktop:
        raise RuntimeError(f"OpenInputDesktop unavailable: {ctypes.get_last_error()}")
    try:
        name = ctypes.create_unicode_buffer(256)
        required = wintypes.DWORD()
        if not user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(required)):
            raise RuntimeError(f"Input desktop name unavailable: {ctypes.get_last_error()}")
        if name.value.casefold() != "default":
            raise RuntimeError(f"Stop: input desktop is {name.value!r}, not unlocked Default")
        return name.value
    finally:
        user32.CloseDesktop(desktop)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scale", choices=("1", "1.5", "2"), default="1")
parser.add_argument("--phase", choices=("exercise", "restore", "curve", "layout"), default="exercise")
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
report = {"phase": args.phase, "scale_factor": args.scale,
          "input_method": "QTest events to this process's own Qt widgets; no OS SendInput",
          "capture_method": "own QWidget.grab plus own VTK framebuffer; no desktop capture",
          "scaling_scope": "QT_SCALE_FACTOR application scaling; OS DPI is observed, never changed",
          "stages": []}
try:
    report["input_desktop"] = desktop_name()
except Exception as exc:
    report.update(status="blocked", reason=str(exc))
    print(json.dumps(report), flush=True)
    raise SystemExit(2)

os.environ["QT_QPA_PLATFORM"] = "windows"
os.environ["QT_SCALE_FACTOR"] = args.scale
repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "src"))
args.output = args.output.resolve()
args.output.mkdir(parents=True, exist_ok=True)

from PySide6 import __version__ as qt_binding_version
from PySide6.QtCore import QByteArray, QCoreApplication, QEvent, QPoint, QRect, QSettings, Qt, QThreadPool, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QScrollArea, QToolBar
from caelab_prep.application.neutral import CurveSession
from caelab_prep.application.session import PrepSession
from caelab_prep.ui.gallery import GalleryWindow
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui import gallery as gallery_module, main_window as main_window_module


def native_settings_snapshot():
    result = {}
    for name in ("Prep", "ComponentGallery"):
        settings = QSettings(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, "CAELab", name)
        result[name] = {"file": settings.fileName(), "format": str(settings.format()), "values": {}}
        for key in settings.allKeys():
            value = settings.value(key)
            result[name]["values"][key] = {
                "type": type(value).__name__,
                "value": bytes(value.toHex()).decode() if isinstance(value, QByteArray) else value}
    return result


native_settings_before = native_settings_snapshot()
(args.output / "native-settings-before.json").write_text(json.dumps(native_settings_before, indent=2), "utf-8")
report["settings_stores"] = {}


def isolated_settings(organization, name):
    # The org/app constructor always selects NativeFormat, regardless of setDefaultFormat.
    directory = args.output / "settings"
    directory.mkdir(exist_ok=True)
    settings = QSettings(str(directory / f"{organization}-{name}.ini"), QSettings.Format.IniFormat)
    settings.setFallbacksEnabled(False)
    assert settings.format() == QSettings.Format.IniFormat
    assert Path(settings.fileName()).resolve().is_relative_to(args.output)
    report["settings_stores"][f"{organization}/{name}"] = {
        "file": settings.fileName(), "format": str(settings.format()), "fallbacks": settings.fallbacksEnabled()}
    return settings


# Injection is local to this evidence process; product sources and the Qt class are unchanged.
main_window_module.QSettings = isolated_settings
gallery_module.QSettings = isolated_settings
report["settings_isolation"] = "Explicit per-window INI filenames; native stores are read only and compared after cleanup"
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
windows = []
report.update(platform=app.platformName(), pyside=qt_binding_version,
              font_families=len(QFontDatabase.families()),
              fonts={name: name in QFontDatabase.families() for name in ("Segoe UI", "Malgun Gothic")},
              screens=[{"name": s.name(), "dpr": s.devicePixelRatio(), "logical_dpi": s.logicalDotsPerInch(),
                        "physical_dpi": s.physicalDotsPerInch(),
                        "geometry": [s.geometry().x(), s.geometry().y(), s.geometry().width(), s.geometry().height()],
                        "available_geometry": [s.availableGeometry().x(), s.availableGeometry().y(),
                                               s.availableGeometry().width(), s.availableGeometry().height()]}
                       for s in app.screens()])


def gate():
    desktop_name()


def pump(ms=100):
    app.processEvents()
    QTest.qWait(ms)


def activate_input(window):
    gate()
    window.raise_(); window.activateWindow()
    assert QTest.qWaitForWindowActive(window, 4000), "Owned input window did not become active"
    assert window.windowHandle().isExposed(), "Owned input window is not exposed"
    assert window.screen().availableGeometry().contains(window.frameGeometry()), "Input window is outside available screen"


def click(widget, point=None, double=False):
    gate()
    activate_input(widget.window())
    assert widget.isVisible() and widget.isEnabled(), "Input target is not visible/enabled"
    target = point or widget.rect().center()
    assert widget.visibleRegion().contains(target), "QTest target point is clipped by its visible region"
    method = QTest.mouseDClick if double else QTest.mouseClick
    method(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
           target, 20)
    pump()


def type_text(editor, text):
    click(editor)
    gate()
    QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor, text)
    pump()


def toolbar_action(window, action):
    button = next((bar.widgetForAction(action) for bar in window.findChildren(QToolBar)
                   if bar.widgetForAction(action) is not None), None)
    assert button is not None, "Action has no actual toolbar control"
    click(button)


def tree_ref(tree, ref):
    index = tree._indices[ref].index()  # Locate only; selection is real QTest input.
    tree.scrollTo(index)
    pump()
    click(tree.viewport(), tree.visualRect(index).center())
    assert tree.selected_ref() == ref


def reachable(widget, window):
    """Scroll the real view, then reject any clipped input target before QTest input."""
    for _ in range(4):
        pump(30)
    ancestor = widget.parentWidget()
    scrolls = []
    while ancestor is not None:
        if isinstance(ancestor, QScrollArea):
            scrolls.append(ancestor)
        ancestor = ancestor.parentWidget()
    for scroll in scrolls:
        centre = widget.mapTo(scroll.widget(), widget.rect().center())
        assert widget.width() <= scroll.viewport().width() and widget.height() <= scroll.viewport().height(), "Control cannot fit scroll viewport"
        scroll.ensureVisible(centre.x(), centre.y(), (widget.width() + 1) // 2 + 4,
                             (widget.height() + 1) // 2 + 4)
        pump(50)
    assert widget.isVisibleTo(window), "Target is hidden"
    ancestor = widget.parentWidget()
    while ancestor is not None:
        mapped = QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())
        assert ancestor.rect().contains(mapped), {
            "target": widget.accessibleName() or widget.text() if hasattr(widget, "text") else type(widget).__name__,
            "clipped_by": type(ancestor).__name__, "target_rect": [mapped.x(), mapped.y(), mapped.width(), mapped.height()],
            "ancestor_size": [ancestor.width(), ancestor.height()]}
        if ancestor is window:
            break
        ancestor = ancestor.parentWidget()
    return {"target": widget.accessibleName() or type(widget).__name__,
            "scrolls": [{"name": scroll.accessibleName(),
                         "horizontal": [scroll.horizontalScrollBar().value(), scroll.horizontalScrollBar().maximum()],
                         "vertical": [scroll.verticalScrollBar().value(), scroll.verticalScrollBar().maximum()]}
                        for scroll in scrolls]}


def wait_file(window):
    deadline = time.monotonic() + 15
    while window._busy and time.monotonic() < deadline:
        pump(20)
    assert not window._busy, "File operation did not finish within 15 seconds"
    assert window.operation_state.status == "succeeded", str(window.operation_state)
    pump()


def expose(window):
    windows.append(window)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 10000), "Native window not exposed"
    pump(200)
    handle = window.windowHandle()
    return {"native_handle": int(window.winId()), "exposed": handle.isExposed(),
            "dpr": window.devicePixelRatioF(), "screen": handle.screen().name(),
            "logical_size": [window.width(), window.height()],
            "frame_geometry": [window.frameGeometry().x(), window.frameGeometry().y(),
                               window.frameGeometry().width(), window.frameGeometry().height()],
            "frame_fits_available_screen": handle.screen().availableGeometry().contains(window.frameGeometry())}


def fit_input_window(window):
    # A 1320 logical window exceeds this monitor at forced 2x; actual input uses 960x640.
    window.resize(960, 640) if float(args.scale) >= 2 else window.resize(1320, 840)
    available = window.screen().availableGeometry()
    window.move(available.topLeft() + QPoint(10, 10))
    activate_input(window); pump()
    assert available.contains(window.frameGeometry()), "Input window does not fit available native screen"


def capture(window, name):
    text = f"NATIVE Qt/windows · QTest own-window input · app scale {args.scale} · no OS SendInput"
    if hasattr(window, "status"):
        window.status.setText(text)
    elif hasattr(window, "statusBar"):
        window.statusBar().showMessage(text)
    pump()
    path = args.output / f"{args.phase}-{name}.png"
    pixmap = window.grab()
    assert pixmap.save(str(path)), "Own-widget screenshot failed"
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pixels": [pixmap.width(), pixmap.height()], "dpr": pixmap.devicePixelRatio(),
            "logical_size": [window.width(), window.height()],
            "frame_geometry": [window.frameGeometry().x(), window.frameGeometry().y(),
                               window.frameGeometry().width(), window.frameGeometry().height()],
            "frame_fits_available_screen": window.screen().availableGeometry().contains(window.frameGeometry())}


def stage(name, function):
    gate()
    try:
        result = function()
        item = {"name": name, "status": "passed", "evidence": result}
    except Exception as exc:
        item = {"name": name, "status": "failed", "error": str(exc), "traceback": traceback.format_exc()}
    report["stages"].append(item)
    print(json.dumps({"stage": item}), flush=True)
    return item["status"] == "passed"


def modal_close(window, choice):
    seen = []
    errors = []
    timer = QTimer()
    started = time.monotonic()
    def answer():
        dialog = app.activeModalWidget()
        if not isinstance(dialog, QMessageBox) or dialog.parentWidget() is not window:
            if time.monotonic() - started > 8:
                errors.append("Expected owned Save/Discard/Cancel modal was not found")
                timer.stop()
            return
        try:
            gate()
            button = dialog.button(choice)
            assert button is not None
            seen.append({"title": dialog.windowTitle(), "text": dialog.text(),
                         "button": button.text(), "focus_widget": type(app.focusWidget()).__name__})
            timer.stop()
            activate_input(dialog)
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        except Exception as exc:
            errors.append(str(exc))
            timer.stop()
            dialog.reject()  # Cancel our own modal during abort; no substitute acceptance evidence.
    timer.timeout.connect(answer)
    timer.start(40)
    window.close()
    timer.stop()
    pump()
    assert not errors, errors
    assert seen, "No real owned modal button was exercised"
    return seen


def layout_description(window):
    return {dock.objectName(): {"area": window.dockWidgetArea(dock).value,
                               "floating": dock.isFloating(), "visible": dock.isVisible()}
            for dock in (window.model_dock, window.properties_dock, window.messages_dock)}


def drag_dock(dock, target_global):
    """A bounded titlebar gesture using only this application's Qt widgets."""
    gate()
    activate_input(dock.window())
    start = QPoint(max(30, dock.width() // 2), 10)
    origin = dock.mapToGlobal(start)
    QTest.mousePress(dock, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    try:
        for step in range(1, 13):
            gate()
            point = QPoint(round(origin.x() + (target_global.x() - origin.x()) * step / 12),
                           round(origin.y() + (target_global.y() - origin.y()) * step / 12))
            QTest.mouseMove(dock, dock.mapFromGlobal(point), 35)
            app.processEvents()
    finally:
        QTest.mouseRelease(dock, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                           dock.mapFromGlobal(target_global))
    pump(250)


def new_rad():
    session = PrepSession()
    project = args.output / "native-rad.caeprep"
    if project.exists():
        session.open_project(str(project))
    else:
        session.open_rad(str(repo / "examples/rad/shell_panels_0000.rad"))
        session.save_project(str(project))
    window = MainWindow(session, enable_viewport=True)
    return window, expose(window)


def gallery_curve_input(gallery):
    fit_input_window(gallery)
    gallery.properties_dock.raise_(); pump()
    ref = next(node.ref for node in gallery.session.tree_nodes()
               if node.ref.kind == "curve" and node.ref.object_id == "load")
    tree_ref(gallery.tree, ref)
    original = tuple(tuple(point) for point in gallery.session.curve_points(ref))
    grid = gallery.curve_table.table
    item = grid.item(0, 1)
    grid.scrollToItem(item); pump()
    reachable(grid.viewport(), gallery)
    click(grid.viewport(), grid.visualItemRect(item).center())
    gate(); QTest.keyClick(grid, Qt.Key.Key_F2); pump()
    editors = [editor for editor in grid.findChildren(QLineEdit) if editor.isVisible()]
    assert len(editors) == 1, {"error": "Expected one visible curve delegate editor", "focus": type(app.focusWidget()).__name__, "editors": len(editors)}
    editor = editors[0]
    assert editor.hasFocus(), "Curve delegate does not own keyboard focus"
    type_text(editor, str(original[0][1] + 1))
    QTest.keyClick(editor, Qt.Key.Key_Return); pump()
    assert gallery.curve_table.has_draft() and gallery.plot._points == original
    reachable(gallery.curve_table.apply_button, gallery)
    click(gallery.curve_table.apply_button)
    edited = tuple(tuple(point) for point in gallery.session.curve_points(ref))
    assert edited[0][1] == original[0][1] + 1 and gallery.plot._points == edited
    applied = capture(gallery, "gallery-curve-applied")
    toolbar_action(gallery, gallery.undo_action)
    assert tuple(tuple(point) for point in gallery.session.curve_points(ref)) == original
    assert gallery.plot._points == original
    return {"curve": ref.object_id, "input": "QTest cell click + F2 + delegate keys, Apply curve button, Undo toolbar",
            "applied": applied, "restored": capture(gallery, "gallery-curve-undo")}


def run():
    assert app.platformName() == "windows", "Wrong QPA platform; no offscreen fallback permitted"
    if args.phase == "layout":
        assert args.scale == "2", "The bounded oversized-layout phase is for application scale 2"
        gallery = GalleryWindow()
        info = expose(gallery)
        def exact_oversized_layout():
            gallery.setFixedSize(1320, 840)
            gallery.move(gallery.screen().availableGeometry().topLeft() + QPoint(10, 10))
            pump(250)
            assert [gallery.width(), gallery.height()] == [1320, 840], "Native window did not retain the exact requested logical size"
            result = capture(gallery, "gallery-exact-1320x840-oversized")
            assert not result["frame_fits_available_screen"], "Expected oversized frame for this scale-2 capture"
            return {"initial_window": info, "requested_logical_size": [1320, 840], "capture": result,
                    "scope": "Own-widget oversized layout capture only; no input or full physical-screen reachability claim"}
        stage("native_gallery_exact_oversized_layout_capture", exact_oversized_layout)
        return
    if args.phase == "curve":
        gallery = GalleryWindow()
        report["curve_window"] = expose(gallery)
        stage("native_existing_curve_cell_apply_plot_and_undo", lambda: gallery_curve_input(gallery))
        return
    rad, info = new_rad()
    if args.phase == "restore":
        expected = json.loads((args.output / "expected-layout.json").read_text("utf-8"))
        def check_restore():
            actual = layout_description(rad)
            assert actual == expected["docks"], {"expected": expected, "actual": actual}
            assert [rad.width(), rad.height()] == expected["logical_size"], "Restored logical window size differs"
            assert rad.session.describe()["project_path"] == str((args.output / "native-rad.caeprep").resolve())
            return {"docks": actual, "capture": capture(rad, "restored-layout"),
                    "restart": "new Python process; same isolated QSettings directory"}
        stage("cross_process_qsettings_layout_and_saved_document", check_restore)
    else:
        def normal_narrow():
            rad.resize(1320, 840); pump()
            normal = capture(rad, "rad-normal")
            rad.resize(960, 640); pump()
            return {"window": info, "normal": normal, "narrow": capture(rad, "rad-narrow")}
        stage("native_rad_normal_and_narrow", normal_narrow)
        fit_input_window(rad)
        material = next(node.ref for node in rad.provider.tree_nodes() if node.group == "Materials")
        part = next(node.ref for node in rad.provider.tree_nodes() if node.ref.native_scope.startswith("/PART/"))
        def rad_tree_edit_history():
            tree_ref(rad.model_tree, part)
            assert rad.provider.active_object() == part and rad.session.selection()["ids"]
            tree_ref(rad.model_tree, material)
            original = next(f["value"] for f in rad.session.card_fields(material.object_id) if f["name"] == "young_modulus")
            edited = 199000 if original != 199000 else 200000
            type_text(rad.field_editors["young_modulus"], str(edited))
            QTest.keyClick(rad.field_editors["young_modulus"], Qt.Key.Key_Return)
            pump()
            toolbar_action(rad, rad.undo_action)
            assert next(f["value"] for f in rad.session.card_fields(material.object_id) if f["name"] == "young_modulus") == original
            toolbar_action(rad, rad.redo_action)
            assert next(f["value"] for f in rad.session.card_fields(material.object_id) if f["name"] == "young_modulus") == edited
            toolbar_action(rad, rad.save_action)
            wait_file(rad)
            return {"tree_input": "QTest clicks", "scalar_input": "QTest keys", "undo_redo": "QTest toolbar clicks"}
        stage("rad_tree_scalar_undo_redo_save", rad_tree_edit_history)

        def vtk_render_pick():
            viewport = rad.viewport
            assert viewport is not None and viewport._initialized and not viewport._render_failed
            toolbar_action(rad, rad.iso_action)
            toolbar_action(rad, rad.fit_action)
            pump(250)
            render_window = viewport._widget.GetRenderWindow()
            render_window.Render()
            assert not render_window.GetNeverRendered() and viewport._grid.GetNumberOfCells() > 0
            image = viewport.vtk.vtkWindowToImageFilter()
            image.SetInput(render_window)
            image.ReadFrontBufferOff()
            image.Update()
            low, high = image.GetOutput().GetScalarRange()
            assert high > low, "VTK framebuffer is uniform"
            target = args.output / "native-vtk-framebuffer.png"
            writer = viewport.vtk.vtkPNGWriter()
            writer.SetFileName(str(target)); writer.SetInputConnection(image.GetOutputPort()); writer.Write()
            emitted = []
            viewport.entityPicked.connect(emitted.append)
            width, height = render_window.GetSize()
            point = None
            for index in range(viewport._grid.GetNumberOfCells()):
                cell = viewport._grid.GetCell(index)
                xyz = [sum(cell.GetPoints().GetPoint(i)[axis] for i in range(cell.GetNumberOfPoints())) / cell.GetNumberOfPoints() for axis in range(3)]
                viewport._renderer.SetWorldPoint(*xyz, 1)
                viewport._renderer.WorldToDisplay()
                x, y, _ = viewport._renderer.GetDisplayPoint()
                picker = viewport.vtk.vtkCellPicker()
                picker.AddPickList(viewport._actor); picker.PickFromListOn()
                if picker.Pick(x, y, 0, viewport._renderer):
                    point = QPoint(round(x * viewport._widget.width() / width),
                                   round((height - 1 - y) * viewport._widget.height() / height))
                    break
            assert point is not None, "No visible cell centre found for actual input"
            click(viewport._widget, point)
            assert emitted and emitted[-1].get("kind") == "element", emitted
            assert rad.session.selection()["ids"] == [emitted[-1]["id"]]
            assert viewport._highlight.GetVisibility()
            render_window.Render()
            image.Modified(); image.Update()
            highlighted = args.output / "native-vtk-post-pick-framebuffer.png"
            writer.SetFileName(str(highlighted)); writer.Write()
            return {"render_window": render_window.GetClassName(), "supports_opengl": render_window.SupportsOpenGL(),
                    "cells": viewport._grid.GetNumberOfCells(), "framebuffer_pixels": list(image.GetOutput().GetDimensions()),
                    "framebuffer": str(target), "post_pick_framebuffer": str(highlighted),
                    "post_pick_sha256": hashlib.sha256(highlighted.read_bytes()).hexdigest(),
                    "click_logical": [point.x(), point.y()], "candidate": emitted[-1],
                    "canonical_selection": rad.session.selection(), "capture": capture(rad, "vtk-pick")}
        stage("live_vtk_render_and_qtest_pick", vtk_render_pick)

        if args.scale == "1":
            def second_solid_input():
                session = PrepSession()
                session.open_rad(str(repo / "examples/rad/solid_blocks_0000.rad"))
                session.save_project(str(args.output / "native-solid.caeprep"))
                solid = MainWindow(session, enable_viewport=True)
                info = expose(solid)
                fit_input_window(solid)
                ref = next(node.ref for node in solid.provider.tree_nodes()
                           if node.ref.native_scope.startswith("/PART/"))
                tree_ref(solid.model_tree, ref)
                assert solid.provider.active_object() == ref and session.selection()["ids"]
                toolbar_action(solid, solid.iso_action); toolbar_action(solid, solid.fit_action)
                viewport = solid.viewport
                assert viewport is not None and viewport._initialized and not viewport._render_failed
                viewport.render()
                render = viewport._widget.GetRenderWindow()
                assert not render.GetNeverRendered() and viewport._grid.GetNumberOfCells() > 0
                image = viewport.vtk.vtkWindowToImageFilter(); image.SetInput(render)
                image.ReadFrontBufferOff(); image.Update()
                framebuffer = args.output / "native-solid-framebuffer.png"
                writer = viewport.vtk.vtkPNGWriter(); writer.SetFileName(str(framebuffer))
                writer.SetInputConnection(image.GetOutputPort()); writer.Write()
                solid.resize(1320, 840); pump(); normal = capture(solid, "solid-normal")
                solid.resize(960, 640); pump(); narrow = capture(solid, "solid-narrow")
                result = {"fixture": "examples/rad/solid_blocks_0000.rad", "window": info,
                          "active_part": ref.object_id, "cells": viewport._grid.GetNumberOfCells(),
                          "render_window": render.GetClassName(), "framebuffer": str(framebuffer),
                          "normal": normal, "narrow": narrow}
                solid._allow_close = True; solid.close(); solid.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                fit_input_window(rad)
                return result
            stage("second_solid_native_tree_properties_and_render", second_solid_input)

        neutral = CurveSession(); neutral.save_project(str(args.output / "neutral-start.caeprep"))
        gallery = GalleryWindow(neutral)
        gallery_info = expose(gallery)
        fit_input_window(gallery)
        def gallery_reference_catalogue():
            ref = next(node.ref for node in neutral.tree_nodes() if node.ref.kind == "material")
            tree_ref(gallery.tree, ref)
            picker = gallery.field_editors["reference_curve"]
            picker.parentWidget().ensurePolished()
            gallery.properties.scroll.ensureWidgetVisible(picker)
            pump()
            click(picker)
            gate(); QTest.keyClick(picker, Qt.Key.Key_End); QTest.keyClick(picker, Qt.Key.Key_Return)
            pump()
            selected = picker.currentData()
            assert selected is not None
            click(gallery.apply_button)
            assert next(spec.value for spec in neutral.properties(ref) if spec.name == "reference_curve") == selected
            gallery.save_project_file(str(args.output / "native-neutral.caeprep")); wait_file(gallery)
            gallery.open_project_file(str(args.output / "native-neutral.caeprep")); wait_file(gallery)
            assert gallery._curve_ref.object_id == selected.object_id
            toolbar_action(gallery, gallery.catalogue_action)
            assert gallery.assets_dock.isVisible()
            gallery.resize(1320, 840); pump()
            normal = capture(gallery, "gallery-catalogue-normal")
            gallery.resize(960, 640)
            gallery.move(gallery.screen().availableGeometry().topLeft() + QPoint(10, 10)); pump()
            scene = gallery.catalogue.scene
            reachability = [reachable(editor, gallery) for editor in scene.editor.editors.values()]
            reachability += [reachable(scene.apply_button, gallery), reachable(scene.revert_button, gallery)]
            click(scene.revert_button)
            editor = scene.editor.editors["young_modulus"]
            reachability.append(reachable(editor, gallery))
            type_text(editor, "198500")
            reachability.append(reachable(scene.apply_button, gallery))
            click(scene.apply_button)
            assert next(spec.value for spec in scene.session.properties(scene.target) if spec.name == "young_modulus") == 198500
            reachability.append(reachable(scene.undo_button, gallery))
            click(scene.undo_button)
            assert next(spec.value for spec in scene.session.properties(scene.target) if spec.name == "young_modulus") != 198500
            narrow = capture(gallery, "gallery-catalogue-narrow")
            return {"window": gallery_info, "reference": selected.object_id, "normal": normal, "narrow": narrow,
                    "narrow_reachability": reachability, "narrow_input": "Scrolled real view, asserted full control bounds, QTest Revert/edit/Apply/Undo"}
        stage("gallery_tree_typed_reference_catalogue_save_reopen", gallery_reference_catalogue)

        if args.scale == "1":
            stage("native_existing_curve_cell_apply_plot_and_undo", lambda: gallery_curve_input(gallery))

        def export_reopen():
            target = args.output / "native-export.rad"
            rad.export_rad_file(str(target)); wait_file(rad)
            assert target.exists()
            rad.open_project_file(str(args.output / "native-rad.caeprep")); wait_file(rad)
            assert rad.session.describe()["element_count"] > 0
            return {"export": str(target), "input_scope": "public window file APIs; no file-dialog input claim"}
        stage("rad_export_and_reopen", export_reopen)

        def docking():
            fit_input_window(rad)
            dock = rad.messages_dock
            click(dock, QPoint(max(30, dock.width() // 2), 10), double=True)
            floated_by_input = dock.isFloating()
            if not floated_by_input:
                dock.setFloating(True); pump()
            floating = capture(dock, "dock-floating")
            click(dock, QPoint(max(30, dock.width() // 2), 10), double=True)
            redocked_by_input = not dock.isFloating()
            if dock.isFloating():
                drag_dock(dock, rad.mapToGlobal(QPoint(12, rad.height() // 2)))
                redocked_by_input = not dock.isFloating()
            if dock.isFloating():
                dock.setFloating(False)
            rad.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
            pump()
            before_drag = rad.dockWidgetArea(dock).value
            assert before_drag == Qt.DockWidgetArea.BottomDockWidgetArea.value
            drag_dock(dock, rad.mapToGlobal(QPoint(12, rad.height() // 2)))
            moved_by_input = (not dock.isFloating()
                              and rad.dockWidgetArea(dock) == Qt.DockWidgetArea.LeftDockWidgetArea)
            drag_result = {"area": rad.dockWidgetArea(dock).value, "floating": dock.isFloating()}
            if not moved_by_input:
                dock.setFloating(False)
                rad.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
            pump()
            expected = {"docks": layout_description(rad), "logical_size": [rad.width(), rad.height()]}
            (args.output / "expected-layout.json").write_text(json.dumps(expected, indent=2), "utf-8")
            return {"float_by_qtest_double_click": floated_by_input,
                    "redock_by_qtest_gesture": redocked_by_input, "move_to_left_by_qtest_drag": moved_by_input,
                    "before_drag_area": before_drag, "drag_result_before_fallback": drag_result,
                    "api_fallback_for_final_layout": not moved_by_input,
                    "input_scope": "QTest titlebar double clicks and 12-step own-widget drag; API fallback explicitly recorded",
                    "layout": expected, "floating_capture": floating, "capture": capture(rad, "dock-redocked")}
        stage("dock_float_redock_and_prepare_restart", docking)

        def close_branches():
            tree_ref(rad.model_tree, material)
            type_text(rad.field_editors["young_modulus"], "1e")
            before = rad.session.describe()["revision"]
            cancel = modal_close(rad, QMessageBox.StandardButton.Cancel)
            assert rad.isVisible() and rad.field_editors["young_modulus"].text() == "1e"
            save_invalid = modal_close(rad, QMessageBox.StandardButton.Save)
            assert rad.isVisible() and not rad._busy and rad.session.describe()["revision"] == before
            assert rad.field_editors["young_modulus"].text() == "1e"
            type_text(rad.field_editors["young_modulus"], "198000")
            save = modal_close(rad, QMessageBox.StandardButton.Save)
            wait_file(rad)
            assert not rad.isVisible()
            reopened, reopened_info = new_rad()
            new_material = next(node.ref for node in reopened.provider.tree_nodes() if node.group == "Materials")
            tree_ref(reopened.model_tree, new_material)
            assert next(f["value"] for f in reopened.session.card_fields(new_material.object_id) if f["name"] == "young_modulus") == 198000
            type_text(reopened.field_editors["young_modulus"], "1e")
            discard = modal_close(reopened, QMessageBox.StandardButton.Discard)
            assert not reopened.isVisible()
            return {"cancel_invalid": cancel, "save_invalid": save_invalid, "save_valid_async": save,
                    "discard_invalid": discard, "reopened_window": reopened_info,
                    "save_reopened_value": 198000, "original_revision": before}
        stage("real_modal_close_save_discard_cancel_and_saved_value", close_branches)

try:
    run()
except Exception as exc:
    report["fatal"] = {"error": str(exc), "traceback": traceback.format_exc()}
finally:
    QThreadPool.globalInstance().waitForDone(15000)
    for window in reversed(windows):
        try:
            window._allow_close = True
            window.close()
            window.deleteLater()
        except RuntimeError:
            pass
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    report["remaining_workers"] = QThreadPool.globalInstance().activeThreadCount()
    native_settings_after = native_settings_snapshot()
    report["native_settings_unchanged"] = native_settings_after == native_settings_before
    (args.output / "native-settings-after.json").write_text(json.dumps(native_settings_after, indent=2), "utf-8")
    if not report["native_settings_unchanged"]:
        report["fatal"] = {"error": "Native settings changed during an explicitly isolated run; investigate without restoring unknown values"}
    report["unverified"] = ["OS SendInput and manual human input were not used",
                            "Application scale factors do not prove changes to OS monitor DPI",
                            "Oversized 1320x840 captures at forced 2x do not prove full physical-screen reachability; input uses fitted 960x640",
                            "Any false dock input assertion remains unverified; API fallback is not input evidence"]
    report["acceptance_claim"] = "Only listed stage assertions; no blanket A7 completion claim"
    report["status"] = "passed" if report["stages"] and all(s["status"] == "passed" for s in report["stages"]) and "fatal" not in report else "failed"
    manifest = args.output / f"{args.phase}-manifest.json"
    manifest.write_text(json.dumps(report, indent=2, ensure_ascii=False), "utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)

raise SystemExit(0 if report["status"] == "passed" else 1)
