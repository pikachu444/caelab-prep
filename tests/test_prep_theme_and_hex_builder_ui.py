"""Tests for structured multi-patch recipe builder, shared-vertex fork UI, dark/light theme, and Korean UI."""

from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from caelab_prep.application import PrepSession
from caelab_prep.application.structured_geometry import validate_recipe
from caelab_prep.application.structured_mesh import generate_structured_mesh, read_recipe_input
from caelab_prep.ui.design import DARK_TOKENS, STYLESHEET, TOKENS, build_stylesheet, icon
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog, StructuredRecipeBuilderDialog
from test_mesh_workflow_ui import choose, pump_until
from test_structured_adoption import _native

pytestmark = pytest.mark.usefixtures("qt_widgets")


def _cleanup_widget(widget) -> None:
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def _create_model(unit: str = "mm", dimension: int = 3):
    session = PrepSession()
    session.new_document("Structured assembly", {"mass": "Mg", "length": unit, "time": "s"})
    material = session.create_material("Structural steel", 7.85e-9, 210000.0, 0.3)["card_id"]
    section = (
        session.create_shell_property("Shell plate", 2.0)["card_id"]
        if dimension == 2
        else session.create_solid_property("Solid brick")["card_id"]
    )
    return session, material, section


def test_structured_recipe_builder_all_presets_quad_and_hex_and_adopt_hollow_frame(tmp_path, monkeypatch):
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable")

    builder = StructuredRecipeBuilderDialog()
    try:
        presets = ["single", "two_patch", "l_bracket_3", "t_gusset_4", "hollow_frame_4"]
        assert [builder.preset.itemData(i) for i in range(builder.preset.count())] == presets

        for preset_key in presets:
            choose(builder.preset, preset_key)
            for mode in ("quad", "hex"):
                choose(builder.mode, mode)
                choose(builder.unit, "mm")
                spec = builder.build_recipe()
                admission = validate_recipe(spec)
                summary_text = builder.preview_summary.text()
                assert str(admission["expected_elements"]) in summary_text.replace(",", "")
                assert str(admission["expected_active_nodes"]) in summary_text.replace(",", "")
                assert ("Analytic volume" if mode == "hex" else "Analytic area") in summary_text
                assert not builder.error.text()
                assert builder.save_button.isEnabled()

                recipe_path = tmp_path / f"{preset_key}_{mode}.json"
                saved = builder.save_recipe(recipe_path)
                assert Path(saved) == recipe_path.resolve()
                candidate = generate_structured_mesh(
                    spec,
                    tmp_path / f"assets_{preset_key}_{mode}",
                    recipe_path=saved,
                )
                assert candidate.quality.passed
                native = candidate.to_native_mesh()
                assert len(native.elements) == admission["expected_elements"]
                assert len(native.nodes) == admission["expected_active_nodes"]
                assert len(native.parts) == len(admission["singles"])
    finally:
        _cleanup_widget(builder)

    # Full end-to-end GUI adoption of hollow_frame_4 in hex mode via MainWindow structured_mesh_action
    session, material, section = _create_model("mm", dimension=3)
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True
    hollow_recipe_file = tmp_path / "hollow_frame_hex.json"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(hollow_recipe_file), "Recipe (*.json)"),
    )
    failures = []

    def drive_structured_dialog():
        dialog = window.mesh_workflow.dialog
        try:
            assert dialog is not None
            assert dialog.source_kind.currentData() == "structured_recipe"
            assert dialog.new_recipe_button.isVisible()

            def configure_builder():
                sub = next(
                    w for w in dialog.findChildren(StructuredRecipeBuilderDialog) if w.isVisible()
                )
                choose(sub.preset, "hollow_frame_4")
                choose(sub.mode, "hex")
                choose(sub.unit, "mm")
                assert sub.nx.numeric_value() == 4
                assert sub.ny.numeric_value() == 3
                assert sub.layers.numeric_value() == 4
                assert sub.sweep_dz.numeric_value() == pytest.approx(12.0)
                QTest.mouseClick(sub.save_button, Qt.MouseButton.LeftButton)

            QTimer.singleShot(0, configure_builder)
            QTest.mouseClick(dialog.new_recipe_button, Qt.MouseButton.LeftButton)

            assert Path(dialog.source.text()) == hollow_recipe_file.resolve()
            assert len(dialog.division_edits) == 4
            assert dialog.layers.numeric_value() == 4
            assert len(dialog._geometry_vertex_ids) == 8

            dialog.output.setText(str(tmp_path / "adopt_assets"))
            QTest.mouseClick(dialog.generate_button, Qt.MouseButton.LeftButton)
            pump_until(dialog)
            assert dialog.candidate is not None, dialog.error.text()
            assert dialog.candidate.quality.passed
            assert len(dialog.candidate.parts) == 4

            choose(dialog.material, material)
            choose(dialog.section, section)
            QTest.mouseClick(dialog.adopt_button, Qt.MouseButton.LeftButton)
            pump_until(dialog)
            assert dialog.result is not None, dialog.error.text()
        except Exception as exc:
            failures.append(exc)
            dialog.reject()

    try:
        assert window.mesh_workflow.structured_mesh_action in window.command_menus["Mesh"].actions()
        QTimer.singleShot(0, drive_structured_dialog)
        window.mesh_workflow.structured_mesh_action.trigger()
        assert not failures, failures

        summary = session.describe()
        assert summary["element_count"] == 4 * 4 * 3 * 4  # 192 Hex8 elements
        assert summary["node_count"] == 64 * 5  # 320 active nodes across 5 planes

        starter = tmp_path / "hollow_frame_0000.rad"
        session.export_solver_inputs(starter, end_time=0.01, output_interval=0.001)
        nodes, elements, parts, _ = _native(starter.read_bytes())
        assert len(parts) == 4
        assert len(elements) == 192
        assert len(nodes) == 320
    finally:
        _cleanup_widget(window)


