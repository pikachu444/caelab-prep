"""Stage factual docs and provenance, excluding reference code/vendor originals.

No Git/network writes here. The integration owner publishes after review.
"""
from pathlib import Path
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT.parent/'solver-input-publish'
PREFIX=Path('docs/solver-input-assets/2026-10-30')

def stage():
    files=[]
    for folder in ['notes','solvers','catalogues','discussion','scripts']:
        files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [ROOT/name for name in ['README.md','THIRD_PARTY.md','summary.json','index.html','validation.json']]
    for folder in ['assets','examples']:
        files += [p for p in (ROOT/folder).rglob('*') if p.is_file() and (
            p.name.lower() in ('notice.md','license','license.md','license.txt','copying','copyright.md')
            or p.name in ('files.json','source-manifest.json','code-manifest.json','pydyna-source-inventory.json')
            or p.name.endswith(('-COPYING','-GPL-2.0.txt','-LICENSE.md','-COPYRIGHT.md','-Copyright.md')))]
    out=[]
    for p in sorted(set(files)):
        relative=PREFIX/p.relative_to(ROOT);dst=DEST/relative;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst);out.append(str(relative))
    all_files=sorted(str(p.relative_to(DEST)) for p in DEST.rglob('*') if p.is_file())
    manifest=dict(file_count=len(all_files),files=all_files,total_bytes=sum((DEST/p).stat().st_size for p in all_files))
    (ROOT/'.transfer/public-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(files=manifest['file_count'],bytes=manifest['total_bytes'])))

if __name__=='__main__':stage()
