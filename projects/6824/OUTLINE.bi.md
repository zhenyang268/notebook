> **双语对照版**：英文原段 → 紧随其后的中文译文（引用块，前缀 `译：`）；每节末附该节生词表。术语首次出现保留英文原词，方便对照阅读与翻译练习。

## 1. What It Is Doing

This project is to write a consensus kernel: make a group of machines (usually 3 or 5) reach complete agreement on “which command to execute next”—even if a minority of them crash, restart, or the network is intermittently disconnected.

> 译：这个项目要做的是编写一个共识内核（consensus kernel）：让一组机器（通常是 3 台或 5 台）就“下一条要执行哪条命令”达成完全一致——即使其中少数机器崩溃、重启，或网络间歇性断开。

The interface is very narrow. An upper-layer service calls `Start(cmd)` to submit a command: if the current node is the leader, it gets the position `(index, term)` that the command will have in the log in the future; if not, it gets `isLeader=false`, and the upper layer retries elsewhere. On all nodes there is an `applyCh` channel; Raft feeds into it, one by one in exactly the same order, commands that have been confirmed by a majority and will not be overturned. After the upper layer receives them, it executes them itself (for example, writes to a KV store), and does not need to know about internal structures such as the log, terms, or voting.

> 译：接口非常窄。上层服务调用 `Start(cmd)` 提交一条命令：如果当前节点是领导者（leader），它就得到该命令将来在日志（log）中所在的位置 `(index, term)`；如果不是，它就得到 `isLeader=false`，上层再到别处重试。所有节点上都有一个 `applyCh` 通道；Raft 会把那些已获多数（majority）确认、且不会被推翻的命令，按照完全相同的顺序逐条送入这个通道。上层收到这些命令后，会自行执行它们（例如写入 KV 存储），而不需要了解日志、任期（term）或投票等内部结构。

Acceptance looks at four scenarios: kill the leader, and the cluster elects a new one within one second; one hundred clients write concurrently, and after they stop, the log prefix on every node is exactly the same; unplug the network cable of a minority and plug it back in, log entries that were not committed while isolated must be overwritten, and not a single committed entry may be lost; the whole group of machines loses power and restarts at the same time, terms do not go backward, and there are no two votes in the same term; a node whose log has been compressed by a snapshot can catch up a new node that is severely behind.

> 译：验收会考察四个场景：杀掉领导者（leader），集群在一秒内选出新的领导者；一百个客户端并发写入，并在它们停止后，每个节点上的日志前缀（log prefix）完全相同；拔掉少数机器的网线再插回去，隔离期间未提交（committed）的日志条目必须被覆盖，而已提交的条目一条也不得丢失；整组机器同时断电并重启，任期（term）不会倒退，同一个任期内不会出现两票；日志已被快照（snapshot）压缩的节点，能够使一个严重落后的新节点追赶上来。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| consensus | n. | 共识 | consensus kernel |
| intermittently | adv. | 间歇地 | intermittently disconnected |
| minority | n. | 少数 | a minority of them |
| leader | n. | 领导者 | is the leader |
| majority | n. | 多数 | confirmed by a majority |
| overturned | v. | 推翻 | will not be overturned |
| acceptance | n. | 验收 | Acceptance looks at |
| committed | adj. | 已提交的 | committed entry |
| snapshot | n. | 快照 | compressed by a snapshot |

## 2. Why Do It This Way (Functional Design)

**What is being replaced.** In reality nobody hand-writes consensus—using etcd/raft or hashicorp/raft libraries, a replication group can be started in a few lines of code. This project removes that entire library layer and writes it itself, keeping only two given things: an RPC framework that can inject packet loss, delay, reordering, duplication, and network disconnection, and a fake disk that can only read and write bytes as whole blocks. In other words, the two sources of “unreliability” are given and are not replaced; what is replaced is the middle layer of logic that “turns unreliable communication into a reliable total order.”

> 译：**被替换的是什么。** 现实中没有人手写共识（consensus）——使用 etcd/raft 或 hashicorp/raft 库，几行代码就能启动一个复制组（replication group）。这个项目移除了整个库层并自己实现它，只保留两样给定的东西：一个可以注入丢包（packet loss）、延迟（delay）、重排序（reordering）、重复（duplication）和网络断开（network disconnection）的 RPC 框架，以及一个只能按整块读写字节的假磁盘（fake disk）。换句话说，“不可靠性”（unreliability）的两个来源是给定的，并且不被替换；被替换的是那层“把不可靠通信变成可靠的全序（total order）”的中间逻辑层。

