"""Real source preview, explicit typed sharing and one-command GUI imports."""
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
from caelab_prep.radioss.modeling import material_block, shell_block
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.source_models import SourceModelsDialog

pytestmark = pytest.mark.usefixtures("qt_widgets")


def model(folder, *, mass="Mg", offset=0, unsupported=False):
    folder.mkdir()
    starter = folder / "same_0000.rad"
    starter.write_bytes(("/BEGIN\nSame name\n      2024         0\n" + f"{mass:>20}{'mm':>20}{'s':>20}\n" * 2
        + material_block(41, "Same steel", 7.8e-9, 210000, .3) + shell_block(21, "Same shell", 1)
        + "/PART/9\nSame part\n" + f"{21:10}{41:10}{0:10}\n#include mesh.inc\n"
        + ("/UNKNOWN/17\npayload\n" if unsupported else "") + "/END\n").encode())
    nodes = [(1, offset, 0), (2, 10 + offset, 0), (3, 10 + offset, 10), (4, offset, 10)]
    (folder / "mesh.inc").write_bytes(("# source comment with retained whitespace  \n/NODE\n"
        + "".join(f"{identifier:10}{x:20g}{y:20g}{0:20g}\n" for identifier, x, y in nodes)
        + "/SHELL/9\n" + "".join(f"{value:10}" for value in (77, 1, 2, 3, 4)) + "\n#enddata\n").encode())
    return starter


def state(session):
    return session.document.id, session.document.revision, session.document.tokens(), session.document.dirty


def pump_until(predicate, timeout=10):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "Source file worker did not finish"
        QTest.qWait(5)
    QApplication.processEvents()


def prepare(dialog, source):
    dialog.tabs.setCurrentIndex(0)
    dialog.source.setText(str(source))
    QTest.mouseClick(dialog.preview_button, Qt.MouseButton.LeftButton)
    pump_until(lambda: dialog._task is None)
    assert dialog._plan is not None, dialog.status.text()
    return dialog._plan


def capture(dialog, name, session):
    location = os.environ.get("CAELAB_SOURCE_CAPTURE_DIR")
    if location:
        assert QApplication.platformName() == "xcb"
        folder = Path(location)
        folder.mkdir(parents=True, exist_ok=True)
        QApplication.processEvents()
        assert dialog.screen().grabWindow(int(dialog.winId())).save(str(folder / (name + ".png")))
        (folder / (name + ".json")).write_text(json.dumps({"platform": "xcb", "dialog_size": [dialog.width(), dialog.height()],
            "source_count": len(session.source_models()), "revision": session.document.revision,
            "preview_rows": dialog.native_model.rowCount(), "shared_rows": dialog.shared_model.rowCount(),
            "status": dialog.status.text(), "scope": "Source import review; not Windows or vendor-product comparison"}))


@pytest.fixture
def owner(tmp_path):
    first, second = model(tmp_path / "base"), model(tmp_path / "independent")
    session = PrepSession()
    session.open_rad(first)
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True
    window.resize(1100, 760)
    window.show()
    QApplication.processEvents()
    yield window, session, second
    window._discard_pending_edits()
    window.close()
    QApplication.processEvents()


def dialog_for(window, session):
    dialog = SourceModelsDialog(session, window, has_draft=window.file_edits.has_draft,
                                is_busy=lambda: window._busy)
    dialog.imported.connect(lambda result: window.refresh_document())
    dialog.show()
    QApplication.processEvents()
    return dialog


