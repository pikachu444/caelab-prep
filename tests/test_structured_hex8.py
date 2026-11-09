"""User-created Hex8 sections support the existing structured sweep workflow."""
from caelab_prep.application import PrepSession
from test_structured_hex_adoption import sweep
from test_structured_adoption import _native


def test_create_hex8_section_adopt_sweep_and_export(sweep, tmp_path):
    case, native = sweep
    assert native.source_kind == "structured_recipe" and native.dimension == 3
    assert all(cell.element_type == 5 and len(cell.node_ids) == 8 for cell in native.elements)
    session = PrepSession()
    session.new_document("Hex8 model", {"mass": "Mg", "length": native.length_unit, "time": "s"})
    material = session.create_material("Steel", 7.8e-9, 210000, .3)["card_id"]
    section = session.create_solid_section("Hex8 Section", element_family="hexa8")["card_id"]
    row = session.card_text(section).splitlines()[2]
    assert tuple(int(row[i:i + 10]) for i in range(0, 80, 10)) == (1, 4, 0, 0, 0, 0, 1000, 1)
    adopted = session.adopt_mesh_candidate(native, material_id=material, property_id=section)
    output = tmp_path / "hex8_0000.rad"
    session.export_rad(output)
    nodes, elements, parts, _ = _native(output.read_bytes())
    assert len(elements) == case["expectation"]["elements"]
    assert len(nodes) == case["expectation"]["active_nodes"]
    for cell in native.elements:
        _, connectivity = elements[adopted["element_id_map"][cell.id]]
        assert connectivity == tuple(adopted["node_id_map"][node] for node in cell.node_ids)
    reopened = PrepSession()
    reopened.open_rad(output)
    assert any(card["keyword"].startswith("/BRICK/") for card in reopened.list_cards())
    assert len(parts) == len(native.parts)
