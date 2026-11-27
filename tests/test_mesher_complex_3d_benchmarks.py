"""Independent OCC fixtures for the complex 3-D mesher benchmarks (millimetres)."""

import math

import pytest


def _cut(occ, body, tools):
    solids, _ = occ.cut([(3, body)], [(3, tool) for tool in tools])
    assert len(solids) == 1
    return solids[0][1]


def _fuse(occ, body, addition):
    solids, _ = occ.fuse([(3, body)], [(3, addition)])
    assert len(solids) == 1
    return solids[0][1]


def _filleted_box(gmsh, x, y, z, dx, dy, dz, radius):
    occ = gmsh.model.occ
    box = occ.addBox(x, y, z, dx, dy, dz)
    occ.synchronize()
    edges = [edge for _, edge in gmsh.model.getEntities(1)
             if abs(occ.getMass(1, edge) - dz) < 1e-8
             and gmsh.model.getBoundingBox(1, edge)[5] -
             gmsh.model.getBoundingBox(1, edge)[2] > dz - 1e-6
             and all(lo - 1e-6 <= coord <= hi + 1e-6 for coord, lo, hi in
                     zip(occ.getCenterOfMass(1, edge), (x, y, z), (x+dx, y+dy, z+dz)))]
    return occ.fillet([box], edges, [radius])[0][1]


def _bracket(gmsh):
    occ = gmsh.model.occ
    base = _filleted_box(gmsh, 0, 0, 0, 32, 20, 5, 2)
    body = _fuse(occ, base, occ.addBox(0, 2, 4, 5, 16, 17))
    body = _fuse(occ, body, occ.addCylinder(21, 10, 4, 0, 0, 5, 5))
    cutters = [occ.addCylinder(x, y, -1, 0, 0, 12, radius)
               for x, y, radius in [(21, 10, 2.5), (10, 4, 1.4), (10, 16, 1.4)]]
    cutters.append(occ.addCylinder(-1, 10, 14, 8, 0, 0, 2.2))
    return [_cut(occ, body, cutters)]


def _housing(gmsh):
    occ = gmsh.model.occ
    base = occ.addCylinder(0, 0, 0, 0, 0, 5, 13)
    body = _fuse(occ, base, occ.addCylinder(0, 0, 5, 0, 0, 9, 10))
    body = _fuse(occ, body, occ.addCone(0, 0, 14, 0, 0, 1, 10, 9))
    cavity = occ.addCylinder(0, 0, 7, 0, 0, 10, 7)
    bore = occ.addCylinder(0, 0, -1, 0, 0, 9, 3)
    return [_cut(occ, body, [cavity, bore])]


def _assembly(gmsh):
    occ = gmsh.model.occ

    def plate(z, thickness, rib=False):
        solid = _filleted_box(gmsh, 0, 0, z, 30, 20, thickness, 2)
        holes = [occ.addCylinder(x, y, z-1, 0, 0, thickness+2, 1.6)
                 for x in (4, 26) for y in (4, 16)]
        holes.append(occ.addCylinder(15, 10, z-1, 0, 0, thickness+2, 4))
        solid = _cut(occ, solid, holes)
        if rib:
            solid = _fuse(occ, solid, occ.addBox(8, 2, z+thickness, 14, 2, 6))
        return solid

    members = [plate(0, 5), plate(5, 1), plate(6, 4, rib=True)]
    for x in (4, 26):
        for y in (4, 16):
            # Simplified clamped fastener. Its cylindrical shank clears the
            # bore; head and integral lower collar touch the outer plates.
            shank = occ.addCylinder(x, y, -0.25, 0, 0, 10.5, 1.25)
            head = occ.addCylinder(x, y, 10, 0, 0, 1.8, 2.5)
            collar = occ.addCylinder(x, y, -1.5, 0, 0, 1.5, 2.5)
            members.append(_fuse(occ, _fuse(occ, shank, head), collar))
    return members


