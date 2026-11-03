> **双语对照版**：英文原段 → 紧随其后的中文译文（引用块，前缀 `译：`）；每节末附该节生词表。术语首次出现保留英文原词，方便对照阅读与翻译练习。

## 1. What It Is Doing

Build a reusable testbed for a class of algorithmic problems, then use it to walk through four routes—divide and conquer, greedy, dynamic programming, and graph algorithms—one by one. Each leaves three things: a pure C implementation that can be compiled and run on its own, a cost curve that can be plotted, and evidence that can convince yourself you didn't write it wrong.

> 译：为一类算法问题构建一个可复用的测试台（testbed），然后用它逐一走通四条路线——分治（divide and conquer）、贪心（greedy）、动态规划（dynamic programming）和图算法（graph algorithms）。每条路线都留下三样东西：一个可以单独编译和运行的纯 C 实现，一条可以绘制的代价曲线（cost curve），以及能让你说服自己没写错的证据。

Input is a problem description plus constraints: the range of problem size n, whether weights can be negative, whether the graph is connected, and whether the data is random or nearly sorted. Output has two things: a batch of single-file implementations that do not depend on any third-party libraries; and a cost report in which each algorithm gives operation counts at 8 size points (number of comparisons, number of relaxations, number of recursive calls) and a log-log fitted slope.

> 译：输入是一份问题描述加上若干约束：问题规模 n 的范围、权重是否可以为负、图是否连通，以及数据是随机的还是近乎有序的。输出有两样东西：一批不依赖任何第三方库的单文件实现；以及一份代价报告，其中每个算法给出在 8 个规模点上的操作计数（比较次数、松弛次数、递归调用次数）和一个双对数拟合斜率（log-log fitted slope）。

Acceptance does not look at "the sample ran out the correct answer." Acceptance looks at three things: whether the slope is stable after scaling n up tenfold; whether it matches brute-force enumeration one by one at small scales; and whether it is still correct after changing the input shape (already sorted, all equal, disconnected, with negative weights). A concrete example: deliver a sorting solution, not a `sort` function, but a count table of "three sorts × six input shapes × eight sizes," plus a curve that can explain "why quicksort degenerates to quadratic here."

> 译：验收不看“样例跑出了正确答案”。验收看三件事：把 n 放大十倍后斜率是否稳定；在小规模下是否与暴力枚举逐一比对一致；以及在改变输入形态（已排序、全部相等、不连通、带负权重）之后是否仍然正确。一个具体例子：交付一个排序解决方案，不是 `sort` 函数，而是一张“三种排序 × 六种输入形态 × 八个规模”的计数表，再加一条能解释“为什么这里的快速排序退化为二次复杂度”的曲线。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| testbed | n. | 测试台 | reusable testbed |
| divide and conquer | n. | 分治 | four routes—divide and conquer |
| cost curve | n. | 代价曲线 | a cost curve that can be plotted |
| constraints | n. | 约束 | problem description plus constraints |
| relaxations | n. | 松弛次数 | number of relaxations |
| log-log fitted slope | n. | 双对数拟合斜率 | a log-log fitted slope |
| brute-force enumeration | n. | 暴力枚举 | matches brute-force enumeration |
| input shape | n. | 输入形态 | changing the input shape |
| degenerates | v. | 退化 | quicksort degenerates to quadratic |

## 2. Why Do It This Way (Functional Design)

**(1) Replace complexity conclusions memorized by rote with quantities you count yourself.**

> 译：**（1）用你自己数出来的量，替换靠死记硬背记住的复杂度结论。**

The key decision is to abandon wall-clock time as the primary criterion and use operation counters instead. The interface connects at the bottommost layer—the **element comparison** layer: all algorithms may not directly write `a[i] < a[j]`; they must go through `LT(a, b)`, with the increment hidden in a macro; graph relaxation goes through `RELAX(u, v, w)`; recursive entry goes through `ENTER()`.

