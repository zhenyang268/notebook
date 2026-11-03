# debug-toolchain · 分章详细

## 第 1 章 从崩溃现场开始：signal、core dump、backtrace

**要解决的问题**：进程死掉的那一刻，唯一还留在机器上的证据是内核写下的 core 和信号信息；不会读它，就只能在代码里加 printf 然后重跑碰运气。

**机制**：

一次空指针写会走完整条链路：CPU 触发缺页异常 → 内核判定该地址不可访问 → 向进程投递 `SIGSEGV`，`siginfo_t` 里 `si_code` 是 `SEGV_MAPERR`（地址未映射）或 `SEGV_ACCERR`（权限不对），`si_addr` 是出错地址。信号的默认动作分 TERM / CORE / STOP / IGN，`SIGSEGV`、`SIGABRT`、`SIGBUS`、`SIGILL`、`SIGFPE`、`SIGQUIT` 的默认动作是 CORE，只有这几个默认产生 core。

内核在 `do_coredump` 里做几件事：检查 `RLIMIT_CORE`（`ulimit -c`）、检查进程是否 dumpable（setuid 程序、调过 `prctl(PR_SET_DUMPABLE, 0)` 的不 dump）、读 `/proc/sys/kernel/core_pattern`。pattern 首字符是 `|` 就管道给用户态程序（systemd-coredump、apport 常见如此），core 不落在 cwd，要用 `coredumpctl` 找；否则按 `%p`（pid）、`%e`（可执行名）、`%t`（时间）展开成文件名。

core 文件本身是 ELF core：`PT_LOAD` 段是各内存映射的快照，`PT_NOTE` 里是关键元数据——`NT_PRPSINFO`（命令行）、`NT_PRSTATUS`（每个线程一套寄存器）、`NT_SIGINFO`（信号与 `si_addr`）、`NT_FILE`（每个映射对应的文件与偏移，gdb 靠它把栈帧还原到共享库）、`NT_AUXV`。

backtrace 有两种展开方式。一是帧指针链：`rbp` 指向上一帧的 saved rbp，返回地址在 `rbp+8`，顺着链走即可，代价低但要求 `-fno-omit-frame-pointer`（优化级别下多数编译器默认省略）。二是 DWARF CFI：编译器把「每一行指令处 CFA 怎么算、寄存器存在哪」写进 `.eh_frame`，unwinder 按 PC 查表逐帧恢复，不需要帧指针，`-g` 不是必需（`.eh_frame` 默认生成），但 strip 掉就没了。glibc 的 `backtrace()` 走的是后者。

抓取现场时最需要处理的是“栈已经坏了”和“不安全调用”两种情况：栈溢出要用 `sigaltstack` + `SA_ONSTACK`，否则 handler 自己也没栈可用；handler 里只能调用 async-signal-safe 函数，`backtrace()` 本身通常可用，但 `backtrace_symbols()` 会 malloc，不安全，应改用 `backtrace_symbols_fd()` 写 fd 2，或干脆只把地址写出去事后 `addr2line`。

**最小例子**：

```c
// crash.c
int main(void) { int *p = 0; *p = 42; return 0; }
```

```bash
gcc -g -O0 -o crash crash.c
ulimit -c unlimited
./crash                      # Segmentation fault (core dumped)
gdb -q ./crash core
(gdb) bt
#0  main () at crash.c:1
(gdb) p $_siginfo._sifields._sigfault.si_addr   # (void *) 0x0
(gdb) info registers rip
```

若 `core_pattern` 是管道，改成 `coredumpctl gdb ./crash` 直接进 gdb；`coredumpctl list` 看历史。反汇编级定位用 `x/i $pc`，还原行号用 `addr2line -e ./crash -f -C 0x...`（PIE 程序地址要以 core 里的运行时基址为准）。

**面试高频问法**：

1. 「core 没生成，怎么查？」→ 考点是整条链路而不是单点 → 答：按顺序看 `ulimit -c` 是否为 0（RLIMIT_CORE 会继承）、`/proc/sys/kernel/core_pattern` 是否以 `|` 开头（是就去 `coredumpctl`）、进程是否 setuid 或不可 dump、`/proc/pid/coredump_filter` 是否把该映射排除了、以及目标目录空间。
2. 「backtrace 靠什么拿到调用栈？」→ 考点是帧指针与 CFI 的区别 → 答：要么顺 `rbp` 链，要么查 `.eh_frame` 的 CFI 规则逐帧恢复，前者要求不省略帧指针，后者要求 unwinding 信息没被 strip。
3. 「信号处理函数里能直接 printf 吗？」→ 考点是 async-signal-safe → 答：不能，printf 会拿锁和缓冲，只能调 async-signal-safe 的 `write`、`backtrace_symbols_fd` 这类；要抓栈还得先 `sigaltstack` 并加 `SA_ONSTACK`。
4. 「SIGSEGV handler 正常返回会怎样？」→ 考点是故障指令会被重试 → 答：返回后 PC 回到那条出错指令，再次触发同一信号，通常表现为死循环；要么 `_exit`，要么 `siglongjmp` 跳走，从 handler 正常返回是未定义行为。
5. 「core 里为什么能看到 libc 的栈帧？」→ 考点是 `NT_FILE` → 答：core 记录了每个映射对应的文件和偏移，gdb 依此加载共享库再 unwind；本机库版本对不上时会告警并断在错误帧。

## 第 2 章 gdb / lldb：断点、条件断点与观察点

**要解决的问题**：core 是事后取证，断点是事中拦截；要能把进程停在“变量刚被改坏”的那一瞬间，而不是靠反复加日志重编。