The interface is cut at the state machine boundary and must be upheld: the upper layer may only throw commands in and take committed commands out of the channel; it is not allowed to read Raft’s internal log in reverse for a “fast read”—that amounts to skipping the “majority confirmation” step, and what is read may be overwritten at any time.

> 译：接口切分在状态机（state machine）边界处，并且必须被遵守：上层只能把命令（commands）扔进去，并从通道（channel）中取出已提交（committed）的命令；不允许反向读取 Raft 的内部日志（internal log）来做“快速读取（fast read）”——那等于跳过“多数确认（majority confirmation）”步骤，而且读到的内容可能随时被覆盖（overwritten）。

**It is an in-process library, not a standalone service.** This choice determines all the concurrency style that follows. Because Raft and the upper layer are in the same address space and share a struct, using a mutex to protect state and keeping critical sections short is easier and more auditable than “turning every event into a message and feeding it into a loop.” The cost is that lock ordering must be maintained by yourself: once an RPC is sent while holding the lock, it will stall the entire node or even deadlock, and in distributed tests this shows up as random timeouts that are extremely hard to locate. Therefore “the lock must be released before sending an RPC” must be treated as a hard rule before writing the first line of replication logic.

> 译：**它是一个进程内库（in-process library），不是独立服务（standalone service）。** 这个选择决定了随后所有的并发（concurrency）风格。因为 Raft 和上层处于同一地址空间（address space）并共享一个 struct，所以使用互斥锁（mutex）保护状态、并保持临界区（critical sections）简短，比“把每个事件变成消息并送入一个循环”更容易，也更可审计（auditable）。代价是锁顺序（lock ordering）必须由你自己维护：一旦在持有锁时发送 RPC，它就会拖住整个节点，甚至死锁（deadlock），而在分布式测试中，这会表现为极难定位的随机超时（random timeouts）。因此，在编写第一行复制逻辑（replication logic）之前，就必须把“发送 RPC 前必须释放锁”当作一条硬性规则（hard rule）。

**Where unreliability comes from and how it is suppressed.** Four sources correspond to four mechanisms:

> 译：**不可靠性来自哪里，以及它如何被抑制。** 四种来源对应四种机制：

- RPCs can be lost and duplicated. → Write every handler to be idempotent: upon receiving AppendEntries, first compare the term, then compare `prevLogIndex/prevLogTerm`; if they do not match, reject so that the leader backs up; if the same request is received twice, the result is the same. The sender does not ask “did it succeed,” it only retries in a loop until success or until it finds that it is no longer the leader. At-least-once delivery + idempotent handling is equivalent to exactly once.

   > 译：RPC 可能丢失，也可能重复。→ 把每个 handler 都写成幂等的（idempotent）：收到 AppendEntries 时，先比较 term，再比较 `prevLogIndex/prevLogTerm`；若两者不一致，就拒绝，好让 leader 回退；若同一个请求收到两次，结果相同。发送方不问“它成功了吗”，它只是在循环里重试，直到成功，或者直到发现自己已不再是 leader。至少一次投递（at-least-once delivery）+ 幂等处理（idempotent handling）等价于恰好一次（exactly once）。

- Messages can be reordered and arrive late. → Each AppendEntries carries `(prevLogIndex, prevLogTerm)`, and the receiver checks whether its own entry at that position really is that log entry; if not, it rejects. This one check is the entire implementation of the “log matching property”: it turns reordering into “temporarily not accepted” rather than “accepting the wrong thing.”

   > 译：消息可能被重排序，也可能迟到。→ 每个 AppendEntries 都携带 `(prevLogIndex, prevLogTerm)`，接收方检查自己在该位置上的条目是否真的是那条日志条目；若不是，就拒绝。这一项检查就是“日志匹配特性（log matching property）”的全部实现：它把重排序变成“暂时不接受”，而不是“接受了错误的东西”。

- Network partitions can occur. → Use term numbers as a logical clock and majorities as the admission condition. The minority side can neither gather enough votes to elect a leader nor gather enough `matchIndex` to advance `commitIndex`; after the partition heals, it returns with a higher term, and the old leader is forced to step down.

   > 译：网络分区（network partition）可能发生。→ 用任期编号（term numbers）作为逻辑时钟（logical clock），并用多数派（majorities）作为准入条件（admission condition）。少数派一侧既无法收集到足够票数来选出领导者（leader），也无法收集到足够的 `matchIndex` 来推进 `commitIndex`；分区愈合后，它以更高的任期（term）返回，旧领导者（old leader）被迫下台（step down）。

