# 열린 GUI 문서 제어

이 연결은 실행 중인 Prep 창의 **같은 `PrepSession`**을 제어한다. 독립 CLI의 파일 열기와 다르며, 연결에 실패하면 문서 사본을 만들지 않는다. 현재 범위는 문서 조회·선택, 제공자가 지원하는 숫자/boolean scalar 편집, Undo/Redo, 작업문서 저장, 세션 이벤트 조회, CAD 메시 후보의 생성·상태·취소다. 케이스·집합 등 모든 모델 명령을 원격 노출하는 범위는 아니다. 선택적인 MCP 어댑터와 실제 목표 클라이언트 사용법은 [MCP 연결](mcp-client.md)에 별도로 설명한다.

## 연결과 수명

```sh
caelab-prep gui model_0000.rad --ipc prep-connection.json
caelab-prep live --connection prep-connection.json
caelab-prep live --connection prep-connection.json --method document.cards
```

`--no-3d`는 실제 Qt 편집기를 VTK 뷰포트 없이 연다. GUI에서는 **Automation → Start live control…**로 새 연결 파일을 지정할 수 있다. 주소와 실행 중인 메시 작업 여부를 상태 표시줄에서 확인한다. 공개 창 API는 `start_live_ipc(path)`, `live_ipc_status()`, `stop_live_ipc()`다.

서버는 `127.0.0.1`의 임의 포트에만 바인딩한다. 새 연결 파일은 형식/버전·주소·서버 ID·무작위 인증 토큰을 포함하며 POSIX에서는 `0600`으로 생성한다. 파일을 다른 사용자나 공개 저장소에 제공하지 않는다. 기존 파일·심볼릭 링크를 덮어쓰지 않으며 정상 종료 때 자신의 연결 파일만 삭제한다. 중단된 서버의 파일로 연결하면 명시 오류가 나며, 새 서버를 열려면 새 파일 경로를 선택한다. Windows ACL과 실제 Windows GUI 동작은 별도 후속 검증이다.

각 CLI 실행은 새 연결을 통해 **동일 서버**에 요청한다. `LiveClient`도 Qt/솔버 없이 사용할 수 있다.

```python
from caelab_prep.application.live_transport import LiveClient

client = LiveClient("prep-connection.json")
current = client.request("document.describe")
cards = client.request("document.cards")["cards"]
# UI에서 작업할 정확한 카드의 typed ref를 선택한다.
material = next(card["ref"] for card in cards if card["group"] == "Materials")
properties = client.request("document.properties", {"target": material})
changed = client.request("document.edit", {
    "handle": current["handle"],
    "target": material,
    "values": {"young_modulus": 205000},
    "units": {"young_modulus": "MPa"},
})
client.request("document.save", {
    "handle": changed["handle"], "path": "edited.caeprep",
})
```

위 수치와 MPa는 예시다. `document.properties`의 단위/허용 목록과 작업 대상의 실제 정보를 먼저 사용한다. native ID를 문서 객체 ID로 대신 전달하지 않는다.

## 메서드 계약

모든 요청은 공개 메서드와 JSON 데이터만 받는다. 코드 실행·임의 Python 호출은 제공하지 않는다. `document.describe`의 `handle`은 `document_id`, `document_epoch`, `revision` 세 값이다. 편집·선택·이력·저장·메시 시작에 모두 필요하다. 같은 작업문서를 다시 열어 ID가 같아도 epoch가 달라 이전 요청은 거부된다.

| 메서드 | 매개변수 / 결과 |
|---|---|
| `hello`, `document.describe` | `{}` → 실제 문서·handle·지원 메서드·draft/busy/modal·현재 이벤트 번호 |
| `document.cards` | `{}` → GUI 제공자의 typed reference와 표시명/그룹 |
| `document.properties` | `target` → 제공자의 값·단위·지원 필드 |
| `document.selection` | `{}` → 현재 정규 선택 |
| `document.select` | `handle`, `target` → 같은 GUI의 선택·속성 표시 |
| `document.edit` | `handle`, `target`, `values`, 선택적 `units` → 같은 `SetProperties` 검증과 한 Undo 명령 |
| `document.undo`, `document.redo` | `handle` → 공용 문서 이력 |
| `document.save` | `handle`, `path` → 원문 보존 `.caeprep` 저장. 솔버 출력/실행 아님 |
| `events.since` | `after` → 후속 세션/작업 이벤트와 새 번호. 버퍼가 만료되면 `event_gap`이며 문서를 다시 조회 |
| `mesh.start` | `handle`, `source`, `output`, `size`, `dimension`(2/3), 선택적 `interface_policy` → 실제 기존 후보 GUI와 Gmsh worker 작업 ID·취소 capability |
| `jobs.get` | `job_id` → 시작 문서 handle, 상태, 결과 자산/오류. 취소 capability는 반환하지 않음 |
| `jobs.cancel` | `job_id`, `cancel_token` → 생성자가 받은 capability로 해당 worker 취소 요청 |
| `jobs.close` | `job_id`, `cancel_token` → 종료된 후보 창 닫기. 실행 중이면 먼저 취소/종료 확인 |

