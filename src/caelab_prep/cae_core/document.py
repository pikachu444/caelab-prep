from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from .errors import PrepError


class Resource(Protocol):
    """Opaque editable resource; the core knows neither solver nor renderer."""

    id: str
    kind: str

    def snapshot(self) -> Any: ...
    def restore(self, state: Any) -> None: ...
    def prepare_state(self, state: Any) -> Any:
        """Validate and normalize a candidate without mutating this resource."""
        ...
    def state_token(self) -> str: ...


@dataclass(frozen=True)
class ChangeSet:
    document_id: str
    revision: int
    label: str
    resource_ids: tuple[str, ...] = ()
    object_ids: tuple[str, ...] = ()
    kind: str = "field"

    def to_dict(self) -> dict:
        return {"document_id": self.document_id, "revision": self.revision,
                "label": self.label, "resource_ids": list(self.resource_ids),
                "object_ids": list(self.object_ids), "kind": self.kind}


@dataclass
class SaveState:
    tokens: tuple[tuple[str, str], ...] = ()
    path: str | None = None


@dataclass(frozen=True)
class SelectionRef:
    resource_id: str
    entity_kind: str
    local_id: int


@dataclass
class Selection:
    kind: str | None = None
    ids: tuple[int, ...] = ()
    refs: tuple[SelectionRef, ...] = ()


@dataclass
class Document:
    name: str
    id: str = field(default_factory=lambda: str(uuid4()))
    revision: int = 0
    resources: dict[str, Resource] = field(default_factory=dict)
    save_state: SaveState = field(default_factory=SaveState)
    selection: Selection = field(default_factory=Selection)

    def tokens(self) -> tuple[tuple[str, str], ...]:
        return tuple((key, value.state_token()) for key, value in sorted(self.resources.items()))

    @property
    def dirty(self) -> bool:
        return self.tokens() != self.save_state.tokens

    def mark_saved(self, path: str | None = None) -> None:
        self.save_state = SaveState(self.tokens(), path)


@dataclass(frozen=True)
class _Entry:
    resource_id: str
    before: Any
    after: Any
    label: str
    object_ids: tuple[str, ...]
    kind: str = "field"


_ABSENT = object()


@dataclass(frozen=True)
class _ResourceChange:
    resource: Resource
    before: Any
    after: Any


@dataclass(frozen=True)
class _BatchEntry:
    changes: tuple[_ResourceChange, ...]
    label: str
    object_ids: tuple[str, ...]
    kind: str


