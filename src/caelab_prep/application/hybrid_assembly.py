"""Generate an audited conformal Cartesian hex-core assembly."""

from dataclasses import dataclass
from pathlib import Path

from .hybrid_hex_core import _generate, _verified_native
from .mesh_candidates import NativeMesh


@dataclass(frozen=True)
class HybridAssemblyCandidate:
    native: NativeMesh
    report: dict
    mesh_path: Path
    report_path: Path

    def to_native_mesh(self, *, length_unit=None):
        return _verified_native(self.native, length_unit)


def generate_hybrid_assembly(source, output_dir, *, length_unit, core_size, boundary_size=None,
                             safety_margin=0., min_scaled_jacobian=.025, min_tet_sicn=.08,
                             relative_volume_tolerance=.03, allow_tet_fallback=False,
                             cancel_event=None, timeout=120.):
    """Mesh closed OCC solids with one fragmented mesh on each shared CAD face.

    A Tet fallback applies per owning solid only when permitted. Part identities,
    shared face ownership, quality and the specific fallback reason remain in the report.
    """
    native, folder, report = _generate(source, output_dir, assembly=True, length_unit=length_unit,
        core_size=core_size, boundary_size=boundary_size, safety_margin=safety_margin,
        min_scaled_jacobian=min_scaled_jacobian, min_tet_sicn=min_tet_sicn,
        relative_volume_tolerance=relative_volume_tolerance, allow_tet_fallback=allow_tet_fallback,
        cancel_event=cancel_event, timeout=timeout)
    return HybridAssemblyCandidate(native, report, folder / "mesh.msh", folder / "report.json")
