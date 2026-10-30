"""One action instance can be shared by menus, toolbars and keyboard shortcuts."""

from PySide6.QtGui import QAction

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