**机制**：

调试器对进程的控制全部经由 `ptrace`：`PTRACE_ATTACH`（或 `PTRACE_SEIZE`）挂上目标并收到一个 stop，`PTRACE_PEEKTEXT` / `POKETEXT` 读写目标内存，`PTRACE_GETREGSET` 读写寄存器，`PTRACE_CONT` / `PTRACE_SINGLESTEP` 推进执行。Linux 上 `ptrace` 受 `/proc/sys/kernel/yama/ptrace_scope` 限制，非子进程 attach 可能被拒。

软件断点是改写指令：把目标地址的首字节存下来换成 `0xCC`（x86 的 `int3`）。执行到那里触发 #BP，内核转成 `SIGTRAP` 交给 tracer，调试器查自己的断点表命中哪一处，把原字节写回、把 PC 减一，然后等你操作；继续运行时再写回 `0xCC`。所以断点只对“能被 ptrace 改写”的代码成立，且改的是运行中进程的内存，不是磁盘文件。

观察点（watchpoint）依赖 x86 调试寄存器：DR0–DR3 放监视地址，DR7 配置是执行、写、还是读写，以及监视长度（1/2/4/8 字节）。硬件槽位只有四个，超了调试器会退化——gdb 的软件观察点靠单步执行、每步比较值来实现，慢一两个数量级。

条件断点不会减少陷入：进程每次到达断点都照样触发 `SIGTRAP`、照样停下来，调试器再求值条件表达式，为假就自动 continue。在一个百万次调用的热函数上挂 `if x == 5`，等于做了百万次上下文切换。想减少停顿，只能在被调试侧判断后用 `raise(SIGTRAP)`，或用 gdb 的 `dprintf`。

lldb 的对应物：`breakpoint set -n func`（按符号）、`-f a.c -l 12`（按行）、`-c 'i==7'`（条件），`watchpoint set variable counter`、`watchpoint set expression -w write -- &x`，attach 用 `process attach --pid`。

**最小例子**：

```c
// w.c
int counter = 0;
int main(void) {
    for (int i = 0; i < 10; i++) counter += i + 1;
    return counter;
}
```

```bash
gcc -g -O0 -o w w.c
gdb -q ./w
(gdb) break w.c:3 if i == 7      # 条件断点：只在 i==7 停
(gdb) run
(gdb) watch counter              # 观察点：counter 每次被写都停
(gdb) continue
Old value = 28
New value = 36                   # i==7 时加 8
(gdb) info watchpoints
(gdb) delete 2
```

lldb 等价：`b w.c:3 -c 'i==7'`、`watchpoint set variable counter`。若目标是已跑飞的服务：`gdb -p $(pidof svc)` 后 `thread apply all bt`，先看所有线程卡在哪把锁上，再决定断点。

**面试高频问法**：

1. 「断点在底层是怎么实现的？」→ 考点是 int3 与 ptrace 的配合 → 答：把目标指令首字节换成 `0xCC`，命中时内核发 `SIGTRAP`，调试器恢复原字节、回退 PC，继续时再写回去。
2. 「为什么 watchpoint 会报无法插入？」→ 考点是硬件调试寄存器 → 答：x86 只有 DR0–DR3 四个槽位，超了就报错或退化成单步比较的软件观察点，后者极慢。
3. 「条件断点为什么在热路径上几乎不能用？」→ 考点是求值发生在陷入之后 → 答：条件不减少陷入次数，每次命中都要停进程交给调试器求值，要么改成代码里判断后 `raise(SIGTRAP)`，要么用 `dprintf`。
4. 「线上进程卡住，怎么不停服地看？」→ 考点是 attach 与全线程栈 → 答：`gdb -p` 挂上去，`thread apply all bt` 一次看全，先判断是死锁、等 IO 还是活锁；注意 `ptrace_scope` 和 attach 期间进程是停的。
5. 「strip 过的 release 程序还能调试吗？」→ 考点是符号层次 → 答：能按地址或动态符号表下断点，但没有行号和局部变量；把 `-g` 产物按 build-id 分离保存，再 `set debug-file-directory` 指过去即可恢复源码级调试。

## 第 3 章 内存错误：ASan 与 Valgrind 的检测原理

**要解决的问题**：越界、use-after-free、未初始化读、泄漏这类错误，症状常常在离根因很远的地方才爆出来；只靠 core dump 只能看到“死在哪”，看不到“谁先写坏了内存”。这一章解决的是：怎样在错误访问发生的那一刻把它拦下来，并给出分配点、释放点和访问点的调用栈。

**机制**：

ASan 走的是“编译期插桩 + 影子内存”路线。编译器在每次 load/store 前插入检查，运行时用一张影子内存记录“这块应用内存是否可访问”。典型映射是每 8 字节应用内存对应 1 字节影子：

```text
shadow_addr = (addr >> 3) + shadow_offset
s = *shadow_addr
if (s == 0)        // 8 字节全可访问
    ok;
else if (s < 0)    // redzone、已释放、栈/全局毒区
    report(addr);
else if ((addr & 7) >= s)  // 只有前 s 字节可访问
    report(addr);
```

真实检查会考虑访问宽度，上面只是单字节访问的简化。影子字节的负值区分 heap-left-redzone、heap-right-redzone、freed、stack、global 等来源，所以报告能直接说 `heap-use-after-free` 或 `stack-buffer-overflow`。ASan 的分配器会在每次 `malloc` 周围加 redzone，并把释放的内存放进 quarantine 延迟复用；栈和全局变量也由编译器插桩加红区。`memcpy`、`strlen`、`free` 等 libc 函数由拦截器包一层，检查传入区间。泄漏检测通常集成在退出时执行，可用 `ASAN_OPTIONS=detect_leaks=1`、`quarantine_size_mb=...` 调整。

