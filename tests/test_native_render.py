"""Opt-in Linux/X11 full Qt + VTK rendering and actual mouse-pick evidence.

Run this file in an Xvfb/Mesa job with QT_QPA_PLATFORM=xcb,
CAELAB_TEST_NATIVE_RENDER=1 and an absolute CAELAB_NATIVE_RENDER_ARTIFACT_DIR.
No Render, interactor, picker or session method is stubbed. These checks cover
Prep's eight presentations, not the corresponding commercial applications or
native Windows behavior. A two-quad independent input keeps pick expectations
unambiguous; it is not a model-size/performance benchmark.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

if os.environ.get("CAELAB_TEST_NATIVE_RENDER") != "1":
    pytest.skip("Full native Qt/VTK rendering requires the explicit X11 CI opt-in", allow_module_level=True)

# When explicitly requested, missing GUI dependencies must fail rather than skip.
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import vtk

from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_modeling_workflow import user_model

pytestmark = pytest.mark.usefixtures("qt_widgets")


def _pump():
    for _ in range(3):
        QApplication.processEvents()
    QTest.qWait(30)


def _readback(window):
    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(window)
    capture.SetInputBufferTypeToRGB()
    capture.ReadFrontBufferOff()
    capture.Update()
    image = vtk.vtkImageData()
    image.DeepCopy(capture.GetOutput())
    scalars = image.GetPointData().GetScalars()
    assert scalars is not None and scalars.GetNumberOfComponents() == 3
    return image, memoryview(scalars).tobytes()


def _png(path, image):
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(image)
    writer.Write()
    assert path.is_file() and path.stat().st_size > 0, f"Framebuffer PNG was not written: {path}"


def _screen_pixels(window):
    screenshot = window.screen().grabWindow(int(window.winId()))
    assert not screenshot.isNull(), "Native X11 window capture failed"
    image = screenshot.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return screenshot, bytes(image.constBits())


@pytest.mark.parametrize("profile", sorted(PROFILES))
@pytest.mark.parametrize("size", [(1920, 1080), (960, 640)], ids=["1920x1080", "960x640"])
def test_native_window_render_and_mouse_pick(user_model, profile, size):
    location = os.environ.get("CAELAB_NATIVE_RENDER_ARTIFACT_DIR")
    assert location, "CAELAB_NATIVE_RENDER_ARTIFACT_DIR is required for reviewable evidence"
    output = Path(location).expanduser()
    assert output.is_absolute(), "The native render artifact directory must be absolute"
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance()
    assert app.platformName() == "xcb", f"Expected real X11 Qt, got {app.platformName()!r}"
    screen = app.primaryScreen()
    assert screen is not None
    available = screen.availableGeometry()
    assert available.width() >= size[0] and available.height() >= size[1], (
        f"X11 work area {available.width()}x{available.height()} is smaller than requested {size}")

    stem = f"{profile}-{size[0]}x{size[1]}"
    evidence = {"status": "running", "profile": profile, "requested_size": list(size),
                "qt_platform": app.platformName(), "device_pixel_ratio": screen.devicePixelRatio(),
                "vtk_version": vtk.vtkVersion.GetVTKVersion(),
                "scope": "Prep Qt/VTK Linux window; not commercial-product or Windows validation"}
    evidence_file = output / (stem + ".json")
    evidence_file.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    session = user_model[0]
    before = session.describe()
    raw_cards = tuple((card["id"], session.card_text(card["id"])) for card in session.list_cards())
    window = None
    try:
        window = MainWindow(session, presentation=profile, enable_viewport=True)
        window._allow_close = True
        window.resize(*size)
        window.move(available.topLeft())
        window.show()
        assert QTest.qWaitForWindowExposed(window, 10000), "The real Qt window was never exposed"
        _pump()
        assert (window.width(), window.height()) == size, "The presentation forced the window beyond its requested size"
        assert available.contains(window.frameGeometry()), "The native window extends outside the X11 work area"
        view = window.viewport
        assert view is not None and view.isVisible() and view._initialized
        assert view._visible_grid.GetNumberOfCells() == 2
        assert view._widget.width() >= 100 and view._widget.height() >= 100
        # Use the production view action, then read the actual native framebuffer.
        window.standard_view_actions[1].trigger()  # Top view: both known quads face the camera.
        _pump()
        view.render()
        render_window = view._widget.GetRenderWindow()
        assert render_window.GetNeverRendered() == 0
        assert not view._render_failed, "VTK reported a graphics error"
        evidence["render_backend"] = render_window.GetClassName()
        assert evidence["render_backend"] == "vtkXOpenGLRenderWindow", (
            "This job requires VTK embedded in the X11 window, not a separate offscreen fallback")
        evidence["render_size"] = list(render_window.GetSize())
        visible_image, visible = _readback(render_window)
        _png(output / (stem + "-viewport.png"), visible_image)
        _, visible_screen = _screen_pixels(window)
        # A nonzero-sized image or gradient alone is not evidence of rendered mesh.
        view._actor.SetVisibility(False)
        try:
            view.render()
            _, background = _readback(render_window)
            _, background_screen = _screen_pixels(window)
        finally:
            view._actor.SetVisibility(True)
            view.render()
        assert len(visible) == len(background) > 0
        changed = sum(visible[index:index + 3] != background[index:index + 3]
                      for index in range(0, len(visible), 3))
        evidence["mesh_pixels_changed_against_hidden_actor"] = changed
        assert changed > 100, "The framebuffer does not contain the mesh actor"
        assert len(visible_screen) == len(background_screen) > 0
        screen_changed = sum(visible_screen[index:index + 4] != background_screen[index:index + 4]
                             for index in range(0, len(visible_screen), 4))
        evidence["native_window_pixels_changed_against_hidden_actor"] = screen_changed
        assert screen_changed > 100, "The actual X11 window does not display the mesh actor"

        picks = []
        geometry_resource = next(card["resource_id"] for card in session.list_cards() if card["keyword"] == "/SHELL/902")
        for identifier, center in ((7001, (1., .5, 0.)), (9007, (1., 3.5, 0.))):
            view._renderer.SetWorldPoint(*center, 1.)
            view._renderer.WorldToDisplay()
            x, y, _ = view._renderer.GetDisplayPoint()
            pixels_wide, pixels_high = render_window.GetSize()
            point = QPoint(round(x * view._widget.width() / pixels_wide),
                           round((pixels_high - 1 - y) * view._widget.height() / pixels_high))
            assert view._widget.rect().contains(point), "Expected cell lies outside the real viewport"
            # This must travel through Qt -> QVTK interactor -> real vtkCellPicker
            # -> host approval -> canonical session selection, not a direct call.
            QTest.mouseClick(view._widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
            _pump()
            selection = session.selection()
            assert selection["kind"] == "element" and selection["ids"] == [identifier], selection
            assert selection["document_id"] == before["document_id"]
            assert selection["refs"] == [{"resource_id": geometry_resource, "entity_kind": "element", "local_id": identifier}]
            assert view._highlight.GetVisibility(), "The approved selection did not reach the renderer"
            view._highlight.GetMapper().Update()
            assert view._highlight.GetMapper().GetInput().GetNumberOfCells() == 1
            assert not view._render_failed
            picks.append({"element_id": identifier, "qt_position": [point.x(), point.y()],
                          "selection": selection})
        evidence["picks"] = picks
        # X11 screen capture includes the real native child render window. Keep
        # framebuffer and full-window captures separate so neither can mask failure.
        screenshot, _ = _screen_pixels(window)
        assert screenshot.save(str(output / (stem + "-window.png")), "PNG")
        selected_image, selected = _readback(render_window)
        _png(output / (stem + "-selected-viewport.png"), selected_image)
        assert selected != visible, "Selection highlight did not change rendered pixels"
        after = session.describe()
        assert after["revision"] == before["revision"] and after["dirty"] == before["dirty"]
        assert raw_cards == tuple((card["id"], session.card_text(card["id"])) for card in session.list_cards())
        evidence["status"] = "passed"
    except BaseException as error:
        evidence["status"] = "failed"
        evidence["error"] = f"{type(error).__name__}: {error}"
        if window is not None and window.isVisible():
            image = window.screen().grabWindow(int(window.winId()))
            if not image.isNull(): image.save(str(output / (stem + "-failure.png")), "PNG")
        raise
    finally:
        evidence_file.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        if window is not None:
            window._allow_close = True
            window.close()
            _pump()


def test_geometry_feature_inspect_render_and_private_mouse_pick(tmp_path):
    """One real source→worker→Qt/VTK path; no renderer or picker stubs."""
    from caelab_prep.application import PrepSession
    from caelab_prep.adapters.gmsh_backend import GmshBackend
    from caelab_prep.ui.geometry_features import GeometryFeaturesDialog
    from test_external_mesh_ui import wait_task

    output = Path(os.environ["CAELAB_NATIVE_RENDER_ARTIFACT_DIR"]).expanduser()
    assert output.is_absolute()
    output.mkdir(parents=True, exist_ok=True)
    assert QApplication.instance().platformName() == "xcb"
    source = tmp_path / "native-hole.step"
    # CC0: self-authored analytic CAD fixture, not a user or vendor model.
    script = """import gmsh, sys
