# harness — 증거 로그·제출 파일 대조·비밀값 검사

쓰는 때: "완료"라고 말하기 전(probe-verify), 제출 직전(probe-wrap). 필요: sh, git, python3(표준 라이브러리만).
한 번에: `sh ~/probe-kit/templates/harness/gate.sh --exclude 원본폴더 --test "python3 -m pytest -q" [--sample sample.csv 제출.csv]` (작업 폴더 = git 루트에서)

| 파일 | 하는 일 | 종료 코드 |
|---|---|---|
| `gate.sh` | `--test`로 준 명령만 돌려 `outputs/logs/gate_*.log`에 남기고 PASS/FAIL/NOT_RUN 요약. 통과한 테스트가 1건 이상 보일 때만 PASS(0건·전부 skip·건수 못 읽음 = NOT_RUN) | FAIL이 하나라도 있으면 1 |
| `verify.sh` | 명령 하나를 로그 첫 줄 commit·dirty, 끝 줄 종료 코드와 함께 실행(probe-verify 2) | 명령의 종료 코드 |
| `check_secrets.py` | 작업 트리·git 이력에서 비밀값·전화·이메일 흔적. `--pattern`(사번 형식), `--literal 값목록.txt`(실제 값, 커밋 금지). `--demo` 자체 점검 | 찾으면 1, git 실패 2 |
| `check_submission.py` | 제출 CSV를 sample과 대조: 헤더·행 수·ID 순서·중복·칸 수, ID 뒤 모든 예측 열의 빈칸·NaN, `--allowed`·`--range` | 어긋나면 1 |

- PASS는 "이 검사로 문제를 못 찾았다"는 뜻이다. NOT_RUN은 실패가 아니라 "증거가 없다" — 로그를 직접 열어 건수를 확인한 뒤에만 PASS로 적는다.
- 로그에는 명령 출력이 그대로 남는다. 테스트가 실제 비밀값·개인정보를 출력하지 않게 한다.
