"""Prepared straight Tet10 uses the existing standalone/Undo/project/native path."""
from pathlib import Path
from importlib.util import find_spec

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.application.external_mesh import import_standalone_mesh
from caelab_prep.application.tet10_geometry import GMSH_EDGES, native_tet10_nodes, certify_straight_tet10
from caelab_prep.cae_core.errors import PrepError
from caelab_prep.radioss.deck import DeckResource
from caelab_prep.radioss.tetra10 import records


@pytest.fixture
def sdk():
    if find_spec('gmsh') is None:
        pytest.skip('Actual standalone MSH inspection requires the optional Gmsh SDK')


def fixture(path, *, curved=False, bad_boundary=False):
    corners = ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.))
    points = list(corners) + [tuple((a+b)/2 for a, b in zip(corners[i], corners[j])) for i, j in GMSH_EDGES]
    if curved:
        points[4] = (.5, .01, 0.)
    ids = tuple(101+31*i for i in range(10))
    mids = {frozenset((i, j)): ids[k+4] for k, (i, j) in enumerate(GMSH_EDGES)}
    triangles = []
    for face in ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)):
        a, b, c = face
        triangles.append(tuple(ids[i] for i in face) + tuple(mids[frozenset(edge)] for edge in ((a,b), (b,c), (c,a))))
    if bad_boundary:
        triangles[0] = (*triangles[0][:-1], ids[7])
    rows = ['711 11 2 7 1 ' + ' '.join(map(str, ids))]
    rows += [f'{801+i} 9 2 8 2 ' + ' '.join(map(str, conn)) for i, conn in enumerate(triangles)]
    text = '\n'.join(['$MeshFormat', '2.2 0 8', '$EndMeshFormat', '$PhysicalNames', '2',
        '3 7 "Solid"', '2 8 "All boundary nodes"', '$EndPhysicalNames', '$Nodes', '10',
        *(f'{node} ' + ' '.join(map(repr, xyz)) for node, xyz in zip(ids, points)), '$EndNodes',
        '$Elements', str(len(rows)), *rows, '$EndElements', ''])
    path.write_text(text, encoding='ascii')
    return ids


def candidate(tmp_path, **kwargs):
    path = tmp_path / 'prepared.msh'
    ids = fixture(path, **kwargs)
    return import_standalone_mesh(path, tmp_path/'imports', length_unit='mm', element_profile='straight_tet10'), ids


def model():
    session = PrepSession()
    session.new_document('Prepared Tet10', {'mass': 'Mg', 'length': 'mm', 'time': 's'})
    material = session.create_material('Steel', 7.8e-9, 210000, .3)['card_id']
    section = session.create_solid_property('Straight Tet10', element_family='tetra10')['card_id']
    return session, material, section


def test_opt_in_and_complete_quadratic_boundary_inventory(tmp_path, sdk):
    path = tmp_path/'prepared.msh'; fixture(path)
    legacy = import_standalone_mesh(path, tmp_path/'old', length_unit='mm')
    assert not legacy.quality.passed and legacy.quality.unsupported_ids
    imported, _ = candidate(tmp_path)
    assert imported.quality.passed
    mesh = imported.to_native_mesh()
    assert len(mesh.elements) == 1 and mesh.elements[0].kind == 'tetra10'
    assert mesh.omitted_boundary_cells == 4 and len(mesh.nodes) == 10
    assert all(item.supported for item in mesh.inventory)
    assert len(next(group for group in mesh.groups if group.kind == 'node').member_ids) == 10


def test_curved_midpoint_blocks_whole_import(tmp_path, sdk):
    imported, _ = candidate(tmp_path, curved=True)
    assert not imported.quality.passed
    with pytest.raises(PrepError, match='whole import'):
        imported.to_native_mesh()


def test_wrong_quadratic_boundary_is_not_discarded(tmp_path, sdk):
    with pytest.raises(PrepError) as exc:
        candidate(tmp_path, bad_boundary=True)
    assert exc.value.code == 'mixed_dimension_mesh'


def test_native_two_rows_one_undo_reopen_and_export(tmp_path, sdk):
    imported, ids = candidate(tmp_path)
    mesh = imported.to_native_mesh()
    session, material, section = model()
    before = session.describe()['revision']
    result = session.adopt_mesh_candidate(mesh, material_id=material, property_id=section)
    assert session.describe()['revision'] == before+1
    projection = session.mesh_view()
    cell = projection['cells'][0]
    expected = tuple(result['node_id_map'][node] for node in native_tet10_nodes(ids))
    assert cell['formulation'] == 'TETRA10' and cell['nodes'] == expected
    session.undo(); assert not session.mesh_view()['cells']
    session.redo(); assert session.mesh_view()['cells'][0]['nodes'] == expected
    project = tmp_path/'mesh.caeprep'; session.save_project(project)
    reopened = PrepSession(); reopened.open_project(project)
    output = tmp_path/'export'/'solid_0000.rad'; reopened.export_rad(output)
    deck = DeckResource(output.read_bytes())
    card = next(card for card in deck.cards if card.keyword.startswith('/TETRA10/'))
    parsed = records(deck.lines, card.data)
    assert len(parsed) == 1 and parsed[0][1] == tuple(expected) and len(card.data) == 2
    view = deck.mesh_projection()
    xyz = dict(zip(view['node_ids'], view['points']))
    proof = certify_straight_tet10([xyz[node] for node in expected], ordering='radioss')
    assert proof['certified_positive'] and proof['midpoint_within_ulp_budget']
    native = PrepSession(); native.open_rad(output)
    assert native.describe()['element_count'] == 1
    assert native.mesh_view()['cells'][0]['nodes'] == expected


