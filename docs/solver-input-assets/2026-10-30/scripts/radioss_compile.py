"""Compile inspected Radioss research records. Does not run a solver or generator."""
from pathlib import Path
from urllib.parse import urldefrag
import csv, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / 'tmp/radioss'
OUT = ROOT / 'solvers/radioss.json'
BASE = 'https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/'
REV = 'cb760c206e346eff12161a2268b134ef9d48a4ef'
TREV = '1b6bb9200ee7dca899e61c18bd982c3fb1c72fd1'
REPO = 'https://github.com/OpenCourant/OpenCourant'
TOOLS = 'https://github.com/OpenCourant/Tools'
acqs = json.loads((TMP / 'acquisitions.json').read_text())
bykey = {r['key']: r for r in acqs}
sources = []
ids = {}

def meta(path):
    p = ROOT / path
    b = p.read_bytes()
    return {'local_file': path, 'sha256': hashlib.sha256(b).hexdigest(), 'size_bytes': len(b)}

def source(sid, key, title, locator, summary, depth='relevant-sections', version='Radioss 2024', kind='manual'):
    a = bykey[key]
    item = {'id':sid, 'url':a['url'], 'title':title, 'kind':kind, 'version':version,
            'locator':locator, 'access':'downloaded', 'read_depth':depth,
            'redistribution':'locator-only', 'summary':summary}
    item.update(meta(str(Path(a['file']).relative_to(ROOT))))
    sources.append(item); ids[key] = sid
    return sid

source('radioss-D01','starter2024','Starter Input','Supported Keywords 전체 섹션','2024 Starter 원문 링크 590행을 보존했다.', 'index-parsed', kind='index')
source('radioss-D02','engine2024','Engine Input','Supported Keywords 전체 섹션','2024 Engine 원문 링크 235행을 보존했다.', 'index-parsed', kind='index')
source('radioss-D03','syntax2024','Starter Keyword Syntax','Block Format / Keyword Options / Comments / Integer / Real / Booleans','블록·필드 형식과 정의/참조 구분, 공란·0의 기본값 의미를 읽었다.')
source('radioss-D04','reference2022','Altair Radioss 2022 Reference Guide','PDF 3550쪽 중 인쇄 쪽 40–41 Keyword Syntax를 허용된 이미지 출력으로 읽음','원본 취득. copy=no이므로 텍스트 추출하지 않았다. PDF 전체 독해가 아니다.', version='Radioss 2022', kind='manual')
source('radioss-D05','starter-current','Starter Input, current rolling edition','2026 banner / Supported Keywords 전체 섹션','2026 Starter 비교 목록 614행. 2024와 합산하지 않는다.','index-parsed','Radioss 2026, acquired 2026-10-30','index')
source('radioss-D06','engine-current','Engine Input, current rolling edition','2026 banner / Supported Keywords 전체 섹션','2026 Engine 비교 목록 241행. 대상 solver 지원표로 간주하지 않는다.','index-parsed','Radioss 2026, acquired 2026-10-30','index')
source('radioss-D07','engine-syntax2024-correct','Engine Keywords Syntax','본문 전체','Engine 자유 형식과 /RUN·/VERS 의무 설명을 확인했다.')
source('radioss-D08','include2024','#include','Format / Definition / Comments 전체','whole block, 경로 기준, 헤더·버전 제약을 읽었다.')
source('radioss-D09','files2024','Radioss Files','Input Format / Version 12.0 and After','입력·restart·결과·제어 파일의 생산자/소비자를 구분했다.')
source('radioss-D10','single-input2024-correct','Single File Input','본문과 Comments 전체','통합 파일은 Engine 앞부분, /END/ENGINE, Starter /BEGIN–/END로 구분한다.')
source('radioss-D11','enddata2024','#enddata','본문 전체','include 종료와 /END의 역할을 구분한다.')

