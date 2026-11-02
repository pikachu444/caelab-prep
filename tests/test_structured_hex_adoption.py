"""Explicit sweep hex8 crosses the existing command/codec/native boundary."""

from collections import Counter
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from caelab_prep.application.structured_mesh import generate_structured_mesh
from caelab_prep.cae_core.errors import PrepError
from test_mesh_adoption import _session, _state
from test_structured_adoption import _native


@pytest.fixture(scope="module", params=["H-N3", "H-D2"])
def sweep(request, tmp_path_factory):
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable; no sweep adoption execution claim")
    cases = json.loads((Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json").read_text(encoding="utf-8"))
    case = next(item for item in cases if item["id"] == request.param)
    folder = tmp_path_factory.mktemp(request.param)
    source = folder / "original recipe.json"
    source.write_text(json.dumps(case["input"]), encoding="utf-8")
    native = generate_structured_mesh(case["input"], folder / "assets", recipe_path=source).to_native_mesh()
    assert len(native.elements) == case["expectation"]["elements"]
    return case, native


def test_sweep_adoption_undo_codec_and_exact_brick_connectivity(sweep, tmp_path):
    from caelab_prep.radioss.relations import node_support
    case, native = sweep
    original = {asset.path: Path(asset.path).read_bytes() for asset in native.assets}
    session, material, prop = _session(native, native.length_unit)
    before = _state(session)[1]
    revision = session.describe()["revision"]
    result = session.adopt_mesh_candidate(native, material_id=material, property_id=prop,
        expected_document_id=session.document.id, expected_revision=revision,
        expected_document_epoch=session.describe()["document_epoch"])
    assert session.describe()["revision"] == revision + 1
    after = _state(session)[1]
    session.undo(); assert _state(session)[1] == before
    session.redo(); assert _state(session)[1] == after
    support = node_support(session._deck_resources(), session.mesh_view(), result["node_id_map"].values())
    assert len(support) == len(native.nodes)
    assert all(row["translations"] and row["status"] == "supported" and row["formulations"] == ["BRICK"] for row in support)
    for write in (session.save_project, session.export_rad):
        with pytest.raises(PrepError) as error:
            write(next(asset.path for asset in native.assets if asset.kind == "recipe"))
        assert error.value.code == "source_overwrite"
    project = tmp_path / "sweep.caeprep"
    session.save_project(project)
    output = tmp_path / "new-process/sweep_0000.rad"
    process = subprocess.run([sys.executable, "-m", "caelab_prep", "export", str(project), "--output", str(output)],
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    nodes, elements, parts, groups = _native(output.read_bytes())
    assert len(nodes) == case["expectation"]["active_nodes"]
    assert len(elements) == case["expectation"]["elements"]
    assert set(parts.values()) == {(207, 41)}
    target_parts = {source: int(next(card["keyword"] for card in session.list_cards() if card["id"] == target).split("/")[2])
                    for source, target in result["part_id_map"].items()}
    for node in native.nodes:
        assert nodes[result["node_id_map"][node.id]] == pytest.approx(node.xyz, rel=1e-12, abs=1e-12)
    for cell in native.elements:
        assert elements[result["element_id_map"][cell.id]] == (
            target_parts[cell.part_uuid], tuple(result["node_id_map"][node] for node in cell.node_ids))
    for group in native.groups:
        keyword = next(card["keyword"] for card in session.list_cards() if card["id"] == result["group_id_map"][group.key])
        mapping = result["node_id_map"] if group.kind == "node" else result["element_id_map"]
        assert keyword.startswith("/GRNOD/NODE/" if group.kind == "node" else "/GRBRIC/BRIC/")
        assert groups[keyword] == tuple(mapping[node] for node in group.member_ids)
    if len(parts) == 2:
        memberships = [set(n for owner, conn in elements.values() if owner == part for n in conn) for part in parts]
        assert len(memberships[0] & memberships[1]) == case["expectation"]["shared_nodes"]
        faces = ((0,1,2,3), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7))
        exterior = []
        for part in parts:
            counts = Counter(tuple(sorted(conn[i] for i in face)) for owner, conn in elements.values() if owner == part for face in faces)
            exterior.append({face for face, count in counts.items() if count == 1})
        assert len(exterior[0] & exterior[1]) == case["expectation"]["shared_boundary_cells"]
    assert all(Path(path).read_bytes() == raw for path, raw in original.items())


def test_sweep_forgery_and_serialization_failure_are_atomic(sweep, monkeypatch):
    from caelab_prep.application import session as implementation
    _, native = sweep
    session, material, prop = _session(native, native.length_unit)
    before = _state(session)
    first = native.elements[0]
    for invalid in (replace(native, elements=(replace(first, node_ids=tuple(reversed(first.node_ids))), *native.elements[1:])),
                    replace(native, groups=())):
        with pytest.raises(PrepError):
            session.adopt_mesh_candidate(invalid, material_id=material, property_id=prop)
        assert _state(session) == before
    monkeypatch.setattr(implementation, "real", lambda value: f"{value:20.0f}")
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=prop)
    assert error.value.code == "native_precision"
    assert _state(session) == before


@pytest.mark.parametrize("formulation", [0, 14, 17, 18, 24])
def test_sweep_does_not_inherit_or_substitute_solid_formulations(sweep, formulation, tmp_path):
    _, native = sweep
    session, material, prop = _session(native, native.length_unit)
    text = session.card_text(prop)
    lines = text.splitlines(keepends=True)
    lines[2] = f"{formulation:10d}" + lines[2][10:]
    source = tmp_path / "explicit unsupported property.rad"
    session.export_rad(source)
    source.write_bytes(source.read_bytes().replace(text.encode("latin1"), "".join(lines).encode("latin1")))
    session.open_rad(str(source))
    material = next(card["id"] for card in session.list_cards() if card["keyword"] == "/MAT/LAW1/41")
    prop = next(card["id"] for card in session.list_cards() if card["keyword"] == "/PROP/SOLID/207")
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=prop)
    assert error.value.code == "incompatible_property"
    assert _state(session) == before
