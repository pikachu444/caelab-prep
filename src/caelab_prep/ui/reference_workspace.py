"""Concrete host assembly over the independent reference presentation seam."""
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar

from .design import icon
from .materials_workspace import MaterialsWorkspace
from .reference_components import ADAPTERS, ReferenceBindings
from .native_commands import command_groups


def _edit_action(window):
    action = QAction(icon("card"), "Edit properties…", window)
    action.setIconText("Edit")
    return action


class ReferenceMaterialsWorkspace(MaterialsWorkspace):
    def build(self):
        super().build()
        h = self.host
        h.edit_properties_action = _edit_action(h)
        h.reference_adapter = ADAPTERS[h.presentation]
        h.reference_bindings = ReferenceBindings(
            h, h.tree, h.model_dock, h.properties_dock, h.messages_dock,
            h.properties, h.document_toolbar,
            {"Document": (h.open_action, h.save_action), "History": (h.undo_action, h.redo_action),
             "Material": (h.edit_properties_action,)}, h._finish_drafts, h.reload_values,
            h.curve_table, h.plot, h.plot.parentWidget(), curve_surface=h.plot.parentWidget(),
            inspector_buttons=(h.apply_button, h.revert_button), edit_action=h.edit_properties_action)
        h.reference_adapter.install(h.reference_bindings)
        h.property_dialog = h.reference_bindings.dialog


def configure_native(h, key, *, native_commands=False):
    """Recompose RAD handles without importing its controller or solver."""
    if not hasattr(h, "edit_properties_action"):
        h.edit_properties_action = _edit_action(h)
    h.reference_adapter = ADAPTERS[key]
    h.reference_bindings = ReferenceBindings(
        h, h.model_tree, h.model_dock, h.properties_dock, h.messages_dock,
        h.property_editor, h.document_toolbar,
        command_groups(h),
        h._finish_pending_edits, h._discard_pending_edits,
        h.curve_table, h.curve_plot, h.curve_plot.parentWidget(), property_tabs=h.property_tabs,
        selection_tools=h.viewport_frame.findChild(QToolBar, "modelViewCommands"), viewport=h.viewport_frame,
        edit_action=h.edit_properties_action)
    h.reference_adapter.install(h.reference_bindings, commands=not native_commands)
    h.property_dialog = h.reference_bindings.dialog
    _register_edge_split_action(h)


class _EdgeSplitCloseFilter(QObject):
    def __init__(self, host):
        super().__init__(host)
        self.host = host

    def eventFilter(self, watched, event):
        if watched is self.host and event.type() == QEvent.Type.Close:
            dialog = getattr(self.host, "edge_split_dialog", None)
            if dialog is not None:
                dialog.reject()
        return False


def _register_edge_split_action(h):
    if getattr(h, "edge_split_action", None) is not None:
        return
    h.edge_split_dialog = None
    action = QAction("Split triangle edge…", h)
    action.setObjectName("mesh.split_triangle_edge")

    def open_edge_split():
        from .element_edits import TriangleEdgeSplitDialog
        return h._open_model_relation_dialog("edge_split_dialog", TriangleEdgeSplitDialog, "changed")

    h.open_edge_split = open_edge_split
    h.edge_split_action = action
    action.triggered.connect(h.open_edge_split)
    if hasattr(h, "shell_normal_action"):
        action.setEnabled(h.shell_normal_action.isEnabled())
        h.shell_normal_action.changed.connect(lambda: action.setEnabled(h.shell_normal_action.isEnabled()))
    else:
        action.setEnabled(False)
    mesh_menu = getattr(h, "command_menus", {}).get("Mesh")
    if mesh_menu is not None:
        anchor = getattr(h, "part_reassignment_action", None)
        if anchor is not None and anchor in mesh_menu.actions():
            mesh_menu.insertAction(anchor, action)
        else:
            mesh_menu.addAction(action)
    if isinstance(h, QObject):
        h._edge_split_close_filter = _EdgeSplitCloseFilter(h)
        h.installEventFilter(h._edge_split_close_filter)
