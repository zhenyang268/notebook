# CS149 · 并行计算

> **工程线（兴趣向，非考试范围）**。本文件不承担复习任务。
> CMU CS149：并行算法、work-span 模型、GPU 与多核性能分析。
>
> **单向引用约定**：本文提到考点时**只写 KP 号与考点名**，不复制 `exam/` 的正文；
> `exam/` 的文件里也不出现本文件的工程名。两边互不依赖，只共享主键。

## 对位考点（单向引用）

| 本文段落 | 对应 KP |
|---|---|
| 多核与共享内存模型 | `408-CO-0507` 多处理器基本概念 |
| Cache 一致性与 false sharing | `408-CO-0305` Cache |
| 线程池与锁 | `408-OS-0203` 同步与互斥 |
| 任务调度与负载均衡 | `408-OS-0202` CPU 调度 |
| 并行 BFS / 图处理 | `408-DS-0503` 图的遍历 |

---

## 0 怎么读这个文件

- §1 给出**课程定位与本地代码现状**（先看清手里到底有什么，别对着空气复习）。
- §2 是**全局地图 + 关键路径**，回答"5 个 PA 分别落在硬件栈的哪一层、按什么顺序过"。
- §3 是**贯穿全课程的设计理念**——**这是整个项目最值钱的部分，别跳过**。CS149 的作业会换硬件、换语言（ISPC / CUDA / NKI），但理念是同一套。
- §4 每个 PA 一个模板：**抓重点 → 关键路径 → 细节与易错点 → 设计理念**，是**大纲级**（每层 4 条以内）。
- §6–§11 是**逐层展开**：真实函数签名、数据流、伪代码、逐条易错点。读到具体动手那一节时再回来翻。
- §12 是**课程讲座层**：补全 18 讲主线，重点展开 PA 没考的 coherence、内存一致性、lock-free（与 408 的存储层次/同步互斥直接相通）。
- §13 是**自测验收清单**；§14 是**求职视角**（岗位地图、面试真题对照、简历写法、补课路线）——要拿这门课找工作就直接从 §14 开始倒推。

---

## 1 定位与现状

### 1.1 一句话

> **CS149 教的不是"怎么写并行程序"，而是"怎么判断一个并行程序在这个硬件上跑得好不好，以及为什么"。**

课程开篇就立了三条 theme：怎么设计能 scale 的并行程序、并行硬件是怎么实现的、怎么思考效率。第三条里有一句必须记住的话：

> **FAST != EFFICIENT**

在 10 个核上拿到 2 倍加速，程序确实变快了，但硬件用得好不好是另一回事。整个学期的作业都在反复考这个区分。

### 1.2 硬件阶梯：5 个 PA 就是 5 个落点

```
  多核 CPU（4-16 核 + SIMD）      PA1 性能分析 / PA2 任务调度
        |                          ISPC, std::thread, pthread
        v
  GPU（CUDA, 数据并行）            PA3 Circle Renderer
        |                          block / warp / shared memory
        v
  AI 加速器（Trainium2 / NKI）     PA4 Fused Conv+MaxPool
        |                          SBUF / PSUM，软件管理的片上存储
        v
  开放性能工程（H100 + leaderboard） PA5 Fast Kernels
                                   FlashAttention / SwiGLU / ...
```

注意这条线不是"难度递增"，而是**"谁来决定数据放在哪"这件事的控制权，一步步从硬件手里交到程序员手里**：CPU 的 cache 是硬件管的；GPU 的 shared memory 要你显式声明；Trainium 的 SBUF/PSUM 每一次搬运都要你写 DMA。

### 1.3 本地代码现状（事实，2026-10-22 实测）

先说清楚，免得复习时找错地方：

| 目录/文件 | 状态 |
|---|---|
| `asst2-master/` | **已解压**，但 `part_a/tasksys.cpp` 与 `part_b/tasksys.cpp` 都是**原始骨架**（`run()` 里是串行 for 循环，Part B 的 `runAsyncWithDeps()` 直接 `return 0`）。只有 `TaskSystemSerial` 是完整的 |
| `asst1-master/` | 目录存在但**内容为空**（只剩 `.DS_Store`）。源码仍在 `asst1-master.zip` 里 |
| `asst3-master.zip` / `asst4-trainium2-main.zip` / `asst5-kernels-main.zip` | 未解压 |
| `biggraphs-ec-main.zip` | 未解压（OpenMP BFS，旧版 PA5 / 加分项） |
| `intro_to_cuda-main.zip` / `cuda_tutorial-main.zip` | 未解压（PA3 的前置小样） |
| git | 仅 2 个提交：`init`（空）、`init asst2`。**没有任何学生实现被提交过** |

结论：**手头是完整的官方 handout，没有自己的历史实现。** 所以这份笔记的定位是"项目指导 + 复习提纲"，不是"你写过的代码的复盘"。要看 handout 原文：

```bash
cd ~/develop/learning/learning-408/parallel-cs149
unzip -q asst3-master.zip -d .        # 其余同理；asst1 解压到别处，别覆盖现有空目录
```

### 1.4 这门课的隐形门槛

官方 course info 把 CS111（同步原语）列为强列建议的先修，并明说：**学生卡住的最主要原因是缺乏调试经验**。作业会碰到 ISPC、CUDA、NKI 三种新语言，课程假设你边做边学。复习时如果卡住，先问"这是我的并行设计错了，还是我还没掌握这门语言的语法"。

---

## 2 全局地图与关键路径

### 2.1 五个 PA 一张表

| PA | 主题 | 硬件/语言 | 分值骨架 | 对应 lecture | 核心考点 |
|---|---|---|---|---|---|
| PA1 | 在四核 CPU 上做性能分析 | std::thread + ISPC + CS149 fake SIMD | 6 个 program：20/20/20/15/10/15 | L1–L3（并行形式、ISPC 抽象） | 负载不均、SIMD divergence、算术强度 |
| PA2 | 从零写任务执行库 | C++ thread pool | A 50 + B 40 + writeup 10 | L5–L6（工作分配与调度） | 三种调度实现的开销对比、DAG 依赖 |
| PA3 | CUDA 圆形渲染器 | CUDA | 5 + 10 + 72(实现) + 13(writeup) | L7–L8（GPU 架构、数据并行） | order + atomicity 两条不变式、scan、shared memory |
| PA4 | Fused Conv+MaxPool | NKI (Python) on Trainium2 | 30 + 70 | L9–L11（DNN 推理、硬件专用化） | 软件管理存储、tiling、loop fusion |
| PA5 | 写一个最快的 kernel | CUDA / Triton / TileLang on H100 | 80–110（按 work log 评分） | L13（DSL 与 AI 驱动优化） | 无参考实现时的开放性能工程 |
| biggraphs | OpenMP BFS（加分） | OpenMP | 70 + 14，可给前面任一 PA 加 `(x/84)*10` 分 | L4–L6 | top-down / bottom-up / hybrid、CAS |

### 2.2 关键路径：复习顺序

推荐顺序 **PA1 → PA2 → PA3 → PA4 → PA5**，理由不是难度，而是**概念依赖**：

1. **PA1 先建立"负载不均 / divergence / 带宽受限"三个直觉。** 这三个词会出现在后面每一个 PA 里。PA1 的 6 个 program 每一个都是一次"为什么加速比不到 8 倍"的诊断练习。
2. **PA2 把 PA1 的直觉变成代码。** PA1 里你只是观察 ISPC 的 `launch` 怎么分任务；PA2 要你自己写那个分发器。Part A 的灵魂问题是"为什么最简单的实现反而更快"。
3. **PA3 换硬件。** 同一个"分任务"问题，在 GPU 上变成了 thread block / warp / shared memory。PA2 的 scan 在这里以 shared-memory prefix-sum 的形式再出现一次。
4. **PA4 把"数据放哪"的控制权交给你。** PA3 的 shared memory 还是"缓存"语义；PA4 的 SBUF/PSUM 是你自己 DMA 的。到这里 locality / blocking / fusion 三个优化才是硬要求，不是加分项。
5. **PA5 是毕业考**：没有参考实现，自己定优化顺序，写 work log。

`biggraphs` 是可选的支线，适合在 PA2 之后当"并行算法 + 同步原语"的练习（CAS、frontier 切换），与主线正交。

### 2.3 一条贯穿所有 PA 的方法论

课程在 PA5 里把它写成了明确的四步循环，其实每个 PA 都在用：

```
1. run      跑当前版本
2. measure  测时间 + 从 profiler 拿统计（吞吐/带宽占用/命中率/MFU）
3. hypothesize  结合对代码的了解（依赖在哪、访存在哪）+ 数据，猜瓶颈是什么
4. change   改一版验证假设，看是不是真的快了
```

四个可能的优化方向（PA5 handout 原话）：**增加并行度 / 减少通信 / 隐藏延迟 / 缓解竞争**。任何一次"我把它改快了"都要能归到这四类之一，否则你只是碰运气。

---

## 3 设计理念（最值钱的一节）

### 3.1 抽象 vs 实现：这门课的复调主题

L3 的标题里直接写着 "ISPC programming, abstraction vs. implementation"。同一件事在三个 PA 里出现三次：

| 层 | 抽象（你写的） | 实现（硬件真的做的） | 陷阱 |
|---|---|---|---|
| ISPC | `foreach (i = 0 ... N)`，只声明"这些迭代独立" | 编译器把迭代切成 gang，映射到 8-wide AVX2 | 你以为在写循环，其实在写 SIMD lane；分支 divergence 直接吃利用率 |
| ISPC | `launch[N]` 起 N 个 task | 运行时把 task 分到多核 | task 数是**实现决策**，不是语义的一部分 |
| CUDA | block / thread 两级抽象 | warp（32 线程 SIMT）+ SM 调度 | 按 thread 思考会写出 divergence 严重的分支；按 warp 思考才对 |
| NKI | tile 上的矩阵运算 | Tensor Engine 的物理 tile 约束 `(128,128) x (128,512)` | 抽象的 tile 大小必须落到硬件约束上，否则编译不过 |

一句话：**抽象给你表达能力，实现决定你的性能。** 每次用一个新的抽象，先问"它下面是什么"。

### 3.2 声明式 vs 命令式

PA1 里有个被 handout 特意强调的对比：

- `sum`（命令式）：手写 `c[programIndex + i] = ...`，你自己在做"把工作映射到执行单元"。
- `sum2`（声明式）：`foreach (i = 0 ... N) { c[i] = a[i] + b[i]; }`，你只声明"有哪些工作"，映射交给系统。

区别很微妙但很重要：声明式给实现留了重排的自由。这也是 `foreach` 和 `launch` 要分成两个机制的原因——前者管"一个核内的 SIMD 并行"，后者管"跨核的任务并行"，两者在实现上是不同的决策，混在一个抽象里就没法分别调优。

### 3.3 三个性能敌人：不均、divergence、带宽

PA1 的 6 个 program 其实是这三件事的标本：

- **负载不均**（mandelbrot threads）：view 1 的上下半图代价差别大，静态按行切块 → 3 线程那个点特别难看。解法是交织（cyclic）静态分配，不需要任何同步。
- **divergence**（mandelbrot ISPC / sqrt）：同一个 gang 里不同 lane 的迭代次数不同，SIMD 必须按最慢的那个 lane 走完。sqrt 的牛顿迭代收敛速度依赖初值，输入分布直接决定加速比——所以 handout 让你"构造一个让加速比最大的输入"和"构造一个让加速比最小的输入"。
- **带宽受限**（saxpy）：2 次浮点运算对 12 字节访存，算术强度极低。多核/多任务都救不了它，这是硬件上限，不是实现问题。

**判断"瓶颈是算力还是带宽"是 CS149 的第一基本功。** 后面 PA3 的 NCU 报告、PA4 的 MFU、PA5 的 DRAM throughput 都在问同一个问题。

### 3.4 存储层次的控制权

这是 CPU → GPU → 加速器这条线最深的一条线索：

| 机器 | 片上存储 | 谁决定放什么 |
|---|---|---|
| 多核 CPU | L1/L2 cache | **硬件**（对软件正确性不可见） |
| GPU | shared memory（每 block 显式声明）+ L1 | **程序员**声明，硬件仍管全局内存 |
| Trainium2 | SBUF（28 MiB）+ PSUM（2 MiB） | **程序员**用 DMA 显式搬；不搬就用不了 |

PA4 的 handout 把这件事说得很直白：传统 cache 下"从软件正确性的角度看，cache 不存在"；而 NeuronCore 的存储是 **software managed**，最大的挑战就是**编排数据怎么流过这台机器**。

推论：**loop blocking 和 loop fusion 在 CPU 上是优化技巧，在加速器上是能不能跑的问题。** PA4 的 conv+pool 融合，本质上是"卷积的结果别写回 HBM，直接在片上做 maxpool"。

### 3.5 开销意识：什么时候"更简单"更快

PA2 Part A 故意让你实现三个版本，然后用 wireup 逼你回答：为什么串行版和"每次 run 都建线程"的版在某些测试上不比线程池慢？

答案是**开销的量级**：
- 任务极便宜（`super_super_light`）→ 线程创建/同步的开销可能大于并行收益，甚至串行的 cache 局部性更好。
- 任务贵且数量多 → 摊销后线程池赢。
- spin vs sleep → spin 延迟低但白占执行资源（在核数等于线程数时会拖慢 worker）；sleep 省资源但有唤醒开销。

**没有"最好的调度器"，只有"对这个负载特征最合适的调度器"。** 这就是真实系统（TBB、Spark、PyTorch）要内置多种策略的原因。

### 3.6 正确性的两条不变式：原子性与顺序

PA3 把这个区分讲得最清楚，而且它适用于所有并行系统：

- **原子性**：读-改-写这个整体不能被打断。
- **顺序**：对**同一个**位置的更新必须按输入顺序发生。

关键洞察（handout 原话加粗）：**顺序只约束同一个像素。** 不重叠的圆之间没有任何顺序要求，可以随便并行。这句话是整个 PA3 的优化空间来源——你的性能上限取决于能不能把"有依赖的部分"圈得足够小。

还有一个次序建议值得记住：**先解决顺序，再看原子性还要不要紧。** 很多时候顺序一旦被保证（比如同一像素只由一个线程按序处理），原子性问题自然消失了。这是个通用思路：靠**消除共享**来保证正确性，比靠加锁便宜得多。

---

## 4 各 PA 大纲（抓重点 / 关键路径 / 易错点 / 设计理念）

> 本节是**大纲层**。每个 PA 的逐层展开（真实函数签名、数据流、伪代码、逐条易错点）见 §6–§11。

### 4.1 PA1 · 在四核 CPU 上做性能分析

