#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""掌握度记账：一个 KP 一行，档位写在 `syllabus/{408,math1}.md` 主键表的「掌握」列。

为什么取代 reviews/REVIEWS.md：旧表是「到期调度」（R1/R2/R3 + 到期日），实测 20 条全部
`R1 待`、7 天一条没推进——**调度不执行就等于没有**。现在只记「我现在到哪一档」，
什么时候再碰由做题结果决定，不由日历决定。

五档（判据写死在 README §掌握度）：
    M0 未读 / M1 能认 / M2 能默 / M3 限时对 / M4 步骤满

用法：
    python3 tools/mastery.py                 # 分布总览
    python3 tools/mastery.py --list M0       # 列出某档（含 M3+ / M0 这种筛选）
    python3 tools/mastery.py --set 408-CO-0305 M3
    python3 tools/mastery.py --check         # 只校验值域（lint 用）
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ("408.md", "math1.md")
TIERS = ("M0", "M1", "M2", "M3", "M4")
ROW = re.compile(r"^\|\s*`((?:408|M1)-[A-Z]{2,4}-\d{2,8})`")


def rows(path):
    """返回 [(行号, KP, 名称, 文件, 档位)]，行号从 0 起。"""
    out = []
    for i, ln in enumerate(path.read_text(encoding="utf-8").split("\n")):
        m = ROW.match(ln)
        if not m:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        out.append((i, m.group(1), cells[1] if len(cells) > 1 else "",
                    cells[5].strip("`") if len(cells) > 5 else "",
                    cells[-1] if len(cells) >= 7 else "?"))
    return out


def collect():
    all_rows = []
    for name in FILES:
        p = ROOT / "syllabus" / name
        if p.exists():
            for r in rows(p):
                all_rows.append((name, *r))
    return all_rows


def main():
    args = sys.argv[1:]
    data = collect()
    if "--check" in args:
        bad = [(f, kp, t) for f, _, kp, _, _, t in data if t not in TIERS]
        for b in bad:
            print(f"✗ 掌握列不合法：{b[0]} {b[1]} = {b[2]}")
        print(f"掌握列 {len(data)} 行，非法 {len(bad)} 行")
        sys.exit(1 if bad else 0)

    if "--set" in args:
        i = args.index("--set")
        kp, tier = args[i + 1], args[i + 2].upper()
        if tier not in TIERS:
            sys.exit(f"档位只能是 {'/'.join(TIERS)}")
        hit = 0
        for name in FILES:
            p = ROOT / "syllabus" / name
            lines = p.read_text(encoding="utf-8").split("\n")
            for j, ln in enumerate(lines):
                m = ROW.match(ln)
                if not m or m.group(1) != kp:
                    continue
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if len(cells) < 7:
                    sys.exit(f"{kp} 没有掌握列，先跑结构脚本")
                cells[-1] = tier
                lines[j] = "| " + " | ".join(cells) + " |"
                hit += 1
            p.write_text("\n".join(lines), encoding="utf-8")
        print(f"{kp} → {tier}" if hit else f"✗ 找不到 {kp}")
        sys.exit(0 if hit else 1)

    if "--list" in args:
        tier = args[args.index("--list") + 1].upper()
        for f, _, kp, nm, t in data:
            if t == tier:
                print(f"{kp}  {nm}")
        sys.exit(0)

    cnt = Counter(t for *_, t in data)
    print("档位        408   数一   合计")
    for t in TIERS:
        a = sum(1 for f, _, _, _, _, x in data if x == t and f == "408.md")
        b = sum(1 for f, _, _, _, _, x in data if x == t and f == "math1.md")
        print(f"{t}         {a:>3}   {b:>3}   {a + b:>4}")
    done = cnt["M3"] + cnt["M4"]
    print(f"\nM3 以上（限时做对）：{done} / {len(data)}")
    print("记一档：python3 tools/mastery.py --set 408-CO-0305 M3")


if __name__ == "__main__":
    main()
