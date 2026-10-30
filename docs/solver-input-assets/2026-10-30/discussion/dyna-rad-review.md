# LS-DYNA–Radioss 입력 생성 자료 교차 검토

2026-10-30. LS-DYNA 담당과 RAD 담당이 각자 확보한 원문·코드를 바탕으로 반례를 교환했다. DYNA 담당은 RAD의 syntax, TETRA4, include, transform 관련 확보 텍스트와 `inp2rad.py`의 해당 코드를 추가로 읽었다. 이 검토에서 새 solver 실행이나 generator 구현은 하지 않았다.

## 코드의 실제 역할

LS-DYNA의 PyDYNA는 실제 `Deck.write`/`export_file`와 keyword/card/field writer를 가진다. 따라서 writer 후보라는 표현은 근거가 있다. 다만 현재 보유한 source subset은 설치 가능한 전체 패키지가 아니며, raw string 보존·기본 `validate=False`·기본 strict=False 때문에 파싱/출력 성공을 모든 keyword의 schema/의미 지원으로 세면 안 된다. raw schema 3,685개와 공식 R17 TOC 1,773행은 분모가 다르다. 전체 field/variant/R17 적합성과 solver 실행은 미검증이다.

- 원문: [PyDYNA `deck.py` 고정 commit](https://github.com/ansys/pydyna/blob/90270f787216c91a969d6b477aaf753d45556035/src/ansys/dyna/core/lib/deck.py), `append` 114행, `_expand_helper` 255–317행, `expand` 319–349행, `write` 422–464행, `export_file` 648행 이후.
- 관련 자산: `assets/dyna/pydyna/`, `catalogues/dyna-toc-schema-differences.csv`. 일치하지 않는 229행은 미지원 229개로 단정하지 않는다.

RAD의 `inp2rad.py`는 Abaqus 계열 INP의 일부 구문·요소·재료·하중 등을 RAD로 변환하는 **converter**다. `convert_elements`는 입력 타입을 명시적으로 분기하며, C3D4 재배열과 C3D6 퇴화 변환은 단순한 keyword 철자 교체가 아니다. converter가 다루지 않는 모든 RAD keyword를 자유롭게 생성하는 standalone native generator라고 부를 수 없다. OpenCourant solver-reader, HyperMesh cfg, converter, QA deck도 각각 역할이 다르다.

- 원문: [OpenCourant Tools 고정 commit](https://github.com/OpenCourant/Tools/blob/1b6bb9200ee7dca899e61c18bd982c3fb1c72fd1/input_converters/inp2rad/inp2rad/inp2rad.py), `convert_elements` 2947–3215행 및 `write_output` 6202–6721행. 구체 지원 분기와 원장: `catalogues/radioss-inp2rad-functions.json`.

## 의미를 보존해야 하는 세 가지 반례

| 주제 | LS-DYNA에서 확인한 사실 | Radioss에서 확인한 사실 | 공용 자산의 경계 |
|---|---|---|---|
| 형식·blank·zero·default | R17 Vol I `CONTROL_IMPLICIT_GENERAL` printed12-320/PDF1646: zero는 실제0이며 DYN/SPR의 blank는 base 값 상속. GS2-29–31/PDF395–397: free/long은 폭과 카드 규칙이 별도 | 공식 2024 syntax의 Default Values/Integer–Real: 일반적으로 blank/zero가 해당 keyword default 활성. 기본값0이 아닌 real에서 zero를 그대로 표현하는 문제도 명시. 고정 block 형식 사용 | 저장된 “미입력”과 수치0을 구분하고 solver/card별 default 규칙을 적용한다. DYNA long이나 comma 구문을 RAD에 그대로 적용하지 않는다 |
| ID·connectivity·part | R17 Vol I `ELEMENT_SOLID`19-119–124/PDF2735–2740: 고차 추가행·반복 node 퇴화 패턴·방향이 정의됨. Fig19-31 실제 그림 확인 | `/TETRA4` Comments/Fig1: element-family별 ID 고유성 및 BRICK/TETRA10과 다른 part_ID 요구. converter C3D4는 `[0,2,1,3]`으로 node 재배열, C3D6는 degenerate BRICK 경로 | 공통 요소명·node 수·숫자ID 동일성으로 입력 의미를 보장하지 않는다. 실제 solver별 순서·퇴화·namespace·part 제약을 별도 보존한다 |
| include·transform·control·restart | R17 Vol I INCLUDE27-3–8/PDF2977–2982 및 PATH27-50/PDF3024는 typed ID offset·경로 기준을 구분. Restart49-1–3/PDF4007–4009는 simple/small/full 경계가 있고 small restart에서 part ID set을 일반 node/element ID set처럼 쓸 수 없음. GS2-19–23/PDF385–389 sense switch와 외부 kill 구분 | `#include` Comments: cwd 기준 상대경로, whole blocks, 원본 버전 준수. `//SUBMODEL` Comments는 Engine 참조ID에 offset 적용. transform overview는 node group 변환이 좌표만 바꾸며 초기상태·재료방향·BC를 완전히 변환하려면 submodel 참조 필요 | “include 전개”, “geometry 이동”, “중지”, “저장”을 공통 함수 하나로 동등 취급하면 의미가 달라진다. 원본 참조/버전/상태 경계가 필요하다 |

정확한 공식 locator:

- [LS-DYNA R17 Vol I](https://lsdyna.ansys.com/wp-content/uploads/2026/06/LS-DYNA_Manual_Vol_I_R17.pdf): 위 표의 printed/PDF 쪽. 전체 manual은 분석용에만 있고 전문은 재게시하지 않는다.
- [Radioss 2024 Starter Keyword Syntax](https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/starter_keyword_syntax_r.htm): General format, Default Values, Integer/Real Input.
- [Radioss 2024 TETRA4](https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/tetra4_starter_r.htm): Definition, Comments, Fig1.
- [Radioss 2024 `//SUBMODEL`](https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/submodel_starter_r.htm): Comments와 Engine ID offset 설명.
- [Radioss 2024 `#include`](https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/include_starter_r.htm) Comments와 [Transformation Overview](https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/transforms_overview_starter_r.htm) Comments. 원문 SHA256은 RAD 취득 원장에 있다.

## 버전과 라이선스 분리

DYNA의 target 문서는 R17이지만 공식 Intro deck·정답은 2013/v971, PyDYNA source는 0.13.dev0 개발 commit이다. 세 축을 합쳐 “R17 실행 통과”로 보고하지 않는다. MIT로 공개된 PyDYNA code/schema와 상용 LS-DYNA binary 실행권도 구분한다. root LICENSE·pyproject·SPDX·경로별 예외 부재를 확인하고 허용된 snapshot에는 LICENSE/NOTICE를 동봉했다. 공식 manual/Intro ZIP은 공개 다운로드가 가능해도 재배포 허가가 확인되지 않아 분석용으로만 보존한다.

RAD 담당은 Tools converter의 MIT, OpenCourant solver의 AGPL, hm_cfg_files의 파일별 제한적 이용 문구, QA 다수 파일의 CC BY-NC를 분리했다. repository의 상위 license 하나만 보고 cfg/시험자료까지 같은 권리로 재배포하면 안 된다. RAD 주 catalogue 문서는 2024, target release는 `latest-20261011`/`cb760c206e346eff12161a2268b134ef9d48a4ef`, target reader default profile은 2026, converter default는 2025(선택 2023/2025)로 서로 다른 판 축이다. 공식 2024 문서의 `/VERS` 요구와 converter/일부 QA 파일의 차이는 runtime 호환성 질문으로 남긴다.

RAD 담당이 공동 문서의 세 반례와 라이선스/버전 구분을 재확인했다. 양쪽 모두 원문 alias·오자·generic family를 보존해야 하므로 “색인 행 수 = 정규화된 keyword 수”로 바꾸지 않기로 했다. RAD의 2024 detail HTML 804/804 취득과 33개 선정 keyword 관련 절 독해 역시 다른 깊이로 보고한다.

검토 결론은 두 가지다. 자료·전체 색인·원본 locator와 구현 참고 소스는 확보할 수 있지만 그것만으로 전체 solver 입력 생성 지원을 선언할 수 없다. 공용 CAE 모델에서 native 입력으로 내려갈 때 default·ID·connectivity·include·상태·버전 의미를 보존하는 규격과 검증이 따로 필요하다. 이 문서는 그 반례와 증거를 고정하며 구현·실행 완료를 주장하지 않는다.
