> **双语对照版**：英文原段 → 紧随其后的中文译文（引用块，前缀 `译：`）；每节末附该节生词表。术语首次出现保留英文原词，方便对照阅读与翻译练习。

## 1. What It Is Doing

Break the statement “parallelism can accelerate” into a string of reproducible numbers, and explain clearly where each number comes from.

> 译：把“并行（parallelism）能够加速（accelerate）”这一说法拆解成一串可复现（reproducible）的数字，并清楚地解释每个数字从何而来。

The input is a fixed set of workloads (vector addition, dot product, reduction, matrix multiplication, stencil) plus a configuration: size N, backend (scalar, SIMD, multithreading, GPU), number of threads, number of repetitions, and whether to pin cores. The output is three things: a speedup table with jitter intervals; a curve of speedup versus N (not a single point); and an attribution explanation for each speedup—how much of this 6× comes from vector width, how much from the number of cores, and how much is eaten by memory bandwidth or copy overhead.

> 译：输入是一组固定的工作负载（workload）（向量加法（vector addition）、点积（dot product）、归约（reduction）、矩阵乘法（matrix multiplication）、模板计算（stencil））加上一个配置：规模 N、后端（backend）（标量（scalar）、SIMD、多线程（multithreading）、GPU）、线程数、重复次数，以及是否绑定核心（pin cores）。输出是三样东西：一张带抖动区间（jitter intervals）的加速比（speedup）表；一条加速比随 N 变化的曲线（不是一个单点）；以及对每个加速比的归因（attribution）解释——这个 6× 中有多少来自向量宽度（vector width），有多少来自核心数，有多少被内存带宽（memory bandwidth）或复制开销（copy overhead）吃掉。

Acceptance looks like this: on another machine of the same architecture, someone else using the same configuration can produce numbers that fall within your error bars; pick any speedup in the table, and you can point to the code and hardware counters and explain clearly how it came about; deliberately shrink N until everything fits in L1, and the curve shape must change as expected. If any one of these three is missing, the numbers are just numbers.

> 译：验收（acceptance）看起来是这样的：在同一架构（architecture）的另一台机器上，另一个人使用相同配置能够产生落在你的误差棒（error bars）范围内的数字；从表中任选一个加速比，你都能指向代码和硬件计数器（hardware counters），并清楚地解释它是怎么产生的；故意把 N 缩小到所有东西都能放进 L1，曲线形状必须如预期那样改变。这三者中只要缺少任何一个，数字就只是数字。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| parallelism | n. | 并行 | parallelism can accelerate |
| reproducible | adj. | 可复现的 | reproducible numbers |
| accelerate | v. | 加速 | parallelism can accelerate |
| jitter | n. | 抖动 | jitter intervals |
| attribution | n. | 归因 | attribution explanation |
| stencil | n. | 模板计算 | matrix multiplication, stencil |
| acceptance | n. | 验收 | Acceptance looks like this |
| error bars | n. | 误差棒 | within your error bars |
| hardware counters | n. | 硬件计数器 | code and hardware counters |

## 2. Why Do It This Way (Functional Design)

This section describes several key trade-offs: which off-the-shelf components are replaced, at which layer the replacement happens, and why it is worth paying this cost.

> 译：本节描述若干关键权衡：替换哪些现成组件，替换发生在哪一层，以及为什么值得付出这一代价。

**(1) Replace compiler auto-vectorization with hand-written SIMD.** The replacement layer is the workload’s backend implementation, not the compiler-option layer. Whether `-O3 -march=native` actually vectorizes, and which loop it vectorizes, depends on the compiler version, loop shape, and alias analysis; you cannot point to a line in the report and say “these 8 floats are consumed by one instruction.” After hand-writing intrinsics, three things that the compiler used to do for you must be implemented yourself: 64-byte-aligned allocation and tail handling (N is rarely an integer multiple of the vector width), vectorized rewriting of branches (`if` causes lanes to diverge, so either rewrite as select/blend or partition first and then compute), and reduction order (floating-point addition is not associative; changing the summation order changes the result, so checksums must have tolerance rather than equality comparison). The cost is direct: the code size is three to five times that of scalar, and changing the instruction set requires rewriting it, so do only two workloads, not all of them.

