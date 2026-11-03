"""Saved control drafts exercise real JSON/evidence reads, never a mesher."""
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from caelab_prep.application.meshing_criteria import MeshingCriteria
from caelab_prep.application.washer_controls import (create_washer_control_draft,
    read_washer_control_draft, save_washer_control_draft)
from caelab_prep.cae_core.errors import PrepError
from geometry_evidence_fixtures import write_hole_inspection
from test_geometry_features import hole, close_cap


@pytest.fixture
def inspection(hole, tmp_path):
    return write_hole_inspection(hole, tmp_path)


def controls(**changes):
    return replace(MeshingCriteria("mm", 1.5, .25, washer_rim_divisions=16,
        washer_width=.5, washer_layers=2, washer_element_family="quad"), **changes)


def target(inspection):
    data = inspection.to_dict()
    return {"hole_surface_uuid": data["surfaces"][0]["uuid"],
            "opening_surface_uuid": data["surfaces"][1]["uuid"], "length_tolerance": 1e-6}


@pytest.mark.parametrize("family", ["quad", "tria"])
@pytest.mark.parametrize("layers", [1, 2])
def test_explicit_family_v2_and_geometry_bound_snapshot_reopen(inspection, tmp_path, family, layers):
    profile = controls(washer_element_family=family, washer_layers=layers)
    before = {asset.path: Path(asset.path).read_bytes() for asset in inspection.assets}
    profile.save(tmp_path/"profile.json")
    assert MeshingCriteria.load(tmp_path/"profile.json") == profile
    assert profile.to_dict()["version"] == 2
    path = tmp_path/"opening.washer.json"
    draft = save_washer_control_draft(path, inspection, profile, **target(inspection))
    assert read_washer_control_draft(path) == draft
    assert draft["radial_layer_radii"] == ([1., 1.5] if layers == 1 else [1., 1.25, 1.5])
    assert draft["width_policy"] == "total_radial_width" and draft["layer_spacing"] == "equal_radial_spacing"
    assert draft["criteria"]["washer_element_family"] == family
    assert draft["mesh_generation_supported"] is False and draft["modifications"] == 0
    assert {asset.path: Path(asset.path).read_bytes() for asset in inspection.assets} == before
    with pytest.raises(PrepError, match="not implemented"):
        profile.gmsh_kwargs(source_path="source.step")


def test_v1_partial_controls_keep_the_original_shape_and_do_not_infer_a_family():
    profile = MeshingCriteria("mm", 1.5, .25, washer_width=.5, washer_layers=2)
    value = profile.to_dict()
    assert value["version"] == 1 and "washer_element_family" not in value
    assert MeshingCriteria.from_dict(value) == profile
    with pytest.raises(PrepError):
        MeshingCriteria.from_dict({**value, "washer_element_family": "quad"})


@pytest.mark.parametrize("change", [{"washer_element_family": None}, {"washer_width": None},
    {"washer_rim_divisions": None}, {"washer_layers": 3}, {"length_unit": "cm"},
    {"washer_width": 3.}, {"washer_width": 1e-8}])
def test_incomplete_units_unsupported_layers_and_unresolved_extents_reject(inspection, change):
    with pytest.raises(PrepError):
        create_washer_control_draft(inspection, controls(**change), **target(inspection))


def test_blind_disk_and_foreign_opening_are_not_washer_targets(hole, tmp_path):
    close_cap(hole["surfaces"][1])
    inspection = write_hole_inspection(hole, tmp_path)
    with pytest.raises(PrepError, match="closed disks"):
        create_washer_control_draft(inspection, controls(), **target(inspection))
    good = {**target(inspection), "opening_surface_uuid": inspection.to_dict()["surfaces"][2]["uuid"]}
    assert create_washer_control_draft(inspection, controls(), **good)["opening_surface_uuid"] == good["opening_surface_uuid"]
    with pytest.raises(PrepError):
        create_washer_control_draft(inspection, controls(), **{**good, "opening_surface_uuid": "foreign"})


