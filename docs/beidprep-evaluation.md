# BeidPrep 1.0.1 실제 시험

2026-10-29에 Windows용 BeidPrep 1.0.1 공개 배포본을 실제 실행했다. 이 기록과 스크립트는 외부 프로그램의 평가 자료이며 CAELab Prep의 구현·성능을 뜻하지 않는다. 2.0은 실행하지 않았다.

## 수행 범위

| 작업 | 결과 |
|---|---|
| 원본 EXE 다운로드·확인 | 164,719,059바이트, 스크립트의 고정 SHA-256과 일치 |
| Windows에서 시작 | 계정·이메일·로그인 입력 없이 주 화면 도달 |
| RAD 열기·3D 표시 | 8절점·셸 2개, 재료·접촉을 가진 소형 모델 표시 |
| 저장·새 프로세스에서 재열기 | 실제 수행. 저장 파일의 물리 조건 보존은 실패 |
| 재료 E 수정 | GUI 자동화가 재료 항목을 찾지 못해 미완료 |
| 재열기 후 GUI 재료값 검증 | 미완료 |
| GUI 내부 솔버 실행 | 미수행 |
| 저장본의 별도 솔버 검사 | Linux OpenCourant Starter/Engine으로 실행. 원본 Engine 재사용 |

실제 Windows 실행은 기존 워크벤치의 [run 40799756961](https://github.com/pikachu444/caelab-workbench/actions/runs/40799756961), [run 40800402280](https://github.com/pikachu444/caelab-workbench/actions/runs/40800402280)에 기록했다. 두 실행의 GUI 저장본은 바이트 단위로 같았다. GUI 자동 편집·값 재읽기를 완료하지 못해 시험 스크립트는 종료 코드 2를 반환했으며 성공으로 바꾸지 않았다.

## 저장 조건 변화

| 항목 | 원본 | GUI 저장본 |
|---|---|---|
| 노드 1–4 병진 구속 X/Y/Z | `111` | `011` |
| 같은 노드 회전 구속 X/Y/Z | `111` | `000` |
| 두 셸 속성 IPLAS | `1` | `0` |
| Starter 오류/경고 | 0 / 0 | 0 / 2 (`100214`, `/BCS/1`) |

구속 변화는 단순 텍스트 차이가 아니라 Starter의 진단 출력으로 확인했다. IPLAS는 지정한 투영 알고리즘 옵션이 기본 선택으로 바뀐 것이며 소성 재료가 삭제됐다는 의미가 아니다. 노드·요소·파트·재료·접촉 개수, 탄성 상수·소성 곡선·마찰계수·초기속도는 보존됐다. Engine은 1,375사이클, 0.002초까지 정상 종료했으나 변경된 구속을 동등한 모델로 인정할 수 없다. 이 소형 충돌 모델은 해석 정확도 검증 사례가 아니다.

## 파일과 재현

- `scripts/evaluation/beidprep_windows_trial.py`: 당시 Windows GUI 시험 코드. 외부 EXE를 별도로 내려받아 실행한다. 앱을 수정하거나 디컴파일하지 않는다.
- `scripts/evaluation/models/`: 직접 작성한 소형 입력과 실제 GUI 저장본. `observed-beidprep-saved_0000.rad`는 결함 재현 자료다.
- `.github/workflows/beidprep-evaluation.yml`: 수동 실행 전용. GPU 없는 Windows runner에 Mesa 24.3.4를 별도로 공급하고 관찰 결과를 Actions 산출물로 보존한다. 일반 제품 CI와 구분한다.

재현은 수동 워크플로의 새 호스팅 runner 또는 폐기 가능한 새 Windows VM에서만 수행한다. 이 역사적 시험 스크립트는 창 제목으로 BeidPrep 창을 선택하고 해당 프로세스 트리를 강제 종료하며, `evaluation-output/`의 같은 이름 출력을 덮어쓴다. **일상 작업 PC나 기존 BeidPrep 세션이 있는 환경에서는 실행하지 않는다.** 실제 당시 시험도 새 Windows 호스팅 runner에서 수행했다.

새 VM에서 직접 재현할 경우 동일한 Windows 렌더링 환경과 `requests`, `pywinauto`, `Pillow`를 준비하고 저장소 루트에서 다음을 실행한다.

```powershell
python scripts/evaluation/beidprep_windows_trial.py
```

관찰 결과는 `evaluation-output/`에 생성된다. 현재 스크립트는 E 수정·재읽기를 확인하지 못하면 종료 코드 2로 끝나므로 파일 열기·저장 관찰과 전체 편집 시험 성공을 구분해야 한다. 이 저장소로 옮긴 뒤 실제 GUI 시험을 다시 실행한 것은 아니다.

제작사 안내: <https://github.com/BeiderSim/BeidPrep>. 공개 배포 EXE는 비공개 소스이며 사용·배포·분석은 제작사 조건을 따른다. 실행 파일은 이 저장소에 동봉하지 않는다.
