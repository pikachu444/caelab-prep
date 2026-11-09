# N17 follow-up — improvements measured; acceptance incomplete

Frozen source: base `976ad7c01ce37097feb779c6acdd4fd3a2de6894` plus the approved working-tree files captured in `snapshot/src`; exact SHA256 list is in `source-manifest.json`, with tracked changes in `product-diff.patch`. No live working-tree file was imported during the run.

Same generated input and environment as `../N17-baseline/report.md`: 1,000,000 actual quad elements, 1,020,100 nodes, 100 parts and 20 native source resources; Qt xcb/Xvfb 1920×1080, software OpenGL, LP/OMP threads 2, 8-CPU quota and 8 GiB cgroup. The HyperMesh presentation was used. No original commercial application or Windows machine was involved. Input hashes match the baseline.

The corrected baseline and this follow-up both completed without the memory or time protection guards firing. The earlier diagnostic-reference-retention attempt remains excluded. The follow-up completed with exit 0 in 283.48 s.

| Component | Before | After |
|---|---:|---:|
| Core source open + first projection | 13.717 s | 21.065 s |
| Cached mesh_view return 1 | 4.508 s | 35.99 µs |
| Cached mesh_view return 2 | 5.066 s | 22.24 µs |
| Project save | 2.096 s | 2.325 s |
| Core project reopen + first projection | 13.453 s | 22.123 s |
| Construct/show/render actual window | 15.510 s | 9.728 s |
| Repeat actual render | 0.490 s | 0.622 s |
| Save with active renderer | 2.152 s | 2.174 s |

| Fixed 100-operation p95 | Before | After | Proposed target |
|---|---:|---:|---:|
| Core element selection | 95.24 ms | 1.42 ms | API component only |
| Command through Qt selection | 978.05 ms | 773.44 ms | 150 ms |
| Command through Qt scalar edit | 943.36 ms | 126.33 ms | 100 ms |
| Command through Qt Undo | 1022.84 ms | 129.81 ms | 100 ms |
| Hide + show, complete pair | 4221.11 ms | 1462.46 ms | Individual calls measured below |

After-only individual measurements: hide p95 **723.75 ms**, show p95 **749.98 ms**, each 100 calls including queued Qt work and rendering. Both exceed the proposed 200 ms target in this environment.

Observed app RSS maximum: **3,676,090,368 bytes (3.424 GiB)** versus baseline 3.891 GiB. The app was the only product process; no meshing worker ran. A synchronized app+worker total was not measured. Core steady-state RSS after opening increased from 1.605 GB to 2.295 GB while later repeated-return and viewport peaks decreased; memory did not improve uniformly.

The geometry returned by both cached mesh_view calls shares the exact point rows, cell mappings, connectivity, part-reference mappings and node-owner containers with the canonical cache. Measured calls dropped from seconds to tens of microseconds. The shallow container-size dump is retained for transparency but must not be summed as independent allocations in the shared version, and proxy sizes do not include their backing mappings.

Viewport changes retain actual NumPy numeric buffers used by VTK, build typed-reference reverse indexes, cache per-part geometry, change only affected visible blocks, and build highlights from selected cells only. Scalar revision/token refresh reuses the same highlight pipeline. Empty selection/document replacement releases the previous VTK ownership.

Verification: 11 focused visibility/scaling checks including real offscreen cell/node picks; 2 native X11 window tests at 1920×1080 and 960×640, using real Qt mouse input and VTK picking. Separate independent review found no additional blocker in small line/triangle/tetra/hex, unsupported-cell omission, empty-document or hide cases. These checks do not replace the large-model timings.

The initial displayed PNG is byte-identical to the baseline (`20a1db3e81c7fd7024dcf12e84ccfe96b20bede27bc975973abbb38b8f4d6cea`); the actual rendered cell count remains 1,000,000. No lower-detail mesh or actor-count substitute was used.

Remaining limits: the four UI p95 targets are still exceeded. Initial source/project-open components became slower, while viewport construction became faster; end-to-end open readiness was not separately measured and component sums are not acceptance evidence. Full-frame software rendering remains expensive (0.622 s observed), but its exact contribution to every UI operation was not instrumented. Cancellation, native Windows/reference GPU, cold file-cache behavior and a simultaneous worker are unverified. Mixed-assembly physics is outside this performance fixture.

Next work should profile the remaining Qt refresh and actual render portions, reduce initial immutable-conversion/index ownership costs where measured, and validate on the declared reference platform. This report does not mark N17/B5 complete or change any original budget.

Evidence: `events.jsonl`, `guard.json`, `console.log`, `million-native-window.png`, the two saved projects, source snapshot/hash manifest, and harness. Original baseline and its excluded first attempt remain preserved separately.
