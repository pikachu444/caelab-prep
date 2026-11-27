"""Headless/offscreen verification for MeshViewport crinkle-cut section slicing,
element-family coloring, PrepWorkspace inline inspection strip, and MeshCandidateDialog
Hybrid Hex-Core / Revolved Multi-Block Sweep / mesher_solver_gate badges."""

from __future__ import annotations

import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from vtkmodules.util.numpy_support import vtk_to_numpy

vtk = pytest.importorskip("vtk")
gmsh = pytest.importorskip("gmsh")

from caelab_prep.application import PrepSession
from caelab_prep.application.hybrid_hex_core import generate_hybrid_hex_core
from caelab_prep.ui.design import ELEMENT_FAMILY_PALETTE_DARK, ELEMENT_FAMILY_PALETTE_LIGHT
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog
from caelab_prep.ui.viewport import SOLID_ELEMENT_FAMILIES, MeshViewport
from test_mesh_workflow_ui import choose
from test_mesher_complex_3d_benchmarks import _write_fixture

pytestmark = pytest.mark.usefixtures("qt_widgets")


def _wait_dialog(dialog, *, timeout: float = 120.0) -> None:
    end = time.monotonic() + timeout
    while dialog._task is not None and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()
    assert dialog._task is None, "Dialog background worker timed out"


def _cleanup(widget) -> None:
    if hasattr(widget, "viewport") and getattr(widget, "viewport", None) is not None:
        if hasattr(widget.viewport, "shutdown"):
            widget.viewport.shutdown()
    if isinstance(widget, MeshViewport):
        widget.shutdown()
    if hasattr(widget, "_allow_close"):
        widget._allow_close = True
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def _hex_to_rgb_tuple(hex_color: str) -> tuple[int, int, int]:
    s = hex_color.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _create_session(unit: str = "mm") -> PrepSession:
    session = PrepSession()
    session.new_document("Hybrid inspection model", {"mass": "Mg", "length": unit, "time": "s"})
    session.create_material("Structural steel", 7.85e-9, 210000.0, 0.3)
    session.create_solid_property("Solid section")
    return session


