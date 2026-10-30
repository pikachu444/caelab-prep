"""Assemble acquisition evidence, not a solver writer. Run from research root.

Requires the already downloaded sources and catalogues; never executes a solver.
"""
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
PIN = 'f51e9ffa74222f93750618d4766e59f2f96751c3'
REPO = 'https://github.com/SteveDoyle2/pyNastran'
ACQ = json.loads((ROOT/'tmp/opti-nastran/acquisition.json').read_text())
BY_KEY = {x['key']: x for x in ACQ}

def dump(path, obj):
    (ROOT/path).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')

def source(key, sid, title, locator, depth='relevant-sections'):
    row = BY_KEY[key]
    return dict(id=sid, url=row['url'], title=title, kind='manual',
                version='2025' if key.startswith('opti') else 'MSC Nastran 2024.2',
                locator=locator, access='downloaded', read_depth=depth,
                local_file=row['file'].removeprefix('solver-input-research/'),
                sha256=row['sha256'], size_bytes=row['size_bytes'],
                redistribution='locator-only',
                summary='공식 원본을 취득했다. 적힌 절만 독해했으며 전문을 재배포하지 않는다.')

PATHS = {
 'LICENSE.md':'LICENSE.md',
 'field_writer_8.py':'pyNastran/bdf/field_writer_8.py',
 'field_writer_16.py':'pyNastran/bdf/field_writer_16.py',
 'field_writer_double.py':'pyNastran/bdf/field_writer_double.py',
 'write_mesh.py':'pyNastran/bdf/bdf_interface/write_mesh.py',
 'bdf.py':'pyNastran/bdf/bdf.py',
 'test_solids.py':'pyNastran/bdf/cards/test/test_solids.py',
 'bdf_demo.rst':'docs/html_docs/quick_start/bdf_demo.rst',
}

def code_sources(key, start):
    rows=[]
    for i, m in enumerate(json.loads((ROOT/'assets/bdf/pynastran/files.json').read_text())):
        name=Path(m['file']).name
        rows.append(dict(id=f'{key}-D{start+i:02d}',url=f'{REPO}/blob/{PIN}/{PATHS[name]}',
            title='PyNastran '+name,kind='license' if name=='LICENSE.md' else 'code',
            version=PIN,locator=PATHS[name],access='downloaded',read_depth='relevant-sections',
            local_file=m['file'],sha256=m['sha256'],size_bytes=m['size_bytes'],
            redistribution='permitted-with-notice',
            summary='BSD-3-Clause 소스 일부. 전체 설치·실행 또는 솔버별 전수 지원 증거는 아니다.'))
    return rows

def code_asset(key, start):
    return dict(id=f'{key}-C01',source_ids=[f'{key}-D{i:02d}' for i in range(start,start+8)],
        role='writer',repository=REPO,revision=PIN,paths=list(PATHS.values()),
        scope='BDF mesh writer와 8/16/double formatter, reader 및 solid 작성 시험 소스',
        limits='reader whitelist 429개는 writer/MSC2024.2/OptiStruct2025 지원 목록이 아니다. 전체 패키지 의존성이 없고 실행하지 않았다. OptiStruct 별도 override도 전수 호환 보증이 아니다.',
        license='BSD-3-Clause; 원 LICENSE와 NOTICE 동봉',
        local_files=[x['file'] for x in json.loads((ROOT/'assets/bdf/pynastran/files.json').read_text())],
        executed=False)

def rule(key, number, qs, sids, text, locator, limit='', status='documented'):
    return dict(id=f'{key}-R{number:02d}',question_ids=qs,
        source_ids=[f'{key}-D{x:02d}' for x in sids],statement=text,locator=locator,
        examples=[],limits=limit,status=status)

