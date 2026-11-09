"""One N17 million-element diagnostic run; product code is read-only.
This script does not turn core/API or Xvfb latency into native-Windows acceptance.
"""
from pathlib import Path
import gc, hashlib, importlib.metadata, json, os, platform, resource, statistics, sys, time, traceback
BASE=Path(__file__).parent
OUT=BASE/'events.jsonl'
resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))
def rss():
 return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
def emit(event, **kw):
 row={'event':event,'time':time.time(),'rss_bytes':rss(),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,**kw}
 with OUT.open('a') as f: f.write(json.dumps(row,default=str)+'\n'); f.flush()
 print(json.dumps(row,default=str),flush=True)
def phase(name,fn):
 emit('start',phase=name); t=time.perf_counter()
 try: out=fn()
 except BaseException as e:
  emit('failed',phase=name,seconds=time.perf_counter()-t,error=repr(e)); raise
 emit('finish',phase=name,seconds=time.perf_counter()-t)
 return out
def loop(name,fn,count=100):
 emit('start',phase=name); values=[]
 for i in range(count):
  t=time.perf_counter(); fn(i); dt=time.perf_counter()-t; values.append(dt)
  emit('operation',phase=name,index=i,seconds=dt)
 emit('finish',phase=name,seconds=sum(values),count=len(values),p95_seconds=sorted(values)[94],maximum_seconds=max(values),median_seconds=statistics.median(values),all_seconds=values)
 return values
emit('environment',host_pid=int(Path('/proc/self/stat').read_text().split()[0]),namespace_pid=os.getpid(),base_sha='0aaada402eaa10d8e45df21995d6c6d88a4711c9',python=sys.version,platform=platform.platform(),display=os.environ.get('DISPLAY'),cgroup_limit_bytes=Path('/sys/fs/cgroup/memory.max').read_text().strip(),cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),safety_virtual_limit_bytes=6*1024**3,safety_rss_stop_bytes=5*1024**3,scope='One diagnostic run; generated source I/O cache is warm; no Windows acceptance')
manifest=json.loads((BASE/'input-manifest.json').read_text()); inp=BASE/'input'
phase('raw_read_sha256',lambda: [hashlib.sha256((inp/x['path']).read_bytes()).hexdigest()==x['sha256'] for x in manifest['files']])
from caelab_prep.application import PrepSession
session=PrepSession()
summary=phase('open_rad_core_including_first_projection',lambda:session.open_rad(str(inp/'large_0000.rad')))
assert summary['element_count']==1_000_000 and summary['node_count']==1_020_100
assert len(session._deck_resources())==20
cards=session.list_cards(); parts=[c for c in cards if c['keyword'].startswith('/PART/')]
assert len(parts)==100
emit('model_counts',elements=summary['element_count'],nodes=summary['node_count'],parts=len(parts),native_sources=len(session._deck_resources()),raw_bytes=manifest['input_bytes'],diagnostics=session.diagnostics())
p1=phase('mesh_view_cached_first_external_copy',session.mesh_view)
p2=phase('mesh_view_cached_second_external_copy_while_first_alive',session.mesh_view)
cache=session._projection_cache
emit('copy_identity',points_container_distinct=p1['points'] is not p2['points'],point_rows_distinct=p1['points'][0] is not p2['points'][0],cells_container_distinct=p1['cells'] is not p2['cells'],cell_dicts_distinct=p1['cells'][0] is not p2['cells'][0],cell_nodes_distinct=p1['cells'][0]['nodes'] is not p2['cells'][0]['nodes'],cell_part_ref_distinct=p1['cells'][0]['part_ref'] is not p2['cells'][0]['part_ref'],node_resources_distinct=p1['node_resources'] is not p2['node_resources'],node_owner_lists_distinct=p1['node_resources'][1] is not p2['node_resources'][1],returned_points_share_cache=p1['points'][0] is cache['points'][0],returned_cells_share_cache=p1['cells'][0] is cache['cells'][0],projection_revision=summary['projection_revision'])
def container_bytes(p):
 return {'points_outer':sys.getsizeof(p['points']),'points_row_containers':sum(map(sys.getsizeof,p['points'])),'node_ids_outer':sys.getsizeof(p['node_ids']),'cells_outer':sys.getsizeof(p['cells']),'cell_dicts':sum(map(sys.getsizeof,p['cells'])),'cell_nodes_lists':sum(sys.getsizeof(c['nodes']) for c in p['cells']),'cell_part_ref_dicts':sum(sys.getsizeof(c['part_ref']) for c in p['cells']),'node_resources_dict':sys.getsizeof(p['node_resources']),'node_owner_lists':sum(map(sys.getsizeof,p['node_resources'].values()))}
