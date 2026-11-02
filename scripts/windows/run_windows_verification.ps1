#Requires -Version 5.1
# CAELab Prep Windows 네이티브 검증 러너.
# Linux에서 작성되었으며 실제 Windows 네이티브 구동은 별도 후속 일괄 검증에서 확인한다.
# 이 러너는 권한 승격, 전역 ExecutionPolicy 변경, 원격 설치, 민감한 환경 값 수집을 하지 않는다.
# 모든 임시 파일과 삭제는 러너 작업 디렉터리(WorkDir) 안에 한정된다.

param(
  [string]$PrepSha = '531e02394694019511df2b38e3d3f7cb2140b254',
  [string]$WorkbenchSha = '865ee159c9bd1375d996a72eacf898484f1d96cb',
  [string]$PythonPath = 'python',
  [string]$PrepDir = '',
  [string]$WorkbenchDir = '',
  [string]$OutputDir = '',
  [string]$SolverPath = '',
  [string]$SolverArguments = '',
  [switch]$RunSolver,
  [double]$W3EndTime = 0.001,
  [double]$W3OutputInterval = 0.0001,
  [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'

$script:Checks = @()
$script:ActiveProcess = $null

if (-not $PrepDir) {
  $PrepDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
if (-not $OutputDir) {
  $OutputDir = Join-Path ([System.IO.Path]::GetTempPath()) ('caelab-windows-verification-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$script:WorkDir = Join-Path $OutputDir ('work-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $script:WorkDir | Out-Null

$script:LogFile = Join-Path $OutputDir 'runner.log'

function Write-Log {
  param([string]$Message)
  $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
  Write-Host $line
  Add-Content -Path $script:LogFile -Value $line -Encoding UTF8
}

function Format-Argument {
  param([string]$Value)
  if ($Value -and ($Value.Contains(' ') -or $Value.Contains('(') -or $Value.Contains(')'))) {
    return ('"{0}"' -f $Value)
  }
  return $Value
}

function Add-Check {
  param([string]$Id, [string]$Title)
  $check = [ordered]@{
    id = $Id
    title = $Title
    status = 'unexecuted'
    detail = ''
    evidence = @{}
  }
  $script:Checks += $check
  return $check
}

function Set-Check {
  param([string]$Id, [string]$Status = '', [string]$Detail = '', $Evidence = $null)
  for ($i = 0; $i -lt $script:Checks.Count; $i++) {
    if ($script:Checks[$i]['id'] -eq $Id) {
      if ($Status) { $script:Checks[$i]['status'] = $Status }
      if ($Detail) { $script:Checks[$i]['detail'] = $Detail }
      if ($Evidence) { $script:Checks[$i]['evidence'] = $Evidence }
      return
    }
  }
}

function Invoke-ProcessTreeCleanup {
  param([int]$ProcessId)
  # taskkill /T는 이 PID에서 뻗은 자식 트리만 정리한다. 이름 기반 프로세스 탐색은 하지 않는다.
  $output = (& taskkill /PID $ProcessId /T /F 2>&1 | Out-String)
  return @{
    performed = ($LASTEXITCODE -eq 0)
    detail = $output.Trim()
  }
}

function Invoke-ChildProcess {
  param(
    [string]$FilePath,
    [string]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$StdoutFile,
    [string]$StderrFile,
    [int]$TimeoutSeconds
  )
  $record = [ordered]@{
    file_path = $FilePath
    arguments = $ArgumentList
    working_directory = $WorkingDirectory
    exit_code = $null
    timed_out = $false
    tree_cleanup_performed = $false
    cleanup_detail = ''
    duration_seconds = $null
    stdout_tail = ''
    stderr_tail = ''
  }
  $watch = [System.Diagnostics.Stopwatch]::StartNew()
  $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
    -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru `
    -RedirectStandardOutput $StdoutFile -RedirectStandardError $StderrFile
  $script:ActiveProcess = $proc
  $exited = $proc.WaitForExit($TimeoutSeconds * 1000)
  if ($exited) {
    $record['exit_code'] = $proc.ExitCode
    $script:ActiveProcess = $null
  } else {
    $record['timed_out'] = $true
    $cleanup = Invoke-ProcessTreeCleanup -ProcessId $proc.Id
    $record['tree_cleanup_performed'] = $cleanup['performed']
    $record['cleanup_detail'] = $cleanup['detail']
    $proc.WaitForExit(5000) | Out-Null
    $script:ActiveProcess = $null
  }
  $watch.Stop()
  $record['duration_seconds'] = [math]::Round($watch.Elapsed.TotalSeconds, 2)
  if (Test-Path $StdoutFile) {
    $record['stdout_tail'] = ((Get-Content -Path $StdoutFile -Tail 40) -join "`n")
  }
  if (Test-Path $StderrFile) {
    $record['stderr_tail'] = ((Get-Content -Path $StderrFile -Tail 40) -join "`n")
  }
  return $record
}

$script:SavedPythonPath = $null
$script:SavedIOEncoding = $null

function Invoke-PrepPython {
  param(
    [string]$Arguments,
    [string]$WorkingDirectory,
    [int]$TimeoutSeconds = 300,
    [string]$Label
  )
  # Prep 저장소의 src를 직접 사용한다. 설치·수정은 하지 않는다.
  $script:SavedPythonPath = $env:PYTHONPATH
  $script:SavedIOEncoding = $env:PYTHONIOENCODING
  $env:PYTHONPATH = (Join-Path $PrepDir 'src')
  $env:PYTHONIOENCODING = 'utf-8'
  try {
    $stdoutFile = Join-Path $script:WorkDir ($Label + '.stdout.txt')
    $stderrFile = Join-Path $script:WorkDir ($Label + '.stderr.txt')
    return Invoke-ChildProcess -FilePath $PythonPath -ArgumentList $Arguments `
      -WorkingDirectory $WorkingDirectory -StdoutFile $stdoutFile -StderrFile $stderrFile `
      -TimeoutSeconds $TimeoutSeconds
  } finally {
    if ($null -ne $script:SavedPythonPath) { $env:PYTHONPATH = $script:SavedPythonPath }
    if ($null -ne $script:SavedIOEncoding) { $env:PYTHONIOENCODING = $script:SavedIOEncoding }
  }
}

function Get-JsonFromFile {
  param([string]$Path)
  $raw = Get-Content -Path $Path -Raw -Encoding UTF8
  return (ConvertFrom-Json $raw)
}

function Get-GitState {
  param([string]$Name, [string]$Dir, [string]$RequestedSha)
  $state = [ordered]@{
    name = $Name
    path = $Dir
    exists = $false
    full_sha = $null
    dirty = $false
    porcelain_entries = @()
    sha_matched = $false
    requested_sha = $RequestedSha
    requested_sha_resolved = $null
    git_error = ''
  }
  if (-not (Test-Path (Join-Path $Dir '.git'))) {
    $state['git_error'] = '.git directory not found under the given path'
    return $state
  }
  $state['exists'] = $true
  $head = (& git -C $Dir rev-parse HEAD 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) {
    $state['git_error'] = $head
    return $state
  }
  $state['full_sha'] = $head
  $porcelain = (& git -C $Dir status --porcelain 2>&1 | Out-String)
  $lines = @($porcelain -split "`r?`n" | ForEach-Object { $_.TrimEnd() } | Where-Object { $_ -ne '' })
  $state['porcelain_entries'] = $lines
  $state['dirty'] = ($lines.Count -gt 0)
  if ($RequestedSha) {
    # 와일드카드 비교 대신 hex commit 표현 검증 후 Git으로 해석한 full SHA와 정확 대조한다.
    if ($RequestedSha -notmatch '^[0-9a-fA-F]{7,40}$') {
      $state['git_error'] = 'requested SHA is not a valid hex commit expression'
      return $state
    }
    $resolved = (& git -C $Dir rev-parse --verify ("{0}^{{commit}}" -f $RequestedSha) 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
      $state['git_error'] = ('requested SHA did not resolve to a commit: ' + $resolved)
      return $state
    }
    $state['requested_sha_resolved'] = $resolved
    $state['sha_matched'] = ($resolved -ieq $head)
  }
  return $state
}

function New-RunnerProbeScript {
  param([string]$Name, [string]$Source)
  $path = Join-Path $script:WorkDir $Name
  # 프로브 코드는 ASCII만 사용한다(한글은 유니코드 이스케이프로 표기).
  [System.IO.File]::WriteAllText($path, $Source, (New-Object System.Text.ASCIIEncoding))
  return $path
}

# ---------------------------------------------------------------- 러너 본체

Write-Log ('Windows verification runner started. OutputDir=' + $OutputDir)
Add-Check 'W1-PRECHECK' '사전 점검(precheck): Prep 공용 NumericEdit 위젯 import와 Workbench 소비 근거 기록 — W1 완전 합격이 아니다'
Add-Check 'W2-PRECHECK' '사전 점검(precheck): RAD 모델 복사본의 두 프로세스 CLI 왕복과 원본 보존 — Workbench 독립 앱 전달 실측이 아니다'
Add-Check 'W3' 'Workbench JobManager의 Starter→Engine 2단계 실행·실패·취소·재실행 실측 (이 러너는 수행하지 않는다)'
Add-Check 'prep_export_solver_smoke' 'Prep export --engine 덱 생성과 (요청 시) 솔버 단일 스모크 구동 — Workbench W3 판정과 별개'
Add-Check 'T1' '탐색·선택·표시 관련 회귀 검사'
Add-Check 'T2' '재료·단면·파트 관련 회귀 검사'
Add-Check 'T3' '표·곡선·단위 관련 회귀 검사'
Add-Check 'T4' '집합·조건·케이스 관련 회귀 검사'
Add-Check 'T5' 'CAD·메시 연결 관련 회귀 검사'
Add-Check 'T6' '문서·솔버 입력 관련 회귀 검사'
Add-Check 'PATH-KO-SPACE' '한글·공백 포함 경로에서 파일 시스템과 Prep CLI 동작 확인'
Add-Check 'CORRUPT-ISOLATION' '손상된 .caeprep 문서가 구조화된 오류로 격리되는지 확인'
Add-Check 'IME' '한글/다국어 IME 실제 입력 조작'
Add-Check 'DPI' 'OS 모니터 배율 변경과 창 이동의 실제 조작'
Add-Check 'GPU' '실제 GPU 렌더 경로 조작과 framebuffer 검증'
Add-Check 'DOCKING' 'titlebar drag와 double click 도킹 실제 조작'

$script:FatalError = ''
$environment = [ordered]@{
  python_version = ''
  python_exit_code = $null
  pyside6_version = ''
  git_version = ''
  os = ''
  system_dpi = $null
}
$prepGit = $null
$workbenchGit = $null
$modelAsset = Join-Path $PrepDir 'scripts\evaluation\models\two_shell_plates_0000.rad'

try {
  # 환경 기록
  $pyVer = Invoke-ChildProcess -FilePath $PythonPath -ArgumentList '--version' `
    -WorkingDirectory $script:WorkDir `
    -StdoutFile (Join-Path $script:WorkDir 'py-version.stdout.txt') `
    -StderrFile (Join-Path $script:WorkDir 'py-version.stderr.txt') `
    -TimeoutSeconds 120
  $environment['python_exit_code'] = $pyVer['exit_code']
  $environment['python_version'] = ($pyVer['stdout_tail'] + ' ' + $pyVer['stderr_tail']).Trim()
  $environment['git_version'] = (& git --version 2>&1 | Out-String).Trim()
  try {
    $osObject = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $environment['os'] = ('{0} build {1}' -f $osObject.Caption, $osObject.BuildNumber)
  } catch {
    $environment['os'] = ('CIM unavailable: ' + $_.Exception.Message)
  }

  $pySide = Invoke-PrepPython -Arguments '-c "import PySide6; print(PySide6.__version__)"' `
    -WorkingDirectory $script:WorkDir -Label 'pyside-version' -TimeoutSeconds 120
  if ($pySide['exit_code'] -eq 0) {
    $environment['pyside6_version'] = $pySide['stdout_tail'].Trim()
  }

  $dpiSource = @'
import ctypes
import json

result = None
try:
    result = int(ctypes.windll.user32.GetDpiForSystem())
except Exception:
    result = None
print(json.dumps({"system_dpi": result}))
'@
  $dpiFile = New-RunnerProbeScript -Name 'dpi-probe.py' -Source $dpiSource
  $dpi = Invoke-PrepPython -Arguments ((Format-Argument $dpiFile)) `
    -WorkingDirectory $script:WorkDir -Label 'dpi-probe' -TimeoutSeconds 120
  if ($dpi['exit_code'] -eq 0 -and $dpi['stdout_tail'].Trim()) {
    try {
      $dpiJson = ConvertFrom-Json $dpi['stdout_tail'].Trim()
      $environment['system_dpi'] = $dpiJson.system_dpi
    } catch {
      Write-Log ('DPI probe output not parseable: ' + $dpi['stdout_tail'])
    }
  }

  # Git 상태: full commit SHA, dirty 여부, 요청 SHA와의 일치
  $prepGit = Get-GitState -Name 'prep' -Dir $PrepDir -RequestedSha $PrepSha
  if ($WorkbenchDir) {
    $workbenchGit = Get-GitState -Name 'workbench' -Dir $WorkbenchDir -RequestedSha $WorkbenchSha
  }
  Write-Log ('Prep git: full=' + $prepGit['full_sha'] + ' dirty=' + $prepGit['dirty'] + ' matched=' + $prepGit['sha_matched'])

  # ---------------------------------------------------------------- W1-PRECHECK
  $w1 = Invoke-PrepPython -Arguments '-c "from caelab_prep.ui.widgets.numeric import NumericEdit; print(NumericEdit.__name__)"' `
    -WorkingDirectory $script:WorkDir -Label 'w1-numeric' -TimeoutSeconds 120
  if ($environment['pyside6_version'] -eq '') {
    Set-Check -Id 'W1-PRECHECK' -Status 'unexecuted' `
      -Detail 'PySide6가 이 Python 환경에 없어 위젯 import 사전 점검을 실행하지 않았다. widgets 추가 의존성 설치 후 다시 실행하라.'
  } elseif ($w1['exit_code'] -eq 0) {
    $w1Evidence = $w1
    if ($WorkbenchDir) {
      $studyConfig = Join-Path $WorkbenchDir 'apps\workbench_qt\mdo_studio\study_config.py'
      if (Test-Path $studyConfig) {
        $studyContent = Get-Content -Path $studyConfig -Raw
        $w1Evidence['workbench_study_config'] = $studyConfig
        $w1Evidence['workbench_consumes_prep_numeric_edit'] = $studyContent.Contains('PrepNumericEdit')
      }
    }
    Set-Check -Id 'W1-PRECHECK' -Status 'passed' `
      -Detail '사전 점검(precheck) 통과: NumericEdit import 성공. 실제 Workbench 위젯 소비 경로는 아니므로 W1 완전 합격이 아니다.' `
      -Evidence $w1Evidence
  } else {
    Set-Check -Id 'W1-PRECHECK' -Status 'failed' -Detail 'NumericEdit import 사전 점검 실패. stderr를 evidence로 남긴다.' -Evidence $w1
  }
  Set-Check -Id 'W1' -Status 'unexecuted' `
    -Detail 'Workbench GUI 상의 실제 위젯 소비 및 도킹 실측은 이 러너가 수행하지 않는다. NumericEdit import 점검은 W1-PRECHECK로 분리 기록되며 실제 W1 합격으로 치환하지 않는다.'

  # ---------------------------------------------------------------- W2-PRECHECK
  $w2Dir = Join-Path $script:WorkDir 'w2'
  New-Item -ItemType Directory -Force -Path $w2Dir | Out-Null
  if (-not (Test-Path $modelAsset)) {
    Set-Check -Id 'W2-PRECHECK' -Status 'unexecuted' -Detail ('기준 모델 자산이 없어 왕복 사전 점검을 실행하지 않았다: ' + $modelAsset)
  } else {
    $modelCopy = Join-Path $w2Dir 'model_0000.rad'
    Copy-Item -Path $modelAsset -Destination $modelCopy
    $hashBefore = (Get-FileHash -Path $modelCopy -Algorithm SHA256).Hash
    $steps = @()
    $w2Ok = $true
    $w2Detail = ''
    $w2Evidence = @{ model_copy = $modelCopy; original_sha256 = $hashBefore; steps = $steps }

    $fields = Invoke-PrepPython -Arguments ('-m caelab_prep fields ' + (Format-Argument $modelCopy)) `
      -WorkingDirectory $w2Dir -Label 'w2-fields'
    $steps += ('fields exit=' + $fields['exit_code'])
    if ($fields['exit_code'] -ne 0) {
      $w2Ok = $false
      $w2Detail = 'fields 호출 실패'
    } else {
      $cards = Get-JsonFromFile -Path (Join-Path $script:WorkDir 'w2-fields.stdout.txt')
      $matHeader = ($cards | Where-Object { $_.keyword -like '/MAT/*' } | Select-Object -First 1).keyword
      if (-not $matHeader) {
        $w2Ok = $false
        $w2Detail = 'fields 결과에서 재료 카드를 찾지 못했다'
      } else {
        $editedPath = Join-Path $w2Dir 'edited.caeprep'
        $editArgs = '-m caelab_prep edit ' + (Format-Argument $modelCopy) + ' --card ' + (Format-Argument $matHeader) + ' --field young_modulus --value 205000 --output ' + (Format-Argument $editedPath)
        $edit = Invoke-PrepPython -Arguments $editArgs -WorkingDirectory $w2Dir -Label 'w2-edit'
        $steps += ('edit exit=' + $edit['exit_code'])
        if ($edit['exit_code'] -ne 0) {
          $w2Ok = $false
          $w2Detail = 'edit 호출 실패'
        } else {
          $exportedPath = Join-Path $w2Dir 'edited_0000.rad'
          $verifyArgs = '-m caelab_prep fields ' + (Format-Argument $editedPath) + ' --card ' + (Format-Argument $matHeader)
          $verify = Invoke-PrepPython -Arguments $verifyArgs -WorkingDirectory $w2Dir -Label 'w2-verify'
          $steps += ('verify exit=' + $verify['exit_code'])
          $exportArgs = '-m caelab_prep export ' + (Format-Argument $editedPath) + ' --output ' + (Format-Argument $exportedPath)
          $export = Invoke-PrepPython -Arguments $exportArgs -WorkingDirectory $w2Dir -Label 'w2-export'
          $steps += ('export exit=' + $export['exit_code'])
          $reopenArgs = '-m caelab_prep fields ' + (Format-Argument $exportedPath) + ' --card ' + (Format-Argument $matHeader)
          $reopen = Invoke-PrepPython -Arguments $reopenArgs -WorkingDirectory $w2Dir -Label 'w2-reopen'
          $steps += ('reopen exit=' + $reopen['exit_code'])

          $valueOk = $false
          $exportedOk = $false
          if (Test-Path $exportedPath) {
            $exportedText = Get-Content -Path $exportedPath -Raw
            $exportedOk = $exportedText.Contains('205000')
          }
          if ($verify['exit_code'] -eq 0 -and $reopen['exit_code'] -eq 0 -and $export['exit_code'] -eq 0) {
            $verifiedFields = Get-JsonFromFile -Path (Join-Path $script:WorkDir 'w2-verify.stdout.txt')
            $reopenedFields = Get-JsonFromFile -Path (Join-Path $script:WorkDir 'w2-reopen.stdout.txt')
            $verifiedValue = ($verifiedFields | Where-Object { $_.name -eq 'young_modulus' } | Select-Object -First 1).value
            $reopenedValue = ($reopenedFields | Where-Object { $_.name -eq 'young_modulus' } | Select-Object -First 1).value
            $valueOk = ([string]$verifiedValue -eq '205000') -and ([string]$reopenedValue -eq '205000')
          }
          $hashAfter = (Get-FileHash -Path $modelCopy -Algorithm SHA256).Hash
          $originalPreserved = ($hashBefore -eq $hashAfter)
          $w2Evidence['value_ok'] = $valueOk
          $w2Evidence['export_contains_new_value'] = $exportedOk
          $w2Evidence['original_preserved'] = $originalPreserved
          if (-not $valueOk -or -not $originalPreserved -or -not $exportedOk) {
            $w2Ok = $false
            $w2Detail = ('왕복 검증 실패: valueOk=' + $valueOk + ' exportOk=' + $exportedOk + ' originalPreserved=' + $originalPreserved)
          }
        }
      }
    }

    if ($w2Ok) {
      Set-Check -Id 'W2-PRECHECK' -Status 'passed' `
        -Detail ('사전 점검(precheck) 통과: 두 프로세스 CLI 왕복 성공. Workbench의 독립 앱 전달 실측이 아니므로 W2 완전 합격이 아니다. ' + ($steps -join '; ')) `
        -Evidence $w2Evidence
    } else {
      Set-Check -Id 'W2-PRECHECK' -Status 'failed' -Detail ('W2 사전 점검 실패: ' + $w2Detail + ' | ' + ($steps -join '; ')) -Evidence $w2Evidence
    }
  }
  Set-Check -Id 'W2' -Status 'unexecuted' `
    -Detail 'Workbench에서 독립 Prep 앱으로의 실제 문서 전달 및 대화형 GUI 실측은 이 러너가 수행하지 않는다. CLI 파일 왕복은 W2-PRECHECK로 분리 기록되며 실제 W2 합격으로 치환하지 않는다.'

  # ---------------------------------------------------------------- PATH-KO-SPACE
  $koDirName = [string][char]0xD55C + [string][char]0xAE00 + ' ' + [string][char]0xACF5 + [string][char]0xBC31 + ' ' + [string][char]0xACBD + [string][char]0xB85C
  $koDir = Join-Path $script:WorkDir $koDirName
  New-Item -ItemType Directory -Force -Path $koDir | Out-Null
  $pathProbeSource = @'
import hashlib
import pathlib
import sys

base = pathlib.Path(sys.argv[1])
target = base / "\uD55C\uAE00 \uACF5\uBC31 \uACBD\uB85C"
target.mkdir(parents=True, exist_ok=True)
payload = "\uAC00\uB098\uB2E4 ABC-123".encode("utf-8")
probe = target / "probe \uD55C\uAE00.txt"
probe.write_bytes(payload)
digest = hashlib.sha256(payload).hexdigest()
read_back = probe.read_bytes()
ok = hashlib.sha256(read_back).hexdigest() == digest and read_back == payload
print("PATH_PROBE_OK" if ok else "PATH_PROBE_FAILED")
'@
  $probeFile = New-RunnerProbeScript -Name 'path-probe.py' -Source $pathProbeSource
  # probe는 sys.argv[1]로 대상 경로를 받는다. 스크립트 경로와 대상 경로를 반드시 함께 전달한다.
  $pathProbeArgs = (Format-Argument $probeFile) + ' ' + (Format-Argument $script:WorkDir)
  $pathProbe = Invoke-PrepPython -Arguments $pathProbeArgs `
    -WorkingDirectory $script:WorkDir -Label 'path-probe' -TimeoutSeconds 120
  $newDoc = Join-Path $koDir 'roundtrip.caeprep'
  $newCliArgs = '-m caelab_prep new --name roundtrip --mass Mg --length mm --time s --output ' + (Format-Argument $newDoc)
  $newCli = Invoke-PrepPython -Arguments $newCliArgs -WorkingDirectory $koDir -Label 'path-new-cli'
  $fsOk = $pathProbe['stdout_tail'].Contains('PATH_PROBE_OK')
  if ($fsOk -and $newCli['exit_code'] -eq 0 -and (Test-Path $newDoc)) {
    Set-Check -Id 'PATH-KO-SPACE' -Status 'passed' -Detail '파일 시스템 왕복과 Prep CLI 생성이 모두 한글·공백 경로에서 통과했다.' `
      -Evidence @{ probe_dir = $koDir; cli_exit_code = $newCli['exit_code'] }
  } else {
    Set-Check -Id 'PATH-KO-SPACE' -Status 'failed' -Detail ('한글·공백 경로 시험 실패: fsOk=' + $fsOk + ' cliExit=' + $newCli['exit_code']) `
      -Evidence @{ probe = $pathProbe; cli = $newCli }
  }

  # ---------------------------------------------------------------- CORRUPT-ISOLATION
  $corruptFile = Join-Path $script:WorkDir 'corrupt.caeprep'
  $corruptSource = @'
import pathlib
import sys
import zipfile

target = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(target, "w") as archive:
    archive.writestr("manifest.json", "{ not valid json")
    archive.writestr("members/broken.rad", "BROKEN")
'@
  $corruptGenerator = New-RunnerProbeScript -Name 'corrupt-probe.py' -Source $corruptSource
  # probe는 sys.argv[1]로 대상 파일 경로를 받는다. 스크립트 경로와 대상 경로를 반드시 함께 전달한다.
  $makeCorruptArgs = (Format-Argument $corruptGenerator) + ' ' + (Format-Argument $corruptFile)
  $makeCorrupt = Invoke-PrepPython -Arguments $makeCorruptArgs `
    -WorkingDirectory $script:WorkDir -Label 'corrupt-make'
  if ($makeCorrupt['exit_code'] -ne 0 -or -not (Test-Path $corruptFile)) {
    Set-Check -Id 'CORRUPT-ISOLATION' -Status 'failed' `
      -Detail '손상 파일 생성 probe 실행 실패 또는 출력 파일 부재 (러너 내부 생성 오류).' `
      -Evidence $makeCorrupt
  } else {
    $inspectArgs = '-m caelab_prep inspect ' + (Format-Argument $corruptFile)
    $corruptHashBefore = (Get-FileHash -Path $corruptFile -Algorithm SHA256).Hash
    $inspect = Invoke-PrepPython -Arguments $inspectArgs -WorkingDirectory $script:WorkDir -Label 'corrupt-inspect'
    $corruptHashAfter = (Get-FileHash -Path $corruptFile -Algorithm SHA256).Hash
    $fileUnchanged = ($corruptHashBefore -eq $corruptHashAfter)
    $structuredError = $false
    $errorCode = ''
    if ($inspect['exit_code'] -ne 0) {
      try {
        $errorJson = Get-JsonFromFile -Path (Join-Path $script:WorkDir 'corrupt-inspect.stdout.txt')
        if ($null -ne $errorJson.error) {
          $structuredError = $true
          $errorCode = [string]$errorJson.error.code
        }
      } catch {
        $structuredError = $false
      }
    }
    $noTraceback = (-not $inspect['stderr_tail'].Contains('Traceback'))
    $expectedCode = 'invalid_project'
    # 합격 조건: 비영 종료 + 트레이스백 없음 + 구조화 오류 존재 + 예상 오류 코드 일치 + 대상 파일 불변
    if ($inspect['exit_code'] -ne 0 -and $noTraceback -and $structuredError -and ($errorCode -eq $expectedCode) -and $fileUnchanged) {
      Set-Check -Id 'CORRUPT-ISOLATION' -Status 'passed' `
        -Detail ('손상 문서가 예상된 구조화 오류(' + $expectedCode + ')로 격리됐고 대상 파일은 불변이다.') `
        -Evidence @{ structured_error = $structuredError; error_code = $errorCode; expected_code = $expectedCode; file_unchanged = $fileUnchanged; inspect = $inspect }
    } else {
      Set-Check -Id 'CORRUPT-ISOLATION' -Status 'failed' `
        -Detail ('손상 문서 격리 계약 미충족: exit=' + $inspect['exit_code'] + ' structuredError=' + $structuredError + ' errorCode=' + $errorCode + ' expected=' + $expectedCode + ' traceback=' + (-not $noTraceback) + ' fileUnchanged=' + $fileUnchanged) `
        -Evidence @{ inspect = $inspect }
    }
  }

  # ---------------------------------------------------------------- T1~T6
  $checkTitles = @{
    'T1' = '탐색·선택·표시'
    'T2' = '재료·단면·파트'
    'T3' = '표·곡선·단위'
    'T4' = '집합·조건·케이스'
    'T5' = 'CAD·메시 연결'
    'T6' = '문서·솔버 입력'
  }
  $testMap = @{
    'T1' = @('test_selection_menu.py', 'test_viewport_visibility.py', 'test_responsive_inspector.py', 'test_groups_ui.py', 'test_common_widgets.py')
    'T2' = @('test_modeling_commands.py', 'test_modeling_workflow.py', 'test_modeling_ui.py', 'test_property_presentations.py')
    'T3' = @('test_curve_csv.py', 'test_curve_plot_scale.py', 'test_curve_workflow.py', 'test_numeric_units.py', 'test_native_units_ui.py', 'test_rad_display_units.py')
    'T4' = @('test_collection_editors.py', 'test_condition_workflow.py', 'test_conditions_ui.py', 'test_analysis_cases.py', 'test_analysis_cases_ui.py', 'test_analysis_cases_solver.py', 'test_case_entrypoints.py')
    'T5' = @('test_external_mesh.py', 'test_external_mesh_native.py', 'test_external_mesh_sdk.py', 'test_external_mesh_solver.py', 'test_external_mesh_ui.py', 'test_mesh_candidates.py', 'test_mesh_adoption.py', 'test_mesh_workflow_ui.py', 'test_gmsh_adapter.py')
    'T6' = @('test_document_core.py', 'test_project_roundtrip.py', 'test_solver_generation.py', 'test_cli_workflow.py', 'test_radioss_editing.py', 'test_radioss_modeling.py', 'test_radioss_defaults.py')
  }
  foreach ($tId in @('T1', 'T2', 'T3', 'T4', 'T5', 'T6')) {
    $testsRoot = Join-Path $PrepDir 'tests'
    $existing = @($testMap[$tId] | Where-Object { Test-Path (Join-Path $testsRoot $_) })
    $missing = @($testMap[$tId] | Where-Object { -not (Test-Path (Join-Path $testsRoot $_)) })
    if ($existing.Count -eq 0) {
      Set-Check -Id $tId -Status 'unexecuted' -Detail ('저장소 tests/에서 매핑된 검사 파일을 찾지 못했다: ' + $checkTitles[$tId])
      continue
    }
    if ($missing.Count -gt 0) {
      # 없는 파일을 조용히 제외하지 않는다. 누락을 기록하고 미실행으로 남긴다.
      Set-Check -Id $tId -Status 'unexecuted' -Detail ('매핑된 검사 파일 일부가 누락되어 실행하지 않았다: ' + ($missing -join ', '))
      continue
    }
    $relative = ($existing | ForEach-Object { 'tests/' + $_ }) -join ' '
    $junitPath = Join-Path $script:WorkDir ($tId.ToLower() + '-junit.xml')
    $pytestArgs = '-m pytest -q ' + $relative + ' --junitxml=' + (Format-Argument $junitPath)
    $pytest = Invoke-PrepPython -Arguments $pytestArgs -WorkingDirectory $PrepDir -TimeoutSeconds $TimeoutSeconds -Label ($tId.ToLower() + '-pytest')
    if ($pytest['stderr_tail'].Contains('No module named pytest')) {
      Set-Check -Id $tId -Status 'unexecuted' -Detail '이 Python 환경에 pytest가 없어 실행하지 않았다. dev 의존성 설치 후 다시 실행하라.' -Evidence $pytest
      continue
    }
    $counts = @{ tests = 0; failures = 0; errors = 0; skipped = 0 }
    $junitReadable = $false
    if (Test-Path $junitPath) {
      try {
        $junitXml = [xml](Get-Content -Path $junitPath -Raw)
        $suites = @($junitXml.testsuites.testsuite)
        if ($suites.Count -eq 0 -and $junitXml.testsuite) { $suites = @($junitXml.testsuite) }
        $suites = @($suites | Where-Object { $_ -ne $null })
        if ($suites.Count -gt 0) {
          foreach ($suite in $suites) {
            $counts['tests'] += [int]$suite.tests
            $counts['failures'] += [int]$suite.failures
            $counts['errors'] += [int]$suite.errors
            $counts['skipped'] += [int]$suite.skipped
          }
          $junitReadable = $true
        }
      } catch {
        $junitReadable = $false
      }
    }
    $pytest['junit_xml'] = $junitPath
    $pytest['junit_readable'] = $junitReadable
    $pytest['junit_counts'] = $counts
    if (-not $junitReadable) {
      Set-Check -Id $tId -Status 'failed' -Detail 'JUnit 결과를 읽을 수 없어 실제 실행 수를 확인하지 못했다. passed로 기록하지 않는다.' -Evidence $pytest
      continue
    }
    if ($counts['tests'] -eq 0) {
      Set-Check -Id $tId -Status 'unexecuted' -Detail '수집된 검사가 0건이다. pytest exit 0과 무관하게 미실행으로 기록한다.' -Evidence $pytest
      continue
    }
    if ($pytest['exit_code'] -ne 0 -or $counts['failures'] -gt 0 -or $counts['errors'] -gt 0) {
      Set-Check -Id $tId -Status 'failed' -Detail ($checkTitles[$tId] + ' 관련 pytest 실패(exit=' + $pytest['exit_code'] + ', failures=' + $counts['failures'] + ', errors=' + $counts['errors'] + ').') -Evidence $pytest
      continue
    }
    if ($counts['skipped'] -gt 0) {
      Set-Check -Id $tId -Status 'partial' -Detail ($checkTitles[$tId] + ': ' + $counts['tests'] + '건 중 ' + $counts['skipped'] + '건 skip. 전부 실행된 통과가 아니므로 partial로 기록한다.') -Evidence $pytest
      continue
    }
    Set-Check -Id $tId -Status 'passed' -Detail ($checkTitles[$tId] + ' 관련 pytest 통과(' + $counts['tests'] + '건, skip 0).') -Evidence $pytest
  }

  # ---------------------------------------------------------------- W3 (Workbench 소유 경로) 와 prep 솔버 스모크 분리
  if (-not $SolverPath -or -not $WorkbenchDir) {
    Set-Check -Id 'prep_export_solver_smoke' -Status 'unexecuted' `
      -Detail 'SolverPath 또는 WorkbenchDir 인수가 없어 prep-export/솔버 스모크를 실행하지 않았다. 최종 일괄 검증 때 인수를 고정해 제공하라.'
  } elseif (-not (Test-Path $SolverPath)) {
    Set-Check -Id 'prep_export_solver_smoke' -Status 'failed' -Detail ('SolverPath가 존재하지 않는다: ' + $SolverPath)
  } elseif (-not (Test-Path $modelAsset)) {
    Set-Check -Id 'prep_export_solver_smoke' -Status 'unexecuted' -Detail ('기준 모델 자산이 없어 덱 생성을 실행하지 않았다: ' + $modelAsset)
  } else {
    $w3Dir = Join-Path $script:WorkDir 'w3'
    New-Item -ItemType Directory -Force -Path $w3Dir | Out-Null
    $w3Model = Join-Path $w3Dir 'model_0000.rad'
    Copy-Item -Path $modelAsset -Destination $w3Model
    $solverHash = (Get-FileHash -Path $SolverPath -Algorithm SHA256).Hash
    $w3Evidence = @{ solver_sha256 = $solverHash }
    $w3Status = 'unexecuted'
    $w3Detail = ''

    $endTimeText = [string]$W3EndTime
    $intervalText = [string]$W3OutputInterval
    $editArgs = '-m caelab_prep edit ' + (Format-Argument $w3Model) + ' --card /MAT/PLAS_TAB/1 --field young_modulus --value 205000 --output ' + (Format-Argument (Join-Path $w3Dir 'w3.caeprep'))
    $edit = Invoke-PrepPython -Arguments $editArgs -WorkingDirectory $w3Dir -Label 'w3-edit'
    $starterPath = Join-Path $w3Dir 'starter_0000.rad'
    $deckExport = $null
    if ($edit['exit_code'] -eq 0) {
      # 현재 CLI 계약: export --engine은 --end-time과 --output-interval이 필수다.
      $exportArgs = '-m caelab_prep export ' + (Format-Argument (Join-Path $w3Dir 'w3.caeprep')) + ' --engine --end-time ' + $endTimeText + ' --output-interval ' + $intervalText + ' --output ' + (Format-Argument $starterPath)
      $deckExport = Invoke-PrepPython -Arguments $exportArgs -WorkingDirectory $w3Dir -Label 'w3-export'
      $w3Evidence['deck_export_exit_code'] = $deckExport['exit_code']
    }
    if (-not $deckExport -or $deckExport['exit_code'] -ne 0 -or -not (Test-Path $starterPath)) {
      $w3Status = 'failed'
      $w3Detail = 'Starter/Engine 덱 생성에 실패했다.'
    } elseif (-not $RunSolver) {
      $w3Status = 'partial'
      $w3Detail = '덱 생성은 통과했고, 솔버 스모크 구동은 RunSolver 스위치가 없어 미실행으로 남긴다.'
    } else {
      $solverArguments = $SolverArguments -replace '\{deck\}', $starterPath
      $solverRun = Invoke-ChildProcess -FilePath $SolverPath -ArgumentList $solverArguments `
        -WorkingDirectory $w3Dir `
        -StdoutFile (Join-Path $script:WorkDir 'w3-solver.stdout.txt') `
        -StderrFile (Join-Path $script:WorkDir 'w3-solver.stderr.txt') `
        -TimeoutSeconds $TimeoutSeconds
      $w3Evidence['solver_run'] = $solverRun
      if ($solverRun['timed_out']) {
        $w3Status = 'failed'
        $w3Detail = '솔버 스모크가 시간을 초과해 프로세스 트리를 정리했다.'
      } elseif ($solverRun['exit_code'] -eq 0) {
        $w3Status = 'passed'
        $w3Detail = '덱 생성과 솔버 단일 스모크가 통과했다. 이는 Workbench W3 판정이 아니다.'
      } else {
        $w3Status = 'failed'
        $w3Detail = ('솔버 스모크가 실패했다: exit=' + $solverRun['exit_code'])
      }
    }
    Set-Check -Id 'prep_export_solver_smoke' -Status $w3Status -Detail $w3Detail -Evidence $w3Evidence
  }

  # Workbench W3의 실제 판정 경로(JobManager Starter→Engine 2단계, 실패·취소·재실행)는
  # 이 러너가 수행하지 않는다. 후속 일괄 검증에서 실제 WB 경로로 수행할 때까지 미실행으로 남는다.
  Set-Check -Id 'W3' -Status 'unexecuted' `
    -Detail 'Workbench JobManager의 Starter→Engine 2단계 실행·실패·취소·재실행 실측은 이 러너가 수행하지 않는다. Prep 덱 생성·솔버 스모크는 별도 항목(prep_export_solver_smoke)으로 기록되며 W3 합격으로 세지 않는다.'
} catch {
  $script:FatalError = ('runner aborted: ' + $_.Exception.Message + ' @ ' + $_.InvocationInfo.PositionMessage)
  Write-Log $script:FatalError
}

# ---------------------------------------------------------------- 미조작 항목 (정직한 unexecuted 기록)
Set-Check -Id 'IME' -Status 'unexecuted' -Detail '이 러너는 한글/다국어 IME 조작을 수행하지 않는다. 실제 입력기 조작은 후속 일괄 검증에서 사람 또는 데스크톱 자동화가 별도로 수행한다.'
Set-Check -Id 'DPI' -Status 'unexecuted' -Detail 'OS 모니터 배율 변경·모니터 이동은 수행하지 않았다. 시스템 DPI 읽기만 environment.system_dpi에 기록했다.'
Set-Check -Id 'GPU' -Status 'unexecuted' -Detail '실제 GPU 렌더 경로 조작과 framebuffer 검증은 수행하지 않았다.'
Set-Check -Id 'DOCKING' -Status 'unexecuted' -Detail 'titlebar drag와 double click 도킹 실제 조작은 수행하지 않았다.'

# ---------------------------------------------------------------- 매니페스트 작성
if ($prepGit -eq $null) {
  $prepGit = Get-GitState -Name 'prep' -Dir $PrepDir -RequestedSha $PrepSha
}

$failedChecks = @($script:Checks | Where-Object { $_['status'] -eq 'failed' })
$unexecutedChecks = @($script:Checks | Where-Object { $_['status'] -eq 'unexecuted' })
$partialChecks = @($script:Checks | Where-Object { $_['status'] -eq 'partial' })

$reposOk = $prepGit['sha_matched'] -and (-not $prepGit['dirty']) -and $prepGit['full_sha']
if ($workbenchGit) {
  $reposOk = $reposOk -and $workbenchGit['sha_matched'] -and (-not $workbenchGit['dirty'])
}

if ((-not $reposOk) -or ($failedChecks.Count -gt 0) -or $script:FatalError) {
  $overallStatus = 'failed'
} elseif (($unexecutedChecks.Count -gt 0) -or ($partialChecks.Count -gt 0)) {
  $overallStatus = 'partial'
} else {
  $overallStatus = 'success'
}

$notes = @(
  '이 러너는 Linux에서 작성되었고 구조적 정적 검사를 통과했다. 실제 Windows 네이티브 구동은 후속 일괄 검증에서 확인한다.',
  'IME/DPI/GPU/도킹의 실제 조작은 수행하지 않으며 unexecuted로 기록된다.',
  '파일 삭제는 러너 작업 디렉터리 안에 한정되며 사용자 모델과 설치 폴더는 보존된다.',
  '요청 SHA와 실제 full commit SHA가 다르거나 작업 복사본이 dirty면 성공으로 기록하지 않는다.',
  '이 러너는 권한 승격, 전역 ExecutionPolicy 변경, 원격 설치, 민감한 환경 값 수집을 하지 않는다.'
)
if ($script:FatalError) {
  $notes += $script:FatalError
}

$manifest = [ordered]@{
  manifest_version = 1
  runner = [ordered]@{
    script = 'run_windows_verification.ps1'
    created_utc = (Get-Date).ToUniversalTime().ToString('o')
    created_local = (Get-Date).ToString('o')
    ps_version = $PSVersionTable.PSVersion.ToString()
    os = $environment['os']
    git_version = $environment['git_version']
  }
  requested = [ordered]@{
    prep_sha = $PrepSha
    workbench_sha = $WorkbenchSha
    python_path = $PythonPath
    prep_dir = $PrepDir
    workbench_dir = $WorkbenchDir
    output_dir = $OutputDir
    solver_path = $SolverPath
    run_solver = [bool]$RunSolver
    timeout_seconds = $TimeoutSeconds
  }
  environment = $environment
  repos = [ordered]@{
    prep = $prepGit
    workbench = $workbenchGit
  }
  paths = [ordered]@{
    output_dir = $OutputDir
    work_dir = $script:WorkDir
    log_file = $script:LogFile
    cleanup_scope = 'runner work directory only'
  }
  interactive_tasks_coverage = [ordered]@{
    scope = 'DESIGN.md 대화형 GUI 및 사용자 과업 (CLI 사전점검 및 pytest 스위트와 분리)'
    status = 'unexecuted'
    tasks = [ordered]@{
      W1 = 'unexecuted'
      W2 = 'unexecuted'
      W3 = 'unexecuted'
      T1 = 'unexecuted'
      T2 = 'unexecuted'
      T3 = 'unexecuted'
      T4 = 'unexecuted'
      T5 = 'unexecuted'
      T6 = 'unexecuted'
    }
    note = 'T1~T6의 pytest 실행 결과는 코드 레벨 단위 검증이며, 실제 사용자 대화형 과업 실측은 후속 일괄 검증 단계에서 수행된다.'
  }
  checks = $script:Checks
  overall_status = $overallStatus
  notes = $notes
}

$manifestPath = Join-Path $OutputDir 'verification_manifest.json'
$manifestJson = ConvertTo-Json -InputObject $manifest -Depth 8
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, (New-Object System.Text.UTF8Encoding($false)))
Write-Log ('Manifest written: ' + $manifestPath)
Write-Log ('Overall status: ' + $overallStatus)

if ($overallStatus -eq 'success') {
  exit 0
} elseif ($overallStatus -eq 'partial') {
  exit 2
} else {
  exit 1
}
