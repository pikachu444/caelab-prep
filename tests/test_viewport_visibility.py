"""Visibility uses the actual unshown MeshViewport and its VTK data pipeline.

The opt-in EGL test is a separate rendering check, not Windows GUI acceptance.
"""

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

vtk = pytest.importorskip("vtk")

from caelab_prep.application.contracts import ObjectRef
from caelab_prep.ui.viewport import MeshViewport, cell_part_key, part_key

pytestmark = pytest.mark.usefixtures("qt_widgets")


class _DatasetViewport(MeshViewport):
    """Let the caller's Qt owner close this unshown pipeline before deletion.

    Other test modules import the factory without this module's fixtures. Keep
    no cross-test widget registry; qt_widgets owns their actual Qt lifetime.
    """

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


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
    view = _DatasetViewport()
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


def test_dataset_viewport_owner_closes_vtk_before_qt_deletion(qt_widgets):
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    view = viewport()
    assert isValid(view) and view._error_observer is not None
    view.close()
    assert isValid(view) and view._error_observer is None
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(view)


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


class _VisibleGridSpy:
    """Delegate vtkMultiBlockDataSet access while recording SetBlock deltas."""

    def __init__(self, target, calls):
        self._target = target
        self._calls = calls

    def SetBlock(self, index, block):
        self._calls.append((index, block is not None))
        return self._target.SetBlock(index, block)

    def __getattr__(self, name):
        return getattr(self._target, name)


class _SpyDatasetViewport(_DatasetViewport):
    """Real MeshViewport subclass spying on block updates, visibility calls, and renders."""

    def __init__(self, parent=None, *, attach_offscreen=True):
        super().__init__(parent)
        self.call_log = []
        self.set_block_calls = []
        self.render_calls = 0
        self.offscreen_renders = 0
        self._offscreen_window = None
        if attach_offscreen:
            rw = vtk.vtkRenderWindow()
            rw.SetOffScreenRendering(1)
            rw.SetSize(240, 180)
            rw.AddRenderer(self._renderer)
            rw.AddObserver("EndEvent", self._on_offscreen_end)
            self._offscreen_window = rw
            self._widget.GetRenderWindow = lambda: rw
            self._initialized = True

    def _on_offscreen_end(self, *_args):
        self.offscreen_renders += 1

    def reset_spies(self):
        self.call_log.clear()
        self.set_block_calls.clear()
        self.render_calls = 0
        self.offscreen_renders = 0

    def set_mesh(self, projection, *, reset_camera=True):
        super().set_mesh(projection, reset_camera=reset_camera)
        if not isinstance(self._visible_grid, _VisibleGridSpy):
            self._visible_grid = _VisibleGridSpy(self._visible_grid, self.set_block_calls)

    def set_hidden_parts(self, part_refs):
        self.call_log.append(("set_hidden_parts", tuple(part_refs)))
        super().set_hidden_parts(part_refs)

    def show_all_parts(self):
        self.call_log.append(("show_all_parts", ()))
        super().show_all_parts()

    def hide_parts(self, part_refs):
        self.call_log.append(("hide_parts", tuple(part_refs)))
        super().hide_parts(part_refs)

    def isolate_parts(self, part_refs):
        self.call_log.append(("isolate_parts", tuple(part_refs)))
        super().isolate_parts(part_refs)

    def render(self):
        self.render_calls += 1
        self.call_log.append(("render", ()))
        super().render()

    def shutdown(self):
        super().shutdown()
        self._offscreen_window = None


def _three_part_projection():
    return {
        "document_id": "document", "document_epoch": "epoch", "revision": 0,
        "projection_revision": 0, "resource_revisions": {"elements": "token"},
        "points": [(0, 0, 0), (2, 0, 0), (0, 2, 0),
                   (10, 0, 0), (12, 0, 0), (10, 2, 0),
                   (20, 0, 0), (22, 0, 0), (20, 2, 0)],
        "node_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "node_resources": {i: ["nodes"] for i in range(1, 10)},
        "cells": [
            {"id": 11, "type": "triangle", "nodes": [1, 2, 3], "resource_id": "elements",
             "part_id": 1, "part_ref": {"resource_id": "part-a", "native_scope": "/PART/1"}},
            {"id": 12, "type": "triangle", "nodes": [4, 5, 6], "resource_id": "elements",
             "part_id": 1, "part_ref": {"resource_id": "part-b", "native_scope": "/PART/1"}},
            {"id": 13, "type": "triangle", "nodes": [7, 8, 9], "resource_id": "elements",
             "part_id": 1, "part_ref": {"resource_id": "part-c", "native_scope": "/PART/1"}},
        ],
    }


