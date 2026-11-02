"""Actual CSV files and mouse gestures through the two shared Qt consumers."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import subprocess
import sys

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLineEdit, QMessageBox, QScrollArea, QTabWidget

from caelab_prep.application import PrepSession
from caelab_prep.application.curve_csv import read_curve_csv, write_curve_csv
from caelab_prep.application.neutral import CurveSession
from caelab_prep.ui.gallery import GalleryWindow
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.reference_profiles import PROFILES
from test_common_widgets import wait_operation
from test_condition_workflow import model, _create_conditions, _block

pytestmark = pytest.mark.usefixtures("qt_widgets")


def pump():
    for _ in range(3):
        QApplication.processEvents()


def capture(window, name):
    directory = os.environ.get("CAELAB_CURVE_CAPTURE_DIR")
    if not directory:
        return
    assert QApplication.platformName() == "xcb", "Native evidence requires the X11 platform"
    pump()
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    assert window.screen().grabWindow(0).save(str(destination / f"{name}.png"))


def host(kind, profile=None):
    if kind == "neutral":
        window = GalleryWindow(presentation=profile)
        target = next(n.ref for n in window.session.tree_nodes() if n.ref.kind == "curve")
        window.select_ref(target)
        values = lambda: tuple(map(tuple, window.session.curve_points(target)))
        plot = window.plot
    else:
        session = PrepSession()
        session.open_rad(Path(__file__).resolve().parents[1] / "examples/rad/solid_blocks_0000.rad")
        target = session.create_curve("Editable CSV curve", ((0, 0), (.5, 1), (1, 2)))["card_id"]
        window = MainWindow(session, presentation=profile, enable_viewport=False)
        window.select_card(target)
        values = lambda: tuple(map(tuple, window.provider.properties(window._card_refs[target])[0].value))
        plot = window.curve_plot
    window._allow_close = True
    window.resize(1400, 950)
    window.show()
    if getattr(window, "property_dialog", None) is not None:
        window.edit_properties_action.trigger()
    pump()
    return window, window.curve_table, plot, target, values


def reveal(window, widget):
    bindings = getattr(window, "reference_bindings", None)
    pages = bindings.curve_pages if bindings else None
    if isinstance(pages, QTabWidget):
        pages.setCurrentWidget(widget)
    widget.show()
    pump()
    ancestor = widget.parentWidget()
    while ancestor is not None:
        if isinstance(ancestor, QScrollArea):
            ancestor.ensureWidgetVisible(widget)
        ancestor = ancestor.parentWidget()
    pump()
    assert widget.isVisible()


def preview_response(accepted, callback=None):
    def respond():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog) and dialog.objectName() == "curveCsvPreview"
        if callback:
            callback()
        dialog.accept() if accepted else dialog.reject()
    QTimer.singleShot(0, respond)


def drag(plot, before, after, *, release=True):
    start, end = plot.data_position(*before).toPoint(), plot.data_position(*after).toPoint()
    assert plot.visibleRegion().contains(start), "The point must be reachable in the actual clipped widget"
    assert plot.visibleRegion().contains(end), "The drag target must be reachable without synthetic offscreen input"
    QTest.mousePress(plot, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(plot, end, delay=10)
    if release:
        QTest.mouseRelease(plot, Qt.MouseButton.LeftButton, pos=end)
    return end


@pytest.mark.parametrize("kind", ("neutral", "rad"))
@pytest.mark.parametrize("profile", PROFILES)
def test_csv_real_file_buttons_preview_apply_export_and_drag_one_undo(kind, profile, tmp_path, monkeypatch):
    window, table, plot, target, values = host(kind, profile)
    reveal(window, table)
    points = ((0., 0.), (.5, 1.), (1., 2.))
    source, exported = tmp_path / "입력 curve.csv", tmp_path / "export.csv"
    write_curve_csv(source, points)
    before, revision = values(), window.session.describe()["revision"]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(source), "CSV"))
    preview_response(True, lambda: capture(window, f"{kind}-{profile}-csv-preview"))
    assert table.import_csv_button.isVisible()
    QTest.mouseClick(table.import_csv_button, Qt.MouseButton.LeftButton)
    assert table.points() == points and values() == before
    assert window.session.describe()["revision"] == revision
    # Deliberately make data different even for the new RAD curve.
    table.table.item(1, 1).setText("1.2")
    QTest.mouseClick(table.apply_button, Qt.MouseButton.LeftButton)
    pump()
    committed = values()
    assert committed == ((0., 0.), (.5, 1.2), (1., 2.))
    assert window.session.describe()["revision"] == revision + 1
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(exported), "CSV"))
    QTest.mouseClick(table.export_csv_button, Qt.MouseButton.LeftButton)
    assert read_curve_csv(exported) == committed
    reveal(window, plot)
    revision = window.session.describe()["revision"]
    drag(plot, committed[1], (.6, 1.5))
    pump()
    changed = values()
    assert changed[1] == pytest.approx((.6, 1.5), abs=.03)
    assert changed[0] == committed[0] and changed[2] == committed[2]
    assert window.session.describe()["revision"] == revision + 1
    capture(window, f"{kind}-{profile}-dragged")
    window.undo_action.trigger(); pump()
    assert values() == committed
    window.redo_action.trigger(); pump()
    assert values() == changed
    window.close()


@pytest.mark.parametrize("kind", ("neutral", "rad"))
def test_csv_cancel_invalid_batch_and_document_switch_leave_model_and_draft(kind, tmp_path, monkeypatch):
    window, table, plot, target, values = host(kind)
    before, revision = values(), window.session.describe()["revision"]
    original_draft = table.draft_state()
    source = tmp_path / "points.csv"
    source.write_text("x,y\n0,5\n1,7\n", encoding="utf-8")
    preview_response(False)
    assert not table.import_csv_file(source)
    assert table.draft_state() == original_draft and values() == before
    source.write_text("x,y\n0,5\n1,broken\n", encoding="utf-8")
    with pytest.raises(ValueError):
        table.import_csv_file(source)
    assert table.draft_state() == original_draft and values() == before
    source.write_text("x,y\n1,5\n0,7\n", encoding="utf-8")
    with pytest.raises(ValueError, match="increase"):
        table.import_csv_file(source)
    assert window.session.describe()["revision"] == revision
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    assert not table.import_csv_dialog()
    assert table.draft_state() == original_draft
    source.write_text("x,y\n0,5\n1,7\n", encoding="utf-8")
    preview_response(True, lambda: table.set_points(before))  # context replaced while dialog is open
    with pytest.raises(ValueError, match="changed"):
        table.import_csv_file(source)
    assert values() == before and table.points() == before
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    assert not table.export_csv_dialog() and read_curve_csv(source) == ((0., 5.), (1., 7.))
    with pytest.raises(FileExistsError):
        table.export_csv_file(source)
    assert read_curve_csv(source) == ((0., 5.), (1., 7.))
    window.close()


@pytest.mark.parametrize("kind", ("neutral", "rad"))
def test_drag_cancel_invalid_x_click_and_stale_document_do_not_commit(kind, tmp_path):
    window, table, plot, target, values = host(kind)
    reveal(window, plot)
    before, revision = values(), window.session.describe()["revision"]
    point = before[1]
    end = drag(plot, point, (point[0], (before[0][1] + before[-1][1]) / 2), release=False)
    assert window.session.describe()["revision"] == revision
    with pytest.raises(ValueError, match="Finish"):
        table.points()
    QTest.keyClick(plot, Qt.Key.Key_Escape)
    QTest.mouseRelease(plot, Qt.MouseButton.LeftButton, pos=end)
    assert values() == before and not table.has_draft()
    QTest.mouseClick(plot, Qt.MouseButton.LeftButton, pos=plot.data_position(*point).toPoint())
    assert values() == before and window.session.describe()["revision"] == revision
    # Crossing the adjacent X fails as a whole gesture.
    drag(plot, point, (before[0][0], point[1]))
    assert values() == before and window.session.describe()["revision"] == revision
    end = drag(plot, point, (point[0], before[-1][1]), release=False)
    # An independently replaced document must never receive the old pointer edit.
    if kind == "neutral":
        project = tmp_path / "replacement.caeprep"
        window.session.save_project(project)
        window.session.open_project(project)
    else:
        window.session.new_document("replacement", {"mass": "Mg", "length": "mm", "time": "s"})
    QTest.mouseRelease(plot, Qt.MouseButton.LeftButton, pos=end)
    assert not table._gesture_active and plot._drag is None
    if kind == "neutral":
        assert values() == before
    else:
        assert not window.session.list_cards() or all(c["keyword"] != "/FUNCT/1" for c in window.session.list_cards())
    window.close()


def test_two_rad_curves_keep_load_references_across_csv_project_and_native(model, tmp_path):
    session, source = model
    ids = _create_conditions(session)
    second = session.create_curve("Second curve", ((0, 3), (4, 9)), native_id=64)["card_id"]
    second_load = session.create_load("Second load", ids["fixed"], second, "X", .1, native_id=82)["card_id"]
    window = MainWindow(session, enable_viewport=False)
    window._allow_close = True
    window.show(); pump()
    expected = {}
    for index, curve in enumerate((ids["curve"], second)):
        assert window.select_card(curve)
        points = ((0., index + 1.), (.005 + index, 7.), (2. + index, 4. + index))
        csv = tmp_path / f"native-{index}.csv"
        write_curve_csv(csv, points)
        assert window.curve_table.import_csv_file(csv, confirm=False)
        assert window.curve_table.apply_changes(); pump()
        exported = tmp_path / f"native-export-{index}.csv"
        window.curve_table.export_csv_file(exported)
        assert read_curve_csv(exported) == points
        expected[curve] = points
    project = tmp_path / "rad curves.caeprep"
    assert window.save_project_file(project); wait_operation(window)
    reopened = PrepSession(); reopened.open_project(project)
    assert reopened.condition_values(ids["load"])["curve_id"] == ids["curve"]
    assert reopened.condition_values(second_load)["curve_id"] == second
    output = tmp_path / "native-output" / "curves_0000.rad"
    reopened.export_rad(output)
    raw = output.read_bytes()
    for keyword, card in (("/FUNCT/63", ids["curve"]), ("/FUNCT/64", second)):
        rows = _block(raw, keyword)[1:]
        assert tuple((float(row[:20]), float(row[20:40])) for row in rows) == expected[card]
    assert int(_block(raw, "/CLOAD/81")[1][:10]) == 63
    assert int(_block(raw, "/CLOAD/82")[1][:10]) == 64
    window.close()


def test_two_neutral_curves_csv_work_document_metadata_reference_roundtrip(tmp_path):
    window, table, plot, target, values = host("neutral")
    initial = window.session.resource.snapshot()
    expected = {}
    for index, ref in enumerate(n.ref for n in window.session.tree_nodes() if n.ref.kind == "curve"):
        window.select_ref(ref)
        points = ((0., 5. + index), (.25 + index, 15.), (2. + index, 20. + index))
        source = tmp_path / f"source-{index}.csv"
        write_curve_csv(source, points)
        assert table.import_csv_file(source, confirm=False)
        assert table.apply_changes(); pump()
        exported = tmp_path / f"export-{index}.csv"
        table.export_csv_file(exported)
        expected[ref.object_id] = read_curve_csv(exported)
    project = tmp_path / "material curve.caeprep"
    assert window.save_project_file(project); wait_operation(window)
    reopened = CurveSession(); reopened.open_project(project)
    state = reopened.resource.snapshot()
    assert state["material"]["reference_curve"] == initial["material"]["reference_curve"]
    for key, curve in state["curves"].items():
        assert tuple(map(tuple, curve["points"])) == expected[key]
        assert (curve["x_unit"], curve["y_unit"], curve["name"]) == tuple(initial["curves"][key][v] for v in ("x_unit", "y_unit", "name"))
    # Reopen in a new Qt-only process; forbid VTK and native solver imports.
    script = """import sys
