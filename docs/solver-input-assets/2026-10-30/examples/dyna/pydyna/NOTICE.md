# PyDYNA source snapshot / provenance

Upstream: https://github.com/ansys/pydyna
Revision: 90270f787216c91a969d6b477aaf753d45556035
Package declaration at this revision: ansys-dyna-core 0.13.dev0 (development source, not the stable v0.12.1 release).
License: MIT, reproduced as LICENSE. Root pyproject declares license=MIT and license-files=[LICENSE].
The recursive upstream tree was checked for LICENSE/NOTICE/COPYING: LICENSE is at root; no different path license was found for these files. Python sources retain their SPDX MIT headers.

Files are unmodified reference excerpts of the upstream project, preserving relative paths. This subset is not an installable standalone package. The file inventory records exact upstream URLs, byte counts, SHA256, and destination paths. No source was installed/imported, no fixture was parsed by PyDYNA, and no solver was run in this collection.

codegen/kwd.json is the full upstream JSON (not a handpicked keyword subset). codegen/README.md describes it as machine-generated from an LS-DYNA manual; manifest.json and additional-cards.json supply corrections/supplements. The upstream snapshot does not identify a complete R17 field support guarantee. The MIT repository snapshot and commercial vendor PDFs have different provenance and distribution conditions; no vendor manual PDF or full page text is included here.

The kwd.json file is retained for the downloadable reference archive, not public Git staging, per integration policy. The remaining source subset is for code reading and asset evaluation; dependency/runtime compatibility is untested.

tests/testfiles/*.k are parser/transform/parameter fixtures. base.k has zero material/section references and is not a complete validated structural model. The transform fixture deliberately contains short/degenerate connectivity cases. Undefined parameter and collision fixtures are useful negative/semantic examples, not solver-certified valid inputs. Test assertions remain upstream evidence only; this research did not execute them.
