"""Independent CAD/mesh acceptance additions for thin-feature and hex-dominance evaluation.

Measurements distinguish volume fractions from cell counts, surface topology from
CAD coverage, and line cell intersections from true element-layer counts.
"""
from pathlib import Path
from collections import Counter
import argparse,json,hashlib,time,traceback,itertools,sys
import numpy as np,meshio
import base_audit as base

def vtk_grid(mesh):
 import vtk
 from vtk.util.numpy_support import numpy_to_vtk
 p=vtk.vtkPoints();p.SetData(numpy_to_vtk(np.ascontiguousarray(mesh.points[:,:3]),deep=1));g=vtk.vtkUnstructuredGrid();g.SetPoints(p)
 types={'tetra':vtk.VTK_TETRA,'hexahedron':vtk.VTK_HEXAHEDRON,'wedge':vtk.VTK_WEDGE,'pyramid':vtk.VTK_PYRAMID}
 for block in mesh.cells:
  if block.type in types:
   for conn in block.data:
    ids=vtk.vtkIdList()
    for n in conn:ids.InsertNextId(int(n))
    g.InsertNextCell(types[block.type],ids)
 loc=vtk.vtkStaticCellLocator();loc.SetDataSet(g);loc.BuildLocator();return g,loc

def external_faces(mesh):
 faces=[];owner=[]
 for b in mesh.cells:
  if b.type not in base.FACES:continue
  for conn in b.data:
   for f in base.FACES[b.type]:faces.append(tuple(int(conn[i]) for i in f));owner.append(b.type)
 keys=[tuple(sorted(f)) for f in faces];c=Counter(keys)
 idx=[i for i,k in enumerate(keys) if c[k]==1]
 return [faces[i] for i in idx],[owner[i] for i in idx]

def surface_topology(faces):
 tri={tuple(sorted(f)) for f in faces if len(f)==3};mismatch=[]
 for q in (f for f in faces if len(f)==4):
  for a,b in [((q[0],q[1],q[2]),(q[0],q[2],q[3])),((q[0],q[1],q[3]),(q[1],q[2],q[3]))]:
   if tuple(sorted(a)) in tri and tuple(sorted(b)) in tri:mismatch.append({'quad':q,'triangles':[a,b]})
 edges=Counter(tuple(sorted((f[i],f[(i+1)%len(f)]))) for f in faces for i in range(len(f)))
 verts={n for f in faces for n in f};parent={n:n for n in verts}
 def find(x):
  while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
  return x
 for a,b in edges:
  x,y=find(a),find(b)
  if x!=y:parent[x]=y
 comps=len({find(n) for n in verts});chi=len(verts)-len(edges)+len(faces);manifold=all(v==2 for v in edges.values())
 return {'external_vertices':len(verts),'external_edges':len(edges),'external_faces':len(faces),'connected_boundary_components':comps,'euler_characteristic':chi,'closed_manifold_edge_incidence':manifold,'total_genus_if_closed_orientable':comps-chi/2 if manifold else None,'quad_two_tri_nonconforming_interfaces':len(mismatch),'quad_two_tri_witnesses':mismatch[:10],'note':'Genus valid only for closed orientable manifold boundary; geometric intersections and vertex singularities are not exhaustively excluded.'}

def independent_gmsh(mesh):
 import gmsh
 gmsh.initialize();gmsh.option.setNumber('General.Terminal',0);gmsh.option.setNumber('General.NumThreads',1)
 try:
  gmsh.model.add('independent_quality');tag=gmsh.model.addDiscreteEntity(3);gmsh.model.mesh.addNodes(3,tag,np.arange(len(mesh.points))+1,mesh.points[:,:3].reshape(-1))
  types={'tetra':4,'hexahedron':5,'wedge':6,'pyramid':7};offset=1;out={}
  for b in mesh.cells:
   if b.type not in types:continue
   tags=np.arange(offset,offset+len(b.data));offset+=len(b.data);gmsh.model.mesh.addElementsByType(tag,types[b.type],tags,(b.data+1).reshape(-1))
   q=np.asarray(gmsh.model.mesh.getElementQualities(tags,'minSICN'));d=np.asarray(gmsh.model.mesh.getElementQualities(tags,'minDetJac'))
   rec={'count':len(q),'minSICN':float(q.min()),'p01SICN':float(np.quantile(q,.01)),'minDetJac':float(d.min()),'nonpositiveDetJac':int((d<=0).sum()),'below_0p05SICN':int((q<.05).sum())}
   if b.type in out:
    old=out[b.type];old['count']+=len(q);old['minSICN']=min(old['minSICN'],rec['minSICN']);old['minDetJac']=min(old['minDetJac'],rec['minDetJac']);old['nonpositiveDetJac']+=rec['nonpositiveDetJac'];old['below_0p05SICN']+=rec['below_0p05SICN'];old['p01SICN']=None
   else:out[b.type]=rec
  return {'gmsh_version':gmsh.__version__,'families':out}
 finally:gmsh.finalize()

