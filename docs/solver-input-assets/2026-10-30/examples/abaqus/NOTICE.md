# Abaqus 관련 공개 코드 원본

이 폴더의 Python 파일은 이번 조사에서 실행하지 않았다. 다운로드한 vendor 매뉴얼·공식 입력 덱은 재배포 허가를 확인하지 못해 포함하지 않는다.

- `meshio/_abaqus.py`, `meshio/test_abaqus.py`: nschloe/meshio `b2ee99842e119901349fdeee06b5bf61e01f450a`의 `src/meshio/abaqus/_abaqus.py`, `tests/test_abaqus.py`. MIT, 해당 `LICENSE.txt` 동봉. 이 어댑터는 mesh와 node/element sets의 제한된 입출력 코드다. 재료·접촉·step·BC·출력 요청을 갖춘 전체 Abaqus writer가 아니다. 원 mesh 시험 파일은 별도 출처/권리이므로 동봉하지 않았다. `_abaqus.py`는 meshio 패키지 상대 import를 사용해 이 파일만 단독 실행할 수 없다.
- `abqpy/compression.py`: haiiliin/abqpy 2025 branch `3088e9fc3b77da615a586524c0cb407b3d0acc48`의 `examples/Compression/compression.py`. MIT, 해당 LICENSE 동봉. Abaqus/CAE 모델·메시·재료·조건·job.writeInput·job.submit 호출 예다. 라이선스가 있는 Abaqus 런타임이 필요하며, 공개 abqpy의 Job.writeInput 본체는 `...` 타입/문서 stub다. 독립 오픈소스 Abaqus 생성기가 아니다. **이 예제는 실행 시 job 제출까지 수행하므로 읽기용 조사 자산으로만 취득했다.**

파일의 upstream 경로·고정 commit·SHA는 solver 자료 JSON에 기록한다. 헤더/권리 고지를 유지한다.
