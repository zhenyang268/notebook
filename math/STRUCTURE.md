# STRUCTURE.md — math/ 结构台账

> **本页只记结构，不记进度。** 进度的唯一真源是父仓 `../NOW.md`（滚动文件）；
> 各子册自己的规约在 `survey/CONTRACT.md` 与 `bridges/README.md`，本页不复述规则，只核对现状。
> 改完 `.tex` 后请重新跑 §4 的两条命令，并把本页数字更新（页数、篇数、行数）。

---

## 1 总账（2026-11-04 合并后）

**结构**：一册到底。`main.tex` 连续 `\input` 24 个文件，**没有 `\part` 分层、没有子目录**。
原本单列的「专题一：微分方程」「专题二：李群」已并入主册（`ode1–4`、`lie1–3`），
理由是它们属于本册主线而不是"回头贯通"的旁支；独立成 `\part` 只让目录多一层、让交叉引用断在册边界上。

| 范围 | 文件数 | 行数 | 章节 |
|---|---|---|---|
| A–R 主体（`A_analysis` … `R_complex`，缺 O 是因为 O 与 N 同在 `partN.tex`） | 16 | 3216 | 16 个 `\section` |
| `partN.tex` | 1 | 271 | 2 个：`N. 核心公式速查表`、`O. 推荐学习路径` |
| `ode1–ode4`（微分方程 9 层 + 总结） | 4 | 1221 | `ODE-1`…`ODE-10` |
| `lie1–lie3`（李群 / 李代数 / 拓扑 / 三个应用 / 总结） | 3 | 890 | `Lie-1`…`Lie-8` |
| **合计** | **24 个 .tex** | **5598** | **36 个 `\section`** |

编译产物：**111 页**（`main.log` 的 `Output written on main.xdv (111 pages…)`），0 error、0 missing character、0 undefined reference、Overfull 仅 1 处（`partN` 的 vbox）。
目录深度设为 `tocdepth=2`（只列到 subsection）：三级小节有 166 个，全展开会把目录撑到 10 页、正文推到第 13 页；
设为 2 后目录 5 页、正文从第 8 页开始。要完整三级目录就把 `main.tex:29` 改成 3。

**编号规则**：A–R 是原有字母序列（`partN` 一份文件承载 N 与 O 两节，历史命名，不改）；
新增部分用语义前缀按出现顺序连续编号——`ODE-1…ODE-10`、`Lie-1…Lie-8`。
层号与文件名不一一对应：`ode1` 收第 1–3 层、`ode2` 收第 4–6 层、`ode3` 收第 7 层、`ode4` 收第 8–9 层 + 总结。

---

## 2 两个独立册（只剩这两个）

| 子册 | 独立 `main.tex` | 独立 PDF | 为什么仍单列 |
|---|---|---|---|
| `bridges/`（br0–br4 + 附录 A） | 有 | 有（37 页） | 性质是「A ≅ B」的**对照索引**，不是正文；会随学习进度增量追加 |
| `survey/`（p1–p11） | 有 | 有（39 页；同目录另有一份中文名发布副本） | 主仓 `learning/graphics` 数学面的**镜像清单**，97 条，跟代码仓走 |

两者都有入口、都有产物，状态完整。正文（A–R + ODE + Lie）全部在主册，不再有"有入口无产物"或"无入口"的情况。

**产物策略（2026-11-04 定）**：`*.pdf` **进库**——它是产出，不是中间态；`aux/xdv/fls/log/toc/out/fdb_latexmk` 不进库。
所以**改了 `.tex` 就要重编译并提交 PDF**，否则库里的产物与源不一致。
`survey/` 有两份产物：`survey.pdf`（规范名）与 `数值库数学串讲.pdf`（发布副本），**重编后必须同步**，见 §4。

**PDF 命名（2026-11-04 改）**：三册不再都叫 `main.pdf` —— `math/math.pdf`、`math/bridges/bridges.pdf`、`math/survey/survey.pdf`。
名字由各目录的 `.latexmkrc` 里 `$jobname` 固定，**入口仍是 `main.tex`**，所以 §4 的命令行一个字都不用改。
新建册子时记得加同款 `.latexmkrc`，否则又会掉回 `main.pdf`。

---

## 3 已知结构性缺口（不是 bug，是取舍的欠账）

