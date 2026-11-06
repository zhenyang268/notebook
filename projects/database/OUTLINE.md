## 一、它解决什么问题

这项能力处理的是“数据在并发和崩溃两种压力下还能不能自洽”的问题。它在真实工程里通常以三类事故的形式出现。

**场景 A：慢查询引发级联故障。** 订单表约 2000 万行，接口跑 `SELECT id FROM orders WHERE user_id = ? AND status = 0 ORDER BY created_at DESC LIMIT 20`。表上只有主键和一个 `(status)` 单列索引。当 `status = 0` 覆盖约六成行时，优化器仍可能选它：扫描上千万行、逐行回表、再 filesort，单次查询从毫秒级掉到秒级；QPS 一上来连接池被打满，故障沿调用链向上放大。这里要问的是：能否读懂 `EXPLAIN` 的 `type` / `key` / `rows` / `Extra`，能否判断选择率，是否知道联合索引最左前缀和覆盖索引。

**场景 B：并发下的一致性缺口。** 库存余量为 1，RC 隔离下两个会话都 `SELECT qty` 读到 1，都判定可扣，于是出现负库存或对账差异。另一类是“写完立刻读从库”：写入主库成功，读请求落到延迟几百毫秒到数秒的从库（按复制方式与回放线程数而定），用户看到“提交成功但列表没变”。这里要问的是：快照读与当前读的边界、隔离级别的选择代价、行锁与间隙锁的作用域、主从延迟下怎么做到读己之写。

**场景 C：崩溃后的不一致。** 进程被 `kill -9` 后重启，redo 前滚已提交的页、undo 回滚未提交事务，而 redo 与 binlog 之间的内部两阶段提交，决定从库会不会多一条或少一条记录。

对应的面试题几乎是同一批：为什么是 B+ 树而不是 B 树或哈希、回表和覆盖索引、RR 到底防不防幻读、MVCC 快照何时创建、间隙锁锁什么、redo 与 binlog 为什么需要两阶段提交、主从延迟怎么发现。

**入口（本文的读法）**：把问题落在 InnoDB 可观测对象上：B+ 树索引页的 LSN、EXPLAIN 的 type/key/rows/Extra、MVCC ReadView 的 m_ids/min_trx_id/max_trx_id、undo 版本链的 trx_id、锁结构 record/gap/next-key、redo record 的 space_id/page_no/offset、binlog event 的 GTID/position、relay log SQL thread 回放位点；据此判断并发读改写与崩溃恢复是否自洽。换的是访问路径（联合索引最左前缀、覆盖索引、回表、filesort）、隔离级别（RC/RR/ReadView 创建时机）、提交协议（redo prepare→binlog fsync→redo commit、sync_binlog、innodb_flush_log_at_trx_commit）、复制策略（异步/半同步、并行回放、GTID 等待、读己之写走主库）。

**不换的是什么**：全程不变的是 B+ 树 page 的 LSN、undo log 的 trx_id 版本链、ReadView 的 m_ids/min_trx_id/max_trx_id、redo record 的 space_id/page_no/offset、binlog event 的 GTID/position 与 relay log 回放位点；看到差异先按顺序问：EXPLAIN 的 key/rows/Extra 是否走覆盖索引或 filesort，当前读是否带 FOR UPDATE/LOCK IN SHARE MODE，隔离级别是否 RC/RR 以及 ReadView 创建时机，锁范围是否 record/gap/next-key，提交是否完成 redo prepare→binlog fsync→redo commit，从库是否满足 GTID 已执行或 Seconds_Behind_Master=0。

## 二、为什么这样做（方法论设计）

**有口径才算数。** “加了索引变快了”不算结论，能证伪的表述是：同一 SQL 优化前后 `EXPLAIN` 的 `rows` 估计、`Extra` 里 `Using filesort` / `Using index` / `Using index condition` 的变化，以及 `Handler_read_next`、`Handler_read_rnd_next` 这类逻辑读计数的差值。事务侧的口径是 `information_schema.INNODB_TRX` 里的事务年龄、`SHOW ENGINE INNODB STATUS` 的 `LATEST DETECTED DEADLOCK` 段、`DATA_LOCK_WAITS`（视图名随版本而异，按实现而定）。复制侧的口径是 GTID gap 与回放线程状态，而不是只看 `Seconds_Behind_Master`。