- Power loss and restart can occur. → `currentTerm`, `votedFor`, the log, and snapshots must be persisted **before replying**. If the order is reversed, most scenarios can still run, but double voting will be exposed at the power-loss point.

   > 译：断电与重启可能发生。→ `currentTerm`、`votedFor`、日志和快照必须在**回复之前**持久化（persisted）。如果顺序反过来，大多数场景仍可运行，但双重投票（double voting）会在断电点暴露出来。

**Why not use simpler approaches.** No replication on a single machine, then this project is not needed. “The primary synchronously writes all replicas”: one slow machine blocks the entire cluster, and it is impossible to distinguish “slow” from “dead” except by timeout; once timeouts are introduced, split brain appears, and then terms and majorities are required, so after going around in a circle we are back here. Fixed timeouts: nodes that start elections at the same time keep colliding, votes are split, and it may be impossible to elect a leader for a long time; the random interval `[T, 2T]` is the lowest-cost means of reducing the collision probability to an acceptable level. Taking `commitIndex` directly as the majority `matchIndex` without checking the term: simpler, but it would allow the leader to commit a log entry “from before its current term that was not actually confirmed by a majority,” which is then overwritten, and a command already returned to the client is lost—the restriction “only entries from the current term can be committed directly by a majority” exists to plug this hole.

> 译：**为什么不使用更简单的方法。** 单机上不做复制（replication），那么这个项目就不需要了。“主节点（primary）同步地写入所有副本（replicas）”：一台慢机器就会阻塞整个集群，而且除了通过超时（timeout）之外，无法区分“慢”和“死”；一旦引入超时，脑裂（split brain）就会出现，于是又需要任期（terms）和多数派（majorities），所以绕了一圈又回到这里。固定超时：同时开始选举的节点会不断碰撞，选票被分散，可能长时间无法选出领导者；随机区间 `[T, 2T]` 是把碰撞概率（collision probability）降到可接受水平的最低成本手段。直接把 `commitIndex` 当作多数派的 `matchIndex` 而不检查任期：这样更简单，但它会让领导者提交一条“来自其当前任期之前、实际上并未被多数派确认”的日志条目，随后这条日志条目被覆盖，而一个已经返回给客户端的命令就丢失了——“只有当前任期内的条目才能由多数派直接提交”这一限制，正是为了堵住这个漏洞。

**Data shape.** The log is an append-only array, each entry carries `(term, command)`, and the index is implicit; a snapshot is a compression of the prefix, and after compression the log no longer starts from 0, so all index arithmetic must add an offset. This offset is the biggest source of errors in the second half—wherever an index appears, ask “is this a logical index or a physical index?”

> 译：**数据形状（Data shape）。** 日志是一个只追加（append-only）数组，每个条目携带 `(term, command)`，而索引是隐式（implicit）的；快照（snapshot）是对前缀的压缩，压缩之后日志不再从 0 开始，所以所有索引运算都必须加一个偏移量（offset）。这个偏移量是后半部分最大的错误来源——只要出现索引，就问一句「这是逻辑索引还是物理索引？」

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| consensus | n. | 共识 | hand-writes consensus |
| reordering | n. | 重排序 | delay, reordering, duplication |
| duplication | n. | 重复 | reordering, duplication, and network disconnection |
| upheld | v. | 被遵守；被维护 | must be upheld |
| committed | adj. | 已提交的 | committed commands |
| overwritten | v. | 被覆盖 | may be overwritten at any time |
| auditable | adj. | 可审计的 | more auditable |
| stall | v. | 拖住；阻塞 | will stall the entire node |
| deadlock | v. | 死锁 | even deadlock |
| suppressed | v. | 抑制、压制 | how it is suppressed |
| idempotent | adj. | 幂等的（重复执行结果不变） | Write every handler to be idempotent |
| retries | v. | 重试 | it only retries in a loop |
| duplicated | v. | 重复、被复制 | lost and duplicated |
| reordered | v. | 重排序、重新排序 | can be reordered and arrive late |
| rejects | v. | 拒绝、不接受 | it rejects |
| log matching property | n. | 日志匹配特性 | the “log matching property” |

