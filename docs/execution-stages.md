# Prep 단계별 개발 작업·종료 조건

기준: `caelab-prep` main `5d16e81c7ec7c92499401d63208039424bf73cc9`, 2026-10-29. 본 문서는 **후속 구현의 작업서**다. Astra의 독립 설계와 별도 Workbench 소비자 검토를 통합했다. 이번에는 제품 코드를 변경하거나 아래 구현 검증을 실행하지 않았다. [공용 기반 설계](shared-cae-foundation-plan.md)의 P0–P9/A1–A8과 [모델·데이터 설계](cae-model-data-design.md)의 B1–B6을 유지하며 실행 경계를 구체화한다. Workbench의 실제 재사용 단위·코드 근거·W1–W3 종료 조건은 [재사용 계획](workbench-reuse-plan.md)을 따른다.

2026-10-30 보완: 고급 메셔는 이 표에 있다고 구현 가능성이 입증된 것이 아니다. 실제 공개 코드·상용 매뉴얼·알고리즘 조사와 별도 SDK 실험은 [메셔 실현 가능성 로드맵](mesher-feasibility-roadmap.md)에 둔다. P7c의 후보 선택 뒤 바로 제품 구현을 확정하지 않고 F0–F2 실증을 선행한다. 아래 앱/파일 검증과 그 별도 SDK 실험을 혼동하지 않는다.

2026-10-30 자료 보강: [벤치마크 자료지도](benchmarks/2026-10-30/README.md)에 7제품의 9과업·123장면과 근거/결손을 연결했다. P0는 이 자료에서 목표 장면·상태·자체 입력·환경을 실제 선택한다. 자료 수집과 P0 완료를 합치지 않으며 신규 메셔 연구 전체를 공용 GUI 개발의 선행 조건으로 만들지 않는다.

## 1. 검토 결론과 수정할 선행 관계

공용 CAE 자산·기반을 개발한다는 저장소 목적과 현재 Qt/VTK·RAD 원문 보존의 출발점은 유지한다. 공용 GUI, 문서/명령, 모델·관계, CAD/메시, 자동화와 배포를 각각 납품 가능한 묶음으로 끝낸다. 모든 솔버 물리와 모든 메시 생성법을 갖출 때까지 첫 산출물을 미루지 않는다.

기존 계획의 가장 큰 실행 병목은 **P7의 첫 CAD/메시 채택이 P6/B 전체, 특히 100만 요소 검증 이후로 밀리는 것**이다. P6를 세 부분으로 나누고 P7a를 앞당긴다.

- A: 기존 P0–P3, A1–A8을 그대로 충족한다. 실제 공용 부품·갤러리·첫 RAD 앱 연결이다.
- C: P6a의 최소 자원/명령 기반 이후 P7a. **CAD → 선형 tri surface 또는 tet → 품질 → 후보 채택 → 편집/Undo → 저장/재열기 → 명시한 RAD native 출력/Starter 읽기**를 처음 끝낸다. B의 100만 요소와 일반 재메시/중립면/hex를 기다리지 않는다.
- B: P6b–P6c에서 기존 B1–B6을 완성한다. C가 통과했다고 B를 완료로 표시하지 않는다.
- P4/P5는 A 이후 별도로 완료할 수 있다. P8의 작업 계약 일부와 P9의 패키징은 각 묶음에 필요한 만큼 먼저 적용한다. IPC/MCP나 최종 설치 배포를 모든 단계의 선행 조건으로 두지 않는다.
- P7b는 일반 메시 수정·재메시와 참조 재연결, P7c는 중립면·sweep/hex의 별도 유한 기능 묶음이다. C로 일정을 당기면서 이 기능들을 계획에서 지우지 않는다.

권장 실행 순서는 `P0 → P1 → P2 → P3/A → P6a → P7a/C → P6b → P6c/B`다. `P4·P5`, 첫 Workbench 파일 전달, P9의 단계별 패키징은 A 이후 독립적으로 진행 가능하다. 한 작업자가 진행할 때는 C를 고급 곡선·두 번째 레이아웃보다 먼저 권장한다. 작업을 나누면 계약과 공통 파일의 편집자를 한 명으로 정한다.

### 구현할 순서와 닫을 산출물

| 순서 | 끝낼 작업 | 단계 종료의 핵심 |
|---|---|---|
| 1. P0 | 지원 범위·참조 장면·자료·환경 고정 | 필요한 선택을 내리고 조사 종료. B 장비 보류가 A/C 전체를 막지 않음 |
| 2. P1 | 최소 계약과 RAD/중립 제공자 | 같은 계약으로 실제 값 수정·오류·Undo, 기존 CLI 보존 |
| 3. P2 → P3/A | 공용 자산·부품 갤러리·실제 작업 화면 | 같은 코드 사용과 A1–A8의 편집/재열기/Windows 외관 통과 |
| 4. P6a → P7a/C | 최소 자원 채택과 첫 CAD/메시 | 세 CAD의 tri/tet 생성·품질·조건·Undo·재열기·Starter 읽기 |
| 5. P6b → P6c/B | 조립·혼합 자유도·관계·대용량 | B1–B6와 고정 시간/메모리 예산 통과 |
| 독립 확장 | P4 곡선 앱, P5 두 번째 배치, P7b 수정/재메시 | 아래 각 카드의 기능·자료·파일 조건으로 따로 종료 |
| 조건부 메시 확장 | P7c-S/M/H와 자동 커널 연구 | 실제 코드/API → 독립 재현 → 지원 형상군 실증 뒤에만 제품 연결. 평가 no-go와 기능 완료 구분 |
| 실제 소비 | Workbench W1 공용 입력, W2 독립 Prep, W3 RAD 실행 | 각 소비자의 실제 작업 통과. 하나의 성공으로 나머지를 완료 처리하지 않음 |
| 점진 적용 | P8의 API/CLI/IPC/MCP, P9의 각 묶음 배포 | 선택한 전달 방식과 배포 묶음별로 종료 |

P0 종료 뒤에는 계획서를 새로 늘리는 작업 대신 P1의 실제 계약·제공자를 구현한다. 기술적 선행 구현이 갖춰졌다면 관련 없는 플랫폼 확인 보류가 다른 작업 전체를 멈추게 하지 않는다. 다만 보류 항목이 있는 묶음을 완료로 보고하지 않는다. 이 문서를 작성한 것만으로 위 구현 단계가 완료된 것은 아니다.

## 2. 현재 코드에서 확인한 실제 간극

| 출발점 | 이미 있는 것 | 후속 작업에서 반드시 추가할 것 |
|---|---|---|
| `cae_core/document.py` | opaque Resource, 한 자원의 상태 변경/Undo, revision·dirty·선택 | 자원 생성/삭제·다중 자원 원자적 commit, 메시에 대한 값 복사 없는 이력, 범위 있는 typed 참조 |
| `application/session.py` | RAD/INCLUDE 열기·patch·ZIP 저장·내보내기, 호출 직렬화 | 공용 세션/codec 경계, 비-RAD 문서, 새 native 객체 생성·안정적인 ID 배정 |
| `ui/main_window.py` | 실제 RAD 편집과 파일 실패/초안 보존 | 공용 Action/트리/속성/셸 추출, 지연 모델/뷰, 긴 작업의 후보/채택 상태 |
| `ui/viewport.py` | VTK 투영·절점/요소 pick | 자원/개정/종류를 가진 선택, CAD·mesh·surface 표시의 구분, 부분 갱신과 cache 수명 |
| `gmsh_worker.py` | 균일 mesh-size, dimension 2/3, 1차 요소, XAO/MSH/연결 metadata, process 경계 | 품질 측정·표시, 문서 채택, native 생성; 대용량에는 전체 coordinates/connectivity JSON list 중복 전달 제거 |
| 기존 검사 | document/RAD/roundtrip/CLI/Qt 문서/CAD worker 테스트 | 공용 계약·자원 채택·모델 관계·실 GUI·실 solver에 대한 해당 단계 검사 |

