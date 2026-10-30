# 독립 Astra 감사 기준

2026-10-30. 수집 전에 합의한 `protocol.md`를 기준으로 작성했다. 본 문서는 감사 기준이며, 아래 항목의 통과·자료 확보·solver 실행을 선언하지 않는다. 외부 원본 수집이나 생성기 구현은 이 검토자가 수행하지 않는다.

## 1. 판단 원칙

- 공용 GUI/문서 기반, 기존 덱의 일부 field patch, 새로운 해석 모델의 native 생성은 서로 다른 범위다. 기존 자산의 존재를 신규 생성 명세·예제 확보의 대체 근거로 사용하지 않는다.
- 핵심 다섯 solver와 root가 추가 확인하는 OptiStruct·MSC Nastran의 두 BDF 변형에 동일한 Q01–Q12를 적용한다. keyword, alias, option, material law, command의 개수와 형식은 억지로 같게 만들지 않는다.
- 전체 index 확보, 개별 entry의 field 독해, 생성 metadata 추출, writer 구현, solver read/run은 각각 독립적인 상태다.
- 접근 가능한 필수 자료를 조사하지 않은 채 소수 예제만으로 종료하지 않는다. 접근 불가·판본 부재 등은 실제 시도와 남는 영향을 기록한다.
- Code_Aster의 `.comm`·`.export`·MED, Radioss의 Starter/Engine 등 형식별 책임 경계를 유지한다. 외부 process 취소와 native interrupt/restart도 구분한다.

## 2. 분모·목록 감사

- [ ] 문서판·공식 URL·권/장/절과 포함·제외 범위가 고정돼 있다.
- [ ] 문서판, 예제판, 소스 revision, 시험 binary판이 각각 기록돼 있다. 미확인은 미확인으로 표시한다.
- [ ] OptiStruct와 MSC Nastran의 BDF catalogue·문법·지원 옵션을 별개로 기록한다. 공통 writer의 format 지원을 두 solver의 모든 카드/옵션 호환성으로 확대하지 않는다.
- [ ] 목록의 각 entry가 공식 이름·종류·source ID·실제 locator를 갖는다.
- [ ] 추출기와 사용한 입력이 추적되며, 출력 건수를 실제 파일에서 재계산할 수 있다.
- [ ] 공식 목차/index와 대조한 결과가 있고, 누락·중복·alias·variant·교차참조·미파싱을 구별한다.
- [ ] 페이지 번호와 PDF 물리 page index를 혼동하지 않으며, 확인하지 않은 anchor를 만들어 넣지 않는다.
- [ ] `complete-index` 주장이 정확히 무엇의 전체인지 명시한다. 해당 release 전체와 선택한 한 권/하위체계 전체를 혼동하지 않는다.
- [ ] 여러 권에서 같은 keyword가 반복되거나 하나의 heading에 여러 keyword가 담긴 경우 집계 규칙을 밝힌다.
- [ ] full-field review와 runtime verification이 목록 확보만으로 true가 되지 않는다.

## 3. 원본·출처·읽기 깊이 감사

- [ ] `sources`의 source ID가 유일하며 모든 참조가 실제 등록 source를 가리킨다.
- [ ] 링크 확인·metadata만 확인·index 추출·원본 다운로드·관련 절 독해를 정확히 구분한다.
- [ ] 다운로드를 주장한 파일이 존재하며 크기·SHA256이 실제 바이트와 일치한다.
- [ ] 리디렉션·접근 오류·일부 다운로드·HTML 오류 페이지를 매뉴얼 원본으로 세지 않는다.
- [ ] 규칙의 locator가 해당 규칙을 직접 뒷받침한다. index 또는 제품 소개만으로 field/default/dependency 규칙을 확정하지 않는다.
- [ ] 문서와 소스가 다른 판본이면 그 차이를 밝히고 호환성을 임의로 확정하지 않는다.
- [ ] 공식 문서, 공식 공개 구현, 제3자 writer/설명 자료의 소유와 역할을 구분한다.
- [ ] 원문 분량을 과도하게 복제하지 않고 자체 요약과 사실형 이름/locator 목록을 사용한다.

## 4. Q01–Q12와 생성 지식 감사

Q01–Q12마다 rule ID·source·locator·독해 범위·미확인 항목이 연결돼야 한다. `documented`는 해당 규칙의 근거가 있다는 의미이며 solver 전체 명세의 완전성을 뜻하지 않는다.

