# STRUCTURE.md — math/ 结构台账

> **本页只记结构，不记进度。** 进度的唯一真源是父仓 `../NOW.md`（滚动文件）；
> 各子册自己的规约在 `survey/CONTRACT.md` 与 `bridges/README.md`，本页不复述规则，只核对现状。
> 改完 `.tex` 后请重新跑 §4 的两条命令，并把本页数字更新（页数、篇数、行数）。

---

## 1 总账

| 范围 | 篇数 | 行数 | 依据 |
|---|---|---|---|
| 根正文 A–R | 17 篇（`partN` 占 N，O 空缺） | 3491 | `main.tex:32-49` 的 `\input` |
| 专题一 `diffrential/` | 4 篇（de1–de4） | 1262 | `main.tex:53-56` |
| 专题二 `li/` | 3 篇（lie1–lie3） | 893 | `main.tex:60-62` |
| 专题三 `bridges/` | 5 篇（br0–br4） | 1326+ | `bridges/main.tex:56-62`，独立册 |
| 数值库 `survey/` | 11 篇（p1–p11） | 2193 | `survey/main.tex:70-80`，独立册 |
| **合计** | **40 篇内容 + 4 个 `main.tex` = 44 个 `.tex`** | 9241+ | |

编译产物：根册 **116 页**（`main.log` 的 `Output written on main.xdv (116 pages…)`）、
`bridges/` 31 页、`survey/` 独立成册。三册各自独立编译。

---

## 2 四个专题的入口与产物（三种状态，别混）

| 子册 | 独立 `main.tex` | 独立 PDF | 状态 |
|---|---|---|---|
| `diffrential/` | 有（`main.tex`，纯 preamble + 4 行 `\input`） | 无 | **有入口无产物** |
| `li/` | **无** | 无 | **无入口**：三篇只能经根 `main.tex` 参与编译，无法单独打印/分发 |
| `bridges/` | 有 | 有 | 完整 |
| `survey/` | 有 | 有 | 完整（注意同目录历史遗留一份中文名 PDF，已加 `.gitignore`） |

`li/` 缺入口是**已知缺口**，不影响根册编译（根 `main.tex:60-62` 已 `\input` 三篇）。

---

## 3 五个已知结构性缺口（不是 bug，是取舍的欠账）

| # | 缺口 | 事实 | 影响 |
|---|---|---|---|
| 1 | `li/` 无独立入口 | 见 §2 | 专题二不能单独成册 |
| 2 | `partN.tex` 与主篇重叠 | 262 行的无推导公式速查卡，Parseval ≡ `A_analysis`、Stokes ≡ `E_Field`、SU(2) ≡ `lie1` | 定位是**速查卡**不是讲解；根册唯一一处 Overfull（vbox 152pt，第 51 页）落在它的页区间 |
| 3 | `br1` / `br4` 无工程落点 | 已补「本篇 ≅」清单与**数学落点**（`br1`→`G4–G6`、`br4`→`P1–P10`）；`bridges/README.md` §1 要求的是工程主键（`IF/W/E/S`），这两篇只能给数学落点 | 按规约字面它们属例外，已在正文注明落点类型 |
| 4 | `E_Field.tex` 是速查卡 | 66 行全是表格与公式，几乎无散文 | 形式上像"篇"，实际是索引 |
| 5 | `bridges/` 篇序 ≠ 骨架序 | `main.tex` 顺序 br0→br1(S4)→br2(S3)→br3(跨)→br4(S5) | `README.md` §7.6 说"篇目顺序 = 骨架顺序"，与实际不符；S1/S2 没有独立篇（正文寄在 br3 §BR3.3 / br1 §BR1.5） |

**唯一被明确登记为"下一步结构缺口"的**是 `bridges/br0_skeleton.tex:203` 自述的那一条：
S5、S6 有骨架级正文，但**还没有一篇把它们与 BR1–BR4 横向缝起来的完整串讲**。

---

## 4 编译与验收（照抄，别改参数）

```bash
cd math
latexmk -pdfxe -interaction=nonstopmode main.tex     # 必须 -pdfxe；用 -pdf 会卡在交互输入
cd bridges && latexmk -pdfxe -interaction=nonstopmode main.tex
cd ../survey && latexmk -pdfxe -interaction=nonstopmode main.tex
cd .. && python3 survey/verify.py                    # 必须 CRIT=0
```

**体检口径**（`main.log` 里该看的四行）：

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