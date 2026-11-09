"""Narrow diagnostic: one original input open, eight real GUI operations/type.
No skipped rendering, no async-first-response metric, no budget acceptance run.
Wrappers always execute the original complete call. Core open is uninstrumented;
this run is limited to the same GUI diagnostic operations on a new frozen snapshot.
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
emit('environment',host_pid=int(Path('/proc/self/stat').read_text().split()[0]),namespace_pid=os.getpid(),scope='PART context cache with explicit legacy-v4 project migration; source-manifest.json pins source; not acceptance campaign')
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
session=PrepSession()
import zipfile
with zipfile.ZipFile('<workspace>/audit/N17-after/million.caelab') as fixture_archive:
 fixture_manifest=json.loads(fixture_archive.read('manifest.json'))
emit('fixture_version',original_project_version=fixture_manifest['version'],original_has_model_relations='model_relations' in fixture_manifest,current_project_version=sm.PROJECT_VERSION)
phase('focused_core_open',lambda:session.open_project('<workspace>/audit/N17-after/million.caelab'))
assert session.describe()['element_count']==1_000_000
emit('open_components',samples={k:{'count':len(v),'sum_seconds':sum(v)} for k,v in samples.items()});samples.clear()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent,QEventLoop
from PySide6.QtTest import QTest
from caelab_prep.ui.main_window import MainWindow
from caelab_prep.ui.viewport import MeshViewport
from caelab_prep.application.rad_provider import RadProvider
# Use actual methods including real refresh, actual Render, and deferred deletion.
for name in ('_session_changed','refresh_document','_refresh_fields','_refresh_tree','_refresh_actions','_refresh_target_roles','_restore_approved_selection','_present_document'):
 wrap(MainWindow,name)
for name in ('set_selection','render','_selection_cell_indices','_apply_visibility'):
 wrap(MeshViewport,name)
for name in ('properties','available_operations','_assignment_fields'):
 wrap(RadProvider,name)
app=QApplication([])
def pump():
 app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
 app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
def make_window():
 w=MainWindow(session,presentation='hypermesh');w._allow_close=True;w.resize(1920,1080);w.show()
 assert QTest.qWaitForWindowExposed(w,10000);pump();w.viewport.standard_view('top');pump();return w
window=phase('focused_window_ready',make_window);view=window.viewport;rw=view._widget.GetRenderWindow()
assert rw.GetClassName()=='vtkXOpenGLRenderWindow';assert view._grid.GetNumberOfCells()==1_000_000
render_start=[]
def render_begin(obj,event):render_start.append(time.perf_counter())
def render_end(obj,event):
 if render_start:add('vtkRenderWindow.frame',time.perf_counter()-render_start.pop())
observers=[rw.AddObserver('StartEvent',render_begin),rw.AddObserver('EndEvent',render_end)]
samples.clear()
def trial(name,fn,count=8):
 emit('start',phase=name)
 records=[]
 for i in range(count):
  samples.clear();start=time.perf_counter();fn(i);pump();elapsed=time.perf_counter()-start
  values={k:{'calls':len(v),'sum_seconds':sum(v)} for k,v in samples.items()}
  records.append({'operation':i,'total_seconds':elapsed,'components':values})
  emit('diagnostic_operation',phase=name,**records[-1])
 emit('finish',phase=name,count=count,seconds=sum(x['total_seconds'] for x in records),median_seconds=statistics.median(x['total_seconds'] for x in records),maximum_seconds=max(x['total_seconds'] for x in records),scope='8 diagnostic trials; not 100-op p95 acceptance')
 return records
results={}
results['select']=trial('selection_breakdown',lambda i:session.select_entity('element',i*100000+5001))
mat=next(c for c in session.list_cards() if c['keyword']=='/MAT/LAW1/41')
results['scalar']=trial('scalar_breakdown',lambda i:session.set_field(mat['id'],'young_modulus',210001+i))
results['undo']=trial('undo_breakdown',lambda i:session.undo())
parts=[{'resource_id':c['resource_id'],'native_scope':c['keyword']} for c in session.list_cards() if c['keyword'].startswith('/PART/')]
results['hide_show']=trial('hide_show_breakdown',lambda i:(view.hide_parts([parts[i*10]]),view.show_all_parts()))
results['render']=trial('direct_render_breakdown',lambda i:view.render(),count=3)
(BASE/'components.json').write_text(json.dumps(results,indent=2))
for observer in observers:rw.RemoveObserver(observer)
window.close();pump();emit('complete',scope='Narrow diagnostics only; original operation bodies and actual renders executed')
