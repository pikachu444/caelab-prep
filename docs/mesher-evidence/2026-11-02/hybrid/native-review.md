# N26 native family probe — 2026-11-02

This is a two-fixture native mapping investigation, not N26 F1/F2, mixed-interface, GUI, or product completion. Product files were not changed. There was one Starter attempt per family and one Engine attempt (pyramid only), with no solver shim, fallback, smaller fixture, changed connectivity, density correction, or blind rerun.

## Official mapping and boundary

The Radioss 2024 `/BRICK` manual comment 6 and Figure 3 explicitly allow degenerate solids through repeated node numbers. Its BRICK_4.svg gives the prism mapping; BRICK_7.svg gives the pyramid mapping and labels that pyramid pattern “not recommended but sometimes needed for complex meshes”. `gmsh-order.json` contains the actual Gmsh 4.15.2 reference ordering.

| Gmsh physical vertices | Native /BRICK slots | Actual reader family |
| --- | --- | --- |
| Prism6 a,b,c,d,e,f | a,b,c,a,d,e,f,d | Eight-slot BRICK / listing SOLID-HEXA |
| Pyramid5 a,b,c,d,e | a,b,c,d,e,e,e,e | Eight-slot BRICK / listing SOLID-HEXA |

`/PENTA6` is not an ordinary solid-prism alternative: its official manual restricts it to thick shells, Isolid15 with PROP20, and directs ordinary solid prisms to degenerate BRICK. These mappings preserve the five/six unique geometric vertices; they do not create a dedicated five/six-node solver family.

Sources:
- https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/brick_starter_r.htm
- https://2024.help.altair.com/2024/hwsolvers/rad/images/solvers/BRICK_4.svg
- https://2024.help.altair.com/2024/hwsolvers/rad/images/solvers/BRICK_7.svg
- https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/penta6_starter_r.htm
- https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/prop_type14_solid_starter_r.htm
- https://gmsh.info/doc/texinfo/#Node-ordering

## Fixed native profile and fixtures

Before either solver launch, the profile was fixed to LAW1 density 1e-9 Mg/mm³, E=1000 N/mm², nu=.25; PROP14 Isolid17 (documented 2×2×2 integration), Ismstr4, Icpre3, Iframe1. All physical vertices were fixed with BCS. End time=1e-6 s and animation interval=5e-7 s. The source-level one-point Isolid1 volume formula predicts 75% of geometric pyramid volume; no Isolid1 native trial was made and no density compensation was used. Isolid17's exact dispatch and eight-slot lumped mass are documented separately in `reader-review.md`.

| Fixture | Unique vertices | Exact volume | Expected/actual total mass | Native counts | Execution |
| --- | --- | --- | --- | --- | --- |
| pyramid5 | (0,0,0),(2,0,0),(2,3,0),(0,3,0),(1,1.5,4) | 8 mm³ | 8e-9 / 8e-9 Mg | NUMNOD5, NUMELS1, NUMELC0 | Starter rc0, 0 errors/0 warnings; Engine rc0, normal termination, 8 cycles |
| prism6 | (10,20,30),(12,20,30),(10,23,30),(10,20,34),(12,20,34),(10,23,34) | 12 mm³ | 1.2e-8 / 1.2e-8 Mg | NUMNOD6, NUMELS1, NUMELC0 | Starter rc3, restart-file writing Segmentation Violation / ERROR760; Engine not executed |

The failed prism listing has no input syntax error and reads its family/count/mass correctly. This does not establish why restart writing failed, nor prove that the prism profile is unsupported. Its normal-termination requirement remains **failed / unresolved**. The exact input pair and logs are preserved under `prism6/` for an independent environment run; no successful solver result is claimed for it.

## Important physical limitation

Full-integration total volume/mass is correct in both listings, but the standard BRICK lumped mass is equal per eight slots. Repeated vertices therefore accumulate multiple shares. The pyramid listing's mass center is (1,1.5,2), while the uniform-density geometric centroid is (1,1.5,1). The prism listing's center is (10.5,20.75,32), versus geometric (10+2/3,21,32). The pinned `smass3.F` source explicitly computes density×volume/8 and adds equal slot masses and moments; this is not an input-coordinate typo.

Consequently, the official encoding is topologically and geometrically documented, but it is **not established as a lossless dynamic/mass-distribution substitute for an independent Pyramid5/Prism6 formulation**. N26 must make that formulation distinction explicit and establish its engineering acceptance criteria before exposing a supported hybrid native profile. Geometry orientation, mixed shared-face conformity, quality, mixed solver behavior, and F2 remain separate untested gates.

## Evidence integrity and observer correction

`result.json` is the unchanged first-run report, including its failed assertions and binary/input/artifact hashes. Its initial observer mistakenly expected NUMELC (four-node shell count) to equal one instead of NUMELS (solid count). `reassessment.json` corrects that labeling from the existing listing, preserves the intended one-solid expectation, and does not rerun the solver or relax the termination requirement. Pyramid is therefore count/mass/termination-pass; prism remains termination-failed. Raw inputs, stdout, listings, animation/restart files remain unchanged. `probe_native.py` is the original generator/runner and retains that observer bug for provenance; do not use its first-run status alone as the final interpretation.

Official OpenCourant release: latest-20261011, commit cb760c206e346eff12161a2268b134ef9d48a4ef. `official-source/manifest.json` records exact immutable source URLs, Git blob hashes and SHA256. The script's absolute install path is a local evidence detail, not a portable product contract.
