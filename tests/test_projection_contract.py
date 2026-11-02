import json
from pathlib import Path

import pytest

from caelab_prep.application import PrepSession

FIXTURE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/two_shell_plates_0000.rad"


def test_geometry_is_nested_readonly_shared_and_mutable_copy_is_explicit():
    session = PrepSession(); session.open_rad(FIXTURE)
    first, again = session.mesh_view(), session.mesh_view()
    assert first is not again
    for key in ("points", "node_ids", "cells", "node_resources", "diagnostics"):
        assert first[key] is again[key]
    for change in (lambda: first["points"][0].__setitem__(0, 77),
                   lambda: first["cells"][0].__setitem__("id", 77),
                   lambda: first["cells"][0]["part_ref"].__setitem__("resource_id", "other"),
                   lambda: first["node_resources"].__setitem__(1, ("other",))):
        with pytest.raises((TypeError, AttributeError)): change()
    detached = session.mesh_view(mutable=True)
    assert json.loads(json.dumps(detached))["node_ids"] == list(first["node_ids"])
    detached["points"][0][0] = 77
    detached["cells"][0]["nodes"].clear()
    assert session.mesh_view()["points"][0][0] == first["points"][0][0]
    assert session.mesh_view()["cells"][0]["nodes"]


def test_scalar_stamps_change_without_geometry_allocation_and_structure_invalidates():
    session = PrepSession(); session.open_rad(FIXTURE)
    first = session.mesh_view()
    material = next(card for card in session.list_cards() if card["keyword"] == "/MAT/PLAS_TAB/1")
    session.set_field(material["id"], "young_modulus", 190000)
    scalar = session.mesh_view()
    assert scalar["cells"] is first["cells"] and scalar["points"] is first["points"]
    assert scalar["revision"] == first["revision"] + 1
    assert scalar["resource_revisions"] != first["resource_revisions"]
    assert scalar["projection_revision"] == first["projection_revision"]
    session.create_node_group("Selection", [first["node_ids"][0]])
    structure = session.mesh_view()
    assert structure["cells"] is not scalar["cells"]
    assert structure["projection_revision"] > scalar["projection_revision"]
    session.undo()
    assert session.mesh_view()["cells"] is not structure["cells"]
    epoch = session.mesh_view()["document_epoch"]
    session.open_rad(FIXTURE)
    assert session.mesh_view()["document_epoch"] != epoch
