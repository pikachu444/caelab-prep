"""Two fixed, distinct mesh fixtures with analytical expected geometry/relations.

Pure candidate only: these tests do not claim session Undo/native/UI coverage.
"""
from dataclasses import replace
import math
import pytest
from mesh_operations import (Ref,ResourceStamp,SnapshotStamp,Node,Cell,Part,ExplicitSet,ReferenceUse,
    MeshSnapshot,MergeApproval,MeshEditError,move_nodes,merge_nodes,delete_elements,flip_shell_normals,
    reassign_parts,reassign_set,sub,cross,dot,_quality)

R='00000000-0000-0000-0000-000000000001'
S='00000000-0000-0000-0000-000000000002'
D='00000000-0000-0000-0000-000000000003'

def ref(kind,id,resource=R): return Ref(resource,kind,id)
def node(id,xyz,resource=R): return Node(ref('node',id,resource),tuple(xyz))
def part(id,component,families,resource=R): return Part(ref('part',id,resource),component,tuple(families),'/PART/'+id)
def cell(id,family,ids,owner,resource=R,orientation=None):
    return Cell(ref('element',id,resource),family,tuple(ref('node',n,resource) for n in ids),owner.ref,'/'+family+'/'+str(id),orientation)
def stamp(): return SnapshotStamp(D,7,'00000000-0000-0000-0000-000000000004',(ResourceStamp(R,'original-r',4),ResourceStamp(S,'original-s',8)))

@pytest.fixture
def shell():
    a=part('1','left',('SHELL',));b=part('2','right',('SHELL','SH3N'));c=part('3','contact-other',('SHELL',),S)
    ns=[node(i,p) for i,p in enumerate(((0,0,0),(1,0,0),(1,1,0),(0,1,0),(2,0,0),(2,1,0),(2.0001,1,0),(3,0,0)),1)]
    ns += [node(99,(20,20,20))]
    ns += [node(i,p,S) for i,p in enumerate(((0,0,0),(1,0,0),(1,1,0),(0,1,0)),1)]
    cells=(cell(1,'SHELL',(1,2,3,4),a),cell(2,'SHELL',(2,5,6,3),b),cell(3,'SH3N',(5,8,7),b),cell(1,'SHELL',(1,2,3,4),c,S))
    groups=(ExplicitSet(ref('set','left-surface'),'node',(ref('node',1),ref('node',4)),True),
            ExplicitSet(ref('set','right-surface'),'node',(ref('node',1,S),ref('node',4,S)),True),
            ExplicitSet(ref('set','nodal-load'),'node',(ref('node',1),ref('node',1,S))),
            ExplicitSet(ref('set','shells'),'element',(ref('element',1),ref('element',2)),True),
            ExplicitSet(ref('set','part-region'),'part',(a.ref,)))
    uses=(ReferenceUse(ref('condition','contact'),'contact',(groups[0].ref,groups[1].ref),True),
          ReferenceUse(ref('condition','force'),'load',(groups[2].ref,),False,(5.,0.,0.)),
          ReferenceUse(ref('condition','material-direction'),'material-axis',(groups[3].ref,),True))
    return MeshSnapshot(stamp(),'mm',tuple(ns),cells,(a,b,c),groups,uses,True)

@pytest.fixture
def solid():
    h=part('hex','body',('BRICK',));t=part('tet','body',('TETRA4',));b=part('beam','frame',('BEAM','TRUSS'))
    points=((0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1),(2,.5,.5),(3,.5,.5),(2,.5,1.5),(4,.5,.5))
    ns=tuple(node(i,p) for i,p in enumerate(points,1))+(node(99,(100,100,100)),)
    cells=(cell(1,'BRICK',tuple(range(1,9)),h),cell(2,'TETRA4',(2,3,6,9),t),cell(3,'BEAM',(9,10),b,orientation=ref('node',11)),cell(4,'TRUSS',(10,12),b))
    groups=(ExplicitSet(ref('set','loaded'),'node',(ref('node',9),ref('node',10))),ExplicitSet(ref('set','solids'),'element',(ref('element',1),ref('element',2))))
    uses=(ReferenceUse(ref('condition','force'),'load',(groups[0].ref,),False,(0.,2.,0.)),ReferenceUse(ref('condition','frame'),'material-axis',(groups[0].ref,),True))
    return MeshSnapshot(stamp(),'mm',ns,cells,(h,t,b),groups,uses,True)