**抓重点**
1. 六个 program 是六种"加速比为什么不理想"的诊断：负载不均（mandelbrot threads）、SIMD 利用率（vecintrin / mandelbrot ISPC）、收敛速度差异（sqrt）、带宽上限（saxpy）、找热点（kmeans）。
2. **ISPC 的 `foreach` 与 `launch` 是两个不同层次的并行**（核内 SIMD / 跨核任务），两者叠起来才有 32x+。
3. 目标数字：mandelbrot ISPC + tasks 要超过串行 **32 倍**；kmeans 要 **2.1x**；prog1 八线程要 **7-8x**。

**关键路径**
- `prog1`（std::thread，静态切块 → 改成交织分配，禁止用同步）→ `prog2`（CS149 fake SIMD intrinsics，练 mask 与尾部处理）→ `prog3`（ISPC，先 `foreach` 后 `launch`，调 task 数）→ `prog4`（sqrt，构造最大/最小加速比的输入）→ `prog5`（saxpy，解释为什么不能线性加速）→ `prog6`（kmeans，插 timer 找热点，只允许改 `kmeansThread.cpp`、只允许并行化一个函数）。

**细节与易错点**
- `prog1`：**不许用任何同步**，必须靠静态分配解决不均（交织/按行取模）。
- `prog1`：`-n 16` 在 8 执行上下文的机器上不会更快——超订（oversubscription）不产生新算力。
- `prog2`：数组长度不是 `VECTOR_WIDTH` 倍数时的尾部处理（`_cs149_init_ones` 造部分掩码）；用 `./myexp -s 3` 测小输入。
- `prog4`：构造"最坏输入"的思路是让同一 gang 内 lane 的迭代次数差最大；构造"最好输入"是让所有 lane 一起结束。
- `prog6`：约束极严——只改 `kmeansThread.cpp`，不许改 `stoppingConditionMet`、不许改 `kMeansThread` 接口、不许改 `dist` 语义、**只能并行化 dist / computeAssignments / computeCentroids / computeCost 中的一个**。热点在 `dist`（K 个质心 × M 个点的 100 维距离）。
- `prog6` 的验收不是看数字而是看 `plot.py` 出的两张图是否和骨架一致（PCA 投影后"点不都归属最近质心"是正常的）。

**设计理念**
- SIMD 的成本模型：**一个 gang 的耗时 = 最慢 lane 的耗时**。所以"输入分布"是性能问题的一部分，不只是数据问题。
- 算术强度决定天花板：saxpy 每 3 个元素 2 次运算、saxpy 的 `TOTAL_BYTES = 4 * N * sizeof(float)`（乘 4 是因为写回要读整条 cache line）——这些数字要能自己算出来。
- 抽象的价值：`foreach` 让你不用手写 lane 划分，但代价是你得按"所有 lane 一起走"的方式思考。

---

### 4.2 PA2 · 从零写任务执行库

**抓重点**
1. `run(runnable, num_total_tasks)` 是**同步 bulk launch**：返回时全部任务必须已完成。
2. Part A 三种实现是一条演进链：**Spawn（每次建线程）→ Thread Pool + Spin → Thread Pool + Sleep**。每一步都必须是可正确运行的完整系统。
3. Part B 加异步 + DAG：`runAsyncWithDeps()` 返回 TaskID，`sync()` 等所有先前 launch 完成；依赖是 **launch 粒度**（A 的全部任务做完，才能开始 B 的任一任务）。

**关键路径**
1. 先读懂 `itasksys.h`：`IRunnable::runTask(task_id, num_total_tasks)` 是任务的入口，你的系统只负责"谁在什么时刻调用它"。
2. `TaskSystemParallelSpawn`：`run()` 里起线程 → 动态抢任务（共享计数器 + 锁/原子）→ join 全部 → 返回。
3. `...ThreadPoolSpinning`：构造时（或首次 run 时）建好池；worker 循环取任务；`run()` 需要判定"这批全部做完"（不能只看队列空——队列空但任务正在执行）。
4. `...ThreadPoolSleeping`：worker 无活时条件变量睡；**调用 `run()` 的主线程也要睡**，否则它会占着一个核空转，抢 worker 的资源。
5. Part B：两个结构——**等待队列**（依赖未满足的 launch）+ **就绪队列**（可立即执行的）；每个 launch 记录剩余任务数，归零时把它依赖者的入度减一，入度归零就推到就绪队列。

**细节与易错点**
- `num_threads` 是**上限**，不是必须值：任务数少于线程数时别傻乎乎地全叫醒。
- 条件变量必须配 `while` 循环等条件（虚假唤醒 + 条件可能被别的线程抢先满足）。
- "全部完成"的判定：用"已完成计数 == num_total_tasks"再唤醒主线程，**不要用"队列为空"**（竞态的经典来源）。
- `run()` 与 `runAsyncWithDeps()` 的语义差别：前者同步、后者立即返回；`run()` 可以用 `runAsyncWithDeps(..., 空 deps)` + `sync()` 实现（handout 明确允许）。
- `sync()` 要等**所有**先前的 launch（不只是最近一个）。
- 依赖是 launch 级：launchA 的 128 个任务**全部**结束，launchB 的 2 个任务才能开始；但 B 和 C 之间可以并行。
- TaskID 必须唯一（不需要考虑 int 溢出，2^31 次 launch 不会到）。
- grading 会用**没提供给你**的 workload 测正确性，所以别只对测试集调参。
- Part B 只需要实现 `TaskSystemParallelThreadPoolSleeping` 一个类。

**设计理念**
- **"为什么简单版更快"**（writeup 必答题）：开销 vs 收益的权衡，答案要能点名具体测试（如 `super_super_light` 任务极便宜、`super_light` 反而要求并行）。
- **spin vs sleep**：spin 换延迟、sleep 换资源利用率；线程数 == 核数时 spin 的代价最大。
- 静态 vs 动态分配：任务代价不均时必须动态（原子计数器），代价均匀时静态更省同步。
- **这就是 TBB / Spark / PyTorch 调度器的同一个问题**：DAG 依赖 + 批量任务 + 线程池。PA2 做完再看这些框架，看到的是实现而不是魔法。

---

### 4.3 PA3 · CUDA 圆形渲染器

**抓重点**
1. 正确性有两条不变式：**原子性** + **顺序（同一像素按 circle 输入顺序）**。不满足两条最多 12/85 分。
2. **顺序只约束同一像素** → 不重叠的圆完全自由，这是所有并行度的来源。
3. 两个并行轴：**parallelism across pixels** 和 **parallelism across circles**，好方案要在不同阶段分别用它们。
4. Part 1 saxpy（5 分）是热身，Part 2 是 scan / find_repeats（10 分），Part 3 才是主场（72 分实现 + 13 分 writeup）。

**关键路径**
1. Part 1：CUDA saxpy，熟悉 `cudaMalloc / cudaMemcpy / kernel<<<>>> / cudaDeviceSynchronize`。
2. Part 2：把课上那个 iterative exclusive scan（upsweep + downsweep）直译成 CUDA，多次 kernel launch；再写 `find_repeats`。
3. Part 3 分三步走（handout 原话）：
   - **先改对**：不靠锁、不靠同步地保证 order + atomicity。
   - **再看为什么慢**。
   - **然后才真正开始思考**：`circleBoxTest.cu_inl` 是关键工具。
4. 主流解法谱系（从慢到快）：全局锁 → 每像素锁/原子 → 用 shared-memory prefix-sum 做 compaction（每个 block 先筛出影响本 tile 的圆）→ 分 tile + circle-box 剔除 + 块内按序 blend + **一次写全局**。

**细节与易错点**
- **scan 的性能陷阱**：naive 实现给 `parallel_for` 的每个迭代都起 N 个线程再用 `if` 筛——upsweep 最后一轮只有 2 个线程干活，其余全空转。满分实现是**每个内层迭代只起一个线程**。
- 提供的 `exclusiveScan.cu_inl` 只支持**长度为 2 的幂**的数组，且**要求 block 内线程数 == 数组大小**（读注释）。
- `shadePixel` 每次都对全局内存读改写 → 改成**寄存器/local 累加器**，最后只写一次全局。
- `rand1M` / `micro2M`：临时结构别乱开全局内存；`cudaMalloc` 失败是**静默**的，不检查 `cudaError_t` 就会变成"莫名其妙的正确性失败"。用 handout 给的 `cudaCheckError` 宏包住所有 CUDA 调用。
- kernel launch 的错误是**异步**的，会在下一次被包的 CUDA 调用处才报出来。
- 建议次序：**先解决 order，再看 atomicity 是否还需要**（很多解法里 order 保证之后 atomicity 自动消失）。
- 评分：8 个场景，每个 2 分正确性 + 7 分性能；`T <= 1.20 * T_ref` 满分，`T > 10 * T_ref` 零分。

**设计理念**
- **消除共享 > 加锁**：把"谁会碰这个像素"圈清楚，比给像素上锁便宜一个数量级。
- **减少通信**：一个像素的累加全程在寄存器/共享内存里，最后一次写全局——PA3 收益最大的一步。
- **数据复用**：circle 数据被一个 block 内所有线程反复用 → 进 shared memory。
- scan 是数据并行四大原语之一（map / reduce / scan / groupBy），PA2 手写过、PA3 在 GPU 上再写一次、PA4 的 PSUM 累加还是它。**scan 是这门课的暗线。**

---

### 4.4 PA4 · Trainium2 上的 Fused Conv+MaxPool

**抓重点**
1. 硬件：Trn2.3xlarge，一个 device 含 8 个 NeuronCore，本次只写**单核** kernel。存储三层：**HBM（96 GiB）/ SBUF（28 MiB，带宽约 HBM 20 倍）/ PSUM（2 MiB，专放矩阵乘结果）**。
2. **SBUF/PSUM 是软件管理的**：不显式 DMA 就用不上。这是和 GPU 最大的区别。
3. NKI 三种操作：load（HBM→SBUF）、compute（引擎）、store（SBUF→HBM）。kernel 用 Python 写，`@nki.jit`。
4. Part 1（30 分）：vector add 的 naive / tiled / stream 三版 + transpose；Part 2（70 分）：fused conv2d + maxpool。

**关键路径（Part 2）**
1. 先在 NumPy 层面把算法想清楚：输入展平成 `(C_in, H*W)`，对 filter 的每个 `(i, j)` 把输入偏移后做一次 matmul 并累加。**注意：这不是课上讲的 im2col（每个 patch 一行），是按 filter 位置累加的另一种映射**，handout 明确标注了区别。
2. 然后才谈 tile：输出 tile 怎么切 → 反推需要 X 和 W 的哪些子块 → 循环次序怎么排才能让中间结果一直留在 PSUM 里。
3. 循环排序原则：**先让每个输出 tile 在 PSUM 里累加完再 copy 回 SBUF**（保证 SBUF 里每个输出块只写一次），再排剩下的循环优化输入局部性。
4. 加 bias（`nisa.tensor_tensor`）、融 maxpool（`nisa.tensor_reduce(nl.max, ...)`）。
5. 用 `neuron-profile` 看 MFU（float32 / float16 都要报）。

**细节与易错点**
- **Tile 硬约束**：`nc_matmul` 的左操作数 tile ≤ `(128, 128)`、右操作数 ≤ `(128, 512)`、PSUM 输出 ≤ `(128, 512)`。
- **左操作数是转置的**：`lhsT`，`nc_matmul(lhsT, rhs)` 算的是 `A x B`，不是 `A^T x B`。这是最容易搞反的一处。
- **partition 维 P ≤ 128，且必须是张量的第一维**；free 维 F 另有上限。
- 约定：只支持 stride = 1、不需要自己做 padding（输入已 pad 好）；`pool_size` 只能是 1 或 2（`pool_size = 1` = 不做池化）；保证 `(H - Fh + 1) % pool_size == 0`。
- NKI 使用纪律：优先 `nisa.*`（`nc_matmul` / `tensor_scalar` / `tensor_reduce` / `dma_copy`）而不是 `nl.matmul` / `nl.load` / `nl.store`；**不要用嵌套函数**；索引用整数切片，**不要嵌套切片**；**不要用 block dimension**；注意 `dma_copy` 是 `dst` 参数而其他 API 返回新张量。
- 测试：小图 `32x16` + 大图 `224x224`（后者装不进 SBUF，必须 tiling）。满分要求性能在参考内核的 **120%** 以内，且 **float16 的门槛更严**。
- 调试：`--simulate` + `nl.device_print`，但模拟器与真机可能有差异。

**设计理念**
- **软件管理的存储层次 = 把 cache 策略交给程序员** → tiling 不再是优化而是必需；这也意味着"数据怎么流过机器"成了首要设计对象。
- **loop fusion**：conv 和 maxpool 融合省掉一次 HBM 往返。这是 L9 "layer fusion" 的实操版。
- **MFU（Model FLOPs Utilization）** 是加速器的效率尺子：不是"跑了多久"，而是"离硬件峰值 FLOPs 有多远"。
- 与 GPU 的对照：GPU 上你写 thread/block，硬件管 warp 和 cache；这里你写 tile 和 DMA，硬件只提供引擎。**抽象层次更高，但暴露的硬件约束也更多。**

---

### 4.5 PA5 · 写一个最快的 kernel（开放题）

**抓重点**
1. **没有性能门槛，评分看 work log。** 80 = 有概念地走了几步；95 = 能用 profiler 数据推出下一步该做什么；100+ = 成绩上榜或令人印象深刻。
2. 平台：H100，通过 `popcorn-cli` 提交到课程作业队列（有 leaderboard）；可选 CUDA / Triton / TileLang。
3. 题目五选一：Histogram、1d-occupancy-decoder、FlashAttention、3D Heat Equation (RK4)、SwiGLU。
4. **明确允许用 LLM**（写代码、解读 profiler、出主意都行），但 work log 必须写清你的推理过程。

**关键路径**
1. 选一个 kernel，跑 baseline（PyTorch 版）拿数字。
2. `--mode profile` 拿 NCU 报告（`Compute_Throughput` / `SM_Busy` / `DRAM_Throughput` / `L1|L2 hit rate`），判断是算力受限、带宽受限还是并行度不够。
3. 按 §2.3 的四步循环迭代，每一步都留一版代码 + 数字。
4. work log 三部分：**每一步做了什么（结构/性能/统计/结论/假设/下一步）→ 为什么停 → LLM 有没有帮上忙**。

