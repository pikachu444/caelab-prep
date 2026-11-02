# F2 addendum: bounded OpenCASCADE arc recipe

This addendum supersedes the current-status conclusion of `F2-report.md` while retaining that report and every original failure unchanged. Date: 2026-11-02.

**Latest per-input F2 evidence: 18/18 pass.** Each family has five supported passes and one safe unsupported rejection. Only the three affected arc inputs were rerun locally on the latest recipe; the other fifteen results are retained from unchanged code paths. This is not a claim that all eighteen ran locally on the latest SHA.

## Exact change and unchanged gates

- Latest recipe SHA256: `8ebf10dc5f97536896744199993c7f3df6396f3b1da89461223b908bfabd954a`.
- Arc geometry construction alone changed from Gmsh built-in `geo.addCircleArc` to `occ.addCircleArc`, followed by `occ.synchronize()` and `model.mesh.setTransfiniteCurve`. The recipe reports `geometry_kernel=OpenCASCADE` for arcs. Other geometry paths remain unchanged.
- The arc integration precision remains `Mesh.LcIntegrationPrecision=1e-12`. No coordinates, seeds, tolerances, quality thresholds, node postprocessing or independent oracle changed. The original input/contract hashes and oracle SHA still match.
- This is a bounded second backend recipe, not an open-ended option search. The implementation owner supplied source-based reasoning for the change. This independent evaluation verifies its diff and measured result; it does not claim to have proved every internal numerical cause.

## Same three affected inputs, one run each

| Input | Result | Line cells / active nodes | Maximum ideal seed error | Unchanged tolerance | Wall seconds |
|---|---|---:|---:|---:|---:|
| L-N2 | pass | 16 / 17 | 2.22044605e-14 mm | 1e-08 mm | 0.1568 |
| L-D1 | pass | 35 / 36 | 2.27484671e-14 mm | 1.2e-08 mm | 0.1382 |
| L-D2 | pass | 19 / 20 | 7.49988544e-12 mm | 3.2e-07 mm | 0.1661 |

Each output also passed its ordered single-chain connectivity, exact prescribed lattice and node count, circle/plane, physical source, analytic chord sum and time limit checks. Maximum chord-length relative error is 2.71e-13. All three SDK calls reported zero errors and warnings. The unused circle-center construction node is a 0D entity, excluded from active-node counts by the preregistered contract.

Artifacts: `arc-occ-retry/source-lock.json`, `summary.json`, and each case directory retain the input, mesh, SDK report and independent result. `occ-final-verdict.json` maps every final input result to its actual evidence stage. The earlier unsupported-twist failure, three original arc failures and partial precision-only correction remain in their original directories.

The six initial holdouts were withheld before the first recipe freeze. These affected reruns are regressions on the fixed inputs, not fresh blind holdout evaluations.

## Product boundary and portable CI harness

This permits F3 work only for the locked family: straight line/unique short arc; one or exactly two explicit-edge-sharing convex planar quads; and their common positive straight, possibly oblique extrusion. Curved source surfaces, holes, annuli, concavity, twist, arbitrary patch assemblies and hybrid transitions remain outside this evidence. Generated-native mapping, material/section/BEAM orientation choices, document/UI/Undo/save/export and Windows require F3 work.

`ci_bundle/` contains byte-identical locked inputs, contract and independent oracle plus `verify_f2.py`. It pins the latest recipe and the original input/oracle hashes, runs all eighteen by default or an explicit `--cases` subset, isolates each in a fresh process, enforces the 30-second limit, preserves reports and exits nonzero on failure. The new portable wrapper was syntax/help checked only; its full SDK run is assigned to CI. Local affected results above used the existing audited harness and unchanged oracle.

Example (from an environment with Gmsh 4.15.2 installed):

```sh
python ci_bundle/verify_f2.py --recipe structured_recipes.py --output f2-evidence
```

No product source, tests or documentation were edited by this evaluator. No additional SDK parameter search or local whole-campaign repetition was performed.
