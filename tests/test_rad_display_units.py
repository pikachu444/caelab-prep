"""Display quantities return to declared native dimensions in one command."""
import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.contracts import OperationRequest, SetProperties
from caelab_prep.application.rad_provider import RadProvider
from caelab_prep.cae_core import PrepError


def _material(mass="Mg", length="mm", time="s"):
    session = PrepSession()
    session.new_document("units", dict(mass=mass, length=length, time=time))
    card_id = session.create_material("Steel", 7.8e-9, 210000, .3)["card_id"]
    provider = RadProvider(session)
    target = provider.ref_for_card(next(c for c in session.list_cards() if c["id"] == card_id))
    return session, provider, target


def test_stress_density_display_conversion_commits_once_and_undo_restores_raw():
    session, provider, target = _material()
    before = session.card_text(target.object_id)
    revision = session.describe()["revision"]
    specs = {p.name: p for p in provider.properties(target)}
    assert specs["young_modulus"].unit == "MPa"
    assert dict(specs["density"].unit_scales)["g/cm³"] == pytest.approx(1e-9)
    assert session.describe()["revision"] == revision  # Reading display units commits nothing.
    provider.submit(SetProperties(target, {"young_modulus": 203, "density": 7.91}, revision,
                                  {"young_modulus": "GPa", "density": "g/cm³"}))
    assert session.describe()["revision"] == revision + 1
    fields = {f["name"]: f["value"] for f in session.card_fields(target.object_id)}
    assert fields["young_modulus"] == 203000 and fields["density"] == pytest.approx(7.91e-9)
    session.undo()
    assert session.card_text(target.object_id) == before
    # Equivalent display quantities must not create a rounding-only revision.
    revision = session.describe()["revision"]
    provider.submit(SetProperties(target, {"young_modulus": 210, "density": 7.8}, revision,
                                  {"young_modulus": "GPa", "density": "g/cm³"}))
    assert session.describe()["revision"] == revision


def test_creation_operation_receives_display_units_and_converts_before_native_validation():
    session = PrepSession(); session.new_document("units", dict(mass="kg", length="m", time="s"))
    provider = RadProvider(session); spec = provider.operation_spec("material.create")
    values = {f.name: f.value for f in spec.fields}
    values.update(density=7.8, young_modulus=210, poisson_ratio=.3)
    created = provider.execute_operation(OperationRequest(spec.key, values, spec.document_id, spec.expected_revision,
                                        units={"density": "g/cm³", "young_modulus": "GPa"}))
    fields = {f["name"]: f["value"] for f in session.card_fields(created["card_id"])}
    assert fields["density"] == 7800 and fields["young_modulus"] == 210e9


@pytest.mark.parametrize("value,unit", [(float("nan"), "GPa"), ("unfinished-", "GPa"), (1, "mm"), (True, "GPa")])
def test_invalid_unit_or_numeric_draft_never_partially_applies(value, unit):
    session, provider, target = _material()
    before = session.card_text(target.object_id); revision = session.describe()["revision"]
    with pytest.raises(PrepError):
        provider.submit(SetProperties(target, {"density": 8, "young_modulus": value}, revision,
                                      {"density": "g/cm³", "young_modulus": unit}))
    assert session.card_text(target.object_id) == before and session.describe()["revision"] == revision


def test_unknown_and_property_override_units_do_not_offer_false_conversions(tmp_path):
    session, provider, target = _material()
    section = session.create_shell_property("Section", 2)["card_id"]
    path = tmp_path / "override.rad"; session.export_rad(str(path))
    path.write_text(path.read_text().replace("/PROP/SHELL/1", "/PROP/SHELL/1/77").replace("/MAT/LAW1/1", "/MAT/LAW1/1/77"))
    session.open_rad(str(path))
    for card in session.list_cards():
        if card["category"] not in ("Materials", "Properties"): continue
        ref = provider.ref_for_card(card)
        for spec in provider.properties(ref):
            assert not spec.unit_choices and spec.unit_context["display_conversion"] == "unavailable"
    # Unrecognized global symbols are not interpreted as SI.
    path.write_text(path.read_text().replace("/77", "").replace("                  Mg", "               slug"))
    session.open_rad(str(path))
    ref = provider.ref_for_card(next(c for c in session.list_cards() if c["category"] == "Materials"))
    assert all(not spec.unit_choices for spec in provider.properties(ref))


