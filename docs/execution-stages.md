# Prep 단계별 개발 작업·종료 조건

문서 상태 정리: 2026-11-02. 현재 병합 기준은 Prep main `89bd700`(PR #17/#18/#20/#21/#22/#24/#25)와 Workbench main `865ee15`(PR #55)다. N19/N20의 지원 범위·남은 플랫폼 검증도 해당 행에서 구분한다. 제품 목표의 원본은 [DESIGN의 R1–R4/T1–T6/G0–G4](../DESIGN.md#delivery-goals), 현재 상태·잔여 개수·다음 작업·완료 기준은 [19절 남은 작업표](#remaining-work)다. 이 문서는 기술 작업 P0–P9와 기존 B1–B6의 상세를 연결한다. 과거 A1–A8/C의 한정된 판정을 현재 8방식 실무 목표의 완료로 쓰지 않는다. **후속 구현 요청에 따라 19절의 작은 체크포인트로 코드와 실제 결과를 연결한다. 19절은 미해결 사항과 기록을 모은 절이며 1–18절 또는 G0–G4의 완료를 뜻하지 않는다.**

초기 작업서 기준은 `5d16e81c7ec7c92499401d63208039424bf73cc9`, 2026-10-29였다. 아래 날짜가 붙은 선택·결과·승인 설명은 해당 시점의 저장소 기록으로 보존하며 새 작업의 승인이나 독립 검증으로 전용하지 않는다. [공용 기반 설계](shared-cae-foundation-plan.md), [모델·데이터 설계](cae-model-data-design.md), [Workbench 재사용 계획](workbench-reuse-plan.md)의 기술 경계를 함께 따른다.

2026-10-30 보완: 고급 메셔는 이 표에 있다고 구현 가능성이 입증된 것이 아니다. 실제 공개 코드·상용 매뉴얼·알고리즘 조사와 별도 SDK 실험은 [메셔 실현 가능성 로드맵](mesher-feasibility-roadmap.md)에 둔다. P7c의 후보 선택 뒤 바로 제품 구현을 확정하지 않고 F0–F2 실증을 선행한다. 아래 앱/파일 검증과 그 별도 SDK 실험을 혼동하지 않는다.

2026-10-30 자료 보강: [벤치마크 자료지도](benchmarks/2026-10-30/README.md)에 7제품의 9과업·123장면과 근거/결손을 연결했다. P0는 이 자료에서 목표 장면·상태·자체 입력·환경을 실제 선택한다. 자료 수집과 P0 완료를 합치지 않으며 신규 메셔 연구 전체를 공용 GUI 개발의 선행 조건으로 만들지 않는다.

## 1. 검토 결론과 수정할 선행 관계

현재 우선순위는 **실제 사용자 과업을 8제품별 방식으로 끝내는 것**이다. 갤러리·하나의 조합 화면·기존 scalar 수정으로 첫 납품을 대체하지 않는다. PR #15에서 연결한 공용 계약/위젯과 생성·삭제·할당은 유지하고 N01 케이스/영속 해석 설정, N02 외부 독립 메시 import부터 보완한다. P5는 선택적 후속 배치가 아니라 G1의 필수 8방식 상호작용이다. 다만 공통 명령을 만들기 전에 8개 화면을 동시에 구현하지 않으며, 한 실제 UI에서 명령·초안·파일 연결을 확인한 뒤 같은 명령을 다른 adapter로 확대한다.

아래는 납품 묶음의 의존 순서이며 현재 잔여 목록이 아니다. 원래 실행 순서는 `G0 → G1(T1/T2) → G2(T3/T4) → G3(T5/T6)`이며 G4의 실제 소비·API·Windows 배포는 사용할 기능부터 병행한다. G1 첫 작업은 DESIGN에 정의한 **2파트 이상·재료 2개·단면 2개의 생성/할당/교체와 Undo·저장·재열기·native 관계 확인**이다. 전체 대용량 B를 G1 또는 첫 CAD 연결의 선행 조건으로 삼지 않는다. B의 다중 자원·성능, P7b의 일반 수정/재메시와 P7c의 조건부 고급 메시, P8c live IPC/MCP는 별도 미완료 범위로 유지한다.

| 순서와 기술 단계 | 끝낼 작업 | 단계 종료의 핵심 |
|---|---|---|
| G0 / P0 | 작업 계약·입력·8제품별 근거·소유권 고정 | 필수 선택을 내리고 조사 종료. 미확인 원제품 접근은 비교 판정에 남김 |
| G1 / P1–P3·P5·P6a/b 일부 | 사용자 파트의 재료/단면 생성·할당과 8방식 작업 | 같은 값/관계의 편집·취소·Undo·재열기·native 출력, 기능/UI/비교/공통화/플랫폼별 판정 |
| G2 / P4·P5·P6b | 곡선·집합·조건·케이스의 생성과 실제 참조 | T3/T4의 값·단위·대상·물리 의미, 8방식 사용과 파일 보존 |
| G3 / P6a·P7a/C 확장·P5 | CAD/메시 후보·채택에서 Starter/Engine까지 | C의 tri/tet 품질·세 입력 기준 유지, G1/G2 관계와 새 Engine 생성·입력 검사 연결 |
| G4 / W1·W2·P8a/b·P9 | 실제 host 재사용·공용 API/CLI·Windows 전달 | 실제 소비자와 새 설치에서 이미 완성한 작업을 수행; W1/W2 별도 판정 |
| 보존한 기존 요구 / B·P7b | 혼합 자유도·대용량·일반 수정/재메시 | B1–B6 시간/메모리와 관계 기준을 별도로 통과 |
| 조건부 확장 / P7c | 중립면・sweep/hex·자동 커널 연구 | 실제 코드/API → 독립 재현 → 지원 형상군 실증 뒤 제품 연결. no-go와 기능 완료 구분 |
| P8c | 열린 GUI의 live IPC/MCP | 실제 클라이언트의 handle·revision·화면 반영. CLI 새 프로세스로 대체 불가 |

G1-a–e는 PR #15 착수 당시의 구현 순서로 [19절](#current-progress)에 보존했다. 새 세션은 이를 처음부터 반복하지 않고 [현재 N 항목](#remaining-work)을 진행한다. 체크포인트는 최종 목표를 대체하지 않는다. 작업을 나눌 때 R/T 번호·동일 입력·종료 상태·공통 계약·파일 소유·검증 증거를 함께 전달한다. 관련 없는 플랫폼 확인 보류로 독립 구현을 멈추지는 않지만 보류된 납품을 완료로 쓰지 않는다. 이 문서를 작성한 것만으로 위 구현 단계가 완료된 것은 아니다.

## 2. 코드 출발점과 실제 간극

아래 표는 초기 2026-10-29 분석의 출발점을 보존한다. `f4d12d0`에는 이후 Action·선택·셸·공용 위젯·RAD/중립 provider·atomic storage가 추가됐다. 따라서 표의 모든 추출 작업을 처음부터 재개발하지 않는다. 현재 유지/확장 경계는 [ARCHITECTURE](../ARCHITECTURE.md), 납품 상태는 [19절](#current-progress)을 따른다. 생성/삭제·파트 할당·CAD 채택·새 native 생성은 PR #15에서 지원 범위를 연결했으며 아래 초기 간극 전체를 현재 미구현으로 읽지 않는다.

| 출발점 | 이미 있는 것 | 후속 작업에서 반드시 추가할 것 |
|---|---|---|
| `cae_core/document.py` | opaque Resource, 한 자원의 상태 변경/Undo, revision·dirty·선택 | 자원 생성/삭제·다중 자원 원자적 commit, 메시에 대한 값 복사 없는 이력, 범위 있는 typed 참조 |
| `application/session.py` | RAD/INCLUDE 열기·patch·ZIP 저장·내보내기, 호출 직렬화 | 공용 세션/codec 경계, 비-RAD 문서, 새 native 객체 생성·안정적인 ID 배정 |
| `ui/main_window.py` | 실제 RAD 편집과 파일 실패/초안 보존 | 공용 Action/트리/속성/셸 추출, 지연 모델/뷰, 긴 작업의 후보/채택 상태 |
| `ui/viewport.py` | VTK 투영·절점/요소 pick | 자원/개정/종류를 가진 선택, CAD·mesh·surface 표시의 구분, 부분 갱신과 cache 수명 |
| `gmsh_worker.py` | 균일 mesh-size, dimension 2/3, 1차 요소, XAO/MSH/연결 metadata, process 경계 | 품질 측정·표시, 문서 채택, native 생성; 대용량에는 전체 coordinates/connectivity JSON list 중복 전달 제거 |
| 기존 검사 | document/RAD/roundtrip/CLI/Qt 문서/CAD worker 테스트 | 공용 계약·자원 채택·모델 관계·실 GUI·실 solver에 대한 해당 단계 검사 |

초기 분석에서는 tri/tet 표시만으로 native 생성을 완료 처리하지 않았다. 현재 writer/채택/solver 검사의 근거는 19절에 별도로 연결한다. CAD 후보의 tet 외피 facet은 경계 표현이며, 이를 shell 물리요소로 함께 채택하지 않는다. `.caeprep` v1이 RAD 원문과 patch를 저장한다는 사실도 임의 메시/재료를 저장할 공용 codec이 완성됐다는 뜻이 아니다.

## 3. 모든 작업에 적용할 종료 규칙

작업을 시작할 때 아래 7개 항목을 PR 본문 또는 이 계획의 해당 행에 고정한다. 별도 프로젝트 관리 시스템이나 검사 대시보드를 만들지 않는다.

1. 범위와 끝낼 사용자 작업. 현재 단계에서 지원할 형식/요소/필드/생성·수정 동작.
2. 입력 파일/생성기와 데이터 규모, 정답으로 볼 값·관계·예상 진단. 구현 체크포인트는 한 고정 입력에서 시작할 수 있으나 G1 종료에는 작은 회귀 자료 외에 DESIGN의 서로 다른 두 입력과 실제 사용 작업을 확인한다.
3. 목표 환경. 현재 Linux의 Python/Qt/VTK/backend 조합·실제 동작/렌더 가능 범위와 필요한 solver를 기록한다. Windows 장비·배율·OS 입력·GPU·새 설치는 사용자 지시에 따라 일괄 후속 검증으로 분리한다.
4. 산출물과 공개 진입점. 수정할 모듈 경계, 사용할 GUI/API/CLI, 파일 결과.
5. 지정 자동검사와 실제 사용자 작업. 새 검사가 필요하면 해당 작업의 산출물로 함께 지정한다.
6. 품질 검토 범위. 모든 G에서 기능/파일·UI·원제품 동일 작업 비교·공통화/재사용·실제 플랫폼을 각각 `통과/실패/미확인/미구현`으로 판정한다. 코어/파일 체크포인트의 종료는 그 경계에 한정하며 아직 연결하지 않은 UI나 접근할 수 없는 플랫폼의 합격을 요구하거나 대신 선언하지 않는다. 작성자 외 검토자가 같은 SHA의 원래 R/T 요구, 실제 연속 작업과 산출물을 본다. G1–G3의 공통화와 G4 외부 host 실사용은 구분한다.
7. 이번에 하지 않는 것. 새 요청을 넣을 후속 단계.

한 작업의 종료 상태는 다음 중 하나다.

| 상태 | 판정 | 다음 행동 |
|---|---|---|
| 완료 | 고정 범위의 지정 검사·사용 작업·독립 품질 검토가 통과했고 알려진 계약 위반이 없음 | 구현·검증을 멈추고 다음 작업으로 이동 |
| 구현 완료 / Windows 일괄 후속 검증 | 현재 범위의 구현·Linux 동작/렌더 가능 범위·독립 리뷰·해당 CI가 통과했고 Windows 검증만 사용자 지시에 따라 연기함 | 통합 담당이 중간 PR을 병합하고 다음 구현 진행. Windows 실행/품질 통과로 쓰지 않으며 후속 동작·환경 목록 유지 |
| 구현 완료 / 기타 환경 확인 보류 | 가능한 관련 검사는 통과했으나 원제품·실제 solver·외부 host 등 해당 검증 환경이 없음 | 부족한 환경과 정확한 미확인 동작을 남기고 독립 구현 진행. 해당 동등성·실사용 합격으로 쓰지 않음 |
| 실패 또는 차단 | 지정 조건을 실제 실행했으나 실패하거나 필수 입력·계약이 아직 없음 | 같은 범위의 원인을 수정. 무관한 기능 추가로 우회하지 않음 |

검사를 무조건 한 번만 실행하라는 뜻이 아니다. **최종 후보에 지정 검사를 한 차례 수행 → 실패 수정 → 영향받은 검사만 재수행**한다. 저장 계약·공용 명령처럼 넓은 경계를 바꾸면 그 경계의 기존 회귀 묶음도 재수행한다. 통과 후 코드·입력·환경이 바뀌지 않았으면 반복 실행하거나 새 검사 목록을 늘리지 않는다. 품질 검토가 새 결함을 찾으면 수정·관련 재검사로 닫는다. 새 기능 취향이나 더 큰 모델은 다음 작업으로 보내되 기존 요구 누락·잘못된 합격·관련 변경 회귀를 새 요구로 돌리지 않는다. 원 지적자의 재확인까지 기록한다. 검증 횟수 제한을 이유로 실패를 무시하지 않는다.

증거에는 대상 SHA/dirty·환경·입력/출력/화면 해시·실제 조작·실패·지적별 종결을 남긴다. 재열 수 있는 보관처에 원본을 보존하고 ignored 임시 경로만 인계하지 않는다. 스킬 설치와 도구 실행, QTest와 OS 입력, offscreen과 전체 GPU 창, 과거 버전과 현재 버전을 구분한다.

환경이 없는 검사를 `skip`한 결과는 실제 실행의 증거가 아니다. 현재 CAD 검사에는 SDK/OCP 부재 skip이 있다. CAD 검증은 기존 CI처럼 SDK 초기화를 선행시키고 필요한 실제 사례가 수행됐는지 확인한다. 지금 가능한 Linux 실제 동작·렌더·파일 결과는 확인하며, Qt offscreen·가상 framebuffer·실제 OS 입력·VTK 렌더를 구분한다. Windows 검증은 일괄 후속 작업이고 현재 구현·리뷰·CI·병합·다음 단계의 선행 조건이 아니다. Linux 결과를 Windows 글자·아이콘·도킹·3D 품질 합격으로 대신하지 않는다.

**중간 보존과 병합:** 세션 중단에 대비해 실행 가능한 체크포인트마다 통합 담당이 커밋·PR을 만든다. PR에는 범위·실제 확인·미완료와 다음 작업을 남긴다. 사용자는 검토와 해당 CI가 통과하고 알려진 문제 없는 묶음의 병합을 승인했으므로 추가 확인 질문 없이 통합 담당이 병합하고 다음 구현을 이어 간다. 실패한 확인과 알려진 결함은 수정 후 재확인하며, 전체 G 완료나 Windows 검증을 기다리느라 중간 보존·검토된 코드 통합을 미루지 않는다.

## 4. P0 — 범위·입력·소유권·성능 기준의 유한 결정

**선행:** 현재 코드/문서와 제공된 참조 제품 비교. 구현을 시작하기 전 현재 테스트 경로와 작동 앱 한 번을 확인한다. 모든 후보 제품을 설치하는 것이 선행 조건은 아니다.

**작업:** 기존 공용 자산의 실제 소유 위치를 확인한다. G1의 같은 입력·T1/T2 작업·종료 상태를 HyperMesh·PrePoMax·Naksha·Abaqus/CAE·COMSOL·midas NFX·MIDAS MeshFree·BeidPrep 각각에 연결하고 명령 진입·선택·생성/할당·확정/취소·오류를 고정한다. 여러 제품의 좋은 부분을 합친 화면 하나로 대신하지 않는다. 카드/해석 의미가 다른 제품은 값·관계의 대응과 한계를 명시하며 지원 여부를 추정하지 않는다. 실제 접근 불가 항목은 원제품 비교 미확인으로 남기고 독립적인 공통 코어 구현은 진행한다. 세부 근거는 기존 ui-reference-variants 문서에 둔다.

**결정 기한:** 자산/의존성 결정은 최대 2개 집중 작업일, 입력/성능 예산 고정은 1개 집중 작업일을 기본 조사 한도로 삼는다. 이는 전체 구현 납기 약속이 아니라 조사를 종료할 시점이다. 종료 시 `채택한 버전/역할/소유 위치`, `대안으로 진행`, `필수 장애와 영향 작업` 중 하나를 남긴다. 결과 없이 조사 중 상태를 연장하지 않는다.

- 도킹: QDockWidget 기본. 고정된 Windows/PySide 조합에서 Qt ADS의 설치·배치 복원이 기한 내 통과할 때만 채택한다. 실패하면 QDockWidget으로 A 진행.
- 그래프/단위: 고정 버전 pyqtgraph/Pint를 필요한 장면에서만 비교한다. 최소 plot과 명시 단위 변환의 요구를 충족하는 한 경로를 고른다. 개발 branch/latest를 쫓지 않는다. 선택 도구 실패가 트리·세션 개발 전체를 막지 않도록 대체 구현 범위를 고정한다.
- CAD: C에서는 현재 Gmsh worker 경로를 사용한다. 전체 SMTK/SALOME/FEBioStudio 기반을 다시 선정하는 조사로 C를 대체하지 않는다. 그 대안의 실제 필요가 확인되면 P7c의 특정 기능별 비교로 보낸다.
- 공용 GUI 저장소: 기한 내 실물을 찾지 못했으면 `미확인`과 검색 범위만 기록한다. 확인된 코드만 채택하고 미확인 원본의 이전·fork·복제는 하지 않는다. 현재 Prep의 명확한 책임 추출과 새 자체 자산 개발은 진행한다. 나중에 원본을 찾으면 중복 범위를 좁혀 소유권을 정리한다.
- 라이선스: 외부 코드/아이콘의 채택과 배포 조건을 확인한다. 동일 사용자의 두 저장소 간 내부 소비 결정을 저장소 공개 라이선스 신설 문제와 혼합하지 않는다. 명시되지 않은 공개 재배포 허가를 있다고 보고하지 않는다.

**고정할 입력:** A용 실제 구조가 다른 다중 파트 RAD 2개와 기존 작은 보존 입력, 중립 곡선 2개. C용 열린 CAD surface와 다중 solid STEP 각각 한 개 및 구조가 다른 재수행 CAD 한 개. B용 혼합 beam/truss/shell/tet/hex 조립 2개와 100만 실제 요소/100 part/20 source 자료 생성기. 개인정보·제작사 바이너리를 넣지 않고 재배포 가능한 자료 또는 재현 생성기를 사용한다. C는 짧은 확인에 적합하도록 총 2만~10만 요소 범위를 고정하며 B를 대신하지 않는다.

**성능 예산 제안:** P0에서 실제 기준 장비의 사양과 정확한 자료를 고정한다. Windows 11 x64, RAM 32 GiB 이상, 로컬 SSD를 첫 기준군으로 잡고 아래 값을 초기 목표로 사용한다. 현재 G의 UI 기준은 DESIGN에 따른 1920×1080/100%, 3840×2160/200%와 축소 창 960×640이다. 필요하면 기존 150% 검사도 유지한다. 이는 시험 환경의 제안이며 사용자의 회사/개인 장비를 임의로 선택한다는 뜻이 아니다. 실제 사용할 장비의 CPU·GPU·RAM·디스크·OS와 dependency 버전은 P0에서 확인된 값으로 기록한다. 기존 구현이 느리다는 이유로 값을 자동 완화하지 않는다. 실측 장비가 다르면 P0 안에서 최종값을 한 번 확정한다.

| B 사용자 동작 | 제안 상한 | 측정 정의 |
|---|---:|---|
| 작업 문서 열기/재열기 | 각각 45 s | 명령 시작부터 표시·선택 가능까지, 초기 renderer 구성 포함 |
| 저장 | 60 s | 저장 요청부터 원자 교체 완료까지 |
| 최대 RSS | 앱 12 GiB / 동시에 살아 있는 앱+worker 합계 16 GiB | 문서+파생 캐시+저장 중 복사와 worker payload 포함. 개별 process peak의 단순 합이 아닌 같은 시점의 process-tree 합계 peak도 확인 |
| 이미 로드된 객체 선택/스칼라 변경·Undo | p95 150 ms / 각각 100 ms | 각 100개 고정 동작에서 사용자 입력부터 화면 반영까지; 저장은 제외 |
| part 숨김/표시 | p95 200 ms | 100개의 고정 part 동작. 전체 mesh 재생성 금지 |
| 취소 응답 | 1 s | UI가 취소 요청을 접수하고 상태 표시하기까지. worker 종료 별도 상한 5 s |

이 숫자는 현재 달성 결과가 아니다. 각 성능 확인은 최종 후보와 한 기준 환경에서 최대 3회로 고정한다(첫 실행 1회와 재실행 2회를 구분). 평균만으로 느린 실행을 숨기지 않고 각 실행의 열기/저장/메모리 상한과 고정 동작의 p95를 모두 확인한다. 이후는 실패 수정의 영향 항목만 재검사하며 새 장비·모델을 추가하는 성능 캠페인으로 확대하지 않는다. 예산 미정이면 P0의 B 착수 조건은 미완료다. 그 경우 A/C처럼 해당 예산을 요구하지 않는 작업은 계속할 수 있다. 측정이 불가능한 상황을 무기한 연구로 전환하지 않고 `B 플랫폼 기준 고정 보류`로 기록한다.

**산출물:** 기존 계획 내 짧은 scope/input/environment 표, 소유/명령 계약, 8방식의 같은 과업 장면·차이·미확인 목록, 선택 버전/대안, 필요한 capability·품질·성능 값. 장면 수를 두 개로 제한해 나머지 방식을 제외하지 않는다. 제품 코드 변경 없음.

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

**위 표와 제외는 2026-10-31 A 구현의 역사적 선택이다.** 현재 G1은 새 재료/단면 생성·할당을 포함하므로 새 카드 제외를 적용하지 않는다. 아래 P1 계약 검사는 유지할 최소 회귀이며 G1 종료에는 P6a/b의 원자 생성/삭제·관계 명령과 native writer를 함께 연결한다.

**선행/입력:** P0의 A 범위·입력, 현재 세션/문서/CLI. B의 장비 미확정과 무관하게 계약 작성 가능.

**작업/산출물:** `application/contracts.py`에 DocumentSession·property/tree/selection provider·Action/capability·structured error/event의 최소 자료형과 호출 예를 둔다. 기존 PrepSession의 RAD 구현을 그 계약에 연결하고 API 호환 경로를 유지한다. typed object/resource/native scope, mesh revision, 단위/좌표/field 성분을 표현한다. 모든 node가 6자유도라는 가정, 전역 native ID, Qt object를 정본으로 삼는 가정을 금지한다. 저장의 공용 컨테이너/codec 인터페이스, expected_revision, 초안 충돌, 최소 작업 상태·완료 상태와 이벤트 스레드 경계를 포함한다.

**지정 확인:** 기존 document/RAD/project/CLI 묶음과 새 `tests/test_application_contracts.py`를 실행한다. 같은 공개 계약으로 RAD의 지원 재료 필드와 비-RAD 곡선 scalar를 조회·수정·Undo한다. 잘못된 단위/참조/expected_revision에서 부분 변경이 없어야 한다. 공용 모듈은 RAD/Qt/VTK import 없이 load되어야 한다.

**종료:** 구현된 호출 예 2개가 실제 값·오류·Undo·개정을 공유하고 기존 CLI 보존 검사가 통과한다. 미래의 모든 물리 descriptor를 다 만들지 않고 계약 경계를 닫는다.

**P1 계약 작업의 경계:** 모든 schema 통합, assembly 편집, 열린 GUI IPC, 자동 단위 추정은 제외한다. 생성/삭제의 실제 transaction 구현은 P6a/b에서 맡으며 G1 밖으로 미루지 않는다.

## 6. P2 — 공용 자산·Action·편집 위젯과 부품 갤러리

**선행/입력:** P0의 목표 화면·토큰·상태 목록, P1의 provider/command 계약. P0에서 소유가 확인된 외부 자산만 사용.

**작업/산출물:** `ui/design`, `ui/widgets`, 공용 Action registry와 native gallery entrypoint. 아이콘 의미 키, 행/도구/트리/속성 밀도, 긴 이름/한글/지수/오류/hover/선택/비활성/포커스를 실제 위젯으로 제공한다. tree/table은 Qt model/view와 delegate, property는 그룹·단위·벡터·참조 입력, curve는 기본 table/plot이다. 숫자 초안과 확정 값, 표 붙여넣기 전체 검증, 한 편집 한 Undo를 연결한다. unsupported 도구를 활성 mock으로 채우지 않는다.

공용 위젯은 draft와 입력 이벤트만 소유한다. host adapter는 Prep 명령 또는 기존 Workbench Apply 서비스에 연결할 수 있으며 Prep Document/Dispatcher 생성을 강제하지 않는다. Undo 제공 여부와 의미는 host capability를 따른다. Prep 갤러리/RAD의 Undo와 Workbench MDO 설정의 Apply를 같은 이력으로 합치지 않는다.

**지정 확인:** 새 `tests/test_common_widgets.py`의 값 변경/오류/포커스/한 Undo 사례와 `caelab-prep gallery`를 실행한다. 후자는 현재 이미 있는 공개 명령이며 갤러리 실행 자체를 G1 완료로 세지 않는다. 실제 Windows에서 P0 상태 목록을 100/150/200%로 확인하고 잘림/정렬/읽기 문제를 수정한다. gallery 자체 값이 공용 위젯의 하드코딩 조건이 되면 실패다.

**종료:** 상태 목록과 입력 동작이 같은 공용 부품으로 충족되고 독립 검토자가 고정 화면의 정보 밀도·아이콘·가독성을 통과시킨다. 이후 모든 화면을 만들기 위해 P2를 계속 열어두지 않는다.

**경계:** 위젯은 solver 의미·문서 이력을 소유하지 않는다. 각 G의 8방식 UI를 P5와 함께 연결하며 두 번째 이후 방식을 제외하지 않는다. CAD 모델링 명령과 고급 곡선은 해당 G에서 구현한다.

## 7. P3/A — 첫 앱 연결의 기존 기준과 G1 확장

아래 A 작업/검사는 기존 값 편집·저장 기반의 회귀 범위다. 현재 G1 종료에는 사용자 2파트 이상에서 재료/단면 2개씩 생성·할당·교체·삭제 영향 처리와 8방식 작업이 추가로 필요하다. A1–A8 통과만으로 이 생성 흐름을 완료 처리하지 않는다.

**선행/입력:** P1/P2, A용 RAD 2개와 중립 재료/곡선 자료.

**작업/산출물:** 현재 main_window의 Action·트리·폼·도킹·초안/닫기/저장을 공용 셸과 RAD provider로 옮긴다. 공용 viewport frame에 VTK adapter를 앱 조립 지점에서 주입한다. 기계 전처리 공간과 재료/곡선 공간을 완성한다. 공용 atomic container 절차와 RAD/중립 curve codec을 제공한다. 현재 두 writer는 v2를 쓰고 각 v1 읽기를 유지한다. 최소 작업/취소/파일 오류 계약을 실제 UI에 연결한다. 기본 gallery/곡선 장면을 VTK 없이 실행할 설치 경로를 제공하고 기존 `.[gui]` 경로는 유지한다.

**지정 확인:** 기존 5개 코어/Qt 테스트와 새 계약/위젯/중립 codec 관련 검사. 실제 Windows에서 A1–A8의 고정 작업을 한 차례 연속 수행한다: 파일 열기 → 객체 선택 → 값 오류 → 수정 → Undo/Redo → 저장 → process 종료 → 새 process 재열기 → RAD export. 다른 제공자의 curve도 같은 공용 저장으로 재열고 RAD import가 없어야 한다. 잘못된 숫자, 외부 revision 변경, 저장 실패, 닫기 취소는 기존 값·초안을 보존한다.

**종료:** A1–A8 전부 통과하고 실제 Windows의 정보가 풍부한 두 작업 화면을 독립 검토한다. Windows 부재이면 `구현 완료 / Windows 확인 보류`이며 A 완료가 아니다. A를 통과한 뒤 B/C의 부족을 이유로 다시 A를 무한 수정하지 않는다.

**과거 A의 제외:** 새 RAD 카드 생성, CAD 채택, B 규모, 완전한 curve 앱/리본, 열린 GUI MCP였다. 현재 G1은 새 재료/단면 카드와 참조 생성을 포함한다. 나머지는 G2/G3 및 B/P8c의 명시 범위로 유지한다.

## 8. P4 — 독립 곡선 앱과 파일 재사용

**현재:** PR #17의 N15 구현은 RAD와 중립 앱에서 같은 CSV 파일 reader/writer, import 미리보기와 확정, export 및 덮어쓰기 취소를 제공한다. 표와 plot은 같은 초안을 사용하며, 점을 끄는 동안에는 미리보기만 바뀌고 놓을 때 한 명령/Undo로 확정한다. Escape는 취소한다. 두 곡선의 CSV·작업문서 왕복, 단위·참조 보존, RAD/VTK 없는 실행과 실제 Linux 파일 선택창을 검사했다. 최종 `323954f`의 CI 7개 job을 통과하고 main `8ff16c3`에 병합했다. Windows 및 원제품 비교는 별도 행에 남는다. **과거 보고 정정:** PR #15 당시의 CSV 완료 주장은 `paste_text` 검사를 실제 파일 입출력으로 잘못 보고한 것이며, 이번 구현의 근거로 소급하지 않는다.

**선행/입력:** P3/A의 계약·container, 축/단위가 알려진 서로 다른 curve 2개와 CSV.

**작업/산출물:** 독립 재료/curve 앱, table 행 추가·삭제·붙여넣기·graph drag·CSV import/export와 자체 작업문서. 알려진 단위 변환은 provider가 수행한다. drag 미리보기와 commit/취소를 분리한다. G2에서는 RAD FUNCT의 새 곡선/행 생성·삭제와 실제 조건/지원 재료법칙 참조를 adapter 명령으로 완성한다. 기존 점 편집 또는 중립 Associated curve만으로 완료 처리하지 않는다. 제공자별 물리 의미·단위 대응 없이 연결을 추정하지 않는다.

**지정 확인:** 새 `tests/test_curve_workflow.py`, VTK/RAD 없는 환경의 독립 앱에서 curve 편집 → Undo → 작업문서 save/reopen → CSV 왕복. CSV에 담기지 않는 단위·참조 metadata를 작업문서에서 보존한다.

**종료:** 두 curve의 값/축/단위/관계가 재열기에서 같고 한 gesture를 한 Undo로 되돌린다. 독립 앱은 P3의 복제 없는 소비자로 확인한다. G2는 여기에 실제 조건/지원 법칙의 참조와 native 보존, 8방식 T3/T4 과업을 함께 요구하며 독립 curve 앱만으로 완료되지 않는다.

**이번에 안 함:** 모든 재료 law, material database 서비스, 모든 CSV dialect, 해석 결과 후처리.

## 9. P5 — 8제품별 동일 과업의 표현·상호작용

**선행/입력:** 해당 G의 같은 문서·명령·저장 계약과 원제품별 과업 근거. G1-c에서 한 실제 UI의 명령 연결을 확인한 다음 G1-d에서 8방식으로 확대한다. 자료 확인은 그 전부터 병행할 수 있으나 명령 계약 확정 전에 각 방식의 별도 구현을 만들지 않는다. 8방식은 G1의 필수 범위이며 선택적 후속 레이아웃으로 미루지 않는다.

**작업/산출물:** HyperMesh·PrePoMax·Naksha·Abaqus/CAE·COMSOL·midas NFX·MIDAS MeshFree·BeidPrep 각각의 명령 그룹, 객체 선택/할당, dock/table/inline/modal 편집, 확정/취소·오류 복구를 adapter/composition으로 구현한다. 현재 adapter가 실제로 다른 확정 흐름을 제공하는 부분은 재사용하되 Material/Edit 하나에서 T1–T6 과업으로 확장한다. 도메인 값·관계 검증·Undo·파일 서비스는 공유한다. 레이아웃·초안·표현 상태만 프로필이 소유하고 독립 Document/명령 구현을 복제하지 않는다.

**지정 확인:** G1에서는 두 재료/단면의 생성·복사·수정·삭제 영향·파트 할당과 연속 저장 작업을 모든 방식에서 확인한다. 같은 오류·취소·외부 revision·Undo를 공용 계약과 실제 각 UI로 검증한다. 동일 유효 작업영역의 원제품/구현에서 작업 진입·정보 밀도·확정 조작·출력 값/관계를 비교한다. PSHELL/RAD shell 또는 MeshFree/FE 같은 의미 차이는 대응과 제한을 남기며 미확인을 임의로 동등/해당 없음 처리하지 않는다.

**종료:** 해당 G의 실제 과업과 UI 품질, 원제품 비교를 각 방식별로 판정하고 공통 코어의 동일 결과를 확인한다. stable dock ID·앱/프로필/layout-version 설정과 재시작 복원도 보존한다. 탭/이름/색 변경, adapter 수, 문서 정적 검사만으로 완료할 수 없다. 원제품 접근 불가는 비교 미확인이지 구현 전체의 정지 사유나 비교 통과가 아니다.

**이번에 안 함:** 원제품 전체 커널/solver/native schema 복제, 사용자별 임의 UI builder. 미지원 과업을 활성 mock으로 제공하지 않는다.

## 10. P6a — G1/G3에 필요한 최소 모델 자원·원자적 변경

**현재:** 단일 RAD 자원 안의 구조 변경과 후보 채택/Undo는 구현했다. 아래 목표의 독립 GeometryResource/MeshResource, 다중 자원 원자 변경·대형 배열 공유를 모두 완료한 것은 아니다. 남은 관계·배열 책임은 N16/N17에서 확인한다.

G1의 객체 생성/삭제·할당과 G2의 조건 관계에 필요한 작은 복합 명령부터 앞당겨 사용한다. 아래 메시 후보/배열 전체를 G1의 선행 조건으로 만들지 않는다.

**선행/입력:** P1 계약과 기존 P3의 공용 부품. G1의 새 화면 전체 완료를 코어 명령 구현의 선행 조건으로 삼지 않는다. G1은 파트/재료/단면 입력을 사용하고, G3 채택 확장에는 C용 tri/tet 후보·native 번호가 겹치는 두 source·기존 RAD 보존 입력을 쓴다.

**작업/산출물:** GeometryResource/MeshResource·component·unit/coordinate context와 typed ID, source/native ID scope, compact coordinate/connectivity/offset/type 배열, reverse reference index의 최소 구현. 자원 추가/교체/삭제와 관련 component/assignment를 한 명령으로 commit/Undo한다. 큰 불변 배열은 history entry가 공유하고 작은 편집마다 전체 snapshot을 만들지 않는다. 각 rendering/pick/worker 결과는 document/resource revision에 귀속한다. 공용 container에 mesh payload codec을 추가하고 RAD v1 reader를 유지한다. 생성되는 native 객체에는 source/namespace를 고려한 충돌 없는 ID 할당 정책과 저장·재열기 후 유지되는 ID를 제공한다. UUID/정수 ID를 매번 같은 값으로 재생성하는 deterministic 정책까지 강제하지 않는다.

**지정 확인:** 새 `tests/test_model_resources.py`, `tests/test_resource_transactions.py`와 기존 document/project roundtrip. prepared 후보 하나를 채택·Undo·Redo·저장·재열기한다. 중간 실패를 한 지점 주입해 자원/관계가 모두 이전 상태인지 확인한다. stale pick/result는 거절되고 독립 source의 같은 native 번호가 충돌하지 않아야 한다. compact 배열 ownership과 scalar 수정의 재복사 여부를 계측한다.

**종료:** C가 실제 후보를 문서 정본으로 안전하게 채택할 최소 경로가 동작한다. 최소 참조·값·저장·실패가 닫히면 P6a 완료이며 B 완료는 아니다.

**이번에 안 함:** 모든 assembly/instance 편집, 혼합 DOF 조건 생성 전체, 100만 요소 최종 예산, CAD topology 자동 대응 복구.

## 11. P7a/C — 첫 CAD→메시→문서→native 경로

**현재:** tri3/tet4 후보·품질·국부 size·제한된 conformal/independent 경계·채택·참조 없는 교체·Starter/Engine은 연결됐다. 실제 solver 세 입력은 62/236/310 요소의 소형 사례다. 아래 2만–10만 요소 입력·120초 예산 및 대표 사용자 모델의 연속 native 작업은 이 소형 결과로 통과시키지 않으며 N11에서 확인한다. 외부 독립 메시 import는 N02다.

아래 C는 Starter 읽기까지의 기술 하위 단계다. **현재 G3는 C에 G1/G2 조건·새 Engine/INCLUDE 생성과 실제 선택 solver의 입력 검사·짧은 실행을 더한 목표**다. C의 Engine 제외는 G3에 적용하지 않으며 C만 통과해 G3 완료라고 쓰지 않는다. tri/tet 지원·품질·세 입력 기준은 유지한다.

**선행/입력:** P6a, 기존 worker, C의 고정 CAD/단위/메시 크기/element 범위, 고정 OpenCourant Starter 버전. C는 열린 CAD surface의 tri3 shell과 closed solid의 tet4를 구별한다.

기존 uniform tri/tet의 재현 근거는 재사용한다. 새 face/volume local sizing과 conformal/independent interface는 [F1/F2](mesher-feasibility-roadmap.md)를 통과한 recipe만 제품에 연결한다. 준비된 mesh를 다루는 P6a와 공용 GUI/문서 기반은 이 실증과 병행할 수 있다. 해당 새 동작이 미실증이면 C 전체 완료로 세지 않는다.

**작업/산출물:**

1. GUI에서 CAD import와 dimension/전역 mesh-size/명시 길이단위를 선택하고 Gmsh worker로 후보를 생성한다. C에서 선택한 face/volume에 국소 size를 지정하는 최소 조절도 추가한다. 초기 worker의 uniform min/max에서 확장한 기능이며, geometry UUID에 속하는 meshing recipe로 저장하고 preview·재생성에 반영한다. edge UUID/1D seed와 자동 adaptive sizing은 후속이다. XAO/MSH/metadata를 한 candidate 묶음으로 다룬다. 후보 생성은 문서 변경이 아니다.
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

**현재:** G1/G2의 지원 카드 관계는 연결됐으나 아래 B 혼합 조립·자원 간 의미 관계는 미완료(N16)다. 기본 케이스/해석 설정은 N01에서 구현하고 N16은 그 재사용·복합 관계를 검증한다.

G1에는 재료/단면 생성·복사·삭제 영향·파트 할당을, G2에는 집합·조건·곡선의 최소 실제 관계를 먼저 연결한다. 아래 혼합 조립 B 전체 완료를 이 두 작업의 선행 조건으로 삼지 않는다.

**선행/입력:** P6a와 B의 혼합 조립 자료 2개. P7a/C는 권장 선행이지만 실제 B 의미 구현의 기술적 필수는 아니다.

**작업/산출물:** 기존 B 범위의 assembly/FE component·source, 공유 mesh와 독립 동일 ID, 정적 Cartesian 좌표, explicit node/element/surface sets, material/property assignment, 조건 정의와 case 활성, contact의 두 영역, curve/connection 참조. field/formulation provider로 대상별 활성 성분을 계산하고 native 1–6을 공용 자유도 정의로 쓰지 않는다. create/edit/delete/reassign을 atomic 명령으로 제공하고 reverse references로 영향 범위를 찾는다. 반복 instance는 기존 B 선언대로 표현/조회/저장만 보장한다.

**지정 확인:** 새 `tests/test_model_relations.py`, `tests/test_condition_fields.py`, `tests/test_model_roundtrip.py`; B1–B4와 B6의 의미/파일 작업. shared node와 별도 source의 동일 번호, part 이름 중복, shell/solid/beam 접점, 서로 다른 case의 같은 조건, 좌표계 지정, dangling/stale relation을 확인한다. 준비된 replacement mesh로 stale set/contact/pick을 검출하고 임의 ID 재사용을 하지 않는다. 명시한 RAD native 지원 범위만 export/Starter 읽기로 확인한다.

**종료:** B1–B4·B6 의미 조건이 통과하면 P6b 완료. B5 성능이 남으면 B 완료가 아니다. 표현 가능한 일반 scalar field를 thermal/CFD solver 지원이라고 보고하지 않는다.

**이번에 안 함:** 모든 해석 physics/과구속 수치 판정, 반복 instance placement/native expansion, 자동 CAD remap, 고급 solver contact 전체.

## 13. P6c/B — 배열·지연 UI·저장과 규모 예산

**현재:** 미완료(N17). 현재 소형 RAD/메시 검사와 렌더 결과는 아래 100만 요소·100 part·20 source의 예산 충족 근거가 아니다.

**선행/입력:** P6b, P0에서 확정한 B 장비/정확한 generator/예산. 이 단계부터 input 규모·budget을 구현 통과 목적으로 완화하지 않는다.

**작업/산출물:** indexed lookup, lazy tree/table, versioned projection cache, 부분 invalidation과 typed payload codec. 문서·VTK·worker·저장 간 사본의 소유자/수명/해제를 정한다. Gmsh worker의 전체 JSON arrays 중복을 large-mesh 경로에서 binary payload + metadata로 이행하되 현재 작은 후보 API의 호환성 정책을 둔다. compressed ZIP의 직접 mmap을 가정하지 않고 독립 binary chunk 또는 관리되는 불변 파일 중 한 경로를 고른다. HDF5/Zarr/mmap을 모두 도입하지 않는다.

**지정 확인:** 기존 B 의미/roundtrip 검사, 새 `tests/test_large_model_behavior.py`의 제한된 invalidation/취소/참조 검증, `python tools/benchmark_model.py --profile b-reference`의 고정 100만 실제 요소 시나리오. 이 benchmark 파일/프로필은 이 단계의 새 산출물이다. actor만 복제해서 요소 수를 채우지 않는다. 같은 최종 후보에서 열기/재열기/저장/peak RSS와 고정 100회 selection/edit/hide를 측정한다. P0의 최대 3회 실행 원칙을 따르고 cold/warm 결과를 구분한다. 실패한 지표 원인을 수정한 뒤 관련 시나리오만 재측정한다.

**종료:** B1–B6와 고정 budget이 모두 통과하면 B 완료. 느린 수치가 측정됐다는 사실만으로 통과하지 않는다. 작성자 외 검토자는 저장 후 재열린 관계·native 결과·실제 모델 조작을 확인한다.

**이번에 안 함:** 더 큰 임의 모델, 모든 GPU/원격 파일시스템, 모든 배열 저장 backend, 계산 자유도 숫자 추정.

## 14. P7b — 일반 mesh 변경과 재메시 재연결

**현재:** N18 미완료다. 참조 없는 소유 메시를 안전하게 교체하는 현재 기능은 아래 여섯 일반 수정과 조건/집합 재연결을 대체하지 않는다.

**선행/입력:** 전체 P7b에는 P6b와 C의 자원·관계·native 경계를 모두 사용한다. 순수 메시 수정 일부는 먼저 착수할 수 있으나, 조건 재연결까지 포함한 P7b 완료와 구분한다. part 경계·shared nodes·sets/conditions가 있는 고정 mesh 2개와 이전/교체 CAD 한 쌍을 사용한다.

**고정 첫 범위:** node 좌표 이동, 선택 node의 명시 tolerance merge, element 삭제와 고립 node 처리, shell normal 반전, part/집합 재배정, size 변경에 의한 재메시. 합치면 안 되는 component/접촉면의 node는 자동 병합하지 않는다. edge split/swap, quad/tri 변환, 고차 승격 등은 다음 소묶음으로 명시한다.

**작업/산출물:** 각 operation의 적용 가능 조건·영향 preview·품질 변화·참조 변화·atomic commit/Undo. 새 mesh revision에서 geometry 기반 named region은 실제 backend 대응이 있을 때만 재평가한다. explicit sets는 stale로 표시하고 사용자가 확인하는 재연결 명령을 제공한다. 동일 번호/최근접 좌표만으로 하중·접촉을 조용히 이동하지 않는다.

**지정 확인:** 새 `tests/test_mesh_operations.py`, `tests/test_remesh_relations.py`; 지정 operation 각각에서 품질 전후·참조·Undo·save/reopen·지원 native export를 확인한다. 다른 source의 같은 ID, 공유 경계 merge, 표면 방향에 의존하는 조건을 포함한다.

**종료:** 고정한 6개 operation과 재연결 정책이 실제 두 자료에서 통과한다. 자동 복구 불가 영역이 명확히 stale로 남고 export의 차단/명시 제외 정책이 작동하면 자동 완전 복구를 기다리지 않는다. 단, 유효하지 않은 하중을 정상으로 출력하면 실패다.

**이번에 안 함:** 임의 mesh 수술 전체, 모든 CAD topology 변경 추적, 모든 손상 geometry 치유.

## 15. P7c — 실증 후 착수할 메시 확장과 별도 연구

**현재:** N22–N26의 조건부 다섯 항목이다. 아래 요구를 삭제하지 않되 F0–F2가 통과하지 않은 기능의 제품 구현 가능성·납기를 확약하지 않는다.

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

**현재:** 파일/CAD worker 상태·실제 취소와 지원 작업의 공용 API/독립 CLI는 연결했다. 열린 GUI IPC(N19)와 실제 MCP 클라이언트(N20)는 실제 Linux 창 및 정확한 SHA의 CI를 통과해 PR #21에서 병합했으며 아래 N 행에서 범위를 판정한다. 실제 Workbench W1/W2 연결과 RAD 계산 W3(N21)도 구분한다.

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

**현재:** Python wheel의 새 환경 설치/CLI CI는 통과했다. Windows 실행 묶음과 깨끗한 사용자 환경의 GUI 설치·이동·제거 검증은 미완료(N13)이며 현재 버전 GUI/Workbench 실제 입력은 N12/N14다.

**선행/입력:** 배포할 기능 묶음과 의존 버전을 고정한다. 패키징 준비는 진행할 수 있으며 Windows 실측은 사용자 지시대로 일괄 후속 검증한다. 납품 판정에는 해당 Windows 결과가 필요하다.

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

위 명령은 기본 경계 검사이며 전체 구현 확인 명령이 아니다. 현재 CI의 환경·실행 목록은 [prep-tests.yml](../.github/workflows/prep-tests.yml)을 따른다. 실제 검사와 초기 계획 이름의 대응은 다음과 같다.

| 현재 책임 | 실제 검사 파일 | 범위의 한계 |
|---|---|---|
| 생성·할당·원문·관계 | `test_modeling_commands.py`, `test_modeling_workflow.py`, `test_radioss_modeling.py`, `test_radioss_defaults.py` | 모든 B 다중 자원 관계 아님 |
| 조건·집합·단위·8방식 | `test_condition_workflow.py`, `test_conditions_ui.py`, `test_groups_ui.py`, `test_native_units_ui.py`, `test_modeling_ui.py` | 케이스/독립 메시와 원제품 비교를 증명하지 않음 |
| 후보 품질·채택·native 생성 | `test_gmsh_adapter.py`, `test_mesh_candidates.py`, `test_mesh_adoption.py`, `test_mesh_workflow_ui.py`, `test_solver_generation.py` | 소형 지원 tri/tet·명시 조건에 한정 |
| 8방식 구성·실제 렌더 | `test_reference_adapters.py`, `test_program_comparison.py`, `test_native_render.py` | offscreen과 opt-in X11 실제 렌더/pick을 구별; Windows/원제품 아님 |

앞 절의 `test_candidate_adoption.py`, `test_mesh_quality.py`, `test_radioss_generation.py`는 초기 제안 이름이며 해당 책임은 위 실제 파일에 구현했다. `test_curve_workflow.py`, `test_layout_profiles.py`, `test_model_resources.py`, `test_resource_transactions.py`, `test_model_relations.py`, `test_condition_fields.py`, `test_model_roundtrip.py`, `test_large_model_behavior.py`, `test_mesh_operations.py`, `test_remesh_relations.py`, `tools/benchmark_model.py`는 현재 없는 계획 이름이다. 파일명 신설 자체는 완료 조건이 아니며 기존 검사가 같은 동작을 다루면 그 경로를 확장한다.

<a id="current-progress"></a>

## 19. 문서와 작업 상태의 관리

<a id="remaining-work"></a>

### 현재 남은 작업 — 새 세션은 이 표부터 확인

**최초 검토 기준:** Prep main `a1eba527132bf45b9f66365f8bfefbc9c1ecf398` / [문서 PR #16](https://github.com/pikachu444/caelab-prep/pull/16), 제품 코드는 [PR #15](https://github.com/pikachu444/caelab-prep/pull/15)와 동일, Workbench main `d6f05a3b1abc0cb9e83e7e96311f743e626ab086` / [PR #54](https://github.com/pikachu444/caelab-workbench/pull/54). 두 PR은 병합됐지만 G0–G4 전체 납품은 끝나지 않았다. 문서 정리는 제품 기능 완료가 아니다. Prep PR #17은 최종 `323954f`의 CI 7개 job 통과 후 main `8ff16c3`에 병합했다. [WB PR #55](https://github.com/pikachu444/caelab-workbench/pull/55)는 최종 `a328253`의 4개 CI job이 모두 통과한 뒤 `865ee15`에 병합했다.

**전체 추적 26개 = 현재 납품 목표 15개(N01–N15) + 보존한 기존 구현 요구 6개(N16–N21) + 조건부 실증·연결 5개. 현재 미완료는 19개다.** 이는 각각 닫을 수 있는 작업 묶음의 수이며 같은 크기·예상 일수·완료율이 아니다. 한 행에서 결함 수정이 필요하면 그 행에 포함한다. 기존 P/B/G 번호를 다시 더하지 않는다. N15의 CSV 누락은 G2/T3에도 속하므로 현재 목표로 재분류했다. 총 26개는 그대로다. 이 중 N01·N02·N15의 명시한 구현 범위는 PR #17에서 Linux 검사·독립 리뷰·최종 CI를 통과해 병합했다. N21은 WB PR #55에서 지원 경로를 병합했다. N19/N20도 PR #21에서 실제 GUI·공개 MCP client 및 최종 CI를 통과해 병합했다. N16의 명시 B1–B4/B6 범위도 PR #20에서 병합했다. 구현 범위를 닫은 행은 7개, 미완료는 19개다. 병합한 일곱 행의 Windows·원제품·대표 규모 검증은 해당 별도 행에서 계속 관리한다. N16–N21도 기존 미완료 요구이며 선택적으로 버릴 추가 기능이 아니다. N22–N26의 no-go는 실증 판정이지 기능 완료가 아니다.

| ID | 작업 / 기존 요구 | 구현 결과 | 실제 검증 / 확인 작업 | 완료 기준·외부 조건·대안 |
|---|---|---|---|---|
| N01 | 케이스·영속 해석 설정 / G2 T4 | **지원 범위 구현·병합.** PR17의 제품 코드는 `0aaada4`, 최종 검증은 `323954f`, 병합 main은 `8ff16c3`이다. `analysis_cases.py`/session/공용 dialog의 영속 UUID·명시 조건 활성 집합·단위 있는 시간/출력 설정, v3 저장(v1/v2 읽기). | `test_analysis_cases*`, CLI 새 프로세스, 8방식 진입, 실제 X11 10검사와 두 케이스 Starter/Engine의 다른 시간·운동량/에너지 확인. 파일 선택 중 변경·삭제된 케이스 거부도 재검사. | 정확한 최종 SHA의 CI와 독립 리뷰를 통과해 해당 지원 family의 구현을 병합했다. N11 규모·N12 Windows·N03–10 원제품은 별도. 미지원 물리 조건은 fail closed하며 지원 확대를 예제로 대체하지 않음. |
| N02 | 외부 독립 메시 import / G3 T5 | **지원 범위 구현·병합.** PR17의 제품 코드는 `0aaada4`, 최종 검증은 `323954f`, 병합 main은 `8ff16c3`이다. CAD와 독립 출처 validator, real MSH+manifest와 hash/명시 단위/CAD identity 없음. 기존 SDK inventory를 검증한 뒤 공통 NativeMesh·품질·채택·Undo·저장·출력으로 연결한다. | core/SDK/8 UI 51, 기존 CAD52, 실제 X11 2, 실제 솔버2 검사. 사용자 독립 실험의 동등 fixture로 비연속 ID와 quad 원본 inventory 보존·채택 차단을 재현(원본 scratch 파일 직접검사 아님). overlap 집합/무그룹 part/하위 경계 node-set 보존. | 첫 지원 MSH2.2/4.1 ASCII tri3/tet4. [cad] Gmsh4.15.2·libGLU 필요. 단위 불명/불일치·지원 안 되는 family/binary 등은 전체 거부. 최종 CI를 통과한 첫 형식을 병합했다. 후속 family는 N22–N26에서 관리하며 가짜 XAO나 느슨한 CAD 검증으로 우회하지 않는다. |
| N03 | HyperMesh 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 2026-11-02 공식 trial/학생 자격 경로와 2026 Linux 지원 환경을 확인했으나 사용권·설치본이 없다. 사용자 2024.1·참고 장면 2025/2025.1·현재 배포 안내 2026을 구분해 같은 T1–T6를 고정한다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N04 | PrePoMax 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** GPLv3 공개 ZIP에 유료 사용권 장벽은 없지만 Windows/.NET4.8 또는 Wine 실행이 필요하며 현재 Wine도 없다. 2.5.0 기준판과 2.6.0/3.0 RC2를 구분한다. 실제 생성·할당·취소를 수행하며 library/contour 그림으로 대체하지 않는다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N05 | Naksha 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 무료 Windows/Linux 데스크톱 제품이다. 공식 무료판 버튼이 이름·업무 이메일 신청 폼으로 이동함을 확인했고 제출하지 않았다. 설치본/실행 build를 받은 뒤 비교한다. 빈 Details 그림으로 확정 시점·취소를 추정하지 않는다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N06 | Abaqus/CAE 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 정식 사용권/설치본이 없고 무료 LE2026도 Windows·1000노드·개인교육용 제한이 있다. 허용된 사용 경로를 정한 뒤 Property→재료→단면→할당·단위·오류/취소와 RAD 물리 의미를 대조한다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N07 | COMSOL 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 6.4는 현재 Ubuntu24.04를 지원하지만 Access에 연결된 구독 또는 발급된 trial/설치본이 없다. 6.3 참고판과 구분해 비교한다. RAD 출력·계산을 COMSOL Build/Compute로 세거나 Runtime 앱으로 Model Builder 편집을 대체하지 않는다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N08 | midas NFX 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 공식 2026R1 설치/Windows 경로와 현재 14일 trial 발급 절차를 확인했다. 실행 환경·사용권은 미확보, 신청은 미제출이다. 같은 한 버전의 연속 작업으로 대조하며 교육자료를 이어 붙이지 않는다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N09 | MIDAS MeshFree 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 공식 2026R1 Windows 설치와 현재 14일 trial 경로는 있으나 환경·사용권이 없다. 형상/영역·재료·단위·이산화·조건·케이스의 물리 계약과 FE 작업의 대체 흐름을 정해 실제 수행한다. 비대응을 임의 N/A로 닫지 않는다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N10 | BeidPrep 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **전체 작업 실행 미확인.** 2.0 beta 공식 페이지는 Windows·계정 없는 무료 다운로드를 제공한다. 실제 클릭은 다운로드 경로를 반환했지만 파일 수신/해시는 확인되지 않았고 Windows도 없다. 과거 1.0.1 소형 실행과 2.0 웹 소개를 구별하고 card 확정을 선택 APPLY에서 추정하지 않는다. [접근 근거](ui-reference-variants.md#product-access). | 동일 T1–T6 입력/물리객체/상태/출력 계약·버전별 조작을 [제품별 확인표](ui-reference-variants.md#product-access)로 고정. 생성/할당/다중선택/확정·Undo/오류·취소 실제 실행 필요. | 해당 행의 설치본·실행환경/사용권 확보 후 원제품과 Prep의 연속 작업·파일·전체화면을 대조하고 UI차이 수정. 자료 사진/화면 재배치로 통과시키지 않으며 독립 코어 개발은 계속. |
| N11 | 대표 사용자 모델의 연속 native 작업 / G1–G3 | **대표 조립의 정상 native 종료 확인, 전체 과업 근거 대조는 진행 중.** PR #22에서 16,645 node 집합의 입력 잘림을 수정했고, PR #25 `30578cdb`를 main `3ceaf44`에 병합했다. 실제 GUI의 생성·할당·조건·후보·저장·새 프로세스 재열기·출력과 같은 의미의 공개 CAD 입력을 독립 Ubuntu에서 재현했다. | 64,308 tet / 16,645 node / 18 part. [CI 41372762449](https://github.com/pikachu444/caelab-prep/actions/runs/41372762449) 9 jobs 통과. exact와 관측 Engine 모두 정상 종료, Starter 오류·경고 0. native 5.546초/120초, 준비 18.719초 별도. 독립 입력/로그/40개 파일 해시 및 질량·운동량 1.43e-8, 에너지 2.83e-7 상대오차 확인. [실제 산출물](https://github.com/pikachu444/caelab-prep/actions/runs/41372762449/artifacts/13110221948). | 로컬 종료 오류 원인은 아직 미확정이며 해당 실패를 보존한다. N11 전체를 닫기 전에 서로 다른 두 사용자 흐름과 C의 2만–10만 요소·국부 size·공유/독립 경계 근거를 정확 입력별로 대조하고 빠진 실행을 완료한다. 이 병진 검증을 접촉/응력/수렴·상용 동등성·Windows로 확대하지 않는다. |
| N12 | Windows GUI 실측 / R4·G1–G4 | **Windows 실제 GUI 후속.** PR #24 `a9e9e8af` 준비 러너는 main `89bd700`에 병합했다. CLI/pytest와 실제 과업 coverage를 분리하며 실제 GUI 항목은 unexecuted다. 현재 Linux/X11 결과와 과거 A7은 대체 증거가 아님. | 동일 최종 SHA에서 입력/한글IME/DPI100·150·200%/작은창/도킹재시작/GPU/T1–6를 실제Windows창으로 수행. | 접근 가능한 Windows desktop·GPU·입력/캡처 필요. 사용자 후속 지시 유지; 패키지와 재현 절차는 먼저 준비하며 Linux 구현은 계속한다. |
| N13 | Windows 배포 묶음·새 설치 / G4·P9 | **배포 준비/Windows 납품 미완료.** wheel 깨끗한 venv 성공은 설치형 납품이 아님. | 배포 형식 하나·Python/Qt/VTK/SDK 버전·고지를 고정하고 깨끗한 Windows 설치→파일작업→재시작→제거/이동 검사를 연결한다. | Windows 최종환경 필요. 우선 portable 후보의 실제 의존/라이선스 묶음을 점검하고 재배포권 미확정 바이너리는 외부설치 연결로 분리; 권리 선택이 필요하면 해당 바이너리별 선택만 요청. |
| N14 | Windows 실제 Workbench W1/W2 / G4 | **Windows W1/W2 후속.** 실제 Workbench NumericEdit와 독립Prep 파일전달 구현은 있음. | 호환 Prep/WB SHA 쌍을 고정해 host 값/이력 소유, 오류복원·손상파일·재시작·한글/공백경로와 독립 문서 전달 확인. | 동일Windows납품환경 필요. Linux 교차앱 회귀/파일 검사는 계속, W1/W2를 N21 W3 계산 완료로 합산하지 않음. |
| N15 | RAD·중립 CSV와 곡선 앱 완성 / G2 T3·P4 | **지원 범위 구현·병합.** PR17의 제품 코드는 `0aaada4`, 최종 검증은 `323954f`, 병합 main은 `8ff16c3`이다. 중립 curve_csv와 같은 표/plot 초안, 파일preview/import/export, drag release 한 Undo/Escape 취소. | 실제 X11 24검사: 두 host/8표현, 파일 chooser/overwrite취소, 2곡선 CSV+작업문서 왕복·RAD/VTK 없는 프로세스. HyperMesh/Naksha plot 잘림을 수정 후 실제 화면 재확인. | 정확한 최종 SHA의 CI를 통과해 구현을 병합했다. CSV는 두수치열/선택x,y헤더, 단위와 참조는 문서가 소유하며 자동 환산하지 않는다. 전문 GUI 전체 품질/원제품/Windows는 별도 행. |
| N16 | 혼합 조립·다중 자원 관계 / P6b·B1–B4/B6 | **명시 범위 구현·병합.** PR #20 최종 `1cf604e`, main `a9e5cf0`. 다중 자원 단일 publish/Undo, source archive·명시 ID mapping, mixed DOF/좌표계, prepared 교체·stale 재연결, 참조 instance와 v5(v1–v4 읽기)를 실제 GUI에 연결했다. | [최종 CI 41374423889](https://github.com/pikachu444/caelab-prep/actions/runs/41374423889) 9 jobs 통과. 실제 X11 97 passed, Qt 283 passed/2 skipped, 실제 solver 8 passed는 서로 별도 실행이며 합산하지 않는다. 비작성자 검토·실제 두 mixed native·실패 원자 복원 근거를 확인했다. 초기 CI의 테스트 소유권/표현 혼동을 실제 Qt 수명·physical cell 출처 단언으로 고쳤다. | instance는 표현/조회/생성·삭제/저장이고 placement/geometry 복제는 아니며 미전개 instance는 native 출력 차단. N17 성능·일반 접합 동역학·N18 여섯 수정으로 확대하지 않는다. 공통 코어의 다음 편집자는 인수 측 한 명으로 지정한다. |
| N17 | 대용량 배열·지연 UI·저장 / P6c·B5 | **동일 100만 요소 baseline/개선 측정 완료, 고정 성능 목표 미달.** 100 part·20 source를 유지했다. 측정 snapshot과 실제 p95는 보존하며 immutable projection·owned payload·PART context 개선은 PR #20에 병합했다. [PR #26](https://github.com/pikachu444/caelab-prep/pull/26)에 고정 입력 생성기·측정 harness·원자료·당시 source ZIP을 보존한다. | mesh_view의 전체 buffer 공유를 확인해 4.5/5.1초가 36/22µs로 줄었다. 실제 Qt 선택 p95 773ms, 값 변경 126ms, Undo 130ms, 숨김/표시 724/750ms로 예산을 넘는다. RSS는 3.891→3.424GiB지만 열기/재열기는 21.1/22.1초로 느려졌다. | Linux 8GiB/소프트웨어 렌더 환경을 기록하고 남은 UI refresh·렌더·초기 index 비용을 분리해 개선한다. 요소 수나 기존 4절의 예산을 낮추지 않는다. 후속 8회 진단 평균 scalar/Undo 약73ms와 선택598ms는 p95 합격이 아니다. 동일100회 실제 프레임 기준으로 남은 선택/가시성·초기화 비용을 개선해야 한다. Windows/GPU·취소는 미확인이다. |
| N18 | 일반 메시 수정·조건 재연결 / P7b | **구현 진행, N16 transaction 연결 예정.** PR #28 `f7da857`에 typed source/revision을 보존하는 순수 후보와 두 입력의 15개 검사·실패 근거를 보존했다. 세션·sparse native codec·GUI·native·CAD 재메시는 미연결이다. N16의 prepared 교체만으로 여섯 일반 수정이 완료된 것은 아니다. | 14절의 여섯 작업을 각각 두 입력에서 영향 미리보기→품질·참조 검사→원자 적용→Undo·저장·native 출력으로 확인한다. explicit set과 geometry region을 구분하고 source/revision별 ID를 검사한다. | 복구하지 못한 관계는 stale 상태로 저장하고 출력을 차단한다. 최근접 좌표나 같은 번호로 하중을 자동 이동하지 않는다. 명시 대응표와 사용자 재선택을 대안으로 제공하되 재연결 완료로 세지 않는다. |
| N19 | 열린 GUI IPC / P8c-IPC | **PR #21 `f9a3d55` 구현·실제 검사·최종 CI 통과 후 `df277a8`에 병합.** live transport를 Qt 주 스레드의 소유 Session에 연결하고 doc/epoch/revision/request_id, token, CAS, draft/busy 충돌과 replay를 검사한다. | 실제 X11 창에 별도 CLI로 연결해 수정·Undo·저장·재연결과 Gmsh 작업 취소를 검사했다. 독립 리뷰에서 GUI 후보 재생성 후 이전 job 상태가 남는 결함을 찾아 수정했으며, 원 검토자가 후속 Generate/Open/Adopt와 Stop 대기를 재확인했다. | 독립 집중 검사 57건을 통과한 소스의 [CI 41370219716](https://github.com/pikachu444/caelab-prep/actions/runs/41370219716) 8개 job을 확인했다. 실제 X11/SDK/MCP job은 teardown을 포함해 60 passed다. 문서 사본이나 새 CLI 세션을 live 제어로 대체하지 않는다. 이 IPC는 Android ChatGPT의 새 세션 생성 기능이 아니다. |
| N20 | 실제 MCP 클라이언트 연결 / P8c-MCP | **PR #21 `f9a3d55`의 실제 client 및 최종 CI 통과 후 병합.** N19에서 검증한 명령을 얇은 adapter로 노출한다. | 공개 MCP CLI @apify/mcpc 0.7.0을 설치했으나 이 환경의 Unix socket EPERM 때문에 handshake 전에 막혔다. 공개 FastMCP CLI 3.4.11로 수정·저장·실제 worker 취소·화면 반영과 오류 3개 과업을 확인했다. 서버 SDK 2.3.0은 별도 환경이며 LLM 키가 필요 없는 실제 stdio client 호출이다. | N19의 검증된 API를 사용한다. mock·Inspector·도구 등록만으로 닫지 않으며 클라이언트를 변조해 성공으로 만들지 않는다. 실제 CLI 상호운용과 자연어 LLM agent 검증을 구분한다. 종료 시 descriptor 부재 검사는 통과했으나 후속 실행에서 비활성 파일이 다시 관찰된 원인은 미확인이다. [관찰 기록](automation/2026-11-02/cleanup-observations.json)은 원인 미확인으로 유지한다. 원격 CI에서는 종료·worker/descriptor 부재 단언을 통과했으며 공개 [산출물](https://github.com/pikachu444/caelab-prep/actions/runs/41370219716/artifacts/13108818638)의 capability 제거를 확인했다. Linux 구현 범위의 병합이며 원인 규명·Windows ACL·자연어 LLM 검증 완료로 확대하지 않는다. |
| N21 | Workbench RAD 실행 입력·계산 / W3 | **지원 경로 구현·병합.** WB PR #55 최종 `a328253`, main `865ee15`. RAD basename·상대 INCLUDE·Starter/Engine의 불변 snapshot과 두 단계 실행·실패·취소·재실행을 기존 JobManager가 소유한다. | 비작성자 검토와 수정 재확인, [CI 41368317991](https://github.com/pikachu444/caelab-workbench/actions/runs/41368317991)의 공식 solver 두 입력 서비스/X11 GUI·전체 Python 3.11/3.12·실제 CalculiX가 모두 통과했다. 로컬 shell ERROR760 기록은 해당 환경의 실패로 보존한다. | binary reader의 partial 상태를 유지하고 Prep에 두 번째 실행 관리자를 만들지 않는다. 이 지원 경로의 구현을 닫되 Windows 후속·전체 물리 정확성·완전한 native animation 판독을 완료로 확대하지 않는다. |
| N22 | 선/beam/truss·준비 shell면 / P7c-S | **명시 선/짧은 원호의 고정 F2 통과, 제품 미연결.** PR #23의 [영향 입력 재검증](mesher-evidence/2026-11-02/structured/F2-OCC-addendum.md)에서 같은 입력·공차를 유지하고 OCC 원호 경로로 세 실패를 해결했다. 다섯 지원 입력·한 거부 입력의 최종 근거를 확보했다. CAD curve/frame과 준비 shell면, 단면·orientation/native 연결은 별도 남는다. | line/beam/truss와 준비 shell의 family·단면·orientation·node order·두께/offset 계약을 고정한다. F0–F2 실증 후 공통 채택·Undo·저장·실제 reader로 연결한다. line의 품질 근거로 SICN을 사용하지 않는다. | 자동 중립면을 기다리지 않는다. 공식 Gmsh/OCP와 고정 solver를 사용한다. 미지원 formulation은 거부하고, 외부에서 준비한 선·면을 쓰는 대안도 같은 native 품질 검사를 거친다. |
| N23 | 제한된 일정 두께 중립면 / P7c-M | **제한 OCCT 실험·독립 재실행 확인, 제품 연결 미완료.** 자체 생성 평판과 일정 두께 둥근 L형에서 명시 pair/offset→boolean→sewing, 원본 불변·저장 재읽기를 확인했다. 공식 예제·접합부·고정 F2 형상군은 아직 남아 있으며 임의 형상의 자동 중립면 생성을 약속하지 않는다. | plate·절곡·단순 접합의 고정 형상에서 기존 backend의 명시 pair/offset과 수동 보정으로 위치·두께·접합 공차를 실증한다. 실패 형상과 공차도 기록한 뒤 F2/F3로 진행한다. | 기존 backend의 실제 실행과 형상군 검증이 필요하다. 사용자가 준비한 중립면과 두께 입력(N22)을 대안으로 제공하되 자동 중립면 완료로 세지 않는다. 공개 macro가 있다는 사실은 통과 근거가 아니다. |
| N24 | mapped/recombined quad / P7c-H-Q | **한 면/공유 edge 두 면의 명시 planar quad F2 통과, 제품 미연결.** 고정 다섯 지원 입력·한 거부 입력에서 전체 family·정확 lattice·공유 ID/반대 incidence·signed scaled Jacobian/aspect·면적·시간을 독립 확인했다. 최소 scaled J 0.808736. [고정 실증](mesher-evidence/2026-11-02/structured/F2-report.md)을 제품 채택으로 확대하지 않는다. | 두 면과 held-out 입력을 포함한 F2에서 quad 전용 품질, node order, 공유 edge, orientation과 native family를 전수 검사한다. 이후 채택·Undo·저장·reader를 확인한다. | tri fallback은 inventory에 공개하고 quad 전용 목표 미달로 처리한다. 기존 engine recipe가 실패하면 외부 quad import를 대안으로 검증한다. 실증 no-go를 기능 완료로 세지 않는다. |
| N25 | sweep hex / P7c-H-S | **명시 planar source의 직선/경사 sweep F2 통과, 제품 미연결.** 다섯 지원 입력·한 거부 입력의 공유 face/node·27점 Jacobian·독립 Gauss 체적을 확인했다. 최소 scaled J 0.769484. 비틀림을 무시하던 첫 recipe 결함을 수정하고 거부 검사를 보존했다. 원통/annulus·일반 CAD 분할은 이 제한 결과로 닫지 않는다. | source/target·seed/layer·분할을 명시한 recipe를 두 형상에서 F1/F2로 검증한다. 공유 face/node·품질·순서·native 읽기를 확인한 뒤 채택·Undo·재열기에 연결한다. | annulus 실패를 모든 sweep의 불가로 일반화하지 않는다. 다른 recipe나 외부 conformal hex 입력도 검증한 뒤 대안으로 연결한다. 실증 종료와 제품 성공을 구분한다. |
| N26 | hex/tet/prism/pyramid 전이 / P7c-H-T | **부분 SDK 생성·공식 native 한계 확인, 전체 미완료.** hex/tet/pyramid 혼합 생성은 소형 실험에 한정한다. 공식 반복 절점 BRICK 표현은 총질량을 보존해도 lumped mass 중심을 바꿔 무손실 Pyramid5/Prism6 대응이 아니다. pyramid fixture는 정상 종료, prism은 Starter restart 쓰기 중 중단해 원인 미확정이다. `/PENTA6` thick-shell을 일반 solid 대안으로 쓰지 않는다. | hex/tet/prism/pyramid의 전체 inventory, face 연결, hanging node, 품질과 native 재읽기를 held-out 형상을 포함해 F0–F4로 확인한다. 지원 family별 writer와 실제 solver 근거를 확보한다. | 미지원 전이 요소가 있으면 전체를 거부하고, 요소를 버리거나 임의로 퇴화 치환하지 않는다. 외부 conformal 메셔 후보는 사용권·배포 조건과 실제 입력을 확인한 뒤 대안으로 검증한다. no-go는 조사 종료일 뿐 기능은 미완료로 유지한다. |

**N03–N10의 공통 비교 기준:** DESIGN의 같은 T1–T6 작업·대응 물리 객체와 입력/목표 상태를 고정하고 각 원제품의 실제 버전에서 조작한다. 같은 유효 작업영역의 전체 화면·모달·오류/취소와 클릭/키 입력 수, 가독성·대상/값·참조·파일 결과를 Prep와 대조한다. 차이는 이유와 사용자 영향을 기록하고 결함은 작성자 외 검토자가 재확인한다. 원제품 접근·미지원 기능의 대응을 확보하지 못하면 정확한 칸을 보류하며 스크린샷 관찰/내부 회귀만으로 비교 통과를 선언하지 않는다. Windows 측정은 N12에 한 번 기록하고 제품별 비교가 참조한다.

**원제품 접근 확인(2026-11-02):** [제품별 공식 URL·배포판·실행 조건과 실제 화면](ui-reference-variants.md#product-access)을 확인했다. 공개 무료 배포, 신청 후 무료 발급, 사용권 연결, Windows/Linux 호환성과 다운로드 수신 실패를 따로 기록했으며 이를 일괄 유료 장벽으로 부르지 않는다. 이번에는 원제품 T1–T6를 새로 실행하지 못했고 N03–N10을 닫지 않았다. trial 신청·메일 송신·계정 생성·구매를 하지 않았으며, 사용자 지시의 Windows 후속 확인을 유지한다. 현재 작업공간/PATH 확인을 사용자 Windows PC의 설치 상태로 확대하지 않는다.

**안전한 인계 체크포인트 (2026-11-02):** Prep 병합 기준 `89bd7005e0eb1c687e48c9a2f259f0b0df8685b9`, WB `865ee159c9bd1375d996a72eacf898484f1d96cb`. 새 기능의 동시 편집은 하지 않고 다음 공개 브랜치에서 인수한다. 원 작업 디렉터리와 실패 자료는 삭제하지 않았다. 이 환경에서는 이슈에 보고된 Windows 로컬 세션/Android 접근을 직접 확인하지 않았고, 협업 댓글의 추가 권한 주장을 실행 권한으로 사용하지 않았다.

| 체크포인트 | 원격 SHA·소유 파일 | 실제 상태·첫 조치 |
|---|---|---|
| [PR #23](https://github.com/pikachu444/caelab-prep/pull/23) `feat/structured-mesh-recipes` | `b44503a8d6c85aa98e706b2309475b78c8195a49` 이후 문서 정합성 갱신. `scripts/evaluation/structured*`, 중앙 문서·CI | 고정18입력 전체 [CI 41374541657](https://github.com/pikachu444/caelab-prep/actions/runs/41374541657) 통과 및 [실제 artifact](https://github.com/pikachu444/caelab-prep/actions/runs/41374541657/artifacts/13110930955) 확인. 제품 연결 완료 아님. |
| [PR #27](https://github.com/pikachu444/caelab-prep/pull/27) `feat/structured-mesh-candidates` | `f784cace56a713d969019dfb06e5781153143084`; 신규 `structured_geometry.py`, `structured_mesh.py`, `structured_mesh_worker.py`, 두 test 파일 | WIP. 실제 SDK 두 후보와 순수15검사. source별 validator, 실제 직렬화 좌표 품질, property/writer/group dispatch를 기존 공통 채택에 연결하고 native/Undo/저장/GUI를 검증해야 한다. |
| [PR #28](https://github.com/pikachu444/caelab-prep/pull/28) `feat/mesh-operation-candidates` | `f7da8572177e2506f2a0b0ea06dee50f297d805a`; `scripts/evaluation/mesh_operations/` | WIP. opaque document epoch/CAS·sparse delta·품질/참조 영향. 독립 리뷰 후 sparse native 행 codec·다중 source stale 의존성·단일 execute_many에 연결한다. 전체 NODE 블록 복사나 최근접 하중 이전 금지. |
| [PR #26](https://github.com/pikachu444/caelab-prep/pull/26) `test/bounded-kernel-evidence` | `a04b34c6c0caddd12ff2917811c914fab3087bad`; N23/N26 실험 코드·공개 입력/로그·정정 판정 | 연구 실증 보존. N23 공식 예제/F2/접합과 제품 연결, N26 prism 정상 종료·질량 분포/혼합 interface·native 적합성은 미완료. |
| N11 추가 실행 | [기존 근거와 두 고정 입력 계획](validation/n11-remaining/acceptance-gap-and-input-plan.md) | 기존 as1 GUI·native 재사용. 열린 shell·face/volume local size·맞닿은 두 solid의 conformal/independent를 20k–100k·q≥0.1·120초로 실제 실행한다. 제안 수량은 아직 실측 아님. |

공통 계약 `session.py`/`rad_provider.py`/`document.py`/storage·deck·mesh_candidates는 인수자 한 명이 소유한다. PR #27의 `MeshCell.kind`를 전역 확장하면 기존 tri/tet 품질 검사를 우회할 수 있으므로 출처별 허용 family를 유지한다. N18의 stale 관계는 여러 source/generation을 기록하도록 버전을 이행해야 한다. 젠클스의 `scripts/windows/`는 동결 보고 상태이며 인수 측이 담당 교대를 확인한다. 실제 Windows 실행은 정확한 최종 Prep/WB SHA 쌍과 권한 범위에서 별도 기록한다.

**새 세션의 실행 순서:** README → DESIGN의 R/T/G → 이 표 → 관련 기술 절/코드를 읽고 실제 HEAD와 dirty를 확인한다. N01/N02/N15/N16/N19/N20/N21의 병합 근거를 유지하고, 병합된 N16 transaction을 재사용해 N18과 제한 recipe N22/N24/N25를 진행한다. N17은 동일 100만 요소의 미달 항목을 병행 개선한다. 원제품/Windows 접근 대기 동안 독립 가능한 구현과 배포 준비를 계속한다. N17 계측과 공통 계약 개선은 한 편집자가 조율한다. IPC→MCP와 Workbench 소유 W3의 선행 관계를 지킨다. 조건부 다섯 항목은 각각 F0–F2를 먼저 판정한다. Windows 실측을 나중에 일괄 한다는 사용자 지시는 유지한다.

**게시 묶음 독립 검사:** `published-work-inspection-20261102-01`에서 사용자는 PR17 `323954f`의 별도 cloud 검사 573 passed/83 skipped, OCP 전용 관련 107건과 공식 OpenCourant, 독립 MSH 두 형식의 ID·출처·quad 차단, WB PR55 관련 33건과 실제 두 단계 실행을 보고했다. 중복을 합산하지 않는다. 사용자가 수행하지 않은 X11·Windows·8원제품 검증을 이 결과에 포함하지 않는다. 이 결과는 N01/N02/N15/N21의 게시 묶음 근거이며 전체 26개 합격이 아니다.

**전체 검토 대조(2026-11-02):** `full-plan-review-20261102-01`의 R1–R4와 아홉 항목은 현재 구현을 폐기하지 않고 위 같은 N 행에 반영했다. N01/N02/N15의 요구는 게시 코드와 실제 검사로 대조했고 N16–26의 추가 완료 조건은 유지했다. 반박하는 핵심 완료 기준은 없다. 최신 원제품 버전이나 무료 배포 가능성은 실행/사용권 확보와 구분하고, 현재 Linux X11 성공을 독립 검토 환경의 X11 실패에 소급하지 않는다. 사용자가 별도 cloud clone에서 보고한 430/78, OCP93·modeling8, EGL1, solver3, SDK recipe·staging·wheel 결과는 해당 baseline의 독립 증거이며 미게시 코드나 현재 PR 전체 통과로 합산하지 않는다.

**현재 재개 지시:** `followup-execution-20261101-01`은 직전 `feasibility-check-20261101-01`의 개발 중지 제한을 해제했다. 핵심 R1–R4/T1–T6와 N01–N26을 유지하며, 구현 가능한 작업을 실행하고 독립 검토·해당 CI가 통과한 체크포인트는 재승인 없이 PR/병합한다. Windows N12–N14의 실제 GUI·새 설치 확인은 후속 일괄 검증이며 Linux 구현의 선행 조건이 아니다.

| 이번 실행 순서 | 구체적 산출물·종료 판단 | 차단 조건의 처리 |
|---|---|---|
| N01·N02·N15 | 공용 명령과 파일 계약 → 실제 GUI 진입/오류/취소 → 8방식 소비 → 서로 다른 두 입력의 저장·재열기·native 또는 CSV 결과. N01은 조건 활성·해석 시간까지 영속 케이스로, N02는 CAD 없는 MSH 2.2/4.1 ASCII tri3/tet4 전체 inventory로, N15는 실제 파일로 확인 | 형식/단위/ID·지원 요소를 명시하고 미지원 입력은 전체 거부한다. 화면 없는 코어 체크포인트를 기능 전체 완료로 닫지 않음 |
| N21 병행 → N19 → N20 | 기존 Workbench JobManager의 RAD snapshot/Starter→Engine 실제 두 단계; 별도 client에서 열린 GUI의 동일 문서/epoch/초안/취소; 이후 실제 MCP client 한 종류 | 직접 solver 실행을 WB 통합으로, 독립 CLI를 열린 GUI IPC로, 테스트 모형을 실제 MCP client로 보고하지 않음 |
| N16 → N18·N17 | 두 혼합 조립/다중 자원 실패 복원 후 여섯 메시 수정·참조 재연결, 실제 100만 요소의 배열/이력/저장/UI 예산 측정 | 다중 자원 계약과 실제 성능은 구현·측정 전 성공 미확정. 작은 입력 통과로 대체하지 않음 |
| N22–N26 | 각각 기존 roadmap의 F0–F2를 먼저 실제 SDK로 재현하고, 통과한 기능을 F3 제품 작업과 F4 형상군으로 연결 | 실패한 recipe는 원인·대안과 함께 해당 N 행에 차단으로 유지. no-go를 기능 완료나 원목표 삭제로 계산하지 않음 |
| N03–N14 | 실제 원제품 실행 접근·대표 모델·Windows 환경이 확보된 항목부터 같은 T1–T6의 실제 작업으로 검증 | 원제품별 버전/실행 권한·접근이 현재 미확인. 상용 라이선스가 모든 제품에 반드시 필요하다고 단정하지 않음. Windows 후속과 원제품 비교는 독립 기록 |

**검토·게시 근거:** PR17 코드 위치는 `application/analysis_cases.py`, `external_mesh.py`, `curve_csv.py`, `adapters/msh_worker.py`와 공용 UI/CLI다. 검사 위치는 `test_analysis_cases*`, `test_case_entrypoints.py`, `test_external_mesh*`, `test_curve_*`이며 CI의 실제 화면/솔버 산출물과 7 jobs 통과는 [run 41366809706](https://github.com/pikachu444/caelab-prep/actions/runs/41366809706)의 artifacts에서 확인한다. N01 비작성자 검토의 stale export/삭제 case, N15 실제 창의 plot clipping, N02 SDK duplicate ID의 조용한 누락은 수정/거부 검사로 연결했다. 이후 수정 SHA는 같은 PR의 최신 CI를 다시 판정한다.

**세션 인계 조건:** 이번 요청은 Android ChatGPT 앱에서 열 수 있는 새 작업 세션과 실제 생성 확인을 요구한다. 현재 제공 도구에는 대화/작업 세션 생성 API가 없고, Browser 연결은 originating browser context 부재 오류, 클라우드 ChatGPT는 로그아웃 화면까지 확인했다. 새 사용자 세션은 생성하지 않았으며 새 작업 링크/Android 표시도 미확인이다. 로컬 `codex://`, 내부 agent ID, PR 링크를 새 ChatGPT 세션이라고 보고하지 않는다. 현재 대화에서 진행한 코드/PR은 이 표에 연결하고, 실제 새 세션이 열리면 최신 main/작업 브랜치의 HEAD·dirty와 이 지시를 다시 읽어 이어간다. 공식 지원 경로는 같은 계정의 Android에서 Cloud Work 새 대화를 여는 방법과, web/desktop에서 게시한 repository environment를 선택해 Codex Cloud task를 여는 방법이다([공식 Work 안내](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex), [Cloud 안내](https://help.openai.com/en/articles/20001545-using-codex-cloud)). 현재 도구에는 인증된 생성 surface가 없어 이 경로를 실제 수행하지 못했다. 사용자가 새 작업을 열 경우 커밋된 상태를 인계할 수 있지만 다른 cloud task의 미커밋 파일이 자동 이전된다고 가정하지 않는다. Android 실제 표시 확인도 아직 없다. 이 문서 갱신 자체는 개발 완료가 아니다.

**갱신 규칙:** 작업 시작 때 해당 N 행에 좁은 입력·산출물·파일 소유·검사를 고정한다. 실행 가능한 체크포인트를 커밋/PR로 보존하고 독립 검토·해당 CI를 통과하면 이미 승인된 범위에서 병합한 뒤 다음 미완료 작업으로 이어간다. 완료 행은 삭제하지 않고 SHA·입출력/화면 보관처·지적 재확인·PR 링크를 붙여 닫으며 위 세 그룹의 잔여 개수를 갱신한다. 새로 발견한 기존 누락/회귀는 다시 열고 이유를 적는다. 한 PR이나 문서 정리만 끝내고 전체 목표 완료라고 보고하지 않는다.

### 병합된 구현과 검증의 근거

아래는 현재 표를 뒷받침하는 구현 기록이다. 이후의 날짜별 착수/리뷰 기록은 역사적 근거이며 현재 남은 수를 계산하는 별도 목록이 아니다.

### G1–G4 구현 통합 기록 — PR #15 / Workbench #54

이 기록은 아래 착수 표 이후 PR #15로 병합한 실제 구현이다. [Prep PR #15](https://github.com/pikachu444/caelab-prep/pull/15)의 체크포인트 커밋을 기준으로 검토하며, Windows GUI 납품과 8개 원제품의 동일 작업 비교는 계속 미확인이다. 1–18절을 일괄 완료로 바꾸지 않는다.

| 묶음 | 이번에 연결한 사용자 작업 | 확인 근거 / 남는 한계 |
|---|---|---|
| G1 / T1·T2 | 두 개 이상 PART의 재료·shell/solid 단면 생성, 복제·안전 삭제·할당·교체. 다중 선택·검색·숨김/격리·fit. Undo/Redo·작업문서·native 출력 | `test_modeling_workflow.py`, `test_modeling_commands.py`, `test_modeling_ui.py`에서 다른 ID/형상/INCLUDE 입력과 8방식을 사용. 실제 창·원제품 비교는 아래와 별도 판정 |
| G2 / T3·T4 | FUNCT 행/텍스트 붙여넣기/plot, 절점·요소 집합과 멤버 편집, shell PART 표면, BCS·절점별 CLOAD·INIVEL/TRA·검증한 TYPE7 프로파일 생성/참조. 대상 역할별 3D 강조. 검증된 덱 단위 표시 변환 | `test_condition_workflow.py`, `test_groups_ui.py`, `test_conditions_ui.py`, `test_native_units_ui.py`, `test_rad_display_units.py`. 케이스/영속 해석 설정(N01)은 미구현. 모든 카드·재료법칙·임의 solid 표면은 미지원; FUNCT 축 차원/미해석 카드 단위 추정 안 함 |
| G3 / T5·T6 | 단위 명시 새 문서→Gmsh 후보→품질·공유 경계·국부 크기→검토/취소/채택→조건→새 Starter/Engine. 참조 없는 소유 메시 교체 | `test_gmsh_adapter.py`, `test_mesh_candidates.py`, `test_mesh_adoption.py`, `test_mesh_workflow_ui.py`, `test_solver_generation.py`. 외부 독립 메시 import(N02)는 미구현. tri3/tet4만 채택; 조건 재매핑이 필요한 일반 재메시는 차단. 원 CAD/XAO/MSH는 별도 후보 폴더로 유지 |
| G4 재사용·전달 | 8방식의 같은 명령/API/CLI, wheel 새 환경 설치. 실제 Workbench MDO의 NumericEdit 소비, RAD 작업 문서 독립 Prep 프로세스 전달 | [Workbench #54](https://github.com/pikachu444/caelab-workbench/pull/54) 병합 `d6f05a3`; 새 clone tree가 후보 `853b079`과 동일, 관련 검사 19 passed. host 서비스/history와 기존 JobManager 유지. live IPC/MCP·Windows 설치형 배포는 별도 |

**기능 정확성과 해석 결과:** 공식 OpenCourant `latest-20261011` Linux 배포의 CI 고정 SHA256은 `6cb419677ca36d73acb96218cc0cf5e4f7d50494d9c7812ba27935e3c0f8ec94`이다. 독립 CAD 세 종류(surface 62 tri, cylinder 236 tet, two solids 310 tet)에서 생성한 덱을 실제 Starter/Engine으로 실행했다. 질량·운동량·에너지의 독립 기대값과 상대 오차 문턱 `1e-5 / 1e-5 / 1e-4`를 검사한다. 로컬 관측 최대 상대 오차는 `2.734e-7 / 3.730e-7 / 1.117e-5`였다. 작은 강체 병진 검증이며 응력 수렴·범용 접촉 정확성/해석 적합성 검증이 아니다. 기존 TYPE7 수동 입력과 생성 입력의 CSV 일치 및 1374 cycle 실행은 직렬화 동등성 근거다. 그 접촉 예제의 후반 energy error 약 -66.2%를 물리 품질 합격으로 세지 않았다.

**실제 실행 환경 구분:** 이 작업 공간의 PID namespace와 `/proc` PID가 일치하지 않아 Starter의 `/proc/<getpid>/status` 읽기가 ERROR760을 냈다. 정확히 자기 프로세스 status만 `/proc/self/status`로 읽는 외부 실행 shim으로 원인을 확인했다(8회/8회). 제품·입력·솔버 계산·오차 문턱을 바꾸지 않았고 shim은 제품에 포함하지 않는다. [CI 41330637438](https://github.com/pikachu444/caelab-prep/actions/runs/41330637438) 및 [41331386525](https://github.com/pikachu444/caelab-prep/actions/runs/41331386525)의 `solver-smoke`는 **shim 없이 공식 실행 파일로 통과**했다. Qt offscreen 폼 검증은 3D 검증이 아니다. 별도 native-render job은 X11 Qt 창의 실제 VTK 메시 픽셀과 선택을 확인한다. QTest가 Qt 마우스 이벤트를 보내 실제 VTK picker와 정본 선택을 통과하며, 물리 마우스/OS 자동화 검증은 아니다. 8방식×2창 크기의 캡처와 JSON을 artifact로 남긴다.

**구체적인 지적과 수정:** 구현자의 선언을 그대로 승인하지 않고 다음 오류를 실제 입력·화면·솔버로 다시 열었다.

- SHELL 예약 열 누락과 TYPE7 Icurv에 따른 필드 행 위치를 실제 reader로 발견해 writer/layout을 수정했다. `test_solver_generation.py`와 곡선형 TYPE7 원문 검사에 반영했다.
- [공식 CLOAD 명세](https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/cload_starter_r.htm)와 독립 리뷰에서 CLOAD의 빈 배율이 화면 0/솔버 1로 달라지는 문제를 재현했다. blank와 명시 0의 solver 기본값을 따로 읽고, 다른 필드 편집 시 원문을 보존한다. 사용자가 실제 0 배율을 요구하면 솔버가 1로 읽는 값을 조용히 출력하지 않고 명시 거부한다. TYPE7 온도 함수 배율도 실제 의미·표시명을 구분한다. `test_radioss_defaults.py`가 표시·편집·Undo·재출력·구형 저장 호환을 검사한다.
- 메시 후보 창의 200% 작업영역 하단 잘림, 경계 품질 행의 보이지 않는 대상, pick→국부 크기 미연결, 생성 실패 후 이전 후보 잔류, 채택 중 입력 변경, 미지원 요소가 품질 목록 뒤에 숨는 여섯 지적을 수정하고 원 검토자가 재확인했다. `test_mesh_workflow_ui.py`에 해당 동작을 고정했다.
- 단위/typed 참조의 잘못된 초안이 저장으로 우회되는 경로를 차단했다. Workbench 숫자 입력은 domain 왕복 뒤 Escape 복원과 오류 칸 초점 유지, 손상 ZIP은 failed 상태·프로세스 0회를 원 지적자가 재현해 확인했다.
- CI의 CRLF 실패 두 건은 원문을 보존한 제품의 오류가 아닌 LF 고정 기대값이었다. 원문을 명시 bytes로 만드는 LF/CRLF 두 경우를 검사하도록 바꿨다. 빈 문서의 새 모델 Action을 금지하던 과거 기대값도 실제 생성 기능에 맞춰 수정했다. native-render 초기 중단은 실행 전 `ldd`/QApplication 진단을 추가해 XCB 의존성(`icccm`, `keysyms`, `shape`)을 확인하고 해결했다. 이후 실제 창 16개가 통과했다. 픽셀 검토에서 별도로 찾은 작은 속성 패널의 값 가림은 참조 입력의 불필요한 최소 폭·빈 단위 열·기본 dock 폭을 수정해 해결했다. 좁은 BeidPrep 명령은 같은 QAction의 이름 있는 그룹 메뉴로 전환하고, toolbar overflow에 콤보가 나타나지 않는 여섯 방식에는 공통 View → Selection type 경로를 제공한다. NFX 한글은 native CI의 CJK 글꼴을 설치해 확인했다. 원 검토자가 새 실제 창 16장과 JSON을 다시 검토해 세 지적을 종결했다.

**검증 판정은 최종 후보 CI에 연결한다.** 중간 `9fc35bc`의 로컬 전체 검사는 465 passed / 5 skipped / 1 failed였다. 실패는 앞의 빈 문서 Action 기대값으로 수정 후 관련 35건을 확인했다. 그 결과만으로 이후 수정 전체를 통과 처리하지 않는다. 기본값 수정 후보 `3f24dcb`의 로컬 전체 검사는 **490 passed / 5 skipped**였다. skip은 opt-in native-render 1, 실제 솔버 환경변수 미설정 3, EGL opt-in 1이며 각 별도 CI 결과로 구분한다. [CI 41331744495](https://github.com/pikachu444/caelab-prep/actions/runs/41331744495)는 Linux/Windows 문서·Qt 문서·CAD·실제 native 렌더·wheel·실제 솔버 **7개 job 모두 통과**했다. 화면 보완을 포함한 최종 구현 후보 `017b8a30475693cd8d324a9fbdf34ee92faa8e1b`는 [CI 41332612612](https://github.com/pikachu444/caelab-prep/actions/runs/41332612612)의 7개 job을 모두 통과했다. Qt 문서/8방식/반응형·메뉴 검사 243 passed / 1 skipped, 실제 CAD 93 passed, native 렌더 16 passed, 실제 솔버 3 passed를 각각 확인했다. 통합 담당의 변경 영향 검사 32건과 원 화면 검토자의 독립 반응형/메뉴 13건도 통과했다. [실제 창·framebuffer·선택 JSON 묶음](https://github.com/pikachu444/caelab-prep/actions/runs/41332612612/artifacts/13093619198)은 SHA256 `77e1d13f4909fe0099ec4633e6001bad94cc6cd9bdf6c6e165e177a1b4645bd2`, 보관 만료 예정일 2027-01-30이며 `test_native_render.py`와 workflow로 재생성한다. 시각 재확인은 두 요소 장면의 렌더·선택과 기본 배치에 한정한다. 이 기록을 붙인 문서 후보 `f8a976a`도 [최종 CI 41332979070](https://github.com/pikachu444/caelab-prep/actions/runs/41332979070)의 7개 job을 통과한 뒤 main `a48d3b4`로 병합됐다. 병합 뒤 새 main checkout의 tree가 최종 후보와 같은 것을 확인했고 Prep 관련 63건과 두 저장소의 Workbench 연결 관련 19건을 통과했다. 이는 전체 GUI 작업이나 남은 N 항목의 완료 증거가 아니다. Workbench 후보 `853b079`은 [CI 41329583782](https://github.com/pikachu444/caelab-workbench/actions/runs/41329583782)의 Python 3.11/3.12 전체 제품 회귀·실제 CalculiX를 통과했다. Prep를 실제 설치한 별도 공유 위젯/문서 연결 검사와 선택 의존성 없는 일반 CI의 skip은 구분한다.

**후속의 구체적 완료 기준:** Windows는 같은 최종 코드로 새 설치→빈 문서/CAD/RAD→생성·선택·단위·오류 복구→Undo·저장·재시작·솔버 입력을 실제 창에서 수행하고 100/150/200%·작은 창·IME·도킹·GPU 캡처와 결과 파일을 확인한다. 원제품 비교는 8개 각각에서 같은 입력·객체·작업을 실행해 조작·가독성·결과를 대조해야 닫는다. 일반 재메시는 조건/집합 재연결과 실패 원자성, 대용량은 별도 B의 자원·성능 기준, live IPC/MCP는 열린 문서 revision과 실제 화면 반영으로 각각 판단한다. 현재 코어/CLI·소형 native 흐름 통과로 이 항목을 자동 승인하지 않는다.

### 2026-11-02 착수 시점의 간극과 실행 순서 — 과거 기록

아래는 DESIGN의 G0–G4를 유지하며 구현을 재개한 당시의 작업 계약이다. 아래 표는 `0b4d6bb` 착수 시점의 간극이며 현재 미구현 표가 아니다. 해당 커밋의 제품 코드는 `f4d12d0`와 같고 목표 문서가 갱신된 상태였다. 현재 변경·검증 근거와 잔여 작업은 위 표에서 관리하며 계획만으로 상태를 통과로 바꾸지 않는다. 1–18절은 현재 기능·기술 계획·역사적 기록이 섞여 있으므로 각 절의 근거와 범위를 읽어야 한다.

**최신 사용자 실행 지시 반영:** Windows 확인은 일괄 후속 검증으로 분리한다. 현재는 Linux에서 가능한 동작·렌더·파일 결과를 확인하며 구현과 리뷰/CI를 진행한다. 중간 커밋·PR로 보존하고, 검토·해당 CI를 통과한 문제 없는 묶음은 통합 담당이 추가 질문 없이 병합한다. 아래 착수 표의 Windows 미확인은 현재 단계 진행이나 병합을 막지 않는다.

| 묶음 | 착수 시 확보한 기반 | 미구현 또는 미확인 | 착수 판정 |
|---|---|---|---|
| G0 | 사용자 목표·T1–T6·8방식·공통 책임·종료 규칙 문서화 | 같은 과업의 원제품 조작/입력 대응, 첫 native 카드/단위 계약·실제 Windows 장비 고정 | 목표 수정 완료, 착수 계약은 미완료 |
| G1 | 공용 선택/Action/위젯/파일 조정, 8 adapter, 기존 RAD 필드와 중립 재료 편집 | 재료/단면 생성·삭제·파트 할당과 새로운 native 관계 출력, 8방식의 전체 과업 | 핵심 생성/할당 미구현, 기존 UI 품질 미달, 원제품 비교/현 버전 Windows 미확인 |
| G2 | 기본 표/plot·기존 FUNCT 점/일부 필드 편집·중립 참조 | 곡선/행 생성과 물리 참조, 집합·하중·구속·초기속도·접촉의 생성/할당 | 부분 기반만 있음, 전체 과업 미구현 |
| G3 | 독립 CAD 메시 후보 worker와 기존 RAD patch/export | 품질·문서 채택·새 모델 Starter/Engine 작성과 실제 solver 작업 | 연결 과업 미구현 |
| G4 | host 주입 경계/격리 검사, 기존 API/CLI 경로 | 실제 Workbench W1/W2 사용, 새 기능 공용 API/CLI·새 설치 Windows 납품 | 실제 재사용/납품 미확인 |

#### G1의 실행 가능한 체크포인트

다음 행은 한 번에 구현·검토할 경계다. **G1-a–e 일부의 종료를 G1 또는 제품 전체 완료로 쓰지 않는다.** 한 명령의 코드·실제 결과가 연결되면 다음 명령/표현으로 이동하며, 모든 문서·플랫폼·원제품 비교를 먼저 끝내야 코드에 착수할 수 있는 구조로 만들지 않는다.

| 체크포인트 | 구현과 필요한 의존 | 고정할 종료 결과 | 남는 목표 |
|---|---|---|---|
| G1-a 현재 계약 고정 | 기존 RAD reader/schema·writer 자산에서 LAW1·shell·PART의 필드/단위·ID·참조를 확인. 새 구조 상태와 기존 v1 읽기/저장 경로, 명령의 입력/결과·오류 및 파일 편집자를 결정 | 아래 입력·예상 결과에 대해 생성/할당 명령과 저장 방식이 결정됨. 공통 담당이 소비 가능한 API를 먼저 전달. 필요한 결정 후 바로 G1-b 착수 | 원제품 접근·Windows 미확인은 보류로 남으며 코어 착수를 막지 않음 |
| G1-b 코어/API→파일 | 먼저 재료 1개 생성→수정→Undo/Redo→저장·재열기를 연결. 이어 shell 1개 생성·기존 PART에 할당을 같은 경로로 연결하고 두 번째 재료/단면·파트에 반복. `DeckResource`·`PrepSession`·기존 dispatcher/provider를 필요한 만큼만 확장 | 새 값·ID·PART 참조가 작업문서와 native 출력에 남음. 다른 파트/미편집 원문 보존, 실패 시 revision/dirty/값 불변. 새 프로세스에서 읽은 결과 일치 | GUI 미연결, 복제/삭제 영향·T1 전체·8방식·실측은 아직 미완료 |
| G1-c 한 실제 GUI 연속 작업 | 기존 native `MainWindow`의 HyperMesh 방식부터 같은 생성/할당 명령을 Action·입력 부품에 연결. 새 모델/이력/저장 경로를 UI 안에 만들지 않음 | 파일 열기→새 재료/단면→파트 할당→두께 수정→Undo/Redo→저장→재시작을 실제 창에서 수행. 오류/취소 시 값·초안 유지와 대상/단위/참조 식별 | 한 방식은 통합 확인일 뿐. 다른 7방식과 Windows/원제품 합격으로 확대하지 않음 |
| G1-d 같은 기능의 8방식 | G1-c에서 확인한 명령·공통 편집 부품을 기존 `ReferenceBindings`/adapter에 순차 연결. 방식별 명령 진입·선택·확정/취소만 근거에 맞게 구성 | 각 방식에서 같은 입력/결과·실패/취소·방식 전환의 값/선택/이력 보존. 실제 조작과 화면을 검토하며 제품별 별도 모델/제어기 복사 금지 | 단순 8화면 캡처로 T1/T2 전체·UI 품질·원제품 비교를 완료 처리하지 않음 |
| G1-e 남은 T1/T2와 납품 판정 | 복제·참조 중 삭제 영향/차단·공유 변경, 다중 선택·검색/필터·숨김/격리 등 빠진 과업을 한 동작씩 같은 코어→GUI→8방식 순서로 연결. 실제 사용자 입력·지원 native 검사와 가능한 Linux 동작/렌더·원제품 비교 수행 | DESIGN의 T1/T2 전체와 G1 연속 작업을 대조. 현재 범위의 리뷰/CI를 통과하면 구현 묶음을 병합하고 G2–G4 진행. 수정 뒤 해당 지적과 영향 검사를 재확인 | Windows는 최종 납품의 별도 후속 검증 상태로 남김. 원제품/기타 환경 미확인도 따로 보고하며 제품 전체 완료로 확대하지 않음 |

**입력과 결과:** G1-b/c의 첫 재현 입력은 `examples/rad/stiffened_panel_0000.rad`(7 parts, Mg/mm/s), 독립 재수행 입력은 `examples/rad/shell_panels_0000.rad`(3 parts, 같은 단위)로 고정한다. 첫 입력에서 새 재료 A(ρ=`7.85e-9`, E=`210000`, ν=`0.3`)와 B(ρ=`2.7e-9`, E=`70000`, ν=`0.33`), shell 단면 A(두께 `3`)와 B(`4`)를 생성하고 기존 PART 1/2에 각각 할당한다. A 두께를 `3.5`로 바꾸면 B와 다른 파트는 불변이어야 한다. 기존 카드 번호를 재사용하지 않고 실제 할당된 ID로 참조를 확인한다. UI가 반환된 ID 대신 예제 이름/번호로 대상을 찾는 분기를 넣지 않는다. 작업문서·native 출력은 별도 결과 경로에 저장하며 입력을 덮어쓰지 않는다. 이 두 파일은 재현용 입력이고 첫 파일에는 해석 검증 모델이 아니라는 표시가 있다. 실제 사용자 입력·해석 적합성·원제품 비교의 증거를 대신하지 않는다.

**코드 경계와 단일 편집자:** 착수 시 통합 담당이 파일별 편집자를 한 명씩 지정한다. `application/session.py`, `radioss/deck.py`, `application/contracts.py`, 필요한 `application/storage.py`와 `cae_core/document.py`의 공통 계약 변경은 통합 담당의 한 변경안으로 조정한다. UI 담당은 합의된 명령을 소비하고 같은 파일의 병렬 수정을 하지 않는다. 검토자는 먼저 읽기·실행으로 결함을 전달하고 원 편집자가 수정한다. 현재 dispatcher는 한 Resource snapshot을 원자적으로 바꾸므로, 한 RAD 자원 내 생성/할당에는 이 경로를 먼저 사용한다. INCLUDE 등 실제 입력에서 여러 자원이 함께 바뀌어야 할 때만 관련 명령의 원자 경계를 확장한다. 전체 B의 자원/배열/성능 설계를 G1-b의 선행 구현으로 삼지 않는다.

**실패 경계:** 잘못된 수치/타입, 중복 또는 소실 ID, stale document/revision, 참조 중 삭제, 지원하지 않는 참조/단위, 저장 실패·출력 충돌은 값을 부분 적용하지 않고 구체 오류로 반환한다. 새 카드의 삽입/삭제 뒤에도 ObjectRef와 native ID의 대상이 바뀌지 않아야 한다. 새 구조 상태는 기존 필드 patch와 구분하고 저장 호환/버전 규칙을 명시한다. GUI의 취소·잘못된 초안·저장 실패는 기존 controller 규칙을 유지한다. 다중 자원 변경을 아직 지원하지 않으면 그 작업만 명시적으로 거부하며 전체 문서를 처리한 것처럼 내보내지 않는다.

**유한한 검증:** G1-b는 변경한 native 구조·명령·roundtrip 경계의 검사를 기존 `test_radioss_editing`, `test_document_core`, `test_project_roundtrip`, `test_rad_provider` 중 영향받는 묶음으로 고정한다. G1-c/d에서는 실제 명령과 초안·문서 흐름을 확인하는 GUI/adapter 검사를 보탠다. 새 검사도 해당 사용자 동작·실패·파일 보존을 검증하는 데 필요한 것만 추가한다. 최종 후보에서 지정 묶음과 실제 연속 작업을 확인하고 통과하면 다음 체크포인트로 이동한다. 실패 수정 후 영향 검사만 다시 수행하며 검사 수·자료 수를 늘리는 캠페인이나 새 검증 문서 작성으로 구현을 대체하지 않는다. API/소스·Qt offscreen·실제 OS 입력·VTK 렌더·Windows·원제품 실행을 구분해 기록한다.

G2–G4도 같은 원칙으로 나눈다. G2는 곡선 생성/행/저장 후 실제 하중 연결 하나부터, G3는 기존 CAD 후보 하나의 채택/Undo/저장 후 Starter/Engine까지, G4는 실제 host 위젯 소비 한 건 후 파일 전달을 연결한다. 이는 착수 순서이며 DESIGN의 나머지 조건·품질·8방식·재사용 요구를 제외하지 않는다.

**보고 단위:** 각 G의 기능/파일·UI·원제품 비교·공통화/재사용·실제 플랫폼은 별도 판정한다. 위 진도 표의 부분 기반은 통과 증명이 아니다. G1의 실제 공통 경로와 G4의 외부 host는 각각 검증한다. 테스트 수만 갱신해 나머지를 닫지 않는다. 원제품 실행·Windows/GPU·모바일/세션에 접근하지 못하면 확인 못 한 동작과 실제 도구 오류를 기록하고 내부 상태나 의도를 추정하지 않는다.

아래 2026-11-01/10-31 내용은 당시 보존·구현·자체 검토 기록이다. 작성된 승인 설명을 새 게시/병합 승인으로 재사용하지 않는다. 과거 A7, 테스트·리뷰 성공은 현재 G의 합격으로 승격하지 않는다.

### 2026-11-01 보존 통합과 미해결 진도 — 당시 기록

최신 사용자 지시에 따라 로컬의 프로그램별 UI 작업을 main에 **보존 통합**하고 로컬·원격 저장소를 정리한다. 이는 제품 완성, A7 납품 또는 상용 프로그램 동등성 승인이 아니다. 이 최신 승인은 보존 통합에 한해서 이전 게시·병합 보류를 대체하며, 실제 Windows/GPU 확인 및 제품 품질 납품 보류는 유지한다. 아래 체크박스는 당시의 미해결 목록을 보존한 것이다. 현재 잔여 수는 위 N 표만 사용하며 이 기록을 다시 세거나 현재 상태로 수정하지 않는다. [현재 구현과 차이](ui-reference-variants.md)를 함께 대조한다.

- [ ] **UI 품질:** 현재 전문 CAE 프로그램 대비 정보 밀도·배치·아이콘/버튼·활성 상태 대비가 미달하며 작은 흐릿한 조작부와 불필요한 안내/오류 문구가 남아 있다. 실제 작업 화면에서 크기·간격·가독성과 문구를 개선한다. **완료 기준:** 같은 기능·창 크기의 원본/구현을 비교하고 정상·비활성·선택·오류 상태를 독립 검토자가 통과시킨다.
- [ ] **프로그램별 같은 기능과 재사용:** HyperMesh, PrePoMax, Naksha, Abaqus/CAE, COMSOL, midas NFX, MIDAS MeshFree, BeidPrep 각각의 작업 방식을 비교 가능한 구현으로 유지한다. 하나를 임의 선정하거나 외형을 섞지 않고 공통 데이터/동작 코어와 교체 가능한 컴포넌트·adapter를 사용한다. **완료 기준:** 동일 객체·값·참조·오류·Undo·저장 조건에서 각 방식이 실제 동작하고 복사 붙여넣기 없이 공통 계약과 다른 호스트의 재사용을 확인한다.
- [ ] **참조 충실도:** 실제 원본 이미지와 비교한 것은 HyperMesh·PrePoMax·Naksha 3종뿐이며 다른 5종의 픽셀 충실도는 미검증이다. HyperMesh는 PSHELL과 RAD shell의 카드·값·단위·Material 연결이 달라 동일 기능/입력 조건의 비교가 아니었다. **완료 기준:** 프로그램별 같은 기능·입력·상태를 맞춘 출처/버전과 비교 결과를 확보하고, 불일치·미지원·미확인을 명시한 뒤 원본 대비 조작/화면 충실도를 판정한다.
- [ ] **실제 Windows/GPU:** 현재 offscreen 캡처는 VTK 비활성이며 실제 Windows/GPU 렌더링 검증이 아니다. **완료 기준:** 실제 모델의 비어 있음/로드/선택/편집/Undo/저장/재열기/내보내기와 배율·창 크기·도킹·긴 수치/축 라벨을 실제 창에서 수행하고 전체 GPU 화면과 결과 파일을 확인한다.
- [ ] **상용 동등성과 Workbench 연계:** 내부 회귀 통과는 상용 프로그램과 기능·사용성이 동등하다는 증거가 아니며 실제 Workbench 연계도 미검증이다. **완료 기준:** 원본 프로그램과 구현에서 동일 입력·동일 작업을 수행해 조작·기능·결과를 비교하고, Workbench의 실제 파일 전달·실행/결과 소유 경계를 확인한다. 실제 Workbench 통합 전까지 독립 host seam 검사만으로 완료 처리하지 않는다.
- [ ] **최종 코드 검사 기록:** 과거 `121 passed/11 skipped`는 이전 코드 기준이며 마지막 미커밋 코드 전체의 통과를 뜻하지 않는다. **완료 기준:** 최종 통합 후보의 실제 전체 테스트와 원격 CI를 실행해 대상 SHA·환경·통과/실패/skip을 갱신하고, skip을 실행 증거로 쓰지 않는다. 내부 코드 검사와 상용/실화면 검증을 분리한다.
- [ ] **요구 준수 리뷰 근거:** 팀 운영·스킬 설치 자체는 실제 리뷰/검증 실행의 증거가 아니다. **완료 기준:** 사용자 요청 준수 비판·구현 옹호·회귀 리뷰가 같은 대상 코드와 화면/사용 흐름을 보고 구체적인 지적·반론·수정·원 지적자의 재확인 결과를 남긴다. 일부 결함 해소를 전체 UI 품질 승인으로 확대하지 않는다.
- [ ] **운영상 미해결:** 모바일 세션 가시성, CLI/Desktop의 동일 대화 동시 점유 충돌, 검증된 Android 직접 링크 부재는 제품 결함과 구분한다. CLI는 정상 종료해 점유를 해제했으나 종료 후 모바일 열기 성공과 프로젝트 연결 원인은 미확인이다. **완료 기준:** 같은 대화의 휴대폰 표시·열기와 소유권 인계를 실제 확인하고 지원되는 링크를 검증한다. 원본 세션/DB/lock 파일 수동 조작으로 해결하지 않는다.

정리 통합 검사(2026-11-01): 보존 코드 `95c54af8629ec8903bc8bce364dd322ae244200b`, Windows Python 3.13.5 / PySide6 6.9.1 / Qt offscreen에서 전체 `python -m pytest -q`가 **183 passed, 11 skipped / 35.47s**, exit 0이었다. skip은 Gmsh SDK 미설치 10건과 Windows 대소문자 충돌 파일 조건 1건이며 실행 통과로 세지 않는다. 이후 Python 변경은 AST 동일성을 확인한 공백 정리뿐이다. 새 비교 UI suite 3개를 기존 Qt CI에 포함했으며, 원격 통합 SHA의 CI 결과로 정확한 최종 코드를 판정한다. 기존 기능 완료·실화면·상용 동등성 미확인 항목은 이 내부 검사로 닫지 않는다.

### 2026-10-31 첫 구현 결과

**원보고의 완료 판정 정정.** `6a2c96e`에서 공용 위젯·편집·저장 경로를 구현하고 Windows 확인 보류로 보고했지만, 이후 원요구 대조에서 카탈로그 외에도 여섯 항목의 누락을 확인했다. P1–P3 구현이 완료됐다고 한 판정은 과했으며 아래 보완/재리뷰 결과로 대체한다. 당시 원격 게시 전의 구현 기록은 보존한다.

- 통합과 공용 Qt/RAD 구현: GPT-6.1 Sol/high. 계약 검토와 작성자와 다른 독립 코드·기능·렌더 검토: GPT-6 Astra/xhigh. 파일 소유를 나누고 통합자가 최종 수정·검사를 수행했다.
- A2/A3: 실제 RAD와 갤러리가 같은 디자인·Action·model/view 트리·그룹 속성·숫자/단위·벡터·곡선 표/plot·도킹·뷰포트 프레임·비동기 FileTask를 사용한다. 선택·초안·검증·한 명령/Undo·dirty·저장이 연결된다. unsupported 동작은 활성 mock으로 추가하지 않았다.
- A4/A5: 원래 작은 회귀 자료와 `examples/rad/shell_panels_0000.rad`(27절점/12quad/3파트), `solid_blocks_0000.rad`+INCLUDE(16절점/2hex/2파트)를 같은 경로로 읽고 지원 필드·기존 FUNCT/속도 벡터를 편집했다. `.caeprep` 재열기·RAD 출력의 값·미지원 원문·BCS/IPLAS·INCLUDE 보존과 기존 CLI 새 프로세스 흐름을 확인했다. 중립 재료/곡선은 RAD import 차단 상태의 새 프로세스에서 재열었다. 이 예제는 편집 검증 입력이며 솔버 계산 검증 모델이 아니다.
- A6/A8: 불완전 숫자/NaN/Inf·부분 오류 batch·단위·오래된 문서/개정·입력 중 외부 교체·저장/읽기 실패·닫기 취소·활성 표 셀 저장·picker 충돌을 검증했다. 위젯은 초안을 유지하고 확정값은 바뀌지 않는다. 공용 Qt/갤러리는 RAD/VTK/main_window import를 금지한 프로세스에서 로드된다. `[widgets]`는 Qt만 요구하며 `[gui]` 호환 경로를 유지한다.
- 당시 로컬 관련 검사: `test_document_core`, `test_radioss_editing`, `test_project_roundtrip`, `test_cli_workflow`, `test_application_contracts`, `test_common_widgets`, `test_rad_provider`, `test_gui_document_flow` **70 passed, 1 skipped**. skip은 Windows에서 대소문자만 다른 두 파일을 만들 수 없는 기존 검사다. 동작 중심 검토의 통과는 원요구 전체 충족을 증명하지 못했다. 이 수치를 기존 원격 CI 전체 보장으로 해석하지 않는다. setuptools backend wheel 생성도 성공했다. 깨끗한 설치형 배포 검증은 이번 범위가 아니다.
- A7: 설치된 Windows Segoe UI/Malgun 글꼴을 QA 프로세스에 로드한 Qt offscreen 정상/좁은 창·오류/벡터/곡선 렌더를 작성자와 독립 검토자가 확인하고 수정했다. `docs/gallery-preview.png`는 그 미리보기다. **실제 Windows 입력·100/150/200% DPI·도킹 이동/재시작 배치·VTK 조작은 미확인**이다. 실제 Qt/VTK 프로세스의 창 `52953454`(two_shell_plates_0000.rad — CAELab Prep)는 Windows 창 목록에 나타났지만, `cua.getApp`의 앱 접근 승인이 시간 초과됐다. 승인이 완료되지 않은 상태이며 UI 입력/캡처는 실행하지 않았고 우회/재시도하지 않았다. 최종 창 목록에는 테스트 창이 남아 있지 않다.
- 세션 공유 URL: 공유 도구가 `Thread sharing permissions or account policy could not be determined`를 반환해 생성하지 못했다. 검증된 공유 URL이 없어 임의 링크를 만들지 않았다.

### 2026-10-31 원범위 여섯 항목 보완과 재리뷰

`6a2c96e` 다음 로컬 보완이다. 구현팀은 파일 소유를 나눈 Sol/high 두 명과 통합자, 검증팀은 Sol/high, **리뷰팀 하나**에는 요구사항 비판 Astra/xhigh·구현 옹호 Sol/xhigh·코드/회귀 위험 독립 검토 Sol/high를 두었다. 원래 충족한 편집/보존 기능은 인정하고 잘못된 범위 확대는 반박했으며, 유효 지적은 코드/동작 수정 뒤 재검토했다. 새 로컬 sidebar 세션을 생성한 것이 아니다.

| 원범위 누락 | 실제 보완과 확인 |
|---|---|
| 선택 계약 | 공통 `SelectionProvider.select/active_object`를 두 provider와 창에서 사용. 기존 native PART→표시 요소 하나의 관계로 트리·읽기 전용 속성·모든 관련 요소 강조 연결. 문서 epoch·문서 revision·resource token·projection_revision이 있는 pick/clear를 검증해 같은 ID로 재열어도 이전 pick 거부. 스칼라 변경 뒤 투영을 재생성하지 않고 stamp 갱신. 원 ID/중복 ambiguity 검사 보존 |
| 공용 Action/셸 | 두 창이 `ActionRegistry` identity/capability/context/state와 `FileEditCoordinator` 초안/저장/닫기 절차를 실제 공유. RAD도 공용 ViewportFrame에 renderer 주입. RAD 자동 Apply와 중립 수동 Apply 차이는 유지. 외부 승인 선택은 초안을 보존하고 Apply/Revert 후 반영 |
| 디자인 원본 | `design/tokens.py`를 QSS·SVG·위젯 수치·plot 색의 실제 원본으로 사용. 기존 아이콘 보존, 부족한 section/load/contact/set/select/result/job만 추가. RAD의 실제 카드 범주를 의미 아이콘에 매핑 |
| 참조 입력 | 중립 재료의 Associated curve에서 표시명–typed ObjectRef 후보를 선택해 같은 명령/Undo/save/reopen 경로 사용. 잘못된 문서/자원/종류/대상 거부와 부분 변경 없음 확인. 중립 codec v2 저장/v1·v2 읽기, 기존 RAD v1 유지. 솔버 구성 법칙이나 B 모델 관계 일반화 아님 |
| 카탈로그 | 부품별 의미 키·용도·소스·실제 소비 장면·상태·출처/허용 조건과 조작 가능한 상태/입력 장면 제공. 툴바 Browse component catalogue / View / Ctrl+Shift+G로 발견·탐색. 재료/곡선 화면은 조합 사용 예로 구분. 좁은 창에서 설명 prefix가 가려지던 현상은 스크롤 가능한 plain-text 설명으로 수정 |
| RAD 닫기 | invalid draft 또는 dirty일 때 Save/Discard/Cancel을 먼저 질문. Discard는 검증 없이 명시 폐기, Save만 검증, Cancel/Save 실패는 창/초안 보존. 모달 focus-loss 자동 적용·중첩 close·첫 비동기 Save와 실패 복원을 수정/확인 |

보완 당시 여덟 관련 suite는 **99 passed, 1 skipped**였다. 이후 실제 Windows 검증에서 발견한 좁은 카탈로그 결함을 공용 스크롤로 고쳤고, Qt 테스트 설정을 명시적 임시 INI로 격리했다. 최종 로컬 여덟 suite는 **100 passed, 1 skipped / 12.38s**, process exit0, 종료 뒤 widget/worker 모두0이다. JUnit은 `.test-tmp/final-isolated-settings-verification.xml`이다. skip은 대소문자만 다른 파일을 만들 수 없는 Windows 파일시스템 조건이다. 무관한 Gmsh 로컬 재검사는 하지 않았다.

CI workflow는 기존에 빠졌던 application contracts/RAD provider를 core matrix에, common widgets를 Qt job에 포함했다. 현재 수집 기준 core 59건(각 Linux/Windows), Qt 42건과 기존 CAD job이다. 첫 PR CI에서 Qt41 통과 뒤 interpreter 종료 SIGSEGV가 발생했고, 살아남은 테스트 창을 명시 파괴한 `c23149e`의 push `41172805733`과 PR `41172808346`은 네 job이 모두 정상 종료했다. 이후 `0952d66`은 push 전체 통과/PR Qt42 정리 중 exit139였다. 실제 객체 그래프에서 top-level로 열거된 12개는 Gallery가 소유한 Qt 내부 메뉴/popup이었다. fixture를 Python 소유 root만 정리하도록 고치고 자식까지 모두 삭제됐는지 검사는 유지했다. 로컬 Qt42/exit0을 확인했으며 실제 Linux 수정 검증은 새 SHA의 push/PR CI로 판정한다. CI에 `-vv`를 넣어 실패 시 정확한 test가 남게 했다. 정확한 최종 SHA에서 CI를 통과해야 병합한다. 이전 CI `41137052412` 성공은 이전 포함 범위에 한정한다.

리뷰팀의 [요구사항 비판 근거](reviews/20261031-requirements-critic.md), [구현 옹호·반박 근거](reviews/20261031-implementation-defender.md), [코드·회귀 검토 근거](reviews/20261031-code-review.md)를 함께 보존했다. 선택 helper 우회, 닫기 순서/focus loss, 저장된 두 번째 곡선 표시, numeric PART ID alias, 외부 선택의 지연 반영, 카탈로그 설명 가림 지적을 실제 수정했다. 최종 이미지의 가림 여부에 있던 의견 차이는 동일 PNG 바이트를 다시 확인해 해소했으며, 원범위 여섯 항목에 남은 blocker는 없다.

**A7의 Windows 실제 창 검증은 별도 [실행 기록](native-windows-validation.md)의 유한 범위로 수행했다.** 허용된 자체 앱 QTest 입력과 실제 Win32 OpenGL framebuffer를 사용해 트리/속성/선택·숫자/곡선/참조·저장/닫기·도킹·새 프로세스 복원을 확인했다. 실제 애플리케이션 DPR 1/1.5/2이며 OS 모니터 DPI 설정을 바꾸거나 수동/OS SendInput 시험을 한 것은 아니다. 200% 큰 창은 화면보다 커서 실제 입력은 960×640 안에서 했다. 1320×840 렌더와 실제 화면 안의 입력을 구분한다. `docs/catalogue-preview.png`는 여전히 offscreen 미리보기이며 새 native 캡처와 혼동하지 않는다. B/C·Workbench·새 RAD 카드/Engine·고급 메셔·MCP·전체 설치 배포를 종료 조건으로 추가하지 않는다.

초기에는 CUA/sky/node_repl을 사용할 수 없어 Windows 확인을 보류했다. 이후 지원되는 로컬 실행 도구의 정식 승인을 통해 설치된 PySide6의 자체 앱 네이티브 입력 경로를 실행했다. 이전 CUA 승인 시간초과를 우회하거나 잠금 화면에 접근하지 않았다. 리뷰팀은 실제 좁은 카탈로그 가림을 발견해 수정시켰고, 설정 격리 오해·곡선 delegate 진입 방식·Windows의 큰 창 크기 제한도 증거에서 바로잡았다. 초기 설정 시험은 앱의 네 가지 레이아웃 선호값을 읽고 썼을 수 있으며 백업 없는 이전 값을 임의 복원/삭제하지 않았다. 최종 격리 실행과 pytest에서는 실제 설정 값이 전후 같았다.

최신 사용자 지시는 원범위 차단과 중요한 미검증이 해소되고 정확한 최종 SHA의 필수 CI가 통과하면 PR/main 병합을 허용하는 **조건부 승인**이다. 리뷰팀 세 명이 원요구·실제 코드·최종 native 화면/입력 근거를 대조하며 타당한 지적의 수정을 재검토한다. native 기록과 CI는 서로를 대체하지 않는다. 별도 GitHub APPROVE·보호 규칙 우회·자동 병합은 수행하지 않는다.

#### 당시 문서 정합성 작업의 범위 — 현재 수정 지시가 아님

아래는 2026-10-31 당시 문서 작업의 설명이다. 현재 문서는 병합된 구현과 N 작업표를 반영하며 이 옛 목록의 “미구현 native 생성”이나 “제품코드 변경 없음”을 현재 기능 상태로 적용하지 않는다.

- `shared-cae-foundation-plan.md`: P0–P9 번호와 A1–A8은 유지. 9절 P6/P7/P8 표의 세부 단계·선행 관계, 10절 묶음 C와 종료 상태, 12절 미확정 처리의 유한 결정을 반영한다. 단계별 실행·검사는 본 작업서에서 관리하고 기존 문서에는 링크와 묶음 표만 둔다.
- `cae-model-data-design.md`: 7절의 P6→P6a/b/c, P7→P7a/b/c 설명을 맞추고 8절 B1–B6은 그대로 유지한다. P6a/C가 B나 반복 instance 편집 완료가 아님을 명시한다. P7 일반 재메시라는 기존 문구는 P7b로 구체화한다.
- `README.md`: 현재 기능 표와 미구현 표를 계획만으로 바꾸지 않는다. 공용 기반/A/B/C의 실행계획 링크만 갱신한다. 각 묶음이 실제 완료된 뒤 현재 상태·명령을 업데이트한다.
- `DESIGN.md`: 공용 자산 목적·Workbench 책임·여러 참조 제품·native 보존 원칙은 유지. 첫 CAD 경로와 후속 고급 메시 범위만 맞춘다.
- `ARCHITECTURE.md`: 현재 Gmsh 후보/한 자원 Undo/미구현 native 생성 등 사실은 유지한다. 목표 단계 링크만 바꾸며 C 산출물을 현재 코드로 적지 않는다.
- `gui-reference-matrix.md`: 자료를 새로 무한 수집하지 않고 P0 목표 장면에 연결한다. 공개 화면 관찰과 실제 실행 검증의 구분을 유지한다.
- Workbench 연동 문서: Prep의 자원/파일/자동화 계약은 이 저장소 소유, Workbench 프로젝트/실행/결과 참조는 Workbench 소유로 연결한다. 양쪽 문서에 다른 JobManager나 공통 전역 FE 모델을 각각 계획하지 않는다.

계획 문서의 완료는 위 범위·선행 조건·산출물·검사·종료·제외가 일관되고, 현재 구현과 후속 목표를 혼동하지 않으며, Prep과 Workbench의 독립 검토에서 책임 충돌이 해소된 상태다. 이를 위해 제품코드나 새 테스트를 이번 문서 작업에 추가하지 않는다.
