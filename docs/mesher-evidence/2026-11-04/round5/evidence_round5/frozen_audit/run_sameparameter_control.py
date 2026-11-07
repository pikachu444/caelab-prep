from pathlib import Path
import subprocess,resource,time,json,os,hashlib
P=Path(__file__).parent.resolve();R=P.parents[1];b=P/'cad_sameparameter_control';out=R/'evidence/repair_variants/drivelink_housing/sameparameter_forced_1e7';out.mkdir(parents=True,exist_ok=False);src=R/'corpus/drivelink_housing/original.brep';env=dict(os.environ,LD_LIBRARY_PATH=str(R.parent/'caelab_mesher_engine_20261104/smesh_layer/native_env/lib'),OMP_NUM_THREADS='1')
def limits():resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
records=[]
for label,args in [('repair',[src,'--sameparameter',out/'repaired.brep']),('stats',[out/'repaired.brep','--stats']),('tessellation',[out/'repaired.brep','--obj','.01',out/'surface.obj'])]:
 b.chmod(0o755);cmd=[str(b),*map(str,args)];t=time.monotonic()
 try:
  x=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=120,preexec_fn=limits);d={'stage':label,'command':cmd,'returncode':x.returncode,'seconds':time.monotonic()-t,'stdout':x.stdout,'stderr':x.stderr,'AS_limit_bytes':1024**3,'timeout_s':120,'binary_sha256':hashlib.sha256(b.read_bytes()).hexdigest()}
  if x.returncode==0:d['parsed']=json.loads(x.stdout)
 except subprocess.TimeoutExpired:d={'stage':label,'command':cmd,'status':'timeout','seconds':time.monotonic()-t,'budget_s':120}
 records.append(d);(out/'control.json').write_text(json.dumps({'original_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'records':records},indent=2));print(label,d.get('parsed',d),flush=True)
 if d.get('returncode')!=0:break
