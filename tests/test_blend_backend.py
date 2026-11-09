"""Pure/fake GI3 quarter-cylinder evidence; no native SDK or G1 qualification."""
from copy import deepcopy
import json
import math
from types import SimpleNamespace

import pytest

from caelab_prep.adapters import gmsh_backend as backend, gmsh_worker as worker
from caelab_prep.adapters.gmsh_geometry import (
    BLEND_PROBE_POLICY, analytic_signed_residual, cylindrical_blend_shape,
    plan_analytic_material_probe,
)
from test_geometry_inspection import source, fake_sdk


def blend_scene(*, cusp=False, axis_sign=1, plane_scale=1.):
    """Small independent analytic extrusion, with actual shared vertex identities."""
    xy = [(1.,0.), (0.,1.), (1.,1.)] if cusp else [(0.,1.), (1.,0.), (12.,0.), (12.,8.), (0.,8.)]
    origin = [0.,0.,0.] if cusp else [1.,1.,0.]
    volume = "volume"
    points = {(level,index): {"backend_tag": 1000+level*100+index,
              "xyz": [*point,3.*level]} for level in (0,1) for index,point in enumerate(xy)}
    curves=[]
    def curve(tag, kind, ends, length):
        row={"backend_tag":tag,"geometry_type":kind,"endpoints":[deepcopy(points[end]) for end in ends],
             "length":length,"parametric_bounds":{"minimum":[0.],"maximum":[math.pi/2 if kind=="Circle" else length]},
             "adjacent_surface_uuids":[]}
        curves.append(row)
        return tag
    bottom=[];top=[]
    for level,tags in ((0,bottom),(1,top)):
        for index in range(len(xy)):
            other=(index+1)%len(xy)
            tags.append(curve(200+level*100+index,"Circle" if index==0 else "Line",
                         [(level,index),(level,other)],math.pi/2 if index==0 else math.dist(xy[index],xy[other])))
    vertical=[curve(400+index,"Line",[(0,index),(1,index)],3.) for index in range(len(xy))]
    def bbox(vertices):
        return [min(point[i] for point in vertices) for i in range(3)]+[max(point[i] for point in vertices) for i in range(3)]
    def face(identity, kind, reals, tags, vertices, sample):
        row={"uuid":identity,"geometry_type":kind,"analytic_properties":{"reals":reals},
            "bbox":bbox(vertices),"samples":[{"xyz":sample,"trim_count":1,"face_normal":[99.,98.,97.]}],
            "orientation_by_volume":[{"volume_uuid":volume,"sign":-1}],
            "curve_loops":[{"backend_tag":1,"curve_tags":tags}],
            "parametric_bounds":{"minimum":[0.,0. if axis_sign==1 else -3.],
                                 "maximum":[math.pi/2,3. if axis_sign==1 else 0.]}}
        for tag in tags:next(curve for curve in curves if curve["backend_tag"]==abs(tag))["adjacent_surface_uuids"].append(identity)
        return row
    radial=-math.sqrt(.5) if not cusp else math.sqrt(.5)
    surfaces=[face("strip","Cylinder",[*origin,0.,0.,float(axis_sign),1.],
        [bottom[0],vertical[1],-top[0],-vertical[0]],
        [[0.,0.,0.],[1.,1.,3.]], [origin[0]+radial,origin[1]+radial,1.5])]
    for index in range(1,len(xy)):
        other=(index+1)%len(xy);a,b=xy[index],xy[other]
        axis=0 if a[0]==b[0] else 1;coordinate=a[axis]
        coefficients=[0.,0.,0.,-plane_scale*coordinate];coefficients[axis]=plane_scale
        vertices=[points[level,j]["xyz"] for level in (0,1) for j in (index,other)]
        sample=[sum(v[i] for v in vertices)/4 for i in range(3)]
        surfaces.append(face("plane-"+str(index),"Plane",coefficients,
            [bottom[index],vertical[other],-top[index],-vertical[index]],vertices,sample))
    for level,tags in ((0,bottom),(1,top)):
        vertices=[points[level,i]["xyz"] for i in range(len(xy))]
        sample=[sum(v[i] for v in vertices)/len(vertices) for i in range(3)]
        surfaces.append(face("cap-"+str(level),"Plane",[0.,0.,1.,-3.*level],tags,vertices,sample))
    volumes=[{"uuid":volume,"backend_tag":10,"surface_uuids":[f["uuid"] for f in surfaces]}]
    return surfaces,volumes,curves


