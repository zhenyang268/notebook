# linux-api · 分章详细

## 第 1 章〔CPU〕进程与线程：fork / exec / wait / clone，父子进程的关系与代价

**要解决的问题**：线上两起典型事故。其一，守护进程反复 `fork()` 子进程却不 `wait()`，僵尸堆到 `pid_max`，之后所有服务报 `fork: Cannot allocate memory`，看起来像“内存不够”，实际是 pid 表满。其二，32 GB 的 Redis/JVM 做 `fork()` 快照，写入放大触发 COW 拆页，RSS 瞬间翻倍，被 OOM killer 杀掉，日志里只有一条 killed。此外还有一类：`exec` 前没给监听 fd 设 `FD_CLOEXEC`，socket 漏进子进程，重启时 `Address already in use`，用 `ss` 查不到占用者，因为占着它的是个不干活的子进程。不会这一章，你只能看到“进程起不来”，说不出“是 pid 耗尽、是 COW 翻倍、还是 fd 泄漏”。

**API 与代价**：

```c
#include <unistd.h>
#include <sys/wait.h>
#include <sched.h>

pid_t pid = fork();
if (pid == 0) {              /* 子进程：只复制了调用线程 */
    execl("/bin/prog", "prog", NULL);
    _exit(127);              /* 注意不是 exit() */
} else if (pid > 0) {        /* 父进程：拿到子 pid */
    int st;
    pid_t r = waitpid(pid, &st, WNOHANG);
    /* r==0   : 子进程还在，稍后再来
       r==-1  : errno==ECHILD 没有这个子进程（已被 SIG_IGN 回收或不是亲生的）
       WIFEXITED(st)/WEXITSTATUS(st)、WIFSIGNALED(st)/WTERMSIG(st) 才是退出码 */
} else {                     /* -1: EAGAIN(超 RLIMIT_NPROC/pid_max) 或 ENOMEM */
}

/* 线程 = 共享地址空间的 clone，内核里同样是 task_struct */
clone(fn, stack, CLONE_VM|CLONE_FS|CLONE_FILES|CLONE_SIGHAND|CLONE_THREAD|CLONE_SYSVSEM, arg);
```

`fork` 是唯一“返回两次”的调用，三分支里漏写 `pid < 0` 是经典 bug。`_exit` 与 `exit` 的差别是致命的：`exit` 会跑 `atexit`、flush stdio 缓冲，`fork` 后子进程调 `exit` 会把父进程未 flush 的缓冲区再写一遍（第 8 章会再碰它）。

`execve(path, argv, envp)` 成功不返回；失败返回 -1，errno 关键分支：`ENOENT`（路径或解释器不存在，脚本 shebang 指向不存在的 bash 也报这个）、`EACCES`、`ENOEXEC`（格式不对且没有 shebang）、`E2BIG`（argv+envp 超过 `ARG_MAX`，典型是 exec 时把整个环境塞进去）。`execvp` 走 `PATH`，`execvpe` 需要 `_GNU_SOURCE`。

代价：`fork` 是 `copy_process()` 加逐级复制页表，成本随虚拟地址空间增大而线性增长，而不随 RSS 增长。64 GB 虚拟地址、几十 MB 实际驻留的进程，`fork` 一样慢，因为复制的页表项按 VMA 覆盖的虚拟范围算。真正的内存代价推迟到写时。`vfork`/`posix_spawn` 在 glibc 上就是 `clone(CLONE_VM|CLONE_VFORK)` 加 `exec`，省掉页表复制，但 `vfork` 子进程只能 `exec` 或 `_exit`，做别的就是未定义行为。

**对应命令与读法**：

- `ps -eo pid,ppid,stat,etime,rss,cmd --sort=-rss | head -20` → 看 `STAT` 列：`Z` 是僵尸、`D` 是不可中断睡眠（IO 卡死）、`S` 可中断睡眠、`R` 运行、`s` 会话首进程、`l` 多线程、`+` 前台。`RSS` 对僵尸恒为 0，所以“内存没涨但进程一堆”正是僵尸的特征；`ETIME` 与 `PPID` 一起看，大量 `PPID=1` 的同名进程说明父进程已经先死（孤儿被过继）。会骗你：`%CPU`/`RSS` 都是瞬间快照，容器内 `ps` 看到的是整个 pid namespace，宿主机视角也在里面。
- `top` → 看 `Tasks:` 那一行 `total / running / sleeping / stopped / zombie`。`zombie` 非 0 且持续上涨就是没 `wait`；`running` 数长期大于 CPU 核数说明在排队。会骗你：`top` 里多线程进程的 `%CPU` 默认按 Irix 模式可超过 100%，按 `I` 切 Solaris 模式才是“占整机百分比”，两个口径混用会把 8 核机器的 400% 误读成 4%。
- `pstree -p <pid>` → 看树形结构与 `(pid)` 标注，`{name}` 是线程组内的线程。用来确认 fork 出来的子进程到底挂在哪、有没有被过继给 1。会骗你：进程一旦被 reparent 到 init/subreaper，树就断了，真实血缘只能靠 `ps -o ppid=` 或审计日志回溯。
- `pidof nginx` → 返回所有匹配可执行文件名的主 pid。用来确认“起了几个、是不是 restart 后老进程还在”。会骗你：对 shell/python 脚本，`pidof` 匹配的是解释器的名字（`pidof myscript.sh` 通常什么也不返回），得用 `pidof -x` 或直接看 `ps -o cmd=`。
- `strace -f -e trace=clone,clone3,execve,wait4 -o /tmp/p.log ./prog` → 看每次 `clone(...) = 12345` 与随后的 `execve`，`CLONE_THREAD` 标志说明是建线程而不是建进程；`wait4` 缺失而 `clone` 很多，就是僵尸的根因。新内核上 `fork` 会显示为 `clone3`，只写 `trace=clone` 会漏。会骗你：`-f` 的 ptrace 会显著拖慢目标（clone 密集时几倍），并且改变调度时序，线上慎用，优先 `-c` 只统计。

**原理**：`fork()` 落到 `kernel_clone()`，`copy_process()` 依次复制 `task_struct`、复制或共享 `files_struct`/`fs_struct`/`sighand`、调 `dup_mmap()` 复制 VMA 和页表，然后把父子双方的 PTE 都改成只读并清 `PTE_W`，页框的 `_refcount` 加一——这就是写时复制。所以 `fork` 的开销是“页表项数 + VMA 数”，不是数据量；第一次写触发缺页，`do_wp_page()` 才分配新页框，此时 RSS 才涨（第 5、6 章会接着算这笔账）。

`CLONE_THREAD` 让新 task 与父 task 共享 `signal_struct` 和 `mm`，`getpid()` 返回同一个 tgid，`gettid()` 才是各自的内核 pid——`ps -L`/`top -H` 里那个 LWP 就是它。线程组里任一线程调 `exit_group`（即 `exit()`）会杀掉整组，`_exit()` 才是只退自己。

退出路径：`do_exit()` 把 `task->exit_state` 置 `EXIT_ZOMBIE`，释放 `mm`（RSS 归零）、关闭 fd、把剩余子进程 reparent 给 `init` 或最近的 `PR_SET_CHILD_SUBREAPER` 进程，然后**保留 task_struct 不释放**，等父进程 `wait4()` 里 `release_task()` 回收。这就是僵尸：pid 被占、`task_struct` 被占，但内存几乎不占。所以“僵尸吃内存”是误会，它吃的是 pid 号；而 `pid_max` 默认 32768（可按发行版调整，`/proc/sys/kernel/pid_max` 上限受 `PID_MAX_LIMIT` 约束），涨到头就 `EAGAIN`。

## 第 2 章〔CPU〕CPU 占用与调度：nice、亲和性、实时策略与被抢占

**要解决的问题**：三种误判。其一，`top` 显示某进程 380% CPU，你就加机器；实际是 4 个线程在 1 个核上排队，`taskset` 一查亲和性掩码只有 `0x1`。其二，把批处理 `nice -n 19` 降级后仍抢 CPU，因为对端是 `SCHED_FIFO`。其三，某个 `SCHED_FIFO 99` 的线程死循环把整机卡死、ssh 都进不去——因为 RT 线程不受 CFS 公平性约束，只受 RT throttling 限制。不会这一章，你分不清“CPU 真的不够”和“CPU 被调度策略锁死在一个核上”。

**API 与代价**：

```c
#include <sched.h>
#include <sys/resource.h>
#include <sys/syscall.h>

/* nice：影响 CFS 权重，-20..19，越小越优先 */
setpriority(PRIO_PROCESS, pid, -5);      /* 降 nice 需 CAP_SYS_NICE 或 RLIMIT_NICE */

/* 调度策略：SCHED_OTHER(CFS) / SCHED_BATCH / SCHED_IDLE / SCHED_FIFO / SCHED_RR */
struct sched_param sp = { .sched_priority = 50 };   /* RT 有效范围 1..99 */
sched_setscheduler(pid, SCHED_FIFO, &sp);           /* EPERM：无 CAP_SYS_NICE 且超 RLIMIT_RTPRIO */
sched_yield();                                      /* 只把 CPU 让给同优先级/更高优先级 */

/* 亲和性：位图，最多 CPU_SETSIZE 个 CPU */
cpu_set_t set; CPU_ZERO(&set); CPU_SET(2, &set); CPU_SET(3, &set);
sched_setaffinity(0, sizeof(set), &set);  /* EINVAL：掩码与任何在线 CPU 无交集 */
```

关键语义：`sched_setscheduler` 的 `sched_priority` 对 CFS 必须为 0，传非 0 返回 `EINVAL`；`SCHED_RR` 与 `SCHED_FIFO` 的差别只在同优先级间的轮转时间片（`/proc/sys/kernel/sched_rr_timeslice_ms`），优先级不同时行为一致。`sched_yield()` 在 CFS 下只是把当前 task 放到红黑树最右（vruntime 最小者优先），并不是“让出到下一轮”。`SCHED_DEADLINE` 必须走 `sched_setattr(2)`，`sched_setscheduler` 设不了。

代价：改亲和性会触发负载均衡器重新拉起迁移，一次 `sched_setaffinity` 可能伴随 cache 冷启动；RT 线程一旦就绪会立刻抢占同核上任何 CFS 任务，包括内核线程，所以 RT 用错等于把机器变砖。降 nice 需要特权，普通用户只能升 nice（变“更不优先”），这是权限设计的必然。

**对应命令与读法**：

