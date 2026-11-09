# N23: bounded paired-face offset experiment

2026-11-02. This is an independent geometry experiment, not a shipped Prep feature. No repository/core/UI file was modified. `results/result.json` is the measured result; `execution.json` records the subprocess exit code and wall time. The original sharp-corner investigation remains in `probe_offsets.py` / `probe-offsets.log`; it is not silently substituted for the rounded constant-thickness bend.

## What actually ran

Installed `cadquery-ocp==7.8.1.1.post1` (OCP reports 7.8.1.1), OCCT 7.8.1, CadQuery 2.7.0, Python 3.12. The explicit face indices are stored against the source BRep SHA-256. They are not automatic face recognition and are not stable identifiers for a changed CAD file.

`paired_offset.extract` validates the selected outer/inner plane or coaxial-cylinder pairs and declared millimetre thickness, deep-copies the geometry, sews each selected side, offsets each side toward the reference surface, takes the Boolean common, and sews the result. Existing OCCT offset, boolean and sewing operations do the geometry work. A face is never silently discarded to pass: face count, connectivity, overlap area and topology are checked. The operation returns a candidate; `write_candidate` atomically replaces the explicitly supplied candidate destination only after the checks pass.

The fixed recipe uses `PerformByJoin`, `BRepOffset_Skin`, `GeomAbs_Intersection`, `Intersection=False`, `SelfInter=False`, and `1e-6 mm` coincidence tolerance. There was no repeated algorithm-option search. The initial sharp-L probe showed that OCCT could connect two planes; because its corner band is not a uniform normal-ray-thickness wall, that topology success was not accepted as thickness proof. The final contract rejects sharp junctions without an explicit rounded bend pair.

Two synthetic inputs were authored from dimensional definitions:

- Plate: 40 × 25 × 2 mm. One opposed plane pair. Result at z=1 mm, one face, area 1000 mm².
- Rounded L: 40 mm horizontal straight arm, 28 mm vertical straight arm, 25 mm width, inner radius 10 mm and outer radius 12 mm. Two opposed plane pairs plus one explicitly selected cylindrical corner pair. Result has three faces, two shared 25 mm seams, one connected component, eight free boundary edges and no nonmanifold edges. Its analytical midsurface area is `25*(40+28+pi*11/2)` = 2131.9689898685965 mm².

`fraction_from_outer=0.5` means midsurface. The separately checked plate fraction 0.25 is a reference surface at z=0.5 mm, not a midsurface. Its geometric shift from the midsurface along the chosen outer normal is `(0.5-fraction)*thickness`. This is not yet a solver-specific shell-offset keyword mapping.

## Measured checks and limits

The midpoint checks for both positive fixtures were repeated on their saved/reopened candidate BReps. The separate quarter-thickness reference surface was checked in memory only. Source BRep bytes before/after extraction matched exactly. The result contains input/output hashes and explicit face manifests. The positive checks use exact plane/cylinder types and independent dimensional/area/boundary expectations, plus 25 UV samples per face including boundary points.

| Check | Plate | Rounded L |
|---|---:|---:|
| Area error (mm²) | 2.27e-13 | 9.09e-13 |
| Bounding box error (mm) | 0 | 0 |
| Largest normal-ray-to-paired-face error (mm) | 0 | 2.67e-15 |
| Largest boundary error (mm) | 0 | 1.78e-15 |
| Shared-edge-to-face error (mm) | n/a: no seam | 8.89e-16 |
| Normal/tangent error, `1-dot` | 0 | 0 |

Fixed acceptance was `1e-6` for these length/area error measurements and `1e-8` for `1-dot`. These numerical errors describe these analytic fixtures and samples; they do not prove general geometry robustness or engineering accuracy.

Six rejected inputs preserved both the original shape bytes and an already existing candidate output: tapered wedge/non-opposed faces, sharp junction, wrong declared thickness, missing explicit bend pair, offset outside the wall, and undeclared units. Manual alternatives are to select a verified opposite face pair and an explicit valid offset, or first prepare/split the geometry externally. Variable thickness cannot be made uniform by relabelling its thickness; a thickness-field/junction workflow remains outside this prototype.

The measured run completed in 2.881 seconds including process imports, with peak RSS 427.55 MiB. The subprocess had a 120-second timeout; the 2 GiB RSS budget was checked after execution, not imposed as an OS allocation limit. Individual positive cases took approximately 0.025 and 0.072 seconds including their geometric checks. These are two small synthetic inputs, not a production throughput benchmark.

## Reproduce

From `scripts/evaluation/midsurface_recipe`, with the pinned environment:

```sh
python run_f1.py
python render_geometry.py
```

Use an outer subprocess timeout of 120 seconds as recorded in `execution.json`. The runner writes only this experiment's `results/` directory. `geometry-preview.png` is drawn from the actual saved BRep geometry; it is a scientific inspection plot, not a Prep GUI or meshing screenshot.

## What remains unproven

This establishes one existing-backend recipe on a plate and a rounded L. It does not close N23 or the complete documented F1/F2 gate. In particular:

- These are self-authored fixtures, not an execution of an official SHAPER macro/sample. That documented official-example reproduction remains unfulfilled.
- Automatic opposing-face selection, rib/boss/junction handling, variable-thickness or freeform surfaces, arbitrary bend radii, branches, multi-solid input and global self-intersection elimination were not implemented or qualified.
- The plan's fixed F2 shape set, including a simple rib/joint, remains open. The sampled checks are not a general proof beyond these cases.
- No document/revision-aware CAD face identity, GUI pairing/manual correction, candidate adoption, mesh generation, shell material/thickness/normal/native offset assignment, Undo, project persistence, or solver readback was added to Prep.
- BRep file roundtrip here is geometry-only; it is not `.caeprep` or RAD native roundtrip. No Windows or commercial-application validation occurred.

A non-author reviewer reran the same fixed recipe in a separate directory: exit 0, 2.123 seconds, peak RSS 428.63 MiB; both positive source/output BRep hashes matched, and all six safe rejections passed. The detailed geometric postconditions are fixture-specific checks in the runner, not a qualification of every input accepted by the reusable wrapper. The next step is the still-unfulfilled official-example gate, a fixed F2 set, and only then document/UI/native integration. The fallback is manual prepared surfaces with explicit thickness/normal/offset; it is not a claim that general automatic midsurface extraction is now available.

## Primary sources actually checked

- OCCT 7.8.1 offset API, including sign, join semantics and self-intersection limitations: https://github.com/Open-Cascade-SAS/OCCT/blob/V7_8_1/src/BRepOffsetAPI/BRepOffsetAPI_MakeOffsetShape.hxx
- OCCT 7.8.1 sewing API: https://github.com/Open-Cascade-SAS/OCCT/blob/V7_8_1/src/BRepBuilderAPI/BRepBuilderAPI_Sewing.hxx
- Installed OCP 7.8.1.1 binding docstrings for `PerformByJoin`, `PerformBySimple`, `BRepBuilderAPI_Copy`, `BRepBuilderAPI_Sewing` and `BRepTools.Write_s`.
- OCP wrapper purpose/source: https://github.com/CadQuery/OCP . Its wrapper is thin; API availability is not midsurface capability proof.
- Installed CadQuery 2.7.0 `Face.normalAt` source was read: normals are obtained from OCCT face geometry. CadQuery builds the synthetic input fixtures and supplies inspection convenience methods; it does not replace the evaluated OCCT operations.

OCCT carries LGPL-2.1 with its stated exception; the OCP wrapper repository uses Apache-2.0. No vendor executable or vendor CAD model is included. The input definitions and prototype are newly authored for this experiment.
