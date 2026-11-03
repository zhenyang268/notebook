> **双语对照版**：英文原段 → 紧随其后的中文译文（引用块，前缀 `译：`）；每节末附该节生词表。术语首次出现保留英文原词，方便对照阅读与翻译练习。

## 1. What It Is Doing

This project turns the five mechanisms from the first nine chapters of CSAPP that are most easily "memorized" — bit-level representation of integers and floating point, procedure calls and stack frames at the assembly level, Cache mapping and replacement, linker symbol resolution and relocation, and process/thread concurrency control — into implementation tasks that **must be aligned item by item with a reference implementation**.

> 译：这个项目把 CSAPP 前九章中最容易被“背下来”的五个机制——整数与浮点数的位级表示、汇编层面的过程调用与栈帧、Cache 映射与替换、链接器符号解析与重定位，以及进程/线程并发控制——转化为**必须与参考实现逐项对齐**的实现任务。

The input is very small: each lab only allows modifying one C file. The output is machine-judgable behavioral differences: return values of bit-operation functions, the three counters hit/miss/eviction produced by the Cache simulator, process state transitions under job control, allocator utilization and throughput, the executable produced by the self-built linker, and correctness and absence of thread races of the concurrent server under stress.

> 译：输入非常小：每个 lab 只允许修改一个 C 文件。输出是机器可判定的行为差异：位运算函数的返回值、Cache 模拟器产生的 hit/miss/eviction 三个计数器、作业控制下的进程状态转换、分配器的利用率与吞吐量、自建链接器产生的可执行文件，以及并发服务器在压力下的正确性和不存在线程竞争。

Acceptance does not look at "whether it runs"; it looks only at three things: results **equal item by item** to the reference implementation (not hit rate approximately equal, not throughput roughly similar), static checks with no warnings, and no crash under boundary and random inputs. What this project really trains is "compressing a vague mechanism description into a set of assertions that can pass."

> 译：验收不看“它是否能运行”；只看三件事：结果**逐项等于**参考实现（不是命中率近似相等，不是吞吐量大致相近）、静态检查没有警告，以及在边界和随机输入下不崩溃。这个项目真正训练的是“把含糊的机制描述压缩成一组能够通过的断言”。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| bit-level representation | n. | 位级表示 | bit-level representation of integers and floating point |
| procedure calls | n. | 过程调用 | procedure calls and stack frames |
| relocation | n. | 重定位 | symbol resolution and relocation |
| machine-judgable | adj. | 机器可判定的 | machine-judgable behavioral differences |
| process state transitions | n. | 进程状态转换 | process state transitions under job control |
| thread races | n. | 线程竞争 | absence of thread races |
| Acceptance | n. | 验收 | Acceptance does not look at |
| assertions | n. | 断言 | a set of assertions that can pass |
| boundary and random inputs | n. | 边界和随机输入 | under boundary and random inputs |

## 2. Why Do It This Way (Functional Design)

The core idea is to **replace off-the-shelf components one by one**, and the replacement points are all chosen at "abstraction boundaries" — precisely the layer that textbooks gloss over in one sentence and that you have never implemented by hand.

> 译：核心思想是**逐个替换现成的组件（off-the-shelf components）**，而替换点都选在“抽象边界（abstraction boundaries）”处——恰恰是教科书用一句话一带而过（gloss over）、而你从未亲手实现过的那一层。

