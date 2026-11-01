# CSAPP 项目指南（CMU CS:APP 3e · 八个 Lab）

> **创建**：2026-10-22 ｜ **实践仓**：`~/develop/learning/learning-408/csapp`
> **证据三源**：① **本地子仓真实文件**（`datalab/ bomb/ cachelab/ malloclab/ shlab/ proxylab/ archlab/ target1/`，git 分支 `attack`，3 个 commit）② **官方 3e writeup**（联网核实：malloclab / proxylab / archlab / attacklab / cachelab 评分口径）③ 本地 `README` 与骨架源码
> **配套笔记**：本文件的知识点按 `AGENTS.md` 只追加归档到 `01-数据表示与编码.ipynb` / `03-存储层次与Cache.ipynb` / `04-内存与虚拟内存.ipynb` / `10-进程与线程.ipynb` / `17-应用层.ipynb`（逐块展开时归档，本轮只出指南）
> **边界**：本文件只回答「CSAPP 这个项目怎么搞」。学习方法论见 `LEARNING.md`，落盘规则见 `AGENTS.md`，进度见 `PROGRESS.md`。
> **符号约定**（遵循 `LEARNING.md` §十）：md 里用 ASCII，写 `2^32`、`T_libc`、`w = 0.6`、`E = exp - 127`。

---

## 0 仓况体检（先看这个，它决定复习路线）

我逐文件读了本地仓，**结论与"我之前做过这个项目"的预期不符**，如实报告：

| 目录 | 真实状态 | 证据 |
|---|---|---|
| `bomb/` | ✅ **唯一有真实产出的**：`bomb/solutions`（94 行中文笔记，含 `(gdb) x/s 0x402400` 反汇编分析，覆盖 phase1–6 + secret phase） | 文件存在且含你的 gdb 分析 |
| `datalab/bits.c` | ⬜ 官方骨架：13 个 puzzle 全部是 `return 2;` / `return 0;` 占位 | `grep return` 全部是占位值 |
| `cachelab/csim.c` | ⬜ 7 行空壳，只有 `printSummary(0,0,0)` | 全文 7 行 |
| `cachelab/trans.c` | ⬜ `transpose_submit` 函数体为空 | 函数体空 |
| `malloclab/mm.c` | ⬜ 官方 `mm-naive.c` 骨架（110 行，brk 递增式，无 header/footer、不合并） | 文件头注释即 naive 版说明 |
| `shlab/tsh.c` | ⬜ 官方 starter（509 行，注释齐全，无 `fork`/`execve`/`waitpid` 实现） | grep 无 fork/execve/waitpid |
| `proxylab/proxy.c` | ⬜ 14 行空壳，只打印 UA 头 | 全文 14 行 |
| `archlab/` | ⬜ `sim.tar` **未解压**，只有 `archlab.pdf` + `simguide.pdf` | `ls archlab/sim` 不存在 |
| `target1/` | 🟡 attacklab 靶子齐全（`ctarget` `rtarget` `farm.c` `hex2raw` `cookie.txt = 0x59b997fa`），但**没有答案文件** | 有靶子无解答 |

**两个环境硬事实**（会直接影响你能不能跑）：

1. **所有参考二进制都是 Linux x86-64 ELF**：`datalab/dlc`、`cachelab/csim-ref`、`cachelab/test-csim`、`shlab/tshref`、`bomb/bomb`、`target1/ctarget` 全部是 ELF。本机是 macOS（darwin），**这些跑不了**。所以 CSAPP 这条线必须有 Linux 环境（Docker / 虚拟机 / 远程主机），macOS 只能做"读代码 + 写代码 + 静态分析"。
2. **`malloclab/` 缺 trace 文件**：本地只有 `short1-bal.rep` / `short2-bal.rep` 两个迷你 trace，`traces/` 与 `mdriver` 二进制都没有 —— 官方 handout 里的 `traces/` 需要从 `csapp.cs.cmu.edu/3e/malloclab-handout.tar` 补。

> 所以这次"复习"的准确定位是：**用你已有的 bomb lab 分析笔记当锚点，把其余七个 lab 按 408 收益重新排序，从零做起**。下面的路线就是按这个定位排的。

---

## 1 怎么读这个文件

- §2 是**全景 + 408 映射 + 关键路径**，回答"这八个 lab 到底在造什么、先做哪个、哪些根本不该碰"。
- §3 是**设计理念**，七条贯穿整个系列的主线。**这是最值钱的部分**——CSAPP 之所以是神课，不是因为题目难，是因为它每个 lab 都在逼你体会同一批设计原则。
- §4 每个 lab 一张卡片：目标 → 接口 → 机制骨架 → **关键路径**（实现顺序）→ **易错点 Top** → **设计理念** → 408 对应点 → 验收命令。
- §5 环境（Linux 硬前提）+ 调试兵器库；§6 是批次划分；**§7 是八个 lab 的逐层设计（完整讲义，含代码骨架与手算过程）—— 真正干活时看这里，§4 只是速查卡片**。
- §8 是**出口视角**（考研复试与找工作面试怎么复用这批 lab，含项目介绍话术与三个"五分钟故事"）—— 初试前不用看，初试结束当晚再翻。

---

## 2 全景

### 2.1 一句话

> **八个 lab = 把一台计算机从"位"到"网络代理"重造一遍，且每一层都只许用上一层已经造好的东西。**

### 2.2 与书的章节对齐（顺序不是随便排的）

| # | Lab | 对应书章节 | 你要造的 | 一句话本质 |
|---|---|---|---|---|
| L1 | **datalab** | Ch2 信息的表示 | `bits.c` 的 13 个位运算谜题 | 在"没有 `if`、没有 `-`、没有 `*`"的世界里重造算术与判断 |
| L2 | **bomblab** | Ch3 机器级表示 | 拆 6 个 phase（+secret）的二进制炸弹 | 只会读汇编，反推 C 源码 |
| L3 | **attacklab** | Ch3.10 缓冲区溢出 | 对 `ctarget`/`rtarget` 做 5 次攻击 | 用"数据当代码用"打破控制流 |
| L4 | **archlab** | Ch4 处理器 + Ch5 优化 | Y86-64 汇编 + 给 SEQ/PIPE 加 `iaddq` | 自己动手改一个 CPU 的数据通路 |
| L5 | **cachelab** | Ch6 存储器层次 | `csim.c`（Cache 模拟器）+ `trans.c`（转置优化） | 把"局部性"从口号变成可数的 miss 数 |
| L6 | **shlab** | Ch8 异常控制流 | `tsh.c`（带作业控制的小 shell） | 直面异步：信号、回收、竞争 |
| L7 | **malloclab** | Ch9 虚拟内存 | `mm.c`（自己的 malloc/free/realloc） | 在一段裸内存上做空间管理 |
| L8 | **proxylab** | Ch10–12 系统级 I/O + 并发 + 网络 | `proxy.c`（带缓存的并发 Web 代理） | 把前面所有东西合起来对外服务 |

**注意这个顺序的教学含义**：L1→L8 严格跟着书的章节走，每个 lab **只用"已经讲过"的知识**，且前一个 lab 的产物就是后一个 lab 的地基（L5 的局部性 → L7 的分配器布局 → L8 的缓存）。

### 2.3 408 映射表（这是你做不做某个 lab 的唯一依据）

> 权重说明：★★★ = 408 该章必考且与 lab 强相关；★★ = 有对应考点但 lab 投入偏大；★ = 只有概念层面的对应。

| Lab | 408 科目·章节 | 具体考点 | 权重 | 备注 |
|---|---|---|---|---|
| L1 datalab | 组成 · 数据表示 | 原/反/补/移码、溢出判断、移位、IEEE 754（s/exp/frac、规格化与非规格化、Bias=127） | ★★★ | **408 选择题年年考，且是大题里浮点计算的地基** |
| L5 cachelab | 组成 · 存储层次 | Cache 三种映射方式、替换算法、命中率计算、写策略、局部性、分块 | ★★★ | **组成原理大题重镇，miss 数是要手算的** |
| L7 malloclab | OS · 内存管理 | 连续分配：首次/最佳/最坏/邻近适应、**空闲块合并**、内部/外部碎片 | ★★★ | 408 直接考"动态分区分配算法"，与显式空闲链表是一回事 |
| L6 shlab | OS · 进程管理 | fork/exec/wait 语义、僵尸进程、waitpid(WNOHANG)、信号、进程组 | ★★★ | OS 进程管理核心，fork 返回两次 / 僵尸 / waitpid 必考 |
| L4 archlab | 组成 · 中央处理器 | 数据通路、指令周期、**流水线冒险（结构/数据/控制）**、转发与阻塞、CPI | ★★★（考点）/ ★（lab 投入） | 考点重要，但 Y86 是玩具 ISA，见下方取舍 |
| L2 bomblab | 组成 · 指令系统 | 寻址方式、栈帧布局、跳转表、递归的机器级表示 | ★★ | 408 考"汇编片段阅读"，不考逆向 |
| L3 attacklab | 组成 · 指令系统 | 栈帧与返回地址、缓冲区溢出、栈随机化/NX/金丝雀 | ★★ | 408 只考栈帧与溢出概念，ROP 不考 |
| L8 proxylab | 网络 · 应用层 | HTTP 报文格式、方法/状态码、**Web 缓存与代理服务器**、Cookie | ★★ | **408 不考 socket 编程**，只考 HTTP 与代理/缓存概念 |

### 2.4 关键路径：冲刺期取舍（距初试约 60 天，必须砍）

> 原则：**只做"做了能直接换算成分数"的 lab；纯工程量、纯调优、408 不考的一律降级。**

**Tier 1 — 必做（约 30–40 h，全部命中 ★★★ 考点）**

1. **L1 datalab**（3–5 h）—— 13 个谜题，做完 IEEE 754 与补码是刻进肌肉的。
2. **L5 cachelab**（6–10 h）—— Part A 模拟器 + Part B 分块优化，**命中率计算从"会背公式"变成"我调过"**。
3. **L7 malloclab**（10–15 h，最难）—— 隐式 → 显式 → 分离空闲链表三级演进，直接对应 408 动态分区分配。
4. **L6 shlab**（6–8 h）—— fork/exec/wait/信号/回收，OS 进程管理的最强直觉来源。

**Tier 2 — 做一半（约 12–18 h）**

5. **L4 archlab**：**只做 Part A**（Y86-64 汇编，3–4 h，练指令与栈）+ **Part B 的 `iaddq`**（读懂 SEQ 数据通路，2–3 h）。**Part C（CPE 优化）不要碰**——那是无底洞，且 408 只要求会算流水线 CPI，不要求会优化玩具 CPU。
6. **L8 proxylab**：**只做 Part I**（顺序代理，5–8 h，把 HTTP 报文格式吃透）+ **Part II 并发**（2–3 h，pthread + detach）。**Part III 缓存跳过**——它的 LRU + 读写锁与 cachelab / OS 同步考点重复，性价比最低。

**Tier 3 — 只读不写（约 3–4 h，但收益不低）**

7. **L2 bomblab**：你有完整 `solutions`，**别重做**。正确姿势是拿你的笔记反推"每关考了哪个机器级知识点"，列成清单（见 §4-L2）。2 h。
8. **L3 attacklab**：**只读栈帧与三级防御原理**，不做（本地连 Linux 靶机都要另配）。1–2 h。

**明确不做的**：archlab Part C、proxylab Part III、任何"Beat the Prof"类的极限优化、bufferlab（本地仓已被删除）。

### 2.5 五条实践线怎么互相借力（本仓真实存在的项目地图）

> 2026-10-22 体检确认：`modules/408/` 下现在有五份项目指南，各自独立、互不复述（真源约定见 `LEARNING.md` §〇）。CSAPP 在这张图里的位置：

| 项目 | 一句话 | 与 CSAPP 的关系 |
|---|---|---|
| **nand2tetris** | 从 NAND 门自底向上造一台计算机 | 给 Ch2/Ch4 提供「硬件底座」直觉：CSAPP 从**位**开始，它从**门**开始 |
| **CSAPP**（本文件） | 系统程序员视角：位 → 汇编 → CPU → cache → 进程 → 虚拟内存 → 网络 | **是其他所有线的公共语言**，先学它再看别的都顺 |
| **jos** | 往 x86 内核里写一个 OS | Ch8/Ch9 的「内核版」：shlab 在用户态做的事（fork/回收/页），jos 在内核态做 |
| **CS144** | 用户态 C++ 手写 TCP/IP | Ch10–12 的深化：proxylab 只是**用** socket，CS144 自己**实现**协议 |
| **CS149** | SIMD / 多核 / CUDA 性能编程 | §3 主线二（局部性）在并行世界的延伸 |

**借力方向（按需加载对应指南，别在这里展开）**：

- 学 cachelab 时若对「为什么存在 cache」没有硬件感 → 去 `NAND2TETRIS.md` 的 CPU 部分；
- 学 shlab 时想看「内核态怎么做同一件事」→ 去 jos 的笔记（实践仓 `learning-408/jos`）；
- 学 proxylab 的 HTTP 时 → CS144 线已归档了整套传输层/应用层讲义（`16-传输层.ipynb` 现 23 cell），直接衔接。

**跨项目总原则**：五条线共用同一套 ipynb 归档体系（本仓 15 个 ipynb，2026-10-22 全部 JSON 校验通过），追加时遵守 `AGENTS.md` 的只追加纪律即可。

---

## 3 设计理念：贯穿八个 lab 的七条主线

> 这一节是整个文档最值钱的部分。CSAPP 的题目会忘，这七条不会；而且它们每一条都在 408 里以不同形式重复出现。

### 主线一：抽象是契约，不是魔法（L1 → 全局）

`int` 的 `+`、`-`、`<` 看起来天经地义，datalab 把它们全部没收，只留 `! ~ & ^ | + << >>`，然后要你实现"异或""取负""判等""条件选择"。**做一遍你就知道：抽象是有成本的，成本就是底下的那几次位运算。**

同一条主线在 IEEE 754 上最漂亮：规格化数与非规格化数的衔接不是拍脑袋的——

```
exp == 0   (非规格化):  E = 1 - Bias,  尾数 M = 0.frac
exp != 0   (规格化):    E = exp - Bias, 尾数 M = 1.frac
```

`E = 1 - Bias`（而不是 `-Bias`）这一个常数偏移，让最大的非规格化数与最小的规格化数**严丝合缝地接上**，浮点加减的"逐级下溢"（gradual underflow）才成立。**这是设计，不是巧合。** 408 考 IEEE 754 时最爱问的"为什么偏置是 127""非规格化数怎么算"，根子就在这。

### 主线二：局部性是第一性原理，而且它是可测量的（L5 → L7 → L8）

cachelab 干的唯一一件事是：**把"局部性好"这个形容词，翻译成一个整数（miss 数）**。

三个必须刻进去的事实：

- **容量够 ≠ 不 miss**。32×32 的 int 矩阵是 4 KB，cache 是 1 KB，装不下——这是**容量不命中**；但即使只访问 1 KB 内的数据，直接映射下两个地址只要组索引相同就会互相驱逐，这是**冲突不命中**。**冲突不命中是"硬件便宜"付出的代价**，也是分块（blocking）能救回来的部分。
- **分块的本质是"把工作集切成能装进 cache 的小块"**，让每块数据被读入后一次用尽再丢弃。
- 同一个技术贯穿三个 lab：cachelab 的矩阵分块、malloclab 的"按大小类分桶"（segregated list 让同类大小的块在内存里聚拢）、proxylab 的 Web 缓存 —— **全是"用局部性换时间"**。

### 主线三：时间 ↔ 空间权衡，且必须"先定指标再优化"（L7 → L4 → L5）

malloclab 的评分公式本身就是一句设计哲学（官方 3e 口径）：

```
P = w * U + (1 - w) * min(1, T / T_libc),  w = 0.6
```

`U` 是空间利用率，`T` 是吞吐。官方明说：**两个指标各最多贡献 w 和 1-w，不许走极端**。这就是在教你"工程上没有最优解，只有权衡点"。

同一思路在另外两个 lab：archlab 用 **CPE（cycles per element）**、cachelab 用 **miss 阈值**（32×32 < 300、64×64 < 1300、61×67 < 2000）。

**通用方法论**：想优化任何东西，第一步是**定义一个可测量的指标**，第二步才是动手。408 里这也成立——算 CPI、算命中率、算平均周转时间，都是同一套动作。

