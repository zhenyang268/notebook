#!/usr/bin/env python3
"""survey/ 同步校验（V1–V5）。

用法（在 notebook/ 下）::

    python3 math/survey/verify.py
    python3 math/survey/verify.py --graphics ~/develop/learning/graphics

退出码: 0 = CRIT 全过; 1 = 有 CRIT。
规约: math/survey/CONTRACT.md §7。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SURVEY = Path(__file__).resolve().parent
NOTEBOOK = SURVEY.parents[1]
DEFAULT_GRAPHICS = SURVEY.parents[2] / "graphics"

STATUS = ("已实现", "框架", "骨架", "未建", "缺位")
# 编号空间: 前缀 -> 该组最大序号。用于把「D19」这类规则编号排除在条目编号之外。
GROUPS = {"A": 6, "L": 10, "N": 13, "C": 6, "H": 11, "P": 10,
          "D": 8, "G": 10, "F": 9, "T": 7, "M": 7}

ID_RE = re.compile(r"\b([ALNCHPDGFTM])(\d{1,2})\b")
KNOW_HEAD = "\\begin{know}"
FIELD_RE = re.compile(r"\\field\{([^}]*)\}(.*?)(?=\\field\{|\\end\{know\})", re.S)


def _groups(text: str, pos: int, n: int) -> list[str]:
    """从 pos 起依次读 n 个平衡花括号组；名字里含 $A^{H}A$ 这类嵌套也能读对。"""
    got = []
    for _ in range(n):
        while pos < len(text) and text[pos] in " \t\r\n":
            pos += 1
        if pos >= len(text) or text[pos] != "{":
            raise ValueError("expect { at %d" % pos)
        depth, start = 0, pos
        while pos < len(text):
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
                if depth == 0:
                    pos += 1
                    break
            pos += 1
        got.append(text[start + 1:pos - 1].strip())
    return got


def scan_know(text: str):
    """-> [(正文起点, [编号, 名称, 状态])]"""
    out, pos = [], 0
    while True:
        i = text.find(KNOW_HEAD, pos)
        if i < 0:
            return out
        j = i + len(KNOW_HEAD)
        out.append((j, _groups(text, j, 3)))
        pos = j


def status_prefix(raw: str) -> str:
    """状态词只认开头那一个白名单词，后面的括号限定与冒号位置不参与判定。"""
    m = re.match(r"(已实现|框架|骨架|未建|缺位)", raw.strip())
    return m.group(1) if m else raw.strip()


def survey_tex() -> list[Path]:
    return sorted(p for p in SURVEY.glob("p*.tex"))


def parse_entries(files: list[Path]):
    """-> [(id, name, status_raw, prefix, fields, file)]"""
    out = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for m, args in scan_know(text):
            body = text[m:]
            fields = {k.strip(): v.strip() for k, v in FIELD_RE.findall(body)}
            prefix = status_prefix(args[2])
            out.append((args[0], args[1], args[2], prefix, fields, f.name))
    return out


def declared_counts() -> tuple[int | None, dict[str, int]]:
    """从 p1-overview.tex 读「共 N 条」与各状态声明数。"""
    text = (SURVEY / "p1-overview.tex").read_text(encoding="utf-8")
    total = re.search(r"共\s*\\textbf\{(\d+)\s*条\}", text)
    per = {}
    for st in STATUS:
        m = re.search(st + r"\s*\\textbf\{(\d+)\s*条\}", text)
        if m:
            per[st] = int(m.group(1))
    return (int(total.group(1)) if total else None), per


def audit_rows() -> dict[str, str]:
    """p11 映射表 -> {文件名: 状态}。第一列 \\texttt{...}。"""
    text = (SURVEY / "p11-audit.tex").read_text(encoding="utf-8")
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\s*\\texttt\{([^}]*)\}\s*&\s*([^&]*?)&", line)
        if m:
            rows[m.group(1).strip()] = m.group(2).strip()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graphics", type=Path, default=DEFAULT_GRAPHICS)
    args = ap.parse_args()

    crit: list[str] = []
    maj: list[str] = []
    skip: list[str] = []

    files = survey_tex()
    entries = parse_entries(files)
    ids = {e[0] for e in entries}
    rows = audit_rows()

    # ---- V1: 头文件 <=> p11 表 ----
    # p11 左列写法: `core/scalar.hpp`（省 src/）、`NOW: grid.hpp`（未建）、`autodiff/grad\_graph.hpp`（转义）
    gdir = args.graphics / "src"
    if not gdir.is_dir():
        skip.append("V1 跳过: 找不到 %s" % gdir)
    else:
        hpps = sorted(str(p.relative_to(args.graphics)) for p in gdir.rglob("*.hpp"))
        listed, planned = set(), set()
        for k in rows:
            k = k.replace("\\_", "_").strip()
            if k.startswith("NOW:"):
                planned.add(k[4:].strip())
            elif k.endswith(".hpp"):
                listed.add(k if k.startswith("src/") else "src/" + k)
        for h in hpps:
            if h not in listed:
                crit.append("V1 头文件未进 p11 映射表: %s" % h)
        for h in sorted(listed - set(hpps)):
            if h not in planned:
                crit.append("V1 p11 表里的文件已不存在: %s" % h)

    # ---- V2: 状态词白名单 ----
    for eid, name, raw, prefix, _fields, fname in entries:
        if prefix not in STATUS:
            crit.append("V2 状态词越界 %s %s: %r (%s)" % (eid, name, prefix, fname))

    # ---- V3: 计数一致性 ----
    total, per = declared_counts()
    actual: dict[str, int] = {}
    for *_x, prefix, _f, _fn in entries:
        actual[prefix] = actual.get(prefix, 0) + 1
    if total != len(entries):
        crit.append("V3 p1 声明总数 %s != 实际条目数 %d" % (total, len(entries)))
    for st in STATUS:
        want = per.get(st)
        got = actual.get(st, 0)
        if want is None:
            crit.append("V3 p1 缺状态声明: %s (实际 %d)" % (st, got))
        elif want != got:
            crit.append("V3 %s 声明 %d != 实际 %d" % (st, want, got))

    # ---- V4: 前置编号必须存在 ----
    def known(tok: str) -> bool:
        m = ID_RE.fullmatch(tok)
        if not m:
            return True
        letter, num = m.group(1), int(m.group(2))
        return tok in ids or num > GROUPS.get(letter, 0)

    for eid, name, _raw, _p, fields, fname in entries:
        pre = fields.get("前置", "")
        if not pre:
            crit.append("V4 %s 缺「前置」字段 (%s)" % (eid, fname))
            continue
        if "无" in pre and not ID_RE.search(pre):
            continue
        for tok in (m.group(0) for m in ID_RE.finditer(pre)):
            if not known(tok):
                crit.append("V4 %s 的前置 %s 不存在 (%s)" % (eid, tok, fname))

    # ---- V5: 缺位条目必须在 p11 缺口节出现 ----
    audit_text = (SURVEY / "p11-audit.tex").read_text(encoding="utf-8")
    for eid, name, _raw, prefix, _f, _fn in entries:
        if prefix == "缺位" and eid not in audit_text.replace("{}", ""):
            maj.append("V5 缺位条目 %s %s 未在 p11 缺口节登记" % (eid, name))

    # ---- 报告 ----
    print("survey/ 校验 | 条目 %d | 状态 %s" % (
        len(entries), " ".join("%s=%d" % (k, v) for k, v in sorted(actual.items()))))
    for tag, items in (("CRIT", crit), ("MAJ", maj), ("SKIP", skip)):
        for it in items:
            print("%-4s %s" % (tag, it))
    print("CRIT=%d MAJ=%d SKIP=%d" % (len(crit), len(maj), len(skip)))
    return 0 if not crit else 1


if __name__ == "__main__":
    sys.exit(main())