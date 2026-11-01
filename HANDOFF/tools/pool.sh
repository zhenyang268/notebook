#!/bin/bash
# agent pool —— 面向长任务的子进程派发器
#
# 设计要点（每条都对应一次真实踩坑）：
#   1. 幂等：派发前用 pid 文件确认该任务没有活进程，避免重复跑。
#   2. 判据：done 必须同时满足「退出码 0」+「字节数 > MIN_BYTES」+「不含错误特征」。
#      只用 -s 判非空会被 1 字节的换行骗过（实测发生过）。
#   3. 限流：MAXPAR 控制并发，撞 429 会自动标 failed 并可重试。
#   4. 重试：failed 自动回到 pending，最多 RETRY 次，超过则 quarantine。
#   5. 背压：没有空位时直接返回，不阻塞调用方。
#   6. 可观测：state/<id>.status 是唯一状态真源，一行一个状态。
#
# 用法：
#   ./pool.sh dispatch            # 有空位就派，立即返回
#   ./pool.sh pump                # 常驻补位（内部循环调 dispatch）
#   ./pool.sh status              # 汇总
#   ./pool.sh reset <id>|failed   # 重置状态为重试
#
# tasks.tsv 每行：id <TAB> model <TAB> sysfile [<TAB> messages_file]

set -u
cd "$(dirname "$0")" || exit 1

BL=${BL:-/Users/apple/.local/bin/bl}
MAXPAR=${MAXPAR:-3}
MIN_BYTES=${MIN_BYTES:-800}
RETRY=${RETRY:-2}
TASKS=${TASKS:-tasks.tsv}
STATE=state
OUT=out

mkdir -p "$STATE" "$OUT"

export BAILIAN_CALLER_TYPE=agent
export BAILIAN_CALLER_NAME=codebuddy
export BAILIAN_SKILL_NAME=bailian-cli
export BAILIAN_SKILL_VERSION=2.7.1
export NO_COLOR=1

alive() {  # 该任务的进程是否还活着（用 pid 文件判，不用状态字段）
  local id=$1
  local pf="$STATE/$id.pid"
  [ -f "$pf" ] || return 1
  local pid
  pid=$(cat "$pf" 2>/dev/null)
  [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null
}

cmd_status() {
  local p=0 r=0 d=0 f=0 q=0
  for s in "$STATE"/*.status; do
    [ -e "$s" ] || continue
    case "$(cat "$s")" in
      pending) p=$((p+1));; running) r=$((r+1));;
      done) d=$((d+1));; failed) f=$((f+1));; quarantine) q=$((q+1));;
    esac
  done
  echo "pending=$p running=$r done=$d failed=$f quarantine=$q"
}

cmd_dispatch() {
  local slots started=0
  local run=0
  for s in "$STATE"/*.status; do
    [ -e "$s" ] || continue
    [ "$(cat "$s")" = running ] && run=$((run+1))
  done
  slots=$(( MAXPAR - run ))
  [ "$slots" -le 0 ] && return 0

  while IFS=$'\t' read -r tid model sysf msgf; do
    [ -z "${tid:-}" ] && continue
    [ "$started" -ge "$slots" ] && break
    local st; st=$(cat "$STATE/$tid.status" 2>/dev/null || echo pending)
    [ "$st" = pending ] || continue
    alive "$tid" && continue          # 幂等：已有活进程就不再派

    echo running > "$STATE/$tid.status"
    nohup bash -c '
      cd "'"$PWD"'"
      out="out/'"$tid"'.md"
      if [ -n "'"${msgf:-}"'" ]; then
        "'"$BL"'" text chat --timeout 1800 --model "'"$model"'" \
          --system "$(cat '"${sysf:-sys.txt}"')" --max-tokens 8000 \
          --messages-file "'"$msgf"'" > "$out" 2>&1
      else
        "'"$BL"'" text chat --timeout 1800 --model "'"$model"'" \
          --system "$(cat '"${sysf:-sys.txt}"')" --max-tokens 8000 \
          --message "$(cat prompts/'"$tid"'.md)" > "$out" 2>&1
      fi
      rc=$?
      sz=$(wc -c < "$out" 2>/dev/null | tr -d " ")
      sz=${sz:-0}
      ok=1
      [ "$rc" -ne 0 ] && ok=0
      [ "$sz" -lt "'"$MIN_BYTES"'" ] && ok=0
      head -8 "$out" | grep -qiE "^Error:|429|rate.?limit|Request timed out" && ok=0
      if [ "$ok" -eq 1 ]; then
        echo done > "state/'"$tid"'.status"
      else
        echo failed > "state/'"$tid"'.status"
      fi
      rm -f "state/'"$tid"'.pid"
    ' > /dev/null 2>&1 &

    echo $! > "$STATE/$tid.pid"
    started=$(( started + 1 ))
    echo "dispatch $tid"
  done < "$TASKS"
  [ "$started" -gt 0 ] && echo "本轮派出 $started 个"
}

cmd_retry() {
  local n=0
  for s in "$STATE"/*.status; do
    [ -e "$s" ] || continue
    [ "$(cat "$s")" = failed ] || continue
    local id; id=$(basename "$s" .status)
    local c="$STATE/$id.retry"
    local k=0; [ -f "$c" ] && k=$(cat "$c")
    if [ "$k" -ge "$RETRY" ]; then
      echo quarantine > "$s"; echo "quarantine $id"
    else
      echo $((k+1)) > "$c"; echo pending > "$s"; echo "retry $id ($((k+1))/$RETRY)"; n=$((n+1))
    fi
  done
  [ "$n" -eq 0 ] && echo "无可重试任务"
}

cmd_reset() {
  local target=${1:-}
  if [ "$target" = failed ] || [ -z "$target" ]; then
    for s in "$STATE"/*.status; do
      [ -e "$s" ] || continue
      [ "$(cat "$s")" = failed ] && echo pending > "$s"
    done
    echo "已把 failed 全部重置为 pending"
  else
    echo pending > "$STATE/$target.status"
    rm -f "$STATE/$target.retry" "$STATE/$target.pid"
    echo "reset $target"
  fi
}

cmd_pump() {
  local idle=0
  while :; do
    cmd_retry > /dev/null 2>&1
    cmd_dispatch > /dev/null 2>&1
    local p=0 r=0
    for s in "$STATE"/*.status; do
      [ -e "$s" ] || continue
      case "$(cat "$s")" in
        pending) p=$((p+1));; running) r=$((r+1));;
      esac
    done
    if [ "$p" -eq 0 ] && [ "$r" -eq 0 ]; then
      idle=$((idle+1))
      # 连续 3 次确认才退出，避免瞬间空档误判（实测踩过）
      [ "$idle" -ge 3 ] && { echo "all settled: $(cmd_status)"; exit 0; }
    else
      idle=0
    fi
    echo "$(date +%H:%M:%S) $(cmd_status)" >> pump.log
    sleep 12
  done
}

case "${1:-dispatch}" in
  dispatch) cmd_dispatch;;
  pump) cmd_pump;;
  status) cmd_status;;
  retry) cmd_retry;;
  reset) cmd_reset "${2:-}";;
  *) echo "usage: $0 {dispatch|pump|status|retry|reset [id|failed]}"; exit 1;;
esac