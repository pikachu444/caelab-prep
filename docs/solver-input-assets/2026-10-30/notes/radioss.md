# Radioss / OpenRadioss / OpenCourant 입력 생성 자산 조사

> **후속 보완:** [새 RAD 생성 자산](../followup/rad/GUIDE.md)과 [Gmsh native mesh writer](../followup/gmsh/README.md)를 추가 확보했다. 공식 카드 필드 규격은 이미 보유하고 있으며 실제 reader/default·writer·MIT 자작 완전 모델까지 연결했다. 아래의 초기 조사 한계 중 “NC-free 완전 작은 모델 미확보”는 column 입력쌍 범위에서 해소됐다. 우리 제품의 전수 생성 구현과는 구분한다.

2026-10-30. 이 기록은 실제 자료 수집과 관련 규칙 독해의 결과다. `caelab-prep`에 신규 RAD 생성기 또는 전 keyword 편집기를 구현했다는 뜻이 아니다. 공용 CAE 자산의 첫 적용 대상으로 OpenRadioss/OpenCourant를 조사했으며, 다른 solver에 같은 default·ID·node 순서를 강제하지 않는다.

## 확보 범위와 판 고정

| 축 | 고정한 대상 | 실제 확보·확인 |
|---|---|---|
| 주 문서 색인 | Altair Radioss 2024 Starter/Engine | Starter 590 + Engine 235 = **825 원문 색인 행**. CSV/JSONL, 원문 URL과 source ID 보유 |
| 상세 원문 | 위 색인의 중복 제거 URL | **804/804 HTML**, 총 **91,098,178 bytes**, 실패 0. 전문은 분석용 `tmp/radioss/keywords2024/`만 보존 |
| 관련 규칙 | 일반 syntax/file/include 절 + 33개 선택 keyword | 관련 절과 SH3N/SHELL/TETRA4의 node/축 그림을 실제 읽고 32개 규칙과 Q01–Q12 연결. 전체 field 독해는 아님 |
| 과거 문서 | 공식 Radioss 2022 Reference Guide PDF | **48,136,101 bytes / 3550쪽**, SHA 기록. `copy=no`라 텍스트 추출하지 않고 허용된 출력으로 **40–41쪽만** 시각 독해 |
| 비교 문서 | 조회 시 current banner Radioss 2026 | Starter 614 + Engine 241 = **855행** 비교 목록과 추가/제거 label 차이. 주 2024 분모와 합산하지 않음 |
| target source | OpenCourant `latest-20261011` | commit `cb760c206e346eff12161a2268b134ef9d48a4ef`; source ZIP **47,436,970 bytes**, 10,563개 파일 원본 취득 |
| converter source | OpenCourant Tools | commit `1b6bb9200ee7dca899e61c18bd982c3fb1c72fd1`; MIT `inp2rad.py` 원문·README·85함수 정적 목록 보유 |
| 실제 실행 | Starter/Engine·converter·QA verifier | **실행하지 않음**. `runtime_verified=false`, `binary_tested=null` |

문서 edition, `/BEGIN` Invers, Engine `/VERS`, source commit, binary build는 별도 판 축이다. 선택한 OpenCourant source reader의 기본 profile은 2026이고, Tools converter 기본 출력판은 2025이며 CLI 선택은 2023/2025다. 이들을 2024 문서와 같은 버전으로 부르지 않는다. 관찰한 현재 main `843b3c457d575dfb22ddca14c95644e2861636fd`도 위 target release pin을 대신하지 않는다.

## 전체 목록의 의미와 재현

`catalogues/radioss.csv`와 `.jsonl`은 공식 Supported Keywords 섹션의 **모든 링크**를 추출했다. Starter 590행/577상세 URL, Engine 235행/227상세 URL이며 미파싱·동일 이름+URL 중복은 0이다. 같은 상세 페이지를 공유하는 그룹은 Starter 11개, Engine 1개다. 원문 Engine의 `FTFILE`은 `/`가 없는 label이고 `atfile_engine_r.htm`으로 연결된다. 그대로 남겼으며 임의의 canonical keyword로 고치지 않았다.

따라서 **825행은 정규화된 독립 keyword 825개나 구현된 지원 825개가 아니다.** family·variant·option·별칭이 섞인 원문 색인 행이다. 의미별 alias 정리와 모든 field의 조건부 전개는 미완료다. 각 행의 `solver_support`는 `not-verified`다.

