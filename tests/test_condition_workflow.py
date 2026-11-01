"""G2 workflow checked against independent Radioss 2024 fixed-column oracles.

No product writer/parser supplies expected rows. The small two-shell model can
also be emitted with independently authored cards for an external solver check.
"""
from __future__ import annotations

import shutil
from uuid import uuid4

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError


def _i(*values):
    return "".join(f"{v:10d}" for v in values)


def _r(*values):
    return "".join(f"{v:20.12g}" for v in values)


def _base_model(directory, name="conditions"):
    directory.mkdir(parents=True, exist_ok=True)
    nodes = [(101, 0, 0, 0), (205, 10, 0, 0), (309, 10, 10, 0), (411, 0, 10, 0),
             (501, 0, 0, 1), (605, 10, 0, 1), (709, 10, 10, 1), (811, 0, 10, 1)]
    geometry = ("# User mesh: preserve this byte sequence.  \n/NODE\n" +
                "\n".join(_i(n) + _r(x, y, z) for n, x, y, z in nodes) +
                "\n/SHELL/902\n" + _i(7001, 101, 205, 309, 411) +
                "\n/SHELL/903\n" + _i(9007, 501, 605, 709, 811) + "\n")
    root = (f"#RADIOSS STARTER\n/BEGIN\n{name}\n" + _i(2024, 0) + "\n" +
            f"{'Mg':>20}{'mm':>20}{'s':>20}\n" * 2 +
            "/MAT/ELAST/17\nUser steel\n" + _r(7.8e-9) + "\n" + _r(210000, .3) +
            "\n/PROP/SHELL/19\nUser shell\n" + _i(24, 4, 2, 2) + " " * 20 + _r(1) +
            "\n" + _r(0, 0, 0, 0, .015) + "\n" + _i(0) + " " * 10 + _r(.1, 5 / 6) + " " * 10 + _i(2, 0) +
            "\n/PART/902\nLower plate\n" + _i(19, 17, 0) +
            "\n/PART/903\nUpper plate\n" + _i(19, 17, 0) +
            "\n#include mesh.inc\n/END\n")
    source = directory / f"{name}_0000.rad"
    source.write_text(root)
    (directory / "mesh.inc").write_text(geometry)
    return source


def _block(raw, keyword):
    lines = raw.decode("latin1").splitlines()
    start = lines.index(keyword) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("/")), len(lines))
    return [line for line in lines[start:end] if line.strip() and not line.lstrip().startswith("#")]


def _card(session, keyword):
    return next(c for c in session.list_cards() if c["keyword"] == keyword)


def _snapshot(session):
    return (session.describe()["revision"], session.describe()["dirty"],
            tuple((c["id"], session.card_text(c["id"])) for c in session.list_cards()))


@pytest.fixture
def model(tmp_path):
    source = _base_model(tmp_path / "input")
    session = PrepSession()
    session.open_rad(str(source))
    return session, source


def _create_conditions(session):
    fixed = session.create_node_group("Support nodes", [101, 205, 309, 411], native_id=47)["card_id"]
    moving = session.create_node_group("Moving nodes", [501, 605, 709, 811], native_id=59)["card_id"]
    curve = session.create_curve("Applied load", [(0, 0), (.002, 1)], native_id=63)["card_id"]
    surface = session.create_surface("Lower shell surface", [_card(session, "/PART/902")["id"]], native_id=71)["card_id"]
    load = session.create_load("Per-node Z load", moving, curve, "Z", -.01, native_id=81)["card_id"]
    bcs = session.create_boundary_condition("Fixed support", fixed, [True, True, True], [True, True, True], native_id=83)["card_id"]
    velocity = session.create_initial_velocity("Impact speed", moving, [0, 0, -1000], native_id=89)["card_id"]
    contact = session.create_contact("Upper to lower", moving, surface, .17, native_id=97)["card_id"]
    return dict(fixed=fixed, moving=moving, curve=curve, surface=surface, load=load, bcs=bcs,
                velocity=velocity, contact=contact)