def _seven_family_projection() -> dict:
    """Build a multi-part 3D projection containing all 7 solid element families
    arranged along X = [0..28] so crinkle-cut slicing cleanly separates cells."""
    points = []
    node_ids = []
    cells = []
    nid = 1

    def add_pts(coords):
        nonlocal nid
        ids = []
        for xyz in coords:
            points.append(tuple(float(c) for c in xyz))
            node_ids.append(nid)
            ids.append(nid)
            nid += 1
        return ids

    # 1. Hex8 at X in [0, 2]
    hex8_nodes = add_pts([
        (0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0),
        (0, 0, 2), (2, 0, 2), (2, 2, 2), (0, 2, 2),
    ])
    cells.append({"id": 101, "type": "hexahedron", "nodes": hex8_nodes, "part_id": 1, "resource_id": "r1"})

    # 2. Wedge6 at X in [4, 6]
    wedge6_nodes = add_pts([
        (4, 0, 0), (6, 0, 0), (5, 2, 0),
        (4, 0, 2), (6, 0, 2), (5, 2, 2),
    ])
    cells.append({"id": 102, "type": "wedge6", "nodes": wedge6_nodes, "part_id": 1, "resource_id": "r1"})

    # 3. Pyramid5 at X in [8, 10]
    pyr5_nodes = add_pts([
        (8, 0, 0), (10, 0, 0), (10, 2, 0), (8, 2, 0), (9, 1, 2),
    ])
    cells.append({"id": 103, "type": "pyramid5", "nodes": pyr5_nodes, "part_id": 1, "resource_id": "r1"})

    # 4. Tet4 at X in [12, 14]
    tet4_nodes = add_pts([
        (12, 0, 0), (14, 0, 0), (13, 2, 0), (13, 0.7, 2),
    ])
    cells.append({"id": 104, "type": "tetra4", "nodes": tet4_nodes, "part_id": 2, "resource_id": "r1"})

    # 5. Tet10 at X in [16, 18] (VTK edge order: 01, 12, 20, 03, 13, 23)
    c0, c1, c2, c3 = (16.0, 0.0, 0.0), (18.0, 0.0, 0.0), (17.0, 2.0, 0.0), (17.0, 0.7, 2.0)
    mid = lambda a, b: tuple((x + y) * 0.5 for x, y in zip(a, b))
    tet10_nodes = add_pts([
        c0, c1, c2, c3,
        mid(c0, c1), mid(c1, c2), mid(c2, c0), mid(c0, c3), mid(c1, c3), mid(c2, c3),
    ])
    cells.append({"id": 105, "type": "tetra10", "nodes": tet10_nodes, "part_id": 2, "resource_id": "r1"})

    # 6. Hex20 at X in [20, 22] (VTK edge order: 01,12,23,30, 45,56,67,74, 04,15,26,37)
    hc = [
        (20.0, 0.0, 0.0), (22.0, 0.0, 0.0), (22.0, 2.0, 0.0), (20.0, 2.0, 0.0),
        (20.0, 0.0, 2.0), (22.0, 0.0, 2.0), (22.0, 2.0, 2.0), (20.0, 2.0, 2.0),
    ]
    hex20_edges = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
    hex20_nodes = add_pts([*hc, *(mid(hc[a], hc[b]) for a, b in hex20_edges)])
    cells.append({"id": 106, "type": "hex20", "nodes": hex20_nodes, "part_id": 2, "resource_id": "r1"})

    # 7. Wedge15 at X in [24, 26] (VTK edge order: 01,12,20, 34,45,53, 03,14,25)
    wc = [
        (24.0, 0.0, 0.0), (26.0, 0.0, 0.0), (25.0, 2.0, 0.0),
        (24.0, 0.0, 2.0), (26.0, 0.0, 2.0), (25.0, 2.0, 2.0),
    ]
    w15_edges = ((0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5))
    w15_nodes = add_pts([*wc, *(mid(wc[a], wc[b]) for a, b in w15_edges)])
    cells.append({"id": 107, "type": "wedge15", "nodes": w15_nodes, "part_id": 2, "resource_id": "r1"})

    # Unused stray node far away must NOT skew section cut bounds
    points.append((5000.0, 5000.0, 5000.0))
    node_ids.append(nid)

    return {
        "document_id": "doc7",
        "document_epoch": "ep7",
        "revision": 0,
        "projection_revision": 0,
        "resource_revisions": {"r1": 0},
        "points": points,
        "node_ids": node_ids,
        "node_resources": {i: ["r1"] for i in node_ids},
        "cells": cells,
    }


