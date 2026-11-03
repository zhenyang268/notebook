# riscv-core · From a single-cycle RV32I to an out-of-order core

> **双语对照版**：英文原段 → 紧随其后的中文译文（引用块，前缀 `译：`）；每节末附该节生词表。术语首次出现保留英文原词，方便对照阅读与翻译练习。

> This directory covers **building** a core only: RTL, difftest, timing and area.
> **Reading a core and attributing performance** lives in `cpu-microarchitecture/`; calling conventions, stack frames and relocation live in `asm-link-arch/`.
> All three share one vocabulary (ISA / microarchitecture / CPI / critical path) and reference each other one way only, without duplicating content.
>
> **译** 本目录只讲如何**构建**一个核：RTL、difftest（差分测试）、时序与面积。
> **阅读一个核并把性能归因**的内容在 `cpu-microarchitecture/`；调用约定、栈帧与重定位在 `asm-link-arch/`。
> 三者共用同一套词汇（ISA／微架构（microarchitecture）／CPI／关键路径（critical path）），并且只单向互相引用，不重复内容。

## 1. What It Is Doing

Start from the semantics of a single `add` and actually build an RV32I machine — then prove, in the way the industry does, that it is **correct, fast, and able to close timing**. There are four deliverables along the chain, and missing any one of them means you only have "it runs":

> 译：从一条 `add` 的语义出发，真正造出一台 RV32I 机器——然后用业界采用的方式证明它**正确、快、并能收敛时序（close timing）**。这条链上有四件交付物（deliverable），缺了其中任何一件，你手里就只有「它能跑」：

**Deliverable one: a cycle-accurate model (C++ or Python).** Before writing a line of RTL, it must compute IPC and support parameter sweeps. The reason is cost: changing one parameter (ROB from 32 to 128) takes minutes in the model and days in RTL. **Design-space exploration must precede implementation** — this is the line between "microarchitecture" and "playing with CPUs".

> 译：**交付物一：一个周期精确模型（cycle-accurate model，C++ 或 Python）。** 在写下第一行 RTL 之前，它必须能算出 IPC，并支持参数扫描（parameter sweep）。原因是成本：改一个参数（ROB 从 32 改成 128），在模型里只要几分钟，在 RTL 里却要几天。**设计空间探索（design-space exploration）必须先于实现**——这正是「微架构」与「玩 CPU」之间的分界线。

**Deliverable two: RTL.** Single cycle → five stages → forwarding/stalls → branch prediction → I/D caches → out-of-order (rename + ROB + reservation stations) → out-of-order memory (LSU queue + disambiguation). Each stage is independently verifiable; you do not have to do it all at once.

> 译：**交付物二：RTL。** 单周期 → 五级流水 → 前递（forwarding）/停顿（stalls） → 分支预测 → I/D 缓存 → 乱序（out-of-order）（重命名 + ROB + 保留站） → 乱序访存（LSU 队列 + 消歧（disambiguation））。每一阶段都可独立验证；你不必一次就把全部做完。

**Deliverable three: a difftest harness plus test sets.** Every committed instruction is compared against Spike (the official RISC-V ISA simulator), over enough random programs. This is the judgment core of the project: **"I think it is right" carries no weight here**.

> 译：**交付物三：一套 difftest 测试框架（harness）加若干测试集。** 每条已提交（committed）的指令都要与 Spike（官方的 RISC-V ISA 模拟器）比对，并且要覆盖足够多的随机程序。这是本项目评判的核心：**“我觉得它是对的”在这里不算数。**

**Deliverable four: timing and area reports.** Yosys synthesizes a netlist, OpenSTA runs static timing analysis on sky130, and you report the critical path in nanoseconds, the area, and the maximum frequency you can reach. **This is what sandbox projects cannot give you** — there, delay is a game unit; here it is nanoseconds.

> 译：**交付物四：时序与面积报告。** Yosys 综合出网表（netlist），OpenSTA 在 sky130 上运行静态时序分析（static timing analysis），然后你报告以纳秒计的关键路径（critical path）、面积，以及你能达到的最高频率。**这正是沙盒项目给不了你的东西**——在那种项目里，延迟只是一个游戏单位；而在这里，它是纳秒。

**There are four kinds of input**: the RV32I specification (the base integer chapter, quite thin); open-source cores for comparison (Rocket for in-order, BOOM/SonicBOOM for out-of-order, CVA6); an open-source toolchain (Verilator / Yosys / OpenSTA / sky130 PDK); and reference models plus tests (Spike, riscv-tests, CoreMark).

> 译：**输入有四类**：RV32I 规范（基础整数指令那一章，篇幅相当薄）；用于对比的开源核（顺序执行的 Rocket，乱序执行的 BOOM/SonicBOOM，CVA6）；开源工具链（Verilator / Yosys / OpenSTA / sky130 PDK）；以及参考模型加测试（Spike、riscv-tests、CoreMark）。

**Acceptance is not "it runs a program" but four criteria**: (1) all `rv32ui-p-*` riscv-tests pass; (2) random difftest shows zero divergence from Spike; (3) synthesis passes and STA is clean, with the start and end points of the critical path reported; (4) every microarchitectural change comes with a table of four numbers — IPC, area, fmax, and a verdict on whether the change is worth it.

> 译：**验收标准在于四条准则，不在「它能跑一个程序」**：（1）所有 `rv32ui-p-*` 的 riscv-tests 全部通过；（2）随机 difftest 显示与 Spike 零分歧；（3）综合通过、STA 干净，并报告关键路径的起点和终点；（4）每一处微架构改动都附带一张包含四个数字的表——IPC、面积、fmax，以及这次改动是否值得的结论。

