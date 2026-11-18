"""Comprehensive D19 (PREP01 live material binding prepare/commit & RPC) tests."""
from __future__ import annotations

from hashlib import sha256
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from caelab_prep.application.live_transport import LiveClient, LiveRemoteError
from caelab_prep.application.material_binding import MaterialBindingManager
from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("latin1"))
    return path


def _build_material_deck(root_dir: Path, *, mass="Mg", length="mm", time_unit="s", include_work_units=True) -> Path:
    _write(
        root_dir / "materials.inc",
        "\n".join(
            [
                "/MAT/LAW1/1",
                "Calibrated Steel Target",
                "            7.85e-09",
                "              210000                 0.3",
                "/MAT/LAW36/2",
                "Existing Plastic Material",
                "             1.1e-09",
                "                2500                0.45",
                "         0         0         0         0         0",
                "                   0                   0",
                "         0         0",
                "         0",
                "",
            ]
        ),
    )
    _write(
        root_dir / "curves.inc",
        "\n".join(
            [
                "/FUNCT/10",
                "Existing Load Curve",
                "                   0                1000",
                "                 0.5                 600",
                "                   5                 400",
                "",
            ]
        ),
    )
    u_row = f"{mass:>20}{length:>20}{time_unit:>20}"
    begin_lines = [
        "#RADIOSS STARTER",
        "/BEGIN",
        "Material Calibration Fixture",
        "      2024         0",
        u_row,
    ]
    if include_work_units:
        begin_lines.append(u_row)
    starter = _write(
        root_dir / "mat_0000.rad",
        "\n".join(
            [
                *begin_lines,
                "/PROP/SHELL/1",
                "Shell 2mm",
                "        24         1         2         2                                       1",
                "                   0                   0                   0                   0               0.015",
                "         0                             2            0.833333                   2         0",
                "/PART/1",
                "Panel 1",
                "         1         1         0",
                "/NODE",
                "         1                   0                   0                   0",
                "         2                  10                   0                   0",
                "         3                  10                  10                   0",
                "/SH3N/1",
                "         1         1         2         3",
                "/GRNOD/NODE/1",
                "Loaded nodes",
                "         1",
                "/CLOAD/1",
                "Condition using FUNCT 10",
                "        10         X         0         0         1                               1                   1",
                "#include materials.inc",
                "#include curves.inc",
                "/END",
                "",
            ]
        ),
    )
    return starter


def _object_ref(session: PrepSession, keyword_prefix: str) -> dict:
    upper = keyword_prefix.upper()
    card = next(c for c in session.list_cards() if c["keyword"].upper().startswith(upper))
    return {
        "document_id": session.document.id,
        "resource_id": card["resource_id"],
        "object_id": card["id"],
        "kind": "rad-card",
        "native_scope": card["keyword"],
    }


def _fields_dict(session: PrepSession, card_id: str) -> dict[str, float]:
    return {row["name"]: row["value"] for row in session.card_fields(card_id)}



def _handle(session):
    return {key: session.describe()[key] for key in ("document_id", "document_epoch", "revision")}


def _request(handle, target, **overrides):
    return {"handle": handle, "target": target, "profile_id": "radioss_law1_elastic_v1", "profile_revision": 1,
            "parameters": {"E": {"value": 205, "unit": "GPa"}, "nu": {"value": 0.29, "unit": "1"},
                           "rho": {"value": 7855, "unit": "kg/m^3"}},
            "curves": [], "evaluation_digest": sha256(b"fixture evaluation").hexdigest(), **overrides}


def _commit(request, prepared):
    return {"plan_id": prepared["plan_id"], "handle": request["handle"], "candidate_hashes": prepared["candidate_hashes"]}


