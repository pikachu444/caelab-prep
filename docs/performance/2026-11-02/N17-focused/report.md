# N17 focused bottleneck diagnosis — 2026-11-02

The remaining GUI selection and visibility cost is dominated by actual VTK frame generation in this Linux software-rendering environment. Scalar edits and Undo do not render, but repeatedly query the same property context and rebuild the inspector. Initial open was dominated by generic recursive immutable conversion; the separately measured owned-payload conversion reduced core open and memory substantially. **These measurements do not close N17/B5 or replace the fixed acceptance budgets.**

## Scope and reproducibility

- Same deterministic input as [the baseline](../N17-baseline/report.md): **1,000,000 actual quad elements, 1,020,100 nodes, 100 parts, 20 native source resources, 123,436,236 native input bytes**. No element-count reduction or actor replication.
- Core-before and the initial GUI run used the frozen source under [N17-after/snapshot](../N17-after/snapshot/) with [its source hashes](../N17-after/source-manifest.json). Core-after used a separate snapshot of base `969b488762d32d4c007e41f781bfaf263ed3f92b` plus working-tree changes, pinned by [seal-after/source-manifest.json](seal-after/source-manifest.json). The snapshots differ; The initial GUI results are **not** measurements of the new owned-payload conversion. A separate follow-up snapshot and GUI run are recorded below.
- Linux/Xvfb with actual `vtkXOpenGLRenderWindow`, PySide6 6.12.0, VTK 9.4.2, Python 3.12.14, software OpenGL, `LP_NUM_THREADS=2`, `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=1`. The parent [full-run report](../N17-after/report.md) records the environment. This is not Windows or a physical reference GPU.
- Instrumentation wraps original method bodies and adds timers to `mesh_view`; the original computation runs. Actual VTK `StartEvent`/`EndEvent` observers record complete render-window frames. Qt events and deferred deletes are processed before each operation ends. No asynchronous first-response substitute, disabled rendering, or reduced geometry.
- Eight diagnostic trials per GUI operation, three direct-render trials. Means/medians below locate costs; they are **not the 100-operation p95 acceptance campaign**. Nested inclusive times overlap and must not be added together.
- Memory guards were RSS 5 GiB / virtual address space 6 GiB / cgroup anonymous-plus-kernel 7 GiB to protect the 8 GiB environment. No guard triggered. These limits do not lower the product's reference budgets.

## Core open decomposition

Seconds, one core-open measurement per exact snapshot:

| Phase | Generic recursive conversion | Owned-payload conversion |
|---|---:|---:|
| Whole core open | 20.013310 | 12.083846 |
| DeckResource construction/layout, summed across 20 resources | 1.681844 | 1.688719 |
| Native parse + merge | 5.923770 | 5.995440 |
| Connectivity validation + node sort | 0.414125 | 0.404933 |
| PART-reference resolution | 0.360497 | 0.072046 |
| Immutable payload conversion | 10.347729 | 1.890149 |
| Index build | 0.219819 | 1.011045 |
| Steady RSS after open, bytes | 2,290,503,680 | 1,583,603,712 |
| Process high-water RSS, bytes | 2,642,669,568 | 1,625,366,528 |

The conversion and shared PART references account for the observed reduction. **Index construction increased by approximately 0.79 s** in this run, so not every phase improved. The parse-and-merge stage remained similar. A single timed run cannot establish variance or a universal speedup.

The parent's change seals only newly built, privately owned projection data: private cell dictionaries are wrapped without copying, connectivity becomes tuples, PART references are shared per PART, node-owner tuples are interned, and the generic recursive `readonly` helper remains unchanged for caller-owned data. After-run assertions checked the real million-cell count, cached cell identity, shared PART/owner identities, and rejection of nested mutation. This validates the intended ownership contract for this run, not every external caller.

Evidence: [before events](events.jsonl), [before instrumentation](instrumented_mesh_view.py), [after events](seal-after/events.jsonl), [after instrumentation](seal-after/instrumented_mesh_view.py), [after guard](seal-after/guard.json). The before harness completed and emitted all core measurements, then failed before GUI because its diagnostic import used `RadPropertyProvider` instead of `RadProvider`; its process exit was 1. The corrected independent GUI run exited 0. No product defect is inferred from that harness typo. The after envelope retains a copied generic scope string referring to the prior snapshot; its actual source path and hashes are the separate `seal-after` snapshot and manifest stated above.

## GUI cost decomposition

Milliseconds per operation; all numbers below use the old frozen N17-after snapshot.

| Operation | Trials | Mean total | Median total | Mean actual VTK frame time | Frames per operation |
|---|---:|---:|---:|---:|---:|
| Selection + complete Qt refresh | 8 | 692.556 | 673.538 | 591.950 | 1 |
| Scalar edit + complete Qt refresh | 8 | 105.455 | 102.910 | 0 | 0 |
| Undo + complete Qt refresh | 8 | 105.136 | 102.683 | 0 | 0 |
| Hide one PART, then show all | 8 | 1,233.522 | 1,218.914 | 1,229.504 | 2 |
| Direct full render | 3 | 536.802 | 535.225 | 536.674 | 1 |

Actual rendering accounts for approximately **85.5% of selection** and **99.7% of the hide/show pair**. The measured selection-index lookup is approximately 0.01 ms; replacing that lookup again cannot explain away the frame cost. A hide/show pair contains two completed operations and must not be compared directly with the per-operation hide/show budget.

For a scalar edit, inspector field refresh averages 68.527 ms inclusive (25.519 ms self), action refresh 21.794 ms inclusive, and tree refresh 8.725 ms inclusive. `RadProvider.properties` is called **three times**, consuming 60.440 ms inclusive; those calls include three `_assignment_fields` calls consuming 39.343 ms. `available_operations` runs twice, consuming 41.976 ms inclusive, overlapping the property queries. Undo shows the same pattern. These are measured duplicate query and refresh costs, not evidence that rendering occurs on scalar edits.

