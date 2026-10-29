# CAELab Prep 개발 기준

## 제품 목표

OpenRadioss/OpenCourant용 독립 GUI 전처리기를 개발한다. 모델 트리, 중앙 3D 화면, 속성·카드 편집기와 선택 도구를 통해 실제 사용자 모델을 편집한다. 유사 프로그램의 화면 구성과 작업 흐름을 참고하되, 자체 소스와 배포 가능한 자산으로 구현한다. 외관만 있는 데모나 시험 실행기를 제품으로 보고하지 않는다.

최종 사용자 작업은 FreeCAD의 CAD → 교환 형상/메시 → CAELab Prep에서 메시·요소·재료·단면·접촉·조건 편집 → Starter/Engine → 솔버 → 후처리로 이어진다. 현재 구현은 기존 RAD 편집·작업 문서·출력과 별도의 CAD/메시 후보 생성까지다. 전체 흐름은 아직 연결되지 않았다.

## 기존 워크벤치와 책임 분리

- CAELab Prep은 독립 실행·파일 열기·편집·저장·재열기를 소유한다. 워크벤치의 내부 StructuralModel이나 예제를 만들어야만 열리는 앱으로 만들지 않는다.
- 워크벤치는 프로그램 탐색·프로젝트 관계·파일 전달·실행·결과 참조를 소유한다. 워크벤치가 시작한 계산은 기존 JobManager가 관리하며 이중 실행 관리자를 만들지 않는다.
- CalculiX에는 PrePoMax 연결을 유지한다. CAELab Prep의 최초 제품 대상은 OpenRadioss/OpenCourant다. 전 솔버 물리 모델을 하나의 공통 FE 스키마로 강제하지 않는다.
- PrePoMax 3.0 Python/MCP 자동화는 워크벤치의 후속 연결 범위다. PMX 편집 원본·INP 출력·FRD 결과를 먼저 안정적으로 주고받고, 반복 작업은 Python, 세션 보조는 MCP를 평가한다. 해당 자동화는 현재 구현·실행 검증되지 않았다.

## 공용 CAE 앱 자산 통합

다른 세션의 「CAE 프로그램을 위한 공용 개발 자산」 조사에서 제안한 design/widgets/framework 분리를 제품 안에 적용한다. 사용자 후속 지시에 따라 공용 자산에는 화면뿐 아니라 모델링 데이터·문서·명령·형상/메시 연결·입출력·자동화 API까지 포함한다. 첫 실제 편집 흐름에서 쓰는 부품부터 내부 모듈로 만들고, 별도 사용처가 생겼을 때 독립 패키지 추출을 판단한다.

| 내부 모듈의 책임 | 포함할 것 |
|---|---|
| 디자인 자산 | 색·글꼴·간격·행 높이·포커스 상태·자체 아이콘 |
| 공학 위젯 | 단위 수치·벡터, 속성 폼, 트리/표, 재료 곡선 |
| 앱 기반 | 메뉴/툴바/단축키가 공유하는 Action, Undo, 선택, 문서, 도킹 배치 |
| 데이터·모델링 기반 | 형상·메시·부품·집합·재료·속성·조건의 ID/참조/단위, 형상과 메시의 연결, 변경 전파, 작업 문서 저장·복원 |
| 솔버별 기능 | Radioss 카드·참조·형식·검사·입출력 |
| 자동화 기반 | GUI·스크립트·MCP가 공유하는 조회/명령 API, 작업 상태·취소·로그, 변경 기록과 시각 피드백 |

첫 원문 편집 흐름은 Python/PySide6 + Qt Widgets + VTK로 구현하고, solver를 모르는 문서 코어와 Radioss 모듈을 분리했다. Gmsh SDK는 별도 프로세스 어댑터로 사용한다. 이 구성은 전체 CAE 기반의 최종 선정과 구분하며 실제 경계는 [ARCHITECTURE](ARCHITECTURE.md)에 둔다. 기존 CAE를 확장하는 C++/Qt·SALOME·C# 경로도 장단점이 있다. 독립 프로그램은 워크벤치와 구현 언어가 같을 필요가 없다. Qt ADS, pyqtgraph, superqt, QtAwesome은 현재 도입하지 않았다. CAD 커널이나 범용 메셔는 기존 도구를 연결하며 처음부터 다시 작성하지 않는다.