def test_multipatch_shared_vertex_fork_in_mesh_candidate_dialog(tmp_path, monkeypatch):
    holdout_path = Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json"
    spec = next(
        case["input"]
        for case in json.loads(holdout_path.read_text(encoding="utf-8"))
        if case["id"] == "H-D2"
    )
    source = tmp_path / "original_hd2.json"
    source.write_text(json.dumps(spec), encoding="utf-8")
    original_bytes = source.read_bytes()

    session, _, _ = _create_model(spec["unit"], dimension=3)
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    try:
        dialog.show()
        choose(dialog.source_kind, "structured_recipe")
        dialog.source.setText(str(source))
        dialog.output.setText(str(tmp_path / "fork_assets"))
        assert dialog.load_divisions()

        assert dialog.geometry_toggle.isEnabled()
        assert dialog._geometry_vertex_ids == sorted(spec["vertices"])
        assert len(dialog.geometry_edits) == len(spec["vertices"]) + 1  # vertices + sweep vector

        dialog.geometry_toggle.setChecked(True)
        assert dialog.geometry_panel.isVisible()

        # Invalid out-of-plane move on a single vertex must block generation and never open Save dialog
        idx_b = dialog._geometry_vertex_ids.index("b")
        b_editor = dialog.geometry_edits[idx_b]
        b_editor.editors[2].selectAll()
        QTest.keyClicks(b_editor.editors[2], "999")
        assert dialog._geometry_dirty
        assert not dialog.generate_button.isEnabled()
        picker_calls = []
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (picker_calls.append(True) or ("", "")),
        )
        assert not dialog.fork_geometry()
        assert picker_calls == []
        assert dialog.error.text()

        # Revert and apply valid in-plane shared-vertex move (move b slightly toward a) + 1.05x sweep vector
        b_editor.revert()
        assert not dialog._geometry_dirty and dialog.generate_button.isEnabled()

        a_xyz = spec["vertices"]["a"]
        b_xyz = spec["vertices"]["b"]
        moved_b = [end + 0.05 * (start - end) for start, end in zip(a_xyz, b_xyz)]
        for comp_edit, coord in zip(b_editor.editors, moved_b):
            comp_edit.selectAll()
            QTest.keyClicks(comp_edit, f"{coord:.12g}")

        vec_editor = dialog.geometry_edits[-1]
        scaled_vec = [1.05 * v for v in spec["vector"]]
        for comp_edit, coord in zip(vec_editor.editors, scaled_vec):
            comp_edit.selectAll()
            QTest.keyClicks(comp_edit, f"{coord:.12g}")

        assert dialog._geometry_dirty
        assert not dialog.generate_button.isEnabled()

        forked_path = tmp_path / "forked_hd2.json"
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            lambda *args, **kwargs: (str(forked_path), "Recipe (*.json)"),
        )
        assert dialog.fork_geometry(), dialog.error.text()
        assert Path(dialog.source.text()) == forked_path.resolve()
        assert not dialog._geometry_dirty
        assert dialog.generate_button.isEnabled()
        assert source.read_bytes() == original_bytes

        forked_spec, forked_digest = read_recipe_input(forked_path)
        assert forked_digest.sha256 != sha256(original_bytes).hexdigest()
        assert forked_spec["vertices"]["b"] == pytest.approx(moved_b)
        assert forked_spec["vector"] == pytest.approx(scaled_vec)

        if importlib.util.find_spec("gmsh") is not None:
            assert dialog.generate()
            pump_until(dialog)
            assert dialog.candidate is not None, dialog.error.text()
            assert dialog.candidate.quality.passed
    finally:
        _cleanup_widget(dialog)