`catalogues/radioss-detail-acquisition.json`은 804개 원문의 URL·상태·크기·SHA256·독해 깊이를 기록한다. 선택 keyword 33개 + 색인에 연결된 `#include`/`#enddata` 2개 = **35개 상세 페이지**만 `relevant-sections`이고 나머지 **769개는 `not-read`**다. CSV도 관련 절 독해35행/색인만790행이다. 별칭 중복 때문에 33과35가 다른 것이 아니다. syntax/files/single-file 등 일반 절은 별도로 기록한다. HTML 다운로드 성공을 전 field 검토로 세지 않는다. 취득기는 6동시성, 자동 재시도 없음, 403/429 시 중지 방식이며 이번에는 해당 제한이 발생하지 않았다.

`scripts/radioss_catalogue.py`, `radioss_keyword_pages.py`, `radioss_fetch.py`는 조사 추출/취득용이다. `radioss_compile.py`는 확보한 원본과 검토 기록으로 원장을 조립한다. solver 또는 generator를 실행하는 코드가 아니다. 2026 비교 차이는 Starter +24/제거0, Engine +10/제거4 label이며 필드 호환성이나 target 지원 차이로 확정하지 않는다.

## 생성 시 보존해야 할 확인된 규칙

원장 `solvers/radioss.json`의 32개 규칙에 source ID와 실제 절을 연결했다. 다음은 구현 의미를 바꾸는 대표 사례다.

- Starter/Engine와 통합 파일은 헤더·구간·종료 규칙이 다르다. Engine include를 Starter include와 같은 기능으로 취급할 수 없다.
- 고정 열, Boolean 특수 위치, 예약 공란을 보존해야 한다. 공란·0·실제0·상속은 field별 의미가 다르다. 일반 integer 설명의 9자리와 일부 keyword ID의 10자리 표기도 target reader 검증 전에 단일 상한으로 합치지 않는다.
- `/BEGIN` 입력 단위와 작업 단위는 다르다. Starter가 변환하며 Engine은 변환하지 않는다. converter의 고정 Mg/mm/s를 자동 단위 판단으로 볼 수 없다.
- `#include` 상대 경로는 작업 디렉터리 기준이고 whole block만 포함한다. parameter expression은 앞선 정의와 외부 templex 의존이 있으며 OpenCourant 배포의 가용성은 미검증이다.
- `//SUBMODEL`의 namespace별 offset은 Engine 참조 ID에도 반영된다. node-group transform은 좌표만 바꾸므로 초기 상태·재료 방향·BC의 완전 변환과 다르다.
- 요소 family ID 고유성, TETRA4/BRICK/TETRA10의 part 분리, connectivity·normal·퇴화 제한을 따로 보존해야 한다. INP C3D4를 TETRA4로 바꾸는 converter도 `[0,2,1,3]` 순서를 사용한다.
- PART material/property 공유, composite ply 예외, group의 정렬 보존, surface 부호에 의한 normal 반전이 있다. 모든 모델 객체를 단순한 ID 목록으로 줄일 수 없다.
- CLOAD는 node당 하중이며 group 전체 합력과 다르다. BCS 자유도 코드, initial velocity의 종류, curve/sensor/skew와 접촉의 조건부 추가 행도 분리해야 한다.
- RUN 최종시간, implicit increment, 출력 간격, binary restart, solver 내부 STOP, 외부 process cancel은 별도 상태다.

공식 2024 Engine 설명은 `/VERS`를 의무로 규정하지만 일부 공식 QA와 Tools 출력에서는 생략된다. 이를 문서 오류나 converter 오류로 즉시 단정하지 않고 target reader의 fallback/호환성 검증 질문으로 남겼다.

## 실제 코드 자산과 권리

