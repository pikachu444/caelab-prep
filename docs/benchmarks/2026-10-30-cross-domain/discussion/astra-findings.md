# Astra 독립 교차감사 결과

2026-10-30. `protocol.md`·`astra-checklist.md`와 기존 CAE `common-assets.md`·`method.md`를 기준으로 여섯 분야의 JSON·노트를 읽었다. 모든 원문을 다시 수집하거나 실제 앱을 실행한 감사가 아니다. 아래 핵심 주장에 대해 공식 원문 표본을 대조하고, 전체 등록 자료의 참조·파일 메타데이터를 검사했다.

## 판정

현 조사 묶음은 공백을 명시한 보충 조사로 닫을 수 있다. 감사한 핵심 표본에서 API 지원을 CAE 작업 완료, 문서 rollback, solver 정체성 또는 실제 재현으로 확대하는 중대한 오류는 찾지 못했다. 작은 전제 누락·locator·조작 경로는 아래와 같이 보강했다. 전체 사용자 작업·구현 준비·상용 동등성이 검증되었다는 판정은 하지 않는다.

## 수정·보강 기록

| ID | 위치 | 확인한 문제와 조치 | 상태 |
|---|---|---|---|
| A01 | jobs-P08 | context 소멸에 따른 continuation 취소에서 앞선 future가 계속 실행될 수 있다는 QFuture 원문 반례를 명시하도록 요청. root가 앞선 계산 비취소를 추가했다. | 수정 확인 |
| A02 | engineering-input-S01/S02·노트 | Qt 6.12 문서 버전과 실제 예제 이미지의 캡처 build를 분리하도록 요청. 캡처 build 미표시를 추가했다. | 수정 확인 |
| A03 | engineering-input-D12/P07 | 고정 소스의 pasteIntoSelection은 1836–2125행에서 끝난다. 다음 함수까지 포함하던 2141행 locator를 좁혔다. | 수정 확인 |
| A04 | shell-D19/P11·engineering-input-P02 | QInputMethodEvent의 commit/preedit Undo 규칙에는 ‘Undo/Redo를 구현한 위젯’이라는 전제가 있다. custom editor에 Undo가 자동 제공된다고 읽히지 않도록 양쪽에 전제를 추가했다. | 수정 확인 |
| A05 | selection-P07 | QGIS의 Apply 외에 ‘해당 form 왼쪽 패널에서 다른 feature 클릭’도 문서상 적용 trigger다. 담당자가 이 경로를 추가하고 미확인 범위를 다른 선택 경로·삭제·invalid draft로 좁혔다. 모든 선택 변경의 자동확정이라는 일반화도 금지했다. | 수정 확인 |

## 원문 표본 대조

아래 ID의 URL·정확한 절은 각 `domains/*.json`에서 추적할 수 있다. GitHub raw/blob 일부 URL은 감사 시 web 접근이 거절되어, 문서 분야와 LabPlot 코드는 담당자가 확보한 고정 원문 파일을 재독했다. 이를 감사자가 별도로 재다운로드한 증거로 세지 않았다.

| 분야 | 실제 대조한 표본 | 결과와 제한 |
|---|---|---|
| jobs | jobs-D01/D04/D05/D06/D12/D13: QProcess, QFuture, QSaveFile, subprocess, Concurrent Run, QgsTask | Windows 동명 terminate 차이, cooperative 취소, basic/promise 모드 차이, direct-write fallback, layer 제거 취소의 범위가 보존된다. A01 보강. |
| engineering-input | D03/D04/D06/D20의 Qt 원문과 D12 pinned paste 함수 | setText·위젯 Undo·IME 전제, 단순 목록 fetch 예제의 범위가 맞다. paste macro를 실패 rollback으로 주장하지 않는다. A02–A04 보강. |
| shell | D03/D11/D17/D19의 VS Code contribution, QMainWindow, High DPI, QInputMethodEvent | 노출/활성화, layout 상태, logical/device 좌표, IME를 도메인 명령·실제 혼합 DPI 검증과 구별한다. A04 보강. |
| document | D23 OCAF 웹 원문; D01/D12/D14/D16의 보유 고정 원문 | Name 재사용, document-local ID, 부분 로드 문서 save의 true 반환, OCAF Undo 활성화·attribute 참여·문서별 transaction 전제가 확인된다. 실제 왕복·실패 복원은 미검증으로 유지한다. |
| mesh-data | D06/D07/D08의 PyVista extract_surface/copy/cell_quality | 원본 ID 배열의 후속 연산 영향, shallow 공유, 미정의 품질 기본값을 각각 문서 정체성·독립 snapshot·음의 Jacobian과 합치지 않는다. VTK/Gmsh 전체 구현을 재감사한 것은 아니다. |
| selection | D02/D11/D13/D19의 QGIS 표·form API, ParaView 선택, Rhino8 선택 | mixed/changed 값과 단일 Undo, transient/query/ID 선택, ambiguous pick 경로가 확인된다. API 버전과 사용자 문서 버전을 유지한다. A05 보강. |

독립 이미지 표본은 document-S09, mesh-data-S05, selection-S03을 실제로 열어 확인했다. 등록된 관측 문구와 맞는다. 특히 메시 품질 4분할 그림의 겹친 제목/색상막대를 좋은 UI 외관의 증거로 쓰지 않은 점, attachment Cancel을 실제 복원 증거로 쓰지 않은 점을 확인했다. 모든 51장을 감사자가 다시 시각 확인했다고 주장하지 않는다.

