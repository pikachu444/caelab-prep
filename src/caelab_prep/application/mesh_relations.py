"""Prepared mesh replacement with explicit stale-target acknowledgement.

This finite boundary accepts a mesh-only resource with unchanged component
headers. It does not remesh CAD, infer nearest nodes, or reuse same-number
members as proof that their physical meaning survived a replacement.
"""
from copy import copy, deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from ..cae_core import PrepError
from ..radioss import DeckResource
from ..radioss.assembly import ELEMENTS, GROUPS, inspect
from ..radioss.modeling import native_identity, member_block


class ModelRelationsResource:
    kind = "native-model-relations"

    def __init__(self, document_id, state=None):
        self.id = str(uuid5(UUID(document_id), "caelab-native-model-relations"))
        self._state = {"state_version": 2, "mesh_revisions": {}, "stale_targets": {}, "replacement_sources": {}, "instances": {}}
        self._token = None
        if state is not None: self.restore(state)

    def snapshot(self):
        # Large explicit memberships are immutable tuples shared by history.
        return {**self._state, "mesh_revisions": dict(self._state["mesh_revisions"]),
                "stale_targets": {key: dict(value) for key,value in self._state["stale_targets"].items()},
                "replacement_sources": {key: dict(value) for key,value in self._state["replacement_sources"].items()},
                "instances": {key: dict(value) for key,value in self._state["instances"].items()}}
    def state_token(self):
        if self._token is None: self._token = sha256(json.dumps(self._state, sort_keys=True).encode()).hexdigest()
        return self._token
    def prepare_state(self, state):
        if isinstance(state, dict) and type(state.get("state_version")) is int and state["state_version"] == 1:
            if set(state) != {"state_version", "mesh_revisions", "stale_targets", "replacement_sources"}:
                raise PrepError("invalid_project", "Invalid legacy model relation state.")
            state = {**state, "state_version": 2, "instances": {}}
        if not isinstance(state, dict) or set(state) != {"state_version", "mesh_revisions", "stale_targets", "replacement_sources", "instances"} or type(state["state_version"]) is not int or state["state_version"] != 2:
            raise PrepError("invalid_project", "Invalid model relation state.")
        if any(not isinstance(state[key], dict) for key in ("mesh_revisions", "stale_targets", "replacement_sources", "instances")):
            raise PrepError("invalid_project", "Invalid relation registries.")
        for rid, revision in state["mesh_revisions"].items():
            UUID(rid)
            if type(revision) is not int or revision < 1: raise PrepError("invalid_project", "Invalid mesh generation.")
        for card_id, item in state["stale_targets"].items():
            UUID(card_id)
            if not isinstance(item, dict) or set(item) != {"resource_id", "mesh_resource_id", "mesh_revision", "family", "members"}:
                raise PrepError("invalid_project", "Invalid stale target record.")
            UUID(item["resource_id"]); UUID(item["mesh_resource_id"])
            if item["family"] not in GROUPS or type(item["mesh_revision"]) is not int or item["mesh_revision"] < 1 or not isinstance(item["members"], (list,tuple)) or any(type(value) is not int or value < 1 for value in item["members"]):
                raise PrepError("invalid_project", "Invalid target generation or membership.")
        for rid, record in state["replacement_sources"].items():
            UUID(rid)
            if not isinstance(record, dict) or set(record) != {"sha256", "name"} or not isinstance(record["name"], str) or not isinstance(record["sha256"], str) or len(record["sha256"]) != 64:
                raise PrepError("invalid_project", "Invalid prepared mesh provenance.")
        for instance_id, record in state["instances"].items():
            UUID(instance_id)
            if not isinstance(record, dict) or set(record) != {"id", "name", "source_id", "root_resource_id", "resource_ids", "status"}:
                raise PrepError("invalid_project", "Invalid instance reference record.")
            if record["id"] != instance_id or record["status"] != "not-expanded" or not isinstance(record["name"], str) or not record["name"].strip() or any(ord(c) < 32 for c in record["name"]):
                raise PrepError("invalid_project", "Invalid instance identity, name or support status.")
            if record["source_id"] is not None: UUID(record["source_id"])
            UUID(record["root_resource_id"])
            if not isinstance(record["resource_ids"], (list, tuple)) or not record["resource_ids"] or len(record["resource_ids"]) != len(set(record["resource_ids"])):
                raise PrepError("invalid_project", "An instance reference must identify distinct source resources.")
            for rid in record["resource_ids"]: UUID(rid)
        return {**state, "mesh_revisions": dict(state["mesh_revisions"]),
                "stale_targets": {key: {**value, "members": tuple(value["members"])} for key,value in state["stale_targets"].items()},
                "replacement_sources": {key: dict(value) for key,value in state["replacement_sources"].items()},
                "instances": {key: {**value, "resource_ids": tuple(value["resource_ids"])} for key,value in state["instances"].items()}}
    def restore(self, state):
        self._state = self.prepare_state(state); self._token = None