**细节与易错点**
- 只在 H100 上收集性能数据；本地小卡（如 L4）只用于调试和探索选项，别拿它调参。
- 写 CUDA 要走 `python wrap_cuda_submission.py <SUNetID>` 包成 `submission.py` 才能提交。
- `ncu` 需要 GPU 性能计数器权限（`NVreg_RestrictProfilingToAdminUsers=0` + 重启）。
- work log 要求的是**判断力**，不是流水账：写"我试了 X 得到 Y，所以我认为瓶颈是 Z，于是下一步做 W"。

**设计理念**
- 这是"**没有参考实现可追**"的真实性能工程：你不知道天花板在哪，只能靠测量逼近。
- 一份好的 work log 就是一门可复现的实验科学记录；**能被推翻的假设比正确的猜测更值钱**。

---

### 4.6 biggraphs · OpenMP BFS（支线 / 加分）

**抓重点**
1. 三种 BFS：**top-down**（遍历 frontier，标记邻居）、**bottom-up**（每个未访问点自己看有没有邻居在 frontier 里）、**hybrid**（按 frontier 大小动态切换）。
2. 同步：frontier 的更新用 **compare-and-swap**（`__sync_bool_compare_and_swap`）远快于 `#pragma omp critical`。
3. 不要指望接近线性加速——writeup 要能说清为什么（负载不均 / 同步 / 数据移动）。

**易错点**
- top-down 里 `dist[v] == -1` 的判断与 CAS 的配合：能提前知道比较必然失败时就别发 CAS。
- bottom-up 需要"未访问集合"的高效表示；两种算法对 frontier 的表示可能不同，hybrid 要在两者之间转换（有开销，切换阈值要算这笔账）。
- 切换阈值：frontier 小时 top-down 快、frontier 大时 bottom-up 快，阈值来自测量而不是猜。

### 4.7 两个 CUDA 小样（PA3 前置）

- `intro_to_cuda-main/`：`demo1` hello world、`demo2` convolution、`demo3` matmul、`demo4` errors（错误处理，带 solutions）、`demo5` matmul debug。
- `cuda_tutorial-main/`：`vecAdd.cu` + `matMul.cu`，最小可跑模板。
- 用法：PA3 之前花一小时过一遍 `demo3`/`demo5` 和 `cuda_tutorial`，把 `cudaMalloc / cudaMemcpy / <<<blocks, threads>>> / cudaDeviceSynchronize` 这套骨架走顺，PA3 就能把精力全放在并行设计上。

---

## 5 逐层展开索引（§6–§11 已全部展开）

| 目标节 | 内容 | 依赖 |
|---|---|---|
| §6 PA1 逐层 | 6 个 program 的数据流与实测口径、`CS149intrin.h` 全部指令清单、kmeans 的 `dist` 热点改写方案 | `asst1-master.zip` 解压 |
| §7 PA2 逐层 | `tasksys.h` 该加哪些成员、三个 run() 的伪代码、Part B 的两队列 + 入度实现、条件变量的正确模板 | `asst2-master/`（已在本地） |
| §8 PA3 逐层 | `cudaRenderer.cu` 的错误在哪、tile + prefix-sum 方案的完整数据流、8 个场景的特征与对应策略 | `asst3-master.zip` 解压 |
| §9 PA4 逐层 | NKI API 速查、tile 尺寸推导、conv→matmul 的矩阵维度图、PSUM 累加的循环排布 | `asst4-trainium2-main.zip` 解压 |
| §10 PA5 逐层 | 五个 kernel 的难度/收益对比与选题建议、NCU 指标读法、work log 模板 | `asst5-kernels-main.zip` 解压 |
| §11 biggraphs 逐层 | 三种 BFS 的伪代码与 OpenMP 标注、CAS 用法、切换阈值的测量方法 | `biggraphs-ec-main.zip` 解压 |

---

## 6 PA1 逐层 · 六个 program 的改法与算账方式

> 源码在 `asst1-master.zip` 内（`prog1_mandelbrot_threads/`、`prog2_vecintrin/`、`prog3_mandelbrot_ispc/`、`prog4_sqrt/`、`prog5_saxpy/`、`prog6_kmeans/`）。
> 环境口径：myth 机器 **4 核 / 8 超线程**；ISPC 用 `--target=avx2`，即 **8-wide**。

### 10.1 prog1：std::thread 版 mandelbrot（20 分）

**真实接口**（`prog1_mandelbrot_threads/mandelbrotSerial.cpp`）：

```
void mandelbrotSerial(float x0, float y0, float x1, float y1,
                      int width, int height,
                      int startRow, int numRows,     // 算 [startRow, startRow+numRows) 这段连续行
                      int maxIterations, int output[]);
```

`prog1_mandelbrot_threads/mandelbrotThread.cpp` 里 `workerThreadStart()` 目前只 `printf("Hello world...")`；主线程复用为 worker 0（`for i=1..numThreads-1` 建线程，然后 `workerThreadStart(&args[0])` 再 join）。

**关键路径**

1. 两线程版：线程 0 算上半、线程 1 算下半 —— 一次 `mandelbrotSerial(..., 0, height/2, ...)` 即可。
2. 推广到 2..8 线程：`startRow = height * threadId / numThreads`，`numRows = height / numThreads`（**连续块**）。画加速比曲线。
3. **这一步一定会翻车**：view 1 的加速比远不到线性，3 线程那个点尤其难看。在每个 `workerThreadStart` 首尾插 `CycleTimer::currentSeconds()` 打印，你会看到线程之间耗时差好几倍 —— 因为 Mandelbrot 集合内部的点要跑满 `maxIterations` 才退出，集合外部的点几步就退出，**图像上半和下半的代价天生不均**。
4. 不改同步、不通信，改分配策略即可：**交织（interleaved / cyclic）**。关键点是 `mandelbrotSerial` 只接受"连续一段行"，所以交织要**按行循环调用**：

```
for (int row = args->threadId; row < args->height; row += args->numThreads)
    mandelbrotSerial(args->x0, args->y0, args->x1, args->y1,
                     args->width, args->height,
                     row, 1,                       // 每次只算 1 行
                     args->maxIterations, args->output);
```

5. 目标：两个 view 上 8 线程都到 **7-8x**。然后跑 16 线程 —— **不会更快**，因为 8 个执行上下文已经用满，超订只增加调度开销。

**易错点**
- `workerThreadStart` 里必须自己判断"我负责哪些行"，`args` 是每个线程一份的数组（`WorkerArgs args[MAX_THREADS]`），写各自的 `args[i]` 是安全的。
- 主线程也是 worker（`args[0]`），别把它漏掉，否则你只用了 `numThreads-1` 个核。
- 交织时每次调用只传 1 行，调用次数 = `height/numThreads`，函数调用开销可忽略（远小于一行 1200 次迭代）。
- 判据：交织后**每个线程的耗时应该几乎相同**——这是"负载是否均衡"的直接证据，写进 writeup。

**设计理念**：这是全课程第一次遇到"**静态分配遇上不均匀代价**"。两种解法——动态调度（PA2 的线程池）或者更聪明的静态策略（这里）。**能用静态解决就不要引入运行时调度**，因为后者本身有成本。

### 10.2 prog2：CS149 fake SIMD intrinsics（20 分）

**可用的指令全集**（`prog2_vecintrin/CS149intrin.h`，真实清单）：

| 类别 | 指令 |
|---|---|
| 掩码 | `_cs149_init_ones(N)`（前 N 个 lane 置 1）、`_cs149_mask_not` / `_or` / `_and`、`_cs149_cntbits`（数 1 的个数） |
| 数据搬移 | `_cs149_vset_float/int`、`_cs149_vmove_float/int`、`_cs149_vload_float/int`、`_cs149_vstore_float/int` |
| 算术 | `_cs149_vadd` / `_vsub` / `_vmult` / `_vdiv` / `_vabs`（float/int 各一份） |
| 比较 | `_cs149_vgt` / `_vlt` / `_veq`（返回掩码） |
| 归约 | `_cs149_hadd_float`（相邻两两相加）、`_cs149_interleave_float`（奇偶重排） |

**语义要点**：**每条指令都带一个可选 mask；mask 位为 0 的 lane 保持原值不变**。这是你实现"条件执行"的唯一手段——没有 if、没有分支，只有掩码。

**`clampedExp` 的写法**（目标：把 `values[i]^exponents[i]` 结果截断到 9.999999）

```
_cs149_vec_float x, result, nine = _cs149_vset_float(9.999999f);
_cs149_mask  maskAll = _cs149_init_ones(VECTOR_WIDTH);

for (int i = 0; i < N; i += VECTOR_WIDTH) {
    _cs149_mask mask = _cs149_init_ones(min(VECTOR_WIDTH, N - i));   // 尾部不足一组
    _cs149_vload_float(x, values + i, mask);
    _cs149_vload_int(e, exponents + i, mask);

    _cs149_vset_float(result, 1.f, mask);           // 累积器初始化
    // 逐位做幂：result *= x 的每一位（或按指数循环）
    ...
    _cs149_mask tooBig = ...;                       // result > 9.999999 ?
    _cs149_vset_float(result, 9.999999f, tooBig);   // 超限的 lane 设为上限
    _cs149_vstore_float(values + i, result, mask);
}
```

实际实现里幂运算要按 `exponents` 的每一位展开（用 `vgt` 判位 + `vmult` 累积），也可以逐次递减计数。**核心是全程无分支**。

**验收与思考**
- 用 `./myexp -s 3` 测**非整数倍长度**（尾部掩码），`-s 10000` 跑大数据；`-l` 打印指令日志。
- 性能指标是 "Total Vector Instructions"（每条算 1 个周期），"Vector Utilization" 是 lane 启用比例。
- 扫 `VECTOR_WIDTH = 2,4,8,16`：**利用率随宽度变化的原因**是尾部与掩码——宽度越大，一次能喂满的 lane 越多但尾部浪费也越明显；同时"需要多少个 `_cs149_cntbits` 之类的标量操作"在变。

**易错点**
- 忘记尾部掩码 → `N` 不是 `VECTOR_WIDTH` 倍数时越界或写入垃圾。
- 混淆"mask 位为 0 表示保持原值"：这意味着**结果寄存器必须先被初始化**，否则未激活 lane 里是未定义值。
- `hadd` / `interleave` 是给 `arraySumVector`（加分题）用的，归约目标是 `N/VECTOR_WIDTH + log2(VECTOR_WIDTH)` 步。

### 10.3 prog3：ISPC 版 mandelbrot（20 分）

- 骨架 bug：`mandelbrot_ispc_withtasks()` 里的 `launch[2]` 只起 2 个任务，改任务数就能过 32 倍。
- **为什么**：`foreach` 只能用一个核的 SIMD 单元（8-wide AVX2，理论 8 倍）；`launch` 才能把任务分到 4 个核。两者相乘 ≈ 32。
- **任务数怎么定**：太少（2 个）→ 核没用满 + 每个核上任务代价仍不均；太多 → 任务调度开销 + 每个任务内 SIMD 组数不足。**经验做法**：任务数取"核数的几倍"（如 4-8 倍执行上下文数），让运行时有调剂余地，又不至于碎掉。
- **上限从哪来**：8-wide AVX2 × 4 核 = 32。观察到的数会更小，因为**divergence**：Mandelbrot 里同一 gang 的 8 个像素迭代次数不同，整组按最慢的走。比较 view 1 和 view 2 就能证实。

### 10.4 prog4：sqrt（15 分）与 prog5：saxpy（10 分）

**sqrt** 用牛顿法解 `1/x^2 - S = 0`，初值固定 1.0，输入在 (0,3)。

- 收敛速度**依赖输入值**：越靠近 1 收敛越快，越靠近 0 或 3 迭代次数越多。
- 于是"输入分布"直接决定加速比：
  - **最大加速比的输入**：让同一 gang 内所有 lane 迭代次数相同（全部取同一个值，或全部取接近 1 的值）→ 无 divergence。
  - **最小加速比的输入**：让同一 gang 内迭代次数差异最大（交替取 1 和 3）→ 最慢 lane 拖着全组。
- 结论要分两层说：**SIMD 加速比**（单核，来自 8-wide）和**多核加速比**（从 without-tasks 到 with-tasks）。改输入对前者影响大，对后者影响小——因为多核是任务级并行，任务之间不存在 lane 同步。

**saxpy** 是 `result = scale*X + Y`，N = 2000 万。

- 每 3 个元素（读 X、读 Y、写 result）只做 2 次浮点运算 → **算术强度极低，天生带宽受限**。
- 所以多核加速比会早早撞墙，"能不能改到近线性？**不能**"——这是硬件上限，不是实现问题。答案要这么写。
- 加分题 `TOTAL_BYTES = 4 * N * sizeof(float)` 里的 **×4**：写回 result 时 CPU 要**先读整条 cache line 再写**（write-allocate），所以一次写 = 一次读 + 一次写。

### 10.5 prog6：kmeans 找热点（15 分）

**真实代码**（`prog6_kmeans/kmeansThread.cpp`，219 行）：

```
double dist(double *x, double *y, int nDim) {
  double accum = 0.0;
  for (int i = 0; i < nDim; i++) accum += pow((x[i] - y[i]), 2);
  return sqrt(accum);
}

void computeAssignments(WorkerArgs *const args) {   // K 个质心 × M 个点
  for (int k = args->start; k < args->end; k++)     // 骨架按 k 切！
    for (int m = 0; m < args->M; m++) {
      double d = dist(&args->data[m*args->N], &args->clusterCentroids[k*args->N], args->N);
      if (d < minDist[m]) { minDist[m] = d; args->clusterAssignments[m] = k; }
    }
}
```

**热点在哪**：`computeAssignments` 是 `K * M` 次 `dist` 调用，每次 N=100 维；`computeCentroids` 只有 `M*N`；`computeCost` 只有 `M` 次 `dist`。**它是压倒性热点**，而且主循环跑很多轮直到收敛。

**关键陷阱（这题的题眼）**：骨架的切分维度是 **k（质心）**，但从 k 切分会让多个线程同时写 `minDist[m]` 和 `clusterAssignments[m]` —— 有数据竞争。**正确做法是按 m（数据点）切分**：每个线程负责一段数据点，对**全部 K 个质心**求距离，写自己那段 `minDist` / `clusterAssignments`，无共享写。

```
void computeAssignments(WorkerArgs *const args) {
  // start/end 现在是数据点 m 的范围
  for (int m = args->start; m < args->end; m++) {
    double best = 1e30; int bestK = -1;
    for (int k = 0; k < args->K; k++) {
      double d = dist(&args->data[m*args->N], &args->clusterCentroids[k*args->N], args->N);
      if (d < best) { best = d; bestK = k; }
    }
    args->minDist[m] = best;  args->clusterAssignments[m] = bestK;
  }
}
```

