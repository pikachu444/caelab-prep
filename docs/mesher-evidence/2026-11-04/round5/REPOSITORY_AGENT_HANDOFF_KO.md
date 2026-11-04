# 저장소 에이전트 인계 - 무료 Hex·혼합 메시 Round5 추가 조사

기존 통합본의50항목을 전체 조사/검증 완료로 취급하지 마세요. 새 목록은68항목이며 독립 생성기 수가 아닙니다. 새 엔진과 wrapper·배포판·후처리를 구분했습니다. 검색 누락은 열등성 근거가 아닙니다.

1. `ROUND5_ADDITIONAL_REVIEW_KO.md`를 먼저 읽고 기존 `previous_handoff`의 원 보고서와 함께 확인하세요. 새 실행은 FieldCraft·meshio++·CinoLib·HexGen·C4·Mesquite·SMESH Cartesian3D7계열입니다. 무조건 채택 가능한 새 범용 자동 CAD mesher는 이번 시험에서 확보하지 못했습니다.
2. CinoLib 새 clone의 projector 초기화 패치와 직렬화는 유한 좌표 문제만 해결했습니다.3 CAD 모두 품질/형상/피처 합격이 아닙니다. raw exit0/코너SJ만으로 채택하면 안 됩니다.
3. Mesquite 후처리는39→11/31→5로27점 nonpositive를 줄였지만 남은 역전과 고정 경계 오차를 해결하지 못했습니다. 후처리 adapter 후보로 유지하고 export 합격을 자동 부여하지 마세요.
4. FieldCraft 공식v0.7.0 binary는 tag commit e9ccf10692a08ea4c6037442c6213e1f68d344b8에 대응합니다. 같은0.7.0 문자열의 default branch와 파일 형식이 다릅니다. 실행한 release/소스/단위/형식을 고정하세요. 복잡3종은 depth5·2M 한도에서 실패했습니다. 관통공 판23,772Hex는 별도 사례이며 형상/품질 불합격입니다.
5. meshio++18.1.0에는 실제 allHex octree 경로가 있습니다. VTU writer crash는 메셔 실패와 별도로 기록했습니다. native 배열을 표준 VTK로 직렬화한 출력도 독립 검사에서 역전/퇴화/피처 실패가 있습니다. 원 코드 변경 없이 저장만 우회한 것입니다.
6. HexGen4단계는 Linux에서 이식 패치 후 빌드됐습니다. 제공된 수동 segmentation+hex block에서만 mapping/quality를 실행했습니다. raw3456Hex·후처리5696Hex 모두 독립 검사 불합격이며 Bottom 자동 segmentation은 충돌했습니다. 이식 문제와 원 알고리즘 일반 성능을 구분하세요.
7. C4는 Clp heuristic으로 유료 solver 없이 빌드됐습니다. seamless map이 있는 Tet 입력부터 시작합니다. minimal64Hex canary는 기본 유효성만 통과했습니다. 복잡 raw STEP 자동화의 대체물이 아닙니다. 다른 준비 매핑 시험은 실행표와 로그를 확인하세요.
8. SMESH Body Fitting은3원본Brep에서Hex+Wedge+polyhedron을실제생성했습니다(Bottom3702+28+2234,Dragon3270+31+3410,CW2773+19+1128). 표준FE전체감사는아니며polyhedron누락출력을금지합니다.  GIBBON 혼합 demo는 quad-tri interface 전이 확인이 필요합니다. 높은 Hex 비율이나 공유 절점으로 표준 FE 정합을 인정하지 마세요.
9. 기존 검증된 Tet 및 분할/sweep 구현은 유지하세요. Mesquite·HexOpt 등 후처리, IA-FEMesh/FEBio Studio/classy_blocks 등의 블록 작업 자산, FieldCraft/meshio++/C4의 별도 연구 worker를 구분해 연결하세요.
10. 새 Linux 실험을 Windows 검증으로 보고하지 마세요. Rad/solver export의 새 승인 근거는 이번에 추가되지 않았습니다. 이전 반복 절점 Pyramid→BRICK 문제도 해결하지 않았습니다.

자료: CANDIDATE_CATALOG.csv/json, INDEPENDENT_RESULT_TABLE.json, EVIDENCE_SUMMARY.json, evidence_round5, previous_handoff. 모든 채택/제외 이유는 입력·버전·옵션·검사 정의에 연결해야 합니다.
