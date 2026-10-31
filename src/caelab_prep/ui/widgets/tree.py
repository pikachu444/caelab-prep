"""Provider-driven model/view navigation without domain-specific naming."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeView

from ..theme import icon
from ..design import TOKENS


def field(item, name, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


class ModelTree(QTreeView):
    nodeSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modelTree")
        self.setAccessibleName("Model objects")
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setAllColumnsShowFocus(True)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setIndentation(TOKENS["tree_indent"])
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._indices = {}
        self._resetting = False
        self.selectionModel().currentChanged.connect(self._selected)

    def set_nodes(self, nodes):
        nodes = list(nodes)
        selected = self.selected_ref()
        scroll = self.verticalScrollBar().value()
        expansion = {self._model.item(row).text(): self.isExpanded(self._model.item(row).index())
                     for row in range(self._model.rowCount())}
        widths = [self.columnWidth(column) for column in range(3)] if self._model.rowCount() else (210, 72, 80)
        self._resetting = True
        self._model.clear()
        self._model.setHorizontalHeaderLabels(["Name", "Type", "ID"])
        self._indices.clear()
        groups = {}
        for node in nodes:
            group = str(field(node, "group", "Objects"))
            if group not in groups:
                parent = QStandardItem(group)
                parent.setEditable(False)
                parent.setSelectable(False)
                font = parent.font()
                font.setBold(True)
                parent.setFont(font)
                parent.setForeground(QColor(TOKENS["group_heading"]))
                parent.setBackground(QColor(TOKENS["raised"]))
                groups[group] = parent
                cells = [parent, QStandardItem(), QStandardItem()]
                for cell in cells[1:]:
                    cell.setSelectable(False)
                    cell.setBackground(QColor(TOKENS["raised"]))
                self._model.appendRow(cells)
            ref = field(node, "ref")
            name = QStandardItem(icon(field(node, "icon", "card")), str(field(node, "label", "")))
            name.setData(ref, Qt.ItemDataRole.UserRole)
            name.setToolTip(str(field(node, "tooltip", "") or field(node, "label", "")))
            kind = str(field(ref, "kind", ""))
            native = field(ref, "native_scope") or field(ref, "object_id", "")
            kind_item, native_item = QStandardItem(kind), QStandardItem(str(native))
            kind_item.setForeground(QColor(TOKENS["muted"]))
            native_item.setForeground(QColor(TOKENS["muted"]))
            native_item.setToolTip(str(native))
            groups[group].appendRow([name, kind_item, native_item])
            self._indices[ref] = name
        # Preserve useful names in a narrow dock; secondary columns can scroll.
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)
        self.setColumnHidden(2, not any(field(field(node, "ref"), "native_scope") for node in nodes))
        for group, item in groups.items():
            count = self._model.item(item.row(), 1)
            count.setText(str(item.rowCount()))
            count.setForeground(QColor(TOKENS["muted"]))
            self.setExpanded(item.index(), expansion.get(group, True))
        if selected in self._indices:
            self.setCurrentIndex(self._indices[selected].index())
        self.verticalScrollBar().setValue(scroll)
        self._resetting = False

    def selected_ref(self):
        return self.currentIndex().siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)

    def select_ref(self, ref):
        item = self._indices.get(ref)
        if item is not None:
            self.setCurrentIndex(item.index())
            self.scrollTo(item.index())
            return True
        return False

    def _selected(self, current, previous):
        ref = current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        if ref is not None and not self._resetting:
            self.nodeSelected.emit(ref)


ObjectTree = ModelTree