## 기반 비교와 현재 판단 (2026-10-29)

아래는 공식 문서와 실제 소스 조사로 보완한 후보 비교이며, 후보 전체를 빌드해 같은 작업으로 평가한 결과가 아니다. 이후 첫 실행 기반으로 Qt/VTK 공개 API와 Gmsh SDK를 연결하고 원문 기반 CAE 문서 코어를 구현했다. 실제 Gmsh CAD/메시 생성과 편집 덱의 OpenCourant Starter 읽기를 확인했지만, 어느 조합이 전체 전처리기에 최선이거나 충분하다고 확정하지 않는다. 외부 CAE 제품의 소스 포크는 도입하지 않았다.

| 후보 | 확보 가능한 실제 기반 | 추가 개발·결합 비용 |
|---|---|---|
| SMTK / CMB ModelBuilder | 형상·메시·시뮬레이션 속성의 resource/attribute 관계, operation, 프로젝트 저장, Qt view, Python과 입력 덱 export 구조. BSD 계열의 C++/Python 기반 | OCCT·메셔 등을 감싸는 상위 프레임워크이므로 실제 backend와 ModelBuilder/ParaView 빌드 조합 확인 필요. 현재 Qt 확장 소스는 Qt5를 요구해 PySide6에 그대로 연결할 수 없음. 문서·배포·master 버전 차이와 Radioss 스키마/reader/writer 확인 필요 |
| FEBioStudio 포크 | 실제 FE 모델·프로젝트, 형상·메시, 재료·단계·하중·접촉, 저장/복원·Command/Undo, CAD/메셔 연결. 본체 MIT, C++/Qt | FEBio SDK·타입/모듈·직렬화에 결합. Radioss LAW/PROP/INTER/Engine의 타입·편집·저장·입출력 추가 필요. 기존 LS-DYNA 메시 export를 완전한 물리 변환으로 취급하지 않는다 |
| SALOME / SMESH 확장 | Study/형상/메시 저장, 형상↔메시 매핑, submesh·메시 가설·품질, geometry/filter 그룹 갱신, Python과 사용자 모듈 앱 | SALOME 전체 호스트 또는 코어 추출의 빌드·배포 비용. 현재 GUI 소스의 Qt5/PySide2·PyQt5 경로는 PySide6 부품과 다름. 솔버별 조건과 native IO는 별도 |
| OCAF + 메셔 + 자체 CAE 코어 | OCAF 문서·참조·Undo·영속 저장과 Gmsh 등의 형상/메시/API를 조합해 독립 앱 구성 | 모델/조건/명령/저장 구조, 형상↔메시↔하중 관계, UI/API를 직접 연결해야 함. 라이브러리 조합만으로 CAE 문서가 완성되지 않음 |
| FreeCAD / PrePoMax 확장 | FreeCAD 문서·재계산·FEM 확장 또는 PrePoMax 모델·명령·PMX·Python/MCP 기반 | 기존 호스트를 수용하는 선택. FreeCAD를 CAD 역할로 쓰는 기존 경로는 유지. PrePoMax는 C#·GPL 및 CalculiX 결합·배포 의존성 확인. 독립 앱의 코어 추출 비용 별도 |

SMTK/CMB의 resource·attribute·operation·export와 FEBioStudio의 실제 FE/문서 코어는 공용 CAE 기반이라는 목적에 직접 맞는 우선 비교 대상이다. SALOME/SMESH는 형상–메시–집합 연결을 기존 기능으로 얼마나 재사용하는지 확인한다. 직접 조합안도 같은 작업으로 비교하며, 익숙한 언어만으로 선정하지 않는다. 이는 조사에 따른 우선순위이며 제품 채택 결정은 아니다.