Valgrind Memcheck 走的是“动态二进制翻译”路线：不用重新编译，把机器指令翻译成 VEX 中间表示，在合成 CPU 上执行。它维护两类元数据：A 位表示某字节是否可寻址，V 位表示某位是否已定义。因此 Memcheck 能报“条件跳转依赖未初始化值”，而 ASan 默认不查未初始化读，那是 MSan 的职责。Memcheck 通过替换分配器识别堆块边界和释放状态，`--leak-check=full` 给出 definitely/indirectly/possibly/still reachable 分类，`--track-origins=yes` 追未初始化值的来源。

| | ASan | Valgrind Memcheck |
|---|---|---|
| 插桩时机 | 编译期 | 运行时 DBI |
| 主要元数据 | 1/8 影子内存 | A/V 位 |
| 未初始化读 | 不查，需 MSan | 查 |
| 栈/全局越界 | 红区可查 | 主要擅长堆，栈/全局较弱 |
| 代价 | 较低 | 明显更高，具体倍率依程序而定 |

**最小例子**：

```c
// uaf.c
#include <stdlib.h>
int main(void) {
    int *p = malloc(4 * sizeof(int));
    free(p);
    return p[0];
}
```

```bash
cc -fsanitize=address -g -O1 uaf.c -o uaf
./uaf
```

结果会看到 `ERROR: AddressSanitizer: heap-use-after-free`，后面跟 `READ of size 4`、`freed by thread T0 here`、`previously allocated by thread T0 here`，进程以非零状态退出。把同一份代码用 `valgrind --leak-check=full ./uaf_no_asan` 跑，也能报非法读，但需要程序已编译成普通二进制。

未初始化读的例子：

```c
// uninit.c
#include <stdlib.h>
int main(void) {
    int *p = malloc(10 * sizeof(int));
    if (p[3]) return 1;
    free(p);
    return 0;
}
```

```bash
cc -g -O0 uninit.c -o uninit
valgrind --track-origins=yes ./uninit
```

结果包含 `Conditional jump or move depends on uninitialised value(s)`，并指出来源是堆分配。注意：Memcheck 不是“读未初始化就立刻报”，而是当未初始化值影响分支、地址计算或系统调用等可观察行为时才报。

**面试高频问法**：

- **ASan 为什么通常比 Valgrind 快？** → 考点：插桩时机与元数据粒度 → 答：ASan 在编译期插入检查，运行时只查一张 1/8 映射的影子内存；Valgrind 要用 DBI 翻译并模拟执行，还要维护逐字节的 A/V 位，开销明显更高。
- **ASan 的影子内存怎么映射？** → 考点：是否理解 `addr >> 3` 和影子字节语义 → 答：每 8 字节应用内存对应 1 字节影子，影子值为 0 表示 8 字节全可访问，1 到 7 表示前 N 字节可访问，负值表示 redzone、已释放或毒区。
- **ASan 能查未初始化读吗？** → 考点：ASan/MSan/Valgrind 的分工 → 答：默认不能，未初始化读要用 MSan；Valgrind Memcheck 也能查，因为它维护 V 位。
- **ASan 的 redzone 和 quarantine 各解决什么？** → 考点：误报与漏报的权衡 → 答：redzone 让越界访问落到毒区，quarantine 延迟释放内存复用，让 use-after-free 更容易在释放后立刻暴露；代价是内存占用。
- **Valgrind 报 `still reachable` 就是泄漏吗？** → 考点：泄漏分类 → 答：不一定，它表示退出时仍可达；真正可疑的是 definitely lost 和 indirectly lost，still reachable 往往只是全局缓存没释放。

## 第 4 章 未定义行为：UBSan 能抓什么、抓不到什么

**要解决的问题**：未定义行为（UB）不是“结果不确定”这么简单，而是编译器可以假设它永不发生，进而删分支、改循环、做激进优化。等出错时，源码已经和机器码对不上。这一章解决的是：用 UBSan 把一部分 UB 变成运行时可见的检查，同时明确它的边界，避免“开了 UBSan 就安全”的错觉。

**机制**：

UBSan 是编译期插桩：编译器在可能触发某类 UB 的操作前插入条件检查，失败时调用运行时处理器。典型开关是 `-fsanitize=undefined`，常用组合：

```bash
cc -fsanitize=undefined -fno-sanitize-recover=undefined -g -O1 ub.c -o ub
UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1 ./ub 1
```

默认是 recover 模式：打印 `runtime error: ...` 后继续执行。要让 CI 把它当错误，需要 `-fno-sanitize-recover=undefined` 或 `UBSAN_OPTIONS=halt_on_error=1`。`print_stacktrace=1` 让报告带栈。

`-fsanitize=undefined` 覆盖的检查组按编译器版本而定，常见包括：有符号整数溢出、移位位数越界或负数移位、整数除零、空指针解引用（配合 null 检查）、非对齐访问、非法的 bool/enum 值、VLA 边界、部分 object-size、返回检查、`unreachable`、指针溢出等。它不包含无符号溢出，因为无符号回绕在 C/C++ 中是定义行为；浮点除零默认也常不在 `undefined` 组里，具体看实现。

抓不到的部分同样重要：

