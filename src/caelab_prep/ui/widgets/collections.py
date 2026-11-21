"""Typed collection drafts shared by native properties and operation forms.

These widgets never submit document commands. Hosts read ``value()`` for a
validated value and retain ``raw_value()`` when an incomplete draft must survive.
"""
from __future__ import annotations

from array import array
from collections import OrderedDict, deque
from collections.abc import Mapping, MutableMapping
from copy import copy
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from functools import cached_property
import gc
from ipaddress import IPv4Address, IPv6Address
from numbers import Number
from pathlib import PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
import re
import sqlite3
import sys
from types import MappingProxyType, MemberDescriptorType
from uuid import UUID
from weakref import WeakKeyDictionary

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
    PurePosixPath, PureWindowsPath, PosixPath, WindowsPath, range,
}
_ROW_ID_ROLE = Qt.ItemDataRole.UserRole + 1
_DICT_ITEMS = type({}.items())
_DICT_VALUES = type({}.values())
_DICT_VIEWS = {type({}.keys()): dict.keys, _DICT_ITEMS: dict.items, _DICT_VALUES: dict.values}
_CACHED_PROPERTY_TYPES = WeakKeyDictionary()


class _DetachedViewDict(dict):
    __slots__ = ("_origin_view",)


class _ReferenceMemo(dict):
    def __init__(self, entries=()):
        super().__init__(entries)
        self.unshareable = set()
        self.frozen_slots = {}


def _proxy_target(value):
    target, = gc.get_referents(value)
    return target


def _view_origin(view):
    backing = _proxy_target(view.mapping)
    return backing._origin_view if type(backing) is _DetachedViewDict else view


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
    slots = memo.frozen_slots.get(id(ref))
    for member, value in _ref_slots(ref) if slots is None else slots:
        member.__set__(clone, _clone_ref(value, memo))


def _frozen_state_values(ref, memo):
    attributes = getattr(ref, "__dict__", {})
    yield from attributes.values()
    names = set(attributes)
    slots = memo.frozen_slots.get(id(ref))
    if slots is None:
        slots = memo.frozen_slots[id(ref)] = tuple(_ref_slots(ref))
    for slot, value in slots:
        names.add(slot.__name__)
        yield value
    for member in fields(ref):
        if member.name not in names:
            try:
                yield getattr(ref, member.name)
            except AttributeError:
                continue


def _has_cached_property(kind):
    try:
        return _CACHED_PROPERTY_TYPES[kind]
    except (KeyError, TypeError):
        result = any(isinstance(member, cached_property) for base in kind.__mro__ for member in vars(base).values())
        try:
            _CACHED_PROPERTY_TYPES[kind] = result
        except TypeError:
            pass
        return result


def _retains_identity(ref, kind):
    if isinstance(ref, (Enum, Number)) or (kind.__eq__ is object.__eq__ and not isinstance(ref, Mapping)):
        return True
    numpy = sys.modules.get("numpy")
    return isinstance(ref, getattr(numpy, "generic", ())) and ref.dtype.kind in "bMSU"


def _share_frozen_state(ref, memo, unshareable):
    """Share a frozen graph only after all of its reachable state is safe."""
    if id(ref) in unshareable:
        return False
    path = [(None, iter((ref,)))]
    visited = {}
    while path:
        try:
            value = next(path[-1][1])
        except StopIteration:
            path.pop()
            continue
        kind = type(value)
        key = id(value)
        if key in memo:
            if memo[key] is value:
                continue
        elif key in visited or kind in _HASH_SCALARS:
            continue
        elif key not in unshareable:
            visited[key] = value
            if kind in (tuple, frozenset):
                path.append((key, iter(value)))
                continue
            elif kind is slice:
                path.append((key, iter((value.start, value.stop, value.step))))
                continue
            elif is_dataclass(kind) and kind.__dataclass_params__.frozen and not _has_cached_property(kind):
                path.append((key, _frozen_state_values(value, memo)))
                continue
            elif (kind not in _DICT_VIEWS and not isinstance(value, (list, deque, set, tuple, array))
                  and _retains_identity(value, kind)):
                continue
        unshareable.add(key)
        unshareable.update(ancestor for ancestor, _ in path[1:])
        return False
    memo.update(visited)
    return True


