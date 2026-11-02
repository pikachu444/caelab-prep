"""Optional saved-design → STEP preparation; never launches SolidCraft.

The CLI contract was read at SOURCE_REVISION. This is independently written
adapter code, not a port of SolidCraft or its Rust dependencies. Container
preflight is not its authoritative parser and does not sandbox a CAD engine.
"""
from dataclasses import dataclass
from hashlib import file_digest, sha256
import json
import math
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

from ..cae_core import PrepError
if TYPE_CHECKING:
    from ..application.mesh_candidates import MeshCandidate


SOURCE_REVISION = "27951f40c374b2495c1cf4648a87410179fa76cf"
MAX_DESIGN_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_STEP_BYTES = 128 * 1024 * 1024


def _digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _design_bytes(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_DESIGN_BYTES + 1)
    if len(data) > MAX_DESIGN_BYTES:
        raise PrepError("invalid_cad_source", "Saved CAD design exceeds the preparation size limit.")
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 4096 or len(names) != len(set(names)) or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
                raise ValueError("Ambiguous or oversized design container")
            for entry in entries:
                name = PurePosixPath(entry.filename)
                if name.is_absolute() or ".." in name.parts or "\\" in entry.filename or ":" in entry.filename or entry.flag_bits & 1:
                    raise ValueError("Unsupported container member path or encryption")
            headers = {}
            for name in ("container.json", "document.json"):
                item = archive.getinfo(name)
                if item.file_size > MAX_JSON_BYTES:
                    raise ValueError("Oversized design metadata")
                with archive.open(item) as stream:
                    headers[name] = json.loads(stream.read(MAX_JSON_BYTES + 1))
            container, document = headers["container.json"], headers["document.json"]
            if not isinstance(container, dict) or container.get("format") != "solidcraft-container/1":
                raise ValueError("Expected a saved SolidCraft container, not a script")
            if (not isinstance(document, dict) or document.get("format") not in ("solidcraft/46", "solidcraft/47")
                    or not isinstance(document.get("name"), str) or not isinstance(document.get("params"), list)
                    or not isinstance(document.get("features"), list)):
                raise ValueError("Unsupported saved design format or document fields")
    except (zipfile.BadZipFile, KeyError, ValueError, UnicodeError, RuntimeError) as exc:
        raise PrepError("invalid_cad_source", "A supported saved SolidCraft design container is required.", {"reason": str(exc)}) from exc
    return data, document["format"]


@dataclass(frozen=True)
class SuppliedStepCandidate:
    candidate: "MeshCandidate"
    document_id: str
    revision: int
    document_epoch: str
    step_sha256: str
    design_sha256: str
    executable_sha256: str


