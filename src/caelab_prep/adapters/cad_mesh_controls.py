"""Validate advanced settings at both ends of the Gmsh worker boundary."""
import math


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_controls(settings, size, minimum, dimension, local_sizes, extension):
    allowed = {"curvature_points", "size_gradient", "structured_blocks", "edge_seeds",
               "element_order", "quality_diagnostics", "prismatic_layers", "block_partition"}
    if not isinstance(settings, dict) or set(settings) - allowed:
        raise ValueError("Unknown advanced CAD meshing control")
    for key in ("structured_blocks", "quality_diagnostics"):
        if type(settings.get(key, False)) is not bool:
            raise ValueError(f"{key} must be boolean")
    samples = settings.get("curvature_points", 0)
    if type(samples) is not int or samples < 0 or 0 < samples < 3:
        raise ValueError("curvature_points must be zero or at least three elements per circle")
    if samples and (minimum is None or minimum >= size):
        raise ValueError("Curvature sizing requires an explicit minimum smaller than the maximum")
    grad = settings.get("size_gradient")
    if grad is not None and (not samples or not _finite(grad) or grad <= 0 or local_sizes):
        raise ValueError("size_gradient requires curvature sizing and a positive slope without a local size field")
    if grad is not None and not math.isfinite((size - minimum) / grad):
        raise ValueError("The curvature growth distance exceeds the finite coordinate range")
    order = settings.get("element_order", 1)
    if type(order) is not int or order not in (1, 2):
        raise ValueError("element_order must be 1 or 2")
    seeds = settings.get("edge_seeds", {})
    mapped = settings.get("structured_blocks")
    partition = settings.get("block_partition")
    if partition is not None and (partition != "revolved" or not mapped or seeds or extension == ".xao"):
        raise ValueError("Revolved partitioning requires fresh mapped CAD with automatic edge divisions")
    if not isinstance(seeds, dict) or (seeds and not mapped):
        raise ValueError("edge_seeds requires structured_blocks")
    curve_tags = set()
    for tag, spec in seeds.items():
        if (type(tag) not in (str, int) or not str(tag).isascii() or not str(tag).isdecimal()
                or str(tag).startswith("0") or not isinstance(spec, (list, tuple)) or len(spec) != 3):
            raise ValueError("An edge seed requires a CAD curve tag and (divisions, distribution, factor)")
        if int(tag) in curve_tags:
            raise ValueError(f"Duplicate edge seed on curve {tag}")
        curve_tags.add(int(tag))
        n, mode, value = spec
        if (type(n) is not int or n < 1 or mode not in ("Progression", "Bump")
                or not _finite(value) or value <= 0
                or (mode == "Progression" and not math.isfinite(1 / value))):
            raise ValueError(f"Invalid transfinite seed on curve {tag}")
    if mapped and (dimension != 3 or samples or local_sizes):
        raise ValueError("Mapped volumes require 3D and use edge divisions for sizing")
    layers = settings.get("prismatic_layers")
    if layers is not None:
        if (not isinstance(layers, dict) or set(layers) != {"face", "vector", "heights"}
                or dimension != 3 or order != 1 or mapped or extension == ".xao" or local_sizes):
            raise ValueError("Use a fresh 3D linear prismatic CAD solid with face, vector and heights")
        face, vector, heights = layers["face"], layers["vector"], layers["heights"]
        if (type(face) is not int or face <= 0 or not isinstance(vector, (list, tuple))
                or len(vector) != 3 or not all(map(_finite, vector))
                or not 0 < math.hypot(*vector) < math.inf):
            raise ValueError("Select a positive CAD face tag and a finite nonzero wall-normal vector")
        if (not isinstance(heights, (list, tuple)) or not heights or heights[-1] != 1
                or not all(map(_finite, heights)) or any(a >= b for a, b in zip([0, *heights], heights))):
            raise ValueError("Supply strictly increasing cumulative layer fractions ending at one")
