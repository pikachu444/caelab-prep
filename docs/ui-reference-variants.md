# Working program-specific UI comparisons

This document describes the eight approaches and separates the merged PR15 source map at `a48d3b4` from the earlier source map at
`f4d12d078aac08f5e4474e362ac18c1aa128386b`. The earlier implementation
record described them as an extension beyond its single P0–P3 composition. That
description is project history, not evidence that the user approved reducing
the original requirement to one composition. The implementation preserves the
existing document, provider, validation, selection, command history and codecs;
it does not implement all features of the referenced products.

The current target and acceptance contract are defined in
[DESIGN, “달성 목표와 제품 완료 기준 (2026-11-02)”](../DESIGN.md#delivery-goals).
All eight approaches must support the same T1–T6 tasks through distinct
presentation and interaction, including command groups and task flow, while
sharing the model, commands, validation and reusable components. The source map
below describes the handoff implementation and its evidence gaps; it is not an
acceptance matrix for that target. Current unresolved status belongs in
[the remaining-work table in section 19](../CURRENT_STATE.md#remaining-work); sections 1–18 are not implied
complete. Functional regression, UI quality, usable engineering tasks and
source-product comparison require separate verdicts. Actual Windows input/GPU
acceptance remains unverified for these eight approaches.

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

## Merged implementation and limits

[PR #15](https://github.com/pikachu444/caelab-prep/pull/15) connects native material/section creation, copy/delete and PART assignment; curve rows/text paste and typed node/element group membership; supported BCS/CLOAD/initial velocity/TYPE7 conditions; verified display-unit conversion; CAD candidate adoption and Starter/Engine export. It did not implement CSV file import/export: the earlier CSV claim confused pasted comma-separated text with file operations. The eight adapters consume the same provider commands and typed editors. `test_modeling_ui.py`, `test_conditions_ui.py`, `test_groups_ui.py` and `test_native_units_ui.py` exercise the corresponding tasks and invalid drafts across all eight approaches. This replaces the old provider's scalar-only limitation; it does not supply vendor-native formats or all vendor features.

The merged N01/N02/N15 support checkpoint adds persistent analysis cases, standalone
external mesh import and shared CSV-file/plot-drag editing in RAD and neutral
hosts. Its exact code, execution and review status belongs in
[section 19](../CURRENT_STATE.md#remaining-work), rather than being inferred
from this source map. The eight same-task source-product comparisons and
resulting UI corrections remain N03–N10; none is closed by adapter counts or
internal tests. Windows GUI and actual Workbench validation remain N12–N14.

The original source map below is a **handoff-era observation**, not the present feature support table. Its statements that creation, assignment or set operations were absent describe `f4d12d0`. Current supported commands are listed in [README](../README.md); source-product operation/appearance gaps remain unverified. Offscreen UI checks and the separate X11 Qt/VTK render/pick job are reported separately in section 19.

Actual external reuse is now implemented in [Workbench PR #54](https://github.com/pikachu444/caelab-workbench/pull/54): MDO consumes `NumericEdit` while retaining its own service/history; RAD `.caeprep` files open in independent Prep processes through the existing program/file/JobManager boundary. This is stronger than the old host seam fixture but is not live GUI IPC/MCP or Windows acceptance.

<a id="product-access"></a>

## Earlier original-product access investigation (2026-11-02)

**This is the earlier access investigation, not an inventory of the current native Windows PC.**
Current Windows installations, license grants and T1–T6 execution remain unverified. No new original-product T1–T6 execution was completed in that access check.
An official download page, tutorial, screenshot or free edition is not a running
editor. The workspace/PATH inspection found no installed executable or installation
archive for these eight products and no Wine, Mono or .NET command. This is a
check of the Linux workspace, not of the user's Windows PC. The investigated cloud/Linux host was
Ubuntu 24.04.3 with software GL. Windows GUI work was deferred at that point; no trial application, email, account creation or purchase
was submitted.

| ID / product | Verified acquisition and runtime path | Unresolved condition / next executable step |
|---|---|---|
| N03 HyperMesh | [Official 2026 platform requirements](https://help.altair.com/hwsolvers/altair_help/topics/getting_started/platform_support_r.htm) list RHEL/CIQ Rocky 9.4 and dedicated NVIDIA for Linux GUI. [Altair One trial](https://2025.help.altair.com/altairone/topics/marketplace/application_try_free.htm) and [eligible student edition](https://www.siemens.com/en-us/company/academic-future-workforce/engineering-student-resources/engineering-student-software/altair-student-edition/) are acquisition paths, not existing entitlements. | Obtain an authorized build and suitable runtime. The user's **2024.1** baseline, collected 2025/2025.1 scenes and current 2026 download documentation are three different versions; do not silently substitute one. Current Ubuntu/software GL is not the documented 2026 support combination. |
| N04 PrePoMax | [Official portable ZIP/source downloads](https://prepomax.fs.um.si/downloads/): GPLv3, .NET Framework 4.8, Windows EXE and Win64 ActiViz dependency. 2.5.0 remains available; 2.6.0 stable and 3.0.0 RC2 are also listed. [2.6.0 manual p.3](https://prepomax.fs.um.si/wp-content/uploads/2026/09/PrePoMax-v2.6.0-manual.pdf) describes VM/emulator/Wine for Linux. | No paid-license barrier was found. Download a fixed version and prove the Windows runtime or Wine compatibility; Wine is absent here. Public source does not establish a working native Linux build. Material creation/assignment/cancel must be run, not inferred from library or contour figures. |
| N05 Naksha | The live [product page](https://agentnaksha.com/product.html) identifies a **Windows/Linux desktop app**. Clicking “Get Naksha free” opens the [name/work-email request form](https://agentnaksha.com/contact.html?interest=free); the vendor says Free includes commercial use and is sent on request. | No public runnable web editor, installer or source build was obtained. A Linux build must be supplied through the official distribution path and its exact build/terms recorded. The old 0.5.07 image with empty Details cannot establish scalar layout or commit/cancel behavior. |
| N06 Abaqus/CAE | [Learning Edition 2026](https://3dswym.3dexperience.3ds.com/wiki/simulia-community/learning-edition-software-downloads__NXifU43Q7yHzTiCX9yEaw) is free, Windows-only, limited to 1,000 structural nodes and personal/educational use. [Commercial download rights](https://www.3ds.com/about/company/facts-and-faqs) require a company-associated 3DEXPERIENCE ID and software entitlement; [supported platforms](https://www.3ds.com/support/hardware-and-software/simulia-systems-information) are version-specific. | Establish a permitted license/use path and runtime. Confirm that the permitted use covers this product-development comparison. Compare Property → material → section → assignment, units and errors with a declared physical mapping; a RAD law is not automatically an Abaqus law. |
| N07 COMSOL | [Current download](https://www.comsol.com/product-download) lists 6.4.0.429 and requires COMSOL Access with an attached subscription license or sales-provided trial; 6.3 is still selectable. [6.4 requirements](https://www.comsol.com/system-requirements/64/general) support Ubuntu 24.04. | The host OS is supported, but no entitled installer/runtime was obtained. Confirm modules, graphics and a fixed version after access. COMSOL Runtime or a published simulation app is not the editable Model Builder required for T1–T6. RAD export/solver execution is not COMSOL Build/Compute. |
| N08 midas NFX | [2026R1 installation page](https://support.midasuser.com/hc/en-us/articles/34146232208793-NFX-Installation-Files), [Windows requirements](https://support.midasuser.com/hc/ko/articles/17928004837273-NFX-시스템-요구사항), and [current 14-day trial](https://www.midasmts.com/en/trial-demo): form → emailed activation key → download → activate. | Windows and an existing entitlement or issued trial are missing here. Use one fixed running version for the continuous task; separate 2024 education and curve HTML sources do not prove it. |
| N09 MIDAS MeshFree | [2026R1 installation page](https://support.midasuser.com/hc/ko/articles/34285656928921-MESHFREE-설치-파일-및-개정-내용), [Windows requirements](https://support.midasuser.com/hc/en-us/articles/17928026014745-System-Requirement-Specifications-for-MESHFREE), and the same [current 14-day trial](https://www.midasmts.com/en/trial-demo); [official request entry](https://landing.midasuser.com/en/gate/mech/trials/mf/step1). | Windows and an issued entitlement/trial are missing. Old 90-day offers are not the current verified path. Before execution, map geometry/body regions, material, units, discretization, conditions and case/result meaning; an FE element operation must have an explicit engineering-equivalent flow or remain an unresolved mismatch, not automatic N/A. |
| N10 BeidPrep | Live [official 2.0 beta page](https://beidersim.com/beidprep.html): Windows 10/11, 218 MB installer, offline/no account, all features free through 2026-12-31, [download without signup](https://beidersim.com/download). [Official repository](https://github.com/BeiderSim/BeidPrep) publishes documentation, not application source; its older v1.0 README states proprietary source. | The download was actually clicked. The browser returned a path, but the file did not exist in either shared filesystem, so receipt/hash verification failed; a direct HTTP request returned 403 without evidence of a bot block. Windows runtime is separately absent. This is not a paywall conclusion. The existing [1.0.1 small-deck execution](beidprep-evaluation.md) and 2.0 website images are distinct; neither completes T1–T6. |

The two inspected acquisition screens are preserved as
[Naksha request form](benchmarks/2026-11-02-access/naksha-access.jpg) and
[BeidPrep no-signup/Windows download page](benchmarks/2026-11-02-access/beidprep-access.jpg).
They prove the observed distribution UI only. The browser extension lacked its
originating context; the independent public-page actions used the cloud browser.
No Android display, user-local session or native vendor application was observed.

When access is available, retain the same two parts, two material/section pairs,
curve and condition/case goals and record full-window/modal/error/cancel behavior,
input count and saved/native results. State each product's physical mapping and
unsupported result explicitly. BeidPrep's selection APPLY must not be treated as
card commit; MeshFree's discretization must not be fabricated as a RAD FE mesh.
Acquisition progress leaves all eight comparison rows open.

## Source-to-implementation map

The authoritative collected scenes remain in
`benchmarks/2026-10-30/products/*.json`. They distinguish static observations,
documented instructions and unknown behavior. They are not native reproduction
tests. PrePoMax supplements that collection with its official 2.5.0 manual,
v1.0.0, 2026-03-08, pp3/5/7/27–29.

N03–N10 retain G0's same-task evidence contract for every approach using these
sources and identify missing observations or original-product runs. A documented
pattern, an inspected screenshot and an actual operation in the source program
are different evidence levels. This table does not establish that T1–T6 have
been performed or reproduced in any source program.

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

At the handoff these were real presentation and interaction seams, but the
limited provider actions did not satisfy the product goal. G1 requires
T1–T2 in all eight approaches on actual parts with material/section creation and
assignment; G2 adds T3–T4 with real curve and condition relationships. Existing
scalar editing or a neutral `Associated curve` reference does not demonstrate
those operations. Detailed requirements and completion criteria remain in
DESIGN rather than being redefined by the current provider's capabilities.

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
The captures in this paragraph are historical; later PR #15 screenshots do
not retroactively change their scope. In the handoff captures, Naksha's Undo/Redo commands were in the small
quick-file row and only its Materials context was included. The G1–G4 adapter
now also provides Selections and Conditions, using the same shared commands.
Unimplemented Home/Results content remains omitted.

During that earlier capture session, additional exact-image downloads were blocked by its local network restriction;
no installation or security setting was changed to retrieve them. Documentation
observations support the working differences above, but do not certify full
pixel fidelity for the missing images. Current Linux X11 CI covers actual Qt/VTK pixels and QTest picking in 16
default two-element scenes. It does not cover a complete T1–T6 native workflow
or original-product equivalence. Current Windows input, GPU capture, display
scaling and full native file/dialog workflows remain unverified.

The earlier implementation report recorded applied guidance from
`cae-desktop-ux` QT-PANELS/FC-PROPERTY/QT-ACCESS for draft-safe
resizing and visual evidence; `ponytail` for retaining typed bindings and
commands; Matt `codebase-design` for the shared interface and real host adapters;
pstack `principle-test-behavior-not-implementation` for externally observable
value/file checks. tstack workflows were inspected but publication/review
automation was not invoked. It reported no changes to hooks or user security
configuration. This statement identifies reported guidance; installation or a
skill name alone is not proof that the required product review took place.

## Historical implementation review record

The following counts and dispositions are the earlier milestone's recorded
results, not a rerun on the preservation commit or acceptance of the current
G0–G4 target. Review reports must be read with their actual task and environment
scope; the existence of a report does not establish a source-product or full
Windows workflow comparison.

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
The milestone report states that these reported defects were corrected and
rechecked by their original reviewers. This does not establish that all product
requirements were examined or met.

The critic closed its five specific findings after source/pixel reinspection;
the defender accepted the working compositions and disclosed differences; the
regression reviewer closed Exit, None selection and adapter import dependence.
This closes those findings, not full source-product fidelity or native Windows
acceptance. Five programs lack newly available original pixels; PrePoMax's
material editor and Naksha's populated Details remain source-evidence gaps.

The milestone recorded reference/implementation image pairs and baseline
comparisons under ignored `.review/program-variants/final`. Those local paths
are not versioned evidence guaranteed to be available in a fresh checkout.
The recorded HyperMesh representative is
`hypermesh-shell-property-reference-vs-implementation.png`; the eight shared
material captures were also reported there. The report's statement that upload,
push, PR and merge had not occurred described that earlier point in time;
[preservation PR #13](https://github.com/pikachu444/caelab-prep/pull/13) and the
handoff commit are later repository history. They do not supply the missing
actual Windows/GPU or same-task original-product acceptance.

<a id="reference-materials"></a>

## Reference material map


2026-11-01 인계 기준: 이 문서는 2026-10-30의 **7제품 자료 수집** 색인이다. 현재 구현 대상은 PrePoMax를 포함한 8개 방식이며, 후속 공식 매뉴얼 근거·현재 구현·미확인 차이는 [8방식 자료](ui-reference-variants.md)에 모은다. [PR #15](https://github.com/pikachu444/caelab-prep/pull/15)의 작업 기능이 병합됐다는 사실과 원제품에서 같은 작업을 실행해 동등성을 확인했다는 판정은 구분한다. 후속 구현·증거·완료 기준은 [남은 작업](../CURRENT_STATE.md#remaining-work)에 둔다.

2026-10-30. 기존 개요 비교를 [7제품 상세 근거 자료](benchmarks/2026-10-30/README.md)로 확장했다. 기술문서 URL 110개, 화면·그림 발췌156개, 작업장면123개를 연결했다. UI포함 발췌141개와 모델뷰/렌더15개를 구별한다. 숫자는 전체 재현 준비나 제품 품질 점수가 아니다.

Abaqus/CAE2025, COMSOL6.3, HyperMesh2025/2025.1, midas NFX, MIDAS MeshFree, Naksha, BeidPrep을 조사했다. NFX와 MeshFree는 별도 제품이며, Abaqus 문서는 vendor-origin 매뉴얼의 Virginia Tech 호스팅 미러다. 자료판·앱빌드·문서그림의 시점 차이를 색인에 기록한다.

## 근거를 찾는 경로

| 필요한 것 | 자료 |
|---|---|
| 제품/버전·실제 확보량·남은 한계 | [자료지도](benchmarks/2026-10-30/README.md) |
| 토론 후 역할분담·S/D/V/R·장면 판정 | [방법과 판정](benchmarks/2026-10-30/method.md) |
| 메뉴·필드·선택·결과·오류/취소·저장과 원문 | 자료지도의 `products/*.json` |
| 공용 Action/트리/속성/표·곡선/메시/저장 계약 | [공용 자산 요구](benchmarks/2026-10-30/common-assets.md) |
| 화면 실측과 앱 DPI/문서 렌더 구별 | [화면 관측](benchmarks/2026-10-30/layout-observations.md) |
| 7제품×9과업의 남은 동작 결손 | [교차검토](benchmarks/2026-10-30/audit.md) |
| 현재 8방식의 실제 구현과 원제품 근거 한계 | [표현별 구현·차이](ui-reference-variants.md) |
| 현재 실행 결과와 남은 동일 작업 비교 | [실행 근거](../CURRENT_STATE.md#current-progress) / [남은 작업](../CURRENT_STATE.md#remaining-work) |

정상 문헌경로가 있는 장면과 과업 전체 준비·직접 실행을 분리한다. 이 2026-10-30 자료 수집에서 전제품의 실제 앱 재현은 0건이며 실패/취소/저장 재열기가 다 연결된 전체 과업 준비로 보고하지 않는다. 별도의 BeidPrep 1.0.1 실행은 아래 과거 기록에 한정한다. 공개 이미지의 버튼 존재를 후속 동작의 보장으로 해석하지 않는다. 현재 Linux X11 16건도 Prep 두 요소 장면의 배치·렌더·선택 검사이며 원제품 실행 증거가 아니다.

## 공용 설계로 연결할 차이

정보 밀도·도구 계층은 HyperMesh/Abaqus/Naksha, 설정과 단위/원문은 COMSOL/BeidPrep/HyperMesh, 조립·조건/케이스는 NFX/MeshFree/HyperMesh를 비교한다. 다른 제품의 용어를 하나의 타입으로 강제하지 않는다. Step과case, geometry component와solver part, mesh품질과해석오차는 구분한다.

P0의 근거 요구는 실제 값이 채워진 장면을 바탕으로 작업·상태·입력·환경을 고정하는 것이다. 대표사진 2~3장이나 이 자료집의 존재만으로 전체 과업의 비교 준비를 완료 처리하지 않는다. 공용 계약·위젯·실제 앱 연결은 이미 구현된 범위를 재사용하고, 다음 비교에서는 현재 지원하는 연속 작업을 원제품의 진입·선택·입력·확정/취소·오류·저장 결과에 대응시킨다. 원제품 접근이 없으면 그 비교만 미확인으로 남기고 구현 상태와 섞지 않는다.

[BeidPrep1.0.1 시험](beidprep-evaluation.md)은 과거 별도 실행기록이다. 2.0 웹자료를 그 실행결과로 승격하지 않는다. 기존 엔진 도입과 복잡 신규 meshing커널의 경계는 [메셔 로드맵](mesher-feasibility-roadmap.md)을 유지한다.


## 이전 절 링크

<a id="merged-baseline-and-current-checkpoint"></a>

이전 절 **Merged baseline and current checkpoint** → [옮긴 내용](#merged-implementation-and-limits).

<a id="original-product-access-checked-on-2026-11-02"></a>

이전 절 **Original-product access checked on 2026-11-02** → [옮긴 내용](#product-access).
