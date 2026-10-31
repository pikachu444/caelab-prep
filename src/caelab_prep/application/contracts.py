"""Small host contracts: no solver, Qt, renderer or gallery dependencies.

Observers run on the committing caller's thread; UI hosts must queue delivery.
Drafts belong to widgets, while sessions own committed values and history.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class ObjectRef:
    document_id: str
    resource_id: str
    object_id: str
    kind: str
    native_scope: str | None = None
    mesh_revision: int | None = None


@dataclass(frozen=True)
class PropertySpec:
    name: str
    label: str
    value: object
    kind: str = "number"
    group: str = "Properties"
    unit: str = ""
    unit_choices: tuple[str, ...] = ()
    editable: bool = True
    components: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[object, ...] = ()
    unit_context: dict = field(default_factory=dict)
    coordinate_frame: str | None = None
    unit_scales: tuple[tuple[str, float], ...] = ()
    choice_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class TreeNode:
    ref: ObjectRef
    label: str
    group: str
    icon: str = "card"
    tooltip: str = ""


@dataclass(frozen=True)
class SetProperties:
    target: ObjectRef
    values: dict[str, object]
    expected_revision: int
    units: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Draft:
    target: ObjectRef
    base_revision: int
    texts: dict[str, str]


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    shortcut: str = ""
    capability: str = ""
    icon: str = ""
    contexts: tuple[str, ...] = ()
    checkable: bool = False


@dataclass(frozen=True)
class OperationState:
    operation_id: str
    status: Literal["running", "succeeded", "failed", "cancelled"]
    cancellable: bool = False
    artifacts: tuple[str, ...] = ()
    error: dict | None = None


@runtime_checkable
class PropertyHost(Protocol):
    """A future consumer may use Apply without implementing a Prep document."""
    def describe(self) -> dict: ...
    def tree_nodes(self) -> list[TreeNode]: ...
    def properties(self, target: ObjectRef) -> list[PropertySpec]: ...
    def submit(self, command: SetProperties) -> dict: ...
    def subscribe(self, listener: Callable[[dict], None]) -> Callable[[], None]: ...


@runtime_checkable
class SelectionProvider(Protocol):
    """Active object identity is shared; domain-specific highlighting stays hosted."""
    def select(self, target: ObjectRef | None) -> object: ...
    def active_object(self) -> ObjectRef | None: ...


class DocumentSession(PropertyHost, SelectionProvider, Protocol):
    def undo(self) -> dict: ...
    def redo(self) -> dict: ...
    def save_project(self, path: str) -> dict: ...
    def open_project(self, path: str) -> dict: ...


class ContainerCodec(Protocol):
    format: str
    version: int
    def encode(self, document: object) -> tuple[dict, dict[str, bytes]]: ...
    def decode(self, manifest: dict, members: dict[str, bytes]) -> object: ...
