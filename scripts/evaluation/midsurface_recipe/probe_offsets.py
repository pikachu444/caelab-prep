import cadquery as cq
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
from OCP.BRepOffset import BRepOffset_Skin
from OCP.GeomAbs import GeomAbs_Intersection
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
shape=cq.Workplane('XZ').polyline([(0,0),(42,0),(42,32),(40,32),(40,2),(0,2)]).close().extrude(25).val()
for i,f in enumerate(shape.Faces()): print(i,f.Center().toTuple(),f.normalAt().toTuple(),f.Area())
faces=shape.Faces()
for name, wanted in [('outer',[(0,0,-1),(1,0,0)]),('inner',[(0,0,1),(-1,0,0)])]:
 selected=[f for f in faces if any((f.normalAt()-cq.Vector(*n)).Length<1e-7 for n in wanted) and f.Area()>100]
 sew=BRepBuilderAPI_Sewing(1e-7)
 for f in selected:sew.Add(f.wrapped)
 sew.Perform();shell=sew.SewedShape()
 print(name,'selected',len(selected),'source_seams',sew.NbContigousEdges())
 op=BRepOffsetAPI_MakeOffsetShape();op.PerformByJoin(shell,-1,1e-7,BRepOffset_Skin,False,False,GeomAbs_Intersection,False)
 print(name,'done',op.IsDone())
 if op.IsDone():
  result=cq.Shape.cast(op.Shape());print('resultvalid',BRepCheck_Analyzer(result.wrapped).IsValid(),'faces',[(f.Center().toTuple(),f.normalAt().toTuple(),f.Area()) for f in result.Faces()])
  globals()[name]=result
if 'outer' in globals() and 'inner' in globals():
 op=BRepAlgoAPI_Common(outer.wrapped,inner.wrapped);op.Build();r=cq.Shape.cast(op.Shape());print('COMMON',op.IsDone(),r.Area(),len(r.Faces()))