- `top -H -p <pid>` → 看每个线程（`THREAD`/`TID` 列）的 `%CPU`、`S`（状态）、`P`（最后运行的 CPU，按 `f` 可开 `Last used CPU` 字段）。用来确认“是单线程打满一个核，还是 N 个线程分散在 N 个核”。`S` 是 `R` 但 `%CPU` 低，说明它在排队而非在算。会骗你：默认 3 秒刷新，短命线程（<1s）根本采不到；`P` 列是采样瞬间的 CPU，线程被迁移后显示的是后一个。
- `pidstat -u -t -p <pid> 1 5` → 输出 `UID PID TID %usr %system %guest %wait %CPU CPU Command`。`%usr` 高是用户态忙算，`%system` 高是系统调用/内核态开销（常见于大量小 `read`/`write`），`%wait` 高说明线程在 runqueue 上等 CPU（procps-ng 较新版本才有此列，老版本无该字段）。`CPU` 列显示线程落在哪个核。会骗你：容器里 `CPU` 编号是宿主机编号，和容器内 `nproc` 对不上；`%wait` 在内核不支持 schedstats 时恒为 0。
- `taskset -pc <pid>` → 打印 `pid 1234's current affinity list: 2,3`，加 `-p` 是查询，不带 `-p` 是设置。看到 `0-63` 但实际只有一个核在跑，就去查 cgroup cpuset。会骗你：这是最大的坑——cgroup v1/v2 的 `cpuset.cpus` 限制不在亲和性掩码里体现，掩码显示全集而 cpuset 只给 1 个核，于是“亲和性没问题但就是不并行”。
- `chrt -p <pid>` → 输出 `pid 1234's current scheduling policy: SCHED_OTHER` 与 `current scheduling priority: 0`。设 `chrt -f -p 50 <pid>`（`-f` FIFO、`-r` RR、`-o` OTHER、`-b` BATCH、`-i` IDLE）。用它确认“降了 nice 还抢 CPU”的对端是不是 RT。会骗你：显示 `SCHED_FIFO` 不代表它一直在跑，`sched_rt_runtime_us / sched_rt_period_us` = 950000/1000000 时，RT 组每秒最多用 950ms，剩下 50ms 强制让给 CFS（`/proc/sys/kernel/sched_rt_runtime_us`）。
- `perf stat -e task-clock,context-switches,cpu-migrations,page-faults,cycles,instructions -- ./prog` → `context-switches` 高说明频繁阻塞或被动抢占，`cpu-migrations` 高说明亲和性太宽或负载均衡在搬线程（每次迁移 L1/L2 缓存全冷），`instructions/cycles` 即 IPC，IPC 远低于 1 说明在等内存而非在算。会骗你：需要 `perf_event_paranoid` 足够低（`/proc/sys/kernel/perf_event_paranoid`，多数发行版默认 2 或 4 会拒绝），虚拟机里 `cycles` 常不可用只能退回 `task-clock`。

**原理**：CFS 用红黑树按 `vruntime` 排序，`vruntime` 的增量是

$$\Delta v_i = \Delta t \cdot \frac{1024}{w_i}$$

`w` 由 nice 映射（nice 0 = 1024，每降 1 约 ×1.25），所以两个线程的 CPU 份额比就是权重比，nice 差 5 大约是 3 倍差距。调度周期 `sched_latency`（默认约 6 ms，`/proc/sys/kernel/sched_latency_ns`）在 runqueue 很长时不再拉长，每个 task 的时间片取

$$\text{slice}_i = \max\!\left(g_{\min},\; \frac{w_i}{W} \cdot L\right)$$

`g_min` 即 `sched_min_granularity`（约 0.75 ms）。这意味着 **runqueue 上任务越多，单任务分到的片越小、切换越频繁，`%system` 随之上升**——不是“CPU 不够”，是上下文切换税。nice 只改权重，不改优先级：一个 nice 19 的线程在其它线程都睡眠时照样能占满 100%。

亲和性落到 `task_struct->cpus_mask`，`sched_setaffinity` 只是改掩码并触发一次 `migration` 检查；真正的迁移由负载均衡器在 `scheduler_tick`/`newidle_balance` 里做，代价是目标 CPU 的缓存与 TLB 全冷。

RT 走另一套结构：每个 CPU 的 `rt_rq` 里按优先级 0..99 挂 100 条链表，`SCHED_FIFO` 的同优先级任务按入队顺序一直跑到阻塞或主动让出，`SCHED_RR` 才在片耗尽时挪到队尾。RT 任务的抢占是无条件的（只要 `need_resched` 置位，`preempt_schedule` 立刻切），因此不需要也不能靠 nice 与之竞争。内核用 RT throttling 兜底：每个 period 只给 RT 组 `sched_rt_runtime_us` 的 CPU 时间，超了就 `rt_rq->rt_throttled = 1` 并把它们从可运行集合中摘掉一个 period，这就是“SCHED_FIFO 死循环也没把机器锁死”的原因——但如果有人把 `sched_rt_runtime_us` 设成 -1（关闭 throttle），就真的会锁死。`SCHED_IDLE` 的权重最低，只在 CPU 空闲时才跑，是比 nice 19 更强的“让路”手段。

## 第 3 章〔CPU〕时间与定时：单调时钟、定时器与忙等 vs 阻塞

**要解决的问题**：周期任务漂移、超时控制不准、延迟毛刺查不出源头。典型故障：用 `gettimeofday` 算间隔，NTP 一次阶跃让延时变成负数或几万秒，熔断器失效；用 `sleep(1)` 轮询，实际唤醒 1.05 ms，1000 QPS 下每个连接多 50 µs；事件循环里混入忙等，把一核跑满导致同机其他服务被挤。不会这套，你只能看到「偶发慢」而说不出慢在哪一段。

**API 与代价**

- `clock_gettime(clk, &ts)`：`CLOCK_REALTIME` 会跳变，只能用来打时间戳；测间隔一律用 `CLOCK_MONOTONIC`（被 NTP 缓慢 slew，但不会倒退）；`CLOCK_MONOTONIC_RAW` 连 slew 都不要（拿来做硬件对齐）；`CLOCK_BOOTTIME` 含 suspend 时间。返回值几乎不会失败（只有 `EINVAL`/`EFAULT`），不必写复杂错误分支。
- 代价：`CLOCK_MONOTONIC`/`REALTIME` 走 vDSO，用户态读共享页，约 20–30 ns，**没有系统调用**；`CLOCK_PROCESS_CPUTIME_ID` 之类的 CPU 时钟需要读 per-task 计数，某些内核上会退化成 syscall。
- `clock_nanosleep` 与 `nanosleep`：**注意返回值**——`clock_nanosleep` 直接返回错误码（`EINTR`），不设 `errno`、不返回 -1，写成 `if (ret < 0)` 是错的。`TIMER_ABSTIME` 用绝对时间，天然消除累积漂移；相对睡眠被信号打断时剩余时间放在 `rem`，必须自己重算。
- 定时器和 fd 绑定：`timerfd_create` + `timerfd_settime` + `epoll`，把超时纳入统一事件循环，无信号、无丢失、无重入问题；代价是多一个 fd、每次到期一次 `read` 8 字节。
- 忙等：`while (clock_gettime(...) < deadline)` 精度可达几十 ns，但独占一个核、阻止 CPU 进 C-state、拉高同核邻居的延迟。只在临界区 < 数十 µs 时值得。

```c
struct timespec next;
clock_gettime(CLOCK_MONOTONIC, &next);
for (int i = 0; i < N; i++) {
    next.tv_nsec += 1000000;                 /* 1ms 周期，绝对时间 */
    if (next.tv_nsec >= 1000000000) { next.tv_sec++; next.tv_nsec -= 1000000000; }
    int r;
    do {
        r = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL);
    } while (r == EINTR);                    /* 返回错误码，非 -1/errno */
}
```

**对应命令与读法**

1. `time -p ./prog`（或 `/usr/bin/time -v ./prog`）→ 看 `real/user/sys` → `real` 远大于 `user+sys` 说明进程在阻塞（睡眠、IO、等锁）；`user` 高是算力问题；`sys` 高是系统调用与内存拷贝。**会骗你**：多线程下 `user` 是各线程 CPU 时间之和，`real` 可能远小于 `user`；容器内 `time` 看不到被抢占的等待。

2. `strace -T -f -e trace=clock_nanosleep,nanosleep,futex,epoll_wait,ppoll,poll,select ./prog` → 每个系统调用后的 `<0.001234>` 是从进入到返回的实际耗时 → 直接定位哪一次调用耗掉了时间。**会骗你**：`write` 快速返回只说明进了页缓存，不代表已写入磁盘；`ptrace` 会让程序整体变慢，时序敏感的程序会失真。

3. `sudo cat /proc/timer_list` → 每个 CPU 一块，找 `# expires at ... nsecs [in X to Y nsecs]` 与 `now at ...` → `X` 是距离到期的纳秒数，同一 CPU 上挂满大量即将到期的 hrtimer 说明定时器集中在这一核（线程被绑核、`timer_migration` 关闭）。**会骗你**：需要 root 且容器里常不可见；未编译 `CONFIG_TIMER_LIST` 的内核上该文件不存在（按内核版本而定）；它只列 hrtimer，不反映 timerfd 的每次到期唤醒成本。

4. `perf sched record -a -- sleep 5` 然后 `perf sched latency` → 看 `Runtime / Switches / Average delay / Maximum delay` → `Maximum delay` 就是「被唤醒后隔多久真正上 CPU」，毛刺排查主要看这一列；`Runtime` 接近窗口长度说明任务一直可运行但抢不到 CPU。**会骗你**：需要 `perf_event_paranoid ≤ 1` 和 root；只统计采样窗口内发生过调度的事件，5 秒窗口里的低频长尾可能一条都没有。

5. `cat /proc/PID/timers` → 每行 `ID: clockid it_value it_interval notify` → `it_interval` 为 0 是单次定时器，非 0 是周期；`notify` 显示信号投递方式。**会骗你**：只显示 `timer_create` 创建的 POSIX 定时器，`timerfd` 和 `nanosleep` 都不在这里；读别的进程需要权限，权限不足时输出为空而不报错。

6. `cat /proc/PID/timerslack_ns` → 该值是内核允许把唤醒合并、推迟的松弛量（ns），默认 50000 → 调小可降延迟、代价是唤醒次数与功耗上升。**会骗你**：写它需要 `CAP_SYS_NICE`；对实时策略线程 slack 被忽略，因此改了也看不到效果。

**原理**

内核为每个 CPU 维护一棵按 `expires` 排序的红黑树（hrtimer），并用 clockevent 设备编程「下一次到期中断」——没有到期任务时干脆不产生 tick（NOHZ），这是空闲机器 CPU 接近 0% 的原因。`nanosleep` 的实现是：算 `expires = now + 请求值`，插入红黑树，`schedule()` 让出 CPU；中断到来后 hrtimer 回调 `wake_up_process`，任务入 runqueue，若目标 CPU 在 idle 还要发 IPI 唤醒。

正因如此，`sleep` 的实际时长是 $t_{\text{real}} \approx \Delta + \delta_{\text{slack}} + \delta_{\text{sched}}$：$\Delta$ 是请求值，$\delta_{\text{slack}}$ 是非实时任务默认 50 µs 量级的合并松弛（把 `expires` 向上取整到 slack 边界），$\delta_{\text{sched}}$ 是唤醒到上 CPU 的调度延迟。想压低后两项，靠提优先级/绑核（第 2 章）和调 `timerslack_ns`，而不是把 `sleep` 值改小——后者只会让 $t_{\text{real}}$ 中固定开销占比更大。

