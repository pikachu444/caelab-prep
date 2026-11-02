# CAELab Prep 설치와 사용

RAD를 편집하고 작업문서를 저장하거나 솔버 입력을 내보내는 절차입니다. PowerShell 명령은 저장소 최상위 폴더에서 실행합니다. 출력은 사용자 원본과 다른 새 폴더를 선택하세요.

<a id="install-windows"></a>

## Windows에 설치하기

Python 3.11 이상을 사용합니다. GUI에는 PySide6와 VTK, CAD·MSH 가져오기에는 Gmsh SDK가 필요합니다. `gui`와 `cad` 옵션으로 설치합니다. 솔버 EXE, FreeCAD, OCP, pytest는 기본 앱 실행의 필수 의존성이 아닙니다.

```powershell
git clone https://github.com/pikachu444/caelab-prep.git
cd caelab-prep
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[gui,cad]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\caelab-prep.exe --help
.\.venv\Scripts\caelab-prep.exe gui
```

`.venv`가 이미 있으면 가상환경 생성 명령을 반복하지 마세요. 기존 환경을 사용하거나 새 이름으로 만들고 실행 경로도 바꿉니다. 가상환경 활성화나 PowerShell 실행 정책 변경은 필요하지 않습니다. `caelab-prep.exe`는 Python console entry point이며 설치형 배포 패키지가 아닙니다.

2026-11-02 Windows 확인 조합은 Python 3.13.5, PySide6/Qt 6.9.1, VTK 9.4.2, Gmsh 4.15.2입니다. 같은 라이브러리 조합을 설치하려면 위 설치 명령을 다음으로 대체합니다. 전체 의존성 lockfile이나 모든 Python 버전의 검증을 뜻하지는 않습니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[gui,cad]" PySide6==6.9.1 vtk==9.4.2
```

GUI 없는 CLI는 `python -m pip install -e .`로 설치합니다. Qt 갤러리만 쓰려면 `.[widgets]`, MCP adapter는 `.[mcp]`, 개발 검사는 `.[dev]`를 선택합니다. `gui --no-3d`는 VTK viewer만 끄며 문서 편집을 유지합니다.

설정까지 분리해 실행하려면 `gui --settings-file "임시 폴더/prep.ini"` 또는 `gallery --settings-file "임시 폴더/gallery.ini"`를 사용합니다. 지정한 INI에 창 배치를 읽고 저장하며 기본 사용자 설정을 읽거나 쓰지 않습니다. 각 작업 공간에는 별도 파일을 지정하세요. 옵션을 생략하면 기존 사용자 설정을 사용합니다. 이 옵션은 작업문서·출력 위치를 바꾸지 않으며, 이전 portable 후보 `46cea514`에는 포함되지 않습니다.

## Linux에서 실행하기

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[gui,cad]"
.venv/bin/caelab-prep gui
```

Qt XCB와 OpenGL 런타임, 한글 글꼴이 필요합니다. Ubuntu 의존성과 X11 실행 환경은 [CI의 `native-render` 설정](../.github/workflows/prep-tests.yml)을 확인하세요. offscreen 실행은 문서·입력 검사이며 데스크톱 3D 표시 확인과 구분합니다.

## RAD를 편집하고 저장하기

기본 native 창에서 다음 순서로 작업합니다. 프로그램별 표현에서는 명령 배치가 다를 수 있습니다.

1. **File → Open Radioss deck…**에서 root RAD를 엽니다. INCLUDE 파일도 원래 상대 경로에서 읽을 수 있어야 합니다. `.caeprep`는 **Open project…**로 엽니다.
2. 트리에서 PART, 재료, 단면 또는 조건을 선택하고 Inspector의 지원 필드를 수정합니다. 미해석 원문 카드는 보존되지만 모든 필드를 편집할 수 있는 것은 아닙니다.
3. 필드의 Enter 또는 편집 창의 **Apply**로 확정합니다. **Undo/Redo**로 확정된 변경을 되돌리거나 다시 적용합니다. 잘못된 숫자나 미확정 초안은 저장 전에 수정하거나 명시적으로 취소합니다.
4. **File → Save project as…**에서 새 `.caeprep` 경로를 선택합니다.
5. 창을 닫고 저장한 문서를 다시 열어 값과 참조를 확인합니다.

`.caeprep`는 편집 원문·문서 상태·관계를 보존합니다. RAD 내보내기는 솔버용 파일을 별도로 작성합니다. 현재 RAD 작업문서는 v6으로 저장하고 v1–v5도 읽습니다. 이전 v5 앱은 v6 문서를 열지 못하므로 기존 작업문서를 보존하고 새 이름으로 저장하세요. 중립 재료/곡선 문서와 RAD 문서는 같은 확장자를 사용하지만 codec이 다르므로 해당 작업 공간에서 여세요.

