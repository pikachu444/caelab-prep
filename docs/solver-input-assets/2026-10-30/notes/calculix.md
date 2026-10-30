# CalculiX 입력 생성 자산 — 2.23

공식 저자 배포 사이트가 안내하는 CCX/CGX 2.23을 기준으로 조사했다. CCX 문서의 표지는 2025-10-19이고 PDF는 835쪽이다. PDF·HTML·TeX 매뉴얼, CCX source·test archive, CGX source를 실제 취득해 바이트 수와 SHA256을 기록했다. PDF 전문 독해가 아니라 HTML의 관련 절을 읽고 목록은 HTML/TeX로 전수 대조했다. 실제 solver·CGX·writer 실행은 하지 않았다.

## 전체 키워드 목록

`catalogues/calculix.csv`와 JSONL은 공식 `Input deck format`의 **143개 keyword subsection 전체**다. HTML의 별표 anchor 145개에는 앞/뒤 이동에 반복된 두 항목이 있어 이를 제거했다. 공식 TeX의 143개 별표 subsection 이름 집합과 전수 비교해 양방향 누락 0개를 확인했다. 각 entry에는 원문 이름·archive member·TeX label/행·해시·독해 범위를 연결했다. parameter/요소형/별칭을 별도 keyword 수로 부풀리지 않았다.

이 결과는 선택한 매뉴얼의 전체 색인을 확보했다는 뜻이다. **143개 keyword의 모든 옵션·조건부 행·조합을 생성 schema로 검증했다는 뜻은 아니다.** 이 구분은 JSON과 각 catalogue entry에 유지했다. 재추출 방법은 `scripts/calculix_catalogue.py`, 대조 결과는 `catalogues/calculix-reconciliation.json`에 있다.

## 생성 규칙과 다른 솔버와의 차이

Q01–Q12의 출처·규칙은 `solvers/calculix.json`의 R01–R16에 연결했다. `*ELEMENT`, material/section/set/surface, boundary/contact, step/restart/output의 원문과 해당 source를 대조했다. 입력의 자유 형식, 행 연속, model/step 문맥과 단위 책임을 구분했다. 화면의 폼을 흉내 내는 자료가 아니라 writer가 알아야 할 규칙을 찾는 조사다.

특히 Abaqus와 입력 모양이 비슷하다고 동일한 지원 범위로 보면 안 된다. CCX의 element·contact·output·explicit 선택은 자체 매뉴얼을 따라야 한다. 입력의 `*OUTPUT` 호환 카드가 Abaqus 출력 구조 전체를 지원한다는 근거는 아니다. shell/solid의 면 번호와 native 연결 순서도 별도다. 이 조사에서 실제 mesh 변환을 실행하거나 숫자 결과의 정확성을 입증하지 않았다.

## 예제와 코드의 실물

| 자산 | 실제 확보 | 사용·검증 범위 |
|---|---|---|
| 공식 2.23 test archive | 1511파일의 원본 archive와 파일별 manifest. `.inp` 638개, `.ref` 855개 | 전체 파일은 내부에 취득. 정상 solid/shell·contact·restart 쌍을 읽었다. 원본 결과는 이번 실행 결과가 아님 |
| Martin Kraska MIT 예제 | 고정 commit의 solid/shell `.inp`, CGX `.fbd`, `test.py`, README 및 support·LICENSE 11파일 | geometry/mesh 생성과 입력 템플릿의 관계를 확인. 단일 `.inp`는 include 파일을 CGX로 먼저 만들어야 함 |
| CGX writer | 공식 `write2aba.c` 원본·GPL 고지 | mesh 출력과 제한된 dataset 제어. 전체 143keyword의 범용 모델 writer가 아님 |
| CCX reader | 공식 `readinput.c` 원본·GPL 고지, 전체 source archive의 관련 함수 | include·전처리·읽기 순서 근거. reader를 generator로 세지 않음 |
| PrePoMax writer 후보 | 공식 master snapshot 원문 및 branch 응답을 읽음 | 모델→keyword tree→출력 경로를 확인. pinned 파일·LICENSE 요청은429로 실패해 정확한 commit-byte 대조와 편입 판단은 미완료 |

공식 test archive의 개별 예제 재배포 고지는 확인되지 않았다. 따라서 최종 배포에는 그 원본을 싣지 않고 URL·archive member·해시를 보존한다. 허용 조건을 확인한 MIT 예제와 GPL source만 각각의 notice와 함께 별도 참고 파일로 둔다. 이들이 CAELab Prep 제품 코드에 편입되거나 의존성으로 설치된 것은 아니다.

MIT 예제의 선택 원본 11파일은 `catalogues/calculix-mit-assets.csv`에서 고정 commit의 파일별 URL·로컬 경로·바이트 수·SHA256으로 찾을 수 있다. D09는 이 11파일의 실제 취득을 나타내는 aggregate이며, `local_file`은 개별 원문을 추적하는 manifest다. manifest 자체를 원본 예제 1파일로 바꿔 세지 않는다.

오류 입력 또는 expected-failure 예제는 선정·검토하지 않았다. 공식 test archive 전체를 취득했다는 사실만으로 음성 시험의 기대 오류와 판정을 확보했다고 볼 수 없다. 확인한 `beamperror`는 error estimator 예제이므로 의도적인 실패 입력으로 분류하지 않았다. 이는 Q11의 명시적인 공백으로 남긴다.

## 재사용할 때의 경계

공용 계약은 구조화한 field·대상·명령 결과를 다루고, CCX keyword/면 번호/step 규칙은 해당 adapter에 남겨야 한다. 원문의 지원 범위와 실제 reader, 외부 writer, 우리 제품의 지원 범위를 따로 관리해야 한다. 공식 test archive는 reference 후보이며, 새 writer가 생성한 덱을 CCX로 읽혀 검증한 결과와 구별한다.

MIT 예제의 `test.py`/`.fbd`는 외부 명령 실행과 파일 이동을 포함한 원본 스크립트다. 이번에는 실행하지 않았다. 재실행에는 CGX/CCX·Python 수치/plot 의존성·쉘 환경이 필요하며, 보유 템플릿만으로 설치형 앱이나 일반 모델 생성 기능이 완성되는 것은 아니다.

## 남은 범위와 종료

공식 전체 색인과 원본 archive 취득·해시·대조, Q01–Q12 관련 규칙·예외, 실제 예제와 writer/reader 역할·권리, 접근 실패까지 기록했다. 이 한정 수집은 닫을 수 있다. 전수 field/dependency schema, 모든 이름/번호 범위·인코딩 예외, Abaqus와의 모든 차이, 실제 writer 출력·CCX 읽기·수치 검증은 완료하지 않았다. 라이선스가 막힌 후보를 도입 가능 자산으로 확정하지 않았다.
