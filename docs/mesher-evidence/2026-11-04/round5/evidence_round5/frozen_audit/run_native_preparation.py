from pathlib import Path
import json,subprocess,time,os,sys,hashlib
R=Path(__file__).resolve().parents[2]; W=R.parent; P=Path(__file__).parent
sys.path.insert(0,str(R));from job_slots import heavy_job_slot
b=P/'cad_prepare'; env=os.environ.copy();env['LD_LIBRARY_PATH']=str(W/'caelab_mesher_engine_20261104/smesh_layer/native_env/lib');env['OMP_NUM_THREADS']='1'
def run(cmd,out,timeout=120):
 b.chmod(0o755);t=time.monotonic()
 try:
  r=subprocess.run([str(b),*map(str,cmd)],env=env,capture_output=True,text=True,timeout=timeout);d={'command':[str(b),*map(str,cmd)],'returncode':r.returncode,'seconds':time.monotonic()-t,'stdout':r.stdout,'stderr':r.stderr,'binary_sha256':hashlib.sha256(b.read_bytes()).hexdigest()}
  try:d['parsed']=json.loads(r.stdout)
  except Exception:pass
 except subprocess.TimeoutExpired as e:d={'command':list(map(str,cmd)),'status':'timeout','budget_s':timeout,'seconds':time.monotonic()-t}
 out.write_text(json.dumps(d,indent=2));print(out.name,d.get('parsed',d.get('status',d['returncode'])),flush=True)
 return d
with heavy_job_slot('corpus:native_CW2_and_validity'):
 old=R/'evidence/component_exports/voron_cw2_mainbody/selection.json';r=json.loads(old.read_text());r.update(status='assembly_import_interrupted_after_600s',exitcode=130,interrupt_note='Owning exec session65108 Ctrl-C confirmed exit130; no selected CAD exported');old.write_text(json.dumps(r,indent=2))
 out=R/'evidence/component_exports/voron_cw2_mainbody_native';out.mkdir(exist_ok=True)
 src=R/'source_research/voron/CAD__Stealthburner_CW2_Assembly.step'
 x=run([src,'--select',458,24244.509356067792,out/'selected.brep'],out/'selection_native.json',180)
 if x.get('returncode')==0:
  run([out/'selected.brep','--stats'],out/'stats.json')
  run([out/'selected.brep','--validity'],out/'validity.json')
 for c in ['drivelink_housing','voron_dragon']:
  src=R/'evidence/component_exports'/c/'selected.brep'
  run([src,'--validity'],P/(c+'_validity.json'))
