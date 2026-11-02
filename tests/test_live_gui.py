"""A separate public CLI controls the actual open Qt owner, never a model copy."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow

pytestmark = pytest.mark.usefixtures("qt_widgets")
ROOT = Path(__file__).resolve().parents[1]


def pump_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline: raise AssertionError("Timed out waiting for the actual Qt/network operation")
        QTest.qWait(5)


def call(connection, method="document.describe", params=None, *, request_id=None, error=None):
    command = [sys.executable,"-m","caelab_prep","live","--connection",str(connection),"--method",method,
               "--params",json.dumps(params or {})]
    if request_id: command += ["--request-id",request_id]
    # The Qt owner must keep pumping while a large CLI response is written.
    # Files avoid waiting for exit with a full, unread pipe on Windows.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output, tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        process = subprocess.Popen(command, stdout=output, stderr=errors, text=True)
        try:
            pump_until(lambda: process.poll() is not None)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        output.seek(0); errors.seek(0)
        stdout, stderr = output.read(), errors.read()
    value = json.loads(stdout)
    capture_dir = os.environ.get("CAELAB_LIVE_CAPTURE_DIR")
    if capture_dir:
        def public(item):
            if isinstance(item, dict): return {key: "<private capability>" if key in ("token", "cancel_token") else public(val) for key,val in item.items()}
            if isinstance(item, list): return [public(val) for val in item]
            return item
        destination = Path(capture_dir); destination.mkdir(parents=True,exist_ok=True)
        with (destination/"requests.jsonl").open("a",encoding="utf-8") as stream:
            stream.write(json.dumps({"method":method,"params":public(params),"response":public(value),"exit_code":process.returncode})+"\n")
    if error:
        assert process.returncode == 1, (stdout,stderr)
        assert value["error"]["code"] == error, value
    else: assert process.returncode == 0, (stdout,stderr)
    return value


@pytest.fixture
def owner(tmp_path):
    session = PrepSession(); session.open_rad(str(ROOT/"examples/rad/shell_panels_0000.rad"))
    window = MainWindow(session,enable_viewport=False)
    window._allow_close = True; window.resize(1200,850); window.show()
    QApplication.processEvents()
    connection = tmp_path/"connection.json"
    window.start_live_ipc(connection)
    yield window,session,connection
    if window._live_control.status().get("active_jobs"):
        window.stop_live_ipc()
        pump_until(lambda:not window._live_control.status().get("active_jobs"))
    window.close(); QApplication.processEvents()


def material(connection):
    result = call(connection,"document.cards")
    return next(card["ref"] for card in result["cards"] if card["group"] == "Materials")


def capture(window, name):
    directory = os.environ.get("CAELAB_LIVE_CAPTURE_DIR")
    if directory:
        assert QApplication.platformName() == "xcb"
        path=Path(directory);path.mkdir(parents=True,exist_ok=True)
        assert window.screen().grabWindow(0).save(str(path/(name+".png")))


def test_external_process_edit_undo_save_events_and_reconnect_same_owner(owner,tmp_path):
    window,session,connection=owner
    description=call(connection)
    assert description["handle"]["document_id"] == session.document.id
    assert description["handle"]["document_epoch"] == session.describe()["document_epoch"]
    target=material(connection)
    call(connection,"document.select",{"handle":description["handle"],"target":target})
    assert window._selected_card_id == target["object_id"]
    initial=next(field["value"] for field in session.card_fields(target["object_id"]) if field["name"]=="young_modulus")
    threads=[]; unsubscribe=session.subscribe(lambda event: threads.append(QThread.currentThread()==window.thread()))
    request_id=str(uuid4())
    params={"handle":description["handle"],"target":target,"values":{"young_modulus":123456.0}}
    changed=call(connection,"document.edit",params,request_id=request_id)
    assert changed["handle"]["revision"] == description["handle"]["revision"]+1
    assert float(window.field_editors["young_modulus"].text()) == 123456
    assert threads and all(threads)
    # Each call above and below is a fresh external Python process/connection.
    assert call(connection,"document.edit",params,request_id=request_id)==changed
    assert session.document.revision == changed["handle"]["revision"]
    call(connection,"document.edit",params,error="revision_conflict")
    capture(window,"edited-owner")
    undone=call(connection,"document.undo",{"handle":changed["handle"]})
    assert float(window.field_editors["young_modulus"].text()) == initial
    redone=call(connection,"document.redo",{"handle":undone["handle"]})
    saved=tmp_path/"live.caeprep"
    call(connection,"document.save",{"handle":redone["handle"],"path":str(saved)})
    assert not session.document.dirty and saved.exists()
    reopened=PrepSession();reopened.open_project(str(saved))
    assert next(f["value"] for f in reopened.card_fields(target["object_id"]) if f["name"]=="young_modulus")==123456
    events=call(connection,"events.since",{"after":description["event_sequence"]})["events"]
    assert any(event["kind"]=="session" and event["payload"]["kind"]=="save" for event in events)
    assert all(b["sequence"]>a["sequence"] for a,b in zip(events,events[1:]))
    unsubscribe()


def test_invalid_gui_draft_busy_unknown_and_reopened_handle_are_rejected(owner,tmp_path):
    window,session,connection=owner
    target=material(connection)
    desc=call(connection)
    call(connection,"document.select",{"handle":desc["handle"],"target":target})
    before=session.document.tokens(),session.document.revision
    editor=window.field_editors["young_modulus"]
    editor.setText("1e");editor.setModified(True)
    assert call(connection)["owner"]["draft_pending"]
    params={"handle":desc["handle"],"target":target,"values":{"young_modulus":100000}}
    call(connection,"document.edit",params,error="draft_pending")
    call(connection,"document.save",{"handle":desc["handle"],"path":str(tmp_path/"bad.caeprep")},error="draft_pending")
    assert (session.document.tokens(),session.document.revision)==before and editor.text()=="1e"
    window._discard_pending_edits();window.refresh_document()
    window._busy=True
    call(connection,"document.edit",params,error="owner_busy")
    window._busy=False
    call(connection,"arbitrary.eval",{"code":"anything"},error="method_not_found")
    project=tmp_path/"same.caeprep";session.save_project(str(project));session.open_project(str(project))
    QApplication.processEvents()
    call(connection,"document.edit",params,error="document_conflict")
    assert session.document.id==desc["handle"]["document_id"]
    assert session.describe()["document_epoch"]!=desc["handle"]["document_epoch"]


def test_stopped_connection_does_not_create_fallback_document(owner):
    window,session,connection=owner
    descriptor=json.loads(connection.read_text())
    assert window.stop_live_ipc()
    assert not connection.exists()
    replacement=connection.with_name("old-connection.json");replacement.write_text(json.dumps(descriptor))
    before=session.document.tokens(),session.document.revision
    call(replacement,error="connection_error")
    assert (session.document.tokens(),session.document.revision)==before


def test_expired_queued_request_never_mutates_after_gui_resumes(owner,monkeypatch):
    from caelab_prep.ui import live_control
    window,session,connection=owner
    target=material(connection); handle=call(connection)["handle"]
    before=session.document.tokens(),session.document.revision
    monkeypatch.setattr(live_control,"_QUEUE_TIMEOUT_SECONDS",.05)
    command=[sys.executable,"-m","caelab_prep","live","--connection",str(connection),"--method","document.edit",
             "--params",json.dumps({"handle":handle,"target":target,"values":{"young_modulus":42}})]
    # Deliberately do not process Qt events while the real socket thread queues
    # the request. The owner must drop it after the bounded queue wait expires.
    process=subprocess.run(command,capture_output=True,text=True,timeout=10)
    assert process.returncode==1 and json.loads(process.stdout)["error"]["code"]=="request_timeout"
    QApplication.processEvents()
    assert (session.document.tokens(),session.document.revision)==before


def test_actual_mesh_worker_job_cancellation_ownership_and_completion(owner,tmp_path):
    from test_gmsh_adapter import require_sdk
    require_sdk()
    pytest.importorskip("OCP")
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs,STEPControl_Writer
    writer=STEPControl_Writer();writer.Transfer(BRepPrimAPI_MakeBox(10,10,10).Shape(),STEPControl_AsIs)
    cad=tmp_path/"box.step";assert int(writer.Write(str(cad)))==1
    window,session,connection=owner
    before=session.document.tokens(),session.document.revision
    handle=call(connection)["handle"]
    job=call(connection,"mesh.start",{"handle":handle,"source":str(cad),"output":str(tmp_path/"cancelled"),"size":.02,"dimension":3})
    assert job["status"]=="running"
    queried=call(connection,"jobs.get",{"job_id":job["id"]})
    assert "cancel_token" not in queried
    call(connection,"jobs.cancel",{"job_id":job["id"],"cancel_token":"not-owner"},error="job_ownership")
    call(connection,"document.undo",{"handle":handle},error="owner_busy")
    call(connection,"jobs.cancel",{"job_id":job["id"],"cancel_token":job["cancel_token"]})
    pump_until(lambda:not window._live_control.status()["active_jobs"])
    cancelled=call(connection,"jobs.get",{"job_id":job["id"]})
    assert cancelled["status"]=="cancelled"
    details=cancelled["error"]["details"]
    assert details["returncode"] is not None
    if os.name=="posix":
        with pytest.raises(ProcessLookupError): os.kill(details["pid"],0)
    call(connection,"jobs.close",{"job_id":job["id"],"cancel_token":job["cancel_token"]})
    assert (session.document.tokens(),session.document.revision)==before
    good=call(connection,"mesh.start",{"handle":handle,"source":str(cad),"output":str(tmp_path/"complete"),"size":4,"dimension":3})
    pump_until(lambda:not window._live_control.status()["active_jobs"],timeout=40)
    completed=call(connection,"jobs.get",{"job_id":good["id"]})
    assert completed["status"]=="succeeded" and completed["result"]["node_count"]>4
    assert completed["result"]["adopted"] is False
    assert all(Path(asset["path"]).exists() for asset in completed["result"]["assets"])
    capture(window,"mesh-candidate-owner")
    call(connection,"jobs.close",{"job_id":good["id"],"cancel_token":good["cancel_token"]})
    assert (session.document.tokens(),session.document.revision)==before
