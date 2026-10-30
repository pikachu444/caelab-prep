"""Grouped property presentation; host providers own meaning and commits."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout,
                              QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget)

from .numeric import NumericEdit, VectorEdit
from .tree import field


class PropertyEditor(QWidget):
    draftChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editors = {}
        self.specs = {}
        self.errors = {}
        self.unit_selectors = {}
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 9, 10, 9)
        self._layout.setSpacing(7)
        self.title = QLabel("Select an object")
        self.title.setObjectName("propertyTitle")
        self.title.setWordWrap(True)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("propertySubtitle")
        self.subtitle.setWordWrap(True)
        self._layout.addWidget(self.title)
        self._layout.addWidget(self.subtitle)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self._layout.addWidget(self.scroll, 1)
        self.set_fields(())

    def set_fields(self, specs, values=None, *, title="", subtitle=""):
        if title:
            self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.editors, self.specs, self.errors, self.unit_selectors = {}, {}, {}, {}
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 3, 0, 0)
        layout.setSpacing(10)
        groups = {}
        for spec in specs:
            name = field(spec, "name")
            self.specs[name] = spec
            group = field(spec, "group", "Properties")
            if group not in groups:
                heading = QLabel(str(group))
                heading.setObjectName("groupTitle")
                layout.addWidget(heading)
                form = QFormLayout()
                form.setContentsMargins(0, 0, 0, 0)
                form.setHorizontalSpacing(8)
                form.setVerticalSpacing(7)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
                form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
                layout.addLayout(form)
                groups[group] = form
            value = (values or {}).get(name, field(spec, "value"))
            kind = field(spec, "kind", "number")
            unit = field(spec, "unit", "")
            if kind in ("number", "integer"):
                editor = NumericEdit(value, unit=unit, minimum=field(spec, "minimum"),
                                     maximum=field(spec, "maximum"), integer=kind == "integer")
                editor.draftChanged.connect(self.draftChanged)
            elif kind == "vector":
                editor = VectorEdit(value, unit=unit, components=field(spec, "components") or ("X", "Y", "Z"))
                editor.draftChanged.connect(self.draftChanged)
            elif kind == "bool":
                editor = QCheckBox()
                editor.setChecked(bool(value))
                editor.toggled.connect(self.draftChanged)
            elif kind == "choice":
                editor = QComboBox()
                for choice in field(spec, "choices", ()):
                    editor.addItem(str(choice), choice)
                editor.setCurrentIndex(editor.findData(value))
                editor.currentIndexChanged.connect(self.draftChanged)
            else:
                editor = QLineEdit(str(value if value is not None else ""))
                editor.textEdited.connect(self.draftChanged)
            label_text = str(field(spec, "label", name))
            editor.setAccessibleName(label_text)
            editor.setEnabled(bool(field(spec, "editable", True)))
            self.editors[name] = editor
            wrapper = QWidget()
            row = QVBoxLayout(wrapper)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            input_row = QHBoxLayout()
            input_row.setContentsMargins(0, 0, 0, 0)
            input_row.setSpacing(5)
            input_row.addWidget(editor, 1)
            units = field(spec, "unit_choices", ())
            if units:
                selector = QComboBox()
                selector.addItems(list(units))
                selector.setCurrentText(unit)
                selector.setAccessibleName(f"{label_text} unit")
                selector.setEnabled(bool(field(spec, "editable", True)))
                scales = dict(field(spec, "unit_scales", ()))
                if scales and isinstance(editor, NumericEdit):
                    self._connect_units(name, editor, selector, scales, unit)
                selector.currentTextChanged.connect(self.draftChanged)
                self.unit_selectors[name] = selector
                input_row.addWidget(selector)
            elif unit:
                unit_label = QLabel(str(unit))
                unit_label.setObjectName("unitsNote")
                unit_label.setWordWrap(True)
                input_row.addWidget(unit_label)
            row.addLayout(input_row)
            error = QLabel()
            error.setWordWrap(True)
            error.setObjectName("inputError")
            error.hide()
            self.errors[name] = error
            row.addWidget(error)
            label = QLabel(label_text)
            label.setWordWrap(True)
            label.setBuddy(editor)
            groups[group].addRow(label, wrapper)
        layout.addStretch()
        previous = self.scroll.takeWidget()
        if previous:
            previous.deleteLater()
        self.scroll.setWidget(body)

    def values(self):
        values, failure = {}, None
        for name, editor in self.editors.items():
            if not field(self.specs[name], "editable", True):
                continue
            try:
                if isinstance(editor, (NumericEdit, VectorEdit)):
                    value = editor.numeric_value()
                elif isinstance(editor, QCheckBox):
                    value = editor.isChecked()
                elif isinstance(editor, QComboBox):
                    value = editor.currentData()
                else:
                    value = editor.text()
                self.set_error(name, "")
                values[name] = value
            except ValueError as exc:
                self.set_error(name, str(exc))
                failure = failure or exc
        if failure:
            raise failure
        return values

    def units(self):
        return {name: selector.currentText() for name, selector in self.unit_selectors.items()}

    def _connect_units(self, name, editor, selector, scales, initial_unit):
        previous = initial_unit
        def change_unit(unit):
            nonlocal previous
            try:
                editor.convert_display(scales[previous] / scales[unit])
            except (ValueError, KeyError) as exc:
                selector.blockSignals(True)
                selector.setCurrentText(previous)
                selector.blockSignals(False)
                self.set_error(name, str(exc))
                return
            previous = unit
            editor.unit = unit
            self.set_error(name, "")
        selector.currentTextChanged.connect(change_unit)

    def set_error(self, name, message):
        editor = self.editors.get(name)
        if hasattr(editor, "set_error"):
            editor.set_error(message)
        error = self.errors.get(name)
        if error:
            error.setText(str(message))
            error.setVisible(bool(message))

    def raw_values(self):
        return {name: tuple(e.text() for e in editor.editors) if isinstance(editor, VectorEdit)
                else editor.text() if isinstance(editor, QLineEdit)
                else editor.isChecked() if isinstance(editor, QCheckBox)
                else editor.currentData() for name, editor in self.editors.items()}


PropertyPanel = PropertyEditor