gmsh.initialize(readConfigFiles=False, interruptible=False)
try:
    gmsh.model.add('own-hole-fixture')
    box = gmsh.model.occ.addBox(0, 0, 0, 12, 8, 3)
    cutter = gmsh.model.occ.addCylinder(6, 4, -1, 0, 0, 5, 1)
    gmsh.model.occ.cut([(3, box)], [(3, cutter)])
    gmsh.model.occ.synchronize()
    gmsh.write(sys.argv[1])
finally:
    gmsh.finalize()
"""
    generated = subprocess.run([sys.executable, "-c", script, str(source)], capture_output=True, text=True, timeout=30)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    session = PrepSession(); before = session.describe()
    window = MainWindow(session, presentation="hypermesh", enable_viewport=False)
    window._allow_close = True
    dialog = GeometryFeaturesDialog(window, backend=GmshBackend(timeout=30), enable_viewport=True)
    evidence = {"status": "running", "source_sha256": source_hash,
                "scope": "One self-authored CAD through-hole, Linux/X11 real inspection/render/pick; Windows unverified"}
    try:
        window.show(); dialog.resize(960, 640); dialog.show()
        assert QTest.qWaitForWindowExposed(dialog, 10000)
        dialog.source.setText(str(source)); dialog.output.setText(str(tmp_path / "inspection"))
        QTest.mouseClick(dialog.inspect_button, Qt.MouseButton.LeftButton)
        wait_task(dialog)
        assert dialog.report and dialog.table.rowCount() == 1, dialog.error.text()
        feature, = dialog.report["features"]
        assert feature["kind"] == "through_hole_candidate" and feature["radius"] == 1.
        view = dialog.viewport; _pump(); view.fit_view(); view.render(); _pump()
        render_window = view._widget.GetRenderWindow()
        assert render_window.GetClassName() == "vtkXOpenGLRenderWindow"
        assert not view._render_failed and render_window.GetNeverRendered() == 0
        assert tuple((dialog.width(), dialog.height())) == (960, 640)
        assert view._visible_grid.GetNumberOfCells() == len(dialog.projection["cells"])
        dialog.table.clearSelection()
        view.set_selection({**{key: dialog.projection[key] for key in
            ("document_id", "document_epoch", "revision", "projection_revision", "resource_revisions")},
            "kind": "element", "ids": [], "refs": []})
        visible_image, visible = _readback(render_window)
        _png(output / "geometry-features-viewport.png", visible_image)
        _, screen_before = _screen_pixels(dialog)
        view._actor.SetVisibility(False)
        try:
            view.render(); _, hidden = _readback(render_window)
            _, screen_hidden = _screen_pixels(dialog)
        finally:
            view._actor.SetVisibility(True); view.render()
        assert len(visible) == len(hidden) > 0 and len(screen_before) == len(screen_hidden) > 0
        changed = sum(visible[index:index + 3] != hidden[index:index + 3] for index in range(0, len(visible), 3))
        screen_changed = sum(screen_before[index:index + 4] != screen_hidden[index:index + 4]
                             for index in range(0, len(screen_before), 4))
        assert changed > 100 and screen_changed > 100
        nodes = dict(zip(dialog.projection["node_ids"], dialog.projection["points"]))
        cell = next(cell for cell in dialog.projection["cells"]
                    if dialog._primitive_owners[cell["id"]] == feature["surface_uuid"]
                    and all(nodes[node][2] == 3. for node in cell["nodes"]))
        center = [sum(nodes[node][axis] for node in cell["nodes"]) / 2 for axis in range(3)]
        view._renderer.SetWorldPoint(*center, 1.); view._renderer.WorldToDisplay()
        x, y, _ = view._renderer.GetDisplayPoint(); width, height = render_window.GetSize()
        point = QPoint(round(x * view._widget.width() / width), round((height - 1 - y) * view._widget.height() / height))
        assert view._widget.rect().contains(point)
        picks = []; view.entityPicked.connect(picks.append)
        QTest.mouseClick(view._widget, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        _pump()
        assert picks and picks[-1]["document_id"] == dialog.preview_id
        assert dialog._primitive_owners[picks[-1]["id"]] == feature["surface_uuid"]
        assert dialog.table.selectionModel().selectedRows()
        assert session.describe() == before
        dialog.inspection.verify_assets()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        screen_image, _ = _screen_pixels(dialog)
        assert screen_image.save(str(output / "geometry-features-960x640.png"), "PNG")
        evidence.update(status="passed", framebuffer_changed_pixels=changed, native_window_changed_pixels=screen_changed,
                        feature=feature, picked=picks[-1], display_line_primitives=len(dialog.projection["cells"]),
                        model_unchanged=True, input_unchanged=True, actual_sdk_inspection_calls=1,
                        fixture_cad_creation_calls=1, mesh_generation_calls=0)
    except BaseException as error:
        evidence.update(status="failed", error=f"{type(error).__name__}: {error}")
        if dialog.isVisible(): dialog.screen().grabWindow(int(dialog.winId())).save(str(output / "geometry-features-failure.png"), "PNG")
        raise
    finally:
        (output / "geometry-features.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        dialog.reject(); window.close(); _pump()