配套改动：`WorkerArgs` 加 `double* minDist`（或每个线程自己 new 一份）、`kMeansThread` 里按 m 切段起线程。handout 说官方解法改了 **20-25 行**——量级就在这。

**第二层优化**：`pow(a, 2)` 换成 `a*a`（语义不变，但 `pow` 是通用浮点函数调用，比一次乘法贵一个数量级）。N=100 维 × M × K 次调用，这笔账很大。

**约束（别踩线）**：只改 `kmeansThread.cpp`；`stoppingConditionMet` 不许动；`kMeansThread` 接口不许改；**只能并行化 `dist` / `computeAssignments` / `computeCentroids` / `computeCost` 中的一个**；不能改算法语义（`plot.py` 出的两张图要和骨架一致）。

---

## 7 PA2 逐层 · 任务执行库的三种实现与 DAG 调度

> 源码在本地已解压：`~/develop/learning/learning-408/parallel-cs149/asst2-master/`（`part_a/`、`part_b/`、`tests/`）。
> 接口定义见 `part_b/itasksys.h`：`IRunnable::runTask(task_id, num_total_tasks)`、`ITaskSystem::run / runAsyncWithDeps / sync`。

### 11.1 先看测试集：你的实现会被什么样的负载考

`tests/README.md` 描述的 11 个测试，就是你的设计约束（这张表值得反复看）：

| 测试 | 任务数 × launch 数 | 特征 | 对调度的含义 |
|---|---|---|---|
| `super_super_light` | 64 tasks × 400 launches | 两个 2^15 缓冲区来回拷贝，**任务极便宜** | 调度开销完全主导 |
| `super_light` | 64 × 400 | 拷贝前递增，**任务便宜** | 需要真并行才能赢 |
| `ping_pong_equal` | 64 × 400 | 2^19 缓冲区，任务代价**均匀** | 静态分配就够 |
| `ping_pong_unequal` | 64 × 400 | 同上但**代价不均** | 必须动态分配 |
| `recursive_fibonacci` | 256 × 30 | 计算密集、递归 | 计算主导，开销可忽略 |
| `math_ops_in_tight_loop` | 16 × 2000 | 每任务 32 次 exp/log/乘加 | launch 数远大于任务数 |
| `..._fewer_tasks` | 9 × 2000 | 512 份工作塞进 9 个任务，**不均** | 任务数 < 核数，考验不浪费线程 |
| `..._fan_in` | 64 × 256 + 1 次 reduce | 末尾一个 reduce 依赖全部 | DAG：扇入 |
| `..._reduction_tree` | 64 × 32 + 二叉归约树 | 每层 add-reduce 依赖两个前驱 | DAG：树形依赖 |
| `spin_between_run_calls` | 1 + 2 + 1 tasks | 轻-中-轻，async 下最后一个依赖前两个 | 考验"别让线程空转" |
| `mandelbrot_chunked` | 128 × 1 | 单 launch，128 个连续块，**不均** | 只有一次 launch，线程池与 spawn 差不多 |

**这张表直接回答了 writeup 必答的"为什么简单版更快"**：`super_super_light` 的任务便宜到什么程度？每个任务就是拷贝 512 个元素，而一次 `run()` 有 64 个任务、跑 400 次。此时线程创建/同步/join 的成本、以及 cache 在线程间来回易主的代价，可能比并行收益还大。**serial 版本没有同步开销，也没有伪共享**。

### 11.2 Part A 三个实现：演进链与伪代码

#### Step 1 · `TaskSystemParallelSpawn`

```
run(runnable, num_total_tasks):
    shared_counter = 0                    // 动态抢任务
    threads = min(num_threads, num_total_tasks)
    spawn threads-1 个 worker，主线程也当 worker
    每个 worker:
        while (true) {
            i = atomic_fetch_add(&shared_counter, 1)
            if (i >= num_total_tasks) break
            runnable->runTask(i, num_total_tasks)
        }
    join 所有 worker
    return                                // 返回时全部任务已完成 → 满足同步语义
```

要点：**任务数少于线程数时别起满线程**（`mandelbrot_chunked` 是 128 任务，但 `spin_between_run_calls` 只有 1 个任务）。动态抢任务用原子计数器就够了，不必用锁。

#### Step 2 · `TaskSystemParallelThreadPoolSpinning`

在构造函数（或首次 `run()`）里把 `num_threads` 个 worker 建好，每个 worker 跑一个死循环：

```
worker_loop:
    while (!shutdown) {
        if (有可执行的任务) { 取一个; runTask(...); 已完成计数++ }
        // 没有就继续转（spin）
    }
```

`run()` 的变化（**这是本步最容易写错的地方**）：

```
run(runnable, num_total_tasks):
    lock(m)
    把这次 launch 的任务挂到就绪队列; num_remaining = num_total_tasks
    unlock(m)
    while (已完成计数 != num_total_tasks) { /* 主线程自旋等待 */ }
    return
```

**致命陷阱**：判断"全部完成"必须看**已完成计数 == num_total_tasks**，不能看"队列为空"。队列空只说明任务都被领走了，它们可能还在跑。同理，worker 数 > 0 且队列空时也不能判定结束。

主线程自旋还带来一个副作用：**它占着一个核空转，抢了 worker 的执行资源**——这正是 Step 3 要修的问题之一。

#### Step 3 · `TaskSystemParallelThreadPoolSleeping`

把两处自旋换成条件变量：

1. worker 无活可干 → 睡在 "有任务" 条件上。
2. **调用 `run()` 的主线程** → 睡在 "本批完成" 条件上，由最后一个完成任务的 worker `notify`。

```
worker_loop:
    lock(m)
    while (!shutdown) {
        while (队列空 && !shutdown) cond_worker.wait(m)     // 必须用 while，不是 if
        if (shutdown) break
        取任务; unlock(m); runTask(); lock(m); 已完成++
        if (已完成 == 本批总数) cond_done.notify_all()
    }
    unlock(m)
```

条件变量的正确姿势：**always wait in a while loop**（虚假唤醒 + 条件可能在你拿到锁之前被别的线程满足）。

### 11.3 Part B：DAG 调度

只改 `TaskSystemParallelThreadPoolSleeping` 一个类。核心是两个结构：

- **`waiting` 集合**：已提交但依赖未满足的 launch。
- **`ready` 队列**：依赖已满足、可以立即执行的任务。

每个 launch 记录：`{runnable, num_total_tasks, remaining, TaskID, 后继列表}`。

```
runAsyncWithDeps(runnable, num_total_tasks, deps):
    lock(m)
    id = next_id++
    launch = {num_total_tasks, remaining = num_total_tasks, 依赖数 = deps.size()}
    for (d : deps)  launches[d].successors.push(id)     // 反向边
    if (依赖数 == 0) 把该 launch 的任务推进 ready 队列
    else            放进 waiting
    cond_worker.notify_all()
    unlock(m)
    return id                                            // 立即返回，任务可能还没开始

// worker 每完成一个任务：
    launch.remaining--
    if (launch.remaining == 0) {
        for (s : launch.successors) {
            launches[s].依赖数--
            if (依赖数 == 0) 把 s 的任务推进 ready 队列
        }
    }

sync():
    lock(m)
    while (还有任何未完成的 launch) cond_done.wait(m)
    unlock(m)
```

**依赖是 launch 粒度**：launchA 的 128 个任务**全部**结束后，launchB 的任一任务才能开始；但 launchB 和 launchC 之间可以完全并行（`..._reduction_tree` 就是考这个）。

**易错点清单**
- `sync()` 等的是**所有先前 launch**，不是最近一个。
- `run()` 可以用 `runAsyncWithDeps(runnable, n, 空 deps)` + `sync()` 实现（handout 明确允许），省得维护两套逻辑。
- TaskID 必须唯一自增；不用考虑 int 溢出。
- 句柄失效：用 `std::vector` 存 launch 时，**不要保存裸指针/引用**（vector 扩容会搬家），存下标或 id 去查。
- grading 会用**没给你**的 workload 测正确性——别对着 11 个测试调参调歪了。
- Part B 的性能门槛比 Part A 宽（50% vs 20%），正确性 30 分远重于性能 10 分。**先保证绝对正确**。

**设计理念**：这就是 TBB / Spark / PyTorch 调度器的同一道题——**批量任务 + 依赖图 + 固定线程池**。做完 PA2 再看这些框架，你看到的是实现细节而不是魔法。

## 8 PA3 逐层 · CUDA 圆形渲染器

> 源码在 `asst3-master.zip` 内（主要战场 `render/cudaRenderer.cu`，645 行；工具 `render/circleBoxTest.cu_inl`、`render/exclusiveScan.cu_inl`）。
> 参考实现 `render/refRenderer.cpp`（串行，正确）；评分 `render/checker.py`。

### 12.1 骨架到底错在哪（逐行看真实代码）

`kernelRenderCircles()` 是一个 **thread 对应一个 circle** 的 kernel：

```
int index = blockIdx.x * blockDim.x + threadIdx.x;
if (index >= cuConstRendererParams.numCircles) return;
...
for (pixelY = screenMinY; pixelY < screenMaxY; pixelY++)
    for (pixelX = screenMinX; pixelX < screenMaxX; pixelX++)
        shadePixel(index, pixelCenterNorm, p, imgPtr);
```

而 `shadePixel()` 里那段被注释框起来的代码：

```
// BEGIN SHOULD-BE-ATOMIC REGION
float4 existingColor = *imagePtr;                 // 读全局
newColor.x = alpha*rgb.x + (1-alpha)*existingColor.x;
...
*imagePtr = newColor;                             // 写全局
// END SHOULD-BE-ATOMIC REGION
```

**两个错误同时存在**：

1. **原子性**：读-混合-写这三步不是原子的，两个圆同时更新同一像素会丢更新。
2. **顺序**：每个 circle 由一个线程独立处理，线程调度顺序 = 圆的完成顺序，**和输入顺序毫无关系**。而半透明混合 `result = C_alpha*C_r + (1-C_alpha)*P_r` 是**不可交换**的（X 盖在 Y 上 ≠ Y 盖在 X 上）。

跑 `./render -r cuda rand10k` 对比 `./render -r cpuref rand10k`，能看到横向条纹，而且每帧都在变。

### 12.2 两条不变式与那句关键洞察

1. **Atomicity**：读四个 float、混合、写回，必须是一整个不可分的操作。
2. **Order**：对**同一个像素**的更新，必须按 circle 的输入顺序发生。

> **A key observation is that the definition of order only specifies the order of updates to the same pixel.**
> 不重叠的圆之间**没有任何顺序要求**，可以随意并行。

这句话是整个 PA3 的优化空间来源：**你的性能上限，取决于能不能把"有依赖的部分"圈得足够小。**

还有一个必须记住的次序建议（handout 原文加粗）：**先解决顺序，再看原子性还要不要紧**。很多时候顺序一旦保证（比如同一像素只由一个线程按序处理完），原子性问题自然消失。

### 12.3 解法谱系：从"能过"到"能拿满分"

| 档 | 做法 | 评价 |
|---|---|---|
| ① | **全局锁**：每个像素一把锁，更新前拿锁 | 正确但慢；锁的开销 + 串行化 |
| ② | **每像素 CAS / atomic 自旋**：抢到锁就按自己的顺序写 | 原子性有了，**顺序仍无法保证**（谁先抢到谁先写）→ 不正确 |
| ③ | **按 circle 顺序处理像素 + 前缀和做 compaction**：block 内先筛出"影响本 tile 的圆"，用 shared-memory exclusive scan 给它们分配紧凑槽位 | 正确且快，经典解法 |
| ④ | **分 tile + circle-box 剔除 + 块内按序 blend + 一次写全局** | 满分路线；对 `micro2M`（200 万个极小圆）尤其有效 |

### 12.4 推荐方案（④）的完整数据流

```
每个 CUDA block 负责图像的一个 tile（如 32x32 或 64x64 像素）
  1. 把该 block 要用的 circle 数据 load 进 shared memory
     —— 先用 circleInBoxConservative() 粗筛（把 box 按半径外扩，判圆心是否在扩大的盒子里）
     —— 再用 circleInBox() 精筛（圆心 clamp 到 box 求最近点，比距离）
  2. block 内用 sharedMemExclusiveScan() 做 compaction：
     每个圆产出一个 flag（是否影响本 tile），scan 之后得到它在本 block 槽位数组中的下标
  3. 槽位数组里的圆**天然按 circle index 升序**——这正是我们需要的输入顺序
  4. 每个线程负责 tile 内若干像素，用一个**寄存器/local 累加器**按槽位顺序做 blend
  5. 累加完只做 **一次全局写**（float4 一次写 4 个分量，比 4 次 fp32 store 更高效）
```

关键点：**`shadePixel` 每次都对全局内存读改写，改成寄存器累加是这一题收益最大的一步改造**。骨架代码里也留了注释提示这条。

### 12.5 Part 2 的 scan（10 分）：真实细节

`exclusiveScan.cu_inl` 的硬性要求（写在文件头，别跳过）：

- 输入长度**必须是 2 的幂**；
- **block 内线程数必须等于数组长度**（`SCAN_BLOCK_DIM` 既是线程数也是扫描元素数，且 ≤ 1024）；
- `sScratch` 要有 `2 * SCAN_BLOCK_DIM` 个元素；
- 三个数组都要在 shared memory 里。

还有一个极易踩的坑（文件里专门用 NOTE 标出来了）：

```
// 线性线程下标必须这样算：
int linearThreadIndex = threadIdx.y * blockDim.x + threadIdx.x;
// 不能写成 threadIdx.x * blockDim.x + threadIdx.y
```

因为 scan 假设**每 32 个相邻的线性下标（0-31, 32-63, ...）构成一个 warp**，它们 lockstep 执行。用 2D 索引时如果顺序弄反，warp 的划分就散了，scan 直接错。

`find_repeats` 的性能陷阱（handout 原文）：**naive 实现给 `parallel_for` 的每个迭代都启动 N 个线程再用 `if` 筛**——upsweep 最后一轮只有 2 个线程在干活，其余全空转。满分实现是**每个内层迭代只起一个线程**。

### 12.6 八个场景与对应策略

评分表里的 8 个场景（`rgb`, `rand10k`, `rand100k`, `pattern`, `snowsingle`, `biglittle`, `rand1M`, `micro2M`），每个 2 分正确性 + 7 分性能：

