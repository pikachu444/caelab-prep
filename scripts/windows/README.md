# scripts/windows — Windows 네이티브 검증 러너

`caelab-prep`과 `caelab-workbench`의 합의된 커밋 쌍을 Windows 네이티브 환경에서 실측 검증하기 위한
PowerShell 러너와 매니페스트 스키마다. Linux 환경에서 작성되었고, 이 폴더의 단위 검사(`test_windows_runner.py`)
로 구조를 확인했다. **실제 Windows 네이티브 구동은 별도 후속 일괄 검증에서 수행한다.**

## 구성 파일

| 파일 | 역할 |
|---|---|
| `run_windows_verification.ps1` | 검증 러너 본체. 환경·Git 상태·W1~W3·T1~T6·경로·손상 파일 항목을 수집해 매니페스트를 남긴다. |
| `verification_schema.json` | 러너가 출력하는 `verification_manifest.json`의 JSON Schema(2020-12). |
| `test_windows_runner.py` | Linux에서 실행하는 구조 단위 검사. `python -m pytest scripts/windows/test_windows_runner.py` |
| `README.md` | 이 문서. |

## 실행 방법 (Windows 네이티브 세션)

PowerShell 5.1 이상, 기존에 설치된 Python 3.11+와 git만 사용한다. 러너는 아무것도 설치하지 않는다.

```powershell
# 프로세스 범위 ExecutionPolicy 해제만 사용한다. 전역 정책은 바꾸지 않는다.
powershell -ExecutionPolicy Bypass -File scripts\windows\run_windows_verification.ps1 ^
  -PrepDir C:\work\caelab-prep `
  -WorkbenchDir C:\work\caelab-workbench `
  -PythonPath C:\Python313\python.exe `
  -OutputDir C:\Temp\caelab-verification
```

최종 일괄 검증 때는 합의된 SHA 쌍과 솔버 경로를 명시한다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\run_windows_verification.ps1 `
  -PrepSha 531e02394694019511df2b38e3d3f7cb2140b254 `
  -WorkbenchSha 865ee159c9bd1375d996a72eacf898484f1d96cb `
  -PrepDir C:\work\caelab-prep `
  -WorkbenchDir C:\work\caelab-workbench `
  -PythonPath C:\Python313\python.exe `
  -SolverPath C:\openradioss\starter.exe `
  -SolverArguments '-i {deck} -np 4' `
  -RunSolver `
  -OutputDir C:\Temp\caelab-verification
