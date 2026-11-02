"""One native merge command and the same Action across the eight presentations."""
import json
import subprocess
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from caelab_prep.cae_core import PrepError
from test_group_member_review import related, state
from test_modeling_ui import pump
from test_node_moves import MODELS, opened

pytestmark = pytest.mark.usefixtures("qt_widgets")


def add_pair(dialog, source, keeper):
    for index, identifier in enumerate((source, keeper)):
        reference = dialog.session.resolve_entity_reference("node", identifier)["reference"]
        dialog.sources[index].setCurrentIndex(dialog.sources[index].findData(reference["resource_id"]))
        dialog.identifiers[index].setText(str(identifier))
    QTest.mouseClick(dialog.add_button, Qt.MouseButton.LeftButton); pump()
    assert dialog.table.rowCount() == len(dialog._pairs)


def open_merge(session, profile=None, *, enable_viewport=False):
    window = MainWindow(session, presentation=profile, enable_viewport=enable_viewport)
    window._allow_close = True; window.show(); pump()
    assert window.node_merge_action.isEnabled()
    window.node_merge_action.trigger(); pump()
    dialog = window.node_merge_dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog.tolerance.text() == "" and dialog.table.rowCount() == 0
    return window, dialog


@pytest.mark.parametrize("name,source,keeper", [("beam_shell_tet", 6, 8), ("truss_shell_hex", 9, 4)])
@pytest.mark.parametrize("profile", PROFILES)
def test_each_presentation_merge_cancel_apply_undo_save_and_new_process_export(name, source, keeper, profile, tmp_path):
    session = opened(name); before = state(session)
    window, dialog = open_merge(session, profile)
    add_pair(dialog, source, keeper); dialog.tolerance.setText("20")
    dialog.preview_button.click(); pump()
    assert dialog._plan is None and state(session) == before  # PART approval was not inferred.
    dialog.cross_parts.setChecked(True); dialog.preview_button.click(); pump()
    assert dialog._plan and dialog._plan["admissible"], dialog.status.text()
    assert "Keeper coordinates stay fixed" in dialog.preview.toPlainText()
    assert not dialog.apply_button.isEnabled() and state(session) == before
    QTest.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton); pump()
    assert window.node_merge_dialog is None and state(session) == before
    window.node_merge_action.trigger(); pump(); dialog = window.node_merge_dialog
    add_pair(dialog, source, keeper); dialog.tolerance.setText("20"); dialog.cross_parts.setChecked(True)
    dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    assert dialog.apply_button.isEnabled()
    dialog.tolerance.setText("21")
    assert dialog._plan is None and not dialog.apply_button.isEnabled()
    dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton); pump()
    assert session.document.revision == before[0] + 1, dialog.status.text()
    assert dialog._pairs == [] and dialog.table.rowCount() == 0 and not dialog.cross_parts.isChecked()
    assert not dialog.apply_button.isEnabled()
    after = state(session)
    dialog.close_button.click(); pump()
    window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
    window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
    project = tmp_path / "merge-ui.caeprep"; session.save_project(project)
    code = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(Path(sys.argv[1]).with_name('merged_0000.rad'))
