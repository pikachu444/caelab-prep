# 입력 생성 자산 후속 독립 검토

기존 PR10의 RAD 미독해 descriptor/semantic reader와 MSC 완전 예제는 공개 취득 경로를 소진한 결과가 아니었다. RAD 상세 문서 대부분은 미독해였고 MSC 추가 조사는 5분으로 한정됐다. 이번 후속에서 실제 새 writer와 MIT 완전 RAD 모델까지 나왔으므로 이 부분을 접근 불가나 권리 문제로 묶어 종료해서는 안 된다. 실제 제약은 특정 CFG의 제한적 조건, upstream QA의 NC 조건, MSC matching-version 설치 예제·실행 환경·재배포 권리다.

RAD `rad/assets/opencourant-readers/starter/source/properties/shell/hm_read_prop01.F`, `loads/general/cload/hm_read_cload.F`, `materials/mat/mat001/hm_read_mat01.F`를 직접 읽었다. SHELL의 ISHELL/ISMSTR/ITHK/IPLAS는 DEFAULTS_SHELL 상속과 sentinel 변환이 있고, NIP==-1은 이 함수의 NPTS_D=0으로 치환되며 NIP>10은 오류다. CLOAD의 zero skew는 submodel skew를 상속하고 zero xscale/magnitude는 단위 처리 경로의 FAC_FCX/FAC_FCY로 치환된다. LAW1은 zero reference density를 initial density로 대체하고 E<=0 오류, ν=0.5 내부 보정이 있다. 이 원문은 실제 의미 규칙이며 폼 설명·검증에 쓸 수 있다. reader 자체가 writer나 완성 schema는 아니고 solver 내부 보정을 exporter의 강제 치환으로 옮겨서는 안 된다. 담당자에게 DEFAULTS/CFG 연결을 요청했고 NIP 기본값의 출처와 상속을 구별하도록 직접 토론했다.

`rad/analysis/external/meshioplusplus/src/python/meshioplusplus/radioss/_radioss.py:1305`의 `write`와 1596행 이후 stub 출력을 읽었다. 실제 writer가 맞지만 geometry/part/group/surface 중심이고 `stubs=False`가 기본이다. 미지원 cell은 경고 후 버리고 옵션 stub은 재료/물성 placeholder이므로 전체 해석 writer로 소개하면 안 된다. 같은 저장소 `tests/python/meshes/radioss_th/column/`의 Starter/Engine와 README를 전부 읽었다. 두 BRICK, LAW1/PROP, bottom BCS, top INIVEL, TH/ANIM 및 시간설정이 포함되고 외부 include가 없는 유용한 완전 파일쌍이다. deck은 BEGIN2017, README의 upstream 실행은 latest-20260728이고 이번 실행은 아니다. MIT 자작 고지가 있어 기존 NC QA와 다른 재사용 경로다. INIVEL은 초기속도이며 지속 강제속도가 아니다.

`rad/analysis/external/k2rad/k2rad/writer/assembly.py`의 `build_starter`/`build_engines`와 세 expected pair를 선별 독해했다. 실제 serializing code이며 ID 생성·set 전개·조건 변환·restart 분할 등 구현 참고 가치가 크다. ConversionState와 다른 모듈에 의존하므로 함수 두 개만 떼어 범용 native writer라 할 수 없다. BEGIN2022 출력과 최신 카드 혼용을 설명하는 README 경고도 target별 확인 대상이다. `shell_explicit`은 외부 파일 없는 serializer golden이지만 BC/하중/초기속도 없이 excitation이 없으므로 물리 benchmark로 세지 않는다. `implicit_qstat`은 BCS와 implicit engine 설정, `rigid_contact`는 CLOAD를 포함하지만 funct_IDT=1에 해당하는 /FUNCT/1이 없다. 담당자가 지적한 뒤 원문을 대조했으며 이 pair는 완결 해석 예제로 권하지 않는다. 이들은 upstream conversion fixture이고 독립 수치 oracle이나 이번 solver acceptance가 아니다. 담당자에게 이 분류를 전달했다.

