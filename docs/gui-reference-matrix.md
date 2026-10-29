# CAE GUI 참조 제품과 공용 자산 비교

2026-10-30. 기존 개요 비교를 [7제품 상세 근거 자료](benchmarks/2026-10-30/README.md)로 확장했다. 기술문서 URL 110개, 화면·그림 발췌156개, 작업장면123개를 연결했다. UI포함 발췌141개와 모델뷰/렌더15개를 구별한다. 숫자는 전체 재현 준비나 제품 품질 점수가 아니다.

Abaqus/CAE2025, COMSOL6.3, HyperMesh2025/2025.1, midas NFX, MIDAS MeshFree, Naksha, BeidPrep을 조사했다. NFX와 MeshFree는 별도 제품이며, Abaqus 문서는 vendor-origin 매뉴얼의 Virginia Tech 호스팅 미러다. 자료판·앱빌드·문서그림의 시점 차이를 색인에 기록한다.

## 근거를 찾는 경로

| 필요한 것 | 자료 |
|---|---|
| 제품/버전·실제 확보량·남은 한계 | [자료지도](benchmarks/2026-10-30/README.md) |
| 토론 후 역할분담·S/D/V/R·장면 판정 | [방법과 판정](benchmarks/2026-10-30/method.md) |
| 메뉴·필드·선택·결과·오류/취소·저장과 원문 | 자료지도의 `products/*.json` |
| 공용 Action/트리/속성/표·곡선/메시/저장 계약 | [공용 자산 요구](benchmarks/2026-10-30/common-assets.md) |
| 화면 실측과 앱 DPI/문서 렌더 구별 | [화면 관측](benchmarks/2026-10-30/layout-observations.md) |
| 7제품×9과업의 남은 동작 결손 | [교차검토](benchmarks/2026-10-30/audit.md) |

정상 문헌경로가 있는 장면과 과업 전체 준비·직접 실행을 분리한다. 이번 전제품의 실제 앱 재현은0건이며 실패/취소/저장 재열기가 다 연결된 전체 과업 준비로 보고하지 않는다. 공개 이미지의 버튼 존재를 후속 동작의 보장으로 해석하지 않는다.

## 공용 설계로 연결할 차이

정보 밀도·도구 계층은 HyperMesh/Abaqus/Naksha, 설정과 단위/원문은 COMSOL/BeidPrep/HyperMesh, 조립·조건/케이스는 NFX/MeshFree/HyperMesh를 비교한다. 다른 제품의 용어를 하나의 타입으로 강제하지 않는다. Step과case, geometry component와solver part, mesh품질과해석오차는 구분한다.

P0에서는 실제 값이 채워진 여러 장면을 근거로 목표 조합 화면과 상태·자체자료·환경을 고정한다. 대표사진2~3장을 확보했다는 이유로 조사를 완료 처리하지 않으며, 이 자료집을 만들었다는 이유로 P0의 실제 선택을 완료 처리하지도 않는다. 이후 [작업서](execution-stages.md)에 따라 첫 공용 계약·위젯·실제 앱 연결을 구현한다.

[BeidPrep1.0.1 시험](beidprep-evaluation.md)은 과거 별도 실행기록이다. 2.0 웹자료를 그 실행결과로 승격하지 않는다. 기존 엔진 도입과 복잡 신규 meshing커널의 경계는 [메셔 로드맵](mesher-feasibility-roadmap.md)을 유지한다.
