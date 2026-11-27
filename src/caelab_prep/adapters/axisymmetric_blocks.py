"""Partition one Z-aligned stepped annulus from trimmed cylindrical/conical CAD."""
from collections import Counter
import math


def _meridian(model, solid):
    occ = model.occ
    faces = model.getBoundary([(3, solid)], oriented=False)
    box = model.getBoundingBox(3, solid)
    tolerance = max(1e-7, 1e-10 * math.dist(box[:3], box[3:]))
    stations = []
    walls = []
    axis = None
    circles = {}
    for _, face in faces:
        kind = model.getType(2, face)
        if kind not in ("Cylinder", "Cone", "Plane"):
            raise ValueError(f"Revolved block partition cannot represent CAD surface {face} ({kind})")
        rings = []
        for _, edge in model.getBoundary([(2, face)], oriented=False):
            if model.getType(1, edge) != "Circle":
                continue
            if edge not in circles:
                lo, hi = model.getParametrizationBounds(1, edge)
                x, y, z = occ.getCenterOfMass(1, edge)
                bounds = model.getBoundingBox(1, edge)
                if (not math.isclose(float(hi[0] - lo[0]), 2*math.pi, abs_tol=1e-8)
                        or bounds[5] - bounds[2] > 4*tolerance):
                    raise ValueError("Revolved partition requires complete horizontal circular trim edges")
                if axis is None:
                    axis = x, y
                if math.dist((x, y), axis) > tolerance:
                    raise ValueError("Circular CAD trims do not share one revolution axis")
                r = occ.getMass(1, edge) / (2*math.pi)
                if r <= tolerance:
                    raise ValueError("Revolved blocks require a finite open through bore")
                circles[edge] = z, r
                stations.append(z)
            rings.append(circles[edge])
        if len(rings) != 2:
            raise ValueError(f"CAD face {face} requires exactly two circular trim edges")
        (za, ra), (zb, rb) = sorted(rings)
        if kind == "Plane":
            if zb - za > tolerance:
                raise ValueError("A revolved step must have planar axial end or shoulder faces")
        elif zb-za <= tolerance:
            raise ValueError(f"CAD side face {face} has no axial span")
        else:
            walls.append((za, zb, ra, rb))

    levels = []
    for z in sorted(stations):
        if not levels or z - levels[-1] > tolerance:
            levels.append(z)
    sections = []
    for z0, z1 in zip(levels, levels[1:]):
        mid = (z0 + z1) / 2
        borders = []
        for za, zb, ra, rb in walls:
            if za < mid < zb:
                slope = (rb-ra)/(zb-za)
                borders.append((ra + slope*(z0-za), ra + slope*(z1-za)))
        if len(borders) != 2:
            raise ValueError("Each axial interval must contain exactly one annular material band")
        inner, outer = sorted(borders)
        if any(a <= tolerance or b-a <= tolerance for a, b in zip(inner, outer)):
            raise ValueError("The revolved profile touches the axis or has a collapsed section")
        sections.append((z0, z1, inner, outer))
    if not sections:
        raise ValueError("No positive axial annulus in this CAD solid")
    return axis, levels, sections, tolerance


def _quadrilaterals(sections, tolerance):
    # Propagate every radial shoulder across all intervals containing that
    # radius. A conical end by itself introduces no interior radial cut.
    radii = []
    for (_, _, left_i, left_o), (_, _, right_i, right_o) in zip(sections, sections[1:]):
        for a, b in ((left_i[1], right_i[0]), (left_o[1], right_o[0])):
            if abs(a-b) > tolerance:
                radii.extend([a, b])
    cuts = []
    for r in sorted(radii):
        if not cuts or r - cuts[-1] > tolerance:
            cuts.append(r)
    for z0, z1, inner, outer in sections:
        lines = [inner]
        for r in cuts:
            at_start = inner[0] + tolerance < r < outer[0] - tolerance
            at_end = inner[1] + tolerance < r < outer[1] - tolerance
            if at_start != at_end:
                raise ValueError("A radial shoulder crosses a sloped wall inside a sweep block")
            if at_start:
                lines.append((r, r))
        lines.append(outer)
        for lower, upper in zip(lines, lines[1:]):
            yield [(lower[0], z0), (upper[0], z0), (upper[1], z1), (lower[1], z1)]