기존 RAD reader가 tri/tet를 표시할 수 있다는 사실은 새 tri/tet의 native 카드 생성 기능이 있다는 뜻이 아니다. CAD 후보의 tet 외피 facet은 경계 표현이며, 이를 shell 물리요소로 함께 채택하지 않는다. `.caeprep` v1이 RAD 원문과 patch를 저장한다는 사실도 임의 메시/재료를 저장할 공용 codec이 완성됐다는 뜻이 아니다.

## 3. 모든 작업에 적용할 종료 규칙

작업을 시작할 때 아래 7개 항목을 PR 본문 또는 이 계획의 해당 행에 고정한다. 별도 프로젝트 관리 시스템이나 검사 대시보드를 만들지 않는다.

1. 범위와 끝낼 사용자 작업. 현재 단계에서 지원할 형식/요소/필드/생성·수정 동작.
2. 입력 파일/생성기와 데이터 규모. 작은 회귀 자료 외에 구조가 다른 두 입력. 정답으로 볼 값·관계·예상 진단.
3. 목표 환경. Python/Qt/VTK/backend 조합, Windows 기준 장비와 배율, 필요한 실제 solver.
4. 산출물과 공개 진입점. 수정할 모듈 경계, 사용할 GUI/API/CLI, 파일 결과.
5. 지정 자동검사와 실제 사용자 작업. 새 검사가 필요하면 해당 작업의 산출물로 함께 지정한다.
6. 품질 검토 범위. A는 고정한 정보가 풍부한 화면, B/C는 실제 모델·파일 값과 참조를 작성자와 별도 검토자가 확인한다.
7. 이번에 하지 않는 것. 새 요청을 넣을 후속 단계.

한 작업의 종료 상태는 다음 중 하나다.

| 상태 | 판정 | 다음 행동 |
|---|---|---|
| 완료 | 고정 범위의 지정 검사·사용 작업·독립 품질 검토가 통과했고 알려진 계약 위반이 없음 | 구현·검증을 멈추고 다음 작업으로 이동 |
| 구현 완료 / 플랫폼 확인 보류 | 구현과 가능한 관련 검사는 통과했으나 명시된 실제 Windows/OpenGL/solver 환경이 없어 필수 확인을 수행하지 못함 | 부족한 환경과 아직 수행할 정확한 동작만 남김. 해당 플랫폼 납품 완료·A/B/C 완료로 쓰지 않음 |
| 실패 또는 차단 | 지정 조건을 실제 실행했으나 실패하거나 필수 입력·계약이 아직 없음 | 같은 범위의 원인을 수정. 무관한 기능 추가로 우회하지 않음 |

검사를 무조건 한 번만 실행하라는 뜻이 아니다. **최종 후보에 지정 검사를 한 차례 수행 → 실패 수정 → 영향받은 검사만 재수행**한다. 저장 계약·공용 명령처럼 넓은 경계를 바꾸면 그 경계의 기존 회귀 묶음도 재수행한다. 통과 후 코드·입력·환경이 바뀌지 않았으면 반복 실행하거나 새 검사 목록을 늘리지 않는다. 품질 검토가 새 결함을 찾으면 수정·관련 재검사로 닫는다. 새 기능 취향이나 더 큰 모델은 다음 작업으로 보낸다. 검증 횟수 제한을 이유로 실패를 무시하지 않는다.

환경이 없는 검사를 `skip`한 결과는 실제 실행의 증거가 아니다. 현재 CAD 검사에는 SDK/OCP 부재 skip이 있다. CAD 검증은 기존 CI처럼 SDK 초기화를 선행시키고 필요한 실제 사례가 수행됐는지 확인한다. Linux Qt offscreen 테스트는 실제 Windows 글자·아이콘·도킹·3D 품질 확인을 대신하지 않는다.

## 4. P0 — 범위·입력·소유권·성능 기준의 유한 결정

**선행:** 현재 코드/문서와 제공된 참조 제품 비교. 구현을 시작하기 전 현재 테스트 경로와 작동 앱 한 번을 확인한다. 모든 후보 제품을 설치하는 것이 선행 조건은 아니다.

**작업:** 기존 공용 GUI 자산의 실제 접근 가능한 저장소와 소유 위치를 확인한다. HyperMesh/Abaqus/Naksha의 정보 밀도, COMSOL/BeidPrep의 속성·원문, NFX/MeshFree의 조건·케이스 패턴을 목표 장면에 반영한다. 참조 목록만 늘리지 않고 첫 기계 작업 공간과 재료/곡선 공간의 행·열·아이콘·패널·상태를 고정한다. A/C/B용 입력과 capability 범위를 등록한다.

**결정 기한:** 자산/의존성 결정은 최대 2개 집중 작업일, 입력/성능 예산 고정은 1개 집중 작업일을 기본 조사 한도로 삼는다. 이는 전체 구현 납기 약속이 아니라 조사를 종료할 시점이다. 종료 시 `채택한 버전/역할/소유 위치`, `대안으로 진행`, `필수 장애와 영향 작업` 중 하나를 남긴다. 결과 없이 조사 중 상태를 연장하지 않는다.

- 도킹: QDockWidget 기본. 고정된 Windows/PySide 조합에서 Qt ADS의 설치·배치 복원이 기한 내 통과할 때만 채택한다. 실패하면 QDockWidget으로 A 진행.
- 그래프/단위: 고정 버전 pyqtgraph/Pint를 필요한 장면에서만 비교한다. 최소 plot과 명시 단위 변환의 요구를 충족하는 한 경로를 고른다. 개발 branch/latest를 쫓지 않는다. 선택 도구 실패가 트리·세션 개발 전체를 막지 않도록 대체 구현 범위를 고정한다.
- CAD: C에서는 현재 Gmsh worker 경로를 사용한다. 전체 SMTK/SALOME/FEBioStudio 기반을 다시 선정하는 조사로 C를 대체하지 않는다. 그 대안의 실제 필요가 확인되면 P7c의 특정 기능별 비교로 보낸다.
- 공용 GUI 저장소: 기한 내 실물을 찾지 못했으면 `미확인`과 검색 범위만 기록한다. 확인된 코드만 채택하고 미확인 원본의 이전·fork·복제는 하지 않는다. 현재 Prep의 명확한 책임 추출과 새 자체 자산 개발은 진행한다. 나중에 원본을 찾으면 중복 범위를 좁혀 소유권을 정리한다.
- 라이선스: 외부 코드/아이콘의 채택과 배포 조건을 확인한다. 동일 사용자의 두 저장소 간 내부 소비 결정을 저장소 공개 라이선스 신설 문제와 혼합하지 않는다. 명시되지 않은 공개 재배포 허가를 있다고 보고하지 않는다.

**고정할 입력:** A용 실제 구조가 다른 다중 파트 RAD 2개와 기존 작은 보존 입력, 중립 곡선 2개. C용 열린 CAD surface와 다중 solid STEP 각각 한 개 및 구조가 다른 재수행 CAD 한 개. B용 혼합 beam/truss/shell/tet/hex 조립 2개와 100만 실제 요소/100 part/20 source 자료 생성기. 개인정보·제작사 바이너리를 넣지 않고 재배포 가능한 자료 또는 재현 생성기를 사용한다. C는 짧은 확인에 적합하도록 총 2만~10만 요소 범위를 고정하며 B를 대신하지 않는다.

