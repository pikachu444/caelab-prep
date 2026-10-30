"""Provider-driven model/view navigation without domain-specific naming."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeView

from ..theme import icon


def field(item, name, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


class ModelTree(QTreeView):
    nodeSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Model objects")
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setIndentation(14)
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
        widths = [self.columnWidth(column) for column in range(3)] if self._model.rowCount() else (220, 80, 100)
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
                groups[group] = parent
                self._model.appendRow([parent, QStandardItem(), QStandardItem()])
            ref = field(node, "ref")
            name = QStandardItem(icon(field(node, "icon", "card")), str(field(node, "label", "")))
            name.setData(ref, Qt.ItemDataRole.UserRole)
            name.setToolTip(str(field(node, "tooltip", "") or field(node, "label", "")))
            kind = str(field(ref, "kind", ""))
            native = field(ref, "native_scope") or field(ref, "object_id", "")
            groups[group].appendRow([name, QStandardItem(kind), QStandardItem(str(native))])
            self._indices[ref] = name
        # Preserve useful names in a narrow dock; secondary columns can scroll.
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate(widths):
            self.setColumnWidth(column, width)
        self.setColumnHidden(2, not any(field(field(node, "ref"), "native_scope") for node in nodes))
        for group, item in groups.items():
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
