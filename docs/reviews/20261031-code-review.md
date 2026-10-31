# Independent code and regression-risk review

Candidate: local `feat/shared-gui-foundation`, base HEAD `6a2c96e`, current uncommitted correction source. Read-only review; only this report was written by the reviewer.

Verdict: no outstanding P1/P2 code blocker in the reviewed final candidate. This is source/flow review plus focused offscreen probes, not a claim of completed Windows acceptance.

Reviewed authority: AGENTS.md, README.md, DESIGN.md, original A1-A8 plan, P1-P3 execution stages, Workbench reuse boundary. New RAD/model creation, B/C, solver execution and publication remain outside this review.

Evidence by contract:

- Selection/identity: `application/contracts.py` declares shared SelectionProvider; neutral and RAD implement it. `application/session.py` activates existing native PART relationships, normalizes numeric PART identity for duplicate checks, and derives canonical entity refs. `select_pick` checks document UUID, live epoch, integer document/projection revisions and resource token before delegating to the existing ambiguity-checking `select_entity`. `_install` rotates epoch even when persisted UUIDs repeat. `ui/viewport.py` snapshots these stamps into pick candidates, refreshes scalar-edit tokens without rebuilding geometry, and highlights every approved resource/local-ID pair. `main_window.select_card` now updates the provider as well as the form.
- File/draft/close: both hosts use shared FileEditCoordinator and ActionRegistry. The coordinator prompts before finishing drafts; Discard bypasses validation, Cancel retains input, and Save finishes then invokes the async save continuation. Dialog choosing suppresses scalar focus-loss auto-commit. Failure/cancel paths restore captured text, units, curve drafts and pending selection. Synchronous close accepts its original event; async close waits for successful save.
- Typed reference: neutral PropertySpec exposes real existing curve ObjectRefs and labels. `CurveSession.submit` validates document/resource/kind/existence before serializing the curve ID, clones and validates a complete candidate before Dispatcher, and uses existing Undo/dirty/save behavior. Neutral codec writes version 2 and reads versions 1/2. RAD v1/raw/INCLUDE/CLI paths retain their existing storage and command implementations.
- Visual source: design/tokens.py feeds QSS template, original semantic SVG drawing, numeric/vector/property/tree/table/plot geometry. Added semantic keys have actual SVG paths; RAD categories use their corresponding keys.
- Catalogue: CatalogueWidget exposes selectable asset records with semantic key, purpose, source path, consumer scenes, status, provenance and permissions. Cached per-asset scenes preserve their drafts while browsing. Numeric, vector/unit, tree/property and curve examples use actual shared controls and real provider Apply/error/Undo flows. Gallery composition remains a separate consumer of the same components.
- External state: both hosts queue session notifications, retain drafts during external selection/replacement, and consume pending canonical selection only after applying/reverting drafts. Neutral and RAD live epochs distinguish replacement from persisted identity.

Corrections raised/reviewed:

1. Nested close regression: a minimal Qt offscreen reproduction of `ignore(); self.close()` inside closeEvent yielded `close_return=False, visible=True, events=1`. The candidate now avoids reentrant close for synchronous clean/Discard decisions.
2. select_card bypass: source review identified local-only selection; verifier independently reproduced active_object=None. Candidate now calls provider.select.
3. Associated curve reopening: legacy first-curve override contradicted the newly selected saved reference. Candidate removes both overrides and routes through _sync_curve_context. A focused in-memory Qt probe after the correction returned `selected=material, associated=load, displayed_curve=load, plot_matches=True`.
4. PART native numeric aliases: /PART/01 and /PART/1 initially escaped exact-header duplicate detection. Current `_native_part_id` canonicalizes the relation before checking ambiguity.

Additional focused preservation probe: an in-memory unknown `/PART/UNKNOWN` card remains readable and returns an empty read-only property list without error.

Validation boundaries: no full suite was duplicated; verifier owns final automated suite and focused integration results. No repository code, tests, staging, commits, remote publication, or external application writes were performed by this reviewer. Actual Windows input, 100/150/200% DPI, dock movement/restoration and native VTK interaction remain pending under the documented prior approval timeout; no retry or bypass was attempted.

Final author-ready re-read: catalogue author confirmed source freeze. Read-only scrollable QPlainTextEdit metadata removes the reported rich-label rendering problem; ActionScene now uses ActionRegistry with capability-driven enabled state and the same menu/toolbar QAction instances. No further code-risk finding from that final delta. Visual reviewers own the fresh-image disposition.

## Reactivated final-diff review

Re-read the preserved 23 tracked changes and six new deliverables at base HEAD `6a2c96e`, including the final committed-review copies, application/viewport identity contracts, host actions/coordinator, draft baseline snapshots, deferred external selection, typed-reference codec, catalogue source/metadata, CI inclusion and documentation corrections. Parent handoff payload and preserved reviewer context were available; no handoff/checkpoint file was found in the checkout.

Result: no new scoped P1/P2 code or regression-risk finding. The later host deltas retain the previously accepted fixes: explicit card activation updates canonical selection immediately; disabled read-only PART summary controls have no edit callbacks; Save-failure snapshots restore the original curve committed baseline as well as visible cell text; snapshots avoid querying stale refs after document replacement; Gallery Apply/Revert buttons follow the shared action enabled state; clearing deferred selection clears both current tree index and properties; reopened material context follows its saved reference.

Independent verifier reports the fresh final eight related suites: **99 passed, 1 skipped in 10.18s**. Evidence: `.test-tmp/final-all-modifications-verification.xml`. The one skip is the pre-existing case-sensitive filesystem setup in `test_project_roundtrip.py:136`. I did not rerun the suite or add a new test campaign. Earlier focused probes remain scoped evidence, not a substitute for native acceptance.

Publication boundary: this review covers the local final source, not a future commit SHA or remote required checks. Root must bind any publication decision to the actual new commit and its required CI result. No GitHub approval, protection bypass, push, PR or merge was performed by this reviewer.

**A7 remains material unverified acceptance work.** Real Windows input, 100/150/200% DPI, dock move/restart restoration and native VTK interaction were not established by this review or the offscreen suite. The code-risk verdict does not certify A/P3 completion, native product acceptance, or the user's conditional `no major unverified` merge condition. Existing documentation correctly keeps A incomplete. Native tool availability/permission checking belongs to root; no old approval timeout retry or bypass was attempted here.

Peer exchange disposition: requirements critic and implementation advocate independently report no new scoped source defect and both classify native A7 as a material original acceptance requirement. I concur: **conditional merge remains blocked at native A7 even if exact-SHA required CI passes**. Root may continue separately authorized draft-PR and CI preparation; these do not constitute native acceptance or permission to bypass it.
