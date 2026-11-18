"""Comprehensive D19 (PREP01 live material binding prepare/commit & RPC) tests."""
from __future__ import annotations

import math
from pathlib import Path
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from caelab_prep.application.contracts import ObjectRef
from caelab_prep.application.live_transport import LiveClient, LiveRemoteError
from caelab_prep.application.material_binding import MaterialBindingManager
from caelab_prep.application.session import PrepSession
from caelab_prep.cae_core import PrepError
from caelab_prep.ui.main_window import MainWindow


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
                "Visco Elastomer Tabular",
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
                "Relaxation Master Curve",
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


def test_d19_law1_prepare_commit_units_undo_save_export(tmp_path: Path):
    """Test radioss_law1_elastic_v1 unit conversions, zero-mutation prepare, 1-step commit/undo, and export."""
    starter = _build_material_deck(tmp_path)
    s = PrepSession()
    s.open_rad(str(starter))
    mgr = MaterialBindingManager(s)

    events = []
    s.subscribe(events.append)
    handle = {k: s.describe()[k] for k in ("document_id", "document_epoch", "revision")}
    law1_ref = _object_ref(s, "/MAT/LAW1/1")
    before_text = s.card_text(law1_ref["object_id"])

    prepared = mgr.prepare_apply(
        handle,
        law1_ref,
        "radioss_law1_elastic_v1",
        {"young_modulus": 195.5, "density": 7900.0, "poisson_ratio": 0.29},
        {"young_modulus": "GPa", "density": "kg/m³", "poisson_ratio": ""},
    )
    # Zero live mutation during prepare
    assert s.describe()["revision"] == handle["revision"]
    assert s.card_text(law1_ref["object_id"]) == before_text
    assert events == []
    assert prepared["admissible"] is True
    assert prepared["expires_in_seconds"] == 60
    assert prepared["exporter_id"] == "radioss_law1_elastic_v1"
    assert "---" in prepared["diff"] and "+++" in prepared["diff"]
    assert "195500" in prepared["diff"]

    committed = mgr.commit_apply(handle, prepared["plan_id"], handle["revision"])
    assert committed["status"] == "committed"
    assert committed["changed"] is True
    assert committed["handle"]["revision"] == handle["revision"] + 1
    assert committed["applied_hashes"] == prepared["candidate_hashes"]

    fields = _fields_dict(s, law1_ref["object_id"])
    assert math.isclose(fields["young_modulus"], 195500.0, rel_tol=1e-12)
    assert math.isclose(fields["density"], 7.9e-9, rel_tol=1e-12)
    assert math.isclose(fields["poisson_ratio"], 0.29, rel_tol=1e-12)

    # Single Undo reverts cleanly; Redo restores
    s.undo()
    assert s.card_text(law1_ref["object_id"]) == before_text
    s.redo()
    assert math.isclose(_fields_dict(s, law1_ref["object_id"])["young_modulus"], 195500.0, rel_tol=1e-12)

    # Save & reopen .caeprep + export Starter/Engine
    proj = tmp_path / "calibrated.caeprep"
    s.save_project(str(proj))
    reopened = PrepSession()
    reopened.open_project(str(proj))
    re_ref = _object_ref(reopened, "/MAT/LAW1/1")
    assert math.isclose(_fields_dict(reopened, re_ref["object_id"])["young_modulus"], 195500.0, rel_tol=1e-12)

    exp_dir = tmp_path / "solver_out"
    exp = reopened.export_solver_inputs(str(exp_dir / "calib_0000.rad"), end_time=0.01, output_interval=0.002)
    verify = PrepSession()
    verify.open_rad(exp["starter_path"])
    ver_ref = _object_ref(verify, "/MAT/LAW1/1")
    assert math.isclose(_fields_dict(verify, ver_ref["object_id"])["young_modulus"], 195500.0, rel_tol=1e-12)


