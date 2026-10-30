# 독립 Astra 감사 기록

2026-10-30. `discussion/protocol.md`와 `discussion/astra-checklist.md`를 기준으로 실제 JSON·목록·원본·예제와 집계를 대조했다. 핵심 5종과 OptiStruct·MSC Nastran의 확보 주장에 대한 최종 감사 기록이다. 실제 solver 실행, 전수 field 의미 검증 또는 신규 원본 수집을 수행한 감사가 아니다.

## 1. CalculiX — 1차 실물 감사

상태: **핵심 확보 주장 확인, 추적성/공백 표기 2건 수정 후 확인**. 현재까지 생성 지원·실행 완료로 부풀린 사실 오류는 찾지 못했다.

### 직접 확인한 내용

- `solvers/calculix.json`의 local source 원본 파일들이 존재하며 기록한 크기와 SHA256이 모두 일치한다.
- catalogue CSV/JSONL은 각각 143개다. 공식 HTML archive의 각 member를 직접 읽어 143개 SHA를 전수 대조했다. 불일치 0개다.
- 공식 TeX archive의 별표 keyword subsection을 독립 추출해 143개 이름을 대조했다. 이름 집합의 양방향 누락 0개다. 이 분모는 CCX 2.23 매뉴얼의 keyword subsection이며 parameter/element type/모든 alias의 수가 아니다.
- catalogue의 독해 상태는 관련 절 19개, index 추출만 124개다. 전체 143개를 field 수준으로 읽었다고 서술하지 않는다.
- 공식 test archive의 1,511개 실제 파일과 manifest를 전수 대조했다. 638개 입력, 855개 reference, 18개 support이며 누락·크기·SHA 불일치 0개다.
- 배포 대상 `ccx-2.23-readinput.c`, `cgx-2.23-write2aba.c`는 원 archive member와 바이트가 같다. 원본의 GPL 고지와 별도 license 파일이 존재한다. reader와 부분 writer의 역할을 구분한다.
- MIT 예제의 license 파일과 고정 commit 표기·CGX가 먼저 생성해야 하는 의존 파일 설명을 확인했다. 해당 `.inp`를 standalone 생성 검증 덱으로 세지 않는다.
- Q03 단위, Q05 include 깊이와 reader의 파일 열기, Q06 reader 재정렬, Q10 `DYNAMIC`의 parameter 생략/값 생략 차이·`RESTART`·`OUTPUT` 규칙을 로컬 공식 원문과 직접 대조했다. 기록한 제한된 규칙을 지지한다.
- PrePoMax는 master snapshot과 pinned commit-byte 동등성/권리 미확인을 분리하고 분석용으로만 둔다. binary/solver 실행 주장은 false다.

### 보완 요청

| ID | 분류 | 요청 | 상태 |
|---|---|---|---|
| CCX-A01 | 공백 표기 | Q11의 오류 입력 예제를 실제 선정/확보했는지 명시. 미선정이면 coverage/gaps에서 분명히 남길 것 | 수정 확인: 오류/expected-failure 미선정, beamperror와 구별 |
| CCX-A02 | 추적성/집계 | D09는 선택 MIT 파일 11개를 보유하지만 source row가 `read`/local null이다. 개별 URL·크기·SHA manifest 또는 동등한 기록으로 실제 다운로드 집계를 명확히 할 것 | 수정 확인: 11파일 manifest·33,763 bytes, 각 실파일 hash/크기 일치. D09의 manifest와 원본 수를 구별 |

## 2. 교차 토론에서 확인할 생성 영향

다음은 담당자 간 대조 결과로 전달받은 쟁점이며, 각 최종 출처·판본·locator의 실물 대조 전까지 여기서 별도 검증 완료로 표시하지 않는다.

- Abaqus와 CalculiX의 `OUTPUT`, `STATIC,EXPLICIT`, `DYNAMIC,EXPLICIT`, PART/INSTANCE/ASSEMBLY와 namespace 차이: 동일 keyword 이름을 공통 생성 규칙으로 사용하면 생략값의 의미가 달라지거나 미지원 입력을 출력할 수 있다.
- OptiStruct 2025와 MSC Nastran 2024.2의 CTETRA PID default/필수 차이: 같은 BDF 형태라고 PID 생략을 공유하면 한 solver에서 오류나 잘못된 참조를 만들 수 있다.
- include 깊이·경로 탐색·입력 구역 차이: 파일을 배치하고 include를 작성하는 생성기의 직접 제약이다. 원문 적용조건과 버전을 함께 기록해야 한다.

