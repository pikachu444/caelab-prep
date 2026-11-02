"""Actual prepared mesh review and typed stale-target reconnection through Qt."""
import json
import os
from pathlib import Path
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QThread, QThreadPool, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.source_models import PreparedMeshDialog

pytestmark = pytest.mark.usefixtures("qt_widgets")
SOURCE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies/beam_shell_tet/model_0000.rad"


def wait_for_read(dialog):
    deadline = time.monotonic() + 10
    while dialog._task is not None:
        assert time.monotonic() < deadline, "Prepared mesh read did not finish"
        QTest.qWait(5)
    QApplication.processEvents()


def state(session):
    return session.document.id, session.document.revision, session.document.tokens(), session.document.dirty


def prepared_file(tmp_path, same_ids=True):
    lines = (SOURCE.parent / "mesh.inc").read_text().splitlines()
    family = None
    for index, line in enumerate(lines):
        if line.startswith("/"):
            family = line.split("/")[1]
        elif line and not line.startswith("#"):
            if family == "NODE":
                identifier = int(line[:10])
                xyz = [float(line[start:start + 20]) for start in (10, 30, 50)]
                lines[index] = f"{identifier if same_ids else identifier + 100:10}" + "".join(f"{value + 2:20g}" for value in xyz)
            elif family in ("BEAM", "SHELL", "TETRA4") and not same_ids:
                values = [int(line[start:start + 10]) for start in range(0, len(line), 10)]
                lines[index] = f"{values[0] + 1000:10}" + "".join(f"{value + 100:10}" for value in values[1:])
    path = tmp_path / "prepared.inc"
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture
def owner(request, tmp_path):
    source = SOURCE
    if getattr(request, "param", None) == "explicit_unit_zero":
        source = tmp_path / "unit_zero_0000.rad"
        source.write_bytes(SOURCE.read_bytes().replace(b"/PART/9\n", b"/PART/9/0\n"))
        (tmp_path / "mesh.inc").write_bytes((SOURCE.parent / "mesh.inc").read_bytes())
    session = PrepSession()
    session.open_rad(source)
    mesh = next(resource for resource in session.document.resources.values() if getattr(resource, "is_include", False))
    group = session.create_node_group("Original nodes", [1, 2])["card_id"]
    elements = session.create_element_group("Original shell", [{"resource_id": mesh.id, "entity_kind": "element", "local_id": 77}])["card_id"]
    part = session.resolve_part_reference(9)["card_id"]
    surface = session.create_surface("Original part surface", [part])["card_id"]
    contact = session.create_contact("Affected contact", group, surface, .1)["card_id"]
    case = session.create_analysis_case("Replacement case", [contact], 1e-6, 5e-7, "s")["case_id"]
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True
    window.resize(1100, 800)
    window.show()
    QApplication.processEvents()
    yield window, session, mesh, dict(group=group, elements=elements, surface=surface, contact=contact, case=case, part=part)
    window._discard_pending_edits()
    window.close()
    QApplication.processEvents()


def dialog_for(window, session):
    dialog = PreparedMeshDialog(session, window, has_draft=window.file_edits.has_draft, is_busy=lambda: window._busy)
    dialog.changed.connect(lambda result: window.refresh_document())
    dialog.show()
    QApplication.processEvents()
    return dialog


def preview(dialog, path):
    dialog.tabs.setCurrentIndex(0)
    dialog.source.setText(str(path))
    QTest.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
    wait_for_read(dialog)
    assert dialog._plan is not None, dialog.status.text()
    return dialog._plan


def replace(dialog, path):
    preview(dialog, path)
    dialog.replacement_reviewed.setChecked(True)
    QTest.mouseClick(dialog.replace_button, Qt.MouseButton.LeftButton)
    assert dialog.last_result is not None, dialog.status.text()


def choose_group(dialog, identifier):
    dialog.tabs.setCurrentIndex(1)
    index = dialog.target_group.findData(identifier)
    assert index >= 0
    dialog.target_group.setCurrentIndex(index)


def link(dialog, original, current):
    dialog.reconnect_table.selectRow(dialog.reconnect_model.rows.index(original))
    dialog.current_target.setText(str(current))
    QTest.mouseClick(dialog.find_target_button, Qt.MouseButton.LeftButton)
    reference = dialog.target_choice.currentData()
    assert reference is not None, dialog.status.text()
    QTest.mouseClick(dialog.link_button, Qt.MouseButton.LeftButton)
    assert original in dialog._mapping, dialog.status.text()
    return reference


