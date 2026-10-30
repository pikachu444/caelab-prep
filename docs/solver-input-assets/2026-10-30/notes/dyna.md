# LS-DYNA 입력 생성 자료 — 수집 결과와 한계

2026-10-30 기준. 이 기록은 생성기 구현이나 LS-DYNA 실행 완료 보고가 아니다. 공식 매뉴얼 실물, 전체 목차, 실제 입력 deck, 재사용 가능한 schema/writer 소스를 확보하고 서로 다른 증거 수준을 분리한 결과다. 구조화 원장은 `solvers/dyna.json`이다.

## 고정한 버전과 실제 확보분

공식 Ansys 다운로드 페이지의 최신 정식 keyword manual **R17**을 선택했다. 수시 draft 및 더 오래된 v261/R16 웹 도움말은 정식 R17 원본의 대용으로 쓰지 않았다. 세 권 모두 표지 imprint가 `R17@e8334f9fb (06/11/26)`이고, 권별로 PDF 4,301 / 2,244 / 828쪽, 합계 **7,373쪽**이다. 공식 PDF를 실제 내려받아 바이트 수와 SHA256을 원장에 기록했다. 원문 전체를 읽었다는 의미는 아니다.

| 구분 | 실제 확보·대조 | 독해·검증 경계 |
|---|---|---|
| R17 Vol I–III | 세 권 PDF 원본, 전체 TOC 추출 | `catalogues/dyna-read-sections.json`의 관련 절만 독해 |
| 전체 TOC | 2,030행: starred 1,773 + 기타 heading/card/option 257 | 개별 option 조합 전개를 뜻하지 않음 |
| starred keyword/family | I 1,016 / II 366 / III 391, 미파싱 0 | 58 family heading과 literal 중복 23행 포함 |
| 재료 alphabetic companion | 362행, numeric alias 또는 범위 표기 345행 | 범위를 임의 개별 keyword 수로 확장하지 않음 |
| 공식 Intro 예제 | 실제 `.k` 82개가 든 ZIP, 전 파일 목록·SHA256 | v971/2013 자료이며 R17 실행 증거 아님 |
| PyDYNA schema | 3,685 raw specs / 12,219 cards / 69,523 fields | 전수 의미·의존관계 검토 아님 |
| PyDYNA source | commit 고정 MIT 파일 36개, 23,271,877 bytes | 설치·import·test·deck 생성·solver 실행 안 함 |

원본 매뉴얼과 공식 예제는 `tmp/dyna/`에서 분석했고 재배포 허가를 찾지 못해 공개·다운로드 묶음에서 제외한다. 원장 URL·버전·바이트 수·해시로 다시 취득할 수 있다. PyDYNA는 `90270f787216c91a969d6b477aaf753d45556035`의 **0.13.dev0 개발 소스**다. 별도 최신 stable release v0.12.1의 사용 문서·배포판과 같은 것으로 부르지 않는다.

## 전수 색인과 locator 검증

`catalogues/dyna.csv`는 별표로 시작하는 공식 TOC 행 1,773개를 전부 보존한다. `dyna-toc-all.csv`는 비별표 카드·옵션·부록 제목까지 포함하는 2,030행이다. 모든 starred 행의 PDF target header를 대조했고, footer가 추출되지 않은 21행은 인접 folio offset과 정확한 keyword header를 함께 확인했다.

공식 TOC 자체의 쪽수 오류도 두 건 발견했다. 원문 쪽수를 덮어쓰지 않고 불일치와 실제 locator를 분리했다.

| 항목 | 원문 TOC | 실제 target |
|---|---|---|
| `*BOUNDARY_ELEMENT_METHOD` | 5-1 | Vol I PDF 859, printed 6-1 |
| `*COMMENT` | 7-1 | Vol I PDF 875, printed 8-1 |