Evidence: [GUI events](gui/events.jsonl), [per-trial components](gui/components.json), [GUI harness](gui/baseline.py), [GUI guard](gui/guard.json). Corrected GUI process: exit 0, wall 51.514 s, maximum sampled RSS 3,539,890,176 bytes, no guard trigger.

## Concrete next boundaries

1. The provider owner added a narrow PART-only property-context cache. The follow-up below measures assignment lookup dropping from three calls to one. Conditions and draft-dependent force/moment context remain uncached; the owner separately validated assignment/Undo/reopen and caller-mutation behavior.
2. Preserve the completed-frame response criterion. Software frame cost is the remaining selection/visibility bottleneck here. Further rendering work must retain picking, hidden geometry exclusion, selected references and display quality; deferred receipt or reduced element count cannot satisfy the budget.
3. The specialized immutable conversion has a measured core-open benefit. The follow-up adds only a limited GUI diagnostic; no new full 100-operation/open-to-ready/cancel acceptance campaign was run after it. The earlier full 100-operation results remain the acceptance evidence, with their failures and limits.
4. N17/B5 remains open: fixed budgets include selection 150 ms, scalar/Undo 100 ms, hide/show 200 ms, complete open/reopen 45 s, save 60 s, app RSS 12 GiB / app-plus-worker 16 GiB, cancel acknowledgement 1 s and worker exit 5 s. This Linux diagnostic does not establish all those criteria, reference Windows/GPU performance, cold-cache behavior, or app-plus-worker totals.

Our viewport files stayed frozen during this follow-up. Existing viewport validation remains 11 focused tests and two real-X11 native-render cases (1920×1080 and 960×640), including actual picking. This report adds diagnosis and the separately measured core-owned conversion; it does not declare a new product acceptance result.

## Follow-up: PART context cache and explicit project-version migration

A new frozen snapshot at base `8c1a67f6b5a8d60c81124073be55dde1aafe4176` plus working-tree changes was measured after the provider owner reported 95 focused passes/1 skip and 37 migration/source/prepared/case/provider passes. The timing run independently used [the exact source hashes](gui-provider-migrated-after/source-manifest.json); the owner's regression counts are not recounted as tests run by this diagnostic.

The first attempt on this snapshot exposed a format-evolution problem before the GUI started: the original N17-after saved document used an early in-development **version 4** with `source_models` but no `model_relations`; the newer reader required `model_relations` for version 4 and raised `KeyError` wrapped as `invalid_project`. [That snapshot](gui-provider-after/source-manifest.json), [failure log](gui-provider-after/console.log), and [guard result](gui-provider-after/guard.json) remain intact. This is a confirmed failure to read this checkpoint artifact, **not evidence of a released-version-4 user-file regression**.

The owner then made the current format version 5 explicit, added legacy version-4 source-only migration, and retained strict required fields for version 5. This diagnostic waited for the reported migration passes and used a fresh frozen snapshot. The original archive was not edited or replaced with a native import: [fixture.json](gui-provider-migrated-after/fixture.json) records SHA-256 `c4f6bcaac342eab7fbb694d0cfdae931bf07b8899e25a698e20e97465cbe903e`, 13,450,396 bytes. The successful run logged `original_project_version: 4`, `original_has_model_relations: false`, and `current_project_version: 5`, opened the actual million elements, and completed the same GUI operations.

Means in milliseconds; eight diagnostic trials per operation and three direct-render trials:

| Operation/component | Initial frozen GUI | Current frozen GUI |
|---|---:|---:|
| Scalar edit, complete response | 105.455 | 73.066 |
| Undo, complete response | 105.136 | 73.124 |
| Scalar: property-query inclusive time, three calls | 60.440 | 22.920 |
| Scalar: assignment-query inclusive time | 39.343, three calls | 15.222, one call |
| Scalar: inspector field refresh inclusive time | 68.527 | 54.066 |
| Scalar: action refresh inclusive time | 21.794 | 2.398 |
| Selection, complete response | 692.556 | 598.266 |
| Selection: actual frame | 591.950 | 537.807 |
| Hide one PART + show all, complete pair | 1,233.522 | 1,201.031 |
| Hide/show: actual two frames | 1,229.504 | 1,197.942 |
| Direct full render | 536.802 | 523.640 |

Scalar and Undo still generated **zero render frames**. All three property calls still execute, but only one assignment query executes for each refreshed PART context; this directly confirms the narrow reuse behavior. The source snapshot also contains other intervening core/UI changes, including owned-payload conversion and format migration. Consequently the total response-time difference is a comparison of the exact snapshots, not a claim that every millisecond is caused solely by the provider cache. The measured drop in assignment calls and query time is separately observable.

The successful current run exited 0 in 39.851 s; maximum sampled RSS was 2,942,889,984 bytes, with no guard trigger. Core open was 12.301 s and subsequent window construction/show/render 7.746 s; these diagnostic phases do not replace an independently specified end-to-end acceptance measurement. The eight-trial means below 100 ms for scalar/Undo are **not proof of a 100-operation p95 pass**. Selection and visibility still have a large actual-frame cost on software OpenGL.

Evidence: [per-trial components](gui-provider-migrated-after/components.json), [summary](gui-provider-migrated-after/summary.json), [events](gui-provider-migrated-after/events.jsonl), [harness](gui-provider-migrated-after/baseline.py), [guard](gui-provider-migrated-after/guard.json). No viewport product code changed during this follow-up. N17/B5 remains open.
