"""Offscreen Qt review with synthetic evidence; no native SDK or VTK renderer."""
import hashlib
import json
import math
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu

from caelab_prep.adapters.gmsh_geometry import plan_cylinder_material_probe
from caelab_prep.application import PrepSession
from caelab_prep.application.geometry_inspection import read_geometry_inspection
from caelab_prep.ui.geometry_features import GeometryFeaturesDialog, geometry_projection
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_external_mesh_ui import pump, wait_task
from test_geometry_features import hole
from test_cylindrical_blends import blend_evidence, persist
from test_conical_blends import cone_evidence


pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.fixture
def inspection(hole, tmp_path):
    """A synthetic geometry graph for UI state checks, not an actual CAD solid."""
    data = hole
    surfaces, curves = data["surfaces"], data["curves"]
    cylinder = surfaces[0]
    volume = cylinder["orientation_by_volume"][0]["volume_uuid"]
    for index, surface in enumerate(surfaces, 1):
        surface.update(backend_tag=index, normal_basis="gmsh_face_oriented_no_volume_sign", sampling_status="unverified")
        surface["bbox"] = [0., 0., 0., 12., 8., 3.]
        surface["center"] = [6., 4., 1.5]
        surface["samples"] = []
        for loop_index, loop in enumerate(surface["curve_loops"], 1): loop["backend_tag"] = 10 * index + loop_index
    cylinder["samples"] = [{"uv": [math.pi, 2.5], "xyz": [5., 4., 1.5], "face_normal": [1., 0., 0.], "trim_count": 1}]
    for curve in curves:
        curve.setdefault("endpoints", [{"backend_tag": 500, "xyz": [7., 4., 0.]},
                                       {"backend_tag": 501, "xyz": [7., 4., 3.]}])
        curve["bbox"] = [0., 0., 0., 12., 8., 3.]
        curve["adjacent_surface_uuids"] = [surface["uuid"] for surface in surfaces
            if any(curve["backend_tag"] in map(abs, loop["curve_tags"]) for loop in surface["curve_loops"])]
    data["volumes"] = [{"uuid": volume, "backend_tag": 1, "bbox": [0., 0., 0., 12., 8., 3.],
                        "surface_uuids": [surface["uuid"] for surface in surfaces]}]
    source, xao, metadata = (tmp_path / name for name in ("synthetic.step", "geometry.xao", "metadata.json"))
    source.write_bytes(b"Synthetic UI source, no actual CAD")
    xao.write_bytes(b"Synthetic UI XAO, no native inspection")
    data.update(schema_version=1, source_kind="cad_geometry_inspection", backend={"name": "gmsh", "version": "synthetic"},
                source={"path": str(source), "captured_path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                assets={"xao": str(xao), "metadata": str(metadata)}, sdk_error_count=0, geometry_tolerance=1e-8)
    plan = plan_cylinder_material_probe(cylinder, surfaces, data["volumes"], curves, 1e-8, "mm")
    assert plan["status"] == "ready"
    plan.update(status="observed", radial_material_side="outward_side_is_material")
    plan["plus"]["inside_count"], plan["minus"]["inside_count"] = 1, 0
    data["cylinder_material_side_probes"] = [plan]
    metadata.write_text(json.dumps(data), encoding="utf-8")
    return read_geometry_inspection(metadata)


@pytest.mark.parametrize("presentation", PROFILES)
def test_all_presentations_share_the_read_only_action_and_review_without_a_document(inspection, monkeypatch, presentation):
    session = PrepSession(); before = session.describe()
    window = MainWindow(session, presentation=presentation, enable_viewport=False)
    window._allow_close = True
    try:
        action = window.mesh_workflow.features_action
        assert action.isEnabled()
        menu = next(menu for menu in window.menuBar().findChildren(QMenu)
                    if menu.title() == "&Mesh")
        assert action in menu.actions()
        dialog = GeometryFeaturesDialog(window, enable_viewport=False)
        assert dialog.present_inspection(inspection)
        assert dialog.table.rowCount() == 1 and dialog.table.item(0, 0).text() == "Through hole"
        assert dialog.table.item(0, 1).text() == "1" and dialog.table.item(0, 2).text() == "3"
        assert session.describe() == before
        dialog.reject()
        seen = []
        monkeypatch.setattr("caelab_prep.ui.geometry_features.GeometryFeaturesDialog",
                            lambda parent, **options: type("Review", (), {"exec": lambda self: seen.append((parent, options))})())
        action.trigger()
        assert seen == [(window, {"enable_viewport": False})] and session.describe() == before
    finally:
        window.close(); pump()


def test_projection_samples_two_rings_and_axis_with_only_private_preview_selection(inspection):
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        assert dialog.present_inspection(inspection)
        projection = dialog.projection
        assert all(cell["type"] == "line" for cell in projection["cells"])
        face = dialog.report["features"][0]["surface_uuid"]
        assert sum(owner == face for owner in dialog._primitive_owners.values()) == 130  # seam + 128 ring segments + axis
        assert projection["document_id"] == dialog.preview_id
        assert all(cell["resource_id"] == "geometry-preview:" + dialog.preview_id for cell in projection["cells"])
        points = dict(zip(projection["node_ids"], projection["points"]))
        marker_nodes = {node for cell in projection["cells"] if dialog._primitive_owners[cell["id"]] == face for node in cell["nodes"]}
        assert {round(math.hypot(points[node][0] - 6., points[node][1] - 4.), 12) for node in marker_nodes} == {0., 1.}
        assert {points[node][2] for node in marker_nodes} == {0., 3.}
        foreign = {**dialog.report, "geometry_revision": 99}
        with pytest.raises(ValueError): geometry_projection(inspection, foreign, "foreign-preview")
        dialog.table.clearSelection()
        owned_id = next(identifier for identifier, owner in dialog._primitive_owners.items() if owner == face)
        dialog.pick_entity({"document_id": dialog.preview_id, "id": owned_id})
        assert dialog.table.selectedItems()
        previous = dialog.preview_id
        dialog.source.setText("another.step")
        assert dialog.report is None and dialog.projection == {}
        dialog.pick_entity({"document_id": previous, "id": 1})
        assert dialog.table.rowCount() == 0
    finally:
        dialog.reject()


def test_invalid_tolerance_hides_old_markers_and_recovers_without_new_inspection(inspection):
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        assert dialog.present_inspection(inspection)
        previous = dialog.preview_id
        dialog.tolerance.setText("invalid")
        assert not dialog.reclassify() and dialog.report is None and dialog.projection == {}
        assert dialog.view_frame.context.text() == "No current review"
        assert dialog.inspection is inspection
        dialog.tolerance.setText("0.000001")
        assert dialog.reclassify() and dialog.preview_id != previous
        assert dialog.table.rowCount() == 1
        old = dialog.table.selectedItems()
        dialog.pick_entity({"document_id": previous, "id": 1})
        assert dialog.table.selectedItems() == old
    finally:
        dialog.reject()


def test_asset_change_invalidates_feature_values_and_markers(inspection):
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        assert dialog.present_inspection(inspection)
        Path(inspection.assets[0].path).write_bytes(b"changed")
        assert not dialog.reclassify() and dialog.table.rowCount() == 0 and dialog.projection == {}
        assert dialog.error.text()
    finally:
        dialog.reject()


def test_escape_restores_the_last_reviewed_tolerance_and_matching_markers(inspection):
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        dialog.show(); pump(); assert dialog.present_inspection(inspection)
        dialog.tolerance.setFocus(); pump(); assert dialog.tolerance.hasFocus()
        dialog.tolerance.selectAll()
        QTest.keyClicks(dialog.tolerance, "0.01")
        assert dialog.report is None and not dialog.projection
        QTest.keyClick(dialog.tolerance, Qt.Key.Key_Tab); pump()
        assert dialog.report and dialog.report["length_tolerance"] == .01, (dialog.error.text(), dialog.summary.text())
        dialog.tolerance.setFocus(); pump(); dialog.tolerance.selectAll()
        QTest.keyClicks(dialog.tolerance, "invalid")
        assert dialog.report is None
        QTest.keyClick(dialog.tolerance, Qt.Key.Key_Escape); pump()
        assert dialog.isVisible()
        assert dialog.tolerance.numeric_value() == .01 == dialog.report["length_tolerance"]
        assert dialog.projection and dialog.table.rowCount() == 1
    finally:
        dialog.reject()


def test_cancel_and_changed_input_cannot_present_a_late_worker_result(inspection, tmp_path):
    class Backend:
        def inspect_geometry(self, source, output, **options):
            assert options["probe_cylinder_material_side"] is True
            assert options["probe_cylindrical_blends"] is True
            assert options["probe_conical_blends"] is True
            assert options["expected_coordinate_length_unit"] == "mm"
            options["cancel_event"].wait(3)
            return inspection.to_dict()  # deliberately late successful response

    dialog = GeometryFeaturesDialog(backend=Backend(), enable_viewport=False)
    try:
        dialog.source.setText("first.step"); dialog.output.setText(str(tmp_path))
        QTest.mouseClick(dialog.inspect_button, Qt.MouseButton.LeftButton)
        assert dialog._task is not None
        assert not dialog.source.isEnabled() and dialog.cancel_button.isEnabled()
        dialog.source.setText("second.step")
        wait_task(dialog)
        assert dialog.inspection is None and dialog.report is None and dialog.source.text() == "second.step"
        assert "cancelled" in dialog.summary.text().lower()
    finally:
        dialog.reject()


def test_open_saved_inspection_reuses_assets_and_requires_no_backend(inspection, monkeypatch):
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        metadata = next(asset.path for asset in inspection.assets if asset.kind == "metadata")
        monkeypatch.setattr("caelab_prep.adapters.gmsh_backend.GmshBackend.inspect_geometry",
                            lambda *args, **kwargs: pytest.fail("Opening saved evidence must not query the SDK"))
        assert dialog.open_inspection(metadata)
        wait_task(dialog)
        assert dialog.report and dialog.table.rowCount() == 1
    finally:
        dialog.reject()


def test_real_unshown_vtk_pipeline_replaces_the_cleared_preview(inspection):
    pytest.importorskip("vtk")
    from test_viewport_visibility import viewport
    view = viewport({"points": [], "node_ids": [], "cells": []})
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    dialog.viewport = view
    try:
        assert dialog.present_inspection(inspection)
        assert not view._initialized and view._widget.GetRenderWindow().GetNeverRendered() == 1
        assert view._grid.GetNumberOfCells() == len(dialog.projection["cells"])
        assert view._visible_grid.GetNumberOfCells() == len(dialog.projection["cells"])
    finally:
        dialog.reject()


@pytest.mark.parametrize("cusp", [False, True])
def test_blend_review_uses_partial_arcs_and_signed_tangent_evidence(tmp_path, cusp):
    data, metadata = blend_evidence(tmp_path, cusp=cusp)
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        assert dialog.present_inspection(persist(data, metadata))
        assert dialog.table.rowCount() == (0 if cusp else 1)
        if cusp:
            assert "material normals not g1" in dialog.summary.toolTip()
            assert not any(dialog._primitive_owners.values())
        else:
            assert dialog.table.item(0, 0).text() == "Cylindrical blend"
            assert dialog.table.item(0, 1).text() == "1" and dialog.table.item(0, 2).text() == "3"
            assert "Material-oriented tangent joins" in dialog.details.text()
            face = dialog.report["features"][0]["surface_uuid"]
            owned = [cell for cell in dialog.projection["cells"] if dialog._primitive_owners[cell["id"]] == face]
            assert len(owned) == 35  # Two generatrices, two 16-segment arcs, axis; no full rings.
            points = dict(zip(dialog.projection["node_ids"], dialog.projection["points"]))
            for node in {node for cell in owned for node in cell["nodes"]}:
                x, y, z = points[node]
                assert -1e-12 <= x <= 1. + 1e-12 and -1e-12 <= y <= 1. + 1e-12
                assert z in (0., 3.)
    finally:
        dialog.reject()


def test_blend_radius_filter_reclassifies_saved_evidence_and_escape_restores_last_review(tmp_path, monkeypatch):
    data, metadata = blend_evidence(tmp_path)
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        monkeypatch.setattr("caelab_prep.adapters.gmsh_backend.GmshBackend.inspect_geometry",
                            lambda *args, **kwargs: pytest.fail("Filter changes must not query SDK"))
        assert dialog.present_inspection(persist(data, metadata))
        dialog.limit_blend_radius.setChecked(True)
        dialog.blend_radius.setText("0.9")
        assert dialog.reclassify() and dialog.table.rowCount() == 0
        dialog.show(); pump()
        dialog.blend_radius.setFocus(); pump(); assert dialog.blend_radius.hasFocus()
        dialog.blend_radius.selectAll(); QTest.keyClicks(dialog.blend_radius, "invalid")
        assert dialog.report is None and not dialog.projection
        QTest.keyClick(dialog.blend_radius, Qt.Key.Key_Escape); pump()
        assert dialog.blend_radius.numeric_value() == .9 and dialog.table.rowCount() == 0
        assert dialog.report["blend_review"]["radius_threshold"] == .9
        dialog.limit_blend_radius.setChecked(False)
        assert dialog.table.rowCount() == 1
    finally:
        dialog.reject()


def test_saved_unknown_unit_evidence_cannot_be_displayed_with_mm_labels(inspection):
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        assert dialog.present_inspection(inspection) and dialog.table.rowCount() == 1
        data = inspection.to_dict()
        data["length_unit"] = "unknown"
        data.pop("cylinder_material_side_probes")
        metadata = Path(data["assets"]["metadata"])
        metadata.write_text(json.dumps(data), encoding="utf-8")
        non_mm = read_geometry_inspection(metadata)
        assert not dialog.present_inspection(non_mm)
        assert dialog.inspection is None and dialog.report is None and not dialog.projection
        assert dialog.table.rowCount() == 0 and "not rescaled" in dialog.error.text()
    finally:
        dialog.reject()


@pytest.mark.parametrize("cusp", [False, True])
@pytest.mark.parametrize("axis_sign", [1, -1])
def test_conical_review_preserves_section_radii_and_signed_material_joins(tmp_path, cusp, axis_sign):
    data, metadata = cone_evidence(tmp_path, cusp=cusp, axis_sign=axis_sign)
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        assert dialog.present_inspection(persist(data, metadata))
        assert dialog.table.rowCount() == (0 if cusp else 1)
        assert not hasattr(dialog, "washer_button")
        if cusp:
            assert "material normals not g1" in dialog.summary.toolTip()
            assert not any(dialog._primitive_owners.values())
            return
        assert dialog.table.item(0, 0).text() == "Conical blend"
        assert dialog.table.item(0, 1).text() == "7.5" and dialog.table.item(0, 2).text() == "4"
        assert "Max normal radius: 7.5 mm" in dialog.details.text()
        assert "Section radii: 3, 6 mm" in dialog.details.text()
        face = dialog.report["features"][0]["surface_uuid"]
        owned = [cell for cell in dialog.projection["cells"] if dialog._primitive_owners[cell["id"]] == face]
        assert len(owned) == 35  # Two generatrices, two partial arcs and axis.
        points = dict(zip(dialog.projection["node_ids"], dialog.projection["points"]))
        marker_points = {points[node] for cell in owned for node in cell["nodes"]}
        for x, y, z in marker_points:
            assert z in (4., 8.) and min(x, y) >= -1e-12
            assert math.hypot(x, y) == pytest.approx(0. if x == y == 0. else .75 * z)
        identifier = owned[0]["id"]
        dialog.table.clearSelection()
        dialog.pick_entity({"document_id": dialog.preview_id, "id": identifier})
        assert dialog.table.selectedItems() and not hasattr(dialog, "washer_button")
    finally:
        dialog.reject()


def test_saved_cone_threshold_filter_uses_normal_radius_without_querying_sdk(tmp_path, monkeypatch):
    data, metadata = cone_evidence(tmp_path)
    dialog = GeometryFeaturesDialog(enable_viewport=False)
    try:
        monkeypatch.setattr("caelab_prep.adapters.gmsh_backend.GmshBackend.inspect_geometry",
                            lambda *args, **kwargs: pytest.fail("Saved cone filtering must not query the SDK"))
        assert dialog.present_inspection(persist(data, metadata))
        dialog.limit_blend_radius.setChecked(True)
        dialog.blend_radius.setText("6")  # Maximum section radius is smaller than the normal radius.
        assert dialog.reclassify() and dialog.table.rowCount() == 0
        assert "radius above threshold" in dialog.summary.toolTip()
        dialog.blend_radius.setText("8")
        assert dialog.reclassify() and dialog.table.rowCount() == 1
        assert dialog.report["conical_review"]["radius_threshold"] == 8
        dialog.blend_radius.setText("invalid")
        assert not dialog.reclassify() and not dialog.projection
        dialog.blend_radius.revert()
        assert dialog.report["conical_review"]["radius_threshold"] == 8
        assert dialog.table.rowCount() == 1
    finally:
        dialog.reject()