### 主线四：先写检查器，再写实现（L7 的 `mm_checkheap`，L5 的 LRU 时间戳）

malloclab 单独给 `mm_checkheap`（堆一致性检查器）打 5 分，原因很实在：**指针算术写错一行，症状会在十万次操作之后才爆**，没有检查器你根本定位不到。要检查的不变量（invariant）就那么几条：

- prologue / epilogue 块完好
- 每个块对齐、大小合法、`header.size == footer.size`、alloc 位一致
- **堆里不存在两个相邻的空闲块**（合并没漏）
- 显式链表：`A->next == B ⟺ B->prev == A`；所有指针落在 `[mem_heap_lo(), mem_heap_high()]`
- 遍历数出来的空闲块个数 == 顺着链表数出来的个数

**这条主线的泛化**：任何"手维护的数据结构"，先写下它的不变量清单，再写代码，最后用检查器把不变量断言出来。cachelab 的 LRU 时间戳、proxylab 的"缓存里无重复条目"，都是同一件事。

### 主线五：异步是常态，同步才是例外；核心问题是"谁回收"（L6 → L8）

shlab 里最要命的三个 bug 全来自同一个认知偏差——**以为子进程结束是"同步发生在我 wait 的地方"**：

1. **回收**：子进程死了才变僵尸，SIGCHLD 是**异步**到的。所以 handler 里要 `while (waitpid(-1, &status, WNOHANG | WUNTRACED) > 0)`——**循环**，因为**信号不排队**，5 个子进程同时死可能只递送一次 SIGCHLD。
2. **竞争**：`fork` 之后，子进程可能在父进程 `addjob` **之前**就退出并触发 handler 里的 `deletejob` —— 删了一个还没加进去的 job。**解法是 fork 前 `sigprocmask(SIG_BLOCK, SIGCHLD)`，addjob 之后解除**；而且子进程继承了阻塞掩码，必须在 `execve` 前恢复。
3. **等待前台**：既然 SIGCHLD 已经被 handler 收走了，`waitfg` 就不能再 `waitpid` 阻塞（会抢掉 handler 的工作）。正解是**循环 `sigsuspend` / 睡眠轮询，直到 jobs 表里没有前台 job**。

proxylab 是同一条主线的另一个面：**共享数据要锁，锁的粒度决定并发度**。官方明确禁止"一把大锁锁住整个 cache"，要求**多读者并发、单写者独占**——这就是读者-写者问题，408 OS 同步章节的标准模型。

### 主线六：安全边界是"数据可以变代码"（L3）

attacklab 用五个 phase 演示了一次完整的**防御—攻击螺旋**：

| 防御手段 | 它挡住什么 | 攻击怎么绕 |
|---|---|---|
| **栈随机化（ASLR）** | 攻击者算不出注入代码的地址 | 用栈上已有的相对位置 / 用 `rsp` 推算 |
| **栈不可执行（NX / W^X）** | 注入的字节码根本不能执行 | **ROP**：不注入代码，改用程序里**现成的**指令片段（gadget，来自 `farm.c`），用栈上的一串地址把它们串起来 |
| **金丝雀（stack canary）** | 覆盖返回地址前会先踩到金丝雀 | 本 lab 的靶子**没开** canary（所以前三关能成功） |

**这条主线的普适结论**：只要"数据"和"代码"在同一块内存里、且"返回地址"这种控制流信息存在可被写穿的位置，**抽象边界就会被打破**。408 考栈帧布局，本质上就是考"控制流信息放在栈上"这件事。

### 主线七：接口（interface）决定实现自由度（L1/L7/L8 对比）

三个 lab 都在教同一件事：**约束良好的窄接口，能让你把实现整个换掉而不影响上层**。

- `mm.c` 只暴露 `mm_init / mm_malloc / mm_free / mm_realloc` 四个函数 → 你可以从"naive brk 递增"一路换到"分离空闲链表"，`mdriver` 一行不用改。
- `cachelab.c` 只暴露 `printSummary(hits, misses, evictions)` → 你的模拟器用什么数据结构随便。
- `proxy.c` 只有 `main(argc, argv)` → 单线程换线程池、无缓存换 LRU 缓存，`driver.sh` 照样跑。

**408 里的对应**：OS 的"系统调用接口"、网络的"分层服务访问点（SAP）"——**分层的好处正是"下层实现可替换"**。CS144（你另一个项目）用 C++ 替换 Linux 协议栈，靠的也是同一条原则。

---

## 4 八个 lab 的卡片（大纲级）

> 每张卡片给"骨架 + 关键决策 + 必踩的坑"。**代码级展开在逐块阶段做**（见 §6）。

### L1 · datalab（Ch2）

- **目标**：改 `datalab/bits.c`，13 个函数全部通过 `btest`，且不违反 `dlc` 的编码规则。
- **题目清单与 ops 上限**（本地 `bits.c` 实测）：

| 函数 | Max ops | 核心思路 |
|---|---|---|
| `bitXor` | 14 | `(x & ~y) | (~x & y)`（或德摩根的等价写法） |
| `tmin` | 4 | `1 << 31` |
| `isTmax` | 10 | `!(~(x+1) ^ x) & !!(x+1)`（第二项是为了排除 `x == -1`） |
| `allOddBits` | 12 | 拼掩码 `0xAAAAAAAA`：`m = 0xAA; m |= m<<8; m |= m<<16;` 再 `!(m & ~x)` |
| `negate` | 5 | `~x + 1` |
| `isAsciiDigit` | 15 | 两次"减法看符号位"判 `0x30 <= x <= 0x39` |
| `conditional` | 16 | 造全 0/全 1 掩码：`mask = !!x << 31 >> 31`，再 `(mask & y) | (~mask & z)` |
| `isLessOrEqual` | 24 | 异号看符号位，同号看 `x + ~y + 1` 的符号位 |
| `logicalNeg` | 12 | `((x | (~x + 1)) >> 31) ^ 1`（只有 0 与自身相反数符号位同为 0） |
| `howManyBits` | 90 | 二分：先看高 16 位是否全 0/1，再逐级收窄 |
| `floatScale2` | 30 | 拆 `exp/frac`；`exp == 0xFF` 原样返回（NaN/∞）；`exp == 0` 非规格化 → `frac << 1`；`exp == 0xFE` → 变 ∞；否则 `exp + 1` |
| `floatFloat2Int` | 30 | `E = exp - 127`；`E < 0` → 0；`E >= 31` → `0x80000000`（越界）；否则 `(1.frac)` 移位并按符号位取负 |
| `floatPower2` | 30 | `x > 127` → `0x7F800000`；`x < -149` → 0；`-126 <= x <= 127` → `(x + 127) << 23`；否则非规格化 `1 << (x + 149)` |

- **关键路径**：① 先装 Linux 环境 → ② 通读 `bits.c` 顶部规则（允许的操作符、常量只能 0–255、整数是 32 位补码、右移是算术右移）→ ③ 按"整数类（前 9 个）→ `howManyBits` → 浮点类（后 3 个）"顺序做 → ④ 每个函数写完立刻 `./btest -f 函数名` → ⑤ 最后 `./dlc bits.c` 查规则 + `./driver.pl` 综合评分。
- **易错点 Top 5**
  1. **常量只能用 0–255**：想要 `0xAAAAAAAA` 必须移位拼出来。
  2. **`-` 不是减号而是"取负 + 加"**：`x - y` 要写 `x + ~y + 1`。
  3. **`>>` 是算术右移**（题目保证），所以 `x >> 31` 得到的是符号位掩码（全 0 或全 1），这是造掩码的基本手法。
  4. **`!` 是允许的逻辑非**，`!!x` 是把任意非零归一为 1 的标准技巧 —— 注意它和 `x != 0` 的区别：后者不是允许的操作符。
  5. **浮点三题要先拆字段**（`s = uf >> 31`、`exp = (uf >> 23) & 0xFF`、`frac = uf & 0x7FFFFF`），且**必须单独处理 `exp == 0xFF`（NaN/∞）和 `exp == 0`（非规格化）两个边界**。
- **设计理念**：见主线一（抽象的成本）+ 主线三（IEEE 754 的平滑衔接是设计）。
- **408 对应**：组成·数据表示（★★★）。
- **验收**：`make && ./btest`（全 13 项），`./dlc bits.c`（无违规），`./driver.pl`（总分）。

### L2 · bomblab（Ch3）

- **状态**：✅ 你已做完，`bomb/solutions`（94 行）覆盖 phase1–6 + secret phase。
- **正确复习姿势（2 h，不重做）**：拿你的笔记反推"每关考的是哪个机器级知识点"，列成下面这张对照表，然后**只复习你不熟的那几个知识点**：

| Phase | 你的答案 | 背后考的机器级知识点 |
|---|---|---|
| 1 | `Border relations with Canada have never been better.` | 字符串比较、`x/s` 看常量串 |
| 2 | `1 2 4 8 16 32` | 数组循环、指针递增（`rbx = &num[1]`） |
| 3 | `0 207` | **跳转表 `jmp *0x402470(,%rax,8)`** = switch-case，注意小端读表 |
| 4 | `7 0` | 递归 `func4` + 二分中点向零取整 `mid = (edx + esi + sign(edx-esi)) / 2` |
| 5 | `ionefg` | **字符低 4 位作索引**查表拼串（ASCII 与位操作） |
| 6 | `4 3 2 1 6 5` | **链表 + 降序重排**（`node->next` 指针重连，6 个节点循环 5 次） |
| secret | — | **二叉搜索树 `fun7`**：`2*fun7(left)` / `2*fun7(right)+1`，路径即编码 |

- **设计理念**：主线一（C 的每一行在机器级长什么样）+ "**逆向是阅读能力的极限测试**"。
- **408 对应**：组成·指令系统与汇编阅读（★★）。408 只考"给一段汇编问它在干什么"，所以**跳转表、递归栈帧、链表指针**这三个形态要能一眼认出。
- **验收（复习形式）**：遮住答案，只看 `objdump -d bomb > bomb.asm`，看能否推出每关的输入。

### L3 · attacklab（Ch3.10）

- **目标**：对 `target1/ctarget`（phase 1–3，代码注入）与 `target1/rtarget`（phase 4–5，ROP）构造攻击串，cookie `0x59b997fa`（本地文件实测）。
- **分值（官方口径）**：phase1 = 10、phase2 = 25、phase3 = 25、phase4 = 35、phase5 = 5，共 100。
- **关键路径（若真要做，需 Linux）**：① `objdump -d ctarget` 找 `getbuf` 的 `BUFFER_SIZE`（**不要照抄别人的 0x28，以你手里的二进制为准**）→ ② phase1 只覆盖返回地址为 `touch1` 地址 → ③ phase2 把注入字节码放在buf 起始处，返回地址指向 buf（用 gdb 拿栈顶地址）→ ④ phase3 注入串里放 cookie 字符串 → ⑤ phase4/5 从 `farm.c`（`gcc -Og -c farm.c` 后 `objdump -d`）里找 gadget，用 `hex2raw` 生成字节串。
- **易错点 Top 4**
  1. **字节序**：`hex2raw` 要求**小端写法**，字 `0xdeadbeef` 要输入 `ef be ad de`。
  2. **不能出现 `0x0a`**（换行会被 `Gets` 当成输入结束）。
  3. **必须加 `-q`**（自学者本地跑，否则会去连不存在的评分服务器）。
  4. **Ubuntu 22.04 上 `ctarget` 会因 `printf` 的 `movaps` 16 字节对齐要求而段错误**（已有人实测；Debian/老 Ubuntu 可行）——**这是环境问题不是你错了**。
- **设计理念**：见主线六（防御—攻击螺旋）。
- **408 对应**：组成·栈帧与缓冲区溢出概念（★★）；ROP 不考。
- **建议**：**只读原理，不做**。你的时间投到 L5/L7/L6 上回报高得多。

### L4 · archlab（Ch4 + Ch5）

- **本地版本**：`archlab.pdf` 经文本提取确认是 **Y86-64 + `iaddq`**（`iaddl` 出现 0 次），即 **3e 口径**。
- **三部分**：
  - **Part A（30 分）**：用 Y86-64 汇编写 `sum.ys`（迭代求和）、`rsum.ys`（递归）、`copy.ys`（拷贝 + xor 校验），要求 `sum_list`/`rsum_list` 返回 `0xcba` 到 `%rax`。
  - **Part B（35 分）**：在 `sim/seq/seq-full.hcl` 里实现 `iaddq V, rB`（**同时需要寄存器与立即数、且要设置条件码**——这是它与 `irmovq` 的唯一区别，也是它必须单独存在的理由）。
  - **Part C（80 分，建议放弃）**：改 `pipe-full.hcl` + `ncopy.ys`，把平均 CPE 压到最低。评分 `S = 0 (c > 12.5)` / `24*(12.5 - c) (10 <= c <= 12.5)` / `60 (c < 10.0)`，baseline 平均 CPE ≈ 15.18，官方最佳 ≈ 9.27。
- **关键路径（建议做 A + B）**：`tar xf sim.tar` → `cd sim/misc && make`（编 `yas`/`yis`）→ 写三个 `.ys`，用 `./yas xxx.ys && ./yis xxx.yo` 验证 → Part B 进 `sim/seq`，改 hcl 后 `make VERSION=full`，跑 `../y86-code` 的 benchmark 回归 + `../ptest` 的 `iaddq` 回归。
- **易错点 Top 3**
  1. **`%r15` 不能当通用寄存器用**（Y86-64 用它做程序计数器），用了必炸。
  2. **`.ys` 必须先 `irmovq stack, %rsp` 设栈**，否则 `call`/`ret` 越界。
  3. **`iaddq` 必须 `set CC`**，漏了会导致后续 `jXX`/`cmovXX` 全错。
- **设计理念**：**"指令集的一个小小增删，会牵动数据通路的每条线"**——`iaddq` 要动 `srcB / aluA / aluB / dstE / set_cc` 五个信号。这就是 408 考"数据通路与控制信号"时想让你建立的感觉。
- **408 对应**：组成·中央处理器与流水线（考点 ★★★，lab 投入 ★）。**做 A+B 建立数据通路直觉，C 放弃。**

### L5 · cachelab（Ch6）★核心

- **两部分**：
  - **Part A（27 分）**：写 `csim.c` —— 一个 Cache 模拟器，参数 `-s <组索引位数> -E <相联度> -b <块偏移位数> -t <trace文件>`，支持 `L`（load）/`S`（store）/`M`（modify = L + S），**LRU 替换**，输出 `hits misses evictions`。
  - **Part B（26 分）**：优化 `trans.c` 的 `transpose_submit`，在 **s=5, E=1, b=5**（32 组、每组 1 行、块 32 B = 8 个 int、共 1 KB）的直接映射 cache 上把 miss 数压到阈值以下。
- **Part B 评分（官方，联网核实）**：

| 矩阵 | 满分线 | 零分线 |
|---|---|---|
| 32 × 32 | < 300 | > 600 |
| 64 × 64 | < 1300 | > 2000 |
| 61 × 67 | < 2000 | > 3000 |

- **Part B 的规则（必守）**：最多 12 个 `int` 局部变量（含被调用函数的栈上变量总和）、**不能 `malloc`**、**不能改 A**（只能改 B）、不能用 `long` 绕过、不能改 `"Transpose submission"` 描述串。
- **关键路径**：① Part A：`getopt` 解析 → 二维数组/结构体表示 `S = 2^s` 组 × `E` 行，每行 `{valid, tag, lru_counter}` → 从地址里切 `tag / 组索引 / 块偏移` → 命中/不命中/驱逐三类分支 → 用 `csim-ref` 对拍（**Linux 必需**）→ ② Part B：先写暴力版看 baseline（32×32 约 1183 miss）→ 做 8×8 分块 → 处理对角线冲突 → 再攻 64×64（8×8 不够，见下）→ 最后 61×67（16×16 分块通常就够）。
- **为什么 8×8 分块在 64×64 上失效（这是本 lab 最有价值的一段推导）**：
  - 32×32：一行 32 int = 128 B = 4 个块；`A[i][j]` 的组索引 ∝ `i*4 + j/8`；数组 A 与 B 的基址相差 32×32×4 B = 4096 B，恰是 cache 容量（1024 B）的整数倍 → **A[i][j] 与 B[i][j] 映射到同一组**，对角线块尤其惨烈。8×8 分块 + 一次读满 8 个局部变量即可把 miss 压到 300 以下。
  - 64×64：一行 64 int = 256 B = 8 个块，**行间距 256 B 正好等于一整个 cache 的组数跨度**，于是 `A[i][j]` 与 `A[i+8][j]` 的组索引**相同** —— 8×8 分块里的 8 行会自己把自己驱逐掉。所以 64×64 必须换思路（4×4 分块 + 先用 A 的上半块填 B 的左上、再把 A 的左下搬到 B 的右上，即"两步搬运"）。
