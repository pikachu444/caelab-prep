"""Preserved curve validation and draft/commit boundary for native table hosts."""

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemDelegate, QLineEdit, QTableWidgetItem


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


class CurveDraftAdapter:
    """Keep complete draft validation, host Apply, rollback and editor flushing."""

    def set_points(self, points, headers=None):
        self._committed = tuple(tuple(p) for p in points)
        self._display_points(self._committed)
        if headers:
            self.table.setHorizontalHeaderLabels(list(headers))
        self._paste_error = False
        self.paste_text_buffer = ""
        self._set_status(f"{len(self._committed)} points")
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
        self._set_status(f"{self.table.rowCount()} points — Modified")
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
            self._set_status(str(exc), invalid=True)
            self.apply_button.setEnabled(False)
            self.revert_button.setEnabled(True)
            raise
        self._display_points(candidate)
        self._changed()
        self._set_status(f"{len(candidate)} points — Paste preview")
        return candidate

    def _paste_clipboard(self, text):
        try:
            self.paste_text(text)
        except ValueError:
            self._paste_dialog()

    def apply_changes(self):
        if self._paste_error:
            return False
        try:
            points = self.points()
        except ValueError as exc:
            self._set_status(str(exc), invalid=True)
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
        self._set_status(state["message"], invalid=self._paste_error)
        self.apply_button.setEnabled(not self._paste_error)
        self.revert_button.setEnabled(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.revert()
            event.accept()
        else:
            super().keyPressEvent(event)