vDSO 是这套 API 便宜的根本原因：内核把 `timespec` 和 seqlock 序号放在进程启动时映射的 `[vvar]` 页里，`clock_gettime` 变成「读序号 → 读数据 → 再读序号，不一致就重试」的纯用户态循环。代价是不做跨核同步，不同 CPU 读到的时间戳可能相差一个 tick 量级的更新延迟——对测量间隔没有影响，但不要用它做严格的全序排序。忙等之所以昂贵，是因为它让该 CPU 一直处于 C0 且不断拉高频率，既消耗了本可让给别人的算力，也改变了同封装内其他核的 turbo 预算。

---

## 第 4 章〔内存〕虚拟内存与 mmap：brk / mmap / mprotect 与地址空间布局

**要解决的问题**：进程「内存一直涨」「RSS 降不下来」「`malloc` 返回 ENOMEM 但机器还有大量空闲内存」「大文件处理时 sys 时间高」。这些现象分别指向：地址空间碎片与 VMA 数量、`free` 后未归还物理页、overcommit/`max_map_count` 限制、`read` 与 `mmap` 的拷贝路径差异。不会这套，你只能靠重启。

**API 与代价**

- `brk(void *addr)` / `sbrk(intptr_t inc)`：只移动 heap 顶部那一个 VMA 的边界。**返回值语义反直觉**：`brk` 成功返回新的 break，失败返回**旧** break（不是 -1），所以 glibc 用 `sbrk(0)` 前后比较来判断。
- `mmap(addr, len, prot, flags, fd, off)`：`MAP_PRIVATE|MAP_ANONYMOUS` 是匿名映射；`MAP_SHARED` 写会回文件；`off` 必须页对齐，否则 `EINVAL`；`MAP_FIXED` 会**静默覆盖**已有映射，只有 allocator/JIT 才该用，普通代码用 `MAP_FIXED_NOREPLACE`。
- `mmap` 只建立 VMA，不分配物理页——首次访问才缺页（匿名页映射到全局只读零页，写时 COW 分配）。所以 `mmap` 一个 1 GB 区域几乎是常数开销，但 `MAP_POPULATE` 会立刻把所有页填上，代价是真实的分配与清零。
- `mprotect(addr, len, prot)`：必须页对齐，会**拆分/合并 VMA**，并在多核上触发 TLB shootdown（IPI）。用来做 guard page、JIT 的 W^X、只读保护时，注意一次 `mprotect` 覆盖大范围比多次小范围便宜得多。
- `madvise`：`MADV_DONTNEED` 立即释放物理页并清零（RSS 立刻降，再访问重新缺页）；`MADV_FREE` 只打标记，压力来了才回收（RSS 暂时不降）；`MADV_HUGEPAGE` 让该区域优先用透明大页。

```c
size_t len = 4096 * 16;
char *p = mmap(NULL, len + 4096, PROT_READ | PROT_WRITE,
               MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
if (p == MAP_FAILED) { perror("mmap"); return -1; }
mprotect(p + len, 4096, PROT_NONE);   /* 尾页做 guard，越界立刻 SIGSEGV */
/* ... 使用 p[0..len) ... */
madvise(p, len, MADV_DONTNEED);       /* 立刻还物理页，RSS 下降 */
munmap(p, len + 4096);
```

**对应命令与读法**

1. `pmap -x PID` → 列 `Address Kbytes RSS Dirty Swap Mode Mapping` → `Kbytes` 是该 VMA 的虚拟大小，`RSS` 是当前驻留物理页；末尾 `total` 行给合计。看 `[heap]` 增长判断 brk 扩张，看大量 `[ anon ]` 判断 mmap 分配。**会骗你**：`total` 的 RSS 会把

## 第 5 章 内存占用口径：VSS / RSS / PSS / USS、缺页与共享页

**要解决的问题**：线上说“内存涨了”，九成先要反问是哪一个口径。`ps` 的 RSS 相加经常超过物理内存——共享库、共享内存、被映射的 page cache 在多个进程里被各记一遍；反过来，容器 OOM 报的 `anon-rss` 又比 `top` 看到的小，因为后者混进了 file-backed 页。分不清这四个口径，就会把共享库当泄漏去扩容、把可回收的页缓存当“还不了的内存”去重启服务。

**API 与代价**：口径来自内核计数器，不是 `free` 现算的。

- `VSS` = `mm->total_vm`，VMA 长度之和。分配地址空间就有，**不占物理页**。
- `RSS` = `mm->rss_stat[]`（每 CPU 计数器求和）× `PAGE_SIZE`，只统计**已建立 PTE 且 Present** 的页。
- `PSS` 没有常驻计数器：`smaps` 遍历每个 VMA、对每页按 `mapcount` 平摊现算，代价 $O(\text{映射数})$，读别人的进程要 root。
- `USS` = `Private_Clean + Private_Dirty`，进程独占。

```c
size_t n = 64UL << 20;
void *p = mmap(NULL, n, PROT_READ|PROT_WRITE,
               MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);  /* VSS +=64MiB，RSS 不变 */
memset(p, 1, n);              /* 16384 次 minor fault 后 RSS 才 +=64MiB */
madvise(p, n, MADV_DONTNEED); /* 匿名页直接丢弃：RSS 归零，内容变零 */
munmap(p, n);                 /* 这时才释放 VMA 和页表页 */
```

按页读 `statm`（**单位是页，不是字节**）：

```c
long sz, res, sh;                    /* size resident shared */
FILE *f = fopen("/proc/self/statm", "r");
fscanf(f, "%ld %ld %ld", &sz, &res, &sh);
printf("RSS=%ld KiB\n", res * sysconf(_SC_PAGESIZE) / 1024);
```

常见误用：把 `statm` 的 `shared` 当 PSS——它其实是**文件后备的驻留页**总数，同一份 libc 在 50 个进程里各记一遍；`getrusage().ru_maxrss` 在 Linux 上单位是 **KiB**，且是历史峰值，永不会下降。

**对应命令与读法**：