> 译：**（1）用手写 SIMD 替换编译器自动向量化。** 替换层是工作负载的后端实现，而不是编译器选项层。`-O3 -march=native` 是否真的实现了向量化、以及它对哪个循环做了向量化，取决于编译器版本、循环形状和别名分析；你无法指着报告中的某一行说“这 8 个浮点数由一条指令消费”。手写 intrinsics 之后，编译器以前替你做的三件事必须自己实现：64 字节对齐分配与尾部处理（N 很少是向量宽度的整数倍）、分支的向量化改写（`if` 会导致 lane 分叉，要么改写为 select/blend，要么先分区再计算）、以及归约顺序（浮点加法不满足结合律；改变求和顺序会改变结果，因此校验和必须带容差而非用相等比较）。代价很直接：代码规模是标量的三到五倍，而且更换指令集就需要重写，所以只做两个工作负载，不要全部都做。

**(2) Take timing and scheduling back from the operating system.** This layer is the harness. Core pinning is not an optimization technique but a measurement precondition—threads migrating between cores carry cache away, and jitter can reach 30%. After warming up several times, discard those runs, repeat R times, and take the median and interquartile range rather than the mean or minimum. Unreliability has several clear sources: frequency and turbo, thread migration, remote NUMA access, background load, and hot/cold caches. The way to suppress it is not “run it a few more times,” but to turn off or fix each source individually. Why not use an off-the-shelf framework such as Google Benchmark: it does not give you core pinning, does not give you uniform CSV fields, and does not give you statistical conventions aligned with Amdahl fitting. The cost is that bugs in the harness itself will contaminate all data, so first take a purely serial function and test it repeatedly, confirm that the harness’s own jitter is within 2%, and only then measure parallel.

> 译：**（2）从操作系统手中收回计时与调度权。** 这一层是测试框架（harness）。核心绑定（core pinning）不是一种优化技术，而是测量的前提条件——线程在核心之间迁移会带走缓存，抖动可达 30%。预热若干次后，丢弃这些运行，重复 R 次，取中位数和四分位距，而不是均值或最小值。不可靠性有几个明确的来源：频率与睿频、线程迁移、远程 NUMA 访问、后台负载，以及热/冷缓存。压制它的办法不是“再多跑几次”，而是逐一关闭或固定每个来源。为什么不用 Google Benchmark 这类现成框架：它不给你核心绑定，不给你统一的 CSV 字段，也不给你与 Amdahl 拟合对齐的统计约定。代价是测试框架自身的 bug 会污染所有数据，所以先用一个纯串行函数反复测试，确认框架自身的抖动在 2% 以内，然后再测量并行。

**(3) Change testing from “one point” to “one curve.”** Input arrays are uniformly 64-byte aligned, and N is swept from fitting in L1 all the way to far beyond LLC. An isolated 6× carries no information—it could come from the number of cores, or it could simply be because the data was already entirely in cache. Only when you see speedup drop as N crosses the L1/L2/LLC boundaries can you separate the two causes “multicore parallelism” and “memory bandwidth.” The cost is that the test matrix expands into backend × N × thread count × repetition count, so the time per run must first be reduced to the second level; otherwise one sweep cannot be completed.

> 译：**(3) 将测试从“单点”改为“单曲线”。** 输入数组统一按 64 字节对齐，N 的扫描范围从能放进 L1 一直到远超 LLC。孤立的 6× 不携带任何信息——它可能来自核心数，也可能仅仅是因为数据已经完全在缓存中。只有当看到加速比在 N 越过 L1/L2/LLC 边界时下降，你才能区分“多核并行”和“内存带宽”这两个原因。代价是测试矩阵会扩展为后端 × N × 线程数 × 重复次数，因此每次运行的时间必须先降到秒级；否则一次扫描无法完成。

**(4) False-sharing experiments must use raw threads, not OpenMP.** OpenMP’s `reduction` and scheduling policies hide the data layout, while the entire requirement of a false-sharing experiment is that you can precisely control “whether two variables written by two threads fall on the same 64-byte cache line.” The approach is that the control group and the fixed group differ only by one `alignas(64)` or padding, with everything else identical. There is a real pitfall here: the compiler may hoist the accumulator variable in the loop into a register, so no memory write occurs at all, and the experiment “cannot detect false sharing.” Either add `volatile`, or force a write-back on every iteration, and acknowledge in the report that this phenomenon is constructed and what the construction conditions are.

