#!/bin/sh
# 증거 실행(probe-verify 2): commit·dirty·명령·종료 코드를 로그에 남긴다. 실패해도 로그는 남고 종료 코드는 그대로 돌려준다.
# 사용: sh verify.sh final "python train.py --train data/train.csv --target y"   → outputs/logs/final.log
# 커밋하지 않은 변경이 있으면 경고한다(그 실행은 증거로 재사용하지 않는다).
set -u
name=${1:?로그 이름}; cmd=${2:?실행할 명령}
mkdir -p outputs/logs
log="outputs/logs/$name.log"
dirty=$(git status --porcelain -- . ':(exclude)outputs/logs' 2>/dev/null | wc -l | tr -d ' ')
[ "$dirty" = "0" ] || echo "경고: 커밋 안 된 변경 $dirty개 - 먼저 commit 하고 다시 돌린다" >&2
{
  echo "commit=$(git rev-parse --short HEAD 2>/dev/null || echo none) dirty=$dirty date=$(date '+%F %T %z') cmd=$cmd"
  sh -c "$cmd"; code=$?
  echo "exit=$code"
} > "$log" 2>&1
code=$(tail -n 1 "$log" | sed 's/exit=//')
after=$(git status --porcelain -- . ':(exclude)outputs/logs' 2>/dev/null | wc -l | tr -d ' ')
echo "$log: exit=$code, 실행 뒤 바뀐 파일 $after개 (0이 아니면 추적 파일을 실행이 바꿨다)"
exit "$code"
