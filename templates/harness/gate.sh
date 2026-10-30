#!/bin/sh
# 한 명령 검사(작업 폴더 = git 루트에서): 지정한 검사만 돌려 각각 verify.sh로 outputs/logs/gate_*.log에 남기고 PASS/FAIL/NOT_RUN으로 요약한다.
# 테스트는 --test로 명령을 직접 준 것만 돌린다(오래 걸리거나 외부에 접속하거나 데이터를 바꾸는 테스트가 몰래 돌지 않게). 찾은 테스트는 후보로만 알려 준다.
# 비밀값 검사는 항상, 제출 형식 검사는 --sample을 줄 때만. 하나라도 FAIL이면 종료 코드 1.
# 사용: sh ~/probe-kit/templates/harness/gate.sh --exclude uploads --test "python3 -m pytest -q" [--test "node --test"] [--sample sample.csv 제출.csv]
# 로그에는 명령 출력이 그대로 남는다: 테스트가 실제 비밀값·개인정보를 출력하지 않게 한다. secrets PASS는 "그 패턴으로 못 찾았다"는 뜻이고 .gitignore로 뺀 로그는 따로 본다.
H=$(cd "$(dirname "$0")" && pwd)
EXCL=""; SAMPLE=""; SUB=""; n=0
while [ $# -gt 0 ]; do
  case "$1" in
    --exclude) EXCL="$EXCL --exclude $2"; shift 2 ;;
    --sample) SAMPLE=$2; SUB=$3; shift 3 ;;
    --test) n=$((n + 1)); eval "TEST_$n=\$2"; shift 2 ;;
    *) echo "모르는 옵션: $1" >&2; exit 2 ;;
  esac
done
PY=${PYTHON:-$(command -v python3 || command -v python)}   # PYTHON=경로 로 바꿀 수 있다
summary=""; failed=0
add() { summary="$summary
$1"; }
run() {  # 로그 이름, 명령
  log="outputs/logs/gate_$1.log"
  sh "$H/verify.sh" "gate_$1" "$2" >/dev/null 2>&1; code=$?
  if [ $code -ne 0 ] && ! { [ "$1" = secrets ] && [ $code -eq 2 ]; } && ! case "$2" in *pytest*) [ $code -eq 5 ];; *) false;; esac; then
    add "$1: FAIL ($log)"; failed=1; return
  fi
  case "$1:$2" in   # 통과한 테스트가 1개 이상 확인될 때만 PASS(0개·전부 skip·건수를 못 읽으면 NOT_RUN)
    secrets:*) [ $code -eq 2 ] && r="NOT_RUN(git 없음 등)" || r=PASS ;;
    submission:*) r=PASS ;;
    *pytest*) grep -Eq "[1-9][0-9]* passed" "$log" && r=PASS || r="NOT_RUN(통과한 테스트 0개)" ;;
    *node*) grep -Eq "^(ℹ|#) pass [1-9]" "$log" && r=PASS || r="NOT_RUN(통과 건수 확인 안 됨: 기본 리포터로)" ;;
    *) r="PASS(종료 코드 기준, 건수는 로그로 확인)" ;;
  esac
  add "$1: $r ($log)"
}

if [ $n -eq 0 ]; then
  hint=""
  [ -d tests ] && hint="$hint --test \"$PY -m pytest -q\""
  [ -f package.json ] && grep -q '"test"' package.json && hint="$hint --test \"npm test --silent\""
  find . -maxdepth 3 -name '*.test.mjs' -not -path './node_modules/*' 2>/dev/null | grep -q . && hint="$hint --test \"node --test\""
  add "test: NOT_RUN(--test 없음)${hint:+ 후보:$hint}"
else
  i=1
  while [ $i -le $n ]; do eval "cmd=\$TEST_$i"; run "test$i" "$cmd"; i=$((i + 1)); done
fi

run secrets "$PY $H/check_secrets.py$EXCL"

if [ -n "$SAMPLE" ]; then run submission "$PY $H/check_submission.py $SUB --sample $SAMPLE"
else add "submission: NOT_RUN(--sample 안 줌)"; fi

printf 'GATE%s\n' "$summary"
exit $failed
