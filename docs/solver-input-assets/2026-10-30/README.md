# CAE 솔버 입력 생성 자료 — 2026-10-30

공용 CAE 개발 자산과 솔버별 native 입력 자산을 확보하기 위한 조사다. OpenRadioss/OpenCourant는 첫 적용 대상이다. 기존 GUI 벤치마크·공용 기능 조사와 별개로 **실제 덱 생성의 구문·기본값·참조·파일 묶음·예제·코드**를 조사했다. DB·검색 체계는 다른 세션 범위다.

**자료 취득·목록 추출·관련 규칙 검토를 수행했다. 모든 필드의 생성 schema, 제품의 전수 keyword 지원, 상용 전처리기 동등성, solver 실행 검증은 완료하지 않았다.**

## 확보 범위

| 솔버/고정판 | 전체 목록과 분모 | 실제 취득 자산 | 상세 |
|---|---|---|---|
| Radioss 2024 / OpenCourant release 별도 고정 | Starter590+Engine235=825행, 상세 URL804개. 2026 비교855행은 별도 | 상세 HTML804개, 2022 Reference Guide3550쪽, cfg/QA inventory, MIT inp2rad 및 AGPL reader/writer 일부 | [노트](notes/radioss.md) · [원장](solvers/radioss.json) |
| LS-DYNA R17 | Vol I–III starred TOC1773행. heading/card/option257행 별도 | 공식 PDF3권7373쪽, PyDYNA kwd.json3685spec/12219card/69523field records, 공식 소개예제82 `.k` | [노트](notes/dyna.md) · [원장](solvers/dyna.json) |
| Abaqus 2025 | keyword600개, 별도 reader index600개 집합 일치 | 상세 HTML600개, 공식 `.inp`6개, MIT meshio/abqpy 관련 소스 | [노트](notes/abaqus.md) · [원장](solvers/abaqus.json) |
| CalculiX2.23 | HTML/TeX keyword143개 집합 일치 | 공식 manual·CCX/CGX source·test1511파일(입력638/ref855/기타18), MIT 예제11파일 | [노트](notes/calculix.md) · [원장](solvers/calculix.json) |
| Code_Aster17.5.8 / v17 manual | 실제Command268+VARIABLE helper1. Commands270파일과 manual270문서는 다른 분모 | 공식 manual41개, Cata/launcher/example338파일, AsterStudy69파일, 실제 `.comm/.export/.datg/.mmed` bundle | [노트](notes/aster.md) · [원장](solvers/aster.json) |
| OptiStruct2025 | Bulk597+I/O131+Subcase118+PARAMoption261=1107행 | 전체 상세 HTML1107개, 공식 ZIP3개 안의 `.fem`7개, BSD PyNastran 일부 | [노트](notes/optistruct.md) · [원장](solvers/optistruct.json) |
| MSC Nastran2024.2 | 전체 북마크2196개, 주요장 분류 entry1879행(그중Bulk924). 고유 keyword 수가 아님 | 공식 QRG3143쪽, BSD PyNastran 일부. NASA95 완전 예제·과거 output은 다른 판의 보조 자료 | [노트](notes/nastran.md) · [원장](solvers/nastran.json) |

각 수량은 서로 다른 단위이므로 합쳐서 ‘전 솔버 keyword 수’라고 쓰지 않는다. 별칭·변형·옵션·명령·schema card를 구별했다. PyDYNA schema와 R17 TOC의 불일치는 별칭/그룹/버전 차이가 섞여 있어 전부 미지원으로 분류하지 않는다. PyNastran reader whitelist429개도 writer나 두 상용 솔버의 지원표가 아니다.

## 찾아보는 순서

1. 위 표의 해당 솔버 노트를 읽는다.
2. `solvers/<key>.json`의 Q01–Q12 coverage에서 필요한 질문과 rule ID를 찾는다. 질문은 파일 역할, 구문, 단위, 조건부/default, include, namespace, 연결순서, 객체 매핑, 하중/접촉, 해석 제어, 예제/코드, 버전/검증이다.
3. 연결된 source ID의 공식 URL·판본·절/쪽/함수·read_depth를 확인한다. `catalogues/`는 전체 이름·locator와 추출/취득 대조 기록이다.
4. 다운로드 묶음의 `assets/`·`examples/`는 허용된 참고 원문 소스이며 제품 코드에 편입한 의존성이 아니다. 실행/이식 완료로 취급하지 않는다.
5. 구현 시에는 필요한 카드의 실제 필드/조건부/의존 규칙을 원문에서 확인하고, 기존 실행 단계에서 정한 범위·종료 조건으로 개발한다. 이 자료조사 때문에 완료한 다른 범위를 다시 열지 않는다.

