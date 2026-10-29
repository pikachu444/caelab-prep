from pathlib import Path

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.radioss import DeckResource


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts/evaluation/models/two_shell_plates_0000.rad"


def card(session, keyword):
    return next(c for c in session.list_cards() if c["keyword"] == keyword)


def test_unchanged_unknown_card_and_crlf_are_byte_identical(tmp_path):
    original = FIXTURE.read_bytes().replace(b"\n", b"\r\n").replace(b"/END", b"/SOME/FUTURE/CARD/77\r\nuntouched payload  \r\n/END")
    source = tmp_path / "input.rad"; source.write_bytes(original)
    session = PrepSession(); session.open_rad(str(source))
    session.export_rad(str(tmp_path / "export.rad"))
    assert (tmp_path / "export.rad").read_bytes() == original
    unknown = card(session, "/SOME/FUTURE/CARD/77")
    assert session.card_fields(unknown["id"]) == []
    with pytest.raises(PrepError) as error:
        session.set_field(unknown["id"], "guessed", 1)
    assert error.value.code == "field_not_writable"
    assert not session.describe()["dirty"]


def test_material_and_bcs_patch_only_the_target_bytes(tmp_path):
    session = PrepSession(); session.open_rad(str(FIXTURE))
    material = card(session, "/MAT/PLAS_TAB/1")
    constraint = card(session, "/BCS/1")
    before_bcs = session.card_text(constraint["id"])
    session.set_field(material["id"], "young_modulus", 205000, expected_revision=0)
    session.set_field(constraint["id"], "tx", False, expected_revision=1)
    bcs = session.card_text(constraint["id"])
    assert bcs.replace("   011 111", "   111 111") == before_bcs
    session.export_rad(str(tmp_path / "edited.rad"))
    expected = FIXTURE.read_bytes().replace(b"              210000", b"            205000.0", 1).replace(b"   111 111", b"   011 111", 1)
    assert (tmp_path / "edited.rad").read_bytes() == expected
    assert session.card_fields(material["id"])[1]["units"]["global"] == {"mass": "Mg", "length": "mm", "time": "s"}


def test_invalid_and_stale_edits_leave_document_unchanged():
    session = PrepSession(); session.open_rad(str(FIXTURE))
    material = card(session, "/MAT/PLAS_TAB/1")
    before = session.card_text(material["id"])
    for value in [-1, float("nan"), float("inf"), True]:
        with pytest.raises(PrepError): session.set_field(material["id"], "young_modulus", value)
    assert session.describe()["revision"] == 0
    assert not session.describe()["dirty"] and session.card_text(material["id"]) == before
    session.set_field(material["id"], "young_modulus", 205000)
    with pytest.raises(PrepError) as error:
        session.set_field(material["id"], "young_modulus", 200000, expected_revision=0)
    assert error.value.code == "revision_conflict"
    assert session.describe()["revision"] == 1


def test_selection_tracks_resource_and_original_id_without_dirtying():
    session = PrepSession(); session.open_rad(str(FIXTURE))
    result = session.select_entity("element", 2)
    assert result["refs"][0]["local_id"] == 2
    assert result["refs"][0]["entity_kind"] == "element"
    assert result["refs"][0]["resource_id"]
    assert not session.describe()["dirty"] and session.describe()["revision"] == 0
    view = session.mesh_view(); view["points"][0][0] = 12345
    assert session.mesh_view()["points"][0][0] == 0


def test_malformed_bcs_is_preserved_and_not_guessed():
    resource = DeckResource(b"/BCS/1\nName\n111 111            0         1\n/END\n")
    assert resource.card_fields(resource.cards[0].id) == []
    assert resource.render() == resource.raw


def test_law_alias_and_card_unit_override():
    raw = ("/MAT/ELAST/12/77\nSteel\n" + f"{7.8e-9:20g}\n" + f"{210000:20g}{.3:20g}\n/END\n").encode()
    resource = DeckResource(raw)
    fields = resource.card_fields(resource.cards[0].id)
    assert fields[1]["name"] == "young_modulus" and fields[1]["value"] == 210000
    assert fields[1]["units"] == {"basis": "input_deck", "global": None, "unit_id": "77"}


def test_session_notifications_follow_model_replacement_and_selection(tmp_path):
    session = PrepSession(); events = []
    unsubscribe = session.subscribe(events.append)
    session.open_rad(str(FIXTURE))
    material = card(session, "/MAT/PLAS_TAB/1")
    session.set_field(material["id"], "young_modulus", 205000)
    session.select_entity("node", 1)
    assert session.clear_selection()["refs"] == []
    session.save_project(str(tmp_path / "a.caeprep"))
    session.open_project(str(tmp_path / "a.caeprep"))
    assert [e["kind"] for e in events] == ["document", "field", "selection", "selection", "save", "document"]
    assert events[1]["change"]["revision"] == 1
    unsubscribe()
    session.select_entity("node", 1)
    assert len(events) == 6
    assert session.describe()["source_path"] is None