- 未初始化读：UBSan 不跟踪定义性，要用 MSan 或 Valgrind。
- 堆 use-after-free、指针退化后的越界：UBSan 没有堆红区，要用 ASan。
- 数据竞争：要用 TSan。
- 严格别名违规、对象生命周期、ODR 违规、跨翻译单元的类型不一致：UBSan 通常不查。
- 已经被编译器优化掉的 UB：编译器基于“UB 不发生”删掉了代码，插桩点可能不存在，或者不再对应源码语义。
- 未插桩的库：检查只存在于被编译插桩的翻译单元里。

所以 UBSan 的定位是“低成本抓一类特定 UB”，不是内存安全的全集。

**最小例子**：

```c
// ub.c
#include <limits.h>
int main(int argc, char **argv) {
    int x = INT_MAX;
    if (argc > 1) x += argc;
    return x;
}
```

```bash
cc -fsanitize=undefined -fno-sanitize-recover=undefined -g -O1 ub.c -o ub
./ub 1
```

`argc` 为 2，执行 `INT_MAX + 2`，输出类似：

```text
runtime error: signed integer overflow: 2147483647 + 2 cannot be represented in type 'int'
```

进程以非零状态终止。若去掉 `-fno-sanitize-recover=undefined`，默认只打印并继续，返回值可能仍是截断后的结果。

抓不到的例子：

```c
// miss.c
int main(void) {
    int x;
    return x;   // 未初始化读，UBSan 不报
}
```

```bash
cc -fsanitize=undefined -g -O0 miss.c -o miss
./miss
```

UBSan 不会报；Valgrind 或 MSan 才会指出未初始化值。另一个常见边界是数组退化成指针后丢失边界：

```c
int a[4];
int *p = a;
return p[4];   // UBSan 的 bounds 检查看不到 p 的边界，ASan 能抓
```

**面试高频问法**：

- **UBSan 和 ASan 的区别是什么？** → 考点：UB 检查与内存错误检查的分工 → 答：UBSan 在编译期插入针对特定 UB 的条件检查；ASan 用影子内存和红区查越界、UAF 等内存错误，二者互补。
- **UBSan 能抓哪些 UB？** → 考点：是否知道检查组边界 → 答：常见的有符号溢出、移位越界、整数除零、空指针、非对齐、非法 bool/enum、VLA 边界等，具体组按编译器版本而定。
- **为什么开了 UBSan 还没报？** → 考点：是否理解“只查被插桩且执行到的检查” → 答：可能路径没执行、优化把 UB 删了、检查组没开、库没插桩，或者默认 recover 模式只打印没终止。
- **UBSan 能替代 ASan/TSan 吗？** → 考点：工具边界 → 答：不能；它不查堆 UAF、指针退化越界、未初始化读和数据竞争，这些分别要 ASan、MSan/Valgrind、TSan。
- **CI 里怎么让 UBSan 真正失败？** → 考点：recover 模式 → 答：加 `-fno-sanitize-recover=undefined`，或设 `UBSAN_OPTIONS=halt_on_error=1`，再配合 `print_stacktrace=1` 定位。

## 第 5 章 数据竞争：TSan 的报告怎么读

**要解决的问题**：数据竞争是「跑一万次挂零次、上线才炸」的那类 bug，靠复现和加日志几乎抓不到；TSan 把它从概率问题变成确定性的报告，这一章解决「报告里那两段栈到底在说什么、什么才算真竞争」。

**机制**：

TSan 是编译器插桩 + 运行时库的组（`-fsanitize=thread`，Clang/GCC 都有）。它在编译期为每个内存访问插入检查调用，运行时维护**影子内存**：把每个 8 字节应用内存映射为 4 个状态，每状态记录该字节区间的 4 个状态槽（状态 = 读/写 + 访问它的线程 + 该线程的逻辑时钟）。一次访问要做「本次访问 vs 影子槽里历史访问」的冲突判定。

核心算法是 **happens-before（HB）**，不是锁集。TSan 为每个线程维护一个**向量时钟**（vector clock：长度 = 线程数的数组，`VC[t]` 是线程 t 已知的进度）。同步事件传递时钟：

```text
线程 A: write(x)                    // 影子槽: {addr=x, tid=A, clock=A的VC, write}
线程 A: pthread_mutex_unlock(m)     // 把 A 的 VC 记进 mutex 的释放时钟
线程 B: pthread_mutex_lock(m)       // B 的 VC = max(B.VC, m.VC)  → 建立 HB
线程 B: read(x)                     // 检查: 槽里是 A 的写，
                                    // 若 A.VC ≤ B.VC 则已 HB，无竞争；
                                    // 否则报告 data race
```

判定条件：两个访问访问同一地址、至少一个是写、来自不同线程、且它们之间**不存在 happens-before 关系**。四种同步原语是 TSan 认识并用于建立 HB 的：mutex、原子操作（含 `memory_order` 语义）、线程 create/join、条件变量（通过关联的 mutex）。裸的 `volatile`、自己实现的 spinlock（如果用的是普通 load/store 而非原子）、无锁队列里的手工屏障，TSan 都看不见，会报**误报**。

报告结构固定三段：

1. **WARNING: ThreadSanitizer: data race**，紧跟读写类型和地址；
2. **Write of size N at 0x... by thread T1**：肇事访问的栈，带 `#0 #1 ...` 帧和源行号；
3. **Previous read/write of size N at 0x... by thread T2**：与之冲突的历史访问栈；
4. 尾部 **Location is heap/global/stack** 说明对象在哪，以及 **Thread T1/T2 (TID) created by ...** 给出线程创建栈 —— 这段经常被忽略，但它是定位「谁该负责同步」的关键。

