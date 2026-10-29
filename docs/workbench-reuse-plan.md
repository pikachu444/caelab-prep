# Prep 산출물의 Workbench 재사용 계획

검토일 2026-10-29. 현재 코드에 대한 독립 검토와 후속 구현 계획이다. 아래 consumer 검증은 **후속 구현의 종료 조건**이며 이번에 실행한 실험이 아니다. 제품 코드·의존성·Workbench는 이번 문서 작업에서 변경하지 않는다. 전체 순서와 단계 종료 규칙은 [단계별 작업서](execution-stages.md)를 따른다.

기준은 `pikachu444/caelab-workbench@92ce81181396bed9bb6e3024bba62913834c2a7e`, `pikachu444/caelab-prep@5d16e81c7ec7c92499401d63208039424bf73cc9`이다. GitHub connector로 두 main을 읽었고 조사 시점에는 모두 기준 SHA와 일치했다. 이후 main이 움직여도 이 검토의 코드 사실은 이 SHA에 한정한다.

## 1. 먼저 확정할 결론

Prep의 정식 산출물은 공용 GUI 자산·공학 위젯·앱 셸·갤러리·문서/모델 데이터·저장·메시 작업 기반이다. OpenRadioss/OpenCourant는 첫 적용 대상이다. Workbench는 그 자산의 소비자가 될 수 있지만 현재 CalculiX/PrePoMax·FreeCAD FEM 호환, MDO/PDE·연구·실행·결과/토론 소유를 Prep로 옮기지 않는다.

**현재 Workbench는 FreeCAD 안에서 실행되는 workbench 플러그인이 아니다.** 독립 Python/PySide6 앱이며 FreeCAD를 별도 실행 파일로 연다. 따라서 Qt5/Qt6 혼재를 현재 두 저장소의 확정 장애로 쓰면 틀리다. 둘 다 PySide6인 것은 직접 재사용의 가능성을 높이지만 실제 고정 조합의 호환성을 증명하지 않는다.

1차 계획은 (W1) 기존 MDO 변수 입력 셀 일부에 공용 숫자/단위 편집 부품을 연결하고 (W2) 독립 Prep의 문서/내보내기 파일을 Workbench 프로그램 노드로 연결하는 두 유한 소비자다. W1에 Prep Document/Dispatcher를 만들지 않으며 W2에 전체 RAD 솔버 실행을 끼워 넣지 않는다. 호환성 조사에서 직접 연결할 수 없다고 판정되면 W1은 확인한 원인과 함께 보류하고 W2를 진행한다. 파일 연결의 성공을 위젯 재사용 성공으로 바꾸어 보고하지 않는다.

## 2. 현재 코드 사실과 확인하지 않은 것

