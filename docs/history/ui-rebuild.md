# Prep UI rebuild — historical record, 2026-10-31

2026-11-01 handoff: this is the earlier presentation rebuild record, not the
current support table or a current publication gate. The eight approaches and
native modeling workflows were subsequently integrated in
[PR #15](https://github.com/pikachu444/caelab-prep/pull/15), merged at `a48d3b4`.
See [current implementation and reference differences](../ui-reference-variants.md),
[current execution evidence](../../CURRENT_STATE.md#current-progress), and the
[remaining work and completion criteria](../../CURRENT_STATE.md#remaining-work).
The source ranges, test counts, process IDs and publication restrictions below
belong to the dated rebuild; they are not refreshed evidence for the merged code.

The later Linux X11 campaign covers eight presentations at two window sizes on
a two-quad input: whole-window layout, actual VTK rendering and picking. It does
not complete the modeling workflow's visual acceptance, Windows verification,
or same-task execution in the eight reference products. Windows verification is
deferred under the current implementation plan; the old native/publication hold
below is not an instruction to stop otherwise authorized work.

## Preserved rebuild status and scope

Status at that review point: second presentation implementation and code regression review complete; native interaction and visual acceptance remained open. Native input/capture was on parent-directed hold pending the user's lock-state check and desktop coordination. The local candidate was not approved to merge on automated tests alone.

## Scope and implementation

Base: main `0dc14127cbfaf22f54cc59b4a6648f35e9cfaec7` (PR #12). New checkout and branch `rebuild/prep-engineering-ui`; no edits to the prior checkout or Workbench.

The application presentation now uses a resizable left stack for model browser and contextual inspector, leaving the central model area dominant. File/history commands and viewport commands have separate locations. The inspector has object identity, grouped rows and local validation; vectors use aligned component rows. Curve controls use a compact command strip, point table and revised plot labels. The material/curve consumer uses the same shared widgets. Developer demonstrations remain in the catalogue, available as a separate `caelab-prep catalogue` process; no catalogue button or example paragraphs occupy the normal Prep workflow. Messages starts closed unless a saved layout or real warning/error requires it.

The first draft at `40d8d913` changed layout and styling while retaining much of the old construction. That draft did not fully satisfy the request to replace the presentation. It was reopened; the current source separates newly written construction/painting from retained editing behavior. This distinction is source provenance, not proof that the resulting screen is good.

| Source in this candidate | New expression or deliberately retained behavior | Reason |
|---|---|---|
| `ui/main_window.py` 15–60 | New small entry point joining the controller and workspace | Keeps public native host and patchable dialog/task/settings dependencies |
| `ui/prep_workspace.py` 25 onward | New menu/command/view/browser/inspector/notice/status construction and schema projection | Replaces the former visual `_create_*` methods rather than invoking the old layout |
| `ui/prep_controller.py` 28–664 | Explicitly retained selection/draft/transaction/file lifecycle adapter, plus new empty-document guards | Preserves revision checking, selection, Undo and Save/Discard/Cancel; module docstring records the old source ranges at `40d8d913` |
| `ui/materials_workspace.py` 12–126 | New material/curve consumer construction | Removes former gallery menu/dock/plot construction methods; reuses actual shared widgets |
| `ui/gallery.py` 16–454 | Retained neutral provider/draft/file behavior with the new construction injected | Keeps actual non-RAD document editing and persistence |
| `ui/widgets/properties.py` 13–198 | New row/section grid and object-header composition | Replaces the old QFormLayout construction; aligned field/unit/error rows |
| `ui/widgets/_editing.py` 9–75 | Retained typed-editor/value/unit bindings extracted explicitly | Unit conversion and draft validation are behavior, not new visual authorship |
| `ui/widgets/tree.py` 21–166 | New delegate/count badges and model construction; retained identity/expansion restoration in `_TreeViewState` 58–83 | Makes counts visible in the name column while retaining canonical selection |
| `ui/widgets/curve.py` 17 onward | New worksheet construction, normalized axis and plot painter | Replaces old construction/painting; no new row/card creation commands |
| `ui/widgets/_curve_data.py` 9–146 | Retained validation, draft capture/restore, paste, editor flush and atomic Apply adapter | Preserves one command/Undo boundary and rejection of partial invalid input |
| `ui/widgets/numeric.py` 13–92 / 95–147 | NumericEdit draft/validation preserved; VectorEdit cell construction newly written | Retains numerical parsing while replacing component presentation |
| `ui/design/appearance.py` 1 onward | New original glyph set, multi-resolution icon construction and surface/state rules | Replaces former glyph definitions and QSS; semantic icon keys preserved |
| `ui/shell.py` 13–106 / 109–166 | File coordinator/task/dock primitive retained; elided view-title/context presentation and local action host updated | Preserve asynchronous/save-close behavior and shared shell contract |
| `ui/viewport.py` 9–299 | Existing mesh projection, render/pick and selection adapter retained; gradient/orientation/standard-view additions | Protect native IDs, epoch/revision guards and GPU lifecycle; not claimed as a new renderer |

`cae_core`, `application`, storage/codecs, the RAD reader/writer, command history and solver behavior are unchanged. Saved raw payloads, INCLUDE handling, selection identity/stale guards, references, existing field schemas, Save/Discard/Cancel and asynchronous operations retain their contracts. No new card creation, CAD adoption, meshing or solver execution is claimed.

Original fixture `examples/rad/stiffened_panel_0000.rad` and its deterministic generator provide 7 parts, 1,075 nodes and 1,008 quads for a populated mechanical scene. It is an editor fixture, not a solver-validated analysis model. Existing shell panels and solid blocks with INCLUDE remain distinct inputs.

## References and design choice

Required planning documents and benchmark task/asset records were read before implementation. These are source observations, not direct execution of the reference programs:

- [Naksha 0.5.07 full application image](https://agentnaksha.com/assets/img/app/app-crash-model.webp), 1600×860: approximately 400px left tree/details column; remaining width devoted to the model; compact command and selection bands. Directly pixel inspected.
- [HyperMesh 2025 Entity Editor image](https://2025.help.altair.com/2025/hwdesktop/hwx/images/entity_editor_unity.png), 381×466 crop: aligned name/value properties with reference and native card identity. Directly pixel inspected; it establishes no whole-window proportion.
- [PrePoMax 2.5.0 manual](https://prepomax.fs.um.si/wp-content/uploads/2026/03/PrePoMax-v2.5.0-manual.pdf), page 3 Figure 1: whole-window tree/model/command hierarchy. Directly pixel inspected; this is a results screen, not proof of material-editing steps.
- [ParaView Basic Usage](https://docs.paraview.org/en/latest/Tutorials/SelfDirectedTutorial/basicUsage.html), §§2.1–2.4, and [FreeCAD property editor documentation](https://raw.githubusercontent.com/FreeCAD/FreeCAD-documentation/main/wiki/Property_editor.md): selection-bound properties and resizable docks. Text read; FreeCAD wiki image access failed and ParaView image retrieval was incomplete. No claim of direct pixel comparison to those two.

Astra compared left-stacked, opposite-side and adjacent-left inspector alternatives. The left stack avoids paying for two permanent side columns when current cards expose few editable fields. Current initial width is 350–420 logical pixels and default browser/inspector allocation is 400:330; a constrained inspector reserves 290px so three common scalar fields and units fit. User resizing remains available. Initial sizing runs before/at first show, not continuously; normal launch followed by maximize still requires native evaluation. Token sizes are project decisions, not copied vendor DPI values. Prep layout version 3 and gallery version 2 reject older default layouts while preserving layouts saved by the new candidate.

| Criterion | Current evidence | Acceptance |
|---|---|---|
| Viewport proportion | Left-stack construction leaves the model dominant; a viewport percentage alone is not an acceptance criterion | Native pixels pending |
| Tree/property visible information | Name-column group badges; offscreen 960×640 shows all three material fields and units without inner/outer inspector scrolling; number inputs measured 151×28 logical pixels | Long-name/row capacity native check pending |
| Blank regions | Browser-first default; quiet log; constrained inspector minimum protects actual editing | Actual populated screen balance pending |
| Command hierarchy | Global file/history; local fit/orientation/edges/pick mode; primary empty-state Open and dirty-state Save; short labels survive QAction changes | Source/offscreen inspected; native state contrast pending |
| Wording noise | Internal explanations removed; one neutral empty-state hint; no-document picks do not create Error messages | Component/source-only whole layouts inspected; native whole app pending |
| Selection/edit steps | Select → edit → Enter; vector/curve Apply remains atomic | Automated behavior passed; native input pending |

These entries are not visual passes. Compare the actual loaded mechanical and material/curve windows at 1320×840 and 960×640 and application scales 100/150/200% when native capture works. Do not substitute the 1440×900 design capture, mockups, QWidget grabs with black VTK, or a framebuffer alone. OS DPI was not changed.

The user's actual remote photo `44893.jpg` was materialized, its pixels inspected, and shown to critic/advocate. Observed defects in that earlier draft: active Open barely differed from disabled commands; the sidebar occupied about 14% of application width; the empty inspector received more height than the browser; two identical no-document Errors were logged. The right black controls and large mouse indicators belong to the remote-control overlay. Gradient and axes are visible, so this photo does not show an application renderer-black failure. Remote scaling does not establish native click-target sizes. Selective changes use 13px type, 26px tree rows and approximately 28px field height; native 1:1 confirmation remains required. Empty/loaded/selected-edit whole windows must be reviewed together.

## Team and actual skill use

Separate newly dispatched roles: shared widgets Sol high; Prep integration Sol high; deep design advisor Astra xhigh; independent QA Sol high; one review team with critic Astra xhigh, advocate Sol xhigh and regression reviewer Sol high. Explicit model/effort arguments were accepted by the dispatch tool. Backend model identity is not independently observable; this record does not claim it was verified. Coordination session model/effort is not exposed by the tools.

- `cae-desktop-ux`: QT-PANELS/FC-PROPERTY/WIN-COMMAND drove left-stack layout, selection-bound inspection and contextual commands; QT-ACCESS drove the scaling evidence boundary.
- `ponytail`: existing model/command/storage paths and validation retained; no new widget framework or dependency.
- pstack `deslop`: diff review for unnecessary wrappers/comments; code and responsibility boundaries kept direct. `architect` and its Codex mapping were read, but its full arena workflow was not executed and is not claimed.
- tstack `file-pr`: local diff/scope review and concise draft PR description. User-requested draft overrides that skill's default ready PR. `babysit-pr` read; bundled `pr-wait` imports Unix `fcntl` and is unsuitable here, so it was not claimed as executed.
- Computer Use: supported native CUA app binding/capture/input attempted by independent QA; no custom native input/capture workaround. Library skill: inspected reference images saved through supported Library upload. The unchanged materialization helper initially failed because Windows Python lacks `os.setxattr`; a task-local compatibility adapter stored and verified returned Library identity/version in NTFS alternate data streams, allowing the exact user photo to be inspected. No OS security/settings change or raw-download substitute was used.

## Verification and review corrections

Final second-presentation automated offscreen suite: 121 passed, 11 skipped. The 10 Gmsh-dependent CAD skips and Windows casefold INCLUDE collision skip are outside changed UI behavior. New focused tests cover filter/selection preservation, invalid draft recovery from Card source, real warning visibility, saved Messages visibility, controller injection compatibility, empty command/access guards, primary command/short-label stability, constrained inspector reachability and numerical plot scales. No existing tests were removed or weakened.

Independent offscreen GUI/file checks across all three fixtures passed scalar/curve edit → atomic Apply → Undo/Redo → save → independent session reopen → projection equality → RAD export → independent reopen. Both declared window sizes passed the three-field inspector/header checks. This is actual file I/O plus offscreen Qt input, not native mouse/keyboard evidence. Catalogue startup was checked with VTK, RAD/session and main-window imports prohibited.

Critic/advocate found saved Messages visibility being overridden; corrected and regression checked. Code reviewer found hidden invalid input causing silent refusal of Save while Card source was active; corrected by revealing the error field/status, retaining the draft and revision. Real model/renderer warnings now reveal Messages. Two empty `_entity_picked` misses reproduced the photo's duplicate Error pattern through `select_pick` → `_require`; loaded guards prevent it. This proves a code failure path, not the user's exact gesture history. Source-only whole layouts exposed a missing elided view title and third field below the constrained inspector; both were corrected. Independent numerical review found collapsed high-offset narrow-range curve ticks; Decimal offset fractions and representable, round-trip tick labels corrected it, with eight focused tests and independent repros. Long tick-label rendering remains part of pixel review. No scoped code blocker remained in the corrected review. Critic/advocate agree the second pass is a substantive presentation rebuild; visual acceptance remains withheld.

## Exact native blocker

Target: isolated Prep Python PID 60864, native window 100994546, initially empty. Supported CUA binding eventually succeeded with accessibility data. Open click failed with `coordinate input geometry is unavailable`; full 1440×931 capture was entirely black except the cursor; activation/input failed with `failed to activate captured window`. One documented rebind/recovery gave the same outcome. No actual model-open input succeeded. This is a failed capture/activation operation, not an explicit denial; no approval remains pending. App observer was responsive and the input desktop read-only check returned Default. Cause is unconfirmed.

Unverified: actual Windows open/edit/Undo/save/reopen, close/cancel/error interactions, docking/narrow windows/application scaling and complete GPU-inclusive application pixels. No acceptable final whole-window product image or associated Library ID exists. Independent QA did not bypass the failure with custom OS input/capture. It left the isolated app running empty at the end of the first QA attempt; later read-only process inventory no longer found PID 60864. Its termination cause is unknown. No unrelated user window/process was closed by this work. Settings were injected into local INI files rather than user app stores; native stores were observed read-only.

The technical team independently reported the same capture/activation failures and a LockApp process; lock state was not thereby established. Parent requested the user's lock check and put native input/capture on hold. No retry or new Windows launch has occurred during that hold. The native scene/scale/docking/maximize/file-flow plan and isolated launcher are prepared for the parent's coordinated release.

The historical branch remained draft at this point; its recorded gate required resolution of this blocker, affected native flows, whole-window pixel review and final green CI. This is the earlier gate, not the status of merged PR #15.

Historical publication attempt: automatic approval review rejected branch push plus draft PR creation before process execution because the existing approval was conditional on no major unresolved verification. No workaround or retry was used. Read-only verification at that time confirmed remote main still `0dc14127cbfaf22f54cc59b4a6648f35e9cfaec7`, no remote rebuild branch and no PR. Remote publication, CI and merge had not occurred at that point. Parent had instructed verification first, with no request to publish an unverified draft. Later preservation and implementation merges are recorded separately in the current execution evidence; they do not turn this failed native capture into a pass.
