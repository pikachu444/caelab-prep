# 메셔의 구현 가능성과 도입 로드맵

기준일: 2026-10-30. 상태: **공개 코드·알고리즘·상용 매뉴얼 조사와 제한된 SDK 실험을 반영한 개발 계획**. Astra의 독립 아키텍처 검토, shell/midsurface 조사, hex/hybrid 조사, 상용 작업 흐름 조사를 통합했다. 제품 메셔·GUI·Windows 연결을 이번에 구현한 것은 아니다.

## 1. 앞선 계획에서 바로잡는 판단

공용 문서/GUI·기존 Gmsh 연결과 상용 수준의 자동 메셔 커널을 같은 확실성으로 계획하면 안 된다. 앞선 P7c의 “후보를 선택하고 구현”이라는 표에는 요구 기능에 대응하는 실제 코드·실행 결과가 부족했다. 문서의 단계와 종료 조건이 일관된다는 검토는 기술적 실현 가능성 검증이 아니다. Codex/Astra가 작성·검토했다는 사실도 커널의 성공률을 입증하지 않는다.

메셔 부분의 현실적인 첫 목표는 **검증한 기존 엔진을 사용하는 CAE 메시 작업 환경**이다. 준비된 면의 tri/quad, solid의 tet, 사용자가 분할·seed를 지정하는 제한된 sweep/hex부터 연결한다. CAD 준비·품질/기하 오차·실패 영역·국부 수정·조건/두께·Undo·저장/native를 공용 자산으로 만든다. 복잡 자동 중립면·범용 all-hex·임의 형상 hybrid 커널은 별도 실증/연구/SDK 평가이며 확정 납기를 가진 구현 항목으로 세지 않는다. 저장소의 공용 GUI·모델/문서 기반 전체가 이 커널들의 완성을 기다리지는 않는다.

계획의 A/B와 [단계별 작업서](execution-stages.md)는 유지한다. 이 문서는 **메셔 기능의 착수 근거와 지원 판정**을 추가한다. 작은 기능의 완료를 취소하지 않으며, 미실증 고급 기능을 이미 구현 가능한 것으로 표시하지 않는다.

## 2. 실제 확보 가능한 기반과 남는 일

| 기반 | 확인한 실제 제공물 | 현재 도입 판단과 한계 |
|---|---|---|
| Gmsh 4.15.2 | CAD/FE meshing SDK·공개 소스·Python/C++ API. tri/tet, size fields, Blossom/recombined·quasi-structured quad, transfinite/extrusion, experimental hybrid | 기본 엔진 유지. 우리 worker에는 uniform 2D/3D만 있으므로 나머지 기능은 실증 후 확장. SDK 기능 존재를 Prep 기능 완료로 세지 않음 |
| SALOME SMESH/HEXABLOCK | FE 메시 설정·submesh·그룹·품질·수정, 구조화 block/매핑의 공개 구현과 Python 경로 | 작업 설계·선택적 worker 비교 후보. 전체 SALOME embedding이나 경량 SDK 추출 성공은 아직 미확인 |
| SALOME SHAPER midsurface | 실제 macro·source·tests. 두 큰 면 또는 plane/cylinder 등 canonical geometry를 이용하는 제한적 추출 | 공식 문서가 추출면의 미연결과 후속 접합 작업을 명시. 범용 rib/boss·가변두께 커널로 채택하지 않음 |
| OCCT | STEP/BRep, 거리·투영·offset·boolean·sewing·shape repair | 수동/반자동 준비면과 partition의 기반. 맞은편 면 선택·두께장·junction 추론은 별도 개발. healing이 형상/위상/공차를 바꿀 수 있음 |
| QuadriFlow / Instant Meshes | 공개 field-aligned surface remeshing 소스와 CLI | triangle/point-cloud retopology. CAD 면/경계·두께·조건 연관성을 갖춘 FE shell 엔진의 대체로 선정하지 않음 |
| HybridOctree_Hex | BSD-3 공개 all-hex 구현·입력/결과·여러 모델 수치. closed-manifold 삼각표면 입력 | 제한된 연구 후보. STEP assembly·지정 feature/접촉 gap·공유면·Windows/native API는 새 실증 필요. 연구 논문은 sharp feature의 명시 제약을 후속 과제로 둠 |
| AlgoHex/HexEx·HexDom 계열 | 공개 frame-field/polycube/hex 추출·혼합 메시 연구 코드 | 하위 추출기와 완성 전처리기를 구분. AlgoHex는 incomplete output 가능성을 명시. 우선 제품 엔진 대신 특정 연구 질문의 비교군 |
| SALOME MG-Hexa/MG-Hybrid·MeshGems 계열 | 공개 wrapper/API와 상용 meshing runtime | wrapper가 공개됐다고 무료 kernel이 확보된 것은 아님. 현행 SDK의 입력·Windows·재배포 조건과 사용자 형상 평가가 선행 |
| Coreform Cubit | CAD 준비·partition·sweep/multisweep·tet/hex/hybrid·품질과 scripting | 유료 외부 프로그램 경로 후보. API 자동 실행과 OEM embedding은 구분. 자체 커널 개발의 필수 선행으로 두지 않음 |
| CAD MidSurfer 논문(2026) | variable-thickness·복잡 face pairing을 다루는 논문·6개 benchmark·dataset | 확인한 저자 페이지에 code/API/license 링크가 없음. 읽고 연구할 자료이며 즉시 가져올 kernel로 계산하지 않음. 동명의 voxel/생물 구조용 ParaView 플러그인과 다름 |

