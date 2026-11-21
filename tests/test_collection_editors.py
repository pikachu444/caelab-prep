"""Real Qt collection drafts; reading input never submits a document command."""
from collections import ChainMap, Counter, OrderedDict, UserDict, defaultdict
from collections.abc import Mapping, Set
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
import os
import sqlite3
from time import perf_counter
from types import MappingProxyType
from typing import NamedTuple
from uuid import UUID
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from caelab_prep.application.contracts import ObjectRef, PropertySpec
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
            expression = sqlalchemy.bindparam("ids", [201], type_=sqlalchemy.JSON).label("nodes")
            ref = connection.execute(sqlalchemy.select(expression)).one()._mapping
            editor = ReferenceListEdit((ref,), choices=(ref,))
            editor.raw_value()[0]["nodes"].append(404)
            ref["nodes"].append(404)
            assert editor.value() == ({"nodes": [201]},)
    finally:
        engine.dispose()


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