@dataclass(frozen=True)
class PreparedSolidCraftStep:
    executable: Path
    executable_sha256: str
    declared_version: str
    captured_design: Path
    design_sha256: str
    design_format: str
    step_path: Path
    timeout: float

    @property
    def argv(self):
        return (str(self.executable), "run", "--in", str(self.captured_design), "--out", str(self.step_path),
                "--quiet", "--param-check", "strict")

    def receipt(self):
        return {"declared_producer": "SolidCraft", "source_revision": SOURCE_REVISION,
                "declared_executable_version": self.declared_version, "executable_sha256": self.executable_sha256,
                "design_sha256": self.design_sha256, "design_format": self.design_format,
                "expected_step_length_unit": "mm", "execution_status": "unexecuted",
                "format_preflight_passed": True, "authoritative_format_validation": "unexecuted",
                "limits": ["No process isolation is provided", "Embedded links may be stale",
                           "External fonts are not captured", "STEP does not carry CAE condition identity"]}

    def validate_step(self):
        """Validate a supplied result before the existing Gmsh worker reads it.

        This does not establish that SolidCraft ran or that the CAD is valid.
        Gmsh's actual CAD import and candidate quality gates remain authoritative.
        """
        try:
            unchanged = _digest(self.captured_design) == self.design_sha256 and _digest(self.executable) == self.executable_sha256
        except OSError as exc:
            raise PrepError("stale_cad_source", "A captured CAD input can no longer be read.", {"reason": str(exc)}) from exc
        if not unchanged:
            raise PrepError("stale_cad_source", "The captured design or selected executable changed.")
        path = self.step_path
        if path.is_symlink() or not path.is_file() or path.resolve().parent != self.captured_design.parent.resolve():
            raise PrepError("invalid_cad_result", "The owned job directory must contain a regular STEP result.")
        size = path.stat().st_size
        if not 0 < size <= MAX_STEP_BYTES:
            raise PrepError("invalid_cad_result", "The STEP result is empty or exceeds the size limit.")
        with path.open("rb") as stream:
            start = stream.read(4096).lstrip()
            stream.seek(max(0, size - 4096))
            end = stream.read()
        if not start.startswith(b"ISO-10303-21;") or b"END-ISO-10303-21;" not in end:
            raise PrepError("invalid_cad_result", "The result is not a complete STEP exchange file.")
        return path

    def generate_mesh_candidate(self, session, candidate_dir, mesh_size_mm, *, cancel_event=None, interface_policy="preserve"):
        """Capture the target before the existing worker runs; no document writes."""
        from .gmsh_backend import GmshBackend
        from ..application.mesh_candidates import read_mesh_candidate
        owner = session.describe()
        if not owner.get("document_id"):
            raise PrepError("no_document", "Open the target CAE document before starting its CAD candidate.")
        step = self.validate_step()
        digest = _digest(step)
        metadata = GmshBackend(timeout=self.timeout).generate(step, candidate_dir, mesh_size_mm,
            dimension=3, cancel_event=cancel_event, interface_policy=interface_policy)
        if (metadata["source"]["sha256"] != digest or _digest(step) != digest
                or Path(metadata["source"]["path"]).resolve() != step.resolve()):
            raise PrepError("cad_source_mismatch", "The STEP input changed while generating the candidate.")
        return SuppliedStepCandidate(read_mesh_candidate(metadata), owner["document_id"], owner["revision"], owner["document_epoch"],
                                     digest, self.design_sha256, self.executable_sha256)

    def adopt_supplied_step(self, session, handoff, *, material_id, property_id, name=None):
        """Keep an unverified preparation declaration with the normal atomic adopt.

        This is the history of the supplied input, not a claim that SolidCraft
        produced it. The existing native conversion and admission gates apply.
        """
        if (not isinstance(handoff, SuppliedStepCandidate) or handoff.design_sha256 != self.design_sha256
                or handoff.executable_sha256 != self.executable_sha256):
            raise PrepError("cad_source_mismatch", "Use a candidate from this preparation and its original target document.")
        step = self.validate_step()
        native = handoff.candidate.to_native_mesh()
        sources = [asset for asset in native.assets if asset.kind == "source"]
        if len(sources) != 1 or sources[0].sha256 != handoff.step_sha256 or sources[0].sha256 != _digest(step):
            raise PrepError("cad_source_mismatch", "The candidate must come from this supplied STEP snapshot.")
        declaration = {"format": "caelab-cad-source-declaration/1", "verification": "unverified",
                       "declared_producer": "SolidCraft", "declared_version": self.declared_version,
                       "design_sha256": self.design_sha256, "executable_sha256": self.executable_sha256,
                       "step_sha256": sources[0].sha256, "expected_step_length_unit": "mm"}
        return session.adopt_mesh_candidate(native, material_id=material_id, property_id=property_id, name=name,
            expected_revision=handoff.revision, expected_document_id=handoff.document_id,
            expected_document_epoch=handoff.document_epoch, source_declaration=declaration)


def prepare_solidcraft_step(executable, design, output_dir, *, declared_version, timeout=120.0):
    """Capture a saved design and prepare fixed argv. Does not execute a CAD app.

    An explicit trusted execution owner must run argv with shell=False, own its
    process timeout/cancellation/logs, and check its exit status before handing
    off STEP. This function grants no permission to run an external executable.
    """
    executable, design = Path(executable), Path(design)
    if not executable.is_absolute() or not executable.is_file() or executable.is_symlink():
        raise PrepError("invalid_cad_source", "Select an existing absolute CAD executable path.")
    if not design.is_file() or not isinstance(declared_version, str) or not declared_version.strip():
        raise PrepError("invalid_cad_source", "Select a saved design and declare the installed CAD version.")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PrepError("invalid_cad_source", "CAD timeout must be finite and positive.")
    data, design_format = _design_bytes(design)
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="solidcraft-", dir=root)).resolve()
    captured, receipt = folder / "source.sc", folder / "preparation.json"
    try:
        captured.write_bytes(data)
        job = PreparedSolidCraftStep(executable.resolve(), _digest(executable), declared_version.strip(), captured,
            sha256(data).hexdigest(), design_format, folder / "produced.step", float(timeout))
        receipt.write_text(json.dumps(job.receipt(), indent=2) + "\n", encoding="utf-8")
        return job
    except Exception:
        # Roll back only the two files this preparation owns; preserve surprises.
        for path in (captured, receipt):
            path.unlink(missing_ok=True)
        if not any(folder.iterdir()):
            folder.rmdir()
        raise