def volume_fractions(mesh):
 sums={};pos={};counts=Counter()
 for b in mesh.cells:
  if b.type not in base.FACES:continue
  xyz=mesh.points[b.data,:3];v=np.zeros(len(xyz))
  for r,s,t,w in base.integration(b.type):v+=w*np.linalg.det(np.einsum('ena,nr->ear',xyz,base.gradient(b.type,r,s,t)))
  sums[b.type]=sums.get(b.type,0)+float(v.sum());pos[b.type]=pos.get(b.type,0)+float(v[v>0].sum());counts[b.type]+=len(v)
 total=sum(sums.values());pt=sum(pos.values());n=sum(counts.values())
 return {'signed_volume_by_family_mm3':sums,'positive_integrated_volume_by_family_mm3':pos,'signed_hex_volume_fraction':sums.get('hexahedron',0)/total if total>0 else None,'positive_volume_hex_fraction':pos.get('hexahedron',0)/pt if pt>0 else None,'hex_cell_count_fraction':counts['hexahedron']/n if n else None,'interpretation':'Positive volume fractions can hide inversions; hex dominance is accepted only alongside independent validity and CAD coverage.'}

def lines_for(case):
 if case=='thin_perforated_plate':return [{'a':[x,y,0],'b':[x,y,.6],'name':f'plate_{x}_{y}'} for x,y in [(2,2),(8,6),(15,6)]]
 if case=='slender_beam':return [{'a':[x,1.5,0],'b':[x,1.5,.8],'name':f'beam_x{x}'} for x in [10,30,50]]
 if case=='thin_fillet_bracket':return [{'a':[10,3,0],'b':[10,3,.7],'name':'horizontal_web'},{'a':[0,3,4],'b':[.7,3,4],'name':'vertical_web'}]
 if case=='curved_thin_tube':return [{'a':[0,5,.6],'b':[0,5,1],'name':'bend_top_wall'},{'a':[0,4,0],'b':[0,4.4,0],'name':'bend_inner_wall'}]
 if case=='ribbed_small_features':return [{'a':[2,5,0],'b':[2,5,.5],'name':'base_plate'},{'a':[5,5,1.5],'b':[5.4,5,1.5],'name':'first_rib'},{'a':[5.8,5,1.5],'b':[6.2,5,1.5],'name':'second_rib'}]
 return []

def feature_audit(mesh,metadata):
 g,loc=vtk_grid(mesh);probes=[]
 for probe in metadata.get('features',{}).get('feature_probes',[]):
  cell=int(loc.FindCell(probe['point']));actual=cell>=0;probes.append({**probe,'mesh_contains':actual,'containing_cell':cell,'matches_expected':actual==probe['inside']})
 lines=[]
 for line in lines_for(metadata['id']):
  a=np.asarray(line['a']);b=np.asarray(line['b']);u=np.linspace(.005,.995,199);xyz=a[None,:]+u[:,None]*(b-a);ids=np.array([int(loc.FindCell(p)) for p in xyz]);changes=int(np.count_nonzero(ids[1:]!=ids[:-1]));lines.append({**line,'samples':len(u),'material_samples':int((ids>=0).sum()),'missing_material_samples':int((ids<0).sum()),'missing_interior_material_samples':int(((ids<0)&(u*np.linalg.norm(b-a)>.01)&((1-u)*np.linalg.norm(b-a)>.01)).sum()),'endpoint_allowance_mm':.01,'distinct_intersected_cells':len(set(ids[ids>=0])),'cell_id_transitions':changes,'note':'Sampled line cell intersections, not certified element layers; oblique tetrahedra can inflate count.'})
 return {'method':'VTK StaticCellLocator point-in-cell on original first-order element connectivity','feature_probes':probes,'feature_probe_failures':sum(not p['matches_expected'] for p in probes),'thickness_probe_lines':lines,'thickness_lines_with_missing_material':sum(p['missing_material_samples']>0 for p in lines),'thickness_lines_with_missing_interior_material':sum(p['missing_interior_material_samples']>0 for p in lines),'limitations':'Finite point probes cannot prove the complete hole or gap is preserved; combine with surface genus and CAD geometry distances.'}