def coverage(key, rules):
    return [dict(question_id=f'Q{i:02d}',
        rule_ids=[r['id'] for r in rules if f'Q{i:02d}' in r['question_ids']],
        status='partial' if i in (4,6,7,9,10,11,12) else 'documented',
        missing={4:'전수 필드·조건부·기본값 schema 미완성.',6:'모든 entry namespace와 중복/참조 규칙 전수 검토 없음.',
            7:'연결순서·면·법선 permutation 실행 검증 없음.',9:'모든 물리/접촉 조합 검토 없음.',
            10:'전체 해석 시퀀스/restart 파일 묶음 및 출력 조합 전수 검토 없음.',
            11:'공식 예제 취득 결과는 별도 manifest. 의도적 오류 입력·실행 oracle 미확보.',
            12:'모든 지원/비지원 조합 및 solver read/run 검증 없음.'}.get(i,'문서 근거이며 실행 검증은 아니다.'))
        for i in range(1,13)]

OPTI_SPECS = [
 ('opti-bulk','Bulk index','strong child links;597 entries','index-parsed'),
 ('opti-io','I/O index','strong child links;131 entries','index-parsed'),
 ('opti-subcase','Subcase index','strong child links;118 entries','index-parsed'),
 ('opti-param_bulk_r','PARAM options','261 option child links;1 navigation excluded','index-parsed'),
 ('opti-bulk-guidelines','Bulk syntax','Guidelines: format/continuation/numbers','relevant-sections'),
 ('opti-io-guidelines','I/O and subcase syntax','Guidelines: abbreviations/continuation/path','relevant-sections'),
 ('opti-input','Input file','I/O Options, Subcase Information, Bulk Data','relevant-sections'),
 ('opti-unit_systems_run_optistruct_r','Units','unit consistency;flexbody/CMS exceptions','relevant-sections'),
 ('opti-grid_bulk_r','GRID','definitions CP/CD/ID;comments','relevant-sections'),
 ('opti-ctria3_bulk_r','CTRIA3','format/node/property/orientation','relevant-sections'),
 ('opti-ctetra_bulk_r','CTETRA','definitions PID/Gi;ordering diagram','relevant-sections'),
 ('opti-mat1_bulk_r','MAT1','definitions;comments1–6','relevant-sections'),
 ('opti-pshell_bulk_r','PSHELL','material/thickness/property definitions','relevant-sections'),
 ('opti-psolid_bulk_r','PSOLID','material/property definitions','relevant-sections'),
 ('opti-spc_bulk_r','SPC','definitions;DOF/scalar/thermal restrictions','relevant-sections'),
 ('opti-force_bulk_r','FORCE','CID/vector/GSET;follower DOF restriction','relevant-sections'),
 ('opti-contact_bulk_r','CONTACT','PID/TYPE/AUTO/SSID/MSID definitions','relevant-sections'),
 ('opti-include_io_r','INCLUDE','search order/relative path/filemap/-incpath/.gz','relevant-sections'),
 ('opti-restart_io_r','RESTART','optimization .sh;not valid in analysis mode','relevant-sections'),
 ('opti-example_problems_os_r','Examples','chapter index','index-parsed'),
 ('opti-verification_problems_os_r','Verification problems','chapter index','index-parsed'),
]

