"""Compile the researched Abaqus evidence record; no solver/generator execution."""
from pathlib import Path
import csv, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://docs.software.vt.edu/abaqusv2025/English/'
PIN_M = 'b2ee99842e119901349fdeee06b5bf61e01f450a'
PIN_A = '3088e9fc3b77da615a586524c0cb407b3d0acc48'
sources = []

def digest(path):
    data = (ROOT/path).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)

def source(sid, part, title, local, locator, summary, kind='manual', depth='relevant-sections', version='Abaqus 2025; vendor-origin manual at Virginia Tech mirror', redistribution='locator-only'):
    url = part if part.startswith('https://') else BASE+part
    sha, size = digest(local) if local else (None, None)
    sources.append(dict(id='abaqus-'+sid, url=url, title=title, kind=kind, version=version,
        locator=locator, access='read' if depth in ('relevant-sections','index-parsed') else 'downloaded', read_depth=depth,
        local_file=local, sha256=sha, size_bytes=size, redistribution=redistribution, summary=summary))

source('D01','SIMACAEKEYRefMap/simakey-c-ov.htm','Abaqus Keywords Guide','tmp/abaqus/keyword-guide.html','Using Abaqus Keywords; Using the Keywords Guide','제품별 지원과 CAE 지원은 개별 옵션에서 확인한다. 전체 목록은 field schema 완성과 다르다.')
source('D02','SIMACAECAERefMap/simacae-c-gen-kwbrowser.htm','Keyword browser table','tmp/abaqus/keyword-browser.html','All 600 keyword rows and linked keyword pages','600개의 고유 keyword 이름과 상세 URL을 추출했다. CAE GUI 지원 표시는 solver 지원과 다르다.','index','index-parsed')
source('D03','SIMACAECAERefMap/simacae-c-gen-kwinpfilereader.htm','Input file reader keyword support','tmp/abaqus/keyword-reader.html','All 600 keyword links','두 번째 전체 목록과 이름·URL 집합을 대조했다. reader가 모든 옵션을 보존한다는 의미는 아니다.','index','index-parsed')
sections = [
('D04','SIMACAEMODRefMap/simamod-c-inputsyntax.htm','Input syntax','syntax.html','Keyword lines; Data lines; Input syntax rules','ASCII, 줄 길이, 연속, 이름, blank/default 및 외부 파일명 규칙을 읽었다.'),
('D05','SIMACAEMODRefMap/simamod-c-model.htm','Defining a model','model.html','Model data; History data; Including Model or History Data from an External File','모델/이력 분리, 동일 분석 제품의 절차, 외부 참조 처리와 최대 5단계 중첩을 읽었다.'),
('D06','SIMACAEMODRefMap/simamod-c-conventions.htm','Conventions','conventions.html','Degrees of Freedom; Units; Rotation and Angle Measures; Unit System Definition','활성 자유도, 일관 단위, 각도 예외, 변환용 UNIT SYSTEM의 한계를 읽었다.'),
('D07','SIMACAEMODRefMap/simamod-c-partassy.htm','Assembly definition','assembly.html','Parts; Instances; Assembly; Naming conventions; Defining nodes/elements/sets','part/instance/assembly 구조와 로컬 식별자·완전 한정 참조를 읽었다.'),
('D08','SIMACAEMODRefMap/simamod-c-node.htm','Node definition','node.html','Defining nodes; Node numbering; Node sets; Local coordinate systems','양의 정수 ID, 중복 마지막 정의, 로컬 scope와 정렬/비정렬 node set을 읽었다.'),
('D09','SIMACAEMODRefMap/simamod-c-element.htm','Element definition','element.html','Defining elements; Element numbering; Node ordering; Element sets','연결·타입·set의 매핑 및 native element 정의와 메시 형식의 경계를 읽었다.'),
('D10','SIMACAEELMRefMap/simaelm-r-3delem.htm','Three-dimensional solid element library','solid-library.html','Element types; Node ordering and face numbering on elements; Variable-node elements','tetra/wedge/brick의 native 연결·face 표와 일부 가변 노드 조건을 읽었다.'),
('D11','SIMACAEMODRefMap/simamod-c-parinput.htm','Parametric modeling','parameter.html','Parameter Names; Parameter Definitions; Parameter Usage; Parameter dependence','대소문자 구분 변수·대입·치환과 선행 테이블 정의 조건을 읽었다.'),
('D12','SIMACAEANLRefMap/simaanl-c-restart.htm','Restarting an analysis','restart-guide.html','Writing restart information; Reading restart information; Standard/Explicit procedures','restart 저장 요청·제품별 상태 파일과 재시작 조건을 읽었다.'),
('D13','SIMACAEEXCRefMap/simaexc-c-analysisproc.htm','Abaqus/Standard and Abaqus/Explicit execution','analysis-execution.html','syntaxcheck; datacheck; continue; recover; parallel options','구문 검사·모델 검사·계속/복구의 차이를 읽었다. 문서 조사만 했으며 명령을 실행하지 않았다.'),
('D14','SIMACAEEXCRefMap/simaexc-c-fetchproc.htm','Fetching sample input files','fetch-example.html','Input file and user subroutine archive files; fetch command','설치된 release 예제와 의존 파일을 fetch하는 방법을 읽었다.'),
('D15','SIMACAEEXCRefMap/simaexc-c-keywordproc.htm','Querying the keyword/problem database','query-examples.html','findkeyword utility; problem database lookup','공식 예제에 사용한 keyword로 모델과 관련 파일을 찾는 방법을 읽었다.'),
('D16','SIMACAEKERRefMap/simaker-c-modeljobpyc.htm','ModelJob API','job-writeinput.html','writeInput method; consistencyChecking','writeInput은 Abaqus 런타임의 모델/job API이며 독립 공개 writer의 구현을 뜻하지 않는다.'),
]
for sid,part,title,file,locator,summary in sections:
    source(sid,part,title,'tmp/abaqus/'+file,locator,summary,kind='api' if sid=='D16' else 'manual')

