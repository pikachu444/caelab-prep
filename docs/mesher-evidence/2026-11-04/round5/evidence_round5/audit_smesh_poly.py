from pathlib import Path
import json,sys,hashlib,importlib.util
from collections import Counter
import numpy as np
R=Path(__file__).resolve().parent
BASE=Path('/workspace/scratch/1d5c10ddf0e3/caelab_mesher_round4_20261104')
spec=importlib.util.spec_from_file_location('audit4',BASE/'audit/audit_round4_v43_frozen.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
for case in ['occt_bottom','voron_dragon','voron_cw2_mainbody']:
 d=R/'runs/smesh_cartesian'/case;p=d/'native.raw';lines=iter(p.read_text().splitlines());n=int(next(lines).split()[1]);labels=[];points=[]
 for _ in range(n):
  z=next(lines).split();labels.append(int(z[0]));points.append(list(map(float,z[1:4])))
 ix={v:i for i,v in enumerate(labels)};points=np.array(points);assert next(lines)=='ELEMENTS';elements={}
 for line in lines:
  if line=='VOLUME_FACES':break
  z=list(map(int,line.split()));elements[z[0]]=(z[1],z[2],z[4:])
 faces=[];centroids=[];native_volumes={};counts=Counter()
 for line in lines:
  z=list(map(int,line.split()));eid,nf=z[:2];pos=2;cf=[]
  for _ in range(nf):
   count=z[pos];pos+=1;f=tuple(ix[v] for v in z[pos:pos+count]);pos+=count;cf.append(f);faces.append(f)
  assert pos==len(z)
  native_volumes[eid]=cf;counts[elements[eid][0]]+=1;centroids.append(points[sorted(set(v for f in cf for v in f))].mean(axis=0))
 keys=[tuple(sorted(f)) for f in faces];incidence=Counter(keys);exterior=[f for f,k in zip(faces,keys) if incidence[k]==1]
 edges=Counter(tuple(sorted((f[i],f[(i+1)%len(f)]))) for f in exterior for i in range(len(f)))
 inventory={'hexahedron':counts[16],'wedge':counts[19],'polyhedron':counts[23]};total=sum(inventory.values())
 cad=a.corrected_cad(BASE/'corpus'/case/'original.brep',points,exterior,np.array(centroids),1000)
 result=dict(case=case,raw_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),nodes=n,volumes=total,inventory=inventory,hex_count_fraction=inventory['hexahedron']/total,exterior_faces=len(exterior),faces_used_more_than_twice=sum(v>2 for v in incidence.values()),exterior_edges_not_twice=sum(v!=2 for v in edges.values()),finite_coordinates=bool(np.isfinite(points).all()),cad=cad,scope='Native SMESH polygon faces retained. Finite CAD distance and face incidence only; no standard FE Jacobian, integrated volume, convexity, cell overlap, global topology or solver acceptance for polyhedra. Vertex-average centroids may lie outside nonconvex cells; outside samples are diagnostic, not proof of invalid volume.')
 (d/'poly_geometry_audit.json').write_text(json.dumps(result,indent=2));print(case,{k:v for k,v in result.items() if k not in ['cad','scope']},flush=True);print(case,'boundaryMax',max(cad['boundary_nodes_to_trimmed_CAD']['max_mm'],cad['boundary_face_centroids_to_trimmed_CAD']['max_mm']),flush=True)
