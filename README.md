# CAELab Prep

여러 CAE 프로그램에서 재사용할 **공용 개발 자산과 기반**을 개발합니다. 문서·명령·선택·Undo·저장, 단위 입력과 공학 위젯, 디자인 자산·앱 셸·실행형 갤러리를 함께 관리합니다.

첫 적용 앱은 **OpenRadioss / OpenCourant용 독립 데스크톱 전처리기**입니다. RAD를 열어 모델과 조건을 편집하고 `.caeprep` 작업문서를 저장하거나 Starter/Engine 입력을 내보냅니다. CAD 원본은 FreeCAD 같은 CAD 도구가 소유하며, Workbench에서 시작한 솔버 실행과 결과 관리는 [CAELab Workbench](https://github.com/pikachu444/caelab-workbench)가 담당합니다.

## 현재 사용할 수 있는 기능

| 작업 | 지원 범위 |
|---|---|
| RAD 편집 | INCLUDE 원문 보존, LAW1 재료·shell/solid 단면·PART 관계의 지원 필드 생성·수정 |
| 조건과 케이스 | 곡선, 집합, BCS, CLOAD, INIVEL/TRA, 제한된 INTER/TYPE7, 영속 해석 케이스와 시간·출력 설정 |
| CAD·메시 | Gmsh worker의 tri3/tet4 후보 검토·채택, MSH 2.2/4.1 ASCII 가져오기, 지원 조건 안의 준비된 메시 교체·대상 재연결 |
| 문서 | Undo/Redo, `.caeprep` 저장·재열기, RAD 및 Starter/Engine 내보내기 |
| 공용 GUI | 같은 문서·명령을 사용하는 8개 프로그램별 표현, 단위 숫자·벡터·표·곡선 입력, 재료/곡선 갤러리와 부품 카탈로그 |
| 자동화 | 독립 CLI, 열린 GUI에 접속하는 live 제어와 선택 설치 MCP adapter |

이 작업 브랜치에는 **절대좌표 절점 이동의 첫 연결**도 있습니다. 요소 품질과 영향 대상을 미리 검토하고 한 Undo로 적용합니다. 영향 집합을 명시적으로 재검토하기 전에는 native 출력을 막습니다. 다중 자원 대상 귀속과 하중 preview 정보에 검토 지적이 남아 있으므로 일반 메시 편집 완료본으로 취급하지 않습니다.

전체 Radioss 카드, 모든 요소·재료법칙, 일반 재메시의 자동 조건 복구, 임의 all-hex·중립면 생성과 Windows 설치형 배포는 지원 완료 범위가 아닙니다. 8개 표현의 존재는 원제품 전체 기능·품질과의 동등성 검증을 뜻하지 않습니다. 선택적 SolidCraft 준비 adapter는 외부 CAD를 실행하지 않으며 실제 design→STEP 생성 관계는 미확인입니다.

## Windows에서 시작하기

Python 3.11 이상과 Git을 설치한 뒤 저장소를 엽니다. PowerShell에서 실행합니다. 기존 가상환경이 있다면 새로 만들지 말고 [설치 가이드](docs/usage.md#install-windows)에 따라 환경을 선택하세요.

```powershell
git clone https://github.com/pikachu444/caelab-prep.git
cd caelab-prep
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[gui,cad]"
.\.venv\Scripts\caelab-prep.exe gui
```

처음에는 **File → Open Radioss deck…**으로 RAD를 열거나 **File → New model…**에서 명시적인 단위를 선택합니다. **Save project**는 편집 원본 `.caeprep`를 저장합니다. 솔버 입력은 별도의 **Export Radioss deck…** 또는 **Export Starter and Engine…**으로 작성합니다. Prep 설치에 솔버 EXE는 포함되지 않으며 덱을 열거나 편집하는 데 솔버 설치는 필요하지 않습니다.

## 사용 안내

- [설치·Windows 실행·편집·저장·CLI·문제 해결](docs/usage.md)
- [열린 GUI의 live 제어](docs/live-control.md), [MCP 클라이언트 연결](docs/mcp-client.md)
- [8개 프로그램별 표현의 근거와 차이](docs/ui-reference-variants.md)
- [Windows 확인 범위와 실행 기록](docs/native-windows-validation.md)
- [외부 라이브러리와 배포 조건](THIRD_PARTY.md)

## 개발 자료

[제품 목표](DESIGN.md#delivery-goals), [현재 코드 구조](ARCHITECTURE.md), [남은 작업과 완료 기준](docs/execution-stages.md#remaining-work), [Workbench 소비자 경계](docs/workbench-reuse-plan.md)를 따릅니다. 공용 자산과 갤러리는 정식 개발 산출물이며 다른 제품이 생길 때까지 개발을 미루지 않습니다.

[공용 기반 실행 계획](docs/shared-cae-foundation-plan.md), [GUI 비교 자료](docs/benchmarks/2026-10-30/README.md), [솔버 입력 자산](docs/solver-input-assets/2026-10-30/README.md), [메셔 실증 범위](docs/mesher-feasibility-roadmap.md)는 개발 근거입니다. 사용자 설치·실행 절차는 위 사용 가이드를 이용하세요.