keywords = [
('D17','surface','*SURFACE','Type/Level; TYPE-dependent data lines','element/node/analytical surface 종류와 필요한 side·방향 데이터가 다르다.'),
('D18','include','*INCLUDE','INPUT; PASSWORD; Data lines','외부 파일 이름은 필수이며 암호화 데이터는 별도 조건을 갖는다.'),
('D19','elastic','*ELASTIC','TYPE; dependencies; data lines','탄성 TYPE과 온도/장 변수에 따라 필드 개수와 반복 행이 달라진다.'),
('D20','solidsection','*SOLID SECTION','Required parameters; MATERIAL/COMPOSITE; Data lines','ELSET·재료/복합체·방향의 조건부 참조를 읽었다.'),
('D21','shellsection','*SHELL SECTION','Required and mutually exclusive parameters; data lines','ELSET·두께·재료/적층과 방향 조건을 읽었다.'),
('D22','boundary','*BOUNDARY','Type/Level; AMPLITUDE; OP; data lines','model/history 조건, 기존 구속 유지·제거 및 amplitude 기본값은 절차별로 다르다.'),
('D23','contactpair','*CONTACT PAIR','Type/Level; INTERACTION; data lines','제품별 model/history 문맥, 상호작용 속성과 surface 쌍 참조를 읽었다.'),
('D24','contact','*CONTACT','General contact; Type/Level; data lines','general contact 시작 옵션만으로 접촉 정의 전체가 완성되지는 않는다.'),
('D25','amplitude','*AMPLITUDE','DEFINITION; TIME; mutually exclusive parameters; data lines','곡선 정의 방식·시간 기준별 조건과 데이터 형식을 읽었다.'),
('D26','step','*STEP','Products; NLGEOM; PERTURBATION; AMPLITUDE','step별 절차와 비선형/섭동·하중 시간 변화 조건을 읽었다.'),
('D27','dynamic','*DYNAMIC','Implicit dynamic analysis; Explicit dynamic analysis; data lines','implicit와 EXPLICIT의 파라미터/행 규칙은 서로 다르다.'),
('D28','output','*OUTPUT','FIELD/HISTORY; frequency/time controls; associated output requests','출력 문맥과 제어·하위 출력 요청을 읽었다.'),
('D29','initialconditions','*INITIAL CONDITIONS','Required TYPE; FILE/USER/EXTERNAL FIELD alternatives; data-line branches','TYPE별 행 분기와 파일/사용자 루틴으로 초기 조건을 주는 경우를 읽었다.'),
('D30','transform','*TRANSFORM','NSET; TYPE; coordinate data line','노드 자유도용 변환과 좌표/재료 방향은 별도 객체다.'),
('D31','cload','*CLOAD','Type/Level; AMPLITUDE; OP; FILE; FOLLOWER','절차별 amplitude 기본값과 기존 하중·회전 추종 조건을 읽었다.'),
]
for sid,key,title,locator,summary in keywords:
    file='tmp/abaqus/'+key+'.html' if (ROOT/('tmp/abaqus/'+key+'.html')).exists() else 'tmp/abaqus/keywords/simakey-r-'+key+'.htm'
    source(sid,'SIMACAEKEYRefMap/simakey-r-'+key+'.htm',title,file,locator,summary)
