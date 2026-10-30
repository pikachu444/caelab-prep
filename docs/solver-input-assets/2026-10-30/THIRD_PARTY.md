# 참고 원문과 사용 조건

이 묶음은 연구·구현 검토용 자료다. 동봉 소스를 제품의 의존성으로 도입하거나 이식·실행했다고 뜻하지 않는다. 파일별 원 고지와 LICENSE/COPYING을 보존했다.

| 위치 | 원천/조건 | 역할·주의 |
|---|---|---|
| assets/dyna/pydyna, examples/dyna/pydyna | Ansys PyDYNA, MIT | schema·writer·parser/transform fixture 일부. full `kwd.json`은 참고 ZIP에만 수록. R17 전수 의미 지원이나 독립 설치 패키지가 아님 |
| assets/bdf/pynastran | Steve Doyle 등 PyNastran, BSD-3-Clause | formatter/writer/reader/시험 일부. 429 reader whitelist는 solver별 writer 지원표가 아님 |
| examples/abaqus/meshio, abqpy | 각 원본 MIT | mesh/set writer 및 Abaqus runtime 의존 예제. solver가 무료·공개라는 뜻이 아님 |
| examples/calculix/mit-parametric | Martin Kraska 예제, MIT | CGX/CCX가 필요한 선택 parametric 예제 |
| examples/calculix/official-code | CCX/CGX source, GPL-2.0 | 선택 reader/부분 writer. 전체 프로그램 의존성 미포함 |
| examples/aster | Code_Aster와 AsterStudy, GPL-3.0 계열 | 고정 commit의 선택 Cata/launcher/serializer·예제. 원 LICENSE와 source manifest를 함께 확인 |
| examples/radioss/code/inp2rad.py | OpenCourant Tools, MIT | 범위가 제한된 converter. 모든 Abaqus/LS-DYNA를 모든 RAD로 변환하지 않음 |
| examples/radioss/code의 나머지 reader/writer/verifier | OpenCourant, AGPL-3.0 계열 | 선택 소스. 원본 파일 고지와 LICENSE/COPYRIGHT 적용; 독립 실행 구성 아님 |

상용 매뉴얼/PDF·HTML 전문, 공식 예제 중 권리가 불명확한 파일, OpenCourant의 제한적 `hm_cfg_files`, CC BY-NC QA 원본, NASA95 원본은 동봉하지 않았다. 해당 원장·취득 manifest에서 URL·버전·member·크기·SHA·권리 상태를 찾아 원천에 접근할 수 있다. 공개 열람·취득 가능과 제품 재배포 허용은 별개다.

GPL/AGPL 소스는 원문 고지를 보존한 참고 사본이다. 향후 제품 결합/수정/배포/네트워크 제공 방식의 의무는 그 도입 작업에서 확인해야 한다. 루트 저장소의 조건을 개별 예제·schema·cfg·문서 전체의 조건으로 일반화하지 않는다.
