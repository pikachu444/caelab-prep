# Independent code and regression-risk review — current final verdict

**Current verdict: final product source/native behavior/documentation remain accepted, and the concrete Qt ownership-root cleanup correction is approved by source review. No remaining scoped source blocker in the new correction. Required CI on the exact new commit SHA is still pending; merge remains gated until it passes.** The 0952d66 PR segmentation fault is retained as a real failure and is not closed by its same-head green push run or by a retry.

This verdict supersedes every earlier pending-Windows/A7/teardown/size-caveat verdict below. The earlier material native acceptance gap is now addressed through the user's explicitly approved own-process Windows QPA/QTest route. It is not an OS SendInput, manual-human-input, OS-monitor-DPI-change, oversized-full-screen-input, floating-caption-redock, installer, B/C or all-feature-combinations claim.

Final source review covers the bounded catalogue QScrollArea fix, explicit isolated test settings, unchanged production persistence/commands, and the promoted native evaluation driver (SHA256 B3C56CA2D29657A60A7432DF7C683A4B1184B63BA0DC6B524094EEC2D4FD27B4). Independent actual evidence includes all three scale manifests and separate-process restores, full-control scrolling plus real Apply/Undo, Win32 OpenGL rendering and stamped pick/canonical highlight, native modal close branches, and the targeted real cell-click/F2 curve recheck. The 200% exact 1320x840 layout supplement is accepted as oversized own-widget rendering; actual 200% input uses the separate screen-fitting 960x640 path.

The final native validation document now correctly discloses old settings contamination, the first failed curve probe and targeted correction, API dock setup before real Bottom→Left movement, unsuccessful floating-redock attempt, isolated INI persistence, and physical-screen/capture limits. No overclaim remains in the reviewed passages. Root may copy this review and prepare the final commit/CI; the reviewer performed no staging, commit, push, PR approval or merge.

The record below preserves the investigation chronology and source/flow evidence. Earlier incomplete or blocked statuses are historical, not the current verdict.
## Historical review record — superseded by the current verdict above

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

## Post-review CI teardown blocker (70a2baf)

Root supplied new evidence: push CI 41172251830 passed, but PR CI 41172293872 ran all 41 Qt tests successfully and then exited with interpreter-teardown segmentation fault 139 on Ubuntu/Python 3.12.15/pytest 9.2.0. Passing test assertions do not close this blocker.

Read-only lifetime inspection found that `test_common_widgets.app` is a return-only function fixture, `test_gui_document_flow.application()` is also return-only, common-widget hosts usually call only close(), and GUI tests call deleteLater() followed only by processEvents(). New registry/coordinator/bound callbacks keep QObject/Python reference cycles alive. This is a concrete cleanup-risk hypothesis, not a proven native stack diagnosis.

Independent verifier instrumentation strengthens that hypothesis: after pytest.main returned, QApplication existed and the global pool had **0 active threads**, but **128 top-level widgets** remained, including **10 GalleryWindow + 2 MainWindow** instances. All 12 hosts were hidden, closed and not busy. Explicit DeferredDelete delivery reduced 128 to 99 but left all 12 hosts, which had never been scheduled for deletion.

Recommended smallest corrective path: lazy Qt session fixture strongly owns QApplication; a per-test Qt fixture owns only top-level widgets created by that test, waits test workers with a bounded assertion, delivers queued terminal events, closes/deletes those objects while the application remains alive, and explicitly dispatches DeferredDelete events. Preserve core-only CI by avoiding module-level PySide imports in shared conftest. Do not change product close semantics or rewrite workers until additional evidence requires it; do not mask exit failures.

Primary reference: Qt documents that local processEvents loops without an event loop do not process DeferredDelete, and describes sendPostedEvents as an alternative: https://doc.qt.io/qt-6/qcoreapplication.html#processEvents .

Current status: blocker pending a concrete reviewed fix and affected Linux interpreter exit-0 verification. Native A7 remains a separate unresolved acceptance blocker.

### Reviewed cleanup correction