**성능 예산 제안:** P0에서 실제 기준 장비의 사양과 정확한 자료를 고정한다. Windows 11 x64, RAM 32 GiB 이상, 로컬 SSD를 첫 기준군으로 잡고 아래 값을 초기 목표로 사용한다. UI 기준은 1920×1080/100%, 2560×1440/150%, 작은 창/200%다. 이는 시험 환경의 제안이며 사용자의 회사/개인 장비를 임의로 선택한다는 뜻이 아니다. 실제 사용할 장비의 CPU·GPU·RAM·디스크·OS와 dependency 버전은 P0에서 확인된 값으로 기록한다. 기존 구현이 느리다는 이유로 값을 자동 완화하지 않는다. 실측 장비가 다르면 P0 안에서 최종값을 한 번 확정한다.

| B 사용자 동작 | 제안 상한 | 측정 정의 |
|---|---:|---|
| 작업 문서 열기/재열기 | 각각 45 s | 명령 시작부터 표시·선택 가능까지, 초기 renderer 구성 포함 |
| 저장 | 60 s | 저장 요청부터 원자 교체 완료까지 |
| 최대 RSS | 앱 12 GiB / 동시에 살아 있는 앱+worker 합계 16 GiB | 문서+파생 캐시+저장 중 복사와 worker payload 포함. 개별 process peak의 단순 합이 아닌 같은 시점의 process-tree 합계 peak도 확인 |
| 이미 로드된 객체 선택/스칼라 변경·Undo | p95 150 ms / 각각 100 ms | 각 100개 고정 동작에서 사용자 입력부터 화면 반영까지; 저장은 제외 |
| part 숨김/표시 | p95 200 ms | 100개의 고정 part 동작. 전체 mesh 재생성 금지 |
| 취소 응답 | 1 s | UI가 취소 요청을 접수하고 상태 표시하기까지. worker 종료 별도 상한 5 s |

이 숫자는 현재 달성 결과가 아니다. 각 성능 확인은 최종 후보와 한 기준 환경에서 최대 3회로 고정한다(첫 실행 1회와 재실행 2회를 구분). 평균만으로 느린 실행을 숨기지 않고 각 실행의 열기/저장/메모리 상한과 고정 동작의 p95를 모두 확인한다. 이후는 실패 수정의 영향 항목만 재검사하며 새 장비·모델을 추가하는 성능 캠페인으로 확대하지 않는다. 예산 미정이면 P0의 B 착수 조건은 미완료다. 그 경우 A/C처럼 해당 예산을 요구하지 않는 작업은 계속할 수 있다. 측정이 불가능한 상황을 무기한 연구로 전환하지 않고 `B 플랫폼 기준 고정 보류`로 기록한다.

**산출물:** 기존 계획 내 짧은 scope/input/environment 표, 자산 소유 표, 목표 장면 2개, 선택 버전/대안, A/B/C capability·품질·성능 값. 제품 코드 변경 없음.

**지정 확인/종료:** 작성자와 별도 검토자가 범위·입력·목표 화면·예산을 읽고 각 후속 작업의 시작/종료를 판정할 수 있는지 한 번 검토한다. 필수 선택에 빈칸이 없고 선택이 실제로 내려졌을 때 P0 완료. 미발견 비필수 자산은 계속 진행의 장애가 아니다.

**이번에 안 함:** 상용 CAE 전체 비교, 모든 UI 라이브러리 벤치마크, 새로운 CAD 커널/범용 메셔, 제품코드 구현.

## 5. P1 — 공용 계약과 기존 RAD의 첫 연결

### 2026-10-31 첫 구현의 고정 입력과 선택 (P0/A1)

| 항목 | 이번 A 구현에서 고정한 선택 |
|---|---|
| 코드/소유 | main `4828818`에서 전용 로컬 `feat/shared-gui-foundation`. 계약·중립 codec·통합은 root, 공용 Qt/갤러리는 별도 구현자, RAD adapter/실제 앱은 별도 구현자, Astra 설계/독립 검토. Workbench 변경·원격 게시 제외 |
| 목표 화면 | 기계 공간: AB01/AB06/AB28, HM03/HM04/HM23의 트리·압축 속성·중앙 메시. 재료/곡선 공간: COM-T02/T09와 AB27의 동일 값 표/plot. 참조의 정적 관찰을 자체 실행 결과로 세지 않음 |
| 상태/자료 | 기존 two_shell_plates 입력 보존 + 자체 생성 다중 파트 셸/브래킷 및 서로 다른 솔리드 조립 RAD 2개, 중립 plastic/load 곡선 2개. 정상/선택/오류/포커스/비활성, 긴 한글, 1320×840 및 960×640, 100/150/200% |
| 실제 환경 | Windows 11 build 26200, Python 3.13.5, PySide6/Qt 6.9.1, VTK 9.4.2. CIM 장비 조회는 접근 거절되어 CPU/GPU/RAM 미확인. B 성능 기준은 보류하며 A에 대용량 예산을 추가하지 않음 |
| 도킹·그래프·단위 | QDockWidget 기본 채택. 기본 곡선은 Qt QPainter와 model/view 표로 구현(새 plot 의존성 불필요). 제공자가 아는 MPa/GPa·kg/m³/g/cm³만 명시 변환, RAD는 입력 덱 문맥 보존. Pint/ADS·고급 곡선은 후속 |
| 자산 | Prep 자체 SVG/토큰을 소유. 기존 GUI 조사 결과의 planning-only prototype 및 Workbench 테마를 제품 코드로 복제하지 않음. 별도 GUI repo 미확인은 비필수 보류. 외부 벤더 아이콘 추가 없음 |
| 종료 | P1 계약/코어·파일·CLI, P2 위젯/갤러리, P3 실제 RAD와 중립 저장 작업을 검증. 실제 Windows 화면·입력 확인이 불가능하면 해당 항목만 보류, A 완료로 쓰지 않음 |

P0의 A 선택은 위 내용으로 닫고 구현한다. C/B·Workbench·새 카드/Engine·고급 메셔·IPC/MCP·최종 설치 배포는 이번 종료 조건이 아니다.

**선행/입력:** P0의 A 범위·입력, 현재 세션/문서/CLI. B의 장비 미확정과 무관하게 계약 작성 가능.

**작업/산출물:** `application/contracts.py`에 DocumentSession·property/tree/selection provider·Action/capability·structured error/event의 최소 자료형과 호출 예를 둔다. 기존 PrepSession의 RAD 구현을 그 계약에 연결하고 API 호환 경로를 유지한다. typed object/resource/native scope, mesh revision, 단위/좌표/field 성분을 표현한다. 모든 node가 6자유도라는 가정, 전역 native ID, Qt object를 정본으로 삼는 가정을 금지한다. 저장의 공용 컨테이너/codec 인터페이스, expected_revision, 초안 충돌, 최소 작업 상태·완료 상태와 이벤트 스레드 경계를 포함한다.

**지정 확인:** 기존 document/RAD/project/CLI 묶음과 새 `tests/test_application_contracts.py`를 실행한다. 같은 공개 계약으로 RAD의 지원 재료 필드와 비-RAD 곡선 scalar를 조회·수정·Undo한다. 잘못된 단위/참조/expected_revision에서 부분 변경이 없어야 한다. 공용 모듈은 RAD/Qt/VTK import 없이 load되어야 한다.

**종료:** 구현된 호출 예 2개가 실제 값·오류·Undo·개정을 공유하고 기존 CLI 보존 검사가 통과한다. 미래의 모든 물리 descriptor를 다 만들지 않고 계약 경계를 닫는다.

**이번에 안 함:** 모든 schema 통합, assembly 편집, 다중 자원 생성/삭제, 열린 GUI IPC, 자동 단위 추정.

## 6. P2 — 공용 자산·Action·편집 위젯과 부품 갤러리

