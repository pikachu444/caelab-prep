# 솔버 입력 생성 자산 수집·검토 합의

2026-10-30. root, 독립 Astra, RAD 담당, LS-DYNA 담당이 수집 전에 토론했다. GUI 참조 자료와 기존 field patch/회귀시험은 입력 생성 규격의 전수 확보를 대신하지 않는다. 목적은 공용 CAE 기반과 솔버별 생성 자산을 위한 실제 문서·목록·코드·예제 확보다. 이번 작업은 생성기/GUI 구현, 신규 솔버 지원 주장, DB·검색 구조 설계가 아니다.

## 범위와 소유

주 조사 솔버는 Radioss/OpenRadioss/OpenCourant, LS-DYNA, Abaqus, CalculiX, Code_Aster다. root는 OptiStruct 2025와 MSC Nastran 2024.2의 BDF 입력 자산을 추가로 조사·통합한다. 총 7개 솔버 계열이며 OptiStruct/Nastran의 공통 BDF 형식을 지원 옵션의 동일성으로 일반화하지 않는다. 같은 기준은 동일한 조사 질문과 상태 구분을 뜻하며, 서로 다른 솔버의 command/keyword/재료 별칭을 같은 수량으로 강제하지 않는다.

각 담당은 `solvers/<key>.json`, `notes/<key>.md`, `catalogues/<key>.*`, `examples/<key>/`, `scripts/<key>*`, `tmp/<key>/`만 편집한다. 통합·공개 게시·다운로드 묶음은 root가 맡고 Astra는 별도 감사한다.

## 필수 조사 질문 Q01–Q12

1. Q01 — 파일 역할·확장자·버전 선언·최소 구조·Starter/Engine/step/command 실행 경계.
2. Q02 — keyword/command 구문·고정/자유/긴 형식·수치 표기·줄 연속·인코딩·주석.
3. Q03 — 단위 체계·명시/암묵·값과 표시·서로 다른 단위 문맥.
4. Q04 — 필수/선택·blank/zero/default·조건부·반복 행과 필드·별칭/variant.
5. Q05 — include·외부 참조·경로 기준·중첩·종료·순서·parameter/transform.
6. Q06 — native ID/이름 namespace·범위·중복·정의/참조·전방/후방 의존.
7. Q07 — node/element 연결 순서·면/side·방향·차수·퇴화 표현과 mesh-format 경계.
8. Q08 — part/assembly/material/property/section/set/surface 간 객체→입력 매핑.
9. Q09 — 하중·구속·초기조건·좌표계·접촉·곡선과 필수 참조/활성 조건.
10. Q10 — explicit/implicit·step/case·제어·restart/interrupt·결과 출력 요청. 외부 process cancel과 구분.
11. Q11 — 완전한 입력 예제·오류 예제·정답/관측의 출처와 공개 writer/generator/parser/solver-reader의 실제 범위.
12. Q12 — 버전별 지원·미지원·수치/의미 검증·실제 solver read/run 증거와 접근/재배포 제한.

관련성이 없으면 원문의 형식 차이와 사유를 명시한다. Code_Aster의 `.comm`/`.export`/MED를 억지 단일 keyword deck으로 다루지 않는다.

## 전수 목록과 조사 깊이

선택한 공식 문서 release·권/절을 먼저 고정한다. 공식 전체 keyword/command index를 실제 추출하며 임의 10–20개로 축소하지 않는다. 목록 entry는 원문 이름·종류(keyword/alias/option/command 등)·공식 locator·source ID·조사 깊이를 가진다. 색인과 별칭/변형·교차참조·중복·미파싱 수를 별도로 기록하고 공식 분모/목차와 대조한다. 확보하지 못한 index는 실패 경로·이유와 영향까지 명시하며 ‘전체 확보’로 부르지 않는다.

목록 전체 확보는 모든 keyword의 모든 field·의존관계 조사/생성 schema 완성 또는 실행 검증을 뜻하지 않는다. 개별 field 설명은 Q01–12에 필요한 관련 절을 실제 읽어 원문 locator와 연결한다. metadata/generator 후보는 해당 소스·함수·license·실지원/누락과 실제 파일을 확인한다. reader/converter/solver source를 writer 완성 증거로 쓰지 않는다.