색인 분모에는 family 제목, 옵션이 생략된 generic 이름, 반복 literal 이름이 섞인다. **1,773은 완전히 전개된 모든 native variant의 수가 아니다.** 재료 별칭 362행이나 raw schema 3,685개를 더해 지원 keyword 수를 부풀리지 않는다. 전수 field 조사, 전수 variant 전개, 구현, solver 검증은 각각 미완료다.

## 가져다 쓸 수 있는 schema와 writer

`assets/dyna/pydyna/codegen/kwd.json`은 22,287,505-byte 원본 전체다. 추려낸 소수 카드가 아니다. 보정용 `manifest.json`, 추가 행용 `additional-cards.json`, 생성 class 매핑과 실제 writer 소스도 보유했다. root LICENSE, pyproject의 MIT 선언, Python SPDX 고지 및 경로별 다른 LICENSE/NOTICE/COPYING 부재를 확인했다. 소스마다 원본 URL·revision·크기·SHA256은 `assets/dyna/pydyna-source-inventory.json`, 배포 조건과 범위는 동봉 `LICENSE`/`NOTICE.md`에 있다. 큰 JSON은 다운로드 참고 묶음용이며 public Git에는 넣지 않는다.

공식 R17 starred TOC와 raw schema를 **문자 그대로** 비교한 결과는 1,544행 일치, class map과는 1,561행 일치다. raw schema와 일치하지 않는 229행을 `dyna-toc-schema-differences.csv`에 전부 남겼다. 이 가운데 family heading 57행, 명시적인 generic 표기 1행, class map만 exact 일치 7행, 의미 검토가 필요한 164행으로 분류했다. **229개가 미지원이라는 결론은 아니다.** 반대로 이름 일치는 fields·defaults·변형·release 적합성을 입증하지 않는다. schema가 어느 manual release로 만들어졌는지도 이 snapshot에서 명시되지 않는다.

PyDYNA `Deck.write`/`export_file`는 실제 text writer다. `KeywordBase` → cards → field writer로 내려가고 폭·공백·수치 쓰기는 hollerith 등에 의존한다. 그러나 이번에 묶은 일부 source만으로 독립 설치 가능한 패키지를 구성한 것은 아니다. 또한 deck이 raw string을 담을 수도 있고, `validate=False`가 기본값이며, 등록된 validator가 전체 물리·참조·R17 적합성을 검사하는 것은 아니다. include 전개는 미해결 파일을 보존할 수 있고, 기본 strict=False는 일부 파싱 실패를 raw text로 남긴다. reader가 파일을 보존했다는 사실과 schema 기반 생성 지원을 같은 것으로 세면 안 된다.

## 생성 시 놓치면 안 되는 실제 규칙

Q01–Q12 각각에 원장 rule을 연결했다. 공통 개념만 읽고 모든 keyword를 조사했다고 하지 않도록 정확한 PDF/printed locator와 누락 범위를 붙였다.

- **형식과 기본값:** Vol I 2-29–2-31/PDF 395–397의 free/long 규칙과 12-320/PDF 1646의 implicit 반례를 읽었다. long 폭은 integer 범위 보장이 아니다. `CONTROL_IMPLICIT_GENERAL`의 zero는 실제 0이고 blank는 DYN/SPR base 값 상속이므로 전체 카드에 “0=기본값”을 적용하면 틀린다.
- **참조와 scope:** Vol I 27-3–27-8/PDF 2977–2982 및 27-50/PDF 3024는 include·transform·경로를, 36-2–36-5/PDF 3576–3579는 parameter 선행 정의와 LOCAL scope를 설명한다. 동일 숫자의 NID/PID/MID/SID를 하나의 전역 ID로 통합하면 안 된다.
- **메시와 객체:** Vol I 19-99–19-124/PDF 2715–2740에서 shell/solid field와 Fig19-31의 실제 그림을 확인했다. 고차/퇴화/방향·반복 node 표기는 solver 전용이다. part→section/material/EOS/hourglass 및 set/segment 구별도 별도로 남겼다.
- **하중과 상태:** SPC·prescribed motion·contact·CID·curve·initial velocity·node/segment load 관련 선정 카드의 참조와 조건부 행을 확인했다. 전체 접촉 알고리즘이나 DOF 활성 조건 전수 표는 아직 없다.
- **restart와 중지:** Vol I 49-1–49-3/PDF 4007–4009의 simple/small/full restart와 2-19–2-23/PDF 385–389의 sense switch를 읽었다. small restart의 허용 명령/ID 집합, dump 파일 역할, MPP Ctrl-C 조건을 제품의 “저장”이나 외부 process kill로 대체할 수 없다.