def test_move_shared_node_sparse_source_and_stamp(shell):
    original=shell.digest
    result=move_nodes(shell,{ref('node',2):(1.05,0.,0.)},length_unit='mm')
    assert result.base is shell and len(result.node_updates)==1 and result.cell_updates==()
    assert {q.element for q in result.quality_after}=={ref('element',1),ref('element',2)}
    assert next(n.xyz for n in result.iter_nodes() if n.ref==ref('node',2))==(1.05,0.,0.)
    assert next(n.xyz for n in result.iter_nodes() if n.ref==ref('node',2,S))==(1,0,0)
    assert shell.digest==original and shell._nodes[ref('node',2)].xyz==(1,0,0)
    assert result.source_stamp==stamp() and result.mesh_revision_resources==(R,)
    assert {i.target for i in result.impacts}>={ref('condition','force'),ref('condition','contact')}
    result.assert_current(stamp(),original)
    for changed in (replace(stamp(),revision=8),replace(stamp(),epoch='00000000-0000-0000-0000-000000000005'),replace(stamp(),resources=(ResourceStamp(R,'original-r',5),stamp().resources[1])),replace(stamp(),resources=(ResourceStamp(R,'changed-token',4),stamp().resources[1]))):
        with pytest.raises(MeshEditError,match='changed'): result.assert_current(changed,original)


def test_merge_selected_tolerance_keeper_no_global_search(shell):
    before=shell.digest
    result=merge_nodes(shell,{ref('node',7):ref('node',6)},tolerance=.001,length_unit='mm')
    assert result.removed_nodes==(ref('node',7),)
    assert result.node_updates==() and len(result.cell_updates)==1
    assert result.cell_updates[0].nodes==(ref('node',5),ref('node',8),ref('node',6))
    assert result.base._nodes[ref('node',6)].xyz==(2,1,0)
    assert ref('node',1,S) in {n.ref for n in result.iter_nodes()}  # coincident nodes outside map survive
    assert shell.digest==before
    with pytest.raises(MeshEditError) as caught: merge_nodes(shell,{ref('node',7):ref('node',6)},tolerance=1e-5,length_unit='mm')
    assert caught.value.code=='outside_tolerance'
    with pytest.raises(MeshEditError) as caught: merge_nodes(shell,{ref('node',7):ref('node',6),ref('node',6):ref('node',5)},tolerance=2,length_unit='mm')
    assert caught.value.code=='invalid_merge_map'


def test_cross_source_contact_merge_explicit_approval_and_load_resultant(shell):
    source,keeper=ref('node',1),ref('node',1,S);contact=ref('condition','contact')
    with pytest.raises(MeshEditError) as caught: merge_nodes(shell,{source:keeper},tolerance=.01,length_unit='mm')
    assert caught.value.code=='source_boundary'
    with pytest.raises(MeshEditError) as caught:
        merge_nodes(shell,{source:keeper},tolerance=.01,length_unit='mm',approvals=(MergeApproval(source,keeper,True,(),True),))
    assert caught.value.code=='contact_boundary'
    result=merge_nodes(shell,{source:keeper},tolerance=.01,length_unit='mm',approvals=(MergeApproval(source,keeper,True,(contact,),True),))
    force=next(i for i in result.impacts if i.target==ref('condition','force'))
    assert force.previous_cardinality==2 and force.projected_cardinality_after_mapping==1
    assert force.previous_resultant==(10.,0.,0.) and force.projected_resultant_after_mapping==(5.,0.,0.)
    assert 'per_node_load_resultant_changes_if_mapping_accepted' in force.reasons
    assert next(s for s in result.iter_sets() if s.ref==ref('set','nodal-load')).members==(source,keeper)
    assert all(i.status=='requires_explicit_reconnection' for i in result.impacts)


