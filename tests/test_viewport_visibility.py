"""Visibility uses the actual unshown MeshViewport and its VTK data pipeline.

The opt-in EGL test is a separate rendering check, not Windows GUI acceptance.
"""

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import pytest

vtk = pytest.importorskip("vtk")

from caelab_prep.application.contracts import ObjectRef
from caelab_prep.ui.viewport import MeshViewport, cell_part_key, part_key

pytestmark = pytest.mark.usefixtures("qt_widgets")
_views = []


@pytest.fixture(autouse=True)
def close_viewports(qt_widgets):
    yield
    while _views:
        view = _views.pop()
        view.shutdown()
        view.close()


def projection():
    return {
        "document_id": "document", "document_epoch": "epoch", "revision": 0,
        "projection_revision": 0, "resource_revisions": {"elements": "token"},
        "points": [(0, 0, 0), (2, 0, 0), (0, 2, 0),
                   (100, 0, 0), (102, 0, 0), (100, 2, 0),
                   (1000, 0, 0)],  # An unused point must not enlarge visible bounds.
        "node_ids": [1, 2, 3, 4, 5, 6, 7],
        "node_resources": {i: ["nodes"] for i in range(1, 8)},
        "cells": [
            {"id": 11, "type": "triangle", "nodes": [1, 2, 3], "resource_id": "elements",
             "part_id": 1, "part_ref": {"resource_id": "part-a", "native_scope": "/PART/1"}},
            {"id": 12, "type": "triangle", "nodes": [4, 5, 6], "resource_id": "elements",
             "part_id": 1, "part_ref": {"resource_id": "part-b", "native_scope": "/PART/1"}},
        ],
    }


def viewport(data=None):
    """Construct the real widget; an unshown viewport naturally does not Render."""
    view = MeshViewport()
    _views.append(view)
    view.set_mesh(projection() if data is None else data, reset_camera=False)
    return view


def selection(view, *, kind="element", ids=(11, 12)):
    return {**view._projection_stamp, "kind": kind, "ids": list(ids), "refs": [
        {"resource_id": "elements" if kind == "element" else "nodes",
         "entity_kind": kind, "local_id": identifier} for identifier in ids]}


def test_part_identity_requires_resource_and_resolved_owner():
    with pytest.raises(ValueError):
        part_key(1)
    assert part_key(("a", "/part/001")) == ("a", "/PART/1")
    assert part_key(("a", "/PART/001/77")) == ("a", "/PART/1")
    assert cell_part_key({"resource_id": "element", "part_id": 1,
                          "part_ref": {"resource_id": "owner", "native_scope": "/PART/1"}}) == ("owner", "/PART/1")
    assert cell_part_key({"resource_id": "element", "part_id": 1, "part_ref": None}) is None
    assert cell_part_key({"resource_id": "element", "part_id": 1}) == ("element", "/PART/1")


def test_hide_part_is_resource_scoped_and_does_not_mutate_projection_or_selection():
    data = projection()
    original = deepcopy(data)
    view = viewport(data)
    approved = selection(view)
    view.set_selection(approved)
    ref = ObjectRef("document", "part-a", "card-a", "rad-card", "/PART/1")
    view.hide_parts([ref])
    assert view.visible_cell_indices() == [1]
    assert view._visible_grid.GetNumberOfCells() == 1
    assert view._visible_grid.GetNumberOfPoints() == 3
    assert view._visible_bounds() == (100, 102, 0, 2, 0, 0)
    view._highlight.GetMapper().Update()
    assert view._highlight.GetMapper().GetInput().GetNumberOfCells() == 1
    assert view._selection == approved
    assert data == original
    assert view._projection_stamp["revision"] == 0


def test_visibility_survives_same_document_reprojection_and_resets_for_new_epoch():
    view = viewport()
    view.hide_parts([("part-a", "/PART/1")])
    view.set_mesh(projection() | {"projection_revision": 1}, reset_camera=False)
    assert view.visible_cell_indices() == [1]
    view.set_mesh(projection() | {"document_epoch": "reopened"}, reset_camera=False)
    assert view.visible_cell_indices() == [0, 1]
    with pytest.raises(ValueError, match="another document"):
        view.hide_parts([ObjectRef("old", "part-a", "card-a", "rad-card", "/PART/1")])
    assert view.visible_cell_indices() == [0, 1]