## 3. Chapter Outline

1. **Consensus and Replicated State Machines**—why a single machine is not enough; what linearizability is actually saying (“it looks like one machine”); the three-layer decomposition of consensus layer / state machine layer / sharding layer; the list of invariants Raft promises. After doing this, you can clearly state the exact meaning of “committed,” and can point out which invariant a seemingly correct implementation violates.

   > 译：**共识与复制状态机（Consensus and Replicated State Machines）**——为什么单台机器不够；线性一致性（linearizability）究竟在说什么（「它看起来就像一台机器」）；共识层 / 状态机层 / 分片层（sharding layer）的三层分解；Raft 所承诺的不变式（invariant）清单。做完这些之后，你能清楚地说出「已提交（committed）」的确切含义，并能指出一个看似正确的实现违反了哪一条不变式。

2. **RPC and Concurrency Skeleton**—the semantics of RPCs being lost, duplicated, and reordered; one goroutine per RPC; how to draw critical sections; timers and `select`; the harm of sending RPCs while holding the lock. After doing this, you can use two nodes to ping each other and still converge under injected packet loss and delay, and no alarms are raised under the race detector.

   > 译：**RPC 与并发骨架**——RPC 被丢失、被重复、被重排（reordered）的语义；每个 RPC 一个 goroutine；如何画出临界区（critical section）；定时器与 `select`；持锁时发送 RPC 的危害。做完这些之后，你能让两个节点互相 ping，并且在注入丢包和延迟的情况下仍然收敛，而且在竞态检测器（race detector）下不会报警。

3. **Leader Election**—terms increase monotonically, one vote per term, RequestVote parameters, the restriction “do not vote if the candidate’s log is not up to date,” randomized election timeout, heartbeats. After doing this, you can verify: after killing the leader, a new one is elected within one second; repeated rounds do not produce occasional failures to elect; during a partition, both sides cannot win at the same term.

   > 译：**领导者选举（Leader Election）**——任期（term）单调递增，每个任期只投一票，RequestVote 参数，“如果候选人的日志不够新就不投票”这一限制，随机化选举超时（randomized election timeout），心跳（heartbeat）。做完这些之后，你可以验证：杀掉领导者后，一秒之内会选出新的领导者；反复多轮也不会出现偶尔选不出来的情况；在网络分区（partition）期间，两侧不能在同一任期都赢得选举。

4. **Log Replication**—the complete AppendEntries parameters, the `prevLogIndex/prevLogTerm` check, `nextIndex` backtracking (backing up one by one or jumping by term), advancing `commitIndex` using the median of `matchIndex`, the current-term restriction, and ordered delivery to `applyCh`. After doing this, you can verify: concurrent writes converge to the same log; uncommitted entries accumulated by an old leader while isolated are overwritten.

   > 译：**日志复制（Log Replication）**——完整的 AppendEntries 参数，`prevLogIndex/prevLogTerm` 检查，`nextIndex` 回退（backtracking）（逐条后退或按任期跳跃），用 `matchIndex` 的中位数（median）推进 `commitIndex`，当前任期限制，以及向 `applyCh` 有序投递（ordered delivery）。做完这些之后，你可以验证：并发写入会收敛到同一份日志；旧领导者在隔离期间累积的未提交条目会被覆盖。

5. **Persistence and Crash Recovery**—the three pieces of state that must be persisted, the order of persistence and reply, replay after restart, and snapshots must also be persisted together. After doing this, you can verify: after power loss and restart, terms do not go backward, votes are not repeated, and committed commands are still there.

   > 译：**持久化与崩溃恢复（Persistence and Crash Recovery）**——必须持久化的三部分状态，持久化与回复的先后顺序，重启后的重放（replay），以及快照（snapshot）也必须一并持久化。做完这些之后，你可以验证：断电重启后，任期不会倒退，投票不会重复，已提交的命令仍然还在。

6. **Snapshots and Log Compaction**—what is stored in a snapshot, the semantics of `lastIncludedIndex/Term`, index offsets, the trigger conditions for InstallSnapshot, and how `nextIndex` is aligned after installing a snapshot. After doing this, you can verify: after the log has been compacted, a brand-new node can still catch up from the leader and continue normal replication.

   > 译：**快照与日志压缩（Snapshots and Log Compaction）**——快照中存储了什么、`lastIncludedIndex/Term` 的语义、索引偏移（index offsets）、InstallSnapshot 的触发条件，以及安装快照后如何对齐 `nextIndex`。做完这些后，你可以验证：日志被压缩之后，一个全新的节点仍然能够从领导者（leader）那里追赶上来，并继续正常复制。

