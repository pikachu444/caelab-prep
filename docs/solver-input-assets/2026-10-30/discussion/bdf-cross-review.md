# BDF 두 계열의 생성 의미 검토

2026-10-30. root가 OptiStruct 2025 HTML과 MSC Nastran2024.2 QRG를 직접 대조하고 독립 Astra에 검토를 요청했다. 최종 독립 감사 결과는 `astra-findings.md`를 따른다.

| 비교 항목 | 확인 근거 | 공용 자산에 미치는 영향 |
|---|---|---|
| CTETRA.PID | OptiStruct `ctetra_bulk_r.htm` definitions: default EID / MSC QRG physical1558, printed1520: required | 동일 card 이름을 이유로 default schema를 공유할 수 없음 |
| INCLUDE | OptiStruct `include_io_r.htm` search/filemap/-incpath/relative/.gz / MSC QRG physical131 중첩10·행72자 | 파일 bundle 및 탐색 정책을 solver/version profile로 지정 |
| RESTART | OptiStruct `restart_io_r.htm`: optimization `.sh`, analysis mode에 유효하지 않음 | 모든 restart를 하나의 범용 단추나 프로세스 재시도로 해석하지 않음 |
| ID/DOF | OptiStruct GRID/MAT1/SPC/FORCE string/part 참조와 물리별 DOF / MSC GRID/SPC/PSOLID | 공용 stable ID와 native ID/namespace 및 DOF 의미를 분리 |
| PyNastran | pinned `bdf.py` reader whitelist429 / `write_mesh.py` writer / formatter8·16·double | reader 목록을 writer·제품별 지원표로 사용하지 않음 |

결론: 공용 기반에서 모델과 의존 그래프를 보존하고, solver별 profile에서 구문·지원·default·namespace·활성화·파일 배치를 검증한다. 실제 구현은 자료 수집 뒤의 별도 작업이다. 이번에는 새 deck 생성이나 solver 실행을 하지 않았다.
