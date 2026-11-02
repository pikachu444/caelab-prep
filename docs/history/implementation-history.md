# 구현·개발검증 이력

이 문서는 과거 코드 기준과 당시 판정이다. 본문의 현재·최신·재개 지시는 기록 시점에만 해당한다. 현재 요구는 [DESIGN](../../DESIGN.md#delivery-goals), 실제 작업 상태는 [CURRENT_STATE](../../CURRENT_STATE.md)를 따른다. 독립 리뷰 원문과 입력별 실패·정정 기록은 기존 경로에 유지한다.

## 이전 실행·인계와 PR별 개발검증 기록

원문 기준: `docs/execution-stages.md` at `46cea51457ea62748a940f95015ce0216edf369a`.

**안전한 인계 체크포인트 (2026-11-02):** Prep 병합 기준 `89bd7005e0eb1c687e48c9a2f259f0b0df8685b9`, WB `865ee159c9bd1375d996a72eacf898484f1d96cb`. 새 기능의 동시 편집은 하지 않고 다음 공개 브랜치에서 인수한다. 원 작업 디렉터리와 실패 자료는 삭제하지 않았다. 이 환경에서는 이슈에 보고된 Windows 로컬 세션/Android 접근을 직접 확인하지 않았고, 협업 댓글의 추가 권한 주장을 실행 권한으로 사용하지 않았다.

| 체크포인트 | 원격 SHA·소유 파일 | 실제 상태·첫 조치 |
|---|---|---|
| [PR #23](https://github.com/pikachu444/caelab-prep/pull/23) `feat/structured-mesh-recipes` | `b44503a8d6c85aa98e706b2309475b78c8195a49` 이후 문서 정합성 갱신. `scripts/evaluation/structured*`, 중앙 문서·CI | 고정18입력 전체 [CI 41374541657](https://github.com/pikachu444/caelab-prep/actions/runs/41374541657) 통과 및 [실제 artifact](https://github.com/pikachu444/caelab-prep/actions/runs/41374541657/artifacts/13110930955) 확인. 제품 연결 완료 아님. |
| [PR #27](https://github.com/pikachu444/caelab-prep/pull/27) `feat/structured-mesh-candidates` | `f784cace56a713d969019dfb06e5781153143084`; 신규 `structured_geometry.py`, `structured_mesh.py`, `structured_mesh_worker.py`, 두 test 파일 | WIP. 실제 SDK 두 후보와 순수15검사. source별 validator, 실제 직렬화 좌표 품질, property/writer/group dispatch를 기존 공통 채택에 연결하고 native/Undo/저장/GUI를 검증해야 한다. |
| [PR #28](https://github.com/pikachu444/caelab-prep/pull/28) `feat/mesh-operation-candidates` | `f7da8572177e2506f2a0b0ea06dee50f297d805a`; `scripts/evaluation/mesh_operations/` | WIP. opaque document epoch/CAS·sparse delta·품질/참조 영향. 독립 리뷰 후 sparse native 행 codec·다중 source stale 의존성·단일 execute_many에 연결한다. 전체 NODE 블록 복사나 최근접 하중 이전 금지. |
| [PR #26](https://github.com/pikachu444/caelab-prep/pull/26) `test/bounded-kernel-evidence` | `a04b34c6c0caddd12ff2917811c914fab3087bad`; N23/N26 실험 코드·공개 입력/로그·정정 판정 | 연구 실증 보존. N23 공식 예제/F2/접합과 제품 연결, N26 prism 정상 종료·질량 분포/혼합 interface·native 적합성은 미완료. |
| N11 추가 실행 | [기존 근거와 두 고정 입력 계획](../validation/n11-remaining/acceptance-gap-and-input-plan.md) | 기존 as1 GUI·native 재사용. 열린 shell·face/volume local size·맞닿은 두 solid의 conformal/independent를 20k–100k·q≥0.1·120초로 실제 실행한다. 제안 수량은 아직 실측 아님. |

공통 계약 `session.py`/`rad_provider.py`/`document.py`/storage·deck·mesh_candidates는 인수자 한 명이 소유한다. PR #27의 `MeshCell.kind`를 전역 확장하면 기존 tri/tet 품질 검사를 우회할 수 있으므로 출처별 허용 family를 유지한다. N18의 stale 관계는 여러 source/generation을 기록하도록 버전을 이행해야 한다. 젠클스의 `scripts/windows/`는 동결 보고 상태이며 인수 측이 담당 교대를 확인한다. 실제 Windows 실행은 정확한 최종 Prep/WB SHA 쌍과 권한 범위에서 별도 기록한다.

**새 세션의 실행 순서:** README → DESIGN의 R/T/G → 이 표 → 관련 기술 절/코드를 읽고 실제 HEAD와 dirty를 확인한다. N01/N02/N15/N16/N19/N20/N21의 병합 근거를 유지하고, 병합된 N16 transaction을 재사용해 N18과 제한 recipe N22/N24/N25를 진행한다. N17은 동일 100만 요소의 미달 항목을 병행 개선한다. 원제품/Windows 접근 대기 동안 독립 가능한 구현과 배포 준비를 계속한다. N17 계측과 공통 계약 개선은 한 편집자가 조율한다. IPC→MCP와 Workbench 소유 W3의 선행 관계를 지킨다. 조건부 다섯 항목은 각각 F0–F2를 먼저 판정한다. Windows 실측을 나중에 일괄 한다는 사용자 지시는 유지한다.

**게시 묶음 독립 검사:** `published-work-inspection-20261102-01`의 개발검증자료는 PR17 `323954f`의 별도 cloud 검사 573 passed/83 skipped, OCP 전용 관련 107건과 공식 OpenCourant, 독립 MSH 두 형식의 ID·출처·quad 차단, WB PR55 관련 33건과 실제 두 단계 실행을 보고했다. 중복을 합산하지 않는다. 이 자료가 확인하지 않은 X11·Windows·8원제품 검증을 이 결과에 포함하지 않는다. 이 결과는 N01/N02/N15/N21의 게시 묶음 근거이며 전체 26개 합격이 아니다.

**전체 검토 대조(2026-11-02):** `full-plan-review-20261102-01`의 R1–R4와 아홉 항목은 현재 구현을 폐기하지 않고 위 같은 N 행에 반영했다. N01/N02/N15의 요구는 게시 코드와 실제 검사로 대조했고 N16–26의 추가 완료 조건은 유지했다. 반박하는 핵심 완료 기준은 없다. 최신 원제품 버전이나 무료 배포 가능성은 실행/사용권 확보와 구분하고, 현재 Linux X11 성공을 독립 검토 환경의 X11 실패에 소급하지 않는다. 별도 cloud clone의 개발검증보고에 기록된 430/78, OCP93·modeling8, EGL1, solver3, SDK recipe·staging·wheel 결과는 해당 baseline의 독립 증거이며 미게시 코드나 현재 PR 전체 통과로 합산하지 않는다.

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

최신 사용자 지시에 따라 로컬의 프로그램별 UI 작업을 main에 **보존 통합**하고 로컬·원격 저장소를 정리한다. 이는 제품 완성, A7 납품 또는 상용 프로그램 동등성 승인이 아니다. 이 최신 승인은 보존 통합에 한해서 이전 게시·병합 보류를 대체하며, 실제 Windows/GPU 확인 및 제품 품질 납품 보류는 유지한다. 아래 체크박스는 당시의 미해결 목록을 보존한 것이다. 현재 잔여 수는 위 N 표만 사용하며 이 기록을 다시 세거나 현재 상태로 수정하지 않는다. [현재 구현과 차이](../ui-reference-variants.md)를 함께 대조한다.

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
- A7: 설치된 Windows Segoe UI/Malgun 글꼴을 QA 프로세스에 로드한 Qt offscreen 정상/좁은 창·오류/벡터/곡선 렌더를 작성자와 독립 검토자가 확인하고 수정했다. [이전 gallery-preview.png](https://github.com/pikachu444/caelab-prep/blob/46cea51457ea62748a940f95015ce0216edf369a/docs/gallery-preview.png)는 그 미리보기다. **실제 Windows 입력·100/150/200% DPI·도킹 이동/재시작 배치·VTK 조작은 미확인**이다. 실제 Qt/VTK 프로세스의 창 `52953454`(two_shell_plates_0000.rad — CAELab Prep)는 Windows 창 목록에 나타났지만, `cua.getApp`의 앱 접근 승인이 시간 초과됐다. 승인이 완료되지 않은 상태이며 UI 입력/캡처는 실행하지 않았고 우회/재시도하지 않았다. 최종 창 목록에는 테스트 창이 남아 있지 않다.
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

리뷰팀의 [요구사항 비판 근거](../reviews/20261031-requirements-critic.md), [구현 옹호·반박 근거](../reviews/20261031-implementation-defender.md), [코드·회귀 검토 근거](../reviews/20261031-code-review.md)를 함께 보존했다. 선택 helper 우회, 닫기 순서/focus loss, 저장된 두 번째 곡선 표시, numeric PART ID alias, 외부 선택의 지연 반영, 카탈로그 설명 가림 지적을 실제 수정했다. 최종 이미지의 가림 여부에 있던 의견 차이는 동일 PNG 바이트를 다시 확인해 해소했으며, 원범위 여섯 항목에 남은 blocker는 없다.

**A7의 Windows 실제 창 검증은 별도 [실행 기록](../native-windows-validation.md)의 유한 범위로 수행했다.** 허용된 자체 앱 QTest 입력과 실제 Win32 OpenGL framebuffer를 사용해 트리/속성/선택·숫자/곡선/참조·저장/닫기·도킹·새 프로세스 복원을 확인했다. 실제 애플리케이션 DPR 1/1.5/2이며 OS 모니터 DPI 설정을 바꾸거나 수동/OS SendInput 시험을 한 것은 아니다. 200% 큰 창은 화면보다 커서 실제 입력은 960×640 안에서 했다. 1320×840 렌더와 실제 화면 안의 입력을 구분한다. [이전 catalogue-preview.png](https://github.com/pikachu444/caelab-prep/blob/46cea51457ea62748a940f95015ce0216edf369a/docs/catalogue-preview.png)는 여전히 offscreen 미리보기이며 새 native 캡처와 혼동하지 않는다. B/C·Workbench·새 RAD 카드/Engine·고급 메셔·MCP·전체 설치 배포를 종료 조건으로 추가하지 않는다.

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


## 초기 코드 진단과 보완 계획

원문 기준: `ARCHITECTURE.md` at `46cea51457ea62748a940f95015ce0216edf369a`.

2026-11-02의 현재 납품 기준은 [DESIGN의 R1–R4/T1–T6/G0–G4](../../DESIGN.md#delivery-goals)를 따른다. 병합 기준은 Prep main `89bd700`(PR #17/#18/#20/#21/#22/#24/#25)와 Workbench main `865ee15`이며, 아래 설명은 PR #21에서 병합한 N19/N20 구현을 포함한다. Workbench PR #55 최종 `a328253`은 실제 두 입력과 필수 CI를 통과해 병합했으며 전체 납품 완료가 아니다. 아래 출발점 표는 `f4d12d0` 진단 기준이며 현재 구현은 이어지는 PR #15 변경 설명과 [남은 작업표](../execution-stages.md#remaining-work)를 따른다. 원제품 충실도와 Windows 검증은 구현 자체와 별도로 남는다.

| 보존할 구현 | 실제 한계 | 현재 목표를 위해 필요한 보완 |
|---|---|---|
| `Document/CommandDispatcher`, typed ref, 초안·Undo·저장 | 기존 단일 resource 상태 변경 중심 | G1의 객체 생성/삭제·파트 참조 할당과 다중 자원 원자 변경, 실패 시 전체 복원 |
| `RadProvider`, 원문 patch·INCLUDE·native 출력 | 일부 기존 필드 편집, PART 관계는 읽기 전용 | G1/G2의 새 native 객체·ID/참조 생성, G3의 Starter/Engine 출력; 원문 보존 경로 유지 |
| `CurveSession`, 공용 속성·표·곡선 위젯 | 재료 하나와 곡선 목록의 제한 host | sample은 개발용 유지; 제품의 다중 재료·단면·조건 모델과 실제 곡선 참조는 domain provider가 소유 |
| `reference_components`의 composition과 8 adapter | 공통 Edit 중심 명령, 배치·일부 확정 방식 차이 | T1–T6 과업별 명령 진입·선택·확정/취소·오류 복구; 공용 명령/문서는 공유, host별 모델 사본 금지 |
| `gmsh_backend`의 별도 worker | 독립 후보 생성이며 GUI 문서와 단절 | G3 품질·채택/교체·관계 영향·Undo·저장 연결 |



## 2026-10-29 공용 기반의 출발점

원문 기준: `docs/shared-cae-foundation-plan.md` at `46cea51457ea62748a940f95015ce0216edf369a`.

## 2. 확인한 출발점

아래는 2026-10-29 원계획의 출발점 기록이다. 이후 분리된 코드와 현재 지원 범위는 ARCHITECTURE/README로 확인하며, 이 표를 현재 코드의 전수 조사 결과로 읽지 않는다.

| 확인 대상 | 확인한 사실 | 계획에 반영할 점 |
|---|---|---|
| README의 `native-editor.png` | 당시 자체 Qt/VTK RAD 편집기. 두 셸과 소수 속성을 표시하는 초기 실행 화면 | 구현 기록으로 유지한다. 목표 외관이나 갤러리의 대표 장면으로 고정하지 않는다 |
| BeidPrep 1.0.1 | Windows에서 열기·3D·저장·재열기 수행. GUI 재료 수정은 미완료, 저장 조건 변화 발견 | 외관 참고와 모델 보존 검증을 구분한다. 상세는 [시험 기록](../beidprep-evaluation.md) |
| BeidPrep 2.0 / Naksha | 이 계획에서 실제 실행 검증한 제품이 아님. Naksha의 과거 확인은 공개 화면·영상 조사 | 공개 자료의 외관 참고와 성능·기능 실측을 혼동하지 않는다 |
| `ui/theme.py` | 자체 SVG 경로와 단일 스타일 문자열. 트리 최소 높이 26px, 입력 상하 padding 등 | 기존 크기를 공용 표준으로 복제하지 않고 참조 화면과 비교해 토큰을 정한다 |
| `ui/main_window.py` | Action·도킹·트리·폼·입력 초안·파일 작업·종료 확인을 함께 소유 | 화면 부품과 문서 수명 주기를 나누되 기존 편집 보존 장치를 함께 옮긴다 |
| `cae_core/document.py` | Qt·솔버를 모르는 문서·자원·명령·선택·저장 기준점. 당시 명령은 한 자원 상태의 Undo/Redo | 기존 코어를 확장 출발점으로 사용한다. 모든 CAE 의미나 다중 자원 트랜잭션이 이미 있는 것으로 보지 않는다 |
| `application/session.py` | RAD 카드·INCLUDE·메시 투영·`.caeprep` 저장을 다루는 당시 PrepSession | 공용 세션의 작은 계약과 RAD 구현을 분리한다. 일반적인 클래스 이름만으로 공용화됐다고 판단하지 않는다 |
| `ui/viewport.py` | VTK 메시 표시·카메라·원본 ID 역매핑·단일 절점/요소 선택 | 렌더러와 공용 뷰포트 프레임을 구분하고 선택·원 ID 보존을 유지한다 |

당시 구조에서 지적한 문제는 여백만이 아니었다. RAD 카드 분류와 공용 트리, 필드 파싱과 속성 위젯, 파일 형식과 문서 수명 주기의 결합을 줄이는 것이 이행 과제였다. 분리된 코드의 존재와 실제 과업을 완수하는 재사용 기반의 완성은 별도로 검증한다.



## 첫 묶음 A의 당시 완료 조건

원문 기준: `docs/shared-cae-foundation-plan.md` at `46cea51457ea62748a940f95015ce0216edf369a`.

### 과거 묶음 A의 완료 조건 기록

묶음 A는 기존에 정의한 **공용 GUI·문서/명령/선택/속성/저장 계약의 첫 배포 범위(P0–P3)**다. 아래 A1–A8은 당시 보고와 증거를 대조하기 위해 보존한다. 여기의 ‘두 작업 화면’·‘기존 FUNCT 점’·‘고정한 참조 영역’은 현재 G1–G4의 요구 범위를 제한하지 않는다. 과거 특정 확인이 통과했더라도 현재 커밋과 현재 과업의 완료 증거는 별도로 확보한다.

| 조건 | 확인할 실제 결과 |
|---|---|
| A1. 범위 고정 | 구현 전에 참조 제품 비교의 채택/보류, 목표 조합 화면·상태, 지원 필드/형식·사용 자료·Windows 환경을 짧게 고정. 필수 자산과 비필수 보류를 구분 |
| A2. 실물 공유 | 토큰·아이콘·Action·트리·속성·단위/벡터·기본 표/plot·도킹·선택 연결을 갤러리와 RAD 앱이 같은 코드로 사용. 동일 부품을 앱마다 복제하지 않음 |
| A3. 두 작업 화면 | 기계 전처리 작업 공간과 재료/곡선 공간이 실제 데이터로 동작. 선택→값 수정→오류→Undo가 연결되고 미구현 도구를 작동하는 것처럼 채우지 않음 |
| A4. 실제 파일 범위 | 소형 시험 외에 다중 부품 RAD 한 개와 형상이 다른 지원 입력 한 개를 같은 열기 경로로 처리. 특정 이름·개수에 맞춘 분기 없이 현재 지원 필드와 기존 FUNCT 점 편집 |
| A5. 저장 보존 | RAD 편집→Undo/Redo→저장→프로세스 재시작·재열기→native 출력. 바뀐 값과 미편집 구속/IPLAS·미지원 원문·해결된 INCLUDE 관계 보존. 중립 재료/곡선도 RAD import 없이 자체 작업 문서로 재열기 |
| A6. 실패·초안 | 불완전 수치·잘못된 값·외부 수정·저장 실패·닫기 취소에서 확정 값/초안이 조용히 사라지지 않음. 실패한 명령의 부분 변경 없음 |
| A7. 외관·배치 | A1에서 고정한 참조 영역과 실제 Windows 화면을 비교. 긴 이름/한글·값/단위·상태·아이콘·정렬이 읽히고 잘리지 않음. 과도한 행/입력 높이·불필요한 고정 빈 패널 문제를 해결. 정한 배율·창 크기·도킹 이동·재시작 배치 복원 통과 |
| A8. 의존 경계 | 기본 부품·곡선 장면은 VTK 없이 실행, 메시 장면만 renderer 사용. 공용층이 RAD/Gallery 자료를 import하지 않으며 기존 GUI/CLI 실행 경로 유지 |

과거 외관 A7 역시 문서의 체크 표시만으로 통과를 입증할 수 없다. 고정한 장면의 실행 화면, 작성자·별도 검토자가 실제 확인한 범위와 발견한 불일치를 대조한다. 과거 리뷰가 존재한다는 사실을 현재 8방식의 동일 과업·Windows 품질 검토로 전용하지 않는다.

이전 계획에서 두 번째 레이아웃과 고급 곡선을 A의 후속으로 분리했던 범위는 역사적 기록이다. 현재는 G1의 8방식과 G2의 곡선 과업을 제외하는 근거로 사용할 수 없다. 반복 instance, 일반 재메시, 전체 물리/요소, MCP·후처리 및 대용량 구조의 범위는 각 목표·후속 계획에 명시하고 현재 과업에 필요한 관계·명령까지 일괄 연기하지 않는다.



## UI 재구현의 독립 기록

작성자·검토·도구 실패와 당시 제한은 [별도 UI 이력](ui-rebuild.md)에 보존한다. 당시 실패를 이후 실행의 성공으로 바꾸지 않는다.

## 2026-10-29 Workbench 원검토

### 2026-10-29 소스 조사 기록

다음 표의 파일 위치·의존성·미구현 설명은 원검토 SHA에 대한 역사적 사실이다. 특히 공용 widget extra, 채택, 공용 셸이 없다는 당시 설명은 위 현재 구현으로 대체됐으며 현재 잔여로 다시 세지 않는다.

| 대상 | 실제 코드에서 확인한 사실 | 해석/한계 |
|---|---|---|
| WB 실행 | `apps/workbench_qt/__main__.py:16–34`가 PySide6 QApplication을 만들고 ProjectWindow(Workbench())를 연다. `run_workbench.bat`는 자체 .venv와 editable GUI/RAG 설치를 사용한다 | FreeCAD 내장 Python/Qt를 호스트로 쓰지 않는다. 사용자의 실제 Windows 설치 버전은 당시 측정하지 않음 |
| WB 의존성 | `pyproject.toml`: Python>=3.11, PySide6>=6.6(Python3.11이면 <6.12), vtk>=9.3; numpy/filelock 기본 | 선언 범위이며 lockfile/검증된 모든 조합 목록이 아니다 |
| Prep 의존성 | `pyproject.toml`: Python>=3.11, 기본 의존성 없음; GUI PySide6>=6.6(Python3.11 <6.12, 3.12이상 <6.13), vtk>=9.4,<10; cad=gmsh==4.15.2 | 당시 GUI extra는 VTK를 함께 설치한다. VTK 없는 공용 위젯 extra는 계획이다 |
| CAD host | WB `connections.py:35–81,252–283`: FreeCAD=.FCStd 외부 GUI, PrePoMax=.pmx/STEP 등, Gmsh=mesh, ParaView 결과 GUI. `jobs.py:698–709`가 Popen 소유 | FreeCAD 내부 Qt/PySide 버전은 WB 호환성의 직접 전제가 아니다. 향후 내부 embedding 요구가 생기면 별도 조사 |
| WB 정본 | `project.py:31–143`: NativeProject/ProgramNode/FileReference/Connection. input/document/output 분리, 파일 SHA 개정·하류 invalidation. JSON schema v3와 atomic 저장 | WB가 소유하는 것은 프로그램·파일·연결·실행 관계. native FE 문서 정밀 편집 정본은 전처리 프로그램 |
| 보조 모델 | `model/schema.py`: StructuralModel에 inline mesh/재료/하중/단계가 있다. `model/AGENTS.md`와 DESIGN은 보조 converter/검사 모델로 제한 | 이 기존 스키마를 Prep ModelDoc로 치환하거나 모든 native 문서를 거쳐 쓰게 하지 않는다 |
| WB 명령/Undo | `workbench.py` facade가 project·launch·jobs 명령을 모은다. `mdo/service.py:443–464` configure는 immutable revision을 새로 만들고 persist. `875–907` apply/undo는 백업 INP의 current-design transaction | WB 전체에 Prep식 일반 Undo dispatcher가 있다는 근거는 없다. MDO 설정 Apply와 현재 설계 적용 Undo를 혼동하면 안 됨 |
| Prep 코어 | `cae_core/document.py`는 Qt/VTK/솔버 import 없는 Document/Resource/CommandDispatcher/ChangeSet/SelectionRef. 한 resource 상태 snapshot Undo/Redo와 expected_revision 검사 | stdlib만 쓰는 재사용 가능한 출발점은 사실. 복합 자원 변경·대용량 배열 history·모든 CAD/FE 의미는 미구현 |
| Prep 세션/codec | `application/session.py:15`가 DeckResource import. RAD 카드·INCLUDE·mesh_view·.caeprep 저장/출력을 직접 소유. ZIP reader는 radioss-deck만 허용 | PrepSession 또는 .caeprep v1 전체를 중립 세션/공용 archive codec으로 직접 쓰지 않음 |
| UI 자산 | WB `theme.py`는 dark/light semantic palette·QSettings·listeners, `icons.py`와 SVG 묶음. Prep `ui/theme.py`는 작은 자체 SVG+단일 light QSS. Prep main_window는 RAD 라벨/카드/세션 작업을 함께 소유 | 당시 작은 Prep theme를 WB 전체 theme에 덮어쓰지 않는다. 공용 widget/shell/gallery는 목표 모듈로만 존재 |
| VTK | WB viewport는 StructuralModel/ResultSet, Prep viewport는 mesh projection/source-ID pick에 결합. 둘 다 QVTKRenderWindowInteractor 사용 | 같은 VTK 도구를 쓴다고 viewport API·선택 의미·배열 소유가 같은 것은 아님 |
| 메시 | Prep gmsh_backend는 Gmsh import 없이 subprocess worker 호출; worker만 SDK import. XAO/MSH/메타데이터·원본 hash·UUID/개정·unit 제공 | candidate assets이며 RAD GUI 문서 채택 명령·하중 재연결 미구현. 당시 backend는 sys.executable을 쓰므로 별도 venv 선택도 자동 구현된 것이 아님 |
| Jobs | WB Workbench.jobs/JobManager와 RunStore가 솔버·MDO 제출/취소·로그·입력 사본·결과 판독 소유. Prep는 파일 QRunnable과 Gmsh subprocess/cancel/timeout이 당시 구현 | 공용 Job protocol/전체 Prep meshing job service는 목표. WB jobs를 Prep 작업체계로 즉시 대체할 이유 없음 |
| 자동화 | Prep CLI는 같은 세션 클래스를 매 호출 새로 만듦. `cli.py`가 열린 GUI IPC client가 아니라고 명시 | CLI 실행이 이미 열린 Prep 문서를 제어하지 않음. MCP/IPC 구현됨 주장 금지 |

원검토 당시 WB CURRENT_STATE에는 Linux Python3.12.14/PySide6 6.12.0/VTK9.7.1 검사와 과거 Windows Python3.13.5/Qt6.9.1 기록이 있다. 이는 해당 기록의 환경이며 현재 사용자 설치 또는 Prep+WB 통합 조합을 직접 측정한 결과가 아니다. 2026-10-29 검토는 source read였으며 GUI·실솔버·Windows·package import를 실행하지 않았다. 이후 W1/W2 실행 근거는 위 현재 상태와 구분해 기록한다.

## 2026-11-02 당시 원제품 접근 조사 요약

아래는 cloud/Linux 조사 환경의 당시 설명이다. Wine 부재와 미설치 판단을 현재 Windows PC의 설치·사용권 상태로 적용하지 않는다. 현재 비교 판정은 CURRENT_STATE의 N03–N10을 따른다.

| N | 당시 조사 기록 |
|---|---|
| N03 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 2026-11-02 공식 trial/학생 자격 경로와 2026 Linux 지원 환경을 확인했으나 사용권·설치본이 없다. 사용자 2024.1·참고 장면 2025/2025.1·현재 배포 안내 2026을 구분해 같은 T1–T6를 고정한다. [접근 근거](../ui-reference-variants.md#product-access). |
| N04 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** GPLv3 공개 ZIP에 유료 사용권 장벽은 없지만 Windows/.NET4.8 또는 Wine 실행이 필요하며 현재 Wine도 없다. 2.5.0 기준판과 2.6.0/3.0 RC2를 구분한다. 실제 생성·할당·취소를 수행하며 library/contour 그림으로 대체하지 않는다. [접근 근거](../ui-reference-variants.md#product-access). |
| N05 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 무료 Windows/Linux 데스크톱 제품이다. 공식 무료판 버튼이 이름·업무 이메일 신청 폼으로 이동함을 확인했고 제출하지 않았다. 설치본/실행 build를 받은 뒤 비교한다. 빈 Details 그림으로 확정 시점·취소를 추정하지 않는다. [접근 근거](../ui-reference-variants.md#product-access). |
| N06 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 정식 사용권/설치본이 없고 무료 LE2026도 Windows·1000노드·개인교육용 제한이 있다. 허용된 사용 경로를 정한 뒤 Property→재료→단면→할당·단위·오류/취소와 RAD 물리 의미를 대조한다. [접근 근거](../ui-reference-variants.md#product-access). |
| N07 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 6.4는 현재 Ubuntu24.04를 지원하지만 Access에 연결된 구독 또는 발급된 trial/설치본이 없다. 6.3 참고판과 구분해 비교한다. RAD 출력·계산을 COMSOL Build/Compute로 세거나 Runtime 앱으로 Model Builder 편집을 대체하지 않는다. [접근 근거](../ui-reference-variants.md#product-access). |
| N08 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 공식 2026R1 설치/Windows 경로와 현재 14일 trial 발급 절차를 확인했다. 실행 환경·사용권은 미확보, 신청은 미제출이다. 같은 한 버전의 연속 작업으로 대조하며 교육자료를 이어 붙이지 않는다. [접근 근거](../ui-reference-variants.md#product-access). |
| N09 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **실행 미확인.** 공식 2026R1 Windows 설치와 현재 14일 trial 경로는 있으나 환경·사용권이 없다. 형상/영역·재료·단위·이산화·조건·케이스의 물리 계약과 FE 작업의 대체 흐름을 정해 실제 수행한다. 비대응을 임의 N/A로 닫지 않는다. [접근 근거](../ui-reference-variants.md#product-access). |
| N10 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** **전체 작업 실행 미확인.** 2.0 beta 공식 페이지는 Windows·계정 없는 무료 다운로드를 제공한다. 실제 클릭은 다운로드 경로를 반환했지만 파일 수신/해시는 확인되지 않았고 Windows도 없다. 과거 1.0.1 소형 실행과 2.0 웹 소개를 구별하고 card 확정을 선택 APPLY에서 추정하지 않는다. [접근 근거](../ui-reference-variants.md#product-access). |

## 단계별 개발검증의 고유 기록

다음은 정리 전 코드 기준 `46cea514` 작업서의 기록이다. CSV 완료 보고의 정정과 소형 CAD 입력 규모를 보존하며 현재 상태는 N표에서 판정한다.

**당시 기록:** PR #17의 N15 구현은 RAD와 중립 앱에서 같은 CSV 파일 reader/writer, import 미리보기와 확정, export 및 덮어쓰기 취소를 제공한다. 표와 plot은 같은 초안을 사용하며, 점을 끄는 동안에는 미리보기만 바뀌고 놓을 때 한 명령/Undo로 확정한다. Escape는 취소한다. 두 곡선의 CSV·작업문서 왕복, 단위·참조 보존, RAD/VTK 없는 실행과 실제 Linux 파일 선택창을 검사했다. 최종 `323954f`의 CI 7개 job을 통과하고 main `8ff16c3`에 병합했다. Windows 및 원제품 비교는 별도 행에 남는다. **과거 보고 정정:** PR #15 당시의 CSV 완료 주장은 `paste_text` 검사를 실제 파일 입출력으로 잘못 보고한 것이며, 이번 구현의 근거로 소급하지 않는다.

**당시 기록:** tri3/tet4 후보·품질·국부 size·제한된 conformal/independent 경계·채택·참조 없는 교체·Starter/Engine은 연결됐다. 실제 solver 세 입력은 62/236/310 요소의 소형 사례다. 아래 2만–10만 요소 입력·120초 예산 및 대표 사용자 모델의 연속 native 작업은 이 소형 결과로 통과시키지 않으며 N11에서 확인한다. 외부 독립 메시 import는 N02다.
