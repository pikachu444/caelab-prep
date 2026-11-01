"""Presentation adapters composed over existing views and document commands."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDockWidget,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QPushButton, QSizePolicy, QSplitter,
    QStyledItemDelegate, QTabWidget, QToolBar, QToolButton, QTreeView, QVBoxLayout, QWidget)

from .reference_profiles import profile
from .widgets import PropertyEditor, VectorEdit


@dataclass
class ReferenceBindings:
    """Presentation handles and existing commands, with no provider dependency."""
    window: QMainWindow
    tree: QTreeView
    model_dock: QDockWidget
    properties_dock: QDockWidget
    messages_dock: QDockWidget
    editor: PropertyEditor
    toolbar: QToolBar
    commands: Mapping[str, tuple[QAction, ...]]
    apply: Callable[[], bool]
    revert: Callable[[], None]
    table: QWidget
    plot: QWidget
    curve_parent: QWidget
    curve_surface: QSplitter | None = None
    property_tabs: QTabWidget | None = None
    inspector_buttons: tuple[QWidget, ...] = ()
    selection_tools: QWidget | None = None
    viewport: QWidget | None = None
    dialog: QDialog | None = None
    curve_pages: QWidget | None = None
    edit_action: QAction | None = None
    dialog_buttons: QWidget | None = None


def reference_style(key):
    return """
    QWidget { font-family: 'Segoe UI'; font-size: 12px; }
    QToolBar { padding: 1px 3px; spacing: 2px; }
    QToolButton { min-height: 19px; padding: 2px 4px; }
    QTreeView::item { padding: 0 2px; }
    QDockWidget::title { padding: 3px 6px; }
    QLineEdit, QComboBox { min-height: 20px; padding: 1px 4px; }
    QLabel#propertyTitle { font-size: 12px; }
    QHeaderView::section { padding: 2px 5px; }
    QTabBar::tab { padding: 3px 8px; }
    QLabel#commandGroup { color: #52606a; font-size: 11px; }
    QTabWidget#referenceCommands::pane { border: 0; }
    """


class _CommandGroup(QWidget):
    """Keep direct commands when they fit, with named group menus when narrow."""

    def __init__(self, key, actions, kind, parent=None):
        super().__init__(parent)
        self.setObjectName("referenceCommandGroup")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        stack = QVBoxLayout(self)
        stack.setContentsMargins(3, 0, 3, 0)
        stack.setSpacing(0)
        self.buttons = QWidget()
        commands = QHBoxLayout(self.buttons)
        commands.setContentsMargins(2, 1, 2, 1)
        for action in actions:
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                if kind == "ribbon" else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(24, 24) if kind == "ribbon" else QSize(16, 16))
            commands.addWidget(button)
        stack.addWidget(self.buttons)
        self.menu_button = QToolButton()
        self.menu_button.setObjectName("referenceGroupMenu")
        self.menu_button.setText(key)
        self.menu_button.setAccessibleName(key + " commands")
        self.menu_button.setToolTip(key + " commands")
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.menu_button)
        menu.addActions(actions)
        self.menu_button.setMenu(menu)
        stack.addWidget(self.menu_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.menu_button.hide()
        caption = QLabel(key)
        caption.setObjectName("commandGroup")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stack.addWidget(caption)
        self.ensurePolished()
        for widget in self.findChildren(QWidget):
            widget.ensurePolished()
        self._preferred = super().sizeHint()
        self._minimum = QSize(self.menu_button.sizeHint().width() + 6, self._preferred.height())
        self.setMinimumWidth(self._minimum.width())

    def sizeHint(self):
        return self._preferred if hasattr(self, "_preferred") else super().sizeHint()

    def minimumSizeHint(self):
        return self._minimum if hasattr(self, "_minimum") else super().minimumSizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        narrow = self.width() < self._preferred.width()
        self.buttons.setVisible(not narrow)
        self.menu_button.setVisible(narrow)


@dataclass(frozen=True)
class CommandSurface:
    kind: str
    pages: tuple[tuple[str, tuple[str, ...]], ...] = ()
    quick_groups: tuple[str, ...] = ()

    def install(self, b: ReferenceBindings):
        b.toolbar.clear()
        contextual_bar = b.toolbar
        if self.quick_groups:
            b.toolbar.setIconSize(QSize(16, 16))
            b.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            for key in self.quick_groups:
                b.toolbar.addActions(b.commands[key])
                b.toolbar.addSeparator()
            contextual_bar = QToolBar("Context commands", b.window)
            contextual_bar.setObjectName("referenceContextCommands")
            contextual_bar.setMovable(False)
            b.window.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
            b.window.addToolBar(Qt.ToolBarArea.TopToolBarArea, contextual_bar)
        if self.kind in ("icons", "module"):
            b.toolbar.setIconSize(QSize(16, 16))
            b.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            for group in b.commands.values():
                if b.toolbar.actions():
                    b.toolbar.addSeparator()
                b.toolbar.addActions(group)
            if self.kind == "module":
                context = QComboBox()
                context.setAccessibleName("Module")
                context.addItem("Property")
                context.setToolTip("Only the Property editing module is supported")
                b.toolbar.addWidget(QLabel("Module:"))
                b.toolbar.addWidget(context)
            return
        tabs = QTabWidget(contextual_bar)
        tabs.setObjectName("referenceCommands")
        for title, keys in self.pages:
            if not any(b.commands.get(key) for key in keys):
                continue
            page = QWidget(tabs)
            row = QHBoxLayout(page)
            row.setContentsMargins(0, 0, 0, 0)
            for key in keys:
                if not b.commands.get(key):
                    continue
                row.addWidget(_CommandGroup(key, b.commands[key], self.kind, page))
            row.addStretch()
            tabs.addTab(page, title)
        contextual_bar.addWidget(tabs)


@dataclass(frozen=True)
class DockArrangement:
    model_title: str
    property_title: str
    adjacent: bool = False
    output: bool = False
    row_height: int = 21
    source_title: str = "Card source"
    output_below_viewport: bool = False
    outline_fraction: float | None = None

    def install(self, b: ReferenceBindings):
        b.model_dock.setWindowTitle(self.model_title)
        b.properties_dock.setWindowTitle(self.property_title)
        b.model_dock.setMinimumWidth(170)
        b.properties_dock.setMinimumWidth(250)
        b.tree.setRootIsDecorated(True)
        b.tree.setIndentation(16)
        b.tree.setColumnHidden(1, True)
        b.tree.setItemDelegate(ReferenceTreeDelegate(self.row_height, b.tree))
        if self.adjacent:
            b.window.removeDockWidget(b.properties_dock)
            b.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, b.properties_dock)
            b.window.splitDockWidget(b.model_dock, b.properties_dock, Qt.Orientation.Horizontal)
            b.properties_dock.show()
        if self.output:
            if self.output_below_viewport:
                b.window.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
            b.messages_dock.show()
            b.window.resizeDocks([b.messages_dock], [90], Qt.Orientation.Vertical)


class ReferenceTreeDelegate(QStyledItemDelegate):
    """Native hierarchy rows, rather than the default gallery's group bands."""
    def __init__(self, height, parent):
        super().__init__(parent)
        self.height = height

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(self.height)
        return size