@pytest.mark.parametrize("single_file", [False, True], ids=["include-law1", "single-elast"])
def test_d19_law1_prepare_commit_units_undo_save_export(tmp_path: Path, single_file):
    starter = _build_material_deck(tmp_path)
    materials = tmp_path / "materials.inc"
    if single_file:
        payload = starter.read_bytes().replace(
            b"#include materials.inc\n", materials.read_bytes().replace(b"/MAT/LAW1/1", b"/MAT/ELAST/1")
        ).replace(b"#include curves.inc\n", (tmp_path / "curves.inc").read_bytes())
        starter.write_bytes(payload)
    source_bytes = {path: path.read_bytes() for path in (starter, materials, tmp_path / "curves.inc")}

    session = PrepSession()
    session.open_rad(starter)
    manager = MaterialBindingManager(session)
    handle = _handle(session)
    target = _object_ref(session, "/MAT/ELAST/1" if single_file else "/MAT/LAW1/1")
    card_id = target["object_id"]
    before = {r.id: r.render() for r in session._deck_resources()}
    projection_revision = session.mesh_view()["projection_revision"]
    baseline_fields = _fields_dict(session, card_id)
    card_before = session.card_text(card_id)
    request = _request(handle, target)
    history = []
    session.dispatcher.subscribe(history.append)
    prepared = manager.prepare_apply(**request)
    assert {"plan_id", "handle", "baseline_hashes", "candidate_hashes", "changes_preview",
            "expires_at", "supported", "reason_codes", "work_units", "expires_in_seconds"} <= prepared.keys()
    assert prepared["handle"] == handle
    assert prepared["supported"] and prepared["reason_codes"] == []
    assert prepared["work_units"] == {"mass": "Mg", "length": "mm", "time": "s"}
    assert prepared["expires_in_seconds"] == 60
    assert 0 < prepared["expires_at"] - time.time() <= 60
    assert prepared["baseline_hashes"] == {card_id: sha256(card_before.encode("latin1")).hexdigest()}
    assert "205000.0" in prepared["changes_preview"][0]["diff"]
    assert _handle(session) == handle and not history
    assert {r.id: r.render() for r in session._deck_resources()} == before

    commit = _commit(request, prepared)
    with pytest.raises(PrepError) as bad_hash:
        manager.commit_apply(**{**commit, "candidate_hashes": {card_id: "0" * 64}})
    assert bad_hash.value.code == "hash_mismatch" and not history
    reply = manager.commit_apply(**commit)
    assert reply["status"] == "committed" and reply["command_id"]
    assert reply["handle_after"]["revision"] == handle["revision"] + 1
    assert reply["reason_codes"] == []
    assert reply["evaluation_digest"] == request["evaluation_digest"]
    assert reply["applied_hashes"] == prepared["candidate_hashes"]
    assert len(history) == 1 and history[0].kind == "values"
    assert history[0].resource_ids == (target["resource_id"],)
    assert session.mesh_view()["projection_revision"] == projection_revision
    expected = {"young_modulus": 205000.0, "poisson_ratio": 0.29, "density": 7.855e-9}
    assert _fields_dict(session, card_id) == expected
    assert all(r.render() == before[r.id] for r in session._deck_resources() if r.id != target["resource_id"])

    with pytest.raises(PrepError) as consumed:
        manager.commit_apply(**{**commit, "handle": reply["handle_after"]})
    assert consumed.value.code == "stale_material_plan"
    session.undo()
    assert _fields_dict(session, card_id) == baseline_fields
    assert {r.id: r.render() for r in session._deck_resources()} == before
    session.redo()
    assert _fields_dict(session, card_id) == expected

    project = tmp_path / "calibration.caeprep"
    session.save_project(project)
    restored = PrepSession()
    restored.open_project(project)
    assert _fields_dict(restored, card_id) == expected
    exported = tmp_path / "export" / "mat_0000.rad"
    restored.export_solver_inputs(exported, end_time=.01, output_interval=.002)
    reparsed = PrepSession()
    reparsed.open_rad(exported)
    assert _fields_dict(reparsed, _object_ref(reparsed, target["native_scope"])["object_id"]) == expected
    assert {path: path.read_bytes() for path in source_bytes} == source_bytes