**One-line positioning**: turn "microarchitecture" from a list of nouns into **the ability to trade off under constraints**. The question you must eventually answer is "if the window goes from 32 to 64, how much does IPC rise, how much does area grow, how much does frequency drop, and is it worth it" — not "I implemented out-of-order execution".

> 译：**一句话定位**：把「微架构」从一串名词，变成**在约束下做取舍的能力**。你最终必须回答的问题是「如果窗口从 32 变成 64，IPC 涨多少、面积增多少、频率降多少、值不值得」——而不是「我实现了乱序执行」。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| deliverable | n. | 交付物 | four deliverables |
| close timing | v. | 收敛时序；满足时序 | close timing |
| semantics | n. | 语义 | the semantics of a single `add` |
| cycle-accurate | adj. | 周期精确的 | a cycle-accurate model |
| parameter sweep | n. | 参数扫描 | support parameter sweeps |
| design-space exploration | n. | 设计空间探索 | Design-space exploration must precede implementation |
| out-of-order | adj. | 乱序的 | out-of-order memory |
| disambiguation | n. | 消歧，歧义消除 | LSU queue + disambiguation |
| harness | n. | 测试框架，测试台 | a difftest harness |
| committed | adj. | 已提交的（指令已完成并写入架构状态） | Every committed instruction |
| netlist | n. | 网表 | synthesizes a netlist |
| static timing analysis | n. | 静态时序分析 | runs static timing analysis on sky130 |
| critical path | n. | 关键路径 | the critical path in nanoseconds |
| in-order | adj. | 顺序（执行）的 | Rocket for in-order |
| toolchain | n. | 工具链 | an open-source toolchain |
| difftest | n. | 差分测试（与参考模型逐条对比的测试方法） | random difftest shows zero divergence |

## 2. Why Do It This Way (Functional Design)

**Trade-off one: why RV32I rather than a home-grown ISA or an x86 subset.** A home-grown ISA spends your time on the manual, the assembler, and the compiler backend — none of which is microarchitecture; an x86 subset forces you to solve variable-length decode and uop conversion first, which puts the difficulty in the wrong place. RV32I's specification is one chapter, about 40 instructions, with a complete toolchain (GCC, objdump, Spike, riscv-tests) and Rocket/BOOM available for structural comparison. **The cost is losing the fun of defining your own encoding** — which is exactly the strength of sandbox-style projects; the two are complementary.

> 译：**权衡一：为什么选 RV32I，而不是自研指令集架构（home-grown ISA）或 x86 的一个子集。** 自研 ISA 会把你的时间花在手册、汇编器和编译器后端（compiler backend）上——这些没有一样属于微架构；而 x86 子集则迫使你先解决变长译码（variable-length decode）和 uop 转换的问题，这让难点落到了错误的位置。RV32I 的规范只有一章、约 40 条指令，配有完整的工具链（GCC、objdump、Spike、riscv-tests），还有 Rocket/BOOM 可用于结构对比。**代价是失去了自定义编码的乐趣**——而这恰恰是沙盒式项目的长处；两者是互补的。

**Trade-off two: why write a cycle-accurate model before RTL.** An RTL simulation run means compiling and staring at waveforms, and changing one parameter means starting over; sweeping window sizes in a model is nearly free. More importantly, **the model forces you to think performance through**: the effect of a structural parameter is a formula in the model and a pile of waveforms in RTL. People who skip this step usually end up with a core that is "structurally complete but cannot explain why it is configured that way" — the missing dimension is precisely "why is this structure this size".

> 译：**权衡二：为什么先写周期精确模型（cycle-accurate model），再写 RTL。** 跑一次 RTL 仿真意味着要编译并盯着波形看，改一个参数就得从头再来；而在模型里扫描各种窗口大小几乎是免费的。更重要的是，**模型迫使你把性能想透**：一个结构参数（structural parameter）的影响，在模型里是一个公式，在 RTL 里则是一堆波形。跳过这一步的人，通常最终做出一个“结构上完整、却说不清为什么这样配置”的核——缺的恰恰是“这个结构为什么是这个尺寸”这一维度。

**Trade-off three: why difftest against Spike instead of your own test programs.** The coverage of hand-written tests always equals your own imagination, and CPU bugs live almost entirely in the combinations you did not think of (`x0` being written, a misaligned `jal` immediate, forwarding missing `x0`, stale reservation-station entries after a flush). Spike is the official reference model; feed it random programs and compare commit by commit, and you can localize a bug to "commit number N differs, PC=0x..., x7 expected A, got B". **The criterion is "identical instruction by instruction", not "the final result is right".**

> 译：**权衡三：为什么用 difftest 对照 Spike，而不是自己写测试程序。** 手写测试的覆盖率永远等于你自己的想象力，而 CPU 的 bug 几乎全都出在你没想到的组合里（写 `x0`、`jal` 立即数未对齐、转发（forwarding）漏掉 `x0`、冲刷之后保留站（reservation station）里残留的过期表项）。Spike 是官方参考模型；喂给它随机程序、逐条提交（commit）比对，你就能把 bug 定位成“第 N 条提交不一致，PC=0x...，x7 期望是 A，实际得到 B”。**判据是“逐条指令完全相同”，而不是“最终结果是对的”。**

