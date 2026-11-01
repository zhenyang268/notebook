#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一验收：文件齐全 / 字数下限 / 结构完整 / 考点覆盖率。

用法：
    python3 HANDOFF/tools/verify.py <目录或文件> [...]
    python3 HANDOFF/tools/verify.py kaoyan/quick
    python3 HANDOFF/tools/verify.py kaoyan/note
    python3 HANDOFF/tools/verify.py kaoyan/exam/真题

判据不是"跑完了"，而是下面四类检查全部 PASS。
退出码：0 全过；1 有失败。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # notebook/
KAOYAN = ROOT / 'kaoyan'
SYL = KAOYAN / 'syllabus'

FAIL = []
INFO = []

def fail(msg):
    FAIL.append(msg)

def info(msg):
    INFO.append(msg)

# ---------- 通用 ----------

def words(p):
    return len(re.sub(r'\s', '', p.read_text(encoding='utf-8')))

def check_common(p, min_chars):
    if not p.exists():
        fail(f'缺文件：{p.relative_to(ROOT)}')
        return False
    n = words(p)
    if n < min_chars:
        fail(f'过短：{p.relative_to(ROOT)} 只有 {n} 字符（下限 {min_chars}）')
    txt = p.read_text(encoding='utf-8')
    if re.match(r'^\s*好的[，,]', txt):
        fail(f'有前言：{p.relative_to(ROOT)}')
    # 只抓真正的定界符；LaTeX 行距 \\[2mm] 这类双反斜杠要排除
    if re.search(r'(?<!\\)\\\(|(?<!\\)\\\[', txt):
        fail(f'公式写法不合规（用了 \\( 或 \\[）：{p.relative_to(ROOT)}')
    return True

# ---------- quick ----------

QUICK = {
    '408-ds.md': 6000, '408-co.md': 6000, '408-os.md': 6000, '408-net.md': 6000,
    'math-hs.md': 6000, 'math-la.md': 6000, 'math-ps.md': 6000,
    'english.md': 5000, 'politics.md': 5000,
}

def verify_quick(d):
    for name, low in QUICK.items():
        p = d / name
        if not check_common(p, low):
            continue
        txt = p.read_text(encoding='utf-8')
        for seg in ('第一部分', '第二部分', '第三部分'):
            if seg not in txt:
                fail(f'{name} 缺「{seg}」（三合一结构不完整）')
    info(f'quick：检查 {len(QUICK)} 份')

# ---------- note（考点 × 真题） ----------

def verify_note(d):
    files = sorted(d.rglob('*.md'))
    if not files:
        fail('note 下没有任何 md 文件')
        return
    YEARS = {2021, 2022, 2023, 2024}      # exam/真题/ 里实际存在的年份，白名单
    tot_si, tot_keng = 0, 0
    for p in files:
        txt = p.read_text(encoding='utf-8')
        n_si = len(re.findall(r'\*\*思路[^*\n]*\*\*', txt))
        n_keng = len(re.findall(r'\*\*坑[^*\n]*\*\*', txt))
        tot_si += n_si
        tot_keng += n_keng
        if n_si == 0:
            fail(f'{p.relative_to(ROOT)} 没有「思路」段')
        if n_keng == 0:
            fail(f'{p.relative_to(ROOT)} 没有「坑」段')
        if n_si != n_keng:
            fail(f'{p.relative_to(ROOT)} 思路({n_si}) 与 坑({n_keng}) 数量不等')
        if '## 考法' not in txt:
            fail(f'{p.relative_to(ROOT)} 没有按「考法」分段')
        if re.search(r'答案[：:]\s*[A-D]\b', txt):
            fail(f'{p.relative_to(ROOT)} 出现了答案（本层不写答案）')
        bad = sorted({int(y) for y in re.findall(r'(20\d{2})\s*(?:年|#)', txt)} - YEARS)
        if bad:
            fail(f'{p.relative_to(ROOT)} 引用了真题库里不存在的年份 {bad}（只允许 2021–2024）')
    info(f'note：{len(files)} 个考点文件，思路 {tot_si} 条，坑 {tot_keng} 条')

# ---------- exam 真题 ----------

