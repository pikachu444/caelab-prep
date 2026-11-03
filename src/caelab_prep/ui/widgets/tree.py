"""Provider-backed native navigator with stable object identity across refreshes."""

from dataclasses import dataclass

from PySide6.QtCore import QItemSelectionModel, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QStyledItemDelegate,
                              QStyle, QStyleOptionViewItem, QTreeView)

from ..design import TOKENS, icon


def field(item, name, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


_GROUP = int(Qt.ItemDataRole.UserRole) + 1
_COUNT = _GROUP + 1


@dataclass(frozen=True)
class TreeAppearance:
    """Host-supplied display state; changing it does not edit the document."""

    visible: bool | None = None
    color: str | None = None

    def __post_init__(self):
        if self.visible is not None and type(self.visible) is not bool:
            raise ValueError("Visibility must be a boolean or None")
        if self.color is not None and (not isinstance(self.color, str) or not QColor(self.color).isValid()):
            raise ValueError("Color must be a valid Qt color string or None")


class _FittingDelegate(QStyledItemDelegate):
    """Keep each presentation's density while fitting its actual text and icons."""

    def __init__(self, delegate, parent):
        super().__init__(parent)
        self.delegate = delegate
        delegate.setParent(self)

    def paint(self, painter, option, index):
        self.delegate.paint(painter, option, index)

    def sizeHint(self, option, index):
        hint = self.delegate.sizeHint(option, index)
        native = QStyleOptionViewItem(option)
        self.initStyleOption(native, index)
        content_height = native.fontMetrics.height()
        if index.data(Qt.ItemDataRole.DecorationRole) is not None:
            content_height = max(content_height, native.decorationSize.height())
        if index.data(Qt.ItemDataRole.CheckStateRole) is not None:
            content_height = max(content_height, self.parent().style().pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight))
        return QSize(hint.width(), max(hint.height(), content_height + 2))


class _ObjectDelegate(QStyledItemDelegate):
    """Group bands and compact metadata share the native selection/focus path."""

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), 20 if index.data(_GROUP) else TOKENS["tree_row_height"])

    def paint(self, painter, option, index):
        if not index.data(_GROUP):
            native = QStyleOptionViewItem(option)
            self.initStyleOption(native, index)
            if index.column() > 0:
                native.palette.setColor(native.palette.ColorRole.Text, QColor(TOKENS["muted"]))
            super().paint(painter, native, index)
            return
        painter.save()
        rect = option.rect
        painter.fillRect(rect, QColor(TOKENS["raised"]))
        painter.setPen(QColor(TOKENS["divider"]))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if index.column() == 0:
            font = option.font
            font.setWeight(font.Weight.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(TOKENS["group_heading"]))
            text = option.fontMetrics.elidedText(str(index.data() or ""), Qt.TextElideMode.ElideRight, max(10, rect.width() - 32))
            painter.drawText(rect.adjusted(4, 0, -28, 0), Qt.AlignmentFlag.AlignVCenter, text)
            badge = QRectF(rect.right() - 25, rect.top() + 2, 21, max(12, rect.height() - 4))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(TOKENS["surface"]))
            painter.drawRoundedRect(badge, 2, 2)
            painter.setPen(QColor(TOKENS["muted"]))
            badge_font = option.font
            badge_font.setPointSize(max(7, badge_font.pointSize() - 2))
            painter.setFont(badge_font)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(index.data(_COUNT) or ""))
        painter.restore()


@dataclass
class _TreeViewState:
    """Compatibility adapter for selection, user expansion and scroll position."""

    selected: object
    active: object
    expanded: dict
    widths: tuple
    scroll: int

    @classmethod
    def capture(cls, tree):
        model = tree.model()
        return cls(tree.selected_refs(), tree.selected_ref(),
                   {model.item(row).text(): tree.isExpanded(model.item(row).index())
                    for row in range(model.rowCount())},
                   tuple(tree.columnWidth(column) if not tree.isColumnHidden(column) else None
                         for column in range(model.columnCount())),
                   tree.verticalScrollBar().value())

    def restore(self, tree, groups):
        for column, width in enumerate(self.widths):
            if width is not None:
                tree.setColumnWidth(column, width)
        for label, item in groups.items():
            tree.setExpanded(item.index(), self.expanded.get(label, True))
        tree.select_refs(self.selected, self.active)
        tree.verticalScrollBar().setValue(self.scroll)


