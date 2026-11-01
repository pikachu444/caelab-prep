"""Native Prep workspace: commands, model navigation and contextual inspection.

This is the new visual construction layer. The host's PrepController supplies
actions and guarded editing callbacks; this module never submits model commands.

Replaces main_window.py at 40d8d913, construction lines 146–313. The property
projection is newly expressed here from the existing schema-binding behavior
(lines 418–441 and 498–579). Labels and units follow provider schemas; commit
timing follows the retained controller.
"""

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QActionGroup, QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHeaderView, QLabel, QLineEdit, QMenu,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QTabWidget, QToolBar, QToolButton, QTreeWidget, QVBoxLayout, QWidget,
)

from .shell import ViewportFrame, create_dock
from .theme import STYLESHEET
from .widgets import CurvePlot, CurveTable, ModelTree, PropertyEditor, VectorEdit


class _SelectionTypeMenu(QObject):
    """Keep a menu route to the toolbar's one selection-mode control.

    Qt toolbar overflow does not reliably expose embedded combo widgets. The
    menu remains usable when the model-view toolbar is narrower than its items.
    """

    def __init__(self, combo, menu):
        super().__init__(menu)
        self.combo = combo
        self.menu = menu
        self.group = QActionGroup(menu)
        self.group.setExclusive(True)
        self.actions = []
        for index, (label, key) in enumerate((("Elements", "element"), ("Nodes", "node"))):
            action = menu.addAction(label)
            action.setObjectName("view.selection." + key)
            action.setCheckable(True)
            action.setData(index)
            self.group.addAction(action)
            self.actions.append(action)
        self.group.triggered.connect(lambda action: combo.setCurrentIndex(action.data()))
        combo.currentIndexChanged.connect(self._sync_checked)
        combo.installEventFilter(self)
        self._sync_checked(combo.currentIndex())
        self._sync_enabled()

    def _sync_checked(self, index):
        if 0 <= index < len(self.actions):
            self.actions[index].setChecked(True)

    def _sync_enabled(self):
        self.menu.setEnabled(self.combo.isEnabled())
        self.group.setEnabled(self.combo.isEnabled())

    def eventFilter(self, watched, event):
        if watched is self.combo and event.type() == QEvent.Type.EnabledChange:
            self._sync_enabled()
        return False


