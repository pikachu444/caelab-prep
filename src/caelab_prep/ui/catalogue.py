"""Browsable source assets and live Qt component scenes, without VTK or RAD."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMenu,
                              QPlainTextEdit, QPushButton, QSplitter, QStackedWidget,
                              QTableWidget, QTableWidgetItem, QToolBar, QToolButton,
                              QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..application.contracts import ActionSpec, SetProperties
from ..application.neutral import CurveSession
from .actions import ActionRegistry
from .design import ICON_PURPOSES, TOKENS, icon
from .widgets import CurvePlot, CurveTable, ModelTree, PropertyEditor


@dataclass(frozen=True)
class AssetRecord:
    key: str
    title: str
    purpose: str
    source_path: str
    consumer_scenes: tuple[str, ...]
    status: str
    provenance: str
    permission: str


def _asset(key, title, purpose, source, scenes, status="Implemented; live component scene"):
    return AssetRecord(key, title, purpose, "src/caelab_prep/ui/" + source, tuple(scenes), status,
                       "Original CAELab implementation; Qt controls supplied by PySide6",
                       "Public redistribution license not declared for repository source; Qt/PySide6 terms: THIRD_PARTY.md")


_ICON_CONSUMERS = {
    "open": ("Gallery / RAD: Open",), "save": ("Gallery / RAD: Save",),
    "export": ("RAD: Export",), "undo": ("Gallery / RAD: Undo",),
    "redo": ("Gallery / RAD: Redo",), "fit": ("RAD: Fit view",),
    "iso": ("RAD: Isometric view",), "edges": ("RAD: Mesh edges",),
    "card": ("Gallery: reload / catalogue", "RAD: other card categories"),
    "apply": ("Gallery / RAD: Apply", "Catalogue: shared command"),
    "material": ("Material composition: material tree", "RAD: Materials"),
    "curve": ("Material composition: curve tree", "RAD: Curves"),
    "section": ("RAD: Properties",), "part": ("RAD: Parts",),
    "mesh": ("RAD: Elements", "Gallery: disabled solver command"),
    "constraint": ("RAD: Constraints",), "contact": ("RAD: Contacts",),
    "set": ("RAD: Groups",), "load": ("RAD: Loads",),
    "vector": ("RAD: Initial conditions",), "select": ("RAD: Nodes", "Catalogue: shared command"),
    "job": ("Catalogue: disabled command",),
}


ASSETS = (
    _asset("component.numeric", "Numeric input states", "Finite scalar drafts, errors, disabled input and keyboard focus.",
           "widgets/numeric.py", ("Catalogue: numeric states", "Material composition", "RAD properties")),
    _asset("component.vector-units", "Vector and units", "Atomic vector input and explicit MPa/GPa display conversion.",
           "widgets/numeric.py", ("Catalogue: vector and units", "Material composition", "RAD velocity fields")),
    _asset("component.properties", "Grouped properties", "Provider labels, groups, editable and read-only values; Apply and Undo.",
           "widgets/properties.py", ("Catalogue: properties", "Material composition", "RAD properties")),
    _asset("component.tree", "Object tree", "Grouped objects, long Korean names, selection and provider properties.",
           "widgets/tree.py", ("Catalogue: tree", "Material composition", "RAD model tree")),
    _asset("component.curve", "Curve table and plot", "Validated paste preview, committed plot, one Apply and one Undo.",
           "widgets/curve.py", ("Catalogue: curve", "Material composition", "RAD FUNCT editor")),
    _asset("component.actions", "Buttons and menus", "One QAction shared by a menu and toolbar; enabled, checked and focus states.",
           "actions.py", ("Catalogue: actions", "Material composition", "RAD document commands")),
    _asset("component.messages", "Messages", "Readable normal, warning and error messages with selectable text.",
           "catalogue.py:MessageScene", ("Catalogue: messages",), "Implemented; Qt message presentation example"),
    _asset("design.tokens", "Shared design tokens", "The source values used by shared QSS, icon drawing and widget metrics.",
           "design/tokens.py", ("All shared component scenes", "Material composition", "RAD workspace"),
           "Implemented; consumed by design/appearance.py and widgets"),
) + tuple(_asset("icon." + key, key.replace("_", " ").capitalize(), purpose,
                 "design/appearance.py:_PATHS[" + key + "]",
                 ("Catalogue: semantic icons",) + _ICON_CONSUMERS.get(key, ()),
                 "Implemented original SVG; asset preview does not enable a modelling command")
          for key, purpose in ICON_PURPOSES.items())


def _label(text, *, title=False):
    label = QLabel(text)
    label.setWordWrap(True)
    if title:
        label.setObjectName("propertyTitle")
    return label


def _layout(widget):
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(*([TOKENS["space_lg"]] * 4))
    layout.setSpacing(TOKENS["space_md"])
    return layout


class PropertyScene(QWidget):
    """A small real provider consumer; components still own only their drafts."""

    def __init__(self, mode="properties", parent=None):
        super().__init__(parent)
        self.session = CurveSession()
        self.mode = mode
        self.target = self.session.tree_nodes()[0].ref
        layout = _layout(self)
        layout.addWidget(_label("Editable sample document · Apply validates; Undo restores one command."))
        if mode == "tree":
            self.tree = ModelTree()
            self.tree.set_nodes(self.session.tree_nodes())
            self.tree.setMaximumHeight(TOKENS["plot_min_height"])
            self.tree.nodeSelected.connect(self._select)
            layout.addWidget(self.tree)
        self.editor = PropertyEditor()
        layout.addWidget(self.editor, 1)
        self.message = _label("")
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        self.focus_button = QPushButton("Focus input")
        self.focus_button.clicked.connect(self._focus)
        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self.undo)
        self.revert_button = QPushButton("Revert")
        self.revert_button.clicked.connect(self.load)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryAction")
        self.apply_button.clicked.connect(self.apply)
        for button in (self.focus_button, self.undo_button, self.revert_button, self.apply_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.load()
        if mode == "numeric":
            self.editor.editors["poisson_ratio"].setText("1e")
            self.editor.set_error("poisson_ratio", "Enter a valid number")
            self.message.setText("Normal modulus / disabled density / invalid Poisson draft. Correct the draft or Revert.")
        if mode == "tree":
            self.tree.select_ref(self.target)

    def _specs(self):
        specs = [spec for spec in self.session.properties(self.target) if spec.kind != "table"]
        if self.mode == "numeric":
            specs = [replace(spec, editable=False) if spec.name == "density" else spec
                     for spec in specs if spec.name in {"young_modulus", "density", "poisson_ratio"}]
        elif self.mode == "vector-units":
            specs = [spec for spec in specs if spec.name in {"young_modulus", "direction"}]
        return specs

    def load(self):
        node = next(node for node in self.session.tree_nodes() if node.ref == self.target)
        self.editor.set_fields(self._specs(), title=node.label,
                               subtitle="Tab through controls; Escape reverts the focused numeric draft.")
        self._revision = self.session.describe()["revision"]
        self._baseline = self.editor.raw_values(), self.editor.units()
        self.undo_button.setEnabled(self.session.describe()["can_undo"])
        self.message.setText(f"Revision {self._revision} · committed document values")

    def apply(self):
        try:
            values = self.editor.values()
            units = {name: unit for name, unit in self.editor.units().items() if name in values}
            self.session.submit(SetProperties(self.target, values, self._revision, units))
        except Exception as exc:
            self.message.setText(str(exc))
            return False
        self.load()
        if hasattr(self, "tree"):
            self.tree.set_nodes(self.session.tree_nodes())
        return True

    def undo(self):
        if (self.editor.raw_values(), self.editor.units()) != self._baseline and not self.apply():
            return False
        if self.session.describe()["can_undo"]:
            self.session.undo()
            self.load()
            if hasattr(self, "tree"):
                self.tree.set_nodes(self.session.tree_nodes())

    def _select(self, ref):
        if ref == self.target:
            return
        if (self.editor.raw_values(), self.editor.units()) != self._baseline and not self.apply():
            self.tree.select_ref(self.target)
            return
        self.target = ref
        self.session.select(ref)
        self.load()

    def _focus(self):
        for editor in self.editor.editors.values():
            if editor.isEnabled():
                editor.setFocus(Qt.FocusReason.OtherFocusReason)
                break


class CurveScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = CurveSession()
        layout = _layout(self)
        layout.addWidget(_label("Edit cells or Paste points…; the plot changes after Apply curve. Undo restores the full curve."))
        self.selector = QComboBox()
        self.selector.setAccessibleName("Sample curve")
        for node in self.session.tree_nodes():
            if node.ref.kind == "curve":
                self.selector.addItem(node.label, node.ref)
        layout.addWidget(self.selector)
        self.plot = CurvePlot()
        self.plot.setMinimumHeight(TOKENS["plot_preview_min_height"])
        self.table = CurveTable(require_increasing_x=True)
        self.table.setMinimumHeight(TOKENS["plot_min_height"])
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.plot)
        splitter.addWidget(self.table)
        splitter.setSizes([TOKENS["plot_preview_min_height"], TOKENS["plot_min_height"]])
        layout.addWidget(splitter, 1)
        self.undo_button = QPushButton("Undo curve edit")
        self.undo_button.clicked.connect(self.undo)
        layout.addWidget(self.undo_button)
        self.table.pointsEdited.connect(self._commit)
        self._current_index = 0
        self.selector.currentIndexChanged.connect(self._select)
        self.load()

    def load(self):
        self.target = self.selector.currentData()
        spec = next(spec for spec in self.session.properties(self.target) if spec.kind == "table")
        points = self.session.curve_points(self.target)
        self.table.set_points(points, headers=spec.components)
        self.plot.set_points(points, x_label=f"X [{spec.components[0]}]", y_label=f"Y [{spec.components[1]}]")
        self._revision = self.session.describe()["revision"]
        self.undo_button.setEnabled(self.session.describe()["can_undo"])

    def _commit(self, points):
        try:
            self.session.set_curve_points(self.target, points, self._revision)
        except Exception as exc:
            self.table.message.setText(str(exc))
            return False
        self.load()
        return True

    def _select(self, index):
        if self.table.has_draft():
            try:
                accepted = self._commit(self.table.points())
            except ValueError as exc:
                self.table.message.setText(str(exc))
                accepted = False
            if not accepted:
                self.selector.blockSignals(True)
                self.selector.setCurrentIndex(self._current_index)
                self.selector.blockSignals(False)
                return
        self._current_index = index
        self.load()

    def undo(self):
        if self.table.has_draft():
            try:
                if not self._commit(self.table.points()):
                    return False
            except ValueError as exc:
                self.table.message.setText(str(exc))
                return False
        if self.session.describe()["can_undo"]:
            self.session.undo()
            self.load()


class ActionScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = _layout(self)
        layout.addWidget(_label("The menu and toolbar use the same actions. Hover or Tab to inspect real Qt states."))
        self.count = 0
        self.message = _label("No message recorded")
        self.actions = ActionRegistry(self)
        self.record_action = self.actions.register(
            ActionSpec("sample.record", "Record message", icon="apply", capability="record_message"), self.record)
        self.details_action = self.actions.register(
            ActionSpec("sample.details", "Show details", icon="select", checkable=True),
            lambda checked: self.details.setVisible(checked))
        self.unavailable_action = self.actions.register(
            ActionSpec("sample.solver", "Solver unavailable", icon="job", capability="solver_execution"), lambda: None)
        toolbar = QToolBar("Component commands")
        toolbar.setIconSize(QSize(TOKENS["icon_size"], TOKENS["icon_size"]))
        toolbar.addActions([self.record_action, self.details_action, self.unavailable_action])
        layout.addWidget(toolbar)
        menu = QMenu(self)
        menu.addActions([self.record_action, self.details_action, self.unavailable_action])
        self.menu_button = QToolButton()
        self.menu_button.setText("Command menu")
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_button.setMenu(menu)
        layout.addWidget(self.menu_button)
        self.enable_control = QCheckBox("Enable Record message")
        self.enable_control.setChecked(True)
        self.enable_control.toggled.connect(self._refresh_actions)
        layout.addWidget(self.enable_control)
        layout.addWidget(self.message)
        self.details = _label("Checked state is shared by both presentations of Show details.")
        self.details.hide()
        layout.addWidget(self.details)
        layout.addStretch()
        self._refresh_actions()

    def _refresh_actions(self):
        self.actions.refresh({"capabilities": {"record_message": self.enable_control.isChecked(),
                                               "solver_execution": False}})

    def record(self):
        self.count += 1
        self.message.setText(f"Recorded message {self.count}")


class MessageScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = _layout(self)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setAccessibleName("Component messages")
        self.messages.setPlainText("Ready: editable sample document loaded.\nWarning: solver execution is unavailable in this Qt-only scene.\nError example: 잘못된 숫자 1e — draft retained; no document values changed.")
        layout.addWidget(self.messages, 1)
        row = QHBoxLayout()
        for label, callback in (("Append message", lambda: self.messages.appendPlainText("Ready: message appended.")),
                                ("Clear messages", self.messages.clear)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)


def _token_scene():
    widget = QWidget()
    layout = _layout(widget)
    layout.addWidget(_label("Read-only design source · consumed by shared styles, icons, input layouts and the plot."))
    table = QTableWidget(len(TOKENS), 2)
    table.setAccessibleName("Shared design tokens")
    table.setHorizontalHeaderLabels(["Semantic key", "Source value"])
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setDefaultSectionSize(TOKENS["row_height"])
    for row, (key, value) in enumerate(TOKENS.items()):
        table.setItem(row, 0, QTableWidgetItem(key))
        item = QTableWidgetItem(str(value))
        if isinstance(value, str) and value.startswith("#"):
            item.setIcon(_color_icon(value))
        table.setItem(row, 1, item)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(table, 1)
    return widget


def _color_icon(color):
    from PySide6.QtGui import QIcon, QPixmap
    pixmap = QPixmap(TOKENS["icon_size"], TOKENS["icon_size"])
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def _icon_scene(key):
    widget = QWidget()
    layout = _layout(widget)
    layout.addWidget(_label(ICON_PURPOSES[key], title=True))
    layout.addWidget(_label("Original SVG line asset. Preview controls toggle checked state; they do not execute a modelling command."))
    for size, enabled, title in ((TOKENS["icon_size"], True, "Toolbar size · click to check"),
                                 (TOKENS["tree_indent"], True, "Tree size · click to check"),
                                 (TOKENS["icon_size"], False, "Disabled presentation")):
        button = QToolButton()
        button.setIcon(icon(key))
        button.setIconSize(QSize(size, size))
        button.setText(title)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(True)
        button.setEnabled(enabled)
        button.setAccessibleName(f"{key}: {title}")
        layout.addWidget(button)
    layout.addStretch()
    return widget


class CatalogueWidget(QWidget):
    """Select an asset to inspect provenance and operate its actual component."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.assets = ASSETS
        self._records = {asset.key: asset for asset in self.assets}
        self._items, self._pages = {}, {}
        self.setAccessibleName("Shared component catalogue")
        layout = _layout(self)
        layout.addWidget(_label("Component catalogue", title=True))
        layout.addWidget(_label("Browse shared source assets. Component scenes use editable sample documents; the material workspace is a composition example."))
        splitter = QSplitter()
        self.navigation = QTreeWidget()
        self.navigation.setHeaderHidden(True)
        self.navigation.setAccessibleName("Catalogue assets")
        self.navigation.setMinimumWidth(TOKENS["catalogue_navigation_width"])
        groups = {}
        for asset in self.assets:
            group = "Components" if asset.key.startswith("component.") else "Semantic icons" if asset.key.startswith("icon.") else "Design source"
            if group not in groups:
                groups[group] = QTreeWidgetItem(self.navigation, [group])
                groups[group].setFlags(groups[group].flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item = QTreeWidgetItem(groups[group], [asset.title])
            item.setData(0, Qt.ItemDataRole.UserRole, asset.key)
            item.setToolTip(0, asset.key)
            if asset.key.startswith("icon."):
                item.setIcon(0, icon(asset.key.removeprefix("icon.")))
            self._items[asset.key] = item
        self.navigation.expandAll()
        splitter.addWidget(self.navigation)
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.metadata = QPlainTextEdit()
        self.metadata.setReadOnly(True)
        self.metadata.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self.metadata.setMaximumHeight(TOKENS["catalogue_metadata_height"])
        self.metadata.setAccessibleName("Selected asset metadata")
        detail_layout.addWidget(self.metadata)
        self.scene_stack = QStackedWidget()
        detail_layout.addWidget(self.scene_stack, 1)
        splitter.addWidget(detail)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self.navigation.currentItemChanged.connect(self._selected)
        self.select_asset("component.numeric")

    @property
    def scene(self):
        return self.scene_stack.currentWidget()

    def selected_asset(self):
        item = self.navigation.currentItem()
        return self._records.get(item.data(0, Qt.ItemDataRole.UserRole)) if item else None

    def select_asset(self, key):
        item = self._items.get(key)
        if item is None:
            return False
        self.navigation.setCurrentItem(item)
        self.navigation.scrollToItem(item)
        return True

    def _selected(self, item, previous):
        asset = self.selected_asset()
        if asset is None:
            return
        self.metadata.setPlainText("\n".join(f"{label}: {value}" for label, value in (
            ("Key", asset.key), ("Purpose", asset.purpose), ("Source", asset.source_path),
            ("Consumers", "; ".join(asset.consumer_scenes)), ("Status", asset.status),
            ("Provenance", asset.provenance), ("Permission", asset.permission))))
        if asset.key not in self._pages:
            kind = asset.key.removeprefix("component.")
            if kind in {"numeric", "vector-units", "properties", "tree"}:
                page = PropertyScene(kind)
            elif kind == "curve":
                page = CurveScene()
            elif kind == "actions":
                page = ActionScene()
            elif kind == "messages":
                page = MessageScene()
            elif asset.key == "design.tokens":
                page = _token_scene()
            else:
                page = _icon_scene(asset.key.removeprefix("icon."))
            self._pages[asset.key] = page
            self.scene_stack.addWidget(page)
        self.scene_stack.setCurrentWidget(self._pages[asset.key])
