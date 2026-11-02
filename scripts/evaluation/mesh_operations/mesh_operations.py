"""Pure N18 sparse mesh edit candidates; no Qt, session, file or solver writes.

Ref matches public SelectionRef fields. An adapter must supply the complete
reference closure and CAS the original stamp/digest before any atomic commit.
Hex mathematics is adapted from the internally authored independent F2 oracle;
27 Jacobian samples are a bounded check, not a global warped-map proof.
"""
from __future__ import annotations
from dataclasses import dataclass, field, fields, replace
from collections.abc import Mapping
from hashlib import sha256
from itertools import product
import json
import math
from types import MappingProxyType
from uuid import UUID


class MeshEditError(ValueError):
    def __init__(self, code, message, details=()):
        super().__init__(message); self.code=code; self.details=details


def fail(code, message, details=()): raise MeshEditError(code,message,details)
def uid(value):
    try: UUID(value)
    except (ValueError,TypeError,AttributeError): fail('invalid_identity','UUID source identity required.')
def finite(value): return type(value) in (int,float) and math.isfinite(value)
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a): return math.hypot(*a)
def scale(a,k): return tuple(x*k for x in a)
def point(value):
    if not isinstance(value,tuple) or len(value)!=3 or not all(finite(x) for x in value):
        fail('invalid_coordinate','Three finite immutable coordinates required.')
    return value

def encoded(value):
    if hasattr(value,'__dataclass_fields__'):
        return {f.name:encoded(getattr(value,f.name)) for f in fields(value) if not f.name.startswith('_')}
    if isinstance(value,tuple): return [encoded(x) for x in value]
    return value