Read the concrete new `tests/conftest.py`, both Qt module fixture hookups, and workflow `PYTHONFAULTHANDLER=1` delta. No new source-risk finding. Session QApplication ownership is strong and imports are lazy; cleanup waits bounded test workers, delivers terminal callbacks while windows/app live, checks no callback-started worker remains, deletes only this test's new top-level widgets with shiboken isValid guards, dispatches DeferredDelete explicitly, and asserts destruction. Both host tests opt in; core-only jobs do not import Qt through conftest. Product QRunnable/window close behavior is untouched; no continue-on-error, os._exit, or other masking is introduced.

Verifier reports corrected local Qt41 **passed in 8.94s with process exit 0**, with **0 top-level widgets and 0 active workers after pytest.main** (previously 128/0). This closes the observed test ownership leak. Approval: patch is suitable for root's commit and required CI validation. It is not yet evidence that the original Linux interpreter crash is fixed: that requires the affected Linux Qt job to exit 0 on the exact new commit. Native A7 remains independent and still blocks the conditional merge.

### Exact-SHA CI closure of teardown blocker

Independently read both saved full Qt job logs at `.test-tmp/ci-qt-c23149-push.log` and `.test-tmp/ci-qt-c23149-pr.log`, and confirmed local HEAD is `c23149e6f64c4e43d25af1be6b0083a73dd2ad55` with a clean worktree.

- Push run `41172805733`, Qt job `124454174042`: checkout is exact head `c23149e6f64c4e43d25af1be6b0083a73dd2ad55`; **41 passed in 4.01s**, followed by normal post-job cleanup. https://github.com/pikachu444/caelab-prep/actions/runs/41172805733
- PR run `41172808346`, Qt job `124454181639`: checkout is synthetic merge `1550aae8d1cb8606245e51988f3b1a005a492a63`, explicitly merging that same head into base `4828818681e0ad3e2ff7c428a0d0c09158f6e32f`; **41 passed in 3.83s**, followed by normal post-job cleanup. https://github.com/pikachu444/caelab-prep/actions/runs/41172808346

Both logs identify Linux/Python 3.12.15, PySide6/shiboken6 6.12.0, VTK 9.7.1 and pytest 9.2.0. Neither log contains the prior segmentation-fault/exit-139 error. The independent verification role additionally confirms through the job API that the Qt steps/jobs and all four jobs in each run succeeded. These are completed job results, not merely passing assertion summaries.

Disposition: the observed test-owned-window leak is corrected (local 128→0), and the actual affected Linux process now completes successfully in both exact-head and PR-merge contexts. **The CI teardown code blocker is resolved at c23149e.** No additional source fix or rerun is warranted on the available evidence. This conclusion does not close native A7, whose separately authorized driver/evidence and final acceptance remain parent-owned.

## Native acceptance evidence review and narrow-host correction

Parent authorized bounded own-process native Qt/QTest/windows-QPA/live-VTK evidence. This is a new permitted route, not a retry/bypass of the old CUA app-access timeout. I only read the harness/artifacts and performed a read-only QSettings constructor probe; root owns native input execution.

Independently viewed original scale-100 and scale-150 integrated narrow catalogue captures: the right-hand metadata/property scene and controls are clipped without recovery scrolling. Their seven-stage `passed` labels therefore do not establish complete A7 usability. The narrow source correction wraps the catalogue's full content in a resizable QScrollArea while retaining asset/page cache ownership; this is an appropriate bounded fix, pending actual scrolled-control reachability/input evidence.

Settings isolation defect confirmed independently: after setDefaultFormat(IniFormat) and setPath(IniFormat,...), constructing QSettings('CAELab','Prep') returned `format=NativeFormat`, `fileName=\\HKEY_CURRENT_USER\\Software\\CAELab\\Prep`. The probe set no values and performed no writes. Qt's explicit org/app constructor ignores the default format: https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSettings.html . Earlier native runs did demonstrate persistence, but their claimed per-scale isolated directory was false and they may have changed actual app-layout preferences. Do not clear/restore unknown native values.

Read the corrective per-test fixture and current native-harness injection: both replace only window-module QSettings aliases with explicit INI filename factories, disable fallbacks and preserve production NativeFormat constructors. The test fixture is lazy and stays installed through widget cleanup. The harness records actual settings filename/format, asserts the path is under the evidence output, and compares read-only native snapshots before/after. No code-risk finding in this isolation correction.

