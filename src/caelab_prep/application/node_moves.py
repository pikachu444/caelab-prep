"""Absolute native node moves with verified geometry and one document publish."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4

from ..cae_core import PrepError
from ..radioss.assembly import ELEMENTS, GROUPS, inspect
from ..radioss.deck import number
from ..radioss.modeling import native_identity
from ..radioss.relations import coordinate_frame
from . import mesh_edit_candidates as edits


class NodeMoveCommands:
    def _node_move_stamp(self):
        relations = self._relations_resource().snapshot()
        return edits.SnapshotStamp(self.document.id, self.document.revision, self._document_epoch,
            tuple(edits.ResourceStamp(resource.id, resource.state_token(), relations["mesh_revisions"].get(resource.id, 0))
                  for resource in self.document.resources.values()))

    def _node_move_snapshot(self):
        resources = self._deck_resources()
        relations = self._relations_resource().snapshot()
        if relations["stale_targets"]:
            raise PrepError("stale_mesh_targets", "Review existing mesh targets before another coordinate move.")
        stamp = self._node_move_stamp()
        cached = getattr(self, "_node_move_snapshot_cache", None)
        if cached is not None and cached.stamp == stamp:
            return cached
        definitions, _, _ = inspect(resources)
        units = self._model_resource(None).unit_context()["global"]
        if not units or units.get("length") not in ("mm", "cm", "m"):
            raise PrepError("invalid_units", "Declare the native input length unit before moving nodes.")
        nodes, cells, parts, groups, uses = [], [], [], [], []
        node_refs = {identifier: edits.Ref(rid, "node", identifier)
                     for (namespace, identifier), (rid, _) in definitions.items() if namespace == "NODE"}
        part_refs = {}
        for resource in resources:
            for card in resource.cards:
                identity = native_identity(card.keyword)
                if identity and identity[0] == "PART":
                    part_refs[identity[1]] = edits.Ref(resource.id, "part", card.id)
        families = defaultdict(set)
        element_refs = {}
        for resource in resources:
            lines = resource.render().decode("latin1").splitlines()
            for card in resource.cards:
                words = card.keyword.upper().strip("/").split("/")
                family = words[0]
                if family == "NODE":
                    for row in card.data:
                        identifier = int(lines[row][:10])
                        nodes.append(edits.Node(node_refs[identifier], tuple(number(lines[row][offset:offset+20]) for offset in (10, 30, 50))))
                elif family in ELEMENTS:
                    part = part_refs[int(words[1])]
                    families[part].add(family)
                    for row in card.data:
                        values = [int(lines[row][offset:offset+10].strip() or "0") for offset in range(0, (ELEMENTS[family]+1)*10, 10)]
                        ref = edits.Ref(resource.id, "element", values[0])
                        orientation = node_refs[values[3]] if family == "BEAM" and values[3] else None
                        connectivity = values[1:3] if family == "BEAM" else values[1:]
                        cells.append(edits.Cell(ref, family, tuple(node_refs[value] for value in connectivity), part,
                                                resource.id, orientation))
                        namespace = "E:SOLID" if family in ("TETRA4", "BRICK") else "E:" + family
                        element_refs[(namespace, values[0])] = ref
        for resource in resources:
            for card in resource.cards:
                identity = native_identity(card.keyword)
                if identity and identity[0] == "PART":
                    ref = part_refs[identity[1]]
                    if families[ref]:
                        parts.append(edits.Part(ref, card.id, tuple(sorted(families[ref])), card.keyword))
                pair = "/".join(card.keyword.upper().strip("/").split("/")[:2])
                if pair in GROUPS:
                    namespace = GROUPS[pair]
                    members = self._integer_members(resource, card)
                    kind = "node" if namespace == "NODE" else "part" if namespace == "PART" else "element"
                    refs = tuple(node_refs[value] if kind == "node" else part_refs[value] if kind == "part"
                                 else element_refs[(namespace, value)] for value in members)
                    groups.append(edits.ExplicitSet(edits.Ref(resource.id, "set", card.id), kind, refs, kind == "part"))
        group_refs = {group.ref.local_id: group.ref for group in groups}
        for resource in resources:
            for card in resource.cards:
                family = card.keyword.upper().strip("/").split("/")[0]
                if family not in ("BCS", "CLOAD", "INIVEL", "INTER"):
                    continue
                values = self.condition_values(card.id)
                if values["diagnostics"]:
                    raise PrepError("incomplete_mesh_references", "Every condition reference must resolve before moving nodes.")
                targets = tuple(group_refs[values[key]] for key in ("group_id", "secondary_group_id", "main_surface_id")
                                if key in values)
                kind = {"BCS": "constraint", "CLOAD": "load", "INIVEL": "constraint", "INTER": "contact"}[family]
                uses.append(edits.ReferenceUse(edits.Ref(resource.id, "condition", card.id), kind, targets,
                                               family == "INTER" or values.get("coordinate_system_id") is not None))
        snapshot = edits.MeshSnapshot(stamp, units["length"], tuple(nodes), tuple(cells), tuple(parts), tuple(groups), tuple(uses), True)
        self._node_move_snapshot_cache = snapshot
        return snapshot

    def plan_node_move(self, updates, *, length_unit):
        """Preview absolute positions, preserving source-qualified node identity."""
        with self._lock:
            self._check_model_edit(None, None)
            try:
                snapshot = self._node_move_snapshot()
                if not isinstance(updates, (list, tuple)) or not updates:
                    raise PrepError("invalid_node_move", "Provide node references and absolute coordinates.")
                positions = {}
                for update in updates:
                    if not isinstance(update, dict) or set(update) != {"reference", "position"}:
                        raise PrepError("invalid_node_move", "Each row requires a node reference and absolute position.")
                    ref = edits.Ref(**update["reference"])
                    if ref in positions:
                        raise PrepError("invalid_node_move", "A node may appear only once in a move.")
                    xyz = tuple(update["position"])
                    edits.point(xyz)
                    # Validate the coordinates that will actually fit in native fields.
                    positions[ref] = tuple(float(format(value, ".12g")) for value in xyz)
                candidate = edits.move_nodes(snapshot, positions, length_unit=length_unit)
                states = self._node_move_states(candidate)
                self._validate_dependent_condition_states({rid: state for rid, state in states.items()
                                                           if rid != self._relations_resource().id})
                load_coefficients = self._node_move_load_coefficients(candidate)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            except (KeyError, TypeError, ValueError) as exc:
                raise PrepError("invalid_node_move", "Coordinates or native references could not be verified.", {"reason": str(exc)}) from exc
            plan_id = str(uuid4())
            self._node_move_plan = (plan_id, candidate)
            return {"plan_id": plan_id, "document_id": self.document.id, "revision": self.document.revision,
                    "document_epoch": self._document_epoch, "length_unit": snapshot.length_unit,
                    "nodes": [{"reference": asdict(node.ref), "before": list(snapshot._nodes[node.ref].xyz), "after": list(node.xyz)}
                              for node in candidate.node_updates],
                    "quality_before": [asdict(item) for item in candidate.quality_before],
                    "quality_after": [asdict(item) for item in candidate.quality_after],
                    "impacts": [asdict(item) for item in candidate.impacts],
                    "load_coefficients": load_coefficients,
                    "stale_targets": deepcopy(states[self._relations_resource().id]["stale_targets"])}

    def _node_move_load_coefficients(self, candidate):
        affected = {impact.target for impact in candidate.impacts}
        result = []
        for use in candidate.base.uses:
            if use.kind != "load" or use.ref not in affected:
                continue
            values = self.condition_values(use.ref.local_id)
            frame = coordinate_frame(self._deck_resources(), self._coordinate_reference(values["coordinate_system_id"]))
            direction = values["direction"]
            axis = frame["axes"]["XYZ".index(direction[0])]
            targets = set().union(*(edits._members_as_nodes(candidate.base, candidate.base._sets[ref])
                                    for ref in use.targets))
            curve_id = values["curve_id"]
            # FUNCT and its native time scaling are not evaluated by a geometry preview.
            result.append({"condition_id": use.ref.local_id,
                "quantity": "moment" if len(direction) == 2 else "force",
                "curve_ref": {"resource_id": self._find_card(curve_id).id, "card_id": curve_id},
                "frame_ref": ({"resource_id": frame["resource_id"], "card_id": frame["card_id"]}
                              if frame["card_id"] is not None else None),
                "native_direction": direction, "global_unit_axis": list(axis), "scale": values["scale"],
                "target_count": len(targets),
                "summed_multiplier": [len(targets) * values["scale"] * component for component in axis],
                "value_basis": "unevaluated_native_curve_multiplier", "time_scaling": "native_not_evaluated",
                "application_point_moments": "not_evaluated"})
        return result

    def _node_move_group_dependencies(self, candidate, group, generations):
        owners = {member.resource_id for member in group.members}
        if group.member_kind != "node":
            cells = ([candidate.base._cells[ref] for ref in group.members] if group.member_kind == "element"
                     else [cell for cell in candidate.base.cells if cell.part in group.members])
            for cell in cells:
                owners.add(cell.ref.resource_id)
                owners.update(node.resource_id for node in cell.nodes)
                if cell.orientation_node is not None:
                    owners.add(cell.orientation_node.resource_id)
        return {rid: generations[rid] for rid in sorted(owners & generations.keys())}

    def _node_move_states(self, candidate):
        grouped = defaultdict(dict)
        for node in candidate.node_updates:
            grouped[node.ref.resource_id][str(node.ref.local_id)] = node.xyz
        states = {rid: self.document.resources[rid].node_positions_state(positions) for rid, positions in grouped.items()}
        relations = self._relations_resource().snapshot()
        generations = {rid: relations["mesh_revisions"].get(rid, 0) + 1 for rid in candidate.mesh_revision_resources}
        relations["mesh_revisions"].update(generations)
        for impact in candidate.impacts:
            if impact.target.entity_kind != "set":
                continue
            resource = self.document.resources[impact.target.resource_id]
            card = resource.card(impact.target.local_id)
            family = "/".join(card.keyword.upper().strip("/").split("/")[:2])
            dependencies = self._node_move_group_dependencies(candidate, candidate.base._sets[impact.target], generations)
            primary = next(iter(dependencies))
            relations["stale_targets"][card.id] = {"resource_id": resource.id, "mesh_resource_id": primary,
                "mesh_revision": generations[primary], "family": family, "members": self._integer_members(resource, card),
                "reason": "geometry_review_required", "mesh_dependencies": dependencies}
        states[self._relations_resource().id] = relations
        return states

    def apply_node_move(self, plan_id, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            plan = getattr(self, "_node_move_plan", None)
            if plan is None or plan[0] != plan_id:
                raise PrepError("stale_mesh_candidate", "Prepare a fresh coordinate preview.")
            _, candidate = plan
            try:
                candidate.assert_current(self._node_move_stamp(), candidate.base.digest)
            except edits.MeshEditError as exc:
                raise PrepError(exc.code, str(exc)) from exc
            states = self._node_move_states(candidate)
            self._validate_dependent_condition_states({rid: state for rid, state in states.items()
                                                       if rid != self._relations_resource().id})
            change = self.dispatcher.execute_many(states, "Move nodes to absolute coordinates",
                expected_revision=self.document.revision, kind="structure")
            self._node_move_plan = None
            return {**self.describe(), "change": change.to_dict(), "mesh_relationships": self.mesh_relationships()}

    def cancel_node_move(self, plan_id):
        with self._lock:
            plan = getattr(self, "_node_move_plan", None)
            if plan is not None and plan[0] == plan_id:
                self._node_move_plan = None
