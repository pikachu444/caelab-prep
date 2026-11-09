# OpenCourant native hybrid reader review

Read-only source review, 2026-11-02. This is not a solver execution result or N26 completion result.

## Fixed source provenance

Official repository `https://github.com/OpenCourant/OpenCourant`, tag `latest-20261011`, resolves to commit `cb760c206e346eff12161a2268b134ef9d48a4ef` using the GitHub tag-ref API. Exact downloaded source text is under `official-source/`; its `manifest.json` records immutable source URLs, byte counts, Git blob IDs, and SHA256. The downloaded Fortran files' recomputed Git blob IDs match the official tree entries. No installed HyperMesh CFG was copied.

## Reader and orientation facts

- `reader/source/solver_interface/source/elements/cpp_brick_read.cpp:41,73–74`: selects `/BRICK` and copies all eight node-ID slots, including repeated IDs, into IXS. There is no unique-node reduction here.
- `starter/source/elements/reader/hm_read_solid.F:144–164`: four trailing zero IDs choose the special tetra branch. `165–190`: two trailing zero IDs choose the special six-node branch. Neither applies to a fully populated repeated-ID connectivity.
- `hm_read_solid.F:191–215`: a fully populated pyramid/prism degenerate connectivity therefore takes the ordinary eight-slot branch, sets `ISOLNOD=8`, and calls `CHECKVOLUME_8N`. A negative sign swaps the first and second four-node faces. This is an orientation correction, not proof that an arbitrary malformed connectivity is valid.
- `starter/source/elements/solid/solide/checksvolume.F:62–118`: shows the eight-slot coordinates and signed determinant expression used by that check.
- `engine/source/elements/solid/solide/degenes8.F:62–74`: explicitly detects repeated node IDs and counts degeneracy. This confirms intentional repeated-node support downstream, but does not create an independent pyramid element family.

## Official documented encoding

The official Radioss 2024 `/BRICK` manual, comment 6, expressly permits repeated node numbers to make degenerate 3D solids. The parent reviewer downloaded and visually checked its Figure 3 SVGs: `BRICK_4.svg` uses prism `[1,2,3,1,5,6,7,5]`; `BRICK_7.svg` uses pyramid `[1,2,3,4,5,5,5,5]`. Accordingly the proposed mapping is:

| Original ordered vertices | Eight `/BRICK` slots |
| --- | --- |
| Gmsh Prism6 `(a,b,c,d,e,f)` | `(a,b,c,a,d,e,f,d)` |
| Gmsh Pyramid5 `(a,b,c,d,e)` | `(a,b,c,d,e,e,e,e)` |

The official `/PENTA6` description restricts that keyword to thick shell Isolid15 with PROP20; it explicitly directs non-thick-shell pentahedra to degenerate `/BRICK`.

Sources:

- https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/brick_starter_r.htm
- https://2024.help.altair.com/2024/hwsolvers/rad/images/solvers/BRICK_4.svg
- https://2024.help.altair.com/2024/hwsolvers/rad/images/solvers/BRICK_7.svg
- https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/penta6_starter_r.htm

## Formulation-dependent volume risk

Official PROP14 describes Isolid1 as one integration point, Isolid17 as fixed 2x2x2 full integration, and Icpre3 as no reduced pressure integration for compressible material. See https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/prop_type14_solid_starter_r.htm (definitions 215–226, 260–270).

The pinned ordinary initialization code contains this distinction: `sinit3.F:299–304` uses `SDERI3B` for NPT=8; `319–327` otherwise uses ordinary `SDERI3` except the specialized JHBE24 branch. `sderi3.F:148–151` uses the central determinant as volume, while `sderi3b.F:149–150,264–265,348–349` sums eight integration-point contributions. `sdlen3.F:93–95` subsequently derives characteristic length from volume and does not correct that volume. However, follow-up source tracing corrected the original implied association of Isolid17 with that `SDERI3B` path: Isolid17 dispatches through `S8ZINIT3`, as detailed below.

Independent evaluation of the exact central-determinant formula for a unit-square-base, height-1 pyramid with apex `(0.5,0.5,1)` and the official repeated-apex connectivity gives `0.25`; its geometric volume is `1/3`. This is an analytical source-level prediction, not an observed Starter result. It means Isolid1 cannot be assumed lossless for this mapping. A documented fully integrated profile such as Isolid17/Ismstr4/Icpre3/Iframe1 should be checked by the actual fixed-coordinate, fixed-density fixture. The parent owns those solver runs, including preservation of any failed first profile.

## Limits

This review establishes official encoding, exact reader path, and formulation sensitivity. It does not prove arbitrary pyramid/prism quality, mixed-face conformity, dynamic accuracy, solver success, or N26 F2 readiness. Actual Starter family/count/mass and Engine termination remain separate evidence.

## Follow-up: exact Isolid17 mass distribution path

After the parent observed correct total mass but shifted centers of mass, a narrow read-only trace found:

- `starter/source/elements/initia/initia.F:1232,1250`: JHBE 14, 222, or 17 dispatches to `S8ZINIT3`.
- `starter/source/elements/solid/solide8z/s8zinit3.F:257–258`: JHBE17 selects integration code222. Lines440–446 call `S8ZDERIC3` for the central reference volume. Lines496–518 loop over 2x2x2 Gauss points and call `S8EDERI3`; `s8zderi3.F:2420–2424` computes each weighted point volume. Lines571–574 of `s8zinit3.F` accumulate the point material quantities through `SVALUE0`; `scinit3.F:507–515` weights density by point-volume/reference-volume. Thus the mass later passed to `SMASS3` is the eight-point integrated mass even though the reference `VOLU` itself remains central. Lines589–595 call `SMASS3` with that accumulated density and reference volume.
- `starter/source/elements/solid/solide/smass3.F:89`: `MASS=FILL*RHO*VOLU/8`; lines99–106 assign this same quantity to all eight connectivity slots. Lines109–118 accumulate part mass and first coordinate moments using those eight slots; the following lines compute inertia from the same slot weights.

Consequently, repeated slots at one physical vertex accumulate multiple equal mass contributions. For the official pyramid mapping, the apex occupies four slots and receives half the element mass. For the official prism mapping, a and d occupy two slots each. This supports the parent's observed center-of-mass bias even while total integrated mass is correct. It is a property of this documented degenerate encoding plus the selected solver formulation/lumping path, not evidence that the importer changed coordinates.

The evidence distinguishes two computations: total mass follows the eight Gauss-point volumes and density accumulation; its distribution is then equal across eight connectivity slots. It would be inaccurate to describe the central `VOLU` variable as directly replaced by the exact integrated volume.

For contrast only, the separate `SMASS3B` path uses integrated nodal weights (`smass3b.F:81–88,105–112`, supplied by `sderi3b.F:290–297`). It is not the Isolid17 path identified above. No extra native execution was performed for this follow-up.
