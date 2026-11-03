"""Real CAD/Gmsh candidates cross the native modeling boundary unchanged.

The optional SDK fixture builds fresh surface, cylinder and two-solid models.
Expected coordinates/connectivity come from the independently inspected MSH;
the exported deck is read with a small fixed-width oracle, not DeckResource.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from test_mesh_candidates import real_candidate


def _session(native, length="mm"):
    session = PrepSession()
    session.new_document("Independent mesh adoption", {"mass": "Mg", "length": length, "time": "s"})
    material = session.create_material("Steel", 7.8e-9, 210000, .3, native_id=41)["card_id"]
    section = (session.create_shell_property("Thin sheet", .1, native_id=207) if native.dimension == 2
               else session.create_solid_property("Linear tetra", native_id=207))["card_id"]
    return session, material, section


def _state(session):
    return session.describe()["revision"], tuple((c["id"], session.card_text(c["id"])) for c in session.list_cards())


def _native(raw):
    nodes, cells, parts = {}, {}, {}
    keyword, rows = None, []
    def consume():
        if keyword == "/NODE":
            for row in rows:
                identifier = int(row[:10])
                assert identifier not in nodes
                nodes[identifier] = tuple(float(row[i:i+20]) for i in (10, 30, 50))
        elif keyword and keyword.startswith(("/SH3N/", "/TETRA4/")):
            count = 3 if keyword.startswith("/SH3N/") else 4
            part = int(keyword.split("/")[2])
            for row in rows:
                identifier = int(row[:10])
                assert identifier not in cells
                cells[identifier] = (part, tuple(int(row[i:i+10]) for i in range(10, 10*(count+1), 10)))
        elif keyword and keyword.startswith("/PART/"):
            parts[int(keyword.split("/")[2])] = (int(rows[1][:10]), int(rows[1][10:20]))
    for line in raw.decode("latin1").splitlines():
        if line.startswith("/"):
            consume(); keyword, rows = line, []
        elif line.strip() and not line.lstrip().startswith("#"):
            rows.append(line)
    consume()
    return nodes, cells, parts


def test_real_candidates_adopt_map_append_undo_save_and_export(real_candidate, tmp_path):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    before = _state(session)
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section,
                                            expected_revision=session.describe()["revision"])
    assert session.describe()["element_count"] == len(native.elements)
    assert len(adopted["part_ids"]) == len(native.parts)
    session.undo()
    assert _state(session)[1] == before[1]
    session.redo()
    assert all(any(c["id"] == identifier for c in session.list_cards()) for identifier in adopted["part_ids"])
    first_cards = {c["id"]: session.card_text(c["id"]) for c in session.list_cards()}
    second = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert set(second["node_id_map"].values()).isdisjoint(adopted["node_id_map"].values())
    assert set(second["element_id_map"].values()).isdisjoint(adopted["element_id_map"].values())
    assert all(session.card_text(identifier) == raw for identifier, raw in first_cards.items())
    session.undo()
    assert session.describe()["element_count"] == len(native.elements)
    project = tmp_path / "working.caeprep"
    session.save_project(str(project))
    relocated = tmp_path / "relocated" / "model.caeprep"
    relocated.parent.mkdir(); shutil.copy2(project, relocated)
    reopened = PrepSession(); reopened.open_project(str(relocated))
    output = tmp_path / "export" / "candidate_0000.rad"
    reopened.export_rad(str(output))
    nodes, cells, parts = _native(output.read_bytes())
    assert len(nodes) == len(native.nodes) and len(cells) == len(native.elements)
    assert set(parts.values()) == {(207, 41)}
    part_native = {source: int(next(c["keyword"] for c in reopened.list_cards() if c["id"] == target).split("/")[2])
                   for source, target in adopted["part_id_map"].items()}
    for node in native.nodes:
        assert nodes[adopted["node_id_map"][node.id]] == pytest.approx(node.xyz, rel=1e-12, abs=1e-12)
    for element in native.elements:
        assert cells[adopted["element_id_map"][element.id]] == (
            part_native[element.part_uuid], tuple(adopted["node_id_map"][node] for node in element.node_ids))


def test_unit_mismatch_and_wrong_property_are_atomic(real_candidate):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native, "m")
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert error.value.code == "unit_mismatch" and _state(session) == before
    session, material, section = _session(native)
    wrong = (session.create_solid_property("Wrong solid") if native.dimension == 2 else
             session.create_shell_property("Wrong shell", .1))["card_id"]
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=wrong)
    assert error.value.code == "incompatible_property" and _state(session) == before


def test_changed_native_value_and_condition_referenced_replacement_are_rejected(real_candidate):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    altered = replace(native, nodes=(replace(native.nodes[0], xyz=(999., 0., 0.)), *native.nodes[1:]))
    before = _state(session)
    with pytest.raises(PrepError):
        session.adopt_mesh_candidate(altered, material_id=material, property_id=section)
    assert _state(session) == before
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    group = session.create_node_group("Referenced mesh", list(adopted["node_id_map"].values()))["card_id"]
    session.create_initial_velocity("Uniform speed", group, [2.5, 0, 0])
    before = _state(session)
    with pytest.raises(PrepError):
        session.adopt_mesh_candidate(native, material_id=material, property_id=section,
                                    replace_part_ids=adopted["part_ids"])
    assert _state(session) == before


def test_owned_mesh_replacement_is_atomic_and_preserves_external_shared_nodes(real_candidate, tmp_path):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    original = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    before = _state(session)
    changed = session.adopt_mesh_candidate(native, material_id=material, property_id=section,
        replace_part_ids=original["part_ids"], expected_revision=before[0])
    assert session.describe()["revision"] == before[0] + 1
    assert session.describe()["element_count"] == len(native.elements)
    assert set(changed["removed_node_ids"]) == set(original["node_id_map"].values())
    assert changed["preserved_shared_node_ids"] == []
    session.undo(); assert _state(session)[1] == before[1]
    session.redo()
    assert all(any(c["id"] == part for c in session.list_cards()) for part in changed["part_ids"])

    # A separately authored external element deliberately shares the first
    # adopted cell's nodes. Its raw block has no adoption ownership marker.
    path = tmp_path / "external.rad"; session.export_rad(str(path))
    nodes, cells, _ = _native(path.read_bytes())
    shared = next(iter(cells.values()))[1]
    external = ("/PART/9007\nExternal owner\n" + f"{207:10d}{41:10d}{0:10d}\n"
                + ("/SH3N/9007\n" if native.dimension == 2 else "/TETRA4/9007\n")
                + "".join(f"{value:10d}" for value in (9009, *shared)) + "\n")
    path.write_bytes(path.read_bytes().replace(b"/END", external.encode() + b"/END"))
    session.open_rad(str(path))
    material = next(c["id"] for c in session.list_cards() if c["keyword"] == "/MAT/LAW1/41")
    section = next(c["id"] for c in session.list_cards() if c["category"] == "Properties")
    owned_parts = [c["id"] for c in session.list_cards() if c["category"] == "Parts" and c["keyword"] != "/PART/9007"]
    external_cards = {c["id"]: session.card_text(c["id"]) for c in session.list_cards()
                      if c["keyword"].endswith("/9007")}
    before = _state(session)
    replacement = session.adopt_mesh_candidate(native, material_id=material, property_id=section,
        replace_part_ids=owned_parts, expected_revision=before[0])
    assert session.describe()["revision"] == before[0] + 1
    assert set(replacement["preserved_shared_node_ids"]) == set(shared)
    assert set(replacement["removed_node_ids"]) == set(nodes) - set(shared)
    assert all(session.card_text(key) == raw for key, raw in external_cards.items())
    session.undo(); assert _state(session)[1] == before[1]
    session.redo()
    saved = tmp_path / "replaced.caeprep"; session.save_project(str(saved))
    reopened = PrepSession(); reopened.open_project(str(saved)); path.unlink()
    output = tmp_path / "replacement.rad"; reopened.export_rad(str(output))
    new_nodes, new_cells, new_parts = _native(output.read_bytes())
    assert len(new_nodes) == len(native.nodes) + len(shared)
    assert len(new_cells) == len(native.elements) + 1 and len(new_parts) == len(native.parts) + 1
    assert new_cells[9009] == (9007, shared)
    assert all(new_nodes[node] == nodes[node] for node in shared)


def test_original_cad_path_is_protected_before_publish_and_after_reopen(real_candidate, tmp_path):
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    _, _, candidate = real_candidate
    metadata = json.loads(Path(next(asset.path for asset in candidate.assets if asset.kind == "metadata")).read_text(encoding="utf-8"))
    captured = Path(metadata["source"]["captured_path"])
    original = tmp_path / "original CAD.step"
    original.write_bytes(captured.read_bytes())
    original_bytes = original.read_bytes()
    metadata["source"]["path"] = str(original)
    manifest = tmp_path / "metadata.json"
    manifest.write_text(json.dumps(metadata), encoding="utf-8")
    native = read_mesh_candidate(manifest).to_native_mesh()
    session, material, section = _session(native)
    observed = []
    project = tmp_path / "observed.caeprep"

    def at_publish(event):
        if event["kind"] != "structure" or event.get("change", {}).get("label") != "Adopt mesh candidate": return
        for write in (session.save_project, session.export_rad):
            try: write(original)
            except PrepError as error: observed.append(error.code)
            else: observed.append("overwrite allowed")
        session.save_project(project)

    session.subscribe(at_publish)
    try:
        session.adopt_mesh_candidate(native, material_id=material, property_id=section)
        assert observed == ["source_overwrite", "source_overwrite"], observed
        assert original.read_bytes() == original_bytes
        reopened = PrepSession(); reopened.open_project(project)
        for write in (reopened.save_project, reopened.export_rad):
            with pytest.raises(PrepError) as error: write(original)
            assert error.value.code == "source_overwrite"
        assert original.read_bytes() == original_bytes
    finally:
        if original.read_bytes() != original_bytes: original.write_bytes(original_bytes)


def test_preparing_adoption_does_not_publish_or_register_sources(real_candidate):
    _, _, candidate = real_candidate
    native = candidate.to_native_mesh()
    session, material, section = _session(native)
    before, paths, events = _state(session), set(session._source_paths), []
    session.subscribe(events.append)
    prepared = session._prepare_mesh_adoption(native, material_id=material, property_id=section)
    assert _state(session) == before and session._source_paths == paths and events == []
    assert prepared["protected_sources"] and prepared["native_mesh"] == native
    assert not set(prepared["result"]["card_ids"]) & {card["id"] for card in session.list_cards()}


def _metadata_native(candidate, tmp_path, original):
    metadata = json.loads(Path(next(a.path for a in candidate.assets if a.kind == "metadata")).read_text(encoding="utf-8"))
    metadata["source"]["path"] = original
    raw = json.dumps(metadata).encode("utf-8")
    path = tmp_path / "metadata.json"; path.write_bytes(raw)
    native = candidate.to_native_mesh()
    return replace(native, assets=tuple(replace(a, path=str(path), sha256=sha256(raw).hexdigest())
                   if a.kind == "metadata" else a for a in native.assets)), path, raw


@pytest.mark.parametrize("original", [False, 0, [], {}, None, "", " "])
def test_falsey_original_cad_path_is_not_an_absent_origin(real_candidate, monkeypatch, tmp_path, original):
    from caelab_prep.application import mesh_candidates
    _, _, candidate = real_candidate
    native, _, _ = _metadata_native(candidate, tmp_path, original)
    monkeypatch.setattr(mesh_candidates, "validate_native_mesh", lambda value: value)
    session, material, section = _session(native)
    before, paths = _state(session), set(session._source_paths)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert error.value.code == "invalid_candidate"
    assert _state(session) == before and session._source_paths == paths


def test_original_cad_path_uses_the_validated_metadata_bytes(real_candidate, monkeypatch, tmp_path):
    from caelab_prep.application import mesh_candidates
    _, _, candidate = real_candidate
    native, path, before_raw = _metadata_native(candidate, tmp_path, str(tmp_path / "A.step"))
    (tmp_path / "metadata-before.json").write_bytes(before_raw)
    def change_after_validation(value):
        data = json.loads(before_raw); data["source"]["path"] = str(tmp_path / "B.step")
        path.write_text(json.dumps(data), encoding="utf-8")
        return value
    monkeypatch.setattr(mesh_candidates, "validate_native_mesh", change_after_validation)
    session, material, section = _session(native)
    before, paths = _state(session), set(session._source_paths)
    with pytest.raises(PrepError) as error:
        session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    assert error.value.code == "candidate_changed"
    assert _state(session) == before and session._source_paths == paths


@pytest.mark.parametrize("beam_part", ["2", "+2"])
@pytest.mark.parametrize("tetra_part", ["1", "+1"])
def test_replacement_preserves_external_beam_direction_reference(beam_part, tetra_part):
    """Preserve raw references even before an external PART's profile is repaired."""
    from copy import copy
    from uuid import uuid4
    session = PrepSession()
    session.new_document("Raw reference preservation", {"mass": "Mg", "length": "mm", "time": "s"})
    session.create_material("Steel", 7.8e-9, 210000, .3, native_id=41)
    session.create_solid_property("Solid", native_id=207)
    resource = session.document.resources[session._root_id]
    mesh, geometry, source_part = str(uuid4()), str(uuid4()), str(uuid4())
    marker = f"# CAELab adopted mesh {mesh}; part {source_part}\n"
    def node(identifier, xyz):
        return f"{identifier:10d}" + "".join(f"{value:20.12e}" for value in xyz) + "\n"
    assignment = f"{207:10d}{41:10d}{0:10d}\n"
    beam = f"/BEAM/{beam_part}\n" + "".join(f"{value:10d}" for value in (101, 5, 6, 9)) + "\n"
    texts = [f"/NODE\n# CAELab mesh {mesh}; geometry {geometry}\n" +
             "".join(node(i, p) for i, p in [(1,(0,0,0)),(2,(1,0,0)),(3,(0,1,0)),(9,(0,0,1))]),
             "/PART/1\nOwned CAD PART\n" + marker + assignment,
             f"/TETRA4/{tetra_part}\n" + marker + "".join(f"{v:10d}" for v in (1,1,2,3,9)) + "\n",
             "/NODE\n" + node(5,(2,0,0)) + node(6,(2,1,0)),
             "/PART/2\nExternal raw PART\n" + assignment, beam]
    # The external BEAM's SOLID assignment is not a certified solver profile.
    # Its declared direction-node reference must nevertheless not be deleted.
    state, ids = resource.inserted_states(texts)
    session.dispatcher.execute(resource.id, state, "Load raw references")
    resource.restore(resource.node_positions_state({"1": [.01,.01,.01], "9": [0,0,1.1]}))
    before = _state(session)
    original_beam = session.card_text(ids[5])
    if tetra_part.startswith("+"):
        with pytest.raises(PrepError) as error: session._mesh_replacement_state([ids[1]])
        assert error.value.code == "mesh_replacement_unsupported" and _state(session) == before
        return
    proposed, details = session._mesh_replacement_state([ids[1]])
    assert 9 not in details["removed_node_ids"]
    assert details["preserved_shared_node_ids"] == [9]
    assert ids[2] in details["removed_card_ids"]
    assert proposed["node_positions"] == {"9": [0,0,1.1]}
    trial = copy(resource); trial.restore(proposed)
    nodes, _, _ = _native(trial.render())
    card = trial.card(ids[5]); lines = trial.render().decode("latin1").splitlines(keepends=True)
    assert set(nodes) == {5,6,9} and "".join(lines[card.start:card.stop]) == original_beam
    assert _state(session) == before