- `rgb` / `pattern`：圆很少，**launch 开销主导**，别为它们过度设计。
- `rand10k` → `rand100k` → `rand1M`：随机圆数量递增，**并行度足够，考验每圆的处理效率**。
- `micro2M`：200 万个**极小圆**——每个圆只覆盖极少数像素，**必须用 circle-based 并行 + 强力剔除**，否则 per-pixel 方案会退化成"每个像素扫 200 万个圆"。
- `snowsingle`：雪花单帧，走 `SNOWFLAKES` 那条带 `lookupColor` 的分支。
- `biglittle`：大小圆混合——大圆覆盖多、小圆覆盖少，考验**负载在 block 间的均衡**。

判分：`T <= 1.20 * T_ref` 满分；`T > 10 * T_ref` 零分；中间按 `7 * T_ref / T` 给分。

### 12.7 易错点清单

- **`cudaMalloc` 失败是静默的**。`rand1M` / `micro2M` 下如果临时结构开太多全局内存，程序不会报错，只会"莫名其妙正确性失败"。必须包 `cudaCheckError` 宏。
- **kernel launch 的错误是异步的**，会在下一次被包的 CUDA 调用处才报出来；所以调试期把所有 CUDA API 都包上。
- **`shadePixel` 里那个场景判断在内层循环**，骨架注释明确建议把它提到 `kernelRenderCircles` 外面（设置 lane mask 本身就有开销）。
- 全局写用 `*(float4*)ptr = value` 一次写 4 个分量（骨架里 `kernelClearImage` 就是这么写的）。
- 图像尺寸保证是 256 的倍数，所以 tile 划分不用处理不规则边界。

### 12.8 设计理念

- **消除共享 > 加锁**：把"谁会碰这个像素"圈清楚（靠 tile + 排序），比给像素上锁便宜一个数量级。
- **减少通信**：一个像素的整个累加过程留在寄存器/共享内存，最后一次写全局。
- **数据复用**：circle 数据被 block 内所有线程反复用 → 进 shared memory。
- **两个并行轴**：parallelism across pixels 与 across circles，在不同阶段分别用（`micro2M` 用后者，`rand1M` 用前者）。
- **scan 是这门课的暗线**：PA2 手写过线程池调度，PA3 在 GPU 上写 scan，PA4 在 PSUM 里做累加——同一件事的三种硬件形态。

## 9 PA4 逐层 · Trainium2 与 NKI

> 源码在 `asst4-trainium2-main.zip` 内：`part1/kernels.py`（152 行）、`part2/conv2d.py`（78 行，函数体是 `raise RuntimeError`）、`part2/conv2d_numpy.py`（NumPy 参考实现）。
> 环境：AWS `Trn2.3xlarge`，一个 Trainium device 含 **8 个 NeuronCore**，本作业只写**单核** kernel。

### 13.1 硬件数字（先背下来，后面每一步都在用）

| 层次 | 容量 | 说明 |
|---|---|---|
| HBM | 96 GiB | 设备主存；kernel 外的 NumPy 数组默认在这里 |
| SBUF | 28 MiB | 片上，**带宽约 HBM 的 20 倍**；不显式搬就用不上 |
| PSUM | 2 MiB | 只放矩阵乘结果（tensor engine 的输出暂存） |

**核心区别**：CPU/GPU 的 cache 对软件"不存在"（硬件实现细节）；NeuronCore 的存储是 **software managed**，每一次搬运都要你写 DMA。

### 13.2 Part 1：vector add 的三步演进（真实骨架）

**① `vector_add_naive`** —— 直接把整个向量搬进 SBUF 再加。**只能处理长度 ≤ 128 的向量**。原因：SBUF 里的张量是二维的，**第一维叫 partition 维 P，P ≤ 128**（这是硬件的 128 条计算通道的限制）。1D 向量唯一的那一维就是 P，所以最多 128 个元素。

**② `vector_add_tiled`** —— 骨架里 `ROW_CHUNK = 1` 是 TODO，你要改成 128：

```
for m in nl.affine_range(M // ROW_CHUNK):
    a_tile = nl.ndarray((ROW_CHUNK, 1), dtype=..., buffer=nl.sbuf)
    nisa.dma_copy(src=a_vec[m*ROW_CHUNK:(m+1)*ROW_CHUNK], dst=a_tile)
    res = nisa.tensor_scalar(a_tile, nl.add, b_tile)
    nisa.dma_copy(src=res, dst=out[...])
```

这样就能处理任意 128 倍数的长度了。

**③ `vector_add_stream`** —— 骨架里 `FREE_DIM = 2` 是 TODO。思路是**把向量 reshape 成 (128, M/128) 的二维 tile**，一次 DMA 搬 `128 × FREE_DIM` 个元素，**摊薄 DMA 的启动开销**：

```
a_vec_re = a_vec.reshape((PARTITION_DIM, M // PARTITION_DIM))   # PARTITION_DIM = 128
for m in nl.affine_range(M // (PARTITION_DIM * FREE_DIM)):
    a_tile = nl.ndarray((PARTITION_DIM, FREE_DIM), ...)
    nisa.dma_copy(src=a_vec_re[:, m*FREE_DIM:(m+1)*FREE_DIM], dst=a_tile)
    res = nisa.tensor_tensor(a_tile, b_tile, op=nl.add)     # 二维要用 tensor_tensor，不是 tensor_scalar
```

`FREE_DIM` 越大，每次 DMA 搬得越多、开销越薄，但 SBUF 容量是上限——**这是一个要实测的权衡**，用 `neuron-profile` 找拐点。

**④ `matrix_transpose`（加分/Step 3）** —— 分 tile，每个 tile ≤ 128x128，只用 `nisa.nc_transpose`。

> NKI 使用纪律（handout 明列）：优先 `nisa.*` 而不是 `nl.matmul` / `nl.load` / `nl.store`；**不要用嵌套函数**（都定义在模块层）；索引用整数切片，**不要嵌套切片**、不要用 `nl.arrange`；**不要用 block dimension**（纯软件概念，不影响硬件）。

### 13.3 矩阵乘：tile 约束与"左操作数是转置的"

Tensor engine 的物理限制（`nisa.nc_matmul`）：

- 左操作数 tile ≤ **(128, 128)**
- 右操作数 tile ≤ **(128, 512)**
- PSUM 里的输出 tile ≤ **(128, 512)**

所以任意尺寸的矩阵乘必须切成 tile 序列。骨架里的 `TILE_M = nl.tile_size.gemm_stationary_fmax`(128)、`TILE_K = nl.tile_size.pmax`(128)、`TILE_N = nl.tile_size.gemm_moving_fmax`(512)。

**最容易搞反的一处**：

> `nisa.nc_matmul(lhsT_tile, rhs_tile)` 里 `lhsT = A^T`。传进去的是**转置后的左矩阵**，算出来的才是 `A x B`。

所以在 conv 里常常要先把输入 reshape/transpose 成"通道维在前"的形状，才能和 filter 切片做收缩。

累加模式（骨架原样）：

```
res_psum = nl.zeros((TILE_M, TILE_N), nl.float32, buffer=nl.psum)
for k in nl.affine_range(K // TILE_K):
    ...dma_copy 两个 tile 进 SBUF...
    res_psum += nisa.nc_matmul(lhsT_tile[...], rhs_tile[...])   # 累加留在 PSUM
res_sb = nl.copy(res_psum, dtype=result.dtype)                  # 算完才搬回 SBUF
nisa.dma_copy(dst=result[...], src=res_sb)
```

### 13.4 Part 2：fused conv2d + maxpool 的算法骨架

`part2/conv2d_numpy.py` 给了清晰的语义（卷积：`out[b,c,i,j] = sum(x_ij * W[c]) + bias[c]`；池化：`amax` 一个 `pool_size × pool_size` 窗口）。

要实现的 `fused_conv2d_maxpool(X, W, bias, pool_size)`，形状约定：

- `X`: `[B, C_in, H, W]`，保证 `C_in % 128 == 0`
- `W`: `[C_out, C_in, Fh, Fw]`，保证 `Fh == Fw`、`C_out % 128 == 0`、**W 能整个装进 SBUF**
- `bias`: `[C_out]`；`pool_size ∈ {1, 2}`（`1` = 不做池化）
- 只支持 stride=1、不用自己做 padding；保证 `(H - Fh + 1) % pool_size == 0`

**注意这个 conv→matmul 的映射和课上讲的不一样**（handout 专门加了 NOTE）：不是"每个空间 patch 展开成一行"的 im2col，而是

```
输入 reshape 成 (C_in, H*W)
for i in range(Fh):
    for j in range(Fw):
        input_shifted = shift(input, (i, j))             # 按 filter 位置偏移对齐
        output += matmul(transpose(weight[i,j,:,:]), input_shifted)
```

即**按 filter 的每个 (i,j) 做一次矩阵乘并累加**，每个 filter slice 形状 `C_in × C_out`，沿 `C_in` 维收缩。

### 13.5 循环怎么排（这题真正的难点）

handout 给的排序原则：

1. **先让每个输出 tile 在 PSUM 里累加完，再 `nl.copy` 回 SBUF** —— 保证 SBUF 里每个输出块**只被写一次**（输出局部性）。
2. 剩下的循环（filter 的 i/j、tiled matmul 的 k、batch）**按输入局部性排序**：让同一块输入被连续复用。
3. 拿不准就**换几种顺序实测**，并说出为什么。

tile 维度的反推顺序（handout 的建议）：**先决定输出 tile 的形状 → 反推需要 X 和 W 的哪些子块 → 再排循环**。

### 13.6 实现顺序（handout 明确推荐）

1. 小图（`32x16`）、无 bias、无 maxpool → 先跑通；
2. 扩展到装不进 SBUF 的大图（`224x224`），加 tiling；
3. 加 bias（`nisa.tensor_tensor`）；
4. 融 maxpool（`nisa.tensor_reduce(nl.max, ...)`）；
5. 全部正确之后再谈性能与加分。

测试：`python3 test_harness.py`（加 `--test_maxpool` 才会跑池化用例）；性能门槛是**参考内核的 120% 以内**，且 **float16 更严格**。写 kernel 时就要为 float16 着想（dtype 转换、`nl.copy` 的 dtype 参数）。

Profiling：`--profile <name>` 出 `.neff` / `.ntff`，然后 `neuron-profile view -n x.neff -s x.ntff`，**看 "Estimated MFU" 那条线的最末端数值**（Cumulative Utilization），float32 和 float16 都要报。

### 13.7 易错点清单

- 左操作数是 **`lhsT`（转置）**，别把 `A x B` 写成 `A^T x B`。
- **partition 维 ≤ 128 且必须是第一维**；reshape 时别把 free 维放到前面。
- `nisa.dma_copy(src=, dst=)` 是**通过 dst 参数写入已有数组**；而大多数 `nisa` 计算指令是**返回新张量**。混用会静默出错。
- 不要把 `block dimension` 当成硬件概念去调。
- 调试用 `--simulate` + `nl.device_print`，但**模拟器和真机可能有差异**，不放心就把中间张量 return 出来看。
- 加分题：小图上的 MFU 通常更低（并行度不够填满引擎），提示是 `nc_matmul` 的 `moving` 参数可以接受 >2D 张量。

### 13.8 设计理念

- **软件管理的存储层次 = 把 cache 策略交给程序员**。tiling 从"优化技巧"变成了"能不能跑起来"的前提。
- **loop fusion**：conv 和 maxpool 融合，省掉一次 HBM 往返——这就是 L9 "layer fusion" 的实操版。**融合的收益 = 省掉的那次 HBM 读写，而不是省掉的算力。**
- **MFU（Model FLOPs Utilization）** 是加速器的效率尺子：不问"跑了多久"，问"离硬件峰值 FLOPs 有多远"。
- 与 GPU 的对照：GPU 上你写 thread/block，硬件管 warp 与 cache；这里你写 tile 和 DMA，硬件只提供引擎。抽象层次更高，暴露的约束也更多。

## 10 PA5 逐层 · H100 上的开放优化

> 源码在 `asst5-kernels-main.zip` 内：`problems/{histogram, 1d-occupancy-decoder, flashattention, rk4, swiglu}/`。
> 平台：H100，通过 `popcorn-cli` 提交到课程作业队列（有 leaderboard）。可用 CUDA / Triton / TileLang，**明确允许用 LLM**。

### 14.1 五个 kernel 的真实形状与本质考点

| kernel | 输入/输出形状 | 本质考点 |
|---|---|---|
| **histogram** | 输入 `[1048576, 512]`（值域 `[0,255]`）→ 输出 `[512, 256]` | **原子竞争**：512 个通道 × 大量线程抢 256 个 bin。经典解法是**先在 shared memory 里做 per-block 直方图，最后再合并到全局**，把全局原子次数降一个数量级 |
| **swiglu** | `SwiGLU(x,W,V,b,c,beta) = Swish(xW+b) ⊙ (xV+c)`，`Swish(x)=x*sigmoid(beta*x)`；`x:[B,S,D_in]` → `[B,S,H]` | **带宽受限的 elementwise + GEMM**。考点是融合：两个 GEMM + 激活 + 逐元素乘，能不能一趟走完不落 HBM |
| **rk4** | 3D 热方程，`u_t = α∇²u`，**8 阶精度 25 点 stencil**（1 中心 + 6 方向 × 4 邻居），RK4 时间推进 | **stencil + 时间步**。算术强度低、**带宽受限**；8 阶 25 点意味着每个点要读 25 个邻居 → shared memory / halo 管理是核心 |
| **flashattention** | `Q,K,V: [B, N, S, D]`，FP16 | 经典三件套：**tiling + fusion + online softmax**（用 running max / running sum 增量归一化，避免整行驻留） |
| **1d-occupancy-decoder** | queries `[B, 250k, 3] → MLP → [B,250k,768]`；latents `[B,1024,768]`；cross-attention 输出 `[B,250k,768]` → `[B,250k,1]` | **极端不平衡的 cross-attention**：query 25 万、latent 仅 1024。和常见 2k×2k 的 benchmark 完全不同，需要针对"K/V 极小、Q 极大"重做分块 |

### 14.2 选题建议（按"上手成本 / 上限"排序）

1. **histogram** —— 概念最集中（原子竞争 + shared memory + 归约），代码量最小，适合"把课上概念完整走一遍"。上限中等。
2. **swiglu** —— 结构清晰（GEMM + elementwise），容易用 Triton 快速迭代；瓶颈明确是带宽，能练"怎么判断带宽受限"。
3. **rk4** —— 有真实物理背景，stencil 的 halo/shared memory 优化路径清晰；work log 好写（每步都有可测的指标变化）。
4. **flashattention** —— 上限高、资料多，但也最容易变成"抄一个现成实现"；如果选它，work log 必须体现**你自己测出来的决策**（tile 尺寸、shared memory 分配、online softmax 的取舍）。
5. **1d-occupancy-decoder** —— 最复杂（MLP + cross-attention + LayerNorm + 投影，一整条前向），适合想冲 100+ 的团队。

