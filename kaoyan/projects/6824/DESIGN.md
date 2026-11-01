# 6.824 · 分布式系统 · 设计文档

> 本文是该项目的设计说明，不是教程。
> 大纲见 `OUTLINE.md`，一小时上手见 `QUICK.md`，详细记录见 `NOTES.md`。

## 一、定位与边界

本项目实现 Raft 共识算法的内核：Leader 选举、日志复制、持久化与日志快照。它对外只暴露三个原语——`Start(command) (index, term, isLeader)`、`GetState()`、`Snapshot(index, data)` / `CondInstallSnapshot(...)`，把"多条命令在集群内形成同一个全序"这件事做成可复用的黑盒。

不解决：状态机的语义（KV 读写、去重表、客户端会话）、线性一致读的实现路径（ReadIndex / lease）、成员变更（joint consensus）、跨分片配置。这些留给上层服务。与相邻项目的分工是：Lab1 提供 RPC 与并发的工程习惯；本项目提供共识内核；后续 KV 服务只做"把命令交给 Raft、从 applyCh 取已提交命令"两件事，不得反向读取 Raft 内部日志。

## 二、整体架构

模块划分与职责：

- **RPC 层**：`RequestVote`、`AppendEntries`、`InstallSnapshot` 三组 handler 与发送端，负责参数封装、任期比较、过期请求丢弃。
- **角色状态机**：Follower / Candidate / Leader 的转换条件与副作用（重置计时器、发起投票、启动/停止复制协程）。
- **选举计时器**：随机化超时 $\text{electionTimeout} \in [T, 2T]$，每次收到合法心跳或授予投票即重置。
- **复制器**：每个 peer 一个协程，维护 $nextIndex_i$、$matchIndex_i$，串行发送 AppendEntries。
- **提交与应用**：由 $matchIndex$ 的中位数推进 $commitIndex$，仅当 $log[commitIndex].term = currentTerm$ 时才提交；独立协程按序投递到 `applyCh`。
- **持久化层**：`persister` 保存 $currentTerm$、$votedFor$、$log$ 与快照，状态变更后同步落盘。
- **快照器**：截断前缀日志、安装远端快照、处理快照与日志索引的偏移。

调用方向单向：上层 → `Start` → 日志追加 → 复制器 → 对端 handler → 落盘 → ACK → 提交推进 → `applyCh` → 上层；快照由上层触发，向下压缩日志。

## 三、技术选型与理由

- **Go**：goroutine 与 `select` 天然表达"计时器 + RPC 并发"，且课程 `labrpc` 只提供 Go 接口。替代方案 C++/Java 需自建 RPC 与超时框架，与教学重点无关。
- **`sync.Mutex` 为主、channel 为辅**：Raft 状态是共享结构体，临界区短，互斥锁比消息传递更易审计锁顺序；仅 `applyCh`、`killCh` 用 channel。
- **`labrpc` 而非 gRPC**：可注入断网、延迟、重复、乱序，是验证安全性的必要条件；gRPC 无法模拟分区。
- **`encoding/gob` 而非 JSON**：日志条目与快照为二进制，gob 体积小、无需 tag 维护；代价是字段必须导出。
- **`go test -race`**：并发 bug 的主要发现手段，选它而非人工 review。

## 四、数据流

一次写请求的路径：客户端命令 → `Start` 在 Leader 锁内追加 `LogEntry{Term, Index, Command}` 并 `persist` → 复制协程取 $(nextIndex_i-1)$ 的 term 作 `PrevLogTerm` 发送 → Follower 做一致性检查，冲突则删除后缀并回退，匹配则追加并 `persist` → Leader 收到成功响应更新 $matchIndex_i$，扫描出满足多数派且任期匹配的最大索引作为 $commitIndex$ → 应用协程把 $[lastApplied+1, commitIndex]$ 依次送入 `applyCh` → 上层调用 `Snapshot` 后，日志前缀被裁掉，$lastIncludedIndex$ 前移，后续所有索引都加上该偏移。

关键数据结构：$log[]$、$nextIndex[]$、$matchIndex[]$、$commitIndex$、$lastApplied$、$lastIncludedIndex$、$lastIncludedTerm$、$electionDeadline$。

## 五、章节目录与知识点映射

