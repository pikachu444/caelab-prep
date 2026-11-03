"""Small immutable generation inputs, separate from native source archives."""
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4
import json

from ..cae_core import PrepError
from .projection import readonly, mutable
from .structured_geometry import MAX_RECIPE_BYTES, validate_recipe
from .structured_mesh import _loads_json, validate_recipe_edit


class StructuredRecipeArchive:
    kind = "structured-recipe-archive"

    def __init__(self, metadata, files):
        try:
            if not isinstance(files, dict) or not isinstance(metadata, dict) or set(metadata) != {"id", "mesh_uuid", "files"}:
                raise ValueError("Invalid recipe archive metadata")
            for key in ("id", "mesh_uuid"):
                if not isinstance(metadata[key], str): raise ValueError("Invalid recipe identity")
                UUID(metadata[key])
            records = metadata["files"]
            if not isinstance(records, list) or not 1 <= len(records) <= 2:
                raise ValueError("Expected one recipe and an optional original input")
            roles, recipes = set(), {}
            for item in records:
                if not isinstance(item, dict) or set(item) != {"role", "original_path", "sha256"}:
                    raise ValueError("Invalid recipe file record")
                role = item["role"]
                if role not in ("recipe", "source_recipe") or role in roles:
                    raise ValueError("Invalid or repeated recipe role")
                if not isinstance(item["original_path"], str) or not item["original_path"].strip() or "\0" in item["original_path"]:
                    raise ValueError("Invalid original recipe path")
                raw = files.get(role)
                if not isinstance(raw, bytes) or len(raw) > MAX_RECIPE_BYTES or sha256(raw).hexdigest() != item["sha256"]:
                    raise ValueError("Recipe bytes do not match the bounded recorded digest")
                spec = _loads_json(raw.decode("utf-8"))
                validate_recipe(spec)
                if spec["mode"] not in ("quad", "hex"):
                    raise ValueError("Only the connected quad and hex generation inputs are archived")
                roles.add(role); recipes[role] = spec
            if "recipe" not in roles or roles != set(files): raise ValueError("Incomplete recipe archive membership")
            if "source_recipe" in roles: validate_recipe_edit(recipes["source_recipe"], recipes["recipe"])
        except (PrepError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise PrepError("invalid_project", "Invalid structured recipe archive.", {"reason": str(exc)}) from exc
        self.id = metadata["id"]
        spec = recipes["recipe"]
        self.description = readonly({"name": spec.get("name") or "Structured recipe",
                                     "mode": spec["mode"], "length_unit": spec["unit"]})
        self.metadata = readonly(metadata)
        self.files = MappingProxyType(dict(files))
        self._token = sha256(json.dumps(metadata, sort_keys=True).encode("utf-8")).hexdigest()

    @classmethod
    def capture(cls, native):
        records, files = [], {}
        for asset in native.assets:
            if asset.kind not in ("recipe", "source_recipe"): continue
            with Path(asset.path).open("rb") as stream: raw = stream.read(MAX_RECIPE_BYTES + 1)
            if len(raw) > MAX_RECIPE_BYTES or sha256(raw).hexdigest() != asset.sha256:
                raise PrepError("candidate_changed", "A recipe changed after candidate validation.")
            records.append({"role": asset.kind, "original_path": asset.path, "sha256": asset.sha256})
            files[asset.kind] = raw
        return cls({"id": str(uuid4()), "mesh_uuid": native.mesh_uuid, "files": records}, files)

    def snapshot(self): return {"state_version": 1}
    def prepare_state(self, state):
        if state != {"state_version": 1}: raise PrepError("invalid_project", "Recipe archives are immutable.")
        return {"state_version": 1}
    def restore(self, state): self.prepare_state(state)
    def state_token(self): return self._token
    def manifest(self): return mutable(self.metadata)


class RecipeArchiveCommands:
    def structured_mesh_recipes(self):
        with self._lock:
            records = []
            document = self._require()
            context = {"document_id": document.id, "document_epoch": self._document_epoch, "revision": document.revision}
            for resource in document.resources.values():
                if not isinstance(resource, StructuredRecipeArchive): continue
                records.append({**resource.manifest(), **resource.description, **context})
            return records

    def export_structured_recipe(self, archive_id, directory, *, expected_document_id=None,
                                 expected_document_epoch=None, expected_revision=None):
        """Extract immutable inputs to a fresh folder; never overwrite a file."""
        with self._lock:
            document = self._require()
            if ((expected_document_id is not None and expected_document_id != document.id)
                    or (expected_document_epoch is not None and expected_document_epoch != self._document_epoch)
                    or (expected_revision is not None and (type(expected_revision) is not int or expected_revision != document.revision))):
                raise PrepError("stale_recipe_selection", "The project changed after choosing its generation input. Choose the recipe again.")
            resource = document.resources.get(archive_id) if isinstance(archive_id, str) else None
            if not isinstance(resource, StructuredRecipeArchive):
                raise PrepError("invalid_reference", "Choose an archived structured recipe.")
            target = Path(directory).expanduser().resolve()
            try:
                target.mkdir(parents=True, exist_ok=False)
                paths = {}
                for role, raw in resource.files.items():
                    path = target / (role + ".json")
                    with path.open("xb") as stream: stream.write(raw)
                    paths[role + "_path"] = str(path)
            except OSError as exc:
                raise PrepError("file_io_error", "Could not extract the recipe into a new folder.", {"reason": str(exc)}) from exc
            return {"archive_id": resource.id, **paths}
