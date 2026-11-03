# 6.824 · 分布式系统（Raft）

> **工程线（兴趣向，非考试范围）**。本文件不承担复习任务。
> MIT 6.824：Raft 一致性、KV 服务与分片。
>
> **单向引用约定**：本文提到考点时**只写 KP 号与考点名**，不复制 `exam/` 的正文；
> `exam/` 的文件里也不出现本文件的工程名。两边互不依赖，只共享主键。

## 对位考点（单向引用）

| 本文段落 | 对应 KP |
|---|---|
| 一把大锁与通道同步 | `408-OS-0203` 同步与互斥 |
| goroutine 与线程模型 | `408-OS-0201` 进程与线程 |
| 超时与定时器 | `408-OS-0202` CPU 调度 |

---

## 0 怎么读这个文件

### 0.1 一条纪律：先确认口径，再下结论

分布式这块最容易出的错不是"不懂 Raft"，而是**把一处代码当成全部事实**：同一远程的多工作区、多分支，读错分支就会得出"这块没做"的结论，而真相在另一个分支里。这条纪律适用于所有引用代码的场景——**先确认分支与版本，再引用**。

本文的写法因此固定为：结论后面跟一条可复查的判据（哪个行为、哪类测试、哪条日志），而不是"我看过代码"。

### 0.2 阅读顺序

- §1 总纲与**两仓三分支关系**（先看这个，别再踩同一个坑）
- §2 设计理念（三支柱 + 分布式 KV 三层分解）—— 全部 lab 共用的底座
- §3 Lab2 复盘（对照 master 版真实代码，含 **2D 快照**与锁专题）
- §4–6 Lab1 / **Lab3（已有实现）** / **Lab4（复制版起步）**
- §7 **C++ craft 重写线**（全部重写：它已经是个能跑的原型，不再是骨架）
- §8–10 408 对接 / 动手顺序与判据 / 检查清单

---

## 1 总纲

### 1.1 一句话

> **在普通进程里模拟一个集群，最终造出一个「容错的、线性一致的、可分片扩展的分布式 KV 数据库」——Raft 是地基，kvraft 是本体，shardkv 是屋顶。**

### 1.2 四个 lab 的台阶

| 台阶 | Lab | 解决的新问题 | 上一层留下的痛点 |
|---|---|---|---|
| 1 并行 | Lab1 MapReduce | 单机算力不够 → 多机并行 | worker 会挂 → 需要容错 |
| 2 容错 | Lab2 Raft | 机器会挂 → 多副本 | 副本不一致 → 需要共识 |
| 3 一致 | Lab3 kvraft | 共识之上建**线性一致** KV | 客户端重试重复执行 → 去重 |
| 4 扩展 | Lab4 shardkv | 单组写入瓶颈 → 按 key 分片 | 分片迁移 → 新协议 |

每层的「新问题」都是上一层方案直接制造的 —— 这条因果链比背知识点有用。

### 1.3 本地仓体检（v2 修正后的真实状态）

**Go 版（`learning-408/raft`，master）**

| 组件 | 状态 | 证据 |
|---|---|---|
| Lab1 MapReduce | **未做**：`mr/coordinator.go` 70 行全 `// Your code here`（`main/` 的 wc.so / mr-out-0 是 `mrsequential` 顺序版产物） | 实读 |
| Lab2 2A 选举 | 完成 | 实读 + 测试通过 |
| Lab2 2B 复制 | 完成 | 实读 + 测试通过 |
| Lab2 2C 持久化 | 已有实现 | 实读 |
| **Lab2 2D 快照** | **已有实现**（`lastSnapshotIndex/Term` 持久化 + `CondInstallSnapshot` + `Snapshot` + `InstallSnapshot` RPC + leader 侧转快照） | 实读 raft.go:208-269 / 665-729 / 758 |
| **Lab3 kvraft** | **已有实现**（`Op` 含 OpType/Key/Value/ClientId/SeqNum；`db/seqMap/resultMap` 三表；apply 循环 + snapshot 编解码） | 实读 server.go 284 行 |
| Lab4 shardkv | **kvraft 完整复制版**（补 `resultMap`/500ms 超时/入口缓存，并顺手修好 `isSuccess :=` 与 `LogLenth` 单位错误），但**仍无任何分片逻辑**，且编译不通过：`shardkv/common.go` 的 `GetArgs/PutAppendArgs` 缺 `ClientId/SeqNum` 字段、包内没有 `DPrintf` | 实读 server.go 282 行 + `go build ./shardkv/` 实测 |
| 其它产物 | `raft/raft_diagram.pdf`（47 KB，你自己画的架构图，在仓里） | stat |

**C++ 版（`raft/craft/`，craft v1.0，已合并）**

| 模块 | 行数 | 状态 |
|---|---|---|
| `src/raft/node.cpp` | **465** | **完整 raft 内核**：三个 gRPC handler + 选举 + 复制 + 提交推进 + apply 循环 |
| `include/craft/raft/raft_node.hpp` | 139 | 完整类设计（含 `group_id`、`LockFreeQueue`、`FaultInjector`） |
| `include/craft/raft/raft_timer.hpp` | 157 | condition_variable 版定时器（**忽略传入 timeout**，内部 150–300ms） |
| `raft_timer_asio.{hpp,cpp}` | 52+98 | asio 版定时器（**尊重 timeout + jitter**，最新提交的产物，**但未被 node.cpp 使用**） |
| `include/craft/raft/lockfree_queue.hpp` | 51 | 无锁队列（单消费者简化版，见 §7.4 缺陷 3） |
| `include/craft/kvserver/kvserver.hpp` | 98 | KVServer 包装 RaftNode；**apply 只打印，无状态机** |
| `include/craft/controller/group_config.hpp` | 50 | **已为 Lab4 设计**：`config_version` / `shard_to_group` / `groups` / `group_fault_configs` |
| `include/craft/controller/grpc_inject.hpp` | 81 | **故障注入完整**：丢包率 / 延迟 / 目标方法 / 目标节点 / 分区表 |
| `include/craft/controller/controller.hpp` | **0** | 空（shardctrler 未写） |
| `include/craft/raft/storage.h` + `storage.cpp` | 约 130 | **2C 持久化**：`RaftStorage` 原子写（tmp→fsync→rename→fsync(dir)）；`InMemoryLog` 仍留作单测对象 |
| `proto/raft.proto` | 53 | **完整三 RPC**（RequestVote / AppendEntries / InstallSnapshot） |
| `src/main.cpp` | 约 110 | **单节点进程**：`--config` 指定配置、`--auto-propose N` 让 leader 自动投命令（从"同进程 3 节点 demo"改造） |
| `proto/config.proto` + `conf/node*.conf` + `src/config/config_loader.cpp` | 60+40+120 | **protobuf text 配置**（group/me/listen/peers/fault）→ `GroupConfig`；TextFormat 解析 + 校验 |
| `CMakeLists.txt` | 86 | 完整：C++20 + protobuf + gRPC + Boost::system + proto 自动生成 |
| 测试 | 30+7 | 单测只测被淘汰的 `InMemoryLog`；system test 只断言 binary 存在 |
| `Dockerfile` + `docker-compose.yml` + `scripts/{docker_cluster,inject_fault}.sh` | 约 300 | 3 容器集群（固定 IP + NET_ADMIN），可在容器内做 tc/iptables/disconnect 真链路故障 |

