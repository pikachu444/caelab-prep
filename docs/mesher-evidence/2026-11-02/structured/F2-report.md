# Fixed F2 structured-recipe evaluation

Date: 2026-11-02. This is an independent, finite SDK experiment. It does not establish product adoption, a generated native workflow, Windows behavior, general mesher robustness, or commercial equivalence.

**Verdict:** quad and straight sweep/Hex8 pass the locked 5-supported + 1-unsupported family gate. The combined line/arc family still fails: initially all three arc cases exceeded the ideal seed-coordinate tolerance; a justified SDK integration-precision correction made one pass, while two still fail. Latest per-input evidence is 16 passes and 2 failures, with only the affected arcs rerun. The failure is retained; no threshold or input was relaxed.

## Locks and evidence

- Original recipe: `996274c2511fd6ba71bed27066aaad42f93d01242ca4d7cda7c1f7161847b841`. H-U1 accepted an unsupported 30-degree twist and produced a straight 192-Hex8 mesh; exit 0. See `original-H-U1/result.json` and the preserved mesh/report.
- Corrected strict recipe: `89f14c423f7fd2604e75c6e952f3a03e3f259985c6e8bf68149d11827ebd83eb`. Unknown semantic fields are rejected. H-U1 alone was repeated; the other 17 cases were executed for the first time.
- The input and contract SHA values were sent to the implementation owner before SDK execution. Normal N3 and difficult D2 in each family were withheld until recipe freeze. [input-lock.json](../../../../scripts/evaluation/structured_f2/input-lock.json) records the three SHA values.
- `frozen-strict/source-lock.json` records the exact recipe, oracle, runner, public/holdout input and contract hashes. Each case has `case.json` and `independent-result.json`; generated supported cases also retain SDK output/report/log and mesh. Unsupported rejections produce no mesh. No product files were changed by this evaluation.

## Predetermined checks

The 30-second gate includes a fresh process, recipe import, SDK initialization, generation, MSH write/reopen and independent verification. Gmsh 4.15.2 ran with one requested thread. The independent checker parses ASCII MSH4.1 directly; it imports no Gmsh or recipe geometry helpers.

Exact source lattice nodes/cells, first-order family, connectivity/order, physical partitions and common node IDs are checked. Quad edges and hex faces have one boundary or two opposite incidences; exact conforming lattices leave no hanging nodes in this bounded family. Quad corner signed scaled Jacobian must be at least 0.30, with edge aspect at most 8. Hex8 must have positive Jacobians and scaled Jacobian at least 0.25 at 27 parametric samples, with edge aspect at most 10. Volume uses independent 2×2×2 Gauss quadrature. These are initial prepared-family gates, not official engineering standards or a validity certificate for arbitrary hexes. SDK minSICN remains a separate reported quantity.

Coordinate tolerance is `1e-9 × characteristic length`; for an arc the characteristic length is its radius. Arc angle tolerance is separately `1e-8 rad`. Analytic measure relative tolerance is `1e-9`. Arc polygon length is compared with `2 N R sin(theta / 2N)`, and true arc length `R theta` is recorded separately.

## Initial fixed 18-case run

| Case | Holdout | Result | Top cells / active nodes | Independent min scaled J | SDK minSICN | Wall seconds |
|---|---:|---|---:|---:|---:|---:|
| H-D1 | no | supported_pass | 360 / 546 | 0.769484 | 0.706058 | 0.5045 |
| H-D2 | yes | supported_pass | 525 / 768 | 0.801263 | 0.703456 | 0.6551 |
| H-N1 | no | supported_pass | 192 / 315 | 1.000000 | 1.000000 | 0.3347 |
| H-N2 | no | supported_pass | 234 / 392 | 1.000000 | 1.000000 | 0.3792 |
| H-N3 | yes | supported_pass | 225 / 360 | 0.975900 | 0.810866 | 0.3563 |
| H-U1 | no | unsupported_rejected | rejected | — | — | 0.1410 |
| L-D1 | no | failure | 35 / 36 | — | — | 0.1690 |
| L-D2 | yes | failure | 19 / 20 | — | — | 0.1734 |
| L-N1 | no | supported_pass | 8 / 9 | — | — | 0.1644 |
| L-N2 | no | failure | 16 / 17 | — | — | 0.1566 |
| L-N3 | yes | supported_pass | 17 / 18 | — | — | 0.1193 |
| L-U1 | no | unsupported_rejected | rejected | — | — | 0.1589 |
| Q-D1 | no | supported_pass | 126 / 152 | 0.868243 | 0.752881 | 0.1682 |
| Q-D2 | yes | supported_pass | 68 / 90 | 0.808736 | 0.745342 | 0.1718 |
| Q-N1 | no | supported_pass | 48 / 63 | 1.000000 | 0.923077 | 0.1636 |
| Q-N2 | no | supported_pass | 78 / 98 | 1.000000 | 1.000000 | 0.1767 |
| Q-N3 | yes | supported_pass | 45 / 60 | 1.000000 | 1.000000 | 0.1332 |
| Q-U1 | no | unsupported_rejected | rejected | — | — | 0.1503 |

Counts in failed arc rows were independently confirmed in the diagnostic; they do not turn the coordinate failure into a pass. All 15 supported SDK calls reported zero errors and warnings. Quad minimum independent scaled Jacobian is 0.808736; Hex8 minimum is 0.769484. The largest supported quad/hex analytic measure relative error is 7.20e-15. Observed case wall times were 0.1193–0.6551 seconds; these small cases do not establish product performance.

