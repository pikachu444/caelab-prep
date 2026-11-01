"""Native material and curve presentation; the host owns document commands."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                              QSplitter, QToolBar, QVBoxLayout, QWidget)

from .catalogue import CatalogueWidget
from .shell import ViewportFrame, create_dock
from .widgets import CurvePlot, CurveTable, ModelTree, PropertyEditor


class MaterialsWorkspace:
    def __init__(self, host):
        self.host = host

    def build(self):
        host = self.host
        self._commands()
        self._objects()
        self._inspector()
        self._curve()
        self._diagnostics()
        self._developer_tools()
        host.splitDockWidget(host.model_dock, host.properties_dock, Qt.Orientation.Vertical)
        host.resizeDocks([host.model_dock], [350], Qt.Orientation.Horizontal)
        host.resizeDocks([host.model_dock, host.properties_dock], [260, 460], Qt.Orientation.Vertical)
        host.status = QLabel()
        host.status.setAccessibleName("Document status")
        host.statusBar().addWidget(host.status, 1)

    def _commands(self):
        host = self.host
        file = host.menuBar().addMenu("&File")
        file.addActions([host.open_action, host.save_action, host.save_as_action])
        file.addSeparator()
        file.addAction(host.close_action)
        edit = host.menuBar().addMenu("&Edit")
        edit.addActions([host.undo_action, host.redo_action])
        edit.addSeparator()
        edit.addActions([host.apply_action, host.reload_action])
        host.view_menu = host.menuBar().addMenu("&View")
        host.menuBar().addMenu("&Developer").addAction(host.catalogue_action)

        strip = QToolBar("Document", host)
        host.document_toolbar = strip
        strip.setObjectName("galleryDocumentToolbar")
        strip.setMovable(False)
        strip.setIconSize(QSize(18, 18))
        strip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action, label in ((host.open_action, "Open"), (host.save_action, "Save")):
            action.setIconText(label)
            strip.addAction(action)
        strip.addSeparator()
        strip.addActions([host.undo_action, host.redo_action])
        host.addToolBar(strip)

    def _objects(self):
        host = self.host
        host.tree = ModelTree()
        host.tree.nodeSelected.connect(host._select_target)
        host.model_dock = self._dock("galleryObjects", "Materials and curves", host.tree,
                                    Qt.DockWidgetArea.LeftDockWidgetArea)

    def _inspector(self):
        host = self.host
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        host.properties = host.property_editor = PropertyEditor()
        column.addWidget(host.properties, 1)

        footer = QFrame()
        footer.setObjectName("inspectorCommands")
        commands = QHBoxLayout(footer)
        commands.setContentsMargins(8, 5, 8, 5)
        commands.setSpacing(6)
        commands.addStretch()
        host.revert_button = QPushButton("Revert")
        host.apply_button = QPushButton("Apply")
        host.apply_button.setObjectName("primaryAction")
        for button, action in ((host.revert_button, host.reload_action), (host.apply_button, host.apply_action)):
            button.setAccessibleName(action.text())
            button.setToolTip(action.text())
            button.clicked.connect(action.trigger)
            action.changed.connect(lambda b=button, a=action: b.setEnabled(a.isEnabled()))
            commands.addWidget(button)
        column.addWidget(footer)
        host.properties_dock = self._dock("galleryProperties", "Inspector", panel,
                                         Qt.DockWidgetArea.LeftDockWidgetArea)

    def _curve(self):
        host = self.host
        host.plot = CurvePlot()
        host.curve_table = CurveTable()
        host.curve_table.pointsEdited.connect(host._commit_curve)
        surface = QSplitter(Qt.Orientation.Vertical)
        surface.setObjectName("curveWorkspace")
        surface.setChildrenCollapsible(False)
        surface.setHandleWidth(4)
        surface.addWidget(host.plot)
        surface.addWidget(host.curve_table)
        surface.setStretchFactor(0, 3)
        surface.setStretchFactor(1, 2)
        surface.setSizes([440, 260])
        host.viewport_frame = ViewportFrame(surface, "Curve")
        host.setCentralWidget(host.viewport_frame)

    def _diagnostics(self):
        host = self.host
        host.messages = QPlainTextEdit()
        host.messages.setReadOnly(True)
        host.messages.setMaximumBlockCount(200)
        host.messages.setAccessibleName("Operation messages")
        host.messages_dock = self._dock("galleryMessages", "Messages", host.messages,
                                       Qt.DockWidgetArea.BottomDockWidgetArea)
        host.messages_dock.hide()

    def _developer_tools(self):
        host = self.host
        host.catalogue = CatalogueWidget()
        host.assets_dock = self._dock("galleryAssets", "Component catalogue", host.catalogue,
                                     Qt.DockWidgetArea.RightDockWidgetArea)
        host.assets_dock.hide()

    def _dock(self, name, title, widget, area):
        return create_dock(self.host, name, title, widget, area, self.host.view_menu)
