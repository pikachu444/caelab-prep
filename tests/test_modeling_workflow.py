"""User-model creation/assignment oracles independent of the product writer.

Radioss 2024 public LAW1, TYPE1 and PART formats define the fixed columns read
below. The inputs deliberately use different material/property/part numbers and
INCLUDE ownership; no fixture name, contiguous numbering or product parser is
used to determine whether an exported assignment is correct.
"""
from __future__ import annotations

import shutil
from uuid import uuid4

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError


def _card(session, keyword):
    return next(item for item in session.list_cards() if item["keyword"] == keyword)


def _state(session):
    return (session.describe()["revision"], session.describe()["dirty"],
            tuple((c["id"], c["resource_id"], session.card_text(c["id"]))
                  for c in session.list_cards()))


def _data(raw: bytes, keyword: str):
    """Read an exported block without importing DeckResource or its schema."""
    lines = raw.decode("latin1").splitlines()
    start = lines.index(keyword) + 1
    stop = next((i for i in range(start, len(lines))
                 if lines[i].startswith("/") or lines[i].lstrip().lower().startswith("#enddata")), len(lines))
    return [line for line in lines[start:stop] if line.strip() and not line.lstrip().startswith("#")]


@pytest.fixture
def user_model(tmp_path):
    inputs = tmp_path / "user-input"
    inputs.mkdir()
    root = ("/BEGIN\r\nIndependent user assembly\r\n      2024         0\r\n"
            "                  Mg                  mm                   s\r\n"
            "#include geometry.inc\r\n#include parts.inc\r\n"
            "/PROP/SHELL/19\r\nExisting section\r\n"
            "        24         4         2         2\r\n"
            "                   0                   0                   0                   0               0.015\r\n"
            "         0                           1.7       0.83333333333         2         0\r\n"
            "/PART/902\r\nTarget plate\r\n"
            f"{19:10d}{17:10d}{0:10d}{3.25:20g}\r\n"
            "/FUTURE/OPAQUE/77\r\nUntouched unsupported block  \r\n  9.876D+05  opaque  \r\n"
            "/END\r\n").encode("latin1")
    geometry = ("# Original mesh, exact bytes are an export oracle.  \r\n/NODE\r\n" +
                "".join(f"{n:10d}{x:20g}{y:20g}{0:20g}\r\n" for n, x, y in
                        [(101, 0, 0), (205, 2, 0), (309, 2, 1), (411, 0, 1),
                         (501, 0, 3), (605, 2, 3), (709, 2, 4), (811, 0, 4)]) +
                "/SHELL/902\r\n" + "".join(f"{i:10d}" for i in [7001, 101, 205, 309, 411]) +
                "\r\n/SHELL/903\r\n" + "".join(f"{i:10d}" for i in [9007, 501, 605, 709, 811]) +
                "\r\n#ENDDATA\r\nignored trailing mesh bytes  \r\n").encode("latin1")
    parts = ("/MAT/ELAST/00017\r\nExisting aluminium\r\n" +
             f"{2.71e-9:20g}\r\n{70123:20g}{.31:20g}\r\n" +
             "/PART/903\r\nUntouched second plate\r\n" +
             f"{19:10d}{17:10d}{0:10d}{8.5:20g}\r\n" +
             "#ENDDATA\r\n/MAT/LAW1/41\r\nInactive tail must not reserve an ID\r\n").encode("latin1")
    (inputs / "assembly_0000.rad").write_bytes(root)
    (inputs / "geometry.inc").write_bytes(geometry)
    (inputs / "parts.inc").write_bytes(parts)
    session = PrepSession()
    session.open_rad(str(inputs / "assembly_0000.rad"))
    assert session.describe()["element_count"] == 2
    return session, inputs, root, geometry, parts


