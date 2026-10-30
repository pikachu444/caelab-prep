"""Acquire the public Abaqus 2025 keyword index and source pages for analysis.

Only factual names/locators/hashes are deliverable. Vendor HTML is analysis-only.
This script does not run Abaqus or generate/validate an analysis deck.
"""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag
import concurrent.futures, csv, hashlib, json, time, urllib.request

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / 'tmp/abaqus'
BASE = 'https://docs.software.vt.edu/abaqusv2025/English/'
INDEX = BASE + 'SIMACAECAERefMap/simacae-c-gen-kwbrowser.htm'
READER = BASE + 'SIMACAECAERefMap/simacae-c-gen-kwinpfilereader.htm'

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.a=None; self.buf=''
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.a=dict(attrs); self.buf=''
    def handle_data(self,s):
        if self.a is not None: self.buf+=s
    def handle_endtag(self,tag):
        if tag=='a' and self.a is not None:
            self.links.append((self.buf.strip(),self.a.get('href','')));self.a=None

def acquire(url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.stat().st_size>1000:
        b=path.read_bytes()
        return {'url':url,'file':str(path.relative_to(ROOT)),'status':'downloaded','size_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    try:
        with urllib.request.urlopen(url,timeout=25) as r:
            b=r.read();final=r.url
        path.write_bytes(b)
        return {'url':url,'final_url':final,'file':str(path.relative_to(ROOT)),'status':'downloaded','size_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
    except Exception as e:
        return {'url':url,'file':None,'status':'failed','error':str(e)}

def main():
    TMP.mkdir(parents=True,exist_ok=True)
    top=[]
    for key,url in [('keyword-browser',INDEX),('keyword-reader',READER)]:
        top.append(acquire(url,TMP/(key+'.html')))
    p=Links();p.feed((TMP/'keyword-browser.html').read_text())
    links=[(name,urljoin(INDEX,href)) for name,href in p.links if 'SIMACAEKEYRefMap/simakey-r-' in href]
    assert len(links)==len(set(links)), 'duplicate keyword table names/links'
    p2=Links();p2.feed((TMP/'keyword-reader.html').read_text())
    reader={(name,urljoin(READER,href)) for name,href in p2.links if 'SIMACAEKEYRefMap/simakey-r-' in href}
    entries=[]
    for i,(name,url) in enumerate(links,1):
        entries.append({'entry_id':f'abaqus-K{i:04d}','name':'*'+name,'kind':'keyword','source_id':'abaqus-D02','url':url,'locator':name+' row in keyword browser; linked keyword page','version':'Abaqus 2025 documentation mirror','read_depth':'index-parsed','full_field_review':False})
    (ROOT/'catalogues').mkdir(exist_ok=True)
    with (ROOT/'catalogues/abaqus.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(entries[0]));w.writeheader();w.writerows(entries)
    urls={urldefrag(x['url'])[0] for x in entries}
    def worker(url):
        return acquire(url,TMP/'keywords'/url.rsplit('/',1)[1])
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        manifest=list(pool.map(worker,sorted(urls)))
    all_manifest=top+manifest
    with (ROOT/'catalogues/abaqus-source-acquisition.jsonl').open('w') as f:
        for item in all_manifest:f.write(json.dumps(item,ensure_ascii=False)+'\n')
    reconciliation={'index_entries':len(entries),'unique_names':len({x['name'] for x in entries}),'unique_keyword_pages':len(urls),'reader_index_entries':len(reader),'browser_not_in_reader':sorted(set(links)-reader),'reader_not_in_browser':sorted(reader-set(links)),'downloaded_keyword_pages':sum(x['status']=='downloaded' for x in manifest),'failed_keyword_pages':[x for x in manifest if x['status']!='downloaded'],'full_field_review_complete':False,'runtime_verified':False}
    (ROOT/'catalogues/abaqus-reconciliation.json').write_text(json.dumps(reconciliation,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in reconciliation.items() if k not in ('browser_not_in_reader','reader_not_in_browser','failed_keyword_pages')},ensure_ascii=False))
    print('failed pages',len(reconciliation['failed_keyword_pages']))

if __name__=='__main__':main()
