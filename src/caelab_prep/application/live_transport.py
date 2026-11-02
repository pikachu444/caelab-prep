"""Authenticated local transport for an explicitly enabled live document owner.

The transport owns no document and imports no GUI. ``dispatch`` runs on a socket
handler thread; the GUI adapter must marshal it to its document owner thread.
Credentials belong in the private descriptor file, never in capability results.
Each request uses a new connection, so callers can reconnect with the same ID
following a lost response. Idempotency lasts only while that ID remains in this
server's bounded cache; it is not a persistent transaction log.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import socket
import socketserver
import stat
import threading
from typing import Callable
from uuid import UUID, uuid4

from ..cae_core.errors import PrepError


DESCRIPTOR_FORMAT = "caelab-prep-live"
PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_MAX_DESCRIPTOR_BYTES = 4096
_MAX_CACHE_ENTRIES = 512
_MAX_CACHE_BYTES = 32 * 1024 * 1024
_MAX_CONNECTIONS = 64
_DUPLICATE_WAIT_SECONDS = 30.0
_SOCKET_TIMEOUT_SECONDS = 30.0


class LiveRemoteError(PrepError):
    """A structured remote error, or a local transport/descriptor failure."""


def _error(request_id, code, message, details=None):
    return {"id": request_id, "error": {
        "code": code, "message": message, "details": details or {},
    }}


def _json_bytes(value):
    # allow_nan=False also catches finite-looking JSON numbers such as 1e999
    # after decoding, and rejects non-JSON dispatch results without repr leakage.
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def _decode(data):
    result = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                        parse_constant=_reject_constant)
    _json_bytes(result)
    return result


def _uuid_string(value):
    if not isinstance(value, str) or len(value) != 36:
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _read_frame(stream, limit):
    frame = stream.readline(limit + 1)
    if len(frame) > limit:
        raise LiveRemoteError("message_too_large", "The live message exceeds its size limit.")
    if not frame or not frame.endswith(b"\n"):
        raise LiveRemoteError("invalid_message", "A complete newline-delimited JSON message is required.")
    return frame[:-1]


def _read_descriptor(path):
    # A replaced FIFO must not hang either GUI shutdown or client startup.
    # O_NOFOLLOW also prevents following a swapped credential-file symlink on
    # platforms that provide it; the regular-file check remains portable.
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor_fd = os.open(path, flags)
    with os.fdopen(descriptor_fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Descriptor must be a regular file")
        data = stream.read(_MAX_DESCRIPTOR_BYTES + 1)
    if len(data) > _MAX_DESCRIPTOR_BYTES:
        raise ValueError("Descriptor too large")
    return _decode(data)


def _validate_descriptor(value):
    required = {"format", "version", "host", "port", "token", "server_id"}
    if (not isinstance(value, dict) or set(value) != required
            or value.get("format") != DESCRIPTOR_FORMAT
            or type(value.get("version")) is not int
            or value.get("version") != PROTOCOL_VERSION
            or value.get("host") != "127.0.0.1"
            or type(value.get("port")) is not int
            or not 1 <= value["port"] <= 65535
            or not isinstance(value.get("token"), str)
            or not 1 <= len(value["token"]) <= 256
            or not _uuid_string(value.get("server_id"))):
        raise LiveRemoteError("invalid_descriptor", "The live connection descriptor is invalid.")
    return dict(value)


@dataclass
class _Request:
    fingerprint: bytes
    ready: threading.Event = field(default_factory=threading.Event)
    response: bytes | None = None


class _TCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False

    def __init__(self, owner):
        self.owner = owner
        self.slots = threading.BoundedSemaphore(_MAX_CONNECTIONS)
        super().__init__(("127.0.0.1", 0), _Handler)

    def process_request(self, request, client_address):
        # Bound idle unauthenticated peers as well as authenticated requests.
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Never log arbitrary payloads, credentials, or dispatch tracebacks.
        pass


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(_SOCKET_TIMEOUT_SECONDS)
        owner = self.server.owner
        with owner._lock:
            if owner._closed:
                return
            owner._connections.add(self.connection)
        try:
            try:
                frame = _read_frame(self.rfile, MAX_REQUEST_BYTES)
                response = owner._process(frame)
            except LiveRemoteError as exc:
                response = _json_bytes(_error(None, exc.code, exc.message, exc.details))
            except (OSError, TimeoutError):
                return
            try:
                self.wfile.write(response + b"\n")
            except OSError:
                pass  # The cached response remains available after disconnect.
        finally:
            with owner._lock:
                owner._connections.discard(self.connection)


class LiveServer:
    """Start a loopback server and exclusively create its private descriptor.

    ``dispatch`` receives ``{id, method, params}``, without the credential. Both
    successes and application errors are cached for idempotent retries. Plain
    exceptions become generic internal errors; structured ``PrepError``-like
    failures preserve their public code, message, and JSON-safe details.
    """

    def __init__(self, dispatch: Callable[[dict], object], descriptor_path):
        if not callable(dispatch):
            raise TypeError("dispatch must be callable")
        self._dispatch = dispatch
        self._path = Path(descriptor_path).absolute()
        self._lock = threading.Lock()
        self._closed = False
        self._connections = set()
        self._requests = OrderedDict()
        self._cache_bytes = 0
        self._server = _TCPServer(self)
        self._descriptor = {
            "format": DESCRIPTOR_FORMAT, "version": PROTOCOL_VERSION,
            "host": "127.0.0.1", "port": self._server.server_address[1],
            "token": secrets.token_urlsafe(32), "server_id": str(uuid4()),
        }
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": 0.05},
                                        name="caelab-prep-live", daemon=True)
        created = False
        try:
            # O_EXCL also rejects an existing symbolic link. Never replace a
            # stale descriptor implicitly; only its owner may remove it.
            descriptor_fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor_fd, "wb") as stream:
                stream.write(_json_bytes(self._descriptor) + b"\n")
            self._thread.start()
        except BaseException:
            self._server.server_close()
            if created:
                self._remove_descriptor()
            raise

    def descriptor(self):
        """Return a private credential-bearing copy for the enabling caller."""
        return dict(self._descriptor)

    def _remove_descriptor(self):
        try:
            current = _read_descriptor(self._path)
            if isinstance(current, dict) and current.get("server_id") == self._descriptor["server_id"]:
                self._path.unlink()
        except (OSError, ValueError, UnicodeError, RecursionError):
            pass

    def close(self):
        """Stop accepting requests and remove only this owner's descriptor."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            connections = tuple(self._connections)
            for pending in self._requests.values():
                pending.ready.set()
        # Do not join handler threads: dispatch may be queued to the GUI thread
        # calling close(). The GUI bridge owns cancellation of those dispatches.
        self._server.shutdown()
        self._server.server_close()
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        self._thread.join(timeout=1)
        self._remove_descriptor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _process(self, frame):
        request_id = None
        try:
            request = _decode(frame)
            if isinstance(request, dict) and _uuid_string(request.get("id")):
                request_id = request["id"]
            if (not isinstance(request, dict)
                    or set(request) != {"id", "token", "method", "params"}
                    or request_id is None
                    or not isinstance(request.get("token"), str)
                    or len(request["token"]) > 256
                    or not isinstance(request.get("method"), str)
                    or not 1 <= len(request["method"]) <= 128
                    or not isinstance(request.get("params"), dict)):
                raise LiveRemoteError("invalid_request", "The live request envelope is invalid.")
            if not hmac.compare_digest(request["token"].encode("utf-8"),
                                       self._descriptor["token"].encode("ascii")):
                raise LiveRemoteError("authentication_failed", "Live connection authentication failed.")
        except LiveRemoteError as exc:
            return _json_bytes(_error(request_id, exc.code, exc.message, exc.details))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return _json_bytes(_error(request_id, "invalid_request", "The live request is not valid JSON."))

        try:
            canonical = json.dumps([request["method"], request["params"]],
                                   sort_keys=True, ensure_ascii=True, allow_nan=False,
                                   separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return _json_bytes(_error(request_id, "invalid_request", "The live request is not valid JSON."))
        # Retain only a digest: 512 near-limit parameter objects must not keep
        # half a gigabyte alive merely to detect idempotent retries.
        fingerprint = hashlib.sha256(canonical).digest()
        with self._lock:
            if self._closed:
                return _json_bytes(_error(request_id, "server_closed", "The live connection is closed."))
            pending = self._requests.get(request_id)
            if pending is not None:
                if pending.fingerprint != fingerprint:
                    return _json_bytes(_error(request_id, "request_id_conflict",
                                             "This request ID was already used for different parameters."))
                self._requests.move_to_end(request_id)
                execute = False
            else:
                self._evict(make_room=True)
                if len(self._requests) >= _MAX_CACHE_ENTRIES:
                    return _json_bytes(_error(request_id, "server_busy", "The live request queue is full."))
                pending = _Request(fingerprint)
                self._requests[request_id] = pending
                execute = True
        if not execute:
            if not pending.ready.wait(_DUPLICATE_WAIT_SECONDS):
                return _json_bytes(_error(request_id, "request_timeout",
                                         "The original live request is still in progress."))
            return pending.response or _json_bytes(_error(request_id, "server_closed", "The live connection is closed."))

        try:
            result = self._dispatch({"id": request_id, "method": request["method"], "params": request["params"]})
            response = _json_bytes({"id": request_id, "result": result})
            if len(response) + 1 > MAX_RESPONSE_BYTES:
                response = _json_bytes(_error(request_id, "response_too_large", "The live response exceeds its size limit."))
        except Exception as exc:
            response = self._dispatch_error(request_id, exc)
        with self._lock:
            pending.response = response
            self._cache_bytes += len(response)
            pending.ready.set()
            self._evict()
        return response

    def _dispatch_error(self, request_id, exc):
        code = getattr(exc, "code", None)
        message = getattr(exc, "message", None)
        details = getattr(exc, "details", None)
        if (isinstance(code, str) and 1 <= len(code) <= 128
                and isinstance(message, str) and len(message) <= 4096
                and isinstance(details, dict)):
            try:
                response = _json_bytes(_error(request_id, code, message, details))
                if len(response) + 1 <= MAX_RESPONSE_BYTES:
                    return response
            except (ValueError, TypeError, UnicodeError, RecursionError):
                pass
        return _json_bytes(_error(request_id, "internal_error", "The live request could not be completed."))

    def _evict(self, make_room=False):
        for request_id in list(self._requests):
            if (len(self._requests) < _MAX_CACHE_ENTRIES if make_room else True) and self._cache_bytes <= _MAX_CACHE_BYTES:
                break
            pending = self._requests[request_id]
            # Never evict an in-flight reservation, even during cache pressure.
            if pending.response is not None:
                self._cache_bytes -= len(pending.response)
                del self._requests[request_id]


class LiveClient:
    """A stdlib-only live client. Connection failure never creates a session."""

    def __init__(self, descriptor_path_or_dict, timeout=30):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        self.timeout = timeout
        try:
            if isinstance(descriptor_path_or_dict, dict):
                descriptor = descriptor_path_or_dict
            else:
                descriptor = _read_descriptor(Path(descriptor_path_or_dict))
            self._descriptor = _validate_descriptor(descriptor)
        except LiveRemoteError:
            raise
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise LiveRemoteError("invalid_descriptor", "The live connection descriptor could not be read.") from exc

    def request(self, method, params=None, request_id=None):
        request_id = str(uuid4()) if request_id is None else request_id
        params = {} if params is None else params
        if (not _uuid_string(request_id) or not isinstance(method, str)
                or not 1 <= len(method) <= 128 or not isinstance(params, dict)):
            raise LiveRemoteError("invalid_request", "The live request envelope is invalid.")
        try:
            frame = _json_bytes({"id": request_id, "token": self._descriptor["token"],
                                 "method": method, "params": params}) + b"\n"
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise LiveRemoteError("invalid_request", "Live request parameters must be finite JSON values.") from exc
        if len(frame) > MAX_REQUEST_BYTES:
            raise LiveRemoteError("message_too_large", "The live request exceeds its size limit.")
        try:
            with socket.create_connection(("127.0.0.1", self._descriptor["port"]), self.timeout) as connection:
                connection.settimeout(self.timeout)
                connection.sendall(frame)
                with connection.makefile("rb") as stream:
                    response = _decode(_read_frame(stream, MAX_RESPONSE_BYTES))
        except LiveRemoteError:
            raise
        except TimeoutError as exc:
            raise LiveRemoteError("request_timeout", "The live request timed out; its outcome may be unknown.",
                                  {"request_id": request_id}) from exc
        except OSError as exc:
            raise LiveRemoteError("connection_error", "The live document owner could not be reached.",
                                  {"request_id": request_id}) from exc
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise LiveRemoteError("invalid_response", "The live document owner returned invalid JSON.") from exc
        if (not isinstance(response, dict) or response.get("id") != request_id
                or set(response) not in ({"id", "result"}, {"id", "error"})):
            raise LiveRemoteError("invalid_response", "The live response envelope is invalid.")
        if "error" in response:
            error = response["error"]
            if (not isinstance(error, dict) or set(error) != {"code", "message", "details"}
                    or not isinstance(error["code"], str) or not isinstance(error["message"], str)
                    or not isinstance(error["details"], dict)):
                raise LiveRemoteError("invalid_response", "The live error envelope is invalid.")
            raise LiveRemoteError(error["code"], error["message"], error["details"])
        return response["result"]
