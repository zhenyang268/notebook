# AGENTS.md — notebook 仓入口

> **读者**：agent。**本仓是三类笔记的源**：数学（LaTeX）、考研（Markdown）、工程线（Markdown）。
> **本仓不做**：不跑 ctest、不建站点、不写进度。这里的 `.tex` / `.md` 就是源文件本身。

## 一、先看哪份

| 你要做什么 | 读哪份 |
|---|---|
| 改 `math/*.tex`（正文 / 证明 / 公式） | `math/STRUCTURE.md`（总账 + 编译命令 + 写作规约在哪） |
| 改 `math/survey/` | `math/survey/CONTRACT.md`（条目格式、状态词白名单、更新触发） |
| 改 `math/bridges/` | `math/bridges/README.md`（骨架 S1–S6、覆盖矩阵） |
| 学数学的深度与流程 | `LEARNING.md` |
| 考研体系 L0–L4 | `kaoyan/` 各级目录 |
| 工程线（服务面试） | `projects/` |

## 二、硬规则

1. **LaTeX 必须 `latexmk -pdfxe -interaction=nonstopmode main.tex`**。
   用 `-pdf`（pdfLaTeX）时 ctex 会报 `fontset 'mac' unavailable` 并卡在交互输入等键盘，命令永不返回。
2. **父仓 `graphics` 的代码规约不适用于 `.tex`**。
   `AGENTS.md` 的「注释三段式 + 公式编号前缀」是 `src/**/*.hpp` 头文件专属，对 `math/` 没有适用对象。
   `math/` 根正文**全部公式不编号**（0 个 `\tag` / `equation` / `label{eq}`），每篇一个 `\section` 大主题。
3. **产物只提交 PDF**：`*.aux` / `*.log` / `*.xdv` / `*.fls` 等已在 `.gitignore`；
   `bridges.pdf` / `survey.pdf` 是入库产物（方便不编译直接看）。

## 三、不要做

- 不写「进度」「下一步」「当前位置」——那类状态不在本仓。
- 不把 `.tex` 转成 Markdown 再改（会丢公式结构）。
- 不为了「看起来整齐」给公式加编号、给章节重排 `\subsubsection` —— 改写顺序会连带影响下游按段切片。