### 14.3 NCU 报告怎么读

handout 给了一个真实 profile 片段（RK4 的 `heat_step_kernel`）：

```
Duration            : 7.10 us
Compute_Throughput  : 18.45%
SM_Busy             : 31.12%
L1_Cache_Throughput : 46.35%
DRAM_Throughput     : 4.45%
L1_Cache_Hit_Rate   : 80.99%
```

**读法**：

- `Compute_Throughput` 18% + `DRAM_Throughput` 4.5% → **既不算力受限也不带宽受限**，那瓶颈是什么？答案是**并行度不足 / 占用率太低**（SM_Busy 只有 31%，大量 warp 槽位空着）。
- 判断口诀：**某个吞吐率接近 100% 的就是瓶颈**；都低 = 延迟没藏好或并行度不够。
- 四个优化方向对照：增加并行度 → 提高占用率；减少通信 → 降 DRAM_Throughput 需求；隐藏延迟 → 更多并发 warp / 异步拷贝；缓解竞争 → 降原子/L2 冲突。

### 14.4 work log 怎么写（这是评分对象）

每一"步"都要有这六项（handout 明确列举）：

```
1. 当前代码是什么结构？（高层描述，如"我们把最外层循环分块，块映射到 CUDA block，内层循环并行到线程"）
2. 性能数字（明确给出运行时间）
3. 还测了哪些统计？（NCU 的哪些指标）
4. 从数据里得出什么结论？
5. 假设瓶颈是什么？怎么得出这个假设的？
6. 这个假设说明下一步该改什么？
```

再加上：**为什么停**（时间到了？还是从 profile 判断没多少空间了——后者的推理要写出来）以及 **LLM 有没有帮上忙、怎么用**。

### 14.5 流程要点

- `popcorn-cli submit --leaderboard <name> --mode <test|benchmark|leaderboard|profile> submission.py`
- 写 CUDA 要先 `python wrap_cuda_submission.py <SUNetID>` 包成 `submission.py`（队列只收 `submission.py`）
- 本地可跑：`python ../eval.py <test|benchmark|profile> test_cases/test.txt`
- `ncu` 需要 GPU 性能计数器权限：`NVreg_RestrictProfilingToAdminUsers=0` + 重启
- **只在 H100 上收集性能数据**；本地小卡（如 L4）只用于调试和探索选项

### 14.6 设计理念

这是"**没有参考实现可追**"的真实性能工程：你不知道天花板在哪，只能靠测量逼近。一份好的 work log 就是一门可复现的实验科学记录——**能被数据推翻的假设，比一次正确的猜测更值钱**。

## 11 biggraphs 逐层 · OpenMP BFS（支线 / 加分）

> 源码在 `biggraphs-ec-main.zip` 内：`bfs/bfs.cpp`（122 行，只有 `bfs_top_down` 是完整的，`bfs_bottom_up` / `bfs_hybrid` 是空函数）、`common/graph.h`。
> 加分规则：拿到 x/84 分就给**前面任意一个** PA 加 `(x/84)*10` 分。

### 15.1 数据结构（真实定义）

```
struct graph {
    int num_edges, num_nodes;
    int* outgoing_starts;  Vertex* outgoing_edges;   // CSR 出边
    int* incoming_starts;  Vertex* incoming_edges;   // CSR 入边（bottom-up 要用）
};
```

frontier 就是一个 `vertex_set { int count; int max_vertices; int* vertices; }`——**一个数组 + 一个计数**，每轮 BFS 在两个 list 之间来回 swap。

### 15.2 Part 1：top-down 并行版

串行骨架：遍历 frontier 里每个点的出边，遇到 `distances[v] == -1` 就设距离并加入新 frontier。并行化时**两处竞争**：

1. `distances[outgoing]` 的读写（多个线程可能同时发现同一个未访问点）；
2. `new_frontier->count++`（抢下标）。

**CAS 解法**（handout 明确要求用 compare-and-swap 而不是 `#pragma omp critical`）：

```
#pragma omp parallel for
for (int i = 0; i < frontier->count; i++) {
    int node = frontier->vertices[i];
    int start = g->outgoing_starts[node];
    int end   = (node == g->num_nodes - 1) ? g->num_edges : g->outgoing_starts[node+1];

    for (int e = start; e < end; e++) {
        int out = g->outgoing_edges[e];
        if (distances[out] == NOT_VISITED_MARKER) {          // 先读一次，明显失败就别发 CAS
            if (__sync_bool_compare_and_swap(&distances[out],
                                             NOT_VISITED_MARKER,
                                             distances[node] + 1)) {
                int index;
                #pragma omp atomic capture
                index = new_frontier->count++;
                new_frontier->vertices[index] = out;
            }
        }
    }
}
```

**为什么先读再 CAS 是安全的**：`distances` 只会从 `-1` 变成某个正数，**不会变回 -1**。所以读到的 `-1` 可能马上失效（那 CAS 会失败，无害），读到的非 `-1` 则一定失败——提前跳过就省掉一次原子操作。handout 专门问了这个问题。

### 15.3 Part 2：bottom-up

```
for each 未访问顶点 v (并行):
    for each 入边 u -> v:
        if (u 在 frontier 上，即 distances[u] == 当前层):
            distances[v] = 当前层 + 1; 加入新 frontier; break;   // 找到就退出
```

- 用 `g->incoming_starts / incoming_edges`（`graph.h` 里确实提供了入边表，还有 `incoming_begin/end/size` Getter）。
- **同步需求大幅下降**：每个 v 只由一个线程写，不需要 CAS（边界情况是同一 v 被两个不同 u 同时命中——但因为写的是同一个值 `当前层+1`，用一次 CAS 或直接写都安全，取决于你的实现）。
- **需要"未访问集合"的高效表示**：top-down 天然只在 frontier 上迭代，bottom-up 要扫全部未访问点（可以扫全部点然后 `if (distances[v] != -1) continue`，代价是 O(V) 的扫描；更好的做法是维护一个未访问列表）。

### 15.4 Part 3：hybrid 与切换阈值

- **frontier 小** → top-down 快（只扫少量点的出边）。
- **frontier 大** → bottom-up 快（此时大量点已访问，top-down 会重复扫已访问点的出边；bottom-up 只关心未访问点，且命中就 break）。
- 切换判据要用**测量的工作量**，不是凭感觉：比较 "frontier 的出边总数" 与 "未访问点的入边总数"，谁小用谁。
- **别忘了转换开销**：如果两种算法用了不同的 frontier 表示，切换时要转换，这笔成本要算进阈值里。

### 15.5 为什么不可能接近线性加速（writeup 必答）

三个原因，按量级排：

1. **不规则访存**：图的邻接访问是随机地址，cache 命中率低，**内存带宽/延迟主导**。
2. **度分布倾斜**：少数高度数顶点让负载严重不均（这是图上并行算法的通病）。
3. **同步开销**：每轮 BFS 结束都要隐式同步（frontier swap）；frontier 小时并行度也不够。

### 15.6 设计理念

同一个算法（BFS），**两种数据视角**（从 frontier 往外推 vs 从候选点往回看），在不同阶段各有优势——这是"**算法选择依赖数据状态**"的最佳范例，也是真实图计算系统（Ligra 等）的核心思想。它和 PA2 的"没有最好的调度器，只有最合适的调度器"是同一条原则。

## 12 课程讲座层：PA 没有覆盖的后半学期

> 5 个 PA 集中在学期前 2/3（L1–L13 的硬件阶梯）；**L14–L18 的共享内存深水区没有对应的 PA**——cache coherence、内存一致性、lock-free、事务内存。
> 但这一段恰好和 408 的**存储层次（03）、进程与线程（10）、同步与互斥（12）**直接相通，也是系统岗面试的高频区。
> 本节先给 18 讲的主线一张表，再把 PA 没考的三块展开到能答题的深度。依据：官方课程页每讲的主题描述 + 标准体系结构教科书内容（Hennessy & Patterson 第 5 章、C++ 内存模型标准）。

### 12.1 十八讲主线一张图

| 讲 | 主题 | 核心概念 | 对应 |
|---|---|---|---|
| L1 | Why Parallelism? Why Efficiency? | 三 theme、FAST != EFFICIENT、功耗墙与多核起源 | §1 |
| L2 | 现代多核处理器 I | 多核 / SIMD / 超线程三种并行形式 | PA1 |
| L3 | 多核 II + ISPC | latency vs bandwidth、抽象 vs 实现 | PA1、§3.1 |
| L4 | 平行化的思考流程 | 数据并行模型 vs 共享地址空间模型 | §2.3 |
| L5 | 优化 1：工作分配与调度 | 静态/动态分配、Cilk、**work stealing** | PA2、§12.2 |
| L6 | 优化 2：局部性与通信 | 消息传递、流水线、**提高算术强度**、缓解竞争 | §3.3、§12.3 |
| L7 | GPU 架构与 CUDA | SM、warp 调度、SIMT | PA3 |
| L8 | 数据并行思维 | map / reduce / scan / groupBy | §8（scan 暗线） |
| L9 | GPU 上的 DNN 推理 | conv→matmul、transformer、**层融合** | PA4、§9.8 |
| L10 | 硬件专用化 | 能效、DNN 加速器设计案例 | PA4 |
| L11 | 专用硬件的编程系统 | DSL 趋势 | NKI / Triton |
| L12 | 数据中心级 AI | serving、批处理、利用率 | §14 求职 |
| L13 | DSL 与 AI 驱动优化 | 自动调优（TVM 一族）、LLM 辅助 kernel 工程 | PA5 的 LLM 政策 |
| L14 | **Cache Coherence** | MSI / MESI、**false sharing** | §12.4 |
| L15 | **同步实现 + 内存一致性** | 锁的实现、relaxed consistency | §12.5 |
| L16 | **细粒度锁与 lock-free** | 单读写队列、lock-free 栈、**ABA 问题** | §12.6 |
| L17–18 | 事务内存 | STM / HTM、乐观并发 | §12.7 |

### 12.2 两个定量定律 + 两种调度（L5 的完整版）

**Amdahl 定律**（408 计算题口径）：

```
speedup = 1 / (s + (1 - s) / p)        s = 串行比例, p = 处理器数
```

直觉：**加核只能压并行部分，串行部分纹丝不动**。取 s = 0.25，则无论 p 多大，speedup 上限 = 1/0.25 = **4 倍**——串行四分之一的程序永远上不了 5 倍。反过来，想把上限提到 100 倍，串行比例必须压到 1% 以下。

**work-span 模型**（比 Amdahl 更贴并行程序本体）：

```
T_p <= W / p + D        W = 总工作量, D = 关键路径长(span), p = 处理器数
```

直觉：再多的核也逃不出**依赖链的长度** D。Mandelbrot 的"必须等最慢线程"（§6.1）、SIMD 的"gang 耗时 = 最慢 lane"（§3.3）、DAG 的"必须等前驱"（§7.3）全是这一项的具体化。**Amdahl 是 work-span 在"串行部分独占 D"时的特例。**

**两种调度器的对账**（L5 的 work stealing vs PA2 的原子计数器）：

- PA2 的做法 = **集中式就绪队列 + 原子计数器抢任务**：简单、负载均衡好，但所有线程都在同一个计数器上竞争（contention），核数多了会饱和。
- Cilk 的 work stealing = 每个 worker 一条**本地 deque**，自己从队头消费，空闲的去**别人队尾偷**：常态零通信，只在负载不均时才付偷的开销，伸缩性更好。
- 选择逻辑和 §3.5 完全一致：**没有最好的调度器，只有对这个负载特征最合适的**。核少 + 任务均匀 → 集中式够用；核多 + 不均 → stealing。

### 12.3 Roofline 模型（L6 的算术强度，画成一张图）

把 §3.3 那个"算力还是带宽"的判断公式化：

```
可达到性能 = min(峰值算力, 带宽 × 算术强度)        [FLOP/s]
算术强度 AI = 总 FLOP 数 / 总访存字节数            [FLOP/Byte]
屋脊点 ridge = 峰值算力 / 带宽                     [FLOP/Byte]
```

在 log-log 图上：x 轴是 AI，y 轴是性能——左边一条**斜率为带宽的斜线**（带宽墙），上面一条**水平线**（算力天花板），两者交点就是屋脊点。

拿 H100 估个数：FP16 Tensor Core 峰值约 10^15 FLOP/s，HBM 带宽约 3.3 x 10^12 Byte/s，屋脊点 ≈ **300 FLOP/Byte**。然后给三个 workload 定位：

| workload | AI（数量级） | 落点 | 结论 |
|---|---|---|---|
| saxpy | ~0.17（2 FLOP / 12 Byte） | 深埋带宽墙下 | 加核加算力都没用，只能减访存 |
| **LLM decode** | ~1（每 token 读全部权重、几乎不算） | 带宽墙下 | **"decode 是 memory-bound"的公式化答案**（面试原题） |
| 大 GEMM | 数百以上 | 算力平台上 | 优化方向是张量核心利用率（tiling、精度） |

**用法**：优化前先算 AI——落在左边的，减访存（fusion、tiling、量化）；落在右边的，提算力（占用率、精度、Tensor Core）。**方向搞反了，所有优化都是白干。** 这也是 §14.3 里 NCU 读法口诀背后的模型。

### 12.4 Cache coherence：MSI / MESI 与 false sharing（L14，408 交叉）

**问题**：每个核有自己的 cache，同一地址可能有多个副本——没有协议的话，核 1 写了自己的副本，核 2 还在读旧值。

**MSI 三态**（每 cache line 一个状态）：

- **M（modified）**：我改过，内存里是旧的，**全机只有我这份**
- **S（shared）**：我和别人都可能有，内容与内存一致，**谁都不能直接写**
- **I（invalid）**：我的副本作废，不能用

写一个 S 态的行，必须先在总线上**广播 invalidate**，把别人的 S 都打成 I，自己升级成 M——这就是"写要先发失效"的直觉：**别人手里的副本越多，写越贵**。

**MESI 加了 E（exclusive）**：干净地独占（只我读过、没改过、和内存一致）。意义：**从 E 升 M 是本地的，不发总线事务**——私有的读-改-写 workload 不再骚扰总线。

**false sharing（伪共享）**——协议机制直接制造的性能陷阱：

```
struct Counters { int c[8]; };        // 8 个 int = 32 Byte，同一 cache line
// 线程 t 只写 c[t]
```

八个线程写**不同的变量**，逻辑上零冲突；但这些变量挤在**同一条 64 Byte 的 cache line** 里——每次写都要 invalidate 别的核，line 在核之间**乒乓**，性能可以掉一个数量级。修复：