def test_merge_collapse_rejected_without_mutation(shell):
    original=shell.digest
    with pytest.raises(MeshEditError) as caught:
        merge_nodes(shell,{ref('node',8):ref('node',5)},tolerance=1.1,length_unit='mm')
    assert caught.value.code=='mesh_quality' and shell.digest==original


@pytest.mark.parametrize('fixture',['shell','solid'])
def test_delete_orphan_policy_retains_existing_orphans(fixture,request):
    snap=request.getfixturevalue(fixture);target=ref('element',3)
    kept=delete_elements(snap,(target,),orphan_policy='keep')
    removed=delete_elements(snap,(target,),orphan_policy='delete_new')
    expected={ref('node',7),ref('node',8)} if fixture=='shell' else {ref('node',11)}
    assert set(kept.new_orphans)==expected==set(removed.removed_nodes)
    assert set(n.ref for n in kept.iter_nodes())==set(n.ref for n in snap.nodes)
    assert ref('node',99) in {n.ref for n in removed.iter_nodes()}
    assert target not in {c.ref for c in removed.iter_cells()}


def test_shell_flip_analytic_orientation_and_directed_impacts(shell):
    original=shell._cells[ref('element',1)];result=flip_shell_normals(shell,(original.ref,))
    changed=result.cell_updates[0]
    assert changed.nodes==(original.nodes[0],original.nodes[3],original.nodes[2],original.nodes[1])
    def normal(cell):
        p=[shell._nodes[r].xyz for r in cell.nodes]
        return cross(sub(p[1],p[0]),sub(p[2],p[0]))
    assert dot(normal(original),normal(changed))==-1
    assert result.quality_before[0].signed_measure==pytest.approx(result.quality_after[0].signed_measure)
    assert 'material_axis_review' in next(i.reasons for i in result.impacts if i.target==ref('condition','material-direction'))
    with pytest.raises(MeshEditError) as caught:
        move_nodes(shell,{ref('node',8):(1.,0.,0.)},length_unit='mm')
    assert caught.value.code=='implicit_normal_reversal'


def test_part_assignment_and_set_membership_are_separate(shell):
    target=ref('part','2');cell_ref=ref('element',1)
    result=reassign_parts(shell,{cell_ref:target})
    assert result.cell_updates[0].part==target and result.set_updates==()
    assert tuple(result.iter_sets())==shell.sets
    group=ref('set','nodal-load');members=(ref('node',5),ref('node',6),ref('node',7))
    changed=reassign_set(shell,group,members)
    assert changed.cell_updates==() and tuple(changed.iter_cells())==shell.cells
    assert changed.set_updates[0].members==members and changed.mesh_revision_resources==()
    load=next(i for i in changed.impacts if i.target==ref('condition','force'))
    assert load.previous_resultant==(10.,0.,0.) and load.projected_resultant_after_mapping==(15.,0.,0.)
    with pytest.raises(MeshEditError) as caught: reassign_parts(shell,{ref('element',3):ref('part','1')})
    assert caught.value.code=='part_family'


def test_mixed_hex_tet_beam_baseline_and_move(solid):
    expected={'BRICK':1.,'TETRA4':1/6,'BEAM':1.,'TRUSS':1.}
    for c in solid.cells:
        q=_quality(c,solid._nodes.__getitem__)
        assert not q.problems and q.signed_measure==pytest.approx(expected[c.family])
    brick=_quality(solid.cells[0],solid._nodes.__getitem__)
    assert brick.metric=='hex_min_scaled_jacobian_27' and brick.value==pytest.approx(1.)
    result=move_nodes(solid,{ref('node',7):(1.,1.,1.1)},length_unit='mm')
    assert {q.element for q in result.quality_after}=={ref('element',1)}
    assert all(not q.problems and q.signed_measure>0 for q in result.quality_after)


