# Round5 검색 범위와 중복 제거

기준일2026-11-04. 기존50항목 목록과2022 Hex-Mesh Generation and Processing survey의 계열/구현 목록을 대조하고2024~2026 공개 저장소·공식 문서에서 누락을 보완했다. 전 세계 구현의 전수 검색 완료 주장은 하지 않는다.

| 탐색 계열 | 새로 추가/복구한 검토 경로 | 실제 실행 여부 |
|---|---|---|
| 비구조 자동 all-Hex | FieldCraft, meshio++ octree, Medial-HexMeshing | 앞2종 실행; Medial 소스/빌드 입구 확인 |
| 방향장·seamless map·quantization | C4/MC3D/QGP3D/TS3D | C4와 dependencies native빌드 및 canary/준비 매핑 실행 |
| polycube | HexGen |4단계 native빌드·raw/후처리 실행 |
| grid·projection | CinoLib |3복잡 CAD raw/수정 전후 실행 |
| Hex·혼합 후처리 | Mesquite |2복잡 CAD native 후처리+독립 감사 |
| 사용자 multiblock | IA-FEMesh, FEBio Studio |공식 문서·소스 라이선스; 미실행 |
| 도메인 전용 Hex | LaGriT, GRIDDER, Neper, TexGen, MyMesh |문서·함수/라이선스; 미실행 |
| dual sheet | Takayama2019 |저자→Bitbucket 링크·논문; 현 라이선스 bytes 미확보 |
| 혼합·cut-cell | SMESH Body Fitting, GIBBON |SMESH3원본Brep native실행; GIBBON은interface 소스확인,미실행 |
| 블록 스크립트 | classy_blocks, gmsh_scripts |같은 blockMesh/Gmsh backend로 중복 제거 |
| 격자 비용 절감 |2026 3-refinement templates |완성 생성기가 아닌 구성 요소로 기록 |
| 배포 접근성 | Hexi |기존 Feature-Preserving Octree의 배포와 중복 구분 |

주요 검색어: open source all hex meshing, free hex dominant hybrid mesher, hexahedra pyramid prism tet conforming, octree hex mesh quality benchmark,2025/2026 hexahedral GitHub, medial hex meshing, dual sheet meshing code license, biological/image voxel hex, LaGriT Neper TexGen, Mesquite untangle hybrid pyramids wedges, FEBio/GIBBON mixed hex tet, Hexi licenses. 검색은1차 출처의 실체·기능·라이선스·실행 경로 확인으로 이어졌으며 검색 순서나 별점으로 성능을 판정하지 않았다.

무료로 오인하기 쉬운 제외: MG-Hexa/MG-Hybrid는 SALOME 플러그인의 공개성과 상용 커널의 무료성이 다르다. Cubit/Sculpt/CF-MESH+ 등은 기존 목록의 제한/상용 구분을 유지한다. TetGen/Netgen/CGAL Mesh_3/HXT/MMG/TetWild의 Tet 기능이나 quad-only surface를 새 완성 Hex 생성기로 계산하지 않는다. CAD와 mesh IO/뷰어/품질 측정만 하는 도구도 생성기 수에 합산하지 않는다.
