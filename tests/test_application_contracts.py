"""Shared public commands, atomic edits and independent document codecs."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from caelab_prep.application.contracts import PropertyHost, SetProperties
from caelab_prep.application.neutral import CurveSession
from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts/evaluation/models/two_shell_plates_0000.rad"


def test_neutral_units_vector_and_invalid_atomic_edit():
    session = CurveSession()
    assert isinstance(session, PropertyHost)
    material = session.tree_nodes()[0].ref
    initial = session.describe()
    session.submit(SetProperties(material, {"young_modulus": 205, "direction": [0, 1, 0]}, 0,
                                 {"young_modulus": "GPa"}))
    fields = {spec.name: spec.value for spec in session.properties(material)}
    assert fields["young_modulus"] == 205000 and fields["direction"] == [0, 1, 0]
    session.undo()
    assert not session.describe()["dirty"]
    assert {spec.name: spec.value for spec in session.properties(material)}["young_modulus"] == 210000
    session.redo()
    before = session.describe()
    values = session.resource.snapshot()
    for command in [
        SetProperties(material, {"density": 1, "poisson_ratio": .9}, before["revision"]),
        SetProperties(material, {"density": "1e"}, before["revision"]),
        SetProperties(material, {"density": float("nan")}, before["revision"]),
        SetProperties(material, {"density": 1}, initial["revision"]),
        SetProperties(material, {"density": 1}, before["revision"], {"density": "MPa"}),
        SetProperties(replace(material, resource_id="missing"), {"density": 1}, before["revision"]),
    ]:
        with pytest.raises(PrepError):
            session.submit(command)
        assert session.describe() == before
        assert session.resource.snapshot() == values


def test_curve_batch_is_one_history_entry_and_reopens_without_rad(tmp_path):
    session = CurveSession()
    curve = session.tree_nodes()[1].ref
    old_points = session.curve_points(curve)
    edited = [[0, 255], [.025, 320], [.09, 400], [.2, 470]]
    session.set_curve_points(curve, edited, session.describe()["revision"])
    assert session.curve_points(curve) == edited
    session.undo()
    assert session.curve_points(curve) == old_points
    session.redo()
    before = session.describe()
    with pytest.raises(PrepError):
        session.set_curve_points(curve, [[0, 100], [0, 200]], before["revision"])
    assert session.describe() == before
    project = tmp_path / "재료 곡선.caeprep"
    session.save_project(project)
    code = """
import importlib.abc, json, sys
class NoSolver(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('caelab_prep.radioss', 'PySide6', 'vtk', 'caelab_prep.application.session')):
            raise AssertionError('forbidden import: ' + fullname)
sys.meta_path.insert(0, NoSolver())
from caelab_prep.application.neutral import CurveSession
s=CurveSession(); s.open_project(sys.argv[1])
ref=s.tree_nodes()[1].ref
print(json.dumps({'points':s.curve_points(ref),'revision':s.describe()['revision'],'dirty':s.describe()['dirty']}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(project)], check=True, capture_output=True, text=True)
    state = json.loads(result.stdout)
    assert state == {"points": edited, "revision": before["revision"], "dirty": False}


def test_neutral_save_failure_and_malformed_open_preserve_model(tmp_path, monkeypatch):
    from caelab_prep.application import storage
    session = CurveSession()
    project = tmp_path / "curve.caeprep"
    session.save_project(project)
    original = project.read_bytes()
    material = session.tree_nodes()[0].ref
    session.submit(SetProperties(material, {"density": 8000}, 0))
    before = session.describe()
    def fail(_fd):
        raise OSError("simulated sync failure")
    with monkeypatch.context() as patch:
        patch.setattr(storage.os, "fsync", fail)
        with pytest.raises(PrepError) as error:
            session.save_project(project)
    assert error.value.code == "project_write_error"
    assert project.read_bytes() == original and session.describe() == before
    assert not list(tmp_path.glob(".caeprep-*"))
    malformed = tmp_path / "bad.caeprep"
    with zipfile.ZipFile(project) as saved, zipfile.ZipFile(malformed, "w") as output:
        manifest = json.loads(saved.read("manifest.json")); manifest["document_id"] = 123
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("material-curves.json", saved.read("material-curves.json"))
    with pytest.raises(PrepError) as error:
        session.open_project(malformed)
    assert error.value.code == "invalid_project" and session.describe() == before
    with pytest.raises(PrepError):
        CurveSession({})


def test_rad_batch_no_partial_change_and_single_undo():
    session = PrepSession(); session.open_rad(FIXTURE)
    card = next(c for c in session.list_cards() if c["keyword"].startswith("/MAT/"))
    original = session.card_fields(card["id"])
    session.set_fields(card["id"], {"density": 8e-9, "young_modulus": 205000}, 0,
                       expected_document_id=session.describe()["document_id"], expected_resource_id=card["resource_id"])
    assert session.describe()["revision"] == 1
    session.undo()
    assert session.card_fields(card["id"]) == original
    assert not session.describe()["can_undo"]
    before = session.describe()
    for kwargs in [
        {"values": {"density": 1, "young_modulus": -1}},
        {"values": {"density": 1}, "expected_document_id": "old"},
        {"values": {"density": 1}, "expected_resource_id": "other"},
        {"values": {"density": 1}, "expected_revision": 0},
    ]:
        with pytest.raises(PrepError):
            session.set_fields(card["id"], **kwargs)
        assert session.describe() == before and session.card_fields(card["id"]) == original


def test_contract_imports_have_no_gui_solver_or_gallery_dependency():
    code = """
import importlib.abc, sys
class Fence(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('PySide6','vtk','caelab_prep.radioss','caelab_prep.ui','caelab_prep.application.session')):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Fence())
from caelab_prep.application.contracts import DocumentSession
from caelab_prep.application.neutral import CurveSession
assert isinstance(CurveSession().describe()['revision'],int)
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)


def test_shared_qt_imports_do_not_load_rad_or_vtk():
    code = """
import importlib.abc, sys
class Fence(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.startswith(('vtk','caelab_prep.radioss','caelab_prep.application.session','caelab_prep.application.rad_provider','caelab_prep.ui.main_window')):
            raise AssertionError(fullname)
sys.meta_path.insert(0,Fence())
from caelab_prep.ui.gallery import GalleryWindow
from caelab_prep.ui.widgets import NumericEdit, CurvePlot
from caelab_prep.ui.shell import FileTask
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