selected = [
 ('begin_starter_r','/BEGIN','Format / Definition: Invers와 입력/작업 단위 / Comments','입력 형식판과 입력/작업 단위를 구분했다.'),
 ('node_starter_r','/NODE','Format / Definition / Comments 전체','node ID와 세 좌표의 반복 행 형식을 읽었다.'),
 ('part_starter_r','/PART','Format / Definition / Comments 전체','파트의 동종 요소 및 material/property/subset 참조와 composite 예외를 읽었다.'),
 ('sh3n_starter_r','/SH3N','Format / Definition / Comments / Figure 1','삼각 shell 연결·두께 상속과 국부 축 그림을 읽었다.'),
 ('shell_starter_r','/SHELL','Format / Definition / Comments / Figure 1','사각 shell 연결·두께 상속과 국부 축 그림을 읽었다.'),
 ('brick_starter_r','/BRICK','Format / Definition / Comments 전체; 도형 전체는 독해하지 않음','여덟 node, 요소 family ID와 조건별 퇴화 표현을 읽었다.'),
 ('tetra4_starter_r','/TETRA4','Format / Definition / Comments / Figure 1','4node tetra의 part 분리와 node 순서 그림을 읽었다.'),
 ('surf_seg_starter_r','/SURF/SEG','Format / 2D format / Definition / Comments 전체','surface segment의 연결·삼각형 fourth-node 생략과 요소 소속 제약을 읽었다.'),
 ('surf_part_starter_r','/SURF/PART','Format / Definition / Comments 전체','surface part 부호에 의한 normal 반전과 3D variant 필요를 읽었다.'),
 ('grnod_starter_r','/GRNOD','Input Type Keywords / Comments','선택 방식별 node group과 정렬 보존 variant를 구분했다.'),
 ('funct_starter_r','/FUNCT','Format / Definition / Comments 전체','엄격 증가 abscissa, 외삽과 TABLE 공유 ID 제약을 읽었다.'),
 ('bcs_starter_r','/BCS','Format / Trarot definition / Comments','자유도별 고정 코드와 mandatory node-group 참조를 읽었다.'),
 ('cload_starter_r','/CLOAD','Format / Definition / Comments 전체','그룹 전체 값과 node당 하중을 구분하고 curve/skew/sensor 참조를 읽었다.'),
 ('inivel_starter_r','/INIVEL','Format / Definition / Comments 전체','재료/격자 및 회전 속도의 차이와 node group 의무를 읽었다.'),
 ('skew_fix_starter_r','/SKEW/FIX','Format / Definition / Comments 전체','SKEW/FRAME ID 공유 제약과 Y/Z 벡터로 축을 만드는 규칙을 읽었다.'),
 ('submodel_starter_r','//SUBMODEL','Format / Definition / Comments 전체','ID offsets, 중첩·버전·단위·지원 제한과 Engine 참조 규칙을 읽었다.'),
 ('transforms_overview_starter_r','Transforms','Comments 전체 / variant 목록','순서 의존과 node-only 대 submodel 전체 변환 범위를 구분했다.'),
 ('parameter_starter_r','/PARAMETER','Format / Definition / Comments 중 scope/name/reference/expression dependency','공란 정렬과 global/local scope, 평가 순서·외부 templex 의존을 읽었다. 예제 전수 독해는 아니다.'),
 ('mat_law1_elast_starter_r','/MAT/LAW1 (ELAST)','Format / Definition / Comments 전체','별칭과 밀도·탄성값, 요소/파괴모델의 조건을 읽었다.'),
 ('mat_law36_plas_tab_starter_r','/MAT/LAW36 (PLAS_TAB)','Format 전체 / Nfunct Definition / Comments 중 곡선 및 strain-rate 규칙','조건부 반복 card 수와 곡선 의존을 읽었다. 모든 재료 field의 전수 표 작성은 아니다.'),
 ('prop_type1_shell_starter_r','/PROP/TYPE1 (SHELL)','Format / Ishell·Ismstr Definition / Comments 1–4','/DEF_SHELL 상속과 formulation/material 호환 조건을 읽었다. 전 field 독해는 아니다.'),
 ('prop_type14_solid_starter_r','/PROP/TYPE14 (SOLID)','Format / Isolid Definition / Comments 중 material-dependent defaults','조건부 Sol2SPH 행, /DEF_SOLID 상속과 재료별 default를 읽었다. 전 field 독해는 아니다.'),
 ('inter_type7_starter_r','/INTER/TYPE7','Description / Format 전체 / group·surface Definition / Comments 첫 항목','group→surface 접촉과 조건부 추가 행, edge-edge 한계를 읽었다. 모든 접촉 수치식은 검토하지 않았다.'),
 ('inter_type24_starter_r','/INTER/TYPE24','Description / Format / Comments 1','자기접촉/양방향/노드 대 면의 참조 조합과 SMP implicit 제한을 읽었다.'),
 ('run_engine_r','/RUN','Format / Definition / Comments 전체','최종시간과 run/restart 파일 참조를 읽었다.'),
 ('vers_engine_r','/VERS','Format / Definition / Comments 전체','Engine 입력판과 Starter 판 일치 요구를 읽었다.'),
 ('rfile_n_engine_r','/RFILE/n','Format / Definition / Comments 전체','restart 파일 주기·순환 개수와 letter 선택을 읽었다.'),
 ('stop_engine_r','/STOP','Description / Format / Definition 중 Emax와 기본값','에너지·질량 기준의 solver 내부 종료이며 외부 process cancel은 아니다.'),
 ('tfile_engine_r','/TFILE','Format / Definition / Comments 전체','출력 시간 간격·형식과 /TH 요청을 구분했다.'),
 ('anim_dt_engine_r','/ANIM/DT','Format / Definition / Comments 전체','animation 시작/빈도/종료 요청을 읽었다.'),
 ('impl_linear_engine_r','/IMPL/LINEAR','본문 전체','선형 정적·모드·좌굴의 implicit 활성 명령을 확인했다.'),
 ('impl_dtini_engine_r','/IMPL/DTINI','Format / Definition / Comments 전체','비선형 implicit 초기 loading increment와 시간을 구분했다.'),
 ('impl_dt_1_engine_r','/IMPL/DT/1','Format / Definition 중 iteration 기반 time-step 증감','적응 increment 제어를 확인했다. implicit 전체 생성법은 아니다.'),
]
for i,(name,title,locator,summary) in enumerate(selected,20):
    key=name if name in bykey else None
    if key:
        source(f'radioss-D{i:02}',key,title,locator,summary)
    else:
        p=Path('tmp/radioss/keywords2024')/(name+'.htm')
        sid=f'radioss-D{i:02}'
        sources.append({'id':sid,'url':BASE+name+'.htm','title':title,'kind':'manual','version':'Radioss 2024','locator':locator,'access':'downloaded','read_depth':'relevant-sections','redistribution':'locator-only','summary':summary,**meta(str(p))})
        ids[name]=sid

