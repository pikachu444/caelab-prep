# RAD 생성 참고 원문

이 폴더는 새 RAD 기능을 개발할 때 읽을 실제 소스와 예제를 담는다. 이번 수집에서 코드 설치·실행·새 덱 생성·solver 실행은 하지 않았다. 기존 CAELab Prep 지원 범위를 확대하는 제품 패치는 아니다.

- `assets/meshioplusplus/`: https://github.com/loumalouomega/meshioplusplus, commit `548cbc8622ba80356590521331b8b21fa04e6e3a`. MIT. 원 LICENSE와 함께 native RAD Python/C++ reader/writer, wrapper·설명·관련 tests·자작 column Starter/Engine 예제를 보존했다. 전체 패키지 의존성이 갖춰진 독립 배포물이 아닌 참고 source subset이다.
- `assets/k2rad/`: https://github.com/pmquang87/k_to_rad_converter, commit `d7652dadb8dcd4b558a68e609e7e5c02ebfe3a26`. MIT, Copyright2026 Minh Quang Pham. 공개 저장소 source archive 전체를 실제 취득했으며, 이 Git 폴더에는 package·진입점·설정·선택 fixture를 보존했다. source·writer·tests와 golden fixture의 존재가 그 전체의 의미·solver 검증을 입증하지 않는다. 원 LICENSE 유지.
- `assets/opencourant-readers/`: https://github.com/OpenCourant/OpenCourant, commit `cb760c206e346eff12161a2268b134ef9d48a4ef`. 원문 각 파일 AGPLv3-or-later 고지 및 LICENSE/COPYRIGHT 유지. 선택 Starter reader·default·unit 관련 소스다. 전체 dependency closure가 아닌 참고 subset이다.
- `analysis/`와 기존 `solver-input-research/tmp/radioss/`는 배포 대상이 아니다. 제한 CFG, 상용 매뉴얼 원문, 라이선스를 찾지 못한 luchete80 소스는 여기에서만 분석했다.

meshio++의 `column_0000.rad`/`column_0001.rad` README는 저자 자작 MIT deck임을 명시한다. 함께 제공된 source/LICENSE와 이 설명을 유지한다. README의 상류 실행 정보는 상류 관측이며 이번 작업에서 재현한 결과가 아니다. top node의 운동은 `/INIVEL/TRA` 초기 속도이며 지속 prescribed velocity가 아니다.

제품에 실제로 결합할 때는 개별 코드의 dependency·지원 범위·실패 동작·배포 조건을 검토해야 한다. 특히 meshio++가 미지원 cells/data를 경고 후 버릴 수 있다는 사실을 숨기지 않는다. k2rad conversion golden fixture를 공학적 benchmark로 취급하지 않는다.
