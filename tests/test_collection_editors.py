"""Real Qt collection drafts; reading input never submits a document command."""
from array import array
from collections import ChainMap, Counter, OrderedDict, UserDict, defaultdict, deque
from collections.abc import Mapping, Set
import ctypes
from dataclasses import dataclass, field, make_dataclass
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from functools import cached_property
from http.cookies import Morsel
import gc
import os
import sqlite3
from time import perf_counter
from types import MappingProxyType
from typing import NamedTuple
from uuid import UUID
from weakref import ref as weakref
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from caelab_prep.application.contracts import ObjectRef, PropertySpec
from caelab_prep.ui.modeling import OperationPanel
from caelab_prep.ui.widgets.collections import (
    BooleanVectorEdit, IntegerListEdit, NumericTableEdit, ReferenceListEdit,
)
from caelab_prep.ui.widgets.curve import CurveTable
from caelab_prep.ui.widgets.properties import PropertyEditor

pytestmark = pytest.mark.usefixtures("qt_widgets")


def test_integer_ids_preserve_unfinished_input_and_reject_lossy_values():
    editor = IntegerListEdit((101, 205))
    assert editor.value() == (101, 205)
    editor.show(); editor.setFocus(); editor.selectAll()
    QTest.keyClicks(editor, "101, 1e")
    with pytest.raises(ValueError, match="positive integer"):
        editor.value()
    assert editor.raw_value() == "101, 1e"
    for text in ("101 101", "1 001", "0", "-2", "1.0", "True", "nan"):
        editor.set_raw_value(text)
        with pytest.raises(ValueError):
            editor.value()
        assert editor.raw_value() == text
    editor.set_raw_value("101, 205 309\t411")
    assert editor.value() == (101, 205, 309, 411)
    editor.set_raw_value(())
    assert editor.value() == ()


def test_boolean_tuple_updates_one_named_component_and_rejects_bad_restore():
    editor = BooleanVectorEdit((True, False, True), components=("TX", "TY", "TZ"))
    changes = []
    editor.draftChanged.connect(lambda: changes.append(editor.value()))
    editor.show(); QApplication.processEvents()
    QTest.mouseClick(editor.editors[1], Qt.MouseButton.LeftButton)
    assert editor.value() == (True, True, True)
    assert changes == [(True, True, True)]
    assert tuple(box.text() for box in editor.editors) == ("TX", "TY", "TZ")
    for invalid in ((True,), (True, 0, False), (True, False, False, False)):
        with pytest.raises(ValueError, match="3 boolean"):
            editor.set_raw_value(invalid)
        assert editor.value() == (True, True, True)
    editor.set_raw_value((False, False, False))
    assert editor.raw_value() == (False, False, False)
    assert changes == [(True, True, True)]  # restoring a draft is not an edit


def test_reference_checks_use_value_identity_and_retain_missing_reference():
    first = ObjectRef("doc", "include-a", "part-a", "rad-card", "/PART/902")
    equal_first = ObjectRef("doc", "include-a", "part-a", "rad-card", "/PART/902")
    second = ObjectRef("doc", "include-b", "part-b", "rad-card", "/PART/902")
    editor = ReferenceListEdit((equal_first,), choices=(first, second),
                               choice_labels=("First include part", "Second include part"))
    assert equal_first is not first and editor.value() == (first,)
    changes = []
    editor.draftChanged.connect(lambda: changes.append(editor.raw_value()))
    editor.list.item(1).setCheckState(Qt.CheckState.Checked)
    assert editor.value() == (first, second) and changes == [(first, second)]
    missing = ObjectRef("doc", "other", "gone", "rad-card", "/PART/999")
    editor.set_raw_value((equal_first, missing))
    assert editor.raw_value() == (first, missing)
    assert editor.list.item(2).text() == "Unavailable: /PART/999"
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    editor.list.item(2).setCheckState(Qt.CheckState.Unchecked)
    assert editor.value() == (first,)


def test_property_editor_round_trips_nested_references():
    first = {"path": ["shells", 201], "identity": {"source": "deck", "element": 201}}
    second = {"identity": {"element": 301, "source": "deck"}, "path": ["solids", 301]}
    reordered = {"identity": {"element": 201, "source": "deck"}, "path": ["shells", 201]}
    editor = PropertyEditor()
    editor.set_fields((PropertySpec("members", "Members", (reordered,), kind="references",
                                    choices=(first, second)),))
    control = editor.editors["members"]
    assert control.list.count() == 2
    assert control.value() == (first,)
    control.set_raw_value((second,))
    assert control.value() == (second,)


def test_reference_buckets_resolve_equality_with_colliding_unhashable_values():
    class Reference:
        def __init__(self, source):
            self.source = source

        def __repr__(self):
            return "Reference"

        def __eq__(self, other):
            return isinstance(other, Reference) and self.source == other.source

    first, second, missing = (Reference(source) for source in ("first", "second", "missing"))
    editor = ReferenceListEdit((Reference("second"),), choices=(first, second))
    assert editor.list.count() == 2
    assert editor.value() == (second,)
    editor.set_raw_value((Reference("second"), missing))
    assert editor.raw_value() == (second, missing)
    assert editor.list.item(2).text() == "Unavailable: Reference"
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()


def test_reference_buckets_match_equal_numeric_values_in_nested_references():
    first = {"id": 201, "path": ["shells", {"active": True}]}
    draft = {"path": ["shells", {"active": 1}], "id": 201.0}
    editor = ReferenceListEdit((draft,), choices=(first,))
    assert editor.list.count() == 1
    value, = editor.value()
    assert value == first and type(value["id"]) is int


@pytest.mark.parametrize("frozen", (False, True))
@pytest.mark.parametrize("nested", (False, True))
def test_reference_labels_do_not_affect_dataclass_equality(frozen, nested):
    @dataclass(frozen=frozen)
    class Reference:
        identifier: int
        label: str = field(compare=False)

    choice = Reference(201, "Original label")
    selected = Reference(201, "New label")
    if nested:
        choice = {"path": [choice]}
        selected = {"path": [selected]}
    editor = ReferenceListEdit((selected,), choices=(choice,))
    assert editor.list.count() == 1
    assert editor.value() == (choice,)


@pytest.mark.parametrize("equivalent", (Decimal("201"), Fraction(201, 1), 201.0))
@pytest.mark.parametrize("nested", (False, True))
def test_reference_buckets_accept_python_numeric_equality(equivalent, nested):
    choice = 201
    if nested:
        choice = {"path": ["shells", 201]}
        equivalent = {"path": ["shells", equivalent]}
    editor = ReferenceListEdit((equivalent,), choices=(choice,))
    assert editor.list.count() == 1
    assert editor.value() == (choice,)


class _ContainerReference(NamedTuple):
    ids: frozenset


@pytest.mark.parametrize("first, second", (
    ((frozenset({201}),), ({201},)),
    (_ContainerReference(frozenset({201})), ({201},)),
    ({"path": [{"ids": frozenset({Decimal("201")})}]}, {"path": [{"ids": {Fraction(201, 1)}}]}),
))
@pytest.mark.parametrize("reverse", (False, True))
def test_reference_buckets_match_equal_container_representations(first, second, reverse):
    choice, selected = (second, first) if reverse else (first, second)
    assert choice == selected
    editor = ReferenceListEdit((selected,), choices=(choice,))
    assert editor.list.count() == 1
    assert editor.value() == (choice,)


