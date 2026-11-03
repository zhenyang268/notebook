#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaoyan 规模统计：**全库数量的唯一真源**。

为什么要有这个文件：2026-11-04 体检发现「KP 数」在四个文档里写成 183 / 184 / 197 三个值，
「项目数」写成 24 / 10 / 九个，真题库写成 2021–2024 而实际是 2016–2024。
数字手写在多处必然歪，所以收归一处：本脚本算，`STATS.md` 记，其它文档只引用。

用法：
  python3 tools/stats.py            # 打印
  python3 tools/stats.py --write    # 重写 STATS.md（带内容指纹）
  python3 tools/stats.py --check    # STATS.md 是否过时（lint 调它）
  python3 tools/stats.py --json     # 机器可读
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # kaoyan/
REPO = ROOT.parent
OUT = ROOT / "STATS.md"
MARK = "<!-- stats-hash: %s -->"


def count_lines(paths):
    n = 0
    for p in paths:
        try:
            n += len(p.read_text(encoding="utf-8").split("\n")) - 1
        except Exception:
            pass
    return n


def mds(d):
    return sorted(p for p in d.rglob("*.md")) if d.exists() else []


def collect():
    s = {}

    # —— syllabus：KP 以主键表的行首编号为准（模板：| `408-DS-0101` | …）
    kp = {}
    for name, pref in (("408", r"408"), ("math1", r"M1"), ("english1", r"E1"), ("politics", r"P1")):
        f = ROOT / "syllabus" / f"{name}.md"
        ids = set(re.findall(rf"`({pref}-[A-Z]{{2,3}}-[\d]{{2,8}})`", f.read_text(encoding="utf-8"))) if f.exists() else set()
        kp[name] = len(ids)
    s["kp"] = kp
    s["kp_main"] = kp["408"] + kp["math1"]
    s["kp_total"] = sum(kp.values())

    # —— note / exam
    note = mds(ROOT / "note")
    s["note_files"] = len(note)
    s["note_lines"] = count_lines(note)

    ex = [p for p in mds(ROOT / "exam")
          if p.name not in ("README.md", "ROADMAP.md")
          and not any(x.startswith("真题") for x in p.relative_to(ROOT / "exam").parts)]
    s["exam_chapters"] = len(ex)
    s["exam_lines"] = count_lines(ex)

    zt = ROOT / "exam" / "真题"
    years = sorted(p for p in zt.glob("*.md") if re.fullmatch(r"20\d\d", p.stem)) if zt.exists() else []
    s["zhenti_years"] = len(years)
    s["zhenti_span"] = f"{years[0].stem}–{years[-1].stem}" if years else "—"
    s["zhenti_questions"] = sum(
        len(re.findall(r"^### \d+\.", p.read_text(encoding="utf-8"), re.M)) for p in years)

    zs = ROOT / "exam" / "真题专项"
    s["zhenti_special"] = len([p for p in mds(zs) if p.name != "README.md"]) if zs.exists() else 0

    # —— drill
    dr = mds(ROOT / "drill")
    lines_ = [p for p in dr if p.name not in ("README.md", "DESIGN.md")]
    s["drill_lines"] = len(lines_)
    s["drill_lines_408"] = len([p for p in lines_ if p.parent.name == "408"])
    s["drill_lines_math1"] = len([p for p in lines_ if p.parent.name == "math1"])
    body = "".join(p.read_text(encoding="utf-8") for p in lines_)
    for t in ("L1", "L2", "L3"):
        s[f"drill_{t}"] = len(re.findall(rf"^### {t}-\d+ ", body, re.M))
    s["drill_questions"] = s["drill_L1"] + s["drill_L2"] + s["drill_L3"]
    s["drill_anchors"] = body.count("**结果锚点**")

    # —— words / reviews / projects
    s["words_files"] = len(mds(ROOT / "words"))
    s["reviews_rows"] = len(re.findall(r"^\|\s*`[A-Z0-9]", (ROOT / "reviews" / "REVIEWS.md").read_text(encoding="utf-8"), re.M))
    pj = REPO / "projects"
    s["projects"] = len([d for d in pj.iterdir() if d.is_dir()]) if pj.exists() else 0

    # —— 分层行数（只统计正文，便于看"哪层虚"）
    s["lines"] = {k: count_lines(mds(ROOT / k)) for k in ("syllabus", "quick", "note", "exam", "drill", "words")}
    return s