Shared topology passed with actual shared node IDs: Q-N2 6 edges/7 nodes; Q-D2 4 edges/5 nodes; H-N2 18 faces/28 nodes; H-D2 35 faces/48 nodes. Each pair had disjoint, exhaustive physical groups 110/111 and opposite interface incidence directions.

## Arc failures retained

| Case | Maximum ideal seed-position error | Locked coordinate tolerance | Ratio | Maximum angle error |
|---|---:|---:|---:|---:|
| L-N2 | 2.19252132e-08 mm | 1e-08 mm | 2.19252 | 2.19252128e-09 rad |
| L-D1 | 5.15050234e-08 mm | 1.2e-08 mm | 4.29209 | 4.29208535e-09 rad |
| L-D2 | 8.36367298e-07 mm | 3.2e-07 mm | 2.61365 | 2.61364731e-09 rad |

All three failures have correct cell/active-node counts, an ordered chain with the intended native node connectivity, physical source 110, and the requested circle/plane. Maximum radius error is 5.06e-12 mm, maximum plane error 4.30e-12 mm, and maximum polygon-length relative error 2.72e-13. Those observations localize the measured failure to the tighter ideal seed-position gate; they do not identify its SDK cause. No coordinate snapping, tolerance change, input replacement or extra SDK campaign was performed. The implementation owner then changed only the arc-specific SDK integration setting; the affected rerun below retains this initial failure.

## One affected numerical-precision rerun

Recipe SHA `e13741a912e8e890057172a1240548b8dbd3edaa38dde73cb521e33303794a0f` differs from the strict recipe only by setting `Mesh.LcIntegrationPrecision=1e-12` for arc mode and reporting the effective option value. The source diff was independently checked. The original input files, coordinate/angle/measure/quality/time gates, checker and output coordinates were unchanged. No coordinate snapping was applied.

Only L-N2, L-D1 and L-D2 were rerun, once each. See `arc-precision-retry/source-lock.json`, `summary.json` and each case result/mesh. The retry is an affected regression, not a new blind holdout run. No already-passing case was regenerated.

| Case | Latest maximum seed-position error | Unchanged tolerance | Latest result | Wall seconds |
|---|---:|---:|---|---:|
| L-N2 | 2.30200601e-08 mm | 1e-08 mm | failure | 0.1719 |
| L-D1 | 5.13369879e-08 mm | 1.2e-08 mm | failure | 0.1466 |
| L-D2 | 1.32620989e-07 mm | 3.2e-07 mm | supported_pass | 0.6200 |

The correction reduces the translated small-angle holdout error below its locked gate, but does not resolve the quarter-circle or 175-degree arc. Their shape, chain order and chord length remain correct; their tighter ideal seed-position gate still fails. This observation does not establish a full SDK root cause. Additional blind option searches were stopped. Line/arc therefore has 3/5 supported passes and 1/1 safe unsupported rejection and is not F2-admitted as a family. Quad and sweep/Hex8 retain 5/5 supported passes and 1/1 safe rejection each.

## Native mapping feasibility and boundary

This evaluation only read existing project-native code and fixtures; it did not export these generated meshes or run a solver. The existing prepared native tests are evidence for a possible target representation, not F3 completion of these recipes.

| Generated family | Existing target representation | Required meaning and scope |
|---|---|---|
| Gmsh type 1, line2 | `/TRUSS` with `/PROP/TRUSS` or TYPE2; `/BEAM` with `/PROP/BEAM` or TYPE3 | Explicit mechanical family/section choice. BEAM requires supported small-strain profile, positive section/inertias, release flags and an orientation definition; these cannot be inferred from a render line. |
| Gmsh type 3, quad4 | `/SHELL`, cyclic four-node order; `/PROP/SHELL` or TYPE1 | Explicit thickness/formulation and consistent normal. Supported relation profiles are checked in native code. |
| Gmsh type 5, hex8 | `/BRICK`, bottom cyclic four nodes followed by corresponding top four; `/PROP/SOLID` or TYPE14 | Linear brick Isolid=1 is the existing verified relation profile. |

Read-only references in the relations checkout (HEAD `8c1a67f6b5a8d60c81124073be55dde1aafe4176` at inspection): `src/caelab_prep/radioss/deck.py:491`, `src/caelab_prep/radioss/relations.py:105`, `:107`, `:125`, `:138`; `scripts/evaluation/models/mixed-assemblies/{beam_shell_tet,truss_shell_hex}/{model_0000.rad,mesh.inc}`; `tests/test_mixed_relations.py:155`. That opt-in test checks prepared native component counts and masses plus short Starter/Engine termination; its own docstring excludes a coupling oracle. `docs/solver-input-assets/2026-10-30/followup/rad/GUIDE.md` distinguishes writer references and solver reader source from a complete schema.

## Limits and next decision

Quad and straight sweep/Hex8 may proceed to F3 for these exact one/two-patch prepared families. Curved/nonplanar faces, holes, annuli, concavity, twist, arbitrary patch assemblies, adaptive/local remeshing and hybrid transitions remain outside this result. The combined line/arc gate remains failed because two original inputs still miss the same tolerance after the single justified correction. No broader product connection for this combined family is admitted by this result. Full generated-native mapping, user choices, selections/conditions, Undo, save/reopen/export and real Windows behavior remain F3 work.

A separate read-only oracle review found no mathematical blocker for the fixed 18 inputs. It noted an unused parser robustness edge: an initial zero-element MSH block would reference an unset local variable. None of these outputs contains that block, so no result depends on it; broad parser reuse should correct it before admitting other files.
