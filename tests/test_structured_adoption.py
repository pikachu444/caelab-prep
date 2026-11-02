"""Real recipe candidates cross the common command/codec/native boundary."""

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from caelab_prep.application.structured_mesh import generate_structured_mesh
from caelab_prep.cae_core.errors import PrepError
from test_mesh_adoption import _session, _state


@pytest.fixture(scope="module", params=["Q-N3", "Q-D2"])
def quad(request, tmp_path_factory):
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable; no structured adoption execution claim")
    inputs = Path(__file__).parents[1] / "scripts/evaluation/structured_f2/holdout-inputs.json"
    case = next(item for item in json.loads(inputs.read_text(encoding="utf-8")) if item["id"] == request.param)
    candidate = generate_structured_mesh(case["input"], tmp_path_factory.mktemp(request.param))
    assert len(candidate.to_native_mesh().elements) == case["expectation"]["elements"]
    return case, candidate.to_native_mesh()


def _native(raw):
    """Fixed-width file oracle, independent of the product's projection/parser."""
    nodes, elements, parts, groups = {}, {}, {}, {}
    keyword, rows = "", []

    def consume():
        if keyword == "/NODE":
            for row in rows:
                identifier = int(row[:10])
                assert identifier not in nodes
                nodes[identifier] = tuple(float(row[i:i + 20]) for i in (10, 30, 50))
        elif keyword.startswith("/SHELL/"):
            for row in rows:
                identifier = int(row[:10])
                assert identifier not in elements
                elements[identifier] = (int(keyword.split("/")[2]),
                    tuple(int(row[i:i + 10]) for i in (10, 20, 30, 40)))
        elif keyword.startswith("/PART/"):
            parts[int(keyword.split("/")[2])] = (int(rows[1][:10]), int(rows[1][10:20]))
        elif keyword.startswith(("/GRNOD/NODE/", "/GRSHEL/SHEL/")):
            groups[keyword] = tuple(int(row[i:i + 10]) for row in rows[1:]
                                    for i in range(0, len(row), 10) if row[i:i + 10].strip())

    for line in raw.decode("latin1").splitlines():
        if line.startswith("/"):
            consume()
            keyword, rows = line, []
        elif line.strip() and not line.lstrip().startswith("#"):
            rows.append(line)
    consume()
    return nodes, elements, parts, groups


def test_real_quads_adopt_once_undo_save_new_process_export(quad, tmp_path):
    case, native = quad
    source_bytes = {asset.path: Path(asset.path).read_bytes() for asset in native.assets}
    session, material, prop = _session(native, native.length_unit)
    before = _state(session)[1]
    result = session.adopt_mesh_candidate(native, material_id=material, property_id=prop,
                                          expected_revision=session.describe()["revision"])
    assert session.describe()["element_count"] == case["expectation"]["elements"]
    assert session.describe()["node_count"] == case["expectation"]["active_nodes"]
    after = _state(session)[1]
    session.undo()
    assert _state(session)[1] == before
    session.redo()
    assert _state(session)[1] == after
    second = session.adopt_mesh_candidate(native, material_id=material, property_id=prop)
    assert set(second["node_id_map"].values()).isdisjoint(result["node_id_map"].values())
    assert set(second["element_id_map"].values()).isdisjoint(result["element_id_map"].values())
    session.undo()
    assert _state(session)[1] == after
    project = tmp_path / "quad.caeprep"
    session.save_project(project)
    output = tmp_path / "new-process/quad_0000.rad"
    command = subprocess.run([sys.executable, "-m", "caelab_prep", "export", str(project),
                              "--output", str(output)], capture_output=True, text=True, timeout=30)
    assert command.returncode == 0, command.stdout + command.stderr
    nodes, elements, parts, groups = _native(output.read_bytes())
    assert len(nodes) == len(native.nodes) and len(elements) == len(native.elements)
    assert set(parts.values()) == {(207, 41)}
    part_ids = {source: int(next(card["keyword"] for card in session.list_cards()
                               if card["id"] == target).split("/")[2])
                for source, target in result["part_id_map"].items()}
    for node in native.nodes:
        assert nodes[result["node_id_map"][node.id]] == pytest.approx(node.xyz, rel=1e-12, abs=1e-12)
    for cell in native.elements:
        assert elements[result["element_id_map"][cell.id]] == (
            part_ids[cell.part_uuid], tuple(result["node_id_map"][node] for node in cell.node_ids))
    for group in native.groups:
        keyword = next(card["keyword"] for card in session.list_cards() if card["id"] == result["group_id_map"][group.key])
        mapping = result["node_id_map"] if group.kind == "node" else result["element_id_map"]
        assert keyword.startswith("/GRNOD/NODE/" if group.kind == "node" else "/GRSHEL/SHEL/")
        assert groups[keyword] == tuple(mapping[identifier] for identifier in group.member_ids)
    if len(native.parts) == 2:
        memberships = [set(node for cell in elements.values() if cell[0] == part
                           for node in cell[1]) for part in parts]
        assert len(memberships[0] & memberships[1]) == case["expectation"]["shared_nodes"]
    assert all(Path(path).read_bytes() == raw for path, raw in source_bytes.items())


