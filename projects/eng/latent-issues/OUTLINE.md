## 一、它解决什么问题

这类能力要解决的是把机制题当背诵题、把现场故障当参数题的问题。真实工程里它对应两类事故：并发/内核交互导致的“偶发但致命”，资源边界导致的“单点拖垮全链路”。

场景一：假设一个 32 worker、单机 2 万 QPS 的接入层，内核在同一监听 fd 上唤醒多个 worker，只有一个 `accept4` 成功，其余返回 `EAGAIN`。平时只是 `sys` CPU 升高和 p99 抖动；遇到 SYN 突刺时 accept 队列溢出，`ListenOverflows` 上升，健康检查超时，扩容也救不回来——新实例同样被惊群打满。

场景二：数万级短连接的网关或爬虫，主动关闭方堆积 `TIME_WAIT`，临时端口按 $N_{tw}\approx \lambda_{conn}T_{tw}$ 被占用；同时 fd 泄漏把进程推到 `EMFILE`，`accept` 失败后连接队列继续涨，最后表现为“端口耗尽 + fd 耗尽 + 雪崩”三连。

面试里它对应：epoll 惊群怎么产生、`TIME_WAIT` 能不能调、`EMFILE` 时 `accept` 返回什么、伪共享怎么测、无锁为什么难、Nagle 为什么叠加延迟。

**入口（本文的读法）**：在 `epoll_wait` 唤醒多个 worker 后 `accept4` 返回 `EAGAIN`、`listen` backlog 与 `ListenOverflows`、`tcp_sock` 的 `TIME_WAIT`/2MSL 定时器、进程 `fd` 表与 `RLIMIT_NOFILE`、`TCP_NODELAY`/delayed ACK 的 `PSH/ACK` 时序、以及 `cmpxchg`/`futex` 和 64B cache line 这些硬约束下，把“偶发致命”和“单点拖垮”改写成可追踪的状态转换。换的是不再背参数结论，而是按 `errno`、`ss -tin` 的 `state/send-Q/recv-Q`、`/proc/sys/net/ipv4/*`、`lsof`/`/proc/<pid>/fd`、`strace` 的 syscall 序列、`perf c2c` 的 cache line 冲突来定位。

**不换的是什么**：全程不变的是内核可观测状态机：`epoll` 的 `ready list`/`EPOLLONESHOT` 语义、`tcp_sock` 状态与 `TIME_WAIT` 定时器、`task_struct->files` 的 `fd` 配额、TCP 发送缓冲与 `TCP_NODELAY`/delayed ACK 的字段组合、x86 `LOCK CMPXCHG`/`futex` 与 cache line 对齐；看到差异先问它改变的是哪条可观测记录：`accept4` 的 `errno`、`ss -tin` 的 `state/backlog`、`/proc/<pid>/limits` 的 `Max open files`、`perf c2c` 的 cache line 地址，还是 `strace -e trace=network,process` 的调用返回。

## 二、为什么这样做（方法论设计）

这套方法的核心取舍是：只对“有口径”的结论买单。有口径 = 能写出触发条件、观测指标、判据、修复代价；缺一项，结论就退化成名词解释。

