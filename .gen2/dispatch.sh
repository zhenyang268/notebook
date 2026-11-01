#!/bin/bash
# 派发器：只启动 pending 任务，最多 MAXPAR 个并发，启动后立即返回。
set -u
cd "$(dirname "$0")" || exit 1

BL=/Users/apple/.local/bin/bl
MAXPAR=${MAXPAR:-3}
export BAILIAN_CALLER_TYPE=agent
export BAILIAN_CALLER_NAME=codebuddy
export BAILIAN_SKILL_NAME=bailian-cli
export BAILIAN_SKILL_VERSION=2.7.1
export NO_COLOR=1

running=$(grep -l '^running$' state/*.status 2>/dev/null | wc -l | tr -d ' ')
slots=$(( MAXPAR - running ))
if [ "$slots" -le 0 ]; then
  echo "running=$running 已满 ($MAXPAR)"
  exit 0
fi

started=0
while IFS=$'\t' read -r tid model; do
  [ -z "${tid:-}" ] && continue
  [ "$started" -ge "$slots" ] && break
  st=$(cat "state/$tid.status" 2>/dev/null || echo pending)
  [ "$st" != "pending" ] && continue

  echo running > "state/$tid.status"
  nohup bash -c '
    cd "'"$PWD"'"
    "'"$BL"'" text chat --timeout 1800 --model "'"$model"'" \
      --system "$(cat sys2.txt)" --max-tokens 8000 \
      --message "$(cat prompts/'"$tid"'.md)" > "out/'"$tid"'.md" 2>&1
    rc=$?
    sz=$(wc -c < "out/'"$tid"'.md" 2>/dev/null | tr -d " ")
    if [ "${sz:-0}" -gt 500 ] && ! head -8 "out/'"$tid"'.md" | grep -qiE "^Error:|429|rate.?limit"; then
      echo done > "state/'"$tid"'.status"
    else
      echo failed > "state/'"$tid"'.status"
    fi
    exit $rc
  ' > /dev/null 2>&1 &

  started=$(( started + 1 ))
  echo "start  $tid  ($model)"
done < tasks.tsv

echo "本轮启动 $started 个；此前 running=$running"