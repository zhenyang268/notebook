# latent-issues · 分章详细

## 第 1 章 惊群效应：accept 惊群与 epoll 惊群

**要解决的问题**：多个进程/线程共享同一个监听 fd 时，一个连接到达会唤醒多少个等待者。不解决这个问题，会出现「QPS 不高，但 CPU 被无效唤醒和上下文切换占满」的情况；接入层压测时尤其明显。

**机制**：监听 socket 上维护一条等待队列，accept 和 epoll_wait 都是往这条队列里挂 waiter。内核的唤醒函数 `__wake_up_common` 在遍历队列时识别 `WQ_FLAG_EXCLUSIVE` 标志：一旦遇到排他 waiter，只唤醒一个，然后停止遍历。

- **accept 侧**：`inet_csk_accept` 调用 `prepare_to_wait_exclusive`，所以现代 Linux 上 accept 本身就是排他唤醒，一个连接只叫醒一个进程。这就是「accept 惊群基本消失」的原因。
- **epoll 侧**：每个 epoll 实例通过 poll table 往同一 socket 挂 `ep_poll_callback`，默认是**非排他**注册。N 个进程各有自己的 epoll 实例监听同一 listen fd（fork 继承），新连接会触发 N 次 callback，N 个进程全被唤醒，只有一个 accept 成功。Linux 4.5 起可以用 `EPOLLEXCLUSIVE` 把注册改成排他。
- **`EPOLLEXCLUSIVE` 的语义是「至少唤醒一个」而规范并不保证只唤醒一个**，并且只能在 `EPOLL_CTL_ADD` 时指定，`MOD` 会返回 `EINVAL`，不能与 `EPOLLONESHOT` 同用。所以用户态必须用非阻塞 accept + `EAGAIN` 兜底，不能假设「我醒了就一定有连接」。
- **另一条路线是 `SO_REUSEPORT`**（Linux 3.9 起）：每个进程 bind 自己的 socket，内核按四元组哈希把连接分流到某个 socket 的 accept 队列，进程之间物理隔离，不存在共享等待队列。

简化后的内核路径：

```c
// __wake_up_common 的核心逻辑
for (curr = list_first_entry(...); ...; curr = next) {
    if (curr->flags & WQ_FLAG_EXCLUSIVE) {
        if (woken++ >= 1) break;   // 排他：只唤醒一个
    }
    curr->func(curr, mode, wake_flags, key);
}
```

用户态正确写法：

```c
int lfd = socket(...);
fcntl(lfd, F_SETFL, O_NONBLOCK);          // 必须非阻塞
struct epoll_event ev = { .events = EPOLLIN | EPOLLEXCLUSIVE, .data.fd = lfd };
epoll_ctl(epfd, EPOLL_CTL_ADD, lfd, &ev);
for (;;) {
    epoll_wait(epfd, evs, n, -1);
    while ((cfd = accept4(lfd, NULL, NULL, SOCK_NONBLOCK)) >= 0) { /* 处理 */ }
    // accept 返回 -1 且 errno == EAGAIN：正常退出内层循环，不是错误
}
```

**最小例子**：4 个进程共享一个 listen fd 做阻塞 accept。

```python
import os, socket
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 8080)); s.listen(128)
for _ in range(4):
    if os.fork() == 0:
        n = 0
        while True:
            c, _ = s.accept(); n += 1
            print(os.getpid(), n, flush=True)
            c.close()
os.wait()
```

```bash
python3 herd.py &
ss -lntp 'sport = :8080'
# LISTEN 0 128 127.0.0.1:8080 users:(("python3",pid=1001,fd=3),("python3",pid=1002,fd=3),...)
for i in $(seq 50); do curl -s http://127.0.0.1:8080/ >/dev/null; done
```

结果：`ss` 显示 4 个 pid 持有同一个 fd=3（同一 inode）；50 次连接通常由其中 1 个 pid 吃掉大部分，其余进程长期没有输出——排他唤醒后，醒来的进程往往在再次调度中继续抢到连接，形成「赢家通吃」。把 accept 换成「4 个进程各自 epoll 实例 + 无 `EPOLLEXCLUSIVE`」再跑，就能看到 4 个进程的唤醒次数接近 1:1:1:1，即出现了 epoll 惊群。

**面试高频问法**：

1. **「accept 惊群在 Linux 上还存在吗？」**
   - 考点：是否知道排他唤醒发生在内核而非用户态，以及剩余窗口。
   - 答法：现代内核 accept 用排他唤醒，一个连接只叫醒一个；但被唤醒的进程可能被信号打断或被抢占，连接被别的进程抢走，所以非阻塞 accept + `EAGAIN` 仍是必备兜底。
2. **「epoll 为什么还会惊群，EPOLLEXCLUSIVE 解决了什么？」**
   - 考点：epoll 注册到 socket 等待队列默认非排他。
   - 答法：N 个 epoll 实例监听同一 fd 会各自挂一个非排他 callback，每次事件全被唤醒；4.5 起 `EPOLLEXCLUSIVE` 改成排他注册，但语义是「至少一个」，所以不能省掉 EAGAIN 判断。
3. **「EPOLLEXCLUSIVE 和 SO_REUSEPORT 怎么选？」**
   - 考点：共享队列 vs 分队列的架构差异。
   - 答法：`EPOLLEXCLUSIVE` 是共享一个 accept 队列，只唤醒一个，改动小，但可能负载不均；`SO_REUSEPORT` 是每进程独立队列、内核哈希分流，隔离更好，但哈希不均、进程重启时连接归属会变。
4. **「惊群的危害只是性能吗？」**
   - 考点：是否把它误判为正确性问题。
   - 答法：主要是性能——无效上下文切换、cache 抖动、CPU 空转导致延迟毛刺；正确性靠的是非阻塞 accept 和错误处理，惊群本身不会让你丢连接。
5. **「nginx 的 accept_mutex 为什么存在，现在还要吗？」**
   - 考点：用户态串行化与内核能力的取舍。
   - 答法：早期内核嘎http://wap.dfszgs.com 不支持排他唤醒，nginx 用用户态锁让只有一个 worker 进 accept，代价是锁开销和延迟；现在支持 `EPOLLEXCLUSIVE` / `SO_REUSEPORT` 后通常不再需要。

## 第 2 章 伪共享：cache line、填充与真伪对比

**要解决的问题**：多线程程序里逻辑上毫不相干的变量，因为落在同一条 cache line 上而互相拖慢。不解决这个问题，会把吞吐瓶颈误判成「锁没优化好」，做一堆无用功。

**机制**：CPU 以 cache line 为单位做一致性管理，行大小 $L$ 在 x86_64 上通常是 64 字节（按架构而定，部分 ARM 服务器为 64B，也有更大的）。MESI 类协议下，一个核要写某个字节，必须先把该行拿到 Modified/Exclusive 状态，其他核的副本被 invalidate。所以两个核各自递增位于同一行的两个**不同**变量时，行会在核间来回迁移，每次写都是一次 cache-to-cache 传输。

判定条件很直接：变量 $a$、$b$ 落在同一行，即

$$
\left\lfloor \frac{\text{addr}(a)}{L} \right\rfloor = \left\lfloor \frac{\text{addr}(b)}{L} \right\rfloor
$$

并且两者被不同核**写**，就是伪共享。如果至少一方只读，行可以多核共享 S 状态，没有一致性流量；如果两个核写的是**同一个**变量，那是真共享，通信是必要的，填充救不了。

消除手段：

- 填充到行边界：C/C++ 用 `alignas(64)` 或 `__attribute__((aligned(64)))` 加 padding；C++17 有 `std::hardware_destructive_interference_size`（值由实现定义）。
- Java 用 `@Contended`，需要 `-XX:-RestrictContended` 才在用户类上生效。
- 减少写共享：每线程本地累加、最后合并；或分片计数后求和。
- 发现手段：`perf c2c`（若内核与 perf 支持）看 HITM 行，HITM 即「本核读/写了一条被其他核改过的行」。

