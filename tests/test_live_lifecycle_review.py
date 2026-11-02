"""Independent live-GUI lifecycle regressions using the real mesher and CLI.

The generation buttons stay usable after an IPC-started operation. Their later
workers must remain owned and cancellable rather than disappearing behind a
cached successful job receipt.
"""
import os

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from test_live_gui import owner as _owner_fixture, call, pump_until

pytestmark = pytest.mark.usefixtures("qt_widgets")


@pytest.fixture
def owner(qt_widgets, tmp_path):
    # Make the Qt ownership baseline precede the autouse worker-reaping fixture.
    yield from _owner_fixture.__wrapped__(tmp_path)


@pytest.fixture(autouse=True)
def _reap_even_untracked_workers(owner):
    yield
    # A failing lifecycle assertion must not destroy the real owner while the
    # defect leaves a later worker outside active_jobs.
    window = owner[0]
    dialogs = [job["dialog"] for job in window._live_control._jobs.values()]
    for dialog in dialogs:
        if dialog._task is not None and not dialog._adopting:
            dialog._cancel.set()
    pump_until(lambda: all(dialog._task is None for dialog in dialogs), timeout=30)


def _box(tmp_path):
    from test_gmsh_adapter import require_sdk
    require_sdk()
    pytest.importorskip("OCP")
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    writer = STEPControl_Writer()
    writer.Transfer(BRepPrimAPI_MakeBox(10, 10, 10).Shape(), STEPControl_AsIs)
    source = tmp_path / "independent-box.step"
    assert int(writer.Write(str(source))) == 1
    return source


def _completed_candidate(owner, tmp_path, dimension):
    window, session, connection = owner
    handle = call(connection)["handle"]
    job = call(connection, "mesh.start", {
        "handle": handle, "source": str(_box(tmp_path)), "output": str(tmp_path / "first-candidate"),
        "size": 4, "dimension": dimension,
    })
    pump_until(lambda: not window.live_ipc_status()["active_jobs"], timeout=40)
    completed = call(connection, "jobs.get", {"job_id": job["id"]})
    assert completed["status"] == "succeeded" and completed["result"]["adopted"] is False
    assert completed["generation"] == 1 and completed["operation"] == "candidate"
    dialog = window._live_control._jobs[job["id"]]["dialog"]
    return job, dialog


def test_gui_regeneration_remains_queryable_cancellable_and_owned_during_stop(owner, tmp_path):
    window, session, connection = owner
    before = session.document.tokens(), session.document.revision
    job, dialog = _completed_candidate(owner, tmp_path, 3)
    # The dialog's existing Open saved candidate path runs the actual reader.
    # It must update the same workflow receipt without inventing another job.
    mesh_uuid = dialog.candidate.mesh_uuid
    metadata = next(asset.path for asset in dialog.candidate.assets if asset.kind == "metadata")
    assert dialog.open_candidate(metadata)
    assert job["id"] in window.live_ipc_status()["active_jobs"]
    pump_until(lambda: not window.live_ipc_status()["active_jobs"], timeout=30)
    reopened = call(connection, "jobs.get", {"job_id": job["id"]})
    assert reopened["generation"] == 2 and reopened["status"] == "succeeded"
    assert reopened["result"]["mesh_uuid"] == mesh_uuid
    dialog.size.setText(".02")
    dialog.output.setText(str(tmp_path / "gui-regeneration"))
    dialog.generate_button.click()
    assert dialog._task is not None
    queried = call(connection, "jobs.get", {"job_id": job["id"]})
    assert queried["status"] == "running"
    assert queried["generation"] == 3 and queried["cancellable"] is True
    assert job["id"] in window.live_ipc_status()["active_jobs"]
    cancelled = call(connection, "jobs.cancel", {"job_id": job["id"], "cancel_token": job["cancel_token"]})
    assert cancelled["status"] in ("cancel_requested", "cancelled")
    pump_until(lambda: not window.live_ipc_status()["active_jobs"], timeout=30)
    cancelled = call(connection, "jobs.get", {"job_id": job["id"]})
    assert cancelled["status"] == "cancelled" and dialog._task is None
    details = cancelled["error"]["details"]
    assert details["returncode"] is not None
    if os.name == "posix":
        with pytest.raises(ProcessLookupError): os.kill(details["pid"], 0)

    # A further GUI generation also participates in connection shutdown.
    dialog.output.setText(str(tmp_path / "stop-regeneration"))
    dialog.generate_button.click()
    assert dialog._task is not None
    assert window.stop_live_ipc() is False
    assert connection.exists()
    pump_until(lambda: window.live_ipc_status()["status"] == "closed", timeout=30)
    assert dialog._task is None and not connection.exists()
    assert (session.document.tokens(), session.document.revision) == before


def test_gui_adoption_cannot_be_reported_cancelled_or_outlive_owner_stop(owner, tmp_path):
    window, session, connection = owner
    job, dialog = _completed_candidate(owner, tmp_path, 2)
    before = session.document.revision
    assert dialog.adopt_button.isEnabled()
    assert dialog.material.count() > 1 and dialog.section.count() > 1
    dialog.material.setCurrentIndex(1)
    dialog.section.setCurrentIndex(1)
    dialog.adopt_button.click()
    assert dialog._task is not None and dialog._adopting
    assert window.stop_live_ipc() is False
    assert connection.exists()
    pump_until(lambda: window.live_ipc_status()["status"] == "closed", timeout=30)
    final = window._live_control._jobs[job["id"]]
    assert dialog._task is None and not connection.exists()
    assert final["status"] == "succeeded", final["error"]
    assert final["generation"] == 2 and final["operation"] == "adopt" and final["cancellable"] is False
    assert final["result"]["adopted"] is True
    assert session.document.revision == before + 1
    assert not dialog._cancel.is_set()
    QApplication.processEvents()