关键运行参数：`TSAN_OPTIONS="halt_on_error=0 second_deadlock_stack=1 history_size=7"`。`halt_on_error=0` 让它在首个竞争后继续跑（默认是继续的，但很多 CI 会设成 1）；`history_size` 控制每个影子槽保留多少历史访问，调大可抓更早的冲突，代价是内存。**内存开销约 5–10 倍，速度 5–15 倍 slowdown**（官方文档口径，按实现与负载而定）。TSan 不能与 ASan 同时开。

**最小例子**：

```c
// race.c
#include <pthread.h>
int g;
void *f(void *p){ g++; return 0; }          // 非原子读改写
int main(){ pthread_t a,b;
  pthread_create(&a,0,f,0); pthread_create(&b,0,f,0);
  pthread_join(a,0); pthread_join(b,0); }
```

```bash
clang -fsanitize=thread -g -O1 race.c -o race && ./race
```

输出（节选，真实格式）：

```text
WARNING: ThreadSanitizer: data race (pid=12345)
  Write of size 4 at 0x... by thread T2:
    #0 f race.c:3 (race+0x...)
  Previous read of size 4 at 0x... by thread T1:
    #0 f race.c:3
  Location is global 'g' of size 4 at 0x... (race+0x...)
  Thread T2 (tid=...) created by main thread at:
    #0 pthread_create ...
    #1 main race.c:5
```

读法：两段栈**指向同一行同一地址**、`by thread T1/T2` 不同、中间没有 `mutex`/`atomic` 帧 → 真竞争。若是全局变量（`Location is global 'g'`），不用看堆栈也能确定对象；若是 `Location is heap` 且两栈里有 `malloc`，说明是某个被共享的堆对象，顺着创建栈找归属线程。

**面试高频问法**：

1. **「TSan 用什么算法检测竞争？和锁集（lockset）方法有什么区别？」**
   → 考点是 HB vs Eraser 类锁集算法。答法：「TSan 用 happens-before：给线程维护向量时钟，同步事件传时钟，两个访问无 HB 关系且至少一个写就报。锁集算法只看『访问时持有哪些锁』，会漏掉用原子操作或无锁结构建立的同步，误报多；HB 更精确但有假阴性——没被执行到的路径抓不到。」

2. **「TSan 报了一次竞争，但我觉得有锁保护，为什么？」**
   → 考点是 TSan 只认标准同步原语。答法：「先确认保护是不是 TSan 认识的：`pthread_mutex`、原子操作、`std::atomic`、create/join。如果是 `volatile` 当同步、自旋锁用普通读写实现、或者用了手写内存屏障，TSan 看不到 HB，就会误报。另外要确认两段栈确实访问同一地址——报告里的地址相同才是真冲突。」

3. **「TSan 的假阴性从哪来？」**
   → 考点是动态分析的固有局限。答法：「三个来源：一是没执行到的代码路径不插桩不检查；二是 HB 只覆盖它看得见的同步，跨进程共享内存、信号处理里的访问它管不了；三是 `history_size` 有限，早期访问被挤出影子槽后，新访问找不到冲突对象。所以 TSan 干净不等于没竞争，只能说不存在它可见的竞争。」

4. **「报告里 `Thread T1 created by` 那段有什么用？」**
   → 考点是会不会读完整报告。答法：「它给线程创建栈，能反推哪个线程负责这个共享对象的生命周期。常见场景是库在内部起工作线程，业务代码不知道这个对象被跨线程访问了；顺着创建栈能找到 fork 点，判断该在哪一层加锁或者改成线程私有。」

5. **「TSan 能不能和 ASan 一起用？线上能开吗？」**
   → 考点是工程约束。答法：「不能同时开，两者都改影子内存布局、都拦 `malloc`，运行时互斥。线上一般不开，内存 5–10 倍、速度 5–15 倍的开销太大；正确做法是在 CI 里跑带 TSan 的构建，或者对已知高风险的模块单独做 TSan 版本压测。TSan 的报告要当断言看，不能当警告忽略。」

---

## 第 6 章 系统调用层：strace、ltrace 与 dtruss

**要解决的问题**：程序「卡住了」「返回 ENOENT 但文件明明在」「权限没问题却打不开」——这些问题的答案在用户态代码之下，需要看进程与内核的边界上到底发生了什么。这一章解决「什么时候该下沉到 syscall 层、以及看到的那行 `= -1 EACCES` 该怎么解读」。

**机制**：

三者都是**跟踪器（tracer）**模式，靠内核的 ptrace 机制工作：

- **strace**：Linux，跟踪**系统调用**。用 `PTRACE_SYSCALL` 让被跟踪进程在每次进出内核时停住，读寄存器（x86-64 上是 `orig_rax` 取 syscall 号、`rdi/rsi/rdx/r10/r8/r9` 取前六个参数、`rax` 取返回值），再按 syscall 表格式化成人类可读文本。所以 strace 能看到 `openat` 的路径、`read` 的 fd、`write` 的字节数，但**看不到**用户态函数调用。
- **ltrace**：Linux，跟踪**动态库函数调用**（PLT 层）。原理是给目标进程的 PLT/GOT 打桩或单步，因此能看到 `malloc`、`strcpy`、`pthread_mutex_lock` 这类库函数，但代价大、对静态链接和 `-fno-plt` 无效，实用性远低于 strace。
- **dtruss**：macOS/BSD 上的对应物，底层是 DTrace。用法和 strace 类似但语法不同：`sudo dtruss -f ./prog`，参数过滤靠 `-t` 或 DTrace 脚本。macOS 上还有 `ktrace`/`kdv` 但日常用 dtruss。**没有 strace 的 macOS 等价便利性**，SIP 保护下对系统二进制常需要关 SIP，这是实际踩坑点。