def test_hex_fold_tet_inversion_and_beam_orientation_rejected(solid):
    before=solid.digest
    for mapping in ({ref('node',7):(-1.,-1.,-1.)},{ref('node',9):(.5,.5,.5)},{ref('node',11):(2.5,.5,.5)}):
        with pytest.raises(MeshEditError) as caught: move_nodes(solid,mapping,length_unit='mm')
        assert caught.value.code=='mesh_quality'
        assert solid.digest==before
    moved={ref('node',7):Node(ref('node',7),(-1.,-1.,-1.))}
    q=_quality(solid.cells[0],lambda r:moved.get(r) or solid._nodes[r])
    assert 'inverted_or_degenerate' in q.problems


def test_units_unknown_closure_bad_coordinates_and_noop_rejected(shell):
    for positions,unit in (({ref('node',2):(1.,0.,0.)},'mm'),({ref('node',2):(1.,0.,0.)},'m'),({ref('node',2):(math.nan,0.,0.)},'mm')):
        with pytest.raises(MeshEditError): move_nodes(shell,positions,length_unit=unit)
    with pytest.raises(MeshEditError): replace(shell,dependency_closure_complete=False)
    with pytest.raises(MeshEditError): replace(shell,nodes=shell.nodes+(shell.nodes[0],))
    with pytest.raises(MeshEditError): reassign_set(shell,ref('set','nodal-load'),(ref('element',1),))


def test_positive_hex_volume_does_not_hide_local_inversion(solid):
    # Only vertex 7 moves inward. The integrated trilinear volume is still
    # 13/40; a positive total cannot qualify the negative corner Jacobian.
    folded=Node(ref('node',7),(.1,.1,.1))
    q=_quality(solid.cells[0],lambda r:folded if r==folded.ref else solid._nodes[r])
    assert q.signed_measure==pytest.approx(13/40) and q.value<0
    assert 'inverted_or_degenerate' in q.problems
    with pytest.raises(MeshEditError) as caught:
        move_nodes(solid,{folded.ref:folded.xyz},length_unit='mm')
    assert caught.value.code=='mesh_quality'


def test_deleted_element_targets_do_not_keep_old_surface_cardinality(shell):
    directed=ReferenceUse(ref('condition','surface-direction'),'material-axis',(ref('set','shells'),),True)
    snap=replace(shell,uses=shell.uses+(directed,))
    result=delete_elements(snap,(ref('element',1),),orphan_policy='keep')
    impact=next(i for i in result.impacts if i.target==directed.ref)
    # Original two quads share 2 nodes: 6 unique targets. Surviving quad:4.
    assert impact.previous_cardinality==6
    assert impact.surviving_cardinality==4 and impact.projected_cardinality_after_mapping==4
    assert next(g for g in result.iter_sets() if g.ref==ref('set','shells')).members==(ref('element',1),ref('element',2))


def test_exact_approval_provenance_and_malformed_inputs(shell):
    a,b=ref('node',1),ref('node',1,S);approval=MergeApproval(a,b,True,(ref('condition','contact'),),True)
    result=merge_nodes(shell,{a:b},tolerance=.01,length_unit='mm',approvals=(approval,))
    assert result.merge_approvals==(approval,) and result.merge_tolerance==.01
    for call in (lambda:merge_nodes(shell,{ref('node',7):[]},tolerance=.1,length_unit='mm'),
                 lambda:move_nodes(shell,[(ref('node',1),(1,2,3))],length_unit='mm'),
                 lambda:reassign_set(shell,ref('set','nodal-load'),([],)),
                 lambda:MergeApproval(a,b,True,[ref('condition','contact')],True)):
        with pytest.raises(MeshEditError): call()


def test_reopened_same_document_same_revision_rejects_old_session_epoch(shell):
    result=move_nodes(shell,{ref('node',2):(1.05,0.,0.)},length_unit='mm')
    # Reopen may preserve document ID, revision and exact source data, but the
    # owning PrepSession generates a new UUID epoch. Never coerce it to a count.
    reopened=replace(shell.stamp,epoch='00000000-0000-0000-0000-000000000006')
    with pytest.raises(MeshEditError) as caught: result.assert_current(reopened,shell.digest)
    assert caught.value.code=='stale_mesh_candidate'
    with pytest.raises(MeshEditError): replace(shell.stamp,epoch=2)
