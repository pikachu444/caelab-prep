# 기존 Gmsh SDK에서 이용할 수 있는 실제 RAD mesh writer

공식 [Gmsh 4.15.2 source archive](https://gmsh.info/src/gmsh-4.15.2-source.tgz)를 내려받아 native RAD 출력부와 요소별 연결 순서 코드를 확보했다. 현재 Prep가 이미 쓰는 Gmsh SDK에 RAD 출력 경로가 있다는 점에서 직접적인 참고 자산이다. 새 mesher나 CAE exporter를 구현한 것은 아니다.

[실제 RAD writer 열기](source/src/geo/GModelIO_RAD.cpp) · [요소 연결 출력](source/src/geo/MElement.cpp) · [라이선스](source/LICENSE.txt)

## 어떤 코드를 읽고 사용할 것인가

| 파일·함수 | 실제로 제공하는 기능 |
|---|---|
| `src/common/CreateFile.cpp`, `FORMAT_RAD` 분기 | `.rad` 확장자에서 `GModel::writeRAD`로 연결 |
| `src/geo/GModelIO_RAD.cpp`, `GModel::writeRAD` | BEGIN/NODE/요소 block, PhysicalGroup에서 절점·요소 집합 출력 |
| 같은 파일 `writeElementsRAD`, `partID` | geometric entity별 요소 block, `dimension*1000000+entity tag` 번호 생성 |
| `src/geo/MElement.cpp`, `MElement::writeRAD` | 고정 폭 연결 순서, penta 퇴화 BRICK, 고차 요소 행 배치 |
| `MTetrahedron.h`, `MHexahedron.h`, `MPrism.h` 등 | RAD용 node 순서와 요소 keyword 선택 |
| `MVertex.cpp`, `MVertex::writeRAD` | 절점 번호와 좌표의 실제 수치 출력 |

Python SDK의 진입점은 기존 mesh를 가진 Gmsh 모델에서 `gmsh.write("mesh_0000.rad")`다. [공식 write API](https://gmsh.info/doc/texinfo/gmsh.html#Namespace-gmsh)와 실제 extension 분기를 대조했다. 여기서는 API나 solver를 실행하지 않았다. `.inc`를 동일 API에 넘기면 RAD가 된다고 가정하지 않는다. 공식 튜토리얼의 `.inc` 저장은 GUI에서 RADIOSS BLOCK 형식을 지정한 흐름이다.

## 공용 mesh adapter에 활용할 때 필요한 연결

이 writer는 **mesh writer**다. 요소 block에 part 번호를 쓰지만 `/PART`, `/MAT`, `/PROP`, 하중·구속·접촉이나 Engine을 만들지 않는다. 따라서 전체 해석 모델 exporter로 연결하려면 앱의 part/property/material 및 조건 객체를 이 번호와 연결해 별도로 작성해야 한다. PhysicalGroup의 set 번호와 geometric entity의 part 번호도 같지 않다.

4.15.2 코드는 `/BEGIN` 판을 2022, 입력/작업 단위를 `Mg mm s`로 쓴다. 좌표 `scalingFactor`는 밀도·탄성계수·시간·힘의 단위 변환이 아니다. 앱의 단위 체계와 이 문자열을 맞추지 않은 채 출력하면 안 된다. mesh include 채택에서도 writer가 BEGIN/END를 포함한다는 사실을 반영해야 한다.

고차·퇴화 표현도 그대로 복사할 수 없다. 예를 들어 Hex27은 BRIC20으로 출력하며 일부 node를 생략하고, prism6은 퇴화 BRICK으로 변환한다. source를 확보했다는 이유로 모든 원본 요소를 손실 없이 보존한다고 주장하지 않는다. 지원할 요소군에서 실제 mapping을 선택하는 데 사용할 코드다.

## 완전한 해석 예제에 접근한 결과

[공식 LAW36/BIQUAD 인장 튜토리얼](https://openradioss.atlassian.net/wiki/spaces/OPENRADIOSS/pages/24444938)은 재료·하중·구속을 가진 wrapper Starter/Engine과 mesh include·STEP의 역할을 설명한다. 이 설명은 mesh와 해석 조건을 나눠 작성하는 실용적인 참고다.

그러나 본문이 가리키는 `Tensile-Test-gmsh_Tutorial.zip?api=v2` 및 query 없는 첨부 URL은 실제 요청에서 모두 404였고, 공개 attachment REST 목록은 403이었다. 이 ZIP 원본을 확보했다고 표시하지 않는다. 새 계정·권한이나 유료 계약은 요청하지 않았다. 이 튜토리얼의 미취득과, 별도로 확보한 meshio++의 공개 Starter/Engine pair는 구분한다.

## 재사용 조건

`source/`는 위 공식 배포본에서 가져온 수정하지 않은 참고 소스 일부다. root `LICENSE.txt`와 `CREDITS.txt`를 보존했다. Gmsh는 GPL-2.0-or-later 및 원문의 결합 예외를 따른다. subset 자체가 설치 가능한 Gmsh 패키지는 아니다. 실제 제품에서 Gmsh SDK를 호출하는 방식과 source를 복사·수정하는 방식은 구분해 도입한다.