```

## 파라미터

| 파라미터 | 기본값 | 의미 |
|---|---|---|
| `-PrepSha` | `531e02394694019511df2b38e3d3f7cb2140b254` | 기준 Prep 커밋(접두어 허용). full SHA와 비교된다. |
| `-WorkbenchSha` | `865ee159c9bd1375d996a72eacf898484f1d96cb` | 기준 Workbench 커밋. `-WorkbenchDir`를 줄 때만 비교한다. |
| `-PythonPath` | `python` | 검증에 사용할 네이티브 Python 실행 파일. |
| `-PrepDir` | 스크립트 기준 저장소 루트 | Prep 작업 복사본 경로. |
| `-WorkbenchDir` | (빈 값) | Workbench 작업 복사본 경로. W1 상세 기록과 W3에 사용. |
| `-OutputDir` | `%TEMP%\caelab-windows-verification-<시각>` | 매니페스트·로그·작업 디렉터리가 만들어지는 곳. |
| `-SolverPath` | (빈 값) | 실제 솔버 실행 파일(W3). 주어지면 SHA256을 기록한다. |
| `-SolverArguments` | (빈 값) | 솔버 인수. `{deck}` 자리에 Starter 덱 경로가 들어간다. |
| `-RunSolver` | 스위치 | 실제 솔버 구동을 수행한다. 없으면 W3의 솔버 구동은 `unexecuted`로 남는다. |
| `-TimeoutSeconds` | `1800` | pytest·솔버 등 장시간 자식 프로세스의 제한 시간. |

## 수집하는 것

- **Git 상태**: `git rev-parse HEAD`(40자 full SHA), `git status --porcelain`의 dirty 여부, 요청 SHA와의
  일치(`sha_matched`). SHA 불일치·dirty는 전체 결과를 `failed`로 만들고 성공으로 기록하지 않는다.
- **환경**: Python 버전, PySide6 버전, git 버전, OS, 시스템 DPI(읽기만 수행).
- **W1**: Prep 패키지의 공용 `NumericEdit` 위젯 import. Workbench의 `study_config.py`가
  `PrepNumericEdit`을 소비하는지도 함께 기록한다.
- **W2**: 기준 모델(`scripts/evaluation/models/two_shell_plates_0000.rad`)의 복사본을 두 프로세스 CLI로
  `fields → edit(young_modulus 205000) → fields → export → 재조회` 왕복시키고, 원본 복사본의 SHA256 불변을 확인한다.
- **W3**: Prep `export --engine`으로 Starter/Engine 입력 덱을 만들고, `-RunSolver`가 주어지면 실제 솔버를
  `{deck}`에 덱을 넣어 구동한다(시간 초과 시 프로세스 트리 정리).
- **T1~T6**: DESIGN.md의 제품 목표에 대응하는 `tests/` 파일 묶음을 pytest로 구분 실행한다.
- **PATH-KO-SPACE**: 한글·공백 경로에서 파일 시스템 해시 왕복과 Prep CLI `new` 생성을 확인한다.
- **CORRUPT-ISOLATION**: 손상된 `.caeprep`(유효하지 않은 manifest.json을 가진 ZIP)이 미처리 예외가 아니라
  구조화된 오류로 격리되는지 확인한다.
- **결과**: `verification_manifest.json`(`verification_schema.json` 계약)과 `runner.log`.

## 정직하게 unexecuted로 남기는 것

이 러너는 다음을 수행하지 않으며, 매니페스트에 `unexecuted`로 기록한다. 자동 검사 통과로 대체하지 않는다.

- **IME**: 한글/다국어 입력기의 실제 조작
- **DPI**: OS 모니터 배율 변경, 모니터 간 창 이동
- **GPU**: 실제 GPU 렌더 경로 조작과 framebuffer 검증
- **DOCKING**: titlebar drag / double click 도킹의 실제 조작

## 절대 하지 않는 것

- 권한 승격(`RunAs`)이나 관리자 권한 요구
- 전역 ExecutionPolicy 변경 (프로세스 범위 `-ExecutionPolicy Bypass`만 사용)
- 설치(pip, 모듈, 원격 다운로드 포함), 레지스트리·방화벽·예약 작업 변경
- 민감한 환경 값(자격 증명·키·세션 값)의 수집이나 출력
- 러너 작업 디렉터리 밖의 파일 삭제 — 사용자 모델과 설치 폴더는 항상 보존된다

## 종료 코드

| 코드 | 의미 |
|---|---|
| `0` | `success` — 모든 검사 실행 후 통과 |
| `2` | `partial` — 실패는 없으나 `unexecuted` 항목이 있다 |
| `1` | `failed` — 실패한 검사, SHA 불일치·dirty, 또는 러너 중단 |

## 검증 상태 (이 PR 시점)

- Linux에서 구조적 정적 검사(`test_windows_runner.py`) 통과: 존재·기본값·균형·금지 동작 부재·스키마 계약.
- pwsh 파서가 있는 환경에서는 `test_pwsh_parser_check_when_available`이 실제 파싱을 수행한다.
  이 PR 작성 환경(Linux 컨테이너)에는 pwsh가 없어 구조 검사로 대체했으며, 실제 PowerShell 문법 확인은
  Windows 일괄 검증 단계에서 다시 확인한다.
- **Windows 네이티브 실제 구동은 미실시**다. 이는 이 PR의 결함이 아니라 합의된 후속 일괄 검증 항목이다.