- **易错点 Top 5**
  1. **`M` 是一次 load + 一次 store**（命中算 2 次 hit，不命中算 1 miss + 1 hit），别只算一次。
  2. **地址不用真的存数据**：模拟器只关心 tag/组/块偏移，不需要存字节。
  3. **LRU 可以用"时间戳递增"或"计数器"两种实现**，但**只在驱逐时才需要准**——命中也要更新时间戳。
  4. **组索引与块偏移的切分**：`组索引 = (addr >> b) & ((1 << s) - 1)`，`tag = addr >> (s + b)`，写错一位全盘皆输。
  5. **Part B 别去优化"运行时间"**——评分只看 miss 数，把代码从循环里提出来毫无意义。
- **设计理念**：见主线二（局部性可测量）+ 主线三（先定指标）。
- **408 对应**：组成·存储层次（★★★，大题）。
- **验收**：`make && ./test-csim`（Part A）、`./test-trans`（Part B，Linux 下用 `csim-ref` 对拍）、`./driver.py`（总分）。

### L6 · shlab（Ch8）★核心

- **目标**：实现 `shlab/tsh.c` —— 一个带**作业控制**的 shell：支持前台/后台（`&`）、`jobs`/`fg`/`bg` 内建命令、`Ctrl-C`（SIGINT）与 `Ctrl-Z`（SIGTSTP）转发给前台作业。
- **关键路径（严格按这个顺序，能避开 90% 的坑）**：
  1. `eval` + `parseline`（解析命令行、判 `&`）→ 先只做**前台**：`fork` → 子进程 `setpgid(0,0)` + `execve` → 父进程 `addjob` + `waitfg`。
  2. **加 SIGCHLD handler**：`while (waitpid(-1, &status, WNOHANG | WUNTRACED) > 0) { deletejob / 改状态 }`，区分 `WIFEXITED`（正常退出）/`WIFSIGNALED`（被信号杀死）/`WIFSTOPPED`（被 Ctrl-Z 停住）。
  3. **堵竞争**：`fork` **前** `sigprocmask(SIG_BLOCK, &mask_all, &prev)`，`addjob` **后** `sigprocmask(SIG_SETMASK, &prev)`；子进程里 `execve` **前** `sigprocmask(SIG_SETMASK, &prev)`（因为它继承了父进程的阻塞掩码）。
  4. `waitfg`：不能用 `waitpid` 阻塞（会和 handler 抢），改成 `while (前台作业仍存在) sigsuspend(&empty_mask)`（或 `sleep(1)` 轮询，先求对再求优雅）。
  5. 内建命令：`jobs`（遍历 job 表）、`bg <job>`（改状态 + `kill(-pid, SIGCONT)`）、`fg <job>`（改状态 + `kill(-pid, SIGCONT)` + `waitfg`）、`quit`。
  6. `sigint_handler` / `sigtstp_handler`：**转发给整个前台进程组**，`kill(-pid, sig)`（**负 pid = 发给进程组**，这是 POSIX 的约定）。
- **易错点 Top 5**
  1. **信号不排队** → handler 里必须 `while` 循环 `waitpid`，只 `waitpid` 一次会漏掉同时结束的多个子进程（僵尸残留）。
  2. **fork 与 addjob 的竞争**（上面第 3 步），不阻塞 SIGCHLD 就是定时炸弹。
  3. **`kill(-pid, sig)` 的负号**：单个子进程用 `pid`，发给进程组用 `-pid`。Ctrl-C 必须发给整组（前台作业可能是管道里的多个进程）。
  4. **子进程继承阻塞掩码**：忘了在 `execve` 前恢复，被 exec 的程序会带着被屏蔽的信号跑。
  5. **输出格式要对得上 `tshref.out`**：`sdriver.pl` 是逐行对比的（含 `[1] (1234) command &` 这类提示行），格式差一个空格就判错。
- **设计理念**：见主线五（异步是常态、谁回收）。
- **408 对应**：OS·进程管理（★★★）：fork 返回两次、exec 后地址空间替换、`wait/waitpid` 与 `WNOHANG`、僵尸进程、进程组。
- **验收**：`make && ./sdriver.pl -t trace01.txt -s ./tsh -a "-p"`（逐个 trace01–16），或 `./sdriver.pl -t trace01.txt -s ./tshref -a "-p" ` 对照参考输出（**`tshref` 是 ELF，需 Linux**）。

### L7 · malloclab（Ch9）★核心·最难

- **目标**：实现 `malloclab/mm.c` 的 `mm_init / mm_malloc / mm_free / mm_realloc`（+ `mm_checkheap`）。
- **硬规则**：8 字节对齐；只改 `mm.c`；**禁止全局复合数据结构**（不能有全局数组/结构体/链表，只能有标量指针）；只能用 `memlib.h` 提供的 `mem_init / mem_sbrk / mem_heap_lo / mem_heap_hi`。
- **评分（官方 3e 口径，联网核实）**：正确性 20 + 性能 35 + 风格 10；`P = w*U + (1-w)*min(1, T/T_libc)`，`w = 0.6`。参考水位（他校实测可类比）：**隐式链表 + first-fit ≈ 50–52**，**显式链表 + first-fit ≈ mid-80s**。
- **关键路径（三级演进，每级都要先跑通再升级）**：
  1. **Level 0（理解用）**：读懂骨架 `mm-naive.c`（brk 递增、无 header、不合并、不复用）——知道它为什么利用率接近 0。
  2. **Level 1 隐式空闲链表**（目标 50+）：header（size | alloc 位）+ footer（为常数时间反向合并）+ prologue/epilogue；`mm_free` 里做**四情况合并**（前后都空 / 前空 / 后空 / 都不空）。
  3. **Level 2 显式空闲链表**（目标 80+）：空闲块体里塞 `pred/succ` 指针，让搜索只遍历空闲块（吞吐大幅提升）；分配策略 first-fit 或 next-fit。
  4. **Level 3 分离空闲链表（segregated free list）**（冲高分）：按大小类分桶（如 `{16, 32, 64, ..., inf}`），近似 best-fit 且搜索是 O(1) 桶定位。
  5. **realloc 独立实现**：能就地扩展（后一块空闲且够大）就就地扩，否则 malloc + memcpy + free。
- **易错点 Top 6**
  1. **指针算术必须用 `char *`（或 `void *`）做加减**：`void *bp = (char *)block + size`，用 `int *` 会按 4/8 字节缩放，差之千里。**官方建议把指针操作全封进宏**（`GET / PUT / PACK / GET_SIZE / GET_ALLOC / HDRP / FTRP / NEXT_BLKP / PREV_BLKP`）。
  2. **8 字节对齐**：`size` 的低 3 位被拿去当 alloc 标志，所以对齐后大小至少 16 B（header + footer + 对齐 + 两个指针）。
  3. **`mem_sbrk` 只能增不能减**：堆只能长，空间只能靠复用省出来。
  4. **合并要检查边界**：别越出 epilogue；也别把 prologue 合并掉。
  5. **`mm_checkheap` 要早写、要真写**（官方单独给分，而且它是你唯一的救命工具）。
  6. **先过前 9 个 trace（只有 malloc/free），再管后 2 个（含 realloc）** —— 官方 hint 明说的顺序。
- **缺件提醒**：本地 `malloclab/` **没有 `traces/` 也没有 `mdriver` 二进制**，需从官方 handout 补齐。
- **设计理念**：见主线三（时空权衡 + 指标先行）+ 主线四（先写检查器）。
- **408 对应**：OS·内存管理（★★★）——**首次适应 / 最佳适应 / 最坏适应 / 邻近适应、碎片、合并**，与显式空闲链表是同一套概念的两种说法。
- **验收**：`make && ./mdriver -V -v`（Linux），先看正确性再看 `Perf index`。

### L8 · proxylab（Ch10–12）

- **三部分与分值（官方 3e，联网核实）**：Basic Correctness 40 + Concurrency 15 + Cache 15 = **70 分**。
- **Part I（必做）**：顺序 Web 代理 —— 读请求行 `GET http://host[:port]/path HTTP/1.0`，**改写成相对 URI + `Host` / `User-Agent` / `Connection: close` / `Proxy-Connection: close` 头**，转给服务器，把响应原样回给客户端。
- **Part II（建议做）**：每连接一线程，**`pthread_detach`**（否则内存泄漏）；`csapp.c` 里的 `open_clientfd` / `open_listenfd` 基于 `getaddrinfo`，**是线程安全的**。
- **Part III（建议跳过）**：缓存，MAX_CACHE_SIZE = 1 MiB、MAX_OBJECT_SIZE = 100 KiB，近似 LRU，**读与写都算"使用"**，且**禁止一把大锁**（要求多读者并发 → 读者-写者锁）。
- **关键路径**：① 用 `telnet` 手敲一个 HTTP 请求打通最小闭环 → ② 解析 URL（`strstr(url, "//")` → host / port / path，注意没有 `//` 的相对形式与带 `:port` 的形式）→ ③ 组装转发请求（**必须自己带上 User-Agent 等四个头**）→ ④ 用 `Rio_readlineb` / `Rio_writen` 做 I/O（**不可用大写封装的 `Open_clientfd` 等，它们出错会 `exit` 掉整个代理** —— 正确做法是关掉这条连接、结束这个线程）→ ⑤ Part II 加线程。
- **易错点 Top 5**
  1. **`csapp.c` 的错误处理函数是"出错即 exit"**，代理服务器是长跑进程，必须自己写错误处理（官方明确会扣 style 分）。
  2. **I/O 必须用 RIO**（处理"短读"），裸 `read` 会在大响应上截断。
  3. **`SIGPIPE` 必须忽略**：客户端断开后写 socket 会收到 SIGPIPE 直接杀死进程。
  4. **线程要 detach**（或 join），否则每连接泄漏一份资源。
  5. **URL 解析的三种形态**都要覆盖：`http://host/path`、`http://host:port/path`、以及缺 `//` 的裸路径。
- **设计理念**：见主线五（锁的粒度）+ 主线七（接口决定实现自由度）+ 主线二（缓存即局部性）。
- **408 对应**：网络·应用层（★★）——HTTP 报文格式、状态码、**Web 缓存与代理服务器**（这是真考点，socket 编程不是）。
- **环境提醒**：`proxylab/tiny`（tiny web server）是 **ELF 二进制**，`driver.sh` 依赖它 → **必须在 Linux 上跑**。
- **验收**：`make && ./driver.sh`（Linux）。

---

## 5 环境与调试兵器库

### 5.1 Linux 是硬前提（本机 macOS 跑不了）

体检确认这些是 ELF x86-64：`datalab/dlc`、`cachelab/csim-ref`、`cachelab/test-csim`、`shlab/tshref`、`bomb/bomb`、`target1/ctarget`、`archlab` 的 sim（待解压）、`proxylab/tiny`。

**可选方案（任选其一，我没有查你这台机器上装了哪个，需要你确认）**：
1. Docker：`docker run -it --rm -v ~/develop/learning/learning-408/csapp:/csapp ubuntu:22.04 bash`，容器内 `apt install build-essential gdb valgrind`（archlab 还需 `bison flex`）。
2. 虚拟机 / 远程 Linux 主机（x86-64）。

**macOS 上仍然能做的**：读汇编、写所有 lab 的 C/Y86 代码、跑不依赖 ELF 的部分（`cachelab` 的 `csim.c` 自编译自跑、`malloclab` 的 `mm.c` 逻辑推演）。**不能做的**：对拍参考实现、跑 `bomb`/`ctarget`、`driver.sh`。

### 5.2 兵器清单

| 场景 | 工具 |
|---|---|
| 看汇编 | `objdump -d`、`gdb` 的 `disas` / `x/s` / `x/x`（你的 bomb 笔记里就在用 `x/s 0x402400`） |
| 位运算调试 | `datalab/fshow`（看浮点位）、`ishow`（看整数位） |
| Cache trace | `cachelab/traces/{yi, yi2, dave, trans, long}.trace` + `csim-ref -v`（`-v` 逐行看命中/驱逐） |
| 堆调试 | 自己写的 `mm_checkheap` + `gdb` 的 `watch` |
| 信号/进程 | `strace`（Linux）、`ps -o pid,ppid,pgid,stat`、`kill -l` |
| 网络 | `telnet <host> <port>` 手敲请求、`curl -x http://localhost:PORT URL` 走代理 |
| 内存/线程 | `valgrind --leak-check=full`（Linux）、`valgrind --tool=helgrind`（查竞争） |

---

## 6 批次划分（对应 §7 的章节）

按 Tier 1 → Tier 2 → Tier 3 顺序。**每一块的讲义已在 §7 展开**（含代码骨架与手算过程），知识点 cell 归档进对应 ipynb。

| 批次 | 内容 | 归档目标 |
|---|---|---|
| 批次 1 | **L1 datalab**：13 题逐个给解法与位级推导 + IEEE 754 三题完整手算 | `01-数据表示与编码.ipynb`（新建） |
| 批次 2 | **L5 cachelab**：Part A 模拟器设计 + Part B 三种矩阵的分块推导（含 64×64 两步搬运） | `03-存储层次与Cache.ipynb`（新建） |
| 批次 3 | **L7 malloclab**：隐式 → 显式 → 分离链表三级，含宏定义、四情况合并、realloc | `04-内存与虚拟内存.ipynb`（新建） |
| 批次 4 | **L6 shlab**：eval/fork/回收/竞争/信号转发完整骨架 + 16 个 trace 的考点分配 | `10-进程与线程.ipynb`（已有，追加） |
| 批次 5 | **L4 archlab A+B** + **L8 proxylab I+II**（简版） | `00-计算机系统概述.ipynb`（已有）/ `17-应用层.ipynb`（已有） |
| 批次 6 | **L2 bomblab 复习清单** + **L3 attacklab 原理**（只读） | `06-指令系统与汇编.ipynb`（按需新建） |

---

## 7 逐层设计（完整讲义）

### 7.1 datalab · 逐层设计（Ch2）

#### 7.1.1 先把规则刻进骨头

`bits.c` 顶部写死的六条（本地文件实测）：

1. **允许的操作符只有**：`! ~ & ^ | + << >>`（**没有** `-`、`*`、`/`、`<`、`>`、`&&`、`||`、`if`、`?:`、循环）。
2. **整型常量只能是 0–255**（0xFF 以内）。想要 `0xAAAAAAAA` 必须移位拼出来。
3. **`int` 是 32 位补码**，右移 `>>` 是**算术右移**（补符号位）—— 这是"造掩码"手法的根基。
4. **`unsigned` 也是 32 位**，右移是逻辑右移。
5. 每条题有 **Max ops 上限**，由 `dlc` 计数：**只数二元/一元操作符，不数括号、不数赋值、不数常量**。
6. 浮点题默认遵循 IEEE 754 单精度：1 位符号 + 8 位阶码（Bias = 127）+ 23 位尾数；**向偶数舍入**；NaN/∞ 的处理每题单独规定。

#### 7.1.2 五个通用武器（13 题全靠它们拼出来）

| # | 手法 | 写法 | 说明 |
|---|---|---|---|
| 1 | 全 0 / 全 1 掩码 | `mask = !!x << 31 >> 31` | `!!x` 归一成 0/1，左移 31 到符号位，算术右移 31 复制符号位 → `x != 0 ? 0xFFFFFFFF : 0` |
| 2 | 取负 / 减法 | `-x` 写 `~x + 1`；`x - y` 写 `x + ~y + 1` | 补码的定义就是这么来的 |
| 3 | 取符号位 | `x >> 31` | 非负 → 0；负 → `0xFFFFFFFF`（= -1） |
| 4 | 判相等 | `!(a ^ b)` | 异或为 0 ⟺ 相等 |
| 5 | 拼大常量 | `m = 0xAA; m |= m << 8; m |= m << 16;` | 逐段翻倍拼出 32 位掩码 |