이 반례들은 공용 모델/GUI 개발을 중단할 이유가 아니다. solver별 생성 제공자의 명세가 실제로 필요하다는 근거이며, 이번 조사의 본래 공백과 직접 연결된다.

## 3. Abaqus — 1차 실물 감사

상태: **핵심 확보 주장 확인, 원격 source 독해 추적성 보완 확인**. 게시를 막는 사실 오류는 찾지 못했다.

- JSON에서 local_file을 갖는 모든 source의 실제 파일·크기·SHA256이 일치한다.
- 원본 취득 manifest의 602행(2개 index·600개 detail)을 전수 대조했다. 실제 파일·크기·SHA 불일치 0개다.
- keyword browser와 reader 표를 독립 재추출했다. 각각 600개 이름/상세 URL이며 catalogue 600행과 양방향 차이 0개다.
- 원본 Keywords Guide(D01)가 browser 표를 모든 Abaqus keyword의 목록으로 안내한다. 선택한 2025 vendor-origin mirror의 전체 keyword 분모를 지지한다. 직접 vendor 호스팅 동일판 대조까지 했다는 뜻은 아니다.
- 600개 상세 HTML의 title 및 catalogue anchor를 실제 파싱해 확인했다. 모두 해당 keyword와 연결된다.
- 개별 keyword 독해 15개, index 수준 585개를 구별한다. 600개 원본 다운로드가 전수 field 독해·생성 schema 완성·제품 지원 또는 runtime 검증으로 바뀌지 않는다.
- 구문/blank/default, 단위·단위 전송, include 5단계/작업 디렉터리, ID/set namespace, solid face 표, solid 검증 예제의 원문 기대 응력/변형률을 직접 대조했다. 현재 요약한 제한된 규칙을 지지한다.
- 공식 `.inp` 6개는 분석용 파일로 존재한다. 작은 4개·대형 헤더 확인·외부 의존 확인을 구별하고 원본의 재배포 허가 미확인, 오류 덱 미확보와 solver 미실행을 명시한다.
- meshio의 mesh/set writer와 완전한 해석 모델 writer를 구별한다. abqpy 예제는 실제 Abaqus runtime 의존 예제로 기록한다. 공식 test mesh를 MIT source 고지로 일괄 재배포하지 않는다.

| ID | 분류 | 요청 | 상태 |
|---|---|---|---|
| ABQ-A01 | 독해 추적성 | C06 `ModelJob.writeInput` stub 주장은 local_file이 없어 직접 로컬 대조하지 못함. 원격 독해 경로/정확한 locator를 담당자에게 확인 요청 | 담당자 pinned GitHub fetch 재확인: 295행 signature, 305행 `...`; 원장에 acquisition route·blob SHA·locator 추가. 로컬 원본 취득으로 집계하지 않음 |

집계 주의: 이 자료의 `access=read` source도 `local_file`·SHA·실파일이 있으면 실제 취득 원본이다. access 문자열만으로 다운로드 수를 세면 과소 집계된다. 반대로 여러 source record가 같은 local 원본을 가리키면 원본 파일 수를 중복 집계하지 않는다.

## 4. Code_Aster — 1차 실물 감사

상태: **핵심 확보 주장 확인, lexical 수량의 정의 표현 보완 확인**.

- 57 source의 local 원본 크기/SHA와 공개 참고 source manifest 407개 파일(Code_Aster338·AsterStudy69)의 크기/SHA를 전수 확인했다. 불일치 0개다.
- Cata Commands의 270 Python 파일을 독립 AST parse했다. 268 Command(OPER135·MACRO116·PROC15·FIN_PROC1·FORM1), VariableSupport 도우미 1개, bootstrap 1개를 확인했다. catalogue 269개 이름과 차이 0개다. source를 import하거나 실행하지 않았다.
- 공식 manual index의 article에서 270개 문서 locator를 독립 추출했다. CSV와 차이 0개다. source 이름 중 exact-title match가 없는 세 항목 및 여러 이름을 포함하는 문서 4개도 재계산해 일치했다. 제목 불일치를 미지원/문서 부재로 일반화하지 않는다.
- 실제 `.export`가 `.comm/.datg/.mmed`를 선언하고 모두 보유한다. MED 파일의 HDF5 signature와 510,938 bytes를 확인했다. 이것은 MED reader 검증이나 해석 실행이 아니다.
- v17 POURSUITE §1 원문을 직접 읽었다. 저장 base가 있으면 DEBUT도 재개하며 POURSUITE를 호환 목적으로 유지한다는 서술을 지지한다. 예제의 TEST_RESU는 상류 기대값이며 이번 관측 결과로 표시하지 않는다.
- Cata schema, `.export` profile writer, AsterStudy `.comm` serializer/importer, libaster/MED/runtime을 구분한다. 문서 branch v17·source17.5.8·AsterStudy commit의 판본 차이를 명시한다.

