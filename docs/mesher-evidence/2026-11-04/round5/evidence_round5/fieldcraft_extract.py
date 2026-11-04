from pathlib import Path
import struct,zipfile,json,hashlib,sys
import numpy as np,meshio
p=Path(sys.argv[1]);d=p.parent
with zipfile.ZipFile(p) as z:
 b=z.read('mesh.bin');manifest=json.loads(z.read('fieldcraft.json'));(d/'package_manifest.json').write_text(json.dumps(manifest,indent=2))
assert b[:8] in (b'MCMESH01',b'MCMESH02');scale=1 if b[:8]==b'MCMESH01' else 1000
n,e,g,et,nt=struct.unpack_from('<5Q',b,8);pos=48;points=[];labels=[]
for i in range(n):
 label,x,y,z=struct.unpack_from('<Iddd',b,pos);pos+=28;labels.append(label);points.append([scale*x,scale*y,scale*z])
ix={label:i for i,label in enumerate(labels)};cells=[]
for i in range(e):
 label,kind=struct.unpack_from('<IB',b,pos);pos+=5;assert kind==10,kind
 conn=struct.unpack_from('<8I',b,pos);pos+=32;cells.append([ix[a] for a in conn])
m=meshio.Mesh(np.array(points),[('hexahedron',np.array(cells))]);meshio.write(d/'candidate.vtu',m)
(d/'conversion.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),nodes=n,hexes=e,entities=g,tagged_elements=et,tagged_nodes=nt,unit='Encoding '+b[:8].decode()+' coordinate scaling to mm: x'+str(scale)+'; MCMESH01 model units unspecified, matched against input plate dimensions; unchanged standard Hex8 ordering',geometry_tag_note='Native tags retained in fieldcraft package; array-only independent audit conversion does not export them'),indent=2))
print(n,e,g,et,nt)