def test_structured_forgeries_units_and_wrong_property_leave_document_unchanged(quad):
    _, native = quad
    session, material, prop = _session(native, native.length_unit)
    solid = session.create_solid_property("Wrong family")["card_id"]
    before = _state(session)
    first = native.nodes[0]
    for invalid in (
        replace(native, nodes=(replace(first, xyz=(first.xyz[0] + .01, *first.xyz[1:])), *native.nodes[1:])),
        replace(native, elements=(replace(native.elements[0], node_ids=tuple(reversed(native.elements[0].node_ids))), *native.elements[1:])),
        replace(native, groups=()),
        replace(native, length_unit="m"),
    ):
        with pytest.raises(PrepError):
            session.adopt_mesh_candidate(invalid, material_id=material, property_id=prop)
        assert _state(session) == before
    with pytest.raises(PrepError, match="shell property"):
        session.adopt_mesh_candidate(native, material_id=material, property_id=solid)
    assert _state(session) == before
    mismatched, other_material, other_prop = _session(native, "mm" if native.length_unit == "cm" else "cm")
    original = _state(mismatched)
    with pytest.raises(PrepError) as error:
        mismatched.adopt_mesh_candidate(native, material_id=other_material, property_id=other_prop)
    assert error.value.code == "unit_mismatch"
    assert _state(mismatched) == original


def test_structured_hex_remains_unadoptable(tmp_path):
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Real Gmsh SDK unavailable")
    spec = dict(mode="hex", unit="mm", corners=[[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0]],
                divisions=[1, 1], vector=[0, 0, 2], layers=1)
    native = generate_structured_mesh(spec, tmp_path).to_native_mesh()
    session, material, prop = _session(native)
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=prop)
    assert error.value.code == "unsupported_mesh_family"
    assert _state(session) == before


def test_serialization_damage_is_rejected_before_publish(quad, monkeypatch):
    from caelab_prep.application import session as session_module

    _, native = quad
    session, material, prop = _session(native, native.length_unit)
    before = _state(session)
    # Fault injection at the writer boundary; source SDK precision is separate.
    monkeypatch.setattr(session_module, "real", lambda value: f"{value:20.0f}")
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=prop)
    assert error.value.code == "native_precision"
    assert _state(session) == before


def test_mismatched_original_recipe_is_rejected_before_creating_assets(tmp_path):
    spec = dict(mode="quad", unit="mm", corners=[[0, 0, 0], [2, 0, 0], [2, 3, 0], [0, 3, 0]], divisions=[1, 1])
    source = tmp_path / "original.json"
    source.write_text(json.dumps(spec), encoding="utf-8")
    original = source.read_bytes()
    with pytest.raises(PrepError) as error:
        generate_structured_mesh(dict(spec, divisions=[2, 1]), tmp_path / "assets", recipe_path=source)
    assert error.value.code == "candidate_changed"
    assert source.read_bytes() == original and not (tmp_path / "assets").exists()


def test_synchronous_autosave_observer_sees_and_persists_source_protection(quad, tmp_path):
    _, native = quad
    source = Path(next(asset.path for asset in native.assets if asset.kind == "recipe"))
    original = source.read_bytes()
    session, material, prop = _session(native, native.length_unit)
    project = tmp_path / "observer-saved.caeprep"
    observed = []

    def save_on_adoption(event):
        if event["kind"] != "structure" or event.get("change", {}).get("label") != "Adopt mesh candidate":
            return
        outcomes = []
        for write in (session.save_project, session.export_rad):
            try:
                write(source)
            except PrepError as error:
                outcomes.append(error.code)
            else:
                outcomes.append("overwrite allowed")
        session.save_project(project)
        observed.append(outcomes)

    session.subscribe(save_on_adoption)
    try:
        session.adopt_mesh_candidate(native, material_id=material, property_id=prop)
        assert observed == [["source_overwrite", "source_overwrite"]]
        assert source.read_bytes() == original
        reopened = type(session)()
        reopened.open_project(project)
        assert reopened.describe()["element_count"] == len(native.elements)
        for write in (reopened.save_project, reopened.export_rad):
            with pytest.raises(PrepError) as error:
                write(source)
            assert error.value.code == "source_overwrite"
        assert source.read_bytes() == original
    finally:
        # The fixture is test-owned; preserve it even when testing broken ordering.
        if source.read_bytes() != original:
            source.write_bytes(original)


def test_failed_adoption_restores_source_protection_with_the_model(quad, tmp_path, monkeypatch):
    _, native = quad
    session, material, prop = _session(native, native.length_unit)
    before = _state(session)
    previous = tmp_path / "before.caeprep"
    session.save_project(previous)
    with zipfile.ZipFile(previous) as archive:
        source_paths = json.loads(archive.read("manifest.json"))["source_paths"]
    resource = session.document.resources[session._root_id]
    source = Path(next(asset.path for asset in native.assets if asset.kind == "recipe"))
    original = source.read_bytes()
    restore = type(resource).restore
    attempted = []

    def fail_first_owner_restore(owner, state):
        if owner is resource and not attempted:
            try:
                session.export_rad(source)
            except PrepError as error:
                attempted.append(error.code)
            else:
                attempted.append("overwrite allowed")
            raise PrepError("injected_commit_failure", "Resource rejected the adoption")
        return restore(owner, state)

    monkeypatch.setattr(type(resource), "restore", fail_first_owner_restore)
    try:
        with pytest.raises(PrepError) as error:
            session.adopt_mesh_candidate(native, material_id=material, property_id=prop)
        assert error.value.code == "injected_commit_failure"
        assert attempted == ["source_overwrite"]
        assert _state(session) == before
        current = tmp_path / "after.caeprep"
        session.save_project(current)
        with zipfile.ZipFile(current) as archive:
            assert json.loads(archive.read("manifest.json"))["source_paths"] == source_paths
        assert source.read_bytes() == original
    finally:
        if source.read_bytes() != original:
            source.write_bytes(original)
