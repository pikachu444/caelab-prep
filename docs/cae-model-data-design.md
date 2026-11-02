# 다중 파트·자유도·대용량 데이터 설계

상태: 2026-10-29 원설계와 완료 조건을 보존한다. 2026-11-02 `feat/model-relations`의 두 번째 검토 체크포인트에서 N16 관계와 N17 조회 변경을 아래 10절에 대조했다. **목표 모델 전체가 구현됐다는 뜻은 아니다.** 적용 범위는 [공용 기반 설계](shared-cae-foundation-plan.md)의 P1/P3과 P6/P7, 구체적인 순서·입력·검사 종료는 [단계별 작업서](execution-stages.md), 현재 코드는 [ARCHITECTURE](../ARCHITECTURE.md)에 구분한다.

## 1. 해결할 범위와 현재 제약

공용 기반은 여러 파트·인스턴스·메시·재료·조건과 서로 다른 활성 자유도를 한 문서 안에서 관리해야 한다. 이를 위해 데이터 소유권·참조·변경·저장 방식을 먼저 정한다. GUI에 파트 항목을 여러 개 추가하는 것만으로 이 요구가 해결됐다고 보지 않는다.

기준 병합 `a48d3b4`의 코어는 자원·명령·선택을 제공하고 RAD provider는 재료/단면·PART 할당, 곡선·집합·조건 생성, tri/tet 후보의 원자 채택과 참조 없는 소유 메시 교체를 지원한다. 다중 PART 선택과 조건 역할별 대상 강조도 연결돼 있었다. 이 기준 코드의 명령 이력은 한 자원 상태 단위였고, `PrepSession.mesh_view()`는 투영 cache가 있어도 반환 시 점/연결 목록을 복사하며 전역 native 절점 ID로 RAD 메시를 모은다. 중복을 진단하는 이 경로가 독립 모델·instance의 일반 namespace나 compact 배열 저장을 구현한 것은 아니다.

