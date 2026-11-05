"""Execute and measure two fixed synthetic CAD fixtures with the existing backend."""
from pathlib import Path
import importlib.metadata as md
import json, math, resource, time, hashlib, traceback
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from paired_offset import Pair, Rejected, extract, write_candidate, brep_bytes, digest, topology, TOL

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
OUT.mkdir(exist_ok=True)


def plate():
    shape=cq.Workplane('XY').box(40,25,2,centered=(False,False,False)).val()
    faces=shape.Faces()
    a=next(i for i,f in enumerate(faces) if abs(f.Center().z)<TOL and f.normalAt().z < -.9)
    b=next(i for i,f in enumerate(faces) if abs(f.Center().z-2)<TOL and f.normalAt().z > .9)
    return shape,[Pair(a,b)]


def bend():
    # 40 mm horizontal arm, 28 mm vertical arm, quarter-circle r=10..12,
    # constant 2 mm radial/planar thickness and 25 mm extrusion width.
    shape=(cq.Workplane('XZ').moveTo(0,0).lineTo(40,0)
       .threePointArc((40+12/math.sqrt(2),12-12/math.sqrt(2)),(52,12))
       .lineTo(52,40).lineTo(50,40).lineTo(50,12)
       .threePointArc((40+10/math.sqrt(2),12-10/math.sqrt(2)),(40,2))
       .lineTo(0,2).close().extrude(25).val())
    return shape,[Pair(0,6),Pair(1,5),Pair(2,4)]


def point_distance(point,face):
    return cq.Vertex.makeVertex(*point).distance(face)


def samples(face):
    u0,u1,v0,v1=BRepTools.UVBounds_s(face.wrapped)
    surface=BRepAdaptor_Surface(face.wrapped)
    return [cq.Vector(surface.Value(u0+(u1-u0)*u,v0+(v1-v0)*v))
            for u in (0,.25,.5,.75,1) for v in (0,.25,.5,.75,1)]


def segment_distance(p,a,b):
    p,a,b=cq.Vector(p),cq.Vector(a),cq.Vector(b)
    d=b-a;t=max(0,min(1,(p-a).dot(d)/d.dot(d)))
    return (p-(a+d*t)).Length


def boundary_distance(p,kind,fraction):
    x,y,z=p.toTuple()
    if kind=='plate':
        height=2*fraction
        points=[(0,0,height),(40,0,height),(40,25,height),(0,25,height)]
        return min(segment_distance(p,a,b) for a,b in zip(points,points[1:]+points[:1]))
    radius=12-2*fraction
    hx,hz=40,12-radius
    vx,vz=40+radius,40
    values=[segment_distance(p,(0,-25,hz),(0,0,hz)),segment_distance(p,(vx,-25,vz),(vx,0,vz))]
    angle=max(-math.pi/2,min(0,math.atan2(z-12,x-40)))
    for yy in (-25,0):
        values += [segment_distance(p,(0,yy,hz),(40,yy,hz)),
                   segment_distance(p,(vx,yy,12),(vx,yy,40)),
                   (p-cq.Vector(40+radius*math.cos(angle),yy,12+radius*math.sin(angle))).Length]
    return min(values)