- **有口径才算数**：惊群看“一次事件唤醒 $W$ 个 worker，仅 1 个 `accept4` 成功”，配合 `strace -f -e trace=accept4,epoll_wait`、`perf sched` 与 `/proc/net/netstat` 的 `ListenOverflows/ListenDrops` 同窗口变化；伪共享看同一 cache line 多核写、`perf c2c` 的 HITM 是否高；fd 看 $N_{fd}\approx N_{conn}+N_{file}+N_{pipe}+N_{timer}+N_{reserve}$ 是否逼近 `ulimit -n`，用 `lsof -p`、`/proc/pid/fd` 看增长曲线；`TIME_WAIT` 看 `ss -s`、`ss -tan state time-wait` 与 ephemeral 端口范围。
- **看起来专业但无法证伪**：“高并发下性能更好”“无锁一定更快”“调大 backlog 就能抗住”“TIME_WAIT 有害”。这些话没有基线、没有 workload、没有阈值，代价是把排障变成猜参数，把瓶颈推到内存、调度或下游。
- **指标**：计数、分位、余量三类。计数如 accept 队列溢出、CAS 重试、OOM kill；分位如 p99/p999、锁等待、调度延迟；余量如 fd 使用率、端口占用率、RSS 与活跃堆差值。指标必须和故障现象同窗口，否则相关性不成立。
- **边界**：只有机制位于关键路径时才成立。单线程、无竞争、无队列、无资源压力时，这些章节是知识地图，不是优化清单。内核版本、架构、虚拟化、库实现都会改变结论，不确定处写“按实现而定”。
- **失效条件**：压测流量与线上分布不一致、采样开销改变行为、应用层队列掩盖内核层问题、只看均值不看尾延迟、没有回滚方案。此时“方法论”会退化成 checklist。
- **常见错误做法的代价**：见 `TIME_WAIT` 就开 `tcp_tw_reuse`/`tcp_tw_recycle`，可能掩盖端口规划问题，`recycle` 在部分内核已移除且对 NAT 不友好；见延迟就 `TCP_NODELAY`，小包变多、拥塞和 CPU 上升，应用层队头阻塞仍在；见伪共享就全结构 padding，内存 footprint 和 cache 利用率下降，误伤只读共享；用无锁替代锁，高竞争下 CAS 重试、ABA、内存回收复杂度上升，尾延迟可能更差；调大 fd/backlog 即“修复”，泄漏仍在，故障后移到 OOM 或下游超时。

## 三、章节大纲

### 惊群效应：accept 惊群与 epoll 惊群
讲多进程/多线程同时阻塞在 `accept` 或 `epoll_wait` 上，一次连接事件唤醒多个 worker 的机制；区分真惊群与内核已缓解的情况，讨论 `EPOLLEXCLUSIVE`、`SO_REUSEPORT`、非阻塞 `accept4` 的取舍。面试问“epoll 惊群怎么产生、`EPOLLEXCLUSIVE` 解决什么”，学完能按唤醒次数、`EAGAIN` 比例和 accept 队列溢出判据回答。

### 伪共享：cache line、填充与真伪对比
讲同一 cache line 被多核写导致的缓存一致性流量，padding、`alignas`、per-CPU 变量，以及“真共享/伪共享/只读共享”的区分。面试问“怎么确认伪共享、padding 是否总有效”，学完能用 `perf c2c` 的 HITM、cache-miss 和热点行地址回答，并说明按实现而定的部分。

### ABA 问题与无锁数据结构的正确做法
讲 CAS 的 ABA、版本号/ tagged pointer、hazard pointer、epoch/RCU 与内存回收。面试问“ABA 在什么场景发生、无锁队列为什么难”，学完能答出“不是换个 CAS 就正确”，并能说出回收语义和重试代价。

### 优先级反转与优先级继承
讲高优先级任务等待低优先级任务持有的锁，被中优先级任务抢占；优先级继承与优先级天花板的区别。面试问“优先级反转成立条件、实时系统怎么选”，学完能按阻塞链、继承范围和 worst-case 延迟回答。

### 活锁、饥饿与公平性
讲重试碰撞导致活锁、锁/调度不公平导致饥饿，退避与公平锁的吞吐代价。面试问“活锁和死锁区别、自旋何时退化”，学完能用重试次数、等待时间分布、调度延迟判断，而不是只说“加随机退避”。

### 缓存击穿、雪崩与热 key
讲单个热 key 过期瞬间击穿、大量 key 同时失效导致雪崩、以及热 key 在多副本间放大请求的三种不同故障形状；对策分别是互斥重建/逻辑过期、过期时间打散、本地缓存分层 + 限流。面试问"击穿和雪崩的区别、为什么加锁重建可能更慢"，学完能按"key 基数、过期分布、回源成本"三个量判断该用哪一种。