strace 常用参数（这些是核心考点）：

```bash
strace -f -o out.txt ./prog        # -f 跟踪子进程/线程（fork/vfork/clone 后的），-o 写文件
strace -e trace=openat,read,write ./prog   # -e trace= 只留指定 syscall
strace -e trace=file ./prog        # 所有带路径名的 syscall（open/stat/unlink...）
strace -e trace=network ./prog     # 网络类
strace -p 1234                     # attach 到运行中进程
strace -c ./prog                   # 汇总：每个 syscall 的次数、耗时、错误数
strace -T -tt ./prog               # -T 每行耗时，-tt 绝对时间戳
strace -y ./prog                   # 把 fd 翻译成路径（打开的文件）—— 定位 fd 泄漏利器
strace -k ./prog                   # 打印每行用户态栈（需内核支持，按实现而定）
```

读结果的关键是**返回值语义**：成功返回那个值（`openat` 返回 fd 数字、`read` 返回字节数），失败返回 `-1` 并跟 `EXXX`。`= -1 ENOENT (No such file or directory)` 和 `= -1 EACCES (Permission denied)` 是两类完全不同的问题；`= ? ERESTARTSYS` 表示被信号打断后重启，通常是正常的。另外注意 `openat(AT_FDCWD, "x", ...)` 里的 `AT_FDCWD` 表示相对当前工作目录——很多「文件找不到」其实是 cwd 不对，不是路径拼错。

**最小例子**：

```bash
# 场景：程序说找不到配置文件
strace -f -e trace=file -o /tmp/tr.txt ./app
grep -E 'ENOENT|EACCES' /tmp/tr.txt | head
```

输出（典型形态）：

```text
openat(AT_FDCWD, "/etc/app/conf.yml", O_RDONLY) = -1 ENOENT (No such file or directory)
openat(AT_FDCWD, "./conf.yml", O_RDONLY)        = 3
read(3, "port: 8080\n", 4096)                   = 11
```

结论：程序先找 `/etc/app/conf.yml` 失败，回落到 cwd 下的 `./conf.yml` 成功。如果线上报「配置没生效」，而这一行显示读的是 `./conf.yml`，那就是**工作目录不对**——systemd 的 `WorkingDirectory`、容器的 `WORKDIR`、cron 的 cwd 都是常见根因，改配置路径不如改成绝对路径。

再看 `strace -c` 的用途：如果某 syscall 的 `seconds` 占比异常高（典型如大量 `futex` 阻塞，或 `read` 在大文件上慢），说明瓶颈在内核侧而非业务逻辑。而 `strace -y` 输出里的 `read(3</var/log/app.log>, ...)` 能一眼看出 fd 3 是哪个文件——排查「句柄泄漏」「write 到已经该关闭的文件」时，比猜 fd 号快得多。

**面试高频问法**：

1. **「strace 是怎么实现的？为什么它能让程序变慢很多？」**
   → 考点是 ptrace 与上下文切换成本。答法：「基于 ptrace 的 `PTRACE_SYSCALL`，被跟踪进程每次进内核和出内核都会停下来通知 tracer，tracer 读寄存器再放行，等于每个 syscall 加两次上下文切换加一次进程间通信。所以高频 syscall 的程序 slowdown 可能到几十倍，生产上只能短时 attach，不能常开。」

2. **「`strace -f` 不加会怎样？为什么有些子进程的 syscall 看不到？」**
   → 考点是跟踪范围。答法：「不加 `-f` 只跟踪主进程，fork/clone 出来的子进程和线程默认不被跟踪，它们的 syscall 全部丢失。加了 `-f` 才会跟随 fork/vfork/clone，输出里用 `[pid 1234]` 前缀区分。注意线程在 Linux 上也是 clone 出来的，多线程程序的 syscall 基本都要 `-f` 才完整。」

3. **「程序打开文件失败，strace 显示 `= -1 ENOENT`，但文件确实存在，怎么解释？」**
   → 考点是路径解析与 cwd/namespace。答法：「三种常见原因：一是 `AT_FDCWD` 相对的路径，实际 cwd 和你以为的不一样（systemd/容器/cron 的 cwd）；二是路径中间某一级目录不存在或没权限，`ENOENT` 报的是解析链上失败的那一段；三是 mount namespace 或 chroot 不同，进程看到的文件系统和 shell 里看到的不是同一个。用 `strace -y` 和 `/proc/<pid>/cwd`、`/proc/<pid>/root` 交叉验证。」

4. **「strace 和 ltrace 该选哪个？为什么 ltrace 用得少？」**
   → 考点是跟踪层次与可用性。答法：「strace 看内核边界（syscall），ltrace 看用户态动态库调用。选 strace 优先，因为几乎所有 I/O、内存映射、进程创建、网络都在 syscall 层可见。ltrace 实现依赖 PLT 打桩，对静态链接、`-fno-plt`、内联后的调用都失效，而且开销更大，实际排查价值有限。」

5. **「macOS 上怎么替代 strace？」**
   → 考点是跨平台工具链常识。答法：「用 `sudo dtruss -f ./prog`，底层是 DTrace，参数过滤语法和 strace 不同（`-t` 或写 DTrace 脚本）。注意 SIP 保护下跟踪系统二进制常需关 SIP；另外 Apple Silicon 上部分场景受限制。跨平台项目最好把 syscall 层排查写成脚本，别把 strace 参数硬编码进流程。」