7. **Correctness Arguments and Testing Methods**—compare the five safety properties against the implementation one by one; fault injection (packet loss rate, delay, partitions, restarts); why distributed tests must be run repeatedly, and one pass does not count as passing; race detector and random seeds; the idea of linearizability checking (take out the history and see whether it can be arranged into a legal total order). After doing this, you can design, for a bug hypothesis, a scenario that is bound to expose it, instead of relying on lengthening timeouts and hoping for luck.

   > 译：**正确性论证与测试方法（Correctness Arguments and Testing Methods）**——将五条安全性属性（safety properties）逐条与实现对照；故障注入（fault injection）（丢包率、延迟、分区、重启）；为什么分布式测试必须反复运行，并且一次通过不能算作通过；竞态检测器（race detector）与随机种子（random seeds）；线性一致性检查（linearizability checking）的思路（取出历史记录，看它能否被排列成一个合法的全序（total order））。做完这些后，你可以针对一个 bug 假设，设计一个必定能暴露它的场景，而不是依靠延长超时（timeout）并寄希望于运气。

8. **Connecting One Layer Up: KV and the Boundary**—the actual usage of `Start` + `applyCh`; the client request number deduplication table implementing “exactly once”; why linearizable reads are harder than linearizable writes (the two ideas ReadIndex / lease); why the upper layer cannot read the log in reverse. After doing this, you can verify: a minimal KV behaves as expected for get/put under partitions and restarts, and the upper layer does not reference Raft internal structures.

   > 译：**向上连接一层：KV 与边界（KV and the Boundary）**——`Start` + `applyCh` 的实际用法；客户端请求编号去重表实现“恰好一次（exactly once）”；为什么线性一致读（linearizable reads）比线性一致写（linearizable writes）更难（ReadIndex / lease 两种思路）；为什么上层不能反向读取日志。做完这些后，你可以验证：一个最小 KV 在分区和重启下对 get/put 的行为符合预期，并且上层不引用 Raft 内部结构。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| linearizability | n. | 线性一致性（一种强一致性正确性条件） | what linearizability is actually saying |
| invariant | n. | 不变式；不变量（任何时刻都必须成立的性质） | the list of invariants |
| sharding | n. | 分片（把数据/负载切分到多个分片） | sharding layer |
| reordered | v. | 被重排；顺序被打乱（此处为过去分词） | lost, duplicated, and reordered |
| critical section | n. | 临界区（访问共享数据、必须互斥执行的代码段） | how to draw critical sections |
| race detector | n. | 竞态检测器（检测数据竞争的工具） | under the race detector |
| term | n. | 任期 | terms increase monotonically |
| randomized election timeout | n. | 随机化选举超时 | randomized election timeout |
| partition | n. | （网络）分区 | during a partition |
| backtracking | n. | 回退，回溯 | `nextIndex` backtracking |
| median | n. | 中位数 | the median of `matchIndex` |
| ordered delivery | n. | 有序投递 | ordered delivery to `applyCh` |
| replay | n. | 重放 | replay after restart |
| snapshot | n. | 快照 | snapshots must also be persisted |
| Log Compaction | n. | 日志压缩 | Snapshots and Log Compaction |
| InstallSnapshot | n. | 安装快照（RPC） | trigger conditions for InstallSnapshot |

## 4. What Not to Do

**Not required by the course**: membership changes (joint consensus, adding/removing nodes), cross-shard and shard migration, multi-group shard management, production-grade TLS/authentication/monitoring. These are necessary for real systems but unrelated to “understanding majorities.”

> 译：**课程不要求**：成员变更（membership changes）（联合共识（joint consensus）、增加/删除节点）、跨分片与分片迁移（shard migration）、多组分片管理、生产级的 TLS/认证/监控。这些对真实系统是必要的，但与“理解多数派（majorities）”无关。

**Explicitly left to the upper layer**: the business semantics of the state machine, the specific implementation of client sessions and the deduplication table, the read request optimization path, batching and pipelining. Raft only guarantees “the same commands arrive at every `applyCh` in the same order”; it does not care about anything else.

