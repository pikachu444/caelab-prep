# 열린 Prep GUI의 MCP 연결

이 어댑터는 [live control](live-control.md)의 인증된 연결을 사용하는 **stdio MCP 서버**다. 자체 `PrepSession`, Qt 창 또는 메시 실행기를 만들지 않는다. 요청은 이미 열린 창의 같은 제공자·문서 잠금·명령·작업에 전달된다. 지원 범위는 문서 조회/선택, 제공자가 허용하는 숫자/boolean 값 변경, Undo/Redo, 작업문서 저장, 이벤트, CAD 메시 후보 작업의 시작·조회·생성자 취소다. 모든 모델링 명령이나 Workbench 솔버 실행 API를 뜻하지 않는다.

목표 클라이언트는 공개 배포된 [FastMCP client CLI](https://gofastmcp.com/cli/client)의 `list`/`call` 명령이다. 설치된 클라이언트가 stdio MCP 서버를 실제로 시작하고 요청하며, 자체 테스트용 SDK client를 작성한 경로가 아니다. 이는 MCP 클라이언트 연결이며 자연어 LLM 실행의 검증이 아니다. 로컬 stdio 연결에는 LLM API 키나 OAuth가 필요하지 않다. 다른 데스크톱/웹 MCP host 및 Windows GUI는 각각 별도로 확인한다.

## 설치와 연결

Prep 환경에 선택 의존성을 설치한다. MCP 서버 프로세스는 GUI 의존성을 가져오지 않으며 GUI가 실행되는 환경과 달라도 된다.

```sh
python -m pip install '.[mcp]'
caelab-prep gui model_0000.rad --ipc /absolute/private/prep-connection.json
```

GUI의 **Automation → Start live control…**도 같은 연결을 만든다. 연결 파일은 인증 정보이므로 공유하거나 저장소에 추가하지 않는다. 서버는 이미 존재하는 파일을 덮어쓰지 않는다. `--no-3d`로 연 Qt 편집기에도 연결할 수 있지만 이 모드는 3D 확인이 아니다.

다음 MCP 설정의 실행파일과 연결 경로를 실제 값으로 바꾼다. 소스 checkout을 사용하면 `PYTHONPATH`에 그 checkout의 절대 `src` 경로를 명시한다. 설치된 wheel이면 `env`가 필요 없다.

```json
{
  "mcpServers": {
    "prep": {
      "command": "/absolute/python",
      "args": ["-m", "caelab_prep", "mcp", "--connection", "/absolute/private/prep-connection.json"],
      "env": {"PYTHONPATH": "/absolute/caelab-prep/src"}
    }
  }
}
```

별도 클라이언트 환경에 FastMCP를 설치하고 실제 명령을 실행한다. 각 호출은 stdio 어댑터를 새로 시작하지만 연결 대상은 계속 **같은 열린 GUI 소유자**다.

```sh
python -m venv /absolute/mcp-client
/absolute/mcp-client/bin/python -m pip install fastmcp==3.4.11
/absolute/mcp-client/bin/fastmcp list /absolute/mcp.json --json
/absolute/mcp-client/bin/fastmcp call /absolute/mcp.json prep_describe --input-json '{}' --json
/absolute/mcp-client/bin/fastmcp call /absolute/mcp.json prep_cards --input-json '{}' --json
```

클라이언트 호출이 끝나도 GUI 문서나 실행 중인 GUI 소유 작업을 대신 닫지 않는다. GUI에서 live control을 중지하면 실제 생성 worker의 종료 또는 원자 채택 완료를 기다린다. 기존 서버가 중지된 뒤 새 GUI 서버가 만들어지면 설정에 새 연결 파일을 지정한다. 연결 실패 시 문서 사본으로 대체하지 않는다.

## 도구와 실패 의미

`list --json`은 각 도구의 입력 schema와 도움말을 제공한다. 먼저 `prep_describe`로 `document_id`, `document_epoch`, `revision`이 든 **handle 전체**를 얻고, `prep_cards`의 typed target과 `prep_properties`의 현재 값·허용 단위를 사용한다. native 숫자 ID를 UUID 대신 넣거나 오류 뒤 개정 번호를 추측하지 않는다.

| 도구 | 같은 열린 GUI에서 하는 일 |
|---|---|
| `prep_describe`, `prep_cards`, `prep_properties`, `prep_selection` | 실제 문서/초안/busy/지원 범위와 객체·값·정규 선택 조회 |
| `prep_select`, `prep_edit_scalar` | 실제 선택·속성 패널 반영, 같은 scalar 명령과 한 Undo |
| `prep_undo`, `prep_redo`, `prep_save` | 현재 handle로 공용 이력 실행 또는 명시 경로에 `.caeprep` 저장 |
| `prep_events` | 후속 세션/작업 이벤트. 만료된 cursor는 명시 오류 |
| `prep_mesh_start` | 실제 후보 GUI·Gmsh worker 시작. 후보를 문서에 자동 채택하지 않음 |
| `prep_job_get`, `prep_job_cancel`, `prep_job_close` | 실제 workflow 세대/상태/결과 조회, 생성자 capability로 취소/종료 |

숫자 편집 예시는 `prep_edit_scalar`에 `handle`, `target`, `values: {"young_modulus": 205000}`, `units: {"young_modulus": "MPa"}`를 함께 보내는 것이다. 이 값·단위는 예시이며 실제 제공자 허용값을 먼저 확인한다. 미적용 GUI 초안·busy/modal·stale document/epoch/revision은 변경 없이 실패한다. 도메인 오류는 MCP `isError=true`와 구조화된 `error.code/message/details`로 반환한다. 오류 문자열을 성공 결과로 취급하지 않는다.

변경 도구의 선택적 `request_id`는 UUID다. 전송 중 연결이 끊기면 같은 ID·같은 인자로 결과를 조회할 수 있으며, 보장 범위는 [live control의 한정된 replay cache](live-control.md#충돌재연결실패)와 동일하다. 클라이언트 timeout은 이미 시작된 저장의 취소를 뜻하지 않는다.

`prep_mesh_start`만 해당 workflow의 `cancel_token`을 반환한다. 이 capability를 가진 생성자가 취소하며 `prep_job_get`으로 다른 클라이언트의 취소 권한을 얻을 수 없다. `cancel_requested`를 완료로 세지 않고 실제 `cancelled`와 worker 종료를 확인한다. 같은 창의 GUI Generate/Open/Adopt도 `generation`과 상태에 반영된다. `operation=adopt`는 원자 변경이므로 취소 불가이며 실제 완료를 기다린다.

## 의존성과 확인 범위

서버는 [공식 Python MCP SDK](https://py.sdk.modelcontextprotocol.io/) 2.x API를 사용하고 선택 의존성은 `mcp>=2.3,<3`이다. SDK/도구 등록만으로 실제 클라이언트 완료를 판정하지 않는다. 재현 검사 `tests/test_mcp_client.py`는 명시한 외부 클라이언트 실행파일과 MCP Python 환경으로 실제 GUI→MCP stdio→live socket→Qt owner를 연결한다. `CAELAB_FASTMCP`와 `CAELAB_MCP_PYTHON`으로 실제 실행파일을 지정한다. 클라이언트 상태와 인증 정보는 임시 비공개 경로에 두고, 보존하는 요청 기록에서는 인증/cancel capability를 제거한다.

2026-11-02 Linux X11에서 **FastMCP client 3.4.11 / 별도 Python MCP server SDK 2.3.0**으로 이 검사 3개가 통과했다. 실제 공개 CLI 호출 35개로 schema·typed 값 조회, GUI 선택/값 표시, 같은 요청 ID 재시도, Undo/Redo, `.caeprep` 저장과 별도 세션 재열기, 이벤트, 연결 종료 후 오류를 확인했다. `1e` 초안 보존·저장 차단, stale 개정/epoch 거절, 실제 Gmsh 생성자의 취소 권한·PID 종료, 후속 후보 성공과 원자산 존재도 확인했다. 후보는 81 nodes/184 tetra4 elements이며 이 확인에서 문서에 자동 채택하지 않았다.

보존 근거는 [민감값을 제거한 실제 클라이언트 요청/응답](automation/2026-11-02/fastmcp-requests.jsonl), [열린 GUI 값 반영](automation/2026-11-02/mcp-edited-open-owner.png), [미확정 초안 보존](automation/2026-11-02/mcp-preserved-invalid-draft.png), [실제 메시 후보 창](automation/2026-11-02/mcp-real-mesh-candidate.png)이다. 캡처는 실제 X11의 Qt 창이며 **3D viewer는 비활성**이었다. 상용 프로그램 UI 품질, 3D 렌더, 자연어 에이전트, Windows 또는 다른 MCP host의 합격으로 확대하지 않는다.

종료 정리에는 [미해결 관찰 기록](automation/2026-11-02/cleanup-observations.json)이 남아 있다. 첫 실행 이후 비활성 연결 파일 두 개가 관찰됐지만 해당 endpoint는 닫혀 있었고 파일 권한은 `0600`이었다. 같은 과업을 다시 실행하고 읽기 오류·소유 ID·삭제 직후를 관찰했을 때는 파일이 없어졌으며, 강화한 종료 검사도 통과했다. 이후 별도 실행의 파일 조회에서 삭제했던 비활성 파일이 다시 나타난 관찰도 있어 원인을 확인하지 못했다. **제품 수정으로 해결했다고 보고하지 않는다.** 공개 근거에는 인증 파일을 포함하지 않는다. 최종 검사는 제한 시간 안의 `closed` 상태, worker 없음, 연결 파일 부재, 최종 Stop 응답을 함께 요구하며 같은 조건을 CI에서 재확인한다. 닫힌 endpoint의 과거 토큰으로 활성 문서를 제어할 수 있다는 근거는 없고 새 소유자는 새 토큰을 만든다.

CI에서도 실제 클라이언트와 서버 환경을 나눠 선택 실행할 수 있다. 아래 실행 Python에는 Qt·Gmsh 및 테스트 입력 생성용 OCP가 준비돼 있어야 하며 X11이 필요하다. 미설치 상태의 skip을 클라이언트 성공으로 세지 않는다.

```sh
python -m venv /absolute/mcp-server
/absolute/mcp-server/bin/python -m pip install mcp==2.3.0
python -m venv /absolute/mcp-client
/absolute/mcp-client/bin/python -m pip install fastmcp==3.4.11
CAELAB_FASTMCP=/absolute/mcp-client/bin/fastmcp \
CAELAB_MCP_PYTHON=/absolute/mcp-server/bin/python \
CAELAB_MCP_CAPTURE_DIR=/absolute/evidence \
PYTHONPATH=src xvfb-run -a python -m pytest -q tests/test_mcp_client.py
```

다른 후보 [Apify mcpc](https://github.com/apify/mcpc) 0.7.0도 설치해 연결을 시도했다. 2026-11-02 이 실행 환경에서 클라이언트 bridge의 Unix socket 생성이 `EPERM`으로 거부돼 **MCP handshake 전에 실패**했다. 독립 AF_UNIX probe도 같은 오류였고 loopback TCP는 동작했다. mcpc를 수정하거나 이 시도를 연결 성공으로 세지 않았다. `CAELAB_MCPC`를 명시하는 별도 선택 경로는 정상 Unix socket 환경에서 같은 과업을 재현하기 위한 검사이며, 여기서의 mcpc 성공 근거는 없다.
