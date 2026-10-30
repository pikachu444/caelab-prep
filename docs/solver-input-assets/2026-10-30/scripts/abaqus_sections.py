"""Acquire selected source sections and examples, without running a solver."""
from pathlib import Path
from html.parser import HTMLParser
import concurrent.futures, json, urllib.request
ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'tmp/abaqus'
BASE='https://docs.software.vt.edu/abaqusv2025/English/'
PAGES={
 'keyword-guide':'SIMACAEKEYRefMap/simakey-c-ov.htm',
 'surface':'SIMACAEKEYRefMap/simakey-r-surface.htm',
 'include':'SIMACAEKEYRefMap/simakey-r-include.htm',
 'elastic':'SIMACAEKEYRefMap/simakey-r-elastic.htm',
 'solidsection':'SIMACAEKEYRefMap/simakey-r-solidsection.htm',
 'shellsection':'SIMACAEKEYRefMap/simakey-r-shellsection.htm',
 'boundary':'SIMACAEKEYRefMap/simakey-r-boundary.htm',
 'contactpair':'SIMACAEKEYRefMap/simakey-r-contactpair.htm',
 'contact':'SIMACAEKEYRefMap/simakey-r-contact.htm',
 'amplitude':'SIMACAEKEYRefMap/simakey-r-amplitude.htm',
 'step':'SIMACAEKEYRefMap/simakey-r-step.htm',
 'dynamic':'SIMACAEKEYRefMap/simakey-r-dynamic.htm',
 'output':'SIMACAEKEYRefMap/simakey-r-output.htm'}
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style']:self.skip+=1
 def handle_endtag(self,t):
  if t in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip and s.strip():self.parts.append(s.strip())
def work(it):
 key,part=it;url=BASE+part
 try:
  p=TMP/(key+'.html')
  if not p.exists():p.write_bytes(urllib.request.urlopen(url,timeout=25).read())
  text=Text();text.feed(p.read_text());(TMP/(key+'.txt')).write_text('\n'.join(text.parts))
  return key,p.stat().st_size
 except Exception as e:return key,str(e)
if __name__=='__main__':
 for row in concurrent.futures.ThreadPoolExecutor(6).map(work,PAGES.items()):print(row)