p=s._mesh_edit_snapshot();print(json.dumps({'nodes':[n.ref.local_id for n in p.nodes],'cells':len(p.cells)}))
"""
    result = json.loads(subprocess.check_output([sys.executable, "-c", code, str(project)], text=True))
    assert source not in result["nodes"] and len(result["nodes"]) == 8 and result["cells"] == 3
    assert window.close()


def test_multiple_pairs_keep_individual_permissions_and_one_history_step():
    session = opened("beam_shell_tet"); before = state(session)
    window, dialog = open_merge(session)
    add_pair(dialog, 6, 9); dialog.cross_parts.setChecked(True)
    add_pair(dialog, 8, 5); dialog.cross_parts.setChecked(True); dialog.tolerance.setText("30")
    dialog.preview_button.click(); pump()
    assert dialog._plan and len(dialog._plan["mapping"]) == 2, dialog.status.text()
    dialog.table.selectRow(0); pump(); dialog.cross_parts.setChecked(False)
    assert dialog._plan is None and not dialog._pairs[0]["cross_parts"] and dialog._pairs[1]["cross_parts"]
    dialog.preview_button.click(); assert dialog._plan is None and state(session) == before
    dialog.cross_parts.setChecked(True); dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    dialog.apply_button.click(); pump()
    assert session.document.revision == before[0] + 1 and len(session._mesh_edit_snapshot().nodes) == 7
    assert window.close()
    session.undo(); assert state(session)[1:] == before[1:]


def test_current_selection_is_used_only_for_the_requested_side():
    session = opened("truss_shell_hex")
    source = session.resolve_entity_reference("node", 9)["reference"]
    session.import_source(session.plan_import_source(MODELS / "beam_shell_tet" / "model_0000.rad")["plan_id"])
    shell = next(c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL" and c.ref.resource_id != source["resource_id"])
    keeper = shell.nodes[0].local_id
    before = state(session); window, dialog = open_merge(session)
    session.select_entity("node", 9); pump(); dialog.selection_buttons[0].click()
    assert dialog.identifiers[0].text() == "9" and dialog.identifiers[1].text() == ""
    session.select_entity("node", keeper); pump(); dialog.selection_buttons[1].click(); dialog.add_button.click()
    assert dialog._pairs[0]["source"] == source and dialog._pairs[0]["keeper"]["resource_id"] == shell.nodes[0].resource_id
    assert dialog.table.item(0, 0).text().splitlines()[0] != dialog.table.item(0, 1).text().splitlines()[0]
    dialog.cross_parts.setChecked(True); dialog.cross_resources.setChecked(True); dialog.tolerance.setText("100")
    dialog.preview_button.click(); assert dialog._plan, dialog.status.text()
    QTest.keyClick(dialog, Qt.Key.Key_Escape); pump()
    assert state(session) == before and window.node_merge_dialog is None
    assert window.close()


def test_default_frame_transition_error_keeps_the_pair_and_original_model():
    session = opened("beam_shell_tet"); before = state(session)
    window, dialog = open_merge(session)
    add_pair(dialog, 6, 2); dialog.cross_parts.setChecked(True); dialog.tolerance.setText("20")
    dialog.preview_button.click(); pump()
    assert dialog._plan is None and not dialog.apply_button.isEnabled()
    assert "beam" in dialog.status.text().lower() and "frame" in dialog.status.text().lower()
    assert dialog.table.rowCount() == 1 and state(session) == before
    assert window.close()


def test_external_change_and_active_model_operation_block_merge_without_losing_drafts():
    session = opened("beam_shell_tet")
    window, dialog = open_merge(session)
    add_pair(dialog, 6, 8); dialog.cross_parts.setChecked(True); dialog.tolerance.setText("20")
    dialog.preview_button.click(); dialog.reviewed.setChecked(True)
    window.modeling.actions["material.create"].trigger(); pump()
    assert window.modeling.active
    before = state(session); dialog.apply_merge()
    assert state(session) == before and window.modeling.active and not dialog.apply_button.isEnabled()
    window.modeling.cancel(); dialog.prepare_preview(); dialog.reviewed.setChecked(True)
    session.create_curve("Concurrent edit", [(0, 0), (1, 1)])
    before = state(session); dialog.apply_merge()  # Guard works before queued event delivery.
    assert state(session) == before and "model changed" in dialog.status.text().lower()
    pump(); assert not dialog.preview_button.isEnabled()
    assert window.close()


def test_reviewed_condition_targets_use_existing_reconnection_ui_before_export(tmp_path):
    from test_prepared_replacement_ui import choose_group, link
    session = opened("truss_shell_hex")
    group, load, _, _ = related(session, [9])
    window, dialog = open_merge(session, "hypermesh")
    add_pair(dialog, 9, 4); dialog.cross_parts.setChecked(True); dialog.tolerance.setText("20")
    dialog.preview_button.click(); pump()
    text = dialog.preview.toPlainText()
    assert "Unevaluated multiplier sum" in text and "Current nodes" in text and "Proposed nodes" in text
    assert "projections only" in text and "explicit reconnection" in text
    dialog.reviewed.setChecked(True); dialog.apply_button.click(); pump()
    assert session.group_members(group)["member_ids"] == [9] and session.condition_support(load)["status"] == "stale"
    with pytest.raises(PrepError) as error: session.export_rad(tmp_path / "blocked_0000.rad")
    assert error.value.code == "stale_mesh_targets"
    dialog.close_button.click(); pump()
    window.prepared_mesh_action.trigger(); pump(); reconnect = window.prepared_mesh_dialog
    assert reconnect is not None
    choose_group(reconnect, group); link(reconnect, 9, 4)
    reconnect.reconnect_reviewed.setChecked(True)
    QTest.mouseClick(reconnect.reconnect_button, Qt.MouseButton.LeftButton); pump()
    assert session.group_members(group)["member_ids"] == [4] and session.condition_support(load)["status"] == "supported"
    session.export_rad(tmp_path / "reconnected_0000.rad")
    project = tmp_path / "reconnected.caeprep"; session.save_project(project)
    assert window.close()


def test_contact_permission_is_explicit_and_targets_remain_stale_after_apply():
    session = opened("truss_shell_hex")
    secondary = session.create_node_group("Reviewed secondary", [9])["card_id"]
    main = session.create_surface("Reviewed main shell", [session.resolve_part_reference(9)["card_id"]])["card_id"]
    contact = session.create_contact("Exact TYPE7 permission", secondary, main, .2)["card_id"]
    before = state(session); window, dialog = open_merge(session, "abaqus")
    add_pair(dialog, 9, 4); dialog.cross_parts.setChecked(True); dialog.tolerance.setText("20")
    dialog.preview_button.click(); assert dialog._plan is None and state(session) == before
    assert dialog.contacts.count() == 1 and dialog.contacts.isVisible()
    item = dialog.contacts.item(0)
    assert item.data(Qt.ItemDataRole.UserRole)["local_id"] == contact
    item.setCheckState(Qt.CheckState.Checked)
    dialog.preview_button.click(); pump()
    assert dialog._plan and dialog._plan["admissible"], dialog.status.text()
    text = dialog.preview.toPlainText()
    assert "Secondary" in text and "Main" in text and "gap, activation, penetration and force are not evaluated" in text
    dialog.reviewed.setChecked(True); dialog.apply_button.click(); pump()
    assert session.document.revision == before[0] + 1
    assert {secondary, main} <= session.mesh_relationships()["stale_targets"].keys()
    assert session.group_members(secondary)["member_ids"] == [9]
    assert window.close()