처음 메시 생성의 국부 크기는 이 좁은 endpoint가 설정하지 않는다. 후보 GUI에서 해당 형상을 선택해 기존 국부 크기 작업을 수행한다. 성공한 메시 작업은 품질과 원자산을 가진 **후보**이며 문서 채택과 다르다. `quality_passed`와 `adopted=false`를 별도로 반환하고, 채택은 기존 GUI의 재료/단면·단위 검증을 따른다.

작업 ID는 한 후보 창의 workflow를 가리킨다. GUI에서 다시 Generate/Open/Adopt를 누르면 `generation`이 증가하고 `operation`과 상태가 새 실제 task를 따른다. 기존 종료 결과를 다음 실행의 상태로 재사용하지 않는다. 생성자가 받은 capability는 이 workflow에 속한다.

취소는 요청 시점에 성공으로 보고하지 않는다. `cancel_requested` 뒤 실제 worker를 terminate/reap하고 `cancelled`로 바뀐다. GUI 사용자도 보이는 후보 창에서 취소할 수 있다. 임의 클라이언트가 `jobs.get`으로 취소 권한을 얻지는 않는다. 연결을 끊어도 작업은 GUI 소유로 남으므로, 다시 연결해 작업 ID와 자신이 보관한 capability로 상태/취소를 처리한다. `operation=adopt`는 원자적인 문서 채택이므로 `cancellable=false`이고 취소를 거절한다. 서버/창 종료는 생성 worker의 취소·종료 또는 시작된 채택의 실제 완료를 먼저 기다린다.

## 충돌·재연결·실패

네트워크 스레드는 Qt 소유자에게 요청을 큐로 전달한다. Qt 스레드가 현재 handle·편집 중인 초안·busy/modal 상태를 확인하고 기존 세션 잠금 안에서 검증과 명령을 연속 실행한다. 미확정 입력을 원격 요청 때문에 자동 적용하거나 폐기하지 않는다. `draft_pending`, `owner_busy`, `document_conflict`, `revision_conflict`에는 파일/문서 변경이 없다. 오류 후 현재 상태를 다시 읽고 사용자가 GUI 초안을 완료하거나 폐기한다.

CLI의 `--params`는 위 매개변수를 담은 JSON 객체다. `--request-id UUID` 또는 `LiveClient.request(..., request_id=UUID)`로 같은 요청을 재조회할 수 있다. 서버는 최근 최대 512개 요청/32MiB 응답에 대해 같은 ID·같은 매개변수의 결과를 재사용하고, 같은 ID로 다른 작업을 보내면 거부한다. 이 보장은 해당 서버와 캐시 수명 안에서만 유효하다. 영구 transaction log가 아니다.

Qt가 30초 안에 요청 실행을 시작하지 못하면 큐 요청을 취소하며 나중에도 적용하지 않는다. 이미 실행을 시작한 저장 등은 중간 중단하지 않는다. 클라이언트 timeout/연결 단절은 명령 실패의 증거가 아니므로 같은 요청 ID로 결과를 조회하거나 현재 문서/저장 결과를 확인한다. 새 ID로 곧바로 같은 변경을 반복하지 않는다. 요청은 1MiB, 응답은 16MiB 제한이며 대용량 전체 모델 스트리밍 계약은 별도다.

## 확인 범위

`tests/test_live_transport.py`는 실제 TCP/독립 subprocess로 인증·프레임·동시 중복 요청·재연결·descriptor 수명·제한을 검사한다. `tests/test_live_gui.py`는 열린 MainWindow에 별도 **공개 CLI 프로세스**를 연결해 값→화면→Undo/Redo→저장→재열기, 이벤트, 초안/개정/epoch 충돌, 실제 Gmsh 취소/PID 회수와 후보 성공을 확인한다. `CAELAB_LIVE_CAPTURE_DIR`를 지정한 X11 실행에서는 화면과 credential을 제거한 요청 기록도 보존한다. 이 연결 확인이 Windows GUI, 상용 제품 비교, MCP 클라이언트 연결의 합격을 대신하지 않는다.
