# Code_Aster / AsterStudy upstream research snapshots

이 디렉터리는 입력 형식·명령 스키마·writer 구조를 확인하기 위한 **수정하지 않은 원문 source subset**이다. solver 설치물, 독립 실행 SDK, 새로 구현한 exporter가 아니다. solver·libaster·AsterStudy QA는 실행하지 않았다.

- `upstream/`: https://gitlab.com/codeaster/src 의 tag `17.5.8`, commit `c1f5c46ef795e0bf6d82a29dc20da30d281535ce`.
  - `code_aster/Cata/` 전체, `run_aster/` 전체, `astest/sslv139a.{comm,export,datg,mmed}`, `README.md`, `LICENSE`.
  - EDF 및 원문 각 파일의 저작권/기여 표시를 보존했다. source 헤더는 **GNU GPL version 3 또는 이후 버전**을 지정한다. [원문 LICENSE](upstream/LICENSE)를 함께 유지한다.
  - `sslv139a.datg`는 Cast3M mesh 생성 문법이고 `.mmed`는 실제 MED binary다. `.export`에 선언된 공개 파일 bundle을 보존한다. mesh를 새로 생성하거나 TEST_RESU 수치를 여기서 관측하지 않았다.
- `asterstudy-upstream/`: https://gitlab.com/salomemeca/modules/salome-asterstudy 의 commit `51c9fdd31b3d900fa6879ead66c58aa171c6ef3f`.
  - `asterstudy/datamodel/` 전체와 `test/datamodel/test_export.py`, `test_conversion.py`, `test_include.py`, `README.md`, `COPYING`.
  - 원문 EDF copyright 헤더 및 **GNU GPL version 3** 조건을 보존했다. [원문 COPYING](asterstudy-upstream/COPYING)을 함께 유지한다.
  - common/SALOME/asrun/Qt 등 외부 의존과 catalogues는 설치·검증하지 않았다. source subset에 대한 분석이 Code_Aster17.5.8 완전 호환이나 실행 성공을 의미하지 않는다.

`source-manifest.json`에는 각 upstream 원문 파일의 저장 경로·정확한 revision URL·바이트 수·SHA256을 기록했다. 이 디렉터리에 상용 매뉴얼/Code_Aster 매뉴얼 전문은 포함하지 않는다. 매뉴얼은 보고서의 공식 locator·관련 절 요약만 참조한다.
