# -*- coding: utf-8 -*-
"""为「按大纲详解」生成任务：从 syllabus 解析章—节结构，按块切分。"""
import re
from pathlib import Path

GEN = Path(__file__).parent
SYL = GEN.parent / 'kaoyan' / 'syllabus'

for d in ('prompts', 'out', 'state'):
    (GEN / d).mkdir(exist_ok=True)

SYS = (
    '你是考研辅导教材的作者，写作目标是一本**可以替代教材的详解本**。\n'
    '只输出 Markdown 正文本身。禁止任何前言（好的、以下是、下面我）、禁止把全文包在代码块里、禁止结尾客套。\n'
    '标题层级：章用 ##，节用 ###，绝不用一级标题。\n'
    '公式必须用 KaTeX：行内 $...$，独立行 $$...$$。禁止反斜杠圆括号或反斜杠方括号。\n'
    '中文标点。不要 emoji。不要写本节将学习这类空话。\n'
    '准确性优先：定义、公式、复杂度、性质必须正确；不确定就不写，绝不编造考纲之外的内容。\n'
)
(GEN / 'sys2.txt').write_text(SYS, encoding='utf-8')


def parse(path):
    """返回 [(章标题, [(kp, 节名)], ...]"""
    out = []
    cur = None
    for line in Path(path).read_text(encoding='utf-8').split('\n'):
        m = re.match(r'^###\s+(.+)$', line)
        if m:
            cur = (m.group(1), [])
            out.append(cur)
            continue
        m = re.match(r'^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|', line)
        if m and cur is not None and re.match(r'^(408|M1)-', m.group(1)):
            cur[1].append((m.group(1), m.group(2)))
    return [c for c in out if c[1]]


def chunk(chapters, size):
    """按 KP 数量把章切成块；一个章不拆，超了就单独成块。"""
    blocks, cur, n = [], [], 0
    for ch in chapters:
        k = len(ch[1])
        if cur and n + k > size:
            blocks.append(cur); cur, n = [], 0
        cur.append(ch); n += k
    if cur:
        blocks.append(cur)
    return blocks


BODY = (
    '任务：为下面这些考点写**按大纲详解**的正文。\n\n'
    '写作要求：\n'
    '1. 严格按给定顺序与编号，**不得增删或改写考点**。章用 `## {编号} {章名}` 作标题，'
    '节用 `### {编号}.{序号} {节名}` 作标题。\n'
    '2. 每个考点 180–260 字，必须讲清三样：'
    '(a) 定义或核心结论是什么；(b) 关键公式/机制，必要时给一句推导思路；'
    '(c) 一个典型计算或一个易错点。\n'
    '3. 连续成文，不要写成词条罗列；但也不要写成随笔，每一句都要有信息量。\n'
    '4. 公式用 $...$；只有在确有必要时才用表格（例：几种排序的复杂度对比）。\n'
    '5. 不写复习建议、不写考试分值、不写排期。\n\n'
    '考点清单如下（**只写这些**）：\n\n'
)

TASKS = []

def add(tid, model, subject, chapters):
    lines = [BODY]
    for ci, (title, kps) in enumerate(chapters, 1):
        lines.append(f'## {title}\n')
        for si, (kp, name) in enumerate(kps, 1):
            lines.append(f'- {kp} | {name}')
        lines.append('')
    lines.append(f'\n科目：{subject}。\n')
    TASKS.append((tid, model, '\n'.join(lines)))


DS = parse(SYL / '408.md')
# 408 四科
part = {c[0].split()[0].split('-')[0]: c for c in DS}
seg = lambda pre: [c for c in DS if c[0].startswith(pre)]

ds_ch = seg('DS-')
co_ch = seg('CO-')
os_ch = seg('OS-')
net_ch = seg('NET-')

for i, blk in enumerate(chunk(ds_ch, 17), 1):
    add(f'd{i}', 'deepseek-v4.1-flash-1017', '408 数据结构', blk)
for i, blk in enumerate(chunk(co_ch, 15), 1):
    add(f'c{i}', 'deepseek-v4.1-flash-1017', '408 计算机组成原理', blk)
for i, blk in enumerate(chunk(os_ch, 11), 1):
    add(f'o{i}', 'deepseek-v4.1-flash-1017', '408 操作系统', blk)
for i, blk in enumerate(chunk(net_ch, 17), 1):
    add(f'n{i}', 'deepseek-v4.1-flash-1017', '408 计算机网络', blk)

M1 = parse(SYL / 'math1.md')
hs_ch = [c for c in M1 if c[0].startswith('HS-')]
la_ch = [c for c in M1 if c[0].startswith('LA-')]
ps_ch = [c for c in M1 if c[0].startswith('PS-')]

for i, blk in enumerate(chunk(hs_ch, 15), 1):
    add(f'h{i}', 'deepseek-v4.1-flash-1017', '数学一 高等数学', blk)
for i, blk in enumerate(chunk(la_ch, 18), 1):
    add(f'l{i}', 'deepseek-v4.1-flash-1017', '数学一 线性代数', blk)
for i, blk in enumerate(chunk(ps_ch, 15), 1):
    add(f'q{i}', 'deepseek-v4.1-flash-1017', '数学一 概率统计', blk)

# 英一 / 政治：按模块（无 KP 到节），单独写
ENG = (
    BODY.replace('考点清单如下（**只写这些**）：', '模块清单如下（**只写这些**）：')
    + '## E1 英语一\n- 分值地图与时间分配\n- 阅读理解：六种题型与五种错误选项\n'
      '- 新题型：七选五、排序、小标题\n- 翻译：拆分与重组\n- 小作文：格式与三类高频\n'
      '- 大作文：三段式与反模板\n- 完形填空\n\n科目：英语一。不编造真题原文。\n'
)
POL = (
    BODY.replace('考点清单如下（**只写这些**）：', '模块清单如下（**只写这些**）：')
    + '## P1 政治\n- 分值地图与题型\n- 马原\n- 新思想\n- 毛中特\n- 史纲\n- 思修与法治\n'
      '- 时政与当代\n- 选择题与材料分析题作答方法\n\n科目：政治。不编造会议与文件表述。\n'
)
TASKS.append(('e1', 'deepseek-v4.1-flash-1017', ENG))
TASKS.append(('pol', 'deepseek-v4.1-flash-1017', POL))

rows = []
for tid, model, prompt in TASKS:
    (GEN / 'prompts' / f'{tid}.md').write_text(prompt, encoding='utf-8')
    (GEN / 'state' / f'{tid}.status').write_text('pending', encoding='utf-8')
    rows.append(f'{tid}\t{model}')
(GEN / 'tasks.tsv').write_text('\n'.join(rows) + '\n', encoding='utf-8')

# 清掉不在当前任务集里的残留状态与产物（避免旧 id 被误派发）
keep = {t[0] for t in TASKS}
for sub in ('state', 'out', 'prompts'):
    for p in (GEN / sub).iterdir():
        if p.is_file() and p.stem not in keep:
            p.unlink()
print(f'tasks: {len(TASKS)}')
print('\n'.join(rows))