def test_dark_and_light_theme_switching_and_viewport_colors():
    assert TOKENS["surface"] == "#ffffff"
    assert TOKENS["font_family"] == "'Segoe UI'"
    assert DARK_TOKENS["workspace"] == "#141920"
    assert DARK_TOKENS["surface"] == "#1d242e"
    assert DARK_TOKENS["accent"] == "#4ea1f3"
    assert "Malgun Gothic" in DARK_TOKENS["font_family"]

    light_qss = build_stylesheet("light")
    dark_qss = build_stylesheet("dark")
    assert light_qss == STYLESHEET
    assert "#141920" in dark_qss and "#1d242e" in dark_qss
    assert "QPushButton#primaryAction { color: #ffffff; background: #4ea1f3;" in dark_qss
    assert icon("mesh", "dark").pixmap(24, 24).toImage() != icon("mesh", "light").pixmap(24, 24).toImage()

    can_use_vtk = importlib.util.find_spec("vtk") is not None and not (
        sys.platform == "linux" and not os.environ.get("DISPLAY")
    )
    session, _, _ = _create_model("mm", dimension=3)
    window = MainWindow(session, enable_viewport=can_use_vtk)
    window._allow_close = True
    try:
        assert window.theme_mode == "light"
        assert not window.dark_theme_action.isChecked()

        window.apply_theme_mode("dark")
        assert window.theme_mode == "dark"
        assert window.dark_theme_action.isChecked()
        assert "#141920" in window.styleSheet()

        if window.viewport is not None:
            assert window.viewport._renderer.GetBackground() == pytest.approx((0.09, 0.12, 0.16))
            assert window.viewport._renderer.GetBackground2() == pytest.approx((0.16, 0.21, 0.27))
            assert window.viewport._actor.GetProperty().GetEdgeColor() == pytest.approx((0.76, 0.84, 0.93))
            assert (
                window.viewport._axes.GetXAxisCaptionActor2D().GetCaptionTextProperty().GetColor()
                == pytest.approx((0.86, 0.90, 0.95))
            )
            # Verify VTK coincident topology polygon offset on element highlight mapper (prevents Z-fighting)
            proj = {
                "document_id": "doc1",
                "document_epoch": "ep1",
                "revision": 0,
                "projection_revision": 0,
                "resource_revisions": {"res1": 0},
                "points": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
                "node_ids": [1, 2, 3, 4],
                "node_resources": {1: ["res1"], 2: ["res1"], 3: ["res1"], 4: ["res1"]},
                "cells": [{"id": 10, "type": "quad", "nodes": [1, 2, 3, 4], "part_id": 1, "resource_id": "res1"}],
            }
            window.viewport.set_mesh(proj, reset_camera=False)
            window.viewport.set_selection({
                "document_id": "doc1",
                "document_epoch": "ep1",
                "revision": 0,
                "projection_revision": 0,
                "kind": "element",
                "ids": [10],
                "refs": [{"resource_id": "res1", "entity_kind": "element", "local_id": 10}],
            })
            hl_mapper = window.viewport._highlight.GetMapper()
            assert hl_mapper is not None
            assert hl_mapper.GetResolveCoincidentTopology() > 0
            if hasattr(hl_mapper, "GetRelativeCoincidentTopologyPolygonOffsetParameters"):
                vtk = window.viewport.vtk
                factor = vtk.reference(0.0)
                units = vtk.reference(0.0)
                hl_mapper.GetRelativeCoincidentTopologyPolygonOffsetParameters(factor, units)
                assert (float(factor), float(units)) == pytest.approx((-1.0, -1.0))

            # Verify dark theme _graphics_error styling
            window.viewport._graphics_error(None, None)
            assert "#3a1e20" in window.viewport._hint.styleSheet()
            assert "#f47067" in window.viewport._hint.styleSheet()

        # Toggle back to light via the View menu action
        window.dark_theme_action.trigger()
        assert window.theme_mode == "light"
        assert not window.dark_theme_action.isChecked()
        assert "#dbe1e7" in window.styleSheet()
        if window.viewport is not None:
            assert window.viewport._renderer.GetBackground() == pytest.approx((0.84, 0.87, 0.90))
            assert window.viewport._renderer.GetBackground2() == pytest.approx((0.97, 0.98, 0.985))
            assert window.viewport._actor.GetProperty().GetEdgeColor() == pytest.approx((0.24, 0.32, 0.4))
    finally:
        if window.viewport is not None:
            window.viewport.shutdown()
        _cleanup_widget(window)