class _FrozenDict(dict):
    def __hash__(self):
        return hash(frozenset(self.items()))


class _ReadOnlySet(Set):
    def __init__(self, *values):
        self.values = values

    def __contains__(self, value):
        return value in self.values

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


@pytest.mark.parametrize("other", (
    MappingProxyType(_FrozenDict(id=201)), {"id": 201}, OrderedDict(id=Decimal("201")),
    defaultdict(int, id=201), Counter(id=201), UserDict(id=201), ChainMap({"id": 201}),
))
@pytest.mark.parametrize("reverse", (False, True))
def test_reference_editor_matches_equal_mapping_representations(other, reverse):
    choice, selected = _FrozenDict(id=201), other
    if reverse:
        choice, selected = selected, choice
    for first, second in ((choice, selected), ([(choice,)], [(selected,)])):
        assert first == second
        editor = ReferenceListEdit((second,), choices=(first,))
        assert editor.list.count() == 1
        assert editor.value() == (first,)


@pytest.mark.parametrize("reverse", (False, True))
def test_reference_editor_matches_standard_set_protocol(reverse):
    choice, selected = _ReadOnlySet(201), frozenset({Decimal("201")})
    if reverse:
        choice, selected = selected, choice
    editor = ReferenceListEdit(((selected,),), choices=((choice,),))
    assert editor.list.count() == 1
    assert editor.value() == ((choice,),)


@pytest.mark.parametrize("proxy", (False, True))
def test_reference_editor_keeps_counter_equality_with_omitted_zero_counts(proxy):
    choice = Counter(id=201)
    selected = Counter(id=201, extra=0)
    if proxy:
        selected = MappingProxyType(selected)
    editor = ReferenceListEdit((selected,), choices=(choice,))
    assert editor.list.count() == 1
    assert editor.value() == (choice,)


class _CaseInsensitiveDict(dict):
    def __eq__(self, other):
        if not isinstance(other, Mapping):
            return NotImplemented
        return {key.casefold(): value for key, value in self.items()} == {
            key.casefold(): value for key, value in other.items()}


@pytest.mark.parametrize("mapping_type", ("standalone", "requests"))
@pytest.mark.parametrize("proxy", (False, True))
@pytest.mark.parametrize("reverse", (False, True))
def test_reference_editor_matches_case_insensitive_mappings(mapping_type, proxy, reverse):
    if mapping_type == "requests":
        factory = pytest.importorskip("requests.structures").CaseInsensitiveDict
    else:
        factory = _CaseInsensitiveDict
    choice, selected = factory({"ID": 201}), factory({"id": 201})
    if proxy:
        choice, selected = MappingProxyType(choice), MappingProxyType(selected)
    if reverse:
        choice, selected = selected, choice
    for first, second in ((choice, selected), ({"path": [choice]}, {"path": [selected]})):
        assert first == second
        editor = ReferenceListEdit((second,), choices=(first,))
        assert editor.list.count() == 1
        assert editor.value() == (first,)


class _TupleLikeRow:
    def __eq__(self, other):
        if isinstance(other, _TupleLikeRow):
            return True
        return (201,) == other

    def __hash__(self):
        return hash((201,))


@pytest.mark.parametrize("row_type", ("standalone", "sqlalchemy"))
@pytest.mark.parametrize("reverse", (False, True))
def test_reference_editor_matches_hashable_rows_and_tuples(row_type, reverse):
    if row_type == "sqlalchemy":
        sqlalchemy = pytest.importorskip("sqlalchemy")
        engine = sqlalchemy.create_engine("sqlite://")
        try:
            with engine.connect() as connection:
                row = connection.execute(sqlalchemy.text("SELECT 201 AS id")).one()
        finally:
            engine.dispose()
    else:
        row = _TupleLikeRow()
    choice, selected = (201,), row
    if reverse:
        choice, selected = selected, choice
    for first, second in ((choice, selected), ({"path": [choice]}, {"path": [selected]})):
        assert first == second
        editor = ReferenceListEdit((second,), choices=(first,))
        assert editor.list.count() == 1
        assert editor.value() == (first,)


@pytest.mark.parametrize("fallback_choice", (False, True))
def test_reference_fallback_can_match_a_hashable_value(fallback_choice):
    class Reference:
        def __eq__(self, other):
            return isinstance(other, Reference) or other == 201

    selected, choice = Reference(), 201
    if fallback_choice:
        selected, choice = choice, selected
    editor = ReferenceListEdit((selected,), choices=(choice,))
    assert editor.list.count() == 1
    result, = editor.value()
    assert type(result) is type(choice)


def test_reference_editor_isolates_nested_mutable_choices_and_results():
    reference = {"element": 101, "nested": (["picked"], {"selected"})}
    expected = {"element": 101, "nested": (["picked"], {"selected"})}
    editor = ReferenceListEdit((reference,), choices=(reference,))
    reference["nested"][0].append("external")
    raw, = editor.raw_value()
    raw["nested"][1].add("external")
    value, = editor.value()
    value["element"] = 102
    assert editor.value() == (expected,)


@pytest.mark.parametrize("mapping", (UserDict, OrderedDict, MappingProxyType))
def test_reference_editor_keeps_mutated_mapping_draft_unavailable(mapping):
    source = {"local_id": [404]}
    editor = ReferenceListEdit((mapping(source),), choices=(mapping({"local_id": [101]}),))
    label = next(editor.list.item(i).text() for i in range(editor.list.count())
                 if editor.list.item(i).text().startswith("Unavailable:"))
    assert "404" in label
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    source["local_id"][0] = 101
    [draft] = editor.raw_value()
    draft["local_id"][0] = 101
    assert editor.raw_value()[0]["local_id"] == [404]
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()


@pytest.mark.parametrize("mapping", (UserDict, OrderedDict))
def test_reference_editor_keeps_returned_mapping_edits_detached(mapping):
    editor = ReferenceListEdit((mapping(local_id=404),), choices=(mapping(local_id=101),))
    editor.raw_value()[0]["local_id"] = 101
    assert editor.raw_value()[0]["local_id"] == 404
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()


@pytest.mark.parametrize("proxy", (False, True))
def test_reference_editor_isolates_mutable_sqlite_row_values(proxy):
    sqlite3.register_converter("PREP_REFERENCE_LIST", lambda value: [int(value)])
    connection = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_COLNAMES)
    try:
        connection.row_factory = sqlite3.Row
        choice, stale, matching = (
            connection.execute('SELECT ? AS "nested [PREP_REFERENCE_LIST]"', (value,)).fetchone()
            for value in (101, 404, 101)
        )
    finally:
        connection.close()
    wrap = MappingProxyType if proxy else lambda row: row
    editor = ReferenceListEdit((wrap(stale),), choices=(wrap(choice),))
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    editor.raw_value()[0]["nested"][0] = 101
    stale["nested"][0] = 101
    assert editor.raw_value()[0]["nested"] == [404]
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    editor.set_raw_value((wrap(matching),))
    assert editor.list.count() == 1
    assert editor.value()[0] == wrap(matching)


