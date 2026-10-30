# CalculiX 참고 코드·예제 고지

`official-code/ccx-2.23-readinput.c`는 Guido Dhondt의 공식 CCX 2.23 source archive에서 수정 없이 복사했다. 해당 파일의 GPL v2 고지와 `CCX-GPL-2.0.txt`를 유지한다.

`official-code/cgx-2.23-write2aba.c`는 Klaus Wittig의 공식 CGX 2.23 source archive에서 수정 없이 복사했다. 해당 파일의 GPL v2 고지와 `CGX-COPYING`을 유지한다.

원본 배포 위치는 https://www.dhondt.de/ 이며 archive URL·SHA256과 원본 member는 `solvers/calculix.json`에 기록했다. 여기에 둔 C 파일은 의존성 전체를 포함하는 독립 빌드 패키지가 아니라 참고용 source다.

`mit-parametric/`는 Martin Kraska의 CalculiX-Examples에서 다음 commit의 선택 파일을 원본 내용으로 보존한 것이다: `316273e9105e44ce7e3ee05059dac1bc3f256a69`. 원본: https://github.com/calculix/CalculiX-Examples/tree/316273e9105e44ce7e3ee05059dac1bc3f256a69 . MIT `LICENSE`를 포함했다. 새 generator를 작성한 것이 아니라 저자의 기존 입력 템플릿·생성/비교 스크립트다.

이 예제들은 이번 조사에서 실행하지 않았다. `.fbd`와 Python 스크립트에는 외부 solver·쉘 실행 및 결과 파일 생성/이동 동작이 있으므로 자동 실행 대상으로 등록하지 않았다. CGX/CCX와 수치 라이브러리를 갖춘 별도 작업 공간에서 원본 사용법을 따라야 한다.

공식 CCX 2.23 test archive의 638개 입력과855개 reference 파일은 내부 취득했으나 개별 재배포 고지를 확인하지 못해 여기에 복제하지 않았다. 파일 목록·크기·SHA·원본 경로는 `catalogues/calculix-test-assets.csv`에서 찾을 수 있다. PrePoMax source snapshot도 pinned 파일/권리 대조가 미완료라 여기에 재배포하지 않는다.