| 章 | 内容 | 涉及的知识点 | 与考纲或前置项目的关系 |
|---|---|---|---|
| 2A-1 | 任期与投票 | 任期单调不减；每个任期至多一票；$\text{votedFor}$ 与 $currentTerm$ 同事务持久化 | 前置：Lab1 的 RPC 参数校验 |
| 2A-2 | 随机超时选举 | 超时区间需大于心跳数倍且随机化，避免活锁与无限分裂投票 | 分布式共识的 liveness 与 split vote |
| 2A-3 | 日志新旧比较 | 候选人的最后一条日志 $(term, index)$ 字典序不落后才可获票 | 选举安全性：Leader Completeness 的前提 |
| 2B-1 | AppendEntries 一致性检查 | $\text{PrevLogIndex}$ / $\text{PrevLogTerm}$ 匹配；冲突时删除后缀 | Log Matching Property 的归纳证明 |
| 2B-2 | 提交规则 | 只有 $log[N].term = currentTerm$ 才能由多数派推出 $commitIndex=N$ | Figure 8 反例：旧任期日志不可直接提交 |
| 2B-3 | 失败回退优化 | 按冲突任期的首个索引跳跃回退 $nextIndex$，而非逐条 $-1$ | 收敛速度：RPC 次数从 $O(n)$ 降到 $O(\text{任期数})$ |
| 2C-1 | 持久化三要素 | $currentTerm$、$votedFor$、$log$ 在响应 RPC 前落盘 | 崩溃恢复后不得重复投票、不得丢已提交日志 |
| 2D-1 | 快照与索引偏移 | $lastIncludedIndex$、$lastIncludedTerm$；$log[0]$ 作哨兵占位 | 日志压缩与 $commitIndex$ 基准平移 |
| 2D-2 | InstallSnapshot | 分块传输 $\text{Offset}$/$\text{Data}$/$\text{Done}$；`CondInstallSnapshot` 与 `Snapshot` 的原子性 | 快照与并发 Apply 的竞态 |
| 工程 | 锁粒度与死锁 | 持锁发 RPC 导致死锁；`applyCh` 阻塞导致提交停滞；`-race` 检测 | 与 Lab1 并发调试经验衔接 |

## 六、验收判据

- `go test -run 2A` 连续 20 次通过，单次耗时 < 30 s。
- 心跳周期 ≤ 100 ms（每节点每秒 ≤ 10 次 AppendEntries），选举超时 300–600 ms。
- 关闭 Leader 后 5 s 内选出新 Leader；`TestReElection2A` 中反复切换 5 次均恢复。
- `TestFigure8Unreliable2C` 连续 10 次通过，日志最终一致率 100%。
- `TestBackup2B` 在 5 s 内完成，`TestRPCBytes2B` 每命令平均 RPC 字节数不随重试线性膨胀。
- 快照阈值 1000 条：压缩后日志长度 < 100；`TestSnapshotInstallUnCrash2D` 通过。
- 全量测试 `-race` 零告警，`applyCh` 无阻塞超过 1 s。

## 七、风险与已知坑

- 随机超时区间与心跳间隔重叠，导致持续重选；或所有节点用同一随机源，出现同步分裂投票。
- 修改 $currentTerm$ 或 $votedFor$ 后未立即 `persist`，重启后重复投票，破坏选举安全。
- 持锁发送 RPC 或持锁写 `applyCh`，前者死锁、后者阻塞提交。
- 已应用索引与快照偏移混用：裁剪日志后仍用原始下标访问，越界 panic。
- 提交旧任期日志（违反 Figure 8），在分区恢复场景丢数据。
- gob 字段未导出导致持久化"成功"但读回为空，测试只在重启用例暴露。
- `CondInstallSnapshot` 与 `Snapshot` 各自加锁，产生快照覆盖竞态。

## 八、与其他项目的关系

前置：Lab1 MapReduce 提供 RPC handler 结构、goroutine 生命周期管理与调试方法。后续：Lab3 基于本内核实现线性一致的 KV 服务（去重表、客户端请求号）；Lab4 在 KV 之上做分片与配置变更，依赖本项目的 `Start` 与快照接口。可复用模块：`persister` 封装、三组 RPC handler 的参数校验骨架、`applyCh` 投递协程模板、随机化计时器工具。这些模块在后续项目中不应重写，只应调用。
