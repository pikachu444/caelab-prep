"""Host-neutral engineering drafts; these controls never commit a document."""

from __future__ import annotations

import math

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..design import TOKENS


def _display_factor(factor):
    """Unit scales cannot reverse bounds, erase values, or create infinities."""
    try:
        value = float(factor)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Unit scale must be a finite positive number") from exc
    if isinstance(factor, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("Unit scale must be a finite positive number")
    return value


def _scaled(value, factor):
    try:
        result = value * factor
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Unit conversion would produce a non-finite number") from exc
    if not math.isfinite(result):
        raise ValueError("Unit conversion would produce a non-finite number")
    if value != 0 and result == 0:
        raise ValueError("Unit conversion would underflow a nonzero value")
    return result


def _display_text(value):
    # Keep a round-trip representation without showing an unnecessary .0.
    text = str(value)
    return text[:-2] if text.endswith(".0") else text


class NumericEdit(QLineEdit):
    """Preserved QLineEdit draft adapter: incomplete text remains valid input state."""

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
        self.setMinimumWidth(TOKENS["numeric_min_width"])
        self.setAccessibleDescription(f"Numeric value; {unit}" if unit else "Numeric value")
        self.textEdited.connect(self._edited)

    def _edited(self):
        self.set_error("")
        self.draftChanged.emit()

    @property
    def draft(self):
        return self.text()

    @property
    def unit(self):
        return self._unit

    @unit.setter
    def unit(self, unit):
        self._unit = str(unit)
        error = getattr(self, "error", "")
        self.setToolTip(error or self._unit)
        self.setAccessibleDescription(error or self._unit or "Numeric value")

    def _validated_value(self, text, *, check_bounds=True):
        """Validate without changing the input or its error presentation."""
        try:
            value = float(text.strip())
        except (ValueError, OverflowError) as exc:
            raise ValueError("Enter a valid number") from exc
        if not math.isfinite(value):
            raise ValueError("Enter a finite number")
        if self.integer and not value.is_integer():
            raise ValueError("Enter a whole number")
        if check_bounds and self.minimum is not None and value < self.minimum:
            raise ValueError(f"Minimum is {self.minimum}")
        if check_bounds and self.maximum is not None and value > self.maximum:
            raise ValueError(f"Maximum is {self.maximum}")
        return int(value) if self.integer else value

    def numeric_value(self):
        try:
            value = self._validated_value(self.text())
        except ValueError as exc:
            self.set_error(str(exc))
            raise
        self.set_error("")
        return value

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
        self._apply_display_conversion(self._display_conversion_plan(_display_factor(factor)))

    def _display_conversion_plan(self, factor):
        """Calculate every changed value before the first widget mutation."""
        value = _scaled(self._validated_value(self.text()), factor)
        committed = (_scaled(self._validated_value(self._committed_text, check_bounds=False), factor)
                     if self._committed_text.strip() else None)
        minimum = _scaled(self.minimum, factor) if self.minimum is not None else None
        maximum = _scaled(self.maximum, factor) if self.maximum is not None else None
        if self.integer and (not value.is_integer() or (committed is not None and not committed.is_integer())):
            raise ValueError("Unit conversion would produce a fractional whole-number field")
        return (_display_text(value), _display_text(committed) if committed is not None else "",
                minimum, maximum, self.isModified(), self.cursorPosition(),
                self.selectionStart(), len(self.selectedText()))

    def _apply_display_conversion(self, plan):
        text, committed, minimum, maximum, modified, cursor, start, length = plan
        self._committed_text, self.minimum, self.maximum = committed, minimum, maximum
        self.setText(text)
        self.setModified(modified)
        if start >= 0:
            self.setSelection(min(start, len(text)), min(length, max(0, len(text) - start)))
        else:
            self.setCursorPosition(min(cursor, len(text)))
        self.set_error("")

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
        self.setObjectName("vectorEdit")
        stack = QVBoxLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(3)
        editors = []
        for component, value in zip(components, values, strict=True):
            cell = QFrame()
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            label = QLabel(str(component))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedWidth(22)
            label.setStyleSheet(f"background: {TOKENS['raised']}; color: {TOKENS['muted']}; padding: 5px 0;")
            editor = NumericEdit(value, unit=unit)
            editor.setAccessibleName(component)
            label.setBuddy(editor)
            row.addWidget(label)
            row.addWidget(editor, 1)
            stack.addWidget(cell)
            editor.draftChanged.connect(self.draftChanged)
            editors.append(editor)
        self.editors = tuple(editors)
        self.unit = unit
        self.setFocusProxy(self.editors[0])

    @property
    def unit(self):
        return self._unit

    @unit.setter
    def unit(self, unit):
        self._unit = str(unit)
        self.setToolTip(self._unit)
        self.setAccessibleDescription(self._unit or "Vector value")
        for editor in self.editors:
            editor.unit = self._unit

    def convert_display(self, factor):
        factor = _display_factor(factor)
        plans = tuple(editor._display_conversion_plan(factor) for editor in self.editors)
        # Observers cannot see a mixture of old and new component units during
        # the display update. The host still owns its one unit-change signal.
        blocked = [QSignalBlocker(editor) for editor in self.editors]
        for editor, plan in zip(self.editors, plans, strict=True):
            editor._apply_display_conversion(plan)
        del blocked

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
