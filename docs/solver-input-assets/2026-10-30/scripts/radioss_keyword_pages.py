"""Download 2024 index-linked detail pages internally, without reproducing text."""
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urldefrag
from concurrent.futures import ThreadPoolExecutor
import csv,json,hashlib,threading,time

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'tmp/radioss/keywords2024';DEST.mkdir(parents=True,exist_ok=True)
rows=list(csv.DictReader((ROOT/'catalogues/radioss.csv').open()))
urls=sorted({urldefrag(x['official_url'])[0] for x in rows})
stop=threading.Event()
def download(url):
    name=url.rsplit('/',1)[-1];p=DEST/name
    if stop.is_set():return {'url':url,'status':'skipped-after-rate-limit'}
    try:
        if p.exists():data=p.read_bytes();final=url
        else:
            with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=22) as r:
                data=r.read();final=r.url
            p.write_bytes(data)
        return {'url':url,'final_url':final,'status':'downloaded','file':'tmp/radioss/keywords2024/'+name,'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data),'read_depth':'not-read','redistribution':'locator-only'}
    except HTTPError as e:
        if e.code in (403,429):stop.set()
        return {'url':url,'status':'blocked','http_status':e.code,'error':str(e)}
    except Exception as e:return {'url':url,'status':'failed','error':str(e)}
started=time.time()
with ThreadPoolExecutor(6) as pool:
    results=list(pool.map(download,urls))
manifest={'version':'Radioss 2024 online official detail pages','unique_url_count':len(urls),'index_row_count':len(rows),'elapsed_seconds':round(time.time()-started,2),'rate_limit_stopped':stop.is_set(),'results':results,'full_field_review_complete':False,'runtime_verified':False}
(ROOT/'catalogues/radioss-detail-acquisition.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
from collections import Counter
print(json.dumps({'unique_urls':len(urls),'status_counts':dict(Counter(x['status'] for x in results)),'bytes':sum(x.get('size_bytes',0) for x in results),'rate_limit_stopped':stop.is_set(),'elapsed':manifest['elapsed_seconds']},indent=2))