def opti():
    key='optistruct'
    sources=[source(a,f'{key}-D{i:02d}',b,c,d) for i,(a,b,c,d) in enumerate(OPTI_SPECS,1)]
    sources+=code_sources(key,22)
    rules=[
      rule(key,1,['Q01'],[7],'I/O·Subcase·Bulk의 세 구역을 구분하고 BEGIN BULK로 유한요소 정의를 시작한다.','Input File:three sections'),
      rule(key,2,['Q02'],[5,6],'Bulk의 8/16자·comma free·이어쓰기 규칙과 I/O/Subcase의 약어·이어쓰기 규칙은 별도다.','Bulk Guidelines;I/O Guidelines','모든 예외를 formatter로 구현/실행하지 않았다.'),
      rule(key,3,['Q03'],[8],'기본은 일관된 단위 사용이며 DTI/UNITS의 특수 변환 문맥을 전역 자동변환으로 일반화하지 않는다.','Units:C​MS/flexbody'),
      rule(key,4,['Q04'],[11,12],'CTETRA.PID 생략은 EID를 사용한다. MAT1의 E/G/NU 공란은 조건부 계산이므로 0 대체가 아니다.','CTETRA.PID;MAT1 comments','나머지 entry 전체 조건부 schema 미검토.','partial'),
      rule(key,5,['Q05'],[18],'INCLUDE 삽입 위치와 검색 순서·상대경로·filemap·-incpath·압축 파일 처리를 보존해야 한다.','INCLUDE definitions/comments','플랫폼별 파일 탐색 실행 검증 없음.'),
      rule(key,6,['Q06'],[9,12,15,16],'숫자 ID·part-qualified 참조·선택 카드의 string label을 구분한다. 모든 ID 필드가 같은 문자열/정수 정책은 아니다.','GRID ID;MAT1 uniqueness;SPC/FORCE fully-qualified refs','전수 namespace schema 미완성.','partial'),
      rule(key,7,['Q07'],[10,11],'요소의 Gi 순서·차수·면/법선은 카드별 순서로 보존한다. 단순 node 목록 재정렬은 허용으로 보지 않는다.','CTRIA3/CTETRA format and ordering','원문 diagrams locator 확보;permutation 시험 없음.','partial'),
      rule(key,8,['Q08'],[9,11,12,13,14],'GRID→element→property→material 참조를 별도 객체로 매핑하고 좌표계 CP/CD를 구분한다.','GRID CP/CD;CTETRA PID;PSHELL/PSOLID MID'),
      rule(key,9,['Q09'],[15,16,17],'SPC의 물리별 DOF 규칙, FORCE의 CID/벡터·회전자유도, CONTACT의 PID/TYPE·AUTO 해석 제한을 보존한다.','SPC Comments;FORCE FLLW;CONTACT TYPE=AUTO','모든 접촉/하중 조합 검증 없음.','partial'),
      rule(key,10,['Q10'],[3,19],'RESTART I/O는 이전 최적화 .sh 상태를 쓰며 analysis mode용이 아니다. 입력 restart와 OS process cancel은 별개다.','RESTART comments','비선형 해석 restart 별도 옵션 전수 조사 없음.','partial'),
      rule(key,11,['Q11'],list(range(22,30)),'PyNastran의 formatter/writer·reader·시험 역할을 분리했다. solid 작성 시험은 완전 해석 deck의 수치 oracle이 아니다.','write_mesh.py;field_writer_*.py;test_solids.py;bdf_demo.rst','완전 패키지/외부 demo 모델 미포함;미실행.','partial'),
      rule(key,12,['Q12'],[1,2,3,4,27],'공식2025 색인 1107행과 PyNastran reader429개는 서로 다른 분모다. 전수 생성 지원을 뜻하지 않는다.','catalogue reconciliation;bdf.py cards_to_read','카드/옵션/해석별 지원 매트릭스 미완성.','partial'),
    ]
    summary=json.loads((ROOT/'tmp/opti-nastran/opti-index-summary.json').read_text())
    obj=dict(key=key,title='OptiStruct 입력 생성 자료',scope='2025 official Bulk/I/O/Subcase/PARAM indexes and selected generation rules; not a full field schema',
      versions=dict(documentation='2025',solver='OptiStruct2025;unexecuted',source='PyNastran '+PIN,examples='별도 example manifest',binary_tested=None),
      sources=sources,catalogue=dict(files=['catalogues/optistruct.csv'],source_ids=[f'{key}-D{i:02d}' for i in range(1,5)],
        scope='597bulk+131IO+118subcase+261PARAM option rows',entry_count=1107,count_unit='서로 다른 종류의 공식 child-link 행',
        completeness='complete-index',sections=summary,reconciliation='4개 child-link 영역의 strong anchor 전수 추출/중복 대조. PARAM navigation1개 제외. 별도 independent numeric index는 없음.',
        full_field_review_complete=False),rules=rules,examples=[],code_assets=[code_asset(key,22)],coverage=coverage(key,rules),
      acquisition_log=[dict(target=x['url'],outcome='downloaded' if x['success'] else x.get('error','failed')) for x in ACQ if x['key'].startswith('opti')],
      gaps=['모든 field/conditional/dependency metadata 또는 제품 생성기 완성 아님.','공식 상용 문서/예제는 원문 재배포 제외.','전체 continuation/숫자 정밀도/요소 순서/경로 실행 검증 없음.','공식 완전 예제 및 오류 예제 취득 상태는 별도 manifest로 표시.'],runtime_verified=False,collected_on='2026-10-30')
    manifest=ROOT/'tmp/opti-nastran/pages-manifest.json'
    if manifest.exists():
        rows=json.loads(manifest.read_text())
        read_urls={s['url'] for s in sources if s['read_depth']=='relevant-sections'}
        for row in rows:
            if row['url'] in read_urls:
                row['read_depth']='relevant-sections'
        obj['page_acquisition']=dict(manifest='catalogues/optistruct-pages.json',attempted=len(rows),downloaded=sum(bool(x.get('acquired')) for x in rows),failed=sum(not x.get('acquired') for x in rows),read_depth='not-read except individually identified relevant sections')
        dump('catalogues/optistruct-pages.json',rows)
        with (ROOT/'catalogues/optistruct.csv').open(newline='') as stream:
            cat=list(csv.DictReader(stream))
        for row in cat:
            if row['url'] in read_urls:
                row['read_depth']='relevant-sections'
        with (ROOT/'catalogues/optistruct.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(cat[0]));writer.writeheader();writer.writerows(cat)
    example_manifest=ROOT/'catalogues/bdf-examples.json'
    if example_manifest.exists():
        obj['supplementary_examples_manifest']='catalogues/bdf-examples.json'
        extra=json.loads(example_manifest.read_text())
        by_name={}
        for i,x in enumerate(extra['raw_acquisitions'],30):
            if not x.get('local_file'):
                continue
            sid=f'{key}-D{i:02d}'
            sources.append(dict(id=sid,url=x['url'],title='Official example acquisition '+Path(x['local_file']).name,
                kind='example',version='2025 distribution;deck header version recorded separately',
                locator=x.get('locator','Model Files;archive member in bdf-examples.json'),access='downloaded',
                read_depth=x.get('read_depth','relevant-sections'),local_file=x['local_file'],
                sha256=x['sha256'],size_bytes=x['size_bytes'],redistribution='locator-only',
                summary='실제 예제/설명 취득. ZIP 내부 각 deck 해시는 별도 manifest이며 미실행이다.'))
            by_name[Path(x['local_file']).name]=sid
        for i,e in enumerate(extra['examples'],1):
            obj['examples'].append(dict(id=f'{key}-E{i:02d}',source_ids=[by_name[n] for n in e['archive_names']],
                url=e['source_page'],file=None,analysis_local_files=[d['local_file'] for d in e['deck_members']],
                sha256=None,version=e['version'],kind='official-deck',purpose=e['purpose'],expected=e['expected'],
                license=e['rights'],redistribution='locator-only',solver_executed=False,
                standalone_input_observed=e['complete_input_observed'],dependency_review=e['dependency_review'],
                members=e['deck_members']))
    return obj

def nastran():
    key='nastran'
    src=source('nastran-qrg',key+'-D01','MSC Nastran 2024.2 Quick Reference Guide',
       '3143 PDF pages;2196 bookmarks. Read physical pages131,175,209,1056,1061,1285,1558,1686,1960,2036,2650,2672,2855,3022;CTETRA diagram visually inspected.')
    src['pdf_page_count']=3143
    shell=source('nastran-bulk',key+'-D02','Legacy Nexus bulk entry HTML shell','JS shell only','metadata-only')
    shell['summary']='HTML 응답은 JS shell이므로 원문 독해 근거로 사용하지 않았다. 공식 PDF를 대신 취득했다.'
    sources=[src,shell]+code_sources(key,3)
    def r(n,qs,text,loc,limit='',sids=[1],status='documented'):
        return rule(key,n,qs,sids,text,loc,limit,status)
    rules=[
      r(1,['Q01'],'Executive SOL/CEND, Case Control, BEGIN BULK/ENDDATA와 선택적 FMS를 구분한다.','QRG sections3–5/9;p131 example'),
      r(2,['Q02'],'Bulk는 small8/large16/free 형식과 전용 이어쓰기 규칙을 가진다. real과 integer 표기도 구분한다.','PDF1056,1061;printed1019+','모든 precision/continuation 예외 미검토.'),
      r(3,['Q03'],'일반 입력은 일관된 단위를 사용하며 DTI,UNITS 특수 변환 문맥은 별도다.','PDF1686;DTI,UNITS'),
      r(4,['Q04'],'MSC CTETRA의 PID는 필수다. OptiStruct2025의 EID 기본값을 가져오면 안 된다.','PDF1558;printed1520;CTETRA.PID','전수 defaults/conditional schema 미완성.',status='partial'),
      r(5,['Q05'],'INCLUDE는 어디든 가능하며 중첩은 최대10, 경로 행은72자 제한이다.','PDF131;printed99;INCLUDE remarks','설치/플랫폼별 실제 탐색은 미실행.'),
      r(6,['Q06'],'GRID ID/CP/CD와 property/material 참조·중복 정책을 분리한다.','PDF1960 GRID;2672 PSOLID','모든 namespace/duplicate 처리 전수 대조 없음.',status='partial'),
      r(7,['Q07'],'CTETRA Gi4–10 순서/차수와 원문 node diagram을 보존한다.','PDF1558 CTETRA figure','그림 실제 확인. 면/법선 permutation 실행 없음.',status='partial'),
      r(8,['Q08'],'GRID→CTETRA→PSOLID→material 참조를 매핑한다. PSOLID의 물리·재료·SOL 제한도 필요하다.','PDF1558;1960;2672'),
      r(9,['Q09'],'SPC/LOAD 정의와 case의 선택은 다르며, SPC DOF 상호배타 집합 및 접촉의 SOL별 제약을 유지한다.','PDF209 Case;1285 BCTABLE;2036 FORCE;2855 SPC','전수 하중/접촉 옵션 검토 없음.',status='partial'),
      r(10,['Q10'],'SOL/Case/TSTEP·출력 선택을 구분한다. transient 시간 정의는 선택 참조가 필요하다.','PDF175 SOL;209 Case;3022 TSTEP','restart FMS/state bundle 전수 검토 없음;process cancel 검증 아님.',status='partial'),
      r(11,['Q11'],'공개 PyNastran은 BDF writer/formatter와 reader·작성 시험 소스를 제공한다. 시험/mesh dump를 완전 해석 deck으로 부르지 않는다.','PyNastran pinned paths','솔버 독립 실행·완전 analysis golden 아님.',list(range(3,11)),status='partial'),
      r(12,['Q12'],'공식 QRG 전체 북마크2196개와 분류 entry1879행을 보존했다. appendices/item code/DOF표를 전부 keyword로 정규화하지 않았다.','QRG outline;catalogue sections2–6/9','다른 Nastran 계열/2025이상/전체 해석 지원으로 일반화하지 않는다.',status='partial'),
    ]
    summary=json.loads((ROOT/'tmp/opti-nastran/nastran-index-summary.json').read_text())
    obj=dict(key=key,title='MSC Nastran 입력 생성 자료',scope='MSC Nastran2024.2 QRG;not NX/Autodesk/NASA distribution or all Nastran dialects',
      versions=dict(documentation='MSC Nastran2024.2 QRG;PDF creation2024-11-21',solver='MSC Nastran2024.2;unexecuted',source='PyNastran '+PIN,examples='별도 example manifest',binary_tested=None),
      sources=sources,catalogue=dict(files=['catalogues/nastran.csv','catalogues/nastran-outline.csv'],source_ids=[key+'-D01'],
        scope=summary['scope'],entry_count=1879,count_unit='설정·entry·option topic 혼합 bookmark 행;고유 keyword 수 아님',
        completeness='complete-outline;scoped-entry-index',sections=summary['sections'],all_outline_records=2196,
        reconciliation='모든 북마크2196개 저장. 본문 주장별 chapter/depth/page 필터로1879행 분류. Chapter7item codes/8DOF/appendices는 entry목록 밖에 남긴다.',full_field_review_complete=False),
      rules=rules,examples=[],code_assets=[code_asset(key,3)],coverage=coverage(key,rules),
      acquisition_log=[dict(target=x['url'],outcome='downloaded;PDF3143pages' if x['key']=='nastran-qrg' else 'downloaded but JS shell') for x in ACQ if x['key'].startswith('nastran')]+[dict(target='web PDF reader',outcome='size>10MiB failed;direct official PDF download succeeded')],
      gaps=['QRG 원본 확보와 전수 field schema는 별개.','공식 완전 example/의도적 오류 deck 확보 상태는 별도 manifest;solver read/run 없음.','전체 appendix/options/sequence별 의미는 전수 검토하지 않았다.','MSC2024.2 문서를 다른 Nastran dialect나 최신판 지원으로 부르지 않는다.','상용 QRG 원문/스크린샷은 배포하지 않는다.'],runtime_verified=False,collected_on='2026-10-30')
    path=ROOT/'catalogues/nastran-examples.json'
    if path.exists():
        extra=json.loads(path.read_text());obj['supplementary_examples_manifest']='catalogues/nastran-examples.json'
        for i,x in enumerate(extra['sources'],11):
            sources.append(dict(id=f'{key}-D{i:02d}',url=x['url'],title='NASA NASTRAN95 '+x['upstream_path'],
                kind='example' if not x['upstream_path'].startswith('NASA Open') else 'license',
                version='NASA NASTRAN95;'+extra['revision'],locator=x['upstream_path'],access='downloaded',
                read_depth='relevant-sections' if x['upstream_path'].endswith(('.inp','.txt','.out')) else 'metadata-only',
                local_file=x['local_file'],sha256=x['sha256'],size_bytes=x['size_bytes'],redistribution='locator-only',
                summary='NASA95 참고자료이며 MSC2024.2에 대한 실행·호환 증거가 아니다.'))
        for i,e in enumerate(extra['selected_examples'],1):
            obj['examples'].append(dict(id=f'{key}-E{i:02d}',source_ids=[f'{key}-D{j:02d}' for j in (13,14,15)],
                url=extra['sources'][2]['url'],file=None,analysis_local_files=[e['input'],e['description'],e['reference_output']],
                sha256=extra['sources'][2]['sha256'],version='NASA NASTRAN95;not MSC2024.2',kind='official-deck',
                purpose=e['purpose'],expected=e['expected'],license=e['rights'],redistribution='locator-only',solver_executed=False,
                msc2024_2_verified=False,dependencies=e['dependencies']))
        obj['gaps'].append('NASA95 완전 사례와 archival output 확보는 MSC2024.2 공식 완전 사례 확보나 실행 검증을 대체하지 않는다.')
    return obj

if __name__=='__main__':
    for obj in [opti(),nastran()]:
        dump(f"solvers/{obj['key']}.json",obj)
        print(obj['key'],len(obj['sources']),obj['catalogue']['entry_count'],len(obj['rules']))
