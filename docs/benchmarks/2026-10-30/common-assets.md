# 벤치마크에서 공용 자산으로 옮길 명세

참조 장면 ID는 동명의 `products/*.json`에 있다. 아래 요구는 우리 프로그램의 설계 선택이며 원 제품의 모든 동작이 이렇다는 뜻은 아니다. UI/메셔 구현은 아직 하지 않았다.

| 자산 | 연결할 참조 장면 | 구현할 공통 책임과 상태 |
|---|---|---|
| Action/메뉴/검색 | ABAQUS AB01·AB05, HyperMesh HM20·HM24, Naksha NA01 | 같은 명령의 메뉴/툴바/단축키를 공유. 문서·선택·busy capability로 활성화. 미구현 동작은 mock 성공 금지 |
| 모델 트리/열 | HM03·HM04, COM-T02, NFX workspace, MeshFree trees | 이름·종류·가시성·필요한 native ID 열. 긴 이름·한글·혼합값·여러 선택. 원형/배치/component/source는 의미를 구분 |
| 조건 정의/케이스 | NFX case/drag, MeshFree trees/case, AB14·AB17 | 조건 객체와 케이스별 사용을 분리. Abaqus Step을 다른 제품의 독립 load case와 동일 타입으로 강제하지 않음 |
| 선택 도구 | AB07, HM05·HM07·HM25, COM-T03, BE03 | entity 종류·범위·추가/제거·preview와 확정 선택을 분리. 필터 변경·취소·숨김/표시·선택 개수를 일관되게 전달 |
| 속성/수치/단위 | AB06·AB28·AB29, HM04·HM23, COM-T02·T09a, BE05 | 표시값·단위·draft·확정값을 분리. 잘못된 입력은 draft 보존, 명시 Apply/취소. provider가 단위/필드 의미를 제공 |
| 참조 선택 | HM15, COM-T03, BE05 | 미해결 참조·필수/선택적 참조·삭제 영향 표시. 잘못된 ID를 0/default로 조용히 치환하지 않음 |
| 표/곡선 | AB27, HM21·HM22, COM-T09b/c, NFX plastic, NA09 | 행열과 plot의 같은 값, 단위/축/선택 연결. 붙여넣기 preview와 전체 유효성, 한 작업 한 Undo. CSV는 작업 문서와 분리 |
| mesh recipe/후보 | AB09–12·AB19, HM06–08, COM-T04, NFX mesh | 대상·크기·알고리즘·차수·국부 override를 저장. 생성 후보와 문서 채택을 분리. 기존 엔진의 실제 지원 recipe만 노출 |
| 품질/문제집합 | AB18·AB21, HM11–15, COM-T06a, NFX quality | family별 metric·threshold·대상 집합과 위치 강조. 표시 threshold와 영구 criterion 설정을 구분. 실제 수리 전후 검증/rollback은 별도 명령 |
| 저장/내보내기 | AB23·AB24, HM16–18, COM-T07, NFX save, MeshFree save | 작업 원본과 solver 출력을 구분. dirty·경로·취소·실패·재열기·값/참조 보존. 원문/미지원 카드 보존은 기존 계약 유지 |
| 진행/중지/취소 | AB22, COM-T06b·T08b, NFX run, MeshFree cancel | 실행 전/진행/성공/실패/취소를 구분. Stop과 Cancel은 backend가 지원하는 의미대로 capability를 제공. Workbench 시작 job은 기존 manager 소유 |
| 자동화 연결 | HM20, AB26, BE08, NA08 | GUI와 같은 command/query/job 경로. 읽기/변경·파일 범위와 action log를 표시. 정적 MCP 소개를 실제 client 연결 증거로 사용하지 않음 |

## 외관을 재현할 때 필요한 값

장면별 원본 해상도·영역 비율·행/툴바 높이·들여쓰기·아이콘/라벨 정렬·선택색·그룹 간격·스크롤/도킹·글꼴/배율 정보를 따로 적는다. 화면에 없는 font family/point size/resize 규칙은 미확인으로 남긴다. [화면 관측](layout-observations.md)의 픽셀 값은 해당 이미지의 관측값이며 그대로 Qt logical pixel 토큰으로 채택하지 않는다.

P0에서 고정할 두 목표 조합 화면은 이 자료의 여러 장면을 근거로 작성한다. 두 장면만 조사했다는 뜻이 아니다. dense 기계 전처리와 재료/곡선의 실제 값을 채우고, 정상/선택/포커스/비활성/오류/긴 이름/좁은 창을 포함한다. Windows 100/150/200%에서 검증할 실제 디자인 토큰은 아직 최종 확정하지 않았다.

## 그대로 가져오지 않을 동작

원 제품이 CSV의 잘못된 행을 건너뛰는 경우에도 우리 입력은 누락을 먼저 알리고 사용자가 정한 처리만 수행한다. 원 제품의 제한된 Undo/취소/단위 범위를 공통 계약의 전역 보장으로 일반화하지 않는다. 화면의 경고 문구·아이콘·브랜드를 복제하는 방식 대신 같은 사용자 문제를 자체 표현과 코드로 해결한다.

## 개발 착수 시 필요한 작은 추가 확인

공통 계약·기본 위젯/문서 개발에 신규 메셔 커널 논문 조사는 필요하지 않다. 선택한 장면에서 실제 필수 상태가 없으면 그 상태만 확인하거나 자체 정책을 명시한다. CAD/메시의 local sizing·conformal·sweep 등은 [메셔 로드맵](../../mesher-feasibility-roadmap.md)의 실제 재현을 따르며 GUI 그림으로 지원을 확정하지 않는다. Workbench의 위젯 소비·외부 Prep 실행·RAD 계산은 [별도 계약](../../workbench-reuse-plan.md)을 유지한다.