def _copy_memoryview(ref):
    data = ref.tobytes()
    backing = data if ref.readonly else bytearray(data)
    snapshot = memoryview(backing)
    layout = ref.format, ref.shape
    if (snapshot.format, snapshot.shape) == layout:
        return snapshot
    try:
        return snapshot.cast(*layout)
    except (TypeError, ValueError):
        if ref.readonly and type(ref.obj) is bytes:
            return ref
        ctypes = sys.modules.get("ctypes")
        scalar_type = getattr(ctypes, "_CData", getattr(ctypes, "_SimpleCData", ()))
        if not ref.shape and isinstance(ref.obj, scalar_type) and ctypes.sizeof(type(ref.obj)) == len(data):
            snapshot = memoryview(type(ref.obj).from_buffer_copy(data))
            if (snapshot.format, snapshot.shape) == layout:
                return snapshot.toreadonly() if ref.readonly else snapshot
        if isinstance(ref.obj, getattr(ctypes, "Array", ())):
            array_type = type(ref.obj)
            if len(data) != ctypes.sizeof(ref.obj) or memoryview(ref.obj).shape != ref.shape:
                while issubclass(array_type, ctypes.Array):
                    array_type = array_type._type_
                for dim in reversed(ref.shape):
                    array_type = array_type * dim
            if ctypes.sizeof(array_type) == len(data):
                snapshot = memoryview(array_type.from_buffer_copy(data))
                if (snapshot.format, snapshot.shape) == layout:
                    return snapshot.toreadonly() if ref.readonly else snapshot
        if isinstance(ref.obj, array):
            copied = array(ref.obj.typecode)
            copied.frombytes(data)
            snapshot = memoryview(copied)
            if (snapshot.format, snapshot.shape) == layout:
                return snapshot.toreadonly() if ref.readonly else snapshot
        numpy = sys.modules.get("numpy")
        if numpy is not None:
            try:
                dtype = ref.obj.dtype if isinstance(ref.obj, numpy.ndarray) else numpy.dtype(ref.format)
                snapshot = memoryview(numpy.frombuffer(backing, dtype=dtype).reshape(ref.shape))
                if (snapshot.format, snapshot.shape) == layout:
                    return snapshot
            except (TypeError, ValueError):
                pass
    raise TypeError(f"Cannot snapshot memoryview with format {ref.format!r} and shape {ref.shape!r}")


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
        memo = _ReferenceMemo()
    key = id(ref)
    if key in memo:
        return memo[key]
    if kind is MappingProxyType:
        return memo.setdefault(key, MappingProxyType(_clone_ref(_proxy_target(ref), memo)))
    if kind is bytearray:
        return memo.setdefault(key, bytearray(ref))
    if kind is array:
        return memo.setdefault(key, copy(ref))
    if isinstance(ref, array):
        clone = array.__new__(kind, ref.typecode, ref)
        memo[key] = clone
        _copy_ref_state(ref, clone, memo)
        return clone
    if kind is memoryview:
        return memo.setdefault(key, _copy_memoryview(ref))
    if kind is slice:
        parts = (ref.start, ref.stop, ref.step)
        cloned = tuple(_clone_ref(value, memo) for value in parts)
        return memo.setdefault(key, ref if all(a is b for a, b in zip(parts, cloned)) else slice(*cloned))
    if kind in _DICT_VIEWS:
        if kind is _DICT_VALUES:
            backing = _DetachedViewDict()
            backing._origin_view = _view_origin(ref)
        else:
            backing = {}
        memo[key] = _DICT_VIEWS[kind](backing)
        backing.update((_clone_ref(name, memo), _clone_ref(value, memo)) for name, value in ref.mapping.items())
        return memo[key]
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
        probe = _ReferenceMemo(memo | {key: ref})
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
    elif _retains_identity(ref, kind):
        # Identity-valued references, such as an ORM entity, must stay attached.
        return ref
    else:
        numpy = sys.modules.get("numpy")
        if isinstance(ref, getattr(numpy, "ndarray", ())):
            clone = ref.copy()
            memo[key] = clone
            if clone.dtype.hasobject:
                masked = isinstance(clone, numpy.ma.MaskedArray)
                original = numpy.ma.getdata(ref) if masked else ref
                data = numpy.ma.getdata(clone) if masked else clone
                if clone.dtype.names:
                    original_fields = [(name, original[name]) for name in clone.dtype.names]
                    for name, values in original_fields:
                        if values.dtype.hasobject:
                            data[name] = _clone_ref(values, memo)
                else:
                    for index in numpy.ndindex(clone.shape):
                        data[index] = _clone_ref(data[index], memo)
            if kind is not numpy.ndarray:
                _copy_ref_state(ref, clone, memo)
            return clone
        if is_dataclass(kind) and kind.__dataclass_params__.frozen:
            if _share_frozen_state(ref, memo, memo.unshareable):
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