emit('projection_container_bytes',cache=container_bytes(cache),returned=container_bytes(p1),excludes='scalar objects, interned/shared strings, raw text, parsed card layouts, allocator fragmentation',logical_numeric_payload_bytes=1_020_100*3*8+1_020_100*8+1_000_000*4*8+1_000_000*8)
del p1,p2; gc.collect(); emit('copies_released')
material=next(c for c in cards if c['keyword']=='/MAT/LAW1/41')
old_cache=id(session._projection_cache)
loop('core_scalar_edit_100',lambda i:session.set_field(material['id'],'young_modulus',210001+i))
loop('core_undo_100',lambda i:session.undo())
assert id(session._projection_cache)==old_cache
loop('core_element_selection_100',lambda i:session.select_entity('element',i*10000+5001))
phase('save_project',lambda:session.save_project(str(BASE/'million.caelab')))
emit('saved_size',bytes=(BASE/'million.caelab').stat().st_size)
phase('reopen_project_core_including_first_projection',lambda:session.open_project(str(BASE/'million.caelab')))
assert session.describe()['element_count']==1_000_000
emit('after_reopen',summary=session.describe())
# Production Qt+VTK window, not a substitute rendering implementation.
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop
from PySide6.QtTest import QTest
from caelab_prep.ui.main_window import MainWindow
import vtk
app=QApplication([])
emit('gui_environment',qt_platform=app.platformName(),versions={name:importlib.metadata.version(name) for name in ['PySide6','vtk','numpy']})
assert app.platformName()=='xcb'
def pump():
 app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)
def make_window():
 w=MainWindow(session,presentation='hypermesh',enable_viewport=True); w._allow_close=True
 w.resize(1920,1080); w.show(); assert QTest.qWaitForWindowExposed(w,10000); pump()
 w.viewport.standard_view('top'); pump(); w.viewport.render(); return w
window=phase('production_window_construct_show_render',make_window)
view=window.viewport; rw=view._widget.GetRenderWindow()
assert rw.GetClassName()=='vtkXOpenGLRenderWindow'
assert view._grid.GetNumberOfCells()==1_000_000 and view._visible_grid.GetNumberOfCells()==1_000_000
assert not view._render_failed
emit('render_counts',backend=rw.GetClassName(),size=list(rw.GetSize()),cells=view._grid.GetNumberOfCells(),points=view._grid.GetNumberOfPoints(),vtk_grid_memory_kib=view._grid.GetActualMemorySize(),vtk_visible_memory_kib=view._visible_grid.GetActualMemorySize())
def screenshot():
 image=app.primaryScreen().grabWindow(int(window.winId())); assert not image.isNull(); assert image.save(str(BASE/'million-native-window.png'))
phase('native_window_screenshot',screenshot)
phase('repeat_actual_render',view.render)
# Timing begins at the canonical API command and ends after queued UI work.
# Physical mouse/keyboard dispatch and native Windows are outside this metric.
loop('command_through_qt_selection_100',lambda i:(session.select_entity('element',i*10000+5001),pump()))
material=next(c for c in session.list_cards() if c['keyword']=='/MAT/LAW1/41')
loop('command_through_qt_scalar_edit_100',lambda i:(session.set_field(material['id'],'young_modulus',210001+i),pump()))
loop('command_through_qt_undo_100',lambda i:(session.undo(),pump()))
partrefs=[{'resource_id':c['resource_id'],'native_scope':c['keyword']} for c in session.list_cards() if c['keyword'].startswith('/PART/')]
loop('viewport_hide_one_then_show_all_100',lambda i:(view.hide_parts([partrefs[i]]),pump(),view.show_all_parts(),pump()))
phase('save_with_live_renderer',lambda:session.save_project(str(BASE/'million-live.caelab')))
window._allow_close=True; window.close(); pump()
emit('complete',scope='Linux Xvfb/software OpenGL diagnostic only; not Windows acceptance; hide metric includes hide+show pair')