@pytest.mark.parametrize(("override", "code"), [
    ({"profile_id": "radioss_prony_visco_v1"}, "UNSUPPORTED_ATOMIC_APPLY"),
    ({"profile_id": "radioss_law36_plastic_v1"}, "UNSUPPORTED_ATOMIC_APPLY"),
    ({"profile_revision": 2}, "UNSUPPORTED_ATOMIC_APPLY"),
    ({"parameters": {"prony_terms": []}}, "UNSUPPORTED_ATOMIC_APPLY"),
    ({"parameters": {"terms": []}}, "UNSUPPORTED_ATOMIC_APPLY"),
    ({"parameters": {"points": []}}, "UNSUPPORTED_ATOMIC_APPLY"),
    *[({"parameters": {"E": {"value": 200, "unit": "GPa"}, key: 1}}, "UNSUPPORTED_ATOMIC_APPLY")
      for key in ("ignored", "sigma_y", "g1", "tau1", "C1")],
    ({"parameters": {"E": {"value": 200, "unit": "GPa", "points": []}}}, "invalid_request"),
    ({"parameters": {"E": {"value": 200, "unit": "GPa"}, "young_modulus": {"value": 200, "unit": "GPa"}}}, "invalid_request"),
    ({"parameters": {"E": {"value": 200, "unit": ""}}}, "invalid_unit"),
    ({"parameters": {"rho": {"value": 7.8, "unit": "ratio"}}}, "invalid_unit"),
    ({"parameters": {"E": {"value": 10**400, "unit": "GPa"}}}, "invalid_value"),
    ({"parameters": {"E": {"value": 5e-324, "unit": "GPa"}}}, "invalid_value"),
    ({"parameters": {"rho": {"value": sys.float_info.min, "unit": "kg/m^3"}}}, "invalid_value"),
    ({"parameters": {"E": {"value": float("inf"), "unit": "GPa"}}}, "invalid_value"),
    ({"parameters": {"E": {"value": float("nan"), "unit": "GPa"}}}, "invalid_value"),
    ({"parameters": {"E": {"value": sys.float_info.max, "unit": "GPa"}}}, "invalid_value"),
    ({"evaluation_digest": "unknown"}, "invalid_request"),
])
def test_d19_invalid_profile_payload_or_value_does_not_change_document(tmp_path, override, code):
    session = PrepSession()
    session.open_rad(_build_material_deck(tmp_path))
    baseline = session.document.tokens()
    manager = MaterialBindingManager(session)
    with pytest.raises(PrepError) as error:
        manager.prepare_apply(**_request(_handle(session), _object_ref(session, "/MAT/LAW1/1"), **override))
    assert error.value.code == code
    assert session.document.tokens() == baseline
    assert session.dispatcher.last_change is None


@pytest.mark.parametrize("bad_unit", ["", "1", "dimensionless", "-", "ratio"])
def test_d19_nonelastic_curves_rejected_even_when_already_referenced(tmp_path, bad_unit):
    session = PrepSession()
    session.open_rad(_build_material_deck(tmp_path))
    handle = _handle(session)
    manager = MaterialBindingManager(session)
    law1 = _object_ref(session, "/MAT/LAW1/1")
    law36 = _object_ref(session, "/MAT/LAW36/2")
    curve = _object_ref(session, "/FUNCT/10")
    load = _object_ref(session, "/CLOAD/1")
    assert session.condition_values(load["object_id"])["curve_id"] == curve["object_id"]
    before = session.card_text(curve["object_id"])
    curves = [{"target": curve, "points": [[0, 1], [1, 2]], "units": {"x": bad_unit, "y": "MPa"}}]
    for target, profile in ((law1, "radioss_law1_elastic_v1"), (law36, "radioss_prony_visco_v1"),
                            (curve, "radioss_prony_visco_v1")):
        with pytest.raises(PrepError) as error:
            manager.prepare_apply(**_request(handle, target, profile_id=profile, curves=curves))
        assert error.value.code == "UNSUPPORTED_ATOMIC_APPLY"
    assert session.card_text(curve["object_id"]) == before
    assert _handle(session) == handle


