# Complex CAD meshing debate and benchmark evidence

## Round 1 – construction review

**Critic verdict: CRITIQUE → APPROVED before production coding.** Clearance to trimmed CAD and to the faceted boundary, an axial pyramid height bound, explicit quality floors and solver-specific rejection resolved the construction objections below.

The critic challenged a centre/vertex-only selector with a thin wall enclosing a bore, and arbitrary pyramid apices with a reentrant voxel valley. The corrected H0 design requires a classified interior cell centre and clearance to **all trimmed CAD faces** exceeding the voxel circumsphere radius plus margin. At height ≤s/4 a face-centred axial apex stays inside that ball. Competing perpendicular pyramids in an empty neighbour require mutually incompatible interior inequalities. The audit also identified an independent failure mode: the faceted CAD skin can cut into material even if the exact CAD surface clears the core. The revised design requires clearance and containment against the actual triangulated shells, or a conservative approximation bound. Fixed-facet recovery and opposite orientation of every interior interface are necessary after cavity filling.

Positive signed volume can coexist with a sliver. The design now distinguishes per-family shape floors and Jacobian checks. Curved/thin solids can exhaust available clearance. A zero-core candidate requires an explicit diagnostic or declared fallback. The critic accepted this **restricted** design after the changes appeared in [the architecture](mesher-architecture-v2.md). Compatibility assertions are specific to the executable: CalculiX 2.21 rejected C3D5, and the tested OpenRadioss Starter rejected /PYRA5. A complete mixed structural deck requires native admissibility for every family.

## Round 2 – complex CAD inputs and measured outcomes

**Critic verdict: CRITIQUE → APPROVED for the observed backend cases.** CAD skin orientation, fixed-node renumbering, coarse fastener tessellation, nested core boundaries and the CalculiX coordinate field width each required a correction and a rerun. The requested native Pyramid5 structural patches remain blocked by the measured parser rejections.

The [benchmark suite](../tests/test_mesher_complex_3d_benchmarks.py) builds genuine OCC B-reps in millimetres, exports STEP or BREP, and calls the public meshing entry points. The tests independently integrate the ordered cells and join opposite cyclic face loops. B1 and B2 match every exterior face against the published or prescribed surface mesh. Assembly interface checks compare actual node IDs and adjacent cell-face cycles. Volume deviations below are absolute differences divided by the corresponding OCC part volume. The 2.5% per-part limit allows for curved-skin chord error.

| Case | Nodes | Physical cells | Minimum scaled Jacobian, by family | Maximum CAD volume error |
|---|---:|---|---|---|
| B1 M1 adaptive bracket | 3,578 | 13,607 Tet4 | Tet 0.106501 | 0.06965% |
| B1 M4 hybrid bracket | 6,210 | 18,787 Tet4, 124 Hex8, 350 Pyramid5 | Tet 0.03097, hex 1.0, pyramid 0.33333 | 0.00957% |
| B2 M2 prepared housing | 2,112 | 1,408 Hex8 over 28 blocks | Hex 0.705305 | 0.33952% |
| B2 M2 original single-solid STEP | 2,112 | 1,408 Hex8 over 28 automatically derived blocks | Hex 0.705305 | 0.33952% |
| B2 M4 hybrid housing | 3,287 | 10,900 Tet4, 371 Hex8, 668 Pyramid5 | Tet 0.047441, hex 1.0, pyramid 0.33333 | 0.11141% |
| B3 conformal assembly | 13,146 | 57,185 Tet4 | Tet 0.091228 | 1.252% |
| B3 independent assembly | 15,743 | 59,569 Tet4 | Tet 0.029831 | 1.252% |
| B3 conformal hybrid assembly | 20,223 | 87,979 Tet4, 46 Hex8, 156 Pyramid5 | Tet 0.04490, hex 1.0, pyramid 0.33333 | 0.84755% |

The tet metric uses the affine determinant scaled by the three edge lengths at each of four corners. Hexes use eight-point volume integration and Jacobian checks at those points, corners and centre. The pyramid checks use four base-corner determinants after removing the collapsed-coordinate factor. Finite samples on hexes do not prove positivity everywhere. For the B1 adaptive tet mesh, the independent all-corner minimum 0.106501 agreed with the corrected product metric. The SDK minSJ was 1.0 and minSICN was 0.29182.

### B1 and B2 – brackets, bores and shell orientation

B1 joins a filleted 32 × 20 × 5 base, an upright and a cylindrical boss. It has three vertical bores and a transverse through-bore. M1 used max size 3 mm, minimum target 0.8 mm, 24 samples per circle and 0.4 target gradient. Integrated volume was 4,465.783 mm³. M4 used 2 mm core pitch and 1.5 mm skin size. Its 1,400 pyramid side triangles paired with tets; total mesh volume was 4,462.248 mm³.

B2 is a stepped cylindrical housing with an axial bore, recessed cavity and conical rim chamfer. Revolving seven exact meridional regions through four quarter-sectors produced the prepared 28-block BREP. Its total OCC volume agreed with the single boolean solid within 1e−10 relative. M2 used a 2 mm edge target. The independent original-STEP run with automatic revolved block partition reproduced the same cell count, all-corner quality and volume agreement. The critic reopened the original STEP in a separate Gmsh session and compared all nine face areas against their 56 unique mapped exterior child faces. Maximum relative face-area error was 5.66e−16. M4 used the original unpartitioned solid with 1.5 mm core pitch and skin size, yielding 4,331.614 mm³.

