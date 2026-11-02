"""Immutable source archives and explicit independent-native-model imports."""
from copy import copy
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from ..cae_core import CommandDispatcher, PrepError
from ..radioss import DeckResource
from ..radioss.assembly import inspect, remap, identity, NativeMap
from .projection import readonly, mutable


class SourceArchiveResource:
    kind = "radioss-source-archive"

    def __init__(self, metadata, files):
        if not isinstance(metadata, dict) or set(metadata) != {"id", "name", "root_resource_id", "files", "id_map", "shared_nodes"}:
            raise PrepError("invalid_project", "Invalid source archive metadata.")
        self.id = metadata["id"]; UUID(self.id)
        if not isinstance(metadata["name"], str) or not isinstance(metadata["files"], list) or not metadata["files"]:
            raise PrepError("invalid_project", "An archive must identify its source files.")
        ids, paths = set(), set()
        for item in metadata["files"]:
            if set(item) != {"original_resource_id", "resource_id", "original_path", "logical_path", "sha256"}:
                raise PrepError("invalid_project", "Invalid archive file record.")
            UUID(item["original_resource_id"]); UUID(item["resource_id"])
            if item["original_resource_id"] in ids or item["logical_path"].casefold() in paths:
                raise PrepError("invalid_project", "Duplicate archive file identity or path.")
            ids.add(item["original_resource_id"]); paths.add(item["logical_path"].casefold())
            payload = files.get(item["original_resource_id"])
            if not isinstance(payload, bytes) or sha256(payload).hexdigest() != item["sha256"]:
                raise PrepError("invalid_project", "Source archive bytes do not match the recorded digest.")
        if ids != set(files) or metadata["root_resource_id"] not in {item["resource_id"] for item in metadata["files"]}:
            raise PrepError("invalid_project", "Source archive membership is inconsistent.")
        seen = set()
        for entry in metadata["id_map"]:
            if not isinstance(entry, list) or len(entry) != 3 or not isinstance(entry[0], str) or any(type(v) is not int or v < 1 for v in entry[1:]):
                raise PrepError("invalid_project", "Invalid source/native mapping.")
            if tuple(entry[:2]) in seen: raise PrepError("invalid_project", "Repeated original native identity.")
            seen.add(tuple(entry[:2]))
        if not isinstance(metadata["shared_nodes"], list) or any(type(i) is not int or ("NODE", i) not in seen for i in metadata["shared_nodes"]):
            raise PrepError("invalid_project", "Invalid explicit shared-node mapping.")
        self.metadata = readonly(metadata)
        self.files = readonly(files)
        self._token = sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()

    def snapshot(self): return {"state_version": 1}
    def prepare_state(self, state):
        if state != {"state_version": 1}: raise PrepError("invalid_project", "Source archives are immutable.")
        return {"state_version": 1}
    def restore(self, state): self.prepare_state(state)
    def state_token(self): return self._token
    def manifest(self): return mutable(self.metadata)

    def validate_mapped_payloads(self, document):
        """The correspondence table is checked evidence, not an unchecked label."""
        originals = [DeckResource(self.files[item["original_resource_id"]], resource_id=item["original_resource_id"],
            name=item["original_path"], is_include=item["resource_id"] != self.metadata["root_resource_id"])
            for item in self.metadata["files"]]
        definitions, _, _ = inspect(originals)
        mapping = NativeMap({(ns, original): mapped for ns, original, mapped in self.metadata["id_map"]},
                            shared={("NODE", value) for value in self.metadata["shared_nodes"]})
        if set(definitions) != set(mapping):
            raise PrepError("invalid_project", "Source mapping does not cover the original native definitions exactly.")
        paths = {item["original_path"]: item["logical_path"] for item in self.metadata["files"]}
        expected = remap(originals, mapping, paths)
        for item in self.metadata["files"]:
            resource = document.resources.get(item["resource_id"])
            if not isinstance(resource, DeckResource) or resource.raw != expected[item["original_resource_id"]]:
                raise PrepError("invalid_project", "Mapped native payload differs from its archived source and correspondence table.")


