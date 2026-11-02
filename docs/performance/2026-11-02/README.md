# N17 측정 인계 — 목표 미달 유지

baseline/after의 실제 100회 p95 측정과 focused의 8회 원인 분리 측정은 서로 다른 실험이다. 평균 73ms 개선을 p95 합격으로 쓰지 않는다. 100만 요소/100 part/20 source와 기존 응답 예산은 유지한다. 일부 개선은 PR #20에 병합됐으나 전체 N17은 미완료다.

원 조사 기록·생성기·harness와 파일별 source manifest 및 해당 `src/` snapshot ZIP을 보존한다. 스냅샷은 역사적 관측 버전이며 현재 main 실행 코드가 아니다. 재현하려면 해당 stage 옆 `snapshot/`에 맞는 ZIP을 풀고 원 report의 환경과 생성 입력을 사용한다. Linux /proc/cgroup/X11 전용 guard를 Windows 러너라고 쓰지 않는다. 일부 역사적 harness의 sha 비교는 결과 목록 반환만 하고 assert하지 않으므로 재실행 전 input-manifest의 모든 hash를 별도 강제 대조해야 한다. 이번 인계에서 baseline/after 각각 20개 원 입력 hash를 실제 다시 확인했다.

원 입력 123MB와 작업문서·이미지, 전체 guard 고빈도 sample은 원 폴더에 보존하고 Git에 중복 저장하지 않았다. generator와 input hash로 같은 입력을 복원할 수 있다. guard 요약의 고빈도 sample만 제외했으며 peak/종료/중단 사유는 유지한다. transient 작업 경로는 `<workspace>`로 치환했다. v4에서 관계 누락을 읽지 못했던 실패와 v5 migration 후 성공을 둘 다 보존한다. 현재 source archive의 hash는 `source-archives.json`에 있다.
