# 고정 structured recipe 실증 근거

현재 판정은 [OCC 후속 판정](F2-OCC-addendum.md), 이전 실패와 정밀도 수정은 [원 보고서](F2-report.md)에 보존한다. 모두 SDK 실증이며 제품 채택·GUI·native 완료가 아니다.

이 폴더는 고정 입력 해시, 실행 요약, 판정과 실패 기록의 공개 사본이다. 보고서의 원 실행 폴더 경로는 당시 조사 산출물 위치이며 모든 원 MSH를 Git에 중복 저장하지 않는다. 현재 recipe 전체 18입력의 새 CI 실행은 `structured-recipe-evidence` artifact에 MSH·SDK 로그·독립 검사 결과를 보존한다. 그 실행 전에는 최신 SHA 전체 18개가 재실행됐다고 주장하지 않는다.

공개 재현 경로는 `scripts/evaluation/structured_recipes.py`와 `scripts/evaluation/structured_f2/verify_f2.py`다. Gmsh 4.15.2에서 원 입력·oracle·공차를 해시로 고정하고 실패/시간 초과 시 비영 종료한다. 지원 입력은 직선/짧은 원호·한 면 또는 공유 edge 두 planar quad·공통 직선 sweep이며 curved source/annulus/twist/임의 patch assembly와 hybrid는 포함하지 않는다.

원호 경로 변경의 코드 근거는 공식 [Gmsh 4.15.2 source](https://gmsh.info/src/gmsh-4.15.2-source.tgz)의 `GeoInterpolation.cpp` `InterpolateCurve(...,1)` 유한차분과 `OCCEdge.cpp` `firstDer`의 OCCT D1이다. 같은 입력의 수치 오차 개선은 실측했지만 모든 SDK 내부 오차 원인을 증명한 것은 아니다.
