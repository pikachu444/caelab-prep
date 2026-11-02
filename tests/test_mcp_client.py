"""Opt-in interoperability with published mcpc and FastMCP client CLIs.

Set CAELAB_MCPC and/or CAELAB_FASTMCP to the installed client executable, plus
CAELAB_MCP_PYTHON to a separate Python with the optional server SDK.
The Qt owner runs in the pytest interpreter, which
also needs Gmsh/OCP for the real worker test. No SDK client or transport mock is
used here. CAELAB_MCP_CAPTURE_DIR records redacted protocol results and X11
screenshots; credentials and cancellation capabilities never enter artifacts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.usefixtures("qt_widgets"),
    pytest.mark.skipif(not ((os.environ.get("CAELAB_MCPC") or os.environ.get("CAELAB_FASTMCP"))
                           and os.environ.get("CAELAB_MCP_PYTHON")),
                       reason="Set CAELAB_MCPC/CAELAB_FASTMCP and CAELAB_MCP_PYTHON for the actual published-client check"),
]


def pump_until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("Timed out waiting for the real MCP client/Qt owner operation")
        QTest.qWait(5)


def redact(value):
    """Redact both structured data and JSON encoded inside MCP text content."""
    if isinstance(value, dict):
        return {key: "<private capability>" if key in {"token", "cancel_token"} else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return value
        if isinstance(decoded, (dict, list)):
            return json.dumps(redact(decoded), ensure_ascii=True)
    return value


def capture(window, name):
    directory = os.environ.get("CAELAB_MCP_CAPTURE_DIR")
    if directory:
        assert QApplication.platformName() == "xcb", "Capture requires the real X11 Qt platform"
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        assert window.screen().grabWindow(0).save(str(destination / (name + ".png")))


class PublishedClient:
    """Invoke the installed CLI, preserving its real exit status and MCP result."""

    def __init__(self, kind, state_dir, config, test_name):
        self.kind = kind
        self.command = os.environ["CAELAB_MCPC" if kind == "mcpc" else "CAELAB_FASTMCP"]
        self.environment = {**os.environ, "MCPC_HOME_DIR": str(state_dir), "FASTMCP_HOME": str(state_dir)}
        self.config = config
        self.session = "@prep"
        self.test_name = test_name
        self.calls = []
        self.secrets = set()

    def _safe(self, value):
        value = redact(value)
        if isinstance(value, dict):
            return {key: self._safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._safe(item) for item in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "<private capability>")
        return value

    def _remember_secrets(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"token", "cancel_token"} and isinstance(item, str):
                    self.secrets.add(item)
                else:
                    self._remember_secrets(item)
        elif isinstance(value, list):
            for item in value:
                self._remember_secrets(item)

    def run(self, *arguments):
        prefix = ["--json", "--timeout", "20"] if self.kind == "mcpc" else []
        command = [self.command, *prefix, *arguments]
        process = subprocess.Popen(command, env=self.environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        finished = threading.Event()
        collected = {}

        def collect():
            try:
                collected["stdout"], collected["stderr"] = process.communicate(timeout=35)
            except subprocess.TimeoutExpired:
                process.kill()
                collected["stdout"], collected["stderr"] = process.communicate()
                collected["timed_out"] = True
            finally:
                finished.set()

        reader = threading.Thread(target=collect, daemon=True)
        reader.start()
        try:
            pump_until(finished.is_set, timeout=40)
        finally:
            if process.poll() is None:
                process.kill()
            reader.join(timeout=2)
        stdout, stderr = collected.get("stdout", ""), collected.get("stderr", "")
        try:
            result = json.loads(stdout)
        except ValueError:
            result = None
        self._remember_secrets(result)
        record = self._safe({"test": self.test_name, "client": self.kind, "arguments": list(arguments),
                             "exit_code": process.returncode, "response": result,
                             "stderr": stderr, "stdout_if_not_json": stdout if result is None else None})
        self.record(record)
        assert not collected.get("timed_out"), record
        return process.returncode, result, record

    def record(self, value):
        record = self._safe({"test": self.test_name, "client": self.kind, **value})
        self.calls.append(record)
        directory = os.environ.get("CAELAB_MCP_CAPTURE_DIR")
        if directory:
            destination = Path(directory)
            destination.mkdir(parents=True, exist_ok=True)
            with (destination / (self.kind + "-requests.jsonl")).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=True) + "\n")

    def connect(self):
        if self.kind == "fastmcp":
            # FastMCP opens and closes stdio for each invocation; this performs
            # a real handshake and discovery without a background bridge.
            return self.tools()
        code, result, record = self.run("connect", str(self.config) + ":prep", self.session, "--no-profile")
        if code:
            log_dir = Path(self.environment["MCPC_HOME_DIR"]) / "logs"
            record["bridge_logs"] = self._safe({path.name: path.read_text(errors="replace")[-8000:]
                                                for path in log_dir.glob("*.log")})
        if code:
            capture_dir = os.environ.get("CAELAB_MCP_CAPTURE_DIR")
            if capture_dir:
                destination = Path(capture_dir) / (self.test_name + "-connection-failure.json")
                destination.write_text(json.dumps(record, indent=2), encoding="utf-8")
            pytest.fail(json.dumps(record, indent=2))
        assert isinstance(result, list) and result, record
        return result

    def tools(self):
        if self.kind == "mcpc":
            code, result, record = self.run(self.session, "tools-list")
        else:
            code, result, record = self.run("list", str(self.config), "--json", "--timeout", "20")
            if isinstance(result, dict):
                result = result.get("tools")
        if code or not isinstance(result, list):
            pytest.fail(json.dumps(record, indent=2))
        return {tool["name"]: tool for tool in result}

    def tool(self, name, arguments=None, *, error=None):
        serialized = json.dumps(arguments or {}, ensure_ascii=True)
        if self.kind == "mcpc":
            code, result, record = self.run(self.session, "tools-call", name, serialized)
            structured_key, error_key, error_exit = "structuredContent", "isError", 2
        else:
            code, result, record = self.run("call", str(self.config), name,
                "--input-json", serialized, "--json", "--timeout", "20")
            structured_key, error_key, error_exit = "structured_content", "is_error", 1
        if not isinstance(result, dict):
            pytest.fail(json.dumps(record, indent=2))
        # Both CLIs expose the tool result, using their documented JSON field
        # names. Test the real structured value and duplicate MCP text content.
        assert "content" in result and structured_key in result, record
        value = result[structured_key]
        texts = [item["text"] for item in result["content"] if item.get("type") == "text"]
        assert texts and json.loads(texts[0]) == value, record
        if error:
            assert code == error_exit and result.get(error_key) is True, record
            assert value["error"]["code"] == error, record
        else:
            assert code == 0 and result.get(error_key) is not True, record
        return value

    def close(self):
        if self.kind == "fastmcp":
            return  # Each completed CLI process already closed its stdio client.
        code, result, record = self.run("close", self.session)
        assert code == 0 and result["closed"] is True, record


@pytest.fixture(params=[kind for kind, variable in (("mcpc", "CAELAB_MCPC"), ("fastmcp", "CAELAB_FASTMCP"))
                        if os.environ.get(variable)] or ["unconfigured"])
def mcp_owner(tmp_path, request):
    session = PrepSession()
    session.open_rad(str(ROOT / "examples/rad/shell_panels_0000.rad"))
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True
    window.resize(1200, 850)
    window.show()
    QApplication.processEvents()
    connection = tmp_path / "connection.json"
    window.start_live_ipc(connection)
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"prep": {
        "command": os.environ["CAELAB_MCP_PYTHON"],
        "args": ["-m", "caelab_prep", "mcp", "--connection", str(connection)],
        "env": {"PYTHONPATH": str(ROOT / "src")},
    }}}), encoding="utf-8")
    # mcpc's Unix socket lives beneath its state directory; pytest's full
    # temporary path can exceed sockaddr_un's platform path-length bound.
    with tempfile.TemporaryDirectory(prefix="prep-mcp-") as state:
        client = PublishedClient(request.param, state, config, request.node.name)
        original_descriptor = json.loads(connection.read_text())
        client.secrets.add(original_descriptor["token"])
        descriptor_matches_owner = original_descriptor["server_id"] == window._live_control.status()["server_id"]
        del original_descriptor
        connected = False
        try:
            client.connect()
            connected = True
            yield window, session, client
        finally:
            try:
                # Close the real published client's bridge in every connected
                # outcome before removing its private session directory.
                if connected:
                    client.close()
                elif client.kind == "mcpc":
                    client.run("close", client.session)
            finally:
                window._discard_pending_edits()
                started = time.time()
                first_stop = window.stop_live_ipc()
                final_ack = None
                try:
                    def stopped():
                        state = window._live_control.status()
                        return state["status"] == "closed" and not state["active_jobs"] and not connection.exists()
                    pump_until(stopped, timeout=30)
                    final_ack = window.stop_live_ipc()
                    assert final_ack is True
                finally:
                    state = window._live_control.status()
                    client.record({"event": "owner_teardown", "started_at": started, "finished_at": time.time(),
                        "initial_stop_result": first_stop, "final_stop_acknowledged": final_ack,
                        "owner_server_id": state["server_id"], "original_descriptor_matches_owner": descriptor_matches_owner,
                        "owner_status": state["status"], "active_jobs": state["active_jobs"],
                        "descriptor_exists": connection.exists()})
                    window.close()
                    QApplication.processEvents()


def target_material(client):
    cards = client.tool("prep_cards")
    return next(card["ref"] for card in cards["cards"] if card["group"] == "Materials")


def test_published_client_edits_same_gui_undo_save_reopen_and_disconnect(mcp_owner, tmp_path):
    window, session, client = mcp_owner
    tools = client.tools()
    assert {"prep_describe", "prep_cards", "prep_properties", "prep_select", "prep_edit_scalar",
            "prep_undo", "prep_redo", "prep_save", "prep_events", "prep_job_cancel"} <= set(tools)
    assert {"handle", "target", "values"} <= set(tools["prep_edit_scalar"]["inputSchema"]["required"])
    description = client.tool("prep_describe")
    assert description["handle"]["document_id"] == session.document.id
    assert description["handle"]["document_epoch"] == session.describe()["document_epoch"]
    target = target_material(client)
    properties = client.tool("prep_properties", {"target": target})
    modulus = next(item for item in properties["properties"] if item["name"] == "young_modulus")
    initial = modulus["value"]
    assert modulus["editable"] and modulus["kind"] == "number"
    client.tool("prep_select", {"handle": description["handle"], "target": target})
    assert window._selected_card_id == target["object_id"]
    threads = []
    unsubscribe = session.subscribe(lambda event: threads.append(QThread.currentThread() == window.thread()))
    try:
        arguments = {"handle": description["handle"], "target": target,
                     "values": {"young_modulus": 123456.0}, "request_id": str(uuid4())}
        changed = client.tool("prep_edit_scalar", arguments)
        assert changed["handle"]["revision"] == description["handle"]["revision"] + 1
        assert float(window.field_editors["young_modulus"].text()) == 123456.0
        assert threads and all(threads)
        assert client.tool("prep_edit_scalar", arguments) == changed
        assert session.document.revision == changed["handle"]["revision"]
        capture(window, "mcp-edited-open-owner")
        undone = client.tool("prep_undo", {"handle": changed["handle"]})
        assert float(window.field_editors["young_modulus"].text()) == initial
        redone = client.tool("prep_redo", {"handle": undone["handle"]})
        assert float(window.field_editors["young_modulus"].text()) == 123456.0
        saved = tmp_path / "mcp-edited.caeprep"
        client.tool("prep_save", {"handle": redone["handle"], "path": str(saved)})
        assert saved.is_file() and not session.document.dirty
        reopened = PrepSession()
        reopened.open_project(str(saved))
        assert next(item["value"] for item in reopened.card_fields(target["object_id"])
                    if item["name"] == "young_modulus") == 123456.0
        events = client.tool("prep_events", {"after": description["event_sequence"]})["events"]
        assert any(event["kind"] == "session" and event["payload"]["kind"] == "save" for event in events)
        # Retain an explicitly stale private descriptor for clients that launch
        # a fresh adapter per call. A disconnected GUI must not create a copy.
        connection = Path(window._live_control.status()["descriptor_path"])
        stale = tmp_path / "disconnected.json"
        stale.write_bytes(connection.read_bytes())
        stale.chmod(0o600)
        try:
            config = json.loads(client.config.read_text())
            config["mcpServers"]["prep"]["args"][-1] = str(stale)
            client.config.write_text(json.dumps(config), encoding="utf-8")
            before = session.document.tokens(), session.document.revision
            assert window.stop_live_ipc()
            client.tool("prep_describe", error="connection_error")
            assert (session.document.tokens(), session.document.revision) == before
        finally:
            stale.unlink()
    finally:
        unsubscribe()


def test_published_client_preserves_drafts_and_rejects_stale_handles(mcp_owner, tmp_path):
    window, session, client = mcp_owner
    target = target_material(client)
    description = client.tool("prep_describe")
    client.tool("prep_select", {"handle": description["handle"], "target": target})
    params = {"handle": description["handle"], "target": target, "values": {"young_modulus": 140000.0}}
    changed = client.tool("prep_edit_scalar", params)
    client.tool("prep_edit_scalar", params, error="revision_conflict")
    before = session.document.tokens(), session.document.revision
    editor = window.field_editors["young_modulus"]
    editor.setText("1e")
    editor.setModified(True)
    assert client.tool("prep_describe")["owner"]["draft_pending"] is True
    params["handle"] = changed["handle"]
    client.tool("prep_edit_scalar", params, error="draft_pending")
    blocked_save = tmp_path / "draft-must-not-save.caeprep"
    client.tool("prep_save", {"handle": changed["handle"], "path": str(blocked_save)}, error="draft_pending")
    assert editor.text() == "1e" and not blocked_save.exists()
    assert (session.document.tokens(), session.document.revision) == before
    capture(window, "mcp-preserved-invalid-draft")
    window._discard_pending_edits()
    window.refresh_document()
    same_file = tmp_path / "same-document.caeprep"
    session.save_project(str(same_file))
    session.open_project(str(same_file))
    QApplication.processEvents()
    assert session.document.id == description["handle"]["document_id"]
    assert session.describe()["document_epoch"] != description["handle"]["document_epoch"]
    client.tool("prep_edit_scalar", params, error="document_conflict")


def test_published_client_owns_and_cancels_real_gmsh_worker(mcp_owner, tmp_path):
    probe = subprocess.run([sys.executable, "-c", "import gmsh;gmsh.initialize(interruptible=False);gmsh.finalize()"],
                           capture_output=True, text=True, timeout=15)
    if probe.returncode:
        pytest.skip("The Qt owner's Python lacks Gmsh/native dependencies: " + probe.stderr[-300:])
    pytest.importorskip("OCP")
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    writer = STEPControl_Writer()
    writer.Transfer(BRepPrimAPI_MakeBox(10, 10, 10).Shape(), STEPControl_AsIs)
    cad = tmp_path / "box.step"
    assert int(writer.Write(str(cad))) == 1
    window, session, client = mcp_owner
    before = session.document.tokens(), session.document.revision
    handle = client.tool("prep_describe")["handle"]
    job = client.tool("prep_mesh_start", {"handle": handle, "source": str(cad),
                      "output": str(tmp_path / "cancelled"), "size": 0.02, "dimension": 3})
    assert job["status"] == "running"
    queried = client.tool("prep_job_get", {"job_id": job["id"]})
    assert "cancel_token" not in queried
    client.tool("prep_job_cancel", {"job_id": job["id"], "cancel_token": "not-the-creator"}, error="job_ownership")
    client.tool("prep_undo", {"handle": handle}, error="owner_busy")
    client.tool("prep_job_cancel", {"job_id": job["id"], "cancel_token": job["cancel_token"]})
    pump_until(lambda: not window._live_control.status()["active_jobs"])
    cancelled = client.tool("prep_job_get", {"job_id": job["id"]})
    assert cancelled["status"] == "cancelled"
    details = cancelled["error"]["details"]
    assert details["returncode"] is not None
    if os.name == "posix":
        with pytest.raises(ProcessLookupError):
            os.kill(details["pid"], 0)
    client.tool("prep_job_close", {"job_id": job["id"], "cancel_token": job["cancel_token"]})
    assert (session.document.tokens(), session.document.revision) == before
    complete = client.tool("prep_mesh_start", {"handle": handle, "source": str(cad),
                           "output": str(tmp_path / "complete"), "size": 4.0, "dimension": 3})
    pump_until(lambda: not window._live_control.status()["active_jobs"], timeout=40)
    result = client.tool("prep_job_get", {"job_id": complete["id"]})
    assert result["status"] == "succeeded" and result["result"]["node_count"] > 4
    assert result["result"]["adopted"] is False
    assert all(Path(asset["path"]).is_file() for asset in result["result"]["assets"])
    capture(window, "mcp-real-mesh-candidate")
    client.tool("prep_job_close", {"job_id": complete["id"], "cancel_token": complete["cancel_token"]})
    assert (session.document.tokens(), session.document.revision) == before
