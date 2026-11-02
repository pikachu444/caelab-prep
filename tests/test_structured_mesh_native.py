"""Opt-in Linux/X11 quad preview, framebuffer and real Qt/VTK picking."""

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
from test_native_render import _pump, _png, _readback
from test_structured_adoption import quad
from test_structured_mesh_ui import _model

pytestmark = pytest.mark.usefixtures("qt_widgets")


def test_native_structured_quad_preview_preserves_cells_and_patch_picks(quad):
    case, native = quad
    assert QApplication.instance().platformName() == "xcb"
    output = Path(os.environ["CAELAB_NATIVE_RENDER_ARTIFACT_DIR"])
    assert output.is_absolute()
    output.mkdir(parents=True, exist_ok=True)
    session, _, _ = _model(native.length_unit)
    before = session.describe()
    host = MainWindow(session, enable_viewport=True)
    host._allow_close = True
    host.show()
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
    assert len(view._cells) == view._grid.GetNumberOfCells() == len(native.elements)
    assert view._visible_cell_count == len(native.elements)
    assert {cell["id"] for cell in view._cells} == {cell.id for cell in native.elements}
    assert {cell["resource_id"] for cell in view._cells} == {native.mesh_uuid}
    assert all(view._grid.GetCellType(index) == view.vtk.VTK_QUAD for index in range(len(native.elements)))
    view.render()
    render_window = view._widget.GetRenderWindow()
    assert render_window.GetClassName() == "vtkXOpenGLRenderWindow"
    rendered, pixels = _readback(render_window)
    _png(output / (case["id"] + "-structured-quad-preview.png"), rendered)
    view._actor.SetVisibility(False)
    try:
        view.render()
        _, empty = _readback(render_window)
    finally:
        view._actor.SetVisibility(True); view.render()
    changed = sum(pixels[index:index + 3] != empty[index:index + 3] for index in range(0, len(pixels), 3))
    assert changed > 100, "The native framebuffer contains no visible quad mesh"
    emitted, picked = [], []
    view.entityPicked.connect(emitted.append)
    view.set_pick_mode("element")
    for part in sorted(set(view._cell_parts)):
        physical = next(index for index, owner in enumerate(view._cell_parts) if owner == part)
        view.isolate_parts([part]); view.fit_view(); _pump()
        points = view._grid.GetCell(physical).GetPoints()
        center = tuple(sum(points.GetPoint(i)[axis] for i in range(4)) / 4 for axis in range(3))
        view._renderer.SetWorldPoint(*center, 1.); view._renderer.WorldToDisplay()
        x, y, _ = view._renderer.GetDisplayPoint()
        width, height = render_window.GetSize()
        point = QPoint(round(x * view._widget.width() / width), round((height - 1 - y) * view._widget.height() / height))
        assert view._widget.visibleRegion().contains(point)
        emitted.clear()
        QTest.mouseClick(view._widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        _pump()
        matches = [event for event in emitted if event.get("kind") == "element"]
        assert matches, "Native Qt/VTK click did not resolve a physical quad"
        result = matches[-1]
        assert (result["resource_id"], result["id"]) == (native.mesh_uuid, view._cells[physical]["id"])
        assert result["document_id"] == result["document_epoch"] == native.mesh_uuid
        assert dialog.local_entity.currentData() == native.parts[part - 1].uuid
        picked.append({"part": part, "element": result["id"]})
    assert session.describe() == before
    evidence = {"scope": "Linux X11/Mesa Qt/VTK preview and Qt mouse picks; no Windows/OS-input/solver claim",
                "case": case["id"], "cells": len(native.elements), "nodes": len(native.nodes),
                "render_backend": render_window.GetClassName(), "mesh_pixels_against_hidden_actor": changed,
                "picked": picked}
    (output / (case["id"] + "-structured-quad-preview.json")).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    dialog.reject(); assert host.close()
