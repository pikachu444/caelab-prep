"""Preserved Prep session/edit adapter, independent of workspace construction.

Selection, draft, transaction and file lifecycle behavior is extracted from the
former main_window.MainWindow. Widgets remain the input/output boundary; the
provider and session continue to own model semantics and persistence.

Provenance: main_window.py at 40d8d913, state/commands lines 52–84 and 122–144;
session/selection lines 315–496; edit/draft/file lifecycle lines 581–992.
Those behaviors are retained, with dialog/task dependencies injected and document
presentation delegated to PrepWorkspace. They are not newly authored model logic.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QCloseEvent, QKeySequence
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QTreeWidgetItem

from .actions import ActionRegistry
from .shell import FileEditCoordinator
from .widgets._editing import editor_value, restore_editor_raw_value
from ..application.contracts import ActionSpec, SetProperties
from ..application.rad_provider import RadProvider


def _field_label(field):
    """Presentation labels; values and their unit context remain solver-owned."""
    name = field["name"]
    labels = {
        "density": "Density", "young_modulus": "Young's modulus",
        "poisson_ratio": "Poisson's ratio", "friction": "Friction coefficient",
        "thickness": "Shell thickness", "vx": "Initial velocity X",
        "vy": "Initial velocity Y", "vz": "Initial velocity Z",
        "tx": "Translation X", "ty": "Translation Y", "tz": "Translation Z",
        "rx": "Rotation X", "ry": "Rotation Y", "rz": "Rotation Z",
    }
    if name in labels:
        return labels[name]
    parts = name.split("_")
    if len(parts) == 3 and parts[0] == "point" and parts[1].isdigit() and parts[2] in ("x", "y"):
        return f"Point {int(parts[1]) + 1} · {parts[2].upper()}"
    return str(field.get("label") or name.replace("_", " ").capitalize())


class PrepController:
    """Behavior adapter mixed into the native host; creates no workspace widgets."""

    def initialize_controller(self, session, *, file_dialog, message_box, task_factory):
        self._file_dialog = file_dialog
        self._message_box = message_box
        self._task_factory = task_factory
        self.session = session
        self.provider = RadProvider(session)
        self._tree_nodes = ()
        self._card_refs = {}
        self._busy = False
        self._active_task = None
        self.operation_state = None
        self._project_path = None
        self._source_path = None
        self._selected_card_id = None
        self._editor_revision = None
        self._card_text_draft = None
        self._replacement_conflict = False
        self._pending_selection = False
        self._updating = False
        self._allow_close = False
        self._closed = False
        self._last_presented_document = None
        self._last_presented_epoch = None
        self._last_presented_revision = -1
        self.field_editors = {}
        self._field_specs = {}
        self.actions = ActionRegistry(self)
        self.file_edits = FileEditCoordinator(
            self, has_draft=lambda: bool(self._text_drafts()) or self._replacement_conflict or self.modeling.active,
            finish=self._finish_pending_edits, discard=self._discard_pending_edits,
            is_dirty=lambda: bool(self._summary().get("dirty")),
            save=lambda continuation: self.save_project_dialog(on_saved=continuation),
            capture=self._capture_pending_edits, restore=self._restore_pending_edits)

    def _action(self, key, label, callback, shortcut="", *, checkable=False, action_id=None, capability="", contexts=()):
        return self.actions.register(ActionSpec(action_id or key, label, shortcut=shortcut,
                                     capability=capability, icon=key, contexts=contexts,
                                     checkable=checkable), callback)

    def _register_commands(self):
        self.open_rad_action = self._action("open", "Open Radioss deck…", self.open_rad_dialog, QKeySequence.StandardKey.Open, action_id="file.open")
        self.open_project_action = self._action("project", "Open project…", self.open_project_dialog, "Ctrl+Shift+O", action_id="file.open_project")
        self.save_action = self._action("save", "Save project", self.save_project_dialog, QKeySequence.StandardKey.Save, action_id="file.save", capability="save")
        self.save_as_action = self._action("save", "Save project as…", lambda: self.save_project_dialog(force_new=True), QKeySequence.StandardKey.SaveAs, action_id="file.save_as", capability="save")
        self.export_action = self._action("export", "Export Radioss deck…", self.export_rad_dialog, "Ctrl+E", action_id="file.export", capability="radioss_raw_preservation")
        self.undo_action = self._action("undo", "Undo", lambda: self._history("undo"), QKeySequence.StandardKey.Undo, action_id="edit.undo", capability="undo")
        self.redo_action = self._action("redo", "Redo", lambda: self._history("redo"), QKeySequence.StandardKey.Redo, action_id="edit.redo", capability="undo")
        self.reload_properties_action = self._action("card", "Reload properties", self._reload_properties, "Ctrl+R", action_id="edit.reload")
        self.fit_action = self._action("fit", "Fit model", self._fit, "F", action_id="view.fit", contexts=("mesh",))
        self.iso_action = self._action("iso", "Isometric view", self._isometric, "0", action_id="view.isometric", contexts=("mesh",))
        self.standard_view_actions = [
            self._action("iso", f"{axis.title()} view", lambda checked=False, a=axis: self._standard_view(a),
                         action_id=f"view.{axis}", contexts=("mesh",))
            for axis in ("front", "top", "right")]
        self.edges_action = self._action("edges", "Show mesh edges", self._toggle_edges, checkable=True, action_id="view.edges", contexts=("mesh",))
        self.edges_action.setChecked(True)
        self.close_action = self._action("card", "Exit", self.close, QKeySequence.StandardKey.Quit, action_id="file.close")
        from .modeling import ModelingActions, display_state
        self.modeling = ModelingActions(self)
        self._display_state = display_state(self.session)
        self._display_state.changed.connect(self._apply_display_state)
        self.hide_selected_action = self._action("part", "Hide selected", self._hide_selected,
                                                action_id="view.hide_selected", contexts=("mesh",))
        self.isolate_action = self._action("part", "Isolate selected", self._isolate_selected,
                                          action_id="view.isolate", contexts=("mesh",))
        self.show_all_action = self._action("part", "Show all parts", self._show_all_parts,
                                           action_id="view.show_all", contexts=("mesh",))
        self.fit_selected_action = self._action("fit", "Fit selected", self._fit_selected,
                                               action_id="view.fit_selected", contexts=("mesh",))
        from .mesh_workflow import MeshWorkflow
        self.mesh_workflow = MeshWorkflow(self)
        from .mesh_import import MeshImportWorkflow
        self.mesh_import = MeshImportWorkflow(self)
        self.source_models_dialog = None
        self.prepared_mesh_dialog = None
        self.node_move_dialog = None
        self.node_merge_dialog = None
        self.shell_normal_dialog = None
        self.element_deletion_dialog = None
        self.source_models_action = self._action(
            "project", "Source models / import RAD…", self.open_source_models,
            action_id="model.sources")
        self.prepared_mesh_action = self._action(
            "mesh", "Replace prepared mesh / reconnect targets…", self.open_prepared_mesh,
            action_id="mesh.replace_prepared")
        self.node_move_action = self._action("mesh", "Move nodes to coordinates…", self.open_node_move,
                                             action_id="mesh.move_nodes")
        self.node_merge_action = self._action("mesh", "Merge nodes with tolerance…", self.open_node_merge,
                                              action_id="mesh.merge_nodes")
        self.shell_normal_action = self._action("mesh", "Reverse shell normals…", self.open_shell_normals,
                                                action_id="mesh.flip_shell_normals")
        self.element_deletion_action = self._action("mesh", "Delete elements…", self.open_element_deletion,
                                                   action_id="mesh.delete_elements")

    def open_element_deletion(self):
        from .element_edits import ElementDeletionDialog
        return self._open_model_relation_dialog("element_deletion_dialog", ElementDeletionDialog, "changed")

    def open_shell_normals(self):
        from .element_edits import ShellNormalDialog
        return self._open_model_relation_dialog("shell_normal_dialog", ShellNormalDialog, "changed")

    def open_node_merge(self):
        from .node_merges import NodeMergeDialog
        if self.modeling.active:
            self.statusBar().showMessage("Finish the current model operation before merging nodes.", 8000)
            return None
        return self._open_model_relation_dialog("node_merge_dialog", NodeMergeDialog, "changed")

    def open_node_move(self):
        from .node_moves import NodeMoveDialog
        return self._open_model_relation_dialog("node_move_dialog", NodeMoveDialog, "changed")

    def open_source_models(self):
        from .source_models import SourceModelsDialog
        return self._open_model_relation_dialog("source_models_dialog", SourceModelsDialog, "imported")

    def open_prepared_mesh(self):
        from .source_models import PreparedMeshDialog
        return self._open_model_relation_dialog("prepared_mesh_dialog", PreparedMeshDialog, "changed")

    def _open_model_relation_dialog(self, attribute, dialog_type, signal):
        """Review relationships beside the model without committing its drafts."""
        if self._closed or self._busy:
            self.statusBar().showMessage("Wait for the current model operation to finish.", 8000)
            return None
        if not self._summary().get("document_id"):
            self.statusBar().showMessage("Create or open a model before reviewing its relationships.", 8000)
            return None
        if self.file_edits.has_draft():
            self.statusBar().showMessage(
                "Apply, cancel or reload the unfinished model input before reviewing relationships.", 8000)
            return None
        dialog = getattr(self, attribute)
        if dialog is None:
            dialog = dialog_type(self.session, self, has_draft=lambda: self.file_edits.has_draft() or self.modeling.active,
                                 is_busy=lambda: self._closed or self._busy or self._replacement_conflict)
            setattr(self, attribute, dialog)
            getattr(dialog, signal).connect(lambda _result: self.refresh_document(rebuild_viewport=True))
            dialog.finished.connect(lambda _result, d=dialog: self._release_model_relation_dialog(attribute, d))
            dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _release_model_relation_dialog(self, attribute, dialog):
        if getattr(self, attribute) is dialog:
            setattr(self, attribute, None)
        # The dialog owns cancellation and its session subscription. A closed
        # source table must not retain its rows until the main window closes.
        dialog.deleteLater()

    def _summary(self):
        return self.session.describe()

    def _session_changed(self, event):
        """Session observers run on any caller thread; this slot is queued to Qt."""
        if self._closed or self._busy:
            return
        kind = event.get("kind")
        same_document = (event.get("document_id") == self._last_presented_document
                         and event.get("document_epoch") == self._last_presented_epoch)
        if kind == "selection":
            if self.viewport:
                self.viewport.set_selection(self.session.selection())
            active = self.provider.active_object()
            target_id = active.object_id if active else None
            if target_id != self._selected_card_id:
                if self._text_drafts():
                    self._pending_selection = True
                    self.statusBar().showMessage("Selection changed. Finish or reload the current property draft before showing the selected object.")
                    return
                self._selected_card_id = target_id
                self._refresh_fields()
            self._restore_approved_selection()
            self._refresh_target_roles()
            self._refresh_actions()
            return
        if kind == "field" and same_document and event.get("revision", -1) <= self._last_presented_revision:
            return
        drafts = self._text_drafts()
        if self._replacement_conflict or (not same_document and drafts):
            self._replacement_conflict = True
            message = "The document was replaced while input was unfinished. Your draft remains visible. Reload properties (Ctrl+R) to discard it and show the current document."
            self.property_subtitle.setText("Draft from the previous document — reload required")
            self._append_message(message)
            self.statusBar().showMessage(message)
            self._refresh_actions()
            return
        draft_revision = self._editor_revision
        self.refresh_document(rebuild_viewport=kind in ("document", "structure"))
        self._restore_text_drafts(drafts)
        if drafts:
            self._editor_revision = draft_revision
            self._append_message("The model changed while a property edit was unfinished. Reload properties (Ctrl+R) to discard the draft and read current values.")

    def refresh_document(self, *, rebuild_viewport=False):
        """Refresh from the canonical session, also usable by an IPC coordinator."""
        if self._busy or self._replacement_conflict:
            return
        summary = self._summary()
        self._display_state.reset(summary.get("document_epoch"))
        self._project_path = Path(summary["project_path"]) if summary.get("project_path") else None
        self._source_path = Path(summary["source_path"]) if summary.get("source_path") else None
        self._updating = True
        try:
            self._present_document(summary)
            self._refresh_tree()
            self._restore_approved_selection()
            self._refresh_fields()
            self._refresh_actions(summary)
            if rebuild_viewport and self.viewport is not None and summary.get("document_id"):
                try:
                    self.viewport.set_mesh(self.session.mesh_view(), reset_camera=
                                           summary.get("document_epoch") != self._last_presented_epoch)
                    self._apply_display_state()
                except Exception as exc:
                    self._viewport_diagnostic(f"Mesh display failed: {exc}")
            if self.viewport is not None and summary.get("document_id"):
                self.viewport.set_selection(self.session.selection())
            self._refresh_tree_appearances()
            self._last_presented_document = summary.get("document_id")
            self._last_presented_epoch = summary.get("document_epoch")
            self._last_presented_revision = summary.get("revision", 0)
            self.statusBar().clearMessage()
        finally:
            self._updating = False

    def _refresh_actions(self, summary=None):
        summary = summary or self._summary()
        loaded = bool(summary.get("document_id"))
        editable = not self._busy and not self._replacement_conflict
        self.actions.refresh(summary, busy=self._busy,
                             context="mesh" if loaded and self.viewport is not None else "",
                             enabled={"file.save": loaded and editable, "file.save_as": loaded and editable,
                                      "file.export": loaded and editable, "edit.undo": editable,
                                      "edit.redo": editable, "edit.reload": loaded})
        form_enabled = loaded and not self._busy and self._card_text_draft is None
        self._form_host.setEnabled(form_enabled)
        self.apply_vector_button.setEnabled(form_enabled)
        self.curve_table.setEnabled(form_enabled)
        self.curve_plot.setEnabled(form_enabled)
        self.model_tree.setEnabled(loaded and not self._busy)
        self.model_filter.setEnabled(loaded and not self._busy)
        if self.viewport:
            self.viewport.setEnabled(loaded and editable)
        self.pick_mode.setEnabled(loaded and self.viewport is not None and editable)
        for action in [self.fit_action, self.iso_action, self.edges_action, *self.standard_view_actions]:
            action.setEnabled(action.isEnabled() and editable)
        self._present_command_priority(open_primary=not loaded and not self._busy,
                                       save_primary=loaded and editable and bool(summary.get("dirty")))
        self.modeling.refresh()
        self.mesh_workflow.mesh_action.setEnabled(loaded and editable)
        self.mesh_workflow.export_action.setEnabled(loaded and editable)
        self.mesh_workflow.cases_action.setEnabled(loaded and editable)
        self.mesh_import.action.setEnabled(loaded and editable)
        self.source_models_action.setEnabled(loaded and editable)
        self.prepared_mesh_action.setEnabled(loaded and editable)
        self.node_move_action.setEnabled(loaded and editable)
        self.node_merge_action.setEnabled(loaded and editable)
        self.shell_normal_action.setEnabled(loaded and editable)
        self.element_deletion_action.setEnabled(loaded and editable)
        selected_parts = self._selected_part_refs() if loaded else ()
        self.hide_selected_action.setEnabled(bool(selected_parts) and loaded and editable and self.viewport is not None)
        self.isolate_action.setEnabled(self.hide_selected_action.isEnabled())
        self.show_all_action.setEnabled(bool(self._display_state.hidden) and loaded and editable and self.viewport is not None)
        self.fit_selected_action.setEnabled(bool(loaded and editable and self.viewport is not None and
                                                 self.session.selection().get("ids")))

    def _card_selected(self, ref):
        if self._updating or self._busy or not self._summary().get("document_id"):
            return
        target_id = ref.object_id if ref else None
        if not self._finish_pending_edits():
            self._restore_approved_selection()
            return
        try:
            parts = self._selected_part_refs()
            if ref in parts and len(parts) > 1:
                self.provider.select_many(parts, active=ref)
            else:
                self._activate_card(ref)
        except Exception as exc:
            self._restore_approved_selection()
            self._show_error(exc)
            return
        self._selected_card_id = target_id
        self._refresh_fields()

    def _objects_selected(self, refs):
        if self._updating or self._busy or not self._summary().get("document_id"):
            return
        if self.modeling.active or self._text_drafts():
            if not self._finish_pending_edits():
                self._restore_approved_selection()
                return
        parts = self._selected_part_refs()
        active = self.model_tree.selected_ref()
        if not refs:
            self.provider.select(None)
            self._selected_card_id = None
            self._refresh_fields()
        elif parts and len(parts) == len(refs):
            try:
                self.provider.select_many(parts, active=active if active in parts else parts[-1])
                if self.viewport:
                    self.viewport.set_selection(self.session.selection())
                self.selectionChanged.emit(self.session.selection())
                if len(parts) > 1:
                    self.statusBar().showMessage(f"{len(parts)} parts selected; properties show the active part")
            except Exception as exc:
                self._show_error(exc)
        elif len(refs) > 1:
            ref = active if active in refs else refs[-1]
            self._activate_card(ref)
            self._focus_tree_card(ref.object_id)
            self._selected_card_id = ref.object_id
            self._refresh_fields()
            self.statusBar().showMessage("Multiple selection is available for parts", 5000)
        self._refresh_actions()

    def _selected_part_refs(self):
        if not hasattr(self, "model_tree"):
            return ()
        part_ids = {node.ref.object_id for node in self._tree_nodes if node.group == "Parts"}
        return tuple(ref for ref in self.model_tree.selected_refs() if ref.object_id in part_ids)

    def _refresh_target_roles(self):
        if not hasattr(self, "target_role_selector"):
            return
        ref = self._card_refs.get(self._selected_card_id)
        try:
            roles = self.provider.target_roles(ref) if ref is not None else ()
        except Exception as exc:
            roles = ()
            self.target_role_selector.setToolTip(str(getattr(exc, "message", exc)))
        selector = self.target_role_selector
        blocked = selector.blockSignals(True)
        selector.clear()
        for key, label in roles:
            selector.addItem("Display: " + label, key)
        active = self.session.selection().get("active_target_role") if roles else None
        if active is not None:
            selector.setCurrentIndex(selector.findData(active))
        selector.setVisible(bool(roles))
        selector.setEnabled(self.viewport is not None and not self._busy)
        selector.blockSignals(blocked)

    def _condition_target_selected(self, index):
        if self._updating or index < 0 or self._busy or not self._finish_pending_edits():
            self._refresh_target_roles()
            return
        target = self._card_refs.get(self._selected_card_id)
        if target is not None:
            try:
                self.provider.select_target(target, self.target_role_selector.itemData(index))
                if self.viewport is not None:
                    self.viewport.set_selection(self.session.selection())
                self.selectionChanged.emit(self.session.selection())
            except Exception as exc:
                self._show_error(exc)
            self._refresh_target_roles()

    def _apply_display_state(self):
        if self._closed or self.viewport is None or not self._summary().get("document_id"):
            return
        self.viewport.show_all_parts()
        if self._display_state.hidden:
            self.viewport.hide_parts(tuple(self._display_state.hidden))
        self._refresh_tree_appearances()
        self._refresh_actions()

    def _refresh_tree_appearances(self):
        from .widgets.tree import TreeAppearance
        from .viewport import part_key
        color_query = getattr(self.viewport, "part_colors", None)
        colors = color_query() if color_query is not None else {}
        appearances = {}
        for node in self._tree_nodes:
            if node.group != "Parts":
                continue
            key = part_key(node.ref)
            if key in colors:
                hidden = (node.ref.resource_id, node.ref.native_scope) in self._display_state.hidden
                appearances[node.ref] = TreeAppearance(visible=not hidden, color=colors[key])
        self.model_tree.update_appearances(appearances)

    def _tree_visibility_requested(self, ref, visible):
        if self._busy or self.viewport is None or ref not in self._card_refs.values():
            return
        if not any(node.ref == ref and node.group == "Parts" for node in self._tree_nodes):
            return
        key = (ref.resource_id, ref.native_scope)
        hidden = set(self._display_state.hidden)
        if visible:
            hidden.discard(key)
        else:
            hidden.add(key)
        self._display_state.set_hidden(hidden)

    def _hide_selected(self):
        if self.viewport is not None and self._finish_pending_edits():
            keys = {(ref.resource_id, ref.native_scope) for ref in self._selected_part_refs()}
            self._display_state.set_hidden(self._display_state.hidden | keys)

    def _isolate_selected(self):
        if self.viewport is not None and self._finish_pending_edits():
            selected = {(ref.resource_id, ref.native_scope) for ref in self._selected_part_refs()}
            if selected:
                all_parts = {(node.ref.resource_id, node.ref.native_scope) for node in self._tree_nodes if node.group == "Parts"}
                self._display_state.set_hidden(all_parts - selected)

    def _show_all_parts(self):
        if self.viewport is not None:
            self._display_state.set_hidden(())

    def _fit_selected(self):
        if self.viewport is not None:
            if not self.viewport.fit_selection(self.session.selection()):
                self.statusBar().showMessage("The selection has no visible geometry", 5000)

    def _focus_tree_card(self, card_id):
        """Restore selection after a rejected draft without rebuilding rows."""
        ref = self._card_refs.get(card_id)
        blocked = self.model_tree.blockSignals(True)
        try:
            self.model_tree.select_refs((ref,) if ref else (), active=ref)
        finally:
            self.model_tree.blockSignals(blocked)
        return ref is not None

    def _restore_approved_selection(self):
        """Present canonical multi-selection without issuing another model command."""
        active = self.provider.active_object()
        refs = self.session.selected_objects()
        if not refs and active is not None:
            refs = (active,)
        refs = tuple(ref for ref in refs if ref.object_id in self._card_refs)
        self._selected_card_id = active.object_id if active else None
        blocked = self.model_tree.blockSignals(True)
        try:
            self.model_tree.select_refs(refs, active=active)
        finally:
            self.model_tree.blockSignals(blocked)

    def _activate_card(self, ref):
        self.provider.select(ref)
        selection = self.session.selection()
        if self.viewport:
            self.viewport.set_selection(selection)
        self.selectionChanged.emit(selection)

    def select_card(self, card_id):
        """Select a model card through the same guarded interaction as the tree."""
        if self._busy or not self._finish_pending_edits():
            return False
        ref = self._card_refs.get(card_id)
        if ref is None:
            return False
        try:
            self._activate_card(ref)
        except Exception as exc:
            self._show_error(exc)
            return False
        self._focus_tree_card(card_id)
        self._selected_card_id = card_id
        self._refresh_fields()
        return True

    def _commit_text(self, name, editor):
        if self._updating or self.file_edits.choosing or not editor.isModified():
            return True
        if name in ("vx", "vy", "vz") and "velocity" in self.property_editor.editors:
            return self._commit_vector()
        try:
            value = editor_value(editor)
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Enter a finite number")
        except (TypeError, ValueError) as exc:
            self.property_editor.set_error(name, str(exc))
            self._append_message(str(exc), "Error")
            return False
        return self._commit_field(name, value)

    def _submit_properties(self, values):
        if self._card_text_draft is not None:
            raise ValueError("Apply or cancel TEXT before editing FORM.")
        ref = self._card_refs[self._selected_card_id]
        units = {name: unit for name, unit in self.property_editor.units().items() if name in values}
        return self.provider.submit(SetProperties(ref, values, self._editor_revision, units=units))

    def _present_card_source(self, ref=None):
        if self._card_text_draft is not None:
            return
        source = self.session.card_text(ref.object_id) if ref is not None else ""
        available = False
        if ref is not None:
            from ..application.card_text import prepare_card_text
            try:
                prepare_card_text(self.provider, ref)
                available = True
            except Exception:
                # Unsupported native layouts remain viewable without inventing
                # a writable contract for them.
                pass
        preview = source
        if len(preview) > 100_000:
            preview = preview[:100_000] + "\n… Preview truncated. Edit supported values opens the complete card."
        self.card_source.present(preview, available=available)

    def _begin_card_text(self):
        if self._busy or self._replacement_conflict or self.modeling.active or not self._finish_pending_edits():
            return False
        ref = self._card_refs.get(self._selected_card_id)
        if ref is None:
            return False
        from ..application.card_text import prepare_card_text
        try:
            self._card_text_draft = prepare_card_text(self.provider, ref)
        except Exception as exc:
            self.card_source.show_error(getattr(exc, "message", str(exc)))
            return False
        self.card_source.begin(self.session.card_text(ref.object_id))
        self._refresh_actions()
        return True

    def _apply_card_text(self):
        draft = self._card_text_draft
        if draft is None:
            return True
        if self._busy or self._replacement_conflict:
            return False
        try:
            with self.session._lock:
                changes = draft.changes(self.provider, self.raw_source.toPlainText())
                if changes:
                    # Keep epoch validation and publication atomic, including
                    # reopening the same saved document at the same revision.
                    self.provider.submit(SetProperties(draft.target, changes, draft.revision))
        except Exception as exc:
            self.card_source.show_error(getattr(exc, "message", str(exc)))
            self._show_error(exc)
            return False
        self._card_text_draft = None
        self.refresh_document()
        self._consume_pending_selection()
        self.statusBar().showMessage("TEXT applied" if changes else "TEXT unchanged", 5000)
        return True

    def _cancel_card_text(self):
        self._card_text_draft = None
        if self._replacement_conflict:
            self._replacement_conflict = False
        self.refresh_document(rebuild_viewport=True)
        self._consume_pending_selection()

    def _review_membership(self, spec, values):
        from .group_members import review_membership
        return review_membership(self, spec, values)

    def _native_display_unit(self, name):
        spec = self.property_editor.specs.get(name)
        return spec is None or self.property_editor.units().get(name, spec.unit) == spec.unit

    def _refresh_property_context(self, choices):
        ref = self._card_refs.get(self._selected_card_id)
        if ref is None or not choices:
            return False
        specs = self.provider.properties(ref, draft_values=choices)
        if not self.property_editor.refresh_context(specs):
            return False
        self.field_editors = dict(self.property_editor.editors)
        self._field_specs.update({spec.name: {"name": spec.name, "label": spec.label,
                                            "value": spec.value, "type": spec.kind} for spec in specs})
        self._connect_property_inputs()
        return True

    def _property_choice_changed(self, name, editor):
        if self._updating or self._busy:
            return
        try:
            choices = {key: self.property_editor.editors[key].currentData()
                       for key, spec in self.property_editor.specs.items() if spec.kind == "choice"}
            if self._refresh_property_context(choices):
                return
            if (not getattr(getattr(self, "reference_adapter", None), "defer_scalars", False)
                    and not self.property_editor.context_changed):
                self._commit_field(name, editor.currentData())
        except Exception as exc:
            self._show_error(exc)

    def _commit_vector(self):
        if self._updating or self._busy:
            return False
        editor = self.property_editor.editors["velocity"]
        try:
            value = editor.numeric_value()
        except ValueError as exc:
            self.property_editor.set_error("velocity", str(exc))
            self._append_message(str(exc), "Error")
            return False
        previous = self.property_editor.specs["velocity"].value
        if value == previous and self._native_display_unit("velocity"):
            self.property_editor.set_error("velocity", "")
            for child in editor.editors:
                child.setModified(False)
            return True
        try:
            self._submit_properties({"velocity": value})
        except Exception as exc:
            self.property_editor.set_error("velocity", str(getattr(exc, "message", exc)))
            self._append_message(str(getattr(exc, "message", exc)), "Error")
            return False
        self.refresh_document()
        self._consume_pending_selection()
        self.statusBar().showMessage("Initial velocity updated", 5000)
        return True

    def _apply_properties(self):
        if self._finish_pending_edits():
            self.statusBar().showMessage("Properties updated", 5000)
            return True
        return False

    def _curve_edit_context(self):
        description = self._summary()
        return (description.get("document_epoch"), description.get("document_id"), description.get("revision"),
                self._selected_card_id, self.provider.active_object())

    def _curve_editable(self):
        description = self._summary()
        active = self.provider.active_object()
        return (not self._updating and not self._busy and not self._replacement_conflict
                and self._curve_active and active is not None and active.object_id == self._selected_card_id
                and description.get("revision") == self._editor_revision
                and description.get("document_epoch") == self._last_presented_epoch)

    def _commit_curve(self, points):
        if self._updating or self._busy:
            return False
        try:
            spec = self.provider.properties(self._card_refs[self._selected_card_id])[0]
            if tuple(map(tuple, points)) == spec.value:
                self.curve_table.set_points(spec.value)
                return True
            self._submit_properties({"points": tuple(map(tuple, points))})
        except Exception as exc:
            self.curve_table.message.setText(str(getattr(exc, "message", exc)))
            self._append_message(str(getattr(exc, "message", exc)), "Error")
            return False
        self.refresh_document()
        self._consume_pending_selection()
        self.statusBar().showMessage("Curve points updated", 5000)
        return True

    def _commit_field(self, name, value):
        if self._updating or self._busy:
            return False
        spec = self._field_specs.get(name, {})
        if value == spec.get("value") and self._native_display_unit(name):
            self.property_editor.set_error(name, "")
            editor = self.field_editors.get(name)
            if isinstance(editor, QLineEdit):
                editor.setModified(False)
            return True
        # A different editor may contain a validator's intermediate text ("1e").
        # Applying this field must not discard that unfinished user input.
        drafts = self._text_drafts(exclude=name)
        try:
            self._submit_properties({name: value})
        except Exception as exc:
            self.property_editor.set_error(name, str(getattr(exc, "message", exc)))
            self._append_message(str(getattr(exc, "message", exc)), "Error")
            return False
        label = _field_label(spec) if spec else "Property"
        self.refresh_document()
        self._restore_text_drafts(drafts)
        self._consume_pending_selection()
        self.statusBar().showMessage(f"{label} updated", 5000)
        return True

    def _text_drafts(self, *, exclude=None):
        drafts = {key: editor.text() for key, editor in self.field_editors.items()
                  if key != exclude and isinstance(editor, QLineEdit) and editor.isModified()}
        if self._curve_active and self.curve_table.has_draft():
            drafts["@curve"] = self.curve_table.draft_state()
        raw = self.property_editor.raw_values()
        units = self.property_editor.units()
        changed = {name: value for name, value in raw.items()
                   if name != exclude and value != getattr(self, "_native_property_baseline", {}).get(name)}
        changed_units = {name: unit for name, unit in units.items() if name != exclude and
                         (name in changed or unit != getattr(self, "_native_unit_baseline", {}).get(name))}
        if changed or changed_units:
            drafts["@properties"] = changed
            drafts["@units"] = changed_units
        if self.property_editor.context_changed:
            drafts["@quantities"] = self.property_editor.context_draft_state()
        if self._card_text_draft is not None:
            drafts["@card_text"] = (self._card_text_draft, self.raw_source.toPlainText(),
                                    self.raw_source.textCursor().position())
        return drafts

    def _restore_text_drafts(self, drafts):
        if "@card_text" in drafts:
            self._card_text_draft, text, position = drafts["@card_text"]
            self.card_source.begin(text)
            cursor = self.raw_source.textCursor()
            cursor.setPosition(min(position, len(text)))
            self.raw_source.setTextCursor(cursor)
        choices = {name: value for name, value in drafts.get("@properties", {}).items()
                   if name in self.property_editor.specs and self.property_editor.specs[name].kind == "choice"}
        self._refresh_property_context(choices)
        self.property_editor.restore_context_drafts(drafts.get("@quantities", {}))
        for name, unit in drafts.get("@units", {}).items():
            selector = self.property_editor.unit_selectors.get(name)
            if selector is not None and selector.findText(unit) >= 0:
                selector.setCurrentText(unit)
        for key, text in drafts.items():
            if key in ("@units", "@quantities", "@card_text"):
                continue
            if key == "@properties":
                for name, raw in text.items():
                    editor = self.property_editor.editors.get(name)
                    if editor is not None:
                        restore_editor_raw_value(editor, raw)
                continue
            if key == "@curve":
                self.curve_table.restore_draft(text)
                continue
            editor = self.field_editors.get(key)
            if isinstance(editor, QLineEdit):
                editor.setText(text)
                editor.setModified(True)

    def _capture_pending_edits(self):
        drafts = self._text_drafts()
        points = None
        if ("@curve" in drafts and self._summary().get("document_epoch") == self._last_presented_epoch
                and not self._replacement_conflict):
            points = next(spec.value for spec in self.provider.properties(self._card_refs[self._selected_card_id])
                          if spec.kind == "table")
        return self._selected_card_id, drafts, self._pending_selection, points

    def _restore_pending_edits(self, state):
        card_id, drafts, pending, points = state
        if self._selected_card_id != card_id:
            self._selected_card_id = card_id
            self._focus_tree_card(card_id)
            self._refresh_fields()
        if points is not None:
            self.curve_table.set_points(points)
        self._restore_text_drafts(drafts)
        self._pending_selection = pending

    def _consume_pending_selection(self):
        if not self._pending_selection or self._text_drafts() or self._replacement_conflict:
            return
        self._pending_selection = False
        active = self.provider.active_object()
        self._selected_card_id = active.object_id if active else None
        self._focus_tree_card(self._selected_card_id)
        self._refresh_fields()

    def _reload_properties(self):
        if self._busy or not self._summary().get("document_id"):
            return
        if self._text_drafts() or self._replacement_conflict:
            answer = self._message_box().question(self, "Unfinished input", "Discard unfinished property input and reload current model values?", self._message_box().StandardButton.Discard | self._message_box().StandardButton.Cancel, self._message_box().StandardButton.Cancel)
            if answer != self._message_box().StandardButton.Discard:
                return
        if self._replacement_conflict:
            self._replacement_conflict = False
            self._card_text_draft = None
            self.refresh_document(rebuild_viewport=True)
        else:
            self._card_text_draft = None
            self._refresh_fields()
            self._refresh_actions()
        self._consume_pending_selection()

    def _finish_pending_edits(self):
        """A validator's intermediate text must never be silently discarded by Save."""
        if not self.modeling.finish():
            return False
        if self._replacement_conflict:
            self._show_error(ValueError("Reload properties (Ctrl+R) before continuing with the replaced document."))
            return False
        if self._card_text_draft is not None:
            self.property_tabs.setCurrentIndex(1)
            self.card_source.show_error("Apply or cancel TEXT before changing selection, saving or continuing.")
            self.raw_source.setFocus()
            return False
        if self._deferred_property_drafts():
            try:
                values = self.property_editor.values()
                if values:
                    current = {spec.name: spec.value for spec in self.provider.properties(
                        self._card_refs[self._selected_card_id])}
                    changed = {name: value for name, value in values.items()
                               if value != current[name] or not self._native_display_unit(name)}
                    if changed:
                        self._submit_properties(changed)
                        self.refresh_document()
            except Exception as exc:
                self.property_tabs.setCurrentIndex(0)
                invalid = next((name for name, error in self.property_editor.errors.items() if error.text()), None)
                if invalid:
                    editor = self.property_editor.editors[invalid]
                    self.property_editor.scroll.ensureWidgetVisible(editor)
                    editor.setFocus()
                self._show_error(exc)
                return False
        for name in list(self.field_editors):
            editor = self.field_editors.get(name)
            if isinstance(editor, QLineEdit) and editor.isModified():
                if not self._commit_text(name, editor):
                    self.property_tabs.setCurrentIndex(0)
                    self.property_editor.scroll.ensureWidgetVisible(editor)
                    self.property_tabs.widget(0).ensureWidgetVisible(editor)
                    editor.setFocus()
                    self.statusBar().showMessage("Correct the highlighted property before continuing", 8000)
                    return False
        if self._curve_active and self.curve_table.has_draft():
            try:
                points = self.curve_table.points()
            except ValueError as exc:
                self.curve_table.message.setText(str(exc))
                self._append_message(str(exc), "Error")
                self.property_tabs.setCurrentIndex(0)
                self.property_tabs.widget(0).ensureWidgetVisible(self.curve_table)
                return False
            if not self._commit_curve(points):
                self.property_tabs.setCurrentIndex(0)
                self.property_tabs.widget(0).ensureWidgetVisible(self.curve_table)
                return False
        self._consume_pending_selection()
        return True

    def _deferred_property_drafts(self):
        return (getattr(getattr(self, "reference_adapter", None), "defer_scalars", False) or
                any(hasattr(editor, "raw_value") for editor in self.property_editor.editors.values()) or
                self.property_editor.context_changed or
                self.property_editor.raw_values() != getattr(self, "_native_property_baseline", {}) or
                self.property_editor.units() != getattr(self, "_native_unit_baseline", {}))

    def _discard_pending_edits(self):
        self.modeling.cancel()
        self._card_text_draft = None
        self._replacement_conflict = False
        self.refresh_document(rebuild_viewport=True)
        self._consume_pending_selection()

    def _history(self, command):
        if self._busy or not self._summary().get("document_id") or not self._finish_pending_edits():
            return
        try:
            getattr(self.session, command)()
        except Exception as exc:
            self._show_error(exc)
            return
        self.refresh_document(rebuild_viewport=True)

    def _append_message(self, message, level="Warning"):
        self.messages.addTopLevelItem(QTreeWidgetItem([level, str(message)]))

    def _viewport_diagnostic(self, message):
        self._append_message(message)
        self.messages_dock.show()

    def _show_error(self, exc):
        message = str(getattr(exc, "message", str(exc)))
        self._append_message(message, "Error")
        self.messages_dock.show()
        self.statusBar().showMessage(message, 12000)

    def _start_task(self, label, function, on_success=None):
        if self._busy:
            return
        self._busy = True
        self._refresh_actions()
        self._progress.show()
        self.statusBar().showMessage(label + "…")
        task = self._task_factory(function, operation_id=label)
        task.signals.stateChanged.connect(self._operation_changed)
        self._active_task = task

        def done(result):
            self._busy = False
            self._active_task = None
            self._progress.hide()
            try:
                if on_success:
                    on_success(result)
                else:
                    self.refresh_document()
            except Exception as exc:
                self._refresh_actions()
                self._show_error(exc)
                self.operationFinished.emit(label, False)
            else:
                self.operationFinished.emit(label, True)

        def failed(exc):
            self._busy = False
            self._active_task = None
            self._progress.hide()
            self._refresh_actions()
            self.file_edits.save_failed()
            self._show_error(exc)
            self.operationFinished.emit(label, False)

        task.signals.complete.connect(done)
        task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)
        return True

    def _operation_changed(self, state):
        self.operation_state = state
        self._progress.setAccessibleDescription(f"{state.operation_id}: {state.status}")

    def _before_replace(self, continuation):
        return self.file_edits.guard(continuation)

    def open_rad_dialog(self):
        filename, _ = self._file_dialog().getOpenFileName(self, "Open Radioss deck", "", "Radioss decks (*.rad);;All files (*)")
        if filename:
            self.open_rad_file(filename)

    def open_rad_file(self, filename):
        if self._busy:
            return
        def loaded(_):
            self._source_path = Path(filename)
            self._project_path = None
            self._selected_card_id = None
            self.refresh_document(rebuild_viewport=True)
        self._before_replace(lambda: self._start_task("Open Radioss deck", lambda: self.session.open_rad(str(filename)), loaded))

    def open_project_dialog(self):
        filename, _ = self._file_dialog().getOpenFileName(self, "Open CAELab Prep project", "", "CAELab Prep projects (*.caeprep);;All files (*)")
        if filename:
            self.open_project_file(filename)

    def open_project_file(self, filename):
        if self._busy:
            return
        def loaded(_):
            self._project_path = Path(filename)
            self._source_path = None
            self._selected_card_id = None
            self.refresh_document(rebuild_viewport=True)
        self._before_replace(lambda: self._start_task("Open project", lambda: self.session.open_project(str(filename)), loaded))

    def save_project_dialog(self, checked=False, *, force_new=False, on_saved=None):
        if self._busy or not self._summary().get("document_id"):
            return False
        if not self._finish_pending_edits():
            return False
        path = None if force_new else self._project_path
        if path is None:
            default = self._source_path.with_suffix(".caeprep") if self._source_path else Path("model.caeprep")
            filename, _ = self._file_dialog().getSaveFileName(self, "Save CAELab Prep project", str(default), "CAELab Prep projects (*.caeprep)")
            if not filename:
                return False
            path = Path(filename)
            if not path.suffix:
                path = path.with_suffix(".caeprep")
        return self.save_project_file(path, on_saved=on_saved)

    def save_project_file(self, filename, *, on_saved=None):
        if self._busy or not self._summary().get("document_id"):
            return False
        if not self._finish_pending_edits():
            return False
        def saved(_):
            self._project_path = Path(filename)
            self.refresh_document()
            self.statusBar().showMessage("Project saved", 5000)
            if on_saved:
                on_saved()
        return self._start_task("Save project", lambda: self.session.save_project(str(filename)), saved)

    def export_rad_dialog(self):
        if self._busy or not self._summary().get("document_id"):
            return
        if not self._finish_pending_edits():
            return
        base = self._project_path or self._source_path or Path("model.rad")
        default = base.with_name(base.stem + "_export.rad")
        filename, _ = self._file_dialog().getSaveFileName(self, "Export Radioss deck", str(default), "Radioss decks (*.rad)")
        if filename:
            self.export_rad_file(filename)

    def export_rad_file(self, filename):
        if self._busy or not self._summary().get("document_id"):
            return
        if not self._finish_pending_edits():
            return
        def exported(_):
            self.refresh_document()
            self.statusBar().showMessage(f"Radioss deck exported to {filename}", 8000)
        self._start_task("Export Radioss deck", lambda: self.session.export_rad(str(filename)), exported)

    def _entity_picked(self, entity):
        if self._busy or self._replacement_conflict or not self._summary().get("document_id"):
            return
        try:
            if self.modeling.active:
                self.modeling.finish()
                return
            if self._text_drafts():
                if not self._finish_pending_edits():
                    return
                # Finishing input can replace the projection stamp; the user picks again.
                self.statusBar().showMessage("Properties applied. Pick the model again.")
                return
            selection = self.session.select_pick(entity)
        except Exception as exc:
            self._show_error(exc)
            return
        if self.viewport:
            self.viewport.set_selection(selection)
        self.selectionChanged.emit(selection)
        if not selection.get("ids"):
            self.statusBar().showMessage("Selection cleared")
            return
        text = f"{entity['kind'].capitalize()} {entity['id']}"
        if entity.get("part_id") is not None:
            text += f"  ·  Part {entity['part_id']}"
        self.statusBar().showMessage(text)

    def _pick_mode_changed(self, index):
        if self.viewport:
            self.viewport.set_pick_mode("node" if index else "element")

    def _fit(self):
        if self.viewport:
            self.viewport.fit_view()

    def _isometric(self):
        if self.viewport:
            self.viewport.isometric_view()

    def _standard_view(self, axis):
        if self.viewport:
            self.viewport.standard_view(axis)

    def _toggle_edges(self, visible):
        if self.viewport:
            self.viewport.set_edges_visible(visible)

    def closeEvent(self, event: QCloseEvent):
        if self._closed:
            event.accept()
            return
        if self._busy:
            self.statusBar().showMessage("Wait for the current file operation to finish")
            event.ignore()
            return
        if not self._allow_close:
            deciding = True
            def continue_close():
                self._allow_close = True
                if not deciding:
                    self.close()
            proceed = self.file_edits.guard(continue_close)
            deciding = False
            if not proceed:
                event.ignore()
                return
        self._settings.setValue("windowGeometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState(self.LAYOUT_VERSION))
        for dialog in (self.source_models_dialog, self.prepared_mesh_dialog, self.node_move_dialog, self.node_merge_dialog, self.shell_normal_dialog, self.element_deletion_dialog):
            if dialog is not None:
                dialog.reject()
        if self.viewport:
            self.viewport.shutdown()
        self._unsubscribe()
        self._display_state.changed.disconnect(self._apply_display_state)
        self._closed = True
        event.accept()

    def _close_after_save(self):
        self._allow_close = True
        self.close()