> 译：关键决策是放弃把挂钟时间（wall-clock time）作为主要判据，改用操作计数器（operation counter）。接口连接在最底层——即**元素比较（element comparison）**层：所有算法都不得直接写 `a[i] < a[j]`；它们必须经过 `LT(a, b)`，其中自增隐藏在宏（macro）里；图的松弛（graph relaxation）要经过 `RELAX(u, v, w)`；递归入口要经过 `ENTER()`。

If this layer is chosen correctly, counting cannot be bypassed. If instead you wrap a timer outside the algorithm, you can get time, but not "how many comparisons were made," and thus cannot match measured values to theoretical formulas. The cost is that these primitives must run through every algorithm; the code is more verbose than writing raw, and if you miss one comparison, the entire curve is systematically low—so tests must specifically check cases like "count is 0 but result is nontrivial."

> 译：如果这一层选得正确，计数就无法被绕过。反之，如果你在算法外面包一个计时器（timer），你能得到时间，但得不到“进行了多少次比较”，因而无法把测量值与理论公式对应起来。代价是：这些原语（primitive）必须贯穿每个算法；代码比直接写原始代码更冗长，而且如果你漏掉一次比较，整条曲线就会系统性地偏低——所以测试必须专门检查诸如“计数为 0 但结果并非平凡（nontrivial）”这样的情况。

By the way, answer why not just time: constant factors drown out the signal at small n; cache and compiler optimizations change the slope at large n; numbers all change on another machine. Counting is machine-independent; this is its only but decisive advantage.

> 译：顺便回答一下“为什么不直接计时”：在小 n 下，常数因子（constant factors）会淹没信号；在大 n 下，缓存和编译器优化会改变斜率（slope）；换到另一台机器上，所有数字都会变。计数（counting）与机器无关（machine-independent）；这是它唯一但决定性的优势。

**(2) Replace "looks correct" with "falsifiable" for correctness.**

> 译：**（2）在正确性上，把“看起来正确”替换为“可证伪（falsifiable）”。**

Whether greedy and DP answers are correct cannot be shown by running one sample. So the testbed must include a brute-force oracle: when n ≤ 10, use full permutations, subset enumeration, or memoized search to find the true optimal solution, then run thousands of random small instances for differential testing, and dump the instance if they disagree.

> 译：贪心（greedy）和 DP 的答案是否正确，不能通过运行一个样例来证明。因此测试台必须包含一个暴力预言机（brute-force oracle）：当 n ≤ 10 时，使用全排列、子集枚举或记忆化搜索（memoized search）来找到真正的最优解，然后运行数千个随机小实例进行差分测试（differential testing），如果它们不一致，就把该实例转储出来。

The value of this step: greedy correctness originally relies on exchange arguments, and writing an exchange argument wrong is the most common failure mode. Differential testing cannot prove it correct, but it can falsify a wrong hypothesis within an afternoon—far more worthwhile than discovering it in an exam. The cost is an extra reference implementation "known to be slow," and the oracle itself may be wrong, so the oracle must be cross-validated once with two independent implementations.

> 译：这一步的价值：贪心正确性（greedy correctness）原本依赖交换论证（exchange argument），而把交换论证写错是最常见的失败模式。差分测试（differential testing）不能证明它正确，但它能在一个下午内证伪一个错误假设——这远比在考试中发现它更值得。代价是多出一个“已知很慢”的参考实现（reference implementation），而且判定器（oracle）本身也可能错，所以必须用两个独立实现把判定器交叉验证一次。

DP needs one more layer: write the same recurrence twice, once top-down memoized (state = function parameters), once bottom-up table filling (watch the traversal order). The two results must be identical point by point. This catches the vast majority of "state definition missing a dimension" and "table-filling order wrong"—without this layer, you cannot distinguish whether the transition or the boundary is wrong.

> 译：动态规划（DP）还需要多一层：把同一个递推式（recurrence）写两遍，一遍写成自顶向下记忆化（memoized）（状态 = 函数参数），一遍写成自底向上填表（注意遍历顺序）。两个结果必须逐点完全相同。这能抓住绝大多数“状态定义少了一维”和“填表顺序错误”——没有这一层，你就无法区分到底是转移（transition）错了还是边界（boundary）错了。