source('D32','SIMACAEVERRefMap/simaver-c-3delem.htm','Verification: solid elements','tmp/abaqus/simaver-c-3delem.htm','Stress/displacement tests; files ec34sfs2.inp and ec38sfs2.inp; expected solution','문서가 제공하는 응력·변형률·section force 기준을 확인했다. 당사 실행 결과가 아니다.')
source('D33','SIMACAEVERRefMap/simaver-c-contsmslcont.htm','Verification: small-sliding contact','tmp/abaqus/simaver-c-contsmslcont.htm','Three-dimensional solid elements; interference/perturbation/friction; ei33sisc_surf.inp','초기 overclosure 제거·섭동·마찰 변경 예의 검증 목적을 확인했다.')

example_defs = [
('E01','c2.inp','자족 B21 beam 대변형 static 예','공식 fetch 문서가 예로 드는 파일. 수치 결과 정답은 여기서 확보하지 않았음.','D14',True),
('E02','ec34sfs2.inp','자족 8-node/5-C3D4 solid 검증 예','D32가 응력 6성분 -1000, normal strain -1.3333e-5, shear strain -8.6667e-5 및 section force 기준을 제공. 여기서는 미실행.','D32',True),
('E03','ec38sfs2.inp','자족 8-node/1-C3D8 solid 검증 예','D32의 동일 solid verification 기준과 연결. 실제 실행/오차 비교는 하지 않았음.','D32',True),
('E04','ei33sisc_surf.inp','자족 C3D4 small-sliding contact 검증 예','D33가 간섭 제거 후 접촉 traction과 해석해의 일치를 설명. 수치 비교는 미수행.','D33',True),
('E05','block_c3d4_b_std_gcont.inp','자족 참조처럼 보이는 Standard general-contact 대형 덱','헤더와 외부 참조 유무만 조사. 전체 모델/검증 결과는 독해하지 않았음.','D01',False),
('E06','boltpipeflange_3d_cyclsym.inp','외부 의존이 있는 flange/bolt assembly 예','node INPUT 및 substructure library 참조가 있어 단일 파일 완전 덱으로 쓰지 못함. 해석 결과 미확인.','D01',False),
]
examples=[]
for eid,name,purpose,expected,parent,read in example_defs:
    sid='X'+eid[1:];file='tmp/abaqus/'+name
    source(sid,'SIMAINPRefResources/'+name,'Official sample input '+name,file,'Whole input text' if read else 'Header and external references only',purpose,kind='example',depth='relevant-sections' if read else 'metadata-only')
    examples.append(dict(id='abaqus-'+eid,source_ids=['abaqus-'+sid,'abaqus-'+parent],url=BASE+'SIMAINPRefResources/'+name,
        file=None,analysis_file=file,sha256=digest(file)[0],version='Abaqus 2025 documentation archive',kind='official-deck',purpose=purpose,
        expected=expected,license='Vendor-origin example; republication permission not verified',redistribution='locator-only',solver_executed=False))

