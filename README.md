# notebook — 笔记总仓

三类笔记的**唯一物理位置**。一个目录 = 一个迁移单元：将来若体积过大，整体 `mv notebook/ ~/` 即可，各子目录自带工具链，无需拆分。

## 30 秒结构

```text
notebook/
├── math/          ← LaTeX 数学笔记（自学数学基础，非应试）
│   ├── main.tex        xelatex 单一主文档，\input 聚合 A_…R_ 各篇
│   ├── diffrential/    专题一：微分方程
│   ├── li/             专题二：李群
│   ├── survey/         专题四（独立册）：主仓数值库的数学镜像，97 条 + verify.py
│   └── bridges/        专题三：跨篇串讲（按 S1–S6 结构动作分篇，含 NOW.md 覆盖矩阵）
├── kaoyan/        ← 11408 考研体系（Markdown）
│   ├── syllabus/       L0 考纲（考点 + 档位 + 真题落点 + 一课位置，唯一坐标系）
│   ├── quick/          L1 一口气讲完一科（9 份三合一：考纲表 + 概括版 + 口语版）
│   ├── note/           L2 考点×真题复合版（184 个考点，一考点一文件，只写思路不写答案）
│   ├── exam/           L3 分章详解（59 篇：408/25 + 数一/22 + 英政/12）+ 真题/（2021–2024）
│   ├── words/          L4 单词书（30 主题组 + 大纲补全，覆盖大纲 5530 词）
│   ├── reviews/        复习状态表
│   └── tools/          lint.py 结构校验 / review.py 到期计算
├── projects/      ← 工程线（**服务面试**，6 个分组 + 6 个单列，36 个两件套单元）
│   os/ 分组 1+5：分组总纲 + 路径手册 ｜ linux-api（用户态） jos（内核态）
│                  kernel-compare（三家对比） drivers（JOS 磁盘与 e1000）
│                  security（原语 / ROP / 外挂与反作弊）
│   cpu/ 分组 1+4：分组总纲 + 路径手册（60 分 / 80 分）｜ asm-link-arch（读得懂）
│                  cpu-microarchitecture（说得清） riscv-core（做得出） compiler（编得动）
│   langs/ 分组 1+3：cpp-basics python-basics cuda
│   algo/ 分组 1+2：algorithm（实现体检） algorithm-interview（题型题库）
│   eng/ 分组 1+5：testing debug-toolchain perf-engineering system-design latent-issues
│   cg/ 分组 1+5：rasterizer（画出来） raytrace（再画一遍） geometry-anim（顶点从哪来）
│                 engine（一帧怎么组织） game（手感与联机）
│   单列 6（不硬放）：csapp 6824 cs149 database ai discrete-math
└── HANDOFF/       ← 交接包：规范、任务 prompt、派发器、验收脚本
```

## 三套技术栈，互不干扰

| 目录 | 格式 | 入口 | 校验 |
|---|---|---|---|
| `math/` | LaTeX | `latexmk -pdfxe -interaction=nonstopmode main.tex`（**必须 `-pdfxe`**，用 `-pdf` 会卡在交互输入） | 看编译是否报错 |
| `kaoyan/` | Markdown + KaTeX | 读 `kaoyan/PROGRESS.md` → `syllabus/` → `quick/` → `note/` → `exam/` | `python3 kaoyan/tools/lint.py` + `python3 HANDOFF/tools/verify.py` |
| `projects/` | Markdown + KaTeX | `projects/README.md` → 选项目 → `OUTLINE.md` | `python3 kaoyan/tools/lint.py`（两件套齐） |

**不要混用格式**：`math/` 里不写 Markdown，`kaoyan/` 与 `projects/` 里不写 LaTeX。

## 三条边界

1. **本仓是单一 git 仓**：`math/` `kaoyan/` `projects/` 共用同一个 `.git`，remote 沿用原 `11408-notebook`
   （`origin` = GitHub `zhenyang268/11408-notebook`，**该仓未创建**；`gitee` = `we_we_we/11408-notebook`）。
   （2026-11-01 之前 `kaoyan/` 曾是内嵌独立仓，已合并；**不要再找 `kaoyan/.git`**。）
2. **工程线全部在 `projects/`**（2026-11-02 起 `kaoyan/projects/` 已并入）：**6 个分组（`os` `cpu` `langs` `algo` `eng` `cg`）+ 6 个单列 = 36 个两件套单元**，每个两件套 `OUTLINE.md`（在做什么 / 为什么这样做 / 章节大纲 / 不做什么 / **面试怎么讲**）+ `NOTES.md`（分章详细）。分组目录自身也有两件套（总纲 + 路径手册），**只做路由与路径，不复制子项目正文**；没关系的不硬放，宁可留在单列。
   `QUICK.md` 与 `DESIGN.md` 已废除，**不要再生**。
3. **`math/` 下两个配套目录职责固定**（2026-11-03 定，真源是各自目录里的规约文件）：
   - `survey/` = 主仓 `learning/graphics` 数学面的**镜像清单**，不是教程。库里有的才写，标状态与判据；
   - `bridges/` = **结构串讲的对照表**，不是知识库。只收「A ≅ B」，按 S1–S6 六个结构动作分篇，覆盖 `NOW.md` 短期规划。

## 各自规约

- `kaoyan/` 的归档规约、KP 命名、双线隔离铁律 → `kaoyan/AGENTS.md`（**真源，本文不复述**）
- `math/` 的公式编号前缀、注释三段式 → 父仓 `AGENTS.md` §六
- `math/survey/` 的条目格式、状态词白名单、更新触发 T1–T5 → `math/survey/CONTRACT.md`（验收 `python3 math/survey/verify.py`）
- `math/bridges/` 的骨架 S1–S6、≅ 规则、覆盖矩阵与占位规则 → `math/bridges/README.md`
- `projects/` 的规约（两件套、五段 OUTLINE、面试章节）→ `projects/README.md`