**结论**：这条线是五条实践线里**唯一「Go 侧做到 Lab3、C++ 侧有自己的可用原型」**的线。复习价值最高，且 C++ 仓已经解决了「没有 labrpc 怎么造不可靠网络」这个最大障碍。

### 1.4 两个工作区、三个分支（这是上一版翻车的根因）

```
git@gitee.com:we_we_we/raft.git
   ├── master      ★ 真正要看的分支（含 craft v1.0 合并、lab3、2D 快照）
   ├── craft        旧 C++ 骨架分支（没有 2D 改动；曾被误当成全部事实）
   └── lab2c-fin    临时测试分支

两个本地工作区：
   ~/develop/raft                        → HEAD 在 craft（旧）
   ~/develop/learning/learning-408/raft  → HEAD 在 master（新，引用代码看这个）
```

**纪律**：引用代码前先 `git -C <路径> log --oneline -1 && git branch --show-current`。同一远程的多工作区，`git log` 默认只看当前分支，**分支不对 = 事实全错**。

### 1.5 关键路径（最少白费）

```
① 读 master 版 2D 快照（§3.4，2h）        ← 复核点，属于"理解已写过的代码"
        │
② 读 kvraft（§5，2h）→ 找那三个缺陷        ← 复核点，属于"审查已写过的代码"
        │
③ C++ craft（§7，4-6h）姿态二选一：
   ├─ 轻：读 465 行 + 对照表，理解 Go→C++ 的并发模型迁移（推荐，4h）
   └─ 重：续写 InstallSnapshot + kvserver 状态机 + controller（20h+，初试后）
        │
④ Lab1 MR（4-6h）/ Lab4 shardkv（15h+）    ← 冲刺期不建议
```

理由：Go 侧 Lab2（含 2D）与 Lab3 在仓里已有实现、C++ 侧已有可用原型——**剩下的价值在「审查」而不在「续写」**。审查能同时喂 408（锁与并发）+ 面试（真实的权衡案例），续写只喂工程。

---

## 2 设计理念 ★

### 2.1 并行：MapReduce 的「移动计算不移动数据」

（Lab1 未做，理念先行，提纲见 §4。）把 map 函数编译成 `.so`（你的 `main/wc.so`）派送到数据所在机器执行 —— 搬运 TB 数据的时间远超计算时间。coordinator 不监控 worker 死活，只监控**任务**是否完成（10s 超时重派），这是分布式「超时派活」路线的极简版。

### 2.2 容错：复制状态机

> **一组机器上的确定性状态机，喂相同的命令序列，必然到达相同状态。**

只要保证「多数派日志一致」，多数派就能在任何少数派故障时继续服务。三个设计决定都从这个母题推导：

1. **多数派而非全员**：任意两个多数派必有交集 → 一个 term 只可能选出一个 leader（选举安全）。你的 C++ 版 `majority = peers_count_/2 + 1`（node.cpp:289）就是它的落地。
2. **strong leader**：数据流单向（leader → follower），换来「日志只从一个方向来」，实现与理解成本骤降。C++ 版 `sendAppendEntries` 里 follower 只会 `resize` 截断对齐，从不反向推。
3. **term 作逻辑时钟**：只增、可比较、见大就认输（step down）。你代码里所有 step-down 都是这条。

### 2.3 一致性：线性一致 =「看起来像一台机器」

- **写要恰好一次**：网络重试 → 去重表（`ClientId + SeqNum`）。
- **读要新**：Get 也必须走日志（不能 leader 直接读本地 map）——你的 kvraft 在 apply 分支里专门写了注释「一致性的关键, 应该返回 log 应用时的 db 状态机结果, 而不是直接读取」，说明你当年想清楚了；但 §5.2 会指出你在**入口处**又违反了它。

### 2.4 分布式 KV 数据库的三层分解 ★

```
第3层 分片层 shardkv（Lab4）   shard_to_group + 配置版本 + 迁移   → 水平扩展
第2层 语义层 kvraft（Lab3）    Op + dupTable + 等待提交          → 恰好一次 + 线性读
第1层 共识层 raft（Lab2）      日志 + 多数派 + 选举 + 快照        → 机器会挂 / 网络会断
```

每层只信任下一层最少的承诺：kvraft 不关心怎么选主，只信「applyCh 的命令序列全组一致」；shardkv 只信「每片上的操作线性一致」。**你 C++ 版把这三层直接写进了目录结构**：`raft/`、`kvserver/`、`controller/`（`group_config.hpp` 的注释原话：「{KVServer 1:1 RaftNode}: 本地进程间通信」「controller 负责管理」）——这个分层是照着数据库架构图搭的，比 Go 版的平铺更接近真实系统。

### 2.5 全部 bug 的总根源

| 形态 | 表现 | 你的代码里对应的例子 |
|---|---|---|
| 过期消息 | 迟到回执把状态改回去 | Go 版 `nextIndex` 只进不退；C++ 版回锁后重验 term/state |
| 重复消息 | 同一命令执行两次 | kvraft 里没用去重表就会 Append 两次 |
| 脑裂 | 旧 leader 还在服务 | **kvraft `Get` 入口读缓存（§5.2 缺陷 1）** |
| 崩溃恢复 | 内存丢、磁盘留 | 2C 三样持久化；2D 重启用「假快照」强制 service 重装 |

---

## 3 Lab2 Raft 复盘（master 版 1139 行）

### 3.0 架构

**状态字段**（raft.go:101-130）：`currentTerm` / `votedFor` / `logs` / `role` / `committedIndex` / `lastAppliedIndex` / `nextIndex[]` / `matchIndex[]`，**2D 新增** `lastSnapshotIndex` / `lastSnapshotTerm`，以及自定义的 `applyCh`。

**三个后台 goroutine**：

```
ticker()（ResetTimer :305 / ResetTicker :328）
    20ms 大循环轮询 electionTimer / heartbeatTimer
applier（Make 里 :1015）
    轮询 committedIndex > lastAppliedIndex → 推 applyCh；lastAppliedIndex == -1 时先推"假快照"
RPC handler（labrpc 派生）
    入口即 Lock；网络调用永远在锁外
```

### 3.1 2A 选举（要点 / 易错点）

**关键路径**：`Make`（:973）→ 初始 timeout `250+rand(151)`ms（:993）→ `ticker` 超时 → `Elect`（:397）term+1 + 自投 + persist + 并行拉票 → 过半变 leader 并初始化 `nextIndex[i]=len(logs)`、`matchIndex[i]=0`。