> 译：**(4) 伪共享（false-sharing）实验必须使用原生线程（raw threads），而不是 OpenMP。** OpenMP 的 `reduction` 和调度策略隐藏了数据布局，而伪共享实验的全部要求正是你能精确控制“两个线程写入的两个变量是否落在同一条 64 字节缓存行（cache line）上”。做法是：对照组和固定组只相差一个 `alignas(64)` 或填充（padding），其他一切都相同。这里有一个真实的陷阱：编译器可能把循环中的累加器变量提升到寄存器中，于是根本不会发生内存写入，实验也就“无法检测到伪共享”。要么加上 `volatile`，要么在每次迭代时强制写回，并在报告中说明这一现象是构造出来的，以及构造条件是什么。

**(5) GPU does only end-to-end accounting, not extreme tuning.** The GPU backend is isomorphic to the CPU backend; both implement the same `run(config)` interface, but timing is split into four segments: allocation, H2D copy, kernel, and D2H copy-back. The reason is: what needs to be demonstrated here is “how much of that 10× is eaten by copy and launch overhead,” not to chase a higher 10×. Choosing CUDA over OpenCL is purely a matter of environment maturity. The cost is that a GPU is required; if one is unavailable, degrade to “read the kernel code + do the accounting with CPU-side data,” with acceptance downgraded but not broken.

> 译：**(5) GPU 只做端到端核算，不做极限调优。** GPU 后端与 CPU 后端同构；两者实现相同的 `run(config)` 接口，但计时被拆成四段：分配、H2D 拷贝、内核和 D2H 拷回。原因是：这里需要展示的是“那个 10× 中有多少被拷贝和启动开销吃掉”，而不是追求更高的 10×。选择 CUDA 而非 OpenCL 纯粹是环境成熟度的问题。代价是需要一块 GPU；如果没有 GPU，就降级为“阅读内核代码 + 用 CPU 侧数据做核算”，验收标准降级但不中断。

**(6) Why not use an easier approach.** The easiest thing is to run a few off-the-shelf benchmarks and copy their conclusions. The cost is: you cannot answer “where does this 6× come from,” and you cannot reproduce it on another machine. The entire output of this project is attribution capability, so the three things—timing, correctness checking, and configuration recording—must be kept in your own hands and cannot be outsourced.

> 译：**（6）为什么不采用更简单的做法。** 最简单的事情就是跑几个现成的基准测试（benchmark），然后照抄它们的结论。代价是：你无法回答“这个 6× 是从哪里来的”，也无法在另一台机器上复现它。这个项目的全部产出就是归因能力（attribution capability），所以这三件事——计时、正确性检查、配置记录——必须掌握在自己手里，不能外包出去。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| trade-offs | n. | 权衡；取舍 | several key trade-offs |
| off-the-shelf | adj. | 现成的；开箱即用的 | off-the-shelf components |
| intrinsics | n. | 内建函数；intrinsic 函数 | hand-writing intrinsics |
| lanes | n. | （SIMD 的）通道；lane | lanes to diverge |
| associative | adj. | 可结合的（满足结合律的） | not associative |
| harness | n. | 测试框架；测试装置 | This layer is the harness |
| core pinning | n. | 核心绑定；CPU 绑核 | Core pinning is not an optimization technique |
| interquartile range | n. | 四分位距 | the median and interquartile range |
| swept | v. | 扫描 | N is swept |
| speedup | n. | 加速比 | speedup drop |
| LLC | n. | 末级缓存（last-level cache） | far beyond LLC |
| False-sharing | n. | 伪共享 | False-sharing experiments |
| cache line | n. | 缓存行 | same 64-byte cache line |
| hoist | v. | 提升 | hoist the accumulator variable |
| isomorphic | adj. | 同构的 | isomorphic to the CPU backend |
| launch overhead | n. | 启动开销 | launch overhead |

## 3. Chapter Outline

1. **Timing foundation and serial baseline**—workload interface, 64B-aligned allocation, checksum, warmup and repetition, core pinning. Knowledge points: timing error, sources of jitter, the difference between median and mean. After completing, you can verify: the harness’s own jitter < 2%, and the serial baseline is reproducible.

   > 译：**计时基础与串行基线（serial baseline）**——工作负载接口、64B 对齐分配、校验和（checksum）、预热与重复（warmup and repetition）、核心绑定（core pinning）。知识点：计时误差、抖动（jitter）的来源、中位数与平均值的区别。完成后你可以验证：测试框架（harness）自身的抖动 < 2%，并且串行基线是可复现的。

