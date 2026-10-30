"""Acquire official linked pages for internal analysis; do not redistribute pages."""
from pathlib import Path
import csv, concurrent.futures, urllib.request, hashlib, json, sys

root = Path(sys.argv[1] if len(sys.argv)>1 else '.')
rows = list(csv.DictReader((root/'catalogues/optistruct.csv').open()))
pages = root/'tmp/opti-nastran/pages'
pages.mkdir(exist_ok=True)
urls = sorted({row['url'] for row in rows})

def fetch(url):
    path = pages/(hashlib.sha256(url.encode()).hexdigest()[:20]+'.html')
    try:
        if path.is_file():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(url,timeout=18) as response:
                data = response.read()
            if b'<main' not in data:
                raise ValueError('not a normal documentation HTML page')
            path.write_bytes(data)
        return {'url':url,'file':str(path.relative_to(root)),
                'size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'acquired':True,'read_depth':'not-read','redistribution':'locator-only'}
    except Exception as exc:
        return {'url':url,'acquired':False,'error':str(exc),'read_depth':'not-read'}

out=[]
with concurrent.futures.ThreadPoolExecutor(8) as pool:
    for i, item in enumerate(pool.map(fetch,urls),1):
        out.append(item)
        if i%100==0:
            print('OptiStruct',i,'/',len(urls),'failed',sum(not x['acquired'] for x in out),flush=True)
(root/'tmp/opti-nastran/pages-manifest.json').write_text(json.dumps(out,indent=2))
print('Complete:',len(out),'acquired:',sum(x['acquired'] for x in out),flush=True)
