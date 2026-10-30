#!/usr/bin/env python3
"""Package MIT source snapshots and inventory vendor examples without publishing them."""
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REV = "90270f787216c91a969d6b477aaf753d45556035"

def sha(data):
    return hashlib.sha256(data).hexdigest()

if __name__ == "__main__":
    records = json.loads((ROOT / "tmp/dyna/pydyna-downloads.json").read_text())
    inventory = []
    for record in records:
        relative = record["path"]
        base = "examples/dyna/pydyna" if relative.endswith(".k") else "assets/dyna/pydyna"
        target = ROOT / base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / record["local_file"], target)
        assert sha(target.read_bytes()) == record["sha256"]
        inventory.append({**record, "packaged_file":str(target.relative_to(ROOT)),
                          "license":"MIT", "solver_executed":False,
                          "git_inclusion":"exclude-large-source" if relative == "codegen/kwd.json" else "small-snapshot"})
    notice = f"""# PyDYNA source snapshot / provenance

Upstream: https://github.com/ansys/pydyna
Revision: {REV}
Package declaration at this revision: ansys-dyna-core 0.13.dev0 (development source, not the stable v0.12.1 release).
License: MIT, reproduced as LICENSE. Root pyproject declares license=MIT and license-files=[LICENSE].
The recursive upstream tree was checked for LICENSE/NOTICE/COPYING: LICENSE is at root; no different path license was found for these files. Python sources retain their SPDX MIT headers.

Files are unmodified reference excerpts of the upstream project, preserving relative paths. This subset is not an installable standalone package. The file inventory records exact upstream URLs, byte counts, SHA256, and destination paths. No source was installed/imported, no fixture was parsed by PyDYNA, and no solver was run in this collection.

codegen/kwd.json is the full upstream JSON (not a handpicked keyword subset). codegen/README.md describes it as machine-generated from an LS-DYNA manual; manifest.json and additional-cards.json supply corrections/supplements. The upstream snapshot does not identify a complete R17 field support guarantee. The MIT repository snapshot and commercial vendor PDFs have different provenance and distribution conditions; no vendor manual PDF or full page text is included here.

The kwd.json file is retained for the downloadable reference archive, not public Git staging, per integration policy. The remaining source subset is for code reading and asset evaluation; dependency/runtime compatibility is untested.

tests/testfiles/*.k are parser/transform/parameter fixtures. base.k has zero material/section references and is not a complete validated structural model. The transform fixture deliberately contains short/degenerate connectivity cases. Undefined parameter and collision fixtures are useful negative/semantic examples, not solver-certified valid inputs. Test assertions remain upstream evidence only; this research did not execute them.
"""
    for folder in [ROOT/"assets/dyna/pydyna", ROOT/"examples/dyna/pydyna"]:
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/"tmp/dyna/pydyna/LICENSE",folder/"LICENSE")
        (folder/"NOTICE.md").write_text(notice)
    (ROOT/"assets/dyna/pydyna-source-inventory.json").write_text(json.dumps(inventory,indent=2)+"\n")
    z = zipfile.ZipFile(ROOT/"tmp/dyna/intro-examples.zip")
    example_rows=[]
    for info in z.infolist():
        if info.is_dir():
            continue
        data=z.read(info.filename)
        text=data.decode("utf-8",errors="replace")
        names=re.findall(r"^\*[^\r\n]+",text,re.MULTILINE)
        example_rows.append({"source_id":"dyna-D05", "archive_member":info.filename,
            "size_bytes":len(data), "sha256":sha(data), "keyword_blocks":len(names),
            "distinct_keyword_names":len(set(names)), "contains_include":any(n.startswith("*INCLUDE") for n in names),
            "keyword_names_json":json.dumps(list(dict.fromkeys(names))),
            "redistribution":"unknown-vendor-download-not-repackaged", "solver_executed":False})
    with (ROOT/"catalogues/dyna-official-examples.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(example_rows[0]));w.writeheader();w.writerows(example_rows)
    for row in example_rows:
        if row["archive_member"] in [
            "example_01/thin_shell_elform_16/ex_01_thin_shell_elform_16.k",
            "example_03/solid_elform_-1/4x6x4_mesh/ex_03_solid_elform_-1_4x6x4_mesh.k"]:
            target=ROOT/"tmp/dyna/official-examples"/row["archive_member"]
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(row["archive_member"]))
    print(json.dumps({"pydyna_files":len(inventory),"vendor_example_files":len(example_rows),
                      "vendor_example_bytes":sum(r["size_bytes"] for r in example_rows)}))