**易错点清单**（逐条能在代码里找到对应的防线）：

- **随机超时**：`ResetTimer` 里 `250+rand(251)`（:305 起）。不随机 → 全网同时超时、拉票分裂、永远选不出（选举活锁）。
  - 你代码里仍保留一处**不一致**：`Make` 初值区间 `rand(151)`、`ResetTimer` 区间 `rand(251)`。都远离心跳 60ms，能过测，属「侥幸正确」。
- **一个 term 只投一票**：`votedFor == -1 || votedFor == candidateId`。
- **投票限制（up-to-date 比较）**：先比 `LastLogTerm`，相等再比 `LastLogIndex` —— 字典序。C++ 版 `isLogUpToDate` 同理（node.cpp:435）。
- **收到更高 term 必须 step down 且重置 votedFor**，三处：RequestVote / AppendLogEntry / heartbeat 回执。
- **`voteCount` 为什么不需要 atomic**：它虽是 Elect 的局部变量被多个 goroutine 自增，但每次自增都在 `rf.mu` 内。判据是「是否被同一把锁覆盖」，不是「是否共享」。

### 3.2 2B 日志复制

**leader 一次 sendHeartbeats**：锁内拷贝 args（`PrevLogIndex=nextIndex-1`、`PrevLogTerm`、`Entries=logs[nextIndex:]`、`LeaderCommit`）→ 锁外 Call → 回锁验证 → 成功则推进 nextIndex/matchIndex 并试提交 / 失败则回退 nextIndex。

**follower 的 `AppendLogEntry`（:515）四道关**：

1. term < 自己 → 拒绝
2. term > 自己（或自己不是 follower）→ step down
3. `PrevLogIndex` 超界 → 拒绝 + 回 hint
4. `logs[PrevLogIndex].Term != PrevLogTerm` → 拒绝（真冲突）

**易错点**：

- **只提交当前任期的日志**（`logs[matchIndex].Term == currentTerm`）：论文 Figure 8 的坑。旧 term 日志即使复制到多数派也不能直接提交，只能被「提交一条当前 term 日志」捎带。你代码注释里那句 `L(1 2 4) s(1 2) s(1 2)` 就是 Figure 8 场景。**这是 2B 最深的一坑，也是面试最爱问的**。
- **follower 的 commit 上限**：`min(LeaderCommit, lastLogIndex)`。漏掉 min → apply 越界。
- **nextIndex 乱序防护**：两个 in-flight 回执乱序时，旧回执不能把 nextIndex 拉回去（「过期消息」形态）。
- **心跳即一致性检查**：没有独立心跳消息，`LogEntries` 可空但 `PrevLogIndex/Term` 永远带 —— 这就是 Raft 与很多协议的区别。
- **防御性分支必须显式置 `IsSuccess=false`（你的代码在这里漏了一处，见 §3.2.1）**：`reply.IsSuccess` 的初始值是 **true**（raft.go:523），所以任何「提前 return」的分支如果忘了改它，leader 就会收到**成功**。

### 3.2.1 一个真 bug：follower 的 `PrevLogIndex < lastSnapshotIndex` 分支返回 success=true

**位置**：`AppendLogEntry`（raft.go:569-576）

```go
if args.PrevLogIndex < rf.lastSnapshotIndex ||
   (args.PrevLogIndex == rf.lastSnapshotIndex && args.PrevLogTerm != rf.lastSnapshotTerm) {
    // 不可能的情况, snapshot说明日志已提交, leader不可能没有已提交的日志
    logging("... ERROR PrevLogIndex %d < SnapshotIndex ...")
    return          // ← 这里没有 reply.IsSuccess = false
}
```

`reply.IsSuccess` 在函数开头被置为 **true**（:523），这个分支直接 return，于是返回给 leader 的是「**成功**」。

**后果链**（为什么它不是"只是少一行"）：

1. leader 收到 `success=true` → 走成功分支（:806 起）→ `nextIndex = PrevLogIndex + 1 + len(entries)`、`matchIndex` 前推。
2. 但 follower **一条日志都没追加**（它其实落后在快照点之后，需要的是 InstallSnapshot）。
3. leader 从此认为这个 follower 已同步，**再也不会给它发快照或回退 nextIndex**。
4. 更严重：`updateCommitIndexUnlocked` 把 `matchIndex` 当"已复制"的证据数多数派 —— 一旦这个假 matchIndex 参与计数，**可能提交只存在于少数派的日志**（Raft 安全性直接破防）。

**触发条件**：follower 的 `lastSnapshotIndex` 大于 leader 发来的 `PrevLogIndex`。作者注释的假设是「快照里的日志必已提交，leader 不可能没有已提交日志」——正常情况下成立，所以测试很难踩到。但这条假设一旦被打破（例如某节点从更新的 leader 那里装过快照、随后又与原 leader 恢复通信），错误会被**静默吞掉**，比 panic 难查得多。

**修法**：该分支加 `reply.IsSuccess = false`（并把 `LastLogIndex/LastLogTerm` 按快照点回填），让 leader 退到 `nextIndex = lastSnapshotIndex` 走快照路径（与 :877-884 那段回退逻辑一致）。

**这条的普适教训**：**「防御性/不可能分支」最容易漏返回值**。写完每个 `return` 都问一句「reply 的每个字段在此刻都正确吗」。同样的问题在 `RequestVote` 里也会出现（那里 `IsVoteGranted=false` 是初始值，方向相反所以天然安全）。

### 3.3 2C 持久化

只持久化三样：`currentTerm` / `votedFor` / `logs`（2D 后加 `lastSnapshotIndex/Term`）。**不持久化** `committedIndex` / `matchIndex`：重启后可凭日志 + 重新选举重建。

判据（比结论重要）：**「重启后能否凭剩余信息安全地推回来」** —— 推得回来就不必落盘。

`votedFor` 必须持久化是「崩溃恢复」形态里最致命的一条：忘了投过谁 → 同 term 投两票 → 双主。

### 3.4 2D 快照 ★（v2 新增：代码侧已有实现，这里是审查版）

**为什么需要**：日志无限增长 → 重启回放越来越慢、磁盘爆。快照把「状态本身」存盘，丢弃之前的日志。**日志从「只增」变成「可丢头部」**——2D 全部复杂度来自这一句。

**你的实现（四个部件）**：

1. **`Snapshot(index, snapshot)`（:248）**——service 说「我到 index 了，可以丢」。
   - `index <= lastSnapshotIndex` 直接返回（幂等）
   - **关键技巧**：`lastSnapshotTerm = logs[index - lastSnapshotIndex - 1].Term` —— 用**被丢弃的最后一条日志的 term** 作为快照的 term。快照数据里本身没有 term 信息，这条必须从日志里捞。这是 2D 最少见但最必要的一行（:258）。
   - 截断：`copy(newLog, logs[index-S:])` → 保留下来的 logs[0] 是**快照后第一条**。