**Trade-off four: why an open-source PDK rather than starting on an FPGA.** An FPGA gives you a real, runnable fmax, but it is not comparable: 50 MHz on an Artix-7 has no conversion to nanoseconds on sky130, and you cannot see which stages of logic the critical path traverses. OpenSTA plus sky130 gives **attributable timing** — which path violates, through which cells, by how many picoseconds. The cost is losing the "it really runs" feeling, plus a fussier toolchain install. **The recommended order is the reverse of intuition**: close the timing loop with the open-source flow first (a report is enough), and keep the board as a later reward.

> 译：**权衡四：为什么用开源 PDK，而不是从 FPGA 起步。** FPGA 能给你一个真实、可运行的 fmax，但它不可比较：Artix-7 上的 50 MHz 无法换算成 sky130 上的纳秒数，而且你看不到关键路径（critical path）穿过哪些逻辑级。OpenSTA 加 sky130 给出的是**可归因的时序（attributable timing）**——哪条路径违例、穿过哪些单元、差多少皮秒。其代价是失去“它真的跑起来了”的感觉，外加更挑剔的工具链安装。**推荐的顺序与直觉相反**：先用开源流程闭合时序环路（有一份报告就够），把板子留作之后的奖励。

**Trade-off five: why not start with Chisel/SpinalHDL.** They generate RTL faster, but they abstract away "how the register-transfer level actually moves" — the layer you want to learn. Write it in SystemVerilog; once you are tired of it, switch to a high-level language, and you will know exactly what that language saves you from.

> 译：**权衡五：为什么不从 Chisel/SpinalHDL 起步。** 它们生成 RTL 更快，但它们把“寄存器传输级（register-transfer level）究竟如何运转”抽象掉了——而那正是你想学的那一层。用 SystemVerilog 来写；等你写腻了它，再换高级语言，那时你会确切知道那门语言替你省掉了什么。

**Trade-off six: why cut MMU, privilege levels, multicore, floating point and vectors.** Each of them moves the center of gravity away from microarchitecture: the MMU is the intersection of OS and architecture (that line lives in `os/jos/`), multicore is coherence protocols, and floating point/vectors are the intersection of datapath and compiler. An RV32I integer core is already enough to do pipeline, prediction, out-of-order and memory access completely; **depth should be added, not area**. If you must add something, the only worthwhile additions are Zicsr plus `mcycle` (to read a cycle counter inside the RTL) and one or two Zbb instructions.

> 译：**权衡六：为什么砍掉 MMU、特权级、多核、浮点和向量。** 它们中每一个都会把重心从微架构（microarchitecture）上移开：MMU 是操作系统与体系结构的交汇点（那条线在 `os/jos/` 里），多核是一致性协议（coherence protocol），浮点/向量是数据通路（datapath）与编译器的交汇点。一个 RV32I 整数核已经足以把流水线、预测、乱序和访存完整地做一遍；**该增加的是深度，不是面积**。如果非要加点什么，唯一值得加的是 Zicsr 加上 `mcycle`（用于在 RTL 内部读取周期计数器）和一两条 Zbb 指令。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| trade-off | n. | 权衡；取舍 | Trade-off one |
| home-grown | adj. | 自研的；自家培育的 | a home-grown ISA |
| variable-length decode | n. | 变长译码 | variable-length decode and uop conversion |
| cycle-accurate | adj. | 周期精确的 | a cycle-accurate model |
| waveform | n. | 波形 | staring at waveforms |
| structural parameter | n. | 结构参数 | the effect of a structural parameter |
| difftest | n. | 差分测试（与参考模型逐条比对） | difftest against Spike |
| forwarding | n. | 旁路；前递 | forwarding missing x0 |
| PDK | n. | 工艺设计套件（process design kit） | an open-source PDK |
| critical path | n. | 关键路径 | the critical path traverses |
| attributable timing | n. | 可归因的时序 | gives attributable timing |
| register-transfer level | n. | 寄存器传输级 | the register-transfer level actually moves |
| abstract away | v. | 抽象掉；把……隐藏起来 | abstract away |
| microarchitecture | n. | 微架构 | moves the center of gravity away from microarchitecture |
| coherence protocol | n. | 一致性协议 | multicore is coherence protocols |
| datapath | n. | 数据通路 | the intersection of datapath and compiler |

## 3. Chapter Outline

Eleven steps, ordered so that each is independently verifiable and depends only on earlier artifacts.

> 译：十一个步骤，其排序使每一步都可独立验证（independently verifiable），并且只依赖更早的产物。

**S0 Toolchain and a minimal test harness.** Install Verilator + the RISC-V GCC + Spike, write a minimal `Top` (a counter is enough) and a C++ testbench, and close the loop "edit RTL → build → run → dump waveform". Criteria: `verilator --lint-only -Wall` is clean, and the VCD dumps with a toggling clock. **If this loop is not closed, every later debugging session pays the debt.**

> 译：**S0 工具链与一个最小测试框架（harness）。** 安装 Verilator + RISC-V GCC + Spike，写一个最小的 `Top`（一个计数器就够了）和一个 C++ 测试台（testbench），并打通「修改 RTL → 构建 → 运行 → 导出波形」这一闭环。验收标准：`verilator --lint-only -Wall` 无告警，且 VCD 能在时钟翻转的情况下导出。**如果这个闭环没有打通，之后每一次调试都要为此还债。**

**S1 Single-cycle RV32I.** Fetch, decode, immediate generation, ALU, branches, loads/stores, register file, `x0` hardwired to zero. Ignore performance; only functional correctness matters. Criteria: all `rv32ui-p-*` riscv-tests pass — the `p` suffix means self-checking (a write to `tohost` reports 1 on success).