def test_create_assign_undo_save_reopen_export_user_model(user_model, tmp_path):
    session, inputs, root_raw, geometry_raw, parts_raw = user_model
    target = _card(session, "/PART/902")
    other = _card(session, "/PART/903")
    target_before = session.card_text(target["id"])
    other_before = session.card_text(other["id"])
    session.create_material("New steel", 7.91e-9, 203456.0, .287, native_id=41,
                            expected_revision=0, expected_document_id=session.describe()["document_id"])
    material = _card(session, "/MAT/LAW1/41")
    session.create_shell_property("New section", 2.375, native_id=207, expected_revision=1)
    section = _card(session, "/PROP/SHELL/207")
    # Appending resources must not silently renumber existing persistent objects.
    assert _card(session, "/PART/902")["id"] == target["id"]
    assert _card(session, "/PART/903")["id"] == other["id"]
    session.assign_part(target["id"], material_id=material["id"], property_id=section["id"],
                        expected_revision=2)
    assert session.describe()["revision"] == 3
    assert session.card_text(other["id"]) == other_before
    assigned = _data(session.card_text(target["id"]).encode("latin1"), "/PART/902")[1]
    assert (int(assigned[:10]), int(assigned[10:20])) == (207, 41)
    assert assigned[20:] == _data(target_before.encode("latin1"), "/PART/902")[1][20:]
    session.undo()
    assert session.card_text(target["id"]) == target_before
    session.redo()
    project = tmp_path / "working.caeprep"
    session.save_project(str(project))
    shutil.rmtree(inputs)
    reopened = PrepSession()
    reopened.open_project(str(project))
    assert _card(reopened, "/PART/902")["id"] == target["id"]
    output = tmp_path / "portable" / "assembly_0000.rad"
    reopened.export_rad(str(output))
    emitted = output.read_bytes()
    assert (output.parent / "geometry.inc").read_bytes() == geometry_raw
    assert (output.parent / "parts.inc").read_bytes() == parts_raw
    assert b"/FUTURE/OPAQUE/77\r\nUntouched unsupported block  \r\n  9.876D+05  opaque  \r\n" in emitted
    assert emitted.endswith(b"/END\r\n")
    assert b"#include geometry.inc\r\n#include parts.inc\r\n" in emitted
    values = _data(emitted, "/MAT/LAW1/41")
    assert float(values[1][:20]) == pytest.approx(7.91e-9)
    assert float(values[2][:20]) == pytest.approx(203456.0)
    assert float(values[2][20:40]) == pytest.approx(.287)
    shell = _data(emitted, "/PROP/SHELL/207")
    assert [int(shell[1][i:i + 10]) for i in range(0, 40, 10)] == [24, 4, 2, 2]
    assert int(shell[3][:10]) == 0
    assert not shell[3][10:20].strip()  # 2024 reserved; not legacy ISTRAIN.
    assert float(shell[3][20:40]) == pytest.approx(2.375)
    assert float(shell[3][40:60]) == pytest.approx(5 / 6)
    assert int(shell[3][60:70]) == 2
    actual = _data(emitted, "/PART/902")[1]
    assert (int(actual[:10]), int(actual[10:20]), float(actual[30:50])) == (207, 41, 3.25)
    # Reopen native output through a fresh public session as a second check.
    exported = PrepSession()
    exported.open_rad(str(output))
    assert exported.describe()["element_count"] == 2
    assert len([c for c in exported.list_cards() if c["keyword"] == "/MAT/LAW1/41"]) == 1


def test_copy_into_include_delete_and_undo_preserve_identity_and_tail(user_model, tmp_path):
    _, inputs, _, geometry_raw, parts_raw = user_model
    # Deletion is only certified for a document with a complete dependency scan.
    # This independent known-only input exercises successful delete; the opaque
    # input remains covered separately by preservation and refusal assertions.
    root = inputs / "assembly_0000.rad"
    opaque = b"/FUTURE/OPAQUE/77\r\nUntouched unsupported block  \r\n  9.876D+05  opaque  \r\n"
    root.write_bytes(root.read_bytes().replace(opaque, b""))
    session = PrepSession()
    session.open_rad(str(root))
    original = _card(session, "/MAT/ELAST/00017")
    result = session.copy_card(original["id"], name="Independent copy", native_id=81,
                               resource_id=original["resource_id"])
    copied_id = result["card_id"]
    copied = next(c for c in session.list_cards() if c["id"] == copied_id)
    assert copied["resource_id"] == original["resource_id"]
    assert copied_id != original["id"]
    values = _data(session.card_text(copied_id).encode("latin1"), copied["keyword"])
    assert values[0] == "Independent copy"
    assert float(values[1][:20]) == pytest.approx(2.71e-9)
    assert float(values[2][:20]) == 70123
    session.delete_card(copied_id)
    assert not any(c["id"] == copied_id for c in session.list_cards())
    session.undo()
    assert any(c["id"] == copied_id for c in session.list_cards())
    session.redo()
    output = tmp_path / "copy-export" / "assembly_0000.rad"
    session.export_rad(str(output))
    assert (output.parent / "parts.inc").read_bytes() == parts_raw
    assert (output.parent / "geometry.inc").read_bytes() == geometry_raw