**最小例子**：4 线程各做 $10^7$ 次原子递增，对比紧凑数组与填充数组。

```c
#include <pthread.h>
#include <stdatomic.h>
#define N 10000000
typedef struct { _Atomic long v; } tight_t;
typedef struct { _Atomic long v; char pad[64 - sizeof(long)]; }
        __attribute__((aligned(64))) padded_t;   // 每实例独占一行
static tight_t  t[8];
static padded_t p[8];
void *work(void *arg) {
    long i = (long)arg;
    for (int k = 0; k < N; k++) atomic_fetch_add_explicit(&t[i].v, 1, memory_order_relaxed);
    for (int k = 0; k < N; k++) atomic_fetch_add_explicit(&p[i].v, 1, memory_order_relaxed);
    return NULL;
}
```

```bash
gcc -O2 -pthread bench.c -o bench && ./bench 4
# 分别计时两段循环：
# tight 段（4 个 8B 变量挤在同一行）明显慢于 padded 段
```

结果：`sizeof(tight_t)=8`，4 个实例共 32 字节，全在一条 64B 行内，4 个核争抢同一行；`sizeof(padded_t)=64` 且 `aligned(64)`，每个实例独占一行，各核各行其是。差距常见在数倍量级，随核心数与拓扑变化，具体倍数按机器而定。用 `perf c2c record ./bench` 后 `perf c2c report --stats`，紧凑版会看到大量 HITM，填充版几乎没有。

真伪对比要记住的分界：

| | 真共享 | 伪共享 |
|---|---|---|
| 数据关系 | 同一变量 | 不同变量、同一行 |
| 一致性流量 | 必要，语义要求 | 纯浪费 |
| 填充能否消除 | 不能 | 能 |
| 正确解法 | 分片/批量/减少临界区 | padding、对齐、分离到不同行 |

**面试高频问法**：

1. **「什么是伪共享？和真共享怎么区分？」**
   - 考点：是否理解一致性以行为单位，而不是以变量为单位。
   - 答法：两个核写逻辑上无关但落在同一 cache line 的变量，行在核间反复失效迁移；真共享是写同一个变量，通信是语义要求的，填充无效。
2. **「填充为什么能解决？代价是什么？」**
   - 考点：对齐与数组步长的关系，以及是否知道副作用。
   - 答法：把每个热点变量拉到独占一行并对齐到行边界，各核不再争同一行；代价是内存膨胀、破坏空间局部性，而且行大小按架构而定，写死 64 并不总对。
3. **「怎么确认是伪共享而不是锁竞争？」**
   - 考点：可观测手段。
   - 答法：看 perf c2c 的 HITM 热点行，或做「只改结构体布局、逻辑不动」的对照实验；如果加 padding 后显著变快，基本可以定案。
4. **「volatile / 原子操作能解决伪共享吗？」**
   - 考点：原子性与缓存一致性是两回事。
   - 答法：不能。原子性保证不丢更新，反而常常因为要独占行而放大一致性流量；消除伪共享靠布局和写频率，而不是靠 atomic。
5. **「除了 padding，还有什么工程手段？」**
   - 考点：是否有实际优化经验。
   - 答法：每线程本地累加再合并、分片计数（如 LongAdder 的思路）、批量提交降低写频率、把只读共享数据与可写数据分开布局。

## 第 3 章 ABA 问题与无锁数据结构的正确做法

**要解决的问题**：CAS 的原子性只覆盖「这一个地址、这一刻」，不覆盖「这个地址的历史」。无锁结构靠「读—算—CAS」重试，如果读和 CAS 之间值被改回了原样，CAS 会误判「没人动过」，把一个已经失效的拓扑当成有效拓扑提交。不解决，无锁栈/队列会静默丢节点、double free、use-after-free，而且极难复现。

**机制**

经典无锁栈 pop：

```c
do {
    top = head.load(acquire);          // ①
    if (!top) return NULL;
    next = top->next;                  // ②
} while (!head.compare_exchange_weak(top, next, acq_rel)); // ③
return top;
```

ABA 的产生需要三个条件同时成立：CAS 只比较值、节点内存可被复用或释放、①②与③之间存在窗口。典型的坏交错：

| 时刻 | T1 | T2 | 栈状态 |
|---|---|---|---|
| t1 | 读到 `top=A, next=B`，被抢占 | | A→B→C |
| t2 | | pop A，pop B，push A | A→C |
| t3 | CAS(head, A, B) 成功 | | head=B，B 已弹出 |

T1 认为「A 还在、A 后面是 B」，于是把 head 改成 B。但 B 已经被弹出甚至释放，C 及其后的节点全部丢失。

解法分三层，工程上通常组合使用：

1. **让「值相同」不再等价于「状态相同」**：tagged pointer，把版本计数和指针打包成一个原子字，每次修改版本加一，CAS 比较整字。64 位平台上指针有效位之外的位可以借给版本（具体位数按平台而定），原子性依赖 128 位 CAS（x86-64 的 `cmpxchg16b`）或 LL/SC 循环。版本会回绕，$2^{k}$ 次修改后理论上仍可 ABA，所以它通常要和回收机制配合。
2. **让内存不能被复用**：hazard pointer、epoch-based reclamation、RCU、引用计数。注意它单独**不解决**逻辑 ABA——值仍可能被改回，只是节点还活着、不会 use-after-free；要真正判定「没人动过」，仍要版本或标记。
3. **利用 LL/SC**：ARM/POWER 的 load-linked/store-conditional 中，任何对该地址的写（哪怕写回原值）都会让后续 SC 失败，因此天然免疫「值回原样」这一类 ABA。但 LL/SC 有伪失败，且不能跨 cache line，循环里仍要正确处理重试。

另外，CAS 失败重试路径要用 `compare_exchange_weak`（允许伪失败，通常在循环里更快），内存序至少要 `acq_rel`，否则读到的 `next` 可能不是与 `top` 匹配的那个版本。Michael-Scott 队列的 head/tail 也有同样的 ABA 面，处理方式一致。

**最小例子**

```bash
gcc -O2 -pthread aba.c -o aba && ./aba
```

程序按上表交错执行：T1 读 `A/B` 后 `sched_yield()`，T2 做完 pop-pop-push，T1 再 CAS。观察输出：

```
CAS succeeded: head = B (freed)
expected: head = C, length 1
actual:   lost C, use-after-free on B
```

把 `head` 换成 `std::atomic<uint64_t>`、高 16 位存版本、用 `cmpxchg16b` 或 `__int128` 的 CAS 后，同一交错下 T1 的 CAS 因版本不匹配失败并重读，输出变为 `CAS failed, retry; head = A (v+2)`，C 保留。

**面试高频问法**

- 「CAS 不是原子的吗，为什么还有 ABA？」→ 考点是原子性 ≠ 历史性。答法：CAS 保证单地址比较交换不可分割，但读和 CAS 之间值可以 A→B→A；CAS 看到 A 仍成功，可它依赖的 `next` 已经失效，于是把过期拓扑提交了。
- 「怎么彻底解决 ABA？」→ 考点是分层。答法：没有银弹，版本号/tagged pointer 解决「值等价」，hazard pointer/epoch/RCU 解决「内存复用」，LL/SC 架构上任何写都会让 SC 失败；工程上组合使用，且版本号会回绕，要靠回收机制兜底。
- 「版本号放多少位，64 位系统怎么塞？」→ 考点是实现细节。答法：指针有效位之外的高位借给版本，具体位数按平台而定；CAS 需要 128 位原子指令或双字 CAS，不是所有平台都有，没有时退回 LL/SC 或加锁。
- 「hazard pointer 能不能单独解决 ABA？」→ 考点是区分 use-after-free 与逻辑 ABA。答法：不能。它保证被引用的节点不被释放，但值仍可能被改回；它解决的是内存回收，逻辑 ABA 还要版本或标记。
- 「Java 里 `AtomicStampedReference` 和 `AtomicMarkableReference` 有什么区别？」→ 考点是标记宽度。答法：前者带整数版本戳，能防 ABA；后者只有一个布尔标记，只能表达「有没有被改过」，防不了 A→B→A。

