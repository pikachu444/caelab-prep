# 저장소 반영 독립 검토

2026-11-04 · 독립 검토자: Astra · 검토 기준 main `f18739cb5ff8e9b52c5a81e6ccd901d6aff82b3f`

## 판단과 변경 범위

이번 결과는 **연구 근거로 보존할 가치가 있고, 제품 메셔 채택 또는 solver export 확대를 정당화하지는 않는다.** 누락 후보·역할·라이선스·실제 실행을 구분하고, 개선 효과와 남은 역전·형상 오차·입력 제한을 함께 기록했다. 연구 실패를 전체 알고리즘 열등성으로 일반화하지 않는 판단도 타당하다.

저장소의 최신 AGENTS·README·DESIGN, 메셔 로드맵, P7c 실행 단계, N25/N26 상태와 Workbench 소유 경계를 대조했다. 독립 clone과 새 문서 브랜치에서 이 자료 디렉터리와 기존 로드맵의 연결만 편집했다. 제품 코드·의존성·native mapping·N 작업 완료 상태·다른 작업자의 브랜치와 기존 여섯 draft PR은 변경하지 않았다. PR은 검토용으로 게시하며 자동 병합하지 않는다.

## 검토한 핵심 경계

- 카탈로그 68개는 독립 무료 엔진 수가 아니다. 기존 50개를 보존하고 18개 검토 항목을 보완했다. 직접 실행한 7계열과 문서 확인만 한 후보를 구분한다. Medial-HexMeshing과 Dual Sheet의 미확인 허용 조건을 확정 채택으로 올리지 않는다.
- 원 CAD 정책 감사 표 8행은 CinoLib 3, Mesquite 2, meshio++ 2와 **별도 FieldCraft 기준판 1행**이다. 마지막 행은 복잡 CAD 성공률의 분모/분자에 합산하지 않는다. HexGen/C4의 준비된 입력 결과는 별도 표로 분리했다. 초안에서 이 구분을 더 명확히 하도록 요청했고 최종 표와 범위 파일에서 반영을 확인했다.
- Mesquite의 역전 감소는 실제 후처리 효용이다. 남은 nonpositive, 경계 고정 및 최대 약 `5e-8 mm`의 출력 반올림 변화가 있어 형상·품질 합격이나 좌표의 byte-exact 보존으로 쓰지 않는다.
- FieldCraft release v0.7.0의 tag/binary와 같은 version 문자열인 default HEAD의 파일 형식을 분리한다. meshio++ writer 충돌과 실제 생성·독립 감사 결과를 분리한다.
- C4 minimal의 64 Hex 기본 검사는 작은 canary다. 다른 준비 매핑 3개는 600초 예산에서 timeout이며 rockerarm의 실제 경과는 약 606.677초다. HexGen의 제공 segmentation/hex block과 C4의 seamless map을 원본 STEP 자동화로 표현하지 않는다.
- SMESH는 Hex/Wedge/polyhedron 전체 inventory를 유지한다. 유한 CAD 거리와 polygon face incidence 진단은 표준 FE Jacobian·전체 체적/겹침·solver 수용의 검사가 아니다. collinear edge 분할을 정규화하지 않은 경계 incidence 수치를 범용 polyhedron 부적합 증명으로도 확대하지 않는다.
- Linux 8 GiB/CPU quota 8의 병행 실행 시간은 순위가 아니다. 이전 2 GiB 제한 시험·Windows 실행과 합쳐 평가하지 않는다. 반복 절점 Pyramid→BRICK의 물리 문제는 해결하지 않았다.

## 실제 검증과 한계

[검증 결과 JSON](REPOSITORY_VALIDATION.json)에 파일 수와 검사 범위를 기록했다. 선별 사본의 바이트/SHA-256을 원 동결 파일과 대조하고, EVIDENCE_SUMMARY의 모든 원 감사 경로·해시·정규화 데이터, 카탈로그 JSON/CSV, 8행 수치와 준비 입력 표를 원 감사 JSON에 직접 대조했다. 포함한 Python harness는 실행 없이 문법을 검사했고, 안내와 보고서의 로컬 링크를 확인했다.

이 독립 검토는 **원 실험 산출물·표·소스 provenance·지원 판단의 검토**다. 메셔를 다시 실행하거나 표본 검사를 전 요소 내부 유효성 증명으로 보강한 것은 아니다. 새 Windows/GUI/solver 실행, 원 CAD 전체 품질 재계산, 68개 후보 각각의 native 실행과 현행 배포 허가 법률 검토를 했다고 주장하지 않는다. 제품 코드가 바뀌지 않아 전체 제품/솔버 회귀 캠페인은 재실행하지 않는다.

## 보존과 재현

[SNAPSHOT_MANIFEST.json](SNAPSHOT_MANIFEST.json)은 원문에서 복사한 각 파일의 크기·해시·원 경로를 기록한다. 문서에 남은 절대 경로는 당시 provenance다. 원 CAD·mesh와 외부 실행파일은 Git 선별 사본에 포함하지 않았으므로 이 디렉터리만으로 모든 native 실행을 즉시 재현할 수 있다는 뜻은 아니다. 공식 원천·commit·입력 해시와 전체 증거 묶음을 함께 사용해야 한다.

HexGen의 [LF 정규화 보조 patch](evidence_round5/logs/hexgen_portability_semantic_LF.patch)는 양쪽 파일의 줄끝을 LF로 맞춘 비교다. 원 4.77 MB byte diff의 대체물이 아니며 전체 묶음에 원 diff가 보존된다. [설명](evidence_round5/logs/hexgen_patch_note.md), [HexGen BSD 고지](third_party_notices/HexGen_Hex2Spline-LICENSE.txt), [CinoLib MIT 고지](third_party_notices/cinolib-LICENSE.txt)를 함께 보존했다. 이 고지는 다른 후보 전체의 배포 허가를 대신하지 않는다.

전체 묶음과 최종 보고서는 영속 보관을 완료했다. 아래 링크는 사용자 계정 접근이 필요할 수 있다. 공개 Git 선별 사본의 감사 JSON·로그·입력/source hash는 별도 접근 없이 판단 근거를 제공한다.

| 보관 자료 | 크기/범위 | SHA-256 |
|---|---|---|
| [전체 실행자료 ZIP](https://chatgpt.com/library?file_id=libfile_6e3a2d1d5b4c8191b98414bcac13ba1b&account_id=personal) | 96,761,010 bytes · manifest 474파일 | `9f468733df85d113ef25cf64320e7a4b122b61a8e23fcc6799b794c959a24777` |
| [최종 통합 PDF](https://chatgpt.com/library?file_id=libfile_27279f08cd988191948fa8ab9f6af1ff&account_id=personal) | 3,266,542 bytes · 18쪽 | `541a33cca52774496ff71653b8e2efb23623324acf8549ae0841fd40bc93e09e` |

[통합 Markdown](https://chatgpt.com/library?file_id=libfile_0a2536bb8b488191987537f59d294296&account_id=personal)과 [개발 인계 Markdown](https://chatgpt.com/library?file_id=libfile_45c393b27a5481918ef8dd73b9411c00&account_id=personal)도 함께 보존했다. 전체 ZIP에 대형 원형상/mesh가 있다는 사실이 이를 제품 배포 자산으로 채택할 수 있다는 허가를 뜻하지 않는다.