## 第 7 章 资源与运行时：/proc、lsof、perf 的调试用法

**要解决的问题**：崩溃现场告诉你"死在哪"，但线上更常见的是"没死但不正常"——内存涨、句柄漏、磁盘满、CPU 打满却不知道在跑什么。这一章提供三把不改代码、不重启进程的望远镜：进程现在长什么样（/proc）、它攥着什么资源（lsof）、时间花在哪（perf）。没有它们，你只能加日志再等下一次故障。

**机制**：

`/proc` 是伪文件系统，内容不是存在磁盘上的，而是**每次 read 时由内核现场生成**。所以它给的是"读的那一刻"的快照，不是流；也意味着读取有成本，`smaps` 要遍历页表，比 `status` 贵得多。

```text
/proc/<pid>/status      VmRSS / Threads / State，一行一个字段，便宜
/proc/<pid>/maps        虚拟地址段 + 权限 + 后备文件，看映射来源
/proc/<pid>/smaps_rollup  各段 RSS 汇总（Pss/Anonymous/File），贵但准
/proc/<pid>/fd/         每个 fd 一个符号链接，指向真实路径，删了带 " (deleted)"
/proc/<pid>/task/<tid>/ 每线程子目录，stack/wchan 看内核栈与阻塞点
/proc/<pid>/limits      RLIMIT_NOFILE 等，句柄上限的真相在 ulimit -n 之外
/proc/<pid>/io          rchar/wchar/read_bytes，判断是不是真在 IO
```

`lsof` 在 Linux 上不是魔法：它枚举 `/proc/*/fd` 做 `readlink`，再配上 `/proc/*/maps`、`/proc/net/*`，反查 inode 到路径。所以它的复杂度约是 `进程数 × fd 数`，机器上进程多时会明显慢——这不是 bug，是数据源决定的。`lsof +L1` 专查 link count < 1 的已删除但仍被打开的文件，是磁盘"空间不见了"的第一招。

`perf` 有两条完全不同的路径：`perf stat` 是**计数**（读 PMU 或软件事件计数器，几乎零开销）；`perf record` 是**采样**（每 N 个事件或每 T 时间触发一次中断，记录当时的 IP 和调用栈）。采样周期 $T = 1/f$，窗口 $W$ 内样本数约 $f \cdot W$，所以比例是从样本里估出来的，不是精确值。`perf trace` 走 tracepoint 而不是 ptrace，能看到系统调用但不等价于 strace 的逐次拦截。

常见的采样命令骨架：

```bash
perf record -F 99 -g -p <pid> -- sleep 10   # 99Hz 采样 10s，带调用栈
perf report -i perf.data --stdio            # 按符号聚合，看 self% 与 children%
perf stat -p <pid> -e cycles,cache-misses -- sleep 5
```

栈的获取方式决定成败：`-g` 默认按构建而定，可能是帧指针。用 `-fno-omit-frame-pointer` 编译时 `--call-graph fp` 便宜且够用；重度优化、帧指针被省掉时用 `--call-graph dwarf`，靠 DWARF 展开栈，代价是每次采样要 dump 更大一块用户栈，且受栈大小限制。JIT 出来的代码在 `maps` 里是可执行匿名段（无文件名），perf 只能显示裸地址，需要 JIT 侧导出符号表（如 perf map 文件）才能解析。

**最小例子**：磁盘告警，`df` 显示写满，但 `du -sh /var/log` 只有几十 M——典型的"删了但没关"。

```bash
$ lsof +L1
COMMAND   PID USER  FD   TYPE DEVICE    SIZE/OFF NLINK     NODE NAME
app      4412 app   7w   REG  253,0 21474836480     0   918273 /var/log/app/access.log (deleted)
```

拿到了 pid 和 fd 号，不用重启也能救回来：

```bash
$ cp /proc/4412/fd/7 /var/log/app/access.recovered.log
```

注意 `: > 文件` 这种"清空"手法对已删除文件无效——路径已经不存在了，只能走 fd。定位到根因后再查代码：日志轮转用 `rename` 还是 `unlink`，决定了要不要通知进程重开文件。

**面试高频问法**：

1. **"进程 RSS 一直涨，怎么用 /proc 判断是真泄漏还是缓存？"** → 考点是区分匿名页与文件页。答法：连续采 `/proc/<pid>/smaps_rollup`，看 `Anonymous` 单调涨就是泄漏嫌疑，`File`/`Pss` 涨且能被回收多半是页缓存；再对照 `/proc/<pid>/status` 的 VmRSS 趋势和 GC 后是否回落。

2. **"lsof 在几千进程的机器上很慢，为什么？"** → 考点是工具的实现代价。答法：它在 Linux 上遍历 `/proc/*/fd` 和 `/proc/*/maps` 做反查，复杂度随进程数和 fd 数增长；所以线上优先直接 `ls -l /proc/<pid>/fd` 只查一个进程。

3. **"perf record 和 strace 都能看程序在干什么，开销差在哪？"** → 考点是采样 vs 陷入。答法：perf 靠硬件/软件事件周期性中断采样，只记录 IP 和栈，开销与频率成正比；strace 每次系统调用都要 ptrace 停住并切换上下文，是逐次拦截，对高频 syscall 的程序可能慢一个量级。

4. **"perf 出来的栈全是十六进制地址或 `[unknown]`，怎么排查？"** → 考点是栈展开与符号。答法：先确认有没有帧指针（没有就换 `--call-graph dwarf`），再确认二进制有没有被 strip、调试符号是否装；匿名可执行段说明是 JIT 代码，需要 JIT 导出 perf map。

