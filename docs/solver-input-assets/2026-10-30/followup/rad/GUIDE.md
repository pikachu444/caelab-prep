# RAD 파일 생성을 개발할 때 실제로 볼 자산

PR #10에서 ‘전수 필드 명세 미완성’을 공식 필드 설명이 없는 상태처럼 읽히게 한 점을 구분한다. **공식 카드별 생성 규칙은 이미 전체 HTML에 있고, CFG에는 타입·default·단위·조건부·버전별 FORMAT이 있다.** 아직 없는 것은 이를 우리 제품의 모든 카드 생성 기능으로 구현하고 검증한 상태다. CFG는 별도 이용 조건이 있어 공용 자유 schema로 재배포하지 않는다.

바로 열기: [Python RAD writer](assets/meshioplusplus/src/python/meshioplusplus/radioss/_radioss.py) · [k2rad Starter/Engine 조립](assets/k2rad/k2rad/writer/assembly.py) · [기본값 처리](assets/opencourant-readers/starter/source/modules/defaults_mod.F90) · [완전 Starter](assets/meshioplusplus/tests/python/meshes/radioss_th/column/column_0000.rad) · [Engine](assets/meshioplusplus/tests/python/meshes/radioss_th/column/column_0001.rad)

## 새로 확보한 writer와 예제