### 队头阻塞：TCP 层与应用层
讲 TCP 有序交付导致的传输层队头阻塞、HTTP/1.1 管道化与 HTTP/2 多路复用后仍然存在的流级阻塞，以及连接池耗尽如何把下游故障放大成雪崩。面试问"HTTP/2 解决了什么、又没解决什么"，学完能区分"丢包导致的阻塞"与"应用串行导致的阻塞"。

### TIME_WAIT 与端口耗尽
讲 TIME_WAIT 的成因（主动关闭方保留 2MSL）、端口四元组复用条件、`tcp_tw_reuse`/`tcp_tw_recycle` 的适用边界与风险，以及短连接放大效应。面试问"TIME_WAIT 多了要不要调"，学完能先问"是客户端还是服务端主动关的、是不是短连接"，再决定改代码还是改内核参数。

### fd 耗尽与 EMFILE 的连锁反应
讲 fd 上限（进程级/系统级）、泄漏与瞬时峰值两种成因、accept 失败后的排队与重试放大，以及 `ulimit -n` 调大之后故障为何转移到下游。面试问"EMFILE 时服务会怎样"，学完能按"泄漏速率、峰值并发、下游超时"三个量定位是泄漏还是容量不足。

### 内存碎片与 OOM killer
讲用户态分配器的碎片（size class、arena、tcache）与内核态不可回收内存（slab、page cache 占比）的区别、RSS 与 VIRT 的误读，以及 OOM killer 的评分规则。面试问"内存泄漏和碎片怎么区分"，学完能用 `/proc/<pid>/smaps`、`slabtop`、`malloc_stats` 三类证据回答。

### Nagle 与延迟 ACK 的交互、粘包与半包
讲 Nagle 与延迟 ACK 叠加产生的 40ms 级延迟、`TCP_NODELAY` 的代价、TCP 是字节流所以必须自己在应用层定界（长度前缀/分隔符/定长）。面试问"为什么关了 Nagle 还是慢"，学完能说明关闭 Nagle 只消除发送端攒批，接收端延迟 ACK 与对端算法仍在。

### 信号与系统调用：EINTR、信号丢失、fork 后的锁状态
讲慢系统调用被信号中断返回 `EINTR`、标准信号不排队导致丢失、`fork` 后子进程继承已加锁的 mutex 导致永久死锁，以及 `sigaction` 与 `pthread_atfork` 的正确用法。面试问"为什么子进程一启动就卡住"，学完能立刻想到"锁在 fork 前被别的线程持有"。

## 四、不做什么 · 必要性 · 失效点

### 必要性：删掉会怎样

| 机制 | 删掉会怎样 | 判定 |
|---|---|---|
| `accept4` | 删掉 `accept4` 返回 `EAGAIN` 的计数口径，惊群承诺“一次 `epoll_wait` 唤醒 $W$ 个 worker，仅 1 个成功”无法证伪，排障会把 `EAGAIN` 误记成业务超时。 | 必需 |
| `ListenOverflows` | 删掉 `/proc/net/netstat` 的 `ListenOverflows/ListenDrops`，SYN 突刺打满 accept 队列的内核侧错误断链，健康检查超时会被归因给 `sys` CPU 或 backlog 参数。 | 必需 |
| `TIME_WAIT` | 删掉 `ss -tan state time-wait` 与 ephemeral 端口范围对账，主动关闭方堆积 `TIME_WAIT` 的端口占用承诺变成名词解释，端口耗尽会被误判为 `EMFILE`。 | 必需 |
| `EMFILE` | 删掉 `ulimit -n`、`/proc/pid/fd`、`lsof -p` 的 fd 余量曲线，`accept` 返回 `EMFILE` 后连接队列继续涨的错误链路断掉，泄漏仍在并会在下一轮 `accept` 再次返回 `EMFILE`。 | 必需 |
| `tcp_tw_recycle` | 删掉 `tcp_tw_recycle` 的内核版本/NAT 边界，见 `TIME_WAIT` 就开 sysctl 的代价承诺丢失；在已移除该 sysctl 或 NAT 多源路径上会把端口耗尽排障变成随机 SYN/ACK 丢弃。 | 选择 |

