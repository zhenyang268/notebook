#!/bin/bash
set -u
cd "$(dirname "$0")" || exit 1
printf '%-5s %-9s %8s\n' ID 状态 字节
for f in state/*.status; do
  [ -e "$f" ] || continue
  id=$(basename "$f" .status)
  st=$(cat "$f")
  if [ -f "out/$id.md" ]; then sz=$(wc -c < "out/$id.md" | tr -d ' '); else sz=0; fi
  printf '%-5s %-9s %8s\n' "$id" "$st" "$sz"
done
echo "---"
echo "pending=$(grep -l '^pending$' state/*.status 2>/dev/null | wc -l | tr -d ' ') running=$(grep -l '^running$' state/*.status 2>/dev/null | wc -l | tr -d ' ') done=$(grep -l '^done$' state/*.status 2>/dev/null | wc -l | tr -d ' ') failed=$(grep -l '^failed$' state/*.status 2>/dev/null | wc -l | tr -d ' ')"