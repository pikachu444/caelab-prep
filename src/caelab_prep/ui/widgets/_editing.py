"""Preserved typed-draft bindings for the rebuilt native presentation."""

import math
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QWidget

from .numeric import NumericEdit, VectorEdit
from .tree import field
from .collections import IntegerListEdit, BooleanVectorEdit, ReferenceListEdit, NumericTableEdit

_COLLECTION_EDITORS = (IntegerListEdit, BooleanVectorEdit, ReferenceListEdit, NumericTableEdit)


class ReferenceComboBox(QComboBox):
    """Qt's opaque Python user data compares identity, but references use value identity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Qualified references belong in the popup/tooltip, not in the minimum
        # width of every row in the inspector. The editor still expands to use
        # all of the space that its host provides.
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(10)
        self.currentTextChanged.connect(self.setToolTip)

    def findData(self, data, role=Qt.ItemDataRole.UserRole,
                 flags=Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchCaseSensitive):
        if role == Qt.ItemDataRole.UserRole:
            for index in range(self.count()):
                if self.itemData(index, role) == data:
                    return index
            return -1
        return super().findData(data, role, flags)


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
    elif kind in ("integer_list", "bool_vector", "references", "table"):
        if kind == "integer_list":
            editor = IntegerListEdit(value)
        elif kind == "bool_vector":
            editor = BooleanVectorEdit(value, components=field(spec, "components") or ("X", "Y", "Z"))
        elif kind == "references":
            editor = ReferenceListEdit(value, choices=field(spec, "choices", ()),
                                       choice_labels=field(spec, "choice_labels", ()))
        else:
            editor = NumericTableEdit(value, components=field(spec, "components") or ("X", "Y"),
                                      minimum_rows=field(spec, "minimum_rows", 0),
                                      maximum_rows=field(spec, "maximum_rows"))
        editor.draftChanged.connect(changed)
    elif kind in ("choice", "reference"):
        editor = ReferenceComboBox() if kind == "reference" else QComboBox()
        labels = field(spec, "choice_labels", ())
        for index, choice in enumerate(field(spec, "choices", ())):
            label = labels[index] if index < len(labels) else str(field(choice, "object_id", choice))
            editor.addItem(label, choice)
            editor.setItemData(index, label, Qt.ItemDataRole.ToolTipRole)
        editor.setCurrentIndex(editor.findData(value))
        editor.currentIndexChanged.connect(changed)
    else:
        editor = QLineEdit(str(value if value is not None else ""))
        editor.textEdited.connect(changed)
    editor.setAccessibleName(str(field(spec, "label", field(spec, "name"))))
    editor.setEnabled(bool(field(spec, "editable", True)))
    return editor


def editor_value(editor):
    if isinstance(editor, _COLLECTION_EDITORS):
        return editor.value()
    if isinstance(editor, (NumericEdit, VectorEdit)):
        return editor.numeric_value()
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    if isinstance(editor, QComboBox):
        return editor.currentData()
    return editor.text()


def editor_raw_value(editor):
    if isinstance(editor, _COLLECTION_EDITORS):
        return editor.raw_value()
    if isinstance(editor, VectorEdit):
        return tuple(component.text() for component in editor.editors)
    if isinstance(editor, QLineEdit):
        return editor.text()
    if isinstance(editor, QCheckBox):
        return editor.isChecked()
    return editor.currentData()


def restore_editor_raw_value(editor, raw):
    """Restore a typed draft without firing any host commit callbacks."""
    blocked = [QSignalBlocker(widget) for widget in (editor, *editor.findChildren(QWidget))]
    if isinstance(editor, _COLLECTION_EDITORS):
        editor.set_raw_value(raw)
        if isinstance(editor, QLineEdit):
            editor.setModified(True)
    elif isinstance(editor, VectorEdit):
        for child, value in zip(editor.editors, raw):
            child.setText(str(value))
            child.setModified(True)
    elif isinstance(editor, QLineEdit):
        editor.setText(str(raw))
        editor.setModified(True)
    elif isinstance(editor, QCheckBox):
        editor.setChecked(raw)
    elif isinstance(editor, QComboBox):
        editor.setCurrentIndex(editor.findData(raw))
    del blocked


def bind_units(editor, selector, scales, initial_unit, report_error):
    previous = initial_unit

    def change_unit(unit):
        nonlocal previous
        try:
            if selector.property("unitChoiceRequired"):
                if unit not in scales:
                    return
                # A new physical quantity has no prior value to convert. Only
                # bounds are expressed in the explicitly chosen display unit.
                factor = scales[previous] / scales[unit]
                components = editor.editors if isinstance(editor, VectorEdit) else (editor,)
                bounds = [(child, {name: getattr(child, name) * factor if getattr(child, name) is not None else None
                                   for name in ("minimum", "maximum")}) for child in components]
                if any(value is not None and not math.isfinite(value) for _, values in bounds for value in values.values()):
                    raise ValueError("The selected unit exceeds the supported numeric range")
                for child, values in bounds:
                    for name, value in values.items():
                        setattr(child, name, value)
                selector.setProperty("unitChoiceRequired", False)
                previous = unit
                editor.unit = unit
                report_error("")
                return
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
