"""Saved-case export and common actions in each actual native presentation."""
import json
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from caelab_prep.application import PrepSession
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.mesh_workflow import SolverExportDialog
from caelab_prep.ui.reference_profiles import PROFILES
from test_condition_workflow import _base_model, _create_conditions

pytestmark = pytest.mark.usefixtures('qt_widgets')


@pytest.mark.parametrize('profile', sorted(PROFILES))
def test_each_presentation_exposes_cases_and_exports_saved_selection(profile, tmp_path):
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / 'input')))
    refs = _create_conditions(session)
    session.create_analysis_case('Load only', [refs['load']], 2, .25, 'ms')
    selected = session.create_analysis_case('Velocity only', [refs['velocity']], 4, .5, 'ms')['case_id']
    native = os.environ.get('CAELAB_TEST_NATIVE_RENDER') == '1'
    window = MainWindow(session, presentation=profile, enable_viewport=native)
    window._allow_close = True; window.resize(1280, 900); window.show()
    QApplication.processEvents()
    assert window.mesh_workflow.cases_action.isEnabled()
    assert window.mesh_workflow.cases_action in window.reference_bindings.commands['Conditions']
    assert window.mesh_workflow.cases_action.associatedObjects()
    assert window.mesh_import.action.isEnabled() and window.mesh_import.action.associatedObjects()
    observed = []
    def inspect_editor():
        dialog = window.mesh_workflow.dialog
        observed.append((dialog.case_list.count(), dialog.status.text()))
        assert dialog.case_list.count() == 2
        if native:
            assert QApplication.instance().platformName() == 'xcb'
            assert QTest.qWaitForWindowExposed(dialog)
            for control in (dialog.name_edit, dialog.end_edit, dialog.conditions, dialog.export_button):
                assert not control.visibleRegion().isEmpty()
            output = Path(os.environ['CAELAB_NATIVE_RENDER_ARTIFACT_DIR'])
            output.mkdir(parents=True, exist_ok=True)
            assert dialog.screen().grabWindow(int(dialog.winId())).save(str(output / f'cases-{profile}.png'))
            (output / f'cases-{profile}.json').write_text(json.dumps({
                'platform': 'xcb', 'scope': 'Prep case editor; QTest input, not Windows or original product',
                'profile': profile, 'selected_case': selected, 'case_count': dialog.case_list.count(),
                'dialog_size': [dialog.width(), dialog.height()]}))
        dialog.reject()
    QTimer.singleShot(0, inspect_editor)
    window.mesh_workflow.cases_action.trigger()
    assert observed and 'Velocity only' in observed[0][1]
    export = SolverExportDialog(session, window)
    assert export.case.currentData() == selected
    assert not export.end.isEnabled() and export.end.text() == '4'
    assert 'ms' in export.hint.text()
    output = tmp_path / 'result' / 'selected_0000.rad'
    export.path.setText(str(output))
    assert export.apply(), export.error.text()
    assert b'/INIVEL/TRA/89' in output.read_bytes() and b'/CLOAD/81' not in output.read_bytes()
    assert '\n0.004\n' in output.with_name('selected_0001.rad').read_text()
    window.close()


def test_export_dialog_rejects_a_case_changed_after_review(tmp_path):
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / 'input')))
    case = session.create_analysis_case('Reviewed', [], .001, .0001, 's')['case_id']
    dialog = SolverExportDialog(session)
    output = tmp_path / 'no-output' / 'stale_0000.rad'
    dialog.path.setText(str(output))
    session.set_analysis_case(case, {'end_time': .002})
    assert not dialog.apply() and not output.exists()
    assert 'changed' in dialog.error.text()
    dialog.reject()


def test_export_case_combo_handles_a_deleted_case_without_signal_exception(tmp_path):
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / 'input')))
    first = session.create_analysis_case('First', [], .001, .0001, 's')['case_id']
    session.create_analysis_case('Second', [], .002, .0001, 's')
    dialog = SolverExportDialog(session)
    session.delete_analysis_case(first)
    dialog.case.setCurrentIndex(dialog.case.findData(first))
    dialog._case_changed()  # Also fail directly if a Qt signal swallowed an exception.
    assert 'changed' in dialog.error.text()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.reject()
