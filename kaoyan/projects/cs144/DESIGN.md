# CS144 · TCP/IP 协议栈 · 设计文档

> 本文是该项目的设计说明，不是教程。
> 大纲见 `OUTLINE.md`，一小时上手见 `QUICK.md`，详细记录见 `NOTES.md`。

## 一、定位与边界

本项目从零实现一个用户态 TCP 子集，把讲义上的滑动窗口、超时重传、序号回绕写成可观测的状态变量。解决的问题是：让每个协议字段都成为有明确生命周期的变量，包括 `next_seqno`、`bytes_in_flight`、`window_edges`、`checkpoint`、`first_unassembled`；并且这些变量只在四个地方被修改。

不解决的问题包括：路由与 IP 分片、拥塞控制（不做 cwnd 与慢启动，只实现接收窗口流控）、SACK、时间戳选项、Nagle 算法的完整形态、多连接复用与 epoll 驱动的高并发。它也不是一个可投入生产的栈。

与相邻项目的分工如下：前置的 `ByteStream` 项目只交付一个带容量的字节队列；本项目的重心是序号空间与状态机；后续的拥塞控制项目直接复用 `TCPSender` 的 `bytes_in_flight` 与 `next_seqno`，把固定窗口替换成动态窗口，而不改动重组层。

## 二、整体架构

五个模块按数据方向串成一条链，且只允许单向依赖：

- **ByteStream**：有容量上限的单向字节队列，提供 `write`、`peek`、`pop` 以及累计计数 `bytes_read`、`bytes_written`。它是全栈唯一的字节存储点。
- **StreamReassembler**：持有 ByteStream 与 `first_unassembled`，负责把乱序、重叠、重复的片段裁剪后顺序写入。
- **TCPReceiver**：负责 32 位序号与 64 位绝对序号的换算，维护 `checkpoint`，产生 `ackno` 与 `window_size`。
- **TCPSender**：负责窗口左边界、发送队列、未确认区、RTO 定时器与重传计数。
- **TCPConnection**：组合收发两侧，实现四次挥手与 TIME_WAIT。

调用方向严格自上而下：`TCPConnection::segment_received` 调用 `TCPReceiver::segment_received`，再调用 `StreamReassembler::push_substring`，最后调用 `ByteStream::write`；发送路径从 `ByteStream::peek` 取出数据，到 `TCPSender::fill_window`，再到 `TCPSegment` 序列化。反向只有两个返回值：`ackno` 与 `window_size`。依赖图中不存在回边，这是保证可测试性的前提。

## 三、技术选型与理由

- **C++17**：固定宽度整数 `uint32_t` 的溢出与回绕语义由标准定义，才能复现序号回绕。换成 Python 不行，因为其无限精度整数会把 `unwrap` 的边界错误悄悄吞掉；换成 Rust 则与课程 starter code 的类型签名不一致。
- **CMake**：starter code 已提供 `sponge` 与 `Minnow` 的 target，增量构建与 sanitizer 开关都是一行配置；Bazel 的工具链锁定对单人项目不划算。
- **sponge::Buffer + std::string**：底层存储直接用 `std::string`，配合 `Buffer` 的读写视图，不手写环形缓冲区。理由是环形缓冲的边界处理会引入与协议无关的 bug，掩盖真正要练的序号逻辑。
- **Catch2**：`SECTION` 能把同一构造下的多组断言分开计时，便于定位是哪个不变量先坏；starter code 已集成，换 GoogleTest 无收益。
- **ASan + UBSan + Valgrind**：越界读与未初始化读在重组裁剪中最常见，仅靠单元测试无法覆盖。
- **tcpdump + Wireshark 回放 pcap**：对照真实报文校验字段编码，替代打印调试。
- **种子化确定性丢包**：所有网络扰动由固定种子驱动，失败可重放。

## 四、数据流

一次典型运行的路径如下：

1. 应用调用 `ByteStream::write`，数据落入发送侧队列，`bytes_written` 增加。
2. `fill_window` 读取通告窗口 $w$，从 `next_seqno` 起构造不超过 $\min(w - \text{bytes\_in\_flight},\ \text{可读字节})$ 的载荷，压入未确认队列。
3. 段被序列化为 `TCPSegment`，经 `TCPSocket` 封装进 UDP 报文发出。
4. 对端 `segment_received` 解析出 `seqno`，用 `checkpoint` 做 `unwrap` 得到绝对序号，再减一（SYN 占一位）得流内索引。
5. `StreamReassembler` 按索引裁剪后写入 ByteStream，`bytes_pending` 随之变化。
6. 回程 `ackno` 推进 `window_edges`，释放未确认区，触发下一次 `fill_window`。