def partition_revolved_solid(gmsh):
    """Derive four azimuthal sectors for each meridional band and prove CAD coverage."""
    model, occ = gmsh.model, gmsh.model.occ
    solids = model.getEntities(3)
    if len(solids) != 1:
        raise ValueError("Automatic revolved partition requires one closed CAD solid")
    source = solids[0]
    mass = occ.getMass(*source)
    source_faces = model.getBoundary([source], oriented=False)
    source_areas = {face: occ.getMass(2, face) for _, face in source_faces}
    source_names = {str(tag): model.getEntityName(dim, tag) for dim, tag in source_faces}
    solid_name = model.getEntityName(*source)
    axis, levels, sections, tolerance = _meridian(model, source[1])
    x0, y0 = axis
    blocks = []
    for corners in _quadrilaterals(sections, tolerance):
        for sector in range(4):
            theta = sector * math.pi/2
            nodes = [occ.addPoint(x0+r*math.cos(theta), y0+r*math.sin(theta), z)
                     for r, z in corners]
            sides = [occ.addLine(a, b) for a, b in zip(nodes, nodes[1:]+nodes[:1])]
            face = occ.addPlaneSurface([occ.addCurveLoop(sides)])
            entities = occ.revolve([(2, face)], x0, y0, 0, 0, 0, 1, math.pi/2)
            sector_volumes = [entity for entity in entities if entity[0] == 3]
            if len(sector_volumes) != 1:
                raise ValueError("OCC could not revolve a meridional quadrilateral")
            blocks.extend(sector_volumes)

    # OCC returns the exact shared subregions for both operands. Equality of
    # region IDs detects omitted and protruding material even at equal mass.
    _, children = occ.fragment([source], blocks + source_faces)
    volume_maps = children[:1+len(blocks)]
    surface_maps = children[1+len(blocks):]
    volume_ids = [{tag for dim, tag in region if dim == 3} for region in volume_maps]
    source_ids = volume_ids[0]
    if (any(len(ids) != 1 for ids in volume_ids[1:]) or len(source_ids) != len(blocks)
            or source_ids != set().union(*volume_ids[1:])):
        raise ValueError("Revolved block union differs from the imported CAD solid")
    occ.synchronize()
    actual = sorted(source_ids)
    if set(model.getEntities(3)) != {(3, tag) for tag in actual}:
        raise ValueError("Unexpected residual solids after revolved partition")
    total = math.fsum(occ.getMass(3, tag) for tag in actual)
    if not math.isclose(total, mass, rel_tol=1e-9):
        raise ValueError("The revolved OCC partition changed the material volume")
    incidence = Counter()
    for tag in actual:
        faces = model.getBoundary([(3, tag)], oriented=False)
        if len(faces) != 6 or any(len(model.getBoundary([face], oriented=False)) != 4 for face in faces):
            raise ValueError(f"Revolved CAD block {tag} needs further face partitioning")
        incidence.update(face for _, face in faces)
    face_map = {str(original): sorted(int(tag) for dim, tag in region if dim == 2)
                for (_, original), region in zip(source_faces, surface_maps, strict=True)}
    exterior = Counter(tag for tag, count in incidence.items() if count == 1)
    if Counter(tag for tags in face_map.values() for tag in tags) != exterior:
        raise ValueError("Revolved partition cannot preserve the complete source skin")
    for original, area in source_areas.items():
        covered = math.fsum(occ.getMass(2, child) for child in face_map[str(original)])
        if not math.isclose(area, covered, rel_tol=1e-9):
            raise ValueError(f"Revolved partition changed the trimmed area of CAD face {original}")
    return {"original_volume": mass, "partition_volume": total,
            "source_to_block_tags": {str(source[1]): actual}, "axis_xy": list(axis),
            "source_to_block_face_tags": face_map, "source_face_names": source_names,
            "source_volume_name": solid_name,
            "axial_stations": levels, "meridional_bands": len(actual)//4}