def test_old_property_is_not_silently_changed(tmp_path, sdk):
    imported, _ = candidate(tmp_path)
    session, material, _ = model()
    old = session.create_solid_property('Old Tet4')['card_id']
    before = (session.describe()['revision'], session.card_text(old))
    with pytest.raises(PrepError) as exc:
        session.adopt_mesh_candidate(imported.to_native_mesh(), material_id=material, property_id=old)
    assert exc.value.code == 'incompatible_property'
    assert (session.describe()['revision'], session.card_text(old)) == before


def test_part_reassignment_keeps_explicit_tetra10_profile(tmp_path, sdk):
    imported, _ = candidate(tmp_path)
    session, material, section = model()
    result = session.adopt_mesh_candidate(imported.to_native_mesh(), material_id=material, property_id=section)
    part = result['part_ids'][0]
    old = session.create_solid_property('Tet4')['card_id']
    before = (session.describe()['revision'], session.card_text(part))
    with pytest.raises(PrepError) as exc:
        session.assign_part(part, property_id=old)
    assert exc.value.code == 'incompatible_property'
    assert (session.describe()['revision'], session.card_text(part)) == before
    other = session.create_solid_property('Other Tet10', element_family='tetra10')['card_id']
    session.assign_part(part, property_id=other)
    assert session.part_assignment(part)['property_id'] == other


def test_second_adoption_reserves_two_row_element_ids(tmp_path, sdk):
    imported, _ = candidate(tmp_path)
    mesh = imported.to_native_mesh()
    session, material, section = model()
    first = session.adopt_mesh_candidate(mesh, material_id=material, property_id=section)
    second = session.adopt_mesh_candidate(mesh, material_id=material, property_id=section)
    assert set(first['element_id_map'].values()).isdisjoint(second['element_id_map'].values())
    assert set(first['node_id_map'].values()).isdisjoint(second['node_id_map'].values())
    assert len(session.mesh_view()['cells']) == 2


@pytest.mark.parametrize('method', ['save_project', 'export_rad'])
def test_original_msh_is_protected_after_adoption_and_project_reopen(tmp_path, sdk, method):
    imported, _ = candidate(tmp_path)
    original = tmp_path/'prepared.msh'
    before = original.read_bytes()
    session, material, section = model()
    session.adopt_mesh_candidate(imported.to_native_mesh(), material_id=material, property_id=section)
    project = tmp_path/'protected.caeprep'; session.save_project(project)
    reopened = PrepSession(); reopened.open_project(project)
    for host in (session, reopened):
        with pytest.raises(PrepError) as exc:
            getattr(host, method)(original)
        assert exc.value.code == 'source_overwrite'
        assert original.read_bytes() == before


@pytest.mark.parametrize('order,accepted', [((0,1,4), True), ((1,0,4), True), ((4,0,1), False)])
def test_line3_annotation_preserves_endpoint_and_midpoint_roles(tmp_path, sdk, order, accepted):
    path = tmp_path/'line.msh'; ids = fixture(path)
    text = path.read_text(encoding='ascii').replace('$Elements\n5\n', '$Elements\n6\n')
    text = text.replace('$EndElements', '901 8 2 0 3 '+' '.join(str(ids[i]) for i in order)+'\n$EndElements')
    path.write_text(text, encoding='ascii')
    if accepted:
        imported = import_standalone_mesh(path, tmp_path/'imports', length_unit='mm', element_profile='straight_tet10')
        assert imported.quality.passed and imported.to_native_mesh().omitted_boundary_cells == 5
    else:
        with pytest.raises(PrepError) as exc:
            import_standalone_mesh(path, tmp_path/'imports', length_unit='mm', element_profile='straight_tet10')
        assert exc.value.code == 'mixed_dimension_mesh'


@pytest.mark.parametrize('text', ['         1\n', '         1         2\n' + ''.join(f'{i:10}' for i in range(1,11))+'\n',
                                  '         1\n' + ''.join(f'{1:10}' for _ in range(10))+'\n'])
def test_malformed_native_tetra10_keeps_raw_and_reports_projection_error(text):
    raw = ('/TETRA10/1\n'+text).encode('ascii')
    deck = DeckResource(raw)
    assert deck.render() == raw
    assert not deck.mesh_projection()['cells']
    assert deck.mesh_projection()['diagnostics'][0]['code'] == 'element_display_parse'
