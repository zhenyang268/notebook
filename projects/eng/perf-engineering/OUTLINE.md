## 一、它解决什么问题

性能工程拦住的是两类事：一类是线上“平均指标好看、尾部已经出事”的事故；另一类是面试里“会背 P99、会画火焰图，但说不清口径和判据”的失分。

场景一（示意量级）：某接口平均延迟 20–30 ms，SLO 要求 P99 < 200 ms；压测只看平均 QPS，报告“达标”。峰值时 P99 到 1–2 s，超时重试放大流量，最后触发限流。问题不在“不会用 perf”，而在指标口径、饱和点、压测连接模型和重试放大没有被纳入同一套判断。

场景二（示意量级）：服务从 4 核扩到 16 核，CPU 利用率看似还有余量，但 QPS 只从几千涨到略高，未线性增长。若没有强扩展/弱扩展、临界区、锁竞争和 IO 等待的量化，容易误判为“机器不够”，继续加副本，成本上升而尾延迟不降。

这项能力的目标不是“会跑工具”，而是把性能结论变成可复核的：口径明确、负载明确、样本明确、边界明确。

**入口（本文的读法）**：在固定 SLO 字段 p99_ms、qps、error_rate、timeout_ms，负载模型 open/closed-loop、连接池大小、retry 与 backoff、HTTP 429/503，采样口径 perf_event_open task-clock/cycles/instructions、sched_switch/futex_wait/epoll_wait、HDR histogram 约束下，解决达标/瓶颈/扩容的边界判定问题。

**不换的是什么**：全程不变的是同一 trace_id/request_id 关联、同一 percentile 分桶与采样窗口、同一负载模型参数（并发、connection_pool_size、timeout_ms/retry_policy、CPU affinity/NUMA）、同一计数器语义（cycles/instructions 与 sched_switch/futex_wait/io_submit 时间戳）；看到差异先问：是否换了 p99 bucket、perf 采样频率、closed/open loop、重试次数、火焰图折叠规则或系统调用计数口径。

**积木**：①perf_event_open 的 cycles/instructions/task-clock 计数器与 ring buffer 样本；它能独立验证一个 tid 在一个采样窗口内消耗了多少 CPU 周期、指令数和 task-clock 时间。②HDR histogram 的 bucket 计数与 p99_ms 字段；它能独立验证同一请求窗口内第 99 百分位延迟是否低于 200ms。③sched_switch、futex_wait、epoll_wait 内核事件与等待队列；它能独立验证线程是否离开 CPU 并进入调度切换、futex 等待或 fd 就绪等待。④HTTP 429/503 状态码字段与 retry/backoff 计数；它能独立验证客户端是否因 429/503 产生额外尝试请求。

**最小情形**：单核单线程两节点一次 HTTP 请求：perf_event_open 只采集该 tid 的 cycles/instructions/task-clock，HDR histogram 只写入一个 bucket，sched_switch 只记录该 tid 是否被内核抢占，futex_wait/epoll_wait 不产生等待事件；NUMA distance、CPU affinity、closed/open loop、connection_pool_size、HTTP 429/503 retry/backoff 在此刻没有可验证对象。

**生成**：累加 单线程一次请求到多核多连接负载模型，新增 CPU affinity、NUMA node、closed/open loop、connection_pool_size、retry/backoff 与 HTTP 429/503 字段约束；覆盖 perf_event_open task-clock/cycles/instructions、sched_switch/futex_wait/epoll_wait、HDR histogram bucket/percentile 和 trace_id/request_id 关联；最坏情形是 p99 bucket 被 retry 尝试请求计入、perf 采样频率过低漏掉 task-clock 短样本、epoll_wait/futex_wait 等待被火焰图折叠规则归入同一栈帧。

**两边**：同一请求延迟状态可表示为用户态 HDR histogram 的 bucket 计数与 p99_ms 字段，也可表示为内核 perf_event_open ring buffer 中的 task-clock/cycles/instructions 样本；前者由压测线程持有，后者由内核 perf 子系统持有。

## 二、为什么这样做（方法论设计）

关键取舍一：**有口径才算数**。一个性能结论至少要绑定：工作负载（读写比、数据集、并发模型）、指标定义（成功请求还是尝试请求、单实例还是集群）、采样窗口与样本量、环境（CPU 拓扑、频率策略、内核/运行时版本、编译选项）、重复次数与置信区间。缺一项，结论就只能算线索，不能算证据。

关键取舍二：**看起来专业但无法证伪的做法要警惕**。单次火焰图、单次压测、只报平均值、“缓存命中率 99%”但不说明 miss 类型与工作集、“QPS 很高”但不说明成功率与尾延迟，都属于不可证伪。火焰图宽度是采样占比，不是耗时因果；没有 on-CPU/off-CPU 对照，容易把“等锁/等 IO”误判为“算得慢”。