def _write_fixture(name, directory):
    gmsh = pytest.importorskip("gmsh")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add(name)
        solids = {"bracket": _bracket, "housing": _housing, "assembly": _assembly}[name](gmsh)
        gmsh.model.occ.synchronize()
        volumes = [gmsh.model.occ.getMass(3, solid) for solid in solids]
        assert min(volumes) > 0
        path = directory / (name + ".step")
        gmsh.write(str(path))
        return path, volumes
    finally:
        gmsh.finalize()


@pytest.mark.parametrize(("name", "parts"), [("bracket", 1), ("housing", 1), ("assembly", 7)])
def test_complex_occ_inputs(name, parts, tmp_path):
    path, volumes = _write_fixture(name, tmp_path)
    assert path.stat().st_size > 0
    assert len(volumes) == parts
    if name == "housing":
        expected = math.pi * (13**2*5 + 10**2*9 + (100+90+81)/3 - 7**2*8 - 3**2*7)
        assert sum(volumes) == pytest.approx(expected)


def _mapped_housing(directory):
    """Exactly partition the same meridional profile into 28 annular sector blocks."""
    gmsh = pytest.importorskip("gmsh")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("mapped_housing")
        occ = gmsh.model.occ
        blocks = []
        bands = [(0, 5, 3, 7, 7), (0, 5, 7, 10, 10), (0, 5, 10, 13, 13),
                 (5, 7, 3, 7, 7), (5, 7, 7, 10, 10), (7, 14, 7, 10, 10),
                 (14, 15, 7, 10, 9)]
        for z0, z1, inner, outer0, outer1 in bands:
            for sector in range(4):
                angle = sector * math.pi/2
                corners = [(inner, z0), (outer0, z0), (outer1, z1), (inner, z1)]
                points = [occ.addPoint(r*math.cos(angle), r*math.sin(angle), z)
                          for r, z in corners]
                edges = [occ.addLine(points[i], points[(i+1) % 4]) for i in range(4)]
                face = occ.addPlaneSurface([occ.addCurveLoop(edges)])
                swept = occ.revolve([(2, face)], 0, 0, 0, 0, 0, 1, math.pi/2)
                blocks.extend(entity for entity in swept if entity[0] == 3)
        occ.removeAllDuplicates()
        occ.synchronize()
        solids = gmsh.model.getEntities(3)
        assert len(solids) == len(blocks) == 28
        volume = sum(occ.getMass(*solid) for solid in solids)
        path = directory / "mapped_housing.brep"
        gmsh.write(str(path))
        return path, volume
    finally:
        gmsh.finalize()


def test_mapped_housing_preserves_cad_volume(tmp_path):
    path, mapped_volume = _mapped_housing(tmp_path)
    _, reference = _write_fixture("housing", tmp_path)
    assert path.is_file()
    assert mapped_volume == pytest.approx(sum(reference), rel=1e-10)


_TET_FACES = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
_HEX_FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
              (2, 3, 7, 6), (3, 0, 4, 7))
_PYR_FACES = ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4))
_FACES = {4: _TET_FACES, 5: _HEX_FACES, 7: _PYR_FACES}


def _worker_arrays(result):
    nodes = result["mesh"]["nodes"]
    xyz = dict(zip(nodes["ids"], nodes["coordinates"], strict=True))
    cells = [(block["entity_uuid"], block["element_type"], conn)
             for block in result["mesh"]["element_blocks"] if block["dimension"] == 3
             for conn in block["connectivity"]]
    return xyz, cells


def _cycle(face):
    return min(face[i:] + face[:i] for i in range(len(face)))


