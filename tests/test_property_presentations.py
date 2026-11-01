"""The same Qt-only inspector in an independent host with its own Apply/history."""

import os
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget, QVBoxLayout, QWidget

from caelab_prep.ui.widgets.properties import PropertyEditor


MODES = ("columns", "grid", "settings", "form", "tabs")
SPECS = (
    dict(name="modulus", label="긴 한글 탄성계수 이름과 재료 방향", value=210000,
         unit="MPa", unit_choices=("MPa", "GPa"), unit_scales=(("MPa", 1), ("GPa", 1000)),
         group="Material"),
    dict(name="ratio", label="Poisson ratio", value=0.3, minimum=0, maximum=0.5, group="Material"),
    dict(name="direction", label="Direction", kind="vector", value=(1, 0, 0), group="Orientation"),
    dict(name="name", label="Name", kind="text", value="한글 재료 이름 " * 8, group="Material"),
    dict(name="unit_text", label="Thermal expansion", value=1.2e-5,
         unit="millimetres per metre per kelvin", group="Material"),
)


class ExistingApplyService:
    """A stand-in for a host's existing configuration service, without Prep state."""

    def __init__(self):
        self.values = {spec["name"]: spec["value"] for spec in SPECS}
        self.history = []

    def apply(self, values, units):
        candidate = dict(values)
        candidate["modulus"] *= {"MPa": 1, "GPa": 1000}[units["modulus"]]
        self.history.append(self.values)
        self.values = candidate

    def undo(self):
        self.values = self.history.pop()


class IndependentHost(QWidget):
    def __init__(self, mode):
        super().__init__()
        self.service = ExistingApplyService()
        self.selection = "existing-study-variable"
        self.properties = PropertyEditor(self)
        QVBoxLayout(self).addWidget(self.properties)
        self.properties.set_presentation(mode)
        self.properties.set_fields(SPECS, title="한글 속성 대상", subtitle="Existing study configuration")

    def apply(self):
        try:
            values = self.properties.values()
        except ValueError:
            return False
        self.service.apply(values, self.properties.units())
        return True


@pytest.fixture
def hosts(qt_app):
    created = []

    def create(mode="columns", width=450):
        host = IndependentHost(mode)
        created.append(host)
        host.resize(width, 520)
        host.show()
        qt_app.processEvents()
        return host

    yield create
    for host in created:
        host.close()
        host.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("mode", MODES)
def test_independent_host_validation_units_and_one_apply_undo(hosts, mode):
    host = hosts(mode)
    panel = host.properties
    original = dict(host.service.values)
    panel.editors["modulus"].setText("1e")
    panel.unit_selectors["modulus"].setCurrentText("GPa")
    assert panel.unit_selectors["modulus"].currentText() == "MPa"
    assert panel.raw_values()["modulus"] == "1e"
    panel.editors["ratio"].setText("0.4")
    assert not host.apply()
    assert host.service.values == original and host.service.history == []
    panel.editors["modulus"].setText("205000")
    panel.unit_selectors["modulus"].setCurrentText("GPa")
    assert panel.raw_values()["modulus"] == "205"
    assert host.service.history == []
    assert host.apply()
    assert host.service.values["modulus"] == 205000
    assert host.service.values["ratio"] == 0.4
    assert len(host.service.history) == 1
    host.service.undo()
    assert host.service.values == original
    assert host.selection == "existing-study-variable"


@pytest.mark.parametrize("mode", ("columns", "grid"))
def test_header_drag_keeps_draft_focus_selection_cursor_and_host_history(hosts, mode):
    host = hosts(mode)
    panel = host.properties
    editor = panel.editors["modulus"]
    editor.setFocus()
    editor.selectAll()
    QTest.keyClicks(editor, "123456.78")
    editor.setSelection(2, 4)
    finished = []
    changed = []
    editor.editingFinished.connect(lambda: finished.append(True))
    panel.draftChanged.connect(lambda: changed.append(True))
    before = (panel.raw_values(), editor.cursorPosition(), editor.selectionStart(), editor.selectedText())
    header = panel.column_header
    x = header.sectionViewportPosition(0) + header.sectionSize(0) - 1
    start = QPoint(x, header.height() // 2)
    QTest.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(header.viewport(), start + QPoint(65, 0), 20)
    QTest.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(65, 0))
    QApplication.processEvents()
    assert header.sectionSize(0) > x + 20
    assert QApplication.focusWidget() is editor
    assert (panel.raw_values(), editor.cursorPosition(), editor.selectionStart(), editor.selectedText()) == before
    assert finished == changed == []
    assert host.service.history == [] and host.selection == "existing-study-variable"
    width = header.sectionSize(0)
    panel.set_fields(SPECS)
    QApplication.processEvents()
    assert header.sectionSize(0) == width