```powershell
.\.venv\Scripts\caelab-prep.exe gui examples/rad/shell_panels_0000.rad
.\.venv\Scripts\caelab-prep.exe gui prep-demo/edited.caeprep
```

## 새 모델에 CAD·메시와 조건 연결하기

개발 API의 `application.structured_mesh.generate_structured_mesh(recipe, output_dir)`는 명시한 planar quad recipe의 후보를 생성합니다. 후보의 `to_native_mesh()`를 기존 `session.adopt_mesh_candidate()`에 전달하면 선택한 재료·shell 단면과 함께 채택·Undo·저장·native 출력할 수 있습니다. recipe 단위와 문서 단위가 같아야 하며, hex 채택과 GUI 진입·recipe의 영속 편집/재생성은 아직 지원 완료가 아닙니다. 아래 GUI의 CAD/독립 MSH 경로와 구분합니다.

1. **File → New model…**에서 이름과 질량·길이·시간 단위를 명시합니다. 단위 없는 입력에 임의 단위를 추정하지 않습니다.
2. 재료와 요소 family에 맞는 shell 또는 solid 단면을 만듭니다.
3. CAD는 **Mesh → CAD / mesh candidate…**에서 입력과 후보 폴더, 요소 크기를 선택합니다. 현재 Gmsh 경로는 tri3/tet4 후보를 지원합니다. CAD 없는 MSH는 **Mesh → Import mesh…**에서 소스 길이 단위를 직접 지정합니다.
4. 후보의 품질·그룹·파트와 오류를 확인합니다. 재료와 단면을 지정한 뒤 **Adopt candidate**로 확정합니다. 후보 생성만으로 모델 문서가 바뀌지 않습니다.
5. 곡선·집합을 만들고 BCS, CLOAD, INIVEL/TRA 또는 지원 TYPE7 조건을 연결합니다. 해석 케이스에서 활성 조건·종료 시간·출력 간격을 저장합니다.
6. `.caeprep`와 후보 자산 폴더를 함께 보관합니다. 작업문서에 native 메시가 있어도 재메시에 필요한 CAD/XAO/MSH 원자산이 모두 동봉되는 것은 아닙니다.

MSH는 2.2/4.1 ASCII에 한정합니다. binary·partition·periodic·data·parametric MSH와 미지원 요소 family는 거부합니다. 문서와 소스 길이 단위가 다르면 자동 환산하지 않습니다. 일반 warped quad, 임의 all-hex, 자동 중립면과 모든 접촉 프로파일은 지원 완료 범위가 아닙니다.

main에 병합된 **Mesh → Move nodes to coordinates…**에서는 소스와 절점 ID를 선택하고 입력 덱 길이 단위의 절대좌표를 입력합니다. **Preview move**에서 품질과 영향 대상을 확인하고 검토 체크 후 **Apply move**로 확정합니다. ID·연결·집합 멤버를 보존해도 하중 작용점과 접촉 간격은 달라질 수 있습니다. 영향 집합은 **Replace prepared mesh / reconnect targets…**에서 명시적으로 검토하기 전까지 native 출력을 막습니다. 다중 자원에서는 집합별 실제 변경 자원에 검토 상태를 연결합니다. API의 하중 진단은 시간함수 평가 전 계수이며 실제 시각의 힘·모멘트나 작용점 모멘트를 계산한 결과가 아닙니다. 일반 메시 편집 전체의 완료본은 아닙니다.

<a id="node-move-images"></a>

### 실제 Windows 화면으로 좌표 이동 확인하기