def membership(*, cusp=False):
    calls=[]
    def inside(dim,tag,xyz,*,parametric):
        assert dim==3 and tag==10 and parametric is False
        calls.append(list(xyz));x,y,z=xyz
        if cusp:
            return int(0<=x<=1 and 0<=y<=1 and 0<=z<=3 and math.hypot(x,y)>=1)
        return int(0<=x<=12 and 0<=y<=8 and 0<=z<=3 and
                   (x>=1 or y>=1 or math.hypot(x-1,y-1)<=1))
    sdk=SimpleNamespace(model=SimpleNamespace(isInside=inside,
        mesh=SimpleNamespace(generate=lambda *args:pytest.fail("Mesh generation forbidden"))))
    return sdk,calls


@pytest.mark.parametrize("cusp",[False,True])
def test_both_independent_shapes_are_eligible_but_material_signs_differ(cusp):
    geometry=blend_scene(cusp=cusp);surfaces,volumes,curves=geometry;before=deepcopy(geometry)
    shape=cylindrical_blend_shape(surfaces[0],*geometry,1e-8,"mm")
    assert shape["eligible"] and shape["reason"] is None
    assert shape["radius"]==1. and shape["axial_range"]==[0.,3.]
    assert len(shape["support_surface_uuids"])==len(shape["shared_line_tags"])==2
    sdk,calls=membership(cusp=cusp)
    rows=worker._blend_material_side_probes(sdk,*geometry,1e-8,"mm")
    assert len(rows)==3 and len(calls)==6
    by_id={row["surface_uuid"]:row for row in rows}
    assert all(row["status"]=="observed" and row["reason"] is None for row in rows)
    assert by_id["strip"]["normal_reference"]=="cylinder_radial"
    assert by_id["strip"]["material_normal_sign"]==(-1 if cusp else 1)
    assert all(by_id[identity]["normal_reference"]=="plane_normal" and
               by_id[identity]["material_normal_sign"]==(1 if cusp else -1)
               for identity in shape["support_surface_uuids"])
    assert all(row["plus"]["inside_count"]!=row["minus"]["inside_count"] for row in rows)
    assert geometry==before
    json.dumps(rows,allow_nan=False)


@pytest.mark.parametrize("mutant",["full_cylinder","nonrect","disconnected","unsupported","unknown_unit",
    "cm","tilted_axis","parallel_supports","arc_length","arc_ends","axial_range","nonmanifold",
    "off_surface","trim0","support_trim0","support_sample_outside","too_large_u","large_arc_parameters","bad_tolerance"])