> 译：**S1 单周期 RV32I。** 取指、译码、立即数生成、ALU、分支、加载/存储、寄存器堆，`x0` 硬连线为零。忽略性能；只有功能正确性才重要。验收标准：所有 `rv32ui-p-*` riscv-tests 通过 —— 后缀 `p` 表示自检（self-checking）（向 `tohost` 写入即报告 1 表示成功）。

**S2 Five-stage pipeline.** Insert the IF/ID, ID/EX, EX/MEM and MEM/WB pipeline registers, plus stall/flush paths. Criteria: the same test suite still passes in one shot (**after a pipeline rewrite, a single failure means the inter-stage semantics are wrong**), and you can point at the waveform and say "while instruction 5 is in WB, instruction 9 is in IF".

> 译：**S2 五级流水线。** 插入 IF/ID、ID/EX、EX/MEM 和 MEM/WB 流水线寄存器（pipeline register），再加上停顿/冲刷（stall/flush）通路。验收标准：同一套测试套件仍然一次通过（**在流水线重写之后，只要出现一个失败，就说明级间语义（inter-stage semantics）有误**），并且你能指着波形图（waveform）说出「当指令 5 处于 WB 阶段时，指令 9 处于 IF 阶段」。

**S3 Hazards and forwarding.** Forwarding from EX/MEM and MEM/WB with the former at higher priority, load-use stalls, branch flushes. Criteria: write a deliberately dependent assembly sequence (`lw` immediately followed by `add`) and count the stalls — they must match theory; after a mispredict flush, register state must match the sequential model.

> 译：**S3 冒险与转发。** 从 EX/MEM 和 MEM/WB 两级转发（forwarding），其中前者优先级更高；处理 load-use 停顿（load-use stall）、分支冲刷（branch flush）。验收标准：写一段刻意构造依赖关系的汇编序列（`lw` 后紧跟 `add`），数出停顿的次数——这些次数必须与理论相符；在一次预测错误冲刷（mispredict flush）之后，寄存器状态必须与顺序模型（sequential model）一致。

**S4 Branch prediction.** From always-not-taken → BHT (2-bit saturating counters) → plus BTB → optionally TAGE-lite. Criteria: on CoreMark or a hand-written loop, mispredictions per kilo-instruction (MPKI) fall and IPC rises as the predictor improves; **report both numbers, since IPC alone does not establish causality**.

> 译：**S4 分支预测。** 从总是预测不跳转（always-not-taken）→ BHT（2 位饱和计数器）→ 再加上 BTB → 可选 TAGE-lite。验收标准：在 CoreMark 或手写循环上，随着预测器改进，每千条指令的预测错误数（MPKI）下降、IPC 上升；**两个数字都要报告，因为单看 IPC 并不能确立因果关系**。

**S5 Memory: I/D caches and the memory interface.** Direct-mapped first, then two-way set-associative; write-through → write-back plus write-allocate; an MSHR prototype is optional. Criteria: for sequential/stride/random microbenchmarks, the miss rates match hand calculations of set conflicts, and the IPC change versus a cacheless version is explained.

> 译：**S5 存储：指令/数据缓存（I/D caches）与存储接口。** 先做直接映射，再做两路组相联；写直达（write-through）→ 写回（write-back）加写分配（write-allocate）；MSHR 原型是可选的。验收标准：对顺序/步长/随机微基准，缺失率与手工计算的组冲突相符，并且与无缓存版本相比的 IPC 变化得到解释。

**S6 difftest and random testing.** Feed Spike's commit log into the testbench and compare PC, instruction and writeback register instruction by instruction; then write a random instruction generator constrained to legal encodings and bounded loops. Criteria: **enough random programs run with zero divergence**; inject a fault on purpose (for example, enable writes to `x0`) and confirm difftest catches it — a difftest that cannot catch an injected fault is worthless.

> 译：**S6 差分测试（difftest）与随机测试。** 把 Spike 的提交日志（commit log）送入测试台，逐条比较 PC、指令与写回寄存器；然后编写一个受限于合法编码与有界循环的随机指令生成器。验收标准：**运行足够多的随机程序且零分歧**；故意注入一个故障（例如允许写 `x0`），并确认 difftest 能捕获它——一个抓不住注入故障的 difftest 是没有价值的。

**S7 Out-of-order front end: rename + ROB + reservation stations.** Map architectural registers onto a physical register pool, allocate and commit the ROB in order, and issue out of order from reservation stations once sources are ready. Criteria: in-order and out-of-order versions agree on the same programs; sweep the ROB/RS depths and obtain an IPC-versus-window saturation curve (**that curve is the only deliverable of this step**).

> 译：**S7 乱序前端：重命名 + ROB + 保留站。** 把架构寄存器映射到物理寄存器池，按序分配并提交 ROB，一旦源操作数就绪就从保留站乱序发射。验收标准：按序版本与乱序版本在同一批程序上结果一致；扫描 ROB/RS 深度，得到 IPC 对窗口大小的饱和曲线（**该曲线是本步骤唯一的交付物**）。

**S8 Out-of-order memory: LSQ + disambiguation.** Load/store queues, stores not reaching the cache before commit, conservative disambiguation → speculative disambiguation with an address predictor. Criteria: the IPC on `memcpy`, linked-list traversal and random access moves as expected, and the gap between "conservative" and "speculative" is attributed to the number of false dependencies.

