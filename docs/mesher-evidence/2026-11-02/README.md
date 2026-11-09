# 미완료 커널 실증 인계

이 체크포인트는 N23/N26의 새 제품 구현이 아니라 수행한 실험 코드·입력·판정을 보존한다. 기존 제품 파일과 권한/환경 설정을 변경하지 않는다.

- N23: `scripts/evaluation/midsurface_recipe`에서 고정 plate/rounded-L을 재현한다. `run_f1.py`는 Linux `resource`를 사용하므로 Windows 러너로 주장하지 않는다. 결과는 스크립트 옆 `results/`에 쓴다. 여기의 공개 result/BRep 사본은 기존 측정값이며 재실행하지 않았다. 입력이 자체 작성됐다는 한계·공식 예제/접합부/F2/제품 연결 미완료를 `midsurface/HANDOFF.md`에 유지한다.
- N26: `hybrid`에 공식 mapping 해석, 독립 형태 두 개의 정확 RAD 쌍·로그·정정 판정을 보존한다. 원래 정점/slot 질량 분포 차이와 prism 실패를 숨기지 않는다. 일반 hybrid native 지원이 아니다.

원 작업 디렉터리와 바이너리는 변경/삭제하지 않았다. vendor 바이너리·manual 이미지·원문 전체·solver restart/animation 파일은 Git에 복제하지 않았다. 기존 해시 manifest의 일부 항목은 원 실험 전체에 대한 것으로, 공개 subset에서 누락된 파일이 있다는 사실을 구분한다. trace의 transient 작업경로만 `<workspace>`로 치환했다. 별도 source archive 해시와 실행 결과를 전체 성공으로 합산하지 않는다.