class MeshRelationCommands:
    def _relations_resource(self):
        return next(resource for resource in self._require().resources.values() if isinstance(resource, ModelRelationsResource))

    def mesh_relationships(self):
        with self._lock:
            state = self._relations_resource().snapshot()
            state["stale_targets"] = {key: {**value, "members": list(value["members"])} for key,value in state["stale_targets"].items()}
            return {**state, "document_id": self.document.id, "revision": self.document.revision,
                    "conditions": self._stale_conditions(state)}

    def _stale_conditions(self, state=None):
        stale = (state or self._relations_resource().snapshot())["stale_targets"]
        result = []
        for card in self.list_cards():
            if card["keyword"].upper().split("/")[1] not in ("BCS", "CLOAD", "INIVEL", "INTER"): continue
            try: values = self.condition_values(card["id"])
            except PrepError: continue
            targets = [value for key,value in values.items() if key in ("group_id", "secondary_group_id", "main_surface_id") and value in stale]
            if targets: result.append({"card_id": card["id"], "stale_target_ids": targets, "status": "stale"})
        return result

    def plan_mesh_replacement(self, resource_id, path):
        with self._lock: candidate = self._planning_snapshot()
        result = candidate._prepare_mesh_replacement(resource_id, path)
        with self._lock:
            if (self.document.id, self.document.revision, self._document_epoch) != (result["document_id"], result["revision"], result["document_epoch"]):
                raise PrepError("stale_mesh_replacement_plan", "The document changed while preparing the replacement.")
            self._mesh_replacement_plan = candidate._mesh_replacement_plan
        return result

    def _prepare_mesh_replacement(self, resource_id, path):
        with self._lock:
            document = self._require()
            resource = document.resources.get(resource_id)
            if not isinstance(resource, DeckResource) or resource_id == self._root_id:
                raise PrepError("unsupported_mesh_replacement", "Choose an existing mesh-only INCLUDE resource.")
            if self._relations_resource().snapshot()["stale_targets"]:
                raise PrepError("stale_mesh_targets", "Reconnect the previous replacement's targets before replacing another mesh.")
            inspect(self._deck_resources())  # Unknown indirect references cannot be marked safely.
            raw = Path(path).read_bytes(); prepared = DeckResource(raw, is_include=True, name=Path(path).name)
            allowed = {"NODE", *ELEMENTS}
            for deck in (resource, prepared):
                if deck.includes() or not deck.cards or any(card.keyword.upper().split("/")[1] not in allowed for card in deck.cards):
                    raise PrepError("unsupported_mesh_replacement", "Prepared replacement contains only NODE and supported element blocks, without file directives.")
            old = {card.keyword: card for card in resource.cards}; new = {card.keyword: card for card in prepared.cards}
            if len(old) != len(resource.cards) or len(new) != len(prepared.cards) or old.keys() != new.keys():
                raise PrepError("unsupported_mesh_replacement", "Prepared mesh component headers must match exactly; element counts and IDs may change.")
            if prepared.mesh_projection()["diagnostics"]:
                raise PrepError("invalid_mesh", "Prepared coordinates/connectivity could not be read completely.")
            candidate = copy(resource)
            for keyword, card in old.items():
                incoming = new[keyword]
                block = "".join(prepared.lines[incoming.start:incoming.stop])
                candidate.restore(candidate.replaced_state(card.id, block))
            # Validate geometry references across all INCLUDEs before publication.
            trial = copy(self); trial.document = copy(document)
            trial.document.resources = {**document.resources, resource_id: candidate}
            trial._projection_cache = None; trial._projection_index = {}
            view = trial.mesh_view()
            if view["diagnostics"]:
                raise PrepError("invalid_mesh", "Replacement introduces duplicate nodes or unresolved connectivity.", {"diagnostics": [dict(item) for item in view["diagnostics"]]})
            identifiers = [cell["id"] for cell in view["cells"]]
            if any(type(value) is not int or value < 1 for value in (*view["node_ids"], *identifiers)) or len(identifiers) != len(set(identifiers)):
                raise PrepError("invalid_mesh", "Replacement requires positive node IDs and unambiguous global element IDs.")
            old_projection = resource.mesh_projection()
            touched_nodes = set(old_projection["node_ids"])
            touched_elements = {cell["id"] for cell in old_projection["cells"]}
            touched_parts = {cell["part_id"] for cell in self.mesh_view()["cells"]
                             if cell["resource_id"] == resource_id or touched_nodes.intersection(cell["nodes"])}
            relations = self._relations_resource().snapshot()
            generation = relations["mesh_revisions"].get(resource_id, 0) + 1
            relations["mesh_revisions"][resource_id] = generation
            relations["replacement_sources"][resource_id] = {"sha256": sha256(raw).hexdigest(), "name": Path(path).name}
            for deck in self._deck_resources():
                for card in deck.cards:
                    family = "/".join(card.keyword.upper().split("/")[1:3])
                    if family not in GROUPS: continue
                    members = self._integer_members(deck, card)
                    affected = touched_nodes if family == "GRNOD/NODE" else touched_parts if family == "SURF/PART" else touched_elements
                    if affected.intersection(members):
                        relations["stale_targets"][card.id] = {"resource_id": deck.id, "mesh_resource_id": resource_id,
                            "mesh_revision": generation, "family": family, "members": members}
            plan_id = str(uuid4())
            self._mesh_replacement_plan = (plan_id, document.id, document.revision, self._document_epoch, resource_id, candidate.snapshot(), relations)
            return {"plan_id": plan_id, "document_id": document.id, "revision": document.revision,
                    "document_epoch": self._document_epoch, "resource_id": resource_id, "mesh_revision": generation,
                    "stale_targets": deepcopy(relations["stale_targets"]), "node_count": len(view["node_ids"]),
                    "element_count": len(view["cells"]), "source": relations["replacement_sources"][resource_id]}

    def replace_prepared_mesh(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_mesh_replacement_plan", None)
            if plan is None or plan[:4] != (plan_id, self.document.id, self.document.revision, self._document_epoch):
                raise PrepError("stale_mesh_replacement_plan", "Prepare a new replacement against the current document.")
            resource_id, state, relations = plan[4:]
            changed = self.dispatcher.execute_many({resource_id: state, self._relations_resource().id: relations},
                "Replace prepared mesh and mark targets stale", expected_revision=self.document.revision, kind="structure")
            self._mesh_replacement_plan = None
            return {**self.describe(), "mesh_relationships": self.mesh_relationships(), "change": changed.to_dict()}

    def reconnect_mesh_targets(self, targets, *, expected_revision=None, expected_document_id=None):
        """Explicit new member references; same numeric IDs still need this command.

        Map each stale group UUID to {mesh_revision, mapping:{old_id: target}}.
        Targets are typed node/element SelectionRefs; a SURF/PART target is a
        PART card UUID. Every old member must have an explicit correspondence.
        The mesh generation and document revision must match current state.
        The whole requested batch and target-marker removal form one Undo.
        """
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            if not isinstance(targets, dict) or not targets:
                raise PrepError("invalid_reference", "Provide explicit replacement memberships for stale target UUIDs.")
            relations = self._relations_resource().snapshot(); candidates = {}; changed_objects = []
            for card_id, replacement in targets.items():
                if card_id not in relations["stale_targets"]:
                    raise PrepError("invalid_reference", "The target is not marked stale.", {"card_id": card_id})
                resource = self._find_card(card_id); card = resource.card(card_id)
                stale = relations["stale_targets"][card_id]
                if (not isinstance(replacement, dict) or set(replacement) != {"mesh_revision", "mapping"}
                        or type(replacement["mesh_revision"]) is not int or replacement["mesh_revision"] != stale["mesh_revision"]
                        or replacement["mesh_revision"] != relations["mesh_revisions"].get(stale["mesh_resource_id"])
                        or not isinstance(replacement["mapping"], dict)):
                    raise PrepError("stale_reference_mapping", "Use an explicit correspondence for the current mesh generation.")
                mapping = replacement["mapping"]
                if any(type(key) is not int or key < 1 for key in mapping):
                    raise PrepError("invalid_reference", "Correspondence keys must be original positive native IDs.")
                if set(mapping) != set(stale["members"]):
                    raise PrepError("incomplete_reference_mapping", "Map every original member explicitly; missing targets remain stale.")
                members = [mapping[value] for value in stale["members"]]
                family = stale["family"]
                if family == "SURF/PART":
                    identifiers = self._surface_part_ids(members)
                elif family == "GRNOD/NODE":
                    if not isinstance(members, (tuple,list)) or not members: raise PrepError("invalid_reference", "Choose explicit typed node references.")
                    identifiers = []
                    for member in members:
                        if not isinstance(member, dict) or set(member) != {"resource_id","entity_kind","local_id"} or member["entity_kind"] != "node" or type(member["local_id"]) is not int or self.mesh_view()["node_resources"].get(member["local_id"]) != (member["resource_id"],):
                            raise PrepError("invalid_reference", "Reconnection requires current resource-qualified node references.")
                        identifiers.append(member["local_id"])
                    identifiers = self._node_members(identifiers)
                else: identifiers, _, _ = self._element_members(members, family)
                candidate = candidates.setdefault(resource.id, copy(resource))
                # Only member rows are replaced; preserve title, comments and
                # non-target card bytes, including comments inside the group.
                lines = candidate.render().decode("latin1").splitlines(keepends=True)
                current = candidate.card(card_id)
                block = lines[current.start:current.stop]
                data_rows = {index-current.start for index in current.data[1:]}
                rows = member_block(family, native_identity(card.keyword)[1], card.title, identifiers, newline=resource.newline).splitlines(keepends=True)[2:]
                output, inserted = [], False
                for index, line in enumerate(block):
                    if index in data_rows:
                        if not inserted: output.extend(rows); inserted=True
                    else: output.append(line)
                candidate.restore(candidate.replaced_state(card_id, "".join(output)))
                del relations["stale_targets"][card_id]; changed_objects.append(card_id)
            states = {key: value.snapshot() for key,value in candidates.items()}
            states[self._relations_resource().id] = relations
            trial = self._planning_snapshot()
            for rid, state in states.items(): trial.document.resources[rid].restore(state)
            for affected in self._stale_conditions():
                card = trial._find_card(affected["card_id"]).card(affected["card_id"])
                if not card.keyword.upper().startswith(("/CLOAD/", "/INIVEL/TRA/")): continue
                support = trial.condition_support(card.id)
                if support["status"] not in ("supported", "stale"):
                    raise PrepError("unsupported_condition_dof", "The explicit correspondence does not support the condition's mechanical fields.",
                                    {"card_id":card.id,"diagnostics":support["diagnostics"]})
            changed = self.dispatcher.execute_many(states, "Reconnect explicit mesh targets", object_ids=tuple(changed_objects),
                expected_revision=self.document.revision, kind="structure")
            return {**self.describe(), "mesh_relationships": self.mesh_relationships(), "change": changed.to_dict()}