def _audit(xyz, cells, cad_volumes, *, expected_skin=None, reported_minima=None):
    """Integrate the actual element maps and match complete oriented interior faces."""
    from collections import Counter, defaultdict
    from itertools import product
    import numpy as np

    owners = defaultdict(list)
    by_type = Counter()
    volume_by_part = defaultdict(float)
    mins = {}
    hex_sign = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                         [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
    gauss = tuple(product((-1/math.sqrt(3), 1/math.sqrt(3)), repeat=3))
    hex_samples = np.array([*gauss, *hex_sign, (0, 0, 0)])
    terms = 1 + hex_samples[:, None, :] * hex_sign
    hex_grad = np.stack([hex_sign[:, i] * terms[:, :, (i+1)%3] *
                         terms[:, :, (i+2)%3] / 8 for i in range(3)], axis=2)
    for part, kind, conn in cells:
        assert len(set(conn)) == len(conn)
        by_type[kind] += 1
        points = np.array([xyz[n] for n in conn])
        if kind == 4:
            # The affine determinant is constant, but corner edge scales differ.
            jac = np.stack([(points[list(others)] - points[i]).T for i, others in
                            enumerate(((1, 2, 3), (0, 3, 2), (3, 0, 1), (2, 1, 0)))])
            volume = np.linalg.det(jac[0]) / 6
        elif kind == 5:
            jac = np.einsum("ij,sik->sjk", points, hex_grad)
            volume = sum(np.linalg.det(jac[:8]))
        else:
            assert kind == 7
            # Bilinear base evaluated at all corners. Removed the positive
            # (1-t)^2 factor of the collapsed cube-to-pyramid reference map.
            jac = np.stack([np.stack((points[(i+1)%4]-points[i],
                                      points[(i-1)%4]-points[i],
                                      points[4]-points[i]), axis=1) for i in range(4)])
            volume = sum(np.linalg.det((points[[a,b,4]] - points[0]).T)
                         for a,b in [(1,2), (2,3)]) / 6
        determinant = np.linalg.det(jac)
        assert determinant.min() > 0, (part, kind, conn)
        scaled = determinant / np.prod(np.linalg.norm(jac, axis=1), axis=1)
        mins[kind] = min(mins.get(kind, 1), scaled.min())
        volume_by_part[part] += volume
        for local_face in _FACES[kind]:
            face = tuple(conn[i] for i in local_face)
            owners[tuple(sorted(face))].append((kind, _cycle(face)))
    skin = set()
    for key, incident in owners.items():
        assert len(incident) <= 2
        if len(incident) == 1:
            skin.add(key)
            continue
        (ka, a), (kb, b) = incident
        assert a == _cycle(b[::-1])
        if 7 in (ka, kb):
            assert sorted((ka,kb)) == ([5,7] if len(key) == 4 else [4,7])
    if expected_skin is not None:
        assert skin == expected_skin
    assert len(cad_volumes) == len(volume_by_part)
    if isinstance(cad_volumes, dict):
        assert volume_by_part.keys() == cad_volumes.keys()
        relative_errors = [abs(v - cad_volumes[k]) / cad_volumes[k]
                           for k, v in volume_by_part.items()]
    else:
        assert len(cad_volumes) == 1
        relative_errors = [abs(sum(volume_by_part.values()) - cad_volumes[0]) / cad_volumes[0]]
    if reported_minima is not None:
        assert set(mins) == set(reported_minima)
        for kind, expected in reported_minima.items():
            assert mins[kind] == pytest.approx(expected, abs=1e-10)
    # Faceted circular boundaries have O(h^2/r^2) chord error.
    assert max(relative_errors) < 0.025, relative_errors
    print("mesh audit", dict(by_type), "total volume", float(sum(volume_by_part.values())),
          "max CAD relative error", float(max(relative_errors)), "min scaled Jacobian", mins)
    return by_type, skin


def _worker_skin(result):
    from collections import Counter
    adjacent = Counter(face for volume in result["volumes"] for face in volume["surface_uuids"])
    return {tuple(sorted(row)) for block in result["mesh"]["element_blocks"]
            if block["dimension"] == 2 and adjacent[block["entity_uuid"]] == 1
            for row in block["connectivity"]}


@pytest.mark.parametrize("policy", ["conformal", "independent"])
def test_bolted_assembly_interfaces_and_quality(tmp_path, policy):
    from caelab_prep.adapters.gmsh_backend import GmshBackend

    path, volumes = _write_fixture("assembly", tmp_path)
    result = GmshBackend().generate(path, tmp_path/"candidates", 2, dimension=3,
                                    minimum_mesh_size=0.4, curvature_points=20,
                                    interface_policy=policy)
    xyz, cells = _worker_arrays(result)
    cad_by_part = {v["uuid"]: v["volume"] for v in result["volumes"]}
    assert sorted(cad_by_part.values()) == pytest.approx(sorted(volumes))
    by_type, _ = _audit(xyz, cells, cad_by_part, expected_skin=_worker_skin(result))
    assert set(by_type) == {4}
    counts = sorted(i["shared_facets_verified"] for i in result["interface_checks"])
    print("interface triangles", policy, counts)
    if policy == "conformal":
        assert len(counts) == 21
        assert sum(n > 0 for n in counts) == 10
    else:
        assert counts == [0] * 21
        assert all(i["shared_node_count"] == 0 for i in result["interface_checks"])


def test_bolted_assembly_ccx_equilibrium_control(tmp_path):
    import os
    import re
    import shutil
    import subprocess
    from caelab_prep.adapters.gmsh_backend import GmshBackend

    path, volumes = _write_fixture("assembly", tmp_path)
    result = GmshBackend().generate(path, tmp_path/"candidates", 2, dimension=3,
                                    minimum_mesh_size=0.4, curvature_points=20,
                                    interface_policy="conformal")
    xyz, cells = _worker_arrays(result)
    assert len(volumes) == 7
    boundaries = sorted(n for n,p in xyz.items() if abs(p[2]) < 1e-7)
    loaded = sorted(n for n,p in xyz.items() if abs(p[2] - 16) < 1e-7)
    assert len(boundaries) >= 3 and len(loaded) >= 3
    from caelab_prep.application.mesh_candidates import read_mesh_candidate
    from caelab_prep.application.mesher_solver_gate import write_calculix_mesh_include
    candidate = read_mesh_candidate(result)
    sections = write_calculix_mesh_include(candidate, tmp_path/"mesh.inc", version="2.21")
    deck = ["*HEADING", "Bonded bracket-gasket-flange linear equilibrium control, N mm",
            "*INCLUDE,INPUT=mesh.inc"]
    for i,vol in enumerate(result["volumes"]):
        modulus = 2000 if abs(vol["bbox"][2] - 5.0) < 1e-5 else 200000
        deck.extend([f"*MATERIAL,NAME=M{i}", "*ELASTIC", f"{modulus},0.3",
                     f"*SOLID SECTION,ELSET={sections[vol['uuid']]},MATERIAL=M{i}", ""])
    deck.append("*NSET,NSET=SUPPORT")
    deck.extend(",".join(map(str, boundaries[i:i+12])) for i in range(0, len(boundaries), 12))
    deck.extend(["*BOUNDARY", "SUPPORT,1,3", "*STEP", "*STATIC", "*CLOAD"])
    applied_force = -1000.0
    deck.extend(f"{n},3,{applied_force/len(loaded):.15g}" for n in loaded)
    deck.extend(["*NODE PRINT,NSET=SUPPORT,TOTALS=ONLY", "RF", "*END STEP"])
    (tmp_path/"control.inp").write_text("\n".join(deck) + "\n", encoding="ascii")
    if os.name == "nt" and shutil.which("wsl"):
        cwd = subprocess.run(["wsl","-d","Ubuntu","-e","wslpath","-a",tmp_path.as_posix()],
                             capture_output=True, text=True)
        if cwd.returncode:
            pytest.skip("WSL Ubuntu unavailable")
        installed = subprocess.run(["wsl", "-d", "Ubuntu", "-e", "which", "ccx"],
                                   capture_output=True)
        if installed.returncode:
            pytest.skip("CalculiX executable unavailable in WSL Ubuntu")
        run = ["wsl","-d","Ubuntu","--cd",cwd.stdout.strip(),"-e","env","OMP_NUM_THREADS=1",
               "ccx","-i","control"]
    elif shutil.which("ccx"):
        run = ["ccx","-i","control"]
    else:
        pytest.skip("CalculiX executable unavailable")
    solve = subprocess.run(run, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert solve.returncode == 0 and "Job finished" in solve.stdout, solve.stdout+solve.stderr
    data = (tmp_path/"control.dat").read_text()
    match = re.search(r"total force[^\n]*\n\s*([-+\d.E]+)\s+([-+\d.E]+)\s+([-+\d.E]+)",
                      data, flags=re.I)
    assert match, data
    reaction = tuple(map(float, match.groups()))
    print("C3D4 assembly", len(xyz), "nodes", len(cells), "cells",
          len(boundaries), "support nodes", len(loaded), "loaded nodes", "reaction N", reaction)
    assert math.dist(reaction, (0, 0, -applied_force)) < 1e-3


def test_boss_bracket_adaptive_tetrahedra(tmp_path):
    from caelab_prep.adapters.gmsh_backend import GmshBackend

    path, volumes = _write_fixture("bracket", tmp_path)
    result = GmshBackend().generate(path, tmp_path/"candidates", 3, minimum_mesh_size=0.8,
                                    curvature_points=24, size_gradient=0.4,
                                    quality_diagnostics=True)
    xyz, cells = _worker_arrays(result)
    minimum = result["quality"]["by_type"]["tet4"]["min_scaled_jacobian"]
    by_type, _ = _audit(xyz, cells, volumes, expected_skin=_worker_skin(result),
                        reported_minima={4: minimum})
    assert set(by_type) == {4}


@pytest.mark.parametrize("partition", ["prepared", "revolved"])
def test_stepped_chamfered_housing_mapped_hex(tmp_path, partition):
    from caelab_prep.adapters.gmsh_backend import GmshBackend

    if partition == "prepared":
        path, volume = _mapped_housing(tmp_path)
        options = {}
    else:
        path, (volume,) = _write_fixture("housing", tmp_path)
        options = {"block_partition": "revolved"}
    result = GmshBackend().generate(path, tmp_path/"candidates", 2, structured_blocks=True,
                                    quality_diagnostics=True, **options)
    xyz, cells = _worker_arrays(result)
    block_volumes = {v["uuid"]: v["volume"] for v in result["volumes"]}
    assert len(block_volumes) == 28 and sum(block_volumes.values()) == pytest.approx(volume)
    minimum = result["quality"]["by_type"]["hex8"]["min_scaled_jacobian"]
    by_type, _ = _audit(xyz, cells, block_volumes, expected_skin=_worker_skin(result),
                        reported_minima={5: minimum})
    assert set(by_type) == {5}
    assert sum(bool(p["shared_facets_verified"]) for p in result["interface_checks"]) >= 28


def _published_triangles(mesh_path):
    """Reread the published neutral-file skin with an independent SDK session."""
    gmsh = pytest.importorskip("gmsh")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))
        types, ids, connectivity = gmsh.model.mesh.getElements(2)
        assert list(types) == [2]
        triangles = {tuple(sorted(map(int, row))) for row in connectivity[0].reshape(-1, 3)}
        assert len(triangles) == len(ids[0])
        return triangles
    finally:
        gmsh.finalize()


