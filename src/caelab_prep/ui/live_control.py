"""Authenticated transport requests executed by the existing Qt document owner.

There is no background copy of the model. Network threads enqueue work; only
this QObject's GUI-thread slot calls the window's provider and session.
"""
from collections import deque
from dataclasses import asdict, is_dataclass
from pathlib import Path
import secrets
import threading
from uuid import uuid4

from PySide6.QtCore import QObject, Qt, Signal, Slot, QThread
from PySide6.QtWidgets import QApplication, QLineEdit

from ..application.contracts import ObjectRef, SetProperties
from ..application.live_transport import LiveServer
from ..cae_core import PrepError
from .mesh_workflow import MeshCandidateDialog


METHODS = ("hello", "document.describe", "document.cards", "document.properties", "document.selection",
           "document.select", "document.edit", "document.undo", "document.redo", "document.save",
           "events.since", "mesh.start", "jobs.get", "jobs.cancel", "jobs.close")
_QUEUE_TIMEOUT_SECONDS = 30.0


def json_value(value):
    if is_dataclass(value): return json_value(asdict(value))
    if isinstance(value, dict): return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [json_value(item) for item in value]
    return value


class _Pending:
    def __init__(self, request):
        self.request, self.event, self.lock = request, threading.Event(), threading.Lock()
        self.state, self.result, self.error = "queued", None, None


class _LiveCandidateDialog(MeshCandidateDialog):
    """Observe every existing workflow task, including GUI-initiated successors."""
    taskStarted = Signal(object, bool, object)
    taskFinished = Signal(object, object, bool)

    def _start(self, function):
        stamp = self.session.describe()
        started = super()._start(function)
        if started: self.taskStarted.emit(self._task, self._adopting, stamp)
        return started

    def _completed(self, result):
        adopting = self._adopting
        super()._completed(result)
        self.taskFinished.emit(result, None, adopting)

    def _failed(self, error):
        adopting = self._adopting
        super()._failed(error)
        self.taskFinished.emit(None, error, adopting)