> 译：**S8 乱序访存：LSQ + 消歧。** 加载/存储队列（load/store queue）、存储在提交（commit）之前不进入缓存、保守消歧（conservative disambiguation）→ 借助地址预测器（address predictor）的推测性消歧（speculative disambiguation）。验收标准：在 `memcpy`、链表遍历和随机访问上的 IPC 变化符合预期，并且「保守」与「推测」之间的差距能归因于假依赖（false dependency）的数量。

**S9 Timing and area loop.** Yosys synthesis, STA on sky130, reporting the critical path and area. Criteria: point at the report and say "fmax is currently limited by this path in this stage", and run one real trade-off experiment (for example, move the ALU comparators into the next stage: frequency up, CPI slightly up — report all four numbers).

> 译：**S9 时序与面积闭环。** 用 Yosys 综合（synthesis），在 sky130 上做 STA（静态时序分析，static timing analysis），报告关键路径（critical path）和面积。验收标准：能指着报告说「当前 fmax 在本阶段受这条路径限制」，并做一次真实的权衡实验（trade-off experiment）（例如把 ALU 的比较器移到下一级：频率升高、CPI 略微升高——把四个数字都报告出来）。

**S10 Performance attribution (optional, closing step).** Decompose your own core's CPI into front-end bound / bad speculation / back-end bound / memory bound, aligned with the Top-down vocabulary in `cpu-microarchitecture/`. Criteria: you can judge where the bottleneck is in a core you wrote, and the judgment is confirmed by the next change you measure.

> 译：**S10 性能归因（可选，收尾步骤）。** 把自己所写内核的 CPI 分解为前端受限（front-end bound）/ 错误推测（bad speculation）/ 后端受限（back-end bound）/ 访存受限（memory bound），与 `cpu-microarchitecture/` 中的自顶向下（Top-down）术语体系保持一致。验收标准：能判断自己写的内核中瓶颈（bottleneck）在哪里，并且这一判断被你接下来测量的一次改动所证实。

**S11 Board and power (optional, pure bonus).** Bring it up on an FPGA and report fmax; estimate power only to an order of magnitude (gate count × unit power), with no sign-off. Criteria: CoreMark on the board gives the same cycle count as simulation.

> 译：**S11 上板与功耗（可选，纯加分项）。** 把它在 FPGA 上跑起来，并报告 fmax；功耗只需估算到一个数量级（门数 × 单位功耗），不做签核（sign-off）。验收标准：板上跑 CoreMark 得到的周期数与仿真一致。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| verifiable | adj. | 可验证的 | independently verifiable |
| artifact | n. | 产物；工件 | earlier artifacts |
| harness | n. | 测试框架；测试装置 | a minimal test harness |
| testbench | n. | 测试台 | a C++ testbench |
| dump | v. | 导出；转储 | the VCD dumps |
| register file | n. | 寄存器堆 | register file |
| hardwired | adj. | 硬连线的 | `x0` hardwired to zero |
| immediate | n. | 立即数 | immediate generation |
| pipeline register | n. | 流水线寄存器 | the IF/ID, ID/EX, EX/MEM and MEM/WB pipeline registers |
| flush | n. | 冲刷（清除流水线中不应继续执行的指令） | stall/flush paths |
| inter-stage semantics | n. | 级间语义（相邻流水级之间传递的含义） | the inter-stage semantics are wrong |
| forwarding | n. | 转发（把后级已算出的结果直接送往前级使用） | Forwarding from EX/MEM and MEM/WB |
| load-use stall | n. | 载入-使用停顿（load 结果尚未就绪就必须使用而造成的停顿） | load-use stalls |
| sequential model | n. | 顺序模型（指令按程序顺序逐条执行的参照语义） | the sequential model |
| saturating counter | n. | 饱和计数器（计到边界后不再增减的计数器） | 2-bit saturating counters |
| mispredictions per kilo-instruction (MPKI) | n. | 每千条指令的预测错误数 | mispredictions per kilo-instruction (MPKI) |

## 4. What It Does Not Do

**No MMU, privilege levels, trap delivery or Linux.** Running Linux needs page tables, a TLB, U/S modes, interrupts and atomics as a whole set; adding them turns the project into "porting Linux" rather than "building microarchitecture". That line lives in `os/jos/`; the two are not merged.

> 译：**不做 MMU、特权级（privilege level）、陷阱投递（trap delivery），也不跑 Linux。** 跑 Linux 需要页表（page table）、TLB、U/S 模式、中断和原子操作（atomics）这一整套；把它们加进来，项目就变成「移植 Linux」而不是「做微架构（microarchitecture）」了。那条线在 `os/jos/` 里；两者不合并。

**No multicore and no cache coherence.** Coherence protocols (MESI, directories) are a substantial topic of their own, with no observable benefit without multiple cores, and only added verification burden.

> 译：**不做多核，也不做缓存一致性（cache coherence）。** 一致性协议（coherence protocol，如 MESI、目录（directories））本身就是一个分量很重的话题；没有多核时看不到任何可观测的收益，只会增加验证负担。

**No floating point and no vectors.** An RV32I integer core already covers pipeline, prediction, out-of-order and memory access; floating point brings rounding and exception flags, vectors bring variable length and masks — both new verification surfaces.

> 译：**不含浮点，也不含向量。** 一个 RV32I 整数核已经覆盖了流水线（pipeline）、预测（prediction）、乱序（out-of-order）与访存（memory access）；浮点会带来舍入与异常标志，向量会带来变长与掩码——两者都是全新的验证面（verification surface）。

