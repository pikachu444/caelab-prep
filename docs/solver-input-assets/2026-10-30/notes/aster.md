# Code_Aster 입력 생성 자료 수집

2026-10-30 기준. 이번 범위는 공식 전체 명령 목록·입력 형식 핵심 규칙·실제 source/검증 예제의 확보와 역할 판별이다. 생성기·GUI·solver 지원을 구현하거나 수치 실행을 완료한 상태가 아니다. 세부 원장과 source locator·읽은 범위·SHA256은 `solvers/aster.json`, 재배포 source의 파일별 목록은 `examples/aster/source-manifest.json`에 있다.

## 버전과 전체 목록 대조

| 축 | 확보한 범위와 판정 |
|---|---|
| Solver source | 공식 Code_Aster tag17.5.8, commit `c1f5c46ef795e0bf6d82a29dc20da30d281535ce` |
| Documentation | 공식 branch `v17`; 정확한 patch build는 별도 확인되지 않으므로 source17.5.8과 동일 문서로 단정하지 않음 |
| Commands source | 270 Python 파일 모두 실제 확보·AST parse, parse 누락0 |
| 실제 Command 정의 | OPER135 + MACRO116 + PROC15 + FIN_PROC1 + FORM1 = **268** |
| 별도 도우미 | VARIABLE1: `VariableSupport` 호출 객체, Command가 아님 |
| Bootstrap | `__init__.py`1; 전체270파일 =268 Command+1 helper+1 bootstrap |
| Source 사실 목록 | `catalogues/aster.csv` 269행=268 Command+VARIABLE1 |
| 공식 manual index | `catalogues/aster-manual-index.csv` 270 **문서**행/고유 locator270 |
| 두 집합의 대조 | source269 중 공식 색인 제목에 exact command-token match266. `IMPR_CORR_HOMO`, `LIRE_CORR_HOMO`, `VARIABLE`는 제목 exact match가 없음. 4문서는 여러 source command를 한 문서에서 설명하므로 문서 수와 command 수는 같지 않음 |
| 구문 노드 계수 | top-level Command 선언 호출 subtree에 직접 나타나는 SIMP12604 / FACT1130 / BLOC1530. 파일 내부 helper factory/function 정의와 공유 Commons factory의 확장을 제외한 lexical node 수이며 **고유 parameter 수·전수 검증 수가 아님** |

위 count는 같은 항목을 중복 집계한 합계로 보고하지 않는다. 추출 재현은 `scripts/aster_collect.py`(확보한 source의 offline AST 대조), `scripts/aster_manual_index.py`(분석용 공식 HTML index의 사실 locator 추출)로 한다. Python import/solver 호출은 하지 않는다.

## Q01–Q12 검토 결과