도입 순서는 Gmsh의 제한 경로 → 필요 기능별 공개 구현 재현 → 부족한 범위의 SDK/외부 앱 평가다. 모든 후보를 제품 의존성에 추가하거나 매 단계 전체 기반 선정을 반복하지 않는다. 공개 구현의 배포 조건은 실제 채택 버전·포함 dependency별로 확인한다.

## 3. 상용 매뉴얼에서 확인한 실제 작업

HyperMesh·Abaqus·COMSOL·midas NFX도 한 번의 자동 호출만으로 모든 형상을 처리하는 방식이 아니다. 공개 문서는 다음을 제품 기능으로 다룬다.

| 작업 계열 | 공식 문서에서 확인한 사용자 작업 | Prep가 구현할 공용 자산 |
|---|---|---|
| CAD 준비 | gap/작은 edge·face 검사, repair tolerance, fillet/hole 처리, virtual topology, partition | 진단 대상 선택, 허용 공차·보존 feature, 변경 preview/Undo와 원본 대응 |
| 표면 메시 | 전역/국부 크기, edge count/bias, seed matching, mapped/free quad·tri 선택 | 저장되는 recipe, 공통 edge 제약, 실패 face와 local remesh |
| midsurface/midmesh | 추출 방식·두께/offset, base/pair 선택, gap·sliver·intersection·밖으로 나간 node 검사 | 추출/준비면/직접 midmesh를 구분, 두께·법선·junction 편집과 실패 영역 |
| tet | watertight 확인, curvature/proximity·growth 설정, defeaturing 후 재생성 | source/영역 보존, 품질·기하 오차, 수동 보수 후 재생성 |
| hex/sweep/hybrid | mappable partition, source/target·연결면, edge divisions·층수·bias, 전이 영역 | 제한된 sweepability 진단, 사용자가 주는 분할/hint, 실제 interface 연결 검사 |
| 품질/수정 | 불량 요소 필터·집합 추출, node/element 수정, 부분 rebuild와 재검사 | 형식별 metric·실패 cluster·수정 명령·rollback·관계 invalidation |

HyperMesh Map은 복잡 solid의 사전 분할과 mappable 여부를 요구하고 모든 mappable solid의 동시 생성도 보장하지 않는다. Abaqus bottom-up은 수동 작업이며 형상에서 벗어난 mesh의 적합성과 association을 확인하도록 한다. COMSOL Free Quad도 필요시 triangle을 삽입한다. NFX 공식 2024 교육자료의 mesh size/seed matching·quality·CAD cleanup을 원문 PDF와 렌더 화면으로 확인했다. 메뉴를 재현하는 것과 이 작업들의 신뢰성을 확보하는 것은 다른 개발량이다.

BeidPrep 2.0의 공식 페이지·자체 평가도 참고했다. 자체 synthetic 8종 평가에서 쉬운 6종과 freeform housing 2종의 coverage 차이와 잔여 불량 요소를 공개한다. 현재 제품 설명은 solid mesh 생성 미지원을 명시한다. 유용한 통합 제품 사례이지만 공개 커널 또는 범용 상용 동등성의 증거로 해석하지 않는다. 이는 1.0.1의 이전 Windows 시험과 다른, 이번 웹 자료 조사다.

## 4. 이번에 직접 실행한 SDK 실험