| # | 缺口 | 事实 | 影响 |
|---|---|---|---|
| 1 | `partN.tex` 与主篇重叠 | 271 行的无推导速查卡，Parseval ≡ `A_analysis`、Stokes ≡ `E_Field`、SU(2) ≡ `lie1` | 定位已明确为**索引**（节首加了指路说明）；根册唯一一处 Overfull（vbox 152pt，第 51 页）也在它的页区间 |
| 2 | `E_Field.tex` 是速查卡 | 65 行全是表格与公式，几乎无散文 | 形式上是"篇"，实际是索引，与 `partN` 功能重叠 |
| 3 | `br1` / `br4` 只能给数学落点 | 已补「本篇 ≅」清单与落点（`br1`→`G4–G6`、`br4`→`P1–P10`）；但 `bridges/README.md` §1 要求的是工程主键（`IF/W/E/S`） | 按规约字面属例外，已在正文注明落点类型 |
| 4 | `bridges/` 篇序 ≠ 骨架序 | `main.tex` 顺序 br0→br1(S4)→br2(S3)→br3(跨)→br4(S5) | `README.md` §7.6 已改为「归位顺序」；S1/S2 没有独立篇（正文寄在 br3 §BR3.3 与 br1 §BR1.5） |
| 5 | 跨篇互链只是文字指引 | 合并后 ODE/Lie 与 A–R 都在同一册，理论上可以 `\ref` 互链；实际只有「详见 ODE-4」这类文字指引 | 全册 0 个 `\label`/`\ref`，改编号不会断引用，但也做不到点击跳转 |

**唯一被明确登记为"下一步结构缺口"的**是 `bridges/br0_skeleton.tex:203` 自述的那一条：
S5、S6 有骨架级正文，但**还没有一篇把它们与 BR1–BR4 横向缝起来的完整串讲**。

---

## 4 编译与验收（照抄，别改参数）

```bash
cd math
latexmk -pdfxe -interaction=nonstopmode main.tex     # 必须 -pdfxe；用 -pdf 会卡在交互输入
cd bridges && latexmk -pdfxe -interaction=nonstopmode main.tex
cd ../survey && latexmk -pdfxe -interaction=nonstopmode main.tex
cp survey.pdf 数值库数学串讲.pdf                       # ← 发布副本必须同步，否则两份产物不一致
cd .. && python3 survey/verify.py                    # 必须 CRIT=0
```

输出名由各目录 `.latexmkrc` 的 `$jobname` 决定：主册 `math.pdf`、`bridges/bridges.pdf`、`survey/survey.pdf`。
所以上面三条命令**不用加 `-jobname`**，也不要在命令行覆盖它 —— 覆盖会让库里的产物变成 `main.pdf`，与命名约定不一致。

**体检口径**（日志随 `$jobname` 走：`math.log` / `bridges.log` / `survey.log`，**不再是 `main.log`** 里该看的四行）：

| 项 | 期望 | 怎么看 |
|---|---|---|
| Error | 0 | `grep -c "^! " main.log` |
| Missing character（中文缺字） | 0 | `grep -c "Missing character" main.log` |
| undefined reference | 0 | 尾部 `There were undefined references` 不应出现 |
| Overfull hbox | 0 | 已知唯一一处是 `partN` 的 vbox，属排版取舍 |

**两类无害告警，不要"修"**：`fancyhdr` 的 `\headheight too small`（每页一次，改 `geometry` 的版式值即可消，但不影响内容）、
`hyperref` 的 `Token not allowed in a PDF string`（带 `$…$` 的 `\section` 标题所致，属 PDF 书签降级）。
**`.log` 被 `.gitignore` 排除**，所以基于 `rg` 的检查看不到它——要核编译告警必须直接读文件。

---

## 5 写作规约在哪

| 对象 | 规约出处 |
|---|---|
| `survey/` 条目格式、状态词白名单（五值）、更新触发 T1–T5 | `survey/CONTRACT.md` |
| `bridges/` 骨架 S1–S6、≅ 规则、覆盖矩阵、占位三行 | `bridges/README.md` |
| 根正文 A–R | 无成文规约：全部公式**不编号**（0 个 `\tag`/`equation`/`label{eq}`），每篇一个 `\section` 大主题 |

> 父仓 `AGENTS.md` §六 的「公式编号前缀 + 注释三段式」是 `graphics/src/**/*.hpp` **头文件专属**，
> 对 `math/` 没有适用对象——不要按它来改 `.tex`。