def test_preview_import_independent_same_ids_one_undo_and_reopen(owner, tmp_path):
    window, session, source = owner
    original = {path.name: path.read_bytes() for path in source.parent.iterdir()}
    before = state(session)
    dialog = dialog_for(window, session)
    assert dialog.sources_model.rowCount() == 0
    plan = prepare(dialog, source)
    assert state(session) == before
    assert plan["node_count"] == 4 and plan["element_count"] == 1
    assert plan["source"]["shared_nodes"] == []
    assert dialog.files_model.rowCount() == 2
    assert dialog.native_model.rowCount() == len(plan["source"]["id_map"])
    assert any(dialog.native_model.value(row, 3) == "Collision — renumbered" for row in range(dialog.native_model.rowCount()))
    assert "0 nodes explicitly shared" in dialog.summary.text()
    assert not dialog.apply_button.isEnabled()
    capture(dialog, "independent-source-preview", session)
    events = []
    unsubscribe = session.subscribe(lambda event: events.append((event, QThread.currentThread() == window.thread())))
    dialog.reviewed.setChecked(True)
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert dialog.result is not None, dialog.status.text()
    assert session.document.revision == before[1] + 1
    assert len([event for event, _ in events if event["kind"] == "structure"]) == 1
    assert events and all(on_owner for _, on_owner in events)
    assert session.describe()["node_count"] == 8 and session.describe()["element_count"] == 2
    assert set(session.mesh_view()["cells"][0]["nodes"]).isdisjoint(session.mesh_view()["cells"][1]["nodes"])
    assert dialog.sources_model.rowCount() == 1 and dialog.archive_files_model.rowCount() == 2
    assert dialog.archive_native_model.rowCount() == len(plan["source"]["id_map"])
    capture(dialog, "imported-source-table", session)
    session.undo()
    QApplication.processEvents()
    assert session.document.tokens() == before[2] and session.describe()["node_count"] == 4
    assert dialog.sources_model.rowCount() == 0
    session.redo()
    QApplication.processEvents()
    project = tmp_path / "sources.caeprep"
    session.save_project(project)
    reopened = PrepSession()
    reopened.open_project(project)
    assert reopened.source_models() == session.source_models()
    assert reopened.describe()["node_count"] == 8
    restored = SourceModelsDialog(reopened)
    restored.show()
    assert restored.sources_model.rowCount() == 1 and restored.archive_files_model.rowCount() == 2
    restored.reject()
    assert {path.name: path.read_bytes() for path in source.parent.iterdir()} == original
    unsubscribe()
    dialog.reject()


def add_shared(dialog, original, destination):
    dialog.preview_tabs.setCurrentIndex(2)
    dialog.source_node.setText(str(original))
    dialog.destination_node.setText(str(destination))
    QTest.mouseClick(dialog.find_node_button, Qt.MouseButton.LeftButton)
    assert dialog.destination_choice.currentData()["local_id"] == destination, dialog.status.text()
    QTest.mouseClick(dialog.add_mapping_button, Qt.MouseButton.LeftButton)


def test_shared_node_requires_explicit_typed_choice_review_and_persists(owner, tmp_path):
    window, session, source = owner
    before = state(session)
    dialog = dialog_for(window, session)
    prepare(dialog, source)
    add_shared(dialog, 1, 1)
    assert dialog._plan is None and not dialog.apply_button.isEnabled()
    assert dialog.shared_model.rowCount() == 1 and state(session) == before
    reference = dialog._shared[1]
    assert reference == {"resource_id": session.mesh_view()["node_resources"][1][0], "entity_kind": "node", "local_id": 1}
    plan = prepare(dialog, source)
    assert plan["source"]["shared_nodes"] == [1]
    assert next(dialog.native_model.value(row, 3) for row in range(dialog.native_model.rowCount())
                if dialog.native_model.value(row, 0) == "NODE" and dialog.native_model.value(row, 1) == 1) == "Explicitly shared"
    capture(dialog, "explicit-shared-node-review", session)
    dialog.reviewed.setChecked(True)
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
    assert dialog.result is not None, dialog.status.text()
    cells = session.mesh_view()["cells"]
    assert set(cells[0]["nodes"]) & set(cells[1]["nodes"]) == {1}
    assert session.describe()["node_count"] == 7
    project = tmp_path / "shared.caeprep"
    session.save_project(project)
    reopened = PrepSession()
    reopened.open_project(project)
    assert reopened.source_models()[0]["shared_nodes"] == [1]
    assert reopened.describe()["node_count"] == 7
    session.undo()
    assert session.document.tokens() == before[2]
    dialog.reject()


def test_cancel_preview_and_pending_file_read_never_imports(owner):
    window, session, source = owner
    before = state(session)
    dialog = dialog_for(window, session)
    prepare(dialog, source)
    dialog.reject()
    assert state(session) == before and session.source_models() == []
    another = dialog_for(window, session)
    another.source.setText(str(source))
    assert another.prepare_preview()
    another.reject()
    pump_until(lambda: another._task is None)
    assert another._plan is None and not another.apply_import()
    assert state(session) == before and session.source_models() == []