code_defs = [
('C01','meshio','nschloe/meshio',PIN_M,'src/meshio/abaqus/_abaqus.py','examples/abaqus/meshio/_abaqus.py','read_buffer; write; abaqus_to_meshio_type','mesh、NSET、ELSET、INCLUDE parser 및 mesh/set writer. 재료·step·접촉 생성기는 아님.','code'),
('C02','meshio','nschloe/meshio',PIN_M,'tests/test_abaqus.py','examples/abaqus/meshio/test_abaqus.py','roundtrip tests; mesh sets','시험 코드만 취득. vendor-origin test mesh 원본은 포함하지 않았다.','code'),
('C03','meshio','nschloe/meshio',PIN_M,'LICENSE.txt','examples/abaqus/meshio/LICENSE.txt','MIT license','MIT 권리·고지를 동봉했다. upstream test mesh의 별도 권리는 해당 README와 구분한다.','license'),
('C04','abqpy','haiiliin/abqpy',PIN_A,'examples/Compression/compression.py','examples/abaqus/abqpy/compression.py','Model; mesh; Job.writeInput; job.submit; waitForCompletion','full CAE workflow 예이나 Abaqus 런타임 API에 위임하며 실행 시 job 제출을 포함한다.','example'),
('C05','abqpy','haiiliin/abqpy',PIN_A,'LICENSE','examples/abaqus/abqpy/LICENSE','MIT license','MIT 권리·고지를 동봉했다.','license'),
]
for sid,title,repo,pin,path,local,locator,summary,kind in code_defs:
    source(sid,f'https://github.com/{repo}/blob/{pin}/{path}',title+' '+path,local,locator,summary,kind=kind,version=pin,redistribution='permitted-with-notice')
source('C06',f'https://github.com/haiiliin/abqpy/blob/{PIN_A}/src/abaqus/Job/ModelJob.py#L295-L305','abqpy ModelJob type/documentation stub',None,'src/abaqus/Job/ModelJob.py:295 signature; 296–304 documentation; 305 ellipsis body','GitHub connector fetch_file로 고정 commit 전체 파일을 읽고 288–310행을 재확인했다. 공개 함수 본체는 ...다. 실제 inp를 생성하는 독립 구현이 아니다.','code',version=PIN_A)
sources[-1]['access']='read'
sources[-1]['acquisition_route']='GitHub connector fetch_file(repository_full_name=haiiliin/abqpy, ref='+PIN_A+', path=src/abaqus/Job/ModelJob.py); audit recheck lines 288–310'
sources[-1]['upstream_git_blob_sha']='e385552a40915d24d97015c860ad47f32d522e38'

rules=[]
def rule(i,q,ss,text,where,limits='',examples=(),status='documented'):
    rules.append(dict(id=f'abaqus-R{i:02}',question_ids=q,source_ids=['abaqus-'+x for x in ss],statement=text,locator=where,examples=['abaqus-'+x for x in examples],limits=limits,status=status))