| 실제 자산 | 개발에 활용할 부분 | 그대로 전제하면 안 되는 것 |
|---|---|---|
| [meshio++ RAD writer](https://github.com/loumalouomega/meshioplusplus/blob/548cbc8622ba80356590521331b8b21fa04e6e3a/src/python/meshioplusplus/radioss/_radioss.py) | `write`1305–1696행, integer10/real20 formatter, node→element→part/property, group/surface, C++ 동일 writer. CAD/mesh 채택 후 native geometry 출력의 실제 참고 코드 | 기본 `stubs=False`; `stubs=True`의 LAW1/PROP는 placeholder다. 재료·하중·접촉 전체를 보존하는 writer가 아니며 미지원 cell/data를 경고 후 버릴 수 있다. wrapper는 input2022를 명시 |
| [k2rad writer](https://github.com/pmquang87/k_to_rad_converter/tree/d7652dadb8dcd4b558a68e609e7e5c02ebfe3a26/k2rad/writer) | `assembly.py:1774 build_starter`, `4295 build_engines`, materials/mesh/loads/contacts/output 등 실제 분리된 emitter와 `ConversionState`, rawtext 출력. 기존 INP converter보다 넓은 writer 구조 참고 | LS-DYNA→RAD 변환기다. 모든 native card를 자유롭게 생성하는 일반 제품 API라는 뜻이 아니다. 긴 수치 필드의 폭, 경고·skipped·recognized-not-emitted도 별도 확인 필요 |
| [MIT 자작 column 모델](https://github.com/loumalouomega/meshioplusplus/tree/548cbc8622ba80356590521331b8b21fa04e6e3a/tests/python/meshes/radioss_th/column) | 실제 Starter/Engine pair. 12nodes·2BRICK, PART/LAW1/PROP, node group, 고정 BCS, 초기 속도, TH/output와 단위·종료시간을 함께 읽을 수 있다. `assets/meshioplusplus/tests/python/meshes/radioss_th/column/`에 보존 | top node는 초기속도다. 상류 README가 latest-20260728 실행과 dt scale0.5를 설명하지만 이번에 solver를 실행하지 않았다. 수치 정확성 기준 전체를 대신하지 않는다 |
| k2rad의 `.k`와 expected Starter/Engine fixture | material·property·contact·reference를 writer가 어떤 문장으로 출력하는지 쌍으로 비교하는 자료 | 해석 검증 예제가 아니다. shell_explicit에는 외력/초기속도/구속이 없고 rigid_contact의 CLOAD는 curve1을 참조하지만 FUNCT1이 없어 완결 해석 benchmark로 분류하지 않았다 |

MIT 원문과 고정판 source는 `assets/meshioplusplus/`, `assets/k2rad/`에 있다. 실제 library 도입은 전체 upstream package/API를 대상으로 해야 한다. 이 폴더의 부분 소스만 복사하여 실행된다고 가정하지 않는다.

## 어떤 새 카드를 추가하든 찾아갈 공식 규칙과 reader

기존 [전체 카드 목록](../../catalogues/radioss.csv)의 원문 이름에서 해당 공식 Format/Definition/Comments로 들어가면 행 순서·필드·optional/조건·ID/단위·예제가 있다. 현재 조사 환경의 804개 실제 원본은 `solver-input-research/tmp/radioss/keywords2024/`에 있다. 새 keyword마다 대표 몇 장을 다시 찾는 대신 이 전체 원문을 사용한다.

고정 OpenCourant source ZIP에는 전체 `starter/source/`가 이미 있다. 이 후속 작업은 전체를 조사 환경의 `analysis/opencourant/starter/source/`로 풀어 어떤 카드를 구현할 때 어느 reader/dispatch/default를 읽는지 연결했다. 선택한 다음 파일은 AGPL 고지와 함께 `assets/opencourant-readers/`에도 담았다.

| 만들 기능 | 실제 공식/solver source 진입점 | 개발에 필요한 확인 내용 |
|---|---|---|
| material card | `materials/mat/hm_read_mat.F90` dispatch → `mat001/hm_read_mat01.F`, `mat036/hm_read_mat36.F` 등 각 law | keyword/LAW 선택과 실제 수치 의미 검사, 조건부 반복 curve, 참조/default. 모든 law의 같은 규칙을 가정하지 않음 |
| shell/solid property | `properties/hm_read_properties.F` → `shell/hm_read_prop01.F`, `solid/hm_read_prop14.F` | 명시값·sentinel·inherited default, formulation별 제약, shell 두께/적분점 |
| 기본 formulation | `modules/defaults_mod.F90`, `general_controls/default_values/hm_read_defshell.F`, `hm_read_defsolid.F` | implicit/explicit·2D 상태에 따라 바뀌는 default와 `/DEF_SHELL`/`/DEF_SOLID` 영향 |
| PART/material/property 관계 | `model/assembling/hm_read_part.F` | property/material ID 참조와 타입 제약. composite 예외는 공식 PART Comments와 함께 읽음 |
| BCS/CLOAD | `constraints/general/bcs/hm_read_bcs.F`, `loads/general/cload/hm_read_cload.F` | DOF·group·skew/submodel·curve·scale가 어떻게 해석되는지 확인 |
| 접촉 TYPE7/24 | `interfaces/reader/hm_read_interfaces.F` → `interfaces/int07/hm_read_inter_type07.F`, `int24/hm_read_inter_type24.F` | contact 선택과 선택 카드별 조건/면·그룹·default 연결. 다른 접촉 유형으로 일반화하지 않음 |
| 단위가 있는 수치 field | `devtools/hm_reader/hm_get_floatv.F`, `hm_get_floatv_dim.F` | descriptor→native field 값·단위 변환. source getter만으로 고정열을 알 수 없으므로 공식 Format과 함께 사용 |

여기서 `starter/source/` 이하 경로를 줄여 썼다. 이 reader들은 exporter가 아니다. 수치 의미 검증과 solver가 실제 사용하는 default의 근거이며, 고정열·조건부 출력은 공식 Format/CFG 또는 writer의 역할이다. source는 release20261011/profile2026 계열, 주 매뉴얼은2024라 버전 차이는 유지한다.

## ‘필드 명세’의 구체적인 확보 예

- **LAW1:** 공식 Format은 제목·밀도행·E/ν행을 설명한다. reader97–112행은 reference density0이면 initial density를 쓰고, E≤0을 오류로 다루며 ν=0.5를 내부 값으로 조정한다. 이는 exporter가 사용자 입력을 몰래0.499로 다시 쓰라는 규칙이 아니다. 입력과 solver-side normalization을 분리한다.
- **LAW36:** 공식 Format에는 `N_funct>0`인 curve ID/scale/strain-rate 반복행 수가 명시되어 있다. reader127–175행은 해당 배열, ν범위, NRATE1..100, 참조 curve와 scale의 단위 경로를 읽는다. 하나의 scalar form으로 만들 수 없는 이유가 실제 원문/코드에 있다.
- **SHELL property:** `hm_read_prop01.F`는 `/DEF_SHELL`의 ISHELL/ISMSTR/IPLAS/ITHK 등을 상속한다. NIP=-1은 이 함수 내부 `NPTS_D=0`으로 바뀌며 NIP>10은 오류다. NIP를 `/DEF_SHELL`에서 그대로 상속한다고 쓰면 틀린다. `defaults_mod.F90:init_def_elem`에서는 implicit shell의 formulation0이24, 일반 미지정0이1로 정해지는 등 해석 문맥이 있다.
- **BCS/CLOAD:** BCS reader는 submodel skew fallback과6DOF를 분리한다. CLOAD의 zero scale은 단순 숫자1이 아니라 unit dimension 값으로 바뀌는 경로가 있다. global ID, 좌표계, 단위/참조를 남겨야 한다.

위 사례는 모든 field를 새 공통 schema로 옮긴 결과가 아니다. 기존 전체 공식 설명과 실제 reader를 이용해 새 카드를 구현할 수 있는 구체적인 출발점이다.

## CFG를 활용할 수 있는 범위와 실제 제한

같은 source archive의 `hm_cfg_files/config/CFG/radioss*/`에는 ATTRIBUTES, DEFAULTS, DIMENSION, FORMAT, conditional export가 들어 있다. 예를 들어 `radioss2024/PROP/prop_p1_shell.cfg`는2024와2020 FORMAT을 모두 가진다.2024의3행은 NIP 다음10자 reserved blank이고,2020에서는 그 자리에 ISTRAIN이 있다. 따라서 속성 이름만 모아 같은 formatter로 출력하면 판본을 틀릴 수 있다.

CFG 헤더는 **OpenRadioss software와 연결해서만 사용·수정할 수 있는 한정 허가**, 수정분 SISW 반환/CLA 조건을 명시한다. OpenCourant 본체의 AGPL을 이 파일들에 덮어 적용하지 않는다. 직접 연결 사용이 사용자 목적에 맞는지와 조건 이행은 별도 판단이 필요하고, 이 수집에서 공용 자유 schema로 재배포하지 않았다. 원본은 접근 실패로 못 찾은 것이 아니라 조건이 있는 채 실제 보유하고 읽은 자료다.

## 이번에 새로 시도한 경로와 남은 것

meshio++와 k2rad는 PR #10에서 시도하지 않았던 공개 writer 경로였고 이번에 실제 확보했다. column 모델도 기존 NC QA가 아닌 MIT 자작 완전 pair를 확보한 것이다. 따라서 ‘NC-free 실제 예제 없음’은 이 작은 모델 범위에서 수정할 수 있다.

`luchete80/radioss_tutorials`도 실제 source를 읽었다. `inc_forming/mesher.py`에는 Material/Prop/Part/Model과 Starter/Engine 생성이 있지만 repository tree에서 LICENSE/COPYING/NOTICE를 찾지 못해 공개 재사용 code에 포함하지 않았다. 접근은 성공했고 재배포 허용이 확인되지 않은 경우다. 원천은 https://github.com/luchete80/radioss_tutorials/tree/09f7bd718cbe2eb08abdae36001891c681966dc0 .

이제 남는 것은 ‘아무 생성 규칙·writer 참고 source가 없다’가 아니다. 필요한 공식 설명·직접 reader·일부 실제 writer·완전 작은 모델은 있다. **모든 카드의 조건부/의존/기본값을 우리 데이터/API에 옮긴 전수 schema, 각 writer 후보의 실제 도입/동작 확인과 모든 모델의 의미 보존**은 아직 구현하지 않았다. 이 자료 확보 작업을 그 신규 제품 구현으로 확대하지 않는다.
