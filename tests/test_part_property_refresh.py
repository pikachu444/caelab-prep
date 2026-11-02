"""Repeated inspector/action queries reuse one revision's PART context."""
from pathlib import Path

from caelab_prep.application import PrepSession
from caelab_prep.application.rad_provider import RadProvider

SOURCE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies/beam_shell_tet/model_0000.rad"


def test_part_refresh_reuses_context_but_assignment_history_and_reopen_change_values(tmp_path, monkeypatch):
    session = PrepSession(); session.open_rad(SOURCE)
    provider = RadProvider(session)
    card = next(item for item in session.list_cards() if item["keyword"] == "/PART/9")
    ref = provider.ref_for_card(card)
    original = provider._assignment_fields
    reads = []
    def observed(part):
        reads.append(session.document.revision)
        return original(part)
    monkeypatch.setattr(provider, "_assignment_fields", observed)
    specs = {field.name:field for field in provider.properties(ref)}
    original_material = specs["material"].value
    # Simulate the inspector and two independent action surfaces' real queries.
    assert "part.assign" in provider.available_operations(ref)
    assert "object.edit" in provider.available_operations(ref)
    assert len(reads) == 1
    specs["material"].unit_context["caller_draft"] = "must not leak"
    assert "caller_draft" not in dict((f.name,f) for f in provider.properties(ref))["material"].unit_context
    created = session.create_material("Alternate", 8e-9, 200000, .28)["card_id"]
    session.assign_part(card["id"], material_id=created)
    assigned = dict((f.name,f) for f in provider.properties(ref))["material"].value
    assert assigned.object_id == created and len(reads) == 2
    session.undo()
    assert dict((f.name,f) for f in provider.properties(ref))["material"].value == original_material
    assert len(reads) == 3
    session.redo()
    path = tmp_path / "part.caeprep"; session.save_project(path)
    session.open_project(path)
    assert dict((f.name,f) for f in provider.properties(ref))["material"].value.object_id == created
    assert len(reads) == 4