rule(1,['Q01'],['D05'],'*.inp는 model data와 *STEP 이후 history data로 나뉜다. 한 job의 procedure는 같은 Standard 또는 Explicit 제품에 속해야 한다.','Model data; History data','import/restart·사용자 루틴·co-simulation은 별도 파일 의존이 가능하다.',('E01','E02'))
rule(2,['Q02'],['D04'],'일반 keyword/data는 7-bit ASCII이며 줄 끝 개행이 필요하다. keyword 첫 유효 문자는 *이고 **는 주석이다. keyword/data line은 최대 256자다.','Keyword lines; Data lines','비 ASCII GUI label을 native deck에 무검증 직렬화하지 않는다.')
rule(3,['Q02','Q04'],['D04'],'keyword는 쉼표 구분 parameter와 끝 쉼표 연속을 쓴다. data 연속은 허용된 옵션에서만 쓴다. 생략 numeric은 별도 default가 없으면 0이며 초과 data 항목은 경고 없이 무시될 수 있다.','Keyword lines; Data lines','blank=0 규칙을 필수/조건부 행 생략과 혼동하면 안 된다.')
rule(4,['Q02','Q06'],['D04'],'일반 keyword/parameter는 대소문자를 구분하지 않으며 유일한 축약을 허용하지만 파일명·수치는 축약하지 않는다. label 인용·길이·허용 문자 제약이 있다.','Input syntax rules','중복 parameter 결과나 축약을 안정적인 writer 전략으로 삼지 않는다.')
rule(5,['Q03'],['D06'],'기본 물리 단위는 자기 일관성이 필요하다. 회전 자유도는 radian, 다른 각도는 degree다. UNIT SYSTEM은 일부 전송/행렬·substructure 정보에 쓰이며 해석값 자동 환산을 보장하지 않는다.','Units; Rotation and Angle Measures; Unit System Definition')
rule(6,['Q05'],['D04','D05','D18'],'INCLUDE는 즉시 외부 내용을 읽고 EOF 후 복귀한다. 최대 5단계 중첩이다. 상대 외부 파일명은 job 제출 디렉터리 기준이고 INPUT과 FILE 확장자 규칙은 다르다.','Including Model or History Data from an External File; Input syntax rules','단순 including-file parent-directory 재귀로 구현하면 원문 규칙과 다를 수 있다.',('E06',))
rule(7,['Q02','Q05'],['D11'],'PARAMETER의 변수 이름은 대소문자를 구분하고 <name> 치환을 한다. 의존 테이블은 사용 전에 정의하며 # parameter 주석과 일반 ** 주석의 문맥이 다르다.','Parameter Names; Parameter Usage; Parameter dependence','모든 Python 기능을 허용하는 문법으로 일반화하지 않는다.')
rule(8,['Q06','Q08'],['D07','D08'],'part/instance/assembly는 로컬 node/element ID와 set/surface namespace를 갖는다. instance 이름과 참조 part를 보존하고 필요한 완전 한정 이름을 쓴다. 같은 숫자 ID를 전역 충돌로 처리하면 안 된다.','Assembly definition; Node numbering','개별 keyword별 forward-reference 허용표는 전수 검토하지 않았다.')
rule(9,['Q06','Q08'],['D08','D09'],'node ID는 양의 정수 최대 999999999이며 비연속 허용·중복 마지막 정의 규칙이 있다. 기본 NSET 정렬·중복 제거와 UNSORTED 순서 보존이 구속식 의미에 영향을 준다.','Node numbering; Node sets; Defining elements','전체 entity 중복 규칙을 node의 마지막 정의 규칙으로 확장하지 않는다.')
rule(10,['Q07'],['D10','D17'],'native element TYPE과 순서·face를 보존해야 한다. 예: C3D8 face1=1,2,3,4; face2=5,8,7,6이며 tetra/wedge는 별도 표다. element surface의 S번호도 native face 표와 연결한다.','Node ordering and face numbering on elements; *SURFACE TYPE=ELEMENT','모든 element type·고차/퇴화/가변 node 조건의 검토는 미완료다.')
rule(11,['Q07','Q09'],['D06','D08','D30'],'활성 DOF는 element 종류가 요구하는 envelope에서 온다. node 생성 좌표계, node DOF TRANSFORM, material ORIENTATION은 별도다. TRANSFORM은 NSET과 R/C/S 형식별 점 정의를 참조한다.','Degrees of Freedom; *TRANSFORM required parameters/data','모든 노드에 항상 6 DOF가 있다는 모델은 부적합하다.')
rule(12,['Q04','Q08'],['D04','D19','D20','D21'],'material 관련 하위 옵션은 연속 블록을 이룬다. solid/shell section은 ELSET와 material/composite 조건을 참조하며 thickness·orientation·elastic TYPE/온도 의존에 따라 행 schema가 달라진다.','Related keyword grouping; section required/mutually exclusive parameters; *ELASTIC data lines','전체 material/section keyword 필드를 schema로 전환한 것은 아니다.',('E02','E03'))
rule(13,['Q04','Q09'],['D22','D25','D31'],'BOUNDARY/CLOAD의 OP=MOD/NEW, AMPLITUDE와 절차별 기본 시간 변화는 step 전이를 반영해야 한다. FOLLOWER 등 선택 조건은 활성 회전 DOF·절차와 연동된다.','*BOUNDARY/*CLOAD OP, AMPLITUDE, FOLLOWER; *AMPLITUDE DEFINITION/TIME','전체 하중·초기조건·다중물리 옵션 표는 아직 완성하지 않았다.')
rule(14,['Q04','Q08','Q09'],['D17','D23','D24'],'CONTACT PAIR은 surface 쌍·INTERACTION 속성이 필요하고 Standard/Explicit의 model/history 문맥이 다르다. CONTACT 하나만 써서 general contact 전체를 생성할 수 없다.','*CONTACT PAIR Products/Type/Level and data lines; *CONTACT','접촉 property/include/exclude/activation 전 옵션 schema는 미완성이다.',('E04',))
rule(15,['Q04','Q09'],['D29'],'INITIAL CONDITIONS는 TYPE에 따라 행이 분기하며 FILE/USER/EXTERNAL FIELD 경로는 일반 직접 data와 다르다. FILE 사용 시 DRIVING ELSETS 등 예외를 별도로 읽어야 한다.','Required TYPE; no-data conditions; TYPE-specific data lines','관련 분기 구조를 읽었으나 모든 TYPE의 필드·단위·기본값을 표로 만들지는 않았다.')
rule(16,['Q01','Q10'],['D05','D26','D27'],'STEP는 절차와 NLGEOM/PERTURBATION 문맥을 갖고 DYNAMIC implicit와 EXPLICIT의 필드·제어가 다르다. 일반 step과 섭동 step의 상태 전달 의미도 다르다.','History data; *STEP parameters; *DYNAMIC implicit/explicit branches','CalculiX 유사 철자와 절차/옵션 의미를 동치로 가정하지 않는다.')
rule(17,['Q10'],['D12','D13','D28'],'restart는 사전 상태 저장과 제품별 파일·제약이 필요하다. OUTPUT FIELD/HISTORY와 하위 요청은 별도다. 외부 process cancel을 restart/recover로 취급하면 안 된다.','Restart guide; recover/continue; *OUTPUT','ODB만으로 모든 restart 상태가 보존된다고 가정하지 않는다.')
rule(18,['Q10','Q12'],['D13'],'syntaxcheck는 syntax만 검사하고 datacheck는 모델 검사 및 계속 실행용 파일을 작성한다. 문서는 syntaxcheck가 license token을 소비하지 않는다고 명시하지만 설치된 Abaqus 실행기가 필요하다.','syntaxcheck; datacheck; continue','실행기가 없어 문서상의 명령만 확보했다. syntax 성공은 의미/수치 검증이 아니다.')
rule(19,['Q11'],['D14','D15','D32','D33'],'공식 fetch/findkeyword 경로와 실제 2025 inp 원본을 취득했다. 완전 자족 4개 예를 직접 읽었고, 큰 general contact는 헤더만 읽었다. flange 예는 외부 node/library 의존이 있다.','fetch; findkeyword; verification Input files','공식 오류 입력/정답 로그와 회귀 실행 결과는 미확보다.',('E01','E02','E03','E04','E05','E06'),'partial')
rule(20,['Q07','Q11'],['C01','C02'],'meshio writer는 NODE/ELEMENT/NSET/ELSET와 heading을 출력하고 parser는 INCLUDE를 읽지만 full model block은 처리하지 않는다. element variant→공통 cell type 병합은 역변환에서 세부 formulation 손실 위험이 있다.','_abaqus.py read_buffer:111+, mappings:17–101, write:402+','단일 파일은 상대 import가 있어 독립 실행 파일이 아니고 mesh roundtrip도 solver 검증이 아니다.')
rule(21,['Q11','Q12'],['C04','C06','D16'],'abqpy 공개 ModelJob.writeInput의 본체는 ...다. Compression script는 Abaqus API로 모델을 만들고 writeInput/submit을 호출한다. MIT 공개 예제와 실제 licensed runtime 의존을 구분해야 한다.','ModelJob.writeInput; examples/Compression/compression.py','독립 무료 full Abaqus generator가 아니며 이 예제는 실행하지 않았다.')
rule(22,['Q12'],['D01','D02','D03','C03','C05'],'문서 버전은 2025로 고정했다. CAE GUI/reader 지원과 solver keyword 존재는 다른 축이다. vendor mirror 접근은 재배포 허가를 뜻하지 않아 원본은 tmp로 제한하고 MIT 예제만 고지와 동봉한다.','Keyword guide/browser/reader; MIT licenses','600개 전체 index/페이지 확보와 모든 필드 검토·실제 제품 지원·solver 실행은 별개다.')

