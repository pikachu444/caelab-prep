"""Fixed-topology geometry creates a new input, with fresh admission later."""
from copy import deepcopy
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from caelab_prep.application import PrepSession
from caelab_prep.application.structured_mesh import fork_geometry_recipe, read_recipe_input, validate_recipe_edit
from caelab_prep.application.structured_geometry import MAX_RECIPE_BYTES
from caelab_prep.cae_core import PrepError
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog
from test_recipe_archives import recipe
from test_mesh_workflow_ui import choose


@pytest.mark.parametrize('mode',['quad','hex'])
def test_fork_preserves_original_and_current_divisions_but_is_new_geometry(mode,tmp_path):
    spec=recipe(mode);source=tmp_path/'original.json';raw=json.dumps(spec).encode();source.write_bytes(raw)
    base,origin=read_recipe_input(source);base['divisions']=[4,2]
    if mode=='hex':base['layers']=3
    corners=[[v+1 for v in point] for point in base['corners']]
    vector=[0,0,3] if mode=='hex' else None
    target=tmp_path/'new.json'
    assert fork_geometry_recipe(base,origin,target,corners=corners,vector=vector)==str(target.resolve())
    new,_=read_recipe_input(target)
    expected=deepcopy(base);expected['corners']=corners
    if vector is not None:expected['vector']=vector
    assert new==expected and source.read_bytes()==raw
    with pytest.raises(PrepError):validate_recipe_edit(spec,new)
    for path in (source,target):
        before=path.read_bytes()
        with pytest.raises(FileExistsError):fork_geometry_recipe(base,origin,path,corners=corners,vector=vector)
        assert path.read_bytes()==before


def test_fork_rejects_changed_source_and_serialized_oversize_before_creation(tmp_path):
    spec=recipe();source=tmp_path/'input.json';source.write_text(json.dumps(spec))
    base,origin=read_recipe_input(source);source.write_bytes(source.read_bytes()+b'\n')
    target=tmp_path/'new.json'
    with pytest.raises(PrepError) as error:fork_geometry_recipe(base,origin,target,corners=base['corners'])
    assert error.value.code=='candidate_changed' and not target.exists()
    spec['name']='x'*(MAX_RECIPE_BYTES-220)
    raw=json.dumps(spec,separators=(',',':')).encode();assert len(raw)<=MAX_RECIPE_BYTES
    source.write_bytes(raw);base,origin=read_recipe_input(source)
    with pytest.raises(PrepError,match='serialized'):fork_geometry_recipe(base,origin,target,corners=base['corners'])
    assert not target.exists() and source.read_bytes()==raw


def edit(editor,value):
    editor.selectAll();QTest.keyClicks(editor,str(value))


@pytest.mark.parametrize('mode',['quad','hex'])
def test_geometry_draft_blocks_generation_cancel_preserves_then_fork_retargets(mode,tmp_path,monkeypatch,qt_widgets):
    source=tmp_path/'original.json';raw=json.dumps(recipe(mode)).encode();source.write_bytes(raw)
    session=PrepSession();session.new_document('Input',{'mass':'Mg','length':'mm','time':'s'})
    dialog=MeshCandidateDialog(session,enable_viewport=False)
    choose(dialog.source_kind,'structured_recipe');dialog.source.setText(str(source));assert dialog.load_divisions()
    dialog.show();dialog.geometry_toggle.setChecked(True)
    revision=session.document.revision
    dialog.candidate=SimpleNamespace(quality=SimpleNamespace(passed=True),length_unit='mm',dimension=2 if mode=='quad' else 3)
    dialog.quality.setRowCount(1)
    edit(dialog.geometry_edits[0].editors[0],-.1)
    assert dialog.candidate is None and dialog.quality.rowCount()==0
    assert not dialog.generate_button.isEnabled() and not dialog.generate()
    edit(dialog.division_edits[0][0],4)
    if mode=='hex':edit(dialog.layers,3)
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:('',''))
    assert not dialog.fork_geometry() and dialog._geometry_dirty
    assert dialog.geometry_edits[0].editors[0].numeric_value()==-.1 and dialog.source.text()==str(source)
    target=tmp_path/'fork.json';monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(target),''))
    assert dialog.fork_geometry(),dialog.error.text()
    assert not dialog._geometry_dirty and dialog.generate_button.isEnabled()
    assert dialog.source.text()==str(target.resolve()) and dialog._seed_source.path==str(target.resolve())
    assert dialog.division_edits[0][0].numeric_value()==4
    committed=dialog.geometry_edits[0].editors[0];edit(committed,-.2);committed.revert()
    assert committed.numeric_value()==-.1
    assert not dialog._geometry_dirty and dialog.generate_button.isEnabled()
    assert source.read_bytes()==raw and session.document.revision==revision
    assert dialog.candidate is None and not dialog.adopt_button.isEnabled()
    dialog.reject()


def test_two_patch_divisions_remain_editable_but_geometry_fork_is_unavailable(tmp_path,qt_widgets):
    path=Path(__file__).parents[1]/'scripts/evaluation/structured_f2/holdout-inputs.json'
    spec=next(case['input'] for case in json.loads(path.read_text()) if case['id']=='Q-D2')
    source=tmp_path/'two.json';source.write_text(json.dumps(spec))
    session=PrepSession();session.new_document('Patches',{'mass':'Mg','length':'mm','time':'s'})
    dialog=MeshCandidateDialog(session,enable_viewport=False)
    choose(dialog.source_kind,'structured_recipe');dialog.source.setText(str(source));assert dialog.load_divisions()
    assert len(dialog.division_edits)==2 and dialog.geometry_edits==[]
    assert not dialog.geometry_toggle.isEnabled() and not dialog.fork_geometry()
    edit(dialog.division_edits[0][0],dialog.division_edits[0][0].numeric_value()+1)
    assert not dialog._geometry_dirty and dialog.generate_button.isEnabled()
    dialog.reject()


def test_invalid_geometry_never_opens_the_save_picker(tmp_path,monkeypatch,qt_widgets):
    source=tmp_path/'input.json';source.write_text(json.dumps(recipe()))
    session=PrepSession();session.new_document('Input',{'mass':'Mg','length':'mm','time':'s'})
    dialog=MeshCandidateDialog(session,enable_viewport=False)
    choose(dialog.source_kind,'structured_recipe');dialog.source.setText(str(source));assert dialog.load_divisions()
    dialog.geometry_toggle.setChecked(True)
    edit(dialog.geometry_edits[0].editors[2],1)
    calls=[]
    def no_picker(*args):
        calls.append(True)
        return '', ''
    monkeypatch.setattr(QFileDialog,'getSaveFileName',no_picker)
    assert not dialog.fork_geometry() and dialog._geometry_dirty
    assert calls==[]
    assert dialog.source.text()==str(source) and not list(tmp_path.glob('fork*'))
    dialog.reject()
