#!/usr/bin/env python3
"""复习到期计算：从 reviews/REVIEWS.md 读出每个 KP 的当前档位与日期，列出到期项。

用法：
    python3 tools/review.py                 # 查今天
    python3 tools/review.py 2026-11-02      # 查指定日期
    python3 tools/review.py --overdue       # 只列已逾期的
    python3 tools/review.py --pass 408-NET-0504
                                            # 标记某 KP 本轮通过（升档）+ 写回文件
    python3 tools/review.py --fail 408-NET-0504
                                            # 标记未通过（同档顺延到明天）

「通过」的日期推进规则：R1->R2（+3 天）、R2->R3（+7 天）、R3 之后写 `R3 已过`。
写回时只改该行的状态与对应日期列，不动其他行。
"""
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWS = ROOT / "reviews" / "REVIEWS.md"
STAGES = ("R1", "R2", "R3")


def load():
    rows = []
    for raw in REVIEWS.read_text(encoding="utf-8").split("\n"):
        if not raw.startswith("| `"):
            continue
        cols = [c.strip() for c in raw.strip("|").split("|")]
        rows.append({
            "raw": raw,
            "kp": cols[0].strip("`"),
            "name": cols[1],
            "file": cols[2].strip("`"),
            "first": cols[3],
            "dates": {"R1": cols[4], "R2": cols[5], "R3": cols[6]},
            "status": cols[7],
        })
    return rows


def due_date(row):
    m = re.search(r"(R[123])\s*(待|已过)", row["status"])
    if not m:
        return None, None
    stage, state = m.group(1), m.group(2)
    if state == "已过":
        return None, None
    try:
        return stage, dt.date.fromisoformat(row["dates"][stage])
    except ValueError:
        return None, None


def cmd_list(day, overdue_only=False):
    rows = load()
    due, future = [], []
    for r in rows:
        stage, d = due_date(r)
        if not stage:
            continue
        (due if d <= day else future).append((d, stage, r))
    due.sort()
    print(f"【复习到期】{day.isoformat()}　共 {len(due)} 项（在册 {len(rows)} 项）")
    if not due:
        print("  今天没有到期项。")
    for d, stage, r in due:
        late = (day - d).days
        flag = f"逾期 {late} 天" if late else "今日"
        print(f"  · {stage} {flag:8s} {r['kp']:14s} {r['name']}　[{r['file']}]")
    if not overdue_only and future:
        nxt = min(f[0] for f in future)
        print(f"\n最近一批未到期：{nxt.isoformat()}（{sum(1 for f in future if f[0] == nxt)} 项）")


def rewrite(rows):
    text = REVIEWS.read_text(encoding="utf-8")
    for r in rows:
        text = text.replace(r["raw"], r["new_raw"])
    REVIEWS.write_text(text, encoding="utf-8")


def cmd_mark(kp, ok, day):
    rows = load()
    hit = [r for r in rows if r["kp"] == kp]
    if not hit:
        sys.exit(f"未找到 KP：{kp}")
    r = hit[0]
    stage, d = due_date(r)
    if not stage:
        sys.exit(f"{kp} 当前状态为「{r['status']}」，无可推进档位")
    if ok:
        i = STAGES.index(stage)
        if i == len(STAGES) - 1:
            r["status"] = "R3 已过"
        else:
            ns = STAGES[i + 1]
            gap = 3 if ns == "R2" else 7
            r["dates"][ns] = (day + dt.timedelta(days=gap)).isoformat()
            r["status"] = f"{ns} 待"
    else:
        r["dates"][stage] = (day + dt.timedelta(days=1)).isoformat()
    m = re.match(r"(\| `[^`]+` \| [^|]+ \| [^|]+ \| [^|]+ \|)([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|", r["raw"])
    if not m:
        sys.exit("行格式无法解析，请手工修改")
    r["new_raw"] = (f"{m.group(1)} {r['dates']['R1']} | {r['dates']['R2']} | {r['dates']['R3']} "
                    f"| {r['status']} |")
    rewrite([r])
    print(f"{kp}：{stage} {'通过' if ok else '未通过'} → 状态「{r['status']}」"
          f"　R1={r['dates']['R1']} R2={r['dates']['R2']} R3={r['dates']['R3']}")
    print("提示：把这次结果也写进对应 KP 文件末尾的「复习记录」小节。")


def main():
    args = [a for a in sys.argv[1:]]
    today = dt.date.today()
    if "--pass" in args or "--fail" in args:
        ok = "--pass" in args
        kp = args[args.index("--pass" if ok else "--fail") + 1]
        return cmd_mark(kp, ok, today)
    day = today
    for a in args:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", a):
            day = dt.date.fromisoformat(a)
    return cmd_list(day, overdue_only="--overdue" in args)


if __name__ == "__main__":
    main()
