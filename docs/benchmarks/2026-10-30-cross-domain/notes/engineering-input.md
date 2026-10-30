# 공학 수치·표·곡선·단위 입력 조사

2026-10-30. 고정한 필수 6묶음에 대해 Qt, LibreOffice Calc, LabPlot, Pint, pyqtgraph의 공식 문서·예제·소스를 비교했다. **문서 URL 22개, 정적 화면 9개, 기능 근거 묶음 11개**다. 실제 앱 실행·영상 연속 관찰은 없으며, 6묶음의 전체 사용자 작업 준비도는 모두 부분 상태다. 제품 구현·의존성 설치·DB/자료관리 설계는 하지 않았다.

상세한 주장과 근거는 [engineering-input.json](../domains/engineering-input.json)의 전역 고유 ID로 연결했다. 아래 표는 찾아볼 위치이며 같은 근거를 새 자료로 중복 집계하지 않는다.

| 필요 기능 | 근거 묶음 | 실제 확보한 자료 | 남은 확인 |
|---|---|---|---|
| 수치 draft·locale·확정·IME | P01–P02 | Qt validator/line edit 예제, IME API, 숫자 파싱 | Windows 한글 조합, 선택 변경·삭제 때 미확정 입력 |
| 단위·차원·배열·오프셋 | P03–P04 | Pint 0.25.2의 고정 예제와 API | solver 필드 의미·좌표계·DOF와 GUI/저장 연결 |
| CSV/붙여넣기 미리보기·오류 | P05–P06·P08 | Calc의 옵션/오류 정책, LabPlot import 화면과 실제 paste 코드 | invalid 셀·누락·비유한값의 종단 처리 |
| 다중 셀 적용·Undo·부분 실패 | P07–P08 | LabPlot의 macro 사용 위치, Qt Undo API | 검증 전 전체 준비, 실패 rollback·문서 참조 복구 |
| X/Y 열·표/곡선·축/단위 | P09–P10 | LabPlot 사용자 흐름/API, pyqtgraph 0.14.0 표시 API | 행/point 양방향 선택, 재료 곡선 규칙·재열기 |
| 대형 표·mixed 값·키보드 | P11·P02 | Qt 증분 모델 예제와 소유 스레드, LabPlot 키 문서 | 이종 객체 mixed 속성, 대용량 편집·메모리 성능 |

P 번호는 모두 `engineering-input-Pnn`의 약칭이다. 사용자 설명, API 계약, 코드에서 읽은 사실과 CAE에 적용할 때의 판단을 JSON에서 구분했다. 특히 P07의 Undo 단위와 P08의 빈칸/숫자 해석은 오류 원자성의 증거로 사용하면 안 된다. 해당 주장에 대한 구체 근거·이식 제한은 각 묶음의 `documented_result`, `failure_cancel_undo_save`, `non_transferable`, `inferences`에 있다.

## 서로 다른 버전을 합치지 않는 규칙

- Qt 문서는 조회 시 6.12.0이며 우리 앱에서 채택/실행한 버전이라는 뜻은 아니다. 예제 이미지 S01/S02의 실제 캡처 Qt/app build는 원문에 표시되지 않았다.
- Calc 최신 도움말은 26.8, 상세 대화상자 그림은 7.1 Community 가이드다. 같은 실행 화면으로 합치지 않는다.
- LabPlot 문서는 2.12 표기다. 화면의 실제 앱 build는 명시되지 않았다. 소스 조사는 별도로 `f9fcda1a11f4cdae07d8e2202f3f2d55cccd8ff6`에 고정했으며, 읽은 master 파일과 pinned 파일의 바이트 일치를 확인했다. 이 소스를 2.12 출시판의 코드라고 보고하지 않는다.
- LabPlot quick start와 KDE trunk_kf6의 수동 그래프 생성 예제는 서로 다른 흐름이다.
- Pint는 0.25.2, pyqtgraph는 0.14.0의 고정 문서다. 검색에서 나온 최신 dev 문서의 옵션을 끼워 넣지 않았다.

## 화면의 범위

9개 이미지는 모두 실제 내려받아 원본 크기로 확인했다. Qt 입력 예제·증분 목록 2개, LabPlot import/preview/X-Y 대상 선택/worksheet 4개, Calc 검증 criteria/error alert/paste special 3개다. 원본 URL·크기·해시·실제로 보이는 내용을 JSON의 assets에 남겼다. font family, DPI, hover/focus/disabled 전 상태, resize 규칙을 그림에서 추정하지 않았다. 화면은 연구 참조이며 제품 아이콘·테마 자산이 아니다.

Calc 7.1 가이드에는 문서·이미지의 CC BY 4.0 또는 GPLv3 이상 조건과 제작 팀 표시가 있다(D09). Qt 문서의 GFDL 고지 및 기타 이미지의 개별 조건은 채택 대상별로 확인해야 한다. 이번 조사에서 vendor 프로그램·매뉴얼 전문은 배포 산출물에 넣지 않는다.

## 이번 조사 종료와 후속 경계

필수 6묶음마다 근거, 적용할 수 있는 책임, 의미가 달라지는 부분, 미확인 상태를 채웠다. 자동 형 변환·invalid 허용·빈칸·macro·표시 최적화의 반례와 대안을 검색했으며 검색 경로/접근 실패도 JSON에 기록했다. 이 한정 조사는 종료할 수 있다. 실제 CAE 수치 입력·저장·Undo·대용량 사용자 작업이 구현 준비 또는 검증 완료라는 판정은 하지 않는다.

문서 담당과 연결할 항목은 **여러 셀의 한 번 적용 ↔ 문서 transaction**이다. 선택 담당과 연결할 항목은 **여러 객체 mixed 값·선택 대상 삭제 ↔ 속성 draft**다. 셸 담당과 연결할 항목은 **IME·Enter/Apply·전역 Undo/단축키 ↔ 편집기 포커스**다. 이들 정책은 이번 문서 수집으로 자동 결정하지 않는다.
