# Abaqus 2025 입력 생성 근거와 취득 상태

이번 범위는 **입력 생성에 필요한 근거 수집**이다. 독립 writer 구현·600개 keyword 지원·Abaqus 실행 검증은 하지 않았다. 근거 원장은 `solvers/abaqus.json`, 사실형 전체 목록은 `catalogues/abaqus.csv`다.

## 버전과 실제 취득

문서는 Abaqus **2025**, vendor가 작성한 문서를 호스팅하는 **Virginia Tech mirror**로 고정했다. 직접 Dassault 호스팅 원본과 같은 판본임을 별도로 비교한 것은 아니다. 공개 접근과 원문 재배포 권한은 구분한다.

| 확인 축 | 실제 상태 |
|---|---|
| 전체 keyword 목록 | browser 600행 = 600 고유 이름/상세 URL |
| 독립 대조 목록 | input reader 지원표의 이름/URL 600개와 집합 일치, 차집합 0 |
| 상세 원본 | 600/600 상세 페이지 실제 취득, 실패·error title 0 |
| 독해 | 공통 모델/문법/실행/element 절과 개별 keyword 15개의 관련 절 |
| 원장 | 45 source record, 생성 규칙 22개, Q01–Q12별 근거/공백 |
| 공식 입력 원본 | 6개 실제 `.inp` 취득. 작은 자족 4개 독해, 큰 1개 헤더 확인, 1개 외부 의존 확인 |
| 공개 코드 | meshio adapter/test와 abqpy compression example, 각 고정 revision·MIT 고지 동봉 |
| 실행 | solver read/run·예제 실행·생성 code 실행 모두 미수행 |

600은 keyword 단위 분모다. parameter/alias/element code/조건부 행 수가 아니다. CSV의 `read_depth`와 `full_field_review=False`를 보존했으므로 페이지 다운로드를 필드 독해로 바꿔 세지 않는다. GUI 지원표와 input reader 지원표는 **solver의 전체 옵션 지원 보증서가 아니다**.

원본의 URL·취득 경로·SHA256·바이트 수는 JSON과 `catalogues/abaqus-source-acquisition.jsonl`에 있다. 분석용 원문은 `tmp/abaqus/`에 있으며 공개 배포 묶음에서 제외한다. 목록과 manifest에는 이름·locator·취득 사실만 둔다. `scripts/abaqus_collect.py`는 표와 600개 페이지 취득을 재현하고, `scripts/abaqus_compile.py`는 조사 원장을 조립한다. 어느 스크립트도 해석기를 실행하지 않는다.

## 생성 시 놓치면 안 되는 경계

모델 블록과 step 이력, native element TYPE/순서/face, part/instance/assembly의 로컬 namespace, section↔ELSET↔material 연결을 별도 의미로 보존해야 한다. 공통 mesh만 쓰는 코드로 이 구조가 생기지는 않는다. 숫자 ID가 다른 part에 반복되는 것은 정상이며, `NSET, UNSORTED`는 순서 의미를 갖는다. 활성 자유도도 모든 node에서 항상 여섯 개로 고정되는 것이 아니다.

blank·0·행 생략을 구분해야 한다. keyword 연속과 data 연속의 조건도 다르다. `INCLUDE`는 job 제출 디렉터리 기준 경로와 최대 다섯 단계 중첩 규칙을 갖고, `PARAMETER` 변수는 일반 keyword와 달리 대소문자를 구분한다. 외부 입력을 읽는 즉시 원문에 삽입하는 의미를 보존해야 한다.

기본 단위는 일관 단위를 사용한다. 회전 DOF는 radian, 다른 각도는 degree라는 예외가 있다. `UNIT SYSTEM`이라는 옵션이 존재한다고 모델 값 전부가 자동 환산되는 것은 아니다.

Standard/Explicit, model/history, 일반/섭동 step, 출력 field/history, 직접 데이터/외부 파일/사용자 루틴 분기는 keyword에 붙는 조건이다. 접촉이나 초기조건은 이름 하나와 임의 행 몇 개로 완성되지 않는다. ODB 요청과 restart 저장도 다른 자산이며 외부 process 취소는 recover/restart와 동일하지 않다. 구체 규칙·절 locator는 JSON의 R01–R22에 연결했다.

## 실제 예제와 정답의 출처