@pytest.mark.parametrize("container", ("dataclass", "chain-map", "named-tuple"))
def test_reference_property_editor_clones_objects_containing_mapping_proxies(container):
    @dataclass
    class DataReference:
        mapping: Mapping

    class TupleReference(NamedTuple):
        mapping: Mapping

    wrap, read = {
        "dataclass": (DataReference, lambda ref: ref.mapping),
        "chain-map": (ChainMap, lambda ref: ref),
        "named-tuple": (TupleReference, lambda ref: ref.mapping),
    }[container]
    nested = [101]
    ref = wrap(MappingProxyType({"nested": nested}))
    editor = PropertyEditor()
    editor.set_fields((PropertySpec("members", "Members", (ref,), kind="references", choices=(ref,)),))
    field = editor.editors["members"]
    assert field.list.count() == 1
    draft, = field.value()
    assert type(draft) is type(ref)
    read(draft)["nested"][0] = 404
    nested[0] = 205
    assert read(field.value()[0])["nested"] == [101]


def test_reference_editor_preserves_sqlalchemy_row_and_bound_entity():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    orm = pytest.importorskip("sqlalchemy.orm")
    base = orm.declarative_base()

    class Shell(base):
        __tablename__ = "shells"
        id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)

    engine = sqlalchemy.create_engine("sqlite://")
    try:
        base.metadata.create_all(engine)
        with orm.Session(engine) as session:
            shell = Shell(id=201)
            session.add(shell)
            row = session.execute(sqlalchemy.select(Shell)).one()
            for selected, choice in ((row, row), (tuple(row), row), (row, tuple(row))):
                editor = ReferenceListEdit((selected,), choices=(choice,))
                assert editor.list.count() == 1
                assert editor.value()[0] is choice
                assert editor.value()[0][0] is shell
                assert orm.object_session(editor.value()[0][0]) is session
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind,value", (("int64", 201), ("bool_", True), ("str_", "shell"),
                                        ("bytes_", b"shell"), ("datetime64", "2026-01-01")))
def test_reference_property_editor_accepts_an_immutable_numpy_scalar(kind, value):
    np = pytest.importorskip("numpy")
    reference = getattr(np, kind)(value)
    editor = PropertyEditor()
    editor.set_fields((PropertySpec("members", "Members", (reference.item(),),
                                    kind="references", choices=(reference,)),))
    field = editor.editors["members"]
    assert field.list.count() == 1
    assert field.value()[0] is reference


def test_reference_editor_accepts_sqlalchemy_row_mapping_and_isolates_mutable_values():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    engine = sqlalchemy.create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            ref = connection.execute(sqlalchemy.text("SELECT 201 AS local_id")).one()._mapping
            editor = ReferenceListEdit(({"local_id": 201},), choices=(ref,))
            assert editor.list.count() == 1
            assert editor.value() == (ref,)
            expression = sqlalchemy.literal([201], type_=sqlalchemy.JSON).label("nodes")
            ref = connection.execute(sqlalchemy.select(expression)).one()._mapping
            editor = ReferenceListEdit((ref,), choices=(ref,))
            draft, = editor.raw_value()
            assert draft[expression] == [201]
            draft["nodes"].append(404)
            ref["nodes"].append(404)
            result, = editor.value()
            assert type(result) is type(ref)
            assert result[expression] == result["nodes"] == [201]
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ("morsel", "html-flat", "html-nested"))
def test_reference_editor_detaches_mutable_dict_subclasses(kind):
    if kind.startswith("html"):
        mapping = pytest.importorskip("bs4.element").HTMLAttributeDict
        values = (["/101"], ["/404"]) if kind == "html-nested" else ("/101", "/404")
        choice, stale = (mapping(path=value) for value in values)
    else:
        choice, stale = Morsel(), Morsel()
        for ref, value in ((choice, "/101"), (stale, "/404")):
            ref.set("shell", "shell", "shell")
            ref["path"] = value
    editor = ReferenceListEdit((stale,), choices=(choice,))
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    draft, = editor.raw_value()
    assert type(draft) is type(stale) and draft is not stale
    if kind == "html-nested":
        draft["path"][0] = "/101"
        assert stale["path"] == editor.raw_value()[0]["path"] == ["/404"]
    else:
        draft["path"] = "/101"
        if kind == "morsel":
            assert draft.key == stale.key == "shell"
        assert stale["path"] == editor.raw_value()[0]["path"] == "/404"
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()


def test_reference_editor_preserves_frozen_row_with_uninitialized_slot():
    @dataclass(frozen=True, slots=True)
    class Reference:
        local_id: int
        _cache: list = field(init=False, repr=False, compare=False)

    ref = Reference(101)
    editor = ReferenceListEdit((ref,), choices=(ref,))
    assert editor.value()[0] is ref
    assert not hasattr(editor.value()[0], "_cache")


@pytest.mark.parametrize("cached", (False, True))
def test_reference_editor_preserves_frozen_cycles_and_detaches_caches(cached):
    @dataclass(frozen=True)
    class Reference:
        local_id: int
        back: object = field(init=False, repr=False, compare=False)

        @cached_property
        def members(self):
            return [self.local_id]

    ref = Reference(101)
    object.__setattr__(ref, "back", ref)
    if cached:
        assert ref.members == [101]
    editor = ReferenceListEdit((ref,), choices=(ref,))
    draft, = editor.raw_value()
    assert draft.back is draft
    if cached:
        draft.members[0] = 404
        assert ref.members == editor.value()[0].members == [101]
    else:
        selected, = editor.value()
        assert selected is not ref and selected.back is selected
        assert "members" not in vars(ref) and "members" not in vars(selected)


@pytest.mark.parametrize("kind", ("bytearray", "memoryview", "dict_keys"))
def test_reference_editor_snapshots_buffers_and_key_views(kind):
    if kind == "dict_keys":
        backing = {"shell": 101, "nested": [101]}
        ref = backing.keys()
    else:
        backing = bytearray(b"X")
        ref = memoryview(backing) if kind == "memoryview" else backing
    editor = ReferenceListEdit((ref,), choices=(ref,))
    value, = editor.value()
    assert type(value) is type(ref) and value == ref
    if kind == "dict_keys":
        assert value.mapping["shell"] == 101
        value.mapping["nested"].append(404)
        backing["nested"].append(405)
        backing["new shell"] = 404
        assert set(editor.value()[0]) == {"shell", "nested"}
        assert editor.value()[0].mapping["nested"] == [101]
    else:
        backing[0] = ord("Y")
        if kind == "bytearray":
            value[0] = ord("Z")
        assert bytes(editor.value()[0]) == b"X"


def test_reference_editor_preserves_endian_buffer_type_and_shape():
    np = pytest.importorskip("numpy")
    allowed = memoryview(np.array([[1065353216]], dtype=">u4"))
    unavailable = memoryview(np.array([[1.0]], dtype=">f4")).toreadonly()
    assert allowed != unavailable and allowed.tobytes() == unavailable.tobytes()
    editor = ReferenceListEdit((unavailable,), choices=(allowed,))
    draft, = editor.raw_value()
    assert (draft.format, draft.shape, draft.readonly) == (unavailable.format, (1, 1), True)
    assert draft == unavailable and draft != allowed
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    editor.set_raw_value((allowed,))
    selected, = editor.value()
    assert selected == allowed and selected.format == allowed.format and selected.shape == (1, 1)
    allowed.obj[0, 0] = 0
    assert editor.value()[0].tobytes() != allowed.tobytes()


