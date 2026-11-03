"""Verified recipe-generated quad4/hex8 candidates using the existing neutral DTO.

This is a distinct source kind. It does not admit these families from arbitrary
CAD or standalone MSH, invent a CAD identity, or bypass final source validation.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import UUID, uuid4, uuid5

from ..cae_core.errors import PrepError
from .mesh_candidates import (AssetDigest, CellInventory, MeshGroup, MeshPart,
    NativeMesh, _cells, _nodes, _sha)
from .structured_geometry import (SIDES_H, SIDES_Q, EDGES_H, validate_recipe,
                                  validate_structured_mesh, MAX_RECIPE_BYTES)


@dataclass(frozen=True)
class StructuredQuality:
    kind: str
    minimum_scaled_jacobian: float
    minimum_signed_jacobian: float
    maximum_edge_aspect_ratio: float
    measure: float
    expected_measure: float
    details_json: str
    passed: bool = True
    problem_ids: tuple = ()
    unsupported_ids: tuple = ()

    def minimum(self, kind):
        return self.minimum_scaled_jacobian if kind == self.kind else None


@dataclass(frozen=True)
class StructuredMeshCandidate:
    mesh_uuid: str
    recipe_json: str
    length_unit: str
    dimension: int
    nodes: tuple
    cells: tuple
    parts: tuple
    groups: tuple
    inventory: tuple
    assets: tuple
    quality: StructuredQuality
    backend_version: str
    geometry_resource_uuid: None = None

    @property
    def manifest_path(self):
        return next(asset.path for asset in self.assets if asset.kind == 'metadata')

    def to_native_mesh(self, *, length_unit=None):
        if length_unit is not None and length_unit != self.length_unit:
            raise PrepError('unit_mismatch', 'A recipe length unit cannot be changed by relabeling.')
        if not self.quality.passed:
            raise PrepError('mesh_quality', 'The structured mesh failed admission.')
        physical = tuple(cell for cell in self.cells if cell.dimension == self.dimension)
        used = {identifier for cell in physical for identifier in cell.node_ids}
        return NativeMesh(self.nodes, physical, self.parts, self.length_unit, None,
            self.mesh_uuid, self.dimension, self.inventory, len(self.cells) - len(physical),
            tuple(node.id for node in self.nodes if node.id not in used), self.assets,
            'structured_recipe', self.groups)


def _loads_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Repeated JSON field: ' + key)
            result[key] = value
        return result
    def finite(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    return json.loads(text, object_pairs_hook=unique, parse_constant=finite)


def _json(path):
    return _loads_json(Path(path).read_text(encoding='utf-8'))


def read_recipe_input(path):
    """Bind the reviewed JSON and digest to the same bounded byte read."""
    path = Path(path).expanduser().resolve()
    with path.open('rb') as stream:
        raw = stream.read(MAX_RECIPE_BYTES + 1)
    if len(raw) > MAX_RECIPE_BYTES:
        raise PrepError('invalid_recipe', 'Recipe JSON exceeds the 1 MiB input limit.')
    return (_loads_json(raw.decode('utf-8')),
            AssetDigest('source_recipe', str(path), hashlib.sha256(raw).hexdigest()))


def _validate_source_recipe(spec, asset):
    if not isinstance(asset, AssetDigest) or asset.kind != 'source_recipe':
        raise PrepError('invalid_recipe', 'Expected the original structured recipe identity.')
    original, current = read_recipe_input(asset.path)
    if current != asset:
        raise PrepError('candidate_changed', 'The original recipe changed after review.')
    validate_recipe_edit(original, spec)


def validate_recipe_edit(original, spec):
    """The same bounded edit contract for live and archived recipe bytes."""
    validate_recipe(original)
    if original.get('mode') != spec.get('mode') or original.get('mode') not in ('quad', 'hex'):
        raise PrepError('invalid_recipe', 'Keep the original quad or hex recipe mode.')
    expected = deepcopy(original)
    if 'patches' in original and 'patches' in spec and len(original['patches']) == len(spec['patches']):
        for old, edited in zip(expected['patches'], spec['patches']):
            old['divisions'] = edited['divisions']
    elif 'patches' not in original and 'patches' not in spec:
        expected['divisions'] = spec['divisions']
    if original['mode'] == 'hex':
        expected['layers'] = spec['layers']
    if expected != spec:
        raise PrepError('invalid_recipe', 'Only divisions and hex layers can differ from an original recipe.')


def _write_json(path, value):
    # A captured recipe is immutable; writing into an existing asset is an error.
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def _child(module, arguments, *, cancel_event=None, timeout=30):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PrepError('invalid_request', 'A positive finite worker timeout is required.')
    if cancel_event is not None and cancel_event.is_set():
        raise PrepError('cancelled', 'Structured mesh work was cancelled.')
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [str(Path(__file__).resolve().parents[2]), env.get('PYTHONPATH')]))
    process = subprocess.Popen([sys.executable, '-m', module, *map(str, arguments)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env)
    started = time.monotonic()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise PrepError('cancelled', 'Structured mesh work was cancelled.', {'pid': process.pid})
            if time.monotonic() - started >= timeout:
                raise PrepError('recipe_timeout', 'Structured mesh work exceeded its time limit.', {'pid': process.pid})
            try:
                stdout, stderr = process.communicate(timeout=.05)
                break
            except subprocess.TimeoutExpired:
                continue
        try:
            response = json.loads(stdout)
        except (ValueError, TypeError):
            raise PrepError('recipe_worker', 'The structured worker returned an invalid response.',
                            {'stderr': stderr[-2000:]}) from None
        if process.returncode or not response.get('ok'):
            raise PrepError('recipe_worker', str(response.get('error', 'Structured worker failed.')),
                            {'exit_code': process.returncode, 'stderr': stderr[-2000:]})
        if cancel_event is not None and cancel_event.is_set():
            raise PrepError('cancelled', 'Structured mesh work was cancelled.', {'pid': process.pid})
        return response
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=3)


def generate_structured_mesh(spec, output_dir, *, recipe_path=None, source_recipe=None, cancel_event=None, timeout=30):
    """Generate from explicit values; retain a supplied original file as an asset."""
    validate_recipe(spec)
    if source_recipe is not None:
        if recipe_path is not None:
            raise PrepError('invalid_recipe', 'Use a snapshot for an edited structured recipe.')
        _validate_source_recipe(spec, source_recipe)
    if not str(output_dir).strip():
        raise PrepError('invalid_request', 'Choose an asset directory.')
    if cancel_event is not None and cancel_event.is_set():
        raise PrepError('cancelled', 'Structured mesh work was cancelled.')
    recipe = None if recipe_path is None else Path(recipe_path).expanduser().resolve()
    recipe_hash = None
    if recipe is not None:
        if recipe.stat().st_size > MAX_RECIPE_BYTES:
            raise PrepError('invalid_recipe', 'Recipe JSON exceeds the 1 MiB input limit.')
        recipe_hash = _sha(recipe)
        if _json(recipe) != spec or _sha(recipe) != recipe_hash:
            raise PrepError('candidate_changed', 'The original recipe differs from the reviewed input.')
    identifier = str(uuid4())
    folder = Path(output_dir).expanduser().resolve() / ('structured-' + identifier)
    folder.mkdir(parents=True, exist_ok=False)
    if recipe is None:
        recipe = folder / 'recipe.json'
        _write_json(recipe, spec)
        recipe_hash = _sha(recipe)
    _child('caelab_prep.application.structured_mesh_worker', [recipe, folder],
           cancel_event=cancel_event, timeout=timeout)
    if _sha(recipe) != recipe_hash:
        raise PrepError('candidate_changed', 'The original recipe changed during generation.')
    if source_recipe is not None:
        _validate_source_recipe(spec, source_recipe)
    sources = {kind: {'path': str(path), 'sha256': _sha(path)} for kind, path in
               [('recipe', recipe), ('msh', folder / 'mesh.msh'), ('sdk', folder / 'sdk.json')]}
    if source_recipe is not None:
        sources['source_recipe'] = {'path': source_recipe.path, 'sha256': source_recipe.sha256}
    metadata = folder / 'metadata.json'
    _write_json(metadata, {'schema': 'caelab.structured-recipe', 'version': 1,
                          'mesh_uuid': identifier, 'assets': sources})
    return read_structured_mesh_candidate(metadata, cancel_event=cancel_event,
                                         inspection_timeout=timeout)


def read_structured_mesh_candidate(metadata, *, cancel_event=None, inspection_timeout=30):
    """Reopen actual source assets; inspect all MSH cells in the official SDK."""
    try:
        metadata = Path(metadata).expanduser().resolve()
        metadata_hash = _sha(metadata)
        manifest = _json(metadata)
        if (manifest['schema'] != 'caelab.structured-recipe' or type(manifest['version']) is not int
                or manifest['version'] != 1 or set(manifest['assets']) not in
                ({'recipe', 'msh', 'sdk'}, {'recipe', 'msh', 'sdk', 'source_recipe'})):
            raise ValueError('Unsupported structured manifest schema.')
        namespace = UUID(manifest['mesh_uuid'])
        assets = [AssetDigest('metadata', str(metadata), metadata_hash)]
        for kind in ('recipe', 'msh', 'sdk', *(('source_recipe',) if 'source_recipe' in manifest['assets'] else ())):
            record = manifest['assets'][kind]
            path = str(Path(record['path']).expanduser().resolve())
            if _sha(path) != record['sha256']:
                raise PrepError('candidate_changed', 'A structured candidate asset changed.', {'asset': kind})
            assets.append(AssetDigest(kind, path, record['sha256']))
        paths = {asset.kind: asset.path for asset in assets}
        recipe = _json(paths['recipe'])
        admission = validate_recipe(recipe)
        if 'source_recipe' in paths:
            _validate_source_recipe(recipe, next(asset for asset in assets if asset.kind == 'source_recipe'))
        sdk = _json(paths['sdk'])
        if (type(sdk['schema_version']) is not int or sdk['schema_version'] != 1
                or sdk['status'] != 'completed'
                or sdk['backend'] != {'name': 'gmsh', 'version': '4.15.2'} or sdk['errors'] or sdk['warnings']
                or sdk['source_sha256'] != manifest['assets']['recipe']['sha256']
                or sdk['mesh_sha256'] != manifest['assets']['msh']['sha256'] or not sdk['reopened']):
            raise PrepError('candidate_mismatch', 'The SDK report does not match the supported recipe assets.')
        independent = _child('caelab_prep.application.mesh_candidates', [paths['msh']],
                             cancel_event=cancel_event, timeout=inspection_timeout)['mesh']
        nodes = _nodes(independent['nodes'])
        dimension = admission['dimension']
        expected_names = ([patch['id'] for patch in recipe['patches']] if 'patches' in recipe
                          else [recipe.get('name') or 'explicit_source_1'])
        groups = independent['physical_groups']
        if (len(groups) != len(expected_names) or
                {(group['dimension'], group['tag'], group['name']) for group in groups}
                != {(dimension, 110 + i, name) for i, name in enumerate(expected_names)}):
            raise PrepError('candidate_mismatch', 'MSH physical sources differ from the recipe patch identities.')
        owner_by_entity, ids_by_owner = {}, {}
        for i, name in enumerate(expected_names):
            group = next(group for group in groups if group['tag'] == 110 + i)
            if len(group['entities']) != 1:
                raise PrepError('candidate_mismatch', 'Each recipe patch must own one physical entity.')
            tag = group['entities'][0]
            if tag in owner_by_entity:
                raise PrepError('candidate_mismatch', 'Recipe patch entities overlap.')
            owner_by_entity[tag] = i
            ids_by_owner[i] = []
        node_ids = {node.id for node in nodes}
        cells, seen, tuples = [], set(), []
        allowed = {0: (15, 1), 1: (1, 2), 2: (3, 4), 3: (5, 8)}
        for block in independent['element_blocks']:
            dim = block['dimension']
            if dim > dimension or (block['element_type'], block['nodes_per_element']) != allowed[dim] or block['order'] != (0 if dim == 0 else 1):
                raise PrepError('unsupported_mesh', 'The complete recipe inventory contains an unsupported family/order.')
            patch = owner_by_entity.get(block['backend_tag']) if dim == dimension else None
            if dim == dimension and patch is None:
                raise PrepError('candidate_mismatch', 'A physical element has no source patch.')
            owner = str(uuid5(namespace, f'patch:{patch}')) if patch is not None else None
            for cell in _cells(block, owner, node_ids):
                if cell.id in seen:
                    raise PrepError('candidate_mismatch', 'Duplicate source element ID.')
                seen.add(cell.id); cells.append(cell)
                if patch is not None:
                    ids_by_owner[patch].append(cell.id)
                    tuples.append((cell.id, patch, cell.node_ids))
        physical = [cell for cell in cells if cell.dimension == dimension]
        used = {n for cell in physical for n in cell.node_ids}
        if used != node_ids:
            raise PrepError('candidate_mismatch', 'Recipe mesh includes unused nodes outside its physical cells.')
        coordinates = {node.id: node.xyz for node in nodes}
        metrics = validate_structured_mesh(recipe, coordinates, tuples)
        faces = {tuple(sorted(cell.node_ids[i] for i in face)) for cell in physical
                 for face in (SIDES_H if dimension == 3 else SIDES_Q)}
        edges = {tuple(sorted((cell.node_ids[a], cell.node_ids[b]))) for cell in physical
                 for a, b in (EDGES_H if dimension == 3 else SIDES_Q)}
        for cell in cells:
            if cell.dimension >= dimension:
                continue
            valid = (set(cell.node_ids) <= used if cell.dimension == 0 else
                     tuple(sorted(cell.node_ids)) in edges if cell.dimension == 1 else
                     tuple(sorted(cell.node_ids)) in faces)
            if not valid:
                raise PrepError('candidate_mismatch', 'A lower-dimensional cell is outside the actual physical topology.')
        counts = sdk['counts']
        if any(counts[key] != value for key, value in {'nodes': len(nodes), 'elements': len(physical),
                 'top_elements': len(physical), 'all_elements': len(cells), 'active_nodes': len(used)}.items()):
            raise PrepError('candidate_mismatch', 'SDK inventory counts do not match the complete MSH.')
        counter = Counter((c.dimension, c.element_type, c.element_name, c.order,
                           'physical' if c.dimension == dimension else 'boundary_annotation') for c in cells)
        inventory = tuple(CellInventory(dim, typ, name, order, count, role, True)
                          for (dim, typ, name, order, role), count in sorted(counter.items()))
        parts = tuple(MeshPart(str(uuid5(namespace, f'patch:{i}')), dimension,
                              next(tag for tag, index in owner_by_entity.items() if index == i),
                              name, tuple(ids_by_owner[i])) for i, name in enumerate(expected_names))
        sets = tuple(MeshGroup(f'patch:{i}', name, 'element', tuple(ids_by_owner[i]))
                     for i, name in enumerate(expected_names))
        if any(_sha(asset.path) != asset.sha256 for asset in assets):
            raise PrepError('candidate_changed', 'Structured candidate assets changed during inspection.')
        quality = StructuredQuality(admission['kind'], metrics['min_independent_scaled_jacobian'],
            metrics['min_signed_jacobian'], metrics['max_edge_aspect_ratio'], metrics['measure'],
            admission['expected_measure'], json.dumps(metrics, sort_keys=True, allow_nan=False))
        return StructuredMeshCandidate(str(namespace), json.dumps(recipe, sort_keys=True, allow_nan=False),
            admission['unit'], dimension, nodes, tuple(cells), parts, sets, inventory, tuple(assets), quality, '4.15.2')
    except PrepError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
        raise PrepError('invalid_candidate', f'Invalid structured recipe candidate: {exc}') from exc


def validate_structured_native_mesh(native):
    """Canonical full-value comparison immediately before atomic adoption."""
    if (not isinstance(native, NativeMesh) or native.source_kind != 'structured_recipe'
            or native.geometry_resource_uuid is not None or not isinstance(native.assets, tuple)
            or any(not isinstance(a, AssetDigest) for a in native.assets)
            or len(native.assets) not in (4, 5) or len({a.kind for a in native.assets}) != len(native.assets)
            or {a.kind for a in native.assets} not in
            ({'recipe', 'metadata', 'msh', 'sdk'}, {'recipe', 'metadata', 'msh', 'sdk', 'source_recipe'})):
        raise PrepError('invalid_native_mesh', 'Structured adoption requires its exact recipe, MSH, report and manifest; no CAD identity.')
    for asset in native.assets:
        if (not isinstance(asset.path, str) or not isinstance(asset.sha256, str)
                or len(asset.sha256) != 64):
            raise PrepError('invalid_native_mesh', 'Malformed structured source asset identity.')
        if _sha(asset.path) != asset.sha256:
            raise PrepError('candidate_changed', 'A structured source asset changed after review.', {'asset': asset.kind})
    canonical = read_structured_mesh_candidate(next(a.path for a in native.assets if a.kind == 'metadata')).to_native_mesh()
    if canonical != native:
        raise PrepError('invalid_native_mesh', 'Structured mesh values differ from the verified source assets.')
    return canonical


def validate_structured_native_coordinates(native, coordinates):
    """Repeat source/quality gates on the native writer's actual encoded values.

    Called after validate_structured_native_mesh; this does not replace its
    asset check or authorize an unverified public NativeMesh by itself.
    """
    if native.source_kind != 'structured_recipe':
        raise PrepError('invalid_native_mesh', 'Expected a structured recipe candidate.')
    recipe_asset = next((a for a in native.assets if a.kind == 'recipe'), None)
    if recipe_asset is None or _sha(recipe_asset.path) != recipe_asset.sha256:
        raise PrepError('candidate_changed', 'The source recipe changed before native serialization.')
    recipe = _json(recipe_asset.path)
    patches = {part.uuid: i for i, part in enumerate(native.parts)}
    return validate_structured_mesh(recipe, coordinates,
        [(cell.id, patches[cell.part_uuid], cell.node_ids) for cell in native.elements])
