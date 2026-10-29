from dataclasses import dataclass

import pytest

from caelab_prep.cae_core import CommandDispatcher, Document, PrepError


@dataclass
class CounterResource:
    id: str = "counter"
    kind: str = "test-counter"
    value: int = 3

    def snapshot(self): return self.value
    def restore(self, state):
        if state < 0: raise ValueError("negative")
        self.value = state
    def state_token(self): return str(self.value)


def test_generic_core_savepoint_undo_revisions_and_failed_command():
    resource = CounterResource()
    document = Document("Counter", resources={resource.id: resource})
    document.mark_saved()
    dispatcher = CommandDispatcher(document)
    changes = []
    dispatcher.subscribe(changes.append)
    dispatcher.execute(resource.id, 8, "set counter", expected_revision=0)
    assert document.dirty and document.revision == 1
    with pytest.raises(ValueError): dispatcher.execute(resource.id, -1, "bad")
    assert resource.value == 8 and document.revision == 1
    dispatcher.undo()
    assert resource.value == 3 and not document.dirty and document.revision == 2
    dispatcher.redo()
    assert resource.value == 8 and document.revision == 3
    assert [c.revision for c in changes] == [1, 2, 3]
    with pytest.raises(PrepError, match="변경"):
        dispatcher.execute(resource.id, 9, "stale", expected_revision=0)
    assert resource.value == 8 and document.revision == 3


def test_observer_failure_does_not_undo_a_committed_command():
    resource = CounterResource()
    document = Document("Counter", resources={resource.id: resource})
    dispatcher = CommandDispatcher(document)
    def broken(_): raise RuntimeError("view unavailable")
    dispatcher.subscribe(broken)
    dispatcher.execute(resource.id, 4, "set")
    assert resource.value == 4 and document.revision == 1 and dispatcher.can_undo
