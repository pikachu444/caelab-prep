"""One document owner and command path for the desktop UI and automation."""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
import os
from pathlib import Path, PurePosixPath
import tempfile
from threading import RLock
from uuid import UUID, uuid4
from dataclasses import asdict
from hashlib import sha256
import zipfile
from functools import wraps

from ..cae_core import CommandDispatcher, Document, PrepError, Selection, SelectionRef
from ..radioss import DeckResource
from ..radioss.deck import number
from ..radioss.modeling import (native_identity, integer, material_block, shell_block, copy_block,
    curve_points, curve_block, member_block, boundary_block, load_block, velocity_block, contact_block, title, real, solid_block, engine_input, condition_scalar_default, reject_default_zero)
from .storage import write_container
from .contracts import ObjectRef
from .analysis_cases import AnalysisCasesResource, AnalysisCaseCommands, condition_kind
from .projection import readonly, mutable as mutable_projection, freeze_mesh_payload
from .source_models import SourceArchiveResource, SourceModelCommands
from .model_relations import ModelRelationCommands
from .mesh_relations import ModelRelationsResource, MeshRelationCommands
from .node_moves import NodeMoveCommands
from .group_members import GroupMemberCommands
from .node_merges import NodeMergeCommands
from .shell_normals import ShellNormalCommands
from .element_deletion import ElementDeletionCommands
from .part_reassignment import PartReassignmentCommands


PROJECT_FORMAT = "caelab-prep-project"
PROJECT_VERSION = 6


