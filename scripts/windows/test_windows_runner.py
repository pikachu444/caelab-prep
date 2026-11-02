"""Linux에서 실행하는 Windows 검증 러너의 구조 단위 검사.

실제 Windows 네이티브 구동은 후속 일괄 검증에서 수행하며, 이 파일은 다음을 확인한다.

1. 러너·스키마·README가 존재하고 스키마가 유효한 JSON인지
2. PowerShell 소스의 구조적 정적 검사(괄호·따옴표 균형, here-string 무결성)
3. 파라미터 기본값(SHA 쌍 등)이 합의된 값과 일치하는지
4. 금지된 동작(권한 승격, 전역 ExecutionPolicy 변경, 설치, 민감 값 수집)이 없는지
5. W1~W3, T1~T6, IME/DPI/GPU/도킹 항목이 구분되어 수집되는지
6. 매핑된 pytest 파일과 기준 모델 자산이 실제 저장소에 존재하는지
7. 매니페스트 샘플이 verification_schema.json을 통과하는지

pwsh(실제 PowerShell 파서)가 있으면 문법 파싱도 수행하고, 없으면 건너뛴다.
실행: python -m pytest scripts/windows/test_windows_runner.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WINDOWS_DIR = Path(__file__).resolve().parent
REPO_ROOT = WINDOWS_DIR.parents[1]
RUNNER_PATH = WINDOWS_DIR / "run_windows_verification.ps1"
SCHEMA_PATH = WINDOWS_DIR / "verification_schema.json"
README_PATH = WINDOWS_DIR / "README.md"
MODEL_ASSET = REPO_ROOT / "scripts" / "evaluation" / "models" / "two_shell_plates_0000.rad"

EXPECTED_PREP_SHA = "531e02394694019511df2b38e3d3f7cb2140b254"
EXPECTED_WORKBENCH_SHA = "865ee159c9bd1375d996a72eacf898484f1d96cb"

CHECK_IDS = ["W1", "W2", "W3", "T1", "T2", "T3", "T4", "T5", "T6", "IME", "DPI", "GPU", "DOCKING"]

FORBIDDEN_PATTERNS = [
    (r"Set-ExecutionPolicy", "전역 ExecutionPolicy 변경"),
    (r"-Verb\s+[""']?RunAs", "권한 승격 실행"),
    (r"Start-Process[^\n]*-Verb", "권한 승격 실행"),
    (r"Invoke-Expression|\biex\s", "문자열 실행"),
    (r"Install-Module|Install-Package|pip\s+install", "설치 시도"),
    (r"Invoke-WebRequest|Invoke-RestMethod|Start-BitsTransfer|DownloadString|WebClient", "원격 다운로드"),
    (r"\breg(add|\.exe)", "레지스트리 변경"),
    (r"\bnetsh\b", "방화벽·네트워크 설정 변경"),
    (r"\bschtasks\b", "예약 작업 등록"),
    (r"SetEnvironmentVariable", "사용자·시스템 환경 변수 변경"),
    (r"PASSWORD|PASSWD|API_KEY|ACCESS_KEY|SECRET|TOKEN", "민감 값 수집 가능성"),
    (r"Enable-PSRemoting|Enter-PSSession|New-PSSession", "원격 실행 경로"),
]

REQUIRED_MANIFEST_KEYS = [
    "manifest_version",
    "runner",
    "requested",
    "environment",
    "repos",
    "paths",
    "checks",
    "overall_status",
]


@pytest.fixture(scope="module")
def runner_source() -> str:
    return RUNNER_PATH.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def schema_document() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _strip_powershell_noise(source: str) -> str:
    """here-string, 문자열 리터럴, 주석을 제거한 소스(균형 검사용)."""
    without_here = re.sub(r"@\x27\r?\n.*?\r?\n\x27@", "", source, flags=re.S)
    without_here = re.sub(r'@"\r?\n.*?\r?\n"@', "", without_here, flags=re.S)
    without_comments = re.sub(r"<#.*?#>", "", without_here, flags=re.S)
    without_comments = re.sub(r"#.*", "", without_comments)
    without_single = re.sub(r"\x27(?:[^\x27]|\x27\x27)*\x27", "''", without_comments)
    without_double = re.sub(r'"(?:[^"\n]|`")*"', '""', without_single)
    return without_double


def _sample_manifest() -> dict:
    return {
        "manifest_version": 1,
        "runner": {
            "script": "run_windows_verification.ps1",
            "created_utc": "2026-11-02T01:20:58.000000Z",
            "created_local": "2026-11-02T10:20:58+09:00",
            "ps_version": "5.1.26200.6901",
            "os": "Microsoft Windows 11 Pro build 26200",
            "git_version": "git version 2.47.0",
        },
        "requested": {
            "prep_sha": EXPECTED_PREP_SHA,
            "workbench_sha": EXPECTED_WORKBENCH_SHA,
            "python_path": "python",
            "prep_dir": "C:\\work\\caelab-prep",
            "workbench_dir": "C:\\work\\caelab-workbench",
            "output_dir": "C:\\Temp\\out",
            "solver_path": "",
            "run_solver": False,
            "timeout_seconds": 1800,
        },
        "environment": {
            "python_version": "Python 3.13.5",
            "python_exit_code": 0,
            "pyside6_version": "6.9.1",
            "git_version": "git version 2.47.0",
            "os": "Microsoft Windows 11 Pro build 26200",
            "system_dpi": 96,
        },
        "repos": {
            "prep": {
                "name": "prep",
                "path": "C:\\work\\caelab-prep",
                "exists": True,
                "full_sha": EXPECTED_PREP_SHA,
                "dirty": False,
                "porcelain_entries": [],
                "sha_matched": True,
                "requested_sha": EXPECTED_PREP_SHA,
                "git_error": "",
            },
            "workbench": {
                "name": "workbench",
                "path": "C:\\work\\caelab-workbench",
                "exists": True,
                "full_sha": EXPECTED_WORKBENCH_SHA,
                "dirty": False,
                "porcelain_entries": [],
                "sha_matched": True,
                "requested_sha": EXPECTED_WORKBENCH_SHA,
                "git_error": "",
            },
        },
        "paths": {
            "output_dir": "C:\\Temp\\out",
            "work_dir": "C:\\Temp\\out\\work-20261102-102000",
            "log_file": "C:\\Temp\\out\\runner.log",
            "cleanup_scope": "runner work directory only",
        },
        "checks": [
            {"id": "W1", "title": "NumericEdit import", "status": "passed", "detail": "ok", "evidence": {}},
            {"id": "W2", "title": "roundtrip", "status": "passed", "detail": "ok", "evidence": {}},
            {"id": "W3", "title": "solver deck", "status": "unexecuted", "detail": "no solver", "evidence": {}},
            {"id": "IME", "title": "IME", "status": "unexecuted", "detail": "not performed", "evidence": {}},
        ],
        "overall_status": "partial",
        "notes": ["note"],
    }


def test_runner_assets_exist():
    for path in (RUNNER_PATH, SCHEMA_PATH, README_PATH, MODEL_ASSET):
        assert path.is_file(), f"missing asset: {path}"
    assert RUNNER_PATH.stat().st_size > 0


def test_runner_parameter_defaults_match_agreed_shas(runner_source: str):
    assert f"$PrepSha = '{EXPECTED_PREP_SHA}'" in runner_source
    assert f"$WorkbenchSha = '{EXPECTED_WORKBENCH_SHA}'" in runner_source
    for parameter in ("$PythonPath", "$PrepDir", "$WorkbenchDir", "$OutputDir", "$SolverPath", "$TimeoutSeconds"):
        assert parameter in runner_source, f"runner lacks parameter {parameter}"


def test_runner_documents_required_parameters(runner_source: str):
    for name in ("PrepSha", "WorkbenchSha", "PythonPath", "OutputDir", "WorkbenchDir"):
        assert re.search(rf"\[{r'string'}\]\${name}\s*=", runner_source) or f"${name}" in runner_source


def test_powershell_structure_balanced(runner_source: str):
    stripped = _strip_powershell_noise(runner_source)
    pairs = {"(": ")", "{": "}", "[": "]"}
    counters = {"(": 0, ")": 0, "{": 0, "}": 0, "[": 0, "]": 0}
    for char in stripped:
        if char in counters:
            counters[char] += 1
    for opening, closing in pairs.items():
        assert counters[opening] == counters[closing], (
            f"unbalanced {opening}{closing}: {counters[opening]} vs {counters[closing]}"
        )


def test_runner_declares_process_cleanup_and_scope(runner_source: str):
    assert "taskkill /PID $ProcessId /T /F" in runner_source
    assert "runner work directory only" in runner_source
    assert "Start-Process" in runner_source and "WaitForExit" in runner_source


def test_runner_records_git_state_and_sha_match(runner_source: str):
    assert "rev-parse HEAD" in runner_source
    assert "status --porcelain" in runner_source
    assert "sha_matched" in runner_source
    assert "full_sha" in runner_source


def test_runner_covers_agreed_check_items(runner_source: str):
    for check_id in CHECK_IDS:
        assert re.search(rf"Add-Check '{re.escape(check_id)}'", runner_source), f"missing check {check_id}"
    assert "unexecuted" in runner_source
    for honest_id in ("IME", "DPI", "GPU", "DOCKING"):
        section = runner_source.split(f"Add-Check '{honest_id}'")[0]
        assert f"Set-Check -Id '{honest_id}' -Status 'unexecuted'" in runner_source or (
            f"Set-Check -Id '{honest_id}' -Status" in runner_source.split(f"Add-Check '{honest_id}'")[-1]
        ), f"{honest_id} must be recorded as unexecuted unless actually performed"
        del section


def test_runner_forbidden_operations_absent(runner_source: str):
    for pattern, reason in FORBIDDEN_PATTERNS:
        assert not re.search(pattern, runner_source), f"runner must not contain {reason} (pattern {pattern})"


def test_runner_deletion_scope_limited(runner_source: str):
    for line in runner_source.splitlines():
        if "Remove-Item" in line:
            assert "Env:" in line or "$script:WorkDir" in line or "$WorkDir" in line, (
                f"Remove-Item outside runner work scope: {line.strip()}"
            )


def test_mapped_test_files_exist_in_repository(runner_source: str):
    mapped = sorted(set(re.findall(r"test_[a-z0-9_]+\.py", runner_source)))
    assert mapped, "runner should map T1~T6 to concrete test files"
    for name in mapped:
        assert (REPO_ROOT / "tests" / name).is_file(), f"mapped test file missing: tests/{name}"


def test_schema_is_valid_and_validates_sample_manifest(schema_document: dict):
    jsonschema = pytest.importorskip("jsonschema")
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema_document)
    validator = Draft202012Validator(schema_document)
    validator.validate(_sample_manifest())


def test_schema_rejects_broken_manifests(schema_document: dict):
    jsonschema = pytest.importorskip("jsonschema")
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError

    validator = Draft202012Validator(schema_document)
    broken = _sample_manifest()
    broken["overall_status"] = "success"  # sha_matched=false + success 조합도 schema 수준에서 재구성 불가 확인용
    validator.validate(broken)

    missing_repos = _sample_manifest()
    del missing_repos["repos"]
    with pytest.raises(ValidationError):
        validator.validate(missing_repos)

    bad_sha = _sample_manifest()
    bad_sha["repos"]["prep"]["full_sha"] = "531e023"
    with pytest.raises(ValidationError):
        validator.validate(bad_sha)

    bad_status = _sample_manifest()
    bad_status["overall_status"] = "completed"
    with pytest.raises(ValidationError):
        validator.validate(bad_status)


def test_sha_mismatch_cannot_be_reported_as_success(runner_source: str):
    """sha_matched=false면 overall이 success가 되어서는 안 된다(소스 수준 확인)."""
    assert "$reposOk = $prepGit['sha_matched'] -and (-not $prepGit['dirty'])" in runner_source
    assert "elseif ($unexecutedChecks.Count -gt 0)" in runner_source


def test_readme_documents_usage_and_limits():
    text = README_PATH.read_text(encoding="utf-8")
    assert "run_windows_verification.ps1" in text
    assert "verification_manifest.json" in text
    assert "ExecutionPolicy" in text
    assert "Windows" in text


def test_pwsh_parser_check_when_available():
    """pwsh가 있으면 실제 PowerShell 파서로 문법을 확인한다. 없으면 건너뛴다."""
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh not available in this environment; structural checks only")
    script = (
        "$tokens = $null; $errors = $null; "
        "$null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{RUNNER_PATH}', [ref]$tokens, [ref]$errors); "
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Host $_.Message }; exit 1 } else { exit 0 }"
    )
    result = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"PowerShell parse errors: {result.stdout}\n{result.stderr}"
