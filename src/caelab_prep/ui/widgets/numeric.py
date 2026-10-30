"""Host-neutral engineering drafts; these controls never commit a document."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


class NumericEdit(QLineEdit):
    """A numeric draft that allows incomplete text and reports errors on Apply."""

    draftChanged = Signal()

    def __init__(self, value=None, *, unit="", minimum=None, maximum=None,
                 integer=False, parent=None):
        super().__init__(parent)
        self.unit = unit
        self.minimum = minimum
        self.maximum = maximum
        self.integer = integer
        self.error = ""
        self._committed_text = "" if value is None else str(value)
        self.setText(self._committed_text)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setMinimumWidth(64)
        self.setAccessibleDescription(f"Numeric value; {unit}" if unit else "Numeric value")
        self.textEdited.connect(self._edited)

    def _edited(self):
        self.set_error("")
        self.draftChanged.emit()

    @property
    def draft(self):
        return self.text()

    def numeric_value(self):
        try:
            value = float(self.text().strip())
            if not math.isfinite(value):
                raise ValueError("Enter a finite number")
            if self.integer and not value.is_integer():
                raise ValueError("Enter a whole number")
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"Minimum is {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"Maximum is {self.maximum}")
        except (ValueError, OverflowError) as exc:
            message = str(exc) if str(exc).startswith(("Enter", "Minimum", "Maximum")) else "Enter a valid number"
            self.set_error(message)
            raise ValueError(message) from exc
        self.set_error("")
        return int(value) if self.integer else value

    def set_error(self, message):
        self.error = str(message)
        self.setProperty("invalid", bool(message))
        self.setToolTip(str(message) or self.unit)
        self.setAccessibleDescription(str(message) or self.unit or "Numeric value")
        self.style().unpolish(self)
        self.style().polish(self)

    def accept_value(self, value):
        self._committed_text = str(value)
        self.setText(self._committed_text)
        self.set_error("")

    def convert_display(self, factor):
        value = self.numeric_value()
        committed = float(self._committed_text)
        self.setText(format(value * factor, ".12g"))
        self._committed_text = format(committed * factor, ".12g")
        if self.minimum is not None:
            self.minimum *= factor
        if self.maximum is not None:
            self.maximum *= factor

    def revert(self):
        self.setText(self._committed_text)
        self.set_error("")
        self.draftChanged.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.revert()
            event.accept()
        else:
            super().keyPressEvent(event)


class VectorEdit(QWidget):
    """One vector draft, validated together by the host's Apply action."""

    draftChanged = Signal()

    def __init__(self, values=(0, 0, 0), *, unit="", components=("X", "Y", "Z"), parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        editors = []
        for component, value in zip(components, values, strict=True):
            label = QLabel(component)
            editor = NumericEdit(value, unit=unit)
            editor.setAccessibleName(component)
            label.setBuddy(editor)
            layout.addWidget(label)
            layout.addWidget(editor, 1)
            editor.draftChanged.connect(self.draftChanged)
            editors.append(editor)
        self.editors = tuple(editors)
        self.setFocusProxy(self.editors[0])

    def numeric_value(self):
        values = []
        failure = None
        for editor in self.editors:
            try:
                values.append(editor.numeric_value())
            except ValueError as exc:
                failure = failure or exc
        if failure:
            raise failure
        return tuple(values)

    values = numeric_value

    def revert(self):
        for editor in self.editors:
            editor.revert()

    def set_error(self, message):
        for editor in self.editors:
            editor.set_error(message)
