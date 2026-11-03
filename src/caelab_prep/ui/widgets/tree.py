"""Provider-backed native navigator with stable object identity across refreshes."""

from dataclasses import dataclass

from PySide6.QtCore import QItemSelectionModel, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QStyledItemDelegate,
                              QStyleOptionViewItem, QTreeView)

from ..design import TOKENS, icon


def field(item, name, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


_GROUP = int(Qt.ItemDataRole.UserRole) + 1
_COUNT = _GROUP + 1


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
                   tuple(tree.columnWidth(column) for column in range(3)) if model.rowCount() else (180, 60, 95),
                   tree.verticalScrollBar().value())

    def restore(self, tree, groups):
        for column, width in enumerate(self.widths):
            tree.setColumnWidth(column, width)
        for label, item in groups.items():
            tree.setExpanded(item.index(), self.expanded.get(label, True))
        tree.select_refs(self.selected, self.active)
        tree.verticalScrollBar().setValue(self.scroll)


class ModelTree(QTreeView):
    nodeSelected = Signal(object)
    selectedRefsChanged = Signal(object)

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
        self._model = QStandardItemModel(0, 3, self)
        self._model.setHorizontalHeaderLabels(["Name", "Type", "ID"])
        self.setModel(self._model)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.header().setMinimumSectionSize(40)
        self._indices, self._resetting = {}, False
        self.selectionModel().currentChanged.connect(self._selected)
        self.selectionModel().selectionChanged.connect(self._selection_changed)

    def set_nodes(self, nodes):
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
                    cells = [QStandardItem(group), QStandardItem(), QStandardItem()]
                    for cell in cells:
                        cell.setData(True, _GROUP)
                        cell.setEditable(False)
                        cell.setSelectable(False)
                    self._model.appendRow(cells)
                    groups[group] = cells[0]
                ref = field(node, "ref")
                native = field(ref, "native_scope") or field(ref, "object_id", "")
                cells = [QStandardItem(icon(field(node, "icon", "card")), str(field(node, "label", ""))),
                         QStandardItem(str(field(ref, "kind", ""))), QStandardItem(str(native))]
                cells[0].setData(ref, Qt.ItemDataRole.UserRole)
                cells[0].setToolTip(str(field(node, "tooltip", "") or field(node, "label", "")))
                cells[2].setToolTip(str(native))
                for cell in cells:
                    cell.setEditable(False)
                groups[group].appendRow(cells)
                self._indices[ref] = cells[0]
            for item in groups.values():
                item.setData(item.rowCount(), _COUNT)
            self.setColumnHidden(2, not any(field(field(node, "ref"), "native_scope") for node in nodes))
            state.restore(self, groups)
            if not self.isColumnHidden(2) and self.columnWidth(2) < 95:
                self.setColumnWidth(2, 95)
        finally:
            self._resetting = False

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