def test_viewport_section_slice_crinkle_cut_and_7_family_color_scalars():
    view = MeshViewport()
    try:
        proj = _seven_family_projection()
        view.set_mesh(proj, reset_camera=False)

        # Default mode is "part" and preserves existing part_colors()
        assert view.color_mode() == "part"
        p_colors = view.part_colors()
        assert len(p_colors) == 2
        assert view.visible_cell_indices() == [0, 1, 2, 3, 4, 5, 6]

        # Switch to element_family color mode and verify all 7 distinct family colors
        view.set_color_mode("element_family")
        assert view.color_mode() == "element_family"
        fam_colors = view.element_family_colors()
        assert tuple(fam_colors.keys()) == SOLID_ELEMENT_FAMILIES
        assert len(set(fam_colors.values())) == 7
        for fam, hex_col in fam_colors.items():
            assert hex_col == ELEMENT_FAMILY_PALETTE_LIGHT[fam]

        # Verify actual VTK cell scalar RGB bytes on every visible block match element_family_colors()
        expected_rgb_by_row = [
            _hex_to_rgb_tuple(fam_colors[fam])
            for fam in ("Hex8", "Wedge6", "Pyramid5", "Tet4", "Tet10", "Hex20", "Wedge15")
        ]
        grid_scalars = vtk_to_numpy(view._grid.GetCellData().GetScalars())
        assert [tuple(int(c) for c in row) for row in grid_scalars] == expected_rgb_by_row

        for slot in range(view._visible_grid.GetNumberOfBlocks()):
            poly = view._visible_grid.GetBlock(slot)
            assert poly is not None and poly.GetNumberOfCells() > 0
            poly_rows = vtk_to_numpy(poly.GetCellData().GetArray("GridCellRow"))
            poly_scalars = vtk_to_numpy(poly.GetCellData().GetScalars())
            for r_idx, rgb in zip(poly_rows, poly_scalars):
                assert tuple(int(c) for c in rgb) == expected_rgb_by_row[int(r_idx)]

        # Dark theme updates active family palette without losing contrast or distinctness
        view.set_theme_mode("dark")
        dark_fam_colors = view.element_family_colors()
        assert len(set(dark_fam_colors.values())) == 7
        for fam, hex_col in dark_fam_colors.items():
            assert hex_col == ELEMENT_FAMILY_PALETTE_DARK[fam]

        # Crinkle-cut section slice along X at fraction=0.5 (used X range is [0, 26] -> cut at X=13.0)
        # Stray node at X=5000 is ignored; cells 0,1,2,3 have centroids 1, 5, 9, 13 <= 13.0!
        sel_all = {
            "document_id": "doc7",
            "document_epoch": "ep7",
            "revision": 0,
            "projection_revision": 0,
            "kind": "element",
            "ids": [101, 102, 103, 104, 105, 106, 107],
            "refs": [{"resource_id": "r1", "entity_kind": "element", "local_id": cid} for cid in range(101, 108)],
        }
        view.set_selection(sel_all)
        assert view._highlight.GetMapper().GetInput().GetNumberOfCells() == 7

        view.set_section_slice("x", 0.45, flip=False)  # cut = 11.7 -> keeps Hex8(1), Wedge6(5), Pyramid5(9)
        assert view.section_slice() == {"axis": "x", "fraction": pytest.approx(0.45), "flip": False}
        assert view.visible_cell_indices() == [0, 1, 2]
        # Highlighted selection stays consistent with visible sliced cells
        assert view._highlight.GetMapper().GetInput().GetNumberOfCells() == 3
        # Verify un-sliced whole 3D surface faces: Hex8 (6 quads) + Wedge6 (5 faces) + Pyramid5 (5 faces) = 16 polygons
        block0 = view._visible_grid.GetBlock(0)
        assert block0 is not None
        assert block0.GetNumberOfCells() == 6 + 5 + 5

        # Flip=True shows the complementary cells past the cut plane (Tet4, Tet10, Hex20, Wedge15)
        view.set_section_slice("x", 0.45, flip=True)
        assert view.visible_cell_indices() == [3, 4, 5, 6]
        assert view._highlight.GetMapper().GetInput().GetNumberOfCells() == 4

        # Y and Z axes + boundary slider fractions [0.05, 0.95] and [0.0, 1.0]
        for axis in ("y", "z"):
            view.set_section_slice(axis, 0.5, flip=False)
            assert len(view.visible_cell_indices()) > 0
        view.set_section_slice("x", 0.05, flip=False)
        assert view.visible_cell_indices() == [0]
        view.set_section_slice("x", 1.0, flip=False)
        assert view.visible_cell_indices() == [0, 1, 2, 3, 4, 5, 6]

        # Clear slice restores all cells and full highlight
        view.set_section_slice(None)
        assert view.section_slice()["axis"] is None
        assert view.visible_cell_indices() == [0, 1, 2, 3, 4, 5, 6]
        assert view._highlight.GetMapper().GetInput().GetNumberOfCells() == 7

        # Validation guards
        with pytest.raises(ValueError):
            view.set_color_mode("invalid_mode")
        with pytest.raises(ValueError):
            view.set_section_slice("w", 0.5)
        with pytest.raises(ValueError):
            view.set_section_slice("x", 1.5)
    finally:
        _cleanup(view)