위 목록은 전수 field 명세가 아니다. 특히 Vol III는 전체 index만 확보했고 multiphysics 개별 field는 대부분 index-only다. native encoding, 모든 namespace 범위, 모든 고차 face 표, 모든 thermal 단위 문맥 등은 실제 지원 keyword를 구현할 때 원문을 더 읽고 규격으로 내려야 한다.

## 예제의 역할과 정답 근거

공식 Intro manual은 2013 draft, v971 및 double precision 조건을 명시한다. ZIP의 예제 1(ELFORM16 shell)과 3(ELFORM-1 solid)은 메시·part·section·material·implicit 하중/제어가 있는 실제 deck이며 원본을 직접 살펴봤다. 문서의 수치 비교 표도 해당 모델/단위/후처리 조건과 함께 원장에 연결했다. 응력의 nodal extrapolation/averaging 조건은 solver 결과 그 자체와 구분해야 한다. 이번 수집에서 재현한 정답이 아니다.

MIT `.k` fixture는 `examples/dyna/pydyna/tests/testfiles/`에 실제 파일로 담았다. global/local parameter include 의존 파일도 함께 보존했다. undefined parameter 예제는 원문 참조를 유지하는 write와 값으로 쓰는 write의 차이를, transform 예제는 연결·ID 변환 시험을 조사하는 자료다. `standard/base.k`는 section/material=0인 parser fixture라 완전 해석 benchmark가 아니다. Taylor Bar Python 예제도 보유하지만 mesh를 외부에서 내려받으므로 자체 완결 모델로 분류하지 않는다.

## 다시 찾고 재현하는 순서

1. 지원하려는 keyword를 `catalogues/dyna.csv`와 `dyna-material-aliases.csv`에서 찾고 원문 PDF locator를 확인한다.
2. `dyna-pydyna-schema.csv` 및 `dyna-toc-schema-differences.csv`로 raw schema/class 이름 차이를 확인한다. 이름이 없다고 즉시 미지원으로 확정하지 않는다.
3. `solvers/dyna.json`의 Q별 rule·limits와 실제 source 경로를 읽고, native field 정의와 variant 조건을 대조한다.
4. 검증할 모델의 완전성·버전·단위·예상 결과 출처를 선택한다. fixture와 해석 benchmark를 구분한다.

`scripts/dyna_acquire.py --vendor-downloads`는 공식 원본을 분석용 tmp로 다시 취득한다. PDF 텍스트는 `pdftotext -layout`으로 생성한 뒤 `scripts/dyna_catalogue.py`를 실행한다. `dyna_package.py`는 허용된 MIT source만 보존하고 vendor 예제는 목록만 만든다. `dyna_manifest.py`는 조사 원장을 재생성한다. 모두 자료 조사용 스크립트이며 새로운 solver deck 생성기나 지원 구현이 아니다.

이번 수집의 종료 조건은 실물·전체 색인·정확한 locator·Q01–Q12의 근거/공백·예제/코드의 역할·버전/권리·추출 대조 기록을 갖추는 것이다. **전수 native 생성과 solver read/run 완료는 종료 조건을 만족했다고 보고하지 않는다.**