| 대상 | 실제 코드에서 확인한 사실 | 해석/한계 |
|---|---|---|
| WB 실행 | `apps/workbench_qt/__main__.py:16–34`가 PySide6 QApplication을 만들고 ProjectWindow(Workbench())를 연다. `run_workbench.bat`는 자체 .venv와 editable GUI/RAG 설치를 사용한다 | FreeCAD 내장 Python/Qt를 호스트로 쓰지 않는다. 사용자의 실제 Windows 설치 버전은 이번에 측정하지 않음 |
| WB 의존성 | `pyproject.toml`: Python>=3.11, PySide6>=6.6(Python3.11이면 <6.12), vtk>=9.3; numpy/filelock 기본 | 선언 범위이며 lockfile/검증된 모든 조합 목록이 아니다 |
| Prep 의존성 | `pyproject.toml`: Python>=3.11, 기본 의존성 없음; GUI PySide6>=6.6(Python3.11 <6.12, 3.12이상 <6.13), vtk>=9.4,<10; cad=gmsh==4.15.2 | 현재 GUI extra는 VTK를 함께 설치한다. VTK 없는 공용 위젯 extra는 계획이다 |
| CAD host | WB `connections.py:35–81,252–283`: FreeCAD=.FCStd 외부 GUI, PrePoMax=.pmx/STEP 등, Gmsh=mesh, ParaView 결과 GUI. `jobs.py:698–709`가 Popen 소유 | FreeCAD 내부 Qt/PySide 버전은 WB 호환성의 직접 전제가 아니다. 향후 내부 embedding 요구가 생기면 별도 조사 |
| WB 정본 | `project.py:31–143`: NativeProject/ProgramNode/FileReference/Connection. input/document/output 분리, 파일 SHA 개정·하류 invalidation. JSON schema v3와 atomic 저장 | WB가 소유하는 것은 프로그램·파일·연결·실행 관계. native FE 문서 정밀 편집 정본은 전처리 프로그램 |
| 보조 모델 | `model/schema.py`: StructuralModel에 inline mesh/재료/하중/단계가 있다. `model/AGENTS.md`와 DESIGN은 보조 converter/검사 모델로 제한 | 이 기존 스키마를 Prep ModelDoc로 치환하거나 모든 native 문서를 거쳐 쓰게 하지 않는다 |
| WB 명령/Undo | `workbench.py` facade가 project·launch·jobs 명령을 모은다. `mdo/service.py:443–464` configure는 immutable revision을 새로 만들고 persist. `875–907` apply/undo는 백업 INP의 current-design transaction | WB 전체에 Prep식 일반 Undo dispatcher가 있다는 근거는 없다. MDO 설정 Apply와 현재 설계 적용 Undo를 혼동하면 안 됨 |
| Prep 코어 | `cae_core/document.py`는 Qt/VTK/솔버 import 없는 Document/Resource/CommandDispatcher/ChangeSet/SelectionRef. 한 resource 상태 snapshot Undo/Redo와 expected_revision 검사 | stdlib만 쓰는 재사용 가능한 출발점은 사실. 복합 자원 변경·대용량 배열 history·모든 CAD/FE 의미는 미구현 |
| Prep 세션/codec | `application/session.py:15`가 DeckResource import. RAD 카드·INCLUDE·mesh_view·.caeprep 저장/출력을 직접 소유. ZIP reader는 radioss-deck만 허용 | PrepSession 또는 .caeprep v1 전체를 중립 세션/공용 archive codec으로 직접 쓰지 않음 |
| UI 자산 | WB `theme.py`는 dark/light semantic palette·QSettings·listeners, `icons.py`와 SVG 묶음. Prep `ui/theme.py`는 작은 자체 SVG+단일 light QSS. Prep main_window는 RAD 라벨/카드/세션 작업을 함께 소유 | 현재 작은 Prep theme를 WB 전체 theme에 덮어쓰지 않는다. 공용 widget/shell/gallery는 목표 모듈로만 존재 |
| VTK | WB viewport는 StructuralModel/ResultSet, Prep viewport는 mesh projection/source-ID pick에 결합. 둘 다 QVTKRenderWindowInteractor 사용 | 같은 VTK 도구를 쓴다고 viewport API·선택 의미·배열 소유가 같은 것은 아님 |
| 메시 | Prep gmsh_backend는 Gmsh import 없이 subprocess worker 호출; worker만 SDK import. XAO/MSH/메타데이터·원본 hash·UUID/개정·unit 제공 | candidate assets이며 RAD GUI 문서 채택 명령·하중 재연결 미구현. 현재 backend는 sys.executable을 쓰므로 별도 venv 선택도 자동 구현된 것이 아님 |
| Jobs | WB Workbench.jobs/JobManager와 RunStore가 솔버·MDO 제출/취소·로그·입력 사본·결과 판독 소유. Prep는 파일 QRunnable과 Gmsh subprocess/cancel/timeout이 현재 구현 | 공용 Job protocol/전체 Prep meshing job service는 목표. WB jobs를 Prep 작업체계로 즉시 대체할 이유 없음 |
| 자동화 | Prep CLI는 같은 세션 클래스를 매 호출 새로 만듦. `cli.py`가 열린 GUI IPC client가 아니라고 명시 | CLI 실행이 이미 열린 Prep 문서를 제어하지 않음. MCP/IPC 구현됨 주장 금지 |

WB CURRENT_STATE에는 Linux Python3.12.14/PySide6 6.12.0/VTK9.7.1 검사와 과거 Windows Python3.13.5/Qt6.9.1 기록이 있다. 이는 해당 기록의 환경이며 현재 사용자 설치 또는 Prep+WB 통합 조합을 직접 측정한 결과가 아니다. 이번 검토는 source read이며 GUI·실솔버·Windows·package import 실행을 수행하지 않았다.

