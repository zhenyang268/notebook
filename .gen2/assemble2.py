# -*- coding: utf-8 -*-
"""把分块结果拼成按大纲详解的四份文件。"""
import re
import sys
from pathlib import Path

GEN = Path(__file__).parent
Q = GEN.parent / 'kaoyan' / 'quick'

SUP = str.maketrans({'⁰':'0','¹':'1','²':'2','³':'3','⁴':'4',
                     '⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9'})

def clean(t):
    t = re.sub(r'\\\((.+?)\\\)', lambda m: '$' + m.group(1) + '$', t)
    t = re.sub(r'\\\[(.+?)\\\]', lambda m: '$$' + m.group(1) + '$$', t, flags=re.S)
    t = re.sub(r'^\s*```[a-zA-Z]*\n(.*)\n```\s*$', r'\1', t, flags=re.S)
    t = re.sub(r'([0-9A-Za-z]+)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)',
               lambda m: '$' + m.group(1) + '^{' + m.group(2).translate(SUP) + '}$', t)
    t = re.sub(r'([0-9A-Za-z]+)\$\^\{([0-9]+)\}\$', r'$\1^{\2}$', t)
    t = t.replace('log₂', r'$\log_2$')
    t = re.sub(r'(?<=[0-9A-Za-z])[₀₁₂₃₄₅₆₇₈₉]+', '', t)
    t = re.sub(r'^\s*好的[，,].*?\n', '', t)
    t = re.sub(r'^\s*以下是.*?\n', '', t)
    return t.strip()

def demote(t, n=1):
    for _ in range(n):
        t = re.sub(r'^(#{1,5})\s+', lambda m: '#' * (len(m.group(1)) + 1) + ' ', t, flags=re.M)
    return t


def load_kp_index():
    """(章号, 序号) -> (KP, 节名)；用于把模型写的 'DS-01.1' 还原成考纲主键。"""
    syl = GEN.parent / 'kaoyan' / 'syllabus'
    idx, kpname = {}, {}
    for f in ('408.md', 'math1.md'):
        p = syl / f
        if not p.exists():
            continue
        cur = None
        for line in p.read_text(encoding='utf-8').split('\n'):
            m = re.match(r'^###\s+(\S+)', line)
            if m:
                cur = m.group(1)
                continue
            m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|', line)
            if m and cur:
                kp, name = m.group(1), m.group(2)
                if re.match(r'^(408|M1)-', kp):
                    cnt = sum(1 for k in idx if k[0] == cur) + 1
                    idx[(cur, cnt)] = kp
                    kpname[kp] = name
    return idx, kpname


KP_IDX, KP_NAME = load_kp_index()


def normalize_heading(t):
    """把所有 `### xxx 节名` 统一成 `### <考纲主键> <节名>`。"""
    def repl(m):
        ident, name = m.group(1), m.group(2)
        if re.match(r'^(408|M1)-[A-Z]+-', ident):
            return f'### {ident} {KP_NAME.get(ident, name)}'
        mm = re.match(r'^([A-Z]+-\d+)\.(\d+)$', ident)
        if mm:
            kp = KP_IDX.get((mm.group(1), int(mm.group(2))))
            if kp:
                return f'### {kp} {KP_NAME.get(kp, name)}'
        return m.group(0)
    return re.sub(r'^###\s+(\S+)\s+(.+)$', repl, t, flags=re.M)

JOBS = [
    ('408.md', '# 408 · 按大纲详解',
     '> 按 `syllabus/408.md` 的章序与考点编号逐条展开，共 25 章 112 个考点。\n'
     '> 每条给出「是什么 → 关键公式或机制 → 一个典型计算或易错点」。\n'
     '> 需要更深的内容去 `exam/`（一个考点一个文件），需要刷题去 `exam/真题专项/`。',
     [('d1','一、数据结构','DS'), ('d2','一、数据结构','DS'), ('d3','一、数据结构','DS'),
      ('c1','二、计算机组成原理','CO'), ('c2','二、计算机组成原理','CO'), ('c3','二、计算机组成原理','CO'),
      ('o1','三、操作系统','OS'), ('o2','三、操作系统','OS'),
      ('n1','四、计算机网络','NET'), ('n2','四、计算机网络','NET')]),

    ('math1.md', '# 数学一 · 按大纲详解',
     '> 按 `syllabus/math1.md` 的章序与考点编号逐条展开，共 22 章 72 个考点。\n'
     '> 每条给出「定义/结论 → 关键公式或推导思路 → 典型计算或易错点」。\n'
     '> 数一的题型高度固定，把每条里的「起手式」练成条件反射比刷题量重要。',
     [('h1','一、高等数学','HS'), ('h2','一、高等数学','HS'), ('h3','一、高等数学','HS'),
      ('l1a','二、线性代数','LA'), ('l1b','二、线性代数','LA'),
      ('q1a','三、概率论与数理统计','PS'), ('q1b','三、概率论与数理统计','PS'),
      ('q2','三、概率论与数理统计','PS')]),

    ('english1.md', '# 英语一 · 按大纲详解',
     '> 按题型逐项展开。英语一是技能型科目，词汇与长难句属日拱，不在本文件范围。\n'
     '> 每条给出可操作的步骤，而不是泛泛而谈。',
     [('e1','一、题型与打法','E1')]),

    ('politics.md', '# 政治 · 按大纲详解',
     '> 按六个模块的 28 章逐条展开。分值口径：马原 22% / 新思想 22% / 史纲 15% / 思法 15% / 毛中特 13% / 时政 13%。\n'
     '> 每条给「核心考点 → 易混辨析 → 分析题怎么用」。时政随年度更新，本文件只给框架。',
     [('m1','一、马原与毛中特','P1'), ('m2','二、新思想与史纲','P1'),
      ('m3','三、思修法治与时政','P1')]),
]

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for out, title, intro, parts in JOBS:
        if only and only not in out:
            continue
        missing = [t for t, _, _ in parts
                   if not (GEN/'out'/(t+'.md')).exists()
                   or (GEN/'out'/(t+'.md')).stat().st_size < 800]
        if missing:
            print(f'SKIP {out}: 缺 {missing}')
            continue
        chunks, seen, last_sec = [], set(), None
        for tid, sec, _ in parts:
            body = clean((GEN/'out'/(tid+'.md')).read_text(encoding='utf-8'))
            body = normalize_heading(body)   # 先在 ### 层统一编号
            body = demote(body, 1)           # 再整体降一级
            head = ''
            if sec != last_sec:
                head = f'## {sec}\n\n'
                last_sec = sec
            chunks.append(head + body)
        text = f'{title}\n\n{intro}\n\n' + '\n\n'.join(chunks) + '\n'
        (Q/out).write_text(text, encoding='utf-8')
        n_ch = len(re.findall(r'^### ', text, flags=re.M))
        n_kp = len(re.findall(r'^#### ', text, flags=re.M))
        print(f'WROTE {out}  {len(text)} 字符  章 {n_ch}  节 {n_kp}')

if __name__ == '__main__':
    main()