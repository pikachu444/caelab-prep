"""Conservative Radioss block reader: original bytes remain the authority.

Only explicitly described fields are writable. Unrecognized cards, comments,
line endings, ordering, and unedited fields are never reformatted.
"""
from __future__ import annotations

from dataclasses import dataclass
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
        self.lines = self.raw.decode("latin1").splitlines(keepends=True)
        self.is_include = is_include
        # #enddata terminates the current INCLUDE, not the caller. Keep the
        # ignored tail in raw, but do not expose it as active model content.
        self.active_stop = next((i for i, line in enumerate(self.lines)
                                 if is_include and re.match(r"^\s*#enddata\b", line, re.I)), len(self.lines))
        self._patches: dict[str, dict[str, object]] = {}
        self.cards: list[Card] = []
        self.diagnostics: list[dict] = []
        starts = [i for i, line in enumerate(self.lines[:self.active_stop]) if line.startswith("/")]
        for ordinal, start in enumerate(starts):
            stop = starts[ordinal + 1] if ordinal + 1 < len(starts) else self.active_stop
            keyword = self.lines[start].strip()
            data = tuple(i for i in range(start + 1, stop)
                         if self.lines[i].strip() and not self.lines[i].lstrip().startswith("#"))
            category = self._category(keyword)
            title = self.lines[data[0]].strip() if data and category not in ("Nodes", "Elements") else ""
            self.cards.append(Card(str(uuid5(UUID(self.id), str(ordinal) + ":" + keyword)),
                                   keyword, start, stop, data, title, category))
        self._by_id = {card.id: card for card in self.cards}
        if not self.cards and not is_include:
            raise PrepError("invalid_deck", "Radioss 블록 카드가 없는 파일입니다.", {"name": name})
        for card in self.cards:
            if card.keyword.upper().startswith("/TRANSFORM"):
                self.diagnostics.append({"severity": "warning", "code": "display_transform_not_applied",
                    "message": "변환 카드는 원문으로 보존합니다. 3D 표시는 변환 전 좌표일 수 있습니다.", "card_id": card.id})
            if card.keyword.upper().startswith("/BCS/") and not self._schema(card):
                self.diagnostics.append({"severity": "warning", "code": "bcs_layout_not_editable",
                    "message": "구속 카드의 고정 폭을 해석하지 못했습니다. 원문을 보존하며 편집하지 않습니다.", "card_id": card.id})

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
        elif len(key) > 2 and key[1:3] == ["INTER", "TYPE24"] and len(data) >= 5:
            fields = [Field("friction", "마찰계수", "float", data[4], 20, 40, 0)]
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

    def patched_state(self, card_id: str, name: str, value: object) -> dict:
        card = self.card(card_id)
        field = next((f for f in self._schema(card) if f.name == name), None)
        if field is None:
            raise PrepError("field_not_writable", "이 필드는 원문 보존 전용입니다.", {"card_id": card_id, "field": name})
        if field.type == "bool":
            if not isinstance(value, bool):
                raise PrepError("invalid_value", "구속 값은 true 또는 false여야 합니다.")
            normalized = value
        else:
            try:
                if isinstance(value, bool):
                    raise ValueError()
                normalized = float(value)
                if not math.isfinite(normalized):
                    raise ValueError()
            except (TypeError, ValueError):
                raise PrepError("invalid_value", "유한한 수치가 필요합니다.", {"field": name}) from None
            if field.minimum is not None and (normalized < field.minimum or (field.strict_minimum and normalized == field.minimum)):
                raise PrepError("invalid_value", "허용 범위보다 작습니다.", {"field": name, "minimum": field.minimum})
            if field.maximum is not None and (normalized > field.maximum or (field.strict_maximum and normalized == field.maximum)):
                raise PrepError("invalid_value", "허용 범위보다 큽니다.", {"field": name, "maximum": field.maximum})
            if normalized != self._read_field(field) and len(repr(normalized)) > field.stop - field.start:
                raise PrepError("field_overflow", "솔버 필드 폭에 값을 기록할 수 없습니다.")
        result = self.snapshot()
        result.setdefault(card_id, {})[name] = normalized
        if normalized == self._read_field(field):
            result[card_id].pop(name)
            if not result[card_id]:
                result.pop(card_id)
        return result

    def snapshot(self) -> dict:
        return {key: dict(value) for key, value in self._patches.items()}

    def restore(self, state: dict) -> None:
        if not isinstance(state, dict):
            raise PrepError("invalid_project", "편집 패치 형식이 잘못됐습니다.")
        # Validate all fields and values without exposing a partial state.
        previous = self._patches
        candidate: dict = {}
        try:
            self._patches = {}
            for card_id, fields in state.items():
                if not isinstance(fields, dict):
                    raise PrepError("invalid_project", "필드 패치 형식이 잘못됐습니다.")
                for name, value in fields.items():
                    candidate = self.patched_state(card_id, name, value)
                    self._patches = candidate
        except Exception:
            self._patches = previous
            raise
        self._patches = candidate

    def state_token(self) -> str:
        return hashlib.sha256(self._raw_digest + json.dumps(self._patches, sort_keys=True).encode()).hexdigest()

    def render(self) -> bytes:
        if not self._patches:
            return self.raw
        lines = list(self.lines)
        for card_id, values in self._patches.items():
            schema = {f.name: f for f in self._schema(self.card(card_id))}
            for name, value in values.items():
                field = schema[name]
                line = lines[field.line]
                ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else "\r" if line.endswith("\r") else ""
                content = line[:-len(ending)] if ending else line
                text = ("1" if value else "0") if field.type == "bool" else repr(float(value)).rjust(field.stop - field.start)
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