> 译：**明确留给上层**：状态机（state machine）的业务语义、客户端会话（client sessions）与去重表（deduplication table）的具体实现、读请求的优化路径、批处理（batching）与流水线（pipelining）。Raft 只保证“相同的命令以相同的顺序到达每一个 `applyCh`”；其他一概不管。

**Implementation freedom (anything is fine as long as the invariants hold)**: log serialization format (gob or hand-built binary); snapshot trigger policy (by entry count, by bytes, or decided by the upper layer); whether `nextIndex` backs up one by one or uses fast backtracking; one big lock or segmented locks; whether `applyCh` is delivered by an independent goroutine or directly on the commit path. The only criterion for tradeoffs: can it make bugs easier to find?

> 译：**实现自由（只要不变式（invariants）成立，怎么做都行）**：日志序列化格式（gob 或手工构造的二进制）；快照触发策略（按条目数、按字节数，或由上层决定）；`nextIndex` 是逐个回退还是使用快速回溯（fast backtracking）；用一把大锁还是分段锁（segmented locks）；`applyCh` 由独立的 goroutine 投递，还是直接在提交路径上投递。权衡取舍的唯一标准：它能让你更容易发现 bug 吗？

**Common deviations**:

> 译：**常见偏差**：

- Increasing timeouts and adding `sleep` in order to “make it pass.” This hides uncertainty, and it will be exposed as soon as you change the seed or run a few more rounds.

   > 译：增大超时（timeout）并加入 `sleep`，只为“让它通过”。这会掩盖不确定性，而一旦你改变种子（seed）或多跑几轮，它就会暴露出来。

- Treating one pass as done. The default state of distributed tests is instability; they must be run repeatedly and with the race detector enabled.

   > 译：把一次通过当作完成。分布式测试（distributed test）的默认状态是不稳定；必须反复运行，并启用竞态检测器（race detector）。

- Sending RPCs while holding the lock. At best it causes overall stalls, at worst deadlocks, and it manifests as random timeouts, which are the hardest to troubleshoot.

   > 译：持锁期间发送 RPC。往好了说，它会造成整体停顿（stalls）；往坏了说，会造成死锁（deadlocks）；而它表现出来的形式是随机超时（random timeouts），这类问题最难排查（troubleshoot）。

- Replying before persisting. Most scenarios can pass, but the category that specifically tests power loss will fail in the most uncomfortable place.

   > 译：在持久化（persisting）之前就回复。大多数场景都能通过，但专门测试断电（power loss）的那一类场景会在最令人难受的地方失败。

- Taking `commitIndex` directly as the majority `matchIndex` without checking the term, causing committed entries to be overwritten.

   > 译：不检查任期（term）就直接把 `commitIndex` 当作多数派的 `matchIndex`，导致已提交的条目被覆盖。

- The upper layer, for convenience, directly reads the log to get results, reads uncommitted data, and the entire layering design is wasted.

   > 译：上层为了图方便，直接读日志来拿结果、读到未提交（uncommitted）的数据，整个分层（layering）设计就白白浪费了。

- Thinking you understand after only finishing election and skipping persistence and snapshots—that is only “can elect a leader,” not “can store data.”

   > 译：只做完选举（election）就跳过持久化（persistence）和快照（snapshots），便以为自己懂了——那只是“能选出领导者”，而不是“能存数据”。

**生词**

| 单词 | 词性 | 释义 | 文中搭配 |
|:---|:---|:---|:---|
| membership changes | n. | 成员变更 | membership changes (joint consensus, adding/removing nodes) |
| joint consensus | n. | 联合共识 | joint consensus |
| shard migration | n. | 分片迁移 | cross-shard and shard migration |
| state machine | n. | 状态机 | the business semantics of the state machine |
| deduplication table | n. | 去重表 | client sessions and the deduplication table |
| pipelining | n. | 流水线（技术） | batching and pipelining |
| invariants | n. | 不变式 | as long as the invariants hold |
| backtracking | n. | 回溯 | fast backtracking |
| segmented locks | n. | 分段锁 | one big lock or segmented locks |
| deviation | n. | 偏差；偏离 | Common deviations |
| timeout | n. | 超时 | Increasing timeouts |
| seed | n. | 种子（随机数种子） | change the seed |
| expose | v. | 暴露；揭露 | will be exposed |
| instability | n. | 不稳定性 | The default state of distributed tests is instability |
| race detector | n. | 竞态检测器 | with the race detector enabled |
| repeatedly | adv. | 反复地；多次地 | run repeatedly |