| ID | 분류 | 요청 | 상태 |
|---|---|---|---|
| AST-A01 | 집계 정의 | SIMP12604/FACT1130/BLOC1530은 전체 파일 AST가 아니라 top-level Command 선언 호출 subtree의 수다. 전체 파일 AST에는 로컬 helper를 포함해 SIMP12624/FACT1131/BLOC1538이 나온다. 기존 수량을 유지한다면 설명을 subtree 및 helper/factory 미확장 기준으로 정밀화할 것 | 수정 확인: notes·structure·JSON·재현 script에 정확한 subtree/helper 제외 정의 반영 |

## 5. LS-DYNA — 실물 감사 완료

상태: **핵심 확보 주장 확인, 질문 존재 검사 명칭 보완 확인**.

- 24 source 중 로컬 취득 원본의 크기/SHA, PyDYNA 36개 원본 및 배포본의 크기/SHA(23,271,877 bytes)를 전수 대조했다. 불일치 0개다.
- 전체 raw schema를 직접 열어 3,685 specs·12,219 cards·69,523 fields를 재계산했다. 원장 수치와 일치한다. 이 개수는 field 의미 검증의 통과 수가 아니다.
- 공식 PDF에서 추출한 4,301/2,244/828 페이지 텍스트의 전체 TOC를 독립 재추출했다. 2,030행이 CSV와 일치하며 starred 1,773행의 실제 target header도 전수 대조해 불일치 0개다. 원문 TOC 오류 2개와 보정 locator를 구별한다.
- 1,773행/고유 literal1,750/family heading58의 분모를 구별한다. 관련 절 독해 28행, index-only1,745행이다. raw schema와 exact-name 일치 1,544행을 다시 확인했으며 이를 의미적 coverage나 229개 미지원으로 해석하지 않는다.
- 공식 ZIP의 실제 `.k` 82개와 예제 manifest의 파일 집합·크기·SHA가 전수 일치한다. vendor 원본은 분석용이며 v971/2013의 기대 결과를 R17 실행 결과로 바꾸지 않는다.
- `CONTROL_IMPLICIT_GENERAL`의 blank/zero/DYN/SPR 상속 반례를 원문 1646쪽 텍스트와 직접 대조했다. PyDYNA writer/parameter/parser fixture와 완전 모델/solver 검증을 구별한다.

| ID | 분류 | 요청 | 상태 |
|---|---|---|---|
| DYN-A01 | 완료 표현 | `coverage_complete_q01_q12=true`는 12질문 레코드 존재만 검사하므로 전수 조사 완료로 오해될 수 있음 | 수정 확인: `all_q01_q12_have_status_records`와 검사 의미 설명으로 변경. field/variant/runtime false 유지 |

## 6. Radioss/OpenCourant — 실물 감사 완료

상태: **핵심 확보 주장 확인, 독해 분모 설명 보완**.

- 59 source 중 local 원본의 크기/SHA 및 상세 페이지 804개 실물의 크기/SHA를 전수 대조했다. 불일치 0개다.
- 공식 2024 Supported Keywords 구역을 독립 파싱해 Starter590·Engine235행을 확인했다. CSV825행과 이름/URL 집합 차이 0개다. 825는 정규화된 고유 keyword 수가 아니며 상세 URL은804개다.
- CSV의 관련 절 독해는35행/35URL, index-only790행이다. 담당자의 ‘선정 keyword33개’에 `#include`·`#enddata`2개를 더한 분모임을 확인했다. 일반 syntax/files 절은 별도다. 804개 다운로드를 전수 field 독해로 세지 않는다.
- 배포 code9파일의 실제 크기/SHA와 AGPL/MIT 원문 header·동봉 고지를 확인했다. 제한 CFG와 NC 모델의 조건을 상위 repository license로 덮어쓰지 않는다.
- 고정 source archive의 QA inventory341파일(그중 `.rad`166개)과 CFG inventory1,333파일을 원 archive member의 실제 크기/SHA로 전수 대조했다. 불일치 0개다. CFG1,331개 제한고지/2개 미분류 및 모델의 NC 표기를 공개 생성 자산의 무제한 사용 허가로 해석하지 않는다.
- Engine 구문의 `/RUN`·`/VERS` 의무 설명과 include의 완전 블록·작업 디렉터리 기준·`#enddata` 경계를 공식 로컬 원문과 직접 대조했다. 일부 QA/Tools의 `/VERS` 생략과 문서의 차이는 미검증 gap으로 유지한다.
- 문서2024·비교2026·역사PDF2022·OpenCourant source pin·각 예제 `/BEGIN`판·converter 기본2025를 분리한다. 실제 target binary read/run, 범용 RAD 생성기 구현, 재배포 가능한 NC-free 완전 시험쌍이 확보됐다고 보고하지 않는다.
- `notes/radioss.md`와 `examples/radioss/NOTICE.md`를 최종 패키징 전에 작성하도록 확인했고, NOTICE 실물에서 code/CFG/NC 모델/상용 매뉴얼의 분리를 확인했다.

