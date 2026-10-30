# Radioss research code: provenance and use conditions

These are unmodified reference source files, not a standalone build or a new solver, converter, or complete deck generator. They were acquired for source inspection on 2026-10-30. No included code or solver was executed. File headers and upstream copyright notices are retained.

## OpenCourant Tools — MIT

Repository: https://github.com/OpenCourant/Tools

Revision: `1b6bb9200ee7dca899e61c18bd982c3fb1c72fd1`

| Local file under `code/` | Original path |
|---|---|
| `inp2rad.py` | `input_converters/inp2rad/inp2rad/inp2rad.py` |
| `inp2rad-README.md` | `input_converters/inp2rad/README.md` |
| `Tools-Copyright.md` | `Copyright.md` |

The converter source header and `Tools-Copyright.md` grant the MIT license. Preserve those notices when reusing the code. The converter handles an INP subset, not every Abaqus option or every native Radioss keyword. Its default format version is 2025, with 2023/2025 choices. Its output defaults are not an independent unit-detection or semantic validation service.

## OpenCourant — AGPL-3.0-or-later selected source

Repository: https://github.com/OpenCourant/OpenCourant

Release: `latest-20261011`; revision: `cb760c206e346eff12161a2268b134ef9d48a4ef`

| Local file under `code/` | Original path |
|---|---|
| `radiossblk.cxx` | `reader/source/io/model_readers/radioss/radiossblk/radiossblk.cxx` |
| `mec_data_writer.cpp` | `reader/source/cfgio/MODEL_IO/mec_data_writer.cpp` |
| `mec_single_file_writer.cpp` | `reader/source/cfgio/MODEL_IO/mec_single_file_writer.cpp` |
| `verify_results.py` | `qa-tests/qa_tools/verify_results.py` |
| `OpenCourant-LICENSE.md` | `LICENSE.md` |
| `OpenCourant-COPYRIGHT.md` | `COPYRIGHT.md` |

The selected source-file headers specify GNU Affero General Public License version 3 or later and the upstream OpenRadioss/OpenCourant copyright attribution. The full license text and upstream copyright statement accompany these files. Their source paths and exact revision above provide the corresponding upstream context. This snapshot is a reference subset; required headers, model descriptors, build files, libraries, and solver binaries are not included as a working package. No claim is made that the subset compiles independently.

The reader/writer source depends on model and CFG machinery. A generic conditional-card writer is not a complete native RAD generator. `verify_results.py` compares upstream regression output; it is not a physical correctness certificate.

## Material deliberately excluded from this distribution

- Altair commercial manual HTML, PDF, and figures: actual originals remain internal to the research acquisition. The published catalogue contains factual names, URLs, page/section locators, hashes, short independent summaries, and read-depth records; it does not republish the manuals.
- `hm_cfg_files`: 1331 of the 1333 inventoried Radioss files have a file-specific limited-use notice restricting use/modification to OpenRadioss and requiring provision of modifications. Two notices remain unclassified. The top-level repository AGPL notice is not assumed to override these notices. No CFG source bytes are included here; see the locator/hash inventory.
- QA model `.rad` files and Tools SDK `small_plast` model files: inspected deck headers say Creative Commons Attribution-NonCommercial 4.0. They are not represented as MIT/AGPL commercial assets and are not reproduced here. Unclassified companion files likewise remain locator-only. Original bytes were actually acquired internally; the example ledger preserves their source, revision, size, and hash.

`code-manifest.json` records the exact included files and SHA256 hashes. Licensing remains file-specific; public availability of a manual, model, or source tree is not a blanket redistribution grant for every item in it.