codefiles = [
 ('radioss-D80','OpenCourant-LICENSE.md','LICENSE.md','AGPL-3.0-or-later license','license'),
 ('radioss-D81','OpenCourant-COPYRIGHT.md','COPYRIGHT.md','OpenCourant file-scope copyright and exceptions','license'),
 ('radioss-D82','Tools-Copyright.md','Copyright.md','MIT license, OpenCourant Tools','license'),
 ('radioss-D83','inp2rad.py','input_converters/inp2rad/inp2rad/inp2rad.py','INP to Radioss converter','code'),
 ('radioss-D84','inp2rad-README.md','input_converters/inp2rad/README.md','inp2rad support scope and beta limits','code'),
 ('radioss-D85','radiossblk.cxx','reader/source/io/model_readers/radioss/radiossblk/radiossblk.cxx','CFG-backed Radioss reader front end','code'),
 ('radioss-D86','mec_data_writer.cpp','reader/source/cfgio/MODEL_IO/mec_data_writer.cpp','Generic CFG-driven data writer','code'),
 ('radioss-D87','mec_single_file_writer.cpp','reader/source/cfgio/MODEL_IO/mec_single_file_writer.cpp','Buffered formatted output context','code'),
 ('radioss-D88','verify_results.py','qa-tests/qa_tools/verify_results.py','Upstream engine-result regression comparator','code'),
]
for sid,local,path,title,kind in codefiles:
    ist = sid in ('radioss-D82','radioss-D83','radioss-D84')
    repo,rev=(TOOLS,TREV) if ist else (REPO,REV)
    locator={'radioss-D83':'convert_nodes 174–186; material conversion 636–1395; write_parts 2355–2373; write_props 2379–2478; convert_elements 2947–3215; write_output 6202–6721; CLI radversion choices',
     'radioss-D85':'GetCurrentRadiossStrVersion; CFG profile initialization 423–455; CommonDataReaderCFG.ReadModel 479–481',
     'radioss-D86':'WriteObjectData 243/253; ComputeValidCards 636; WriteCard 794; WriteSingleCard 1763; WriteIfCard 2856; WriteIfCell 3073',
     'radioss-D87':'file header; class constructor, WriteFile and RemoveBlankEnd',
     'radioss-D88':'extract_engine_results 29; extract_reference 104; compute_tolerance 131; compare 222'}.get(sid,'file notice / README complete relevant text')
    sources.append({'id':sid,'url':f'{repo}/blob/{rev}/{path}','title':title,'kind':kind,'version':rev,'locator':locator,'access':'downloaded','read_depth':'relevant-sections','redistribution':'permitted-with-notice','summary':'원문 파일과 저작권 문구를 보존했다. 선택한 함수·관련 절만 읽었으며 빌드/실행하지 않았다.',**meta('examples/radioss/code/'+local)})
source('radioss-D89','oc-source-archive','OpenCourant release source archive','latest-20261011 commit archive; 10563 files','고정 commit 소스 원본을 내부 취득했다. archive 안의 파일별 예외를 분리했다.','metadata-only',REV,'code')
source('radioss-D90','ocdownload','OpenCourant downloads','release / platform links','선택한 release와 프로젝트의 공식 배포 경로를 확인했다. 바이너리는 시험하지 않았다.','relevant-sections','acquired 2026-10-30','api')
source('radioss-D91','new-keywords2026','New and modified keywords in Radioss 2026','new/modified keyword headings','2026 문서와 2024 문서의 판 차이를 확인했다.','relevant-sections','Radioss 2026','manual')

def mdsource(sid,path,title,kind,locator,summary):
    sources.append({'id':sid,'url':f'{REPO}/tree/{REV}/{path}','title':title,'kind':kind,'version':REV,'locator':locator,'access':'downloaded','read_depth':'relevant-sections','local_file':'tmp/radioss/oc-source-archive.zip','sha256':hashlib.sha256((TMP/'oc-source-archive.zip').read_bytes()).hexdigest(),'size_bytes':(TMP/'oc-source-archive.zip').stat().st_size,'redistribution':'locator-only','summary':summary})
mdsource('radioss-D92','hm_cfg_files','HyperMesh/reader CFG descriptors','code','Radioss inventory 1333 files; sample begin/tetra4/2025 shell-solid ATTRIBUTES, DEFAULTS, FORMAT/HEADER/CARD','1331개 파일에 OpenRadioss 한정 사용 및 변경 제공 조건이 보인다. repository AGPL을 이 파일들에 덮어 적용하지 않았다.')
mdsource('radioss-D93','qa-tests/miniqa','OpenCourant upstream QA model and reference corpus','example','166 .rad files in acquired archive; 5 case groups selected and read','모델의 file-level CC BY-NC 표시와 회귀 reference를 분리했다. 이 연구에서 solver를 실행하지 않았다.')
sources.append({'id':'radioss-D94','url':f'{TOOLS}/blob/{TREV}/userlib_sdk/examples/USER_material_laws_for_solids_and_shells/Solids/small_plast_0000.rad','title':'Tools SDK small_plast USER01 example','kind':'example','version':TREV,'locator':'file header; /BEGIN2022; /MAT/USER01; paired0001 Engine','access':'downloaded','read_depth':'relevant-sections','redistribution':'locator-only','summary':'실제 모델을 취득했다. code MIT와 별개로 모델 header가 CC BY-NC4.0이므로 deck bytes를 배포하지 않는다.',**meta('tmp/radioss/tools-small-plast-0000.rad')})

rules=[]
def rule(n,qs,s,statement,locator,limits='',status='documented',examples=None):
    ss=[ids.get(x,x) for x in s]
    rules.append({'id':f'radioss-R{n:02}','question_ids':qs,'source_ids':ss,'statement':statement,'locator':locator,'examples':examples or [],'limits':limits or 'Radioss 2024 문서 규칙이며 고정 OpenCourant release에서 실행 검증하지 않았다.','status':status})
