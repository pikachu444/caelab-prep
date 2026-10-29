# 동작·상태 완전성 최종 감사

검토 기준: [방법과 판정](method.md). 7개 research JSON의 장면·결손 전체와 각 specs를 대조했다. 감사자는 로컬 원본 이미지 15개를 추가로 열어 확인했고, COMSOL의 grounded 두 장면은 연결된 기존 원문을 재열람했다. 신규 제품·입력 모델 조사와 앱 실행은 수행하지 않았다.

## 최종 판정 경계

- 7제품 × T01~T09의 **63개 셀 모두 존재**한다. 각 셀 내부에서 빠진 조작/상태는 아래 missing으로 남겼다.
- `design_path_grounded`: 좁게 지정한 정상 경로의 선행 상태·메뉴·선택·필수 입력·결과를 D/S로 추적할 수 있음. 별도 입력 파일·실행 결과를 보유했다는 뜻은 아니다.
- `full_workflow_ready`: 과업 전체의 핵심 분기·오류/취소·저장 연결까지 준비됨. 현재 **63셀 모두 조건부**이며 완료로 승격할 수 없다.
- `reproduction_verified`: 동일 입력을 실제 앱에서 실행하여 검증함. 전 제품 false이며 R/V 근거도 없다.
- `grounded` 장면 수는 제품 품질 순위나 전체 과업 확보율이 아니다. 제품마다 장면 크기가 다르며 HyperMesh처럼 보수적으로 전부 partial인 자료에도 유용한 정상 경로 근거가 있다.
- 수정된 JSON에서 근거 없이 직접 실행 결과로 승격된 주장은 발견하지 않았다. 이 판정은 모든 원문 문장의 독립 진위 검증이 아니라 자료 내 상태·조작 연결의 감사 결과다.

## Naksha / BeidPrep — 1차 감사

두 제품의 research JSON과 specs 전체를 읽었다. Naksha 작업공간, BeidPrep Node Move·Morph·LAW36 화면 4개는 로컬 원본을 직접 재검사했다. 두 제품 모두 9개 과업 셀은 존재하며 18장면 모두 `partial`이다. 근거 없는 `grounded` 승격은 없다. 과업 전체의 필수 동작 연결이 충족된 셀은 각각 0/9다.

| 과업 | Naksha 핵심 결손 | BeidPrep 핵심 결손 |
|---|---|---|
| T01 | Import 진입·옵션/단위·입력→트리 결과·실패 흐름 missing. 작업공간 배치만 조건부 활용. | File 하위 메뉴·입력/옵션·결과·오류 흐름 missing. 열린 덱의 작업공간만 조건부 활용. |
| T02 | 행 선택→Details 갱신·필드 편집/적용·다중 선택 충돌·저장 missing. | 트리 선택→폼 갱신·편집/적용·배정·저장 missing. |
| T03 | 필터·명령 외관은 있으나 선택 전후·추가/제거·숨김/복원 결과 missing. | Node Move 패널과 안내는 있으나 패널 진입·실제 선택/드래그 전후·commit/cancel·가시성 동작 missing. |
| T04 | hex 결과 그림만 있으며 생성 명령·입력·필수 설정·실패/검사 missing. | mesh 편집/morph 화면은 있으나 **메시 생성 흐름 자체 missing**. 선택 모델·명령·seed/크기·생성/품질 결과를 대체하지 못함. |
| T05 | 재료 선택 화면 이후 import/card 매핑·단위 검증·조건/케이스 배정 missing. | LAW36 필드 화면 이후 생성 진입·단위·폼 적용·대상/케이스 배정·검증 missing. |
| T06 | 기능 소개 외 검사 입력·진입·진단 화면·문제 집합·취소/수정 후 상태 missing. | 제작사 검증 설명 외 GUI 검사 진입·오류 화면·불량 선택·취소/수정 후 상태 missing. |
| T07 | 형식 목록 외 native 저장/solver export 조작·옵션·완료/오류·재열기 보존 missing. | Save/Export 문서 경로 외 저장창·옵션·GUI 완료/오류·재열기 동일값·미저장 변경 처리 missing. |
| T08 | 결과창은 실행/자동화 증거가 아님. 실행 설정·launch/로그/종료·agent 연결/승인/취소 흐름 missing. | 권한 설정 화면 외 진입·연결 과정·실행/승인·로그 변화·종료/실패/취소 흐름 missing. |
| T09 | 곡선 표시만 있고 표/곡선 편집·열/단위·입력검증·적용·저장 missing. | 입력 경로 소개만 있고 실제 편집기·열/단위·붙여넣기 전후·오류/적용·저장 missing. |