## 3. 재사용 단위별 1차 분류

| 단위 | 1차 연결 방식 | 필요한 adapter/선행조건 | 금지/보류 |
|---|---|---|---|
| 색·간격·글꼴·SVG 의미 키 | 버전 있는 공용 design assets 직접 import/리소스 참조 후보 | Prep가 토큰/아이콘 registry를 소유하고 WB가 기존 semantic palette와 매핑. 출처·허용조건 확인 | light-only QSS로 WB 전체 교체, 개별 파일 복사 뒤 양쪽 수정 |
| 숫자·단위/벡터/표·곡선·오류 표시 | 공용 Qt widget/delegate + WB host-binding adapter | W1 한 영역에서 먼저 검증. widget은 draft/입력 이벤트만, domain validate/apply/save는 WB service. 공용 style은 해당 부품 subtree로 제한 | RAD MainWindow/PrepSession 통째 임베딩, QWidget이 별도 문서/history 소유, QApplication 전역 stylesheet 덮어쓰기 |
| Action·선택·앱 셸 | 작은 contracts/표현 부품 재사용, 앱별 조립 | WB의 프로그램/스터디 선택과 Prep의 modeling 선택 namespace 구분. QAction callback을 기존 WB 명령에 bind | 첫 consumer에서 모든 창/도킹/메뉴를 전면 교체 |
| 중립 data/contracts | Qt/solver-free 작은 DTO/Protocol 직접 import 후보 | 현재 cae_core와 새 contracts의 의존성 검사. resource/object/native ID·unit/revision 의미 명시 | WB NativeProject·MDO study·PDE 문서를 Prep Document 하나에 흡수, StructuralModel 강제 이행 |
| Document/CommandDispatcher | Prep standalone/gallery/곡선 앱에서 정본으로 사용 | WB 안에서 신규 모델 편집기를 정말 만드는 별도 결정 때만 단일 owner로 연결 검토 | W1 기존 MDO 값을 두 Document/Undo stack으로 복제 |
| archive 기반 | 공통 atomic replace/manifest/version/resource packaging 추출 후 codec 주입 | RAD v1 reader/export를 보존. WB project/run/study JSON의 기존 version/locking 유지 | .caeprep v1을 WB project 저장형식으로 채택, RAD payload 강제 |
| Gmsh worker | 별도 process + XAO/MSH/중립 metadata 파일 교환 | meshing job ID·실제 결과 경로·취소/실패·source hash. WB에서 호출한다면 outer request와 Prep meshing job handle 연결 | GUI에 gmsh/OCC native 객체 전달, Gmsh mesh를 완전한 FE 모델로 인정 |
| Mesh adoption | Prep 모델 세션의 명시적 command | candidate resource 검증·target doc epoch/revision·조건 영향·단위·오래된 explicit set/pick 거부 | WB가 배열을 또 정본으로 소유, node 번호 같다는 이유로 재연결 |
| solver/research jobs | WB JobManager/RunStore 유지; 공용 status 표현/DTO만 adapter | solver별 snapshot/argv/result 계약. Prep 화면이 요청하면 WB service에 제출하고 run handle을 받음 | 두 관리자가 같은 PID/group/timeout/cancel을 동시에 소유 |
| 독립 Prep↔WB | W2: 프로그램 실행 + document/output 파일 참조/해시, 명시적 refresh | Prep executable/python env 설정, .caeprep 편집원본과 .rad 출력 구분 | CLI 호출을 live GUI 접속으로 표시, save=export=run 성공으로 합침 |
| 열린 Prep 제어 | 필요한 사용자 작업이 생길 때 선택적 IPC | doc/session handle·epoch·expected_revision·capability/error/job schema·접속/파일 범위 | 초기 필수 의존성, 두 프로세스가 동일 파일을 몰래 편집 |

### 현재 RAD 실행의 구체적 후속 장애