@pytest.mark.parametrize("kind", ("ctypes", "ctypes-slice", "ctypes-reshape", "array", "numpy-slice"))
def test_reference_editor_copies_typed_views_of_standard_backings(kind):
    if kind == "ctypes-reshape":
        backing = ((ctypes.c_ubyte * 2) * 2)((101, 102), (103, 104))
        original = memoryview(backing)[:1].toreadonly()
    elif kind == "numpy-slice":
        np = pytest.importorskip("numpy")
        backing = np.array([[101, 102], [103, 104]], dtype=">u4")
        original = memoryview(backing)[::2].toreadonly()
    else:
        backing = (ctypes.c_ubyte * 2)(101, 102) if kind.startswith("ctypes") else array("i", [101, 102])
        original = memoryview(backing).toreadonly()
        if kind.endswith("slice") or kind == "array":
            original = original[1:]
    editor = ReferenceListEdit((original,), choices=(original,))
    result, = editor.value()
    assert result == original
    assert (result.format, result.shape, result.readonly) == (original.format, original.shape, True)
    assert result.obj is not backing


def test_reference_editor_preserves_sqlite_row_containing_frozen_enum():
    class Kind(Enum):
        SHELL = "shell"

    @dataclass(frozen=True)
    class Reference:
        local_id: int
        kind: Kind

    sqlite3.register_converter("PREP_FROZEN_ENUM", lambda value: Reference(int(value), Kind.SHELL))
    with sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        original = connection.execute('select 101 as "member [PREP_FROZEN_ENUM]"').fetchone()
    connection.close()
    result, = ReferenceListEdit((original,), choices=(original,)).value()
    assert result is original and sqlite3.Row.keys(result) == ["member"]


@pytest.mark.parametrize("kind", ("numpy-keys", "array-keys", "dict-values"))
def test_reference_editor_detaches_dictionary_views_with_mutable_values(kind):
    if kind == "numpy-keys":
        backing = {"shell": pytest.importorskip("numpy").array([101, 102])}
    elif kind == "array-keys":
        backing = {"shell": array("i", [101, 102])}
    else:
        backing = {"shell": [101, 102]}
    original = backing.values() if kind == "dict-values" else backing.keys()
    editor = ReferenceListEdit((original,), choices=(original,))
    assert editor.list.count() == 1
    draft, = editor.raw_value()
    draft.mapping["shell"][0] = 404
    assert backing["shell"][0] == 101
    backing["shell"][1] = 405
    result, = editor.value()
    assert type(result) is type(original)
    assert list(result.mapping["shell"]) == [101, 102]
    result.mapping["shell"][0] = 406
    assert list(editor.value()[0].mapping["shell"]) == [101, 102]


def _reference_apply_panel(fields):
    panel = OperationPanel()
    panel.editor.set_fields(fields)
    submitted = []

    def apply():
        try:
            submitted.append(panel.editor.values()["members"])
        except ValueError as error:
            panel.fail(str(error))

    panel.applyRequested.connect(apply)
    return panel, submitted


@pytest.mark.parametrize("view", ("items", "keys", "values"))
def test_reference_apply_isolates_nested_objects_in_array_views(view):
    np = pytest.importorskip("numpy")
    allowed = np.empty(1, dtype=object)
    allowed[0] = [101]
    stale = np.empty(1, dtype=object)
    stale[0] = [404]
    choice = getattr({"id": allowed}, view)()
    selected_key = "stale" if view == "keys" else "id"
    selection = getattr({selected_key: stale}, view)()
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selection,), kind="references", choices=(choice,)),
    ))
    draft, = panel.editor.raw_values()["members"]
    draft.mapping[selected_key][0][0] = 101
    assert stale[0] == [404]
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()
    if view == "items":
        panel.editor.editors["members"].set_raw_value((draft,))
        panel.apply_button.click()
        assert len(submitted) == 1


@pytest.mark.parametrize("kind", ("values", "items", "multi-choice-items"))
def test_reference_apply_keeps_view_drafts_across_property_context_refresh(kind):
    if kind == "values":
        backing = {"id": [101, 102]}
        choice = backing.values()
        choices = (choice, choice)
    else:
        np = pytest.importorskip("numpy")
        backing = {"id": np.array([101, 102])}
        choice = backing.items()
        choices = (choice, {"other": np.array([201, 202])}.items()) if kind == "multi-choice-items" else (choice,)
    spec = PropertySpec("members", "Members", (choice,), kind="references", choices=choices)
    panel, submitted = _reference_apply_panel((spec, PropertySpec("size", "Size", 2, unit_context={"quantity": "length"})))
    assert panel.editor.editors["members"].list.count() == (2 if kind == "multi-choice-items" else 1)
    panel.apply_button.click()
    assert len(submitted) == len(submitted[0]) == 1
    assert panel.editor.refresh_context((spec, PropertySpec("size", "Size", 2, unit_context={"quantity": "area"})))
    panel.editor.editors["size"].setText("2")
    panel.apply_button.click()
    assert len(submitted) == 2 and len(submitted[1]) == 1
    assert list(submitted[1][0].mapping["id"]) == [101, 102]
    if kind == "values":
        draft, = panel.editor.raw_values()["members"]
        draft.mapping["id"].append(404)
        assert backing["id"] == [101, 102]
        panel.editor.editors["members"].set_raw_value((draft,))
        panel.apply_button.click()
        assert len(submitted) == 2 and "no longer available" in panel.error.text()
        distinct = {"id": [101, 102]}.values()
        panel.editor.editors["members"].set_raw_value((distinct,))
        panel.apply_button.click()
        assert len(submitted) == 2


def test_reference_values_draft_keeps_its_original_view_only_for_its_lifetime():
    class Backing(dict):
        pass

    def saved_draft():
        backing = Backing(id=[101])
        view = backing.values()
        editor = ReferenceListEdit((view,), choices=(view,))
        draft, = editor.raw_value()
        editor.deleteLater()
        return draft, weakref(backing), id(view)

    draft, original_backing, original_address = saved_draft()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    assert original_backing() is not None
    new_view = {"id": [101]}.values()
    assert id(new_view) != original_address
    editor = ReferenceListEdit((draft,), choices=(new_view,))
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (draft,), kind="references", choices=(new_view,)),
    ))
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()
    editor.deleteLater()
    panel.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    del editor, panel, draft
    gc.collect()
    assert original_backing() is None


@pytest.mark.parametrize("wrap", (
    lambda view: {"members": view},
    lambda view: MappingProxyType({"members": [view]}),
    lambda view: {"members": (view,)}.items(),
    lambda view: OrderedDict(members=view, other=201),
), ids=("dict", "proxy-list", "items-tuple", "ordered-dict"))
def test_reference_apply_keeps_nested_values_draft_across_context_refresh(wrap):
    view = {"id": [101]}.values()
    choice = wrap(view)
    spec = PropertySpec("members", "Members", (choice,), kind="references", choices=(choice,))
    panel, submitted = _reference_apply_panel((spec, PropertySpec("size", "Size", 2, unit_context={"quantity": "length"})))
    editor = panel.editor.editors["members"]
    editor.set_raw_value(editor.raw_value())
    assert editor.list.count() == 1
    panel.apply_button.click()
    assert len(submitted) == 1 and len(submitted[0]) == 1
    assert panel.editor.refresh_context((spec, PropertySpec("size", "Size", 2, unit_context={"quantity": "area"})))
    panel.editor.editors["size"].setText("2")
    panel.apply_button.click()
    assert len(submitted) == 2 and len(submitted[1]) == 1