**선행/입력:** P0의 목표 화면·토큰·상태 목록, P1의 provider/command 계약. P0에서 소유가 확인된 외부 자산만 사용.

**작업/산출물:** `ui/design`, `ui/widgets`, 공용 Action registry와 native gallery entrypoint. 아이콘 의미 키, 행/도구/트리/속성 밀도, 긴 이름/한글/지수/오류/hover/선택/비활성/포커스를 실제 위젯으로 제공한다. tree/table은 Qt model/view와 delegate, property는 그룹·단위·벡터·참조 입력, curve는 기본 table/plot이다. 숫자 초안과 확정 값, 표 붙여넣기 전체 검증, 한 편집 한 Undo를 연결한다. unsupported 도구를 활성 mock으로 채우지 않는다.

공용 위젯은 draft와 입력 이벤트만 소유한다. host adapter는 Prep 명령 또는 기존 Workbench Apply 서비스에 연결할 수 있으며 Prep Document/Dispatcher 생성을 강제하지 않는다. Undo 제공 여부와 의미는 host capability를 따른다. Prep 갤러리/RAD의 Undo와 Workbench MDO 설정의 Apply를 같은 이력으로 합치지 않는다.

**지정 확인:** 새 `tests/test_common_widgets.py`의 값 변경/오류/포커스/한 Undo 사례와 `caelab-prep gallery`를 실행한다. 후자는 이 단계에서 추가할 공개 명령이다. 실제 Windows에서 P0 상태 목록을 100/150/200%로 확인하고 잘림/정렬/읽기 문제를 수정한다. gallery 자체 값이 공용 위젯의 하드코딩 조건이 되면 실패다.

**종료:** 상태 목록과 입력 동작이 같은 공용 부품으로 충족되고 독립 검토자가 고정 화면의 정보 밀도·아이콘·가독성을 통과시킨다. 이후 모든 화면을 만들기 위해 P2를 계속 열어두지 않는다.

**이번에 안 함:** RAD 전체 앱 이전, 두 번째 화면 프로필, CAD 모델링 명령, 고급 곡선 생성/삭제.

## 7. P3/A — 첫 실제 앱 셸과 저장 흐름

**선행/입력:** P1/P2, A용 RAD 2개와 중립 재료/곡선 자료.

**작업/산출물:** 현재 main_window의 Action·트리·폼·도킹·초안/닫기/저장을 공용 셸과 RAD provider로 옮긴다. 공용 viewport frame에 VTK adapter를 앱 조립 지점에서 주입한다. 기계 전처리 공간과 재료/곡선 공간을 완성한다. 공용 atomic container 절차와 RAD v1/중립 curve codec을 제공한다. 최소 작업/취소/파일 오류 계약을 실제 UI에 연결한다. 기본 gallery/곡선 장면을 VTK 없이 실행할 설치 경로를 제공하고 기존 `.[gui]` 경로는 유지한다.

**지정 확인:** 기존 5개 코어/Qt 테스트와 새 계약/위젯/중립 codec 관련 검사. 실제 Windows에서 A1–A8의 고정 작업을 한 차례 연속 수행한다: 파일 열기 → 객체 선택 → 값 오류 → 수정 → Undo/Redo → 저장 → process 종료 → 새 process 재열기 → RAD export. 다른 제공자의 curve도 같은 공용 저장으로 재열고 RAD import가 없어야 한다. 잘못된 숫자, 외부 revision 변경, 저장 실패, 닫기 취소는 기존 값·초안을 보존한다.

**종료:** A1–A8 전부 통과하고 실제 Windows의 정보가 풍부한 두 작업 화면을 독립 검토한다. Windows 부재이면 `구현 완료 / Windows 확인 보류`이며 A 완료가 아니다. A를 통과한 뒤 B/C의 부족을 이유로 다시 A를 무한 수정하지 않는다.

**이번에 안 함:** 새 RAD 카드 생성, CAD 채택, B 규모, 완전한 curve 앱/리본, 열린 GUI MCP.

## 8. P4 — 독립 곡선 앱과 파일 재사용

**선행/입력:** P3/A의 계약·container, 축/단위가 알려진 서로 다른 curve 2개와 CSV.

**작업/산출물:** 독립 재료/curve 앱, table 행 추가·삭제·붙여넣기·graph drag·CSV import/export와 자체 작업문서. 알려진 단위 변환은 provider가 수행한다. drag 미리보기와 commit/취소를 분리한다. RAD FUNCT는 기존 점 편집 지원을 유지하며 새 행/카드는 별도 adapter 명령이 실제 완성된 경우만 제공한다.

**지정 확인:** 새 `tests/test_curve_workflow.py`, VTK/RAD 없는 환경의 독립 앱에서 curve 편집 → Undo → 작업문서 save/reopen → CSV 왕복. CSV에 담기지 않는 단위·참조 metadata를 작업문서에서 보존한다.

**종료:** 두 curve의 값/축/단위/관계가 재열기에서 같고 한 gesture를 한 Undo로 되돌린다. 독립 앱이 P3의 복제 없는 실제 두 번째 소비자다.

**이번에 안 함:** 모든 재료 law, material database 서비스, 모든 CSV dialect, 해석 결과 후처리.

## 9. P5 — 두 번째 화면 프로필

**선행/입력:** P3의 동일 문서/provider; curve 장면은 P4 자료.

**작업/산출물:** COMSOL 계열 tree/settings/graphics 배치와 문맥 command groups. 기존 Action과 편집기를 사용하고 stable dock ID, 앱/프로필/layout-version 키로 환경을 저장한다.

**지정 확인:** 새 `tests/test_layout_profiles.py`와 실제 두 프로필 전환 → 값/선택 유지 → 미완료 초안 처리 → 도킹 이동 → 재시작 복원. 고정 배율·작은 창에서 정보가 잘리지 않는지 확인한다.

**종료:** 문서나 편집기 두 벌을 만들지 않고 배치만 교체되며 프로필 설정이 서로 덮어써지지 않는다.

**이번에 안 함:** 참조 제품의 완전한 ribbon 복제, 사용자별 임의 UI builder.

## 10. P6a — C에 필요한 최소 모델 자원·원자적 채택

**선행/입력:** P1과 P3. C용 준비된 tri/tet 후보 파일, native 번호가 겹치는 두 source, 기존 RAD 보존 입력.

**작업/산출물:** GeometryResource/MeshResource·component·unit/coordinate context와 typed ID, source/native ID scope, compact coordinate/connectivity/offset/type 배열, reverse reference index의 최소 구현. 자원 추가/교체/삭제와 관련 component/assignment를 한 명령으로 commit/Undo한다. 큰 불변 배열은 history entry가 공유하고 작은 편집마다 전체 snapshot을 만들지 않는다. 각 rendering/pick/worker 결과는 document/resource revision에 귀속한다. 공용 container에 mesh payload codec을 추가하고 RAD v1 reader를 유지한다. 생성되는 native 객체에는 source/namespace를 고려한 충돌 없는 ID 할당 정책과 저장·재열기 후 유지되는 ID를 제공한다. UUID/정수 ID를 매번 같은 값으로 재생성하는 deterministic 정책까지 강제하지 않는다.

**지정 확인:** 새 `tests/test_model_resources.py`, `tests/test_resource_transactions.py`와 기존 document/project roundtrip. prepared 후보 하나를 채택·Undo·Redo·저장·재열기한다. 중간 실패를 한 지점 주입해 자원/관계가 모두 이전 상태인지 확인한다. stale pick/result는 거절되고 독립 source의 같은 native 번호가 충돌하지 않아야 한다. compact 배열 ownership과 scalar 수정의 재복사 여부를 계측한다.

