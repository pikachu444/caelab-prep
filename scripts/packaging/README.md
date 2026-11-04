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

## Archive a built candidate

After the build, prepare an independently verifiable handoff without rebuilding:

```powershell
python scripts/packaging/archive_portable.py --candidate C:/path/to/new-candidate/dist/CAELab-Prep --output C:/path/to/new-handoff
```

The output directory must be new and outside the candidate. The command checks
the successful build's full source/packaging commits, every recorded file's size
and SHA256, and the complete inventory. Missing, changed, additional, symbolic-link
or unsafe/duplicate paths are rejected. It preserves the candidate and creates
a ZIP named with both commits and a `.zip.sha256` sidecar. The ZIP is reopened
and its CRCs and payload hashes checked before its final name is exposed.

Every recorded runtime, resource and notice file is retained except the local
`analysis-inputs.json`. The original `build-manifest.json` is replaced inside
the ZIP by a filtered handoff record: commits, payload inventory, original
record hashes, notice-gap counts and an explicit unaccepted redistribution
status. Environment paths, build commands, original analysis and private logs
are not copied into that record. This filtered record is not the original
analysis; keep the original build directory for that evidence. Notice texts
remain unchanged. Do not add user files to the candidate.

This command verifies archive integrity only. It does not run the EXE, validate
Windows installation/settings/VTK, clear redistribution conditions, publish a
release or turn an older source candidate into a build of current main. A failed
archive attempt can leave a new output directory; use a new path for a retry.