def _same_dict_values(left, right, compared):
    return (type(left) is type(right) is _DICT_VALUES
            and _view_origin(left) is _view_origin(right)
            and _equal_mappings(_proxy_target(left.mapping), _proxy_target(right.mapping), compared))


def _equality_target(value):
    while type(value) is MappingProxyType:
        value = _proxy_target(value)
    return value


_MAPPING_EQUALITY = (dict.__eq__, OrderedDict.__eq__, Mapping.__eq__)
_SEQUENCE_EQUALITY = (list.__eq__, tuple.__eq__, deque.__eq__)
_SET_EQUALITY = (set.__eq__, frozenset.__eq__)


def _equal_mappings(left, right, compared):
    if isinstance(left, dict) and isinstance(right, dict):
        if type(left).__eq__ is type(right).__eq__ is OrderedDict.__eq__:
            if tuple(OrderedDict.keys(left)) != tuple(OrderedDict.keys(right)):
                return False
        return dict.__len__(left) == dict.__len__(right) and all(
            dict.__contains__(right, key)
            and _safe_equal(dict.__getitem__(left, key), dict.__getitem__(right, key), compared)
            for key in dict.keys(left))
    return len(left) == len(right) and all(key in right and _safe_equal(left[key], right[key], compared) for key in left)


def _equal_sets(left, right, compared):
    if len(left) != len(right):
        return False
    if _HASH_SCALARS.issuperset(map(type, left)) and _HASH_SCALARS.issuperset(map(type, right)):
        return left == right
    choices = tuple(right)
    edges = [tuple(i for i, candidate in enumerate(choices) if _safe_equal(value, candidate, compared))
             for value in left]
    matched = {}

    def assign(row, seen):
        for column in edges[row]:
            if column in seen:
                continue
            seen.add(column)
            if column not in matched or assign(matched[column], seen):
                matched[column] = row
                return True
        return False

    return all(assign(row, set()) for row in sorted(range(len(edges)), key=lambda row: len(edges[row])))


def _equal_array_data(left, right, numpy, compared):
    if not left.dtype.hasobject:
        return bool(numpy.array_equal(left, right))
    if left.dtype.names:
        return all(_safe_equal(left[name], right[name], compared) for name in left.dtype.names)
    return all(_safe_equal(a, b, compared) for a, b in zip(left.flat, right.flat))


def _equal_arrays(left, right, numpy, compared):
    kind = type(left)
    if kind is not type(right) or left.shape != right.shape or left.dtype != right.dtype:
        return False
    if kind is numpy.ndarray:
        return _equal_array_data(left, right, numpy, compared)
    masked = isinstance(left, numpy.ma.MaskedArray)
    if kind is not numpy.ma.MaskedArray:
        try:
            equal = left == right
        except ValueError:
            if not masked:
                return _equal_array_data(left, right, numpy, compared)
        except RecursionError:
            return False
        else:
            if isinstance(equal, (bool, numpy.bool_)):
                if not masked or not bool(equal):
                    return bool(equal)
            elif not (isinstance(equal, numpy.ndarray) and equal.dtype.kind == "b"
                      and bool(numpy.ma.filled(equal, True).all())):
                return False
            elif not masked:
                return True
    if masked:
        mask = numpy.ma.getmaskarray(left)
        if not numpy.array_equal(mask, numpy.ma.getmaskarray(right)):
            return False
        if mask.dtype.names:
            return all(_safe_equal(left[name], right[name], compared) for name in mask.dtype.names)
        return _equal_array_data(numpy.ma.getdata(left)[~mask], numpy.ma.getdata(right)[~mask], numpy, compared)
    return False