## 산출물 JSON

```json
{
 "key":"dyna","title":"LS-DYNA","scope":"고정 문서/범위",
 "versions":{"documentation":"...","solver":"...","source":"commit/tag","examples":"...","binary_tested":null},
 "sources":[{"id":"dyna-D01","url":"https://...","title":"...","kind":"manual|index|api|code|example|license","version":"...","locator":"정확한 절/쪽/함수","access":"read|downloaded|blocked","read_depth":"index-parsed|relevant-sections|metadata-only|not-read","local_file":null,"sha256":null,"size_bytes":null,"redistribution":"locator-only|permitted-with-notice|unknown","summary":"짧은 독자 서술"}],
 "catalogue":{"files":["catalogues/dyna.csv"],"source_ids":["dyna-D01"],"scope":"Vol I–III 특정판","entry_count":0,"count_unit":"원문 색인 행","completeness":"complete-index|partial-index|unavailable","reconciliation":"추출/누락/별칭/분모 대조","full_field_review_complete":false},
 "rules":[{"id":"dyna-R01","question_ids":["Q01"],"source_ids":["dyna-D01"],"statement":"확인된 생성 규칙","locator":"정확한 절/쪽","examples":[],"limits":"미확인/차이","status":"documented|partial|gap"}],
 "examples":[{"id":"dyna-E01","source_ids":["dyna-D02"],"url":"https://...","file":null,"sha256":null,"version":"...","kind":"official-deck|source-example|self-authored","purpose":"...","expected":"문서가 제시한 결과 또는 미확인","license":"근거","redistribution":"locator-only|permitted-with-notice|unknown","solver_executed":false}],
 "code_assets":[{"id":"dyna-C01","source_ids":["dyna-D03"],"role":"writer|generator|converter|parser|solver-reader|schema","repository":"https://...","revision":"...","paths":["..."],"scope":"실제 처리 범위","limits":"...","license":"...","local_files":[],"executed":false}],
 "coverage":[{"question_id":"Q01","rule_ids":["dyna-R01"],"status":"documented|partial|gap","missing":"..."}],
 "acquisition_log":[{"target":"...","outcome":"..."}],"gaps":["..."],"runtime_verified":false
}
```

catalogue CSV/JSONL은 사실형 keyword/command 이름·URL/쪽/종류·관련 절 독해 여부로 제한한다. 상용 매뉴얼 설명을 통째로 복사하지 않는다. 출처당 독자 요약은 짧게 하고 장문 인용을 피한다. source ID는 분야 namespace로 유일하게 한다.

## 원본과 재배포

공식 원본을 실제 내려받으면 URL·버전·바이트 수·SHA256·읽은 범위를 기록한다. 매뉴얼 전문은 분석용 `tmp/`에 두고 공개/다운로드 배포물에 재게시하지 않는다. 공개 문서 접근과 재배포 허용은 다르다. 허용된 공개 code/example만 해당 license/notice를 함께 포함할 수 있다. 불명확한 예제는 원문 locator를 보존하고 자체로 완전한 수치 정답이나 저작권 허가를 발명하지 않는다.

## 종료·감사

공식 전체 목록의 확보/결손과 추출 대조, Q01–12의 근거/부분/공백, 실제 예제와 code 역할/버전/조건, 취득 상태·locator·해시를 기록하고 독립 지적을 수정하면 이번 수집 범위는 닫는다. 접근 가능한 필수 자료가 남아 있는데 임의 소수 예제로 축소해 완료 처리하지 않는다. 전수 field 검토·생성 schema·실제 실행은 별도 축이며 미수행은 false다. 제품 수/URL 수를 충분성 기준으로 쓰지 않는다.

최종 비교는 ‘링크 확인/실제 원본 취득/전체 색인 추출/관련 규칙 독해/예제 보유/생성 code 범위/실제 실행’을 각각 보고한다. 일곱 솔버 계열의 전체 keyword 지원이 제품에 구현됐다는 주장은 하지 않는다.
