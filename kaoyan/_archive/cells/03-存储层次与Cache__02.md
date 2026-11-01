<!-- 出处：03-存储层次与Cache.ipynb cell[2] · 迁移于 2026-10-28 -->

## [CS149] 多核 cache 一致性：MSI/MESI 与 false sharing

> 2026-10-22 · 来源：CS149 项目复习（真源 modules/408/CS149.md）

- **MSI 三态**：M（改过、全机唯一）/ S（与内存一致、可多副本、不能直接写）/ I（作废）。写 S 态必须先广播 invalidate —— **别人手里的副本越多，写越贵**。
- **MESI 的 E 态**：干净独占（只我读过、未改、与内存一致）。**E 升 M 是本地事务、不发总线** —— 私有的读-改-写不再骚扰总线，这就是加 E 的全部意义。
- **false sharing（伪共享）**：不同变量挤同一 64B cache line，各核写各自的变量，逻辑零冲突，但每次写都互相 invalidate，line 在核间乒乓，性能可掉一个数量级。修复：alignas(64) 或 padding 让每个热点变量独占一条 line。
- 与 408 的关系：408 只考到「多核 cache 一致性」概念级；协议级（MSI/MESI 状态转换）与工程级（false sharing 定位与修复）是 CS149 L14 的内容。

