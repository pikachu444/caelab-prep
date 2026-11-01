# Working program-specific UI comparisons

This is a user-requested extension of the UI rebuild, beyond the earlier single
P0–P3 composition. It preserves the existing document, provider, validation,
selection, command history and codecs. It does not add the referenced solvers or
their full product features. Visual fidelity and functional regression are
separate verdicts; actual Windows input/GPU acceptance is still on hold.

## Entry points and shared state

```
caelab-prep compare
caelab-prep compare materials.caeprep
caelab-prep compare --rad examples/rad/stiffened_panel_0000.rad
caelab-prep compare --rad model.caeprep
```

The selector switches working approaches to the **same session, object, values,
references and Undo history**. A valid draft is finished before switching; an
invalid or stale draft blocks the switch and remains in its original view.
Save produces the existing `.caeprep` format. Native mode retains separate RAD
export. `--no-3d` disables VTK for layout inspection and cannot demonstrate a
rendered model or native picking.

The comparison header's **Reference / differences** button explains each
approach's source scenes and deviations. Product names identify references;
these are CAELab Prep views, not vendor software or endorsed implementations.

## Source-to-implementation map

The authoritative collected scenes remain in
`benchmarks/2026-10-30/products/*.json`. They distinguish static observations,
documented instructions and unknown behavior. They are not native reproduction
tests. PrePoMax supplements that collection with its official 2.5.0 manual,
v1.0.0, 2026-03-08, pp3/5/7/27–29.

| Reference | Implemented composition/interaction | Source scenes | Important differences / missing evidence |
|---|---|---|---|
| HyperMesh 2025 / curve 2025.1 | Lower-left Name/Value Entity Editor; scalar focus completion; table-left/plot-right | HM03/04/05/21/22 | Original PSHELL crop was inspected. Whole-window proportion and full Curve Editor pixels are not newly verified. Prep keeps atomic table Apply, its own units and typed curve references. |
| PrePoMax 2.5.0 | Compact icon commands, tall FE tree, bottom output; material dialog | Manual p3 Fig1, p5 Fig2, p7, p27–29 Fig14 | Main screen/tree/library figures inspected. Exact material edit form is absent from the acquired pages; its property dialog remains provisional. No CalculiX, expression parsing or creation tools. |
| Abaqus/CAE 2025 docs | Property module; tree double-click; grouped material dialog; Data/Plot pages | AB01/04/06/07/23/27/29 | Existing observation records, not newly downloaded pixels. Native `.cae`, expressions, ambiguous/multiple selection and material-law construction are absent. Extra Prep reference/unit fields are not an Abaqus material mapping. |
| COMSOL 6.3 docs | Model Builder / selected-node Settings / Graphics; grouped settings and table | COM-T02/03/09a/09b/09c | Settings crop observations are recorded; new image retrieval failed. No expression evaluator, physics, Build/Compute or named boundary sets. Prep's manual Apply is a disclosed difference. |
| midas NFX | Material command groups; separate material form; simultaneous table/graph | nfx-workspace/material/property/query/plastic | 2024 education and separate HTML curve sources are not one continuous app run. Current source screenshots could not be downloaded. Creation/case/set operations are absent. |
| MIDAS MeshFree | Separate material form and spreadsheet/graph; independent model navigation | meshfree-trees/assign/material/table/select | 2026 education, actual UI build unknown. No fake analysis-case subset, material assignment or solver operations. Exact form/cancel appearance remains unverified. |
| Naksha | Outline/Details, command tabs, local selection strip; table/plot | NA01/02/03/05/07/09 | 0.5.07 main image inspected; Details is empty there, so scalar composition/commit timing remains unverified. Library build differs/unknown; no imported strain-rate law, box/multiple pick or library import. |
| BeidPrep | MODEL beside FORM/TEXT and model view; bottom selection strip | BE01/02/03/05/07/09 | Web 2.0/build unknown. Card commit timing and curve editor are not established by the image. Bottom APPLY belongs to selection and is not fabricated as card Apply. No digitizer/node-move preview/new cards. |

For all approaches, only the current provider's supported objects and actions
are offered. A source's extra menu items are not filled with fake commands.
Unknown commit/cancel behavior is not inferred from a visible button. Shared
Prep safety rules are retained and disclosed where original behavior is unknown.
HyperMesh-style scalar edits complete immediately; Prep vectors retain explicit
Apply/Revert for an atomic three-component command and one Undo.

## Reuse interface and ownership

`ui/reference_components.py` owns the reusable presentation seam;
`ui/reference_workspace.py` binds the two concrete Prep consumers to it:

- `ReferenceBindings` supplies Qt views, existing QActions, Apply/Revert
  callbacks and optional renderer/selection-tool handles. It owns no document.