def test_d19_prony_visco_multiresource_material_plus_funct_one_transaction(tmp_path: Path):
    """Commit material + companion /FUNCT curve across two #include files in ONE execute_many / 1 Undo."""
    starter = _build_material_deck(tmp_path)
    s = PrepSession()
    s.open_rad(str(starter))
    mgr = MaterialBindingManager(s)

    handle = {k: s.describe()[k] for k in ("document_id", "document_epoch", "revision")}
    law36_ref = _object_ref(s, "/MAT/LAW36/2")
    funct_ref = _object_ref(s, "/FUNCT/10")
    before_mat = s.card_text(law36_ref["object_id"])
    before_fn = s.card_text(funct_ref["object_id"])

    prepared = mgr.prepare_apply(
        handle,
        law36_ref,
        "radioss_prony_visco_v1",
        {"young_modulus": 3.2, "density": 1.15, "poisson_ratio": 0.44},
        {"young_modulus": "GPa", "density": "g/cm^3", "x": "ms", "y": "GPa"},
        cards=[
            {
                "target": funct_ref,
                "role": "relaxation_curve",
                "points": [[0.0, 3.2], [5.0, 2.1], [50.0, 1.4], [500.0, 1.1]],
            }
        ],
    )
    assert s.describe()["revision"] == handle["revision"]
    assert law36_ref["object_id"] in prepared["candidate_hashes"]
    assert funct_ref["object_id"] in prepared["candidate_hashes"]
    assert len(prepared["applied_cards"]) == 2

    res = mgr.commit_apply(handle, prepared["plan_id"], handle["revision"])
    assert res["handle"]["revision"] == handle["revision"] + 1  # ONE transaction for 2 includes!
    mat_fields = _fields_dict(s, law36_ref["object_id"])
    assert math.isclose(mat_fields["young_modulus"], 3200.0, rel_tol=1e-12)
    assert math.isclose(mat_fields["density"], 1.15e-9, rel_tol=1e-12)
    fn_fields = _fields_dict(s, funct_ref["object_id"])
    assert math.isclose(fn_fields["point_1_x"], 0.005, rel_tol=1e-12)
    assert math.isclose(fn_fields["point_1_y"], 2100.0, rel_tol=1e-12)
    assert math.isclose(fn_fields["point_3_x"], 0.5, rel_tol=1e-12)
    assert math.isclose(fn_fields["point_3_y"], 1100.0, rel_tol=1e-12)

    # ONE Undo reverts BOTH materials.inc and curves.inc
    s.undo()
    assert s.card_text(law36_ref["object_id"]) == before_mat
    assert s.card_text(funct_ref["object_id"]) == before_fn
    s.redo()
    assert math.isclose(_fields_dict(s, funct_ref["object_id"])["point_2_x"], 0.05, rel_tol=1e-12)

    # Also verify Prony term generation path onto /FUNCT
    handle2 = {k: s.describe()[k] for k in ("document_id", "document_epoch", "revision")}
    prep_terms = mgr.prepare_apply(
        handle2,
        law36_ref,
        "radioss_prony_visco_v1",
        {"young_modulus": 2800.0, "prony_terms": [{"g": 0.35, "tau": 20.0}, {"g": 0.25, "tau": 200.0}]},
        {"young_modulus": "MPa", "time": "ms"},
        cards=[{"target": funct_ref}],
    )
    res2 = mgr.commit_apply(handle2, prep_terms["plan_id"], handle2["revision"])
    assert res2["changed"] is True
    pts = _fields_dict(s, funct_ref["object_id"])
    assert math.isclose(pts["point_0_x"], 0.0)
    assert math.isclose(pts["point_0_y"], 2800.0, rel_tol=1e-9)
    assert pts["point_1_x"] > 0.0 and pts["point_1_y"] < 2800.0


