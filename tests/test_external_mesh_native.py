"""Opt-in real Linux/X11 import preview and adopted-mesh framebuffer evidence.

This uses two independent CAD-less inputs and the production menu/dialog/worker.
It is not Windows, vendor-product or representative model-size validation.
"""
import json
import os
from collections import Counter
from pathlib import Path

import pytest

if os.environ.get("CAELAB_TEST_NATIVE_RENDER") != "1":
    pytest.skip("Requires explicit native X11 rendering opt-in", allow_module_level=True)

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from caelab_prep.ui.main_window import MainWindow
from test_external_mesh import external_input, gmsh_sdk, session_for, state
from test_external_mesh_ui import wait_task
from test_native_render import _pump, _png, _readback, _screen_pixels

pytestmark = pytest.mark.usefixtures("qt_widgets")


def _click(widget, point=None):
    point = point or widget.rect().center()
    assert widget.isEnabled() and widget.isVisible()
    assert widget.visibleRegion().contains(point), f"Click target is clipped: {widget.objectName() or type(widget).__name__}"
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    _pump()


def _mesh_capture(view, output, stem, *, expected_ids, resource_id, dimension):
    assert view is not None and view.isVisible() and view._initialized
    # The canonical grid contains physical elements. Per-PART display blocks
    # contain their exterior faces: each of these two tetrahedra contributes
    # four triangles, including the separately owned shared interface.
    assert len(view._cells) == view._grid.GetNumberOfCells() == view._visible_cell_count == 2
    assert view.visible_cell_indices() == [0, 1]
    assert {(cell["resource_id"], cell["id"]) for cell in view._cells} == {
        (resource_id, identifier) for identifier in expected_ids}
    expected_type = view.vtk.VTK_TRIANGLE if dimension == 2 else view.vtk.VTK_TETRA
    assert [view._grid.GetCellType(index) for index in range(2)] == [expected_type]*2
    faces = Counter()
    for index in range(view._visible_grid.GetNumberOfBlocks()):
        block = view._visible_grid.GetBlock(index)
        assert block is not None
        provenance = block.GetCellData().GetArray("ProjectionCellIndex")
        assert provenance is not None and provenance.GetNumberOfTuples() == block.GetNumberOfCells()
        for row in range(block.GetNumberOfCells()):
            physical = int(provenance.GetValue(row))
            assert 0 <= physical < 2
            faces[physical] += 1
    assert faces == Counter({0: 1 if dimension == 2 else 4, 1: 1 if dimension == 2 else 4})
    assert view._visible_grid.GetNumberOfCells() == sum(faces.values())
    assert view._widget.width() >= 100 and view._widget.height() >= 100
    assert view._widget.visibleRegion().contains(view._widget.rect().center())
    view.render()
    native = view._widget.GetRenderWindow()
    assert native.GetClassName() == "vtkXOpenGLRenderWindow" and native.GetNeverRendered() == 0
    assert not view._render_failed
    rendered, pixels = _readback(native)
    _png(output / (stem + "-viewport.png"), rendered)
    view._actor.SetVisibility(False)
    try:
        view.render()
        _, empty = _readback(native)
    finally:
        view._actor.SetVisibility(True); view.render()
    changed = sum(pixels[n:n + 3] != empty[n:n + 3] for n in range(0, len(pixels), 3))
    assert changed > 100, "The actual native framebuffer contains no mesh"
    # Exercise the real Qt -> QVTK -> cell-picker path against each separately
    # owned PART. Isolation makes both sides of the shared tetrahedral interface
    # independently pickable without substituting a direct selection call.
    emitted, picked = [], []
    view.entityPicked.connect(emitted.append)
    old_mode = view._pick_mode
    try:
        view.set_pick_mode("element")
        for physical in range(2):
            part = view._cell_parts[physical]
            view.isolate_parts([part]); view.fit_view(); _pump()
            data = view._part_data[part]
            expected = view._cells[physical]
            accepted = None
            for face in range(data.GetNumberOfCells()):
                points = data.GetCell(face).GetPoints()
                center = tuple(sum(points.GetPoint(i)[axis] for i in range(points.GetNumberOfPoints())) / points.GetNumberOfPoints()
                               for axis in range(3))
                view._renderer.SetWorldPoint(*center, 1.); view._renderer.WorldToDisplay()
                x, y, _ = view._renderer.GetDisplayPoint()
                width, height = native.GetSize()
                point = QPoint(round(x*view._widget.width()/width), round((height-1-y)*view._widget.height()/height))
                if not view._widget.rect().contains(point): continue
                emitted.clear(); _click(view._widget, point)
                matches = [item for item in emitted if item.get("kind") == "element"]
                if not matches: continue
                accepted = matches[-1]
                assert (accepted["resource_id"], accepted["id"]) == (resource_id, expected["id"])
                assert accepted["document_epoch"] == view._projection_stamp["document_epoch"]
                assert accepted["resource_revision"] == view._projection_stamp["resource_revisions"][resource_id]
                break
            assert accepted is not None, f"No native face pick resolved physical element {expected['id']}"
            picked.append({"resource_id": accepted["resource_id"], "element_id": accepted["id"]})
    finally:
        view.entityPicked.disconnect(emitted.append)
        view.show_all_parts(); view.isometric_view(); view.set_pick_mode(old_mode); _pump()
    assert {item["element_id"] for item in picked} == set(expected_ids)
    return {"render_backend": native.GetClassName(), "render_size": list(native.GetSize()),
            "mesh_pixels_against_hidden_actor": changed, "physical_cells": 2,
            "display_faces": sum(faces.values()), "physical_cell_picks": picked}


