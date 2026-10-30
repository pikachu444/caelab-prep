# OptiStruct 공식 완전 입력 예제의 추가 취득

2026-10-30. root가 지정한 한정 조사로 공식 OptiStruct 2025 예제 2묶음을 실제 취득했다. **ZIP 3개 안의 실제 `.fem` 7개**, 압축 해제 후 총 863,400바이트다. ZIP·페이지·개별 deck의 URL, 크기, SHA256, archive member와 검토 범위는 `catalogues/bdf-examples.json`에 있다. 원본은 모두 `tmp/opti-nastran/examples/`에만 둔다.

공식 페이지의 원래 모델 링크는 `majorv`/`minorv` placeholder다. 공식 `offlinecheck.js`의 `setupOfflineCheck`를 실제 읽어 `.wh_version`의 2025를 대입하고 HTTP를 HTTPS로 바꾸는 규칙으로 링크를 해석했다. 다른 경로나 버전을 추측한 다운로드가 아니다.

| 예제 | 실제 취득 | 검토한 입력 구조 |
|---|---|---|
| OS-V:0110 One Dimensional Transient Heat Transfer | `T3_a.zip`, `T3_b.zip`: CBEAM/Quad4/Quad8의 coarse/fine `.fem` 6개 | `ANALYSIS HEAT`, subcase, mesh/material/property, BC/load/table/time 제어, `BEGIN BULK`·`ENDDATA` |
| OS-E:9000 Piezoelectric Analysis of a Cantilevered Bar | `piezoelectric_analysis_bar.zip`: `.fem` 1개 | `ANALYSIS DTRAN` 2 subcase, solid mesh, MAT2PT/MATPZO/MAT9OR, MPC, 강제 전압/변위와 시간 제어 |

7개 파일에서 주석을 제외한 INCLUDE/ASSIGN/LOADLIB/RESTART 등의 외부 입력 파일 요청은 관측하지 않았다. 이는 파일 전체의 제한된 텍스트·의존성 검토 결과다. 완전한 parser 검사, solver read/run 또는 수치 검증을 뜻하지 않는다. 압전 예제의 두 번째 하중은 문서에서 첫 번째 결과로부터 만든 변위라고 설명하며, 배포 deck 안에 해당 표 자료가 들어 있다.

예제 제공 페이지와 모델 URL은 2025지만 T3 파일 header의 생성 도구는 HyperMesh 2017.1.0.19 / template 2017.1이다. 배포판, 원본 생성 도구, 실제 실행 solver 버전을 구별했다. T3 공식 페이지의 결과 표 제목은 transient 문제 설명과 달리 Linear Static으로 표기되어 있어 원문상의 혼동도 기록했다. 제공 결과값·압전 결과 그림은 상류의 reference이며 이번 실행에서 얻은 정답이 아니다.

ZIP에는 별도 LICENSE/NOTICE가 없고 공식 문서에 저작권 및 권리 유보 고지가 있다. 공개 다운로드만으로 원본 재배포 허용을 추론하지 않는다. 공개 산출물에는 metadata·locator·해시와 독자 요약만 남기며 ZIP과 deck 원본은 싣지 않는다. MSC Nastran 고유 예제 확보, 오류 입력 예제, solver 실행은 이 보충 조사에 포함하지 않았다.