@pytest.mark.parametrize(("input_units", "work_units", "unit_override", "code"), [
    (None, "Mg mm s", "", "invalid_units"),
    ("Mg mm", "Mg mm s", "", "invalid_units"),
    ("Mg ft s", "Mg mm s", "", "invalid_units"),
    ("Mg mm s", None, "", "invalid_units"),
    ("Mg m s", "Mg mm s", "", "unit_mismatch"),
    ("Mg mm s", "Mg mm s", "/5", "invalid_unit"),
])
def test_d19_requires_matching_valid_begin_rows_and_no_card_override(tmp_path, input_units, work_units, unit_override, code):
    starter = _build_material_deck(tmp_path)
    u_row = b"                  Mg                  mm                   s\n"
    rows = "".join(row + "\n" for row in (input_units, work_units) if row is not None)
    starter.write_bytes(starter.read_bytes().replace(u_row * 2, rows.encode("ascii")))
    materials = tmp_path / "materials.inc"
    materials.write_bytes(materials.read_bytes().replace(b"/MAT/LAW1/1\n", f"/MAT/LAW1/1{unit_override}\n".encode("ascii")))
    session = PrepSession()
    session.open_rad(starter)
    with pytest.raises(PrepError) as error:
        MaterialBindingManager(session).prepare_apply(**_request(_handle(session), _object_ref(session, "/MAT/LAW1/1")))
    assert error.value.code == code
    assert not session.document.dirty


def test_d19_typed_target_and_expired_or_stale_plan(tmp_path):
    starter = _build_material_deck(tmp_path)
    session = PrepSession()
    session.open_rad(starter)
    time_now = 10.0
    manager = MaterialBindingManager(session, clock=lambda: time_now)
    target = _object_ref(session, "/MAT/LAW1/1")
    request = _request(_handle(session), target)
    for bad_target in ({"kind": "node"}, {"entity_kind": "node"}, {"mesh_revision": 0},
                       {"resource_id": session._root_id}, {"native_scope": "/MAT/ELAST/1"}, {"document_id": str(uuid4())}):
        with pytest.raises(PrepError) as error:
            manager.prepare_apply(**{**request, "target": {**target, **bad_target}})
        assert error.value.code in ("invalid_reference", "card_not_found", "document_conflict")

    expired = manager.prepare_apply(**request)
    time_now += 60.0
    current_plan = manager.prepare_apply(**request)
    for _ in range(2):
        with pytest.raises(PrepError) as error:
            manager.commit_apply(**_commit(request, expired))
        assert error.value.code == "plan_expired"
    assert not session.document.dirty
    session.set_field(target["object_id"], "young_modulus", 200000)
    with pytest.raises(PrepError) as error:
        manager.commit_apply(**{**_commit(request, current_plan), "handle": _handle(session)})
    assert error.value.code == "revision_conflict"
    assert _fields_dict(session, target["object_id"])["young_modulus"] == 200000


@pytest.mark.parametrize("keyword", ["/VISC/PRONY/1", "/FAIL/JOHNSON/1", "/HEAT/MAT/1",
                                      "/EOS/LINEAR/1", "/MAT/ORTHO/1", "/THERM_STRESS/MAT/1",
                                      "/TABLE/MAT/1", "/FUNCT/MAT/1", "/VISC/PRONY/         1",
                                      "/FAIL/JOHNSON/ +0001", "/HEAT/ MAT / 01", "/EOS/LINEAR/ 1 /42",
                                      "/MAT/ORTHO/   001"])