**종료:** C가 실제 후보를 문서 정본으로 안전하게 채택할 최소 경로가 동작한다. 최소 참조·값·저장·실패가 닫히면 P6a 완료이며 B 완료는 아니다.

**이번에 안 함:** 모든 assembly/instance 편집, 혼합 DOF 조건 생성 전체, 100만 요소 최종 예산, CAD topology 자동 대응 복구.

## 11. P7a/C — 첫 CAD→메시→문서→native 경로

**선행/입력:** P6a, 기존 worker, C의 고정 CAD/단위/메시 크기/element 범위, 고정 OpenCourant Starter 버전. C는 열린 CAD surface의 tri3 shell과 closed solid의 tet4를 구별한다.

기존 uniform tri/tet의 재현 근거는 재사용한다. 새 face/volume local sizing과 conformal/independent interface는 [F1/F2](mesher-feasibility-roadmap.md)를 통과한 recipe만 제품에 연결한다. 준비된 mesh를 다루는 P6a와 공용 GUI/문서 기반은 이 실증과 병행할 수 있다. 해당 새 동작이 미실증이면 C 전체 완료로 세지 않는다.

**작업/산출물:**

1. GUI에서 CAD import와 dimension/전역 mesh-size/명시 길이단위를 선택하고 Gmsh worker로 후보를 생성한다. C에서 선택한 face/volume에 국소 size를 지정하는 최소 조절도 추가한다. 현재 worker의 uniform min/max보다 확장되는 기능이며, geometry UUID에 속하는 meshing recipe로 저장하고 preview·재생성에 반영한다. edge UUID/1D seed와 자동 adaptive sizing은 후속이다. XAO/MSH/metadata를 한 candidate 묶음으로 다룬다. 후보 생성은 문서 변경이 아니다.
2. 다중 volume의 관계는 conformal 공유 interface와 독립 contact interface를 구별해 meshing recipe에 명시한다. 고정 CAD에는 실제 공유 절점이 필요한 인접 volume 한 쌍과 동일/인접 좌표여도 독립이어야 하는 접촉면 사례를 포함한다. conformal 경계는 node 정체성과 양쪽 element 연결을 실제로 검사하고, independent 경계는 좌표만 같다는 이유로 merge하지 않는다. 기존 backend가 공통 topology를 만들지 못하면 그 준비 동작을 C에서 추가하거나 해당 후보를 거절한다. candidate preview와 element 수·part/source·품질 통계·문제 요소 선택을 표시한다. 명시 단위가 없으면 native export 전에 입력받거나 오류를 반환한다. Gmsh tag를 영속 참조로 사용하지 않는다.
3. `adopt_candidate`를 공용 명령으로 제공한다. expected document/resource revision 검사 후 geometry/mesh/component/연결을 원자 채택한다. Undo는 원래 문서로 돌아가고 실패·취소·문서 교체 뒤 지연 도착한 결과는 정본에 합쳐지지 않는다.
4. 첫 RAD 생성 provider에 새 node/tri3/tet4, part, 탄성 material, shell/solid property와 최소 대상집합/구속을 작성하는 지원 mapping을 명시한다. 현재 patch 경로와 구별하고 새 카드/ID 생성 자체를 C 산출물에 포함한다. node/element만 있는 파일을 완성된 해석 모델이라고 부르지 않는다.
5. material/property/constraint를 실제 값으로 부여 → Undo/Redo → `.caeprep` 저장 → 다른 process에서 재열기 → 지원 native deck export → Starter 읽기를 연결한다. Engine 계산이나 결과 정확도 검증은 C 완료 주장에 포함하지 않는다.

**품질 계약:** geometry boundary의 display facets와 shell physical elements를 구분한다. tetra mesh의 외피를 별도 shell elements로 중복 출력하지 않는다. node 참조/element 중복/퇴화/체적 부호를 검사하고 문제 요소를 선택할 수 있어야 한다. 첫 tri 지표는 `q = 4√3·area / Σ(edge length²)`, tet 지표는 `q = 12·(3V)^(2/3) / Σ(edge length²)`(V는 체적의 절댓값)를 사용하되 tet의 signed volume·orientation 검사를 별도로 수행한다. 절댓값 지표가 음의 Jacobian/뒤집힌 요소를 통과시키지 않게 한다. 정상 정삼각형/정사면체에서 q=1이다. 고정 fixture는 inverted/zero-area/zero-volume 0개와 q_min ≥ 0.1을 기본 수락 조건으로 둔다. q는 모델의 해석 적합성을 보증하지 않는다. 실제 사용자 입력에서는 threshold·경고·채택 여부를 명시하며 silent repair/automatic acceptance를 하지 않는다. C 시작 전에 사용하는 좌표계·면 방향·공차·threshold를 확정한다.

**메시 시간 예산:** C의 CAD 원본·전역/국소 size·thread 수와 결과 규모를 P0/P7a 착수 시 고정하고, 각 후보 생성의 worker 시작부터 XAO/MSH/metadata 완료까지 **120초 이하**를 초기 목표로 둔다. 품질 나쁜 메시를 빠르게 만들어 시간만 통과시키지 않는다. 품질·요소 수·국소 size 요구를 동시에 만족해야 한다. 한 기준 환경의 최초 1회/재실행 2회까지만 비교하고 실패 수정 후 관련 모델만 재수행한다. 이는 일반 CAD 전체의 성능 보증이 아니며 실제 장비가 없으면 확인 보류다.

**지정 확인:** 새 `tests/test_candidate_adoption.py`, `tests/test_mesh_quality.py`, `tests/test_radioss_generation.py`와 기존 `test_gmsh_adapter.py`/project/GUI 관련 검사. 실제 SDK 초기화 후 고정 CAD 3개를 생성하고 품질·채택·Undo·save/reopen을 수행한다. 실제 Windows 3D에서 CAD와 mesh를 구분해 선택하고 문제 요소를 표시한다. 삼각 셸과 tetra 각각 native export를 Starter로 읽혀 node/element/part/material/property/구속의 값·개수를 확인한다. 사용자 파일 로딩 경로를 그대로 쓰며 입력 이름별 특별 처리를 금지한다.

**종료:** C의 두 topology 흐름과 세 입력에서 후보·정본·파일·native 경계가 모두 연결되고 지정 품질을 통과한다. 전체 생성 cell inventory와 SDK 오류를 확인하며 return code 0·일부 요소의 양의 quality만으로 통과시키지 않는다. local size·공유/독립 경계 조건도 실제 충족해야 한다. 실제 Starter가 없으면 native 플랫폼 확인 보류이며 C 완료가 아니다. 대용량/일반 재메시가 남았어도 C를 무한 확장하지 않는다. 세 입력은 첫 연결 검증이며 상용 수준의 robustness 증명이 아니다.

**이번에 안 함:** 모든 CAD 치유, 자동 중립면, hex/sweep, 고차/quad meshing, 일반 mesh 수술, 무제한 contact 생성, 전체 RAD 카드, Engine 자동 작성/solver 실행·후처리.

## 12. P6b — 다중 파트·혼합 필드·집합·조건 관계

**선행/입력:** P6a와 B의 혼합 조립 자료 2개. P7a/C는 권장 선행이지만 실제 B 의미 구현의 기술적 필수는 아니다.

**작업/산출물:** 기존 B 범위의 assembly/FE component·source, 공유 mesh와 독립 동일 ID, 정적 Cartesian 좌표, explicit node/element/surface sets, material/property assignment, 조건 정의와 case 활성, contact의 두 영역, curve/connection 참조. field/formulation provider로 대상별 활성 성분을 계산하고 native 1–6을 공용 자유도 정의로 쓰지 않는다. create/edit/delete/reassign을 atomic 명령으로 제공하고 reverse references로 영향 범위를 찾는다. 반복 instance는 기존 B 선언대로 표현/조회/저장만 보장한다.