def test_columns_align_missing_units_and_scroll_with_header(hosts):
    host = hosts(width=270)
    panel = host.properties
    panel.column_header.resizeSection(0, 185)
    panel.column_header.resizeSection(1, 190)
    panel.column_header.resizeSection(2, 110)
    QApplication.processEvents()
    assert panel.scroll.horizontalScrollBar().maximum() > 0
    panel.scroll.horizontalScrollBar().setValue(75)
    QApplication.processEvents()
    assert panel.column_header.offset() == 75
    rows = panel.findChildren(QWidget, "propertyRow")
    for row in rows:
        for index, cell in enumerate((row.label, row.value_cell, row.unit_cell)):
            x = cell.mapTo(panel.scroll.viewport(), QPoint()).x()
            assert x == panel.column_header.sectionViewportPosition(index)
            assert cell.width() == panel.column_header.sectionSize(index)
    assert panel.editors["name"].text() == SPECS[3]["value"]
    unit = next(label for label in panel.findChildren(QLabel)
                if label.text() == "millimetres per metre per kelvin")
    assert unit.toolTip() == unit.text() and unit.wordWrap()


def test_errors_mark_rows_and_show_only_focused_detail_including_vector_child(hosts):
    panel = hosts().properties
    panel.editors["modulus"].setText("1e")
    panel.editors["ratio"].setText("8")
    panel.editors["direction"].editors[1].setText("NaN")
    with pytest.raises(ValueError):
        panel.values()
    assert sum(bool(error.text()) for error in panel.errors.values()) == 3
    assert all(error.isHidden() for error in panel.errors.values())
    assert all(panel.editors[name].property("invalid") for name in ("modulus", "ratio"))
    panel.editors["ratio"].setFocus()
    QApplication.processEvents()
    assert "Poisson ratio" in panel.error_detail.text()
    panel.editors["direction"].editors[1].setFocus()
    QApplication.processEvents()
    assert "Direction" in panel.error_detail.text()
    assert panel.error_detail.height() <= 58
    panel.editors["modulus"].setText("210000")
    panel.editors["ratio"].setText("0.3")
    panel.editors["direction"].editors[1].setText("0")
    panel.values()
    assert panel.error_detail.isHidden()
    assert panel.edit_state.text() != "Invalid draft"


def test_presentation_adapters_recompose_same_drafts_without_committing(hosts):
    panel = hosts().properties
    editor = panel.editors["modulus"]
    editor.setText("1e")
    editor.setFocus()
    finished = []
    editor.editingFinished.connect(lambda: finished.append(True))
    for mode in (*MODES[1:], "columns"):
        panel.set_presentation(mode)
        QApplication.processEvents()
        assert panel.editors["modulus"] is editor and editor.text() == "1e"
        assert QApplication.focusWidget() is editor
        assert panel.column_header.isVisible() == (mode in ("columns", "grid"))
        tabs = panel.scroll.widget().findChild(QTabWidget)
        assert (tabs is not None) == (mode == "tabs")
        if tabs is not None:
            assert [tabs.tabText(i) for i in range(tabs.count())] == ["Material", "Orientation"]
    assert finished == []
    with pytest.raises(ValueError, match="Unknown property presentation"):
        panel.set_presentation("unknown")


@pytest.mark.parametrize("width", (450, 270))
def test_tab_single_rows_keep_natural_height_and_long_labels_wrap(hosts, width):
    panel = hosts("tabs", width=width).properties
    panel.set_fields((
        dict(name="name", label="Name", kind="text", value="긴 한글 재료 이름", group="Properties"),
        dict(name="modulus", label="긴 한글 탄성계수 이름과 재료 방향 " * 3,
             value=210000, group="Elastic material"),
    ))
    QApplication.processEvents()
    tabs = panel.scroll.widget().findChild(QTabWidget)
    for index, name in enumerate(("name", "modulus")):
        tabs.setCurrentIndex(index)
        panel.set_error(name, "Check this draft")
        QApplication.processEvents()
        editor = panel.editors[name]
        row = editor.parentWidget().parentWidget()
        label = row.findChild(QLabel, "propertyLabel")
        editor_rect = editor.geometry().translated(editor.parentWidget().pos())
        assert label.y() < 10
        assert editor_rect.top() - label.geometry().bottom() <= 8
        assert row.height() - editor_rect.bottom() <= 10
        assert label.height() >= label.heightForWidth(label.width())
        if name == "name":
            assert row.height() < 100
        assert panel.errors[name].isHidden() and panel.error_detail.isVisible()


def test_widget_import_needs_no_prep_document_session_or_history():
    code = """
import builtins
original = builtins.__import__
def isolated(name, *args, **kwargs):
    if any(part in name for part in ('cae_core', 'application', 'radioss', 'main_window', 'vtk')):
        raise AssertionError('Unexpected host dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = isolated
from PySide6.QtWidgets import QApplication, QWidget
from caelab_prep.ui.widgets.properties import PropertyEditor
app = QApplication([])
host = QWidget()
panel = PropertyEditor(host)
panel.set_fields([dict(name='value', value=3)])
assert panel.values() == {'value': 3.0}
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=os.environ)
    assert result.returncode == 0, result.stderr
