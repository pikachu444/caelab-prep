"""Offscreen request/save/reopen UI checks; no mesh or native renderer."""
import os
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from caelab_prep.application import PrepSession
from caelab_prep.application.meshing_criteria import MeshingCriteria
from caelab_prep.application.washer_controls import read_washer_control_draft
from caelab_prep.ui.geometry_features import GeometryFeaturesDialog
from caelab_prep.ui.washer_controls import WasherControlsDialog
from test_geometry_features_ui import inspection
from test_geometry_features import hole
from test_cylindrical_blends import blend_evidence, persist
from test_external_mesh_ui import pump

pytestmark = pytest.mark.usefixtures("qt_widgets")


def configured(inspection, tmp_path):
    parent = GeometryFeaturesDialog(enable_viewport=False)
    assert parent.present_inspection(inspection)
    dialog = WasherControlsDialog(inspection, parent.report["features"][0], length_tolerance=1e-6, parent=parent)
    assert dialog.width() >= dialog.minimumWidth()
    profile = tmp_path/"criteria.json"
    MeshingCriteria("mm", 1.5, .25, fillet_suppression_threshold=.1).save(profile)
    assert dialog.load_profile(profile)
    dialog.opening.setCurrentIndex(1); dialog.family.setCurrentIndex(1); dialog.layers.setCurrentIndex(2)
    dialog.radial_width.setText("0.5"); dialog.divisions.setText("16")
    return parent, dialog, profile


def test_explicit_opening_controls_save_and_reopen_preserve_profile_and_document(inspection, tmp_path):
    session = PrepSession(); before = session.describe()
    parent, dialog, profile = configured(inspection, tmp_path)
    second = None
    original = profile.read_bytes()
    try:
        draft = dialog.review()
        assert draft["criteria"]["washer_element_family"] == "quad"
        assert draft["criteria"]["target_size"] == 1.5 and draft["criteria"]["minimum_size"] == .25
        assert draft["criteria"]["fillet_suppression_threshold"] == .1
        assert draft["radial_layer_radii"] == [1., 1.25, 1.5]
        assert "unavailable" in dialog.status.text()
        path = tmp_path/"controls.washer.json"
        assert dialog.save_draft(path) and read_washer_control_draft(path) == dialog.draft
        second = WasherControlsDialog(inspection, parent.report["features"][0], length_tolerance=1e-6)
        assert second.open_draft(path)
        assert second.opening.currentData() == draft["opening_surface_uuid"]
        assert second.family.currentData() == "quad" and second.layers.currentData() == 2
        assert second.radial_width.numeric_value() == .5 and second.divisions.numeric_value() == 16
        assert second.draft == dialog.draft
        assert profile.read_bytes() == original and session.describe() == before
        assert not dialog.save_draft(profile) and profile.read_bytes() == original
        assert not second.save_draft(profile) and profile.read_bytes() == original
        alias = tmp_path/"profile-alias.json"; os.link(profile, alias)
        assert not second.save_draft(alias) and profile.read_bytes() == original
        other = tmp_path/"other-profile.json"; MeshingCriteria("mm", 2., .5).save(other)
        assert dialog.load_profile(other)
        dialog.family.setCurrentIndex(1); dialog.layers.setCurrentIndex(2)
        dialog.radial_width.setText(".5"); dialog.divisions.setText("16")
        assert dialog.review()
        assert not dialog.save_draft(profile) and profile.read_bytes() == original
    finally:
        if second: second.reject()
        dialog.reject(); parent.reject()


def test_missing_profile_opening_and_explicit_element_family_cannot_save(inspection, tmp_path):
    parent = GeometryFeaturesDialog(enable_viewport=False); parent.present_inspection(inspection)
    dialog = WasherControlsDialog(inspection, parent.report["features"][0], length_tolerance=1e-6)
    path = tmp_path/"controls.json"
    try:
        assert dialog.review() is None and "profile" in dialog.error.text()
        profile = tmp_path/"criteria.json"; MeshingCriteria("mm", 1.5, .25).save(profile)
        assert dialog.load_profile(profile)
        assert dialog.family.currentData() is None and dialog.layers.currentData() is None
        dialog.radial_width.setText(".5"); dialog.divisions.setText("16")
        assert not dialog.save_draft(path) and not path.exists()
        dialog.family.setCurrentIndex(2); dialog.layers.setCurrentIndex(1)
        assert dialog.review() is None
        dialog.opening.setCurrentIndex(1)
        assert dialog.review()["criteria"]["washer_element_family"] == "tria"
    finally:
        dialog.reject(); parent.reject()


def test_user_edit_invalidates_review_and_save_revalidates(inspection, tmp_path):
    parent, dialog, _ = configured(inspection, tmp_path)
    try:
        assert dialog.review()
        dialog.show(); pump(); dialog.radial_width.setFocus(); pump()
        dialog.radial_width.selectAll(); QTest.keyClicks(dialog.radial_width, "invalid")
        assert dialog.draft is None and "No mesh" in dialog.status.text()
        path = tmp_path/"must-not-save.json"
        assert not dialog.save_draft(path) and not path.exists()
        QTest.keyClick(dialog.radial_width, Qt.Key.Key_Escape); pump()
        assert dialog.radial_width.numeric_value() == .5 and dialog.draft is None
    finally:
        dialog.reject(); parent.reject()


def test_parent_button_requires_a_current_hole_selection_and_blends_have_no_washer(inspection, tmp_path, monkeypatch):
    parent = GeometryFeaturesDialog(enable_viewport=False)
    try:
        assert parent.present_inspection(inspection) and parent.washer_button.isEnabled()
        seen = []
        monkeypatch.setattr("caelab_prep.ui.washer_controls.WasherControlsDialog",
            lambda *args, **kwargs: type("Review", (), {"exec": lambda self: seen.append((args, kwargs))})())
        assert parent.open_washer_controls() and len(seen) == 1
        assert seen[0][0][0] is inspection and seen[0][1]["length_tolerance"] == 1e-6
        parent.table.clearSelection()
        assert not parent.washer_button.isEnabled() and not parent.open_washer_controls()
        data, metadata = blend_evidence(tmp_path)
        assert parent.present_inspection(persist(data, metadata))
        assert not parent.washer_button.isEnabled() and not parent.open_washer_controls()
    finally:
        parent.reject()


def test_changed_assets_invalidate_draft_before_save(inspection, tmp_path):
    parent, dialog, _ = configured(inspection, tmp_path)
    try:
        assert dialog.review()
        Path(inspection.assets[0].path).write_bytes(b"changed")
        path = tmp_path/"stale.json"
        assert not dialog.save_draft(path) and not path.exists() and dialog.draft is None
    finally:
        dialog.reject(); parent.reject()