이 표의 missing은 과업 셀 부재가 아니라 셀 내부의 핵심 동작 근거 부재를 뜻한다. UI 참고 이미지/필드 목록으로 쓸 수 있는 부분과 동작 명세의 미확정 부분을 함께 유지해야 한다.

### 수정 권고

| ID | 위치 | 발견·권고 | 상태 |
|---|---|---|---|
| AS-01 | BeidPrep BE-05 result | ‘적용 버튼 관찰’은 카드 폼 적용으로 오해된다. 화면의 APPLY는 하단 선택 띠에 있으며 카드 commit과 연결되지 않았다. | 수정 확인: 카드 적용 주장 제거, card commit unknown 추가. |
| AS-02 | BeidPrep BE-03/04 menu_path | `Editing > MESH > Node > Move`는 열린 Editing 패널의 내부 경로다. 전역 메뉴 진입과 구별해야 한다. | 수정 확인: 패널 내부 경로/전역 진입 미확인 명시. |
| AS-03 | 두 제품 과업 표 | 과업 제목만으로 해당 흐름 확보로 오독될 수 있다. 생성·실행/자동화·편집의 실제 결손을 보존해야 한다. | 이 감사표에서 모두 명시. 통합물에서도 유지. |

## Abaqus / COMSOL / HyperMesh — 모든 셀의 잔여 결손

각 셀은 **확보한 설계 근거; missing** 순이다. 모두 과업 전체로는 조건부다.