def test_stale_review_and_replaced_owner_cannot_apply(owner, tmp_path):
    window, session, source = owner
    dialog = dialog_for(window, session)
    prepare(dialog, source)
    dialog.reviewed.setChecked(True)
    material = next(card for card in session.list_cards() if card["keyword"] == "/MAT/LAW1/41")
    session.set_field(material["id"], "young_modulus", 190000)
    QApplication.processEvents()
    assert dialog._plan is None and not dialog.apply_button.isEnabled()
    assert "changed" in dialog.status.text()
    prepare(dialog, source)
    dialog.reviewed.setChecked(True)
    session.plan_import_source(source)  # Another review supersedes the single retained plan.
    before = state(session)
    assert not dialog.apply_import()
    assert "stale_import_plan" in dialog.status.text() and state(session) == before
    prepare(dialog, source)
    project = tmp_path / "same.caeprep"
    session.save_project(project)
    session.open_project(project)
    QApplication.processEvents()
    assert dialog._plan is None and not dialog.apply_button.isEnabled()
    assert session.source_models() == []
    dialog.reject()


def test_model_draft_and_busy_guards_preserve_unapplied_input(owner):
    window, session, source = owner
    material = next(node.ref for node in window.provider.tree_nodes() if node.group == "Materials")
    window.provider.select(material)
    window.refresh_document()
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    before = state(session)
    dialog = dialog_for(window, session)
    dialog.source.setText(str(source))
    assert not dialog.prepare_preview() and "draft_pending" in dialog.status.text()
    assert editor.text() == "1e" and state(session) == before
    window._discard_pending_edits()
    window.refresh_document()
    window._busy = True
    assert not dialog.prepare_preview() and "owner_busy" in dialog.status.text()
    window._busy = False
    prepare(dialog, source)
    dialog.reviewed.setChecked(True)
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    assert not dialog.apply_import() and "draft_pending" in dialog.status.text()
    assert state(session) == before and editor.text() == "1e"
    dialog.reject()


@pytest.mark.parametrize("mass,unsupported,error", [("kg", False, "source_units_mismatch"),
    ("Mg", True, "unsupported_source_profile")])
def test_units_and_unsupported_source_fail_without_partial_changes(owner, tmp_path, mass, unsupported, error):
    window, session, _ = owner
    source = model(tmp_path / "rejected", mass=mass, unsupported=unsupported)
    before = state(session)
    dialog = dialog_for(window, session)
    dialog.source.setText(str(source))
    assert dialog.prepare_preview()
    pump_until(lambda: dialog._task is None)
    assert dialog._plan is None and error in dialog.status.text()
    assert not dialog.apply_button.isEnabled() and state(session) == before
    dialog.reject()


def test_wrong_shared_coordinates_and_unfinished_entry_are_not_silently_accepted(owner):
    window, session, source = owner
    before = state(session)
    dialog = dialog_for(window, session)
    prepare(dialog, source)
    dialog.reviewed.setChecked(True)
    dialog.source_node.setText("1")
    assert not dialog.apply_button.isEnabled()
    assert not dialog.prepare_preview() and "draft_pending" in dialog.status.text()
    dialog.clear_mapping_entry()
    add_shared(dialog, 1, 2)
    assert dialog.prepare_preview()
    pump_until(lambda: dialog._task is None)
    assert "shared_node_coordinate_mismatch" in dialog.status.text()
    assert dialog.shared_model.rowCount() == 1 and state(session) == before
    assert not dialog.apply_button.isEnabled()
    dialog.shared_table.selectRow(0)
    QTest.mouseClick(dialog.remove_mapping_button, Qt.MouseButton.LeftButton)
    assert dialog.shared_model.rowCount() == 0
    plan = prepare(dialog, source)
    assert plan["source"]["shared_nodes"] == []
    dialog.reject()


@pytest.mark.parametrize("reject_first", [False, True])
def test_dispose_pending_source_preview_releases_subscription_without_import(owner, reject_first):
    from shiboken6 import isValid

    window, session, source = owner
    before, listeners = state(session), len(session._listeners)
    dialog = dialog_for(window, session)
    dialog.source.setText(str(source))
    assert dialog.prepare_preview()
    assert len(session._listeners) == listeners + 1
    if reject_first:
        dialog.reject()
        assert len(session._listeners) == listeners
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(dialog) and len(session._listeners) == listeners
    pump_until(lambda: QThreadPool.globalInstance().activeThreadCount() == 0)
    assert state(session) == before and session.source_models() == []


def review_instance(dialog, name, source_id=None):
    dialog.tabs.setCurrentIndex(2)
    dialog.instance_name.setText(name)
    index = dialog.instance_source.findData(source_id)
    assert index >= 0
    dialog.instance_source.setCurrentIndex(index)
    dialog.instance_acknowledged.setChecked(True)
    assert dialog.create_instance_button.isEnabled()