code_assets = [
dict(id='abaqus-A01',source_ids=['abaqus-C01','abaqus-C02','abaqus-C03'],role='writer',repository='https://github.com/nschloe/meshio',revision=PIN_M,paths=['src/meshio/abaqus/_abaqus.py','tests/test_abaqus.py','LICENSE.txt'],scope='Mesh reader/converter plus mesh/set writer only',limits='재료·section·step·BC·load·contact·output 생성 없음. formulation/type alias 손실 가능. package dependencies 필요.',license='MIT; LICENSE.txt included; third-party test meshes excluded',local_files=['examples/abaqus/meshio/_abaqus.py','examples/abaqus/meshio/test_abaqus.py','examples/abaqus/meshio/LICENSE.txt'],executed=False),
dict(id='abaqus-A02',source_ids=['abaqus-C04','abaqus-C05','abaqus-C06','abaqus-D16'],role='generator',repository='https://github.com/haiiliin/abqpy',revision=PIN_A,paths=['examples/Compression/compression.py','src/abaqus/Job/ModelJob.py','LICENSE'],scope='Abaqus/CAE runtime modeling script example and API type stubs; no independent native writer implementation',limits='Abaqus installation/runtime required; writeInput is ... stub. example also calls job.submit/waitForCompletion.',license='MIT; LICENSE included',local_files=['examples/abaqus/abqpy/compression.py','examples/abaqus/abqpy/LICENSE'],executed=False),
]
coverage=[]
missing={
'Q01':'추가 procedure·import·co-simulation 최소 유효 덱은 아직 전수 도출하지 않았다.',
'Q02':'외부 binary·사용자 루틴의 인코딩/IO는 이 text deck 조사 범위 밖이다.',
'Q03':'모든 다중물리 property의 단위 차원 dictionary를 구축하지 않았다.',
'Q04':'600개 keyword 전 필드·분기·기본값·필수 참조 schema는 미완성이다.',
'Q05':'모든 FILE/INPUT 옵션과 암호화·특수 외부 형식의 dependency resolver는 없다.',
'Q06':'모든 entity/keyword의 선후 참조·중복 정책 전수표는 없다.',
'Q07':'모든 element family의 고차·퇴화·가변노드·face/DOF 전수표는 없다.',
'Q08':'모든 property/section·재료·assembly keyword 객체 매핑이 구현/완료되지 않았다.',
'Q09':'모든 하중·초기조건·접촉 옵션과 단계 간 활성화 schema는 미완성이다.',
'Q10':'실제 중단·restart·recover와 output 회귀는 실행하지 않았다.',
'Q11':'공식 malformed/error deck 및 정답 로그 미확보; full standalone writer 미발견.',
'Q12':'직접 vendor portal의 동일판 원본 교차 비교·실행기 검증·전수 field 의미 검증 미수행.',
}
for i in range(1,13):
    q=f'Q{i:02}';coverage.append(dict(question_id=q,rule_ids=[x['id'] for x in rules if q in x['question_ids']],status='partial',missing=missing[q]))