1. `free -m` → 看 `available` 而不是 `free` → 它是内核估算的“还能给新应用多少”（扣除 low watermark 与不可回收 slab）→ 骗你处：`buff/cache` 含 tmpfs/shmem，这部分**不可回收**，tmpfs 写满时 `available` 才掉，平时容易漏判。
2. `vmstat 1 5` → 跳过第一行（开机以来均值）；看 `si/so`（换页 KB/s）、`free`、`cache`、`wa` → `si/so` 长期非 0 是真缺内存 → 骗你处：`cache` 列不含 SReclaimable slab，也不反映碎片，空闲页够但 order-3 分配失败它看不出来。
3. `cat /proc/PID/statm` → 第 1 列 `size` 是 VSS（页），第 2 列 `resident` 是 RSS（页）→ 差值大说明“申请了没碰” → 骗你处：`resident` 含共享页，多进程相加必然重复计算。
4. `grep -E 'R

## 第 7 章 文件 IO 与 fd 语义：open 标志、偏移、原子性与 EINTR

**要解决的问题**

线上四类经典故障：服务运行几天后 `accept` 报 `Too many open files`（fd 泄漏）；多个 worker 往同一个日志 `lseek`+`write` 互相覆盖（偏移不共享却以为共享，或反过来）；`read` 拿到短读被当成 EOF，配置文件只解析了一半；加了信号处理后 `accept`/`read` 突然返回 -1，连接被丢掉。这些都不是"文件系统坏了"，而是 fd 到底是什么、偏移归谁、哪些操作原子、被打断之后内核还认不认这次调用。

**API 与代价**

```c
int open(const char *path, int flags, ...);
ssize_t read(int fd, void *buf, size_t n);
ssize_t write(int fd, const void *buf, size_t n);
int dup(int oldfd);  int dup2(int oldfd, int newfd);
off_t lseek(int fd, off_t off, int whence);
```

`open` 返回进程内最小可用 fd，失败 -1：`ENOENT`/`EACCES` 是路径与权限，`EMFILE` 是本进程 fd 表满（`RLIMIT_NOFILE`），`ENFILE` 是系统级 `file-max` 满——面试高频区分点。`read`/`write` 返回 0 才是 EOF，单次上限 `0x7ffff000` 字节（约 2 GB），管道、socket、终端随时短读短写，**必须循环**。

```c
static int write_all(int fd, const char *buf, size_t n) {
    size_t off = 0;
    while (off < n) {
        ssize_t w = write(fd, buf + off, n - off);
        if (w < 0) {
            if (errno == EINTR) continue;                 /* 信号打断，重试 */
            if (errno == EAGAIN) { poll_wait(fd); continue; }
            return -1;
        }
        off += (size_t)w;                                 /* 短写，继续 */
    }
    return 0;
}
```

关键语义：

- `O_APPEND`：定位与写入在内核 `i_rwsem` 下一起完成，多进程追加日志只有它是安全的；单次 `write` 之间仍可被插入，所以"每条日志一行"要一次写完。
- `O_CREAT|O_EXCL`：创建判定原子，`access()`+`open()` 是 TOCTOU 漏洞。
- `dup`/`fork` 共享同一个 open file description，**共享偏移与 O_APPEND 标志**；两次 `open` 得到两个独立偏移。
- `O_CLOEXEC` 要用 `open` 的标志位，不要 `fcntl(F_SETFD)`——后者在多线程下有竞态窗口，fd 已经漏进 `exec`。
- `close` 在 Linux 上失败也不要重试：fd 已释放，重试可能关掉别人刚拿到的同号 fd。

**对应命令与读法**

1. `lsof -p $PID | head -50` → `FD` 列的数字 fd、`TYPE`、`NAME` → 同一 `NAME` 上挂了几百个数字 fd，就是泄漏点；`NAME` 带 `(deleted)` 说明文件已删但 fd 未关，磁盘空间不释放 → 骗你：非 root 看不到别的用户进程；lsof 自己做路径解析也会占 fd；`OFFSET` 列（`0t123`）是读取瞬间的快照，共享偏移的多个 fd 会显示得不一致。

2. `ls -l /proc/$PID/fd | awk '{print $NF}' | sort | uniq -c | sort -rn | head` → 每个路径的 fd 计数 → 谁在被反复打开不关 → 骗你：无权限时符号链接读成空；`socket:[12345]`、`anon_inode:[eventfd]` 这类名字对定位帮助有限，要配合 `ss -p` 看。

3. `cat /proc/$PID/limits | grep 'open files'` 与 `ulimit -n` → soft/hard 两列 → soft 就是 `EMFILE` 的阈值，hard 限制能否 `setrlimit` 抬升 → 骗你：`ulimit` 显示的是你当前 shell 的值，守护进程可能被 systemd 单元或容器运行时改成别的值，必须读 `/proc/$PID/limits`。

4. `strace -f -e trace=openat,open,close -p $PID` → 返回值即 fd 号，`= -1 EMFILE` / `ENOENT` 直接给出 errno → 判断是泄漏还是路径错 → 骗你：ptrace 让目标慢数倍，可能把偶发超时放大成雪崩；不加 `-f` 跟不到线程；部分容器默认禁 ptrace。

5. `cat /proc/$PID/fdinfo/3` → `pos:`（当前偏移）与 `flags:`（八进制）→ `pos` 相同说明是两个 fd 共享同一 description；`flags` 里 `02000` 是 `O_APPEND`、`04000` 是 `O_NONBLOCK` → 骗你：这只是快照，且不同内核版本 `flags` 位展示不全。

**原理**

fd 只是 `files_struct->fdtable` 数组的下标，三级结构：`fdtable` → `struct file`（open file description，含 `f_pos`、`f_flags`、`f_count`、`f_op`、`f_path`）→ `dentry` → `inode`。所以"文件"有两层身份：`struct file` 决定偏移与状态标志，`inode` 决定数据。`fork` 复制 `files_struct`（线程用 `CLONE_FILES` 直接共享整表），每个 `struct file` 的 `f_count` 加一——这是父子进程交替写同一文件会互相覆盖的根因；要各写各的必须重新 `open`。

`open` 的路径解析走 dcache，未命中才逐级读目录 inode，代价高；`O_CREAT` 还要拿父目录 `i_rwsem` 写锁，高并发创建同目录文件会在这里排队。`write` 到普通文件默认只写进页缓存就返回（脏页由 writeback 线程回写，见第 10 章），`O_SYNC`/`O_DSYNC` 则每次等落盘，代价从微秒级跳到毫秒级。

EINTR 的路径：信号递送唤醒可中断睡眠，慢系统调用内部返回 `-ERESTARTSYS`，内核在返回用户态前检查该信号的处理函数是否带 `SA_RESTART`，带则重启，不带则给用户返回 `-1/EINTR`。注意 `select`/`poll`/`epoll_wait` 即使在 `SA_RESTART` 下也不重启，`nanosleep` 返回 EINTR 并给出剩余时间——自己写循环是唯一稳的做法。普通文件读写几乎不会 EINTR（不睡眠），所以这个坑往往在 socket、FIFO、终端上才炸。

## 第 8 章 标准 IO 与缓冲：stdio 缓冲三态、行缓冲与全缓冲的坑

**要解决的问题**

`printf` 的日志在终端里实时滚动，一重定向到文件就"卡住不输出"；进程被 `kill -9` 后日志末尾少一截；`fork` 之后每行日志打印两遍；容器里日志被切成 8 KB 一块的怪块。反过来，日志量一上来，`perf top` 里一半 CPU 在 `write` 系统调用上——都是 stdio 三态缓冲的锅。

**API 与代价**

```c
FILE *fopen(const char *path, const char *mode);
int setvbuf(FILE *stream, char *buf, int mode, size_t size);  /* 0 / EOF */
int fflush(FILE *stream);      /* 用户态缓冲 → 内核页缓存，不是落盘 */
size_t fwrite(const void *p, size_t sz, size_t n, FILE *fp); /* 返回项数 */
int fileno(FILE *stream);
```

三种模式：`_IOFBF` 全缓冲、`_IOLBF` 行缓冲、`_IONBF` 无缓冲。glibc 的默认判定是：`stderr` 恒无缓冲；`stdin`/`stdout` 若 `isatty()` 为真则行缓冲，否则全缓冲（通常是 `st_blksize` 或 `BUFSIZ`=8192）。`setvbuf` **必须在该流任何 IO 之前**调用，否则行为未定义。

```c
int main(void) {
    setvbuf(stdout, NULL, _IOLBF, 0);   /* 必须在第一次 printf 前 */
    printf("start\n");                  /* 遇 \n 触发一次 write(1, "start\n", 6) */
    fprintf(stderr, "err\n");           /* 默认无缓冲，立刻可见 */
    fflush(stdout);                     /* fork 前必须刷，否则缓冲区被复制一份 */
    if (fork() == 0) { printf("child\n"); _exit(0); }  /* _exit 不 flush */
    return 0;                           /* exit / main return 会 flush 全部流 */
}
```

三个高频误用：`fwrite` 返回值是**项数**不是字节数，判断短写要乘 `sz`；`fflush` 只把数据交给内核，断电照样丢，落盘要 `fsync(fileno(fp))`；`abort()`、`_exit()`、`SIGKILL` 都不会 flush。

**对应命令与读法**

1. `stdbuf -oL ./app > out.log 2>&1`（或 `-o0` 无缓冲、`-eL` 改 stderr）→ 输出是否变成实时 → 说明原程序在被重定向时是全缓冲 → 骗你：`stdbuf` 靠 `LD_PRELOAD` 改 libc 内部变量，静态链接、musl、或程序自己调过 `setvbuf` 都会失效；对已经在跑的进程完全无能为力。

2. `strace -f -e trace=write -c -p $PID` → `calls` 列与 `total` 列、用 `total/calls` 估算单次字节数 → 一分钟几十万次 write、每次几十字节，就是行缓冲或无缓冲在放大系统调用；次数很少、单次 8 KB 的是全缓冲 → 骗你：`-c` 是汇总，看不到写的内容；ptrace 让 `total` 时间虚高，只能看比例不能看绝对值。

3. `strace -f -e trace=write -s 64 -p $PID` → 单次 `write(1, "....\n", 12)` 的字符串与长度 → 一眼看出是行缓冲还是整块 → 骗你：`-s` 会截断长串（默认 32）；不加 `-f` 看不到子线程的 write。

4. `ls -l /proc/$PID/fd/1; cat /proc/$PID/fdinfo/1` → `flags:` 有没有 `O_APPEND`（`02000`）、`pos:` 多大 → `pos` 就是已 flush 到文件的字节数，远小于你以为的输出量，说明还压在用户态缓冲里 → 骗你：`pos` 反映的是内核偏移，不是 `printf` 的累计量。

5. `script -q -c ./app /dev/null` → 给程序套一个伪终端，对比输出行为 → 终端下行缓冲、管道下全缓冲的差异当场复现 → 骗你：pty 会改变程序对 `isatty` 的判断，也可能带出颜色码等副作用。

6. `wc -c out.log` → 字节数 → 与期望输出长度对比，判断尾部是否丢在缓冲里 → 骗你：`kill -9` 之后没 flush 的部分本来就不在文件里，`wc` 只能看到已落盘的部分，会把"丢数据"误判成"程序没输出"。

**原理**

`FILE` 结构体内持有 `_IO_read_ptr/_IO_write_ptr` 指向用户态缓冲，`fwrite` 在全缓冲下只是 `memcpy` 到这块内存，写满（或行缓冲遇到 `\n`）才真正调 `write`。这把 $N$ 次系统调用压到 $N/\text{size}$ 次，代价是**延迟**和一个**丢失窗口**：数据在用户态时进程崩了就是没了。`stderr` 无缓冲是刻意的设计取舍——错误信息宁可变慢也不能丢。

`fork` 的坑来自缓冲是进程堆内存：子进程拿到一份副本，父子各自在 `exit` 时 flush，同一段内容被写两遍。解法只有 `fork` 前 `fflush`，或子进程用 `_exit`。

再往下就是第 10 章：`write` 到普通文件只是拷贝进页缓存并标脏，返回即成功；`fflush` 到这一步为止，`fsync` 才走 `<file>->f_op->fsync` 把脏页和元数据真正推给块设备。所以"日志写了但机器掉电后没有"从来不是 stdio 的问题，是没 `fsync`。另外 stdio 的锁是 `FILE` 内部的，`flockfile` 可保多线程下一次 `fprintf` 的原子性；但**多进程共享同一个 `FILE` 毫无意义**，跨进程追加只能靠 `O_APPEND` 的单次 `write`。

## 第 9 章〔文件〕元数据与目录：inode、硬链接与软链接、stat 的三个时间

**要解决的问题**：四类真实故障都源于元数据没搞清。①`df -h` 还有 40% 空间，创建文件却报 `No space left on device`——inode 被小文件耗尽；②`df` 用 90%、`du -sh` 加起来只有 30%——被删除但仍被进程打开的文件没释放；③改完配置重启服务仍读旧值——编辑器用 `rename` 换了 inode，旧进程还持有旧 inode 的 fd；④增量备份、`find -mtime` 漏文件——把 `ctime` 当创建时间、或把 `mtime` 当成“最后一次访问”。不会这一层，线上就只能靠重启和猜。

**API 与代价**：

```c
#include <sys/stat.h>
struct stat st;
if (stat("/etc/app.conf", &st) == -1)   /* 跟随符号链接；lstat 不跟随 */
    perror("stat");                     /* ENOENT ENOTDIR ELOOP EACCES ENAMETOOLONG */
st.st_dev; st.st_ino;   /* 唯一标识：跨文件系统 ino 会重复，必须带 dev */
st.st_nlink;            /* 硬链接数，普通目录至少 2 */
st.st_size;             /* 逻辑大小 */
st.st_blocks;           /* 512B 为单位的实占块数，稀疏文件 << size/512 */
st.st_atim; st.st_mtim; st.st_ctim;     /* 访问 / 修改 / inode 变更 */

