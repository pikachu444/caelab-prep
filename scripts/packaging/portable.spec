"""One-directory Windows candidate; input paths are set by build_portable.py."""
import os
import sys
import hashlib
import json
import runpy
from pathlib import Path

import PyInstaller
import _pyinstaller_hooks_contrib

source = Path(os.environ["PREP_BUNDLE_SOURCE"])
dependencies = Path(os.environ["PREP_BUNDLE_DEPENDENCIES"])
build_tools = Path(os.environ["PREP_BUNDLE_TOOLS"])
entry = Path(SPECPATH) / "prep_entry.py"
site = dependencies / "Lib" / "site-packages"
validate_native_input = runpy.run_path(str(Path(SPECPATH) / "build_portable.py"))["validate_native_input"]
dependency_paths = [site]
# Selected-venv .pth files are not processed merely by placing site on
# PYTHONPATH. Reuse pywin32's two installed search paths and standard hooks.
for relative in ("win32", "win32/lib"):
    path = site / relative
    if path.is_dir():
        resolved = path.resolve()
        if not resolved.is_relative_to(site.resolve()):
            raise ValueError(f"PyWin32 search path outside selected environment: {path}")
        dependency_paths.append(resolved)
# Isolated hook children inherit this path list, including the staged build tools.
sys.path[:] = [path for path in sys.path if "site-packages" not in Path(path).parts
               or Path(path).resolve().is_relative_to(dependencies)]

a = Analysis(
    [str(entry)],
    pathex=[str(source / "src"), *map(str, dependency_paths)],
    binaries=[(str(dependencies / "Lib" / "gmsh-4.15.dll"), ".")],
    datas=[(str(source / "THIRD_PARTY.md"), "notices")],
    hiddenimports=[
        "caelab_prep.adapters.gmsh_worker",
        "caelab_prep.adapters.msh_worker",
        "caelab_prep.application.mesh_candidates",
        "caelab_prep.application.structured_mesh_worker",
        "vtkmodules.qt.QVTKRenderWindowInteractor",
        "gmsh",
    ],
    hookspath=[str(Path(SPECPATH) / "hooks")],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "IPython", "pytest",
              "setuptools", "_distutils_hack", "pkg_resources"],
    noarchive=False,
)
inputs = []
packager_roots = [Path(module.__file__).resolve().parent for module in (PyInstaller, _pyinstaller_hooks_contrib)]
for kind, entries in (("scripts", a.scripts), ("modules", a.pure), ("binaries", a.binaries), ("data", a.datas)):
    for name, origin, typecode in entries:
        path = Path(origin).resolve()
        if not path.is_file():
            continue
        if kind == "binaries" or path.suffix.casefold() in (".dll", ".pyd", ".exe"):
            validate_native_input(path, dependencies, build_tools)
        if (("site-packages" in path.parts or path.is_relative_to(build_tools)) and not path.is_relative_to(dependencies)
                and not any(path.is_relative_to(root) for root in packager_roots)):
            raise ValueError(f"Application input outside selected dependency environment: {path}")
        if (name == "caelab_prep" or name.startswith("caelab_prep.")) and not path.is_relative_to(source / "src"):
            raise ValueError(f"Application input outside source snapshot: {path}")
        with path.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        inputs.append({"kind": kind, "name": name, "source": str(path), "type": typecode,
                       "bytes": path.stat().st_size, "sha256": sha})
Path(os.environ["PREP_BUNDLE_INPUTS"]).write_text(json.dumps(inputs, indent=2), encoding="utf-8")
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="caelab-prep",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CAELab-Prep")