def test_d19_expiry_unit_guards_and_stale_handle_rejections(tmp_path: Path):
    """Reject missing units, unknown units, wrong exporter, expired plan (>60s), and stale revision."""
    starter = _build_material_deck(tmp_path)
    s = PrepSession()
    s.open_rad(str(starter))
    clock = [1000.0]
    mgr = MaterialBindingManager(s, clock=lambda: clock[0])

    handle = {k: s.describe()[k] for k in ("document_id", "document_epoch", "revision")}
    law1_ref = _object_ref(s, "/MAT/LAW1/1")
    law36_ref = _object_ref(s, "/MAT/LAW36/2")
    part_ref = _object_ref(s, "/PART/1")

    # 1. Missing / empty units rejected (never guessed)
    with pytest.raises(PrepError) as e_units:
        mgr.prepare_apply(handle, law1_ref, "radioss_law1_elastic_v1", {"young_modulus": 210000.0}, {})
    assert e_units.value.code == "invalid_units"

    # 2. Unknown unit symbol rejected
    with pytest.raises(PrepError) as e_bad_u:
        mgr.prepare_apply(handle, law1_ref, "radioss_law1_elastic_v1", {"young_modulus": 100.0}, {"young_modulus": "psi"})
    assert e_bad_u.value.code == "invalid_unit"

    # 3. Unsupported exporter / target mismatch -> UNSUPPORTED_ATOMIC_APPLY
    with pytest.raises(PrepError) as e_exp:
        mgr.prepare_apply(handle, law1_ref, "radioss_unknown_v9", {"young_modulus": 200.0}, {"young_modulus": "GPa"})
    assert e_exp.value.code == "UNSUPPORTED_ATOMIC_APPLY"

    with pytest.raises(PrepError) as e_card:
        mgr.prepare_apply(handle, law36_ref, "radioss_law1_elastic_v1", {"young_modulus": 2.0}, {"young_modulus": "GPa"})
    assert e_card.value.code == "UNSUPPORTED_ATOMIC_APPLY"

    with pytest.raises(PrepError) as e_part:
        mgr.prepare_apply(handle, part_ref, "radioss_law1_elastic_v1", {"young_modulus": 2.0}, {"young_modulus": "GPa"})
    assert e_part.value.code == "UNSUPPORTED_ATOMIC_APPLY"

    # 4. 60-second monotonic expiry
    plan = mgr.prepare_apply(handle, law1_ref, "radioss_law1_elastic_v1", {"young_modulus": 220.0}, {"young_modulus": "GPa"})
    clock[0] += 60.5
    with pytest.raises(PrepError) as e_expired:
        mgr.commit_apply(handle, plan["plan_id"], handle["revision"])
    assert e_expired.value.code == "plan_expired"
    assert s.describe()["revision"] == handle["revision"]

    # Consumed/expired plan cannot be committed afterwards
    with pytest.raises(PrepError) as e_stale:
        mgr.commit_apply(handle, plan["plan_id"], handle["revision"])
    assert e_stale.value.code == "stale_material_plan"

    # 5. Revision conflict on commit after unrelated edit
    plan2 = mgr.prepare_apply(handle, law1_ref, "radioss_law1_elastic_v1", {"young_modulus": 230.0}, {"young_modulus": "GPa"})
    s.set_fields(law36_ref["object_id"], {"poisson_ratio": 0.42}, expected_revision=s.document.revision)
    with pytest.raises(PrepError) as e_rev:
        mgr.commit_apply(handle, plan2["plan_id"], handle["revision"])
    assert e_rev.value.code == "revision_conflict"

    # 6. Missing work unit row in /BEGIN -> invalid_units
    no_work_dir = tmp_path / "no_work_units"
    no_work_starter = _build_material_deck(no_work_dir, include_work_units=False)
    s_no_u = PrepSession()
    s_no_u.open_rad(str(no_work_starter))
    mgr_no_u = MaterialBindingManager(s_no_u)
    h_no_u = {k: s_no_u.describe()[k] for k in ("document_id", "document_epoch", "revision")}
    with pytest.raises(PrepError) as e_no_work:
        mgr_no_u.prepare_apply(h_no_u, _object_ref(s_no_u, "/MAT/LAW1/1"), "radioss_law1_elastic_v1",
                               {"young_modulus": 200.0}, {"young_modulus": "GPa"})
    assert e_no_work.value.code == "invalid_units"