def test_isolate_show_all_and_hidden_selection_fit():
    view = viewport()
    approved = selection(view, ids=(11,))
    view.set_selection(approved)
    view.isolate_parts([("part-b", "/PART/1")])
    assert not view._highlight.GetVisibility()
    assert not view.fit_selection()
    assert view.fit_view()
    assert view._renderer.GetActiveCamera().GetFocalPoint() == (101, 1, 0)
    view.isolate_parts([])
    assert view.visible_cell_indices() == [1]
    view.show_all_parts()
    assert view.visible_cell_indices() == [0, 1]
    assert view._highlight.GetVisibility()
    assert view.fit_selection()
    assert view._renderer.GetActiveCamera().GetFocalPoint() == (1, 1, 0)
    with pytest.raises(ValueError, match="present"):
        view.isolate_parts([("missing", "/PART/1")])
    assert view.visible_cell_indices() == [0, 1]


def test_all_hidden_is_empty_and_does_not_reset_camera_to_hidden_model():
    view = viewport()
    view.fit_view()
    camera_position = view._renderer.GetActiveCamera().GetPosition()
    view.hide_parts([("part-a", "/PART/1"), ("part-b", "/PART/1")])
    assert view._visible_grid.GetNumberOfCells() == 0
    assert view._visible_grid.GetNumberOfPoints() == 0
    assert not view.fit_view()
    assert view._renderer.GetActiveCamera().GetPosition() == camera_position
    assert not view._hint.isHidden() and view._hint.text() == "All elements hidden"


def test_node_highlight_and_fit_exclude_hidden_and_unused_nodes():
    view = viewport()
    view.isolate_parts([("part-b", "/PART/1")])
    hidden = selection(view, kind="node", ids=(1, 7))
    view.set_selection(hidden)
    assert not view._highlight.GetVisibility()
    assert not view.fit_selection()
    visible = selection(view, kind="node", ids=(1, 4))
    view.set_selection(visible)
    assert view._highlight.GetVisibility()
    assert view._highlight.GetMapper().GetInput().GetNumberOfPoints() == 1
    assert view.fit_selection()
    assert view._renderer.GetActiveCamera().GetFocalPoint() == (100, 0, 0)
    view.show_all_parts()
    view.set_selection(selection(view, kind="node", ids=(1, 4, 7)))
    assert view._highlight.GetMapper().GetInput().GetNumberOfPoints() == 2


def test_fit_rejects_stale_selection_and_ambiguous_element_ids():
    view = viewport()
    assert not view.fit_selection(selection(view) | {"document_epoch": "old"})
    missing = selection(view, ids=(99,))
    assert not view.fit_selection(missing)
    view.set_selection(missing)
    assert not view._highlight.GetVisibility()


@pytest.mark.skipif(os.environ.get("CAELAB_TEST_EGL") != "1", reason="Opt-in EGL rendering, separate from dataset tests")
def test_egl_render_and_pick_visible_cells():
    # Driver failures must fail this check without terminating the entire suite.
    code = "import runpy; runpy.run_path(" + repr(str(Path(__file__).resolve())) + ")[\"_egl_render_and_pick\"]()"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"EGL rendering subprocess exited {result.returncode}: {result.stderr[-3000:]}"


def _egl_render_and_pick():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    view = viewport()
    view._renderer.SetBackground(0, 0, 0)
    window = vtk.vtkRenderWindow()  # Let VTK select the supported offscreen backend.
    window.SetOffScreenRendering(1)
    window.SetSize(400, 300)
    window.AddRenderer(view._renderer)
    view.hide_parts([("part-a", "/PART/1")])
    view.fit_view()
    try:
        window.Render()
        assert window.GetNeverRendered() == 0
        view._renderer.SetWorldPoint(100.5, 0.5, 0, 1)
        view._renderer.WorldToDisplay()
        x, y, _ = view._renderer.GetDisplayPoint()
        picker = vtk.vtkCellPicker()
        picker.AddPickList(view._actor)
        picker.PickFromListOn()
        assert picker.Pick(x, y, 0, view._renderer)
        originals = picker.GetDataSet().GetCellData().GetArray("ProjectionCellIndex")
        assert originals.GetValue(picker.GetCellId()) == 1
        events = []
        view.entityPicked.connect(events.append)
        view._widget.SetEventPosition(round(x), round(y))
        view.set_pick_mode("element")
        view._on_pick(None, None)
        assert events[-1]["id"] == 12 and events[-1]["resource_id"] == "elements"
        view._renderer.SetWorldPoint(100, 0, 0, 1)
        view._renderer.WorldToDisplay()
        nx, ny, _ = view._renderer.GetDisplayPoint()
        view._widget.SetEventPosition(round(nx), round(ny))
        view.set_pick_mode("node")
        view._on_pick(None, None)
        assert events[-1]["id"] == 4 and events[-1]["resource_id"] == "nodes"
        view._renderer.SetWorldPoint(0.5, 0.5, 0, 1)
        view._renderer.WorldToDisplay()
        x, y, _ = view._renderer.GetDisplayPoint()
        assert not picker.Pick(x, y, 0, view._renderer)
    finally:
        window.Finalize()
        view.shutdown()
        view.close()