def test_unsupported_strip_shapes_are_indeterminate_without_queries(mutant):
    geometry=blend_scene();surfaces,volumes,curves=geometry;unit="mm";kwargs={}
    if mutant=="full_cylinder":surfaces[0]["parametric_bounds"]["maximum"][0]=math.tau
    if mutant=="nonrect":surfaces[1]["curve_loops"][0]["curve_tags"].pop()
    if mutant=="disconnected":curves[0]["endpoints"][0]["backend_tag"]=99999
    if mutant=="unsupported":surfaces[1]["geometry_type"]="Cone"
    if mutant=="unknown_unit":unit="unknown"
    if mutant=="cm":unit="cm"
    if mutant=="tilted_axis":surfaces[0]["analytic_properties"]["reals"][3]=1e-16
    if mutant=="parallel_supports":
        surfaces[1]["analytic_properties"]["reals"]=[1.,0.,0.,0.]
    if mutant=="arc_length":curves[0]["length"]*=.5
    if mutant=="arc_ends":curves[0]["endpoints"][1]=deepcopy(curves[1]["endpoints"][1])
    if mutant=="axial_range":curves[-1]["endpoints"][1]["xyz"][2]=2.
    if mutant=="nonmanifold":next(c for c in curves if c["backend_tag"]==400)["adjacent_surface_uuids"].append("cap-0")
    if mutant=="off_surface":surfaces[0]["samples"][0]["xyz"][0]=-.5
    if mutant=="trim0":surfaces[0]["samples"][0]["trim_count"]=0
    if mutant=="support_trim0":surfaces[1]["samples"][0]["trim_count"]=0
    if mutant=="support_sample_outside":surfaces[1]["samples"][0]["xyz"][0]=20.
    if mutant=="too_large_u":surfaces[0]["parametric_bounds"]={"minimum":[1e16,0.],"maximum":[1e16+2,3.]}
    if mutant=="large_arc_parameters":curves[0]["parametric_bounds"]={"minimum":[1e9],"maximum":[1e9+math.pi/2]}
    if mutant=="bad_tolerance":kwargs["length_tolerance"]=True
    shape=cylindrical_blend_shape(surfaces[0],*geometry,1e-8,unit,**kwargs)
    assert not shape["eligible"] and shape["reason"]
    if mutant!="bad_tolerance":
        sdk,calls=membership();rows=worker._blend_material_side_probes(sdk,*geometry,1e-8,unit)
        assert calls==[] and len(rows)==1 and rows[0]["status"]=="indeterminate"


def test_generic_plane_uses_normalized_coefficients_and_preserves_raw_values():
    geometry=blend_scene(cusp=True,plane_scale=2.);surfaces,volumes,curves=geometry
    before=deepcopy(geometry)
    for plane in surfaces[1:3]:
        plan=plan_analytic_material_probe(plane,surfaces,volumes,1e-8,"mm")
        assert plan["status"]=="ready" and plan["normal_reference"]=="plane_normal"
        for side in ("plus","minus"):
            assert plan[side]["signed_surface_residual"]==analytic_signed_residual(plane,plan[side]["xyz"])
        assert plan["plus"]["signed_surface_residual"]>0>plan["minus"]["signed_surface_residual"]
    assert geometry==before


@pytest.mark.parametrize("mutant",["near_boundary","big_coords","off_plane","bad_unit","unsupported_neighbor"])
def test_generic_safety_failures_never_query_the_affected_surface(mutant):
    geometry=blend_scene();surfaces,volumes,curves=geometry;face=surfaces[0];unit="mm"
    if mutant=="near_boundary":face["samples"][0]["xyz"]=[0.,1.,1.5]
    if mutant=="big_coords":surfaces[1]["bbox"][0]=1e15
    if mutant=="off_plane":face=surfaces[1];face["samples"][0]["xyz"][1]=.1
    if mutant=="bad_unit":unit="unknown"
    if mutant=="unsupported_neighbor":surfaces[-1]["geometry_type"]="Torus"
    plan=plan_analytic_material_probe(face,surfaces,volumes,1e-8,unit)
    assert plan["status"]=="indeterminate" and plan["reason"]
    assert plan["material_normal_sign"] is None


