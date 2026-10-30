# 비 CAE 프로그램·기술문서에서 공용 CAE 기능을 배우기

2026-10-30. 기존 [7제품 CAE GUI 벤치마크](https://github.com/pikachu444/caelab-prep/blob/main/docs/benchmarks/2026-10-30/README.md)의 기능 근거를 넓힌 보충 조사다. root·Astra·담당자들이 방법과 경계를 먼저 토론한 뒤 여섯 분야를 수집하고 독립 검토했다. GUI/메셔 구현, DB·검색·Semantica 구조 설계, 기존 실행 계획의 범위 변경은 이번 작업이 아니다.

**방향은 제품 하나를 통째로 따라 만드는 것이 아니라, 필요한 기능마다 사용자 동작과 구현 근거를 대조하는 것이다.** 상용 CAE 자료는 CAE의 사용자 작업과 물리 의미의 기준으로 유지한다. IDE·CAD·GIS·시각화·과학 데이터 프로그램과 기술문서는 명령·편집·선택·참조·수치·성능·작업 수명의 구현 근거를 보충한다. 어느 프로그램/라이브러리를 채택했다고 결정한 자료가 아니다.

## 분야별 조사물

| 분야 | 비교한 주요 원천 | 원문 등록 | 보유 그림 | 기능 근거 묶음 | 상세 |
|---|---|---:|---:|---:|---|
| 셸·명령·도킹·아이콘·DPI | Qt Creator, Designer, VS Code, Qt/PySide6 예제, KDE HIG | 23 | 11 | 12 | [노트](notes/shell.md) · [근거](domains/shell.json) |
| 선택·가시성·다중 편집 | QGIS, ParaView, Blender 소스, Rhino | 23 | 6 | 14 | [노트](notes/selection.md) · [근거](domains/selection.json) |
| 문서·정체성·참조·Undo·저장 | FreeCAD, OCCT/OCAF/XDE, AutoCAD 반례 | 25 | 14 | 11 | [노트](notes/document.md) · [근거](domains/document.json) |
| 공학 수치·표·곡선·단위 | Calc, LabPlot, Qt, Pint, pyqtgraph | 22 | 9 | 11 | [노트](notes/engineering-input.md) · [근거](domains/engineering-input.json) |
| 메시·표시 데이터·품질 | Gmsh, VTK/PyVista, MOAB, CGAL | 18 | 8 | 10 | [노트](notes/mesh-data.md) · [근거](domains/mesh-data.json) |
| 긴 작업·취소·산출물 수명 | QGIS, VS Code, Qt, Python, Win32 | 14 | 3 | 10 | [노트](notes/jobs.md) · [근거](domains/jobs.json) |

등록은 125건이지만 Qt IME 원문 1개가 두 분야에서 공유돼 **중복을 제거한 원문 URL은 124개**다. 그림은 파일 SHA256 기준 **51개**, 기능 근거 묶음은 **68개**다. 원문은 사용자 매뉴얼·설계 지침·API·코드·예제를 포함한다. 그림에는 UI 외에도 기술 설명·모델/품질 그림이 들어 있다. 68개 묶음은 원문과 그림을 연결한 설명이므로 추가 자료로 합산하지 않는다.

이전 GUI 묶음과 URL/그림 바이트 중복은 없었다. 두 묶음 기준으로 원문 URL 234개와 그림 207개다. 이 수치는 앞선 세션 전체의 메셔 논문·설계 조사까지 합친 전역 수량이 아니다. 다른 URL이 곧 독립된 저자/근거라는 뜻도 아니며 매뉴얼 전문 124개를 오프라인 저장했다는 뜻도 아니다. 계산 규칙과 내역은 [summary.json](summary.json)에 있다.

## 후속 개발자가 읽는 순서

1. [취합 결론과 기능별 활용](synthesis.md)에서 필요한 공용 기능을 고른다.
2. 분야 노트에서 비교·버전·반례를 읽고 JSON의 pattern ID에 연결된 원문·API locator를 확인한다.
3. 해당 패턴의 `failure_cancel_undo_save`, `non_transferable`, `unknowns`를 함께 읽는다. UI 근거와 API 근거가 다른 버전/예제면 같은 재현으로 합치지 않는다.
4. 실제 구현 단계의 입력·종료 조건은 기존 실행 작업서를 따른다. 이번 문헌 조사로 실제 Windows·대용량·솔버 검증이 통과한 것으로 처리하지 않는다.

별도의 다운로드 묶음에는 이 텍스트/JSON과 등록 그림, 인터넷 없이 열 수 있는 `index.html`을 넣었다. Git에는 출처/locator·독자 서술·그림 메타데이터만 둔다. JSON의 `assets[].file`은 다운로드 묶음 기준 경로이며 Git에 없는 파일을 뜻한다. 원본 이미지는 `source_url`로도 찾을 수 있다. vendor 프로그램·매뉴얼 전문·제품에 편입할 아이콘 원본은 포함하지 않는다. 기존 GUI 묶음은 별도 자료이며 이 ZIP에 중복 수록하지 않았다.

## 조사 종료와 구현 완료의 구분

필수 묶음에 근거·대안/반례·공백과 개발 영향을 기록하고 교차검토했다. 이 한정 조사 작업의 종료 조건이다. `supported`는 기록된 좁은 문헌/API 계약의 지원이며 전체 사용자 작업이 준비됐다는 뜻이 아니다. 전체와 모든 패턴의 실제 실행 검증은 false이며 제품 직접 실행 R·연속 영상 관찰 V는 0이다. 정상/오류/취소/Undo/저장·재열기의 종단 검증과 상용 수준 동등성은 확인하지 않았다.

특히 선택 대상 삭제 중 편집 draft, 실행 중 입력 개정과 stale 결과, 여러 파일/문서의 원자적 채택, 복잡 형상 교체/재메시의 참조 유지, 백만 요소 편집, 실제 한글 IME·혼합 DPI는 남아 있다. 이 공백을 새로운 자체 정책이나 동작 추정으로 채우지 않았다.

[사전 합의](discussion/protocol.md) · [독립 감사 기준](discussion/astra-checklist.md) · [독립 감사 결과](discussion/astra-findings.md) · [통합 검증](audit.md)
