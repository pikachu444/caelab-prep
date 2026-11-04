"""R4 finite-sample audit of unchanged original practical CAD and standard FE cells.

Uses validated native OCCT trimmed-boundary distance and explicit
.01/.05/.1 mm sensitivity. Does not claim industrial certification or Hausdorff proof.
"""
from pathlib import Path
import argparse,json,sys,time,hashlib,traceback
import numpy as np,gmsh,meshio
import audit_round3_v2 as prior
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from job_slots import heavy_job_slot

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def stats(a):
 a=np.asarray(a);return {'samples':len(a),'max_mm':float(np.max(a)) if len(a) else None,'p95_mm':float(np.quantile(a,.95)) if len(a) else None,'unresolved':int((~np.isfinite(a)).sum())}
def boundary_distance(p,surfs,prune=True):
 p=np.asarray(p).reshape(-1,3);best=np.full(len(p),np.inf);witness=np.full((len(p),2),-1,int)
 curves=sorted({abs(t) for d,t in gmsh.model.getBoundary([(2,s) for s in surfs],combined=False,oriented=False) if d==1})
 vertices=sorted({abs(t) for d,t in gmsh.model.getBoundary([(1,c) for c in curves],combined=False,oriented=False) if d==0})
 for v in vertices:
  dist=np.linalg.norm(p-np.asarray(gmsh.model.getValue(0,v,[])),axis=1);use=dist<best;best[use]=dist[use];witness[use]=[0,v]
 entities=[]
 for d,tags in [(2,surfs),(1,curves)]:
  for tag in tags:
   box=np.asarray(gmsh.model.getBoundingBox(d,tag));lo=np.maximum(np.maximum(box[:3]-p,p-box[3:]),0);lower=np.linalg.norm(lo,axis=1)
   entities.append((float(np.median(lower)) if len(lower) else 0,d,tag,lower))
 calls=0;query_points=0;skipped=[]
 for _,d,tag,lower in sorted(entities,key=lambda x:x[0]):
  ids=np.flatnonzero(lower<=best+1e-9) if prune else np.arange(len(p))
  if not len(ids):continue
  try:cp,uv=gmsh.model.getClosestPoint(d,tag,p[ids].reshape(-1));calls+=1;query_points+=len(ids)
  except Exception as e:
   if d!=1 or 'curve is null' not in str(e):raise
   box=np.asarray(gmsh.model.getBoundingBox(1,tag));ends=[abs(t) for dim,t in gmsh.model.getBoundary([(1,tag)],combined=False,oriented=False) if dim==0]
   if gmsh.model.occ.getMass(1,tag)>1e-9 or np.linalg.norm(box[3:]-box[:3])>1e-6 or not ends or not all(v in vertices for v in ends):raise
   skipped.append(tag);continue
  cp=np.asarray(cp).reshape(-1,3)
  if d==1:uv=gmsh.model.getParametrization(1,tag,cp.reshape(-1))
  uv=np.asarray(uv).reshape(-1,d);evaluated=np.asarray(gmsh.model.getValue(d,tag,uv.reshape(-1))).reshape(-1,3)
  if np.any(np.linalg.norm(evaluated-cp,axis=1)>1e-6):raise ValueError(f'CAD closest-point parameter validation failed on entity {d},{tag}')
  dist=np.linalg.norm(p[ids]-cp,axis=1)
  for j in np.flatnonzero(np.isfinite(dist)&(dist<best[ids])):
   if gmsh.model.isInside(d,tag,uv[j],parametric=True):best[ids[j]]=dist[j];witness[ids[j]]=[d,tag]
 return best,{'projection_calls':calls,'projected_points':query_points,'source_surface_count':len(surfs),'curve_count':len(curves),'vertex_count':len(vertices),'collapsed_edges_covered_by_vertices':skipped,'curve_parameter_fix':'Recompute inverse curve parameter from closestXYZ and verify getValue; Gmsh4.15.2 closest-curve param output observed uninitialized.', 'closest_entity_dimensions_counts':{str(d):int((witness[:,0]==d).sum()) for d in [-1,0,1,2]}}

def boundary_distance_native(points,cad):
 from engines.cad_tools.cached_boundary_distance import CADBoundaryDistance
 with CADBoundaryDistance(cad) as query:result=query.query(points)
 return result[:,0],{'method':'OCCT8 BRepExtrema_DistShapeShape to compound of original trimmed boundary faces','samples':len(result),'support_type_counts':{str(int(v)):int((result[:,4]==v).sum()) for v in np.unique(result[:,4])},'native_tolerance_mm':1e-9}