| 예제 | 실제 확인 | 검증 기준과 한계 |
|---|---|---|
| `c2.inp` | 645B, B21 beam, material/section/BC/load/static step/output | 공식 fetch 예제. 수치 정답·실행 로그는 미확보 |
| `ec34sfs2.inp` | 1531B, 8 node/5 C3D4, surface/load/output 포함 | 공식 solid verification 설명의 응력·변형률·section force 기준. 당사 실행 결과 아님 |
| `ec38sfs2.inp` | 1542B, 8 node/1 C3D8, section output 포함 | 같은 공식 검증 절과 연결. 수치 실행 미수행 |
| `ei33sisc_surf.inp` | 3562B, C3D4 small-sliding contact | 간섭 제거·섭동·마찰 변경 검증 절과 연결. 정답 로그 미보유 |
| `block_c3d4_b_std_gcont.inp` | 416890B, 외부 파일 참조는 관측되지 않음 | 헤더와 참조만 확인. 전체 독해·수치 정답 확인 아님 |
| `boltpipeflange_3d_cyclsym.inp` | 127135B, node INPUT·substructure 참조 | 단일 파일만으로 완전 모델이 아님. 의존 원본 묶음 추가 필요 |

공식 `.inp`도 매뉴얼과 마찬가지로 재배포 허가를 확인하지 못했다. 따라서 결과물은 원문 URL·해시·독해 범위와 `abaqus fetch` 취득 경로를 제공하고, 원본 파일은 분석용으로만 보유한다. 공식 잘못된 입력 덱과 예상 오류 로그는 확보하지 못했다.

## 공개 코드의 실제 사용 범위

| 자산 | 고정 revision | 가능한 역할 | 부족한 것 |
|---|---|---|---|
| meshio `_abaqus.py` | `b2ee99842e119901349fdeee06b5bf61e01f450a` | mesh와 node/element set reader/writer, INCLUDE reader | 재료/section/step/BC/load/contact/output full writer가 아님. variant→공통 cell type 변환의 정보 손실, 상대 package import 의존 |
| abqpy 2025 compression example | `3088e9fc3b77da615a586524c0cb407b3d0acc48` | Abaqus API 모델→writeInput workflow 예 | 공개 `ModelJob.writeInput` 본체는 `...` stub. 실제 입력 작성은 설치된 Abaqus runtime에 의존 |

MIT 허용 파일만 `examples/abaqus/`에 해당 LICENSE와 NOTICE를 함께 넣었다. meshio 시험용 원 mesh 파일의 별도 vendor/대학 출처는 MIT 소스로 일괄 간주하지 않고 제외했다. abqpy compression 예제에는 `job.submit`도 있으므로 취득·독해만 했고 실행하지 않았다.

## Q01–Q12 종료 상태와 남은 일

| 질문 | 확보한 관련 근거 | 아직 안 된 것 |
|---|---|---|
| Q01 | model/history, Standard/Explicit, step, 공식 작은 덱 | 모든 procedure의 최소 덱 |
| Q02 | ASCII/행/쉼표/연속/주석/숫자·label 규칙 | 특수 binary·외부 사용자 IO |
| Q03 | 일관 단위·각도·전송 단위 | 전체 property 차원 사전 |
| Q04 | blank/default·탄성·section·초기조건 분기 | 600 keyword 전 필드 schema |
| Q05 | include·경로·중첩·parameter | 모든 외부 형식 dependency resolver |
| Q06 | ID/name scope·중복·set 순서 | 모든 entity의 참조 선후·중복 표 |
| Q07 | 3D solid 연결/face·DOF·mesh 변환 한계 | 전체 element library의 고차/퇴화/face 표 |
| Q08 | part/assembly·material/section/set/surface | 전체 객체→native keyword 매핑 |
| Q09 | 구속/집중하중/초기조건/접촉/amplitude | 모든 multiphysics·접촉 활성 분기 |
| Q10 | 절차·restart·실행/검사·출력 구분 | 중단/복구/출력 실제 회귀 |
| Q11 | 실제 공식 덱·검증 절·MIT code | 잘못된 덱/예상 오류 로그, 독립 full writer |
| Q12 | 2025 고정·license·실행축 분리 | vendor-hosted 동일판 대조·실제 해석기 검증 |

이번 수집은 완전한 목록·관련 절·실제 예제·code 범위의 근거를 남기는 데서 닫을 수 있다. 이를 제품 개발 완료나 모든 필드 조사 완료라고 부르면 안 된다. 향후 writer 개발 단계는 필요한 procedure/element/material profile을 먼저 고정하고 native 입력과 원문 기대 결과를 비교하는 별도 종료 조건이 필요하다.

다른 담당과 교차 논의한 결과 **Abaqus `.inp`와 CalculiX `.inp`의 철자 유사성은 의미/지원 동치가 아님**을 확인했다. 예를 들어 CCX의 `*OUTPUT`·`*STATIC, EXPLICIT`·`*DYNAMIC` 옵션·접촉 타입 제약을 Abaqus 스키마로 대체하면 안 된다. 공통 문서 계약은 재사용할 수 있지만 solver별 실행 의미와 지원 범위는 유지해야 한다.