@dataclass(frozen=True)
class EditorInteraction:
    mode: str
    title: str = "Edit properties"

    def install(self, b: ReferenceBindings):
        if self.mode in ("inline", "dialog"):
            for button in b.inspector_buttons:
                button.hide()
        if self.mode != "dialog":
            return
        panel = b.properties_dock.widget()
        b.properties_dock.setWidget(QWidget())
        b.properties_dock.hide()
        dialog = QDialog(b.window)
        dialog.setObjectName("referencePropertyDialog")
        dialog.setWindowTitle(self.title + " — CAELab Prep")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.resize(540, 560)
        column = QVBoxLayout(dialog)
        column.addWidget(panel)
        panel.show()
        buttons = QWidget()
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch()
        ok, cancel = QPushButton("OK"), QPushButton("Cancel")
        ok.setObjectName("primaryAction")
        def accept():
            if b.apply():
                dialog.accept()
        ok.clicked.connect(accept)
        cancel.clicked.connect(dialog.reject)
        dialog.rejected.connect(b.revert)
        row.addWidget(ok)
        row.addWidget(cancel)
        column.addWidget(buttons)
        b.dialog_buttons = buttons
        b.dialog = dialog
        b.tree.doubleClicked.connect(lambda _: dialog.open())

    def bind_fields(self, editors: Mapping[str, QWidget], apply: Callable[[], bool],
                    bindings: ReferenceBindings):
        if self.mode != "inline":
            return
        # A vector keeps one explicit transaction for all of its components.
        has_vector = any(isinstance(editor, VectorEdit) and editor.isEnabled()
                         for editor in editors.values())
        for button in bindings.inspector_buttons:
            button.setVisible(has_vector)
        for editor in editors.values():
            if not editor.isEnabled():
                continue
            if isinstance(editor, QLineEdit):
                editor.editingFinished.connect(apply)
            elif isinstance(editor, QComboBox):
                editor.activated.connect(lambda _: apply())
            elif isinstance(editor, QCheckBox):
                editor.clicked.connect(lambda _: apply())


