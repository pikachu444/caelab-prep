# Round5 재현·감사 안내

1. logs/source_inventory.json과 RELEASE_AND_ENVIRONMENT.json의 버전과 SHA를 우선 고정한다. FieldCraft release tag는 default branch와 다르다. meshio++는 공식18.1.0 wheel을 그대로 사용했고 메셔 코드를 바꾸지 않았다.
2. build_remaining.py, cinolib_driver.cpp, mesquite_driver.cpp, fieldcraft_canary.py, fieldcraft_extract.py, meshioplusplus_worker_arrays.py가 새 adapter의 소스다. logs의 CMake/g++/configure 명령과 diff를 함께 읽는다. C4 submodule pins는 native configure 로그에도 기록됐다.
3. common_inputs/{case}/metadata.json, original.brep, surface.obj는 원형상/공통 입력이다. FieldCraft의 input.3mf에는 같은 삼각면과 face 태그를 보존했다. scripts의 절대 /workspace 경로는 당시 provenance다. 다른 컴퓨터에서 재생할 때는 새 checkout과 common_inputs 위치에 맞게 치환해야 한다.
4. frozen_audit는 이전 audit4.3과 그 의존 Python/C++ 원문이다. gmsh4.15.2, meshio, numpy, vtk, native OCCT8 classifier/distance helper를 사용한다. 파일 단위 SHA는 EVIDENCE_SUMMARY/COMMON_INPUT_MANIFEST를 따른다. 원 CAD 단위는mm다.
5. FieldCraft native MCMESH01의 좌표는 이 시험에서 입력의mm와 일치한다. MCMESH02의metres와 혼동하면 안 된다. native package에는 원 태그를 보존하고 독립 감사 변환은 좌표·Hex8 연결성만 추출했다.
6. meshio++ native VTU writer crash는 표준 VTK2.0/NPZ로 저장만 우회했다. C++ native output 배열은 그대로다. native report를 내보내기 전에 저장한다. VTK crash에서 단순히 rc-11을 메셔 실패로 세지 않는다.
7. CinoLib은 수정 전/후를 모두 보존했다. 수정 후에도 정점 좌표 유한성만 확보했을 뿐 종합 합격이 아니다. Mesquite 입력은 VTK4.2 호환 직렬화가 필요했다. native 경계 고정과 실제 소수 출력 변화는 boundary_unchanged.json에서 확인한다.
8. C4의 --output-hex-file은 접미사 _100_hex.ovm 등을 자동으로 붙인다. 명령에 적힌 basename의 존재 여부만으로 출력 없음이라 판단하지 않는다. output glob과 로그의 최종 생성 단계를 함께 읽는다.
9. 실행 시간은 병행 호스트·서로 다른 설정/요소 수에서 얻은 단발 시간이다. 순위표로 사용하지 않는다.0 또는 비현실적인 peak RSS 샘플은 측정 불충분이다. native exit0, corner SJ 양수, solver exit0는 원 CAD 정확도와 동일하지 않다.
10. 유료 solver는 C4 빌드에 사용하지 않았다. 공식 Clp heuristic 경로다. 전체 upstream 소스/설치 패키지/컴파일된 외부 binary는 이 묶음에 중복 배포하지 않는다. 라이선스와 공식 source pins, 로컬 수정 patch를 보관했다.
