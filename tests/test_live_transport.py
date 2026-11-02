"""Socket/protocol tests independent of Qt and of a standalone Prep session."""
import concurrent.futures
import json
import os
import socket
import stat
import subprocess
import sys
import threading
from uuid import uuid4

import pytest

from caelab_prep.application import live_transport
from caelab_prep.application.live_transport import LiveClient, LiveRemoteError, LiveServer
from caelab_prep.cae_core.errors import PrepError


def envelope(server, **overrides):
    return {"id": str(uuid4()), "token": server.descriptor()["token"],
            "method": "inspect", "params": {}, **overrides}


def raw_request(server, payload):
    descriptor = server.descriptor()
    with socket.create_connection((descriptor["host"], descriptor["port"]), 2) as connection:
        connection.settimeout(2)
        connection.sendall(payload)
        with connection.makefile("rb") as stream:
            return json.loads(stream.readline())


def test_subprocess_client_reconnect_save_and_descriptor_cleanup(tmp_path):
    descriptor = tmp_path / "live.json"
    output = tmp_path / "saved.caeprep"
    calls = []
    owner_thread = threading.get_ident()

    def dispatch(request):
        assert threading.get_ident() != owner_thread
        assert set(request) == {"id", "method", "params"}
        calls.append(request["method"])
        if request["method"] == "save":
            output.write_text(request["params"]["value"], encoding="utf-8")
            return {"path": str(output), "revision": 4}
        return {"revision": 4}

    server = LiveServer(dispatch, descriptor)
    try:
        assert json.loads(descriptor.read_text()) == server.descriptor()
        if os.name != "nt":
            assert stat.S_IMODE(descriptor.stat().st_mode) == 0o600
        script = """
import json, sys
from caelab_prep.application.live_transport import LiveClient
client = LiveClient(sys.argv[1])
assert 'PySide6' not in sys.modules
print(json.dumps([client.request('inspect'), client.request('save', {'value': 'edited document'})]))
"""
        result = subprocess.run([sys.executable, "-c", script, str(descriptor)],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == [{"revision": 4}, {"path": str(output), "revision": 4}]
        assert output.read_text() == "edited document"
        # A second client connects to the same owner, with no local session.
        client = LiveClient(descriptor)
        assert client.request("inspect") == {"revision": 4}
        assert calls == ["inspect", "save", "inspect"]
    finally:
        server.close()
    assert not descriptor.exists()
    server.close()
    with pytest.raises(LiveRemoteError) as failure:
        client.request("inspect")
    assert failure.value.code == "connection_error"


def test_existing_descriptor_is_never_overwritten(tmp_path):
    descriptor = tmp_path / "live.json"
    descriptor.write_text("user-owned file")
    with pytest.raises(FileExistsError):
        LiveServer(lambda request: {}, descriptor)
    assert descriptor.read_text() == "user-owned file"


def test_close_keeps_replacement_descriptor(tmp_path):
    descriptor = tmp_path / "live.json"
    server = LiveServer(lambda request: {}, descriptor)
    replacement = {**server.descriptor(), "server_id": str(uuid4())}
    descriptor.write_text(json.dumps(replacement))
    server.close()
    assert json.loads(descriptor.read_text()) == replacement


def test_descriptor_copy_cannot_change_credentials(tmp_path):
    with LiveServer(lambda request: {}, tmp_path / "live.json") as server:
        modified = server.descriptor()
        modified["token"] = "other"
        assert LiveClient(server.descriptor()).request("inspect") == {}


@pytest.mark.parametrize("patch", [
    {"host": "localhost"}, {"host": "::1"}, {"host": "192.168.1.1"},
    {"port": True}, {"port": 0}, {"port": 65536}, {"port": "123"},
    {"format": "other"}, {"version": True}, {"version": 2},
    {"token": ""}, {"token": "x" * 257}, {"server_id": "missing"}, {"extra": 1},
])
def test_descriptor_validation(tmp_path, patch):
    with LiveServer(lambda request: {}, tmp_path / "live.json") as server:
        with pytest.raises(LiveRemoteError) as failure:
            LiveClient({**server.descriptor(), **patch})
        assert failure.value.code == "invalid_descriptor"


def test_authentication_failure_never_dispatches(tmp_path):
    calls = []
    with LiveServer(lambda request: calls.append(request), tmp_path / "live.json") as server:
        client = LiveClient({**server.descriptor(), "token": "wrong"})
        with pytest.raises(LiveRemoteError) as failure:
            client.request("inspect")
        assert failure.value.code == "authentication_failed"
        assert calls == []


@pytest.mark.parametrize("patch", [
    {"extra": 1}, {"id": "not-a-uuid"}, {"token": 4}, {"params": []},
    {"method": 1}, {"method": ""}, {"method": "x" * 129},
    {"params": {"value": float("nan")}}, {"params": {"value": float("inf")}},
])
def test_malformed_envelopes_never_dispatch(tmp_path, patch):
    calls = []
    with LiveServer(lambda request: calls.append(request), tmp_path / "live.json") as server:
        response = raw_request(server, json.dumps(envelope(server, **patch)).encode() + b"\n")
        assert response["error"]["code"] == "invalid_request"
        assert calls == []


@pytest.mark.parametrize("payload", [
    b"not json\n", b"[]\n", b"{}\n", b"{\xff}\n",
    b'{"id":1,"id":2}\n', b'{"value":1e999}\n', b"[" * 2000 + b"\n",
])
def test_invalid_json_is_structured(tmp_path, payload):
    with LiveServer(lambda request: pytest.fail("dispatch called"), tmp_path / "live.json") as server:
        assert raw_request(server, payload)["error"]["code"] == "invalid_request"


def test_oversized_request_and_result(tmp_path, monkeypatch):
    monkeypatch.setattr(live_transport, "MAX_REQUEST_BYTES", 1024)
    monkeypatch.setattr(live_transport, "MAX_RESPONSE_BYTES", 1024)
    with LiveServer(lambda request: "x" * 2048, tmp_path / "live.json") as server:
        assert raw_request(server, b"x" * 1025 + b"\n")["error"]["code"] == "message_too_large"
        client = LiveClient(server.descriptor())
        with pytest.raises(LiveRemoteError) as failure:
            client.request("inspect", {"value": "x" * 1024})
        assert failure.value.code == "message_too_large"
        with pytest.raises(LiveRemoteError) as failure:
            client.request("inspect")
        assert failure.value.code == "response_too_large"


def test_application_error_and_internal_failure_are_distinct(tmp_path):
    def dispatch(request):
        if request["method"] == "unknown":
            raise PrepError("unknown_method", "This method is unsupported.", {"method": "unknown"})
        raise RuntimeError("secret implementation traceback and credential")

    with LiveServer(dispatch, tmp_path / "live.json") as server:
        client = LiveClient(server.descriptor())
        with pytest.raises(LiveRemoteError) as failure:
            client.request("unknown")
        assert failure.value.code == "unknown_method"
        assert failure.value.details == {"method": "unknown"}
        assert failure.value.message == "This method is unsupported."
        with pytest.raises(LiveRemoteError) as failure:
            client.request("explode")
        assert failure.value.code == "internal_error"
        assert "secret" not in str(failure.value)


def test_identical_request_replays_result_or_error_once(tmp_path):
    calls = []

    def dispatch(request):
        calls.append(request)
        if request["method"] == "unknown":
            raise PrepError("unknown_method", "Unsupported", {})
        return {"count": len(calls)}

    with LiveServer(dispatch, tmp_path / "live.json") as server:
        client = LiveClient(server.descriptor())
        request_id = str(uuid4())
        assert client.request("edit", {"a": 1, "b": 2}, request_id) == {"count": 1}
        assert client.request("edit", {"b": 2, "a": 1}, request_id) == {"count": 1}
        with pytest.raises(LiveRemoteError) as failure:
            client.request("edit", {"a": 2}, request_id)
        assert failure.value.code == "request_id_conflict"
        error_id = str(uuid4())
        for _ in range(2):
            with pytest.raises(LiveRemoteError) as failure:
                client.request("unknown", request_id=error_id)
            assert failure.value.code == "unknown_method"
        assert len(calls) == 2


def test_concurrent_duplicate_and_disconnect_dispatch_exactly_once(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def dispatch(request):
        calls.append(request)
        entered.set()
        assert release.wait(5)
        return {"revision": 1}

    with LiveServer(dispatch, tmp_path / "live.json") as server:
        descriptor = server.descriptor()
        request = envelope(server, method="edit", params={"value": 42})
        connection = socket.create_connection((descriptor["host"], descriptor["port"]), 2)
        connection.sendall(json.dumps(request).encode() + b"\n")
        assert entered.wait(2)
        connection.close()  # Lose the first response, then retry the same ID.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(LiveClient(descriptor).request, "edit", {"value": 42}, request["id"])
                       for _ in range(4)]
            release.set()
            assert [future.result(5) for future in futures] == [{"revision": 1}] * 4
        assert len(calls) == 1


def test_duplicate_wait_has_a_bound_without_discarding_reservation(tmp_path, monkeypatch):
    monkeypatch.setattr(live_transport, "_DUPLICATE_WAIT_SECONDS", 0.05)
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def dispatch(request):
        calls.append(request)
        entered.set()
        assert release.wait(5)
        return {"revision": 1}

    with LiveServer(dispatch, tmp_path / "live.json") as server:
        client = LiveClient(server.descriptor())
        request_id = str(uuid4())
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            original = pool.submit(client.request, "edit", {}, request_id)
            assert entered.wait(2)
            try:
                with pytest.raises(LiveRemoteError) as failure:
                    client.request("edit", {}, request_id)
                assert failure.value.code == "request_timeout"
                assert len(calls) == 1
            finally:
                release.set()
            assert original.result(5) == {"revision": 1}
        assert client.request("edit", {}, request_id) == {"revision": 1}
        assert len(calls) == 1


def test_bounded_cache_evicts_completed_requests_only(tmp_path, monkeypatch):
    monkeypatch.setattr(live_transport, "_MAX_CACHE_ENTRIES", 2)
    calls = []
    with LiveServer(lambda request: calls.append(request) or len(calls), tmp_path / "live.json") as server:
        client = LiveClient(server.descriptor())
        ids = [str(uuid4()) for _ in range(3)]
        for index, request_id in enumerate(ids, 1):
            assert client.request("inspect", request_id=request_id) == index
        assert len(server._requests) == 2
        assert client.request("inspect", request_id=ids[-1]) == 3
        assert client.request("inspect", request_id=ids[0]) == 4


def test_client_timeout_preserves_request_id_for_retry(tmp_path):
    release = threading.Event()
    with LiveServer(lambda request: release.wait(5), tmp_path / "live.json") as server:
        client = LiveClient(server.descriptor(), timeout=0.05)
        request_id = str(uuid4())
        try:
            with pytest.raises(LiveRemoteError) as failure:
                client.request("edit", request_id=request_id)
            assert failure.value.code == "request_timeout"
            assert failure.value.details == {"request_id": request_id}
        finally:
            release.set()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, "30"])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValueError):
        LiveClient({}, timeout=timeout)


def test_cache_does_not_retain_full_request_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr(live_transport, "_MAX_CACHE_BYTES", 1024)
    with LiveServer(lambda request: True, tmp_path / "live.json") as server:
        client = LiveClient(server.descriptor())
        for _ in range(3):
            assert client.request("inspect", {"value": "x" * 100_000}) is True
        retained = sum(len(request.fingerprint) + len(request.response)
                       for request in server._requests.values())
        assert retained < 4096


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO descriptors are POSIX-specific")
def test_fifo_descriptor_does_not_block_client_or_server_close(tmp_path):
    script = """
import os, sys
from pathlib import Path
from caelab_prep.application.live_transport import LiveClient, LiveRemoteError, LiveServer
path = Path(sys.argv[1])
server = LiveServer(lambda request: {}, path)
path.unlink()
os.mkfifo(path)
try:
    LiveClient(path, timeout=0.1)
except LiveRemoteError as exc:
    assert exc.code == 'invalid_descriptor'
else:
    raise AssertionError('FIFO descriptor accepted')
server.close()
assert path.exists()
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "fifo")],
                            capture_output=True, text=True, timeout=3)
    assert result.returncode == 0, result.stderr
