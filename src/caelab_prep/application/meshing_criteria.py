"""Persisted mesher inputs; unsupported feature controls never become no-ops."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from uuid import uuid4

from ..cae_core.errors import PrepError


SCHEMA = "caelab.meshing-criteria"


def _length(value, field, *, zero=False):
    try:
        number = float(value) if type(value) in (int, float) else float("nan")
    except OverflowError:
        number = float("inf")
    if not math.isfinite(number) or (number < 0 if zero else number <= 0):
        raise PrepError("invalid_meshing_criteria", f"{field} must be a finite {'nonnegative' if zero else 'positive'} length.")
    return number


@dataclass(frozen=True)
class MeshingCriteria:
    length_unit: str
    target_size: float
    minimum_size: float
    washer_rim_divisions: int | None = None
    washer_width: float | None = None
    washer_layers: int | None = None
    fillet_suppression_threshold: float | None = None

    def __post_init__(self):
        if self.length_unit not in ("mm", "cm", "m"):
            raise PrepError("invalid_meshing_criteria", "Declare the criteria length unit: mm, cm or m.")
        object.__setattr__(self, "target_size", _length(self.target_size, "target_size"))
        object.__setattr__(self, "minimum_size", _length(self.minimum_size, "minimum_size"))
        if self.minimum_size > self.target_size:
            raise PrepError("invalid_meshing_criteria", "minimum_size must not exceed target_size.")
        if self.washer_rim_divisions is not None and (type(self.washer_rim_divisions) is not int or self.washer_rim_divisions < 3):
            raise PrepError("invalid_meshing_criteria", "washer_rim_divisions must be an integer of at least three.")
        if self.washer_width is not None:
            object.__setattr__(self, "washer_width", _length(self.washer_width, "washer_width"))
        if self.washer_layers is not None and (type(self.washer_layers) is not int or self.washer_layers < 1):
            raise PrepError("invalid_meshing_criteria", "washer_layers must be a positive integer.")
        if self.fillet_suppression_threshold is not None:
            object.__setattr__(self, "fillet_suppression_threshold",
                               _length(self.fillet_suppression_threshold, "fillet_suppression_threshold", zero=True))

    def to_dict(self):
        return {"schema": SCHEMA, "version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        required = {"schema", "version", "length_unit", "target_size", "minimum_size"}
        optional = {"washer_rim_divisions", "washer_width", "washer_layers", "fillet_suppression_threshold"}
        if not isinstance(value, dict) or required - value.keys() or value.keys() - required - optional:
            raise PrepError("invalid_meshing_criteria", "Expected the complete criteria schema with no unknown fields.")
        if value["schema"] != SCHEMA or type(value["version"]) is not int or value["version"] != 1:
            raise PrepError("invalid_meshing_criteria", "Unsupported meshing criteria schema/version.")
        return cls(**{key: item for key, item in value.items() if key not in ("schema", "version")})

    @classmethod
    def load(cls, path):
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate criteria field")
                result[key] = value
            return result
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
        except (OSError, UnicodeError, ValueError) as exc:
            raise PrepError("invalid_meshing_criteria", f"Cannot read criteria: {exc}") from exc
        return cls.from_dict(value)

    def save(self, path):
        path = Path(path).expanduser().resolve()
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        created = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("x", encoding="utf-8") as stream:
                created = True
                json.dump(self.to_dict(), stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
            temporary.replace(path)
        except OSError as exc:
            raise PrepError("meshing_criteria_io", f"Cannot save criteria: {exc}") from exc
        finally:
            if created:
                temporary.unlink(missing_ok=True)

    def _check_coordinate_unit(self, coordinate_length_unit):
        if coordinate_length_unit not in ("mm", "cm", "m"):
            raise PrepError("criteria_unknown_coordinate_unit", "The actual coordinate length unit must be known or explicitly declared.")
        if coordinate_length_unit != self.length_unit:
            raise PrepError("criteria_unit_mismatch", "Criteria and actual coordinate units must match; sizes are not implicitly rescaled.")

    def gmsh_kwargs(self, *, source_path, declared_coordinate_length_unit=None):
        """SDK input clamps, not a promise about every resulting element edge.

        A null feature control is unrequested. Non-null requests are retained in
        the file but rejected for execution until their actual implementation.
        STEP/IGES use normalized mm coordinates. Unitless CAD needs an explicit
        coordinate declaration; the original file's unit is not this contract.
        """
        from ..adapters.gmsh_backend import cad_coordinate_length_unit
        self._check_coordinate_unit(cad_coordinate_length_unit(
            source_path, declared_coordinate_length_unit=declared_coordinate_length_unit))
        unsupported = [field for field in ("washer_rim_divisions", "washer_width", "washer_layers", "fillet_suppression_threshold")
                       if getattr(self, field) is not None]
        if unsupported:
            raise PrepError("unsupported_meshing_criteria", "These feature controls are not implemented for the CAD backend.",
                            {"fields": unsupported})
        return {"mesh_size": self.target_size, "minimum_mesh_size": self.minimum_size,
                "expected_coordinate_length_unit": self.length_unit}

    def audit_minimum_edges(self, nodes, cells, *, coordinate_length_unit):
        """Evaluate the output minimum-edge criterion without modifying any mesh."""
        from .minimum_size_audit import audit_minimum_edges
        self._check_coordinate_unit(coordinate_length_unit)
        return {"criterion": "minimum_edge_length", "length_unit": self.length_unit,
                **audit_minimum_edges(nodes, cells, self.minimum_size)}
