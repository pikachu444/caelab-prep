"""Extract factual index entries; this does not build a card-generation schema."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag
from collections import Counter
import csv,json,re,hashlib

ROOT=Path(__file__).resolve().parents[1]
class Links(HTMLParser):
    def __init__(self):super().__init__();self.items=[];self.current=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a' and a.get('href'):
            self.current={'href':a['href'],'name':''};self.items.append(self.current)
    def handle_data(self,s):
        if self.current is not None:self.current['name']+=s
    def handle_endtag(self,tag):
        if tag=='a':self.current=None

rows=[];reconcile={}
for stage,key,sid in [('starter','starter2024','radioss-D01'),('engine','engine2024','radioss-D02')]:
    path=ROOT/'tmp/radioss'/(key+'.html');t=path.read_text()
    marker=re.search(r'<h2[^>]*>Supported Keywords</h2>',t)
    if not marker:raise RuntimeError('No official index marker '+key)
    section=t[marker.end():t.index('</section>',marker.end())]
    p=Links();p.feed(section)
    candidates=[a for a in p.items if a['name'].strip()] # Preserve official non-slash FTFILE label too
    unknown=[a for a in p.items if a not in candidates]
    pairs=Counter((a['name'].strip(),a['href']) for a in candidates)
    base='https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/'+('starter_input_r.htm' if stage=='starter' else 'engine_input_r.htm')
    for n,a in enumerate(candidates,1):
        rows.append({'entry_id':f'radioss-2024-{stage}-{n:04d}','name':a['name'].strip(),'entry_kind':('keyword-or-option-index-entry' if a['name'].strip().startswith(('/','#')) else 'non-slash-index-label'),'stage':stage,'source_id':sid,'official_url':urljoin(base,a['href']),'documentation_version':'Radioss 2024','detail_review':'index-only','canonical_keyword':'','alias_resolution':'not-exhaustively-resolved','solver_support':'not-verified'})
    byurl=Counter(urldefrag(urljoin(base,a['href']))[0] for a in candidates)
    reconcile[stage]={'source_links_in_supported_section':len(p.items),'extracted_index_rows':len(candidates),'unparsed_links':unknown,'duplicate_name_url_rows':sum(v-1 for v in pairs.values()),'unique_name_url_pairs':len(pairs),'unique_detail_pages':len(byurl),'shared_detail_page_count':sum(v>1 for v in byurl.values()),'aliases_and_variants':'index labels preserved; semantic alias/variant inventory not exhaustively classified','source_html_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
out=ROOT/'catalogues/radioss.csv'
with out.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with (ROOT/'catalogues/radioss.jsonl').open('w') as f:
    for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
(ROOT/'catalogues/radioss-reconciliation.json').write_text(json.dumps(reconcile,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'total_rows':len(rows),'stages':reconcile},ensure_ascii=False,indent=2))
