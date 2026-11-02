"""Opt-in Linux/X11 actual sweep rendering and physical-volume picks."""

import json
import os
from pathlib import Path

import pytest

if os.environ.get("CAELAB_TEST_NATIVE_RENDER") != "1":
    pytest.skip("Requires explicit Linux/X11 native render opt-in", allow_module_level=True)

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog
from test_mesh_workflow_ui import choose, pump_until
from test_native_render import _pump, _png, _readback, _screen_pixels
from test_structured_hex_adoption import sweep
from test_structured_mesh_ui import _model

pytestmark = pytest.mark.usefixtures("qt_widgets")


def test_native_sweep_preserves_hex_cells_and_picks_each_patch(sweep):
    case, native = sweep
    assert QApplication.instance().platformName() == "xcb"
    output = Path(os.environ["CAELAB_NATIVE_RENDER_ARTIFACT_DIR"])
    assert output.is_absolute()
    output.mkdir(parents=True, exist_ok=True)
    session, _, _ = _model(native.length_unit, 3)
    before = session.describe()
    host = MainWindow(session, enable_viewport=True)
    host._allow_close = True; host.show()
    assert QTest.qWaitForWindowExposed(host, 10000)
    dialog = MeshCandidateDialog(session, host, enable_viewport=True)
    dialog.resize(1100, 760); dialog.show()
    assert QTest.qWaitForWindowExposed(dialog, 10000)
    choose(dialog.source_kind, "structured_recipe")
    dialog.open_candidate(next(asset.path for asset in native.assets if asset.kind == "metadata"))
    pump_until(dialog); _pump()
    assert dialog.candidate is not None, dialog.error.text()
    view = dialog.viewport
    assert view._initialized and not view._render_failed
    assert view._grid.GetNumberOfCells() == view._visible_cell_count == len(native.elements)
    assert all(view._grid.GetCellType(i) == view.vtk.VTK_HEXAHEDRON for i in range(len(native.elements)))
    assert {cell["id"] for cell in view._cells} == {cell.id for cell in native.elements}
    view.render()
    render_window = view._widget.GetRenderWindow()
    assert render_window.GetClassName() == "vtkXOpenGLRenderWindow"
    rendered, pixels = _readback(render_window)
    _png(output / (case["id"] + "-sweep-preview.png"), rendered)
    screenshot, _ = _screen_pixels(dialog)
    assert screenshot.save(str(output / (case["id"] + "-sweep-dialog.png")))
    view._actor.SetVisibility(False)
    try:
        view.render(); _, empty = _readback(render_window)
    finally:
        view._actor.SetVisibility(True); view.render()
    changed = sum(pixels[i:i+3] != empty[i:i+3] for i in range(0, len(pixels), 3))
    assert changed > len(pixels) / 3 * .02, "No readable sweep mesh in the actual framebuffer"
    emitted, picked = [], []
    view.entityPicked.connect(emitted.append)
    view.set_pick_mode("element")
    for part in sorted(set(view._cell_parts)):
        view.isolate_parts([part]); view.fit_view(); _pump()
        emitted.clear()
        QTest.mouseClick(view._widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(view._widget.width() // 2, view._widget.height() // 2))
        _pump()
        matches = [event for event in emitted if event.get("kind") == "element"]
        assert matches, "Native Qt/VTK click did not resolve an isolated sweep patch"
        event = matches[-1]
        cell = next(cell for cell in native.elements if cell.id == event["id"])
        assert event["resource_id"] == event["document_id"] == event["document_epoch"] == native.mesh_uuid
        assert view._cell_parts[next(i for i, row in enumerate(view._cells) if row["id"] == cell.id)] == part
        assert dialog.local_entity.currentData() == cell.part_uuid
        picked.append({"patch": cell.part_uuid, "element": cell.id})
    assert session.describe() == before
    (output / (case["id"] + "-sweep-preview.json")).write_text(json.dumps({
        "scope": "Linux X11/Mesa actual hex8 preview/picking only; not Windows/frozen/solver",
        "source_case": case["id"], "nodes": len(native.nodes), "cells": len(native.elements),
        "actor_pixels": changed, "picked": picked}, indent=2), encoding="utf-8")
    dialog.reject(); assert host.close()
