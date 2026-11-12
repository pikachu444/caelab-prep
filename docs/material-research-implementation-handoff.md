# 재료 연구·전문가 자문·솔버 결과 후처리의 Prep 구현 인계

이 문서는 Prep `555af5b3ab2c6e7dc276111609302ef565bb4fc8`와 Workbench `104cdd6888a5554eecc8cf965c60ff1bd980b6da`를 기준으로 작성했습니다. 전체 기준은 [WB 통합 명세](https://github.com/pikachu444/caelab-workbench/blob/31fea8e1f03e2479549aaf7f6dc5a55a62d3d434/docs/specs/spec-cae-research-implementation.md), [공통 계약 C7–C11](https://github.com/pikachu444/caelab-workbench/blob/31fea8e1f03e2479549aaf7f6dc5a55a62d3d434/docs/specs/cae-research/core-implementation.md), [실제 토의·검토·자료 색인](https://github.com/pikachu444/caelab-workbench/blob/31fea8e1f03e2479549aaf7f6dc5a55a62d3d434/docs/specs/cae-research/README.md)에 있습니다. 이번 변경은 명세 갱신이며, 새 제품 기능의 구현 완료를 뜻하지 않습니다. Drucker–Prager(DP)와 Xia는 여러 재료 모델 중 예시입니다.

## Prep가 담당할 일과 재사용할 코드

| 경로·접점 | 현재 코드가 제공하는 기능 | 구현할 변경 |
|---|---|---|
| `src/caelab_prep/application/contracts.py` | `ObjectRef` / `PropertySpec` / `SetProperties` / `PropertyHost` | 재료와 솔버 카드의 연결 및 공용 위젯의 호스트를 기존 형식 지정 계약으로 연결합니다. |
| `src/caelab_prep/application/live_transport.py` | `LiveClient(descriptor_path_or_dict,timeout=30).request(method,params=None,request_id=None)` | 이미 열린 문서를 소유한 프로세스에 준비·확정 명령을 추가합니다. 별도 통신 계층·세션·작업 대기열은 만들지 않습니다. |
| 기존 live/GUI 소유 프로세스의 명령 분배기 | 문서·`epoch`·`revision`·`token`·`request_id`, 비교 후 교체(CAS), Qt 주 스레드의 `Session` 소유 | 적용 계획의 보관·만료, 여러 자원의 원자적 확정, 응답 유실 후 상태 조회를 추가합니다. |
| `application/card_text.py` 및 솔버 고유 RAD 코덱·제공자 | 고정폭 필드의 범위, `SetProperties` → `set_fields`, 원 덱·`INCLUDE` 보존 | 등록된 솔버·법칙·판본에 한해 계수와 곡선을 솔버 카드에 연결합니다. |
| 기존 `CommandDispatcher.execute_many` | 여러 자원의 후보 상태·추가·삭제·예상 개정을 한 명령으로 처리 | 재료·곡선·연결을 한 번의 실행 취소·다시 실행(Undo/Redo) 단위로 확정합니다. |
| `NumericEdit` / `CurveTable` / `CurvePlot` / `PropertyEditor` · `PropertyHost` | 실제 Qt 숫자·단위·곡선·속성 부품 | `WBMaterialStudy`의 편집 초안을 표시하는 호스트로 재사용합니다. 파일을 복사하지 않고 패키지로 사용합니다. |
| 기존 문서 저장·내보내기 | Prep 문서와 솔버 입력 덱의 소유 | 계수 보정 보고서나 계수 등록만으로 솔버 카드까지 지원한다고 표시하지 않습니다. |

현재 형식이 지정된 LAW1·LAW36의 지원 범위와, 아직 구현하지 않은 LAW33·다른 솔버 법칙의 카드 연결을 구분합니다. Workbench의 최적화 계산이 가능해도 Prep의 문서 적용(Apply)이 자동으로 지원되지는 않습니다. 원래의 솔버 입력 덱을 실행하는 기능과 보정용 모델의 검증 목록도 따로 유지합니다. Prep에 새 범용 전처리기, 구성식 데이터베이스, 솔버 실행 관리자를 추가하지 않습니다.

## PREP01: 열린 문서에서 미리 본 뒤 한 번에 적용

1. Workbench는 기존 접속 설명자(`descriptor`)로 이미 열린 Prep 소유 프로세스에 접속해 `hello` / `describe` / `cards` / `properties`를 읽습니다. 연결 실패를 우회하려고 화면 없는 새 `Session`을 만들거나 원파일을 바꾸어서는 안 됩니다. `handle={document_id,document_epoch,revision}`, 대상 `ObjectRef`, 지원하는 카드·필드의 정확한 형식과 기준 해시를 고정합니다.
2. 새 명령 `material.prepare_apply({handle,target,profile_id,profile_revision,parameters,curves,evaluation_digest})`를 추가합니다. 서버가 UUID 형식의 `plan_id`를 발급하고 `handle`, `baseline_hashes`, `candidate_hashes`, `changes_preview`, `expires_at`, `supported`, `reason_codes`를 반환합니다. 계획의 유효 시간은 60초입니다. 설치·등록된 솔버 카드 연결만 허용하며, 준비 중에는 문서를 전혀 변경하지 않습니다.
3. 서버는 모든 값·단위·고정폭 필드·곡선 ID·참조·종속 사용처를 검증한 뒤 후보 자원 상태와 추가·삭제 집합을 보관합니다. 문서 전체를 교체하는 요청이나 임의의 함수명·코드 가져오기 요청은 받지 않습니다.
4. `material.commit_apply({plan_id,handle,candidate_hashes})`는 같은 소유 `Session`의 잠금과 기존 보호 조건 아래에서 `epoch` / `revision` / 기준 해시 / 후보 해시 / 만료 여부를 다시 검사합니다. 기존 `execute_many`를 딱 한 번 호출합니다. 응답은 `{status,handle_after,command_id,applied_hashes,reason_codes}`입니다.
5. 문서가 달라졌거나 계획이 만료됐거나 기능을 지원하지 않으면 변경은 0건입니다. 화면의 초안은 보존하고 원인을 표시합니다. 새 조회와 미리보기 없이 자동 재적용하지 않습니다. 카드 연결이나 원자적 준비를 지원하지 않으면 `UNSUPPORTED_ATOMIC_APPLY`를 표시하고 내보내기만 허용합니다.
6. 첫 단계에서는 LAW1 카드의 탄성계수 E 한 개를 기존 `document.edit`의 형식 지정 `SetProperties` → `set_fields` 경로로 연결할 수 있습니다. 한 번의 Undo 단위로 처리하며, 여러 카드를 여러 `set_fields`나 별도 Undo 명령으로 나누어 적용하지 않습니다.
7. 기존 요청 캐시의 크기 512는 영구적인 1회 실행 보장이 아닙니다. 응답을 잃은 뒤 재시도할 때는 같은 `request_id`만 사용합니다. 서버 재시작·캐시 누락·만료 뒤에는 새 ID로 확정을 자동 재시도하지 않습니다. 문서 핸들과 현재 형식 지정 값의 해시를 다시 조회해, 적용된 상태를 관측했다면 `applied_state_observed`, 연결 단절 뒤 판단할 수 없다면 `unknown_after_disconnect`를 표시합니다. 토큰과 비밀값은 대규모 언어 모델(LLM), 파일 목록(manifest), 보고서에 넣지 않습니다.

완료 검사는 실제 열린 GUI 문서와 별도 실제 `LiveClient`로 수행합니다. 정상 단일 값·연결 곡선 편집, 준비 중 변경 0건, 확정 시 명령 1건, Undo/Redo 각 1회, 저장 후 재열기와 솔버 덱 내보내기를 확인합니다. 오래된 `epoch`·`revision`, 일부 잘못된 곡선, 계획 만료, 다른 문서의 대상, 실패 시 되돌리기, 응답 유실 뒤 동일 ID 재시도, 재시작 뒤 판단 불가 상태도 확인합니다. 모의 객체만으로 열린 소유 프로세스 연결을 완료 처리하지 않습니다. 실제 Windows의 운영체제·한글 입력기(IME)·한글 및 공백 경로·고해상도 동작, 솔버의 카드 수용과 물리적 동등성은 해당 모델별로 따로 검사합니다.

## LINK01/UI01: 공용 Qt 부품과 독립 연구 프로그램

다음 세 문단은 구현할 화면·저장 동작의 규칙이며, 현재 구현 완료를 뜻하지 않습니다.

Workbench의 `MaterialStudyWindow`는 `--study` 또는 `--project` / `--node`로 여는 별도 Windows Qt 연구창입니다. 트리에는 모델(`Model`), 시험(`Experiments`), 계수(`Parameters`), 비교(`Comparisons`), 반복 계산 묶음(`Campaigns`), 평가(`Evaluations`), 내보내기(`Exports`), 검토(`Reviews`)를 둡니다. 숫자·계수 표, 곡선·잔차 그래프, 로그 패널을 제공하고 실제 CSV 미리보기·적합·정지·취소·저장·재열기·내보내기·Apply를 연결합니다. Prep의 위젯을 재사용하되 위젯이 별도의 보정 이력을 소유하지는 않습니다.

`WBMaterialParameterHost`는 `PropertyHost` 인터페이스를 구현합니다. 위젯에는 초안용 지역 정수 개정 번호를 사용합니다. 이 번호는 재료 manifest의 바이트 SHA나 Prep 문서의 `epoch` / `revision`이 아닙니다. 위젯 편집은 초안입니다. 사용자가 초안 확정을 요청하면 Workbench 서비스의 `configure(...)`가 CAS로 저장합니다. 실제 Prep의 `ObjectRef`는 실제 Apply 대상에만 사용합니다. 원 CSV는 자동으로 덮어쓰지 않습니다.

Workbench 프로젝트에 `material_study` 역할을 처음 저장할 때는 v4를 사용하고, 읽기와 다른 이름으로 저장(SaveAs)은 v1–4를 지원합니다. `programid=caelab_material_study`, `kind=research`인 노드가 상대 경로의 manifest를 참조하는 관계이며, 유한요소(FE) 입력·출력 연결이 아닙니다. Prep 문서 형식을 Workbench 프로젝트 v4로 바꾸지 않습니다. 후처리 전용 파생 자료의 별도 보조 파일은 현재 Workbench 프로젝트 v3와 호환됩니다. MDO study v2를 재료 연구로 자동 변환하지 않습니다.

## 모델별 솔버 카드 연결과 후처리의 책임

Workbench 공용 서비스는 모델 설명자, 계수, 여러 시험의 동시 적합, 잔차, 적합에 쓰지 않은 검증 자료(holdout), 제약, 계수를 구별해 알아낼 수 있는지에 대한 판단(식별성)을 소유합니다. DP / LAW33 / 파생 XBP / Ogden / Prony / NEML / JC의 정확한 계산 소스·API와 한계는 Workbench A/B 명세를 따릅니다. Xia2002와 LAW112를 같은 모델로 취급하지 않습니다. 파생 XBP는 솔버 덱 내보내기와 Apply가 미지원임을 표시합니다.

Prep는 지원하는 솔버·판본·법칙에 대해 솔버 카드·곡선·포함 파일의 생성·검증·내보내기를 소유합니다. 내보내기는 새 파일과 manifest를 만드는 일이며, 열린 문서의 변경과 별개입니다. Workbench의 INP 토큰 치환 기능을 RAD 고정폭 출력에 사용하지 않습니다. 현재 연결이 없는 필드·카드·곡선은 보존·읽기 범위로 남기고 미지원임을 명시합니다. 해당 연결이 없으면 내보내기 성공으로 처리하지 않습니다.

전문가 도구는 읽기 조회만 제공합니다. 모델 변경·덱 덮어쓰기·솔버 제출 도구를 노출하지 않습니다. 제안과 별도 검토는 같은 불변 문맥·원문·실제 결과를 읽습니다. 명시적인 Apply와 실행은 사용자가 수행합니다. Prep의 모델 문맥 프로토콜(MCP)이 작동하는 것과 Workbench의 검색 증강 생성(RAG)·모델 제공자 호출 흐름이 연결된 것은 별개의 확인 사항입니다.

OpenCourantRP는 별도로 설치하는 앱이며, Workbench의 기존 `JobManager`가 실행을 소유합니다. 원본 앱에서 수동으로 보기, Workbench가 소유한 변환기·수치 조회, 선택적 AGPL 파생판에 대한 정확한 파일 전달을 각각 검사합니다. 선택 파생판의 명령줄은 `--post-only --handoff <json> --receipt <json>`이며, 현재 원본 앱이 제공하는 기능은 아닙니다. Prep에는 새 후처리 대기열을 만들지 않습니다. 원 Prep 문서·덱·`INCLUDE`와 불변 실행 기록은 RP가 수정할 대상으로 주지 않습니다.

## 작업 순서와 완료 판정

PREP01은 기존 소유 프로세스 조회와 형식이 지정된 단일 값 연결부터 시작합니다. 다음으로 등록된 카드 연결의 준비, 여러 자원의 원자적 확정과 Undo/Redo·오류·응답 유실 처리, 공용 위젯 호스트와 독립 `MaterialStudy` 연결 순으로 진행합니다. Workbench CORE01/02·STORE01과의 계약을 먼저 확정합니다. 모델별 물리 검증·변환·솔버 검증은 해당 담당 작업과 연결합니다. 공용 파일을 여러 사람이 중복 편집하지 않도록 새 `material_binding.py`와 기존 명령 분배기 확장은 한 명이 소유합니다.

작성자와 다른 QA가 같은 커밋의 실제 파일·문서·명령·GUI·출력·오류를 확인해야 작업을 닫습니다. 인터페이스 정의, 모의 객체, 소스 버전 고정, 수치 참조가 있다는 사실만으로 사용자의 전체 작업이 완료됐다고 판단하지 않습니다. 원환경 단절 전 실행, 회수한 원바이트, 새로 재구성한 자료, 현재 재검사는 Workbench 자산 manifest와 토의 기록에서 구분합니다.