SMTK는 확인한 master의 `version.txt`가 26.04.0인 반면 조회한 문서는 25.6, CMB 다운로드 안내는 23.01로 시점이 다르다. 현 master의 Qt 확장에는 Qt5가 명시돼 있고, 문서의 `smtk/mesh` 경로가 현재 tree와 일치하지 않아 mesh backend/API를 실제 채택 버전으로 대조해야 한다. OpenCASCADE session도 별도 플러그인이다. SMTK task의 `Agent` 클래스명은 워크플로 핸들러를 의미하며 LLM/MCP 내장 기능의 근거가 아니다.

보조 데이터 라이브러리는 필요한 역할에만 채택한다.

| 자산 | 적합한 역할 | 대신하지 못하는 것 |
|---|---|---|
| MEDCoupling / MEDLoader | 메시·필드·배열, MED 파일 입출력, 메시 간 보간·투영 | CAD 이력·전체 전처리 문서·Radioss 물리 규칙 |
| MOAB / PyMOAB | 엔티티·집합·태그·연결관계, 대용량·병렬 메시 DB | CAD 모델링·작업 이력·구체적 솔버 카드 |
| meshio | 가벼운 메시 교환·집합/데이터 전달 | 재료·접촉·하중까지 의미를 보존하는 범용 CAE 변환 |
| VTK / PyVista | 표시·선택·필터·시각 피드백 | 편집 원본 CAE 모델과 CAD/물리 의미 전체 |
| Netgen 등 메셔 | 메시 생성·최적화·세분화 | 문서·물리 조건·자동화 전체 기반 |

모든 라이브러리를 초기 의존성으로 넣지 않는다. 메시의 정본과 소유자를 정하고 여러 라이브러리에 대형 배열을 중복 보관하지 않도록 한다. 중립면·두께 추출, 판금용 quad, 임의 솔리드의 구조화 hex, 재메시/형상 변경 뒤 조건 연결은 별도 기능 확인 대상이다. 기존의 geometry group 갱신도 외부 CAD 교체 시 모든 면 참조를 자동 복구한다는 뜻은 아니다.

전체 플랫폼 선정에는 같은 사용자 작업인 **CAD 가져오기 → 메시 생성 → 재료·면 집합·하중/접촉 정의 → 작업 원본 저장·재열기 → Radioss Starter/Engine 출력·읽기**를 후보별로 확인해야 한다. Windows 배포와 라이선스·바인딩·메셔 조합, 조건 보존, 필요한 추가 구현량을 함께 비교한다. 이 전체 비교 작업은 아직 수행하지 않았다. 첫 구현에서 CAD/메시 어댑터는 독립 산출물 생성, RAD 앱은 기존 덱의 필드 편집·저장·출력을 각각 수행한다. 둘 사이의 조건 채택 명령은 남은 구현이다. 기반 선정과 상용 CAE GUI 재현은 별개다. 이후 서로 다른 두 앱이 같은 공용 코드를 사용하고 실제 편집·파일 저장·출력을 수행하는지 확인한다.

## AI·스크립팅·MCP를 위한 앱 계약

MCP는 모델링 기능을 제공하는 커널이 아니다. 다음 앱 API 위에 연결하는 전달 계층으로 둔다. GUI·Python/CLI·MCP는 같은 문서와 명령을 사용하며 서로 다른 모델 사본을 몰래 수정하지 않는다.

| 필수 기능 | 계약 |
|---|---|
| 모델 조회 | 열린 문서/개정, 객체·단위·허용 옵션, 형상·메시·집합·참조와 선택 대상을 구조화해 조회. 대형 원시 메시 전체 대신 필요한 범위를 검색·요약하고 상세 조회를 제공 |
| 모델 변경 | 대상 ID·개정·단위를 명시하는 생성/수정/삭제 명령. GUI의 Undo·참조 검사·변경 전파와 같은 경로를 사용. 오래된 개정의 변경은 충돌로 보고 |
| 문서·입출력 | 작업 문서 열기/저장/재열기, CAD/메시 import, native 덱 export 결과·경고·실제 파일 참조를 반환 |
| 긴 작업 | 메시·변환·계산의 job ID, 진행·완료·실패·취소·로그·실제 산출물을 반환. MCP 요청 취소와 실제 프로세스 중단을 구분하고 GUI 스레드를 장시간 막지 않음 |
| 확인·재현 | 선택 대상을 하이라이트하고 viewport/변경 요약을 제공. 명령 기록을 스크립트로 재생할 수 있게 설계하고 저장 후 값을 다시 확인 |
| 프로토콜 | 입력/출력 schema·오류·도움말·지원 버전을 제공. 앱 문서/작업 handle을 명시하고 MCP의 연결 상태에 문서 소유를 숨기지 않음. 실제 host와 SDK/프로토콜 호환을 확인 |
| 접속·권한 | stdio/HTTP 등 전송 방식에 맞는 접속 인증·노출 범위, 읽기/변경 권한과 파일 읽기/출력 경로 범위를 명시하고 기존 정책에 따라 API/명령 층에서 적용. 도구의 안내용 annotation만으로 권한을 보장하지 않음 |

