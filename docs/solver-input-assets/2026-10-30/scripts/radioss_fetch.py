"""Acquire public official reference pages for read-only input-format research."""
from pathlib import Path
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json, hashlib

BASE = Path(__file__).resolve().parents[1] / 'tmp' / 'radioss'
BASE.mkdir(parents=True, exist_ok=True)
class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.links=[]; self.current=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='a' and a.get('href'):
            self.current={'href':a['href'],'text':''};self.links.append(self.current)
    def handle_endtag(self,tag):
        if tag=='a':self.current=None
    def handle_data(self,s):
        if s.strip():self.text.append(s.strip())
        if self.current is not None:self.current['text']+=s

def acquire(item):
    key,url=item
    try:
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r:
            data=r.read();final=r.url;ct=r.headers.get('content-type','')
        ext='pdf' if data.startswith(b'%PDF') else ('zip' if data.startswith(b'PK') else 'html')
        f=BASE/(key+'.'+ext);f.write_bytes(data)
        out={'key':key,'url':url,'final_url':final,'status':'downloaded','file':str(f), 'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data),'content_type':ct}
        if ext=='html':
            p=Page();p.feed(data.decode('utf-8',errors='replace'))
            (BASE/(key+'.txt')).write_text('\n'.join(p.text))
            (BASE/(key+'.links.json')).write_text(json.dumps(p.links,ensure_ascii=False,indent=2))
        return out
    except Exception as e:return {'key':key,'url':url,'status':'blocked','error':str(e)}

if __name__=='__main__':
    import sys
    items=json.load(sys.stdin)
    results=list(ThreadPoolExecutor(8).map(acquire,items.items()))
    log=BASE/'acquisitions.json';old=json.loads(log.read_text()) if log.exists() else []
    old.extend(results);log.write_text(json.dumps(old,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False,indent=2))