**(3) Data shape is the main source of unreliability in complexity.**

> 译：**（3）数据形态（data shape）是复杂度（complexity）中不可靠性（unreliability）的主要来源。**

The generator must cover six shapes: random, sorted, reverse sorted, all equal, nearly sorted, few distinct values. Quicksort's quadratic degeneration only appears in the latter few; running only random data is as good as not testing. The graph generator must additionally create: disconnected, self-loops, multi-edges, chain, star, and edges with negative weights (specifically to verify that Dijkstra gives wrong answers).

> 译：生成器必须覆盖六种形态：随机、有序、逆序、全部相等、接近有序、少量不同取值。Quicksort 的平方级退化（quadratic degeneration）只出现在后几种里；只跑随机数据等同于没测。图生成器还必须额外造出：不连通、自环（self-loops）、多重边（multi-edges）、链、星形，以及带负权重的边（专门用来验证 Dijkstra 会给出错误答案）。

The report must give the distribution over multiple runs rather than a single point. A number from one run of a randomized algorithm is meaningless; take the median of 21 runs and attach the interquartile range. The cost is that each experiment takes twenty times longer, but a single point's number cannot support any conclusion anyway.

> 译：报告必须给出多次运行上的分布，而不是单点。随机化算法（randomized algorithm）一次运行得到的数字没有意义；取 21 次运行的中位数（median），并附上四分位距（interquartile range）。代价是每个实验要多花二十倍时间，但单点的数字本来就支撑不了任何结论。

**(4) Graph algorithms rely on mutual verification, not each writing a pile of asserts.**

> 译：**（4）图算法依靠相互验证（mutual verification），而不是各自写一堆断言（asserts）。**

Dijkstra's result must be identical point by point to Bellman-Ford on positive-weight graphs; with negative weights the two must differ, and you must be able to point out which edge causes it. Prim and Kruskal's MST total weight on the same graph must be the same (edge sets may differ—state this clearly in the report, otherwise it will be misjudged as a bug). Topological sort's indegree version and DFS version sequences may differ, but both must pass the check "all edges point consistently"; cyclic graphs must report a cycle.

> 译：Dijkstra 的结果在正权图（positive-weight graphs）上必须与 Bellman-Ford 逐点完全相同；在带负权时，两者必须不同，而且你必须能指出是哪条边导致的。Prim 与 Kruskal 在同一张图上的 MST 总权重必须相同（边集可以不同——这一点要在报告中写清楚，否则会被误判为 bug）。拓扑排序（topological sort）的入度（indegree）版本与 DFS 版本得到的序列可以不同，但两者都必须通过「所有边方向一致」这一检查；有环图（cyclic graph）必须报告出环。

This is more effective than writing separate assertions for each algorithm because it tests the **definition**, not implementation details—the half you wrote wrong will be exposed by the half you wrote right.

> 译：这比给每个算法分别写断言（assertion）更有效，因为它检验的是**定义**，而不是实现细节——你写错的那一半，会被你写对的那一半暴露出来。

**Why not use a simpler approach:** Memorizing a complexity table takes half an hour and is done, at the cost that when encountering a variant problem (change to kth largest, add a constraint, change weights) you collapse, because you have nothing measurable in hand. Using library functions throughout is also fast, but library functions do not produce counts—equivalent to throwing away the project's only product.

