"""Actual X11 group review windows; no Windows/OS-input/solver claim."""
import os
from pathlib import Path

import pytest

if os.environ.get("CAELAB_TEST_NATIVE_RENDER") != "1":
    pytest.skip("Requires explicit Linux/X11 native render opt-in", allow_module_level=True)

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.ui.main_window import MainWindow
from test_group_member_review import related
from test_group_member_review_ui import edit, review
from test_modeling_ui import pump
from test_native_render import _screen_pixels
from test_node_moves import opened

pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
@pytest.mark.parametrize("profile", ["hypermesh", "abaqus"])
def test_actual_x11_membership_review_dialog_and_apply(name, profile):
    assert QApplication.instance().platformName() == "xcb"
    output = Path(os.environ["CAELAB_NATIVE_RENDER_ARTIFACT_DIR"]) / "group-members"
    assert output.is_absolute()
    output.mkdir(parents=True, exist_ok=True)
    session = opened(name)
    group, _, _, _ = related(session, [2])
    window = MainWindow(session, presentation=profile, enable_viewport=True)
    window._allow_close = True; window.show()
    assert QTest.qWaitForWindowExposed(window, 10000)
    pump()
    before = session.document.revision
    edit(window, group, [2, 5])

    def inspect(dialog):
        assert QTest.qWaitForWindowExposed(dialog, 10000)
        for width, height in ((900, 680), (640, 480)):
            dialog.resize(width, height); pump()
            assert dialog.screen().availableGeometry().contains(dialog.frameGeometry())
            assert dialog.apply_button.visibleRegion().boundingRect().contains(dialog.apply_button.rect())
            for phase in ("top", "bottom"):
                bar = dialog.details.verticalScrollBar()
                bar.setValue(0 if phase == "top" else bar.maximum()); pump()
                screenshot, _ = _screen_pixels(dialog)
                assert screenshot.save(str(output / f"{name}-{profile}-{width}x{height}-{phase}.png"))
        assert session.document.revision == before
        QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)

    text = review(window, inspect)
    (output / f"{name}-{profile}-review.txt").write_text(text, encoding="utf-8")
    assert session.document.revision == before + 1
    assert session.group_members(group)["member_ids"] == [2, 5]
    assert not window.modeling.active
    assert window.close()