2. **`CondInstallSnapshot`（:208）**——service 侧决定是否接受 leader 塞来的快照。**三条件拒收**：比已有快照旧 / 同 index 但 term 不同 / 不比 committedIndex 新。三条缺一都会让「旧快照覆盖新状态」。
3. **`InstallSnapshot` RPC（:665）**——follower 侧收到：term 检查 → step down → 重置选举定时器（**50ms，与普通心跳一致**）→ `LastSnapshotIndex < committedIndex` 则拒收 → **异步 goroutine 推 applyCh**（`SnapshotValid=true`，`CommandValid=false`）。
4. **leader 侧自动转快照（:758）**：`nextIndex[server] <= lastSnapshotIndex` 时改发 InstallSnapshot，否则正常发 AppendEntries。这一行是 2D 的核心判断——follower 落后到快照之前，日志已经没了，只能发快照。

**下标换算：2D 唯一的真难点**

```
                 lastSnapshotIndex = S
logs[0] 对应    index = S + 1
logs[i] 对应    index = S + 1 + i
index 转下标    i = index - S - 1        ← apply 循环用的就是这个（:1042）
末条 index      = S + len(logs)          ← Log()（:289）返回的也是这个
初始（无快照）  S = -1 → logs[i] 对应 index i，与 2A/2B 的"dummy 在 0"完全兼容
```

`S = -1` 这个初值（:996）是让 2C 的旧代码一行不改就能跑 2D 的关键 —— **用 -1 而不是 0，把「无快照」与「快照在 0」区分开**。C++ 版那套没做这件事（它的 dummy 直接占 index 0），将来加 2D 会疼。

**crash 恢复的巧招（:1001-1034）**：重启时若 `lastSnapshotIndex != -1`，就置 `committedIndex = S`、`lastAppliedIndex = -1`；applier 看到 -1 立刻推一条**假快照**（`SnapshotIndex: -1`，注释原话「crash恢复必须要应用snap」）给 service，让 service 自己重新装填状态机。**这是 2D 最优雅的一处**：不用给 service 加"启动"接口，用一条特殊消息表达了「请重装」。

**两个真实瑕疵**（不影响过测，但值得知道）：

1. `SaveStateAndSnapshot(ReadRaftState(), snapshot)` 之后再 `persist()`（:238-239、:267-268）—— **顺序反了**：第一次落盘写的是「**旧** raft state + **新** snapshot」。第一句用「旧 state + 新 snapshot」落盘，第二句再写新 state。若崩溃在两次写之间，会得到「state 落后但 snapshot 已新」的错配。正确顺序是先 `persist()` 再 `SaveStateAndSnapshot`（或一次原子写）。
2. `InstallSnapshot` 里 `args := &InstallSnapshotArgs{}`（:760）**遮蔽了外层 `args`** —— Go 的短声明在 `if` 块内新建变量，外层那份仍是 `AppendLogEntryArgs`。当前恰好能跑（内层作用域里用完），但这是「看起来在用同一个变量，其实不是」的经典陷阱。

### 3.5 锁与并发专题 ★

**决策一：单把大锁**

全部状态在 `rf.mu` 下。理由：raft 状态字段耦合极深（一个操作常同时碰 term/role/logs/nextIndex），细粒度锁的锁序设计成本远超收益；测试规模下竞争低；**正确性 > 性能**。

**决策二：锁内拷贝 → 锁外通信 → 回锁验证（三段式）**

```go
rf.Lock()
args := &...{所有参数从 rf 拷贝}   // 锁内快照
rf.Unlock()
ok := rf.peers[s].Call(...)        // 锁外：慢操作
rf.Lock(); defer rf.Unlock()
if rf.role != Leader { return }    // 回锁后重验：世界可能变了
```

**死锁原理**：锁内发 RPC，对方 handler 也要抢锁，网络一卡就全组死锁。**绝不在持锁时做慢操作** —— 这条可以搬到任何并发程序。

**回锁重验的普适律**：跨越任何阻塞点后，缓存的世界观一律作废。你 Go 版每一处 `if rf.role != Leader { return }`、C++ 版每一处 `if (state_ != NodeState::Leader || current_term_ != term) return;` 都是这条。

**决策三：轮询 ticker（Go）vs 双版本定时器（C++）**

- Go：`ticker()` 20ms 轮询两个 timer。代价是平均 10ms 唤醒延迟，收益是每轮天然重读状态、timer 换代检查极其直白。
- C++：写了两版 —— `RaftTimer`（cv + 单线程 + 每轮重算最近 deadline）与 `RaftTimerAsio`（asio steady_timer + async_wait）。**这本身就是一节并发课**：cv 版要自己维护「两个 deadline 取最小 + 谓词重算」，asio 版把「等待」交给 io_context。最新提交叫 restore asio timer，但 `raft_node.hpp` 仍用 `RaftTimer`（cv 版）—— 切换没做完（§7.4 缺陷 2）。

**决策四：apply 的生产者-消费者**

协议层只推 `committedIndex`（生产），applier 只读 `committedIndex > lastAppliedIndex`（消费）。408 的「缓冲区」从一个环形数组变成「两个下标之间的日志区间」。Go 用 `chan ApplyMsg`，C++ 用 `LockFreeQueue<std::string>` + KVServer 侧再起一个消费线程 —— **同一条语义，两种原语**（已归档 `os/02-03-同步与互斥.md`）。

### 3.6 调试兵器

| 兵器 | 用法 |
|---|---|
| `src/raft/test.sh` | `while true` 循环跑 2A/2B/2C `-race`，失败即停（master 里 37 行，2D 时扩充过） |
| `-race` | 必开；raft 的数据竞争几乎必然表现为随机失败 |
| `logging()` + 角色前缀 | `[leader]/[candidate]/[follower] [&-id T:term]` |
| `tmp` / `tmp1` | 1.1MB / 318KB 调试日志遗存（在 craft 分支工作区） |
| 测试超时口径 | `RaftElectionTimeout = 1000ms`，比论文宽 4 倍 → 你的 250–500ms 留了 2 倍裕度 |

---

## 4 Lab1 MapReduce（未做 · 提纲）

- `coordinator.go`：任务表（nMap + nReduce）、RPC（要任务 / 交任务）、10s 超时重派、`Done()`
- `worker.go`：循环「要任务 → map（输出 `mr-X-Y`，`ihash(key) % nReduce`）或 reduce（读所有 `mr-*-Y`、排序、输出 `mr-out-Y`）→ 汇报」

**四个易错点**：① 输出必须「写临时文件 + rename」原子提交；② 超时重派后旧 worker 也会写完 → 靠原子提交兜底；③ worker 需要从 reply 拿到 nReduce；④ `Done()` 为真后 RPC server 要再活一会儿。

**408**：并行 vs 并发、纯消息传递（RPC）vs 共享内存 + P/V。

