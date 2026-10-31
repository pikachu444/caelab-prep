"""Native curve worksheet and a scale-aware, dependency-free plot presentation."""

from decimal import Decimal, ROUND_CEILING
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox,
                              QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                              QPlainTextEdit, QPushButton, QTableWidget,
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

    def __init__(self, parent=None, *, minimum_points=1, require_increasing_x=False):
        super().__init__(parent)
        self.setObjectName("curveTable")
        self.minimum_points, self.require_increasing_x = minimum_points, require_increasing_x
        self._committed, self.paste_text_buffer = (), ""
        self._loading, self._paste_error = False, False
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
        self.paste_button = QPushButton("Paste…")
        self.paste_button.setAccessibleName("Paste curve points")
        self.paste_button.setToolTip("Paste curve points (Ctrl+V)")
        self.paste_button.clicked.connect(self._paste_dialog)
        commands.addWidget(self.paste_button)
        worksheet.addWidget(toolbar)

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
    """Plot current document values; optional row emphasis is view state only."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("curvePlot")
        self.setAccessibleName("Curve plot")
        self.setMinimumSize(TOKENS["plot_min_width"], TOKENS["plot_min_height"])
        self._points, self._selected_rows = (), set()
        self.x_label, self.y_label = "X", "Y"

    def set_points(self, points, *, x_label=None, y_label=None):
        self._points = tuple(tuple(point) for point in points)
        self.set_labels(x_label if x_label is not None else self.x_label,
                        y_label if y_label is not None else self.y_label)
        self.setAccessibleDescription(f"{len(self._points)} curve points; {self.x_label}, {self.y_label}")

    def set_labels(self, x, y):
        self.x_label, self.y_label = x, y
        self.setToolTip(f"{y}\n{x}")
        self.update()

    def set_selected_rows(self, rows):
        self._selected_rows = set(rows)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(TOKENS["surface"]))
        if not self._points:
            painter.setPen(QColor(TOKENS["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No curve selected")
            return
        x_axis = _Axis([point[0] for point in self._points])
        y_axis = _Axis([point[1] for point in self._points])
        y_ticks = y_axis.ticks(max(2, min(6, self.height() // 70)))
        metrics = painter.fontMetrics()
        left = 30 + max((metrics.horizontalAdvance(label) for _, label in y_ticks), default=30)
        plot = QRectF(left, 24, max(20, self.width() - left - 28), max(20, self.height() - 78))
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
