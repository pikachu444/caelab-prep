"""Two real SDK candidates plus immutable-source/DTO rejection checks.

These tests do not claim native adoption, solver execution, GUI or Windows
completion. The common session dispatch is intentionally outside this module.
"""
from dataclasses import replace
import importlib.util
from pathlib import Path

import pytest

from caelab_prep.application.structured_mesh import (generate_structured_mesh,
    read_structured_mesh_candidate, validate_structured_native_mesh,
    validate_structured_native_coordinates)
from caelab_prep.cae_core.errors import PrepError
from caelab_prep.radioss.modeling import real


@pytest.fixture(scope='module', params=['quad', 'hex'])
def generated(request, tmp_path_factory):
    if importlib.util.find_spec('gmsh') is None:
        pytest.skip('Real Gmsh SDK is unavailable; no generation claim.')
    if request.param == 'quad':
        spec = dict(mode='quad', unit='mm', vertices=dict(a=[0,0,0],b=[4,0,0],c=[3,2,0],
            d=[.5,2,0],e=[7,0,0],f=[6.5,2,0]), patches=[
            dict(id='left',corners=['a','b','c','d'],divisions=[4,2]),
            dict(id='right',corners=['b','e','f','c'],divisions=[3,2])])
    else:
        spec = dict(mode='hex', unit='cm', corners=[[0,0,0],[4,0,0],[3,2,0],[.5,2,0]],
                    divisions=[4,2], vector=[.5,.2,2], layers=2, name='User sweep')
    folder = tmp_path_factory.mktemp('structured-' + request.param)
    candidate = generate_structured_mesh(spec, folder)
    return candidate, spec


def test_real_recipe_generation_complete_inventory_reopen_and_canonical_gate(generated):
    candidate, spec = generated
    native = candidate.to_native_mesh()
    assert native.source_kind == 'structured_recipe' and native.geometry_resource_uuid is None
    assert native.length_unit == spec['unit']
    assert candidate.quality.passed
    assert len(native.elements) == (14 if spec['mode'] == 'quad' else 16)
    assert all(cell.element_type == (3 if spec['mode'] == 'quad' else 5) for cell in native.elements)
    assert native.omitted_boundary_cells > 0
    assert sum(row.count for row in native.inventory) == len(candidate.cells)
    assert native.groups and all(group.member_ids for group in native.groups)
    assert read_structured_mesh_candidate(candidate.manifest_path) == candidate
    assert validate_structured_native_mesh(native) == native
    encoded = {node.id: tuple(float(real(x)) for x in node.xyz) for node in native.nodes}
    assert validate_structured_native_coordinates(native, encoded)['kind'] == ('quad4' if spec['mode']=='quad' else 'hex8')


def test_forged_coordinate_connectivity_groups_and_cad_identity_rejected(generated):
    native = generated[0].to_native_mesh()
    first = native.nodes[0]
    moved = replace(first, xyz=(first.xyz[0] + .01, *first.xyz[1:]))
    cell = native.elements[0]
    altered = replace(cell, node_ids=tuple(reversed(cell.node_ids)))
    values = [replace(native, nodes=(moved, *native.nodes[1:])),
              replace(native, elements=(altered, *native.elements[1:])),
              replace(native, groups=()), replace(native, geometry_resource_uuid='invented-cad')]
    for forged in values:
        with pytest.raises(PrepError):
            validate_structured_native_mesh(forged)


def test_changed_asset_and_native_rounding_damage_rejected(generated, tmp_path):
    native = generated[0].to_native_mesh()
    source = next(a for a in native.assets if a.kind == 'msh')
    altered = tmp_path / 'altered.msh'
    altered.write_bytes(Path(source.path).read_bytes() + b'\n# changed after review\n')
    forged = replace(native, assets=tuple(replace(a, path=str(altered)) if a.kind == 'msh' else a for a in native.assets))
    with pytest.raises(PrepError) as error:
        validate_structured_native_mesh(forged)
    assert error.value.code == 'candidate_changed'
    coordinates = {node.id: node.xyz for node in native.nodes}
    first = native.nodes[0]
    coordinates[first.id] = (first.xyz[0] + .01, *first.xyz[1:])
    with pytest.raises(PrepError):
        validate_structured_native_coordinates(native, coordinates)
    with pytest.raises(PrepError) as error:
        generated[0].to_native_mesh(length_unit='m')
    assert error.value.code == 'unit_mismatch'
