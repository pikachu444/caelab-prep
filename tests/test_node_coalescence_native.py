"""Linux X11 final reconnection review, separately from Windows OS acceptance."""
import os
from pathlib import Path

import pytest

if os.environ.get("CAELAB_TEST_NATIVE_RENDER") != "1":
    pytest.skip("Requires explicit Linux/X11 native render opt-in", allow_module_level=True)

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from test_modeling_ui import pump
from test_native_render import _screen_pixels
from test_node_coalescence import merged_group
from test_node_coalescence_ui import fill_links, open_reconnection

pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.mark.parametrize("profile", ["hypermesh", "abaqus"])
def test_actual_x11_final_targets_review_and_unchanged_physical_grid(profile):
    assert QApplication.instance().platformName() == "xcb"
    folder = Path(os.environ["CAELAB_NATIVE_RENDER_ARTIFACT_DIR"]) / "node-coalescence"
    assert folder.is_absolute(); folder.mkdir(parents=True, exist_ok=True)
    session, group, load, _, _ = merged_group()
    window, dialog = open_reconnection(session, group, profile, enable_viewport=True)
    assert QTest.qWaitForWindowExposed(window, 10000) and QTest.qWaitForWindowExposed(dialog, 10000)
    fill_links(dialog); dialog.coalesce_targets.setChecked(True)
    revision = session.document.revision
    for stage in ("mapping", "review"):
        if stage == "review":
            dialog.reconnect_preview_button.click(); pump()
            assert dialog._reconnect_plan, dialog.status.text()
            dialog.reconnect_reviewed.setChecked(True)
            (folder / f"{profile}-review.txt").write_text(dialog.reconnect_details.toPlainText(), encoding="utf-8")
        for width, height in ((1020, 760), (680, 500)):
            dialog.resize(width, height); pump()
            assert (dialog.width(), dialog.height()) == (width, height)
            assert dialog.screen().availableGeometry().contains(dialog.frameGeometry())
            for button in (dialog.reconnect_preview_button, dialog.reconnect_button, dialog.close_button):
                assert button.visibleRegion().boundingRect().contains(button.rect())
            assert dialog.reconnect_reviewed.width() >= dialog.reconnect_reviewed.minimumSizeHint().width()
            bar = dialog.tabs.widget(1).verticalScrollBar() if stage == "mapping" else dialog.reconnect_details.verticalScrollBar()
            for position in ("top", "bottom"):
                bar.setValue(0 if position == "top" else bar.maximum()); pump()
                screenshot, _ = _screen_pixels(dialog)
                assert screenshot.save(str(folder / f"{profile}-{stage}-{width}x{height}-{position}.png"))
    assert session.document.revision == revision
    dialog.reconnect_button.click(); pump()
    assert session.document.revision == revision + 1 and session.group_members(group)["member_ids"] == [4]
    assert session.condition_support(load)["status"] == "supported"
    assert not session.mesh_relationships()["stale_targets"]
    assert window.viewport._grid.GetNumberOfPoints() == 8 and window.viewport._grid.GetNumberOfCells() == 3
    assert window.close()