/* 创建时间要 statx，且底层支持 */
struct statx sx;
statx(AT_FDCWD, "/etc/app.conf", 0, STATX_BTIME, &sx);
```

- `stat` 一次系统调用，内核走逐级路径解析：每级目录先查 dentry 缓存，未命中就目录读 I/O。代价与路径深度成正比；热路径用 `openat(dirfd, name)` 缓存目录 fd、必要时 `fstatat(dirfd, name, &st, AT_SYMLINK_NOFOLLOW)`，避免重复解析。
- `link()`/`linkat()` 只是新增一个目录项、`i_nlink++`，不复制数据；跨文件系统返回 `EXDEV`。`unlink()` 只是 `i_nlink--`，inode 要等 `nlink == 0 && i_count == 0` 才回收。
- `symlink()` 创建 `S_IFLNK` 类型的新 inode；目标串短于 60 字节时直接内联在 `i_block[]`（fast symlink），不占数据块。`readlink()` 不保证 `\0` 结尾。
- 常见误用：拿 `st_ctime` 当创建时间；`stat` 一个软链接拿到目标信息导致 `nlink` 判断错；以为 `unlink` 立即释放空间；`rename` 之后不 `fsync` 父目录 fd，掉电后目录项可能回退。

**对应命令与读法**：

1. `stat /var/log/app.log` → 看 `Inode`、`Links`、`Access`/`Modify`/`Change`/`Birth` → `Links` 大于 1 说明有硬链接；`Change` 是 inode 变更时间（chmod/chown/link 都会改），**不是创建时间**；`Birth` 为 `-` 表示该文件系统或 inode 不支持 btime（如 ext4 用了 128B inode）→ 会骗你：`Access` 在 `relatime` 下长时间不更新，别用它证明“文件没被读过”。
2. `df -i /var` → 看 `IUsed`、`IFree`、`IUse%` → `IUse%` 到 100% 时任何创建都报 `ENOSPC`，而 `df -h` 可能还很空 → 会骗你：XFS 动态分配 inode，`IUse%` 高但一般打不满；ext4 的 inode 总数在 `mkfs` 时就固定了。
3. `du -sh /var/*` → 按 `st_blocks`（512B）累加，不是 `st_size` → 远小于 `df` 用量时，怀疑 deleted-but-open 与稀疏文件 → 会骗你：同一次遍历里硬链接只算一次（这是对的），但被删文件完全不出现；目录自身也占块；跨挂载点会算进别的文件系统。
4. `ls -li /var/log` → 第一列是 inode 号 → 两个路径 inode 相同即同一文件（硬链接）；不相同的软链接会显示 `->` → 会骗你：`ino` 只在同一 `st_dev` 内唯一，容器/多挂载点下必须配合 `stat` 的 `Device` 一起看。
5. `find /var -xdev -inum 1234567` → 定位某 inode 的所有路径 → 核对“这是不是残留硬链接 / 到底谁占着这个 inode” → 会骗你：不加 `-xdev` 会跨进别的文件系统（慢且混入无关结果）；对已删除但仍打开的文件它找不到，得用 `lsof +L1`。

**原理**：inode 是磁盘上固定大小的记录（ext4 默认 256B，`mkfs` 时按 `bytes-per-inode≈16384` 预分配整张表），存属主、模式、大小、三个时间、块映射与 `i_links_count`；文件名不在 inode 里。目录本身是一个“名字 → inode 号”的映射文件，`ls -li` 的第一列就是映射结果，所以硬链接在语义上就是“同一 inode 的第二个目录项”，与复制数据无关。

路径解析靠内存中的 dentry 缓存（`struct dentry` 持有 `d_inode`）：命中 dcache 时完全不碰磁盘，这是“反复 `stat` 同一路径很便宜、冷路径每层都要读目录块”的原因。ext4 大目录用 htree 索引，但首次查找仍可能触发多次读。

三个时间由写路径维护：`file_update_time()` 更新 `mtime`/`ctime` 并置 `I_DIRTY_SYNC`，随 journal 事务提交落盘。`atime` 由挂载选项决定：`strictatime` 每次读都写 inode，`relatime`（默认）只在

$$\text{atime} < \text{mtime} \;\lor\; \text{now} - \text{atime} > 24\text{h}$$

时更新，`noatime` 永不更新——这就是把只读负载从“写 inode”里救出来的机制。

删除路径：`unlink` → `vfs_unlink` → 摘目录项 → `drop_nlink` → `iput()`；只要还有打开的文件描述符（`i_count > 0`），inode 与数据块都留在内存和磁盘上，只有最后一个 `close` 才真正释放。这正是 `df` 与 `du` 对不上的根因。

---

## 第 10 章〔文件〕IO 栈与页缓存：buffered vs direct IO、fsync 与写放大

**要解决的问题**：`write()` 返回成功不等于数据在盘上——进程被杀没事，机器掉电就丢；数据库每条 `fsync` 让 p99 从 2ms 抖到 200ms；应用只写了 10MB/s，`iostat` 显示磁盘 300MB/s；`iostat` 的 `%util` 100% 但 `iotop` 里一个在写的进程都没有。这一章解决的就是“写下去的东西去哪了、什么时候真到盘、代价谁付”。

**API 与代价**：

```c
ssize_t n = write(fd, buf, len);        /* 只拷进 page cache，不分配块、不发起 I/O */
if (n < 0 && errno == EINTR) /* 重试 */;
fsync(fd);      /* 数据 + 元数据（size/mtime/块映射）都持久化 */
fdatasync(fd);  /* 只保证数据可取回，可省无关元数据 */
sync_file_range(fd, off, len, SYNC_FILE_RANGE_WRITE); /* 仅触发回写，不保证落盘 */
posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED);         /* 丢弃干净页，避免缓存污染 */
fallocate(fd, 0, 0, len);                             /* 预分配，把块分配移出写路径 */
int fd2 = open(p, O_RDWR|O_CREAT|O_DIRECT, 0644);     /* 绕过页缓存 */
```

- `write` 返回的是“已拷入页缓存的字节数”，短写和 `EINTR` 都必须循环重试。
- `fsync` 的代价是一组真实 I/O 加一次缓存屏障：机械盘 ms 级，SSD 几十 µs~ms；逐条 `fsync` 与批量 `fsync` 差一个数量级。
- `O_DIRECT` 有对齐约束：偏移、长度、缓冲区地址按逻辑块（常见 512/4096）对齐，否则 `EINVAL`，缓冲区用 `posix_memalign` 分配。它仍不保证元数据落盘，要持久化还得 `fsync`。
- `O_SYNC`/`O_DSYNC` 等价于每次 `write` 自带 `fsync`，是最贵的选项。
- 常见误用：把 `write` 成功当持久化；拿 `sync_file_range` 替代 `fsync`；`rename`/`unlink` 后忘了 `fsync` 父目录 fd；用小缓冲逐条 `write` 再逐条 `fsync`。

**对应命令与读法**：

1. `iostat -x 1 5` → 看 `w/s`、`wkB/s`、`await`/`w_await`、`aqu-sz`（旧版叫 `avgqu-sz`）、`%util`、`wareq-sz` → `w_await` 高说明排队在设备侧；`wareq-sz` 远大于 4KB 说明合并良好，接近 4KB 且有大量小写说明随机写；`%util` 贴 100% 且 `await` 同步上升就是饱和 → 会骗你：NVMe/RAID 能并行处理，`%util` 100% 不代表打满；`await` 含排队时间，不能当单次 I/O 服务时间。
2. `iotop -o -b -n 2 -d 5`（需 root，依赖内核 `CONFIG_TASK_IO_ACCOUNTING`/`TASK_DELAY_ACCT`）→ 看 `DISK WRITE` 与 `IO>` 两列 → `IO>` 高说明进程在等 I/O 而不是在算 → 会骗你：异步回写由 `kworker`/`flush-*` 完成，脏页的“账”算在 `kworker` 头上，你看到的是回写者不是元凶；容器里经常只看到宿主进程。
3. `grep -E '^(Cached|Dirty|Writeback|Buffers|MemFree)' /proc/meminfo` → `Dirty` 是尚未回写的脏页，`Writeback` 是正在回写的页 → `Dirty` 持续接近 `dirty_ratio` 说明写入速率超过设备能力，`write()` 已经在被限流 → 会骗你：`Cached` 含 tmpfs/shmem（`Shmem` 行），不代表全是可回收的文件页；瞬时值波动大，要连续采样。
4. `perf trace -p <pid> -e write,fsync,fdatasync -s`（需 root 或放宽 `perf_event_paranoid`）→ 看各系统调用次数、总耗时、平均耗时 → 直接量化“`fsync` 吃掉了多少时间”：次数多但平均很短是正常的 WAL 批量；单次 `fsync` 上百 ms 就是设备屏障或队列问题 → 会骗你：只覆盖系统调用时间，不含回写线程后续的真实 I/O；高频率下有可观测开销。
5. `cat /proc/<pid>/io` → `wchar` 是 `write` 累计字节，`write_bytes` 是“导致发往存储层的字节”，`cancelled_write_bytes` 是被丢弃的脏页 → 两者接近且都很大，说明是 `O_DIRECT`/`O_SYNC` 或回写已跟不上的 buffered 写；`write_bytes` 远小于 `wchar` 说明数据还躺在页缓存里 → 会骗你：

## 第 11 章〔网络〕socket 与 TCP 生命周期：从 listen 到 close 的每个状态

**要解决的问题**：服务端“连不上”“握手慢”“句柄只涨不降”“重启后大量 TIME_WAIT 打满端口”，本质都是对 TCP 状态机和两个队列没有可见性。不会这些，排障只能靠重启；而重启会把 CLOSE_WAIT 泄漏、accept 队列溢出这类真问题一起掩盖掉。

**API 与代价**

```c
int s = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
int one = 1;
setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
bind(s, (struct sockaddr *)&addr, sizeof addr);
listen(s, 128);                      /* backlog，内核截到 net.core.somaxconn */
for (;;) {
    int c = accept4(s, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (c < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) break;  /* 队列已空 */
        if (errno == ECONNABORTED || errno == EINTR) continue; /* 可重试 */
        if (errno == EMFILE || errno == ENFILE) { /* fd 耗尽，需预留 fd 或降级 */ }
    }
}
```

- `listen(fd, backlog)`：backlog 不是“最大连接数”，只约束**已完成三次握手的 accept 队列**长度，且被 `somaxconn` 截断。半连接队列由 `tcp_max_syn_backlog` 与 `tcp_syncookies` 管。
- `accept` 返回的新 fd **不继承**监听 fd 的 `O_NONBLOCK`（Linux 行为，POSIX 未规定）；用 `accept4` 一次性带上标志，省一次 `fcntl` 和竞态窗口。
- `close()` 只是减引用计数并推动状态机；有 `SO_LINGER{l_onoff=1,l_linger=0}` 时直接发 RST，**丢弃发送缓冲**，对端看到 `ECONNRESET` —— 这是“优雅关闭”最常见的误用。
- `shutdown(fd, SHUT_WR)` 发 FIN 但保留读方向，半关闭场景必须用它，不能用 `close`。

**对应命令与读法**

1. `ss -tanp` → 看 `State` 列、`Recv-Q/Send-Q`、`users:(("nginx",pid=...,fd=...))`。`ESTAB` 且 `Recv-Q` 持续 >0 说明应用没在读；`Send-Q` 大说明对端窗口小或本端发送积压。**会骗你**：进程退出后 socket 进入 orphan，`users` 为空但连接还在；在容器里 `pid` 是宿主命名空间的值。
2. `ss -lnt` → LISTEN 行的 `Recv-Q` 是当前 accept 队列里已完成握手的连接数，`Send-Q` 是 backlog 上限。`Recv-Q` 贴着 `Send-Q` = 应用 accept 太慢或卡死。**会骗你**：syncookies 生效时半连接根本不入队，`Recv-Q` 很干净，客户端照样超时。
3. `awk 'NR>1{print $4}' /proc/net/tcp | sort | uniq -c` → 第 4 列是十六进制状态：`01`=ESTABLISHED、`06`=TIME_WAIT、`08`=CLOSE_WAIT、`0A`=LISTEN、`03`=SYN_RECV。`CLOSE_WAIT` 单调上涨 = 应用收到 FIN 却从不 `close`。**会骗你**：只覆盖 IPv4，IPv6 在 `/proc/net/tcp6`；地址端口是 hex，需自己转。
4. `netstat -s | grep -Ei 'listen|retransmit|reset'` → `times the listen queue of a socket overflowed`、`SYNs to LISTEN sockets dropped` 增长 = accept 队列溢出；`segments retransmitted` 占比高 = 链路丢包或对端不回 ACK。**会骗你**：全是累计计数器，重启清零，必须隔 10s 取两次差值；net-tools 未安装时用 `nstat -az TcpExtListenOverflows TcpRetransSegs`。
5. `ss -tan state time-wait '( sport = :80 )' | wc -l` → 服务端本地端口 80 上的 TIME_WAIT 数。TIME_WAIT 只出现在**主动关闭方**，服务端堆积说明是服务端先 `close`。**会骗你**：短连接压测天然制造 TIME_WAIT，数量大本身不是故障，看的是端口是否耗尽（`ss -s` 的 `timewait` 与本地端口范围对比）。

**原理**

三次握手时，内核先为 SYN 建 `request_sock` 挂到监听 socket 的半连接队列；握手完成后创建完整 `struct tcp_sock`，挂进 `icsk_accept_queue`，并唤醒 `accept()` 的等待队列。`accept` 的代价因此只是“从队列摘一个 sock + 分配 `struct file`/fd”，比 `connect` 便宜得多。队列满时：半连接队列溢出丢 SYN（客户端重传，表现为 1s/3s 起的握手延迟），accept 队列溢出则默认丢掉 ACK，靠客户端重传来补救。

`close` 之后进入 `FIN_WAIT_1`，收到对端 FIN 且自己 FIN 被 ACK 后进入 `TIME_WAIT`，持续 $2 \times \text{MSL} = 60\text{s}$，目的是让旧连接的重复报文在网络中消亡，避免污染复用同一四元组的新连接。所以端口耗尽的本质是**四元组**耗尽，而不是 fd 耗尽。

数据路径上，`write` 把用户数据拷进 `sk_write_queue` 的 skb，再经拥塞窗口与 Nagle 决定何时交给网卡；接收侧软中断把 skb 挂到 `sk_receive_queue`，`read` 再拷一次到用户态——每个方向都是一次拷贝，零拷贝（`sendfile`/`MSG_ZEROCOPY`）绕过的正是第二次。`CLOSE_WAIT` 堆积的真正原因是 socket inode 与 `struct file` 的引用计数没释放，fd 表和内存一起涨，最终撞上 `EMFILE` 而 `accept` 失败——此时内核仍会完成握手，形成“连接看起来建立了但没人处理”的假象。

## 第 12 章〔网络〕IO 多路复用：select / poll / epoll 的差别与边缘触发

**要解决的问题**：单线程要扛上万连接，或者已经上了 epoll 却在压测里“偶发不收数据”“CPU 空转在 sys 态”。前者是模型选错，后者几乎都是 ET 没读到 `EAGAIN`、或者 LT 下事件没处理干净导致的反复唤醒。

**API 与代价**

```c
int ep = epoll_create1(EPOLL_CLOEXEC);
struct epoll_event ev = { .events = EPOLLIN | EPOLLET, .data.fd = cfd };
epoll_ctl(ep, EPOLL_CTL_ADD, cfd, &ev);        /* 一次注册，O(log n) 插红黑树 */
struct epoll_event evs[64];
int n = epoll_wait(ep, evs, 64, -1);           /* 只拷就绪项 */
for (int i = 0; i < n; i++) {
    for (;;) {                                  /* ET 必须读到 EAGAIN */
        ssize_t r = read(evs[i].data.fd, buf, sizeof buf);
        if (r > 0) continue;
        if (r == 0) { close(evs[i].data.fd); break; }
        if (errno == EAGAIN || errno == EWOULDBLOCK) break;
        if (errno == EINTR) continue;
        close(evs[i].data.fd); break;
    }
}
```

- `select`：`fd_set` 是编译期 `FD_SETSIZE`（通常 1024）位图，每次调用把三张位图**拷进内核**并线性扫描全部位；返回后 `fd_set` 被就地修改，下轮必须重新 `FD_SET`；`timeout` 在 Linux 上也会被改写，循环里要重置。
- `poll`：`struct pollfd` 数组，突破 1024，但仍每次全量拷贝 + 线性扫描，连接数 $n$ 时单次调用代价 $O(n)$。
- `epoll`：`epoll_ctl` 付一次注册成本，`epoll_wait` 的代价是 $O(\text{就绪数})$，与总连接数无关。但**不是零拷贝神话**：就绪数组仍要 `copy_to_user`，只是拷的是就绪项而非全集。
- 触发模式：默认 LT（电平），只要缓冲区还有数据就反复上报；`EPOLLET` 只在**状态变化**时上报一次。用 ET 必须把 fd 设成 `O_NONBLOCK`，否则最后一次 `read` 会阻塞住整个事件循环。
- `EPOLLONESHOT` 让一次事件后自动失活，多线程处理同一连接时必须用，否则两个线程同时读同一条连接。`EPOLLEXCLUSIVE`（4.5+）用于多个进程监听同一端口时避免惊群。

**对应命令与读法**

1. `ss -s` → `Total`、`TCP: estab ... orphaned ... timewait`。连接数与预期严重不符（远大于 worker 数 × 预期）说明 fd/socket 泄漏。**会骗你**：只统计当前 netns，容器里必须 `nsenter -t <pid> -n ss -s`；`closed` 包含尚未回收的短连接。
2. `ls -l /proc/PID/fd | grep -c 'eventpoll'` → 每 `epoll_create` 一次就多一个 `anon_inode:[eventpoll]`。数量随请求增长 = 每次请求新建 epoll 却没 `close`。**会骗你**：`ls -l` 输出里 fd 号会复用，看到的名字是当前指向；权限不足时读不到别人的 `/proc`。
3. `cat /proc/PID/fdinfo/<epfd>` → 每行 `tfd: 7 events: 1d data: ...` 是一个被监听的 fd，`events` 是十六进制掩码（`1`=EPOLLIN，`4`=EPOLLOUT，`80000000`=EPOLLET）。`tfd` 行数远超 `ss` 里的活跃连接数 = 忘了 `EPOLL_CTL_DEL` 或 fd 已关但没摘。**会骗你**：这里不显示就绪状态，掩码要手工换算。
4. `strace -e trace=epoll_wait,epoll_ctl -p PID` → 看 `epoll_wait` 的返回值和 `timeout` 参数。返回值长期为 0 且 `timeout=0` = 忙轮询；返回 nfds>0 但很快又全量返回 = LT 下没把数据读干净。**会骗你**：`strace` 让目标慢一个数量级以上，可能把偶发问题放大成必现；`-p` 需要 ptrace 权限（`kernel.yama.ptrace_scope`）。
5. `ss -tan state established | wc -l` 与上面 `fdinfo` 的 `tfd` 数对比 → 两者应大致相等。注册数远大于实际连接数，就是事件表泄漏；反过来少很多，说明有连接没被注册（新 accept 后漏了 `epoll_ctl`）。**会骗你**：`ss` 有采样间隙，且包含 TIME_WAIT 以外的所有状态，需固定 `state established`。

**原理**

`struct eventpoll` 里三样东西：红黑树 `rbr` 存所有注册的 `epitem`、就绪链表 `rdllist`、等待队列 `wq`。`epoll_ctl(ADD)` 时，内核在该 fd 对应 `struct file` 的 `poll` 回调链上挂一个 `ep_poll_callback`；数据到达时，协议栈调用 `sk_data_ready` → `wake_up` → 回调把 `epitem` 链进 `rdllist` 并唤醒 `epoll_wait` 的等待者。所以 `epoll_wait` 的成本只跟就绪项数量相关，而不是连接总数——这是它相对 `select`/`poll` 的本质差别。

LT 与 ET 的差别发生在 `ep_send_events`：LT 在把事件交给用户态后，会重新调用该文件的 `poll` 检查是否仍有数据，有就重新挂回 `rdllist`；ET 只交付一次，之后必须等下一次**状态跃变**（空→非空）才会再触发。这就是 ET 丢事件的根因：socket 的 `sk_data_ready` 回调只在接收队列由空变非空时触发，如果应用没读到 `EAGAIN` 就返回，队列始终非空，后续数据到来不会再产生新回调。

`select` 的 1024 上限来自 `fd_set` 的位图大小，是编译期常量，改 `FD_SETSIZE` 需要重新编译所有相关代码，且内核侧同样按位扫描；`poll` 去掉了上限但没去掉 $O(n)$ 的拷贝和扫描。连接数上千后，`select`/`poll` 的成本主要在两次用户/内核态的全量拷贝和线性遍历，而 `epoll` 把这份成本前移到了 `epoll_ctl`。代价是状态挂在 fd 上：`fork` 后子进程继承同一个 epoll fd 并共享事件，父子同时 `epoll_wait` 会各自拿到一部分事件，这是许多“明明注册了却不处理”的隐蔽来源。

## 第 13 章〔网络〕链路与丢包诊断：重传、队列、MTU 与拥塞

**要解决的问题**：P99 抖动到几百毫秒甚至几秒，CPU 不高、磁盘不忙，监控上“一切正常”；或者大包不通、小包 `ping` 能过（MTU 黑洞）；或者 `ip -s link` 的 dropped 一直在涨。不掌握这套方法，就只能把“网络慢”归因于玄学，改异步、加机器都没用。

**API 与代价**：

- `send()` 返回小于 `len`、或非阻塞下 `errno == EAGAIN`：发送队列满，根因在下游（对端窗口、拥塞窗口、链路），不在本进程。阻塞 socket 配 `SO_SNDTIMEO` 时返回 `EAGAIN` 表示超时。
- `EMSGSIZE`：UDP 数据报超过路径 MTU，且 `IP_MTU_DISCOVER` 为 `IP_PMTUDISC_DO` 时协议栈拒绝替你分片；TCP 不会遇到，MSS 已经替它协商好。
- `setsockopt(TCP_NODELAY)`：关掉 Nagle。代价是小包数量上升，与 `TCP_CORK`/`MSG_MORE` 正好相反。它治不了“窗口小”和“重传”造成的延迟，很多团队把它当成优化手段来加，纯属心理安慰。
- `SO_SNDBUF`/`SO_RCVBUF`：内核记账值约为设置值的 2 倍（含 `sk_buff` 开销），设大只换来缓冲膨胀和更大内存水位，吞吐是否上升取决于 BDP，不是取决于缓冲。

```c
int one = 1;
setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
ssize_t n = send(fd, buf, len, MSG_MORE);   /* 短写是常态，不是错误 */
if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
    ; /* 发送队列满：等 EPOLLOUT，别 spin */
