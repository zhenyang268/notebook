#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""drill 做题记录：把「做没做、对没对」落成数据，否则「限时正确率」永远是嘴上说的。

为什么要工具而不是手记：`drill/DESIGN.md` §7 第 3 层要求按档统计正确率
（过关线 L1 ≥90% / L2 ≥70% / L3 ≥40%）。手记 119 行必然漏、且算不出分档正确率。

用法：
  python3 tools/drill_log.py add 41-L1-1 对 4 "模板背下来了"    # 记一条
  python3 tools/drill_log.py stat                              # 分档统计 + 必做集进度
  python3 tools/drill_log.py todo                              # 还差哪些必做题
"""
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "drill" / "LOG.md"
DRILL = ROOT / "drill"
HEAD = """# LOG.md — drill 做题记录

> **本页由 `tools/drill_log.py add` 追加，不要整页手改表头。**
> 结果三档：`对`（自己算对）/ `部分`（思路对、算错或缺步）/ `错`（没思路）。
> 过关线（`DESIGN.md` §7）：L1 ≥90% / L2 ≥70% / L3 ≥40%，按「对」计。
> 必做集 81 题：L1 全部 39 + L2 每线 2 + L3 每线 1。

| 日期 | 题号 | 结果 | 用时(min) | 备注 |
|---|---|---|---|---|
"""


def all_questions():
    """{题号: (线, 档)}；题号形如 41-L1-1。"""
    out = {}
    for f in sorted(DRILL.glob("408/*.md")) + sorted(DRILL.glob("math1/*.md")):
        no = f.stem.split("-")[0]
        for m in re.finditer(r"^### (L[123])-(\d+) ", f.read_text(encoding="utf-8"), re.M):
            out[f"{no}-{m.group(1)}-{m.group(2)}"] = (no, m.group(1))
    return out


def rows():
    if not LOG.exists():
        return []
    out = []
    for ln in LOG.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^\|\s*(\d{4}-\d\d-\d\d)\s*\|\s*([0-9m]+-L[123]-\d+)\s*\|\s*(对|部分|错)\s*\|\s*([\d.]+)\s*\|\s*(.*?)\s*\|", ln)
        if m:
            out.append(m.groups())
    return out


def cmd_add(argv):
    if len(argv) < 2:
        print("用法：add <题号> <对|部分|错> [用时分钟] [备注]")
        return 1
    qid, verdict = argv[0], argv[1]
    mins = argv[2] if len(argv) > 2 else "0"
    note = argv[3] if len(argv) > 3 else ""
    qs = all_questions()
    if qid not in qs:
        near = [k for k in qs if k.endswith(qid.split("-", 1)[-1])][:5]
        print(f"✗ 题号 {qid} 不存在。形如 41-L1-1。可能是：{near}")
        return 1
    if verdict not in ("对", "部分", "错"):
        print("✗ 结果只能是 对 / 部分 / 错")
        return 1
    if not LOG.exists():
        LOG.write_text(HEAD, encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"| {dt.date.today()} | {qid} | {verdict} | {mins} | {note} |\n")
    print(f"记 {qid} → {verdict}")
    return 0


def cmd_stat(_argv):
    qs = all_questions()
    rs = rows()
    line_of = {k: v[0] for k, v in qs.items()}
    tier_of = {k: v[1] for k, v in qs.items()}
    seen, good = {t: 0 for t in ("L1", "L2", "L3")}, {t: 0 for t in ("L1", "L2", "L3")}
    used = set()
    for _d, qid, v, _m, _n in rs:
        if qid not in qs:
            continue
        t = tier_of[qid]
        seen[t] += 1
        if v == "对":
            good[t] += 1
        used.add(qid)
    print(f"记录 {len(rs)} 条，覆盖 {len(used)}/{len(qs)} 题（共 {len(qs)}）\n")
    print("| 档 | 做过 | 对 | 正确率 | 过关线 | 判定 |")
    print("|---|---|---|---|---|---|")
    need = {"L1": 90, "L2": 70, "L3": 40}
    for t in ("L1", "L2", "L3"):
        n = sum(1 for k in qs if tier_of[k] == t)
        rate = (good[t] / seen[t] * 100) if seen[t] else 0
        flag = "— 没开始" if seen[t] == 0 else ("过" if rate >= need[t] else "**没过**")
        print(f"| {t} | {seen[t]}/{n} | {good[t]} | {rate:.0f}% | ≥{need[t]}% | {flag} |")
    # 必做集：L1 全部 + 每条线 L2 前 2 + L3 前 1
    must = set()
    lines = sorted({line_of[k] for k in qs})
    for ln in lines:
        for i in (1, 2):
            must.add(f"{ln}-L2-{i}")
        must.add(f"{ln}-L3-1")
    must |= {k for k in qs if tier_of[k] == "L1"}
    must &= set(qs)
    miss = sorted(must - used)
    print(f"\n必做集 {len(must & set(qs))} 题，已做 {len(must & used)}，还差 {len(miss)}")
    return 0


def cmd_todo(_argv):
    qs = all_questions()
    rs = rows()
    used = {r[1] for r in rs}
    tier_of = {k: v[1] for k, v in qs.items()}
    line_of = {k: v[0] for k, v in qs.items()}
    lines = sorted({line_of[k] for k in qs})
    must = {k for k in qs if tier_of[k] == "L1"}
    for ln in lines:
        must |= {f"{ln}-L2-1", f"{ln}-L2-2", f"{ln}-L3-1"}
    must &= set(qs)
    for k in sorted(must - used):
        print(k)
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stat"
    return {"add": cmd_add, "stat": cmd_stat, "todo": cmd_todo}.get(cmd, cmd_stat)(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())