| 자산 | 확인한 역할 | 범위·권리 조건 |
|---|---|---|
| Tools `inp2rad.py` | 일부 INP → RAD Starter/Engine text converter | MIT 원문·README·Copyright 동봉. 일부 keyword/suboption만 지원하는 beta, standalone 전 keyword native generator 아님. 실행하지 않음 |
| `radiossblk.cxx` | CFG 기반 reader front end | AGPL-3.0-or-later 원문과 license 동봉. profile 선택/ReadModel/offset 경로를 읽음. reader 파일 하나가 전체 semantic validator는 아님 |
| `mec_data_writer.cpp`, `mec_single_file_writer.cpp` | descriptor/CFG 기반 field/card/조건부 출력과 buffer | AGPL-3.0-or-later. 모델·descriptor·runtime에 의존하는 참고 원문이며 독립 빌드/제품은 아님 |
| `hm_cfg_files` | 버전 계층과 기계 판독 descriptor 후보 | Radioss 파일 **1333개**의 path/size/SHA 목록. **1331개에 OpenRadioss 한정 사용 및 변경 제공 조건**, 2개 미분류. CFG 원문은 배포하지 않으며 상위 AGPL을 덮어 적용하지 않음 |
| `verify_results.py` | Engine 출력 및 upstream `ref.extract` 회귀 비교 | AGPL-3.0-or-later 원문 동봉. 입력 생성기나 독립 물리 정답이 아님 |

`examples/radioss/NOTICE.md`와 `code-manifest.json`이 배포 코드의 원본 경로·commit·조건·SHA를 보존한다. descriptor 파일 수는 버전 override/상속을 포함하므로 keyword 수와 같지 않다. CFG interpreter를 완전히 분리·재사용할 수 있는지, 조건에 맞는지에 대한 승인이 확보됐다고 주장하지 않는다.

## 실제 예제와 기대값

고정 source archive에 QA 관련 **341개 파일/166 RAD**의 실제 bytes가 들어 있다. 원장은 모두 path/hash로 열거하며 **161개 파일의 CC BY-NC4.0 표시**와 나머지 미분류 180개를 구분한다. 모델의 공개 접근 가능성과 상업적 공용 자산 재배포 허용은 다르다. QA 모델·reference의 원문은 배포하지 않는다.

다섯 사례의 deck, Engine, include, readme, `test_files.json`과 `ref.extract`를 실제 내부 추출해 읽었다.

| 사례 | format / 주제 | 기대 자료의 성격 |
|---|---|---|
| COQUES3N/ct3a | BEGIN2019, SH3N/초기속도 | upstream 회귀 reference |
| INTERF/INT_25/tetra4 | BEGIN2022, TETRA4/접촉/파괴 | reference에 energy ERROR -27.0도 존재. 정상 물리 정답으로 포장하지 않음 |
| LOIS/LOI44/solides_8pt | BEGIN2017, BRICK/LAW44, 수치 단위 | version 혼합이 있는 upstream 사례 |
| FLUIDE_NEW/EBCS/INIV | BEGIN2019, ALE/EOS, Engine 3단계 | test_files가 지정한 run/restart와 reference |
| EOS/EOS_PUFF_2 | BEGIN2018, EOS/LAW4 | readme의 format2018 이후 RHO0 변경과 reference |

추가 Tools SDK `small_plast`는 실제 확보했으나 `/MAT/USER01`의 별도 user library가 필요하고 **deck header는 MIT가 아닌 CC BY-NC4.0**이다. 이를 범용 완전 해석 예제로 배포하지 않는다. 모든 사례는 `solver_executed=false`다. upstream reference는 관측 회귀 기준이며 새 generator 출력의 golden이나 독립 물리 검증은 아니다. 배포 허가가 분명한 NC-free 완전 모델 시험쌍 및 의도된 오류/expected diagnostic corpus는 아직 확보·분류되지 않았다. 자작 미실행 deck으로 이 공백을 대체하지 않았다.

## 현재 닫은 범위와 남은 공백

공식 전체 색인 추출·분모 대조, 해당 상세 원문 취득, Q01–Q12 관련 근거/부분/공백 분리, 실제 예제와 코드 역할·판·권리·해시 기록을 마쳤다. LS-DYNA 담당과 default·connectivity·include/transform의 반례를 교환했고 `discussion/dyna-rad-review.md`에 대조했다.

**전체 field 검토, 생성 schema 완성, 모든 keyword 구현, target Starter read/run은 모두 미완료다.** 고차 요소 전체/face 번호, ID namespace와 상한, 전체 property/material/contact/implicit/output 조합, NC-free 오류 시험 corpus와 runtime 호환성은 후속 구현 전 별도 완료 기준이 필요하다. 이 기록은 이전의 일부 기존-card patch metadata와 fixture를 전체 입력 생성 자산으로 혼동한 판단을 정정한다.

