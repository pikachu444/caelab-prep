from pathlib import Path
import sys,json,time,hashlib
import gmsh,numpy as np,meshio
P=Path(__file__).parent.resolve();R=P.parents[1];sys.path.insert(0,str(P));from cached_boundary_distance import CADBoundaryDistance
out=P/'boundary_validation';out.mkdir(exist_ok=True)
gmsh.initialize();gmsh.option.setNumber('General.Terminal',0)
gmsh.model.add('box');gmsh.model.occ.addBox(0,0,0,2,3,4);gmsh.model.occ.synchronize();gmsh.write(str(out/'box.brep'));gmsh.clear();gmsh.model.add('quarter_disk');o=gmsh.model.occ.addPoint(0,0,0);x=gmsh.model.occ.addPoint(2,0,0);y=gmsh.model.occ.addPoint(0,2,0);l1=gmsh.model.occ.addLine(o,x);arc=gmsh.model.occ.addCircleArc(x,o,y);l2=gmsh.model.occ.addLine(y,o);loop=gmsh.model.occ.addCurveLoop([l1,arc,l2]);gmsh.model.occ.addPlaneSurface([loop]);gmsh.model.occ.synchronize();gmsh.write(str(out/'quarter_disk.brep'));gmsh.finalize()
records={}
points=np.array([[1,1.5,2],[-1,0,0],[-1,-1,-1],[1,-2,-3],[1,1,0],[1,1,2],[3,4,5]],float);expected=np.array([1,1,np.sqrt(3),np.sqrt(13),0,1,np.sqrt(3)])
for case,pts,exp in [('box',points,expected),('quarter_disk',np.array(json.loads((R/'audit/calibrate_v41.json').read_text())['points']),np.array(json.loads((R/'audit/calibrate_v41.json').read_text())['analytic_distance_mm']))]:
 t=time.monotonic()
 with CADBoundaryDistance(out/(case+'.brep'),log=out/(case+'.log'))as q: values=q.query(pts)
 records[case]={'points':pts.tolist(),'expected':exp.tolist(),'actual':values[:,0].tolist(),'maximum_error_mm':float(np.max(np.abs(values[:,0]-exp))),'witness_distance_error_mm':float(np.max(np.abs(np.linalg.norm(pts-values[:,1:4],axis=1)-values[:,0]))),'seconds':time.monotonic()-t,'pass':bool(np.allclose(values[:,0],exp,rtol=0,atol=1e-8))};print(case,records[case],flush=True)
 (out/'validation.json').write_text(json.dumps(records,indent=2))
m=meshio.read(R/'corpus/occt_bottom/surface.vtu');points=m.points[np.linspace(0,len(m.points)-1,100,dtype=int)];bad=json.loads((R/'audit/curve_parameter_failure_witness.json').read_text());points=np.vstack([points,bad['query_point']]);t=time.monotonic()
with CADBoundaryDistance(R/'corpus/occt_bottom/original.brep',log=out/'bottom.log')as q:values=q.query(points)
records['bottom']={'points':len(points),'seconds':time.monotonic()-t,'boundary100_max_distance_mm':float(values[:-1,0].max()),'gmsh_inverse_failure_query_native_distance_mm':float(values[-1,0]),'gmsh_inverse_failure_query_native_closest':values[-1,1:4].tolist(),'max_witness_distance_error_mm':float(np.max(np.abs(np.linalg.norm(points-values[:,1:4],axis=1)-values[:,0]))),'support_type_counts':{str(int(x)):int((values[:,4]==x).sum())for x in np.unique(values[:,4])},'native_query_file_sha256':hashlib.sha256((P/'cad_boundary_query.cpp').read_bytes()).hexdigest()}
np.savez(out/'bottom_points_witnesses.npz',points=points,result=values)
(out/'validation.json').write_text(json.dumps(records,indent=2));print(records['bottom'],flush=True)
