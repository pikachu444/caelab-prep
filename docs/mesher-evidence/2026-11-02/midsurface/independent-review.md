# Independent review: N23 bounded paired-face experiment

Reviewed 2026-11-02 by a non-author agent. Verdict: **PASS for the two fixed synthetic midpoint fixtures; no blocker found for that claim.** This is not qualification of generic extraction, the complete F1/F2 gate, or N23.

The original `paired_offset.py` and `run_f1.py` were copied without edits from `../midsurface-f1/` into this independent directory. The original evidence and product files were not modified. The independent invocation was equivalent to:

```sh
cd /workspace/scratch/acd284e248ea/audit/midsurface-f1-review
/workspace/scratch/acd284e248ea/envs/g3-gmsh/bin/python run_f1.py > rerun.log 2>&1
```

The invocation used `subprocess.run(..., timeout=120)`. It exited **0**, with measured wall time **2.12317620000249 seconds** (including process startup/imports) and peak RSS **428.6328125 MiB**. Detailed independent output is `results/result.json`; stdout/stderr is `rerun.log`.

The independent run reproduced all four original source/candidate SHA-256 values:

| Fixture | Source BRep SHA-256 | Candidate BRep SHA-256 |
|---|---|---|
| Plate | `fcd5c3b19cc01fe19bd4387debe66b4ebddfa9c67b3ba6e8994b6dc9150c8499` | `ab52d09810c0c40c795128ed92e9f6c227641fc4994d0f451550993ad3592dda` |
| Rounded L | `48d59575dd900a7c6a4f175c8eb53c7fe899b0d2ffbe3d366c4fcd4cc7941bfe` | `a10a49181632a895f67d4266632d7cedb4c0d9dcfc62868c797dd7904e3699ed` |

Both midpoint fixtures passed the dimensional, area, normal-ray thickness, boundary, shared-edge/tangency, topology, source immutability, and saved/reopened candidate checks. All six declared invalid inputs were rejected while preserving both source BRep bytes and an existing candidate output: tapered wedge, sharp junction, incorrect declared thickness, missing explicit bend pair, out-of-wall offset, and undeclared units.

Code review confirmed actual deep-copy, OCCT offset, Boolean common, and sewing operations in `paired_offset.py:147–168`; fixture-specific postconditions and reopen checks are in `run_f1.py:69–111` and `131–139`. Those detailed numerical postconditions are in the fixed fixture runner, not a universal validation layer inside `extract`. This evidence must not be generalized to all otherwise accepted inputs.

One reporting correction was requested: the original HANDOFF's “All checks … saved/reopened” needed to refer specifically to the two midpoint fixtures, because the separate quarter-offset reference check does not reopen its file. The author reports that wording corrected; no experiment code change or additional run was required.

Official-example reproduction, the full fixed F2 set, automatic pairing, ribs/junctions/variable thickness, general robustness, document identity, GUI adoption, meshing, shell/native mapping, project roundtrip, solver readback, and Windows/commercial-product validation remain outside this demonstrated result.