class ModelTree(QTreeView):
    nodeSelected = Signal(object)
    selectedRefsChanged = Signal(object)
    visibilityRequested = Signal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modelTree")
        self.setAccessibleName("Model objects")
        self.setRootIsDecorated(True)
        self.setItemsExpandable(True)
        self.setUniformRowHeights(False)
        self.setAlternatingRowColors(False)
        self.setAllColumnsShowFocus(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setIconSize(QSize(14, 14))
        self.setIndentation(12)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setItemDelegate(_ObjectDelegate(self))
        self._model = QStandardItemModel(0, 5, self)
        self._model.setHorizontalHeaderLabels(["Name", "Type", "ID", "Visible", "Color"])
        self.setModel(self._model)
        self.header().setStretchLastSection(False)
        for column, width in enumerate((180, 60, 95, 40, 40)):
            self.header().setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self.setColumnWidth(column, width)
        self.setColumnHidden(3, True)
        self.setColumnHidden(4, True)
        self.header().setMinimumSectionSize(40)
        self._indices, self._resetting = {}, False
        self._appearances = {}
        self._pressed_visibility = None
        self._name_width = None
        self._sizing_columns = False
        self.header().sectionResized.connect(self._column_resized)
        self.header().geometriesChanged.connect(self._fit_name_column)
        self.selectionModel().currentChanged.connect(self._selected)
        self.selectionModel().selectionChanged.connect(self._selection_changed)

    def _column_resized(self, column, old_width, width):
        if self._sizing_columns or self._resetting:
            return
        if column == 0:
            self._name_width = max(100, width)
        self._fit_name_column()

    def _fit_name_column(self):
        if self._sizing_columns or self._resetting:
            return
        width = self._name_width
        if width is None:
            width = self.viewport().width() - sum(self.columnWidth(column)
                for column in range(1, self._model.columnCount()) if not self.isColumnHidden(column))
        width = max(100, width)
        if self.columnWidth(0) == width:
            return
        self._sizing_columns = True
        try:
            self.setColumnWidth(0, width)
        finally:
            self._sizing_columns = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_name_column()

    def setItemDelegate(self, delegate):
        previous = getattr(self, "_sizing_delegate", None)
        self._sizing_delegate = _FittingDelegate(delegate, self)
        super().setItemDelegate(self._sizing_delegate)
        if previous is not None:
            previous.deleteLater()

    def set_nodes(self, nodes, *, appearances=None):
        nodes = list(nodes)
        state = _TreeViewState.capture(self)
        self._resetting = True
        try:
            self._model.removeRows(0, self._model.rowCount())
            self._indices.clear()
            groups = {}
            for node in nodes:
                group = str(field(node, "group", "Objects"))
                if group not in groups:
                    cells = [QStandardItem(group)] + [QStandardItem() for _ in range(4)]
                    for cell in cells:
                        cell.setData(True, _GROUP)
                        cell.setEditable(False)
                        cell.setSelectable(False)
                    self._model.appendRow(cells)
                    groups[group] = cells[0]
                ref = field(node, "ref")
                native = field(ref, "native_scope") or ""
                cells = [QStandardItem(icon(field(node, "icon", "card")), str(field(node, "label", ""))),
                         QStandardItem(str(field(ref, "kind", ""))), QStandardItem(str(native)),
                         QStandardItem(), QStandardItem()]
                cells[0].setData(ref, Qt.ItemDataRole.UserRole)
                cells[0].setToolTip(str(field(node, "tooltip", "") or field(node, "label", "")))
                cells[2].setToolTip(str(native))
                for cell in cells:
                    cell.setEditable(False)
                groups[group].appendRow(cells)
                self._indices[ref] = cells[0]
            for item in groups.values():
                item.setData(item.rowCount(), _COUNT)
            state.restore(self, groups)
            self.setColumnHidden(2, not any(field(field(node, "ref"), "native_scope") for node in nodes))
            self._appearances = {}
            self.update_appearances(appearances or {})
        finally:
            self._resetting = False
        self._fit_name_column()

    def update_appearances(self, mapping):
        """Replace the host's appearance snapshot without rebuilding tree rows."""
        appearances = {ref: value for ref, value in mapping.items() if ref in self._indices}
        for ref, item in self._indices.items():
            appearance = appearances.get(ref, TreeAppearance())
            if appearance == self._appearances.get(ref, TreeAppearance()):
                continue
            visible = self._model.itemFromIndex(item.index().siblingAtColumn(3))
            visible.setData(None if appearance.visible is None else
                            Qt.CheckState.Checked if appearance.visible else Qt.CheckState.Unchecked,
                            Qt.ItemDataRole.CheckStateRole)
            text = "" if appearance.visible is None else "Visible" if appearance.visible else "Hidden"
            visible.setToolTip(text)
            visible.setData(text, Qt.ItemDataRole.AccessibleTextRole)
            color = self._model.itemFromIndex(item.index().siblingAtColumn(4))
            color.setData(QColor(appearance.color) if appearance.color is not None else None,
                          Qt.ItemDataRole.DecorationRole)
            color.setToolTip(appearance.color or "")
            color.setData(appearance.color or "", Qt.ItemDataRole.AccessibleTextRole)
        self._appearances = appearances
        self.setColumnHidden(3, not any(value.visible is not None for value in appearances.values()))
        self.setColumnHidden(4, not any(value.color is not None for value in appearances.values()))
        self._fit_name_column()

    def _visibility_ref_at(self, position):
        index = self.indexAt(position)
        if index.column() == 3:
            ref = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
            if self._appearances.get(ref, TreeAppearance()).visible is not None:
                return ref
        return None

    def _request_visibility(self, ref):
        appearance = self._appearances.get(ref, TreeAppearance())
        if appearance.visible is not None:
            self.visibilityRequested.emit(ref, not appearance.visible)

    def mousePressEvent(self, event):
        self._pressed_visibility = None
        if event.button() == Qt.MouseButton.LeftButton:
            ref = self._visibility_ref_at(event.position().toPoint())
            if ref is not None:
                self._pressed_visibility = ref
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed_visibility is not None:
            ref, self._pressed_visibility = self._pressed_visibility, None
            if event.button() == Qt.MouseButton.LeftButton and self._visibility_ref_at(event.position().toPoint()) == ref:
                self._request_visibility(ref)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._visibility_ref_at(event.position().toPoint()) is not None:
            self._pressed_visibility = None
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.NoModifier
                and self._appearances.get(self.selected_ref(), TreeAppearance()).visible is not None):
            self._request_visibility(self.selected_ref())
            event.accept()
            return
        super().keyPressEvent(event)

    def selected_ref(self):
        return self.currentIndex().siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)

    def selected_refs(self):
        return tuple(ref for index in self.selectionModel().selectedRows(0)
                     if (ref := index.data(Qt.ItemDataRole.UserRole)) is not None)

    def select_refs(self, refs, active=None):
        refs = tuple(refs)
        self.selectionModel().clearSelection()
        for ref in refs:
            item = self._indices.get(ref)
            if item is not None:
                self.selectionModel().select(item.index(), QItemSelectionModel.SelectionFlag.Select |
                                             QItemSelectionModel.SelectionFlag.Rows)
        current = self._indices.get(active)
        if current is not None:
            self.selectionModel().setCurrentIndex(current.index(), QItemSelectionModel.SelectionFlag.NoUpdate)
        else:
            self.selectionModel().clearCurrentIndex()

    def _selection_changed(self, selected, deselected):
        if not self._resetting:
            self.selectedRefsChanged.emit(self.selected_refs())

    def select_ref(self, ref):
        item = self._indices.get(ref)
        if item is None:
            return False
        self.setCurrentIndex(item.index())
        self.scrollTo(item.index())
        return True

    def _selected(self, current, previous):
        ref = current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        if ref is not None and not self._resetting:
            self.nodeSelected.emit(ref)


ObjectTree = ModelTree