## 7. OptiStruct / MSC Nastran — 실물 감사 완료

상태: **선언한 범위의 확보 주장 확인. 현행 MSC 완전 예제의 결손은 계속 명시해야 함**.

- OptiStruct36·MSC17 source 중 local 원본의 크기/SHA가 일치한다. OptiStruct 상세 페이지1,107개 및 예제 sidecar의 실제 원본/멤버 파일, NASA95 보조7파일의 크기/SHA를 전수 대조했다. 불일치 0개다.
- OptiStruct 공식 child-link 분모를 독립 대조했다. bulk597·I/O131·subcase118·PARAM option261이다. bulk 영역의 본문 각주 link1개를 entry로 세지 않은 것은 적절하다. 1,107은 같은 종류의 고유 keyword 수가 아니다.
- MSC QRG 실제 PDF는3,143쪽이며 전체 bookmark2,196개를 독립 재추출했다. 원장/전체 outline과 이름·depth·page 차이 0개다. 분류 목록1,879행(그중 bulk924)은 선택한 장/깊이의 혼합 topic 행이고, 전체 appendix/item-code의 정규화된 전수 keyword 목록이 아니다.
- CTETRA.PID의 OptiStruct default=EID와 MSC required, MSC INCLUDE 최대10단계·행72자, OptiStruct RESTART의 optimization 전용/analysis-mode 제외를 각각 로컬 원문과 직접 대조했다. 공통 BDF 모양에서 동일 default·파일 정책·restart 의미를 도출하면 안 된다는 반례를 지지한다.
- 공유 PyNastran reader whitelist429개는 writer의 각 solver 지원표가 아니다. source snapshot·작성 시험·정상 해석 실행을 구별한다.
- OptiStruct 공식 ZIP3개/.fem7개의 배포판2025와 예제 header2017.1을 분리한다. 원본은 재배포 제외다.
- NASA95 deck·archival output은 보조 참고자료다. **MSC Nastran2024.2의 공식 완전 예제·예상 오류 corpus 및 실제 solver 검증은 여전히 미확보/미수행**이다. NASA95 확보로 이 결손을 닫지 않는다.

## 8. 최종 판정

**선언한 수집 범위의 확보 사실과 분모·출처·권리·실행 상태를 공개하는 데 남은 blocking 지적은 없다.** 독립 감사에서 요청한 공백 표기·취득 manifest·원격 locator·AST 집계 정의·질문 존재 검사 명칭은 수정 또는 근거 보강됐다. RAD 독해35행의33+2 분모도 확인했다.

다만 다음 결손은 이번 수집 종료와 함께 그대로 공개해야 한다.

- 각 solver의 모든 field/default/조건부·dependency·variant를 의미 검증한 생성 schema는 완성되지 않았다.
- 모든 solver/예제/writer 실행·수치 정답 재현은 미수행이다. parser 보존·metadata·상류 reference 선언은 실행 증거가 아니다.
- MSC catalogue는 전체 outline과 범위를 정한 entry 분류이며, 모든 appendix/item code를 전수 정규화한 목록이 아니다. 현행 MSC 완전 예제는 NASA95 보조자료로 대체되지 않는다.
- RAD CFG/NC 모델과 상용 매뉴얼·예제는 원본 취득과 재사용/재배포 허용이 다르다. 최종 공개·다운로드 묶음은 기록한 제외 경계를 유지해야 한다.
- native 버전별 지원 mapping, 오류 corpus, 일부 완전한 reference bundle, source dependency closure가 남아 있다. 실제 구현 단계에서 해당 범위에 필요한 후속 확인을 해야 한다.

이 감사는 실제로 확보한 생성 자료를 과장 없이 닫는 판단이다. CAELab Prep의 신규 native generator, 다중 solver 제품 지원, 또는 입력 생성의 공학적 정확성 완료를 선언하지 않는다.
