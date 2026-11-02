## 1. What It Is Doing

Build a reusable testbed for a class of algorithmic problems, then use it to walk through four routes—divide and conquer, greedy, dynamic programming, and graph algorithms—one by one. Each leaves three things: a pure C implementation that can be compiled and run on its own, a cost curve that can be plotted, and evidence that can convince yourself you didn't write it wrong.

Input is a problem description plus constraints: the range of problem size n, whether weights can be negative, whether the graph is connected, and whether the data is random or nearly sorted. Output has two things: a batch of single-file implementations that do not depend on any third-party libraries; and a cost report in which each algorithm gives operation counts at 8 size points (number of comparisons, number of relaxations, number of recursive calls) and a log-log fitted slope.

Acceptance does not look at "the sample ran out the correct answer." Acceptance looks at three things: whether the slope is stable after scaling n up tenfold; whether it matches brute-force enumeration one by one at small scales; and whether it is still correct after changing the input shape (already sorted, all equal, disconnected, with negative weights). A concrete example: deliver a sorting solution, not a `sort` function, but a count table of "three sorts × six input shapes × eight sizes," plus a curve that can explain "why quicksort degenerates to quadratic here."

## 2. Why Do It This Way (Functional Design)

** (1) Replace complexity conclusions memorized by rote with quantities you count yourself.**

The key decision is to abandon wall-clock time as the primary criterion and use operation counters instead. The interface connects at the bottommost layer—the **element comparison** layer: all algorithms may not directly write `a[i] < a[j]`; they must go through `LT(a, b)`, with the increment hidden in a macro; graph relaxation goes through `RELAX(u, v, w)`; recursive entry goes through `ENTER()`.

If this layer is chosen correctly, counting cannot be bypassed. If instead you wrap a timer outside the algorithm, you can get time, but not "how many comparisons were made," and thus cannot match measured values to theoretical formulas. The cost is that these primitives must run through every algorithm; the code is more verbose than writing raw, and if you miss one comparison, the entire curve is systematically low—so tests must specifically check cases like "count is 0 but result is nontrivial."

By the way, answer why not just time: constant factors drown out the signal at small n; cache and compiler optimizations change the slope at large n; numbers all change on another machine. Counting is machine-independent; this is its only but decisive advantage.

** (2) Replace "looks correct" with "falsifiable" for correctness.**

Whether greedy and DP answers are correct cannot be shown by running one sample. So the testbed must include a brute-force oracle: when n ≤ 10, use full permutations, subset enumeration, or memoized search to find the true optimal solution, then run thousands of random small instances for differential testing, and dump the instance if they disagree.

The value of this step: greedy correctness originally relies on exchange arguments, and writing an exchange argument wrong is the most common failure mode. Differential testing cannot prove it correct, but it can falsify a wrong hypothesis within an afternoon—far more worthwhile than discovering it in an exam. The cost is an extra reference implementation "known to be slow," and the oracle itself may be wrong, so the oracle must be cross-validated once with two independent implementations.

DP needs one more layer: write the same recurrence twice, once top-down memoized (state = function parameters), once bottom-up table filling (watch the traversal order). The two results must be identical point by point. This catches the vast majority of "state definition missing a dimension" and "table-filling order wrong"—without this layer, you cannot distinguish whether the transition or the boundary is wrong.

** (3) Data shape is the main source of unreliability in complexity.**

The generator must cover six shapes: random, sorted, reverse sorted, all equal, nearly sorted, few distinct values. Quicksort's quadratic degeneration only appears in the latter few; running only random data is as good as not testing. The graph generator must additionally create: disconnected, self-loops, multi-edges, chain, star, and edges with negative weights (specifically to verify that Dijkstra gives wrong answers).

The report must give the distribution over multiple runs rather than a single point. A number from one run of a randomized algorithm is meaningless; take the median of 21 runs and attach the interquartile range. The cost is that each experiment takes twenty times longer, but a single point's number cannot support any conclusion anyway.

** (4) Graph algorithms rely on mutual verification, not each writing a pile of asserts.**

Dijkstra's result must be identical point by point to Bellman-Ford on positive-weight graphs; with negative weights the two must differ, and you must be able to point out which edge causes it. Prim and Kruskal's MST total weight on the same graph must be the same (edge sets may differ—state this clearly in the report, otherwise it will be misjudged as a bug). Topological sort's indegree version and DFS version sequences may differ, but both must pass the check "all edges point consistently"; cyclic graphs must report a cycle.