rule(1,['Q01','Q12'],['files2024','begin_starter_r'],'현재 계열은 model_0000.rad Starter와 model_0001.rad 이후 Engine 입력을 구분한다. /BEGIN의 Invers는 문서 입력 형식판이며 제품 release/코드 commit과 동일한 값이 아니다.','Files: Input Format, Version 12.0 and After; /BEGIN: Invers','공식 문서의 상향 호환 설명을 OpenCourant의 전 keyword 지원 보증으로 확대하지 않는다.')
rule(2,['Q01','Q02'],['syntax2024','enddata2024'],'분리 Starter는 #RADIOSS STARTER 헤더, /BEGIN 및 최종 /END 경계를 가진다. 슬래시 블록은 다음 블록에서 끝난다. #enddata는 include 잔여 부분의 종료이다.','Starter Keyword Syntax: Block Format; #enddata: Comments','PARAMETER의 /BEGIN 앞 정의 등 별도 규칙이 있으므로 일반 헤더 설명만으로 모든 입력 행의 순서를 결정하지 않는다.')
rule(3,['Q01','Q05'],['single-input2024-correct'],'통합 입력은 Engine 옵션을 먼저 두고 /END/ENGINE으로 닫은 뒤 /BEGIN–/END Starter를 둔다. Engine 옵션은 main 파일에 두며 Engine include와 다중 Engine instance는 이 방식에서 지원하지 않는다.','Single File Input: syntax and Comments')
rule(4,['Q02','Q04'],['syntax2024','radioss-D04'],'Starter의 기본 행 길이는 100자이며 기본 격자는 10자 열이다. 일반 integer/real 설명과 Boolean 특수 위치를 구분한다. reserved 빈 열에 설명문을 넣지 않는다. #/$ 첫 열 주석에는 특수 header/directive 예외가 있다.','2024 Starter Keyword Syntax; 2022 PDF pp40–41','일부 keyword는 ID 최대10자리, 일반 integer 절은 최대9자리로 적는다. 인코딩·수치 exponent/overflow·모든 예외는 reader와 추가 대조가 필요하다.','partial')
rule(5,['Q02','Q04','Q10'],['engine-syntax2024-correct','vers_engine_r'],'Engine은 100자 이내 자유 형식, 변수 간 공백, 모든 변수를 적는 방식이다. 문서는 /RUN과 /VERS를 의무로 적고 Engine/Starter 형식판의 일치를 요구한다.','Engine Keywords Syntax 전체; /VERS Comments','선택한 공식 QA/Tools converter 중 /VERS 생략 사례가 있다. 생략 허용/호환 fallback은 고정 release에서 미검증이다.','partial')
rule(6,['Q03'],['begin_starter_r'],'/BEGIN은 입력 질량·길이·시간과 작업 단위를 구분한다. Starter가 입력을 작업 단위로 변환하며 Engine에서는 단위 변환하지 않고 결과는 작업 단위다. 입력 단위를 생략하면 작업 단위를 따른다.','/BEGIN: Definition and Comments on input/work units')
rule(7,['Q04'],['syntax2024','mat_law1_elast_starter_r','mat_law36_plas_tab_starter_r'],'공란 또는 0은 각 keyword가 정한 default를 활성화할 수 있으므로 미기입/실제0/상속을 독립 의미로 관리해야 한다. LAW1/ELAST, LAW36/PLAS_TAB과 같은 이름 별칭을 원문과 연결한다.','Starter Keyword Syntax: Comments; material Format','전체 825행의 별칭·조건별 default를 전수 정규화한 schema가 아니다.')
rule(8,['Q04','Q08'],['prop_type1_shell_starter_r','prop_type14_solid_starter_r'],'SHELL/SOLID formulation의 0은 /DEF_SHELL·/DEF_SOLID 상속을 뜻할 수 있고 SOLID 일부 default는 material law에 의존한다. Sol2SPH 추가 행 등 조건에 따라 실제 card 수가 달라진다.','PROP TYPE1: Ishell, Ismstr; TYPE14: Format and Isolid comments','예시 formulation만 읽었다. 모든 property/material 조합의 허용표를 만들지 않았다.','partial')
rule(9,['Q04','Q09'],['mat_law36_plas_tab_starter_r'],'LAW36의 Nfunct>0에서는 function ID·scale·strain-rate 각 목록을 5개 단위로 반복한다. strain-rate는 증가 순서이며 function의 첫 plastic-strain 값과 외삽 의미를 검토해야 한다.','LAW36 Format; Nfunct; Comments on curves','재료 전체 field 및 모든 failure/strain-rate 조건은 미검토다.','partial')
rule(10,['Q05'],['include2024'],'#include는 완전한 블록만 포함하며 main 헤더를 포함시킬 수 없다. 상대 경로는 작업 디렉터리 기준이다. filename 공백과 500자 directive 제한, main format 일치와 #enddata 처리를 보존한다.','include Comments 전체','중첩 시 include 파일 자체 디렉터리 기준으로 임의 변경하면 안 된다.')
rule(11,['Q05','Q06'],['parameter_starter_r'],'GLOBAL/LOCAL parameter의 scope와 이름 대소문자, 왼쪽 정렬·치환 폭을 보존한다. expression 인수는 앞에서 정의해야 하고 공식 문서는 평가에 외부 templex 실행파일을 요구한다.','PARAMETER Format/Definition/Comments: names, references, expression order','OpenCourant 배포에서 templex 기능의 제공·대체 여부는 미검증이다.','partial')
rule(12,['Q05','Q06','Q08'],['submodel_starter_r'],'//SUBMODEL은 namespace별 ID offset과 별도 입력판/단위를 가질 수 있다. //ENDSUB가 필요하며 중첩의 제한·무시/비호환 옵션이 있다. Engine의 entity 참조는 적용 후 offset ID를 사용한다.','SUBMODEL Definition and Comments 전체','큰 다중파트 모델의 ID 재할당 구현이나 충돌검사는 수행하지 않았다.')
rule(13,['Q05','Q07','Q09'],['transforms_overview_starter_r'],'TRANSFORM은 기록 순서대로 적용한다. node-group 대상은 좌표만 바꾸며 초기 상태·재료 방향·BC 전체 변환은 되지 않는다. 문서는 전체 변환을 위해 submodel 참조를 권한다.','Transforms Comments','모든 variant의 mirror handedness·하위 객체 변환을 전수 검토하지 않았다.','partial')
rule(14,['Q06','Q08'],['syntax2024','part_starter_r','shell_starter_r'],'option ID의 정의와 reference ID를 분리한다. SHELL의 part_ID는 PART 참조이며 PART를 정의하지 않는다. 다른 PART가 같은 material/property를 공유할 수 있다.','Keyword Options / PART Comments / SHELL Format')
rule(15,['Q06','Q07'],['sh3n_starter_r','shell_starter_r','brick_starter_r','tetra4_starter_r'],'element ID는 family 안에서 유일해야 하며 문서는 전체 모델 고유 번호를 권한다. TETRA4의 part_ID는 BRICK 및 TETRA10과 분리한다.','각 element Comments','모든 family의 정확한 namespace 통합표나 32/64bit ID 한계는 미확정이다.','partial')
rule(16,['Q07'],['node_starter_r','sh3n_starter_r','shell_starter_r','tetra4_starter_r','brick_starter_r'],'NODE 좌표와 요소별 연결 순서를 따로 저장한다. SH3N/SHELL/TETRA4 그림에서 node 순서와 국부 축을 확인했다. 퇴화 BRICK 허용은 formulation별 제한이 있어 모든 wedge/tet을 같은 node 반복으로 바꾸면 안 된다.','NODE Format; SH3N/SHELL/TETRA4 Figure1; BRICK Comments','고차 요소, 모든 face 번호, 모든 BRICK 도형과 퇴화 조건 전수는 미검토다. mesh 외부 포맷 순서를 native 순서로 가정하지 않는다.','partial')
rule(17,['Q07','Q08','Q09'],['surf_seg_starter_r','surf_part_starter_r'],'SURF/SEG은 요소에 속한 node로 segment를 구성하며 삼각형은 네 번째 node를 생략할 수 있다. SURF/PART의 음수 part 참조는 normal을 뒤집고 solid는 EXT/ALL variant가 필요하다.','SURF/SEG Comments; SURF/PART Comments','face/normal의 모든 접촉·압력 조건은 미검토다.','partial')
rule(18,['Q08'],['part_starter_r'],'PART는 같은 요소 종류·material/property를 갖는 동종 집합이다. composite property/ply material은 PART의 단순 mat_ID와 다른 의미를 가지며 PART material은 시간증분·접촉 stiffness에만 사용될 수 있다.','PART Comments 1–4','assembly/ply/failure 전체 매핑은 미완성이다.','partial')
rule(19,['Q08','Q09'],['grnod_starter_r'],'GRNOD는 명시 node·range·요소·part·property·material·하위 group 등으로 정의된다. NODENS는 입력 순서를 유지하는 특수 variant이므로 일반 정렬과 구분한다.','GRNOD Input Type Keywords and Comments','모든 group variant 상세 행은 전수 독해하지 않았다.','partial')
rule(20,['Q09'],['bcs_starter_r','skew_fix_starter_r'],'BCS는 여섯 병진/회전 자유도 코드와 필수 node group을 참조하고 local skew 적용을 구분한다. Boolean의 열 배치가 있다. SKEW/FIX는 FRAME/FIX와 ID가 중복되면 안 된다.','BCS Trarot and Comments; SKEW/FIX Definition','모든 shell/solid DOF 조합이나 중복 BC의 solver 진단은 미검증이다.','partial')
rule(21,['Q09'],['cload_starter_r','funct_starter_r'],'CLOAD 값은 group 전체 합력이 아니라 node당 force/moment이다. curve와 방향·skew·sensor 참조를 보존한다. FUNCT의 X는 엄격 증가하며 범위 밖은 마지막 두 점의 기울기로 외삽한다. TABLE과 ID를 공유하지 않는다.','CLOAD Definition/Comments; FUNCT Comments')
rule(22,['Q09'],['inivel_starter_r'],'INIVEL은 필수 node group, 선택 skew, 병진/회전/격자 종류를 구분한다. 회전 속도는 rad/time이며 translation과 동일한 차원의 값으로 저장하지 않는다.','INIVEL Definition and Comments')
rule(23,['Q04','Q09'],['inter_type7_starter_r','inter_type24_starter_r'],'TYPE7의 secondary node group/main surface 참조와 TYPE24의 self/surface-surface/node-surface 조합은 다르다. friction/thermal 등의 flag에 따라 추가 행이 달라진다. TYPE7 edge-edge와 TYPE24 implicit SMP 제약을 보존한다.','TYPE7 Description/Format; TYPE24 Description/Format/Comments1','모든 접촉 field·수치식·MPI/implicit compatibility는 전수 검토하지 않았다.','partial')
rule(24,['Q10'],['run_engine_r','rfile_n_engine_r'],'RUN의 final time와 run number, restart letter를 구분한다. RFILE은 cycle 주기로 상태를 쓰고 선택 n에 따라 I/J/K 파일을 순환하며 다음 run은 해당 상태를 참조한다.','RUN Format/Comments; RFILE/n Comments','restart 파일은 generated text deck이 아니라 solver-produced binary state이다.')
rule(25,['Q10'],['stop_engine_r','files2024'],'STOP은 solver 내부의 에너지/질량 기준 종료다. .ctl 제어 파일과 OS process cancel은 다른 경로이며 안전한 중단·restart 유효성은 실제 런에서 검증해야 한다.','STOP Description/Definition; Files control/restart rows','외부 kill/cancel을 restart 저장 성공과 동일시하지 않는다.','partial')
rule(26,['Q10'],['impl_linear_engine_r','impl_dtini_engine_r','impl_dt_1_engine_r'],'IMPL/LINEAR의 선형 정적·모드·좌굴과 비선형 IMPL/DTINI 초기 증분, IMPL/DT/1 적응 제어를 구분한다. explicit 시간 제어와 같은 단일 step 필드로 환원하지 않는다.','IMPL/LINEAR Comments; DTINI Comments; DT/1 Format/Definition','commercial manual의 implicit keyword 존재는 OpenCourant target의 전수 implicit 기능 가용성 증거가 아니다.','partial')
rule(27,['Q10'],['tfile_engine_r','anim_dt_engine_r'],'TFILE은 time-history의 출력 형식·시간 간격이고 TH 계열은 요청 변수/객체다. ANIM/DT도 시작·빈도·종료 요청이다. 분석 최종시간과 결과 표본 간격을 분리한다.','TFILE Definition/Comments; ANIM/DT Definition','H3D 모든 요청·필드 전수는 미검토다.','partial')
rule(28,['Q11','Q12'],['radioss-D83','radioss-D84'],'MIT inp2rad는 일부 INP를 읽어 Starter/Engine text를 출력하는 실제 converter다. 기본 radversion=2025와 2023/2025 CLI 분기, hardcoded Mg/mm/s, 일부 재료·요소 변환을 확인했다.','inp2rad convert_nodes/materials/elements, write_parts/props, write_output; README supported keywords','Abaqus 전 옵션·Radioss 전 keyword의 standalone generator가 아니다. 실행하지 않았고 변환 의미가 보존되는지도 시험하지 않았다.','partial')
rule(29,['Q07','Q11'],['radioss-D83'],'inp2rad의 C3D4는 node [0,2,1,3]으로 바꾸고 C3D6은 일부 node를 반복하는 BRICK으로 매핑한다. 이는 선택한 converter의 판단이며 native 포맷의 모든 요소 규격을 대체하지 않는다.','inp2rad.py convert_elements 2947–3215','변환 결과의 orientation·Jacobian·formulation은 별도 검증해야 한다.','partial')
rule(30,['Q11','Q12'],['radioss-D85','radioss-D86','radioss-D87','radioss-D92'],'AGPL reader/writer는 실제 CFG 기반 읽기·조건부 card 출력 구조를 갖는다. 독립 writer는 descriptor·모델·CFG runtime에 의존한다. 제한적 CFG notice가 있는 파일을 AGPL 코드와 같은 조건으로 재사용할 수 있다고 가정하지 않는다.','radiossblk CFG.Init/ReadModel; mec_data_writer WriteCard/WriteIfCard; file headers','파일 1333개는 keyword 1333개가 아니며 역사 버전 상속을 포함한다. 빌드·실행하지 않았다.','partial')
rule(31,['Q11','Q12'],['radioss-D88','radioss-D93'],'공식 QA deck과 ref.extract, verifier를 실제 확보했다. reference는 upstream 회귀 관측값이며 새로운 generator의 수치 정답이나 독립 물리 검증이 아니다. .rad 다수의 CC BY-NC 표시를 확인해 원문은 내부에만 둔다.','qa-tests selected case decks/readme/test_files/ref.extract; verify_results.py functions','의도된 오류 deck corpus/validator 오류 사전은 확보·분류되지 않았다. 선택 사례의 큰 energy error도 숨기지 않는다.','partial',['radioss-E01','radioss-E02','radioss-E03','radioss-E04','radioss-E05'])
rule(32,['Q12'],['starter2024','engine2024','starter-current','engine-current','radioss-D89'],'2024 문서 색인 825행과 2026 색인 855행, OpenCourant latest-20261011 commit은 서로 다른 판 축이다. 색인·다운로드·관련 절 독해·지원 구현·solver read/run을 독립 상태로 기록한다.','catalogue reconciliation and version diff; source archive revision','문서 전 field 검토와 target runtime 지원 확인은 false다.','partial')

