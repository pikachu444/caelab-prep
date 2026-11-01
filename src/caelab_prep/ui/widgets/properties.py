"""Native engineering inspector composed from field rows and section grids."""

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                              QHeaderView, QLabel, QScrollArea, QSizePolicy,
                              QTabWidget, QVBoxLayout, QWidget)

from ._editing import bind_units, create_editor, editor_raw_value, editor_value, restore_editor_raw_value
from .numeric import NumericEdit, VectorEdit
from .tree import field
from ..design import TOKENS


class _PropertyRow(QFrame):
    """A label, typed draft and unit share one aligned engineering row."""

    def __init__(self, label, editor, unit_widget, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyRow")
        grid = QGridLayout(self)
        self.grid = grid
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(0)
        self.label = QLabel(label)
        self.label.setObjectName("propertyLabel")
        self.label.setWordWrap(True)
        self.label.setToolTip(label)
        self.label.setContentsMargins(7, 0, 5, 0)
        self.label.setBuddy(editor)
        grid.addWidget(self.label, 0, 0)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.value_cell = QWidget()
        value_layout = QHBoxLayout(self.value_cell)
        value_layout.setContentsMargins(4, 0, 4, 0)
        value_layout.setSpacing(4)
        value_layout.addWidget(editor, 1)
        grid.addWidget(self.value_cell, 0, 1)
        self.editor, self.unit_widget = editor, unit_widget
        self.multiline = bool(getattr(editor, "is_multiline", False))
        self.unit_cell = QWidget()
        unit_layout = QHBoxLayout(self.unit_cell)
        unit_layout.setContentsMargins(3, 0, 3, 0)
        if unit_widget is not None:
            if isinstance(unit_widget, QLabel):
                unit_widget.setWordWrap(True)
            unit_widget.setToolTip(unit_widget.currentText() if isinstance(unit_widget, QComboBox) else unit_widget.text())
            unit_layout.addWidget(unit_widget)
        grid.addWidget(self.unit_cell, 0, 2)
        self.error = QLabel(self)
        self.error.setObjectName("inputError")
        self.error.setWordWrap(True)
        self.error.hide()

    def reset_layout(self):
        for widget in (self.label, self.value_cell, self.unit_cell):
            self.grid.removeWidget(widget)
            widget.setMinimumWidth(0)
            widget.setMaximumWidth(16777215)
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self.grid.setContentsMargins(0, 2, 0, 2)
        self.grid.setVerticalSpacing(0)
        for column in range(3):
            self.grid.setColumnStretch(column, 0)
        self.label.setContentsMargins(7, 0, 5, 0)
        self.grid.addWidget(self.label, 0, 0)
        self.grid.addWidget(self.value_cell, 0, 1)
        self.grid.addWidget(self.unit_cell, 0, 2)
        self.unit_cell.show()
        if self.unit_widget is not None:
            self.unit_cell.layout().addWidget(self.unit_widget)

    def pair_unit(self):
        self.unit_cell.hide()
        if self.unit_widget is not None:
            self.value_cell.layout().addWidget(self.unit_widget)

    def set_columns(self, widths, *, paired=False):
        self.label.setFixedWidth(widths[0])
        self.value_cell.setFixedWidth(widths[1])
        if paired:
            self.pair_unit()
        else:
            self.unit_cell.setFixedWidth(widths[2])
        self.setFixedWidth(sum(widths))

    def stack_label(self):
        self.grid.removeWidget(self.label)
        self.grid.addWidget(self.label, 0, 0)
        self.grid.removeWidget(self.value_cell)
        self.grid.addWidget(self.value_cell, 1, 0, 1, 2 if self.multiline else 1)
        self.grid.setVerticalSpacing(3)
        self.grid.setColumnStretch(0, 1)
        self.grid.setContentsMargins(6, 4, 6, 5)
        self.label.setContentsMargins(4, 0, 0, 0)
        self.grid.removeWidget(self.unit_cell)
        if self.multiline:
            self.grid.addWidget(self.unit_cell, 0, 1)
            self.unit_cell.show()
        else:
            self.pair_unit()

    def settings_label(self, width):
        self.label.setFixedWidth(width)
        self.grid.setColumnStretch(1, 1)
        self.pair_unit()


class _PropertySection(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyGroup")
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        heading = QFrame()
        heading.setObjectName("propertySectionHeading")
        line = QHBoxLayout(heading)
        line.setContentsMargins(7, 3, 7, 3)
        label = QLabel(title)
        label.setObjectName("groupTitle")
        label.setWordWrap(True)
        line.addWidget(label, 1)
        self.rows.addWidget(heading)

    def add_row(self, row):
        self.rows.addWidget(row)


def _grouped_body(rows, specs, *, tabbed=False):
    body = QWidget()
    body.setObjectName("propertyBody")
    stack = QVBoxLayout(body)
    stack.setContentsMargins(0, 0, 0, 0)
    stack.setSpacing(0)
    tabs = QTabWidget() if tabbed else None
    if tabs is not None:
        stack.addWidget(tabs)
    groups = {}
    for name, row in rows.items():
        group = str(field(specs[name], "group", "Properties"))
        if group not in groups:
            section = groups[group] = _PropertySection(group)
            if tabs is not None:
                tabs.addTab(section, group)
            else:
                stack.addWidget(section)
        groups[group].add_row(row)
    for section in groups.values():
        section.rows.itemAt(0).widget().setVisible(len(groups) > 1 and tabs is None)
        if tabs is not None:
            section.rows.addStretch(1)
    stack.addStretch(1)
    return body


class _ColumnPresentation:
    def __init__(self, *, paired=False):
        self.paired = paired
        self.headers = ("Name", "Value") if paired else ("Name", "Value", "Unit")

    def compose(self, rows, specs):
        for row in rows.values():
            if row.multiline:
                row.stack_label()
            elif self.paired:
                row.pair_unit()
        return _grouped_body(rows, specs)

    def fit(self, panel):
        widths = panel._column_sizes[:len(self.headers)]
        available = panel.scroll.viewport().width()
        minimum = max((row.value_cell.minimumSizeHint().width() for row in panel._rows.values()
                       if not row.multiline), default=100)
        if not self.paired:
            has_units = any(row.unit_widget is not None for row in panel._rows.values())
            panel.column_header.setSectionHidden(2, not has_units)
            widths[2] = (max(widths[2], max((row.unit_cell.minimumSizeHint().width()
                                           for row in panel._rows.values()), default=64))
                         if has_units else 0)
        if not panel._columns_changed:
            widths[0] = max(96, min(156, round(available * .40)))
            widths[1] = max(110, available - widths[0] - sum(widths[2:]))
        elif sum(widths) < available:
            widths[1] += available - sum(widths)
        widths[1] = max(widths[1], minimum)
        for index, size in enumerate(widths):
            panel.column_header.resizeSection(index, size)
        for row in panel._rows.values():
            if row.multiline:
                row.setFixedWidth(max(available, sum(widths)))
            else:
                row.set_columns(widths, paired=self.paired)
        panel.scroll.widget().setMinimumWidth(sum(widths))
        panel.column_header.setFixedHeight(panel.column_header.sizeHint().height())


class _FormPresentation:
    headers = ()

    def __init__(self, *, tabbed=False):
        self.tabbed = tabbed

    def compose(self, rows, specs):
        for row in rows.values():
            row.stack_label()
        return _grouped_body(rows, specs, tabbed=self.tabbed)

    def fit(self, panel):
        pass


class _SettingsPresentation:
    headers = ()

    def compose(self, rows, specs):
        for row in rows.values():
            row.stack_label() if row.multiline else row.settings_label(148)
            row._settings_stacked = row.multiline
        return _grouped_body(rows, specs)

    def fit(self, panel):
        # A narrow Settings dock must keep the complete value and its unit
        # visible. Only the label placement changes; the editors/draft survive.
        for row in panel._rows.values():
            stacked = row.multiline or panel.scroll.viewport().width() < 360
            if getattr(row, "_settings_stacked", None) == stacked:
                continue
            row.reset_layout()
            if stacked:
                row.stack_label()
            else:
                row.settings_label(148)
            row._settings_stacked = stacked


_PRESENTATIONS = {
    "columns": _ColumnPresentation,
    "grid": lambda: _ColumnPresentation(paired=True),
    "settings": _SettingsPresentation,
    "form": _FormPresentation,
    "tabs": lambda: _FormPresentation(tabbed=True),
}


class PropertyEditor(QWidget):
    """Own presentation and input buffers; the host owns Apply and Undo."""

    draftChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyEditor")
        self.setStyleSheet(
            f"QFrame#propertySectionHeading {{ background: {TOKENS['raised']}; "
            f"border-top: 1px solid {TOKENS['divider']}; border-bottom: 1px solid {TOKENS['divider']}; }}"
            f"QFrame#propertyRow {{ background: {TOKENS['surface']}; border-bottom: 1px solid {TOKENS['alternate']}; }}"
            f"QLabel#propertyLabel[invalid='true'] {{ color: {TOKENS['error']}; font-weight: bold; }}")
        self.editors, self.specs, self.errors, self.unit_selectors = {}, {}, {}, {}
        self._rows = {}
        self._quantity_drafts = {}
        self.context_changed = False
        self.presentation = "columns"
        self._presentation = _ColumnPresentation()
        self._spec_sequence = ()
        self._column_sizes = [136, 132, 66]
        self._columns_changed = False
        self._adjusting_columns = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("propertyHeader")
        identity = QGridLayout(header)
        identity.setContentsMargins(7, 5, 7, 5)
        identity.setHorizontalSpacing(8)
        identity.setVerticalSpacing(2)
        self.edit_state = QLabel()
        self.edit_state.setObjectName("unitsNote")
        self.edit_state.setAccessibleName("Property edit state")
        self.title = QLabel("Select an object")
        self.title.setObjectName("propertyTitle")
        self.title.setWordWrap(True)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("propertySubtitle")
        self.subtitle.setWordWrap(True)
        identity.addWidget(self.title, 0, 0)
        identity.addWidget(self.edit_state, 0, 1, Qt.AlignmentFlag.AlignRight)
        identity.addWidget(self.subtitle, 1, 0, 1, 2)
        identity.setColumnStretch(0, 1)
        self._layout.addWidget(header)
        self.column_header = QHeaderView(Qt.Orientation.Horizontal)
        self.column_header.setObjectName("propertyColumns")
        self.column_header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.column_header.setAccessibleName("Resize property name, value and unit columns")
        self.column_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.column_header.setMinimumSectionSize(64)
        self.column_header.setStretchLastSection(False)
        self._header_model = QStandardItemModel(0, 3, self)
        self.column_header.setModel(self._header_model)
        self.column_header.sectionResized.connect(self._column_resized)
        self._layout.addWidget(self.column_header)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.horizontalScrollBar().valueChanged.connect(self.column_header.setOffset)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.setAccessibleName("Object properties")
        self._layout.addWidget(self.scroll, 1)
        self.error_detail = QLabel()
        self.error_detail.setObjectName("inputError")
        self.error_detail.setWordWrap(True)
        self.error_detail.setContentsMargins(7, 3, 7, 3)
        self.error_detail.setMaximumHeight(58)
        self.error_detail.hide()
        self._layout.addWidget(self.error_detail)
        self.set_fields(())

    def set_presentation(self, presentation):
        """Change composition only; typed drafts and commands belong to the host."""
        if presentation not in _PRESENTATIONS:
            raise ValueError(f"Unknown property presentation: {presentation}")
        if self.presentation == presentation:
            return
        self.presentation = presentation
        self._presentation = _PRESENTATIONS[presentation]()
        self._compose_rows()

    def _column_resized(self, index, old, size):
        if self._adjusting_columns:
            return
        minimum = 100 if index == 1 else 64
        if not self._columns_changed:
            for column in range(self.column_header.count()):
                self._column_sizes[column] = self.column_header.sectionSize(column)
        self._column_sizes[index] = max(minimum, size)
        self._columns_changed = True
        self._fit_columns()

    def _fit_columns(self):
        if self._adjusting_columns or self.scroll.widget() is None:
            return
        self._adjusting_columns = True
        try:
            self._presentation.fit(self)
        finally:
            self._adjusting_columns = False

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_columns()
        elif event.type() == QEvent.Type.FocusIn:
            self._show_error_detail()
        return super().eventFilter(watched, event)

    def _show_error_detail(self):
        failures = [(name, label.text()) for name, label in self.errors.items() if label.text()]
        focused = QApplication.focusWidget()
        name, message = next(((n, m) for n, m in failures if focused is self.editors[n]
                              or (focused is not None and self._rows[n].isAncestorOf(focused))), failures[0] if failures else (None, ""))
        text = f"{field(self.specs[name], 'label', name)}: {message}" if name else ""
        if len(failures) > 1:
            text = f"{len(failures)} invalid fields. " + text
        self.error_detail.setText(text)
        self.error_detail.setToolTip("\n".join(f"{field(self.specs[n], 'label', n)}: {m}" for n, m in failures))
        self.error_detail.setVisible(bool(failures))
        if failures:
            self.edit_state.setText("Invalid draft")
        elif self.edit_state.text() == "Invalid draft":
            self.edit_state.setText("Draft")

    def set_fields(self, specs, values=None, *, title="", subtitle="", preserve_context=False):
        if not preserve_context:
            self._quantity_drafts = {}
            self.context_changed = False
        specs = tuple(specs)
        self._spec_sequence = specs
        if title:
            self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self.editors, self.specs, self.errors, self.unit_selectors = {}, {}, {}, {}
        self._rows = {}
        self.error_detail.hide()
        self.edit_state.setText("" if not specs else "Values" if any(field(s, "editable", True) for s in specs) else "Read-only")
        for spec in specs:
            name = field(spec, "name")
            label = str(field(spec, "label", name))
            def changed(n=name):
                self.set_error(n, "")
                self.edit_state.setText("Draft")
                self.draftChanged.emit()
            editor = create_editor(spec, (values or {}).get(name, field(spec, "value")), changed)
            editor.installEventFilter(self)
            for child in editor.findChildren(QWidget):
                child.installEventFilter(self)
            self.specs[name], self.editors[name] = spec, editor
            row = _PropertyRow(label, editor, self._unit_widget(name, spec, editor, label))
            self._rows[name], self.errors[name] = row, row.error
        self._compose_rows()

    def refresh_context(self, specs):
        """Switch provider-defined quantities without inventing a conversion.

        Unrelated inputs retain their exact drafts. A previously visited quantity
        restores its own draft; a new quantity requires a fresh value and unit.
        """
        specs = tuple(specs)
        changed = {field(spec, "name") for spec in specs
                   if field(spec, "name") in self.specs and
                   field(spec, "unit_context", {}).get("quantity") !=
                   field(self.specs[field(spec, "name")], "unit_context", {}).get("quantity")}
        if not changed:
            return False
        raw, units = self.raw_values(), self.units()
        for name in changed:
            quantity = field(self.specs[name], "unit_context", {}).get("quantity")
            self._quantity_drafts[(name, quantity)] = (raw[name], units.get(name))
        self.set_fields(specs, title=self.title.text(), subtitle=self.subtitle.text(), preserve_context=True)
        self.context_changed = True
        for name, editor in self.editors.items():
            selector = self.unit_selectors.get(name)
            if name in changed:
                quantity = field(self.specs[name], "unit_context", {}).get("quantity")
                cached = self._quantity_drafts.get((name, quantity))
                value, unit = cached if cached is not None else ("", None)
                if isinstance(editor, NumericEdit):
                    editor.accept_value("")
                if selector is not None:
                    blocked = QSignalBlocker(selector)
                    selector.insertItem(0, "Select a unit", None)
                    selector.setCurrentIndex(0)
                    selector.setProperty("unitChoiceRequired", True)
                    del blocked
                    if unit is not None:
                        selector.setCurrentText(unit)
                restore_editor_raw_value(editor, value)
                self.set_error(name, "Enter a value and choose its unit for the new quantity" if cached is None else "")
            elif name in raw:
                if selector is not None and name in units and selector.findText(units[name]) >= 0:
                    selector.setCurrentText(units[name])
                restore_editor_raw_value(editor, raw[name])
        self.draftChanged.emit()
        return True

    def context_draft_state(self):
        return dict(self._quantity_drafts)

    def restore_context_drafts(self, state):
        self._quantity_drafts.update(state)

    def _compose_rows(self):
        # Detach retained drafts before disposing of their former containers.
        focused = QApplication.focusWidget()
        retained_focus = focused is not None and any(row.isAncestorOf(focused) for row in self._rows.values())
        blocked = [QSignalBlocker(widget) for row in self._rows.values()
                   for widget in (row.editor, *row.editor.findChildren(QWidget))]
        for row in self._rows.values():
            row.setParent(self)
            row.reset_layout()
        headers = self._presentation.headers
        self._adjusting_columns = True
        self._header_model.setColumnCount(len(headers))
        self._header_model.setHorizontalHeaderLabels(list(headers))
        self._adjusting_columns = False
        self.column_header.setVisible(bool(self._rows) and bool(headers))
        body = self._presentation.compose(self._rows, self.specs)
        previous = self.scroll.takeWidget()
        if previous is not None:
            previous.deleteLater()
        self.scroll.setWidget(body)
        self._fit_columns()
        for row in self._rows.values():
            row.show()
        if retained_focus:
            focused.setFocus(Qt.FocusReason.OtherFocusReason)
        del blocked

    def _unit_widget(self, name, spec, editor, label):
        unit = str(field(spec, "unit", ""))
        choices = field(spec, "unit_choices", ())
        if choices:
            selector = QComboBox()
            selector.addItems(list(choices))
            selector.setCurrentText(unit)
            selector.setAccessibleName(f"{label} unit")
            selector.installEventFilter(self)
            selector.currentTextChanged.connect(selector.setToolTip)
            selector.setEnabled(bool(field(spec, "editable", True)))
            scales = dict(field(spec, "unit_scales", ()))
            if scales and isinstance(editor, (NumericEdit, VectorEdit)):
                self._connect_units(name, editor, selector, scales, unit)
            selector.currentTextChanged.connect(self.draftChanged)
            self.unit_selectors[name] = selector
            return selector
        if unit:
            label = QLabel(unit)
            label.setObjectName("unitsNote")
            reason = field(spec, "unit_context", {}).get("reason", "")
            if reason:
                label.setToolTip(reason)
                label.setAccessibleDescription(reason)
            return label
        return None

    # Compatibility adapter: typed values, invalid drafts and unit rollback are
    # unchanged; rebuilding the inspector never submits a document command.
    def values(self):
        values, failure = {}, None
        for name, editor in self.editors.items():
            if not field(self.specs[name], "editable", True):
                continue
            try:
                values[name] = editor_value(editor)
                selector = self.unit_selectors.get(name)
                if selector is not None and selector.property("unitChoiceRequired"):
                    raise ValueError("Choose a display unit for this quantity")
                self.set_error(name, "")
            except ValueError as exc:
                self.set_error(name, str(exc))
                failure = failure or exc
        if failure:
            raise failure
        return values

    def units(self):
        return {name: selector.currentText() for name, selector in self.unit_selectors.items()}

    def raw_values(self):
        return {name: editor_raw_value(editor) for name, editor in self.editors.items()}

    def _connect_units(self, name, editor, selector, scales, initial_unit):
        bind_units(editor, selector, scales, initial_unit, lambda message: self.set_error(name, message))

    def set_error(self, name, message):
        editor = self.editors.get(name)
        if hasattr(editor, "set_error"):
            editor.set_error(message)
        error = self.errors.get(name)
        if error is not None:
            error.setText(str(message))
            row = self._rows[name]
            row.label.setToolTip(str(message) or row.label.text())
            row.label.setProperty("invalid", bool(message))
            row.setProperty("invalid", bool(message))
            row.label.style().unpolish(row.label)
            row.label.style().polish(row.label)
            row.style().unpolish(row)
            row.style().polish(row)
            self._show_error_detail()


PropertyPanel = PropertyEditor
