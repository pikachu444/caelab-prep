"""Actual Linux/X11 merge windows and physical VTK data; not Windows OS proof."""
import os
from pathlib import Path

import pytest

if os.environ.get("CAELAB_TEST_NATIVE_RENDER") != "1":
    pytest.skip("Requires explicit Linux/X11 native render opt-in", allow_module_level=True)

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from vtkmodules.util.vtkConstants import VTK_LINE, VTK_QUAD, VTK_TETRA, VTK_HEXAHEDRON

from test_group_member_review import related
from test_modeling_ui import pump
from test_native_render import _screen_pixels
from test_node_merges_ui import add_pair, open_merge
from test_node_moves import opened

pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.mark.parametrize("name,source,keeper", [("beam_shell_tet", 6, 8), ("truss_shell_hex", 9, 4)])
@pytest.mark.parametrize("profile", ["hypermesh", "abaqus"])
def test_actual_x11_merge_inputs_review_apply_and_physical_grid(name, source, keeper, profile):
    assert QApplication.instance().platformName() == "xcb"
    output = Path(os.environ["CAELAB_NATIVE_RENDER_ARTIFACT_DIR"]) / "node-merges"
    assert output.is_absolute(); output.mkdir(parents=True, exist_ok=True)
    session = opened(name)
    group, _, _, _ = related(session, [2 if name == "beam_shell_tet" else 9])
    if name == "truss_shell_hex":
        main = session.create_surface("Reviewed main shell", [session.resolve_part_reference(9)["card_id"]])["card_id"]
        session.create_contact("Explicit TYPE7 boundary", group, main, .2)
    revision = session.document.revision
    window, dialog = open_merge(session, profile, enable_viewport=True)
    assert QTest.qWaitForWindowExposed(window, 10000) and QTest.qWaitForWindowExposed(dialog, 10000)
    add_pair(dialog, source, keeper); dialog.tolerance.setText("20"); dialog.cross_parts.setChecked(True)
    if name == "truss_shell_hex": dialog.contacts.item(0).setCheckState(Qt.CheckState.Checked)
    for stage in ("pairs", "review"):
        if stage == "review":
            QTest.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton); pump()
            assert dialog._plan and dialog._plan["admissible"], dialog.status.text()
            dialog.reviewed.setChecked(True)
            (output / f"{name}-{profile}-review.txt").write_text(dialog.preview.toPlainText(), encoding="utf-8")
        for width, height in ((960, 760), (640, 480)):
            dialog.resize(width, height); pump()
            assert (dialog.width(), dialog.height()) == (width, height)
            assert dialog.screen().availableGeometry().contains(dialog.frameGeometry())
            for button in (dialog.preview_button, dialog.apply_button, dialog.close_button):
                assert button.visibleRegion().boundingRect().contains(button.rect())
            bar = dialog.tabs.widget(0).verticalScrollBar() if stage == "pairs" else dialog.preview.verticalScrollBar()
            for position in ("top", "bottom"):
                bar.setValue(0 if position == "top" else bar.maximum()); pump()
                screenshot, _ = _screen_pixels(dialog)
                assert screenshot.save(str(output / f"{name}-{profile}-{stage}-{width}x{height}-{position}.png"))
    assert session.document.revision == revision
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton); pump()
    assert session.document.revision == revision + 1 and dialog._pairs == []
    view = window.viewport
    assert view._grid.GetNumberOfPoints() == len(view._node_ids) == 8
    assert view._grid.GetNumberOfCells() == len(view._cells) == 3
    assert source not in view._node_ids and all(source not in cell["nodes"] for cell in view._cells)
    expected = {VTK_LINE, VTK_QUAD, VTK_TETRA if name == "beam_shell_tet" else VTK_HEXAHEDRON}
    assert {view._grid.GetCellType(i) for i in range(3)} == expected
    assert view.visible_cell_indices() == [0, 1, 2]
    assert session.mesh_relationships()["stale_targets"]
    if name == "beam_shell_tet":
        resource = next(r for r in session._deck_resources() if any(c.keyword == "/BEAM/10" for c in r.cards))
        card = next(c for c in resource.cards if c.keyword == "/BEAM/10")
        line = resource.render().decode("latin1").splitlines()[card.data[0]]
        assert int(line[30:40]) == 8
    assert window.close()