---

## 5 Lab3 kvraft（已有实现 · 审查版）

> 实读 `src/kvraft/server.go`（284 行）+ `client.go`（66 行）。**你写完了，且主体思路正确**，下面先讲结构，再讲三处该改的地方。

### 5.1 实现结构

```
Op{OpType, Key, Value, ClientId, SeqNum}       // Op 自带去重键
KVServer{ db map[string]string                  // 状态机
          seqMap map[int64]int64                // 每 client 已执行的最大 SeqNum
          resultMap map[int64]OpResult }        // 每 client 最近一次结果（供重试直接返回）
Clerk{ clientId = nrand(), seqNum 每次请求 +1 }
```

- **Put/Append/Get 全部走 `rf.Start(Op)`**（:82、:129）—— 线性一致读的正确姿势。
- apply 循环（:209-282）：`SeqNum <= seqMap[ClientId]` 就跳过（**恰好一次**的核心），否则执行 Put/Append/Get，更新 `seqMap` 与 `resultMap`；`maxraftstate` 超限就 labgob 编码三张表 → `rf.Snapshot`。
- `SnapshotValid` 分支：`CondInstallSnapshot` 通过后反序列化回三张表。
- client 侧：`clientId` 随机、`seqNum` 单调，失败就换 server 重试（标准做法）。

### 5.2 审查结论：一条真 bug、两处瑕疵、一条我上次判错了

**① 快照反序列化不检查错误（真 bug，最该修）**

```go
r := bytes.NewBuffer(msg.Snapshot)
d := labgob.NewDecoder(r)
d.Decode(&kv.db)          // ← 三个 Decode 都不看返回值
d.Decode(&kv.seqMap)
d.Decode(&kv.resultMap)
```

`Decode` 失败时返回 error 且**目标变量可能被置空或只填一半**，代码继续跑。表现在运维上是「重启后数据凭空少了一部分」，在测试里则很难复现（因为快照总是自己刚编的）。修法：三个 `if err := d.Decode(...); err != nil { panic/拒绝安装 }`，并且**先解到临时变量、全部成功后再一次性替换**（避免半填状态机）。

**② snapshot 判定与编码不在同一临界区（瑕疵）**

```go
if kv.maxraftstate != -1 && persister.RaftStateSize() >= kv.maxraftstate {   // 判定（锁外）
    ...
    kv.mu.Lock(); e.Encode(kv.db); ...; kv.mu.Unlock()                        // 编码（锁内）
    kv.rf.Snapshot(msg.CommandIndex, data)
}
```

`RaftStateSize()` 是锁外读的，到真正编码之间状态可能已变。后果只是「快照点与实际状态差一条」，不会错乱（因为 Snapshot 的 index 是 `msg.CommandIndex`），但属于「判定与使用分离」。另外 `Encode` 三张表的顺序必须与 `Decode` 严格一致——**这一点你做到了**（db/seqMap/resultMap），而 raft 侧的 `persist` 也是同样纪律。

**③ 我上次判错的一条：`Get` 入口读缓存不是「脑裂读」**

上一版我把它写成「旧 leader 返回旧值 → 违反线性一致」。**这个判断是错的**，原因在 client 侧：

```go
atomic.AddInt64(&ck.seqNum, 1)   // client.go：每次新请求都 +1
args.SeqNum = ck.seqNum
for { ... 重试同一份 args ... }   // 只有重试时 seqNum 不变
```

于是 `resultMap[clientId].SeqNum == args.SeqNum` **只可能在同一逻辑请求的重试时命中**。而「同一操作的重复投递返回相同结果」正是线性一致**允许**的（操作的真实生效点在第一次 apply 时，仍在第二次调用的 invocation 之前）。所以它是**正确的幂等优化**，不是 bug。

顺带说清一个对照：**用 `(ClientId, SeqNum)` 匹配比用 `index` 匹配更安全**——换主后同 index 指向的是另一条命令，而 SeqNum 全局唯一。你这里选对了。

**④ 真正会让人误判的地方（保留提醒）**

`kv.rf.Start(Op)` 之后如果本节点下台，该命令可能被新 leader 在**不同 index** 上 apply；由于你按 SeqNum 匹配，仍能正确拿到结果。但如果哪天改成 index 匹配（很多教程这么写），就必须加 `term` 校验，否则会返回别人的结果。

### 5.3 与「标准解」的差异（知道就行，不必改）

| 你 | 常见标准解 | 影响 |
|---|---|---|
| 轮询 resultMap 等结果 | per-index channel 或 cond | 多耗 CPU，但实现短 |
| `resultMap` 只留每 client 最后一条 | 一样 | 等价 |
| 超时 500ms | 无超时（靠 client 重试） | 更快失败，更容易触发缺陷 ① |

### 5.4 数据库设计视角

`db + seqMap + resultMap` 三张表就是**最小可用的分布式 KV**：状态机 + 会话去重表 + 结果缓存。真实系统里对应：状态机（RocksDB）、Percolator 的 `client_id` 去重、TiKV 的 ReadIndex 缓存。**你手搓的这套「恰好一次」，是分布式数据库最难也最容易被忽略的一节。**

---

## 6 Lab4 shardkv（复制版起步 · 现状与清单）

### 6.1 现状：这不是 shardkv，是「kvraft 去掉 resultMap」

实读 `src/shardkv/server.go`（220 行）+ `client.go`：

| 项 | 状态 |
|---|---|
| `config`（分片归属） | **无** |
| shardctrler 配置拉取循环 | **无**（`kv.ctrlers` 只存着没用） |
| 分片状态机（Serving/Pulling） | **无** |
| 跨组迁移（DataPull RPC） | **无** |
| `db / seqMap` | 有（全局一份，未按 shard 切） |
| 编译 | **仍不过**（实测 `go build ./shardkv/`）：`common.go` 的 `GetArgs`/`PutAppendArgs` 缺 `ClientId`/`SeqNum` 字段（4 处）、包里没有 `DPrintf`（1 处）——像是只搬了 server.go 没搬 common.go 的字段 |

所以 Lab4 的真实进度 = **「把 Lab3 的壳抄过来，删掉 resultMap，然后停手」**（那组改动里 +121 行）。

### 6.2 要补齐的清单（做的时候按序）

1. **修编译**（1 行 import + 1 个 `:=`）
2. **拉配置**：`shardctrler.MakeClerk(ctrlers)` + 后台循环 Query，config num 前进才动作
3. **按键路由**：`shard = key2shard(key)`；不属于本组的 shard 一律回 `ErrWrongGroup`
4. **分片状态机**：`Serving → Pulling → Serving`，中间态拒绝读写
5. **迁移**：向旧组发 Migrate/Pull RPC，**把 db 切片 + seqMap 切片 + config num 一起搬**（去重表必须跟着分片走）
6. **快照**：把 config num + 各分片状态一起编进去（否则重启后不知道自己在哪个配置）

