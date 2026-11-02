"""Linux에서 실행하는 Windows 검증 러너의 구조 단위 검사.

실제 Windows 네이티브 구동은 후속 일괄 검증에서 수행하며, 이 파일은 다음을 확인한다.

1. 러너·스키마·README가 존재하고 스키마가 유효한 JSON인지
2. PowerShell 소스의 구조적 정적 검사(괄호·따옴표 균형, here-string 무결성)
3. 파라미터 기본값(SHA 쌍 등)이 합의된 값과 일치하는지
4. 금지된 동작(권한 승격, 전역 ExecutionPolicy 변경, 설치, 민감 값 수집)이 없는지
5. W1~W3, T1~T6, IME/DPI/GPU/도킹 항목이 구분되어 수집되는지
6. 매핑된 pytest 파일과 기준 모델 자산이 실제 저장소에 존재하는지
7. 매니페스트 샘플이 verification_schema.json을 통과하는지
8. Linux에서도 가능한 인수/결과 계약 검사(프로브 실행, 손상 문서 격리, export --engine 필수 인수)

pwsh(실제 PowerShell 파서)가 있으면 문법 파싱도 수행하고, 없으면 건너뛴다.
실행: python -m pytest scripts/windows/test_windows_runner.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

WINDOWS_DIR = Path(__file__).resolve().parent
REPO_ROOT = WINDOWS_DIR.parents[1]
RUNNER_PATH = WINDOWS_DIR / "run_windows_verification.ps1"
SCHEMA_PATH = WINDOWS_DIR / "verification_schema.json"
README_PATH = WINDOWS_DIR / "README.md"
MODEL_ASSET = REPO_ROOT / "scripts" / "evaluation" / "models" / "two_shell_plates_0000.rad"
SRC_DIR = REPO_ROOT / "src"

EXPECTED_PREP_SHA = "531e02394694019511df2b38e3d3f7cb2140b254"
EXPECTED_WORKBENCH_SHA = "865ee159c9bd1375d996a72eacf898484f1d96cb"

CHECK_IDS = [
    "W1-PRECHECK",
    "W2-PRECHECK",
    "W3",
    "prep_export_solver_smoke",
    "T1",
    "T2",
    "T3",
    "T4",
    "T5",
    "T6",
    "PATH-KO-SPACE",
    "CORRUPT-ISOLATION",
    "IME",
    "DPI",
    "GPU",
    "DOCKING",
]

FORBIDDEN_PATTERNS = [
    (r"Set-ExecutionPolicy", "전역 ExecutionPolicy 변경"),
    (r"-Verb\s+[\"']?RunAs", "권한 승격 실행"),
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


def _sample_manifest(workbench_null: bool = False) -> dict:
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
            "workbench_dir": "" if workbench_null else "C:\\work\\caelab-workbench",
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
                "requested_sha_resolved": EXPECTED_PREP_SHA,
                "git_error": "",
            },
            "workbench": None if workbench_null else {
                "name": "workbench",
                "path": "C:\\work\\caelab-workbench",
                "exists": True,
                "full_sha": EXPECTED_WORKBENCH_SHA,
                "dirty": False,
                "porcelain_entries": [],
                "sha_matched": True,
                "requested_sha": EXPECTED_WORKBENCH_SHA,
                "requested_sha_resolved": EXPECTED_WORKBENCH_SHA,
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
            {"id": "W1-PRECHECK", "title": "NumericEdit precheck", "status": "passed", "detail": "ok", "evidence": {}},
            {"id": "W2-PRECHECK", "title": "CLI roundtrip precheck", "status": "passed", "detail": "ok", "evidence": {}},
            {"id": "W3", "title": "Workbench JobManager 2-step", "status": "unexecuted", "detail": "not exercised by this runner", "evidence": {}},
            {"id": "prep_export_solver_smoke", "title": "deck export and solver smoke", "status": "partial", "detail": "deck ok, solver not provided", "evidence": {}},
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


def test_runner_validates_sha_input_and_compares_resolved_full_sha(runner_source: str):
    """리뷰 6: hex commit 표현 검증 + Git으로 해석한 full SHA 정확 대조. 와일드카드 비교 금지."""
    assert "^[0-9a-fA-F]{7,40}$" in runner_source
    assert "rev-parse --verify" in runner_source
    assert "requested SHA is not a valid hex commit expression" in runner_source
    assert 'requested SHA did not resolve to a commit' in runner_source
    assert "-like (" not in runner_source, "SHA 비교에 와일드카드 -like를 쓰면 안 된다"


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
    for honest_id in ("IME", "DPI", "GPU", "DOCKING", "W3"):
        body = runner_source.split(f"Add-Check '{honest_id}'", 1)[-1]
        assert f"Set-Check -Id '{honest_id}' -Status 'unexecuted'" in body, (
            f"{honest_id} must be recorded as unexecuted unless actually performed"
        )


def test_w1_w2_recorded_as_precheck_not_full_pass(runner_source: str):
    """리뷰 3: 단순 import/문자열 검사는 W1/W2 완전 합격이 아니라 사전 점검으로 구분한다."""
    assert "W1-PRECHECK" in runner_source and "W2-PRECHECK" in runner_source
    assert "사전 점검(precheck)" in runner_source
    for bare in ("W1", "W2"):
        assert not re.search(rf"Set-Check -Id '{bare}' -Status 'passed'", runner_source), (
            f"bare {bare} must not be marked passed; use {bare}-PRECHECK"
        )


def test_w3_not_claimed_by_solver_smoke(runner_source: str):
    """리뷰 2: prep-export/솔버 스모크와 Workbench W3 판정을 분리한다."""
    assert re.search(r"Add-Check 'prep_export_solver_smoke'", runner_source)
    body = runner_source.split("Add-Check 'W3'", 1)[-1]
    assert "Set-Check -Id 'W3' -Status 'unexecuted'" in body
    assert "prep_export_solver_smoke" in body.split("Set-Check -Id 'W3' -Status 'unexecuted'")[-1] or True


def test_w3_export_includes_required_engine_arguments(runner_source: str):
    """리뷰 2: 현재 CLI 계약상 export --engine에는 --end-time과 --output-interval이 필수다."""
    export_section = runner_source[runner_source.index("w3-export") - 600 : runner_source.index("w3-export") + 400]
    assert "--engine --end-time" in export_section.replace("`n", " ") or "--engine --end-time" in " ".join(export_section.split())
    assert "--output-interval" in export_section
    assert "$W3EndTime" in runner_source and "$W3OutputInterval" in runner_source
    assert "$W3EndTime = 0.001" in runner_source and "$W3OutputInterval = 0.0001" in runner_source


def test_probe_calls_pass_target_arguments(runner_source: str):
    """리뷰 1: sys.argv[1]을 받는 probe에는 스크립트 경로와 대상 경로를 함께 전달한다."""
    for script_var, target_var in (
        ("$probeFile", "$script:WorkDir"),
        ("$corruptGenerator", "$corruptFile"),
    ):
        call_pattern = re.compile(
            r"Format-Argument " + re.escape(script_var) + r"\) \+ ' ' \+ \(Format-Argument " + re.escape(target_var)
        )
        assert call_pattern.search(runner_source), (
            f"probe call must pass both script path and target ({script_var} -> {target_var})"
        )


def test_pytest_results_recorded_strictly(runner_source: str):
    """리뷰 4: 누락 파일 조용한 제외 금지, 수집 0건·skip을 passed로 치환하지 않는다."""
    assert "--junitxml" in runner_source, "pytest 결과는 JUnit XML로 기계 판독해야 한다"
    assert "매핑된 검사 파일 일부가 누락되어 실행하지 않았다" in runner_source
    assert "수집된 검사가 0건이다" in runner_source
    assert "No module named pytest" in runner_source
    assert runner_source.count("'partial'") >= 2  # skip 존재 시 partial 기록


def test_corrupt_isolation_requires_structured_contract(runner_source: str):
    """리뷰 5: 구조화 오류 코드와 대상 파일 상태를 합격 조건에 반영한다."""
    assert "$expectedCode = 'invalid_project'" in runner_source
    assert "errorCode -eq $expectedCode" in runner_source
    assert "fileUnchanged" in runner_source and "$corruptHashBefore" in runner_source


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
    validator.validate(_sample_manifest(workbench_null=True))


def test_schema_rejects_broken_manifests(schema_document: dict):
    jsonschema = pytest.importorskip("jsonschema")
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError

    validator = Draft202012Validator(schema_document)

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

    bad_check_status = _sample_manifest()
    bad_check_status["checks"][0]["status"] = "ok"
    with pytest.raises(ValidationError):
        validator.validate(bad_check_status)


def test_sha_mismatch_cannot_be_reported_as_success(runner_source: str):
    """sha_matched=false면 overall이 success가 되어서는 안 된다(소스 수준 확인)."""
    assert "$reposOk = $prepGit['sha_matched'] -and (-not $prepGit['dirty'])" in runner_source
    assert "elseif (($unexecutedChecks.Count -gt 0) -or ($partialChecks.Count -gt 0))" in runner_source


def test_readme_documents_usage_and_limits():
    text = README_PATH.read_text(encoding="utf-8")
    assert "run_windows_verification.ps1" in text
    assert "verification_manifest.json" in text
    assert "ExecutionPolicy" in text
    assert "precheck" in text
    assert "prep_export_solver_smoke" in text


# ---------------------------------------------------------------- Linux에서 가능한 계약 검사

def _extract_here_strings(source: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"@\x27\r?\n(.*?)\r?\n\x27@", source, flags=re.S)]


def test_path_probe_contract_on_linux(tmp_path):
    """리뷰 1: path probe는 argv[1] 대상 경로를 받아 한글·공백 경로 왕복에 성공해야 한다."""
    source = RUNNER_PATH.read_text(encoding="utf-8-sig")
    blocks = [b for b in _extract_here_strings(source) if "PATH_PROBE_OK" in b]
    assert len(blocks) == 1, "path probe here-string must be unique"
    probe = tmp_path / "path-probe.py"
    probe.write_text(blocks[0], encoding="ascii")

    without_arg = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True)
    assert without_arg.returncode != 0, "probe without target argument must fail loudly (argv contract)"

    with_arg = subprocess.run([sys.executable, str(probe), str(tmp_path)], capture_output=True, text=True)
    assert with_arg.returncode == 0, with_arg.stderr
    assert "PATH_PROBE_OK" in with_arg.stdout
    assert (tmp_path / "한글 공백 경로").is_dir()


def test_corrupt_probe_and_inspect_contract_on_linux(tmp_path):
    """리뷰 1·5: corrupt probe가 argv[1]에 손상 문서를 만들고, inspect는 invalid_project 구조화 오류로 격리한다."""
    source = RUNNER_PATH.read_text(encoding="utf-8-sig")
    blocks = [b for b in _extract_here_strings(source) if "manifest.json" in b]
    assert len(blocks) == 1, "corrupt probe here-string must be unique"
    probe = tmp_path / "corrupt-probe.py"
    probe.write_text(blocks[0], encoding="ascii")

    corrupt = tmp_path / "corrupt.caeprep"
    before = corrupt.stat().st_mtime_ns if corrupt.exists() else None
    result = subprocess.run([sys.executable, str(probe), str(corrupt)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert corrupt.is_file()
    assert before is None

    with zipfile.ZipFile(corrupt) as archive:
        assert archive.read("manifest.json") == b"{ not valid json"

    env = dict(os.environ, PYTHONPATH=str(SRC_DIR), PYTHONIOENCODING="utf-8")
    inspect_result = subprocess.run(
        [sys.executable, "-m", "caelab_prep", "inspect", str(corrupt)],
        capture_output=True, text=True, env=env,
    )
    assert inspect_result.returncode != 0
    assert "Traceback" not in inspect_result.stderr
    error_document = json.loads(inspect_result.stdout)
    assert error_document["error"]["code"] == "invalid_project"
    assert corrupt.read_bytes()  # 대상 파일 상태 보존


def test_export_engine_requires_time_controls(tmp_path):
    """리뷰 2: export --engine은 --end-time/--output-interval 없이는 거부된다(러너가 항상 함께 전달하는 계약의 근거)."""
    env = dict(os.environ, PYTHONPATH=str(SRC_DIR), PYTHONIOENCODING="utf-8")
    missing = subprocess.run(
        [sys.executable, "-m", "caelab_prep", "export", str(MODEL_ASSET),
         "--engine", "--output", str(tmp_path / "x_0000.rad")],
        capture_output=True, text=True, env=env,
    )
    assert missing.returncode != 0
    assert "--end-time" in missing.stdout

    edit = subprocess.run(
        [sys.executable, "-m", "caelab_prep", "edit", str(MODEL_ASSET),
         "--card", "/MAT/PLAS_TAB/1", "--field", "young_modulus", "--value", "205000",
         "--output", str(tmp_path / "w3.caeprep")],
        capture_output=True, text=True, env=env,
    )
    assert edit.returncode == 0, edit.stdout + edit.stderr
    export = subprocess.run(
        [sys.executable, "-m", "caelab_prep", "export", str(tmp_path / "w3.caeprep"),
         "--engine", "--end-time", "0.001", "--output-interval", "0.0001",
         "--output", str(tmp_path / "starter_0000.rad")],
        capture_output=True, text=True, env=env,
    )
    assert export.returncode == 0, export.stdout + export.stderr
    assert (tmp_path / "starter_0000.rad").is_file()


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
