"""Bounded OCCT experiment, not a Prep feature or automatic midsurface kernel.

Caller selects source face pairs and units. Supports one planar wall, or two
planar walls joined by one explicitly paired coaxial cylindrical bend. Inputs
are copied before offset/boolean/sewing. No source topology is edited.
"""
from dataclasses import dataclass
import hashlib
import io
import math
import os
from pathlib import Path
import tempfile

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_Sewing
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
from OCP.BRepOffset import BRepOffset_Skin
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Intersection

TOL = 1e-6  # millimetres, fixed for these fixtures
ANG = 1e-8

class Rejected(ValueError):
    pass

@dataclass(frozen=True)
class Pair:
    outer: int
    inner: int


def brep_bytes(shape):
    stream = io.BytesIO()
    BRepTools.Write_s(shape.wrapped, stream)
    return stream.getvalue()


def digest(shape):
    return hashlib.sha256(brep_bytes(shape)).hexdigest()


def topology(shape):
    faces = shape.Faces()
    edges = []
    for i, face in enumerate(faces):
        for edge in face.Edges():
            old = next((entry for entry in edges if edge.wrapped.IsSame(entry[0].wrapped)), None)
            if old is None:
                edges.append((edge, {i}))
            else:
                old[1].add(i)
    adjacent = [set() for _ in faces]
    for edge, owners in edges:
        for owner in owners:
            adjacent[owner].update(owners - {owner})
    remaining = set(range(len(faces)))
    components = 0
    while remaining:
        components += 1
        pending = [remaining.pop()]
        while pending:
            found = adjacent[pending.pop()] & remaining
            remaining -= found
            pending.extend(found)
    return {"faces": len(faces), "components": components,
            "free_edges": sum(len(owners) == 1 for _, owners in edges),
            "shared_edges": sum(len(owners) == 2 for _, owners in edges),
            "nonmanifold_edges": sum(len(owners) > 2 for _, owners in edges),
            "seam_lengths_mm": [edge.Length() for edge, owners in edges if len(owners) == 2]}, edges


def sew(faces):
    operation = BRepBuilderAPI_Sewing(TOL)
    for face in faces:
        operation.Add(face.wrapped)
    operation.Perform()
    result = cq.Shape.cast(operation.SewedShape())
    if not result.isValid():
        raise Rejected("Sewing did not produce valid topology")
    return result


def _pair_measure(a, b, thickness):
    kind = a.geomType()
    if kind != b.geomType() or kind not in ("PLANE", "CYLINDER"):
        raise Rejected("Only explicit planar or coaxial cylindrical pairs are supported")
    if a.normalAt().dot(b.normalAt()) > -1 + ANG:
        raise Rejected("Selected face normals are not opposed")
    if kind == "PLANE":
        measured = -(b.Center() - a.Center()).dot(a.normalAt())
        if measured <= 0:
            raise Rejected("The selected outer normal does not point away from the opposing face")
    else:
        ca, cb = BRepAdaptor_Surface(a.wrapped).Cylinder(), BRepAdaptor_Surface(b.wrapped).Cylinder()
        axis_a, axis_b = cq.Vector(ca.Axis().Direction()), cq.Vector(cb.Axis().Direction())
        axis_delta = cq.Vector(cb.Location()) - cq.Vector(ca.Location())
        if abs(abs(axis_a.dot(axis_b)) - 1) > ANG or axis_delta.cross(axis_a).Length > TOL:
            raise Rejected("Cylindrical pair must be coaxial")
        measured = ca.Radius() - cb.Radius()
        if cb.Radius() <= thickness:
            raise Rejected("This experiment excludes bends whose inner radius is no larger than thickness")
    if abs(measured - thickness) > TOL:
        raise Rejected("Pair thickness differs from the declared uniform thickness")
    return {"kind": kind, "measured_thickness_mm": measured, "thickness_error_mm": abs(measured - thickness),
            "outer_area_mm2": a.Area(), "inner_area_mm2": b.Area()}


def _offset(shell, distance):
    operation = BRepOffsetAPI_MakeOffsetShape()
    operation.PerformByJoin(shell.wrapped, distance, TOL, BRepOffset_Skin,
                            False, False, GeomAbs_Intersection, False)
    if not operation.IsDone():
        raise Rejected("OCCT offset failed; original shape and destination are unchanged")
    result = cq.Shape.cast(operation.Shape())
    if not result.isValid():
        raise Rejected("OCCT offset returned invalid topology")
    return result


