# Prep UI rebuild — 2026-10-31

Status: implementation and code review complete; native interaction and visual acceptance blocked. This branch is a draft and must not merge on the strength of automated tests alone.

## Scope and implementation

Base: main `0dc14127cbfaf22f54cc59b4a6648f35e9cfaec7` (PR #12). New checkout and branch `rebuild/prep-engineering-ui`; no edits to the prior checkout or Workbench.

The application presentation now uses a resizable left stack for model browser and contextual inspector, leaving the central model area dominant. File/history commands and viewport commands have separate locations. The inspector has object identity, grouped rows and local validation; vectors use aligned component rows. Curve controls use a compact command strip, point table and revised plot labels. The material/curve consumer uses the same shared widgets. Developer demonstrations remain in the catalogue, available as a separate `caelab-prep catalogue` process; no catalogue button or example paragraphs occupy the normal Prep workflow. Messages starts closed unless a saved layout or real warning/error requires it.

The rewrite concerns presentation construction and arrangement. Existing widget validation, unit conversion, transaction methods and application adapters are deliberately retained, not described as newly authored. `cae_core`, `application`, storage/codecs, the RAD reader/writer, command history and solver behavior are unchanged. Saved raw payloads, INCLUDE handling, selection identity/stale guards, references, existing field schemas, Save/Discard/Cancel and asynchronous operations retain their contracts. No new card creation, CAD adoption, meshing or solver execution is claimed.

Original fixture `examples/rad/stiffened_panel_0000.rad` and its deterministic generator provide 7 parts, 1,075 nodes and 1,008 quads for a populated mechanical scene. It is an editor fixture, not a solver-validated analysis model. Existing shell panels and solid blocks with INCLUDE remain distinct inputs.

## References and design choice

Required planning documents and benchmark task/asset records were read before implementation. These are source observations, not direct execution of the reference programs:

- [Naksha 0.5.07 full application image](https://agentnaksha.com/assets/img/app/app-crash-model.webp), 1600×860: approximately 400px left tree/details column; remaining width devoted to the model; compact command and selection bands. Directly pixel inspected.
- [HyperMesh 2025 Entity Editor image](https://2025.help.altair.com/2025/hwdesktop/hwx/images/entity_editor_unity.png), 381×466 crop: aligned name/value properties with reference and native card identity. Directly pixel inspected; it establishes no whole-window proportion.
- [PrePoMax 2.5.0 manual](https://prepomax.fs.um.si/wp-content/uploads/2026/03/PrePoMax-v2.5.0-manual.pdf), page 3 Figure 1: whole-window tree/model/command hierarchy. Directly pixel inspected; this is a results screen, not proof of material-editing steps.
- [ParaView Basic Usage](https://docs.paraview.org/en/latest/Tutorials/SelfDirectedTutorial/basicUsage.html), §§2.1–2.4, and [FreeCAD property editor documentation](https://raw.githubusercontent.com/FreeCAD/FreeCAD-documentation/main/wiki/Property_editor.md): selection-bound properties and resizable docks. Text read; FreeCAD wiki image access failed and ParaView image retrieval was incomplete. No claim of direct pixel comparison to those two.

Astra compared left-stacked, opposite-side and adjacent-left inspector alternatives. The chosen 350px left stack avoids paying for two permanent side columns when current cards expose few editable fields. Tree and inspector heights remain independently resizable. Token sizes are project decisions, not copied vendor DPI values. Existing saved gallery layouts are intentionally retained; a fresh settings store uses the new default stack. Prep layout version 2 avoids restoring the old default arrangement as the new layout.

| Criterion | Current evidence | Acceptance |
|---|---|---|
| Viewport proportion | New layout allocates about 75% of width at 1440 logical pixels; old editor image about 55% | Native pixels pending |
| Tree/property visible information | Parts first; redundant type hidden; named fields, unit context, grouped inspector | Long-name/row capacity native check pending |
| Blank regions | Default log removed, side panels consolidated | Actual populated screen balance pending |
| Command hierarchy | Global file/history; local fit/orientation/edges/pick mode | Code reviewed; native constrained-width check pending |
| Wording noise | Internal revision/provider/example instructions removed | Component pixels inspected; whole app pending |
| Selection/edit steps | Select → edit → Enter; vector/curve Apply remains atomic | Automated behavior passed; native input pending |

These entries are not visual passes. Compare the actual loaded mechanical and material/curve windows at 1320×840 and 960×640 and application scales 100/150/200% when native capture works. Do not substitute the 1440×900 design capture, mockups, QWidget grabs with black VTK, or a framebuffer alone. OS DPI was not changed.

## Team and actual skill use

Separate newly dispatched roles: shared widgets Sol high; Prep integration Sol high; deep design advisor Astra xhigh; independent QA Sol high; one review team with critic Astra xhigh, advocate Sol xhigh and regression reviewer Sol high. Explicit model/effort arguments were accepted by the dispatch tool. Backend model identity is not independently observable; this record does not claim it was verified. Coordination session model/effort is not exposed by the tools.

- `cae-desktop-ux`: QT-PANELS/FC-PROPERTY/WIN-COMMAND drove left-stack layout, selection-bound inspection and contextual commands; QT-ACCESS drove the scaling evidence boundary.
- `ponytail`: existing model/command/storage paths and validation retained; no new widget framework or dependency.
- pstack `deslop`: diff review for unnecessary wrappers/comments; code and responsibility boundaries kept direct. `architect` and its Codex mapping were read, but its full arena workflow was not executed and is not claimed.
- tstack `file-pr`: local diff/scope review and concise draft PR description. User-requested draft overrides that skill's default ready PR. `babysit-pr` read; bundled `pr-wait` imports Unix `fcntl` and is unsuitable here, so it was not claimed as executed.
- Computer Use: supported native CUA app binding/capture/input attempted by independent QA; no custom native helper workaround. Library skill: inspected reference images saved through supported Library upload; local xattr writeback unsupported by Windows `os.setxattr`.

## Verification and review corrections

Final automated offscreen suite: 108 passed, 11 skipped. The 10 Gmsh-dependent CAD skips and Windows casefold INCLUDE collision skip are outside changed UI behavior. New focused tests cover filter/selection preservation, invalid draft recovery from Card source, real warning visibility and saved Messages visibility. No existing tests were removed or weakened.

Independent file I/O checks across all three fixtures passed material edit → Undo/Redo → save → new session reopen → projection equality → RAD export → independent reopen. This is actual file I/O, not native mouse/keyboard evidence. Catalogue startup was checked with VTK, RAD/session and main-window imports prohibited.

Critic/advocate found saved Messages visibility being overridden; corrected and regression checked. Code reviewer found hidden invalid input causing silent refusal of Save while Card source was active; corrected by revealing the error field/status, retaining the draft and revision. Warnings for partial/untransformed geometry were hidden by the quiet default; real model/renderer warnings now reveal Messages. README command labels and catalogue routes were updated. No scoped code blocker remained in the corrected review. The three reviewers withheld visual acceptance.

## Exact native blocker

Target: isolated Prep Python PID 60864, native window 100994546, initially empty. Supported CUA binding eventually succeeded with accessibility data. Open click failed with `coordinate input geometry is unavailable`; full 1440×931 capture was entirely black except the cursor; activation/input failed with `failed to activate captured window`. One documented rebind/recovery gave the same outcome. No actual model-open input succeeded. This is a failed capture/activation operation, not an explicit denial; no approval remains pending. App observer was responsive and the input desktop read-only check returned Default. Cause is unconfirmed.

Unverified: actual Windows open/edit/Undo/save/reopen, close/cancel/error interactions, docking/narrow windows/application scaling and complete GPU-inclusive application pixels. No acceptable final whole-window product image or associated Library ID exists. Independent QA did not bypass the failure with custom OS input/capture. The isolated app remains running empty because its launcher has no stop channel; no unrelated Python process was terminated. Settings were injected into local INI files rather than user app stores; native stores were observed read-only.

The branch remains draft; do not merge until this blocker is resolved, affected native flows pass, whole-window pixels are inspected by the review team and final CI is green.
