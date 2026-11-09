"""Explicit Drop in the existing typed target editor, with sealed review and history."""
import pytest

from caelab_prep.application import PrepSession
from caelab_prep.ui.reference_profiles import PROFILES
from test_group_member_review import state
from test_mesh_target_drop import moved, node_request
from test_modeling_ui import pump
from test_node_coalescence_ui import open_reconnection
from test_node_moves import MODELS, opened
from test_prepared_replacement_ui import choose_group, link

pytestmark = pytest.mark.usefixtures("qt_widgets")


def drop(dialog, original):
    dialog.tabs.setCurrentIndex(1)
    dialog.reconnect_table.selectRow(dialog.reconnect_model.rows.index(original))
    assert dialog.drop_member_button.isEnabled()
    dialog.drop_member_button.click(); pump()
    assert original in dialog._dropped, dialog.status.text()


@pytest.mark.parametrize("profile", PROFILES)
def test_presentations_explicit_drop_needs_final_preview_and_one_undo(profile, tmp_path):
    session = opened("beam_shell_tet")
    group, load, bcs, velocity, _ = node_request(session)
    window, dialog = open_reconnection(session, group, profile)
    before = state(session); declarations = {c: session.card_text(c) for c in (load, bcs, velocity)}
    link(dialog, 2, 2)
    assert not dialog.reconnect_preview_button.isEnabled()
    assert "drop_members" not in dialog._reconnection_request()[group]
    drop(dialog, 1)
    assert dialog._mapping.keys() == {2} and "1 mapped + 1 dropped; 0 pending" in dialog.link_counts.text()
    assert dialog.reconnect_model.value(0, 2) == "Explicit Drop"
    dialog.reconnect_reviewed.setChecked(True)
    assert not dialog.reconnect_button.isEnabled() and not dialog.apply_reconnection()
    assert state(session) == before
    dialog.reconnect_preview_button.click(); pump()
    assert dialog._reconnect_plan, dialog.status.text()
    text = dialog.reconnect_details.toPlainText()
    assert "Remove these old IDs from the group: [1]" in text
    assert "1 explicitly removed; 0 repeated links coalesced" in text
    assert "[6.0, 0.0, 0.0] → [3.0, 0.0, 0.0]" in text
    assert state(session) == before and dialog.reconnect_reviewed.isChecked()
    assert dialog.reconnect_button.isEnabled()
    dialog.reconnect_reviewed.setChecked(False)
    assert not dialog.reconnect_button.isEnabled() and not dialog.apply_reconnection()
    assert "review_required" in dialog.status.text() and state(session) == before
    assert dialog.prepare_reconnection() and dialog.reconnect_reviewed.isChecked()
    dialog.reconnect_button.click(); pump()
    assert session.document.revision == before[0] + 1
    assert session.group_members(group)["member_ids"] == [2]
    assert not dialog._dropped and dialog._reconnect_plan is None
    assert all(session.card_text(c) == raw for c, raw in declarations.items())
    dialog.close_button.click(); pump()
    after = state(session)
    window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
    window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
    path = tmp_path / "drop-ui.caeprep"; session.save_project(path)
    reopened = PrepSession(); reopened.open_project(path)
    assert reopened.group_members(group)["member_ids"] == [2]
    assert not reopened.mesh_relationships()["stale_targets"]
    assert window.close()


@pytest.mark.parametrize("kind", ["element", "part"])
def test_typed_drop_review_reuses_the_same_dialog_and_shows_current_source(kind):
    session = opened("beam_shell_tet")
    session.import_source(session.plan_import_source(MODELS / "truss_shell_hex" / "model_0000.rad")["plan_id"])
    shells = [c for c in session._mesh_edit_snapshot().cells if c.family == "SHELL"]
    if kind == "element":
        refs = [{"resource_id": c.ref.resource_id, "entity_kind": "element", "local_id": c.ref.local_id} for c in shells]
        group = session.create_element_group("Two shells", refs)["card_id"]
        identifiers = [c.ref.local_id for c in shells]
    else:
        group = session.create_surface("Two PARTs", [c.part.local_id for c in shells])["card_id"]
        identifiers = [session.part_assignments(c.part.local_id)["native_part_id"] for c in shells]
    moved(session, group)
    window, dialog = open_reconnection(session, group)
    before = state(session)
    link(dialog, identifiers[1], identifiers[1]); drop(dialog, identifiers[0])
    assert not dialog.coalesce_targets.isEnabled()
    assert dialog.prepare_reconnection(), dialog.status.text()
    text = dialog.reconnect_details.toPlainText()
    assert f"Remove these old IDs from the group: [{identifiers[0]}]" in text
    resource = (session.document.resources[shells[1].ref.resource_id] if kind == "element"
                else session._find_card(shells[1].part.local_id))
    assert resource.name in text
    assert (f"element {identifiers[1]}" if kind == "element" else "/PART") in text
    assert state(session) == before
    dialog.reconnect_reviewed.setChecked(True)
    assert dialog.apply_reconnection(), dialog.status.text()
    assert group not in session.mesh_relationships()["stale_targets"]
    assert session.card_text(group).splitlines()[2].strip() == str(identifiers[1])
    session.undo(); assert state(session)[1:] == before[1:]
    dialog.close_button.click(); assert window.close()


