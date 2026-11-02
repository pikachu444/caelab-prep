"""Viewport cache/lookup contracts on real Qt and VTK objects.

These bounded data tests exercise ownership and invalidation, not the separate
million-element timing budget or native Windows rendering acceptance.
"""
from collections.abc import Sequence
import gc
from types import MappingProxyType

import pytest

pytest.importorskip("PySide6")
vtk = pytest.importorskip("vtk")
np = pytest.importorskip("numpy")
from vtkmodules.util.numpy_support import vtk_to_numpy

from caelab_prep.application import PrepSession
from caelab_prep.ui.viewport import MeshViewport


def _readonly(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _readonly(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_readonly(item) for item in value)
    return value


def _projection(per_part=1):
    points, node_ids, owners, cells = [], [], {}, []
    for part, suffix in enumerate(("a", "b")):
        for index in range(per_part):
            first = 1 + part * 10000 + index * 3
            x = part * 1000 + index * 3
            for offset, point in enumerate(((x, 0, 0), (x + 1, 0, 0), (x, 1, 0))):
                points.append(point)
                node_ids.append(first + offset)
                owners[first + offset] = (f"nodes-{suffix}",)
            cells.append({
                "id": 17 + index, "type": "triangle", "nodes": (first, first + 1, first + 2),
                "resource_id": f"elements-{suffix}", "part_id": 1,
                "part_ref": {"resource_id": f"parts-{suffix}", "native_scope": "/PART/1"},
            })
    return {
        "document_id": "document", "document_epoch": "epoch", "revision": 0,
        "projection_revision": 0,
        "resource_revisions": _readonly({"elements-a": "a0", "elements-b": "b0"}),
        "points": _readonly(points), "node_ids": tuple(node_ids),
        "node_resources": _readonly(owners), "cells": _readonly(cells),
    }


@pytest.fixture
def viewport_factory(qt_widgets):
    views = []

    def create(projection):
        view = MeshViewport()
        views.append(view)
        # An unshown widget naturally has no initialized render window. No
        # Render, mapper, selection method or host operation is replaced.
        view.set_mesh(projection, reset_camera=False)
        return view

    yield create
    for view in views:
        view.shutdown()


def _geometry_objects(view):
    return {
        "grid": view._grid,
        "vtk_points": view._grid.GetPoints().GetData(),
        "vtk_connectivity": view._grid.GetCells().GetConnectivityArray(),
        "buffers": view._buffers,
        "node_index": view._node_index,
        "element_index": view._element_index,
        "part_cells": view._part_cells,
        "part_data": view._part_data,
    }


def test_scalar_stamp_reuses_real_vtk_buffers_and_readonly_projection(viewport_factory):
    projection = _projection()
    view = viewport_factory(projection)
    before = _geometry_objects(view)
    buffers = dict(view._buffers)
    parts = dict(view._part_data)
    arrays = [value for value in buffers.values() if isinstance(value, np.ndarray)]
    assert arrays, "The retained buffer owners must include the actual numeric arrays"
    # This checks storage that VTK consumes, not merely a same-identity marker.
    assert any(np.shares_memory(vtk_to_numpy(before["vtk_points"]), value) for value in arrays)
    assert any(np.shares_memory(vtk_to_numpy(before["vtk_connectivity"]), value) for value in arrays)
    points_before = vtk_to_numpy(before["vtk_points"]).copy()
    view.set_selection({**view._projection_stamp, "kind": "element", "ids": [17], "refs": [
        {"resource_id": "elements-a", "entity_kind": "element", "local_id": 17}]})
    highlight_mapper = view._highlight.GetMapper()
    highlight_mapper.Update()
    highlight_filter = highlight_mapper.GetInputAlgorithm()

    updated = projection | {"revision": 5, "resource_revisions": _readonly({"elements-a": "a1", "elements-b": "b0"})}
    view.set_mesh(updated, reset_camera=False)

    assert all(_geometry_objects(view)[name] is value for name, value in before.items())
    assert all(view._buffers[name] is value for name, value in buffers.items())
    assert all(view._part_data[key] is value for key, value in parts.items())
    assert view._projection_stamp["revision"] == 5
    assert view._projection_stamp["resource_revisions"]["elements-a"] == "a1"
    assert view._highlight.GetMapper() is highlight_mapper
    assert view._highlight.GetMapper().GetInputAlgorithm() is highlight_filter
    np.testing.assert_array_equal(vtk_to_numpy(view._grid.GetPoints().GetData()), points_before)
    assert projection["cells"][0]["nodes"] == (1, 2, 3)
    assert set(view._part_data) == {("parts-a", "/PART/1"), ("parts-b", "/PART/1")}

    mapper_reference = vtk.vtkWeakReference()
    mapper_reference.Set(highlight_mapper)
    view.set_selection({**view._projection_stamp, "kind": None, "ids": [], "refs": []})
    assert view._highlight.GetMapper() is None
    assert not view._highlight.GetVisibility()
    del highlight_mapper, highlight_filter
    gc.collect()
    assert mapper_reference.Get() is None, "Clearing selection must release its old VTK pipeline"


def test_actual_structure_undo_and_document_reopen_invalidate_view_cache(viewport_factory, tmp_path):
    path = tmp_path / "independent_0000.rad"
    raw = ("/BEGIN\nViewport cache input\n      2024         0\n"
           "                  Mg                  mm                   s\n"
           "/NODE\n" + "".join(f"{identifier:10d}{x:20g}{y:20g}{0:20g}\n"
                                for identifier, x, y in ((101, 0, 0), (205, 2, 0), (309, 0, 2))) +
           "/SH3N/88\n" + "".join(f"{value:10d}" for value in (701, 101, 205, 309)) + "\n/END\n")
    path.write_bytes(raw.encode("ascii"))
    session = PrepSession()
    session.open_rad(str(path))
    first = session.mesh_view()
    view = viewport_factory(first)
    before = _geometry_objects(view)
    original_points = vtk_to_numpy(view._grid.GetPoints().GetData()).copy()

    created = session.create_shell_property("Additional user section", 2.3, native_id=91)
    after_create = session.mesh_view()
    assert after_create["projection_revision"] != first["projection_revision"]
    view.set_mesh(after_create, reset_camera=False)
    assert view._grid is not before["grid"]
    assert view._buffers is not before["buffers"]
    np.testing.assert_array_equal(vtk_to_numpy(view._grid.GetPoints().GetData()), original_points)
    assert any(card["id"] == created["card_id"] for card in session.list_cards())

    changed_grid = view._grid
    session.undo()
    after_undo = session.mesh_view()
    view.set_mesh(after_undo, reset_camera=False)
    assert after_undo["projection_revision"] != after_create["projection_revision"]
    assert view._grid is not changed_grid
    assert all(card["id"] != created["card_id"] for card in session.list_cards())
    np.testing.assert_array_equal(vtk_to_numpy(view._grid.GetPoints().GetData()), original_points)

    undo_grid = view._grid
    previous_epoch = after_undo["document_epoch"]
    session.open_rad(str(path))
    reopened = session.mesh_view()
    view.set_mesh(reopened, reset_camera=False)
    assert reopened["document_epoch"] != previous_epoch
    assert view._grid is not undo_grid
    assert view._grid.GetNumberOfCells() == 1
    np.testing.assert_array_equal(vtk_to_numpy(view._grid.GetPoints().GetData()), original_points)

    # A hidden selection filter must not keep an old million-element grid alive
    # after the user replaces the document. A VTK weak reference observes C++
    # ownership as well as Python wrapper lifetime.
    view.set_selection(session.select_entity("element", 701))
    view._highlight.GetMapper().Update()
    selected_grid = vtk.vtkWeakReference()
    selected_grid.Set(view._grid)
    session.new_document("Replacement", {"mass": "Mg", "length": "mm", "time": "s"})
    view.set_mesh(session.mesh_view(), reset_camera=False)
    gc.collect()
    assert selected_grid.Get() is None, "The previous highlight pipeline retained the replaced document grid"


class _CountedCells(Sequence):
    """Observe reads of real source rows; never substitute a product result."""
    def __init__(self, values):
        self.values = tuple(values)
        self.iterations = self.reads = 0

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        self.reads += 1
        return self.values[index]

    def __iter__(self):
        self.iterations += 1
        for value in self.values:
            self.reads += 1
            yield value


def test_typed_selection_and_part_visibility_use_existing_indexes(viewport_factory):
    projection = _projection(per_part=64)
    cells = _CountedCells(projection["cells"])
    projection["cells"] = cells
    view = viewport_factory(projection)
    assert view._cells is cells, "The immutable source rows must not be copied into a second cell catalogue"
    before = _geometry_objects(view)
    parts = dict(view._part_data)
    data_times = {key: value.GetMTime() for key, value in parts.items()}
    cells.iterations = cells.reads = 0
    selected = {**view._projection_stamp, "kind": "element", "ids": [17], "refs": [
        {"resource_id": "elements-b", "entity_kind": "element", "local_id": 17}]}

    view.set_selection(selected)
    view.hide_parts([_readonly({"resource_id": "parts-a", "native_scope": "/PART/1"})])
    assert view._visible_grid.GetNumberOfCells() == 64
    assert view.visible_cell_indices() == list(range(64, 128))
    assert view._selection == selected
    view._highlight.GetMapper().Update()
    highlight = view._highlight.GetMapper().GetInput()
    assert highlight.GetNumberOfCells() == 1
    assert highlight.GetCellData().GetArray("ProjectionCellIndex").GetValue(0) == 64
    assert view.fit_selection()
    assert view._renderer.GetActiveCamera().GetFocalPoint() == (1000.5, .5, 0.)

    view.isolate_parts([("parts-a", "/PART/1")])
    assert not view._highlight.GetVisibility()
    assert view._visible_grid.GetNumberOfCells() == 64
    view.show_all_parts()
    assert view._visible_grid.GetNumberOfCells() == 128
    assert view._highlight.GetVisibility()
    assert cells.iterations == 0, "Selection or visibility iterated all source cells again"
    assert cells.reads < 16, "A fixed single-element selection read unrelated source cells"
    assert all(_geometry_objects(view)[name] is value for name, value in before.items())
    assert all(view._part_data[key] is value for key, value in parts.items())
    assert {key: value.GetMTime() for key, value in parts.items()} == data_times