def test_native_external_mesh_preview_adoption_and_visible_controls(external_input, tmp_path):
    source, dimension = external_input
    output = Path(os.environ["CAELAB_NATIVE_RENDER_ARTIFACT_DIR"])
    assert output.is_absolute(); output.mkdir(parents=True, exist_ok=True)
    assert QApplication.instance().platformName() == "xcb"
    session, material, section = session_for(dimension)
    original = state(session)
    window = MainWindow(session, presentation="hypermesh", enable_viewport=True)
    window._allow_close = True; window.resize(960, 640); window.show()
    assert QTest.qWaitForWindowExposed(window, 10000); _pump()
    stem = f"external-msh-{dimension}d-960x640"
    evidence = {"status": "running", "source_format": "2.2" if dimension == 2 else "4.1",
                "scope": "Linux X11 real Qt/VTK import; no CAD, Windows or commercial-product claim"}
    errors = []

    def exercise_dialog():
        dialog = window.mesh_import.dialog
        try:
            dialog.resize(900, 560)
            assert QTest.qWaitForWindowExposed(dialog, 10000); _pump()
            assert dialog.screen().availableGeometry().contains(dialog.frameGeometry())
            dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "native-import"))
            dialog.length.setCurrentIndex(dialog.length.findData("mm"))
            scroll = dialog.findChild(QScrollArea)
            scroll.ensureWidgetVisible(dialog.inspect_button); _pump(); _click(dialog.inspect_button)
            wait_task(dialog)
            assert dialog.candidate is not None, dialog.error.text()
            assert state(session) == original
            evidence["source_inventory"] = sum(row.count for row in dialog.candidate.inventory)
            evidence["groups"] = [{"name": group.name, "kind": group.kind, "members": list(group.member_ids)}
                                  for group in dialog.candidate.groups]
            original_ids = {501, 901} if dimension == 2 else {402, 403}
            evidence["preview"] = _mesh_capture(dialog.viewport, output, stem + "-preview",
                expected_ids=original_ids, resource_id=dialog.candidate.mesh_uuid, dimension=dimension)
            scroll.ensureWidgetVisible(dialog.quality); _pump()
            cell = dialog.quality.visualItemRect(dialog.quality.item(0, 0)).center()
            _click(dialog.quality.viewport(), cell)
            assert dialog.viewport._highlight.GetVisibility()
            dialog.viewport._highlight.GetMapper().Update()
            assert dialog.viewport._highlight.GetMapper().GetInput().GetNumberOfCells() == 1
            if dimension == 3:
                boundary_row = next(row for row in range(dialog.quality.rowCount())
                                    if dialog.quality.item(row, 0).text() == "401")
                _click(dialog.quality.viewport(), dialog.quality.visualItemRect(dialog.quality.item(boundary_row, 0)).center())
                assert dialog.viewport._selection["kind"] == "node"
                assert set(dialog.viewport._selection["ids"]) == {10, 20, 30}
            screenshot, _ = _screen_pixels(dialog)
            assert screenshot.save(str(output / (stem + "-preview-window.png")), "PNG")
            for box, identifier in ((dialog.material, material), (dialog.section, section)):
                scroll.ensureWidgetVisible(box); _pump()
                assert box.visibleRegion().contains(box.rect().center())
                box.setFocus()
                QTest.keyClick(box, Qt.Key.Key_Home)
                for _ in range(box.findData(identifier)): QTest.keyClick(box, Qt.Key.Key_Down)
                _pump()
                assert box.currentData() == identifier
            _click(dialog.adopt_button); wait_task(dialog)
            assert dialog.result is not None, dialog.error.text()
            evidence["adoption_revision_delta"] = session.describe()["revision"] - original[0]
            assert evidence["adoption_revision_delta"] == 1
        except BaseException as exc:
            errors.append(exc)
            screenshot, _ = _screen_pixels(dialog)
            screenshot.save(str(output / (stem + "-failure.png")), "PNG")
            dialog.reject()

    try:
        QTimer.singleShot(0, exercise_dialog)
        window.mesh_import.action.trigger()  # Production command opens its real modal event loop.
        if errors: raise errors[0]
        _pump()
        assert session.describe()["element_count"] == 2
        original_ids = {501, 901} if dimension == 2 else {402, 403}
        adopted_ids = {window.mesh_import.dialog.result["element_id_map"][value] for value in original_ids}
        evidence["adopted"] = _mesh_capture(window.viewport, output, stem + "-adopted",
            expected_ids=adopted_ids, resource_id=window.mesh_import.dialog.result["resource_id"], dimension=dimension)
        screenshot, _ = _screen_pixels(window)
        assert screenshot.save(str(output / (stem + "-adopted-window.png")), "PNG")
        evidence["status"] = "passed"
    except BaseException as exc:
        evidence["status"] = "failed"; evidence["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (output / (stem + ".json")).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        window.close(); _pump()
