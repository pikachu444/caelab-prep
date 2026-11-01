"""Conservative Radioss block reader: original bytes remain the authority.

Only explicitly described fields are writable. Unrecognized cards, comments,
line endings, ordering, and unedited fields are never reformatted.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import copy
import hashlib
import json
import math
import re
from uuid import UUID, uuid4, uuid5

from ..cae_core.errors import PrepError


def number(value: str) -> float:
    return float(value.replace("D", "E").replace("d", "e"))


@dataclass(frozen=True)
class Card:
    id: str
    keyword: str
    start: int
    stop: int
    data: tuple[int, ...]
    title: str
    category: str


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: str
    line: int
    start: int
    stop: int
    minimum: float | None = None
    maximum: float | None = None
    strict_minimum: bool = False
    strict_maximum: bool = False


class DeckResource:
    kind = "radioss-deck"

    def __init__(self, raw: bytes, *, resource_id: str | None = None, name: str = "model_0000.rad",
                 is_include: bool = False):
        self.id = resource_id or str(uuid4())
        UUID(self.id)
        self.raw = bytes(raw)
        self._raw_digest = hashlib.sha256(self.raw).digest()
        self.name = name
        self.is_include = is_include
        self._patches: dict[str, dict[str, object]] = {}
        self._created: list[dict[str, str]] = []
        self._deleted: set[str] = set()
        self._replaced: dict[str, str] = {}
        self._state_token_cache = None
        self._source_lines = self.raw.decode("latin1").splitlines(keepends=True)
        self._parse_layout(self._source_lines)
        self._source_cards = tuple(self.cards)
        self._source_active_stop = self.active_stop
        if not self.cards and not is_include:
            raise PrepError("invalid_deck", "Radioss 블록 카드가 없는 파일입니다.", {"name": name})

    def _parse_layout(self, lines, card_ids=None):
        """Build the editing projection; explicit identities survive structural edits."""
        self.lines = list(lines)
        self.active_stop = next((i for i, line in enumerate(self.lines)
                                 if self.is_include and re.match(r"^\s*#enddata\b", line, re.I)), len(self.lines))
        starts = [i for i, line in enumerate(self.lines[:self.active_stop]) if line.startswith("/")]
        if card_ids is not None and len(card_ids) != len(starts):
            raise PrepError("invalid_project", "Card identity count does not match the deck layout.")
        self.cards, self.diagnostics = [], []
        for ordinal, start in enumerate(starts):
            stop = starts[ordinal + 1] if ordinal + 1 < len(starts) else self.active_stop
            keyword = self.lines[start].strip()
            data = tuple(i for i in range(start + 1, stop)
                         if self.lines[i].strip() and not self.lines[i].lstrip().startswith("#"))
            category = self._category(keyword)
            title = self.lines[data[0]].strip() if data and category not in ("Nodes", "Elements") else ""
            try:
                title = title.encode("latin1").decode("utf-8")
            except UnicodeError:
                pass
            identity = card_ids[ordinal] if card_ids is not None else str(uuid5(UUID(self.id), str(ordinal) + ":" + keyword))
            self.cards.append(Card(identity, keyword, start, stop, data, title, category))
        self._by_id = {card.id: card for card in self.cards}
        for card in self.cards:
            if card.keyword.upper().startswith("/TRANSFORM"):
                self.diagnostics.append({"severity": "warning", "code": "display_transform_not_applied",
                    "message": "변환 카드는 원문으로 보존합니다. 3D 표시는 변환 전 좌표일 수 있습니다.", "card_id": card.id})
            if card.keyword.upper().startswith("/BCS/") and not self._schema(card):
                self.diagnostics.append({"severity": "warning", "code": "bcs_layout_not_editable",
                    "message": "구속 카드의 고정 폭을 해석하지 못했습니다. 원문을 보존하며 편집하지 않습니다.", "card_id": card.id})

    @property
    def newline(self):
        for line in self._source_lines:
            if line.endswith("\r\n"): return "\r\n"
            if line.endswith("\n"): return "\n"
            if line.endswith("\r"): return "\r"
        return "\n"

    def _rebuild_layout(self):
        """Retain original spans, inserting new blocks before /END or #enddata."""
        first = self._source_cards[0].start if self._source_cards else self._source_active_stop
        chunks = ["".join(self._source_lines[:first])]
        identities, inserted = [], False
        def insert():
            nonlocal inserted
            if self._created and chunks and chunks[-1] and not chunks[-1].endswith(("\n", "\r")):
                chunks.append(self.newline)
            for item in self._created:
                chunks.append(item["text"])
                identities.append(item["id"])
            inserted = True
        for card in self._source_cards:
            if card.keyword.upper() == "/END" and not inserted:
                insert()
            if card.id not in self._deleted:
                chunks.append(self._replaced.get(card.id, "".join(self._source_lines[card.start:card.stop])))
                identities.append(card.id)
        if not inserted: insert()
        chunks.append("".join(self._source_lines[self._source_active_stop:]))
        self._parse_layout("".join(chunks).splitlines(keepends=True), identities)

    @staticmethod
    def _category(keyword: str) -> str:
        root = keyword.upper().split("/")[1]
        return {"NODE": "Nodes", "SHELL": "Elements", "SH3N": "Elements", "BRICK": "Elements",
                "TETRA4": "Elements", "TETRA": "Elements", "BEAM": "Elements", "TRUSS": "Elements",
                "MAT": "Materials", "PROP": "Properties", "PART": "Parts", "BCS": "Constraints",
                "INTER": "Contacts", "FUNCT": "Curves", "GRNOD": "Groups", "SURF": "Groups",
                "PLOAD": "Loads", "CLOAD": "Loads", "INIVEL": "Initial conditions"}.get(root, "Other cards")

    def card(self, card_id: str) -> Card:
        try:
            return self._by_id[card_id]
        except KeyError:
            raise PrepError("card_not_found", "카드를 찾을 수 없습니다.", {"card_id": card_id}) from None

    def _schema(self, card: Card) -> list[Field]:
        key = card.keyword.upper().split("/")
        data = card.data
        fields: list[Field] = []
        if len(key) > 2 and key[1] == "MAT" and key[2] in ("LAW1", "ELAST", "LAW36", "PLAS_TAB") and len(data) >= 3:
            fields = [Field("density", "밀도 (입력 덱 단위)", "float", data[1], 0, 20, 0, strict_minimum=True),
                      Field("young_modulus", "Young 계수 (입력 덱 단위)", "float", data[2], 0, 20, 0, strict_minimum=True),
                      Field("poisson_ratio", "Poisson 비", "float", data[2], 20, 40, -1, 0.5, True, True)]
        elif (len(key) in (3, 4) and key[1] == "PART" and key[2].isdigit()
              and (len(key) == 3 or key[3].isdigit()) and len(data) >= 2):
            fields = [Field("property_id", "Property ID", "int", data[1], 0, 10, 1),
                      Field("material_id", "Material ID", "int", data[1], 10, 20, 1)]
        elif len(key) > 1 and key[1] == "BCS" and len(data) >= 2:
            line = self.lines[data[1]].rstrip("\r\n")
            # /BCS uses fields of width 6 (Tra), 4 (Rot), then two width-10 IDs.
            if len(line) >= 10 and re.fullmatch(r"[01]{3}", line[:6].strip()) and re.fullmatch(r"[01]{3}", line[6:10].strip()):
                t = line[:6].index(line[:6].strip())
                r = 6 + line[6:10].index(line[6:10].strip())
                fields = [Field(name, label, "bool", data[1], position, position + 1)
                          for name, label, position in [("tx", "병진 X 고정", t), ("ty", "병진 Y 고정", t + 1),
                          ("tz", "병진 Z 고정", t + 2), ("rx", "회전 X 고정", r),
                          ("ry", "회전 Y 고정", r + 1), ("rz", "회전 Z 고정", r + 2)]]
        elif len(key) > 2 and key[1] == "INTER" and key[2] in ("TYPE24", "TYPE7") and len(data) >= 5:
            row = 4
            if key[2] == "TYPE7":
                try: curvature = int(self.lines[data[1]][80:90].strip() or "0")
                except ValueError: curvature = None
                if curvature not in (0, 1, 2, 3): return []
                if curvature in (1, 2): row = 5
            if len(data) > row:
                fields = [Field("friction", "마찰계수", "float", data[row], 20, 40, 0)]
        elif len(key) > 1 and key[1] == "FUNCT" and len(data) >= 2:
            for row, line in enumerate(data[1:]):
                fields += [Field(f"point_{row}_x", f"곡선 {row + 1}: X (입력 덱 단위)", "float", line, 0, 20),
                           Field(f"point_{row}_y", f"곡선 {row + 1}: Y (입력 덱 단위)", "float", line, 20, 40)]
        elif len(key) > 2 and key[1:3] == ["INIVEL", "TRA"] and len(data) >= 2:
            fields = [Field(name, label, "float", data[1], offset, offset + 20)
                      for name, label, offset in [("vx", "초기 속도 X (입력 덱 단위)", 0),
                                                 ("vy", "초기 속도 Y (입력 덱 단위)", 20),
                                                 ("vz", "초기 속도 Z (입력 덱 단위)", 40)]]
        elif len(key) > 2 and key[1] == "PROP" and key[2] in ("SHELL", "TYPE1") and len(data) >= 4:
            fields = [Field("thickness", "두께 (입력 덱 단위)", "float", data[3], 20, 40, 0, strict_minimum=True)]
        valid = []
        for field in fields:
            try:
                self._read_field(field)
                valid.append(field)
            except (ValueError, IndexError):
                continue
        return valid

    def _read_field(self, field: Field) -> object:
        text = self.lines[field.line].rstrip("\r\n")[field.start:field.stop].strip()
        if field.type == "bool":
            if text not in ("0", "1"):
                raise ValueError(text)
            return text == "1"
        if field.type == "int":
            return int(text)
        result = number(text)
        if not math.isfinite(result):
            raise ValueError(text)
        return result

    def unit_context(self, card: Card | None = None) -> dict:
        units = None
        for item in self.cards:
            if item.keyword.upper() == "/BEGIN" and len(item.data) >= 3:
                tokens = self.lines[item.data[2]].split()
                if len(tokens) == 3:
                    units = dict(zip(("mass", "length", "time"), tokens))
                break
        parts = card.keyword.split("/") if card else []
        return {"basis": "input_deck", "global": units,
                "unit_id": parts[4] if len(parts) > 4 and parts[1].upper() == "MAT" else None}

    def card_fields(self, card_id: str) -> list[dict]:
        card = self.card(card_id)
        patches = self._patches.get(card_id, {})
        return [{"name": f.name, "label": f.label, "type": f.type,
                 "value": patches.get(f.name, self._read_field(f)), "writable": True,
                 "units": self.unit_context(card), "minimum": f.minimum, "maximum": f.maximum}
                for f in self._schema(card)]

    def _validated_value(self, field, value):
        if field.type == "bool":
            if not isinstance(value, bool):
                raise PrepError("invalid_value", "구속 값은 true 또는 false여야 합니다.")
            return value
        if field.type == "int":
            if type(value) is not int:
                raise PrepError("invalid_value", "An integer native ID is required.")
            normalized = value
        else:
            try:
                if isinstance(value, bool): raise ValueError()
                normalized = float(value)
                if not math.isfinite(normalized): raise ValueError()
            except (TypeError, ValueError, OverflowError):
                raise PrepError("invalid_value", "유한한 수치가 필요합니다.", {"field": field.name}) from None
        if field.minimum is not None and (normalized < field.minimum or (field.strict_minimum and normalized == field.minimum)):
            raise PrepError("invalid_value", "허용 범위보다 작습니다.", {"field": field.name, "minimum": field.minimum})
        if field.maximum is not None and (normalized > field.maximum or (field.strict_maximum and normalized == field.maximum)):
            raise PrepError("invalid_value", "허용 범위보다 큽니다.", {"field": field.name, "maximum": field.maximum})
        text = str(normalized) if field.type == "int" else repr(normalized)
        if normalized != self._read_field(field) and len(text) > field.stop - field.start:
            raise PrepError("field_overflow", "솔버 필드 폭에 값을 기록할 수 없습니다.")
        return normalized

    def patched_state(self, card_id: str, name: str, value: object) -> dict:
        return self.fields_state(card_id, {name: value})

    def fields_state(self, card_id: str, values: dict) -> dict:
        schema = {field.name: field for field in self._schema(self.card(card_id))}
        result = self.snapshot()
        patches = result["patches"]
        for name, value in values.items():
            field = schema.get(name)
            if field is None:
                raise PrepError("field_not_writable", "이 필드는 원문 보존 전용입니다.", {"card_id": card_id, "field": name})
            normalized = self._validated_value(field, value)
            if normalized != self._read_field(field):
                patches.setdefault(card_id, {})[name] = normalized
            else:
                patches.get(card_id, {}).pop(name, None)
                if card_id in patches and not patches[card_id]: patches.pop(card_id)
        if self.card(card_id).keyword.upper().startswith("/FUNCT/") and values:
            from .modeling import curve_points
            merged = {name: patches.get(card_id, {}).get(name, self._read_field(field)) for name, field in schema.items()}
            curve_points([(merged.get(f"point_{i}_x"), merged.get(f"point_{i}_y")) for i in range(len(self.card(card_id).data) - 1)])
        return result

    def snapshot(self) -> dict:
        return {"state_version": 3, "patches": {key: dict(value) for key, value in self._patches.items()},
                "created": [dict(item) for item in self._created], "deleted": sorted(self._deleted),
                "replaced": dict(self._replaced)}

    def restore(self, state: dict) -> None:
        """Validate a candidate before replacing live state; legacy patch dictionaries still read."""
        if not isinstance(state, dict):
            raise PrepError("invalid_project", "편집 패치 형식이 잘못됐습니다.")
        if "state_version" not in state:
            state = {"state_version": 2, "patches": state, "created": [], "deleted": []}
        if state.get("state_version") == 2 and set(state) == {"state_version", "patches", "created", "deleted"}:
            state = {**state, "state_version": 3, "replaced": {}}
        if (type(state.get("state_version")) is not int or state["state_version"] != 3
                or set(state) != {"state_version", "patches", "created", "deleted", "replaced"}
                or not isinstance(state["patches"], dict) or not isinstance(state["created"], list)
                or not isinstance(state["deleted"], list) or not isinstance(state["replaced"], dict)):
            raise PrepError("invalid_project", "Unsupported structural deck state.")
        source_ids = {card.id for card in self._source_cards}
        created, used = [], set(source_ids)
        for item in state["created"]:
            if not isinstance(item, dict) or set(item) != {"id", "text"} or not all(isinstance(value, str) for value in item.values()):
                raise PrepError("invalid_project", "Invalid created card block.")
            try:
                UUID(item["id"])
                item["text"].encode("latin1")
            except (ValueError, UnicodeError):
                raise PrepError("invalid_project", "Invalid created card identity or encoding.") from None
            lines = item["text"].splitlines()
            if (item["id"] in used or not lines or not lines[0].startswith("/")
                    or len([line for line in lines if line.startswith("/")]) != 1
                    or lines[0].upper().strip() in ("/BEGIN", "/END")
                    or any(re.match(r"^\s*#(?:include|enddata)\b", line, re.I) for line in lines)
                    or not item["text"].endswith(("\n", "\r"))):
                raise PrepError("invalid_project", "Invalid created card block boundaries.")
            used.add(item["id"])
            created.append(dict(item))
        if (any(not isinstance(item, str) or item not in source_ids for item in state["deleted"])
                or len(state["deleted"]) != len(set(state["deleted"]))):
            raise PrepError("invalid_project", "Invalid deleted card identities.")
        deleted = set(state["deleted"])
        for card in self._source_cards:
            if card.id in deleted:
                text = "".join(self._source_lines[card.start:card.stop])
                if card.keyword.upper() in ("/BEGIN", "/END") or re.search(r"^\s*#include\b", text, re.I | re.M):
                    raise PrepError("invalid_project", "Cannot remove a document boundary or INCLUDE directive.")
        replaced = {}
        original_by_id = {card.id: card for card in self._source_cards}
        for card_id, text in state["replaced"].items():
            if card_id not in original_by_id or card_id in deleted or not isinstance(text, str):
                raise PrepError("invalid_project", "Invalid replaced card identity.")
            self._validate_replacement(original_by_id[card_id].keyword, text)
            replaced[card_id] = text
        candidate = copy(self)
        candidate._created, candidate._deleted, candidate._patches, candidate._replaced = created, deleted, {}, replaced
        candidate._state_token_cache = None
        if created != self._created or deleted != self._deleted or replaced != self._replaced:
            candidate._rebuild_layout()
        for card_id, values in state["patches"].items():
            if not isinstance(values, dict):
                raise PrepError("invalid_project", "필드 패치 형식이 잘못됐습니다.")
            candidate._patches = candidate.fields_state(card_id, values)["patches"]
        self.__dict__.update(candidate.__dict__)

    def inserted_states(self, texts, *, card_ids=None):
        """Prepare a batch in one resource; the dispatcher commits it once."""
        identities = list(card_ids) if card_ids is not None else [str(uuid4()) for _ in texts]
        if len(identities) != len(texts):
            raise PrepError("invalid_command", "Every inserted block needs one identity.")
        state = self.snapshot()
        state["created"].extend({"id": identity, "text": text} for identity, text in zip(identities, texts))
        candidate = copy(self)
        candidate.restore(state)
        return state, identities

    def inserted_state(self, text: str, *, card_id=None):
        state, identities = self.inserted_states([text], card_ids=[card_id or str(uuid4())])
        return state, identities[0]

    def deleted_state(self, card_id):
        self.card(card_id)
        state = self.snapshot()
        if any(item["id"] == card_id for item in state["created"]):
            state["created"] = [item for item in state["created"] if item["id"] != card_id]
        else:
            state["deleted"].append(card_id)
        state["patches"].pop(card_id, None)
        state["replaced"].pop(card_id, None)
        candidate = copy(self)
        candidate.restore(state)
        return state

    @staticmethod
    def _validate_replacement(keyword, text):
        try:
            lines = text.splitlines()
            text.encode("latin1")
        except (AttributeError, UnicodeError):
            raise PrepError("invalid_project", "Invalid replacement card encoding.") from None
        if (not lines or lines[0].strip() != keyword or not text.endswith(("\r", "\n"))
                or sum(line.startswith("/") for line in lines) != 1
                or any(re.match(r"^\s*#(?:include|enddata)\b", line, re.I) for line in lines)):
            raise PrepError("invalid_project", "Replacement must retain one native card identity and no file directives.")

    def replaced_state(self, card_id, text):
        card = self.card(card_id)
        self._validate_replacement(card.keyword, text)
        state = self.snapshot()
        created = next((item for item in state["created"] if item["id"] == card_id), None)
        if created is None:
            original = next(card for card in self._source_cards if card.id == card_id)
            original_text = "".join(self._source_lines[original.start:original.stop])
            if text == original_text: state["replaced"].pop(card_id, None)
            else: state["replaced"][card_id] = text
        else:
            created["text"] = text
        state["patches"].pop(card_id, None)
        candidate = copy(self)
        candidate.restore(state)
        return state

    def state_token(self) -> str:
        if self._state_token_cache is None:
            self._state_token_cache = hashlib.sha256(self._raw_digest + json.dumps(self.snapshot(), sort_keys=True).encode()).hexdigest()
        return self._state_token_cache

    def render(self) -> bytes:
        if not self._patches and not self._created and not self._deleted and not self._replaced:
            return self.raw
        lines = list(self.lines)
        for card_id, values in self._patches.items():
            schema = {f.name: f for f in self._schema(self.card(card_id))}
            for name, value in values.items():
                field = schema[name]
                line = lines[field.line]
                ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else "\r" if line.endswith("\r") else ""
                content = line[:-len(ending)] if ending else line
                text = (("1" if value else "0") if field.type == "bool" else
                        (str(value) if field.type == "int" else repr(float(value))).rjust(field.stop - field.start))
                lines[field.line] = content[:field.start] + text + content[field.stop:] + ending
        return "".join(lines).encode("latin1")

    def list_cards(self) -> list[dict]:
        return [{"id": c.id, "keyword": c.keyword, "title": c.title, "category": c.category,
                 "resource_id": self.id, "resource_name": self.name,
                 "writable": bool(self._schema(c)), "units": self.unit_context(c)} for c in self.cards]

    def includes(self) -> list[dict]:
        references = []
        for index, line in enumerate(self.lines[:self.active_stop]):
            match = re.match(r"^\s*#include\b(.*)$", line, re.I)
            if not match:
                continue
            value = match.group(1).strip()
            if not value:
                cursor = index + 1
                while cursor < self.active_stop and (not self.lines[cursor].strip() or self.lines[cursor].lstrip().startswith("#")):
                    cursor += 1
                value = self.lines[cursor].strip() if cursor < self.active_stop else ""
            references.append({"path": value.strip('"\''), "line": index + 1})
        return references

    def mesh_projection(self) -> dict:
        # Coordinates are read-only in this version; the native raw span is authoritative.
        nodes: dict[int, list[float]] = {}
        cells = []
        diagnostics = []
        for card in self.cards:
            key = card.keyword.upper().split("/")
            if key[1] == "NODE":
                for index in card.data:
                    line = self.lines[index].rstrip("\r\n")
                    try:
                        identifier = int(line[:10]); xyz = [number(line[p:p + 20].strip()) for p in (10, 30, 50)]
                        if not all(math.isfinite(v) for v in xyz):
                            raise ValueError()
                        if identifier in nodes:
                            diagnostics.append({"severity": "warning", "code": "duplicate_node_id", "message": f"중복 절점 ID {identifier}; 3D 표시가 부분적입니다."})
                        else:
                            nodes[identifier] = xyz
                    except ValueError:
                        diagnostics.append({"severity": "warning", "code": "node_display_parse", "message": "일부 절점 행을 표시하지 못했습니다.", "line": index + 1})
            elif key[1] in ("SHELL", "SH3N", "BRICK", "TETRA4", "TETRA", "BEAM", "TRUSS"):
                kind, count = {"SHELL": ("quad", 4), "SH3N": ("triangle", 3), "BRICK": ("hexahedron", 8),
                               "TETRA4": ("tetra", 4), "TETRA": ("tetra", 4), "BEAM": ("line", 2), "TRUSS": ("line", 2)}[key[1]]
                part = int(key[2]) if len(key) > 2 and key[2].isdigit() else None
                for index in card.data:
                    line = self.lines[index].rstrip("\r\n")
                    try:
                        values = [int(line[p:p + 10]) for p in range(0, (count + 1) * 10, 10)]
                        cells.append({"id": values[0], "type": kind, "nodes": values[1:], "part_id": part,
                                      "card_id": card.id, "resource_id": self.id})
                    except ValueError:
                        diagnostics.append({"severity": "warning", "code": "element_display_parse", "message": "일부 요소 행을 표시하지 못했습니다.", "line": index + 1})
        identifiers = sorted(nodes)
        # An element resource may refer to nodes in another INCLUDE resource.
        # Validate connectivity only after the document has assembled all resources.
        return {"points": [nodes[i] for i in identifiers], "node_ids": identifiers, "cells": cells,
                "diagnostics": diagnostics}