class LiveControl(QObject):
    requested = Signal(object)
    sessionEvent = Signal(object)
    changed = Signal(dict)

    def __init__(self, host, descriptor_path):
        super().__init__(host)
        self.host, self.session = host, host.session
        self._closing = self._closed = False
        self._sequence = 0
        self._events = deque(maxlen=512)
        self._jobs = {}
        self.requested.connect(self._execute_queued, Qt.ConnectionType.QueuedConnection)
        self.sessionEvent.connect(self._session_event, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = self.session.subscribe(self.sessionEvent.emit)
        try: self.server = LiveServer(self._dispatch, descriptor_path)
        except Exception:
            self._unsubscribe(); raise
        self._descriptor_path = str(Path(descriptor_path).resolve())
        self._publish("connection", {"status": "listening"})

    def status(self):
        descriptor = self.server.descriptor()
        return {"status": "closed" if self._closed else "stopping" if self._closing else "listening",
                "host": descriptor["host"], "port": descriptor["port"], "server_id": descriptor["server_id"],
                "descriptor_path": self._descriptor_path, "active_jobs": self._active_jobs()}

    def _dispatch(self, request):
        pending = _Pending(request)
        self.requested.emit(pending)
        if not pending.event.wait(_QUEUE_TIMEOUT_SECONDS):
            with pending.lock:
                if pending.state == "queued":
                    pending.state = "cancelled"
                    raise PrepError("request_timeout", "GUI did not accept the queued request; no command was applied.")
            # A running save cannot be rolled back by a disconnected client.
            # Keep its idempotency reservation until the actual result is known.
            pending.event.wait()
        if pending.error is not None: raise pending.error
        return pending.result

    @Slot(object)
    def _execute_queued(self, pending):
        assert QThread.currentThread() == self.thread()
        with pending.lock:
            if pending.state == "cancelled": return
            pending.state = "started"
        try:
            if self._closed or self._closing: raise PrepError("server_closed", "Live control is stopping.")
            pending.result = json_value(self._request(pending.request["method"], pending.request["params"]))
        except Exception as exc: pending.error = exc
        finally:
            with pending.lock: pending.state = "done"
            pending.event.set()

    def _handle(self):
        description = self.session.describe()
        return {key: description[key] for key in ("document_id", "document_epoch", "revision")}

    def _draft_pending(self):
        # Do not close a user's active table delegate just to answer a query.
        focused = QApplication.focusWidget()
        if isinstance(focused, QLineEdit) and self.host.curve_table.table.isAncestorOf(focused): return True
        return bool(self.host.file_edits.has_draft())

    def _owner_state(self):
        return {"draft_pending": self._draft_pending(), "busy": bool(self.host._busy or self._active_jobs()),
                "modal": QApplication.activeModalWidget() is not None}

    def _guard(self, handle):
        if not isinstance(handle, dict) or set(handle) != {"document_id", "document_epoch", "revision"}:
            raise PrepError("invalid_handle", "Send the complete document handle returned by document.describe.")
        current = self._handle()
        if handle.get("document_id") != current["document_id"] or handle.get("document_epoch") != current["document_epoch"]:
            raise PrepError("document_conflict", "The GUI document was replaced. Query its current handle.", {"actual": current})
        if type(handle.get("revision")) is not int or handle["revision"] != current["revision"]:
            raise PrepError("revision_conflict", "The GUI document changed. Query its current handle.", {"actual": current})
        owner = self._owner_state()
        if owner["draft_pending"]:
            raise PrepError("draft_pending", "Finish or discard the GUI draft before changing the document remotely.")
        if owner["busy"] or owner["modal"]:
            raise PrepError("owner_busy", "The GUI has an active operation or dialog; query or cancel its owned job first.")

    @staticmethod
    def _keys(params, required=(), optional=()):
        if not isinstance(params, dict) or set(required) - set(params) or set(params) - set(required) - set(optional):
            raise PrepError("invalid_request", "Request parameters do not match the advertised method.",
                            {"required": list(required), "optional": list(optional)})

    @staticmethod
    def _ref(value):
        try:
            if not isinstance(value, dict): raise TypeError()
            return ObjectRef(**value)
        except TypeError: raise PrepError("invalid_reference", "Send the typed object reference returned by document.cards.") from None

    def _request(self, method, params):
        if method not in METHODS: raise PrepError("method_not_found", "Unsupported live-control method.")
        if method in ("hello", "document.describe"):
            self._keys(params)
            return {"protocol_version": 1, "server_id": self.server.descriptor()["server_id"],
                    "methods": METHODS, "handle": self._handle(), "document": self.session.describe(),
                    "owner": self._owner_state(), "event_sequence": self._sequence,
                    "limits": {"edit": "provider scalar number/bool fields only", "mesh": "candidate generation, query and creator-capability cancellation; adoption remains in GUI"}}
        if method == "document.cards":
            self._keys(params)
            return {"handle": self._handle(), "cards": self.host.provider.tree_nodes()}
        if method == "document.properties":
            self._keys(params, ("target",))
            return {"handle": self._handle(), "properties": self.host.provider.properties(self._ref(params["target"]))}
        if method == "document.selection":
            self._keys(params)
            return {"handle": self._handle(), "selection": self.session.selection() if self.session.document else None}
        if method == "events.since":
            self._keys(params, ("after",))
            after = params["after"]
            if type(after) is not int or after < 0 or after > self._sequence:
                raise PrepError("invalid_request", "Event cursor must be a nonnegative known sequence.")
            if self._events and after < self._events[0]["sequence"] - 1:
                raise PrepError("event_gap", "The event buffer expired. Query the document and use its new event_sequence.")
            return {"events": [event for event in self._events if event["sequence"] > after], "event_sequence": self._sequence,
                    "handle": self._handle()}
        if method.startswith("jobs."): return self._job_request(method, params)
        if method == "mesh.start":
            self._keys(params, ("handle", "source", "output", "size", "dimension"), ("interface_policy", "local_sizes"))
            with self.session._lock:
                self._guard(params["handle"])
                return self._start_mesh(params)
        # Hold the existing session lock across the revision check and command.
        # This also serializes direct in-process callers using that same owner.
        with self.session._lock:
            required = {"document.select": ("handle", "target"), "document.edit": ("handle", "target", "values"),
                        "document.save": ("handle", "path"), "document.undo": ("handle",), "document.redo": ("handle",)}[method]
            self._keys(params, required, ("units",) if method == "document.edit" else ())
            self._guard(params["handle"])
            if method == "document.edit":
                ref = self._ref(params["target"])
                specs = {item.name: item for item in self.host.provider.properties(ref)}
                values = params["values"]
                if not isinstance(values, dict) or not values or any(key not in specs or not specs[key].editable or specs[key].kind not in ("number", "bool") for key in values):
                    raise PrepError("unsupported_operation", "Live edit supports writable scalar number/bool properties only.")
                result = self.host.provider.submit(SetProperties(ref, values, params["handle"]["revision"], params.get("units", {})))
            elif method == "document.select": result = self.host.provider.select(self._ref(params["target"]))
            elif method == "document.undo": result = self.session.undo()
            elif method == "document.redo": result = self.session.redo()
            else:
                if not isinstance(params["path"], str) or not params["path"]: raise PrepError("invalid_request", "A work-document path is required.")
                result = self.session.save_project(params["path"])
            self.host.refresh_document()
            return {"handle": self._handle(), "result": result}

    @Slot(object)
    def _session_event(self, event):
        if not self._closed: self._publish("session", event)

    def _publish(self, kind, payload):
        self._sequence += 1
        event = {"sequence": self._sequence, "kind": kind, "payload": json_value(payload)}
        self._events.append(event)
        self.changed.emit(event)

    def _active_jobs(self):
        return [key for key, job in self._jobs.items() if job["status"] in ("running", "cancel_requested")]

    def _start_mesh(self, params):
        if len(self._jobs) >= 64: raise PrepError("job_limit", "Close and restart live control after 64 retained jobs.")
        if not isinstance(params["source"], str) or not isinstance(params["output"], str):
            raise PrepError("invalid_request", "Source and output paths must be strings.")
        if type(params["dimension"]) is not int or params["dimension"] not in (2, 3):
            raise PrepError("invalid_request", "Mesh dimension must be 2 or 3.")
        # The existing GUI controller owns generation and its actual cancel event.
        dialog = _LiveCandidateDialog(self.session, self.host, enable_viewport=self.host.viewport is not None)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.source.setText(params["source"]); dialog.output.setText(params["output"])
        dialog.size.setText(str(params["size"]))
        dialog.dimension.setCurrentIndex(dialog.dimension.findData(params["dimension"]))
        policy = params.get("interface_policy", "preserve")
        index = dialog.policy.findData(policy)
        if index < 0: dialog.deleteLater(); raise PrepError("invalid_request", "Unknown interface policy.")
        dialog.policy.setCurrentIndex(index)
        if params.get("local_sizes"):
            dialog.deleteLater()
            raise PrepError("unsupported_operation", "The live initial-generation endpoint does not configure local entity sizing; use the candidate UI.")
        key, cancellation = str(uuid4()), secrets.token_urlsafe(32)
        job = {"id": key, "status": "idle", "handle": self._handle(), "dialog": dialog,
               "task": None, "cancel_token": cancellation, "result": None, "error": None,
               "generation": 0, "operation": "candidate", "cancellable": True}
        self._jobs[key] = job
        dialog.taskStarted.connect(lambda task, adopting, stamp: self._job_started(key, task, adopting, stamp))
        dialog.taskFinished.connect(lambda result, error, adopting: self._job_finished(key, result, error, adopting))
        if not dialog.generate():
            message = dialog.error.text(); dialog.deleteLater(); self._jobs.pop(key)
            raise PrepError("invalid_request", message or "Mesh generation did not start.")
        dialog.show()
        return {**self._job_view(job), "cancel_token": cancellation}

    @staticmethod
    def _job_view(job):
        return {key: job[key] for key in ("id", "status", "handle", "generation", "operation", "cancellable", "result", "error")}

    def _job_started(self, job_id, task, adopting, stamp):
        job = self._jobs[job_id]
        handle = {key: stamp[key] for key in ("document_id", "document_epoch", "revision")}
        job.update(task=task, status="running", handle=handle, generation=job["generation"] + 1,
                   operation="adopt" if adopting else "candidate", cancellable=not adopting, result=None, error=None)
        self._publish("job", self._job_view(job))

    def _job_finished(self, job_id, result, error, adopting):
        job = self._jobs[job_id]
        if error is not None:
            job["status"] = "cancelled" if not adopting and getattr(error, "code", None) == "cancelled" else "failed"
            job["error"] = {"code": getattr(error, "code", "mesh_failed"), "message": str(error), "details": getattr(error, "details", {})}
        elif not adopting and job["dialog"]._cancel.is_set():
            job["status"] = "cancelled"
        elif adopting:
            job.update(status="succeeded", result={"adopted": True, "adoption": result})
        else:
            job.update(status="succeeded", result={"mesh_uuid": result.mesh_uuid, "dimension": result.dimension,
                "node_count": len(result.nodes), "cell_count": len(result.cells),
                "quality_passed": result.quality.passed, "assets": [asdict(asset) for asset in result.assets], "adopted": False})
        self._publish("job", self._job_view(job))
        if self._closing and not self._active_jobs(): self.close()

    def _job_request(self, method, params):
        self._keys(params, ("job_id",) if method == "jobs.get" else ("job_id", "cancel_token"))
        key = params["job_id"]
        job = self._jobs.get(key) if isinstance(key, str) else None
        if job is None: raise PrepError("job_not_found", "This GUI owner does not know the job.")
        if method != "jobs.get":
            token = params["cancel_token"]
            if not isinstance(token, str) or not secrets.compare_digest(token, job["cancel_token"]):
                raise PrepError("job_ownership", "Only the job creator's cancellation capability can control this job.")
        if method == "jobs.cancel" and job["status"] == "running":
            if not job["cancellable"]:
                raise PrepError("operation_not_cancellable", "Native adoption is atomic and cannot be cancelled. Wait for its actual result.")
            job["dialog"]._cancel.set(); job["status"] = "cancel_requested"
            self._publish("job", self._job_view(job))
        elif method == "jobs.close":
            if job["status"] in ("running", "cancel_requested"):
                raise PrepError("owner_busy", "Wait for worker cancellation/termination before closing the candidate.")
            job["dialog"].reject()
        return self._job_view(job)

    def close(self):
        if self._closed: return True
        if self._active_jobs():
            self._closing = True
            for key in self._active_jobs():
                if self._jobs[key]["cancellable"]:
                    self._jobs[key]["dialog"]._cancel.set()
                    self._jobs[key]["status"] = "cancel_requested"
            self.changed.emit({"status": "stopping"})
            return False
        self._closed = True; self._unsubscribe()
        for job in self._jobs.values(): job["dialog"].reject()
        self.server.close()
        self.changed.emit({"status": "closed"})
        return True
