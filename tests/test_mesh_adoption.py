"""Real CAD/Gmsh candidates cross the native modeling boundary unchanged.

The optional SDK fixture builds fresh surface, cylinder and two-solid models.
Expected coordinates/connectivity come from the independently inspected MSH;
the exported deck is read with a small fixed-width oracle, not DeckResource.
"""
from __future__ import annotations

from dataclasses import replace
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