class PrepWorkspace:
    """Qt presentation mixed into MainWindow; keeps the host's public UI handles."""

    def build_workspace(self, *, enable_viewport):
        self.setObjectName("caelabPrepWindow")
        self.setWindowTitle("CAELab Prep")
        self.resize(1440, 900)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLESHEET)
        self.setDockOptions(self.DockOption.AllowTabbedDocks | self.DockOption.AllowNestedDocks)

        self._install_command_surfaces()
        self._install_model_view(enable_viewport)
        self._install_navigation()
        self._install_inspector()
        self._install_notices()
        self._install_status()
        self.splitDockWidget(self.model_dock, self.properties_dock, Qt.Orientation.Vertical)
        self.resizeDocks([self.model_dock], [350], Qt.Orientation.Horizontal)
        self.resizeDocks([self.model_dock, self.properties_dock], [400, 330], Qt.Orientation.Vertical)
        self.resizeDocks([self.messages_dock], [125], Qt.Orientation.Vertical)

    def _install_command_surfaces(self):
        groups = (
            ("&File", ((self.mesh_workflow.new_action, self.open_rad_action, self.open_project_action),
                       (self.save_action, self.save_as_action, self.export_action, self.mesh_workflow.export_action), (self.close_action,))),
            ("&Edit", ((self.undo_action, self.redo_action), (self.reload_properties_action,))),
            ("&Model", ((self.modeling.actions["material.create"], self.modeling.actions["section.create"]),
                        (self.modeling.actions["solid_section.create"],),
                        (self.modeling.actions["group.create"], self.modeling.actions["element_group.create"], self.modeling.actions["surface.create"]),
                        (self.modeling.actions["object.edit"],),
                        (self.modeling.actions["object.copy"], self.modeling.actions["object.delete"]),
                        (self.modeling.actions["part.assign"],))),
            ("&Conditions", ((self.modeling.actions["curve.create"],),
                             tuple(self.modeling.actions[key + ".create"] for key in
                                   ("constraint", "load", "velocity", "contact")))),
            ("&Mesh", ((self.mesh_workflow.mesh_action,),)),
            ("&View", ((self.fit_action, self.fit_selected_action, self.iso_action, *self.standard_view_actions, self.edges_action),
                       (self.hide_selected_action, self.isolate_action, self.show_all_action))),
        )
        for name, sections in groups:
            if name in ("&Model", "&Conditions") and self.presentation:
                continue
            menu = self.menuBar().addMenu(name)
            for index, actions in enumerate(sections):
                if index:
                    menu.addSeparator()
                menu.addActions(actions)
            if name == "&View":
                self._view_menu = menu
                menu.addSeparator()

        bar = QToolBar("Document", self)
        self.document_toolbar = bar
        bar.setObjectName("documentToolbar")
        bar.setMovable(False)
        bar.setIconSize(QSize(18, 18))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(bar)
        brand = QLabel("CAELab  /  Prep")
        brand.setObjectName("applicationBrand")
        brand.setContentsMargins(12, 0, 18, 0)
        bar.addWidget(brand)
        for action, label in ((self.open_rad_action, "Open deck"), (self.save_action, "Save"),
                              (self.export_action, "Export")):
            action.setIconText(label)
            bar.addAction(action)
        open_button = bar.widgetForAction(self.open_rad_action)
        open_menu = QMenu(open_button)
        open_menu.addActions([self.open_rad_action, self.open_project_action])
        open_button.setMenu(open_menu)
        open_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        bar.addSeparator()
        bar.addActions([self.undo_action, self.redo_action])
        if not self.presentation:
            bar.addSeparator()
            bar.addActions([self.modeling.actions["material.create"], self.modeling.actions["section.create"],
                            self.modeling.actions["part.assign"]])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.document_state = QLabel()
        self.document_state.setObjectName("documentState")
        self.document_state.setContentsMargins(8, 0, 12, 0)
        bar.addWidget(self.document_state)

    def _install_model_view(self, enabled):
        self.viewport = None
        failure = ""
        if enabled:
            try:
                from .viewport import MeshViewport
                self.viewport = MeshViewport(self)
            except Exception as exc:
                failure = str(exc)
        if self.viewport is not None:
            content = self.viewport
            content.entityPicked.connect(self._entity_picked)
            content.diagnostic.connect(self._viewport_diagnostic)
        else:
            content = QLabel("3D viewer unavailable" if failure else "3D viewer disabled for this session")
            content.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content.setWordWrap(True)
            content.setToolTip(failure)

        self.viewport_frame = ViewportFrame(content, "Model")
        self.viewport_frame.title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.viewport_frame.context.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.viewport_frame.header.addWidget(self._view_commands())
        self.setCentralWidget(self.viewport_frame)

    def _view_commands(self):
        bar = QToolBar("Model view", self)
        bar.setObjectName("modelViewCommands")
        bar.setIconSize(QSize(16, 16))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action, label in ((self.fit_action, "Fit"), (self.iso_action, "Isometric"),
                              (self.edges_action, "Edges")):
            action.setIconText(label)
            bar.addAction(action)
        orientation = bar.widgetForAction(self.iso_action)
        views = QMenu(orientation)
        views.addActions([self.iso_action, *self.standard_view_actions])
        orientation.setMenu(views)
        orientation.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        bar.addSeparator()
        for action, label in ((self.fit_selected_action, "Fit selection"),
                              (self.hide_selected_action, "Hide"), (self.isolate_action, "Isolate"),
                              (self.show_all_action, "Show all")):
            action.setIconText(label)
            bar.addAction(action)
        bar.addSeparator()
        self.pick_mode = QComboBox()
        self.pick_mode.setObjectName("pickMode")
        self.pick_mode.setAccessibleName("Mesh selection type")
        self.pick_mode.addItems(["Elements", "Nodes"])
        self.pick_mode.currentIndexChanged.connect(self._pick_mode_changed)
        bar.addWidget(self.pick_mode)
        self.selection_type_menu = self._view_menu.addMenu("Selection type")
        self.selection_type_menu.setObjectName("selectionTypeMenu")
        self._selection_type_menu = _SelectionTypeMenu(self.pick_mode, self.selection_type_menu)
        return bar

    def _install_navigation(self):
        browser = QWidget()
        browser.setObjectName("modelBrowser")
        layout = QVBoxLayout(browser)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.model_filter = QLineEdit()
        self.model_filter.setObjectName("modelFilter")
        self.model_filter.setAccessibleName("Filter model objects")
        self.model_filter.setPlaceholderText("Filter model objects")
        self.model_filter.setClearButtonEnabled(True)
        self.model_filter.textChanged.connect(self._filter_model)
        self.model_tree = ModelTree()
        self.model_tree.setSelectionMode(ModelTree.SelectionMode.ExtendedSelection)
        self.model_tree.model().setHorizontalHeaderLabels(["Name", "Type", "Card"])
        self.model_tree.setColumnHidden(1, True)
        self.model_tree.setColumnHidden(2, False)
        self.model_tree.nodeSelected.connect(self._card_selected)
        self.model_tree.selectedRefsChanged.connect(self._objects_selected)
        self.model_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.model_tree.customContextMenuRequested.connect(self._model_context_menu)
        layout.addWidget(self.model_filter)
        layout.addWidget(self.model_tree, 1)
        self.model_dock = create_dock(self, "modelDock", "Model browser", browser,
                                     Qt.DockWidgetArea.LeftDockWidgetArea, self._view_menu)
        self.model_dock.setMinimumWidth(300)

    def _model_context_menu(self, position):
        index = self.model_tree.indexAt(position)
        if index.isValid():
            ref = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
            if ref is not None and ref not in self.model_tree.selected_refs():
                self.select_card(ref.object_id)
        self.modeling.refresh()
        menu = QMenu(self.model_tree)
        menu.addActions([self.hide_selected_action, self.isolate_action, self.show_all_action, self.fit_selected_action])
        menu.addSeparator()
        menu.addActions(list(self.modeling.actions.values()))
        menu.exec(self.model_tree.viewport().mapToGlobal(position))

    def _install_inspector(self):
        self.property_tabs = QTabWidget()
        self.property_tabs.setObjectName("inspectorTabs")
        properties = QWidget()
        properties.setObjectName("nativeProperties")
        layout = QVBoxLayout(properties)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.property_editor = PropertyEditor()
        self.property_title = self.property_editor.title
        self.property_subtitle = self.property_editor.subtitle
        self._form_host = self.property_editor
        self.apply_vector_button = QPushButton("Apply velocity")
        self.apply_vector_button.setObjectName("primaryAction")
        self.apply_vector_button.clicked.connect(self._apply_properties)
        self.curve_table = CurveTable(minimum_points=1, require_increasing_x=False)
        self.curve_table.pointsEdited.connect(self._commit_curve)
        self.curve_plot = CurvePlot()
        self.units_note = QLabel()
        self.units_note.setObjectName("unitsNote")
        self.units_note.setWordWrap(True)
        self.units_note.setContentsMargins(8, 5, 8, 5)
        self.units_note.setToolTip("Input deck unit context; no unit conversion is applied.")
        self.target_role_selector = QComboBox()
        self.target_role_selector.setObjectName("conditionTargetRole")
        self.target_role_selector.setAccessibleName("Displayed condition target")
        self.target_role_selector.setToolTip("Choose which referenced geometry is highlighted in the 3D view")
        self.target_role_selector.currentIndexChanged.connect(self._condition_target_selected)
        layout.addWidget(self.target_role_selector)
        layout.addWidget(self.property_editor, 1)
        layout.addWidget(self.apply_vector_button)
        layout.addWidget(self.curve_table)
        layout.addWidget(self.curve_plot, 1)
        layout.addWidget(self.units_note)
        form_scroll = QScrollArea()
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_scroll.setWidgetResizable(True)
        form_scroll.setWidget(properties)
        self.raw_source = QPlainTextEdit()
        self.raw_source.setAccessibleName("Selected card source")
        self.raw_source.setReadOnly(True)
        self.raw_source.setFont(QFont("Consolas", 10))
        self.raw_source.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.property_tabs.addTab(form_scroll, "Properties")
        self.property_tabs.addTab(self.raw_source, "Card source")
        self.inspector_stack = QStackedWidget()
        self.inspector_stack.addWidget(self.property_tabs)
        self.modeling.mount(self.inspector_stack)
        self.properties_dock = create_dock(self, "propertiesDock", "Inspector", self.inspector_stack,
                                          Qt.DockWidgetArea.LeftDockWidgetArea, self._view_menu)
        self.properties_dock.setMinimumWidth(300)
        self.properties_dock.setMinimumHeight(290)
        self._clear_form()

    def _install_notices(self):
        self.messages = QTreeWidget()
        self.messages.setObjectName("messages")
        self.messages.setAccessibleName("Document and operation messages")
        self.messages.setHeaderLabels(["Level", "Message"])
        self.messages.setRootIsDecorated(False)
        self.messages.setWordWrap(True)
        self.messages.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.messages.header().setStretchLastSection(True)
        self.messages_dock = create_dock(self, "messagesDock", "Messages", self.messages,
                                        Qt.DockWidgetArea.BottomDockWidgetArea, self._view_menu)

    def _install_status(self):
        self._counts = QLabel()
        self._counts.setContentsMargins(8, 0, 10, 0)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setMaximumWidth(160)
        self._progress.hide()
        self.statusBar().addPermanentWidget(self._progress)
        self.statusBar().addPermanentWidget(self._counts)

    def _present_document(self, summary):
        name = str(summary.get("name") or "Untitled")
        self.setWindowTitle(f"{name}{' *' if summary.get('dirty') else ''} — CAELab Prep")
        self.viewport_frame.title.setText(name if summary.get("document_id") else "Model")
        self.viewport_frame.title.setToolTip(name)
        self.viewport_frame.context.setText("" if summary.get("document_id") else "Open a deck or project")
        self.document_state.setText("Unsaved changes" if summary.get("dirty") else "Radioss" if summary.get("document_id") else "")
        self._counts.setText(f"{summary.get('node_count', 0):,} nodes  ·  {summary.get('element_count', 0):,} elements")
        self.messages.clear()
        for diagnostic in summary.get("diagnostics", ()):
            if isinstance(diagnostic, dict):
                level = str(diagnostic.get("severity", diagnostic.get("level", "Info"))).title()
                text = str(diagnostic.get("message", diagnostic))
            else:
                level, text = "Info", str(diagnostic)
            self._append_message(text, level)
            if level.casefold() in ("warning", "error"):
                self.messages_dock.show()

    def _present_command_priority(self, *, open_primary, save_primary):
        for action, primary in ((self.open_rad_action, open_primary), (self.save_action, save_primary)):
            action.setProperty("primaryCommand", primary)
            for button in self.document_toolbar.findChildren(QToolButton):
                if button.defaultAction() is action and button.property("primaryCommand") != primary:
                    button.setProperty("primaryCommand", primary)
                    button.style().unpolish(button)
                    button.style().polish(button)
                    button.update()

    def _size_initial_sidebar(self):
        if hasattr(self, "reference_adapter"):
            self.reference_adapter.resize(self.reference_bindings)
            return
        width = max(350, min(420, round(self.width() * .20)))
        self.resizeDocks([self.model_dock], [width], Qt.Orientation.Horizontal)

    def _refresh_tree(self):
        nodes = self.provider.tree_nodes()
        if nodes == self._tree_nodes:
            return
        self._tree_nodes = nodes
        self._card_refs = {node.ref.object_id: node.ref for node in nodes}
        order = {name: index for index, name in enumerate(("Parts", "Materials", "Properties", "Groups",
                 "Constraints", "Contacts", "Loads", "Initial conditions", "Curves", "Nodes", "Elements", "Other cards"))}
        self.model_tree.blockSignals(True)
        try:
            self.model_tree.set_nodes(sorted(nodes, key=lambda node: order.get(node.group, len(order))))
            self.model_tree.setColumnHidden(1, True)
            self.model_tree.setColumnHidden(2, False)
            self.model_tree.model().setHeaderData(2, Qt.Orientation.Horizontal, "Card")
            if self._selected_card_id not in self._card_refs:
                self._selected_card_id = None
            self._restore_approved_selection()
            self._filter_model(self.model_filter.text())
        finally:
            self.model_tree.blockSignals(False)

    def _filter_model(self, text):
        query = text.strip().casefold()
        model = self.model_tree.model()
        for row in range(model.rowCount()):
            parent = model.index(row, 0)
            group_match = query in str(parent.data() or "").casefold()
            visible_count = 0
            for child in range(model.rowCount(parent)):
                text = " ".join(str(model.index(child, column, parent).data() or "")
                                for column in range(model.columnCount(parent))).casefold()
                visible = not query or group_match or query in text
                self.model_tree.setRowHidden(child, parent, not visible)
                visible_count += visible
            self.model_tree.setRowHidden(row, parent.parent(), not visible_count)
            if query and visible_count:
                self.model_tree.expand(parent)

    def _clear_form(self):
        self._curve_active = False
        self.target_role_selector.hide()
        self.property_editor.set_fields(())
        self.property_editor.setMinimumHeight(0)
        self.property_editor.scroll.show()
        self.property_editor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        for widget in (self.apply_vector_button, self.curve_table, self.curve_plot):
            widget.hide()
        self.units_note.clear()
        self.field_editors, self._field_specs = {}, {}
        self._native_property_baseline = {}
        bindings = getattr(self, "reference_bindings", None)
        if bindings is not None and bindings.curve_pages is not None:
            bindings.curve_pages.hide()

    def _refresh_fields(self):
        previous_units = self.property_editor.units()
        target_key = (self._summary().get("document_epoch"), self._selected_card_id)
        retain_units = getattr(self, "_property_target_key", None) == target_key
        self._clear_form()
        cards = {card["id"]: card for card in self.session.list_cards()} if self._selected_card_id else {}
        card = cards.get(self._selected_card_id)
        if card is None:
            self._selected_card_id = None
            self.property_title.setText("No object selected")
            self.property_subtitle.clear()
            self.raw_source.clear()
            self.modeling.refresh()
            return
        ref = self._card_refs[self._selected_card_id]
        specs = self.provider.properties(ref)
        fields = self.session.card_fields(self._selected_card_id)
        self._editor_revision = self._summary().get("revision")
        self._field_specs = {field["name"]: field for field in fields}
        self._field_specs.update({spec.name: {"name": spec.name, "label": spec.label,
                                            "value": spec.value, "type": spec.kind} for spec in specs})
        self.property_editor.set_fields(tuple(spec for spec in specs if spec.kind != "table"),
                                        title=str(card.get("title") or "Properties"),
                                        subtitle=str(card.get("keyword") or ""))
        if retain_units:
            for name, unit in previous_units.items():
                selector = self.property_editor.unit_selectors.get(name)
                if selector is not None and selector.findText(unit) >= 0:
                    selector.setCurrentText(unit)
        self._property_target_key = target_key
        self.field_editors = dict(self.property_editor.editors)
        self._native_property_baseline = self.property_editor.raw_values()
        self._native_unit_baseline = self.property_editor.units()
        self._connect_property_inputs()
        self._refresh_target_roles()
        source = self.session.card_text(self._selected_card_id)
        if len(source) > 100_000:
            source = source[:100_000] + "\n… Card preview truncated; the full card is preserved in the document."
        self.raw_source.setPlainText(source)
        units = self.provider.unit_context(ref)
        self.units_note.setText(self._unit_caption(units))
        table = next((spec for spec in specs if spec.kind == "table"), None)
        if table:
            self._present_curve(table)
        if not specs or not any(spec.editable for spec in specs):
            self.property_subtitle.setText(str(card.get("keyword") or "") + "  /  Read-only")
            if specs:
                self.units_note.clear()
        self.modeling.refresh()

    def _connect_property_inputs(self):
        deferred = self._deferred_property_drafts()
        for name, editor in self.property_editor.editors.items():
            if not editor.isEnabled():
                continue
            if isinstance(editor, VectorEdit):
                self.property_editor.setMinimumHeight(190)
                for component, child in zip(("vx", "vy", "vz"), editor.editors):
                    self.field_editors[component] = child
                    child.setObjectName("field_" + component)
                    if not deferred:
                        child.returnPressed.connect(lambda n=component, e=child: self._commit_text(n, e))
                self.apply_vector_button.setToolTip("Apply all three velocity components together (Enter)")
                self.apply_vector_button.setText("Apply velocity")
                self.apply_vector_button.setVisible(not deferred)
            elif isinstance(editor, QCheckBox):
                if not deferred:
                    editor.toggled.connect(lambda checked, n=name: self._commit_field(n, checked))
            elif isinstance(editor, QComboBox):
                if self.property_editor.specs[name].kind == "choice":
                    editor.currentIndexChanged.connect(lambda index, n=name, e=editor: self._property_choice_changed(n, e))
                elif not deferred:
                    editor.activated.connect(lambda index, n=name, e=editor: self._commit_field(n, e.itemData(index)))
            elif isinstance(editor, QLineEdit):
                editor.setObjectName("field_" + name)
                if not deferred:
                    editor.editingFinished.connect(lambda n=name, e=editor: self._commit_text(n, e))
        if deferred and not getattr(getattr(self, "reference_adapter", None), "defer_scalars", False):
            self.apply_vector_button.setText("Apply properties")
            self.apply_vector_button.setToolTip("Apply the complete property draft as one transaction")
            self.apply_vector_button.show()

    def _present_curve(self, spec):
        points = spec.value
        self._curve_active = True
        self.property_editor.scroll.hide()
        self.property_editor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.curve_table.minimum_points = spec.minimum_rows
        self.curve_table.maximum_points = spec.maximum_rows
        self.curve_table.set_points(points, headers=spec.components or ("X", "Y"))
        grid = self.curve_table.table
        grid.setFixedHeight(grid.horizontalHeader().sizeHint().height()
                            + min(8, len(points)) * grid.verticalHeader().defaultSectionSize()
                            + 2 * grid.frameWidth())
        self.curve_plot.set_points(points, x_label="X (input deck)", y_label="Y (input deck)")
        self.curve_table.show()
        self.curve_plot.show()
        bindings = getattr(self, "reference_bindings", None)
        if bindings is not None and bindings.curve_pages is not None:
            bindings.curve_pages.show()

    @staticmethod
    def _unit_caption(units):
        if units.get("unit_id") is not None:
            return f"Material unit system: {units['unit_id']}"
        if units.get("global"):
            return "Units: " + ", ".join(f"{key}: {value}" for key, value in units["global"].items())
        return "Units: input deck"
