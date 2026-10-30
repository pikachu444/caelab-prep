#!/usr/bin/env python3
"""Reacquire the pinned LS-DYNA reference sources; vendor files stay under tmp.

No solver is installed, imported, invoked, or validated by this script.
"""
import concurrent.futures
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = "90270f787216c91a969d6b477aaf753d45556035"
ROOT = Path(__file__).resolve().parents[1]
PYDYNA_PATHS = [
    "LICENSE", "README.rst", "pyproject.toml", "codegen/README.md",
    "codegen/kwd.json", "codegen/manifest.json", "codegen/additional-cards.json",
    "src/ansys/dyna/core/lib/deck.py", "src/ansys/dyna/core/lib/keyword_base.py",
    "src/ansys/dyna/core/lib/card_writer.py", "src/ansys/dyna/core/lib/field_writer.py",
    "src/ansys/dyna/core/lib/format_type.py", "src/ansys/dyna/core/lib/parameters.py",
    "src/ansys/dyna/core/lib/transform.py", "src/ansys/dyna/core/lib/validation_mixin.py",
    "src/ansys/dyna/core/keywords/keyword_classes/type_mapping.py",
    "src/ansys/dyna/core/keywords/keyword_classes/auto_keywords.py",
    "src/ansys/dyna/core/keywords/keyword_classes/auto/part/part.py",
    "src/ansys/dyna/core/keywords/keyword_classes/auto/section/section_shell.py",
    "src/ansys/dyna/core/keywords/keyword_classes/auto/mat/mat_piecewise_linear_plasticity.py",
    "examples/Taylor_Bar/plot_taylor_bar.py", "tests/test_deck.py", "tests/test_deck_validation.py",
    "tests/testfiles/standard/base.k",
    "tests/testfiles/keywords/transform/test.k", "tests/testfiles/keywords/transform/test_part.k",
    "tests/testfiles/keywords/expand_parameters/collision/main_with_consumer.k",
    "tests/testfiles/keywords/expand_parameters/collision/module_a.k",
    "tests/testfiles/keywords/expand_parameters/collision/module_b.k",
    "tests/testfiles/keywords/expand_parameters/collision/module_c_consumer.k",
    "tests/testfiles/keywords/expand_parameters/collision_local/main.k",
    "tests/testfiles/keywords/expand_parameters/collision_local/module_a_local.k",
    "tests/testfiles/keywords/expand_parameters/collision_local/module_b_local.k",
    "tests/testfiles/keywords/parameter_error_location/test_undefined_param.k",
    "tests/test_parameter_error_location.py", "tests/test_transform.py",
]

def fetch(path):
    url = f"https://raw.githubusercontent.com/ansys/pydyna/{REVISION}/{path}"
    destination = ROOT / "tmp/dyna/pydyna" / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        data = destination.read_bytes()
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "CAE-reference-research"})
        data = urllib.request.urlopen(request, timeout=90).read()
        destination.write_bytes(data)
    return {"path": path, "url": url, "revision": REVISION,
            "local_file": str(destination.relative_to(ROOT)),
            "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor-downloads", action="store_true",
                        help="Also acquire vendor manuals/examples into tmp only; never republishes them")
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(fetch, PYDYNA_PATHS))
    (ROOT / "tmp/dyna/pydyna-downloads.json").write_text(json.dumps(results, indent=2)+"\n")
    if args.vendor_downloads:
        vendor = []
        urls = [(f"vol{i}.pdf", f"https://lsdyna.ansys.com/wp-content/uploads/2026/06/LS-DYNA_Manual_Vol_{v}_R17.pdf")
                for i,v in enumerate(["I", "II", "III"],1)]
        urls += [("intro-examples.zip", "https://lsdyna.ansys.com/wp-content/uploads/2026/08/Intro_Examples_Manual.input_decks.zip"),
                 ("intro-examples-manual.pdf", "https://lsdyna.ansys.com/wp-content/uploads/2026/08/Intro_Examples_Manual_DRAFT.pdf")]
        for filename,url in urls:
            destination = ROOT/"tmp/dyna"/filename
            if not destination.exists():
                request = urllib.request.Request(url, headers={"User-Agent":"CAE-reference-research"})
                destination.write_bytes(urllib.request.urlopen(request,timeout=120).read())
            data = destination.read_bytes()
            vendor.append({"url":url,"local_file":str(destination.relative_to(ROOT)),
                           "size_bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),
                           "redistribution":"not-granted-do-not-repackage"})
        (ROOT/"tmp/dyna/vendor-downloads.json").write_text(json.dumps(vendor,indent=2)+"\n")
    print(json.dumps({"files": len(results), "revision": REVISION,
                      "total_bytes": sum(x["size_bytes"] for x in results)}))
