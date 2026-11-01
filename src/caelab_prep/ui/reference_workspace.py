"""Concrete host assembly over the independent reference presentation seam."""
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar

from .design import icon
from .materials_workspace import MaterialsWorkspace
from .reference_components import ADAPTERS, ReferenceBindings


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
            inspector_buttons=(h.apply_button, h.revert_button))
        h.reference_adapter.install(h.reference_bindings)
        h.property_dialog = h.reference_bindings.dialog


def configure_native(h, key):
    """Recompose RAD handles without importing its controller or solver."""
    h.edit_properties_action = _edit_action(h)
    h.reference_adapter = ADAPTERS[key]
    h.reference_bindings = ReferenceBindings(
        h, h.model_tree, h.model_dock, h.properties_dock, h.messages_dock,
        h.property_editor, h.document_toolbar,
        {"Document": (h.open_rad_action, h.open_project_action, h.save_action, h.export_action),
         "History": (h.undo_action, h.redo_action), "Material": (h.edit_properties_action,)},
        h._finish_pending_edits, h._discard_pending_edits,
        h.curve_table, h.curve_plot, h.curve_plot.parentWidget(), property_tabs=h.property_tabs,
        selection_tools=h.viewport_frame.findChild(QToolBar, "modelViewCommands"), viewport=h.viewport_frame)
    h.reference_adapter.install(h.reference_bindings)
    h.property_dialog = h.reference_bindings.dialog