The first hybrid runs rejected both surfaces as inconsistently oriented. After the owner corrected CAD triangle orientation and preserved prescribed node IDs during cavity filling, the critic reran both original STEP files. Their public hybrid candidates passed the independent topology, Jacobian, volume and published-skin comparisons.

The original core trimming could discard voxels that were still admissible after eliminating a pinch. The final B2 construction restored 16 of 26 pinch-trimmed cells. The critic reconstructed the grid from the published Hex8 coordinates and enumerated every face neighbour, independently measuring distance to trimmed OCC faces and actual boundary triangles. In the final B2 result two of 529 neighbouring cells passed the clearance tests; adding either would violate the connected closed two-manifold boundary requirement. In B1 none of 322 neighbours met clearance. This establishes saturation under individual face-adjacent additions for these cases. It does not establish a globally maximum-volume core. B2 preserved 3,552 CAD skin facets and paired 668 hex/pyramid and 2,672 pyramid/tet interfaces.

A separate enclosed-void regression exercised a 10 × 8 × 8 block with a 1³ internal cutout, supplied as BREP in declared cm. At 0.8 cm pitch and 0.9 cm skin size, the revised algorithm removed two core cells in a single face-connected channel, then repeated the manifold and clearance checks. Public generation produced 675 Hex8, 540 Pyramid5 and 6,424 Tet4. Independent reread found 1,588 prescribed triangles, 540 hex/pyramid contacts and 2,160 pyramid/tet contacts. Integrated volume was 639.000000000027 cm³ against 639 cm³ CAD. Minimum tet/hex/pyramid scaled Jacobians were 0.099868, 1.0 and 0.33333.

### B3 – seven-solid CAD with fasteners and gasket

The identical STEP in each B3 run contains a filleted base flange, a 1 mm gasket, a ribbed upper bracket and four headed fasteners with integral lower collars. The shanks have 0.35 mm radial clearance. There are ten touching face pairs. The bonded control models neither thread geometry nor bolt preload or frictional separation.

An initial uniform 2 mm tetrahedral mesh missed 12.4–13.1% of fastener volume. Curvature sizing at 20 points per circle with a 0.4 mm minimum target brought both interface policies within the per-part limit. The conformal assembly shared 1,522 triangles on each gasket interface and 80 triangles on each fastener/plate interface. The independent assembly shared no node IDs across any of the 21 possible part pairs.

The conformal hybrid used a 2 mm core pitch, a 1.5 mm skin target and explicit per-part tet fallback. The base took 20,492 Tet4 plus every hex and pyramid. No connected core survived the clearance criterion on the gasket (8,222 Tet4), upper bracket (23,559 Tet4) or four fasteners (8,925 / 8,933 / 8,879 / 8,969 Tet4). The mesh retained two interfaces of 2,094 shared triangles each and eight of 96 each.

### B3 – native writer and equilibrium

The neutral mixed assembly reached the production CalculiX include writer. The writer refused Pyramid5 before creating the destination. The installed CCX 2.21 has no native C3D5 response for the full mixed case.

For a supported control, the default candidate reader admitted the conformal 13,146-node Tet4 mesh. The production writer initially emitted an exponent-form node coordinate wider than 20 characters. The actual CCX reader rejected the first node. The corrected writer fits each coordinate within the supported field and checks whether distinct positions collapse during formatting. The critic reran the original STEP through the reader, writer and WSL Ubuntu CCX 2.21.

The linear-static deck fixed all translations on 833 base-plane nodes and distributed −1000 N vertically across 23 rib-top nodes. The flange, bracket and fasteners used E = 200,000 MPa, the gasket E = 2,000 MPa; all Poisson ratios were 0.3. The resulting total support reaction was (4.91e−12, 1.53e−12, 1000.0) N.

### Reproduction

Install the CAD and dev extras and run `python -B -m pytest -q -s tests/test_mesher_complex_3d_benchmarks.py`. The native control detects CCX on PATH or in WSL Ubuntu and leaves the generated mesh include, INP and DAT in the pytest case directory. The reported CAD and mesh runs used Windows Gmsh SDK 4.15.2.

**Verification verdict.** Fourteen complex-benchmark cases passed in one Windows run (81.39 s), including automatic source STEP partition, reopened neutral files, actual rejected hybrid export and the supported WSL CCX solve. The independent rerun of `python -B -m pytest -q tests/test_hybrid_hex_core.py` passed all five cases (4.07 s). After introducing deterministic core add-back and the common quality implementation, the three affected B1/B2/B3 hybrid end-to-end tests passed together in 32.96 s; the B2 table reports this final run. These results admit the observed backend cases. No native mixed Pyramid5 structural response was obtained. The review ran on the feature worktree based on `a4f0c3216f9fcae88dd8283b0f1db6b1b5cd6cd2` with the mesher changes present.
