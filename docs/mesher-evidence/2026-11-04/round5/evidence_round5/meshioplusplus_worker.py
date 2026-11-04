from pathlib import Path
import meshioplusplus as mp,json,sys,time
case=sys.argv[1];spacing=float(sys.argv[2]);d=Path(sys.argv[3]);r=Path('/workspace/scratch/1d5c10ddf0e3/caelab_mesher_round4_20261104')
skin=mp.read(str(r/'corpus'/case/'surface.obj'))
t=time.monotonic()
m,report=mp.octree_mesh(skin,output="hex",min_size=spacing,max_size=4*spacing,surface_size=spacing,hex_grading="uniform",untangle_iterations=50,max_cells=1000000,max_tets=1500000,return_report=True)
mp.write(str(d/'candidate.vtu'),m)
report['call_seconds']=time.monotonic()-t
(d/'native_report.json').write_text(json.dumps(report,indent=2,default=str))
print(json.dumps(report,default=str))