class Guard:
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('vtk', 'caelab_prep.radioss')): raise RuntimeError(fullname)
sys.meta_path.insert(0, Guard())
from caelab_prep.application.neutral import CurveSession
from caelab_prep.application.curve_csv import read_curve_csv
s=CurveSession();s.open_project(sys.argv[1]); assert len(s.resource.snapshot()['curves'])==2
from PySide6.QtWidgets import QApplication
from caelab_prep.ui.gallery import GalleryWindow
a=QApplication([]);w=GalleryWindow(s);w._allow_close=True;w.close()
"""
    result = subprocess.run([sys.executable, "-c", script, str(project)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    window.close()


def test_csv_export_new_name_race_requires_explicit_overwrite_confirmation(tmp_path, monkeypatch):
    window, table, plot, target, values = host("neutral")
    output = tmp_path / "created-elsewhere.csv"
    calls = []
    def choose(*args, **kwargs):
        assert not output.exists()
        output.write_text("unconfirmed concurrent file", encoding="utf-8")
        return str(output), "CSV"
    def answer(parent, title, *args):
        calls.append(title)
        return QMessageBox.StandardButton.Ok if title.startswith("Export") else QMessageBox.StandardButton.No
    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    monkeypatch.setattr(QMessageBox, "question", answer)
    assert not table.export_csv_dialog()
    assert calls == ["Export displayed curve values", "Replace CSV file?"]
    assert output.read_text(encoding="utf-8") == "unconfirmed concurrent file"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(output), "CSV"))
    monkeypatch.setattr(QMessageBox, "question", lambda parent, title, *args:
                        QMessageBox.StandardButton.Ok if title.startswith("Export") else QMessageBox.StandardButton.Yes)
    assert table.export_csv_dialog()
    assert read_curve_csv(output) == values()
    window.close()


def test_x11_actual_csv_file_choosers_preview_and_overwrite_cancel(tmp_path):
    if QApplication.platformName() != "xcb":
        pytest.skip("Actual X11 file dialogs are checked in the native GUI environment")
    window, table, plot, target, values = host("neutral")
    source, output = tmp_path / "실제 input.csv", tmp_path / "existing.csv"
    points = ((0., 2.), (.4, 6.), (1., 4.))
    write_curve_csv(source, points)
    output.write_bytes(b"preserve until explicitly replaced")
    errors = []

    def drive(steps):
        pending = list(steps)
        attempts = [0]
        def next_dialog():
            dialog = QApplication.activeModalWidget()
            if dialog is None:
                attempts[0] += 1
                if attempts[0] < 200:
                    QTimer.singleShot(10, next_dialog)
                    return
                errors.append("Expected file/confirmation dialog never appeared")
                return
            action = pending.pop(0)
            try:
                action(dialog)
            except Exception as exc:
                errors.append(repr(exc)); dialog.reject()
                return
            if pending:
                QTimer.singleShot(30, next_dialog)
        QTimer.singleShot(30, next_dialog)
        return pending

    def choose(dialog, path):
        assert isinstance(dialog, QFileDialog)
        dialog.setDirectory(str(path.parent)); pump()
        name = dialog.findChild(QLineEdit, "fileNameEdit")
        assert name is not None
        name.setText(path.name)
        capture(window, "file-dialog-" + ("import" if path == source else "export"))
        dialog.accept()

    def answer(dialog, button):
        assert isinstance(dialog, QMessageBox)
        dialog.button(button).click()

    def preview(dialog):
        assert dialog.objectName() == "curveCsvPreview"
        capture(window, "actual-file-preview")
        dialog.accept()

    before = values()
    pending = drive((lambda d: choose(d, source), preview))
    table.import_csv_button.click()
    assert not pending and not errors
    assert values() == before and table.points() == points
    table.apply_button.click(); pump()
    assert values() == points
    for overwrite in (False, True):
        pending = drive((lambda d: answer(d, QMessageBox.StandardButton.Ok),
                         lambda d: choose(d, output),
                         lambda d: answer(d, QMessageBox.StandardButton.Yes if overwrite else QMessageBox.StandardButton.No)))
        table.export_csv_button.click()
        assert not pending and not errors
        if not overwrite:
            assert output.read_bytes() == b"preserve until explicitly replaced"
    assert read_curve_csv(output) == points
    window.close()
