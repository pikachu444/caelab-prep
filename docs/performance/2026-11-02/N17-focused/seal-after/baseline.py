"""Narrow diagnostic: one original input open, eight real GUI operations/type.
No skipped rendering, no async-first-response metric, no budget acceptance run.
The only runtime method replacement inserts timing boundaries into unchanged
mesh_view logic; wrappers always execute the original complete call.
"""
from pathlib import Path
import functools, gc, inspect, json, os, resource, statistics, textwrap, time
BASE=Path(__file__).parent; OUT=BASE/'events.jsonl'
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
def rss(): return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
def emit(event, **kw):
 r={'event':event,'time':time.time(),'rss_bytes':rss(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,**kw}
 with OUT.open('a') as f: f.write(json.dumps(r,default=str)+'\n')
 print(json.dumps(r,default=str),flush=True)
def phase(name,fn):
 emit('start',phase=name);t=time.perf_counter();v=fn();emit('finish',phase=name,seconds=time.perf_counter()-t);return v
emit('environment',host_pid=int(Path('/proc/self/stat').read_text().split()[0]),namespace_pid=os.getpid(),scope='Focused breakdown on prior N17-after frozen source; not another acceptance campaign')
from caelab_prep.application import PrepSession
from caelab_prep.application import session as sm
from caelab_prep.radioss import DeckResource
samples={};stack=[]
def add(label,elapsed): samples.setdefault(label,[]).append(elapsed)
def wrap(cls,name,label=None):
 original=getattr(cls,name);key=label or f'{cls.__name__}.{name}'
 @functools.wraps(original)
 def timed(*args,**kwargs):
  t=time.perf_counter();frame=[key,t,0.];stack.append(frame)
  try:return original(*args,**kwargs)
  finally:
   elapsed=time.perf_counter()-t;stack.pop();add(key+'.inclusive',elapsed);add(key+'.self',elapsed-frame[2])
   if stack:stack[-1][2]+=elapsed
 setattr(cls,name,timed)
for method in ('__init__','mesh_projection'):wrap(DeckResource,method)
# Each inserted mark surrounds only the existing code; its source is retained.
source=textwrap.dedent(inspect.getsource(PrepSession.mesh_view))
source=source.replace('''        if self._projection_cache is None:
            nodes:''','''        if self._projection_cache is None:
            _n17_t = _n17_clock()
            nodes:''')
source=source.replace('''            valid = []''','''            _n17_mark("native_parse_and_merge", _n17_t)
            _n17_t = _n17_clock()
            valid = []''',1)
source=source.replace('''            parts = {}''','''            _n17_mark("validate_connectivity_and_sort_nodes", _n17_t)
            _n17_t = _n17_clock()
            parts = {}''',1)
source=source.replace('''            cache = freeze_mesh_payload(''','''            _n17_mark("shared_part_reference_resolution", _n17_t)
            _n17_t = _n17_clock()
            cache = freeze_mesh_payload(''',1)
source=source.replace('''            by_id, by_part = {}, {}''','''            _n17_mark("owned_payload_seal", _n17_t)
            _n17_t = _n17_clock()
            by_id, by_part = {}, {}''',1)
source=source.replace('''            self._projection_index = {"cells_by_id": by_id, "cells_by_part": by_part}''','''            self._projection_index = {"cells_by_id": by_id, "cells_by_part": by_part}
            _n17_mark("index_build", _n17_t)''',1)
assert source.count('_n17_mark(')==5
(BASE/'instrumented_mesh_view.py').write_text(source)
def mark(label,started):
 elapsed=time.perf_counter()-started;add(label,elapsed);emit('mesh_phase',phase=label,seconds=elapsed)
ns=dict(sm.__dict__);ns.update(_n17_clock=time.perf_counter,_n17_mark=mark)
exec(compile(source,str(BASE/'instrumented_mesh_view.py'),'exec'),ns)
PrepSession.mesh_view=ns['mesh_view']
session=PrepSession()
phase('focused_core_open',lambda:session.open_rad('<workspace>/audit/N17-baseline/input/large_0000.rad'))
assert session.describe()['element_count']==1_000_000
view1=session.mesh_view();view2=session.mesh_view()
assert view1['cells'] is view2['cells']
assert view1['cells'][0]['part_ref'] is view1['cells'][9999]['part_ref']
assert view1['node_resources'][1] is view1['node_resources'][2]
try:view1['cells'][0]['nodes']=(0,)
except TypeError:pass
else:raise AssertionError('mutable cell escaped')
emit('open_components',samples={k:{'count':len(v),'sum_seconds':sum(v)} for k,v in samples.items()});samples.clear()
emit('complete',scope='Core open/seal/index only, no GUI or acceptance campaign')
