# 비 CAE 프로그램·기술문서 보충 조사 합의

2026-10-30. root, 독립 Astra, 셸 담당, 문서 담당의 사전 토론을 거쳐 확정했다. 이번 작업은 분야별 자료 조사·취합이다. GUI/메셔 구현, 새 DB·검색·Semantica 구조 설계, 기존 제품/모델 계약 변경은 하지 않는다.

## 담당과 경계

| 담당 파일 | 책임 |
|---|---|
| shell | Qt/IDE의 action, 메뉴·단축키, 포커스, 도킹, 아이콘·HiDPI·접근성 |
| selection | Blender/QGIS/ParaView 등의 pick, 선택, 필터, 가시성, 격리, 트리·viewport 동기화 |
| document | FreeCAD/OCCT 등의 정체성·수명·참조, transaction/Undo, dependency, 저장·재열기 |
| engineering-input | 표·곡선·단위·수치·locale·붙여넣기·오류와 draft |
| mesh-data | 메시/표시 데이터의 tag·집합·배열·연결·변환, recipe·품질과 기술적 한계 |
| jobs (root) | 긴 작업, 취소·종료, thread/process, 진척·오류, 결과 채택과 stale 경계 |
| Astra | 수집과 별도로 주장·근거·이식 한계와 교차 경계를 감사 |

선택 담당은 일시 pick/preview/visibility를, 문서 담당은 저장되는 정체성·수명·참조를 맡는다. 표의 셀 Undo와 문서 transaction, 선택과 action enablement, 작업 중단과 문서 rollback은 교차 확인한다. Workbench의 기존 job 소유권을 변경하지 않는다.

## 조사 단위와 근거

제품 소개 대신 좁은 기능/상태 전이의 근거 묶음으로 수집한다. 실제 읽은 공식 사용자 문서와 API/소스/예제를 함께 연결하고, UI 동작과 API 보장을 서로 대체하지 않는다. 다른 버전·mode·예제를 하나의 연속 작업으로 이어 붙이지 않는다. 여러 제품의 정책을 비교하되 제품 수나 이미지 수는 충분성 기준으로 쓰지 않는다.

각 분야는 `domains/<key>.json`, `notes/<key>.md`, `assets/<key>/`만 편집한다. 원문 HTML·PDF 등 임시 다운로드는 `tmp/<key>/`에 두고 최종 배포하지 않는다. 실제 원문 이미지를 보유하고 시각 확인한 경우만 assets에 등록한다. 기술 계약에 그림이 필요 없으면 억지로 채우지 않는다. 공식 문서의 세부 화면·대화상자가 있는 분야는 필요한 상태별로 확보한다. vendor 원본 전체, 로고·아이콘을 제품 자산으로 재배포하지 않는다.

JSON 필수 형식:

```json
{
  "key": "shell", "title": "분야", "scope": "이번 조사 범위",
  "sources": [{"id":"shell-D01","url":"https://...","title":"...","product":"...","version":"명시 버전 또는 미확인","kind":"user-manual|api|code|example|paper|design-guideline","evidence_type":"D","locator":"절/anchor/함수/commit","read_status":"full-relevant-sections","summary":"독자적인 짧은 요약"}],
  "assets": [{"id":"shell-S01","source_ids":["shell-D01"],"source_url":"https://...","file":"assets/shell/name.png","width":800,"height":600,"kind":"screen|dialog|diagram","visual_review":true,"observations":"실제로 보이는 것만"}],
  "patterns": [{"id":"shell-P01","requirement":"필요 기능","products":["..."],"source_ids":["shell-D01"],"asset_ids":[],"prerequisite":"...","actions":["..."],"documented_result":"...","implementation_locator":"실제 API/소스/예제 위치","failure_cancel_undo_save":"확인된 범위와 미확인 구분","transferable":"CAE에서 참고할 원리","non_transferable":"동치로 취급하면 안 되는 의미","unknowns":["..."],"status":"supported|partial|gap","runtime_verified":false}],
  "coverage": [{"requirement":"필수 기능/상태","pattern_ids":["shell-P01"],"status":"supported|partial|gap","gap_reason":"..."}],
  "search_log": [{"query":"반례/대안/결손 검색","outcome":"..."}],
  "gaps":["..."], "runtime_verified":false
}
```

ID는 분야 namespace로 전역 고유하게 한다. source URL은 실제 읽은 원문만 등록한다. 검색 결과만 본 후보는 search_log/gaps에 두며 확보한 문서 수에 더하지 않는다. source.summary 및 그 URL에 근거한 모든 서술을 합해 원문의 요약 한도에 맞춘다. 긴 원문 인용/소스 복사는 하지 않는다. 미래 제품 도입이나 구현 가능성의 결론은 근거보다 크게 쓰지 않는다.

## 종료 조건

분야 시작 전에 필수 기능 묶음을 고정한다. 각 묶음에 사용자 목적/조작 근거, 관련 API·소스·예제 위치, 오류·취소·Undo·저장 중 관련 상태와 공백, 이식 가능한 책임과 금지 일반화를 기록한다. 서로 다른 접근·반례를 검색하고 남은 공백의 이유·개발 영향을 기록하면 이번 한정 조사 작업은 종료한다. 확인되지 않은 상태는 partial/gap으로 남는다. 자료 조사 종료와 구현 착수 준비·실제 재현·상용 동등성은 별개다. 실제 앱 실행이나 영상 연속 관찰을 수행하지 않았으면 V/R로 표시하지 않는다.

필수 교차 시나리오: 선택 객체 삭제 후 속성 draft/Undo; 다중 선택 mixed값/부분 적용; 붙여넣기 실패와 transaction; hide/isolate/filter와 선택; 표시 단위와 값 변환; CAD topology 변경 뒤 참조; job 시작 후 대상 수정/삭제·문서 닫기; GUI·script 명령의 의미; 한글/IME·키보드·혼합 DPI. 원문에서 답이 없으면 자체 정책으로 위장하지 않고 공백으로 기록한다.
