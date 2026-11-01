"""Preserved typed-draft bindings for the rebuilt native presentation."""

from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit

from .numeric import NumericEdit, VectorEdit
from .tree import field


def create_editor(spec, value, changed):
    kind, unit = field(spec, "kind", "number"), field(spec, "unit", "")
    if kind in ("number", "integer"):
        editor = NumericEdit(value, unit=unit, minimum=field(spec, "minimum"),
                             maximum=field(spec, "maximum"), integer=kind == "integer")
        editor.draftChanged.connect(changed)
    elif kind == "vector":
        editor = VectorEdit(value, unit=unit, components=field(spec, "components") or ("X", "Y", "Z"))
        editor.draftChanged.connect(changed)
    elif kind == "bool":
        editor = QCheckBox()
        editor.setChecked(bool(value))
        editor.toggled.connect(changed)
    elif kind in ("choice", "reference"):
        editor = QComboBox()
        labels = field(spec, "choice_labels", ())
        for index, choice in enumerate(field(spec, "choices", ())):
            label = labels[index] if index < len(labels) else str(field(choice, "object_id", choice))
            editor.addItem(label, choice)
        editor.setCurrentIndex(editor.findData(value))
        editor.currentIndexChanged.connect(changed)
    else:
        editor = QLineEdit(str(value if value is not None else ""))
        editor.textEdited.connect(changed)
    editor.setAccessibleName(str(field(spec, "label", field(spec, "name"))))
    editor.setEnabled(bool(field(spec, "editable", True)))
    return editor


def editor_value(editor):
    if isinstance(editor, (NumericEdit, VectorEdit)):
        return editor.numeric_value()
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    if isinstance(editor, QComboBox):
        return editor.currentData()
    return editor.text()


def editor_raw_value(editor):
    if isinstance(editor, VectorEdit):
        return tuple(component.text() for component in editor.editors)
    if isinstance(editor, QLineEdit):
        return editor.text()
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    return editor.currentData()


def bind_units(editor, selector, scales, initial_unit, report_error):
    previous = initial_unit

    def change_unit(unit):
        nonlocal previous
        try:
            editor.convert_display(scales[previous] / scales[unit])
        except (ValueError, KeyError) as exc:
            selector.blockSignals(True)
            selector.setCurrentText(previous)
            selector.blockSignals(False)
            report_error(str(exc))
            return
        previous = unit
        editor.unit = unit
        report_error("")

    selector.currentTextChanged.connect(change_unit)
