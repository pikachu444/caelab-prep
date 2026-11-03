"""Optional display state stays separate from object selection and edits."""

import os
from dataclasses import FrozenInstanceError

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPersistentModelIndex, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from caelab_prep.application.contracts import ObjectRef, TreeNode
from caelab_prep.ui.design import TOKENS
from caelab_prep.ui.reference_components import ReferenceTreeDelegate
from caelab_prep.ui.widgets.tree import ModelTree, TreeAppearance


def nodes(count=3):
    return [TreeNode(ObjectRef("document", f"resource-{i % 2}", f"private-uuid-{i}",
                               "rad-card", f"/PART/{i + 1}"),
                     f"Part {i + 1}", "Parts", "part") for i in range(count)]


def show_tree(app, items, appearances=None, reference_height=None):
    tree = ModelTree()
    if reference_height is not None:
        tree.setItemDelegate(ReferenceTreeDelegate(reference_height, tree))
    tree.resize(700, 220)
    tree.set_nodes(items, appearances=appearances)
    tree.show()
    app.processEvents()
    return tree


def test_appearance_is_immutable_and_id_never_falls_back_to_uuid(qt_widgets):
    appearance = TreeAppearance(True, "#123456")
    with pytest.raises(FrozenInstanceError):
        appearance.visible = False
    native = nodes(1)[0]
    neutral = TreeNode(ObjectRef("document", "neutral", "private-neutral-uuid", "curve"),
                       "Load curve", "Curves")
    tree = show_tree(qt_widgets, [native, neutral])
    model = tree.model()
    assert model.item(0).child(0, 2).text() == "/PART/1"
    assert model.item(1).child(0, 2).text() == ""
    assert model.item(1).child(0, 2).toolTip() == ""
    assert tree.selected_ref() is None
    assert tree.isColumnHidden(3) and tree.isColumnHidden(4)
    tree.set_nodes([neutral])
    assert tree.isColumnHidden(2)
    assert model.item(0).child(0, 2).text() == ""


def test_refresh_preserves_qualified_identity_expansion_scroll_and_user_widths(qt_widgets):
    items = nodes(60)
    extra = TreeNode(ObjectRef("document", "other", "material-uuid", "material"),
                     "Material", "Materials")
    appearances = {item.ref: TreeAppearance(True, "#123456") for item in items}
    tree = show_tree(qt_widgets, items + [extra], appearances)
    tree.setSelectionMode(ModelTree.SelectionMode.ExtendedSelection)
    chosen = (items[20].ref, items[30].ref)
    tree.select_refs(chosen, active=chosen[-1])
    tree.setExpanded(tree.model().item(1).index(), False)
    for column, width in ((1, 55), (2, 57), (3, 72), (4, 76)):
        tree.setColumnWidth(column, width)
    tree.verticalScrollBar().setValue(100)
    before_scroll = tree.verticalScrollBar().value()
    selected_events = []
    tree.nodeSelected.connect(selected_events.append)
    tree.set_nodes(list(reversed(items)) + [extra], appearances=appearances)
    qt_widgets.processEvents()
    assert set(tree.selected_refs()) == set(chosen)
    assert tree.selected_ref() == chosen[-1]
    assert not tree.isExpanded(tree.model().item(1).index())
    assert tree.verticalScrollBar().value() == before_scroll
    assert [tree.columnWidth(column) for column in range(1, 5)] == [55, 57, 72, 76]
    assert not selected_events


@pytest.mark.parametrize("reference_height", [None, 19])
def test_visibility_click_and_space_request_without_selection_or_local_change(qt_widgets, reference_height):
    items = nodes()
    appearances = {items[0].ref: TreeAppearance(True), items[1].ref: TreeAppearance(False)}
    tree = show_tree(qt_widgets, items, appearances, reference_height)
    tree.select_ref(items[0].ref)
    requests, selections, activations = [], [], []
    tree.visibilityRequested.connect(lambda ref, visible: requests.append((ref, visible)))
    tree.nodeSelected.connect(selections.append)
    tree.selectedRefsChanged.connect(selections.append)
    tree.doubleClicked.connect(activations.append)
    target = tree.model().item(0).child(1, 3).index()
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualRect(target).center())
    assert requests == [(items[1].ref, True)]
    assert tree.selected_ref() == items[0].ref
    assert tree.selected_refs() == (items[0].ref,)
    assert target.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert not target.flags() & Qt.ItemFlag.ItemIsUserCheckable
    QTest.keyClick(tree, Qt.Key.Key_Space)
    assert requests[-1] == (items[0].ref, False)
    assert tree.selected_ref() == items[0].ref
    QTest.mouseDClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualRect(target).center())
    assert not selections and not activations


