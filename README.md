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
│   ├── syllabus/       L1 考纲 + KP 主键（唯一坐标系）
│   ├── quick/          L2 一小时速通（一个子科一份，共 9 份）
│   ├── exam/           L3 考试线正文（一个 KP = 一个文件）
│   ├── projects/       考纲相关项目（5 个，各含 OUTLINE/QUICK/NOTES）
│   ├── reviews/        复习状态表
│   └── tools/          lint.py 结构校验 / review.py 到期计算
└── projects/      ← 工程笔记（与考纲无关，5 个，各含 OUTLINE/QUICK/NOTES）
                     cs149  cs231n  cs336  cmu11785  pku-cg
```

## 三套技术栈，互不干扰

| 目录 | 格式 | 入口 | 校验 |
|---|---|---|---|
| `math/` | LaTeX | `latexmk -pdfxe -interaction=nonstopmode main.tex`（**必须 `-pdfxe`**，用 `-pdf` 会卡在交互输入） | 看编译是否报错 |
| `kaoyan/` | Markdown + KaTeX | 读 `kaoyan/PROGRESS.md` → `syllabus/` → `exam/` | `python3 kaoyan/tools/lint.py` |
| `projects/` | Markdown + KaTeX | 直接读 | 无自动校验 |

**不要混用格式**：`math/` 里不写 Markdown，`kaoyan/` 与 `projects/` 里不写 LaTeX。

## 三条边界

1. **本仓是单一 git 仓**：`math/` `kaoyan/` `projects/` 共用同一个 `.git`，remote 沿用原 `11408-notebook`
   （`origin` = GitHub `zhenyang268/11408-notebook`，**该仓未创建**；`gitee` = `we_we_we/11408-notebook`）。
   （2026-11-01 之前 `kaoyan/` 曾是内嵌独立仓，已合并；**不要再找 `kaoyan/.git`**。）
2. **`projects/` 与 `kaoyan/projects/` 的分界**：能对上考纲 KP 的进 `kaoyan/projects/`（受 `lint.py` 的「对位考点」检查约束）；对不上的进本层 `projects/`。
   **两侧都是三件套结构**：`OUTLINE.md`（大纲，决定做不做）/ `QUICK.md`（一小时上手）/ `NOTES.md`（详细记录）。
3. **`math/bridges/` 是"跨篇串讲"**，不是新知识点。它的内容是篇与篇之间的连接，读法是"回头贯通"，不是"逐篇学"。

## 各自规约

- `kaoyan/` 的归档规约、KP 命名、双线隔离铁律 → `kaoyan/AGENTS.md`（**真源，本文不复述**）
- `math/` 的公式编号前缀、注释三段式 → 父仓 `AGENTS.md` §六
- `projects/` 暂无规约，新增时参考 `kaoyan/projects/` 的文件骨架，去掉「对位考点」一节