## 第 4 章 优先级反转与优先级继承

**要解决的问题**：优先级调度假设「高优先级先跑」，但锁把执行权交给了持锁的低优先级任务；一旦中间优先级任务可抢占，高优先级就被一个与锁无关的任务无限期挡住。不解决，实时系统会 miss deadline，而且现象依赖时序、极难复现。

**机制**

优先级反转需要三要素同时成立：至少三个优先级、一把共享锁、中优先级任务可运行。经典时间线是 L 持锁 → H 阻塞在锁上 → M 就绪并抢占 L → H 等 M 跑完。

优先级继承（PI）：当高优先级任务阻塞在锁上，持有者临时继承等待者中的最高优先级，释放后恢复；等待链上要传递。优先级天花板：给锁静态设定天花板优先级，等于所有可能获取者的最高优先级；任务一拿到锁就升到天花板。两者对比：PI 动态、按需、实现简单，但只在真正阻塞时才提升；天花板可静态做可调度性分析、按固定顺序加锁还能防死锁，代价是可能不必要地提升、挡住中优先级任务。

核心伪代码（真实实现还要处理多等待者、提升叠加、链式传播）：

```c
lock(m):
    if (m->owner == NULL) { m->owner = self; return; }
    if (self->prio > m->owner->prio)
        boost(m->owner, self->prio);   // 可能沿等待链向上传播
    block(self, m);

unlock(m):
    m->owner = NULL;
    restore_prio(self);                // 回到基础优先级或剩余等待者最高值
    wake_one(m);
```

Linux 内核里带 PI 的互斥是 `rt_mutex`；用户态通过 `pthread_mutexattr_setprotocol(&attr, PTHREAD_PRIO_INHERIT)` 使用，底层走 futex 的 PI 接口（具体路径按 glibc/内核版本而定）。普通 futex 不继承优先级。PI 只对同一把锁的等待链有效，对自旋锁、CPU 带宽、内存带宽、I/O 等非锁资源造成的反转无能为力；它也不能防死锁。

**最小例子**

三个 `SCHED_FIFO` 线程，L=10、M=20、H=30，L 先拿 mutex 并进入临界区，H 稍后到达，M 一直忙等：

```bash
sudo chrt -f 10 ./low &   # 先拿锁，临界区里 sleep 一小段
sudo chrt -f 20 ./mid &   # 纯 CPU 忙等
sudo chrt -f 30 ./high    # 等同一把锁
```

需要 `CAP_SYS_NICE`。用 `ftrace` 的 `sched_switch` 观察：`PTHREAD_PRIO_NONE` 时，`mid` 抢占 `low`，`high` 要等 `mid` 跑完才拿到锁；改成 `PTHREAD_PRIO_INHERIT` 后，`low` 在阻塞期间以 prio 30 运行，先于 `mid` 完成临界区并释放，`high` 随即被唤醒。临界区越长，差距越明显（具体时长取决于临界区长度和 M 的行为，不给固定数字）。

**面试高频问法**

- 「描述一下优先级反转，举一个真实案例。」→ 考点是能否讲清三要素和后果。答法：低优先级任务持锁，高优先级任务阻塞，中优先级任务抢占持有者，高优先级被间接无限期阻塞；Mars Pathfinder 上低优先级气象任务持信息量锁、中优先级通信任务抢占、高优先级总线管理任务无法复位看门狗导致系统重启，NASA 远程打开优先级继承。
- 「优先级继承和优先级天花板有什么区别，怎么选？」→ 考点是动态 vs 静态。答法：PI 只在阻塞发生时把持有者提升到等待者最高优先级，开销在慢路径；天花板是拿锁即提升到预设值，可静态分析、配合有序加锁能防死锁，但可能过度提升。硬实时、锁集合固定时倾向天花板，通用系统倾向 PI。
- 「Linux 上怎么用 PI 锁？」→ 考点是接口和前提。答法：`pthread_mutexattr_setprotocol(PTHREAD_PRIO_INHERIT)`，线程要用 `SCHED_FIFO/SCHED_RR` 才有意义，底层是 `rt_mutex`/futex PI；普通互斥和自旋锁不继承。`PTHREAD_PRIO_PROTECT` 对应天花板，glibc 的支持情况按版本而定。
- 「PI 有什么代价和局限？」→ 考点是别把它当万能药。答法：只对同一把锁的等待链有效，链式提升让 unlock 路径变复杂；不解决自旋锁和非锁资源（CPU、内存带宽、I/O）导致的反转；不能防死锁；提升/恢复本身有开销。
- 「为什么用户态自旋锁不能做优先级继承？」→ 考点是等待关系不可见。答法：自旋者不睡眠，内核看不到谁在等；持有者可能已被更高优先级任务抢占或不在同一 CPU，继承了也没法立刻运行；实时内核里要改用会睡眠的 rtmutex 或直接禁抢占。

## 第 5 章 活锁、饥饿与公平性

**要解决的问题**：并发系统里“不阻塞”不等于“有进展”。活锁和饥饿都不会表现出死锁那种明显的挂起——CPU 正常、线程都在跑、日志一直在刷，但业务指标不动。这一章解决的是：当系统的推进保证依赖“重试策略 + 排队规则”而不是锁本身时，怎么保证每个参与者最终都能前进。

**机制**：

先划清三者的边界，这是回答所有相关问题的地基：

- 死锁：所有参与者阻塞等待，CPU 空转，栈上全是等锁。
- 活锁：所有参与者都在运行，但状态互相抵消，系统级无进展。
- 饥饿：系统整体有进展，但某个特定参与者长期轮不到。

活锁的两个典型形态。第一种是**冲突重试无退避**：CAS 失败立刻重试，冲突率不降反升，重试本身还加剧了总线流量。修复手段是指数退避加随机抖动：

$$t_n = \min(t_{max},\ t_0 \cdot 2^n) \cdot U(0.5,\ 1.5)$$

退避降低碰撞频率，抖动打破“所有人在同一时刻失败、又在同一时刻重试”的相位同步。第二种是**对称谦让**：两个线程检测到冲突后同时释放已持资源再重试，动作完全镜像，下一轮仍然冲突。修复是引入不对称量——按 ID 排序、随机等待、或者取号。

饥饿的根因是排队规则里不含“年龄”。三种常见来源：

- **非公平锁**：释放锁时新到的线程直接在快路径上抢（barging），等待队列里的线程永远排在“刚到的”后面。`synchronized` 与 `ReentrantLock(false)` 都是这种。
- **读写锁偏向读者**：读持续不断时，写者等不到“无读者”的空窗。glibc 的 `pthread_rwlock_t` 默认行为偏读者，需要 `pthread_rwlockattr_setkind_np` 设 `PTHREAD_RWLOCK_PREFER_WRITER_NONRECURSIVE_NP` 来抑制写者饥饿（具体默认值按 glibc 版本与实现而定）。反过来，Go 的 `sync.RWMutex` 在有 writer 等待时会阻塞新读者，于是被饿死的是读者。
- **优先级**：实时任务占满 CPU，普通任务轮不到。Linux CFS 用 vruntime 记账，醒得晚的任务 vruntime 更小、更容易被选中，天然抗饥饿；但 SCHED_FIFO 的 RT 任务不主动让出，只能靠 `sched_rt_runtime_us` 的带宽上限兜底。

公平性的实现手段无非三类：严格 FIFO（ticket lock、取号队列，无饥饿但 cache 不友好）、按年龄提升优先级（MLFQ、写者优先）、以及队列序选择（LIFO 提升 cache 局部性与吞吐，但队尾任务可能永久饥饿；FIFO 公平，代价是吞吐）。