**지정 확인:** 새 `tests/test_model_relations.py`, `tests/test_condition_fields.py`, `tests/test_model_roundtrip.py`; B1–B4와 B6의 의미/파일 작업. shared node와 별도 source의 동일 번호, part 이름 중복, shell/solid/beam 접점, 서로 다른 case의 같은 조건, 좌표계 지정, dangling/stale relation을 확인한다. 준비된 replacement mesh로 stale set/contact/pick을 검출하고 임의 ID 재사용을 하지 않는다. 명시한 RAD native 지원 범위만 export/Starter 읽기로 확인한다.

**종료:** B1–B4·B6 의미 조건이 통과하면 P6b 완료. B5 성능이 남으면 B 완료가 아니다. 표현 가능한 일반 scalar field를 thermal/CFD solver 지원이라고 보고하지 않는다.

**이번에 안 함:** 모든 해석 physics/과구속 수치 판정, 반복 instance placement/native expansion, 자동 CAD remap, 고급 solver contact 전체.

## 13. P6c/B — 배열·지연 UI·저장과 규모 예산

**선행/입력:** P6b, P0에서 확정한 B 장비/정확한 generator/예산. 이 단계부터 input 규모·budget을 구현 통과 목적으로 완화하지 않는다.

**작업/산출물:** indexed lookup, lazy tree/table, versioned projection cache, 부분 invalidation과 typed payload codec. 문서·VTK·worker·저장 간 사본의 소유자/수명/해제를 정한다. Gmsh worker의 전체 JSON arrays 중복을 large-mesh 경로에서 binary payload + metadata로 이행하되 현재 작은 후보 API의 호환성 정책을 둔다. compressed ZIP의 직접 mmap을 가정하지 않고 독립 binary chunk 또는 관리되는 불변 파일 중 한 경로를 고른다. HDF5/Zarr/mmap을 모두 도입하지 않는다.

**지정 확인:** 기존 B 의미/roundtrip 검사, 새 `tests/test_large_model_behavior.py`의 제한된 invalidation/취소/참조 검증, `python tools/benchmark_model.py --profile b-reference`의 고정 100만 실제 요소 시나리오. 이 benchmark 파일/프로필은 이 단계의 새 산출물이다. actor만 복제해서 요소 수를 채우지 않는다. 같은 최종 후보에서 열기/재열기/저장/peak RSS와 고정 100회 selection/edit/hide를 측정한다. P0의 최대 3회 실행 원칙을 따르고 cold/warm 결과를 구분한다. 실패한 지표 원인을 수정한 뒤 관련 시나리오만 재측정한다.

**종료:** B1–B6와 고정 budget이 모두 통과하면 B 완료. 느린 수치가 측정됐다는 사실만으로 통과하지 않는다. 작성자 외 검토자는 저장 후 재열린 관계·native 결과·실제 모델 조작을 확인한다.

**이번에 안 함:** 더 큰 임의 모델, 모든 GPU/원격 파일시스템, 모든 배열 저장 backend, 계산 자유도 숫자 추정.

## 14. P7b — 일반 mesh 변경과 재메시 재연결

**선행/입력:** 전체 P7b에는 P6b와 C의 자원·관계·native 경계를 모두 사용한다. 순수 메시 수정 일부는 먼저 착수할 수 있으나, 조건 재연결까지 포함한 P7b 완료와 구분한다. part 경계·shared nodes·sets/conditions가 있는 고정 mesh 2개와 이전/교체 CAD 한 쌍을 사용한다.

**고정 첫 범위:** node 좌표 이동, 선택 node의 명시 tolerance merge, element 삭제와 고립 node 처리, shell normal 반전, part/집합 재배정, size 변경에 의한 재메시. 합치면 안 되는 component/접촉면의 node는 자동 병합하지 않는다. edge split/swap, quad/tri 변환, 고차 승격 등은 다음 소묶음으로 명시한다.

**작업/산출물:** 각 operation의 적용 가능 조건·영향 preview·품질 변화·참조 변화·atomic commit/Undo. 새 mesh revision에서 geometry 기반 named region은 실제 backend 대응이 있을 때만 재평가한다. explicit sets는 stale로 표시하고 사용자가 확인하는 재연결 명령을 제공한다. 동일 번호/최근접 좌표만으로 하중·접촉을 조용히 이동하지 않는다.

**지정 확인:** 새 `tests/test_mesh_operations.py`, `tests/test_remesh_relations.py`; 지정 operation 각각에서 품질 전후·참조·Undo·save/reopen·지원 native export를 확인한다. 다른 source의 같은 ID, 공유 경계 merge, 표면 방향에 의존하는 조건을 포함한다.

**종료:** 고정한 6개 operation과 재연결 정책이 실제 두 자료에서 통과한다. 자동 복구 불가 영역이 명확히 stale로 남고 export의 차단/명시 제외 정책이 작동하면 자동 완전 복구를 기다리지 않는다. 단, 유효하지 않은 하중을 정상으로 출력하면 실패다.

**이번에 안 함:** 임의 mesh 수술 전체, 모든 CAD topology 변경 추적, 모든 손상 geometry 치유.

## 15. P7c — 실증 후 착수할 메시 확장과 별도 연구

P7c는 하나의 무기한 연구 과제가 아니다. `P7c-S`, `P7c-M`, `P7c-H`를 독립적으로 착수/종료한다. P7c-S는 자동 중립면 구현을 기다리지 않고 준비된 선/면을 사용해 먼저 끝낼 수 있다. 한 기능이 실패해도 C/B나 다른 P7c 기능 완료를 취소하지 않는다.

다음 표는 **제품 연결을 진행할 수 있을 때의 목표 조건**이며 모두 구현 가능한 것으로 확정한 backlog가 아니다. [F0–F2 실증](mesher-feasibility-roadmap.md)을 기능별로 통과해야 착수한다. 복잡 rib/boss·가변두께 중립면과 일반 CAD 자동 all-hex는 현재 확정 구현/납기에 포함하지 않으며 연구·SDK·외부 프로그램 평가로 분류한다.

| 작업 | 고정 첫 입력/기능 | 산출물과 지정 확인 | 종료 조건 / 제외 |
|---|---|---|---|
| P7c-S 선·준비면 | CAD curve와 연결 frame 2개, 이미 준비된 midsurface plate/절곡 shell 2개; 1D line/beam/truss와 준비면의 선형 tri | 1D backend/edge identity, section·orientation/local axis, shell thickness/normal/offset·원 solid 참조. 편집·quality·Undo·save/reopen·지원 native mapping 검사 | 선 단면/방향과 shell 법선/두께/offset이 실제 native 읽기까지 유지. quad 생성은 H-Q 이후 별도 확장이며 S 종료 조건에 포함하지 않음. 자동 midsurface·고차 beam·일반 joint formulation 제외 |
| P7c-M 중립면 | 일정 두께 plate, 절곡 plate, 단순 rib/접합의 재배포 가능 CAD; 두께·offset·연결 공차 지정 | backend별 실제 capability 평가 후 한 경로 선택. 중립면 후보+두께/offset/원 solid 연결, 수동 보정, shell mesh, 품질/물리 할당·save/reopen/native | fixture 각각에서 중립면 위치/두께/접합 오차를 고정 tolerance로 충족. 임의 casting/variable-thickness의 완전 자동 추출 제외 |
| P7c-H quad/sweep/혼합 mesh | H-Q: mapped/recombined quad면 2개. H-S: block/원통·분할 sweep volume. H-T: 미리 분할한 hex↔tet 전이 영역과 prism/pyramid를 명시한 혼합 fixture | 각 소묶음의 capability·seed/layer/공유 interface·quality 목표를 고정. family별 connectivity·orientation·formulation과 RAD native mapping 표, adoption·Undo·save/reopen. 미지원 family의 native export는 차단 | H-Q/H-S는 고정 품질·연결·저장·native 조건으로 각각 종료. H-T는 아래 중립/실제 native 완료를 별도 판정. 미지원 family를 임의 degenerate element로 바꾸거나 버리지 않음. 임의 CAD all-hex/자동 decomposition/모든 hybrid 생성 제외 |

