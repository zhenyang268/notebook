# 6.824 · 一小时上手

> **前提**：会 Go 的 goroutine 与 mutex；知道"多数派"是什么。
> **这一小时的产出**：一个能选出 leader 的最小 Raft（约 150 行）。
> **不碰**：日志复制、持久化、快照。

---

## 1 这一小时只做一件事

**让三个节点中有一个成为 leader，并在它挂掉后重新选出。**

因为 leader 选举是 Raft 的**全部骨架**——日志复制只是"leader 说了算"，快照只是"日志太长"，持久化只是"重启别忘"。**选举通了，剩下都是加字段。**

---

## 2 最小可跑（50 分钟）

### 2.1 状态（10 分钟）

```go
type Raft struct {
    mu        sync.Mutex
    peers     []*labrpc.ClientEnd
    me        int
    currentTerm int
    votedFor  int          // -1 表示没投
    state     int          // Follower / Candidate / Leader
    electionTimer time.Time
}
```

**三个字段就能撑起选举**：`currentTerm`（谁新）、`votedFor`（一任只投一次）、`state`。

### 2.2 三个动作（30 分钟）

**动作一：心跳（leader → follower）**
```go
// leader 每 100ms 发一次，term 低于自己的直接无视
go func() {
    for {
        time.Sleep(100 * time.Millisecond)
        if s.state == Leader {
            for i := range s.peers {
                if i != s.me { go s.sendAppendEntries(i) }
            }
        }
    }
}()
```

**动作二：超时变候选（follower）**
```go
// 每次收到心跳就重置 timer；超时则 term++ 并拉票
if time.Since(s.electionTimer) > randomTimeout(300, 600) {
    s.state = Candidate
    s.currentTerm++
    s.votedFor = s.me
    go s.startElection()
}
```

**动作三：投票（收到 RequestVote）**
```go
// 只有 term 更新 + 没投过 才投
if args.Term > s.currentTerm {
    s.currentTerm = args.Term
    s.votedFor = -1
    s.state = Follower
}
if args.Term == s.currentTerm && (s.votedFor == -1 || s.votedFor == args.CandidateId) {
    s.votedFor = args.CandidateId
    reply.VoteGranted = true
    s.electionTimer = time.Now()   // 投票后重置，避免立刻又选
}
```

### 2.3 验证（10 分钟）

用 `labrpc` 的 `network` 起 3 个节点，跑 5 秒：
```
预期：稳定后有且仅有一个 leader；杀掉它，1 秒内出现新 leader
```

---

## 3 三个核心难点

### 3.1 随机超时是防"平票"的唯一手段

如果所有 follower 超时时间相同，它们会**同时**变候选、同时拉票，各得一票，无限循环。
**随机化把"同时"打散**，让某个节点先发制人。

### 3.2 term 只增不减，且必须持久化

`currentTerm` 回退会导致"旧 leader 复活"。所以**收到更大 term 必须立刻更新并变 follower**，
且 `currentTerm` 与 `votedFor` **必须落盘**（M3 的事，但字段现在就要有）。

### 3.3 投票后要重置 timer

否则刚投完票就超时，又发起选举，形成活锁。

---

## 4 卡住怎么办

| 现象 | 原因 | 修法 |
|---|---|---|
| 一直选不出 leader | 随机超时范围太小 | 改成 300–600ms |
| 两个 leader 同时存在 | 投票没检查 term | 先比 term 再比 votedFor |
| 选出来后立刻又选 | 投票后没重置 timer | 投票成功路径加 `electionTimer = now()` |
| 测试偶尔挂 | 没加锁 | 所有读写 `currentTerm`/`state` 都加 `mu` |

**分布式调试方法**：打印**(节点, term, state, 事件)**四元组，按时间排序看。**不要只看单个节点**。

---

## 5 这一小时之后

- 通了 → 加 `AppendEntries`（M2），把"leader 说了算"变成真日志。
- 没通 → 先在**单节点**上跑通"变 leader"，再加第二、第三个节点。

## 6 通向

| 你要什么 | 去哪 |
|---|---|
| 完整里程碑 | `OUTLINE.md` |
| 详细实验记录 | `NOTES.md` |
| OS 的 PV 与互斥 | `exam/408/os/ROADMAP.md` |