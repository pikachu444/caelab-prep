"""Checks for build input and notice preservation without running a bundler."""

import importlib.util
import json
from pathlib import Path
import sys
import sysconfig
import subprocess
import runpy
import types
import zipfile

import pytest


spec = importlib.util.spec_from_file_location(
    "build_portable", Path(__file__).parents[1] / "scripts/packaging/build_portable.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

@pytest.fixture
def native_runtime(tmp_path, monkeypatch):
    dependencies, tools, base, windows = (tmp_path / name for name in ("selected", "tools", "python", "windows"))
    for path in (dependencies, tools, base, windows):
        path.mkdir()
    monkeypatch.setattr(sys, "base_prefix", str(base))
    monkeypatch.setenv("SystemRoot", str(windows))
    return dependencies, tools, base, windows


def test_native_search_does_not_inherit_desktop_cache_paths(native_runtime, tmp_path, monkeypatch):
    dependencies, _, base, windows = native_runtime
    cache = tmp_path / "desktop-cache/bin"
    monkeypatch.setenv("PATH", str(cache))
    paths = builder.native_search_path(dependencies).split(builder.os.pathsep)
    assert str(cache) not in paths
    assert {str(path.resolve()) for path in (dependencies / "Scripts", dependencies / "Lib",
                                           base, base / "DLLs", windows / "System32")}.issubset(paths)
    assert builder.os.environ["PATH"] == str(cache)


@pytest.mark.parametrize("origin", ["selected", "tools", "python", "system"])
def test_native_origin_accepts_only_declared_runtime_roots(native_runtime, origin):
    dependencies, tools, base, windows = native_runtime
    roots = {"selected": dependencies / "Lib/site-packages/vendor", "tools": tools / "vendor",
             "python": base / "DLLs", "system": windows / "System32"}
    path = roots[origin] / "runtime.dll"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"native fixture")
    builder.validate_native_input(path, dependencies, tools)


@pytest.mark.parametrize("origin", ["poppler-cache", "libheif-cache", "global-site", "prefix-sibling"])
def test_native_origin_rejects_ambient_cache_and_global_packages(native_runtime, tmp_path, origin):
    dependencies, tools, base, _ = native_runtime
    roots = {"poppler-cache": tmp_path / "desktop/poppler/bin", "libheif-cache": tmp_path / "desktop/libheif/bin",
             "global-site": base / "Lib/site-packages/global", "prefix-sibling": tmp_path / "selected-other"}
    path = roots[origin] / "runtime.dll"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ambient fixture")
    with pytest.raises(ValueError, match="Native input outside"):
        builder.validate_native_input(path, dependencies, tools)


@pytest.mark.parametrize("ambient", [False, True])
def test_spec_applies_native_origin_guard_before_recording_or_building(native_runtime, tmp_path, monkeypatch, ambient):
    dependencies, tools, _, _ = native_runtime
    source = tmp_path / "source"
    source.mkdir()
    native = (tmp_path / "desktop-cache" if ambient else dependencies / "Lib") / "runtime.dll"
    native.parent.mkdir(parents=True, exist_ok=True)
    native.write_bytes(b"native fixture")
    inputs = tmp_path / "analysis-inputs.json"
    for key, path in {"PREP_BUNDLE_SOURCE": source, "PREP_BUNDLE_DEPENDENCIES": dependencies,
                      "PREP_BUNDLE_TOOLS": tools, "PREP_BUNDLE_INPUTS": inputs}.items():
        monkeypatch.setenv(key, str(path))
    for name in ("PyInstaller", "_pyinstaller_hooks_contrib"):
        module = types.ModuleType(name)
        module.__file__ = str(tools / name / "__init__.py")
        monkeypatch.setitem(sys.modules, name, module)
    # The spec mutates sys.path; keep that mutation local to this verification.
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec_path = Path(__file__).parents[1] / "scripts/packaging/portable.spec"
    globals_ = {"SPECPATH": str(spec_path.parent),
                "Analysis": lambda *a, **kw: types.SimpleNamespace(scripts=[], pure=[], datas=[],
                                                                  binaries=[("runtime.dll", str(native), "BINARY")]),
                "PYZ": lambda *a, **kw: object(), "EXE": lambda *a, **kw: object(),
                "COLLECT": lambda *a, **kw: object()}
    if ambient:
        with pytest.raises(ValueError, match="Native input outside"):
            runpy.run_path(str(spec_path), init_globals=globals_)
        assert not inputs.exists()
    else:
        runpy.run_path(str(spec_path), init_globals=globals_)
        assert json.loads(inputs.read_text())[0]["sha256"] == builder.digest(native)