**No exhaustive formal verification.** Bounded model checking only for small critical modules (decode, forwarding selection, ROB commit), no whole-core equivalence proof.

> 译：**不做穷尽式形式验证（exhaustive formal verification）。** 只对少量关键模块（译码、转发选择、ROB 提交）做有界模型检验（bounded model checking），不做全核的等价性证明。

**No power sign-off and no physical design.** No place and route, no IR drop, no clock-tree synthesis; area is post-synthesis cell area, frequency is the STA estimate. Those belong to digital back-end work, not microarchitecture.

> 译：**不做功耗签核（power sign-off），也不做物理设计（physical design）。** 不做布局布线（place and route），不做 IR drop 分析，不做时钟树综合（clock-tree synthesis）；面积指综合后的单元面积，频率是 STA 的估计值。这些属于数字后端工作，不属于微架构（microarchitecture）。

**No chasing SPEC scores.** CoreMark/Dhrystone are only vehicles for relative comparison; never compare absolute numbers against a commercial core — comparing IPC across cores without comparing area and power is a methodological error.

> 译：**不要追逐 SPEC 分数（SPEC scores）。** CoreMark/Dhrystone 只是用于相对比较的载体（vehicle）；绝不要拿绝对数值去和商业核心比较——在不比较面积（area）与功耗（power）的情况下跨核心比较 IPC，是方法论（methodological）上的错误。

**No submitting a modified existing core.** Rocket/BOOM may be read, compared against and imitated structurally, but cannot be your implementation — difftest would still pass and you would gain nothing.

> 译：**不要提交改造过的现成核心。** Rocket/BOOM 可以被阅读、被拿来对比、在结构上被模仿，但不能成为你的实现（implementation）——difftest 仍然会通过，而你什么也得不到。

**Common ways to go off track**: skipping the cycle model and going straight to RTL (you end up able to run but not to trade off); starting with out-of-order (the in-order pipeline is not even clean, so out-of-order bugs cannot be attributed); installing a whole PDK before writing code (the toolchain becomes the project); replacing difftest with home-made tests (coverage equals imagination); reporting IPC without area and frequency (violating the constraint premise).

> 译：**常见的跑偏方式**：跳过周期模型（cycle model）直接写 RTL（结果是你跑得起来，却做不了权衡（trade off））；一上来就做乱序（out-of-order）（顺序流水线（in-order pipeline）都还没理顺，乱序的 bug 就无法归因）；在写代码之前先装一整套 PDK（工具链（toolchain）变成了项目本身）；用自制的测试替代 difftest（覆盖率（coverage）等于想象力）；只报 IPC 而不报面积和频率（违反了约束前提（constraint premise））。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| privilege level | n. | 特权级 | privilege levels |
| trap delivery | n. | 陷阱投递（异常/陷阱传递到处理程序） | trap delivery |
| atomics | n. | 原子操作 | interrupts and atomics |
| cache coherence | n. | 缓存一致性 | no cache coherence |
| directories | n. | 目录（目录式缓存一致性协议） | (MESI, directories) |
| substantial | adj. | 分量重的，实质性的 | a substantial topic |
| out-of-order | adj. | 乱序的 | out-of-order and memory access |
| rounding | n. | 舍入 | floating point brings rounding and exception flags |
| masks | n. | 掩码 | variable length and masks |
| exhaustive | adj. | 穷尽式的、全面的 | No exhaustive formal verification |
| bounded model checking | n. | 有界模型检验 | Bounded model checking only for small critical modules |
| equivalence proof | n. | 等价性证明 | no whole-core equivalence proof |
| sign-off | n. | 签核 | No power sign-off |
| place and route | n. | 布局布线 | No place and route |
| IR drop | n. | 电压降（IR 压降） | no IR drop |
| vehicle | n. | 载体；工具；手段 | vehicles for relative comparison |

## 5. How to Talk About It in an Interview

**30-second version** (say this up front, 120–180 words)

> 译：**30 秒版本**（先说这段，120–180 词）

> I built an RV32I core, from single-cycle up to out-of-order: first a cycle-accurate model for design-space exploration, then RTL, then commit-by-commit difftest against Spike, and finally Yosys + OpenSTA on an open-source PDK for critical path and area. So every structural change comes with four numbers — IPC, area, fmax, and a verdict on whether it is worth it. I think the core of microarchitecture is not "having implemented out-of-order" but "being able to say, under frequency and area constraints, why a structure has this size". That is also why I skipped the MMU and multicore: those belong to OS and coherence protocols and would dilute this line.
>
> **译** 我构建了一个 RV32I 核心，从单周期一直到乱序（out-of-order）：先是为设计空间探索（design-space exploration）做的周期精确（cycle-accurate）模型，然后是 RTL，再是逐提交地与 Spike 做差分测试（difftest），最后是在开源 PDK 上用 Yosys + OpenSTA 看关键路径（critical path）和面积。所以每一次结构变更都附带四个数字——IPC、面积、fmax，以及一个关于它是否值得的结论。我认为微架构（microarchitecture）的核心不是“实现了乱序”，而是“能够在频率和面积约束下说明为什么某个结构是这种大小”。这也是我跳过 MMU 和多核的原因：那些属于操作系统和一致性协议（coherence protocols），会稀释这条主线。

**Eight likely follow-ups**

> 译：**八个可能的追问**

