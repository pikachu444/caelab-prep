"""Regress the real 16,645-node selection loss and atomic input rejection."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.widgets.collections import IntegerListEdit
from test_condition_workflow import _base_model, _block, _card

pytestmark = pytest.mark.usefixtures("qt_widgets")


def paste(editor, value):
    QApplication.clipboard().setText(value)
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()


def test_paste_and_programmatic_restore_keep_every_original_reproduction_id():
    members = tuple(range(1, 16646))
    raw = ", ".join(map(str, members))
    assert len(raw) > 32767
    editor = IntegerListEdit(); editor.show()
    paste(editor, raw)
    assert editor.text() == raw and editor.value() == members
    restored = IntegerListEdit(members)
    assert restored.value() == members and restored.text() == raw
    restored.set_raw_value(editor.raw_value())
    assert restored.value() == members


@pytest.mark.parametrize("path", ["keyboard_paste", "paste_slot", "context_paste", "ime", "typed", "drop"])
def test_overflow_is_rejected_as_a_whole_for_real_qt_input_paths(path):
    editor = IntegerListEdit("11 22", maximum_bytes=7)
    editor.resize(300, 35); editor.show(); editor.setFocus()
    QApplication.processEvents()
    original = editor.text()
    # A partial selection exposes the particularly dangerous 'replace then
    # truncate' path: neither the selected IDs nor any other text may be lost.
    editor.setSelection(0, 2)
    incoming = "1234567890" * 10
    if path == "keyboard_paste":
        paste(editor, incoming)
    elif path == "paste_slot":
        QApplication.clipboard().setText(incoming); editor.paste()
    elif path == "context_paste":
        QApplication.clipboard().setText(incoming)
        menu = editor.createStandardContextMenu()
        action = next(item for item in menu.actions() if item.text().replace("&", "").startswith("Paste"))
        action.trigger()
    elif path == "ime":
        event = QInputMethodEvent(); event.setCommitString(incoming)
        QApplication.sendEvent(editor, event)
    elif path == "typed":
        editor.set_raw_value("11 2222"); editor.deselect(); editor.setCursorPosition(7)
        original = editor.text()
        QTest.keyClick(editor, Qt.Key.Key_3)
    else:
        mime = QMimeData(); mime.setText(incoming)
        drag = QDragEnterEvent(QPoint(5, 10), Qt.DropAction.CopyAction, mime,
                               Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(editor, drag)
        assert drag.isAccepted()
        drop = QDropEvent(QPointF(5, 10), Qt.DropAction.CopyAction, mime,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(editor, drop)
    assert editor.text() == original
    with pytest.raises(ValueError, match="entire edit was rejected"):
        editor.value()
    draft = editor.raw_value()
    other = IntegerListEdit(maximum_bytes=7); other.set_raw_value(draft)
    assert other.raw_value() == draft and other.text() == original
    with pytest.raises(ValueError, match="entire edit was rejected"):
        other.value()
    editor.set_raw_value(original)
    assert editor.value() == tuple(map(int, original.split()))


def test_utf8_limit_rejects_whole_non_ascii_ime_and_keeps_preedit_out_of_data():
    editor = IntegerListEdit("11", maximum_bytes=7); editor.show(); editor.setFocus()
    # Display composition is not an accepted numeric draft or document edit.
    QApplication.sendEvent(editor, QInputMethodEvent("가", []))
    assert editor.text() == "11"
    event = QInputMethodEvent(); event.setCommitString("가나")
    QApplication.sendEvent(editor, event)
    assert editor.text() == "11"
    with pytest.raises(ValueError, match="entire edit was rejected"): editor.value()
    editor.set_raw_value("11")
    event = QInputMethodEvent(); event.setCommitString(" 22")
    QApplication.sendEvent(editor, event)
    assert editor.value() == (11, 22)


def test_invalid_restore_raises_before_changing_text_draft_or_cursor():
    editor = IntegerListEdit("11 22", maximum_bytes=7); editor.setSelection(0, 2)
    before = (editor.raw_value(), editor.cursorPosition(), editor.selectedText())
    for value in ("1 " * 10, (111, 222, 333), {"text": "1 " * 10, "input_error": "previous failure"}):
        with pytest.raises(ValueError, match="existing IDs are unchanged"): editor.set_raw_value(value)
        assert (editor.raw_value(), editor.cursorPosition(), editor.selectedText()) == before
    with pytest.raises(ValueError, match="existing IDs are unchanged"): editor.setText("1 " * 10)
    assert editor.value() == (11, 22)


def test_actual_group_create_export_and_undo_preserve_all_16645_ids(tmp_path):
    source = _base_model(tmp_path / "input")
    geometry = source.parent / "mesh.inc"
    shells = "/SHELL/" + geometry.read_text().split("/SHELL/", 1)[1]
    members = tuple(range(1, 16646))
    geometry.write_text("/NODE\n" + "".join(f"{i:10d}{float(i):20.12g}{0.:20.12g}{0.:20.12g}\n" for i in members) + shells)
    session = PrepSession(); session.open_rad(source)
    window = MainWindow(session, enable_viewport=False); window._allow_close = True
    window.show(); QApplication.processEvents()
    before = session.describe()["revision"]
    window.modeling.actions["group.create"].trigger()
    panel = window.modeling.panel
    panel.editor.editors["name"].setText("All physical nodes")
    panel.editor.editors["native_id"].setText("47")
    editor = panel.editor.editors["node_ids"]
    paste(editor, ", ".join(map(str, members)))
    assert editor.value() == members and session.describe()["revision"] == before
    QTest.mouseClick(panel.apply_button, Qt.MouseButton.LeftButton); QApplication.processEvents()
    assert not window.modeling.active, panel.error.text()
    group = _card(session, "/GRNOD/NODE/47")
    assert session.describe()["revision"] == before + 1
    output = tmp_path / "output" / "group_0000.rad"
    session.export_rad(output)
    rows = _block(output.read_bytes(), "/GRNOD/NODE/47")[1:]
    saved = tuple(int(row[i:i+10]) for row in rows for i in range(0, len(row), 10) if row[i:i+10].strip())
    assert saved == members
    session.undo(); assert all(item["id"] != group["id"] for item in session.list_cards())
    session.redo(); assert session.card_text(group["id"])

    # Exercise the real production limit, not a reduced host/test-only limit.
    window.modeling.actions["group.create"].trigger(); QApplication.processEvents()
    panel = window.modeling.panel; editor = panel.editor.editors["node_ids"]
    panel.editor.editors["name"].setText("Rejected oversized batch")
    editor.set_raw_value((1, 2)); before = session.describe()["revision"]
    paste(editor, "1" * (IntegerListEdit.MAX_INPUT_BYTES + 10))
    assert editor.text() == "1, 2"
    QTest.mouseClick(panel.apply_button, Qt.MouseButton.LeftButton); QApplication.processEvents()
    assert window.modeling.active and "rejected" in panel.error.text().lower()
    assert session.describe()["revision"] == before
    QTest.mouseClick(panel.cancel_button, Qt.MouseButton.LeftButton)
    assert session.describe()["revision"] == before
    window.close()