Native evidence review remains open: revised runs must establish full target bounds through ancestor viewports, physical screen/frame reachability, genuine dock transitions measured immediately before the gesture (not before setup), and independent per-scale restore stores. A QWidget.grab of an oversized window or a stage isVisible assertion alone is insufficient. The old 150% before-area=1/final-area=1 diagnostic was sampled before an API Bottom-area setup; that timing error is inconclusive about whether the subsequent gesture moved the dock and must be corrected rather than treated as proof of failure or success.

### Revised source and evidence-driver review

The final narrow-host source fix remains limited to an outer QScrollArea; added regression coverage reveals actual numeric/property-reference/curve/action controls in the constrained integrated catalogue and performs QTest edit/Apply/Undo. No code-risk finding in the production change or the explicit per-test INI settings fixture.

Reviewed native driver snapshot SHA256 `475DD71D3FE9C100F71EEF859FF509D080163257018951DBF4B3BAD807E14FBC`: explicit per-host INI files/fallbacks off; real native settings snapshots compared read-only before/after; 200% actual input uses a fitted 960x640 frame with available-screen containment assertion; catalogue reachability scrolls nested real views and checks full input-control rectangles through every ancestor viewport; clicks reject points outside visibleRegion; dock pre-gesture area is now recorded/asserted Bottom after setup; oversized 1320x840 captures at 2x are explicitly excluded from full-screen reachability claims.

One final driver caveat was sent to author/root: the gallery remains shown before the later RAD docking stage, while that snapshot does not raise/activate RAD immediately before those gestures. QWidget visibleRegion does not establish absence of coverage by another top-level window. Raise/activate the target owned window before that input, then examine actual revised run artifacts. No native execution was performed by this reviewer.

Final driver re-read SHA256 `DA2D15E60588222BC3E98E3342CC47CC641A0E46FB7E03896BA6750562A078E7` closes the own-window coverage gap: every click/drag raises and activates its target top-level, waits for native active/exposed status, and asserts its frame fits the available screen; modal button input uses the same guard; docking explicitly fits/raises RAD after Gallery. Scroll reachability now uses mapped control centres with half-control margins, then verifies the full rectangle through every ancestor. Source is acceptable for the parent's authorized native run; final acceptance still requires inspecting actual updated artifacts and false/fallback flags at all three scales.

### Fresh isolated 100% evidence inspected

The fresh `isolated-100/exercise-manifest.json` has eight passing stages and one failed added curve-delegate-open stage; its overall failure must remain visible until a targeted native correction/recheck. Passing stages include actual integrated narrow catalogue scroll/edit/Apply/Undo, second solid native rendering, stamped live VTK pick, modal close branches and native-settings-unchanged=true with explicit INI store paths. Dock movement records actual pre-gesture Bottom=8 and resulting Left=1, no final-layout fallback; the earlier separate redock attempt's false flag remains honest data.

Independently viewed `isolated-100/exercise-gallery-catalogue-narrow.png`: horizontal/vertical recovery scrollbars now exist, Apply/Revert/Undo are fully available in the scrolled viewport, and the edited value is restored by Undo. Portions of navigation/header outside that current scroll position are recoverable, unlike the old unscrollable clipping. Per-control full-ancestor-rectangle assertions and actual input support this visual assessment.

The current focused curve correction uses a real cell click followed by F2 and keyboard editing, asserts one visible delegate and keyboard focus, then actual Apply/Undo controls. This is a valid user event path, not direct model/editItem mutation. Its resulting native evidence remains pending; the prior failed stage is not being silently treated as passed.

## Final narrow-source and native behavior review

Re-read the narrow catalogue QScrollArea change, explicit per-test INI settings aliases, new constrained-control regression and promoted `scripts/evaluation/verify_native_windows.py`. The promoted driver is byte-identical to the final evidence driver, SHA256 `F079AF702EB203E49FF7FE460123D9987A8C42B7F716AF68DF3A1532C24C980F`. No new scoped code/regression defect found. Production settings constructors and file/command behavior remain unchanged. Root reports the affected final local suite: 100 passed, one filesystem skip, with zero remaining Qt objects/workers; this reviewer did not duplicate it.

Independently read the actual `isolated-100`, `isolated-150`, `isolated-200` exercise manifests and all three separate-process restore manifests; read the focused `isolated-curve-100/curve-manifest.json`; viewed corrected narrow images at all scales, native curve applied/undo images, and the 200% post-pick VTK framebuffer. This is actual source/flow/artifact evidence, not agreement with a stage label:

