"""One final reviewed set in the existing mesh-target editor and document history."""
import json
import subprocess
import sys

import pytest

from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_group_member_review import related, state
from test_modeling_ui import pump
from test_node_coalescence import merged_group
from test_node_merges_ui import add_pair, open_merge
from test_node_moves import opened
from test_prepared_replacement_ui import choose_group, link

pytestmark = pytest.mark.usefixtures("qt_widgets")


def open_reconnection(session, group, profile=None, *, enable_viewport=False):
    window = MainWindow(session, presentation=profile, enable_viewport=enable_viewport)
    window._allow_close = True; window.show(); pump()
    window.prepared_mesh_action.trigger(); pump()
    dialog = window.prepared_mesh_dialog
    choose_group(dialog, group)
    return window, dialog


def fill_links(dialog):
    link(dialog, 9, 4); link(dialog, 4, 4)
    assert "2 / 2 old links mapped → 1 unique" in dialog.link_counts.text()


@pytest.mark.parametrize("profile", PROFILES)
def test_all_presentations_review_merge_then_explicit_coalescence_one_undo_and_reopen(profile, tmp_path):
    session = opened("truss_shell_hex")
    group, load, _, _ = related(session, [9, 4])
    window, merge = open_merge(session, profile)
    add_pair(merge, 9, 4); merge.tolerance.setText("20"); merge.cross_parts.setChecked(True)
    merge.preview_button.click(); pump()
    assert merge._plan and merge._plan["admissible"], merge.status.text()
    assert "2 old links → 1 unique targets" in merge.preview.toPlainText()
    merge.reviewed.setChecked(True); merge.apply_button.click(); pump()
    merge.close_button.click(); pump()
    assert session.group_members(group)["member_ids"] == [9, 4]
    window.prepared_mesh_action.trigger(); pump(); dialog = window.prepared_mesh_dialog
    choose_group(dialog, group); fill_links(dialog)
    before = state(session); original_load = session.card_text(load)
    dialog.reconnect_reviewed.setChecked(True)
    assert not dialog.reconnect_button.isEnabled()
    assert not dialog.prepare_reconnection() and state(session) == before
    dialog.coalesce_targets.setChecked(True)
    assert not dialog.reconnect_reviewed.isChecked() and not dialog.reconnect_button.isEnabled()
    assert dialog.prepare_reconnection(), dialog.status.text()
    text = dialog.reconnect_details.toPlainText()
    assert "2 old links → 1 unique current targets" in text
    assert "[6.0, 0.0, 0.0] → [3.0, 0.0, 0.0]" in text
    assert "historical node ownership" in text and "empty overlap list" in text
    assert "Declared initial velocity" in text and dialog.tabs.currentIndex() == 3
    dialog.reconnect_reviewed.setChecked(True)
    assert dialog.reconnect_button.isEnabled() and state(session) == before
    dialog.reconnect_button.click(); pump()
    assert session.document.revision == before[0] + 1 and session.group_members(group)["member_ids"] == [4]
    assert session.card_text(load) == original_load and dialog._reconnect_plan is None
    assert not dialog.coalesce_targets.isChecked()
    after = state(session); dialog.close_button.click(); pump()
    window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
    window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
    project = tmp_path / "coalesced-ui.caeprep"; session.save_project(project)
    code = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(Path(sys.argv[1]).with_name('coalesced_0000.rad'))
print(json.dumps(s.group_members(sys.argv[2])['member_ids']))
"""
    assert json.loads(subprocess.check_output([sys.executable, "-X", "utf8", "-c", code, str(project), group], text=True)) == [4]
    assert window.close()


@pytest.mark.parametrize("change", ["permission", "entry", "link", "document", "close"])
def test_changed_input_or_close_cancels_only_the_reviewed_reconnection(change):
    session, group, _, _, _ = merged_group()
    window, dialog = open_reconnection(session, group)
    fill_links(dialog); dialog.coalesce_targets.setChecked(True)
    assert dialog.prepare_reconnection(); token = dialog._reconnect_plan["plan_id"]
    dialog.reconnect_reviewed.setChecked(True)
    if change == "permission": dialog.coalesce_targets.setChecked(False)
    elif change == "entry": dialog.current_target.setText("1")
    elif change == "link":
        dialog.tabs.setCurrentIndex(1); dialog.reconnect_table.selectRow(0); dialog.remove_link_button.click()
    elif change == "document": session.create_curve("Concurrent change", [(0, 0), (1, 1)]); pump()
    else: dialog.close_button.click(); pump()
    assert dialog._reconnect_plan is None and not dialog.reconnect_button.isEnabled()
    assert getattr(session, "_mesh_reconnection_plan", None) is None
    assert session.group_members(group)["member_ids"] == [9, 4]
    assert token
    assert window.close()


def test_open_model_operation_blocks_preview_and_apply_without_losing_its_draft():
    session, group, _, _, _ = merged_group()
    window, dialog = open_reconnection(session, group); fill_links(dialog)
    dialog.coalesce_targets.setChecked(True); assert dialog.prepare_reconnection()
    dialog.reconnect_reviewed.setChecked(True)
    window.modeling.actions["material.create"].trigger(); pump()
    assert window.modeling.active
    before = state(session)
    assert not dialog.apply_reconnection() and "draft_pending" in dialog.status.text()
    assert state(session) == before and window.modeling.active
    assert not dialog.prepare_reconnection() and "draft_pending" in dialog.status.text()
    window.modeling.cancel(); dialog.close_button.click(); pump()
    assert window.close()
