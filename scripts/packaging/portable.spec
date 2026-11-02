"""One-directory Windows candidate; input paths are set by build_portable.py."""
import os
from pathlib import Path

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
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="caelab-prep",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CAELab-Prep")
