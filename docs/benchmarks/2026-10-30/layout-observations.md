# 원본 화면의 관측과 실측

root가 실제 이미지를 열어 확인했다. 아래 수치는 앱 설정값/기본값/권장값이 아니다. 측정 대상은 별도 자료집의 이미지이며 source URL은 제품 JSON에 연결돼 있다. 글꼴명·OS 배율은 원문에서 확인되지 않았다.

| 대상 | 원본 치수 | 관측 영역/값 | 해석 제한 |
|---|---|---|---|
| Naksha NA01 전체 화면 | 1600×860 | 왼쪽 Outline/Details가 약400px; viewport는 x≈402부터. 선택 띠는 y≈160–190; 하단 status는 y≈839부터 | 해당 0.5.07 이미지의 경계 ±3px 관측. 다른 창 크기의 비율/도킹 최소폭은 모름 |
| Naksha NA05 재료 창 | 1250×720 | 필터 띠·왼쪽 행열·오른쪽 상세/곡선·하단 Import가 동시에 존재 | 열/패널 resize 정책·실제 import 결과는 미확인 |
| BeidPrep BE05 카드 폼 | 1560×1170 | 모델 트리 약220px; 폼 x≈228–488; viewport가 오른쪽. TEXT/FORM 전환과 field 그룹 스크롤 | 하단 APPLY는 선택 도구 소속. 카드 값 확정 시점은 그림으로 모름 |
| BeidPrep BE03 이동 패널 | 1560×1170 | 오른쪽 Editing 패널은 x≈1316부터. 중앙 preview와 하단 선택 도구가 함께 있음 | 전역 메뉴 진입·commit/cancel·좌표 보존은 미확인 |
| HyperMesh HM07 Select Surfaces | 1125×716 | Name/ID/Include/Config/Status 표와 하단 Apply/OK/Cancel. status 점 중심 간격의 중앙값23px | 원본 status 점의 y중심 103.5,126.5,…655.5를 픽셀 검사. 앱 DPI/글꼴 크기로 해석 금지 |
| HyperMesh HM21 Curve Editor | 767×525 | 왼쪽 entity/표, 오른쪽 plot; Property Editor/Table 탭 | 빈 초기 plot 장면이므로 큰 곡선/다중열의 밀도 기준으로 단독 사용하지 않음 |
| COMSOL COM-T04 Size Settings | 266×473 | 상단 build, 선택 domain, custom 최대크기의 세 그룹 | Settings 패널 발췌일 뿐 전체 앱의 패널 비율을 모름 |
| NFX 교육 p42 | 발췌1414×834 | 리본·트리/속성·복수 모델창·로그·단위 표시가 함께 있음 | 교육용 주석/화살표와144dpi 렌더를 제거하지 않은 관측. 원래 앱 치수로 측정 금지 |
| MeshFree 교육 p18 | 발췌1416×776 | 모델/해석 트리 분리·3스텝·viewport·출력·단위 | 빈 workspace 장면이므로 정보 밀도 목표로 단독 선정하지 않음 |

원본 이미지를 통해 필요한 부품·비례·상태 배치를 관측할 수 있지만, 모든 resize/hover/focus/disabled 상태를 재현할 자료가 확보된 것은 아니다. 구현자가 그림에 없는 상태를 원 제품과 같다고 주장하지 않게 결손을 남긴다.
