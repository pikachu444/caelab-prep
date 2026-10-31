"""Atomic tabular curve drafts and a lightweight Qt-only engineering plot."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFrame,
                              QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton,
                              QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..design import TOKENS


def validate_points(points, *, minimum_points=1, require_increasing_x=False):
    result = []
    for row, point in enumerate(points, 1):
        if len(point) != 2:
            raise ValueError(f"Row {row}: expected two columns")
        try:
            pair = tuple(float(v) for v in point)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Row {row}: enter two valid numbers") from exc
        if not all(math.isfinite(v) for v in pair):
            raise ValueError(f"Row {row}: enter finite numbers")
        result.append(pair)
    if len(result) < minimum_points:
        raise ValueError(f"A curve needs at least {minimum_points} point(s)")
    if require_increasing_x and any(b[0] <= a[0] for a, b in zip(result, result[1:])):
        raise ValueError("X values must increase strictly; no rows were applied")
    return tuple(result)


class _CurveGrid(QTableWidget):
    pasteRequested = Signal(str)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.pasteRequested.emit(QApplication.clipboard().text())
            event.accept()
        else:
            super().keyPressEvent(event)


class CurveTable(QWidget):
    """Table edits are a preview until Apply; a host handles one emitted command."""

    pointsEdited = Signal(object)
    draftChanged = Signal()

    def __init__(self, parent=None, *, minimum_points=1, require_increasing_x=False):
        super().__init__(parent)
        self._committed = ()
        self.minimum_points = minimum_points
        self.require_increasing_x = require_increasing_x
        self._loading = False
        self._paste_error = False
        self.paste_text_buffer = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setObjectName("curveTable")
        self.table = _CurveGrid(0, 2)
        self.table.setAccessibleName("Curve points")
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(TOKENS["row_height"])
        self.table.verticalHeader().setMinimumWidth(30)
        self.table.horizontalHeader().setMinimumSectionSize(80)
        self.table.itemChanged.connect(self._changed)
        self.table.pasteRequested.connect(self._paste_clipboard)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("propertySubtitle")
        commands = QFrame()
        commands.setObjectName("curveCommands")
        row = QHBoxLayout(commands)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)
        title = QLabel("Points")
        title.setObjectName("groupTitle")
        self.paste_button = QPushButton("Paste…")
        self.paste_button.setAccessibleName("Paste curve points")
        self.paste_button.setToolTip("Paste curve points (Ctrl+V)")
        self.paste_button.clicked.connect(self._paste_dialog)
        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(self.revert)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setAccessibleName("Apply curve")
        self.apply_button.setToolTip("Apply curve points")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.clicked.connect(self.apply_changes)
        row.addWidget(title)
        row.addStretch()
        row.addWidget(self.paste_button)
        row.addWidget(self.revert_button)
        row.addWidget(self.apply_button)
        layout.addWidget(commands)
        layout.addWidget(self.table, 1)
        self.message.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.message)
        self.set_points((), headers=("X", "Y"))

    def set_points(self, points, headers=None):
        self._committed = tuple(tuple(p) for p in points)
        self._display_points(self._committed)
        if headers:
            self.table.setHorizontalHeaderLabels(list(headers))
        self._paste_error = False
        self.paste_text_buffer = ""
        self.message.setText(f"{len(self._committed)} points")
        self.message.setObjectName("propertySubtitle")
        self.message.setProperty("invalid", False)
        self.apply_button.setEnabled(False)
        self.revert_button.setEnabled(False)

    def _display_points(self, points):
        self._loading = True
        self.table.setRowCount(len(points))
        for row, point in enumerate(points):
            for column, value in enumerate(point):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self._loading = False

    def points(self):
        self.flush_editor()
        if self._paste_error:
            raise ValueError(self.message.text())
        rows = [[self.table.item(r, c).text() if self.table.item(r, c) else ""
                 for c in range(2)] for r in range(self.table.rowCount())]
        return validate_points(rows, minimum_points=self.minimum_points,
                               require_increasing_x=self.require_increasing_x)

    def _changed(self):
        if self._loading:
            return
        self._paste_error = False
        self.message.setProperty("invalid", False)
        self.message.setText(f"{self.table.rowCount()} points — Modified")
        self.apply_button.setEnabled(True)
        self.revert_button.setEnabled(True)
        self.draftChanged.emit()

    def paste_text(self, text):
        self.paste_text_buffer = text
        lines = text.strip().splitlines()
        rows = [line.split("\t") if "\t" in line else line.split(",") if "," in line else line.split()
                for line in lines]
        try:
            candidate = validate_points(rows, minimum_points=self.minimum_points,
                                        require_increasing_x=self.require_increasing_x)
        except ValueError as exc:
            self._paste_error = True
            self.message.setProperty("invalid", True)
            self.message.setText(str(exc))
            self.apply_button.setEnabled(False)
            self.revert_button.setEnabled(True)
            raise
        self._display_points(candidate)
        self._changed()
        self.message.setText(f"{len(candidate)} points — Paste preview")
        return candidate

    def _paste_clipboard(self, text):
        try:
            self.paste_text(text)
        except ValueError:
            self._paste_dialog()

    def _paste_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Paste curve points")
        dialog.resize(430, 320)
        layout = QVBoxLayout(dialog)
        label = QLabel("Two numeric columns, separated by tabs, commas or spaces.\nAll rows are checked before the table preview changes.")
        label.setWordWrap(True)
        layout.addWidget(label)
        edit = QPlainTextEdit(self.paste_text_buffer or QApplication.clipboard().text())
        edit.setAccessibleName("Pasted curve data")
        layout.addWidget(edit)
        error = QLabel()
        error.setObjectName("inputError")
        error.setWordWrap(True)
        layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Preview")
        layout.addWidget(buttons)
        def preview():
            try:
                self.paste_text(edit.toPlainText())
            except ValueError as exc:
                error.setText(str(exc))
            else:
                dialog.accept()
        buttons.accepted.connect(preview)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def apply_changes(self):
        if self._paste_error:
            return False
        try:
            points = self.points()
        except ValueError as exc:
            self.message.setText(str(exc))
            self.message.setProperty("invalid", True)
            return False
        self.pointsEdited.emit(points)
        return True

    def revert(self):
        self.set_points(self._committed)
        self.draftChanged.emit()

    def has_draft(self):
        self.flush_editor()
        if self._paste_error:
            return True
        try:
            return self.points() != self._committed
        except ValueError:
            return bool(self.table.rowCount())

    def draft_state(self):
        self.flush_editor()
        return {"cells": [[self.table.item(r, c).text() if self.table.item(r, c) else ""
                            for c in range(2)] for r in range(self.table.rowCount())],
                "paste": self.paste_text_buffer, "paste_error": self._paste_error,
                "message": self.message.text()}

    def flush_editor(self):
        """Finish the actual delegate draft before a host tests/reads table data."""
        editor = self.table.focusWidget()
        if isinstance(editor, QLineEdit) and self.table.isAncestorOf(editor):
            self.table.commitData(editor)
            self.table.closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)

    def restore_draft(self, state):
        self._display_points(state["cells"])
        self.paste_text_buffer = state["paste"]
        self._paste_error = state["paste_error"]
        self.message.setProperty("invalid", self._paste_error)
        self.message.setText(state["message"])
        self.apply_button.setEnabled(not self._paste_error)
        self.revert_button.setEnabled(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.revert()
            event.accept()
        else:
            super().keyPressEvent(event)


class CurvePlot(QWidget):
    """Small real-value plot; no rendering backend or plotting dependency required."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points = ()
        self.x_label, self.y_label = "X", "Y"
        self.setMinimumSize(TOKENS["plot_min_width"], TOKENS["plot_min_height"])
        self.setAccessibleName("Curve plot")

    def set_points(self, points, *, x_label=None, y_label=None):
        self._points = tuple(tuple(p) for p in points)
        if x_label is not None:
            self.x_label = x_label
        if y_label is not None:
            self.y_label = y_label
        self.setAccessibleDescription(f"{len(self._points)} curve points; {self.x_label}, {self.y_label}")
        self.update()

    def set_labels(self, x, y):
        self.x_label, self.y_label = x, y
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(TOKENS["surface"]))
        if not self._points:
            painter.setPen(QColor(TOKENS["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No curve selected")
            return
        xs, ys = zip(*self._points)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        if x0 == x1:
            x1 = x0 + 1
        if y0 == y1:
            y1 = y0 + 1
        # Leave enough room for scientific tick labels at the current font size.
        metrics = painter.fontMetrics()
        y_ticks = [f"{y0+step/4*(y1-y0):.4g}" for step in range(5)]
        left = max(62, max(metrics.horizontalAdvance(tick) for tick in y_ticks) + 28)
        area = QRectF(left, 24, max(16, self.width()-left-30), max(16, self.height()-80))
        painter.setPen(QColor(TOKENS["plot_text"]))
        painter.drawText(QRectF(area.left(), self.height()-27, area.width(), 20),
                         Qt.AlignmentFlag.AlignCenter, self.x_label)
        painter.save()
        painter.translate(15, area.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-area.height()/2, -10, area.height(), 20),
                         Qt.AlignmentFlag.AlignCenter, self.y_label)
        painter.restore()
        x_steps = 4 if area.width() >= 360 else 2
        for step in range(5):
            fraction = step / 4
            y = area.bottom()-fraction*area.height()
            painter.setPen(QColor(TOKENS["plot_grid"]))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(QColor(TOKENS["plot_text"]))
            painter.drawText(QRectF(22, y-9, left-30, 18), Qt.AlignmentFlag.AlignRight, y_ticks[step])
        for step in range(x_steps+1):
            fraction = step / x_steps
            x = area.left()+fraction*area.width()
            painter.setPen(QColor(TOKENS["plot_grid"]))
            painter.drawLine(QPointF(x, area.top()), QPointF(x, area.bottom()))
            painter.setPen(QColor(TOKENS["plot_text"]))
            painter.drawText(QRectF(x-40, area.bottom()+7, 80, 18), Qt.AlignmentFlag.AlignHCenter,
                             f"{x0+fraction*(x1-x0):.4g}")
        painter.setPen(QPen(QColor(TOKENS["plot_border"]), TOKENS["border_width"]))
        painter.drawRect(area)
        path = QPainterPath()
        coordinates = [QPointF(area.left()+(x-x0)/(x1-x0)*area.width(), area.bottom()-(y-y0)/(y1-y0)*area.height())
                       for x, y in self._points]
        path.moveTo(coordinates[0])
        for point in coordinates[1:]:
            path.lineTo(point)
        painter.setPen(QPen(QColor(TOKENS["accent"]), TOKENS["plot_line_width"]))
        painter.drawPath(path)
        painter.setBrush(QColor(TOKENS["surface"]))
        for point in coordinates:
            painter.drawEllipse(point, TOKENS["plot_marker_radius"], TOKENS["plot_marker_radius"])