### 失效点：哪条前提一破，结论就变

- 核数=1 或所有写变量落在不同 cache line → `perf c2c` 的 HITM 不再证明伪共享，`CAS` 重试计数不会因同一 cache line 争用而上升。
- 权限位=无 `CAP_SYS_PTRACE`/`CAP_SYS_ADMIN` → `strace -f -e trace=accept4,epoll_wait` 与 `perf c2c` 采不到 `EAGAIN` 和 HITM，惊群/伪共享判据退化成日志猜测。
- 协议版本/内核 sysctl=TCP timestamps 经 NAT 多源共享公网 IP，或内核已移除 `tcp_tw_recycle` → `tcp_tw_recycle` 的时间戳检查会丢弃合法 SYN/ACK，`TIME_WAIT` 缓解结论变成握手失败。
- 时钟源=容器 `CLOCK_MONOTONIC` 与宿主机 `perf sched`/`ss` 采样窗口不同步 → p99、`ListenOverflows`、`TIME_WAIT` 无法同窗口对齐，相关性不成立。
- 队列=应用层队列或 TLS 记录层已缓冲小包 → `TCP_NODELAY` 不再能消除尾延迟，错误变成小包增多、拥塞窗口和 CPU 上升而队头阻塞仍在。

### 不做什么（范围）

- **不做性能调优实战**：本篇只到"能定位、能说清机制、能给判据"。真做优化属于 `eng/perf-engineering/`，两边不重复。
- **不写内核版本适配表**：同一参数在不同版本的默认值与行为会变，逐版本列表一定会过期。只写"哪些结论按实现而定"。
- **不给"最佳实践清单"**：每个陷阱的结论都带前置条件，抽成清单必然变成盲目套用——这是本篇最主要的反面例子（见 §二"常见错误做法的代价"）。
- **不复制代码**：示例只写关键几行（伪代码或最小可编译片段），完整工程在代码仓，本文只做指针。
- **不覆盖硬件级问题**：NUMA 亲和、CPU 频率、内存带宽属于 `cpu/cpu-microarchitecture/`，本篇只在需要时引用结论。

## 五、面试怎么讲

这一节对应的是方法论能力，核心是**你能不能用证据说清一个陷阱“什么时候会发作、怎么观测、怎么证明修好了”**，不是背名词。所有回答的骨架都是同一个：先定位触发条件 → 拿到机制级证据 → 用最小 workload 复现 → 用同一口径对比。把这条方法论讲透，比逐个背陷阱定义有用得多。

**30 秒版本（面试开场可以说）**

> 这类陷阱有个共同点：它们不出现在功能测试里，只在特定的并发时序或负载形状下才发作，发作时的表现通常是“变慢”，而不是“报错”，所以光靠 code review 和功能测试抓不到。我处理这类问题分三步：第一，先拿到机制层面的证据，证明它真的在发生，不是看到慢就猜一个名词；第二，用最小 workload 把它稳定触发出来；第三，用同一个 workload 对比修复前后的口径，比如 wakeup 次数与 accept 次数的比值、cacheline 的 HITM 次数、p99 尾延迟。这三步里最容易出错的是第三步：口径选错了，就会把噪声当成收益。

**可能被追问的 8 个点**