archive_spec = importlib.util.spec_from_file_location(
    "archive_portable", Path(__file__).parents[1] / "scripts/packaging/archive_portable.py")
archiver = importlib.util.module_from_spec(archive_spec)
archive_spec.loader.exec_module(archiver)


@pytest.fixture
def portable_candidate(tmp_path):
    candidate = tmp_path / "candidate"
    files = {"caelab-prep.exe": b"fixture executable", "_internal/runtime.dll": b"fixture runtime",
             "_internal/resources/icon.svg": b"fixture resource",
             "notices/pkg/licenses/LICENSE": b"package license",
             "notices/pkg/licenses/vendor/LICENSE": b"vendor license",
             "analysis-inputs.json": b'[{"source":"C:/private-user/environment/module.py"}]'}
    for name, data in files.items():
        path = candidate / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    records = [{"path": name, "bytes": len(data), "sha256": builder.digest(candidate / name)}
               for name, data in files.items()]
    manifest = {"stage": "built", "build_exit_code": 0, "source_commit": "a" * 40,
                "packaging_commit": "b" * 40, "files": records, "file_count": len(records),
                "total_bytes": sum(item["bytes"] for item in records),
                "analysis_inputs_sha256": builder.digest(candidate / "analysis-inputs.json"),
                "dependency_environment": {"base_prefix": "C:/private-user/python"},
                "command": ["C:/private-user/python/python.exe"],
                "notices": {"files": [{"source": "C:/private-user/license"}],
                            "no_installed_notice_found": ["missing-license"], "unresolved": ["terms pending"]}}
    (candidate / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return candidate, manifest


def test_archive_preserves_payload_notices_and_private_candidate(portable_candidate, tmp_path):
    candidate, original = portable_candidate
    before = {p.relative_to(candidate).as_posix(): p.read_bytes() for p in candidate.rglob("*") if p.is_file()}
    archive_path = archiver.archive_candidate(candidate, tmp_path / "handoff")
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        public = json.loads(archive.read("CAELab-Prep/build-manifest.json"))
        assert "CAELab-Prep/analysis-inputs.json" not in archive.namelist()
        assert b"private-user" not in archive.read("CAELab-Prep/build-manifest.json")
        assert public["source_commit"] == original["source_commit"]
        assert public["packaging_commit"] == original["packaging_commit"]
        assert public["source_manifest_sha256"] == builder.digest(candidate / "build-manifest.json")
        assert public["analysis_inputs_sha256"] == original["analysis_inputs_sha256"]
        assert public["redistribution_accepted"] is False
        assert public["notice_gaps"] == public["unresolved_redistribution_conditions"] == 1
        assert set(archive.namelist()) == {"CAELab-Prep/" + name for name in before if name != "analysis-inputs.json"}
        for item in public["files"]:
            assert archive.read("CAELab-Prep/" + item["path"]) == before[item["path"]]
    checksum = archive_path.with_suffix(".zip.sha256").read_text(encoding="ascii")
    assert checksum == f"{builder.digest(archive_path)}  {archive_path.name}\n"
    assert before == {p.relative_to(candidate).as_posix(): p.read_bytes() for p in candidate.rglob("*") if p.is_file()}


@pytest.mark.parametrize("change", ["modified", "missing", "unrecorded"])
def test_archive_rejects_changed_inventory(portable_candidate, tmp_path, change):
    candidate, _ = portable_candidate
    if change == "modified":
        (candidate / "caelab-prep.exe").write_bytes(b"altered executable")
    elif change == "missing":
        (candidate / "_internal/runtime.dll").unlink()
    else:
        (candidate / "private-build.log").write_text("local build details")
    output = tmp_path / "handoff"
    with pytest.raises(ValueError, match="missing or changed|outside its recorded inventory"):
        archiver.archive_candidate(candidate, output)
    assert not output.exists()


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/absolute", "dir\\file",
                                  "dir/./file", "dir//file", "CAELAB-PREP.EXE", "build-manifest.json"])