@dataclass(frozen=True)
class CurveArrangement:
    mode: str
    labels: tuple[str, str] = ("Data", "Plot")

    def install(self, b: ReferenceBindings):
        if self.mode == "stacked":
            return
        # Reparent the real editors, retaining their draft/validation connections.
        if self.mode == "side":
            surface = b.curve_surface or QSplitter(Qt.Orientation.Horizontal)
            surface.setOrientation(Qt.Orientation.Horizontal)
            surface.addWidget(b.table)
            surface.addWidget(b.plot)
            surface.setSizes([350, 500])
            if b.curve_surface is None:
                b.curve_parent.layout().insertWidget(2, surface)
                b.curve_pages = surface
            return
        pages = QTabWidget()
        pages.setObjectName("referenceCurvePages")
        pages.addTab(b.table, self.labels[0])
        pages.addTab(b.plot, self.labels[1])
        if b.curve_surface is not None:
            b.curve_surface.addWidget(pages)
        else:
            b.curve_parent.layout().insertWidget(2, pages)
        b.curve_pages = pages


@dataclass(frozen=True)
class ReferenceAdapter:
    key: str
    commands: CommandSurface
    docks: DockArrangement
    interaction: EditorInteraction
    curves: CurveArrangement
    selection_position: str = "header"
    selection_icons: bool = False

    @property
    def defer_scalars(self):
        return self.interaction.mode == "dialog"

    def install(self, b: ReferenceBindings):
        b.window.setStyleSheet(b.window.styleSheet() + reference_style(self.key))
        b.editor.set_presentation(profile(self.key).property_mode)
        self.commands.install(b)
        self.docks.install(b)
        self.curves.install(b)
        self.interaction.install(b)
        edit = b.edit_action or b.commands["Material"][0]
        edit.triggered.connect(lambda: b.dialog.open() if b.dialog else b.properties_dock.show())
        menu = b.window.menuBar().addMenu("Property" if self.commands.kind in ("icons", "module") else "Material")
        for group in ("Material", "Section", "Object", "Assignment"):
            group_actions = b.commands.get(group, ())
            if group_actions:
                if menu.actions():
                    menu.addSeparator()
                menu.addActions(group_actions)
        if b.commands.get("Selection"):
            b.window.menuBar().addMenu("Selection").addActions(b.commands["Selection"])
        if b.commands.get("Conditions"):
            conditions = b.window.menuBar().addMenu("Conditions")
            conditions.addActions(b.commands.get("Curve", ()))
            conditions.addSeparator()
            conditions.addActions(b.commands["Conditions"])
        if b.property_tabs is not None:
            b.property_tabs.setTabText(0, self.docks.property_title)
            b.property_tabs.setTabText(1, self.docks.source_title)
        if b.selection_tools is not None and self.selection_position != "header":
            if self.selection_position == "global":
                b.selection_tools.setMovable(False)
                b.selection_tools.setFloatable(False)
                if self.selection_icons:
                    b.selection_tools.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                b.window.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
                b.window.addToolBar(Qt.ToolBarArea.TopToolBarArea, b.selection_tools)
            elif self.selection_position == "bottom":
                layout = b.viewport.layout()
                layout.addWidget(b.selection_tools)
            else:
                layout = b.viewport.layout()
                layout.insertWidget(1, b.selection_tools)
        self.resize(b)

    def resize(self, b: ReferenceBindings):
        if self.docks.adjacent:
            width = max(800, b.window.width())
            b.window.resizeDocks([b.model_dock, b.properties_dock],
                [round(width * .17), max(320, round(width * .27))], Qt.Orientation.Horizontal)
        else:
            width = round(b.window.width() * profile(self.key).tree_fraction)
            if self.interaction.mode != "dialog":
                width = max(340, width)
            b.window.resizeDocks([b.model_dock], [width], Qt.Orientation.Horizontal)
        if self.docks.outline_fraction is not None:
            # Initial arrangement only: the host calls resize before its first
            # show, so subsequent user splitter changes remain untouched.
            b.properties_dock.setMinimumHeight(180)
            fraction = self.docks.outline_fraction
            b.window.resizeDocks([b.model_dock, b.properties_dock],
                [round(1000 * fraction), round(1000 * (1 - fraction))], Qt.Orientation.Vertical)

    def bind_fields(self, editors: Mapping[str, QWidget], apply: Callable[[], bool],
                    bindings: ReferenceBindings):
        self.interaction.bind_fields(editors, apply, bindings)