MSC `msc/analysis-only/msc2018-implicit-examples/bolt_n_gasket.bdf`의 header, executive/case control, material과 마지막 행을 직접 읽었다. 공식 SOL600 학습 포럼 첨부라는 맥락과 달리 파일 자체는 2005 Patran13.1.116이 만든 SOL101 메시·재료 모델이다. SPC/LOAD case 선택 및 실제 BC/load/nonlinear/contact bulk가 없고 CSV도 덱에 참조되지 않는다. 따라서 완전 SOL600 해석 예제가 아니라 tutorial 시작모델+후속 입력용 곡선이다. 담당자에게 즉시 전달했으며 공식 설명 PDF와 별도 완전 listing 경로 조사가 필요하다. 공개 첨부 취득은 실제 진전이지만 MSC2024.2 완전 예제 공백을 닫지는 않는다.


추가 도착한 `msc/analysis-only/MSC_Nastran_2024.2_Linear_Static_Analysis_User_Guide.txt`의 Listing 2-1 TRUSS1(본문 34쪽)과 Listing 4-7 BEAM2(122–123쪽)를 실제 읽었다. TRUSS1에는 SOL101/LOAD10/SPC11, GRID/CROD/PROD/MAT1/FORCE/SPC1부터 ENDDATA까지 있고, BEAM2에는 SOL101/LOAD1/SPC1, GRID/SPOINT/CBEAM/PBEAM/MAT1/FORCE와 ENDDATA가 있다. 두 listing은 외부 include 없이 완전 모델을 설명한다. 따라서 **MSC2024.2 문서에 실린 완전 입력 예제 원문 확보**는 성공이다. 설치 raw `.dat` bytes와 이번 실행결과를 얻었다는 뜻은 아니다. PDF 텍스트 추출에는 우측 설명 라벨·페이지 머리말·가변 들여쓰기가 섞여 있으므로 그 텍스트 자체를 실행 가능한 fixed-column 덱으로 배포하면 안 된다. 담당자와 이 구분을 토론했다. 예제 주변의 하중·변형 설명과 결과 그림도 생성기 구현의 의미 확인에 유용하며, 이전의 단순 설치 경로 발견보다 실질적으로 진전됐다.


RAD 후속 `analysis/opencourant/starter/source/modules/defaults_mod.F90`도 읽었다. `init_def_elem`은 implicit 여부에 따라 shell zero를 24 또는 1, solid zero를 14 또는 1로 정하고 ish3n zero를 2로 정한다. 단일 카드의 zero/default를 독립 상수로 만들 수 없다는 앞선 지적을 연결 원문으로 보강했다.

Gmsh 4.15.2 `gmsh/source/src/geo/GModelIO_RAD.cpp`의 `writeRAD` 전체와 `MElement.cpp`/`MVertex.cpp` 진입을 읽었다. 실제 메시 writer이며 /BEGIN2022, Mg/mm/s 문자열, NODE/element/PhysicalGroup 출력을 생성한다. element block의 partID는 `dim*1000000+entity tag`이고 /PART 정의는 만들지 않는다. MAT/PROP/BC/Engine도 없으므로 메시 출력 후 물리 모델을 결합해야 한다. 좌표 scalingFactor를 모든 물리량의 단위 변환으로 해석하면 안 된다. GPL2+ 및 exception 조건의 독립 재사용 판단은 MIT 후보와 분리한다.

마지막으로 MSC 공식 raw 경로에서 확보된 `msc/analysis-only/official-decks/ch047/nug_47a.dat`, `ch027/nug_27.dat`, `ch010/nug_10.dat`의 executive/case/model/조건과 종료부를 선별 읽었다. 각각 NLTRAN 충돌(초기조건·SPC·접촉·메시), clipping/retraction 두 STEP, MATG gasket 접촉(SPCD/SPCADD 포함)이 있는 실제 완전 native 입력이다. 눈으로 확인한 입력에는 활성 외부 include가 없고 ch027의 TPLDIR include는 주석이다. 이는 교육 시작 mesh였던 이전 첨부와 다르며 **공식 완전 raw 예제 확보의 성공**으로 분류한다. 연결 문서는 2026.1.1이고 47a는 Patran2025.1/2026 생성 표기이므로 MSC2024.2에서 실행됐다고 쓰면 안 된다. 2024.2 완전 예제는 문서 listing, 최신 문서 계열은 raw file 확보로 나눠 기록하면 된다. 전체 참조 그래프와 solver acceptance는 이번 검토 밖이다. 공식 공개 접근은 원본의 공개 재배포 허가와 같지 않아 분석용 보존 구분을 유지한다.

검토 범위는 위 원문 선별 독해와 담당자 토론이다. 원격 게시·병합·제품 구현·solver 실행을 하지 않았다. 모든 카드의 의미나 모든 fixture의 물리적 적합성을 보증하지 않는다.
