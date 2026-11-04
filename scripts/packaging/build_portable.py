"""Build a local Windows portable candidate with already installed dependencies.

Run with the Python that already has PyInstaller. No dependency installation,
working-tree cleanup, solver binaries or publication is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tarfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def native_search_path(dependencies):
    """Keep the analysis DLL search independent of the launching desktop tools."""
    base = Path(sys.base_prefix)
    windows = Path(os.environ["SystemRoot"])
    paths = (dependencies / "Scripts", dependencies / "Lib", base, base / "DLLs",
             windows / "System32", windows)
    return os.pathsep.join(str(path.resolve()) for path in paths)


def validate_native_input(path, dependencies, build_tools):
    path = path.resolve()
    selected = (dependencies.resolve(), build_tools.resolve())
    if (any(part.casefold() == "site-packages" for part in path.parts)
            and not any(path.is_relative_to(root) for root in selected)):
        raise ValueError(f"Native input outside selected environment: {path}")
    roots = (*selected, Path(sys.base_prefix).resolve(),
             (Path(os.environ["SystemRoot"]) / "System32").resolve())
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError(f"Native input outside declared runtime roots: {path}")


def dependency_inventory(dependencies):
    """Inspect the selected environment without PYTHONPATH or user-site fallback."""
    probe = r'''
import importlib.metadata as m, importlib.util, json, sys, sysconfig
names = ('PySide6', 'shiboken6', 'vtkmodules', 'gmsh')
print(json.dumps({
    'python': sys.version, 'base_prefix': sys.base_prefix,
    'abi': sysconfig.get_config_var('SOABI'),
    'modules': {n: importlib.util.find_spec(n).origin for n in names},
    'distributions': {d.metadata['Name']: {'version': d.version, 'root': str(d.locate_file(''))}
                      for d in m.distributions()},
}))
'''
    result = json.loads(subprocess.check_output(
        [str(dependencies / "Scripts" / "python.exe"), "-I", "-c", probe], text=True))
    site = dependencies / "Lib" / "site-packages"
    if (result["abi"] != sysconfig.get_config_var("SOABI")
            or Path(result["base_prefix"]).resolve() != Path(sys.base_prefix).resolve()):
        raise ValueError("Packager and dependency environment must use the same base Python/ABI")
    if any(not Path(path).resolve().is_relative_to(site) for path in result["modules"].values()):
        raise ValueError("Required application modules must come from the selected dependency environment")
    return result


def collect_notices(distributions, destination, allowed_root):
    records = []
    missing = []
    for distribution in distributions:
        name = distribution.metadata["Name"].lower().replace("-", "_")
        found = False
        for item in distribution.files or []:
            if not any(word in str(item).lower() for word in ("license", "copying", "copyright", "notice")):
                continue
            original = Path(distribution.locate_file(item)).resolve()
            if not original.is_file():
                continue
            relative = original.relative_to(allowed_root)
            target = destination / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            records.append({"distribution": name, "source": str(original),
                            "path": target.relative_to(destination).as_posix(), "sha256": digest(target)})
            found = True
        if not found:
            missing.append(name)
    return records, missing


def copy_build_tools(destination):
    """Expose installed Windows build tools without exposing all user packages."""
    records = []
    for name in ("PyInstaller", "pyinstaller-hooks-contrib", "altgraph", "packaging",
                 "pefile", "pywin32-ctypes", "setuptools"):
        distribution = metadata.distribution(name)
        root = Path(distribution.locate_file("")).resolve()
        for item in distribution.files or []:
            original = Path(distribution.locate_file(item)).resolve()
            if not original.is_file() or not original.is_relative_to(root) or original.suffix == ".pyc":
                continue
            relative = original.relative_to(root)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            sha = digest(original)
            if target.exists() and digest(target) != sha:
                raise ValueError(f"Build-tool distributions disagree on {relative}")
            shutil.copyfile(original, target)
            records.append({"distribution": name, "version": distribution.version,
                            "source": str(original), "path": relative.as_posix(), "sha256": sha})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Published source commit to snapshot")
    parser.add_argument("--dependencies", required=True, type=Path, help="Existing application venv")
    parser.add_argument("--output", required=True, type=Path, help="New, nonexisting build directory")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This candidate is built on Windows")
    import PyInstaller

    root = Path(__file__).resolve().parents[2]
    tooling = Path(__file__).resolve().parent
    dependencies = args.dependencies.resolve()
    site = dependencies / "Lib" / "site-packages"
    if not (dependencies / "Scripts" / "python.exe").is_file() or not (dependencies / "Lib" / "gmsh-4.15.dll").is_file():
        parser.error("Existing gui/cad environment and gmsh DLL are required")
    output = args.output.resolve()
    if output.exists():
        parser.error("Output must be new; existing candidates are preserved")
    inputs = dependency_inventory(dependencies)
    tooling_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--", "scripts/packaging"], cwd=root, text=True).strip():
        parser.error("Commit packaging changes before building so tooling inputs have an exact SHA")
    sha = subprocess.check_output(["git", "rev-parse", f"{args.ref}^{{commit}}"], cwd=root, text=True).strip()
    archive = subprocess.check_output(["git", "archive", sha, "src", "pyproject.toml", "THIRD_PARTY.md"], cwd=root)
    output.mkdir(parents=True)
    source = output / "source"
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(source, filter="data")
    build_tools = output / "build-tools"
    tool_inputs = copy_build_tools(build_tools)
    # Analysis and its isolated children see selected dependencies and exact tools.
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(source / "src"), str(site), str(build_tools)))
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    env["PATH"] = native_search_path(dependencies)
    env.update(PREP_BUNDLE_SOURCE=str(source), PREP_BUNDLE_DEPENDENCIES=str(dependencies),
               PREP_BUNDLE_TOOLS=str(build_tools),
               PREP_BUNDLE_INPUTS=str(output / "analysis-inputs.json"),
               PYINSTALLER_CONFIG_DIR=str(output / "cache"), MPLCONFIGDIR=str(output / "mpl-cache"))
    application_versions = {name: item["version"] for name, item in inputs["distributions"].items()}
    versions = {"python": sys.version, "packages": {
        **{name: metadata.version(name) for name in ("PyInstaller", "pyinstaller-hooks-contrib")},
        **{name: application_versions[name] for name in ("PySide6", "shiboken6", "vtk", "gmsh")},
    }}
    if "mcp" in application_versions:
        versions["packages"]["mcp"] = application_versions["mcp"]
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output / "dist"),
               "--workpath", str(output / "work"), str(tooling / "portable.spec")]
    manifest = {"source_commit": sha, "source_kind": "git archive; no working-tree application edits",
                "stage": "building", "versions": versions,
                "packaging_commit": tooling_sha, "dependency_environment": inputs,
                "native_search_path": env["PATH"].split(os.pathsep),
                "native_input_scope": "selected dependencies, staged tools, base Python and Windows System32",
                "build_tool_inputs": tool_inputs,
                "packaging_files": {p.relative_to(tooling).as_posix(): digest(p)
                                    for p in (Path(__file__), tooling / "prep_entry.py", tooling / "portable.spec",
                                              *sorted((tooling / "hooks").glob("*.py")))},
                "command": command, "external_solver_binaries_bundled": False,
                "scope": "local internal candidate; no clean-machine or public redistribution acceptance"}
    manifest_path = output / "build-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Building {sha} -> {output / 'dist' / 'CAELab-Prep'}", flush=True)
    with (output / "build.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    manifest.update(stage="built" if result.returncode == 0 else "failed", build_exit_code=result.returncode)
    if result.returncode == 0:
        destination = output / "dist" / "CAELab-Prep"
        notices = destination / "notices"
        notices.mkdir()
        # Environment-wide notices are a superset, not redistribution clearance.
        records, missing = collect_notices(metadata.distributions(path=[str(site)]), notices, dependencies)
        packager_missing = []
        items, packager_missing = collect_notices(metadata.distributions(path=[str(build_tools)]), notices, build_tools)
        records.extend(items)
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        shutil.copyfile(python_license, notices / "CPython-LICENSE.txt")
        records.append({"distribution": "CPython", "source": str(python_license),
                        "path": "CPython-LICENSE.txt", "sha256": digest(python_license)})
        manifest["notices"] = {"files": records, "no_installed_notice_found": missing + packager_missing,
                               "scope": "selected environment superset plus CPython and PyInstaller; not legal clearance",
                               "unresolved": ["Qt/PySide6 LGPL/GPL texts and obligations are not established by installed commercial notices",
                                              "Complete transitive binary redistribution conditions remain unverified"]}
        shutil.copyfile(output / "analysis-inputs.json", destination / "analysis-inputs.json")
        manifest["analysis_inputs_sha256"] = digest(destination / "analysis-inputs.json")
        manifest["files"] = [{"path": p.relative_to(destination).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)}
                             for p in sorted(destination.rglob("*")) if p.is_file()]
        manifest["total_bytes"] = sum(p["bytes"] for p in manifest["files"])
        manifest["file_count"] = len(manifest["files"])
        (destination / "build-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Built {manifest['file_count']} files, {manifest['total_bytes']} bytes", flush=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