Linux x86_64, Python 3.12.14, Gmsh 4.15.2, 요청 thread=1. 작은 합성 형상 4개를 각 새 프로세스와 120초 제한으로 실행했다. GUI·작업 문서 채택·STEP roundtrip·RAD native·Windows는 이 실험 범위가 아니다. 속도는 작은 사례의 관측값이며 제품 성능 목표나 상용 비교가 아니다.

| 실험/고정 recipe | 관측된 요소/품질 | 판정 |
|---|---|---|
| 구멍 있는 평판, Algorithm 11 | quad4 802개, minSICN 약 0.617, 기록된 SDK 오류 0 | 해당 SDK/작은 형상에서 quad 생성 재현. 기하/FE 적합성 전체 인증은 아님 |
| 환형 단면 4층 extrusion, Algorithm 11+recombine | 생성된 hex8 528개, 해당 hex의 minSICN 약 0.543. `Could not find extruded vertex` 등을 포함한 SDK 오류 1,375개 | **정상 sweep 성공으로 인정하지 않음.** return code 0·양의 quality·hex 개수만으로 통과시킬 수 없음 |
| 가로 관통 구멍이 있는 L 브래킷, HXT | tet4 1,511개, minSICN 약 0.363, 기록된 SDK 오류 0 | 해당 SDK/작은 형상에서 tet 생성 재현 |
| 같은 브래킷, 공식 CLI hybrid와 같은 9/9/recombine 설정 | 두 번째 실행에서 tet4 519개·hex8 174개까지 조회. 이후 요소 metadata 조회가 `Size of basis incompatible with element type`로 실패 | **전체 family·품질·연결성 미확인.** 기본 conformity=0. 실제 FE hybrid 지원으로 세지 않음 |

hybrid의 최초 계측 실패 뒤 계측 처리만 한 번 보정하여 재실행했다. 알고리즘 옵션은 바꾸지 않았으며 최초/재실행의 요소 개수도 달랐다. 알려진 두 family만 합산해 전체 요소 수라고 표시하지 않는다. sweep 실패를 Gmsh의 모든 sweep 불가로, hybrid 조회 실패를 모든 hybrid 생성 불가로 일반화하지 않는다. 후속 F1에서 공식 예제와 recipe/API 조합을 분리해 원인을 확인해야 한다. 성공할 때까지 옵션을 무한 탐색하지 않는다.

현재 확인한 Gmsh 4.15.2 공식 문서에서 3D recombination/conformity는 experimental이고 기본 conformity는 nonconforming이다. 공식 source의 `-hybrid` 설정은 Algorithm2D=9, Algorithm3D=9, Recombine3DAll=1이다. HXT=10을 켰다는 사실만으로 hex/hybrid를 시험했다고 하지 않는다. source의 trihedron(type140) 같은 전이 형식은 목표 solver 지원을 확인하지 못하면 native export를 차단한다. 이번 metadata 오류의 원인을 type140이라고 확정한 것은 아니다.

## 5. 기능별 개발 착수 판단

| 기능 | 지금 가능한 결정 | 다음 작업과 넘어갈 조건 |
|---|---|---|
| 문서/배열/채택·GUI/품질/수정/저장 | 기존 구현과 명확한 앱 엔지니어링 경로가 있음 | 준비된 mesh부터 P6a/공용 부품 개발. 실제 기능·실패·Undo/파일 조건으로 닫음 |
| 기본 tri/tet 생성 연결 | 기존 worker 이력과 이번 tet 재현 근거가 있음 | C의 문서/native 연결. local sizing·conformal은 별도 미실증 항목으로 추적 |
| 준비된 shell 면의 quad | 실제 공개 kernel·논문·작은 quad 재현이 있음 | 아래 F1/F2에서 곡면·holes·seed·두께/법선/면 대응을 확인한 뒤 H-Q/S에 연결 |
| 제한 sweep/hex | 실제 API/공식 예제가 있으나 이번 recipe는 정상 통과 못함 | 공식 recipe 재현과 원인 분리부터 진행. supported geometry/seed/layer·오류 0·실제 conformity가 확인되기 전 H-S 제품 구현을 확정하지 않음 |
| hex–tet hybrid | 공개/상용 후보가 있으나 이번 Gmsh 결과는 전체 검사 실패 | 지원 cell/전이 topology부터 실증하고 native 변환을 별도 확인. 연구용 cell을 삭제·퇴화 변환해 통과시키지 않음 |
| 반자동 중립면 | OCCT 연산과 제한 SHAPER reference 존재 | 사용자가 source/opposed face를 지정하는 일정두께 plane/cylinder부터 별도 F1/F2. 자동 복잡 pairing을 전제로 하지 않음 |
| rib/boss·가변두께·freeform 자동 중립면 | 현재 실제 사용할 범용 kernel을 확보/재현하지 못함 | 공개 구현 확보·논문 재현 연구·SDK/외부 앱 평가 중 하나를 선택. 확정 제품 backlog/납기에서 제외 |
| 일반 CAD 자동 all-hex | 공개 연구 구현은 존재. 실제 목표 CAD/assembly 검증 없음 | HybridOctree 등 제한 연구만 F0부터. 실패하면 외부 mesher import/상용 SDK 또는 보류. 상용 동등성을 모델 능력으로 약속하지 않음 |

