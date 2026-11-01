# 执行顺序与分工

> 任务总量：约 190 个生成块（旧估 60 是漏算，2026-11-02 按实测重算）。
> `MAXPAR=3` 实测吞吐约 1 块/分钟 → 纯生成 5–6 小时，含拼装与返工墙钟 10–14 小时。
> **并行不等于提速**：单账号总额度是 3，只让一个 pump 跑，其余 agent 只做验收。

## 阶段 1 · 地基（必须先做，串行）

| 顺序 | 任务 | prompt | 为什么必须先做 |
|---|---|---|---|
| 1 | 结构迁移 | `prompts/00-migrate.md` | 不先删旧文件，后面全在错的基础上叠 |
| 2 | K0 考纲强化 | `prompts/K0-syllabus.md` | quick 第一段和 exam 第一段都要抄它 |

**验收**：`lint.py` 能跑通（会报缺文件，属预期）；`syllabus` 每个考点都有档位。

## 阶段 2 · 主体（可 3 个 agent 并行）

| Agent | 负责 | 文件 |
|---|---|---|
| A | K1–K4（408 四科） | `prompts/K-quick.md` |
| B | K5–K7（数学三科） | 同上 |
| C | K8–K9（英语、政治） | 同上 |

**为什么先做 quick 再做 exam**：quick 会逼着你把"这一科的主线"想清楚；
先写 exam 容易写成资料汇编，没有主线。

**验收**：九份 quick 都在、三段齐、≥6000 字符。

## 阶段 3 · 详细与配题（可 3 个 agent 并行，按科拆）

| Agent | 负责 | 依赖 |
|---|---|---|
| A | E1 + N1（408 四科） | K0、K1–K4 |
| B | E2 + N2（数一三科） | K0、K5–K7 |
| C | E3 + N3（英政）+ W1（单词书） | K0、K8–K9 |

**注意**：`N*` 必须在对应的 `E*` 之后——配题要按讲解的章节走。

单词书独立，不依赖任何前置，可以和任何任务并行，但**失败率高**，建议单独一个 agent 盯着。

## 阶段 4 · 项目与双语（可 3 个 agent 并行）

| Agent | 负责 |
|---|---|
| A | P1（5 个考纲相关项目） |
| B | P2（5 个工程侧项目） |
| C | B1（双语化，**依赖 A/B 完成**） |

**验收**：10 个项目都有 `OUTLINE.md` 四段齐、无 `QUICK.md`；10 个 `OUTLINE.bi.md` 成对。

## 3 个 agent 的调度规则

1. **各自独立任务表**：`tasks-A.tsv` / `tasks-B.tsv` / `tasks-C.tsv`，不要共用一个 `state/` 目录。
2. **每家 `MAXPAR=3`**，但**三家合计不要超过 3**——`bl` 端是同一个账号，超了撞 429。
   实际做法：**同一时刻只让 1 个 agent 在跑**，其余做规划与验收。或者轮流跑。
3. **别让两个 agent 写同一批文件**。文件归属按上表硬切。

## 最容易返工的三处（提前避开）

1. **quick 写成教材**。打开文件读第一段，如果像"XX 是指……"，重写。
2. **配题编造真题**。一旦出现"XX 年第 N 题"却没有实证，整层作废。
3. **单词书总量不够**。做到 2000 就收手是最常见的失败，必须做到 5500。

## 交付后的最终检查

```bash
cd notebook
# 结构
python3 kaoyan/tools/lint.py

# 覆盖面
cd kaoyan && python3 - <<'PY'
import re
from pathlib import Path
for f, pre in [('408.md','408-'), ('math1.md','M1-')]:
    syl = Path(f'syllabus/{f}').read_text(encoding='utf-8')
    want = list(dict.fromkeys(re.findall(r'`(' + pre + r'[A-Z]{2,3}-\d{4})`', syl)))
    txt = ''.join(p.read_text(encoding='utf-8') for p in Path('quick').glob('*.md'))
    got = set(re.findall(r'(' + pre + r'[A-Z]{2,3}-\d{4})', txt))
    print(f'{f}: {len(want)} 个考点，quick 覆盖 {len(got)}，缺 {len([k for k in want if k not in got])}')
PY

# 篇幅
wc -m quick/*.md words/*.md | tail -5
```