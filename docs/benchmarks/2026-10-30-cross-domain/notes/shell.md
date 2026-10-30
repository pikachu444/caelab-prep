# 셸·명령·도킹·아이콘 조사

조사일: 2026-10-30. **23개 공식 원문 URL, 11개 실제 보유·시각 확인 화면, 12개 기능 근거 묶음**이다. 화면 수는 제품 수/독립 원문 수가 아니다. 모든 근거는 D/S이며 실제 앱 재현은 하지 않았다. DB·검색 구조나 GUI 구현은 이번 범위가 아니다.

## 찾은 방향

공용 셸은 창 배치만 제공해서는 부족하다. 제품의 사용자 경로와 이를 지탱하는 구현 계약을 연결해야 한다. 여기서는 Qt Creator·Qt Widgets Designer·VS Code 사용자 문서, KDE HIG와 Qt6 공식 API/실제 PySide 예제를 비교했다. `shell.json`의 source/pattern ID에서 각 원문 절과 실제 이미지를 찾을 수 있다.

| 필요한 책임 | 근거 묶음 | 이번 확인과 남은 공백 |
|---|---|---|
| 명령 표면 공유·context dispatch | shell-P01–03 | 단순 QAction과 QtCreator Command의 차이를 확인. CAE busy/선택 삭제 정책은 별도 |
| dock·tab·닫힌 view 복원 | shell-P04–05 | 제품별 reset/reopen 경로와 Qt state 버전 실패 확인. monitor 제거 복원은 미재현 |
| property/tree와 편집 adapter | shell-P06–07 | 타입별 editor·수정값 표시·모델/선택 분리 근거. mixed/error partial apply는 공백 |
| 아이콘 문법·상태·해상도 | shell-P08–09 | HIG의 의미/정렬과 QIcon의 표시 API를 분리. 자체 FEA 기호/라이브러리는 미선정 |
| focus·IME·접근성 | shell-P10–12 | 키보드 사용 경로와 custom-control 계약 확보. 한글/스크린리더 실증 미수행 |

## 서로 다른 정책을 합치면 생기는 오류

- Qt Creator는 같은 context에서 단축키가 충돌하면 실행하지 않는다. VS Code는 키 규칙의 첫 매칭 우선순위를 사용한다. 하나의 공통 정책으로 묘사하지 않는다 (`shell-D06/07`).
- VS Code의 명령 enablement와 메뉴 노출 when은 역할이 다르다. QtCreator의 context command API도 일반 QtGui QAction API가 아니다 (`shell-D03/05`).
- 레이아웃 저장은 CAE 문서/선택/draft/job 재개와 별도다. Qt의 state 이름/버전 복원 규칙은 이 구분을 구현할 기술 근거다 (`shell-D11`).
- 모델을 공유하는 것과 선택 모델을 공유하는 것은 다르며, delegate가 FE 변경 transaction을 제공하지 않는다 (`shell-D14/15`).
- IME preedit는 확정된 문서 수정이 아니다. Qt의 이 규칙은 Undo/Redo를 구현한 위젯이라는 전제이며 custom editor에 Undo가 자동 제공된다는 뜻이 아니다. 조합 중 문자열을 매번 FE Undo로 보내는 구현은 해당 입력 규칙과 맞지 않는다 (`shell-D19`).

## 외관 자료의 실제 한계

`designer-properties.png`, `designer-objects.png`는 현재 Qt6 문서에 있지만 오래된 창 장식이다. 2026 상용 외관/DPI 토큰의 기준으로 쓰면 안 된다. 화면은 Property/Value 열, 접는 그룹, 타입별 editor 및 객체 트리 계층의 **구조 근거**다. Creator 화면도 캡처 앱 빌드는 확인되지 않는다.

VS Code의 panel/split 메뉴는 비활성 항목·separator·단축키 정렬·선택 행을 실제로 볼 수 있다. density 그림은 Default/Compact 선택지만 보여 주며 Compact 적용 후 치수는 보여 주지 않는다. `qt-dprgadget.png`는 단일 진단 화면으로 mixed monitor 동작의 증거가 아니다. 모든 이미지의 파일 치수는 물리 캡처 픽셀이며 Qt logical pixel 값으로 직접 바꾸지 않는다.

## 이식할 책임과 다음 구현 단계의 질문

아이콘은 단지 SVG를 로드하는 기능이 아니다. 의미가 겹치지 않는 기호, 크기별 정렬/여백, disabled/active/selected 표시와 설명 text가 함께 필요하다. KDE의 테마 전제나 VS Code의 규격 숫자를 그대로 프로젝트 전체 규칙으로 확정하지 않았다 (`shell-D16/22/23`).

반드시 남겨야 할 질문은 선택 대상 삭제 중 속성 draft, 다중 선택 validation의 원자성, job 중 target 변경과 명령 상태, IME 확정 Enter와 Apply의 중복 처리, 3D viewport의 DPR/pick 및 custom accessibility다. 공식 문서에 답이 없는 부분을 제품의 동작으로 꾸미지 않고 `coverage`를 partial로 남겼다. 이번 자료 수집 작업은 이 공백까지 기록한 상태에서 닫을 수 있지만 실제 개발 준비·상용 동등성 완료를 뜻하지 않는다.

## 구현자가 먼저 읽을 원문

1. [공식 PySide6 Dock Widgets 예제](https://doc.qt.io/qtforpython-6/examples/example_widgets_mainwindows_dockwidgets.html): 실제 `create_actions`, `create_menus`, `create_tool_bars`, `create_dock_windows`를 확인했다. 샘플의 편지 편집 Undo는 CAE Undo가 아니다.
2. [Qt Creator command/context 설명](https://doc.qt.io/qtcreator-extending/actionmanager.html): public UI action과 내부 handler action의 경계를 확인한다.
3. [Qt MainWindow state 계약](https://doc.qt.io/qt-6/qmainwindow.html#saveState): layout identity/version과 geometry를 구분한다.
4. [Qt input method 계약](https://doc.qt.io/qt-6/qinputmethodevent.html#details): custom editor의 commit/preedit/Undo를 구분한다.
5. [KDE 아이콘 지침](https://develop.kde.org/hig/icons/): 의미·label·context를 API 렌더링과 함께 검토한다.

원문 전문은 `tmp/shell/`에만 있으며 배포 대상이 아니다. 사용자 화면/아이콘 발췌도 개발 참고 자료이며 제품 리소스로 편입하지 않는다.