def fingerprint(value): return sha256(json.dumps(encoded(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True,order=True)
class Ref:
    resource_id: str
    entity_kind: str
    local_id: int | str
    def __post_init__(self):
        uid(self.resource_id)
        if self.entity_kind not in ('node','element','part','set','condition'):
            fail('invalid_reference','Unknown entity kind.')
        if self.entity_kind in ('node','element'):
            if type(self.local_id) is not int or self.local_id<1: fail('invalid_reference','Positive local native ID required.')
        elif not isinstance(self.local_id,str) or not self.local_id: fail('invalid_reference','Stable object ID required.')

@dataclass(frozen=True)
class ResourceStamp:
    resource_id: str
    state_token: str
    mesh_revision: int
    def __post_init__(self):
        uid(self.resource_id)
        if not isinstance(self.state_token,str) or not self.state_token or type(self.mesh_revision) is not int or self.mesh_revision<0:
            fail('invalid_stamp','Source token and nonnegative mesh generation required.')

@dataclass(frozen=True)
class SnapshotStamp:
    document_id: str
    revision: int
    epoch: str
    resources: tuple[ResourceStamp,...]
    def __post_init__(self):
        uid(self.document_id)
        if type(self.revision) is not int or self.revision<0 or not isinstance(self.epoch,str) or not self.epoch or not isinstance(self.resources,tuple) or any(not isinstance(r,ResourceStamp) for r in self.resources):
            fail('invalid_stamp','Document revision, opaque nonempty session epoch and immutable resource stamps required.')
        if len({r.resource_id for r in self.resources})!=len(self.resources): fail('invalid_stamp','Duplicate resource stamp.')

@dataclass(frozen=True)
class Node:
    ref: Ref
    xyz: tuple[float,float,float]
    def __post_init__(self):
        if self.ref.entity_kind!='node': fail('invalid_reference','Node reference required.')
        point(self.xyz)

@dataclass(frozen=True)
class Part:
    ref: Ref
    component_id: str
    families: tuple[str,...]
    native_scope: str

@dataclass(frozen=True)
class Cell:
    ref: Ref
    family: str
    nodes: tuple[Ref,...]
    part: Ref
    source_scope: str
    orientation_node: Ref | None = None

@dataclass(frozen=True)
class ExplicitSet:
    ref: Ref
    member_kind: str
    members: tuple[Ref,...]
    orientation_sensitive: bool = False

@dataclass(frozen=True)
class ReferenceUse:
    ref: Ref
    kind: str  # load, constraint, contact, material-axis, other supported dependency
    targets: tuple[Ref,...]  # set refs; contact roles remain ordered
    orientation_sensitive: bool = False
    per_node_value: tuple[float,float,float] | None = None

@dataclass(frozen=True)
class MeshSnapshot:
    stamp: SnapshotStamp
    length_unit: str
    nodes: tuple[Node,...]
    cells: tuple[Cell,...]
    parts: tuple[Part,...]
    sets: tuple[ExplicitSet,...] = ()
    uses: tuple[ReferenceUse,...] = ()
    dependency_closure_complete: bool = False
    _nodes: object = field(init=False,repr=False,compare=False)
    _cells: object = field(init=False,repr=False,compare=False)
    _parts: object = field(init=False,repr=False,compare=False)
    _sets: object = field(init=False,repr=False,compare=False)
    def __post_init__(self):
        if not isinstance(self.stamp,SnapshotStamp): fail('invalid_stamp','Typed snapshot stamp required.')
        if self.length_unit not in ('mm','cm','m') or self.dependency_closure_complete is not True:
            fail('incomplete_snapshot','Known length units and complete dependency closure are required.')
        resources={r.resource_id for r in self.stamp.resources}
        for name in ('nodes','cells','parts','sets','uses'):
            values=getattr(self,name)
            cls={'nodes':Node,'cells':Cell,'parts':Part,'sets':ExplicitSet,'uses':ReferenceUse}[name]
            if not isinstance(values,tuple) or any(not isinstance(x,cls) for x in values): fail('mutable_snapshot','Typed immutable snapshot tuples required.')
            if len({x.ref for x in values})!=len(values): fail('ambiguous_reference','Duplicate scoped entity IDs.')
            if any(x.ref.resource_id not in resources for x in values): fail('unstamped_resource','Every entity owner needs a source stamp.')
            if name!='uses': object.__setattr__(self,'_'+name,MappingProxyType({x.ref:x for x in values}))
        for part in self.parts:
            if part.ref.entity_kind!='part' or not isinstance(part.component_id,str) or not part.component_id or not isinstance(part.families,tuple) or not part.families or any(not isinstance(f,str) for f in part.families) or not isinstance(part.native_scope,str) or not part.native_scope:
                fail('invalid_part','Part component, native scope and supported families required.')
        for cell in self.cells:
            if cell.ref.entity_kind!='element' or not isinstance(cell.nodes,tuple) or any(not isinstance(r,Ref) for r in cell.nodes) or not isinstance(cell.part,Ref) or cell.part not in self._parts or not isinstance(cell.source_scope,str) or not cell.source_scope:
                fail('invalid_cell','Typed element/connectivity/part required.')
            if len(set(cell.nodes))!=len(cell.nodes) or (cell.family in ARITY and len(cell.nodes)!=ARITY[cell.family]): fail('invalid_connectivity','Baseline topology must have distinct supported-arity nodes.')
            if cell.orientation_node is not None and (cell.family!='BEAM' or not isinstance(cell.orientation_node,Ref)): fail('invalid_orientation','Only BEAM has an orientation-only node.')
            if cell.family not in self._parts[cell.part].families: fail('part_family','Element family incompatible with assigned part.')
            if any(n not in self._nodes for n in cell.nodes) or (cell.orientation_node is not None and cell.orientation_node not in self._nodes):
                fail('dangling_connectivity','Node owner/reference not present in snapshot.')
        for group in self.sets:
            if group.ref.entity_kind!='set' or group.member_kind not in ('node','element','part') or not isinstance(group.members,tuple):
                fail('invalid_set','Typed immutable explicit membership required.')
            if any(not isinstance(r,Ref) for r in group.members): fail('invalid_set','Typed membership references required.')
            if len(set(group.members))!=len(group.members): fail('invalid_set','Duplicate explicit members.')
            index={'node':self._nodes,'element':self._cells,'part':self._parts}[group.member_kind]
            if any(r not in index for r in group.members): fail('dangling_set','Baseline explicit set must resolve.')
        for use in self.uses:
            if use.ref.entity_kind!='condition' or use.kind not in ('load','constraint','contact','material-axis','connection') or not isinstance(use.targets,tuple) or any(not isinstance(r,Ref) or r not in self._sets for r in use.targets):
                fail('invalid_use','Dependency targets must resolve to explicit sets.')
            if use.kind=='contact' and len(use.targets)!=2: fail('invalid_use','Contact requires ordered two-side target sets.')
            if use.per_node_value is not None:
                point(use.per_node_value)
                if any(self._sets[r].member_kind!='node' for r in use.targets): fail('invalid_use','Per-node value requires explicit node sets.')
    @property
    def digest(self): return fingerprint(self)

@dataclass(frozen=True)
class Quality:
    element: Ref
    metric: str
    value: float
    signed_measure: float
    problems: tuple[str,...] = ()

@dataclass(frozen=True)
class Impact:
    target: Ref
    reasons: tuple[str,...]
    previous_cardinality: int
    surviving_cardinality: int
    projected_cardinality_after_mapping: int
    previous_resultant: tuple[float,float,float] | None = None
    projected_resultant_after_mapping: tuple[float,float,float] | None = None
    status: str = 'requires_explicit_reconnection'

@dataclass(frozen=True)
class MergeApproval:
    source: Ref
    keeper: Ref
    cross_components: bool = False
    contacts: tuple[Ref,...] = ()
    cross_resources: bool = False
    def __post_init__(self):
        if any(not isinstance(r,Ref) or r.entity_kind!='node' for r in (self.source,self.keeper)) or type(self.cross_components) is not bool or type(self.cross_resources) is not bool:
            fail('invalid_merge_approval','Approval needs exact node references and boolean crossing permissions.')
        if not isinstance(self.contacts,tuple) or any(not isinstance(r,Ref) or r.entity_kind!='condition' for r in self.contacts) or len(set(self.contacts))!=len(self.contacts):
            fail('invalid_merge_approval','Immutable distinct contact references required.')

@dataclass(frozen=True)
class MeshEditCandidate:
    operation: str
    base: MeshSnapshot
    source_digest: str
    node_updates: tuple[Node,...] = ()
    cell_updates: tuple[Cell,...] = ()
    set_updates: tuple[ExplicitSet,...] = ()
    removed_nodes: tuple[Ref,...] = ()
    removed_cells: tuple[Ref,...] = ()
    merge_map: tuple[tuple[Ref,Ref],...] = ()
    merge_tolerance: float | None = None
    merge_approvals: tuple[MergeApproval,...] = ()
    orphan_policy: str | None = None
    new_orphans: tuple[Ref,...] = ()
    affected_resources: tuple[str,...] = ()
    mesh_revision_resources: tuple[str,...] = ()
    quality_before: tuple[Quality,...] = ()
    quality_after: tuple[Quality,...] = ()
    impacts: tuple[Impact,...] = ()
    @property
    def source_stamp(self): return self.base.stamp
    def iter_nodes(self):
        changed={x.ref:x for x in self.node_updates};removed=set(self.removed_nodes)
        for item in self.base.nodes:
            if item.ref not in removed: yield changed.get(item.ref,item)
    def iter_cells(self):
        changed={x.ref:x for x in self.cell_updates};removed=set(self.removed_cells)
        for item in self.base.cells:
            if item.ref not in removed: yield changed.get(item.ref,item)
    def iter_sets(self):
        changed={x.ref:x for x in self.set_updates}
        for item in self.base.sets: yield changed.get(item.ref,item)
    def assert_current(self,stamp,source_digest):
        if stamp!=self.source_stamp or source_digest!=self.source_digest:
            fail('stale_mesh_candidate','Document/epoch/source token/mesh generation or geometry changed.')


ARITY={'TRUSS':2,'BEAM':2,'SH3N':3,'SHELL':4,'TETRA4':4,'BRICK':8}
HEX_SIGNS=((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
HEX_FACES=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))

def _hex_jacobian(p,xi,eta,zeta):
    p=[sub(x,p[0]) for x in p]
    derivatives=[(sx*(1+sy*eta)*(1+sz*zeta)/8,sy*(1+sx*xi)*(1+sz*zeta)/8,sz*(1+sx*xi)*(1+sy*eta)/8) for sx,sy,sz in HEX_SIGNS]
    columns=[tuple(sum(p[i][k]*derivatives[i][j] for i in range(8)) for k in range(3)) for j in range(3)]
    determinant=dot(columns[0],cross(columns[1],columns[2]));denominator=math.prod(norm(x) for x in columns)
    return determinant,determinant/denominator if denominator else 0.

def _quality(cell,lookup):
    try: return _quality_impl(cell,lookup)
    except (OverflowError,ZeroDivisionError):
        return Quality(cell.ref,'geometry',0.,0.,('nonfinite_geometry',))

def _quality_impl(cell,lookup):
    if cell.family not in ARITY: return Quality(cell.ref,'unsupported',0,0,('unsupported_quality_profile',))
    if len(cell.nodes)!=ARITY[cell.family] or len(set(cell.nodes))!=len(cell.nodes):
        return Quality(cell.ref,'connectivity',0,0,('repeated_or_wrong_connectivity',))
    try: p=[lookup(r).xyz for r in cell.nodes]
    except KeyError: return Quality(cell.ref,'connectivity',0,0,('dangling_connectivity',))
    edges=[sub(b,a) for i,a in enumerate(p) for b in p[i+1:]];size=max(map(norm,edges),default=0)
    if not size or not math.isfinite(size): return Quality(cell.ref,'geometry',0,0,('degenerate_or_nonfinite',))
    s=[scale(sub(x,p[0]),1/size) for x in p];problems=[];q=1.;measure=0.;metric=''
    if cell.family in ('TRUSS','BEAM'):
        metric='normalized_length';measure=norm(sub(p[1],p[0]));q=measure/size
        if cell.orientation_node is not None and cell.orientation_node not in cell.nodes:
            v=sub(lookup(cell.orientation_node).xyz,p[0]);den=norm(v)*measure
            if not den or norm(cross(sub(p[1],p[0]),v))/den<=1e-12: problems.append('degenerate_beam_orientation')
    elif cell.family=='SH3N':
        area=norm(cross(s[1],s[2]))/2;den=sum(dot(sub(a,b),sub(a,b)) for i,a in enumerate(s) for b in s[i+1:])
        q=4*math.sqrt(3)*area/den;measure=area*size*size;metric='triangle_mean_ratio'
        if area<=1e-12: problems.append('degenerate')
    elif cell.family=='TETRA4':
        volume=dot(s[1],cross(s[2],s[3]))/6;den=sum(dot(sub(a,b),sub(a,b)) for i,a in enumerate(s) for b in s[i+1:])
        q=12*(3*abs(volume))**(2/3)/den;measure=volume*size**3;metric='tet_mean_ratio'
        if volume<=1e-12: problems.append('inverted_or_degenerate')
    elif cell.family=='SHELL':
        reference=cross(s[1],s[2]);length=norm(reference);metric='quad_min_corner_scaled_jacobian'
        if length<=1e-12: problems.append('degenerate');normal=(0.,0.,0.)
        else: normal=scale(reference,1/length)
        values=[]
        for i in range(4):
            a,b=sub(s[(i+1)%4],s[i]),sub(s[(i-1)%4],s[i]);den=norm(a)*norm(b)
            values.append(dot(cross(a,b),normal)/den if den else 0.)
        q=min(values);measure=sum(dot(cross(s[i],s[i+1]),normal)/2 for i in (1,2))*size**2
        if abs(dot(s[3],normal))>1e-8: problems.append('unsupported_warped_quad')
        if q<=1e-12: problems.append('inverted_or_degenerate')
    else:
        metric='hex_min_scaled_jacobian_27';samples=[_hex_jacobian(s,*t) for t in product((-1.,0.,1.),repeat=3)]
        q=min(x[1] for x in samples)
        if min(x[0] for x in samples)<=1e-12: problems.append('inverted_or_degenerate')
        gauss=(-1/math.sqrt(3),1/math.sqrt(3));measure=sum(_hex_jacobian(s,*t)[0] for t in product(gauss,repeat=3))*size**3
        center=tuple(sum(x[k] for x in s)/8 for k in range(3))
        for face in HEX_FACES:
            p0,p1,p2,p3=[s[i] for i in face]
            fc=tuple((p0[k]+p1[k]+p2[k]+p3[k])/4 for k in range(3))
            outward=sub(fc,center)
            for a,b,c in ((p0,p1,p2),(p0,p2,p3)):
                if dot(cross(sub(b,a),sub(c,a)),outward)<=1e-12: problems.append('invalid_hex_face_orientation')
    if not all(math.isfinite(x) for x in (q,measure)): problems.append('nonfinite_geometry')
    if q<.1: problems.append('below_quality_limit')
    return Quality(cell.ref,metric,q,measure,tuple(sorted(set(problems))))


def _selection(snapshot,refs,index,kind):
    values=tuple(refs)
    if not values or any(not isinstance(r,Ref) or r.entity_kind!=kind or r not in index for r in values) or len(set(values))!=len(values):
        fail('invalid_selection','Nonempty distinct exact scoped references required.')
    return values

def _members_as_nodes(snapshot,group):
    if group.member_kind=='node': return frozenset(group.members)
    cells=[snapshot._cells[r] for r in group.members] if group.member_kind=='element' else [c for c in snapshot.cells if c.part in group.members]
    return frozenset(n for c in cells for n in c.nodes)

def _finish(candidate,affected_cells,*,normal_flip=False):
    base=candidate.base;node_updates={n.ref:n for n in candidate.node_updates};cell_updates={c.ref:c for c in candidate.cell_updates}
    deleted_nodes=set(candidate.removed_nodes);deleted_cells=set(candidate.removed_cells)
    def node(r):
        if r in deleted_nodes: raise KeyError(r)
        return node_updates.get(r) or base._nodes[r]
    before=tuple(_quality(base._cells[r],base._nodes.__getitem__) for r in sorted(affected_cells))
    after=tuple(_quality(cell_updates.get(r) or base._cells[r],node) for r in sorted(affected_cells-deleted_cells))
    if not normal_flip:
        for ref in affected_cells-deleted_cells:
            previous=base._cells[ref];current=cell_updates.get(ref) or previous
            if current.family in ('SH3N','SHELL'):
                old=[base._nodes[r].xyz for r in previous.nodes[:3]];new=[node(r).xyz for r in current.nodes[:3]]
                a=cross(sub(old[1],old[0]),sub(old[2],old[0]));b=cross(sub(new[1],new[0]),sub(new[2],new[0]))
                if norm(a)>0 and norm(b)>0 and dot(scale(a,1/norm(a)),scale(b,1/norm(b)))<=1e-12:
                    fail('implicit_normal_reversal','Use explicit shell-normal reversal; this edit reverses or passes through the previous normal.',(ref,))
    problems=[q for q in after if q.problems]
    if problems: fail('mesh_quality','Edit creates unsupported, inverted, degenerate or poor geometry.',tuple(problems))
    signatures={}
    for c in candidate.iter_cells():
        signature=(c.family,frozenset(c.nodes))
        if signature in signatures and (c.ref in affected_cells or signatures[signature] in affected_cells):
            fail('duplicate_elements','Edit creates coincident duplicate element connectivity.',(signatures[signature],c.ref))
        signatures[signature]=c.ref
    changed_nodes=set(node_updates)|deleted_nodes
    resources={r.resource_id for r in changed_nodes|affected_cells|deleted_cells}
    affected_parts={base._cells[r].part for r in affected_cells}|{c.part for c in candidate.cell_updates}
    updated_sets={s.ref:s for s in candidate.set_updates};mapping=dict(candidate.merge_map);impacts=[];set_impacts={}
    for group in base.sets:
        hits=(set(group.members)&(changed_nodes|affected_cells|affected_parts))
        # Mesh generations invalidate explicit memberships even when a number survives.
        generation_hit=any(r.resource_id in resources for r in group.members)
        if not hits and not generation_hit and group.ref not in updated_sets: continue
        reasons=[]
        if generation_hit: reasons.append('mesh_generation_changed')
        if group.ref in updated_sets: reasons.append('explicit_membership_replaced')
        if normal_flip and (group.orientation_sensitive or group.member_kind in ('element','part')): reasons.append('surface_orientation_changed')
        remaining=set(group.members)-deleted_nodes-deleted_cells
        projected=set(updated_sets[group.ref].members) if group.ref in updated_sets else {mapping.get(r,r) for r in group.members if r not in deleted_cells and (r not in deleted_nodes or r in mapping)}
        impact=Impact(group.ref,tuple(reasons),len(group.members),len(remaining),len(projected))
        impacts.append(impact);set_impacts[group.ref]=impact
    live_cells={r:c for r,c in cell_updates.items()}
    def live_cell(ref):
        return None if ref in deleted_cells else live_cells.get(ref) or base._cells.get(ref)
    def expanded(group,members):
        if group.member_kind=='node': return set(members)-deleted_nodes
        cells=[live_cell(r) for r in members] if group.member_kind=='element' else [c for c in candidate.iter_cells() if c.part in members]
        return {n for c in cells if c is not None for n in c.nodes}
    def projected_members(group):
        if group.ref in updated_sets: return updated_sets[group.ref].members
        return tuple(mapping.get(r,r) for r in group.members if r not in deleted_cells and (r not in deleted_nodes or r in mapping))
    for use in base.uses:
        targets=[set_impacts[r] for r in use.targets if r in set_impacts]
        if not targets: continue
        old=set().union(*(_members_as_nodes(base,base._sets[r]) for r in use.targets))
        alive=set().union(*(expanded(base._sets[r],base._sets[r].members) for r in use.targets))
        projected=set().union(*(expanded(base._sets[r],projected_members(base._sets[r])) for r in use.targets))
        reasons={'target_set_requires_reconnection','mechanical_components_require_validation'}
        if use.kind=='contact': reasons.add('contact_pair_membership_review')
        if normal_flip and use.orientation_sensitive: reasons.add('directed_condition_orientation_review')
        if use.kind=='material-axis': reasons.add('material_axis_review')
        before_result=scale(use.per_node_value,len(old)) if use.per_node_value is not None else None
        after_result=scale(use.per_node_value,len(projected)) if use.per_node_value is not None else None
        if before_result!=after_result: reasons.add('per_node_load_resultant_changes_if_mapping_accepted')
        impacts.append(Impact(use.ref,tuple(sorted(reasons)),len(old),len(alive),len(projected),before_result,after_result))
    if fingerprint(base)!=candidate.source_digest: fail('source_mutated','Source changed while computing a candidate.')
    touched=resources|{r.resource_id for r in updated_sets}
    return replace(candidate,affected_resources=tuple(sorted(touched)),mesh_revision_resources=tuple(sorted(resources)),quality_before=before,quality_after=after,impacts=tuple(impacts))


def move_nodes(snapshot,positions,*,length_unit):
    if not isinstance(positions,Mapping): fail('invalid_positions','Exact node-to-position mapping required.')
    if length_unit!=snapshot.length_unit: fail('unit_mismatch','Convert coordinates explicitly before editing.')
    refs=_selection(snapshot,positions,snapshot._nodes,'node')
    updates=tuple(Node(r,point(positions[r])) for r in refs if positions[r]!=snapshot._nodes[r].xyz)
    if not updates: fail('no_change','Coordinates are unchanged.')
    changed={n.ref for n in updates};affected={c.ref for c in snapshot.cells if changed.intersection(c.nodes) or c.orientation_node in changed}
    return _finish(MeshEditCandidate('move_nodes',snapshot,snapshot.digest,node_updates=updates),affected)


def merge_nodes(snapshot,mapping,*,tolerance,length_unit,approvals=()):
    if not isinstance(mapping,Mapping) or not isinstance(approvals,tuple) or any(not isinstance(a,MergeApproval) for a in approvals): fail('invalid_merge_map','Typed explicit mapping and immutable approvals required.')
    if length_unit!=snapshot.length_unit or not finite(tolerance) or tolerance<=0:
        fail('invalid_tolerance','Positive finite tolerance in the explicit source length unit required.')
    sources=_selection(snapshot,mapping,snapshot._nodes,'node');keepers=tuple(mapping[r] for r in sources)
    if any(not isinstance(k,Ref) or k not in snapshot._nodes or k.entity_kind!='node' for k in keepers) or set(sources)&set(keepers):
        fail('invalid_merge_map','Use exact existing keepers; self/chained/cyclic mapping is rejected.')
    authorization={(a.source,a.keeper):a for a in approvals}
    if len(authorization)!=len(approvals) or set(authorization)-set(zip(sources,keepers)):
        fail('invalid_merge_approval','Approvals must correspond exactly to requested source/keeper pairs.')
    components={r:frozenset(snapshot._parts[c.part].component_id for c in snapshot.cells if r in c.nodes or r==c.orientation_node) for r in set(sources)|set(keepers)}
    for source,keeper in zip(sources,keepers):
        if norm(sub(snapshot._nodes[source].xyz,snapshot._nodes[keeper].xyz))>tolerance:
            fail('outside_tolerance','Selected source is outside tolerance of its explicit keeper.',(source,keeper))
        contacts=[]
        for use in snapshot.uses:
            if use.kind!='contact': continue
            roles=[_members_as_nodes(snapshot,snapshot._sets[r]) for r in use.targets]
            if tuple(source in role for role in roles)!=tuple(keeper in role for role in roles): contacts.append(use.ref)
        approval=authorization.get((source,keeper))
        if source.resource_id!=keeper.resource_id and (approval is None or not approval.cross_resources):
            fail('source_boundary','Cross-resource merge requires an exact additional approval.',(source,keeper))
        if components[source]!=components[keeper] and (approval is None or not approval.cross_components):
            fail('component_boundary','Cross-component merge requires an exact additional approval.',(source,keeper))
        if contacts and (approval is None or set(approval.contacts)!=set(contacts)):
            fail('contact_boundary','Contact-side merge requires explicit affected-contact approval.',tuple(contacts))
    updates=[];affected=set()
    for cell in snapshot.cells:
        nodes=tuple(mapping.get(r,r) for r in cell.nodes);orientation=mapping.get(cell.orientation_node,cell.orientation_node)
        if nodes!=cell.nodes or orientation!=cell.orientation_node:
            updates.append(replace(cell,nodes=nodes,orientation_node=orientation));affected.add(cell.ref)
    candidate=MeshEditCandidate('merge_nodes',snapshot,snapshot.digest,cell_updates=tuple(updates),removed_nodes=sources,merge_map=tuple(zip(sources,keepers)),merge_tolerance=tolerance,merge_approvals=approvals)
    return _finish(candidate,affected)


def delete_elements(snapshot,refs,*,orphan_policy):
    selected=_selection(snapshot,refs,snapshot._cells,'element')
    if orphan_policy not in ('keep','delete_new'): fail('orphan_policy','Choose keep or delete_new explicitly.')
    removed=set(selected)
    def cell_nodes(cell): return set(cell.nodes)|({cell.orientation_node} if cell.orientation_node is not None else set())
    before=set().union(*(cell_nodes(c) for c in snapshot.cells))
    after=set().union(*(cell_nodes(c) for c in snapshot.cells if c.ref not in removed))
    orphans=tuple(sorted(before-after));deletions=orphans if orphan_policy=='delete_new' else ()
    candidate=MeshEditCandidate('delete_elements',snapshot,snapshot.digest,removed_cells=selected,removed_nodes=deletions,new_orphans=orphans,orphan_policy=orphan_policy)
    return _finish(candidate,removed)


def flip_shell_normals(snapshot,refs):
    selected=_selection(snapshot,refs,snapshot._cells,'element');updates=[]
    for r in selected:
        cell=snapshot._cells[r]
        if cell.family not in ('SH3N','SHELL'): fail('not_shell','Only shell elements have this normal reversal.')
        order=(0,2,1) if cell.family=='SH3N' else (0,3,2,1)
        updates.append(replace(cell,nodes=tuple(cell.nodes[i] for i in order)))
    return _finish(MeshEditCandidate('flip_shell_normals',snapshot,snapshot.digest,cell_updates=tuple(updates)),set(selected),normal_flip=True)


def reassign_parts(snapshot,assignments):
    if not isinstance(assignments,Mapping): fail('invalid_assignment','Exact element-to-part mapping required.')
    refs=_selection(snapshot,assignments,snapshot._cells,'element');updates=[]
    for r in refs:
        target=assignments[r];cell=snapshot._cells[r]
        if not isinstance(target,Ref) or target not in snapshot._parts or cell.family not in snapshot._parts[target].families:
            fail('part_family','Existing compatible target part required.')
        if target!=cell.part: updates.append(replace(cell,part=target))
    if not updates: fail('no_change','Part ownership is unchanged.')
    return _finish(MeshEditCandidate('reassign_parts',snapshot,snapshot.digest,cell_updates=tuple(updates)),{c.ref for c in updates})


def reassign_set(snapshot,set_ref,members):
    if not isinstance(set_ref,Ref) or set_ref not in snapshot._sets: fail('invalid_set','Exact current set reference required.')
    group=snapshot._sets[set_ref];values=tuple(members);index={'node':snapshot._nodes,'element':snapshot._cells,'part':snapshot._parts}[group.member_kind]
    if not values or any(not isinstance(r,Ref) or r not in index or r.entity_kind!=group.member_kind for r in values) or len(set(values))!=len(values):
        fail('invalid_membership','Nonempty distinct typed members of the set kind required.')
    if set(values)==set(group.members): fail('no_change','Explicit set membership is unchanged.')
    candidate=MeshEditCandidate('reassign_set',snapshot,snapshot.digest,set_updates=(replace(group,members=values),))
    return _finish(candidate,set())
