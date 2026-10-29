# CAE GUI 참조 제품과 공용 자산 비교

조사 기준일: 2026-10-29. 이 문서는 [실행 계획](shared-cae-foundation-plan.md)의 참조 범위를 구체화한다. 제품 화면의 관찰과 설치·실행 검증을 구분한다. 상용 제품마다 앱을 한 벌씩 복제하는 계획은 아니다.

## 1. 제품별 확인과 활용

| 제품 | 이번에 확인한 근거와 수준 | 가져올 설계 패턴 | 연결할 공용 자산/계약 |
|---|---|---|---|
| Abaqus/CAE 2025 | 공급사 주 화면 문서 확인. 이번 조사에서 설치하지 않음 | 모듈/대상 문맥, 모델/결과 트리, 도구상자, 작업 지시 | Action 문맥·도구 그룹·선택 절차·트리·뷰포트 조합 |
| COMSOL Desktop | 공식 Desktop·레이아웃 문서 확인. 설치하지 않음 | Model Builder–Settings–Graphics, 문맥 명령, 로컬 툴바 | 같은 문서/제공자를 다른 배치와 설정 패널로 표현 |
| HyperMesh 2025 | 공식 Model/Part Browser 문서와 Model Browser 이미지를 직접 확인. 설치하지 않음 | 검색·분류·속성 열·공통 Entity Editor, part/assembly/instance·표현/개정 | 밀도 높은 트리/표·속성 편집, source/native 참조·조립 계층과 표시 상태 |
| midas NFX 2026 | 공식 릴리스 PDF p9–10의 조건 트리와 하중 표시 설명·그림 확인. 설치하지 않음 | 하중/경계조건의 set 간 drag/drop, 방향·수치의 3D 표현 | 조건 정의/배정 명령, 다중 항목 이동의 Undo, 단위/좌표와 연결된 glyph |
| MIDAS MeshFree | 공식 기초교육 PDF p18·20의 실제 GUI 그림 확인. 과거 교육 자료이며 최신 버전 실행 검증은 아님 | 전체 모델 트리와 케이스별 해석 트리의 분리, 조건 배정·작업 단계·단위 | 정의와 케이스 활성 관계, 재사용 조건 목록·대상 선택·해석 케이스 편집 |
| Naksha / Effileap | 현재 공식 제품 페이지와 충돌 모델 화면을 확인. 실행본 시험은 하지 않음 | 명령 검색·다층 도구 영역·종류별 선택 표시줄·ID/표시 열·파트별 색 | 공용 명령 검색·선택 표시줄·상태 열·표시 제어. 성능 수치는 자체 측정으로 인용하지 않음 |
| BeidPrep | 공식 2.0 소개와 LAW36 카드 화면 확인. 직접 실행 이력은 별도 기록의 1.0.1뿐 | native 카드의 폼/원문 전환, 참조 ID 입력, 표/곡선 입력과 선택 | 제공자 기반 속성 폼·native 원문 조회·참조 편집·곡선/선택 부품 |

MeshFree는 여기서 **MIDAS MeshFree**를 뜻한다. 일반적인 meshfree 해석법이나 다른 회사의 동명 제품과 구분한다.

특히 MIDAS 교육 자료에서는 전체 모델에 있는 모든 파트·접촉·경계조건·하중과 특정 해석 케이스에 배정한 부분을 별도로 보여준다. 이 패턴은 디자인뿐 아니라 **조건 객체의 정의와 케이스별 사용 관계를 분리**하는 데이터 설계에 반영한다. HyperMesh의 part/instance 구분도 화면 그룹만 복제하는 방식 대신 공용 참조 설계로 연결한다.

BeidPrep 1.0.1의 열기/저장 시험은 [기록](beidprep-evaluation.md)을 따른다. 그 시험에서 구속·옵션 보존 문제가 있었으므로 좋은 입력 폼을 참고하는 것과 파일 의미 보존이 검증됐다는 판단을 합치지 않는다. 공식 Naksha/BeidPrep 소개의 기능·대용량·정확도 수치는 제작사 설명이며 이번 실행 검증 결과가 아니다.

## 2. 제품 목록을 실제 설계 선택으로 바꾸기