특히 C의 face/volume local size는 현재 uniform min/max worker에 UI만 추가하면 구현되지 않는다. Gmsh `setSize`는 point 대상이며 field/restriction·경계 전파와 실제 크기 분포 확인이 필요하다. `occ.fragment`는 conformal 인터페이스를 만드는 경로가 있지만 boolean 뒤 tag/면 대응은 달라질 수 있다. part·UUID·하중/접촉의 의미 보존은 Prep의 추가 책임이다.

C의 필수 local/conformal 조건을 통과하지 못하면 C 완료가 아니다. 작은 결과를 먼저 배포할 때는 “기본 tri/tet 연결 완료 / local·conformal 보류”로 정확히 나누며 C의 원래 조건을 조용히 완화하지 않는다.

## 6. 구현 가능성을 먼저 확인하는 유한 단계

| 단계 | 입력·수행할 일 | 종료 조건과 허용하는 주장 |
|---|---|---|
| F0 실제 코드/API 확인 | 기능마다 후보 최대 2개, 버전·source/API·입력 제한·공식 예제·배포 경계 확인 | 접근 가능한 실행 후보와 대안 1개를 정하면 조사 종료. 코드/API가 없으면 연구/SDK/외부 앱 평가. **구현 가능 판정은 아님** |
| F1 독립 재현 | 제품 GUI 없이 공식 예제 1개와 다른 형상 1개. 각 실행 timeout·메모리와 지원 cell을 고정 | 오류 없는 산출물과 전체 inventory·품질·기하 검사가 되면 “이 recipe 재현”. 실패는 환경/recipe/algorithm/계측을 구분. 원인을 바꾸는 수정 후 관련 사례만 재실행 |
| F2 지원 형상군 실증 | 기능당 고정 6개: 대표 정상 3, 범위 안의 어려운 형상 2, 명시 미지원 1. 정상/어려운 각 1개는 recipe를 맞추지 않은 holdout | 지원 입력 5개가 사전 geometry/topology/quality·시간 조건 통과, 출력 cell의 목표 solver mapping 가능성을 확인. 미지원 1개는 안전한 실패/제한 보고. **그 형상군의 제품 연결만 허용** |
| F3 제품 연결 | 통과한 엔진/recipe만 P7a/b/c의 선택·편집·Undo·저장·native/API에 연결 | 해당 P 카드의 실제 사용자 작업·실패/취소·파일 보존·Windows/native를 통과하면 그 기능 완료 |
| F4 실무 적합성 | 정한 작업군의 24개 고정 입력(개발 16, 미노출 8)과 수동/기존 도구 작업 비교. 기능군을 release에 명시 | 자동/수동 보정 결과를 분리하고 허용한 작업량 안에서 올바른 최종 모델을 만들며 필수 위반 0. 대상 해석의 소수 reference 계산까지 통과하면 **그 작업군의 실무 지원**. 모든 상용 기능 동등성 주장은 별도 |

F0의 **최대 3개 집중 작업일**은 접근성/도입 경로를 결정하는 조사 한도다. 그 안에 자동 중립면·hex 커널을 완성한다는 일정이 아니다. F1은 위 두 입력과 최대 두 recipe 조합으로, F2는 고정 여섯 입력으로 평가를 닫는다. 버그 수정은 원인과 관련 사례를 다시 확인하되 목표 기능을 매번 확대하지 않는다. 한 조사 작업 예산 안에 원인을 좁히지 못하면 결과·차단 원인·다음 경로 하나를 남기고 no-go/보류로 닫는다. 불합격 판정으로 조사만 종료했을 때 기능 완료로 세지 않는다.