def test_referenced_delete_and_invalid_assignment_are_atomic(user_model):
    session, *_ = user_model
    target = _card(session, "/PART/902")
    material = _card(session, "/MAT/ELAST/00017")
    section = _card(session, "/PROP/SHELL/19")
    session.create_material("Candidate assignment", 7.9e-9, 202000, .3, native_id=41)
    replacement = _card(session, "/MAT/LAW1/41")
    events = []
    session.subscribe(events.append)
    before = _state(session)
    for card_id in (material["id"], section["id"]):
        with pytest.raises(PrepError):
            session.delete_card(card_id)
        assert _state(session) == before
    # A valid material plus an invalid property cannot partially change PART.
    for wrong_property in (str(uuid4()), material["id"]):
        with pytest.raises(PrepError):
            session.assign_part(target["id"], material_id=replacement["id"], property_id=wrong_property)
        assert _state(session) == before
    assert events == []


@pytest.mark.parametrize("native_id", [17, 0, -1, True, 1.5, 10_000_000_000])
def test_material_native_id_conflict_or_bad_id_rejects_before_mutation(user_model, native_id):
    session, *_ = user_model
    before = _state(session)
    with pytest.raises(PrepError):
        session.create_material("Rejected", 7.9e-9, 202000, .3, native_id=native_id)
    assert _state(session) == before


def test_cross_family_id_reuse_is_allowed_and_generated_ids_are_unique(user_model):
    session, *_ = user_model
    session.create_material("Material nineteen", 7.9e-9, 202000, .3, native_id=19)
    session.create_shell_property("Property seventeen", 2.0, native_id=17)
    assert _card(session, "/MAT/LAW1/19")
    assert _card(session, "/PROP/SHELL/17")
    first = session.create_material("Auto one", 7.9e-9, 202000, .3)["card_id"]
    second = session.create_material("Auto two", 7.9e-9, 202000, .3)["card_id"]
    assert first != second
    native = [int(c["keyword"].split("/")[3]) for c in session.list_cards()
              if c["keyword"].startswith("/MAT/")]
    assert len(native) == len(set(native))


@pytest.mark.parametrize("changes", [
    {"density": 0}, {"young_modulus": -1}, {"poisson_ratio": .5},
    {"young_modulus": float("nan")}, {"density": float("inf")},
    {"name": "name\n/END"}, {"name": "x" * 101},
])
def test_invalid_material_does_not_mutate(user_model, changes):
    session, *_ = user_model
    args = {"name": "Valid", "density": 7.9e-9, "young_modulus": 202000,
            "poisson_ratio": .3, "native_id": 41} | changes
    before = _state(session)
    with pytest.raises(PrepError):
        session.create_material(**args)
    assert _state(session) == before


def test_stale_revision_and_wrong_document_do_not_mutate(user_model):
    session, *_ = user_model
    before = _state(session)
    with pytest.raises(PrepError):
        session.create_shell_property("Valid", 2.0, native_id=207, expected_revision=99)
    assert _state(session) == before
    with pytest.raises(PrepError):
        session.create_shell_property("Valid", 2.0, native_id=207, expected_document_id=str(uuid4()))
    assert _state(session) == before


@pytest.mark.parametrize("thickness", [0, -1, float("nan"), float("inf"), True])
def test_invalid_shell_thickness_does_not_create_a_card(user_model, thickness):
    session, *_ = user_model
    before = _state(session)
    with pytest.raises(PrepError):
        session.create_shell_property("Invalid section", thickness, native_id=207)
    assert _state(session) == before