1. **"Why RV32I instead of designing your own ISA?"** → Real test: do you know the division of labor between ISA and microarchitecture.
   → Answer: designing an ISA spends time on the manual, assembler and compiler backend, none of which is microarchitecture; RV32I has an official reference model (Spike), ready-made test suites and open cores for comparison, so all the time goes into pipeline and out-of-order. **Defining your own encoding is valuable on a different axis** (sandbox projects); the two are complementary. Boundary: RV32I is integer-only, with no CSR or floating point — reading a cycle counter requires implementing Zicsr.

   > 译：**“为什么用 RV32I 而不是自己设计一套 ISA？”** → 真正的考点：你知不知道 ISA 与微架构（microarchitecture）之间的分工。 → 回答：设计一套 ISA，时间要花在手册、汇编器和编译器后端上，而这些没有一样属于微架构；RV32I 有官方参考模型（Spike）、现成的测试套件和可供对比的开源核（open cores），所以时间可以全部投到流水线和乱序执行上。**定义自己的编码在另一个维度上有价值**（沙盒项目）；两者是互补的。边界：RV32I 只有整数，没有 CSR 也没有浮点——要读周期计数器，就得实现 Zicsr。

2. **"What is the relationship between the cycle-accurate model and the RTL? Why do you need both?"** → Real test: where design-space exploration sits.
   → Answer: the model is the **parameter-sweeping tool**, the RTL is the **carrier of correctness and timing**. Sweeping the window from 32 to 256 takes minutes in the model and requires resynthesis plus a full test run in RTL. The model tells you which size to choose; the RTL proves that size can be built. Boundary: the model must be calibrated against the same trace, otherwise the two curves are not comparable.

   > 译：**“周期精确（cycle-accurate）模型和 RTL 是什么关系？为什么两个都要？”** → 真正的考点：设计空间探索（design-space exploration）处在什么位置。 → 回答：模型是**扫参数的工具**，RTL 是**正确性与时序的载体**。把窗口从 32 扫到 256，在模型里只要几分钟，在 RTL 里则要重新综合，外加跑一遍完整测试。模型告诉你该选哪个尺寸；RTL 证明这个尺寸能造出来。边界：模型必须用同一条 trace 校准，否则两条曲线不可比。

3. **"How do you prove the core is correct?"** → Real test: verification methodology rather than "I ran a program".
   → Answer: three layers. (1) the `rv32ui-p-*` riscv-tests self-checks; (2) random-program difftest against Spike's commit log, comparing PC, instruction and writeback values with zero divergence; (3) fault injection — deliberately enabling writes to `x0` or corrupting an immediate, and confirming difftest catches it. Verification that cannot fail is not verification.

   > 译：**“你怎么证明这个核是正确的？”** → 真正的考点：验证方法论，而不是“我跑过一个程序”。 → 回答：三层。(1) `rv32ui-p-*` riscv-tests 的自检；(2) 用随机程序对 Spike 的提交日志（commit log）做差分测试（difftest），比较 PC、指令和写回值，要求零分歧；(3) 故障注入（fault injection）——故意允许对 `x0` 的写入，或破坏一个立即数，然后确认 difftest 能抓到它。不会失败的验证不叫验证。

4. **"Why must you stall when a load is immediately followed by its consumer?"** → Real test: when a value becomes available, not "is there a dependency".
   → Answer: load data is only available at the end of MEM, while the consumer needs it in EX, so forwarding cannot run ahead of production; you stall one cycle and forward from MEM/WB. In an out-of-order core the dependency remains — it is simply filled with other instructions. **Out-of-order removes waiting, not dependencies.**

   > 译：**“为什么当一个载入（load）紧接着它的使用方时，你必须停顿（stall）？”** → 真正的检验是：一个值何时变为可用，而不是“是否存在依赖”。 → 答案：载入数据只有在 MEM 末尾才可用，而使用方需要在 EX 中就需要它，因此前递（forwarding）不能跑在产生之前；你停顿一个周期，并从 MEM/WB 前递。在乱序（out-of-order）核心中，依赖仍然存在——它只是被其他指令填充。**乱序消除的是等待，不是依赖。**

5. **"Is a bigger out-of-order window always better?"** → Real test: diminishing returns against superlinear cost.
   → Answer: a larger window covers more long-latency operations, but IPC saturates at the program's inherent ILP; meanwhile ROB/RS area grows roughly linearly while wakeup and select logic grow superlinearly in both area and delay, so fmax drops. **The answer is a curve, not a number** — sweep the parameters and pick the point where the IPC gain stops paying for area and frequency.

   > 译：**“更大的乱序（out-of-order）窗口总是更好吗？”** → 真正的检验：面对超线性成本时的收益递减。 → 答案：更大的窗口能覆盖更多长延迟操作，但 IPC 会在程序固有的 ILP 处饱和；同时，ROB/RS 面积大致线性增长，而唤醒（wakeup）和选择（select）逻辑在面积和延迟两方面都超线性增长，因此 fmax 下降。**答案是曲线，不是一个数字**——扫描参数，并挑选 IPC 增益不再足以抵偿面积和频率代价的那个点。

6. **"What do you do when the critical path blocks you?"** → Real test: can you translate a timing report into a structural change.
   → Answer: read the start and end points in the STA report first. The three usual suspects: the ALU carry chain (split the stage or use carry-lookahead), reservation-station wakeup plus select (bank it, use an age matrix instead of priority encoding), and rename read ports (narrow the issue width or read in batches). Re-report the four numbers after each change; if frequency rises while CPI rises, explain the net effect.

   > 译：**“当关键路径（critical path）挡住你时，你怎么办？”** → 真正的检验：你能否把时序报告（timing report）转化为结构上的改变。 → 答案：先读 STA 报告中的起点和终点。三个常见的嫌疑对象是：ALU 进位链（carry chain）（拆分该流水级，或使用先行进位（carry-lookahead））、保留站（reservation-station）唤醒加选择（把它分 bank，使用年龄矩阵（age matrix）而不是优先级编码（priority encoding）），以及重命名（rename）读端口（缩窄发射宽度（issue width），或分批读取）。每次修改后重新报告四个数字；如果频率上升而 CPI 也上升，解释净效应。