def test_d19_live_rpc_guards_refresh_and_idempotent_replay(tmp_path: Path):
    """End-to-end LiveControl + LiveServer + LiveClient socket RPC with guards and idempotent request_id."""
    app = QApplication.instance() or QApplication([])
    starter = _build_material_deck(tmp_path)
    descriptor = tmp_path / "live-conn.json"

    win = MainWindow(enable_viewport=False)
    try:
        win.session.open_rad(str(starter))
        win.refresh_document()
        app.processEvents()
        win.start_live_ipc(str(descriptor))
        client = LiveClient(str(descriptor), timeout=10.0)

        def call(method: str, params=None, request_id=None):
            # Pump Qt main loop while worker thread waits on LiveServer
            result_box = {}
            exc_box = {}
            import threading

            def run():
                try:
                    result_box["value"] = client.request(method, params, request_id=request_id)
                except Exception as exc:  # noqa: BLE001
                    exc_box["exc"] = exc

            th = threading.Thread(target=run, daemon=True)
            th.start()
            while th.is_alive():
                app.processEvents()
            th.join(timeout=2.0)
            if "exc" in exc_box:
                raise exc_box["exc"]
            return result_box["value"]

        hello = call("hello")
        assert "material.prepare_apply" in hello["methods"]
        assert "material.commit_apply" in hello["methods"]
        handle = hello["handle"]

        law36_ref = _object_ref(win.session, "/MAT/LAW36/2")
        funct_ref = _object_ref(win.session, "/FUNCT/10")

        # 1. Owner-busy and draft-pending guard rejections over RPC
        win._busy = True
        try:
            with pytest.raises(LiveRemoteError) as err_busy:
                call("material.prepare_apply", {
                    "handle": handle,
                    "target": law36_ref,
                    "exporter_id": "radioss_prony_visco_v1",
                    "parameters": {"young_modulus": 4.0},
                    "units": {"young_modulus": "GPa"},
                })
            assert err_busy.value.code == "owner_busy"
        finally:
            win._busy = False

        # Active modal widget rejection
        modal = QDialog(win)
        modal.setWindowModality(Qt.WindowModality.ApplicationModal)
        modal.show()
        app.processEvents()
        try:
            with pytest.raises(LiveRemoteError) as err_modal:
                call("material.prepare_apply", {
                    "handle": handle,
                    "target": law36_ref,
                    "exporter_id": "radioss_prony_visco_v1",
                    "parameters": {"young_modulus": 4.0},
                    "units": {"young_modulus": "GPa"},
                })
            assert err_modal.value.code == "owner_busy"
        finally:
            modal.close()
            app.processEvents()

        # Draft pending rejection via active curve_table cell editor (real _draft_pending path)
        from PySide6.QtWidgets import QLineEdit
        win.show()
        win.select_card(law36_ref["object_id"])
        app.processEvents()
        fake_editor = QLineEdit(win.curve_table.table)
        fake_editor.show()
        fake_editor.setFocus()
        app.processEvents()
        try:
            with pytest.raises(LiveRemoteError) as err_draft:
                call("material.prepare_apply", {
                    "handle": handle,
                    "target": law36_ref,
                    "exporter_id": "radioss_prony_visco_v1",
                    "parameters": {"young_modulus": 4.0},
                    "units": {"young_modulus": "GPa"},
                })
            assert err_draft.value.code == "draft_pending"
        finally:
            fake_editor.clearFocus()
            fake_editor.deleteLater()
            app.processEvents()

        # 2. Prepare + Commit across LAW36 & FUNCT + idempotent request_id replay!
        prep = call("material.prepare_apply", {
            "handle": handle,
            "target": law36_ref,
            "exporter_id": "radioss_prony_visco_v1",
            "parameters": {"young_modulus": 3.5, "density": 1200.0},
            "units": {"young_modulus": "GPa", "density": "kg/m^3", "x": "ms", "y": "MPa"},
            "cards": [{"target": funct_ref, "points": [[0.0, 3500.0], [10.0, 1800.0], [100.0, 1200.0]]}],
        })
        assert prep["admissible"] is True
        assert prep["expires_in_seconds"] == 60
        assert win.session.describe()["revision"] == handle["revision"]

        commit_req_id = str(uuid4())
        commit_params = {"handle": handle, "plan_id": prep["plan_id"], "expected_revision": handle["revision"]}
        receipt1 = call("material.commit_apply", commit_params, request_id=commit_req_id)
        assert receipt1["status"] == "committed"
        assert receipt1["handle"]["revision"] == handle["revision"] + 1
        assert math.isclose(_fields_dict(win.session, law36_ref["object_id"])["young_modulus"], 3500.0, rel_tol=1e-12)

        # Replay exact same commit request_id -> must return identical cached receipt cleanly!
        receipt2 = call("material.commit_apply", commit_params, request_id=commit_req_id)
        assert receipt2 == receipt1
        assert win.session.describe()["revision"] == handle["revision"] + 1

        # Undo + Redo over RPC
        undo_res = call("document.undo", {"handle": receipt1["handle"]})
        assert undo_res["handle"]["revision"] == handle["revision"] + 2
        assert math.isclose(_fields_dict(win.session, law36_ref["object_id"])["young_modulus"], 2500.0, rel_tol=1e-12)
        redo_res = call("document.redo", {"handle": undo_res["handle"]})
        assert math.isclose(_fields_dict(win.session, law36_ref["object_id"])["young_modulus"], 3500.0, rel_tol=1e-12)
        assert redo_res["handle"]["revision"] == handle["revision"] + 3
    finally:
        win.stop_live_ipc()
        win._allow_close = True
        win.close()
        app.processEvents()