**看起来专业但无法证伪的说法要剔除。** “我们用了 MVCC 所以读不加锁”——当前读照样加锁。“B+ 树三层能存两千万行”——不给页大小、主键长度、行宽就是口号。可证伪的写法是给公式：扇出 $\text{fanout}=\left\lfloor \dfrac{P}{K+p} \right\rfloor$（$P$ 页大小、$K$ 键长、$p$ 指针长），三层容量约为 $\text{fanout}^2 \times \text{leaf\_rows}$，具体数值按实现而定。

**指标分三层定义。** 语句层：扫描行数、回表次数、是否落盘排序；实例层：活跃事务数、锁等待时长、脏页比例、redo 生成速率、history list length；集群层：复制延迟、2PC 悬挂事务数。每层至少有一个可测判据，否则这一层就等于没讲。

**边界与失效条件。** 这套方法在单机 OLTP 上最有效；遇到长事务、超大事务、DDL 变更窗口、跨分片写入会明显失效。换引擎也要换口径：InnoDB 用 MVCC + next-key lock，PostgreSQL 用 SSI，两者对“RR 防不防幻读”的答案不同，混着讲就是错的。

**常见错误做法的代价。**
- “索引越多越好”：每个二级索引都是一次额外写放大和一次页分裂风险，还扩大了优化器的搜索空间，代价是写 TPS 和 buffer pool 命中率。
- “调到 SERIALIZABLE 最安全”：并发度下降、死锁率上升，且实现往往是谓词锁或更大范围的 next-key lock。
- “一个事务包住整个业务请求”：undo 版本链无法 purge，回滚段膨胀，purge 线程追不上，最终 history list length 涨到拖慢普通查询。
- “主从延迟就 sleep 一下”：把延迟转嫁给可用性，抖动时仍然不一致；正确做法是按 GTID 等待或会话粘性。
- “慢就加缓存”：掩盖的是“没定义哪个时刻的一致”。

## 三、章节大纲

**关系模型与 SQL 的逻辑执行顺序**：FROM/JOIN → WHERE → GROUP BY → HAVING → SELECT → ORDER BY → LIMIT 的逻辑序，与优化器实际执行序的差异，别名可见性从何而来。可回答：“SQL 的执行顺序是什么，为什么 WHERE 不能用 SELECT 里的别名？”

**存储引擎：页、行格式与堆表**：页大小与页目录、页内有序槽位、行头与变长列、溢出页；索引组织表与堆表的差别。可回答：“一行数据在磁盘上长什么样，大字段存哪？”

**索引一：B+ 树的结构、分裂与回表**：扇出估算、随机主键与自增主键的页填充率差异、回表与覆盖索引、最左前缀、索引下推。可回答：“为什么推荐自增主键，UUID 主键的代价在哪？”

**索引二：LSM 与写放大**：memtable、SSTable、leveled 与 tiered compaction 的取舍，写放大近似 $WA \approx r\cdot(L-1)$（$r$ 为层间size ratio、$L$ 为层数，按实现而定），bloom filter 挡读。可回答：“LSM 和 B+ 树怎么选，写放大从哪来？”

**事务与 ACID 的真实含义**：C 是业务约束而非引擎保证，A 靠 undo，D 由 flush 策略决定，I 靠锁与 MVCC 组合。可回答：“ACID 里哪几条是数据库真正保证的？”

**隔离级别：从读未提交到可串行化**：四种级别对应的三类现象，标准定义与具体实现的偏差。可回答：“RR 能不能防幻读，MySQL 和 PostgreSQL 的答案为什么不同？”

**MVCC：版本链、快照与回滚段**：隐藏事务列与回滚指针、undo 版本链、read view 的活跃事务集合与可见性判断、快照创建时机（RR 是首条一致性读，RC 是每条语句）、purge 与 history list length。可回答：“长事务为什么危险，快照是什么时候建的？”