class CommandDispatcher:
    """Commit validated states, with the same revisions and events for every caller."""

    def __init__(self, document: Document):
        self.document = document
        self._undo: list[_Entry | _BatchEntry] = []
        self._redo: list[_Entry | _BatchEntry] = []
        self._listeners: list[Callable[[ChangeSet], None]] = []
        self.last_change: ChangeSet | None = None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def subscribe(self, listener: Callable[[ChangeSet], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def _emit(self, label: str, resource_id: str | tuple[str, ...], objects: tuple[str, ...], kind: str = "field") -> ChangeSet:
        self.document.revision += 1
        resource_ids = (resource_id,) if isinstance(resource_id, str) else resource_id
        event = ChangeSet(self.document.id, self.document.revision, label, resource_ids, objects, kind)
        self.last_change = event
        for listener in tuple(self._listeners):
            # Observers cannot roll back an already committed model command.
            try:
                listener(event)
            except Exception:
                continue
        return event

    def execute(self, resource_id: str, state: Any, label: str, *,
                object_ids: tuple[str, ...] = (), expected_revision: int | None = None,
                kind: str = "field") -> ChangeSet | None:
        if expected_revision is not None and expected_revision != self.document.revision:
            raise PrepError("revision_conflict", "모델이 변경됐습니다. 현재 값을 다시 읽어 주세요.",
                            {"expected": expected_revision, "actual": self.document.revision})
        resource = self.document.resources[resource_id]
        before = resource.snapshot()
        if before == state:
            return None
        # Resource.restore must validate before assigning; keep a rollback as a last boundary.
        try:
            resource.restore(state)
        except Exception:
            resource.restore(before)
            raise
        self._undo.append(_Entry(resource_id, before, resource.snapshot(), label, object_ids, kind))
        self._redo.clear()
        return self._emit(label, resource_id, object_ids, kind)

    @staticmethod
    def _prepare(resource: Resource, state: Any) -> Any:
        prepare = getattr(resource, "prepare_state", None)
        if not callable(prepare):
            raise PrepError("transaction_unsupported", "The resource does not provide non-mutating candidate validation.",
                            {"resource_id": resource.id, "kind": resource.kind})
        return prepare(state)

    def _apply_many(self, changes: tuple[_ResourceChange, ...], *, forward: bool) -> None:
        """Called under the owning application's lock; publish no intermediate event.

        Resource snapshots contain deltas/immutable payload references, not whole
        mesh copies. A resource must validate candidates without touching live
        state, and must be able to restore its own previously valid snapshot.
        """
        registry = self.document.resources
        prepared, backups = [], []
        for change in changes:
            resource = change.resource
            expected = change.before if forward else change.after
            target = change.after if forward else change.before
            present = registry.get(resource.id, _ABSENT)
            if (expected is _ABSENT and present is not _ABSENT) or (expected is not _ABSENT and present is not resource):
                raise PrepError("resource_conflict", "The resource registry changed outside its command history.", {"resource_id": resource.id})
            backups.append((resource, resource.snapshot()))
            prepared.append((resource, _ABSENT if target is _ABSENT else self._prepare(resource, target)))
        attempted = []
        try:
            for (resource, state), (_, backup) in zip(prepared, backups):
                if state is not _ABSENT:
                    attempted.append((resource, backup))
                    resource.restore(state)
            # Registry membership is published once after every restore succeeds.
            updated = dict(registry)
            for resource, state in prepared:
                if state is _ABSENT:
                    del updated[resource.id]
                else:
                    updated[resource.id] = resource
            self.document.resources = updated
        except Exception as error:
            rollback_errors = []
            for resource, backup in reversed(attempted):
                try:
                    resource.restore(backup)
                except Exception as rollback:
                    rollback_errors.append((resource.id, str(rollback)))
            if rollback_errors:
                raise PrepError("transaction_rollback_failed", "A resource could not restore its previously valid state.",
                                {"resources": rollback_errors}) from error
            raise

    def execute_many(self, states: Mapping[str, Any], label: str, *, additions: tuple[Resource, ...] = (),
                     removals: tuple[str, ...] = (), object_ids: tuple[str, ...] = (),
                     expected_revision: int | None = None, kind: str = "structure") -> ChangeSet | None:
        """Validate all affected resources, commit once, and retain one Undo entry.

        Adds/removes participate in the same transaction. Cross-resource domain
        references must be checked by the caller against its complete candidate
        before submitting this solver-independent command.
        """
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision != self.document.revision):
            raise PrepError("revision_conflict", "모델이 변경됐습니다. 현재 값을 다시 읽어 주세요.",
                            {"expected": expected_revision, "actual": self.document.revision})
        if not isinstance(states, Mapping):
            raise PrepError("invalid_command", "Resource states must be an ID-to-state mapping.")
        added = {resource.id: resource for resource in additions}
        if len(added) != len(additions) or len(set(removals)) != len(removals) or set(added) & set(removals):
            raise PrepError("invalid_command", "Resource membership changes must have distinct identities.")
        if set(added) & set(self.document.resources):
            raise PrepError("resource_conflict", "An added resource identity already exists.")
        if set(removals) - set(self.document.resources) or set(states) & set(removals):
            raise PrepError("invalid_command", "Cannot edit a removed or missing resource.")
        available = {**self.document.resources, **added}
        if set(states) - set(available):
            raise PrepError("resource_not_found", "A transaction target resource is missing.")
        changes = []
        for identifier in dict.fromkeys((*states, *added, *removals)):
            resource = available[identifier]
            before = _ABSENT if identifier in added else resource.snapshot()
            after = (_ABSENT if identifier in removals else
                     self._prepare(resource, states.get(identifier, resource.snapshot())))
            if before is _ABSENT or after is _ABSENT or before != after:
                changes.append(_ResourceChange(resource, before, after))
        if not changes:
            return None
        entry = _BatchEntry(tuple(changes), label, object_ids, kind)
        self._apply_many(entry.changes, forward=True)
        self._undo.append(entry)
        self._redo.clear()
        return self._emit(label, tuple(change.resource.id for change in entry.changes), object_ids, kind)

    def undo(self) -> ChangeSet:
        if not self._undo:
            raise PrepError("nothing_to_undo", "실행 취소할 변경이 없습니다.")
        entry = self._undo[-1]
        if isinstance(entry, _BatchEntry):
            self._apply_many(entry.changes, forward=False)
        else:
            self.document.resources[entry.resource_id].restore(entry.before)
        self._undo.pop()
        self._redo.append(entry)
        resources = tuple(change.resource.id for change in entry.changes) if isinstance(entry, _BatchEntry) else entry.resource_id
        return self._emit("실행 취소: " + entry.label, resources, entry.object_ids, entry.kind)

    def redo(self) -> ChangeSet:
        if not self._redo:
            raise PrepError("nothing_to_redo", "다시 실행할 변경이 없습니다.")
        entry = self._redo[-1]
        if isinstance(entry, _BatchEntry):
            self._apply_many(entry.changes, forward=True)
        else:
            self.document.resources[entry.resource_id].restore(entry.after)
        self._redo.pop()
        self._undo.append(entry)
        resources = tuple(change.resource.id for change in entry.changes) if isinstance(entry, _BatchEntry) else entry.resource_id
        return self._emit("다시 실행: " + entry.label, resources, entry.object_ids, entry.kind)