@pytest.mark.parametrize("asset", ["source", "xao", "metadata", "hardlink"])
def test_saving_cannot_overwrite_inspected_assets_or_hardlink_alias(inspection, tmp_path, asset):
    path = Path(next(row.path for row in inspection.assets if row.kind == (asset if asset != "hardlink" else "xao")))
    original = path.read_bytes()
    if asset == "hardlink":
        alias = tmp_path/"alias.json"; os.link(path, alias); path = alias
    with pytest.raises(PrepError) as exc:
        save_washer_control_draft(path, inspection, controls(), **target(inspection))
    assert exc.value.code == "washer_control_overwrite" and path.read_bytes() == original


@pytest.mark.parametrize("change", ["target", "radius", "policy", "generation", "extra", "criteria", "stale",
    "bool_revision", "bool_circle", "bool_radius", "bool_generation", "bool_modifications"])
def test_reopen_recomputes_target_controls_and_evidence(inspection, tmp_path, change):
    path = tmp_path/"draft.json"
    draft = save_washer_control_draft(path, inspection, controls(), **target(inspection))
    if change == "target": draft["opening_surface_uuid"] = "foreign"
    if change == "radius": draft["radial_layer_radii"][1] = 999
    if change == "policy": draft["width_policy"] = "per_layer_width"
    if change == "generation": draft["mesh_generation_supported"] = True
    if change == "extra": draft["mesh_uuid"] = "fabricated"
    if change == "criteria": draft["criteria"]["washer_width"] = .75
    if change == "stale": Path(inspection.assets[0].path).write_bytes(b"changed")
    if change == "bool_revision": draft["geometry_revision"] = True
    if change == "bool_circle": draft["opening_circle_tag"] = True
    if change == "bool_radius": draft["radial_layer_radii"][0] = True
    if change == "bool_generation": draft["mesh_generation_supported"] = 0
    if change == "bool_modifications": draft["modifications"] = False
    path.write_text(json.dumps(draft), encoding="utf-8")
    with pytest.raises(PrepError):
        read_washer_control_draft(path)


def test_failed_stale_save_keeps_the_previous_draft(inspection, tmp_path):
    path = tmp_path/"draft.json"
    save_washer_control_draft(path, inspection, controls(), **target(inspection))
    original = path.read_bytes()
    Path(inspection.assets[0].path).write_bytes(b"changed")
    with pytest.raises(PrepError):
        save_washer_control_draft(path, inspection, controls(), **target(inspection))
    assert path.read_bytes() == original


def test_asset_change_during_serialization_keeps_previous_draft_and_removes_temporary(inspection, tmp_path, monkeypatch):
    from caelab_prep.application import storage
    path = tmp_path/"draft.json"
    save_washer_control_draft(path, inspection, controls(), **target(inspection))
    original = path.read_bytes()
    original_dump = storage.json.dump
    def changing_dump(*args, **kwargs):
        original_dump(*args, **kwargs)
        Path(inspection.assets[0].path).write_bytes(b"changed during serialization")
    monkeypatch.setattr(storage.json, "dump", changing_dump)
    with pytest.raises(PrepError):
        save_washer_control_draft(path, inspection, controls(), **target(inspection))
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".caelab-json-*"))


@pytest.mark.parametrize("alias_kind", ["hardlink", "symlink"])
def test_late_destination_alias_does_not_overwrite_original_input(inspection, tmp_path, monkeypatch, alias_kind):
    from caelab_prep.application import washer_controls
    original = Path(inspection.to_dict()["source"]["path"])
    before = original.read_bytes()
    destination = tmp_path/"late-link.json"
    writer = washer_controls.write_json
    def alias_before_write(path, value, **kwargs):
        try:
            (os.link if alias_kind == "hardlink" else os.symlink)(original, path)
        except OSError as exc:
            pytest.skip(f"Symbolic links unavailable: {exc}")
        return writer(path, value, **kwargs)
    monkeypatch.setattr(washer_controls, "write_json", alias_before_write)
    with pytest.raises(PrepError) as exc:
        save_washer_control_draft(destination, inspection, controls(), **target(inspection))
    assert exc.value.code == "washer_control_overwrite"
    assert original.read_bytes() == before and destination.exists()
    assert not list(tmp_path.glob(".caelab-json-*"))