@pytest.mark.parametrize(("name","pitch"), [("bracket", 2.0), ("housing", 1.5)])
def test_complex_single_solid_hybrid(tmp_path, name, pitch):
    from caelab_prep.application.hybrid_hex_core import generate_hybrid_hex_core

    path, volumes = _write_fixture(name, tmp_path)
    hybrid = generate_hybrid_hex_core(path, tmp_path/"candidates", length_unit="mm",
                                      core_size=pitch, boundary_size=1.5)
    native = hybrid.native
    xyz = {n.id: n.xyz for n in native.nodes}
    cells = [(c.part_uuid, c.element_type, c.node_ids) for c in native.elements]
    by_type, skin = _audit(xyz, cells, volumes, expected_skin=_published_triangles(hybrid.mesh_path))
    assert set(by_type) == {4, 5, 7}
    assert all(len(face) == 3 for face in skin)
    from caelab_prep.application.mesher_solver_gate import require_generated_mesh_support
    from caelab_prep.cae_core.errors import PrepError
    with pytest.raises(PrepError) as failure:
        require_generated_mesh_support(native, solver="calculix", version="2.21")
    assert failure.value.code == "solver_element_unsupported"


def test_hybrid_assembly_declines_unmatched_multipart_skin(tmp_path):
    from caelab_prep.application.hybrid_hex_core import generate_hybrid_hex_core
    from caelab_prep.cae_core.errors import PrepError

    path, _ = _write_fixture("assembly", tmp_path)
    with pytest.raises(PrepError, match="one closed OCC solid") as caught:
        generate_hybrid_hex_core(path, tmp_path/"mixed", length_unit="mm",
                                 core_size=2, boundary_size=1.5)
    assert caught.value.code == "hybrid_hex_core"
    assert not list((tmp_path/"mixed").rglob("*.msh"))


