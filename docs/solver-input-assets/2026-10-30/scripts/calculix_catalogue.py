"""Extract the official CCX 2.23 keyword index; does not generate solver decks."""
from pathlib import Path
from html.parser import HTMLParser
import re,csv,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'tmp/calculix'
HTML=TMP/'extract-ccx_2.23.htm/CalculiX/ccx_2.23/doc/ccx'
TEX=TMP/'extract-ccx_2.23.doc/CalculiX/ccx_2.23/doc/ccx.tex'
class Parse(HTMLParser):
 def __init__(self):super().__init__();self.anchors=[];self.cur=None;self.parts=[]
 def handle_starttag(self,t,a):
  if t.lower()=='a':self.cur=[dict(a).get('href',''),'']
 def handle_data(self,s):
  self.parts.append(s)
  if self.cur is not None:self.cur[1]+=s
 def handle_endtag(self,t):
  if t.lower()=='a' and self.cur is not None:self.anchors.append(self.cur);self.cur=None
p=Parse();p.feed((HTML/'node223.html').read_text());anchors=[(href,text.strip()) for href,text in p.anchors if text.strip().startswith('*')]
unique={}
for href,name in anchors:unique.setdefault(name,href)
tex_entries=[]
for i,line in enumerate(TEX.read_text().splitlines(),1):
 m=re.search(r'\\subsection\{\\label\{([^}]+)\}(\*[^}]+)\}',line)
 if m:tex_entries.append((m[2],m[1],i))
assert set(unique)==set(x[0] for x in tex_entries)
reviewed={4,33,223,224,227,249,273,274,277,281,303,311,323,328,331,333,338,345,346,350,352,356,408}
rows=[]
for name,label,line in tex_entries:
 href=unique[name];f=HTML/href;q=Parse();q.feed(f.read_text());txt=' '.join(''.join(q.parts).split());m=re.search(r'Keyword type:\s*(.*?)(?:This |With |Sometimes |A |The |One |It |In |First |For |\*|$)',txt)
 rows.append({'name':name,'kind':'keyword','manual_version':'CCX 2.23, 2025-10-19','source_id':'calculix-D02','official_source_url':'https://www.dhondt.de/ccx_2.23.htm.tar.bz2','archive_member':'CalculiX/ccx_2.23/doc/ccx/'+href,'tex_label':label,'tex_line':line,'html_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'read_depth':'relevant-sections' if int(re.search(r'node(\d+)',href)[1]) in reviewed else 'index-parsed','field_schema_complete':False,'solver_executed':False})
def write_csv(path,rows):
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
write_csv(ROOT/'catalogues/calculix.csv',rows)
with (ROOT/'catalogues/calculix.jsonl').open('w') as f:
 for x in rows:f.write(json.dumps(x,ensure_ascii=False)+'\n')
manifest=[]
TEST=TMP/'extract-ccx_2.23.test/CalculiX/ccx_2.23/test'
for f in sorted(TEST.rglob('*')):
 if f.is_file():manifest.append({'archive_member':'CalculiX/ccx_2.23/test/'+str(f.relative_to(TEST)),'role':'input-deck' if f.suffix=='.inp' else 'reference-result' if f.suffix=='.ref' else 'test-support','size_bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'source_id':'calculix-D06','redistribution':'unknown; archive/source locator only in deliverable'})
write_csv(ROOT/'catalogues/calculix-test-assets.csv',manifest)
report={'official_index_anchor_count':len(anchors),'unique_manual_keyword_sections':len(unique),'tex_keyword_subsections':len(tex_entries),'navigation_duplicate_anchors':len(anchors)-len(unique),'index_minus_tex':sorted(set(unique)-set(x[0] for x in tex_entries)),'tex_minus_index':sorted(set(x[0] for x in tex_entries)-set(unique)),'missing_local_html':[],'aliases_and_options':'No synthetic aliases/options count added; each official starred subsection retained exactly. Parameters and element types are not extra keywords.','official_test_archive_files':len(manifest),'official_input_decks':sum(x['role']=='input-deck' for x in manifest),'official_reference_result_files':sum(x['role']=='reference-result' for x in manifest),'all_fields_reviewed':False,'runtime_verified':False}
(ROOT/'catalogues/calculix-reconciliation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