def capture(dialog, name, session):
    location = os.environ.get("CAELAB_SOURCE_CAPTURE_DIR")
    if location:
        assert QApplication.platformName() == "xcb"
        folder = Path(location)
        folder.mkdir(parents=True, exist_ok=True)
        QApplication.processEvents()
        assert dialog.screen().grabWindow(int(dialog.winId())).save(str(folder / (name + ".png")))
        (folder / (name + ".json")).write_text(json.dumps({"platform": "xcb", "dialog_size": [dialog.width(), dialog.height()],
            "stale_groups": len(session.mesh_relationships()["stale_targets"]), "revision": session.document.revision,
            "explicit_links": len(dialog._mapping), "status": dialog.status.text(),
            "scope": "Prepared mesh replacement and explicit reconnection; not mesher generation or Windows proof"}))


@pytest.mark.parametrize("same_ids", [False, True])
def test_real_replacement_stales_even_same_ids_explicit_links_undo_save_reopen(owner, tmp_path, same_ids):
    window, session, mesh, ids = owner
    path = prepared_file(tmp_path, same_ids)
    original = state(session)
    original_mesh, original_raw = mesh.render(), mesh.raw
    dialog = dialog_for(window, session)
    plan = preview(dialog, path)
    assert state(session) == original
    assert set(plan["stale_targets"]) == {ids[key] for key in ("group", "elements", "surface")}
    assert dialog.targets_model.rowCount() == 3 and not dialog.replace_button.isEnabled()
    if same_ids:
        capture(dialog, "prepared-mesh-preview", session)
    events = []
    unsubscribe = session.subscribe(lambda event: events.append((event, QThread.currentThread() == window.thread())))
    dialog.replacement_reviewed.setChecked(True)
    QTest.mouseClick(dialog.replace_button, Qt.MouseButton.LeftButton)
    assert session.document.revision == original[1] + 1
    assert len([event for event, _ in events if event["kind"] == "structure"]) == 1
    assert all(on_owner for _, on_owner in events)
    assert mesh.raw is original_raw and mesh.render() != original_mesh
    assert dialog.conditions_model.rowCount() == 1 and dialog.target_group.count() == 3
    assert not dialog._mapping and not dialog.reconnect_button.isEnabled()
    if same_ids:
        capture(dialog, "stale-mesh-targets", session)
    project = tmp_path / "stale.caeprep"
    session.save_project(project)
    reopened = PrepSession()
    reopened.open_project(project)
    restored = PreparedMeshDialog(reopened)
    restored.show()
    assert restored.target_group.count() == 3 and not restored._mapping
    assert reopened.mesh_relationships()["stale_targets"] == session.mesh_relationships()["stale_targets"]
    restored.reject()
    with pytest.raises(PrepError) as error:
        session.export_analysis_case(tmp_path / "blocked_0000.rad", ids["case"])
    assert error.value.code == "stale_mesh_targets"
    delta = 0 if same_ids else 100
    choose_group(dialog, ids["group"])
    first = link(dialog, 1, 1 + delta)
    assert first == {"resource_id": mesh.id, "entity_kind": "node", "local_id": 1 + delta}
    assert not dialog.reconnect_button.isEnabled()
    link(dialog, 2, 2 + delta)
    assert not dialog.reconnect_button.isEnabled()
    if same_ids:
        capture(dialog, "explicit-current-mesh-links", session)
    dialog.reconnect_reviewed.setChecked(True)
    before_apply, event_count = state(session), len(events)
    QTest.mouseClick(dialog.reconnect_button, Qt.MouseButton.LeftButton)
    assert session.document.revision == before_apply[1] + 1
    assert len(events) == event_count + 1 and events[-1][0]["kind"] == "structure"
    assert set(session.mesh_relationships()["stale_targets"]) == {ids["elements"], ids["surface"]}
    assert session.group_members(ids["group"])["member_ids"] == [1 + delta, 2 + delta]
    session.undo()
    assert session.document.tokens() == before_apply[2] and ids["group"] in session.mesh_relationships()["stale_targets"]
    session.redo()
    choose_group(dialog, ids["elements"])
    reference = link(dialog, 77, 77 if same_ids else 1077)
    assert reference["entity_kind"] == "element" and reference["resource_id"] == mesh.id
    dialog.reconnect_reviewed.setChecked(True)
    assert dialog.apply_reconnection(), dialog.status.text()
    choose_group(dialog, ids["surface"])
    assert link(dialog, 9, 9) == ids["part"]
    dialog.reconnect_reviewed.setChecked(True)
    assert dialog.apply_reconnection(), dialog.status.text()
    assert not session.mesh_relationships()["stale_targets"] and dialog.target_group.count() == 0
    session.export_analysis_case(tmp_path / "out" / "connected_0000.rad", ids["case"])
    session.save_project(project)
    reopened.open_project(project)
    assert reopened.mesh_relationships()["stale_targets"] == {}
    assert reopened.group_members(ids["group"])["member_ids"] == [1 + delta, 2 + delta]
    for _ in range(3):
        session.undo()
    assert len(session.mesh_relationships()["stale_targets"]) == 3
    session.undo()
    assert mesh.render() == original_mesh and session.document.tokens() == original[2]
    assert not session.mesh_relationships()["stale_targets"]
    unsubscribe()
    dialog.reject()