def measure(source,pairs,candidate,kind,fraction):
    faces=source.Faces()
    expected_area=1000 if kind=='plate' else 25*(40+28+math.pi/2*(12-2*fraction))
    expected_bbox=(0,0,2*fraction,40,25,2*fraction) if kind=='plate' else (0,-25,2*fraction,52-2*fraction,0,40)
    bb=candidate.BoundingBox()
    bounds=(bb.xmin,bb.ymin,bb.zmin,bb.xmax,bb.ymax,bb.zmax)
    errors={'area_error_mm2':abs(candidate.Area()-expected_area),
            'bbox_max_error_mm':max(abs(a-b) for a,b in zip(bounds,expected_bbox)),
            'thickness_ray_outer_max_error_mm':0.,'thickness_ray_inner_max_error_mm':0.,
            'outer_normal_max_one_minus_dot':0.,'boundary_max_error_mm':0.,
            'shared_edge_surface_max_error_mm':0.,'seam_tangency_max_one_minus_dot':0.}
    count=0
    for face in candidate.Faces():
        pair=next(pair for pair in pairs if faces[pair.outer].geomType()==face.geomType()
                  and (face.geomType()=='CYLINDER' or faces[pair.outer].normalAt().dot(face.normalAt())>1-1e-8))
        outer,inner=faces[pair.outer],faces[pair.inner]
        for point in samples(face):
            normal=face.normalAt(point);count+=1
            outer_point=point+normal*(2*fraction)
            inner_point=point-normal*(2*(1-fraction))
            errors['thickness_ray_outer_max_error_mm']=max(errors['thickness_ray_outer_max_error_mm'],point_distance(outer_point,outer))
            errors['thickness_ray_inner_max_error_mm']=max(errors['thickness_ray_inner_max_error_mm'],point_distance(inner_point,inner))
            errors['outer_normal_max_one_minus_dot']=max(errors['outer_normal_max_one_minus_dot'],abs(1-normal.dot(outer.normalAt(outer_point))))
    topo,edges=topology(candidate)
    for edge,owners in edges:
        for fraction_along in (0,.25,.5,.75,1):
            point=edge.positionAt(fraction_along)
            if len(owners)==1:
                errors['boundary_max_error_mm']=max(errors['boundary_max_error_mm'],boundary_distance(point,kind,fraction))
            if len(owners)==2:
                adjacent=[candidate.Faces()[i] for i in sorted(owners)]
                for face in adjacent:
                    errors['shared_edge_surface_max_error_mm']=max(errors['shared_edge_surface_max_error_mm'],point_distance(point,face))
                errors['seam_tangency_max_one_minus_dot']=max(errors['seam_tangency_max_one_minus_dot'],abs(1-adjacent[0].normalAt(point).dot(adjacent[1].normalAt(point))))
    assert topo['faces']==(1 if kind=='plate' else 3)
    assert topo['shared_edges']==(0 if kind=='plate' else 2)
    assert topo['free_edges']==(4 if kind=='plate' else 8)
    assert all(abs(length-25)<TOL for length in topo['seam_lengths_mm'])
    assert all(value< (1e-8 if 'dot' in key else TOL) for key,value in errors.items()),errors
    assert abs(source.Volume() - (2000 if kind=='plate' else 2*25*(40+28+math.pi/2*11)))<TOL
    return {'analytic_area_mm2':expected_area,'area_mm2':candidate.Area(),'bbox_mm':bounds,
            'source_volume_mm3':source.Volume(),'surface_samples_including_boundaries':count,
            'errors':errors,'topology':topo}


report={'scope':'F1 bounded synthetic-fixture feasibility only; no automatic pairing, no Prep UI/Undo/native integration, no F2 qualification.',
 'versions':{'cadquery-ocp':md.version('cadquery-ocp'),'cadquery':md.version('cadquery')},
 'fixed_recipe':{'kernel':'OCCT7.8.1','offset':'PerformByJoin','join':'GeomAbs_Intersection','Intersection':False,'SelfInter':False,
                 'tolerance_mm':TOL,'normal_tolerance_one_minus_dot':1e-8,'units':'mm'},
 'budget':{'per_process_timeout_seconds':120,'measured_peak_rss_limit_MiB':2048,'algorithm_recipe_search':'one fixed join recipe; initial sharp-junction probe retained, no tuning loop'},
 'positive':{},'safe_rejections':[]}
