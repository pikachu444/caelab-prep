# OptiStruct 2025 입력 생성 자료

2026-10-30 조사. 이 문서는 자료 확보 결과다. caelab-prep의 OptiStruct 지원 또는 완전한 `.fem` 생성기 완성을 뜻하지 않는다.

## 실제 확보

- 공식 2025 Bulk 597행, I/O 131행, Subcase 118행, PARAM option 261행: 총 1,107개의 서로 다른 URL을 색인에서 추출했다. Bulk card와 PARAM option을 같은 종류의 keyword로 세지 않는다.
- 4개 child-link 영역의 모든 strong anchor를 추출하고 중복을 검사했다. PARAM의 navigation 1개는 제외했다. 별도의 독립 공식 숫자 분모는 없으므로 추출 근거와 원본 해시를 남긴다.
- 전체 상세 HTML 취득의 성공/실패는 `catalogues/optistruct-pages.json`을 따른다. 다운로드는 독해가 아니다. 개별 원장 source가 지정한 관련 절만 읽었다.
- BSD-3-Clause PyNastran의 writer/숫자 formatter/reader/solid 작성 시험 소스 8개를 실제 취득하고 LICENSE와 NOTICE를 함께 보존했다. 전체 의존 패키지를 설치하거나 실행하지 않았다.
- 공식 완전 예제 취득 결과와 의존 파일은 `catalogues/bdf-examples.json`을 따른다. 상용 원본은 분석용이며 배포 묶음에는 들어가지 않는다.

## 생성에 직접 영향을 주는 확인 사항

`solvers/optistruct.json`의 Q01–Q12와 source ID가 근거를 연결한다. Bulk와 I/O/Subcase는 구문·약어·연속행 규칙이 다르다. 숫자 ID, part-qualified 참조, 일부 카드의 string label도 구분해야 한다. 일반적인 단위 일관성과 특수한 CMS/flexbody 변환을 섞지 않는다.

CTETRA의 PID 공란은 EID로 해석된다. MAT1은 E/G/NU 공란의 조건부 계산을 가지므로 모든 공란을 0으로 채울 수 없다. SPC에는 구조·열·전기 물리별 DOF 제약이 있고, FORCE의 follower 옵션은 회전자유도 조건이 있다. CONTACT의 AUTO는 명시 동적 해석 조건을 가진다.

INCLUDE는 삽입 위치·검색 순서·포함 파일 기준 상대경로·filemap·-incpath·압축 파일 처리를 보존해야 한다. RESTART I/O는 최적화 `.sh` 상태용이며 analysis mode용이라고 쓰면 틀린다.

## 재사용과 한계

공용 기반에는 참조 그래프·namespace·단위·파일 묶음·숫자 표현을 담을 수 있다. 실제 기본값·조건부 필드·지원 카드는 버전이 고정된 solver profile에 둬야 한다. 공용 schema가 같은 이름을 발견했다는 이유로 기본값까지 공유하면 안 된다.

PyNastran reader의 429개 whitelist는 writer 지원표나 OptiStruct 2025 전수 지원표가 아니다. 1,107개 색인 확보 역시 필드 schema, 새 모델 생성, solver read/run의 완료가 아니다. 전수 field 검토와 실제 실행은 모두 false다. 고의 오류 deck과 실행 결과 oracle도 아직 확보·검증하지 않았다.

원문 경로는 `tmp/` 분석 환경 기준이다. 배포물에는 공식 URL·버전·locator·크기·SHA 및 자체 조사 기록을 남기며, 상용 문서 전문을 재배포하지 않는다.