@pytest.mark.parametrize("change", ["clear", "link", "group", "document", "close"])
def test_new_decision_group_document_or_close_invalidates_drop_review(change):
    session = opened("beam_shell_tet")
    if change == "group":
        other = session.create_node_group("Other", [1, 2])["card_id"]
    group, _, _, _, _ = node_request(session)
    window, dialog = open_reconnection(session, group)
    link(dialog, 2, 2); drop(dialog, 1)
    assert dialog.prepare_reconnection()
    dialog.reconnect_reviewed.setChecked(True)
    if change == "clear":
        dialog.tabs.setCurrentIndex(1); dialog.reconnect_table.selectRow(0); dialog.remove_link_button.click()
        assert not dialog._dropped and 1 not in dialog._mapping
        assert "Decision cleared" in dialog.status.text() and "will be removed" not in dialog.status.text()
    elif change == "link":
        dialog.tabs.setCurrentIndex(1); link(dialog, 1, 1)
        assert not dialog._dropped and 1 in dialog._mapping
    elif change == "group": choose_group(dialog, other)
    elif change == "document": session.create_curve("External", [(0, 0), (1, 1)]); pump()
    else: dialog.close_button.click(); pump()
    assert dialog._reconnect_plan is None and getattr(session, "_mesh_reconnection_plan", None) is None
    assert not dialog.reconnect_reviewed.isChecked() and not dialog.reconnect_button.isEnabled()
    assert session.group_members(group)["member_ids"] == [1, 2]
    dialog.close_button.click(); assert window.close()


def test_no_selection_and_all_dropped_cannot_commit_and_pending_entry_is_cleared():
    session = opened("beam_shell_tet")
    group, _, _, _, _ = node_request(session)
    window, dialog = open_reconnection(session, group)
    before = state(session)
    dialog.reconnect_table.clearSelection()
    assert not dialog.drop_member_button.isEnabled() and not dialog.remove_link_button.isEnabled()
    dialog.drop_member(); assert not dialog._dropped and "invalid_reference" in dialog.status.text()
    drop(dialog, 1); drop(dialog, 2)
    assert not dialog.reconnect_preview_button.isEnabled() and not dialog.reconnect_button.isEnabled()
    assert "Keep at least one current target" in dialog.link_counts.text()
    assert not dialog.prepare_reconnection() and state(session) == before
    dialog.reconnect_table.selectRow(1); dialog.current_target.setText("2"); dialog.find_target_button.click()
    dialog.drop_member_button.click(); pump()
    assert not dialog.current_target.text() and dialog.target_choice.count() == 0
    link(dialog, 2, 2)
    assert dialog._dropped == {1} and dialog.prepare_reconnection()
    dialog.close_button.click(); assert state(session) == before and window.close()


def test_minimum_mapping_keeps_decision_column_visible_and_scrolls_to_drop():
    session = opened("beam_shell_tet")
    group, _, _, _, _ = node_request(session)
    window, dialog = open_reconnection(session, group)
    dialog.resize(680, 500); pump()
    assert dialog.reconnect_table.horizontalScrollBar().maximum() == 0
    header = dialog.reconnect_table.horizontalHeader()
    assert header.sectionViewportPosition(2) + header.sectionSize(2) <= dialog.reconnect_table.viewport().width()
    page = dialog.tabs.widget(1)
    page.ensureWidgetVisible(dialog.drop_member_button); pump()
    assert dialog.drop_member_button.visibleRegion().boundingRect().width() >= dialog.drop_member_button.sizeHint().width()
    dialog.reconnect_table.selectRow(0); dialog.drop_member_button.click(); pump()
    assert dialog._dropped == {1} and not dialog.reconnect_reviewed.isChecked()
    dialog.reconnect_table.selectRow(0); dialog.remove_link_button.click(); pump()
    assert not dialog._dropped and "Decision cleared" in dialog.status.text()
    dialog.close_button.click(); assert window.close()
