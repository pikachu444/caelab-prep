"""Native TEXT shares provider commands without replacing native card blocks."""
from dataclasses import replace

import pytest

from caelab_prep.application.card_text import prepare_card_text
from caelab_prep.application.contracts import SetProperties
from caelab_prep.application.rad_provider import RadProvider
from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError
from test_modeling_workflow import user_model
from test_node_moves import opened as mixed
from test_rad_provider import opened, node


def changed(draft, **values):
    lines = draft.ui_text.splitlines(keepends=True)
    for item in draft._fields:
        if item.name in values:
            line = lines[item.line]
            body, ending = line.rstrip("\n"), "\n" if line.endswith("\n") else ""
            value = str(values[item.name]).rjust(item.stop - item.start)
            assert len(value) == item.stop - item.start
            lines[item.line] = body.ljust(item.stop)[:item.start] + value + body[item.stop:] + ending
    return "".join(lines)


def state(session):
    return session.document.revision, session.document.tokens(), session.describe()["can_undo"]


def test_mixed_include_multi_field_text_uses_one_existing_command_and_native_units(user_model):
    session = user_model[0]; provider = RadProvider(session)
    target = node(provider, "/MAT/ELAST/00017").ref
    draft = prepare_card_text(provider, target)
    assert draft.target == target and draft.revision == 0 and "\r\n" in draft.baseline
    before = state(session); originals = {r.id: r.raw for r in session._deck_resources()}
    values = draft.changes(provider, changed(draft, density="2.8D-9", young_modulus="71234", poisson_ratio=".29"))
    assert values == {"density": 2.8e-9, "young_modulus": 71234, "poisson_ratio": .29}
    assert state(session) == before
    events = []; session.subscribe(events.append)
    provider.submit(SetProperties(target, values, draft.revision))
    assert len(events) == 1 and session.document.revision == 1
    assert {f["name"]: f["value"] for f in session.card_fields(target.object_id)} == values
    assert {r.id: r.raw for r in session._deck_resources()} == originals
    assert "\r\n" in session.card_text(target.object_id)
    session.undo(); assert session.card_text(target.object_id) == draft.baseline


def test_full_current_render_and_lf_noop_preserve_history(user_model):
    session = user_model[0]; provider = RadProvider(session)
    target = node(provider, "/MAT/ELAST/00017").ref
    provider.submit(SetProperties(target, {"young_modulus": 70000}, 0))
    draft = prepare_card_text(provider, target)
    assert "70000" in draft.baseline and draft.baseline == session.card_text(target.object_id)
    before = state(session)
    assert draft.changes(provider, draft.baseline) == draft.changes(provider, draft.ui_text) == {}
    assert state(session) == before


@pytest.mark.parametrize("bad", ["1e", "NaN", "-1"])
def test_malformed_or_out_of_range_field_never_mutates_a_valid_prefix(user_model, bad):
    session = user_model[0]; provider = RadProvider(session)
    draft = prepare_card_text(provider, node(provider, "/MAT/ELAST/00017").ref)
    text = changed(draft, density="2.8e-9", young_modulus=bad)
    before = state(session)
    with pytest.raises(PrepError): draft.changes(provider, text)
    assert state(session) == before and session.card_text(draft.target.object_id) == draft.baseline