def test_reference_nested_view_matching_respects_container_specific_inequality():
    class OwnedList(list):
        def __eq__(self, other):
            return type(self) is type(other) and self.owner == other.owner and super().__eq__(other)

    view = {"id": [101]}.values()
    choice = OwnedList([view])
    stale = OwnedList([view])
    choice.owner, stale.owner = "allowed", "stale"
    ordered = OrderedDict(members=view, other=201)
    reverse = OrderedDict(reversed(ordered.items()))
    for allowed, rejected in ((choice, stale), (ordered, reverse)):
        editor = ReferenceListEdit((rejected,), choices=(allowed,))
        with pytest.raises(ValueError, match="no longer available"):
            editor.value()


@pytest.mark.parametrize("masked", (False, True), ids=("owner", "mask"))
def test_reference_apply_uses_numpy_subclass_equality_and_detaches_state(masked):
    np = pytest.importorskip("numpy")
    if masked:
        choice = np.ma.array([101, 201], mask=[False, True])
        stale = np.ma.array([101, 201], mask=[True, True])
        equivalent = np.ma.array([101, 404], mask=[False, True])
    else:
        class OwnedArray(np.ndarray):
            def __eq__(self, other):
                if type(other) is not type(self) or self.owner != other.owner:
                    return False
                return super().__eq__(other)

        choice, stale, equivalent = (np.array([101, 201]).view(OwnedArray) for _ in range(3))
        choice.owner, stale.owner, equivalent.owner = ["allowed"], ["stale"], ["allowed"]
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (stale,), kind="references", choices=(choice,)),
    ))
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()
    editor = panel.editor.editors["members"]
    editor.set_raw_value((equivalent,))
    panel.apply_button.click()
    result, = submitted[0]
    assert type(result) is type(choice)
    if masked:
        result.mask[0] = True
        assert not editor.value()[0].mask[0] and not choice.mask[0]
    else:
        assert result.owner == ["allowed"]
        result.owner[0] = "stale"
        assert editor.value()[0].owner == ["allowed"] and choice.owner == ["allowed"]


def test_reference_apply_cannot_mutate_choices_through_user_role():
    choice = array("i", [101])
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (choice,), kind="references", choices=(choice,)),
    ))
    editor = panel.editor.editors["members"]
    editor.list.item(0).data(Qt.ItemDataRole.UserRole)[0] = 404
    assert editor.value() == (array("i", [101]),)
    editor.set_raw_value((array("i", [404]),))
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()


@pytest.mark.parametrize("kind", ("first-item-dict", "provider-view", "masked-owner", "nested-array-layout"))
def test_reference_apply_rejects_distinct_provider_values(kind):
    if kind == "first-item-dict":
        class First(dict):
            def __getitem__(self, key):
                return super().__getitem__(key)[0]

        choice = First(picks=array("i", [101, 202]))
        stale = First(picks=array("i", [101, 404]))
    elif kind == "provider-view":
        class ProviderMap(dict):
            _origin_view = None

        choice, stale = ProviderMap(s=1).values(), ProviderMap(s=1).values()
    else:
        np = pytest.importorskip("numpy")
        if kind == "masked-owner":
            class OwnedMask(np.ma.MaskedArray):
                def __eq__(self, other):
                    if type(other) is not type(self) or other.owner != self.owner:
                        return False
                    return super().__eq__(other)

            choice, stale = (np.ma.array([101], mask=[False]).view(OwnedMask) for _ in range(2))
            choice.owner, stale.owner = "A", "B"
        else:
            choice = {"k": np.array([1], dtype=np.int32)}
            stale = {"k": np.array([[1]], dtype=np.float64)}
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (stale,), kind="references", choices=(choice,)),
    ))
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()


@pytest.mark.parametrize("kind", ("record-array", "labeled-array"))
def test_reference_apply_accepts_equal_numpy_subclass_values(kind):
    np = pytest.importorskip("numpy")
    if kind == "record-array":
        choice = np.recarray(1, dtype=[("member", object)])
        choice["member"][0] = np.array([3, 4])
        selected = choice
    else:
        class Labeled(np.ndarray):
            pass

        choice, selected = (np.array([5, 7]).view(Labeled) for _ in range(2))
        choice.label, selected.label = "old", "new"
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    editor = panel.editor.editors["members"]
    assert editor.list.count() == 1
    editor.set_raw_value(editor.raw_value())
    panel.apply_button.click()
    assert len(submitted) == 1
    restored, = submitted[0]
    assert type(restored) is type(choice)
    if kind == "record-array":
        assert restored["member"][0].tolist() == [3, 4]
    else:
        assert restored.label == "old"


def test_reference_apply_detaches_masked_object_cells_in_qt_user_role():
    np = pytest.importorskip("numpy")
    values = np.empty(2, dtype=object)
    values[0], values[1] = [101], [202]
    choice = np.ma.array(values, mask=[False, True])
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (choice,), kind="references", choices=(choice,)),
    ))
    editor = panel.editor.editors["members"]
    editor.list.item(0).data(Qt.ItemDataRole.UserRole).data[1].append(999)
    assert choice.data[1] == [202]
    assert editor.value()[0].data[1] == [202]
    panel.apply_button.click()
    assert submitted[0][0].data[1] == [202]


@pytest.mark.parametrize("wrap", (deque, set, frozenset), ids=("deque", "set", "frozenset"))
def test_reference_apply_restores_values_view_in_container(wrap):
    backing = {"id": [101]}
    choice = wrap((backing.values(),))
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (choice,), kind="references", choices=(choice,)),
    ))
    editor = panel.editor.editors["members"]
    editor.set_raw_value(editor.raw_value())
    assert editor.list.count() == 1
    panel.apply_button.click()
    assert len(submitted) == len(submitted[0]) == 1
    assert list(next(iter(submitted[0][0]))) == [[101]]


def test_reference_apply_refreshes_values_view_from_dict_to_ordered_dict():
    view = {"id": [101]}.values()
    old = {"ref": view}
    new = OrderedDict(ref=view)
    spec = PropertySpec("members", "Members", (old,), kind="references", choices=(old,))
    panel, submitted = _reference_apply_panel((spec, PropertySpec("size", "Size", 2, unit_context={"quantity": "length"})))
    replacement = PropertySpec("members", "Members", (new,), kind="references", choices=(new,))
    assert panel.editor.refresh_context((replacement, PropertySpec("size", "Size", 2, unit_context={"quantity": "area"})))
    panel.editor.editors["size"].setText("2")
    panel.apply_button.click()
    assert len(submitted) == len(submitted[0]) == 1
    assert isinstance(submitted[0][0], OrderedDict)
    assert list(submitted[0][0]["ref"]) == [[101]]


