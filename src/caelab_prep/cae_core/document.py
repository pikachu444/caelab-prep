from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from uuid import uuid4

from .errors import PrepError


class Resource(Protocol):
    """Opaque editable resource; the core knows neither solver nor renderer."""

    id: str
    kind: str

    def snapshot(self) -> Any: ...
    def restore(self, state: Any) -> None: ...
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


class CommandDispatcher:
    """Commit validated states, with the same revisions and events for every caller."""

    def __init__(self, document: Document):
        self.document = document
        self._undo: list[_Entry] = []
        self._redo: list[_Entry] = []
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

    def _emit(self, label: str, resource_id: str, objects: tuple[str, ...]) -> ChangeSet:
        self.document.revision += 1
        event = ChangeSet(self.document.id, self.document.revision, label, (resource_id,), objects)
        self.last_change = event
        for listener in tuple(self._listeners):
            # Observers cannot roll back an already committed model command.
            try:
                listener(event)
            except Exception:
                continue
        return event

    def execute(self, resource_id: str, state: Any, label: str, *,
                object_ids: tuple[str, ...] = (), expected_revision: int | None = None) -> ChangeSet | None:
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
        self._undo.append(_Entry(resource_id, before, resource.snapshot(), label, object_ids))
        self._redo.clear()
        return self._emit(label, resource_id, object_ids)

    def undo(self) -> ChangeSet:
        if not self._undo:
            raise PrepError("nothing_to_undo", "실행 취소할 변경이 없습니다.")
        entry = self._undo[-1]
        self.document.resources[entry.resource_id].restore(entry.before)
        self._undo.pop()
        self._redo.append(entry)
        return self._emit("실행 취소: " + entry.label, entry.resource_id, entry.object_ids)

    def redo(self) -> ChangeSet:
        if not self._redo:
            raise PrepError("nothing_to_redo", "다시 실행할 변경이 없습니다.")
        entry = self._redo[-1]
        self.document.resources[entry.resource_id].restore(entry.after)
        self._redo.pop()
        self._undo.append(entry)
        return self._emit("다시 실행: " + entry.label, entry.resource_id, entry.object_ids)