def test_unknown_include_blocks_creation_instead_of_guessing_global_ids(tmp_path):
    source = tmp_path / "unresolved.rad"
    source.write_bytes(b"/BEGIN\nUnresolved assembly\n#include unavailable.inc\n/END\n")
    session = PrepSession()
    session.open_rad(str(source))
    before = _state(session)
    with pytest.raises(PrepError):
        session.create_material("Unknown namespace", 7.9e-9, 202000, .3)
    assert _state(session) == before


def test_optional_part_unit_id_cannot_hide_assignment_dependencies(user_model):
    _, inputs, *_ = user_model
    root = inputs / "assembly_0000.rad"
    root.write_bytes(root.read_bytes().replace(b"/PART/902\r\n", b"/PART/902/77\r\n").replace(
        b"/PROP/SHELL/19", b"/UNIT/77\r\nContact units\r\n                  Mg                  mm                   s\r\n/PROP/SHELL/19"))
    included = inputs / "parts.inc"
    included.write_bytes(included.read_bytes().replace(b"/PART/903\r\n", b"/PART/903/77\r\n"))
    session = PrepSession()
    session.open_rad(str(root))
    material = _card(session, "/MAT/ELAST/00017")
    before = _state(session)
    with pytest.raises(PrepError):
        session.delete_card(material["id"])
    assert _state(session) == before
    part = _card(session, "/PART/902/77")
    assert session.part_assignment(part["id"])["native_material_id"] == 17
    created = session.create_material("Unit-bearing target", 7.9e-9, 202000, .3, native_id=41)
    session.assign_part(part["id"], material_id=created["card_id"])
    line = _data(session.card_text(part["id"]).encode("latin1"), "/PART/902/77")[1]
    assert int(line[10:20]) == 41
    assert float(line[30:50]) == 3.25


def test_ply_material_reference_blocks_unsafe_delete(user_model):
    _, inputs, *_ = user_model
    root = inputs / "assembly_0000.rad"
    # Public 2024 /PROP/TYPE19 format: mat_ID10, t20, angle20,
    # grsh4n10, grsh3n10, Npt_ply10, alpha20. No PART references MAT 41.
    additional = ("/MAT/LAW1/41\r\nPly material\r\n" +
                  f"{7.9e-9:20g}\r\n{203000:20g}{.29:20g}\r\n" +
                  "/PROP/TYPE19/88\r\nPly reference\r\n" +
                  f"{41:10d}{.4:20g}{45:20g}{0:10d}{0:10d}{1:10d}{90:20g}\r\n").encode("latin1")
    known = root.read_bytes().replace(
        b"/FUTURE/OPAQUE/77\r\nUntouched unsupported block  \r\n  9.876D+05  opaque  \r\n", b"")
    root.write_bytes(known.replace(b"/END\r\n", additional + b"/END\r\n"))
    session = PrepSession()
    session.open_rad(str(root))
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.delete_card(_card(session, "/MAT/LAW1/41")["id"])
    assert error.value.code == "card_in_use"
    assert _state(session) == before


def test_opaque_native_references_block_delete_without_guessing(user_model):
    session, *_ = user_model
    created = session.create_material("Not referenced by known PARTs", 7.9e-9, 202000, .3, native_id=41)
    before = _state(session)
    with pytest.raises(PrepError) as error:
        session.delete_card(created["card_id"])
    assert error.value.code == "dependency_scan_incomplete"
    assert _state(session) == before


def test_solid_property_cannot_be_assigned_to_a_shell_part(user_model):
    _, inputs, *_ = user_model
    root = inputs / "assembly_0000.rad"
    solid = ("/PROP/SOLID/88\r\nExisting solid property\r\n" +
             f"{17:10d}{0:10d}" + " " * 10 + f"{0:10d}" + " " * 10 +
             f"{0:10d}{0:10d}{0:10d}{0:20g}\r\n\r\n{0:20g}{0:10d}{0:10d}\r\n").encode("latin1")
    root.write_bytes(root.read_bytes().replace(b"/END\r\n", solid + b"/END\r\n"))
    session = PrepSession()
    session.open_rad(str(root))
    before = _state(session)
    with pytest.raises(PrepError):
        session.assign_part(_card(session, "/PART/902")["id"],
                            property_id=_card(session, "/PROP/SOLID/88")["id"])
    assert _state(session) == before