def test_axis_flip_raw_normal_and_volume_sign_do_not_change_shape_or_material_probes():
    original=blend_scene();flipped=blend_scene(axis_sign=-1)
    for face in flipped[0]:
        face["orientation_by_volume"][0]["sign"]*=-1
        face["samples"][0]["face_normal"]=[-1e99,2e99,3e99]
    shape1=cylindrical_blend_shape(original[0][0],*original,1e-8,"mm")
    shape2=cylindrical_blend_shape(flipped[0][0],*flipped,1e-8,"mm")
    assert shape1==shape2
    sdk,_=membership();first=worker._blend_material_side_probes(sdk,*original,1e-8,"mm")
    sdk,_=membership();second=worker._blend_material_side_probes(sdk,*flipped,1e-8,"mm")
    assert first==second


@pytest.mark.parametrize("answer",[0,1,None,2,True,RuntimeError("query failed")])
def test_ambiguous_invalid_and_failed_queries_are_unqualified(answer):
    geometry=blend_scene();calls=[]
    def inside(*args,**kwargs):
        calls.append(args)
        if isinstance(answer,Exception):raise answer
        return answer
    rows=worker._blend_material_side_probes(SimpleNamespace(model=SimpleNamespace(isInside=inside)),*geometry,1e-8,"mm")
    assert len(rows)==3 and all(row["status"]=="indeterminate" and row["material_normal_sign"] is None for row in rows)
    assert len(calls)==(6 if type(answer) is int and answer in (0,1) else 3)


@pytest.mark.parametrize("flag",[1,0,None,"true"])
def test_blend_boolean_validation_rejects_before_any_sdk_or_job(source,tmp_path,flag):
    with pytest.raises(backend.GmshBackendError):
        backend.GmshBackend().inspect_geometry(source,tmp_path/"jobs",probe_cylindrical_blends=flag)
    assert not (tmp_path/"jobs").exists()
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind":"cad_geometry_inspection","probe_cylindrical_blends":flag})
    assert error.value.code=="invalid_request"


@pytest.mark.parametrize("kind",[None,"cad","closed_tri_surface","structured_recipe"])
def test_blend_flag_is_explicitly_unsupported_even_false_outside_inspection(kind):
    with pytest.raises(worker.WorkerFailure) as error:
        worker.generate({"source_kind":kind,"probe_cylindrical_blends":False})
    assert error.value.code=="unsupported_criteria"


def test_inspection_default_omits_flag_policy_and_evidence_and_opt_in_records_policy(source,tmp_path,monkeypatch):
    _,events=fake_sdk(monkeypatch);requests=[]
    def run(self,request,*args):
        requests.append(deepcopy(request))
        return worker.generate(request)
    monkeypatch.setattr(backend.GmshBackend,"_run",run)
    old=backend.GmshBackend().inspect_geometry(source,tmp_path/"default")
    new=backend.GmshBackend().inspect_geometry(source,tmp_path/"opted",probe_cylindrical_blends=True)
    old_request,new_request=requests
    assert "probe_cylindrical_blends" not in old_request and new_request["probe_cylindrical_blends"] is True
    assert "blend_material_side_probes" not in old and "blend_probe_policy" not in old
    assert new["blend_probe_policy"]==BLEND_PROBE_POLICY
    assert new["blend_material_side_probes"][0]["status"]=="indeterminate"
    assert old["surfaces"]==new["surfaces"] and old["curves"]==new["curves"]
    assert "cylinder_material_side_probes" not in new
    assert all(event[0]!="volume_query" for event in events)