def fingerprint(s):
    return hashlib.sha1(json.dumps(s, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def render(s):
    L = s["lines"]
    return f"""# STATS.md — 规模统计（**由脚本生成，勿手改**）

> 生成命令：`cd kaoyan && python3 tools/stats.py --write`
> 本文件是**全库数量的唯一真源**。任何文档要报数量，引用本页，不要在正文里手写——
> 2026-11-04 体检时「KP 数」曾同时存在 183 / 184 / 197 三个值，「项目数」存在 24 / 10 / 九个三个值。
> `tools/lint.py` 会校验本页是否为最新（跑 stats.py 重算指纹）。

{MARK % fingerprint(s)}

## 一、考纲与文档覆盖

| 项 | 数量 | 说明 |
|---|---|---|
| 408 考点（KP） | **{s['kp']['408']}** | `syllabus/408.md` 主键表行数 |
| 数一考点（KP） | **{s['kp']['math1']}** | `syllabus/math1.md` |
| 英一 / 政治条目 | {s['kp']['english1']} / {s['kp']['politics']} | 非 KP 主键，按题型/模块计 |
| 主键 KP（408 + 数一） | **{s['kp_main']}** | 与 `note/` 文件数应相等 |
| KP 合计 | **{s['kp_total']}** | 再加英一 {s['kp']['english1']} / 政治 {s['kp']['politics']} |
| `note/` 考点文件 | **{s['note_files']}** | 一考点一文件（粒度锁） |
| `exam/` 章文件 | **{s['exam_chapters']}** | 一章一文件（不含 `真题/`、`真题专项/`） |

## 二、真题库

| 项 | 数量 | 说明 |
|---|---|---|
| 年份文件 | **{s['zhenti_years']}** | `exam/真题/<年>.md` |
| 年份跨度 | {s['zhenti_span']} | |
| 题目数 | **{s['zhenti_questions']}** | 全部为**选择题**；综合题原卷未收 |
| 真题专项篇 | {s['zhenti_special']} | `exam/真题专项/` |

## 三、难度阶梯 `drill/`

| 项 | 数量 | 说明 |
|---|---|---|
| 题型线 | **{s['drill_lines']}** | 408 {s['drill_lines_408']} 条（题号 41–47）+ 数一 {s['drill_lines_math1']} 条 |
| 题目数 | **{s['drill_questions']}** | L1 {s['drill_L1']} / L2 {s['drill_L2']} / L3 {s['drill_L3']} |
| 结果锚点 | {s['drill_anchors']} | 应等于题目数（一题一条） |

## 四、其它

| 项 | 数量 | 说明 |
|---|---|---|
| `words/` 文件 | {s['words_files']} | 30 主题组 + 补全表 |
| `reviews/` 行 | {s['reviews_rows']} | 一个 KP 一行 |
| `projects/` 项目目录 | {s['projects']} | 副线，初试前冻结 |

## 五、各层行数（看"哪层虚"）

| 层 | 行数 |
|---|---|
| `syllabus/` | {L['syllabus']} |
| `quick/` | {L['quick']} |
| `note/` | {L['note']} |
| `exam/` | {L['exam']} |
| `drill/` | {L['drill']} |
| `words/` | {L['words']} |
"""


def main():
    s = collect()
    if "--json" in sys.argv:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return
    if "--write" in sys.argv:
        OUT.write_text(render(s), encoding="utf-8")
        print(f"写 {OUT.relative_to(REPO)}（指纹 {fingerprint(s)}）")
        return
    if "--check" in sys.argv:
        if not OUT.exists():
            print("✗ 缺 STATS.md，跑 python3 tools/stats.py --write")
            sys.exit(1)
        txt = OUT.read_text(encoding="utf-8")
        m = re.search(r"stats-hash: ([0-9a-f]+)", txt)
        if not m or m.group(1) != fingerprint(s):
            print("✗ STATS.md 已过时，跑 python3 tools/stats.py --write")
            sys.exit(1)
        print(f"STATS.md 最新（{m.group(1)}）")
        return
    for k, v in s.items():
        print(f"{k:22} {v}")


if __name__ == "__main__":
    main()