def test_cancel_ready_or_running_replacement_and_unsupported_file_leave_model_unchanged(owner, tmp_path):
    window, session, _, _ = owner
    before = state(session)
    path = prepared_file(tmp_path)
    dialog = dialog_for(window, session)
    preview(dialog, path)
    dialog.reject()
    assert not dialog.apply_replacement() and state(session) == before
    running = dialog_for(window, session)
    running.source.setText(str(path))
    assert running.prepare_preview()
    running.reject()
    wait_for_read(running)
    assert running._plan is None and state(session) == before
    invalid = tmp_path / "unsupported.inc"
    invalid.write_text("/INCLUDE\nother.inc\n")
    rejected = dialog_for(window, session)
    rejected.source.setText(str(invalid))
    assert rejected.prepare_preview()
    wait_for_read(rejected)
    assert rejected._plan is None and "unsupported_mesh_replacement" in rejected.status.text()
    assert state(session) == before and not rejected.replace_button.isEnabled()
    rejected.reject()


def test_stale_plan_epoch_and_open_model_draft_busy_preserve_changes(owner, tmp_path):
    window, session, mesh, ids = owner
    dialog = dialog_for(window, session)
    path = prepared_file(tmp_path)
    preview(dialog, path)
    dialog.replacement_reviewed.setChecked(True)
    session.set_analysis_case(ids["case"], {"name": "Other edit"})
    QApplication.processEvents()
    assert dialog._plan is None and not dialog.replace_button.isEnabled()
    preview(dialog, path)
    dialog.replacement_reviewed.setChecked(True)
    session.plan_mesh_replacement(mesh.id, path)
    before = state(session)
    assert not dialog.apply_replacement() and "stale_mesh_replacement_plan" in dialog.status.text()
    assert state(session) == before
    preview(dialog, path)
    project = tmp_path / "reopen.caeprep"
    session.save_project(project)
    session.open_project(project)
    QApplication.processEvents()
    assert dialog._plan is None
    material = next(node.ref for node in window.provider.tree_nodes() if node.group == "Materials")
    window.provider.select(material)
    window.refresh_document()
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    before = state(session)
    assert not dialog.prepare_preview() and "draft_pending" in dialog.status.text()
    assert state(session) == before and editor.text() == "1e"
    window._discard_pending_edits()
    window._busy = True
    assert not dialog.prepare_preview() and "owner_busy" in dialog.status.text()
    window._busy = False
    preview(dialog, path)
    dialog.replacement_reviewed.setChecked(True)
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    assert not dialog.apply_replacement() and "draft_pending" in dialog.status.text()
    assert state(session) == before and editor.text() == "1e"
    dialog.reject()