def extract(shape, pairs, *, thickness_mm, fraction=0.5, units="mm"):
    """Return a candidate and measurements; no writes or implicit face pairing.

    fraction is measured from each outer face toward its paired inner face.
    0.5 is the midsurface. Other fractions describe a reference surface only.
    Native shell offsets are deliberately not inferred or exported here.
    """
    if units != "mm" or not math.isfinite(thickness_mm) or thickness_mm <= 10 * TOL:
        raise Rejected("Declare positive millimetre thickness; automatic unit conversion is not supported")
    if not math.isfinite(fraction) or not 0 < fraction < 1:
        raise Rejected("Offset fraction must be strictly between the paired faces")
    if not shape.isValid() or len(shape.Solids()) != 1:
        raise Rejected("One valid source solid is required")
    source_before = digest(shape)
    faces = shape.Faces()
    chosen = [index for pair in pairs for index in (pair.outer, pair.inner)]
    if len(set(chosen)) != len(chosen) or any(type(index) is not int or index < 0 or index >= len(faces) for index in chosen):
        raise Rejected("Each explicitly selected source face must be distinct and present")
    measurements = [_pair_measure(faces[p.outer], faces[p.inner], thickness_mm) for p in pairs]
    kinds = sorted(item["kind"] for item in measurements)
    if kinds not in (["PLANE"], ["CYLINDER", "PLANE", "PLANE"]):
        raise Rejected("Supported recipes: one planar pair, or two planar pairs plus an explicit rounded bend pair; sharp junction thickness is unresolved")
    # Deep-copy all source geometry before invoking topology-changing backend operations.
    copied = cq.Shape.cast(BRepBuilderAPI_Copy(shape.wrapped, True, False).Shape()).Faces()
    outer = sew([copied[p.outer] for p in pairs])
    inner = sew([copied[p.inner] for p in pairs])
    if topology(outer)[0]["components"] != 1 or topology(inner)[0]["components"] != 1:
        raise Rejected("The explicitly selected wall faces do not form one connected patch on each side")
    first = _offset(outer, -fraction * thickness_mm)
    second = _offset(inner, -(1 - fraction) * thickness_mm)
    common = BRepAlgoAPI_Common(first.wrapped, second.wrapped)
    common.SetNonDestructive(True)
    common.Build()
    if not common.IsDone():
        raise Rejected("Boolean correspondence between the two offsets failed")
    overlap = cq.Shape.cast(common.Shape())
    area_tolerance = TOL * max(1.0, math.sqrt(first.Area()))
    if abs(first.Area() - overlap.Area()) > area_tolerance or abs(second.Area() - overlap.Area()) > area_tolerance:
        raise Rejected("The paired offsets have different trimmed boundaries; manual preparation is required")
    result = sew(overlap.Faces())
    info, _ = topology(result)
    if info["faces"] != len(pairs) or info["components"] != 1 or info["nonmanifold_edges"] or info["shared_edges"] != len(pairs) - 1:
        raise Rejected("Candidate topology does not retain the expected connected wall patches")
    if digest(shape) != source_before:
        raise RuntimeError("Source BRep changed during candidate extraction")
    report = {"source_brep_sha256": source_before, "source_unchanged": True,
              "pairs": [{"outer_face_index": p.outer, "inner_face_index": p.inner, **m} for p, m in zip(pairs, measurements)],
              "thickness_mm": thickness_mm, "fraction_from_outer": fraction,
              "reference_shift_from_mid_along_outer_normal_mm": (0.5 - fraction) * thickness_mm,
              "candidate_role": "midsurface" if fraction == 0.5 else "offset reference surface, not midsurface",
              "topology": info, "outer_offset_area_mm2": first.Area(), "inner_offset_area_mm2": second.Area(),
              "common_area_mm2": overlap.Area(), "boundary_overlap_area_error_mm2": max(abs(first.Area() - overlap.Area()), abs(second.Area() - overlap.Area())),
              "candidate_brep_sha256": digest(result)}
    return result, report


def write_candidate(shape, pairs, destination, **options):
    """Compute/validate first, then atomically replace the explicitly supplied output."""
    candidate, report = extract(shape, pairs, **options)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(brep_bytes(candidate))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return candidate, report
