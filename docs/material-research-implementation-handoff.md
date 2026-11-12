# 재료 연구·전문가 자문·native 후처리의 Prep 구현 인계

기준 Prep555af5b3ab2c6e7dc276111609302ef565bb4fc8,Workbench104cdd6888a5554eecc8cf965c60ff1bd980b6da. 전체 정본은 [WB 통합명세](https://github.com/pikachu444/caelab-workbench/blob/98be90bfe1d8d02ae099bc0aecf84d1d11110218/docs/specs/spec-cae-research-implementation.md),[core C7–C11](https://github.com/pikachu444/caelab-workbench/blob/98be90bfe1d8d02ae099bc0aecf84d1d11110218/docs/specs/cae-research/core-implementation.md),[실제토의·검토·자료색인](https://github.com/pikachu444/caelab-workbench/blob/98be90bfe1d8d02ae099bc0aecf84d1d11110218/docs/specs/cae-research/README.md)입니다. 명세 갱신이며 새 제품 기능 구현 완료가 아닙니다. DP/Xia는 예시입니다.

## Prep 담당과 기존 실제 코드

| 경로/접점 | 현재 재사용 | 구현할 변경 |
|---|---|---|
| src/caelab_prep/application/contracts.py | ObjectRef/PropertySpec/SetProperties/PropertyHost | material binding과공용위젯host를기존typed계약으로연결 |
| src/caelab_prep/application/live_transport.py | LiveClient(descriptor_path_or_dict,timeout=30).request(method,params=None,request_id=None) | 기존열린owner프로세스에새typed prepare/commit명령추가;새transport/session/queue없음 |
| 기존 live/GUI owner dispatcher | doc/epoch/revision/token/request_id/CAS·Qt주스레드소유Session | prepare계획보관/expiry·원자multi-resourcecommit·acklost상태조회 |
| application/card_text.py 및 native RAD codec/provider | 고정폭span·SetProperties→set_fields·원덱/INCLUDE보존 | 등록된exactsolver/law/version에만native계수/곡선binding |
| 기존 CommandDispatcher.execute_many | 여러resource후보상태/additions/removals/expectedrevision한command | material+curve+link 전체를한Undo/Redo로확정 |
| NumericEdit/CurveTable/CurvePlot/PropertyEditor·PropertyHost | 실제Qt 숫자·단위·곡선·속성부품 | WBMaterialStudy의draft host로재사용;파일복제대신package소비 |
| 기존문서저장/export | Prep문서/native덱소유 | 보정report/계수등록을nativecard지원으로승격하지않음 |

현재typedLAW1/LAW36의범위와새LAW33·다른native법칙binding의미구현을구분합니다. Workbench최적화backend가계산된다고PrepApply가자동지원되는것은아닙니다. 원native덱실행은보정profile검증의지원목록과별도로유지합니다. 새로운범용전처리기/구성식DB/solver실행manager를Prep에추가하지않습니다.

## PREP01: 열린 문서에 preview→원자 Apply

1 Workbench는기존descriptor로이미열린Prepowner에접속하고 hello/describe/cards/properties를읽습니다. 연결실패때새headlessSession을만들어원파일을변경하지않습니다. handle={document_id,document_epoch,revision},targetObjectRef,exacttypedcapability와baselinehash를고정합니다.
2 material.prepare_apply({handle,target,profile_id,profile_revision,parameters,curves,evaluation_digest})를새명령으로추가합니다. server발급UUIDplan_id,handle,baseline_hashes,candidate_hashes,changes_preview,expires_at,supported,reason_codes를반환합니다. 유효60초. 설치/등록된nativebinding만허용하며stage중mutation0입니다.
3 모든값/단위/고정폭native필드/곡선ID/reference/dependent사용처를검증한candidate resource state·추가/삭제집합을서버에보관합니다. 원문서전체replacement나임의함수명/코드import를받지않습니다.
4 material.commit_apply({plan_id,handle,candidate_hashes})는같은ownerSessionlock/기존guard아래epoch/revision/baseline/candidate/expiry를재검사합니다. 기존execute_many를한번만호출합니다. 응답={status,handle_after,command_id,applied_hashes,reason_codes}.
5 stale/만료/unsupported면문서변경0,UI draft보존과원인표시입니다. 새읽기/preview없이자동재적용하지않습니다. binding/atomicprepare가없으면UNSUPPORTED_ATOMIC_APPLY/export-only입니다.
6 첫scalarLAW1Ebinding은기존document.edit typedSetProperties→set_fields의한Undo로먼저연결할수있습니다. multi-card를여러set_fields/별도Undo명령으로쪼개지않습니다.
7 기존requestcache512는영구exactly-once저장이아닙니다. acklostretry는같은request_id만사용합니다. 서버재시작/cache미스/expiry뒤새IDcommit자동재시도금지. handle/currenttypedhash를재조회하여applied_state_observed또는unknown_after_disconnect를표시합니다. token/secret은LLM·manifest·보고서에넣지않습니다.

인수: 열린실제GUI문서와별도실제LiveClient를사용해정상scalar/linkedcurve편집·prepare mutation0·commit한command·UndoRedo각한번·저장재열기/nativeexport, staleepoch/revision·partialinvalidcurve·plan만료·다른문서target·실패rollback·acklost동일ID·restartunknown을검사합니다. mock만으로열린owner연결을닫지않습니다. Windows실제OS/IME·한글공백경로·고해상도와native solver카드수용/물리동등성은별도해당profile인수입니다.

## LINK01/UI01: 공용 Qt와 독립 프로그램

Workbench MaterialStudyWindow는 --study 또는 --project/--node로열리는별도WindowsQt연구창입니다. Model/Experiments/Parameters/Comparisons/Campaigns/Evaluations/Exports/Reviews트리,숫자/계수·곡선/잔차plot·로그dock,실제CSVpreview/fit/stop/cancel/save/reopen/export/Apply를연결합니다. Prep의위젯만재사용하며별도보정history를위젯이소유하지않습니다.

WBMaterialParameterHost는PropertyHost인터페이스를구현하고위젯용localintegerdraftrevision을씁니다. 이것을materialmanifestbytesSHA또는Prepdocumentepoch/revision으로위장하지않습니다. 위젯편집은draft,configureCommit때WBserviceCAS입니다. nativePrepObjectRef는실제Applytarget에서만사용합니다. 원CSV자동덮어쓰기없음.

Workbenchproject의material_study role첫저장은v4,reader/SaveAs는v1–4입니다. programid=caelab_material_study,kind=research의상대manifest관계이며FE input/output연결이아닙니다. Prep문서포맷을Workbenchproject4로바꾸지않습니다. post-onlyderivedsidecar는현WBprojectv3compatible입니다. MDOstudyv2를materialstudy로자동이행하지않습니다.

## 모델별 native binding과 후처리 경계

모델descriptor/계수/다시험적합/잔차/holdout/제약/식별성은WB공용서비스가소유합니다. exactDP/LAW33/derivedXBP·Ogden·Prony·NEML·JC의계산source/API와한계는WB A/B명세에고정합니다. Xia2002와LAW112를동일시하지않고derivedXBP의nativeexport/Apply미지원을표시합니다.

Prep은supportedsolver/version/law의nativecard·curve/include생성/검증/export를소유합니다. export는새파일/manifest이며열린문서변경과별개입니다. WorkbenchINP토큰치환을RAD고정폭renderer에쓰지않습니다. 현재없는field/card/curvebinding은보존/읽기·명시미지원으로남기고출력성공을발명하지않습니다.

전문가도구는읽기조회이며모델변경/덱덮어쓰기/solver제출도구를노출하지않습니다. 제안·별도review는동일immutablecontext/원문/실제result를읽고명시Apply/run은사용자동작입니다. PrepMCP가작동한다는사실과WBRAG/providerloop의연동완료를구분합니다.

OpenCourantRP는별도설치앱,WBJobManager는기존실행소유자입니다. vanilla수동보기/WB소유converter·수치조회/optionalAGPLforkexacthandoff를독립인수합니다. 선택forkCLI는 --post-only --handoff <json> --receipt <json>,현재upstream기능이아닙니다. Prep은새후처리queue를만들지않습니다. 원Prep문서/덱/INCLUDE와불변run은RP에수정대상으로주지않습니다.

## 작업 순서와 완료 판정

PREP01의기존owner읽기/단일typedscalar연결→등록된nativebinding의prepare→multi-resourceatomiccommit·UndoRedo·오류/acklost→공용위젯host·독립MaterialStudy연결순서로진행합니다. WB CORE01/02·STORE01과contract를먼저고정하고nativeprofile별물리/변환/solver검증은그담당작업과연결합니다. 공용파일을각자중복편집하지않고새파일material_binding.py와기존dispatcher확장owner를한명으로둡니다.

구현자가아닌QA가동일commit의실제파일·문서·command·GUI·출력과오류를확인해야작업을닫습니다. 문서의인터페이스정의·mock·sourcepin·수치reference를제품사용자flow완료로세지않습니다. 원환경단절전실행과회수한원bytes/새재구성/현재재검사는WB자산manifest와토의기록에서분리합니다.