def test_d19_attached_card_blocks_scalar_only_apply(tmp_path, keyword):
    starter = _build_material_deck(tmp_path)
    curves = tmp_path / "curves.inc"
    curves.write_bytes(curves.read_bytes() + f"{keyword}\nAttachment\n       999\n/FUNCT/999\nCurve\n".encode())
    session = PrepSession()
    session.open_rad(starter)
    manager = MaterialBindingManager(session)
    with pytest.raises(PrepError) as error:
        manager.prepare_apply(**_request(_handle(session), _object_ref(session, "/MAT/LAW1/1")))
    assert error.value.code == "UNSUPPORTED_ATOMIC_APPLY"
    assert error.value.details["dependency"] == keyword
    assert not manager._plans and not session.document.dirty


@pytest.mark.parametrize(("rho_0", "trailing", "supported"), [
    ("", "", True), ("0", "", True), ("0.0", "", True), ("0D0", "", True),
    ("1e-9", "", False), ("NOT-A-NUM", "", False), ("0", "        99", False),
])
def test_d19_reference_density_default_remains_unchanged(tmp_path, rho_0, trailing, supported):
    starter = _build_material_deck(tmp_path)
    material_file = tmp_path / "materials.inc"
    density = f"{'7.85e-09':>20}{rho_0:>20}{trailing}".encode("ascii")
    material_file.write_bytes(material_file.read_bytes().replace(b"            7.85e-09\n", density + b"\n", 1))
    # A padded unit ID equal to the target material ID does not make this an attachment.
    curves = tmp_path / "curves.inc"
    curves.write_bytes(curves.read_bytes() + b"/VISC/PRONY/   2/   1\nOther material\n")
    session = PrepSession()
    session.open_rad(starter)
    target = _object_ref(session, "/MAT/LAW1/1")
    manager = MaterialBindingManager(session)
    request = _request(_handle(session), target, parameters={"E": {"value": 205, "unit": "GPa"}})
    if supported:
        plan = manager.prepare_apply(**request)
        manager.commit_apply(**_commit(request, plan))
        assert session.card_text(target["object_id"]).splitlines()[2].encode("ascii") == density
        assert _fields_dict(session, target["object_id"])["young_modulus"] == 205000
    else:
        with pytest.raises(PrepError) as error:
            manager.prepare_apply(**request)
        assert error.value.code == "UNSUPPORTED_ATOMIC_APPLY"
        assert not session.document.dirty


@pytest.mark.parametrize(("rho", "modulus", "nu", "extra", "code"), [
    ("NOT-A-NUM", 210000, 0.3, "", "invalid_target_card"),
    (7.85e-9, 210000, "NOT-A-NUM", "", "invalid_target_card"),
    (0, 210000, 0.3, "", "invalid_target_card"),
    (7.85e-9, -1, 0.3, "", "invalid_target_card"),
    (7.85e-9, 210000, 0.5, "", "invalid_target_card"),
    (7.85e-9, 210000, 0.3, f"{10:10d}", "UNSUPPORTED_ATOMIC_APPLY"),
    (7.85e-9, 210000, 0.3, "\n        10", "UNSUPPORTED_ATOMIC_APPLY"),
])
def test_d19_validate_all_existing_slots_and_unverified_function_fields(tmp_path, rho, modulus, nu, extra, code):
    starter = _build_material_deck(tmp_path)
    cards = tmp_path / "materials.inc"
    text = cards.read_text(encoding="ascii")
    start = text.index("            7.85e-09")
    stop = text.index("/MAT/LAW36/2")
    cards.write_text(text[:start] + f"{str(rho):>20}\n{str(modulus):>20}{str(nu):>20}{extra}\n" + text[stop:], encoding="ascii")
    session = PrepSession()
    session.open_rad(starter)
    with pytest.raises(PrepError) as error:
        MaterialBindingManager(session).prepare_apply(**_request(_handle(session), _object_ref(session, "/MAT/LAW1/1"),
                                                                 parameters={"E": {"value": 205, "unit": "GPa"}}))
    assert error.value.code == code
    assert not session.document.dirty


