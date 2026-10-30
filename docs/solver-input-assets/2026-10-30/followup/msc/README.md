# MSC 입력 생성: 추가로 확보한 실제 자산

2026-10-30. PR #10의 ‘MSC 완전 예제 미확보’는 공개 경로를 충분히 시도한 결과가 아니었다. 이번에는 공식 문서가 직접 연결하는 native 입력 파일을 실제 취득했다. **대표 세 모델은 메시·재료·조건·해석 제어를 포함하는 완전 SOL400 입력이다.** 실제 솔버 실행은 하지 않았다.

## 새 writer를 만들 때 바로 볼 모델

아래 링크는 Cadence 공식 MSC Nastran **2026.1.1** Implicit Nonlinear Demonstration Guide가 연결하는 vendor 원본이다. 문서 판본, 덱 생성 헤더, 실행한 솔버 판본은 서로 구분한다. 이 모델을 MSC2024.2 실행 통과 예제로 부르지 않는다.

| 필요한 기능 | 실제 입력 | 개발할 때 볼 내용 | 공식 설명 |
|---|---|---|---|
| 비선형 충돌·초기속도·beam contact | [nug_47a.dat](https://www.mscsoftware.com/doc/nastran/mdug/input_files/ch047/nug_47a.dat) | SOL400/NLTRAN, IC/TIC, SPC, TSTEPNL, rigid sphere/직물 beam 접촉과 질량. 헤더는 Patran2025.1, 2026-01-30 생성 | [Input Files](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Dynamic_Impact/11_Input_Files.htm), [하중·구속](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Dynamic_Impact/7_Loading_and_Boundary_Conditions.htm), [결과](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Dynamic_Impact/9_Results.htm) |
| 대슬라이딩 접촉·여러 STEP·강제변위 | [nug_27.dat](https://www.mscsoftware.com/doc/nastran/mdug/input_files/ch027/nug_27.dat) | 삽입/회수 두 NLSTATIC STEP, 각각의 LOAD/SPC/BCONTACT 선택, SPCD, NLSTEP, 접촉 body/surface/마찰 정의. 헤더에 구형 Patran2006 표기가 남아 있으나 현행 공식 문서가 배포하는 파일 | [Input Files](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Large_Sliding_Contact/11_Input_Files.htm), [접촉](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Large_Sliding_Contact/5_Modeling_Contact.htm), [결과](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Large_Sliding_Contact/9_Results.htm) |
| gasket 물성·곡선·볼트 프리텐션·MPC | [nug_10.dat](https://www.mscsoftware.com/doc/nastran/mdug/input_files/ch010/nug_10.dat) | SOL400, MATG/TABLES1, solid/property, MPC와 SPCD, 접촉/초기 간극 및 NLSTEP. 가스켓 body와 ring의 서로 다른 하중/제하 재료 의미 | [Input Files](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Engine_Gasket/9_Input_Files.htm), [모델](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Engine_Gasket/4_Model_Details.htm), [해석 구성](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Engine_Gasket/5_FEM_Solutions.htm), [결과](https://documentation.cadence.com/msc/MSC%20Nastran/MSC_Nastran_2026.1.1/Nastran/Demonstration_Problems_Guide_Implicit_Nonlinear/Engine_Gasket/6_Results.htm) |

대표 세 덱을 실제 읽고 Executive/Case/Bulk 구역, 선택되는 하중/구속/초기조건·접촉, 메시/재료와 ENDDATA를 확인했다. 활성 INCLUDE/ASSIGN/READFILE/RESTART 등 별도 입력 의존은 관측되지 않았다. `nug_27.dat`의 TPLDIR include는 `$` 주석이고 `nug_47a.dat`의 restart 문장은 설명 주석이다. 이 판별은 전체 참조 그래프나 수치 타당성을 검증했다는 뜻은 아니다.

각 공식 Input Files 페이지가 제공하는 변형들도 실제 취득했다. `ch047`의 a/ax/b/bx, `ch027`의 기본/f/a/c, `ch010`의 기본/bolt/bolt1a–d다. 대표 세 모델을 상세 독해했고 나머지 변형 전부의 의미를 검토했다고 주장하지 않는다. 외부 solver·추가 결과 파일 없이 파일 자체는 확보했으며, 문서 결과 그림/논의는 상류 기대 경향이다.

`download_msc_examples.py`는 위 대표 세 덱을 원천에서 내려받는다. `--all-variants`는 연결된 변형, `--guides`는 아래 공식 PDF도 받는다. 기존 파일을 덮어쓰지 않고 솔버를 실행하지 않는다.

## 기존 목표판 MSC2024.2의 생성 규칙과 완전 listing

공식 [Linear Static Analysis User’s Guide 2024.2](https://documentation-be.hexagon.com/bundle/MSC_Nastran_2024.2_Linear_Static_Analysis_User_Guide/raw/resource/enus/MSC_Nastran_2024.2_Linear_Static_Analysis_User_Guide.pdf)를 실제 취득했다.

- Listing2-1 `TRUSS1`: SOL101, SPC/LOAD 선택, GRID/CROD/PROD/MAT1/FORCE/SPC1을 포함하는 완전 입력 listing이다.
- Listing4-7 `BEAM2`, printed122–123 / PDF120–121: tapered PBEAM station·continuation, CBEAM offset/warping·scalar point, FORCE/SPC와 전체 입력 구역을 보인다. 이어지는 출력·설명이 변위와 비틀림 의미를 설명한다.
- Listing7-5 `ROTATE`, printed283–284 / PDF281–282: 여러 subcase와 RFORCE·CONM2를 구성한다. 단순 load 배수와 회전속도 제곱 효과를 혼동하지 않는 예다.

이것은 2024.2 문서의 **완전 입력 listing 확보**이며 설치 배포본의 원 `.dat`를 받았다는 뜻은 아니다. PDF에는 페이지 구분·여백·설명 라벨이 섞이므로 pdftotext 출력을 바로 유효 deck으로 사용하면 안 된다. BEAM2의 실제 PDF 페이지를 시각 확인했다. 새 deck으로 전사하거나 실행하지 않았다.

[Getting Started Guide2024.2](https://documentation-be.hexagon.com/bundle/MSC_Nastran_2024.2_Getting_Started_Guide/raw/resource/enus/MSC_Nastran_2024.2_Getting_Started_Guide.pdf)의 파일 구역·입력 형식·제약/하중·해석 완성 흐름도 확보했다. [SOL400 Getting Started2024.2](https://documentation-be.hexagon.com/bundle/MSC_Nastran_2024.2_SOL_400_Getting_Started_Guide/raw/resource/enus/MSC_Nastran_2024.2_SOL_400_Getting_Started_Guide.pdf)의 Listing4-1은 NLSTATIC/BCONTACT/NLSTEP 구성을 보여주지만 본문이 두 CHEXA 이후 끝나는 **축약 예시**라 완전 모델로 세지 않는다.

## 생성 코드에서 실제로 재사용할 부분

바로 열기: [카드 생성 API](assets/pynastran/pyNastran/bdf/bdf_interface/add_card.py) · [solid field/출력](assets/pynastran/pyNastran/bdf/cards/elements/solid.py) · [MSC 접촉 구현/미구현](assets/pynastran/pyNastran/bdf/cards/contact/msc.py)

PR10의 formatter/writer 일부에 더해 같은 PyNastran pin `f51e9ffa74222f93750618d4766e59f2f96751c3`의 다음 실제 원문을 추가 취득했다. BSD-3-Clause LICENSE를 동봉했다. 전체 설치 패키지가 아닌 읽기·도입 검토용 source subset이며 실행하지 않았다.

| 코드 | 활용 지점 |
|---|---|
| `bdf_interface/add_card.py` | `add_grid`, `add_ctetra`, `add_psolid`, `add_force`, `add_spc` 등 객체 생성 API와 native 카드 객체 연결 |
| `cards/elements/solid.py` | CTETRA 등 차수/연결과 card field 배치·출력 |
| `cards/properties/solid.py` | PSOLID 등 재료/속성 참조·기본값·`raw_fields`/`write_card` |
| `cards/constraints.py` | SPC/SPC1/SPCADD 등 DOF/집합/반복 행 출력 |
| `cards/contact/msc.py`, `contact_common.py` | MSC contact의 실제 구현 범위와 미구현 경계 |

중요한 실제 한계: 이 pin의 `contact/msc.py` 머리말에는 **BCBODY1/BCONECT/BCONPRP/BCTABL1이 todo**로 남아 있다. 이번 최신 공식 SOL400 모델들이 이 카드를 사용한다. 따라서 PyNastran을 이 모델 전체의 완성된 schema writer라고 쓰면 안 된다. 기본 카드 생성 경로는 활용하고, 최신 접촉 카드 생성은 공식 QRG·실물 덱을 함께 보며 별도 지원을 개발해야 한다. reader/raw text 보존은 그 생성 구현의 대체가 아니다.

## 다시 시도한 경로와 실제 남은 제한

- KIT의 MSC NAS120 support 페이지는 실제 읽었지만 지원 파일 링크가 `ftp.mscsoftware.com.tw/download/training/`이고 이 호스트는 DNS 해석에 실패했다. 이 구형 경로는 실제 막혔다.
- Nexus 문서 HTML은 실제 JS shell이었다. **Cadence 공식 정적 HTML → MSC 원본 input file 링크**로 이동하니 인증 없이 다운로드가 됐다. 따라서 MSC 공식 예제 전체가 로그인으로 막혔다고 보고하지 않는다.
- 공식 community의 `files.zip`과 설명 PDF도 받았다. `bolt_n_gasket.bdf`는 SOL101 mesh/material 시작 모델이며 BC/load가 없어 완전 SOL600 모델이 아니다. CSV4개는 후속 교육용 재료 데이터다. 직접 읽은 뒤 complete 모델 분류에서 제외했다.
- 현대 MSC raw 모델은 확보했지만 ‘2024.2 설치 예제 raw와 실행 결과’의 동일판 쌍은 이번에 확보하지 않았다. 대신 2024.2 완전 listing과 현행 공식 raw를 각각 보존한다. 이 차이는 실행 호환성 확인에서 중요하다.
- 상용 매뉴얼·vendor 입력 예제의 자유 재배포 허가는 확인하지 못했다. 원문은 `analysis-only/`에 보존하고 공개 저장소에는 이 사용 안내·직접 원천 URL·다운로더를 둔다. 새 계약·로그인·추가 권한은 사용하지 않았다.

독립 검토자가 대표 세 raw 모델과 2024.2 완전 listing, 포럼 시작 모델의 분류를 실제로 읽어 대조했다. 이번 결과는 개발 자산 확보이며 전수 field schema·새 전처리기·solver 실행의 완료는 아니다.
