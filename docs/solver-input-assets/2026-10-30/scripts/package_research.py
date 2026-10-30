"""Build a reference archive and factual index. Does not run source excerpts.

Vendor documents/examples stay in tmp and are never included. This is not a DB
migration or a product capability check. Run after independent audit closes.
"""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import html
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PUBLIC_PREFIX='docs/solver-input-assets/2026-10-30'
KEYS=['radioss','dyna','abaqus','calculix','aster','optistruct','nastran']

def dump(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def build_index():
    solvers=[json.loads((ROOT/f'solvers/{k}.json').read_text()) for k in KEYS]
    rows=[]
    urls=set()
    for d in solvers:
        urls.update(s['url'] for s in d['sources'] if s.get('url'))
        rows.append(dict(key=d['key'],documentation=d['versions']['documentation'],
            source_records=len(d['sources']),source_urls=len({s['url'] for s in d['sources'] if s.get('url')}),
            catalogue_rows=d['catalogue']['entry_count'],catalogue_unit=d['catalogue']['count_unit'],
            rules=len(d['rules']),example_records=len(d['examples']),
            runtime_verified=d['runtime_verified'],full_field_review_complete=d['catalogue']['full_field_review_complete']))
    dump(ROOT/'summary.json',dict(date='2026-10-30',solver_families=7,
        source_records=sum(x['source_records'] for x in rows),unique_source_record_urls=len(urls),
        source_url_count_scope='central source records only; not all detailed-page catalogue URLs or archive members',
        rules=sum(x['rules'] for x in rows),example_records=sum(x['example_records'] for x in rows),
        example_count_unit='mixed selected bundle/fixture/case records, not count of standalone complete decks',
        catalogue_rows_sum=sum(x['catalogue_rows'] for x in rows),
        catalogue_sum_warning='mixed keyword/command/helper/options/bookmark rows; not unique keywords or implemented support',
        solver_runs=0,full_field_reviews_complete=0,solvers=rows))
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>CAE 솔버 입력 생성 자료</title><style>body{font:15px/1.55 system-ui,sans-serif;margin:32px auto;max-width:1220px;padding:0 20px;color:#17202b}h1{font-size:25px}table{width:100%;border-collapse:collapse}td,th{text-align:left;border-bottom:1px solid #d7dde4;padding:8px;vertical-align:top}th{background:#edf1f5}input{font:inherit;padding:9px;width:min(94%,650px);margin:12px 0}a{color:#164fa0}small{color:#526170}.warning{padding:14px;background:#fff5d9}#list td:nth-child(3){font-size:13px}</style>',
        '<h1>CAE 솔버 입력 생성 자료 · 2026-10-30</h1>',
        '<p class="warning">자료 취득·목록 추출·관련 규칙 검토 결과입니다. 전수 필드 schema·신규 생성기·solver 실행 완료가 아닙니다. 원문 판본·조사 깊이·권리와 누락을 함께 확인하십시오.</p>',
        '<p><a href="README.md">전체 안내</a> · <a href="summary.json">정확한 집계</a> · <a href="discussion/astra-findings.md">독립 감사</a> · <a href="validation.json">자료 검증</a></p>',
        '<table><thead><tr><th>솔버</th><th>문서 판본</th><th>목록 행</th><th>상세</th></tr></thead><tbody>']
    for d in solvers:
        k=d['key'];parts.append(f'<tr><td>{html.escape(k)}</td><td>{html.escape(d["versions"]["documentation"])}</td><td>{d["catalogue"]["entry_count"]}</td><td><a href="notes/{k}.md">노트</a> · <a href="solvers/{k}.json">근거/Q01–Q12</a> · <a href="catalogues/{k}.csv">전체 목록</a></td></tr>')
    parts+=['</tbody></table><h2>전체 목록에서 이름 찾기</h2><p><small>단순 파일 내 필터입니다. 공식 원문 전문은 포함하지 않습니다. 종류가 다른 행과 다른 버전을 합쳐 지원 수로 세지 않습니다.</small></p>',
        '<input id="q" placeholder="솔버, keyword/command 이름, 종류 검색" aria-label="목록 필터"><span id="n"></span>',
        '<table id="list"><thead><tr><th>솔버</th><th>이름</th><th>종류 · 조사 깊이</th><th>공식 locator</th></tr></thead><tbody>']
    for d in solvers:
        k=d['key'];source_by_id={s['id']:s for s in d['sources']}
        for row in csv.DictReader((ROOT/f'catalogues/{k}.csv').open()):
            name=row.get('name','');kind=row.get('kind',row.get('entry_kind',''))
            url=row.get('url') or row.get('official_url') or row.get('official_source_url') or ''
            src=source_by_id.get(row.get('source_id'),{})
            if not url:url=src.get('url','')
            depth=row.get('read_depth') or row.get('detail_review') or row.get('depth','')
            loc=row.get('locator') or row.get('printed_page') or row.get('pdf_page') or row.get('source_path') or row.get('archive_member') or '문서'
            if k=='dyna' and row.get('target_pdf_page'):url+='#page='+row['target_pdf_page']
            parts.append('<tr><td>'+html.escape(k)+'</td><td>'+html.escape(name)+'</td><td>'+html.escape(kind+' · '+depth)+'</td><td><a href="'+html.escape(url,quote=True)+'">'+html.escape(str(loc))+'</a></td></tr>')
    parts+=['</tbody></table><script>const rows=[...document.querySelectorAll("#list tbody tr")];const q=document.querySelector("#q"),n=document.querySelector("#n");function filter(){const s=q.value.trim().toLowerCase();let count=0;for(const r of rows){const visible=r.textContent.toLowerCase().includes(s);r.hidden=!visible;if(visible)count++}n.textContent=" "+count+"행"}q.addEventListener("input",filter);filter();</script></html>']
    (ROOT/'index.html').write_text('\n'.join(parts)+'\n')

def selected_files():
    roots=['assets','examples','catalogues','solvers','notes','discussion','scripts']
    files=[p for name in roots for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [ROOT/x for x in ['README.md','summary.json','index.html','validation.json','THIRD_PARTY.md']]
    return sorted(set(files))

def build():
    build_index()
    files=selected_files()
    missing=[str(p) for p in files if not p.is_file()]
    if missing:raise RuntimeError(missing)
    forbidden=[str(p) for p in files if 'tmp' in p.relative_to(ROOT).parts or p.suffix.lower() in ('.pdf','.exe','.dll','.zip')]
    if forbidden:raise RuntimeError(forbidden)
    manifest=[dict(file=str(p.relative_to(ROOT)),size_bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
    dump(ROOT/'files.json',manifest)
    out=ROOT.parent/'CAE-Solver-Input-Assets-20261030.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for p in files+[ROOT/'files.json']:z.write(p,p.relative_to(ROOT))
    with zipfile.ZipFile(out) as z:
        if z.testzip():raise RuntimeError('ZIP integrity error')
    print(json.dumps(dict(file=str(out),files=len(files)+1,uncompressed_bytes=sum(p.stat().st_size for p in files),zip_bytes=out.stat().st_size,sha256=hashlib.sha256(out.read_bytes()).hexdigest())))

if __name__=='__main__':build()
