# 참고 원문과 사용 조건

이 묶음은 연구·구현 검토용 자료다. 동봉 소스를 제품의 의존성으로 도입하거나 이식·실행했다고 뜻하지 않는다. 파일별 원 고지와 LICENSE/COPYING을 보존했다.

| 위치 | 원천/조건 | 역할·주의 |
|---|---|---|
| PyDYNA 참고 archive, `assets/dyna/pydyna-source-inventory.json` | Ansys PyDYNA, MIT | 참고 ZIP의 schema·writer·parser/transform fixture 원장. 이 Git tree에는 PyDYNA 코드가 없다. full `kwd.json`도 참고 ZIP 범위다. R17 전수 의미 지원이나 독립 설치 패키지가 아님 |
| `followup/msc/assets/pynastran` | Steve Doyle 등 PyNastran, BSD-3-Clause | 실제 복사 Python 6개와 BSD 고지를 유지한다. 과거 archive의 formatter/writer/reader 범위는 원장에 별도 기록한다. 429 reader whitelist는 solver별 writer 지원표가 아님 |
| examples/abaqus/meshio, abqpy | 각 원본 MIT | mesh/set writer 및 Abaqus runtime 의존 예제. solver가 무료·공개라는 뜻이 아님 |
| examples/calculix/mit-parametric | Martin Kraska 예제, MIT | CGX/CCX가 필요한 선택 parametric 예제 |
| examples/calculix/official-code | CCX/CGX source, GPL-2.0 | 선택 reader/부분 writer. 전체 프로그램 의존성 미포함 |
| examples/aster | Code_Aster와 AsterStudy, GPL-3.0 계열 | 고정 commit의 선택 Cata/launcher/serializer·예제. 원 LICENSE와 source manifest를 함께 확인 |
| examples/radioss/code/inp2rad.py | OpenCourant Tools, MIT | 범위가 제한된 converter. 모든 Abaqus/LS-DYNA를 모든 RAD로 변환하지 않음 |
| examples/radioss/code의 나머지 reader/writer/verifier | OpenCourant, AGPL-3.0 계열 | 선택 소스. 원본 파일 고지와 LICENSE/COPYRIGHT 적용; 독립 실행 구성 아님 |

상용 매뉴얼/PDF·HTML 전문, 공식 예제 중 권리가 불명확한 파일, OpenCourant의 제한적 `hm_cfg_files`, CC BY-NC QA 원본, NASA95 원본은 동봉하지 않았다. 해당 원장·취득 manifest에서 URL·버전·member·크기·SHA·권리 상태를 찾아 원천에 접근할 수 있다. 공개 열람·취득 가능과 제품 재배포 허용은 별개다.

GPL/AGPL 소스는 원문 고지를 보존한 참고 사본이다. 향후 제품 결합/수정/배포/네트워크 제공 방식의 의무는 그 도입 작업에서 확인해야 한다. 루트 저장소의 조건을 개별 예제·schema·cfg·문서 전체의 조건으로 일반화하지 않는다.

## Archive 원장과 Git의 실제 복사 코드

PyDYNA 두 폴더는 같은 LICENSE/NOTICE만 있고 코드가 없어 제거했다. 원천은 [PyDYNA](https://github.com/ansys/pydyna/tree/90270f787216c91a969d6b477aaf753d45556035), 고정 revision은 `90270f787216c91a969d6b477aaf753d45556035`, 당시 패키지 표기는 `ansys-dyna-core 0.13.dev0`, 이용조건은 원천의 MIT다. 상세 URL·archive 내부 경로·바이트·해시는 [source inventory](assets/dyna/pydyna-source-inventory.json)를 유지한다. 기계 생성 `kwd.json`과 상용 매뉴얼은 출처와 조건이 다르며, R17 전수 의미 지원을 보장하지 않는다. archive는 독립 설치 패키지가 아니고 당시 이 수집에서 PyDYNA/solver를 실행하지 않았다.

실제 pyNastran Python 파일이 있는 [MSC source 묶음](followup/msc/assets/pynastran/NOTICE.md)에는 [BSD 고지](followup/msc/assets/pynastran/LICENSE.md)를 유지한다. 실제 OpenCourant Fortran 20개가 있는 [reader 묶음](followup/rad/assets/opencourant-readers/COPYRIGHT.md)에는 [원 LICENSE](followup/rad/assets/opencourant-readers/LICENSE.md)를 유지한다. 코드가 없는 예전 위치의 동일 고지 사본만 통합했다. source-manifest와 files 원장은 당시 archive의 내부 경로이며 현재 Git에 모든 파일이 있다는 뜻이 아니다.

Aster/AsterStudy의 두 LICENSE 사본 위치에도 Git의 실제 코드가 없었다. [원장](examples/aster/source-manifest.json)과 [출처·조건](examples/aster/NOTICE.md)을 유지하고, archive source를 다시 배포할 때는 해당 원 GPL 고지를 함께 전달한다. 제거한 원문은 [정리 전 Git tree](https://github.com/pikachu444/caelab-prep/tree/46cea51457ea62748a940f95015ce0216edf369a/docs/solver-input-assets/2026-10-30/examples/aster)에서 확인할 수 있다. 실제 복사 코드를 제거하거나 그 코드의 고지를 삭제한 변경은 아니다.