### 6.3 三个必知的坑

1. 迁移期间该分片**既不能服务新请求，也不能丢旧请求**
2. 去重表跟分片走（漏了 → 重试导致重复执行）
3. 拉数据时旧组可能同时在拉新配置 → 用 config num 比较裁决

### 6.4 「配置也是日志」的设计理念

shardctrler 自己也是一个 raft 组：**控制面变更走共识**，就不会出现「一半节点看到新配置一半看到旧配置」。这是把 raft 的「日志一致」从数据面推广到控制面 —— 与 etcd 的「一切皆 revision」同源。

---

## 7 C++ craft 重写线（v2 全部重写）

### 7.1 先纠正一个前提

`raft/cpp/craft/`（61 行、`Craft::` 类名错、proto 缺 AppendEntries 消息、编译不过）是 **2026-03 的废弃骨架**，只在 `craft` 分支上，master 分支没有它。
真正的成果是 **`raft/craft/`**：原独立仓 `git@gitee.com:we_we_we/craft.git`（3 提交），**合并进本仓并定稿为 craft v1.0**（tag `craft-v1.0`），独立仓停更。1729 行，**能编译、能跑 3 节点 demo**。

### 7.2 架构：分层比 Go 版更像真实系统

```
craft/                            ← craft v1.0（tag craft-v1.0）+ 集群测试能力
├── proto/raft.proto            三个 RPC 全定义（含 InstallSnapshot）
├── proto/config.proto          集群配置（.conf 用 text format 写）
├── conf/node{1,2,3}.conf       3 节点单机配置，开箱可跑
├── include/craft/
│   ├── raft/                   raft_node.hpp / raft_timer.hpp / raft_timer_asio.hpp
│   │                           lockfree_queue.hpp / storage.h(遗留)
│   ├── config/config_loader.hpp  .conf → GroupConfig
│   ├── kvserver/kvserver.hpp   1:1 包一个 RaftNode
│   └── controller/             group_config.hpp（分片↔组）+ grpc_inject.hpp（故障注入）
│                               controller.hpp（0 行，未写）
├── src/raft/{node,raft_timer,raft_timer_asio,storage}.cpp
├── src/main.cpp                单进程 3 节点 demo
├── tests/{unit,system}
└── scripts/{gen_proto,netem_on,netem_off,run_system_tests}.sh
```

**两个设计决定值得单独说**：

1. **`NodeConfig.group_id` + `GroupConfig`（shard_to_group / groups / group_fault_configs）** —— 一开始就是按 **Lab4 多组**设计的，不是单组 raft。`RaftNode` 构造时按自己的 `group_id` 挑出同组 peer（node.cpp:28），故障配置也按组取。**这是 Go 版没有的抽象**。
2. **`FaultInjector` 替代 labrpc** —— Go 靠 labrpc 内置丢包，C++ 用 gRPC 真网络，于是自己写了一套：`drop_rate`（伯努利）、`min/max_delay_ms`、`target_methods`（只打某类 RPC）、`target_nodes`（只打某节点）、`partitions`（**按分区号：`partitions[src] != partitions[dst]` 就丢**）。配合 `scripts/netem_on.sh`（Linux `tc netem` 真链路延迟/丢包）。**「没有 labrpc 怎么办」这个最大障碍，你已经解决了。**

### 7.3 与 Go 版逐项对照（这张表本身就值一节课）

| 概念 | Go（master 1139 行） | C++ craft（node.cpp 465 行） | 迁移的本质 |
|---|---|---|---|
| 并发单元 | goroutine（M:N 协程，阻塞不占线程） | `std::thread`（1:1 内核线程） | 有栈协程 vs 内核线程；Go 随手 `go func`，C++ 必须算线程成本 |
| 每次广播 | 每 peer 一个 goroutine，**不等待** | 每 peer 一个 `std::thread` 然后**全部 join**（node.cpp:291-321） | 「多发并发、单个完成」→「同步等一轮」：更直白，但每次心跳创建 N-1 个线程 |
| 锁 | `sync.Mutex` + defer | `std::mutex` + `lock_guard`（RAII） | C++ 必须 RAII 才能在异常路径解锁 |
| 等待/通知 | channel | `condition_variable` + 谓词 / `LockFreeQueue` | channel = 队列+唤醒；cv 只是唤醒，队列要自己维护 |
| 定时器 | `time.Timer` + 20ms 轮询 ticker | **两版**：cv 单线程（重算最近 deadline）/ asio `steady_timer + async_wait` | 轮询→事件驱动；cv 版要自己处理「两个 deadline 取最小」 |
| RPC | labrpc（进程内，自带故障） | gRPC（真网络）+ `FaultInjector` + `netem` | 真网络：deadline（两处都 200ms）、keepalive、端口都要自己管 |
| 序列化 | labgob（反射） | protobuf（`.proto` 显式） | C++ 要先写 proto 再生成；proto 不全编译不过 |
| 持久化 | persister（内存模拟） | **没有**（`InMemoryLog` 未接入） | 2C 在 C++ 版是空缺 |
| 提交推进 | 遍历 matchIndex 数过半 | `updateCommitIndexUnlocked`（node.cpp:443）从尾往前找**当前 term** 的第一条 | 同一策略，写法不同 |

**最值钱的一行**：`startElection` 里 `std::atomic<std::size_t> votes_granted{1}` + `atomic<bool> won_election` 的 CAS（:287-308）。Go 版用锁 + 局部变量就够，C++ 版必须显式表达「谁先到多数派谁赢、只赢一次」——**这就是原子操作在真实协议里的用途**，比背 CAS 定义强。

### 7.4 待修点（实读发现，按严重度排）

| # | 位置 | 问题 | 影响 |
|---|---|---|---|
| 1 | `InstallSnapshot`（node.cpp:206） | **空实现**，只回 term | 2D 在 C++ 侧完全没做；落后 follower 永远追不上（**2C 已在下面补掉，2D 仍未做**） |
| 2 | `raft_node.hpp:113` | 用 `RaftTimer`（cv 版），但最新提交是 "restore boost asio timer" | **切换没做完**：asio 实现存在却没人用 |
| 3 | `lockfree_queue.hpp` | Michael-Scott 队列的**单消费者简化版**：`Dequeue` 无 CAS 循环、`delete old_head` 无内存回收（ABA / use-after-free） | 单生产单消费（applyLoop → KVServer）勉强安全；加第二个消费者立刻崩 |
| 4 | `kvserver.hpp:73` | `apply()` 只 `std::cout` 打印，**没有 `map` 状态机、没有去重表** | Lab3 语义层在 C++ 侧还是空的 |
| 5 | `kvserver.hpp:83` | `Dequeue(cmd)` 后用 `cmd.empty()` 判断「没数据」 | **空命令是合法命令**，会被当无数据 sleep 掉 |
| 6 | `raft_timer.hpp:110-128` | `ResetElectionTimer(timeout)` **忽略参数**，内部固定 `rand()%150+150`；`(void)timeout` | 调用方传 300ms 实际是 150–300ms；接口撒谎 |
| 7 | `storage.h` / `tests/unit` | `InMemoryLog` 没被 `RaftNode` 使用（node 用自己的 `vector<LogEntry>`），但单测只测它 | **测试测的是死代码**，raft 内核零测试覆盖 |
| 8 | `kvserver.hpp:29` | 把 `config.node_address` 传给 `NodeConfig.listen_address` 字段，而 `initPeers` 又用 `node_address` 建 channel | 两个地址字段语义混乱；扩到多进程/多机就会踩 |
| 9 | `fault_injector` | **v1.0 时是死代码**：只在构造里初始化，`sendRequestVote`/`sendAppendEntries` 从未调用它 | **已接上**：两个 RPC 出口都接上 `ShouldDrop` / `MaybeDelay`，配置里的 `drop_rate`/`delay_*`/`partition` 真正生效（实测见 §7.5.1） |