class SourceModelCommands:
    def source_models(self):
        with self._lock:
            return [resource.manifest() for resource in self._require().resources.values() if isinstance(resource, SourceArchiveResource)]

    def _source_roots(self, document=None):
        return [resource.metadata["root_resource_id"] for resource in (document or self._require()).resources.values()
                if isinstance(resource, SourceArchiveResource)]

    def _sync_source_paths(self):
        document = self._require()
        self._paths = {key: value for key, value in self._paths.items() if key in document.resources}
        for resource in document.resources.values():
            if isinstance(resource, SourceArchiveResource):
                self._paths.update({item["resource_id"]: item["logical_path"] for item in resource.metadata["files"]})

    def plan_import_source(self, path, *, shared_node_map=None):
        """Snapshot the input and propose every remapped ID without changing the model.

        ``shared_node_map`` maps an ORIGINAL source node ID to an existing typed
        node reference. Equal coordinates alone never imply sharing.
        """
        with self._lock:
            document = self._require()
            source = type(self)(); source.open_rad(path)
            if any(item.get("unresolved_include") for item in source.diagnostics()):
                raise PrepError("unresolved_include", "Resolve every source INCLUDE before importing.")
            original_resources = source._deck_resources()
            definitions, _, _ = inspect(original_resources)
            # An unknown destination reference could accidentally acquire a new
            # meaning when a previously unused native ID is allocated.
            inspect(self._deck_resources())
            def units(session):
                root = session.document.resources[session._root_id]
                begin = next((card for card in root.cards if card.keyword.upper() == "/BEGIN"), None)
                if begin is None or len(begin.data) < 4: raise PrepError("unsupported_source_units", "Import requires explicit input and working units.")
                values = [tuple(root.lines[index].split()) for index in begin.data[2:4]]
                allowed = ({"Mg", "kg", "g"}, {"mm", "cm", "m"}, {"s", "ms", "mus"})
                if any(len(row) != 3 or any(token not in allowed[i] for i, token in enumerate(row)) for row in values):
                    raise PrepError("unsupported_source_units", "Unsupported source input/working units.")
                return values
            if units(source) != units(self):
                raise PrepError("source_units_mismatch", "This import profile requires identical explicit input and working units; no silent conversion is performed.")
            existing = set()
            for resource in self._deck_resources():
                for card in resource.cards:
                    key = identity(card.keyword)
                    if key: existing.add(key)
            projection = self.mesh_view()
            existing.update(("NODE", identifier) for identifier in projection["node_ids"])
            element_ids = {cell["id"] for cell in projection["cells"]}
            shared = shared_node_map or {}
            if not isinstance(shared, dict): raise PrepError("invalid_reference", "Explicit shared-node mappings must be an object.")
            source_projection = source.mesh_view()
            source_points = dict(zip(source_projection["node_ids"], source_projection["points"]))
            destination_points = dict(zip(projection["node_ids"], projection["points"]))
            mapping = NativeMap(shared={("NODE", key) for key in shared})
            for original, reference in shared.items():
                if type(original) is not int or ("NODE", original) not in definitions or not isinstance(reference, dict) or set(reference) != {"resource_id", "entity_kind", "local_id"}:
                    raise PrepError("invalid_reference", "Use source node IDs and resource-qualified destination node references.")
                target = reference["local_id"]
                if reference["entity_kind"] != "node" or type(target) is not int or projection["node_resources"].get(target) != (reference["resource_id"],):
                    raise PrepError("invalid_reference", "The shared destination node is not uniquely resolved.")
                if source_points[original] != destination_points[target]:
                    raise PrepError("shared_node_coordinate_mismatch", "Explicit node sharing requires identical coordinates in the agreed units.")
                mapping[("NODE", original)] = target
            collisions = []
            next_ids = {}
            used_by_namespace = {}
            for namespace, value in existing: used_by_namespace.setdefault(namespace, set()).add(value)
            for namespace, original in sorted(definitions):
                if (namespace, original) in mapping: continue
                used = element_ids if namespace.startswith("E:") else used_by_namespace.setdefault(namespace, set())
                identifier = original
                if identifier in used:
                    collisions.append([namespace, original])
                    pool = "ELEMENT" if namespace.startswith("E:") else namespace
                    identifier = max(next_ids.get(pool, 1), max(used, default=0) + 1)
                    while identifier in used: identifier += 1
                    next_ids[pool] = identifier + 1
                if identifier > 9999999999: raise PrepError("native_id_exhausted", "Native ID capacity is exhausted.")
                mapping[(namespace, original)] = identifier
                used.add(identifier)
            source_id = str(uuid4()); prefix = f"sources/{source_id}/"
            translated_paths = {logical: prefix + logical for logical in source._paths.values()}
            payloads = remap(original_resources, mapping, translated_paths)
            resources, files, records = [], {}, []
            root_id = None
            for original in original_resources:
                logical = translated_paths[source._paths[original.id]]
                converted = DeckResource(payloads[original.id], name=logical, is_include=True)
                resources.append(converted); files[original.id] = original.raw
                if original.id == source._root_id: root_id = converted.id
                records.append(dict(original_resource_id=original.id, resource_id=converted.id,
                    original_path=source._paths[original.id], logical_path=logical, sha256=sha256(original.raw).hexdigest()))
            archive = SourceArchiveResource(dict(id=source_id, name=Path(path).name, root_resource_id=root_id,
                files=records, id_map=[[ns, original, mapped] for (ns, original), mapped in sorted(mapping.items())],
                shared_nodes=sorted(shared)), files)
            plan_id = str(uuid4())
            self._import_plan = (plan_id, document.id, document.revision, self._document_epoch, archive, tuple(resources), source._source_paths)
            return {"plan_id": plan_id, "document_id": document.id, "revision": document.revision,
                    "document_epoch": self._document_epoch, "source": archive.manifest(), "collisions": collisions,
                    "node_count": len(source_projection["node_ids"]), "element_count": len(source_projection["cells"])}

    def import_source(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_import_plan", None)
            if plan is None or plan[:4] != (plan_id, self.document.id, self.document.revision, self._document_epoch):
                raise PrepError("stale_import_plan", "Prepare the source mapping against the current document again.")
            _, _, _, _, archive, resources, originals = plan
            change = self.dispatcher.execute_many({}, "Import independent source", additions=(*resources, archive),
                                                 expected_revision=self.document.revision, kind="structure")
            self._source_paths.update(originals)
            self._import_plan = None
            return {**self.describe(), "source_model_id": archive.id, "resource_ids": [resource.id for resource in resources],
                    "change": change.to_dict()}

    def execute_many(self, commands, *, label="Edit model relationships", expected_revision=None, expected_document_id=None):
        """Validate domain operations on sparse candidate resources, then publish once."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            allowed = {"set_fields", "set_condition_values", "set_group_members", "assign_part", "set_analysis_case",
                       "create_analysis_case", "delete_analysis_case", "select_analysis_case"}
            if not isinstance(commands, list) or not commands:
                raise PrepError("invalid_command", "Provide a nonempty list of domain commands.")
            candidate = copy(self); candidate._lock = RLock(); candidate._listeners = []
            candidate.document = copy(self.document)
            candidate.document.resources = {key: copy(resource) for key, resource in self.document.resources.items()}
            candidate.dispatcher = CommandDispatcher(candidate.document)
            candidate.dispatcher.subscribe(candidate._command_changed)
            candidate_changes = []
            candidate.dispatcher.subscribe(candidate_changes.append)
            candidate._paths = dict(self._paths); candidate._source_paths = set(self._source_paths)
            results = []
            for command in commands:
                if not isinstance(command, dict) or set(command) != {"operation", "arguments"} or command["operation"] not in allowed or not isinstance(command["arguments"], dict):
                    raise PrepError("invalid_command", "Unsupported compound domain command.")
                if any(key.startswith("expected_") for key in command["arguments"]):
                    raise PrepError("invalid_command", "Use one transaction revision precondition.")
                results.append(getattr(candidate, command["operation"])(**command["arguments"]))
            for case in candidate.analysis_cases()["cases"]: candidate._validate_case_refs(case)
            states = {key: resource.snapshot() for key, resource in candidate.document.resources.items()
                      if resource.state_token() != self.document.resources[key].state_token()}
            kind = "structure" if any(item.kind == "structure" for item in candidate_changes) else "field"
            change = self.dispatcher.execute_many(states, label, expected_revision=self.document.revision, kind=kind)
            return {**self.describe(), "change": change.to_dict() if change else None,
                    "operation_count": len(results)}