def test_archive_rejects_unsafe_or_duplicate_paths(portable_candidate, tmp_path, name):
    candidate, manifest = portable_candidate
    manifest["files"].append({"path": name, "bytes": 0, "sha256": "0" * 64})
    (candidate / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe or duplicate"):
        archiver.archive_candidate(candidate, tmp_path / "handoff")


@pytest.mark.parametrize("field,value", [("stage", "failed"), ("build_exit_code", 1),
                                         ("source_commit", "HEAD"), ("packaging_commit", "dirty"),
                                         ("file_count", 0), ("analysis_inputs_sha256", "0" * 64)])
def test_archive_requires_successful_pinned_build(portable_candidate, tmp_path, field, value):
    candidate, manifest = portable_candidate
    manifest[field] = value
    (candidate / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        archiver.archive_candidate(candidate, tmp_path / "handoff")


def test_archive_preserves_existing_output_and_rejects_output_inside_candidate(portable_candidate, tmp_path):
    candidate, _ = portable_candidate
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "existing.zip"
    sentinel.write_bytes(b"preserve")
    for path in (output, candidate / "nested-output"):
        with pytest.raises(ValueError, match="new and outside"):
            archiver.archive_candidate(candidate, path)
    assert sentinel.read_bytes() == b"preserve"


def test_archive_detects_change_during_compression_without_handoff_zip(portable_candidate, tmp_path, monkeypatch):
    candidate, _ = portable_candidate
    write = archiver.zipfile.ZipFile.write

    def changed_write(archive, filename, *args, **kwargs):
        if Path(filename).name == "caelab-prep.exe":
            Path(filename).write_bytes(b"changed during compression")
        return write(archive, filename, *args, **kwargs)

    monkeypatch.setattr(archiver.zipfile.ZipFile, "write", changed_write)
    output = tmp_path / "handoff"
    with pytest.raises(ValueError, match="changed while archiving"):
        archiver.archive_candidate(candidate, output)
    assert list(output.iterdir()) == []


def test_archive_cli_creates_handoff_and_refuses_to_overwrite_it(portable_candidate, tmp_path):
    candidate, _ = portable_candidate
    output = tmp_path / "handoff"
    script = Path(__file__).parents[1] / "scripts/packaging/archive_portable.py"
    command = [sys.executable, str(script), "--candidate", str(candidate), "--output", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    archive = Path(result.stdout.strip())
    assert archive.is_file() and archive.parent == output
    checksum = builder.digest(archive)
    repeated = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert repeated.returncode == 2 and "new and outside" in repeated.stderr
    assert builder.digest(archive) == checksum


def test_archive_cleans_checksum_when_final_publication_fails(portable_candidate, tmp_path, monkeypatch):
    candidate, _ = portable_candidate
    before = {p.relative_to(candidate).as_posix(): p.read_bytes() for p in candidate.rglob("*") if p.is_file()}

    def failed_replace(path, target):
        raise PermissionError("publication denied")

    monkeypatch.setattr(Path, "replace", failed_replace)
    output = tmp_path / "handoff"
    with pytest.raises(PermissionError, match="publication denied"):
        archiver.archive_candidate(candidate, output)
    assert list(output.iterdir()) == []
    assert before == {p.relative_to(candidate).as_posix(): p.read_bytes() for p in candidate.rglob("*") if p.is_file()}


def test_notices_keep_nested_files_with_the_same_basename(tmp_path):
    site = tmp_path / "environment"
    files = [Path("pkg.dist-info/licenses/LICENSE"), Path("pkg.dist-info/licenses/vendor/LICENSE")]
    for item, text in zip(files, ("package terms", "vendor terms")):
        path = site / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    class Distribution:
        metadata = {"Name": "pkg"}

        def locate_file(self, item):
            return site / item

    distribution = Distribution()
    distribution.files = files
    destination = tmp_path / "notices"
    records, missing = builder.collect_notices([distribution], destination, site)
    assert not missing
    assert len(records) == 2
    assert {p.read_text() for p in destination.rglob("LICENSE")} == {"package terms", "vendor terms"}
    assert len({record["sha256"] for record in records}) == 2


@pytest.mark.parametrize("mismatch", ["abi", "module"])
def test_dependency_inventory_rejects_wrong_runtime_or_global_fallback(tmp_path, monkeypatch, mismatch):
    environment = tmp_path / "environment"
    module = environment / "Lib/site-packages/PySide6/__init__.py"
    result = {"abi": sysconfig.get_config_var("SOABI"), "base_prefix": sys.base_prefix,
              "modules": {"PySide6": str(module)}, "distributions": {}}
    if mismatch == "abi":
        result["abi"] = "incompatible-python"
    else:
        result["modules"]["PySide6"] = str(tmp_path / "global/PySide6/__init__.py")
    monkeypatch.setattr(builder.subprocess, "check_output", lambda *args, **kwargs: json.dumps(result))
    with pytest.raises(ValueError, match="Python/ABI|selected dependency environment"):
        builder.dependency_inventory(environment)


def test_packaged_entry_routes_recipe_worker_and_preserves_json_error_protocol(tmp_path):
    source = tmp_path / "missing recipe.json"
    entry = Path(__file__).parents[1] / "scripts/packaging/prep_entry.py"
    result = subprocess.run(
        [sys.executable, str(entry), "-m", "caelab_prep.application.structured_mesh_worker",
         str(source), str(tmp_path / "output")], capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    response = json.loads(result.stdout)
    assert response["ok"] is False and response["error"]["code"] == "structured_mesh_failed"
    assert source.name in response["error"]["message"]
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("separator,uppercase", [("/", False), ("\\", False), ("\\", True)])
def test_qtgui_hook_omits_only_optional_plugins_before_dependency_expansion(monkeypatch, separator, uppercase):
    packages = {}
    for name in ("PyInstaller", "PyInstaller.utils", "PyInstaller.utils.hooks", "PyInstaller.utils.hooks.qt"):
        packages[name] = types.ModuleType(name)
        packages[name].__path__ = []
        monkeypatch.setitem(sys.modules, name, packages[name])
    plugins = [("platforminputcontexts", "qtvirtualkeyboardplugin.dll"),
               ("imageformats", "qpdf.dll"), ("platforms", "qwindows.dll"),
               ("platforminputcontexts", "native-input.dll"), ("imageformats", "qjpeg.dll"),
               ("imageformats", "qsvg.dll")]
    binaries = []
    for bucket, name in plugins:
        source = f"C:/selected/PySide6/plugins/{bucket}/{name}"
        destination = f"PySide6/plugins/{bucket}"
        pair = (source.replace("/", separator), destination.replace("/", separator))
        binaries.append(tuple(value.upper() for value in pair) if uppercase else pair)
    # A DLL with the same basename outside the exact Qt plugin bucket is retained.
    binaries.append(("C:/other/qpdf.dll", "other/imageformats"))
    original = list(binaries)
    calls = []
    def collect(path):
        calls.append(Path(path).name)
        return ["PySide6.QtCore"], binaries, [("translation.qm", "PySide6/translations")]
    packages["PyInstaller.utils.hooks.qt"].add_qt6_dependencies = collect
    hook = Path(__file__).parents[1]/"scripts/packaging/hooks/hook-PySide6.QtGui.py"
    result = runpy.run_path(str(hook))
    assert calls == [hook.name]
    assert result["binaries"] == original[2:]
    assert binaries == original
    assert result["hiddenimports"] == ["PySide6.QtCore"]
    assert result["datas"] == [("translation.qm", "PySide6/translations")]