start=time.monotonic()
try:
    for name,fixture in [('plate',plate),('rounded_L',bend)]:
        source,pairs=fixture()
        directory=OUT/name;directory.mkdir(exist_ok=True)
        raw=brep_bytes(source);(directory/'source.brep').write_bytes(raw)
        face_manifest=[{'index':i,'kind':face.geomType(),'center_mm':face.Center().toTuple(),
                        'outward_normal_at_uv_mid':face.normalAt().toTuple(),'area_mm2':face.Area()} for i,face in enumerate(source.Faces())]
        (directory/'explicit-face-selection.json').write_text(json.dumps({'unit':'mm','thickness_mm':2,
            'pairs':[dict(outer=p.outer,inner=p.inner) for p in pairs],'faces':face_manifest},indent=2))
        tick=time.monotonic()
        candidate,evidence=write_candidate(source,pairs,directory/'candidate.brep',thickness_mm=2)
        evidence['measurements']=measure(source,pairs,candidate,'plate' if name=='plate' else 'bend',.5)
        evidence['seconds']=time.monotonic()-tick
        assert brep_bytes(source)==raw
        assert digest(cq.Shape.importBrep(str(directory/'source.brep')))==hashlib.sha256(raw).hexdigest()
        reopened=cq.Shape.importBrep(str(directory/'candidate.brep'))
        evidence['reopened_measurements']=measure(source,pairs,reopened,'plate' if name=='plate' else 'bend',.5)
        evidence['source_file_sha256']=hashlib.sha256((directory/'source.brep').read_bytes()).hexdigest()
        evidence['output_file_sha256']=hashlib.sha256((directory/'candidate.brep').read_bytes()).hexdigest()
        report['positive'][name]=evidence
    # An explicit reference offset is tested as a different physical role, not
    # misreported as a midsurface. Same plate, same fixed kernel settings.
    source,pairs=plate();candidate,evidence=write_candidate(source,pairs,OUT/'plate'/'quarter-reference.brep',thickness_mm=2,fraction=.25)
    evidence['measurements']=measure(source,pairs,candidate,'plate',.25)
    report['reference_offset_contract']=evidence
    wedge=cq.Workplane('XZ').polyline([(0,0),(40,0),(40,4),(0,2)]).close().extrude(25).val()
    sharp=cq.Workplane('XZ').polyline([(0,0),(42,0),(42,32),(40,32),(40,2),(0,2)]).close().extrude(25).val()
    plate_shape,plate_pairs=plate();bend_shape,bend_pairs=bend()
    cases=[('variable_thickness_wedge',wedge,[Pair(0,2)],dict(thickness_mm=2)),
           ('sharp_junction_not_uniform_ray_thickness',sharp,[Pair(0,4),Pair(1,3)],dict(thickness_mm=2)),
           ('wrong_declared_thickness',plate_shape,plate_pairs,dict(thickness_mm=3)),
           ('missing_explicit_bend_pair',bend_shape,[bend_pairs[0],bend_pairs[2]],dict(thickness_mm=2)),
           ('offset_outside_wall',plate_shape,plate_pairs,dict(thickness_mm=2,fraction=1.1)),
           ('unresolved_units',plate_shape,plate_pairs,dict(thickness_mm=2,units='unknown'))]
    for name,source,pairs,options in cases:
        before=brep_bytes(source);target=OUT/'refusal-keeps-existing-candidate.brep'
        baseline=(OUT/'plate'/'candidate.brep').read_bytes();target.write_bytes(baseline)
        try:write_candidate(source,pairs,target,**options)
        except Rejected as error:
            assert brep_bytes(source)==before and target.read_bytes()==baseline
            report['safe_rejections'].append({'case':name,'reason':str(error),'source_unchanged':True,'previous_output_unchanged':True,
                'source_sha256':hashlib.sha256(before).hexdigest()})
        else:raise AssertionError('Invalid fixture accepted: '+name)
    report['status']='passed_bounded_recipe_only'
except BaseException:
    report['status']='failed';report['error']=traceback.format_exc()
report['seconds_total_including_imported_backend_work']=time.monotonic()-start
report['peak_rss_MiB']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
if report['peak_rss_MiB']>2048:report['status']='memory_budget_failed'
(OUT/'result.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('positive','reference_offset_contract')},indent=2))
raise SystemExit(0 if report['status']=='passed_bounded_recipe_only' else 1)