- All scales use Windows QPA/PySide6 6.9.1 on exposed native windows, with active owned-window and available-screen guards before input. Actual input and narrow views fit at 100/150%; 200% uses 960x640 logical size and a fitting 960x656 frame. Oversized normal captures are excluded from full physical-screen reachability claims.
- Each scale records eight full-control/ancestor-scroll reachability assertions and actual native QTest Revert/edit/Apply/Undo on the repaired catalogue. Corrected captures show recovery scrollbars and fully reachable right-hand action controls, resolving the prior unscrollable clipping.
- All three actual VTK windows are `vtkWin32OpenGLRenderWindow`, OpenGL support=1, twelve displayed cells. Real Qt mouse input emits a stamped element candidate that equals the canonical document/resource/entity selection; post-pick pixels show the orange selected-element edge. This establishes actual rendering/selection rather than a disabled placeholder or synthetic pick.
- Native scalar tree selection/edit/Undo/Redo/save, typed-curve reference/save/reopen, modal Cancel/invalid Save/valid async Save/Discard and saved values pass. The first 100% curve delegate-open probe failed honestly; the targeted real cell-click/F2/delegate-key/Apply/Undo correction passed, with original images showing cell Y 1.0 then restored 0.0. It supersedes only that failed probe; the first overall failed manifest is retained.
- Each scale records actual docked Bottom=8 before the gesture and Left=1 afterward, with no final-layout fallback. All three new-process restores match the resulting layout and saved project. The separate floating redock attempt remains false and is not claimed as successful; original dock movement and persistence are established by the successful docked move/restart path.
- Every revised run records real explicit per-scale INI filenames, IniFormat, fallbacks=false, native-settings-unchanged=true and zero remaining workers. These prove isolated persistence through real QSettings; they do not falsely label the production constructor as INI. Earlier unisolated trials may have changed app-layout preferences; prior unknown values must not be reconstructed or cleared.

Disposition: no remaining scoped implementation/native-behavior blocker for the explicitly approved own-process QTest/windows-QPA route. This is not a claim of OS SendInput, manual human interaction, OS monitor-DPI changes, every possible native-caption gesture or installation validation. Current README/DESIGN/ARCHITECTURE draft wording accurately says application scaling and points to bounded execution evidence rather than those excluded claims.

One exact-matrix evidence caveat remains for documentation/critic disposition: the 200% Gallery normal resize was actually clamped to 1282x711 logical (2564x1422 pixels), not the original 1320x840 target. Do not label it an exact-size target pass without a bounded supplemental native capture, or explicitly retain that case exception. All actual narrow input/restore behavior is accepted. After that wording/evidence disposition, root must still obtain required CI for the exact final new commit; the prior c23149e success does not cover the new wrapper/settings/test/driver changes.

### Exact-size supplement and final native disposition

Read `isolated-layout-200/layout-manifest.json` and viewed its native Gallery composition image. The supplement actually retains 1320x840 logical size at DPR 2, with 2640x1680 pixels; all four curve rows, plot axes and property actions are readable. Its frame is explicitly outside the available screen and its scope explicitly excludes input/full-screen reachability. This closes the exact-size layout-capture exception; the accepted 200% input evidence remains the separate fitting 960x640 path. Native settings remain unchanged. The promoted and executed final driver are byte-identical, latest SHA256 `B3C56CA2D29657A60A7432DF7C683A4B1184B63BA0DC6B524094EEC2D4FD27B4`; the only new phase fixes size and asserts dimensions for that bounded supplemental capture.

Read the new README/DESIGN/ARCHITECTURE and native validation record. Application scaling, own-widget capture, OS/manual-input exclusions, first-run curve failure plus targeted recheck, old settings contamination, INI isolation and oversized-screen limits are disclosed accurately. One wording correction was requested: the successful drag is a docked Bottom→Left area move after explicit setup, not proof that the separate failed floating-native-caption redock attempt succeeded. Keep that false attempt disclosed and describe the successful path as dock-area movement plus restart persistence.