def test_bolted_assembly_hybrid_neutral_and_solver_gate(tmp_path):
    from collections import defaultdict
    from caelab_prep.application.hybrid_assembly import generate_hybrid_assembly
    from caelab_prep.cae_core.errors import PrepError

    path, volumes = _write_fixture("assembly", tmp_path)
    candidate = generate_hybrid_assembly(path, tmp_path/"candidate", length_unit="mm",
                                         core_size=2.0, boundary_size=1.5,
                                         allow_tet_fallback=True)
    native = candidate.native
    xyz = {n.id: n.xyz for n in native.nodes}
    cells = [(e.part_uuid, e.element_type, e.node_ids) for e in native.elements]
    part_nodes = defaultdict(set)
    face_owners = defaultdict(list)
    for part, kind, conn in cells:
        part_nodes[part].update(conn)
        for face in _FACES[kind]:
            key = tuple(sorted(conn[j] for j in face))
            face_owners[key].append(part)
    assert len(part_nodes) == 7
    cad_by_part = {}
    labels = {}
    for part, ids in part_nodes.items():
        z = [xyz[n][2] for n in ids]
        if min(z) < -1:
            slot = 3
        elif max(z) > 15:
            slot = 2
        elif min(z) > 4.99:
            slot = 1
        else:
            slot = 0
        labels[part] = ("flange","gasket","bracket","fastener")[slot]
        cad_by_part[part] = volumes[slot]
    assert list(labels.values()).count("fastener") == 4
    families, skin = _audit(xyz, cells, cad_by_part)
    assert set(families) == {4, 5, 7}
    assert all(len(face) == 3 for face in skin)
    pairs = defaultdict(int)
    for face, adjacent in face_owners.items():
        if len(set(adjacent)) == 2:
            assert len(face) == 3
            pairs[tuple(sorted(adjacent))] += 1
    assert len(pairs) == 10
    assert sorted(tuple(sorted((labels[a], labels[b]))) for a, b in pairs) == sorted(
        [("bracket","fastener")] * 4 + [("fastener","flange")] * 4 +
        [("bracket","gasket"), ("flange","gasket")])
    print("hybrid shared triangles", sorted(pairs.values()))
    from caelab_prep.application.mesher_solver_gate import write_calculix_mesh_include
    rejected_path = tmp_path / "unsupported.inc"
    with pytest.raises(PrepError, match="Gmsh 7") as caught:
        write_calculix_mesh_include(candidate, rejected_path, version="2.21")
    assert caught.value.code == "solver_element_unsupported"
    assert not rejected_path.exists()