_PROVENANCE = {"study_id": "study-A", "evaluation_id": "evaluation-A", "selection_id": "selection-A",
               "content_revision": "a" * 64, "parameter_set_sha256": "c" * 64, "holdout_status": "pass",
               "source_fingerprint": "f" * 64}


@pytest.mark.parametrize("fields", [
    {"study_id": "study-A"}, {"provenance": {"study_id": "study-A"}}, {"provenance": {}}, {"provenance": None},
    {"provenance": dict.fromkeys(_PROVENANCE)}, {"provenance": dict.fromkeys(_PROVENANCE, "")},
    {"provenance": {**_PROVENANCE, "selection_id": "   "}},
    {"provenance": {**_PROVENANCE, "content_revision": 7}},
    {"provenance": {**_PROVENANCE, "content_revision": "A" * 64}},
    {"provenance": {**_PROVENANCE, "parameter_set_sha256": "g" * 64}},
    {"provenance": {**_PROVENANCE, "source_fingerprint": "f" * 63}},
    {"provenance": {**_PROVENANCE, "holdout_status": "unknown"}},
])
def test_d19_rejects_incomplete_or_malformed_provenance(tmp_path, fields):
    session = PrepSession()
    session.open_rad(_build_material_deck(tmp_path))
    manager = MaterialBindingManager(session)
    with pytest.raises(PrepError) as error:
        manager.prepare_apply(**_request(_handle(session), _object_ref(session, "/MAT/LAW1/1"), **fields))
    assert error.value.code == "invalid_request"
    assert not manager._plans and not session.document.dirty


@pytest.mark.parametrize("form", ["nested", "flat", "alongside"])
def test_d19_commit_binds_each_prepared_provenance_field(tmp_path, form):
    session = PrepSession()
    session.open_rad(_build_material_deck(tmp_path))
    target = _object_ref(session, "/MAT/LAW1/1")
    request = _request(_handle(session), target, **_PROVENANCE)
    manager = MaterialBindingManager(session)
    prepared = manager.prepare_apply(**request)
    assert prepared["candidate_hashes"]["provenance"] == _PROVENANCE
    base = _commit(request, prepared)
    card_id = target["object_id"]
    hashes = {card_id: prepared["candidate_hashes"][card_id]}
    for key in _PROVENANCE:
        changed = ("b" * 64 if key in ("content_revision", "parameter_set_sha256", "source_fingerprint")
                   else "fail" if key == "holdout_status" else "altered")
        bad = hashes | {"provenance": {**_PROVENANCE, key: changed}}
        with pytest.raises(PrepError) as error:
            manager.commit_apply(**{**base, "candidate_hashes": bad})
        assert error.value.code == "hash_mismatch"
    with pytest.raises(PrepError) as missing:
        manager.commit_apply(**{**base, "candidate_hashes": hashes})
    assert missing.value.code == "hash_mismatch"
    assert not session.document.dirty

    if form == "flat":
        base["candidate_hashes"] = hashes | _PROVENANCE
    elif form == "alongside":
        base.update(candidate_hashes=hashes, **_PROVENANCE)
    receipt = manager.commit_apply(**base)
    assert receipt["applied_hashes"] == hashes and receipt["provenance"] == _PROVENANCE


def test_d19_expired_plan_markers_are_bounded(tmp_path):
    session = PrepSession()
    session.open_rad(_build_material_deck(tmp_path))
    req = _request(_handle(session), _object_ref(session, "/MAT/LAW1/1"))
    now = 10
    manager = MaterialBindingManager(session, clock=lambda: now)
    plans = [manager.prepare_apply(**req) for _ in range(257)]
    now += 60
    manager.prepare_apply(**req)
    assert len(manager._expired_plan_ids) == 256
    for plan, code in ((plans[0], "stale_material_plan"), (plans[-1], "plan_expired")):
        with pytest.raises(PrepError) as error:
            manager.commit_apply(**_commit(req, plan))
        assert error.value.code == code