**1. “你怎么知道线上是惊群？”**
→ 考点：你是有证据才这么判断，还是背了名词。
→ 答法：先分清是哪一种惊群。epoll 惊群：多个线程阻塞在同一个 epoll 实例的 `epoll_wait` 上，一个事件到达时会全部被唤醒，但只有一个线程能处理，其余线程醒来后发现没有事可做。用户态测到的方法是：用 `perf record -e sched:sched_wakeup` 抓唤醒次数，再跟实际处理成功的事件数比对，正常应该接近 1:1；或者看 `/proc/<pid>/status` 里的 `voluntary_ctxt_switches`。修复手段：`EPOLLEXCLUSIVE`（Linux 4.5+）让内核只唤醒一个等待者，或者用 `EPOLLONESHOT` 并在处理完事件后重新注册。accept 惊群：Linux 4.5 起，内核在 accept 路径上做了排他唤醒，老内核才需要“只让一个线程 accept，再把 fd 传出去”，或者用 `SO_REUSEPORT` 做哈希分流。**这句话要讲清楚：修好了是指 wakeup 次数降下来，不是说延迟看起来变好了。**

**2. 伪共享**
→ 考点：是否知道 cacheline 大小、MESI 状态，以及怎么证明是伪共享。
→ 答法：x86-64 上 cacheline 是 64 字节，两个变量落在同一条 line 上、被不同核写，line 会在 M 状态之间来回迁移。证明方式不能光看“慢”，要用 `perf c2c record` + `perf c2c report` 看 HITM（HIT Modified）计数和 Shared Data Cache Line Table，这是唯一能直接指认罪魁 line 的工具。修复：`alignas(64)` / `__attribute__((aligned(64)))`，内核里是 `____cacheline_aligned_in_smp`；C++17 有 `std::hardware_destructive_interference_size`，但各平台取值不稳定，实践中直接写 64 更稳。**加分点**：先反问一句“这个热点真的是伪共享造成的吗，还是锁竞争或分支预测失败”，因为 c2c 也会把真共享报出来。

**3. ABA**
→ 考点：无锁编程中真实的失败模式，以及你是否清楚它的代价。
→ 答法：经典场景是 lock-free 栈的 pop：`head` 读到 A，CAS 之前 A 被弹出、A 的地址被复用于 B、B 又被弹出、A 被重新压回，CAS 依然成功。解法两条：带 tag 的双字 CAS（x86-64 用 `cmpxchg16b`，要求 16 字节对齐，注意对齐是硬性要求，不满足会 fault），或者把版本号塞进指针高位（用户态指针实际只用到 48 位，5 级页表下是 57 位，不能想当然地借用高位）。另一条路是干脆不回收内存：hazard pointer、epoch/RCU 延迟释放，从根上消除“地址被复用”这个前提。**加分点**：补一句“如果能用 mutex，就不该上 lock-free，ABA 只是 lock-free 的众多坑之一”。

**4. 优先级反转**
→ 考点：是否只会背“火星探路者”，还是能说清适用边界。
→ 答法：高优先级任务等低优先级任务持有的锁，中优先级任务抢占低优先级任务，导致高优先级任务被无限期阻塞。解法是优先级继承（持锁者临时提升到等待者的优先级，释放后恢复）或优先级天花板（锁的优先级取所有可能使用者的最高值）。Linux 上对应 `pthread_mutexattr_setprotocol(PTHREAD_PRIO_INHERIT)`，底层走 `rt_mutex`，futex 的 PI 版本是 `FUTEX_LOCK_PI`。**边界一定要说**：条件变量不参与 PI；PI 只解决单把锁的反转，多把锁链式的反转（H 等 L1 持有的锁、L1 又在等 L2）它管不了，那本质上变成了死锁问题。