> 译：**为什么不用更简单的做法：** 背一张复杂度表只需半小时就能搞定，代价是：一旦遇到变体（variant）问题（改成第 k 大、加一个约束、改权重），你就垮了，因为你手上没有任何可度量的东西。全程使用库函数（library function）也很快，但库函数不产生计数——等于把本项目唯一的产物扔掉。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| rote | n. | 死记硬背 | memorized by rote |
| complexity | n. | 复杂度 | complexity conclusions |
| wall-clock time | n. | 挂钟时间 | abandon wall-clock time |
| criterion | n. | 判据；标准 | primary criterion |
| macro | n. | 宏 | hidden in a macro |
| primitive | n. | 原语 | these primitives |
| verbose | adj. | 冗长的 | more verbose than writing raw |
| nontrivial | adj. | 非平凡的 | result is nontrivial |
| constant factors | n. | 常数因子 | constant factors drown out the signal |
| slope | n. | 斜率 | change the slope at large n |
| machine-independent | adj. | 与机器无关的 | Counting is machine-independent |
| falsifiable | adj. | 可证伪的 | with "falsifiable" |
| brute-force oracle | n. | 暴力预言机 | a brute-force oracle |
| memoized search | n. | 记忆化搜索 | or memoized search |
| differential testing | n. | 差分测试 | for differential testing |
| exchange argument | n. | 交换论证 | exchange arguments |

## 3. Chapter Outline

**Chapter 1 Testbed.** Counter primitives, six-shape generator, brute-force oracle, differential-testing driver, reproducible random seed. Knowledge points: macros and function pointers, return-value conventions, deterministic reproduction. After completion you can verify: the comparison count of the same bubble sort on six shapes can be printed, and two runs are completely identical.

> 译：**第 1 章 测试台（Testbed）。** 计数原语（counter primitives）、六种形状生成器、暴力对照器（brute-force oracle）、差分测试驱动（differential-testing driver）、可复现随机种子。知识点：宏与函数指针、返回值约定、确定性复现（deterministic reproduction）。完成后可验证：同一冒泡排序在六种形状上的比较次数能够被打印出来，且两次运行完全一致。

**Chapter 2 Asymptotic Metrics.** Distinguishing Θ/Ο/Ω, log-log least-squares fitting, influence of constant and lower-order terms, introduction to amortized analysis. Knowledge point: how to infer order from discrete points. After completion you can verify: the slopes of three sorts fall near 2, 1.1~1.3, and 1 respectively, and deviations can be attributed to specific implementation details.

> 译：**第 2 章 渐近度量（Asymptotic Metrics）。** 区分 Θ/Ο/Ω、双对数最小二乘拟合（log-log least-squares fitting）、常数项与低阶项的影响、摊还分析（amortized analysis）简介。知识点：如何从离散点推断出阶。完成后可验证：三种排序的斜率分别落在 2、1.1~1.3 和 1 附近，且偏差能够归因到具体的实现细节。

**Chapter 3 Divide and Conquer.** Merge sort, quicksort partition, binary search boundaries, closest pair of points, large integer multiplication. Knowledge points: recursion tree, master theorem, partition invariant, recursion depth and stack space. After completion you can verify: merge's recursive call count is close to 2n−1, consistent with the recursion tree derivation.

> 译：**第 3 章 分治（Divide and Conquer）。** 归并排序、快速排序划分（quicksort partition）、二分查找边界、最近点对、大整数乘法。知识点：递归树、主定理（master theorem）、划分不变式（partition invariant）、递归深度与栈空间。完成后可验证：归并的递归调用次数接近 2n−1，与递归树推导一致。

**Chapter 4 Greedy.** Interval scheduling, Huffman tree building, coin change, minimum-lateness scheduling. Knowledge points: greedy-choice property, how to write exchange arguments, matroids (only briefly). After completion you can verify: each greedy either has a counterexample caught by differential testing, or leaves a fully written exchange argument.

> 译：**第 4 章 贪心。** 区间调度、Huffman 树构建、找零钱、最小延迟调度。知识点：贪心选择性质（greedy-choice property）、如何写交换论证（exchange argument）、拟阵（matroid）（仅简要涉及）。完成之后你可以验证：每个贪心算法要么存在一个能被差分测试（differential testing）抓到的反例，要么留下一份写完整的交换论证。

**Chapter 5 Dynamic Programming.** LIS, LCS, 0-1 knapsack, edit distance, matrix-chain multiplication. Knowledge points: optimal substructure, design of states and transitions, table-filling order, rolling-array compression. After completion you can verify: memoization and table filling are identical point by point, and both match the brute-force oracle at small scales.