指标怎么定：吞吐定义为“单位时间内满足成功判据的请求数”，必须写清成功判据与统计边界；延迟用分布，至少 P50/P90/P99/P999 与样本数，均值只作辅助。P99 的算法要固定（如 nearest-rank 或固定桶直方图），并报告样本量；样本不足以覆盖尾部事件时，P99 不可比。饱和点用“吞吐不再上升且排队延迟出现拐点”作判据，阈值需在 SLO 下预先声明，不能事后挑点。

边界怎么划：benchmark 只能回答“在该负载模型下”的问题；profiling 有采样偏差和扰动，开销按实现和负载而定；微基准不能直接外推到生产；JIT/GC、频率缩放、虚拟化、噪声邻居、coordinated omission 都会让结果失效。失效时结论应降级为“假设”，而不是“优化收益”。

常见错误为什么错：只看平均延迟，代价是尾部超时与重试放大；单次跑分决策，代价是把噪声当收益；不做 warmup，代价是冷缓存/冷 JIT 误导；压测客户端先饱和，代价是测到假天花板；只看一张 on-CPU 火焰图就改代码，代价是绕开真正的等待点。排队直觉可用 Little 定律作 sanity check：$$
 L=\lambda W 
$$，其中 $L$ 为系统内请求数，$\lambda$ 为到达率，$W$ 为停留时间；量纲不一致时，先怀疑口径。

## 三、章节大纲

**指标与口径：吞吐、延迟分布、P99 与饱和点**  
讲吞吐的成功判据、延迟直方图与分位数、P99 样本量、饱和点与拐点判定。学完能回答：“P99 怎么算、样本多少才可信、如何判断系统已饱和？”

**benchmark 怎么设计才不骗自己（warmup、隔离、重复、置信区间）**  
讲 warmup、环境隔离、重复实验、置信区间、负载模型与结果记录。学完能回答：“你的 benchmark 如何排除噪声和冷启动，如何证明差异不是偶然？”

**CPU profiling：采样 vs 插桩，perf 与 Instruments 怎么用**  
讲采样与插桩的取舍、perf record/report、Instruments Time Profiler 的基本用法与扰动评估。学完能回答：“采样和插桩怎么选，profiling 开销如何判断？”

**火焰图读法：on-CPU 与 off-CPU，宽度、合并与调用栈**  
讲火焰图宽度含义、调用栈合并、on-CPU 与 off-CPU 的区分及误读。学完能回答：“火焰图最宽的函数一定是根因吗？等待时间怎么看出来？”

**内存与缓存：miss、NUMA、伪共享的量化**  
讲 cache miss、LLC、NUMA 访问、伪共享的实验与指标。学完能回答：“如何量化缓存问题和伪共享，而不是凭感觉加 padding？”

**IO 与锁竞争：iostat、perf lock、临界区怎么量**  
讲 iostat 的 await/util/queue、perf lock 竞争、临界区测量与等待占比。学完能回答：“IO 慢还是锁慢，临界区怎么量，优化判据是什么？”

**压测与容量估算：连接模型、排队直觉、限流位点**  
讲开环/闭环连接模型、coordinated omission、Little 定律、限流位点与容量余量。学完能回答：“压测 QPS 能否直接外推到线上？限流应放在哪里？”

**加速比与扩展性：Amdahl、强扩展与弱扩展**  
讲串行比例、强扩展/弱扩展、效率与瓶颈迁移。学完能回答：“加机器为什么不线性？强扩展和弱扩展分别怎么测？”

## 四、不做什么 · 必要性 · 失效点

### 必要性：删掉会怎样

| 机制 | 删掉会怎样 | 判定 |
|---|---|---|
| 指标口径 | 删掉“成功请求/尝试请求、单实例/集群”绑定后，SLO 的 P99 < 200 ms 承诺不可复核；重试放大会被计入尝试请求，压测“达标”变成错误结论 | 必需 |
| 饱和点 | 删掉“吞吐不再上升且排队延迟出现拐点”判据后，平均 QPS 报告会在压测连接模型耗尽、限流触发前误判达标，P99 1–2 s 尾部事故漏过 | 必需 |
| on-CPU/off-CPU | 删掉 off-CPU 对照后，火焰图宽度只给采样占比，`futex_wait`/`epoll_wait` 等等待点无法与计算热点区分，会把锁竞争/IO 等待误判为“算得慢” | 必需 |
| 重复次数与置信区间 | 删掉重复次数与置信区间后，单次压测的 P99 差异无法区分噪声与收益；`nearest-rank`/固定桶直方图结果只能降级为假设 | 选择 |
| 强扩展/弱扩展 | 删掉强扩展/弱扩展判据后，4 核扩到 16 核 QPS 不线性会被归因为机器不够，继续加副本而不检查临界区/锁竞争 | 必需 |

### 失效点：哪条前提一破，结论就变