2. **Arithmetic intensity and roofline positioning**—plot each workload on the roofline graph and determine whether it is compute-bound or bandwidth-bound. Knowledge points: arithmetic intensity, peak compute throughput, bandwidth, average memory access time. After completing, you can verify: you can predict in advance which workload has a lower speedup ceiling, and the prediction is hit by measurement.

   > 译：**算术强度（arithmetic intensity）与 roofline 定位**——把每个工作负载画到 roofline 图上，判断它是计算受限（compute-bound）还是带宽受限（bandwidth-bound）。知识点：算术强度、峰值计算吞吐量（peak compute throughput）、带宽、平均内存访问时间（average memory access time）。完成后你可以验证：你能提前预测哪个工作负载的加速比上限更低，而且该预测被实测结果命中。

3. **SIMD vectorization**—from scalar to AVX2/NEON, vector width, alignment, tails, masks, branch rewriting, reduction order. Knowledge points: SIMD execution model, lane divergence, floating-point non-associativity. After completing, you can verify: at least 2.5× relative to scalar, and the slowdown points can be explained by tails or alignment.

   > 译：**SIMD 向量化（SIMD vectorization）**——从标量（scalar）到 AVX2/NEON、向量宽度（vector width）、对齐（alignment）、尾部（tails）、掩码（masks）、分支改写（branch rewriting）、归约顺序（reduction order）。知识点：SIMD 执行模型（SIMD execution model）、lane 分歧（lane divergence）、浮点非结合性（floating-point non-associativity）。完成后，你可以验证：至少达到标量的 2.5 倍，并且变慢的点可以用尾部或对齐来解释。

4. **Two ways of writing multicore parallelism**—OpenMP’s `parallel for`/`reduction` and manual partitioning with `std::thread`, static and dynamic scheduling, reduction tree. Knowledge points: data partitioning, load imbalance, scheduling overhead. After completing, you can verify: measure the actual speedup on 8 cores, and use Amdahl to infer the serial fraction.

   > 译：**编写多核并行（multicore parallelism）的两种方式**——OpenMP 的 `parallel for`/`reduction` 与用 `std::thread` 手工划分（manual partitioning）、静态与动态调度（static and dynamic scheduling）、归约树（reduction tree）。知识点：数据划分（data partitioning）、负载不均衡（load imbalance）、调度开销（scheduling overhead）。完成后，你可以验证：在 8 核上测量实际加速比（speedup），并用 Amdahl 定律推断串行部分占比（serial fraction）。

5. **Cache coherence and false sharing**—MESI intuition, cache line, padding, reproduction and fix comparison. Knowledge points: coherence traffic, write invalidation, alignment. After completing, you can verify: after the fix,

   > 译：**缓存一致性（cache coherence）与伪共享（false sharing）**——MESI 的直观理解（intuition）、缓存行（cache line）、填充（padding）、复现与修复的对比。知识点：一致性流量（coherence traffic）、写失效（write invalidation）、对齐（alignment）。完成后，你可以验证：修复之后，

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| checksum | n. | 校验和 | checksum |
| jitter | n. | 抖动（计时结果的短期波动） | sources of jitter |
| core pinning | n. | 核心绑定（把线程固定到指定 CPU 核心上运行） | core pinning |
| arithmetic intensity | n. | 算术强度（计算量与访存数据量之比） | arithmetic intensity |
| compute-bound | adj. | 计算受限的 | compute-bound |
| roofline | n. | roofline 模型（用屋顶线图刻画性能上限） | roofline graph |
| vectorization | n. | 向量化 | SIMD vectorization |
| lane divergence | n. | lane 分歧（同一向量指令内不同 lane 走向不同分支） | lane divergence |
| floating-point non-associativity | n. | 浮点非结合性（加法结合律不成立） | floating-point non-associativity |
| load imbalance | n. | 负载不均衡 | load imbalance |
| scheduling overhead | n. | 调度开销 | scheduling overhead |
| serial fraction | n. | 串行部分占比 | the serial fraction |
| cache coherence | n. | 缓存一致性 | Cache coherence |
| false sharing | n. | 伪共享 | false sharing |
| write invalidation | n. | 写失效 | write invalidation |
