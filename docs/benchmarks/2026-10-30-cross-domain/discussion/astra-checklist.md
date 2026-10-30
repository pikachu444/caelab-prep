# Astra 독립 교차감사 체크리스트

2026-10-30. 기준: `protocol.md`, 기존 `common-assets.md`·`method.md`. 자료 수집·제품 실행·설계 선택의 결과가 아니라, 분야 산출물을 받은 뒤 적용할 감사 기준이다. GUI/메셔 구현, DB·검색·자료정리 구조, 모델 계약 변경은 범위 밖이다.

## 1. 주장과 근거

- 각 `pattern`의 source/asset 참조가 실제 같은 분야 자료를 가리키고, 원문 URL·버전·locator가 해당 주장을 확인할 정도로 구체적인가.
- 문서를 읽어 확인한 절차(D), 보유·시각 확인한 그림(S), 연속 영상 관찰(V), 직접 실행(R)을 혼합하지 않는가. API 문서와 정적 전후 그림은 실행 증거가 아니다.
- 사용자 목적·조작 근거와 API/소스/예제 근거를 연결하되, 후자가 GUI 노출·Undo·취소·저장을 자동 보장한다고 주장하지 않는가.
- 서로 다른 버전, mode, 예제, 입력 데이터의 결과를 하나의 연속 작업처럼 합치지 않는가.
- `documented_result`는 원문 동작, `transferable`은 참고할 책임/원리, `unknowns`는 결손으로 구별되는가. 참고 원리가 이미 확정된 공용 설계로 서술되지 않는가.
- `supported`는 기재된 좁은 요구의 문헌 지원일 뿐 전체 workflow readiness가 아님이 분명한가. 관련 실패·취소·Undo·재열기 결손은 coverage와 gaps에도 드러나는가.
- 실제 앱 실행을 수행하지 않은 전체/패턴의 `runtime_verified`가 false인가. 기존 corpus의 full-app V/R 부재를 새 문서 조사로 해소했다고 쓰지 않는가.

## 2. 분야별 의미 보존

| 분야 | 우선 감사할 구별 | 대표적인 금지 일반화 |
|---|---|---|
| shell | action 존재/활성화/실행 가능, shortcut context, focus와 입력, docking 저장 범위, logical/physical pixel | API 보유만으로 사용자에게 안전한 실행 경로·접근성·혼합 DPI 완성을 보장 |
| selection | preview/확정 선택, pick/filter, visible/selectable/selected, mode와 entity 범위 | Blender object/collection, GIS layer, pipeline output을 CAE solver entity/case와 동치로 취급 |
| document | 내부 정체성/name/native번호, 공유/복사/instance, 참조 수명, dirty/recompute, transaction/Undo, 부분 저장 실패 | 문서 객체 ID 안정성을 topology 변경 후 subshape 안정성 또는 solver ID 안정성으로 확대 |
| engineering-input | draft/확정값, 빈칸/0/NaN, 표시단위/저장값, locale/정밀도, formula/수치값, table/plot의 동일 데이터 | 일반 spreadsheet 자동 변환·부분 paste·수식 동작을 solver 수치 입력의 허용 정책으로 채택 |
| mesh-data | geometry entity/node/element tag, 집합/physical group, dataset/array, topology/geometry, 표시변환/실제변환 | Gmsh tag·VTK array·CAD shape를 권위 있는 solver 카드 ID/문서 모델로 동일시 |
| jobs | 요청/실행/중단 요청/실제 종료/결과 채택, thread/process, stale 결과, 외부 효과 | process kill을 solver stop이나 문서 rollback과 동일시, Workbench job 소유권 변경 |

## 3. 교차 시나리오

각 행에서 원문으로 확인된 범위와 결손을 함께 기록한다. 복수 분야를 읽고 조합한 자체 정책은 조사 결과로 확정하지 않는다.

| 시나리오 | 확인할 연결과 실패 조건 |
|---|---|
| 표 paste → 문서 변경 → Undo | 여러 셀 중 하나가 invalid일 때 draft 보존·전체/부분 반영·rollback·Undo 단위가 각각 무엇인지 |
| 선택 변경 → action 활성화 | entity 종류, 숨김/격리/filter, 문서 busy가 바뀌면 선택과 실행 capability가 어떻게 바뀌는지 |
| worker cancel → 문서/산출물 상태 | 중단 요청과 실제 종료가 구별되고, 임시 산출물·문서 변경·외부 효과의 처리 근거가 있는지 |
| 선택 대상 삭제 → property draft → Undo | 참조 소멸·dangling 처리·편집값·정체성 복원의 범위가 연결되는지 |
| 여러 객체의 mixed 값 → 일부 편집 | 공통값/혼합값 표현과 대상 중 일부만 편집 불가할 때 적용 범위가 드러나는지 |
| 표시 단위 변경 → 입력/표/곡선 | 값의 의미와 저장값, 축 단위, locale, 반올림이 혼동되지 않는지 |
| topology 변경 → 참조 유지/손실 | 문서 객체 참조와 subshape 참조, 인덱스와 안정적 정체성의 차이가 드러나는지 |
| job 시작 → 대상 수정/삭제/문서 닫기 | stale 결과 통지와 채택, 완료 후 target 부재, 취소와 완료의 경합이 확인되거나 공백인지 |
| GUI ↔ script | 같은 명령 이름이나 API 존재만으로 transaction·validation·Undo 의미가 같다고 추정하지 않는지 |
| 키보드/IME/혼합 DPI | shortcut과 text entry 충돌, 한글 조합, 긴 이름·좁은 창·배율 전환이 확인되거나 공백인지 |

## 4. 자료·집계의 진실성

- source는 실제 원문의 관련 절을 읽은 경우만 집계하며, 검색 결과에만 등장한 후보는 분리한다.
- 문서 URL·보유 distinct image·pattern record 수를 별도로 집계한다. 같은 문서의 anchor와 반복 등록을 새 문서처럼 세지 않는다. 버전·언어·내용을 바꾸는 URL 차이는 성급히 병합하지 않는다.
- 기존 CAE corpus와 중복된 문서/이미지는 보충분의 신규 확보 수에 중복 합산하지 않는다.
- asset은 실제 파일 존재, 등록 치수, source 연결, 시각 확인 여부를 점검한다. 원본 사진/화면과 crop·PDF raster의 파생 관계가 숨겨지지 않는가.
- 이미지 해상도에서 앱의 논리 pixel·글꼴·DPI를 추정하여 확정하지 않는다. 내부 코드 diagram과 제품 GUI 화면을 구별한다.
- 원문 요약/인용 한도와 라이선스·브랜드 경계를 지키는가. source.summary와 notes의 중복 서술도 같은 출처에서 나온 분량으로 본다.

## 5. 종료 판정

필수 기능 묶음이 누락 없이 coverage에 있고, 각 묶음의 문헌 지원·부분 지원·자료부재 사유와 개발 영향이 설명되어야 한다. 대안/반례 검색 흔적이 있고 독립 접근의 차이를 설명할 수 있어야 한다. 제품 수나 대표 그림 수는 충분성 기준이 아니다. 자료 조사는 공백을 정직하게 남긴 채 종료할 수 있으나, 그 종료를 구현 준비 완료·재현 검증·상용 동등성으로 표현할 수 없다.

감사 결과는 근거 오류/의미 손실/추적 불가능/누락을 구별하고, 수정 가능한 오류는 수정 후 재확인한다. 자료가 원래 답하지 않는 질문은 새 정책을 정하는 대신 gap으로 남긴다.
