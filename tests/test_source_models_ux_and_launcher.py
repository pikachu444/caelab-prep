"""Source and reference display labels and the Windows launcher entry point."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def test_source_and_instance_labels_hide_internal_ids(tmp_path, request):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from caelab_prep.application import PrepSession
    from caelab_prep.ui.source_models import SourceModelsDialog
    from test_source_models_ui import create_instance, model

    request.getfixturevalue("qt_widgets")
    session = PrepSession()
    session.open_rad(model(tmp_path / "base"))
    for offset in (20, 40):
        plan = session.plan_import_source(model(tmp_path / f"source-{offset}", offset=offset))
        session.import_source(plan["plan_id"])
    first, second = session.source_models()
    dialog = SourceModelsDialog(session)
    dialog.show()
    assert dialog.instance_root.text() == "Select a reference to inspect its linked resources."

    dialog.tabs.setCurrentIndex(1)
    dialog.sources_table.selectRow(0)
    assert dialog.archive_native_model.rowCount() == len(first["id_map"])
    assert [dialog.archive_files_model.value(row, 1) for row in range(dialog.archive_files_model.rowCount())] == [
        item["logical_path"] for item in first["files"]
    ]

    combo = dialog.instance_source
    source_label = f"Imported source: {first['name']}"
    assert first["name"] == second["name"]
    assert [combo.itemText(row) for row in range(combo.count())] == ["Base model", source_label, source_label]
    assert [combo.itemData(row) for row in range(combo.count())] == [None, first["id"], second["id"]]
    assert dialog._instance_source_label("missing-source-id") == "Unresolved source"
    assert dialog._resource_label("missing-resource-id") == "Unnamed resource"

    base_id = create_instance(dialog, "Base reference")
    instance_id = create_instance(dialog, "Source reference", first["id"])
    references = session.instance_references()
    record = references[1]
    assert record["id"] == instance_id and record["source_id"] == first["id"]
    names = [session.document.resources[rid].name for rid in record["resource_ids"]]
    assert dialog.instance_root.text() == f"Root resource: {session.document.resources[record['root_resource_id']].name}"
    assert dialog.instance_resources_model.rowCount() == len(names) == 2

    expected = (
        (dialog.sources_model, ("Source name", "Files", "Native IDs", "Shared nodes"),
         [(source["name"], len(source["files"]), len(source["id_map"]), len(source["shared_nodes"]))
          for source in (first, second)]),
        (dialog.instances_model, ("Reference name", "Referenced source", "Status", "Resources"),
         [("Base reference", "Base model", "not-expanded", len(references[0]["resource_ids"])),
          ("Source reference", source_label, "not-expanded", len(names))]),
        (dialog.instance_resources_model, ("Referenced resource",), [(name,) for name in names]),
    )
    visible = [dialog.instance_root.text(), *(combo.itemText(row) for row in range(combo.count()))]
    for table_model, headers, rows in expected:
        shown_headers = tuple(table_model.headerData(col, Qt.Orientation.Horizontal)
                              for col in range(table_model.columnCount()))
        shown_rows = [tuple(table_model.index(row, col).data() for col in range(table_model.columnCount()))
                      for row in range(table_model.rowCount())]
        assert shown_headers == headers
        assert shown_rows == [tuple(map(str, row)) for row in rows]
        visible.extend(shown_headers)
        visible.extend(cell for row in shown_rows for cell in row)
    assert {"Source identity", "Instance identity", "Resource identity"}.isdisjoint(visible)
    source_ids = (first["id"], second["id"])
    assert all(identifier not in combo.itemText(row) for identifier in source_ids for row in range(combo.count()))
    identifiers = (*source_ids, base_id, instance_id, *record["resource_ids"], *references[0]["resource_ids"])
    assert set(identifiers).isdisjoint(visible)
    assert all(f"({identifier})" not in label for identifier in identifiers for label in visible)

    dialog.instances_table.selectRow(1)
    QTest.mouseClick(dialog.delete_instance_button, Qt.MouseButton.LeftButton)
    assert session.instance_references() == references[:1]
    assert dialog.instances_model.rowCount() == 1 and dialog.instance_resources_model.rowCount() == 0
    session.undo()
    assert session.instance_references() == references
    dialog.instances_table.selectRow(1)
    assert dialog.instance_resources_model.rowCount() == len(names)
    session.redo()
    assert session.instance_references() == references[:1]
    assert dialog.instances_model.rowCount() == 1 and dialog.instance_resources_model.rowCount() == 0
    dialog.reject()


def test_windows_batch_points_to_launcher():
    root = Path(__file__).resolve().parents[1]
    batch = (root / "CAELab_Prep_Install_And_Run.bat").read_text(encoding="ascii")
    assert r'-File "%~dp0scripts\install_and_run_prep.ps1" %*' in batch


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell launcher")
def test_windows_launcher_dry_run_does_not_create_environment(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "checkout with spaces" / "scripts"
    scripts.mkdir(parents=True)
    script = Path(shutil.copyfile(root / "scripts/install_and_run_prep.ps1", scripts / "install_and_run_prep.ps1"))
    powershell = Path(os.environ["SystemRoot"], "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    monkeypatch.setenv("PATH", str(tmp_path))
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-DryRun", "-CreateShortcut", "-ForceReinstall"],
        cwd=tmp_path, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"Dry run: CAELab Prep" in result.stdout
    assert b"Would reinstall .[gui,cad]." in result.stdout
    assert b"Would create CAELab Prep.lnk" in result.stdout
    assert not (scripts.parent / ".venv").exists()