WB `native/adapter.py`는 OpenRadioss/OpenCourant adapter를 등록하지만 등록은 끝단 완료가 아니다. `jobs.py:_run_native:278`는 모든 solver에 `input_snapshot.snapshot_input()`을 호출한다. 이 코드는 INP `*INCLUDE` 문법을 읽고 실행 root를 **model.inp**로 만든다(`input_snapshot.py:90–145`). 반면 `connections.py:335–343`의 Radioss request는 원 `.rad` basename을 run 폴더에 있는 것으로 구성한다. 따라서 Prep RAD 출력 등록만으로 현재 WB에서 그 파일을 정상 Starter/Engine 계산한다고 가정할 수 없다. 복수 RAD/INCLUDE와 Starter/Engine 단계·이름을 보존하는 solver-specific snapshot/launch는 WB 후속 구현이다.

`native/radioss.py`도 native A### binary animation을 해독하지 않으며 opaque payload는 partial/경고로 남긴다. 첫 파일 연결 소비자의 완료를 Radioss 결과 끝단 완료로 확대하지 않는다. 기존 CalculiX snapshot/INCLUDE·FRD/DAT·MDO 경로는 유지한다.

## 4. 소유권과 단일 변경 경로

| 자료/행동 | 단일 소유자 | 다른 앱이 받는 것 |
|---|---|---|
| CAD 원본/형상 재생성 | FreeCAD 등 CAD 도구 | STEP 등 교환파일/출처 |
| Prep 모델링 문서·조건·선택·Undo/dirty/save·mesh adoption | Prep session/ModelDoc와 앱 codec | document handle/저장된 파일·개정·경량 조회/제안 결과 |
| WB 프로그램·file graph·프로젝트 개정 | WB NativeProject/Workbench | 참조/상태. Prep가 project.json을 직접 수정하지 않음 |
| MDO 변수·response·연구 revision·current-design apply/Undo | WB MDOStudyService | 공용 widget에는 값과 단위/오류·가능동작만 제공 |
| WB가 시작한 solver/MDO/PDE 실행·input snapshot·result evidence | WB JobManager/RunStore와 각 service | run ID/status/log/result ref. Prep는 동일 solver process를 별도 submit/cancel하지 않음 |
| Prep의 import/저장/메시 worker와 채택 | Prep job/session 경계 | outer WB 작업에는 Prep job ID/결과 ref. 프로세스 종료 권한도 Prep 한 곳 |

동일 값을 두 문서에 쓰지 않는다. W1은 existing MDO service를 owner로 두고 공용 widget의 buffer를 입력 초안으로만 취급한다. WB adapter가 service revision을 확인하고 기존 configure 호출에 전달한다. Prep Document/Dispatcher/SaveState를 그 값에 새로 만들지 않는다. Prep가 소유한 모델을 WB에서 바꾸어야 한다면 향후 같은 Prep command API에 expected_revision을 포함해 요청한다.

WB의 current-design INP 적용/Undo는 기존 서비스의 파일 transaction이다. 이를 Prep modeldoc 편집 Undo로 재해석하지 않는다. Prep 문서와 export deck은 서로 다른 자료이며 INP/RAD 외부 변경을 자동 역동기화하지 않는다. 저장된 문서/출력의 개정 변화는 WB가 감지해 하류 결과를 invalidation하고 사용자에게 재export/재등록 경로를 제공한다.

## 5. 런타임·binary·패키징·라이선스 판정

두 repo의 선언 교집합은 Python>=3.11/VTK>=9.4,<10이며 PySide6은 Python3.11에서 >=6.6,<6.12, Python3.12 이상에서 >=6.6,<6.13이다. 이것은 설치 가능한 후보 범위이고 모든 조합의 GUI 호환성을 보장하지 않는다. 첫 W1은 VTK 없는 widget 경계로 제한하고, 정확한 Python/PySide6/Qt/VTK/OS/arch/module 경로를 기록한 하나의 환경에서 검사한다. package import, QApplication 수명/스레드, keyboard draft, dark/light font/scale를 나누어 확인한다. VTK viewport 통합은 후속이다.

Qt5 host를 향후 embedding할 때에는 Qt5/PySide2와 Qt6/PySide6를 같은 프로세스에 넣지 않는 것을 기본으로 한다. Qt 공식 문서는 한 executable/library의 Qt5/Qt6 혼용을 지원하지 않는다. 현재 WB가 FreeCAD host라는 뜻은 아니다. host major가 다르면 리소스 파일/별도 실행파일/IPC 경계를 사용하며 무리한 binding 교체를 선행조건으로 만들지 않는다.

