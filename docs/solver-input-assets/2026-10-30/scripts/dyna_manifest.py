#!/usr/bin/env python3
"""Write the factual LS-DYNA acquisition manifest. This does not generate a solver deck."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REV="90270f787216c91a969d6b477aaf753d45556035"
VERSION="R17@e8334f9fb (06/11/26)"
RAW=f"https://raw.githubusercontent.com/ansys/pydyna/{REV}/"
SRC=f"https://github.com/ansys/pydyna/blob/{REV}/"

def source(number,title,kind,url,file,locator,depth,summary,version=VERSION,redistribution="locator-only"):
    path=ROOT/file if file else None
    data=path.read_bytes() if path and path.exists() else None
    return {"id":f"dyna-D{number:02d}","title":title,"kind":kind,"url":url,
        "version":version,"locator":locator,"access":"downloaded" if data is not None else "read",
        "read_depth":depth,"local_file":file,"sha256":hashlib.sha256(data).hexdigest() if data is not None else None,
        "size_bytes":len(data) if data is not None else None,"redistribution":redistribution,"summary":summary}

def code_source(number,path,title,kind,locator,summary):
    return source(number,title,kind,SRC+path,"assets/dyna/pydyna/"+path,locator,"relevant-sections",summary,
                  "0.13.dev0 @ "+REV,"permitted-with-notice")

def rule(n,q,ids,statement,locator,limits,status="partial",examples=None):
    return {"id":f"dyna-R{n:02d}","question_ids":[q],"source_ids":[f"dyna-D{i:02d}" for i in ids],
            "statement":statement,"locator":locator,"examples":examples or [],"limits":limits,"status":status}

if __name__ == "__main__":
    stats=json.loads((ROOT/"catalogues/dyna-reconciliation.json").read_text())
    reads=json.loads((ROOT/"tmp/dyna/read-sections.json").read_text())
    (ROOT/"catalogues/dyna-read-sections.json").write_text(json.dumps(reads,indent=2)+"\n")
    sources=[
      source(1,"Ansys LS-DYNA Manuals Download","index","https://lsdyna.ansys.com/manuals-download/",
             "tmp/dyna/manuals-download.html","Released R17 entries; draft manuals listed separately","relevant-sections",
             "접근 가능한 최신 정식판 R17 세 권을 기준으로 고정했다. 수시 draft와 이전 R16 웹 도움말을 혼용하지 않았다.","observed 2026-10-30"),
      source(2,"LS-DYNA Keyword User's Manual R17 Vol I","manual",
             "https://lsdyna.ansys.com/wp-content/uploads/2026/06/LS-DYNA_Manual_Vol_I_R17.pdf","tmp/dyna/vol1.pdf",
             "4301 PDF pages; TOC PDF 7–42; related PDF ranges in catalogues/dyna-read-sections.json","index-parsed+relevant-sections",
             "구조·구문·제어·restart 관련 절과 선정 카드 정의를 읽었다. 4,301쪽 전체 field를 읽은 것은 아니다."),
      source(3,"LS-DYNA Keyword User's Manual R17 Vol II: Material Models","manual",
             "https://lsdyna.ansys.com/wp-content/uploads/2026/06/LS-DYNA_Manual_Vol_II_R17.pdf","tmp/dyna/vol2.pdf",
             "2244 PDF pages; TOC PDF 5–15; MAT introduction PDF 87–89; material list PDF 109 onward; MAT_024 PDF 355–356","index-parsed+relevant-sections",
             "재료 별칭·요소 적합성·TITLE 및 MAT_024 변형 절을 읽었다. 전 재료의 물성 field 검토는 아니다."),
      source(4,"LS-DYNA Keyword User's Manual R17 Vol III: Multiphysics Solvers","manual",
             "https://lsdyna.ansys.com/wp-content/uploads/2026/06/LS-DYNA_Manual_Vol_III_R17.pdf","tmp/dyna/vol3.pdf",
             "828 PDF pages; TOC PDF 4–14; introduction PDF 15","index-parsed+relevant-sections",
             "multiphysics 권까지 목차 전부를 추출했다. 개별 multiphysics field는 전수 독해하지 않았다."),
      source(5,"Official Introductory Examples input decks ZIP","example",
             "https://lsdyna.ansys.com/wp-content/uploads/2026/08/Intro_Examples_Manual.input_decks.zip","tmp/dyna/intro-examples.zip",
             "82 actual .k files; catalogue lists member paths, sizes and hashes; examples 01 and 03 inspected","relevant-sections",
             "메시를 포함한 실제 deck 82개를 취득하고 전부 목록·해시를 기록했다. 재배포 허가를 찾지 못해 원본 ZIP은 분석용에만 둔다.","June 2013 manual / v971 examples","unknown"),
      code_source(6,"LICENSE","PyDYNA MIT license","license","Entire license; root pyproject license declaration; no nested LICENSE/NOTICE/COPYING found","MIT 고지와 경로별 예외 유무를 확인했다."),
      code_source(7,"codegen/README.md","PyDYNA codegen architecture","code","Input Files; Output; Validation","raw manual-derived schema와 보정 manifest, 추가 카드의 역할을 구분한다."),
      code_source(8,"src/ansys/dyna/core/lib/deck.py","PyDYNA Deck reader/writer","code","Deck.append 114; _expand_helper 255–317; expand 319–349; write 422–464; import_file 633; export_file 648","deck writer와 include 전개를 직접 읽었다. 미해결 include 보존과 strict 기본값을 기록했다."),
      code_source(9,"codegen/kwd.json","PyDYNA complete raw keyword schema snapshot","code","All JSON keys enumerated; selected PART/SECTION/MAT field shape checked","3,685 spec·12,219 card·69,523 field를 파싱·계수했다. 모든 field 뜻과 R17 적합성을 검토하지 않았다."),
      code_source(10,"codegen/manifest.json","PyDYNA codegen corrections and variants","code","PARAMETER/BOUNDARY_PRESCRIBED_MOTION/element/part patterns and conditional-card declarations","조건부 행·변형·이름 보정이 raw schema 외부에 있음을 확인했다."),
      code_source(11,"src/ansys/dyna/core/keywords/keyword_classes/type_mapping.py","PyDYNA keyword to generated-class mapping","code","Entire TypeMapping AST literal enumerated","3,685 매핑을 실제 추출했으며 공식 TOC와 문자 일치만 비교했다."),
      code_source(12,"src/ansys/dyna/core/lib/keyword_base.py","PyDYNA keyword reader/writer base","code","_process_title; _write_header; write 427–464","keyword format marker·title·cards 쓰기를 확인했다."),
      code_source(13,"examples/Taylor_Bar/plot_taylor_bar.py","PyDYNA Taylor bar deck construction example","example","create_input_deck; mesh Include; export_file; downstream solver section not executed","Python API로 재료·part·section·제어를 구성하되 메시 파일은 외부에서 받는 예제다."),
      source(14,"PyDYNA stable keywords documentation","api","https://dyna.docs.pyansys.com/version/stable/getting-started/modules/keywords.html",None,
             "Creating Keywords; multirow fields; Deck read/write","relevant-sections","stable 사용 문서는 개발 snapshot과 분리해 참고했다.","stable site observed 2026-10-30"),
      code_source(15,"codegen/additional-cards.json","PyDYNA supplementary card definitions","code","Top-level entries and referenced additions enumerated; not all semantics reviewed","manifest가 참조하는 별도 카드 자산도 원본으로 확보했다."),
      source(16,"Introductory Examples Manual for LS-DYNA Users","manual",
             "https://lsdyna.ansys.com/wp-content/uploads/2026/08/Intro_Examples_Manual_DRAFT.pdf","tmp/dyna/intro-examples-manual.pdf",
             "229 PDF pages; introduction PDF 3; example 1 PDF 7–12; example 3 PDF 19–24","relevant-sections",
             "v971·double precision 기준이라는 원문 조건과 예제 1·3의 표 결과를 읽었다. 여기서 재실행한 결과가 아니다.","June 2013 draft / LS-DYNA v971"),
      code_source(17,"tests/test_deck.py","PyDYNA include and parameter tests","code","test_deck_expand_global_parameter_collision 911–951; local scope 954 onward","전역 parameter 충돌과 import 시점 치환에 관한 upstream 예상값을 확인했다."),
      code_source(18,"tests/test_parameter_error_location.py","PyDYNA undefined-parameter tests","code","test_undefined_param_loads_successfully; test_write_retain_parameters_false_raises_on_undefined_param","undefined parameter를 보존해 쓰는 경로와 기본 write 오류 경로를 구분한다."),
      code_source(19,"tests/test_transform.py","PyDYNA include transform tests","code","node/element/part transform tests and testfiles/keywords/transform inputs","변환 fixture와 시험 코드의 대응을 보유했다. 시험을 실행하지 않았다."),
      code_source(20,"pyproject.toml","PyDYNA pinned package/version/license declaration","code","project.version; project.license; dependencies","0.13.dev0, MIT, Python 및 외부 의존성 선언을 확인했다."),
      code_source(21,"README.rst","PyDYNA project scope and solver license boundary","license","modules 45–52; License 82–89","keyword 생성 API와 LS-DYNA 실행 라이선스 요구를 분리했다."),
      code_source(22,"src/ansys/dyna/core/lib/card_writer.py","PyDYNA active-card writer","code","write_cards 37 onward","활성 카드와 parameter 참조 유지 경로를 읽었다."),
      code_source(23,"src/ansys/dyna/core/lib/field_writer.py","PyDYNA numeric/blank/width writer","code","_field_iterator; write_field_c; write_c_dataframe","폭·공백·정수/실수 쓰기를 외부 hollerith에 위임하는 경로를 읽었다."),
      code_source(24,"tests/test_deck_validation.py","PyDYNA registered-validator tests","code","RequiredFieldValidator; UniqueIDValidator; validate-on-export; custom material-reference example","선택적 검증 사례를 보유했다. 전체 물리·참조·수치 유효성 검증의 증거는 아니다."),
    ]
    rules=[
      rule(1,"Q01",[2],"주 입력은 keyword deck이며 *KEYWORD/본문/*END 또는 EOF 경계를 갖는다. include와 binary restart dump는 역할이 다르다. *KEYWORD ID/JOBID는 출력 prefix이고 input 파일 이름을 바꾸지 않는다.","Vol I 2-1–2-3 (PDF 367–369); 32-1–32-3 (PDF 3355–3357); 49-1–49-3 (PDF 4007–4009)",".k/.key 확장자가 파서의 버전 선언을 대신하지 않는다. 실사용 binary 버전은 확보·실행하지 않았다.","documented"),
      rule(2,"Q02",[2,12,22,23],"선두 * keyword와 $ comment, 고정·comma 자유 형식, 80/long 형식을 구분한다. 자유 형식에도 카드별 폭 제한이 남고 한 행 안에서 고정/자유 형식을 혼합하지 않는다. long 선택은 필드 폭과 solver 정수 범위를 같은 것으로 만들지 않는다.","Vol I 2-1–2-3, 2-29–2-31 (PDF 367–369,395–397); KeywordBase.write; field_writer._field_iterator","모든 카드의 예외 폭·수치/문자 형식·native text encoding 및 platform 동등성은 전수 검증하지 않았다."),
      rule(3,"Q03",[2,16],"값은 일관된 단위계를 사용자가 정해야 한다. 화면 단위 표시를 숫자 자동 변환의 근거로 삼으면 안 된다. 공식 예제 1·3은 kg-m-s-N-Pa를 명시한다.","Vol I 2-28 (PDF 394); Intro Examples PDF 7–8 and 20","모든 thermal/chemistry/multiphysics의 별도 단위 문맥은 전수 정리하지 않았다.","documented"),
      rule(4,"Q04",[2,3,9,10,15],"필수·선택·반복·조건부 카드를 카드별로 보존해야 한다. 중간 optional card 생략과 끝 optional 생략은 다르다. TITLE/ID/options는 추가 행을 바꿀 수 있으며 blank와 zero는 일괄 동일시할 수 없다.","Vol I 2-30 (PDF396); *CONTROL_IMPLICIT_GENERAL 12-320 (PDF1646); *SECTION_SHELL 41-62 (PDF3744); Vol II 2-1–2-3; codegen manifest/additional-cards","IMPLICIT_GENERAL의 zero는 실제 0, blank는 상속인 반례를 확인했다. 모든 variant 조합의 전개/field 검토는 미완료다."),
      rule(5,"Q05",[2,8,10,17],"include는 중첩·종료·경로 검색·parameter scope·transform에 영향을 준다. INCLUDE_PATH_RELATIVE는 input 위치 기준이고 긴 경로 연속 규칙이 별도다. PARAMETER는 사용 전에 정의하고 LOCAL 범위를 보존해야 한다.","Vol I *INCLUDE 27-3–27-8 (PDF2977–2982); INCLUDE_PATH 27-50 (PDF3024); PARAMETER 36-2–36-5 (PDF3576–3579); Deck.expand 244–349","PyDYNA expand는 못 찾은 include를 남길 수 있고 strict=False에서 파싱 실패가 raw string으로 보존될 수 있다. parser 성공을 native 의미 검증으로 보지 않는다.",examples=["dyna-E04","dyna-E05"]),
      rule(6,"Q06",[2,8,24],"NID/EID/PID/SECID/MID/EOSID/HGID/set/function 등 서로 다른 참조를 보존한다. EID/PID 연결과 section/material 연결, PARAMETER 선행 의존 및 include ID offset은 별도 검증 대상이다.","Vol I 2-2 (PDF368); INCLUDE_TRANSFORM PDF2977–2982; PART 37-2–37-5 (PDF3590–3593); PyDYNA validator tests","모든 keyword의 ID 허용 범위·label 허용 여부·namespace·전방 참조 예외를 전수 매핑하지 않았다."),
      rule(7,"Q07",[2],"요소별 connectivity 순서·방향·퇴화·차수를 solver 전용으로 매핑해야 한다. ELEMENT_SOLID Fig19-31은 4/6/8/10/20 node 순서를 제시하며 N4 등 반복으로 표현하는 퇴화 패턴과 고차 자동 midside 생성의 set 차이가 있다.","Vol I ELEMENT_SHELL 19-99–19-100 (PDF2715–2716); ELEMENT_SOLID 19-119–19-124 (PDF2735–2740), Fig19-31 visually inspected","전체 beam/shell/solid/high-order/particle/multiphysics의 면·방향·퇴화 표를 기계 schema로 전환하거나 시험하지 않았다."),
      rule(8,"Q08",[2,3,9],"Part가 section/material/EOS/hourglass 등을 참조하며 section은 formulation·적분 등의 의미를 가진다. nodal set과 segment set은 동일 객체가 아니다. 재료가 존재해도 모든 요소 formulation에서 사용 가능하다는 뜻은 아니다.","Vol I PART PDF3590–3593; SECTION_SHELL PDF3744; SET_NODE PDF3875; SET_SEGMENT PDF3901; Vol II MAT introduction PDF87–89","assembly·all material/EOS/thermal·all set/section의 전수 객체 매핑 구현은 없다."),
      rule(9,"Q09",[2],"하중·구속·초기조건은 node/set/rigid/segment 선택과 DOF·curve·CID 참조에 따라 다른 카드를 쓴다. INITIAL_VELOCITY의 제외 set은 추가 행을 요구할 수 있고 LOAD_SEGMENT의 고차 node/ID option도 행 수를 바꾼다.","Vol I PRESCRIBED_MOTION PDF754; SPC PDF810; CONTACT PDF1119; DEFINE_COORDINATE_SYSTEM PDF2197; DEFINE_CURVE PDF2226; INITIAL_VELOCITY PDF3175; LOAD_NODE PDF3442; LOAD_SEGMENT PDF3464","모든 contact algorithm·DOF 활성 조건·전역/국부 좌표 변환·곡선 종류의 의미를 전수 검토하지 않았다."),
      rule(10,"Q10",[2],"implicit 활성·종료·시간간격·출력 빈도/내용·binary restart는 서로 다른 상태다. simple/small/full restart는 허용 변경과 참조 유지가 다르다. sense switch SW1/SW3와 외부 kill을 같은 중지 기능으로 구현하면 안 된다.","Vol I IMPLICIT_GENERAL PDF1646; TERMINATION PDF1884; TIMESTEP PDF1909; DATABASE_BINARY PDF1998–1999; EXTENT_BINARY PDF2030; GS PDF385–389; Restart PDF4007–4010","MPP frontend Ctrl-C가 프로세스를 죽일 수 있다는 조건을 보존했다. dump 호환성·실행 중 제어·모든 restart 옵션은 검증하지 않았다."),
      rule(11,"Q11",[5,8,13,16,17,18,19,24],"공식 82 deck 원본 ZIP과 사례 1·3의 문서 정답을 취득했다. 별도로 MIT source/fixture는 writer·include/parameter·transform·오류 보존 동작을 조사할 수 있는 자산이다. parser fixture를 완전한 해석 모델로 세지 않는다.","catalogues/dyna-official-examples.csv; Intro manual PDF7–12,19–24; Taylor Bar create_input_deck; test_deck and test_parameter_error_location","공식 예제의 재배포 허가는 미확인이다. upstream test 예상과 수치 결과는 여기서 실행한 관측이 아니다.",examples=["dyna-E01","dyna-E02","dyna-E03","dyna-E04","dyna-E05","dyna-E06"]),
      rule(12,"Q12",[1,2,3,4,6,7,9,11,20,21],"문서 R17, 예제 v971, PyDYNA dev snapshot을 별도 version 축으로 고정했다. MIT writer/schema 사용권과 상용 LS-DYNA 실행권은 구분한다. 전수 색인 및 exact-name 대응은 전수 field·생성·solver 검증을 대신하지 않는다.","Manual covers R17@e8334f9fb; PyDYNA revision 90270f7 pyproject; README License; catalogue reconciliation","R17 모든 field·옵션 조합·semantic validation·runtime은 미검증이다. source schema의 대상 manual release는 명시되지 않아 R17 대응률로 환산할 수 없다."),
    ]
    examples=[]
    vendor=list(csv.DictReader((ROOT/"catalogues/dyna-official-examples.csv").open()))
    members=["example_01/thin_shell_elform_16/ex_01_thin_shell_elform_16.k",
             "example_03/solid_elform_-1/4x6x4_mesh/ex_03_solid_elform_-1_4x6x4_mesh.k"]
    expected=["Intro manual PDF8: ELFORM16 max principal stress 0.696e6 Pa; Uz -1.404e-5 m. v971/double-precision published result, postprocessing assumptions PDF9; not reproduced here.",
              "Intro manual PDF21: ELFORM -1 axial stress -5.35e6 Pa; Uz -1.005e-4 m. v971/double-precision published result; nodal extrapolation/postprocessing assumptions apply; not reproduced here."]
    for i,member in enumerate(members,1):
        r=next(x for x in vendor if x['archive_member']==member)
        examples.append({"id":f"dyna-E{i:02d}","source_ids":["dyna-D05","dyna-D16"],"url":sources[4]['url'],
            "file":None,"analysis_file":"tmp/dyna/official-examples/"+member,"archive_member":member,"sha256":r['sha256'],
            "version":"June 2013 draft / LS-DYNA v971, double precision per manual introduction",
            "kind":"official-deck","purpose":"Complete mesh + material/section/part + implicit pressure benchmark deck; inspected locally",
            "expected":expected[i-1],"license":"Official free download; redistribution grant not located","redistribution":"unknown","solver_executed":False})
    fixture_specs=[
      (3,"tests/testfiles/standard/base.k","Base parser fixture with control/mesh/part; zero section/material references mean not a complete structural benchmark","No numerical result asserted; this collection did not execute parser or solver",[8]),
      (4,"tests/testfiles/keywords/expand_parameters/collision/main_with_consumer.k","Three include modules expose global parameter collisions","Upstream test_deck.py 911–951 asserts section100 ELFORM=1, section200=2, section300=2 at import/expand time; not executed here",[17]),
      (5,"tests/testfiles/keywords/parameter_error_location/test_undefined_param.k","Undefined parameter reference fixture; distinguishes retained-source writing from resolved writing","Upstream tests retain &undef with retain_parameters=True; default False write raises ValueError; not executed here",[18]),
      (6,"tests/testfiles/keywords/transform/test.k","Connectivity/node transform fixture including deliberately short element records","See upstream test_transform.py; not a complete solver model; no runtime observation here",[19]),
      (7,"tests/testfiles/keywords/expand_parameters/collision_local/main.k","Two includes with PARAMETER_LOCAL prevent global collisions","Upstream test_deck.py 954 onward asserts independent module values; not executed here",[17]),
    ]
    for n,path,purpose,expect,ids in fixture_specs:
        local="examples/dyna/pydyna/"+path;data=(ROOT/local).read_bytes()
        examples.append({"id":f"dyna-E{n:02d}","source_ids":[f"dyna-D{i:02d}" for i in ids]+["dyna-D06"],"url":SRC+path,
            "file":local,"sha256":hashlib.sha256(data).hexdigest(),"version":REV,"kind":"source-example",
            "purpose":purpose,"expected":expect,"license":"MIT root LICENSE, no path exception found; NOTICE and LICENSE included",
            "redistribution":"permitted-with-notice","solver_executed":False})
    assets=[
      {"id":"dyna-C01","source_ids":["dyna-D06","dyna-D08","dyna-D12","dyna-D22","dyna-D23"],"role":"writer",
       "repository":"https://github.com/ansys/pydyna","revision":REV,
       "paths":["src/ansys/dyna/core/lib/deck.py","src/ansys/dyna/core/lib/keyword_base.py","src/ansys/dyna/core/lib/card_writer.py","src/ansys/dyna/core/lib/field_writer.py"],
       "scope":"Native keyword card/deck text writing with active cards, fixed/long field machinery and parameter retain/resolve paths; Deck can also contain raw strings",
       "limits":"Reference source subset is not installed. Untyped preserved text does not count as schema-backed support. validate=False is write default; optional validators are not full solver checks.",
       "license":"MIT","local_files":["assets/dyna/pydyna/src/ansys/dyna/core/lib/"+p for p in ["deck.py","keyword_base.py","card_writer.py","field_writer.py"]],"executed":False},
      {"id":"dyna-C02","source_ids":["dyna-D06","dyna-D07","dyna-D09","dyna-D10","dyna-D11","dyna-D15"],"role":"schema",
       "repository":"https://github.com/ansys/pydyna","revision":REV,
       "paths":["codegen/kwd.json","codegen/manifest.json","codegen/additional-cards.json","src/ansys/dyna/core/keywords/keyword_classes/type_mapping.py"],
       "scope":"Full raw 3685-spec schema, 12219 cards, 69523 fields, 3685 generated-class name mappings, correction/conditional/additional definitions physically retained",
       "limits":"Raw schema names, generated aliases and R17 manual TOC use different denominators. 1544 exact TOC-schema rows and 1561 TOC-class rows do not measure semantic coverage. 229 mismatches individually preserved, not labelled unsupported. All variant expansion/full field review/runtime remain false.",
       "license":"MIT repository declaration; no path-specific exclusion found; preserve upstream LICENSE and source inventory",
       "local_files":["assets/dyna/pydyna/"+p for p in ["codegen/kwd.json","codegen/manifest.json","codegen/additional-cards.json","src/ansys/dyna/core/keywords/keyword_classes/type_mapping.py"]],"executed":False},
      {"id":"dyna-C03","source_ids":["dyna-D08","dyna-D17","dyna-D18","dyna-D19"],"role":"parser",
       "repository":"https://github.com/ansys/pydyna","revision":REV,
       "paths":["src/ansys/dyna/core/lib/deck.py","src/ansys/dyna/core/lib/parameters.py","src/ansys/dyna/core/lib/transform.py"],
       "scope":"Include expansion, parameter scopes, transform and raw/error preservation reference; fixtures and upstream assertions retained",
       "limits":"Missing include may remain unresolved; strict mode default false; undefined references have distinct retained-write behavior. Collection read source only, no parser or tests run.",
       "license":"MIT","local_files":["assets/dyna/pydyna/src/ansys/dyna/core/lib/"+p for p in ["deck.py","parameters.py","transform.py"]],"executed":False},
    ]
    manifest={"key":"dyna","title":"LS-DYNA","scope":"Official released R17 keyword manuals Vol I–III, their entire TOC and starred keyword rows; alphabetic material aliases; actual official example files; pinned MIT PyDYNA schema/writer references. No solver or GUI implementation.",
        "versions":{"documentation":VERSION,"solver":"R17 documentation target only; no licensed solver binary acquired",
                    "source":"ansys-dyna-core 0.13.dev0 @ "+REV,"examples":"Official June 2013/v971 manual and pinned PyDYNA source fixtures; not equivalent to R17 runtime proof","binary_tested":None},
        "sources":sources,"catalogue":{"files":["catalogues/"+p for p in ["dyna.csv","dyna-toc-all.csv","dyna-material-aliases.csv","dyna-pydyna-schema.csv","dyna-toc-schema-differences.csv","dyna-reconciliation.json","dyna-official-examples.csv","dyna-read-sections.json","dyna-validation.json"]],
           "source_ids":["dyna-D02","dyna-D03","dyna-D04","dyna-D09","dyna-D11"],
           "scope":"All R17 Vol I–III TOC rows: 2030 (1773 starred family/keyword rows + 257 other headings/card/options). Material alphabetic list is a separate 362-row companion, not added to keyword denominator.",
           "entry_count":1773,"count_unit":"starred official TOC rows, including 58 family headings and 23 duplicate literal-name rows",
           "completeness":"complete-index","reconciliation":"Vol I 1016/1016; II 366/366; III 391/391; 0 unparsed starred rows and 0 unresolved PDF targets. All 1773 target headers checked; 2 official TOC folio errors retained separately. 2030/2030 dotted TOC rows retained. 3685 raw schema specs and 3685 class mappings enumerated; exact matching only, no unsupported inference.",
           "full_field_review_complete":False,"full_variant_expansion_complete":False,"counts":stats},
        "rules":rules,"examples":examples,"code_assets":assets,
        "coverage":[{"question_id":f"Q{i:02d}","rule_ids":[f"dyna-R{i:02d}"],"status":rules[i-1]['status'],"missing":rules[i-1]['limits']} for i in range(1,13)],
        "acquisition_log":[
          {"target":"Latest released official manual set","outcome":"R17 Vol I–III downloaded, hashed, 7373 PDF pages; covers dated 2026-06-11. Draft manuals and older v261/R16 web help are not substituted."},
          {"target":"Complete keyword index and aliases","outcome":"pdftotext layout extraction + exact target-header comparison; 2030 full TOC rows, 1773 starred rows, 362 alphabetic material rows, 2 official source TOC errors recorded."},
          {"target":"Large manual web-view access","outcome":"Web viewer rejected some large Vol I/II PDF opens; direct official HTTP downloads succeeded. These were actually obtained, not link-only records."},
          {"target":"Actual official example inputs","outcome":"17,393,584-byte ZIP obtained; 82 .k files totaling 140,830,499 uncompressed bytes inventoried and hashed. Example 1 and 3 source plus original numerical comparison sections read. Unknown redistribution => tmp only."},
          {"target":"Native input-generating source and schema","outcome":"36 pinned MIT upstream files downloaded (23,271,877 bytes), including entire 22,287,505-byte kwd.json, corrections, supplementary cards, writer and fixtures. Bytes unchanged. Root LICENSE + pyproject MIT + SPDX + no path exception check; archive NOTICE/inventory supplied. kwd.json excluded from public Git staging by integration policy."},
          {"target":"Reproducibility and runtime boundary","outcome":"Acquisition, catalogue and snapshot packaging scripts retained. Executed research scripts only; never installed/imported PyDYNA, generated a deck, ran upstream tests, or invoked LS-DYNA."}],
        "gaps":["No all-fields/all-variants semantic specification or implemented full native generator.",
                 "Schema source manual release unspecified; exact-name correspondence cannot establish R17 version or field coverage.",
                 "229 TOC rows lack exact raw schema keys; family/option/alias differences and actual omissions require semantic review. They are not automatically 229 unsupported keywords.",
                 "No licensed binary or solver read/run/restart validation. Official v971 numbers and upstream assertions are external evidence only.",
                 "Official manual/example redistribution permission was not located; their originals remain analysis-only. Locator/hash manifests permit reacquisition.",
                 "Volume III catalogue is complete but individual multiphysics field semantics were not reviewed.",
                 "Native encoding, every ID namespace/range, high-order face table, contact algorithm and unit context remain per-keyword review work."],
        "runtime_verified":False}
    target=ROOT/"solvers/dyna.json";target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"sources":len(sources),"rules":len(rules),"examples":len(examples),"code_assets":len(assets),"runtime_verified":False}))
