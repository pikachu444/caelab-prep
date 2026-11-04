from pathlib import Path
import json,subprocess,os,time,hashlib,sys
P=Path(__file__).parent.resolve();R=P.parents[1];sys.path.insert(0,str(R));from job_slots import heavy_job_slot
b=P/'cad_repair_experimental_v2';env=dict(os.environ,LD_LIBRARY_PATH=str(R.parent/'caelab_mesher_engine_20261104/smesh_layer/native_env/lib'),OMP_NUM_THREADS='1')
with heavy_job_slot('corpus:explicit_repair_trials'):
 for c in ['voron_dragon','voron_cw2_mainbody']:
  src=R/'corpus'/c/'original.brep';out=R/'evidence/repair_variants'/c/'shapefix_max001';out.mkdir(parents=True,exist_ok=False);b.chmod(0o755);t=time.monotonic();cmd=[str(b),str(src),'--repair','.001',str(out/'repaired.brep')]
  try:
   x=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=120);d={'command':cmd,'returncode':x.returncode,'seconds':time.monotonic()-t,'stdout':x.stdout,'stderr':x.stderr,'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(b.read_bytes()).hexdigest()}
   if x.returncode==0:
    d['parsed']=json.loads(x.stdout)
    for mode in ['stats','validity']:
     b.chmod(0o755);z=subprocess.run([str(b),str(out/'repaired.brep'),'--'+mode],env=env,capture_output=True,text=True,timeout=120);(out/(mode+'.json')).write_text(z.stdout if z.returncode==0 else json.dumps({'error':z.stderr,'returncode':z.returncode}))
    d['repaired_sha256']=hashlib.sha256((out/'repaired.brep').read_bytes()).hexdigest()
  except subprocess.TimeoutExpired:d={'command':cmd,'status':'timeout','budget_seconds':120}
  (out/'trial.json').write_text(json.dumps(d,indent=2));print(c,d.get('parsed',d),flush=True)