@pytest.mark.parametrize("masked", (False, True), ids=("ndarray", "masked-array"))
def test_reference_apply_rejects_array_subclass_equality_error(masked):
    np = pytest.importorskip("numpy")
    base = np.ma.MaskedArray if masked else np.ndarray

    class OwnedArray(base):
        def __eq__(self, other):
            if self.owner != other.owner:
                raise ValueError("array owners differ")
            return super().__eq__(other)

    make_array = np.ma.array if masked else np.array
    choice, selected = (make_array([101]).view(OwnedArray) for _ in range(2))
    choice.owner, selected.owner = "A", "B"
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()


@pytest.mark.parametrize("raises", (False, True), ids=("returns-false", "value-error"))
def test_reference_apply_rejects_ufunc_owner_mismatch(raises):
    np = pytest.importorskip("numpy")

    class OwnedArray(np.ndarray):
        def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
            if ufunc is np.equal and method == "__call__":
                if raises and inputs[0].owner != inputs[1].owner:
                    raise ValueError("incompatible owners")
                return np.full(self.shape, inputs[0].owner == inputs[1].owner)
            return NotImplemented

    choice, mismatch, match = (np.array([101, 101]).view(OwnedArray) for _ in range(3))
    choice.owner, mismatch.owner, match.owner = "A", "B", "A"
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (mismatch,), kind="references", choices=(choice,)),
    ))
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()
    panel.editor.editors["members"].set_raw_value((match,))
    panel.apply_button.click()
    assert len(submitted) == 1 and submitted[0][0].owner == "A"


@pytest.mark.parametrize("kind", ("ndarray-function", "masked-function", "masked-object"))
def test_reference_apply_matches_passive_numpy_subclasses(kind):
    np = pytest.importorskip("numpy")
    if kind == "ndarray-function":
        class Passive(np.ndarray):
            def __array_function__(self, func, types, args, kwargs):
                return NotImplemented

        make_array = lambda: np.array([1, 2]).view(Passive)
    elif kind == "masked-function":
        class Passive(np.ma.MaskedArray):
            def __array_function__(self, func, types, args, kwargs):
                return NotImplemented

        make_array = lambda: np.ma.array([1, 2]).view(Passive)
    else:
        class Passive(np.ma.MaskedArray):
            pass

        def make_array():
            values = np.empty(1, dtype=object)
            values[0] = np.array([1, 2])
            return np.ma.array(values, mask=[False]).view(Passive)

    choice, selected = make_array(), make_array()
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    assert panel.editor.editors["members"].list.count() == 1
    panel.apply_button.click()
    assert len(submitted) == 1 and type(submitted[0][0]) is Passive
    saved = np.asarray(submitted[0][0])
    assert (saved[0] if saved.dtype.hasobject else saved).tolist() == [1, 2]


def test_reference_apply_matches_mixed_sets_by_element_hash():
    class Member:
        def __init__(self, number):
            self.number = number

        def __hash__(self):
            return hash(self.number)

        def __eq__(self, other):
            return self.number == other.number

    choice, selected = ({1, Member(2)} for _ in range(2))
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    assert panel.editor.editors["members"].list.count() == 1
    panel.apply_button.click()
    assert submitted == [(choice,)]


@pytest.mark.parametrize("zero_on_choice", (False, True), ids=("selected-zero", "choice-zero"))
def test_reference_apply_matches_counter_array_counts_and_missing_zeros(zero_on_choice):
    np = pytest.importorskip("numpy")
    choice = Counter(a=np.array([1, 2]))
    selected = Counter(a=np.array([1, 2]))
    (choice if zero_on_choice else selected)["missing"] = 0
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    editor = panel.editor.editors["members"]
    assert editor.list.count() == 1
    panel.apply_button.click()
    restored, = submitted[0]
    assert isinstance(restored, Counter) and restored["a"].tolist() == [1, 2]
    editor.set_raw_value((Counter(a=np.array([1, 3])),))
    panel.apply_button.click()
    assert len(submitted) == 1 and "no longer available" in panel.error.text()


@pytest.mark.parametrize("kind", ("strict-equality", "hidden-keys"))
def test_reference_apply_rejects_distinct_counter_subclasses(kind):
    if kind == "strict-equality":
        class Strict(Counter):
            __eq__ = dict.__eq__

        choice, selected = Counter(a=1), Strict(a=1, b=0)
    else:
        class Index(Counter):
            def keys(self):
                return {}.keys()

        choice, selected = Index(a=1), Index(a=2)
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()


def test_reference_apply_formats_mapping_proxy_of_array_counter():
    np = pytest.importorskip("numpy")
    choice, selected = (MappingProxyType(Counter(a=np.array([1, 2]), b=0)) for _ in range(2))
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    assert panel.editor.editors["members"].list.count() == 1
    panel.apply_button.click()
    restored, = submitted[0]
    assert isinstance(restored, MappingProxyType) and restored["a"].tolist() == [1, 2]


@pytest.mark.parametrize("reverse", (False, True))
def test_reference_apply_matches_hashed_abstract_set_of_values_views(reverse):
    class H(Set):
        def __init__(self, members):
            self.members = frozenset(members)

        def __len__(self):
            return len(self.members)

        def __iter__(self):
            return iter(self.members)

        def __contains__(self, item):
            return item in self.members

        __hash__ = Set._hash

    view = {"id": [101]}.values()
    plain, abstract = {frozenset([view])}, {H([view])}
    choice, selected = (abstract, plain) if reverse else (plain, abstract)
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    editor = panel.editor.editors["members"]
    assert editor.list.count() == 1
    editor.set_raw_value(editor.raw_value())
    panel.apply_button.click()
    assert len(submitted) == 1
    values, = submitted[0]
    wrapped, = values
    restored, = wrapped
    assert list(restored) == [[101]]


def test_reference_apply_matches_abstract_set_with_unhashable_members():
    class ListBacked(Set):
        def __init__(self, members):
            self.members = list(members)

        def __len__(self):
            return len(self.members)

        def __iter__(self):
            return iter(self.members)

        def __contains__(self, item):
            return item in self.members

    choice = ListBacked([{"id": 101}, {"id": 205}])
    selected = ListBacked([{"id": 205}, {"id": 101}])
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    panel.apply_button.click()
    assert submitted == [(choice,)]


def test_reference_apply_ignores_backing_order_for_dict_items():
    choice = dict.items(OrderedDict(a=1, b=2))
    selected = dict.items(OrderedDict(b=2, a=1))
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (selected,), kind="references", choices=(choice,)),
    ))
    assert panel.editor.editors["members"].list.count() == 1
    panel.apply_button.click()
    assert submitted == [(choice,)]


def test_reference_editor_matches_nested_values_views_in_hashed_sets():
    view = {"id": [101]}.values()
    choice = {(frozenset((view,)),)}
    editor = ReferenceListEdit((choice,), choices=(choice,))
    editor.set_raw_value(editor.raw_value())
    assert editor.list.count() == 1
    values, = editor.value()
    (views,), = values
    restored, = views
    assert list(restored) == [[101]]


def test_reference_editor_matches_512_tuple_set_items_quickly():
    choice = {("shell", index) for index in range(512)}
    selected = {("shell", index) for index in reversed(range(512))}
    start = perf_counter()
    editor = ReferenceListEdit((selected,), choices=(choice,))
    result = editor.value()
    elapsed = perf_counter() - start
    assert result == (choice,) and editor.list.count() == 1
    assert elapsed < .05, f"Opening and validating the 512-element set took {elapsed * 1000:.1f} ms"