def test_partial_unfinished_wrong_family_and_stale_reconnect_never_partially_commit(owner, tmp_path):
    window, session, _, ids = owner
    dialog = dialog_for(window, session)
    replace(dialog, prepared_file(tmp_path))
    choose_group(dialog, ids["group"])
    before = state(session)
    link(dialog, 1, 1)
    dialog.reconnect_reviewed.setChecked(True)
    assert not dialog.apply_reconnection() and state(session) == before
    link(dialog, 2, 2)
    dialog.reconnect_reviewed.setChecked(True)
    dialog.current_target.setText("3")
    assert not dialog.reconnect_button.isEnabled()
    assert not dialog.apply_reconnection() and state(session) == before
    dialog._clear_entry()
    session.set_analysis_case(ids["case"], {"name": "New revision"})
    QApplication.processEvents()
    assert not dialog._mapping and not dialog.reconnect_button.isEnabled()
    before = state(session)
    assert not dialog.apply_reconnection() and state(session) == before
    choose_group(dialog, ids["elements"])
    wrong = next(cell for cell in session.mesh_view()["cells"] if cell.get("formulation") == "TETRA4")
    link(dialog, 77, wrong["id"])
    dialog.reconnect_reviewed.setChecked(True)
    assert not dialog.apply_reconnection() and "incompatible_group" in dialog.status.text()
    assert state(session) == before and len(session.mesh_relationships()["stale_targets"]) == 3
    link(dialog, 77, 77)
    dialog.reconnect_reviewed.setChecked(True)
    assert dialog.apply_reconnection(), dialog.status.text()
    assert len(session.mesh_relationships()["stale_targets"]) == 2
    choose_group(dialog, ids["group"])
    link(dialog, 1, 1)
    link(dialog, 2, 2)
    project = tmp_path / "same-handle.caeprep"
    session.save_project(project)
    session.open_project(project)
    QApplication.processEvents()
    assert not dialog._mapping and not dialog.reconnect_button.isEnabled()
    dialog.reject()


def test_reconnect_draft_busy_and_cancel_preserve_model_and_local_review(owner, tmp_path):
    window, session, _, ids = owner
    dialog = dialog_for(window, session)
    replace(dialog, prepared_file(tmp_path))
    choose_group(dialog, ids["group"])
    link(dialog, 1, 1)
    link(dialog, 2, 2)
    dialog.reconnect_reviewed.setChecked(True)
    before = state(session)
    window._busy = True
    assert not dialog.apply_reconnection() and "owner_busy" in dialog.status.text()
    assert state(session) == before and len(dialog._mapping) == 2
    window._busy = False
    material = next(node.ref for node in window.provider.tree_nodes() if node.group == "Materials")
    window.provider.select(material)
    window.refresh_document()
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    assert not dialog.apply_reconnection() and "draft_pending" in dialog.status.text()
    assert state(session) == before and editor.text() == "1e" and len(dialog._mapping) == 2
    dialog.reject()
    assert not dialog.apply_reconnection() and state(session) == before
    assert len(session.mesh_relationships()["stale_targets"]) == 3


@pytest.mark.parametrize("reject_first", [False, True])
def test_dispose_pending_prepared_read_releases_subscription_without_replacement(owner, tmp_path, reject_first):
    from shiboken6 import isValid

    window, session, _, _ = owner
    before, listeners = state(session), len(session._listeners)
    dialog = dialog_for(window, session)
    dialog.source.setText(str(prepared_file(tmp_path)))
    assert dialog.prepare_preview()
    assert len(session._listeners) == listeners + 1
    if reject_first:
        dialog.reject()
        assert len(session._listeners) == listeners
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(dialog) and len(session._listeners) == listeners
    deadline = time.monotonic() + 10
    while QThreadPool.globalInstance().activeThreadCount():
        assert time.monotonic() < deadline
        QTest.qWait(5)
    QApplication.processEvents()
    assert state(session) == before and not session.mesh_relationships()["stale_targets"]


@pytest.mark.parametrize("owner", ["explicit_unit_zero"], indirect=True)
def test_explicit_zero_unit_part_resolves_for_real_surface_reconnection(owner, tmp_path):
    window, session, _, ids = owner
    assert next(card for card in session.list_cards() if card["id"] == ids["part"])["keyword"] == "/PART/9/0"
    dialog = dialog_for(window, session)
    replace(dialog, prepared_file(tmp_path))
    choose_group(dialog, ids["surface"])
    before = state(session)
    assert link(dialog, 9, 9) == ids["part"]
    assert state(session) == before
    dialog.reconnect_reviewed.setChecked(True)
    assert dialog.apply_reconnection(), dialog.status.text()
    assert ids["surface"] not in session.mesh_relationships()["stale_targets"]
    assert len(session.mesh_relationships()["stale_targets"]) == 2
    session.undo()
    assert state(session)[2] == before[2] and ids["surface"] in session.mesh_relationships()["stale_targets"]
    dialog.reject()
