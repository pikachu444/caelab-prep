# Nastran 공식 예제 한정 추가 조사

2026-10-30. MSC Nastran 2024.2 QRG 수집을 보완하기 위해 공식 complete analysis deck를 최대 5분 추가 조사했다. **NASA 공식 NASTRAN-95 예제 한 묶음은 실제 취득했다. MSC 2024.2 덱/실행 검증은 확보하지 못했다.**

## 실제 확보

- 저장소: `https://github.com/nasa/NASTRAN-95`
- 고정 commit: `65e29e9db7b21a02bb42e723afa74fa7635ed765` (2015-12-03)
- 해석판: NASA NASTRAN 1995 edition. 보존 output은 SUN SOLARIS / May 17, 1995 표기를 포함한다.
- 입력: `inp/d05011a.inp`, 원문 설명 `inp/d05011a.txt`, 보존 결과 `demoout/d05011a.out`.
- 원본·README·NOSA license DOC 및 기각 후보 포함 7개 실제 파일, 총 260448B. 각 URL·size·SHA256은 `catalogues/nastran-examples.json`에 기록했다.

`d05011a.inp`는 원통 대칭 좌굴 문제다. SOL 5,1, CEND, case control, static preload/buckling subcase, BEGIN BULK/ENDDATA, GRID/CTRIA1/PTRIA1/MAT1, LOAD/FORCE, SPC/SPCADD, EIGB를 실제 파일에서 확인했다. READFILE/INCLUDE/ASSIGN 외부 입력 지시문은 관측되지 않았다. Plotter NASTPLT 출력 요청과 해당 NASA 실행 환경은 별도 runtime 의존이다. 전체 의미 참조 그래프 검증이나 solver acceptance까지 수행했다는 뜻은 아니다.

설명에는 좌굴 계수와 해석해 비교표가 있고 같은 이름의 archival output도 취득했다. 이 파일들은 **NASA의 과거 실행 자료**이며 현재 수집자가 해석기를 실행한 결과가 아니다. NASA rigid format·구형 CTRIA1 등 native 카드가 있으므로 현대 MSC 2024.2에 그대로 유효하다고 일반화하지 않는다.

## 기각과 남은 공백

`d01001a.inp`는 DIAG48 메시지 출력 후 멈추고 bulk가 비어 있는 진단 job이므로 구조 해석 예로 세지 않았다. `d01021b.inp`는 READFILE RSCARDS와 비어 있는 bulk를 갖는 restart 덱이라 자족 모델로 세지 않았다. 두 파일도 판단 근거를 위해 분석용으로 취득했다.

Hexagon 공식 검색에서는 MSC Nastran 2022.1 Linear Static Analysis Guide의 Listing 4-7과 설치 예제 위치 `MSC_DOC_DIR/doc/linstat/beam2.dat`를 찾았다. 그러나 bounded 조사에서 공식 MSC 2024.2 standalone raw deck를 취득하지 못했다. 설치된 MSC example archive와 matching output은 여전히 공백이다.

## 권리와 종료

NASA README는 NOSA 1.3 공개라고 명시하고 license DOC 원본도 확보했다. 이 추가 조사에서 license 전체 조건의 재배포 검토까지 완료하지 않았으므로 파일은 모두 `tmp/opti-nastran/nastran-examples/` 분석용에만 두고 공개 묶음에는 원문 URL/해시/독자 설명만 포함한다. 상용 MSC 매뉴얼 입력 예제도 자동으로 복제 허용으로 취급하지 않았다.

한정 조사는 **완전 NASA native 입력·공식 설명·과거 output·권리 문서의 실물 확보 1건**, MSC 2024.2 실제 완전 덱 미확보로 종료한다. 모든 실행 플래그는 false다.