**锁：行锁、间隙锁、意向锁与死锁检测**：记录锁、间隙锁、next-key lock、插入意向锁，意向锁的表级语义，wait-for graph 与死锁回滚选谁。可回答：“间隙锁锁的是什么，两个事务为什么会死锁？”

**日志与恢复：WAL、redo、undo、checkpoint**：先写日志再刷页、redo 的物理逻辑性与 LSN、undo 的逻辑回滚、checkpoint 推进与崩溃恢复的分析/重做/回滚三阶段。可回答：“redo 和 undo 各保证什么，checkpoint 解决什么问题？”

**查询优化：执行计划与代价模型**：`EXPLAIN` 各列读法、IO 代价加 CPU 代价的估算、统计信息与采样误差、选错索引的排查路径（直方图、force index 作为临时手段）。可回答：“优化器为什么会选错索引？”

**复制与分布式事务：主从延迟、两阶段提交**：binlog 格式、半同步、GTID、延迟来源（大事务、回放并行度），2PC 的 prepare/commit 与悬挂事务。可回答：“两阶段提交解决什么问题，代价是什么？”

**一致性四层串讲：CPU 缓存 / 内存序 / 事务 / 副本**：MESI 与可见性、内存屏障与顺序、事务隔离与串行化点、副本复制与读己之写，四层共享“多副本 + 可见性顺序”的同一抽象，越往下代价越高、粒度越粗。可回答：“数据库事务和内存屏障是不是一回事？”

## 四、不做什么 · 必要性 · 失效点

### 必要性：删掉会怎样

| 机制 | 删掉会怎样 | 判定 |
|---|---|---|
| 联合索引最左前缀与覆盖索引 | `EXPLAIN` 仍出现 `type=ALL`、`key=(status)`、`rows` 上千万、`Extra=Using filesort`，`ORDER BY created_at DESC LIMIT 20` 不能按索引序返回，承诺“扫描行数接近 LIMIT”破 | 必需 |
| MVCC 快照读 | 普通 `SELECT qty` 不能从 undo 版本链读取可见版本，读不加锁承诺破，RC/RR 下会与当前读争用同一行锁 | 必需 |
| next-key lock（行锁 + 间隙锁） | RR 下范围查询/更新不再锁住记录间隙，幻读可发生，`SELECT ... FOR UPDATE` 后插入仍使两次范围结果不同 | 必需 |
| redo 与 binlog 两阶段提交 | `kill -9` 后 redo 前滚页与 binlog 事务顺序无法对齐，从库可能多一条或少一条，崩溃后主从一致承诺破 | 必需 |
| GTID 等待与会话粘性 | “写完立刻读从库”只能依赖 `Seconds_Behind_Master`，回放线程阻塞或延迟抖动时仍读到旧副本，读己之写承诺破 | 选择 |

### 失效点：哪条前提一破，结论就变

- redo/binlog 所在存储关闭 fsync/FUA 且 `innodb_flush_log_at_trx_commit=2` 或 `sync_binlog=0` → 两阶段提交不再保证已提交事务必进 binlog，`kill -9` 后从库可能少一条。
- 复制协议未启用 GTID（`gtid_mode=OFF`） → `GTID gap` 口径不可用，只能看 `Seconds_Behind_Master`，会漏报 SQL 线程中断。
- 会话缺少 `PROCESS`/`PERFORMANCE_SCHEMA` 权限或 `performance_schema=OFF` → `DATA_LOCK_WAITS` 为空，锁等待时长与死锁检测口径失效。
- 主从无 NTP/PTP 时钟同步且时钟漂移大于复制延迟 → `Seconds_Behind_Master` 可能为负或虚高，复制延迟判据变错。
- `innodb_buffer_pool_instances` 与核数/内存不匹配且热工作集超过 buffer pool → `Handler_read_rnd_next`、脏页比例、redo 生成速率上升，覆盖索引减少回表的收益被页淘汰抵消。

### 不做什么（范围）

