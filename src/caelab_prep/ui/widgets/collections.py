"""Typed collection drafts shared by native properties and operation forms.

These widgets never submit document commands. Hosts read ``value()`` for a
validated value and retain ``raw_value()`` when an incomplete draft must survive.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Mapping, MutableMapping
from copy import copy
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from fractions import Fraction
import gc
from ipaddress import IPv4Address, IPv6Address
from numbers import Number
from pathlib import PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
import re
import sqlite3
import sys
from types import MappingProxyType, MemberDescriptorType
from uuid import UUID

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QClipboard, QKeySequence, QValidator
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLineEdit, QListWidget,
                              QListWidgetItem, QMenu, QVBoxLayout, QWidget)

from ...application.contracts import ObjectRef
from .curve import CurveTable


class _IdTextLimit(QValidator):
    """Reject an entire edit before QLineEdit can publish a shortened ID list."""

    def __init__(self, maximum_bytes, parent):
        super().__init__(parent)
        self.maximum_bytes = maximum_bytes

    def validate(self, text, position):
        state = (QValidator.State.Acceptable if len(text.encode("utf-8", "surrogatepass")) <= self.maximum_bytes
                 else QValidator.State.Invalid)
        return state, text, position


class IntegerListEdit(QLineEdit):
    """A positive-ID draft; oversized input is rejected, never truncated.

    QLineEdit defaults to 32767 UTF-16 units and can silently shorten paste or
    IME input. Keep a one-unit canary above the explicit UTF-8 byte limit: even
    if Qt shortens an incoming edit to maxLength, the validator sees an invalid
    result and restores the entire previous text. UTF-8 uses at least as many
    bytes as UTF-16 units, including non-ASCII/IME input. Programmatic restores
    need their own check because setText bypasses QValidator.
    """

    draftChanged = Signal()
    MAX_INPUT_BYTES = 16 * 1024 * 1024

    def __init__(self, value=(), parent=None, *, maximum_bytes=MAX_INPUT_BYTES):
        super().__init__(parent)
        if type(maximum_bytes) is not int or not 0 < maximum_bytes <= self.MAX_INPUT_BYTES:
            raise ValueError("ID text size limit must be a positive integer up to 16 MiB")
        self.maximum_bytes = maximum_bytes
        self._input_error = ""
        self._help = (f"IDs separated by spaces or commas. Maximum text size: {maximum_bytes:,} UTF-8 bytes. "
                      "Larger edits are rejected without changing the existing IDs.")
        self.setMaxLength(maximum_bytes + 1)
        self.setValidator(_IdTextLimit(maximum_bytes, self))
        self.setPlaceholderText("IDs: 1, 2, 3")
        self.set_raw_value(value)
        self.textEdited.connect(self._edited)
        self.inputRejected.connect(self._rejected)

    def _edited(self, *_):
        self._input_error = ""
        self.setToolTip(self._help)
        self.draftChanged.emit()

    def _rejected(self):
        self._input_error = (f"ID text exceeds {self.maximum_bytes:,} UTF-8 bytes. "
                             "The entire edit was rejected; existing IDs are unchanged. Edit again or Revert/Cancel.")
        self.setToolTip(self._input_error)
        self.draftChanged.emit()

    def setText(self, text):
        if len(text.encode("utf-8", "surrogatepass")) > self.maximum_bytes:
            raise ValueError(f"ID text exceeds {self.maximum_bytes:,} UTF-8 bytes; existing IDs are unchanged")
        self._input_error = ""
        self.setToolTip(self._help)
        super().setText(text)

    def _can_insert(self, text):
        size = (len(self.text().encode("utf-8", "surrogatepass"))
                - len(self.selectedText().encode("utf-8", "surrogatepass"))
                + len(text.encode("utf-8", "surrogatepass")))
        if size > self.maximum_bytes:
            self._rejected()
            return False
        return True

    def insert(self, text):
        # Preflight bulk data before Qt allocates/shapes the inserted line.
        # The validator remains the final guard for native editing paths.
        if not self.isReadOnly() and self._can_insert(text):
            super().insert(text)

    def paste(self):
        self.insert(QApplication.clipboard().text())

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste(); event.accept()
        else:
            super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        # Native replacement offsets are in UTF-16 units; let Qt and the
        # validator handle them. Reject an oversized commit before shaping it.
        if len(event.commitString().encode("utf-8", "surrogatepass")) > self.maximum_bytes:
            self._rejected(); event.accept()
        else:
            super().inputMethodEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasText() and not self._can_insert(event.mimeData().text()):
            event.ignore()
        else:
            super().dropEvent(event)

    def mouseReleaseEvent(self, event):
        clipboard = QApplication.clipboard()
        if (event.button() == Qt.MouseButton.MiddleButton and clipboard.supportsSelection()
                and not self._can_insert(clipboard.text(QClipboard.Mode.Selection))):
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def createStandardContextMenu(self):
        # Qt's built-in Paste action calls the C++ slot directly. Route the
        # standard text actions through the same bulk-input preflight instead
        # of relying on private QAction names or translated label matching.
        menu = QMenu(self)
        writable, selected = not self.isReadOnly(), self.hasSelectedText()
        entries = (("Undo", self.undo, writable and self.isUndoAvailable()),
                   ("Redo", self.redo, writable and self.isRedoAvailable()), None,
                   ("Cut", self.cut, writable and selected), ("Copy", self.copy, selected),
                   ("Paste", self.paste, writable and QApplication.clipboard().mimeData().hasText()),
                   ("Delete", lambda: self.insert(""), writable and selected), None,
                   ("Select All", self.selectAll, bool(self.text())))
        for entry in entries:
            if entry is None:
                menu.addSeparator()
            else:
                label, callback, enabled = entry
                action = menu.addAction(self.tr(label)); action.triggered.connect(callback); action.setEnabled(enabled)
        return menu

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.exec(event.globalPos())
        menu.deleteLater()

    def value(self):
        if self._input_error:
            raise ValueError(self._input_error)
        text = self.text().strip()
        if not text:
            return ()
        tokens = re.split(r"[\s,]+", text)
        if any(not re.fullmatch(r"[0-9]+", token) or int(token) <= 0 for token in tokens):
            raise ValueError("Enter positive integer IDs separated by spaces or commas")
        values = tuple(int(token) for token in tokens)
        if len(set(values)) != len(values):
            raise ValueError("Each ID may occur only once")
        return values

    def raw_value(self):
        # Keep rejected-input diagnostics when a host preserves/rebuilds a draft.
        return {"text": self.text(), "input_error": self._input_error} if self._input_error else self.text()

    def set_raw_value(self, value):
        error = ""
        if isinstance(value, dict):
            if set(value) != {"text", "input_error"} or not all(isinstance(item, str) for item in value.values()):
                raise ValueError("Expected ID text and its rejected-input diagnostic")
            value, error = value["text"], value["input_error"]
        self.setText(value if isinstance(value, str) else ", ".join(str(item) for item in value))
        self._input_error = error
        if error:
            self.setToolTip(error)


class BooleanVectorEdit(QWidget):
    """One logical tuple with named component checkboxes."""

    draftChanged = Signal()
    is_multiline = False

    def __init__(self, value=(False, False, False), *, components=("X", "Y", "Z"), parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.editors = tuple(QCheckBox(str(component), self) for component in components)
        for component, editor in zip(components, self.editors):
            editor.setAccessibleName(str(component))
            editor.toggled.connect(self.draftChanged)
            row.addWidget(editor)
        row.addStretch(1)
        self.set_raw_value(value)

    def value(self):
        return tuple(editor.isChecked() for editor in self.editors)

    def raw_value(self):
        return self.value()

    def set_raw_value(self, value):
        value = tuple(value)
        if len(value) != len(self.editors) or any(type(item) is not bool for item in value):
            raise ValueError(f"Expected {len(self.editors)} boolean components")
        blocked = [QSignalBlocker(editor) for editor in self.editors]
        for editor, checked in zip(self.editors, value):
            editor.setChecked(checked)
        del blocked


_PLAIN_PRIMITIVES = frozenset({str, int, float, bool, type(None), Decimal, Fraction, complex})
_HASH_SCALARS = _PLAIN_PRIMITIVES | {
    bytes, ObjectRef, UUID, date, datetime, time, timedelta, IPv4Address, IPv6Address,
    PurePosixPath, PureWindowsPath, PosixPath, WindowsPath,
}
_ROW_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_DICT_KEYS = type({}.keys())


def _proxy_target(value):
    target, = gc.get_referents(value)
    return target


def _unwrap_standard_dict(value):
    while type(value) is MappingProxyType:
        value = _proxy_target(value)
    if isinstance(value, dict) and type(value).__eq__ is dict.__eq__:
        return value
    return None


class _SQLiteRowSnapshot:
    """A detached sqlite row with the same column lookup and equality."""

    __slots__ = ("_description", "_values")

    def __init__(self, description, values):
        self._description = description
        self._values = values

    def keys(self):
        return [column[0] for column in self._description]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __getitem__(self, key):
        if isinstance(key, str):
            for index, (name, *_) in enumerate(self._description):
                if key == name or (key.isascii() and name.isascii() and key.lower() == name.lower()):
                    return self._values[index]
            raise IndexError("No item with that key")
        return self._values[key]

    def __eq__(self, other):
        if isinstance(other, (sqlite3.Row, _SQLiteRowSnapshot)):
            return self._description == _sqlite_description(other) and self._values == tuple(other)
        return NotImplemented

    def __hash__(self):
        # CPython's sqlite row hashes the full cursor description and values.
        return hash(self._description) ^ hash(self._values)

    def __repr__(self):
        return repr(list(zip(self.keys(), self._values)))


def _sqlite_description(row):
    if isinstance(row, _SQLiteRowSnapshot):
        return row._description
    # sqlite3 supplies the DB-API seven-tuple with only the column name set.
    return tuple((name, None, None, None, None, None, None) for name in row.keys())


def _ref_slots(ref):
    for base in type(ref).__mro__:
        for member in vars(base).values():
            if isinstance(member, MemberDescriptorType):
                try:
                    value = member.__get__(ref)
                except AttributeError:
                    continue
                yield member, value


def _copy_ref_state(ref, clone, memo):
    if hasattr(ref, "__dict__"):
        object.__setattr__(clone, "__dict__", _clone_ref(vars(ref), memo))
    for member, value in _ref_slots(ref):
        member.__set__(clone, _clone_ref(value, memo))


def _frozen_state_values(ref):
    attributes = getattr(ref, "__dict__", {})
    yield from attributes.values()
    yield from (value for _, value in _ref_slots(ref))
    for member in fields(ref):
        if member.name not in attributes:
            try:
                yield getattr(ref, member.name)
            except AttributeError:
                continue


def _clone_sqlalchemy_row(ref, memo):
    state = ref.__getstate__()
    items = state["_data"]
    values = tuple(_clone_ref(item, memo) for item in items)
    if all(value is item for value, item in zip(values, items)):
        return ref
    kind = type(ref)
    clone = kind.__new__(kind)
    # The original parent preserves both string and SQL-expression lookups.
    clone.__setstate__({**state, "_data": values})
    return memo.setdefault(id(ref), clone)


def _clone_ref(ref, memo=None):
    kind = type(ref)
    if kind is dict and memo is None and _HASH_SCALARS.issuperset(map(type, ref.values())):
        return ref.copy()
    if kind in _HASH_SCALARS:
        return ref
    if memo is None and kind is MappingProxyType:
        return MappingProxyType(_clone_ref(_proxy_target(ref)))
    if memo is None:
        memo = {}
    key = id(ref)
    if key in memo:
        return memo[key]
    if kind is MappingProxyType:
        return memo.setdefault(key, MappingProxyType(_clone_ref(_proxy_target(ref), memo)))
    if kind is bytearray:
        return memo.setdefault(key, bytearray(ref))
    if kind is memoryview:
        snapshot = memoryview(ref.tobytes())
        if (snapshot.format, snapshot.shape) != (ref.format, ref.shape):
            try:
                snapshot = snapshot.cast(ref.format, ref.shape)
            except (TypeError, ValueError):
                pass
        return memo.setdefault(key, snapshot)
    if kind is _DICT_KEYS:
        return memo.setdefault(key, dict.fromkeys(_clone_ref(name, memo) for name in ref).keys())
    if isinstance(ref, dict):
        clone = {} if kind is dict else copy(ref)
        if clone is ref:
            # Immutable dict subclasses may implement copy as an identity
            # operation. Rebuild them without ever clearing the original.
            return memo.setdefault(key, kind((_clone_ref(name, memo), _clone_ref(value, memo))
                                             for name, value in ref.items()))
        if isinstance(clone, OrderedDict):
            OrderedDict.clear(clone)
            set_item = OrderedDict.__setitem__
        else:
            dict.clear(clone)
            set_item = dict.__setitem__
        memo[key] = clone
        for name, value in ref.items():
            set_item(clone, _clone_ref(name, memo), _clone_ref(value, memo))
    elif kind is getattr(sys.modules.get("sqlalchemy.engine.row"), "RowMapping", None):
        return _clone_sqlalchemy_row(ref, memo)
    elif isinstance(ref, Mapping) and not isinstance(ref, MutableMapping):
        entries = tuple(ref.items())
        pairs = tuple((_clone_ref(name, memo), _clone_ref(value, memo)) for name, value in entries)
        state = tuple(getattr(ref, "__dict__", {}).values()) + tuple(value for _, value in _ref_slots(ref))
        probe = memo | {key: ref}
        if (all(name is old_name and value is old_value for (name, value), (old_name, old_value) in zip(pairs, entries))
                and all(_clone_ref(value, probe) is value for value in state)):
            return ref
        if state:
            try:
                clone = copy(ref)
            except TypeError:
                clone = ref
            if clone is not ref:
                memo[key] = clone
                _copy_ref_state(ref, clone, memo)
                return clone
        try:
            clone = kind(pairs)
        except (AttributeError, TypeError):
            clone = dict(pairs)
        return memo.setdefault(key, clone)
    elif isinstance(ref, (list, deque, set)):
        clone = copy(ref)
        clone.clear()
        memo[key] = clone
        values = (_clone_ref(value, memo) for value in ref)
        if isinstance(ref, set):
            clone.update(values)
        else:
            clone.extend(values)
    elif kind is getattr(sys.modules.get("sqlalchemy.engine.row"), "Row", None):
        return _clone_sqlalchemy_row(ref, memo)
    elif isinstance(ref, (tuple, frozenset, sqlite3.Row, _SQLiteRowSnapshot)):
        items = tuple(ref)
        values = tuple(_clone_ref(item, memo) for item in items)
        unchanged = all(value is item for value, item in zip(values, items))
        if unchanged and not hasattr(ref, "__dict__"):
            return ref
        if key in memo:
            return memo[key]
        if isinstance(ref, tuple):
            clone = tuple.__new__(kind, values)
        elif isinstance(ref, frozenset):
            clone = frozenset.__new__(kind, values)
        else:
            return memo.setdefault(key, _SQLiteRowSnapshot(_sqlite_description(ref), values))
        memo[key] = clone
    elif isinstance(ref, (Enum, Number)) or (kind.__eq__ is object.__eq__ and not isinstance(ref, Mapping)):
        # Identity-valued references, such as an ORM entity, must stay attached.
        return ref
    else:
        numpy = sys.modules.get("numpy")
        if isinstance(ref, getattr(numpy, "generic", ())) and ref.dtype.kind in "bMSU":
            # NumPy booleans, dates and strings are immutable values outside
            # numbers.Number. Keep the widget package independent of NumPy.
            return ref
        if is_dataclass(ref) and kind.__dataclass_params__.frozen:
            # Treat back-references as unchanged while probing. If any state
            # needs detaching, revisit it with the real clone in the memo.
            probe = memo | {key: ref}
            if all(_clone_ref(value, probe) is value for value in _frozen_state_values(ref)):
                return ref
        clone = object.__new__(kind)
        memo[key] = clone
    if kind not in (dict, list, set, tuple, frozenset, deque):
        _copy_ref_state(ref, clone, memo)
    return clone


def _plain_key(value):
    kind = type(value)
    if kind in _HASH_SCALARS:
        return hash(value)
    if kind is tuple or kind is list:
        items = tuple(_plain_key(item) for item in value)
        return (kind.__name__, items) if None not in items else None
    target = value if kind is dict else _unwrap_standard_dict(value)
    if target is None:
        return None
    items = []
    for key, item in dict.items(target):
        name_key = hash(key) if type(key) in _HASH_SCALARS else _plain_key(key)
        value_key = hash(item) if type(item) in _HASH_SCALARS else _plain_key(item)
        if name_key is None or value_key is None:
            return None
        items.append((name_key, value_key))
    return ("dict", frozenset(items))


def _shares_hash_bucket(value):
    kind = type(value)
    return (kind in _HASH_SCALARS or
            (kind is tuple or kind is frozenset) and all(_shares_hash_bucket(item) for item in value) or
            isinstance(value, Enum) and kind.__eq__ in (object.__eq__, int.__eq__, str.__eq__))


def _bucket_key(value):
    kind = type(value)
    if kind in _HASH_SCALARS:
        return ("hash", hash(value))
    if kind is dict or kind is list:
        return _plain_key(value)
    if isinstance(value, Mapping):
        return _plain_key(value)
    # Arbitrary record classes can compare equal to a structured mapping even
    # when they provide a hash. Compare those values against all buckets.
    if not _shares_hash_bucket(value):
        return None
    try:
        return ("hash", hash(value))
    except TypeError:
        return None


def _contains(buckets, item, key):
    matches = buckets.get(key)
    if matches and any(existing == item for existing in matches):
        return True
    # A value without a reliable key may compare equal to a keyed value.
    if key is None:
        return any(existing == item for other, bucket in buckets.items()
                   if other is not None for existing in bucket)
    fallback = buckets.get(None)
    return bool(fallback and any(existing == item for existing in fallback))


class ReferenceListEdit(QWidget):
    """Check qualified object references by equality, keeping missing choices visible."""

    draftChanged = Signal()
    is_multiline = True

    def __init__(self, value=(), *, choices=(), choice_labels=(), parent=None):
        super().__init__(parent)
        source_choices = tuple(choices)
        self.choices = tuple(_clone_ref(ref) for ref in source_choices)
        self._choice_keys = tuple(_bucket_key(ref) for ref in self.choices)
        self._choice_buckets = {}
        for key, ref in zip(self._choice_keys, self.choices):
            self._choice_buckets.setdefault(key, []).append(ref)
        self.choice_labels = tuple(choice_labels)
        self.list = QListWidget(self)
        self.list.setUniformItemSizes(True)
        self.list.setAccessibleName("Referenced objects")
        self.list.setMinimumHeight(120)
        self.list.setMaximumHeight(160)
        self._row_refs = []
        self._row_available = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list)
        self.list.itemChanged.connect(self.draftChanged)
        selected = tuple(value)
        checked_rows = None
        if len(self._choice_buckets) == len(source_choices) and None not in self._choice_buckets:
            # Providers can pass the actual choices back as the initial
            # selection. With unique keys, those rows need no second indexing.
            positions = {id(ref): index for index, ref in enumerate(source_choices)}
            indices = tuple(positions.get(id(ref)) for ref in selected)
            if all(index is not None and self.choices[index] == ref for index, ref in zip(indices, selected)):
                checked_rows = set(indices)
        self._set_raw_value(selected, checked_rows)

    def _checked_row_ids(self):
        item_at = self.list.item
        checked = Qt.CheckState.Checked
        for index in range(self.list.count()):
            item = item_at(index)
            if item.checkState() == checked:
                yield item.data(_ROW_ID_ROLE)

    def raw_value(self):
        return tuple(_clone_ref(self._row_refs[row_id]) for row_id in self._checked_row_ids())

    def value(self):
        selected = []
        for row_id in self._checked_row_ids():
            ref = self._row_refs[row_id]
            if not self._row_available[row_id] and not _contains(self._choice_buckets, ref, _bucket_key(ref)):
                raise ValueError("A selected object is no longer available; uncheck it or choose an available object")
            selected.append(_clone_ref(ref))
        return tuple(selected)

    def set_raw_value(self, value):
        self._set_raw_value(tuple(value), None)

    def _set_raw_value(self, selected, checked_rows):
        if checked_rows is None:
            selected_keys = tuple(_bucket_key(ref) for ref in selected)
            selected_buckets = {}
            for key, ref in zip(selected_keys, selected):
                selected_buckets.setdefault(key, []).append(ref)
        item_type, add_item = QListWidgetItem, self.list.addItem
        checked, unchecked = Qt.CheckState.Checked, Qt.CheckState.Unchecked
        user_role = Qt.ItemDataRole.UserRole
        row_role = _ROW_ID_ROLE
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
        rows = self._row_refs
        available_rows = self._row_available

        def add_row(ref, label, selected, available):
            cloned = _clone_ref(ref)
            item = item_type(label)
            item.setData(user_role, cloned)
            item.setData(row_role, len(rows))
            item.setToolTip(label)
            item.setFlags(flags)
            item.setCheckState(checked if selected else unchecked)
            add_item(item)
            rows.append(cloned)
            available_rows.append(available)

        displayed_buckets = {}
        blocked = QSignalBlocker(self.list)
        self.list.setUpdatesEnabled(False)
        try:
            self.list.clear()
            rows.clear()
            available_rows.clear()
            for index, (key, ref) in enumerate(zip(self._choice_keys, self.choices)):
                if checked_rows is None:
                    if _contains(displayed_buckets, ref, key):
                        continue
                    selected_row = _contains(selected_buckets, ref, key)
                    displayed_buckets.setdefault(key, []).append(ref)
                else:
                    selected_row = index in checked_rows
                label = (self.choice_labels[index] if index < len(self.choice_labels)
                         else getattr(ref, "native_scope", None) or getattr(ref, "object_id", ref))
                add_row(ref, str(label), selected_row, True)
            if checked_rows is None:
                for key, ref in zip(selected_keys, selected):
                    if not _contains(displayed_buckets, ref, key):
                        label = str(getattr(ref, "native_scope", None) or getattr(ref, "object_id", ref))
                        add_row(ref, "Unavailable: " + label, True, False)
                        displayed_buckets.setdefault(key, []).append(ref)
        finally:
            self.list.setUpdatesEnabled(True)
            del blocked


class NumericTableEdit(CurveTable):
    """Two-column worksheet whose commit button belongs to the outer form."""

    is_multiline = True

    def __init__(self, value=(), *, components=("X", "Y"), minimum_rows=0,
                 maximum_rows=None, parent=None):
        if len(components) != 2:
            raise ValueError("The numeric worksheet requires two column labels")
        super().__init__(parent, minimum_points=minimum_rows, maximum_points=maximum_rows)
        self.set_points(value, headers=components)
        self.apply_button.hide()
        self.revert_button.hide()
        # An embedded worksheet already receives the property row's padding.
        # Avoid adding enough duplicate margin to force horizontal scrolling in
        # the narrow Settings/FORM inspector; keep every command label intact.
        toolbar_layout = self.layout().itemAt(0).widget().layout()
        margins = toolbar_layout.contentsMargins()
        toolbar_layout.setContentsMargins(4, margins.top(), 4, margins.bottom())
        self.setMinimumHeight(210)

    def sizeHint(self):
        return QSize(super().sizeHint().width(), 240)

    def value(self):
        return self.points()

    def raw_value(self):
        return self.draft_state()

    def set_raw_value(self, value):
        self.restore_draft(value)
