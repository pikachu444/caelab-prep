# 공개 기반의 사용

제작사 프로그램의 비공개 코드를 추출하거나 복사하지 않는다. 현재 제품 코드는 공개 API를 연결하며 아래 라이브러리의 실행 파일·소스 배포본은 Git에 넣지 않는다.

| 기반 | 사용 방식 | 원문 |
|---|---|---|
| Qt / PySide6 | 데스크톱 위젯·Action·작업 신호 | [Qt for Python 라이선스](https://doc.qt.io/qtforpython-6/licenses.html) |
| VTK | 실제 메시 렌더링·선택·원 ID 역매핑. 실행 환경 검사는 9.7.1 사용 | [VTK 라이선스](https://vtk.org/about/) |
| Gmsh 4.15.2 / 내장 OCC 경로 | 선택 설치한 SDK를 별도 프로세스로 호출해 CAD·메시 자산 생성 | [Gmsh 조건](https://gmsh.info/doc/texinfo/#Copying-conditions), [공식 소스](https://gitlab.onelab.info/gmsh/gmsh) |

상세 라이선스와 배포 조건은 실제 사용하는 버전·바인딩·플러그인별로 확인한다. 현재 설치형 바이너리를 동봉한 배포는 아니다. OCP를 이용한 별도 검증 입력 생성은 제품 의존성이 아니다.
