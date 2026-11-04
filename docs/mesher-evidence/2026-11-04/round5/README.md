# Round5 Hex·혼합 메시 조사와 저장소 반영 판단

2026-11-04 · 메시어검토 · Prep N25/N26 / P7c-H 연구 근거

**판정: 연구 자료로 보존하고 기존 메셔 로드맵에서 연결한다. 제품 엔진의 자동 채택이나 solver export 허용으로 반영하지 않는다.** 추가 시험에서 복잡 원본 CAD의 품질·형상·피처 기준을 모두 통과한 새 범용 자동 메셔는 확보하지 못했다. 미시험 후보가 열등하다는 뜻도 아니다.

## 읽는 순서

1. [추가 조사와 직접 실행](ROUND5_ADDITIONAL_REVIEW_KO.md)
2. [후속 개발 에이전트 인계](REPOSITORY_AGENT_HANDOFF_KO.md), [이전 조사까지 포함한 통합 보고서](MESHER_CONSOLIDATED_REVIEW_KO.md)
3. [전체 후보 JSON](CANDIDATE_CATALOG.json) / [CSV](CANDIDATE_CATALOG.csv)
4. [원 CAD 정책 감사와 별도 기준판 수치](INDEPENDENT_RESULT_TABLE.json), [준비된 입력의 품질](PREPARED_INPUT_QUALITY_TABLE.json)
5. [증거 요약](EVIDENCE_SUMMARY.json), [재현 안내](evidence_round5/REPRODUCTION_GUIDE.md), [보존 검증](REPOSITORY_REVIEW_KO.md)

총 68개는 기존 50개와 추가 18개의 **검토 항목**이다. 생성기, 사용자 블록 도구, 후처리, wrapper, 배포판과 제외 후보를 포함하므로 독립 무료 엔진의 수가 아니다. 후보별 공개 소스·배포본·라이선스 확인과 직접 실행 단계도 다르다.

## 적용할 개발 경계

| 관측/후보 | 보존·재사용할 것 | 이번 자료로 승인하지 않는 것 |
|---|---|---|
| CinoLib·Mesquite | 비유한 좌표 문제와 후처리 효과의 원인·실패·감사 수치 | 잔여 역전, CAD 경계 오차와 피처 실패를 무시한 채택 |
| FieldCraft·meshio++ | 고정 release/형식·설정, native 생성과 writer 충돌을 분리한 근거 | 기준판 성공을 복잡 CAD 성공으로 합산하거나 실행 종료값으로 품질 통과 |
| HexGen·C4 | 수동 분할/블록 또는 seamless map을 이미 가진 입력의 결과 | 준비 작업이 없는 STEP 자동 처리, 시간 초과를 모든 환경의 불가능으로 확대 |
| SMESH Cartesian3D | 전체 Hex/Wedge/polyhedron inventory와 원본 CAD 진단 | polyhedron 누락·퇴화 변환으로 표준 FE 정합 전이 또는 RAD 출력 합격 |
| 기타 추가 후보 | 역할·출처·라이선스·미실행 상태와 후속 평가 경로 | 문서/논문 존재만으로 기능 완료, wrapper를 독립 커널로 중복 계산 |

[기존 F0–F4 문턱](../../../mesher-feasibility-roadmap.md#6-구현-가능성을-먼저-확인하는-유한-단계), [현재 N 작업표](../../../../CURRENT_STATE.md#remaining-work)와 [Workbench 소비 경계](../../../workbench-reuse-plan.md)를 따른다. 이번 자료 보존은 N25/N26 완료·기존 draft 종료·Windows 검증·native/해석 적합성의 새 판정이 아니다. 기존 검증된 tri/tet 및 제한 quad/sweep 기능은 유지한다. 다음 구현자는 자신의 작업 범위와 기준 입력을 고정한 뒤 해당 실패·미확인 항목만 이어서 검증한다.

## 보관 범위

이 디렉터리는 검토에 필요한 문서·기계 판독 표·source pin·입력 해시·감사 JSON·실패 로그와 자체 실행/감사 harness의 선별 사본이다. 원본 CAD, 대형 메시, 외부 실행파일·설치 패키지·전체 upstream clone은 Git에 넣지 않았다. 전체 묶음의 보관 위치와 SHA-256, 사본별 파일 해시는 보존 검증 문서와 manifest를 따른다.

`EVIDENCE_SUMMARY.json`은 퇴화 요소의 비유한 값을 `null`로 직렬화하며 원 감사 파일의 해시를 유지한다. 원 감사 JSON에는 Python `NaN`이 있으므로 엄격한 JSON 소비자는 요약 표를 사용하고 이를 0 또는 합격으로 바꾸지 않는다. 로그·harness의 절대 경로는 당시 실험 출처이며 다른 환경에서 그대로 실행되는 설치 API가 아니다.
