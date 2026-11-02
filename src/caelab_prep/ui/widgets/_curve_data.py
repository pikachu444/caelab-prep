"""Preserved curve validation and draft/commit boundary for native table hosts."""

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemDelegate, QLineEdit, QTableWidgetItem


def validate_points(points, *, minimum_points=1, maximum_points=None, require_increasing_x=False):
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
    if maximum_points is not None and len(result) > maximum_points:
        raise ValueError(f"A curve allows at most {maximum_points} point(s)")
    if require_increasing_x and any(b[0] <= a[0] for a, b in zip(result, result[1:])):
        raise ValueError("X values must increase strictly; no rows were applied")
    return tuple(result)


class CurveDraftAdapter:
    """Keep complete draft validation, host Apply, rollback and editor flushing."""

    def set_points(self, points, headers=None):
        if getattr(self, "_plot", None) is not None:
            self._plot.cancel_drag(restore=False)
        self._generation = getattr(self, "_generation", 0) + 1
        self._committed = tuple(tuple(p) for p in points)
        self._display_points(self._committed)
        if headers:
            self.table.setHorizontalHeaderLabels(list(headers))
        self._paste_error = False
        self.paste_text_buffer = ""
        self._set_status(f"{len(self._committed)} points")
        self.apply_button.setEnabled(False)
        self.revert_button.setEnabled(False)
        self._sync_plot()

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
        if getattr(self, "_gesture_active", False):
            raise ValueError("Finish the point drag or press Escape before another operation.")
        self.flush_editor()
        if self._paste_error:
            raise ValueError(self.message.text())
        rows = [[self.table.item(r, c).text() if self.table.item(r, c) else ""
                 for c in range(2)] for r in range(self.table.rowCount())]
        return validate_points(rows, minimum_points=self.minimum_points,
                               maximum_points=self.maximum_points,
                               require_increasing_x=self.require_increasing_x)

    def _changed(self):
        if self._loading:
            return
        self._paste_error = False
        self._set_status(f"{self.table.rowCount()} points — Modified")
        self.apply_button.setEnabled(True)
        self.revert_button.setEnabled(True)
        self.draftChanged.emit()
        self._sync_plot()

    def _sync_plot(self):
        plot = getattr(self, "_plot", None)
        if plot is not None and not getattr(self, "_gesture_active", False):
            try:
                points = self.points()
                plot.set_points(points)
                plot.set_preview(points != self._committed)
            except ValueError:
                pass

    def paste_text(self, text):
        self.paste_text_buffer = text
        lines = text.strip().splitlines()
        rows = [line.split("\t") if "\t" in line else line.split(",") if "," in line else line.split()
                for line in lines]
        try:
            candidate = validate_points(rows, minimum_points=self.minimum_points,
                                        maximum_points=self.maximum_points,
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
        if getattr(self, "_gesture_active", False):
            return True
        self.flush_editor()
        if self._paste_error:
            return True
        try:
            return self.points() != self._committed
        except ValueError:
            # Removing every row is still an unfinished draft when the host's
            # minimum count is nonzero; navigation must not silently discard it.
            return self.draft_state()["cells"] != [list(map(str, p)) for p in self._committed]

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
        self._sync_plot()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.revert()
            event.accept()
        else:
            super().keyPressEvent(event)