| 질문 | 실제 읽은 근거와 생성 시 보존할 내용 | 남은 경계 |
|---|---|---|
| Q01 파일·최소 구조 | U1.03.00 §1, U1.05.00 §3, run_aster/export.py: `.comm`은 Python 계산 프로그램, `.export`는 실행·파일 프로파일, MED는 별도 mesh/field 형식. 전통 DEBUT→mesh→할당→계산→출력→FIN 흐름을 확인 | 모든 물리·저수준 CA API 프로그램의 최소 입력을 생성한 상태는 아님 |
| Q02 문법 | U1.03.01 §3, U4.01.00, command_files.py: Python keyword arguments·`_F`·반복 tuple/list·주석·줄 연속·수치/문자열·UTF-8 전처리. .export P/A/F/R whitespace 행은 별도 문법 | 임의 Python의 graphical round-trip 보장 없음 |
| Q03 단위 | U4.44.01 §2.5, U4.43.01 탄성 절: 길이·힘·물성 일관성, 선/면/체적 하중, 축대칭 1radian 하중 주의 | 모든 물리별 단위/예외의 전수 표는 없음 |
| Q04 필수·조건·반복·기본값 | U4.01.00 §3–4, Cata Language: SIMP/FACT/BLOC·statut/typ/min/max/defaut/into·조합 rules와 실행 단계 검증을 분리 | 모든 conditional parameter, Commons 확장, compat_syntax 별칭·callback을 의미 평가하지 않음 |
| Q05 include·순서·외부 파일 | U4.13.01 §3, Export.parse: 프로파일 부모 기준 상대 경로, unit과 D/R/C, INCLUDE UNITE와 DONNEE 차이. 결과 concept은 사용 전 정의 | 중첩 include·임의 Python 외부 파일의 전체 조합 미실행 |
| Q06 이름·참조 | U1.03.01 §3, U3.01.00 §2, AsterStudy conversion QA: Python 변수·내부 typed concept·node/cell·group은 별도 namespace. 구형 ASCII mesh entity8자/group24자 규칙을 Python 변수에 일괄 적용하지 않음 | source17.5.8 모든 동적 명명/충돌 규칙 전수 검증 아님 |
| Q07 mesh·연결·방향 | U3.01.00 §4 요소/차수/방향 도표, U4.21.01 §3 MED group/family·형식 경계, U4.42.01 §10 local orientation을 확보·관련 절 독해 | 고차 요소의 모든 node permutation·퇴화 조합을 전사하거나 MED writer round-trip 시험하지 않음 |
| Q08 객체 할당 | U4.41.01 §3, U1.03.00 §3.4–3.5, U4.42.01: mesh topology와 modelisation/physical phenomenon/formulation, material, material field, element properties, group assignment 분리. 할당 순서의 덮어쓰기와 성분 잔존 보존 | 모든 modelisation/물성 조합이나 assembly 생성 구현 아님 |
| Q09 하중·구속·초기·접촉·곡선 | U4.44.01 Dirichlet, U4.44.11 §3.1–3.2, U4.53.01 §3.5/3.8, U4.31.02 §3.8–3.11, U4.42.01 §10: EXCIT/ETAT_INIT 구분, master/slave 그룹·외향 법선·분리 조건, 보간/외삽·frame 분리 | U2.04.04 접촉 방법론과 모든 contact formulation/조합 심화 검토가 남음 |
| Q10 제어·시간·재시작·출력 | U4.51.03 §4 pseudo time, U4.53.01 §3.19 explicit/implicit 조건, U7.05.21 §3 MED output/version/unit80. U4.11.03 §1: **v17 DEBUT도 base가 있으면 자동 이어서 실행**, POURSUITE는 호환 명령 | 외부 process cancel, 보존 base·ETAT_INIT/reuse, 출력 요청은 서로 다른 축. restart/cancel 실험 없음 |
| Q11 예제·writer·QA | 공식 sslv139a4파일 실물, Cata, run_aster, AsterStudy 실제 serializer/importer 및 정상·오류 QA code 확보 | converter 오류 시험은 solver 오류 시험 아님. source subset은 독립 writer SDK가 아님 |
| Q12 버전·지원·검증·권리 | source/documentation/AsterStudy revision 별도 pin, 원문 size/SHA/read-depth 기록. GPL 조건·원문 notice 보존; manual 전문 배포 제외 | 모든 field 의미·버전 차이·물리 타당성·solver read/run 검증은 완료 아님 |

## 실제 입력 bundle과 code의 역할

`examples/aster/upstream/astest/sslv139a.export`가 선언하는 `.comm/.datg/.mmed` 및 export 자체를 보존했다. MED는 510938바이트의 실제 binary이며 Git LFS pointer가 아니다. `.datg`는 Cast3M mesh 생성 스크립트이며 `.comm` 형식이나 INCLUDE라고 오인하면 안 된다.

`.comm`에는 축대칭 Fourier 모델의 mesh·group·재료·하중·좌굴 모드 계산과 TEST_RESU가 있다. 상류 CHAR_CRIT 기대값은 VALE_CALC=-848467.4364780696, 해석 reference=-8.49350940e05, PRECISION=2e-3이다. **이번 작업에서 관측한 수치가 아니다.**

| 자산 | 확인된 실제 역할 | 한계 |
|---|---|---|
| Cata Commands/Commons/Language 전체 | 명령 schema·type·factor·conditional block·조합검사 source | schema가 solver reader·완성 model writer·수치 검증기는 아님 |
| run_aster.Export.parse / __repr__ / write_to | `.export` 실행 프로파일 parser/writer | mesh→물리 모델을 `.comm`으로 생성하지 않음 |
| run_aster.command_files | import/coding line/interactive 실행용 명령 텍스트 보완 | 전체 CAE model generator 아님 |
| AsterStudy study2comm / ExportToCommVisitor | dependency 순서와 값/factor를 실제 `.comm` 텍스트로 직렬화 | `limit>0`는 display용 생략으로 invalid 입력을 만들 수 있음. 버전 Features와 의존성 필요 |
| AsterStudy Stage.export / Case.export→ExportCase | `.comm` 저장 및 case `.export`·의존 파일 export | common/SALOME/asrun 등의 dependency closure나 source17.5.8 호환 실행 검증 없음 |
| AsterStudy comm2study, test_conversion/test_export/test_include | importer, 정상 출력 비교, unsupported Python/오류 변환 QA | 임의 Python 모두 graphical 변환 가능한 것이 아니며 source QA도 실행하지 않음 |
| libaster, solver reader, MED writer/reader | 별도 실행·형식 계층 | 이번 source snapshot만으로 설치·운영·검증하지 않음 |

