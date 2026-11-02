"""One-directory Windows candidate; input paths are set by build_portable.py."""
import os
import hashlib
import json
from pathlib import Path

import PyInstaller
import _pyinstaller_hooks_contrib

source = Path(os.environ["PREP_BUNDLE_SOURCE"])
dependencies = Path(os.environ["PREP_BUNDLE_DEPENDENCIES"])
entry = Path(SPECPATH) / "prep_entry.py"

a = Analysis(
    [str(entry)],
    pathex=[str(source / "src"), str(dependencies / "Lib" / "site-packages")],
    binaries=[(str(dependencies / "Lib" / "gmsh-4.15.dll"), ".")],
    datas=[(str(source / "THIRD_PARTY.md"), "notices")],
    hiddenimports=[
        "caelab_prep.adapters.gmsh_worker",
        "caelab_prep.adapters.msh_worker",
        "caelab_prep.application.mesh_candidates",
        "vtkmodules.qt.QVTKRenderWindowInteractor",
        "gmsh",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "IPython", "pytest"],
    noarchive=False,
)
inputs = []
packager_roots = [Path(module.__file__).resolve().parent for module in (PyInstaller, _pyinstaller_hooks_contrib)]
for kind, entries in (("scripts", a.scripts), ("modules", a.pure), ("binaries", a.binaries), ("data", a.datas)):
    for name, origin, typecode in entries:
        path = Path(origin).resolve()
        if not path.is_file():
            continue
        if ("site-packages" in path.parts and not path.is_relative_to(dependencies)
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
