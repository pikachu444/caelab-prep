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
import tarfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
    sha = subprocess.check_output(["git", "rev-parse", f"{args.ref}^{{commit}}"], cwd=root, text=True).strip()
    archive = subprocess.check_output(["git", "archive", sha, "src", "pyproject.toml", "THIRD_PARTY.md"], cwd=root)
    output.mkdir(parents=True)
    source = output / "source"
    source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(source, filter="data")
    # Existing venv dependencies take precedence over the packager's global site.
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(source / "src"), str(site), str(Path(PyInstaller.__file__).resolve().parent.parent)))
    env.pop("PYTHONHOME", None)
    env.update(PREP_BUNDLE_SOURCE=str(source), PREP_BUNDLE_DEPENDENCIES=str(dependencies),
               PYINSTALLER_CONFIG_DIR=str(output / "cache"), MPLCONFIGDIR=str(output / "mpl-cache"))
    versions = subprocess.check_output(
        [sys.executable, "-c", "import sys,json,importlib.metadata as m; print(json.dumps({'python':sys.version,'packages':{n:m.version(n) for n in ('PyInstaller','pyinstaller-hooks-contrib','PySide6','shiboken6','vtk','gmsh','mcp')}}))"],
        cwd=source, env=env, text=True,
    )
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output / "dist"),
               "--workpath", str(output / "work"), str(tooling / "portable.spec")]
    manifest = {"source_commit": sha, "source_kind": "git archive; no working-tree application edits",
                "stage": "building", "versions": json.loads(versions),
                "packaging_files": {p.name: digest(p) for p in (Path(__file__), tooling / "prep_entry.py", tooling / "portable.spec")},
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
        # Preserve installed license texts verbatim and record the exact included files.
        distributions = {d.metadata["Name"].lower().replace("-", "_"): d for d in metadata.distributions(path=[str(site)])}
        for name in ("pyside6", "pyside6_essentials", "pyside6_addons", "shiboken6", "vtk", "gmsh"):
            distribution = distributions[name]
            for item in distribution.files or []:
                if any(word in str(item).lower() for word in ("license", "copying", "copyright")):
                    original = Path(distribution.locate_file(item))
                    if original.is_file():
                        target = notices / name / original.name
                        target.parent.mkdir(exist_ok=True)
                        shutil.copyfile(original, target)
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
