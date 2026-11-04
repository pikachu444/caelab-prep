from pathlib import Path
import subprocess,json,time,hashlib,os,signal
root=Path(__file__).resolve().parent
prior=Path('/workspace/scratch/1d5c10ddf0e3/caelab_mesher_round4_20261104')
for case,res in [('occt_bottom',64),('voron_dragon',96),('voron_cw2_mainbody',96)]:
 meta=json.loads((prior/'corpus'/case/'metadata.json').read_text())
 source=Path(meta['files']['surface.obj']['path'])
 assert hashlib.sha256(source.read_bytes()).hexdigest()==meta['files']['surface.obj']['sha256']
 dest=root/'runs/cinolib'/case;dest.mkdir(parents=True,exist_ok=True)
 cmd=[str(root/'build/cinolib_driver'),str(source),str(res),'10',str(dest/'candidate.mesh')]
 t=time.monotonic();peak=0;threads=0;timeout=False
 with (dest/'native.log').open('w') as f:
  p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),start_new_session=True)
  while p.poll() is None:
   try:
    status=Path(f'/proc/{p.pid}/status').read_text()
    for line in status.splitlines():
     if line.startswith('VmHWM:'):peak=max(peak,int(line.split()[1]))
     if line.startswith('Threads:'):threads=max(threads,int(line.split()[1]))
   except OSError:pass
   if time.monotonic()-t>900:os.killpg(p.pid,signal.SIGKILL);timeout=True;break
   time.sleep(0.5)
  rc=p.wait()
 rec=dict(case=case,resolution=res,projection_iterations=10,returncode=rc,timeout=timeout,seconds=time.monotonic()-t,peak_RSS_KiB_sampled=peak,max_OS_threads_observed=threads,command=cmd,input_sha256=meta['files']['surface.obj']['sha256'],input_cad_metadata=str(prior/'corpus'/case/'metadata.json'),native_output_exists=(dest/'candidate.mesh').exists(),native_source_commit='151dc5c46309affedadb9b45619cc137fb7326ed',policy_note='No 2GiB address-space limit; physical cgroup host8GiB. Raw and projected mesh both retained.')
 (dest/'result.json').write_text(json.dumps(rec,indent=2));print(json.dumps(rec),flush=True)