- `ReferenceAdapter` composes command, docking, editor-interaction and curve
  arrangement objects. The registry swaps these objects, rather than copying
  controllers or branching the application by program name.
- The same adapter is used by neutral `GalleryWindow` and native `MainWindow`.
  Solver/session/VTK and concrete gallery implementations are not imported by
  the reusable adapter module. Consumer assembly stays in `reference_workspace`.
- `PropertyEditor` has replaceable column, settings and form presentations.
  Typed editor widgets and draft buffers survive a presentation change. Its
  header owns column widths; scrolling shares that offset. Invalid rows carry
  markers/tooltips, with one focused error detail instead of expanding every row.

The property widget can also bind to an existing host's Apply/history service
without creating a Prep Document or dispatcher. `test_property_presentations.py`
exercises that independent QWidget host, including unit conversion, failed
validation and one Apply/Undo. This demonstrates the host seam, not integration
into a live Workbench installation. Workbench keeps its own MDO/project/run owner.
The adapter tests separately reject transitive imports of application/session,
gallery/catalogue and VTK while loading the common composition module, and bind
it to a QWidget/QAction host's existing Apply callback.

## Checks and visual evidence

`test_reference_adapters.py` checks both real consumers, layout/interaction
differences, immediate editing and dialog behavior. `test_program_comparison.py`
checks shared selection/values/references/history, invalid/stale drafts, native
modal boolean transactions, saving/reopening and RAD export across approaches.
Existing common-widget/document/file-flow tests remain applicable.

Offscreen captures use temporary INI settings, installed Windows fonts and no
VTK renderer. The untouched `cf74b0a` source was copied into ignored `.review`
before editing for repeatable before/after captures. The reference pixels are
analysis-only `.review` inputs, never shipped product artwork. Resized/letterboxed
reference comparisons disclose that scaling and do not measure vendor DPI.
The representative HyperMesh pair additionally selects an actual RAD
`/PROP/SHELL/1` shell property: its thickness is 2.0 in an mm deck context.
The source crop is PSHELL_2 with T=1.25 and no visible unit. Object name/card ID
appear in the Prep inspector header; its only editable provider field is shell
thickness. Material is linked through the RAD PART, so the PSHELL Material row
is not fabricated. This is a shell-property editing comparison, not identical
cards, values or a claim that all source metadata is editable.
Naksha's supported Undo/Redo commands are in the small quick-file row. Only the
working Materials context is included; unimplemented Home/Results content is
omitted rather than filling a ribbon with inert controls.

Additional exact-image downloads were blocked by the local network restriction;
no installation or security setting was changed to retrieve them. Documentation
observations support the working differences above, but do not certify full
pixel fidelity for the missing images. Actual Windows input, complete GPU
captures, display scaling and native file/dialog workflows remain unverified.

Applied guidance: `cae-desktop-ux` QT-PANELS/FC-PROPERTY/QT-ACCESS for draft-safe
resizing and visual evidence; `ponytail` for retaining typed bindings and
commands; Matt `codebase-design` for the shared interface and real host adapters;
pstack `principle-test-behavior-not-implementation` for externally observable
value/file checks. tstack workflows were inspected but publication/review
automation was not invoked. No hooks or user security configuration were changed.

## This milestone's recorded result

Independent offscreen QA ran the six affected suites: **105 passed**, plus
**11 independent user-flow cases**. The final Naksha quick-command/pane-ratio
changes then passed their two affected geometry/draft-preservation checks;
unaffected suites were not repeated. These results are distinct from the
handoff's older 121 passed/11 skipped and from the earlier 163/1 baseline run.

The independent QA found a real hidden-table draft-loss regression. The fix
tracks the selected curve editing context rather than tab visibility; save,
close, cancellation, discard, invalid input and save failure were rechecked.
Review also found the embedded Exit/None-selection defects, consumer transitive
imports, missing vector Apply, tab row spacing and source-layout differences.
All reported defects were corrected and rechecked by their original reviewers.

The critic closed its five specific findings after source/pixel reinspection;
the defender accepted the working compositions and disclosed differences; the
regression reviewer closed Exit, None selection and adapter import dependence.
This closes those findings, not full source-product fidelity or native Windows
acceptance. Five programs lack newly available original pixels; PrePoMax's
material editor and Naksha's populated Details remain source-evidence gaps.

Reference/implementation image pairs and baseline comparisons are under ignored
`.review/program-variants/final`. The HyperMesh representative is
`hypermesh-shell-property-reference-vs-implementation.png`; the eight shared
material captures remain available. Actual Windows/GPU, original-product runs,
Library upload, push, PR and merge have not been performed.
