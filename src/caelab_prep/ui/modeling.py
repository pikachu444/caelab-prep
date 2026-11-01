"""Provider-backed operation editing and transient display state shared by views."""
from weakref import WeakKeyDictionary
from dataclasses import replace
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..application.contracts import OperationRequest
from .widgets import PropertyEditor


class DisplayState(QObject):
    """Visibility belongs to the UI session, independently of document Undo/save."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.epoch = None
        self.hidden = frozenset()

    def reset(self, epoch):
        if epoch != self.epoch:
            self.epoch = epoch
            self.hidden = frozenset()

    def set_hidden(self, refs):
        hidden = frozenset(refs)
        if hidden != self.hidden:
            self.hidden = hidden
            self.changed.emit()


_DISPLAY_STATES = WeakKeyDictionary()


def display_state(session):
    if session not in _DISPLAY_STATES:
        _DISPLAY_STATES[session] = DisplayState()
    return _DISPLAY_STATES[session]


class OperationPanel(QWidget):
    """Keep a complete create/copy/assignment draft outside the document."""

    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modelOperationPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setContentsMargins(8, 5, 8, 5)
        layout.addWidget(self.description)
        self.editor = PropertyEditor()
        layout.addWidget(self.editor, 1)
        self.error = QLabel()
        self.error.setObjectName("inputError")
        self.error.setWordWrap(True)
        self.error.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryAction")
        self.cancel_button = QPushButton("Cancel")
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.apply_button.clicked.connect(self.applyRequested)
        self.cancel_button.clicked.connect(self.cancelRequested)

    def present(self, spec, presentation):
        self.editor.set_presentation(presentation)
        self.editor.set_fields(spec.fields, title=spec.title)
        self.description.setText(spec.description)
        self.description.setVisible(bool(spec.description))
        self.error.clear()
        self.error.hide()
        self.apply_button.setText("Delete" if spec.destructive else
                                  "Create" if spec.key.endswith(".create") or spec.key == "object.copy" else "Apply")

    def fail(self, message):
        self.error.setText(message)
        self.error.show()


class ModelingActions(QObject):
    """Share action identity, operation drafts and commit behavior across profiles."""

    COMMANDS = (
        ("material.create", "New material…", "material"),
        ("section.create", "New shell section…", "section"),
        ("solid_section.create", "New solid section…", "section"),
        ("curve.create", "New load curve…", "curve"),
        ("group.create", "New node group…", "set"),
        ("element_group.create", "New element group…", "set"),
        ("surface.create", "New shell surface…", "mesh"),
        ("constraint.create", "New boundary condition…", "constraint"),
        ("load.create", "New per-node load…", "load"),
        ("velocity.create", "New initial velocity…", "vector"),
        ("contact.create", "New TYPE7 contact…", "contact"),
        ("object.edit", "Edit selected…", "card"),
        ("object.copy", "Copy selected…", "project"),
        ("object.delete", "Delete selected…", "card"),
        ("part.assign", "Assign material / section…", "part"),
    )

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.panel = OperationPanel(host)
        self.panel.hide()
        self.spec = None
        self.stack = None
        self._dock_sizes = None
        self.actions = {}
        for key, label, glyph in self.COMMANDS:
            self.actions[key] = host._action(glyph, label, lambda checked=False, k=key: self.begin(k),
                                             action_id=key)
            self.actions[key].setIconText({"material.create": "New material", "section.create": "Shell section",
                                           "solid_section.create": "Solid section",
                                           "object.copy": "Copy", "object.delete": "Delete", "object.edit": "Edit",
                                           "part.assign": "Assign", "curve.create": "Curve", "group.create": "Node group",
                                           "element_group.create": "Element group",
                                           "surface.create": "Surface", "constraint.create": "Boundary",
                                           "load.create": "Load", "velocity.create": "Velocity", "contact.create": "Contact"}[key])
        self.panel.applyRequested.connect(self.commit)
        self.panel.cancelRequested.connect(self.cancel)

    @property
    def active(self):
        return self.spec is not None

    def mount(self, stack):
        self.stack = stack
        stack.addWidget(self.panel)

    def refresh(self):
        h = self.host
        available = set()
        describe = getattr(h.provider, "available_operations", None)
        if describe and not h._busy and not h._replacement_conflict and not self.active:
            try:
                available = set(describe(h.provider.active_object()))
            except Exception:
                available = set()
        if hasattr(h, "model_tree") and len(h.model_tree.selected_refs()) > 1:
            available.difference_update(("object.edit", "object.copy", "object.delete", "part.assign"))
        for key, action in self.actions.items():
            action.setEnabled(key in available)

    def begin(self, key):
        h = self.host
        if self.active or h._busy or not h._finish_pending_edits():
            return False
        try:
            target = None if key.endswith(".create") else h.provider.active_object()
            spec = h.provider.operation_spec(key, target)
        except Exception as exc:
            h._show_error(exc)
            return False
        self.spec = spec
        self.panel.present(spec, h.property_editor.presentation)
        self._bind_context_choices()
        self.stack.setCurrentWidget(self.panel)
        self._show()
        self.refresh()
        return True

    def _bind_context_choices(self):
        for field in self.spec.fields:
            if field.kind == "choice":
                self.panel.editor.editors[field.name].currentIndexChanged.connect(self._context_changed)

    def _context_changed(self, _index):
        if self.spec is None:
            return
        editor = self.panel.editor
        values = {field.name: editor.editors[field.name].currentData()
                  for field in self.spec.fields if field.kind == "choice"}
        try:
            fresh = self.host.provider.operation_spec(self.spec.key, self.spec.target, draft_values=values)
            if editor.refresh_context(fresh.fields):
                self.spec = replace(self.spec, fields=fresh.fields)
                self._bind_context_choices()
        except Exception as exc:
            self.panel.fail(str(getattr(exc, "message", exc)))

    def _show(self):
        h = self.host
        dialog = getattr(h, "property_dialog", None)
        if dialog is not None:
            bindings = h.reference_bindings
            if bindings.dialog_buttons is not None:
                bindings.dialog_buttons.hide()
            dialog.setWindowTitle(self.spec.title + " — CAELab Prep")
            dialog.open()
        else:
            h.properties_dock.show()
            h.properties_dock.raise_()
            adjacent = getattr(getattr(h, "reference_adapter", None), "docks", None)
            if self._dock_sizes is None and not (adjacent and adjacent.adjacent):
                self._dock_sizes = (h.model_dock.height(), h.properties_dock.height())
                total = sum(self._dock_sizes)
                h.resizeDocks([h.model_dock, h.properties_dock],
                              [max(90, total - 390), min(390, max(290, total - 90))], Qt.Orientation.Vertical)

    def finish(self):
        """File/navigation actions cannot implicitly create or delete an object."""
        if not self.active:
            return True
        message = "Apply or cancel the current operation before continuing."
        self.panel.fail(message)
        self._show()
        self.host.statusBar().showMessage(message, 8000)
        return False

    def commit(self):
        if not self.active or self.host._busy:
            return False
        spec = self.spec
        try:
            values = self.panel.editor.values()
            result = self.host.provider.execute_operation(OperationRequest(
                spec.key, values, spec.document_id, spec.expected_revision, spec.target,
                units=self.panel.editor.units()))
        except Exception as exc:
            self.panel.fail(str(getattr(exc, "message", exc)))
            return False
        self.cancel()
        self.host.refresh_document(rebuild_viewport=True)
        target = result.get("object")
        if target is not None and target != self.host.provider.active_object():
            self.host.select_card(target.object_id)
        self.host.statusBar().showMessage(spec.title + " completed", 5000)
        return True

    def cancel(self):
        if not self.active:
            return
        self.spec = None
        if self.stack is not None:
            self.stack.setCurrentIndex(0)
        h = self.host
        dialog = getattr(h, "property_dialog", None)
        if dialog is not None:
            dialog.hide()
            bindings = h.reference_bindings
            if bindings.dialog_buttons is not None:
                bindings.dialog_buttons.show()
            dialog.setWindowTitle(h.reference_adapter.interaction.title + " — CAELab Prep")
        if self._dock_sizes is not None:
            h.resizeDocks([h.model_dock, h.properties_dock], self._dock_sizes, Qt.Orientation.Vertical)
            self._dock_sizes = None
        self.refresh()
