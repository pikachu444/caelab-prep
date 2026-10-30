# 수집 후 토론·통합 결론

2026-10-30. root + 담당자5명 + 독립 Astra1명, 총7명으로 수행했다. 수집 전 `protocol.md`에서 질문·판본·목록 분모·독해 깊이·권리·종료 조건을 합의한 뒤 담당을 나눴다. root는 BDF 두 계열과 통합, 담당자는 RAD/DYNA/Abaqus/CalculiX/Code_Aster를 맡았다. Astra는 작성자가 아닌 입장에서 실물·집계·주장을 검토했다.

## 보고서 교환을 넘어서 대조한 내용

| 참가 범위 | 실제 대조 쟁점 | 결론과 반영 위치 |
|---|---|---|
| RAD↔DYNA | blank/zero/default, fixed/free/long, C3D4 변환 순서, typed ID offset, small restart, cfg/QA 권리 | converter·reader·schema·writer를 나누고 값/ID/순서/상태와 문서·source·예제 판본을 보존. `dyna-rad-review.md` |
| Abaqus↔CalculiX | OUTPUT FIELD/HISTORY 호환 범위, STATIC EXPLICIT의 CFD 문맥, DYNAMIC 인자 생략, assembly namespace | 같은 `.inp`/keyword를 지원/기본값의 동일성으로 해석하지 않음. 양쪽 notes와 원장 |
| Code_Aster↔Abaqus/DYNA/root | .comm/.export/MED bundle, Python variable/concept/group 이름, Cata helper/command/document 분모, v17 restart | single deck/global ID로 평탄화하지 않음. Cata/serializer/runtime 역할 분리. `notes/aster.md` |
| root↔Astra/담당자 | CTETRA PID 필수/default, INCLUDE 정책, 최적화 RESTART, reader whitelist | solver/version profile에서 실제 조건을 소유. `bdf-cross-review.md`, BDF 원장 |
| 작성자↔독립 Astra | 원본·hash·목록 분모·locator·권리·독해/실행 과장 | 지적별 수정 확인은 `astra-findings.md`. 통합 구조/해시 확인은 `validation.json` |

## 당초 판단에서 수정한 부분

기존 RAD 편집 코드의 일부 Field 메타데이터와 회귀 입력을 생성용 전수 규격·시험자료의 대체로 본 판단은 잘못이다. 기존 파일 patch 기능과 새로운 모델/카드 생성은 다르다. README·DESIGN·AGENTS에 실제 현재 범위와 이번 자료의 진입점을 반영했다.

공식 목록은 임의 대표 카드로 줄이지 않고 전체 추출했다. 서로 다른 분모가 발견되면 원문을 유지했다. DYNA는 family/option·alias·중복과 schema 이름 불일치, Code_Aster는 command/helper/document, Nastran은 북마크/설정/옵션/entry를 분리했다. 단순 합계로 ‘모든 keyword 수’를 만들지 않았다.

원본을 실제 취득했지만 상용 manual/권리 불명 예제를 그대로 공개하지 않는다. OpenCourant의 cfg/QA/Tools도 root license 하나로 취급하지 않는다. 허용된 source/schema/example은 개별 고지와 원문 URL·commit·해시를 포함한 참고 묶음에 보존한다.

## 개발에서 사용할 방법

공용 기반은 identity/reference graph, 단위, 명령·Undo, 선택, 배열과 파일 bundle, 값의 생략/0/default/상속 상태를 보존한다. 솔버별 profile은 native 구문·namespace·field 조건·기본값·연결순서·활성 참조·파일 탐색과 해석 제약을 소유한다. UI가 internal schema를 그대로 나열하는 것으로 끝나지 않게 기존 GUI 벤치마크의 작업·밀도·상태 근거와 함께 사용한다.

첫 적용은 OpenRadioss/OpenCourant로 유지한다. 다른6계열 자료 확보는 현재 제품이 그 솔버를 지원한다는 선언이 아니다. Workbench는 이 저장소가 실제 제공·검증한 API/자산/native file bundle을 소비하고 기존 프로젝트·실행 관리 책임을 유지한다. 수집한 모든 framework/source를 의존성으로 추가하지 않는다.

## 이번 작업의 종료와 남은 부분

이번 종료 대상은 고정 범위의 전체 목록/대조, Q01–Q12의 근거·부분·공백, 실제 예제/코드 역할, 판본·취득·권리·해시와 독립 지적의 수정이다. 이것이 통과하면 자료 수집은 닫는다. 대표 그림/몇 개 카드만 찾은 상태와는 구분한다.

전수 field/conditional/dependency schema, 모든 옵션의 의미 검토, native writer의 실제 이식, 정상·오류·경계 deck 생성과 solver read/run은 미완료다. MSC2024.2 고유 complete deck은 미확보이며 NASA95 예제는 보조 자료다. 일부 권리·접근 제한은 원장에 남긴다. 다음 개발은 기존 단계의 선언된 기능/solver/version 범위에서 필요한 명세와 시험을 구체화하며, 이번 문헌 조사로 기능 완료를 선언하지 않는다.