```python
def cas_with_backoff(counter):
    n = 0
    while True:
        old = counter.load()
        if counter.compare_exchange(old, old + 1):
            return old
        n += 1
        t = min(MAX_BACKOFF, BASE << min(n, 10))
        sleep(random.uniform(0.5, 1.5) * t)   # 抖动打散相位
```

**最小例子**：用一个实时任务制造饥饿，观察低优先级任务的唤醒延迟。

```bash
# 终端 A：SCHED_FIFO 忙循环，不主动让出
sudo chrt -f 50 sh -c 'while :; do :; done'
# 终端 B：普通任务测唤醒延迟
time sleep 1
```

A 跑起来后，B 的 `sleep 1` 实际耗时明显变长，具体倍数取决于核数与 `/proc/sys/kernel/sched_rt_runtime_us` 的当前值（先 `cat` 一下确认，它给 RT 任务留了运行上限，所以是“严重延迟”而不是完全饿死）。把 A 换成 `chrt -o 0` 改回 SCHED_OTHER，或直接 kill 掉，B 的延迟回到正常。记着清理 A，别让它一直占着核。

**面试高频问法**：

1. 问法：「活锁和死锁线上怎么区分？」
   考点：两者的可观测信号完全不同，考你有没有真排查过。
   答法：死锁看线程栈全卡在等锁、CPU 低；活锁看 CPU 高、重试计数暴涨但业务成功数不涨——判断依据是“重试次数/成功数”这个比值，不是 CPU。

2. 问法：「重试为什么必须加随机抖动，只做指数退避行不行？」
   考点：相位同步问题。
   答法：指数退避只降低重试频率，不打破同步；一批客户端同时失败就会同时重试，加抖动才能把碰撞概率打散，这跟 CSMA/CD 的退避和 Raft 的随机选举超时是同一个思路。

3. 问法：「公平锁一定更好吗？」
   考点：公平性的代价。
   答法：不是。公平锁要排队、要唤醒、要上下文切换，吞吐和 cache 局部性都变差；只有当“某个线程被无限期推迟会造成业务后果”（写锁、任务队列、消息消费位点）时才值得强制公平。

4. 问法：「读写锁为什么会出现写者饥饿，怎么解？」
   考点：读者并发进入导致空窗消失。
   答法：读者可以并发进入，写者必须等无读者的瞬间，读流量持续不断时这个瞬间不出现；解法是写者优先，或者等 writer 到达阈值后阻塞新读者，glibc 里就是设 `PTHREAD_RWLOCK_PREFER_WRITER_NONRECURSIVE_NP`。

5. 问法：「任务队列用 LIFO 有什么问题？」
   考点：吞吐与公平的权衡。
   答法：LIFO 让热数据留在队头，cache 命中好、吞吐高，但队尾的老任务可能永远轮不到；要补一个最大等待时间或定期把队尾翻上来。

## 第 6 章 缓存击穿、雪崩与热 key

**要解决的问题**：缓存的价值是把后端 QPS 压到它能承受的量级，但缓存失效不是均匀渐变的，而是三种突变：单 key 失效的瞬间、大批 key 同时失效或缓存层整体不可用、单 key 流量超过单节点能力。这一章解决的是让失效流量变得可预测，并且在失效窗口内后端不被打穿。

**机制**：

先分清四个词，这是这一章的第一道面试题：

- **穿透**：查一个根本不存在的 key，缓存永不命中，每次都打 DB。
- **击穿**：一个热点 key 到期，瞬间并发全部落到 DB。
- **雪崩**：大量 key 同一时刻过期，或缓存集群整体故障。
- **热 key**：单 key 的 QPS 超过一个节点/一个分片的承载能力，即使不过期也是瓶颈。

**击穿的解法是单飞**：把“回源”这个动作按 key 合并，只放一个请求去查 DB，其余等结果。

```go
v, err, _ := group.Do(key, func() (any, error) {
    if v, ok := local.Get(key); ok {
        return v, nil
    }
    v, err := db.Query(key)          // 只有一个 goroutine 真正回源
    if err == nil {
        cache.Set(key, v, ttlWithJitter())
    }
    return v, err
})
```

（`group` 即 `golang.org/x/sync/singleflight` 的 `Group`，`Do` 返回结果、错误和一个 `shared` 标志表示本次结果是否被多方共享。）

三个必须注意的点：合并粒度由 key 决定，key 设计粗了会把不相关请求合并；慢请求会让所有等待者一起变慢，尾延迟被放大；错误会广播给所有等待者，所以不能把“这次失败”当成“这个 key 不存在”写进缓存。跨进程的单飞要靠分布式锁，例如 `SET lock:{key} 1 NX PX 3000`，抢不到锁的请求短暂等待后重读缓存。

**雪崩的解法**是分层防御：TTL 抖动，$ttl = base + U(0, J)$，$J$ 通常取 $base$ 的 10%~20%，把“同一秒过期”摊成一条斜线；发布前异步预热，避免上线瞬间全空；多级缓存，本地缓存挡一层，Redis 挂了还有兜底（代价是一致性窗口）；客户端或 DB 侧限流熔断，宁可拒绝也不要把 DB 拖死；缓存层本身做多副本/Cluster，消除“整个缓存层消失”这个最坏情况。

**热 key 的解法**先探测再处理。探测手段有 `redis-cli --hotkeys`（需要淘汰策略为 LFU 系列）、客户端埋点统计、代理层采样。处理手段有三类：本地缓存把“每请求一次 Redis”降到“每进程每几秒一次”；key 拆分 `hotkey:{0..N}`，写时写 N 份或写主 key 异步同步，读时轮询分散到多个分片；读写分离、多副本读。

**最小例子**：

```bash
# 1) TTL 抖动前：所有 key 都是 3600 秒，同一秒集体过期
redis-cli SET sku:1 v EX 3600
redis-cli TTL sku:1
# → (integer) 3600

# 2) NX 互斥：只有一个请求能拿到回源权
redis-cli SET lock:sku:1 1 NX PX 3000
# → OK
redis-cli SET lock:sku:1 1 NX PX 3000
# → (nil)   # 第二个请求拿不到锁，走“短暂等待 + 重读缓存”

# 3) 找热 key，先切到 LFU 淘汰策略
redis-cli CONFIG SET maxmemory-policy allkeys-lfu
redis-cli --hotkeys
# → 按访问频率列出的 key（采样结果随实例状态而定）
```

第 1 步就复现了雪崩的成因：把 `EX 3600` 换成 `EX $((3600 + RANDOM % 600))`，过期点就散到 10 分钟的窗口里。

**面试高频问法**：

1. 问法：「击穿、雪崩、穿透有什么区别？」
   考点：是不是把三个词当同义词背。
   答法：穿透是 key 压根不存在，击穿是单个热 key 过期，雪崩是大面积同时失效或缓存层故障；对应解法分别是布隆过滤器/空值缓存、单飞或分布式锁、TTL 抖动加多级缓存加熔断。

2. 问法：「singleflight 有什么坑？」
   考点：合并的副作用。
   答法：粒度是 key，key 设计错会把不相关请求合并；一次慢回源会让所有等待者一起超时，放大尾延迟；错误会广播给所有等待者，所以不能把一次失败当不存在缓存起来。

3. 问法：「逻辑过期和互斥重建怎么选？」
   考点：可用性与一致性的取舍。
   答法：逻辑过期把过期时间写在 value 里，过期后仍返回旧值并异步刷新，可用性优先但有一致性窗口；互斥重建是同步等结果，一致性好但把延迟直接暴露给用户。热点 key 通常选前者。

4. 问法：「TTL 抖动为什么能缓解雪崩，范围怎么定？」
   考点：是否知道抖动也有代价。
   答法：把同时过期摊平到一段时间上；范围取 base 的 10%~20%，太小没效果，太大会拉低命中率、拉长脏数据窗口，上限必须小于业务能容忍的陈旧时间。