- [ ] Q01: 최소 구조와 파일별 역할·실행 경계가 실제 자료로 뒷받침된다.
- [ ] Q02: 구문·필드 폭·연속행·주석·수치 표기의 적용 조건이 구별돼 있다.
- [ ] Q03: solver가 요구하는 단위 일관성과 명시 단위 선언·변환을 혼동하지 않는다.
- [ ] Q04: 필수·선택·blank·zero·default·조건부·반복행·별칭을 구분한다. 예제에 채워진 값과 공식 default를 동일시하지 않는다.
- [ ] Q05: include·경로·중첩·순서·parameter/transform을 확인한 범위만 서술한다.
- [ ] Q06: ID/이름의 종류별 namespace·범위·충돌·참조 순서를 확인한다.
- [ ] Q07: 요소 family/차수별 순서·면/방향·퇴화와 외부 mesh 형식의 경계를 확인한다.
- [ ] Q08: mesh·part/assembly·material·property/section·set/surface의 관계를 구문과 연결한다.
- [ ] Q09: 하중·구속·초기조건·좌표계·접촉·곡선의 참조와 활성 조건을 확인한 범위로 한정한다.
- [ ] Q10: step/case·해석 제어·restart/interrupt·output 요청을 구별하며 외부 취소를 같은 것으로 세지 않는다.
- [ ] Q11: 완전한 입력/부분 snippet, 정상/오류 예제, 문서 정답/실측 결과를 구별한다.
- [ ] Q12: parser가 읽는 범위, writer가 생성하는 범위, solver가 지원하는 범위를 구별한다.
- [ ] 형식상 해당하지 않는 질문은 근거와 차이를 설명한다. 빈칸이나 미조사를 `해당 없음`으로 숨기지 않는다.

## 5. 예제·코드·권리 감사

- [ ] 예제의 원본 URL·파일·version·SHA256·공식성/출처가 추적된다.
- [ ] 여러 파일이 필요한 예제는 include, mesh, 재료, 실행설정 등 의존 파일의 보유/결손을 표시한다.
- [ ] 예제를 보유한 것과 자체 writer가 생성한 것을 구분한다.
- [ ] expected 결과가 원문에서 제시됐는지, 실제 실행 결과인지, 아직 미확인인지 구분한다.
- [ ] 공개 source의 role을 writer/generator/converter/parser/solver-reader/schema로 구분한다.
- [ ] 코드의 정확한 revision·파일/함수·실제 지원 범위·누락·의존성이 확인된다.
- [ ] repository를 내려받은 것만으로 writer 실행/재사용 가능성을 확정하지 않는다.
- [ ] license/notice가 실제 해당 코드·예제에 적용되는 근거가 있다. 주변 repository의 license를 외부 예제에 무조건 전용하지 않는다.
- [ ] 허용되지 않거나 불명확한 상용 매뉴얼 전문·예제 원본을 공개/다운로드 배포물에 넣지 않는다.
- [ ] 허용 code/example을 배포할 때 필요한 license/notice와 원 출처가 같이 들어 있다.

## 6. 실행·집계·최종 표현 감사

- [ ] 실제 solver 실행 주장은 binary version·명령·입력·로그·결과와 연결된다. 미실행은 false다.
- [ ] parser 재읽기, solver Starter/read 성공, 계산 완료, 수치 정답 검증을 구분한다.
- [ ] URL·manual file·catalogue entry·example·code asset의 집계 단위와 중복 제거 규칙이 명시된다.
- [ ] summary 수치가 JSON·catalogue·실제 배포 파일과 일치한다.
- [ ] 핵심 다섯 solver와 두 BDF 변형 각각의 링크/원본/index/관련절/예제/코드/실행 상태를 따로 보고한다.
- [ ] ‘모든 것 조사’, ‘완전한 생성 schema’, ‘전체 keyword 지원’처럼 현재 증거를 넘는 표현이 없다.
- [ ] 미확인 목록에는 무엇이 부족한지와 그 부족이 어느 생성 기능 판단을 막는지가 적혀 있다.

## 7. 최종 토론과 감사 결과

각 담당자의 산출물과 자기점검 이후, 공통 의미의 차이·누락·집계 문제를 다시 토론한다. 독립 감사는 발견 사항을 `사실 오류`, `확보/완료 과장`, `누락`, `표현/추적성 개선`으로 분류하고 근거 위치와 수정 필요성을 남긴다. 수정된 실물과 집계를 다시 확인한 항목만 닫는다. 감사 종료는 조사 산출물의 정확성에 대한 판단이며 solver 지원 구현이나 전수 field 검증을 뜻하지 않는다.
