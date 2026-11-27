"""Real OCC and SDK round-trip controls for the bounded hybrid backend."""

from itertools import product
import json
from pathlib import Path

import pytest

from caelab_prep.adapters.hybrid_hex_core_geometry import _add_back_core_cells
from caelab_prep.adapters.msh_worker import read_msh
from caelab_prep.application.hybrid_hex_core import generate_hybrid_hex_core
from caelab_prep.cae_core.errors import PrepError


def _write_brep(path, geometry):
    gmsh = pytest.importorskip("gmsh")
    gmsh.initialize(readConfigFiles=False, interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add(path.stem)
        occ = gmsh.model.occ
        if geometry == "shell":
            occ.addRectangle(0, 0, 0, 4, 4)
        elif geometry == "thin":
            occ.addBox(0, 0, 0, 10, 6, .6)
        else:
            body = occ.addBox(0, 0, 0, 10, 8, 8)
            if geometry == "void":
                cavity = occ.addBox(4, 3, 3, 1, 1, 1)
                occ.cut([(3, body)], [(3, cavity)])
            elif geometry == "free-curve":
                a = occ.addPoint(40, 0, 0)
                b = occ.addPoint(41, 0, 0)
                occ.addLine(a, b)
            elif geometry == "free-point":
                occ.addPoint(40, 0, 0)
        occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()
    return path


def test_enclosed_void_opens_one_core_channel_and_preserves_msh(tmp_path):
    source = _write_brep(tmp_path / "void.brep", "void")
    candidate = generate_hybrid_hex_core(source, tmp_path / "assets", length_unit="cm",
                                         core_size=.8, boundary_size=.9)
    assert candidate.fallback_reason is None
    assert candidate.core_audit["channels"] == 1
    assert candidate.core_audit["channel_trimmed"] > 0
    assert candidate.cad_volume == pytest.approx(639)
    assert candidate.mesh_volume == pytest.approx(639)
    assert set(candidate.quality) == {"tet4", "hex8", "pyramid5"}
    pyramid_count = candidate.quality["pyramid5"]["count"]
    assert candidate.face_audit["hex_pyramid_faces"] == pyramid_count
    assert candidate.face_audit["pyramid_tet_faces"] == 4 * pyramid_count
    assert candidate.quality["pyramid5"]["minimum_scaled_jacobian"] == pytest.approx(1/3)
    for metrics in candidate.quality.values():
        assert metrics["max_edge_aspect_ratio"] >= 1
        assert 0 <= metrics["max_face_skewness"] < 1
        assert 0 < metrics["min_dihedral_degrees"] < 180
    assert candidate.quality["hex8"]["min_dihedral_degrees"] == pytest.approx(90)

    raw = read_msh(candidate.mesh_path)
    actual = {tag: tuple(nodes) for block in raw["blocks"] if block["dimension"] == 3
              for tag, nodes in zip(block["ids"], block["connectivity"])}
    assert actual == {cell.id: cell.node_ids for cell in candidate.to_native_mesh().elements}
    boundary = [nodes for block in raw["blocks"] if block["dimension"] == 2 for nodes in block["connectivity"]]
    xyz = dict(zip(raw["nodes"]["ids"], raw["nodes"]["coordinates"]))
    assert len(boundary) == candidate.face_audit["external_triangle_faces"]
    assert any(all(all(lo <= value <= hi for lo, value, hi in zip((4, 3, 3), xyz[tag], (5, 4, 4)))
                   for tag in face) for face in boundary)
    report = json.loads(candidate.report_path.read_text(encoding="utf-8"))
    assert report["sdk_reopen_verified"]
    assert report["assets"] == {asset.kind: {"name": Path(asset.path).name, "sha256": asset.sha256}
                                for asset in candidate.native.assets if asset.kind != "report"}


def test_thin_cad_reports_no_core_and_requires_explicit_tet_fallback(tmp_path):
    source = _write_brep(tmp_path / "thin.brep", "thin")
    output = tmp_path / "assets"
    options = dict(length_unit="mm", core_size=2., boundary_size=.8)
    with pytest.raises(PrepError, match="exceeds at least one CAD extent"):
        generate_hybrid_hex_core(source, output, **options)
    assert list(output.iterdir()) == []
    candidate = generate_hybrid_hex_core(source, output, **options, allow_tet_fallback=True)
    assert "exceeds at least one CAD extent" in candidate.fallback_reason
    assert set(candidate.quality) == {"tet4"}
    assert candidate.face_audit["hex_pyramid_faces"] == 0
    assert candidate.mesh_volume == pytest.approx(36)
    candidate.mesh_path.write_text("damaged after review", encoding="utf-8")
    with pytest.raises(PrepError, match="reviewed hybrid mesh asset changed"):
        candidate.to_native_mesh()


@pytest.mark.parametrize(("geometry", "reason"), [
    ("shell", "requires one closed OCC solid"),
    ("free-curve", "unowned faces, curves or points"),
    ("free-point", "unowned faces, curves or points"),
])
def test_refuses_open_or_mixed_dimension_cad_even_with_fallback(tmp_path, geometry, reason):
    source = _write_brep(tmp_path / f"{geometry}.brep", geometry)
    output = tmp_path / "assets"
    with pytest.raises(PrepError, match=reason):
        generate_hybrid_hex_core(source, output, length_unit="mm", core_size=.8, allow_tet_fallback=True)
    assert list(output.iterdir()) == []


def test_core_add_back_retries_rejected_neighbors_without_closing_a_void():
    full = set(product(range(3), repeat=3))
    mouth, interior = (1, 1, 0), (1, 1, 1)
    opened = full - {mouth, interior}

    # Restoring the first (lexicographic) candidate alone would seal an empty
    # chamber. Filling the interior first makes a later retry of the mouth valid.
    assert _add_back_core_cells(opened, full - {interior}) == 0
    assert mouth not in opened
    assert _add_back_core_cells(opened, full) == 2
    assert opened == full