5. 问法：「热 key 拆成 N 份之后，写怎么保证一致？」
   考点：拆分带来的写放大。
   答法：要么写 N 份并做部分失败的补偿，要么写主 key 再异步同步到副本、读时允许短暂不一致；N 按“单 key QPS / 单节点安全水位”估，估不出来就先做本地缓存挡一层。

## 第 7 章 队头阻塞：TCP 层与应用层

**要解决的问题**：说明“一条连接/一个 worker 上的慢任务会拖垮整条链路”这一现象的两种来源：TCP 的按序交付（协议强制）与应用层的串行模型（设计选择）。不解决这个问题，就会误以为“换成 HTTP/2 或加连接池就没事了”，而在丢包率上升或出现单个慢请求时出现无法解释的 p99 长尾。

**机制**：TCP 提供的是**有序字节流**，不带消息边界，也不带流 ID。接收端把乱序到达的段放进 out-of-order 队列缓存但**不交付**，`read()` 只有在 `rcv_nxt` 之前的空洞被填上后才返回数据。所以只要一条 TCP 连接上有一次丢包，这条连接上所有复用它的逻辑请求会一起等待重传，等待量级是 $RTO$（Linux 的 $RTO_{min}$ 通常在 200 ms 量级，按内核实现而定）。

```python
# 接收端交付语义（伪代码）：一处空洞，全连接停摆
next_seq = rcv_nxt
while True:
    seg = recv_segment()
    if seg.seq == next_seq:
        deliver(seg.data); next_seq += len(seg.data)
        while next_seq in ooo:            # 补齐后一次性放行
            deliver(ooo.pop(next_seq)); next_seq += len(ooo_chunk)
    elif seg.seq > next_seq:
        ooo[seg.seq] = seg.data           # 缓存，但不交付给应用
    # 应用侧此时 read() 拿不到任何字节 → 复用该连接的所有请求一起等
```

应用层的队头阻塞来自另一个方向：单连接串行（HTTP/1.1 pipelining）、单 worker 阻塞（worker 里做同步磁盘 IO / 同步下游调用）、单线程数据结构的排队（Redis 单个大 key 的 `O(N)` 命令、阻塞队列前面的慢任务）。判断口径很简单：**是否共享同一个“交付序列”或同一个“执行线程”**——共享就是队头阻塞的候选。

三种改进各自处理的范围：
- HTTP/2：多路复用解决的是**应用层**队头阻塞（多个请求并发在同一条连接上），但底层仍是一条 TCP，丢包时全部 stream 一起等。
- QUIC：跑在 UDP 上，每个 stream 有自己的偏移和重传，一个 stream 丢包只阻塞自己，同时绕开了内核 TCP 的状态。
- 连接池 / 多连接：用 $N$ 条独立的阻塞域换并发，代价是握手、TLS、fd 和慢启动，不是免费的。

**最小例子**：用 `ab -k` 保持 keep-alive，对比单连接串行与多连接并发，在有无丢包两种情形下的 p99。

```bash
tc qdisc add dev lo root netem loss 1%          # 仅测试机，回环注入 1% 丢包
ab -k -c 1  -n 200 http://127.0.0.1:8080/x      # 单连接串行
ab -k -c 10 -n 200 http://127.0.0.1:8080/x      # 10 条连接
tc qdisc del dev lo root
```

在无丢包时，两者 p99 差距主要由服务端并发度决定；注入 1% 丢包后，`-c 1` 的 p99 会被抬高到接近 $RTO$ 量级（每次丢包都让该连接后续请求一起等重传），而 `-c 10` 因为阻塞域被切成 10 份，长尾被摊薄。具体数值按机器与服务端实现而定，要看的是**丢包前后 p99 的抬升幅度是否随并发度变化**。

**面试高频问法**：

1. **“HTTP/2 解决了队头阻塞吗？”** → 考点是能否区分两层：应用层多路复用 vs 传输层按序交付 → 答法：“只解决了一半。HTTP/2 在同一条 TCP 上多路复用，解决了 HTTP/1.1 的串行请求队头阻塞；但底层还是一条有序字节流，一个包丢了所有 stream 一起等重传，所以才有 QUIC 把流控和重传下沉到每条 stream。”
2. **“为什么 TCP 不能像 QUIC 那样按流交付？”** → 考点是 TCP 的接口契约 → 答法：“TCP 对应用暴露的是无边界字节流，内核不知道你上层有几条逻辑流，也不知道每条流归属哪些字节，所以只能维护一个 `rcv_nxt`；要按流交付就必须在协议头里加流 ID，那是 QUIC 干的事。”
3. **“线上 p99 突然变高但吞吐正常，怎么怀疑到队头阻塞？”** → 考点是定位路径 → 答法：“先看 `ss -tin` 的 `Recv-Q`/`Send-Q` 和重传、`rtt`，再看是不是所有请求都慢还是只有部分慢；如果只有复用同一条连接的那批一起慢、且和丢包率相关，就是 TCP 层；如果慢请求后面跟着一串等待的，就是 worker 或队列的串行。”
4. **“为什么不能干脆一个请求一条连接？”** → 考点是代价意识 → 答法：“TCP 三次握手加 TLS 握手，加上新连接的慢启动，短请求下开销占比极高；而且连接数直接吃掉 fd 和端口，服务端还要为每条连接维护缓冲区，所以连接池是在阻塞域和开销之间取平衡。”

## 第 8 章 TIME_WAIT 与端口耗尽

**要解决的问题**：TIME_WAIT 是**主动关闭方**必然会进入的状态，它不是泄漏也不是 bug；但它会把四元组占住一段时间，在短连接 + 单后端的场景下直接表现为“连不上（Cannot assign requested address）”。这一章要能把“TIME_WAIT 堆积”拆成“该不该有”和“谁该有”两个问题。

**机制**：四次挥手中，主动关闭方发出最后一个 ACK 后进入 `TIME_WAIT`，持续 $2 \times MSL$（Linux 上通常固定为 60 秒，按内核实现而定）。它承担两件事：

1. **保证最后的 ACK 能重传**：如果这个 ACK 丢了，对方会重发 FIN，处于 TIME_WAIT 的一方还能再回一次 ACK；若直接进 CLOSED，对方收到的是 RST，连接被异常终止。
2. **让旧连接的残余段在网络中消亡**：同一四元组上如果立刻建立新连接，旧连接迟到的重复段可能被新连接当成有效数据收下。TIME_WAIT 相当于给这个四元组一个静默期。

关键推论：**被动关闭方不进 TIME_WAIT**（它走 `CLOSE_WAIT → LAST_ACK → CLOSED`）。所以：

- 客户端大量 TIME_WAIT：说明是客户端先关，且短连接，**真的会耗尽本地端口**。
- 服务端大量 TIME_WAIT：说明服务端先关（HTTP/1.0、或 keepalive 超时短于客户端），但服务端本地端口固定、靠四元组区分连接，**主要成本是内存和 fd，不是端口**，通常不需要处理。

端口上限的算术：可用端口数 = `ip_local_port_range` 的跨度，到**同一个** `dst_ip:dst_port` 的连接受这个数限制。

```bash
sysctl net.ipv4.ip_local_port_range      # 例如 32768  60999
ss -tan state time-wait | wc -l          # 当前 TIME_WAIT 数
cat /proc/net/sockstat                   # TCP: inuse ... tw ...
sysctl net.ipv4.tcp_tw_reuse             # 出新连接时复用 TIME_WAIT
```

按上例跨度 28232 个端口、每条占 60 秒估算，到单一后端的稳定新建速率上限约为 $\frac{28232}{60} \approx 470$ 条/秒；超过这个量就会开始在 `connect()` 上失败。注意这是**算术上界**，实际还要扣掉保留端口和其他出向连接。

