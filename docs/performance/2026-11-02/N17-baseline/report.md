# N17 baseline — 2026-11-02

Read-only product baseline: Prep `0aaada402eaa10d8e45df21995d6c6d88a4711c9`, archived `snapshot/src`. No product changes in this measurement.

Actual deterministic input: 1,000,000 quad elements, 1,020,100 nodes, 100 parts, 20 native resources including the root file; 123,436,236 input bytes. No actor duplication is used. Generator and file hashes are in `generate.py` and `input-manifest.json`. This is a large-model geometry/I/O baseline, not mixed-assembly or solver-physics validation.

Environment: Linux 6.18.57 x86_64, AMD EPYC 9V74, cgroup quota 8 CPU / 8 GiB RAM, Python 3.12.14, PySide6 6.12.0, VTK 9.4.2, NumPy 2.3.5. Real Qt xcb + task-local Xvfb 1920×1080 / `vtkXOpenGLRenderWindow`; software OpenGL (`LP_NUM_THREADS=2`, `OMP_NUM_THREADS=2`). Generated-file cache was warm. This is not the proposed Windows 11 / 32 GiB / physical GPU reference environment.

Safety guards: process RSS 5 GiB, virtual address space 6 GiB, cgroup anonymous+kernel memory 7 GiB. They are environment-protection limits, not changes to the documented 12/16 GiB product budgets. No guard fired.

| Measurement | Result | Meaning |
|---|---:|---|
| Raw read + SHA256 | 0.098 s | Warm file reads; separate from parsing |
| Open native source, core + first projection | 13.717 s | No renderer included |
| Cached mesh_view, first returned copy | 4.508 s | Additional full container copy |
| Cached mesh_view, second simultaneous copy | 5.066 s | First returned copy remains alive |
| Save project | 2.096 s | Atomic project save, no live renderer |
| Reopen project, core + first projection | 13.453 s | Same process, no renderer included |
| Construct/show/render production window | 15.510 s | On the reopened document; not added to source-open as an independent acceptance result |
| Repeat actual render | 0.490 s | Synchronous VTK render |
| Save with live renderer | 2.152 s | Same active document |

| Fixed 100-operation sequence | p95 | Boundary |
|---|---:|---|
| Core scalar edit | 0.12 ms | API only |
| Core Undo | 0.11 ms | API only |
| Core element selection | 95.24 ms | API only |
| Command → queued Qt selection | 978.05 ms | Canonical command through actual UI/render; excludes physical input dispatch |
| Command → queued Qt scalar edit | 943.36 ms | Canonical command through actual UI/render |
| Command → queued Qt Undo | 1022.84 ms | Canonical command through actual UI/render |
| Hide one part + show all, per pair | 4221.11 ms | 100 pairs; individual hide/show p95 not separately recorded |

Process high-water RSS: 4,177,833,984 bytes (3.891 GiB); 50 ms sampled maximum 4,154,966,016 bytes. No CAD/meshing worker ran, and a synchronized app+worker process-tree total was not measured. Xvfb/runner overhead is separate from the app RSS.

Copies were verified by object identity: points rows, cell dictionaries, connectivity lists, part-reference dictionaries, node-owner mappings/lists all differ between the cache and returned copies. Each cache/returned projection holds 790,539,040 bytes of measured container objects, excluding numeric/string scalar objects, raw text and allocator overhead. Logical numeric payload alone is 72,643,200 bytes.

Confirmed baseline misses: UI selection p95 978 ms versus 150 ms target; scalar 943 ms and Undo 1,023 ms versus 100 ms targets. The hide+show pair is slow (4.221 s p95) but its two individual p95 values were not measured. Opening/saving figures above are component measurements and do not by themselves certify the full user-input-to-ready B5 budget. Cancellation was not measured.

First attempt: `attempt-1-diagnostic-reference-retained/` is preserved. It was manually stopped when a diagnostic variable retained the previous projection across reopen, and its Qt event pump did not explicitly flush DeferredDelete. Later RSS/UI figures from that attempt are excluded from the final baseline. The corrected run removed that reference and flushed DeferredDelete; it completed with exit 0 in 699.76 s. No input-size reduction occurred.

Source findings (baseline): session.mesh_view rebuilds returned containers on every call; part references occupy one dict per cell. Element lookup and viewport highlight preparation scan every cell. Visibility performs full extraction on every hide/show. Scalar refresh re-renders unchanged geometry. Follow-up implementation is separate from this archived baseline.

Evidence: `events.jsonl`, `guard.json`, `console.log`, `million-native-window.png`, `million.caelab`, `snapshot/src`; generator and harness are beside this report.