> 译：**第 5 章 动态规划。** LIS、LCS、0-1 背包、编辑距离、矩阵链相乘。知识点：最优子结构（optimal substructure）、状态与转移的设计、填表顺序、滚动数组压缩（rolling-array compression）。完成之后你可以验证：记忆化（memoization）与填表逐点完全相同，并且两者在小规模上都与暴力对照基准（brute-force oracle）一致。

**Chapter 6 Graph Representation and Traversal.** Adjacency matrix and adjacency list, BFS/DFS, topological sort, connected components. Knowledge points: cost comparison of the two storage forms, hand-written queue and stack, timestamps. After completion you can verify: two topological implementations pass each other's edge-direction check, and the number of components in a disconnected graph is correct.

> 译：**第 6 章 图的表示与遍历。** 邻接矩阵与邻接表（adjacency list）、BFS/DFS、拓扑排序（topological sort）、连通分量。知识点：两种存储形式的代价比较、手写队列与栈、时间戳（timestamps）。完成之后你可以验证：两种拓扑排序实现能互相通过对方的边方向检查，且非连通图中连通分量的数目正确。

**Chapter 7 Weighted Graphs.** Dijkstra (including hand-written heap), Bellman-Ford, Floyd, Prim, Kruskal, union-find. Knowledge points: relaxation, priority queue, negative weights and negative cycles, INF addition overflow. After completion you can verify: on positive-weight graphs Dijkstra and Bellman-Ford are identical point by point; negative cycles can be detected and the vertices on the cycle reported.

> 译：**第 7 章 加权图（Weighted Graphs）。**Dijkstra（包括手写堆）、Bellman-Ford、Floyd、Prim、Kruskal、并查集（union-find）。知识点：松弛（relaxation）、优先队列（priority queue）、负权与负环（negative cycles）、INF 相加溢出（overflow）。完成后你可以验证：在正权图上，Dijkstra 与 Bellman-Ford 逐点完全一致；负环可以被检测出来，并报告出环上的顶点。

**Chapter 8 Strategy Selection Retrospective.** For the same problem (weighted interval selection is recommended), write it four times with brute force, divide and conquer, DP, and greedy, and plot the four cost curves on one graph. Knowledge points: problem reduction, criteria for greedy failure, cost of exact solution. After completion you can verify: you can point at the graph and explain clearly at what scale each curve becomes unusable.

> 译：**第 8 章 策略选择复盘。**对同一个问题（推荐用加权区间选择），分别用暴力、分治、DP 和贪心写四遍，并把四条代价曲线画在同一张图上。知识点：问题归约（problem reduction）、贪心失效的判据（criteria）、精确解的代价。完成后你可以验证：你能指着这张图，清楚地说明每条曲线在什么规模上变得不可用。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| oracle | n. | 对照器，标准参照（用于给出正确答案的基准程序） | brute-force oracle |
| differential-testing | adj. | 差分测试的（对比两个实现的结果来发现差异） | differential-testing driver |
| deterministic reproduction | n. | 确定性复现 | deterministic reproduction |
| least-squares | adj. | 最小二乘的 | log-log least-squares fitting |
| amortized analysis | n. | 摊还分析 | introduction to amortized analysis |
| lower-order terms | n. | 低阶项 | constant and lower-order terms |
| master theorem | n. | 主定理 | recursion tree, master theorem |
| invariant | n. | 不变式 | partition invariant |
| recursion depth | n. | 递归深度 | recursion depth and stack space |
| greedy-choice property | n. | 贪心选择性质 | greedy-choice property |
| exchange argument | n. | 交换论证 | write exchange arguments |
| matroid | n. | 拟阵 | matroids (only briefly) |
| optimal substructure | n. | 最优子结构 | optimal substructure |
| memoization | n. | 记忆化 | memoization and table filling |
| rolling-array compression | n. | 滚动数组压缩 | rolling-array compression |
| adjacency list | n. | 邻接表 | adjacency matrix and adjacency list |

## 4. What Not to Do

