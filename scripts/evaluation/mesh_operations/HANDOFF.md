# N18 pure candidate checkpoint — frozen preparation, not feature completion

2026-11-02. Parent requested a coherent WIP checkpoint before core/UI integration. All files are isolated in this directory; no shared repository, core/session, UI or documentation file was edited. Source API baseline inspected: `/caelab-prep-relations` commit `65ff8803c15872974a90a62004e6b65833dd65e9`.

## Implemented

`mesh_operations.py` is a reusable pure Python module with no Qt, VTK, CAD SDK, solver, filesystem or document mutation. An immutable source snapshot is shared by a candidate; only node/cell/set updates, removals and explicit mappings are stored as deltas. Snapshot construction itself still uses per-entity Python records/indexes; this is not the million-element N17 memory solution.

The candidate preserves source document UUID/revision, opaque session epoch string, resource state tokens and mesh generations, plus a source digest. `assert_current` refuses stale generation/token/revision/epoch even when native IDs match. The core owner identified the initial int-epoch mismatch; it was corrected to the real PrepSession UUID-string contract and covered by a same-document/revision reopen regression.

Five fixed operation families are present:

1. Absolute node-coordinate move in explicitly matching source units.
2. Explicit source→keeper tolerance merge. No global closest-node search, chain/cycle mapping, implicit midpoint or unrequested merge. Source/resource, component and contact-side crossings require exact additional approvals. The exact tolerance/approvals are retained.
3. Element deletion with explicit keep/delete-new-orphans policy. Existing orphan nodes survive; beam orientation-only nodes count as referenced geometry.
4. SH3N/SHELL normal reversal with fixed connectivity ordering. Implicit reversal through a coordinate/merge edit is rejected.
5. Element→part reassignment and explicit set replacement are separate commands, with compatible target families and typed memberships.

Size-change/remesh is the sixth family and remains in the existing CAD worker/session integration. It is not implemented by this module.

Quality previews retain before/after values for affected cells. Checks include typed connectivity, duplicates, finite coordinates, line/beam orientation, tri/tet mean ratio and signed tet volume, planar quad corner Jacobians, BRICK8 trilinear Jacobians at 27 points, 8-Gauss integrated volume and outward face orientation. Hex math is adapted from the internally authored `audit/structured-recipes-f2-independent/independent_oracle.py`; the new tests use distinct fixed mesh fixtures and analytical expectations. Twenty-seven samples are a bounded check, not proof of positive Jacobian everywhere for arbitrary warped geometry. Warped quads outside the current planar quality profile are explicitly refused.

Reference previews report affected explicit sets/conditions, old/surviving/proposed cardinalities, contact/normal/material-axis/component review needs and per-node load resultants if the proposed mapping were accepted. They deliberately retain original raw set membership. A successful pure candidate is not safe native output until stale references are explicitly reconnected and physical/component rules revalidated by the session adapter.

## Actual tests

Command:

```sh
python -m pytest -q /workspace/scratch/acd284e248ea/audit/mesh-operations-prototype/test_mesh_operations.py
```

Final result: **15 passed in 0.10 seconds**, preserved in `pytest-final.log`.

Two authored fixed inputs:

- Shell/contact fixture: 13 nodes, four cells (three quads and one triangle), three parts, shared boundary nodes, a second resource with coincident coordinates and repeated local IDs, five explicit sets and load/contact/material-axis dependencies.
- Mixed fixture: 13 nodes, one BRICK8, one TETRA4, one BEAM and one TRUSS, three parts, two sets and load/material-axis dependencies. The beam has a separate orientation node. Both inputs include a pre-existing orphan.

Tests cover scoped same-ID preservation; sparse updates; units/no-op/nonfinite/closure refusal; exact tolerance/keeper/chained-merge boundaries; cross-resource/contact approval; duplicate-node collapse; newly orphaned versus pre-existing nodes; analytic shell reversal; part/set distinction; load cardinality/resultant changes without transfer; stale session/token/generation; beam orientation collapse; tet inversion; and a folded Hex whose **positive integrated volume is 13/40 while a local Jacobian is negative**. The latter is rejected, so total volume alone cannot falsely qualify it.

The tests and module were authored by this agent. A separate core owner reviewed API compatibility and supplied the epoch correction; no non-author full implementation review or independent rerun has been claimed. The attempted additional child assignment returned `agent thread limit reached`.

## Required before product adoption

- A native adapter must build the complete reference closure from canonical resources. `mesh_view` alone is insufficient: it intentionally omits BEAM orientation-only n3 and does not prove opaque native references are understood. Unknown relevant references must block snapshot creation.
- The adapter must verify/recompute the plan against exact owner stamps, then atomically commit coordinate/connectivity/part/set updates and stale-target metadata in one document command. Source-native header/line ownership, cross-resource writes, Undo/Redo, serialization and native reread are unimplemented here.
- Existing conditions need component/formulation/material-axis validation, explicit reconnect/exclude behavior and export guards. Per-node load arithmetic is a preview, not a solver load-transfer method.
- GUI preview/apply/cancel, document-switch/draft/busy ownership, affected-element selection and all eight presentations remain unconnected.
- Existing CAD worker size-remesh/candidate replacement and actual geometry correspondence remain unconnected. No closest-position or same-ID automatic reconnect may be added as a shortcut.
- Current quality profiles need independent review on the supported native families before adoption. No performance, Windows, actual solver, project roundtrip or whole-N18 completion is claimed.

Files are frozen for parent-owned checkpoint publication. `API.md` describes the callable contract; `fixtures.json` stores the exact small input records; `candidate-evidence.json` preserves representative sparse candidate/quality/impact outcomes; `manifest.json` identifies the frozen files.
