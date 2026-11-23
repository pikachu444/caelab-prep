# 현재 구현과 남은 작업

실행 순서는 [단계 계획 앞부분](docs/execution-stages.md#execution-order)을 따릅니다. 첫 코드는 D03 표시 갱신이며 D23/D38의 기존 과업 확인, D24/D25 성능·편집 확대, D26–D31 메시·8제품 후속, D19 재료 적용, D33/D34/D36 실제 환경·전체 인수까지 이어갑니다. 이 문서의 N01–N26 상태와 7/16/3 분류는 유지합니다.

## P0 Track A2 소스 모델 표시와 Windows 실행 — 2026-11-23

- Source Models에서 소스·인스턴스·리소스의 내부 ID 전용 열과 괄호 접미사를 제거했습니다. 참조 선택, 생성·삭제 및 Undo/Redo에는 기존 내부 ID를 사용합니다. 리소스 이름과 보관된 작업 파일 경로는 기존 값을 표시합니다. [대화상자 코드](src/caelab_prep/ui/source_models.py)
- Windows 실행 배치는 체크아웃에 `.venv`를 설치하고 `pyproject.toml` 스탬프와 import 검사로 재사용 여부를 결정합니다. N13의 Windows 배포 묶음과 N14의 Workbench 연동 검증은 후속입니다. [실행 배치](CAELab_Prep_Install_And_Run.bat), [시작 안내](README.md#windows에서-시작하기)
- Windows의 Python 3.13·Qt offscreen에서 참조 동작과 PowerShell `-DryRun`을 확인했습니다. 실제 `.bat`로 `uv`와 Python/pip 설치, 스탬프 재사용, 손상 환경 복구, 분리 실행을 확인했습니다. [집중 회귀 검사](tests/test_source_models_ux_and_launcher.py)

<a id="track-3-corrections"></a>

## Track 3 검토 수정 (D23, D25, D19) — 2026-11-18

검토 기준은 `cef119b9fa9b610ec9ff41339a14ea916abdfd6b`다. 수정 범위는 `feature/prep-d23-d25-mesh-and-binding`의 D23, D25, D19 검사다.

| 작업 | 구현 및 확인 | 후속 |
|---|---|---|
| D23 / N18 | 두 다중 INCLUDE 입력에서 `node_move`, `node_merge`, `element_delete`, `shell_flip`, `part_reassign`, 준비한 INCLUDE 교체(`replace_prepared_mesh`)와 Undo/Redo를 확인했다. Deck B의 별도 검사는 평면 패치를 Gmsh 최대 크기 10 mm와 2.5 mm로 각각 생성해 절점 수, 삼각형 수, 최대 변 길이를 비교하고 더 조밀한 후보를 추가했다. `.caeprep` 및 Starter를 다시 열어 절점 좌표, 순서가 있는 연결, BEAM 방향, PART와 INCLUDE 소유권, 집합 멤버, 조건 참조를 비교했다. | 기존 CAD 영역을 다시 메시하는 일반 작업 흐름, 실제 Starter/Engine 실행 및 물리 응답 확인 |
| D25 / N18 | `split_triangle_edge`로 선형 SH3N 한두 개의 공용 변을 분할한다. 다른 요소가 같은 변을 사용하면 차단한다. 두 자식에 부모 행의 두께·각도·후행 필드를 복사한다. GUI와 API에서 명시한 자식 전부를 집합에 재연결할 수 있다. 내보낸 `/GRSH3N` 재파싱에서 자식 4개와 합계 100 mm²를 확인했다. Qt 창에서 저장 확인을 취소해도 검토 창이 유지된다. | edge swap, quad/tri 변환, 고차 승격, 실제 Windows 데스크톱/VTK 및 원제품 비교 |
| D19 / N19 | C10의 해시·만료 검사를 기존 소유 프로세스 IPC에 연결했다. `radioss_law1_elastic_v1`은 루트 또는 INCLUDE의 LAW1/ELAST에서 E·ν·ρ를 값 변경 한 건으로 적용한다. Prony, LAW36 및 동반 곡선 요청은 `UNSUPPORTED_ATOMIC_APPLY`를 반환한다. | Workbench 저장 평가와의 합동 확인 및 모델별 솔버 검증 |

Windows Python 3.13에서 집중 pytest 43건을 확인했다. `prep-tests.yml`에 나열된 검사의 로컬 결과는 `document` 1,239 통과·11 건너뜀·11 제외, `qt-document` 508 통과·2 건너뜀, `live-automation` 86 통과·7 건너뜀이다. BeidPrep 표현의 Qt offscreen 검토 화면(780×640)은 로컬 `C:/Users/pikac/.gemini/antigravity/brain/9beddcd8-3baf-44f6-9560-2c07a847da3f/d25_prep_edge_split_dialog.png`에 있다. 원 검토자의 수정본 재검토는 통합 인계에 남긴다.

### 두 번째 검토 수정

`16a387046e7429b9d8358f776edacb6313add9c3` 재검토에서 찾은 문제를 수정했다. D23은 루트 메시 카드 뒤의 INCLUDE 지시문과 삭제한 행 뒤 주석을 보존한다. 요소 생성·quad 분할·tri 결합 결과는 준비한 INCLUDE를 교체하는 경로로 저장·재열기·Starter 내보내기를 확인했다. 선택한 요소를 직접 생성하거나 변환하는 명령은 후속이다.

D25는 분할 변의 양 끝점을 포함한 미선택 요소를 차단한다. 저장한 프로젝트에서 SH3N 부모별 자식 ID를 읽어 명시 재연결할 수 있다. 사용자가 버튼을 활성화하려면 새 미리보기를 확인한 뒤 검토 상자를 체크해야 한다.

D19는 대상 탄성 카드의 기존 세 계수와 다중 INCLUDE의 재료 옵션을 검사한다. 확정은 준비한 카드 해시와 평가 출처를 함께 검증한다. 최근 만료된 계획은 최대 256개까지 추적한다. Windows Python 3.13에서 `document` 1,270 통과·11 건너뜀·11 제외, `qt-document` 516 통과·2 건너뜀, `live-automation` 109 통과·7 건너뜀을 확인했다. Qt 형상 검사는 첫 teardown 중단 뒤 별도 프로세스에서 25건을 통과했다. 마지막 주석 보존 교정 후 집중 75건과 영향 회귀 207건을 통과했다(1건 건너뜀). 같은 위치에 BeidPrep Qt offscreen 화면(780×640)을 다시 저장했다.

### 세 번째 검토 수정

`24137d60e24759708fe5b78148c3233ce49984ee` 재검토에서 찾은 문제를 수정했다. 루트와 중첩 INCLUDE에서 한 줄 또는 두 줄 지시문 뒤의 파일 관계를 유지한다. 카드 행을 모두 삭제할 때 현재 블록의 주석을 보존한다. Deck B의 `/GRSH3N/SH3N/32`는 `81 → 581, 582`, `82 → 583, 584`를 명시 재연결한다. Starter를 다시 열어 각 요소의 면적 25 mm²와 집합의 합계 100 mm²를 확인했다.

D25 요소 재연결에는 자원 범위가 있는 요소 참조를 사용한다. 자식 목록의 정수 ID는 해당 부모의 저장된 자식 ID와 일치할 때 허용한다. D19는 공백이 채워진 재료 옵션 ID를 인식하고, LAW1의 비어 있거나 0인 `rho_0`를 보존한다. 평가 출처를 보내면 필수 7개 문자열과 해시 형식을 검증한 뒤 확정 요청에서 같은 값을 요구한다.

Windows Python 3.13에서 집중 pytest 109건을 통과했다. 로컬 `document`는 1,305 통과·11 건너뜀·11 제외, Qt offscreen `qt-document`는 527 통과·2 건너뜀, `live-automation`은 133 통과·7 건너뜀이다.

### 네 번째 검토 수정

`8fe6609b241f7440f39da4331d3cd57c72355204` 재검토를 반영했다. 중첩 INCLUDE는 Starter 루트에서 먼저 찾고 해당 경로가 없을 때 현재 INCLUDE 디렉터리에서 찾는다. 두 경로가 모두 존재하는 입력과 같은 디렉터리에서만 찾을 수 있는 입력을 한 줄·두 줄 지시문으로 구성해 네이티브 열기, 독립 소스 가져오기, 프로젝트 재열기, Starter 내보내기에서 확인했다. `24137d60`으로 저장한 충돌 재현용 프로젝트가 `8fe6609`에서 `invalid_project`를 반환했고, 수정 후에는 두 INCLUDE의 절점 소유권과 셸 연결을 유지한 채 다시 열렸다.

D19 준비와 확정 요청은 모두 평가 출처 7개 필드를 요구한다. 출처가 빠진 준비 요청은 `invalid_request`, 준비 때의 출처와 일치하지 않거나 출처가 빠진 확정 요청은 `hash_mismatch`를 반환한다. LAW1의 `rho_0`는 비어 있거나 정확한 0일 때 허용한다. 밑줄 표기와 부동소수점에서 0으로 언더플로되는 0이 아닌 값은 거부한다.

Gmsh 4.15.2에서 같은 평면 BREP에 최대 크기 10 mm와 2.5 mm를 적용했다. 절점은 24개에서 221개, 삼각형은 32개에서 388개로 늘었고 최대 변 길이는 12.479 mm에서 2.891 mm로 줄었다.

Windows Python 3.13.5에서 집중 pytest 121건을 통과했다. 로컬 `document`는 1,317 통과·11 건너뜀·11 제외, Qt offscreen `qt-document`는 531 통과·2 건너뜀, `live-automation`은 141 통과·7 건너뜀이다.

### 다섯 번째 검토 수정

`987c52b8` 재검토를 반영했다. 같은 이름의 루트·형제 INCLUDE 파일이 모두 있으면 먼저 Starter의 직접 참조와 디렉터리가 명시된 참조를 해석한다. 이 참조에서 루트 파일을 이미 사용했고 형제 파일을 명시하지 않았다면 중첩 지시문은 형제 파일에 바인딩한다. 루트의 디렉터리는 파일 후보에서 제외한다. 정확한 대소문자가 없으면 유일한 일치 경로를 사용한다. Starter나 Engine 출력 이름 또는 기존 출력 디렉터리의 파일이 중첩 INCLUDE를 가릴 때 내보낸 지시문에 루트 기준 경로를 쓴다.

`24137d60`과 `8fe6609`에서 각각 저장한 충돌 프로젝트를 다시 열어 절점 소유권과 셸 연결을 확인했다. `8fe6609`에서 저장한 14절점 독립 소스 프로젝트도 따옴표가 있는 두 줄 INCLUDE를 유지한 채 열고 Starter로 내보냈다. 새 독립 소스 가져오기는 두 줄 지시문의 파일명을 매핑하고 따옴표를 보존한다. D25에서 같은 분할 변의 양 끝점을 포함한 `/QUAD`, `/SH4N`, `/TETRA` 이웃은 `EDGE_HAS_UNSELECTED_NEIGHBORS`로 거부한다.

Windows Python 3.13.5에서 집중 pytest 134건을 통과했다. 로컬 `document`는 1,330 통과·11 건너뜀·11 제외, Qt offscreen `qt-document`는 544 통과·2 건너뜀, `live-automation`은 141 통과·7 건너뜀이다.

### 여섯 번째 검토 수정

`ac0a255` 재검토를 반영했다. 중첩 INCLUDE는 `sets/nodes.inc`처럼 디렉터리를 포함한 경로에도 루트·형제 후보를 비교한다. 모호한 지시문은 해석 전에 확정된 참조를 기준으로 각각 처리한다. 대상 폴더의 기존 형제 파일이 루트에 바인딩된 지시문을 가릴 수 있으면 Starter 및 Starter/Engine 내보내기가 `include_output_collision`으로 중단된다.

`8fe6609`에서 저장한 두 종류의 디렉터리 경로 프로젝트와 한 줄·두 줄 지시문이 섞인 독립 소스 프로젝트를 다시 열고 내보내 15절점과 셸 연결을 확인했다. `/QUAD`는 2D 솔리드로서 `/GRQUAD/QUAD` 집합을 사용한다. 이전 독립 소스 아카이브의 절점·요소 대응은 원본으로 검증한다. OpenRadioss ALE2D 덱에서 `/QUAD` 요소 1의 집합을 내보내고 다시 열어 확인했다. D25 분할 미리보기는 양 끝점에 닿는 미선택 `/QUAD`, `/SH4N`, `/TETRA`를 여전히 거부한다.

Windows Python 3.13.5에서 지정 pytest 177건을 통과했다. 로컬 `document`는 1,347 통과·11 건너뜀·11 제외, Qt offscreen `qt-document`는 559 통과·2 건너뜀, `live-automation`은 141 통과·7 건너뜀이다.

### 일곱 번째 검토 수정

`bde82a5` 재검토를 반영했다. Starter를 작성하기 전에 내보낼 바이트와 대상 폴더를 합쳐 INCLUDE를 다시 해석한다. 파일 또는 지시문 바인딩이 달라지면 `include_output_collision`으로 중단한다. 활성 바인딩은 프로젝트에 보존하고, 다음 차수의 모호한 지시문을 처리할 때 앞서 확정된 참조를 반영한다.

`8fe6609`에서 직접 생성한 한 줄 전용 및 혼합 독립 소스 아카이브를 열고 다시 저장한 뒤 Starter로 내보냈다. 두 입력에서 15절점·7셸과 INCLUDE 소유권을 확인했다. `ac0a255`의 2절점 아카이브도 같은 경로를 통과했다. 독립 소스의 바이트는 실제 과거 작성 방식으로 검증한다.

`/QUAD` 파트는 2D 솔리드 속성을 받는다. `/GRQUAD/QUAD`는 해당 요소군에서 ID를 찾고 음수 항목을 제외 목록으로 적용한다. 해석 케이스 출력은 그룹 검사와 같은 진단을 사용한다. OpenRadioss ALE2D 입력에서 `/PROP/TYPE14` 할당, 셸 속성 거부 및 `/GRQUAD/QUAD` 출력 재열기를 확인했다.

Windows Python 3.13.5에서 지정 pytest 187건을 통과했다. 로컬 `document`는 1,357 통과·11 건너뜀·11 제외, Qt offscreen `qt-document`는 566 통과·2 건너뜀, `live-automation`은 141 통과·7 건너뜀이다.

### 여덟 번째 검토 수정

`8e85a66` 재검토를 반영했다. 기존 INCLUDE 경로가 내보낸 트리에서도 같은 대상을 가리키면 그 경로를 보존한다. 독립 소스 가져오기는 네이티브 열기에서 확정한 바인딩을 저장한다. 과거 아카이브의 매핑은 해당 작성 규칙으로 재현한 바이트와 대조한다. `ac0a255`가 작성한 아카이브의 세 지시문과 `8fe6609`가 작성한 한 줄 지시문 반복 사례의 형제 파일 바인딩을 재열기와 내보내기로 확인했다.

`/QUAD`의 속성 할당에는 Type 14 이름만 사용한다. OpenRadioss ALE2D 입력에서 기존 `LAW3`를 유지하며 검사기와 속성 할당 작업으로 단면을 바꿨다. 같은 파일에서 동일한 ID를 쓰는 셸과 2D 솔리드는 native 요소군으로 구분해 VTK 선택 강조와 맞춤을 확인했다. 반복·음수 그룹 항목은 원문을 보존하며 유효 멤버를 계산한다.

Windows Python 3.13.5에서 영향 범위 pytest 334건을 통과했다. 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 아홉 번째 검토 수정

`eaeceb5` 재검토를 반영했다. 내보내기는 Starter의 INCLUDE 해석 순서와 대소문자를 무시한 파일 조회를 사용해 필요한 지시문만 바꾼다. `8fe6609`로 생성한 반복 지시문 아카이브 두 건(각 15절점·7요소)과 `#enddata` 뒤에 지시문이 있는 아카이브(14절점·7요소)를 재열기·다시 저장·Starter 내보내기로 확인했다.

해석 케이스 내보내기는 요소가 있는 PART의 속성·재료를 할당 작업과 같은 검사로 확인한다. 요소 집합 편집기는 같은 파일에 같은 ID가 있는 SHELL과 QUAD를 native 요소군 이름으로 표시한다. Windows Python 3.13.5에서 관련 pytest 176건을 통과했다. 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열 번째 검토 수정

`45883d1` 재검토에서 확인한 9파일 모델은 상위 INCLUDE 지시문 하나를 수정하면 모든 바인딩을 유지한다. 수정 후보를 제한된 범위에서 개별·조합으로 시험하고, 바인딩 전부가 일치할 때 Starter를 내보낸다. 해석 케이스를 포함한 두 내보내기 경로를 작업 문서 재열기 전후에 확인했다.

소스 아카이브는 기록된 파일 순서와 매핑 바이트를 함께 확인한다. `8fe6609`가 작성한 반복 지시문의 형제 파일 바인딩과 `#enddata` 뒤의 `#include"nodes.inc"` 원문을 복원했다. `24137d6`, `987c52b`, `ac0a255`, `8e85a66` 작성본과 `8e85a66`으로 다시 저장한 `ac0a255` 작성본은 두 지시문의 기존 루트 파일 바인딩을 유지했다.

해석 케이스는 표시에서 제외된 요소의 PART 참조와 속성도 검사한다. 같은 native 요소 집합에 동일 ID가 두 개 있으면 생성 전에 거부한다. Windows에서 지정된 pytest 4개 모듈은 155건을 통과했고 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열한 번째 검토 수정

`a4b9059` 재검토에서 확인한 73파일·18절점 모델을 작업 문서 재열기 전후에 Starter와 해석 케이스로 내보냈다. 내보내기는 일치하는 INCLUDE 바인딩의 앞부분을 늘리는 개별 수정을 우선하고, 개별 수정으로 진행할 수 없으면 최대 256개 조합을 시험한다. 네이티브 재열기에서 전체 바인딩을 비교했다.

파일 순서와 매핑 바이트가 일치하는 과거 작성 규칙이 서로 다른 바인딩을 가리키면, 명시 바인딩이 없는 아카이브는 `invalid_project`로 거부한다. `8fe6609`, `987c52b`, `ac0a255` 작성본에서 거부를 확인했고 `8e85a66`으로 다시 저장한 작성본의 명시 바인딩은 유지했다. `8fe6609`와 `ac0a255`에서 생성한 공백 없는 활성 INCLUDE의 두 경로 형식도 재열기·내보내기로 확인했다.

공백으로 채운 PART ID를 읽을 수 있으며, 형식이 잘못된 절점·요소 행은 해석 케이스 내보내기 전에 거부한다. PART 할당과 요소 집합 검사는 화면에서 빠진 요소도 포함한다. Windows Python 3.13.5에서 지정된 pytest 4개 모듈은 164건을 통과했고 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열두 번째 검토 수정

`a0e9839` 재검토를 반영했다. `24137d6`의 루트 기준 INCLUDE 탐색과 `987c52b`의 형제 파일 탐색·경로 재작성을 각각 재현한다. `8fe6609`가 작성한 형제 파일 전용 INCLUDE의 네 조합에서 15절점·7요소와 바인딩을 재열기·내보내기로 확인했다. 동일 바이트에서 서로 다른 바인딩이 가능한 아카이브는 명시 바인딩이 없으면 거부한다.

25파일 모델에서 상위 지시문 아홉 개를 함께 수정해 Starter·해석 케이스 내보내기와 작업 문서 재열기 전후의 바인딩을 확인했다. PART 할당은 요소 행 전체를 읽을 수 없는 경우에도 카드 헤더의 요소 종류를 사용한다. 해석 케이스는 모든 절점·요소 집합을 검사한다. SHELL과 QUAD가 같은 ID를 쓰고 한 요소만 표시되는 두 Qt/VTK 사례에서 해당 요소의 강조와 맞춤을 확인했다.

Windows Python 3.13.5에서 지정된 pytest 4개 모듈은 172건을 통과했고 별도 EGL 렌더링 검사 1건은 건너뛰었다. 해석 케이스 추가 검사 20건을 통과했다.

### 열세 번째 검토 수정

`24ff5f2` 재검토를 반영했다. 덱 상태의 원래 버전을 검증 후 보존한다. `24137d6`가 작성한 두 v4 아카이브는 15절점·7요소와 루트 INCLUDE 바인딩을 유지했다. `8fe6609`, `987c52b`, `ac0a255`가 작성한 여섯 v5 모호 사례는 거부했다.

29파일 모델에서 한 파일에 이르는 두 INCLUDE 경로를 모두 보정했다. Starter, Starter/Engine, 해석 케이스를 작업 문서 재열기 전후에 내보내고 모든 바인딩을 비교했다. 가져온 `/GRNOD/NODE`의 중복 ID와 0 패딩은 멤버 계산 시 정리하며 원문을 보존한다. 직접 그룹 편집은 중복과 0을 거부한다. 20,000절점·96그룹 검사에서 검증 두 번에 원문 절점 ID를 한 번씩만 읽었고 메시 변경·Undo 후 캐시를 다시 계산했다.

Windows Python 3.13.5에서 영향 범위 pytest 8개 모듈은 326건을 통과했고 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열네 번째 검토 수정

`acd8a18` 재검토를 반영했다. 덱 상태 버전은 정수만 받고, v5에서 추가한 보존 주석 레코드는 이전 상태에서 거부한다. `24137d6` 작성본 두 개는 15절점·7요소와 루트 INCLUDE 바인딩을 유지했고, 모호한 v5 아카이브 여섯 개는 계속 거부했다.

`/GRNOD/NODE`의 0 패딩을 보존하면서 독립 소스 가져오기·그룹 편집 미리보기·절점 이동 미리보기를 확인했다. 빈 노드 그룹을 참조하는 BCS는 검사기에 `unverified: empty_node_group`으로 표시한다. `24ff5f2` 작성본에 기록된 과거 중복 멤버는 실제 노드별로 정리하며, 서로 다른 두 절점의 동일 대상 매핑에는 명시 승인이 필요하다.

덱 상태 토큰으로 원문 절점 ID 캐시를 확인한다. 자원 직접 복원과 필드 변경 이벤트 후 기존 ID가 거부됨을 검증했다. 20,000절점·96그룹 사례의 Windows 웜 검증 중앙값은 단일 파일 1.026 ms, 절점 INCLUDE 1.056 ms였다(각 55회, 전체 검증 성공). 집중 검사 29건과 전체 영향 범위 pytest 11개 모듈 389건을 통과했고, 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열다섯 번째 검토 수정

`2a82798` 재검토를 반영했다. 작업 문서 열기와 재연결에서 저장된 대상 종류를 실제 카드 키워드와 비교한다. `acd8a18` 작성본에서 삭제된 빈 노드 그룹이 원본에만 남아 있는 사례를 다시 열어 해석 케이스의 16절점·4요소를 재출력했다. 0만 있는 그룹과 밑줄이 포함된 정수 필드는 계속 거부한다.

덱 구조 토큰이 바뀌면 기존 메시 표시와 절점 소유권을 갱신한다. 자원 직접 복원과 기본 필드 변경 이벤트에서 절점·요소 연결·그룹의 새 ID를 확인했다. 재료 스칼라 편집의 표시 리비전은 유지한다. 20,000절점·96그룹 웜 검증은 단일 파일 중앙값 1.259 ms, 절점 INCLUDE 1.285 ms였다(각 81회 성공). 집중 검사 27건과 전체 영향 범위 pytest 13개 모듈 408건을 통과했고, 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열여섯 번째 검토 수정

`24c8a2e` 재검토를 반영했다. `2a82798`로 작성한 원본 노드 그룹의 밑줄 정수 사례 세 개를 다시 열어 16절점·4요소와 각 활성 그룹 상태를 내보냈다. `acd8a18`로 작성한 제목만 있는 원본 그룹 사례도 재출력했다. 새 가져오기와 메시 편집 미리보기는 빈 그룹과 밑줄 정수 필드를 거부한다.

자원 직접 복원과 기본 필드 변경 이벤트에서 이전 절점 선택을 제거한다. 다른 INCLUDE의 메시 좌표를 바꾼 뒤 첫 번째 이전 선택 요청을 거부했다. 교체된 20,000절점 덱의 재료 스칼라 편집 41회에서 구조 JSON 직렬화와 해시 호출은 각각 0회였고 표시 리비전은 유지됐다. 집중 검사 23건과 전체 영향 범위 pytest 13개 모듈 418건을 통과했고, 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열일곱 번째 검토 수정

`042d5e8` 재검토를 반영했다. `2a82798` 작성본의 절점 정의와 셸 연결에 밑줄 정수가 들어간 두 사례를 재열어 각각 16절점·4요소의 정수 ID를 내보냈다. 새 가져오기는 같은 입력을 거부한다. `acd8a18`으로 작성한 제목만 있는 그룹은 재열었고 동일한 원본·매핑에 0만 채운 사례는 거부했다.

기본 필드 변경 이벤트로 절점을 100 mm 옮기면 Qt/VTK 표시가 갱신되어 새 선택을 승인한다. 중복 절점 소유권과 같은 자원의 중복 요소 ID는 모호한 선택을 해제한다. 활성 PART의 요소 ID가 바뀌면 강조를 다시 계산한다. 직접 복원으로 그룹 또는 재료를 삭제한 뒤 요약과 선택 조회 결과가 일치한다. 교체된 20,000절점 덱의 스칼라 편집 41회에서 구조 직렬화·해시는 각각 0회였으며 표시 리비전은 유지됐다.

Windows Python 3.13에서 집중 검사 37건과 영향 범위 pytest 22개 모듈 555건을 통과했다. 별도 EGL 렌더링 검사 1건은 건너뛰었다.

### 열여덟 번째 검토 수정

`eb11392` 재검토를 반영했다. SH3N을 선택해 변을 분할하면 자식 요소를 선택하고 유일한 소유 PART를 활성 상태로 유지한다. PART 자체를 선택한 경우 기존 요소와 자식 요소를 함께 강조한다. 셸을 선택할 때 명시한 요소 형식을 유지하므로 같은 ID의 QUAD를 추가한 뒤에도 셸이 강조된다. 같은 형식과 ID의 요소가 추가되어 선택이 모호해지면 선택을 해제한다.

독립 원본 아카이브는 각 세대의 정수 표기와 절점 그룹 규칙을 원본 전체에 적용해 저장한 매핑 바이트와 대조한다. Pass 13–15 작성본 네 개를 다시 열고 케이스를 내보내 각각 16절점·4요소를 확인했다. 밑줄 정수와 0 패딩을 혼합한 아카이브는 거부했다. 새 가져오기에는 현재 규칙을 적용한다.

Windows Python 3.13과 Qt offscreen에서 영향 범위 25개 모듈 627건과 요소 편집 창 3개 모듈 64건을 통과했다. 별도 EGL 렌더링 검사 1건은 건너뛰었다. 교체된 20,000절점 덱의 스칼라 편집 41회에서 구조 직렬화와 해시 호출은 각각 0회였으며 표시 리비전은 유지됐다.

### 열아홉 번째 검토 수정

`611bf10` 재검토를 반영했다. 요소 형식을 명시한 화면 선택으로 요소 그룹을 만들고, 같은 선택 참조를 SH3N 변 분할·요소 삭제·셸 방향 반전·PART 재할당 미리보기에 전달할 수 있다. 분할한 자식 요소를 재할당하면 선택을 유지하고 새 소유 PART를 활성화한다. 요소가 절점 누락으로 화면에 표시되지 않더라도 원본 요소 ID의 중복을 검사해 선택의 모호성을 판단한다.

독립 원본 아카이브 검증에서 INCLUDE 작성 방식과 해당 세대의 정수·절점 그룹 규칙을 함께 적용한다. `2a82798`로 생성한 밑줄 절점 ID와 0 패딩 그룹이 함께 있는 아카이브를 포함해 Pass 13–15 작성본 다섯 개를 다시 열어 각각 16절점·4요소를 내보냈다. 0 패딩과 이전 세대의 따옴표 없는 두 줄 INCLUDE를 섞거나, 밑줄 정수와 0 패딩 및 제목만 있는 그룹을 섞은 아카이브는 거부했다.

Windows Python 3.13과 Qt offscreen에서 집중 검사 23건과 영향 범위 30개 모듈 730건을 통과했다. 선택 실행 EGL 검사 1건과 OCP 미설치 검사 3건은 건너뛰었다. Windows VTK 오프스크린 렌더에서 SHELL 1을 선택한 뒤 Qt Apply로 멤버가 1인 `/GRSHEL/SHEL/1`을 만들었다. 20,000절점 덱에서 스칼라 편집 41회 동안 표시 리비전은 유지됐고 구조 직렬화와 해시는 각각 0회였다.

### 스무 번째 검토 수정

`cd0be79` 재검토를 반영했다. SH4N과 TETRA의 별칭을 요소 선택 및 편집 검증에 적용한다. 연결을 읽을 수 없는 요소도 유효한 원본 ID가 있으면 중복 검사에 포함한다. Windows VTK offscreen에서 SH4N 201을 선택해 강조하고 삭제·방향 반전·PART 재할당을 미리봤다. 셸 8,000개를 선택한 상태에서 그룹 폼에 필요한 항목을 만드는 데 다섯 번 측정한 중앙값은 17.7 ms였다(16.0–18.7 ms).

원본 INCLUDE 연결 기록 유무와 덱 버전에 따라 해당 작성 세대의 규칙으로 아카이브를 검증한다. `ac0a255`의 QUAD 아카이브와 `2a82798`의 `0_0` 패딩 아카이브는 각각 케이스를 내보내고 다시 열어 16절점·4요소를 확인했다. 새 가져오기는 `0_0`을 거부하며, 이후 세대의 규칙을 덧붙인 이전 아카이브도 거부한다.

Windows Python 3.13과 Qt offscreen에서 집중 검사 28건과 영향 범위 30개 모듈 740건을 통과했다. 선택 실행 EGL 검사 1건과 OCP 미설치 검사 3건은 건너뛰었다. 20,000절점 덱에서 스칼라 편집 41회 동안 표시 리비전은 유지됐고 구조 직렬화와 해시는 각각 0회였다.

### 스물한 번째 검토 수정

`633ec1d` 재검토를 반영했다. 원본 연결 기록, 아카이브에 속한 덱의 버전, 해당 작성 세대의 요소 규칙을 함께 검증한다. `24137d6`과 `987c52b` 작성본은 열리고 QUAD를 끼워 넣은 변형은 거부된다. `ac0a255`의 QUAD와 Pass 14의 `0_0` 패딩 아카이브에서 각각 케이스를 내보내 16절점·4요소를 확인했다. `0_0`은 검증된 Pass 14 아카이브의 매핑 덱에만 허용한다. 새 RAD와 같은 프로젝트의 호스트 덱은 거부한다.

연결을 읽을 수 없는 TETRA10 행도 원본 ID 중복 검사에 포함한다. PART 선택은 표시에서 제외된 중복 요소를 확인하고, SURF/PART는 연결을 읽을 수 없는 QUAD가 포함된 PART를 거부한다. Deck A의 SH4N·TETRA가 케이스 출력 후 다시 열린다. Qt 요소 그룹 편집기는 모든 선택을 검증하며 명시적인 `formulation=None`도 올바른 선택 항목으로 처리한다. 셸 8,000개를 선택한 BeidPrep 폼을 열고 검증하는 시간은 다섯 번 측정한 중앙값 220.1 ms였다(213.4–247.0 ms).

Windows Python 3.13과 Qt offscreen에서 영향 범위 31개 모듈 769건과 목록 편집기 검사 6건을 통과했다. 선택 실행 EGL 검사 1건과 OCP 미설치 검사 3건은 건너뛰었다. Windows VTK offscreen에서 SHELL 1을 선택한 뒤 Qt Apply로 멤버가 1인 요소 그룹을 만들었다. 20,000절점 덱의 스칼라 편집 41회에서 표시 리비전은 유지됐고 구조 직렬화와 해시는 각각 0회였다.

### 스물두 번째 검토 수정

`9bb4262` 재검토를 반영했다. 검증된 Pass 14 원본에서 온 정확한 그룹 행에만 `0_0`을 허용한다. 작업문서의 원본 텍스트를 유지하고 Starter와 케이스 출력에 표준 `0`을 쓴다. 실제 Pass 14 작성본에서 BCS 71을 포함한 케이스를 내보냈다. 다시 연 그룹 48의 멤버는 812와 813이었으며 케이스를 재출력했다. 이전 작성본에 SH4N을 넣거나 `ac0a255`의 QUAD 매핑을 바꾼 변형은 거부했다.

TETRA10 연결 행이 누락돼도 다음 요소 ID부터 다시 읽고, 연결 행의 첫 절점을 요소로 색인하지 않는다. PART 선택은 동일한 원본 요소 번호 공간의 중복을 검사한다. SURF/PART도 같은 검사를 적용한다. 중첩 참조를 Qt 목록 편집기에서 선택하고 복원한다. 셸 8,000개를 선택한 BeidPrep 그룹 폼을 열고 검증하는 시간은 다섯 번 측정한 중앙값 284.1 ms였다(276.7–301.4 ms).

Windows Python 3.13과 Qt offscreen에서 집중 검사 42건과 영향 범위 32개 모듈 783건을 통과했다. 선택 실행 EGL 검사 1건과 OCP 미설치 검사 3건은 건너뛰었다. Windows VTK offscreen에서 SHELL 1을 선택한 뒤 Qt Apply로 멤버가 1인 요소 그룹을 만들었다. 20,000절점 덱의 스칼라 편집 41회에서 표시 리비전은 유지됐고 구조 직렬화와 해시는 각각 0회였다.

### 스물세 번째 검토 수정

`57fe70e` 재검토를 반영했다. 실제 `bde82a5` 작성본의 13개 원본 파일과 `E:QUAD 9007 → 9008` 매핑을 복원해 16절점·4요소의 케이스를 내보냈다. 해당 매핑을 E:SHELL로 바꾸거나 `ac0a255` 작성본을 E:QUAD로 바꾼 변형은 거부했다. `24137d6`과 `987c52b` 작성본의 TETRA 별칭 변형도 거부했다. Pass 14의 `0_0` 허용 범위는 원본 카드 UUID, 데이터 행, 필드 위치, 토큰으로 고정했다. 실제 그룹 48의 멤버를 813에서 814로 바꾼 뒤 `[812, 0, 814]`를 출력했고, 같은 번호로 새로 만든 카드는 원본 패딩을 가져오지 못했다.

PART와 SURF/PART는 표시되지 않는 요소까지 포함해 동일 자원의 원본 요소 번호 공간에서 중복을 확인한다. SURF/PART는 연결을 읽을 수 없는 요소가 포함된 PART도 거부한다. Qt 참조 목록은 해시로 후보를 찾고 값의 동등성을 확인한다. 셸 8,000개를 선택한 BeidPrep 그룹 폼을 열고 검증하는 데 다섯 번 측정한 중앙값은 303.2 ms였다(285.3–311.8 ms).

Windows Python 3.13과 Qt offscreen에서 집중 검사 47건과 영향 범위 32개 모듈 794건을 통과했다. 선택 실행 EGL 검사 1건과 OCP 미설치 검사 3건은 건너뛰었다. Windows VTK offscreen에서 SHELL 1을 선택한 뒤 Qt Apply로 그룹을 만들었다. 20,000절점 덱의 스칼라 편집 41회 동안 표시 리비전은 유지됐고 구조 직렬화와 해시는 각각 0회였다.

### 스물네 번째 검토 수정

`95849bf` 재검토를 반영했다. 요소 ID가 비어 있거나 참조 절점이 누락된 PART는 선택, SURF/PART 작성, TYPE7 대상 해석 및 케이스 내보내기에서 오류를 보고한다. PART 속성 편집은 계속 사용할 수 있다. 음수 요소 제외는 이를 지원하는 작성본에서만 복원한다. 실제 `24137d60`과 `987c52b8` 작성본에 `-9007`과 대응 ID `-9009`를 삽입한 변형은 거부했고, 이를 지원하는 `8e85a669` 작성본은 복원했다.

Qt 참조 목록은 Python 값 동등성으로 선택을 확인한다. Windows Qt offscreen에서 셸 8,000개를 선택한 폼의 열기와 검증은 중앙값 204.6 ms였다(5회, 202.5–217.4 ms). 20,000절점 덱의 스칼라 편집 41회에서 구조 직렬화와 해시는 각각 0회였고 표시 리비전은 유지됐다.

Windows Python 3.13로 집중 검사 104건과 영향 범위 32개 모듈 812건을 통과했다. 전체 실행에서 건너뛴 선택 실행 렌더링·피킹 검사 1건은 별도로 활성화해 통과했다. OCP 미설치 검사 3건은 건너뛰었다.

### 스물다섯 번째 검토 수정

`b6f1c0c` 재검토를 반영했다. `8e85a669`의 순차 INCLUDE 재시도 규칙을 복원했다. 해당 작성기로 만든 원본 7파일 보관본을 두 번 저장·재열고 케이스로 내보냈다. 절점 16개와 요소 4개, 원문 셸 그룹 `[9008, 9009, -9009]`와 유효 멤버 `[9008]`를 확인했다. 음수 제외를 삽입한 `24137d60`과 `987c52b8` 보관본은 계속 거부한다.

요소 ID나 참조 절점이 누락된 PART를 트리에서 클릭하면 진단과 재료·단면 편집을 표시한다. 표면·접촉·케이스 검증에서 오류를 반환하며 내보내기 파일과 리비전 변화는 없었다. Qt 참조 목록은 `set`·`frozenset`을 포함한 중첩 컨테이너의 Python 동등성을 적용한다. 셸 8,000개 폼을 열고 검증하는 시간은 Windows Qt offscreen에서 중앙값 252.5 ms였다(5회, 245.7–292.4 ms).

Windows Python 3.13에서 집중 검사 111건과 영향 범위 32개 모듈 821건을 통과했다. 선택 실행 VTK 렌더링·피킹 검사는 별도로 활성화해 통과했고 OCP 미설치 검사 3건은 건너뛰었다. 20,000절점 덱의 스칼라 편집 41회에서 표시 리비전을 유지했으며 구조 직렬화와 해시는 각각 0회였다.

### 스물여섯 번째 검토 수정

`82622b1` 재검토를 반영했다. `8e85a669`의 INCLUDE 재시도는 두 원본 파일을 같은 파일의 반복 피연산자 하나로만 설명해야 하는 경우를 거부한다. 같은 디스크 입력에서 `ac0a255`는 원본 4개, `8e85a669`는 3개를 수집했다. 실제 `ac0a255` 보관본은 열렸고 `E:SHELL 9007 → 9009` 태그만 `E:QUAD`로 바꾼 보관본은 거부했다. 실제 `8e85a669` 7파일 보관본과 별도 경로로 반복 대상에 도달하는 11파일 보관본, `bde82a5` 13파일 보관본은 케이스 내보내기와 재열기를 확인했다.

Qt 참조 목록은 읽기 전용 프록시를 포함한 표준 매핑과 집합에서 Python 동등성을 적용한다. 셸 8,000개 폼의 열기·검증 시간은 Windows Qt offscreen에서 중앙값 268.6 ms였다(5회, 257.9–298.4 ms).

Windows Python 3.13에서 집중 검사 131건과 영향 범위 32개 모듈 841건을 통과했다. 선택 실행 VTK 피킹 검사는 별도로 통과했고 OCP 미설치 검사 3건은 건너뛰었다. 20,000절점 덱의 스칼라 편집 41회에서 표시 리비전을 유지했으며 구조 직렬화와 해시는 각각 0회였다.

### 스물일곱 번째 검토 수정

`526a0c3` 재검토를 반영했다. `8e85a669` 보관본 검증은 당시 디스크의 INCLUDE 탐색을 웨이브 단위로 재현한다. 보관되지 않은 형제 경로가 원본 선택을 지연시킬 수 있는 경우만 탐색하며, 그 경로를 실제로 읽는 경우는 거부한다. `ac0a255` 보관본의 대소문자, 같은 웨이브의 추가 참조, 누락 파일 뒤의 참조 변형에서 바꾼 요소 매핑 태그를 모두 거부했다. 실제 7·11파일 `8e85a669` 보관본과 13파일 `bde82a5` 보관본은 케이스 내보내기와 재열기를 확인했다.

Qt 참조 목록은 매핑 프록시를 Python 동등성으로 비교하고, 해시가 같은 행 객체와 튜플을 같은 후보에서 찾는다. 셸 8,000개 폼의 열기·검증은 기존 0.5초 단언을 유지한 독립 실행 5회에서 중앙값 208.4 ms였다(190.0–224.7 ms). 모든 실행에서 선택된 참조 8,000개가 일치했다.

Windows Python 3.13에서 집중 검사 146건과 영향 범위 32개 모듈 856건을 통과했다. 선택 실행 VTK 피킹 검사는 별도로 통과했고 OCP 미설치 검사 3건은 건너뛰었다. 20,000절점 덱의 스칼라 편집 41회에서 표시 리비전을 유지했으며 구조 직렬화와 해시는 각각 0회였다.

### 스물여덟 번째 검토 수정

`4ae3028` 재검토를 반영했다. 보관된 INCLUDE 방문 순서로 누락된 형제 파일을 추론한 뒤, 고정한 파일 배치에서 방문 순서와 원본 목록을 함께 검증한다. 보관본에서 확인되는 디렉터리와 파일 아래에 가상의 파일을 둘 수 없다. `ac0a255`의 디렉터리·순서 변형에서 바꾼 요소 매핑 태그를 거부했다. 실제 `8e85a669` 작성기로 만든 79파일 보관본은 저장·재열기와 케이스 내보내기 후에도 절점 16개, 요소 4개와 원본 그룹 `[9008, 9009, -9009]`를 유지했다.

Qt 참조 목록은 반환하는 가변 값을 복사한다. 정렬한 뒤에도 선택한 행의 참조와 유효성을 유지한다. 일반 딕셔너리와 같은 동등성 규칙을 쓰는 읽기 전용 매핑은 같은 방식으로 후보를 찾는다. Windows Qt offscreen에서 8,000개 셸 폼은 중앙값 252.6 ms(232.4–271.9 ms), 8,000개 매핑 프록시 목록은 중앙값 194.5 ms(170.2–217.1 ms)였다. 각각 독립 실행 5회 모두 0.5초 미만이었다.

Windows Python 3.13에서 집중 검사 153건과 영향 범위 32개 모듈 863건을 통과했다. 선택 실행 VTK 피킹 검사는 별도로 통과했고 OCP 미설치 검사 3건은 건너뛰었다. 20,000절점 덱의 스칼라 편집 41회에서 표시 리비전을 유지했으며 구조 직렬화와 해시는 각각 0회였다.

## D03 표시 갱신 원자화 (PREP:N17 부분 개선) — 2026-11-18

코드 커밋 `64fa6115d37853b062cdd53cf78e5b667f8f8fd6`(브랜치 `feature/prep-d03-atomic-visibility`)에서 `MeshViewport.set_hidden_parts` 및 `_apply_visibility()` 대칭차(`_hidden_parts ^ _applied_hidden`) 단일 패스(`src/caelab_prep/ui/viewport.py`), `PrepController._apply_display_state`의 단일 `set_hidden_parts(hidden)` 호출(`src/caelab_prep/ui/prep_controller.py`), 무변화 no-op 조기 반환을 구현해 숨김·고립·전체 표시 전환 시 중간 전체 모델 노출(`show_all_parts` 후 `hide_parts`)과 중복 `render()` 호출을 제거했습니다(기존 4개 테스트 더블의 레거시 목업 호환 분기 유지, 프로덕션 `MeshViewport` 호출자는 모두 `set_hidden_parts` 사용).

- **단위·통합 검증 (`QT_QPA_PLATFORM=offscreen`)**: `tests/test_viewport_visibility.py`, `tests/test_tree_appearance.py`, `tests/test_viewport_scaling.py`, `tests/test_modeling_ui.py`, `tests/test_conditions_ui.py`, `tests/test_courant_workspace.py`, `tests/test_gui_document_flow.py` 전체 **101 passed, 1 skipped** (`test_egl_render_and_pick_visible_cells`는 Linux EGL `CAELAB_TEST_EGL=1` 전용으로 skip). 오프스크린 `vtkRenderWindow` (`SetOffScreenRendering(1)`) `EndEvent`·`GetRGBACharPixelData` 차분·실제 `MainWindow`/`PrepSession`/`QAction`/선택/Undo 무변경 확인 포함.
- **100만 요소·100 part·20 source·100회 숨김/표시/고립 벤치마크 (`QT_QPA_PLATFORM=offscreen`, `vtkWin32OpenGLRenderWindow` `SetOffScreenRendering(1)`, 800×600, 활성 요소 선택 1건 포함)**:
  `elements=1,000,000`, `nodes=515,100`, `parts=100`, `ops=100`, `renders=100`, `never_rendered=0`, `p50=55.432 ms`, `p95=97.601 ms` (< 200 ms), `max=106.555 ms`.
- **미완·구분 범위 (N17 전체 미종료)**: 선택·값 편집·열기/재열기 지연 비용(기존 773 ms / 21.1 s)과 **실제 Windows 데스크톱 GPU 대화형 화면(`QVTKRenderWindowInteractor`)**은 이번 작업에서 검증하지 않았으므로 아래 N17의 부분 구현/검증 상태와 7/16/3 분류는 그대로 유지합니다(`D24` / `D33` 후속).

## 기존 계획과 재료 연구 후속의 연결 — 2026-11-12

이번 변경은 [기존 실행 단계](docs/execution-stages.md#research-integration)·[WB 재사용 계획](docs/workbench-reuse-plan.md#material-expert-rp-followup)·[적용 인계](docs/material-research-implementation-handoff.md)를 WB의 새 12개 세부 작업에 연결한 문서 갱신입니다. 새 제품 기능은 구현 예정이며 문서 병합으로 구현 진도를 올리지 않습니다. 구현 담당·독립 QA·달력 날짜는 아직 미정입니다.

기존 N01–N26와 7/16/3 분류는 유지합니다. N16의 원자 명령, N19의 owner IPC, N20의 실제 MCP client, N21/W3 실행은 확인한 범위를 재사용하고 새 모델 Apply·AI·수치 판독·RP 완료로 전용하지 않습니다. N03–N10의 8제품 비교, N11 연속 과업, N12–N14 Windows/새 설치/두 앱 조합, N17 대용량, N18 나머지 메시 수정, N22–N26 조건부 메시 실증의 잔여는 보존합니다. 새 12개를 기존 26행에 더해 진행률을 계산하지 않습니다.

PREP01의 첫 LAW1 E 연결과 여러 시험에서 얻은 전체 계수·곡선·축 적용을 구별합니다. 계산·동정·FE 재평가·native 내보내기·Apply는 모델/솔버/판본별로 따로 지원을 판정합니다. 원자 Apply 미지원 시 native exporter가 별도로 검증된 경우에만 덱 내보내기를 허용합니다. 일반 보고서를 솔버 덱으로 표시하지 않습니다. Windows는 기존 일괄 후속으로 유지하고 독립 가능한 개발을 진행합니다.


## 2026-11-12 전체 재료 연구·자문·후처리 연결 명세 갱신

Workbench의 전체 구현 명세와 Prep가 담당할 작업을 [연결 작업서](docs/material-research-implementation-handoff.md)에 정리했습니다. Prep는 이미 열린 문서, 형식이 지정된 솔버 카드 편집, 명령·실행 취소(Undo)·솔버 입력 덱 내보내기, 공용 Qt 숫자·곡선·속성 위젯을 계속 소유합니다. Workbench는 공용 최적화 도구, 시험·평가 서비스, 전문가 자문, 외부 후처리 프로그램 연결을 맡습니다.

이번 변경은 명세 갱신이며 새 제품 코드의 구현이 아닙니다. 기존 LAW1·LAW36 편집이나 프로세스 간 통신(IPC)·모델 문맥 프로토콜(MCP)이 있다는 사실만으로 모든 재료 카드 또는 대규모 언어 모델(LLM) 자문 연결이 완료됐다고 판단하지 않습니다. Drucker–Prager(DP)와 Xia는 여러 재료군 중 예시입니다. 각 모델의 정확한 연결 모듈·계산 구현·출력·검증·내보내기 지원 여부를 따로 관리합니다. 원래 Xia2002 모델, LAW112, 이번 GMN2012 기반 파생 XBP는 서로 구분합니다.

## 사용자 기능 점검 — 2026-11-12

**범위 정정:** DP와 Xia는 여러 재료 모델 중 예시입니다. 여러 재료를 모델링하고 시험자료로 계수를 찾는 동정·최적화를 위해 모델별 연결 모듈을 둡니다. 공통 구현 규칙과 처음 구현할 작업은 [WB 통합 구현 명세](https://github.com/pikachu444/caelab-workbench/blob/main/docs/specs/spec-cae-research-implementation.md)를 따릅니다. Prep는 솔버 카드·문서·명령·실행 취소(Undo)·내보내기를 계속 소유합니다.

점검 기준은 원격 main `f40bfea307e4c2134cb8c4ae61864b629fda5c60`, 연결 Workbench는
`1c1cacb85018fd080c42f4d475812669b71cae90`이다. 아래 과거 진행 기록의 SHA는 해당
구현·실행 당시 기준이며 최신 main과 구분한다. [최신 main CI](https://github.com/pikachu444/caelab-prep/actions/runs/42559182326)는
문서 Ubuntu/Windows·Qt·실제 렌더·CAD worker·구조화 recipe·solver 등 10작업 성공이다.
Windows document 작업의 성공이 OS 실조작·새 설치·원제품 T1–T6 비교의 완료는 아니다.

| 사용자 작업 | 현재 구현 | 남은 범위 |
|---|---|---|
| 모델 작성·저장·출력 | 지원하는 RAD 재료·단면·집합·조건·케이스를 편집합니다. 메시 채택·제한 수정, Undo, 저장·재열기, Starter/Engine 내보내기를 지원합니다. | 모든 재료법·모든 키워드의 지원과 일반 CAD 조건의 자동 복원은 미완료입니다. |
| DP·Xia 재료 정의 | 지원 카드의 원문을 보존합니다. 구조화 편집은 LAW1·LAW36의 기존 지원 필드에 한정되며, 새 재료 생성은 LAW1입니다. | DP 및 Xia/LAW112 전용 계수·검증·곡선 연결은 없습니다. 목록에 있다는 이유만으로 모델링을 지원한다고 표시하지 않습니다. |
| 시험곡선·계수 최적화 | 공용 표·곡선·단위 위젯과 CSV 입력을 재사용할 수 있습니다. | 시험값의 의미 변환, 여러 시험의 잔차, 계수 보정 실행은 Workbench가 후속 구현합니다. Prep에서 곡선을 편집할 수 있다는 사실만으로 재료 보정이 완료됐다고 판단하지 않습니다. |
| 자동화·전문가 연결 | 독립 명령줄(CLI), 열린 프로세스와의 통신(IPC), 선택적 MCP 연결 모듈이 있습니다. | Workbench 전문가의 검색 증강 생성(RAG)·도구 호출 연결과 독립 공학 검토는 별도로 아직 구현하지 않았습니다. |
| Hex8·형상 검사 | PR70의 Hex8 단면 선택/지원 recipe, 창 배치·Preview 후 Apply 활성화·제한 blend 후보 검토 | 범용 all-hex·washer 요소 생성·일반 형상 정리·N25 전체 완료 아님 |

재료 보정·자문·RP 후처리에서 각 프로그램이 맡을 일과 다음 작업은 [Workbench 재사용 계획](docs/workbench-reuse-plan.md#material-expert-rp-followup)에 추가했습니다.
기존 7/16/3행 분류와 N01–N26 종료 판정은 이 조사로 변경하지 않는다. 열린 PR은 점검 시점 0건이며,
#26/#28/#43/#47/#48/#50의 미병합 종료는 해당 전체 기능의 완료 근거가 아니다.

이 문서는 N01–N26의 상태·완료 기준·다음 작업의 정본이다. 요구는 [DESIGN](DESIGN.md#delivery-goals), 현재 코드 계약은 [ARCHITECTURE](ARCHITECTURE.md), 단계별 입력·산출물은 [실행 계획](docs/execution-stages.md)을 따른다.

기존 기능의 통합 이력 기준은 Prep main `d5aaa76b49dcbfaf41dc4a9720958ce1f0e7ea62`다. PR37 최종 검토 `3ff6eda709da0405411965cb452b2091c1f15755`의 Git 부모·동일 tree·PR merged 상태를 확인했다. PR29의 첫 절대좌표 이동, PR32의 설정 격리·빌드 도구, PR27/34의 제한 quad/sweep hex 연결, PR35의 명시 집합 검토와 PR36의 BEAM merge guard를 포함한다. 이후 명시 native merge의 제품 기준은 API `e32b62d538c83de600aa9a679447875cabbd64f6`·GUI `b7c5446a656c58f9f68d2ba5884f722a1cee3792`이며 아래 N18에서 별도 기록한다. PR32 당시 N13 로컬 후보는 `b3a1c6a058a79fbe4af40dd2781f23d1f3c71ce4`, N18 집합 검토는 API `64cdcc102e993777229e8ef78472d8f221354f9f`·GUI `22284aa2989a632be295cd86b43a6c056a6dea9e`·복구 안내 `6791da9e0fe50166702a87d503af1436b2ffc234`를 구분한다. Workbench는 이 문서에서 대신 판정하지 않으며 [소유 경계](docs/workbench-reuse-plan.md)를 따른다.

2026-11-03 재개: [Gemini 공식 배정6592941640](https://github.com/pikachu444/caelab-prep/issues/19#issuecomment-6592941640)을 읽고 [범위 회신6593271212](https://github.com/pikachu444/caelab-prep/issues/19#issuecomment-6593271212)을 게시했다. UI·메뉴·브랜딩은 총괄 소유로 유지하고 Prep root가 PR38 코어·관련 검사·공식 런처 자산 조사만 재개했다. 현재 로컬은 PR38의9cf5241과 main UI39 `cbcc5fe98dfe75f7015244aa3248e39f92050e1a`를 합친 `e3b9e1d6e60748c5da7e3c91933d51fb7632fd51`에서 출발했다. 들어온 문서 dirty는 보관하고 CourantPrep 브랜딩 dirty는 변경·stage하지 않았다. 아래 코어 후보의 제품 SHA는25d4a9a, 강화된 native 출력 재파싱 검사는82f8fa0이며 새 최종head CI는 게시 뒤 [PR38 checks](https://github.com/pikachu444/caelab-prep/pull/38/checks)와 같은 보관처 acceptance에 정확 SHA로 연결한다. 이전 인계 중단 기록과 당시9cf의 CI를 이 재개 head의 통과로 쓰지 않는다.

<a id="remaining-work"></a>

## 남은 작업과 완료 기준

지원 범위의 구현·병합 7행, 제품·플랫폼 부분 구현/검증 16행, SDK·연구 부분 실증 3행이다. 부분 구현 16행에는 N13의 로컬 후보, N18의 집합 검토·명시 native merge와 N24/N25의 제한된 공통 채택 API/GUI가 포함된다. N03–N10·N12–N14·N22–N26의 외부 비교/Windows/SDK 조건은 다른 분류와 겹치므로 별도로 더하지 않는다. 한 행의 제한된 성공은 R1–R4 또는 G0–G4 전체 완료가 아니다.

| ID | 작업 / 기존 요구 | 구현 결과 | 실제 검증 / 확인 작업 | 완료 기준·외부 조건·대안 |
|---|---|---|---|---|
| N01 | 케이스·영속 해석 설정 / G2 T4 | **지원 범위 구현·병합.** PR17의 제품 코드는 `0aaada4`, 최종 검증은 `323954f`, 병합 main은 `8ff16c3`이다. `analysis_cases.py`/session/공용 dialog의 영속 UUID·명시 조건 활성 집합·단위 있는 시간/출력 설정, 해당 PR 당시 v3 저장(v1/v2 읽기). 현재 codec은 [저장 계약](ARCHITECTURE.md#작업-파일과-native-덱)을 따른다. | `test_analysis_cases*`, CLI 새 프로세스, 8방식 진입, 실제 X11 10검사와 두 케이스 Starter/Engine의 다른 시간·운동량/에너지 확인. 파일 선택 중 변경·삭제된 케이스 거부도 재검사. | 정확한 최종 SHA의 CI와 독립 리뷰를 통과해 해당 지원 family의 구현을 병합했다. N11 규모·N12 Windows·N03–10 원제품은 별도. 미지원 물리 조건은 fail closed하며 지원 확대를 예제로 대체하지 않음. |
| N02 | 외부 독립 메시 import / G3 T5 | **지원 범위 구현·병합.** PR17의 제품 코드는 `0aaada4`, 최종 검증은 `323954f`, 병합 main은 `8ff16c3`이다. CAD와 독립 출처 validator, real MSH+manifest와 hash/명시 단위/CAD identity 없음. 기존 SDK inventory를 검증한 뒤 공통 NativeMesh·품질·채택·Undo·저장·출력으로 연결한다. | core/SDK/8 UI 51, 기존 CAD52, 실제 X11 2, 실제 솔버2 검사. 독립 개발검증자료의 동등 fixture로 비연속 ID와 quad 원본 inventory 보존·채택 차단을 재현(원본 scratch 파일 직접검사 아님). overlap 집합/무그룹 part/하위 경계 node-set 보존. | 첫 지원 MSH2.2/4.1 ASCII tri3/tet4. [cad] Gmsh4.15.2·libGLU 필요. 단위 불명/불일치·지원 안 되는 family/binary 등은 전체 거부. 최종 CI를 통과한 첫 형식을 병합했다. 후속 family는 N22–N26에서 관리하며 가짜 XAO나 느슨한 CAD 검증으로 우회하지 않는다. |
| N03 | HyperMesh 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N04 | PrePoMax 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N05 | Naksha 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N06 | Abaqus/CAE 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N07 | COMSOL 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N08 | midas NFX 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N09 | MIDAS MeshFree 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N10 | BeidPrep 동일 과업 비교·UI 보완 / R2·R4 | **공통 사용자 흐름 구현, 원제품 비교 미완료.** 당시 접근 조사와 현재 Windows 미확인은 아래 공통 기준으로 구분한다. | [같은 T1–T6의 공통 확인 기준](#product-comparison)을 해당 제품 버전에서 수행한다. | 설치본·사용권·실행 환경을 확인한 뒤 원제품과 Prep의 같은 연속 작업·파일·전체 창을 비교한다. 미확인 칸은 보류한다. |
| N11 | 대표 사용자 모델의 연속 native 작업 / G1–G3 | **대표 조립의 정상 native 종료 확인, 전체 과업 근거 대조는 진행 중.** PR #22에서 16,645 node 집합의 입력 잘림을 수정했고, PR #25 `30578cdb`를 main `3ceaf44`에 병합했다. 실제 GUI의 생성·할당·조건·후보·저장·새 프로세스 재열기·출력과 같은 의미의 공개 CAD 입력을 독립 Ubuntu에서 재현했다. | 64,308 tet / 16,645 node / 18 part. [CI 41372762449](https://github.com/pikachu444/caelab-prep/actions/runs/41372762449) 9 jobs 통과. exact와 관측 Engine 모두 정상 종료, Starter 오류·경고 0. native 5.546초/120초, 준비 18.719초 별도. 독립 입력/로그/40개 파일 해시 및 질량·운동량 1.43e-8, 에너지 2.83e-7 상대오차 확인. [실제 산출물](https://github.com/pikachu444/caelab-prep/actions/runs/41372762449/artifacts/13110221948). | 로컬 종료 오류 원인은 아직 미확정이며 해당 실패를 보존한다. N11 전체를 닫기 전에 서로 다른 두 사용자 흐름과 C의 2만–10만 요소·국부 size·공유/독립 경계 근거를 정확 입력별로 대조하고 빠진 실행을 완료한다. 이 병진 검증을 접촉/응력/수렴·상용 동등성·Windows로 확대하지 않는다. |
| N12 | Windows GUI 실측 / R4·G1–G4 | **Windows 실제 GUI 후속.** PR #24 `a9e9e8af` 준비 러너는 main `89bd700`에 병합했다. CLI/pytest와 실제 과업 coverage를 분리하며 실제 GUI 항목은 unexecuted다. 현재 Linux/X11 결과와 과거 A7은 대체 증거가 아님. | 동일 최종 SHA에서 입력/한글IME/DPI100·150·200%/작은창/도킹재시작/GPU/T1–6를 실제Windows창으로 수행. | 접근 가능한 Windows desktop·GPU·입력/캡처 필요. 사용자 후속 지시 유지; 패키지와 재현 절차는 먼저 준비하며 Linux 구현은 계속한다. |
| N13 | Windows 배포 묶음·새 설치 / G4·P9 | **로컬 portable 후보·설정 격리 구현, 납품 미완료.** [PR32](https://github.com/pikachu444/caelab-prep/pull/32)의 source/tooling `b3a1c6a`로 EXE/DLL을 빌드했다. `gui/gallery --settings-file`은 명시 INI·fallback 비활성화를 사용한다. Analysis의 실제 입력 해시와 선택 venv/정확한 build-tool 출처, 설치 고지 146개·미확보 조건을 기록한다.  후속 packaging `1352c10772b3ff8a5d48537dc79582a5f5bed0c1`은 QtGui의 미사용 VirtualKeyboard/PDF image plugin 두 개만 Analysis 전에 제외한다. 애플리케이션 source SHA는 기존 b3로 고정하고 entry/tooling 변경은 분리해 비교했다. [인도용 archive 단계](#n13-portable-archive-progress)는 source/packaging SHA·inventory를 검증한 ZIP과 경로를 제외한 요약을 생성하며 전체 납품은 미완료다. 현재 source0ada의 새 후보와 [PR57](https://github.com/pikachu444/caelab-prep/pull/57)(정상 병합 `f6a4488`) packaging `2168300`의 Win32 경로 보완·MCP metadata 확인은 [후속 검증](#n13-mcp-packaging-progress)에 연결한다. | 새 source/venv는 독립 offscreen 정상 닫기→새 process INI 복원과 오류 경로를 통과했다. 새 EXE는 옵션 도움말·잘못된 INI 경로 4건만 확인했다. [CI 41480263514](https://github.com/pikachu444/caelab-prep/actions/runs/41480263514) 10 jobs 통과. 원지적자와 독립 QA의 수정·산출물 재확인 완료. 이전 `46cea514/8525686`의 worker·파일·자동 재열기·WM_CLOSE 성공은 재사용하며 새 EXE에서 반복한 결과로 세지 않는다. 공급자 STEP PLC 실패도 이전 범위의 source 재현 결과다.  관련7 source검사와 새 build1회에서 두 plugin·연결 Qt DLL7개가 빠졌고 남은 plugin20/필수 출력 DLL7의 hash·앱 module 입력66개가 기존과 같았다. 새 EXE63397b73의 offscreen 시작1/public describe1도 통과했다. source검사에는 missing-recipe 음성 dispatch1이 포함되며 frozen/native worker·저장/reopen/WM_CLOSE·solver는 반복하지 않았다. 원 ZIP/manifest는 불변이고 근거·pinned tooling은 `C:/Users/pikac/.codex/visualizations/2026/11/03/prep-portable-qt-plugins-1352c10/verification-summary.json`에 연결한다. | 새 frozen GUI의 유효 INI 저장/재열기, 깨끗한 Windows 환경, OS 실조작·실화면/VTK 판정, 전체 Qt/전이 바이너리 재배포 조건과 MCP의 Windows published-client 전체 상호운용·편집/작업은 미확인이다. 후속 후보의 기본 stdio initialize/list/조회5확인은 해당 전체 흐름과 구분한다. 분석 입력 기록을 전이 빌드의 bit-identical 재현 보장으로 확대하지 않는다. public release나 N13 종료가 아니며 같은 호스트 실행으로 새 설치를 닫지 않는다.  새 startup은 자기 Popen43052 tree를 강제 종료하고 해당 Popen만 wait한 범위다. 정상 닫기/INI 복원이 아니며 자식별 독립 reap은 미기록이다. 이전 source b3에 없던 추가 structured worker의 Analysis ERROR도 당시 기록으로 보존한다. 후속 source0ada의 module 수집·기본 GUI/stdio도 실제 전체 기능 지원으로 확대하지 않는다. |
| N14 | Windows 실제 Workbench W1/W2 / G4 | **Windows W1/W2 후속.** 실제 Workbench NumericEdit와 독립Prep 파일전달 구현은 있음. | 호환 Prep/WB SHA 쌍을 고정해 host 값/이력 소유, 오류복원·손상파일·재시작·한글/공백경로와 독립 문서 전달 확인. | 동일Windows납품환경 필요. Linux 교차앱 회귀/파일 검사는 계속, W1/W2를 N21 W3 계산 완료로 합산하지 않음. |
| N15 | RAD·중립 CSV와 곡선 앱 완성 / G2 T3·P4 | **지원 범위 구현·병합.** PR17의 제품 코드는 `0aaada4`, 최종 검증은 `323954f`, 병합 main은 `8ff16c3`이다. 중립 curve_csv와 같은 표/plot 초안, 파일preview/import/export, drag release 한 Undo/Escape 취소. | 실제 X11 24검사: 두 host/8표현, 파일 chooser/overwrite취소, 2곡선 CSV+작업문서 왕복·RAD/VTK 없는 프로세스. HyperMesh/Naksha plot 잘림을 수정 후 실제 화면 재확인. | 정확한 최종 SHA의 CI를 통과해 구현을 병합했다. CSV는 두수치열/선택x,y헤더, 단위와 참조는 문서가 소유하며 자동 환산하지 않는다. 전문 GUI 전체 품질/원제품/Windows는 별도 행. |
| N16 | 혼합 조립·다중 자원 관계 / P6b·B1–B4/B6 | **명시 범위 구현·병합.** PR #20 최종 `1cf604e`, main `a9e5cf0`. 다중 자원 단일 publish/Undo, source archive·명시 ID mapping, mixed DOF/좌표계, prepared 교체·stale 재연결, 참조 instance와 해당 PR 당시 v5(v1–v4 읽기)를 실제 GUI에 연결했다. 현재 codec은 [저장 계약](ARCHITECTURE.md#작업-파일과-native-덱)을 따른다. | [최종 CI 41374423889](https://github.com/pikachu444/caelab-prep/actions/runs/41374423889) 9 jobs 통과. 실제 X11 97 passed, Qt 283 passed/2 skipped, 실제 solver 8 passed는 서로 별도 실행이며 합산하지 않는다. 비작성자 검토·실제 두 mixed native·실패 원자 복원 근거를 확인했다. 초기 CI의 테스트 소유권/표현 혼동을 실제 Qt 수명·physical cell 출처 단언으로 고쳤다. | instance는 표현/조회/생성·삭제/저장이고 placement/geometry 복제는 아니며 미전개 instance는 native 출력 차단. N17 성능·일반 접합 동역학·N18 여섯 수정으로 확대하지 않는다. 공통 코어의 다음 편집자는 인수 측 한 명으로 지정한다. |
| N17 | 대용량 배열·지연 UI·저장 / P6c·B5 | **동일 100만 요소 baseline/개선 측정 완료 및 D03 표시 갱신 원자화 구현, 전체 N17 미완료.** 100 part·20 source를 유지했다. 측정 snapshot과 실제 p95는 보존하며 immutable projection·owned payload·PART context 개선은 PR #20에 병합했다. [PR #26](https://github.com/pikachu444/caelab-prep/pull/26)에 고정 입력 생성기·측정 harness·원자료·당시 source ZIP을 보존한다. 이후 `64fa611`에서 `MeshViewport.set_hidden_parts`·`PrepController._apply_display_state` 단일 대칭차 갱신으로 중간 전체 표시·중복 렌더를 제거했다. | mesh_view의 전체 buffer 공유를 확인해 4.5/5.1초가 36/22µs로 줄었다. 이전 Qt 선택 p95 773ms, 값 변경 126ms, Undo 130ms, 숨김/표시 724/750ms는 예산을 넘었다. D03(`64fa611`) 적용 후 `QT_QPA_PLATFORM=offscreen` + 오프스크린 `vtkRenderWindow` (`SetOffScreenRendering(1)`) 100만 요소·515,100 절점·100 part·20 source·100회 전환 실측에서는 `renders=100` (`never_rendered=0`), `p50=55.432 ms`, `p95=97.601 ms`, `max=106.555 ms`를 기록했다(관련 Qt/VTK 테스트 101 passed, 1 EGL skipped). | Linux 8GiB/소프트웨어 렌더·오프스크린 측정과 실제 Windows 데스크톱 GPU 대화형 화면을 구분하며, 남은 UI 선택·열기/재열기(21.1/22.1초)·초기 index 비용을 `D24`/`D33`에서 분리 개선·인수한다. 요소 수나 기존 4절의 예산을 낮추지 않고 N17 전체 완료로 닫지 않는다. Windows/GPU·취소는 미확인이다. |
| N18 | 일반 메시 수정·조건 재연결 / P7b | **이동·집합 검토·native merge/반전/삭제/PART 이동·참조된 CAD 후보 교체의 제한 구현·검증, 전체 P7b 미완료.** [PR61](https://github.com/pikachu444/caelab-prep/pull/61)·코드 `7ba062457fbfe79316bef0357b02d6c391f96a09`의 [CAD 교체·재연결 근거](#cad-replacement-progress)는 기존 root 소유/명시 stale 범위이며 전체 CAD topology 추적·물리 경계 복원이 아니다. 원본 CAD 경로 보호와 순수 상태 준비의 후속 [PR60](https://github.com/pikachu444/caelab-prep/pull/60) `43f4ef8a0e6b59f877d0ab1394ebd022f0a49b07`은 [별도 확인](#adoption-source-progress)에 연결한다. 아래 PR38 이력·보류 범위는 당시 기록으로 보존한다. PR29 최종 `89ef36b`·병합 `e929bcd`의 이동/희소 NODE/geometry review를 유지한다. [PR35](https://github.com/pikachu444/caelab-prep/pull/35) 최종 head `f6adc16b2c2a5d65bf94b314daf16dde4188c1e9`·병합 `36d1e71c4847421611a2e228b7bd9cfa432fbd74`의 API `64cdcc102e993777229e8ef78472d8f221354f9f`·GUI `22284aa2989a632be295cd86b43a6c056a6dea9e`·복구 안내 `6791da9e0fe50166702a87d503af1436b2ffc234`는 같은 editor의 선택적 Preview change와 명시 절점·요소 집합 멤버 검토를 기존 set_group_members/한 Undo/v6에 연결한다. closed-profile 밖 preview는 거부하되 기존 Apply/inspector는 유지한다. geometry generation/stale을 새로 만들지 않고 기존 stale을 차단한다. [PR36](https://github.com/pikachu444/caelab-prep/pull/36)의 guard `618f4f39c57980754080c951b8f5d67c19b71a52`는 main `45aeb80255ebdf2a3b75107cea7b3c11fcd798aa`에 병합했다. 명시 BEAM 방향절점이 끝점이 되어 조용히 default frame으로 전환되는 merge를 거부한다. 후속 native API `e32b62d538c83de600aa9a679447875cabbd64f6`·GUI `b7c5446a656c58f9f68d2ba5884f722a1cee3792`는 명시 pair·tolerance·PART/source/contact 허용, NODE 제거/연결·방향점 재배선, 전체 native inventory 대조·한 publish/Undo/v6와 8표현 공통 Action을 연결한다. 원 대상은 자동 변경하지 않고 stale로 보존한다. PR37 당시 many-to-one 축약은 거부했다. 후속 후보 `17c35d2f55e6422e5fc0d0c5f96fbf0fe0a386b3`는 merge의 trial 투영과 기존 재연결의 opt-in Preview/Apply를 연결한다. 최종 typed mapping 전체를 검증하고 old 링크·현재 선언·최종 집합과 CLOAD/INIVEL을 검토한 sealed states만 한 Undo/v6로 적용한다. 다른 stale 그룹과 기존 replacement 밖 layout의 제한은 유지하며 전체 P7b는 미완료다.  재개 코어 `25d4a9a5a1b74e7bef3aa1f4ae561c779f5d4f4f`는 유한 정수 좌표 거리의 overflow, BEAM 방향 외적의 overflow/underflow 판정, 미변경 연결 칸 정규화를 수정했다. source/keeper의 정확 거리≤공차와 기존 지원·명시 허용 경계를 유지한다.   추가 [PR51](https://github.com/pikachu444/caelab-prep/pull/51)의 셸 반전 API `c469122d21ec337ed7c7a832b58bf7703d24f9a8`·UI `062018e070193a1ca29fbc7f7f9316f06ec4e8cb`·잠금 표시 교정 `64c74c2d0703d9ab089fc2fa0e484e1fac9ca375`는 기존 순수 후보를 source-qualified 목록/Preview·한 Undo·v6·stale/export 경로에 연결했고, 정상 merge `9887a168a84e51d2777bf69174d892e568aa6ae7`로 소스 범위를 통합했다. SH3N·평면 SHELL의 닫힌 native 범위이며 전체 P7b는 미완료다.   최종 BCS/TYPE7 재연결 및 집합 검토의 무지지 절점 수용 보완은 [PR53](https://github.com/pikachu444/caelab-prep/pull/53)·코드 `5effcba52911411f1ee6f4dcf531b63160d79070`에 연결한다. BCS inactive_rotation-only 허용과 TYPE7 public not-applicable 표기는 유지하며 resolved 역할/secondary attachment를 따로 검사한다. 후속 [PR54](https://github.com/pikachu444/caelab-prep/pull/54)·코드 `90ddcc6`의 [명시 Drop](#mesh-target-drop-progress)은 절점·요소·SURF/PART의 제거를 sealed 검토/공용 UI에 연결하며 실제 메시 entity 삭제는 후속 [PR55](https://github.com/pikachu444/caelab-prep/pull/55)·API `6166269`·UI `6149401`의 [삭제 검증](#element-deletion-progress)으로 연결하며 전체 P7b는 남긴다. 추가 요소 PART 소유 이동은 [PR56](https://github.com/pikachu444/caelab-prep/pull/56)·API `d6f3f0f`·UI `80aaac4`/오류경계 `be45256`의 [검증](#part-ownership-progress)으로 연결하며 기존 part.assign과 구별한다. | [D23/D25 수정·입출력 확인](#track-3-corrections). 같은 beam_shell_tet/truss_shell_hex RAD+INCLUDE를 사용했다. 작성자 Qt 8표현×두 입력의 node16·cross-source element16, 차단/오래된 preview/기존 Apply3과 기존 group UI8을 통과했다. 독립 source API4(초기 API `823d4e8`)·GUI4(`22284aa`)는 원본 불변·취소/초안·적용/Undo·저장·새 프로세스 native 출력을 확인했다. lowercase family·잘못된 CLOAD 방향·solid main 접촉의 실제 결함을 고치고 원 지적자가 재확인했다. stale 복구 문구 수정은 영향1건과 원 지적자 읽기로 종결했다. 다음 BEAM merge guard는 작성자 새4+기존 후보17=21건과 독립4건을 통과했고 원 CAE 지적자가 재확인했다. 초기 endpoint mapping의 shell 품질 실패는 BEAM 행 분리 후 두 실제 default 전환 반례의 red로 구분했다. guard 입력/코드/원 실패·수정/독립 결과는 로컬 `C:\Users\pikac\.codex\visualizations\2026\11\03\prep-merge-orientation-618f4f3`에 보존한다. 명시 native merge는 실제 두 입력의6→8 방향점/9→4 TRUSS 연결, source 원본·선언 보존·Undo·v6/새 프로세스 출력을 확인했다. 최종 API17+관련node move1=18건, 앞선 직접 영향61건은 실행 범위를 구분한다. Qt22고유사례(8표현×두 입력16+여섯 경계)를 영향별로 확인했다. 독립 API4(`6764d4a`)+후속2(`e32b62d`), GUI4(`d8f1200`)+배치영향1(`b7c5446`)이 통과했다. 짧은 행의 실제 요소 유실, 외부source 접촉 의존성, foreign node의 DOF 누락을 red로 재현·수정하고 원 지적자가 재확인했다. native merge의 고정 입출력·DTO·원 실패/수정·독립 결과와 source 그림은 `C:\Users\pikac\.codex\visualizations\2026\11\03\prep-node-merge-e32b62d`의 acceptance/inventory/path-map에 보존한다. 고정 입력/출력/DTO/원 실패·수정 JUnit/그림은 로컬 보관처 `C:\Users\pikac\.codex\visualizations\2026\11\03\prep-group-review-22284aa`의 acceptance/inventory/path-map으로 재열 수 있다.  보강 입력은 같은 두 mixed RAD/INCLUDE의 native ID를101/8/909/4007/55/600001/3/8400/99로 바꾸고 NODE 행을 역순·연결 칸을 zero-pad한 것이다. 신규9(순수7/native2)를 포함한 직접 영향60 통과, 후속 출력 재파싱2는 같은 native2의 강화 확인이며 합산하지 않는다. 독립25d API6·test-only `82f8fa0a974e31750b4c3cefe329c322c3587db1`의 재파싱2가 통과했다. 원 거리/BEAM/원문 지적자는 수정과 red/green을 대조해 재확인했다. 실제 exported RAD를 별도 session으로 읽어 ID·연결/방향·BCS/CLOAD/INIVEL/TYPE7 keyword/순서/원문을 v6와 대조했다. `.out`이나 solver 실행은 확인하지 않았다. 입력·출력·원 실패·수정·hash/독립 결과는 `C:/Users/pikac/.codex/visualizations/2026/11/03/prep-pr38-core-25d4a9a/acceptance.json`과 inventory/path-map에 보존한다.   [셸 반전 검증 범위](#shell-normal-progress)는 같은 두 mixed SHELL 입력과 별도 copied SH3N을 구분하며, 원본·미변경 연결 칸·tail/행끝·좌표/ID/PART 보존과 명시 재연결을 확인했다. SDK·solver·VTK Render·OS 확인은 추가하지 않았다.   [attachment 보완 근거](#reconnection-attachment-progress)의 총43=신규8+Group16+Merge19, source/CAE 원 지적 종결과 실제 Qt 보류/교정 귀속을 구분한다. PR53 당시 요소 삭제/Drop은 미연결이었다. | [PR35 코드 head CI41530740968](https://github.com/pikachu444/caelab-prep/actions/runs/41530740968)의 10 jobs가 통과했다. [PR35 최종 문서 head CI41531508382](https://github.com/pikachu444/caelab-prep/actions/runs/41531508382)도 10 jobs 통과했으며 자동 반복 실행을 새 고유 검사로 더하지 않는다. 새 실제 X11 그룹 검토4건(두 표현×두 입력)과 같은 job의 기존 quad/hex4건·native97건을 구분한다. [900×680/640×480 상하단 그림](https://github.com/pikachu444/caelab-prep/actions/runs/41530740968/artifacts/13180814491)은 작성자·독립 검토자가 원문·스크롤·Apply/Cancel 접근성을 직접 확인했다. 시각 판정은 두 표현의 절점 그룹 장면에 한정한다. 로컬 그림은 source/offscreen(설치 글꼴을 QA process에만 등록)이다. [PR37 코드 head 7fa8c0f CI41541877284](https://github.com/pikachu444/caelab-prep/actions/runs/41541877284)는 10 jobs가 통과했다. 실제 Linux X11의 새 merge4건(두 표현×두 입력), 같은 step의 기존group/quad/hex8건, 별도기존native97건을 구분한다. physical VTK8points/3cells·source ID 제거·BEAM 방향 필드를 확인했고 [pairs/review 960×760/640×480 상하단 PNG32·본문4](https://github.com/pikachu444/caelab-prep/actions/runs/41541877284/artifacts/13185774255)를 작성자·독립 검토자가 직접 읽어 해당 장면의 시각적 차단 결함이 없음을 확인했다. 판정과 범위는 같은 acceptance.json에 기록한다. 기존 group/quad/hex 그림을 새 merge 화면 근거로 대신하지 않는다. 후속 coalescence `17c35d2`는 새 API13·Qt14 고유사례를 영향별 실행으로 확인했다. 기존 준비·그룹/merge 영향44·공유UI66·최종영향64·마지막표시수정4는 겹치는 실행이며 합산하지 않는다. 독립 API6·source/offscreen Qt3은 같은 제품 파일 hash에서 통과했다. 저장 old/current 선언 혼용과 조건 없는 그룹의 현재 선언 누락을 고치고 원 지적자가 각각 재확인했다. 입력·native 출력/v6·DTO·원 실패/수정·임시 INI·1020×760/680×500 그림8은 `C:\Users\pikac\.codex\visualizations\2026\11\03\prep-node-coalescence-17c35d2`의 acceptance/inventory/path-map에 보존한다. [PR38 초기 head bb33013 CI41548177115](https://github.com/pikachu444/caelab-prep/actions/runs/41548177115)는 10jobs를 통과했다. 실제 Linux X11 새 coalescence2건과 기존merge/group/quad/hex12건=14pass, 별도기존native97pass를 구분한다. [artifact13190575208](https://github.com/pikachu444/caelab-prep/actions/runs/41548177115/artifacts/13190575208)의 16PNG/본문2는 원 검토자가 직접 읽었다. 이 장면은 저장old/current 선언이 같고 remaining stale=None이며 다른 반례의 시각 근거로 확대하지 않는다. root가 compact 검토 checkbox 끝문자 잘림을 추가로 발견해 라벨을 짧게 하고 자연 너비 단언을 보강한 [교정 head9cf5241 CI41549559367](https://github.com/pikachu444/caelab-prep/actions/runs/41549559367)도 10jobs를 통과했다. 짧은 Mapping reviewed 라벨과 자연 최소너비 단언의 영향Qt2를 확인했으며 [교정 artifact13189564559](https://github.com/pikachu444/caelab-prep/actions/runs/41549559367/artifacts/13189564559)의 두 compact review 그림은 root가 직접 읽어 끝문자 잘림 해소를 확인했다. 이 자동 반복 실행은 새 고유 검사로 더하지 않는다. 최신 사용자 지시에 따라 PR38은 draft/미병합으로 인계하며 이후 통합 결정은 Gemini 총괄 배정에 따른다. 독립 API의 pytest 캐시 rename WinError5 경고는 검사·산출물 성공과 구분한다. native merge/coalescence의 새 Windows OS/VTK·frozen·solver 검증은 하지 않았다. 이전 이동의 Windows/솔버 한계는 [당시 기록](docs/native-windows-validation.md#node-move-20261102)을 유지한다. 접촉 secondary/main·평가 전 하중 계수·초기속도 중복은 물리 응답/유효 초기상태 판정이 아니다. PR38 당시 part 소유 변경·나머지 P7b 작업·CAD 재메시·N17 예산과 원제품 비교는 미완료였다. geometry 변경의 영향 집합은 기존 명시 재연결 전까지 export를 차단한다.  이번 코어 보강은 GUI/8원제품·Windows/새frozen·solver 수용/물리 동등성이나 전체 P7b의 완료가 아니다. PR38 최종 UI·통합은 Gemini 총괄 배정에 따른다. |
| N19 | 열린 GUI IPC / P8c-IPC | **PR #21 `f9a3d55` 구현·실제 검사·최종 CI 통과 후 `df277a8`에 병합.** live transport를 Qt 주 스레드의 소유 Session에 연결하고 doc/epoch/revision/request_id, token, CAS, draft/busy 충돌과 replay를 검사한다. | [D19 C10 탄성 계수 적용 확인](#track-3-corrections). 실제 X11 창에 별도 CLI로 연결해 수정·Undo·저장·재연결과 Gmsh 작업 취소를 검사했다. 독립 리뷰에서 GUI 후보 재생성 후 이전 job 상태가 남는 결함을 찾아 수정했으며, 원 검토자가 후속 Generate/Open/Adopt와 Stop 대기를 재확인했다. | 독립 집중 검사 57건을 통과한 소스의 [CI 41370219716](https://github.com/pikachu444/caelab-prep/actions/runs/41370219716) 8개 job을 확인했다. 실제 X11/SDK/MCP job은 teardown을 포함해 60 passed다. 문서 사본이나 새 CLI 세션을 live 제어로 대체하지 않는다. 이 IPC는 Android ChatGPT의 새 세션 생성 기능이 아니다. |
| N20 | 실제 MCP 클라이언트 연결 / P8c-MCP | **PR #21 `f9a3d55`의 실제 client 및 최종 CI 통과 후 병합.** N19에서 검증한 명령을 얇은 adapter로 노출한다. | 공개 MCP CLI @apify/mcpc 0.7.0을 설치했으나 이 환경의 Unix socket EPERM 때문에 handshake 전에 막혔다. 공개 FastMCP CLI 3.4.11로 수정·저장·실제 worker 취소·화면 반영과 오류 3개 과업을 확인했다. 서버 SDK 2.3.0은 별도 환경이며 LLM 키가 필요 없는 실제 stdio client 호출이다. | N19의 검증된 API를 사용한다. mock·Inspector·도구 등록만으로 닫지 않으며 클라이언트를 변조해 성공으로 만들지 않는다. 실제 CLI 상호운용과 자연어 LLM agent 검증을 구분한다. 종료 시 descriptor 부재 검사는 통과했으나 후속 실행에서 비활성 파일이 다시 관찰된 원인은 미확인이다. [관찰 기록](docs/automation/2026-11-02/cleanup-observations.json)은 원인 미확인으로 유지한다. 원격 CI에서는 종료·worker/descriptor 부재 단언을 통과했으며 공개 [산출물](https://github.com/pikachu444/caelab-prep/actions/runs/41370219716/artifacts/13108818638)의 capability 제거를 확인했다. Linux 구현 범위의 병합이며 원인 규명·Windows ACL·자연어 LLM 검증 완료로 확대하지 않는다. |
| N21 | Workbench RAD 실행 입력·계산 / W3 | **지원 경로 구현·병합.** WB PR #55 최종 `a328253`, main `865ee15`. RAD basename·상대 INCLUDE·Starter/Engine의 불변 snapshot과 두 단계 실행·실패·취소·재실행을 기존 JobManager가 소유한다. | 비작성자 검토와 수정 재확인, [CI 41368317991](https://github.com/pikachu444/caelab-workbench/actions/runs/41368317991)의 공식 solver 두 입력 서비스/X11 GUI·전체 Python 3.11/3.12·실제 CalculiX가 모두 통과했다. 로컬 shell ERROR760 기록은 해당 환경의 실패로 보존한다. | binary reader의 partial 상태를 유지하고 Prep에 두 번째 실행 관리자를 만들지 않는다. 이 지원 경로의 구현을 닫되 Windows 후속·전체 물리 정확성·완전한 native animation 판독을 완료로 확대하지 않는다. |
| N22 | 선/beam/truss·준비 shell면 / P7c-S | **명시 선/짧은 원호의 고정 F2 통과, 제품 미연결.** PR #23의 [영향 입력 재검증](docs/mesher-evidence/2026-11-02/structured/F2-OCC-addendum.md)에서 같은 입력·공차를 유지하고 OCC 원호 경로로 세 실패를 해결했다. 다섯 지원 입력·한 거부 입력의 최종 근거를 확보했다. CAD curve/frame과 준비 shell면, 단면·orientation/native 연결은 별도 남는다. | line/beam/truss와 준비 shell의 family·단면·orientation·node order·두께/offset 계약을 고정한다. F0–F2 실증 후 공통 채택·Undo·저장·실제 reader로 연결한다. line의 품질 근거로 SICN을 사용하지 않는다. | 자동 중립면을 기다리지 않는다. 공식 Gmsh/OCP와 고정 solver를 사용한다. 미지원 formulation은 거부하고, 외부에서 준비한 선·면을 쓰는 대안도 같은 native 품질 검사를 거친다. |
| N23 | 제한된 일정 두께 중립면 / P7c-M | **제한 OCCT 실험·독립 재실행 확인, 제품 연결 미완료.** 자체 생성 평판과 일정 두께 둥근 L형에서 명시 pair/offset→boolean→sewing, 원본 불변·저장 재읽기를 확인했다. 공식 예제·접합부·고정 F2 형상군은 아직 남아 있으며 임의 형상의 자동 중립면 생성을 약속하지 않는다. | plate·절곡·단순 접합의 고정 형상에서 기존 backend의 명시 pair/offset과 수동 보정으로 위치·두께·접합 공차를 실증한다. 실패 형상과 공차도 기록한 뒤 F2/F3로 진행한다. | 기존 backend의 실제 실행과 형상군 검증이 필요하다. 사용자가 준비한 중립면과 두께 입력(N22)을 대안으로 제공하되 자동 중립면 완료로 세지 않는다. 공개 macro가 있다는 사실은 통과 근거가 아니다. |
| N24 | mapped/recombined quad / P7c-H-Q | **제한된 planar quad4의 F3 API/GUI 연결, 전체 후속은 유지.** [PR62](https://github.com/pikachu444/caelab-prep/pull/62)·코드 `8708b2de897e8f4a282698385b850efdc8ba2f03`의 [채택 recipe 보관·재생성 확인](#recipe-archive-progress)은 작은 선택 v6 자원과 기존 생성기를 사용한다. [PR27](https://github.com/pikachu444/caelab-prep/pull/27) 제품 코드 `b0b06682f12c43e3d09fda9249f9f5d1bd3f1765`·검토 head `674ffbc9f8af84b9762b16eba4eb5b893a5a89e8`·병합 main `35c97fa794d4c5c17cf7e5d1cd5043f012433152`는 별도 source/실제 직렬화 좌표 검사, 같은 dialog의 recipe 생성·취소·품질·SHELL/GRSHEL 채택, 한 Undo·v6 저장에 연결한다. 원본 JSON을 자산으로 보존해 commit 관찰자의 즉시 저장과 실패 rollback까지 덮어쓰기 보호를 유지한다. 해당 PR 당시 CAD/독립 MSH family를 유지하고 hex를 거부했다. 이후 명시 sweep hex 연결은 N25에서 구분한다. 후속 [PR58](https://github.com/pikachu444/caelab-prep/pull/58)(정상 병합 `5898dbd`) `a230d322f71cc2da8104239c7441fa4745c54f27`의 GUI quad divisions 편집은 [후속 확인](#quad-divisions-progress)에 연결한다. | 기존 [F2 실증](docs/mesher-evidence/2026-11-02/structured/F2-report.md) 입력 Q-N3(cm, 45요소/60절점)·Q-D2(mm, 68요소/90절점, 공유절점5)를 재사용했다. 8표현의 공통 Action→dialog→채택/Undo→저장·새 CLI export 16건과 원본/구조 오류·실제 worker 취소를 작성자/독립 QA가 확인했다. source Qt 그림은 QA process의 설치 글꼴 등록 후 960×640/760×480 가독성을 재확인한 것이며 OS 화면이 아니다. 실제 Windows OpenRadioss Starter는 기록된 EXE+기존 Intel runtime의 child PATH에서 두 입력 모두 rc0/정상 종료·오류0/경고0, 개수·PART 질량·Ishell24를 확인했다. 최초 loader 실패와 미실행을 별도로 보존했다. | Windows 실제 OS/VTK·원제품 비교, [PR63](https://github.com/pikachu444/caelab-prep/pull/63)·`498375d`의 단일 patch corner 좌표 fork는 [후속 확인](#recipe-geometry-fork-progress)에 연결하고 두 patch의 공유 vertex·patch 구성 편집은 후속이며 recipe 동봉 재생성의 제한된 후속 확인은 별도 anchor에 연결한다. quad divisions 편집의 제한된 확인은 별도이며 N24 전체 완료가 아니다. 정확한 head의 [CI 41499732419](https://github.com/pikachu444/caelab-prep/actions/runs/41499732419) 10 jobs와 실제 X11 quad preview/pick 2건·기존 native 97건이 통과했다. 앞선 green 그림의 Q-D2 edge-on 결함을 찾아 면 법선 camera로 수정하고 원 지적자·독립 검토자가 [새 그림](https://github.com/pikachu444/caelab-prep/actions/runs/41499421273/artifacts/13167847692)을 직접 확인했다. 새 frozen b0 번들은 수정 UI 입력·고지를 검토했으며 worker/parser 불변 경로만 이전 fc0499f의 실제 frozen90절점/68quad 검증을 재사용한다. 새 frozen GUI/camera는 미실행이다. Engine·재료 물성/해석 응답·단위변환 보증은 이번 Starter 확인에 포함되지 않는다. 제한된 source의 성공을 임의 곡면·holes·patch assembly·tri fallback의 성공으로 확대하지 않는다. |
| N25 | sweep hex / P7c-H-S | **제한 sweep hex8의 F3 공통 API/GUI 연결, 전체 후속은 유지.** [PR62](https://github.com/pikachu444/caelab-prep/pull/62)·코드 `8708b2de897e8f4a282698385b850efdc8ba2f03`의 [recipe 보관·재생성 확인](#recipe-archive-progress)을 같은 경로로 사용하며 전체 H-S/F4는 닫지 않는다. [PR34](https://github.com/pikachu444/caelab-prep/pull/34) 최종 검토 `375fdee6b3a9346408675fde9d9c3317d9f70c91`·실제 Git 통합 `fc98c25fa725859e64ff03adf4b4b9cebcbfb19c`, API `ebd18e398118cf63bfee4e0bc90c5d16c4dbbd5a`·GUI/검사 연결 `7fa0c35a2a6fec1a388f68e72c6061b0e6b27e2d`는 기존 F2 source/27점 기하·실제 직렬화 좌표 검사를 재사용해 BRICK/GRBRIC·명시 Isolid=1·한 Undo/v6 저장에 연결한다. CAD/독립 MSH hex는 허용하지 않는다. 후속 [PR59](https://github.com/pikachu444/caelab-prep/pull/59)(정상 병합 `a03f41f`) `02f936c36458536baea418c9d627481987004c6f`의 직접 divisions/layers 편집은 [별도 확인](#hex-divisions-progress)에 연결한다.  [WBS-C1-C2](#wbs-c1-c2)의 Hex8 단면 생성·공용 선택·실제 recipe 채택/출력 연결은 코드0ea4ca4에서 보완했으며 전체 N25는 미완료다. | 같은 H-N3(cm225hex/360node, V112.5)·H-D2(mm525hex/768node, V245, 공유면35/절점48)의 원래 8절점 순서·집합·공유 연결과 새 CLI 출력을 작성자·독립 API QA가 확인했다. GUI 8표현×두 입력16건과 생성/닫기2건, quad 영향8건이 로컬 통과했다. 새 두 입력의 실제 Windows Starter는 기존 EXE+Intel child PATH에서 각1회 rc0/오류0·경고0, SOLID-HEXA와 Isolid1/Ismstr4/Iframe1·개수·PART 질량을 확인했다. 초기 검사기의 node_support 반환형/Undo revision 가정 오류는 실제 계약에 맞게 정정했다. | 독립 GUI QA는 생성/닫기2건·실제 hypermesh 표현의 채택/저장2건이 통과했다. [최종 head 375fdee CI](https://github.com/pikachu444/caelab-prep/actions/runs/41503612679)의 10 jobs가 통과했다. 앞선 코드 동일 head 3fb62cd 실행에서도 실제 X11 quad/hex preview·pick 4건과 기존 native 97건을 확인했다. merge 호출은 ReadTimeout이었으나 Git main의 두 부모·동일 tree·head 포함으로 실제 통합을 확인했다. 재호출 없이 PR을 닫았고 GitHub metadata의 merged=false는 별도로 유지된다. [hex 전체 dialog/preview 그림](https://github.com/pikachu444/caelab-prep/actions/runs/41502782390/artifacts/13169341907)을 원 지적자·독립 검토자가 직접 읽었다. H-N3 초기 시점은 깊이 상세에 회전이 필요하지만 표시/검토를 막는 결함은 없었다. Windows 실제 OS/VTK·frozen hex·원제품 비교·Engine/물성/해석 응답은 미확인이다. [PR63](https://github.com/pikachu444/caelab-prep/pull/63)·`498375d`의 단일 patch corner/sweep vector fork는 [후속 확인](#recipe-geometry-fork-progress)에 연결하며 두 patch/일반 형상 편집은 남긴다. recipe 동봉 재생성의 제한된 후속 확인은 별도 anchor에 연결한다. divisions/layers의 제한된 코드·파일 확인은 시각/전체 H-S 합격과 구분한다. 이전 F2·mixed native 성공을 새 출력 성공으로 대신하지 않는다. 비틀림·곡면·원통/annulus·일반 CAD 분할의 전체 H-S/F4는 후속이며 제한 source 성공을 전체 완료로 세지 않는다. |
| N26 | hex/tet/prism/pyramid 전이 / P7c-H-T | **부분 SDK 생성·공식 native 한계 확인, 전체 미완료.** hex/tet/pyramid 혼합 생성은 소형 실험에 한정한다. 공식 반복 절점 BRICK 표현은 총질량을 보존해도 lumped mass 중심을 바꿔 무손실 Pyramid5/Prism6 대응이 아니다. pyramid fixture는 정상 종료, prism은 Starter restart 쓰기 중 중단해 원인 미확정이다. `/PENTA6` thick-shell을 일반 solid 대안으로 쓰지 않는다. | hex/tet/prism/pyramid의 전체 inventory, face 연결, hanging node, 품질과 native 재읽기를 held-out 형상을 포함해 F0–F4로 확인한다. 지원 family별 writer와 실제 solver 근거를 확보한다. | 미지원 전이 요소가 있으면 전체를 거부하고, 요소를 버리거나 임의로 퇴화 치환하지 않는다. 외부 conformal 메셔 후보는 사용권·배포 조건과 실제 입력을 확인한 뒤 대안으로 검증한다. no-go는 조사 종료일 뿐 기능은 미완료로 유지한다. |

<a id="product-comparison"></a>

**N03–N10의 공통 비교 기준:** DESIGN의 같은 T1–T6 작업·대응 물리 객체와 입력/목표 상태를 고정하고 각 원제품의 실제 버전에서 조작한다. 같은 유효 작업영역의 전체 화면·모달·오류/취소와 클릭/키 입력 수, 가독성·대상/값·참조·파일 결과를 Prep와 대조한다. 차이는 이유와 사용자 영향을 기록하고 결함은 작성자 외 검토자가 재확인한다. 원제품 접근·미지원 기능의 대응을 확보하지 못하면 정확한 칸을 보류하며 스크린샷 관찰/내부 회귀만으로 비교 통과를 선언하지 않는다. Windows 측정은 N12에 한 번 기록하고 제품별 비교가 참조한다.

**당시 원제품 접근 조사(2026-11-02):** [제품별 공식 URL·배포판·실행 조건과 실제 화면](docs/ui-reference-variants.md#product-access)을 확인했다. 공개 무료 배포, 신청 후 무료 발급, 사용권 연결, Windows/Linux 호환성과 다운로드 수신 실패를 따로 기록했으며 이를 일괄 유료 장벽으로 부르지 않는다. 이번에는 원제품 T1–T6를 새로 실행하지 못했고 N03–N10을 닫지 않았다. trial 신청·메일 송신·계정 생성·구매를 하지 않았으며, 사용자 지시의 Windows 후속 확인을 유지한다. 해당 cloud/Linux 작업공간의 PATH·Wine 부재를 현재 Windows PC의 blocker로 쓰지 않는다. 현재 native Windows PC의 원제품 설치본·사용권·T1–T6 직접 실행 여부는 미확인이다. 이 문서 정리에서 새 설치·실행 조사를 하지 않았다.

<a id="current-progress"></a>

Phase 3.6 폐삼각표면 Auto-Tet의 독립 진단 코드는 `01e0be2`에 보존했다. [고정 F1 결과](docs/mesher-feasibility-roadmap.md#2026-11-03-폐삼각표면-auto-tet-f1)는 L형 Tet4/Tet10 통과와 공식 구 J 미달을 구분한다. 두 recipe의 F1은 품질 미달이며 F2·자동생성의 공통 채택은 미완료다. 이후 별도 [prepared Tet10 선행 경로](docs/usage.md#prepared-tet10)의 API `da754bf`는 기존 NativeMesh/v6에 opt-in admission·한 Undo·두 행 RAD 출력을 연결했다. 고정 L의 새 프로세스 재열기·실제 Starter 입력 확인은 Engine 부재 경고1과 응답 미확인을 구분한다. 공용 Qt `3c47c31`의 가져오기·단면 선택과 source preview의 정확한 순서 연결은 같은 API를 사용한다. 8표현의 조작·Undo·재열기, 원본 보호·Line3 역할·문서 재열기 epoch의 원지적 종결과 실제 OS/VTK 후속을 구분한다. N02의 기존 tri3/tet4 import와 N18의 기존 메시 수정 지원 또는 그룹별 잔여 수를 이 진단으로 닫지 않는다.

추가 [Targeted Interior Corner-J F0 기록](docs/mesher-feasibility-roadmap.md#targeted-corner-j-f0)은 PR43의 고정 구 실험에서 Jmin .284588→.314196, 미달 272→271로 개선했지만 목표 미달·예산 소진임을 보존한다. 측정은 수정 전 소스에 귀속되며 수정 후 구 재실행은 없다. 문서 보존은 prototype 코드 병합이나 F1/F2/F3 통과가 아니며 N01–N26 상태와 그룹별 잔여 개수를 변경하지 않는다.

## 현재 개발검증자료와 진행 중 변경

<a id="wbs-c1-c2"></a>

2026-11-09 **WBS-C1-C2 Part3 QA 후속**(검토 기준 `4dfcf39a30abbc736d1714e6d6ab60654bdb5133`): 사용자 QA가 수용한 Hex8·도킹·PR 통합은 유지하고, merge/move·공유 요소 편집·소스 import·준비 메시/CAD 교체·최종 재연결의 유효한 Preview가 완료되면 해당 검토 체크를 자동으로 켠다. 비동기 결과는 문서/revision/입력 generation 검사를 통과한 뒤에만 체크한다. 입력 편집·무효화·실패/지연 결과는 체크 해제를 유지하고, 직접 체크를 끄면 버튼 비활성화와 기존 review_required 적용 차단이 동작한다. PART/source/contact 경계 허용과 반복 대상 병합의 별도 명시 허용은 자동 추정하지 않는다.

기존 영향 검사14파일은250pass/60skip(OCP 미설치)이며, 추가한 CAD 비동기 callback4건(성공·입력변경·문서변경·실패)과 형상 hint1건은5pass다. 고유255pass/60skip이며 별도 실행을 단일 full-run으로 쓰지 않는다. mesh recipe hint의 두 기존 quad/hex 사례에 짧은 문구와 원 corner-order 툴팁을 확인하는 assertion을 추가해 해당2pass로 재검사했으며 중복 합산하지 않았다. 실제 source import/준비 메시·재연결과 native 편집의 Preview→Apply·수동 해제 거절·Undo·편집 무효화는 기존 RAD 입력/8표현 경로로 확인했다. CAD callback 네 건은 모의 UI 결과이며 실제 CAD 교체 실행이나 SDK/solver 검증으로 세지 않는다.

형상 하단 안내는 단위·표시용 선·원본 불변의 한 줄로 줄이고 원뿔 공식·형상 범위를 툴팁으로 옮겼다. 같은 저장 conical-P metadata와 Segoe UI를 사용한 source/offscreen 1040×700·760×520 전후 그림에서 안내 높이는32→16px·48→16px다. root가 원해상도 그림을 읽었으며 OS 입력/실제 VTK 창·solver는 실행하지 않았다. 보관처 `C:/Users/pikac/.codex/visualizations/2026/11/09/wbs-c1-c2/preview-followup`와 부모의 `preview-followup-{ui,new,hint}.xml`에 하네스·그림·검사 결과를 유지하고, 후속 report에 최종 코드SHA/환경/범위를 연결한다. 독립 검토자는 소스·XML·전후 원해상도 그림4장을 읽고 mesh hint의 추가 검사2건을 재확인해 이번 Part3 후속을 승인했다. 이번 변경으로 기존 N 행과 그룹별7/16/3을 닫지 않는다.

2026-11-09 **WBS-C1-C2 구현 코드 `0ea4ca4470a98a32a6b412bc33b0974ce4187c82`**, 기준 `940a9cba`·브랜치 `feat/prep-core-ui`: PR47 두 커밋과 PR50의 지정 네 커밋만 이식했다. PR48의 두 커밋·Washer 모듈/버튼은 제외했다. 원통/유한 원뿔 후보 판독과 공용 창은 읽기 전용 범위를 유지한다. 새 `create_solid_section(..., element_family="hexa8")`와 공용 선택은 기존 PROP/SOLID `Isolid=1, Ismstr=4`·BRICK 채택 경로를 사용한다. H-N3/H-D2 recipe의 실제 SDK 생성→새 Hex8 단면→채택→RAD 출력에서 모든 ordered connectivity를 확인했다. 새 formulation·일반 CAD all-hex·N25 전체 완료는 아니다.

BeidPrep 기본 레이아웃 v4는 표시 후 리사이즈와 첫 수동 dock drag를 구분한다. 동일 two_shell_plates 입력/Steel 선택의 1440×900 offscreen Qt에서 MODEL/FORM/중앙은 이전245/250/937px→187/240/1009px(70.07%)이고, 960×640에서는175/240/541px다. v3 dock state 초기화·v4 수동 배치 복원도 확인했다. 검사/후보/MSH 가져오기는 실행 전 고유 임시 경로를 채우고, 명시적 빈 경로 거절과 기존 출력 widget을 유지한다. 일곱 편집창의 첫 안내와 ID 입력 placeholder만 줄였으며 상세 영향 검토·16MiB 검증은 보존했다.

Windows Python3.13.5/PySide6 6.9.1/Gmsh4.15.2의 지정 검사 최초155건은151pass/4fail(이식한 Washer assertion)이었고, 네 assertion을 제외 조건으로 수정해 해당4pass로 재확인했다. 추가 dock-version1pass를 합친 **고유156건이 통과**했으며 단일 전체 green 재실행으로 주장하지 않는다. dock-version의 첫 실패는 offscreen 화면 경계로 restoreGeometry가850px로 축소한 상태에1440px의70% 조건을 적용한 검사 오류였고, 명시1440px 리사이즈 후1pass다. 추가 통합 검사496pass/63skip은 OCP 의존 실제 CAD fixture의 미설치를 성공으로 세지 않는다. 독립 검토자는 소스·원해상도1440/960 그림·실행 자료를 읽어 코드 결함이 없음을 확인했고, 이식한 Washer assertion4건 수정 재확인을 종결했다.

체적 비교는 새 `scripts/evaluation/geometry_volume.py`에서 mm³ 절대차 `<=1e-9`를 사용한다. 현재 코드로 보관 원통P/N과 원뿔P/N XAO를 각각1회 실제 SDK 검사해 후보수와 원본hash 불변·체적을 모두 통과했다. 원통N의 −3.552713678800501e−15mm³와 원뿔P의 +5.684341886080802e−14mm³는 허용 범위다. 과거 `gi3-actual-01` frozen false는 수정하지 않았다. 명세의 원통6시편 A1/A2/B/C/N/O를 이 입력들에 대응시킬 근거는 아직 없어 해당 전체 gate는 **입력 식별 보류**다. 임의로 P를 O 등에 대응시키지 않는다. 새 OS입력/VTK·Starter/Engine·원제품 비교·원격CI는 미실행이며 N12/N13/N25와 그룹별7/16/3은 닫지 않는다.

재열 수 있는 보관처는 `C:/Users/pikac/.codex/visualizations/2026/11/09/wbs-c1-c2/report.json`이다. XML·로그·입력/출력 metadata·체적 재검사 하네스와 보고서·같은 입력의 전후 PNG1440/960·레이아웃 JSON·base source ZIP을 연결한다. 보고서에 코드SHA·환경·산출물hash·전체 변경 파일을 보존했다. Git에는 외부 CAD·바이너리·임시 결과를 넣지 않았다.

### 보존한 원 PR 기록 (2026-11-04 및 그 이전 범위)

아래 GI3/GI4의 PR48 stack·Washer 상태·옛 CI/수용 문구는 **원 PR 당시의 기록**이다. 현재 통합의 Washer 포함이나 새 실행 결과를 뜻하지 않으며, 현재 WBS 범위와 실제 결과는 바로 위 항목을 따른다.

2026-11-04 GI4는 topology helper `d67572a`, core `659fc0d1917f4d5e386f308b5d29f20beba1a794`, 공용 UI `fe2a8eaee5ce22219bb06b2040dea472fc6cb0ce`로 [PR50](https://github.com/pikachu444/caelab-prep/pull/50)에 게시했다(PR48 위 draft, main728의 PR49 변경 포함). mm 축 정렬 유한 quarter-cone·두 사다리꼴 Plane 지지면의 raw material 관측과 signed G1 후보만 지원하며, 판정 반경은 trim의 최대 유한 주곡률 반경이다. 기존 offset·reader·후보 표를 재사용하고 기본 Plane/Cylinder 지원 범위는 넓히지 않았다. 신규 backend81·기존 공유 core 영향142·앱/reader117·Qt29는 겹치는 실행으로 구분하며, 독립 코드·CAE 검토에서 남은 차단 지적은 없었다. 새 전체 CI/solver 반복을 피하도록 `[skip ci]`로 게시했고 현재 head의 새 Linux render 통과를 주장하지 않는다.

GI4 실제 `surface-autotet/phase37-cone-f0/material-observation-01/report.json`(SHA256 `9dda1946a1e4a9c9e74f8c71487eadd4e9fdb282ffe7c01a051890820846f21b`)은 fe2와 입력·하네스 해시를 고정한 첫 실행에서 두 기존 XAO를 각각1회 검사했다. 각 initialize/finalize1회·재료 query6회, trim N5/P7회이며 P 후보1/dot+1,+1·N 후보0/dot−1,−1과 P의 7.5 포함/7.49 제외를 관측했다. 최대 Rκ는 양쪽 `7.499999999996179 mm`이다. 저장 STEP-import 대비 volume 차이 N−3.55e−15/P+5.68e−14 mm³는 **이 실행 전 선언한 1e−9** 안이며 이전 GI3의 exact-volume frozen false를 바꾸지 않는다. 원 F0·출력·소스 해시가 유지됐고, 독립 검토자가 raw XYZ/count/sign·잔차·classifier·승인 시점과 trace를 대조했다. 두 launcher rc0/wait와 실제 Python PID/PPID/finally는 대응하지만 별도 child OS reap은 미기록이다. 새 CAD 생성·STEP import·독립 SDK reader·mesh·solver·GUI/OS는 이 material packet에서0이다.

GI4 공용 창의 synthetic QA는 첫2확인 후 QA exact-float 가정 실패를 보존하고 같은 소스·자료의 남은25확인을 완료했다. root와 QA가 1040×700/760×520 PNG를 직접 읽었고, data-only VTK는 NeverRendered=1을 유지했다. 별도 실제 저장 자료 UI 연결은 첫 P 표·identity 확인 뒤 잘못된 1e−12 이론 반경 비교 실패를 보존하고, raw 값은 고정 actual classifier와 정확 비교해 남은13확인을 완료했다. 총 Qt2프로세스·3 pureloads(P2/N1)이며 앞선 P 확인을 중복 합산하지 않는다. P의 단면3/6·두16선분 부분 호/35 owned lines, N의 후보0·표식 없음, Washer 비활성·활성 문서/원자료 불변은 `ui-qa-01/report.json`과 `actual-saved-ui.json`에 귀속한다. 이들은 `C:/Users/pikac/.codex/visualizations/2026/11/03/surface-autotet/phase37-cone-f0`에서 재열 수 있다. 실제 Windows/VTK Render·일반 원뿔/토러스/fillet·억제·Washer 요소 생성·batch/cleanup은 미확인·미구현으로 남기며 N12/N13/N18과 그룹별7/16/3은 닫지 않는다.

Phase 3.7 GI3 코드 `58bca2c500b6b0e1f75c28bcf136a62bc848a708`는 mm 축 정렬 quarter-cylinder와 두 직사각 지지면에 한정해 재료 방향의 signed G1·포함 반경 threshold를 검사한다. 공유 offset/reader와 사각 wire를 재사용했고, 유한 원통 패치 밖 sample 허용 결함은 원 반례2 red→영향33 green 후 원 지적자가 종결했다. 최종 직접 영향 순수263통과(actual3 제외), 공용 Qt19건과 마지막 저장 unknown 단위 반례의 영향1건은 겹치는 실행으로 구분한다. 독립 synthetic offscreen QA16확인·6PNG와 root의 1040/760 그림 읽기는 `surface-autotet/phase37-fillet-f0/gi3-ui-qa-01`에 보관한다. UI는 같은 후보 표/Action/viewport를 사용하며 원통 blend의 끝은 16분할 부분 호이고, Washer 요소가 아니다. 새 실제 Linux render/pick은 CI 연결만 준비했으며 아직 미확인이다.

GI3 실제 `gi3-actual-01/report.json`은 기존 고정 P/N XAO 각각1회·재료 query 각각6회에서 P 후보1/dot+1,+1과 N 후보0/dot−1,−1을 관측했다. 반경1 포함/.999 제외는 같은 저장 자료의 순수 재판독이다. 원본·capture·core 소스 hash와 embedded BREP text/format은 불변이다. **전체 frozen report는 passed=false**다. N 체적 관측은 이전 STEP-import `.6438055098076205`에서 XAO-import `.643805509807617 mm³`로 −3.552713678800501e−15(−32ULP) 달랐다. 원 보고서를 보존하고 `xao-volume-attribution.json`에 비교 경로·파생값 차이와 XML geometry.name 외 동일함을 기록했으며 root/원 비판자/CAE 검토자가 직접 대조했다. 내부 원인·동일 XAO 반복의 비결정성은 확인하지 않았다. 새 CAD 생성·mesh·solver·OS0이며 추가 SDK 실행이나 기준 완화는 하지 않았다. 두 Popen launcher의 rc0/회수와 실제 query PID trace는 구분하며 historical parent 관계·독립 child reap은 미기록이다.

같은 UI hash에서 실제 저장 P/N metadata를 각1회 순수 load한 독립 검토도 P1/R1/길이3·두 부분 호/35 display lines와 N0/비접선 사유·활성 문서 불변을 확인했다(`gi3-ui-qa-01/actual-saved-ui.json`). 새 SDK/VTK/OS/그림은 0이며 원 전체 false를 변경하지 않는다. 이 단위는 원본 CAD를 바꾸지 않는 제한된 기하 후보 판독이다. 원추/토러스·일반 fillet·메싱 접선 edge 억제·Washer Quad/Tria ring 제어/생성·batch/cleanup, N12 Windows OS/VTK와 그룹별 잔여7/16/3은 미완료로 유지한다.

<a id="n13-mcp-packaging-progress"></a>

2026-11-04 현재 앱 source `0ada7ce1143e04931e1554430270247f3d994df9`·동일 tooling의 비공개 build1은 application90개와 actual EXE PYZ의 신규3모듈 수집·frozen CLI help1을 확인했다. 원 verifier는 Git blob LF와 archive CRLF를 같은 것으로 오해해 CLI 실행 전에 실패했으며 `verification/report` SHA256 `d4d6f644d9faaa786e9c10740d304a4c0c273f3d122964e83e44fad5b0711074`와 원하네스를 보존했다. fixed SHA의 fresh git archive 바이트를 직접 비교한 `verification-archive-02/report` `7e6492e86fccea133589f908381b03d0556ccc07f02274594b21cf592c313ee1`의9확인·독립 source90/PySide6하위DLL·PYD28 실제 해시 확인과 Qt plugin 두 개 제외는 제한된 수집/CLI 근거다. newline 정규화를 합격 조건으로 쓰지 않았다. 이 번들의 MCP 실제첫시도는 GUI/privateINI/descriptor 시작을 통과했으나 initialize1이 Connection closed로 끝났고 server stderr에는 generic Install-MCP 오류만 남았다. 원 report `9ba75e4891c9c491d8ddb6d9d835877b8aa41c6f92e9a59c7c5ccdc6f297ab49`와 stderr는 유지했다.

실제 PYZ/Analysis/warn과 설치 SDK 원문 대조에서 MCP server/types는 있으나 selected venv의 `pywin32.pth` 검색 경로가 Analysis에 반영되지 않아 `pywintypes`/`win32api`/`win32job`/`win32con`·DLL이 빠졌음을 확인했다. Runtime 예외 cause는 가려져 있어 최초 예외 문자열까지 회수했다고 주장하지 않는다. [PR57](https://github.com/pikachu444/caelab-prep/pull/57)의 packaging 코드 `2168300ce8985ed28a55561a1aeefcec3e4c4192`는 존재하는 선택 site의 `win32`/`win32/lib`만 `pathex`에 추가하고 resolve가 site 밖이면 거부한다. 기존 source/global-input guard·표준 PyInstaller DLL/runtime hook을 유지하며 새 설치·전역 경로 확대·새 worker/framework는 없다. 영향6pass, 미변경 entry-worker 검사1deselected와 독립 소스 검토를 구분한다.

고정 source0ada/tooling2168300의 새 private build1은1,432payload files/500,048,626B(manifest 자체 제외)이며 EXE SHA256 `24348b9def6c4e7d20c018b627eaf4ed79c3ccfa4a6b94c2829e8e7566f408bc`다. 앱 입력90개의 이름/해시는 이전 source0ada 후보와 정확히 같고 실제 archive 파일과 일치한다. 새 Win32 모듈·DLL·기존 runtime hook을 수집했다. 실제 payload 비교는 PYD5/DLL1 추가·제거0이며 EXE·analysis-inputs.json·base_library.zip·setuptools 고지 하위 __pycache__ 파일의 기존4경로도 바뀌었다. 마지막 cache 차이의 원인은 조사하지 않았으며 번들 전체가 동일하다고 주장하지 않는다. 독립 검토자는 추가6파일의 입력/manifest/실제 해시와 PYZ 모듈명·runtime-hook 항목을 읽었다. 새 metadata 검사의 첫 controller 준비는 이전 후보 report 경로를 찾다가 프로세스 생성 전0실행으로 중단됐고 별도 preflight 기록을 보존했다. 후보별 보호 목록을 교정한 실제 첫 GUI1/MCP1은 initialize1·tools/list1·`prep_describe`1의5확인으로 같은 owned server ID/empty문서0nodes0cells를 확인했다. 서버 version1.0과 협상 MCP protocol2025-11-25는 별개다. 모델 열기/복제/편집/저장·worker·mesher SDK실험·solver·OS입력/capture·VTK Render는0이며 앞선 worker/save/reopen/WM_CLOSE 근거를 반복하지 않았다.

보관처는 `C:/Users/pikac/.codex/visualizations/2026/11/04/prep-portable-0ada7ce`와 `prep-portable-mcp-2168300`이다. 두 후보/기존 ZIP을 보존했고 build는총2회(원실패후원인수정 후보별각1), 실제 GUI/MCP도각2회(before 실패/after 교정)다. `same-source-comparison.json` SHA256 `f5cde4bf077f8a85fc825d445003fc665d9de4ab0f379e7dfbdf03c6bad6b252`, `mcp-stdio-protocol-01/report.json` `9ea89c92211a073f0112fbeff50714957af0436a46e8f679ae116a672056c471`·실사용controller snapshot/INI·redacted logs로 재열 수 있다. root가 실행했고 독립 검토자는 입력/산출물·기록을 읽은 것이며 독립 runtime 재실행으로 합산하지 않는다. MCP SDK context 종료는 개별PID/rc/reap 증거가 아니다. GUI는 자기 Popen tree만 강제 종료(taskkill0/parentwait1)했으며 정상 닫기/INI복원이 아니고 child별 독립 reap도 미확인이다. ownINI/보호4파일 해시는 같고 private descriptor/credential은 삭제했다. 유효 INI의 정상 frozen 저장·재열기, 실제 Windows/IME/VTK·깨끗한 PC·published-client 전체 상호운용/편집·작업, 전체 Qt/전이 재배포 조건·자체 설치 `caelab_prep` notice 미수집은 남으며 N13/그룹별7/16/3을 닫지 않는다. 자체 notice는 editable RECORD와 저장소에 원문/라이선스 선언이 없는 상태로, 수집기가 놓친 기존 고지나 코드만으로 정할 조건으로 처리하지 않는다.

<a id="n13-portable-archive-progress"></a>

2026-11-04 N13/P9-A의 인도용 archive 코드는 `465b88852bd9ea82c1015d0bbe6fe612986fa269`다. `scripts/packaging/archive_portable.py --candidate <기존 dist/CAELab-Prep> --output <새 인도 폴더>`는 기존 builder의 built/exit0·source/packaging full SHA와 전체 파일 inventory·크기·SHA256을 확인한 뒤 ZIP과 SHA256 sidecar를 만든다. EXE/DLL·리소스·고지를 보존하고 내부 `analysis-inputs.json`은 제외하며, ZIP 안의 build manifest는 로컬 환경 경로/command 대신 source/packaging SHA·원 기록 hash·payload 목록·고지 미확보/조건 미해결 개수와 배포 미승인 상태만 담은 별도 요약이다. 원 후보와 private 기록은 덮어쓰지 않는다. 누락·추가·변조·unsafe/중복 경로·symlink·기존 출력은 거부하고, ZIP을 다시 열어 CRC·전체 payload hash와 요약 bytes를 대조한다. 사용법은 [packaging 안내](scripts/packaging/README.md#archive-a-built-candidate), 실행·통합 협의는 [기존 공개 실행표](https://github.com/pikachu444/caelab-prep/issues/64#issuecomment-6624408883)에 연결한다.

관련 파일의 수정 전 검사는28pass/0.90s이고, 원 critic의 N13-ARCH-R1(최종 이동 실패 때 checksum 잔여)을 수정한 뒤 영향3검사는3pass/26deselected/0.51s다. 합성 EXE/DLL/resource/license fixture를 실제 ZIP으로 묶은 코드/CLI 검사이며 frozen 앱 실행이 아니다. 실패 이동 주입 뒤 출력 폴더가 비고 후보 bytes가 유지되는 회귀와 원 critic의 소스/검사/사용법 재확인으로 R1을 종결했다. 새 build·OS/VTK·solver·전체 suite는 실행하지 않았으며 이 커밋은 `[skip ci]`다. 이 archive 단계의 종료는 최신 source의 Windows 납품·정상 INI 복원·새 PC·전체 재배포 조건 승인이나 N13/N14 전체 완료를 뜻하지 않는다. 기존 후보·실패와 그룹별7/16/3은 유지한다.

같은 archive 코드로 보존된 실제 source `0ada7ce1143e04931e1554430270247f3d994df9`/packaging `2168300ce8985ed28a55561a1aeefcec3e4c4192` 후보를1회 묶었다. 입력1,432파일/500,048,626B를 검증했고 ZIP은1,432members(원 payload1,431+filtered manifest1), 174,399,742B·SHA256 `cd6f77402e585b6a8ed6838e3a5b357a5b9aa9cc6aa8cccfd9071bdd854fb067`다. archive 명령exit0의 ZIP CRC/전체 payload hash와 별도 sidecar SHA·public field allowlist를 확인했으며 원 private manifest/analysis bytes는 불변이다. 고지 미확보1·조건 미해결2와 배포 미승인 상태를 유지한다. [PR66](https://github.com/pikachu444/caelab-prep/pull/66)은 이 코드·검사·실제 후보 호환성 근거를 연결하며, 새 source 빌드나 실제 앱/Windows 확인을 수행한 것으로 세지 않는다.

2026-11-04 N13-DLL-R1은 [PR67](https://github.com/pikachu444/caelab-prep/pull/67)의 packaging `5fcc01d34768f1915c07f235e0d5688b918283d8`로 교정했다. 앱 source는 `6365237f0d913bac09ca600ce27a579619b09f21`로 고정했다. 분석 child의 DLL 검색 PATH를 선택 환경·base Python·Windows로 제한하고, 선택 환경·staged tools·base Python·System32 밖의 native 입력과 global site-packages 유입은 PYZ/EXE 전에 거부한다. 작성자 관련40검사와 통합 clean clone의40검사는 각각 통과했으며 합산하지 않는다. 원 발견자는 새 build의 실제 Analysis·manifest·로그를 읽어 native448항목/446고유 원천 중 범위 밖0, 이전 외부DLL46개 제거·추가0, 앱91모듈 이름·source hash 불변과 native missing/unresolved 경고0을 확인하고 해당 원천 결함을 종결했다. deprecation·ctypes 분류·중복 경로 경고는 보존한다. 이 커밋은 `[skip ci]`이며 원격 CI 통과를 주장하지 않는다.

같은 source636/tooling5fcc의 작성자 build1회는 exit0이고, frozen CLI 도움말·잘못된 worker 입력의 실패/출력없음과 후보 DLL 경로를 사용한 host loader의 Qt/Gmsh4개 load를 확인했다. QApp·VTK render·SDK API·solver·clean Windows 실행은 아니다. 검증 ZIP은170,533,078B·SHA256 `338fe8d43c05d11b3ffa3048e25dfb1d3e834fdb269561687585d7d417dcb16f`이며 CRC·전체 payload hash·sidecar와 원 private 기록 불변을 확인했다. 이전 source636/tooling636의 외부 원천 포함 후보와 ZIP은 보존하고 배포 미승인으로 유지한다. 자체 `caelab_prep` LICENSE/NOTICE 결정, Qt·전이/MSVC 재배포 조건, 정상 INI·IME/VTK·worker 취소·새 Windows·W1/W2·최종 WB 조합은 별도 잔여다. 바이너리 공개나 N13 전체 종료가 아니며 그룹별7/16/3은 유지한다.

<a id="quad-divisions-progress"></a>

2026-11-04 N24의 [PR58](https://github.com/pikachu444/caelab-prep/pull/58) quad divisions 편집 코드는 `a230d322f71cc2da8104239c7441fa4745c54f27`이다. 기존 candidate 창에서 Load quad divisions로 원 JSON을 읽고 patch의 순서 있는 Edge 1–2/2–3 정수 분할 수만 바꾼다. 입력을 바꾸면 즉시 이전 candidate/Passed/Adopt를 지우고, 기존 generation·예산·공유 edge·실제 lattice/연결·Jacobian/AR·native 반올림 검사를 다시 적용한다. 단위·좌표·patch 정체성은 보존하고 원본 JSON의 같은 bounded bytes로 내용/hash를 묶는다. 수정 snapshot과 선택 source_recipe 자산은 기존 manifest/read/native.assets의 검증·publish 전 원본 보호·rollback·v6 경로를 사용한다. 별도 문서/codec/worker나 CAD/독립 MSH family 확대는 없다.

작성자 신규34고유검사(초기27+추가7)·관련 기존25pass/24deselected를 구분한다. 신규에는 8표현×두 입력의 실제 창·Load/invalid/Cancel16, Q-N3[18,10]의180quad/209node·Q-D2 left[12,6]/right[9,6]의126quad/154node 실제 생성/품질/저장후보 재열기/채택 한 Undo/redo·즉시 관찰자 원본 보호/v6·native 재파싱2가 있다. v6는 같은 process의 새 session이다. 추가7은 source mismatch의 SDK 이전 거절6과 모의 child의 생성 중 원본 변경1이며 실제 SDK 실행으로 세지 않는다. 원 비판자와 CAE 검토자는 소스/검사 정의를 읽어 지적 종결과 범위를 확인했으며 작성자 runtime 재실행으로 합산하지 않는다. 보관처 `C:/Users/pikac/.codex/visualizations/2026/11/04/quad-seed-edit/author-01/report.json` SHA256 `c5aab3963802ed8ba41807ad5bfd217b61f4e5d57a10dd9cf46b6cb2375953c9`에 XML3·정확 파일 snapshot4를 연결한다. 당시 hex/layers 편집의 후속은 [아래 N25](#hex-divisions-progress)로 구분한다. 좌표/patch 편집·recipe 동봉 재생성·Windows OS/VTK·원제품/solver 응답·N24 전체와 그룹별7/16/3은 남는다.

독립 QA의 BeidPrep/no3d 첫 Qt1process는 두 입력에서 generation각1(총2)·Gmsh inspection총4, worker6의 communicate/rc0와 기능60확인을 기록했다. 마지막 검사기가 inspection총2를 잘못 기대해 단언1실패/exit1/overall failed인 `qa-01/report.json` SHA256 `bcd0513571fc45f6b6b6cc6cc066f7dd1bd640dd8b7c9a966eef4582ee7dd109`를 그대로 유지한다. 실제 generate→reader1와 adopt→canonical reader1씩인 호출 원인을 원 비판자가 source/workerstdout으로 대조해 종결했다. line250 부모 종료 집계와 line251 overall passed 지정은 미실행이고 자식별 독립 reap으로 확대하지 않는다. `qa-01/readback.json` `bd0ae1da9c4b0c49ad91ec4822016b6cb970e6455dd3c69994d62ebd87ea650a`는 source94/원본·snapshot/assets/v6/export/INI/PNG의 기록 해시 불일치0과 범위를 연결한다. v6는 같은 process 새 session이며 INI는 하네스가 직접 sync해 복원 검사가 아니다. root와 QA는 원 PNG4의 ASCII까지 □ glyph인 상태를 직접 읽고 시각 판정을 보류했다. 원 실행/그림을 재작성하거나 기능/SDK 실행을 반복하지 않는다. 별도 font-only process1은 QApplication 생성 완료 checkpoint 전에 exit -1073741819(0xC0000005), stdout/stderr0으로 끝났다. 폰트 등록/coverage 완료와 Load·새 PNG의 근거는 없고 Generate/SDKreader/Adopt/OS/VTK는0이다. QApplication 생성 뒤 등록 전 font_state 조회도 다음 저장 checkpoint 앞에 있어, 정확한 충돌 위치·조회 시작 여부와 내부 원인·QApplication 생성 완료는 미확정이다. visual-font-01/exit-readback.json SHA256 `df1405ea45b4572159cac47ab9407eec1e70267caca96ba9d95bcd8147c85c34`와 starting report/harness를 보존하고 재시도하지 않았다. 제품2파일 hash도 불변이다. 코드/기능 확인과 시각 미판정을 나눠 두며 GUI 품질·Windows/N24 전체 합격으로 바꾸지 않는다.

<a id="hex-divisions-progress"></a>

2026-11-04 N25의 [PR59](https://github.com/pikachu444/caelab-prep/pull/59) 직접 divisions/layers 편집 코드는 `02f936c36458536baea418c9d627481987004c6f`다. N24의 같은 candidate 창·분할 표·source_recipe 원본 보호·기존 worker/품질/채택/Undo/v6를 재사용한다. 같은 quad/hex mode에서 patch divisions와 hex의 top-level 공통 layers만 바꾸며 vector·geometry·unit·patch ID/순서는 보존한다. layers도 정수1..10000·전체 예산·공유 edge 검증을 적용하고 변경 즉시 이전 품질/Adopt를 무효화한다. 원 비판자의 Escape→빈칸 결함은 실제2red 뒤 NumericEdit.accept_value의 기존 성공값/복원 계약으로 고쳤고 관련39pass/34deselected 및 원 지적자의 소스/기록 재확인을 연결했다. 별도 dialog·문서 모델·codec·worker는 없다.

검사 파일은 기존34+추가39인73고유 case다. 첫71 중70pass/1실패는 H-D2의 shared 분할을 원래5와 같은5로 넣고 거절을 기대한 오라클 오류다. 원값+1 교정 후 관련2pass/69deselected만 반복했다. 그 실패에서 실제 정상 H-D2 generation이 시작돼 mesh/sdk/metadata 생성까지 관측했지만 pytest398 임시 산출물이 자동 정리돼 원 SDK 출력은 보존하지 못했다. XML과 당시 파일명/크기 관측만 남겼으며 보존된 원 출력으로 주장하지 않는다. 전체73을 다시 green으로 만들었다고 세지 않는다.

마지막 UI 복원 수정 영향을 확인할 두 실제 edited hex만 고정 code의 영구 author-runtime-02에서2pass/71deselected로 검사했다. H-N3[10,6]/layers6은360hex/539node·112.5cm³, H-D2[8,6]+[7,6]/layers8은720hex/1008node·245mm³·공유48face/63node다. 실제 기존 generation/공유 topology·품질 gate/저장 후보 재열기/한 Adopt·Undo/redo·publish 시 원본 보호/v6 freshsession·native 재파싱 범위다. v6는 같은 process이며 solver 수용/해석 응답이 아니다. 앞선 영구 경로의 부모 누락은 test body 전 setup2errors로 따로 보존했고 generation0이며 그 XML을 덮어쓰지 않았다. 보관처 `C:/Users/pikac/.codex/visualizations/2026/11/04/hex-seed-edit/author-01/report.json` SHA256 `a33fdbdb3b63e0bba2840a5430bbee47a40ebff1df628b3d8a2ada69656765fc`는 정확 source3/XML4와 최종 source/recipe/MSH/sdk/metadata/v6/RAD/XML18파일 hash를 연결한다. N24의 원 glyph/별도Qt초기화 실패를 N25에서 재시도하거나 시각 pass로 바꾸지 않았고, 위 source/file 확인을 Windows/VTK/frozen/원제품·전체N25/H-S/F4 판정으로 확대하지 않으며 그룹별7/16/3은 유지한다.

독립 파일 QA는 `hex-seed-edit/review-01/report.json` SHA256 `5667e0b6ff02b9fd17e954e1410ff9a3229d51f3645c7e0c22c3d2e87eb0a7e5`의69확인으로 최종MSH/native/v6 전체 좌표·연결순서·공유48면/63절점과 면의 반대 cyclic 순서, 원geometry/vector/unit/patch 보존·분할만 변경을 대조했다. native element ID는 기존 allocator의 재배정 대응표로 비교했고, reader의 초기 whitespace/동일ID 오라클 오류 기록도 보존했다. 추적29파일 전후 hash는 불변이며 Qt/SDK/worker를 새로 실행하지 않았다. Undo/원본 덮어쓰기 거절은 작성자 XML·검사 본문 근거이며 독립 runtime으로 합산하지 않는다. 원 비판자는 사용법의 Starter 문구도 기존 PR34의225/525요소 입력과 이번360/720요소의 미실행으로 분리한 뒤 종결했다.

<a id="recipe-geometry-fork-progress"></a>

2026-11-04 N24/N25 [PR63](https://github.com/pikachu444/caelab-prep/pull/63)의 코드 `498375df00b22aeed07d7f3a12a428dc94efc98f`는 기존 VectorEdit와 단일 patch recipe validator를 사용해 corner4개·hex vector를 같은 메시 창에서 편집하고 새 recipe 파일로 분기한다. 현재 divisions/layers를 함께 수집하고 mode/unit/topology·source corner 순서는 유지한다. 기존 source_recipe의 동일 geometry/divisions/layers 관계를 넓히지 않으며 새 파일을 기준으로 digest/seed를 다시 읽고 기존 Generate·새 품질·채택/archive 한 Undo를 사용한다. 파일 fork 자체는 문서 Undo 밖이고 원본과의 저장된 geometry 편집 관계·기존 mesh/조건 자동 대응은 없다. 두 patch는 기존 분할 편집을 유지하고 geometry fork는 거절한다. [사용법](docs/usage.md#recipe-geometry-fork)을 연결한다.

신규7고유(API3/Qt4)와 공유 UI 영향13을 확인했다. 원본 hash/기존 파일 exclusive 거절·직렬화1MiB 이전 검사, 미저장 geometry의 Generate 진입 차단, 취소/실패 draft 보존·새 path/hash/seed 전환·같은 저장 값 복귀·두 patch 유지·invalid geometry의 picker 미진입을 확인했다. 모의 candidate를 쓴 무효화 검사는 실제 품질 실증과 구분한다. 처음에는 NumericEdit가 저장 값으로 돌아가도 dirty latch가 남아 생성이 막혔고, 실제2red 뒤 현재 vector값과 저장 seed 비교로 고쳐 영향2green을 확인했다. 옛 후보/Passed는 복원하지 않는다. 최종신규7pass와 앞선 중복 실행은 합산하지 않는다. `recipe-geometry-fork/author-evidence-01/report.json` SHA256 `b25e5e2804e606b1853b6fb8fb20d1c94e9410553d2a4f722a5a2a46aa4b0718`에 원 red/green·XML·실제 하네스를 보존하며 원 요구 비판자가 helper/UI/test를 읽어 경계를 확인했다.

고정 source/offscreen Qt1의 실제 Save as 버튼→새 입력→Generate→Adopt2흐름은33확인을 통과했다. 기존 Q-N3/H-N3 edited 자산을 재사용해 corner를(1,.5,-.25)cm 이동하고 hex vector를1.2배로 바꿨다. quad209nodes/180quad4의 면적은45cm² 유지, hex539/360hex8의 체적은112.5→135cm³였다. 모든 격자 좌표를 원 좌표와 layer projection으로 만든 기대 위치와 대조하고 새 UUID/품질·native 전좌표/ordered 연결·원문 불변·한 Undo/redo·v6 새 session·새 recipe 정확 bytes와 old source_recipe 관계 미사용을 확인했다. v6 재열기는 같은 process이며 solver/질량/강성/응답 판정은 아니다. 새생성2/MSH reader6의 delegated children8완료·원본/소스13 hash 불변이며 전체 suite·solver/OS/VTK/frozen/font/PNG·설치는0이다.

보관처 `C:/Users/pikac/.codex/visualizations/2026/11/04/recipe-geometry-fork/functional-01/report.json` SHA256 `34293df997768daa0a40b1f02ea76b41056660d2e3c4428c8fb2d9e1b1ed2d45`는 source3 snapshot·출력17/보호13파일과 `_functional_fork.py`를 연결한다. chooser의 경로 반환은 대체했고 실제 버튼·NumericEdit Qt 이벤트/현재 reader를 사용한 source 확인이다. 이를 실제 OS·시각·원제품 비교·Windows/frozen/solver 수용·전체 N24/N25/7·16·3으로 확대하지 않는다. 두 patch의 공유 vertex·patch 추가/삭제/연결·일반 곡면/sweep와 기존 메시/조건 geometry 대응은 남긴다.

독립 stdlib 감사 `recipe-geometry-fork/functional-review-01/report.json` SHA256 `d7ac9cce51ff12302aed7e13c6136e9a6b22f654fdc5c6c4f1bb768206129008`는41확인/추적32파일 불변으로 source3·출력17·보호13 hash와 새 JSON의 지정 변환/불변값·전체 lattice의 해석적 위치·ordered 연결·native/v6 새 recipe를 대조했다. SDK 단위/개수·새 UUID/digest를 확인했으며 J/AR 재계산·Undo/redo·UI·SDK 재실행으로 확대하지 않는다.

독립 source/offscreen Qt1의 첫 QA는 실제 Save As 취소/저장·현재 counts/geometry/digest 전환·실제 Escape·불완전/비평면 입력 picker0 등23확인 뒤24번째 compact geometry 단언에서 멈춰 **23pass/1fail·status=failed / passed=false**로 보존했다. Corner4 Z는 ensureWidgetVisible 뒤 rect(31,360,682,22), viewport722×378로 아래4px 벗어났지만 bar494/max973에 추가479px 여지가 있었다. 제품에는 이 QA helper 호출이 없으며 이 자료만으로 수동 스크롤 접근 불가를 확정하지 않는다. `qa-01/report.json` SHA256 `807d116010d4473155b93df2537259a453aa9358ce43ce8f7c79e14a8f42f2d1`·원하네스와 소스/입력 hash를 유지했다.

실패/미실행 대상만 새 Qt1로 확인한 `qa-remainder-01/report.json` SHA256 `8abaabfb2a4b2e919978ee6b89c4a910c241824bc701ad3b762e4c6c38a4ee4a`의18확인은 Corner4 Z·Sweep XYZ·Save As full rect와 실제 bar8px 이동·keyboard/Escape·quad/two-patch 상태를 확인했다. 이번 viewport는722×366으로 원 실패 상태와 달랐고 다섯 대상은 first ensure부터 들어왔다. 따라서 원4px 이탈의 재현·수정·소급 pass나 전체24 합격으로 바꾸지 않는다. 소스6/입력·문서 상태는 불변, 각 QA의 subprocess/SDK/생성/OS/VTK/font/PNG는0이다. 원 상태의 compact full-rect/시각 수용은 미확인으로 남긴다.

<a id="recipe-archive-progress"></a>

PR62는 검토 head `3deb08751c53f7d491e84fd73c65c30898f76abb`에서 정상 merge `1f161698cca2decf025c6fd9fb2e2763fae514a7`했고 fetched main의 두 부모·동일 tree `8b0a868b5532560e4199a5b6e3db44f4a598d112`/diff0을 확인했다.

2026-11-04 N24/N25 [PR62](https://github.com/pikachu444/caelab-prep/pull/62)의 코드 `8708b2de897e8f4a282698385b850efdc8ba2f03`는 기존 불투명 Resource·execute_many(additions)·atomic container를 사용해 structured 채택 입력을 native와 한 Undo로 보관하고, 같은 MeshCandidateDialog의 Open project recipe…→추출/Load→기존 Generate로 새 후보를 만든다. 실제 recipe와 선택 source_recipe의 정확한 bytes·검증된 digest를 한 bounded read에서 묶고 기존 divisions/layers 편집 관계를 재사용한다. 각각1MiB·고정 ZIP role 경로·선택 v6 registry이며 source RAD archive를 전용하거나 별도 문서/일반 codec 체계·WB 모델을 만들지 않았다. 같은 후보를 반복 채택해도 archive UUID는 별개이며 당시 입력을 이후 메시 편집의 복원으로 표시하지 않는다. 현재 native/WB 고정 L 소비 계약은 유지한다. [사용법](docs/usage.md#project-recipes)·[저장 계약](ARCHITECTURE.md#작업-파일과-native-덱)에 범위를 연결한다.

새 API/Qt 고유23=API16/Qt7과 기존 동기 observer·실패 복구 영향4를 확인했다. 외부 자산 제거는 retained 원본이 아닌 flat private 복사본만 대상으로 했고 저장된 문서의 정확한 원문 추출·기존 폴더 무덮기·반복 채택/한 Undo·동기 save·손상/누락/중복/UUID충돌/읽기 전 크기 제한을 확인했다. 첫 rollback01의 지속 실패 주입은 복구까지 실패시키는 테스트 설정이었고, rollback02는 publish 전 캐시가 중간 상태를 숨기는 describe를 잘못 기대했다. 직접 root projection에서 실제 restore 뒤 일회 실패를 주입한 rollback03의2pass로 native+archive+보호 경로 복원을 확인했다. 원 비판자가 발견한 A→B→A 동일 archive 재열기 반례는 실제1red 후 query의 문서 ID/epoch/revision을 lock 안에서 묶고 추출 lock의 폴더 생성 전에 검사해 영향6green으로 종결했다. 두 번째 추출 파일의 I/O 실패1도 기존 입력/seed를 보존하고 false/error를 반환했다. 일부 새 폴더는 남을 수 있어 추출 전체의 원자성을 주장하지 않는다. `recipe-archive/author-01/report.json` SHA256 `a17ded219aef8436809204f530946bb7470ffe319e03d20a6a06a0968a1a1b53`에 실패/XML/실행 하네스를 보존한다.

고정 코드의 source/offscreen Qt1에서는 두 실제 채택 문서의 private 외부 자산을 제거한 뒤 각각 별도 plain process에서 SDK/Qt import 없이 원문을 추출했다. 실제 Open project recipe 버튼→Load→Generate로 quad209nodes/180quad4와 hex539/360hex8을 각1회 새 생성했고 새 UUID·현재 reader의 새 품질 검사와 전체 좌표/ordered physical 연결의 동일성을 확인했다. 문서의 native 자원/수정 번호는 바꾸지 않았다. 이는 같은 실제 입력·현재 고정 엔진의 재생성이며 임의 버전/후속 메시 편집 복원 보증이 아니다. 총25확인·generator2/MSH reader6 delegated child 완료, 별도 extract process2이며 새 solver/VTK/OS/frozen/font/PNG는0이다. 정상1060×720/최소760×480의 recipe 버튼 x/y/width/height가 scroll viewport 안에 드는4확인을 시각 합격과 구분한다. `C:/Users/pikac/.codex/visualizations/2026/11/04/recipe-archive/functional-01/report.json` SHA256 `adb92a87980b6f0578a909ba12dcd1ed2cdda24b8887e44fe2b18bbd3f73dc1e`는 source6 snapshot·출력26/보호16파일 전후 불변과 actual harness를 연결한다. 옛 Passed나 MSH/SDK를 프로젝트 첨부로 재생하지 않는다.

독립 stdlib 파일 감사 `functional-review-01/report.json` SHA256 `35d57f51139c13daa8c6bb9bc44d50fd32906d8362624a0d3914fa1c558d5717`는47확인/추적44파일 hash 불변으로 ZIP의 current/historical 원문·추출본·원 자산 동일성과 두 새 MSH의 전좌표/ordered 연결·새 UUID·단위/개수를 대조했다. SDK JSON에는 수치 J/AR가 없어 품질 통과는 보존된 실제 reader/UI 단언 근거와 구분하며 독립 SDK/Qt 재실행은0이다. chooser 반환값 대체와 offscreen geometry를 실제 OS/시각 판정으로 확대하지 않는다.

독립 source/offscreen Qt1의 실제 버튼·QInputDialog/QFileDialog 선택 흐름은20확인을 통과했다. 선택/폴더 취소의 source/output·수정 중 분할 수 보존, 실제 v6의 current/historical bytes 추출·[18,10]/cm·미생성 상태·문서 무변경을 확인했다. A→B→sameA의 ID/revision/archive UUID는 같고 epoch만 다른 반례도 세 expected 값을 전달한 추출에서 stale_recipe_selection으로 거부됐으며 child 폴더는 생성되지 않았다. 정상/최소창·DPR1의 버튼 full geometry는 시각 수용과 구별한다. `qa-01/report.json` SHA256 `e4f84420cf2357f589fe984d7bafd8bdf1948e2b260ead0edee0be6b26f3954a`와 실제 harness를 보존하며 원 프로젝트/source6은 불변이다. subprocess/SDK/생성·solver/OS/VTK/font/PNG·재시도는0이며 독립 새 생성 확인으로 확대하지 않는다.

독립 `compat-review-01/report.json` SHA256 `ac00c0e04423e9cc50dab5b9f02a6c2dd653c2b42f8d039c146ba23b197eee3b`의23확인은 실제 이전9df4b515 session source를 현재 의존 모듈과 함께 읽어 native209/180·539/360을 열고 재저장했을 때 선택 registry·recipe payload가 유실됨을 확인했다. 재저장 native registry/raw는 같고 현재 reader의 recipe 조회는 빈 목록이었다. 원 프로젝트2/source6은 불변이며 이전 전체 설치나 archive 보존형 writer 호환의 증거로 확대하지 않는다. 이전 문서의 첨부 부재·구버전 재저장 유실과 새 UI 기능을 구별한다. PR62 당시 좌표/patch/sweep vector 편집은 미연결이었다. 후속 단일 patch의 새 geometry recipe는 위 별도 확인에 연결하며 두 patch/patch 구성·원제품/시각/Windows·solver/물성/응답·전체 N24/N25/7·16·3은 미완료로 남긴다.

<a id="cad-replacement-progress"></a>

N18 PR61은 검토 head `dd3ddf6e771250a2e4a51c0c939e9d2ff434708a`에서 정상 merge `9df4b515b95f2f0ad5a9b832751d275ea3e5aa2b`했고 fetched main의 두 부모·동일 tree `8bee1eb70cb5a83684a87a7b052b817beead7cb9`/diff0을 확인했다.

2026-11-04 N18 [PR61](https://github.com/pikachu444/caelab-prep/pull/61)의 코드 `7ba062457fbfe79316bef0357b02d6c391f96a09`는 기존 CAD 후보 검증/순수 준비·root 채택 writer와 prepared stale/reconnect를 재사용해 참조된 adoption-owned PART 교체를 연결한다. Review는 문서·자원 token/mesh revision·epoch에 묶인 상태를 봉인하며, Apply는 자산을 재검증하고 root+relations를 한 Undo로 게시한다. 공개 plan 사본의 변경은 게시 상태를 바꾸지 않는다. 원 그룹·조건을 유지하고 영향 명시 집합을 stale로 남기며 자동 대응/새 경계 절점 추가/하중 재분배는 하지 않는다. 기존 직접 채택의 strict 참조 거절·외부 INCLUDE 소유·미확인 카드·변환/단위/전체 품질 경계를 유지한다. GUI는 Review replacement/검토/Apply와 기존 재연결 창을 사용하고 별도 문서·codec·WB 소비 모델을 만들지 않았다. 사용법은 [CAD 메시 교체](docs/usage.md#cad-replacement)에 연결한다.

원 비판자가 발견한 이동 절점 overlay의 잔존은 실제 plate/cylinder의 public node move→교체 2red로 재현해 제거되는 ID만 정리하고 shared 절점 이동값은 보존했다. 기존 assembly의 참조 없는 exact pair 분류를 공유해 inspect 성공 후 새 allow-stale 경로에서만 BEAM/TRUSS 속성·고정 좌표계의 재차 unknown 거절을 해소했다. 다른 BEAM 방향점으로만 쓰는 절점도 보호하며 signed BEAM PART 헤더를 공통 파서로 해석하고 projection이 불완전한 선택 signed TETRA 헤더는 무게시 거절한다. 조건 라벨의 live 조회 경합은 sealed plan 라벨로 교정했다. 원 API·GUI 지적자는 수정 소스를 다시 읽어 해당 지적을 종결했다. 참조 범위 검사는 모든 PROP 수치·solver 정식화 인증이 아니다.

작성자 API 두 retained solid 입력의 고유 36사례, 신규 Qt 20사례와 기존 직접 채택 영향4·structured source/cancel5·prepared 교체3·shared BEAM overlay4를 영향별로 확인했다. 라벨 수정 뒤 Qt6은 신규2+기존4로 앞선 실행과 겹치므로 합산하지 않는다. API 첫20pass/4실패는 잘못된 테스트 hook 경로와 SKEW 준비 오류였고 관련4를 교정해 통과했다. 다음16pass/2실패는 3D solid에서 SURF/PART를 만들려던 테스트 준비를 제품이 올바르게 거절한 결과였다. 최종 TYPE7 검사는 실제 2D 입력에서 아래 별도 수행했다. publication 실패 주입은 execute_many 진입 전 실패와 원본 경로 복구이며 중간 commit rollback 실증으로 확대하지 않는다. XML/실패/하네스는 `cad-remesh/author-02/report.json` SHA256 `4657a101383b2963635d8f0c99566fc2a8d1e653a85e81cd14c09cf989067cac`에 연결한다. 전체 suite·CI/solver를 반복하지 않았으며 등록한 새 CI 검사를 이번 cloud 통과로 세지 않는다. 후속 test-only `292a90da961fb6bbcd2aceb9e77e84b608841ca6`는 같은 plate 후보에서8표현의 실제 QAction→Review/Apply→기존 재연결창 탭1→한 Undo를8pass/28deselected로 확인했다. `cad-remesh/host-handoff-01.json` SHA256 `850d2ac1295ebca358a389fe061645e50ab9a83e49040e305bc59c205fa5a4e6`과 source/XML을 보존하며 원제품8개 비교·cylinder의 host8 확인으로 확대하지 않는다.

고정 코드에서 Phase37 XAO를 재사용해 plate와 cylinder 각각 1회 size1.2 후보를 실제 생성했다. 기존1.5와 비교해 plate는354nodes/1062tet4→406/1279, cylinder는287/963→290/975였다. 같은 geometry UUID/revision·surface/volume identity와 전체 후보 품질을 확인하고 offscreen Qt1 process에서 두 Review/Apply·단일 Undo/redo·stale v6 저장·기존 Find/Add/명시 재연결·native 전체 좌표/연결을 확인했다. 별도 v6 reader2 process도 stale과 출력 차단을 확인했다. 대응은 시험에서 고른 유효 현재 절점 두 개이며 원 경계 영역·힘의 동등성을 입증하지 않는다. 별도 plate XAO의 2D 후보1생성은 single old main PART의 일시 소실과 역할별 명시 재연결 API를 확인했고, 같은 후보를 old/new로 사용해 2D size 변경 실증과 구분한다. 실제 생성은3회, 기존 MSH 검사 호출14회이며 새 SDK 연구가 아니다.

독립 source/offscreen Qt1의2D TYPE7 흐름은24기능 확인을 통과했다. Review/Cancel 무변경·한 publish/Undo/redo·같은 process 새 v6 session·기존 Find/Add/Apply의 secondary→main 역할별 재연결을 확인했고, main만 stale인 중간 단계에서는 출력이 차단됐다. 원 BCS/TYPE7 선언과354nodes/708tri3 export 재열기를 확인했다. 기존 canonical MSH reader5·launcher5 rc0이며 source94/입력5 hash는 불변이다. `qa-01/report.json` SHA256 `fd46600ebe7be7709b27c7c529a26f82221ecfb5918b057845d9fad154bee810`과 실제 harness를 보존한다. 새 생성·solver·OS·VTK·font·PNG0이며 descendant별 reap이나 시각 합격을 주장하지 않는다. 같은 후보의2D 관계 확인이며2D size 변경이 아니다.

독립 QA가 발견한760×480의 review checkbox 가로 이탈은 실제 scroll viewport에서 x=-16인1red로 재현하고 `d356cb3761bf5e7f3405ad69f99af3964d851ff0`에서 짧은 Replacement reviewed 라벨·전체 영향 tooltip/accessiblename으로 고쳤다. 정상1060×720/최소760×480의 indicator 포함 가로 전체 범위·sizeHint 너비·초기 미선택2pass로 영향만 반복했으며 SDK/TYPE7 전체 흐름은 재실행하지 않았다. `compact-review-01/report.json` SHA256 `b70780596b30c6e5b485876900cfeacb3ba13f72dc2033c6e26aeea48f457bd7`과 수정 source2/red/green XML을 보존한다. 기존 재연결 창은 선언한 최소 높이500 때문에 요청760×480에서 실제760×500이었음을 유지한다. 원 지적자는 수정 source/snapshot/red/green을 읽어 가로 이탈을 종결했다. 원 compact 보고서의 full rect 표현은 같은 폴더 clarification.json에서 가로 범위 확인으로 한정했고 y/height·2D 전체 rect/시각 수용으로 확대하지 않는다.

보관처 `C:/Users/pikac/.codex/visualizations/2026/11/04/cad-remesh/functional-01/report.json` SHA256 `34e2bf0d30f300fb8e27bb09f7fc483eb3130933e2d578430636e580d9ddcb88`의30확인·source7 snapshot·출력38파일·보호17파일 전후 hash와 실제 `_functional_remesh.py`를 재열 수 있다. v6의 GUI 재열기는 같은 process 새 session이며 별도 reader2는 저장된 stale 문서 판독/차단만 수행했다. 독립 파일 감사 `functional-review-01/report.json` SHA256 `dd2300b5470a98f35023e66d432914928b5031d9b3b5441bbd2a225a0fa3952f`는45확인/추적57파일 불변으로 source snapshot7·manifest38·보호17 hash, stdlib binary MSH의 전체 좌표/ordered 연결·v6 stale/recovered·원 조건을 대조했다. native 좌표 최대차는0이었고 독립 Qt/SDK 재실행은0이다. 원 campaign 뒤의 명시 test-only 수정은 원7ba snapshot과 분리했다. 기존 N24 glyph/Qt font probe는 재시도하지 않았고 이번 새 위젯 동작 확인을 시각/Windows OS·VTK/frozen·물리 응답/solver 수용·원제품/전체 P7b 통과로 바꾸지 않는다. N18와 그룹별7/16/3은 그대로 남긴다.

<a id="adoption-source-progress"></a>

2026-11-04 N18의 다음 CAD 재메시 연결을 준비하며 원본 경로 보호 누락을 [PR60](https://github.com/pikachu444/caelab-prep/pull/60)의 코드 `43f4ef8a0e6b59f877d0ab1394ebd022f0a49b07`에서 고쳤다. 기존 public adopt_mesh_candidate의 인수·strict 참조 거절·한 command·보호 경로의 publish 전 등록/실패 복구는 유지하고 내부 순수 상태 준비를 분리했다. CAD metadata.source.path가 있으면 캡처 자산과 함께 원경로를 보호한다. 검증된 metadata digest와 이번에 읽은 동일 bytes를 대조한 뒤 경로를 해석하며, 키가 있으면 nonempty string을 요구하고 부재만 생략한다. standalone MSH의 기존 original_path도 같은 경계를 사용한다. 원본 내용의 최신성이나 재생성을 보증하지 않는다.

기존 OCP fixture 경로9건은 미설치로 skip이며 성공으로 세지 않는다. 보존된 Phase37 plate/cylinder를 기존3함수에 직접 전달한6pass, 새 원경로 보호2pass·준비 무게시2pass를 구분한다. 첫 red-01은 테스트의 MeshCandidate.manifest_path 오타로 API 전 실패했고, 실제 assets.metadata 계약으로 바로잡은 red-02는 동기 관찰자의 보호 누락을 재현했다. 쓰기 대상은 private CAD 복사본이며 finally 복원도 그 복사본에만 수행했다. 원 비판자의 metadata A→B 교체/잘못된7값은 validation return hook의8red→8green으로 닫았고, 마지막 비모의 cylinder 보호/무게시 준비2건과 standalone 2D/3D 영향2건도 통과했다. 단계별 중복을 합산하지 않으며 v6 재열기는 같은 process 새 session이다. 새 메시 생성·Qt/OS/VTK/solver는0이고 실제 candidate 검증에는 기존 SDK reader를 사용했다.

`C:/Users/pikac/.codex/visualizations/2026/11/04/cad-remesh/adoption-source-author-01/report.json` SHA256 `95907386f509f18b4ea21aa3e524021ba1eb98e1a39b73ace1a162e98c4fce47`은 source2·phase9를 연결한다. 실행 wrapper는 stdin이었으며 호출한 실제 repo 검사 함수 snapshot과 각 phase report를 보존한다. 독립 파일 검토 `adoption-source-review-01/report.json` `e13511b1cfefde1b07d9d23e66fbee8de15167839c332aee3f35afbae3f6c0da`의35확인/추적71파일 hash 불변은 수정 전 v6의 원경로 누락과 수정 후3파일의 원본/캡처 보호·원 STEP hash·복사본 쓰기 경계를 대조한 근거다. 독립 runtime/SDK 재실행은0이며 원 비판자가 동일 bytes와 falsey 지적을 재확인해 종결했다. PR60 당시 참조가 있는 CAD 교체의 sealed preview·stale 동시 게시·GUI 연결과 BEAM 방향점 공유 보호는 이 묶음에서 구현하지 않았다. 후속은 위 [CAD 교체 근거](#cad-replacement-progress)에 구분하며 N18·Windows/시각·7/16/3은 닫지 않는다.

<a id="part-ownership-progress"></a>

2026-11-04 N18 요소의 PART 소유 이동은 [PR56](https://github.com/pikachu444/caelab-prep/pull/56)의 API `d6f3f0f8f8e8046043408ca6731774123030b1f1`, 공용 UI/변경 없는 행 표시 `80aaac4b1f098588bc5828c74bcc4bb5679a16f0`, 원문 오류 경계 `be452565bba85bbb314bc16b29fca710f94e6604`에 연결했다. 기존 `part.assign`의 MAT/PROP 변경과 별개이며 source-qualified 요소→PART 참조를 사용한다. 기존 native replacement/insert/delete state로 원 resource 안의 요소 행을 이동해 native ID·연결·orientation·전체 suffix/CRLF·주석을 보존한다. native 헤더 블록 UUID는 바뀔 수 있다. 빈 기존 PART도 실제 MAT/PROP UUID 해석과 렌더된 이동 요소의 기계 프로필 검사를 통과해야 하며, 이름만으로 허용하거나 MAT 수치·모든 PROP 필드/solver 수용을 인증하지 않는다. old/new PART의 실제 segment와 incoming source generation을 포함해 원 선언을 stale로 보존하고 빈 target/마지막 main support는 거부한다. [사용법](docs/usage.md#element-part-ownership)을 함께 갱신했다.

최종 작성자 영향은 신규 API21+삭제24+merge19+반전20=84pass다. 첫 native API 미연결1red, 초기13pass, empty-target14실행 중1실패는 `copy_card`가 PART도 지원한다고 오해한 fixture 오류였으며 실제 임시 RAD PART900으로 교정한 해당1pass와 후속 경계6pass를 구분한다. 원문 row/shell angle·Thick/BEAM orientation/CRLF·comment, directive 거절, incoming TYPE7 main확장4→8, no-op/서로 다른source/기계 성분 소실과 CAS·한 Undo·v6/native 출력을 확인했다. 독립 CAE 원 지적자와 backend 검토자는 source를 읽어 한정 경계에 새 blocker가 없다고 판정했다. 새 Qt20(8표현×두입력16 포함)과 기존 반전/삭제42pass에서 같은 pending list·guard·수명/Undo를 재사용했다. 독립 UI 검토자가 발견한 중복 PART ID/잘못된 assignment의 생성자 예외는 실제2red→picker에서 UUID/header만 읽고 Preview API가 검증/진단하도록 고쳐 영향4pass로 확인했으며 원 지적자가 종결했다. 새 Qt고유사례는 해당 두 반례를 포함22이며 반복 실행은 합산하지 않는다.

독립 source/offscreen Qt 첫 실행은 Preview·Cancel·native PART/MAT/PROP·incoming source의4확인 뒤 UI Apply1 후 복합 assertion에서 중단됐다. QA가 PART header를 다시 만드는 native 블록 `card_id`까지 불변으로 요구한 오류였다. 저장된 native element77/resourceA/연결과 PART9→12·event1 및 header-block UUID 변경은 확인했고, 복합식의 다른 미기록 항목·미실행 Undo/v6/reconnect/native parse를 통과로 추정하지 않는다. 원 B06 UI·하네스·PNG4/실패 기록은 보존했다. 후속 Qt1회는 API ownership plan/apply각1로 상태를 재구성하고 개별 보존11항목·실제 Undo/redo·v6 freshsession·stale export 차단·기존 Qt 창의 secondary3/mainPART12 identity direct Apply와 stale없음·TYPE7 not-applicable까지17확인 뒤 마지막 native parser의 full-span 비교에서 중단됐다. 원 상태·행·원선언 보존을 확인한 단계와 마지막 실패는 합산하거나 덮어쓰지 않는다. 원 QA agent의 다음 턴은 실제 모델 수용량 오류로 종료됐고 새 모델/작성자로 바꾸지 않았다. 원지적 교정의 UI `7070cfc049fc8cfac38f02dac97bc675e036a95bdc519428acb2bf2fecc840f7`은 첫 그림/실행 `b06e8cad…09bad479`와 귀속을 분리한다. OS/VTK·SDK/solver/build/fullsuite는 새로 실행하지 않았고 N18 전체·그룹별7/16/3은 그대로 남긴다.

보관처는 `C:/Users/pikac/.codex/visualizations/2026/11/04/part-ownership/qa-01`이다. first-attempt/report SHA256 `914fa5d7685bebdfc5e703611d06319de28e68c07a6d71e84ccf7a8d3ba74edb`·remainder-01/report `2bd9b7c24c37a8a5ca0835d29c3a8f6526cc2dfd4f6c955ce0984f01660a9bc4`는 각각4/1실패·17/1실패 상태를 그대로 보존한다. root는 새 GUI·모델 재구성·export 없이 저장된 export만 별도 plain reader process1회로 읽어11개 항목을 확인했다. `native-readback-01/report` SHA256 `13d3c2838136fcec409048517e133580d80661e14382c377f8197082211d58df`는18nodes/6cells·좌표/ID·PART12의shell77+80·TYPE7 friction.2/not-applicable·secondary[3]/main[12]와 실제 attachment, 원 INTER의 header/title/data exact bytes를 확인한다. 마지막 full-span 차이는 exporter의 실제 source INCLUDE1줄뿐이고 export 내부 대상 파일 존재·원 출력/하네스/v6/보고서의 해시 불변을 확인했다. 독립 검토자가 실제637byte INTER payload/추가70byte INCLUDE와 parser/exporter 구현을 읽어 이 원인 분리를 확인했고 한정 종결했다. root reader의 직접 보호 범위는 출력·프로젝트·이전 QA8파일이며 제품 source 불변은 앞선 QA의 해시 근거다. 원 조건 payload와 generated file directive를 구분한 판독이며 원 QA 실패를 pass로 바꾸지 않는다. v6 재열기는 같은 QA process의 새session이고, 별도 root process는 native export 판독만 수행했다. root와 원 QA가 정상/최소 B06 그림4를 직접 읽었으며, 최소창 긴 source표시는 잘리고 전체 currentText/tooltip data는 보존됐지만 실제 tooltip popup은 미확인이다. 이 자료로 Windows OS/VTK·frozen·물리 응답/8원제품 비교·전체 N18을 닫지 않는다.

<a id="element-deletion-progress"></a>

2026-11-04 N18 요소 삭제는 [PR55](https://github.com/pikachu444/caelab-prep/pull/55)의 API `6166269bfdc95f97e647fc4353342c67e0b37cbb`·공용 UI `61494015c02267c831219e3036fc50d6e99aa9bd`에 연결했다. 기존 pure 후보·native slot writer/trial·member-row writer와 CAS/Undo/v6를 재사용한다. `keep`/`delete_new`는 명시 선택이며 이미 고립된 절점은 보존하고 BEAM orientation 참조도 포함한다. 원 PART/집합/조건 선언은 그대로 두고 영향 집합은 stale로 보존한다. 생존 대상 투영은 preview 복사본에만 반영하고 실제 복구는 기존 mapping/Drop 검토에 남긴다. 빈 제안 집합과 마지막 TYPE7 main shell 제거는 현재 거부한다. 살아남은 절점의 DOF 소실과 kept orphan의 무지지를 검사하며 질량·운동량·에너지/접촉 응답 보존을 주장하지 않는다. [사용법](docs/usage.md#element-deletion)을 함께 갱신했다.

신규 API24고유사례는 초기 API 미연결2red, 구현 뒤16pass/4 테스트 oracle의 없는 nodes키 오류를 실제 snapshot으로 교정한 뒤 신규20+merge19+shell20+Drop17=76pass, 후속 source 경계4pass로 확인했다. SURF/PART projected-cardinality2와 survivor1 불일치는 독립 source 검토자의 원지적을1red로 재현하고 pure의 같은 projected_members 계산을 공유해1green·pure24+해당1=25pass로 고쳤으며 원 지적자가 종결했다. 첫 작성자 Qt20은8표현×두 실제 입력16·정책변경·누적source목록·실제삭제후Drop복구·stale/draft 차단이며, 공유 UI로 옮긴 기존shell Qt22도 통과했다. 위 실행은 겹침을 더하지 않는다. 독립 CAE 원 지적자와 source/UI 검토자는 실제 소스와 저장 기록을 읽어 한정 범위의 차단 지적을 종결했다.

독립 offscreen Qt 첫1process/13확인은 실제 Delete QAction 두창의 Preview/Cancel1·Apply1·Undo/redo1·v6와 같은 process의 새session, stale export 거절, 실제 재연결 QAction의 map4+Drop9/Preview/Apply·native 새parser를 확인했다. `truss_shell_hex`의 TRUSS78·새orphan9 삭제 후8nodes/2cells와 원멤버[4,9]/조건 선언 보존·stale, 복구 후stale없음과8nodes/2cells 출력을 구분한다. 해당 모델의 기존 orphan은 비어 있으므로 기존orphan1000 보존은 작성자 별도 copied-input 검사로만 귀속한다. TYPE7 실제 독립 실행·새process 재열기는 이 대표 흐름에서 확인하지 않았다. root와 독립 QA가780×600/540×420의 PNG4를 직접 읽었고, 표 가로scroll0·본문 상하 접근·footer/검토/Apply/Close와 물리 한계 문구를 확인했다. 이는8원제품 비교나 전체 GUI 품질 승인이 아니다.

보관처는 `C:/Users/pikac/.codex/visualizations/2026/11/04/element-deletion/qa-01`이다. 원입력/소스 해시·실사용 source snapshot/map·하네스·v6 stale/recovered·export RAD/INCLUDE와 그림4를 보존하며 최종 report SHA256은 `ee41c429b20c8c92f17d1d3c69afe24be14b511912652abc8fb871e7cf5caa3a`다. UI physical `3dbc24a2f53f845a457b48376b386506d4d46c0f875b5d8ac8b19f54f151145b`에서 실제 실행했고 전후 source/입력은 동일하다. OS 입력/VTK Render·SDK·solver·새build/full suite는0이며 frozen 납품·물리 응답은 미확인으로 남긴다. 이 PR 당시 N18의 part 소유 재배정·재메시와 나머지 P7b, 그룹별7/16/3은 닫지 않았다. 후속 소유 이동의 실제 소스 검증은 별도 단위에 연결한다. PR55는 검토 head `8f73e04bda31b8c434ef28143dfd3acc5e75631e`에서 정상 merge `0e823da1ad2f4869c3fd782451b95839111cc789`했고 fetched main과 tree `b10102591c19dc56df61f143d1a0b868640ad9dd` 일치를 확인했다. 코드·실제 입력/출력·독립 검토와 소스 검증의 게시 범위는 같은 PR55에 연결한다.

<a id="mesh-target-drop-progress"></a>

2026-11-04 N18의 옛 멤버 명시 Drop은 [PR54](https://github.com/pikachu444/caelab-prep/pull/54)·코드 `90ddcc6dbe24c3264668a5350c704205d3e74e99`에서 기존 mesh reconnection의 sealed plan·단일 Apply/Undo·v6와 공용 PreparedMeshDialog에 연결했다. 절점·요소·SURF/PART의 원 멤버 전부를 mapping/Drop의 겹치지 않는 분할로 요구하며, 생략을 Drop으로 추정하지 않고 빈 최종 집합은 거부한다. 반복 절점 대응의 기존 opt-in과 최종 BCS/TYPE7/CLOAD/INIVEL 검사를 유지한다. 원 조건 선언값은 바꾸지 않으며 실제 메시 entity 삭제와 구분한다. [사용법](docs/usage.md#mesh-target-drop)을 함께 갱신했다.

작성자 API 영향36(신규15+기존 coalescence13+attachment8)과 후속 attachment2, 신규 Qt16고유사례(8표현 포함), 기존 UI/coalescence 영향36을 확인했다. Qt 첫14pass/2실패는 PART 선언 source와 stale 상태의 두 번째 편집을 잘못 예상한 테스트 준비·기대값 오류였고 교정 영향6pass에는 겹치는 사례가 있어 합산하지 않는다. 독립 소스 검토는 backend와 UI의 고정 physical SHA에서 차단 결함 없음으로 판정했다. 독립 source/offscreen Qt 대표13확인은 첫1process exit0이며 실제 QAction/Cancel+clear·Drop Apply1·Undo/redo1·v6와 같은 process의 새 project/native parser session을 확인했다. mesh9nodes/3cells·원선언은 보존되고 미평가 CLOAD vector6→3, 남은 stale=None이었다. TYPE7·non-node UI는 이 대표 독립 실행의 범위가 아니다. 정상/최소 그림을 읽고 발견한 Review열 가로밀림은 `e4f166c2c048f7def5247b68a7e7e677fd3da140`로 고쳐 root영향2pass와 독립 tiny1process/5확인·실제105/105스크롤·Find/Add/Drop/Clear클릭·Cancel불변으로 확인했다. Drop Clear뒤 옛 상태문구가 남은 원지적은 두상태각1red→`8106bfa50ce0b22b9c1b56fe45b9a68b44f41e53`→영향2pass로 수정했고 원 QA 지적자가 최종 source와 red/green XML을 읽어 종결했다(추가 Qt0). 신규Qt고유사례는 마지막 최소창1을 포함17이며 반복 실행 수는 더하지 않는다. [PR54](https://github.com/pikachu444/caelab-prep/pull/54)는 검토 head `09087c9afc376bb5595da2358261c7b22f1b36e2`에서 정상 merge `63eaaa0bf60a6d24d7b5732c3d3d35570c6a41f6`했고 fetched main의 동일 tree `55190e86bdf3d20f57df04bb9cd758756fa49df4`를 확인했다. 전체 suite·SDK·solver·OS·VTK Render·빌드는 반복하지 않았다. 이 PR 당시 element removed_cells writer/trial/UI는 미연결이었다. 후속 삭제 검증을 별도로 연결하며 N18 전체와 그룹별7/16/3은 미완료로 남긴다.

근거는 `C:/Users/pikac/.codex/visualizations/2026/11/04/mesh-target-drop/qa-01`의 원 report SHA256 `1e7dcab40a13be8f286688bc75f2c408195dc34805b67312d144db2b510061b6`, source3 snapshot·v6·실제 export와 `compact-followup` report `067f7e630387734bef6efde3b901622c6b80cb3ca44c022514c4f81bef84ed85`·새 layout source·총PNG9에서 재열 수 있다. 본 QA의 UI `a2dfdca8…f1d35bb0`, layout QA `2d1fef95…f5cc5e8e`, 마지막 caption 수정 `a090102f…f71b840`과 `compact-followup/caption-read-closure.json`(SHA256 `315f2e4e270fc00f0f23567d7f66f2c7a8d56d61ebd609cef2ca6969a55131e1`)은 서로 다른 시점이며 root도 두크기 그림을 직접 읽었다. Windows OS/VTK Render·새process 재열기·solver/물리 응답과 최신 frozen 납품은 이 source 검증으로 닫지 않는다.

<a id="reconnection-attachment-progress"></a>

2026-11-04 [PR53](https://github.com/pikachu444/caelab-prep/pull/53)·코드 `5effcba52911411f1ee6f4dcf531b63160d79070`는 최종 BCS/TYPE7 대응과 contact 집합 preview가 존재하지만 무지지인 절점을 수용하던 경계를 보완했다. 반례 Node6은 `beam_shell_tet`의 BEAM orientation 전용 절점이며 다른 모델의 같은 ID를 뜻하지 않는다. 원5실패/양성3에서 총43통과(신규8+기존Group16+Merge19), 진단 영향5통과/3deselected를 구분한다. BCS inactive_rotation-only와 실제 무지지 진단을 분리하고, TYPE7은 해당 stale 역할만 pending으로 남겨 resolved secondary 검사를 숨기지 않는다. 원 CAE 지적자와 독립 소스 검토자가 source를 대조해 지적을 종결했다. 기존 full mapping·typed reference·CAS·stale/export 및 CLOAD/INIVEL 경계는 유지한다.

독립 sourceQt 첫 실행은 BCS/TYPE7의 Node6 Preview/direct Apply 거절과 Node7 복구 등15확인 뒤 TYPE7의 기존 not-applicable을 supported로 오해한 QA assertion에서 중단됐다. 그때 최종 main stale 값은 미기록으로 남겼다. 두 번째 실행은 QA의 CRLF 문자열/바이트 hash 비교로 결과 저장이 실패해 제품 관측을 회수하지 못했으며 통과로 세지 않는다. 보호 원본과 실패 하네스를 유지하고, 마지막 복구 실행의 남은4확인에서 실제 main identity 복구 뒤 stale 없음·public status not-applicable/진단 없음·secondary7/main PART9/friction.2·원 INTER 선언 보존, export의 새 RAD parser9nodes/3cells와 실제 membership preview의 Node6 차단·Apply 비활성/Cancel 초안 보존을 확인했다. 마지막 재구성 API/nodeMove1·secondary7 대응1·main UI Apply1·export/parser1·membershipPreview1을 기존 guard/BCS 검사 반복과 구분했다. 총 Qt3시도이며 15/미회수/4를 합산하지 않는다. export 임시 파일은 parse 후 제거됐고 원 입력·하네스·관측 값/해시는 보관한다.

자료는 `C:/Users/pikac/.codex/visualizations/2026/11/04/reconnection-attachment/qa-01`의 원 `report.json`(SHA256 `108356df743f618bdfb7fbcee69427ab2d0845e2c5b1aeda414e5e616f5bf99c`)과 `remainder.json`(SHA256 `75606ecb3c3d68d0b85ff7f656c0761a302390118c3cebbde86066313cc172a5`), 실패 하네스·exact-byte source3 snapshot에서 재열 수 있다. Source/원입력 전후 해시는 유지됐고 새 SDK/solver/VTK/OS/그림은0이다. 이 정적 기계 연결 검사는 일반 contact force/gap·BCS 충분성·물리 응답의 합격이 아니다. 이 PR 당시 삭제 멤버의 명시 Drop과 element removed_cells writer/trial/UI는 미연결이었으며 N18 전체와 그룹별7/16/3은 그대로다. 관련 검사만 수행하고 전체 CI/solver 반복은 `[skip ci]`로 피했다.

<a id="shell-normal-progress"></a>

2026-11-04 N18 셸 반전은 [PR51](https://github.com/pikachu444/caelab-prep/pull/51)의 API `c469122d21ec337ed7c7a832b58bf7703d24f9a8`, 공용 UI `062018e070193a1ca29fbc7f7f9316f06ec4e8cb`, 잠금 표시 교정 `64c74c2d0703d9ab089fc2fa0e484e1fac9ca375`로 게시하고 main `9887a168a84e51d2777bf69174d892e568aa6ae7`에 정상 merge했다. 검토 head612bc38과 병합 tree `17092b5f2c2ffe627cf1153adb6b4e8d2994a1c2`는 동일하다. 기존 flip 후보와 node-merge의 native slot writer/trial을 재사용하며 새 문서·codec·WB 모델은 만들지 않았다. 실제 PART/속성/정식화·warped quad/품질·closed-profile·sealed CAS를 검사한다. 두께·저장 각도·좌표/ID/PART는 보존하고 연결 순서·면내 축을 바꾼다. 영향 집합은 stale로 남겨 명시 재연결 전까지 export를 막으며 조건 값을 자동 보정하지 않는다. 지원 TYPE7의 양면 접촉 역할/값 보존과 실제 접촉력 응답 확인을 구분한다.

기존 merge19, 새 API의 초기18통과/잘못된 token 설정1실패를 교정한 영향2통과, 추가 두-source 한Undo1통과는 별도 실행이다. Add/Remove 후 Qt22(8표현×두 입력16 포함)가 통과했고, 문서 변경 뒤 Remove 표시가 다시 켜지는 원 반례1red는 교정 후 원재현·정상 목록2green 및 원 비판자의 읽기 재확인으로 종결했다. 앞서 여러 pick이 목록을 교체하던 누락도 red1→누적/중복 제거·행 제거·source 보존으로 교정했다. 독립 후속 QA33과 마지막 표시 재확인4는 별도로 통과했으며 root/기존 baseline과 합산하지 않는다. 첫 QA의 정상 stale guard 관측 오류와 그림은 보존했다. 두 기존 SHELL 입력과 copied SH3N의 Undo/Redo·v6·같은 프로세스의 새 session 재열기·native parser 재읽기, stale/export 차단·identity reconnect를 구분했다. 새 프로세스 재열기나 실제 solver 결과가 아니다.

자료는 `C:/Users/pikac/.codex/visualizations/2026/11/04/shell-normal-review/qa-01`의 `report.json`(SHA256 `6a967c700859abeb91a74ddc41bbb752a54ea6690f00d0436bb977e46b317ce8`)·`stale-remove-recheck.json`(SHA256 `21e7ad4cb87aed0ed9305e24a4bcae6fe555d7894b720ee67a79c125cf9f8727`)에서 재열 수 있다. root와 QA가 780×600/540×420 그림을 직접 읽어 버튼·Type 열·검토·스크롤 접근을 확인했다. 그림/QA33의 UI는 `88c276db…` 시점이고 마지막 stamp 조건 교정 UI `29fc5fc7…`는 별도 재확인에 귀속한다. 전체 CI·solver 반복을 피한 `[skip ci]` head이며 관련 검사 파일은 향후 CI에 등록했다. 실제 Windows/VTK·frozen·원제품 비교와 나머지 P7b·N12/N13 및 그룹별7/16/3은 미완료로 유지한다.

PR46 최초 head `f5f37d4`의 CI41631351152는 새 실제 CAD3건·새 Qt 단계를 통과했지만, native preview가 비운 화면과 채운 화면에 같은 캐시 표식을 써 0/142 cell로 실패했다. 수정 `d3b7d76f764de637c9627d6247ba7691ae7deeda`는 기존 source preview처럼 identity 없는 빈 projection을 사용한다. 실제 unshown VTK 데이터의 0/138 red를 보존하고 138개 재구성을 확인했으며, 의도된 무문서 읽기 Action의 기존 허용 목록과 Qt 영향22건을 통과했다. 원 비판자가 수정·선택 격리를 읽기 재확인했고, 실제 Linux 렌더/pick은 수정 HEAD의 CI에서 별도로 확인한다. 이 데이터 검사는 Render/OS 실행이 아니다.

GI2 코드 `0d567fba238648ecd6ee2baccdd8cb82941361f2`의 실제 고정 A/B/C는 관통 후보1·외부 원통 후보0·blind 후보1(R1, 깊이3/2)을 첫 시도에 구분했다. A/B의 기존 XAO UUID/revision을 보존했고 새 자체 blind CAD 생성1·inspection3, 메시/solver/독립 SDK 재읽기0·4 native process rc0/회수다. 원래 GI1 자산은 실행 전후 불변, 새 자산은 생성 뒤 최초/최종 snapshot 불변이며 `phase37-geometry-inspection/gi2-actual-01`에 plan·입력 lock·원시 metadata·classifier와 해시를 보관한다. 공통 plan·실제 좌표 잔차·계산 floor·사각 wire의 원 지적은 수정 후 각각 원 지적자가 종결했다. 일반 shape/fillet·전체 공극 연결의 완료가 아닌 제한된 후보 판정이다.

공용 Qt 코드 `80a4c4d14092eee1c3ae770ce42b7c63df6775c5`는 8표현의 같은 Action/무문서 진입과 evidence 재열기·private wireframe 선택을 연결했다. Qt 영향14통과, 독립 실제 자료37확인과 caption delta1·원 허용오차/Escape 지적 재확인은 각각의 source에 귀속한다. 원 offscreen 환경은 font families0으로 tofu 그림7장을 보존했으며, child의 `QT_QPA_FONTDIR`만 지정한 추가4그림은 기존 QSS Segoe UI12px/font override0에서 가독성을 재확인했다. root도 대표 정상/제한창 그림을 직접 읽었다. 이 조건을 실제 Windows appearance/OS/VTK로 세지 않으며, 새 Linux/X11 실제 source→worker→render/pick 검사는 CI에 연결해 아직 결과를 기다린다. 기존 그룹별 잔여 7/16/3은 그대로다.

PR45는 head `9828783`의 [CI41619212860](https://github.com/pikachu444/caelab-prep/actions/runs/41619212860) 10 jobs·새 실제 criteria 통합2건 통과 후 main `4ac672d0`에 squash 병합됐다. 다음 geometry-only 코드 `3aba56b0f9785b4db19a9a352facf058e14d8231`은 mesh 없이 기존 capture/import/identity/worker와 AssetDigest를 재사용한다. 고정 through-hole plate와 같은 R1/H3 외부 원통의 실제 검사 각1회, 새 자체 음성 CAD 생성1회에서 축/반경/bbox·체적·면 수를 대조했다. source/captured/XAO/metadata·실행 소스 해시 불변, 3 native process rc0/회수 완료이며 `phase37-geometry-inspection/actual-pair-01/report.json`에 보관한다. 원 지적자의 reader 배열/빈 volume 경계 수정 재확인과 backend/실제 자료 읽기 검토는 완료했으며, 공유 import 영향132통과·실제 CI 추가2skip을 구분한다. Raw normal/volume sign/trim은 미확인이며 feature 분류는 0건이다. Through/blind hole·fillet 인식/시각화와 나머지 Phase3.7 요구는 진행 중으로 남긴다.

Phase 3.7은 main `31430e10`(PR44) 위 `codex/batch-mesher-feature-recognition`에서 진행한다. 첫 criteria/minimum 코드 e9282e20c9d864e30340d256079c93b6e8b981f는 [사용법](docs/usage.md#meshing-criteria)의 독립 JSON·SDK 입력 clamp·전체 선형 edge 감사이며 N18의 자동 cleanup 완료가 아니다. 실제 plate-with-hole/cylinder의 SDK 생성은 각각 1회, 전체 inventory 독립 읽기는 각각 1회였다. Lmin=.25에서 1,797/1,458 cell 중 point 10/2개를 명시 skip하고, 관측 최단 edge .693558/.674359, 미달·미지원·invalid 0을 확인했다. 원본/출력 hash는 불변이며 수집 근거는 `C:\Users\pikac\.codex\visualizations\2026\11\03\surface-autotet\phase37-minimum-size\report.json`과 `phase37-minimum-edge-audit\report.json`에 보존한다. STEP 정규화·저장 XAO 단위 충돌 P37-R1은 source 경로와 worker identity 대조로 수정하고 원 지적자가 종결했다. 영향 검사 153통과·실제 SDK 통합 2skip을 기록했으며 이번 수정에서 SDK/메시 생성은 0회다. 실제 두 입력의 통합검사는 CAD-worker CI에 연결했다. 기능 인식·ring/억제·batch·실제 cleanup, N12 OS/VTK와 그룹별 잔여 7/16/3은 그대로 남는다.

PR29 `89ef36b`는 정확한 head의 필수 CI 10개 job과 독립 검토 후 main `e929bcd`에 병합했다. push/PR 이벤트의 중복 실행은 별개 검사 수로 합산하지 않는다. N18의 Windows 입력·좌표/참조·저장 결과는 [기록](docs/native-windows-validation.md#node-move-20261102)에 한정한다.

| 관련 PR과 후속 | 기준 | 남은 범위 |
|---|---|---|
| [PR26](https://github.com/pikachu444/caelab-prep/pull/26) | `a136c0c08018968dfc1c8d590a4fb85da79e284e`, draft | N17·N23·N26 개발검증자료 보존. 제품 완성으로 세지 않음 |
| [PR27](https://github.com/pikachu444/caelab-prep/pull/27) | 제품·bundle `b0b06682f12c43e3d09fda9249f9f5d1bd3f1765`, 최종 검토 `674ffbc9f8af84b9762b16eba4eb5b893a5a89e8`, 병합 `35c97fa794d4c5c17cf7e5d1cd5043f012433152` | 제한 quad4 공통 API/GUI·원본 보호·Undo·저장·Starter 두 입력·최종 CI10 jobs/X11 preview 확인. 새 bundle 정적 delta와 이전 불변 worker 근거를 구분. Windows OS/VTK·frozen GUI·recipe 편집/재생성은 후속이며, hex는 N25의 제한 연결로 이어짐 |
| [PR28](https://github.com/pikachu444/caelab-prep/pull/28) | `f7da8572177e2506f2a0b0ea06dee50f297d805a`, draft | 일반 메시 연산 후보. PR29에 연결한 첫 이동과 나머지 연산을 구분 |
| [PR32](https://github.com/pikachu444/caelab-prep/pull/32) | 코드·로컬 후보 `b3a1c6a058a79fbe4af40dd2781f23d1f3c71ce4` | N13 설정 격리·분석 입력/고지 수집 구현. 새 frozen GUI·새 환경·OS/VTK·배포 조건 미확인 |
| [PR34](https://github.com/pikachu444/caelab-prep/pull/34) | 검토 `375fdee6b3a9346408675fde9d9c3317d9f70c91`, Git 통합 `fc98c25fa725859e64ff03adf4b4b9cebcbfb19c` | N25 제한 hex8 공통 연결. merge timeout 후 실제 Git 통합을 확인해 PR은 closed, metadata merged=false와 구분. Windows OS/VTK·frozen hex·전체 H-S/F4는 후속 |
| [PR35](https://github.com/pikachu444/caelab-prep/pull/35) | 최종 검토 `f6adc16b2c2a5d65bf94b314daf16dde4188c1e9`, 병합 `36d1e71c4847421611a2e228b7bd9cfa432fbd74`, API `64cdcc1`, GUI `22284aa`, 복구 안내 `6791da9` | N18 선택적 명시 멤버 검토. 독립 검토/4 Qt 흐름·CI10 jobs·실제 X11 그룹4건 통과. part 소유 변경과 나머지 일반 메시 연산은 미완료 |
| [PR36](https://github.com/pikachu444/caelab-prep/pull/36) | 코드 `618f4f3`, 검토 `4851df5a15c5d8a3e9c44c12c3c697bff943acbd`, 병합 `45aeb80255ebdf2a3b75107cea7b3c11fcd798aa` | 조용한 BEAM default-frame 전환 guard. 원 지적 재확인·[CI41532630456](https://github.com/pikachu444/caelab-prep/actions/runs/41532630456) 10jobs 통과. 전체 merge 기능으로 세지 않음 |
| [PR37](https://github.com/pikachu444/caelab-prep/pull/37) | API `e32b62d`, GUI `b7c5446`, 코드 검토 head `7fa8c0f5376a2913f7ef54b40cec740bcceffc04`; 보관처 `prep-node-merge-e32b62d` | 첫 native API/GUI·source/요소 의존성·stale 재연결·단일 이력. 코드 head CI10jobs·새 X11 merge4건·독립 시각 판정 통과. 최종 문서/통합 SHA는 acceptance와 PR에서 구분. PR37 당시 many-to-one은 후속이었고 다음 `17c35d2` 후보로 분리했다. 일부 layout·전체 N18은 미완료 |

과거 PR별 실행 수치·실패·재검토·당시 세션 제약은 [구현 이력](docs/history/implementation-history.md)에 있다. 과거 기록의 '현재/최신'은 당시 범위이며 새 실행 지시가 아니다.

## 작업을 이어갈 때

README → DESIGN의 R/T/G → 이 표 → 해당 기술 절과 코드를 읽는다. 실제 HEAD·dirty·환경을 위 코드 기준과 대조하고 해당 N 행의 첫 미완료 작업을 진행한다. 공통 파일의 편집자는 한 명으로 정하며 기존 작업을 보존한다. 원제품 접근이나 Windows 후속 확인을 기다리는 동안 독립 가능한 구현을 진행한다.

### 현재 → 다음 → 그다음 (2026-11-03 #19 기록, 이후 배정은 Gemini 총괄)

이하 표는6591670200 당시 인계 기록을 보존한다. 이후6592941640의 구체 배정으로 코어·런처 조사를 재개했으며, UI 작성 해제와 총괄 권한은 유지한다. 새 자율 개발 우선순위나 두 번째 JobManager를 만들지 않는다.

기존 [실행 계획 §1·§9](docs/execution-stages.md#9-p5--8제품별-동일-과업의-표현상호작용)은 G1-c의 실제 UI 연결 → G1-d의 필수 8방식 확대를 이미 요구했다. 새 요구나 계획 부재가 아니라, 기능 PR을 진행하는 동안 R2/R4의 실제 원제품 대조·메인 작업영역 전달을 미완료로 남긴 이행 부족을 수정한다. 현재의 N03–N10·N12 상태와 7/16/3행 분류는 그대로이며 단일 기능 PR의 통합으로 줄이지 않는다.

| 순서 | 작성·수정 범위 | 같은 사용자 행동·종료와 독립 확인 |
|---|---|---|
| 현재 보존점 | Prep root 단일 writer. `codex/reconnect-node-coalescence`, 제품 `17c35d2`, `mesh_relations/reconnection_review/source_models/mesh_target_text`와 관련 검사. | 원2링크→최종1집합의 opt-in 검토·단일 Undo·v6/재열기/native 출력. 원 지적자 2건 재확인 완료, 독립 API6/Qt3 통과. 코드·입출력을 보관하고 draft PR로 고정한다. 새 X11/CI는 대기 상태 그대로 회수하며 전체 N18 종료나 다른 미구현 연산을 이 다음 작업의 선행조건으로 두지 않는다. |
| 바로 다음: R2/R4·N03–N10 메인 화면 실제 수정 | 첫 제한 수정은 root 로컬 cd2cd24(parent d5aaa76)에 보존했다(reference tree natural font 높이, BeidPrep FORM 폭; 기본 native 진입은 미변경). 원 비판자의 실제 전후 그림에서 정상 행21→26px의 밀도 회귀 GUI-DENSITY-1과 기본 진입 누락 GUI-SCOPE-1이 열려 있어 그대로 채택할 수 없다. 이후 #19 Gemini6591517918/6591521995의 GUI 총괄·작성 보고와 실제 ui-overhaul worktree를 확인해 root는 겹치는 추가 GUI 작성을 해제했다(회신6591586257/6591650562). 최신 사용자 직접 지시 인계 [#19 6591670200](https://github.com/pikachu444/caelab-prep/issues/19#issuecomment-6591670200)에 따라 Gemini가 개발 전권 총괄이다. root도 공통 계약·문서·PR38의 추가 편집/통합 판단을 여기서 해제하고 현재 커밋·dirty·원 지적을 보존해 인계한다. 이후 작성/검토 배정과 순서는 Gemini에 맞추며 자동 재개·감독을 약속하지 않는다. 타 worktree와 진행 파일은 수정하지 않았다. | 같은 메시 import→트리/3D 선택→두 재료·단면 생성/편집/할당→잘못된 값·Cancel·Undo→연속 저장/재열기를 첫 장면으로 고정한다. 원제품의 메뉴·도구막대·트리·3D·속성/작업 패널과 명령/확정 수명을 대조해 공통 글꼴/크기 충돌·불필요한 빈 영역부터 실제 코드로 수정한다. Astra의 원제품/요구 비판과 기존 독립 Qt QA를 수정 뒤 다시 받는다. 조사는 구현 완료로 세지 않는다. |
| 그다음: 같은 원장면 재검토와 8방식 확대 | 같은 Document/provider/Action/Undo/storage를 소비하는 8 adapter/composition의 차이를 연결한다. 별도 문서 모델이나 전제품 단일 2열 즉시편집기로 바꾸지 않는다. | HyperMesh/PrePoMax/Naksha/Abaqus/COMSOL/midas NFX/MeshFree/BeidPrep 각각의 같은 행동·오류·취소·저장 출력과 화면을 원 비판자가 확인한다. DESIGN의 1920×1080/100%, 3840×2160/200%, 축소960×640 기준을 유지하고 Windows OS·DPI는 기존 operator의 후속 미확인으로 구분한다. 한 장면·두 표현·Linux/offscreen을 전체 R2/R4 또는 원제품 동등성으로 확대하지 않는다. |

출처 버전도 구분한다. Naksha 전체 이미지는 `products/naksha.json`의 **0.5.07**, library는 build 미표시다. BeidPrep은 [1.0.1 별도 실행](docs/beidprep-evaluation.md)과 `products/beidprep.json`의 **2.0 공개 페이지/build 미표시 이미지**가 다르며 2.0 실행·편집을 확인한 것으로 쓰지 않는다. 첫 제한 GUI 후보의 같은 입력/전후 그림·글꼴·실패/수정·미해결 지적은 로컬 `C:/Users/pikac/.codex/visualizations/2026/11/03/prep-reference-gui-cd2cd24/manifest.json`에 보존한다. source/offscreen·설치 글꼴 QA process-only·3D 비활성 장면이며 기본 native/G1 생성·할당 전체 또는 사용자 Windows 품질을 종결하지 않는다. 현재 사용자 창의 build/픽셀/DPI는 이 root가 아직 확인하지 않았다. 13pt 원인·70% 빈 영역·2배 밀도 같은 미측정 수치나 context menu 전면 부재를 수정 근거로 채택하지 않는다.

기능 작성자는 같은 N 행의 지원 범위와 사용법을 갱신한다. 통합 담당은 코드 SHA·입출력·실제 확인/미확인·검토/PR 근거와 그룹별 잔여 수를 대조한다. 개발검증자료의 작성·실행 주체를 밝히고 사용자 직접 시험으로 바꾸어 쓰지 않는다. 자료를 통합·삭제할 때는 고유 정보·재현 입력·필수 저작권 고지·기존 링크를 확인한다.

