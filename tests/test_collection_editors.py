"""Real Qt collection drafts; reading input never submits a document command."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from caelab_prep.application.contracts import ObjectRef
from caelab_prep.ui.widgets.collections import (
    BooleanVectorEdit, IntegerListEdit, NumericTableEdit, ReferenceListEdit,
)
from caelab_prep.ui.widgets.curve import CurveTable

pytestmark = pytest.mark.usefixtures("qt_widgets")


def test_integer_ids_preserve_unfinished_input_and_reject_lossy_values():
    editor = IntegerListEdit((101, 205))
    assert editor.value() == (101, 205)
    editor.show(); editor.setFocus(); editor.selectAll()
    QTest.keyClicks(editor, "101, 1e")
    with pytest.raises(ValueError, match="positive integer"):
        editor.value()
    assert editor.raw_value() == "101, 1e"
    for text in ("101 101", "1 001", "0", "-2", "1.0", "True", "nan"):
        editor.set_raw_value(text)
        with pytest.raises(ValueError):
            editor.value()
        assert editor.raw_value() == text
    editor.set_raw_value("101, 205 309\t411")
    assert editor.value() == (101, 205, 309, 411)
    editor.set_raw_value(())
    assert editor.value() == ()


def test_boolean_tuple_updates_one_named_component_and_rejects_bad_restore():
    editor = BooleanVectorEdit((True, False, True), components=("TX", "TY", "TZ"))
    changes = []
    editor.draftChanged.connect(lambda: changes.append(editor.value()))
    editor.show(); QApplication.processEvents()
    QTest.mouseClick(editor.editors[1], Qt.MouseButton.LeftButton)
    assert editor.value() == (True, True, True)
    assert changes == [(True, True, True)]
    assert tuple(box.text() for box in editor.editors) == ("TX", "TY", "TZ")
    for invalid in ((True,), (True, 0, False), (True, False, False, False)):
        with pytest.raises(ValueError, match="3 boolean"):
            editor.set_raw_value(invalid)
        assert editor.value() == (True, True, True)
    editor.set_raw_value((False, False, False))
    assert editor.raw_value() == (False, False, False)
    assert changes == [(True, True, True)]  # restoring a draft is not an edit


def test_reference_checks_use_value_identity_and_retain_missing_reference():
    first = ObjectRef("doc", "include-a", "part-a", "rad-card", "/PART/902")
    equal_first = ObjectRef("doc", "include-a", "part-a", "rad-card", "/PART/902")
    second = ObjectRef("doc", "include-b", "part-b", "rad-card", "/PART/902")
    editor = ReferenceListEdit((equal_first,), choices=(first, second),
                               choice_labels=("First include part", "Second include part"))
    assert equal_first is not first and editor.value() == (first,)
    changes = []
    editor.draftChanged.connect(lambda: changes.append(editor.raw_value()))
    editor.list.item(1).setCheckState(Qt.CheckState.Checked)
    assert editor.value() == (first, second) and changes == [(first, second)]
    missing = ObjectRef("doc", "other", "gone", "rad-card", "/PART/999")
    editor.set_raw_value((equal_first, missing))
    assert editor.raw_value() == (first, missing)
    assert editor.list.item(2).text() == "Unavailable: /PART/999"
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    editor.list.item(2).setCheckState(Qt.CheckState.Unchecked)
    assert editor.value() == (first,)


def test_numeric_table_csv_rows_and_failed_paste_are_uncommitted_drafts():
    editor = NumericTableEdit(((0, 0), (1, 10)), components=("Time", "Force"),
                              minimum_rows=2, maximum_rows=3)
    editor.show(); QApplication.processEvents()
    applied = []
    editor.pointsEdited.connect(applied.append)
    assert editor.apply_button.isHidden() and editor.revert_button.isHidden()
    assert editor.table.horizontalHeaderItem(0).text() == "Time"
    assert editor.paste_text("0,0\n0.2,15\n1,20") == ((0., 0.), (.2, 15.), (1., 20.))
    before = editor.raw_value()
    with pytest.raises(ValueError):
        editor.paste_text("0,0\n0.2,unfinished")
    failed = editor.raw_value()
    assert failed["cells"] == before["cells"]
    assert failed["paste"].endswith("unfinished") and failed["paste_error"]
    restored = NumericTableEdit(minimum_rows=2, maximum_rows=3)
    restored.set_raw_value(failed)
    assert restored.raw_value() == failed
    with pytest.raises(ValueError):
        restored.value()
    editor.set_raw_value(before)
    editor.table.setCurrentCell(2, 0)
    QTest.mouseClick(editor.add_button, Qt.MouseButton.LeftButton)
    assert editor.table.rowCount() == 4
    for column, text in enumerate(("2", "30")):
        editor.table.item(3, column).setText(text)
    with pytest.raises(ValueError, match="at most 3"):
        editor.value()
    QTest.mouseClick(editor.remove_button, Qt.MouseButton.LeftButton)
    assert editor.value() == ((0., 0.), (.2, 15.), (1., 20.))
    editor.table.selectAll()
    QTest.mouseClick(editor.remove_button, Qt.MouseButton.LeftButton)
    assert editor.table.rowCount() == 0 and editor.has_draft()
    with pytest.raises(ValueError, match="at least 2"):
        editor.value()
    assert applied == []


def test_outer_table_value_flushes_open_delegate_without_emitting_apply():
    editor = NumericTableEdit(((0, 0), (1, 10)), minimum_rows=2)
    editor.resize(420, 300); editor.show(); QApplication.processEvents()
    item = editor.table.item(1, 1)
    editor.table.setCurrentItem(item)
    editor.table.editItem(item)
    QApplication.processEvents()
    delegate = editor.table.focusWidget()
    assert isinstance(delegate, QLineEdit)
    delegate.selectAll(); QTest.keyClicks(delegate, "27.5")
    applied = []
    editor.pointsEdited.connect(applied.append)
    assert editor.value() == ((0., 0.), (1., 27.5))
    assert applied == []


def test_regular_curve_row_changes_emit_only_on_explicit_apply():
    table = CurveTable(minimum_points=1)
    table.set_points(((0, 1),))
    table.show(); QApplication.processEvents()
    applied = []
    table.pointsEdited.connect(applied.append)
    QTest.mouseClick(table.add_button, Qt.MouseButton.LeftButton)
    assert table.table.rowCount() == 2 and table.has_draft() and not applied
    with pytest.raises(ValueError):
        table.points()
    table.table.item(1, 0).setText("1")
    table.table.item(1, 1).setText("2")
    assert table.apply_changes()
    assert applied == [((0., 1.), (1., 2.))]