7. **"Why not use a standard FPGA flow?"** → Real test: knowing what each flow can give.
   → Answer: FPGA gives real fmax and "it actually runs", but it is neither comparable nor attributable — you cannot see which stages a path traverses. An open-source PDK plus OpenSTA gives attributable nanoseconds and area, at the cost of the board experience. So I close the timing loop with the open-source flow first and keep the board as a later reward.

   > 译：**「为什么不直接用标准的 FPGA 流程？」** → 真正的考验是：知道每种流程能给你什么。 → 回答：FPGA 给出真实的 fmax 和「它确实跑起来了」，但它既不可比较，也不可归因——你看不到一条路径经过了哪些流水级。开源的 PDK（process design kit，工艺设计套件）加上 OpenSTA，能给出可归因的纳秒数与面积，代价是失去上板的体验。所以我先用开源流程把时序闭环（timing loop）闭上，把上板留作之后的奖励。

8. **"How is this different from the five-stage pipeline in an architecture course?"** → Real test: have you only memorized the textbook.
   → Answer: the textbook gives structures and formulas; the implementation forces you to handle what textbooks omit — stale reservation-station entries on flush, `x0` write masking across every write port, stores that may not touch the cache before commit, and mispredict recovery aligned with ROB rollback. **Those boundaries are exactly the distance between textbook and implementation.**

   > 译：**「这和体系结构课上的五级流水线有什么不同？」** → 真正的考验是：你是不是只背了教科书。 → 回答：教科书给的是结构和公式；而实现逼着你去处理教科书略过的东西——冲刷（flush）时残留的保留站（reservation station）表项、跨每个写端口的 `x0` 写屏蔽（write masking）、提交前可能根本不碰缓存的存储指令（store），以及与 ROB 回滚对齐的预测失败恢复。**这些边界恰恰就是教科书与实现之间的距离。**

**Things not to say**

> 译：**不该说的话**

- **"I implemented an out-of-order CPU."** The next question is "how big is the window, why that size, what is the area, what is the fmax" — and it collapses. Talk about the trade-off behind the four numbers.

   > 译：**“我实现了一个乱序（out-of-order）CPU。”** 下一个问题就是“窗口（window）有多大，为什么选这个大小，面积是多少，fmax 是多少”——然后就垮了。要谈这四个数字背后的权衡（trade-off）。

- **"I used Verilator/Yosys, so I understand verification/synthesis."** Tools are tools; talk about the difftest comparison criterion, fault injection, and how to read an STA report.

   > 译：**“我用了 Verilator/Yosys，所以我懂验证/综合。”** 工具只是工具；要谈差分测试（difftest）的比较判据、故障注入（fault injection），以及如何读 STA 报告。

- **"IPC improved by X times."** Without a same-criterion baseline (same trace, same clock constraint, same synthesis target) do not quote a number; instead say "on the same random test set, going from a 32-entry to a 128-entry window raises IPC by A%, area by B%, and fmax falls from C to D".

   > 译：**“IPC 提升了 X 倍。”** 没有同一判据的基线（baseline）（同一 trace、同一时钟约束、同一综合目标），就不要报数字；而要说“在同一随机测试集上，窗口从 32 项增至 128 项，IPC 提升 A%，面积增加 B%，fmax 从 C 降到 D”。

- **"How does it compare to an i7?"** Different process, area and power budgets; comparing IPC across cores is a methodological error. Compare area-performance points at the same process instead.

   > 译：**“它跟 i7 比起来怎么样？”** 制造工艺、面积和功耗预算都不同；跨核比较 IPC 是方法论上的错误。应当改为在相同工艺下比较面积—性能点。

- **Quoting frequencies or areas you never measured.** Do not say "it can reach 1 GHz" without STA, and do not say "the area is small" without synthesis.

   > 译：**引用你从未测量过的频率或面积。** 没有做 STA 就不要说“它能达到 1 GHz”，没有做综合就不要说“面积很小”。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| up front | adv. | 预先；一开始 | say this up front |
| cycle-accurate | adj. | 周期精确的 | a cycle-accurate model |
| difftest | n. | 差分测试 | commit-by-commit difftest against Spike |
| critical path | n. | 关键路径 | for critical path and area |
| follow-up | n. | 后续问题；追问 | likely follow-ups |
| microarchitecture | n. | 微架构 | between ISA and microarchitecture |
| open cores | n. | 开源核 | open cores for comparison |
| out-of-order | adj. | 乱序（执行）的 | pipeline and out-of-order |
| design-space exploration | n. | 设计空间探索 | where design-space exploration sits |
| resynthesis | n. | 重新综合 | requires resynthesis plus a full test run |
| fault injection | n. | 故障注入 | fault injection |
| writeback | n. | 写回 | writeback values |
| stall | v. | 停顿；挂起 | must you stall |
| forwarding | n. | 前递；转发 | forwarding cannot run ahead of production |
| diminishing returns | n. | 收益递减 | diminishing returns against superlinear cost |
| superlinear | adj. | 超线性的 | superlinear cost |