def audit(mesh_path,metadata_path,samples=1000):
 start=time.monotonic();source_sha={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(base.__file__)]};meta=json.loads(Path(metadata_path).read_text());p=Path(mesh_path);m=meshio.read(p);r=base.audit(p,Path(meta['step']),samples)
 faces,_=external_faces(m);r['round3_surface_topology']=surface_topology(faces);r['volume_fractions']=volume_fractions(m);r['gmsh_independent_quality']=independent_gmsh(m);r['thin_features']=feature_audit(m,meta);expected=meta.get('features',{}).get('expected_boundary_genus');r['expected_boundary_genus']=expected;r['boundary_genus_matches']=None if expected is None else r['round3_surface_topology']['total_genus_if_closed_orientable']==expected
 q=r['shape_function_quality'];g=r['gmsh_independent_quality']['families'];features=r['thin_features'];cad=r.get('cad',{});boundary= max(cad.get('boundary_nodes_to_trimmed_CAD',{}).get('max_mm') or 0,cad.get('boundary_face_centroids_to_trimmed_CAD',{}).get('max_mm') or 0)
 r['criteria']={'thickness_probe_endpoint_allowance_mm':.01,'sampled_normalized_J_min':.1,'gmsh_minSICN_min':.05,'absolute_CAD_volume_error_percent_max':1,'boundary_node_and_face_centroid_distance_mm_max':.01,'hex_dominant_volume_fraction_min':.5,'note':'Project research thresholds, not NFX or solver certification. Hex fraction 50% is an explicit majority criterion, not a universal industry standard.'}
 r['checks']={'basic':r['basic_validity_pass'],'normalized_J':bool(q) and all(x['min_normalized_jacobian']>=.1 for x in q.values()),'SICN':bool(g) and all(x['minSICN']>=.05 for x in g.values()),'CAD_volume':abs(r.get('cad_volume_error_percent',float('inf')))<=1,'sampled_boundary':boundary<=.01,'sampled_outside_centroids':(cad.get('outside_centroid_distance_to_trimmed_CAD',{}).get('max_mm') or 0)<=.01,'surface_conformity':r['round3_surface_topology']['quad_two_tri_nonconforming_interfaces']==0,'feature_probes':features['feature_probe_failures']==0 and features['thickness_lines_with_missing_interior_material']==0,'boundary_genus':r['boundary_genus_matches'] is not False}
 r['mesh_policy_pass']=all(r['checks'].values());r['hex_dominant_policy_pass']=r['mesh_policy_pass'] and (r['volume_fractions']['signed_hex_volume_fraction'] or 0)>=.5;r['case_id']=meta['id'];r['case_metadata_sha256']=hashlib.sha256(Path(metadata_path).read_bytes()).hexdigest();r['audit_source_sha256']=source_sha;r['extended_audit_seconds']=time.monotonic()-start;return r
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('mesh');ap.add_argument('--metadata',required=True);ap.add_argument('--output',required=True);ap.add_argument('--samples',type=int,default=1000);a=ap.parse_args()
 try:r=audit(a.mesh,a.metadata,a.samples)
 except Exception as e:r={'status':'audit_failed','mesh':a.mesh,'error':str(e),'traceback':traceback.format_exc()}
 Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k) for k in ['case_id','elements','volume_fractions','checks','mesh_policy_pass','hex_dominant_policy_pass','error','extended_audit_seconds']},indent=2));sys.exit(0 if r.get('mesh_policy_pass') else 2)