F2는 제품 연결의 시작 문턱이며 아직 전체 native workflow가 아니다. 기존 codec이 없는 형식은 목표 family/순서/참조 mapping을 먼저 확인하고, F3에서 생성 provider와 실제 native 재읽기를 구현·검증한다. 독립 export probe가 있다면 그 결과를 F3에서 재사용한다. F2에서 원리상 불가능한 native mapping을 발견하면 해당 native 기능은 no-go로 남긴다. F3가 끝나기 전에 solver 지원 완료라고 표시하지 않는다.

F4의 24개는 상용 동등성을 증명하는 통계 표본 수가 아니다. 현실적인 초기 제품 검토 묶음이며 착수 전에 정확한 원본·기대 결과·품질/오차·자동 성공률·수동 시간 상한을 한 번 고정한다. 예시 생산성 목표는 자동 통과 22/24 이상, 나머지의 명시적 수동 복구, 보정 시간 중앙값 10분 이하다. 이 숫자는 제안이며 현재 실측이나 공학 품질 표준이 아니다. 오류 있는 결과를 성공 처리하거나 실패 사례를 분모에서 빼면 통과가 아니다. 실제 작업군이 없으면 F4 미착수로 남기고 이미 끝난 F3를 다시 미완료로 바꾸지 않는다.

## 7. 무엇을 검사하고 언제 멈추는가

형상군과 기능에 필요한 기준만 고정한다. 모든 후보에 아래 전체를 반복하는 무제한 평가 캠페인을 만들지 않는다.

- **기하/위상:** 보존 지정 hole·feature·contact gap, 예상 connected component와 junction, surface/curve deviation, CAD tolerance·단위. healing으로 중요한 형상을 지워 성공률을 올리지 않음.
- **공유/독립:** conformal 경계의 실제 공통 node/face, 독립 부품의 중복 좌표를 분리. hanging/nonconforming을 허용하면 명시한 solver relation으로 표현하고 별도 지원으로 판정.
- **물리 의미:** shell 두께·offset·법선·재료축·영역/조건. 중립면의 위치뿐 아니라 두께장과 접합이 맞아야 함. FE 정식화별로 적합성을 판단.
- **요소/품질:** family·차수별 Jacobian/validity·warpage·angle/size grading과 worst set. Gmsh minSICN, scaled Jacobian, solver의 Jacobian ratio를 같은 지표로 취급하지 않음. 선형 tet의 양의 체적이나 q_min 하나로 hex/고차 유효성을 인증하지 않음.
- **native/해석:** 모든 생성 family를 지원 표에 넣고 node ordering·part/집합/조건을 출력 후 재읽기. 미지원 형식의 silent drop 금지. Starter 읽기와 변위/에너지·굽힘 등 reference 계산의 적합성은 별도 gate.
- **작업량:** 최초 자동/보정 후 성공, 실패 이유·수동 pairing/partition·수정 시간과 비용. 공개 논문의 좋은 예제·요소 수·FPS만으로 생산성을 판단하지 않음.

F1/F2는 최종 후보의 고정 입력을 한 번 수행하고, 실패를 수정한 영향 항목만 다시 확인한다. F4도 한 번 고정한 묶음을 사용한다. 새 형상군은 다음 범위이며 기존 구현/회귀가 바뀌지 않은 통과 사례를 계속 늘려 검사하지 않는다. “지원 범위를 제한한다”는 결정은 원래 실패와 이유를 남기고 기능 이름/지원표에 반영해야 한다.

## 8. 논문·매뉴얼을 어떻게 사용할 것인가

매뉴얼에서는 입력·설정·출력·실패 수정의 **기능 명세**를 추출한다. 논문에서는 가정·자료구조·수식·범위·실패 조건을 확인한다. 허용된 공개 구현은 버전을 고정해 직접 재현하고 필요한 부분을 연결/확장한다. 사용할 코드가 없으면 해당 알고리즘의 자체 구현은 별도 연구 작업으로 산정한다. robust predicate·trimmed/periodic CAD·퇴화 입력·boundary recovery·sliver/untangling·junction·전이 cell·병렬/메모리·Windows 배포가 의사코드 밖의 실제 작업이다.

기능적 아이디어를 참고해 독립 구현하는 것과 매뉴얼의 본문·그림·아이콘·프로그램 소스를 그대로 옮기는 것은 구분한다. 공개 저장소의 source도 실제 허용 조건을 따른다. 이 계획은 상용 매뉴얼의 무단 복제·번역 배포나 비공개 커널 추출을 개발 방법으로 삼지 않는다. 한국저작권위원회도 아이디어와 그 표현의 보호를 구분한다.