def test_conditions_create_curve_edit_undo_save_reopen_export(model, tmp_path):
    session, source = model
    mesh_before = (source.parent / "mesh.inc").read_bytes()
    ids = _create_conditions(session)
    before = session.card_text(ids["curve"])
    session.set_curve_points(ids["curve"], [(0, 0), (.0005, .75), (.002, 1)])
    assert session.card_text(ids["curve"]) != before
    assert _card(session, "/FUNCT/63")["id"] == ids["curve"]
    session.undo()
    assert session.card_text(ids["curve"]) == before
    session.redo()
    project = tmp_path / "saved.caeprep"
    session.save_project(str(project))
    shutil.rmtree(source.parent)
    reopened = PrepSession()
    reopened.open_project(str(project))
    assert _card(reopened, "/FUNCT/63")["id"] == ids["curve"]
    output = tmp_path / "export" / "conditions_0000.rad"
    reopened.export_rad(str(output))
    raw = output.read_bytes()
    assert (output.parent / "mesh.inc").read_bytes() == mesh_before
    assert b"#include mesh.inc\n" in raw
    curve = _block(raw, "/FUNCT/63")
    assert [(float(r[:20]), float(r[20:40])) for r in curve[1:]] == [(0, 0), (.0005, .75), (.002, 1)]
    for keyword, expected in (("/GRNOD/NODE/47", [101, 205, 309, 411]),
                              ("/GRNOD/NODE/59", [501, 605, 709, 811]),
                              ("/SURF/PART/71", [902])):
        assert [int(row[i:i+10]) for row in _block(raw, keyword)[1:] for i in range(0, len(row.rstrip()), 10)] == expected
    load = _block(raw, "/CLOAD/81")[1]
    assert int(load[:10]) == 63 and load[10:20] == "         Z"
    assert [int(load[i:i+10]) for i in (20, 30, 40)] == [0, 0, 59]
    assert not load[50:60].strip()
    assert (float(load[60:80]), float(load[80:100])) == (1, -.01)
    bcs = _block(raw, "/BCS/83")[1]
    assert bcs[:10] == "   111 111" and (int(bcs[10:20]), int(bcs[20:30])) == (0, 47)
    velocity = _block(raw, "/INIVEL/TRA/89")[1]
    assert [float(velocity[i:i+20]) for i in (0, 20, 40)] == [0, 0, -1000]
    assert int(velocity[60:70]) == 59 and int(velocity[70:80]) == 0
    contact = _block(raw, "/INTER/TYPE7/97")
    assert len(contact) == 7  # title and six nonoptional data rows
    assert [int(contact[1][i:i+10]) for i in (0, 10, 20, 30, 40, 60, 70, 80, 90)] == [59, 71, 1000, 0, 1, 0, 1000, 0, 0]
    assert [float(contact[4][i:i+20]) for i in (0, 20, 40, 60, 80)] == [1, .17, 0, 0, 1e30]
    assert int(contact[6][40:50]) == 2
    native_reopened = PrepSession()
    native_reopened.open_rad(str(output))
    assert native_reopened.describe()["element_count"] == 2


@pytest.mark.parametrize("points", [[], [(0, 1)], [(0, 0), (0, 1)], [(1, 0), (0, 1)],
                                   [(0, 0), (float("nan"), 1)], [(0, 0), (1, float("inf"))]])
def test_invalid_curve_points_are_rejected_atomically(model, points):
    session, _ = model
    curve = session.create_curve("Valid", [(0, 0), (1, 1)])["card_id"]
    before = _snapshot(session)
    with pytest.raises(PrepError):
        session.set_curve_points(curve, points)
    assert _snapshot(session) == before
    with pytest.raises(PrepError):
        session.create_curve("Rejected", points)
    assert _snapshot(session) == before


@pytest.mark.parametrize("node_ids", [[], [99999], [True], [101, 101], [101.0], [0]])
def test_invalid_group_members_do_not_create_partial_cards(model, node_ids):
    session, _ = model
    before = _snapshot(session)
    with pytest.raises(PrepError):
        session.create_node_group("Invalid group", node_ids)
    assert _snapshot(session) == before


def test_condition_reference_types_and_values_are_checked_before_mutation(model):
    session, _ = model
    ids = _create_conditions(session)
    before = _snapshot(session)
    operations = [
        lambda: session.create_load("Wrong group", ids["surface"], ids["curve"], "X", 1),
        lambda: session.create_load("Wrong curve", ids["moving"], ids["surface"], "X", 1),
        lambda: session.create_load("Dangling", ids["moving"], str(uuid4()), "X", 1),
        lambda: session.create_load("Wrong direction", ids["moving"], ids["curve"], "XY", 1),
        lambda: session.create_load("Nonfinite", ids["moving"], ids["curve"], "X", float("inf")),
        lambda: session.create_surface("Wrong part", [ids["moving"]]),
        lambda: session.create_boundary_condition("Wrong DOF", ids["fixed"], [1, 2, 0], [0, 0, 0]),
        lambda: session.create_initial_velocity("Wrong vector", ids["moving"], [0, 0]),
        lambda: session.create_initial_velocity("Nonfinite", ids["moving"], [0, float("nan"), 0]),
        lambda: session.create_contact("Wrong secondary", ids["surface"], ids["surface"], .1),
        lambda: session.create_contact("Wrong main", ids["moving"], ids["moving"], .1),
        lambda: session.create_contact("Bad friction", ids["moving"], ids["surface"], -.1),
    ]
    for operation in operations:
        with pytest.raises(PrepError):
            operation()
        assert _snapshot(session) == before