def test_thickness_velocity_force_and_moment_dimensions(tmp_path):
    # Reuse only an independent raw input builder, never a product field writer.
    from test_condition_workflow import _base_model, _create_conditions
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / "input")))
    ids = _create_conditions(session); provider = RadProvider(session)
    def ref(identifier): return provider.ref_for_card(next(c for c in session.list_cards() if c["id"] == identifier))
    velocity = ref(ids["velocity"])
    provider.submit(SetProperties(velocity, {"velocity": [2, -.5, .25]}, session.describe()["revision"], {"velocity": "m/s"}))
    assert session.condition_values(ids["velocity"])["velocity"] == [2000, -500, 250]
    load = ref(ids["load"])
    revision = session.describe()["revision"]
    moment_spec = next(f for f in provider.properties(load, {"direction": "XX"}) if f.name == "scale")
    assert moment_spec.unit_context["quantity"] == "moment" and moment_spec.unit == "N·mm"
    assert "kN" not in moment_spec.unit_choices and session.describe()["revision"] == revision
    create_spec = provider.operation_spec("load.create", draft_values={"direction": "ZZ"})
    assert next(f for f in create_spec.fields if f.name == "scale").unit_context["quantity"] == "moment"
    provider.submit(SetProperties(load, {"scale": 2}, session.describe()["revision"], {"scale": "kN"}))
    assert session.condition_values(ids["load"])["scale"] == 2000
    provider.submit(SetProperties(load, {"direction": "XX", "scale": 2}, session.describe()["revision"], {"scale": "N·m"}))
    assert session.condition_values(ids["load"])["scale"] == 2000  # Mg·mm²/s² = N·mm.
    section = next(c for c in session.list_cards() if c["category"] == "Properties")
    provider.submit(SetProperties(provider.ref_for_card(section), {"thickness": .25}, session.describe()["revision"], {"thickness": "cm"}))
    assert session.card_fields(section["id"])[0]["value"] == 2.5
    curve_spec = provider.properties(ref(ids["curve"]))[0]
    assert not curve_spec.unit_choices and "no declared physical dimension" in curve_spec.unit_context["reason"]


def test_cli_explicit_display_units_are_stored_as_native_values(tmp_path):
    from test_modeling_commands import cli
    project = tmp_path / "base.caeprep"
    assert cli("new", "--name", "units", "--mass", "Mg", "--length", "mm", "--time", "s", "--output", project)[0] == 0
    converted = tmp_path / "converted.caeprep"
    code, result = cli("model", project, "material.create", "--set", "density=7.91", "--unit", "density=g/cm³",
                       "--set", "young_modulus=203", "--unit", "young_modulus=GPa", "--output", converted)
    assert code == 0, result
    session = PrepSession(); session.open_project(str(converted))
    material = next(c for c in session.list_cards() if c["category"] == "Materials")
    values = {f["name"]: f["value"] for f in session.card_fields(material["id"])}
    assert values["density"] == 7.91e-9 and values["young_modulus"] == 203000


def test_load_direction_change_does_not_bypass_per_card_unit_override(tmp_path):
    from test_condition_workflow import _base_model, _create_conditions
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / "input")))
    ids = _create_conditions(session)
    load = next(c for c in session.list_cards() if c["id"] == ids["load"])
    path = tmp_path / "override.rad"; session.export_rad(str(path))
    path.write_text(path.read_text().replace(load["keyword"] + "\n", load["keyword"] + "/77\n"))
    session.open_rad(str(path)); provider = RadProvider(session)
    target = provider.ref_for_card(next(c for c in session.list_cards() if c["keyword"].startswith("/CLOAD/")))
    spec = next(f for f in provider.properties(target, {"direction": "XX"}) if f.name == "scale")
    assert spec.unit_context["quantity"] == "moment" and not spec.unit_choices
    before = session.card_text(target.object_id); revision = session.describe()["revision"]
    with pytest.raises(PrepError) as error:
        provider.submit(SetProperties(target, {"direction": "XX", "scale": 2}, revision, {"scale": "N·m"}))
    assert error.value.code == "invalid_unit"
    assert session.card_text(target.object_id) == before and session.describe()["revision"] == revision


@pytest.mark.parametrize("function_id,friction_field,expected_label,expected_value", [
    (0, "0.17", "Friction coefficient", .17),
    (63, "", "Friction function scale", 1.),
    (63, "0", "Friction function scale", 1.),
])
def test_type7_friction_label_tracks_native_function_and_stays_dimensionless(
        tmp_path, function_id, friction_field, expected_label, expected_value):
    from test_condition_workflow import _base_model, _create_conditions
    session = PrepSession(); session.open_rad(str(_base_model(tmp_path / "input")))
    _create_conditions(session)
    source = tmp_path / "contact.rad"; session.export_rad(str(source))
    # Independent fixed-column mutation of the ordinary TYPE7 source profile:
    # data row 4 has Fric, data row 6 has fct_ID_F. Preserve every other byte.
    lines = source.read_bytes().splitlines(keepends=True)
    header = next(i for i, line in enumerate(lines) if line.rstrip(b"\r\n") == b"/INTER/TYPE7/97")
    lines[header + 5] = lines[header + 5][:20] + friction_field.rjust(20).encode("ascii") + lines[header + 5][40:]
    lines[header + 7] = lines[header + 7][:60] + f"{function_id:10d}".encode("ascii") + lines[header + 7][70:]
    source.write_bytes(b"".join(lines))
    session.open_rad(str(source)); provider = RadProvider(session)
    target = provider.ref_for_card(next(card for card in session.list_cards() if card["keyword"] == "/INTER/TYPE7/97"))
    for fields in (provider.properties(target), provider.operation_spec("object.edit", target).fields):
        spec = next(field for field in fields if field.name == "friction")
        assert spec.label == expected_label and spec.value == expected_value
        assert spec.unit == "" and not spec.unit_choices and not spec.unit_scales
    creation = next(field for field in provider.operation_spec("contact.create").fields if field.name == "friction")
    assert creation.label == "Friction coefficient"
    before = session.card_text(target.object_id); revision = session.describe()["revision"]
    with pytest.raises(PrepError):
        provider.submit(SetProperties(target, {"friction": 2}, revision, {"friction": "N"}))
    if function_id:
        with pytest.raises(PrepError):
            provider.submit(SetProperties(target, {"friction": 0}, revision))
    assert session.card_text(target.object_id) == before and session.describe()["revision"] == revision