**第 1 条是 datalab 的万能钥匙**：造出"条件掩码"之后，`if` 就变成了 `(mask & A) | (~mask & B)`。你在 `conditional` 那一题里亲手造的这个东西，就是后面 `isLessOrEqual`、`isAsciiDigit` 的公共零件。

#### 7.1.3 整数类 9 题：逐个拆解

```c
/* 1. bitXor —— Max ops 14，实际 5 */
int bitXor(int x, int y) {
    return (x & ~y) | (~x & y);
}

/* 2. tmin —— Max ops 4，实际 1（常量不计数） */
int tmin(void) {
    return 1 << 31;              /* 0x80000000 == INT_MIN */
}

/* 3. isTmax —— Max ops 10，实际 8 */
int isTmax(int x) {
    /* Tmax + 1 == Tmin，~Tmin == Tmax，故 ~(x+1) == x  ⟺  x == Tmax 或 x == -1 */
    return !(~(x + 1) ^ x) & !!(x + 1);   /* 第二项排除 -1（x+1 == 0） */
}

/* 4. allOddBits —— Max ops 12，实际 7 */
int allOddBits(int x) {
    int m = 0xAA;                /* 常量 <= 255 合法 */
    m |= m << 8;                 /* 0xAAAA */
    m |= m << 16;                /* 0xAAAAAAAA：bit1,3,5,...,31 */
    return !(m & ~x);            /* x 的奇数位若全为 1，则 ~x 与 m 无交集 */
}

/* 5. negate —— Max ops 5，实际 2 */
int negate(int x) {
    return ~x + 1;
}

/* 6. isAsciiDigit —— Max ops 15，实际 11 */
int isAsciiDigit(int x) {
    int lo = x + ~0x30 + 1;      /* x - '0'，符号位为 0 表示 x >= 0x30 */
    int hi = 0x39 + ~x + 1;      /* '9' - x，符号位为 0 表示 x <= 0x39 */
    return !(lo >> 31) & !(hi >> 31);
}

/* 7. conditional —— Max ops 16，实际 8 */
int conditional(int x, int y, int z) {
    int mask = !!x << 31 >> 31;  /* x != 0 -> 全 1；x == 0 -> 全 0 */
    return (mask & y) | (~mask & z);
}

/* 8. isLessOrEqual —— Max ops 24，实际 13 */
int isLessOrEqual(int x, int y) {
    int sx = x >> 31, sy = y >> 31;
    int same = !(sx ^ sy);
    int diff = y + ~x + 1;                      /* y - x */
    /* 同号：看 y - x 的符号位；异号：x 为负则 x < y */
    return (same & !(diff >> 31)) | (!same & sx);
}

/* 9. logicalNeg —— Max ops 12，实际 5 */
int logicalNeg(int x) {
    /* x 与 -x 异号（或同为 0）：只有 x == 0 时二者符号位同为 0 */
    return ((x | (~x + 1)) >> 31) + 1;
}
```

**逐题验证（自己动手过一遍，别信我）**

- `isTmax(0x7FFFFFFF)`：`x+1 = 0x80000000`，`~(x+1) = 0x7FFFFFFF`，`^ x = 0` → `!0 = 1`；`!!(x+1) = 1` → 结果 1 ✓。`isTmax(-1)`：`x+1 = 0`，`~0 = 0xFFFFFFFF`，`^ (-1) = 0` → 第一项也是 1，**靠 `!!(x+1) = 0` 压掉** → 0 ✓（这是唯一会被漏掉的边界，官方题目就是冲它来的）。
- `logicalNeg(0)`：`~0+1 = 0`，`0|0 = 0`，`>>31 = 0`，`+1 = 1` ✓。`logicalNeg(Tmin)`：`~Tmin+1 = Tmin`，`|` 后仍是 `Tmin`，`>>31 = -1`，`+1 = 0` ✓（Tmin 的相反数是它自己，但符号位仍是 1，所以照样成立）。
- `isLessOrEqual(-1, 1)`：`sx = -1`，`same = 0`，`!same & sx = -1`（非零即真）→ 1 ✓。
- `allOddBits(0xAAAAAAAA)`：官方示例给的就是它，`~x = 0x55555555`，`m & ~x = 0` → 1 ✓。

#### 7.1.4 howManyBits：唯一的"算法题"（Max ops 90）

**题意**：返回表示 `x` 所需的**最少位数**（按补码算，含符号位）。`0 → 1`、`1 → 2`、`-1 → 1`、`2 → 3`、`-2 → 2`。

**关键转化**：负数的位数 = 它按位取反后的正数的位数（`~(-2) = 1`，与 `-2` 同为 2 位）。所以第一步把负数取反成正数，后面就只处理"找最高有效位"。

```c
int howManyBits(int x) {
    int s = x >> 31;                     /* 负 -> 全 1 */
    x = (s & ~x) | (~s & x);             /* 负数取反，正数不变 */
    int c1 = !!(x >> 16) << 4;  x >>= c1;   /* 高 16 位有货？有则右移 16 */
    int c2 = !!(x >>  8) << 3;  x >>= c2;   /* 再看 8 */
    int c3 = !!(x >>  4) << 2;  x >>= c3;
    int c4 = !!(x >>  2) << 1;  x >>= c4;
    int c5 = !!(x >>  1);       x >>= c5;
    return c1 + c2 + c3 + c4 + c5 + x + 1;   /* +1 是补码必带的符号位 */
}
```

**手算验证**：`x = 2`（`0b10`）→ 取反跳过 → `c1..c4 = 0`，`c5 = !!(2>>1) = 1`，`x = 1` → `0+0+0+0+1+1+1 = 3` ✓（补码 `010`）。`x = -2` → 取反得 `1` → `c5 = 0`，`x = 1` → `1 + 1 = 2` ✓（补码 `10`）。

**这就是二分查找的位运算版本**，也是"为什么 Max ops 给到 90"的原因——允许你写笨一点的版本。

#### 7.1.5 浮点三题：先把 IEEE 754 拆解成公式

```
位布局:  [31] s | [30..23] exp (8 bit) | [22..0] frac (23 bit)

exp != 0 (规格化):   E = exp - 127,   M = 1.frac    值 = (-1)^s * M * 2^E
exp == 0 (非规格化): E = 1 - 127 = -126, M = 0.frac 值 = (-1)^s * M * 2^E
exp == 0xFF:         frac == 0 -> ±inf；frac != 0 -> NaN
```

**为什么非规格化的 E 取 `1 - Bias` 而不是 `-Bias`**（主线一里讲过，这里给出算证据）：

- 最小规格化数：`exp = 1, frac = 0` → 值 `= 1.0 × 2^(1-127) = 2^-126`
- 最大非规格化数：`exp = 0, frac = 0x7FFFFF` → 值 `= 0.111...1₂ × 2^-126 = 2^-126 - 2^-149`
- 两者之间**相差恰好一个 `2^-149`**（最小非规格化步长），中间不留缝。

这个"严丝合缝"就是 `E = 1 - Bias` 这个常数偏移换来的，浮点加减的**逐级下溢**（gradual underflow）靠它成立。408 若问"偏置为何是 127""非规格化数怎么算"，根子在这。

```c
/* 11. floatScale2 —— 返回 2.0 * f 的位表示，Max ops 30 */
unsigned floatScale2(unsigned uf) {
    unsigned s    = uf & 0x80000000;
    unsigned exp  = (uf >> 23) & 0xFF;
    unsigned frac = uf & 0x7FFFFF;

    if (exp == 0xFF) return uf;              /* NaN / inf：原样返回 */

    if (exp == 0) {                          /* 非规格化：尾数左移一位 */
        frac <<= 1;
        if (frac & 0x800000) {               /* 尾数溢出 -> 自然升为规格化 */
            exp = 1;
            frac &= 0x7FFFFF;
        }
        return s | (exp << 23) | frac;
    }

    exp++;                                   /* 规格化：阶码 +1 */
    if (exp == 0xFF) frac = 0;               /* 上溢 -> +inf */
    return s | (exp << 23) | frac;
}

/* 12. floatFloat2Int —— (int)f，越界返回 0x80000000，Max ops 30 */
int floatFloat2Int(unsigned uf) {
    unsigned s    = uf >> 31;
    int      exp  = (uf >> 23) & 0xFF;
    unsigned frac = uf & 0x7FFFFF;
    int      E    = exp - 127;

    if (E < 0)  return 0;                    /* |f| < 1 -> 截断为 0 */
    if (E >= 31) return 0x80000000;          /* 超出 int 范围（含 inf/NaN） */

    frac |= 0x800000;                        /* 补回隐含的最高位 1 */
    if (E < 23) frac >>= (23 - E);           /* 小数点右移不到位就右移 */
    else        frac <<= (E - 23);

    if (s) return ~frac + 1;                 /* 不能用一元 '-'，补码取负 */
    return frac;
}

/* 13. floatPower2 —— 返回 2.0^x 的位表示，Max ops 30 */
unsigned floatPower2(int x) {
    if (x > 127)  return 0xFF << 23;         /* +inf（注意：常量只能 <= 255，必须移位构造） */
    if (x < -149) return 0;                  /* 比最小非规格化还小 -> 0 */
    if (x >= -126) return (unsigned)(x + 127) << 23;   /* 规格化 */
    return 1u << (x + 149);                  /* 非规格化：2^(x+149) 落在 frac 上 */
}
```

**手算验证（三个边界必须自己算一遍）**

| x | 推导 | 结果 | 含义 |
|---|---|---|---|
| `0` | `(0+127) << 23` | `0x3F800000` | 1.0 ✓ |
| `127` | `(127+127) << 23 = 254<<23` | `0x7F000000` | 最大有限数 |
| `128` | `> 127` | `0x7F800000` | +∞ |
| `-126` | `(1) << 23` | `0x00800000` | 最小**规格化**数 |
| `-127` | `1 << (-127+149) = 1<<22` | `0x00400000` | 最大**非规格化**数 |
| `-149` | `1 << 0` | `0x00000001` | 最小非规格化数 |
| `-150` | `< -149` | `0` | 下溢到 0 |

`floatScale2` 的非规格化分支也验证一次：`uf = 0x00400000`（`frac = 0x400000`，值 `= 2^22 × 2^-149 = 2^-127`）→ `frac <<= 1 = 0x800000` 触发进位 → `exp = 1, frac = 0` → `0x00800000 = 2^-126` ✓ **乘 2 之后正好跨进规格化区，中间没有缝**。

#### 7.1.6 易错点复查清单（写完 13 题后逐条自问）

1. 我用了 `-x` 吗？（不允许，必须 `~x + 1`）
2. 我用了 `if` / `?:` / `&&` / `||` 吗？（不允许）
3. 常量里有 `> 255` 的吗？（`0x7F800000` 必须写成 `0xFF << 23`）
4. `dlc` 报 ops 超限了吗？（`./dlc bits.c` 会逐题报）
5. 浮点题处理了 `exp == 0` 和 `exp == 0xFF` 两个边界吗？（每题都要）
6. `>>` 用在有符号数上是否依赖算术右移？（是的，题目保证；但别在 `unsigned` 上指望它）

#### 7.1.7 验收

> **机器验证记录（2026-10-22，本地 Python）**：本节 13 个解法已按"32 位补码 + 算术右移"语义做过性质测试 —— 整数 9 题各 2 万组随机输入、`howManyBits` 2 万组 + 9 个边界值、`floatScale2`/`floatFloat2Int` 各 20 万组随机位模式、`floatPower2` 覆盖 `x ∈ [-160, 139]` 全区间，**零失败**。一个值得记住的插曲：验证脚本第一版在 `conditional`/`logicalNeg` 上报了假错 —— 因为 Python 的 `>>` 是**逻辑**右移，而这两题的正确性恰恰依赖 C 的**算术**右移（题目明确保证）。这两题也因此在纯逻辑右移的机器上无解。

```bash
make btest          # 或者 make
./btest             # 13 题全测（含正确性 + ops 计数）
./btest -f floatScale2    # 单题测
./dlc bits.c        # 规则合规检查（不报就是过）
./driver.pl         # 综合评分
./ishow 0x80000000  # 看整数的十进制/十六进制
./fshow 0x3F800000  # 看浮点的 s / exp / frac 分解
```

> **设计理念小结**：datalab 真正教你的不是 13 个 trick，而是**"抽象之下是什么"**。当你用 `(mask & y) | (~mask & z)` 写出一个 `if` 的时候，你才算真的理解了"控制流 = 数据选择"；当你亲手处理 `exp == 0 → exp == 1` 的进位，你才算真的理解了 IEEE 754 为什么要那么设计。

### 7.2 bomblab · 逐层设计（Ch3，复习式）

> 你已经做完了（`bomb/solutions`，6 phase + secret）。这一节**不是让你重做**，而是把那 94 行笔记里的每个答案，反推成"它背后考的是哪个机器级知识点"，再按 408 的口径过一遍。

#### 7.2.1 通用拆解流程（这套动作比某个炸弹的答案值钱）

```
1. objdump -d bomb > bomb.asm          # 全部反汇编，离线看
2. 定位 <main>：找到 phase_1 ... phase_6 的调用点与 read_line / phase_defused
3. 定位 <phase_N>：从函数入口往下读，先找"输入被送到哪里"（sscanf 的格式串是关键）
4. 找常量：objdump -s -j .rodata  /  gdb 里 x/s <addr>  (你笔记里的 x/s 0x402400 就是这么用的)
5. 关键判断处下断点：break *0x40xxxx ;  run ;  x/s $rax ...
6. 推输入 -> 试 -> 若引爆炸弹，回到第 3 步重新精读
```

**三个"一眼认出来"的形态**（408 考汇编阅读就考这三种）：

| 形态 | 汇编特征 | 对应 C 结构 |
|---|---|---|
| **跳转表** | `jmp *0x402470(,%rax,8)` + 一段连续 8 字节地址区 | `switch (i) { case ... }` |
| **递归调用** | 函数体内 `call` 自身 + 栈上保存参数 | `int f(int a, int l, int r)` |
| **链表遍历** | `mov 0x8(%rbx), %rax` / `mov (%rax), %eax`（偏移 8 = next 指针） | `while (p) { ... p = p->next; }` |

#### 7.2.2 七关的知识点对照（按你的 solutions 反推）

| Phase | 你的答案 | 机器级知识点 | 三层问答 |
|---|---|---|---|
| 1 | `Border relations with Canada have never been better.` | **字符串比较**：`strings_not_equal` 循环逐字节比 | ① 逐字节 `cmpb` 直到 `\0`；② 为什么不一次比 8 字节（长度未知必须逐个）；③ 若给一段 `movzbl (%rdi,%rax), %eax` 循环，能否认出是 `strcmp` |
| 2 | `1 2 4 8 16 32` | **数组 + 指针递增**：`rbx = &num[1]`，`cmp -0x4(%rbx), %eax` | ① 循环里比较相邻元素；② 编译器用指针自增代替下标（`num[i]` → `*(p++)`）；③ 认出 `add $0x4,%rbx` = 数组步进 4 字节（int） |
| 3 | `0 207` | **跳转表 switch**：`jmp *0x402470(,%rax,8)` | ① 索引 → 表基址 + 8×索引 → 取目标地址；② 为什么用表而不用 `if-else` 链（O(1) vs O(n)）；③ **小端读表**：表里的 8 字节要反着读 |
| 4 | `7 0` | **递归 + 二分**：`func4(a, 0, 14)`，中点 `mid = (edx + esi + sign(edx-esi)) / 2` | ① 递归栈帧与参数传递（前 6 个参数走寄存器）；② "向零取整"的除法在汇编里是 `+sign` 再 `/2`；③ 给一段递归汇编能否画出调用树 |
| 5 | `ionefg` | **字符低 4 位作索引查表** | ① `and $0xf, %eax` + 查表拼串；② ASCII 与位操作的配合；③ 认出 `and $0xf` 是"取低 4 位"的掩码操作 |
| 6 | `4 3 2 1 6 5` | **链表排序**：6 个节点循环 5 次，比较 `node->val` 降序 | ① 结构体内存布局（val 在 0，next 在 8）；② 链表重排是改指针不是搬数据；③ 认出 `0x8(%rbx)` 是 `next` 字段 |
| secret | — | **二叉搜索树**：`fun7(root, x)`，返回值编码路径 `2*f(left)` / `2*f(right)+1` | ① BST 查找路径；② 用 2 进制位编码"左右"路径（路径即编码）；③ 给返回式能否反推输入 |