def corrected_cad(cad,points,faces,centroids,max_samples):
 from engines.cad_tools.cached_boundary_distance import CADBoundaryDistance
 from engines.cad_tools.cached_classifier import CADClassifier
 gmsh.initialize();gmsh.option.setNumber('General.Terminal',0);gmsh.option.setNumber('General.NumThreads',1);gmsh.option.setString('Geometry.OCCTargetUnit','MM')
 try:
  gmsh.model.occ.importShapes(str(cad));gmsh.model.occ.synchronize();vols=[t for d,t in gmsh.model.getEntities(3)];surfs=sorted({abs(t) for d,t in gmsh.model.getBoundary([(3,v) for v in vols],combined=True,oriented=False) if d==2});volume=sum(gmsh.model.occ.getMass(3,v) for v in vols)
 finally:gmsh.finalize()
 def sample(a):return a[np.linspace(0,len(a)-1,min(max_samples,len(a)),dtype=int)] if len(a) else a
 bi=np.array(sorted({n for f in faces for n in f}),int);ids=sample(bi);fi=sample(np.arange(len(faces)));fc=np.asarray([points[list(faces[i])].mean(axis=0) for i in fi]).reshape(-1,3);cs=sample(centroids)
 with CADClassifier(cad) as classifier:states=classifier.classify(cs)
 if np.any(states==-1):raise ValueError('Native cached classifier returned UNKNOWN')
 outside=states==0
 with CADBoundaryDistance(cad) as query:
  nr=query.query(points[ids]);fr=query.query(fc);ore=query.query(cs[outside])
 root=Path(__file__).resolve().parents[1]/'engines/cad_tools'
 dependency={name:sha(root/name) for name in ['cad_query.cpp','cad_query','cached_classifier.py','cad_boundary_query.cpp','cad_boundary_query','cached_boundary_distance.py']}
 return {'path':str(cad),'sha256':sha(cad),'unit':'mm per case metadata','solid_count':len(vols),'surface_count':len(surfs),'volume':volume,'boundary_nodes_to_trimmed_CAD':stats(nr[:,0]),'boundary_face_centroids_to_trimmed_CAD':stats(fr[:,0]),'cell_centroid_samples':len(cs),'cell_centroid_samples_outside':int(outside.sum()),'outside_centroid_distance_to_trimmed_CAD':stats(ore[:,0]),'distance_note':'Deterministic finite mesh-to-CAD samples. OCCT8 BRepExtrema_DistShapeShape against a compound of original trimmed boundary faces, including edge/vertex minima. Boundary compound excludes solid interiors as zero-distance targets. No Gmsh closest-point or inverseUV is used. No Hausdorff/global-coverage proof.','projection_performance':{'backend':'native_OCCT8_boundary','nodes':len(nr),'faces':len(fr),'outside':len(ore)},'native_dependencies_sha256':dependency,'native_boundary_tolerance_mm':1e-9,'cached_classifier':{'states':{str(v):int((states==v).sum()) for v in [-1,0,1,2]},'tolerance_mm':1e-7,'ON_policy':'ON included; outside means OUT only'}}

def audit(path,metadata,samples=1000):
 meta=json.loads(Path(metadata).read_text());m=meshio.read(path)
 if not np.isfinite(m.points).all():raise ValueError('Nonfinite input coordinates rejected before CAD projection')
 prior.base.cad_audit=corrected_cad
 old_lines=prior.lines_for;prior.lines_for=lambda case:meta.get('features',{}).get('thickness_probe_lines',[])
 try:r=prior.audit(path,metadata,samples)
 finally:prior.lines_for=old_lines
 boundary=max(r['cad']['boundary_nodes_to_trimmed_CAD']['max_mm'] or 0,r['cad']['boundary_face_centroids_to_trimmed_CAD']['max_mm'] or 0);outside=r['cad']['outside_centroid_distance_to_trimmed_CAD']['max_mm'] or 0
 r['audit_version']='4.3';r['criteria']['primary_CAD_distance_mm']=.01;r['criteria']['additional_sensitivity_mm']=[.05,.1];r['criteria']['unchanged_primary_Round3_thresholds']=True
 r['checks']['explicit_CAD_feature_probes_available']=bool(meta.get('features',{}).get('feature_probes'));r['mesh_policy_pass']=all(r['checks'].values());r['hex_dominant_policy_pass']=r['mesh_policy_pass'] and (r['volume_fractions']['signed_hex_volume_fraction'] or 0)>=.5
 r['feature_coverage_status']='sampled_explicit_probes_only' if r['checks']['explicit_CAD_feature_probes_available'] else 'unverified_no_probes_not_approved'
 r['sensitivity']={}
 for tol in [.01,.05,.1]:
  checks=dict(r['checks']);checks['sampled_boundary']=boundary<=tol;checks['sampled_outside_centroids']=outside<=tol
  r['sensitivity'][str(tol)]={'checks':checks,'mesh_policy_pass':all(checks.values()),'hex_dominant_policy_pass':all(checks.values()) and (r['volume_fractions']['signed_hex_volume_fraction'] or 0)>=.5}
 r['feature_coverage_statement']='No global small-feature preservation claim. Only explicitly listed probes/normal chords and sampled CAD distances are tested.'
 r['feature_probe_count']=len(meta.get('features',{}).get('feature_probes',[]));r['case_units_note']=meta.get('unit_note');r['authoritative_original_cad']=meta.get('step');r['audit_round4_source_sha256']=sha(__file__)
 return r

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('mesh');ap.add_argument('--metadata',required=True);ap.add_argument('--output',required=True);ap.add_argument('--samples',type=int,default=1000);ap.add_argument('--no-slot',action='store_true');a=ap.parse_args()
 try:
  if a.no_slot:r=audit(a.mesh,a.metadata,a.samples)
  else:
   with heavy_job_slot('audit:'+Path(a.mesh).parent.name):r=audit(a.mesh,a.metadata,a.samples)
 except Exception as e:r={'status':'audit_failed','mesh':a.mesh,'error':str(e),'traceback':traceback.format_exc()}
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k) for k in ['case_id','elements','volume_fractions','checks','mesh_policy_pass','sensitivity','error']},indent=2));sys.exit(0 if r.get('mesh_policy_pass') else 2)