def test_shared_support_queries_are_cached_once_per_job(monkeypatch):
    """Cache-only fake: shape and plan validation are exercised separately above."""
    from caelab_prep.adapters import gmsh_geometry
    faces=[{"uuid":identity,"geometry_type":"Cylinder" if identity.startswith("strip") else "Plane"}
           for identity in ("strip1","strip2","shared","support1","support2")]
    def shape(face,*args):
        return {"eligible":True,"support_surface_uuids":["shared","support"+face["uuid"][-1]]}
    plans=[]
    def plan(face,*args):
        plans.append(face["uuid"])
        return {"surface_uuid":face["uuid"],"volume_uuid":"volume","status":"ready","reason":None,
            "normal_reference":"plane_normal" if face["geometry_type"]=="Plane" else "cylinder_radial",
            "material_normal_sign":None,"plus":{"xyz":[1.,0.,0.],"inside_count":None},
            "minus":{"xyz":[-1.,0.,0.],"inside_count":None}}
    monkeypatch.setattr(gmsh_geometry,"cylindrical_blend_shape",shape)
    monkeypatch.setattr(gmsh_geometry,"plan_analytic_material_probe",plan)
    calls=[]
    def inside(dim,tag,xyz,*,parametric):
        calls.append(list(xyz));return int(xyz[0]<0)
    rows=worker._blend_material_side_probes(SimpleNamespace(model=SimpleNamespace(isInside=inside)),
        faces,[{"uuid":"volume","backend_tag":10}],[],1e-8,"mm")
    assert len(rows)==len(plans)==5 and len(calls)==10
    assert plans.count("shared")==1 and all(row["status"]=="observed" for row in rows)


@pytest.mark.parametrize("sample_kind",["outside_axial","opposite_quadrant"])
def test_original_critic_outside_strip_samples_are_rejected_before_queries(sample_kind):
    geometry=blend_scene();surfaces,volumes,curves=geometry
    sample=surfaces[0]["samples"][0]["xyz"]
    if sample_kind=="outside_axial":sample[2]=4.5
    else:sample[:2]=[1+math.sqrt(.5),1+math.sqrt(.5)]
    before=deepcopy(geometry)
    shape=cylindrical_blend_shape(surfaces[0],*geometry,1e-8,"mm")
    assert not shape["eligible"] and shape["reason"]=="strip_sample_outside_patch"
    sdk,calls=membership();rows=worker._blend_material_side_probes(sdk,*geometry,1e-8,"mm")
    assert calls==[] and len(rows)==1 and rows[0]["status"]=="indeterminate"
    assert rows[0]["reason"]=="strip_sample_outside_patch" and geometry==before


@pytest.mark.parametrize("cusp",[False,True])
@pytest.mark.parametrize("axis_sign",[-1,1])
@pytest.mark.parametrize("boundary",["cap_low","cap_high","near_cap_low","near_cap_high","ray0","ray1","near_ray0"])
def test_finite_strip_cap_and_ray_margins_reject_before_queries(cusp,axis_sign,boundary):
    geometry=blend_scene(cusp=cusp,axis_sign=axis_sign);surfaces,volumes,curves=geometry
    face=surfaces[0];point=face["samples"][0]["xyz"]
    if boundary=="cap_low":point[2]=0.
    if boundary=="cap_high":point[2]=3.
    if boundary=="near_cap_low":point[2]=.5e-6
    if boundary=="near_cap_high":point[2]=3.-.5e-6
    if boundary.startswith("ray"):
        tag=400+int(boundary[-1])
        point[:2]=next(c for c in curves if c["backend_tag"]==tag)["endpoints"][0]["xyz"][:2]
    if boundary=="near_ray0":
        origin=face["analytic_properties"]["reals"][:2]
        a=next(c for c in curves if c["backend_tag"]==400)["endpoints"][0]["xyz"][:2]
        b=next(c for c in curves if c["backend_tag"]==401)["endpoints"][0]["xyz"][:2]
        point[:2]=[origin[i]+(a[i]-origin[i])*math.cos(.5e-6)+(b[i]-origin[i])*math.sin(.5e-6) for i in range(2)]
    before=deepcopy(geometry)
    shape=cylindrical_blend_shape(face,*geometry,1e-8,"mm")
    assert not shape["eligible"] and shape["reason"]=="strip_sample_outside_patch"
    sdk,calls=membership(cusp=cusp)
    rows=worker._blend_material_side_probes(sdk,*geometry,1e-8,"mm")
    assert calls==[] and len(rows)==1 and rows[0]["status"]=="indeterminate"
    assert geometry==before