#### 7.2.3 408 视角的三个抓手

408 **不考逆向**，但考"给一段 GCC 生成的 x86-64 汇编，问它在干什么"。所以从 bomb 里要带走的是这三条：

1. **栈帧布局**：`call` 压返回地址 → `push %rbp; mov %rsp,%rbp` → 局部变量在 `-0x8(%rbp)` 一带 → 第 7 个及以上参数走栈。
2. **参数传递约定**：`%rdi %rsi %rdx %rcx %r8 %r9`（整型/指针），返回值 `%rax`。
3. **数组/结构体/指针的三种寻址**：`(%rbx)`、`0x8(%rbx)`、`(%rax,%rbx,4)`（基址+变址×比例 = 数组下标）。

**复习验收（30 分钟）**：遮住 `solutions`，只看 `bomb.asm` 的 `phase_3` 与 `phase_6`，要求自己说出"这是 switch 跳转表""这是链表降序重排"，并指出判断依据的那条指令。

### 7.3 attacklab · 逐层设计（Ch3.10，只读原理）

> 建议只读不做（Tier 3）。但**栈帧与返回地址这一层必须懂**——408 考"函数调用的机器级表示"，考的就是这张图。

#### 7.3.1 一切的起点：`getbuf` 的栈帧

```c
unsigned getbuf() {
    char buf[BUFFER_SIZE];     /* BUFFER_SIZE 要自己 objdump 出来，别照抄别人的 0x28 */
    Gets(buf);                 /* 无边界检查 —— 漏洞就在这 */
    return 1;
}
```

对应的栈帧（`getbuf` 被调用时，从高地址往低地址看）：

```
高地址
+---------------------------+
| test 的栈帧               |
|  ...                      |
| 返回地址（回到 test）      |  <- ret 指令会把它弹进 %rip
+---------------------------+
| 保存的 %rbp（若有）        |
+---------------------------+
| buf[BUFFER_SIZE-1]        |  <- Gets 从 buf[0] 往上写
|  ...                      |
| buf[0]                    |  <- 输入的第一个字节
+---------------------------+  低地址（%rsp）
```

**一次缓冲区溢出做了什么**：往 `buf[0]` 开始写，写满 `BUFFER_SIZE` 之后继续写，就会**覆盖"返回地址"那个 8 字节槽位**。`getbuf` 执行 `ret` 时，`%rip` 被改成你写进去的那个值 —— **控制流被数据劫持**。

这就是主线六说的：**只要控制流信息（返回地址）放在可被写穿的内存里，"数据"和"代码"的边界就不存在**。

#### 7.3.2 五个 phase 与三级防御的对应

| Phase | 程序 | 手段 | 目标 | 官方分值 | 它绕过了什么 |
|---|---|---|---|---|---|
| 1 | ctarget | CI | 跳到 `touch1` | 10 | 无（栈固定、可执行） |
| 2 | ctarget | CI | 跳到 `touch2` 且传参 cookie | 25 | 需要注入代码把 cookie 放进 `%rdi` |
| 3 | ctarget | CI | 跳到 `touch3` 且传 cookie 字符串 | 25 | 字符串要放在不被覆盖的位置 |
| 4 | rtarget | ROP | 用 gadget 实现 `touch2` | 35 | **栈随机化 + 栈不可执行** |
| 5 | rtarget | ROP | 用 gadget 实现 `touch3` | 5 | 同上，且要拼字符串地址 |

**三级防御与被绕方式**（这张表是本节的核心）：

| 防御 | 机制 | 攻击怎么绕 |
|---|---|---|
| **栈随机化 ASLR** | 每次运行栈基址不同 → 猜不到注入代码的地址 | 用栈上已有的相对关系 / 用 `%rsp` 推算 / **改用不需要知道地址的 ROP** |
| **栈不可执行 NX（W^X）** | 栈页标记不可执行 → 注入的字节码直接段错误 | **ROP**：不注入代码，改用程序里**现成**的指令片段（gadget），用栈上一串地址把它们串起来 |
| **金丝雀 canary** | 返回地址前放一个随机值，返回前校验 | 本 lab 的靶子**没开** canary（所以前三关才能成功） |

#### 7.3.3 ROP 的原理（phase 4/5 的本质）

思路一句话：**既然不能注入指令，就把程序里已有的 `ret` 结尾的小片段（gadget）当积木，用栈上的一串地址串成程序。**

```
栈（从 buf[0] 往上）:
+----------------------------+
| gadget1 的地址              |  <- ret 后跳到这里
| gadget2 的地址              |
| gadget3 的地址              |
| touch2 的地址               |
| cookie (0x59b997fa)        |
+----------------------------+

执行流: ret -> gadget1 (pop %rax; ret) 
                -> gadget2 (mov %rax,%rdi; ret) 
                -> touch2
```

**典型 gadget（在 `farm.c` 里找，形态通用，具体地址以你反汇编结果为准）**：

| 想做的事 | 需要的 gadget 形态 |
|---|---|
| 把栈上的值弹进寄存器 | `popq %rax ; ret`（字节码 `58 c3`） |
| 寄存器间搬数据 | `movq %rax, %rdi ; ret`（`48 89 c7 c3`） |
| 算地址（phase 5 关键） | `lea (%rdi,%rsi,1), %rax ; ret` |
| 加法 | `addq %rbx, %rax ; ret` |

找法：`gcc -Og -c farm.c && objdump -d farm.o`，扫所有以 `c3`（`ret`）结尾的字节序列 —— **注意 `c3` 也可能是指令中间字节，所以要从真实指令边界开始扫**。

#### 7.3.4 实操易错点（真做的话）

1. **必须加 `-q`**：自学者本地跑，否则会去连不存在的评分服务器。
2. **小端**：`hex2raw` 里字 `0xdeadbeef` 要输入 `ef be ad de`。
3. **不能出现 `0x0a`**：换行会被 `Gets` 当成输入结束（`0x0a` = `\n`）。
4. **Ubuntu 22.04 上 `ctarget` 会因 `printf` 的 `movaps` 要求 16 字节对齐而段错误**（有人实测；Debian / 老版本 Ubuntu 可行）——**这是环境问题，不是你错了**。
5. **`BUFFER_SIZE` 以你手里的二进制为准**：`objdump -d ctarget | grep -A20 "<getbuf>:"`，看 `sub $0x??, %rsp`。

#### 7.3.5 408 对应点

- **必考**：栈帧布局、`call/ret` 对栈的作用、返回地址的位置、函数调用的机器级表示。
- **概念层**：缓冲区溢出、栈随机化 / 不可执行 / 金丝雀三种防御各自的**作用点**（选择题可能问"哪种防御能挡住哪类攻击"）。
- **不考**：ROP gadget 的构造、具体字节码。

### 7.4 archlab · 逐层设计（Ch4 + Ch5，只做 Part A + B）

#### 7.4.1 Y86-64 速查（与 x86-64 的三点关键差异）

| 项目 | Y86-64 | 说明 |
|---|---|---|
| 寄存器 | `%rax %rcx %rdx %rbx %rsp %rbp %rsi %rdi %r8..%r14` | **没有 `%r15`**（它被用作程序计数器）—— 用它必炸，这是最著名的坑 |
| 立即数 | `irmovq $0x100, %rbx` | 立即数必须用 `$` 前缀，且**只能作为 `irmovq` 的源** |
| 访存 | `mrmovq D(%rB), %rA` / `rmmovq %rA, D(%rB)` | 内存→寄存器、寄存器→内存，不支持 `mov` 内存到内存 |
| 运算 | `addq subq andq xorq` | 只能操作**寄存器**（不能带立即数，这正是 `iaddq` 存在的理由） |
| 跳转 | `jmp jle jl je jne jge jg` + `cmovXX` | 依赖条件码（ZF/SF/OF） |
| 栈 | `pushq popq call ret` | 同 x86-64 语义 |
| 停止 | `halt` / `nop` | — |

**汇编文件格式（`.ys`）**

```
        .pos 0                  # 从地址 0 开始
init:   irmovq stack, %rsp      # 必须先设栈，否则 call/ret 越界
        call main
        halt

        .align 8                # 数据按 8 字节对齐
ele1:   .quad 0x00a             # 链表节点：val, next
        .quad ele2
...
stack:  .quad 0                 # 栈底（栈向低地址长，所以放在最后）
```

#### 7.4.2 Part A：三个程序骨架

```asm
# ---- sum.ys：迭代求和 ----
sum_list:
        irmovq $0, %rax
        jmp    test
loop:
        mrmovq (%rdi), %rsi     # val = ls->val   (偏移 0)
        addq   %rsi, %rax
        mrmovq 8(%rdi), %rdi    # ls = ls->next   (偏移 8)
test:
        andq   %rdi, %rdi       # 用 andq 自身设置 ZF（Y86-64 没有 test 指令）
        jne    loop
        ret
```

```asm
# ---- rsum.ys：递归版 ----
rsum_list:
        andq   %rdi, %rdi
        je     zero             # ls == NULL -> 返回 0
        mrmovq (%rdi), %rsi     # val = ls->val
        pushq  %rsi             # val 过不了递归，必须压栈保存
        mrmovq 8(%rdi), %rdi    # ls->next
        call   rsum_list        # 递归（结果在 %rax）
        popq   %rsi
        addq   %rsi, %rax
        ret
zero:
        irmovq $0, %rax
        ret
```

```asm
# ---- copy.ys：拷贝 + xor 校验 ----
# 参数: %rdi = src, %rsi = dest, %rdx = len；返回 %rax = xor 校验和
copy_block:
        irmovq $0, %rax
        jmp    test
loop:
        mrmovq (%rdi), %r8      # val = *src
        irmovq $8, %r9
        addq   %r9, %rdi        # src++
        rmmovq %r8, (%rsi)      # *dest = val
        addq   %r9, %rsi        # dest++
        xorq   %r8, %rax        # result ^= val
        irmovq $1, %r9
        subq   %r9, %rdx        # len--
test:
        andq   %rdx, %rdx
        jg     loop             # len > 0
        ret
```

**验收**：`./yas sum.ys && ./yis sum.yo`，要求 `%rax == 0xcba`；`copy.ys` 还要求三个值 `0x00a 0x0b0 0xc00` 被拷到 `dest` 起始的 24 字节，且**不得破坏其它内存**（所以循环边界差一个就是 0 分）。

#### 7.4.3 Part B：给 SEQ 加 `iaddq`（这是本节的核心）

**指令语义**：`iaddq V, rB` → `R[rB] <- R[rB] + V`，**并且设置条件码**。编码：`C0 rB V(8字节)`（第一个寄存器字段未用）。

**为什么需要它**：Y86-64 的 `addq` 只能加寄存器，`irmovq` 不能做加法。要执行 `rB += 8`，标准 Y86-64 得写两条指令（`irmovq $8, %r9; addq %r9, %rB`）。`iaddq` 把它合成一条 —— **这就是 CISC 与 RISC 之争的一个缩影**（408 必考 CISC/RISC 对比）。

**SEQ 各阶段要动的信号**（在 `sim/seq/seq-full.hcl` 里）：

| 阶段 | 信号 | iaddq 的取值 | 与 `irmovq` 的差别 |
|---|---|---|---|
| fetch | `instr_valid` | `icode in { ..., IIADDQ }` | 要加进合法集合 |
| fetch | `need_regids` | `1`（有寄存器字节） | 同 irmovq |
| decode | `srcA` | `RNONE`（不读 rA） | 同 irmovq |
| decode | **`srcB`** | **`rB`** | **irmovq 是 `RNONE`** ← 差别 1 |
| execute | `aluA` | `valB` | irmovq 的 valB 无意义 |
| execute | `aluB` | `valC` | 同 irmovq |
| execute | `set_cc` | **1** | **irmovq 是 0** ← 差别 2 |
| write-back | `dstE` | `rB` | 同 irmovq |
| PC | `new_pc` | `valP` | 同 irmovq |

**整段 HCL 只多两处**（示意，`I` 表示 icode）：

```
word srcB = [
    I in { IRRMOVQ, IMRMOVQ, IOPQ, IRMMOVQ } : rB;
    I in { IIADDQ }                          : rB;   # <- 新增
    I in { IPUSHQ, IPOPQ, ICALL, IRET }      : RRSP;
    1                                        : RNONE;
];

word set_cc = I in { IOPQ };                          # 原式
word set_cc = I in { IOPQ, IIADDQ };                  # <- 新增
```

**这一改动的价值远超 35 分**：它让你看清"**一条指令在数据通路里就是若干个控制信号的一次取值**"。408 考流水线数据通路时，让你填的正是这张表。

#### 7.4.4 Part C 为什么建议放弃

评分看平均 CPE（cycles per element，块长 1..64 平均）：`S = 0 (c > 12.5)` / `24*(12.5 - c) (10 <= c <= 12.5)` / `60 (c < 10.0)`，baseline ≈ 15.18，官方最佳 ≈ 9.27。要压下去得做：加 `iaddq` → 用 `iaddq` 消掉减法 → 利用其 `set_cc` 省掉一条比较 → 8 路循环展开 → 处理余数 → 调 PIPE 的转发逻辑……

**这是一整个独立的优化课题，且 408 只要求你会算流水线的 CPI，不要求你会优化玩具 CPU。** 时间投到 malloclab / shlab 上回报高一个量级。

#### 7.4.5 验收命令

```bash
cd sim/misc && make                 # 编 yas / yis
./yas sum.ys && ./yis sum.yo        # Part A：看 %rax 是否 0xcba
cd ../seq   && make VERSION=full    # Part B：重建带 iaddq 的 SEQ
(cd ../y86-code; make testssim)     # 回归测试：benchmark 全过
(cd ../ptest;  make SIM=../seq/ssim TFLAGS=-i)   # iaddq 专项回归
```

### 7.5 cachelab · 逐层设计（Ch6）★核心

#### 7.5.1 先把 cache 参数算成具体的数

Part B 的评分 cache：`s = 5, E = 1, b = 5`。把它翻译成人话：

| 量 | 值 | 怎么来的 |
|---|---|---|
| 组数 `S` | `2^5 = 32` | `s` 是组索引位数 |
| 相联度 `E` | 1 | **直接映射**（每组只有一行 —— 冲突不命中的根源） |
| 块大小 `B` | `2^5 = 32` 字节 = **8 个 int** | `b` 是块内偏移位数 |
| 总容量 | `32 × 1 × 32 = 1024` 字节 = **1 KB** | `S × E × B` |

地址怎么切（这行写错全盘皆输）：

```
tag      = addr >> (s + b)
set_idx  = (addr >> b) & ((1 << s) - 1)      /* 先去掉块内偏移，再取低 s 位 */
b_offset = addr & ((1 << b) - 1)             /* 模拟器里其实用不上 */
```

#### 7.5.2 Part A：模拟器骨架（`csim.c`）

```c
typedef struct { int valid; unsigned long tag; unsigned long stamp; } line_t;

/* 全局：S 组 × E 行 */
static line_t **sets;              /* sets[i][j] 是第 i 组第 j 行 */
static unsigned long clock_tick = 0;
static long hits = 0, misses = 0, evictions = 0;

static void touch(unsigned long addr) {
    unsigned long tag = addr >> (s + b);
    unsigned long idx = (addr >> b) & ((1UL << s) - 1);
    line_t *set = sets[idx];
    int i, victim = 0;

    for (i = 0; i < E; i++)                       /* 1) 查命中 */
        if (set[i].valid && set[i].tag == tag) {
            hits++;
            set[i].stamp = ++clock_tick;          /* 命中也要更新时间戳 */
            return;
        }

    misses++;                                     /* 2) 未命中：找空行 */
    for (i = 0; i < E; i++)
        if (!set[i].valid) { victim = i; goto fill; }

    for (i = 1; i < E; i++)                       /* 3) 无空行：LRU 驱逐 */
        if (set[i].stamp < set[victim].stamp) victim = i;
    evictions++;

fill:
    set[victim].valid = 1;
    set[victim].tag   = tag;
    set[victim].stamp = ++clock_tick;
}

/* 读一行 trace：形如 " M 0020f5,4" 或 "L 7fff...,8"（首字符可能是空格） */
static void replay(char *line) {
    if (line[0] != ' ') return;                   /* 跳过 I（指令）行 */
    char op;
    unsigned long addr; int size;
    sscanf(line + 1, " %c %lx,%d", &op, &addr, &size);
    if (op == 'L' || op == 'S') touch(addr);
    else if (op == 'M') { touch(addr); touch(addr); }   /* M = 一次读 + 一次写 */
}
```