手段与边界：
- **长连接 / 连接池**：根治，把“每秒新建”变成“一次性建立”。
- **多目标地址**：后端有多个 IP 时，端口池按 `dst_ip` 分别计算，等效扩容。
- **`tcp_tw_reuse=1`**：只作用于**主动发起的新连接**，且依赖 TCP 时间戳（`tcp_timestamps`）来区分旧连接的迟到段，所以在 NAT 后时间戳被改写等场景要谨慎。
- **`tcp_tw_recycle`**：已在新内核移除（4.12 起），面试里提到它基本等于暴露知识过期。
- **`tcp_max_tw_buckets`**：只是限制数量上限、超出直接销毁，掩盖现象不解决问题。
- **`SO_LINGER` 置 0**：`close()` 直接发 RST，绕过 TIME_WAIT，但会丢弃发送缓冲里未确认的数据，也可能让对端读到 RST 而非正常 EOF，属于“明知道有数据风险才用”的手段。

**最小例子**：在客户端机器上快速建立大量短连接到同一后端，复现端口耗尽。

```bash
# 1) 压出一批短连接（每次请求后关闭）
for i in $(seq 1 20000); do curl -s -o /dev/null http://10.0.0.5:80/ & done; wait
# 2) 观察
ss -tan state time-wait | wc -l
ss -tan state time-wait | awk '{print $4}' | cut -d: -f2 | sort -u | wc -l
# 3) 继续加压，出现：curl: (7) Failed to connect ... Cannot assign requested address
```

预期结果：第 2 步的 TIME_WAIT 数和去重后的本地端口数接近，说明端口被四元组占满；第 3 步的报错来自 `connect()` 拿不到可用的本地端口（`EADDRNOTAVAIL`）。把请求改成复用连接池（或用 `ab -k`）后同一压力下不再报错，即可确认因果。

**面试高频问法**：

1. **“TIME_WAIT 为什么必须存在？去掉行不行？”** → 考点是协议正确性而非运维 → 答法：“两个作用：一是最后的 ACK 丢了还能重传，否则对端会收到 RST；二是给这个四元组一个静默期，让旧连接的迟到重复段消亡，不会污染立刻复用的新连接。去掉会引入连接异常终止和串数据的风险。”
2. **“服务端 TIME_WAIT 几万个，是问题吗？”** → 考点是分清主动/被动关闭方 → 答法：“TIME_WAIT 只出现在主动关闭方。服务端有 TIME_WAIT 说明是它先关连接，通常来自短连接或 keepalive 超时比客户端短；服务端本地端口固定，靠四元组区分连接，不会端口耗尽，成本只是内存和 fd，一般先去看是不是该改成让客户端先关或者调长 keepalive。”
3. **“客户端报 Cannot assign requested address 怎么查？”** → 考点是从现象推到端口池 → 答法：“这是 `connect()` 拿不到本地端口。看 `ip_local_port_range` 和 `ss -tan state time-wait` 的去重端口数，如果两者逼近就是耗尽；根因通常是短连接打同一后端，解法是连接池或长连接，临时可以开 `tcp_tw_reuse`。”
4. **“`tcp_tw_reuse` 为什么要求开时间戳？”** → 考点是复用的安全性从哪来 → 答法：“复用 TIME_WAIT 的四元组本质上是赌旧连接的残留段不会再被误收。时间戳让新连接能通过 PAWS 把旧段判掉，没有时间戳就没有区分依据，复用就会串数据。”
5. **“`SO_LINGER` 设 0 是不是能绕过 TIME_WAIT？”** → 考点是代价意识 → 答法：“能，`close()` 直接发 RST，跳过后面的挥手。但发送缓冲里没确认的数据会丢，对端拿到的是 RST 不是正常 EOF，可能触发对端错误日志或重试；只有在明确允许丢数据的场景才用。”

## 第 9 章 fd 耗尽与 EMFILE 的连锁反应

**要解决的问题**：文件描述符是进程级的有界资源，一旦耗尽，失败不会只限于某一个模块：**连“处理错误”的代码本身都会失败**（日志文件打不开、等待队列写入失败、探活 socket 创建不出来），一次小泄漏因此被放大成整个进程不可用。

**机制**：

fd 是进程 fd table 的下标，表的上限由 `RLIMIT_NOFILE` 软限制决定（`ulimit -n`）；内核全局还有一张 `struct file` 表，受 `file-max` 约束。两层对应两个 errno：

- `EMFILE`：**进程**的 fd table 满了 —— 你自己的泄漏；
- `ENFILE`：**内核全局** file 表满了 —— 通常是同机别的进程在泄漏。

真正致命的是 Linux 上 `accept()` 在 fd 表满时的行为：它返回 `EMFILE`，但**不会把连接从 accept 队列取走**。于是监听 socket 在 epoll 里永远可读（水平触发），事件循环被这个就绪事件反复唤醒、每次都失败，CPU 空转；正常连接也进不来。这就是“连锁反应”的第一环。第二环是错误路径：想写日志 → `open()` 失败 → 返回错误 → 上层重试 → 又消耗 fd。第三环是子进程/`exec`/DNS 解析，它们全都需要 fd。

标准解法是**预留一个 idle fd** 做占位，收到 `EMFILE` 时先释放它、把连接取出来立刻关掉、再补回占位：

```c
int idle_fd = open("/dev/null", O_RDONLY);   // 启动时占位，永不使用
for (;;) {
    int c = accept4(lfd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (c < 0) {
        if (errno == EMFILE || errno == ENFILE) {
            close(idle_fd);                  // 腾出一个名额
            c = accept(lfd, NULL, NULL);     // 把队头连接取走
            if (c >= 0) close(c);            // 立刻关闭，让客户端尽快失败而非挂到超时
            idle_fd = open("/dev/null", O_RDONLY);  // 恢复占位
            continue;
        }
        if (errno == EAGAIN || errno == EWOULDBLOCK) break;  // ET 下必须循环到 EAGAIN
        if (errno == EINTR) continue;                        // 见第 12 章
        break;
    }
    handle(c);
}
```

要点：idle fd 只能让**单个连接**快速失败，不解决根本问题；想限流还得在 accept 路径上做拒绝或从 epoll 摘掉 listen fd（连接会留在 backlog 里，不丢，但你也不再消费）。

**最小例子**：用 16 个 fd 的限额跑一个自增打开文件的小程序：

```python
import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
fds = []
try:
    while True:
        fds.append(open('/dev/null'))
except OSError as e:
    print(len(fds), e)
```

典型输出是 `[Errno 24] Too many open files`（0/1/2 和解释器自身已占若干）。线上排查对应命令：

```bash
ls -l /proc/$(pgrep -f myserver)/fd | wc -l          # 当前占用
lsof -p <pid> | awk '{print $5}' | sort | uniq -c    # 按类型/状态聚合
ss -tanp | grep <pid> | awk '{print $1}' | sort | uniq -c  # 看是不是连接没关
```

**面试高频问法**：

1. **EMFILE 和 ENFILE 有什么区别？** → 考点是“资源有哪几层”。→ 一句话答法：EMFILE 是本进程的 fd 表满了，泄漏在自己身上；ENFILE 是内核全局 file 表满了，污染源在同机其他进程，排查方向完全不同。
2. **accept 返回 EMFILE 之后，直接 `continue` 行不行？** → 考点是 accept 队列语义与 epoll 行为。→ 答：不行，Linux 在 fd 满时不会把连接取走，listen fd 一直可读，水平触发下事件循环会 100% 空转，得先用预留的 idle fd 腾出名额把连接取走丢掉。
3. **怎么定位 fd 泄漏？** → 考点是可观测性。→ 答：先 `/proc/<pid>/fd` 计数看趋势确认是否单调涨，再用 `lsof` 或 `ss` 按 peer/状态聚合，找出是哪一类 fd（连接、文件、epoll、eventfd）在涨，最后回去看那条路径的异常分支有没有漏 close。
4. **fd 耗尽为什么连健康检查都失败、进程被摘掉？** → 考点是连锁性。→ 答：探活、日志、DNS 查询都要创建 fd，同一个资源池被抢光时它们一起失败，监控看到的是“整个进程不可用”而不是“某个接口变慢”。
5. **把 `ulimit -n` 调到 100 万算解决吗？** → 考点是治标。→ 答：只是把故障推迟，泄漏仍在，而且 fd table 变大后遍历与 `select` 类调用的开销变化按实现而定；正确做法是限流 + 修泄漏 + 保留 idle fd 兜底。