**环境事实（实测更新）**：`build.sh` 里 `cd /home/wzy/develop/craft` 是 Linux/WSL 时期的脚本，但 **macOS（Apple Silicon + brew grpc 1.78.1 / protobuf 34 / boost 1.90 / cmake 4.2.3）现在能编能跑**，已实测 3 节点选主 + 5 条命令三副本 apply。为此修了三处：

| 坑 | 现象 | 修法 |
|---|---|---|
| Boost 组件 | `Could not find boost_systemConfig.cmake` | Boost.System 自 1.70 起 header-only → `find_package(Boost)` + 退化到 `Boost::headers` |
| grpc 插件路径 | 写死 `/usr/bin/grpc_cpp_plugin` | `find_program(... HINTS /usr/bin /usr/local/bin /opt/homebrew/bin)` |
| **protobuf 双版本** | 编译过、**一启动 SIGSEGV，崩溃点在 `main` 之前**（dyld 静态初始化） | brew 的 grpc 依赖 `protobuf@33`，`find_package(Protobuf)` 却给 34 → 两份 protobuf 各初始化一次全局 DescriptorPool。必须 `-DProtobuf_DIR=/opt/homebrew/opt/protobuf@33/lib/cmake/protobuf` 显式统一 |

另：`raft_timer_asio.cpp` 用了 `boost::asio::io_context::work`（1.66 起废弃、**1.90 已移除**），而 `raft_node` 用的是 cv 版 `RaftTimer` —— 所以 CMake 默认**不编译**它（`-DCPPRAFT_BUILD_ASIO_TIMER=ON` 才编译）。这也说明 §7.4 缺陷 2「asio/cv 切换没做完」比原先判断更严重：那版 asio 代码在新 Boost 上根本编译不过。

### 7.5 构建与测试

```bash
cmake -S . -B build -DCPPRAFT_BUILD_TESTS=ON   # 需 C++20 + protobuf + gRPC + Boost::system
cmake --build build -j
./build/cppraftd                                 # 3 节点 demo，投 5 条 set 命令
cmake --build build --target unit-tests          # 只有 2 个 storage 测试
./scripts/run_system_tests.sh                    # pytest：只断言 binary 存在
```

**故障注入两种**：

```bash
# 1) RPC 层（进程内，确定性）——目标设计，见 §7.4 缺陷 9
export CRAFT_RPC_DROP_RATE=0.15
export CRAFT_RPC_DELAY_MIN_MS=20 CRAFT_RPC_DELAY_MAX_MS=120
export CRAFT_RPC_TARGET_METHODS=AppendEntries CRAFT_RPC_TARGET_SOURCE_IDS=1

# 2) 内核层（真链路，Linux）
sudo ./scripts/netem_on.sh lo 100 30 10   # delay 100ms jitter 30ms loss 10%
```

### 7.5.1 实测：三进程集群 / 丢包 / 分区

改造后同一份二进制可以起 3 个进程，`scripts/run_cluster.sh` 负责等端口、跑一轮、汇总统计。

| 场景 | 造法 | 实测 |
|---|---|---|
| 正常 | 默认 `conf/` | node3 当 leader，3 条命令，**三节点各 applied=3，errors=0** |
| 20% 丢包 | `fault { drop_rate: 0.2 }` | **发生换主**（node1 投 3 条、node2 再投 3 条），6 条命令**三副本全 apply**，errors=0 |
| 网络分区 `{1,2} \| {3}` | node3 的 `partition: 1` | `{1,2}` 侧正常服务（applied=2），**隔离的 node3 applied=0**，errors=0 |

**这三行就是 raft 该有的样子**：丢包下靠随机超时重新选主、但不丢命令；分区时少数派不服务、多数派继续。

过程中踩到两个真问题（都已修）：

1. **gRPC 走 HTTP 代理**：环境里有 `HTTP_PROXY` 时，gRPC 连 `127.0.0.1` 也走代理 → `http_connect_handshaker ... 502`，选举直接失败。修法：`args.SetInt(GRPC_ARG_ENABLE_HTTP_PROXY, 0)`。
2. **`BuildAndStart()` 返回 nullptr 不检查**：端口被占用时表现为「进程活着但没人能连」。修法：抛异常（`failed to listen on ...`）。
3. 另：`listen_address` 与 `node_address` 语义混乱（KVServer 把 `node_address` 传给 bind 字段）→ 已改为 `listen` 管 bind、`peers[].addr` 管 dial。

### 7.5.2 容器集群：五个场景实测，以及 S5 挖出来的真问题

`Dockerfile` + `docker-compose.yml`（3 容器、固定 IP `10.5.0.11-13`、`NET_ADMIN`）+ `scripts/{docker_cluster,inject_fault}.sh`。
镜像 Ubuntu 22.04 多阶段构建，首次约 20 秒；每个容器能在自己网卡上 `tc`/`iptables`，**故障只影响目标节点**。

| # | 场景 | 实测 |
|---|---|---|
| S1 | 正常 | node1 leader，三节点 `applied=3`，errors=0 |
| S2 | node2 加 20ms 延迟 + 5ms 抖动 | 6 秒内 `applied` 22→40，**node2 仍跟得上** |
| S3 | `network disconnect node2`（真分区） | {1,3} 继续，**node2 停在 56**；`heal` 后 10 秒内**追到 119** |
| S4 | `kill` 当时 leader（node1） | node2 接任（proposed 0→12），两个存活节点 `applied=155` 同步 |
| S5 | `restart` 崩掉的 node1 | ⚠️ **node1 applied=343，另两个 205/206** |

**S5 是这轮最有价值的发现**：craft 没有持久化，重启后 `term=0`、`logs` 为空，只能被 leader 从头灌。于是：

1. **状态机被重复 apply** —— 这次命令是 `set`（幂等）所以没炸；换成 `append` 就是重复追加。
2. **`votedFor` 丢失** —— 同一 term 可能给两个 candidate 投票，**Raft 选举安全的前提被打破**。
3. 已提交日志在本地消失，全靠 leader 重发（leader 也挂就真丢）。