그 뒤 구현된 복합 명령과 읽기 전용 projection은 10절을 따른다. 현재 작업의 케이스 정의/배정은 [중앙 잔여 N01](../CURRENT_STATE.md#remaining-work), 이 설계의 혼합 관계/다중 자원은 N16, 규모·배열·codec은 N17, 일반 메시 변경/재연결은 N18로 관리한다. 이미 있는 G1–G3 기능을 B 전체와 함께 다시 미구현으로 세지 않으며, B1–B6는 납품 개수가 아니라 아래 유한 범위의 합격 조건이다.

이 문서는 모델 편집·저장·표시를 위한 설계다. 강성/질량 행렬 조립·방정식 번호·접촉 해법은 솔버가 소유한다. 큰 자유도를 처리하는 설계와 실제 솔버의 계산 능력을 구분한다.

## 2. 소유 구조

| 개념 | 소유할 자료와 관계 | 혼동하지 않을 것 |
|---|---|---|
| 문서/모델 | 자원 목록·관계·단위 문맥·작업 개정·해석 설정 참조 | 하나의 UI 트리나 하나의 입력 파일과 동일시하지 않음 |
| PartDefinition | 원형 CAD/메시·지역 좌표·명명된 영역의 참조 | 모든 솔버의 `/PART`와 같지 않음 |
| PartInstance / Assembly | 원형 참조·배치 변환·조립 계층·인스턴스별 할당 | 화면 Actor 복제를 독립 FE 모델로 간주하지 않음 |
| FE component | 요소 집합과 재료/단면·물성·솔버별 분류의 관계 | CAD 부품/파일 소유 구조와 일대일로 강제하지 않음 |
| MeshResource | 노드·요소·연결·요소 형식·원본 ID 매핑·메시 버전 | 파트마다 공유 절점을 복사하거나 좌표 일치만으로 병합하지 않음 |
| Material / Property | 재료·단면 정의와 참조. 여러 component에서 공유 가능 | 공유 정의 변경과 특정 instance 재할당을 같은 명령으로 취급하지 않음 |
| Region / Set / Surface | 객체/엔티티 참조, 집합 정의, 면 방향·측면, 명시적/형상 기반 범위 | 트리 선택이나 현재 VTK selection과 구분 |
| Condition / Connection | 대상 영역·자유도/필드·좌표계·값/곡선·적용 단계, 접촉 양쪽·coupling 관계 | 서로 다른 조건·단계·접촉을 단순한 고정 bool 배열에 합치지 않음 |
| AnalysisCase / Activation | 사용할 파트·조건·접촉·해석 설정의 참조와 케이스별 활성/override | 조건 정의 자체, 화면 숨김, 해석 적용 여부를 하나의 체크 상태로 합치지 않음 |
| Source / codec | 원본 파일·INCLUDE·형식 버전·native ID 규칙·원문 payload | INCLUDE 파일을 조립 부품으로 자동 해석하지 않음 |

Radioss `/PART`는 재료·property를 공유하는 동종 요소 그룹이다. 입력에서 가져올 때 FE component와 원문 관계로 유지한다. CAD 원형·배치 인스턴스가 실제로 존재하지 않으면 그것을 임의로 생성한 것으로 보고하지 않는다. 공용 모델의 관계와 솔버별 payload를 함께 보존하며 모든 물리를 하나의 고정 FE 클래스에 끼워 넣지 않는다.

공유 절점은 하나의 MeshResource 안의 같은 엔티티를 여러 component가 참조할 수 있다. 독립적인 두 메시의 같은 좌표/번호는 별도 엔티티다. 연결하려면 명시적인 병합·tie·coupling 등의 명령과 솔버별 규칙이 필요하다. 동일 원형의 여러 instance는 형상 자료를 공유할 수 있지만 native 출력에서는 솔버의 instance 지원 또는 실제 엔티티 전개/ID 매핑을 어댑터가 처리한다.

조건을 모델에 정의하는 것과 특정 케이스에 배정하는 것은 별도 명령이다. 화면에서 숨긴 부품은 기본적으로 저장·출력 대상에 남으며 해석 비활성화는 케이스의 명시적인 모델 변경이다. 트리 그룹 이동이 원본 파일이나 배열 소유자를 자동으로 바꾸지 않는다.

## 3. 참조와 좌표계

| 참조 | 구성과 역할 |
|---|---|
| 공용 객체 키 | 자원 ID + 객체 종류 + 영속 객체 키. 표시 이름·트리 행·파일 순서와 분리 |
| 배치 참조 | instance ID + 원형의 객체/영역 참조. 다른 배치의 같은 local ID를 구분 |
| native 참조 | solver/모델 namespace + 엔티티 종류 + 원본 ID + 출처. 공용 키와 별도 매핑 |
| 유효성 표식 | 문서 정체성 + 관련 자원/메시 버전. 오래된 pick·작업 결과·집합 갱신을 판정 |

일반 속성 변경은 객체 키를 바꾸지 않는다. 삭제한 키를 다른 객체에 재사용하지 않거나 generation으로 구분하고 Undo 복원은 원래 정체성을 회복한다. 파일의 문서 ID만으로 현재 실행 세션을 식별하지 않으며 세션 교체 epoch를 함께 사용해 이전 열기 작업의 결과를 거부한다. 버전은 유효성 판정 정보이고 객체 정체성 자체가 아니다.

native 번호의 유일성 범위는 각 reader/writer가 정의한다. RAD의 한 모델에서 INCLUDE 간 공유하는 전역 번호를 임의의 파일별 namespace로 바꾸지 않는다. 반대로 독립 모델·배치의 같은 번호를 하나로 합치지도 않는다. 실제 충돌은 진단하고 출력 ID를 새로 배정해야 할 때에는 대응표를 보존한다. 원본을 조용히 재번호화하지 않는다.

전역 좌표, instance 배치, 절점 변환 좌표, 요소/재료 방향을 구분한다. 하중/구속은 대상과 좌표계 참조를 보유한다. 화면상의 world 좌표로 한 번 변환한 값만 저장하지 않는다. 표시·선택·저장·native 출력이 같은 변환 정의를 사용한다.

## 4. 자유도·필드 모델

**모든 절점에 6자유도를 고정하지 않는다.** 활성 성분은 연결된 요소의 formulation, 해석 종류, 연결/기준점의 역할과 솔버 규칙으로 정한다.

| 자료 | 포함할 내용 |
|---|---|
| FieldDescriptor | 물리 필드, 성분 목록·사용자 이름, 단위 문맥, scalar/vector/tensor, 좌표계, node/element/face 등의 association, 미지수/매개변수/상태/결과 역할 |
| FormulationDescriptor | 엔티티/요소 종류와 필요한 필드·성분, 지원/미지원/미확인 상태 |
| DofSupport 조회 | 특정 절점/영역에서 적용 가능한 성분과 이유. 필요할 때 인덱스로 조회 |
| ConditionTarget | 영역 참조 + 필드/성분 + 좌표계 + 단계/시간 + 값/곡선 참조 |
| Solver mapping | 공용 의미와 native 자유도 번호·카드 필드 간 대응 및 변환 가능 여부 |

예를 들어 변위 성분만 필요한 연속체와 회전 성분을 사용하는 셸/보/기준점이 함께 있을 수 있다. 온도·압력 등의 scalar 필드도 표현할 수 있는 구조로 두되, 표현 가능하다는 사실을 해당 해석의 reader/editor/export/solver 지원으로 보고하지 않는다. 자유도를 UI 체크박스나 native 번호 1–6으로만 정의하지 않는다.

혼합 연결점은 요소별 요구의 합성과 연결 규칙을 제공자가 계산한다. 축대칭·특수 셸·고차/내부 자유도 등을 일반적인 3/6 성분 가정으로 확정하지 않는다. 공용층이 솔버의 내부 방정식 번호를 생성하거나 `절점 수 × 6`을 실제 계산 자유도로 표시하지 않는다. 알려진 편집 필드 규모와 솔버가 보고한 방정식 수는 이름을 구분한다.

기존 RAD 구속 flag는 native 문맥 그대로 보존한다. 미확인 조건을 불필요하다고 판단해 기본값으로 정규화하지 않는다. 새 편집은 제공자가 알고 있는 대상·성분을 검사하고, 범위 밖은 명확히 지원 상태를 반환한다. 중복·모순된 조건은 단계·좌표계·성분을 함께 비교하며, 이 검사가 모든 수치적 특이성이나 과구속 판정을 대신하지는 않는다.

수백만 절점마다 Python DOF 객체를 만들거나 전체 `절점×필드` 밀집 배열을 강제하지 않는다. formulation별 descriptor, 대상 집합과 성분 규칙, 필요한 값 배열/희소 할당으로 표현한다.

## 5. 관계·참조·재메시

재료/단면 할당, 파트–메시 연결, set/surface, 하중/구속, 접촉 두 영역, rigid/coupling과 곡선 참조는 자원 간 관계로 관리한다. 역참조 인덱스를 두어 삭제·변경의 영향 대상을 찾는다. 전체 모델을 매번 순회하거나 UI 트리를 참조 DB로 사용하지 않는다.

관계 상태는 유효·미해결·오래됨·지원 미확인으로 구분하고, 객체/필드/대상과 함께 사용자에게 설명한다. 아직 로드하지 않음·누락·삭제·비활성 상태도 같은 오류로 합치지 않는다. 객체 삭제 시 참조를 함께 바꾸는 명령 또는 변경 거부가 필요하며, 영향을 숨긴 채 일부만 삭제하지 않는다. 여러 자원 명령은 검증 후 원자적으로 적용하고 실패하면 이전 상태를 유지한다.

재메시/CAD 교체 시 새 자원 버전을 만든다. 이전 explicit node/element 집합은 같은 번호나 가까운 좌표만으로 새 메시로 전용하지 않는다. 형상 기반/명명 영역은 backend가 제공하는 실제 대응이 있을 때 재평가하며, 미해결 항목은 표시하고 재연결 명령으로 처리한다. 오래된 viewport pick·백그라운드 결과도 같은 버전 규칙으로 거부한다. 묶음 B에서는 준비된 교체 메시로 이 경계를 확인하고 일반 CAD 재메시 생성·형상 대응 복구는 P7의 후속 작업으로 둔다.

## 6. 대용량 자료와 저장

| 영역 | 설계 방안 | 완료 시 확인할 점 |
|---|---|---|
| 정본 배열 | 소유 자원이 compact typed 좌표·연결·offset·요소 종류·ID 배열을 소유 | 모든 노드/요소를 UI Python 객체로 복제하지 않음 |
| 조회/표시 | 읽기 전용 view 또는 버전 있는 projection handle, 필요한 backend 사본과 크기 제한 캐시 | 속성 한 개 수정/선택 때 전체 메시를 재복사·재생성하지 않음 |
| 인덱스 | 엔티티 키/native ID·파트/집합·역참조 인덱스 | 조회 때 선형 전체 스캔을 반복하지 않음 |
| 트리/표 | 필요한 계층/행을 지연 제공하는 모델/뷰 | 수백만 엔티티를 전부 QTreeWidgetItem으로 생성하지 않음 |
| Undo | 변경된 필드·연결·배열 구간과 자원 채택 전후를 기록 | 작은 변경마다 전체 메시 snapshot을 history에 쌓지 않음 |
| 파일 | 공용 컨테이너 + 버전 있는 codec + logical resource 참조 + 배열 payload | 동일 자료와 관계를 재열기. 실패/취소 시 불완전한 파일을 정본으로 삼지 않음 |
| 긴 작업 | UI 밖에서 읽기/메시/저장, 완료 후 유효한 문서에 명령으로 채택 | 취소와 실패가 UI 응답·기존 문서 보존을 해치지 않음 |

소유권 하나는 모든 backend에서 무복사를 보장한다는 뜻이 아니다. VTK·저장 codec에 필요한 변환 사본은 파생 캐시로 한정하고 소유자·버전·수명·해제 조건을 정한다. 스칼라 속성 변경과 메시 버전 변경의 invalidation 범위를 구분한다.

현재 RAD 자원의 필드 patch와 생성/삭제/교체 상태 snapshot은 기존 호환 경로로 유지할 수 있다. 대형 메시 편집이 추가되면 변경 구간·복합 명령에 맞는 기록을 사용한다. immutable 원문/메시를 재사용하고 모델 전체를 명령마다 복사하지 않는다.

현재 압축 ZIP 엔트리에 직접 mmap/부분 읽기가 된다고 전제하지 않는다. 큰 배열의 새 codec은 독립적으로 접근 가능한 binary chunk 또는 수명이 관리되는 불변 파일을 비교한다. NumPy 기반 배열을 출발점으로 삼되 HDF5/Zarr/메모리 매핑을 모두 초기 의존성으로 넣지 않는다. 실제 저장·재열기·메모리 조건을 만족하는 한 경로를 선택한다. 기존 `.caeprep` v1 reader·원문/INCLUDE 보존·지원 제한을 유지하며 형식 전환을 명시한다.

## 7. 지원 상태와 구현 순서

다음 표는 기술적 책임의 단계 배치다. 실제 병합 범위와 남은 작업은 위 현재 코드 설명 및 중앙 목록을 따른다. G1/G2의 native 관계와 G3의 제한된 채택이 구현됐더라도 B의 assembly/혼합 자유도·일반 case·배열/규모가 완료된 것은 아니다.

각 기능의 **자료 표현 / 의미 편집 / native 입출력 / 실제 계산 확인**을 구분한 capability 표를 유지한다. opaque 원문을 보존했다고 의미 편집을 지원하는 것이 아니며, 중립 자료에서 동작했다고 Radioss 출력이 지원되는 것도 아니다.

| 시점 | 반드시 반영할 것 | 현재 구현만으로 완료로 주장하지 않을 것 |
|---|---|---|
| P1 | 자원/객체/배치/native 참조 구분, 필드·성분·좌표/단위 문맥, 저장/작업 버전 계약 | 전체 assembly 편집·혼합 자유도 명령 |
| P3 / 첫 묶음 A | 다중 파트 자료의 읽기·선택·기존 지원 필드 편집, 범위 있는 참조, 대형 배열 소유 경계 | 새 instance/연결/재메시·모든 요소 편집 |
| P6a → P7a / 묶음 C | 최소 geometry/mesh 자원·배열 소유·원자적 채택/Undo/저장, 첫 CAD 생성·품질·지원 native 출력 | B 전체 완료는 선행하지 않음. 일반 형상 교체/모든 면 대응은 아직 미지원 |
| P6b/c / 묶음 B | 실제 assembly·shared mesh·set/condition·혼합 자유도·복합 변경과 재열기, 인덱스/배열/codec 이행 | 아직 연결하지 않은 솔버 물리·성능 범위 |
| P7b/c | 셸/중립면·quad/sweep hex·hybrid와 일반 재메시/형상 교체를 별도 범위로 구현 | 대응을 찾지 못한 모든 면/집합의 자동 복구 |

## 8. 묶음 B의 고정 완료 조건

B는 현재 미완료다. P6b 의미/관계(N16)와 P6c 규모(N17)를 별도로 종료하며, 현재 G2의 최소 케이스(N01)와 같은 작업을 중복 계수하지 않는다. 최소 케이스 구현을 N16 전체 완료 때까지 미루지 않고, 그 결과를 B의 혼합 모델에 재사용한다.

구현 전에 아래 자료와 지원 형식을 작업 범위에 고정한다. 조건을 통과한 묶음은 **다중 파트·데이터 기반 B 완료**로 기록한다. 더 큰 모델·다른 솔버·새 물리 요구를 나중에 추가해 완료를 취소하지 않는다.

첫 B의 모델링 범위는 assembly/FE component, 공유 절점이 있는 선형 beam/truss/shell/tet/hex 자료, 명시적 node/element/surface set, 정적 Cartesian 좌표계, 조건/접촉/케이스 참조와 복합 변경이다. native 편집/출력은 사전에 명시한 첫 RAD adapter 지원 범위로 확인한다. 반복 instance의 자료 표현·조회/저장 참조는 설계에 포함하지만 일반적인 instance 생성·배치 변경·native 전개는 ID allocator/transform을 갖추는 후속 작업으로 명시한다. 이를 B에서 구현한 것으로 보고하지 않는다.

| 조건 | 수행할 실제 작업과 통과 기준 |
|---|---|
| B1. 혼합 조립 | 셸·솔리드·보/연결 역할이 있는 조립 자료와 구성이 다른 두 번째 자료에서 파트/재료/단면·좌표·집합·조건을 조회·편집·저장·재열기. 지원 formulation과 native 출력 범위를 사전에 명시 |
| B2. 정체성과 공유 | 독립 source의 겹치는 native 번호·같은 표시 이름·의도적으로 공유한 절점을 구분. 할당 수정이 무관한 객체를 바꾸지 않고 공유 정의 변경은 명시된 소비자에 반영. instance 참조는 표현/조회/저장 수준을 별도 확인 |
| B3. 자유도와 관계 | 대상별 활성 성분·좌표계를 반영해 조건/connection을 편집. 한 조건을 서로 다른 케이스에 배정/해제하고 화면 숨김과 해석 비활성화를 구분. 허용되지 않은 새 성분·끊어진 참조는 진단, 실패 시 부분 변경 없음. Undo/Redo로 관계와 값 복원 |
| B4. 변경과 재메시 | 준비된 교체 메시로 자원 버전을 바꾸어 stale set·접촉·pick을 식별. 유효한 대응은 갱신하고 미해결은 표시. 같은 번호라는 이유로 잘못된 조건을 연결하지 않음. 일반 CAD 재메시 생성은 이 조건의 전제가 아님 |
| B5. 규모와 응답 | 아래 규모 자료에서 고정한 시간/메모리 예산을 만족. 스칼라 편집·선택·숨김 때 전체 메시 복사/재구축이 발생하지 않고 취소 후 기존 문서 유지 |
| B6. 저장·출력 | 완전한 작업 문서 재열기에서 객체·좌표·단위·관계·native 대응 유지. 명시한 첫 RAD 지원 범위는 native 출력/솔버 읽기로 확인하고 미편집 조건도 보존 |

규모 시험의 초기 목표 범위는 **100만 개의 실제 편집 대상 요소, 100개 파트, 20개 source 자원**이다. 화면 Actor/인스턴스만 복제해 이 규모를 채우지 않는다. 절점 수·혼합 요소·집합/조건·native ID와 사용 필드도 기록하며, 요소 수를 계산 자유도 수로 부르지 않는다. 이 수치는 구현 목표이며 현재 달성한 성능이 아니다.

Windows 기준 장비·자료 명세·초기 시간/메모리 목표와 측정 종료 규칙은 [단계별 작업서](execution-stages.md)에서 구체화한다. 그 초기 목표와 기준 측정으로 B 구현 전에 적용 예산을 고정한다. B 완료에는 기능 작업과 이 예산의 통과가 모두 필요하며 느린 수치를 기록하기만 해서는 통과가 아니다. 예산이 미정이면 B의 시작 준비가 끝나지 않은 것이며 A/C와 소비자 적용 전체를 차단하지 않는다. 구현 중 통과시키려고 자료·장비·예산을 바꾸지 않는다. 실제 변경이 필요하면 사유와 범위 변경을 별도로 기록한다.

## 9. 설계 근거

- [Radioss /PART](https://help.altair.com/hwsolvers/rad/topics/solvers/rad/part_starter_r.htm): 요소 그룹·material/property 관계와 CAD 원형의 구분.
- [Abaqus 2025 conventions](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEMODRefMap/simamod-c-conventions.htm): formulation에 따라 다른 활성 자유도·좌표/필드의 예. 이 예를 Radioss 번호 체계로 일반화하지 않음.
- [Radioss 좌표계](https://help.altair.com/hwsolvers/rad/topics/solvers/rad/radioss_coordinate_system_intro_c.htm): 전역·자연·요소/재료 좌표의 구분.
- [참조 제품 비교](gui-reference-matrix.md)의 HyperMesh 조립 구조와 MIDAS MeshFree의 모델 정의/해석 케이스 분리.
- 현재 `cae_core/document.py`, `application/session.py`, `radioss/deck.py`, `ui/viewport.py`의 소유·ID·projection·저장 경계.

구조를 적는 것만으로 모든 복잡한 모델에서 문제가 없다고 입증되지는 않는다. 위 유한한 사용 범위와 완료 조건을 통해 구현을 종료·확장할 기준을 둔다.


## 10. N16/N17 검토 체크포인트의 실제 계약 (2026-11-02)

이 절은 `feat/model-relations`의 실행 코드와 연결된 유한 범위다. B 전체나 성능 예산의 합격 선언이 아니다. 병합/정확한 검사 SHA와 중앙 잔여 판정은 [N16·N17 상태표](../CURRENT_STATE.md#remaining-work)를 따른다.

- `CommandDispatcher.execute_many`는 모든 자원 후보를 먼저 검증한다. 두 번째 자원 복원 실패도 이미 변경한 자원과 실패 자원 자체를 되돌리며, 실패 시 revision·dirty·Redo·관찰 event를 바꾸지 않는다. 성공은 하나의 ChangeSet·revision·Undo다. `PrepSession.execute_many`는 지원 native 명령을 sparse 후보에 적용하고 **최종** 관계를 검증하므로 유효한 재연결 묶음의 중간 상태 때문에 거절하지 않는다. 원문 bytes와 큰 기존 payload는 이력마다 복제하지 않는다.
- 독립 RAD source는 `plan_import_source`의 전체 native ID 대응표와 명시적 shared-node 선택을 검토한 후 한 명령으로 채택한다. 같은 이름·번호·좌표만으로 합치지 않는다. 하나의 source 안의 INCLUDE는 같은 native namespace를 유지한다. 원본 파일 bytes·SHA-256과 **원본→최초 채택 native 번호** 대응표는 불변 archive로 저장한다. 이후 메시 교체의 현재 번호를 이 최초 대응표라고 보고하지 않는다.
- 첫 import/remap profile은 동일한 명시 input/working 단위, LAW1/ELAST, BEAM/TYPE3·TRUSS/TYPE2·SHELL/TYPE1·SOLID/TYPE14, 대응 선형 요소, 명시적 node/element 집합·SURF/PART, FUNCT, BCS/CLOAD/INIVEL/TRA, 제한된 TYPE7, SKEW/FIX다. 원문 보존 가능 범위와 의미 remap 가능 범위는 다르다. 미확인 참조, 다른 단위, 비영(非零) per-card 단위 override는 import 전에 거절한다. 추가 header suffix 허용은 확인된 `/PART/id/0`에 한정한다.
- `dof_support`/`condition_support`는 대상 절점에 연결된 formulation의 병진 성분과 **전역축에서 표현한 회전 부분공간**을 조회한다. 셸 접선 회전과 공유 보 절점의 합성을 다루며 전역 Z축을 일괄 금지하지 않는다. Idrill의 적용 formulation·막 요소·보의 release 및 기본 orientation을 구분한다. 지원 밖은 미확인으로 표시한다. 이는 편집기 적용 가능성 검사이며 솔버 방정식 수·강성 rank·과구속 판정이 아니다. 비활성 회전 flag를 포함한 기존 BCS는 허용/보존한다. 새 CLOAD 모멘트와 초기속도는 알려진 대상 성분을 검사하고, 좌표계·집합·property 변경 시 기존 지원 조건을 무효하게 만들면 원자 거절한다.
- 정적 `/SKEW/FIX`는 원점·Y/Z 방향과 조건의 typed 좌표계 참조를 편집한다. 좌표계를 바꾸어도 절점 위치를 이동하지 않는다. 각 조건의 케이스 배정은 기존 N01 자원을 재사용하며 화면 숨김과 별개다.
- 준비된 메시 교체는 **메시 전용 INCLUDE와 동일한 component header 집합**에 한정한다. 절점/요소 수와 번호는 바뀔 수 있다. source resource·generation을 기록하고 영향받은 node/element set·surface 및 참조 조건을 stale로 만든다. 같은 번호가 남아 있어도 자동 복구하지 않는다. old ID→현재 typed reference와 generation의 명시적 대응으로 재연결하며, 실패 시 부분 변경이 없다. stale 상태는 저장/재열기/Undo에 남고 native 출력은 차단한다. 일반 CAD 재메시·근접 대응·형상 기반 자동 복구는 구현하지 않았다.
- `.caeprep` v5는 source archive와 model-relations 상태를 필수 구조로 저장하고 1/2/3/4 reader를 유지한다. 먼저 게시된 v4의 source archive 전용 구조는 빈 관계로 명시 이행하며, 이미 관계가 있는 v4는 검증하여 읽는다. v5에서 누락/null 관계는 거절한다. 모르는 자원을 저장에서 조용히 생략하지 않는다. 새 프로세스 왕복 검사에서 원문·native 대응·stale 상태를 확인한다. 반복 instance는 별도 stable UUID·base/imported source 참조·소유 resource 목록·`not-expanded` 상태로 표현/조회/저장한다. 생성/삭제는 각각 한 Undo이며 원형 bytes나 geometry를 복제하지 않는다. 독립 source archive와 다른 자료이고 일반 배치·변환·native 전개를 구현하지 않았다. 미전개 instance가 하나라도 있으면 native/Engine/case 출력을 명시적으로 거절하여 조용히 생략하지 않는다.

Native GUI의 File → Source models / import RAD, Mesh → Replace prepared mesh / reconnect targets와 고정 좌표계 작성은 8개 presentation에서 같은 세션 명령을 사용한다. Source models의 Instance references 탭은 별도 참조 목록·자원 소유·미전개 상태를 표시하고, 생성/삭제/Undo는 geometry 복제 없이 정본 세션에 연결한다. 계획 준비는 sparse snapshot의 worker에서 수행하고 짧은 owner lock으로 문서/revision/epoch를 다시 검사한다. 미완성 입력·busy·문서 교체 중 적용을 거절한다. 대화상자 Cancel은 모델 변경을 만들지 않으며, 창 종료 시 구독과 화면 자료를 해제한다. 비동기라는 이유만으로 대형 import의 응답 예산을 통과했다고 보지는 않는다.

실행 가능한 입력은 `scripts/evaluation/models/mixed-assemblies/beam_shell_tet`과 `truss_shell_hex`다. 각각 9절점/3요소/3PART이며, 하나는 beam+shell+tet, 다른 하나는 truss+shell+hex와 공유 절점을 갖는다. 두 입력을 함께 가져올 때 충돌 번호가 분리되고, 명시 shared mapping만 공유한다. `tests/test_mixed_relations.py`의 opt-in native 검사는 Starter/Engine 정상 종료, native 요소·PART·property 수와 부품 질량을 확인한다. 이 짧은 전부 고정 계산은 접촉 충돌·coupling 응답·응력 정확도 oracle이 아니다. `tests/test_multiresource_commands.py`, `test_source_models.py`, `test_instance_references.py`, `test_prepared_replacement.py`와 GUI/host 검사는 원자 실패·재열기·명시 재연결·8 presentation의 실제 명령 연결을 검사한다. Linux X11 확인을 Windows 또는 원제품 동일 과업 비교로 확대하지 않는다.

N17에서는 `mesh_view()`가 중첩 읽기 전용 tuple/mapping을 공유하고 `mutable=True`만 분리된 변경 가능 JSON 사본을 만든다. CLI/IPC의 공개 작은 DTO는 JSON 계약을 유지한다. geometry와 scalar revision의 invalidation을 나누고 exact entity lookup·VTK geometry·PART surface를 재사용한다. 소유한 unpublished cell payload만 특별 seal 경로로 동결하며 일반 caller 자료의 alias를 허용하지 않는다. PART inspector와 action의 같은 epoch/revision/target 조회는 작은 assignment 문맥을 재사용한다. 조건의 draft 방향/단위 명세는 캐시하지 않으며, 캐시 반환의 mutable 단위 문맥은 분리한다. 그러나 전체 저장/초기 parsing과 DOF 적용 조회의 전체 순회가 모두 제거된 것은 아니다.

고정 100만 요소의 한정 재계측에서 owned seal 이전/이후 core open은 20.013→12.084초, freeze는 10.348→1.890초, peak RSS는 2.643→1.626GB였다. index 구축은 0.220→1.011초로 증가했다. 이 값은 같은 입력의 **core 한정** 비교이며 새 seal 이후 GUI 합격 수치가 아니다. 앞선 GUI p95 선택 773ms, scalar 126ms, Undo 130ms, hide/show 724/750ms는 고정 예산을 넘는다. N17은 미완료이며 시간/자료/종료 기준을 바꾸지 않는다.

후속 PART 조회 재사용을 포함한 같은 저장 문서의 8회 GUI 진단 평균은 scalar 105.455→73.066ms, Undo 105.136→73.124ms였다. PART assignment 조회가 한 refresh에서 3→1회로 줄었고 scalar/Undo의 실제 Render는 계속 0회였다. 선택 평균 598.266ms, hide/show 쌍 1201.031ms는 렌더링 병목이 남았음을 보인다. 서로 다른 snapshot의 한정 비교이며 100회 p95 예산 검사를 대체하지 않는다. 기존 v4 진단 문서의 필수 관계 누락 열기 실패를 보존했고, 같은 원본 파일을 v5 명시 migration으로 다시 열어 성공했다.