## 第 10 章 内存碎片与 OOM killer

**要解决的问题**：进程“看起来没泄漏”但 RSS 只涨不落，或者系统 `free` 明明还有内存、容器却因为 `memory.max` 被 OOM 杀掉 —— 要能把**内部碎片、外部碎片、allocator 缓存、cgroup 限制**四件事分开归因，否则调参永远打偏。

**机制**：

三层的区别先要分清：

- **内部碎片**：分配器按 size class 向上取整。请求 $n$ 字节拿到 $\text{roundup}(n)$ 字节，浪费比 $w=\frac{\text{roundup}(n)-n}{\text{roundup}(n)}$，小对象在小 size class 里最严重。
- **外部碎片**：空闲总量够，但没有一块**连续**空间满足本次请求，于是向 OS 再要内存，RSS 继续涨。
- **allocator 缓存**：这才是“RSS 不落”的最常见解释。

glibc malloc 的路径决定归还行为：小的分配来自 per-thread 的 arena（多线程会开出多个 arena，数量有上限，按实现而定），free 之后先进 tcache / fastbin，内存仍属该 arena；只有 top chunk 尾部超过 trim 阈值时才 `brk` 回缩到 OS，而堆中间的洞无法回缩（要搬移，等于复制整个堆）。超过 `M_MMAP_THRESHOLD`（glibc 初始约 128 KiB，会随释放行为动态上调，具体按版本和配置而定）的大块走 `mmap`，free 时 `munmap`，**这块是真的立刻还给 OS**。

所以典型故障形态是：常驻小对象和周期性大对象交错分布，峰值过后 `brk` 堆被打成筛子，RSS 停在峰值附近。

OOM 侧要看触发者是谁：

- **cgroup v2**：`memory.max` 是硬墙。`memory.current` 逼近时**先回收 page cache**，回收不动才触发 cgroup OOM；`memory.oom.group=1` 时杀整个 cgroup，否则杀其中单个进程。
- **宿主内核 OOM killer**：按 `oom_score` 挑受害者，主因子是 RSS 占比，叠加 `oom_score_adj`（-1000 免疫，1000 最优先被杀）。`/proc/<pid>/oom_score` 可读。
- **overcommit**：`vm.overcommit_memory=0` 启发式、`1` 总是允许、`2` 严格按 `CommitLimit`；`1` 下 malloc 几乎不会失败，代价是真正触碰页面时才 OOM。

**最小例子**：

```c
void *p[100000];
for (int i = 0; i < 100000; i++) p[i] = malloc(64);   // 小对象落在 brk 堆
for (int i = 0; i < 100000; i += 2) free(p[i]);       // 交替释放，留下大量无法合并的洞
void *big = malloc(4 << 20);                          // 超过 mmap 阈值
free(big);                                            // munmap，RSS 立刻下降
malloc_trim(0);                                       // 显式要求把 top 之上的内存还给 OS
```

观测与复现：

```bash
grep -E 'VmRSS|VmSize|RssAnon|RssFile' /proc/$(pgrep -f myserver)/status
mkdir /sys/fs/cgroup/demo && echo 100M > /sys/fs/cgroup/demo/memory.max
echo $$ > /sys/fs/cgroup/demo/cgroup.procs   # 把当前 shell 关进 100M 的盒子
cat /sys/fs/cgroup/demo/memory.events        # 出现 oom / oom_kill 计数即已被杀
```

**面试高频问法**：

1. **RSS 一直涨，但 ASan / valgrind 说没有泄漏，怎么解释？** → 考点是“泄漏”与“未归还”不是一回事。→ 答：内存还在 allocator 手里（tcache / arena 缓存 + 外部碎片），没有指针可达性泄漏；要看 `malloc_trim` 后是否回落、以及分配大小分布是否被打散。
2. **内部碎片和外部碎片分别由什么造成？** → 考点是 allocator 结构。→ 答：内部碎片来自 size class 向上取整，请求越小浪费比例越大；外部碎片来自 bin 里没有满足大小的连续 chunk，空闲总量够但没法用。
3. **`free()` 之后内存为什么没还给 OS？** → 考点是 brk/mmap 两条路径。→ 答：`brk` 只能从堆顶回缩，中间的洞回收不了；只有走 `mmap` 的大块 free 时直接 `munmap`，所以大分配的 RSS 曲线是锯齿，小分配是平台。
4. **OOM killer 怎么选受害者？** → 考点是评分模型。→ 答：宿主上看 `oom_score`，主要是 RSS 占比，再用 `oom_score_adj` 人工加权（-1000 免疫）；容器里先撞 `memory.max`，触发 cgroup OOM，`memory.oom.group` 决定杀一个还是整组。
5. **把 `vm.overcommit_memory` 设成 1 有什么风险？** → 考点是延迟失败。→ 答：malloc 几乎不会返回失败，应用以为申请成功，真正写页面时才 OOM，失败点离根因很远；Redis 之类的 fork 场景常被迫这么设，但要配合 `maxmemory` 和 cgroup 兜底。
6. **怎么缓解长期运行服务的碎片？** → 考点是工程手段而非单一 API。→ 答：按大小分池复用对象、避免小大交错、限制 arena 数量、把大分配独立走 mmap 或单独区域、必要时重启或 `malloc_trim`；换 jemalloc/tcmalloc 的 size class 设计也只是缓解。

## 第 11 章 Nagle 与延迟 ACK 的交互、粘包与半包

**要解决的问题**：解释两件事——为什么一个小请求被拆成两次 `write` 后会莫名多出几十毫秒；为什么 `read` 一次拿不到一条完整消息。不解决这两个问题，线上会表现为“RPC 偶发慢”和“分帧解析器在压力下偶发错位”，而且两者都极难通过读业务代码发现问题。

**机制**：

Nagle 是发送端策略（RFC 896）：任一时刻最多允许一个“未被确认的小段”（< MSS）在途。伪代码只有四行：

```
on write(data):
    if 待发 >= MSS or 没有未确认的小段 in flight or TCP_NODELAY:
        send_now(data)
    else:
        buffer(data)          # 等 ACK 到达，或攒够一个 MSS 再发
```

Linux 里对应的判断在 `tcp_nagle_check()`：非满段 + 存在未确认数据 + 未设 `TCP_NODELAY`/`MSG_MORE` → 推迟发送。

延迟 ACK 是接收端策略：收到数据后不立刻确认，期望把 ACK 捎带在响应上，或等第二个段一起确认。Linux 上该定时器是毫秒级（常见约 40ms 量级，具体按实现与连接状态而定），另有 quickack 模式在特定条件下立即确认。

两者叠加，就是经典的 write-write-read 互锁：

1. 客户端 `write(header)`，header 是满段以外的小包，直接发出。
2. 客户端 `write(body)`，body 小，且 header 尚未被确认，被 Nagle 扣在发送缓冲区。
3. 服务端收到 header，延迟 ACK 定时器启动；服务端的 `read` 阻塞等 body。
4. 定时器到期，ACK 上送。
5. 客户端 Nagle 收到 ACK，才放出 body。

一次逻辑交互的成本变成 $T = \mathrm{RTT} + T_{\text{delack}}$。这笔延迟落在应用线程阻塞的 `read` 上，从外部看就是“网络偶尔会慢一下”。

粘包、半包与 Nagle 无关，但总被一起问：TCP 提供的是字节流，`read` 返回的是内核接收缓冲区“当前有多少字节”，和 `write` 的调用边界没有任何对应关系。$M$ 次 `write` 被 $N$ 次 `read` 取走，$M$、$N$ 之间无约束。消息边界只能由应用层协议定义：