def _file_boundary(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except PrepError:
            raise
        except OSError as exc:
            raise PrepError("file_io_error", "파일 작업을 완료하지 못했습니다.", {"reason": str(exc)}) from exc
    return wrapped


class PrepSession(AnalysisCaseCommands, SourceModelCommands, ModelRelationCommands, MeshRelationCommands, NodeMoveCommands, GroupMemberCommands, NodeMergeCommands, ShellNormalCommands, ElementDeletionCommands, PartReassignmentCommands):
    def __init__(self):
        self._lock = RLock()
        self.document: Document | None = None
        self.dispatcher: CommandDispatcher | None = None
        self._root_id: str | None = None
        self._paths: dict[str, str] = {}
        self._source_paths: set[str] = set()
        self._diagnostics: list[dict] = []
        self._projection_cache: dict | None = None
        self._projection_index = {}
        self._source_path: str | None = None
        self._listeners = []
        self._active_object: ObjectRef | None = None
        self._selected_objects: tuple[ObjectRef, ...] = ()
        self._active_target_role = None
        self._document_epoch = str(uuid4())
        self._projection_revision = 0

    def subscribe(self, listener):
        """Observe committed session events on the calling thread; return unsubscribe.

        Events are dictionaries containing kind/document_id/revision. A GUI must
        queue delivery to its own thread. Observer errors never undo model work.
        """
        with self._lock:
            self._listeners.append(listener)
        def unsubscribe():
            with self._lock:
                if listener in self._listeners: self._listeners.remove(listener)
        return unsubscribe

    def _notify(self, kind: str, **details) -> None:
        event = {"kind": kind, "document_id": self.document.id if self.document else None,
                 "revision": self.document.revision if self.document else 0,
                 "document_epoch": self._document_epoch, **details}
        for listener in tuple(self._listeners):
            try:
                listener(dict(event))
            except Exception:
                continue

    def _require(self) -> Document:
        if self.document is None:
            raise PrepError("no_document", "먼저 Radioss 덱이나 작업 문서를 열어 주세요.")
        return self.document

    def _deck_resources(self, document=None):
        return [r for r in (document or self._require()).resources.values() if isinstance(r, DeckResource)]

    @staticmethod
    def _include_relative(value: str) -> PurePosixPath:
        if not isinstance(value, str):
            raise PrepError("invalid_project", "INCLUDE 경로는 문자열이어야 합니다.")
        portable = value.replace("\\", "/")
        path = PurePosixPath(portable)
        if not value or path.is_absolute() or ":" in portable or ".." in path.parts:
            raise PrepError("include_path_unsupported", "이 INCLUDE 경로는 독립 문서로 묶을 수 없습니다.", {"path": value})
        return path

    def _install(self, document: Document, root_id: str, paths: dict[str, str],
                 source_paths: set[str], diagnostics: list[dict], source_path: str | None = None) -> None:
        if self.document is not None and self.document.id == document.id:
            document.revision = max(self.document.revision + 1, document.revision)
        if not any(isinstance(r, AnalysisCasesResource) for r in document.resources.values()):
            cases = AnalysisCasesResource(document.id)
            document.resources[cases.id] = cases
            document.mark_saved(document.save_state.path)
        if not any(isinstance(r, ModelRelationsResource) for r in document.resources.values()):
            relations = ModelRelationsResource(document.id)
            document.resources[relations.id] = relations
            document.mark_saved(document.save_state.path)
        self.document = document
        self.dispatcher = CommandDispatcher(document)
        self.dispatcher.subscribe(self._command_changed)
        self._root_id = root_id
        self._paths = paths
        self._source_paths = source_paths
        self._diagnostics = diagnostics
        self._projection_cache = None
        self._projection_index = {}
        self._source_path = source_path
        self._active_object = None
        self._selected_objects = ()
        self._active_target_role = None
        self._document_epoch = str(uuid4())
        self._projection_revision += 1
        self._import_plan = None
        self._mesh_replacement_plan = None
        self._cad_mesh_replacement_plan = None

    @staticmethod
    def _path_collisions(paths: dict[str, str]) -> list[list[str]]:
        grouped: dict[str, list[str]] = {}
        for path in paths.values(): grouped.setdefault(path.casefold(), []).append(path)
        return [group for group in grouped.values() if len(group) > 1]

    def new_document(self, name, units):
        """Create an empty native document with explicitly declared input/output units."""
        with self._lock:
            native_title = title(name)
            if not isinstance(units, dict) or set(units) != {"mass", "length", "time"}:
                raise PrepError("invalid_units", "Declare mass, length and time units explicitly.")
            supported = {"mass": ("Mg", "kg", "g"), "length": ("mm", "cm", "m"), "time": ("s", "ms")}
            if any(units[key] not in choices for key, choices in supported.items()):
                raise PrepError("invalid_units", "Supported units are Mg/kg/g, mm/cm/m and s/ms.")
            unit_row = "".join(f"{units[key]:>20}" for key in ("mass", "length", "time"))
            raw = ("#RADIOSS STARTER\n/BEGIN\n" + native_title + "\n" + f"{2024:10d}{0:10d}" + "\n" + unit_row + "\n" + unit_row + "\n/END\n").encode("latin1")
            resource = DeckResource(raw, name="model_0000.rad")
            document = Document(name)
            document.resources[resource.id] = resource
            document.mark_saved()
            self._install(document, resource.id, {resource.id: resource.name}, set(), [])
            self._notify("document")
            return self.describe()

    @_file_boundary
    def open_rad(self, path: str) -> dict:
        with self._lock:
            source = Path(path).expanduser().resolve()
            if not source.is_file():
                raise PrepError("file_not_found", "입력 파일을 찾을 수 없습니다.", {"path": str(source)})
            base = source.parent
            document = Document(source.name)
            paths: dict[str, str] = {}
            seen: dict[Path, str] = {}
            diagnostics: list[dict] = []

            def visit(filename: Path, chain: tuple[Path, ...]) -> str:
                if filename in seen:
                    return seen[filename]
                try:
                    resource = DeckResource(filename.read_bytes(), name=filename.relative_to(base).as_posix(),
                                            is_include=filename != source)
                except OSError as exc:
                    raise PrepError("file_read_error", "파일을 읽지 못했습니다.", {"path": str(filename), "reason": str(exc)}) from exc
                seen[filename] = resource.id
                paths[resource.id] = filename.relative_to(base).as_posix()
                document.resources[resource.id] = resource
                for reference in resource.includes():
                    details = {"resource_id": resource.id, **reference}
                    try:
                        relative = self._include_relative(reference["path"])
                        target = (base / relative).resolve()
                        target.relative_to(base)
                        if target in chain + (filename,):
                            raise PrepError("include_cycle", "순환 INCLUDE를 발견했습니다.", {"path": str(target)})
                        if not target.is_file():
                            raise PrepError("include_missing", "INCLUDE 파일이 없습니다.", {"path": str(target)})
                        visit(target, chain + (filename,))
                    except (PrepError, ValueError, OSError) as exc:
                        diagnostics.append({"severity": "warning", "code": getattr(exc, "code", "include_read_error"),
                            "message": str(exc), "unresolved_include": True, **details})
                return resource.id

            root = visit(source, ())
            collisions = self._path_collisions(paths)
            if collisions:
                diagnostics.append({"severity": "warning", "code": "project_path_collision",
                    "message": "대소문자만 다른 경로는 이식 가능한 작업 문서에 함께 저장할 수 없습니다.", "paths": collisions})
            document.mark_saved()
            self._install(document, root, paths, {str(p) for p in seen}, diagnostics, str(source))
            result = self.describe()
            self._notify("document")
            return result

    def describe(self) -> dict:
        with self._lock:
            document = self.document
            if document is None:
                return {"document_id": None, "revision": 0, "dirty": False, "name": "새 작업",
                        "can_undo": False, "can_redo": False, "node_count": 0, "element_count": 0,
                        "capabilities": self.capabilities(), "diagnostics": [], "source_path": None,
                        "project_path": None, "last_change": None, "active_object": None, "selected_objects": [], "active_case_id": None,
                        "document_epoch": self._document_epoch, "projection_revision": self._projection_revision}
            if self._projection_cache is None:
                self.mesh_view()
            projection = self._projection_cache
            assert self.dispatcher is not None
            return {"document_id": document.id, "revision": document.revision, "dirty": document.dirty,
                    "name": document.name, "can_undo": self.dispatcher.can_undo,
                    "can_redo": self.dispatcher.can_redo, "node_count": len(projection["node_ids"]),
                    "element_count": len(projection["cells"]), "capabilities": self.capabilities(),
                    "diagnostics": self.diagnostics(), "project_path": document.save_state.path,
                    "source_path": self._source_path,
                    "active_case_id": self._cases_resource().snapshot()["active_case_id"],
                    "last_change": self.dispatcher.last_change.to_dict() if self.dispatcher.last_change else None,
                    "active_object": asdict(self._active_object) if self._active_object else None,
                    "active_target_role": self._active_target_role,
                    "selected_objects": [asdict(ref) for ref in self._selected_objects],
                    "document_epoch": self._document_epoch, "projection_revision": self._projection_revision}

    @staticmethod
    def capabilities() -> dict:
        return {"save": True, "undo": True, "radioss_raw_preservation": True, "project_format": PROJECT_FORMAT,
                "project_version": PROJECT_VERSION, "analysis_cases": ["BCS", "CLOAD", "INIVEL/TRA", "INTER/TYPE7"], "material_edit": ["LAW1/ELAST", "LAW36/PLAS_TAB"],
                "constraint_edit": ["BCS"], "contact_edit": ["INTER/TYPE7 targets and friction", "INTER/TYPE24 friction"],
                "curve_edit": ["FUNCT point values and row count"], "initial_velocity_edit": ["INIVEL/TRA"],
                "shell_edit": ["PROP/SHELL thickness"],
                "create_cards": ["MAT/LAW1", "PROP/SHELL", "PROP/SOLID", "SKEW/FIX", "FUNCT", "GRNOD/NODE", "GRSH3N/SH3N", "GRSHEL/SHEL", "GRBRIC/BRIC", "GRBEAM/BEAM", "GRTRUS/TRUS", "SURF/PART", "BCS", "CLOAD", "INIVEL/TRA", "INTER/TYPE7"],
                "copy_delete_cards": ["MAT/LAW1", "MAT/LAW36", "PROP/SHELL", "PROP/SOLID", "FUNCT", "GRNOD/NODE", "GRSH3N/SH3N", "GRSHEL/SHEL", "GRBRIC/BRIC", "GRBEAM/BEAM", "GRTRUS/TRUS", "SURF/PART", "BCS", "CLOAD", "INIVEL/TRA", "INTER/TYPE7"],
                "part_assignment": True, "new_document": True, "mesh_adoption": ["triangle3", "tetra4", "tetra10"],
                "mesh_adoption_sources": {"cad_gmsh": ["triangle3", "tetra4"],
                    "standalone_msh": ["triangle3", "tetra4", "tetra10"], "structured_recipe": ["quad4", "hex8"]},
                "mesh_replacement": "adoption-owned parts without dependent groups/surfaces or unknown references", "solver_input_export": True,
                "source_import": "explicit native ID mapping and source archive within the closed initial profile",
                "prepared_mesh_replacement": "mesh-only INCLUDE with unchanged component headers; explicit stale-target reconnection",
                "instance_references": "metadata only; not-expanded references block native export",
                "multi_resource_commands": True,
                "cad_import": False, "meshing": False, "solver_execution": False,
                "projection_only": True, "include_base": "root-deck-working-directory",
                "unsupported_cards": "read-only, original bytes preserved"}

    def diagnostics(self) -> list[dict]:
        with self._lock:
            document = self._require()
            result = list(self._diagnostics)
            for resource in self._deck_resources(document): result.extend(resource.diagnostics)
            if self._projection_cache is None: self.mesh_view()
            result.extend(self._projection_cache.get("diagnostics", []))
            # Diagnostics can contain export guards; never expose their internal objects.
            return mutable_projection(result)

    def list_cards(self) -> list[dict]:
        with self._lock:
            document = self._require()
            return [card for resource in self._deck_resources(document) for card in resource.list_cards()]

    def _find_card(self, card_id: str) -> DeckResource:
        if not isinstance(card_id, str):
            raise PrepError("invalid_reference", "A card UUID is required.")
        for resource in self._deck_resources():
            if card_id in resource._by_id:
                return resource
        raise PrepError("card_not_found", "카드를 찾을 수 없습니다.", {"card_id": card_id})

    def card_fields(self, card_id: str) -> list[dict]:
        with self._lock:
            return self._find_card(card_id).card_fields(card_id)

    def card_text(self, card_id: str) -> str:
        with self._lock:
            resource = self._find_card(card_id)
            card = resource.card(card_id)
            return "".join(resource.render().decode("latin1").splitlines(keepends=True)[card.start:card.stop])

    def set_field(self, card_id: str, field_name: str, value: object,
                  expected_revision: int | None = None) -> dict:
        return self.set_fields(card_id, {field_name: value}, expected_revision=expected_revision)

    def set_fields(self, card_id: str, values: dict[str, object],
                   expected_revision: int | None = None, *,
                   expected_document_id: str | None = None,
                   expected_resource_id: str | None = None) -> dict:
        """Validate all fields first, then commit one vector/table/property edit."""
        with self._lock:
            document = self._require()
            if expected_document_id is not None and expected_document_id != document.id:
                raise PrepError("document_conflict", "The target document has been replaced.")
            if expected_revision is not None and (type(expected_revision) is not int or expected_revision != self._require().revision):
                raise PrepError("revision_conflict", "모델이 변경됐습니다. 현재 값을 다시 읽어 주세요.",
                                {"expected": expected_revision, "actual": self._require().revision})
            resource = self._find_card(card_id)
            if expected_resource_id is not None and expected_resource_id != resource.id:
                raise PrepError("invalid_reference", "The target resource does not match.")
            if not isinstance(values, dict) or not values:
                raise PrepError("invalid_command", "A nonempty field mapping is required.")
            if native_identity(resource.card(card_id).keyword) and resource.card(card_id).keyword.upper().startswith("/PART/"):
                raise PrepError("reference_command_required", "Use assign_part with material/property card identities.")
            state = resource.fields_state(card_id, values)
            if resource.card(card_id).keyword.upper().startswith("/PROP/"):
                self._validate_dependent_condition_states({resource.id:state})
            assert self.dispatcher is not None
            self.dispatcher.execute(resource.id, state, f"{resource.card(card_id).keyword}: {', '.join(values)}",
                                    object_ids=(card_id,), expected_revision=expected_revision)
            return self.describe()

    def _command_changed(self, change):
        if change.kind == "structure":
            self._sync_source_paths()
            self._projection_cache = None
            self._projection_index = {}
            self._projection_revision += 1
            if self._active_object is not None:
                resource = self.document.resources.get(self._active_object.resource_id)
                if resource is None or self._active_object.object_id not in getattr(resource, "_by_id", {}):
                    self._active_object = None
                    self.document.selection = Selection()
            self._selected_objects = tuple(ref for ref in self._selected_objects
                if ref.resource_id in self.document.resources and ref.object_id in getattr(self.document.resources[ref.resource_id], "_by_id", {}))
            if self._active_object is not None and self._active_target_role is not None:
                self.document.selection, self._active_target_role = self._condition_selection(
                    self._active_object.object_id, self._active_target_role)
        self._notify(change.kind, change=change.to_dict())

    def _check_model_edit(self, expected_revision, expected_document_id):
        document = self._require()
        if expected_document_id is not None and expected_document_id != document.id:
            raise PrepError("document_conflict", "The target document has been replaced.")
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision != document.revision):
            raise PrepError("revision_conflict", "The model changed. Reload before editing.",
                            {"expected": expected_revision, "actual": document.revision})
        if any(item.get("unresolved_include") for item in self._diagnostics):
            raise PrepError("unresolved_include", "Resolve INCLUDE files before changing native identities or references.")
        if any(card["keyword"].upper().startswith(("/SUBMODEL", "/SUBDOMAIN")) for card in self.list_cards()):
            raise PrepError("unsupported_submodel", "Native identity and reference changes are unavailable for SUBMODEL/SUBDOMAIN decks because their offset scopes are not implemented.")
        return document

    def _native_matches(self, namespace, identifier):
        return [card for card in self.list_cards() if native_identity(card["keyword"]) == (namespace, identifier)]

    def _allocate_native_id(self, namespace, requested=None):
        used = {identity[1] for card in self.list_cards()
                if (identity := native_identity(card["keyword"])) and identity[0] == namespace}
        if requested is None:
            requested = 1
            while requested in used: requested += 1
        integer(requested)
        if requested in used:
            raise PrepError("native_id_collision", "That native ID already exists in this document.",
                            {"namespace": namespace, "native_id": requested})
        return requested

    def _model_resource(self, resource_id):
        identity = resource_id if resource_id is not None else self._root_id
        if not isinstance(identity, str):
            raise PrepError("invalid_reference", "A resource UUID is required.")
        resource = self._require().resources.get(identity)
        if not isinstance(resource, DeckResource):
            raise PrepError("invalid_reference", "The target deck resource does not exist.")
        return resource

    def _unique_card(self, card_id, namespace=None):
        resource = self._find_card(card_id)
        card = resource.card(card_id)
        identity = native_identity(card.keyword)
        if identity is None or (namespace is not None and identity[0] != namespace):
            raise PrepError("invalid_reference", "The card is not in the required native namespace.")
        if len(self._native_matches(*identity)) != 1:
            raise PrepError("ambiguous_reference", "The native ID is repeated across resources.",
                            {"namespace": identity[0], "native_id": identity[1]})
        return resource, card, identity

    def _model_result(self, resource, card_id, change, **details):
        return {**self.describe(), "card_id": card_id, "resource_id": resource.id,
                "change": change.to_dict() if change else None, **details}

    def _insert_model_card(self, resource, text, label, expected_revision):
        state, card_id = resource.inserted_state(text)
        change = self.dispatcher.execute(resource.id, state, label, object_ids=(card_id,),
                                         expected_revision=expected_revision, kind="structure")
        return self._model_result(resource, card_id, change)

    def create_material(self, name, density, young_modulus, poisson_ratio, *, resource_id=None,
                        native_id=None, expected_revision=None, expected_document_id=None):
        """Create one linear isotropic LAW1 in the input deck's unit system."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("MAT", native_id)
            text = material_block(identifier, name, density, young_modulus, poisson_ratio, newline=resource.newline)
            return self._insert_model_card(resource, text, "Create material", expected_revision)

    def create_shell_property(self, name, thickness, *, resource_id=None, native_id=None,
                              expected_revision=None, expected_document_id=None):
        """Create the explicitly specified QEPH elastic-shell property profile."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("PROP", native_id)
            text = shell_block(identifier, name, thickness, newline=resource.newline)
            return self._insert_model_card(resource, text, "Create shell property", expected_revision)

    def create_solid_property(self, name, *, resource_id=None, native_id=None,
                              expected_revision=None, expected_document_id=None, element_family="tetra4"):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("PROP", native_id)
            return self._insert_model_card(resource, solid_block(identifier, name, newline=resource.newline,
                                           element_family=element_family),
                                           f"Create {element_family} property", expected_revision)

    def _mesh_replacement_state(self, part_ids, *, allow_stale=False):
        """Remove only proven adoption-owned geometry; protect external node use."""
        from ..radioss.assembly import REFERENCE_FREE_PAIRS, element_node_references, element_part_reference, inspect
        self._member_sequence(part_ids)
        resource = self._model_resource(None)
        selected, batches, blockers, unknown = {}, set(), [], []
        for part_id in part_ids:
            owner, card, identity = self._unique_card(part_id, "PART")
            marker = re.search(r"^# CAELab adopted mesh ([0-9a-f-]+); part ([0-9a-f-]+)$", self.card_text(part_id), re.M)
            if owner.id != resource.id or marker is None:
                raise PrepError("mesh_replacement_unsupported", "Only parts created by mesh adoption in the root resource have proven geometry ownership.", {"card_id": part_id})
            selected[identity[1]] = card
            batches.add(marker.group(1))
            dependents, unverified = self._dependency_inventory(part_id)
            blockers.extend(dependents)
            unknown.extend(unverified)
        if allow_stale:
            if self._relations_resource().snapshot()["stale_targets"]:
                raise PrepError("stale_mesh_targets", "Reconnect the previous replacement's targets before replacing another mesh.")
            inspect(self._deck_resources())
            unknown = [item for item in unknown if "/".join(item["keyword"].upper().split("/")[1:3]) not in REFERENCE_FREE_PAIRS]
        cells = [cell for item in self._deck_resources() for cell in item.mesh_projection()["cells"]]
        selected_nodes = {node for cell in cells if cell.get("part_id") in selected for node in cell["nodes"]}
        used_elsewhere = {node for cell in cells if cell.get("part_id") not in selected for node in cell["nodes"]}
        for owner in self._deck_resources():
            lines = owner.render().decode("latin1").splitlines()
            for card in owner.cards:
                words = card.keyword.upper().split("/")
                if len(words) > 1 and words[1] == "BEAM" and element_part_reference(card.keyword) not in selected:
                    for row in card.data:
                        used_elsewhere.update(value for _, value in element_node_references("BEAM", lines[row]))
        shared_nodes = selected_nodes & used_elsewhere
        potentially_removed = set(selected_nodes)
        for card in resource.cards:
            if card.keyword.upper().split("/")[1] != "NODE": continue
            marker = re.search(r"^# CAELab mesh ([0-9a-f-]+); geometry ", self.card_text(card.id), re.M)
            if marker is None or marker.group(1) not in batches: continue
            remaining = [item for item in resource.cards if item.id not in part_ids and item.keyword.upper().startswith("/PART/")
                and f"# CAELab adopted mesh {marker.group(1)}; part " in self.card_text(item.id)]
            if not remaining:
                for index in card.data:
                    try: potentially_removed.add(int(resource.lines[index][:10]))
                    except ValueError:
                        raise PrepError("mesh_inventory_incomplete", "An owned node ID cannot be parsed.") from None
        for item in self.list_cards():
            if item["keyword"].upper().startswith("/GRNOD/NODE/"):
                owner = self._find_card(item["id"])
                try: nodes = self._integer_members(owner, owner.card(item["id"]))
                except PrepError:
                    unknown.append(item)
                    continue
                if potentially_removed.intersection(nodes): blockers.append(item)
            elif tuple(item["keyword"].upper().split("/")[1:3]) in (("GRSH3N", "SH3N"), ("GRSHEL", "SHEL"), ("GRBRIC", "BRIC"), ("GRBEAM", "BEAM"), ("GRTRUS", "TRUS")):
                owner = self._find_card(item["id"])
                try: identifiers = self._integer_members(owner, owner.card(item["id"]))
                except PrepError:
                    unknown.append(item)
                    continue
                selected_elements = {cell["id"] for cell in cells if cell.get("part_id") in selected}
                if selected_elements.intersection(identifiers): blockers.append(item)
        targets = None
        if allow_stale:
            elements = {cell["id"] for cell in cells if cell.get("part_id") in selected}
            parts = set(selected) | {cell["part_id"] for cell in cells
                                    if cell.get("part_id") is not None and potentially_removed.intersection(cell["nodes"])}
            targets = self._mesh_replacement_targets(potentially_removed, elements, parts)
            blockers = [item for item in blockers if item["id"] not in targets]
        if blockers or unknown:
            raise PrepError("mesh_replacement_in_use", "Replacement is blocked by existing groups/surfaces/conditions or unverified references.",
                            {"dependents": list({item["id"]: item for item in blockers}.values()),
                             "unverified": list({item["id"]: item for item in unknown}.values())})
        state = resource.snapshot()
        removed_cards, removed_nodes = [], set()
        def remove(card):
            if any(item["id"] == card.id for item in state["created"]):
                state["created"] = [item for item in state["created"] if item["id"] != card.id]
            else: state["deleted"].append(card.id)
            state["patches"].pop(card.id, None)
            state["replaced"].pop(card.id, None)
            removed_cards.append(card.id)
        for card in selected.values(): remove(card)
        element_roots = {"SHELL", "SH3N", "BRICK", "TETRA4", "TETRA", "TETRA10", "BEAM", "TRUSS"}
        for owner in self._deck_resources():
            for card in owner.cards:
                words = card.keyword.upper().split("/")
                if words[1] in element_roots and element_part_reference(card.keyword) in selected:
                    if not words[2].isdigit():
                        raise PrepError("mesh_replacement_unsupported", "Normalize the selected element PART header before replacement; its geometry projection is incomplete.", {"card_id": card.id})
                    marker = re.search(r"^# CAELab adopted mesh ([0-9a-f-]+); part ([0-9a-f-]+)$", self.card_text(card.id), re.M)
                    if owner.id != resource.id or marker is None or marker.group(1) not in batches:
                        raise PrepError("mesh_replacement_unsupported", "An element block has no proven ownership by the selected adopted mesh.", {"card_id": card.id})
                    remove(card)
        for card in resource.cards:
            if card.keyword.upper().split("/")[1] != "NODE": continue
            text = self.card_text(card.id)
            marker = re.search(r"^# CAELab mesh ([0-9a-f-]+); geometry ", text, re.M)
            if marker is None or marker.group(1) not in batches: continue
            other_batch_parts = [item for item in resource.cards if item.id not in removed_cards and item.keyword.upper().startswith("/PART/")
                and f"# CAELab adopted mesh {marker.group(1)}; part " in self.card_text(item.id)]
            lines = text.splitlines(keepends=True)
            remove_rows = set()
            for index in card.data:
                try: node = int(resource.lines[index][:10])
                except ValueError:
                    raise PrepError("mesh_inventory_incomplete", "An owned node row has an invalid ID.", {"card_id": card.id}) from None
                if node not in used_elsewhere and (node in selected_nodes or not other_batch_parts):
                    remove_rows.add(index - card.start)
                    removed_nodes.add(node)
            if len(remove_rows) == len(card.data): remove(card)
            elif remove_rows:
                replacement = "".join(line for index, line in enumerate(lines) if index not in remove_rows)
                resource._validate_replacement(card.keyword, replacement)
                created = next((item for item in state["created"] if item["id"] == card.id), None)
                if created is not None: created["text"] = replacement
                else: state["replaced"][card.id] = replacement
                state["patches"].pop(card.id, None)
        state["node_positions"] = {key: value for key, value in state["node_positions"].items()
                                   if int(key) not in removed_nodes}
        details = {"replaced_part_ids": list(part_ids), "removed_card_ids": removed_cards,
                   "removed_node_ids": sorted(removed_nodes), "preserved_shared_node_ids": sorted(shared_nodes)}
        if targets is not None: details["_replacement_targets"] = targets
        return state, details

    def adopt_mesh_candidate(self, native_mesh, *, material_id, property_id, name=None,
                             replace_part_ids=None, expected_revision=None, expected_document_id=None,
                             source_declaration=None, expected_document_epoch=None):
        """Adopt a verified candidate into one atomic native resource command."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            if expected_document_epoch is not None and expected_document_epoch != self._document_epoch:
                raise PrepError("document_epoch_conflict", "The target document was reopened; inspect a current mesh candidate.")
            prepared = self._prepare_mesh_adoption(native_mesh, material_id=material_id, property_id=property_id,
                name=name, replace_part_ids=replace_part_ids, source_declaration=source_declaration)
            return self._publish_mesh_adoption(prepared, expected_revision=expected_revision)

    def _prepare_mesh_adoption(self, native_mesh, *, material_id, property_id, name=None,
                               replace_part_ids=None, source_declaration=None, allow_stale=False):
        """Validate and build private states; publication remains a separate command."""
        from .mesh_candidates import validate_native_mesh, triangle_quality, tetrahedron_quality
        with self._lock:
            self._check_model_edit(None, None)
            if any(card["keyword"].upper().startswith("/TRANSFORM") for card in self.list_cards()):
                raise PrepError("unsupported_mesh_transform", "Mesh adoption does not reinterpret existing native transformation scopes.")
            replacement_state, replacement_details = (self._mesh_replacement_state(replace_part_ids, allow_stale=allow_stale)
                if replace_part_ids is not None else (None, {}))
            replacement_targets = replacement_details.pop("_replacement_targets", None)
            native_mesh = validate_native_mesh(native_mesh)
            declaration_text = None
            if source_declaration is not None:
                keys = {"format", "verification", "declared_producer", "declared_version", "design_sha256",
                        "executable_sha256", "step_sha256", "expected_step_length_unit"}
                if (not isinstance(source_declaration, dict) or set(source_declaration) != keys
                        or any(not isinstance(value, str) for value in source_declaration.values())
                        or source_declaration["format"] != "caelab-cad-source-declaration/1"
                        or source_declaration["verification"] != "unverified"
                        or source_declaration["expected_step_length_unit"] != "mm"
                        or any(not 0 < len(source_declaration[key]) <= 80 or not source_declaration[key].isprintable()
                               for key in ("declared_producer", "declared_version"))
                        or any(re.fullmatch(r"[0-9a-f]{64}", source_declaration[key]) is None
                               for key in ("design_sha256", "executable_sha256", "step_sha256"))):
                    raise PrepError("invalid_source_declaration", "Unsupported CAD input declaration.")
                sources = [asset for asset in native_mesh.assets if asset.kind == "source"]
                if (native_mesh.source_kind != "cad_gmsh" or len(sources) != 1
                        or Path(sources[0].path).suffix.lower() not in (".step", ".stp")
                        or sources[0].sha256 != source_declaration["step_sha256"]):
                    raise PrepError("invalid_source_declaration", "The declaration must match the verified STEP source asset.")
                declaration_text = json.dumps(source_declaration, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            resource = self._model_resource(None)
            units = resource.unit_context().get("global")
            if not units or units.get("length") != native_mesh.length_unit:
                raise PrepError("unit_mismatch", "Candidate and document length units must match exactly; coordinate conversion is not implicit.",
                                {"document_units": units, "candidate_length_unit": native_mesh.length_unit})
            _, material_card, material = self._unique_card(material_id, "MAT")
            if material_card.keyword.upper().split("/")[2] not in ("LAW1", "ELAST", "LAW36", "PLAS_TAB"):
                raise PrepError("unsupported_operation", "Mesh adoption supports LAW1/LAW36 material families.")
            property_owner, property_card, prop = self._unique_card(property_id, "PROP")
            prop_family = property_card.keyword.upper().split("/")[2]
            allowed = {"SHELL", "TYPE1"} if native_mesh.dimension == 2 else {"SOLID", "TYPE14"}
            if prop_family not in allowed:
                raise PrepError("incompatible_property", "Choose a shell property for surface meshes and a solid property for volume meshes.")
            tetra10 = bool(native_mesh.elements) and all(cell.kind == "tetra10" for cell in native_mesh.elements)
            if tetra10:
                if native_mesh.source_kind != "standalone_msh" or material_card.keyword.upper().split("/")[2] not in ("LAW1", "ELAST"):
                    raise PrepError("unsupported_operation", "Prepared straight Tet10 adoption requires explicit standalone MSH and LAW1.")
                try:
                    row = property_owner.render().decode("latin1").splitlines()[property_card.data[1]]
                    profile = tuple(int(row[start:start + 10].strip() or "0") for start in (10, 20, 40))
                except (IndexError, ValueError):
                    profile = None
                if profile != (4, 0, 1000):
                    raise PrepError("incompatible_property", "Tet10 requires explicit SOLID Ismstr=4, Iale=0 and Itetra10=1000.")
            structured = native_mesh.source_kind == "structured_recipe"
            structured_hex = structured and native_mesh.dimension == 3
            if structured_hex:
                try:
                    rows = property_owner.render().decode("latin1").splitlines()
                    isolid = int(rows[property_card.data[1]][:10].strip() or "0")
                except (IndexError, ValueError):
                    isolid = None
                if isolid != 1:
                    raise PrepError("incompatible_property", "Sweep hex8 adoption requires explicit PROP/SOLID Isolid=1; inherited or other formulations are not substituted.")
            if name is not None: title(name)
            # Reserve every native integer in parsed node/element rows, including
            # rows omitted by the display projection because their geometry is bad.
            used_nodes, used_elements = set(), set()
            element_roots = {"SHELL", "SH3N", "BRICK", "TETRA4", "TETRA", "BEAM", "TRUSS"}
            for source in self._deck_resources():
                for card in source.cards:
                    root = card.keyword.upper().split("/")[1]
                    if root == "TETRA10":
                        from ..radioss.tetra10 import records
                        used_elements.update(row[0] for row in records(source.lines, card.data))
                        continue
                    used = used_nodes if root == "NODE" else used_elements
                    for index in card.data:
                        try: used.add(int(source.lines[index][:10]))
                        except ValueError:
                            if root in element_roots or root == "NODE":
                                raise PrepError("mesh_inventory_incomplete", "An existing native mesh ID cannot be parsed safely; resolve it before adoption.", {"card_id": card.id}) from None
                    # Reserving leading integers of unrecognised cards is
                    # conservative: other element families still own their IDs.
            def remap(identifiers, used):
                result, next_id = {}, 1
                for identifier in identifiers:
                    candidate = identifier
                    if candidate in used or not 1 <= candidate <= 9999999999:
                        while next_id in used: next_id += 1
                        candidate = next_id
                    integer(candidate)
                    used.add(candidate)
                    result[identifier] = candidate
                return result
            node_map = remap((node.id for node in native_mesh.nodes), used_nodes)
            element_map = remap((cell.id for cell in native_mesh.elements), used_elements)
            used_parts = {identity[1] for card in self.list_cards() if (identity := native_identity(card["keyword"])) and identity[0] == "PART"}
            part_native = {}
            for part in native_mesh.parts:
                identifier = 1
                while identifier in used_parts: identifier += 1
                integer(identifier)
                part_native[part.uuid] = identifier
                used_parts.add(identifier)
            newline = resource.newline
            encoded_coordinates = {node.id: tuple(float(real(value)) for value in node.xyz) for node in native_mesh.nodes}
            structured_quad = structured and native_mesh.dimension == 2
            if structured:
                from .structured_mesh import validate_structured_native_coordinates
                try:
                    validate_structured_native_coordinates(native_mesh, encoded_coordinates)
                except PrepError as exc:
                    if exc.code == "candidate_changed":
                        raise
                    raise PrepError("native_precision", "Native field rounding would violate the structured mesh admission limits.",
                                    {"reason": exc.code, **exc.details}) from exc
            elif tetra10:
                from .tet10_geometry import assess_straight_tet10
                for cell in native_mesh.elements:
                    report = assess_straight_tet10(tuple(encoded_coordinates[node] for node in cell.node_ids))
                    if report["problem"]:
                        raise PrepError("native_precision", "Native coordinates violate the straight Tet10 profile.",
                                        {"element_id": cell.id, "reason": report["problem"]})
            else:
                for cell in native_mesh.elements:
                    points = [encoded_coordinates[node] for node in cell.node_ids]
                    q, measure, normalized = (triangle_quality(points) if native_mesh.dimension == 2 else tetrahedron_quality(points))
                    if (not all(math.isfinite(value) for value in (q, measure, normalized)) or normalized <= 1e-12 or q < .1):
                        raise PrepError("native_precision", "Native field rounding would violate the mesh quality admission limits.", {"element_id": cell.id})
            node_rows = [integer(node_map[node.id]) + "".join(real(value) for value in node.xyz) for node in native_mesh.nodes]
            provenance = [f"# CAELab mesh {native_mesh.mesh_uuid}; geometry {native_mesh.geometry_resource_uuid}",
                          f"# Length unit {native_mesh.length_unit}; omitted boundary cells {native_mesh.omitted_boundary_cells}"]
            provenance.extend(f"# Source {asset.kind} sha256 {asset.sha256}" for asset in native_mesh.assets)
            if declaration_text is not None:
                provenance.append("# CAELab adopted input declaration (unverified): " + declaration_text)
            texts = [newline.join(["/NODE", *provenance, *node_rows, ""])]
            part_positions, cells_by_part = {}, {}
            for cell in native_mesh.elements: cells_by_part.setdefault(cell.part_uuid, []).append(cell)
            for part in native_mesh.parts:
                identifier = part_native[part.uuid]
                part_name = name if name is not None and len(native_mesh.parts) == 1 else part.name
                if name is not None and len(native_mesh.parts) > 1: part_name = f"{name}: {part.name}"
                part_positions[part.uuid] = len(texts)
                marker = f"# CAELab adopted mesh {native_mesh.mesh_uuid}; part {part.uuid}"
                texts.append(newline.join([f"/PART/{identifier}", title(part_name), marker,
                    integer(prop[1]) + integer(material[1]) + f"{0:10d}", ""]))
                keyword = "SHELL" if structured_quad else "BRICK" if structured_hex else "TETRA10" if tetra10 else "SH3N" if native_mesh.dimension == 2 else "TETRA4"
                cells = cells_by_part.get(part.uuid, [])
                if tetra10:
                    from .tet10_geometry import native_tet10_nodes
                    rows = [row for cell in cells for row in (integer(element_map[cell.id]),
                            "".join(integer(node_map[node]) for node in native_tet10_nodes(cell.node_ids)))]
                else:
                    rows = [integer(element_map[cell.id]) + "".join(integer(node_map[node]) for node in cell.node_ids) for cell in cells]
                texts.append(newline.join([f"/{keyword}/{identifier}", marker, *rows, ""]))
            group_positions = {}
            group_reserved = {}
            for group in getattr(native_mesh, "groups", ()):
                if group.key in group_positions:
                    raise PrepError("invalid_reference", "Imported group keys must be distinct.")
                if group.kind == "node":
                    family, mapping = "GRNOD/NODE", node_map
                elif group.kind == "element":
                    family = self._element_group_family("quad" if structured_quad else "hexahedron" if structured_hex else "triangle" if native_mesh.dimension == 2 else "tetra")
                    mapping = element_map
                else:
                    raise PrepError("invalid_reference", "Imported groups must contain nodes or physical elements.")
                if not group.member_ids or len(set(group.member_ids)) != len(group.member_ids) or any(type(item) is not int or item not in mapping for item in group.member_ids):
                    raise PrepError("invalid_reference", "An imported group contains duplicate or unadopted members.", {"group_key": group.key})
                namespace = family.split("/")[0]
                if namespace not in group_reserved:
                    group_reserved[namespace] = {identity[1] for card in self.list_cards()
                        if (identity := native_identity(card["keyword"])) and identity[0] == namespace}
                identifier = 1
                while identifier in group_reserved[namespace]: identifier += 1
                group_reserved[namespace].add(identifier)
                group_positions[group.key] = len(texts)
                texts.append(member_block(family, identifier, group.name,
                    [mapping[item] for item in group.member_ids], newline=newline))
            if replacement_state is None:
                state, card_ids = resource.inserted_states(texts)
            else:
                state, card_ids = replacement_state, [str(uuid4()) for _ in texts]
                state["created"].extend({"id": card_id, "text": text} for card_id, text in zip(card_ids, texts))
            part_map = {key: card_ids[position] for key, position in part_positions.items()}
            group_map = {key: card_ids[position] for key, position in group_positions.items()}
            protected_sources = {str(Path(asset.path).resolve()) for asset in native_mesh.assets}
            if native_mesh.source_kind in ("standalone_msh", "cad_gmsh"):
                metadata = next(asset for asset in native_mesh.assets if asset.kind == "metadata")
                raw = Path(metadata.path).read_bytes()
                if sha256(raw).hexdigest() != metadata.sha256:
                    raise PrepError("candidate_changed", "Candidate metadata changed after validation.")
                source = json.loads(raw.decode("utf-8"))["source"]
                key = "original_path" if native_mesh.source_kind == "standalone_msh" else "path"
                if key in source:
                    original = source[key]
                    if not isinstance(original, str) or not original.strip():
                        raise PrepError("invalid_candidate", "An original source path must be a nonempty string.")
                    protected_sources.add(str(Path(original).expanduser().resolve()))
            result = dict(
                card_ids=card_ids, part_ids=list(part_map.values()), part_id_map=part_map,
                group_id_map=group_map, source_kind=getattr(native_mesh, "source_kind", "cad_gmsh"),
                node_id_map=node_map, element_id_map=element_map,
                mesh_uuid=native_mesh.mesh_uuid, geometry_resource_uuid=native_mesh.geometry_resource_uuid,
                omitted_boundary_cells=native_mesh.omitted_boundary_cells, unused_node_ids=list(native_mesh.unused_node_ids), **replacement_details)
            return {"resource_id": resource.id, "state": state, "result": result,
                    "protected_sources": protected_sources, "native_mesh": native_mesh,
                    "replacement_targets": replacement_targets}

    def _publish_mesh_adoption(self, prepared, *, expected_revision=None):
        # Observers may save synchronously when the committed geometry is published.
        previous_sources = self._source_paths
        self._source_paths = previous_sources | prepared["protected_sources"]
        resource = self.document.resources[prepared["resource_id"]]
        result = prepared["result"]
        try:
            if "relations" in prepared:
                change = self.dispatcher.execute_many(
                    {resource.id: prepared["state"], self._relations_resource().id: prepared["relations"]},
                    "Replace CAD mesh and mark targets stale",
                    object_ids=tuple(result["card_ids"]) + tuple(prepared["replacement_targets"]),
                    expected_revision=expected_revision, kind="structure")
            else:
                change = self.dispatcher.execute(resource.id, prepared["state"], "Adopt mesh candidate",
                    object_ids=tuple(result["card_ids"]), expected_revision=expected_revision, kind="structure")
        except Exception:
            self._source_paths = previous_sources
            raise
        return self._model_result(resource, next(iter(result["part_ids"]), None), change, **result)

    def create_curve(self, name, points, *, resource_id=None, native_id=None,
                     expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("FUNCT", native_id)
            return self._insert_model_card(resource, curve_block(identifier, name, points, newline=resource.newline),
                                           "Create curve", expected_revision)

    def set_curve_points(self, card_id, points, *, expected_revision=None, expected_document_id=None):
        """Replace numeric rows, preserving card identity, title, comments and other cards."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource, card, _ = self._unique_card(card_id, "FUNCT")
            if card.keyword.upper().split("/")[1] != "FUNCT" or len(card.data) < 2:
                raise PrepError("unsupported_operation", "Only ordinary FUNCT curve rows can be replaced.")
            rows = curve_points(points)
            lines = self.card_text(card_id).splitlines(keepends=True)
            point_rows = {index - card.start for index in card.data[1:]}
            result, cursor = [], 0
            last = max(point_rows)
            for index, line in enumerate(lines):
                if index not in point_rows:
                    result.append(line)
                elif cursor < len(rows):
                    ending = "\r\n" if line.endswith("\r\n") else "\r" if line.endswith("\r") else "\n"
                    result.append(rows[cursor] + ending)
                    cursor += 1
                if index == last:
                    result.extend(row + resource.newline for row in rows[cursor:])
                    cursor = len(rows)
            state = resource.replaced_state(card_id, "".join(result))
            change = self.dispatcher.execute(resource.id, state, "Edit curve points", object_ids=(card_id,),
                                             expected_revision=expected_revision, kind="structure")
            return self._model_result(resource, card_id, change)

    @staticmethod
    def _member_sequence(values):
        if not isinstance(values, (list, tuple)) or not values:
            raise PrepError("invalid_reference", "Choose at least one member.")
        if any(not isinstance(value, (str, int)) or isinstance(value, bool) for value in values) or len(set(values)) != len(values):
            raise PrepError("invalid_reference", "Members must be distinct typed identities.")
        return values

    def _node_members(self, values):
        self._member_sequence(values)
        for value in values: integer(value)
        # Inspect raw native IDs, including duplicates within one NODE block; the
        # display projection intentionally removes these and cannot be an oracle.
        counts = {}
        for resource in self._deck_resources():
            for card in resource.cards:
                if card.keyword.upper().split("/")[1] != "NODE": continue
                for index in card.data:
                    try: node = int(resource.lines[index][:10])
                    except ValueError: continue
                    counts[node] = counts.get(node, 0) + 1
        for value in values:
            if counts.get(value, 0) != 1:
                raise PrepError("dangling_reference" if not counts.get(value) else "ambiguous_reference",
                                "Each group node must exist exactly once in the assembled document.", {"node_id": value})
        return list(values)

    def _supported_reference(self, card_id, namespace, allowed):
        resource, card, identity = self._unique_card(card_id, namespace)
        words = card.keyword.upper().split("/")
        family = words[2] if len(words) > 2 and namespace not in ("FUNCT", "BCS", "CLOAD") else words[1]
        if family not in allowed or (namespace == "FUNCT" and words[1] != "FUNCT"):
            raise PrepError("unsupported_operation", "This reference uses an unsupported native card family.")
        return resource, card, identity

    def _group_reference(self, card_id):
        if card_id in self._relations_resource().snapshot()["stale_targets"]:
            raise PrepError("stale_mesh_target", "Reconnect this node group's explicit correspondence before assigning it to a condition.")
        resource, card, identity = self._supported_reference(card_id, "GRNOD", {"NODE"})
        self._node_members(self._integer_members(resource, card))
        return identity[1]

    @staticmethod
    def _integer_members(resource, card):
        lines = resource.render().decode("latin1").splitlines()
        try:
            values = [int(lines[index][offset:offset + 10]) for index in card.data[1:]
                      for offset in range(0, len(lines[index].rstrip()), 10) if lines[index][offset:offset + 10].strip()]
        except ValueError:
            raise PrepError("invalid_reference", "The member list is not a supported fixed-width integer list.") from None
        return values

    def create_node_group(self, name, node_ids, *, resource_id=None, native_id=None,
                          expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            members = self._node_members(node_ids)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("GRNOD", native_id)
            return self._insert_model_card(resource, member_block("GRNOD/NODE", identifier, name, members, newline=resource.newline),
                                           "Create node group", expected_revision)

    def _surface_part_ids(self, part_ids):
        self._member_sequence(part_ids)
        identifiers = []
        # Read all cells, even those the display omitted for missing nodes.
        cells = [cell for resource in self._deck_resources() for cell in resource.mesh_projection()["cells"]]
        kinds_by_part = {}
        for cell in cells: kinds_by_part.setdefault(cell.get("part_id"), set()).add(cell["type"])
        for part_id in part_ids:
            _, _, identity = self._unique_card(part_id, "PART")
            kinds = kinds_by_part.get(identity[1], set())
            if not kinds or kinds - {"quad", "triangle"}:
                raise PrepError("incompatible_surface", "SURF/PART supports nonempty shell/triangle parts; solid faces need a different surface definition.")
            identifiers.append(identity[1])
        return identifiers

    @staticmethod
    def _element_group_family(kind, formulation=None):
        if kind == "line": return {"BEAM": "GRBEAM/BEAM", "TRUSS": "GRTRUS/TRUS"}.get(formulation)
        return {"triangle": "GRSH3N/SH3N", "quad": "GRSHEL/SHEL", "tetra": "GRBRIC/BRIC", "tetra10": "GRBRIC/BRIC",
                "hexahedron": "GRBRIC/BRIC", "wedge": "GRBRIC/BRIC", "pyramid": "GRBRIC/BRIC"}.get(kind)

    def _element_members(self, members, family=None):
        if not isinstance(members, (tuple, list)) or not members:
            raise PrepError("invalid_reference", "Choose at least one typed element reference.")
        if self._projection_cache is None: self.mesh_view()
        references, identifiers, families, seen = [], [], set(), set()
        cells_by_id = self._projection_index["cells_by_id"]
        for value in members:
            if isinstance(value, SelectionRef): ref = value
            elif isinstance(value, dict) and set(value) == {"resource_id", "entity_kind", "local_id"}:
                ref = SelectionRef(**value)
            else:
                raise PrepError("invalid_reference", "Element members require resource_id, entity_kind and local_id.")
            if ref.entity_kind != "element" or not isinstance(ref.resource_id, str):
                raise PrepError("invalid_reference", "A typed element reference is required.")
            integer(ref.local_id)
            matches = cells_by_id.get(ref.local_id, [])
            if len(matches) != 1:
                raise PrepError("dangling_reference" if not matches else "ambiguous_reference", "Element IDs in a native group must resolve uniquely across resources.", {"element_id": ref.local_id})
            cell = matches[0]
            if cell["resource_id"] != ref.resource_id:
                raise PrepError("invalid_reference", "The element does not belong to the stated resource.")
            kind = self._element_group_family(cell["type"], cell.get("formulation"))
            if kind is None:
                raise PrepError("unsupported_operation", "Element groups support triangle3, quad4 and supported solid cells.")
            if ref in seen:
                raise PrepError("invalid_reference", "Group members must be distinct.")
            seen.add(ref)
            references.append(ref)
            identifiers.append(ref.local_id)
            families.add(kind)
        if len(families) != 1 or (family is not None and families != {family}):
            raise PrepError("incompatible_group", "A native element group must keep its triangle, quad or solid family; mixed shell families require separate groups.")
        return identifiers, references, next(iter(families))

    def create_element_group(self, name, element_refs, *, resource_id=None, native_id=None,
                             expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            members, _, family = self._element_members(element_refs)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id(family.split("/")[0], native_id)
            return self._insert_model_card(resource, member_block(family, identifier, name, members, newline=resource.newline),
                                           "Create element group", expected_revision)

    def group_members(self, card_id):
        with self._lock:
            resource = self._find_card(card_id)
            card = resource.card(card_id)
            family = "/".join(card.keyword.upper().split("/")[1:3])
            if family not in ("GRNOD/NODE", "GRSH3N/SH3N", "GRSHEL/SHEL", "GRBRIC/BRIC", "GRBEAM/BEAM", "GRTRUS/TRUS"):
                raise PrepError("unsupported_operation", "Group membership editing supports explicit node, triangle, quad and solid ID lists.")
            result = {"card_id": card_id, "resource_id": resource.id, "kind": "node" if family == "GRNOD/NODE" else "element",
                      "members": [], "member_ids": [], "diagnostics": []}
            stale = self._relations_resource().snapshot()["stale_targets"].get(card_id)
            if stale:
                result["diagnostics"].append({"code": "stale_mesh_target", "message": "Explicit correspondence to the replacement mesh has not been accepted.",
                    "mesh_resource_id": stale["mesh_resource_id"], "mesh_revision": stale["mesh_revision"]})
            try:
                identifiers = self._integer_members(resource, card)
                result["member_ids"] = identifiers
                if family == "GRNOD/NODE":
                    self._node_members(identifiers)
                    if self._projection_cache is None: self.mesh_view()
                    refs = []
                    for identifier in identifiers:
                        owners = self._projection_cache["node_resources"].get(identifier, [])
                        if len(owners) != 1:
                            raise PrepError("invalid_reference", "A group node cannot be displayed uniquely.")
                        refs.append(SelectionRef(owners[0], "node", identifier))
                else:
                    if self._projection_cache is None: self.mesh_view()
                    refs, cells_by_id = [], {}
                    for cell in self._projection_cache["cells"]:
                        cells_by_id.setdefault(cell["id"], []).append(cell)
                    for identifier in identifiers:
                        matches = cells_by_id.get(identifier, [])
                        if len(matches) != 1:
                            raise PrepError("dangling_reference" if not matches else "ambiguous_reference", "A group element cannot be resolved uniquely.", {"element_id": identifier})
                        refs.append(SelectionRef(matches[0]["resource_id"], "element", identifier))
                    _, refs, _ = self._element_members(refs, family)
                result["members"] = [asdict(ref) for ref in refs]
            except PrepError as exc:
                result["diagnostics"].append({"code": exc.code, "message": exc.message, **exc.details})
            return result

    def _group_members_state(self, card_id, members):
        """Prepare the existing native member-row edit without publishing it."""
        resource, card, _ = self._unique_card(card_id)
        family = "/".join(card.keyword.upper().split("/")[1:3])
        if family == "GRNOD/NODE":
            if isinstance(members, (list, tuple)) and members and all(type(member) is int for member in members):
                identifiers = self._node_members(members)
            else:
                if not isinstance(members, (list, tuple)) or not members:
                    raise PrepError("invalid_reference", "Choose at least one node.")
                if self._projection_cache is None: self.mesh_view()
                identifiers = []
                for member in members:
                    ref = member if isinstance(member, SelectionRef) else SelectionRef(**member) if isinstance(member, dict) and set(member) == {"resource_id", "entity_kind", "local_id"} else None
                    if (ref is None or ref.entity_kind != "node" or type(ref.local_id) is not int
                            or self._projection_cache["node_resources"].get(ref.local_id) != (ref.resource_id,)):
                        raise PrepError("invalid_reference", "A uniquely owned node reference is required.")
                    identifiers.append(ref.local_id)
                identifiers = self._node_members(identifiers)
        elif family in ("GRSH3N/SH3N", "GRSHEL/SHEL", "GRBRIC/BRIC", "GRBEAM/BEAM", "GRTRUS/TRUS"):
            identifiers, _, _ = self._element_members(members, family)
        else:
            raise PrepError("unsupported_operation", "This native group does not have an editable explicit member list.")
        if identifiers == self._integer_members(resource, card):
            return resource, card, identifiers, None
        if len(card.data) < 2:
            raise PrepError("invalid_card", "The group has no native member rows.")
        rows = ["".join(integer(identifier) for identifier in identifiers[index:index + 10]) for index in range(0, len(identifiers), 10)]
        lines = self.card_text(card_id).splitlines(keepends=True)
        member_rows = {index - card.start for index in card.data[1:]}
        result, cursor = [], 0
        for index, line in enumerate(lines):
            if index not in member_rows: result.append(line)
            elif cursor < len(rows):
                ending = "\r\n" if line.endswith("\r\n") else "\r" if line.endswith("\r") else "\n"
                result.append(rows[cursor] + ending)
                cursor += 1
            if index == max(member_rows):
                result.extend(row + resource.newline for row in rows[cursor:])
                cursor = len(rows)
        return resource, card, identifiers, resource.replaced_state(card_id, "".join(result))

    def set_group_members(self, card_id, members, *, expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource, card, _, state = self._group_members_state(card_id, members)
            if state is None:
                return self._model_result(resource, card_id, None)
            self._validate_dependent_condition_states({resource.id:state})
            change = self.dispatcher.execute(resource.id, state, "Edit group members", object_ids=(card_id,),
                                             expected_revision=expected_revision, kind="structure")
            return self._model_result(resource, card_id, change)

    def create_surface(self, name, part_ids, *, resource_id=None, native_id=None,
                       expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            members = self._surface_part_ids(part_ids)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("SURF", native_id)
            return self._insert_model_card(resource, member_block("SURF/PART", identifier, name, members, newline=resource.newline),
                                           "Create shell surface", expected_revision)

    def create_boundary_condition(self, name, group_id, translations, rotations, *, coordinate_system_id=None, resource_id=None, native_id=None,
                                  expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            group = self._group_reference(group_id)
            # Native BCS permits fixing an inactive rotation. Report the field
            # applicability separately; do not reject a valid all-fixed deck.
            self._validate_condition_components(group_id, translations=translations, rotations=rotations, coordinate_system_id=coordinate_system_id, enforce=False)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("BCS", native_id)
            return self._insert_model_card(resource, boundary_block(identifier, name, group, translations, rotations,
                skew=self._coordinate_reference(coordinate_system_id), newline=resource.newline),
                                           "Create boundary condition", expected_revision)

    def create_load(self, name, group_id, curve_id, direction, scale, *, coordinate_system_id=None, resource_id=None, native_id=None,
                    expected_revision=None, expected_document_id=None):
        """CLOAD scale is the load at EACH group node, not the group resultant."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            group = self._group_reference(group_id)
            curve = self._curve_reference(curve_id)
            self._validate_condition_components(group_id, translations=tuple(direction == value for value in ("X","Y","Z")),
                rotations=tuple(direction == value for value in ("XX","YY","ZZ")), coordinate_system_id=coordinate_system_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("CLOAD", native_id)
            return self._insert_model_card(resource, load_block(identifier, name, group, curve, direction, scale,
                skew=self._coordinate_reference(coordinate_system_id), newline=resource.newline),
                                           "Create per-node load", expected_revision)

    def create_initial_velocity(self, name, group_id, velocity, *, coordinate_system_id=None, resource_id=None, native_id=None,
                                expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            group = self._group_reference(group_id)
            self._validate_condition_components(group_id, translations=(True,True,True), coordinate_system_id=coordinate_system_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("INIVEL", native_id)
            return self._insert_model_card(resource, velocity_block(identifier, name, group, velocity,
                skew=self._coordinate_reference(coordinate_system_id), newline=resource.newline),
                                           "Create initial velocity", expected_revision)

    def create_contact(self, name, secondary_group_id, main_surface_id, friction, *, resource_id=None, native_id=None,
                       expected_revision=None, expected_document_id=None):
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            secondary = self._group_reference(secondary_group_id)
            surface = self._surface_reference(main_surface_id)
            resource = self._model_resource(resource_id)
            identifier = self._allocate_native_id("INTER", native_id)
            return self._insert_model_card(resource, contact_block(identifier, name, secondary, surface, friction, newline=resource.newline),
                                           "Create TYPE7 contact", expected_revision)

    def _condition_layout(self, card):
        words = card.keyword.upper().split("/")
        family = "/".join(words[1:3]) if words[1] in ("INIVEL", "INTER") else words[1]
        layouts = {
            "BCS": {"translations": (1, 0, 6, "bool3"), "rotations": (1, 6, 10, "bool3"), "group_id": (1, 20, 30, "GRNOD"), "coordinate_system_id": (1,10,20,"SKEW")},
            "CLOAD": {"curve_id": (1, 0, 10, "FUNCT"), "direction": (1, 10, 20, "str"),
                      "group_id": (1, 40, 50, "GRNOD"), "scale": (1, 80, 100, "float"), "coordinate_system_id": (1,20,30,"SKEW")},
            "INIVEL/TRA": {"velocity": (1, 0, 60, "vector3"), "group_id": (1, 60, 70, "GRNOD"), "coordinate_system_id": (1,70,80,"SKEW")},
            "INTER/TYPE7": {"secondary_group_id": (1, 0, 10, "GRNOD"), "main_surface_id": (1, 10, 20, "SURF"),
                            "friction": (4, 20, 40, "float")},
        }
        if family not in layouts:
            raise PrepError("unsupported_operation", "Condition editing supports BCS, CLOAD, INIVEL/TRA and INTER/TYPE7.")
        layout = dict(layouts[family])
        if family == "INTER/TYPE7":
            resource = self._find_card(card.id)
            lines = resource.render().decode("latin1").splitlines()
            try: curvature = int(lines[card.data[1]][80:90].strip() or "0")
            except (ValueError, IndexError):
                raise PrepError("invalid_card", "Cannot read TYPE7 curvature options.") from None
            if curvature not in (0, 1, 2, 3):
                raise PrepError("unsupported_operation", "TYPE7 curvature options outside 0/1/2/3 are not editable.")
            if curvature in (1, 2):
                layout["friction"] = (5, 20, 40, "float")
        return family, layout

    def condition_values(self, card_id):
        """Read supported logical values and resolve references without hiding ambiguity."""
        with self._lock:
            resource = self._find_card(card_id)
            card = resource.card(card_id)
            _, layout = self._condition_layout(card)
            lines = resource.render().decode("latin1").splitlines()
            native_rows = [lines[index] for index in card.data]
            result = {"card_id": card.id, "resource_id": resource.id, "diagnostics": []}
            for key, (row, start, stop, kind) in layout.items():
                try:
                    raw = lines[card.data[row]][start:stop]
                    if kind == "str": value = raw.strip()
                    elif kind == "float":
                        default, zero_default = condition_scalar_default(card.keyword, key, native_rows)
                        value = number(raw.strip()) if raw.strip() else default
                        if zero_default and value == 0: value = default
                        if key == "friction": result["friction_is_scale"] = zero_default
                    elif kind == "vector3": value = [number(raw[index:index + 20].strip() or "0") for index in (0, 20, 40)]
                    elif kind == "bool3":
                        bits = raw.strip()
                        if len(bits) != 3 or set(bits) - {"0", "1"}: raise ValueError()
                        value = [bit == "1" for bit in bits]
                    else:
                        native_id = int(raw.strip() or "0")
                        if kind == "SKEW" and native_id == 0:
                            result[key] = None
                            continue
                        matches = self._native_matches(kind, native_id)
                        value = matches[0]["id"] if len(matches) == 1 else None
                        if value is None:
                            result["diagnostics"].append({"code": "dangling_reference" if not matches else "ambiguous_reference",
                                "field": key, "native_id": native_id, "message": "The condition reference cannot be resolved uniquely."})
                    if kind == "float" and not math.isfinite(value): raise ValueError()
                    if kind == "vector3" and not all(math.isfinite(item) for item in value): raise ValueError()
                except (ValueError, IndexError):
                    raise PrepError("invalid_card", "A supported condition field is malformed.", {"card_id": card_id, "field": key}) from None
                result[key] = value
            return result

    def _curve_reference(self, card_id):
        resource, card, identity = self._supported_reference(card_id, "FUNCT", {"FUNCT"})
        values = {field["name"]: field["value"] for field in resource.card_fields(card_id)}
        curve_points([(values.get(f"point_{i}_x"), values.get(f"point_{i}_y")) for i in range(len(card.data) - 1)])
        return identity[1]

    def _surface_reference(self, card_id):
        if card_id in self._relations_resource().snapshot()["stale_targets"]:
            raise PrepError("stale_mesh_target", "Reconnect this surface before assigning it to a contact.")
        resource, card, identity = self._supported_reference(card_id, "SURF", {"PART"})
        parts = []
        for native_part in self._integer_members(resource, card):
            matches = self._native_matches("PART", native_part)
            if len(matches) != 1:
                raise PrepError("invalid_reference", "The surface contains an unresolved or ambiguous PART.")
            parts.append(matches[0]["id"])
        self._surface_part_ids(parts)
        return identity[1]

    def set_condition_values(self, card_id, values, *, expected_revision=None, expected_document_id=None):
        """Patch only requested native columns; retain options, comments and stable ID."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource, card, identity = self._unique_card(card_id)
            family, layout = self._condition_layout(card)
            if not isinstance(values, dict) or not values or set(values) - set(layout):
                raise PrepError("invalid_command", "Choose supported condition fields only.")
            current = self.condition_values(card_id)
            merged = {**current, **values}
            for key, (_, _, _, kind) in layout.items():
                if kind in ("GRNOD", "FUNCT", "SURF") and merged[key] is None:
                    raise PrepError("invalid_reference", "Replace unresolved condition references before applying.", {"field": key})
            if family == "BCS":
                self._validate_condition_components(merged["group_id"], translations=merged["translations"], rotations=merged["rotations"], coordinate_system_id=merged["coordinate_system_id"], enforce=False)
                text = boundary_block(identity[1], "Validated", self._group_reference(merged["group_id"]), merged["translations"], merged["rotations"], skew=self._coordinate_reference(merged["coordinate_system_id"]))
            elif family == "CLOAD":
                self._validate_condition_components(merged["group_id"], translations=tuple(merged["direction"] == value for value in ("X","Y","Z")), rotations=tuple(merged["direction"] == value for value in ("XX","YY","ZZ")), coordinate_system_id=merged["coordinate_system_id"])
                text = load_block(identity[1], "Validated", self._group_reference(merged["group_id"]), self._curve_reference(merged["curve_id"]), merged["direction"], merged["scale"], skew=self._coordinate_reference(merged["coordinate_system_id"]))
            elif family == "INIVEL/TRA":
                self._validate_condition_components(merged["group_id"], translations=(True,True,True), coordinate_system_id=merged["coordinate_system_id"])
                text = velocity_block(identity[1], "Validated", self._group_reference(merged["group_id"]), merged["velocity"], skew=self._coordinate_reference(merged["coordinate_system_id"]))
            else:
                text = contact_block(identity[1], "Validated", self._group_reference(merged["secondary_group_id"]), self._surface_reference(merged["main_surface_id"]), merged["friction"])
                rendered = resource.render().decode("latin1").splitlines()
                _, zero_default = condition_scalar_default(card.keyword, "friction", [rendered[index] for index in card.data])
                if zero_default: reject_default_zero(merged["friction"], "friction")
            canonical = text.splitlines()[1:]
            changed = []
            for key, value in values.items():
                kind = layout[key][3]
                normalized = (float(value) if kind == "float" else [float(item) for item in value] if kind == "vector3"
                              else list(value) if kind == "bool3" else value)
                if normalized != current[key]: changed.append(key)
            if not changed:
                return self._model_result(resource, card_id, None)
            lines = self.card_text(card_id).splitlines(keepends=True)
            for key in changed:
                row, start, stop, _ = layout[key]
                index = card.data[row] - card.start
                old = lines[index]
                ending = "\r\n" if old.endswith("\r\n") else "\r" if old.endswith("\r") else "\n" if old.endswith("\n") else ""
                body = old[:-len(ending)] if ending else old
                lines[index] = body.ljust(stop)[:start] + canonical[4 if family == "INTER/TYPE7" and key == "friction" else row][start:stop] + body[stop:] + ending
            state = resource.replaced_state(card_id, "".join(lines))
            change = self.dispatcher.execute(resource.id, state, "Edit condition", object_ids=(card_id,),
                                             expected_revision=expected_revision, kind="structure")
            return self._model_result(resource, card_id, change)

    @staticmethod
    def _supported_model_card(card):
        words = card.keyword.upper().split("/")
        return len(words) >= 4 and ((words[1] == "MAT" and words[2] in ("LAW1", "ELAST", "LAW36", "PLAS_TAB"))
                                  or (words[1] == "PROP" and words[2] in ("SHELL", "TYPE1", "SOLID", "TYPE14"))) or (
                words[1] in ("FUNCT", "BCS", "CLOAD") or tuple(words[1:3]) in
                (("GRNOD", "NODE"), ("GRSH3N", "SH3N"), ("GRSHEL", "SHEL"), ("GRBRIC", "BRIC"), ("GRBEAM", "BEAM"), ("GRTRUS", "TRUS"),
                 ("SURF", "PART"), ("INIVEL", "TRA"), ("INTER", "TYPE7")))

    def copy_card(self, card_id, *, name=None, resource_id=None, native_id=None,
                  expected_revision=None, expected_document_id=None):
        """Copy a complete material/property block, retaining its nonedited native fields."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            source, card, identity = self._unique_card(card_id)
            if not self._supported_model_card(card):
                raise PrepError("unsupported_operation", "Copy supports the verified material, shell property and condition card families only.")
            destination = self._model_resource(resource_id if resource_id is not None else source.id)
            identifier = self._allocate_native_id(identity[0], native_id)
            text = copy_block(self.card_text(card_id), identifier, name=name, newline=destination.newline)
            return self._insert_model_card(destination, text, "Copy " + card.keyword, expected_revision)

    def _part_native_references(self, card_id):
        resource, card, identity = self._unique_card(card_id, "PART")
        if len(card.data) < 2:
            raise PrepError("invalid_reference", "The PART card has no assignment row.")
        lines = resource.render().decode("latin1").splitlines()
        line = lines[card.data[1]]
        try:
            prop, material = int(line[:10]), int(line[10:20])
            subset = int(line[20:30].strip() or "0")
            if min(prop, material) < 1 or subset < 0: raise ValueError()
        except ValueError:
            raise PrepError("invalid_reference", "The PART assignment row is not a supported fixed-width reference.") from None
        return resource, card, {"native_property_id": prop, "native_material_id": material,
                                "subset_id": subset, "native_part_id": identity[1]}

    def part_assignments(self, card_id):
        """Resolve current UUID targets; unresolved or ambiguous references remain explicit."""
        with self._lock:
            resource, card, refs = self._part_native_references(card_id)
            result = {"card_id": card.id, "resource_id": resource.id, **refs, "diagnostics": []}
            for key, namespace in (("material_id", "MAT"), ("property_id", "PROP")):
                identifier = refs["native_" + key]
                matches = self._native_matches(namespace, identifier)
                result[key] = matches[0]["id"] if len(matches) == 1 else None
                if len(matches) != 1:
                    result["diagnostics"].append({"code": "dangling_reference" if not matches else "ambiguous_reference",
                        "field": key, "native_id": identifier, "message": "The PART reference cannot be resolved uniquely."})
            return result

    # Singular alias for callers using an individual PART query.
    part_assignment = part_assignments

    def _dependency_inventory(self, card_id):
        _, _, identity = self._unique_card(card_id)
        dependents, unverified = [], []
        independent = {"BEGIN", "END", "NODE", "SHELL", "SH3N", "BRICK", "TETRA4", "TETRA",
                       "BEAM", "TRUSS", "FUNCT", "UNIT"}
        independent_pairs = {("MAT", "LAW1"), ("MAT", "ELAST"), ("PROP", "SHELL"), ("PROP", "TYPE1"), ("PROP", "SOLID"), ("PROP", "TYPE14")}
        rendered_by_resource = {}
        for item in self.list_cards():
            words = item["keyword"].upper().split("/")
            root, pair = words[1], tuple(words[1:3])
            resource = self._find_card(item["id"])
            card = resource.card(item["id"])
            if resource.id not in rendered_by_resource:
                rendered_by_resource[resource.id] = resource.render().decode("latin1").splitlines()
            rendered = rendered_by_resource[resource.id]
            rows = [rendered[index] for index in card.data]
            references = []
            def at(row, start, stop):
                return int(rows[row][start:stop].strip() or "0")
            try:
                if root == "PART":
                    _, _, refs = self._part_native_references(item["id"])
                    references = [("MAT", refs["native_material_id"]), ("PROP", refs["native_property_id"])]
                elif pair in (("PROP", "PLY"), ("PROP", "TYPE19")):
                    references = [("MAT", at(1, 0, 10))]
                elif root == "BCS":
                    references = [("GRNOD", at(1, 20, 30))]
                elif root == "CLOAD":
                    references = [("FUNCT", at(1, 0, 10)), ("GRNOD", at(1, 40, 50))]
                elif pair == ("INIVEL", "TRA"):
                    references = [("GRNOD", at(1, 60, 70))]
                elif pair == ("INTER", "TYPE7"):
                    curvature = at(1, 80, 90)
                    if curvature not in (0, 1, 2, 3): raise ValueError()
                    final_row = 7 if curvature in (1, 2) else 6
                    references = [("GRNOD", at(1, 0, 10)), ("SURF", at(1, 10, 20)), ("FUNCT", at(final_row, 60, 70))]
                    # Thermal/friction-law options add conditional rows. Their
                    # references are not guessed by the supported mechanical profile.
                    if identity[0] == "FUNCT" and (at(1, 30, 40) or at(final_row, 0, 10)):
                        unverified.append(item)
                elif pair in (("SURF", "PART"), ("GRNOD", "PART")):
                    references = [("PART", value) for value in self._integer_members(resource, card)]
                elif pair in (("GRNOD", "NODE"), ("GRSH3N", "SH3N"), ("GRSHEL", "SHEL"), ("GRBRIC", "BRIC"), ("GRBEAM", "BEAM"), ("GRTRUS", "TRUS")):
                    pass  # Node/element identities are not card-level deletable objects.
                elif pair in (("MAT", "LAW36"), ("MAT", "PLAS_TAB")):
                    if identity[0] == "FUNCT": unverified.append(item)
                elif root not in independent and pair not in independent_pairs:
                    unverified.append(item)
            except (PrepError, ValueError, IndexError):
                unverified.append(item)
                continue
            if identity in references:
                dependents.append(item)
        return dependents, unverified

    def card_dependents(self, card_id):
        """Known typed references; deletion additionally requires a complete native scan."""
        with self._lock:
            return self._dependency_inventory(card_id)[0]

    def delete_card(self, card_id, *, expected_revision=None, expected_document_id=None):
        """Delete an unreferenced material/property; never cascade into other cards."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource, card, identity = self._unique_card(card_id)
            if not self._supported_model_card(card):
                raise PrepError("unsupported_operation", "Delete supports the verified material, shell property and condition card families only.")
            cases = [case for case in self.analysis_cases()["cases"] if card_id in case["condition_ids"]]
            if cases:
                raise PrepError("card_in_use", "Remove the condition from these analysis cases before deleting it: " + ", ".join(case["name"] for case in cases), {"analysis_cases": cases})
            dependents, unverified = self._dependency_inventory(card_id)
            if dependents:
                raise PrepError("card_in_use", "Remove or reassign the dependent cards before deleting this card.",
                                {"dependents": dependents})
            if unverified:
                raise PrepError("dependency_scan_incomplete", "Deletion is blocked because some cards have unverified native references.",
                                {"cards": unverified})
            state = resource.deleted_state(card_id)
            change = self.dispatcher.execute(resource.id, state, "Delete " + card.keyword,
                object_ids=(card_id,), expected_revision=expected_revision, kind="structure")
            return self._model_result(resource, None, change, deleted_card_id=card_id)

    def assign_part(self, card_id, *, material_id=None, property_id=None,
                    expected_revision=None, expected_document_id=None):
        """Assign UUID targets atomically; native IDs never masquerade as object IDs."""
        with self._lock:
            self._check_model_edit(expected_revision, expected_document_id)
            resource, card, refs = self._part_native_references(card_id)
            if self._projection_cache is None: self.mesh_view()
            part_kinds = {cell["type"] for cell in self._projection_cache["cells"] if cell.get("part_id") == refs["native_part_id"]}
            if "tetra10" in part_kinds and part_kinds != {"tetra10"}:
                raise PrepError("incompatible_property", "Tet10 requires a separate PART from other solid families.")
            if material_id is None and property_id is None:
                raise PrepError("invalid_command", "Choose a material or property to assign.")
            values = {}
            for key, target, namespace in (("material_id", material_id, "MAT"), ("property_id", property_id, "PROP")):
                if target is None:
                    matches = self._native_matches(namespace, refs["native_" + key])
                    if len(matches) != 1:
                        raise PrepError("dangling_reference" if not matches else "ambiguous_reference",
                                        "Replace the unresolved PART reference before applying.", {"field": key})
                    continue
                target_owner, target_card, identity = self._unique_card(target, namespace)
                values[key] = identity[1]
                if key == "material_id" and target_card.keyword.upper().split("/")[2] not in ("LAW1", "ELAST", "LAW36", "PLAS_TAB"):
                    raise PrepError("unsupported_operation", "Assignment supports LAW1/LAW36 material families only.")
                if key == "material_id" and "tetra10" in part_kinds and target_card.keyword.upper().split("/")[2] not in ("LAW1", "ELAST"):
                    raise PrepError("unsupported_operation", "The prepared Tet10 profile supports LAW1 material only.")
                if key == "property_id":
                    family = target_card.keyword.upper().split("/")[2]
                    compatible = ({"quad", "triangle"} if family in ("SHELL", "TYPE1") else
                                  {"tetra", "tetra10", "hexahedron", "wedge", "pyramid"} if family in ("SOLID", "TYPE14") else
                                  {"line"} if family in ("BEAM", "TYPE3", "TRUSS", "TYPE2") else None)
                    if compatible is None and identity[1] != refs["native_property_id"]:
                        raise PrepError("unsupported_operation", "Assignment supports SHELL and SOLID property families only.")
                    if self._projection_cache is None: self.mesh_view()
                    kinds = {cell["type"] for cell in self._projection_cache["cells"] if cell.get("part_id") == refs["native_part_id"]}
                    if compatible is not None and kinds - compatible:
                        raise PrepError("incompatible_property", "The property family does not match the part's element types.")
                    if "tetra10" in kinds:
                        try:
                            row = target_owner.render().decode("latin1").splitlines()[target_card.data[1]]
                            profile = tuple(int(row[start:start + 10].strip() or "0") for start in (10, 20, 40))
                        except (IndexError, ValueError):
                            profile = None
                        if profile != (4, 0, 1000):
                            raise PrepError("incompatible_property", "Tet10 requires explicit SOLID Ismstr=4, Iale=0 and Itetra10=1000.")
                    if family in ("BEAM", "TYPE3", "TRUSS", "TYPE2"):
                        expected = "BEAM" if family in ("BEAM", "TYPE3") else "TRUSS"
                        if any(cell.get("formulation") != expected for cell in self._projection_index["cells_by_part"].get(refs["native_part_id"], ())):
                            raise PrepError("incompatible_property", "Beam and truss sections have different native mechanical formulations.")
            state = resource.fields_state(card_id, values)
            self._validate_dependent_condition_states({resource.id:state})
            change = self.dispatcher.execute(resource.id, state, "Assign material / property",
                object_ids=(card_id,), expected_revision=expected_revision)
            return self._model_result(resource, card_id, change)

    def undo(self) -> dict:
        with self._lock:
            self._require()
            assert self.dispatcher is not None
            self.dispatcher.undo()
            return self.describe()

    def redo(self) -> dict:
        with self._lock:
            self._require()
            assert self.dispatcher is not None
            self.dispatcher.redo()
            return self.describe()

    def mesh_view(self, *, mutable: bool = False) -> dict:
        """Return shared, nested read-only geometry plus current small stamps.

        Geometry identity is stable until a structural command, Undo/Redo of
        that command, or document replacement. ``mutable=True`` explicitly
        materializes detached lists/dicts for editing or JSON serialization.
        Neither form permits mutations of the document through this view.
        """
        with self._lock:
            document = self._require()
            if self._projection_cache is None:
                nodes: dict[int, list[float]] = {}; node_resources: dict[int, list[str]] = {}; cells = []; diagnostics = []
                for resource in self._deck_resources(document):
                    projection = resource.mesh_projection()
                    for identifier, point in zip(projection["node_ids"], projection["points"]):
                        node_resources.setdefault(identifier, []).append(resource.id)
                        if identifier in nodes:
                            diagnostics.append({"severity": "warning", "code": "duplicate_global_node_id",
                                "message": f"INCLUDE 전체에서 절점 ID {identifier}가 중복돼 표시가 부분적입니다."})
                        else:
                            nodes[identifier] = point
                    cells.extend(projection["cells"]); diagnostics.extend(projection["diagnostics"])
                valid = []
                for cell in cells:
                    if all(node in nodes for node in cell["nodes"]):
                        valid.append(cell)
                    else:
                        diagnostics.append({"severity": "warning", "code": "missing_display_nodes",
                            "message": f"요소 {cell['id']}의 참조 절점이 없어 표시하지 못했습니다."})
                identifiers = sorted(nodes)
                parts = {}
                for resource in self._deck_resources(document):
                    for card in resource.cards:
                        identity = native_identity(card.keyword)
                        if identity and identity[0] == "PART":
                            parts.setdefault(identity[1], []).append((resource.id, card))
                part_refs = {identifier: readonly({"resource_id": matches[0][0], "native_scope": matches[0][1].keyword})
                             for identifier,matches in parts.items() if len(matches)==1}
                for cell in valid: cell["part_ref"] = part_refs.get(cell.get("part_id"))
                cache = freeze_mesh_payload(points=(nodes[i] for i in identifiers), node_ids=identifiers,
                    cells=valid, diagnostics=diagnostics, document_id=document.id, node_resources=node_resources)
                by_id, by_part = {}, {}
                for cell in cache["cells"]:
                    by_id[cell["id"]] = (*by_id.get(cell["id"], ()), cell)
                    by_part.setdefault(cell.get("part_id"), []).append(cell)
                self._projection_cache = cache
                self._projection_index = {"cells_by_id": by_id, "cells_by_part": by_part}
            result = {**self._projection_cache, "revision": document.revision,
                    "document_epoch": self._document_epoch, "projection_revision": self._projection_revision,
                    "resource_revisions": readonly({key: resource.state_token() for key, resource in document.resources.items()})}
            if mutable:
                result = mutable_projection(result)
                result["immutable_projection"] = False
            return result

    def _object_card(self, target: ObjectRef):
        document = self._require()
        if not isinstance(target, ObjectRef) or target.document_id != document.id or target.kind != "rad-card":
            raise PrepError("invalid_reference", "A card in the current document is required.")
        resource = document.resources.get(target.resource_id)
        if not isinstance(resource, DeckResource):
            raise PrepError("invalid_reference", "The target resource does not exist.")
        card = resource.card(target.object_id)
        if target.native_scope != card.keyword or target.mesh_revision is not None:
            raise PrepError("invalid_reference", "The card scope does not match.")
        return resource, card

    def active_object(self) -> ObjectRef | None:
        with self._lock:
            return self._active_object

    @staticmethod
    def _native_part_id(keyword):
        identity = native_identity(keyword)
        return identity[1] if identity and identity[0] == "PART" else None

    def _part_cells(self, target: ObjectRef) -> list[dict]:
        """One supported relationship: a native PART to its displayed elements."""
        _, card = self._object_card(target)
        part_id = self._native_part_id(card.keyword)
        if part_id is None:
            return []
        matching = [item for item in self.list_cards() if self._native_part_id(item["keyword"]) == part_id]
        if len(matching) != 1:
            raise PrepError("ambiguous_selection", "The PART ID is repeated across resources.")
        if self._projection_cache is None:
            self.mesh_view()
        cells = self._projection_index["cells_by_part"].get(part_id, [])
        keys = [(cell["resource_id"], cell["id"]) for cell in cells]
        if len(keys) != len(set(keys)):
            raise PrepError("ambiguous_selection", "The part contains repeated element IDs.")
        return cells

    def part_summary(self, target: ObjectRef) -> dict:
        with self._lock:
            _, card = self._object_card(target)
            part_id = self._native_part_id(card.keyword)
            if part_id is None:
                raise PrepError("invalid_reference", "A native PART is required.")
            cells = self._part_cells(target)
            return {"part_id": part_id, "element_count": len(cells)}

    def condition_targets(self, card_id):
        """Read role-specific native targets; UI code need not interpret solver IDs."""
        with self._lock:
            resource = self._find_card(card_id)
            card = resource.card(card_id)
            words = card.keyword.upper().split("/")
            root, pair = words[1], tuple(words[1:3])
            result = {"card_id": card_id, "resource_id": resource.id, "roles": [], "diagnostics": []}
            stale = self._relations_resource().snapshot()["stale_targets"]
            conditions = self._stale_conditions() if stale else []
            if card_id in stale or any(item["card_id"] == card_id for item in conditions):
                result["diagnostics"].append({"code": "stale_mesh_target", "message": "Reconnect explicit targets before displaying them as current selections."})
                return result
            if self._projection_cache is None: self.mesh_view()
            def nodes(group_id):
                self._group_reference(group_id)
                owner = self._find_card(group_id)
                identifiers = self._integer_members(owner, owner.card(group_id))
                refs = []
                for identifier in identifiers:
                    resources = self._projection_cache["node_resources"].get(identifier, [])
                    if len(resources) != 1:
                        raise PrepError("invalid_reference", "A target node is not uniquely displayable.", {"node_id": identifier})
                    refs.append(SelectionRef(resources[0], "node", identifier))
                return refs
            def elements(surface_id):
                self._surface_reference(surface_id)
                owner = self._find_card(surface_id)
                refs = []
                for identifier in self._integer_members(owner, owner.card(surface_id)):
                    part = self._native_matches("PART", identifier)[0]
                    target = ObjectRef(self.document.id, part["resource_id"], part["id"], "rad-card", part["keyword"])
                    refs.extend(SelectionRef(cell["resource_id"], "element", cell["id"]) for cell in self._part_cells(target))
                return list(dict.fromkeys(refs))
            specs = []
            try:
                if pair == ("GRNOD", "NODE"):
                    specs = [("nodes", "Group nodes", "node", nodes, card_id)]
                elif pair == ("SURF", "PART"):
                    specs = [("elements", "Surface elements", "element", elements, card_id)]
                elif pair in (("GRSH3N", "SH3N"), ("GRSHEL", "SHEL"), ("GRBRIC", "BRIC"), ("GRBEAM", "BEAM"), ("GRTRUS", "TRUS")):
                    def group_elements(group_id):
                        group = self.group_members(group_id)
                        if group["diagnostics"]:
                            raise PrepError("invalid_reference", "Element group targets cannot be resolved uniquely.", {"diagnostics": group["diagnostics"]})
                        return [SelectionRef(**item) for item in group["members"]]
                    specs = [("elements", "Group elements", "element", group_elements, card_id)]
                elif root in ("BCS", "CLOAD") or pair == ("INIVEL", "TRA"):
                    values = self.condition_values(card_id)
                    result["diagnostics"].extend(values["diagnostics"])
                    specs = [("nodes", "Target nodes", "node", nodes, values["group_id"])]
                elif pair == ("INTER", "TYPE7"):
                    values = self.condition_values(card_id)
                    result["diagnostics"].extend(values["diagnostics"])
                    specs = [("secondary_nodes", "Secondary nodes", "node", nodes, values["secondary_group_id"]),
                             ("main_elements", "Main surface", "element", elements, values["main_surface_id"])]
            except PrepError as exc:
                result["diagnostics"].append({"code": exc.code, "message": exc.message, **exc.details})
            for key, label, kind, resolver, identity in specs:
                try: refs = resolver(identity)
                except PrepError as exc:
                    refs = []
                    result["diagnostics"].append({"code": exc.code, "message": exc.message, "role": key, **exc.details})
                result["roles"].append({"key": key, "label": label, "kind": kind,
                    "ids": [ref.local_id for ref in refs], "refs": [asdict(ref) for ref in refs]})
            return result

    def _condition_selection(self, card_id, role=None):
        targets = self.condition_targets(card_id)
        choices = targets["roles"]
        selected = next((item for item in choices if item["key"] == role), None) if role is not None else (choices[0] if choices else None)
        if selected is None:
            return Selection(), None
        refs = tuple(SelectionRef(**item) for item in selected["refs"])
        return (Selection(selected["kind"], tuple(selected["ids"]), refs) if refs else Selection()), selected["key"]

    def select_condition_target(self, card_id, role):
        with self._lock:
            resource = self._find_card(card_id)
            card = resource.card(card_id)
            selection, selected_role = self._condition_selection(card_id, role)
            if selected_role is None or not selection.refs:
                raise PrepError("invalid_selection", "The requested condition target cannot be resolved for display.",
                                {"role": role, "diagnostics": self.condition_targets(card_id)["diagnostics"]})
            target = ObjectRef(self.document.id, resource.id, card.id, "rad-card", card.keyword)
            self._active_object, self._selected_objects = target, (target,)
            self._active_target_role = selected_role
            self.document.selection = selection
            self._notify("selection")
            return self.selection()

    def activate_object(self, target: ObjectRef | None) -> dict:
        with self._lock:
            document = self._require()
            cells = []
            if target is not None:
                self._object_card(target)
                cells = self._part_cells(target)
            selection = Selection("element", tuple(cell["id"] for cell in cells),
                tuple(SelectionRef(cell["resource_id"], "element", cell["id"]) for cell in cells)) if cells else Selection()
            active_role = None
            if target is not None and not cells:
                selection, active_role = self._condition_selection(target.object_id)
            self._active_object = target
            self._selected_objects = (target,) if target is not None else ()
            self._active_target_role = active_role
            document.selection = selection
            self._notify("selection")
            return self.selection()

    def selected_objects(self):
        with self._lock:
            return self._selected_objects

    def select_objects(self, refs, active=None):
        """Select existing PARTs together, with one separately specified active object.

        Every reference is validated before selection changes. One notification
        contains the canonical union of element refs across all selected PARTs.
        """
        with self._lock:
            document = self._require()
            if not isinstance(refs, (tuple, list)):
                raise PrepError("invalid_selection", "Provide a sequence of PART references.")
            normalized, cells = [], []
            for ref in refs:
                _, card = self._object_card(ref)
                if self._native_part_id(card.keyword) is None:
                    raise PrepError("unsupported_selection", "Multiple-object selection currently supports PARTs only.")
                if ref not in normalized:
                    normalized.append(ref)
                    cells.extend(self._part_cells(ref))
            if active is not None and active not in normalized:
                raise PrepError("invalid_selection", "The active PART must belong to the selected objects.")
            entity_refs = tuple(dict.fromkeys(SelectionRef(cell["resource_id"], "element", cell["id"]) for cell in cells))
            selection = Selection("element", tuple(ref.local_id for ref in entity_refs), entity_refs) if entity_refs else Selection()
            self._selected_objects = tuple(normalized)
            self._active_target_role = None
            self._active_object = active
            document.selection = selection
            self._notify("selection")
            return self.selection()

    def select_pick(self, candidate: dict) -> dict:
        """A transient renderer candidate must match the exact displayed projection."""
        with self._lock:
            document = self._require()
            if (not isinstance(candidate, dict) or candidate.get("document_id") != document.id
                    or candidate.get("document_epoch") != self._document_epoch
                    or type(candidate.get("revision")) is not int or candidate["revision"] != document.revision
                    or type(candidate.get("projection_revision")) is not int
                    or candidate["projection_revision"] != self._projection_revision):
                raise PrepError("stale_pick", "The displayed document or projection has changed. Pick again.")
            kind = candidate.get("kind")
            if kind is None:
                return self.clear_selection()
            if kind not in ("node", "element") or type(candidate.get("id")) is not int:
                raise PrepError("invalid_selection", "A node/element and integer native ID are required.")
            resource_id = candidate.get("resource_id")
            resource = document.resources.get(resource_id) if isinstance(resource_id, str) else None
            if resource is None or candidate.get("resource_revision") != resource.state_token():
                raise PrepError("stale_pick", "The displayed resource has changed. Pick again.")
            entity_id = candidate.get("id")
            if self._projection_cache is None:
                self.mesh_view()
            resources = self._projection_cache["node_resources"].get(entity_id, ()) if kind == "node" else [
                cell["resource_id"] for cell in self._projection_index["cells_by_id"].get(entity_id, ())]
            if resource_id not in resources:
                raise PrepError("invalid_selection", "The entity does not belong to the displayed resource.")
            return self.select_entity(kind, entity_id)

    def select_entity(self, kind: str, entity_id: int) -> dict:
        with self._lock:
            document = self._require()
            if kind not in ("node", "element") or type(entity_id) is not int:
                raise PrepError("invalid_selection", "선택에는 node/element와 정수 원본 ID가 필요합니다.")
            if self._projection_cache is None: self.mesh_view()
            resources = self._projection_cache["node_resources"].get(entity_id, ()) if kind == "node" else [c["resource_id"] for c in self._projection_index["cells_by_id"].get(entity_id, ())]
            if isinstance(entity_id, bool) or not resources:
                raise PrepError("invalid_selection", "선택한 모델 객체를 찾을 수 없습니다.", {"kind": kind, "id": entity_id})
            if len(resources) != 1:
                raise PrepError("ambiguous_selection", "여러 자원에 같은 ID가 있어 선택 대상을 확정할 수 없습니다.", {"kind": kind, "id": entity_id})
            document.selection = Selection(kind, (int(entity_id),), (SelectionRef(resources[0], kind, int(entity_id)),))
            self._active_object = None
            self._active_target_role = None
            if kind == "element":
                cell = self._projection_index["cells_by_id"][entity_id][0]
                parts = [item for item in self.list_cards() if self._native_part_id(item["keyword"]) == cell.get("part_id")]
                if len(parts) == 1:
                    card = parts[0]
                    self._active_object = ObjectRef(document.id, card["resource_id"], card["id"], "rad-card", card["keyword"])
            self._selected_objects = (self._active_object,) if self._active_object is not None else ()
            self._notify("selection")
            return self.selection()

    def clear_selection(self) -> dict:
        with self._lock:
            self._require().selection = Selection()
            self._active_object = None
            self._selected_objects = ()
            self._active_target_role = None
            self._notify("selection")
            return self.selection()

    def selection(self) -> dict:
        with self._lock:
            document = self._require()
            return {"kind": document.selection.kind, "ids": list(document.selection.ids),
                    "document_id": document.id, "revision": document.revision,
                    "document_epoch": self._document_epoch, "projection_revision": self._projection_revision,
                    "resource_revisions": {key: resource.state_token() for key, resource in document.resources.items()},
                    "active_object": asdict(self._active_object) if self._active_object else None,
                    "active_target_role": self._active_target_role,
                    "selected_objects": [asdict(ref) for ref in self._selected_objects],
                    "refs": [{"resource_id": r.resource_id, "entity_kind": r.entity_kind, "local_id": r.local_id}
                             for r in document.selection.refs]}

    def _protected(self, target: Path) -> bool:
        return str(target.resolve()) in self._source_paths or any(
            target.exists() and Path(source).exists() and target.samefile(source) for source in self._source_paths)

    @_file_boundary
    def save_project(self, path: str) -> dict:
        with self._lock:
            document = self._require(); target = Path(path).expanduser().resolve()
            if self._protected(target):
                raise PrepError("source_overwrite", "원본 입력 파일에 작업 문서를 덮어쓸 수 없습니다.")
            collisions = self._path_collisions(self._paths)
            if collisions:
                raise PrepError("project_path_collision", "대소문자만 다른 경로를 작업 문서에 함께 저장할 수 없습니다.", {"paths": collisions})
            target.parent.mkdir(parents=True, exist_ok=True)
            if any(not isinstance(resource, (DeckResource, AnalysisCasesResource, SourceArchiveResource, ModelRelationsResource)) for resource in document.resources.values()):
                raise PrepError("unsupported_project_resource", "A resource has no registered native-project codec; nothing was saved.")
            sources = [r for r in document.resources.values() if isinstance(r, SourceArchiveResource)]
            manifest = {"format": PROJECT_FORMAT, "version": PROJECT_VERSION, "document_id": document.id,
                        "name": document.name, "revision": document.revision, "root_id": self._root_id,
                        "source_paths": sorted(self._source_paths), "diagnostics": self._diagnostics,
                        "resources": [{"id": r.id, "kind": r.kind, "name": r.name,
                            "logical_path": self._paths[r.id], "raw_member": f"raw/{r.id}.rad",
                            "state": r.snapshot()} for r in self._deck_resources(document)],
                        "analysis_cases": self._cases_resource().snapshot(),
                        "source_models": [resource.manifest() for resource in sources],
                        "model_relations": self._relations_resource().snapshot()}
            try:
                members = {f"raw/{resource.id}.rad": resource.raw for resource in self._deck_resources(document)}
                members.update({f"sources/{resource.id}/{original_id}.rad": raw
                                for resource in sources for original_id, raw in resource.files.items()})
                write_container(target, manifest, members)
            except (OSError, zipfile.BadZipFile) as exc:
                raise PrepError("project_write_error", "작업 문서를 저장하지 못했습니다.", {"reason": str(exc)}) from exc
            document.mark_saved(str(target))
            self._notify("save")
            return {**self.describe(), "saved_path": str(target)}

    @_file_boundary
    def open_project(self, path: str) -> dict:
        with self._lock:
            source = Path(path).expanduser().resolve()
            try:
                with zipfile.ZipFile(source) as archive:
                    if len(archive.infolist()) > 10000 or sum(i.file_size for i in archive.infolist()) > 2 * 1024**3:
                        raise PrepError("project_too_large", "작업 문서의 자원 크기 제한을 초과했습니다.")
                    if len(archive.namelist()) != len(set(archive.namelist())):
                        raise ValueError("duplicate ZIP member")
                    manifest = json.loads(archive.read("manifest.json"))
                    if not isinstance(manifest, dict):
                        raise PrepError("invalid_project", "작업 문서의 manifest는 객체여야 합니다.")
                    if manifest.get("format") != PROJECT_FORMAT or type(manifest.get("version")) is not int or manifest.get("version") not in (1, 2, 3, 4, 5, PROJECT_VERSION):
                        raise PrepError("project_version", "지원하지 않는 작업 문서 형식/버전입니다.")
                    if not isinstance(manifest["document_id"], str): raise ValueError("invalid document ID")
                    UUID(manifest["document_id"])
                    if type(manifest["revision"]) is not int or manifest["revision"] < 0: raise ValueError("invalid revision")
                    if not isinstance(manifest["name"], str) or not isinstance(manifest["root_id"], str): raise ValueError("invalid document metadata")
                    if not isinstance(manifest["resources"], list): raise ValueError("invalid resources")
                    document = Document(str(manifest["name"]), id=manifest["document_id"], revision=manifest["revision"])
                    paths = {}; path_keys = set()
                    for item in manifest["resources"]:
                        if not isinstance(item, dict): raise ValueError("invalid resource metadata")
                        if not all(isinstance(item[field], str) for field in ("id", "kind", "name", "logical_path", "raw_member")):
                            raise ValueError("invalid resource metadata type")
                        if item["kind"] != "radioss-deck": raise ValueError("unknown resource kind")
                        UUID(item["id"])
                        logical = self._include_relative(item["logical_path"]).as_posix()
                        if logical.casefold() in path_keys or item["id"] in document.resources: raise ValueError("duplicate resource")
                        path_keys.add(logical.casefold())
                        member = f"raw/{item['id']}.rad"
                        if item["raw_member"] != member: raise ValueError("invalid raw member")
                        resource = DeckResource(archive.read(member), resource_id=item["id"], name=item["name"],
                                                is_include=item["id"] != manifest["root_id"])
                        resource.restore(item["patches"] if manifest["version"] == 1 else item["state"])
                        document.resources[resource.id] = resource; paths[resource.id] = logical
                    if manifest["root_id"] not in document.resources: raise ValueError("missing root resource")
                    if manifest["version"] >= 4:
                        # The first v4 checkpoint stored independent source
                        # archives before prepared-mesh/instance relationships.
                        # Its absent registry means empty; v5 requires it. A
                        # present v4 registry is still validated, never ignored.
                        relation_state = manifest["model_relations"] if manifest["version"] >= 5 else manifest.get("model_relations")
                        if "model_relations" in manifest and not isinstance(relation_state, dict):
                            raise ValueError("invalid model relation registry")
                        relations = ModelRelationsResource(document.id, relation_state)
                        if relations.id in document.resources: raise ValueError("relation resource identity collision")
                        for rid in relations.snapshot()["mesh_revisions"]:
                            if rid not in paths: raise ValueError("relation mesh resource is missing")
                        for card_id, record in relations.snapshot()["stale_targets"].items():
                            owner = document.resources.get(record["resource_id"])
                            if not isinstance(owner, DeckResource) or card_id not in owner._by_id or record["mesh_resource_id"] not in paths:
                                raise ValueError("stale relation target does not exist")
                            if any(rid not in paths for rid in record.get("mesh_dependencies", {})):
                                raise ValueError("stale mesh dependency does not exist")
                        document.resources[relations.id] = relations
                        if not isinstance(manifest["source_models"], list): raise ValueError("invalid source model registry")
                        owned = set()
                        for metadata in manifest["source_models"]:
                            source_id = metadata["id"]; UUID(source_id)
                            files = {item["original_resource_id"]: archive.read(f"sources/{source_id}/{item['original_resource_id']}.rad")
                                     for item in metadata["files"]}
                            source_resource = SourceArchiveResource(metadata, files)
                            if source_resource.id in document.resources: raise ValueError("duplicate source identity")
                            for item in metadata["files"]:
                                rid = item["resource_id"]
                                if rid == manifest["root_id"] or rid in owned or rid not in paths or paths[rid] != item["logical_path"]:
                                    raise ValueError("invalid mapped resource ownership")
                                self._include_relative(item["original_path"])
                                if not paths[rid].startswith(f"sources/{source_id}/"):
                                    raise ValueError("source path escapes its namespace")
                                owned.add(rid)
                            document.resources[source_resource.id] = source_resource
                        for source_resource in document.resources.values():
                            if isinstance(source_resource, SourceArchiveResource):
                                source_resource.validate_mapped_payloads(document)
                        self._validate_instance_references(document, manifest["root_id"], relations.snapshot()["instances"])
                    if not isinstance(manifest.get("source_paths", []), list) or not all(isinstance(p, str) for p in manifest.get("source_paths", [])):
                        raise ValueError("invalid source path metadata")
                    diagnostics = self._project_include_diagnostics(document, paths, manifest["root_id"])
                    if manifest["version"] >= 3:
                        cases = AnalysisCasesResource(document.id, manifest["analysis_cases"])
                        if cases.id in document.resources:
                            raise ValueError("analysis case resource identity collision")
                        cards = {card.id: card for resource in self._deck_resources(document) for card in resource.cards}
                        for case in cases.snapshot()["cases"]:
                            for identity in case["condition_ids"]:
                                if identity not in cards or condition_kind(cards[identity].keyword) is None:
                                    raise PrepError("invalid_project", "An analysis case references a missing or unsupported condition.", {"case_id": case["id"], "card_id": identity})
                        document.resources[cases.id] = cases
                    document.mark_saved(str(source))
                    self._install(document, manifest["root_id"], paths, set(manifest.get("source_paths", [])), diagnostics)
            except PrepError:
                raise
            except (OSError, zipfile.BadZipFile, KeyError, TypeError, ValueError, UnicodeError) as exc:
                raise PrepError("invalid_project", "작업 문서를 읽지 못했습니다.", {"reason": str(exc)}) from exc
            result = self.describe()
            self._notify("document")
            return result

    def _project_include_diagnostics(self, document: Document, paths: dict[str, str], root_id: str) -> list[dict]:
        """Rebuild the include graph; serialized diagnostics are not trusted state."""
        by_path = {value: key for key, value in paths.items()}
        reached = set()
        diagnostics = []

        def visit(resource_id: str, chain: tuple[str, ...]):
            if resource_id in reached: return
            reached.add(resource_id)
            resource = document.resources[resource_id]
            for reference in resource.includes():
                try:
                    logical = self._include_relative(reference["path"]).as_posix()
                    if logical not in by_path:
                        raise PrepError("include_missing", "작업 문서에 INCLUDE 자원이 없습니다.", {"path": logical})
                    target = by_path[logical]
                    if target in chain + (resource_id,):
                        raise PrepError("include_cycle", "순환 INCLUDE를 발견했습니다.")
                    visit(target, chain + (resource_id,))
                except PrepError as exc:
                    diagnostics.append({"severity": "warning", "code": exc.code, "message": exc.message,
                        "unresolved_include": True, "resource_id": resource_id, **reference})

        visit(root_id, ())
        for source_root in self._source_roots(document):
            visit(source_root, (root_id,))
        if reached != set(paths):
            raise PrepError("invalid_project", "루트 입력에서 참조하지 않는 자원이 작업 문서에 있습니다.")
        return diagnostics

    def _rad_outputs(self, target, inactive_condition_ids=()):
        document = self._require()
        self._require_expanded_instances()
        stale = self._relations_resource().snapshot()["stale_targets"]
        if stale:
            raise PrepError("stale_mesh_targets", "Reconnect the explicit mesh targets before native export; same-number nodes are not a correspondence.", {"targets": stale})
        if any(d.get("unresolved_include") for d in self._diagnostics):
            raise PrepError("unresolved_include", "미해결 INCLUDE가 있어 독립 입력 파일을 내보낼 수 없습니다.",
                            {"diagnostics": self._diagnostics})
        if document.save_state.path and target == Path(document.save_state.path):
            raise PrepError("project_overwrite", "작업 문서를 솔버 입력으로 덮어쓸 수 없습니다.")
        outputs = []
        targets = set()
        for resource in self._deck_resources(document):
            destination = target if resource.id == self._root_id else target.parent / self._paths[resource.id]
            destination = destination.resolve()
            if self._protected(destination):
                raise PrepError("source_overwrite", "원본 입력 파일을 덮어쓰지 않습니다. 새 경로를 선택해 주세요.", {"path": str(destination)})
            key = str(destination).casefold()
            if key in targets: raise PrepError("export_path_collision", "출력 파일 경로가 충돌합니다.")
            targets.add(key)
            excluded = [identity for identity in inactive_condition_ids if identity in resource._by_id]
            payload = resource.render()
            if resource.id == self._root_id and self._source_roots():
                text = payload.decode("latin1").splitlines(keepends=True)
                end = next((index for index, line in enumerate(text) if line.strip().upper() == "/END"), None)
                if end is None: raise PrepError("invalid_deck", "Assembly export requires an explicit root /END.")
                text[end:end] = [f"#include {self._paths[rid]}{resource.newline}" for rid in self._source_roots()]
                payload = "".join(text).encode("latin1")
            if excluded:
                # INCLUDE directives are comments in the block layout. Retain
                # them and all comments, even when they follow an omitted card.
                omitted = {index for identity in excluded for index in
                           (resource.card(identity).start, *resource.card(identity).data)}
                payload = "".join(line for index, line in enumerate(payload.decode("latin1").splitlines(keepends=True))
                                  if index not in omitted).encode("latin1")
            if resource.id != self._root_id and destination.exists() and destination.read_bytes() != payload:
                raise PrepError("include_output_collision", "기존 INCLUDE 출력과 내용이 다릅니다. 빈 출력 폴더를 선택해 주세요.", {"path": str(destination)})
            outputs.append((destination, payload))
        return outputs

    @staticmethod
    def _write_output_batch(outputs):
        staged = []; backups = {}
        try:
            for destination, payload in outputs:
                destination.parent.mkdir(parents=True, exist_ok=True)
                backups[destination] = destination.read_bytes() if destination.exists() else None
                fd, temporary = tempfile.mkstemp(prefix=".rad-", dir=destination.parent)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload); stream.flush(); os.fsync(stream.fileno())
                staged.append((destination, temporary))
            committed = []
            try:
                for destination, temporary in staged:
                    os.replace(temporary, destination); committed.append(destination)
            except OSError:
                for destination in reversed(committed):
                    previous = backups[destination]
                    if previous is None: destination.unlink(missing_ok=True)
                    else: destination.write_bytes(previous)
                raise
        except OSError as exc:
            raise PrepError("export_write_error", "솔버 입력을 내보내지 못했습니다.", {"reason": str(exc)}) from exc
        finally:
            for _, temporary in staged:
                if os.path.exists(temporary): os.unlink(temporary)

    @_file_boundary
    def export_rad(self, path: str) -> dict:
        with self._lock:
            document = self._require()
            target = Path(path).expanduser().resolve()
            outputs = self._rad_outputs(target)
            self._write_output_batch(outputs)
            return {"path": str(target), "files": [str(p) for p, _ in outputs],
                    "document_id": document.id, "revision": document.revision,
                    "diagnostics": self.diagnostics(), "engine_companion": "not generated or rewritten"}

    @_file_boundary
    def export_solver_inputs(self, path, end_time, output_interval, *, _inactive_condition_ids=()):
        """Export preserved Starter inputs and a separately generated Engine deck."""
        with self._lock:
            document = self._require()
            target = Path(path).expanduser().resolve()
            if not target.name.endswith("_0000.rad"):
                raise PrepError("invalid_export_name", "Choose a Starter filename ending in _0000.rad.")
            run_name = target.name[:-9]
            engine = target.with_name(run_name + "_0001.rad")
            engine_bytes = engine_input(run_name, end_time, output_interval)
            outputs = self._rad_outputs(target, _inactive_condition_ids)
            if self._protected(engine) or (document.save_state.path and engine == Path(document.save_state.path)):
                raise PrepError("source_overwrite", "Choose a new directory for generated solver inputs.")
            if str(engine).casefold() in {str(destination).casefold() for destination, _ in outputs}:
                raise PrepError("export_path_collision", "Engine filename conflicts with an INCLUDE output.")
            root = self._model_resource(None)
            units = self._solver_work_units()
            # Native export preserves raw files. Run export can add the mandatory
            # solver header to its OUTPUT only, without changing the document.
            added_header = False
            for index, (destination, payload) in enumerate(outputs):
                if destination == target and not payload.startswith(b"#RADIOSS STARTER"):
                    outputs[index] = (destination, b"#RADIOSS STARTER" + root.newline.encode() + payload)
                    added_header = True
            outputs.append((engine, engine_bytes))
            self._write_output_batch(outputs)
            return {"path": str(target), "starter_path": str(target), "engine_path": str(engine),
                    "files": [str(destination) for destination, _ in outputs], "document_id": document.id,
                    "revision": document.revision, "units": units, "added_starter_header": added_header,
                    "end_time": float(end_time), "output_interval": float(output_interval),
                    "diagnostics": self.diagnostics(), "engine_companion": "generated explicit run and animation interval"}

    def _solver_work_units(self):
        root = self._model_resource(None)
        begin = next((card for card in root.cards if card.keyword.upper() == "/BEGIN"), None)
        tokens = root.lines[begin.data[3]].split() if begin is not None and len(begin.data) >= 4 else []
        if len(tokens) != 3:
            raise PrepError("invalid_units", "Declare the second BEGIN unit row explicitly; Engine times use working units, not inferred input units.")
        units = dict(zip(("mass", "length", "time"), tokens))
        if units["time"] not in ("s", "ms", "mus"):
            raise PrepError("invalid_units", "The declared working time unit is outside the supported solver export profile.")
        return units