공식 MCP SDK는 tools/resources와 구조화 입출력·전송을 제공하지만 위의 CAE 명령과 데이터 의미를 구현해 주지 않는다. 장시간 작업은 앱의 job API로 먼저 관리하고 MCP Tasks 등 확장은 실제 클라이언트 지원을 확인해 연결한다. 모델 조회·허용 인자·단위·솔버 도움말/예제를 AI가 읽을 경로도 둔다. 벡터 DB나 별도 에이전트 프레임워크는 초기 필수 의존성이 아니며 검색·연구 요구에 따라 추가한다.

PrePoMax 3.0의 공식 Python/API·MCP·journal 문서와 FreeCAD MCP의 실제 document/command/screenshot/job bridge는 참고 대상이다. `neka-nat/freecad-mcp`의 비동기/별도 headless 경로와 GUI 스레드를 막는 FEM 호출은 구분한다. MCP 도구가 있다는 사실만으로 실제 모델 편집·저장·장시간 실행이 검증된 것으로 세지 않는다. 이들 후보는 이번에 실행하지 않았다.

워크벤치는 CAE·수치해석 연구의 계획·반복 실행·MDO/PDE·결과 비교·LLM 근거 토론을 소유하고, Prep은 모델링·문서·선택·입출력 API를 제공한다. 워크벤치가 시작한 솔버 계산의 JobManager 소유는 유지한다. MCP 도입으로 기존의 LLM 읽기·제안/사용자 적용·실행 경계를 자동 변경하지 않으며, 이미 허용된 작업에 불필요한 반복 승인 절차를 추가하지 않는다.

### 조사 근거