def test_existing_curve_rows_preserve_id_comments_and_other_cards(model):
    _, source = model
    extra = ("/FUNCT/406\nExisting measured load\n# measured data comment  \n" + _r(0, 2) +
             "\n# instrument calibration remains\n" + _r(1, 3) + "\n")
    source.write_text(source.read_text().replace("/END\n", extra + "/END\n"))
    session = PrepSession()
    session.open_rad(str(source))
    curve = _card(session, "/FUNCT/406")
    untouched = {c["id"]: session.card_text(c["id"]) for c in session.list_cards() if c["id"] != curve["id"]}
    session.set_curve_points(curve["id"], [(0, 10), (.3, 20), (.9, 15), (1, 0)])
    text = session.card_text(curve["id"])
    assert "# measured data comment  \n" in text
    assert "# instrument calibration remains\n" in text
    assert len(_block(text.encode("latin1"), "/FUNCT/406")) == 5
    assert {c["id"]: session.card_text(c["id"]) for c in session.list_cards() if c["id"] != curve["id"]} == untouched


def test_curve_id_conflicts_with_table_namespace(model):
    _, source = model
    # The opaque table is retained; its ID still reserves the function namespace.
    source.write_text(source.read_text().replace("/END\n", "/TABLE/1/406\nExisting table\n         1\n/END\n"))
    session = PrepSession()
    session.open_rad(str(source))
    before = _snapshot(session)
    with pytest.raises(PrepError):
        session.create_curve("Conflicting curve", [(0, 0), (1, 1)], native_id=406)
    assert _snapshot(session) == before


def test_referenced_condition_objects_cannot_be_deleted_and_leaf_delete_undo_works(model):
    session, _ = model
    ids = _create_conditions(session)
    before = _snapshot(session)
    for key in ("fixed", "moving", "curve", "surface"):
        with pytest.raises(PrepError) as error:
            session.delete_card(ids[key])
        assert error.value.code == "card_in_use"
        assert _snapshot(session) == before
    original_load = session.card_text(ids["load"])
    session.delete_card(ids["load"])
    session.undo()
    assert session.card_text(ids["load"]) == original_load
    session.redo()
    session.delete_card(ids["curve"])
    assert not any(c["id"] in {ids["load"], ids["curve"]} for c in session.list_cards())


def test_group_with_more_than_ten_nodes_uses_continuation_rows(model):
    _, source = model
    mesh = source.parent / "mesh.inc"
    additions = "\n".join(_i(n) + _r(n, 0, 0) for n in (9001, 9003, 9007, 9011))
    mesh.write_text(mesh.read_text().replace("/SHELL/902", additions + "\n/SHELL/902"))
    session = PrepSession()
    session.open_rad(str(source))
    members = [101, 205, 309, 411, 501, 605, 709, 811, 9001, 9003, 9007, 9011]
    result = session.create_node_group("Twelve selected nodes", members, native_id=157)
    data = _block(session.card_text(result["card_id"]).encode("latin1"), "/GRNOD/NODE/157")
    assert len(data) == 3 and len(data[1]) == 100
    assert [int(row[i:i+10]) for row in data[1:] for i in range(0, len(row.rstrip()), 10)] == members


def test_surface_rejects_solid_part_instead_of_silently_ignoring_volume_elements(model):
    _, source = model
    mesh = source.parent / "mesh.inc"
    mesh.write_text(mesh.read_text() + "/BRICK/903\n" + _i(9901, 101, 205, 309, 411, 501, 605, 709, 811) + "\n")
    session = PrepSession()
    session.open_rad(str(source))
    before = _snapshot(session)
    with pytest.raises(PrepError):
        session.create_surface("Mixed shell and solid", [_card(session, "/PART/903")["id"]])
    assert _snapshot(session) == before
