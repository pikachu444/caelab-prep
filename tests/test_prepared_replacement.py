import json
import subprocess
import sys
from pathlib import Path

import pytest

from caelab_prep.application import PrepSession
from caelab_prep.cae_core import PrepError

SOURCE = Path(__file__).resolve().parents[1] / "scripts/evaluation/models/mixed-assemblies/beam_shell_tet/model_0000.rad"


def assembly():
    session = PrepSession(); session.open_rad(SOURCE)
    mesh = next(r for r in session._deck_resources() if r.id != session._root_id)
    group = session.create_node_group("Explicit old nodes", [1,2])["card_id"]
    element = next(cell for cell in session.mesh_view()["cells"] if cell["id"] == 77)
    elements = session.create_element_group("Explicit old shell", [{"resource_id":mesh.id,"entity_kind":"element","local_id":77}])["card_id"]
    part = next(card for card in session.list_cards() if card["keyword"] == "/PART/9")["id"]
    surface = session.create_surface("Old surface", [part])["card_id"]
    contact = session.create_contact("Contact", group, surface, .1)["card_id"]
    case = session.create_analysis_case("Assembly case", [contact], 1e-6, 5e-7, "s")["case_id"]
    return session, mesh, dict(group=group,elements=elements,surface=surface,contact=contact,case=case,part=part)


def replacement(tmp_path, same_ids):
    lines = (SOURCE.parent / "mesh.inc").read_text().splitlines()
    family = None
    for index, line in enumerate(lines):
        if line.startswith("/"): family = line.split("/")[1]; continue
        if not line or line.startswith("#"): continue
        if family == "NODE":
            old = int(line[:10]); xyz = [float(line[start:start+20]) for start in (10,30,50)]
            lines[index] = f"{old if same_ids else old+100:10}" + "".join(f"{value+2:20g}" for value in xyz)
        elif family in ("BEAM","SHELL","TETRA4") and not same_ids:
            ids = [int(line[start:start+10]) for start in range(0,len(line),10)]
            lines[index] = f"{ids[0]+1000:10}" + "".join(f"{value+100:10}" for value in ids[1:])
    target = tmp_path / "prepared.inc"; target.write_text("\n".join(lines)+"\n")
    return target


@pytest.mark.parametrize("same_ids", [False, True])
def test_replacement_stales_same_number_targets_save_reopen_and_explicit_reconnect(same_ids,tmp_path):
    session, mesh, ids = assembly()
    before_raw = mesh.raw; before_rendered = mesh.render()
    pick = session.mesh_view()
    old_pick = {key:pick[key] for key in ("document_id","document_epoch","revision","projection_revision")}
    old_pick.update(kind="element",id=77,resource_id=mesh.id,resource_revision=pick["resource_revisions"][mesh.id])
    plan = session.plan_mesh_replacement(mesh.id, replacement(tmp_path,same_ids))
    assert set(plan["stale_targets"]) == {ids["group"],ids["elements"],ids["surface"]}
    before_revision = session.document.revision; events=[]; session.subscribe(events.append)
    session.replace_prepared_mesh(plan["plan_id"],expected_revision=before_revision)
    assert len(events)==1 and session.document.revision==before_revision+1 and mesh.raw is before_raw
    assert mesh.render()!=before_rendered
    assert session.mesh_relationships()["conditions"]==[{"card_id":ids["contact"],"stale_target_ids":[ids["group"],ids["surface"]],"status":"stale"}]
    with pytest.raises(PrepError) as error: session.select_pick(old_pick)
    assert error.value.code=="stale_pick"
    with pytest.raises(PrepError) as error: session.export_analysis_case(tmp_path/"blocked_0000.rad",ids["case"])
    assert error.value.code=="stale_mesh_targets" and not (tmp_path/"blocked_0000.rad").exists()
    project=tmp_path/"stale.caeprep";session.save_project(project)
    script="import json,sys;from caelab_prep.application import PrepSession;s=PrepSession();s.open_project(sys.argv[1]);print(json.dumps(s.mesh_relationships()))"
    saved=json.loads(subprocess.check_output([sys.executable,"-c",script,str(project)],text=True))
    assert saved["stale_targets"]==session.mesh_relationships()["stale_targets"]
    delta=0 if same_ids else 100
    mapping={ids["group"]:{"mesh_revision":1,"mapping":{old:{"resource_id":mesh.id,"entity_kind":"node","local_id":old+delta} for old in (1,2)}},
             ids["elements"]:{"mesh_revision":1,"mapping":{77:{"resource_id":mesh.id,"entity_kind":"element","local_id":77 if same_ids else 1077}}},
             ids["surface"]:{"mesh_revision":1,"mapping":{9:ids["part"]}}}
    # A failed second target cannot update the first group's rows or markers.
    bad={**mapping,ids["elements"]:{"mesh_revision":0,"mapping":mapping[ids["elements"]]["mapping"]}}
    state=(session.document.tokens(),session.document.revision,len(events),session.dispatcher.can_redo)
    with pytest.raises(PrepError):session.reconnect_mesh_targets(bad)
    assert state==(session.document.tokens(),session.document.revision,len(events),session.dispatcher.can_redo)
    session.reconnect_mesh_targets(mapping,expected_revision=session.document.revision)
    assert session.mesh_relationships()["stale_targets"]=={}
    assert session.group_members(ids["group"])["member_ids"]==[1+delta,2+delta]
    session.export_analysis_case(tmp_path/"out"/"restored_0000.rad",ids["case"])
    session.undo();assert session.mesh_relationships()["stale_targets"]
    session.undo();assert mesh.render()==before_rendered and session.mesh_relationships()["stale_targets"]=={}
    session.redo();session.redo();assert session.mesh_relationships()["stale_targets"]=={}


def test_stale_replacement_plan_and_unmapped_old_members_leave_model_unchanged(tmp_path):
    session,mesh,ids=assembly()
    plan=session.plan_mesh_replacement(mesh.id,replacement(tmp_path,True))
    session.set_analysis_case(ids["case"],{"name":"Changed"})
    before=session.describe()
    with pytest.raises(PrepError) as error:session.replace_prepared_mesh(plan["plan_id"])
    assert error.value.code=="stale_mesh_replacement_plan" and session.describe()==before
    plan=session.plan_mesh_replacement(mesh.id,tmp_path/"prepared.inc")
    session.replace_prepared_mesh(plan["plan_id"])
    before=session.document.tokens()
    with pytest.raises(PrepError) as error:session.reconnect_mesh_targets({ids["group"]:{"mesh_revision":1,"mapping":{1:{"resource_id":mesh.id,"entity_kind":"node","local_id":1}}}})
    assert error.value.code=="incomplete_reference_mapping" and session.document.tokens()==before