```
struct alignas(64) PaddedCounter { int c; char pad[60]; };   // 每个计数器独占一条 line
```

**与 408 的对应**：408 只到"多核 cache 一致性"的概念级；这里到协议与工程级。归档见 `co/03-05-Cache.md`。

### 12.5 内存一致性与 C++ memory_order（L15）

先分清两个被混用的词：

- **coherence**：**单个地址**上，所有处理器看到的写顺序一致（单地点顺序）。
- **consistency**：**不同地址**之间，读写全局顺序的约定（多地点顺序）。

SC（顺序一致）最直观但最贵：现代 CPU 都有写缓冲、store forwarding，天然是 **relaxed**——写操作可以先对自己可见。于是语言层面要给程序员一套围栏工具。C++ 的五档（从弱到强）：

| memory_order | 语义 | 典型用途 |
|---|---|---|
| `relaxed` | 只保证本变量的原子性，无顺序约束 | 统计计数器（biggraphs 的 frontier 计数就可以用它） |
| `acquire` | 后面的读写不许重排到本读之前 | 锁的取锁侧、flag 读取 |
| `release` | 前面的读写不许重排到本写之后 | 锁的放锁侧、flag 置位 |
| `acq_rel` | 读改写同时具备两者 | fetch_add 一类 |
| `seq_cst` | 全局总顺序，最贵（默认） | 双检查锁定等需要全序的场景 |

**经典坑：双检查锁定（DCLP）**。不用 `acquire/release` 去读 instance 指针时，指令重排可能让你**先看到非空指针、后看到未构造完的对象**。这不是理论问题，是每个 C++ 面试都爱问的实战题。

**与 PA2 的关联**：你调 `mutex` 的 lock/unlock，就是一次 acquire/release 对——所以"锁保护的数据不会观察到半成品状态"不是运气，是锁自带的围栏语义。PA2 里"条件变量必须配 while"（§7.2）也是同一讲的考点。

### 12.6 Lock-free 与 ABA 问题（L16）

**什么时候才考虑 lock-free**：锁竞争成为实测瓶颈、且读写模式简单（读多写少、栈/队列）。纪律是**先量测再上**——lock-free 正确性论证的难度是锁的十倍。

**单读单写队列（SPSC）**：一个生产者一个消费者，head 只由消费者写、tail 只由生产者写——**两个变量各归其主，天然无竞争**，连 CAS 都不用（配 acquire/release 即可）。这是"用所有权划分消灭同步"的教科书案例，和 §3.6 的"消除共享 > 加锁"是同一原则。

**lock-free 栈**（两条 CAS）：

```
push: node->next = head;  while (!CAS(&head, node->next, node)) retry;
pop :  next = head->next; while (!CAS(&head, head, next)) retry;
```

**ABA 问题**（pop 上的坑）：线程 1 读到 `head = A`，正要 CAS；此时线程 2 pop 掉 A、push 了 B、又**把 A 的地址重新 push 回来**。线程 1 的 CAS 检查"head 还是 A 吗"——是！成功。但此时 `A->next` 已经不是原来那个值了，拿到的可能是**悬垂指针**。CAS 只认值，不认"中间发生过什么"。

修复思路：**tagged pointer**——指针带上版本号，`{A, v1}` 和 `{A, v2}` 是不同的值，中间的变化骗不过 CAS。工业实现里还有 hazard pointer / epoch reclamation 一整族方案（面试说出名字即可）。

### 12.7 事务内存（L17–18，了解即可）

思路转变：锁是**悲观**并发（先占住再干活，死锁四条件随之而来）；事务是**乐观**并发（直接干，冲突了回滚重来）。

- **HTM**（硬件事务内存）：Intel TSX 指令集（后来在部分 CPU 上因安全漏洞被禁用了）、IBM z 系列仍在用。
- **STM**（软件事务内存）：库层面实现，开销大但可移植。

为什么它没统治世界：事务有**容量限制**（cache 装得下才 tracked得住）、**best-effort**（可能任意失败，必须保留锁的 fallback 路径）——于是复杂度两头都付。但它留下的遗产很实在：**数据库的 MVCC、Rust 的借用检查思路、无锁数据结构的设计直觉**都受益于"乐观并发"这个视角。

### 12.8 一页纸术语卡（全课概念速查）

| 术语 | 一句话定义 | 出现处 |
|---|---|---|
| arithmetic intensity | 总 FLOP / 总访存字节，决定优化方向 | §3.3、§12.3 |
| roofline / ridge point | 带宽墙与算力平台的交点；AI 在左边看带宽、右边看算力 | §12.3 |
| Amdahl 定律 | speedup = 1/(s + (1-s)/p)，串行比例钉死上限 | §12.2 |
| work / span | 总工作量 / 关键路径长；T_p <= W/p + D | §12.2 |
| work stealing | 本地 deque 自消费 + 空闲者从队尾偷 | §12.2 |
| divergence | 一个 gang/warp 内 lane 分支不同步，耗时 = 最慢 lane | §3.3 |
| oversubscription | 线程数 > 执行上下文，只增调度开销 | §6.1 |
| occupancy | SM 上活跃 warp / 上限；受寄存器与 shared memory 限制 | §14.3.1 |
| coalescing | warp 访问连续地址合并成一次事务；散乱访问带宽掉到 1/32 | §14.3.1 |
| bank conflict | shared memory 32 bank 同 bank 不同地址被串行化；padding 修复 | §14.3.1 |
| MFU | 实测 FLOP / 硬件峰值 FLOP，加速器的效率尺子 | §9.8 |
| false sharing | 不同变量挤同一 cache line，写互相 invalidate，line 乒乓 | §12.4 |
| MSI / MESI | cache line 的一致性状态机；E 的意义是私有写不发总线 | §12.4 |
| coherence vs consistency | 单地址顺序 vs 跨地址全局顺序 | §12.5 |
| acquire / release | 一对单向围栏：锁语义的最小构件 | §12.5 |
| ABA | CAS 只认值不认历史；tagged pointer 修复 | §12.6 |
| SPSC 队列 | 单读单写、所有权划分、零原子冲突 | §12.6 |
| kernel fusion | 多算子并一个，收益 = 省掉的 HBM 往返 | §9.8 |
| online softmax | running max/sum 增量归一化，整行不必驻留 | §10.1 |

### 12.9 自由发挥：从 ISPC 到 Triton——SPMD 的三次转世

这是全课我最想让你带走的一条**隐线**：三个相差十几年的编程系统，暴露给你的其实是同一副骨架：

| | ISPC（2010s） | CUDA（2007） | Triton（2021） |
|---|---|---|---|
| 执行单元编号 | `programIndex`（gang 内 lane） | `threadIdx` / `blockIdx` | `tl.program_id`（一个 program = 一个 tile） |
| 声明独立性 | `foreach` / `launch[N]` | kernel 启动网格 | block 网格 + `tl.load(mask=...)` |
| 尾部处理 | mask 寄存器 | predication（warp 内掩码） | `mask` 参数 + `other=` 填充值 |
| 硬件真身 | SIMD lane | warp（32 线程 lockstep） | warp + shared memory tiling |
| 程序员写 | 逐 lane 逻辑 | 逐 thread 逻辑 | 逐 tile 逻辑 |

三层抽象一层比一层粗（lane → thread → tile），**但每一层都在做同一件事：把"哪些计算互相独立"声明出来，把"怎么映射到执行单元"留给系统**。所以：

- 你在 prog2 里练的**掩码思维**，就是 Triton 里 `tl.load(ptr, mask=...)` 的直接前置；
- 你在 PA3 里对 block/shared memory 建立的直觉，就是读 Triton FlashAttention 前向那 30 行代码的全部前置；
- 你在 PA4 里对 tile + DMA 的理解，是理解"为什么 Triton 在 tile 层抽象上能自动管好 shared memory"的钥匙。

**学完 CS149 再去读一个 Triton kernel，你看到的不是新语言，是老朋友换了件衣服。** 这也是 §14.6 补课路线把 Triton 放在前面的原因——它不是新知识，是复习。

## 13 复习验收清单（自测用）

每个 PA 过完，试着**不看笔记**回答下面这些问题；答不上来就回对应章节。

**PA1**
1. 为什么 mandelbrot 按连续块切分时 3 线程那个点特别差？交织分配为什么不需要任何同步？
2. 为什么 16 线程不会比 8 线程快？
3. 同一个 gang 里 lane 的迭代次数不同，对耗时的精确影响是什么？
4. saxpy 每 3 个元素 2 次运算，为什么"改到近线性加速"是不可能的？`TOTAL_BYTES` 里为什么乘 4？
5. kmeans 的热点为什么是 `computeAssignments`？为什么骨架按 k 切分是错的？

**PA2**
1. `run()` 返回时，"队列为空" 和 "已完成计数 == 总数" 哪个才是正确判据？为什么？
2. 主线程在 `run()` 里自旋会怎样伤害 worker？
3. 条件变量为什么必须放在 `while` 里等？
4. 依赖是任务级还是 launch 级？launchA 结束后 launchB 和 launchC 之间是什么关系？
5. `super_super_light` 上为什么串行版能赢？

**PA3**
1. 骨架错在哪两处？为什么"顺序只约束同一像素"这句话是优化空间的来源？
2. 为什么建议先解决 order 再考虑 atomicity？
3. shared-memory scan 的三条硬性要求是什么？2D 线程下标为什么必须 `threadIdx.y * blockDim.x + threadIdx.x`？
4. `micro2M`（200 万个极小圆）为什么逼着你换并行轴？
5. `cudaMalloc` 失败了你会看到什么？（答案：什么都不看到——所以它必须被包起来）

**PA4**
1. SBUF / PSUM / HBM 的容量与角色？为什么说 Trainium 的存储是 software managed？
2. `nc_matmul` 的三个 tile 上限？左操作数为什么要转置？
3. partition 维 P 的上限是多少、必须是第几维？
4. 融合 conv+maxpool 到底省了什么？（答案：一次 HBM 往返，不是算力）
5. 循环排序的两条原则是什么？

**PA5**
1. 给出一组 NCU 数字（Compute 18%、DRAM 4.5%、SM Busy 31%），瓶颈是什么？
2. work log 的每一步要写哪六项？

**biggraphs**
1. 为什么"先读一次再决定是否发 CAS"是安全的？
2. top-down / bottom-up 各自在什么 frontier 规模下占优？阈值该怎么定？

**课程后半场（§12，面试 + 408 双考点）**
1. 串行比例 s = 0.25 的程序，核数趋于无穷时加速比上限是多少？想把上限提到 100 倍，s 必须压到多少以下？
2. work-span 模型里 D 是什么？mandelbrot 的"等最慢线程"和 SIMD 的"最慢 lane"分别是 W/p 和 D 里的哪一项造成的？
3. H100 的屋脊点大约在多少 FLOP/Byte？LLM decode 的算术强度是多少、落在墙的哪一侧？——这道题的公式化答案是什么？
4. MESI 比 MSI 多出的 E 态，省掉了哪一类总线事务？
5. 八个线程写同一 cache line 里的八个不同 int，为什么性能崩？怎么修？
6. coherence 和 consistency 的区别是什么？DCLP 在没有 acquire/release 时会坏在哪一步？
7. ABA 问题为什么骗得过 CAS？tagged pointer 是怎么堵住它的？

## 14 求职视角：CS149 能兑换成什么（2026-10 市场快照）

> 素材来源：① 腾讯 / 商汤 / 清昴智能 2026 年国内在招 JD（异构推理调优、国产芯片推理优化）
> ② NVIDIA / Fireworks / Together / OpenAI / Anthropic 的公开面试题库 ③ PA5 handout 自带的论文与讲义链接。
> 本节回答一个问题：**这门课学的东西，在招聘市场上对应哪些岗位、面试怎么考、简历怎么写。**

### 14.1 岗位地图：五个 PA 各自对口什么

| 方向 | 代表雇主（国内 / 海外·开源） | 对口 PA | JD 关键词 |
|---|---|---|---|
| **CUDA / Kernel 工程** | 腾讯、字节、DeepSeek、摩尔线程、沐曦 ／ NVIDIA、OpenAI(Triton) | PA3 + PA5 | CUDA C/C++、warp primitives、coalescing、occupancy |
| **AI Infra / 推理优化** | 商汤、清昴智能、各大模型厂 ／ Fireworks、Together、vLLM/SGLang 生态 | PA4 + PA5 | vLLM/SGLang/TensorRT-LLM/MindIE、KV Cache、PagedAttention、量化 |
| **国产芯片算子** | 华为昇腾(CANN/AscendC)、寒武纪(BangC)、沐曦(MACA)、燧原 | PA4（概念直接迁移） | 软件管理存储、tiling、算子融合——**就是 NKI 那套思路** |
| **性能工程 / 系统工程** | 各大厂基础架构 ／ Meta、Google | PA1 + PA2 | profiling、调度器、并发库（TBB 一族） |
| **图形学** | 游戏与渲染公司 | PA3（A-over-B 混合、order 问题） | 半透明合成、并行渲染 |

一个值得注意的事实：**腾讯 2026 年的推理调优 JD 里明确写着「CUDA、Triton、TileLang、AscendC、BangC 至少一种，两种以上优先」**——其中 CUDA / Triton / TileLang 三样正是 CS149 PA5 允许的提交语言。这门课的作业选型就是照着业界口味设计的。

### 14.2 JD 硬技能清单：CS149 覆盖了什么、缺什么

**已覆盖**（可以直接写进简历技能栏）：

- CUDA 编程模型（grid/block/thread/warp、shared memory、`__syncthreads`）
- 并行 prefix-sum / reduction / histogram / tiled GEMM / transpose（面试手写五大件，全在 PA3+PA5）
- roofline 判断：compute-bound vs memory-bound（§3.3，**这是所有 JD 的第一道隐形门槛**）
- profiler 驱动的优化循环（NCU 指标读法，§10.3）
- kernel fusion 的收益本质（§9.8：省 HBM 往返）
- FlashAttention 的三件套：tiling + fusion + online softmax（§10.1）
- 线程池 / 条件变量 / 原子操作 / CAS（PA2，系统岗 coding 必考）
- DAG 任务调度（= TBB / Spark / PyTorch 调度器的同构问题）

**未覆盖**（求职前要另补，按优先级）：

