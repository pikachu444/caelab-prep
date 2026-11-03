"""The existing mesh window uses archived adoption inputs without a new editor."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog

from caelab_prep.application import PrepSession
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog
from test_recipe_archives import archive_resource, recipe, resource_states
from test_mesh_workflow_ui import choose

pytestmark = pytest.mark.usefixtures("qt_widgets")


def owner(mode):
    session = PrepSession(); session.new_document("Stored inputs", {"mass":"Mg", "length":"mm", "time":"s"})
    archive = archive_resource(mode=mode)
    session.dispatcher.execute_many({}, "Attach stored generation input", additions=(archive,))
    return session, archive


@pytest.mark.parametrize("mode", ["quad", "hex"])
def test_project_recipe_loads_exact_input_and_requires_new_generation(mode, tmp_path, monkeypatch):
    session, archive = owner(mode)
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    choose(dialog.source_kind, "structured_recipe")
    before, revision = resource_states(session), session.document.revision
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (args[3][0], True))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    assert dialog.open_project_recipe(), dialog.error.text()
    assert Path(dialog.source.text()).read_bytes() == archive.files["recipe"]
    assert (Path(dialog.source.text()).parent / "source_recipe.json").read_bytes() == archive.files["source_recipe"]
    assert [edit.numeric_value() for edit in dialog.division_edits[0]] == [4,2]
    if mode == "hex": assert dialog.layers.numeric_value() == 2
    assert dialog.candidate is None and dialog.quality.rowCount() == 0 and not dialog.adopt_button.isEnabled()
    assert "Generate a new candidate" in dialog.summary.text()
    assert resource_states(session) == before and session.document.revision == revision
    dialog.reject()


@pytest.mark.parametrize("cancel", ["choice", "directory", "document", "same_document"])
def test_cancel_or_changed_document_preserves_input_draft(cancel, tmp_path, monkeypatch):
    import json
    session, archive = owner("quad")
    project = tmp_path / "original.caeprep"; session.save_project(project)
    source = tmp_path / "draft.json"; source.write_text(json.dumps(recipe()))
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    choose(dialog.source_kind, "structured_recipe"); dialog.source.setText(str(source))
    assert dialog.load_divisions()
    dialog.division_edits[0][0].setText("3")
    before = (dialog.source.text(),dialog.output.text(),dialog.division_edits[0][0].text())
    def choice(*args):
        if cancel in ("document", "same_document"):
            session.new_document("Different", {"mass":"Mg", "length":"mm", "time":"s"})
            if cancel == "same_document": session.open_project(project)
        return args[3][0], cancel != "choice"
    monkeypatch.setattr(QInputDialog, "getItem", choice)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: "" if cancel=="directory" else str(tmp_path))
    assert not dialog.open_project_recipe()
    assert (dialog.source.text(),dialog.output.text(),dialog.division_edits[0][0].text()) == before
    assert not list(tmp_path.glob("recipe-*"))
    dialog.reject()


def test_partial_extraction_failure_does_not_replace_the_input_draft(tmp_path, monkeypatch):
    import json
    session, _ = owner("quad")
    source = tmp_path / "draft.json"; source.write_text(json.dumps(recipe()))
    dialog = MeshCandidateDialog(session, enable_viewport=False)
    choose(dialog.source_kind, "structured_recipe"); dialog.source.setText(str(source))
    assert dialog.load_divisions()
    before = (dialog.source.text(),dialog.output.text(),dialog._seed_recipe)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (args[3][0], True))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    opened = Path.open
    def fail_second(path, *args, **kwargs):
        if path.name == "source_recipe.json" and path.parent.name.startswith("recipe-"):
            raise OSError("injected second-file extraction error")
        return opened(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail_second)
    assert not dialog.open_project_recipe()
    assert "Could not extract" in dialog.error.text()
    assert (dialog.source.text(),dialog.output.text(),dialog._seed_recipe) == before
    children = list(tmp_path.glob("recipe-*"))
    assert len(children) == 1 and (children[0] / "recipe.json").exists()
    assert not (children[0] / "source_recipe.json").exists()
    dialog.reject()
