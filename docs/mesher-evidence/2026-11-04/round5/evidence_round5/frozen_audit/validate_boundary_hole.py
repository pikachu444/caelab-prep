from pathlib import Path
import sys,json,time
import numpy as np,gmsh
P=Path(__file__).parent.resolve();sys.path.insert(0,str(P));from cached_boundary_distance import CADBoundaryDistance
out=P/'boundary_validation';cad=out/'hollow_cylinder.brep';gmsh.initialize();gmsh.option.setNumber('General.Terminal',0);a=gmsh.model.occ.addCylinder(0,0,0,0,0,4,2);b=gmsh.model.occ.addCylinder(0,0,0,0,0,4,1);gmsh.model.occ.cut([(3,a)],[(3,b)]);gmsh.model.occ.synchronize();gmsh.write(str(cad));gmsh.finalize()
points=np.array([[0,0,2],[1.5,0,2],[3,0,2],[1.5,0,5],[0,0,5],[0,1,2],[0,2,4]],float);expected=np.array([1,.5,1,1,np.sqrt(2),0,0]);t=time.monotonic()
with CADBoundaryDistance(cad,log=out/'hollow_cylinder.log')as q:values=q.query(points)
r={'fixture':'Analytic hollow cylinder Rinner1 Router2 z0..4; includes hole axis, material interior, curved faces and cap edges','points':points.tolist(),'expected':expected.tolist(),'actual':values[:,0].tolist(),'max_error_mm':float(np.max(np.abs(values[:,0]-expected))),'seconds':time.monotonic()-t,'pass':bool(np.allclose(values[:,0],expected,atol=1e-8,rtol=0))};(out/'hollow_cylinder_validation.json').write_text(json.dumps(r,indent=2));print(r)