rec=json.loads((ROOT/'catalogues/abaqus-reconciliation.json').read_text())
result=dict(key='abaqus',title='Abaqus',scope='Abaqus 2025 keyword browser/reader A–Z 600 keyword entries; vendor-origin Virginia Tech mirror; selected input-generation sections and actual examples',
versions=dict(documentation='2025, docs.software.vt.edu vendor-origin mirror (not direct Dassault hosting)',solver='Abaqus/Standard and Abaqus/Explicit 2025 documented; no binary installed/tested',source={'meshio':PIN_M,'abqpy_2025_branch':PIN_A},examples='2025 official documentation resources; code examples at pinned commits',binary_tested=None),
sources=sources,catalogue=dict(files=['catalogues/abaqus.csv','catalogues/abaqus-source-acquisition.jsonl','catalogues/abaqus-reconciliation.json'],source_ids=['abaqus-D02','abaqus-D03'],scope='2025 keyword browser/reader complete name+detail-URL index; parameters/aliases within keywords are not separate denominator entries',entry_count=600,count_unit='unique keyword name/detail locator pairs',completeness='complete-index',reconciliation=rec,full_field_review_complete=False),rules=rules,examples=examples,code_assets=code_assets,coverage=coverage,
acquisition_log=[dict(target='2025 keyword browser and input-reader indexes',outcome='600/600 unique names and locators agree exactly; no unmatched rows; all 600 linked keyword pages acquired and have non-error HTML titles'),dict(target='Direct Dassault documentation portal',outcome='Public documentation portal located; versioned full reference was acquired at clearly labeled Virginia Tech mirror, not independently vendor-hosted crosschecked'),dict(target='2025 official input resources',outcome='6 actual inp files acquired; 4 small complete examples read; 1 large deck headers only; flange has external dependencies; guessed ec3d8.inp/pframe.inp returned 404'),dict(target='Public generator/parser candidates',outcome='Pinned MIT meshio adapter/test/license and abqpy compression example/license acquired. Limited mesh writer and runtime-dependent script classified separately; no solver execution')],
gaps=list(missing.values()),runtime_verified=False)
(ROOT/'solvers').mkdir(exist_ok=True)
(ROOT/'solvers/abaqus.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
# Mark only the individually read keyword sections, never every downloaded page.
path=ROOT/'catalogues/abaqus.csv'
rows=list(csv.DictReader(path.open()))
read_names={x[2] for x in keywords}
for row in rows:
    if row['name'] in read_names:row['read_depth']='relevant-sections'
with path.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps({'sources':len(sources),'rules':len(rules),'official_example_files':len(examples),'keyword_entries':len(rows),'keyword_sections_read':sum(x['read_depth']=='relevant-sections' for x in rows),'runtime_verified':False}))
