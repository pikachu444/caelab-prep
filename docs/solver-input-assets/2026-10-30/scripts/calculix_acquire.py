from pathlib import Path
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor
import hashlib,json
BASE=Path(__file__).resolve().parents[1]/'tmp/calculix'
BASE.mkdir(parents=True,exist_ok=True)
names=['ccx_2.23.src.tar.bz2','ccx_2.23.doc.tar.bz2','ccx_2.23.htm.tar.bz2','ccx_2.23.pdf','ccx_2.23.test.tar.bz2','cgx_2.23.all.tar.bz2','gpl-2.0.txt']
def get(n):
 p=BASE/n;u='https://www.dhondt.de/'+n
 try:
  if not p.exists():
   with urlopen(u,timeout=40) as r:p.write_bytes(r.read())
  b=p.read_bytes();return dict(name=n,url=u,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),status='downloaded')
 except Exception as e:return dict(name=n,url=u,status='failed',error=str(e))
results=list(ThreadPoolExecutor(7).map(get,names));(BASE/'downloads.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
