"""The existing group editor offers a separate, source-qualified review flow."""
import json
import subprocess
import sys

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest

from caelab_prep.ui.group_members import GroupMemberReviewDialog
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from caelab_prep.cae_core import PrepError
from test_conditions_ui import fill_operation
from test_group_member_review import element_model, related, state
from test_modeling_ui import pump
from test_node_moves import opened

pytestmark = pytest.mark.usefixtures("qt_widgets")


def edit(window, group, members, field="node_ids"):
    assert window.select_card(group)
    window.modeling.actions["object.edit"].trigger(); pump()
    assert window.modeling.active
    fill_operation(window, {field: tuple(members)})
    assert window.modeling.panel.preview_button.isVisible()


def review(window, operation):
    failures, seen = [], []

    def operate():
        dialog = window.modeling.membership_dialog
        try:
            assert isinstance(dialog, GroupMemberReviewDialog) and dialog.isVisible()
            seen.append(dialog.details.toPlainText())
            operation(dialog)
        except Exception as exc:
            failures.append(exc)
            dialog.reject()

    QTimer.singleShot(0, operate)
    QTest.mouseClick(window.modeling.panel.preview_button, Qt.MouseButton.LeftButton)
    pump()
    assert not failures, failures
    assert len(seen) == 1, window.modeling.panel.error.text()
    return seen[0]


@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
@pytest.mark.parametrize("profile", PROFILES)
def test_each_presentation_reviews_same_membership_then_one_apply(name, profile, tmp_path):
    session = opened(name)
    group, load, _, _ = related(session, [2])
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    before = state(session)
    edit(window, group, [2, 5])
    text = review(window, lambda dialog: QTest.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton))
    assert state(session) == before and window.modeling.active
    assert window.modeling.panel.editor.values()["node_ids"] == (2, 5)
    assert "Proposed members (2)" in text and "Unevaluated multiplier sum" in text
    review(window, lambda dialog: QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton))
    assert not window.modeling.active and session.group_members(group)["member_ids"] == [2, 5]
    assert session.document.revision == before[0] + 1
    assert not window.modeling.panel.preview_button.isVisible()
    after = state(session)
    window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
    window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
    project = tmp_path / "reviewed.caeprep"
    session.save_project(project)
    command = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(Path(sys.argv[1]).with_name('reviewed_0000.rad'))
print(json.dumps({'members':s.group_members(sys.argv[2])['member_ids'],'support':s.condition_support(sys.argv[3])['status']}))
"""
    result = json.loads(subprocess.check_output([sys.executable, "-c", command, str(project), group, load], text=True))
    assert result == {"members": [2, 5], "support": "supported"}
    assert window.close()


def test_unsupported_moment_is_visible_and_cannot_be_applied():
    session = opened("beam_shell_tet")
    group = session.create_node_group("Moment carriers", [2, 5])["card_id"]
    curve = session.create_curve("Moment curve", [(0, 0), (1, 1)])["card_id"]
    session.create_load("Rotational load", group, curve, "XX", 3)
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    before = state(session)
    edit(window, group, [2, 7])

    def blocked(dialog):
        assert not dialog.apply_button.isEnabled() and dialog.error.text()
        assert "inactive_rotation" in dialog.details.toPlainText()
        dialog.reject()

    review(window, blocked)
    assert state(session) == before and window.modeling.active
    assert window.modeling.panel.editor.values()["node_ids"] == (2, 7)
    window.modeling.cancel(); assert window.close()


def test_model_change_invalidates_visible_review_and_keeps_draft():
    session = opened("beam_shell_tet")
    group, _, _, _ = related(session, [2])
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    edit(window, group, [2, 5])

    def change(dialog):
        assert dialog.apply_button.isEnabled()
        session.create_curve("Concurrent command", [(0, 0), (1, 1)]); pump()
        assert not dialog.apply_button.isEnabled() and "model changed" in dialog.error.text().lower()
        assert session.group_members(group)["member_ids"] == [2]
        dialog.reject()

    review(window, change)
    assert window.modeling.active
    assert window.modeling.panel.editor.values()["node_ids"] == (2, 5)
    window.modeling.cancel(); assert window.close()


@pytest.mark.parametrize("name", ["beam_shell_tet", "truss_shell_hex"])
@pytest.mark.parametrize("profile", PROFILES)
def test_each_presentation_reviews_element_set_without_inventing_nodal_load_changes(name, profile, tmp_path):
    session, group, refs = element_model(name)
    nodal, load, boundary, velocity = related(session, [2])
    declarations = {card: session.card_text(card) for card in (nodal, load, boundary, velocity)}
    session.select_entity("element", refs[1]["local_id"])
    proposed = tuple(session.selection()["refs"])
    window = MainWindow(session, presentation=profile, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    before = state(session)
    edit(window, group, proposed, "element_refs")
    text = review(window, lambda dialog: QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton))
    assert "No condition in the supported reference profile targets this group" in text
    assert not window.modeling.active
    assert session.group_members(group)["members"] == refs[1:]
    assert session.document.revision == before[0] + 1
    assert all(session.card_text(card) == value for card, value in declarations.items())
    after = state(session)
    window.undo_action.trigger(); pump(); assert state(session)[1:] == before[1:]
    window.redo_action.trigger(); pump(); assert state(session)[1:] == after[1:]
    project = tmp_path / "reviewed-elements.caeprep"
    session.save_project(project)
    code = """import json,sys
from pathlib import Path
from caelab_prep.application import PrepSession
s=PrepSession();s.open_project(sys.argv[1]);s.export_rad(Path(sys.argv[1]).with_name('reviewed-elements_0000.rad'))
print(json.dumps(s.group_members(sys.argv[2])['members']))
"""
    result = json.loads(subprocess.check_output([sys.executable, "-c", code, str(project), group], text=True))
    assert result == refs[1:]
    assert window.close()


def test_unavailable_preview_preserves_existing_editor_and_explicit_apply(monkeypatch):
    session = opened("beam_shell_tet")
    group, _, _, _ = related(session, [2])
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True; window.show(); pump()
    edit(window, group, [2, 5])

    def unavailable(*args, **kwargs):
        raise PrepError("unsupported_source_profile", "This input has no complete mesh-preview reference mapping.")

    monkeypatch.setattr(session, "plan_group_members", unavailable)
    QTest.mouseClick(window.modeling.panel.preview_button, Qt.MouseButton.LeftButton); pump()
    assert "reference mapping" in window.modeling.panel.error.text()
    assert session.group_members(group)["member_ids"] == [2] and window.modeling.active
    assert window.modeling.panel.editor.values()["node_ids"] == (2, 5)
    QTest.mouseClick(window.modeling.panel.apply_button, Qt.MouseButton.LeftButton); pump()
    assert not window.modeling.active and session.group_members(group)["member_ids"] == [2, 5]
    assert window.close()