else if (n < 0 && errno == EMSGSIZE)
    ; /* UDP 超路径 MTU：应用层切片，别指望 IP 分片 */
```

**对应命令与读法**：

1. `ss -ti dst 10.0.0.5` → 看 `retrans:a/b`（左当前、右累计）、`rto`、`cwnd` 与 `ssthresh` 的相对大小、`unacked`、`send-q` → `retrans` 涨说明真丢包；`cwnd < ssthresh` 且 `cwnd` 明显小于 `10` 说明正处在慢启动或拥塞回退。→ **会骗你的情况**：`cwnd` 单位是 MSS 段数不是字节；连接刚建立时数值天然小；`retrans` 在 GSO 大包场景按段计数，看起来比实际严重。
2. `nstat -az | grep -E 'TcpRetransSegs|TCPLostRetransmit|TCPTimeouts|TCPOFOQueue'` → 看累计计数器的差值 → `TcpRetransSegs` 增长率超 0.1% 就有问题，`TCPLostRetransmit` 非零说明重传本身又丢了，链路很差。→ **会骗你的情况**：全部是累计值，进程或机器重启后清零，必须隔 10s 采两次做差，或直接看监控的 rate。
3. `ip -s link show eth0` → 看 RX/TX 的 `errors`、`dropped`、`overrun` → `overrun` 涨是网卡 ring buffer 满了（收不过来，多与中断绑核、NAPI 预算有关），`dropped` 涨看方向区分是驱动丢还是 qdisc 丢。→ **会骗你的情况**：容器里的 `eth0` 是 veth，统计是本端的对端视角，和物理链路无关；`noqueue` qdisc 下没有排队丢弃，dropped 恒为 0 不代表没丢。
4. `tcpdump -i any -nn -vv port 80` → 看 `[TCP Retransmission]`、`[TCP Dup ACK]`、`win` 窗口值、`mss` → 连续 Dup ACK 意味着对端有空洞、本端在快重传。→ **会骗你的情况**：抓包点在 GSO 之后，看到的是聚合大包；高流量下 tcpdump 自己丢包（`-w` 抓文件写盘也丢），漏包让人误判“没重传”；`-i any` 的链路层是 cooked 格式，看不到真实以太网头。
5. `ping -M do -s 1472 -c 2 host` → 1472 = 1500 − 20(IP) − 8(ICMP) → 成功说明路径 MTU ≥1500；返回 `EMSGSIZE`/`Frag needed` 就是 MTU 黑洞。→ **会骗你的情况**：需要 root 或 `net.ipv4.ping_group_range` 放行（按发行版而定）；ICMP 被防火墙拦时表现为超时，不是 MTU 问题。

**原理**：`send()` 把数据挂到 `sk_write_queue`，每个 `sk_buff` 计入 `sk_wmem_alloc`；TCP 只在 `cwnd` 与接收窗口的较小值允许时把 skb 交给 qdisc（`fq_codel`/`pfifo_fast`），所以“发出去了”和“离开网卡了”是两件事。MSS 由 SYN 的 MSS option 取双方最小值，路径 MTU 变小只会通过 ICMP `Frag needed` 或 PMTUD 超时被发现，扔掉 ICMP 的路由器就是黑洞的来源。拥塞控制是状态机：3 个 Dup ACK 触发快速重传并置 `ssthresh = max(FlightSize/2, 2*MSS)`，RTO 超时则 `cwnd` 归 1、指数退避，这就是“丢一个包卡两秒”的物理来源。接收侧 `rcv_ssthresh` 收缩会让发送方停在 `unacked`——此时 `ss` 上看到的是本端无辜、对端窗口为 0。

## 第 14 章〔网络〕连接边界：backlog、TIME_WAIT、端口耗尽与参数调优

**要解决的问题**：压测 QPS 上不去却偶发连接失败；日志里 `connect: Cannot assign requested address`；`Connection refused` 和 `Connection timed out` 混为一谈；机器上几万个 TIME_WAIT 让新人慌了神去改内核参数；`netstat -s` 里 listen overflow 在涨。不理解边界，调参只会把问题从一处搬到另一处。

**API 与代价**：

- `listen(fd, backlog)`：`backlog` 是**全连接队列**上限，且被 `net.core.somaxconn` 截断，内核取 `min(backlog, somaxconn)`。它从来不是“最大并发连接数”，已建立连接再多也只看这一个上限。
- `accept()`：从全连接队列取走请求。队列满时新到的 ACK 默认被丢弃，客户端感知是 `SYN` 重传后超时；`net.ipv4.tcp_abort_on_overflow=1` 则直接回 RST，变成 `Connection reset`。**代价**：超时慢、RST 快，前者掩盖故障，后者暴露但可能误伤。
- `SO_REUSEADDR`：允许 `bind` 一个仍处于 `TIME_WAIT` 的本地地址，只影响 bind 判定，不改变 TIME_WAIT 本身。`SO_REUSEPORT`：多进程共听同一端口，内核按四元组哈希分流；代价是哈希可能不均，某进程接了 95% 的连接。
- `connect()` 返回 `EADDRNOTAVAIL` = 本地临时端口耗尽（`ip_local_port_range` 内无可用四元组）；`ECONNREFUSED` = 对端 RST（没监听或 backlog 溢出且开了 abort）；`ETIMEDOUT` = SYN 无人应答。

```c
listen(fd, 4096);            /* 实际生效值是 min(4096, net.core.somaxconn) */
for (;;) {
    int c = accept4(fd, &sa, &slen, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (c < 0) {
        if (errno == EMFILE || errno == ENFILE) { /* fd 耗尽：留一个 spare fd 应急 */ }
        else if (errno == EAGAIN) { /* 水平触发下的重复就绪，不是错误 */ }
        else if (errno == ECONNABORTED) { continue; }   /* 客户端撤了 */
    }
}
```

**对应命令与读法**：

1. `ss -tan state time-wait | wc -l`（或 `ss -s` 的 `timewait` 行）→ 看总数与对端分布 → 短连接服务几万属于正常；活跃连接数只有几十而 TIME_WAIT 上万才值得查。→ **会骗你的情况**：TIME_WAIT 全在**主动关闭方**，如果你的机器是客户端，看到多说明是你在关连接；`ss -tan state time-wait` 在某些版本要写成 `state time-wait` 的小写连字符形式，写错会静默返回全部连接。
2. `ss -lnt` → 看 `Recv-Q`（当前全连接队列长度）和 `Send-Q`（该 socket 的 backlog 上限）→ `Recv-Q` 持续逼近 `Send-Q` 就是 accept 跟不上，`Send-Q` 小于你 `listen()` 传的值说明被 `somaxconn` 截断了。→ **会骗你的情况**：只对 LISTEN 状态的 socket 有这层含义，普通连接上 `Send-Q` 是发送队列字节数；IPv6 socket 用 `-4` 看不到。
3. `sysctl net.ipv4.tcp_max_tw_buckets net.ipv4.ip_local_port_range net.ipv4.tcp_tw_reuse net.core.somaxconn` → 看端口区间宽度、`tw_reuse` 是否开启 → 端口数 = 区间大小 × 目的 IP 数，区间 32768 配单目标 IP，短连接下几秒就能打满。→ **会骗你的情况**：`tcp_tw_reuse` 只对**主动发起连接**的客户端生效，服务端改它没用；它依赖时间戳避免 PAWS 回绕，对端禁用时间戳时复用会被拒。
4. `netstat -s | grep -iE 'overflow|drop|SYNs'`（新版用 `nstat -az TcpExtListenOverflows TcpExtListenDrops`）→ `listen overflows` 非零就是全连接队列满，`SYNs to LISTEN sockets dropped` 是半连接队列或全连接队列被丢的总量。→ **会骗你的情况**：`netstat` 在部分发行版已废弃、字段名随内核变化；数值是累计量，重启清零，要看 rate。
5. `ss -tan state syn-recv | wc -l` → 半连接队列当前深度 → 短时冲高正常，持续高位叠加 SYN drop 就是 SYN 攻击或 accept 阻塞。→ **会骗你的情况**：开了 `tcp_syncookies` 后，半连接队列不再需要挂满即可完成握手，这个数会偏低，看起来“很健康”。

**原理**：三次握手对应两个队列。SYN 到达时，内核在 `request_sock_queue` 的 `syn_table` 里建 `request_sock` 并回 SYN+ACK（半连接）；收到最终 ACK 后创建 `sock`，挂到 `sk_ack_backlog`，只有当 `sk_ack_backlog < sk_max_ack_backlog` 时才入队，否则丢 ACK 或（abort 开启时）回 RST——`sk_max_ack_backlog` 就是 `somaxconn` 截断后的那个值。`accept()` 只是从队列摘一个节点，所以“accept 慢”会直接表现为客户端超时，而不是服务端报错。TIME_WAIT 存在的原因是四元组在 $2 \times MSL$ 内不能再被复用，否则旧连接的延迟报文会污染新连接；`tcp_tw_reuse` 用时间戳做单调性校验后才敢复用。临时端口选择是 `bind_conflict` 在四元组哈希上做的冲突检测：端口区间窄、目的地址少、短连接多，三者相乘就是 `EADDRNOTAVAIL` 的充分条件。调大 `ip_local_port_range` 或用连接池复用长连接，才是治本；改 `tcp_max_tw_buckets` 只是让内核提前回收，日志会更干净，故障不会更少。

## 第 15 章 信号与可重入：屏蔽、竞态、EINTR 与异步安全

**要解决的问题**：进程收到 SIGTERM 却不退出、收到 SIGTERM 后退出得太快导致数据没写入磁盘、日志的最后一条丢失、`read` 偶尔返回 -1/EINTR 却被当成真正的错误、Ctrl-C 之后子进程变成孤儿或把父进程一起终止。信号是异步投递的：如果不显式屏蔽，就必然会在“检查标志”和“进入睡眠”之间丢失事件；如果 handler 里调用 `printf`/`malloc`，就会在主流程持有锁时死锁。这类故障出现频率低、无法稳定复现，排障成本远高于提前写对。

**API 与代价**：

- `sigaction(int sig, const struct sigaction *act, struct sigaction *old)`：`act.sa_mask` 在 handler 执行期间**追加**到屏蔽字（当前信号默认也被屏蔽，除非 `SA_NODEFER`）；`SA_RESTART` 让系统调用自动重试；`SA_SIGINFO` 才拿得到 `siginfo_t`（`si_code` 区分 `SI_USER`/`SI_KERNEL`/`SI_QUEUE`）。失败 `EINVAL`（信号号非法，或试图改 SIGKILL/SIGSTOP）。
- `sigprocmask(SIG_BLOCK,&set,&old)`：屏蔽字是**每线程**的。多线程进程必须用 `pthread_sigmask`，`sigprocmask` 在 glibc 多线程下行为未定义。
- 经典竞态：`if(!flag) pause();` 若信号在判断之后、`pause` 之前到达，事件永久丢失。正解是屏蔽 → 检查条件 → `sigsuspend(&old)`，原子地换屏蔽字并睡眠。
- handler 内只能用 async-signal-safe 函数：`write`、`_exit`、`kill`。`printf`（stdio 锁）、`malloc`（arena 锁）、`syslog` 都可能重入死锁。标志用 `volatile sig_atomic_t`，用 `int` 会被编译器缓存进寄存器。

```c
static volatile sig_atomic_t got;
static void h(int s){ int e=errno; char c='x'; write(2,&c,1); got=1; errno=e; }

sigset_t s, old; sigemptyset(&s); sigaddset(&s, SIGTERM);
sigprocmask(SIG_BLOCK, &s, &old);
struct sigaction sa = {.sa_handler=h, .sa_flags=SA_RESTART};
sigemptyset(&sa.sa_mask); sigaction(SIGTERM, &sa, NULL);
while (!got) sigsuspend(&old);        /* 原子：换屏蔽字 + 睡眠 */
sigprocmask(SIG_SETMASK, &old, NULL);
```

**对应命令与读法**：

- `kill -l` → 信号名与编号的对照表 → 说明 x86_64 上 `9=SIGKILL`、`15=SIGTERM`、`19=SIGSTOP` → **会骗你**：编号随架构变化（SIGUSR1 在 x86 是 10、MIPS 是 16），脚本里硬编码数字会杀错进程；SIGKILL/SIGSTOP 不可捕获、不可屏蔽，别指望 handler 清场。
- `grep -E 'Sig(Q|Blk|Ign|Cgt|Pnd)|ShdPnd' /proc/PID/status` → `SigQ` 是「已排队/上限」（受 `RLIMIT_SIGPENDING` 约束），`SigBlk`/`SigCgt` 是十六进制位图（bit0=SIGHUP，bit8=SIGKILL）→ 说明该线程屏蔽了哪些信号、装了哪些 handler、有无待决信号 → **会骗你**：标准信号不排队，同一信号多次投递只留一个，`SigQ` 很小也可能已经丢过；`SigPnd` 是线程私有、`ShdPnd` 是进程共享，看错列会误判成“信号没到”。
- `strace -e trace=signal -p PID` → 输出 `--- SIGTERM {si_signo=SIGTERM, si_code=SI_USER, si_pid=...} ---` 及随后的 `rt_sigreturn`、被打断的 `read(...) = -1 EINTR` → 说明信号确实送达、由谁发出、系统调用是被打断还是被重启 → **会骗你**：`SA_RESTART` 的重启由内核透明完成，看起来像一次成功调用；ptrace 改变了时序，纯竞态故障在 strace 下常常不复现。
- `kill -0 PID` → 退出码与 errno → `0` 存在且有权限、`EPERM` 存在但无权、`ESRCH` 不存在 → **会骗你**：僵尸进程照样返回 0，PID 也可能已被复用。
- `grep -i 'pending signals' /proc/PID/limits` → `Max pending signals` → 实时信号队列上限，打满后 `sigqueue` 返回 `EAGAIN` → **会骗你**：这只对实时信号有意义，标准信号永远不报这个错，只是静默合并。

**原理**：信号产生时 `send_signal()` 在 `task_struct->pending`（线程私有）或 `signal_struct->shared_pending` 上置位：标准信号只置一个 bit，实时信号挂进 `sigqueue` 链表并按 `RLIMIT_SIGPENDING` 限长——这就是“信号会丢”的内核根源。真正投递发生在返回用户态之前：`do_signal()` 把 `sigframe`（保存寄存器与旧屏蔽字）压到**用户栈**，把 `%rip` 改成 handler 入口，handler 一返回就落进 `__restore_rt` 触发 `rt_sigreturn`，由内核恢复原上下文——所以 handler 只是被内核劫持出来的一个普通函数调用，它没有独立的栈。被打断的系统调用若在 `TASK_INTERRUPTIBLE` 睡眠点被唤醒，内核返回 `-ERESTARTSYS`：有 `SA_RESTART` 且在白名单里（`read`/`write`/`wait`）就自动重入；`select`/`poll`/`epoll_wait`/`nanosleep` **从不重启**，必须自己处理 `EINTR`。信号处理过程本身不取任何锁，因此 handler 天然运行在主流程任意临界区的中间——这就是异步安全清单存在的全部理由。

## 第 16 章 IPC：管道、FIFO、共享内存、信号量、消息队列的取舍

**要解决的问题**：父子或兄弟进程之间要传数据、要互斥、要一方等另一方。选错机制的代价很具体：拿共享内存传结构体却忘了同步 → 读到被写端改了一半的字段；拿 System V 共享内存做临时缓冲 → 进程崩溃后

## 第 6 章 内存故障定位：OOM killer、泄漏、碎片与回收

**要解决的问题**：典型现场有三类。第一类是进程被 `SIGKILL`，日志只剩 `Killed`，`dmesg` 里一段 `Out of memory: Killed process`，但没人知道被杀的是不是写代码的那个人。第二类是 RSS 只涨不降，重启能缓解、几天后复发，是泄漏、缓存还是 glibc arena 碎片说不清。第三类是 `free` 看着还有几百 MB，`malloc(8MB)` 或 THP 却失败，`dmesg` 报 `order:3 allocation failure`，这是碎片而不是总量不足。三者处置完全不同：泄漏要改代码，碎片要 compaction 或调整分配尺寸，回收压力要调 watermark 与脏页比例。分不清就会用“定时重启”掩盖问题，把可用性赌在运气上。

**API 与代价**：

`mmap` 只建立虚拟映射，代价是 VMA 插入与页表项；真正的物理页在首次写入时由缺页异常分配。所以 `MAP_NORESERVE` 下 `mmap` 成功不代表内存够用，失败通常已经是 `ENOMEM`（超过 `vm.max_map_count`、或 overcommit 策略拒绝）。

```c
void *p = mmap(NULL, len, PROT_READ|PROT_WRITE,
               MAP_PRIVATE|MAP_ANONYMOUS|MAP_NORESERVE, -1, 0);
if (p == MAP_FAILED) {          /* ENOMEM：地址空间/map_count/overcommit */
    perror("mmap"); return -1;
}
memset(p, 0, len);              /* 此刻才占物理页，minor fault 逐页发生 */
madvise(p, len, MADV_DONTNEED); /* 匿名页：立即丢弃并清零，RSS 掉，映射保留 */
/* madvise(p, len, MADV_FREE); 惰性版：内核可回收，回收前读仍是旧值 */
munmap(p, len);                 /* 拆 VMA、断页表，代价与映射页数成正比 */

int fd = open("/proc/self/oom_score_adj", O_WRONLY);
write(fd, "-900", 4);           /* -1000..1000；调低需 CAP_SYS_RESOURCE */
```

关键分支：`madvise(MADV_DONTNEED)` 对匿名私有页是丢弃，对 `MAP_SHARED` 文件页是丢页缓存且**不保证写回**，脏页上用它等于拿数据完整性换内存。`mlock` 失败返回 `ENOMEM`（撞 `RLIMIT_MEMLOCK`），配合 `mmap(MAP_LOCKED)` 常用于防止关键页被回收，但也把页钉死在 zone 里，加重碎片。glibc 侧：大于 `M_MMAP_THRESHOLD`（默认 128 KB，动态可升到 32 MB）的请求走 `mmap`，`free` 后立即 `munmap` 还给内核；小块走 `brk`  arena，多线程会分裂出多个 arena，每个 arena 各自持有空闲块，这就是“进程 RSS 不降但 `malloc` 也没泄漏”的常见来源。`malloc_trim(0)` 可把 arena 顶部归还，但只对 `brk` 段有效。

**对应命令与读法**：

1. `dmesg -T | grep -iE 'out of memory|oom-kill|allocation failure'` → 看 `order:N`、`Killed process <pid> (<comm>) total-vm/rss`、是否 `memory cgroup out of memory` → `order` 大于 0 说明是**高阶分配失败**（碎片/紧急回收），不是总量不足；`cgroup out of memory` 走的是 memcg 限额而非全局 → 会骗你：全局 OOM 选中的是 `oom_badness` 最高者，往往不是真凶；容器里 `dmesg` 常被 `dmesg_restrict` 或命名空间挡住，看不到。

2. `grep -E 'MemTotal|MemFree|MemAvailable|Dirty|Writeback|Slab|SReclaimable|SUnreclaim|Committed_AS|CommitLimit' /proc/meminfo` → `MemAvailable` 是内核估算的可回收+空闲，`Dirty` 是待回写脏页，`SReclaimable` 是可回收 slab（dentry/inode 缓存），`SUnreclaim` 是不可回收 → `SUnreclaim` 单项持续增长基本可判内核对象泄漏；`Committed_AS` 逼近 `CommitLimit`（`overcommit_memory=2`）时 `malloc` 会直接失败 → 会骗你：`MemFree` 低完全不代表内存紧张，page cache 占满是设计目标；`MemAvailable` 是启发式估算，对不可移动页、zram、cgroup 限额都不感知。

3. `cat /proc/buddyinfo` → 每行一个 zone，从左到右是 order 0..10 的空闲块个数 → order-0 成千上万而 order-3 及以上为 0，说明**内存碎成小块**，此时 `free` 再多也满足不了 THP、`fork` 的连续页表、大块 slab → 会骗你：不包含 per-CPU pageset 缓存（`/proc/pagetypeinfo` 才有迁移类型拆分），order 高处的块也可能落在 `ZONE_MOVABLE`/CMA 里普通分配用不上。

4. `grep -E 'min|low|high|protection|nr_free_pages|nr_zone_inactive_anon|nr_zone_active_file|scanned|pgsteal' /proc/zoneinfo` → 把 `nr_free_pages` 和 `protection: (x, y, z)` 的 min/low/high 比大小 → 低于 low 唤醒 kswapd，低于 min 触发 **direct reclaim**，进程在 `alloc_pages` 里同步卡住，表现为延迟尖刺和 CPU `sys` 升高；`scanned` 涨而 `pgsteal` 不涨是**扫描无果**，常见于全是不可回收页 → 会骗你：各 zone 要分别看，Normal 紧张时 DMA32 的富余帮不上；watermark 有 boost 值，瞬时显示会偏高。

5. `valgrind --tool=massif --pages-as-heap=yes --massif-out-file=/tmp/m.out ./prog` 再 `ms_print /tmp/m.out` → 看峰值快照的调用栈和 `(B)` 字节数 → 栈顶函数就是增长点；`--pages-as-heap=yes` 把 `mmap`/`brk` 也按堆计入，覆盖直接调 `mmap` 的分配器 → 会骗你：默认只跟踪 `malloc` 家族，看不到 `mmap`；程序慢 10–20 倍，超时逻辑会改变行为；对 `MADV_FREE` 延迟回收不敏感。

6. `slabtop -o -s c`（或 `grep -E 'dentry|inode_cache|task_struct|kmalloc' /proc/slabinfo`）→ 看 `OBJS`/`ACTIVE` 与 `SIZE` → `dentry` 随目录遍历暴涨多为缓存（可回收），`kmalloc-*` 单项只增不减才是泄漏 → 会骗你：`ACTIVE` 小于 `OBJS` 的差额是空闲对象，仍占 slab 页；`SReclaimable` 在压力下会被 shrinker 收走，看着“泄漏”其实不是。

**原理**：物理页由 buddy 分配器按 order 管理，`free_area[order]` 是伙伴链表，分配不到就向上一级借并劈半，释放时若伙伴空闲则合并——合并是碎片的解药，而**不可移动页**（内核 slab、页表、长期 `mlock` 的页）夹在可移动页之间，就把大块永久切碎了。内核为此给页块打迁移类型（`MIGRATE_UNMOVABLE/RECLAIMABLE/MOVABLE`），并尽量按类型聚集；`/proc/pagetypeinfo` 才看得到这层，compaction 就是把可移动页搬走来拼出高阶块，代价是 CPU 与停顿。

回收分两条腿：文件页在 page cache 里，匿名页靠 swap。两者都挂在 per-zone 的 LRU 双链表（active/inactive × anon/file）上，kswapd 按 watermark 后台扫描，先降级 active→inactive 再回收；进程如果分配快过 kswapd，就在 `alloc_pages` 的 slowpath 里**同步**做 direct reclaim，这是尾延迟的最大来源。脏页必须先回写才能回收，所以 `Dirty` 高、`Writeback` 堵（`dirty_ratio`/`dirty_background_ratio`、设备带宽不足）时，回收会被 IO 拖住，`MemAvailable` 看着够却一直进 direct reclaim。

OOM killer 在回收彻底失败后启动，按 badness 选人：

$$\text{badness}=\frac{\text{rss}+\text{swap}+\text{pgtables}}{\text{totalram}}\times 1000+\text{oom\_score\_adj}$$

所以**占内存多的被杀**，而不是导致紧张的被杀；memcg 下限额见底时同理，但它只在 cgroup 内选，且 `memory.oom.group` 可整组杀。判断泄漏的可靠口径是分区看：RSS 涨而 `SUnreclaim` 不涨、`PagesAnon` 涨、`smaps_rollup` 里某段 `Private_Dirty` 单调涨，才指向用户态泄漏；否则优先怀疑缓存与 arena 碎片。
