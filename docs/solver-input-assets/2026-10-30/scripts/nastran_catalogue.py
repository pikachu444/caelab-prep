"""Extract factual entry names and page locators from the official QRG bookmarks.

Usage: python scripts/nastran_catalogue.py ROOT
Requires pypdf; source PDF is analysis-only and is not redistributed.
The full bookmark inventory is separate from the classified entry inventory.
"""
from pathlib import Path
import json,csv,collections,sys
from pypdf import PdfReader

URL='https://documentation-be.hexagon.com/bundle/MSC_Nastran_2024.2_Quick_Reference_Guide/raw/resource/enus/MSC_Nastran_2024.2_Quick_Reference_Guide.pdf'

def write_csv(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)

def extract(root):
    reader=PdfReader(root/'tmp/opti-nastran/nastran-qrg.pdf')
    def walk(items,depth=0):
        for item in items:
            if isinstance(item,list):
                yield from walk(item,depth+1)
            else:
                yield {'name':str(item.title),'depth':depth,
                       'page':reader.get_destination_page_number(item)+1}
    outline=list(walk(reader.outline))
    chapter='';rows=[];full=[];counts=collections.Counter()
    for item in outline:
        if item['depth']==0:chapter=item['name']
        full.append({**item,'chapter':chapter,'url':URL+'#page='+str(item['page']),
                     'kind':'source-bookmark-not-normalized-keyword'})
        depth,page=item['depth'],item['page'];kind=None
        if chapter.startswith('Chapter 2:') and depth==2:kind='nastran-system-setting'
        if chapter.startswith('Chapter 3:') and depth==3:kind='file-management'
        if chapter.startswith('Chapter 4:') and depth==2 and page>=145:kind='executive'
        if chapter.startswith('Chapter 5:') and depth==2 and page>=222:kind='case-control'
        if chapter.startswith('Chapter 5:') and depth==3:kind='case-option-topic'
        if chapter.startswith('Chapter 6:') and depth==2:kind='parameter'
        if chapter.startswith('Chapter 9:') and depth==2 and page>=1112:kind='bulk-entry'
        if not kind:continue
        rows.append({'name':item['name'],'kind':kind,'url':URL+'#page='+str(page),
                     'pdf_page':page,'source_id':'nastran-D01','read_depth':'outline-only',
                     'implementation_verified':'false','solver_executed':'false'})
        counts[kind]+=1
    assert len(full)==2196
    assert counts['bulk-entry']==924
    write_csv(root/'catalogues/nastran.csv',rows)
    write_csv(root/'catalogues/nastran-outline.csv',full)
    summary={'entries':len(rows),'sections':dict(counts),'all_outline_records':len(outline),
        'scope':'QRG chapter2/3/4/5/6/9 entry-level bookmarks; all book bookmarks retained separately; appendix/runtime/item-code entries not normalized into the entry list'}
    (root/'tmp/opti-nastran/nastran-index-summary.json').write_text(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':
    print(json.dumps(extract(Path(sys.argv[1] if len(sys.argv)>1 else '.')),indent=2))
