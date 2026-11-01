# CSAPP · 系统级编程实验 · 设计文档

> 本文是该项目的设计说明，不是教程。
> 大纲见 `OUTLINE.md`，一小时上手见 `QUICK.md`，详细记录见 `NOTES.md`。

## 一、定位与边界

本项目是 CMU 15-213 四个 lab（datalab、cachelab、shlab、malloclab）的自建实现与判分框架，目标是用必须通过机器判分的代码，来验证 408 组成原理与操作系统中被抽象掉的部分：Cache 的映射与替换、进程与信号的语义、堆管理器的块布局。

它解决什么：让“组相联”“僵尸进程”“首次适配”“round-to-even”这些在教材里只以文字成立的结论，被写成可执行的断言，并给出可以量化的判分结果。

它不解决什么：不教 C 语法，不教 x86-64 汇编语义（属于 bomblab/attacklab 的领域），不涉及并发同步与网络协议（pthread lab、proxy lab），也不实现真实文件系统与虚拟内存的页表硬件。性能调优的通用方法论同样不在范围内。对象只到“机制验证”，不到“系统构建”。

与相邻项目的分工：本项目做单机机制验证；逆向类项目做指令级；并发与网络类项目在其基础上做协议层与同步层。

## 二、整体架构

五个模块，单向依赖，被测代码永远不反向依赖测试代码。

- `common/`：Makefile 片段、trace 解析器、高精度计时（`clock_gettime(CLOCK_MONOTONIC)`）、结果汇总与退出码。
- `datalab/`：`bits.c` 是唯一可改文件；`btest`、`dlc`、`tests.c` 只读。
- `cachelab/`：`csim.c` 实现 LRU 模拟器，`trans.c` 实现分块转置；共用一个 trace 驱动。
- `shlab/`：`tsh.c` 单文件 shell，配 pty 驱动的 trace 回放器。
- `malloclab/`：`mm.c` 分配器，`memlib.c` 提供模拟堆，`mdriver` 计算利用率与吞吐。

调用方向统一为：`make check LAB=x` → 该 lab 的 driver `main` → 加载测试数据 → 链接或子进程方式调用被测函数 → 判分器比对参考输出 → `common/` 汇总。硬性约束：被测文件不得 `#include` 任何测试头文件，不得读取 trace 文件，不得依据输入内容做特判。

## 三、技术选型与理由

**C11 而非 Rust/C++**：malloclab 需要手工控制 8 字节对齐的块布局与裸指针算术，Rust 的借用检查会把空闲链表逼成大片 `unsafe`，反而丢掉教学价值；C++ 的隐式构造与异常会在 `-O2` 下干扰堆行为可预测性。

**gcc `-O2 -Wall -Wextra` 而非 `-O0`**：malloclab 的吞吐必须在优化后测量，`-O0` 下的性能指数没有意义。clang 作为第二编译器做交叉验证，用于发现未定义行为依赖。

**POSIX/Linux 而非 Windows**：shlab 依赖 `fork`/`setpgid`/`kill`/`waitpid`/`sigprocmask` 的确切语义，Windows 无对应物。WSL2 可用，但 pid 命名空间与终端作业控制行为存在差异，需在 README 标注。

**Make 而非 CMake**：四个独立 lab 无跨语言依赖，Makefile 更贴近 handout 原貌，也便于学生直接读。

**gdb + valgrind + perf 而非 printf**：malloclab 的堆破坏表现为延迟崩溃，必须靠 valgrind 定位；但 valgrind 只在功能测试阶段启用，因为会彻底破坏吞吐测量。

## 四、数据流

以 `make check LAB=cachelab` 为典型一次运行：

输入是 trace 文本行，形如 `L 10,1`、`M 20,4`、`S 18,1`。解析后得到关键结构 `struct memop { char op; unsigned long addr; int size; }`。

Cache 状态用二维数组表示：

```c
struct line { int valid; unsigned tag; unsigned lru; };
struct line cache[1 << S][E];
unsigned lru_clock;
```

地址切分：$set = (addr \gg b)\,\&\,((1 \ll S)-1)$，$tag = addr \gg (b+S)$。命中则刷新 `lru`；缺失时优先占用无效行，否则淘汰 `lru` 最小者并计一次 eviction。输出为 `hits:N misses:N evictions:N`，与参考输出逐行比对。

其余三个 lab 的数据流同构：shlab 是 trace 文本 → pty 注入 → `tsh` 逐行解析 → `job_t jobs[MAXJOBS]` 状态机（UNDEF/FG/BG/ST）→ 输出比对；malloclab 是 11 条 trace 的 (alloc/free/realloc, size) 序列 → `mm_malloc` → 堆镜像 → 利用率与吞吐统计。

## 五、章节目录与知识点映射