def test_bare_defaults_and_env_var_korean_dark_switching(monkeypatch):
    monkeypatch.delenv("CAELAB_THEME_MODE", raising=False)
    monkeypatch.delenv("CAELAB_UI_LANGUAGE", raising=False)

    bare = MainWindow(enable_viewport=False)
    bare._allow_close = True
    try:
        assert bare.theme_mode == "light"
        assert bare.ui_language == "en"
        assert not bare.dark_theme_action.isChecked()
        assert not bare.korean_ui_action.isChecked()
        en_menus = [a.text() for a in bare.menuBar().actions()]
        assert en_menus == ["&File", "&Edit", "&Model", "&Mesh", "&Conditions", "&View", "&Automation"]
        assert [bare.pick_mode.itemText(0), bare.pick_mode.itemText(1)] == ["Elements", "Nodes"]
        assert bare.model_filter.placeholderText() == "Filter model objects"
    finally:
        _cleanup_widget(bare)

    # Env-var auto-initialization when launched from caelab-workbench ProjectWindow
    monkeypatch.setenv("CAELAB_THEME_MODE", "dark")
    monkeypatch.setenv("CAELAB_UI_LANGUAGE", "ko")
    session, _, _ = _create_model("mm", dimension=3)
    ko_win = MainWindow(session, enable_viewport=False)
    ko_win._allow_close = True
    try:
        assert ko_win.theme_mode == "dark"
        assert ko_win.ui_language == "ko"
        assert ko_win.dark_theme_action.isChecked()
        assert ko_win.korean_ui_action.isChecked()

        ko_menus = [a.text() for a in ko_win.menuBar().actions()]
        assert ko_menus == ["&파일", "&편집", "&모델", "&메시", "&조건", "&보기", "&자동화"]
        assert (
            ko_win.model_dock.windowTitle(),
            ko_win.properties_dock.windowTitle(),
            ko_win.messages_dock.windowTitle(),
        ) == ("모델 트리", "속성 검사기", "메시지")
        assert ko_win.model_filter.placeholderText() == "모델 객체 검색"
        assert [ko_win.pick_mode.itemText(0), ko_win.pick_mode.itemText(1)] == ["요소", "절점"]
        assert ko_win.pick_mode.objectName() == "pickMode"
        assert [
            ko_win.fit_action.iconText(),
            ko_win.iso_action.iconText(),
            ko_win.edges_action.iconText(),
            ko_win.fit_selected_action.iconText(),
            ko_win.hide_selected_action.iconText(),
            ko_win.isolate_action.iconText(),
            ko_win.show_all_action.iconText(),
        ] == ["맞춤", "등각", "요소선", "선택 맞춤", "숨기기", "격리", "모두 표시"]
        assert ko_win.dark_theme_action.text() == "다크 테마"
        assert ko_win.korean_ui_action.text() == "한국어 UI"

        assert [
            ko_win.model_tree.model().headerData(col, Qt.Orientation.Horizontal)
            for col in range(5)
        ] == ["이름", "유형", "카드", "표시", "색상"]
        tree_groups = [
            ko_win.model_tree.model().item(r, 0).text()
            for r in range(ko_win.model_tree.model().rowCount())
        ]
        assert {"재료", "단면 속성", "기타 카드"} <= set(tree_groups)
        assert {"Materials", "Properties", "Other cards"} <= {node.group for node in ko_win._tree_nodes}
        assert ko_win.property_title.text() == "선택된 객체 없음"

        # Select a material card and verify Korean inspector labels & unit caption
        mat_card = next(c for c in session.list_cards() if c["keyword"].startswith("/MAT/"))
        assert ko_win.select_card(mat_card["id"])
        assert ko_win.property_editor.edit_state.text() == "입력 값"
        shown_labels = [row.label.text() for row in ko_win.property_editor._rows.values()]
        assert {"밀도", "탄성계수", "푸아송 비"} <= set(shown_labels)
        assert ko_win.units_note.text().startswith("단위:")

        # Child dialogs inherit Korean + Dark theme and preserve underlying currentData() keys
        cand_dialog = MeshCandidateDialog(session, ko_win, enable_viewport=False, initial_source_kind="structured_recipe")
        try:
            cand_dialog.show()
            QApplication.processEvents()
            assert cand_dialog.ui_language == "ko"
            assert cand_dialog.theme_mode == "dark"
            assert cand_dialog.mesh_candidate_panel.objectName() == "meshCandidatePanel"
            assert cand_dialog.divisions.minimumHeight() >= 140
            assert cand_dialog.divisions.maximumHeight() >= 168
            assert "분할 수, 스윕 층수 및 공유 절점 형상을 편집할 수 있습니다." in cand_dialog.pick_hint.text()
            for lbl in (cand_dialog._source_kind_label, cand_dialog.source_label, cand_dialog.summary):
                fg = lbl.palette().color(lbl.foregroundRole())
                assert fg.lightness() >= 200, (lbl.text(), fg.name())
            assert cand_dialog.new_recipe_button.text() == "다중 패치 레시피 생성…"
            assert [cand_dialog.divisions.horizontalHeaderItem(i).text() for i in range(3)] == ["패치", "변 1–2", "변 2–3"]
            assert cand_dialog.source_kind.currentData() == "structured_recipe"
        finally:
            _cleanup_widget(cand_dialog)

        builder = StructuredRecipeBuilderDialog(ko_win)
        try:
            assert builder.ui_language == "ko"
            assert builder.theme_mode == "dark"
            assert builder.preset.itemText(4) == "4패치 중공 프레임"
            assert builder.preset.itemData(4) == "hollow_frame_4"
            assert "패치" in builder.preview_summary.text()
        finally:
            _cleanup_widget(builder)

        # Switch back dynamically to English & Light
        ko_win.apply_ui_language("en")
        ko_win.apply_theme_mode("light")
        assert ko_win.ui_language == "en" and ko_win.theme_mode == "light"
        assert [a.text() for a in ko_win.menuBar().actions()] == [
            "&File", "&Edit", "&Model", "&Mesh", "&Conditions", "&View", "&Automation"
        ]
        assert [
            ko_win.model_tree.model().headerData(col, Qt.Orientation.Horizontal)
            for col in range(5)
        ] == ["Name", "Type", "Card", "Visible", "Color"]
        en_tree_groups = [
            ko_win.model_tree.model().item(r, 0).text()
            for r in range(ko_win.model_tree.model().rowCount())
        ]
        assert "Materials" in en_tree_groups and "Properties" in en_tree_groups
        assert (ko_win.model_dock.windowTitle(), ko_win.properties_dock.windowTitle()) == ("MODEL", "FORM")
        assert [ko_win.pick_mode.itemText(0), ko_win.pick_mode.itemText(1)] == ["Elements", "Nodes"]
    finally:
        _cleanup_widget(ko_win)