**Rebuild arithmetic and floating point with bit operations (replacing the compiler's arithmetic instructions).** The interface is at the function-signature level: `bitAnd`, `logicalShift`, `floatScale2`, `floatFloat2Int`, and the like; the constraint is that the file under test may contain only `~ & ^ | << >>` and a limited set of constants, with no loops, conditionals, function calls, or casts. This means the modular arithmetic semantics of two's complement, the difference between arithmetic right shift and logical right shift, the three-part decomposition of IEEE 754, round-to-even, the implicit bit being 0 for denormalized numbers, NaN comparison, and truncation toward zero and overflow when converting floating point to integer all must be filled in by yourself. Unreliability comes from boundary values: whether `Tmin` negated is itself, `-0.0` versus `0.0`, and rounding carry pushing the exponent up by one. The mechanism that constrains it has two layers — the static checker reduces the language capability to only bit operations (no convenient syntax to slack off with), and large-scale random vectors are differentially tested bit by bit against the reference implementation. Why not just write `a & b`: that is exactly the abstraction to be dismantled; why not write it in Python: Python integers have no bit width, so overflow and denormalization simply do not exist, which amounts to bypassing what is to be learned.

> 译：**用位运算重建算术与浮点（替换编译器的算术指令）。** 接口在函数签名层面：`bitAnd`、`logicalShift`、`floatScale2`、`floatFloat2Int` 等；约束是受测文件只能包含 `~ & ^ | << >>` 和一组有限常量，不能有循环、条件、函数调用或类型转换。这意味着补码（two's complement）的模算术语义、算术右移与逻辑右移的区别、IEEE 754 的三段分解、向偶数舍入（round-to-even）、非规格化数（denormalized numbers）的隐含位为 0、NaN 比较，以及浮点转整数时的向零截断与溢出，全都必须由你自己补齐。不可靠性来自边界值：`Tmin` 取负是否仍是自身、`-0.0` 与 `0.0` 的差别，以及舍入进位把指数推高一位。约束它的机制有两层——静态检查器把语言能力削减到只剩位运算（没有方便语法可以偷懒），大规模随机向量则与参考实现逐位做差分测试。为什么不直接写 `a & b`：那正是要被拆掉的抽象；为什么不用 Python 写：Python 整数没有位宽，溢出和非规格化根本不存在，这等于绕过了要学的东西。

**Simulate the Cache in software (replacing the cache controller in hardware).** The interface falls at the "memory access stream" level: the input is the `L/S/M addr,size` sequence in the trace, and the output is three counters. The conventions to implement yourself include: splitting the address by s/E/b into tag, set index, and block offset; the LRU replacement order; the write-hit and write-miss policies (write-back or write-through, whether write-allocate); and `M` counting as one load plus one store. Unreliability comes from the trace being a black box and the address space being far larger than the cache, while **the replacement order within the same set determines all later hits** — one policy error is amplified into hundreds of counter differences. Therefore acceptance is item-by-item equality, not approximate hit rate; a difference of 1 means the semantics of replacement or `M` are wrong. The simpler approach (just using a large array indexed by address) amounts to assuming fully associative with infinite capacity, and the entire concept of conflict misses disappears.

> 译：**用软件模拟缓存（替换硬件中的缓存控制器（cache controller））。** 接口落在“内存访问流”层面：输入是踪迹（trace）中的 `L/S/M addr,size` 序列，输出是三个计数器。要自己实现的约定包括：按 s/E/b 把地址拆成 tag、组索引和块偏移；LRU 替换顺序（LRU replacement order）；写命中与写缺失策略（写回还是写直达，是否写分配）；以及 `M` 计为一次加载加一次存储。不可靠性来自踪迹是黑箱、地址空间远大于缓存，而**同一组内的替换顺序决定之后所有命中**——一个策略错误会被放大成数百个计数器差异。因此验收是逐项相等，而不是近似命中率；差 1 就意味着替换或 `M` 的语义错了。更简单的做法（只用按地址索引的大数组）等于假设全相联（fully associative）且容量无限，于是冲突缺失的整个概念就消失了。

**Rebuild a shell with user-mode code (replacing bash's process management).** The interface is at the system-call level: `fork` / `execve` / `setpgid` / `waitpid` / `kill` / `sigprocmask` / `tcsetpgrp`. The conventions to define yourself: ownership of the foreground process group and the terminal, `SIGINT`/`SIGTSTP` being sent only to the foreground process group, jobs entering the stopped state after Ctrl-Z, the state machine of `jobs`/`fg`/`bg`, and **who is responsible for reaping**. Unreliability comes from asynchrony: `SIGCHLD` may arrive between any two instructions, creating a race with `waitpid` — the child exits before the parent enters blocking, the signal is coalesced or lost, and the job table misses an entry. The mechanism that constrains it is signal masking: block `SIGCHLD` before `fork`, and unblock only after the parent has written the pid into the job table; use `sigprocmask` to manually construct the critical section instead of relying on `sleep` and luck. The simpler approach is to call `system()` directly or let the child not change its process group — the former loses job control, and the latter lets Ctrl-C kill the shell itself as well.

> 译：**用用户态代码重建一个 shell（替换 bash 的进程管理）。** 接口位于系统调用层：`fork` / `execve` / `setpgid` / `waitpid` / `kill` / `sigprocmask` / `tcsetpgrp`。需要你自己定义的约定：前台进程组与终端的所有权、`SIGINT`/`SIGTSTP` 只发送给前台进程组、作业在 Ctrl-Z 之后进入停止状态、`jobs`/`fg`/`bg` 的状态机，以及**谁负责回收（reaping）**。不可靠性来自异步性（asynchrony）：`SIGCHLD` 可能在任意两条指令之间到达，与 `waitpid` 形成竞争（race）——子进程在父进程进入阻塞之前就退出，信号被合并（coalesced）或丢失，作业表漏掉一项。约束它的机制是信号屏蔽（signal masking）：在 `fork` 之前阻塞 `SIGCHLD`，并且只有在父进程把 pid 写入作业表之后才解除阻塞；用 `sigprocmask` 手工构造临界区，而不是依赖 `sleep` 和运气。更简单的做法是直接调用 `system()`，或者让子进程不改变自己的进程组——前者会失去作业控制（job control），后者会让 Ctrl-C 把 shell 自己也杀掉。

**Replace glibc's malloc with your own allocator.** The interface is only the three functions `mm_malloc` / `mm_free` / `mm_realloc`, plus a simulated heap provided by `memlib` (a fixed-length array + a `brk` pointer), completely avoiding the real kernel's `brk`/`mmap`. The conventions to implement yourself: alignment granularity, putting size and allocated bit in the block header, when to coalesce free blocks, in-place expansion and moving in `realloc`, and the size-class partitioning for segregated free lists. Unreliability comes from **fragmentation accumulating over the long term**: each operation is legal, but after the sequence lengthens, large requests begin to fail; and heap corruption manifests as delayed crashes, where the crash site is far from the error site. The mechanism that constrains it is dual metrics plus a checker: utilization is not allowed to be gamed by wasting alignment, throughput is not allowed to be gamed by not coalescing, and the two constrain each other; then write an `mm_checkheap` that traverses the entire heap after operations to verify block boundaries, free-list consistency, and no overlap — turning "invisible corruption" into an on-the-spot assertion. The simpler approach is to wrap a system malloc or use a fixed-size block pool: the former skips fragmentation entirely, and the latter's utilization drops below 30% under mixed sizes.

> 译：**用你自己的分配器替换 glibc 的 `malloc`。** 接口只有 `mm_malloc` / `mm_free` / `mm_realloc` 三个函数，外加 `memlib` 提供的模拟堆（一个定长数组 + 一个 `brk` 指针），完全避开真实内核的 `brk`/`mmap`。需要你自己实现的约定：对齐粒度、把大小和已分配位放入块头（block header）、何时合并（coalesce）空闲块、`realloc` 中的原地扩展与移动，以及分离空闲链表（segregated free lists）的尺寸类划分。不可靠性来自**长期累积的碎片化（fragmentation）**：每次操作都合法，但序列变长之后，大请求开始失败；堆破坏（heap corruption）表现为延迟崩溃：崩溃地点离出错地点很远。约束它的机制是双重指标加一个检查器：利用率（utilization）不允许通过浪费对齐来钻空子，吞吐量不允许通过不合并来钻空子，而两者相互制约；然后写一个 `mm_checkheap`，在操作之后遍历整个堆，验证块边界、空闲链表一致性和无重叠——把“不可见的破坏”变成当场断言。更简单的做法是包装系统 malloc，或使用固定大小的块池：前者完全跳过碎片化，后者在混合大小下利用率会降到 30% 以下。

**Walk through linking once yourself (replacing part of ld's responsibility).** The input is several relocatable object files and static libraries, and the output is an executable. The conventions to implement yourself: the ELF header and section header table, global/weak/local bindings in the symbol table, symbol resolution rules (strong symbols unique, weak symbols yield, undefined symbols reported only at the end), static libraries "pulled on demand and order-sensitive", and the calculation of addends and PC-relative addresses in relocation entries. Unreliability comes from the non-uniform shape of object files and the uncertainty introduced by library order. The mechanism that constrains it is section-by-section comparison with the output of the reference linker, and aligning diagnostic messages with ld. The simpler approach is to just let gcc link it — then Chapter 7 is left with nothing but nouns.

> 译：**自己完整走一遍链接（linking）过程（替换 `ld` 的一部分职责）。** 输入是若干可重定位目标文件（relocatable object files）和静态库，输出是一个可执行文件。需要你自己实现的约定：ELF 头与节头表（section header table）、符号表中的全局/弱/局部绑定（global/weak/local bindings）、符号解析规则（强符号唯一、弱符号让步、未定义符号只在最后报告）、静态库“按需拉取且对顺序敏感”，以及重定位条目（relocation entries）中加数（addends）和 PC 相对地址的计算。不可靠性来自目标文件形态不统一，以及库顺序引入的不确定性。约束它的机制是逐节与参考链接器的输出比较，并让诊断消息与 `ld` 对齐。更简单的做法是直接让 gcc 来链接——那样第 7 章就只剩下名词了。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| off-the-shelf components | n. | 现成的组件 | off-the-shelf components |
| abstraction boundaries | n. | 抽象边界 | abstraction boundaries |
| gloss over | v. | 一带而过；掩饰 | gloss over |
| two's complement | n. | 补码 | two's complement |
| round-to-even | n. | 向偶数舍入 | round-to-even |
| denormalized numbers | n. | 非规格化数 | denormalized numbers |
| cache controller | n. | 缓存控制器 | cache controller in hardware |
| LRU replacement order | n. | LRU 替换顺序 | LRU replacement order |
| fully associative | adj. | 全相联 | fully associative with infinite capacity |
| asynchrony | n. | 异步性 | Unreliability comes from asynchrony |
| coalesced | v. | 被合并 | the signal is coalesced |
| reaping | n. | 回收 | responsible for reaping |
| fragmentation | n. | 碎片化 | fragmentation accumulating over the long term |
| coalesce | v. | 合并 | when to coalesce free blocks |
| utilization | n. | 利用率 | utilization is not allowed to be gamed |
| relocatable | adj. | 可重定位的 | relocatable object files |

## 3. Chapter Outline

1. **Bits and Integers** — modular arithmetic in two's complement, shift semantics, overflow determination, and implementing addition, subtraction, multiplication, division, and comparison with bit operations. When done, you can verify: without using arithmetic operators, all integer test cases are bit-for-bit equal to the reference implementation.

   > 译：**位与整数（Bits and Integers）** — 补码（two's complement）中的模运算（modular arithmetic）、移位语义、溢出判定，以及用位运算实现加法、减法、乘法、除法和比较。完成后，你可以验证：不使用算术运算符，所有整数测试用例都与参考实现逐位相同。

2. **Floating Point** — three-part decomposition of IEEE 754, normalized/denormalized/special values, round-to-even, and bidirectional conversion between integers and floating point. When done, you can verify: `floatScale`, `floatFloat2Int` agree with hardware results at boundaries (`Tmin`, `-0.0`, `Inf`, `NaN`).

   > 译：**浮点数（Floating Point）** — IEEE 754 的三部分分解、规格化/非规格化/特殊值、向偶数舍入（round-to-even），以及整数与浮点数之间的双向转换。完成后，你可以验证：在边界处（`Tmin`、`-0.0`、`Inf`、`NaN`），`floatScale`、`floatFloat2Int` 与硬件结果一致。

3. **Assembly and Procedure Calls** — register usage and calling conventions, stack-frame layout, control-flow recovery (jump tables, loops), return addresses, and the principles of buffer overflow. When done, you can verify: given a piece of machine code without disassembly, you can explain function by function where the arguments are, where the local variables are, and where the return value is.

   > 译：**汇编与过程调用（Assembly and Procedure Calls）** — 寄存器的用途与调用约定（calling conventions）、栈帧布局、控制流恢复（跳转表、循环）、返回地址，以及缓冲区溢出的原理。完成后，你可以验证：给定一段没有反汇编的机器代码，你能逐个函数解释参数在哪里、局部变量在哪里、返回值在哪里。

4. **Storage Hierarchy and Cache** — locality, address splitting, direct-mapped/set-associative/fully associative, LRU and write policies, blocked transpose. When done, you can verify: the three counters output by the self-built simulator are equal item by item to the reference; the miss count of blocked transpose shows the expected U-shape as the block length varies.

   > 译：**存储层次结构与缓存（Storage Hierarchy and Cache）**——局部性（locality）、地址拆分（address splitting）、直接映射/组相联/全相联（direct-mapped/set-associative/fully associative）、LRU 与写策略（write policies）、分块转置（blocked transpose）。完成这部分后，你可以验证：自建模拟器输出的三个计数器与参考结果逐项相等；分块转置的缺失计数（miss count）会随着块长度的变化呈现预期的 U 形。

5. **Linking** — ELF structure, symbol resolution, relocation, and the difference between static and shared libraries. When done, you can verify: the executable produced by the self-built linker for a given set of object files runs correctly, and symbol-conflict errors match the reference.

   > 译：**链接（Linking）**——ELF 结构、符号解析（symbol resolution）、重定位（relocation），以及静态库与共享库的区别。完成这部分后，你可以验证：对给定的一组目标文件，自建链接器生成的可执行文件能正确运行，并且符号冲突错误与参考结果一致。

6. **Processes and Signals** — process creation and replacement, process groups, job control, signal semantics and blocking, and the generation and elimination of races. When done, you can verify: job control has correct state under various interleavings of Ctrl-C / Ctrl-Z / `fg` / `bg`, and leaves no zombie processes.

   > 译：**进程与信号（Processes and Signals）**——进程的创建与替换、进程组、作业控制（job control）、信号语义与阻塞，以及竞态（race）的产生与消除。完成这部分后，你可以验证：在 Ctrl-C / Ctrl-Z / `fg` / `bg` 的各种交错（interleaving）情况下，作业控制都处于正确的状态，并且不留下僵尸进程（zombie process）。

7. **Heap Management** — block layout and alignment, implicit/explicit free lists, segregated fit, coalescing and `realloc`, and the heap checker. When done, you can verify: utilization and throughput both meet the target simultaneously, and the heap checker reports no warnings after every operation.

   > 译：**堆管理（Heap Management）**——块布局与对齐、隐式/显式空闲链表（implicit/explicit free lists）、分离适配（segregated fit）、合并（coalescing）与 `realloc`，以及堆检查器（heap checker）。完成后，你可以验证：利用率与吞吐量（throughput）同时达到目标，并且每次操作之后堆检查器都报告无警告。

8. **Concurrency** — threads and shared state, mutexes and semaphores, producer-consumer, prethreaded server, and using race-detection tools to locate data races. When done, you can verify: results are correct under stress, there is no deadlock, and the detection tool reports clean.

   > 译：**并发（Concurrency）**——线程与共享状态、互斥锁（mutexes）与信号量（semaphores）、生产者-消费者（producer-consumer）、预线程化服务器（prethreaded server），以及使用竞争检测工具（race-detection tools）定位数据竞争（data races）。完成后，你可以验证：在压力下结果正确、没有死锁（deadlock），并且检测工具报告干净。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| modular arithmetic | n. | 模运算 | modular arithmetic in two's complement |
| two's complement | n. | 补码 | in two's complement |
| bit-for-bit | adv. | 逐位地 | bit-for-bit equal |
| decomposition | n. | 分解 | three-part decomposition of IEEE 754 |
| denormalized | adj. | 非规格化的 | normalized/denormalized/special values |
| round-to-even | n. | 向偶数舍入 | round-to-even |
| calling conventions | n. | 调用约定 | register usage and calling conventions |
| stack-frame | n. | 栈帧 | stack-frame layout |
| disassembly | n. | 反汇编 | without disassembly |
| locality | n. | 局部性 | locality |
| blocked transpose | n. | 分块转置 | blocked transpose |
| write policies | n. | 写策略 | LRU and write policies |
| symbol resolution | n. | 符号解析 | symbol resolution |
| relocation | n. | 重定位 | relocation |
| linker | n. | 链接器 | the self-built linker |
| job control | n. | 作业控制 | job control |

## 4. What It Does Not Do

It does not do kernel-mode things: no writing system calls, no writing page-table hardware, no implementing real virtual-memory paging; `memlib` is purely a user-mode simulation.

> 译：它不做内核模式（kernel-mode）的事情：不编写系统调用、不编写页表（page-table）硬件、不实现真正的虚拟内存分页（virtual-memory paging）；`memlib` 纯粹是用户模式（user-mode）的模拟。

It does not pursue full-mark performance: the allocator's throughput is not pushed to the reference limit, only enough to meet the target; the general methodology of performance tuning (profiling-driven iteration) is out of scope.

> 译：它不追求满分性能：分配器的吞吐量不会被推到参考极限，只推到足以满足目标的程度；性能调优的通用方法论（由性能剖析驱动的迭代）不在讨论范围之内。

It does not write attack payloads: buffer overflow is only read to the principle level — stack frames, return addresses, and the role of stack randomization and non-executable stacks; it does not actually construct a getshell string.

> 译：它不编写攻击载荷：缓冲区溢出只讲到原理层面——栈帧、返回地址，以及栈随机化和不可执行栈的作用；它并不实际构造 getshell 字符串。

It does not do networking and protocols: proxy servers and HTTP parsing belong to another project; concurrency here stops at the level of "multithreaded correctness".

> 译：它不做网络与协议：代理服务器和 HTTP 解析属于另一个项目；这里的并发只停留在「多线程正确性」的层面。

It does not teach the language: it does not teach C syntax, Makefile writing, or basic gdb commands; these are prerequisites.

> 译：它不教语言本身：它不教 C 语法、Makefile 编写或基本 gdb 命令；这些是先修要求（prerequisites）。

It does not write the test framework itself: the grader, trace replayer, and reference implementation are considered given; the file under test must not depend on any test header file, must not read the trace, and must not special-case based on input — this is a hard boundary, and crossing it is deemed incomplete.

> 译：它不编写测试框架本身：评分器（grader）、trace 重放器（trace replayer）和参考实现（reference implementation）被视为已给定；被测文件不得依赖任何测试头文件，不得读取 trace，也不得基于输入做特例处理——这是一条硬边界，越过它就被视为未完成。

The freedom of implementation lies in: whether the allocator uses implicit or explicit lists, how many size classes segregated fit uses, the data structures of the Cache simulator, and how the shell's job table is organized — all can be chosen freely, as long as external behavior aligns. A common misstep is "optimize first, then set metrics" — first make the structure pretty, then tune utilization, and finally discover that fragmentation comes from the initial alignment choice, leaving no choice but to start over.

> 译：实现的自由之处在于：分配器（allocator）使用隐式列表（implicit lists）还是显式列表（explicit lists），分离适配（segregated fit）使用多少个大小类（size classes），Cache 模拟器（Cache simulator）的数据结构，以及 shell 的作业表（job table）如何组织——这些都可以自由选择，只要外部行为一致。一个常见失误是“先优化，再设指标”——先把结构做得漂亮，然后调整利用率（utilization），最后发现碎片（fragmentation）来自最初的对齐（alignment）选择，别无选择，只能从头开始。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| kernel-mode | adj. | 内核模式的 | kernel-mode things |
| page-table | n. | 页表 | page-table hardware |
| virtual-memory paging | n. | 虚拟内存分页 | real virtual-memory paging |
| allocator | n. | 分配器 | the allocator's throughput |
| throughput | n. | 吞吐量 | the allocator's throughput |
| profiling-driven | adj. | 性能剖析驱动的 | profiling-driven iteration |
| payload | n. | 载荷 | write attack payloads |
| stack randomization | n. | 栈随机化 | the role of stack randomization |
| non-executable | adj. | 不可执行的 | non-executable stacks |
| proxy server | n. | 代理服务器 | proxy servers and HTTP parsing |
| parsing | n. | 解析 | HTTP parsing |
| concurrency | n. | 并发 | concurrency here stops at |
| prerequisites | n. | 先修要求；前提条件 | these are prerequisites |
| syntax | n. | 语法 | C syntax |
| reference implementation | n. | 参考实现 | the grader, trace replayer, and reference implementation are considered given |
| special-case | v. | 对…做特例处理 | special-case based on input |