Code_Aster 원문338파일 약3.0MB와 AsterStudy 원문69파일 약0.8MB를 보관했다. 파일 개수는 자료의 충분성 판정이 아니다. 원문 file-level manifest와 라이선스는 `examples/aster/NOTICE.md`를 진입점으로 삼는다. 매뉴얼 HTML41개는 실제 취득해 SHA/크기/독해범위를 원장에 기록했으며 분석용 tmp에만 있고 공개 파일 묶음에 포함하지 않는다. 목차 취득과 관련 절 독해를 나눠 기록했다.

## 공용 자산에 주는 결론과 종료 경계

공용 모델의 identity/reference, mesh topology, modelisation/property assignment, load history, execution profile, file bundle, result request를 독립적으로 유지해야 한다. 단일 문자열 keyword deck이나 모든 솔버에 같은 part/step/ID/default를 강제하는 구조로는 .comm/.export/MED와 v17 restart 의미를 보존할 수 없다. solver profile이 각 native namespace·기본값·조건·파일 경계를 설명해야 한다.

이번 수집은 전체 목록의 실물/분모 대조, 12개 질문의 근거/부분/공백, 공식 예제/실제 writer source/권리/해시를 제공하는 데서 닫는다. **전수 conditional-field schema, 생성기 구현, 전체 키워드 제품 지원, solver 실행 검증은 미완료다.** 필요한 다음 개발은 선언한 target version과 기능 범위를 정한 뒤 해당 field 조건·mesh mapping을 구현하고 실제 read/run 회귀시험을 따로 수행하는 일이다. 수집한 자료가 그 시험의 통과를 대신하지 않는다.

## 수집 후 상호 토론 기록

2026-10-30 root·Abaqus 담당·LS-DYNA 담당과 다음 경계를 교차 검토했고 독립 Astra 감사에 원장을 전달했다. 아래 타 solver 사실은 해당 담당자의 조사 결과/원장을 참조하는 교차 검토 의견이며 이 Code_Aster 담당이 원문을 다시 전수 검증했다는 뜻은 아니다.

- Abaqus 담당은 mesh-only writer와 Abaqus runtime script를 독립 full generator라고 부르지 않는 경계를 공유했다. Code_Aster에서도 Cata schema, .comm serializer, .export writer, importer, libaster/runtime을 역할별로 나눴다.
- LS-DYNA 담당은 R17 `*CONTROL_IMPLICIT_GENERAL` Vol I12-320/PDF1646에서 blank가 base 상속이고 zero는 실제0인 예를 제시했다. small restart Vol I49-3/PDF4009는 node/element ID 기반 set을 재정의해야 하고 part ID set과 같지 않다고 확인했다. `*INCLUDE_TRANSFORM` Vol I27-3–8/PDF2977–2982는 entity별 ID offset과 단위 scale까지 다루므로 좌표 transform 하나로 대체할 수 없다고 확인했다. 근거 원장은 `solvers/dyna.json`이다.
- root는 `CTETRA`의 PID가 OptiStruct에서는 EID default, MSC Nastran에서는 required인 차이를 확인했다. 근거 원장은 `solvers/optistruct.json`, `solvers/nastran.json`이다.
- Code_Aster 담당은 명령/도우미/문서 수의 분모, .comm/.export/MED/mesh-provenance bundle, 별도 namespace, v17 DEBUT/base restart 의미를 제시했다. 자료 개수·source schema 확보가 모든 conditional field의 의미 검증이나 solver 실행을 대신하지 않는다는 경계를 맞췄다.

공통 결론은 공용 모델에서 값의 부재/명시0/기본값/상속, identity와 참조 scope, assignment 순서, 파일 bundle과 solver version을 보존하고 각 solver profile에서 native 규칙으로 내보내야 한다는 것이다. 단일 blank/default 규칙이나 ID 하나, 좌표 변환 하나, 단일 deck 텍스트만으로 공통화하는 설계는 이 근거들과 충돌한다. 이번 단계에서는 그 생성기를 새로 구현하지 않는다.

독립 Astra 감사에서 source57건과 upstream 원문407파일의 hash/size, source Commands270파일의 AST 분모, 목록269행, MED header/크기, export의 의존3파일을 별도로 대조했다. 구문 node 수의 범위를 전체 파일 AST가 아닌 top-level Command 선언 호출 subtree로 정밀화했다. 이는 solver·converter 실행 검증이 아니다.
