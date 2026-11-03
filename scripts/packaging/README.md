# Local Windows portable candidate

Use an existing application environment and a Python with PyInstaller installed:

```powershell
python scripts/packaging/build_portable.py --ref <published-source-SHA> --dependencies C:/path/to/application-venv --output C:/path/to/new-candidate
```

Commit packaging changes first. The builder snapshots the selected source with
`git archive`, records the separate packaging commit and hashes the entry, spec
and project hooks. It rejects an existing output directory and preserves earlier
candidates. Do not change the packaging checkout while the build is running.

The QtGui hook uses PyInstaller's normal dependency collection, excluding only
the Windows Qt Virtual Keyboard input-context plugin and PDF image-reader
plugin before their DLL dependencies are expanded. Prep's QtWidgets UI does not
use those features. Native platform/input plugins, SVG and other image plugins
are retained. This does not establish Windows IME or clean-machine acceptance;
inspect the new Analysis input list and verify the affected startup path.

Installed notices are collected with their original paths and hashes. Their
presence or number is not redistribution clearance. Qt module/third-party
conditions and missing LGPL/GPL texts remain unresolved in the manifest; do not
publish the candidate as an approved release on this basis. Keep EXE/DLL/ZIP
artifacts and user models out of Git.
