#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真题落点：从 `exam/真题/<年>.md` 里的 `→ ``DS-02``` 标注**生成** syllabus 的落点行。

为什么改成生成：原先落点行手写在 `syllabus/408.md`，写的是「（2021–2024）」，
而真题库实际有 2016–2024 九年、每题末尾都带 KP 标注。手写的代价是
①少报 5 年 ②每加一年都要回头改 25 处 ③改漏了没人发现。
现在：脚本算，`--check` 进 lint，落点行不会再歪。

用法：
  python3 tools/landing.py --dry      # 只看差异
  python3 tools/landing.py --write    # 重写落点行
  python3 tools/landing.py --check    # 是否与真题库一致（lint 调它）
  python3 tools/landing.py --missing  # 列出没打 KP 标注的题
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZT = ROOT / "exam" / "真题"
SYL = ROOT / "syllabus" / "408.md"

Q_HEAD = re.compile(r"^### (\d+)\.")
Q_BOLD = re.compile(r"^\*\*(\d+)\.\*\*")
KP = re.compile(r"→\s*`([A-Z]{2,3})-(\d{2})")


def parse_year(p):
    """返回 [(题号, 章代码)]；章代码形如 DS-02。"""
    out, cur = [], None
    for ln in p.read_text(encoding="utf-8").split("\n"):
        m = Q_HEAD.match(ln) or Q_BOLD.match(ln)
        if m:
            cur = int(m.group(1))
            continue
        m = KP.search(ln)
        if m and cur is not None:
            out.append((cur, f"{m.group(1)}-{m.group(2)}"))
            cur = None
    return out


def build():
    years = sorted(p.stem for p in ZT.glob("*.md") if re.fullmatch(r"20\d\d", p.stem))
    mapping, missing = {}, []
    for y in years:
        rows = parse_year(ZT / f"{y}.md")
        seen = {n for n, _ in rows}
        for n in range(1, 41):
            if n not in seen:
                missing.append((y, n))
        for n, ch in rows:
            mapping.setdefault(ch, []).append((int(y), n))
    return years, mapping, missing


def line_for(ch, years, mapping):
    rows = sorted(mapping.get(ch, []))
    if not rows:
        return f"> 真题落点（{years[0]}–{years[-1]}，按 KP 标注统计）：九年均无对应选择题（该章只在综合题里出现）"
    by_year = {}
    for y, n in rows:
        by_year.setdefault(y, []).append(n)
    seg = []
    for y in sorted(by_year):
        nums = "、".join(f"#{n}" for n in sorted(by_year[y]))
        seg.append(f"{y} {nums}")
    return f"> 真题落点（{years[0]}–{years[-1]}，按 KP 标注统计）：共 {len(rows)} 题 —— " + "；".join(seg)


def rewrite(dry=False):
    years, mapping, _ = build()
    lines = SYL.read_text(encoding="utf-8").split("\n")
    out, cur_ch, changed, bad = [], None, 0, []
    for i, ln in enumerate(lines):
        m = re.match(r"^### ([A-Z]{2,3})-(\d{2})\s", ln)
        if m:
            cur_ch = f"{m.group(1)}-{m.group(2)}"
        if ln.startswith("> 真题落点") and cur_ch:
            new = line_for(cur_ch, years, mapping)
            if ln != new:
                changed += 1
                if dry:
                    print(f"[{cur_ch}] {ln[:60]}…\n      → {new[:80]}…")
            out.append(new)
            continue
        out.append(ln)
    if not dry:
        SYL.write_text("\n".join(out), encoding="utf-8")
    return changed


def main():
    if "--missing" in sys.argv:
        years, _, missing = build()
        print(f"未打 KP 标注的题 {len(missing)} 道：" + "、".join(f"{y}#{n}" for y, n in missing))
        return
    if "--check" in sys.argv:
        years, mapping, _ = build()
        lines = SYL.read_text(encoding="utf-8").split("\n")
        cur, bad = None, 0
        for ln in lines:
            m = re.match(r"^### ([A-Z]{2,3})-(\d{2})\s", ln)
            if m:
                cur = f"{m.group(1)}-{m.group(2)}"
            if ln.startswith("> 真题落点") and cur:
                if ln != line_for(cur, years, mapping):
                    bad += 1
        if bad:
            print(f"✗ syllabus/408.md 有 {bad} 处落点行与真题库不一致，跑 python3 tools/landing.py --write")
            sys.exit(1)
        print("落点行与真题库一致")
        return
    n = rewrite(dry="--dry" in sys.argv)
    if "--dry" in sys.argv:
        print(f"将改 {n} 行")
    else:
        print(f"已改 {n} 行")


if __name__ == "__main__":
    main()