| 章 | 内容 | 涉及的知识点 | 与考纲或前置项目的关系 |
|---|---|---|---|
| datalab-1 | 整数位运算 12 题 | 补码表示、算术右移与逻辑右移、移位量对字长取模、$|tmin|=tmin$、除 $2^k$ 的偏置修正、无分支比较、二分法位计数 | 408 组成原理「数据的表示与运算」 |
| datalab-2 | 浮点 3 题（`float_neg`/`float_i2f`/`float_twice`） | IEEE 754 单精度 1-8-23 布局、隐藏位、非规格化数、round-to-even、尾数进位溢出到指数域 | 408 浮点数表示与舍入规则 |
| cachelab-1 | LRU 模拟器 `csim` | 地址划分为 tag/set/offset、直接映射与 $E$ 路组相联、LRU 替换、命中/缺失/驱逐计数 | 408 存储系统 Cache 映射方式与替换算法 |
| cachelab-2 | 矩阵转置 `trans` | 空间局部性、块划分、一行 32 字节恰容纳 8 个 int、32×32 每 8 行同集冲突、64×64 的 4×4 子块与对角线暂存、61×67 用 16×16 块 | 408 局部性原理；与 OS 缺页行为类比 |
| shlab-1 | 命令行解析与内建命令 | argv 切分、内建命令与外部命令分流、`execve` 与 PATH 查找 | OS 进程创建 |
| shlab-2 | 作业控制 | `fork`/`execve` 父子进程、`setpgid` 进程组、前台/后台、`waitpid` 带 `WUNTRACED`\|`WCONTINUED`、SIGCHLD/SIGINT/SIGTSTP 处理、`sigprocmask` 消除竞态 | OS 进程与信号 |
| shlab-3 | I/O 重定向 | `open`/`dup2`/`close`、文件描述符表继承、fd 泄漏与恢复 | OS 文件系统接口 |
| malloclab-1 | 隐式空闲链表 | 带边界标签的块格式、8 字节对齐、首次适配、合并四种情形、`sbrk` 扩展堆 | OS 虚拟内存与堆管理 |
| malloclab-2 | 显式空闲链表与分离适配 | 双向链表 LIFO 插入、按大小类分桶、`realloc` 就地扩展与后继块检查 | 数据结构 + 内存分配策略 |
| 工具链 | gdb、valgrind、perf、dlc | 断点调试、堆一致性检查、性能剖析、运算符条数机械化校验 | 前置项目：C 语言与汇编基础 |

## 六、验收判据

- datalab：15/15 函数通过 `btest`；`dlc` 报 0 违规（运算符种类、条数上限、禁止循环与递归）；`float_i2f` 在 $10^6$ 个随机输入上与 gcc 强转结果逐位一致，误差 0 位。
- cachelab-A：官方 trace 16/16 通过，hits/misses/evictions 与参考输出逐行一致。
- cachelab-B：32×32 miss < 300；64×64 miss < 1300；61×67 miss < 2000。
- shlab：16/16 trace 通过；除 prompt 外无额外输出；trace 结束后 `ps` 中无残留子进程；Ctrl-C 后前台进程被 SIGINT 终止。
- malloclab：11/11 trace 通过且堆一致性检查零错误；峰值利用率 ≥ 0.88；吞吐 ≥ 3000 Kops/s（`-O2`，单线程）；`realloc` 相关 trace 利用率 ≥ 0.85。
- 全局：`make check` 下 `-Wall -Wextra` 零警告；valgrind 无 invalid write/read。

## 七、风险与已知坑

**datalab**：`tmin` 取负仍是自身；移位量 ≥ 字长在 C 中是未定义行为，必须先 `& 31`；`divpwr2` 对负数需加偏置 $(1 \ll k)-1$；`fitsBits` 在 $n=32$ 时需特判；`float_i2f` 的 round-to-even 在尾数全 1 时会进位到指数域。

**cachelab**：64×64 每行只装 8 个 int，必须 4×4 子块 + 对角线暂存；LRU 时间戳要用全局单调计数器，不能每行独立计数。

**shlab**：SIGCHLD 处理器必须写成 `while (waitpid(-1, &st, WNOHANG|WUNTRACED|WCONTINUED) > 0)`；`fork` 后父进程 `setpgid` 与子进程 `execve` 之间存在竞态，需用 `sigprocmask` 屏蔽；Ctrl-Z 只对前台进程组生效；重定向后忘记恢复 fd 会导致后续输出丢失。

**malloclab**：边界标签各 4 字节、最小块 16 字节；合并要覆盖四种情形；`realloc` 就地扩展必须先确认后继块空闲；隐式链表达不到 3000 Kops/s，需要分离适配；valgrind 下计时无效，必须与性能测试分开跑。

## 八、与其他项目的关系

前置：C 指针与内存模型、x86-64 汇编基础、Linux 命令行与 gdb。后续可接并发 lab（pthread 与同步）、网络 lab（proxy）、体系结构 lab（流水线与分支预测）。可复用模块：`common/` 的 trace 解析与计时模块可被任何需要吞吐测量的 lab 直接引用；cachelab 的 LRU 结构可作为页表模拟、缓冲区管理的原型；malloclab 的块格式与合并逻辑可迁移到文件系统空闲块管理。