- [SMTK 개요](https://www.computationalmodelbuilder.org/smtk/), [subsystems](https://smtk.readthedocs.io/en/latest/userguide/overview.html), [실제 프로젝트 저장 예제](https://smtk.readthedocs.io/en/latest/tutorials/create_a_project/index.html), [현재 소스](https://gitlab.kitware.com/cmb/smtk), [별도 OCCT session](https://gitlab.kitware.com/cmb/plugins/opencascade-session).
- FEBioStudio [FSModel](https://github.com/febiosoftware/FEBioStudio/blob/develop/FEMLib/FSModel.h), [FSProject](https://github.com/febiosoftware/FEBioStudio/blob/develop/FEMLib/FSProject.cpp), [UndoDocument](https://github.com/febiosoftware/FEBioStudio/blob/develop/FEBioStudio/UndoDocument.h), [빌드·의존성](https://github.com/febiosoftware/FEBioStudio/blob/develop/BUILD.md).
- SALOME [사용자 정의 앱](https://docs.salome-platform.org/latest/tui/KERNEL/SALOME_Application.html), [SMESH 그룹](https://docs.salome-platform.org/latest/gui/SMESH/grouping_elements.html), [SMESH 데이터 소스](https://github.com/SalomePlatform/smesh/blob/master/src/SMESHDS/SMESHDS_Mesh.hxx).
- [OCAF](https://dev.opencascade.org/doc/overview/html/occt_user_guides__ocaf.html), [Gmsh](https://gmsh.info/doc/texinfo/), [MEDCoupling의 역할](https://docs.salome-platform.org/latest/dev/MEDCoupling/developer/library.html), [MOAB](https://sigma.mcs.anl.gov/moab-library/).
- [PrePoMax 3.0 발표](https://prepomax.fs.um.si/version-3-0-0/), [공식 API 개요](https://gitlab.com/MatejB/PrePoMax/-/raw/master/Python_API_Overview.md), [FreeCAD MCP](https://github.com/neka-nat/freecad-mcp), [실제 server.py](https://github.com/neka-nat/freecad-mcp/blob/main/src/freecad_mcp/server.py).
- [공식 MCP SDK](https://py.sdk.modelcontextprotocol.io/), [버전·호환 변경](https://py.sdk.modelcontextprotocol.io/whats-new/), [Tasks 확장](https://tasks.extensions.modelcontextprotocol.io/).

기능·라이선스·의존성은 위 공개 원문과 실제 채택 버전을 대조한다. 본체의 MIT/BSD/LGPL/GPL 조건을 바인딩·아이콘·메셔·플러그인 전체의 조건으로 일반화하지 않는다.

## 파일·편집 계약

1. CAD 원본, 교환 형상/메시, 전처리 편집 문서, Starter/Engine 출력의 역할을 구분한다. 첫 편집 문서는 원문과 필드 patch를 동봉한 버전 있는 `.caeprep` ZIP이다. CLI와 실제 지원 범위는 [README](README.md), 내부 계약은 [ARCHITECTURE](ARCHITECTURE.md)에 공개한다. Engine 생성은 아직 없다.
2. 원 RAD의 카드 순서·주석·미편집 필드·미지원 카드와 INCLUDE 파일 관계를 보존한다. 미지원 카드는 읽기 전용 원문으로 남기고 지원하지 않는 편집은 명시한다. 이해하지 못한 필드를 기본값으로 덮어쓰지 않는다.
3. 형식 지정은 공개 솔버 규격에 맞추며 ID 참조와 단위 선언을 유지한다. 공통 GUI가 솔버 고유 옵션을 제거하지 않게 한다.
4. 메뉴·툴바·단축키·추후 자동화는 같은 명령을 사용한다. 선택 → 속성 수정 → Undo/Redo → 저장/취소가 같은 문서에 반영돼야 한다.
5. 저장하지 않은 변경, 입력 갱신, 경고와 실패를 사용자 용어로 표시한다. 내부 변수명·해시·검사 수치를 사용자 화면의 주 정보로 노출하지 않는다.

## 제품 개발 순서

| 순서 | 실제 사용자 작업 | 완료에 필요한 확인 |
|---|---|---|
| 1. 네이티브 편집 | 사용자 RAD 열기, 메시/트리 표시, 재료·구속·접촉 편집, Undo, 저장·재열기 | 실제 앱에서 바뀐 값과 미편집 조건이 보존되는지 확인 |
| 2. 모델 구성 | 집합·면 선택, 요소/단면·초기조건·하중·곡선·제어 설정, 새 카드 생성 | 소형 시험 외의 사용자 입력으로 선택·참조·출력 확인 |
| 3. CAD/메시 연결 | FreeCAD 교환 형상과 기존 메셔 연결, 부품·집합 유지 | 실제 형상에서 메시와 조건을 작성하는 흐름 확인 |
| 4. 연결·배포 | Windows 실행 앱 배포, 워크벤치에서 열기·덱 전달, 솔버 검사·실행 연계 | 새 Windows 환경에서 전체 파일 흐름과 오류 처리 확인 |

각 단계는 실제 사용자 작업을 구현하는 단위다. 위젯 갤러리는 개발 보조이며 이 작업의 대체물이 아니다. 등록된 시험 자료·메뉴 존재·검사 통과 수로 프로그램 지원 완료를 주장하지 않는다.

## 검증에 반영할 경험

BeidPrep 1.0.1은 소형 모델을 열고 저장할 수 있었지만 저장본의 구속과 IPLAS 옵션이 달라졌다. 따라서 원본 보존, 미지원 카드, INCLUDE, 참조, 고정 폭 필드, 편집 값의 재열기를 확인한다. 솔버 정상 종료와 모델 조건 보존·해석 정확도는 각각 판단한다. 시험 범위는 [기록](docs/beidprep-evaluation.md)을 따른다.