# Independent command, docking, editing and curve choices at one shared seam.
ADAPTERS = {
    "hypermesh": ReferenceAdapter("hypermesh", CommandSurface("compact", (("Home", ("Document", "History")), ("Materials", ("Material", "Section", "Assignment", "Object")), ("Sets", ("Selection",)), ("Conditions", ("Curve", "Conditions")))), DockArrangement("Model", "Entity Editor"), EditorInteraction("inline"), CurveArrangement("side")),
    "prepomax": ReferenceAdapter("prepomax", CommandSurface("icons"), DockArrangement("FE Model", "Properties", output=True, row_height=19, output_below_viewport=True), EditorInteraction("dialog", "Edit material / curve"), CurveArrangement("stacked"), "global", selection_icons=True),
    "abaqus": ReferenceAdapter("abaqus", CommandSurface("module"), DockArrangement("Model", "Properties"), EditorInteraction("dialog", "Edit Material"), CurveArrangement("pages")),
    "comsol": ReferenceAdapter("comsol", CommandSurface("ribbon", (("Home", ("Document", "History")), ("Model", ("Material", "Section", "Assignment", "Object")), ("Definitions", ("Selection", "Curve")), ("Physics", ("Conditions",)))), DockArrangement("Model Builder", "Settings", adjacent=True), EditorInteraction("settings"), CurveArrangement("stacked")),
    "nfx": ReferenceAdapter("nfx", CommandSurface("ribbon", (("파일", ("Document", "History")), ("모델", ("Material", "Section", "Assignment", "Object")), ("선택", ("Selection",)), ("조건", ("Curve", "Conditions")))), DockArrangement("Model", "Properties"), EditorInteraction("dialog", "재료"), CurveArrangement("stacked")),
    "meshfree": ReferenceAdapter("meshfree", CommandSurface("ribbon", (("Home", ("Document", "History")), ("Material", ("Material", "Section", "Assignment", "Object")), ("Selection", ("Selection",)), ("Analysis", ("Curve", "Conditions")))), DockArrangement("Model", "Properties"), EditorInteraction("dialog", "Material"), CurveArrangement("pages", ("Spreadsheet", "Graph"))),
    "naksha": ReferenceAdapter("naksha", CommandSurface("ribbon", (("Materials", ("Material", "Section", "Assignment", "Object")), ("Selections", ("Selection",)), ("Conditions", ("Curve", "Conditions"))), quick_groups=("Document", "History")), DockArrangement("Outline", "Details", outline_fraction=.57), EditorInteraction("details"), CurveArrangement("side"), "global"),
    "beidprep": ReferenceAdapter("beidprep", CommandSurface("compact", (("MODEL", ("Document", "History", "Material", "Section", "Assignment", "Object")), ("SET", ("Selection",)), ("CONDITION", ("Curve", "Conditions")))), DockArrangement("MODEL", "FORM", adjacent=True, source_title="TEXT"), EditorInteraction("adjacent"), CurveArrangement("stacked"), "bottom"),
}
