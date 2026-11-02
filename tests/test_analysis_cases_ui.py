import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog

from caelab_prep.application import PrepSession
from caelab_prep.ui.analysis_cases import AnalysisCasesDialog
from test_condition_workflow import _base_model, _create_conditions

pytestmark = pytest.mark.usefixtures("qt_widgets")


def test_dialog_creates_two_persisted_cases_and_undo_refreshes(tmp_path):
    app = QApplication.instance() or QApplication([])
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / "input")))
    refs = _create_conditions(session)
    dialog = AnalysisCasesDialog(session); dialog.show(); app.processEvents()
    for name, end, target in (("Load", ".002", refs["load"]), ("Velocity", ".003", refs["velocity"])):
        dialog.new_button.click()
        dialog.name_edit.setText(name); dialog.end_edit.setText(end); dialog.interval_edit.setText(".0005")
        for row in range(dialog.conditions.rowCount()):
            item = dialog.conditions.item(row, 0)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) == target else Qt.CheckState.Unchecked)
        dialog.apply_button.click(); app.processEvents()
        assert session.analysis_case()["name"] == name
    assert len(session.analysis_cases()["cases"]) == 2
    dialog.case_list.setCurrentRow(0); dialog.use_button.click()
    assert session.analysis_case()["name"] == "Load"
    session.undo(); app.processEvents()
    assert session.analysis_case()["name"] == "Velocity"
    dialog.name_edit.setText("Pending")
    before = session.analysis_cases()
    session.create_curve("Other edit", [(0, 0), (1, 1)])
    dialog.apply_button.click(); app.processEvents()
    assert session.analysis_cases()["cases"] == before["cases"]
    assert "changed" in dialog.status.text().lower()
    dialog._dirty = False; dialog.reject()


def test_replacing_document_disables_case_editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / "input")))
    dialog = AnalysisCasesDialog(session)
    session.new_document("Replacement", {"mass": "Mg", "length": "mm", "time": "s"})
    app.processEvents()
    assert not dialog.apply_button.isEnabled() and not dialog.export_button.isEnabled()
    dialog.reject()


def test_file_picker_case_edit_cannot_export_unreviewed_settings(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / "input")))
    case = session.create_analysis_case("Reviewed", [], .001, .0005, "s")["case_id"]
    dialog = AnalysisCasesDialog(session)
    output = tmp_path / "out" / "case_0000.rad"
    def choose(*args, **kwargs):
        session.set_analysis_case(case, {"end_time": .002})
        app.processEvents()  # Refreshes dialog._revision while picker is open.
        return str(output), "Radioss"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    dialog.export_button.click()
    assert not output.exists()
    assert "changed" in dialog.status.text().lower()
    dialog.reject()