def test_reference_apply_preserves_array_subclass_equality():
    class OwnedArray(array):
        def __eq__(self, other):
            return type(self) is type(other) and self.owner == other.owner and super().__eq__(other)

    choice = OwnedArray("i", [101])
    stale = OwnedArray("i", [101])
    choice.owner, stale.owner = "allowed", "stale"
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (stale,), kind="references", choices=(choice,)),
    ))
    draft, = panel.editor.raw_values()["members"]
    assert type(draft) is OwnedArray and draft.owner == "stale" and not draft == choice
    panel.apply_button.click()
    assert not submitted and "no longer available" in panel.error.text()
    panel.editor.editors["members"].set_raw_value((choice,))
    panel.apply_button.click()
    assert len(submitted) == 1 and type(submitted[0][0]) is OwnedArray


@pytest.mark.parametrize("invalid", (float("nan"), Decimal("NaN")), ids=("float", "decimal"))
def test_reference_apply_rejects_nonreflexive_singleton_before_and_after_restore(invalid):
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (invalid,), kind="references", choices=(invalid,)),
    ))
    for _ in range(2):
        panel.apply_button.click()
        assert not submitted and "no longer available" in panel.error.text()
        panel.editor.editors["members"].set_raw_value(panel.editor.raw_values()["members"])


def test_reference_apply_detaches_zero_dimensional_ctypes_scalar_view():
    backing = ctypes.c_int(101)
    original = memoryview(backing).toreadonly()
    panel, submitted = _reference_apply_panel((
        PropertySpec("members", "Members", (original,), kind="references", choices=(original,)),
    ))
    panel.apply_button.click()
    restored, = submitted[0]
    assert restored == original
    assert (restored.format, restored.shape, restored.readonly) == (original.format, (), True)
    backing.value = 404
    assert restored.obj is not backing
    assert restored.obj.value == 101


@pytest.mark.parametrize("depth", (8, 16, 32))
@pytest.mark.parametrize("leaf", ("mutable", "enum"))
@pytest.mark.parametrize("mixed", (False, True), ids=("slots", "mixed"))
def test_reference_editor_visits_frozen_chain_linearly(monkeypatch, depth, leaf, mixed):
    from caelab_prep.ui.widgets import collections

    reads = slot_reads = attribute_reads = 0

    class Kind(Enum):
        SHELL = "shell"

    class Node:
        __slots__ = ()

        def __getattribute__(self, name):
            nonlocal attribute_reads
            attribute_reads += name == "parent"
            return object.__getattribute__(self, name)

    @dataclass(frozen=True)
    class Plain(Node):
        parent: object

    @dataclass(frozen=True, slots=True)
    class Slot(Node):
        parent: object

    original = collections._frozen_state_values
    original_slots = collections._ref_slots

    def values(ref, memo):
        nonlocal reads
        for value in original(ref, memo):
            reads += isinstance(ref, (Slot, Plain))
            yield value

    def count_slots(ref):
        nonlocal slot_reads
        for member, value in original_slots(ref):
            slot_reads += isinstance(ref, Slot) and member.__name__ == "parent"
            yield member, value

    node = payload = [101] if leaf == "mutable" else Kind.SHELL
    for index in range(depth):
        node = (Plain if mixed and index % 2 else Slot)(node)
    monkeypatch.setattr(collections, "_frozen_state_values", values)
    monkeypatch.setattr(collections, "_ref_slots", count_slots)
    result, = ReferenceListEdit((node,), choices=(node,)).value()
    assert reads <= 4 * depth
    assert slot_reads + attribute_reads <= 4 * depth
    if leaf == "enum":
        assert result is node
    else:
        for _ in range(depth):
            result = result.parent
        result[0] = 404
        assert payload == [101]


def test_reference_editor_does_not_retain_generated_frozen_types():
    def closed_form(index):
        kind = make_dataclass(f"GeneratedReference{index}", [("member", int)], frozen=True)
        original = kind(index)
        editor = ReferenceListEdit((original,), choices=(original,))
        assert editor.value()[0] == original
        editor.deleteLater()
        return weakref(kind)

    classes = [closed_form(index) for index in range(20)]
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    assert sum(kind() is not None for kind in classes) == 0


def test_reference_editor_leaves_cold_cached_property_on_its_own_instance():
    class Members:
        @cached_property
        def members(self):
            return [self.local_id]

    @dataclass(frozen=True)
    class Reference(Members):
        local_id: int

    ref = Reference(101)
    editor = ReferenceListEdit((ref,), choices=(ref,))
    draft, = editor.raw_value()
    draft.members[0] = 404
    assert "members" not in vars(ref)
    assert editor.value()[0].members == [101]


def test_reference_editor_supports_immutable_ranges_in_reference_state():
    @dataclass(frozen=True)
    class Reference:
        local_id: int

        @cached_property
        def members(self):
            return range(self.local_id, self.local_id + 2)

    class ReadonlyMapping(Mapping):
        def __init__(self, values):
            self.values_range = values

        def __getitem__(self, index):
            return self.values_range[index]

        def __iter__(self):
            return iter(range(len(self.values_range)))

        def __len__(self):
            return len(self.values_range)

    ref = Reference(101)
    expected = ref.members
    assert ReferenceListEdit((ref,), choices=(ref,)).value()[0].members == expected
    mapping = ReadonlyMapping(expected)
    assert ReferenceListEdit((mapping,), choices=(mapping,)).value()[0] == {0: 101, 1: 102}


def test_reference_editor_reads_nested_frozen_slots_once_per_snapshot(monkeypatch):
    from caelab_prep.ui.widgets import collections

    reads = 0

    @dataclass(frozen=True, slots=True)
    class Link:
        parent: object

        def __getattribute__(self, name):
            nonlocal reads
            reads += name == "parent"
            return object.__getattribute__(self, name)

    original_slots = collections._ref_slots

    def count_slot_reads(ref):
        nonlocal reads
        for member, value in original_slots(ref):
            reads += isinstance(ref, Link) and member.__name__ == "parent"
            yield member, value

    monkeypatch.setattr(collections, "_ref_slots", count_slot_reads)
    chain = None
    for _ in range(16):
        chain = Link(chain)
    editor = ReferenceListEdit((chain,), choices=(chain,))
    assert editor.value()[0] is chain
    assert reads <= 100


def test_reference_editor_handles_frozendict_choices_without_mutating_them():
    immutable_dict = pytest.importorskip("frozendict").frozendict
    choice = {"local_id": 101}
    nested = [404]
    other = immutable_dict(local_id=404)
    ref = immutable_dict(nodes=nested)
    editor = ReferenceListEdit((choice, ref), choices=(choice, other, ref))
    assert editor.list.count() == 3
    assert editor.value() == (choice, ref)
    nested[0] = 101
    editor.raw_value()[1]["nodes"].append(101)
    assert editor.value() == (choice, {"nodes": [404]})


def test_reference_editor_keeps_identity_valued_dataclass():
    @dataclass(eq=False)
    class Reference:
        local_id: int

    ref = Reference(201)
    editor = ReferenceListEdit((ref,), choices=(ref,))
    assert editor.list.count() == 1
    assert editor.value()[0] is ref


