"""Source-lattice and element quality gates, independent of Gmsh/Qt."""
from copy import deepcopy
import subprocess
import sys

import pytest

from caelab_prep.application.structured_geometry import validate_recipe, validate_structured_mesh
from caelab_prep.cae_core.errors import PrepError

QUAD = dict(mode='quad', unit='mm', corners=[[0, 0, 0], [2, 0, 0], [2, 3, 0], [0, 3, 0]], divisions=[1, 1])
NODES = {1: (0, 0, 0), 2: (2, 0, 0), 3: (2, 3, 0), 4: (0, 3, 0)}


def test_quad_and_oblique_hex_exact_geometry_and_signed_quality():
    q = validate_structured_mesh(QUAD, NODES, [(91, 0, (1, 2, 3, 4))])
    assert q['measure'] == pytest.approx(6)
    assert q['min_independent_scaled_jacobian'] == pytest.approx(1)
    spec = dict(QUAD, mode='hex', vector=[1, .2, 4], layers=1)
    xyz = dict(NODES, **{})
    xyz.update({n + 4: tuple(p[i] + spec['vector'][i] for i in range(3)) for n, p in NODES.items()})
    h = validate_structured_mesh(spec, xyz, [(92, 0, tuple(range(1, 9)))])
    assert h['measure'] == pytest.approx(24)
    assert h['min_signed_jacobian'] > 0
    assert h['min_independent_scaled_jacobian'] > .9


@pytest.mark.parametrize('change', [dict(twist_degrees=10), dict(divisions=[True, 1]),
    dict(divisions=[10000, 10000]), dict(unit='unknown'), dict(mode='arc'),
    dict(corners=[[0, 0, 0], [2, 0, 0], [2, 3, .1], [0, 3, 0]])])
def test_unsupported_semantics_units_counts_and_source_shape_rejected(change):
    with pytest.raises(PrepError):
        validate_recipe(dict(QUAD, **change))


@pytest.mark.parametrize('conn', [(1, 4, 3, 2), (1, 3, 2, 4), (1, 2, 3, 3)])
def test_inversion_crossing_and_repeated_nodes_are_not_repaired(conn):
    with pytest.raises(PrepError):
        validate_structured_mesh(QUAD, NODES, [(91, 0, conn)])


def test_unexpected_coordinates_and_physical_owner_rejected():
    moved = dict(NODES); moved[3] = (1.99, 3, 0)
    for nodes, patch in [(moved, 0), (NODES, 1)]:
        with pytest.raises(PrepError):
            validate_structured_mesh(QUAD, nodes, [(91, patch, (1, 2, 3, 4))])


def test_explicit_adjacent_patches_require_same_seed_count_and_shared_ids():
    spec = dict(mode='quad', unit='mm', vertices=dict(a=[0, 0, 0], b=[2, 0, 0],
        c=[2, 3, 0], d=[0, 3, 0], e=[4, 0, 0], f=[4, 3, 0]), patches=[
        dict(id='left', corners=['a', 'b', 'c', 'd'], divisions=[1, 1]),
        dict(id='right', corners=['b', 'e', 'f', 'c'], divisions=[1, 1])])
    nodes = dict(NODES); nodes.update({5: (4, 0, 0), 6: (4, 3, 0)})
    r = validate_structured_mesh(spec, nodes, [(1, 0, (1, 2, 3, 4)), (2, 1, (2, 5, 6, 3))])
    assert r['shared_boundary_cells'] == 1 and r['shared_nodes'] == 2
    bad = deepcopy(spec); bad['patches'][1]['divisions'][1] = 2
    with pytest.raises(PrepError): validate_recipe(bad)
    split = dict(nodes); split.update({7: nodes[2], 8: nodes[3]})
    with pytest.raises(PrepError):
        validate_structured_mesh(spec, split, [(1, 0, (1, 2, 3, 4)), (2, 1, (7, 5, 6, 8))])


def test_admission_stays_enabled_under_python_optimization():
    script = f'''from caelab_prep.application.structured_geometry import validate_structured_mesh
from caelab_prep.cae_core.errors import PrepError
try: validate_structured_mesh({QUAD!r}, {NODES!r}, [(91,0,(1,4,3,2))])
except PrepError: pass
else: raise RuntimeError('validation disabled')
'''
    r = subprocess.run([sys.executable, '-O', '-c', script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize('text, reason', [('{"schema":1,"schema":2}', 'Repeated JSON field'),
                                         ('{"value":NaN}', 'Nonfinite JSON number')])
def test_candidate_json_rejects_duplicate_fields_and_nonfinite_values(tmp_path, text, reason):
    from caelab_prep.application.structured_mesh import read_structured_mesh_candidate
    path = tmp_path / 'metadata.json'
    path.write_text(text)
    with pytest.raises(PrepError, match=reason):
        read_structured_mesh_candidate(path)