Gmsh는 현재처럼 worker에 native import를 제한한다. CAD/mesh candidate 파일과 중립 metadata만 경계를 넘기고 Gmsh/OCC handle, Qt QObject, VTK 객체를 IPC payload로 사용하지 않는다. 현재 backend의 sys.executable 사용은 worker가 새 프로세스라는 뜻이며 다른 가상환경이 자동 선택된다는 뜻은 아니다. 별도 SDK 환경이 필요하면 명시적인 실행 설정과 packaging을 후속 adapter로 제공한다. OCP 테스트 입력 생성용 환경을 제품 의존성으로 끌어들이지 않는다.

두 pinned tree에 최상위 LICENSE와 pyproject license 선언은 보이지 않는다. 공개 저장소라는 사실만으로 외부 재배포 허용이 자동 확정되는 것은 아니므로 공용 패키지 배포 전에 자체 코드·SVG의 권리/라이선스를 명시하고 포함 자산의 출처를 고정한다. Prep THIRD_PARTY는 현재 바이너리를 Git/설치형 배포에 동봉하지 않는 상태를 설명한다.

| 외부 기반 | 확인할 조건과 계획상 판단 |
|---|---|
| PySide6/Qt | LGPLv3/GPLv3/commercial 경로와 실제 모듈·bundle 구성 확인. frozen profile마다 Qt binding 하나를 선택하고 plugin discovery/재연결·교체 조건 포함 |
| VTK | 본체 BSD 3-clause 고지 보존. 본체 조건을 Qt/모든 bundled dependency/아이콘 전체로 일반화하지 않음 |
| Gmsh4.15.2/OCC | 공식 GPL v2-or-later와 특정 결합 예외·별도 상업 조건, SDK에 포함된 제3자 조건을 실제 배포본별 확인. worker/process 분리는 기술 경계이며 GPL 검토 면제라는 결론 아님 |
| 배포 | 현재 editable 설치와 추후 wheel/frozen installer를 구분. 첫 소비자에서는 versioned wheel 또는 고정 commit 개발 설치 한 경로 선택, installer 전면 통합은 별도 범위 |