def create_instance(dialog, name, source_id=None):
    review_instance(dialog, name, source_id)
    QTest.mouseClick(dialog.create_instance_button, Qt.MouseButton.LeftButton)
    assert dialog.instance_result is not None, dialog.status.text()
    return dialog.instance_result["instance_id"]


def capture_instances(dialog, session):
    location = os.environ.get("CAELAB_SOURCE_CAPTURE_DIR")
    if location:
        assert QApplication.platformName() == "xcb"
        folder = Path(location)
        folder.mkdir(parents=True, exist_ok=True)
        QApplication.processEvents()
        assert dialog.screen().grabWindow(int(dialog.winId())).save(str(folder / "instance-reference-metadata.png"))
        (folder / "instance-reference-metadata.json").write_text(json.dumps({"platform": "xcb",
            "dialog_size": [dialog.width(), dialog.height()], "source_count": len(session.source_models()),
            "instance_count": len(session.instance_references()), "node_count": session.describe()["node_count"],
            "status": dialog.status.text(), "scope": "Unexpanded reference metadata only; no placement or native geometry expansion"}))


def test_instance_reference_metadata_separate_from_archives_one_undo_save_reopen(owner, tmp_path):
    window, session, source = owner
    dialog = dialog_for(window, session)
    prepare(dialog, source)
    dialog.reviewed.setChecked(True)
    QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
    source_id = session.source_models()[0]["id"]
    mesh = session.mesh_view()
    raws = {rid: resource.raw for rid, resource in session.document.resources.items() if hasattr(resource, "raw")}
    prepare(dialog, source)
    dialog.reviewed.setChecked(True)
    before = state(session)
    events, signals = [], []
    unsubscribe = session.subscribe(lambda event: events.append((event, QThread.currentThread() == window.thread())))
    dialog.changed.connect(signals.append)
    base = create_instance(dialog, "Same reference name")
    assert session.document.revision == before[1] + 1
    assert len(events) == 1 and events[0][0]["kind"] == "model_relation" and events[0][1]
    assert len(signals) == 1 and signals[0]["instance_id"] == base
    assert dialog._plan is None and not dialog.apply_button.isEnabled()
    assert session.instance_references()[0]["source_id"] is None
    session.undo()
    assert session.document.tokens() == before[2] and session.instance_references() == []
    session.redo()
    first = create_instance(dialog, "Same reference name", source_id)
    second = create_instance(dialog, "Same reference name", source_id)
    rows = session.instance_references()
    assert len({base, first, second}) == 3
    assert [item["source_id"] for item in rows] == [None, source_id, source_id]
    assert rows[1]["resource_ids"] == rows[2]["resource_ids"]
    assert {item["status"] for item in rows} == {"not-expanded"}
    assert dialog.sources_model.rowCount() == 1 and dialog.instances_model.rowCount() == 3
    assert dialog.instance_resources_model.rowCount() == 2
    assert session.mesh_view()["cells"] is mesh["cells"] and session.describe()["node_count"] == 8
    assert all(session.document.resources[rid].raw is raw for rid, raw in raws.items())
    assert not dialog.apply_button.isVisible() and not dialog.reviewed.isVisible()
    assert window.undo_action.isEnabled()  # The canonical host observes model_relation events.
    capture_instances(dialog, session)
    with pytest.raises(PrepError) as error:
        session.export_solver_inputs(tmp_path / "blocked_0000.rad", 1e-5, 1e-6)
    assert error.value.code == "unexpanded_instances" and not (tmp_path / "blocked_0000.rad").exists()
    project = tmp_path / "instance-references.caeprep"
    session.save_project(project)
    reopened = PrepSession()
    reopened.open_project(project)
    assert reopened.instance_references() == rows
    restored = SourceModelsDialog(reopened)
    restored.show()
    restored.tabs.setCurrentIndex(2)
    assert restored.instances_model.rowCount() == 3 and restored.sources_model.rowCount() == 1
    restored.instances_table.selectRow(1)
    assert restored.instance_resources_model.rowCount() == 2
    restored.reject()
    dialog.instances_table.selectRow(1)
    before_delete = state(session)
    QTest.mouseClick(dialog.delete_instance_button, Qt.MouseButton.LeftButton)
    assert [item["id"] for item in session.instance_references()] == [base, second]
    assert session.document.revision == before_delete[1] + 1
    session.undo()
    assert session.document.tokens() == before_delete[2] and session.instance_references() == rows
    session.redo()
    for _ in range(2):
        dialog.instances_table.selectRow(0)
        QTest.mouseClick(dialog.delete_instance_button, Qt.MouseButton.LeftButton)
    assert session.instance_references() == [] and dialog.instances_model.rowCount() == 0
    assert len(session.source_models()) == 1 and session.mesh_view()["cells"] is mesh["cells"]
    session.export_solver_inputs(tmp_path / "restored_0000.rad", 1e-5, 1e-6)
    assert (tmp_path / "restored_0000.rad").exists()
    unsubscribe()
    dialog.reject()