def _multi_source_projection(*, part_count=100, source_count=20, triangles_per_part=16):
    points, node_ids, node_resources, cells = [], [], {}, []
    nid = 1
    eid = 1
    resource_revisions = {}
    for p in range(part_count):
        src_idx = p % source_count
        elem_res = f"elem-src-{src_idx:02d}"
        part_res = f"part-src-{src_idx:02d}"
        node_res = (f"node-src-{src_idx:02d}",)
        resource_revisions[elem_res] = "r0"
        part_ref = {"resource_id": part_res, "native_scope": f"/PART/{p + 1}"}
        base_x = float((p % 10) * 5)
        base_y = float((p // 10) * 5)
        for t in range(triangles_per_part):
            x = base_x + (t % 4) * 0.5
            y = base_y + (t // 4) * 0.5
            n0, n1, n2 = nid, nid + 1, nid + 2
            points.extend(((x, y, 0.0), (x + 0.4, y, 0.0), (x, y + 0.4, 0.0)))
            node_ids.extend((n0, n1, n2))
            node_resources[n0] = node_resources[n1] = node_resources[n2] = node_res
            cells.append({
                "id": eid, "type": "triangle", "nodes": (n0, n1, n2),
                "resource_id": elem_res, "part_id": p + 1, "part_ref": part_ref,
            })
            nid += 3
            eid += 1
    return {
        "document_id": "bench-doc", "document_epoch": "bench-epoch",
        "revision": 0, "projection_revision": 0,
        "resource_revisions": resource_revisions,
        "points": points, "node_ids": node_ids,
        "node_resources": node_resources, "cells": cells,
    }


@pytest.mark.parametrize("with_selection", [False, True])
def test_set_hidden_parts_applies_symmetric_difference_deltas_atomically(with_selection):
    view = _SpyDatasetViewport()
    view.set_mesh(_three_part_projection(), reset_camera=False)
    part_a = ("part-a", "/PART/1")
    part_b = ("part-b", "/PART/1")
    part_c = ("part-c", "/PART/1")
    slot_a = view._part_slots[part_a]
    slot_b = view._part_slots[part_b]
    slot_c = view._part_slots[part_c]
    if with_selection:
        view.set_selection(selection(view, ids=(11, 13)))
    view.reset_spies()

    # hide A
    view.set_hidden_parts([part_a])
    assert view.set_block_calls == [(slot_a, False)]
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert view.visible_cell_indices() == [1, 2]

    # no-op hide A again
    saved_key = view._selection_visual_key
    view.reset_spies()
    view.set_hidden_parts([part_a])
    assert view.set_block_calls == []
    assert view.render_calls == 0 and view.offscreen_renders == 0
    assert view._selection_visual_key == saved_key

    # hide A+B: already-hidden A must never be re-inserted or touched
    view.reset_spies()
    view.set_hidden_parts([part_a, part_b])
    assert view.set_block_calls == [(slot_b, False)]
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert view.visible_cell_indices() == [2]

    # isolate B (hide A+C): already-hidden A must never be re-inserted
    view.reset_spies()
    view.set_hidden_parts([part_a, part_c])
    assert set(view.set_block_calls) == {(slot_b, True), (slot_c, False)}
    assert len(view.set_block_calls) == 2
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert view.visible_cell_indices() == [1]
    assert not view._highlight.GetVisibility()

    # show all: already-visible B must never be touched
    view.reset_spies()
    view.set_hidden_parts(())
    assert set(view.set_block_calls) == {(slot_a, True), (slot_c, True)}
    assert len(view.set_block_calls) == 2
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert view.visible_cell_indices() == [0, 1, 2]
    if with_selection:
        assert view._highlight.GetVisibility()

    # no-op show all again
    view.reset_spies()
    view.set_hidden_parts(())
    assert view.set_block_calls == []
    assert view.render_calls == 0 and view.offscreen_renders == 0

    # foreign document reference fails without changing visibility or rendering
    view.reset_spies()
    with pytest.raises(ValueError, match="another document"):
        view.set_hidden_parts([ObjectRef("other-doc", "part-a", "card-a", "rad-card", "/PART/1")])
    assert view.set_block_calls == []
    assert view.render_calls == 0
    assert view.visible_cell_indices() == [0, 1, 2]
    assert view._offscreen_window.GetNeverRendered() == 0
    assert not view._render_failed


def test_prep_controller_atomic_visibility_preserves_selection_history_and_avoids_show_all_hide(
    qt_widgets, tmp_path, monkeypatch
):
    from PySide6.QtCore import Qt
    from caelab_prep.application import PrepSession
    from caelab_prep.ui import viewport as viewport_module
    from caelab_prep.ui.main_window import MainWindow

    deck = tmp_path / "three_parts_0000.rad"
    deck.write_text(
        "/BEGIN\nThree part visibility test\n      2024         0\n"
        "                  Mg                  mm                   s\n"
        "/NODE\n"
        "       101                   0                   0                   0\n"
        "       102                   1                   0                   0\n"
        "       103                   0                   1                   0\n"
        "       201                  10                   0                   0\n"
        "       202                  11                   0                   0\n"
        "       203                  10                   1                   0\n"
        "       301                  20                   0                   0\n"
        "       302                  21                   0                   0\n"
        "       303                  20                   1                   0\n"
        "/MAT/LAW1/1\nSteel\n              7.8e-9\n              210000                 0.3\n"
        "/PROP/SHELL/1\nShell\n        24         4         2         2\n"
        "                   0                   0                   0                   0               0.015\n"
        "         0                           1.0       0.83333333333                   2         0\n"
        "/PART/1\nPart A\n         1         1         0                   0\n"
        "/PART/2\nPart B\n         1         1         0                   0\n"
        "/PART/3\nPart C\n         1         1         0                   0\n"
        "/SH3N/1\n       101       101       102       103\n"
        "/SH3N/2\n       102       201       202       203\n"
        "/SH3N/3\n       103       301       302       303\n"
        "/END\n",
        encoding="ascii",
    )

    session = PrepSession()
    session.open_rad(str(deck))
    mat_card = next(c for c in session.list_cards() if c["keyword"].startswith("/MAT/"))
    original_ym = session.card_text(mat_card["id"])
    session.set_field(mat_card["id"], "young_modulus", 205000.0)

    monkeypatch.setattr(viewport_module, "MeshViewport", _SpyDatasetViewport)
    window = MainWindow(session, enable_viewport=True)
    window._allow_close = True
    window.show()
    qt_widgets.processEvents()

    view = window.viewport
    assert isinstance(view, _SpyDatasetViewport)

    cards = {c["keyword"]: c for c in session.list_cards()}
    ref_a = window.provider.ref_for_card(cards["/PART/1"])
    ref_b = window.provider.ref_for_card(cards["/PART/2"])
    ref_c = window.provider.ref_for_card(cards["/PART/3"])
    key_a = (ref_a.resource_id, ref_a.native_scope)
    key_b = (ref_b.resource_id, ref_b.native_scope)
    key_c = (ref_c.resource_id, ref_c.native_scope)
    slot_a = view._part_slots[part_key(key_a)]
    slot_b = view._part_slots[part_key(key_b)]
    slot_c = view._part_slots[part_key(key_c)]

    def part_check_states():
        model = window.model_tree.model()
        states = {}
        for row in range(model.rowCount()):
            group = model.item(row)
            if group.text() != "Parts":
                continue
            for child in range(group.rowCount()):
                item = group.child(child)
                ref = item.data(Qt.ItemDataRole.UserRole)
                states[ref] = group.child(child, 3).data(Qt.ItemDataRole.CheckStateRole)
        return states

    def snapshot():
        desc = session.describe()
        return (
            session.selection(),
            desc["revision"],
            desc["dirty"],
            desc["can_undo"],
            desc["can_redo"],
        )

    assert window.select_card(cards["/PART/1"]["id"])
    qt_widgets.processEvents()
    baseline = snapshot()
    assert baseline[1:] == (1, True, True, False)

    # 1. hide A via action
    view.reset_spies()
    window.hide_selected_action.trigger()
    qt_widgets.processEvents()
    assert [name for name, _ in view.call_log if name != "render"] == ["set_hidden_parts"]
    assert "show_all_parts" not in [name for name, _ in view.call_log]
    assert "hide_parts" not in [name for name, _ in view.call_log]
    assert view.set_block_calls == [(slot_a, False)]
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert part_check_states() == {
        ref_a: Qt.CheckState.Unchecked,
        ref_b: Qt.CheckState.Checked,
        ref_c: Qt.CheckState.Checked,
    }
    assert snapshot() == baseline

    # 2. hide A+B via tree eye toggle (selection must remain Part A)
    view.reset_spies()
    window.model_tree.visibilityRequested.emit(ref_b, False)
    qt_widgets.processEvents()
    assert [name for name, _ in view.call_log if name != "render"] == ["set_hidden_parts"]
    assert view.set_block_calls == [(slot_b, False)]
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert part_check_states() == {
        ref_a: Qt.CheckState.Unchecked,
        ref_b: Qt.CheckState.Unchecked,
        ref_c: Qt.CheckState.Checked,
    }
    assert snapshot() == baseline

    # 2b. no-op visibility call triggers 0 SetBlock and 0 renders
    view.reset_spies()
    window.model_tree.visibilityRequested.emit(ref_b, False)
    window._apply_display_state()
    assert view.set_block_calls == []
    assert view.render_calls == 0 and view.offscreen_renders == 0
    assert snapshot() == baseline

    # 3. select Part B then isolate B: already-hidden A must stay untouched
    assert window.select_card(cards["/PART/2"]["id"])
    qt_widgets.processEvents()
    isolated_baseline = snapshot()
    view.reset_spies()
    window.isolate_action.trigger()
    qt_widgets.processEvents()
    assert [name for name, _ in view.call_log if name != "render"] == ["set_hidden_parts"]
    assert set(view.set_block_calls) == {(slot_b, True), (slot_c, False)}
    assert len(view.set_block_calls) == 2
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert part_check_states() == {
        ref_a: Qt.CheckState.Unchecked,
        ref_b: Qt.CheckState.Checked,
        ref_c: Qt.CheckState.Unchecked,
    }
    assert snapshot() == isolated_baseline

    # 4. show all via action: already-visible B must stay untouched
    view.reset_spies()
    window.show_all_action.trigger()
    qt_widgets.processEvents()
    assert [name for name, _ in view.call_log if name != "render"] == ["set_hidden_parts"]
    assert set(view.set_block_calls) == {(slot_a, True), (slot_c, True)}
    assert len(view.set_block_calls) == 2
    assert view.render_calls == 1 and view.offscreen_renders == 1
    assert part_check_states() == {
        ref_a: Qt.CheckState.Checked,
        ref_b: Qt.CheckState.Checked,
        ref_c: Qt.CheckState.Checked,
    }
    assert snapshot() == isolated_baseline

    # 4b. no-op show all triggers 0 SetBlock and 0 renders
    view.reset_spies()
    window._apply_display_state()
    assert view.set_block_calls == []
    assert view.render_calls == 0 and view.offscreen_renders == 0

    # Verify undo history stayed intact for the real property edit
    window.undo_action.trigger()
    qt_widgets.processEvents()
    assert session.card_text(mat_card["id"]) == original_ym
    desc = session.describe()
    assert desc["revision"] == 2
    assert not desc["can_undo"] and desc["can_redo"]
    assert view._offscreen_window.GetNeverRendered() == 0
    assert not view._render_failed


def test_offscreen_render_window_and_100_part_20_source_benchmark():
    proj = _multi_source_projection(part_count=100, source_count=20, triangles_per_part=16)
    view = _SpyDatasetViewport()
    view.set_mesh(proj, reset_camera=False)
    view.fit_view()

    # Offscreen pixel readback confirms visible vs all-hidden actually updates framebuffer
    rw = view._offscreen_window
    rw.Render()
    pixels_all = vtk.vtkUnsignedCharArray()
    rw.GetRGBACharPixelData(0, 0, 239, 179, 1, pixels_all)

    part_keys = [(f"part-src-{p % 20:02d}", f"/PART/{p + 1}") for p in range(100)]
    view.set_hidden_parts(part_keys)
    pixels_none = vtk.vtkUnsignedCharArray()
    rw.GetRGBACharPixelData(0, 0, 239, 179, 1, pixels_none)
    assert any(pixels_all.GetValue(i) != pixels_none.GetValue(i) for i in range(pixels_all.GetNumberOfValues()))

    # 100 operations across 100 parts / 20 sources: 80 distinct transitions + 20 no-ops
    view.set_hidden_parts(())
    ops = []
    for i in range(100):
        step = i % 5
        if step == 0:
            ops.append(part_keys[:((i % 10) + 1) * 5])
        elif step == 1:
            ops.append(ops[-1])  # intentional no-op repeat
        elif step == 2:
            keep = i % 100
            ops.append([k for j, k in enumerate(part_keys) if j != keep])
        elif step == 3:
            keep = (i * 7) % 100
            ops.append([k for j, k in enumerate(part_keys) if j != keep])
        else:
            ops.append(())

    view.reset_spies()
    latencies_ms = []
    for target in ops:
        start = time.perf_counter()
        view.set_hidden_parts(target)
        latencies_ms.append((time.perf_counter() - start) * 1000.0)
    latencies_ms.sort()
    p95_ms = latencies_ms[int(0.95 * len(latencies_ms)) - 1]
    assert view.render_calls == 80
    assert view.offscreen_renders == 80
    assert p95_ms < 200.0
    assert rw.GetNeverRendered() == 0
    assert not view._render_failed
