"""Independent first-order FE and face-incidence audit for arbitrary mesh files.

Gmsh is used only for optional CAD geometry queries, never element quality.
The normalized Jacobian below is a shape-function metric, NOT Verdict's metric.
Sampling does not prove positivity everywhere or absence of global overlaps.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib, itertools, json
import time
try:
 import resource
except ImportError: # Windows has no POSIX resource module.
 resource=None
from pathlib import Path
import meshio
import numpy as np

FACES = {
 'tetra':((0,2,1),(0,1,3),(1,2,3),(2,0,3)),
 'hexahedron':((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)),
 'pyramid':((0,3,2,1),(0,1,4),(1,2,4),(2,3,4),(3,0,4)),
 'wedge':((0,2,1),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)),
}
HEX = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],float)

def gradient(kind, r,s,t):
 if kind=='tetra': return np.array([[-1,-1,-1],[1,0,0],[0,1,0],[0,0,1]],float)
 if kind=='hexahedron':
  q=np.array([r,s,t]); out=np.empty((8,3))
  for k in range(3):
   others=[j for j in range(3) if j!=k]
   out[:,k]=HEX[:,k]*np.prod(1+HEX[:,others]*q[others],axis=1)/8
  return out
 if kind=='wedge':
  tri=np.array([1-r-s,r,s]); dtri=np.array([[-1,-1],[1,0],[0,1]])
  out=np.empty((6,3));out[:3,:2]=(1-t)*dtri/2;out[3:,:2]=(1+t)*dtri/2
  out[:3,2]=-tri/2;out[3:,2]=tri/2
  return out
 if kind=='pyramid':
  sig=HEX[:4,:2];out=np.zeros((5,3))
  out[:4,0]=sig[:,0]*(1+sig[:,1]*s)*(1-t)/4
  out[:4,1]=sig[:,1]*(1+sig[:,0]*r)*(1-t)/4
  out[:4,2]=-(1+sig[:,0]*r)*(1+sig[:,1]*s)/4;out[4,2]=1
  return out
 raise ValueError(kind)

def samples(kind):
 if kind=='tetra':return [(0.25,0.25,0.25)]
 if kind=='hexahedron':return list(itertools.product([-1.,0.,1.],repeat=3))
 if kind=='pyramid':return list(itertools.product([-1.,0.,1.],[-1.,0.,1.],[0.,.5,.9]))
 return [(r,s,t) for r,s in [(0,0),(1,0),(0,1),(1/3,1/3)] for t in [-1,0,1]]

def integration(kind):
 if kind=='tetra':return [(0.25,0.25,0.25,1/6)]
 q,w=np.polynomial.legendre.leggauss(3)
 if kind=='wedge':
  return [(r,s,t,w[k]/6) for r,s in [(1/6,1/6),(2/3,1/6),(1/6,2/3)] for k,t in enumerate(q)]
 return [(q[i],q[j],q[k] if kind=='hexahedron' else (q[k]+1)/2,
          w[i]*w[j]*w[k]*(1 if kind=='hexahedron' else .5)) for i,j,k in itertools.product(range(3),repeat=3)]

def shape_quality(xyz,kind,chunk_size=8192):
 """Same reference samples and quadrature, bounded temporary Jacobian arrays."""
 mins=np.empty(len(xyz));mindets=np.empty(len(xyz));finite=np.ones(len(xyz),bool);volume=np.zeros(len(xyz))
 for start in range(0,len(xyz),chunk_size):
  stop=min(start+chunk_size,len(xyz));part=xyz[start:stop]
  dm=np.full(len(part),np.inf);sm=np.full(len(part),np.inf)
  for p in samples(kind):
   jac=np.einsum('ena,nr->ear',part,gradient(kind,*p));d=np.linalg.det(jac)
   scale=np.prod(np.linalg.norm(jac,axis=1),axis=1)
   scaled=np.divide(d,scale,out=np.full_like(d,np.nan),where=scale>0)
   dm=np.minimum(dm,d);sm=np.minimum(sm,scaled);finite[start:stop]&=np.isfinite(scaled)
  mins[start:stop]=sm;mindets[start:stop]=dm
  for r,s,t,w in integration(kind):volume[start:stop]+=w*np.linalg.det(np.einsum('ena,nr->ear',part,gradient(kind,r,s,t)))
 return {'sample_count':len(samples(kind)),'min_determinant':float(mindets.min()),
  'min_normalized_jacobian':float(mins.min()),'p01_normalized_jacobian':float(np.quantile(mins,.01)),
  'median_normalized_jacobian':float(np.median(mins)),
  'nonpositive_cells':int(np.count_nonzero(mindets<=0)),
  'nonfinite_cells':int(np.count_nonzero(~finite)),
  'cells_below_0p1_normalized_jacobian':int(np.count_nonzero(mins<.1)),
  'cells_below_0p3_normalized_jacobian':int(np.count_nonzero(mins<.3)),
  'signed_volume':float(volume.sum()),'min_signed_volume':float(volume.min())}

def trim_distance(points, surfaces, gmsh):
 distances=np.full(len(points),np.inf)
 if len(points)==0:return distances
 for surf in surfaces:
  closest,uv=gmsh.model.getClosestPoint(2,surf,points.reshape(-1))
  closest=np.asarray(closest).reshape(-1,3);uv=np.asarray(uv).reshape(-1,2)
  d=np.linalg.norm(points-closest,axis=1)
  for i in np.flatnonzero(d<distances):
   if gmsh.model.isInside(2,surf,uv[i],parametric=True):distances[i]=d[i]
 return distances

def cad_audit(cad,points,faces,centroids,max_samples):
 import gmsh
 gmsh.initialize();gmsh.option.setNumber('General.Terminal',0)
 gmsh.option.setString('Geometry.OCCTargetUnit','MM')
 try:
  gmsh.model.occ.importShapes(str(cad));gmsh.model.occ.synchronize()
  vols=[t for d,t in gmsh.model.getEntities(3)]
  surfs=sorted({abs(t) for d,t in gmsh.model.getBoundary([(3,v) for v in vols],combined=True,oriented=False) if d==2})
  vol=sum(gmsh.model.occ.getMass(3,t) for t in vols)
  def sample(a):return a[np.linspace(0,len(a)-1,min(max_samples,len(a)),dtype=int)] if len(a) else a
  bi=np.array(sorted({n for f in faces for n in f}),int)
  # Sample face indices before constructing geometric centroids; preserve original order.
  fi=sample(np.arange(len(faces)));facecent=np.array([points[list(faces[i])].mean(axis=0) for i in fi])
  def stats(a):return {'samples':len(a),'max_mm':float(np.max(a)) if len(a) else None,
                       'p95_mm':float(np.quantile(a,.95)) if len(a) else None,
                       'unresolved':int(np.sum(~np.isfinite(a)))}
  nd=trim_distance(points[sample(bi)],surfs,gmsh);fd=trim_distance(facecent,surfs,gmsh)
  cs=sample(centroids)
  outside_mask=np.array([not any(gmsh.model.isInside(3,t,c) for t in vols) for c in cs],dtype=bool)
  outside=int(np.count_nonzero(outside_mask))
  outside_distances=trim_distance(cs[outside_mask],surfs,gmsh)
  return {'path':str(cad),'sha256':hashlib.sha256(cad.read_bytes()).hexdigest(),
          'unit':'mm','solid_count':len(vols),'surface_count':len(surfs),'volume':vol,
          'boundary_nodes_to_trimmed_CAD':stats(nd),'boundary_face_centroids_to_trimmed_CAD':stats(fd),
          'cell_centroid_samples':len(cs),'cell_centroid_samples_outside':outside,
          'outside_centroid_distance_to_trimmed_CAD':stats(outside_distances),
          'distance_note':'Finite sample of closest points on trimmed OCC faces; face-centroid error includes linear mesh chord error. Not Hausdorff distance.'}
 finally:gmsh.finalize()

def _rows(a):
 a=np.ascontiguousarray(a)
 return a.view(np.dtype((np.void,a.dtype.itemsize*a.shape[1]))).ravel()

def audit(path,cad=None,max_samples=1000):
 """Audit first-order cells. Face sorting is O(F log F); no pairwise search."""
 if not 1<=max_samples<=1000:raise ValueError('CAD sample limit must be between 1 and 1000')
 started=time.monotonic();timings={}
 mesh=meshio.read(path);points=np.asarray(mesh.points[:,:3]);timings['read_seconds']=time.monotonic()-started
 inventory=Counter();quality={};unsupported=[];centroids=[];cell_blocks=defaultdict(list)
 for block in mesh.cells:
  if block.type in FACES:cell_blocks[block.type].append(np.asarray(block.data,dtype=np.int64));inventory[block.type]+=len(block.data)
  elif block.type not in ('vertex','line','triangle','quad'):unsupported.append(block.type)
 # Keep face records in cell-block/cell/local-face order, matching the prior auditor.
 records=[];families=[];lengths=[];kinds=list(FACES);used=np.zeros(len(points),bool);duplicates=0
 t=time.monotonic()
 for kind,blocks in cell_blocks.items():
  cells=np.concatenate(blocks);used[cells]=True
  duplicates+=len(cells)-len(np.unique(np.sort(cells,axis=1),axis=0))
  quality[kind]=shape_quality(points[cells],kind)
 for block in mesh.cells:
  if block.type not in FACES:continue
  cells=block.data;local_faces=FACES[block.type];n=len(cells);nf=len(local_faces)
  rec=np.full((n,nf,4),-1,dtype=np.int64);lens=np.empty((n,nf),np.int8)
  for j,local in enumerate(local_faces):rec[:,j,:len(local)]=cells[:,local];lens[:,j]=len(local)
  records.append(rec.reshape(-1,4));lengths.append(lens.ravel());families.append(np.full(n*nf,kinds.index(block.type),np.int8))
  centroids.append(points[cells].mean(axis=1))
 timings['quality_and_records_seconds']=time.monotonic()-t;t=time.monotonic()
 faces=np.concatenate(records) if records else np.empty((0,4),dtype=np.int64)
 lengths=np.concatenate(lengths) if lengths else np.empty(0,np.int8)
 family=np.concatenate(families) if families else np.empty(0,np.int8)
 keys=np.sort(faces,axis=1);order=np.lexsort(keys.T[::-1]);sorted_keys=keys[order]
 starts=np.r_[0,np.flatnonzero(np.any(sorted_keys[1:]!=sorted_keys[:-1],axis=1))+1] if len(keys) else np.empty(0,dtype=int)
 counts=np.diff(np.r_[starts,len(keys)]);exterior_idx=np.sort(order[starts[counts==1]])
 shared_starts=starts[counts==2];a=order[shared_starts];b=order[shared_starts+1]
 bad_orientation=0
 for n in (3,4):
  mask=lengths[a]==n;aa=faces[a[mask],:n];bb=faces[b[mask],:n][:,::-1]
  opposite=np.zeros(len(aa),bool)
  for shift in range(n):opposite|=np.all(aa==np.roll(bb,shift,axis=1),axis=1)
  bad_orientation+=int(np.count_nonzero(~opposite))
 mixed=Counter()
 for ia,ib in zip(family[a],family[b]):
  if ia!=ib:mixed['+'.join(sorted((kinds[ia],kinds[ib])))]+=1
 boundary_kind=Counter();boundary_area=Counter();edge_arrays=[]
 for n in (3,4):
  idx=exterior_idx[lengths[exterior_idx]==n];ef=faces[idx,:n];xyz=points[ef]
  area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
  if n==4:area+=np.linalg.norm(np.cross(xyz[:,2]-xyz[:,0],xyz[:,3]-xyz[:,0]),axis=1)/2
  for k,kind in enumerate(kinds):
   sel=family[idx]==k
   if np.any(sel):boundary_kind[kind]+=int(sel.sum());boundary_area[kind]+=float(area[sel].sum())
  if len(ef):edge_arrays.append(np.sort(np.stack([ef,np.roll(ef,-1,axis=1)],axis=-1).reshape(-1,2),axis=1))
 if edge_arrays:
  _,edge_counts=np.unique(np.concatenate(edge_arrays),axis=0,return_counts=True);open_edges=int(np.count_nonzero(edge_counts!=2))
 else:open_edges=0
 surface_keys=[]
 for block in mesh.cells:
  if block.type in ('triangle','quad'):
   sk=np.full((len(block.data),4),-1,dtype=np.int64);sk[:,:block.data.shape[1]]=block.data;surface_keys.append(np.sort(sk,axis=1))
 missing=int(np.count_nonzero(~np.isin(_rows(keys[exterior_idx]),_rows(np.concatenate(surface_keys))))) if surface_keys else None
 exterior=[tuple(int(n) for n in keys[i] if n>=0) for i in exterior_idx]
 topology={'external_faces':len(exterior_idx),'nonmanifold_faces':int(np.count_nonzero(counts>2)),
  'shared_faces_without_opposite_orientation':bad_orientation,'duplicate_volume_cells':int(duplicates),
  'external_edges_not_twice':open_edges,'unused_nodes':int(np.count_nonzero(~used)),
  'duplicate_all_coordinates_rounded_10dp':len(points)-len(np.unique(np.round(points,10),axis=0)),
  'duplicate_coordinates_rounded_10dp':int(used.sum())-len(np.unique(np.round(points[used],10),axis=0)),
  'external_faces_missing_from_supplied_surface_cells':missing,
  'boundary_face_owner_families':dict(boundary_kind),'boundary_area_by_owner_family':dict(boundary_area),
  'boundary_area_hex_fraction':boundary_area['hexahedron']/sum(boundary_area.values()) if boundary_area else None,
  'mixed_shared_faces':dict(mixed)}
 timings['topology_seconds']=time.monotonic()-t
 result={'mesh':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'nodes':len(points),
  'elements':dict(inventory),'unsupported_volume_types':unsupported,'shape_function_quality':quality,
  'signed_mesh_volume':sum(q['signed_volume'] for q in quality.values()),'topology':topology,
  'limitations':['Sampled shape-function normalized Jacobian is not Verdict scaled Jacobian.',
    'No whole-cell positivity proof, no exhaustive cell-overlap test, no solver analysis.',
    'Closed boundary alone does not prove CAD coverage; inspect CAD distance and volume.']}
 if cad:
  t=time.monotonic();result['cad']=cad_audit(cad,points,exterior,np.concatenate(centroids) if centroids else np.empty((0,3)),max_samples)
  result['cad_volume_error_percent']=100*(result['signed_mesh_volume']/result['cad']['volume']-1);timings['cad_seconds']=time.monotonic()-t
 result['basic_validity_pass']=bool(inventory) and not unsupported and all(q['nonpositive_cells']==0 and q['nonfinite_cells']==0 for q in quality.values()) and all(topology[k]==0 for k in ('nonmanifold_faces','external_edges_not_twice','duplicate_coordinates_rounded_10dp','shared_faces_without_opposite_orientation','duplicate_volume_cells'))
 timings['total_seconds']=time.monotonic()-started
 peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None
 result['audit_performance']={'implementation':'vectorized-face-sort-v2','timings':timings,'peak_rss_kib':peak_rss,'cad_sample_limit':max_samples,'shape_quality_chunk_cells':8192}
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mesh',type=Path);p.add_argument('--cad',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--samples',type=int,default=1000)
 a=p.parse_args();r=audit(a.mesh,a.cad,a.samples);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
 raise SystemExit(0 if r['basic_validity_pass'] else 2)