H-T는 **중립 생성·편집 완료**와 **RAD native 완료**를 분리한다. 중립 완료에는 고정한 전이 fixture의 연결성·품질·채택·Undo·저장/재열기가 필요하다. RAD native 완료에는 모든 요소 family가 실제 지원되는 전이 모델 최소 한 개의 native 출력·Starter 읽기를 추가로 통과해야 한다. 지원되는 전이 모델이 없으면 native 단계는 차단/미구현으로 남는다. 중립 표현과 export 차단만으로 H-T 전체 완료 또는 RAD hybrid 지원을 선언하지 않는다.

backend 조사 **최대 3개 집중 작업일**은 F0의 실제 source/API·접근성·도입 경로 판정에만 적용한다. F1의 독립 재현과 F2의 고정 형상군·품질/기하/연결 검사를 통과하기 전에는 “지원하므로 구현 가능”으로 바꾸지 않는다. 통과한 버전/recipe/지원 범위를 고정한 뒤 제품 연결을 한다. 실패하면 원인과 제한/SDK/외부 도구/연구 중 다음 경로 하나를 남기고 평가를 닫는다. 조사 기한 종료나 문서 정합성 검토를 기능 완료로 쓰지 않는다. 처음부터 CAD kernel이나 범용 mesh generator를 직접 작성하는 계획으로 자동 전환하지 않는다.

## 16. P8 — 작업·자동화와 Workbench 경계

P8을 C 뒤에 전부 몰지 않는다. `P8a`의 progress/cancel/error/artifact/result/adoption 자료와 세션 직렬화는 P1/P3에 최소형을 두고 C에서 실제 worker와 연결한다. `P8b`의 독립 API/CLI는 각 명령이 구현될 때 추가한다. `P8c`의 열린 GUI IPC/MCP만 계약 안정 이후 후속으로 둔다.

| 세부 단계 | 고정할 범위와 종료 조건 |
|---|---|
| P8a 작업 계약 | 파일/CAD 작업의 진행·실제 취소·실패·후보 산출물·채택을 구분하고 한 곳이 worker를 종료. A/C의 해당 작업에서 확인 후 종료 |
| P8b API/CLI | 선택한 조회·편집·채택·저장 명령을 실제 독립 subprocess로 호출. GUI와 같은 값/오류·개정 검사 및 저장 결과를 확인하면 종료 |
| P8c-IPC | 열린 Prep 문서 하나에 연결해 조회·값 변경·저장. draft 충돌·오래된 handle/개정·연결 해제·작업 취소를 고정한 사례로 확인하면 IPC 완료 |
| P8c-MCP | 같은 API의 조회/변경/작업 도구를 실제 목표 클라이언트 한 종류에서 호출. 대상 문서·오류·취소·파일 결과를 확인하면 해당 연결 완료. IPC만 작동한 상태와 구분 |

P8c의 첫 범위는 문서 하나의 조회, 지원 scalar 수정, 저장과 C meshing 작업의 상태/취소다. 모든 모델링 명령을 처음부터 MCP 도구로 확장하지 않는다. 실제 클라이언트가 없으면 MCP 확인 보류로 남기며 P8a/b 완료를 취소하지 않는다.

**선행/입력:** P8a는 해당 단계의 세션·파일/worker 구현과 함께 개발하며 A/C 완료를 기다리지 않는다. P8b/c는 연결할 공개 command/capability가 이미 구현되어 있으면 착수할 수 있고 A/B/C 전체 완료를 일괄 요구하지 않는다. Workbench 파일 역할·상태·오류 계약은 실제 Workbench 연결을 구현할 때만 적용한다. 독립 Prep의 API/CLI를 Workbench의 존재에 종속시키지 않는다.

**산출물:** GUI·in-process API·CLI가 같은 command validation/Undo/save를 사용한다. 새 CLI는 JSON 요청/결과·명시 exit code·capability query·output file을 갖는다. Workbench에는 프로젝트/입력/작업문서/native deck/로그의 역할을 돌려주고 Prep 내부의 live Python/Qt object를 직렬화해 보내지 않는다. GUI IPC는 document ID/revision/owner를 확인하고 열린 문서의 변경을 소유 세션에 전달한다. 연결 실패 시 별도 사본을 몰래 편집하지 않는다.

**지정 확인:** API와 GUI에서 같은 request가 같은 값/오류를 내는 관련 검사, 실제 subprocess CLI, 실패·취소·partial output·동일 문서 동시 변경 거절. IPC를 착수한 경우만 실제 열린 GUI의 revision conflict와 disconnect 재연결을 확인한다.

**종료:** 선택한 transport 범위에서 실제 사용자 작업을 수행하고 생성 파일의 역할·상태·소유자가 명확하다. CLI 완료와 live GUI IPC 완료를 서로 대신하지 않는다.

**이번에 안 함:** Prep의 두 번째 solver job queue, Workbench 프로젝트 DB 복제, 모든 solver schema 통합, 기존 CalculiX/PrePoMax 경로 교체. Workbench가 시작한 solver 실행은 기존 JobManager가 소유한다. Prep은 독립 실행·사용자 파일 편집 기능을 유지한다.

## 17. P9 — 각 완료 묶음의 배포

**선행/입력:** A 또는 C/B 등 명시한 완료 묶음. 필수 native Windows 확인은 해당 묶음의 조건대로 수행한다.

**작업/산출물:** 선택 설치 옵션(core/common-Qt/VTK/CAD)과 public API 사용 예, gallery, 독립 RAD 앱, 필요한 CLI, Windows 실행 묶음. 사용자 설정·작업파일·임시 후보·log 위치와 오류 안내를 정한다. installer 선택은 dependency/asset/license 조건을 확인한 뒤 한 경로로 고정한다.

**지정 확인:** 깨끗한 Windows 사용자 환경에서 설치 → gallery → 실제 파일 열기/수정/Undo/save/reopen/export → 제거 또는 portable folder 이동. Qt-only 장면에 VTK/Gmsh가 필요하지 않은지 확인한다. C를 포함하면 worker DLL/Gmsh dependency와 취소를 확인한다. 새 설치 검사만을 위해 전체 solver 성능 시험을 반복하지 않는다.

**종료:** 명시한 묶음의 공개 명령과 파일 작업이 새 Windows에서 작동하고 사용법·지원 범위가 실제 결과와 일치한다. 하나의 release에 후속 모든 기능을 끌어넣지 않는다.

**이번에 안 함:** Mac/Linux installer 동시 완성, 기업 자동배포·auto-updater, 전체 상용 CAE 호환.

## 18. 검증 명령의 현재/계획 구분

다음 명령은 현재 저장소에 존재하는 경로다. 실제 실행은 환경별로 나눈다.

```sh
# core/CLI 환경
python -m pip install -e ".[dev]"
python -m pytest tests/test_document_core.py tests/test_radioss_editing.py tests/test_project_roundtrip.py tests/test_cli_workflow.py

# Qt 환경. offscreen 실행은 실제 Windows UI 검증과 구분
python -m pip install -e ".[gui,dev]"
python -m pytest tests/test_gui_document_flow.py

# 별도 CAD 시험 환경. OCP는 테스트 CAD 생성용이며 제품 의존성 아님
python -m pip install -e ".[cad,dev]" cadquery-ocp==7.8.1.1.post1
python -c "import gmsh, OCP; gmsh.initialize(interruptible=False); gmsh.finalize()"
python -m pytest tests/test_gmsh_adapter.py

# 현재 지원하는 독립 후보 생성. OUT은 비어 있는 새 출력 디렉터리
caelab-prep mesh INPUT.step --output OUT --size 2.0 --dimension 3
```

