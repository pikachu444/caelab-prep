"""Atomic display-only unit conversion; model commits remain host-owned."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from caelab_prep.ui.widgets.numeric import NumericEdit, VectorEdit

pytestmark = pytest.mark.usefixtures("qt_widgets")


def state(editor):
    return (editor.text(), editor._committed_text, editor.minimum, editor.maximum,
            editor.isModified(), editor.cursorPosition(), editor.selectionStart(),
            editor.selectedText(), editor.unit, editor.error, editor.toolTip(),
            editor.accessibleDescription())


def test_scalar_unit_conversion_preserves_native_draft_flag_and_scales_limits():
    editor = NumericEdit(210000, unit="MPa", minimum=0, maximum=300000)
    editor.show(); editor.setFocus(); editor.selectAll()
    QTest.keyClicks(editor, "205000")
    assert editor.isModified()
    committed = []
    changed = []
    editor.editingFinished.connect(lambda: committed.append(True))
    editor.draftChanged.connect(lambda: changed.append(True))
    editor.convert_display(.001)
    assert editor.text() == "205" and editor._committed_text == "210"
    assert editor.numeric_value() == 205
    assert editor.minimum == 0 and editor.maximum == 300
    assert editor.isModified() and not committed and not changed
    editor.unit = "GPa"
    assert editor.toolTip() == "GPa" and editor.accessibleDescription() == "GPa"
    editor.revert()
    assert editor.text() == "210" and not editor.isModified()
    editor.convert_display(1000)
    assert editor.text() == "210000" and not editor.isModified()
    assert editor.maximum == 300000


@pytest.mark.parametrize("factor", [0, -1, float("nan"), float("inf"), -float("inf"), True, "invalid"])
def test_bad_factor_changes_no_scalar_or_vector_state(factor):
    scalar = NumericEdit(12, unit="mm", minimum=0, maximum=100)
    scalar.setSelection(0, 1); scalar.setModified(True)
    vector = VectorEdit((1, 2, 3), unit="mm")
    vector.editors[1].setText("1e"); vector.editors[1].setModified(True)
    scalar_before = state(scalar)
    vector_before = tuple(state(e) for e in vector.editors)
    with pytest.raises(ValueError, match="finite positive"):
        scalar.convert_display(factor)
    with pytest.raises(ValueError, match="finite positive"):
        vector.convert_display(factor)
    assert state(scalar) == scalar_before
    assert tuple(state(e) for e in vector.editors) == vector_before


@pytest.mark.parametrize("failure", ["draft", "committed", "maximum", "minimum", "intermediate"])
def test_scalar_failed_conversion_keeps_text_baseline_bounds_and_modified(failure):
    editor = NumericEdit(5, unit="mm", minimum=-100, maximum=100)
    factor = 10
    if failure == "draft":
        editor.maximum = None
        editor.setText("1e308")
    elif failure == "committed":
        editor._committed_text = "1e308"
    elif failure == "maximum":
        editor.maximum = 1e308
    elif failure == "minimum":
        editor.minimum = -1e308
    else:
        editor.setText("1e")
    editor.setModified(True); editor.setSelection(0, 1)
    before = state(editor)
    with pytest.raises(ValueError):
        editor.convert_display(factor)
    assert state(editor) == before


def test_vector_conversion_validates_all_components_before_mutation():
    vector = VectorEdit((1000, 2000, 3000), unit="mm/s")
    for index, editor in enumerate(vector.editors):
        editor.minimum, editor.maximum = -4000, 4000
        editor.setModified(index != 1)
    events = []
    vector.draftChanged.connect(lambda: events.append("draft"))
    for editor in vector.editors:
        editor.editingFinished.connect(lambda: events.append("commit"))
        editor.textChanged.connect(lambda: events.append("partial text"))
    vector.convert_display(.001)
    assert vector.numeric_value() == (1, 2, 3)
    assert tuple(editor.isModified() for editor in vector.editors) == (True, False, True)
    assert all((editor.minimum, editor.maximum) == (-4, 4) for editor in vector.editors)
    assert tuple(editor._committed_text for editor in vector.editors) == ("1", "2", "3")
    assert not events
    vector.unit = "m/s"
    assert vector.unit == "m/s" and vector.toolTip() == "m/s"
    assert all(editor.unit == "m/s" and editor.toolTip() == "m/s" for editor in vector.editors)
    assert all(editor.accessibleDescription() == "m/s" for editor in vector.editors)
    vector.editors[1].set_error("Enter a valid number")
    vector.unit = "cm/s"
    assert vector.editors[1].unit == "cm/s"
    assert vector.editors[1].toolTip() == "Enter a valid number"


@pytest.mark.parametrize("last_value", ["1e", "1e308"])
def test_late_invalid_vector_component_rolls_back_every_component(last_value):
    vector = VectorEdit((1, 2, 3), unit="mm")
    vector.editors[0].setText("4.500"); vector.editors[0].setModified(True)
    vector.editors[0].setSelection(1, 2)
    vector.editors[1].minimum, vector.editors[1].maximum = 0, 10
    vector.editors[2].setText(last_value); vector.editors[2].setModified(True)
    before = tuple(state(e) for e in vector.editors)
    with pytest.raises(ValueError):
        vector.convert_display(10)
    assert tuple(state(e) for e in vector.editors) == before
    assert vector.unit == "mm"


def test_integer_conversion_rejects_fractional_result_without_partial_state():
    scalar = NumericEdit(1, integer=True, minimum=0, maximum=10)
    before = state(scalar)
    with pytest.raises(ValueError, match="fractional"):
        scalar.convert_display(.5)
    assert state(scalar) == before
    scalar.convert_display(2)
    assert scalar.numeric_value() == 2 and scalar.maximum == 20


def test_conversion_keeps_empty_revert_baseline_and_round_trip_precision():
    editor = NumericEdit(None, unit="m")
    editor.setText("1.234567890123456"); editor.setModified(True)
    original = editor.numeric_value()
    editor.convert_display(1000)
    assert editor.numeric_value() == original * 1000
    assert editor._committed_text == "" and editor.isModified()
    editor.convert_display(.001)
    assert editor.numeric_value() == pytest.approx(original, rel=1e-15)
    editor.revert()
    assert editor.text() == ""


def test_underflow_does_not_silently_zero_a_nonzero_draft():
    vector = VectorEdit((1, 2, 1e-300))
    before = tuple(state(e) for e in vector.editors)
    with pytest.raises(ValueError, match="underflow"):
        vector.convert_display(1e-100)
    assert tuple(state(e) for e in vector.editors) == before


def test_new_quantity_blank_baseline_allows_typed_value_but_not_invalid_baseline():
    editor = NumericEdit(None, unit="N")
    editor.show(); editor.setFocus()
    blank = state(editor)
    with pytest.raises(ValueError, match="valid number"):
        editor.convert_display(.001)
    assert state(editor) == blank
    QTest.keyClicks(editor, "2500")
    assert editor.isModified()
    editor.convert_display(.001)
    editor.unit = "kN"
    assert editor.text() == "2.5" and editor._committed_text == ""
    assert editor.isModified()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert editor.text() == "" and not editor.isModified()
    QTest.keyClicks(editor, "3.5")
    editor._committed_text = "1e"
    before = state(editor)
    with pytest.raises(ValueError, match="valid number"):
        editor.convert_display(1000)
    assert state(editor) == before