Codex/Astra는 공개 API 연결, 자료구조·UI/명령·파일/실패 처리, 제한된 CAD 연산·알고리즘 실험과 기존 코드의 확장에 사용할 수 있다. **모델에 가능하다고 물어보는 일을 F1/F2의 실제 결과 대신 사용하지 않는다.** 복잡한 신규 meshing kernel은 기하/수치해석 전문 연구와 유지보수의 별도 책임이며, 모델만으로 기간·품질·일반화를 보장하지 않는다.

## 9. 근거

- Gmsh [4.15.2 manual](https://gmsh.info/doc/texinfo/), [공식 source](https://gmsh.info/src/gmsh-4.15.2-source.tgz), [quasi-structured quad 논문](https://arxiv.org/abs/2103.04652). 문서/API·공식 source의 CLI/element 상수와 논문을 대조했다.
- SALOME [mesh catalog](https://www.salome-platform.org/?page_id=374), [SMESH mapping](https://docs.salome-platform.org/latest/gui/SMESH/quad_ijk_algo.html), [SHAPER midsurface 범위](https://docs.salome-platform.org/latest/gui/SHAPER/addons_Features/midSurfaceFeature.html), [실제 macro](https://github.com/SalomePlatform/shaper/blob/master/src/PythonAddons/macros/midSurface/surfaceMediane.py). macro와 tests를 읽었으며 이 세션에서 실행하지 않았다.
- OCCT [Shape Healing](https://dev.opencascade.org/doc/overview/html/occt_user_guides__shape_healing.html), CGAL [Mesh_3](https://doc.cgal.org/latest/Mesh_3/index.html), [optimization 상태](https://doc.cgal.org/latest/Mesh_3/group__PkgMesh3Functions.html), [linear hex validity 논문](https://arxiv.org/abs/1706.01613).
- 공개 연구: [HybridOctree_Hex](https://github.com/CMU-CBML/HybridOctree_Hex), [AlgoHex](https://github.com/cgg-bern/AlgoHex), [QuadriFlow](https://github.com/hjwdzh/QuadriFlow), [Instant Meshes](https://github.com/wjakob/instant-meshes), [CAD MidSurfer](https://min-tang.github.io/MidSurf/). 코드/논문/공개 결과의 범위와 우리 미실행을 구분했다.
- 상용 작업: HyperMesh [Map](https://2025.help.altair.com/2025.1/hwdesktop/hwx/topics/pre_processing/meshing/meshing_solid_map_unity_c.htm), [Tet tutorial](https://2025.help.altair.com/2025.1/hwdesktop/hwx/topics/tutorials/hwx/tetrameshing_t.htm), [Midmesh](https://2025.help.altair.com/2025/hwdesktop/hwx/topics/pre_processing/meshing/midmesh_generate_unity_t.htm); Abaqus [bottom-up](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-c-mgnconcmeshingbottomup.htm); COMSOL [Free Quad](https://doc.comsol.com/6.3/doc/com.comsol.help.comsol/comsol_ref_mesh.24.67.html), [Swept](https://doc.comsol.com/6.3/doc/com.comsol.help.comsol/comsol_ref_mesh.24.88.html).
- NFX [공식 교육자료 배포](https://support.midasuser.com/hc/ko/articles/23673650074905--정기교육-NFX-기본교육-교재-및-실습자료), [2024 PDF](https://patch.midasit.com/00_MODS/kr/03_TechnicalData/기계/교육자료/2024/midas%20NFX%20구조해석%20기본.pdf). PDF의 size/seed matching·quality·cleanup 부분과 화면을 직접 확인했다. 제작사 자료는 저장소에 복제하지 않는다.
- 비교 제품의 자체 범위: [BeidPrep 2.0](https://beidersim.com/beidprep.html), [midsurface 자체 평가](https://beidersim.com/validation-midsurface.html), [Naksha](https://agentnaksha.com/). 웹 자료 조사이며 이번에 두 제품을 실행한 결과가 아니다.
- [한국저작권위원회: 아이디어와 표현](https://www.copyright.or.kr/information-materials/common-sense/knowledge-for-netizen/index.do).

이번 결과로 끝낼 것은 근거 없는 확정 개발 약속이다. 다음 실제 작업은 기본 공용 자산/문서 구현과 병행하여 **준비면 quad·제한 sweep·반자동 중립면 중 한 기능의 F1/F2**를 명시적으로 수행하는 것이다. 하나의 기능이 go가 되면 제품 연결로 이동하고, 실패하면 그 원인과 대안으로 조사 작업을 닫는다.