关键数据结构：`std::map<uint64_t, std::string>` 保存乱序区间（键为起始索引，保证遍历有序且天然去重）；`std::queue<TCPSegment>` 保存未确认段；`std::optional<uint64_t>` 表示 `ackno` 与 `checkpoint` 的“未初始化”状态。

## 五、章节目录与知识点映射

| 章 | 内容 | 涉及的知识点 | 与考纲或前置项目的关系 |
| --- | --- | --- | --- |
| 0 | ByteStream | 容量双指针、`peek`/`pop` 非对称语义、`bytes_read` 单调累计、EOF 转半关闭 | 前置项目直接产物；对应“流量控制缓冲区”概念题 |
| 1 | StreamReassembler | 乱序区间有序表、重叠裁剪三种情形、`first_unassembled` 推进、容量上界 $\text{first\_unassembled} + \text{capacity}$ | 对应“滑动窗口接收侧”计算题 |
| 2 | TCPReceiver | SYN/FIN 各占一个序号、`unwrap` 取最近绝对序号、`checkpoint` 更新时机、`window_size = capacity - bytes_pending` | 对应“序号回绕与窗口通告”题；依赖第 1 章 |
| 3 | TCPSender | `next_seqno` 与 `bytes_in_flight`、窗口左边界闭合、RTO 指数退避 $\text{RTO}_k = \text{RTO}_0 2^k$、零窗口探测单字节、连续重传上限 | 对应“超时重传与退避”计算题；依赖第 0 章 |
| 4 | TCPConnection | 三次握手末态、四条关闭条件、TIME_WAIT 保持 $10 \times \text{rt\_timeout}$、收到 RST 立即 `active=false` | 对应“状态机转换”题；依赖第 2、3 章 |
| 5 | 定时器与时钟 | 累积 tick 与 `ms_since_last` 归零、重传定时器仅在非零窗口启动、`ack` 前进后复位退避 | 对应“定时器管理”设计题 |
| 6 | 报文编解码 | 头部字段位宽、校验和、序号与标志位打包、UDP 载荷封装 | 对应“TCP 首部格式”记忆题 |
| 7 | 验证与模糊测试 | 随机乱序注入、种子化丢包网络、不变量断言（`bytes_in_flight ≤ w`） | 衔接后续拥塞控制项目 |
| 8 | 性能与拷贝语义 | 每字节拷贝次数、`std::string` 移动、避免重组时二次扫描 | 支撑第 6 章验收指标 |

## 六、验收判据

- ByteStream：容量为 1 时任意读写序列不越界；10$^{6}$ 次随机操作后 `bytes_written - bytes_read` 等于队列长度，误差 0。
- StreamReassembler：10$^{4}$ 个随机乱序段（含 30% 重叠、10% 重复）重组结果与原串逐字节相等；任何时刻 `bytes_pending ≤ capacity`；跨越 $2^{32}$ 序号三次以上，绝对序号误差 0。
- TCPSender：10% 丢包网络下 1 MB 数据完整送达；RTO 序列严格 2 倍递增，连续重传 8 次后中止连接；`bytes_in_flight ≤ window_size` 全程成立。
- TCPConnection：被动关闭与主动关闭各 100 次，全部在 TIME_WAIT 后正常退出；官方 17 个测试用例通过 17/17。
- 性能：1 MB 传输耗时随数据量线性，拟合 $R^2 \ge 0.99$；单字节平均拷贝 ≤ 2 次；ASan 与 Valgrind 报告 0 泄漏、0 越界。

## 七、风险与已知坑

- **`unwrap` 的边界**：当序号差恰为 $2^{31}$ 时，取最近绝对序号的方向不唯一，容易写出单向比较而漏掉负方向。
- **SYN 与 FIN 占位**：流内索引与绝对序号差一，FIN 之后 `first_unassembled` 的推进常被漏掉，导致连接永不关闭。
- **零窗口死锁**：窗口为 0 时仍有探测包必须发出，且探测包不能被计入 `bytes_in_flight` 的窗口判定。
- **容量语义混用**：ByteStream 容量与接收窗口是同一个数，但重组器丢弃越窗字节的判据是 `first_unassembled + capacity`，两者一旦分开维护就会失配。
- **重传计时器重启条件**：只有 `ack` 确认了新数据才复位，重复 `ack` 不应清零，否则退避失效。

## 八、与其他项目的关系

前置为 `ByteStream` 与基础网络 I/O 封装；后续为拥塞控制项目（替换固定窗口为 cwnd 与 ssthresh，复用 `bytes_in_flight`、`next_seqno`、RTO 计算），以及可靠传输性能分析项目（复用种子化丢包网络做对照实验）。可复用模块：`StreamReassembler` 的有序区间表可直接用于任何乱序重组场景；`unwrap` 与 `checkpoint` 逻辑可迁移到基于序号的日志复制；种子化的丢包与乱序注入器是后续所有对照实验的基础设施。