- 定长（简单，浪费带宽）；
- 分隔符（`\r\n`，需处理转义，且分隔符可能跨两次 `read`）；
- 长度前缀（最常用：定长 4 字节或 varint 长度 + payload；gRPC、HTTP/2 frame、protobuf delimited 都是这个思路）；
- 自描述格式。

解析器必须是有状态的：先凑够头部，从头部解出 body 长度，再凑够 body，循环解析直到剩余字节不足（这就是半包），残余字节留在缓冲区等下一次 `read`。长度字段必须设上限，否则对端一个伪造的 4 字节长度就足以让你 `malloc` 到 OOM。

**最小例子**：

```bash
# 终端 1：服务端必须凑齐 4 字节长度 + body 才回（人为制造 write-write-read）
python3 - <<'EOF'
import socket, struct
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', 9000)); s.listen(1)
c, _ = s.accept()
hdr = b''
while len(hdr) < 4: hdr += c.recv(4 - len(hdr))      # 半包：循环凑头部
n = struct.unpack('!I', hdr)[0]
body = b''
while len(body) < n: body += c.recv(n - len(body))   # 半包：循环凑 body
print('got', body); c.sendall(b'ok'); c.close()
EOF

# 终端 2：看分段与 ACK 时序
tcpdump -i any -n -tttt 'tcp port 9000'

# 终端 3：客户端分两次写
python3 -c "
import socket, struct
c = socket.create_connection(('127.0.0.1', 9000))
c.send(struct.pack('!I', 2)); c.send(b'hi')          # 两次小写
print(c.recv(2))"
```

典型形态：客户端第二个 `[P.]` 段的时间戳紧跟服务端 `[.]` ACK 之后，间隔由延迟 ACK 定时器决定（回环上几乎为 0，真实链路常见

## 第 12 章 信号与系统调用：EINTR、信号丢失、fork 后的锁状态

**要解决的问题**：信号会异步打断阻塞系统调用、合并同类事件，并在 `fork` 时把“别的线程正持有的锁”复制进子进程；不处理这三件事，服务会出现随机 `EINTR` 失败、事件丢失和子进程死锁。

**机制**：

`EINTR` 的来源是“信号递达”和“系统调用睡眠”撞在一起。进程阻塞在 `read`、`write`、`accept`、`poll` 等调用上时，信号处理函数执行；如果该调用不可自动重启，内核让它返回 `-1`，并把 `errno` 设为 `EINTR`。`SA_RESTART` 只对一部分系统调用生效，`poll`、`select`、`epoll_wait`、`nanosleep` 等仍可能被信号打断，所以不能靠一个标志一劳永逸。正确姿势是显式重试，并且读写要按返回值推进偏移：

```c
ssize_t n;
do {
    n = read(fd, buf, len);
} while (n < 0 && errno == EINTR);
```

但 `read` 返回正数也可能只读了一部分，`write` 同理；`EINTR` 重试和“短读写循环”是两件事。对于 `poll` 这类带超时的调用，被打断后还要重新计算剩余超时，不能把 `EINTR` 当普通错误退出事件循环。

信号丢失有两个典型来源。第一，标准信号不排队：同一种标准信号处于未决状态时，内核只保留一个“未决位”，连续 `kill` 三次可能只触发一次处理。实时信号有排队能力，但队列也有上限。第二，检查标志和睡眠之间存在竞态：

```c
if (!flag) pause();   // 信号可能刚好在 if 和 pause 之间到达
```

信号在这条缝里到达，`pause()` 就会永久睡下去。标准解法是“先阻塞信号，检查标志，再用 `sigsuspend` 原子地解除阻塞并睡眠”；工程上更常用 self-pipe 或 Linux 的 `signalfd`：信号处理函数只做 async-signal-safe 的 `write` 一个字节，主循环从 pipe/fd 读事件，业务逻辑不放进 handler。handler 里不能 `printf`、`malloc`，共享标志用 `volatile sig_atomic_t`。

`fork` 后的锁状态更隐蔽。`fork` 只复制调用线程，不复制其他线程。若线程 A 持有 `pthread_mutex_t`，线程 B 调用 `fork`，子进程会继承“已加锁”的 mutex 内存，但持有者线程 A 在子进程里不存在；子进程再 `pthread_mutex_lock` 同一个 mutex，就等一个永远不会释放的锁。按 POSIX，子进程在 `exec` 前只应调用 async-signal-safe 函数，调用 `pthread_mutex_lock` 本身就不安全；在 glibc 上常见表现就是死锁。

解决方式有三类：第一，多线程进程尽量避免 `fork`，需要新进程时用 `fork` 后立即 `exec`，或使用 `posix_spawn`；第二，确实要在子进程里继续用锁，就用 `pthread_atfork(prepare, parent, child)` 在 `fork` 前按固定顺序获取自建锁，在父、子进程里分别释放；第三，把“fork 前必须加锁”的锁全部注册进去，不能假设第三方库内部锁也安全。文件锁还要区分：`fcntl` 记录锁通常不随 `fork` 继承，`flock` 锁与打开文件描述关联，`fork` 后可能共享；以目标系统语义为准。

**最小例子**：

父进程安装 `SIGUSR1` 处理函数且不设 `SA_RESTART`，子进程阻塞在 `read(pipefd[0], buf, 16)`。另一进程执行 `kill(pid, SIGUSR1)`，`read` 返回 `-1`、`errno=EINTR`；用重试循环后读到 5 字节。若父进程先用 `pthread_sigmask` 阻塞 `SIGUSR1`，连续 `kill` 三次再解除阻塞，处理函数只执行一次，因为标准信号的未决位被合并；要三次都处理，应使用实时信号，或让 handler 把每次事件写入 self-pipe，由主循环逐条消费。

`fork` 场景：线程 A 持有 mutex 时线程 B 调用 `fork`，子进程再锁同一 mutex 会卡死；改为 `pthread_atfork` 在 prepare 中加锁、parent/child 中解锁，或 `fork` 后立即 `exec`，可避开继承的锁状态。

**面试高频问法**：

- **问法**：为什么 `read` 会返回 `EINTR`？设了 `SA_RESTART` 是不是就不用管了？ → **考点**：信号打断阻塞系统调用，以及可重启调用的范围。 → **答法**：信号处理函数执行后，不可自动重启的系统调用会返回 `-1/EINTR`；`SA_RESTART` 只覆盖部分调用，`poll`、`select`、`epoll_wait`、`nanosleep` 等仍可能被打断，必须显式重试并处理短读写。

- **问法**：标准信号为什么会丢？怎么保证事件不丢？ → **考点**：标准信号未决位合并、实时信号排队、self-pipe/signalfd。 → **答法**：标准信号不排队，同种信号未决时只保留一个，连续到达会合并；要可靠计数用实时信号，工程上更常见的是 handler 只写 self-pipe 或 `signalfd`，把信号转成事件队列由主循环消费。

- **问法**：多线程程序 `fork` 后，子进程为什么会死锁在父进程的 mutex 上？ → **考点**：`fork` 只复制调用线程，锁内存被复制但持有线程不存在。 → **答法**：子进程继承了已加锁的 mutex，却没有能解锁的线程；POSIX 规定 `exec` 前只能调 async-signal-safe 函数，所以多线程进程应优先 `fork+exec`，自建锁则用 `pthread_atfork` 在 fork 前后加解锁。

- **问法**：`pthread_atfork` 能解决所有 fork 后的锁问题吗？ → **考点**：atfork 只覆盖注册过的锁，prepare/parent/child 的顺序和限制。 → **答法**：不能，它只处理你显式注册的锁；prepare 要按固定顺序加锁，parent/child 再释放，第三方库和未注册锁仍可能把子进程卡住，最稳的是 fork 后立即 exec。

- **问法**：信号处理函数里能不能 `printf` 或 `malloc`？ → **考点**：async-signal-safe 与可重入。 → **答法**：不能，handler 只能调用 async-signal-safe 函数，比如 `write`；共享标志用 `volatile sig_atomic_t`，真正的业务处理放到主循环，避免在信号上下文里碰锁和堆。