- `CAP_PERFMON`/`ptrace` 权限位从允许变为拒绝 → `perf_event_open` 返回 `EPERM`，on-CPU/off-CPU 对照缺失，火焰图宽度不能证明 `futex_wait`/`epoll_wait` 等待点。
- CPU 频率策略从 `performance` governor 变为 `schedutil`/动态调频 → `rdtsc`/TSC 周期与 ns 延迟换算失效，P99 分布混入频率缩放，微基准不能外推到生产。
- 工作集从 L3 缓存内变为 DRAM/NVMe 介质 → 缓存命中率 99% 不再覆盖 miss 类型，IO 等待主导尾延迟，饱和点从 CPU 吞吐拐点移动到块设备队列深度/`epoll` 等待。
- HTTP 协议版本从 HTTP/1.1 keep-alive 长连接变为 HTTP/2 多路复用或短连接 TLS handshake → 成功请求延迟包含 `SETTINGS`/TLS 证书验证，P99 < 200 ms 的 SLO 口径改变，压测连接模型需重算。
- 时钟源从 TSC 稳定变为 `kvm-clock`/NTP step → 采样窗口与样本量时间戳失真，coordinated omission 无法对齐重试放大，Little 定律 \(L=\lambda W\) 的量纲 sanity check 失效。

### 不做什么（范围）

不做 408 考点式的操作系统选择题、页面置换算法推导和调度算法背诵；这些属于考试层，不是这里的判据。不做具体语言语法、框架入门和 API 用法教学；工具只讲到能形成证据链。不做某云厂商参数模板、某内核版本的固定调优清单；参数与默认值按实现和版本而定。不做无负载模型的容量承诺，也不把未经验证的“优化案例”包装成结论。

## 五、面试怎么讲

**30 秒版本（120–180 字）**  
我能把“性能慢”拆成可复核的口径：先定义吞吐、延迟分布、P99 与饱和点；再用 warmup、隔离、重复和置信区间设计 benchmark；随后用 perf/Instruments 采样、火焰图区分 on-CPU 与 off-CPU，配合 iostat、perf lock 和缓存指标定位瓶颈；最后用排队模型与强/弱扩展判断容量边界。

**可能被追问的 6–8 个点**

1. 问法：“P99 怎么算，样本多少才够？”→ 考点：分位数口径。答：固定算法（nearest-rank 或固定桶直方图），报告样本数、窗口和成功率；样本不足以覆盖尾部事件时，P99 不可比，需用更长窗口或更高负载复测。
2. 问法：“benchmark 怎么防止骗自己？”→ 考点：实验设计。答：warmup、环境隔离、重复运行、置信区间、固定数据集与负载模型；记录 commit、编译选项、内核、CPU 拓扑和频率策略，否则差异不可归因。
3. 问法：“采样和插桩怎么选？”→ 考点：扰动与精度。答：采样开销低但有统计偏差，插桩精确但可能改变时序；用 A/B 对照测 profiling 开销，开销按实现和负载而定。
4. 问法：“火焰图宽度代表什么？”→ 考点：读图边界。答：宽度是采样占比，不是延迟因果；要区分 on-CPU 与 off-CPU，合并调用栈后看热点，但不能只凭一张图断言根因。
5. 问法：“缓存 miss 和伪共享怎么量化？”→ 考点：指标与实验。答：用 perf stat 看 cache-misses、LLC-load-misses、cycles、instructions，用 perf c2c 或 padding 对照实验验证伪共享；判据是 miss 与 cycles 是否同向改善。
6. 问法：“IO 慢还是锁慢？”→ 考点：等待归因。答：iostat 看 await、util、queue，perf lock 看竞争与等待时间，临界区用插桩或锁统计量测；比较等待时间占总延迟比例。
7. 问法：“压测 QPS 能直接外推线上吗？”→ 考点：连接模型与容量。答：不能直接外推；要说明开环/闭环、客户端是否先饱和、是否有 coordinated omission，用 Little 定律 $L=\lambda W$ 做一致性检查，限流放在瓶颈之前的入口层。
8. 问法：“加机器为什么不线性？”→ 考点：扩展性。答：用 Amdahl 定律 $S(n)=1/((1-p)+p/n)$ 估上界；强扩展固定问题规模看 $S(N)=T_1/T_N$，弱扩展固定每节点工作量看效率 $E(N)=T_1/T_N$，并检查共享瓶颈是否迁移。

**别说什么**

- “平均延迟降了，所以性能好了。”——尾部与 SLO 可能更差。
- “火焰图最宽，所以根因就是它。”——宽度是采样占比，可能是等待或采样偏差。
- “压测到多少 QPS，线上就能扛多少。”——负载模型、连接模型、数据量和客户端瓶颈都不同。
- “加机器就能线性扩展。”——串行比例、锁、IO 和共享资源会让加速比饱和。

  Update available: 2.7.1 → 2.7.2
  Run bl update to upgrade