`tmp/` 경로는 수집 시 분석용 원본 위치다. 공개 Git과 다운로드 ZIP에는 상용 매뉴얼·재배포 불명 예제 전문을 넣지 않는다. URL·고정 버전·locator·크기·SHA·취득 manifest를 보존해 다시 찾을 수 있게 했다. HTML 원본 전체를 영구 오프라인 배포했다고 표현하지 않는다.

공개 Git에는 자체 노트·원장·목록·취득 manifest·감사·재현 스크립트와 참고 source의 NOTICE/라이선스를 둔다. 허용된 참고 source/schema/example의 실제 파일은 별도 다운로드 ZIP에 있다. 원장의 `assets/`·`examples/` 파일 경로는 이 ZIP을 기준으로 하며, Git의 제품 source에 편입됐다는 뜻이 아니다. `index.html`은 ZIP을 풀어 브라우저에서 여는 전체 목록 진입점이다.

## 교차 검토 결론

- 같은 keyword/BDF/`.inp` 형식이어도 blank·zero·default, local ID, element 순서, step/case 활성 규칙은 달랐다. [교차 검토](discussion/dyna-rad-review.md)와 [BDF 대조](discussion/bdf-cross-review.md)를 참고한다.
- 공용 기반은 객체/참조/단위/선택/명령/파일 묶음을 관리하고, 솔버·버전 profile이 생성 구문·default·지원/검사 규칙을 소유해야 한다. 하나의 FE schema로 모든 솔버 의미를 강제하지 않는다.
- OpenCourant 본체의 AGPL을 cfg/QA/Tools 전체에 적용하면 안 된다. 제한된 cfg 고지, QA의 CC BY-NC, Tools의 MIT를 파일별로 분리했다. 해당 cfg/QA 원문은 공용 자유 재사용 자산으로 배포하지 않는다.
- 공식 예제/공개 writer/API 존재는 완전한 생성기 구현 또는 실제 실행을 대신하지 않는다. abqpy의 runtime 의존/stub, meshio의 mesh/set 범위, reader와 writer 차이도 기록했다.

## 현재 제품 상태의 정정과 개발 영향

caelab-prep의 기존 RAD 기능은 **기존 파일의 일부 지원 필드를 수정·저장·출력하는 시제품**이다. 완전한 새 Starter/Engine 생성기나 모든 keyword editor가 아니다. 기존 `Field` 메타데이터와 작은 회귀 입력을 근거로 ‘생성용 카드 메타데이터·시험자료 확보 필요가 낮다’고 판단할 수 없다. 그 판단은 철회하며, 이번 취득 자료가 그 공백의 조사 기반이다.

첫 적용에서는 원문 보존 편집과 새 카드/모델 생성을 구분한다. 새 생성 기능은 versioned field/default/conditional/reference 명세, 정상·오류·경계 예제, 생성→reader/solver 확인을 고정 범위별로 추가해야 한다. 이번 작업에서 기존 코드·GUI·mesher·solver 지원을 확대하지 않았다.

Workbench는 이 저장소에서 검증해 제공할 자산/API와 native 파일 묶음을 소비하며 프로젝트·실행 관리 소유권을 유지한다. 수집한 GPL/AGPL 소스를 가져오기 전에 실제 제품 결합 방식과 배포 의무를 따로 결정한다. 자료 ZIP의 참고 소스를 자동 제품 의존성으로 추가하지 않는다.

## 종료 상태

7계열에 대해 목록 분모/결손, Q01–Q12 근거/부분/공백, 예제/코드 역할·판본·조건, 실제 취득·해시를 기록했다. 담당자 교차토론, 독립 Astra 지적의 수정 확인, [통합 검증](validation.json)을 통과한 범위를 이번 자료 수집으로 닫는다. 전수 field review·신규 생성기·solver run은 별도 미완료 항목이다.

잔여 공백은 모든 조건부 필드/해석 조합의 전수 schema, 의도적 오류 예제와 실제 실행 oracle, 최신판 간 모든 차이, MSC2024.2 고유 완전 예제 및 일부 원문의 재배포 권리다. 접근 실패·불명확한 항목을 찾았다고 바꾸지 않았다.

[사전 합의](discussion/protocol.md) · [토론·통합 결론](discussion/synthesis.md) · [독립 감사 기준](discussion/astra-checklist.md) · [독립 감사 결과](discussion/astra-findings.md) · [자료 집계](summary.json)