def test_appearance_snapshot_updates_roles_without_rebuilding_or_losing_view_state(qt_widgets):
    items = nodes(40)
    tree = show_tree(qt_widgets, items, {items[0].ref: TreeAppearance(True, "#123456")})
    tree.select_ref(items[20].ref)
    tree.setColumnWidth(3, 74)
    tree.setColumnWidth(4, 78)
    tree.verticalScrollBar().setValue(80)
    before_scroll = tree.verticalScrollBar().value()
    item = tree.model().item(0).child(0)
    persistent = QPersistentModelIndex(item.index())
    removals = []
    tree.model().rowsRemoved.connect(lambda *args: removals.append(args))
    tree.update_appearances({items[0].ref: TreeAppearance(False, "#abcdef")})
    assert persistent.isValid() and tree.model().item(0).child(0) is item
    assert item.parent().child(0, 3).data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert item.parent().child(0, 4).data(Qt.ItemDataRole.DecorationRole) == QColor("#abcdef")
    assert not item.parent().child(0, 4).isEditable()
    assert tree.selected_ref() == items[20].ref
    assert tree.verticalScrollBar().value() == before_scroll
    assert not removals
    tree.update_appearances({})
    assert tree.isColumnHidden(3) and tree.isColumnHidden(4)
    assert item.parent().child(0, 3).data(Qt.ItemDataRole.CheckStateRole) is None
    assert item.parent().child(0, 4).data(Qt.ItemDataRole.DecorationRole) is None
    tree.update_appearances({items[0].ref: TreeAppearance(True, "#123456")})
    assert tree.columnWidth(3) == 74 and tree.columnWidth(4) == 78
    assert tree.selected_ref() == items[20].ref


@pytest.mark.parametrize("width", [170, 260, 326])
@pytest.mark.parametrize("hide_type", [False, True])
def test_narrow_tree_keeps_names_and_compact_optional_columns_reachable(qt_widgets, width, hide_type):
    items = nodes()
    appearances = {item.ref: TreeAppearance(True, "#123456") for item in items}
    tree = show_tree(qt_widgets, items, appearances)
    tree.setColumnHidden(1, hide_type)
    tree.resize(width, 220)
    qt_widgets.processEvents()
    assert tree.columnWidth(0) >= 100
    assert tree.columnWidth(3) == tree.columnWidth(4) == 40
    if width < 326 or not hide_type:
        assert tree.horizontalScrollBar().maximum() > 0
    tree.select_ref(items[0].ref)
    tree.horizontalScrollBar().setValue(tree.horizontalScrollBar().maximum())
    target = tree.model().item(0).child(1, 3).index()
    color = target.siblingAtColumn(4)
    assert tree.viewport().rect().contains(tree.visualRect(target).center())
    assert tree.viewport().rect().contains(tree.visualRect(color).center())
    requests = []
    tree.visibilityRequested.connect(lambda ref, visible: requests.append((ref, visible)))
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualRect(target).center())
    assert requests == [(items[1].ref, False)]
    assert tree.selected_ref() == items[0].ref


def test_user_name_and_optional_widths_survive_updates_refresh_and_resize(qt_widgets):
    items = nodes()
    appearances = {items[0].ref: TreeAppearance(True, "#123456")}
    tree = show_tree(qt_widgets, items, appearances)
    tree.setColumnHidden(1, True)
    for column, width in ((0, 145), (3, 53), (4, 55)):
        tree.setColumnWidth(column, width)
    tree.resize(260, 220)
    tree.update_appearances({items[0].ref: TreeAppearance(False, "#abcdef")})
    tree.set_nodes(items, appearances=appearances)
    qt_widgets.processEvents()
    assert [tree.columnWidth(column) for column in (0, 3, 4)] == [145, 53, 55]
    tree.resize(700, 220)
    qt_widgets.processEvents()
    assert tree.columnWidth(0) == 145
    tree.setColumnWidth(0, 45)
    assert tree.columnWidth(0) == 100


@pytest.mark.parametrize("reference_height", [None, 19, 21])
def test_rows_keep_density_but_fit_large_actual_font_and_icons(qt_widgets, reference_height):
    items = nodes(1)
    tree = show_tree(qt_widgets, items, {items[0].ref: TreeAppearance(True, "#123456")}, reference_height)
    font = tree.font()
    font.setPointSize(9)
    tree.setFont(font)
    tree.setStyleSheet("QTreeView::item { min-height: 26px; }")
    tree.doItemsLayout()
    qt_widgets.processEvents()
    index = tree.model().item(0).child(0).index()
    assert tree.visualRect(index).height() == (reference_height or TOKENS["tree_row_height"])
    font.setPointSize(24)
    tree.setFont(font)
    tree.doItemsLayout()
    qt_widgets.processEvents()
    assert tree.visualRect(index).height() >= tree.fontMetrics().height() + 2
    font.setPointSize(9)
    tree.setFont(font)
    tree.setIconSize(QSize(36, 36))
    tree.doItemsLayout()
    qt_widgets.processEvents()
    assert tree.visualRect(index).height() >= 38