공식 근거: [Qt5/6 mixing](https://doc.qt.io/qt-6/cmake-qt5-and-qt6-compatibility.html#mixing-qt-5-and-qt-6), [Qt for Python licenses](https://doc.qt.io/qtforpython-6/licenses.html), [VTK QVTK 지원](https://docs.vtk.org/en/v9.6.1/api/python/vtkmodules/vtkmodules.qt.QVTKRenderWindowInteractor.html), [VTK copyright](https://github.com/Kitware/VTK/blob/master/Copyright.txt), [Gmsh API](https://gmsh.info/doc/texinfo/gmsh.html#Gmsh-application-programming-interface), [Gmsh copying](https://gmsh.info/doc/texinfo/gmsh.html#Copying-conditions). 라이선스 판단은 배포 설계의 확인 항목이며 이 문서는 법률 검토 완료 선언이 아니다.

## 6. 가장 작은 실제 consumer와 종료조건

### W1 — MDO StudyConfigEditor의 continuous 변수 입력

선택 영역을 `apps/workbench_qt/mdo_studio/study_config.py` Variables 표의 **Lower/Upper/Initial 숫자와 Unit 표시/검증**으로 고정한다. 공용 numeric/unit delegate 또는 작은 property editor를 사용하고 토큰·name·domain·responses 등 나머지 UI와 기존 서비스를 유지한다. curve·renderer·새 general shell은 이 consumer에 넣지 않는다.

현재 경로는 `StudyConfigEditor.configuration():81–113` → `window._configure_study():481–495` → `MDOStudyService.configure():443–464`다. 동일 경로를 유지하며 generic widget은 buffer/표현만 소유한다. Unit 문자열의 기존 문법과 parse_unit/도메인 규칙을 유지하고 단위를 새로 추측하거나 native 덱을 자동 재작성하지 않는다. 도메인 검증은 기존 ContinuousVariable/VariableSpace와 MDO service가 소유한다. 공용 theme 적용은 이 입력 부품의 objectName/subtree로 한정해 WB 전역 QSS와 충돌하지 않게 한다.

종료조건:

1. 기존 CalculiX 사용자 INP의 두 scalar token을 연 Study에서 기존 lower/upper/initial/unit을 공용 부품으로 표시하고 값 하나를 변경해 같은 configure 경로로 새 study revision을 만든다. solver 호출은 발생하지 않는다.
2. `1e`, NaN/Inf, 범위 역전, 빈/알 수 없는 unit은 invalid draft를 유지하고 Apply되지 않는다. Escape/Cancel/Revert로 draft만 취소한다. 이전 revision/actual row는 바뀌지 않는다.
3. 저장·새 프로세스 재열기에서 값/단위/revision을 재확인한다. active campaign/read-only/historical revision에서는 기존 편집 제한이 유지되고 stale adapter submit은 거부한다.
4. 동일 공용 부품을 Prep gallery/RAD 기존 지원 숫자 필드에서 사용한다. RAD provider가 덱 단위 문맥과 field label을 제공하고 기존 field command→Undo/Redo→저장/재열기가 유지된다.
5. WB MDO `Undo Current Design Apply`는 기존 서비스/파일 transaction만 호출한다. configure에 Undo가 없는 현 상태를 명시하고 공용 widget history로 덮지 않는다. 기존 apply/Undo 회귀를 확인한다.
6. 고정된 Windows Qt6 환경에서 실제 UI와 관련 offscreen 검사를 구분해 기록한다. WB dark/light와 정상/좁은 크기에서 입력/오류를 읽고 사용할 수 있다. W1 완료는 해당 셀 경계만이며 전 화면 교체 완료가 아니다.

일상적인 코드 결함은 수정하고 영향받은 확인만 다시 수행한다. 고정한 설치/호환성 조사 후 해당 조합에서 연결할 수 없다고 판정되면 원인·패키지 조합을 기록하고 WB 기존 delegate를 유지한다. Prep gallery+RAD 공용화는 계속 진행하고 W2 파일 consumer를 먼저 닫는다. 이 경우 W1은 **보류**이며 W1 완료로 세지 않는다. 재시도는 실패 원인을 바꾸는 수정이나 새 환경이 있을 때 해당 확인만 다시 연다.

### W2 — 독립 Prep의 편집문서/출력 등록

Workbench에서 Prep 프로그램을 명시 설정하고 기존 `LaunchRequest`→JobManager.launch로 `.caeprep` 또는 RAD를 연다. 처음의 역할은 **input=.rad, document=.caeprep, output=.rad**로 고정한다. Prep에서 지원 재료 필드 편집·Undo/Redo·저장·새 실행 재열기·별도 RAD export 후 각 역할에 별도 등록한다. 출력 변경/문서 변경의 상태를 확인한다. CAD 입력은 Prep의 CAD/메시 문서 채택 완료 뒤 추가한다. CAD→STEP→mesh→새 RAD 해석 모델 생성·Engine 생성·실솔버/결과까지 포함하지 않는다. STEP/MSH 교환이 재료·접촉·하중·단계까지 완전 전달한다는 주장도 하지 않는다.

종료조건:

1. 설치 경로/실행 환경/파일 인자가 실제 Prep 새 프로세스를 열고 해당 파일을 읽는다. launch opened를 save/export/solver success로 표시하지 않는다.
2. output과 document가 input을 대체하지 않으며 WB 저장·재시작 후 같은 파일/개정/단위 관계를 복원한다. 원본 RAD는 덮어쓰지 않는다.
3. Prep가 document 또는 output을 변경하면 WB refresh가 하류 입력/결과를 stale로 표시하고 재export·재등록할 경로를 제공한다. 잘못된 파일·누락 파일·미완료 export는 성공으로 채택하지 않는다.
4. 기존 CalculiX/PrePoMax/FreeCAD FEM 프로젝트 열기·선택 실행·결과 전달·MDO 경로의 관련 회귀가 유지된다. W2가 OpenRadioss 실행 adapter의 완료를 의미하지 않음을 문서/지원표에 남긴다.
5. 고정한 Windows 환경에서 실제 Workbench→Prep 실행과 파일 작업을 확인한다. 공백/한글 경로도 argv 인자로 전달되고 기존 Qt/프로그램 환경 설정을 오염시키지 않는다. 해당 환경이 없으면 W2의 실제 플랫폼 확인 보류로 남긴다.

후속은 별도 종료조건으로 연다: (a) solver-specific RAD/INCLUDE/Engine snapshot와 실제 Starter/Engine 두 단계, (b) mesh candidate adoption와 조건 invalidation, (c) live GUI를 제어해야 하는 작업이 확인되면 IPC. IPC에서는 문서 소유자 handshake, 미적용 draft, 오래된 session/epoch, 중첩 요청과 취소의 교착 방지를 함께 검증한다. W1/W2 종료를 이 기능들이 생길 때마다 소급 취소하지 않는다.


### W3 — RAD 실행 입력 묶음과 실제 계산 연결

W2와 별도인 Workbench 실행 기능이다. Prep C의 신규 덱 출력 또는 사용자가 준비한 Starter/Engine 묶음을 입력으로 쓰며, C에 Engine 자동 생성까지 소급해 요구하지 않는다.

- **입력:** Starter 단일 파일 묶음과 상대 INCLUDE를 포함한 두 번째 묶음. 각 묶음의 Engine 파일·참조·실행 버전을 고정한다.
- **변경 책임:** Workbench solver adapter가 입력 수집/복사 규칙과 실행 entrypoint를 제공하고 JobManager가 실행·취소·로그·RunStore를 계속 소유한다. 현재 CalculiX용 `snapshot_input`을 RAD에도 그대로 쓰지 않는다. Prep는 출력의 실제 경로·역할·버전을 전달한다.
- **완료:** 실행 폴더에 Starter/Engine/INCLUDE와 필요한 부속 파일이 원래 이름/관계를 보존해 복사되고, 명령은 그 사본을 읽는다. 원본 변경과 누락 INCLUDE를 실행 전에 진단한다. 고정한 OpenCourant 버전에서 Starter 다음 Engine이 실제 실행되고, 실패/취소/시간 초과는 기존 JobManager와 RunStore에 정확히 남는다.
- **보존:** 원본 입력은 바뀌지 않고 고정한 재료/구속/접촉 값이 실행 사본에도 유지된다. 기존 CalculiX 입력 복사·계산·결과 판독의 관련 회귀를 통과한다.
- **검사 종료:** 두 입력 묶음의 정상 경로, 누락 입력·취소 경로와 영향받은 기존 회귀가 통과하면 W3를 닫는다. 새 solver/Engine 옵션·모든 결과 포맷을 추가하지 않는다. solver 실행 환경이 없으면 그 확인만 보류하며 모의 프로세스의 성공을 실제 계산으로 보고하지 않는다.

W3 완료는 범위를 고정한 입력 실행 완료다. Radioss animation binary의 모든 결과 필드 판독과 후처리 편집은 별도 기능이며 현재 partial 경고를 유지한다.

## 7. 순서와 repo별 변경 소유

| 순서 | Prep 소유 | Workbench 소유 | 고정 결과 |
|---|---|---|---|
| R0 사실/중복/환경 고정 | 공용 자산 목록·권리·배포 경계, 실제 기존 gallery 위치 확인 | 실행환경·기존 consumer 위치·보존 회귀 확정 | 이 문서의 pinned source + W1/W2 입력/환경/성공·실패 기준. 이번은 문서 작업만 |
| R1 작은 공용 추출 | numeric/unit 부품·최소 provider 계약·design token·gallery/RAD 연결. .caeprep v1/RAD 기능 보존 | 변경 없음 | Prep 공용 자산 첫 묶음 완료. 두 번째 repo를 기다려 시작하지 않음 |
| R2 W1 consumer | versioned package/호환 설치 경로와 공용 부품 오류수정 | 단일 StudyConfig 셀 adapter, 기존 configure/save 경로, 범위 내 검증 | 실제 두 소비자의 같은 코드 사용 또는 명시 fallback 판정 |
| R3 W2 연결 | 실제 CLI GUI 진입·open/save/export 계약/실행 설정 | connections/program 탐색·launch·NativeProject file roles/state 연결 | 독립 앱과 파일 교환 완료 |
| R4 model/codec/mesh | 계획 P6/P7에 따른 ModelDoc/대형 배열/codec/복합 명령/mesh adoption·meshing jobs | 필요 시 artifact/job handle adapter만 | candidate→유효 문서 명령 채택, solver 지원과 별도 판정 |
| R5 W3 / jobs·automation | 출력 bundle 계약과 모델 조회/명령/작업 API. live 제어는 후속 | W3 solver별 snapshot/실제 실행과 기존 연구/solver jobs 소유 유지 | W3는 위 입력 실행 조건으로 종료. IPC/MCP는 작업서의 별도 단계로 종료 |

공통 계약 담당은 Prep 통합자 1명, WB adapter/서비스 담당 1명으로 정한다. 제품별 모델·작업 history는 각 repo가 책임지고 변경 계획/PR도 분리한다. 공용 package extraction을 위해 현재 두 repo를 합치거나 별도 신설 repo부터 만들지 않는다. 목표 packaging은 기존 `caelab-prep` 한 배포물 안에서 선택적인 widgets 설치 경로를 제공하는 방안으로 시작할 수 있다. `[widgets]` 같은 extra와 목표 모듈은 아직 존재하지 않으며 R1에서 실제 dependency 분리 후 이름/사용법을 확정한다.

## 8. 기존 공개 GUI 자산 조사 범위

GitHub accessible owner 목록과 gui 이름/설명 검색에서는 별도 전용 공용 GUI 저장소를 특정하지 못했다. 그러므로 존재하지 않는다고 결론 내리지 않는다. `autonomous-cae-lab@46a5cf57803b35549aab4261e309bb6ee0390e32`에서 `docs/design/20261012-desktop-planning/pro-authored/prototype/README.md`를 실제 읽었다. PySide6 6.9.1 기반 gallery/material harness가 있으나 스스로 **planning-only/simulated UI**, 별도 prototype·비제품 import·실Qt 미검증이라고 명시한다. 이를 Prep 실행형 공용 library로 바로 연결하지 않는다. `cae-material-platform` 검색 결과의 ux-reference-gallery는 reference screenshots 영역이며 공용 Qt 위젯 증거가 아니다.

이미 WB에는 semantic dark/light theme·SVG icons·MDO engineering view가 있다. Prep 새 자산 계획에 이를 목록화하고 의미 키/토큰 mapping을 비교할 필요는 있으나 코드 소유권·license·API·실소비자 확인 없이 복제/삭제/강제이행하지 않는다. 정확한 외부 GUI repo가 뒤에 확인되면 R0 asset ownership만 보완하고 W1/W2의 종료 범위를 무한 확장하지 않는다.

## 9. 핵심 소스 링크

- [Workbench 실행](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/apps/workbench_qt/__main__.py), [의존성](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/pyproject.toml), [프로그램 연결](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/caelab/connections.py)
- [NativeProject](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/caelab/project.py), [Workbench facade](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/caelab/workbench.py), [JobManager](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/caelab/jobs.py), [input snapshot](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/caelab/native/input_snapshot.py)
- [MDO config UI](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/apps/workbench_qt/mdo_studio/study_config.py), [Studio binding](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/apps/workbench_qt/mdo_studio/window.py), [MDO service](https://github.com/pikachu444/caelab-workbench/blob/92ce81181396bed9bb6e3024bba62913834c2a7e/caelab/mdo/service.py)
- [Prep 의존성](https://github.com/pikachu444/caelab-prep/blob/5d16e81c7ec7c92499401d63208039424bf73cc9/pyproject.toml), [코어](https://github.com/pikachu444/caelab-prep/blob/5d16e81c7ec7c92499401d63208039424bf73cc9/src/caelab_prep/cae_core/document.py), [현재 RAD 세션](https://github.com/pikachu444/caelab-prep/blob/5d16e81c7ec7c92499401d63208039424bf73cc9/src/caelab_prep/application/session.py), [Gmsh backend](https://github.com/pikachu444/caelab-prep/blob/5d16e81c7ec7c92499401d63208039424bf73cc9/src/caelab_prep/adapters/gmsh_backend.py), [worker](https://github.com/pikachu444/caelab-prep/blob/5d16e81c7ec7c92499401d63208039424bf73cc9/src/caelab_prep/adapters/gmsh_worker.py)