**5. TIME_WAIT 堆积、fd 耗尽**
→ 考点：是否把正常状态当 bug，是否知道 EMFILE 和 ENFILE 的区别。
→ 答法：TIME_WAIT 出现在主动关闭方，时长是 2MSL（Linux 固定 60 秒，`TCP_TIMEWAIT_LEN`），作用有两个：保证最后一个 ACK 能重传、让旧连接的残余报文在网络里消亡，所以它不是 bug。堆积通常发生在短连接且己方是主动关闭方的时候。手段：`tcp_tw_reuse` 只对主动发起 connect 的 socket 生效，且依赖 timestamp；`tcp_tw_recycle` 在 NAT 环境下会丢包，4.12 已移除，不要提它。根治办法是长连接、连接池，或者让对端先关。fd 耗尽：`EMFILE` 是进程 fd 表满（`RLIMIT_NOFILE` / `ulimit -n`），`ENFILE` 是系统级 `file-max` 满，两者处理方式不同。`accept` 返回 `EMFILE` 的标准做法是预留一个 idle fd，关掉它去 accept 拿到新连接再立刻 close，防止监听队列被占满导致客户端集体超时。

**6. EINTR 和短写**
→ 考点：你是否默认“系统调用要么成功要么失败”。
→ 答法：慢系统调用会被信号打断，返回 -1 且 `errno == EINTR`，必须循环重试，`accept`/`read`/`write`/`connect`/`select` 都是。`epoll_wait` 尤其要小心：被信号打断返回 EINTR 时不更新 timeout，剩余时间要自己算，否则会多睡。短写：`write` 的返回值可能小于 count，`writev` 同理，要循环到写完。还有 `SIGPIPE`：往对端已关闭的连接写会收到信号，默认动作是杀进程，要么忽略，要么用 `MSG_NOSIGNAL`。

**7. Nagle、delayed ACK 和队头阻塞**
→ 考点：40ms 级别的延迟从哪来。
→ 答法：Nagle 的规则是“有未确认的小包就不发新的小包”，delayed ACK 是接收方最多等 40ms 再确认（Linux 上 quickack 模式除外），两者一叠加，就是典型的 40ms 卡顿。解法是 `TCP_NODELAY`，或者应用层用 `writev` 合并、用缓冲区攒批，`TCP_CORK` 只能短开（有 200ms 上限）。队头阻塞要分层讲：TCP 是字节流，前面丢一个包，后面的数据即使到了也要等重传；HTTP/1.1 的 pipelining 要求响应严格按序；应用层是单队列加固定线程池，一个慢任务就把后面全堵住。**验证口径**：队列等待时间直方图加 p99，而不是平均延迟。

**8. 活锁和碎片**
→ 考点：能否区分死锁、活锁、饥饿，以及 RSS 上涨到底是不是泄漏。
→ 答法：活锁是状态一直在变但无进展，典型是多个线程 CAS 同时失败又同时重试，解法是随机退避加 jitter，或者换成有排队的锁（ticket lock / MCS lock）；以太网的二进制指数退避是教科书案例。饥饿是有人一直抢不到。碎片分内外：内碎片是 size class 向上取整造成的，外碎片是空闲块不连续造成的。glibc malloc 的 RSS 虚高，多半是 per-thread arena 增多（上限是 8 × 核数），可以试 `MALLOC_ARENA_MAX`、`malloc_trim(0)`，用 `mallinfo2()` 观察。**关键的反问**：“RSS 涨但 valgrind 没报泄漏”只能说明不是泄漏，还得证明是碎片还是 arena，别直接下结论。

**别说什么**

- **别把框架当原理讲**。“用了 Netty 所以没有惊群”“用了 Go 所以没有伪共享”，这种话一出口就露怯，因为追问一句“框架底下调的是哪个 syscall”就答不上来。要么讲到 epoll/syscall 层，要么直接说“这块我只知道到 API 层”。
- **别把“跑通了”当成“修对了”**。压测没炸不等于陷阱不存在，只说明触发条件没凑齐。要说清触发条件是什么、为什么这次没触发。
- **别报没测过的数字**。“提升 3 倍”“降低 90%”这种话，被追问“怎么测的、基线是什么、样本多少”会立刻崩。宁可说“这个我没量化，但验证口径是 X”。
- **别倒因为果**。看到 QPS 掉就说惊群、看到 RSS 涨就说内存碎片，这是背名词不是做工程。顺序永远是：先有证据，再命名问题。