@pytest.mark.parametrize("damage", ["header", "comment", "row", "final_newline", "shift", "encoding", "nul"])
def test_structural_and_unowned_bytes_are_rejected(user_model, damage):
    session, inputs = user_model[:2]
    parts = inputs / "parts.inc"
    parts.write_bytes(parts.read_bytes().replace(b"Existing aluminium\r\n", b"Existing aluminium\r\n# keep this comment  \r\n"))
    session.open_rad(inputs / "assembly_0000.rad"); provider = RadProvider(session)
    draft = prepare_card_text(provider, node(provider, "/MAT/ELAST/00017").ref)
    text = changed(draft, young_modulus="71000")
    if damage == "header": text = text.replace("/MAT/ELAST/00017", "/MAT/ELAST/00018")
    elif damage == "comment": text = text.replace("# keep this comment  ", "# altered comment    ")
    elif damage == "row": text = text.replace("# keep this comment  \n", "")
    elif damage == "final_newline": text = text.rstrip("\n")
    elif damage == "shift": text = text.replace("71000", "710000", 1)
    elif damage == "encoding": text = text.replace("Existing aluminium", "한글")
    else: text = text.replace("Existing aluminium\n", "Existing aluminium\0\n")
    before = state(session)
    with pytest.raises(PrepError): draft.changes(provider, text)
    assert state(session) == before


@pytest.mark.parametrize("change", ["revision", "epoch", "baseline", "resource"])
def test_stale_document_epoch_baseline_and_identity_are_rejected(user_model, tmp_path, change):
    session = user_model[0]; provider = RadProvider(session)
    if change == "epoch":
        project = tmp_path / "same.caeprep"; session.save_project(project)
    draft = prepare_card_text(provider, node(provider, "/MAT/ELAST/00017").ref)
    text = changed(draft, young_modulus="71000")
    if change == "epoch":
        session = PrepSession(); provider = RadProvider(session)
        session.open_project(project)
        assert session.document.id == draft.target.document_id and session.document.revision == draft.revision
    elif change == "revision": provider.submit(SetProperties(draft.target, {"poisson_ratio": .28}, draft.revision))
    elif change == "resource": draft = replace(draft, target=replace(draft.target, resource_id="wrong-resource"))
    else:
        owner = session._find_card(draft.target.object_id)
        owner.restore(owner.fields_state(draft.target.object_id, {"poisson_ratio": .28}))
        assert session.document.revision == draft.revision
    before = state(session)
    with pytest.raises(PrepError) as error: draft.changes(provider, text)
    assert error.value.code == "stale_card_text" and state(session) == before


def test_part_ids_resolve_to_existing_typed_assignment_choices(user_model):
    session = user_model[0]; provider = RadProvider(session)
    material = session.create_material("Other", 8e-9, 200000, .3, native_id=41)["card_id"]
    prop = session.create_shell_property("Other section", 2, native_id=207)["card_id"]
    draft = prepare_card_text(provider, node(provider, "/PART/902").ref)
    before = state(session)
    with pytest.raises(PrepError): draft.changes(provider, changed(draft, material_id=999))
    assert state(session) == before
    values = draft.changes(provider, changed(draft, property_id=207, material_id=41))
    assert values["material"].object_id == material and values["property"].object_id == prop
    provider.submit(SetProperties(draft.target, values, draft.revision))
    assignments = session.part_assignments(draft.target.object_id)
    assert assignments["material_id"] == material and assignments["property_id"] == prop


@pytest.mark.parametrize("name,keyword", [("beam_shell_tet", "/PROP/BEAM/22"),
                                         ("truss_shell_hex", "/PROP/TRUSS/22")])
def test_beam_and_truss_scalar_names_use_native_property_commands(name, keyword):
    session = mixed(name); provider = RadProvider(session)
    draft = prepare_card_text(provider, node(provider, keyword).ref)
    values = draft.changes(provider, changed(draft, area=3.5))
    assert values == {"area": 3.5}
    provider.submit(SetProperties(draft.target, values, draft.revision))
    assert next(spec.value for spec in provider.properties(draft.target) if spec.name == "area") == 3.5


def test_type7_friction_uses_the_existing_condition_command():
    session, provider = opened()
    group = node(provider, "/GRNOD/NODE/1").ref.object_id
    surface = session.create_surface("Main", [node(provider, "/PART/1").ref.object_id])["card_id"]
    contact = session.create_contact("Pair", group, surface, .2)["card_id"]
    target = provider.ref_for_card(next(card for card in session.list_cards() if card["id"] == contact))
    draft = prepare_card_text(provider, target)
    values = draft.changes(provider, changed(draft, friction=.4))
    assert values == {"friction": .4}
    provider.submit(SetProperties(target, values, draft.revision))
    assert session.condition_values(contact)["friction"] == .4