1. **Transformer 推理栈**：KV Cache 的内存账、PagedAttention、continuous batching、PD 分离（prefill 算力受限 / decode 带宽受限）→ 读 vLLM 论文（Kwon et al., 2023）
2. **分布式**：TP/PP/EP、NCCL、ring all-reduce、ZeRO/FSDP → 分布式训练是另一门课的量
3. **量化**：FP8/INT8/W4A16 的精度-吞吐权衡
4. **Tensor 底层**：mma PTX、WMMA、CUTLASS
5. **host 侧**：CUDA stream、pinned memory、NCCL 集合通信

### 14.3 面试题对照表：CS149 学的 vs 面试问的

把公开面试题库里的真题和本笔记的章节一一对上——**你会发现 CS149 的考点覆盖率惊人地高**：

| 面试真题（出处） | 对应本笔记 |
|---|---|
| 手写 reduction / tiled matmul / transpose / histogram / scan（NVIDIA 经典 coding 五件套） | §8.5 + §10.1（scan 在 PA3、histogram 在 PA5） |
| "What is memory coalescing and why does a strided access hurt?"（NVIDIA/Fireworks） | §14.3.1（见下，面试高频但课程没细讲，这里补） |
| "Explain shared memory bank conflicts with the bank arithmetic, fix with padding"（NVIDIA/Together） | §13.3.1 |
| "Explain occupancy and register pressure: why can 50% occupancy beat 100%?"（NVIDIA） | §13.3.1 |
| "Explain FlashAttention. Why is it called IO-aware, what does it actually save?"（Fireworks/Together/Anthropic） | §10.1 |
| "Here is an Nsight Compute report for a slow kernel. Name the bottleneck."（NVIDIA/Fireworks） | §10.3 的读法口诀 |
| "Why fuse kernels, how much does it save, and what can fusion NOT fix?"（Fireworks/Together/OpenAI） | §9.8 |
| "Implement a request scheduler with priority and preemption"（面试 coding） | §7（PA2 的 ready queue + 依赖计数就是它的骨架） |
| "Why is decode memory-bound and prefill compute-bound?" | §3.3 算术强度：decode 每 token 读全部权重、几乎不算 |
| "What is MFU, how do you compute it?"（Meta/Google/Anthropic） | §9.8 |
| "Sum 100 million floats as fast as the hardware allows. Justify each step."（NVIDIA） | §2.3 四步循环 + reduce 的树形结构 |

#### 14.3.1 三个面试高频、课程没细讲的点（补齐）

**① Memory coalescing（合并访问）**
一个 warp 的 32 个线程访问**连续**地址时，内存控制器可以用一次 128-byte cache line 事务服务全部请求；访问散乱/跨步时最多要 32 次事务，有效带宽掉到 1/32。对策：数据结构用 **SoA**（array of structs → struct of arrays）、tile 按 cache line 对齐。面试追问形态：给你一组线程的地址，让你判断 coalesced / strided / random。

**② Shared memory bank conflict**
shared memory 物理上分 **32 个 bank**（按 4-byte 交错）。同一 warp 里多个线程访问**同一 bank 的不同地址** → 访问被串行化；访问**同一地址**是 broadcast，不冲突。经典修复：给 tile 加一列 padding（如 `[32][33]`），错开 bank。面试常给一个具体 kernel 让你算 bank 编号。

**③ Occupancy（占用率）与寄存器压力**
occupancy = 每个 SM 上活跃 warp 数 / 上限。寄存器用得多 → 每线程占的硬件资源多 → 并发 warp 变少。**为什么 50% occupancy 可能比 100% 快**：寄存器多意味着更多数据留在寄存器里（少跑 memory），ILP 更好；满 occupancy 但每线程只分到很少寄存器反而带宽受限。用 `__launch_bounds__` 控制。这与 §10.3 那组 NCU 数字（Compute 18% + SM Busy 31% → 并行度不足）是同一件事的两面。

### 14.4 简历写法：把 PA 变成 bullet

**前提先说清**：目前 `parallel-cs149` 里没有任何实现——**没做掉的 PA 不能写**。下面这些模板是"做掉之后"怎么写。

原则：**动词 + 系统 + 关键技术决策 + 量化结果**。每一句都要有一个数字和一个决策，光有数字没决策是流水账，光有决策没数字是PPT。

```
PA2（调度器）：
  Implemented a C++ task-execution library supporting synchronous bulk launch and
  async DAG scheduling (runAsyncWithDeps/sync) with spinning and sleeping thread
  pools; matched the staff reference implementation within 20% across 11 workloads
  including imbalanced-task and fan-in/fan-out dependency graphs.

PA3（渲染器）：
  Built a CUDA renderer satisfying atomicity and per-pixel ordering invariants via
  per-tile circle culling with shared-memory prefix-sum compaction; achieved
  T <= 1.2x staff reference on all 8 scenes (incl. 2M-circle micro2M).

PA5（开放优化）：
  Optimized a FlashAttention-style kernel on H100 using Triton through NCU-guided
  iterations (occupancy, coalescing, online-softmax register pressure);
  X ms -> Y ms, Zx over the PyTorch baseline.
```

中文简历同理，套这个结构。**PA2 那条最有系统岗含金量**（调度器 + 同步原语 + 性能对比），**PA5 那条最有 infra 含金量**（H100 + NCU + 具体优化手段）。

### 14.5 面试讲故事的骨架

面试官要的不是"我做完了"，是"你怎么想的"。PA5 的 work log 四步循环**天然就是 STAR**：

- **S/T**：baseline 是什么、目标是什么
- **A**：测到了什么（NCU 数字）→ 猜瓶颈是什么（假设）→ 改了什么（验证）
- **R**：数字变化 + 为什么停（profile 显示还有没有空间）

经典句式（面试题库原话的形态）：*"the kernel went from 12 ms to 3 ms because ..."* —— **因为什么**比**变成多少**重要。准备两三个这样的故事，每个都带数字。

### 14.6 补课路线（CS149 之后接什么）

按性价比排：

1. **FlashAttention 论文 + UW 讲义**（PA5 README 里就有链接：arXiv 2205.14135；`courses.cs.washington.edu` 的 from-online-softmax-to-flashattention 讲义）—— 一次把 attention 优化讲透
2. **vLLM 源码 + PagedAttention 论文**（Kwon et al., 2023）—— KV Cache / continuous batching / PD 分离全在这
3. **GPU MODE（原 CUDA MODE）社区讲座** —— 业界 kernel 工程师的一线实战，节奏是每周一个具体 kernel 的优化复盘
4. **KernelBench 式练手**：拿 PyTorch 算子写 CUDA/Triton 对拍优化，产出可以直接进作品集
5. **CMU 15-418**（CS149 的 CMU 姊妹课）—— 想补理论体系时回去翻
6. 国内向：**MindIE / AscendC 文档**（昇腾）、各家国产芯片编程栈——概念与 NKI 同构（软件管理存储 + tile + DMA），迁移成本低

一句话：**CS149 给你的是"方法论 + 五个可量化的项目"；市场要的是"方法论 + Transformer 推理栈的领域知识"。前者已经在这份笔记里，后者按上面顺序补。**

## 15 一句话总结

**CS149 的全部作业都在练同一件事：拿到一段代码 + 一台机器，判断它离"这台机器的上限"还有多远、差在哪一步，然后用最小的改动把它推近。** 语言（ISPC/CUDA/NKI）和硬件（CPU/GPU/Trainium）都只是这道题的换皮版本。

---

## 迁移归档：来自旧 ipynb 的工程笔记（2026-10-28）

## [CS149] 并行计算的效率观：FAST 不等于 EFFICIENT

> 2026-10-22 · 来源：CS149 项目复习（真源 `projects/cs149.md`）

- **FAST != EFFICIENT**：在 10 个核上拿到 2 倍加速只说明程序变快了，硬件用得好不好是另一回事。整门课都在考这个区分。
- **三个性能敌人**：① 负载不均（静态分块遇上代价不均的工作）② SIMD divergence（一个 gang 的耗时 = 最慢 lane 的耗时）③ 算术强度太低（如 saxpy 每 3 个元素只做 2 次运算 → 带宽受限，加核救不了）。
- **判断瓶颈是算力还是带宽**是并行优化的第一基本功；工具形态随硬件升级：CPU 计时器 → GPU 的 NCU 报告 → 加速器的 MFU。
- **存储层次的控制权**：CPU cache 由硬件管 → GPU shared memory 由程序员声明 → Trainium 的 SBUF/PSUM 要显式 DMA。越往上，程序员越要为数据布局负责。
- **正确性的两条不变式**：原子性（读-改-写不可分）+ 顺序（对同一位置的更新必须按输入序）。关键洞察：**顺序只约束同一个位置**，不重叠的部分完全自由 —— 并行度就藏在这句话里。
- **优化四方向**：增加并行度 / 减少通信 / 隐藏延迟 / 缓解竞争。任何一次「改快了」都要能归到其中之一。

---

## [CS149] 并行性能的三个定量工具：Amdahl、work-span、roofline

> 2026-10-22 · 来源：CS149 项目复习（真源 `projects/cs149.md`）

- **Amdahl 定律**：speedup = 1 / (s + (1-s)/p)。串行比例钉死加速比上限 —— s=0.25 时核数再多上限也是 4 倍；想提到 100 倍，s 必须压到 1% 以下。（408 计算题口径）
- **work-span 模型**：T_p <= W/p + D。D 是关键路径长 —— 依赖链的长度，加核逃不出它。Amdahl 是「串行部分独占 D」的特例。
- **roofline**：可达到性能 = min(峰值算力, 带宽 x 算术强度)。屋脊点 = 峰值算力/带宽（H100 FP16 约 300 FLOP/Byte）。**AI 落在墙左看带宽（fusion/tiling/量化），落在墙右看算力（占用率/Tensor Core）—— 方向搞反，优化全白干。**
- **LLM decode 为什么 memory-bound 的公式化答案**：decode 每 token 读全部权重、几乎不算，算术强度约 1 FLOP/Byte，深埋带宽墙下。

---

## [CS149] 多核 cache 一致性：MSI/MESI 与 false sharing

> 2026-10-22 · 来源：CS149 项目复习（真源 `projects/cs149.md`）

- **MSI 三态**：M（改过、全机唯一）/ S（与内存一致、可多副本、不能直接写）/ I（作废）。写 S 态必须先广播 invalidate —— **别人手里的副本越多，写越贵**。
- **MESI 的 E 态**：干净独占（只我读过、未改、与内存一致）。**E 升 M 是本地事务、不发总线** —— 私有的读-改-写不再骚扰总线，这就是加 E 的全部意义。
- **false sharing（伪共享）**：不同变量挤同一 64B cache line，各核写各自的变量，逻辑零冲突，但每次写都互相 invalidate，line 在核间乒乓，性能可掉一个数量级。修复：alignas(64) 或 padding 让每个热点变量独占一条 line。
- 与 408 的关系：408 只考到「多核 cache 一致性」概念级；协议级（MSI/MESI 状态转换）与工程级（false sharing 定位与修复）是 CS149 L14 的内容。

---

## [CS149 · PA2] 自己写线程池：三种调度的同步设计

> 2026-10-22 · 来源：CS149 项目复习（真源 `projects/cs149.md`）

- **三种任务系统演进**：每次 run() 都建线程（开销主导，轻负载反而可赢）→ 线程池 + 自旋（延迟低但空占执行资源）→ 线程池 + 条件变量休眠（省资源，需处理唤醒开销）。
- **条件变量纪律**：必须在 `while` 循环里等条件（防虚假唤醒；条件可能在你拿到锁之前已被别的线程满足），判断前先拿锁。
- **「任务完成」的判定用计数，不用队列空**：队列空只说明任务被领走，可能还在执行。用「已完成计数 == 本批总数」，由最后一个完成的线程 notify 主线程。
- **主线程也在抢核**：run() 里自旋等待会占掉一个执行上下文，直接拖慢 worker —— 主线程也该睡。
- **原子 vs 锁**：动态抢任务用原子计数器即可，无需互斥锁；biggraphs 的 BFS 用 compare-and-swap（先读一次、明显会失败就不发 CAS，因为 dist 只会从 -1 变正数不会变回来）。
- **DAG 依赖调度**：等待集合 + 就绪队列双结构，每个 launch 记剩余任务数，归零时给后继的入度减一，入度归零推入就绪队列 —— TBB / Spark / PyTorch 调度器的同构问题。

---

## [CS149] 内存一致性与 lock-free：acquire/release、ABA

> 2026-10-22 · 来源：CS149 项目复习（真源 `projects/cs149.md`）

- **coherence vs consistency**：coherence 管「单个地址」上所有核看到的写顺序；consistency 管「跨地址」的全局读写顺序约定。两回事，别混用。
- **C++ memory_order 五档**：relaxed（只保证原子性）/ acquire + release（一对单向围栏，锁的最小构件）/ acq_rel / seq_cst（全局总序，最贵，默认）。**经典坑：双检查锁定（DCLP）不用 acquire/release 时，可能先看到非空指针、后看到未构造完的对象。**
- **mutex 自带 acquire/release 语义** —— 锁保护的数据不会观察到半成品，不是运气，是围栏。
- **SPSC 队列**：单生产者单消费者，head/tail 各归其主，所有权划分消灭同步，连 CAS 都不用 —— 「消除共享 > 加锁」的教科书案例。
- **ABA 问题**：CAS 只认值不认历史 —— pop 时 head 从 A 走到 B 又回到同地址的 A2，CAS 骗过、拿到悬垂指针。修复：tagged pointer（指针带版本号）；工业级还有 hazard pointer / epoch reclamation。
- **纪律**：lock-free 是最后手段，先量测锁竞争是否真是瓶颈，再上；正确性论证难度是锁的十倍。

---

## [CS149 · biggraphs] 并行 BFS 的三种形态

> 2026-10-22 · 来源：CS149 项目复习（真源 `projects/cs149.md`）

- **top-down**：遍历 frontier 里每个点的出边，遇到未访问点就设距离并加入新 frontier。frontier 小时最快。
- **bottom-up**：每个未访问点检查自己的入边，看有没有邻居在 frontier 上，命中即退出。frontier 大时最快（避免重复扫已访问点的出边）。
- **hybrid**：按工作量动态切换 —— 比较「frontier 的出边总数」与「未访问点的入边总数」，谁小用谁；切换阈值要算上两种 frontier 表示之间的转换开销。
- **同步**：用 compare-and-swap（`__sync_bool_compare_and_swap`）远快于 `#pragma omp critical`。技巧：先读一次判断，明显会失败的就不发 CAS（因为 dist 只会从 -1 变正数，不会变回来，所以读到的非 -1 一定失败）。
- **为什么图算法拿不到线性加速**：不规则访存（cache 命中率低）+ 度分布倾斜（少数高度数点造成负载不均）+ 每轮 BFS 结束时的隐式同步。

---
