"""One document owner and command path for the desktop UI and automation."""
from __future__ import annotations

import json
from copy import deepcopy
import os
from pathlib import Path, PurePosixPath
import tempfile
from threading import RLock
from uuid import UUID
import zipfile
from functools import wraps

from ..cae_core import CommandDispatcher, Document, PrepError, Selection, SelectionRef
from ..radioss import DeckResource


PROJECT_FORMAT = "caelab-prep-project"
PROJECT_VERSION = 1


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


class PrepSession:
    def __init__(self):
        self._lock = RLock()
        self.document: Document | None = None
        self.dispatcher: CommandDispatcher | None = None
        self._root_id: str | None = None
        self._paths: dict[str, str] = {}
        self._source_paths: set[str] = set()
        self._diagnostics: list[dict] = []
        self._projection_cache: dict | None = None
        self._source_path: str | None = None
        self._listeners = []

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
                 "revision": self.document.revision if self.document else 0, **details}
        for listener in tuple(self._listeners):
            try:
                listener(dict(event))
            except Exception:
                continue

    def _require(self) -> Document:
        if self.document is None:
            raise PrepError("no_document", "먼저 Radioss 덱이나 작업 문서를 열어 주세요.")
        return self.document

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
        self.document = document
        self.dispatcher = CommandDispatcher(document)
        self.dispatcher.subscribe(lambda change: self._notify(change.kind, change=change.to_dict()))
        self._root_id = root_id
        self._paths = paths
        self._source_paths = source_paths
        self._diagnostics = diagnostics
        self._projection_cache = None
        self._source_path = source_path

    @staticmethod
    def _path_collisions(paths: dict[str, str]) -> list[list[str]]:
        grouped: dict[str, list[str]] = {}
        for path in paths.values(): grouped.setdefault(path.casefold(), []).append(path)
        return [group for group in grouped.values() if len(group) > 1]

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
                        "project_path": None, "last_change": None}
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
                    "last_change": self.dispatcher.last_change.to_dict() if self.dispatcher.last_change else None}

    @staticmethod
    def capabilities() -> dict:
        return {"radioss_raw_preservation": True, "project_format": PROJECT_FORMAT,
                "project_version": PROJECT_VERSION, "material_edit": ["LAW1/ELAST", "LAW36/PLAS_TAB"],
                "constraint_edit": ["BCS"], "contact_edit": ["INTER/TYPE24 friction"],
                "curve_edit": ["FUNCT existing points"], "initial_velocity_edit": ["INIVEL/TRA"],
                "shell_edit": ["PROP/SHELL thickness"], "create_cards": False,
                "cad_import": False, "meshing": False, "solver_execution": False,
                "projection_only": True, "include_base": "root-deck-working-directory",
                "unsupported_cards": "read-only, original bytes preserved"}

    def diagnostics(self) -> list[dict]:
        with self._lock:
            document = self._require()
            result = list(self._diagnostics)
            for resource in document.resources.values(): result.extend(resource.diagnostics)
            if self._projection_cache is None: self.mesh_view()
            result.extend(self._projection_cache.get("diagnostics", []))
            # Diagnostics can contain export guards; never expose their internal objects.
            return deepcopy(result)

    def list_cards(self) -> list[dict]:
        with self._lock:
            document = self._require()
            return [card for resource in document.resources.values() for card in resource.list_cards()]

    def _find_card(self, card_id: str) -> DeckResource:
        for resource in self._require().resources.values():
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
        with self._lock:
            if expected_revision is not None and (type(expected_revision) is not int or expected_revision != self._require().revision):
                raise PrepError("revision_conflict", "모델이 변경됐습니다. 현재 값을 다시 읽어 주세요.",
                                {"expected": expected_revision, "actual": self._require().revision})
            resource = self._find_card(card_id)
            state = resource.patched_state(card_id, field_name, value)
            assert self.dispatcher is not None
            self.dispatcher.execute(resource.id, state, f"{resource.card(card_id).keyword}: {field_name}",
                                    object_ids=(card_id,), expected_revision=expected_revision)
            return self.describe()

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

    def mesh_view(self) -> dict:
        with self._lock:
            document = self._require()
            if self._projection_cache is None:
                nodes: dict[int, list[float]] = {}; node_resources: dict[int, list[str]] = {}; cells = []; diagnostics = []
                for resource in document.resources.values():
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
                self._projection_cache = {"points": [nodes[i] for i in identifiers], "node_ids": identifiers,
                    "cells": valid, "diagnostics": diagnostics, "immutable_projection": True,
                    "document_id": document.id, "node_resources": node_resources}
            # The caller may render or serialize this projection, never mutate the model through it.
            return {"points": [list(p) for p in self._projection_cache["points"]],
                    "node_ids": list(self._projection_cache["node_ids"]),
                    "cells": [{**c, "nodes": list(c["nodes"])} for c in self._projection_cache["cells"]],
                    "diagnostics": [dict(d) for d in self._projection_cache["diagnostics"]],
                    "immutable_projection": True, "document_id": document.id, "revision": document.revision}

    def select_entity(self, kind: str, entity_id: int) -> dict:
        with self._lock:
            document = self._require()
            if kind not in ("node", "element") or type(entity_id) is not int:
                raise PrepError("invalid_selection", "선택에는 node/element와 정수 원본 ID가 필요합니다.")
            if self._projection_cache is None: self.mesh_view()
            resources = self._projection_cache["node_resources"].get(entity_id, []) if kind == "node" else [c["resource_id"] for c in self._projection_cache["cells"] if c["id"] == entity_id]
            if isinstance(entity_id, bool) or not resources:
                raise PrepError("invalid_selection", "선택한 모델 객체를 찾을 수 없습니다.", {"kind": kind, "id": entity_id})
            if len(resources) != 1:
                raise PrepError("ambiguous_selection", "여러 자원에 같은 ID가 있어 선택 대상을 확정할 수 없습니다.", {"kind": kind, "id": entity_id})
            document.selection = Selection(kind, (int(entity_id),), (SelectionRef(resources[0], kind, int(entity_id)),))
            self._notify("selection")
            return self.selection()

    def clear_selection(self) -> dict:
        with self._lock:
            self._require().selection = Selection()
            self._notify("selection")
            return self.selection()

    def selection(self) -> dict:
        with self._lock:
            document = self._require()
            return {"kind": document.selection.kind, "ids": list(document.selection.ids),
                    "document_id": document.id, "revision": document.revision,
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
            manifest = {"format": PROJECT_FORMAT, "version": PROJECT_VERSION, "document_id": document.id,
                        "name": document.name, "revision": document.revision, "root_id": self._root_id,
                        "source_paths": sorted(self._source_paths), "diagnostics": self._diagnostics,
                        "resources": [{"id": r.id, "kind": r.kind, "name": r.name,
                            "logical_path": self._paths[r.id], "raw_member": f"raw/{r.id}.rad",
                            "patches": r.snapshot()} for r in document.resources.values()]}
            fd, temp = tempfile.mkstemp(prefix=".caeprep-", dir=target.parent)
            os.close(fd)
            try:
                with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                    for resource in document.resources.values():
                        archive.writestr(f"raw/{resource.id}.rad", resource.raw)
                with open(temp, "rb") as stream:
                    os.fsync(stream.fileno())
                os.replace(temp, target)
            except (OSError, zipfile.BadZipFile) as exc:
                raise PrepError("project_write_error", "작업 문서를 저장하지 못했습니다.", {"reason": str(exc)}) from exc
            finally:
                if os.path.exists(temp): os.unlink(temp)
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
                    if manifest.get("format") != PROJECT_FORMAT or type(manifest.get("version")) is not int or manifest.get("version") != PROJECT_VERSION:
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
                        resource.restore(item["patches"])
                        document.resources[resource.id] = resource; paths[resource.id] = logical
                    if manifest["root_id"] not in document.resources: raise ValueError("missing root resource")
                    if not isinstance(manifest.get("source_paths", []), list) or not all(isinstance(p, str) for p in manifest.get("source_paths", [])):
                        raise ValueError("invalid source path metadata")
                    diagnostics = self._project_include_diagnostics(document, paths, manifest["root_id"])
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
        if reached != set(document.resources):
            raise PrepError("invalid_project", "루트 입력에서 참조하지 않는 자원이 작업 문서에 있습니다.")
        return diagnostics

    @_file_boundary
    def export_rad(self, path: str) -> dict:
        with self._lock:
            document = self._require(); target = Path(path).expanduser().resolve()
            if any(d.get("unresolved_include") for d in self._diagnostics):
                raise PrepError("unresolved_include", "미해결 INCLUDE가 있어 독립 입력 파일을 내보낼 수 없습니다.",
                                {"diagnostics": self._diagnostics})
            if document.save_state.path and target == Path(document.save_state.path):
                raise PrepError("project_overwrite", "작업 문서를 솔버 입력으로 덮어쓸 수 없습니다.")
            outputs = []
            targets = set()
            for resource in document.resources.values():
                destination = target if resource.id == self._root_id else target.parent / self._paths[resource.id]
                destination = destination.resolve()
                if self._protected(destination):
                    raise PrepError("source_overwrite", "원본 입력 파일을 덮어쓰지 않습니다. 새 경로를 선택해 주세요.", {"path": str(destination)})
                key = str(destination).casefold()
                if key in targets: raise PrepError("export_path_collision", "출력 파일 경로가 충돌합니다.")
                targets.add(key)
                payload = resource.render()
                if resource.id != self._root_id and destination.exists() and destination.read_bytes() != payload:
                    raise PrepError("include_output_collision", "기존 INCLUDE 출력과 내용이 다릅니다. 빈 출력 폴더를 선택해 주세요.", {"path": str(destination)})
                outputs.append((destination, payload))
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
            return {"path": str(target), "files": [str(p) for p, _ in outputs],
                    "document_id": document.id, "revision": document.revision,
                    "diagnostics": self.diagnostics(), "engine_companion": "not generated or rewritten"}
