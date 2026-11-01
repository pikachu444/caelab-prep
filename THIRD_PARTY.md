# 공개 기반의 사용

제작사 프로그램의 비공개 코드를 추출하거나 복사하지 않는다. 현재 제품 코드는 공개 API를 연결하며 아래 라이브러리의 실행 파일·소스 배포본은 Git에 넣지 않는다. 구현 기준은 Prep main `a48d3b4`이며 실제 설치 범위는 `pyproject.toml`, 실행 검증 버전은 [작업서 19절](docs/execution-stages.md#current-progress)을 따른다.

| 기반 | 사용 방식 | 원문 |
|---|---|---|
| Qt / PySide6 | 데스크톱 위젯·Action·작업 신호 | [Qt for Python 라이선스](https://doc.qt.io/qtforpython-6/licenses.html) |
| VTK | 실제 메시 렌더링·선택·원 ID 역매핑. 실행 환경 검사는 9.7.1 사용 | [VTK 라이선스](https://vtk.org/about/) |
| Gmsh 4.15.2 / 내장 OCC 경로 | 선택 설치한 SDK를 별도 프로세스로 호출해 CAD·메시 자산 생성 | [Gmsh 조건](https://gmsh.info/doc/texinfo/#Copying-conditions), [공식 소스](https://gitlab.onelab.info/gmsh/gmsh) |

상세 라이선스와 배포 조건은 실제 사용하는 버전·바인딩·플러그인별로 확인한다. 현재 CI의 wheel은 Python 패키지와 자체 자산을 담으며 새 환경에서 CLI 설치를 검사한다. Qt/VTK/Gmsh를 동봉한 Windows 설치형 배포의 검증은 아직 없고 N13에 남는다. OCP `7.8.1.1.post1`은 별도 CAD 시험 환경의 입력 생성용이며 제품 의존성이 아니다. 고정한 공식 OpenCourant 바이너리는 solver-smoke CI에서 내려받아 실행하며 제품/저장소에 재배포하지 않는다.

참조 화면·매뉴얼의 관찰 기록은 제품 artwork가 아니다. 자료 폴더의 외부 예제·소스는 [수집 자산 고지](docs/solver-input-assets/2026-10-30/THIRD_PARTY.md)의 개별 조건을 따른다. 문서 최신화로 원저작자의 LICENSE/NOTICE를 변경하지 않는다. 이 문서는 전체 라이선스 심사가 끝났다는 선언이 아니며 설치형 배포를 만들 때 실제 포함 파일과 고지를 확인한다.
