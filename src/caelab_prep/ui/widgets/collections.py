"""Typed collection drafts shared by native properties and operation forms.

These widgets never submit document commands. Hosts read ``value()`` for a
validated value and retain ``raw_value()`` when an incomplete draft must survive.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLineEdit, QListWidget,
                              QListWidgetItem, QVBoxLayout, QWidget)

from .curve import CurveTable


class IntegerListEdit(QLineEdit):
    """A list of positive IDs with no lossy numeric coercion."""

    draftChanged = Signal()

    def __init__(self, value=(), parent=None):
        super().__init__(parent)
        self.setPlaceholderText("IDs separated by spaces or commas")
        self.set_raw_value(value)
        self.textEdited.connect(self.draftChanged)

    def value(self):
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
        return self.text()

    def set_raw_value(self, value):
        self.setText(value if isinstance(value, str) else ", ".join(str(item) for item in value))


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