cases=[
 ('01','COQUES3N/ct3a','CT3AV4','2019','SH3N beam/support and initial velocity','upstream ref.extract: cycle/time/energies; 독립 실행하지 않았다.'),
 ('02','INTERF/INT_25/tetra4','model_00','2022','TETRA4 contact TYPE25 and material/failure dependencies','upstream ref.extract has energy ERROR -27.0; clean physical gold standard로 부르지 않는다.'),
 ('03','LOIS/LOI44/solides_8pt','44SLD8','2017','Single BRICK / COWPER LAW44, numeric unit factors, Engine VERS41','upstream ref.extract, 2022 readme changes; 이 연구에서 비교 실행하지 않았다.'),
 ('04','FLUIDE_NEW/EBCS/INIV','INIV','2019','ALE/EOS/HYDVISC and three Engine restart/run stages','test_files.json engine array plus upstream ref.extract; USER/외부 환경과 모든 수치 조건을 검증하지 않았다.'),
 ('05','EOS/EOS_PUFF_2','EOSPUFFDET3DCU','2018','EOS PUFF + LAW4; version-dependent RHO0 readme','upstream ref.extract; readme says RHO0 behavior from format2018, not a new golden result.'),
]
examples=[]
for num,folder,stem,fmt,purpose,expected in cases:
    directory=TMP/'qa-selected/qa-tests/miniqa'/folder/'data'
    deck=directory/(stem+'_0000.rad')
    # QA example format below is explicitly recorded from the selected /BEGIN.
    data=deck.read_text(errors='replace')
    members=[]
    for p in sorted(directory.iterdir()):
        path=str(p.relative_to(TMP/'qa-selected'))
        members.append({'path':path,'url':f'{REPO}/blob/{REV}/{path}','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size,'internal_file':str(p.relative_to(ROOT)),'redistribution':'locator-only'})
    path=str(deck.relative_to(TMP/'qa-selected'))
    examples.append({'id':'radioss-E'+num,'source_ids':['radioss-D93','radioss-D88'],'url':f'{REPO}/blob/{REV}/{path}','file':None,'sha256':hashlib.sha256(deck.read_bytes()).hexdigest(),'version':f'OpenCourant {REV}; Starter /BEGIN {fmt}','kind':'official-deck','purpose':purpose,'expected':expected,'license':'RAD file header: Creative Commons Attribution-NonCommercial 4.0; ref/meta files not assumed same license','redistribution':'locator-only','solver_executed':False,'acquisition':'actual bytes internal in pinned archive and selected paths; public bundle contains locator/hash only','members':members})

smallp=TMP/'tools-small-plast-0000.rad'
if smallp.exists():
 examples.append({'id':'radioss-E06','source_ids':['radioss-D82','radioss-D94'],'url':f'{TOOLS}/blob/{TREV}/userlib_sdk/examples/USER_material_laws_for_solids_and_shells/Solids/small_plast_0000.rad','file':None,'sha256':hashlib.sha256(smallp.read_bytes()).hexdigest(),'version':TREV,'kind':'source-example','purpose':'Tools SDK small_plast USER01 sample; user library required','expected':'제공 deck을 읽었으며 library build/solver 실행은 하지 않았다.','license':'RAD file header is CC BY-NC 4.0, not the Tools code MIT notice','redistribution':'locator-only','solver_executed':False,'internal_file':str(smallp.relative_to(ROOT))})

code_assets=[
 {'id':'radioss-C01','source_ids':['radioss-D82','radioss-D83','radioss-D84'],'role':'converter','repository':TOOLS,'revision':TREV,'paths':['input_converters/inp2rad/inp2rad/inp2rad.py','input_converters/inp2rad/README.md'],'scope':'Actual INP-to-RAD text conversion for documented subset; 85 Python functions inventoried','limits':'Beta/unsupported suboptions; default version2025 and choices2023/2025; hardcoded Mg/mm/s; no all-keyword claim or execution','license':'MIT per source header and Tools Copyright.md','local_files':['examples/radioss/code/inp2rad.py','examples/radioss/code/inp2rad-README.md','examples/radioss/code/Tools-Copyright.md'],'executed':False},
 {'id':'radioss-C02','source_ids':['radioss-D80','radioss-D81','radioss-D85','radioss-D92'],'role':'solver-reader','repository':REPO,'revision':REV,'paths':['reader/source/io/model_readers/radioss/radiossblk/radiossblk.cxx'],'scope':'CFG-backed reader front end, profile selection, ReadModel and offsets','limits':'Not standalone; selected main profile defaults2026; full starter Fortran semantic implementation not reviewed','license':'AGPL-3.0-or-later source file; required CFG has distinct restrictive notices','local_files':['examples/radioss/code/radiossblk.cxx','examples/radioss/code/OpenCourant-LICENSE.md','examples/radioss/code/OpenCourant-COPYRIGHT.md'],'executed':False},
 {'id':'radioss-C03','source_ids':['radioss-D80','radioss-D81','radioss-D86','radioss-D87','radioss-D92'],'role':'writer','repository':REPO,'revision':REV,'paths':['reader/source/cfgio/MODEL_IO/mec_data_writer.cpp','reader/source/cfgio/MODEL_IO/mec_single_file_writer.cpp'],'scope':'Generic descriptor/CFG-driven field/card/list/conditional text output and output buffer','limits':'Not a standalone generated RAD application or full schema; requires model/runtime/descriptors and CFG with separate conditions','license':'AGPL-3.0-or-later in selected file headers','local_files':['examples/radioss/code/mec_data_writer.cpp','examples/radioss/code/mec_single_file_writer.cpp','examples/radioss/code/OpenCourant-LICENSE.md'],'executed':False},
 {'id':'radioss-C04','source_ids':['radioss-D89','radioss-D92'],'role':'schema','repository':REPO,'revision':REV,'paths':['hm_cfg_files/config/CFG/radioss*'],'scope':'1333 descriptors/version hierarchy paths, SHA and header license classifications; selected ATTRIBUTES/DEFAULTS/FORMAT/CARD structures read','limits':'1331 restrictive CFG notices, 2 unclassified; no CFG bytes redistributed; file count is not keyword count; inherited-version resolution/full-field schema not complete','license':'File-specific limited use solely with OpenRadioss and modification contribution conditions; not assumed AGPL','local_files':['catalogues/radioss-cfg-inventory.json'],'executed':False},
 {'id':'radioss-C05','source_ids':['radioss-D80','radioss-D88','radioss-D93'],'role':'parser','repository':REPO,'revision':REV,'paths':['qa-tests/qa_tools/verify_results.py'],'scope':'Engine-output extraction and comparison to ref.extract with configured tolerances','limits':'Regression comparator, not deck writer or proof of physical correctness; no runtime execution','license':'AGPL-3.0-or-later in source header','local_files':['examples/radioss/code/verify_results.py','examples/radioss/code/OpenCourant-LICENSE.md'],'executed':False}
]

missing={
 'Q01':'실제 target 최소 덱 read/run 및 모든 특수 파일 역할은 미검증.',
 'Q02':'인코딩, 전체 수치 표기/overflow/continuation 예외와 모든 card의 exact column schema 미완성.',
 'Q03':'모든 unit_ID 및 열/전기/복합 단위 field의 전수 변환표 미완성.',
 'Q04':'825행의 전체 field/조건/default/별칭 정규화·상속 전수 검토는 false.',
 'Q05':'모든 include/parameter/transform edge case와 templex 제공 여부 runtime 미검증.',
 'Q06':'전체 keyword namespace/ID 상한/duplicate 진단/forward-reference 규칙표와 allocator 미구현.',
 'Q07':'고차 요소 전체, face/side 전체, formulation별 퇴화/노멀 전수 규칙과 양의 Jacobian 시험 미확보.',
 'Q08':'복합재·assembly·MPC·rigid·SPH/ALE 등 전체 객체 매핑 schema 미완성.',
 'Q09':'모든 하중/접촉/재료/센서·curve 참조의 조건과 activation 전수 미완성.',
 'Q10':'전체 explicit/implicit/restart/output 조합·실제 중단 복구 의미 runtime 미검증.',
 'Q11':'의도된 오류 fixture/expected diagnostic corpus 미분류; 배포 가능한 NC-free 완전 모델 시험쌍 미확보; official NC deck은 내부 취득.',
 'Q12':'target OpenCourant의 2024/2026 keyword/field별 support 매핑과 binary read/run false; 제한 CFG 권리 미해소.'}
coverage=[]
for n in range(1,13):
 q=f'Q{n:02}';coverage.append({'question_id':q,'rule_ids':[r['id'] for r in rules if q in r['question_ids']],'status':'partial','missing':missing[q]})

detailpath=ROOT/'catalogues/radioss-detail-acquisition.json'
detail=json.loads(detailpath.read_text()) if detailpath.exists() else None
reviewed_urls={urldefrag(s['url'])[0]:s['locator'] for s in sources if s['version']=='Radioss 2024' and s['read_depth']=='relevant-sections'}
if detail:
    for x in detail['results']:
        if x['url'] in reviewed_urls and x['status']=='downloaded':
            x['read_depth']='relevant-sections';x['read_locator']=reviewed_urls[x['url']]
    detailpath.write_text(json.dumps(detail,ensure_ascii=False,indent=2)+'\n')

# Preserve raw index labels; only annotate which detail pages had relevant sections read.
cp=ROOT/'catalogues/radioss.csv';rows=list(csv.DictReader(cp.open()));fields=list(rows[0])
for row in rows:
    if urldefrag(row['official_url'])[0] in reviewed_urls:row['detail_review']='relevant-sections'
with cp.open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(ROOT/'catalogues/radioss.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))

figp=TMP/'figures2024/manifest.json'
if figp.exists():
 figs=json.loads(figp.read_text())
 for f in figs:
  if Path(f['file']).name in ('clip0140.png','sh3n.png','shell.png'):f['read_depth']='visually-read';f['locator']='TETRA4/SH3N/SHELL Figure1 node order/local axes'
 figp.write_text(json.dumps(figs,ensure_ascii=False,indent=2)+'\n')

doc={'key':'radioss','title':'Radioss / OpenRadioss / OpenCourant 입력 생성 자료',
 'scope':'공용 전처리 자산의 첫 적용 조사. 주 목록은 Altair Radioss2024 Starter+Engine이며 OpenCourant release latest-20261011 소스는 별도 고정한다. 문서 전체 색인 확보는 전수 field 구현/지원/실행을 뜻하지 않는다.',
 'versions':{'documentation':'Primary Radioss2024 online; historical Reference Guide2022 PDF; comparator current online banner2026 acquired2026-10-30','solver':f'OpenCourant latest-20261011; commit {REV}; binary not run','source':f'OpenCourant {REV}; Tools {TREV}; observed current main843b3c457d575dfb22ddca14c95644e2861636fd is NOT target pin','examples':f'QA source archive {REV}, heterogeneous /BEGIN2017/2018/2019/2022; Tools sample {TREV}','binary_tested':None},
 'sources':sources,
 'catalogue':{'files':['catalogues/radioss.csv','catalogues/radioss.jsonl','catalogues/radioss-reconciliation.json','catalogues/radioss-detail-acquisition.json'],'source_ids':['radioss-D01','radioss-D02'],'scope':'Radioss2024 Starter+Engine Supported Keywords sections, complete index links only','entry_count':825,'count_unit':'原文索引行: keyword/family/option/alias labels mixed, not canonical unique supported keywords','completeness':'complete-index','reconciliation':'Starter590/Engine235 links parsed; zero unparsed and zero duplicate name+URL rows. Starter577/Engine227 unique detail URLs (combined804). Shared-page groups11+1. Preserve raw FTFILE label linked to atfile_engine_r.htm; semantic aliases/variants not exhaustively resolved. Separate2026 comparator855 rows and added/removed diff; do not add as one denominator.','full_field_review_complete':False},
 'rules':rules,'examples':examples,'code_assets':code_assets,'coverage':coverage,
 'acquisition_log':[{'target':a['url'],'outcome':a.get('status'),'key':a['key'],**{k:a[k] for k in ('size_bytes','sha256','error') if k in a}} for a in acqs]+[{'target':'2024 index-linked detail pages804 unique URLs','outcome':'See catalogues/radioss-detail-acquisition.json; original HTML internal only; no retry; stop403/429; selected pages relevant-sections, others not-read'},{'target':'OpenCourant source archive QA and CFG','outcome':'Actual original47,436,970bytes/SHA9055ad07964dec2b7f2d8b526155fd389ae55585dbe65ac81bbd6e059e6ce502 acquired; QA/CFG path+hash inventories retained, proprietary/NC material not put in public assets'}],
 'gaps':list(missing.values())+['문서 edition·/BEGIN Invers·Engine VERS·source release·binary build는 별도 축이다. source reader의 기본 profile2026과 converter 기본2025를2024 catalogue와 동일하게 보지 않는다.','공식2024 /VERS mandatory와 일부 QA/Tools의 생략 사례가 불일치해 target runtime 검증 전 판단을 유보한다.','현재 작업은 실제 수집과 근거 분류이며 caelab-prep에 신규 RAD generator나 전 keyword editor를 구현한 작업이 아니다.'],
 'runtime_verified':False}
OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')

manifest=[]
for p in sorted((ROOT/'examples/radioss/code').iterdir()):
 if p.is_file():manifest.append({'file':str(p.relative_to(ROOT)),**{k:v for k,v in meta(str(p.relative_to(ROOT))).items() if k!='local_file'}})
(ROOT/'examples/radioss/code-manifest.json').write_text(json.dumps({'source_pin':REV,'tools_pin':TREV,'files':manifest,'solver_executed':False},indent=2)+'\n')
print(json.dumps({'sources':len(sources),'rules':len(rules),'examples':len(examples),'code_assets':len(code_assets),'catalogue_rows':len(rows),'relevant_detail_pages':sum(1 for s in sources if s['id'] in [ids[n] for n,*_ in selected]),'detail_manifest_ready':bool(detail)},ensure_ascii=False))