def test_mesh_candidate_dialog_hybrid_hex_core_bracket_assembly_and_tet_fallback(tmp_path):
    bracket_step, (bracket_vol,) = _write_fixture("bracket", tmp_path)
    assembly_step, assembly_vols = _write_fixture("assembly", tmp_path)

    session = _create_session("mm")
    dialog = MeshCandidateDialog(
        session,
        enable_viewport=True,
        language="ko",
        theme_mode="dark",
        initial_source_kind="hybrid_hex_core",
    )
    try:
        dialog.show()
        QApplication.processEvents()
        assert dialog.source_kind.currentData() == "hybrid_hex_core"
        assert dialog.core_size.isVisible()
        assert dialog.boundary_size.isVisible()
        assert dialog.safety_margin.isVisible()

        # 1. Complex multi-feature bracket (Hex8 + Pyramid5 + Tet4)
        dialog.source.setText(str(bracket_step))
        dialog.output.setText(str(tmp_path / "bracket_hybrid_out"))
        dialog.core_size.accept_value("2.0")
        dialog.boundary_size.accept_value("1.5")
        dialog.safety_margin.accept_value("0.1")
        assert dialog.generate()
        _wait_dialog(dialog, timeout=90)

        assert dialog.candidate is not None, dialog.error.text()
        assert dialog.readout_frame.isVisible()
        counts_text = dialog.family_counts_label.text()
        for fam in ("Hex8:", "Wedge6: 0", "Pyramid5:", "Tet4:"):
            assert fam in counts_text
        # Bracket hybrid must contain positive Hex8, Pyramid5, and Tet4 counts
        fam_counts = dialog.viewport.element_family_counts()
        assert fam_counts["Hex8"] > 0
        assert fam_counts["Pyramid5"] > 0
        assert fam_counts["Tet4"] > 0
        assert "상대 CAD 체적 오차:" in dialog.volume_error_label.text()
        assert "최소 스케일드 야코비안:" in dialog.jacobian_sicn_label.text()
        assert "최소 사면체 SICN:" in dialog.jacobian_sicn_label.text()

        # Solver gate badges must explicitly flag Pyramid5 rejection for both solvers
        assert dialog.ccx_gate_badge.property("solverAdmissible") is False
        assert dialog.radioss_gate_badge.property("solverAdmissible") is False
        assert "Pyramid5" in dialog.ccx_gate_badge.text() and "부적합" in dialog.ccx_gate_badge.text()
        assert "Pyramid5" in dialog.radioss_gate_badge.text() and "부적합" in dialog.radioss_gate_badge.text()

        # Switch language dynamically to EN and Light theme -> badges update cleanly
        dialog.apply_ui_language("en")
        dialog.apply_theme_mode("light")
        assert "Pyramid5 transition elements" in dialog.ccx_gate_badge.text()
        assert "Rejected" in dialog.ccx_gate_badge.text()
        assert "Pyramid5 transition elements" in dialog.radioss_gate_badge.text()

        # Slice inside MeshCandidateDialog's own inspection_bar
        assert dialog.inspection_bar is not None
        QTest.mouseClick(dialog.inspection_bar.color_buttons["element_family"], Qt.MouseButton.LeftButton)
        QTest.mouseClick(dialog.inspection_bar.axis_buttons["x"], Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert dialog.viewport.color_mode() == "element_family"
        assert dialog.viewport.section_slice()["axis"] == "x"
        assert 0 < len(dialog.viewport.visible_cell_indices()) < sum(fam_counts.values())

        # 2. 7-part bolted assembly via auto conformal hybrid assembly dispatch
        dialog.source.setText(str(assembly_step))
        dialog.output.setText(str(tmp_path / "assembly_hybrid_out"))
        dialog.core_size.accept_value("2.0")
        dialog.boundary_size.accept_value("1.5")
        dialog.safety_margin.accept_value("0.0")
        dialog.allow_tet_fallback.setChecked(True)
        assert dialog.generate()
        _wait_dialog(dialog, timeout=120)
        assert dialog.candidate is not None, dialog.error.text()
        assert len(dialog.candidate.native.parts) == len(assembly_vols) == 7
        asm_counts = dialog.viewport.element_family_counts()
        assert asm_counts["Hex8"] > 0 and asm_counts["Pyramid5"] > 0 and asm_counts["Tet4"] > 0
        assert dialog.ccx_gate_badge.property("solverAdmissible") is False
        assert dialog.radioss_gate_badge.property("solverAdmissible") is False

        # 3. Thin coreless solid with allow_tet_fallback=True -> pure Tet4 -> both solver badges VALID
        dialog.core_size.accept_value("25.0")  # exceeds bracket extent -> triggers Tet4 fallback
        dialog.source.setText(str(bracket_step))
        dialog.output.setText(str(tmp_path / "bracket_fallback_out"))
        dialog.allow_tet_fallback.setChecked(True)
        assert dialog.generate()
        _wait_dialog(dialog, timeout=90)
        assert dialog.candidate is not None, dialog.error.text()
        fb_counts = dialog.viewport.element_family_counts()
        assert fb_counts == {"Tet4": fb_counts["Tet4"]} and fb_counts["Tet4"] > 0
        assert dialog.ccx_gate_badge.property("solverAdmissible") is True
        assert "C3D4" in dialog.ccx_gate_badge.text()
        assert dialog.radioss_gate_badge.property("solverAdmissible") is True
        assert "/TETRA4" in dialog.radioss_gate_badge.text()
    finally:
        _cleanup(dialog)


def test_mesh_candidate_dialog_revolved_sweep_housing_and_non_axisymmetric_guidance(tmp_path):
    housing_step, (housing_vol,) = _write_fixture("housing", tmp_path)
    bracket_step, _ = _write_fixture("bracket", tmp_path)

    session = _create_session("mm")
    dialog = MeshCandidateDialog(
        session,
        enable_viewport=True,
        language="ko",
        theme_mode="dark",
        initial_source_kind="revolved_hex_sweep",
    )
    try:
        dialog.show()
        QApplication.processEvents()
        assert dialog.source_kind.currentData() == "revolved_hex_sweep"

        # 1. Stepped chamfered axisymmetric housing -> 28 sector blocks of pure Hex8
        dialog.source.setText(str(housing_step))
        dialog.output.setText(str(tmp_path / "housing_revolved_out"))
        dialog.size.accept_value("2.0")
        assert dialog.generate()
        _wait_dialog(dialog, timeout=90)

        assert dialog.candidate is not None, dialog.error.text()
        assert len(dialog.candidate.native.parts) == 28
        assert dialog.candidate.cad_volume == pytest.approx(housing_vol, rel=1e-6)
        rev_counts = dialog.viewport.element_family_counts()
        assert set(rev_counts.keys()) == {"Hex8"} and rev_counts["Hex8"] > 0
        assert dialog.ccx_gate_badge.property("solverAdmissible") is True
        assert "적합" in dialog.ccx_gate_badge.text() and "C3D8" in dialog.ccx_gate_badge.text()
        assert dialog.radioss_gate_badge.property("solverAdmissible") is True
        assert "적합" in dialog.radioss_gate_badge.text() and "/BRICK" in dialog.radioss_gate_badge.text()

        # 2. Non-axisymmetric bracket.step -> clear Korean & English engineering guidance
        dialog.source.setText(str(bracket_step))
        dialog.output.setText(str(tmp_path / "bracket_revolved_fail"))
        assert dialog.generate()
        _wait_dialog(dialog, timeout=60)
        assert dialog.candidate is None
        ko_err = dialog.error.text()
        assert "비축대칭 형상 감지" in ko_err
        assert "하이브리드 육면체 코어" in ko_err

        dialog.apply_ui_language("en")
        assert dialog.generate()
        _wait_dialog(dialog, timeout=60)
        en_err = dialog.error.text()
        assert "Non-axisymmetric CAD geometry detected" in en_err
        assert "Hybrid Hex-Core" in en_err
    finally:
        _cleanup(dialog)


def test_prep_workspace_1440x900_sliced_hybrid_bracket_and_housing_dark_and_light_ko(tmp_path, monkeypatch):
    # Verify unset env vars keep default Light + English for all 8 PROFILES compatibility
    monkeypatch.delenv("CAELAB_THEME_MODE", raising=False)
    monkeypatch.delenv("CAELAB_UI_LANGUAGE", raising=False)
    default_win = MainWindow(enable_viewport=False)
    try:
        assert default_win.theme_mode == "light"
        assert default_win.ui_language == "en"
        assert default_win.viewport_inspection_bar.section_label.text() == "Section cut"
        assert default_win.viewport_inspection_bar.color_label.text() == "Color by"
    finally:
        _cleanup(default_win)

    bracket_step, _ = _write_fixture("bracket", tmp_path)
    housing_step, _ = _write_fixture("housing", tmp_path)
    bracket_hybrid = generate_hybrid_hex_core(
        bracket_step, tmp_path / "ws_bracket", length_unit="mm", core_size=2.0, boundary_size=1.5
    )
    housing_hybrid = generate_hybrid_hex_core(
        housing_step, tmp_path / "ws_housing", length_unit="mm", core_size=1.5, boundary_size=1.5
    )

    session = _create_session("mm")
    window = MainWindow(session, enable_viewport=True, theme_mode="dark", ui_language="ko")
    window._allow_close = True
    try:
        window.setWindowState(Qt.WindowState.WindowNoState)
        window.resize(1440, 900)
        window.show()
        QApplication.processEvents()
        assert window.size().width() == 1440 and window.size().height() == 900

        bar = window.viewport_inspection_bar
        assert bar.isVisible()
        assert bar.section_label.text() == "단면 절단"
        assert bar.axis_buttons["off"].text() == "해제"
        assert bar.flip_button.text() == "반전"
        assert bar.color_label.text() == "색상 기준"
        assert bar.color_buttons["part"].text() == "파트"
        assert bar.color_buttons["element_family"].text() == "요소 계열"

        forbidden_jargon = ("vtk", "gmsh 7", "traceback", "source_kind", "native_scope", "caelab:volume:")

        for theme in ("dark", "light"):
            window.apply_theme_mode(theme)
            for label_title, cand, axis in (
                ("브래킷 하이브리드 육면체 코어", bracket_hybrid, "x"),
                ("하우징 하이브리드 육면체 코어", housing_hybrid, "y"),
            ):
                window.preview_candidate_mesh(cand, title=label_title)
                QApplication.processEvents()

                total_cells = len(cand.native.elements)
                assert window.viewport_frame.title.text() == label_title
                assert "미리보기 전용" in window.viewport_frame.context.text()
                assert f"요소 {total_cells:,}개" in window._counts.text()

                # Activate Element Family coloring + section cut via actual toolbar buttons
                if not bar.color_buttons["element_family"].isChecked():
                    QTest.mouseClick(bar.color_buttons["element_family"], Qt.MouseButton.LeftButton)
                QTest.mouseClick(bar.axis_buttons[axis], Qt.MouseButton.LeftButton)
                bar.slice_slider.setValue(50)
                QApplication.processEvents()

                sliced_no_flip = window.viewport.visible_cell_indices()
                assert 0 < len(sliced_no_flip) < total_cells

                QTest.mouseClick(bar.flip_button, Qt.MouseButton.LeftButton)
                QApplication.processEvents()
                sliced_flipped = window.viewport.visible_cell_indices()
                assert 0 < len(sliced_flipped) < total_cells
                assert sliced_flipped != sliced_no_flip

                # Reset flip back to False and verify legend swatches
                QTest.mouseClick(bar.flip_button, Qt.MouseButton.LeftButton)
                QApplication.processEvents()
                assert bar.legend_container.isVisible()
                active_map = window.viewport.element_family_colors()
                assert set(active_map.keys()) == {"Hex8", "Pyramid5", "Tet4"}
                chip_families = [fam for fam, _chip, _sw, _lbl in bar._chips]
                assert chip_families == ["Hex8", "Pyramid5", "Tet4"]
                for fam, chip, _sw, lbl in bar._chips:
                    assert chip.property("swatchHex") == active_map[fam]
                    assert chip.isVisible()
                    # Unclipped label text check
                    text_w = lbl.fontMetrics().horizontalAdvance(lbl.text())
                    assert lbl.width() >= text_w - 2, (theme, fam, lbl.text(), lbl.width(), text_w)
                    # Fits completely inside the inspection bar width
                    top_left = chip.mapTo(bar, chip.rect().topLeft())
                    bottom_right = chip.mapTo(bar, chip.rect().bottomRight())
                    assert top_left.x() >= 0 and bottom_right.x() <= bar.width(), (
                        theme,
                        fam,
                        bottom_right.x(),
                        bar.width(),
                    )

                # Non-overlapping dock & central viewport geometry at 1440x900
                model_geo = window.model_dock.geometry()
                prop_geo = window.properties_dock.geometry()
                vp_geo = window.viewport_frame.geometry()
                assert not model_geo.intersects(prop_geo)
                assert not prop_geo.intersects(vp_geo)
                assert vp_geo.width() >= 760

                # Check all visible QLabels in the window have zero parser/internal jargon
                for qlabel in window.findChildren(QLabel):
                    if qlabel.isVisible() and qlabel.text():
                        lowered = qlabel.text().lower()
                        for bad in forbidden_jargon:
                            assert bad not in lowered, (qlabel.objectName(), qlabel.text())

                # Grab offscreen window snapshot to confirm clean Qt + VTK composition
                pixmap = window.grab()
                assert not pixmap.isNull()
                assert pixmap.width() == 1440 and pixmap.height() == 900
    finally:
        _cleanup(window)
