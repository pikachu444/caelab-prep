"""Native mechanical relationships shared by GUI and automation commands."""
from copy import copy
from ..cae_core import PrepError
from ..radioss.relations import coordinate_frame, frame_block, node_support, validate_components
from ..radioss.modeling import load_direction


class ModelRelationCommands:
    def resolve_part_reference(self, native_id):
        """Resolve the PART namespace including supported native unit suffixes."""
        with self._lock:
            if type(native_id) is not int or native_id < 1:
                raise PrepError("invalid_reference", "Use a positive native PART ID.")
            matches = self._native_matches("PART", native_id)
            if len(matches) != 1:
                raise PrepError("ambiguous_reference" if matches else "dangling_reference", "The PART ID must resolve uniquely.")
            card = matches[0]
            return {"card_id": card["id"], "resource_id": card["resource_id"], "native_id": native_id,
                    "native_scope": card["keyword"], "document_id": self.document.id,
                    "revision": self.document.revision, "document_epoch": self._document_epoch}

    def _validate_dependent_condition_states(self, states):
        """A relationship edit cannot invalidate a previously supported load.

        Existing opaque/unsupported source conditions remain inspectable. BCS
        inactive rotations are permitted native constraints and are not rejected.
        """
        if getattr(self, "_defer_relation_validation", False): return
        candidate = self._planning_snapshot()
        for rid, state in states.items(): candidate.document.resources[rid].restore(state)
        candidate._projection_cache = None
        candidate._projection_index = {}
        for card in self.list_cards():
            words = card["keyword"].upper().split("/")
            if words[1] != "CLOAD" and tuple(words[1:3]) != ("INIVEL","TRA"): continue
            try: before = self.condition_support(card["id"])
            except PrepError: continue
            if before["status"] != "supported": continue
            try: after = candidate.condition_support(card["id"])
            except PrepError as exc:
                raise PrepError("dependent_condition_invalid", "This edit would invalidate a dependent condition.", {"card_id":card["id"],"reason":exc.message}) from exc
            if after["status"] != "supported":
                raise PrepError("dependent_condition_invalid", "This edit would move a dependent condition outside its supported mechanical fields.",
                                {"card_id":card["id"],"diagnostics":after["diagnostics"]})

    def resolve_entity_reference(self, kind, native_id):
        """Resolve an exact current native ID; never nearest-node correspondence."""
        with self._lock:
            if kind not in ("node", "element") or type(native_id) is not int or native_id < 1:
                raise PrepError("invalid_reference", "Use node/element and a positive native ID.")
            projection = self.mesh_view()
            owners = projection["node_resources"].get(native_id, ()) if kind == "node" else tuple(
                cell["resource_id"] for cell in self._projection_index["cells_by_id"].get(native_id, ()))
            if len(owners) != 1:
                raise PrepError("ambiguous_reference" if owners else "dangling_reference", "The current native ID must resolve to exactly one entity.")
            return {"reference": {"resource_id": owners[0], "entity_kind": kind, "local_id": native_id},
                    "document_id": self.document.id, "revision": self.document.revision, "document_epoch": self._document_epoch,
                    "mesh_revision": self._relations_resource().snapshot()["mesh_revisions"].get(owners[0], 0)}

    def coordinate_systems(self):
        with self._lock:
            results = [coordinate_frame(self._deck_resources(), 0)]
            for card in self.list_cards():
                if not card["keyword"].upper().startswith("/SKEW/FIX/"): continue
                try:
                    results.append({**coordinate_frame(self._deck_resources(), int(card["keyword"].split("/")[3])), "name": card["title"]})
                except PrepError as exc:
                    results.append({"card_id": card["id"], "resource_id": card["resource_id"], "name": card["title"],
                                    "diagnostics": [{"code": exc.code, "message": exc.message}]})
            return results

    def _coordinate_reference(self, card_id):
        if card_id is None: return 0
        _, _, identity = self._unique_card(card_id, "SKEW")
        coordinate_frame(self._deck_resources(), identity[1])
        return identity[1]

    def create_coordinate_system(self, name, origin, y_axis, z_axis, *, resource_id=None, native_id=None,
                                 expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("SKEW", native_id)
            return self._insert_model_card(resource, frame_block(identifier, name, origin, y_axis, z_axis, newline=resource.newline),
                                           "Create fixed Cartesian coordinate system", expected_revision)

    def coordinate_system_values(self, card_id):
        with self._lock:
            owner, card, identity = self._unique_card(card_id, "SKEW")
            coordinate_frame(self._deck_resources(), identity[1])
            lines = self.card_text(card_id).splitlines()
            from ..radioss.deck import number
            values = [[number(lines[index-card.start][start:start+20]) for start in (0,20,40)] for index in card.data[1:]]
            return dict(zip(("origin", "y_axis", "z_axis"), values))

    def set_coordinate_system_values(self, card_id, values, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource, card, identity = self._unique_card(card_id, "SKEW")
            current = self.coordinate_system_values(card_id)
            if not isinstance(values, dict) or not values or set(values) - set(current):
                raise PrepError("invalid_command", "Choose origin, y_axis or z_axis.")
            merged = {**current, **values}
            validated = frame_block(identity[1], card.title, **merged).splitlines()
            lines = self.card_text(card_id).splitlines(keepends=True)
            for row, name in enumerate(("origin", "y_axis", "z_axis"), 1):
                if name not in values: continue
                index = card.data[row] - card.start
                body = lines[index].rstrip("\r\n"); ending = lines[index][len(body):]
                lines[index] = validated[row+1] + body[60:] + ending
            state = resource.replaced_state(card_id, "".join(lines))
            self._validate_dependent_condition_states({resource.id:state})
            change = self.dispatcher.execute(resource.id, state, "Edit coordinate system", object_ids=(card_id,),
                expected_revision=expected_revision, kind="structure")
            return self._model_result(resource, card_id, change)

    def dof_support(self, node_ids):
        with self._lock:
            if not isinstance(node_ids, (tuple, list)) or not node_ids or any(type(value) is not int or value < 1 for value in node_ids):
                raise PrepError("invalid_reference", "Choose positive node IDs in the current combined native model.")
            return {"document_id": self.document.id, "revision": self.document.revision,
                    "nodes": node_support(self._deck_resources(), self.mesh_view(), node_ids),
                    "scope": "initial mechanical field applicability; not equation count or coupling verification"}

    def condition_support(self, card_id):
        with self._lock:
            stale = next((item for item in self._stale_conditions() if item["card_id"] == card_id), None)
            if stale: return {"status": "stale", "diagnostics": [{"code": "stale_mesh_target", **stale}]}
            values = self.condition_values(card_id)
            if "group_id" not in values: return {"status": "not-applicable", "diagnostics": []}
            direction = values.get("direction")
            if direction is not None:
                try: load_direction(direction)
                except PrepError as exc:
                    return {"status": "unverified", "diagnostics": [{"code": exc.code, "message": exc.message, "field": "direction"}]}
            translations = values.get("translations", (True,True,True) if "velocity" in values else tuple(direction == v for v in ("X","Y","Z")))
            rotations = values.get("rotations", tuple(direction == v for v in ("XX","YY","ZZ")))
            return self._validate_condition_components(values["group_id"], translations=translations, rotations=rotations,
                coordinate_system_id=values.get("coordinate_system_id"), enforce=False)

    def _validate_condition_components(self, group_id, *, translations=(False,False,False), rotations=(False,False,False), coordinate_system_id=None, enforce=True):
        native_skew_id = self._coordinate_reference(coordinate_system_id)
        resource = self._find_card(group_id)
        node_ids = self._integer_members(resource, resource.card(group_id))
        return validate_components(self._deck_resources(), self.mesh_view(), node_ids,
                                   translations=translations, rotations=rotations, native_skew_id=native_skew_id,
                                   enforce=enforce and not getattr(self,"_defer_relation_validation",False))
