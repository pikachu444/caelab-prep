"""Typed collection drafts shared by native properties and operation forms.

These widgets never submit document commands. Hosts read ``value()`` for a
validated value and retain ``raw_value()`` when an incomplete draft must survive.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QClipboard, QKeySequence, QValidator
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLineEdit, QListWidget,
                              QListWidgetItem, QMenu, QVBoxLayout, QWidget)

from .curve import CurveTable


class _IdTextLimit(QValidator):
    """Reject an entire edit before QLineEdit can publish a shortened ID list."""

    def __init__(self, maximum_bytes, parent):
        super().__init__(parent)
        self.maximum_bytes = maximum_bytes

    def validate(self, text, position):
        state = (QValidator.State.Acceptable if len(text.encode("utf-8", "surrogatepass")) <= self.maximum_bytes
                 else QValidator.State.Invalid)
        return state, text, position


class IntegerListEdit(QLineEdit):
    """A positive-ID draft; oversized input is rejected, never truncated.

    QLineEdit defaults to 32767 UTF-16 units and can silently shorten paste or
    IME input. Keep a one-unit canary above the explicit UTF-8 byte limit: even
    if Qt shortens an incoming edit to maxLength, the validator sees an invalid
    result and restores the entire previous text. UTF-8 uses at least as many
    bytes as UTF-16 units, including non-ASCII/IME input. Programmatic restores
    need their own check because setText bypasses QValidator.
    """

    draftChanged = Signal()
    MAX_INPUT_BYTES = 16 * 1024 * 1024

    def __init__(self, value=(), parent=None, *, maximum_bytes=MAX_INPUT_BYTES):
        super().__init__(parent)
        if type(maximum_bytes) is not int or not 0 < maximum_bytes <= self.MAX_INPUT_BYTES:
            raise ValueError("ID text size limit must be a positive integer up to 16 MiB")
        self.maximum_bytes = maximum_bytes
        self._input_error = ""
        self._help = (f"IDs separated by spaces or commas. Maximum text size: {maximum_bytes:,} UTF-8 bytes. "
                      "Larger edits are rejected without changing the existing IDs.")
        self.setMaxLength(maximum_bytes + 1)
        self.setValidator(_IdTextLimit(maximum_bytes, self))
        self.setPlaceholderText("IDs: 1, 2, 3")
        self.set_raw_value(value)
        self.textEdited.connect(self._edited)
        self.inputRejected.connect(self._rejected)

    def _edited(self, *_):
        self._input_error = ""
        self.setToolTip(self._help)
        self.draftChanged.emit()

    def _rejected(self):
        self._input_error = (f"ID text exceeds {self.maximum_bytes:,} UTF-8 bytes. "
                             "The entire edit was rejected; existing IDs are unchanged. Edit again or Revert/Cancel.")
        self.setToolTip(self._input_error)
        self.draftChanged.emit()

    def setText(self, text):
        if len(text.encode("utf-8", "surrogatepass")) > self.maximum_bytes:
            raise ValueError(f"ID text exceeds {self.maximum_bytes:,} UTF-8 bytes; existing IDs are unchanged")
        self._input_error = ""
        self.setToolTip(self._help)
        super().setText(text)

    def _can_insert(self, text):
        size = (len(self.text().encode("utf-8", "surrogatepass"))
                - len(self.selectedText().encode("utf-8", "surrogatepass"))
                + len(text.encode("utf-8", "surrogatepass")))
        if size > self.maximum_bytes:
            self._rejected()
            return False
        return True

    def insert(self, text):
        # Preflight bulk data before Qt allocates/shapes the inserted line.
        # The validator remains the final guard for native editing paths.
        if not self.isReadOnly() and self._can_insert(text):
            super().insert(text)

    def paste(self):
        self.insert(QApplication.clipboard().text())

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste(); event.accept()
        else:
            super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        # Native replacement offsets are in UTF-16 units; let Qt and the
        # validator handle them. Reject an oversized commit before shaping it.
        if len(event.commitString().encode("utf-8", "surrogatepass")) > self.maximum_bytes:
            self._rejected(); event.accept()
        else:
            super().inputMethodEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasText() and not self._can_insert(event.mimeData().text()):
            event.ignore()
        else:
            super().dropEvent(event)

    def mouseReleaseEvent(self, event):
        clipboard = QApplication.clipboard()
        if (event.button() == Qt.MouseButton.MiddleButton and clipboard.supportsSelection()
                and not self._can_insert(clipboard.text(QClipboard.Mode.Selection))):
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def createStandardContextMenu(self):
        # Qt's built-in Paste action calls the C++ slot directly. Route the
        # standard text actions through the same bulk-input preflight instead
        # of relying on private QAction names or translated label matching.
        menu = QMenu(self)
        writable, selected = not self.isReadOnly(), self.hasSelectedText()
        entries = (("Undo", self.undo, writable and self.isUndoAvailable()),
                   ("Redo", self.redo, writable and self.isRedoAvailable()), None,
                   ("Cut", self.cut, writable and selected), ("Copy", self.copy, selected),
                   ("Paste", self.paste, writable and QApplication.clipboard().mimeData().hasText()),
                   ("Delete", lambda: self.insert(""), writable and selected), None,
                   ("Select All", self.selectAll, bool(self.text())))
        for entry in entries:
            if entry is None:
                menu.addSeparator()
            else:
                label, callback, enabled = entry
                action = menu.addAction(self.tr(label)); action.triggered.connect(callback); action.setEnabled(enabled)
        return menu

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.exec(event.globalPos())
        menu.deleteLater()

    def value(self):
        if self._input_error:
            raise ValueError(self._input_error)
        text = self.text().strip()
        if not text:
            return ()
        tokens = re.split(r"[\s,]+", text)
        if any(not re.fullmatch(r"[0-9]+", token) or int(token) <= 0 for token in tokens):
            raise ValueError("Enter positive integer IDs separated by spaces or commas")
        values = tuple(int(token) for token in tokens)
        if len(set(values)) != len(values):
            raise ValueError("Each ID may occur only once")
        return values

    def raw_value(self):
        # Keep rejected-input diagnostics when a host preserves/rebuilds a draft.
        return {"text": self.text(), "input_error": self._input_error} if self._input_error else self.text()

    def set_raw_value(self, value):
        error = ""
        if isinstance(value, dict):
            if set(value) != {"text", "input_error"} or not all(isinstance(item, str) for item in value.values()):
                raise ValueError("Expected ID text and its rejected-input diagnostic")
            value, error = value["text"], value["input_error"]
        self.setText(value if isinstance(value, str) else ", ".join(str(item) for item in value))
        self._input_error = error
        if error:
            self.setToolTip(error)


class BooleanVectorEdit(QWidget):
    """One logical tuple with named component checkboxes."""

    draftChanged = Signal()
    is_multiline = False

    def __init__(self, value=(False, False, False), *, components=("X", "Y", "Z"), parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.editors = tuple(QCheckBox(str(component), self) for component in components)
        for component, editor in zip(components, self.editors):
            editor.setAccessibleName(str(component))
            editor.toggled.connect(self.draftChanged)
            row.addWidget(editor)
        row.addStretch(1)
        self.set_raw_value(value)

    def value(self):
        return tuple(editor.isChecked() for editor in self.editors)

    def raw_value(self):
        return self.value()

    def set_raw_value(self, value):
        value = tuple(value)
        if len(value) != len(self.editors) or any(type(item) is not bool for item in value):
            raise ValueError(f"Expected {len(self.editors)} boolean components")
        blocked = [QSignalBlocker(editor) for editor in self.editors]
        for editor, checked in zip(self.editors, value):
            editor.setChecked(checked)
        del blocked


class ReferenceListEdit(QWidget):
    """Check qualified object references by equality, keeping missing choices visible."""

    draftChanged = Signal()
    is_multiline = True

    def __init__(self, value=(), *, choices=(), choice_labels=(), parent=None):
        super().__init__(parent)
        self.choices = tuple(choices)
        self.choice_labels = tuple(choice_labels)
        self.list = QListWidget(self)
        self.list.setAccessibleName("Referenced objects")
        self.list.setMinimumHeight(120)
        self.list.setMaximumHeight(160)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list)
        self.list.itemChanged.connect(self.draftChanged)
        self.set_raw_value(value)

    def raw_value(self):
        return tuple(self.list.item(index).data(Qt.ItemDataRole.UserRole)
                     for index in range(self.list.count())
                     if self.list.item(index).checkState() == Qt.CheckState.Checked)

    def value(self):
        selected = self.raw_value()
        if any(ref not in self.choices for ref in selected):
            raise ValueError("A selected object is no longer available; uncheck it or choose an available object")
        return selected

    def set_raw_value(self, value):
        selected = tuple(value)
        blocked = QSignalBlocker(self.list)
        self.list.clear()
        displayed = []
        for index, ref in enumerate(self.choices):
            if ref in displayed:
                continue
            label = (self.choice_labels[index] if index < len(self.choice_labels)
                     else str(getattr(ref, "native_scope", None) or getattr(ref, "object_id", ref)))
            self._add_item(ref, label, ref in selected)
            displayed.append(ref)
        for ref in selected:
            if ref not in displayed:
                label = str(getattr(ref, "native_scope", None) or getattr(ref, "object_id", ref))
                self._add_item(ref, "Unavailable: " + label, True)
                displayed.append(ref)
        del blocked

    def _add_item(self, ref, label, checked):
        item = QListWidgetItem(str(label), self.list)
        item.setData(Qt.ItemDataRole.UserRole, ref)
        item.setToolTip(str(label))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)


class NumericTableEdit(CurveTable):
    """Two-column worksheet whose commit button belongs to the outer form."""

    is_multiline = True

    def __init__(self, value=(), *, components=("X", "Y"), minimum_rows=0,
                 maximum_rows=None, parent=None):
        if len(components) != 2:
            raise ValueError("The numeric worksheet requires two column labels")
        super().__init__(parent, minimum_points=minimum_rows, maximum_points=maximum_rows)
        self.set_points(value, headers=components)
        self.apply_button.hide()
        self.revert_button.hide()
        # An embedded worksheet already receives the property row's padding.
        # Avoid adding enough duplicate margin to force horizontal scrolling in
        # the narrow Settings/FORM inspector; keep every command label intact.
        toolbar_layout = self.layout().itemAt(0).widget().layout()
        margins = toolbar_layout.contentsMargins()
        toolbar_layout.setContentsMargins(4, margins.top(), 4, margins.bottom())
        self.setMinimumHeight(210)

    def sizeHint(self):
        return QSize(super().sizeHint().width(), 240)

    def value(self):
        return self.points()

    def raw_value(self):
        return self.draft_state()

    def set_raw_value(self, value):
        self.restore_draft(value)