| 설계 문제 | 우선 비교할 제품 | 구현 전 결정할 내용 |
|---|---|---|
| 정보 밀도·도구 계층 | HyperMesh, Abaqus, Naksha | 트리/표 열, 행·아이콘·도구 그룹, 문맥 표시와 빈 영역 사용 |
| 속성·단위·native 입력 | COMSOL, HyperMesh, BeidPrep | 그룹형 속성, 값/단위·참조 대상, 오류·원문 전환 |
| 선택과 모델–뷰 연결 | HyperMesh, Naksha, BeidPrep | 종류 필터·추가/제거·선택 목록, 숨김과 해석 비활성화의 구분 |
| 조건·조립·케이스 | HyperMesh, NFX, MeshFree | 원형/배치·component·source 관계, 조건 재배정·케이스 포함 관계 |
| 하중·방향·좌표 표시 | NFX, Abaqus, COMSOL | 값·단위·좌표계와 glyph가 같은 대상을 표현하는지 |
| 작업 가이드와 결과 영역 | MeshFree, COMSOL, Naksha | 작업 지시·로그·진행·결과 영역. 첫 묶음에서 실제 지원하는 동작만 제공 |

실행 계획의 Abaqus 계열/COMSOL 계열 명칭은 두 레이아웃의 가칭이다. **참조 제품을 두 개로 제한하는 이름이 아니다.** 첫 기계 전처리 화면과 설정 중심 화면은 위 제품들을 영역별로 비교해 구성한다. 비교 결과는 다음처럼 짧게 기록한다.

- 자료의 제품/버전·출처·화면 영역·해상도/배율과 확인 수준.
- 관찰한 패턴과 해당 공용 부품의 요구.
- 채택/수정/보류 이유, 자체 구현 또는 외부 코드 재사용의 구분.
- 첫 묶음의 목표 조합 화면과 상태 목록. 구현 시작 전에 고정하고 새 요구는 다음 묶음으로 관리.

P0에서 값이 들어 있는 화면을 골라 비교한다. 빈 시작 화면·작은 모델 화면만으로 정보 밀도나 완성도를 평가하지 않는다. 원본 화면의 모든 버튼을 채우는 대신 실제 제공자의 가능 동작과 공용 자산을 연결한다.

## 3. 근거

- [Abaqus 2025 주 화면 구성](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEGSARefMap/simagsa-c-absmaincaewindow.htm).
- [COMSOL Desktop](https://www.comsol.com/support/learning-center/article/Introduction-to-the-desktop-34131), [레이아웃](https://www.comsol.com/support/learning-center/article/Personalize-the-desktop-34391).
- HyperMesh [Model Browser](https://2025.help.altair.com/2025/hwdesktop/hwx/topics/user_interface/browser_model_overview_c.htm), [Part Browser](https://2025.help.altair.com/2025/hwdesktop/hwx/topics/pre_processing/model_build_and_assembly/part_browser_open_t.htm), [Parts/Assemblies/Instances](https://2025.help.altair.com/2025/hwdesktop/hwx/topics/pre_processing/model_build_and_assembly/part_and_part_assembly_about_c.htm).
- [midas NFX 공식 2026 릴리스 PDF](https://support.midasuser.com/hc/en-us/article_attachments/56118571181593), p9–10.
- [MIDAS MeshFree 제품](https://www.midasmts.com/meshfree), [공식 기초교육 PDF](https://patch.midasit.com/00_MODS/kr/03_TechnicalData/%EA%B8%B0%EA%B3%84/%EA%B5%90%EC%9C%A1%EC%9E%90%EB%A3%8C/%5BMeshFree%5D%EA%B8%B0%EC%B4%88%EA%B3%BC%EC%A0%95.pdf), p18·20.
- [Naksha 공식 제품](https://agentnaksha.com/), [공식 모델 화면](https://agentnaksha.com/assets/img/app/app-crash-model.webp).
- [BeidPrep 공식 소개](https://beidersim.com/beidprep.html), [공식 LAW36 화면](https://beidersim.com/images/card-editor-law36.png), [1.0.1 실제 시험](beidprep-evaluation.md).

공식 문서와 공개 화면을 참고한 설계 비교이며 각 제품의 비공개 코드를 가져왔거나 실행 검증을 완료했다는 뜻이 아니다.
