"""Effective defaults must agree with native semantics without rewriting raw cards.

Radioss 2024 CLOAD: blank/zero Fscale_y selects 1.0.
TYPE7: Fric is zero by default for constant Coulomb friction, but blank/zero
selects 1.0 when fct_ID_F is present. Both were checked with the actual Starter.
"""
from pathlib import Path

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.radioss import DeckResource

SOURCE = Path(__file__).resolve().parents[1] / "examples/rad/shell_panels_0000.rad"


def _card(session, keyword):
    return next(card for card in session.list_cards() if card["keyword"] == keyword)


def _original(tmp_path, field_text, *, function=0, newline="\n"):
    source = tmp_path / "base.rad"
    source.write_bytes(SOURCE.read_bytes().split(b"/PRESERVED/EDITOR/91", 1)[0] + b"/END\n")
    session = PrepSession()
    session.open_rad(source)
    group, curve = _card(session, "/GRNOD/NODE/1")["id"], _card(session, "/FUNCT/1")["id"]
    surface = session.create_surface("Surface", [_card(session, "/PART/1")["id"]], native_id=71)["card_id"]
    session.create_contact("Contact", group, surface, .2, native_id=97)
    session.create_load("Load", group, curve, "X", 2, native_id=81)
    exported = tmp_path / "input.rad"
    session.export_rad(exported)
    lines = exported.read_bytes().decode("latin1").splitlines()
    load = lines.index("/CLOAD/81")
    contact = lines.index("/INTER/TYPE7/97")
    lines[load + 2] = lines[load + 2][:80] + field_text.rjust(20)
    lines[contact + 5] = lines[contact + 5][:20] + field_text.rjust(20) + lines[contact + 5][40:]
    lines[contact + 7] = lines[contact + 7][:60] + f"{function:10d}" + lines[contact + 7][70:]
    exported.write_bytes((newline.join(lines) + newline).encode("latin1"))
    reopened = PrepSession()
    reopened.open_rad(exported)
    return reopened, exported


@pytest.mark.parametrize("raw", ["", "0", "0.0", "-0.0"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_load_default_read_edit_reopen_and_undo_preserve_native_sentinel(tmp_path, raw, newline):
    session, source = _original(tmp_path, raw, newline=newline)
    load = _card(session, "/CLOAD/81")["id"]
    original = session.card_text(load)
    assert session.condition_values(load)["scale"] == 1.0
    assert not session.describe()["dirty"]
    assert session.set_condition_values(load, {"scale": 1})["change"] is None
    assert session.card_text(load) == original
    session.set_condition_values(load, {"direction": "Z"})
    changed = session.card_text(load)
    assert changed.splitlines()[2][80:100] == raw.rjust(20)
    assert changed.splitlines()[2][10:20] == "         Z"
    session.undo()
    assert session.card_text(load) == original and not session.describe()["dirty"]
    session.set_condition_values(load, {"scale": -3.25})
    assert float(session.card_text(load).splitlines()[2][80:100]) == -3.25
    project = tmp_path / "saved.caeprep"
    session.save_project(project)
    check = PrepSession()
    check.open_project(project)
    assert check.condition_values(load)["scale"] == -3.25
    output = tmp_path / "edited.rad"
    check.export_rad(output)
    native = PrepSession()
    native.open_rad(output)
    assert native.condition_values(_card(native, "/CLOAD/81")["id"])["scale"] == -3.25
    session.undo()
    assert session.card_text(load) == original
    assert source.read_bytes().decode("latin1").find(original) >= 0


@pytest.mark.parametrize("raw", ["", "0", "2"])
def test_zero_load_requests_are_rejected_without_creating_or_changing_a_card(tmp_path, raw):
    session, _ = _original(tmp_path, raw)
    load = _card(session, "/CLOAD/81")["id"]
    before = session.describe()["revision"], tuple((card["id"], session.card_text(card["id"])) for card in session.list_cards())
    for value in (0, -0.0, "0"):
        with pytest.raises(PrepError) as caught:
            session.set_condition_values(load, {"direction": "Y", "scale": value})
        assert caught.value.code == "native_default_value"
        with pytest.raises(PrepError) as caught:
            session.create_load("Zero request", _card(session, "/GRNOD/NODE/1")["id"], _card(session, "/FUNCT/1")["id"], "X", value)
        assert caught.value.code == "native_default_value"
        assert (session.describe()["revision"], tuple((card["id"], session.card_text(card["id"])) for card in session.list_cards())) == before


@pytest.mark.parametrize("function,expected", [(0, 0.0), (1, 1.0)])
@pytest.mark.parametrize("raw", ["", "0", "0.0"])
def test_contact_defaults_depend_on_function_and_match_both_editing_paths(tmp_path, function, expected, raw):
    session, _ = _original(tmp_path, raw, function=function)
    contact = _card(session, "/INTER/TYPE7/97")["id"]
    original = session.card_text(contact)
    values = session.condition_values(contact)
    assert values["friction"] == expected and values["friction_is_scale"] is bool(function)
    assert next(field["value"] for field in session.card_fields(contact) if field["name"] == "friction") == expected
    assert session.set_condition_values(contact, {"friction": expected})["change"] is None
    assert session.card_text(contact) == original
    if function:
        for edit in (lambda: session.set_condition_values(contact, {"friction": 0}),
                     lambda: session.set_field(contact, "friction", 0)):
            with pytest.raises(PrepError) as caught: edit()
            assert caught.value.code == "native_default_value"
            assert session.card_text(contact) == original
    session.set_condition_values(contact, {"friction": .35})
    assert float(session.card_text(contact).splitlines()[5][20:40]) == .35
    session.undo()
    assert session.card_text(contact) == original


def test_legacy_zero_friction_patch_preserves_native_text_but_reports_effective_default(tmp_path):
    session, _ = _original(tmp_path, ".2", function=1)
    card = _card(session, "/INTER/TYPE7/97")
    resource = session.document.resources[card["resource_id"]]
    legacy = DeckResource(resource.raw, resource_id=resource.id)
    legacy.restore({card["id"]: {"friction": 0.0}})
    assert next(field["value"] for field in legacy.card_fields(card["id"]) if field["name"] == "friction") == 1
    assert legacy.snapshot()["patches"][card["id"]]["friction"] == 0
    before = legacy.render()
    legacy.restore(legacy.fields_state(card["id"], {"friction": 1}))
    assert legacy.render() == before
    with pytest.raises(PrepError) as caught: legacy.fields_state(card["id"], {"friction": 0})
    assert caught.value.code == "native_default_value"


def test_unknown_contact_function_field_fails_closed_without_guessing_a_default(tmp_path):
    session, source = _original(tmp_path, "", function=1)
    raw = source.read_bytes()
    lines = raw.decode("latin1").splitlines()
    contact = lines.index("/INTER/TYPE7/97")
    lines[contact + 7] = lines[contact + 7][:60] + "   invalid" + lines[contact + 7][70:]
    source.write_bytes(("\n".join(lines) + "\n").encode("latin1"))
    session = PrepSession()
    session.open_rad(source)
    card = _card(session, "/INTER/TYPE7/97")["id"]
    before = session.card_text(card)
    with pytest.raises(PrepError) as caught: session.condition_values(card)
    assert caught.value.code == "invalid_card"
    with pytest.raises(PrepError): session.set_condition_values(card, {"friction": .5})
    assert session.card_text(card) == before and not session.describe()["dirty"]
    assert not any(field["name"] == "friction" for field in session.card_fields(card))
