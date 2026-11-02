"""Owned-window Windows file/node-move smoke; not full GUI acceptance.

Run save and reopen in separate processes with the same --output and --model.
Uses QTest controls and public window file APIs, not OS input or file dialogs.
"""
import argparse
import ctypes
from ctypes import wintypes
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
import time

parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=("save", "reopen"))
parser.add_argument("--move", action="store_true")
parser.add_argument("--model", choices=("beam_shell_tet", "truss_shell_hex"), default="beam_shell_tet")
parser.add_argument("--observe", action="store_true")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--dialog-size", choices=("900x680", "640x480"), default="900x680")
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
repo = Path(__file__).resolve().parents[2]
if args.move:
    output = output / "node-move" / args.model
    output.mkdir(parents=True, exist_ok=True)
receipt = {"phase": args.phase, "model": args.model, "status": "running",
           "source_hashes": {name: sha256((repo / name).read_bytes()).hexdigest() for name in (
               "src/caelab_prep/application/node_moves.py", "src/caelab_prep/application/session.py",
               "src/caelab_prep/application/mesh_edit_candidates.py", "src/caelab_prep/radioss/deck.py",
               "src/caelab_prep/ui/node_moves.py")}}
(output / (args.phase + ".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
def failed(kind, value, tb):
    receipt.update(status="failed", error="".join(traceback.format_exception(kind, value, tb)))
    (output / (args.phase + ".json")).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    sys.__excepthook__(kind, value, tb)
sys.excepthook = failed
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.GetUserObjectInformationW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
desktop = user32.OpenInputDesktop(0, False, 1)
if not desktop:
    raise RuntimeError(f"Input desktop unavailable: {ctypes.get_last_error()}")
try:
    name = ctypes.create_unicode_buffer(256)
    required = wintypes.DWORD()
    assert user32.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(required))
    assert name.value.casefold() == "default", f"Non-default desktop: {name.value}"
finally:
    user32.CloseDesktop(desktop)

os.environ["QT_QPA_PLATFORM"] = "windows"
from PySide6.QtCore import QSettings, QCoreApplication, QEvent, QThreadPool, Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from caelab_prep.ui import main_window

native = QSettings(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, "CAELab", "Prep")
def settings_values():
    return {key: repr(native.value(key)) for key in native.allKeys()}
before = settings_values()
def settings(organization, application):
    value = QSettings(str(output / f"{organization}-{application}.ini"), QSettings.Format.IniFormat)
    value.setFallbacksEnabled(False)
    return value
main_window.QSettings = settings
app = QApplication([])
assert app.platformName() == "windows"
window = main_window.MainWindow(enable_viewport=True)
errors = []
window._show_error = lambda error: errors.append(str(error))
window.resize(960, 640)
window.show()
assert QTest.qWaitForWindowExposed(window, 10000)

def wait_operation():
    deadline = time.monotonic() + 30
    while window._busy and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert not window._busy, "File operation timed out"
    assert not errors, errors
    app.processEvents()

source = repo / "scripts/evaluation/models/mixed-assemblies" / args.model
copied = output / "사용자 모델"
copied.mkdir(exist_ok=True)
for filename in ("model_0000.rad", "mesh.inc"):
    target = copied / filename
    if args.phase == "save":
        shutil.copyfile(source / filename, target)
hashes = {name: sha256((copied / name).read_bytes()).hexdigest() for name in ("model_0000.rad", "mesh.inc")}
project = copied / "작업 문서.caeprep"
try:
    if args.phase == "save":
        window.open_rad_file(copied / "model_0000.rad")
        wait_operation()
        if args.move:
            targets = [1, 2] if args.model == "beam_shell_tet" else [5, 6]
            group = window.session.create_node_group("Moved attachment review", targets)["card_id"]
            window.session.create_boundary_condition("Fixed attachment", group, [True]*3, [False]*3)
            app.processEvents()
            dialog = window.open_node_move()
            dialog.resize(*(int(value) for value in args.dialog_size.split("x")))
            assert QTest.qWaitForWindowExposed(dialog, 5000)
            app.processEvents()
            receipt["actual_dialog_size"] = [dialog.width(), dialog.height()]
            mesh = next(resource for resource in window.session._deck_resources() if resource.id != window.session._root_id)
            dialog.resource.setCurrentIndex(dialog.resource.findData(mesh.id))
            dialog.identifiers.setFocus()
            node_ids = "2" if args.model == "beam_shell_tet" else "5 6 7 8 9"
            QTest.keyClicks(dialog.identifiers, node_ids)
            QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton)
            assert dialog.table.rowCount() == len(node_ids.split())
            for row in range(dialog.table.rowCount()):
                editor = dialog.table.cellWidget(row, 2 if args.model == "beam_shell_tet" else 4)
                dialog.table.scrollTo(dialog.table.model().index(row, 2 if args.model == "beam_shell_tet" else 4))
                app.processEvents()
                assert editor.isVisible() and editor.visibleRegion().contains(editor.rect().center())
                QTest.mouseClick(editor, Qt.MouseButton.LeftButton)
                QTest.keyClick(editor, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
                QTest.keyClicks(editor, "11")
            QTest.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
            assert dialog._plan is not None, dialog.status.text()
            click_position = QPoint(10, dialog.reviewed.height()//2)
            assert dialog.reviewed.isVisible() and dialog.reviewed.visibleRegion().contains(click_position)
            before_click = {"checked": dialog.reviewed.isChecked(), "plan_present": dialog._plan is not None}
            QTest.mouseClick(dialog.reviewed, Qt.MouseButton.LeftButton, pos=click_position)
            print(json.dumps({"checkbox_before": before_click, "checkbox_after": dialog.reviewed.isChecked(),
                              "plan_after": dialog._plan is not None, "apply_enabled": dialog.apply_button.isEnabled(),
                              "click": [click_position.x(), click_position.y()],
                              "checkbox_size": [dialog.reviewed.width(), dialog.reviewed.height()]}), flush=True)
            assert dialog.apply_button.isEnabled()
            assert dialog.grab().save(str(output / "preview.png"))
            QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
            app.processEvents()
            actual = window.session.mesh_view()["points"]
            assert actual[1][0] == 11 if args.model == "beam_shell_tet" else all(actual[index][2] == 11 for index in range(4, 9))
            QTest.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)
            app.processEvents()
        window.save_project_file(project)
        wait_operation()
        assert project.is_file()
    else:
        window.open_project_file(project)
        wait_operation()
    projection = window.session.mesh_view()
    snapshot = {"node_ids": list(projection["node_ids"]),
                "points": [list(point) for point in projection["points"]],
                "cells": [{key: list(cell[key]) if key == "nodes" else cell[key]
                           for key in ("id", "nodes", "part_id", "formulation")} for cell in projection["cells"]]}
    assert len(snapshot["node_ids"]) == 9 and len(snapshot["cells"]) == 3
    if args.move:
        assert snapshot["points"][1] == [11, 0, 0] if args.model == "beam_shell_tet" else all(snapshot["points"][index][2] == 11 for index in range(4, 9))
        assert window.session.mesh_relationships()["stale_targets"]
    if args.phase == "save":
        (output / "expected.json").write_text(json.dumps(snapshot), encoding="utf-8")
    else:
        assert snapshot == json.loads((output / "expected.json").read_text(encoding="utf-8"))
    assert window.grab().save(str(output / (args.phase + ".png")))
    import vtk
    render_window = window.viewport._widget.GetRenderWindow()
    render_window.Render()
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(render_window)
    capture.SetInputBufferTypeToRGB()
    capture.ReadFrontBufferOff()
    capture.Update()
    scalars = capture.GetOutput().GetPointData().GetScalars()
    assert scalars is not None and len(set(memoryview(scalars).tobytes())) > 16
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(output / (args.phase + "-framebuffer.png")))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()
    if args.observe:
        (output / "observation-release").unlink(missing_ok=True)
        window.setWindowTitle("CAELab Prep Native Node Move Observation")
        window.raise_()
        window.activateWindow()
        print(json.dumps({"observation_ready": True, "title": window.windowTitle(), "pid": os.getpid(), "hwnd": int(window.winId())}), flush=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and not (output / "observation-release").exists():
            app.processEvents()
            QTest.qWait(100)
    assert hashes == {name: sha256((copied / name).read_bytes()).hexdigest() for name in hashes}
finally:
    window._allow_close = True
    window.close()
    window.deleteLater()
    assert QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert QThreadPool.globalInstance().activeThreadCount() == 0
    assert settings_values() == before, "Native settings changed"
report = {"phase": args.phase, "status": "passed", "platform": app.platformName(),
          "input_desktop": name.value, "nodes": 9, "elements": 3,
          "settings_unchanged": True, "source_unchanged": True,
          "absolute_node_move": args.move,
          "model": args.model,
          "scope": "Own Windows Qt/VTK window and file API; no OS input, IME, DPI, solver or eight-product acceptance"}
report["source_hashes"] = receipt["source_hashes"]
report["actual_dialog_size"] = receipt.get("actual_dialog_size")
(output / (args.phase + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
