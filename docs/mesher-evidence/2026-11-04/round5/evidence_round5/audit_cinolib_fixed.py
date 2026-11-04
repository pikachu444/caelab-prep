from pathlib import Path
import os,subprocess,json,time,sys
import numpy as np,meshio
R=Path(__file__).resolve().parent
BASE=Path('/workspace/scratch/1d5c10ddf0e3');R4=BASE/'caelab_mesher_round4_20261104'
PY=BASE/'caelab_mesher_round2_20261104/runtime/bin/python'
ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','LD_LIBRARY_PATH':str(BASE/'hex_eval_20261103/gmsh/libs/usr/lib/x86_64-linux-gnu'),'PYTHONPATH':str(BASE/'caelab_mesher_round3_20261104/audit')}
for d in sorted((R/'runs/cinolib_fixed').iterdir()):
 for variant,suffix in [('projected','candidate.mesh'),('raw','candidate.mesh.raw.mesh')]:
  p=d/suffix
  if not p.exists():continue
  m=meshio.read(p);finite=np.isfinite(m.points).all(axis=1)
  rec=dict(vertices=len(m.points),cells={c.type:len(c.data) for c in m.cells},nonfinite_vertices=int((~finite).sum()),variant=variant)
  (d/f'{variant}_precheck.json').write_text(json.dumps(rec,indent=2));print(d.name,rec,flush=True)
  if not finite.all():continue
  v=d/(variant+'.vtu');meshio.write(v,m)
  cmd=[str(PY),str(R4/'audit/audit_round4_v43_frozen.py'),str(v),'--metadata',str(R4/'corpus'/d.name/'metadata.json'),'--output',str(d/(variant+'_audit.json')),'--samples','1000','--no-slot']
  t=time.monotonic()
  with (d/(variant+'_audit.log')).open('w') as f:
   try:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=ENV,timeout=600);rc=r.returncode;to=False
   except subprocess.TimeoutExpired:rc=None;to=True
  print(d.name,variant,dict(rc=rc,timeout=to,seconds=time.monotonic()-t),flush=True)
