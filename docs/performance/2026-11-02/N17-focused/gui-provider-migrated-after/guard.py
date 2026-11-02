"""Run one process with RSS and cgroup anonymous-memory guards.
The guard is an environment-protection stop, not a lowered product budget.
"""
from pathlib import Path
import json, os, signal, subprocess, sys, time
BASE=Path(__file__).parent
out=(BASE/'console.log').open('w')
env=os.environ.copy(); env.update(PYTHONPATH=str(BASE/'snapshot/src'),PYTHONUNBUFFERED='1',XDG_CONFIG_HOME=str(BASE/'qt-config'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='2',LP_NUM_THREADS='2')
command=[sys.executable,str(BASE/'baseline.py')]
p=subprocess.Popen(command,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
t0=time.monotonic(); host_pid=None; maxrss=0; reason=None; samples=[]; phase='startup'; stage_t=t0
try:
 while p.poll() is None:
  if (BASE/'events.jsonl').exists():
   rows=(BASE/'events.jsonl').read_text().splitlines()
   for line in reversed(rows):
    try: r=json.loads(line)
    except ValueError: continue
    if r.get('event')=='start':
     candidate=(r['phase'],r['time'])
     if candidate!=phase: phase=candidate; stage_t=time.monotonic()-(time.time()-r['time'])
     break
   if host_pid is None and rows:
    first=json.loads(rows[0]); host_pid=first.get('host_pid')
  rss=0
  if host_pid:
   try: rss=int(Path(f'/proc/{host_pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
   except FileNotFoundError: pass
  maxrss=max(maxrss,rss)
  stats=dict(line.split() for line in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines())
  anonymous=int(stats['anon'])+int(stats['kernel'])
  current=int(Path('/sys/fs/cgroup/memory.current').read_text())
  samples.append([round(time.monotonic()-t0,3),rss,current,anonymous])
  if rss>5*1024**3: reason='environment_guard_process_RSS_above_5GiB'
  elif anonymous>7*1024**3: reason='environment_guard_cgroup_anon_plus_kernel_above_7GiB'
  elif time.monotonic()-stage_t>600: reason='diagnostic_stage_timeout_600s_not_product_budget'
  elif time.monotonic()-t0>1200: reason='diagnostic_run_timeout_1200s'
  if reason:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   break
  time.sleep(.05)
finally:
 out.close()
 result={'returncode':p.wait(),'wall_seconds':time.monotonic()-t0,'guard_reason':reason,'last_phase':phase,'max_sampled_process_rss_bytes':maxrss,'sample_interval_seconds':.05,'command':command,'samples_t_rss_cgroup_total_anon_plus_kernel':samples}
 (BASE/'guard.json').write_text(json.dumps(result,indent=2)); print(json.dumps({k:v for k,v in result.items() if not k.startswith('samples')}),flush=True)