Do not touch proofs of NP-completeness, and do not implement approximation algorithms or randomized algorithms (except quicksort's random sampling). They do not change the goal of "the feel of the four strategies," and the input-output ratio is not worthwhile.

> 译：不要碰 NP 完全性（NP-completeness）的证明，也不要实现近似算法（approximation algorithms）或随机算法（randomized algorithms）（快速排序的随机采样除外）。它们并不改变“四种策略的感觉”这一目标，投入产出比（input-output ratio）也不划算。

No engineering: no build beyond a single-file Makefile, no memory pool, no generics. Elements uniformly `int`, weights uniformly `long long`. Type generalization makes threading counters through extremely difficult, with zero benefit.

> 译：不做工程化：除单文件 Makefile 之外没有任何构建，没有内存池（memory pool），没有泛型（generics）。元素统一用 `int`，权重统一用 `long long`。类型泛化（type generalization）会让计数器在各处穿线变得极其困难，而且毫无收益。

Do not pursue short code. Solving sorting in one line with `qsort` is an advantage in other projects; here it is equivalent to doing nothing, because it does not produce a cost curve.

> 译：不要追求代码短。用 `qsort` 一行解决排序，在其他项目里是优势；在这里等同于什么都没做，因为它产生不出成本曲线（cost curve）。

Do not write problem solutions, do not organize common interview questions—that is another project's responsibility. Also do not make lecture notes that "explain the principle of every algorithm"; principles are in textbooks; here only executable judgments are kept.

> 译：不要写题解，不要整理常见面试题——那是另一个项目的职责。也不要写那种“讲解每个算法原理”的讲义；原理在教科书里；这里只保留可执行的判断（executable judgments）。

Implementation freedom: choose code style within C99; the priority queue can be a hand-written heap, or an ordered array as a substitute, but the report must state which part of the complexity this replacement changes; for the graph's primary storage choose either of the two, but the other must at least be convertible.

> 译：实现自由：在 C99 范围内自选代码风格；优先队列（priority queue）可以是手写的堆（heap），也可以用有序数组作为替代，但报告必须说明这一替换改变了复杂度的哪一部分；图的主存储（primary storage）在两者中任选其一，但另一种至少必须可转换。

There are four common derailments: spending effort on making timing more accurate (should spend it on counting); writing a general test framework for differential testing (thirty lines is enough); running only random data (degenerate shapes are the exam points); treating DP's table-filling order as a conclusion to memorize, rather than something derived from state dependencies.

> 译：有四种常见的跑偏（derailment）：把精力花在让计时更准确上（应该花在计数上）；为差分测试（differential testing）写一个通用测试框架（三十行就够了）；只跑随机数据（退化形状（degenerate shapes）才是考点）；把 DP 的填表顺序当成要背下来的结论，而不是从状态依赖关系推导出来的东西。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| NP-completeness | n. | NP 完全性 | proofs of NP-completeness |
| approximation algorithms | n. | 近似算法 | implement approximation algorithms |
| input-output ratio | n. | 投入产出比 | the input-output ratio is not worthwhile |
| memory pool | n. | 内存池 | no memory pool |
| generics | n. | 泛型 | no generics |
| type generalization | n. | 类型泛化 | Type generalization makes threading counters through extremely difficult |
| cost curve | n. | 成本曲线 | it does not produce a cost curve |
| equivalent | adj. | 等同的 | it is equivalent to doing nothing |
| problem solutions | n. | 题解 | Do not write problem solutions |
| lecture notes | n. | 讲义 | do not make lecture notes |
| executable judgments | n. | 可执行的判断 | only executable judgments are kept |
| priority queue | n. | 优先队列 | the priority queue can be a hand-written heap |
| heap | n. | 堆（一种树形数据结构） | a hand-written heap |
| convertible | adj. | 可转换的 | must at least be convertible |
| derailment | n. | 偏离正轨、跑偏 | four common derailments |
| differential testing | n. | 差分测试（用两种实现互相对比结果） | a general test framework for differential testing |