def test_readonly_or_nonnative_provider_defaults_disable_text_support(monkeypatch):
    session, provider = opened()
    target = node(provider, "/MAT/LAW1/1").ref
    original = provider.properties
    for spec_change in ({"editable": False}, {"unit_scales": (("MPa", 1000.),), "unit": "MPa"}):
        monkeypatch.setattr(provider, "properties", lambda ref: tuple(
            replace(spec, **spec_change) if spec.name == "young_modulus" else spec for spec in original(ref)))
        before = state(session)
        with pytest.raises(PrepError) as error: prepare_card_text(provider, target)
        assert error.value.code == "unsupported_card_text" and state(session) == before


@pytest.mark.parametrize("keyword,fields,expected", [
    ("/FUNCT/1", {"point_1_y": 45}, {"points": ((0., 0.), (.1, 45.), (.3, 80.))}),
    ("/INIVEL/TRA/1", {"vx": 10, "vy": 20, "vz": -30}, {"velocity": (10., 20., -30.)}),
    ("/BCS/1", {"tx": 0, "ry": 0}, {"translations": (False, True, True), "rotations": (True, False, True)}),
])
def test_curve_vector_and_boolean_fields_use_existing_logical_commands(keyword, fields, expected):
    session, provider = opened()
    draft = prepare_card_text(provider, node(provider, keyword).ref)
    before = state(session)
    values = draft.changes(provider, changed(draft, **fields))
    assert values == expected and state(session) == before
    provider.submit(SetProperties(draft.target, values, draft.revision))
    actual = {spec.name: spec.value for spec in provider.properties(draft.target)}
    assert all(actual[name] == value for name, value in expected.items())
    assert session.document.revision == 1
    session.undo(); assert session.card_text(draft.target.object_id) == draft.baseline


def test_unknown_and_partial_curve_fields_are_explicitly_unsupported(tmp_path):
    session, provider = opened()
    with pytest.raises(PrepError): prepare_card_text(provider, node(provider, "/PRESERVED/EDITOR/91").ref)
    source = tmp_path / "partial.rad"
    source.write_text("/FUNCT/1\nPartial\n" + f"{0:20g}{1:20g}\n{'bad':>20}{2:20g}\n/END\n", encoding="ascii")
    session.open_rad(source)
    before = state(session)
    with pytest.raises(PrepError): prepare_card_text(provider, node(provider, "/FUNCT/1").ref)
    assert state(session) == before


@pytest.mark.parametrize("layout", ["curve_suffix", "curve_missing_eol", "boundary_alignment", "boundary_padding"])
def test_specialized_writer_layouts_that_cannot_preserve_protected_bytes_are_disabled(tmp_path, layout):
    session, provider = opened()
    keyword = "/FUNCT/1" if layout.startswith("curve") else "/BCS/1"
    original = session.card_text(node(provider, keyword).ref.object_id)
    raw = session._deck_resources()[0].render()
    if layout == "curve_suffix":
        lines = original.splitlines(keepends=True)
        lines[2] = lines[2].rstrip("\r\n") + "  # native suffix\n"
        raw = raw.replace(original.encode("latin1"), "".join(lines).encode("latin1"))
    elif layout == "curve_missing_eol": raw = original.rstrip("\r\n").encode("latin1")
    elif layout == "boundary_alignment": raw = raw.replace(b"   111 111", b"111    111")
    else: raw = raw.replace(b"   111 111", b" \t 111 111")
    source = tmp_path / "layout.rad"; source.write_bytes(raw)
    session.open_rad(source)
    before = state(session)
    with pytest.raises(PrepError) as error: prepare_card_text(provider, node(provider, keyword).ref)
    assert error.value.code == "unsupported_card_text" and state(session) == before