对比 Go 版：`raft.go` 里 `persist()` 在 5 个落点都调了，2C 是过测的。**C++ 版这一块完全空缺**（`storage.h` 的 `InMemoryLog` 甚至没被 `RaftNode` 使用）。

⇒ 这给出了 v1.1 的**验收标准**：`restart` 之后 `applied` 不应超过真实命令数；`term` 不应回退；`votedFor` 落盘。

### 7.5.3 2C 持久化：做完并实测

v1.0 的 S5 暴露了「无持久化」：重启节点 `applied=343` vs 另两个 205/206，全部历史日志被重放。补上后：

**存什么**（对照论文 Figure 2 的 persistent state）：`currentTerm` / `votedFor` / `logs`。
**不存**：`commitIndex` / `lastApplied` / `nextIndex` / `matchIndex` —— 前两个可由「日志 + 重新选举」重建，后两个只有 leader 用。
判据仍是那句话：**重启后能否凭剩余信息安全地推回来**。

**实现三件套**：

1. `proto/persist.proto`：`PersistentState{term, voted_for, repeated PersistentEntry}`（protobuf 二进制存储）
2. `RaftStorage`（`storage.h/cpp`）：`临时文件 → fsync → rename → fsync(dir)`。
   直接覆盖写会在崩在中途时截断文件 → 重启解析失败变成空节点；`rename` 同文件系统原子；**目录 fsync 才能保证 rename 落地**（常见漏项）。
3. 5 个落点（与 Go 版一一对应）：`OnElectionTimeout` / `RequestVote` 投票后 / `AppendEntries` 日志变更后（`log_changed` 标记，**纯心跳不落盘**）/ `becomeFollower` / `StartOp`（**先落盘再宣称已接收**）。

**三轮对照实测**（本机三进程，每轮各投 5 条）：

| 轮次 | 数据目录 | 每节点 applied | 解读 |
|---|---|---|---|
| 1 | 全新 | 5 | 投 5 条 |
| 2 | **保留** | **10** | 5 重放历史 + 5 新命令 ✅ |
| 3 | 清空（对照） | 5 | 0 历史 + 5 新命令 |

容器侧（`down` 保留 volume → `up`）：保留数据时重启**首条 apply 是上一轮的 `set k3-0`**；`down --purge` 后首条是本轮新命令。

**⚠️ 顺带纠正一个错误判断**：我在 §7.5.2 里写的验收标准「restart 后 applied 不应超过真实命令数」是**错的**。
状态机（KV map）在内存，重启必须重放全部已提交日志才能重建状态 —— 除非有快照（2D）。**持久化不会减少 apply 次数**，它的价值是三件事：

1. `term` 不回退（否则可能给旧 term 的 candidate 投票）
2. `votedFor` 不丢（否则同 term 可投两票 = 双主）
3. 日志不依赖 leader 重发（leader 也挂了数据还在）

正确的验收是「重启后日志内容还在、term 延续」。

**已知代价**：`persist()` 在 `mutex_` 内做全量重写 + fsync。几十条日志没问题，生产上这是瓶颈 —— 正解是 WAL 追加 + group commit + 定期 compaction。这也是 Raft 工程实现里最重的一块，比协议本身难。

### 7.6 续写关键路径（如果走"重"路线）

```
① 修 7.4 的 5/6 两处小 bug（1h）→ 让行为可预期
② 给 raft 内核加单测（3-4h）：选举状态机 / 日志截断 / 提交推进，不需要网络
③ 接故障注入（2h）：把 FaultInjector 接进 sendRequestVote / sendAppendEntries 的出口
④ 补 InstallSnapshot（4-6h）+ storage 落盘（4h，2C）
⑤ kvserver 状态机 + 去重表（6h）→ 等价于 Lab3
⑥ controller（shardctrler + 迁移）（15h+）→ 等价于 Lab4
```

**取舍建议**：①+② 约 5h，收益最大（把「能跑的 demo」变成「可验证的实现」）；③ 是 C++ 侧独有的乐趣（真能 ping 出丢包下的选举）；④–⑥ 是 30h+ 的工程，**初试前不要碰**。

---

## 8 与 408 的对接

| 内容 | 408 章节 | 用法 |
|---|---|---|
| Raft 大锁 / 三段式 / 回锁重验 | **12-同步与互斥** | 学 P/V 时回来看「互斥锁工程形态」 |
| applyCh / LockFreeQueue 的生产者-消费者 | **12-同步与互斥** | 408 的环形缓冲区 ↔ 两个下标之间的日志区间 |
| goroutine vs std::thread | **10-进程与线程** | 用户级线程 vs 内核级线程的天然对照组 |
| kvraft 三张表 | 12 + **21-查找与排序** | 散列表的工业用途 |
| shardkv 分片 | （无直接考点） | 复试/面试素材 |

**定位**：408 不考分布式。这条线的价值 = **12 章的工程锚点**（背 P/V 不如有真实代码画面）+ **复试硬通货**（自研 raft 的候选人极稀缺）。

---

## 9 动手顺序与判据

按"收益/成本"排序，每一步都带判据；没有判据的步骤不做。

| 顺序 | 事项 | 判据 |
|---|---|---|
| 1 | 把 Raft 的三段式（大锁 → 状态快照 → 回锁验任期）讲成一段话 | 能说清"为什么必须在回锁后重新检查 term"，并举一个不检查就会错的交错 |
| 2 | 快照与 InstallSnapshot 的数据流 | 能画出"日志被截断后，落后的 peer 靠哪条路径追上"，并说明 `lastIncludedIndex` 在两条路径上的含义 |
| 3 | kvraft 的去重表（ClientId + SeqNum） | 能解释"为什么只靠 term 去重会重放"，并给出重复提交的触发序列 |
| 4 | shardkv 的分片与迁移 | 能说清"配置变更期间请求应该在哪个时刻被拒绝/重定向" |
| 5 | C++ 侧的线程模型（每 peer 一线程 + join） | 能指出共享状态在哪、为什么原子计数必须用在这里 |

**纪律**：Lab4 这类工程量大、且与"讲清共识"关系较弱的部分，只读设计不改代码——先把 1–4 的判据拿到手。

---

## 10 检查清单

- [ ] 引用任何一处实现前，先确认它在哪个分支/版本——**分支不对，事实全错**
- [ ] 每条结论后面有判据：哪个测试类、哪条日志、哪段交错序列
- [ ] `-race` 跑过至少一轮（数据竞争在单线程测试里不暴露）
- [ ] 能画出一次选举 + 一次追加日志的完整时序，含任期变化
- [ ] 能解释快照两条路径（本地截断 / 落后追赶）各自的边界条件
- [ ] 不把"能跑通 demo"当成"实现了共识"——线性一致性要单独论证

---