def _safe_equal(left, right, compared=None):
    left_kind, right_kind = type(left), type(right)
    if left_kind in _HASH_SCALARS and right_kind in _HASH_SCALARS:
        return bool(left == right)
    if (left_kind is right_kind is dict and _HASH_SCALARS.issuperset(map(type, left.values()))
            and _HASH_SCALARS.issuperset(map(type, right.values()))):
        return left == right
    values_view = left_kind is _DICT_VALUES or right_kind is _DICT_VALUES
    numpy = sys.modules.get("numpy")
    ndarray = getattr(numpy, "ndarray", ())
    array_value = isinstance(left, ndarray) or isinstance(right, ndarray)
    left_target, right_target = _equality_target(left), _equality_target(right)
    left_eq, right_eq = type(left_target).__eq__, type(right_target).__eq__
    mapping = (left_eq in _MAPPING_EQUALITY and right_eq in _MAPPING_EQUALITY
               and isinstance(left_target, Mapping) and isinstance(right_target, Mapping))
    sequence = left_eq is right_eq and left_eq in _SEQUENCE_EQUALITY
    unordered = left_eq in _SET_EQUALITY and right_eq in _SET_EQUALITY
    items_view = left_kind is right_kind is _DICT_ITEMS
    if not (values_view or array_value or mapping or sequence or unordered or items_view):
        try:
            return bool(left == right)
        except (ValueError, RecursionError):
            return False
    if compared is None:
        compared = set()
    pair = (id(left), id(right))
    if pair in compared:
        return True
    compared.add(pair)
    try:
        if values_view:
            return _same_dict_values(left, right, compared)
        if array_value:
            return _equal_arrays(left, right, numpy, compared)
        if items_view:
            return _equal_mappings(_proxy_target(left.mapping), _proxy_target(right.mapping), compared)
        if mapping:
            return _equal_mappings(left_target, right_target, compared)
        if unordered:
            return _equal_sets(left_target, right_target, compared)
        return len(left_target) == len(right_target) and all(
            _safe_equal(a, b, compared) for a, b in zip(left_target, right_target))
    finally:
        compared.remove(pair)


def _contains(buckets, item, key):
    matches = buckets.get(key)
    if matches and any(_safe_equal(existing, item) for existing in matches):
        return True
    # A value without a reliable key may compare equal to a keyed value.
    if key is None:
        return any(_safe_equal(existing, item) for other, bucket in buckets.items()
                   if other is not None for existing in bucket)
    fallback = buckets.get(None)
    return bool(fallback and any(_safe_equal(existing, item) for existing in fallback))


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
            if all(index is not None and _safe_equal(self.choices[index], ref) for index, ref in zip(indices, selected)):
                checked_rows = set(indices)
        self._set_raw_value(selected, checked_rows, matching_choices=source_choices)

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

    def _set_raw_value(self, selected, checked_rows, *, matching_choices=None):
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
            memo = _ReferenceMemo() if is_dataclass(type(ref)) else None
            snapshot = _clone_ref(ref, memo)
            if memo is not None:
                # Reuse the state inspection, never the detached objects.
                for key in tuple(memo):
                    if id(memo[key]) != key:
                        del memo[key]
            item = item_type(label)
            item.setData(user_role, _clone_ref(ref, memo))
            item.setData(row_role, len(rows))
            item.setToolTip(label)
            item.setFlags(flags)
            item.setCheckState(checked if selected else unchecked)
            add_item(item)
            rows.append(snapshot)
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
                    choice = ref if matching_choices is None else matching_choices[index]
                    if _contains(displayed_buckets, choice, key):
                        continue
                    selected_row = _contains(selected_buckets, choice, key)
                    displayed_buckets.setdefault(key, []).append(choice)
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
