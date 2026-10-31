"""One action instance can be shared by menus, toolbars and keyboard shortcuts."""

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction

from ..application.contracts import ActionSpec

from .theme import icon


def create_action(parent, key, label, callback, shortcut=None, *, checkable=False):
    action = QAction(icon(key), label, parent)
    action.setObjectName(key)
    action.setCheckable(checkable)
    if shortcut:
        action.setShortcut(shortcut)
    action.setStatusTip(label.replace("…", ""))
    action.triggered.connect(callback)
    return action


class ActionRegistry(QObject):
    """Own command identity and derive presentation state from a host description."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.specs = {}
        self.actions = {}

    def register(self, spec: ActionSpec, callback):
        if spec.key in self.actions:
            raise ValueError(f"Action already registered: {spec.key}")
        action = create_action(self, spec.icon or spec.key, spec.label, callback,
                               spec.shortcut, checkable=spec.checkable)
        action.setObjectName(spec.key)
        action.setProperty("capability", spec.capability)
        self.specs[spec.key] = spec
        self.actions[spec.key] = action
        return action

    def action(self, key):
        return self.actions[key]

    def refresh(self, description, *, busy=False, context="", enabled=None, checked=None):
        capabilities = description.get("capabilities", {})
        for key, spec in self.specs.items():
            available = not spec.capability or bool(capabilities.get(spec.capability, False))
            available = available and (not spec.contexts or context in spec.contexts)
            state = available and not busy and (enabled or {}).get(key, True)
            if key in ("edit.undo", "edit.redo"):
                state = state and bool(description.get("can_" + key.split(".")[-1]))
            self.actions[key].setEnabled(state)
            if key in (checked or {}):
                self.actions[key].setChecked(checked[key])