def verify_zhenti(d):
    files = sorted(d.glob('20*.md'))
    if not files:
        fail('真题下没有年份文件')
        return
    for p in files:
        y = p.stem
        txt = p.read_text(encoding='utf-8')
        if '版权' not in txt and '回忆' not in txt:
            fail(f'{y}.md 缺来源与版权说明')
        # 兼容两种题号写法：`### 1. 标题` 与 `**1.** 题干`
        n = len(re.findall(r'(?:^### \d+\.|^\*\*\d+[.．]\*\*)', txt, flags=re.M))
        if n < 30:
            fail(f'{y}.md 题目数偏少（{n}），选择题应有 40 题')
        # 缺图/缺表必须有标注（三种写法任选其一）
        if not re.search(r'缺图|原卷有图|原题附图', txt):
            fail(f'{y}.md 没有缺图说明（即使没有缺图也要写"无"）')
        # 每题必须带"要点"或"思路"，否则刷题时无从对照
        n_pt = len(re.findall(r'要点[：:]|\*\*思路\*\*', txt))
        if n_pt < n:
            fail(f'{y}.md 有 {n} 题但只有 {n_pt} 条要点/思路')
    info(f'真题：{len(files)} 个年份（{files[0].stem}–{files[-1].stem}）')

# ---------- exam 分章 ----------

def verify_exam(d):
    files = sorted(d.rglob('*.md'))
    if not files:
        fail(f'{d.name} 下没有章节文件')
        return
    # 段名两种写法都接受（TASKS.md 与早期模板措辞不同）
    SEGS = (('## 一、本章考点', '## 一、本章考点与档位'),
            ('## 二、正文',),
            ('## 三、真题落点',),
            ('## 四、易错', '## 四、易错清单'))
    for p in files:
        txt = p.read_text(encoding='utf-8')
        if 'ROADMAP' in p.name:
            continue
        for alts in SEGS:
            if not any(s in txt for s in alts):
                fail(f'{p.relative_to(ROOT)} 缺「{alts[0]}」段')
        n = words(p)
        if n < 1800:
            fail(f'过短：{p.relative_to(ROOT)} 只有 {n} 字符（章下限 1800）')
    info(f'{d.name}：{len(files)} 章')

# ---------- 覆盖率 ----------

def defined_kps(fname):
    p = SYL / fname
    if not p.exists():
        return []
    return list(dict.fromkeys(re.findall(
        r'`((?:408|M1)-[A-Z]{2,3}-\d{4})`', p.read_text(encoding='utf-8'))))

def verify_coverage(dirp, label):
    """检查 syllabus 的考点在目录里是否都有落点。"""
    want = []
    for f in ('408.md', 'math1.md'):
        want += defined_kps(f)
    if not want:
        return
    txt = ''
    for p in dirp.rglob('*.md'):
        txt += p.read_text(encoding='utf-8')
    got = set(re.findall(r'((?:408|M1)-[A-Z]{2,3}-\d{4})', txt))
    # 只统计 408 与 M1 的
    want = [k for k in want]
    missing = [k for k in want if k not in got]
    ratio = (len(want) - len(missing)) / len(want) * 100
    if missing:
        fail(f'{label} 覆盖率 {ratio:.0f}%，缺 {len(missing)} 个考点：{missing[:8]}'
             + (' …' if len(missing) > 8 else ''))
    else:
        info(f'{label} 覆盖率 100%（{len(want)} 个考点）')

# ---------- 入口 ----------

def dispatch(path):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        fail(f'路径不存在：{path}')
        return
    name = p.name
    if name == 'quick':
        verify_quick(p)
        verify_coverage(p, 'quick')
    elif name == 'note':
        verify_note(p)
        verify_coverage(p, 'note')
    elif name == '真题':
        verify_zhenti(p)
    elif p.is_dir() and (name in ('ds', 'co', 'os', 'net', 'hs', 'la', 'ps', '408', 'math1', 'english1', 'politics')
                         or (p / 'ds').exists()):
        verify_exam(p)
    elif p.suffix == '.md':
        check_common(p, 500)
    else:
        verify_exam(p)

def main():
    argv = [a for a in sys.argv[1:] if a != '--json']
    as_json = '--json' in sys.argv[1:]
    args = argv or ['kaoyan/quick', 'kaoyan/note']
    for a in args:
        dispatch(a)
    if as_json:
        import json
        print(json.dumps({'pass': not FAIL, 'fail': FAIL, 'info': INFO},
                         ensure_ascii=False, indent=1))
        return 1 if FAIL else 0
    print('=' * 56)
    for i in INFO:
        print('  ·', i)
    print('=' * 56)
    if FAIL:
        for f in FAIL:
            print('  ✗', f)
        print(f'\nFAIL：{len(FAIL)} 项')
        return 1
    print('PASS：全部通过')
    return 0

if __name__ == '__main__':
    sys.exit(main())