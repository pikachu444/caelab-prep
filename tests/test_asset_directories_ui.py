"""Default worker asset paths are usable drafts and still explicitly clearable."""
from pathlib import Path

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.ui.geometry_features import GeometryFeaturesDialog
from caelab_prep.ui.mesh_import import ImportMeshDialog
from caelab_prep.ui.mesh_workflow import MeshCandidateDialog


@pytest.mark.usefixtures("qt_widgets")
@pytest.mark.parametrize("kind", ["geometry", "mesh", "import"])
def test_asset_path_defaults_are_unique_lazy_and_clearable(kind):
    session = PrepSession()
    session.new_document("Asset defaults", {"mass": "Mg", "length": "mm", "time": "s"})
    def create():
        if kind == "geometry":
            return GeometryFeaturesDialog(enable_viewport=False)
        cls = MeshCandidateDialog if kind == "mesh" else ImportMeshDialog
        return cls(session, enable_viewport=False)
    first, second = create(), create()
    path = Path(first.output.text())
    assert path.is_absolute() and not path.exists()
    assert first.output.text() != second.output.text()
    first.source.setText("source.step" if kind != "import" else "source.msh")
    first.output.clear()
    if kind == "mesh":
        first.size.setText("2")
        assert not first.generate()
    else:
        assert not first.inspect()
    assert first.error.text() and first._task is None
    first.reject(); second.reject()