**五个必须注意的点**

1. **`M` 是两次访问**：命中时贡献 2 次 hit；未命中时 1 次 miss + 1 次 hit（第二次必定命中）。
2. **trace 里的 `I`（指令取指）行要跳过**（Part A 的 cache 只模拟数据）。
3. **`getopt` 的参数串是 `"s:E:b:t:"`**，`-v` 是可选的详细模式（对拍时非常有用）。
4. **LRU 只在驱逐时才需要绝对准确**，但**命中必须更新时间戳**（否则时间序就错了）。
5. **不需要真的存数据**：模拟器只关心 tag 与有效位，块内容一个字节都不用。

**验收**：`make && ./test-csim`（27 分满分）；想看细节用 `./csim-ref -v -s 4 -E 1 -b 4 -t traces/yi.trace` 逐行对拍。

#### 7.5.3 Part B：为什么暴力转置是 1183 次 miss

暴力版：

```c
for (i = 0; i < N; i++)
    for (j = 0; j < M; j++)
        B[j][i] = A[i][j];
```

拆开算（32×32，A/B 相邻存放，A 与 B 基址相差 `32*32*4 = 4096` 字节）：

- **A 是顺序访问**：每 8 个 int 装满一个块 → 每 8 次访问 1 次 miss → A 侧 miss ≈ `1024/8 = 128`。
- **B 是按列访问**：`B[j][i]` 固定 `i`、变 `j`，地址步长 `32*4 = 128` 字节 → 组索引 = `(j*4 + i/8) mod 32`，`j` 每加 8 就绕回同一组 → 32 次访问只落在 8 个组上；更要命的是 **4096 是 cache 容量 1024 的整数倍，所以 `A[i][j]` 与 `B[i][j]` 的组索引完全相同**，两边互相驱逐 → B 侧几乎每次都 miss ≈ 1024。
- 合计 ≈ 1150 上下，再加上冲突导致的重复加载 → 实测 **1183**。

**这一算就暴露了三件事**：① 容量不命中（4 KB 数据 vs 1 KB cache）；② **冲突不命中**（直接映射 + 数组基址对齐，让 A、B 争同一批组）；③ 时间局部性几乎为零（读入的块马上被挤掉）。

#### 7.5.4 Part B：32×32 —— 8×8 分块（这是分块思想的模板）

```c
if (M == 32 && N == 32) {
    int i, j, k;
    int a0, a1, a2, a3, a4, a5, a6, a7;      /* 局部变量合计 11 个 <= 12 */
    for (i = 0; i < 32; i += 8)
        for (j = 0; j < 32; j += 8)
            for (k = i; k < i + 8; k++) {
                a0 = A[k][j];   a1 = A[k][j+1]; a2 = A[k][j+2]; a3 = A[k][j+3];
                a4 = A[k][j+4]; a5 = A[k][j+5]; a6 = A[k][j+6]; a7 = A[k][j+7];
                B[j][k]   = a0; B[j+1][k] = a1; B[j+2][k] = a2; B[j+3][k] = a3;
                B[j+4][k] = a4; B[j+5][k] = a5; B[j+6][k] = a6; B[j+7][k] = a7;
            }
}
```

**为什么这样就行**（三层原因）：

1. **工作集变小**：8×8 块 = 8 行 × 1 块（A）+ 8 行 × 1 块（B）= 16 个块，远小于 32 组 → 装得下。
2. **一次读满再用**：`a0..a7` 把 A 的一整行（8 个 int = 恰好一个块）一次读进寄存器，这个块读入后**立刻用完、不再需要**。
3. **B 的写入也是成块的**：`B[j..j+7][k]` 是 B 的一列，虽然不连续，但每次写都会把对应块带进 cache，而同一次 `k` 的 8 次写分属 8 个不同行 → 组索引 `(j+m)*4 + k/8` 各不相同 → 不互相驱逐。

**残留问题：对角线块**。当 `i == j` 时，A 的块与 B 的块会落在同一组上互相驱逐。缓解办法是**对角线元素单独处理**（先存到局部变量，最后再写），这也是官方 hint 提到的。实测这一版 miss 数约在 280–300 之间（**具体以 `./test-trans` 实测为准**，不同编译/基址会有几个百分点的波动），稳过 300 的满分线。

#### 7.5.5 Part B：64×64 —— 为什么 8×8 会失效，以及"两步搬运"

**先推导失效原因**（这段是本章最有价值的部分）：

- 64×64 时一行 = 64 int = 256 字节 = 8 个块；
- 组索引 = `((i*64 + j) * 4 / 32) mod 32 = (i*8 + j/8) mod 32`；
- **`i` 每加 4，组索引加 32 ≡ 0（mod 32）** → `A[i][j]` 与 `A[i+4][j]` **落在同一组**！
- 于是 8×8 分块里 A 的 8 行只用 2 个"组循环"，读第 5 行时第 1 行的块已经被挤掉 → 分块内部自己打架。

**满分思路：8×8 外层 + 内部拆成 4×4 的"两步搬运"**

```
8x8 块 (行 i..i+7, 列 j..j+7) 内部的四个 4x4 子块：

        A 侧                B 侧（转置后）
   +--------+--------+     +--------+--------+
   |  左上  |  右上  |     |  左上  |  左下  |
   +--------+--------+  => +--------+--------+
   |  左下  |  右下  |     |  右上  |  右下  |
   +--------+--------+     +--------+--------+
```

关键点：`B[j+k][i..i+3]` 与 `B[j+k][i+4..i+7]` 是**同一个 32 字节块的两半**（B 的一行里 8 个连续 int）。所以：

**阶段 1**（k = 0..3，扫 A 的上 4 行）：把 A 左上正确写入 B 左上；把 A 右上**先暂存到 B 右上**（因为 B 右上的块刚刚被带上 cache，这次写入几乎免费）。

**阶段 2**（k = 0..3，扫 A 的下 4 行）：把 B 右上里暂存的数据读出、写到它的最终位置 **B 左下**；顺手把 A 左下写入 **B 右上**（覆盖暂存位，恰是它的最终位置）；再把 A 右下写入 **B 右下**。

```c
if (M == 64 && N == 64) {
    int i, j, k;
    int a0, a1, a2, a3, a4, a5, a6, a7;         /* 11 个局部变量 */
    for (i = 0; i < 64; i += 8)
      for (j = 0; j < 64; j += 8) {
        for (k = 0; k < 4; k++) {                /* 阶段 1：A 上 4 行 */
            a0 = A[i+k][j];   a1 = A[i+k][j+1]; a2 = A[i+k][j+2]; a3 = A[i+k][j+3];
            a4 = A[i+k][j+4]; a5 = A[i+k][j+5]; a6 = A[i+k][j+6]; a7 = A[i+k][j+7];
            B[j+k][i]   = a0; B[j+k][i+1] = a1; B[j+k][i+2] = a2; B[j+k][i+3] = a3;
            B[j+k][i+4] = a4; B[j+k][i+5] = a5; B[j+k][i+6] = a6; B[j+k][i+7] = a7;
        }
        for (k = 0; k < 4; k++) {                /* 阶段 2：A 下 4 行 + 回搬 */
            a4 = B[j+k][i+4]; a5 = B[j+k][i+5];  /* 取回暂存的 A 右上 */
            a6 = B[j+k][i+6]; a7 = B[j+k][i+7];
            B[j+4+k][i]   = a4; B[j+4+k][i+1] = a5;   /* -> B 左下（最终位） */
            B[j+4+k][i+2] = a6; B[j+4+k][i+3] = a7;
            a0 = A[i+4+k][j];   a1 = A[i+4+k][j+1];   /* A 左下 */
            a2 = A[i+4+k][j+2]; a3 = A[i+4+k][j+3];
            B[j+k][i+4] = a0; B[j+k][i+5] = a1;       /* -> B 右上（最终位） */
            B[j+k][i+6] = a2; B[j+k][i+7] = a3;
            a4 = A[i+4+k][j+4]; a5 = A[i+4+k][j+5];   /* A 右下 */
            a6 = A[i+4+k][j+6]; a7 = A[i+4+k][j+7];
            B[j+4+k][i+4] = a4; B[j+4+k][i+5] = a5;   /* -> B 右下（最终位） */
            B[j+4+k][i+6] = a6; B[j+4+k][i+7] = a7;
        }
      }
}
```

**这个解法的"设计"含量在哪**：它利用了两件硬件事实 —— ① 一个块装 8 个 int，所以 `B[j+k][i..i+7]` 是一次加载就能写完的；② 直接映射下"错位的暂存"反而比"直接写最终位置"便宜。换句话说：**你在用 cache 的映射规则本身做调度**。实测这一版通常落在 1200–1350（满分线 1300），若差一点，可对**对角线块**再做一次特殊处理。

#### 7.5.6 Part B：61×67 —— 不规则矩阵

```c
else {                                            /* 61x67：16x16 分块足够 */
    int i, j, k, l;
    for (i = 0; i < N; i += 16)
        for (j = 0; j < M; j += 16)
            for (k = i; k < i + 16 && k < N; k++)
                for (l = j; l < j + 16 && l < M; l++)
                    B[l][k] = A[k][l];
}
```

不规则尺寸的好处是**行长度 67 不是 2 的幂**，天然打破了"行与行之间的组索引对齐"；坏处是**边界必须判越界**（`k < N && l < M`）。它的满分线最宽松（< 2000），16×16 分块通常就能过。

#### 7.5.7 规则复查与验收

- 局部变量 ≤ 12（含被调用函数栈上的总和）、**不能 `malloc`**、**不能改 A**、不能用 `long` 绕过、不能改 `"Transpose submission"` 描述串、不能有递归。
- **别去优化运行时间**：评分只看 miss 数，"把乘法提到循环外"这类优化在这里毫无意义。

```bash
make && ./test-csim      # Part A
./test-trans -M 32 -N 32 # 单测某个矩阵
./test-trans -M 64 -N 64
./driver.py              # 总分（Linux 下调用 csim-ref / tracegen）
```

### 7.6 shlab · 逐层设计（Ch8）★核心

#### 7.6.1 三件事，按这个顺序做，能避开 90% 的坑

```
① 先做"前台跑一条命令"        -> eval + parseline + fork/execve + addjob + waitfg
② 再加"异步回收"              -> sigchld_handler（while + waitpid WNOHANG|WUNTRACED）
③ 最后堵"fork 与 addjob 的竞争" -> fork 前 block SIGCHLD，addjob 后解除
```

顺序反了会怎样？先加 handler 再加竞争保护，你会遇到"job 在 addjob 之前就被 deletejob 删掉"的诡异现象 —— 而且它**只在机器忙的时候复现**。

#### 7.6.2 函数清单与骨架

```c
/* ---- eval：核心，5 处信号操作一个都不能少 ---- */
void eval(char *cmdline)
{
    char *argv[MAXARGS], buf[MAXLINE];
    int bg;
    pid_t pid;
    sigset_t mask_all, mask_chld, prev;

    strcpy(buf, cmdline);
    bg = parseline(buf, argv);            /* 返回 1 表示末尾有 & */
    if (argv[0] == NULL) return;          /* 空行 */

    if (!builtin_cmd(argv)) {             /* 内建命令不 fork */
        sigemptyset(&mask_chld);
        sigaddset(&mask_chld, SIGCHLD);
        sigfillset(&mask_all);

        /* ① fork 前阻塞 SIGCHLD：防止子进程先死、handler 先 deletejob */
        sigprocmask(SIG_BLOCK, &mask_chld, &prev);

        if ((pid = fork()) == 0) {
            /* ② 子进程继承了父进程的阻塞掩码，execve 前必须恢复 */
            sigprocmask(SIG_SETMASK, &prev, NULL);
            setpgid(0, 0);                /* ③ 独立进程组：Ctrl-C 才不会打到 shell 自己 */
            if (execve(argv[0], argv, environ) < 0) {
                printf("%s: Command not found\n", argv[0]);
                exit(1);
            }
        }

        /* ④ 父进程：屏蔽所有信号保护 addjob（它要改全局 jobs） */
        sigprocmask(SIG_BLOCK, &mask_all, NULL);
        addjob(jobs, pid, bg ? BG : FG, cmdline);
        sigprocmask(SIG_SETMASK, &prev, NULL);   /* ⑤ 恢复 */

        if (bg)
            printf("[%d] (%d) %s", pid2jid(pid), pid, cmdline);
        else
            waitfg(pid);                  /* 前台：等它结束 */
    }
}
```

```c
/* ---- sigchld_handler：异步回收，必须 while ---- */
void sigchld_handler(int sig)
{
    int olderrno = errno;                 /* handler 里改了 errno 要还原 */
    sigset_t mask_all, prev;
    pid_t pid;
    int status;
    struct job_t *j;

    sigfillset(&mask_all);
    /* 信号不排队：5 个子进程同时死可能只递送一次 -> 必须循环回收 */
    while ((pid = waitpid(-1, &status, WNOHANG | WUNTRACED)) > 0) {
        sigprocmask(SIG_BLOCK, &mask_all, &prev);      /* 保护 jobs 表 */
        if (WIFEXITED(status)) {
            deletejob(jobs, pid);
        } else if (WIFSIGNALED(status)) {
            j = getjobpid(jobs, pid);
            printf("Job [%d] (%d) terminated by signal %d\n",
                   j->jid, pid, WTERMSIG(status));
            deletejob(jobs, pid);
        } else if (WIFSTOPPED(status)) {
            j = getjobpid(jobs, pid);
            j->state = ST;                             /* 停止：不能删，要留在表里 */
            printf("Job [%d] (%d) stopped by signal %d\n",
                   j->jid, pid, WSTOPSIG(status));
        }
        sigprocmask(SIG_SETMASK, &prev, NULL);
    }
    errno = olderrno;
}
```

```c
/* ---- waitfg：不能再用 waitpid 阻塞（会和 handler 抢）---- */
void waitfg(pid_t pid)
{
    sigset_t empty;
    sigemptyset(&empty);
    while (pid == fgpid(jobs))            /* 前台还是它？是就继续等 */
        sigsuspend(&empty);               /* 挂起，等任意信号递送后返回 */
}
```

```c
/* ---- 两个转发型 handler：发给整个前台进程组 ---- */
void sigint_handler(int sig)  { pid_t p = fgpid(jobs); if (p) kill(-p, SIGINT);  }
void sigtstp_handler(int sig) { pid_t p = fgpid(jobs); if (p) kill(-p, SIGTSTP); }
```

```c
/* ---- do_bgfg：fg / bg 内建命令 ---- */
void do_bgfg(char **argv)
{
    struct job_t *j;
    pid_t pid;

    if (argv[1] == NULL) { printf("%s command requires PID or %%jobid argument\n", argv[0]); return; }

    if (argv[1][0] == '%') {                 /* %jid 形式 */
        if ((j = getjobjid(jobs, atoi(argv[1] + 1))) == NULL) { printf("%%%s: No such job\n", argv[1]+1); return; }
    } else if (atoi(argv[1]) > 0) {           /* pid 形式 */
        if ((j = getjobpid(jobs, atoi(argv[1]))) == NULL) { printf("(%s): No such process\n", argv[1]); return; }
    } else { printf("%s: argument must be a PID or %%jobid\n", argv[0]); return; }

    kill(-j->pid, SIGCONT);                   /* 先让它继续跑 */
    if (!strcmp(argv[0], "bg")) {
        j->state = BG;
        printf("[%d] (%d) %s", j->jid, j->pid, j->cmdline);
    } else {
        j->state = FG;
        waitfg(j->pid);                       /* fg 必须等 */
    }
}
```

#### 7.6.3 五个必踩的坑（逐个自查）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| 1 | **信号不排队** | 同时结束多个子进程，只有一部分被回收，`jobs` 里残留僵尸 | handler 里 `while (waitpid(...)) > 0)` |
| 2 | **fork 与 addjob 竞争** | 极偶发：`Job not found`、job 从不出现 | `fork` 前阻塞 SIGCHLD，`addjob` 后解除 |
| 3 | **子进程继承阻塞掩码** | 被 exec 的程序收不到它依赖的信号 | execve 前 `sigprocmask(SIG_SETMASK, &prev, NULL)` |
| 4 | **`kill` 的正负号** | Ctrl-C 只杀掉管道里第一个进程 | 发给进程组用 `-pid`；所以必须 `setpgid(0,0)` |
| 5 | **输出格式** | `sdriver.pl` 逐行对比失败 | 与 `tshref.out` 逐字符对齐（含 `[1] (1234) ...` 的空格与换行） |