def test_d19_live_rpc_guards_refresh_and_idempotent_replay(tmp_path: Path, request):
    pytest.importorskip("PySide6")
    request.getfixturevalue("qt_settings")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QDialog, QLineEdit
    from caelab_prep.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    starter = _build_material_deck(tmp_path)
    descriptor = tmp_path / "live-conn.json"
    win = MainWindow(enable_viewport=False)
    try:
        win.session.open_rad(starter)
        win.refresh_document()
        win.start_live_ipc(descriptor)
        client = LiveClient(descriptor, timeout=10.0)

        with ThreadPoolExecutor(max_workers=1) as pool:
            def call(method, params=None, request_id=None):
                result = pool.submit(client.request, method, params, request_id=request_id)
                while not result.done():
                    app.processEvents()
                    time.sleep(.001)
                return result.result()

            hello = call("hello")
            assert {"material.prepare_apply", "material.commit_apply"} <= set(hello["methods"])
            assert "radioss_law1_elastic_v1" in hello["limits"]["material"]
            handle = hello["handle"]
            target = next(card["ref"] for card in call("document.cards")["cards"]
                          if card["ref"]["native_scope"] == "/MAT/LAW1/1")
            request = _request(handle, target, provenance=_PROVENANCE)

            win._busy = True
            try:
                with pytest.raises(LiveRemoteError) as busy:
                    call("material.prepare_apply", request)
                assert busy.value.code == "owner_busy"
            finally:
                win._busy = False

            modal = QDialog(win)
            modal.setWindowModality(Qt.WindowModality.ApplicationModal)
            modal.show()
            app.processEvents()
            try:
                with pytest.raises(LiveRemoteError) as busy:
                    call("material.prepare_apply", request)
                assert busy.value.code == "owner_busy"
            finally:
                modal.close()

            win.show()
            win.select_card(_object_ref(win.session, "/FUNCT/10")["object_id"])
            app.processEvents()
            editor = QLineEdit(win.curve_table.table)
            editor.show()
            editor.setFocus()
            app.processEvents()
            try:
                with pytest.raises(LiveRemoteError) as draft:
                    call("material.prepare_apply", request)
                assert draft.value.code == "draft_pending"
            finally:
                editor.clearFocus()
                editor.deleteLater()
                app.processEvents()

            win.select_card(target["object_id"])
            prepared = call("material.prepare_apply", request)
            assert prepared["supported"] and _handle(win.session) == handle
            commit = _commit(request, prepared)
            with pytest.raises(LiveRemoteError) as mismatch:
                call("material.commit_apply", {**commit, "candidate_hashes": {}})
            assert mismatch.value.code == "hash_mismatch"
            request_id = str(uuid4())
            receipt = call("material.commit_apply", commit, request_id)
            assert call("material.commit_apply", commit, request_id) == receipt
            assert receipt["applied_hashes"] == {target["object_id"]: prepared["candidate_hashes"][target["object_id"]]}
            assert receipt["provenance"] == _PROVENANCE
            assert receipt["handle_after"]["revision"] == handle["revision"] + 1
            assert receipt["change"]["kind"] == "values"
            app.processEvents()
            assert win._editor_revision == receipt["handle_after"]["revision"]
            assert _fields_dict(win.session, target["object_id"])["young_modulus"] == 205000.0

            undo = call("document.undo", {"handle": receipt["handle_after"]})
            assert _fields_dict(win.session, target["object_id"])["young_modulus"] == 210000.0
            redo = call("document.redo", {"handle": undo["handle"]})
            assert redo["handle"]["revision"] == handle["revision"] + 3
            assert _fields_dict(win.session, target["object_id"])["young_modulus"] == 205000.0
    finally:
        win.stop_live_ipc()
        win._allow_close = True
        win.close()
        app.processEvents()
