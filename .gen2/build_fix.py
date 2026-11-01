# -*- coding: utf-8 -*-
"""把失败的两块（LA 全量、PS 前半）拆成更小的块重跑。"""
import re
from pathlib import Path

GEN = Path(__file__).parent
SYL = GEN.parent / 'kaoyan' / 'syllabus'

SYS = (GEN / 'sys2.txt').read_text(encoding='utf-8')

def parse(path, prefix):
    out, cur = [], None
    for line in Path(path).read_text(encoding='utf-8').split('\n'):
        m = re.match(r'^###\s+(.+)$', line)
        if m:
            cur = (m.group(1), [])
            if m.group(1).startswith(prefix):
                out.append(cur)
            continue
        m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|', line)
        if m and cur and cur[0].startswith(prefix) and re.match(r'^M1-', m.group(1)):
            cur[1].append((m.group(1), m.group(2)))
    return [c for c in out if c[1]]

def flat(chs):
    """展开成 (章标题, kp, 节名) 的线性序列"""
    return [(ch, kp, nm) for ch, kps in chs for kp, nm in kps]

BODY = (GEN / 'prompts' / 'd1.md').read_text(encoding='utf-8')
HEAD = BODY.split('考点清单如下')[0] + '考点清单如下（**只写这些**）：\n\n'

def make(tid, subject, items):
    lines = [HEAD]
    last = None
    for ch, kp, nm in items:
        if ch != last:
            lines.append(f'## {ch}\n')
            last = ch
        lines.append(f'- {kp} | {nm}')
    lines.append(f'\n科目：{subject}。\n')
    (GEN / 'prompts' / f'{tid}.md').write_text('\n'.join(lines), encoding='utf-8')
    (GEN / 'state' / f'{tid}.status').write_text('pending', encoding='utf-8')
    return f'{tid}\tdeepseek-v4.1-flash-1017'

la = flat(parse(SYL / 'math1.md', 'LA-'))
ps = flat(parse(SYL / 'math1.md', 'PS-'))
print(f'LA 共 {len(la)} 条，PS 共 {len(ps)} 条')

rows = []
# LA 拆两半
cut = (len(la) + 1) // 2
rows.append(make('l1a', '数学一 线性代数', la[:cut]))
rows.append(make('l1b', '数学一 线性代数', la[cut:]))
# PS 前半（原 q1 覆盖的那 15 条）拆两半；q2 已成功，不动
ps_head = ps[:15]
c2 = (len(ps_head) + 1) // 2
rows.append(make('q1a', '数学一 概率统计', ps_head[:c2]))
rows.append(make('q1b', '数学一 概率统计', ps_head[c2:]))

(GEN / 'tasks_fix.tsv').write_text('\n'.join(rows) + '\n', encoding='utf-8')
print('\n'.join(rows))