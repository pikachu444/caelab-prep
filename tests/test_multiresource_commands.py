"""Opaque transaction boundaries; mixed-model semantics are tested separately."""
from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from caelab_prep.cae_core import CommandDispatcher, Document, PrepError, Selection, SelectionRef
from caelab_prep.application.analysis_cases import AnalysisCasesResource
from caelab_prep.radioss.deck import DeckResource


@dataclass
class Probe:
    id: str
    value: int
    journal: list = field(repr=False)
    fail: int | None = None
    kind: str = "transaction-probe"

    def snapshot(self): return self.value
    def state_token(self): return str(self.value)
    def prepare_state(self, state):
        self.journal.append(("prepare", self.id, state))
        if type(state) is not int or state < 0: raise ValueError("invalid candidate")
        return state
    def restore(self, state):
        self.journal.append(("restore", self.id, state))
        self.value = state
        if state == self.fail: raise RuntimeError("failed after assignment")


def setup():
    journal = []
    a, b = Probe("a", 1, journal), Probe("b", 2, journal)
    document = Document("Transaction", resources={"a": a, "b": b})
    document.selection = Selection("node", (91,), (SelectionRef("a", "node", 91),))
    document.mark_saved()
    dispatcher = CommandDispatcher(document)
    events = []
    dispatcher.subscribe(events.append)
    return document, dispatcher, a, b, journal, events


def test_every_candidate_validates_before_any_live_restore():
    doc, commands, a, b, journal, events = setup()
    with pytest.raises(ValueError): commands.execute_many({"a": 11, "b": -1}, "invalid pair")
    assert all(kind == "prepare" for kind, _, _ in journal)
    assert (a.value, b.value, doc.revision, doc.dirty, commands.can_undo) == (1, 2, 0, False, False)
    assert events == []


def test_second_restore_failure_rolls_back_failed_resource_and_history():
    doc, commands, a, b, journal, events = setup()
    commands.execute("a", 3, "earlier")
    commands.undo()
    doc.mark_saved()
    before = (doc.revision, doc.tokens(), commands.last_change, doc.selection, doc.resources)
    events.clear(); journal.clear(); b.fail = 22
    with pytest.raises(RuntimeError): commands.execute_many({"a": 11, "b": 22}, "pair")
    assert (a.value, b.value) == (1, 2)
    assert (doc.revision, doc.tokens(), commands.last_change, doc.selection, doc.resources) == before
    assert commands.can_redo and not commands.can_undo and not doc.dirty and not events
    assert journal[-2:] == [("restore", "b", 2), ("restore", "a", 1)]


def test_membership_changes_and_values_have_one_history_event_and_undo():
    doc, commands, a, b, journal, events = setup()
    c = Probe("c", 7, journal)
    observed = []
    commands.subscribe(lambda event: observed.append((set(doc.resources), a.value, doc.resources["c"].value)))
    change = commands.execute_many({"a": 11, "c": 33}, "replace source", additions=(c,), removals=("b",), expected_revision=0)
    assert observed == [({"a", "c"}, 11, 33)]
    assert set(change.resource_ids) == {"a", "b", "c"} and change.revision == 1
    assert len(events) == 1 and doc.dirty
    commands.undo()
    assert doc.resources == {"a": a, "b": b} and a.value == 1 and not doc.dirty
    assert not commands.can_undo and commands.can_redo and len(events) == 2
    commands.redo()
    assert doc.resources == {"a": a, "c": c} and (a.value, c.value) == (11, 33)
    assert doc.revision == 3 and len(events) == 3


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_history_restore_failure_is_atomic(direction):
    doc, commands, a, b, journal, events = setup()
    commands.execute_many({"a": 11, "b": 22}, "pair")
    if direction == "redo": commands.undo()
    before = (doc.revision, doc.tokens(), commands.last_change, commands.can_undo, commands.can_redo, list(events))
    b.fail = 2 if direction == "undo" else 22
    with pytest.raises(RuntimeError): getattr(commands, direction)()
    assert (doc.revision, doc.tokens(), commands.last_change, commands.can_undo, commands.can_redo, events) == before
    assert (a.value, b.value) == ((11, 22) if direction == "undo" else (1, 2))


def test_native_and_case_candidates_share_raw_payload_and_commit_once():
    raw = ("/BEGIN\nmodel\n      2024\n/MAT/LAW1/41\nSteel\n" + f"{7.8e-9:20g}\n{210000:20g}{.3:20g}\n/END\n").encode()
    deck = DeckResource(raw)
    doc = Document("Mixed resources", resources={deck.id: deck})
    cases = AnalysisCasesResource(doc.id)
    doc.resources[cases.id] = cases
    doc.mark_saved()
    commands = CommandDispatcher(doc)
    material = next(card for card in deck.cards if card.keyword.startswith("/MAT/"))
    case_id = str(uuid4())
    case_state = {"state_version": 1, "active_case_id": case_id, "cases": [{"id": case_id,
        "name": "Alternate", "condition_ids": [], "end_time": 1, "output_interval": .1, "time_unit": "ms"}]}
    payload, source_lines = deck.raw, deck._source_lines
    events = []; commands.subscribe(events.append)
    commands.execute_many({deck.id: deck.fields_state(material.id, {"young_modulus": 190000}), cases.id: case_state}, "material and case")
    assert deck.raw is payload and deck._source_lines is source_lines
    assert b"190000" in deck.render() and cases.snapshot()["active_case_id"] == case_id
    assert len(events) == 1 and doc.revision == 1
    commands.undo()
    assert deck.render() == raw and cases.snapshot()["cases"] == [] and not doc.dirty


def test_duplicate_or_stale_transaction_cannot_publish():
    doc, commands, a, b, journal, events = setup()
    with pytest.raises(PrepError): commands.execute_many({"a": 9}, "stale", expected_revision=1)
    with pytest.raises(PrepError): commands.execute_many({}, "duplicate", additions=(a,))
    assert commands.execute_many({"a": 1, "b": 2}, "no change") is None
    assert doc.revision == 0 and not doc.dirty and not events