아래는 현재 main에 통합된 절대좌표 이동 기능의 2026-11-02 당시 개발검증자료입니다. 각 단계는 [검증 기록](native-windows-validation.md#node-move-20261102)에 적힌 서로 다른 소스 기준을 사용했습니다. 현재 HEAD나 같은 frozen 배포본 전체를 검증한 이미지가 아닙니다. 미리보기는 실제 Qt 위젯 캡처이며, 메시 이미지는 같은 실행 흐름의 VTK framebuffer입니다. 위젯 캡처에서 검게 보였던 OpenGL 영역은 사용하지 않았으며 두 이미지를 합성하지 않았습니다.

![입력 덱 mm 단위로 node 2의 X를 11로 지정한 실제 미리보기](native-windows/2026-11-02-node-move/beam_shell_tet/preview.png)

절점 ID와 절대좌표를 넣고 **Preview move**를 누르면 변경 전후 품질과 검토 대상이 나타납니다. 상세 목록은 내부 스크롤로 확인합니다. 위 화면은 beam/shell/tet 입력의 node 2를 X=10에서 11 mm로 이동하는 예입니다.

![이동한 작업문서를 새 프로세스에서 다시 연 VTK 메시](native-windows/2026-11-02-node-move/beam_shell_tet/reopen-framebuffer.png)

**Apply move → Save project → 별도 프로세스 재열기** 후 표시한 메시입니다. 화면뿐 아니라 절점 ID·좌표·연결도 대조했습니다. 형상 검토 대기는 재열기 후에도 남습니다. 이 그림이 재연결 조작·솔버 계산·물리 적합성을 확인한 것은 아닙니다. 실행 단계별 소스 hash와 [저장 기록](native-windows/2026-11-02-node-move/beam_shell_tet/save.json), [재열기 기록](native-windows/2026-11-02-node-move/beam_shell_tet/reopen.json)은 [Windows 확인 범위](native-windows-validation.md#node-move-20261102)를 따릅니다.

## Starter와 Engine 내보내기

**File → Export Radioss deck…**은 편집된 RAD와 해석한 의존 파일을 내보냅니다. 새 해석 입력은 **File → Export Starter and Engine…**에서 종료 시간·출력 간격과 `model_0000.rad` 경로를 지정합니다. 저장된 활성 케이스를 사용하는지 수동 설정인지 확인하세요. 출력은 `_0000.rad` Starter와 `_0001.rad` Engine으로 나뉩니다.

내보내기는 솔버 실행이 아닙니다. 검토 대기·미해석 물리 조건·미지원 요소가 출력을 막으면 해당 오류를 해결하세요. 원본 RAD나 이전 계산 폴더와 다른 새 출력 폴더를 사용합니다.

Engine 출력에는 `/BEGIN`의 입력 단위뿐 아니라 두 번째 작업 단위 행도 명시되어 있어야 합니다. 예제 `shell_panels_0000.rad`처럼 작업 단위 행이 없는 RAD는 일반 RAD 내보내기를 할 수 있지만 Engine 출력은 `invalid_units`로 거부합니다. 입력 시간 단위를 작업 시간 단위로 추정하지 않습니다. 새 모델은 **New model…**에서 명시적 단위로 시작하고, 기존 입력은 작업 단위가 명시된 덱을 준비하세요.

Prep에는 솔버 실행 경로나 Intel runtime을 설정하는 기능이 없습니다. 계산은 [CAELab Workbench](https://github.com/pikachu444/caelab-workbench/blob/main/docs/tutorials/workbench_quickstart.md#caelab-prep와-공용-입력-위젯)의 프로그램 연결과 기존 JobManager에서 설정합니다. Workbench 안내에 따라 Starter/Engine, MPI·공유 라이브러리와 실행 환경을 준비하세요. Prep를 설치했다고 솔버가 설치되거나 정상 동작이 확인된 것은 아닙니다. 실제 입력별 실행·오류·경고와 확인 범위는 [Windows 기록](native-windows-validation.md)을 확인하세요.

## CLI로 편집·저장·재열기하기

다음 예제는 저장소의 CC0 shell 입력으로 필드 변경과 파일 전달을 확인합니다. 물리 해석 결과를 검증하는 예제가 아닙니다. PowerShell에서 새 출력 폴더를 선택해 실행합니다.

```powershell
$prep = (Resolve-Path .\.venv\Scripts\caelab-prep.exe).Path
& $prep inspect examples/rad/shell_panels_0000.rad
& $prep fields examples/rad/shell_panels_0000.rad --card /MAT/LAW1/1
& $prep edit examples/rad/shell_panels_0000.rad --card /MAT/LAW1/1 --field young_modulus --value 205000 --output prep-demo/edited.caeprep
& $prep fields prep-demo/edited.caeprep --card /MAT/LAW1/1
& $prep export prep-demo/edited.caeprep --output prep-demo/export/edited_0000.rad
```

각 명령은 독립 세션을 열고 JSON을 반환합니다. 네 번째 명령은 저장한 문서를 새 프로세스로 다시 열어 변경값을 조회합니다. `--card`에는 조회 결과의 UUID 또는 중복 없는 정확한 native header를 사용합니다. 일반 CLI는 이미 열린 GUI 문서를 자동으로 변경하지 않습니다.

새 문서와 재료·solid 단면을 작성할 수도 있습니다. 수치는 Mg/mm/s 입력의 예시이며 사용할 물성은 별도로 정해야 합니다.

```powershell
& $prep new --name "User model" --mass Mg --length mm --time s --output prep-demo/model.caeprep
& $prep model prep-demo/model.caeprep material.create --describe
& $prep model prep-demo/model.caeprep material.create --set name=Steel --set native_id=41 --set density=7.85e-9 --set young_modulus=210000 --set poisson_ratio=0.3 --output prep-demo/material.caeprep
& $prep model prep-demo/material.caeprep solid_section.create --set name=Solid --set native_id=207 --output prep-demo/section.caeprep
```

CAD 메시·MSH·케이스의 정확한 인수는 도움말에서 조회합니다. `mesh` 결과의 실제 metadata 경로를 `adopt --candidate`에 전달하며 임의 UUID를 복사하지 않습니다.

```powershell
& $prep mesh --help
& $prep adopt --help
& $prep import-mesh --help
& $prep case --help
& $prep export --help
```

`export --engine`은 `--end-time`, `--output-interval`과 `_0000.rad` 출력명을 함께 사용합니다. 두 시간 값은 선언된 작업 시간 단위입니다. 저장된 케이스의 시간 단위를 사용하려면 `case <문서> export --output <경로>`로 내보냅니다.

## 갤러리와 프로그램별 표현 열기

```powershell
.\.venv\Scripts\caelab-prep.exe gallery
.\.venv\Scripts\caelab-prep.exe catalogue
.\.venv\Scripts\caelab-prep.exe compare --rad examples/rad/shell_panels_0000.rad
```

`gallery`는 중립 재료/곡선 작업 공간, `catalogue`는 공용 부품·아이콘·디자인 상태 탐색기입니다. 두 명령은 `widgets`만으로도 실행하며 VTK가 필요하지 않습니다. 곡선 CSV는 UTF-8/BOM의 두 수치 열과 선택적 `x,y` 헤더를 받습니다. Import CSV의 preview를 Apply로 확정하고 plot drag는 release 때 한 Undo로 확정합니다.

`compare`의 기본 문서는 중립 문서입니다. RAD 또는 RAD 작업문서를 열 때는 `--rad`를 지정합니다. [표현별 안내](ui-reference-variants.md)의 구현·미확인 차이를 확인하세요.

## 열린 GUI 자동화하기

**Automation → Start live control…** 또는 `gui --ipc <새 연결 파일>`로 연결합니다. `live` CLI와 MCP adapter는 그 창의 같은 문서에 요청합니다. 연결 파일에는 인증 정보가 있으므로 공유하거나 Git에 넣지 마세요. [live 제어](live-control.md)와 [MCP 클라이언트](mcp-client.md) 절차를 따릅니다.

## 실행 문제 해결하기

| 증상 | 확인할 것 |
|---|---|
| 명령을 찾지 못함 | 가상환경의 `Scripts/caelab-prep.exe`를 직접 실행합니다. 설치한 Python과 실행한 Python이 같은지 확인합니다. |
| PySide6 또는 VTK import 실패 | 해당 환경에 `.[gui]`를 설치합니다. CLI 또는 `widgets` 설치만으로 3D viewer가 추가되지는 않습니다. |
| 3D 영역이 검거나 OpenGL 초기화 실패 | 데스크톱과 드라이버를 확인하고 `gui --no-3d`로 문서 편집을 구분해 확인합니다. 위젯 캡처의 검은 영역만으로 실제 VTK 표시 실패를 단정하지 않습니다. |
| CAD/MSH worker 실패 | 같은 환경의 `.[cad]`, 입력 형식·단위·품질과 worker 오류를 확인합니다. 미지원 요소를 지워 성공 처리하지 않습니다. |
| 기존 출력 파일 때문에 거절 | 새 작업·출력 폴더를 선택하고 원본을 보존합니다. 사용자 파일을 지워 해결하지 않습니다. |
| 초안·busy·개정 충돌 | 편집을 확정하거나 취소하고 작업 종료 후 현재 문서를 다시 조회합니다. 이전 preview나 handle을 재사용하지 않습니다. |
| export 후 솔버 실패 | Prep 출력과 Workbench 실행 로그를 나누어 확인합니다. 실행파일·runtime·입력 읽기·계산·결과 판독을 따로 확인합니다. |
| Engine 출력의 `invalid_units` | `/BEGIN`의 두 번째 작업 단위 행을 확인합니다. 입력 단위만 있는 RAD에서 시간을 추정하지 않습니다. |

OCP fixture 생성용 개발 환경은 GUI 환경과 분리합니다. CI의 `cadquery-ocp==7.8.1.1.post1`은 VTK 9.3.1을 요구하므로 GUI의 VTK 9.4 이상과 강제로 맞추지 않습니다. 제품 실행에 OCP를 추가할 필요는 없습니다. 배포 조건은 [THIRD_PARTY](../THIRD_PARTY.md), 실제 확인과 미확인은 [Windows 기록](native-windows-validation.md)을 따릅니다.