| 과업 | Abaqus | COMSOL | HyperMesh |
|---|---|---|---|
| T01 | 새 Beam 정상 경로와 STEP 절차; STEP 표본·옵션 선택값·가져오기 결과·실패 missing. | 새 모델 wizard 정상 경로; CAD 예제 파일·Import 전후 UI·취소/외부 경로 재열기 missing. | profile/Open/solver reader; 원본 파일·입력 전후·Import 오류/Cancel missing. |
| T02 | 트리·feature 메뉴·재료 입력; feature 값 편집·적용/취소 비교·실패 입력 missing. | 노드/Settings/Properties; 값 편집 commit·취소·저장 메타데이터 확인 missing. | 계층/열·Entity Editor·즉시 반영 문서; 선택 변경 전후·다중 편집·취소/저장 범위 missing. |
| T03 | 필터·추가/제거·모호 선택 정상 경로; 숨김/복원 전후·선택 수·가림 우선순위 missing. | 이름 선택 생성/재사용·가시성 문서; 영역/추가제거/가림 정책·취소 후 선택·가시성 저장 missing. | 확장 선택·필터·삼상태 가시성; 같은 모델의 선택/표시 전후·취소·재열기 missing. |
| T04 | Hex/Structured→C3D8I→seed→생성 문헌 경로; Controls/Seeds 전체 UI·같은 모델 품질수치·실패 재현 missing. | 두 도메인 size/Build All·메시 그림; 선행 RF 모델·취소 후 잔류 메시·요소수/품질수치 missing. | model/local controls·Tet·representation 대안; 동일 경로의 입력/출력 완결·메시 실패/중단·XML 저장 missing. |
| T05 | 재료/단면/단계/BC/압력 정상 경로; **Assembly 인스턴스 생성·배치**·editor 전체 UI·독립 case 관리·오류 missing. | 재료/전위·선택 문서; Vtot 입력 파일·펼친 재료값 UI·조건→Study 전후·충돌/복구 missing. | MAT1→PSHELL·TEMPD/TEMP→SUBCASE; 원본 모델·구속조건 상세·온도 단위 문맥·취소/오류 missing. |
| T06 | 세 오류창과 응답 의미·Verify/Monitor; 실패 유발 입력·문제 강조·수정 성공·품질수치·중단 후 상태 missing. | Statistics/진단/Stop·Cancel 문서; 실제 통계 UI·불량 위치 수정·계층별 종료 후 결과/파일 missing. | quality 범례·geometry/mesh 수리·unresolved·Undo; 수리 전후 품질수치·실패/중단/복구 상태 missing. |
| T07 | native Save/Open과 .inp 쓰기 정상 경로; Save UI·실제 파일·재열 데이터 비교·쓰기실패/덮어쓰기 missing. | MPH/스크립트 저장·Revert 문서; Save/일반 Open UI·덮어쓰기/취소·파일 보존 검증 missing. Java 저장은 solver deck 아님. | assembly binary 재열기 그림·model save/open·solver export; 실제 deck·재import 비교·disk 실패/덮어쓰기/Cancel 상태 missing. |
| T08 | job 정상 경로·noGUI/recover 진입; 인스턴스 선행 단계·실제 로그/출력·스크립트 내용·복구 결과 missing. | micromixer batch 문헌 경로; Batch/External Process UI·입출력 파일·실행/재열 검증·실제 solver 오류 missing. | solver 제출·완료 문구·Python recording; 실행 로그·생성 script·실행 결과·취소 효과 missing. |
| T09 | 표/ASCII/XY·수식·일관 단위 규약; 입력 표본·곡선 결과·영구저장·현행 expression 평가 missing. | 파라미터/보간/결과표; 수치 행/파일·곡선/단위 편집 UI·단위오류·round trip missing. | 곡선/CSV·array 제한·sketch 단위; CSV round trip·오류 표시·단위 UI/수치변환 missing. |

## NFX / MeshFree — 모든 셀의 잔여 결손

| 과업 | NFX | MeshFree |
|---|---|---|
| T01 | 새 작업/단위·CAD import 정상 경로; 외부 파일 실물·실패/취소·단위변경 효과·재열기 missing. | import 정상 경로; 외부 파일 실물·새 세션 전후·입력 실패/취소·재열기 missing. |
| T02 | 트리 영역·솔리드 특성 입력; 선택→속성 갱신·적용 후 트리·다중 편집·취소/저장 missing. | 전체/케이스 트리·재료배정; 배정 후 트리·활성 부분집합 변경 전후·취소/저장 missing. |
| T03 | 특성별 가시성 정상 경로·절점 질의·값 표시; 선택 추가/제거·필터/가림 정책·조작 후 저장 missing. | 면 선택·파트 표시/투명도 문서; 필터/피처각·선택 해제·가시성 우클릭 UI·상태 보존 missing. |
| T04 | 자동 솔리드·고속 tetra·size9·특성/세트 연결; 동일 입력 파일·품질 결과·생성 실패·취소복원 missing. | AutoGrid 예비검사·격자 미리보기; 입력 밀도/메모리·격자수·오류/취소·해석 결과 연결 missing. FEM 메시 생성과 동치 아님. |
| T05 | 재료·대칭구속·하중·케이스·세트 이동; 각각 적용 후 트리/값·충돌·Undo/취소·저장 연결 missing. | 재료·케이스·하중 입력; 적용 후 결과·오류/취소·재배정/케이스 활성 전후 missing. 교재 상충 부분은 미확인 유지. |
| T06 | 품질 임계값·불량 색상; 실패 유발 입력·검사 수치·수정/취소/복구 전후 missing. | 오차표·취소 버튼; 오류표 진입·수정/재계산·실제 취소 후 상태 missing. 선형/비선형 표시 불일치 보존. |
| T07 | 실행 중 프로젝트 저장 지시/창; 일반 저장 진입·내보내기·실제 파일·재열기·덮어쓰기/실패 missing. | 다른 이름 .mef 저장창; export·실제 파일·재열기·덮어쓰기/저장실패 missing. |
| T08 | solver 창·구조/유동 옵션; 실제 완료/오류 로그·중지 후 상태·API/스크립트/배치 입력 missing. | batch/진행·과도 제어; 같은 case의 일관된 상태·실제 완료/오류·API/스크립트 missing. |
| T09 | 소성 표/곡선·요약 설정·새 모델 단위; 행 오류·적용 후 모델·단위변환·곡선 저장/재열기 missing. | 재료 DB 표/파일 저장 문서; 입력 행 검증·단위변환/파싱·재불러오기·곡선 편집 missing. |