**另外两条工程常识**：handler 里改了 `errno` 要还原；访问全局 `jobs` 表时要屏蔽信号（handler 与主程序共享这份数据）。

#### 7.6.4 trace 分组与验收（以实际跑出的对比为准）

```
trace01-05  基础：前台执行 / 内建 quit+jobs / 后台 & 不等待 / 混合
trace06-09  信号转发：SIGINT 与 SIGTSTP 只打前台，不影响后台与 shell
trace10-13  内建 fg / bg：拉回前台、恢复后台、对其再发信号
trace14-16  错误处理与综合：不存在的命令、带 & 的内建、随机混合
```

```bash
make
./sdriver.pl -t trace01.txt -s ./tsh -a "-p"     # 逐条
./sdriver.pl -t trace01.txt -s ./tshref -a "-p"  # 对照参考实现（tshref 是 ELF，需 Linux）
make test01 ... make test16                      # 或按 Makefile 里的目标批量跑
```

#### 7.6.5 408 对应点（这块是 OS 进程管理的活标本）

| tsh 里的现象 | 408 考点 |
|---|---|
| `fork` 返回两次（父得 pid、子得 0） | 进程创建、fork 语义 |
| `execve` 后地址空间被替换、pid 不变 | 程序装入与进程映像替换 |
| 不回收就变僵尸，`waitpid` 阻塞 vs `WNOHANG` | 进程终止与回收、僵尸进程 |
| `setpgid` + `kill(-pid, sig)` | 进程组、信号发送对象 |
| 前台等待 vs 后台并发 | 进程状态与调度 |
| handler 与主程序共享 `jobs` | 内核态/用户态与异步事件 |

### 7.7 malloclab · 逐层设计（Ch9）★核心·最难

> 先说清楚：下面是**教学参考骨架**（CS:APP 3e §9.9 的思路重写，适配 `size_t` 8 字节的 64 位环境），**不是你仓里的代码** —— 本地 `mm.c` 目前还是官方 `mm-naive.c`。写它的目的是让你知道每一块砖该放哪。

#### 7.7.1 块格式：先定死布局，再谈算法

```
高地址
+---------------------------+
| 结尾块 epilogue: size=0,alloc=1  (8 B)
+---------------------------+
|                           |
|   普通块：                |
|   header (8 B): size | a  |   <- size 的低 3 位被挪用作标志位（因为 8 字节对齐）
|   payload ...             |   <- mm_malloc 返回的就是 payload 的首地址
|   footer (8 B): size | a  |   <- 与 header 同内容，为反向合并服务
|                           |
+---------------------------+
| 起始块 prologue: size=16,alloc=1 (header 8 + footer 8，无 payload)
+---------------------------+
低地址（mem_heap_lo()）
```

**三条硬约束**：

1. **8 字节对齐** → `size` 的低 3 位永远是 0，正好拿最低位当 **alloc 标志**。
2. **最小块 32 字节**（64 位）：header 8 + footer 8 + 至少 16（显式链表要放 `pred/succ` 两个 8 字节指针）。
3. **`mem_sbrk` 只能增不能减** → 空间只能靠"复用 + 合并"省出来，不能还给系统。

#### 7.7.2 指针算术必须封进宏（这不是风格问题，是生存问题）

```c
#define WSIZE       8                     /* 字长 / header 大小 */
#define DSIZE       16                    /* 双字：对齐单位 */
#define CHUNKSIZE   (1 << 12)             /* 每次扩堆 4 KB */
#define MIN_BLK     32                    /* header + footer + 两个指针 */
#define MAX(x, y)   ((x) > (y) ? (x) : (y))

#define PACK(size, alloc)   ((size) | (alloc))
#define GET(p)              (*(size_t *)(p))
#define PUT(p, val)         (*(size_t *)(p) = (size_t)(val))
#define GET_SIZE(p)         (GET(p) & ~0x7)
#define GET_ALLOC(p)        (GET(p) & 0x1)

#define HDRP(bp)            ((char *)(bp) - WSIZE)                       /* 块指针 -> header */
#define FTRP(bp)            ((char *)(bp) + GET_SIZE(HDRP(bp)) - DSIZE)  /* 块指针 -> footer */
#define NEXT_BLKP(bp)       ((char *)(bp) + GET_SIZE(((char *)(bp) - WSIZE)))
#define PREV_BLKP(bp)       ((char *)(bp) - GET_SIZE(((char *)(bp) - DSIZE)))

/* 请求字节数 -> 需要的块大小：payload + header，再向上对齐到 16 */
#define ASIZE(size)  (MAX(MIN_BLK, DSIZE * (((size) + WSIZE + DSIZE - 1) / DSIZE)))
```

**为什么必须用 `(char *)` 做加减**：`(char *)bp + 8` 前进 8 字节；若写成 `(size_t *)bp + 1`，指针算术会按 8 字节缩放（虽然这里恰好也是 8，但只要类型一换就全错）。官方 hint 明确说：**把所有指针操作封进宏，别散落在函数里**。

#### 7.7.3 Level 1：隐式空闲链表（目标 Perf ≈ 50–52）

```c
static char *heap_listp;      /* 只允许标量全局变量（规则禁止全局复合结构） */

int mm_init(void)
{
    if ((heap_listp = mem_sbrk(4 * WSIZE)) == (void *)-1) return -1;
    PUT(heap_listp, 0);                                    /* 对齐填充 */
    PUT(heap_listp + (1 * WSIZE), PACK(DSIZE, 1));         /* prologue header */
    PUT(heap_listp + (2 * WSIZE), PACK(DSIZE, 1));         /* prologue footer */
    PUT(heap_listp + (3 * WSIZE), PACK(0, 1));             /* epilogue header */
    heap_listp += (2 * WSIZE);

    if (extend_heap(CHUNKSIZE / WSIZE) == NULL) return -1;  /* 先开一块 */
    return 0;
}

static void *extend_heap(size_t words)
{
    char *bp;
    size_t size = (words % 2) ? (words + 1) * WSIZE : words * WSIZE;   /* 保持双字对齐 */
    if ((long)(bp = mem_sbrk(size)) == -1) return NULL;

    PUT(HDRP(bp), PACK(size, 0));            /* 新的大空闲块 */
    PUT(FTRP(bp), PACK(size, 0));
    PUT(HDRP(NEXT_BLKP(bp)), PACK(0, 1));    /* 新的 epilogue */
    return coalesce(bp);                      /* 与前一块合并 */
}

/* 四情况合并 —— 隐式/显式链表都用这一份 */
static void *coalesce(void *bp)
{
    size_t prev_alloc = GET_ALLOC(FTRP(PREV_BLKP(bp)));   /* 用前块的 footer 判断 */
    size_t next_alloc = GET_ALLOC(HDRP(NEXT_BLKP(bp)));
    size_t size = GET_SIZE(HDRP(bp));

    if (prev_alloc && next_alloc) {                        /* 情况 1：都不空 */
        return bp;
    } else if (prev_alloc && !next_alloc) {                /* 情况 2：后空 */
        size += GET_SIZE(HDRP(NEXT_BLKP(bp)));
        PUT(HDRP(bp), PACK(size, 0));
        PUT(FTRP(bp), PACK(size, 0));
    } else if (!prev_alloc && next_alloc) {                /* 情况 3：前空 */
        size += GET_SIZE(HDRP(PREV_BLKP(bp)));
        PUT(FTRP(bp), PACK(size, 0));
        PUT(HDRP(PREV_BLKP(bp)), PACK(size, 0));
        bp = PREV_BLKP(bp);
    } else {                                               /* 情况 4：都空 */
        size += GET_SIZE(HDRP(PREV_BLKP(bp))) + GET_SIZE(FTRP(NEXT_BLKP(bp)));
        PUT(HDRP(PREV_BLKP(bp)), PACK(size, 0));
        PUT(FTRP(NEXT_BLKP(bp)), PACK(size, 0));
        bp = PREV_BLKP(bp);
    }
    return bp;
}

void *mm_malloc(size_t size)
{
    size_t asize = ASIZE(size);
    size_t extendsize;
    char *bp;

    if (size == 0) return NULL;
    if ((bp = find_fit(asize)) != NULL) { place(bp, asize); return bp; }

    extendsize = MAX(asize, CHUNKSIZE);                    /* 找不到就扩堆 */
    if ((bp = extend_heap(extendsize / WSIZE)) == NULL) return NULL;
    place(bp, asize);
    return bp;
}

void mm_free(void *ptr)
{
    size_t size = GET_SIZE(HDRP(ptr));
    PUT(HDRP(ptr), PACK(size, 0));
    PUT(FTRP(ptr), PACK(size, 0));
    coalesce(ptr);                                         /* 立即合并 */
}
```

**`place` 里的分裂**：空闲块比需要的大出至少 `MIN_BLK` 才分裂，否则整块给出（否则会留下一个连最小块都不如的碎片，永远无法分配）。

```c
static void place(void *bp, size_t asize)
{
    size_t csize = GET_SIZE(HDRP(bp));
    if ((csize - asize) >= MIN_BLK) {
        PUT(HDRP(bp), PACK(asize, 1));
        PUT(FTRP(bp), PACK(asize, 1));
        bp = NEXT_BLKP(bp);
        PUT(HDRP(bp), PACK(csize - asize, 0));
        PUT(FTRP(bp), PACK(csize - asize, 0));
    } else {
        PUT(HDRP(bp), PACK(csize, 1));
        PUT(FTRP(bp), PACK(csize, 1));
    }
}
```

**手算一遍（必须自己算，别跳过）**：`mm_malloc(1)`
- `asize = MAX(32, 16 * ((1 + 8 + 15) / 16)) = MAX(32, 16 * 1) = 32`
- 返回指针 = 块首 + 8（跳过 header）；块共 32 字节：header 8 + payload 16 + footer 8，其中 payload 实际浪费了 15 字节（内部碎片）
- 堆指针前进 32

#### 7.7.4 Level 2：显式空闲链表（目标 Perf ≈ 80+）

**隐式链表的瓶颈**：`find_fit` 要顺着**所有块**（含已分配块）走一遍，代价与总块数成正比。显式链表让空闲块自己串起来 —— 搜索只遍历空闲块。

```
空闲块内部（payload 的前 16 字节被征用）：
+------------------+------------------+------------------+
| header (size|a)  | pred (前驱指针)  | succ (后继指针)  |
+------------------+------------------+------------------+
|  ... 剩余 payload 随便用 ...        | footer (size|a)  |
+------------------------------------+------------------+
```

要点：

- **只有空闲块才有 pred/succ**，分配出去时这两格被 payload 覆盖（所以最小块必须 ≥ 32）。
- 插入用 **LIFO**（插到表头，`O(1)`）；删除要处理"前驱/后继存在与否"四种情况。
- 关键的**不变式**：`A->succ == B ⟺ B->pred == A`（这是 `mm_checkheap` 必查的一条）。

```c
/* 表头插（LIFO），root 是全局指针标量 */
static void insert_free(void *bp) {
    PUT(SUCCP(bp), root);
    PUT(PREDP(bp), NULL);
    if (root != NULL) PUT(PREDP(root), bp);
    root = bp;
}
static void remove_free(void *bp) {
    void *pr = GET(PREDP(bp)), *sc = GET(SUCCP(bp));
    if (pr == NULL) { root = sc; } else { PUT(SUCCP(pr), sc); }
    if (sc != NULL) { PUT(PREDP(sc), pr); }
}
```

**注意**：`place` 分裂时要 `remove_free(bp)` 并把剩余部分 `insert_free`；`mm_free` 合并后要 `remove_free` 掉被吃掉的两个块、再 `insert_free` 合并后的块。**漏一次 remove 就会出现"链表里有个已分配的块"**，症状是几十万次操作后的一次段错误。

#### 7.7.5 Level 3：分离空闲链表（冲高分）

按大小类分桶：`{16-31}, {32-63}, {64-127}, ..., {4096+}`（约 10–14 个桶）。分配时先定位桶再在桶内 first-fit —— **近似 best-fit 的效果，O(1) 的定位代价**。这是工业级分配器（glibc 的 tcmalloc/jemalloc 思路）的雏形。

```
桶数组（用 mem_sbrk 出来的堆内存自己维护，不能是全局数组）：
seg[0] -> 16..31
seg[1] -> 32..63
seg[2] -> 64..127
 ...
seg[k] -> 4096..inf
```
> **规则的坑**：禁止"全局复合数据结构"，所以桶数组不能直接 `static void *seg[14]`（那是全局数组）。做法是桶数组也放在堆里（`mm_init` 时 `mem_sbrk` 一块，或把桶数组伪装进 prologue 区）。

#### 7.7.6 realloc（官方提示：先用 malloc+free 顶上，再独立实现）

```c
void *mm_realloc(void *ptr, size_t size)
{
    if (ptr == NULL) return mm_malloc(size);
    if (size == 0) { mm_free(ptr); return NULL; }

    size_t asize = ASIZE(size);
    size_t csize = GET_SIZE(HDRP(ptr));

    if (asize <= csize) return ptr;                   /* 变小：就地返回（可考虑分裂回空闲表） */

    /* 变大：优先就地吃后一块（若后一块空闲且够大） */
    void *next = NEXT_BLKP(ptr);
    if (!GET_ALLOC(HDRP(next)) && (csize + GET_SIZE(HDRP(next))) >= asize) {
        remove_free(next);
        size_t nsize = csize + GET_SIZE(HDRP(next));
        PUT(HDRP(ptr), PACK(nsize, 1));
        PUT(FTRP(ptr), PACK(nsize, 1));
        /* 若还富余出 MIN_BLK，可以再分裂回去 */
        return ptr;
    }

    void *newp = mm_malloc(size);                     /* 兜底：搬走 */
    if (newp == NULL) return NULL;
    memcpy(newp, ptr, csize - WSIZE);                 /* 注意：搬的是原 payload 大小 */
    mm_free(ptr);
    return newp;
}
```

**两个易错**：① 搬数据时长度要用**原来的** payload 大小（`csize - WSIZE`），不是新的；② 就地扩展后富余部分若 ≥ `MIN_BLK` 应分裂回空闲表，否则利用率会被拖低。

#### 7.7.7 `mm_checkheap`：先写检查器，再写实现（主线四）

```c
int mm_checkheap(int verbose)
{
    char *bp = heap_listp;
    /* 1. prologue：size == DSIZE 且 alloc == 1 */
    /* 2. 逐块遍历到 epilogue：
          - 块地址 8 字节对齐
          - size >= MIN_BLK 且是 16 的倍数
          - header.size == footer.size，header.alloc == footer.alloc
          - 不存在两个相邻的空闲块（漏合并的唯一症状）
          - 块地址落在 [mem_heap_lo(), mem_heap_hi()] 内
    */
    /* 3. 空闲链表（显式/分离）：
          - A->succ == B <=> B->pred == A
          - 所有指针落在堆范围内
          - 遍历堆数出的空闲块个数 == 顺链表数出的个数
          - 每个桶里的块大小确实落在该桶区间内
    */
    /* 4. epilogue：size == 0 且 alloc == 1 */
    return 1;
}
```

**为什么必须早写**：指针算术错一行，症状可能在第 30 万次操作才炸，那时堆已经面目全非。有了检查器，你在 `mm_malloc` 入口调一次 `mm_checkheap(0)`，就能把崩溃定位到"某次操作之后"。

#### 7.7.8 评分与调优路径

```
P = w*U + (1-w)*min(1, T/T_libc),  w = 0.6
总分（3e 口径）= 正确性 20 + 性能 35 + 风格 10
参考水位：隐式+first-fit ≈ 50-52；显式+first-fit ≈ mid-80s
```

| 阶段 | 动作 | 预期 |
|---|---|---|
| 0 | `mm-naive`（brk 递增，不合并） | 利用率接近 0，但能跑通正确性 |
| 1 | 隐式链表 + 四情况合并 + first-fit | ~50 |
| 2 | 显式链表（LIFO 插入、立即合并） | ~80 |
| 3 | 分离链表（10–14 桶） | 85+ |
| 4 | 独立 realloc + 就地扩展 | 再涨几十分位 |