## 교차 경계 판정

| 경계 | 연결한 근거 | 남겨야 할 공백 |
|---|---|---|
| 표 셀 Undo ↔ 문서 transaction | engineering-input-P07/P08, document-P05, selection-P07 | 단일 Undo 명령과 invalid/중간 실패 시 전체 원자 rollback은 다르다. 실제 CAE draft·속성·참조 참여는 미확인. |
| 선택 ↔ action enablement | selection-P13, shell-P02/P06/P10, document-P04 | 필요한 신호와 API가 있어도 삭제·Undo·busy 전환 중 draft와 명령의 안전한 갱신 순서를 입증하지 않는다. 해당 coverage gap을 유지한다. |
| worker cancel ↔ 문서/파일 rollback | jobs-P03/P05/P07/P08, document-P05/P07, mesh-data-P04/P10 | 요청·실제 종료·이전 계산·공유 배열·임시 파일·문서 채택·외부 효과를 한 단계로 합치지 않는다. stale·다중 파일 원자성은 partial로 남는다. |
| topology/filter ↔ 참조 정체성 | document-P01/P09, mesh-data-P05/P08, selection-P08/P09 | CAD subshape, VTK/PV 원본 인덱스, solver native 번호가 서로 같거나 remesh 후 물리 의미를 자동 보존한다고 주장하지 않는다. |
| 표/곡선/단위 ↔ 표시·저장값 | engineering-input-P03/P04/P09/P10, selection-P11/P12 | 단위 차원·좌표계·DOF·재료 곡선 규칙·표시 decimation·GPU 보정의 책임이 구별된다. 실제 왕복과 양방향 선택은 미확인. |
| IME/키보드/DPI ↔ 실제 플랫폼 | shell-P09/P10/P11, engineering-input-P01/P02 | 문서의 계약을 Windows 한글 조합, 모니터 이동, viewport pick, 포커스 회귀 실행 결과로 보고하지 않는다. |

OpenRadioss를 첫 소비자로 삼는 공용 자산 맥락과 Workbench의 별도 job 소유권은 유지한다. 조사 원리·반례는 모델/DB/저장 구조의 채택 결정으로 서술하지 않았다.

## 버전과 확보 범위

- Qt jobs는 6.8.9 문서, shell/input은 6.12 계열 문서다. 같은 실행환경으로 검증하지 않았다.
- Calc 최신 도움말 26.8과 7.1 가이드 그림, LabPlot 2.12 문서와 별도 master 고정 소스는 분리되어 있다.
- FreeCAD 문서 snapshot과 현재 소스 snapshot, OCCT 현재 웹 안내서와 고정 소스는 서로 다른 근거다.
- VTK 9.4.2 소스·9.6.1/9.7 문서·PyVista 0.49.2를 하나의 실행환경으로 합치지 않았다.
- Blender는 소스 근거만 있다. 사용자 문서 접근 실패를 제품 기능 부재로 처리하지 않았다. Rhino8 사용자 도움말과 Rhino9 API/2018 예제도 분리한다.
- selection의 보유 그림은 QGIS 6개이며, mesh-data의 8개는 기술 예제 그림으로 UI 수에 넣지 않는다. 전체 이미지 수가 사용자 workflow의 충분성 지표는 아니다.

## 등록 자료 검사와 집계

여섯 JSON 모두에서 전역 ID의 중복, source/asset/pattern/coverage 연결 누락, 등록 파일 부재, 실제 이미지 치수 불일치, 등록 SHA 불일치, runtime_verified의 true를 검사했고 발견한 오류는 0건이다.

| 종류 | 검사 결과 |
|---|---:|
| 분야 source 등록 수 합계 | 125 |
| fragment를 제거한 고유 문서 URL | 124 |
| 실제 보유 이미지 등록 수 | 51 |
| 보유 파일 SHA-256 기준 distinct image | 51 |
| 기능 pattern record | 68 |
| 필수 coverage 항목 | 41 |
| coverage supported / partial / gap | 5 / 35 / 1 |

중복 원문은 shell-D19와 engineering-input-D06의 QInputMethodEvent 한 쌍이다. `supported` 다섯 항목도 좁은 API·상태 의미에 대한 문헌 지원이며 전체 사용자 작업의 완료 수가 아니다. 기존 CAE 제품 JSON의 전체 source URL 집합 및 156개 이미지 해시와 대조한 신규 묶음의 정확한 URL/바이트 해시 중복은 0건이다. URL 내용의 의미상 유사성이나 다른 crop의 시각적 중복까지 완전 판별한 집계는 아니다. 이전 corpus의 문서 수 정의를 이번 감사에서 변경하지 않는다.

자료 조사 종료와 실제 구현의 종단 검증을 구별한다. 삭제 중 draft·invalid 일괄 적용·취소/완료 경합·다중 파일 채택·재메시 참조·Windows 입력/배율·대용량 성능은 조사 결과에 남아 있는 확인 과제다.

마지막으로 `README.md`·`synthesis.md`를 읽어 분야 수량, 버전·미확인 상태, 기존 validation/stale/채택 계약을 유지하는 범위를 확인했다. A01–A05의 수정은 모두 재확인했다. 이번 한정 보충 조사에 대한 독립 교차감사를 종료한다.