This is more effective than writing separate assertions for each algorithm because it tests the **definition**, not implementation details—the half you wrote wrong will be exposed by the half you wrote right.

**Why not use a simpler approach:** Memorizing a complexity table takes half an hour and is done, at the cost that when encountering a variant problem (change to kth largest, add a constraint, change weights) you collapse, because you have nothing measurable in hand. Using library functions throughout is also fast, but library functions do not produce counts—equivalent to throwing away the project's only product.

## 3. Chapter Outline

**Chapter 1 Testbed.** Counter primitives, six-shape generator, brute-force oracle, differential-testing driver, reproducible random seed. Knowledge points: macros and function pointers, return-value conventions, deterministic reproduction. After completion you can verify: the comparison count of the same bubble sort on six shapes can be printed, and two runs are completely identical.

**Chapter 2 Asymptotic Metrics.** Distinguishing Θ/Ο/Ω, log-log least-squares fitting, influence of constant and lower-order terms, introduction to amortized analysis. Knowledge point: how to infer order from discrete points. After completion you can verify: the slopes of three sorts fall near 2, 1.1~1.3, and 1 respectively, and deviations can be attributed to specific implementation details.

**Chapter 3 Divide and Conquer.** Merge sort, quicksort partition, binary search boundaries, closest pair of points, large integer multiplication. Knowledge points: recursion tree, master theorem, partition invariant, recursion depth and stack space. After completion you can verify: merge's recursive call count is close to 2n−1, consistent with the recursion tree derivation.

**Chapter 4 Greedy.** Interval scheduling, Huffman tree building, coin change, minimum-lateness scheduling. Knowledge points: greedy-choice property, how to write exchange arguments, matroids (only briefly). After completion you can verify: each greedy either has a counterexample caught by differential testing, or leaves a fully written exchange argument.

**Chapter 5 Dynamic Programming.** LIS, LCS, 0-1 knapsack, edit distance, matrix-chain multiplication. Knowledge points: optimal substructure, design of states and transitions, table-filling order, rolling-array compression. After completion you can verify: memoization and table filling are identical point by point, and both match the brute-force oracle at small scales.

**Chapter 6 Graph Representation and Traversal.** Adjacency matrix and adjacency list, BFS/DFS, topological sort, connected components. Knowledge points: cost comparison of the two storage forms, hand-written queue and stack, timestamps. After completion you can verify: two topological implementations pass each other's edge-direction check, and the number of components in a disconnected graph is correct.

**Chapter 7 Weighted Graphs.** Dijkstra (including hand-written heap), Bellman-Ford, Floyd, Prim, Kruskal, union-find. Knowledge points: relaxation, priority queue, negative weights and negative cycles, INF addition overflow. After completion you can verify: on positive-weight graphs Dijkstra and Bellman-Ford are identical point by point; negative cycles can be detected and the vertices on the cycle reported.

**Chapter 8 Strategy Selection Retrospective.** For the same problem (weighted interval selection is recommended), write it four times with brute force, divide and conquer, DP, and greedy, and plot the four cost curves on one graph. Knowledge points: problem reduction, criteria for greedy failure, cost of exact solution. After completion you can verify: you can point at the graph and explain clearly at what scale each curve becomes unusable.

## 4. What Not to Do

Do not touch proofs of NP-completeness, and do not implement approximation algorithms or randomized algorithms (except quicksort's random sampling). They do not change the goal of "the feel of the four strategies," and the input-output ratio is not worthwhile.

No engineering: no build beyond a single-file Makefile, no memory pool, no generics. Elements uniformly `int`, weights uniformly `long long`. Type generalization makes threading counters through extremely difficult, with zero benefit.

Do not pursue short code. Solving sorting in one line with `qsort` is an advantage in other projects; here it is equivalent to doing nothing, because it does not produce a cost curve.

Do not write problem solutions, do not organize common interview questions—that is another project's responsibility. Also do not make lecture notes that "explain the principle of every algorithm"; principles are in textbooks; here only executable judgments are kept.

Implementation freedom: choose code style within C99; the priority queue can be a hand-written heap, or an ordered array as a substitute, but the report must state which part of the complexity this replacement changes; for the graph's primary storage choose either of the two, but the other must at least be convertible.

There are four common derailments: spending effort on making timing more accurate (should spend it on counting); writing a general test framework for differential testing (thirty lines is enough); running only random data (degenerate shapes are the exam points); treating DP's table-filling order as a conclusion to memorize, rather than something derived from state dependencies.