- 不做 408 式推导：关系代数、范式分解证明、SQL 语法教学。
- 不做具体语言与框架层：ORM 用法、连接池参数调优、驱动重试策略。
- 不做引擎源码逐行解读（函数级调用链），只到机制与现象可对应的粒度。
- 不做运维交付：备份恢复演练编排、监控告警平台选型、容器化部署。
- 不做基准测试报告，不给任何“提升 N 倍”的承诺数字；不确定处写“按实现而定”。
- 缓存只在与副本一致性做类比的层面出现，不展开穿透/雪崩；分库分表只在 2PC 与副本一致性语境里提，不做选型。

## 五、面试怎么讲

**30 秒版本**

这块我按“一条 SQL 从解析到落盘”的链路组织：逻辑执行顺序决定优化器能改什么，页与行格式决定 I/O 单位，B+ 树与 LSM 是读放大和写放大的取舍，MVCC 加锁决定并发语义，WAL 与 redo/undo 决定崩溃后能否回到一致点，复制和 2PC 把同一套问题推到多机。我判断自己懂没懂的标准，是能不能用执行计划、锁等待、逻辑读这些口径把结论证伪，而不是背结论。

**可能被追问的 6–8 个点**

1. “为什么 InnoDB 用 B+ 树？”→ 考点：I/O 单位与范围扫描。答：非叶节点只存键和指针，扇出高，三层覆盖的行数量级按 $\lfloor P/(K+p)\rfloor^2$ 估；数据全在叶节点且叶间有链，范围扫描不用中序回溯；哈希不支持范围与排序。
2. “回表的代价怎么量化？”→ 考点：索引选择率与覆盖索引。答：看 `EXPLAIN` 的 `rows` 乘过滤率，再看 `Handler_read_%` 或 `performance_schema` 的 `ROWS_EXAMINED`；`Extra: Using index` 表示零回表；MRR 把随机回表转成按主键排序的顺序读。
3. “RR 到底防不防幻读？”→ 考点：快照读 vs 当前读。答：快照读由 read view 保证，当前读（`FOR UPDATE`、`UPDATE`、`DELETE`）由 next-key lock 保证；证据看 `SHOW ENGINE INNODB STATUS` 的 `TRANSACTIONS` 段锁信息。
4. “MVCC 快照什么时候建？”→ 考点：可见性时机。答：RR 是事务内首条一致性读，不是 `BEGIN`；RC 是每条语句新建 read view。可用 `INNODB_TRX` 的 `trx_started` 与事务年龄交叉验证。
5. “redo 和 binlog 为什么要两阶段提交？”→ 考点：跨层日志的顺序与崩溃点。答：redo prepare → binlog 写并 fsync → redo commit；恢复时 redo 处于 prepare 而 binlog 不完整则回滚。持久性档位由 `innodb_flush_log_at_trx_commit` 与 `sync_binlog` 共同决定，具体组合按配置而定。
6. “LSM 的写放大怎么算？”→ 考点：compaction 策略。答：按层间 size ratio 与层数估算，读放大靠 bloom filter 压；判据看 compaction 统计里每层读写字节数，而非主观感觉。
7. “间隙锁锁什么，为什么会死锁？”→ 考点：锁作用域与环路。答：锁索引记录之间的间隙以阻止插入；两事务以相反顺序取 next-key lock 即形成环，`LATEST DETECTED DEADLOCK` 段能看到持锁与等锁记录；相关参数 `innodb_lock_wait_timeout`、`innodb_deadlock_detect`。
8. “主从延迟怎么发现，读己之写怎么做？”→ 考点：延迟度量与补偿。答：`Seconds_Behind_Master` 粒度粗，用 GTID gap 或回放线程状态更准；补偿手段是按 GTID 等待、写后短窗口走主库、会话粘性——不是 sleep。

**别说什么**

- “我们用了 MVCC，所以读都不加锁。”——当前读照样加锁，这句话会立刻被追问打穿。
- “加到 SERIALIZABLE 就万无一失。”——不谈并发度代价和实现差异，等于没用过。
- “加了索引一定变快。”——不给执行计划和选择率，任何性能断言都不成立。
- “redo log 就是 binlog。”——层级、用途、写入方全不同，这句一出口基本就结束了。
