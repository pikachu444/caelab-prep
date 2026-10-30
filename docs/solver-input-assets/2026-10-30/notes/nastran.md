# MSC Nastran 2024.2 입력 생성 자료

2026-10-30 조사. MSC 2024.2를 고정했다. NX/Autodesk/NASA Nastran 또는 최신 MSC 판의 지원으로 일반화하지 않는다.

## 실제 확보와 목록 분모

공식 Quick Reference Guide 원본 26,543,810 bytes, 3,143 PDF pages를 실제 취득했다. SHA256은 `solvers/nastran.json`에 있다. 웹 PDF reader는 크기 제한으로 실패했지만 공식 파일 직접 다운로드는 성공했다. legacy HTML 응답은 JS shell이므로 본문 독해 증거로 쓰지 않았다.

PDF의 북마크 2,196개를 전부 보존했다. 이 중 주요 입력 장의 entry level을 분류한 목록은 1,879행이다.

| 종류 | 행 수 |
|---|---:|
| NASTRAN system setting | 154 |
| File Management | 22 |
| Executive | 20 |
| Case Control | 277 |
| Case option topic | 68 |
| PARAM | 414 |
| Bulk entry | 924 |

이것은 1,879개의 고유 keyword가 아니다. 같은 이름의 변형·옵션·주석 표시가 포함된다. Chapter7 item code, Chapter8 DOF, appendices와 실행 옵션은 전체 북마크에 남겼으며 별도 entry 목록으로 전부 정규화하지 않았다. 따라서 **전체 북마크 확보 / 범위가 정해진 entry 색인**으로 표시한다.

## 관련 절 독해와 교차 검토

구문, INCLUDE, SOL/Case, GRID/CTETRA/PSOLID, SPC/FORCE, 단위, 접촉, TSTEP 관련 실제 페이지를 읽었다. CTETRA의 순서 그림은 렌더링해 확인했다. 정확한 physical PDF page와 printed page는 원장 rule locator에 있다.

생성 시 SOL/CEND, Case 선택, BEGIN BULK/ENDDATA의 경계를 유지한다. INCLUDE는 중첩 최대10 및 행 길이72자 제한이 있다. 소형/대형/자유형의 숫자와 연속행 규칙도 별도다. GRID의 위치 좌표계 CP와 변위 좌표계 CD, property/material 참조를 합치지 않는다.

**MSC CTETRA PID는 필수**다. OptiStruct 2025의 PID=EID 기본값을 공유하면 잘못된 입력을 만들 수 있다. PSOLID의 재료·물리·SOL별 제한, SPC의 상호배타 DOF 집합, Case에서의 활성 선택도 단순 card 출력 이상의 의미 검증이 필요하다.

## 코드·예제와 한계

BSD-3-Clause PyNastran의 실제 writer/formatter와 reader/solid 작성 시험 일부를 취득했다. LICENSE/NOTICE와 pinned commit을 보존했다. reader whitelist429개와 writer 지원을 같다고 보지 않는다. 시험 소스는 전체 해석 입력·수치 oracle이 아니고 demo의 외부 ISat 모델도 이 묶음에 없다.

공식 완전 예제 취득의 성공/실패와 의존 파일은 `catalogues/nastran-examples.json`을 따른다. 원문이 공개되어 있어도 재배포 허용으로 단정하지 않는다. QRG 전문과 렌더링 이미지는 배포하지 않는다.

전체 필드·조건부·기본값 schema, 모든 해석별 restart/state bundle, 의도적 오류 예제, 최신판 차이와 solver read/run은 미완료다. 이 작업은 자료 취득과 관련 규칙의 문서 검토이며, 새 solver 지원 구현은 아니다.