def test_instance_reference_review_invalidated_by_input_revision_and_document_epoch(owner, tmp_path):
    window, session, _ = owner
    dialog = dialog_for(window, session)
    review_instance(dialog, "Uncommitted")
    dialog.instance_name.setText("Changed name")
    assert not dialog.instance_acknowledged.isChecked() and not dialog.create_instance_button.isEnabled()
    assert not dialog.create_instance_reference() and session.instance_references() == []
    review_instance(dialog, "Reviewed")
    session.select_entity("node", 1)
    QApplication.processEvents()
    assert dialog.instance_acknowledged.isChecked()  # Selection alone does not stale document metadata.
    material = next(card for card in session.list_cards() if card["keyword"] == "/MAT/LAW1/41")
    session.set_field(material["id"], "young_modulus", 190000)
    QApplication.processEvents()
    before = state(session)
    assert dialog.instance_name.text() == "Reviewed" and not dialog.instance_acknowledged.isChecked()
    assert not dialog.create_instance_reference() and state(session) == before
    identifier = create_instance(dialog, "Persisted")
    dialog.instances_table.selectRow(0)
    assert dialog.delete_instance_button.isEnabled()
    session.set_field(material["id"], "young_modulus", 180000)
    QApplication.processEvents()
    before = state(session)
    assert not dialog.delete_instance_button.isEnabled()
    assert not dialog.delete_instance_reference() and state(session) == before
    review_instance(dialog, "Old document review")
    dialog.instances_table.selectRow(0)
    project = tmp_path / "same-instance-document.caeprep"
    session.save_project(project)
    session.open_project(project)
    QApplication.processEvents()
    before = state(session)
    assert not dialog.create_instance_button.isEnabled() and not dialog.delete_instance_button.isEnabled()
    assert not dialog.create_instance_reference() and not dialog.delete_instance_reference()
    assert state(session) == before and session.instance_references()[0]["id"] == identifier
    dialog.reject()


def test_instance_reference_draft_busy_pending_read_and_cancel_do_not_commit(owner):
    window, session, source = owner
    dialog = dialog_for(window, session)
    before = state(session)
    review_instance(dialog, "Uncommitted")
    window._busy = True
    assert not dialog.create_instance_reference() and "owner_busy" in dialog.status.text()
    window._busy = False
    material = next(node.ref for node in window.provider.tree_nodes() if node.group == "Materials")
    window.provider.select(material)
    window.refresh_document()
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    assert not dialog.create_instance_reference() and "draft_pending" in dialog.status.text()
    assert editor.text() == "1e" and state(session) == before
    window._discard_pending_edits()
    dialog.source.setText(str(source))
    assert dialog.prepare_preview()
    assert not dialog.create_instance_button.isEnabled()
    assert not dialog.create_instance_reference() and state(session) == before
    pump_until(lambda: dialog._task is None)
    dialog.reject()
    assert not dialog.create_instance_reference() and state(session) == before
    assert session.instance_references() == []


def test_instance_reference_delete_preserves_host_draft_and_does_not_omit_other_reference(owner):
    window, session, _ = owner
    dialog = dialog_for(window, session)
    first = create_instance(dialog, "First")
    second = create_instance(dialog, "Second")
    dialog.instances_table.selectRow(0)
    before = state(session)
    window._busy = True
    assert not dialog.delete_instance_reference() and "owner_busy" in dialog.status.text()
    window._busy = False
    material = next(node.ref for node in window.provider.tree_nodes() if node.group == "Materials")
    window.provider.select(material)
    window.refresh_document()
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    assert not dialog.delete_instance_reference() and "draft_pending" in dialog.status.text()
    assert state(session) == before and editor.text() == "1e"
    window._discard_pending_edits()
    assert dialog.delete_instance_reference(), dialog.status.text()
    assert [item["id"] for item in session.instance_references()] == [second]
    session.undo()
    assert [item["id"] for item in session.instance_references()] == [first, second]
    dialog.reject()