**顺序纪律**：官方 hint 明说 —— **先让前 9 个 trace（只有 malloc/free）正确且够快，再动后 2 个（含 realloc）**。

#### 7.7.9 408 对应点（这块和教材几乎是同一张图）

| malloclab 概念 | 408 OS · 内存管理 |
|---|---|
| first-fit / next-fit / best-fit | **首次适应 / 邻近适应 / 最佳适应 / 最坏适应**（必考） |
| 空闲块合并（四情况） | **紧凑与碎片整理**：合并相邻空闲分区 |
| 内部碎片（对齐导致的浪费） | 内部碎片 |
| 外部碎片（利用率 U < 1） | 外部碎片 |
| 分离空闲链表 | 伙伴系统 /  slabs（了解层面） |
| `mem_sbrk` 只能增 | 连续分配方式下"内存只能从空闲区里切" |

**缺件提醒**：本地 `malloclab/` 没有 `traces/` 也没有 `mdriver` 二进制，需从官方 handout（`csapp.cs.cmu.edu/3e/malloclab-handout.tar`）补齐后才能跑分。

### 7.8 proxylab · 逐层设计（Ch10–12，做 Part I + II）

#### 7.8.1 Part I：顺序代理（40 分，HTTP 报文格式的活标本）

```c
static void doit(int fd)
{
    char buf[MAXLINE], method[MAXLINE], uri[MAXLINE], version[MAXLINE];
    char hostname[MAXLINE], path[MAXLINE], req[MAXLINE];
    int port, serverfd;
    rio_t rio_c, rio_s;
    ssize_t n;

    Rio_readinitb(&rio_c, fd);
    if (!Rio_readlineb(&rio_c, buf, MAXLINE)) return;      /* 空请求：直接断开 */
    sscanf(buf, "%s %s %s", method, uri, version);

    if (strcasecmp(method, "GET")) {                        /* 只处理 GET */
        clienterror(fd, method, "501", "Not implemented",
                    "Proxy does not implement this method");
        return;
    }
    if (parse_uri(uri, hostname, &port, path) < 0) {
        clienterror(fd, uri, "400", "Bad Request", "Invalid URL");
        return;
    }

    /* 小写 open_clientfd：失败返回 -1，不会 exit 掉整个代理 */
    if ((serverfd = open_clientfd(hostname, port)) < 0) {
        clienterror(fd, uri, "502", "Bad Gateway", "Cannot connect to server");
        return;
    }

    /* 组装转发请求：GET 行改成相对路径，并补四个头 */
    sprintf(req, "GET %s HTTP/1.0\r\n", path);
    sprintf(req, "%sHost: %s\r\n", req, hostname);
    sprintf(req, "%s%s", req, user_agent_hdr);              /* 官方给的 UA 常量 */
    sprintf(req, "%sConnection: close\r\n", req);
    sprintf(req, "%sProxy-Connection: close\r\n", req);
    sprintf(req, "%s\r\n", req);                            /* 空行结束头部 */
    Rio_writen(serverfd, req, strlen(req));

    /* 原样转发响应 */
    Rio_readinitb(&rio_s, serverfd);
    char resp[MAXBUF];
    while ((n = Rio_readnb(&rio_s, resp, MAXBUF)) > 0)
        Rio_writen(fd, resp, n);

    Close(serverfd);
}

static int parse_uri(char *uri, char *hostname, int *port, char *path)
{
    char *hoststart, *pathstart, *portstart;
    *port = 80;
    strcpy(path, "/");

    if (strncasecmp(uri, "http://", 7) != 0) return -1;     /* 形态①：必须是绝对 URL */
    hoststart = uri + 7;

    pathstart = strchr(hoststart, '/');                     /* 形态②：有无路径部分 */
    if (pathstart == NULL) { strcpy(hostname, hoststart); return 0; }
    *pathstart = '\0';
    strcpy(hostname, hoststart);
    *pathstart = '/';
    strcpy(path, pathstart);

    portstart = strchr(hostname, ':');                      /* 形态③：显式端口 */
    if (portstart) { *portstart = '\0'; *port = atoi(portstart + 1); }
    return 0;
}
```

**四个必须补的头**（缺一个就可能被真实服务器拒绝或返回错误内容）：`Host`、`User-Agent`、`Connection: close`、`Proxy-Connection: close`。

**为什么 `GET http://host/path HTTP/1.1` 要改写成 `GET /path HTTP/1.0`**：代理面向的是服务器，服务器只见"路径"；`Host` 头承载主机名。HTTP/1.0 + `Connection: close` 让"连接关闭"= "响应结束"，省掉解析 `Content-Length` 的麻烦 —— **这是本 lab 简化协议的关键设计决策**。

#### 7.8.2 Part II：并发（15 分）

```c
int main(int argc, char **argv)
{
    int listenfd, *connfdp;
    socklen_t clientlen;
    struct sockaddr_storage clientaddr;
    pthread_t tid;

    if (argc != 2) { fprintf(stderr, "usage: %s <port>\n", argv[0]); exit(1); }
    Signal(SIGPIPE, SIG_IGN);                 /* 关键：客户端断开后再写会被 SIGPIPE 杀死 */
    listenfd = Open_listenfd(argv[1]);

    while (1) {
        clientlen = sizeof(clientaddr);
        connfdp = Malloc(sizeof(int));        /* 每个连接一份拷贝，避免下面的经典 bug */
        *connfdp = Accept(listenfd, (SA *)&clientaddr, &clientlen);
        Pthread_create(&tid, NULL, thread, connfdp);
    }
}

static void *thread(void *vargp)
{
    int connfd = *((int *)vargp);
    Free(vargp);
    Pthread_detach(Pthread_self());           /* detach：线程结束自动回收资源 */
    doit(connfd);
    Close(connfd);
    return NULL;
}
```

**并发的三个要点**

1. **`connfd` 不能直接传地址**。若写 `Pthread_create(&tid, NULL, thread, &connfd)`，主循环马上会 `Accept` 覆盖 `connfd`，线程读到的可能是下一个连接的 fd —— 这是本 lab 最著名的 bug。解法：传值（`(void *)(intptr_t)connfd`）或每次 `Malloc` 一份（上面用的是后者）。
2. **线程必须 detach**（或 join），否则每来一个连接泄漏一份线程资源，长跑必挂。
3. **`open_clientfd` / `open_listenfd` 是线程安全的**（基于 `getaddrinfo`），可以直接在多线程里用；但 **`csapp.c` 里的大写封装（`Open_clientfd` 等）会在出错时 `exit` 掉整个进程** —— 代理是长跑进程，必须自己检查返回值并只关闭当前连接。

#### 7.8.3 Part III 为什么不值得做（以及与 cachelab 的关系）

Part III = 缓存（1 MiB 上限、100 KiB 单对象上限）+ 近似 LRU + **读者-写者锁**（官方明确禁止"一把大锁"，要求多读者并发）。

- **408 视角**：它的考点（Web 缓存、代理服务器、命中/未命中）在应用层**以概念形式**考，不需要你实现；而"读者-写者"在 OS 同步章节是标准模型，用 PV 操作那套就够了。
- **项目视角**：LRU + 缓存大小管理，和 cachelab 的 LRU 替换是**同一件事**（cachelab 里你已经写过一遍时间戳 LRU）。重复投入，收益递减。

**所以**：把时间省下来给 malloclab 和 shlab。

#### 7.8.4 验收与调试

```bash
make
./free-port.sh                      # 取一个空闲端口
./proxy <port> &                    # 起代理
telnet localhost <port>             # 手敲请求：
#   GET http://www.example.com/ HTTP/1.0
#   （空行结束）
curl -v -x http://localhost:<port> http://www.example.com/    # 用 curl 走代理
./driver.sh                         # 官方评分（Linux 下，依赖 tiny 二进制）
```

**环境提醒**：`proxylab/tiny` 是 ELF 二进制 → `driver.sh` 只能在 Linux 上跑。

### 7.9 冲刺期怎么排这张表（60 天，项目线不占教材主线）

> 假设每周能给项目线 8–10 小时（教材主线之外的余量）。**任何一关卡住超过预算 1.5 倍，就跳到下一个** —— 卡住的地方回头再看往往一眼就通。

| 周次 | 内容 | 预算 | 完成标志 |
|---|---|---|---|
| 第 1 周 | **datalab** 13 题 + cachelab **Part A** | 6–8 h | `./btest` 全绿；`./test-csim` 满分 |
| 第 2 周 | cachelab **Part B**（32→64→61 三关） | 4–6 h | `./driver.py` 三个矩阵都过满分线 |
| 第 3–4 周 | **malloclab** Level 1 → Level 2（显式链表） | 10–15 h | 前 9 个 trace 正确 + Perf index ≥ 75 |
| 第 5 周 | **shlab** 16 个 trace | 6–8 h | `sdriver.pl` 全 16 条与 `tshref.out` 对齐 |
| 第 6 周（可选） | archlab **A+B** 或 proxylab **Part I** | 5–8 h | `yis` 出 0xcba；或 telnet 打通代理 |
| 机动 | bomb 复习清单 + attack 原理 | 3–4 h | 见 §7.2 / §7.3 的验收要求 |

**优先级铁律**：`malloclab` 与 `shlab` 是 OS 的两块硬骨头，优先级高于 archlab/proxylab；`archlab Part C` 与 `proxylab Part III` 永远排最后，时间不够就直接砍。

## 8 出口视角：考研复试与找工作（先存着，初试后再用）

> **时间纪律（重要）**：初试在 12 月下旬，现在（10 月下旬）的每一小时都应该给 Tier 1 的四个 lab 和教材主线。**这一节是弹药库，不是待办** —— 初试结束当晚再来翻。写在这里是因为复试（次年 3–4 月）与春招/实习面试时间相邻，而它们需要的弹药是同一批。

### 8.1 考研复试视角

**机试**：多数院校考 C 语言 + 数据结构（链表/树/排序为主）。datalab 的位运算训练与 shlab 的指针操作正好是 C 功底；malloclab 做过的人写链表题几乎不会犯指针错误。

**面试高频问题 → 你的弹药对应表**（这些是计算机考研复试的真实高频题）：

| 复试面试官问 | 你的弹药 | 出处 |
|---|---|---|
| "讲讲虚拟内存 / 为什么每个进程有独立地址空间" | malloclab 的堆 + `mem_sbrk`；结合 jos 的页表 | §7.7 + jos 线 |
| "进程和线程的区别？切换成本差在哪？" | shlab 的 fork/进程组 + 教材线程章 | §7.6 |
| "malloc 是怎么实现的？free 之后内存去哪了？" | 隐式→显式→分离链表三级演进，能讲出 footer 的用途与四情况合并 | §7.7 |
| "Cache 是什么？为什么有的程序快有的慢？" | s/E/b 换算 + 分块推导 + 冲突不命中 | §7.5 |
| "TCP 怎么做到可靠？" | 已归档的整套传输层讲义 + CS144 | `16-传输层.ipynb` |
| "缓冲区溢出是怎么回事？" | 栈帧图 + 三级防御 | §7.3 |

**项目介绍的讲法模板**（复试里"介绍一个你做过的项目"的标准结构）：

```
做了什么（1 句）→ 难在哪（1 句，说权衡不说苦劳）→
怎么解决的（2-3 句，讲设计选择）→ 量化结果（1 句）
```

例：「我完整实现了 CS:APP 的全部核心 lab。malloc 实验里我在隐式空闲链表和显式链表之间做了取舍——隐式实现简单但搜索是 O(n)，显式把搜索范围缩到空闲块但要多维护一对指针和一条不变量；最终显式链表版本把性能指数从 50 提到 85 左右。做完这套实验，我对'空间换时间还是时间换空间'有了肌肉记忆。」

**复试讲项目的最大误区**：炫难度（"我做了一个很复杂的 lab"）。老师想听的是**设计权衡与取舍**——你能不能说清"为什么这样做、不那样做会怎样"。这正是 §3 七条主线的用法：每条主线都是一个现成的"权衡叙事"。

### 8.2 找工作 / 实习面试视角

CS:APP 是 C/C++ 后端、系统、嵌入式、基础架构、游戏引擎岗的面试圣经。高频题映射：

| 面试题（真实出现频率从高到低） | 你的弹药 | 出处 |
|---|---|---|
| "手写一个简易 malloc / 讲讲内存分配原理" | malloclab 全套（大厂 C/C++ 面试经典） | §7.7 |
| "cache line 多大？数组为什么比链表快？什么是伪共享（false sharing）？" | cachelab 的 B=32 字节直觉；伪共享是主线二的延伸（两个线程各写同一条 cache line 的不同字节，互相驱逐） | §7.5 |
| "进程 vs 线程 vs 协程？上下文切换成本？" | shlab + Ch8 | §7.6 |
| "大小端怎么判断？struct 为什么要对齐？sizeof 怎么算？" | datalab 的位级直觉 + bomblab 读表经验 | §7.1 / §7.2 |
| "讲讲 epoll / Reactor / 惊群" | proxylab 是入门，**但注意**：CSAPP 3e 没讲 epoll，这是需要另行补的延伸点 | §7.8 + 标注 |
| "TCP 三次握手为什么不是两次？" | 已归档的传输层讲义 | `16-传输层.ipynb` |

**简历的量化写法**（把 lab 写成项目经历的标准姿势）：

```
- 实现显式空闲链表内存分配器（CS:APP Malloc Lab），
  支持立即合并与边界标记，性能指数 85+/100（空间利用率 90%+）
- 实现 LRU Cache 模拟器与矩阵转置分块优化（CS:APP Cache Lab），
  64×64 矩阵 miss 数从 1183 降至 <1300（满分线内）
- 实现带作业控制的并发 shell（CS:APP Shell Lab），
  正确处理 SIGCHLD 异步回收与 fork/addjob 竞争，16/16 trace 全过
```

**诚实标注**：`volatile` / 内存模型 / `std::atomic` / epoll / 零拷贝 这些超出 CSAPP 范围，是面试下一层的弹药，**初试与 Tier 1 完成之前都不要碰**。

### 8.3 三个能讲五分钟的小故事（复试与面试通用）

> 这三个故事的共同点：**起点是一个反直觉的现象，终点是一条设计原则**。这是讲技术最好的结构。

**故事一：为什么 8×8 分块在 64×64 上失效（30 秒版）**
"矩阵转置在 1 KB 直接映射 cache 上，32×32 用 8×8 分块能把 miss 从 1183 压到 300 以下；但同一个方法到 64×64 就失灵——因为行间距变成 cache 容量的整数倍，分块内第 5 行会精确地驱逐第 1 行。容量明明够，miss 却照发生，这就是冲突不命中：**硬件的便宜（直接映射只要一个比较器）是用冲突换的**。解法是两步搬运，用 cache 的映射规则本身做调度。"

**故事二：fork 与 addjob 的竞争（30 秒版）**
"子进程可能在父进程把 job 加进表**之前**就退出并触发信号处理器去删它——删一个还不存在的条目。这个 bug 只在机器忙的时候复现，概率性地消失又出现。修法是在 fork 前阻塞那个信号。教训：**异步世界里，'先做 A 再做 B'的顺序保证必须显式构造，它不是免费的**。"

**故事三：IEEE 754 的平滑衔接（30 秒版）**
"规格化数的阶码减一个偏置，非规格化数却减'偏置减一'——多出来的这个 1 不是失误：它让最大非规格化数和最小规格化数恰好差一个最小步长，中间不留缝。浮点运算的逐级下溢靠这一条成立。**好的编码设计会为了边界的连续性付出一个看似任意的常数**，这是我做过 datalab 之后才真正看懂的一件事。"

## 9 一句话收尾

> CSAPP 这八个 lab，对 408 的价值**不在代码，而在它把"补码 / Cache / 分配算法 / 进程回收"这些考点变成了你亲手调过的东西**。
> 冲刺期只做 Tier 1 四个（datalab / cachelab / malloclab / shlab），你就把组成的数据表示、存储的 Cache、OS 的内存与进程四块最难的选择/大题直觉全立起来了。
> 而同一批 lab，在初试之后会自动变成你的复试弹药与面试故事（§8）——**一次投入，三个战场：初试、复试、春招**。