## 최종 수정 확인

| ID | 발견 | 처리 |
|---|---|---|
| AS-04 | NFX mesh에서 알고리즘·특성·세트·단위 선행 문맥 누락. | 원본 UI 대조 후 모두 JSON에 추가. 좁은 정상 경로 grounded 유지. |
| AS-05 | NFX import 화면 파일명 접두어 누락, filter의 D 결과/S 메뉴상태 혼동 가능. | 파일명 D/S 구별·format/단위·결과 구분 추가. |
| AS-06 | MIDAS 장면에 ‘취소 버튼 관찰’을 일괄 사용. | 실제 취소/X/닫기/미확인으로 개별화 확인. |
| AS-07 | Abaqus BC 타입의 정확한 이름 부족, Beam instance 선행 단계 누락. | 타입 풀네임 및 AB15/16/25 선행 인스턴스와 미수집 gap 추가 확인. |
| AS-08 | COMSOL batch unknowns 빈 목록이 UI/파일 부재를 숨길 수 있음; 표 순서 불일치. | 장면 unknowns에 UI/입출력 파일/검증 부재 추가, ID별 status 표 수정 확인. |
| AS-09 | HyperMesh HM08에서 별도 Tet/representation 경로를 steps로 병치. | 대안 A/B이며 연속실행 아님을 명시한 수정 확인. |
| AS-10 | HyperMesh HM10의 두 TEMPD collector가 같은 S로 확인된 것처럼 보임. | collector별 D/S 분리: temp_initial은 D+S, thermal_loading은 D만으로 명시한 수정 확인. |
| AS-11 | 제품별 grounded 기준 차이가 제품 평가로 오독될 위험. | root와 3축 분리 합의. 21개 좁은 grounded는 장면 통계이며 제품 순위/전체 준비도 아님. |

총 123장면을 점검했다. 최종 status는 좁은 문헌 grounded 21, partial 102이며, 각 제품의 선언 범위 안에서 판정을 유지할 수 있다. 감사 중 제기한 구체 표현/핵심필드 수정은 완료되었다. 남은 missing은 수집 실패를 숨기지 않는 후속 결손이며 이번에 추가 수집하거나 구현한 것으로 처리하지 않는다.

## 최종 통합 확인

7제품·123장면·63과업셀을 확인했다. source/asset 참조와156실재파일의치수는 맞았다. 자료집과 공개JSON에 design_path_grounded/full_workflow_ready/reproduction_verified3축을 전장면 명시했다. BeidPrep 중립면제작사평가의엔진은원문8cefff4/2026-10-27로보강했다.

별도출처감사에서는수집자가156개발췌를직접확인했다고기록한것과감사자가27개를직접재검사한것을구분했다. UI참조141개와UI없는모델crop/렌더15개를분리했고,Abaqus대학미러·문서발췌해상도·그림의버전미확인을보존했다.

이자료수집묶음은종료가능하다. 전체GUI재현준비와제품구현완료는선언하지않는다. 다음구현은현재근거와자체정책을분리하고선택한장면의필수결손을좁혀해결한다. 같은원문을반복수집하거나이미지개수를늘리기위해새제품을추가하지않는다.
