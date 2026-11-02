"""Visualize actual saved BReps; this is a geometry inspection plot, not GUI proof."""
from pathlib import Path
import hashlib,json
import cadquery as cq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
P=Path(__file__).resolve().parent/'results'
fig=plt.figure(figsize=(12,5.5),layout='constrained')
for i,name in enumerate(('plate','rounded_L')):
 ax=fig.add_subplot(1,2,i+1,projection='3d')
 source=cq.Shape.importBrep(str(P/name/'source.brep'))
 candidate=cq.Shape.importBrep(str(P/name/'candidate.brep'))
 for shape,color,alpha in [(source,'#94a3b8',.12),(candidate,'#e99624',.82)]:
  vertices,triangles=shape.tessellate(.15,.1)
  points=[v.toTuple() for v in vertices]
  ax.add_collection3d(Poly3DCollection([[points[j] for j in t] for t in triangles],facecolor=color,edgecolor='none',alpha=alpha))
 for shape,color,width in [(source,'#64748b',.65),(candidate,'#9a4e00',1.8)]:
  for edge in shape.Edges():
   points=[edge.positionAt(j/30).toTuple() for j in range(31)]
   ax.plot(*zip(*points),color=color,lw=width)
 bb=source.BoundingBox()
 ax.set_xlim(bb.xmin-1,bb.xmax+1);ax.set_ylim(bb.ymin-1,bb.ymax+1);ax.set_zlim(bb.zmin-1,bb.zmax+1)
 ax.set_box_aspect((bb.xlen+2,bb.ylen+2,bb.zlen+2))
 ax.set_xlabel('X [mm]');ax.set_ylabel('Y [mm]');ax.set_zlabel('Z [mm]')
 ax.view_init(elev=24,azim=-63)
 ax.set_title('Plate: 2 mm, 1 candidate face' if name=='plate' else 'Rounded L: 2 mm, 3 faces, 2 shared seams')
fig.suptitle('Saved OCCT BReps: source boundary (grey), explicit paired-offset candidate (orange)\nSynthetic fixtures; geometric F1 evidence only')
fig.savefig(P/'geometry-preview.png',dpi=170)
print(P/'geometry-preview.png')
