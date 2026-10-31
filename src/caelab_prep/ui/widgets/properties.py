"""Native engineering inspector composed from field rows and section grids."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                              QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ._editing import bind_units, create_editor, editor_raw_value, editor_value
from .numeric import NumericEdit
from .tree import field
from ..design import TOKENS, icon


class _PropertyRow(QFrame):
    """A label, typed draft and unit share one aligned engineering row."""

    def __init__(self, label, editor, unit_widget, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyRow")
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        self.label = QLabel(label)
        self.label.setObjectName("propertyLabel")
        self.label.setWordWrap(True)
        self.label.setFixedWidth(110)
        self.label.setBuddy(editor)
        grid.addWidget(self.label, 0, 0, Qt.AlignmentFlag.AlignVCenter)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        grid.addWidget(editor, 0, 1)
        if unit_widget is not None:
            unit_widget.setMinimumWidth(56)
            unit_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            grid.addWidget(unit_widget, 0, 2, Qt.AlignmentFlag.AlignVCenter)
        self.error = QLabel()
        self.error.setObjectName("inputError")
        self.error.setWordWrap(True)
        self.error.hide()
        grid.addWidget(self.error, 1, 1, 1, 2)
        grid.setColumnStretch(1, 1)


class _PropertySection(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyGroup")
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(0, 0, 0, 3)
        self.rows.setSpacing(0)
        heading = QFrame()
        heading.setObjectName("propertySectionHeading")
        line = QHBoxLayout(heading)
        line.setContentsMargins(8, 5, 8, 5)
        label = QLabel(title)
        label.setObjectName("groupTitle")
        label.setWordWrap(True)
        line.addWidget(label, 1)
        self.count = QLabel()
        self.count.setObjectName("unitsNote")
        line.addWidget(self.count)
        self.rows.addWidget(heading)
        self._count = 0

    def add_row(self, row):
        self.rows.addWidget(row)
        self._count += 1
        self.count.setText(str(self._count))


class PropertyEditor(QWidget):
    """Own presentation and input buffers; the host owns Apply and Undo."""

    draftChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyEditor")
        self.setStyleSheet(
            f"QFrame#propertySectionHeading {{ background: {TOKENS['raised']}; "
            f"border-top: 1px solid {TOKENS['divider']}; border-bottom: 1px solid {TOKENS['divider']}; }}"
            f"QFrame#propertyRow {{ background: {TOKENS['surface']}; border-bottom: 1px solid {TOKENS['alternate']}; }}")
        self.editors, self.specs, self.errors, self.unit_selectors = {}, {}, {}, {}
        self._rows = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("propertyHeader")
        identity = QGridLayout(header)
        identity.setContentsMargins(9, 9, 9, 9)
        identity.setHorizontalSpacing(8)
        identity.setVerticalSpacing(2)
        symbol = QLabel()
        symbol.setPixmap(icon("card").pixmap(20, 20))
        identity.addWidget(symbol, 0, 0, 2, 1, Qt.AlignmentFlag.AlignTop)
        self.title = QLabel("Select an object")
        self.title.setObjectName("propertyTitle")
        self.title.setWordWrap(True)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("propertySubtitle")
        self.subtitle.setWordWrap(True)
        identity.addWidget(self.title, 0, 1)
        identity.addWidget(self.subtitle, 1, 1)
        identity.setColumnStretch(1, 1)
        self._layout.addWidget(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAccessibleName("Object properties")
        self._layout.addWidget(self.scroll, 1)
        self.set_fields(())

    def set_fields(self, specs, values=None, *, title="", subtitle=""):
        if title:
            self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self.editors, self.specs, self.errors, self.unit_selectors = {}, {}, {}, {}
        self._rows = {}
        body = QWidget()
        body.setObjectName("propertyBody")
        stack = QVBoxLayout(body)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        sections = {}
        for spec in specs:
            name = field(spec, "name")
            label = str(field(spec, "label", name))
            group = str(field(spec, "group", "Properties"))
            if group not in sections:
                sections[group] = _PropertySection(group)
                stack.addWidget(sections[group])
            editor = create_editor(spec, (values or {}).get(name, field(spec, "value")), self.draftChanged.emit)
            self.specs[name], self.editors[name] = spec, editor
            row = _PropertyRow(label, editor, self._unit_widget(name, spec, editor, label))
            sections[group].add_row(row)
            self._rows[name], self.errors[name] = row, row.error
        stack.addStretch(1)
        previous = self.scroll.takeWidget()
        if previous is not None:
            previous.deleteLater()
        self.scroll.setWidget(body)

    def _unit_widget(self, name, spec, editor, label):
        unit = str(field(spec, "unit", ""))
        choices = field(spec, "unit_choices", ())
        if choices:
            selector = QComboBox()
            selector.addItems(list(choices))
            selector.setCurrentText(unit)
            selector.setAccessibleName(f"{label} unit")
            selector.setEnabled(bool(field(spec, "editable", True)))
            scales = dict(field(spec, "unit_scales", ()))
            if scales and isinstance(editor, NumericEdit):
                self._connect_units(name, editor, selector, scales, unit)
            selector.currentTextChanged.connect(self.draftChanged)
            self.unit_selectors[name] = selector
            return selector
        if unit:
            label = QLabel(unit)
            label.setObjectName("unitsNote")
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
            error.setVisible(bool(message))


PropertyPanel = PropertyEditor
