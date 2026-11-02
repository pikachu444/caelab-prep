"""Native curve worksheet and a scale-aware, dependency-free plot presentation."""

from decimal import Decimal, ROUND_CEILING
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog,
                              QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                              QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                              QVBoxLayout, QWidget)

from ._curve_data import CurveDraftAdapter, validate_points
from ..design import TOKENS


class _CurveGrid(QTableWidget):
    pasteRequested = Signal(str)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.pasteRequested.emit(QApplication.clipboard().text())
            event.accept()
            return
        super().keyPressEvent(event)


class CurveTable(CurveDraftAdapter, QWidget):
    """A worksheet that publishes one complete validated draft on Apply."""

    pointsEdited = Signal(object)
    draftChanged = Signal()
    selectedRowsChanged = Signal(object)

    def __init__(self, parent=None, *, minimum_points=1, maximum_points=None, require_increasing_x=False):
        super().__init__(parent)
        self.setObjectName("curveTable")
        self.minimum_points, self.require_increasing_x = minimum_points, require_increasing_x
        self.maximum_points = maximum_points
        self._committed, self.paste_text_buffer = (), ""
        self._loading, self._paste_error = False, False
        self._plot = None
        self._gesture_active = False
        self._context = lambda: None
        self._can_edit = lambda: self.isEnabled()
        self._generation = 0
        self.csv_axes = ("X (current values)", "Y (current values)")
        worksheet = QVBoxLayout(self)
        worksheet.setContentsMargins(0, 0, 0, 0)
        worksheet.setSpacing(0)
        toolbar = QFrame()
        toolbar.setObjectName("curveCommands")
        commands = QHBoxLayout(toolbar)
        commands.setContentsMargins(8, 4, 8, 4)
        commands.setSpacing(4)
        heading = QLabel("Curve data")
        heading.setObjectName("groupTitle")
        commands.addWidget(heading, 1)
        self.add_button = QPushButton("+")
        self.add_button.setAccessibleName("Add curve row")
        self.add_button.setToolTip("Add a blank row after the current row")
        self.add_button.setFixedWidth(28)
        self.add_button.clicked.connect(self.add_row)
        commands.addWidget(self.add_button)
        self.remove_button = QPushButton("−")
        self.remove_button.setAccessibleName("Remove selected curve rows")
        self.remove_button.setToolTip("Remove selected rows")
        self.remove_button.setFixedWidth(28)
        self.remove_button.clicked.connect(self.remove_selected_rows)
        commands.addWidget(self.remove_button)
        self.paste_button = QPushButton("Paste…")
        self.paste_button.setAccessibleName("Paste curve points")
        self.paste_button.setToolTip("Paste curve points (Ctrl+V)")
        self.paste_button.clicked.connect(self._paste_dialog)
        commands.addWidget(self.paste_button)
        worksheet.addWidget(toolbar)
        files = QHBoxLayout()
        files.setContentsMargins(8, 2, 8, 4)
        self.import_csv_button = QPushButton("Import CSV…")
        self.export_csv_button = QPushButton("Export CSV…")
        self.import_csv_button.setAccessibleName("Import curve CSV file")
        self.export_csv_button.setAccessibleName("Export curve CSV file")
        self.import_csv_button.clicked.connect(self.import_csv_dialog)
        self.export_csv_button.clicked.connect(self.export_csv_dialog)
        for button in (self.import_csv_button, self.export_csv_button):
            button.setToolTip("Two numeric columns in the displayed axes. CSV does not store units or references.")
            files.addWidget(button)
        files.addStretch()
        worksheet.addLayout(files)

        self.table = _CurveGrid(0, 2)
        self.table.setAccessibleName("Curve points")
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed |
                                   QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(70)
        self.table.verticalHeader().setDefaultSectionSize(TOKENS["row_height"])
        self.table.verticalHeader().setMinimumWidth(28)
        self.table.itemChanged.connect(self._changed)
        self.table.pasteRequested.connect(self._paste_clipboard)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        worksheet.addWidget(self.table, 1)

        footer = QFrame()
        footer.setObjectName("curveCommands")
        status = QGridLayout(footer)
        status.setContentsMargins(8, 5, 8, 5)
        status.setHorizontalSpacing(6)
        status.setVerticalSpacing(4)
        self.message = QLabel()
        self.message.setObjectName("propertySubtitle")
        self.message.setWordWrap(True)
        status.addWidget(self.message, 0, 0, 1, 3)
        self.selection_label = QLabel()
        self.selection_label.setObjectName("unitsNote")
        status.addWidget(self.selection_label, 1, 0)
        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(self.revert)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.setAccessibleName("Apply curve")
        self.apply_button.clicked.connect(self.apply_changes)
        status.addWidget(self.revert_button, 1, 1)
        status.addWidget(self.apply_button, 1, 2)
        status.setColumnStretch(0, 1)
        worksheet.addWidget(footer)
        self.set_points((), headers=("X", "Y"))
        self._selection_changed()

    def bind_plot(self, plot, *, commit, context, can_edit=None):
        """Bind shared draft UI to a host-owned command and document identity."""
        self._plot, self._context = plot, context
        self._can_edit = can_edit or (lambda: self.isEnabled())
        plot.bind_table(self, commit)
        self.selectedRowsChanged.connect(plot.set_selected_rows)
        self._sync_plot()

    def context_token(self):
        return self._generation, self._context()

    def set_csv_axes(self, x, y):
        self.csv_axes = (str(x), str(y))

    def _csv_policy(self):
        return (f"X: {self.csv_axes[0]}\nY: {self.csv_axes[1]}\n"
                "CSV contains numeric values only in these axes; no unit conversion is performed. "
                "Units, curve identity and references remain in the work document (.caeprep).")

    def _check_file_context(self, token):
        if token != self.context_token() or not self._can_edit() or self._gesture_active:
            raise ValueError("The curve or document changed. Reopen the CSV operation for the current curve.")

    def import_csv_file(self, path, *, confirm=True):
        """Validate the complete file, then offer a preview; Apply owns mutation."""
        from ...application.curve_csv import read_curve_csv
        token = self.context_token()
        self._check_file_context(token)
        candidate = validate_points(read_curve_csv(path), minimum_points=self.minimum_points,
                                    maximum_points=self.maximum_points,
                                    require_increasing_x=self.require_increasing_x)
        if confirm:
            dialog = QDialog(self)
            dialog.setObjectName("curveCsvPreview")
            dialog.setWindowTitle("Import curve CSV — preview")
            dialog.resize(520, 430)
            layout = QVBoxLayout(dialog)
            info = QLabel(f"{Path(path).name}: {len(candidate)} points\n" + self._csv_policy())
            info.setWordWrap(True)
            layout.addWidget(info)
            preview = QTableWidget(min(len(candidate), 100), 2)
            preview.setHorizontalHeaderLabels(list(self.csv_axes))
            preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for row, pair in enumerate(candidate[:100]):
                for column, value in enumerate(pair):
                    preview.setItem(row, column, QTableWidgetItem(repr(value)))
            layout.addWidget(preview)
            note = QLabel("Preview shows the first 100 rows. All rows were validated.\n"
                          "Use these points replaces the current table draft. Apply commits one Undo step.")
            note.setWordWrap(True)
            layout.addWidget(note)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use these points")
            buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
        self._check_file_context(token)
        self._display_points(candidate)
        self._changed()
        self._set_status(f"{len(candidate)} imported points — Preview; Apply to commit")
        return True

    def import_csv_dialog(self):
        token = self.context_token()
        path, _ = QFileDialog.getOpenFileName(self, "Import curve CSV", "", "CSV (*.csv)")
        if not path:
            return False
        try:
            self._check_file_context(token)
            return self.import_csv_file(path)
        except (OSError, ValueError) as exc:
            self._set_status(f"CSV import failed: {exc}", invalid=True)
            return False

    def export_csv_file(self, path, *, overwrite=False):
        from ...application.curve_csv import write_curve_csv
        token = self.context_token()
        self._check_file_context(token)
        points = self.points()
        self._check_file_context(token)
        return write_curve_csv(path, points, overwrite=overwrite)

    def export_csv_dialog(self):
        token = self.context_token()
        try:
            self._check_file_context(token)
            self.points()  # Reject an invalid draft before opening a save dialog.
            if QMessageBox.question(self, "Export displayed curve values", self._csv_policy(),
                                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                                    QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Ok:
                return False
            path, _ = QFileDialog.getSaveFileName(self, "Export curve CSV", "curve.csv", "CSV (*.csv)",
                                                 options=QFileDialog.Option.DontConfirmOverwrite)
            if not path:
                return False
            self._check_file_context(token)
            overwrite = Path(path).exists() or Path(path).is_symlink()
            if overwrite and QMessageBox.question(self, "Replace CSV file?", f"Replace the existing file?\n{path}",
                                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                   QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return False
            self._check_file_context(token)
            # An initially absent target is published exclusively; a concurrent
            # creator cannot be overwritten without a separate confirmation.
            self.export_csv_file(path, overwrite=overwrite)
            self._set_status(f"Exported displayed values to {Path(path).name}")
            return True
        except (OSError, ValueError) as exc:
            self._set_status(f"CSV export failed: {exc}", invalid=True)
            return False

    def _set_status(self, text, *, invalid=False):
        self.message.setText(text)
        self.message.setProperty("invalid", invalid)
        self.message.setAccessibleDescription("Curve input error" if invalid else "Curve draft status")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def _selection_changed(self):
        rows = tuple(sorted({index.row() for index in self.table.selectedIndexes()}))
        if hasattr(self, "selection_label"):
            self.selection_label.setText(f"{len(rows)} selected" if rows else "")
        self.selectedRowsChanged.emit(rows)
        self.remove_button.setEnabled(bool(rows))

    def add_row(self):
        """Add an intentionally blank draft; the host validates the whole table."""
        self.flush_editor()
        current = self.table.currentRow()
        row = current + 1 if current >= 0 else self.table.rowCount()
        self._loading = True
        try:
            self.table.insertRow(row)
            for column in range(2):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
            self.table.setCurrentCell(row, 0)
        finally:
            self._loading = False
        self._changed()
        self.table.scrollToItem(self.table.item(row, 0))

    def remove_selected_rows(self):
        self.flush_editor()
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._loading = True
        try:
            for row in rows:
                self.table.removeRow(row)
        finally:
            self._loading = False
        self._changed()
        self._selection_changed()

    def _paste_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Paste curve points")
        dialog.resize(460, 340)
        form = QVBoxLayout(dialog)
        form.setSpacing(8)
        title = QLabel("Curve points")
        title.setObjectName("propertyTitle")
        form.addWidget(title)
        edit = QPlainTextEdit(self.paste_text_buffer or QApplication.clipboard().text())
        edit.setAccessibleName("Pasted curve data")
        edit.setPlaceholderText("X\tY\n0\t0\n1\t100")
        form.addWidget(edit, 1)
        format_label = QLabel("Two columns: tab, comma or space separated")
        format_label.setObjectName("unitsNote")
        form.addWidget(format_label)
        error = QLabel()
        error.setObjectName("inputError")
        error.setWordWrap(True)
        form.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Preview")
        form.addWidget(buttons)

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


class _Axis:
    """Subtract decimal offsets before converting a bounded fraction to float."""

    def __init__(self, values):
        values = [Decimal(str(value)) for value in values] or [Decimal(0), Decimal(1)]
        self.low, self.high = min(values), max(values)
        if self.low == self.high:
            padding = abs(self.low) / 10 or Decimal("0.1")
            self.low -= padding
            self.high += padding
        self._span = self.high - self.low

    def fraction(self, value):
        return float((Decimal(str(value)) - self.low) / self._span)

    def value_at(self, fraction):
        return float(self.low + Decimal(str(fraction)) * self._span)

    def ticks(self, count):
        distance = self._span / count
        base = Decimal(10) ** distance.adjusted()
        step = next(candidate * base for candidate in (1, 2, 5, 10) if candidate * base >= distance)
        start = (self.low / step).to_integral_value(rounding=ROUND_CEILING) * step
        ticks = []
        previous = None
        for index in range(count + 2):
            value = start + index * step
            if value > self.high:
                break
            numeric = float(value)
            if not math.isfinite(numeric) or (previous is not None and numeric <= previous):
                continue
            represented = Decimal(str(numeric))
            if not self.low <= represented <= self.high:
                continue
            # Round-trip strings retain close values; multiple mathematical
            # ticks that round to the same representable float share one mark.
            label = str(numeric)
            if label.endswith(".0"):
                label = label[:-2]
            ticks.append((self.fraction(numeric), label))
            previous = numeric
        return ticks


class CurvePlot(QWidget):
    """Shared data-coordinate preview; only the host commits a completed drag."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("curvePlot")
        self.setAccessibleName("Curve plot")
        self.setMinimumSize(TOKENS["plot_min_width"], TOKENS["plot_min_height"])
        self._points, self._selected_rows = (), set()
        self.x_label, self.y_label = "X", "Y"
        self._table = self._commit = self._drag = None
        self._preview = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def bind_table(self, table, commit):
        self._table, self._commit = table, commit
        self.setToolTip("Drag a point to edit. Release applies one Undo step; Escape cancels. Apply/revert table drafts first.")

    def _plot_geometry(self):
        if self._drag is not None:
            return self._drag["geometry"]
        x_axis = _Axis([point[0] for point in self._points])
        y_axis = _Axis([point[1] for point in self._points])
        y_ticks = y_axis.ticks(max(2, min(6, self.height() // 70)))
        metrics = self.fontMetrics()
        left = 30 + max((metrics.horizontalAdvance(label) for _, label in y_ticks), default=30)
        return x_axis, y_axis, QRectF(left, 24, max(20, self.width() - left - 28), max(20, self.height() - 78))

    def data_position(self, x, y):
        """Map displayed data to a widget position (also used by interaction tests)."""
        x_axis, y_axis, rect = self._plot_geometry()
        return QPointF(rect.left() + x_axis.fraction(x) * rect.width(),
                       rect.bottom() - y_axis.fraction(y) * rect.height())

    def mousePressEvent(self, event):
        table = self._table
        if event.button() != Qt.MouseButton.LeftButton or table is None or not self._points:
            return super().mousePressEvent(event)
        if not table.isEnabled() or not table._can_edit():
            return
        if table.has_draft():
            table._set_status("Apply or revert the table draft before dragging a point.", invalid=True)
            return
        distances = [((self.data_position(*point) - event.position()).manhattanLength(), row)
                     for row, point in enumerate(self._points)]
        distance, row = min(distances)
        if distance > 12:
            return
        self._drag = {"row": row, "before": self._points, "state": table.draft_state(),
                      "token": table.context_token(), "geometry": self._plot_geometry(), "valid": True,
                      "press": event.position(), "moved": False}
        table._gesture_active = True
        table.table.selectRow(row)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._selected_rows = {row}
        table._set_status(f"Dragging point {row + 1} — Release to apply; Escape to cancel")
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return super().mouseMoveEvent(event)
        table, drag = self._table, self._drag
        if drag["token"] != table.context_token() or not table._can_edit():
            self.cancel_drag(message="Document or curve changed — drag cancelled; reload current values.")
            return
        x_axis, y_axis, rect = drag["geometry"]
        position = event.position()
        if not drag["moved"] and (position - drag["press"]).manhattanLength() < 3:
            return
        drag["moved"] = True
        candidate = list(drag["before"])
        candidate[drag["row"]] = (x_axis.value_at(max(0., min(1., (position.x() - rect.left()) / rect.width()))),
                                  y_axis.value_at(max(0., min(1., (rect.bottom() - position.y()) / rect.height()))))
        try:
            candidate = validate_points(candidate, minimum_points=table.minimum_points,
                                        maximum_points=table.maximum_points,
                                        require_increasing_x=table.require_increasing_x)
        except ValueError as exc:
            drag["valid"] = False
            table._set_status(f"Invalid drag: {exc} — Release cancels", invalid=True)
            return
        drag["valid"] = True
        table._display_points(candidate)
        self._points = candidate
        self._preview = True
        table._set_status(f"Point {drag['row'] + 1}: {candidate[drag['row']]} — Release to apply; Escape cancels")
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._drag is None:
            return super().mouseReleaseEvent(event)
        self.mouseMoveEvent(event)
        if self._drag is None:
            return
        table, drag, points = self._table, self._drag, self._points
        if not drag["valid"]:
            self.cancel_drag(message="Invalid point position — no curve changes applied.")
            return
        self._drag = None
        table._gesture_active = False
        if points == drag["before"]:
            table.restore_draft(drag["state"])
            return
        # The host's existing expected-revision command is the sole mutation.
        try:
            accepted = self._commit(points)
        except Exception as exc:
            accepted = False
            table._set_status(str(exc), invalid=True)
        if not accepted:
            table.restore_draft(drag["state"])
            self.set_points(drag["before"])
            table._set_status("Drag was not applied. Reload the curve before retrying.", invalid=True)
        self.update()
        event.accept()

    def cancel_drag(self, *, restore=True, message=None):
        if self._drag is None:
            return False
        table, drag = self._table, self._drag
        self._drag = None
        table._gesture_active = False
        if restore:
            table.restore_draft(drag["state"])
            self.set_points(drag["before"])
        if message:
            table._set_status(message, invalid=True)
        self.update()
        return True

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.cancel_drag(message="Point drag cancelled"):
            event.accept()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        self.cancel_drag()
        super().hideEvent(event)

    def set_points(self, points, *, x_label=None, y_label=None):
        self._points = tuple(tuple(point) for point in points)
        self.set_labels(x_label if x_label is not None else self.x_label,
                        y_label if y_label is not None else self.y_label)
        self.setAccessibleDescription(f"{len(self._points)} curve points; {self.x_label}, {self.y_label}")

    def set_preview(self, preview):
        self._preview = bool(preview)
        self.update()

    def set_labels(self, x, y):
        self.x_label, self.y_label = x, y
        self.setToolTip(f"{y}\n{x}" + ("\nDrag a point; release applies, Escape cancels." if self._table else ""))
        self.update()

    def set_selected_rows(self, rows):
        self._selected_rows = set(rows)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(TOKENS["surface"]))
        if self._preview:
            painter.setPen(QColor(TOKENS["accent"]))
            painter.drawText(QRectF(30, 2, self.width() - 45, 18), Qt.AlignmentFlag.AlignCenter,
                             "Preview — Apply / Revert" if self._drag is None else "Preview — Release / Escape")
        if not self._points:
            painter.setPen(QColor(TOKENS["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No curve selected")
            return
        x_axis, y_axis, plot = self._plot_geometry()
        y_ticks = y_axis.ticks(max(2, min(6, self.height() // 70)))
        x_ticks = x_axis.ticks(max(2, min(7, int(plot.width() // 100))))
        self._draw_axes(painter, plot, x_ticks, y_ticks)
        painter.save()
        painter.setClipRect(plot.adjusted(-5, -5, 5, 5))
        points = [QPointF(plot.left() + x_axis.fraction(x) * plot.width(),
                         plot.bottom() - y_axis.fraction(y) * plot.height()) for x, y in self._points]
        line = QPainterPath(points[0])
        for point in points[1:]:
            line.lineTo(point)
        painter.setPen(QPen(QColor(TOKENS["accent"]), 1.8))
        painter.drawPath(line)
        for row, point in enumerate(points):
            selected = row in self._selected_rows
            painter.setBrush(QColor(TOKENS["accent"] if selected else TOKENS["surface"]))
            radius = 4.5 if selected else 2.8
            painter.drawEllipse(point, radius, radius)
        painter.restore()

    def _draw_axes(self, painter, plot, x_ticks, y_ticks):
        for fraction, label in y_ticks:
            y = plot.bottom() - fraction * plot.height()
            painter.setPen(QPen(QColor(TOKENS["plot_grid"]), 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(TOKENS["plot_text"]))
            painter.drawText(QRectF(23, y - 10, plot.left() - 31, 20), Qt.AlignmentFlag.AlignRight, label)
        for fraction, label in x_ticks:
            x = plot.left() + fraction * plot.width()
            painter.setPen(QPen(QColor(TOKENS["plot_grid"]), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor(TOKENS["plot_text"]))
            painter.drawText(QRectF(x - 40, plot.bottom() + 7, 80, 20), Qt.AlignmentFlag.AlignHCenter, label)
        painter.setPen(QPen(QColor(TOKENS["plot_border"]), 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.bottomLeft(), plot.topLeft())
        painter.setPen(QColor(TOKENS["plot_text"]))
        painter.drawText(QRectF(plot.left(), self.height() - 26, plot.width(), 20), Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(self.x_label, Qt.TextElideMode.ElideRight, int(plot.width())))
        painter.save()
        painter.translate(13, plot.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-plot.height() / 2, -10, plot.height(), 20), Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(self.y_label, Qt.TextElideMode.ElideRight, int(plot.height())))
        painter.restore()