5. **"容器里的 `/proc/meminfo` 能代表这个容器的内存上限吗？"** → 考点是命名空间边界。答法：不能，`meminfo` 多数字段是宿主视角；容器限额在 cgroupfs 里（v2 的 `memory.max`/`memory.current`/`memory.events`），OOM 证据要去那里找。

## 第 8 章 日志与可观测性：结构化日志、trace id、最小复现

**要解决的问题**：前七章解决"故障发生时我在场"；这一章解决"故障发生时我不在场"。线上问题的事后证据几乎只有日志，但如果日志是一句拼好的字符串、没有关联 id、也不知道当时参数，那它只能证明"出过事"，不能帮你复现。这一章的目标是让每条日志都能被机器筛选、被跨进程 join、并最终压成一条能重跑的命令。

**机制**：

结构化日志的本质是：**日志是一条事件记录，不是一个句子**。写入端不做字符串拼接，而是给字段；序列化交给 encoder（JSON 或 logfmt）。schema 要固定：`ts`、`level`、`msg`、`service`、`trace_id`、`span_id`、`pid/tid`、业务主键、`err`（拆成 type / message / stack）。固定 schema 的价值在于可以按字段聚合和告警，而 `grep "timeout"` 不是聚合。

关键纪律是基数控制：`user_id`、`request_id` 这类高基数字段不要做成日志系统的索引标签/label，否则时间序列基数爆炸；它们应该留在日志正文里被检索，而不是变成 metric 维度。

trace id 的传播是这套东西的骨架。跨进程用 W3C Trace Context 的 `traceparent` 头：`00-<32 位十六进制 trace-id>-<16 位 parent-id>-<flags>`，网关或入口服务生成，后续每一跳透传。进程内不要靠"随手传参"，而是放进请求上下文，由日志组件自动注入：

```python
# 伪代码：context 承载 trace 上下文，日志组件自动读取
def handle(req):
    ctx = extract(req.headers.get("traceparent")) or new_trace()
    with trace_context(ctx):              # 绑定到当前执行上下文
        log.info("order.create", order_id=oid, amount=amt)
        executor.submit(with_context(ctx, charge, oid))  # 跨线程显式携带
```

三个容易丢的地方：线程池提交任务时（ThreadLocal 不会自动过去）、异步回调/协程切换时、消息队列投递时（trace 上下文要写进消息头）。丢一处，链路就断成两截，而这恰恰是最需要证据的跨服务段。

最小复现是这条链的终点：从 trace 里找到**第一个**异常 span，把它前后的字段抽出来，固定输入、剥离环境、压掉并发，得到一个能反复跑的东西。降维按三条轴走：输入（哪个参数、哪条数据）、环境（配置、版本、时区、locale、内核/libc）、时序（并发度、重试、超时）。如果压到单线程单请求仍然复现不了，那结论本身就很有价值——它是并发或时序问题，需要用压力或确定性重放（如 rr 的 record/replay）来打。

**最小例子**：三个服务串一次下单，用户报"偶发下单失败"。先按 trace id 把日志捞齐：

```bash
$ grep -h '"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"' /var/log/{gw,order,pay}/*.log
{"ts":"...","level":"info","svc":"gw","msg":"order.create","trace_id":"4bf9...4736","order_id":"A17","amount":199}
{"ts":"...","level":"warn","svc":"order","msg":"pay.call.retry","trace_id":"4bf9...4736","attempt":3,"elapsed_ms":2870}
{"ts":"...","level":"error","svc":"pay","msg":"pay.charge.failed","trace_id":"4bf9...4736","err.type":"TimeoutError","err.msg":"deadline exceeded"}
```

看到 `attempt:3` 和 `elapsed_ms:2870`，怀疑是上游重试把下游的时间预算吃光了。把它压成一条本地复现：固定 `order_id=A17`、`amount=199`、下游延迟注入 3s、重试 3 次，用同一份代码跑单测——复现出来，就不是"偶发"，是"重试预算没扣减"。

**面试高频问法**：

1. **"结构化日志和 `printf` 日志的本质区别是什么？"** → 考点是可否被机器消费。答法：结构化日志输出字段而非句子，schema 固定，能按字段聚合、告警、和 trace 关联；拼接字符串只能人肉 grep，字段一旦变格式就全废。

2. **"trace id 怎么跨线程池和消息队列传？"** → 考点是上下文传播的边界。答法：显式携带，不能裸用 ThreadLocal——线程池提交时用包装器把上下文绑到任务上，队列投递时写进消息头，消费端先 extract 再绑定；否则子任务日志里 trace_id 为空或串到别的请求上。

3. **"采样怎么做才不会把有价值的请求丢掉？"** → 考点是头部采样与尾部采样的取舍。答法：头部采样在入口按概率 $p$ 决定，实现简单但会丢掉大部分错误请求；尾部采样先缓冲整条 trace，按状态码/延迟决定留不留，能保住错误和慢请求，代价是要缓冲和额外内存。

4. **"线上日志该写什么、不该写什么？"** → 考点是安全与成本。答法：写事件名 + 业务主键 + 错误类型 + 关键数量；不写密钥、token、完整 PII、超大 payload；高基数 id 不要做成索引标签，否则日志系统基数爆炸。

5. **"给你一个线上 bug，你怎么做出最小复现？"** → 考点是方法论而非工具。答法：先从 trace 定位第一个异常 span，抽出当时输入与配置，固定输入、剥离环境、降到单线程单请求；还复现不了就判定为并发/时序问题，用加压或 rr 重放；最后把复现步骤固化成一条能跑的命令或一个失败的测试用例。
