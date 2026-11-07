from pathlib import Path
import meshioplusplus as mp,json,sys,time,numpy as np
case=sys.argv[1];spacing=float(sys.argv[2]);d=Path(sys.argv[3]);r=Path('/workspace/scratch/1d5c10ddf0e3/caelab_mesher_round4_20261104')
skin=mp.read(str(r/'corpus'/case/'surface.obj'))
t=time.monotonic()
m,report=mp.octree_mesh(skin,output="hex",min_size=spacing,max_size=4*spacing,surface_size=spacing,hex_grading="uniform",untangle_iterations=50,max_cells=3000000,max_tets=1500000,return_report=True)
report['call_seconds']=time.monotonic()-t
(d/'native_report.json').write_text(json.dumps(report,indent=2,default=str))
points=np.asarray(m.points);conn=np.asarray(m.cells_dict['hexahedron'])
np.savez_compressed(d/'candidate.npz',points=points,hexahedron=conn)
with (d/'candidate.vtk').open('w') as f:
 f.write('# vtk DataFile Version 2.0\nmeshio++ native output; array-only export bypasses confirmed VTU writer crash\nASCII\nDATASET UNSTRUCTURED_GRID\nPOINTS %d double\n'%len(points));np.savetxt(f,points,fmt='%.17g')
 f.write('CELLS %d %d\n'%(len(conn),9*len(conn)));np.savetxt(f,np.c_[np.full(len(conn),8),conn],fmt='%d')
 f.write('CELL_TYPES %d\n'%len(conn));np.savetxt(f,np.full(len(conn),12),fmt='%d')
print(json.dumps(report,default=str))
