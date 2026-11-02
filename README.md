# notebook — 笔记总仓

三类笔记的**唯一物理位置**。一个目录 = 一个迁移单元：将来若体积过大，整体 `mv notebook/ ~/` 即可，各子目录自带工具链，无需拆分。

## 30 秒结构

```text
notebook/
├── math/          ← LaTeX 数学笔记（自学数学基础，非应试）
│   ├── main.tex        xelatex 单一主文档，\input 聚合 A_…R_ 各篇
│   ├── diffrential/    专题一：微分方程
│   ├── li/             专题二：李群
│   └── bridges/        专题三：跨篇串讲（含 README 索引与 graphics 对照表）
├── kaoyan/        ← 11408 考研体系（Markdown）
│   ├── syllabus/       L0 考纲（考点 + 档位 + 真题落点 + 一课位置，唯一坐标系）
│   ├── quick/          L1 一口气讲完一科（9 份三合一：考纲表 + 概括版 + 口语版）
│   ├── note/           L2 考点×真题复合版（184 个考点，一考点一文件，只写思路不写答案）
│   ├── exam/           L3 分章详解（59 篇：408/25 + 数一/22 + 英政/12）+ 真题/（2021–2024）
│   ├── words/          L4 单词书（30 主题组 + 大纲补全，覆盖大纲 5530 词）
│   ├── reviews/        复习状态表
│   └── tools/          lint.py 结构校验 / review.py 到期计算
├── projects/      ← 工程线（**服务面试**，22 个，OUTLINE + NOTES 两件套 + 可选双语）
│   系统与网络 5：jos csapp cs144 nand2tetris 6824
│   体系与编译器 3：cpu-microarchitecture asm-link-arch compiler（+ MINI-COMPILER.md）
│   语言与 API 3：linux-api cpp-basics python-basics
│   算法与计算 2：algorithm cs149
│   AI 与图形 2：ai pku-cg
│   能力方法论 7：perf-engineering testing database debug-toolchain
│                system-design latent-issues algorithm-interview
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
2. **工程线全部在 `projects/`**（2026-11-02 起 `kaoyan/projects/` 已并入）：22 个项目（15 课程/基础 + 7 能力方法论），每个两件套 `OUTLINE.md`（在做什么 / 为什么这样做 / 章节大纲 / 不做什么 / **面试怎么讲**）+ `NOTES.md`（分章详细）。
   `QUICK.md` 与 `DESIGN.md` 已废除，**不要再生**。
3. **`math/bridges/` 是"跨篇串讲"**，不是新知识点。它的内容是篇与篇之间的连接，读法是"回头贯通"，不是"逐篇学"。

## 各自规约

- `kaoyan/` 的归档规约、KP 命名、双线隔离铁律 → `kaoyan/AGENTS.md`（**真源，本文不复述**）
- `math/` 的公式编号前缀、注释三段式 → 父仓 `AGENTS.md` §六
- `projects/` 的规约（两件套、五段 OUTLINE、面试章节）→ `projects/README.md`