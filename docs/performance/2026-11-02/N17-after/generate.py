"""Deterministic native input: one million real quads, 100 parts, 20 sources.
Not a solver/physics oracle: geometry and I/O/performance fixture only.
"""
from pathlib import Path
import json, hashlib, time
root=Path(__file__).parent / 'input'
root.mkdir(exist_ok=True)
t0=time.perf_counter()
manifest={'generator_version':1,'elements':1_000_000,'nodes':1_020_100,'parts':100,'sources':20,'element_family':'SHELL quad4','grid_per_part':[100,100],'sources_include_root':True,'files':[]}
for source in range(20):
 path=root/('large_0000.rad' if source==0 else f'source-{source:02}.inc')
 with path.open('w',encoding='ascii',newline='\n') as f:
  if source==0:
   f.write('#RADIOSS STARTER\n/BEGIN\nN17 million actual quads\n      2024         0\n                  Mg                  mm                   s\n                  Mg                  mm                   s\n')
   for n in range(1,20): f.write(f'#include source-{n:02}.inc\n')
   f.write('/MAT/LAW1/41\nN17 elastic material\n'+f'{7.8e-9:20g}\n{210000:20g}{0.3:20g}\n')
   f.write('/PROP/SHELL/207\nN17 uniform shell\n'+f'{24:10d}{4:10d}{2:10d}{2:10d}'+' '*20+f'{1:20g}'+' '*20+'\n'+''.join(f'{x:20g}' for x in [0,0,0,0,.015])+'\n'+f'{0:10d}'+' '*10+f'{1:20g}{5/6:20.12g}'+' '*10+f'{2:10d}{0:10d}\n')
  else: f.write('# N17 generated geometry source\n')
  for p in range(source*5,(source+1)*5):
   pid=1001+p; nb=p*10201; eb=p*10000
   f.write(f'/PART/{pid}\nN17 part {p+1:03}\n'+f'{207:10d}{41:10d}{0:10d}\n/NODE\n')
   for y in range(101):
    for x in range(101): f.write(f'{nb+y*101+x+1:10d}{(p%10)*110+x:20g}{(p//10)*110+y:20g}{0:20g}\n')
   f.write(f'/SHELL/{pid}\n')
   for y in range(100):
    for x in range(100):
     n=nb+y*101+x+1
     f.write(''.join(f'{v:10d}' for v in [eb+y*100+x+1,n,n+1,n+102,n+101])+'\n')
  f.write('/END\n' if source==0 else '#ENDDATA\n')
 data=path.read_bytes(); manifest['files'].append({'path':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
manifest['generation_seconds']=time.perf_counter()-t0
manifest['input_bytes']=sum(x['bytes'] for x in manifest['files'])
(root.parent/'input-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2))
