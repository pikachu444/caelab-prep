"""GI4 pure/fake Cone evidence. No native SDK, source generation or feature verdict."""
from copy import deepcopy
import json
import math
from types import SimpleNamespace

import pytest

from caelab_prep.adapters import gmsh_backend as backend,gmsh_worker as worker
from caelab_prep.adapters.gmsh_geometry import (CONICAL_PROBE_POLICY,analytic_signed_residual,
    analytic_unit_normal,conical_blend_shape,plan_analytic_material_probe)
from test_geometry_inspection import source,fake_sdk


def conical_scene(cusp=False,axis_sign=1,*,plane_scale=1.,origin_shift=0.):
    """Independent S-minus-N / W-minus-C domains; shared IDs, finite sloping sides."""
    xy=[(1.,0.),(0.,1.),(1.,1.)] if cusp else [(1.,0.),(0.,1.),(-1.,1.),(-1.,-1.),(1.,-1.)]
    levels=((4.,3.),(8.,6.));points={(level,index):{'backend_tag':1000+level*100+index,
        'xyz':[radius*x,radius*y,z]} for level,(z,radius) in enumerate(levels) for index,(x,y) in enumerate(xy)}
    curves=[]
    def curve(tag,kind,ends,length):
        curves.append({'backend_tag':tag,'geometry_type':kind,'length':length,
            'endpoints':[deepcopy(points[end]) for end in ends],
            'parametric_bounds':{'minimum':[0.],'maximum':[math.pi/2 if kind=='Circle' else length]},
            'adjacent_surface_uuids':[]})
        return tag
    bottom=[];top=[]
    for level,tags in ((0,bottom),(1,top)):
        for i in range(len(xy)):
            j=(i+1)%len(xy);a,b=points[level,i]['xyz'],points[level,j]['xyz']
            tags.append(curve(200+level*100+i,'Circle' if i==0 else 'Line',[(level,i),(level,j)],
                              levels[level][1]*math.pi/2 if i==0 else math.dist(a,b)))
    vertical=[curve(400+i,'Line',[(0,i),(1,i)],math.dist(points[0,i]['xyz'],points[1,i]['xyz'])) for i in range(len(xy))]
    def face(identity,kind,reals,tags,vertices,sample):
        row={'uuid':identity,'geometry_type':kind,'analytic_properties':{'reals':reals},
             'bbox':[min(p[i] for p in vertices) for i in range(3)]+[max(p[i] for p in vertices) for i in range(3)],
             'samples':[{'xyz':sample,'trim_count':1,'face_normal':[12.,13.,14.]}],
             'orientation_by_volume':[{'volume_uuid':'volume','sign':-1}],
             'curve_loops':[{'backend_tag':1,'curve_tags':tags}],
             'parametric_bounds':{'minimum':[0.,0.],'maximum':[math.pi/2,5.]}}
        for tag in tags:next(c for c in curves if c['backend_tag']==abs(tag))['adjacent_surface_uuids'].append(identity)
        return row
    alpha=axis_sign*math.atan(.75);origin=[0.,0.,4.+axis_sign*origin_shift];ref=3.+origin_shift*math.tan(alpha)
    target=face('strip','Cone',[*origin,0.,0.,float(axis_sign),ref,alpha],
        [bottom[0],vertical[1],-top[0],-vertical[0]],[[0.,0.,4.],[6.,6.,8.]],
        [4.5*math.sqrt(.5),4.5*math.sqrt(.5),6.])
    v=sorted((axis_sign*(z-origin[2])/math.cos(alpha) for z in (4.,8.)))
    target['parametric_bounds']={'minimum':[0.,v[0]],'maximum':[math.pi/2,v[1]]}
    surfaces=[target]
    for i in range(1,len(xy)):
        j=(i+1)%len(xy);a,b,c=points[0,i]['xyz'],points[0,j]['xyz'],points[1,j]['xyz']
        u=[y-x for x,y in zip(a,b)];v=[y-x for x,y in zip(a,c)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        scale=max(abs(value) for value in n);n=[value/scale*plane_scale for value in n]
        values=[*n,-math.fsum(x*y for x,y in zip(n,a))]
        vertices=[points[level,index]['xyz'] for level in (0,1) for index in (i,j)]
        sample=[sum(p[k] for p in vertices)/4 for k in range(3)]
        surfaces.append(face('plane-'+str(i),'Plane',values,[bottom[i],vertical[j],-top[i],-vertical[i]],vertices,sample))
    for level,tags in ((0,bottom),(1,top)):
        vertices=[points[level,i]['xyz'] for i in range(len(xy))]
        sample=[sum(p[k] for p in vertices)/len(vertices) for k in range(3)]
        surfaces.append(face('cap-'+str(level),'Plane',[0.,0.,1.,-levels[level][0]],tags,vertices,sample))
    return surfaces,[{'uuid':'volume','backend_tag':10,'surface_uuids':[s['uuid'] for s in surfaces]}],curves


def conical_membership(cusp=False):
    calls=[]
    def inside(dim,tag,xyz,*,parametric):
        assert dim==3 and tag==10 and parametric is False
        calls.append(list(xyz));x,y,z=xyz;r=.75*z
        if not 4<=z<=8:return 0
        if cusp:return int(0<=x<=r and 0<=y<=r and math.hypot(x,y)>=r)
        return int(-r<=x<=r and -r<=y<=r and (x<=0 or y<=0 or math.hypot(x,y)<=r))
    return SimpleNamespace(model=SimpleNamespace(isInside=inside,
        mesh=SimpleNamespace(generate=lambda *args:pytest.fail('No mesh in GI4')))),calls


@pytest.mark.parametrize('cusp',[False,True])
def test_finite_conical_shapes_and_raw_material_membership(cusp):
    geometry=conical_scene(cusp);faces,volumes,curves=geometry;before=deepcopy(geometry)
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm')
    assert shape['eligible'],shape
    assert shape['axial_range']==[4.,8.] and shape['radius']==pytest.approx(7.5)
    assert [end['radius'] for end in shape['end_sections']]==pytest.approx([3.,6.])
    assert shape['curvature_radius_range']==pytest.approx([3.75,7.5])
    sdk,calls=conical_membership(cusp)
    rows=worker._conical_material_side_probes(sdk,*geometry,1e-8,'mm')
    assert len(rows)==3 and len(calls)==6 and all(row['status']=='observed' for row in rows),rows
    by_id={row['surface_uuid']:row for row in rows}
    assert by_id['strip']['normal_reference']=='cone_radial_axial'
    assert by_id['strip']['material_normal_sign']==(-1 if cusp else 1)
    assert all(by_id[identity]['material_normal_sign']==(-1 if cusp else 1) for identity in shape['support_surface_uuids'])
    assert geometry==before
    json.dumps(rows,allow_nan=False)


def test_oblique_planes_are_not_required_to_be_orthogonal():
    geometry=conical_scene();faces,volumes,curves=geometry
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm');assert shape['eligible']
    by_id={face['uuid']:face for face in faces};normals=[analytic_unit_normal(by_id[i],by_id[i]['samples'][0]['xyz']) for i in shape['support_surface_uuids']]
    assert abs(math.fsum(a*b for a,b in zip(*normals)))==pytest.approx(.36)


@pytest.mark.parametrize('cusp',[False,True])
@pytest.mark.parametrize('axis_sign',[-1,1])
@pytest.mark.parametrize('shift',[0.,1.,-1.])
def test_axis_angle_and_origin_reference_reparameterization(cusp,axis_sign,shift):
    geometry=conical_scene(cusp,axis_sign,origin_shift=shift);faces,volumes,curves=geometry
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm');assert shape['eligible'],shape
    assert shape['semi_angle']==axis_sign*math.atan(.75)
    assert shape['axis_direction']==[0.,0.,float(axis_sign)]
    assert shape['curvature_radius_range']==pytest.approx([3.75,7.5],abs=1e-12)
    normal=analytic_unit_normal(faces[0],faces[0]['samples'][0]['xyz'])
    assert normal==pytest.approx((.8*math.sqrt(.5),.8*math.sqrt(.5),-.6),abs=1e-15)
    assert analytic_signed_residual(faces[0],faces[0]['samples'][0]['xyz'])==pytest.approx(0.,abs=1e-14)
    sdk,calls=conical_membership(cusp);rows=worker._conical_material_side_probes(sdk,*geometry,1e-8,'mm')
    assert len(calls)==6 and all(row['status']=='observed' for row in rows)


@pytest.mark.parametrize('scale',[2.,-3.,1e-200,1e200])
def test_arbitrary_plane_scaling_preserves_geometric_material_normal(scale):
    geometry=conical_scene(plane_scale=scale);faces,volumes,curves=geometry
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm');assert shape['eligible'],shape
    sdk,calls=conical_membership();rows=worker._conical_material_side_probes(sdk,*geometry,1e-8,'mm')
    assert len(calls)==6 and all(row['status']=='observed' for row in rows)
    by_id={f['uuid']:f for f in faces}
    for row in rows:
        normal=analytic_unit_normal(by_id[row['surface_uuid']],by_id[row['surface_uuid']]['samples'][0]['xyz'])
        assert normal is not None and math.hypot(*normal)==pytest.approx(1.)
        for side in ('plus','minus'):
            assert row[side]['signed_surface_residual']==analytic_signed_residual(by_id[row['surface_uuid']],row[side]['xyz'])
        if row['normal_reference']=='plane_normal':assert row['material_normal_sign']==(1 if scale>0 else -1)


def test_default_plan_does_not_admit_cone_or_oblique_plane():
    geometry=conical_scene();faces,volumes,curves=geometry
    for face in faces[:2]:
        old=plan_analytic_material_probe(face,faces,volumes,1e-8,'mm')
        opted=plan_analytic_material_probe(face,faces,volumes,1e-8,'mm',conical_supports=True)
        assert old['status']=='indeterminate' and old['reason']=='unsupported_analytic_support'
        assert opted['status']=='ready'
    assert plan_analytic_material_probe(faces[0],faces,volumes,1e-8,'mm',conical_supports=1)['status']=='indeterminate'


def test_negative_nappe_neighbor_has_zero_conservative_clearance():
    neighbor=deepcopy(conical_scene()[0][0]);neighbor['uuid']='neighbor'
    plane={'uuid':'plane','geometry_type':'Plane','analytic_properties':{'reals':[1.,0.,0.,-3.]},
        'samples':[{'xyz':[3.,0.,-4.],'trim_count':1}],'bbox':[3.,-10.,-10.,3.,10.,10.],
        'orientation_by_volume':[{'volume_uuid':'volume','sign':1}]}
    neighbor['bbox']=[-10.,-10.,-10.,10.,10.,10.]
    volume=[{'uuid':'volume','backend_tag':10,'surface_uuids':['plane','neighbor']}]
    # Positive-nappe F+ alone overestimates: the other nappe actually passes here.
    assert analytic_signed_residual(neighbor,[3.,0.,-4.])==pytest.approx(4.8)
    plan=plan_analytic_material_probe(plane,[plane,neighbor],volume,1e-8,'mm',conical_supports=True)
    assert plan['status']=='indeterminate' and plan['reason']=='no_positive_boundary_clearance'


def test_normal_offset_may_cross_reference_section_radius_zero_without_crossing_its_foot():
    target=deepcopy(conical_scene()[0][0]);alpha=math.acos(.001)
    target['analytic_properties']['reals']=[0.,0.,0.,0.,0.,1.,1.,alpha]
    target['samples'][0]['xyz']=[1.,0.,0.];target['bbox']=[-100.,-100.,-100.,100.,100.,100.]
    plane={'uuid':'far','geometry_type':'Plane','analytic_properties':{'reals':[0.,0.,1.,-100.]},
        'bbox':[-100.,-100.,100.,100.,100.,100.]}
    volume=[{'uuid':'volume','backend_tag':10,'surface_uuids':['strip','far']}]
    plan=plan_analytic_material_probe(target,[target,plane],volume,1e-8,'mm',conical_supports=True)
    assert plan['status']=='ready',plan
    plus=plan['plus']['xyz']
    assert 1.+plus[2]*math.tan(alpha)<0
    assert plan['plus']['signed_surface_residual']>0>plan['minus']['signed_surface_residual']
    assert plan['epsilon']<=1./64


@pytest.mark.parametrize('bad_angle',[0.,.5e-6,math.pi/2,math.pi/2-1e-7,2*math.pi+.2,float('inf'),float('nan'),True])
def test_degenerate_or_periodically_aliased_cone_angles_are_unsupported(bad_angle):
    geometry=conical_scene();faces,volumes,curves=geometry
    faces[0]['analytic_properties']['reals'][7]=bad_angle
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm')
    assert not shape['eligible']
    assert analytic_unit_normal(faces[0],faces[0]['samples'][0]['xyz']) is None
    sdk,calls=conical_membership();rows=worker._conical_material_side_probes(sdk,*geometry,1e-8,'mm')
    assert calls==[] and rows[0]['status']=='indeterminate'


@pytest.mark.parametrize('mutant',['bad_unit','cm','full_span','missing_edge','disconnected','wrong_radius','axis_tilt','negative_ref',
    'outside_axial','opposite_quadrant','near_cap','near_ray','trim0','support_trim0','support_nontrap','support_outside',
    'bad_tangent','arc_length','arc_phase','missing_cap','wrong_cap_volume','tilted_cap','nonmanifold','apex','malformed'])
def test_unsupported_conical_trims_never_issue_queries(mutant):
    geometry=conical_scene();faces,volumes,curves=geometry;face=faces[0];unit='mm'
    if mutant=='bad_unit':unit='unknown'
    if mutant=='cm':unit='cm'
    if mutant=='full_span':face['parametric_bounds']['maximum'][0]=math.tau
    if mutant=='missing_edge':face['curve_loops'][0]['curve_tags'].pop()
    if mutant=='disconnected':curves[0]['endpoints'][0]['backend_tag']=9999
    if mutant=='wrong_radius':face['analytic_properties']['reals'][6]=4.
    if mutant=='axis_tilt':face['analytic_properties']['reals'][3]=1e-16
    if mutant=='negative_ref':face['analytic_properties']['reals'][6]=-1.
    if mutant=='outside_axial':face['samples'][0]['xyz']=[6.75*math.sqrt(.5),6.75*math.sqrt(.5),9.]
    if mutant=='opposite_quadrant':face['samples'][0]['xyz']=[-4.5*math.sqrt(.5),-4.5*math.sqrt(.5),6.]
    if mutant=='near_cap':face['samples'][0]['xyz']=[3*math.sqrt(.5),3*math.sqrt(.5),4.]
    if mutant=='near_ray':face['samples'][0]['xyz']=[4.5,0.,6.]
    if mutant=='trim0':face['samples'][0]['trim_count']=0
    if mutant=='support_trim0':faces[1]['samples'][0]['trim_count']=0
    if mutant=='support_nontrap':faces[1]['curve_loops'][0]['curve_tags'].pop()
    if mutant=='support_outside':faces[1]['samples'][0]['xyz']=[-100.,-100.,6.]
    if mutant=='bad_tangent':faces[1]['analytic_properties']['reals'][0]=.1
    if mutant=='arc_length':curves[0]['length']*=.5
    if mutant=='arc_phase':curves[0]['parametric_bounds']['maximum'][0]=math.pi/3
    if mutant=='missing_cap':curves[0]['adjacent_surface_uuids']=['strip']
    if mutant=='wrong_cap_volume':faces[-2]['orientation_by_volume'][0]['volume_uuid']='other'
    if mutant=='tilted_cap':faces[-2]['analytic_properties']['reals']=[1e-9,0.,1.,-4.]
    if mutant=='nonmanifold':next(c for c in curves if c['backend_tag']==400)['adjacent_surface_uuids'].append('cap-0')
    if mutant=='apex':face['analytic_properties']['reals'][6]=0.
    if mutant=='malformed':face['parametric_bounds']['minimum']=[]
    before=deepcopy(geometry)
    shape=conical_blend_shape(face,*geometry,1e-8,unit)
    assert not shape['eligible'],(mutant,shape)
    sdk,calls=conical_membership();rows=worker._conical_material_side_probes(sdk,*geometry,1e-8,unit)
    assert calls==[] and len(rows)==1 and rows[0]['status']=='indeterminate'
    assert geometry==before


def test_numerical_floor_rejects_uncertain_coordinates_without_queries():
    geometry=conical_scene();geometry[0][0]['bbox'][0]=1e15
    assert conical_blend_shape(geometry[0][0],*geometry,1e-8,'mm')['eligible']
    sdk,calls=conical_membership();rows=worker._conical_material_side_probes(sdk,*geometry,1e-8,'mm')
    assert calls==[] and all(row['status']=='indeterminate' for row in rows)


def test_reference_apex_neighborhood_is_not_offset_when_below_numeric_floor():
    geometry=conical_scene();face=geometry[0][0]
    face['analytic_properties']['reals']=[0.,0.,0.,0.,0.,1.,0.,math.atan(.75)]
    face['samples'][0]['xyz']=[.75e-8,0.,1e-8]
    plan=plan_analytic_material_probe(face,geometry[0],geometry[1],1e-8,'mm',conical_supports=True)
    assert plan['status']=='indeterminate' and plan['material_normal_sign'] is None


def test_cap_midpoints_may_remain_unverified_without_blocking_the_supported_strip():
    geometry=conical_scene(True)
    for cap in geometry[0][-2:]:cap['samples'][0]['trim_count']=0
    shape=conical_blend_shape(geometry[0][0],*geometry,1e-8,'mm');assert shape['eligible']
    sdk,calls=conical_membership(True);rows=worker._conical_material_side_probes(sdk,*geometry,1e-8,'mm')
    assert len(calls)==6 and all(row['status']=='observed' for row in rows)


@pytest.mark.parametrize('answer',[0,1,True,2,None,RuntimeError('query failed')])
def test_invalid_ambiguous_or_failed_native_answers_have_no_material_sign(answer):
    geometry=conical_scene();calls=[]
    def inside(*args,**kwargs):
        calls.append(args)
        if isinstance(answer,Exception):raise answer
        return answer
    rows=worker._conical_material_side_probes(SimpleNamespace(model=SimpleNamespace(isInside=inside)),*geometry,1e-8,'mm')
    assert len(rows)==3 and all(row['status']=='indeterminate' and row['material_normal_sign'] is None for row in rows)
    assert len(calls)==(6 if type(answer) is int and answer in (0,1) else 3)


@pytest.mark.parametrize('flag',[1,0,None,'true'])
def test_conical_flag_is_strict_bool_before_job_or_sdk(source,tmp_path,flag):
    with pytest.raises(backend.GmshBackendError):backend.GmshBackend().inspect_geometry(source,tmp_path/'jobs',probe_conical_blends=flag)
    assert not (tmp_path/'jobs').exists()
    with pytest.raises(worker.WorkerFailure) as error:worker.generate({'source_kind':'cad_geometry_inspection','probe_conical_blends':flag})
    assert error.value.code=='invalid_request'


@pytest.mark.parametrize('kind',[None,'cad','closed_tri_surface','structured_recipe'])
def test_noninspection_conical_flag_is_rejected_even_false(kind):
    with pytest.raises(worker.WorkerFailure) as error:worker.generate({'source_kind':kind,'probe_conical_blends':False})
    assert error.value.code=='unsupported_criteria'


def test_default_omits_conical_keys_and_explicit_true_retains_raw_only_policy(source,tmp_path,monkeypatch):
    _,events=fake_sdk(monkeypatch);requests=[]
    def run(self,request,*args):requests.append(deepcopy(request));return worker.generate(request)
    monkeypatch.setattr(backend.GmshBackend,'_run',run)
    old=backend.GmshBackend().inspect_geometry(source,tmp_path/'old')
    new=backend.GmshBackend().inspect_geometry(source,tmp_path/'new',probe_conical_blends=True)
    assert 'probe_conical_blends' not in requests[0] and requests[1]['probe_conical_blends'] is True
    assert 'conical_material_side_probes' not in old and 'conical_probe_policy' not in old
    assert new['conical_material_side_probes']==[] and new['conical_probe_policy']==CONICAL_PROBE_POLICY
    assert old['surfaces']==new['surfaces'] and old['curves']==new['curves']
    assert 'blend_material_side_probes' not in new and 'cylinder_material_side_probes' not in new
    assert all(event[0]!='volume_query' for event in events)



def test_conical_shared_support_has_one_plan_and_one_query_pair_per_job(monkeypatch):
    """Cache-only fake; conical geometry and membership are tested independently."""
    from caelab_prep.adapters import gmsh_geometry
    faces=[{'uuid':identity,'geometry_type':'Cone' if identity.startswith('cone') else 'Plane'}
           for identity in ('cone1','cone2','shared','plane1','plane2')]
    def shape(face,*args):return {'eligible':True,'support_surface_uuids':['shared','plane'+face['uuid'][-1]]}
    plans=[]
    def plan(face,*args,conical_supports=False):
        assert conical_supports is True;plans.append(face['uuid'])
        return {'surface_uuid':face['uuid'],'volume_uuid':'volume','status':'ready','reason':None,
            'normal_reference':'cone_radial_axial' if face['geometry_type']=='Cone' else 'plane_normal',
            'material_normal_sign':None,'plus':{'xyz':[1.,0.,0.],'inside_count':None},
            'minus':{'xyz':[-1.,0.,0.],'inside_count':None}}
    monkeypatch.setattr(gmsh_geometry,'conical_blend_shape',shape)
    monkeypatch.setattr(gmsh_geometry,'plan_analytic_material_probe',plan)
    calls=[]
    def inside(dim,tag,xyz,*,parametric):calls.append(list(xyz));return int(xyz[0]<0)
    rows=worker._conical_material_side_probes(SimpleNamespace(model=SimpleNamespace(isInside=inside)),
        faces,[{'uuid':'volume','backend_tag':10}],[],1e-8,'mm')
    assert len(rows)==len(plans)==5 and len(calls)==10 and plans.count('shared')==1


def test_raw_normal_volume_sign_and_u_phase_do_not_define_conical_material_side():
    geometry=conical_scene();changed=deepcopy(geometry)
    for face in changed[0]:
        face['samples'][0]['face_normal']=[-1e90,2e90,3e90]
        face['orientation_by_volume'][0]['sign']*=-1
    changed[0][0]['parametric_bounds']['minimum'][0]+=2.
    changed[0][0]['parametric_bounds']['maximum'][0]+=2.
    original_shape=conical_blend_shape(geometry[0][0],*geometry,1e-8,'mm')
    changed_shape=conical_blend_shape(changed[0][0],*changed,1e-8,'mm')
    assert original_shape==changed_shape
    sdk,_=conical_membership();original=worker._conical_material_side_probes(sdk,*geometry,1e-8,'mm')
    sdk,_=conical_membership();altered=worker._conical_material_side_probes(sdk,*changed,1e-8,'mm')
    assert original==altered


@pytest.mark.parametrize('axis_sign',[-1,1])
def test_reference_radius_zero_is_allowed_when_the_finite_strip_avoids_apex(axis_sign):
    geometry=conical_scene(axis_sign=axis_sign,origin_shift=-4.*axis_sign)
    assert geometry[0][0]['analytic_properties']['reals'][6]==0.
    shape=conical_blend_shape(geometry[0][0],*geometry,1e-8,'mm')
    assert shape['eligible'] and shape['radius']==pytest.approx(7.5)


def test_end_sections_use_world_axial_order_when_radius_decreases_with_world_axis():
    geometry=conical_scene();faces,volumes,curves=geometry
    for face in faces:
        low,high=face['bbox'][2],face['bbox'][5];face['bbox'][2],face['bbox'][5]=12.-high,12.-low
        face['samples'][0]['xyz'][2]=12.-face['samples'][0]['xyz'][2]
        values=face['analytic_properties']['reals']
        if face['geometry_type']=='Cone':values[2]=12.-values[2];values[5]*=-1
        else:values[3]+=12.*values[2];values[2]*=-1
    for curve in curves:
        for endpoint in curve['endpoints']:endpoint['xyz'][2]=12.-endpoint['xyz'][2]
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm');assert shape['eligible'],shape
    assert shape['axial_range']==[4.,8.]
    assert [section['radius'] for section in shape['end_sections']]==pytest.approx([6.,3.])
    assert [section['curvature_radius'] for section in shape['end_sections']]==pytest.approx([7.5,3.75])
    assert shape['curvature_radius_range']==pytest.approx([3.75,7.5]) and shape['radius']==pytest.approx(7.5)


@pytest.mark.parametrize('permutation',[(2,0,1),(1,2,0)])
def test_exact_basis_axes_share_the_same_shape_and_offset_math(permutation):
    geometry=conical_scene();faces,volumes,curves=geometry
    def permute(values):return [values[index] for index in permutation]
    for face in faces:
        face['bbox']=permute(face['bbox'][:3])+permute(face['bbox'][3:])
        face['samples'][0]['xyz']=permute(face['samples'][0]['xyz'])
        values=face['analytic_properties']['reals']
        if face['geometry_type']=='Cone':values[:6]=permute(values[:3])+permute(values[3:6])
        else:values[:3]=permute(values[:3])
    for curve in curves:
        for endpoint in curve['endpoints']:endpoint['xyz']=permute(endpoint['xyz'])
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm');assert shape['eligible'],shape
    assert shape['axis_index']==permutation.index(2) and shape['axial_range']==[4.,8.]
    for identity in ('strip',*shape['support_surface_uuids']):
        face=next(f for f in faces if f['uuid']==identity)
        assert plan_analytic_material_probe(face,faces,volumes,1e-8,'mm',conical_supports=True)['status']=='ready'



def test_generatrix_ray_drift_is_limited_in_length_units_at_large_radius():
    geometry=conical_scene();faces,volumes,curves=geometry;scale=1e8
    for face in faces:
        face['bbox']=[value*scale for value in face['bbox']]
        face['samples'][0]['xyz']=[value*scale for value in face['samples'][0]['xyz']]
        values=face['analytic_properties']['reals']
        if face['geometry_type']=='Cone':values[:3]=[value*scale for value in values[:3]];values[6]*=scale
        else:values[3]*=scale
    for curve in curves:
        curve['length']*=scale
        for endpoint in curve['endpoints']:endpoint['xyz']=[value*scale for value in endpoint['xyz']]
    drift=3e-8;point=[6.*scale*math.cos(drift),6.*scale*math.sin(drift),8.*scale]
    for curve in curves:
        for endpoint in curve['endpoints']:
            if endpoint['backend_tag']==1100:endpoint['xyz']=point[:]
        if curve['geometry_type']=='Line':curve['length']=math.dist(*(e['xyz'] for e in curve['endpoints']))
    shape=conical_blend_shape(faces[0],*geometry,1e-8,'mm')
    assert not shape['eligible'] and shape['reason']=='shared_line_not_conical_generatrix',shape