`test_application_contracts.py`, `test_common_widgets.py`, `test_rad_provider.py`와 `caelab-prep gallery`는 첫 구현에서 추가했다. 나머지 단계의 `test_curve_workflow.py`, `test_layout_profiles.py`, `test_model_resources.py`, `test_resource_transactions.py`, `test_candidate_adoption.py`, `test_mesh_quality.py`, `test_radioss_generation.py`, `test_model_relations.py`, `test_condition_fields.py`, `test_model_roundtrip.py`, `test_large_model_behavior.py`, `test_mesh_operations.py`, `test_remesh_relations.py`, `tools/benchmark_model.py`는 **후속 작업에서 추가할 산출물 이름**이다. 이 나머지 항목을 현재 실행 가능한 것으로 기재하지 않는다. 같은 책임의 기존 검사가 있으면 그 파일에 합친다.

## 19. 문서와 작업 상태의 관리

### 2026-10-31 첫 구현 결과

**P1–P3 구현 완료 / Windows 확인 보류. A 완료 아님.** 전용 브랜치 `feat/shared-gui-foundation`에서 공용 계약·디자인·위젯·실행 갤러리·RAD adapter/실제 화면·중립 codec을 구현했다. 초기 main은 `4828818`이며 원격 push/PR/병합과 Workbench 변경은 하지 않았다.

- 통합과 공용 Qt/RAD 구현: GPT-6.1 Sol/high. 계약 검토와 작성자와 다른 독립 코드·기능·렌더 검토: GPT-6 Astra/xhigh. 파일 소유를 나누고 통합자가 최종 수정·검사를 수행했다.
- A2/A3: 실제 RAD와 갤러리가 같은 디자인·Action·model/view 트리·그룹 속성·숫자/단위·벡터·곡선 표/plot·도킹·뷰포트 프레임·비동기 FileTask를 사용한다. 선택·초안·검증·한 명령/Undo·dirty·저장이 연결된다. unsupported 동작은 활성 mock으로 추가하지 않았다.
- A4/A5: 원래 작은 회귀 자료와 `examples/rad/shell_panels_0000.rad`(27절점/12quad/3파트), `solid_blocks_0000.rad`+INCLUDE(16절점/2hex/2파트)를 같은 경로로 읽고 지원 필드·기존 FUNCT/속도 벡터를 편집했다. `.caeprep` 재열기·RAD 출력의 값·미지원 원문·BCS/IPLAS·INCLUDE 보존과 기존 CLI 새 프로세스 흐름을 확인했다. 중립 재료/곡선은 RAD import 차단 상태의 새 프로세스에서 재열었다. 이 예제는 편집 검증 입력이며 솔버 계산 검증 모델이 아니다.
- A6/A8: 불완전 숫자/NaN/Inf·부분 오류 batch·단위·오래된 문서/개정·입력 중 외부 교체·저장/읽기 실패·닫기 취소·활성 표 셀 저장·picker 충돌을 검증했다. 위젯은 초안을 유지하고 확정값은 바뀌지 않는다. 공용 Qt/갤러리는 RAD/VTK/main_window import를 금지한 프로세스에서 로드된다. `[widgets]`는 Qt만 요구하며 `[gui]` 호환 경로를 유지한다.
- 최종 관련 검사: `test_document_core`, `test_radioss_editing`, `test_project_roundtrip`, `test_cli_workflow`, `test_application_contracts`, `test_common_widgets`, `test_rad_provider`, `test_gui_document_flow` **70 passed, 1 skipped**. skip은 Windows에서 대소문자만 다른 두 파일을 만들 수 없는 기존 검사다. 독립 검토의 남은 코드/기능 결함은 없음. setuptools backend wheel 생성도 성공했다. 깨끗한 설치형 배포 검증은 이번 범위가 아니다.
- A7: 설치된 Windows Segoe UI/Malgun 글꼴을 QA 프로세스에 로드한 Qt offscreen 정상/좁은 창·오류/벡터/곡선 렌더를 작성자와 독립 검토자가 확인하고 수정했다. `docs/gallery-preview.png`는 그 미리보기다. **실제 Windows 입력·100/150/200% DPI·도킹 이동/재시작 배치·VTK 조작은 미확인**이다. 실제 Qt/VTK 프로세스의 창 `52953454`(two_shell_plates_0000.rad — CAELab Prep)는 Windows 창 목록에 나타났지만, `cua.getApp`의 앱 접근 승인이 시간 초과됐다. 승인이 완료되지 않은 상태이며 UI 입력/캡처는 실행하지 않았고 우회/재시도하지 않았다. 최종 창 목록에는 테스트 창이 남아 있지 않다.
- 세션 공유 URL: 공유 도구가 `Thread sharing permissions or account policy could not be determined`를 반환해 생성하지 못했다. 검증된 공유 URL이 없어 임의 링크를 만들지 않았다.

다음은 접근 승인 가능한 실제 Windows 세션에서 위 A7 항목만 확인하는 것이다. C/B·Workbench·새 RAD 카드/Engine·고급 메셔·MCP 전체·설치형 배포를 A 종료 조건에 추가하지 않는다.

- `shared-cae-foundation-plan.md`: P0–P9 번호와 A1–A8은 유지. 9절 P6/P7/P8 표의 세부 단계·선행 관계, 10절 묶음 C와 종료 상태, 12절 미확정 처리의 유한 결정을 반영한다. 단계별 실행·검사는 본 작업서에서 관리하고 기존 문서에는 링크와 묶음 표만 둔다.
- `cae-model-data-design.md`: 7절의 P6→P6a/b/c, P7→P7a/b/c 설명을 맞추고 8절 B1–B6은 그대로 유지한다. P6a/C가 B나 반복 instance 편집 완료가 아님을 명시한다. P7 일반 재메시라는 기존 문구는 P7b로 구체화한다.
- `README.md`: 현재 기능 표와 미구현 표를 계획만으로 바꾸지 않는다. 공용 기반/A/B/C의 실행계획 링크만 갱신한다. 각 묶음이 실제 완료된 뒤 현재 상태·명령을 업데이트한다.
- `DESIGN.md`: 공용 자산 목적·Workbench 책임·여러 참조 제품·native 보존 원칙은 유지. 첫 CAD 경로와 후속 고급 메시 범위만 맞춘다.
- `ARCHITECTURE.md`: 현재 Gmsh 후보/한 자원 Undo/미구현 native 생성 등 사실은 유지한다. 목표 단계 링크만 바꾸며 C 산출물을 현재 코드로 적지 않는다.
- `gui-reference-matrix.md`: 자료를 새로 무한 수집하지 않고 P0 목표 장면에 연결한다. 공개 화면 관찰과 실제 실행 검증의 구분을 유지한다.
- Workbench 연동 문서: Prep의 자원/파일/자동화 계약은 이 저장소 소유, Workbench 프로젝트/실행/결과 참조는 Workbench 소유로 연결한다. 양쪽 문서에 다른 JobManager나 공통 전역 FE 모델을 각각 계획하지 않는다.

계획 문서의 완료는 위 범위·선행 조건·산출물·검사·종료·제외가 일관되고, 현재 구현과 후속 목표를 혼동하지 않으며, Prep과 Workbench의 독립 검토에서 책임 충돌이 해소된 상태다. 이를 위해 제품코드나 새 테스트를 이번 문서 작업에 추가하지 않는다.
