import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.ui.main_window import MainWindow
from test_node_moves import opened


pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.mark.parametrize("name,ids,positions", [
    ("beam_shell_tet", "2", [(11, 0, 0)]),
    ("truss_shell_hex", "5 6 7 8 9", [(0, 0, 11), (10, 0, 11), (10, 10, 11), (0, 10, 11), (-10, 10, 11)]),
])
def test_window_action_drafts_preview_apply_undo_and_cancel(qt_widgets, name, ids, positions):
    session = opened(name)
    window = MainWindow(session, enable_viewport=False)
    window.show()
    window.node_move_action.trigger()
    QApplication.processEvents()
    dialog = window.node_move_dialog
    assert dialog is not None and dialog.isVisible()
    mesh = next(resource for resource in session._deck_resources() if resource.id != session._root_id)
    dialog.resource.setCurrentIndex(dialog.resource.findData(mesh.id))
    dialog.identifiers.setText(ids)
    dialog.add_button.click()
    assert dialog.table.rowCount() == len(positions)
    revision = session.document.revision
    baseline = session.mesh_view(mutable=True)["points"]
    for row, xyz in enumerate(positions):
        for axis, value in enumerate(xyz):
            dialog.table.cellWidget(row, axis+2).setText(str(value))
    dialog.preview_button.click()
    assert dialog._plan is not None, dialog.status.text()
    assert session.document.revision == revision and not dialog.apply_button.isEnabled()
    dialog.reviewed.setChecked(True)
    assert dialog.apply_button.isEnabled()
    dialog.table.cellWidget(0, 2).setText(str(positions[0][0] + .25))
    assert dialog._plan is None and not dialog.apply_button.isEnabled()
    dialog.table.cellWidget(0, 2).setText(str(positions[0][0]))
    dialog.preview_button.click()
    dialog.reviewed.setChecked(True)
    dialog.apply_button.click()
    QApplication.processEvents()
    assert session.document.revision == revision + 1, dialog.status.text()
    assert session.mesh_view(mutable=True)["points"] != baseline
    window.undo_action.trigger()
    QApplication.processEvents()
    assert session.mesh_view(mutable=True)["points"] == baseline
    # Closing a stale preview does not create another command.
    before = session.describe()
    dialog.close_button.click()
    QApplication.processEvents()
    assert session.describe() == before


def test_wrong_source_invalid_coordinate_and_external_change_block_apply(qt_widgets):
    session = opened("beam_shell_tet")
    window = MainWindow(session, enable_viewport=False)
    window.show()
    dialog = window.open_node_move()
    mesh = next(resource for resource in session._deck_resources() if resource.id != session._root_id)
    dialog.resource.setCurrentIndex(dialog.resource.findData(mesh.id))
    dialog.identifiers.setText("2")
    dialog.add_nodes()
    editor = dialog.table.cellWidget(0, 2)
    editor.setText("NaN")
    dialog.prepare_preview()
    assert dialog._plan is None
    editor.setText("11")
    dialog.prepare_preview()
    dialog.reviewed.setChecked(True)
    revision = session.document.revision
    session.create_node_group("External edit", [1])
    # Guard also works before the queued UI event is delivered.
    dialog.apply_move()
    assert session.document.revision == revision + 1 and dialog._plan is None
    QTest.qWait(5)