def test_reference_editor_keeps_sqlalchemy_identity_valued_mapped_dataclass():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    orm = pytest.importorskip("sqlalchemy.orm")

    class Base(orm.MappedAsDataclass, orm.DeclarativeBase, eq=False):
        pass

    class Shell(Base, eq=False):
        __tablename__ = "shells"
        id: orm.Mapped[int] = orm.mapped_column(primary_key=True)

    engine = sqlalchemy.create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        with orm.Session(engine) as session:
            ref = Shell(id=201)
            session.add(ref)
            session.flush()
            editor = ReferenceListEdit((ref,), choices=(ref,))
            assert editor.list.count() == 1
            assert editor.value()[0] is ref
            assert orm.object_session(editor.value()[0]) is session
    finally:
        engine.dispose()


@pytest.mark.parametrize("frozen", (False, True))
def test_reference_editor_preserves_sqlite_row_hash_contract(frozen):
    @dataclass(frozen=frozen, unsafe_hash=True)
    class Reference:
        local_id: int

    sqlite3.register_converter("PREP_HASHABLE_REFERENCE", lambda value: Reference(int(value)))
    connection = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_COLNAMES)
    try:
        connection.row_factory = sqlite3.Row
        row = connection.execute('SELECT 201 AS "ref [PREP_HASHABLE_REFERENCE]"').fetchone()
    finally:
        connection.close()
    editor = ReferenceListEdit((row,), choices=(row,))
    result, = editor.value()
    assert result == row and row == result
    assert {row: "shell"}[result] == "shell"
    if frozen:
        assert result is row
    else:
        assert result["ref"] is not row["ref"]


@pytest.mark.parametrize("reverse", (False, True))
def test_reference_editor_matches_frozen_pydantic_models_and_mapping_proxies(reverse):
    pydantic = pytest.importorskip("pydantic.v1")
    model = pydantic.create_model("ElementReference", __config__=type("Config", (), {"frozen": True}),
                                  local_id=(int, ...))
    proxy, ref = MappingProxyType({"local_id": 201}), model(local_id=201)
    assert proxy == ref and ref == proxy
    choice, selected = (ref, proxy) if reverse else (proxy, ref)
    editor = ReferenceListEdit((selected,), choices=(choice,))
    assert editor.list.count() == 1
    assert editor.value() == (choice,)
    editor.set_raw_value((selected,))
    assert editor.value() == (choice,)


def test_reference_editor_sort_keeps_unavailable_row_and_checked_references():
    editor = ReferenceListEdit(("missing",), choices=("a", "z"), choice_labels=("Zulu", "Alpha"))
    editor.list.sortItems()
    assert editor.raw_value() == ("missing",)
    with pytest.raises(ValueError, match="no longer available"):
        editor.value()
    editor.set_raw_value(("a", "z"))
    editor.list.sortItems()
    assert editor.value() == ("z", "a")


def test_reference_editor_validates_8000_standard_mapping_proxies():
    choices = tuple(MappingProxyType({"local_id": index, "formulation": "SH3N"}) for index in range(8000))
    start = perf_counter()
    editor = ReferenceListEdit(choices, choices=choices)
    selected = editor.value()
    elapsed = perf_counter() - start
    assert selected == choices
    assert elapsed < 1.0, f"Opening and validating the proxy list took {elapsed:.3f} seconds"


@pytest.mark.parametrize("mixed", (False, True), ids=("uuid", "mixed"))
def test_reference_editor_validates_8000_uuids(mixed):
    choices = tuple({"local_id": index} if mixed and index % 2 else UUID(int=index) for index in range(8000))
    start = perf_counter()
    editor = ReferenceListEdit(choices, choices=choices)
    selected = editor.value()
    elapsed = perf_counter() - start
    assert selected == choices
    assert elapsed < .5, f"Opening and validating the UUID list took {elapsed:.3f} seconds"


def test_numeric_table_csv_rows_and_failed_paste_are_uncommitted_drafts():
    editor = NumericTableEdit(((0, 0), (1, 10)), components=("Time", "Force"),
                              minimum_rows=2, maximum_rows=3)
    editor.show(); QApplication.processEvents()
    applied = []
    editor.pointsEdited.connect(applied.append)
    assert editor.apply_button.isHidden() and editor.revert_button.isHidden()
    assert editor.table.horizontalHeaderItem(0).text() == "Time"
    assert editor.paste_text("0,0\n0.2,15\n1,20") == ((0., 0.), (.2, 15.), (1., 20.))
    before = editor.raw_value()
    with pytest.raises(ValueError):
        editor.paste_text("0,0\n0.2,unfinished")
    failed = editor.raw_value()
    assert failed["cells"] == before["cells"]
    assert failed["paste"].endswith("unfinished") and failed["paste_error"]
    restored = NumericTableEdit(minimum_rows=2, maximum_rows=3)
    restored.set_raw_value(failed)
    assert restored.raw_value() == failed
    with pytest.raises(ValueError):
        restored.value()
    editor.set_raw_value(before)
    editor.table.setCurrentCell(2, 0)
    QTest.mouseClick(editor.add_button, Qt.MouseButton.LeftButton)
    assert editor.table.rowCount() == 4
    for column, text in enumerate(("2", "30")):
        editor.table.item(3, column).setText(text)
    with pytest.raises(ValueError, match="at most 3"):
        editor.value()
    QTest.mouseClick(editor.remove_button, Qt.MouseButton.LeftButton)
    assert editor.value() == ((0., 0.), (.2, 15.), (1., 20.))
    editor.table.selectAll()
    QTest.mouseClick(editor.remove_button, Qt.MouseButton.LeftButton)
    assert editor.table.rowCount() == 0 and editor.has_draft()
    with pytest.raises(ValueError, match="at least 2"):
        editor.value()
    assert applied == []


def test_outer_table_value_flushes_open_delegate_without_emitting_apply():
    editor = NumericTableEdit(((0, 0), (1, 10)), minimum_rows=2)
    editor.resize(420, 300); editor.show(); QApplication.processEvents()
    item = editor.table.item(1, 1)
    editor.table.setCurrentItem(item)
    editor.table.editItem(item)
    QApplication.processEvents()
    delegate = editor.table.focusWidget()
    assert isinstance(delegate, QLineEdit)
    delegate.selectAll(); QTest.keyClicks(delegate, "27.5")
    applied = []
    editor.pointsEdited.connect(applied.append)
    assert editor.value() == ((0., 0.), (1., 27.5))
    assert applied == []


def test_regular_curve_row_changes_emit_only_on_explicit_apply():
    table = CurveTable(minimum_points=1)
    table.set_points(((0, 1),))
    table.show(); QApplication.processEvents()
    applied = []
    table.pointsEdited.connect(applied.append)
    QTest.mouseClick(table.add_button, Qt.MouseButton.LeftButton)
    assert table.table.rowCount() == 2 and table.has_draft() and not applied
    with pytest.raises(ValueError):
        table.points()
    table.table.item(1, 0).setText("1")
    table.table.item(1, 1).setText("2")
    assert table.apply_changes()
    assert applied == [((0., 1.), (1., 2.))]
