from pathlib import Path
import gmsh, zipfile, json, hashlib
from xml.sax.saxutils import escape
R=Path(__file__).resolve().parent;d=R/'runs/fieldcraft/common_plate';d.mkdir(parents=True,exist_ok=True)
gmsh.initialize();gmsh.option.setNumber('General.Terminal',0);gmsh.option.setNumber('General.NumThreads',1)
box=gmsh.model.occ.addBox(0,0,0,40,20,10);hole=gmsh.model.occ.addCylinder(30,10,-1,0,0,12,4)
gmsh.model.occ.cut([(3,box)],[(3,hole)]);gmsh.model.occ.synchronize();gmsh.write(str(d/'original.brep'))
gmsh.option.setNumber('Mesh.MeshSizeMin',0.5);gmsh.option.setNumber('Mesh.MeshSizeMax',0.5);gmsh.model.mesh.generate(2)
tags,xyz,_=gmsh.model.mesh.getNodes();idx={int(t):i for i,t in enumerate(tags)};xyz=xyz.reshape(-1,3);tri=[];faces=[]
for fi,(_,tag) in enumerate(gmsh.model.getEntities(2)):
 types,_,nodes=gmsh.model.mesh.getElements(2,tag);faces.append(tag)
 for typ,ns in zip(types,nodes):
  assert typ==2
  for row in ns.reshape(-1,3):tri.append(([idx[int(t)] for t in row],fi))
gmsh.write(str(d/'surface.msh'));gmsh.finalize()
ns='https://github.com/bherbruck/solidcraft/formats/3mf-face-tags/2026/10'
v=''.join('<vertex x="%.17g" y="%.17g" z="%.17g"/>'%tuple(p) for p in xyz)
t=''.join('<triangle v1="%d" v2="%d" v3="%d" ft:face="%d"/>'%(*a,f) for a,f in tri)
f=''.join('<ft:face index="%d" name="CAD_face_%d"/>'%(i,tag) for i,tag in enumerate(faces))
model=f'<?xml version="1.0"?><model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:ft="{ns}"><resources><object id="1" type="model" name="Plate" ft:faces="{len(faces)}"><mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh></object></resources><build><item objectid="1"/></build></model>'
with zipfile.ZipFile(d/'input.3mf','w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('3D/3dmodel.model',model)
 z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
 z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
script=[{'command':'geometry.import.mesh','params':{'path':str(d/'input.3mf')}},{'command':'mesh.hex.octree','params':{'surface':0,'size':2.0,'max_depth':4,'max_elements':500000,'attempts':2}},{'command':'mesh.quality','params':{}},{'command':'file.save','params':{'path':str(d/'candidate.fieldcraft')}}]
(d/'script.json').write_text(json.dumps(script,indent=2))
(d/'input_provenance.json').write_text(json.dumps(dict(geometry='40x20x10 mm plate minus R4 through hole at (30,10)',exact_volume_mm3=8000-160*3.141592653589793,vertices=len(xyz),triangles=len(tri),face_mapping=faces,source='Independent Gmsh OCC construction of the same analytic S1 common plate; not complex original CAD',cad_sha256=hashlib.sha256((d/'original.brep').read_bytes()).hexdigest()),indent=2))
print(d)