**Final code-peer verdict:** no remaining scoped code/regression or native-behavior blocker for the explicitly authorized Windows own-process QTest route. This conclusion is based on the reviewed source, actual input/state/value assertions, all three separate-process restores, repaired-control bounds, actual Win32 OpenGL pixels/pick, and the independently inspected images—not only stage visibility. The originally material A7 environment gap has been addressed for that bounded agreed route. Physical-screen limits at the oversized 200% normal size and excluded OS/manual methods remain limitations, not false completion claims. Root must still bind publication/merge to the exact final new commit and successful required CI; c23149e's green checks do not cover this new source/test/driver/doc correction.

Final documentation re-read confirms the requested dock wording is corrected: it explicitly records the API Bottom setup, actual Bottom→Left drag, and does not claim floating→docked input success. The 200% exact-size supplement is separately labelled layout rendering with no physical-screen input claim. No documentation overclaim remains in those reviewed passages.



## New 0952d66 CI cleanup blocker — ownership diagnosis

Push run 41174599358 passed all four jobs (Qt42, exit0), but PR run 41174601977 segfaulted with exit139 while `tests/conftest.py:54` delivered DeferredDelete during a function fixture. The log has nineteen completed GUI cases and twenty-one common-widget dots, pinpointing teardown of `test_narrow_gallery_catalogue_scrolls_controls_into_view_before_edit_and_undo`, not interpreter shutdown after all tests. No green retry may substitute for correcting this gate failure.

Independently read `.test-tmp/ci-qt-0952-pr-failure.log` and verifier's actual `.test-tmp/qt-owner-flags-before.log`. The narrow test produces thirteen top-level widgets: one parentless/Python-owned GalleryWindow, six parent-owned/non-Python-owned QMenus, and six QComboBoxPrivateContainers parented to QComboBoxes. All twelve private/menu windows descend from the Gallery root. The fixture's new-top-level list misidentifies creation as ownership and calls close/deleteLater on all thirteen independently.

Minimal causal correction: close/delete only test-created parentless Python-owned roots; let Qt-owned descendants be destroyed with their owning root. Preserve the assertion that every original test-created top-level wrapper is invalid afterward. This removes arbitrary independent close/deletion of Qt private popup containers and related owner callbacks, rather than adding delays, masking failure, weakening checks or changing production behavior.

Qt's documented QObject tree semantics already prevent generic parent-child double deletion regardless of destruction order (https://doc.qt.io/qt-6/objecttrees.html). Therefore this is not a proven generic QObject double-delete stack diagnosis; the actionable mistake is independently manipulating non-owned private widget internals. Root-only cleanup needs concrete patch review and actual affected Linux CI exit0. Native A7 acceptance is unchanged and does not need another native campaign for this test-only correction.


### Concrete ownership-root correction reviewed

Independently reviewed the minimal fixture diff: import shiboken ownedByPython, select only new widgets whose QObject parent is None and which are owned by Python, and close/delete those roots. The original `assert all(not isValid(widget) for widget in owned)` is unchanged and still checks destruction of every originally observed root/menu/private-popup wrapper. Worker bounds and deferred delivery checks remain unchanged. The CI-only -vv addition improves failing-case identification without masking errors. No production source or native UI behavior changes.

The actual ownership graph justifies this correction: all twelve non-root QMenu/QComboBoxPrivateContainer objects belong to the single Gallery root and should be destroyed through that owner, not independently closed and deleted by a top-level-window scan. This removes the concrete ownership mistake; it does not claim a native stack-proven generic QObject double-delete bug.

Read `.test-tmp/qt-root-ownership-verification.xml`: 42 tests, zero errors/failures/skips, including the previously implicated narrow-gallery case and both subsequent external-selection cases. Verifier reports process exit0, native settings unchanged, zero top-level widgets and zero workers. No duplicate suite/native run was performed by this reviewer.

**Disposition:** source review approves this bounded cleanup patch for root's new commit and required CI. Native A7 acceptance remains unchanged. Actual Linux success for the exact new commit is still required to close the current CI gate; no previous passing job, single successful retry, test skip, dependency pin or exit suppression substitutes for that result. The prior 0952d66 PR failure must remain documented honestly.

Reviewer correction: my earlier cleanup approval did not distinguish a newly created top-level window from a Python-owned lifetime root. The captured private-popup ownership graph shows that omission was unsafe. The revised approval is specifically for ownership-root deletion with the full descendant-destruction assertion retained, not a blanket endorsement of deleting everything returned by topLevelWidgets().
