# CS144 · 从零实现 TCP/IP 协议栈

> **工程线（兴趣向，非考试范围）**。本文件不承担复习任务。
> 斯坦福 CS144：在用户态用 C++ 重写一个能跑通真实互联网的 TCP。
>
> **单向引用约定**：本文提到考点时**只写 KP 号与考点名**，不复制 `exam/` 的正文；
> `exam/` 的文件里也不出现本文件的工程名。两边互不依赖，只共享主键。

## 对位考点（单向引用）

| 本文段落 | 对应 KP |
|---|---|
| 滑动窗口 / 可靠传输 / 重传 | `408-NET-0504` TCP 可靠传输与流量控制 |
| 连接建立与释放、状态机 | `408-NET-0503` TCP 连接管理 |
| 链路层 ARP 与网络接口 | `408-NET-0404` 分片与配套协议 |
| 路由表与最长前缀匹配 | `408-NET-0403` IPv4 地址与子网划分 |
| 分层、封装与解封装 | `408-NET-0102` 分层与参考模型 |
| 检错与校验和 | `408-NET-0302` 差错控制 |

---

## 0 怎么读这个文件

- §1 给出**全景与关键路径**，回答"这个系列到底在造什么、先做哪个"。
- §2 是**设计理念**，回答你最关心的那个问题：为什么一堆 C++ 类就敢说"替换了 Linux 的网络协议栈"，以及网络层的路由、传输层的 TCP/IP 究竟是怎么被替换掉的、又是怎么和现实网络接线的。**这是整个项目最值钱的部分，别跳过。**
- §3 每个 checkpoint 一个模板：目标 → 要实现的接口 → 机制 → **关键路径**（实现顺序）→ **易错点清单** → 与现实对照 → 408 对应点 → 验收命令。
- §4–5 是调试兵器库与时间预算（含冲刺期取舍建议）。

---

## 1 总纲：这个项目在造什么

### 1.1 一句话

> **在普通用户态 C++ 进程里，从零重写 TCP/IP 的下四层（以太网 + IP + TCP），并且让它和真实互联网上的服务器对话。**

注意措辞：不是"劫持"内核，不是 hook 系统调用，不是改 `/proc`。它是一个**普通进程**，跑完 `./scripts/tun.sh start 144` 之后，拥有往内核网络栈里"塞数据报"的权限。

### 1.2 运行视角的分层图（数据怎么走）

```
        应用层 app        webget / tcp_ipv4 / endtoend
                              |  (可靠的双向字节流: ByteStream)
   ========================== 替换的分界线 ==========================
        传输层 TCP       TCPPeer  =  TCPSender  +  TCPReceiver      check3 / check2
                                        |              |
                                        |        StreamReassembler   check1
                                        |              |
                                        |         ByteStream         check0
   -----------------------------------------------------------------
        网络层 IP        wrap_tcp_in_ip / unwrap_tcp_in_ip (util 提供)
                         InternetDatagram = IPv4Header + payload
   -----------------------------------------------------------------
        链路层 Ethernet  NetworkInterface（ARP 解析下一跳 MAC）      check5
                         EthernetFrame / EthernetHeader / ARPMessage
   -----------------------------------------------------------------
        【出口】         TunFD(TUN, 三层) / TapFD(TAP, 二层)
                         UDPSocket(AF_INET) / PacketSocket(AF_PACKET)
   ====================== 上面的东西全是你写的 ======================
        Linux 内核       路由表 + NAT/masquerade + 物理网卡驱动
```

**图本身就说了一件关键的事**：`NetworkInterface` 这一层**在同一份代码里被复用两次**（check5 官方 PDF 图 1 就是这么画的）——

- 左边：作为**主机** TCP/IP 栈的最底层，把 IP 数据报变成以太网帧；
- 右边：作为**路由器**的一块网卡，各个 interface 之间互转数据报。

这就是它为什么被单独拆成一个 checkpoint：**它是 IP 世界和以太网世界之间的唯一翻译官。**

### 1.3 建造顺序 ≠ 运行顺序（这是本设计的核心巧妙处）

| 方向 | 顺序 | 含义 |
|---|---|---|
| **运行**（数据自顶向下流动） | app → TCP → IP → Ethernet → 内核 | 上层调用下层 |
| **建造**（checkpoint 顺序） | check0 字节流 → check1 重组器 → check2 收端 → check3 发端 → check4 互通 **→ 然后回头 check5 以太网/ARP → check6 路由器** | **先竖起 TCP，再回头补底下两层** |

为什么能这样造？因为**每一层在写的时候，下层是"假的"或用现成的替身**：

- check0–3 写 TCP 的时候，下层是单测直接喂结构体
- check4 下层是 TUN 设备（内核顺手帮它做了以太网那一层，见 §2.1）；
- check5 才把"内核帮忙做的那一步"变成你自己写的 ARP + Ethernet 封装。

**教学含义**：每一步都有可单独跑的单元测试，一个 bug 不会被下层的不确定性掩盖。这也是为什么 check4 之前你对"MAC 地址"一无所知却已经能让 HTTP 跑通了。

### 1.4 八 checkpoint 全景表

> **得到了本地 `git ls-tree` 与官方 PDF 的双向核实**，文件名真实存在。

| # | 名称 | 你要写的 / 改的 | 代码量（官方口径） | 强依赖 | 408 对应章节 |
|---|---|---|---|---|---|
| check0 | Networking warmup | `apps/webget.cc`（用手写 HTTP GET）+ `src/byte_stream.{hh,cc}` | ByteStream 约 111 行（官方解） | 无 | 17-应用层（HTTP 报文格式） |
| check1 | Stitching substrings into a byte stream | `src/reassembler.cc`（`insert` + `bytes_pending`） | 约 50–60 行新增 | check0 | 16-传输层 SR 接收窗口 / 序号与滑动窗口 |
| check2 | The TCP receiver | `src/wrapping_integers.cc`（wrap/unwrap）+ `src/tcp_receiver.cc` | receiver 约 15 行 | check1 | 16：序号空间 / SYN-FIN 占号 / 累积确认 / 流量控制 |
| check3 | The TCP sender | `src/tcp_sender.cc`（4 个方法） | 约 100–150 行 | check2 | 16：超时重传 ARQ / RTO 指数退避 / 零窗口探测 |
| check4 | Interoperating in the world | 基本**不写代码**：改 `webget.cc` 换 socket 类 + 跑 2 小时 ping 统计报告 | ≈ 0 | check3 | 16：连接管理（握手/挥手/TIME_WAIT）的一次实战验收 |
| check5 | The network interface (ARP) | `src/network_interface.cc`（3 个方法） | 约 100–150 行 | 无（不依赖 TCP！） | 14-链路层：以太网帧 / ARP / MAC 寻址 |
| check6 | Building an IP router | `src/router.cc`（`add_route` + `route`） | 约 30–60 行（starter 38 行 / 官方解 89 行） | check5 | 15-网络层：路由表 / 最长前缀匹配 / TTL / 首部校验和 |
| check7 | Putting it all together | 基本不写代码：`endtoend` 联调（两人一组，或自己开两个终端分饰两角） | ≈ 0 | check5+6 | 综合 + NAT 的现实后果 |

### 1.5 依赖与关键路径（最少白费的排序）

```
check0 ──> check1 ──> check2 ──> check3 ──> check4
                                              (互通：真实互联网)
                                   \
                    check5 (ARP) ──> check6 (Router) ──> check7 (联调)
```

**关键路径＝check1 → check2 → check3**。理由：

1. 这条链上任何一环有 bug，check4 的"和真实服务器对话"会以一种**完全静默**的方式失败（对端丢包不解释原因），debug 成本极高。
2. check5/check6 **不依赖 TCP**（官方原话：*"Checkpoint 6 builds on your implementation of NetworkInterface from Checkpoint 5, but does not use the TCP stack"*），所以它们可以从另一头单独做，随时插入。
3. check4 / check7 的价值是**验收**，不是开发。通不过 = 前面有 bug。

### 1.6 本地子仓体检结果（动手前先看这块）

在 `~/develop/learning/learning-408/cs144` 里实读得到的事实：

| 项 | 现状 |
|---|---|
| 版本 | **2024 winter minnow**，C++20；`project(minnow CXX)`；必须 out-of-source 构建（`cmake -S . -B build`，写了 guard 会报错） |
| `apps/webget.cc` | **已完成**，手写 HTTP/1.1 GET（用了内核 `TCPSocket`） |
| `src/byte_stream.hh/cc` | **已完成**。见下面"你当年实现里的两个值得复盘的点" |
| `src/reassembler.cc` | **仍是空骨架** —— `insert()` 里只有 `(void)first_index; (void)data; (void)is_last_substring;`，`bytes_pending()` 返回 `{}`。**这就是你重做的起点。** |
| check2–7 骨架 | **不在工作区，但全在本地**：`git branch -a` 可见 `remotes/origin/check2-startercode` … `check7-startercode`。直接 `git merge origin/checkN-startercode` 就能拿到官方头文件。当前 HEAD 在 `check1-startercode` |
| 单测 | `tests/` 已有 byte_stream 6 项 + reassembler 7 项 + 两个 speed test（跑 `--target check1` 与 `--target speed`）；后续 merge 新的 startercode 时测试集会自动补齐 |
| `writeups/check0.md` / `check1.md` | 还是模板（含 `[your name here]` 等占位符），需重填 |

**你当年 byte_stream.cc 里两个值得复盘的 decisions**（实测撸出来的，不吹不黑）：

1. `pop()` 用了**惰性压缩**：只有当 `first_unread_ > 4096 && first_unread_ * 2 > buffer_.size()` 时才 `erase`，否则只挪游标。这是标准的摊销 O(1) 写法，也是它能过 `byte_stream_speed_test` 的原因。反过来想：如果你换成"每次 pop 都 erase(0,n)"，就是 O(n^2)，速度测试直接掉到 0.1 Gbit/s 以下。
2. `available_capacity()` 写成 `capacity_ - (buffer_.size() - first_unread_)`，而不是 `capacity_ - bytes_buffered()` 之外的什么花样 —— 这个表达式**决定了 check1 的容量边界怎么算**（§3.1，最关键的一个坑）。

> ⚠️ 硬规则提醒（`LEARNING.md` §2）：引用实践代码时只能引这个仓里的真实文件，并且在归档里标注"仓库名 + 路径"。本文件的所有代码级描述都来自上述三源，**没有一句是凭印象编的**；凡是没拿到文件的部分（例如 check2/check3 的 `.cc` 实现体），本文件只写接口与规则，不编实现。

---

## 2 设计理念 ★：为什么 C++ 代码能替换 Linux 网络协议栈

### 2.1 三种"携带 TCP 的方式"——理解整个项目的钥匙

check5 官方 PDF 的 Overview 一开头就把这件事讲透了：你写好的 TCP 段，是怎么跑到对端的 TCP 实现手里的？**只有三种答案，而这三种答案正好对应这个项目里的三个出口**：

| 方式 | 谁来构造 TCP/IP/Ethernet 头 | 内核给什么接口 | 用在哪个 checkpoint |
|---|---|---|---|
| **TCP-in-UDP-in-IP** | 内核写 UDP+IP+Ethernet 头，你只给 payload 和目的地址 | **datagram socket**（`UDPSocket`，`AF_INET`+`SOCK_DGRAM`） | 最省事；check6/check7 的模拟网络就用这种思路，把整个 IP 数据报当 UDP 的 payload 搬运 |
| **TCP-in-IP** | 你写完整 **IP 头**，内核写以太网头并真发 | **TUN 设备**（`TunFD`，`IFF_TUN`） | **check4 —— 所谓"Interoperating in the real world"就是这个** |
| **TCP-in-IP-in-Ethernet** | IP 头 **和** 以太网头全你自己写（含 ARP 解析 MAC） | **TAP 设备**（`TapFD`，`IFF_TAP`）或直接 `AF_PACKET` | **check5/check7** |

一句话串起来：**这个项目每往后做一个 checkpoint，就是把"内核帮忙写的那部分头"拿走一层变成自己写。**check4 时以太网头由内核写；check5 你自己写以太网头 + 用 ARP 查 MAC；到 check7 你的 host + 你的 router 全栈自给自足。

### 2.2 唯一的契约是：一切皆 fd

`util/file_descriptor.hh` 是整个设计的地基：

```cpp
// A reference-counted handle to a file descriptor
class FileDescriptor { ... std::shared_ptr<FDWrapper> internal_fd_; ... };
```

然后所有东西都长得跟它一样：

- `Socket : public FileDescriptor` → `TCPSocket` / `UDPSocket` / `PacketSocket` / `LocalStreamSocket`
- `TunTapFD : public FileDescriptor` → `TunFD` / `TapFD`
- `apps/bidirectional_stream_copy.cc` 里直接 `FileDescriptor _input { STDIN_FILENO };`

于是整个 Minnow 世界里数据流动只有两个动作：**`read()` 和 `write()`**。你的 TCP 栈不需要"发包函数"，它就是往某个 fd 里 `write()` 一串字节；网络侧的数据到来也不需要"中断处理"，就是某个 fd 变得可读。

> 对比：内核里 `struct sock` 的成员 `sk_socket->file` 也是这个结构——socket 之所以能 `read/write/select`，就是因为它挂在 fd 后面。**CS144 把内核的这一条约定原样搬进了用户态。**

### 2.3 四条"现实出口"（真正接线的那几根）

#### (a) TUN —— 三层虚拟网卡（check4 的真身）

`util/tun.cc` 全文不到 30 行，做的事只有两件：

```cpp
FileDescriptor( CheckSystemCall("open", open("/dev/net/tun", O_RDWR | O_CLOEXEC)) );
tun_req.ifr_flags = (is_tun ? IFF_TUN : IFF_TAP) | IFF_NO_PI;   // no packetinfo
CheckSystemCall("ioctl", ioctl(fd_num(), TUNSETIFF, &tun_req));
```

**打开 `/dev/net/tun` + `TUNSETIFF` ioctl，就把你的进程 fd 和一块虚拟网卡焊在一起了。** 之后：

- 你 `write()` 一个 IP 数据报进 fd → 内核当作"这块网卡刚从网线收到这个包"，照常做路由、NAT、发到物理网卡；
- 内核决定交给这块网卡的 IP 数据报 → 你 `read()` 出来。

`IFF_NO_PI` 的含义也值得一记：**不要**在包前面附 packet information 头。少了这 4 字节，你 read 出来的就是纯粹的 IP 数据报，直接进入 `Parser`。

#### (b) `scripts/tun.sh` —— 打通真实互联网的最后三件事

```bash
TUN_IP_PREFIX=169.254                                  # link-local，刻意避开你的真实网段
ip tuntap add mode tun user ${SUDO_USER} name tun144
ip addr add 169.254.144.1/24 dev tun144                 # 内核侧地址：你的网关
ip link set dev tun144 up
ip route change 169.254.144.0/24 dev tun144 rto_min 10ms
iptables -t nat -A PREROUTING -s 169.254.144.0/24 -j CONNMARK --set-mark 144
iptables -t nat -A POSTROUTING -j MASQUERADE -m connmark --mark 144
echo 1 > /proc/sys/net/ipv4/ip_forward
```

逐条翻译成人话：

- `169.254.144.1` 是**你这台虚拟机在 TUN 那一侧的地址** —— 也就是你的 TCP 栈眼里的"默认网关"（所以 check4 手册让你 `tcp_ipv4 169.254.144.1 9090` 连自己机器上用内核 TCP 的服务器）。
- `MASQUERADE` = NAT。你的 IP 数据报源地址是 `169.254.144.9` 这种私有 link-local 地址，直接扔到公网上没人认识，出去之前被内核换成虚拟机的真实 IP，回来的包再换回来。
- `ip_forward=1` = 允许内核在 TUN 和物理网卡之间转发。

> **这就是"替换"的全部真相**：你的协议栈负责**内容**（TCP 语义 + IP 头），最后一公里的**搬运**（以太网 + 出网卡 + NAT）仍然由内核完成。它不是被你替换掉了，而是被你**当成传输介质**用了——就像你把内核当成一根网线。
> check5 把这根网线的一部分也拿回来自己写：那时你产出的是**以太网帧**，走 TAP。

#### (c) UDP socket —— 隧道（check6/7 的多机玩法）

`util/socket.hh` 的 `UDPSocket` 让你把**整个 IP 数据报**塞进 UDP payload 发到另一个进程/另一台机器。对方解出来，交给它的 IP 层继续走。**这就是隧道（tunneling）**：IP-in-UDP。check7 的 `endtoend` 靠一个中继服务器（`cs144.keithw.org`）在两个都躲在 NAT 后面的学生的虚拟机之间搭这条隧道。

> 现实对照：VPN / VXLAN / WireGuard 干的是同一件事，只是封装外层换掉了。**理解 CS144 的这条，就理解了所有 overlay 网络。**

#### (d) `PacketSocket`（`AF_PACKET`）—— 直接跟网卡打交道

`apps/` 之外，`util/socket.hh` 里还留了 `PacketSocket(AF_PACKET, type, protocol)` 与 `set_promiscuous()` 两个口子。这是二层的最高权限：能收发原始以太网帧。check7 的尽头就是它。

### 2.4 数据面的通用语言：`Parser` / `Serializer`

**这是我认为整个项目最优雅的一笔，值得单独拿出来讲。**

`util/parser.hh` 规定了每一层必须实现的一对成员：

```cpp
void parse( Parser& parser );
void serialize( Serializer& serializer ) const;
```

于是**一个报文**在 Minnow 里的表示是 `std::vector<std::string>`（一串 buffer，允许零拷贝拼接），而每一层都遵循同样的三板斧：

```
EthernetFrame::parse()   -> header.parse(parser); parser.all_remaining(payload);
IPv4Datagram::parse()    -> header.parse(parser); parser.all_remaining(payload);
TCPSegment::parse()      -> ... -> 直到最后 payload 是应用层字节
```

剥完一层，`parser` 里剩下的东西直接喂给下一层，`payload` 用 `all_remaining()` 一次拖走。**上层不需要知道下层的长度、对齐、拷贝策略。**

> **现实对照（这很重要）**：Linux 内核里对应物是 `struct sk_buff`，它靠 `skb->network_header` / `skb->transport_header` 这些指针做同样的事——同一个 buffer，剥包头只是**挪指针**，不拷贝。CS144 用 `Parser::remove_prefix(n)` + `std::string_view peek()` 表达了同一个思想，只是把指针换成了 span 语义的安全版本。
> **边界标注**：sk_buff 还能做 skb_clone / 分散聚集 DMA / GRO 这类优化，CS144 不考也不做。别把课本上学的发展和这 200 行代码划等号。

配套的通用 helper（`util/parser.hh` 末尾）：

```cpp
template<class T> std::vector<std::string> serialize( const T& obj );
template<class T> bool parse( T& obj, const std::vector<std::string>& buffers );  // 返回是否 OK
```

注意 `parse<T>()` **返回一个 bool**——这就是 check5 手册里那句 "if successful (meaning the parse() method returned ParseResult::NoError)" 的由来：**每个入站包都必须检查解析是否成功，失败就丢。** 这是你写防御式编程的第一个惯性动作。

### 2.5 谁来管时间：`EventLoop` + 手工 `tick`

TCP 有很多"等着"的事：重传计时器、TIME_WAIT、ARP 缓存过期。两种时间的来源在 Minnow 里泾渭分明：

| 时间来源 | 载体 | 谁回调 | 现实对照 |
|---|---|---|---|
| **真实时间流逝** | `EventLoop`（`util/eventloop.hh`，`poll(2)` 封装） | `add_rule(name, fd, Direction::In/Out, callback, interest, cancel, error)` + `wait_next_event(timeout_ms)` | 内核的软中断 / epoll 事件驱动 |
| **协议内部的"虚拟时间"** | `tick(uint64_t ms_since_last_tick)` | 上层驱动调用 | 内核 `tcp_write_timer` 等定时器 |

`bidirectional_stream_copy.cc` 是 `EventLoop` 的教科书范例：4 条规则分别处理 stdin→outbound stream、outbound→socket、socket→inbound、inbound→stdout，每条都配 `interest`（什么时候关心这个事件）和 `cancel/error` 回调。**没有任何线程、没有 sleep、没有忙等。**

⚠️ **check3 手册里一句硬规则**（直接影响你能否过测试）：

> *"please don't try to call any 'time' or 'clock' functions from the operating system or CPU — the tick method is your only access to the passage of time. That keeps things deterministic and testable."*

**`TCPSender` 里禁止碰真实时钟。** 一旦你用了 `gettimeofday`，所有单测就不可复现了。这个约束不是洁癖，是让 distributed system 测试成为可能的地基。

### 2.6 替换的真正落点在 socket 这一层：`TCPMinnowSocket`

回到 §2.1，最锋利的一刀在这里。`util/tcp_minnow_socket.hh` 的原版注释直接把话说白了：

> *"This class involves the simultaneous operation of two threads. One, the 'owner' or foreground thread, interacts with this class in much the same way as one would interact with a TCPSocket... **The other, the 'TCPPeer' thread, takes care of the back-end tasks that the kernel would perform for a TCPSocket**: reading and parsing datagrams from the wire, filtering out segments unrelated to the connection, etc."*

套一层壳，它就是 check4 那次"替换"真正发生的地方：

```
class TCPMinnowSocket : public LocalStreamSocket        // ← 它仍然是 Socket，仍然是 fd！
{
  AdaptT        _datagram_adapter;   // 底下可以是 TUN(TCP-over-IP)，也可以是 UDP socket(TCP-in-UDP)
  LocalStreamSocket _thread_data;    // 用 Unix domain socketpair 把两个线程接起来
  std::optional<TCPPeer> _tcp {};    // 你的 TCP 状态机（TCPSender + TCPReceiver）
  EventLoop     _eventloop {};
  std::thread   _tcp_thread {};      // 后台线程跑 TCPPeer + EventLoop
};
```

**把"内核干的那部分活"搬到你自己进程的另一个线程里去做，对外仍然暴露一个 fd。**这就是 dropped-in replacement 的完整答案。check4 里你做的全部事情只有一行：

```cpp
// apps/webget.cc
#include "tcp_minnow_socket.hh"
CS144TCPSocket socket;      // 原来是 TCPSocket socket;  —— 换成你自己实现的 TCP
```

上层 `get_URL()` 一个字不改，发的是同一条 HTTP 请求，收的是同一个网页，只不过**底下换成你写的 TCPSender/TCPReceiver**。

> 差异也要诚实说明：官方注释自己列了三条不同 —— 只能接一条连接；`listen_and_accept()` 把 `listen(2)`+`accept(2)` 合成一个阻塞调用；析构时若连接还开着直接发 RST（除非你先 `wait_until_closed()`）。
> `bind`/`local_address`/`set_reuseaddr` 被 `= delete` 掉：**一个诚实的实现宁可删掉，也不假装支持。**

### 2.7 为什么每一层都能单独测

这是这套设计最"工程"的部分，靠三个机制：

1. **把输出口做成抽象接口**（依赖注入）。`NetworkInterface` 内部不是"直接写 fd"，而是调用一个虚函数：

   ```cpp
   class OutputPort { public: virtual void transmit(const NetworkInterface&, const EthernetFrame&) = 0; };
   void transmit(const EthernetFrame& frame) const { port_->transmit(*this, frame); }
   ```

   单测只要塞一个记帧的假 OutputPort，就能断言"你到底发出了什么以太网帧"，**不需要一根真实网线**。

2. **用 C++20 concept 约束适配器形状**：

   ```cpp
   template<class T> concept TCPDatagramAdapter = requires(T a, TCPMessage seg) {
     { a.write(seg) } -> std::same_as<void>;
     { a.read() } -> std::same_as<std::optional<TCPMessage>>;
   };
   ```

   然后 `using TCPOverIPv4MinnowSocket = TCPMinnowSocket<TCPOverIPv4OverTunFdAdapter>;` —— **同一个 TCP 实现，换个 Adapter 就能从 TUN 换到 UDP 隧道**，一行代码量的替换。

3. **`LossyFdAdapter` 装饰器**：可以人为注入上下行丢包率（`tcp_ipv4 -Lu 0.1 -Ld 0.1`）。**不用真断网就能测重传。** 这是对"可测性"理解到骨子里才会做的设计。

### 2.8 故意的简化清单 —— 这是最有价值的"现实边界"素材

每处简化都能明确对照 RFC，也正好是 408 课本里"考不考"的分界：

| 简化 | 项目里的做法 | 现实/RFC | 对 408 的意义 |
|---|---|---|---|
| **没有拥塞控制** | `TCPSender` 只有流控窗口，没有 cwnd/慢启动/Reno | 真实 TCP 的半壁江山 | **lab 里那个窗口就是纯 rwnd**，不要混淆。这也解释了为什么你之前归档的那条"CS144 TCPSender 无 cwnd"是对的 |
| **IP 不分片** | `IPv4Header` 构造就带 `df = true` | 真实 IP 会分片 | 反而帮助你把这个因素隔离出来专心看 MSS/MTU 关系 |
| **不要求发 ICMP** | check5 ARP 不回、check6 TTL 耗尽只丢不发 Time Exceeded | 真实路由器会发 ICMP 差错报告 | 408 仍要考 ICMP（traceroute/PING 原理），lab 不实现≠不考 |
| **TIME_WAIT 简化** | `TCPPeer::active()`：`lingering = cumulative_time_ < time_of_last_receipt_ + 10 * cfg_.rt_timeout`（默认 10 s） | RFC 793 的 2×MSL（常见 60 s） | 数值不必背量级，但"为什么要等"这个**动机**必须懂 |
| **窗口字段只有 16 位** | `window_size` 上限 `UINT16_MAX = 65535` | 真实 TCP 得靠窗口扩大选项（scale factor） | ★必考：为什么首部只留 16 位带来的量级限制，以及怎么破 |
| **RTO 简化** | 初始 1 s（`TIMEOUT_DFLT = 1000`）、超时翻倍、新 ACK 复位；**没有** RTT 采样/Karn/RFC 6298 完整公式 | RFC 6298 的 SRTT+RTTVAR | 课本要会算 RTO（加权平均），lab 只实现"翻倍+复位" |
| **重传即重发原段** | 不允许合包重传、不允许部分裁剪 outstanding | 真实实现会更激进（SACK/重组的好处） | 理解"为什么禁止"比"会写"更有益 |

### 2.9 一句话总结这个设计理念

> **分层之所以能被"手写"，是因为每一层的输入输出都被压成了同一种形状：一层 = 一个 struct + 一对 parse/serialize + 一个 fd 口；层与层之间的接缝是显式的数据结构（`TCPSenderMessage` / `InternetDatagram` / `EthernetFrame`）而不是函数调用。**
>
> 内核做的事并没有被"替换"，而是被**降级成了运输大队**：它只管把你的字节塞给网卡、把网卡的字节取回来。剩下的语义（可靠性、顺序、流量、连接生命周期、地址解析、转发决策），全在你这 ~1000 行 C++ 里。

---

## 3 checkpoint 逐个拆解

每个小节统一格式：**目标 → 接口（真实路径）→ 机制 → 关键路径 → 易错点 → 现实对照 / 408 对应 → 验收**。

### 3.0 Checkpoint 0：Networking warmup + ByteStream

**目标**：两件事。用 socket 手写 HTTP/1.1 GET 抓网页（`get_URL`）；在内存里实现一个受容量约束的**可靠字节流** `ByteStream`。

**机制**：三个计数 + 一个闭合标记：

- `bytes_pushed`（写端累计写了多少）
- `bytes_popped`（读端累计读了多少）
- `bytes_buffered = pushed - popped`（当前占着缓冲的）
- `closed`（写端不会再写）
- **`capacity` 是"缓冲上限"，不是"累计上限"** —— 读走的字节会释放额度

**关键路径**：
1. 先手做 §2.1 的手工 HTTP（*顺序不能乱：GET 行 → Host → Connection: close → 空行**；空行才是"报完"的信号），拿到 `X-Your-Code-Is:`；
2. `Writer::push` → `close` → `available_capacity` → `bytes_pushed`；
3. `Reader::peek` → `pop` → `is_finished` → `bytes_buffered` → `bytes_popped`；
4. 最后抠性能（`byte_stream_speed_test`）。

**易错点**：
- **HTTP 的行尾必须是 CRLF `\r\n`**，只发 `\n` 在严格服务器眼里等于请求不合规；
- **必须有空行结束头部**（你本地实现的写法 `"...Connection: close\r\n\r\n"` 是对的）；
- `push` 超容量部分**静默丢弃**（只写能写下的部分），这是 check1 的隐含契约，不是 bug；
- 用 `cout` 输出页面内容是 OK 的，**但任何调试信息必须去 `cerr`**（check4 手册明确要求，否则污染 stdout）；
- `webget.cc` 在整个系列里会被反复 merge：每份 checkN 手册都说"不要改 `src/` 之外的文件，**除了 `webget.cc`**"——因为 check4 要在这里换 socket 类型；
- **Modern C++ 纪律**（check0 PDF §3.2 明文，会被判风格分）：绝不用 `malloc/free`、绝不用 `new/delete`，一切"配对操作"改成 RAII（构造里获取、析构里释放）。

**408 对应**：HTTP 请求/响应格式、`GET` 方法与首部行。这一段的价值是让你先亲手确认一件事：**应用层看到的就是一条可靠的字节流**。

**验收**：`cmake --build build --target check0`

---

### 3.1 Checkpoint 1：StreamReassembler ★ 从这一块真正开始动脑

**目标**：把一堆**可能乱序、可能重叠、可能重复、可能丢**的 substring，按字节序号缝回那一条字节流。

**接口**（`src/reassembler.hh` 真实存在）：

```cpp
void     insert( uint64_t first_index, std::string data, bool is_last_substring );
uint64_t bytes_pending() const;
```

**机制**：官方 PDF 明确把 Reassembler 的知识分成三类，图画得很清楚（`[已pop][绿色: 在 ByteStream 里缓冲][红色: 在 Reassembler 里等][更远: 丢]`）：

1. 正好是下一个字节 → **立刻** push 到 `output_.writer()`；
2. 落在容量内但前面还有空洞 → 存在 Reassembler 内部；
3. **超出容量的 → 直接丢弃。**

> ⚠️ **"capacity 同时约束绿色和红色两块"** —— 这是本 checkpoint 唯一的、也是几乎所有人都踩的坑。官方 FAQ 原话：
> *"Is it okay for our re-assembly data structure to store overlapping substrings? No. ... But allowing the re-assembler to do this undermines the notion of 'capacity' as a memory limit."*

**由此推出第一原则**：

```
first_unacceptable  =  output.writer().bytes_pushed() + output.writer().available_capacity()
                   =  capacity + output.reader().bytes_popped()      // 两个写法等价，都行
```

注意它**会随上层 pop 而向前滑**。用常量 `capacity_` 算、或用 `first_unassembled + capacity` 算，都是错的。

**关键路径**（按此顺序写，一次只加一个难度）：
1. 只有按序、不重复的 insert → 立刻 push；
2. 支持 `bytes_pending()` 的精确计数（**重叠部分不能重复计数**）；
3. 数据结构选型：标准解是 `std::map<uint64_t, std::string>`（key = 起始 index），插入时**与邻居合并/裁剪**；
4. 处理**带空洞的 FIN**（`is_last_substring=true` 但还有字节没到 → 记住 EOF 字节位置，等到排到再 `close()`）；
5. 最后做速度：`reassembler_speed_test` 要求 **> 0.1 Gbit/s**，官方范例能到 10 Gbit/s。**线性扫描全容器必然超时。**

**易错点清单**：
- [ ] `first_index < 已排到的位置`（迟到/重复数据）→ 要**裁剪掉前面的部分**，不是整段丢弃；
- [ ] 同一片数据重叠多次 → 只能存一份，否则 memory 上限失守（上面那句官方 FAQ）；
- [ ] 空字符串 + `is_last_substring=true`（FIN 单独到达）→ 仍然要触发后续的 `close()`；
- [ ] `bytes_pending()` **在 push 到 ByteStream 之后必须减少**（它只统计还没进 ByteStream 的字节）；
- [ ] 不要借 Reassembler 的手去读 Reader 一侧 —— 官方：`"Will the Reassembler ever use the Reader side of the ByteStream? No—that's for the external customer."`
- [ ] 别把 FIN 的**序号**混进来：check1 的 `first_index` 是纯字节 index，不含 SYN/FIN。序号要等到 check2 才登场。

**现实对照**：这就是 Linux `tcp_data_queue()` + out-of-order queue 干的事，也是课本里 **SR（选择重传）接收窗口**的具体实现。区别仅为：内核要考虑 SACK 与内存回收压力。**边界**：不要在 408 答题里写"用 map 实现"——课本要的是 SR 的窗口逻辑，不是数据结构。

**验收**：`cmake --build build --target check1`；`make check1` 之外务必跑 `--target speed`（速度也有门槛）

---

### 3.2 Checkpoint 2：TCP Receiver

**目标**：把 `TCPSenderMessage` 翻译成 `Reassembler::insert` 调用，并算出两个回答给发送方的信号：**ackno 与 window size**。

**必须捋清的三套编号**（★这就是 check2 的全部难点，也是 408 传输层的核心考点）：

| | 起点 | 是否含 SYN/FIN | 位数 | check2 PDF 的 'cat' 例子 |
|---|---|---|---|---|
| **seqno** | 随机的 ISN | 含 | 32，**会回绕** | SYN=`2^32-2`, c=`2^32-1`, a=0, t=1, FIN=2 |
| **absolute seqno** | 0 | 含 | 64，不回绕 | 0, 1, 2, 3, 4 |
| **stream index** | 0 | **不含** | 64，不回绕 | —, 0, 1, 2 |

换算规则：`stream_index = absolute_seqno - 1`（因为 SYN 占了 1 个号）；abs ↔ seqno 靠 `Wrap32`。

**接口**（check2 官方给的真实定义）：

```cpp
struct TCPSenderMessage {                      // util/tcp_sender_message.hh
  Wrap32 seqno {0}; bool SYN{}; std::string payload{}; bool FIN{}; bool RST{};
  size_t sequence_length() const { return SYN + payload.size() + FIN; }
};
struct TCPReceiverMessage {                    // util/tcp_receiver_message.hh
  std::optional<Wrap32> ackno {};              // 还没收到 SYN 时为空
  uint16_t window_size {};                     // 上限 UINT16_MAX = 65535
  bool RST {};
};
class TCPReceiver {
  void receive( TCPSenderMessage message );    // src/tcp_receiver.hh
  TCPReceiverMessage send() const;
};
// 另外：src/wrapping_integers.{hh,cc}
static Wrap32 Wrap32::wrap( uint64_t n, Wrap32 zero_point );
uint64_t unwrap( Wrap32 zero_point, uint64_t checkpoint ) const;
```

**关键路径**：
1. `wrap`：一行（`zero_point + n`）。官方提示："expecting one line of code for wrap"。
2. `unwrap`：**不要用 `abs()` / 不要先转有符号**。做法：算 `distance = (raw_value - wrap(checkpoint, zero_point)) mod 2^32`，若 `distance > 2^31` 则把距离往回退（`checkpoint + distance - 2^32`）。官方提示"less than 10 lines"。
   **checkpoint 取什么**：文档明文 "*you'll use the first unassembled index as the checkpoint*"。
3. `receive()`：
   - 第一个带 SYN 的报文 → 记下 ISN（`SYN` 也可能同时带数据/FIN：check2 手册特别提醒 "*the SYN flag is just one flag in the header. The same message could also carry data or have the FIN flag set*"）；
   - 在收到第一个 SYN 之前到来的报文一律忽略（没握手，不接受数据）；
   - 内部：`abs_seqno = message.seqno.unwrap(ISN, checkpoint)`；`stream_index = abs_seqno + message.SYN - 1` → 喂给 `reassembler_.insert(stream_index, payload, FIN)`；
   - `RST` → `reassembler_.reader().set_error()`，之后 `send()` 里 `RST` 要回 true。
4. `send()`：`ackno = optional<Wrap32>`（没 ISN 就 `nullopt`）；`window_size = min(available_capacity, 65535)`。

**易错点清单**：
- [ ] **ISN 不能因为第二个 SYN 到了就重设**（重复 SYN 是常态，尤其对手是真实服务器时）；
- [ ] window_size 必须**截断到 65535**（16 bit 字段）+ 它是**sequence number 的个数**，从 ackno 起算；
- [ ] **ackno 到底指什么必须算对**：它是对方"期望收到的下一个 seqno"，即 `wrap(SYN(1) + 已排好序的字节数 + FIN(若已收到))` —— 写法取决于你怎么记账，核心是回答"我还缺哪个号"；
- [ ] `unwrap` 的 32 位算术要在 **mod 2^32 语义**下做，C++ 里 `uint32_t` 天然回绕，但 `uint64_t` 不；不要混用宽度；
- [ ] `checkpoint` 选错会导致 unwrap 跳到 4 GiB 之外 → 症状是"突然整个乱序号"，而且只在流长到一定程度才复现（难调！）。

**408 对应**：★核心。这里就是"TCP 序号针对字节编号、SYN/FIN 各消耗一个序号、确认号含义=期望收到的下一字节"三个考点的具体实现。有了这一层体感，做真题的序号推算题基本不会再错。

**验收**：`cmake --build build --target check2`

---

### 3.3 Checkpoint 3：TCP Sender

**目标**：反过来——读 ByteStream，打成 TCP 段发出去，跟踪未确认的段，超时重传。

**接口**（`src/tcp_sender.hh` 真实）：

```cpp
TCPSenderMessage make_empty_message() const;
void receive( const TCPReceiverMessage& msg );
using TransmitFunction = std::function<void(const TCPSenderMessage&)>;
void push( const TransmitFunction& transmit );
void tick( uint64_t ms_since_last_tick, const TransmitFunction& transmit );
uint64_t sequence_numbers_in_flight() const;
uint64_t consecutive_retransmissions() const;
```

注意它是**回调式**的（给你一个 `transmit` 去调用），而不是返回 vector。这保证"发"和"MakeStateMachineProgress"解耦。

**关键参数**（`util/tcp_config.hh` 真实值）：

```cpp
DEFAULT_CAPACITY = 64000;  MAX_PAYLOAD_SIZE = 1000;  TIMEOUT_DFLT = 1000 /* ms */;
MAX_RETX_ATTEMPTS = 8;     Wrap32 isn { 137 };       // 137 是测试默认值；tcp_ipv4.cc 里换成 random_device()
```

> ⚠️ **`MAX_PAYLOAD_SIZE` 冲突**：check3 的 PDF 写的是 1452，而 check7 骨架的 `tcp_config.hh` 里是 **1000**（注释写的是 "Conservative max payload size for real Internet"）。**以你实际 merge 到的骨架为准**；写代码时别硬编码这个数字，统一引用 `TCPConfig::MAX_PAYLOAD_SIZE`。

**计时器的六条铁律**（check3 PDF §2.1，逐条照搬——照着写就能过）：

1. **禁止使用真实时钟**（见 §2.5）。
2. 每次发出一个**占据序号空间**的段（无论首传还是重传），若 timer 没开 → 开，RTO 后到期。
3. 所有 outstanding 数据都被确认 → **停 timer**。
4. tick 时若 timer 到期：重传**最早的那个**未完全确认的段。
5. 若**发送窗口非零**：① 连续重传计数 +1（供上层判定"连接没救了"）② **RTO 翻倍**。
6. 重置 timer 到新的 RTO。

收到新 ACK（ackno 大于此前最大值）时：① **RTO 复位回初始值** ② 若还有 outstanding 则重启 timer ③ 连续重传计数清零。

**关键路径**：
1. 状态四件套：`next_seqno(abs)`、`outstanding 队列`、`timer_running / ticks`、`consecutive_retransmissions`。
2. 先做 `push` 顺序：SYN → payload → FIN，注意 `sequence_length()` 算占几个号。
3. 再做 `receive`：清出被完全确认的段（`ackno > 该段最后一个序号`），更新 `window`（左边界=ackno，右边界=ackno+window_size）。
4. 最后做 `tick` 与退避。
5. `make_empty_message()`：纯 ACK 用的空段，**不占序号、不进 outstanding、永不重传**。

**零窗口的特殊语义**（★易错、★也是 408 的考点）：

> check3 PDF 原文：*"If the receiver has announced a window size of zero, the push method should pretend like the window size is one. ... This is the only special-case behavior your implementation should have for the case of a zero-size window. The TCPSender shouldn't actually remember a false window size of 1."*

两句话拆开讲：
- **为什么要装作窗口=1**：接收方把窗口开回非零后，不会主动通知你（它没有"我窗口变了"这种报文，只能搭 ACK 顺风车）；你若不发这一字节去"戳"一下，就再也拿不到新的 ACK → **死锁**（这就是课本上的"零窗口探测"）；
- **只在 `push` 内部**，不能把它存进成员；且 **"窗口大小=1"不等于"窗口满"**（后者是完全不同的判断）。

初始假设：收到任何 `receive()` 之前，认为对方窗口 = **1**（只够发 SYN）。

**其余易错点**：
- [ ] 部分确认不裁剪（官方 FAQ 明确说"no need to get fancy"，整段算 outstanding 直到全部确认）；
- [ ] 不允许把 abc 合并成一个大段重传（同上）；
- [ ] 空段不入库、不重传；
- [ ] SYN/FIN **各占一个序号**，也占窗口空间；
- [ ] RTO 翻倍后要靠"收到新 ACK"才复位，不是靠"下一次 tick"；
- [ ] `MAX_RETX_ATTEMPTS`(8) 的判定在 check4 的 `TCPPeer`/上层做，sender 只负责提供 `consecutive_retransmissions()`。

**408 对应**：★必考区。ARQ、超时重传时间的选择、指数退避、零窗口死锁、GBN vs SR 的实践差异。**但切记：lab 没有拥塞控制**——408 里 cwnd 和 rwnd 是两个窗口之和；这里只有 rwnd。

**验收**：`cmake --build build --target check3`

---

### 3.4 Checkpoint 4：Interoperating in the world ★（你的"怎么替换"问题的正面回答）

**目标**：**几乎不写代码**，把你的 TCP 推到真实互联网上去。

**三件事**：

1. 改 `apps/webget.cc`，把内核 socket 换成你的：

   ```cpp
   #include "tcp_minnow_socket.hh"
   CS144TCPSocket socket;      // 原来是：TCPSocket socket;
   ```

2. 打通权限与 NAT：

   ```bash
   ./scripts/tun.sh start 144        # 每次重启 VM 都要重跑
   cmake --build build --target check_webget
   ./build/apps/webget cs144.keithw.org /nph-hasher/xyzzy
   ```

3. 交一份**数据报告**：选 RTT ≥ 100 ms 的远端主机，`ping -D -n -i 0.2 host | tee data.txt` 跑 ≥ 2 小时，统计丢包率、最长连续成功/丢失串、条件概率 π(第 N+1 次成功 | 第 N 次成功) 与 π(第 N+1 次成功 | 第 N 次丢失) 的对比、RTT 时序图 + 直方图/CDF + 相邻 RTT 相关性图，回答"丢包的时间相关性强不强"。**这其实就是课本里"丢包模型是 Bernoulli 还是 bursty"的一次实证**，值得好好做，不是走过场。

**调试的黄金三角**：
- `./build/apps/tcp_ipv4 169.254.144.1 9090` — 你的 TCP 做客户端
- `./build/apps/tcp_native -l 0 9090` — 内核 TCP 做服务端
- `sudo tshark -i tun144 -vvv`（或 wireshark）— 站在"网线"上看你的包长啥样

**为什么这个对照实验无价**：同一套 `bidirectional_stream_copy()` 上层代码，两边跑不同 TCP。**跑不通，错误百分之百在你这边**（内核 TCP 是参照组）。这就是 check4 官方说的"if your TCP implementation is written properly, you may not have to write any code for this checkpoint"。

**必读的设计细节**（现在你可以对照真实代码看一遍这条链）：

```
apps/tcp_ipv4.cc:
  TunFD("tun144")
   └─ TCPOverIPv4OverTunFdAdapter(TunFD)
        write(msg): _tun.write(serialize(wrap_tcp_in_ip(msg)))   ← 见 util/tcp_over_ip.cc
        read():     unwrap_tcp_in_ip(InternetDatagram) -> optional<TCPMessage>
   └─ LossyFdAdapter<...>            （可注入上下行丢包）
   └─ LossyTCPOverIPv4MinnowSocket   （类 socket + 后台线程跑 TCPPeer）
   └─ bidirectional_stream_copy(...) （和 tcp_native 完全相同的上层代码）
```

`wrap_tcp_in_ip` 值得逐行读（`util/tcp_over_ip.cc`，约 15 行）：它设置 src/dst IP、**把 TCP 校验和依赖的伪首部交给 `ip_dgram.header.pseudo_checksum()`**、在**算完校验和之后**才 `serialize(seg)` 填进 payload、最后 `ip_dgram.header.compute_checksum()`。顺序不能反，也不能漏——**校验和错了，对端会一声不响地丢包**，这是 check4 最常见的"卡死"原因。

同样，`unwrap_tcp_in_ip` 里那串守卫也值得当模板读：dst IP 是不是我 → src IP 是不是我 peer → `proto == IPv4Header::PROTO_TCP` → 解析成功？→ 目的端口是不是我 → 源端口是不是我 peer。**这就是"用一个 4 元组（src ip/port, dst ip/port）界定一条连接"的具体实现**，对应课本里的 socket 四元组。

**易错点**：
- [ ] 忘了 `./scripts/tun.sh start 144`（重启后 TUN 设备没了）→ 症状：打开 tun 设备失败或直接没流量；
- [ ] 调试信息打到 `cout` → 和 HTTP body 混一起，check 失败。**必须 cerr**；
- [ ] 校验和算错（尤其伪首部 `pseudo_checksum()` 忘了传）→ 静默丢包；
- [ ] ISN 忘记换成随机（`TCPConfig` 默认 `Wrap32{137}` 是给单测用的确定性值；跑真实网络时 `tcp_ipv4.cc` 用 `Wrap32{random_device()()}`）；
- [ ] 没有正确处理"最后的 lingering"（默认 10 × RTO = 10 s）→ 连接提前销毁，对端收到 RST。

---

### 3.5 Checkpoint 5：Network Interface（ARP）

**目标**：把 IP 数据报 ↔ 以太网帧互相翻译，核心是**查下一跳的 MAC 地址**。官方定义它是 "the bridge between Internet datagrams that travel the world, and link-layer Ethernet frames that travel one hop"。

**接口**（`src/network_interface.hh` 真实）：

```cpp
void send_datagram( const InternetDatagram& dgram, const Address& next_hop );
void recv_frame( const EthernetFrame& frame );
void tick( size_t ms_since_last_tick );
std::queue<InternetDatagram>& datagrams_received();
void transmit( const EthernetFrame& frame ) const { port_->transmit( *this, frame ); }
```

**语义**（逐条来自 check5 PDF + 骨架注释）：

| 方法 | 要做什么 |
|---|---|
| `send_datagram` | 已知 MAC → 构造 `EthernetHeader`（`type = TYPE_IPv4`，src=自己，dst=目标 MAC）立刻发；**未知 MAC → 广播 ARP request，并把数据报排队**；若最近 **5 秒**内已为同一 IP 发过 ARP request，**不要重发**，继续排队即可 |
| `recv_frame` | 目标 MAC **既不是广播也不是自己** → 忽略；IPv4 → parse 成功则塞进 `datagrams_received()`；ARP → **不管 request 还是 reply，都学「sender IP→sender MAC」映射，存 30 秒**；若是问我的 request → 回 ARP reply |
| `tick` | 淘汰超过 30 秒的映射 |

**关键路径**：
1. `Address::ipv4_numeric()` 把 `Address` 变成 32 位整数（这就是你填 ARP 报文 `sender_ip_address` /  `target_ip_address` 用的）；
2. 广播地址：以太网 `ff:ff:ff:ff:ff:ff` 表示"发给链路上的所有人"（ARP request 就发到这儿）；
3. 先打通"已知 MAC 直接发"，再做"未知→ARP+排队"，最后加 5 s 抑制与 30 s 过期；
4. ARP reply 回来后，**把队列里所有等这个 IP 的数据报一次性放出去**。

**易错点清单**：
- [ ] **别把"最终目的地"和"下一跳"搞混** —— 官方 PDF 用脚注特别提醒了这一条：*`Please don't confuse the ultimate destination of the datagram ... with the next hop. In this lab you're only going to care about the next hop's address`*。**这是全 lab 第一号语义错误。**
- [ ] 5 秒抑制是"同一个 IP 的 request"，不是"全局 5 秒只能发一次 ARP"；
- [ ] 30 秒是**从学到映射那一刻算起**（也有人按"最后一次使用起算"写，两种都能跑通测试，但你要在 writeup 里说清楚自己选了哪种）；
- [ ] 即使没人问过，**ARP request/reply 里的 sender 信息都要缓存**（顺路学习，这叫 gratuitous learning）；
- [ ] 只有 target IP == 自己的 IP 时才回 reply；
- [ ] **sender / target 两组字段别填反**：`ethernet_address_` 是自己的 MAC，别在 request 里把自己的 MAC 当成对方的 MAC 填进 `target_ethernet_address`；

**现实对照**：`ip neigh` / `arp -n` 看到的那张表就是它；内核对应逻辑在 `neigh_*`。**边界**：真实系统还会做 gratuitous ARP、DUPLICATE address detection、队列超时+ICMP host unreachable（手册明说这两条 **lab 不需要做**）。

**408 对应**：★ 链路层必考。以太网帧格式、MAC 地址、ARP 解析过程（广播请求/单播响应/缓存）、以及"为什么有了 IP 地址还要 MAC 地址"这道大题的答案。

**验收**：`cmake --build build --target check5`

---

### 3.6 Checkpoint 6：IP Router ★ 命中 408 考点最密的一个

**目标**：多个 `NetworkInterface` + 一张路由表，按最长前缀匹配转发。

**接口**（`src/router.hh` 真实）：

```cpp
size_t add_interface( std::shared_ptr<NetworkInterface> interface );
std::shared_ptr<NetworkInterface> interface( size_t N );
void add_route( uint32_t route_prefix, uint8_t prefix_length,
                std::optional<Address> next_hop, size_t interface_num );
void route();
```

**语义**（check6 PDF）：

- **match**：目的地址的最高 `prefix_length` 位 == `route_prefix` 的最高 `prefix_length` 位；
- 在所有匹配的路由里选 **`prefix_length` 最大**的（最长前缀匹配）；
- 没有匹配 → **丢弃**；
- **TTL**：`if (ttl == 0 || --ttl == 0) drop;`（即：本来就是 0，或减完变 0，都丢）；
- next_hop 是 `nullopt`（直连路由）→ 用**数据报的目的 IP** 当下一跳；否则用给定的下一跳路由器 IP；
- 发出去：`interface(interface_num)->send_datagram(dgram, next_hop)`；
- **ICMP 不要求**（TTL 耗尽丢掉即可）。

**路由只需要 O(N) 扫描**（官方 FAQ 明文允许："It's perfectly acceptable for each datagram to require O(N) work"）。别上来就写 trie。

**关键路径**：
1. `add_route` 存表 → 2. `route()` 逐个 interface 抽 `datagrams_received()` → 3. 最长前缀匹配 → 4. TTL 判定 → 5. 递减+**重算校验和** → 6. `send_datagram`。

**易错点清单**：
- [ ] 🔥 **移位 UB**：构造掩码时 `0xffffffff << (32 - prefix_length)`，当 `prefix_length == 0` 时是 **`<< 32`，32 位整数移位 32 位是未定义行为**。check6 PDF 专门点名：*"it can produce undefined behavior to shift a 32-bit integer by 32 bits. The tests run your code under sanitizers that try to detect this."* **必须特判 `prefix_length == 0`（默认路由）。**
- [ ] 🔥 **TTL 递减后忘了 `compute_checksum()`** —— IPv4 首部里有 checksum 字段，首部一变就得重算。忘记的结果：下一跳路由器直接丢弃。
- [ ] `prefix_length` 是 `uint8_t`，参与运算前留意整型提升；
- [ ] 直连路由 next_hop 为空的情况别忘；
- [ ] 后端 `Address::from_ipv4_numeric()` / `ipv4_numeric()` 一对转换别搞反。

**这一 check 的设计精髓**（官方 PDF 原文，也是这句话解释了整个互联网为什么能分层）：

> *"the router never thinks about TCP, about ARP, or about Ethernet frames. The router doesn't even know what the link layer looks like. The router only thinks about Internet datagrams, and only interacts with the link layer through the NetworkInterface abstraction."*

路由器只知道 IP。底下以太网长什么样、MAC 怎么查，全被 `NetworkInterface` 吸收掉了。**这就是为什么 check5 那一层被单独拆出来做成零件。**

**408 对应**：★网络层核心。路由聚合 + 最长前缀匹配 + TTL 生存时间 + 首部校验和 + 直接交付/间接交付。**做完这个 check，`ip route` 命令的输出在你眼里不再是天书。**

**验收**：`cmake --build build --target check6`（PDF 第 4 节写的是 `check5`，那是文档笔误，按标题应是 check6）

---

### 3.7 Checkpoint 7：Putting it all together

**目标**：**不写代码**，把你自己全部层拼起来，做一个真网络：两端各贡献"一台主机（ByteStream+TCP+NetworkInterface）"和"一个路由器"，两台虚拟机之间的 TCP 会话要穿越你写的以太网 + IP + 路由器（另一端可能是别的同学写的实现）。

**为什么需要中继**：官方 PDF 说得很直白 —— *"it's likely that you or your lab partner will be behind a Network Address Translator, the network connection between the two sides will flow through a relay server (cs144.keithw.org)"*。**这就是 NAT 的现实后果：两个躲在 NAT 后面的节点不能直接连。**

**网络拓扑**（check7 Figure 1，真实数据）：

```
[host 192.168.0.50] -- host_side 192.168.0.1      host_side 172.16.0.1 -- [host 172.16.0.100]
                        internet_side 10.0.0.192  ==隧道==  10.0.0.172
                        route: 192.168.0.0/16 (direct)      route: 172.16.0.0/12 (direct)
                        route: 10.0.0.0/8 (direct)          route: 10.0.0.0/8 (direct)
                        route: 172.16.0.0/12 via 10.0.0.172 route: 192.168.0.0/16 via 10.0.0.192
```

**步骤**（务必遵守顺序）：
1. **先自己和自己跑通**（两个终端同时扮演 client/server）—— 官方第一条就是这条：*"If necessary, the same student can serve as 'lab partner' more than once. Before doing these steps with a lab partner, try them by yourself."* **自己和自己先跑一遍比跟陌生人联调容易一个数量级**；
2. 选一个 **1024–64000 之间的随机偶数** N 作为组号（要偶数、要和别人不同）；
3. server 跑 `./apps/endtoend server cs144.keithw.org N`，client 跑 `... client cs144.keithw.org N+1`；
4. 传文件验证：**`dd if=/dev/urandom bs=1M count=1 of=/tmp/big.txt`**，server 端 `< /tmp/big.txt`，client 端 `> /tmp/big-received.txt`，最后 **`sha256sum`** 比对哈希。用随机数据是故意的——压缩友好的数据会掩盖 off-by-one；
5. 传较慢就加一个 `debug` 参数：官方说会打印**每一个以太网帧**，ARP/TCP/IP 全可见。

**易错点**：
- [ ] 组号冲突（课堂上限流）→ 症状：连不上、或者连进了别人的组；
- [ ] 必须一偶一奇、client = N+1；
- [ ] 忘了先自己和自己跑通就直接找搭档 → debug 成本翻十倍；
- [ ] 传 1 MB 文件这一步才会暴露**窗口管理与流边界**的问题（这类细节单测往往测不到）。

**408 对应**：综合实战。NAT、私有地址段，以及"端到端原则在现实里被破坏"的后果——你在这里会亲眼遇到：两台虚拟机明明都能上网，却必须借道一个中继服务器才能互相连上。

---

## 4 调试兵器库

| 兵器 | 用法 | 解决什么 |
|---|---|---|
| `tshark`/`wireshark` 挂 `tun144` | `sudo tshark -i tun144 -vvv` | 站在"网线"上看你的包是否真发出去、字段对不对 |
| **对照组** `tcp_native` vs `tcp_ipv4` | 两个终端，一边内核 TCP 一边你的 TCP | 判断"错在我这边还是对面" |
| `LossyFdAdapter` | `tcp_ipv4 -Lu 0.1 -Ld 0.1` | 不用断网就能测重传逻辑 |
| address 转换 | `Address::ipv4_numeric()` / `from_ipv4_numeric()` | 避免自己手写 htonl/ntohl 出错 |
| `--target tidy` / `--target format` | 提交前必跑 | 风格分 + 提前暴露可疑写法 |
| `cerr` 不是 `cout` | check4 明文要求 | 避免调试输出污染 HTTP body |
| 允许改的文件 | **只有 `src/*.{hh,cc}` 与 `webget.cc`**（每份 PDF 的 Submit 第 1 条） | 防止 merge 冲突 |
| 构建崩了的标准复位手段 | `rm -rf build && cmake -S . -B build`（check1 PDF §3.5 建议） | 拿不准的时候别硬调 CMake |

**拿到 starter code 的方式**（你这块和官方不同，很重要）：

- 上游 `https://github.com/cs144/minnow` **当前不可公开访问**（实测 404）；
- 但你的私有仓 `git@gitee.com:we_we_we/cs144.git` 里**所有 checkN-startercode 分支都已经 fetch 在本地**（`git branch -a` 可见 check2–check7）；
- 所以标准流程是：`git merge origin/checkN-startercode`（**而不是 `git fetch --all`**，你 fetch 不到上游）。

---

## 5 时间预算与冲刺期取舍

官方口径的总工作量参考（`scripts/lines-of-code` 工具也能量）：ByteStream ~111 行，Reassembler 额外 50–60 行，TCPReceiver ~15 行，TCPSender 100–150 行，NetworkInterface 100–150 行，Router 30–60 行。**代码不多，难在概念。**

| checkpoint | 我的时间估计（有 C++ 基础、清醒状态） |
|---|---|
| check0 | 半天（其中 ByteStream 主体 1–2 小时） |
| check1 | 半天–1 天（容量边界 + 性能） |
| check2 | 1 天（wrap/unwrap 想明白之后就快了） |
| check3 | 1–1.5 天（整个系列最难的一个） |
| check4 | 半天编程 + 2 小时 ping（必须挂 2 小时，早点起跑） |
| check5 | 1 天 |
| check6 | 半天 |
| check7 | 半天（联调时间不算） |

**冲刺期建议**（现在距初试约 9 周，`LEARNING.md` §6A）：**别按 8 周的计划重跑。** 按 ROI 排序，只取对 408 有直接收益的部分：

| 优先级 | 做 | 理由 |
|---|---|---|
| ★★★ | **check2 + check3**（做完立刻去做真题里的同类题） | 直接对应 408 传输层最密的考点：序号空间、累计确认、rwnd、ARQ/RTO、零窗口死锁。做完这两个，相关知识从"背下来的"变成"手搓过的" |
| ★★ | **check6 Router** | 网络层最长前缀匹配 + TTL + 校验和，考点密集且代码只要 30–60 行，**性价比最高** |
| ★★ | **check5 ARP** | 链路层必考点（ARP + 以太网帧），做完课本上的图就有了 implementation 版锚点 |
| ★ | check0/check1 | 作为热身，半天到一天；做完 `Reassembler`，408 里 SR 接收端的逻辑就不再是背诵项 |
| ○ | check4 / check7 的报告部分 | **2 小时 ping 的统计报告可以趁复习间隙挂着跑**，但"写英文报告"这一步优先级最低 |

一句话：**把 CS144 当成 408 网络部分的"现实视角教材"（`LEARNING.md` §2 三视角里的那一维）来用，而不是当成第二条战线。**

---

## 6 Writeup 要求（统一模板，每份 20–50 行）

每个 checkpoint 都要在 `writeups/checkN.md` 交一份英文报告，≤80 字符/行，固定三段：

1. **Program Structure and Design** —— 不要逐行翻译代码；要讲你**做了什么设计选择、为什么**（数据结构选了什么、和备选方案比有什么 trade-off）。
2. **Implementation Challenges** —— 最难受的部分 + 你是怎么越过去的 + 你用什么手段保证 invariants（防御式断言/单测/调试器）。
3. **Remaining Bugs** —— 诚实列出已知的未处理边界。官方明确期待这一段，撒谎会被扣分。

check0/check1 的模板里还要求填写：**花费小时数**、合作者、"你被什么惊讶到了/学到了什么"。

check7 额外要求分组：Solo 部分 / Group 部分（含搭档 SUNetID）/ Creative 部分。

---

## 7 附录

### 7.1 官方 PDF 索引（Winter 2024，来自 CS 自学社区镜像；已核对内容）

| checkpoint | PDF |
|---|---|
| check0 | https://www.learncs.site/assets/files/check0-0de083d1c15c182068ea66bc90c0c883.pdf |
| check1 | https://www.learncs.site/assets/files/check1-7b57b8c9fe87bdb20a1d11e4bae463e6.pdf |
| check2 | https://www.learncs.site/assets/files/check2-a0da04de3cd9715ce8a3dccaf3fbe903.pdf |
| check3 | https://www.learncs.site/assets/files/check3-c86e29d001b025fad918919dd5d2bcd8.pdf |
| check4 | https://www.learncs.site/assets/files/check4-524dd6a97f01d0a30dbbe7eb65f5d16b.pdf |
| check5 | https://www.learncs.site/assets/files/check5-243f553de21f2b7846a04a8fc245c831.pdf |
| check6 | https://www.learncs.site/assets/files/check6-eb0ec16d09e94e9564f8b175b69be333.pdf |
| check7 | https://www.learncs.site/assets/files/check7-c6c22999d874eb76b20590d7140ef9a8.pdf |

课程官网另有 FAQ：https://cs144.github.io/lab_faq.html（PDF 更新后的问题会挂在这里）。

### 7.2 动手前的检查清单

- [ ] `cd ~/develop/learning/learning-408/cs144 && git status`（确认在 `check1-startercode` 且工作区干净）
- [ ] 当前进度：**`src/reassembler.cc` 还是空骨架** —— 直接从这里开始写 `insert` / `bytes_pending`
- [ ] `cmake -S . -B build && cmake --build build && cmake --build build --target check1`（先让 check0/现有状态是绿的）
- [ ] 后续每个 checkpoint：`git merge origin/checkN-startercode`，然后 **只改 `src/*.{hh,cc}` 和 `webget.cc`**
- [ ] 每次开始 checkN 前先通读对应 PDF（PDF 里有 implementation order、FAQ、以及明确说"不需要做"的东西）
- [ ] 归档：每个 checkpoint 的所得，按 `AGENTS.md` 落到 `16-传输层` / `14-网络分层与链路层` / `15-网络层` 三个 ipynb

---

## 8 408 真题对位·变式题集（③ 验收层，2026-10-22 增补）

> **性质声明**：以下题目全部为**自编变式**（难度与题型对齐 408 真题，标注教材分块与 CS144 对位），不是真题原文；**所有答案先手算复核再落盘**。
> **用法**（对齐 `LEARNING.md` §六）：限时作答——选择 2 分钟、大题 15–20 分钟；哪题卡住，回 §3 对应小节回补，再按归因维度（概念不清 / 计算失误 / 没记住 / 审题错 / 项目误导 / 存疑待核）记账。
> **一个已知归属差异要说明**：教材把 ARP 划在**网络层**（15），而 CS144 的 check5 cell 已落在 **14**（当时主题是"网络接口 + 以太网"）。两边都算数：14 那条是"实现视角"，15 另补一条"教材考点视角"（见各 ipynb 的 `[CS144·验收]` cell）。

### 8.1 传输层（16-传输层 · 对位 check2 / check3 / check4）

**题型 1：握手与挥手的序号推算**（★核心 · 对位 check2「三套编号」+ check4 连接管理）

【题】主机 A 与 B 建立 TCP 连接，A 的 ISN = 1000，B 的 ISN = 3000。握手完成后 A 立即发送一段 100 字节的数据。求：
(1) B 的 SYN+ACK 段的 seq 与 ack；
(2) A 的第三次握手的 ACK 段的 seq 与 ack；
(3) A 首个数据段的 seq；B 收到该段后回的 ACK 号。

【模板】SYN 占 1 个号、FIN 占 1 个号、每个数据字节占 1 个号；**ack = 期望收到的下一个序号**；握手后数据起始 seq = 自己的 ISN + 1。

【解】A→B SYN：seq=1000（SYN 占掉 1000 这个号）｜B→A SYN+ACK：seq=**3000**，ack=**1001**｜A 第三条 ACK：seq=**1001**，ack=**3001**｜A 首个数据段：seq=**1001**（100 字节占 1001–1100）｜B 回 ACK：ack=**1101**。

【变式】A 再发 200 字节后关闭（发 FIN），B 不发数据直接关闭。求 A 的 FIN 的 seq、B 对该 FIN 的 ack、B 的 FIN 的 seq、A 对 B 的 FIN 的 ack。
【解】200 字节占 1101–1300 → A 的 FIN seq=**1301**，B 回 ack=**1302**；B 的 SYN 已占 3000 且无数据 → B 的 FIN seq=**3001**，A 回 ack=**3002**。
【易错】B 的 FIN 是 ISN+2 而不是 ISN+1——**SYN 占号**这一条在握手方向上最容易被忽略；纯 ACK（第三次握手）不消耗序号，所以 A 的数据段 seq 与第三条 ACK 的 seq 相同（都是 1001）。

**题型 2：发送窗口 = min(rwnd, cwnd)**（★核心 · lab 与 408 的最大差异点）

【题】A 向 B 发送数据，B 通告 rwnd = 2000 字节。A 当前 snd_una = 1000，snd_nxt = 2500。
(1) 不考虑拥塞控制，A 还能发送多少字节？
(2) 若 B 的 ACK 把 snd_una 推进到 1500（rwnd 仍 2000），A 还能发多少？
(3) 若同时 cwnd = 1500（408 视角），发送窗口与还能发的字节数？

【模板】发送窗口 = **min(rwnd, cwnd)**；还能发 = 发送窗口 − 已发未确认 = min(rwnd, cwnd) − (snd_nxt − snd_una)。

【解】(1) 2000 − (2500−1000) = **500** 字节。(2) 2000 − (2500−1500) = **1000** 字节。(3) min(2000, 1500) = 1500；1500 − 1500 = **0** 字节。

【CS144 对位】check3 的 TCPSender **没有 cwnd**，lab 里只有 (1)(2) 的算法；408 真题必须先取 min。这是 §2.8「没有拥塞控制」在考试侧的直接后果——**别把 lab 习惯带进考场**。

**题型 3：RTO 两种考法**（☆常规 · 课本加权平均 vs lab 指数退避）

【题】(1) 课本法：RTT 估计值 RTTs = 100 ms，新样本 SampleRTT = 200 ms，α = 1/8，求新 RTTs。(2) lab 法：CS144 初始 RTO = 1000 ms，连续两次超时重传（窗口非零），RTO 依次变成多少？之后收到确认新数据的 ACK，RTO 变多少？(3) 连续重传达到 `MAX_RETX_ATTEMPTS = 8` 时，上层的 TCPConnection 做什么？

【解】(1) RTTs_new = (1 − 1/8)×100 + (1/8)×200 = 87.5 + 25 = **112.5 ms**。(2) 1000 → **2000** → **4000**（每次超时翻倍）；新 ACK 后**复位回初始值 1000**（不是减半）。(3) 判定连接不可救，**放弃连接并把流出错**（对外表现为 RST，对端 stream `set_error`）。

【易错】(2) 里"RTO 翻倍"仅在窗口非零时伴随"连续重传计数 +1"一起发生；复位目标是**初始值**。课本的 RTO 公式（RTO = RTTs + 4×RTTd）408 也要会，但 CS144 没实现它——两边都别混。

**题型 4：零窗口与坚持探测**（★核心 · check3 明文规定）

【题】B 通告 window_size = 0。(1) 408 术语：A 应启动什么、发什么？为什么不能干等？(2) CS144 里 `push()` 怎么处理？这条规定的适用边界是什么？(3) 接收窗口随后恢复为非零，连接为什么不会自动解锁？

【解】(1) 启动**坚持定时器**，周期性发送**零窗口探测报文**；(2) `push()` **假装窗口 = 1**，发一个可能被拒收的字节去"戳"出一个携带新窗口通告的 ACK——**假装只发生在本次 push 内部，不能把假窗口 1 存进成员**；(3) 接收方没有"窗口恢复"的主动通知，窗口通告只能**搭 ACK 的顺风车**——不探测就永远等不到新 ACK，死锁。

### 8.2 网络层（15-网络层 · 对位 check6）

**题型 5：最长前缀匹配 + 默认路由 + 直连交付**（★核心 · 一题覆盖 check6 全部语义）

【题】某路由器的路由表：

| 路由 | 下一跳 | 接口 |
|---|---|---|
| 10.0.0.0/8 | （直连） | 0 |
| 10.1.0.0/16 | 10.0.0.5 | 1 |
| 10.1.128.0/17 | 10.0.0.9 | 1 |
| 0.0.0.0/0 | 192.168.1.1 | 2 |

四个目的地址各从哪个接口转发、下一跳是谁？① 10.1.130.5　② 10.1.5.5　③ 10.200.1.1　④ 172.16.0.1

【模板】逐条判 `(dst & mask) == (prefix & mask)`；在成立的里面挑 **prefix_length 最大**的；/0 默认路由永远匹配但优先级最低；**直连路由（下一跳为空）把目的地址本身当下一跳**。

【解】
① 匹配 /8、/16、/17（第三字节 130 ≥ 128，落在 10.1.128.0–10.1.255.255）→ **/17，接口 1，下一跳 10.0.0.9**。
② 匹配 /8、/16（5 < 128，不中 /17）→ **/16，接口 1，下一跳 10.0.0.5**。
③ 匹配 /8（第三字节 200 ≠ 1，不中 /16 与 /17）→ **接口 0，直连，下一跳 = 目的地址 10.200.1.1 本身**。
④ 只有 /0 匹配 → **接口 2，下一跳 192.168.1.1**。

【易错】③ 的"直连时下一跳 = 目的地"与 ④ 的"/0 兜底"各占一半分值；写出 & 掩码比较过程比背结论重要。
【CS144 对位】这正是 `Router::route()` 里 `next_hop` 为 `optional` 的语义；掩码构造时 `prefix_length == 0` 必须特判（32 位移 32 位是 UB，sanitizer 会抓）。

**题型 6：TTL 与首部校验和**（☆常规）

【题】TTL = 1 的分组到达路由器，如何处理？TTL = 2 呢（转发后首部哪个字段变化、还需做什么）？408 视角：前一种情况真实路由器还会做什么（CS144 官方不要求）？

【解】TTL = 1：减 1 后为 0 → **丢弃**；408 还要答：**向源点发 ICMP 时间超时差错报告**（CS144 明说不要求实现，但考点照考——traceroute 正靠它工作）。TTL = 2：正常转发，TTL 变 1，**首部校验和必须重算**（首部任一字段变了都要重算）。【易错】不是"转发一个 TTL=0 的包"。

### 8.3 链路层与 ARP（14 / 15 · 对位 check5 / check1）

**题型 7：ARP 的两种场景**（★核心 · check5 第一号语义坑）

【题】主机 A（192.168.0.10/24，MAC = A）要发数据给同网段 B（192.168.0.20/24）与跨网段 C（10.0.0.1，默认网关 G = 192.168.0.1）。A 的 ARP 缓存为空。
(1) A 要发几个 ARP 请求？请求的"目标 IP 字段"分别是什么？帧的目的 MAC 是什么？谁回应？
(2) A 发往 C 的帧里，目的 IP 与目的 MAC 分别是什么？A 实际解析的是谁的 MAC？
(3) 用 CS144 的接口表述：`send_datagram(dgram, next_hop)` 的 next_hop 两种场景各取什么？

【模板】**IP 层端到端不变，MAC 层逐跳变；ARP 解析的永远是"下一跳"**（同网段 = 目的主机本身，跨网段 = 默认网关）。

【解】(1) 两个请求：目标 IP 分别为 **192.168.0.20**（B）与 **192.168.0.1**（G）；帧目的 MAC 均为**广播 ff:ff:ff:ff:ff:ff**；只有被询问的那台主机以**单播 reply** 回应（reply 携带自己的 MAC，请求方顺路学习 30 秒）。(2) 目的 IP = **10.0.0.1（C，端到端不变）**，目的 MAC = **G 的 MAC**；A 解析的是**网关的 MAC**。(3) 同网段 next_hop = B 的 IP；跨网段 next_hop = G 的 IP——**绝不是 C 的 IP**（check5 官方脚注专门警告的那条混淆）。

**题型 8：GBN / SR 窗口上限与 32 位序号**（★核心 · check1 / check2 对位）

【题】(1) 序号字段 3 位（0–7）：GBN 与 SR 的发送窗口上限各多少？SR 两窗口满足什么关系？(2) TCP 序号 32 位、窗口字段只有 16 位（≤ 65535）：结合 CS144 说明为什么工程上不担心"序号回绕导致新旧分组混淆"？(3) check1 的 Reassembler 里"接收窗口的内存上限"公式是什么？

【解】(1) GBN：W ≤ 2^3 − 1 = **7**（留一个序号当分界）；SR：W ≤ 2^(3−1) = **4**，约束 **W_发送 + W_接收 ≤ 2^n**（4 + 4 = 8）。(2) 三重护栏：**ISN 随机**（新连接序号区间与旧连接错开，check2 官方给的理由）、**窗口 ≤ 65535 远小于 2^31**（一个窗口内的序号跨度不会绕进重叠区）、**分组寿命有限（MSL）**；check2 的 `unwrap` 取"离 checkpoint 最近"正是在窗口跨度 < 2^31 的前提下消歧。(3) `first_unacceptable = bytes_pushed + available_capacity = capacity + bytes_popped`——重组器内部（红）+ ByteStream 缓冲（绿）两块合计不超过 capacity。

**题型 9：最小帧长与 lab 边界**（☆常规 · "现实边界"怎么用）

【题】CS144 的 `EthernetFrame` 不做 FCS 校验、不做 64 字节最小帧长填充，照样跑通全部测试。(1) 真实以太网 64 字节下限是为谁服务的？(2) 为什么 CS144 可以不做？(3) 这条"lab 缺席"对 408 意味着什么？

【解】(1) 为 **CSMA/CD 冲突检测**服务：帧太短会在检测到冲突前发完，发送方误判成功——所以 64B 下限的来历 = 争用期内必须还在发送（512 bit 时间），它**不是帧语义的一部分**。(2) CS144 的链路是虚拟网口/交换式全双工链路，**没有冲突域**，CSMA/CD 整体缺席；FCS 由真实网卡硬件处理，教学栈只管"形状对"。(3) **lab 缺席 ≠ 考点缺席**：408 照考 64B 的来历与争用期计算——这正是 §2.8"现实边界清单"的用法：每条 lab 简化都要能反向说出"课本考什么"。

### 8.4 对位总表（题号 × 教材分块 × CS144 来源）

| 题型 | 教材分块 | CS144 来源 | 优先级 |
|---|---|---|---|
| 1 握手/挥手序号推算 | 16 块3 连接管理 | check2 三套编号 + check4 | ★核心 |
| 2 发送窗口 min(rwnd, cwnd) | 16 块4 可靠传输 | check3（纯 rwnd 对照） | ★核心 |
| 3 RTO 两种考法 | 16 块4 | check3 计时六律 | ☆常规 |
| 4 零窗口/坚持探测 | 16 块4 | check3 明文规定 | ★核心 |
| 5 最长前缀匹配/默认路由/直连 | 15 块2 路由表 | check6 | ★核心 |
| 6 TTL/首部校验和 | 15 块2 | check6 | ☆常规 |
| 7 ARP 两种场景 | 15 网络层（ARP） | check5 | ★核心 |
| 8 GBN/SR 窗口上限 | 14 链路层 + 16 块4 | check1/check2 | ★核心 |
| 9 最小帧长/CSMA/CD | 14 链路层 | check5 的边界 | ☆常规 |

> 以上题目与解答同时以 `[CS144·验收]` cell 归档进对应 ipynb（14 / 15 / 16），复习计划随 cell 走。

---

## 迁移归档：来自旧 ipynb 的工程笔记（2026-10-28）

## [CS144①] 设计理念：C++ 为什么能替换 Linux 网络协议栈

> 2026-10-20 · 来源：CS144 项目重修（learning-408/cs144 实读 + check0–7 官方 PDF）

- **我的理解**（本条由代码 + 官方 PDF 推导，非对话原话）：替换不是劫持内核，而是**重建** —— 你的 TCP/IP 就是一个普通用户态进程。三条支撑事实：

  1. **唯一的契约是文件描述符**：`Socket` / `TunFD` / `TapFD` / stdin 全都继承自 `FileDescriptor`（`cs144/util/file_descriptor.hh`，引用计数持有 fd）。整个 Minnow 里数据流动只有 `read()` 和 `write()`。

  2. **每层的形状被压成同一种**：一个 struct + 一对 `parse(Parser&)` / `serialize(Serializer&)`，报文本身是 `vector<string>`（`cs144/util/parser.hh`）。剥一层头就 `remove_prefix`，下一层接着剥。

  3. **时间只有两个来源**：`EventLoop`（poll 封装，真实事件）与 `tick(ms)`（协议内虚拟时间，check3 明文禁止碰真实时钟）。

- **出站方式的三个等级**（check5 官方 PDF §0 原文列举）：

  1. **TCP-in-UDP-in-IP** —— 用 `UDPSocket`，内核写 UDP/IP/以太头，你只给 payload 和目的地址；

  2. **TCP-in-IP** —— 用 **TUN 设备**，你写完整 IP 头，内核写以太头并真发；

  3. **TCP-in-IP-in-Ethernet** —— 用 **TAP** 或 `AF_PACKET`，连以太头和 ARP 都自己写。

- **一句话串起来**：每往后做一个 checkpoint，就把「内核帮忙写的那部分头」拿走一层变成自己写。

- **项目映射**（出处：`cs144/util/tun.cc`、`cs144/scripts/tun.sh`、`cs144/apps/tcp_ipv4.cc`）：`open('/dev/net/tun')` + `ioctl(TUNSETIFF, IFF_TUN|IFF_NO_PI)` 把进程 fd 与虚拟网卡焊死；`tun.sh` 再补三件事 —— 给 `169.254.144.1/24`（link-local 段）、`iptables ... MASQUERADE`（NAT）、`ip_forward=1`。**最后一公里（以太网 + 出物理网卡 + NAT）仍是内核干的**：内核在这里是被当成传输介质，不是被替换掉。

- **真正的替换点在 socket 层**（`cs144/util/tcp_minnow_socket.hh`）：`TCPMinnowSocket` 继承 `LocalStreamSocket`（它仍然是 Socket、仍然是 fd），内部另起一个线程跑 `TCPPeer` + `EventLoop`。官方注释原话大意是：「另一个线程负责本来由内核替 TCPSocket 做的那些后端活」。于是 check4 的全部改动只有一行：把 `webget.cc` 里的 `TCPSocket` 换成 `CS144TCPSocket`。

- **考试侧重点**：① 分层与封装（每层各加谁的头）；② IPv4 首部字段的现实含义（TTL / 首部校验和 / 协议字段 6=TCP）；③ NAT 与私有地址的现实后果。

- **易错点**：以为「替换」等于「内核彻底不参与」 —— 错。`NetworkInterface` 之前的链路层一跳一直是 Linux 代劳的（见 check5 才会自己写以太头 + ARP）；以为 cs144 里有拥塞控制 —— 没有，那里的窗口就是纯 rwnd。

- **待解决问题**：这条线索在 check5（以太头自己写）之后值得再回看一次。

- **复习计划**：R1 @ 2026-10-21 · R2 @ 2026-10-23 · R3 @ 2026-10-27

---

## [CS144②] 网络接口与 ARP（check5）

> 2026-10-20 · 来源：CS144 项目重修（learning-408/cs144 实读 + check0–7 官方 PDF）

- **我的理解**（Evidence-based）：`NetworkInterface` 是 IP 世界与以太网世界之间的唯一翻译官，**同一份代码被复用两次** —— 作为主机 TCP/IP 栈的最底层，也作为路由器的一块网卡（check5 官方图 1 左右两侧）。

- **项目映射**（出处：`cs144` 分支 `origin/check7-startercode:src/network_interface.hh`）：三个方法 `send_datagram(dgram, next_hop)` / `recv_frame(frame)` / `tick(ms)`；发送靠虚函数口 `OutputPort::transmit()`（依赖注入，单测可插一个假的网口）；学到的 IP→MAC 映射只留 **30 秒**；同一个 IP 的 ARP request **5 秒内不重发**。

- **核心机制**：未知下一跳 MAC → 广播 ARP request + **把数据报排队**；reply 与 request 里的 sender 信息都顺手学（30 s）；目标 MAC 既不是广播也不是自己的帧一律忽略；IPv4 帧解析成功才塞进 `datagrams_received()`。

- **为什么值得做**：这三个动作就是课本上「MAC 地址 + ARP」那几页的实现版，做完以后「有了 IP 为什么还要 MAC 地址」这道题就不是背出来的了。

- **考试侧重点**：★链路层必考。以太网帧格式、MAC 寻址、ARP 三步（广播请求 / 单播响应 / 缓存）、以及 ARP 缓存带来的首次延迟。

- **易错点**：① **把最终目的地当成下一跳**（check5 PDF 用脚注专门警告，全 lab 第一号语义错误）；② 5 秒抑制是「同一 IP」，不是全局限流；③ request 和 reply 里的 sender 信息都要缓存；④ 只有 target IP 等于自己的 IP 才回 reply。

- **边界**：真实系统还会做 gratuitous ARP、重复地址检测、ARP 长时间无回应后回 ICMP host unreachable（官方明说 lab 不需要做）。这几条 408 不考。

- **复习计划**：R1 @ 2026-10-21 · R2 @ 2026-10-23 · R3 @ 2026-10-27

---

## [CS144·验收] 真题对位变式：GBN/SR 窗口与最小帧长（§8 题型 8–9）

> 2026-10-22 · 来源：CS144 真题对位变式（自编，题目与解答真源 = `projects/cs144/NOTES.md` §8.3；全部答案先手算复核再落盘）

- **用法（对齐 LEARNING.md §六）**：限时作答——选择 2 分钟、大题 15–20 分钟；先遮住【解】自己算，再对答案。卡住的题回 `projects/cs144/NOTES.md` §3.1 / §3.5 / §2.8 回补，并按归因维度记账：概念不清 / 计算失误 / 没记住 / 审题错 / 项目误导 / 存疑待核。

**题型 8：GBN / SR 窗口上限与 32 位序号**（★核心 · check1 / check2 对位）

【题】(1) 序号字段 3 位（0–7）：GBN 与 SR 的发送窗口上限各多少？SR 两窗口满足什么关系？
(2) TCP 序号 32 位、窗口字段只有 16 位（≤ 65535）：结合 CS144 说明为什么工程上不担心「序号回绕导致新旧分组混淆」？
(3) check1 的 Reassembler 里「接收窗口的内存上限」公式是什么？

【解】(1) GBN：$W \le 2^3 - 1 = 7$（留一个序号当分界）；SR：$W \le 2^{3-1} = 4$，约束 $W_{\text{发送}} + W_{\text{接收}} \le 2^n$（4 + 4 = 8）。
(2) 三重护栏：**ISN 随机**（新连接序号区间与旧连接错开，check2 官方给的理由）、**窗口 ≤ 65535 远小于 $2^{31}$**（一个窗口内的序号跨度不会绕进重叠区）、**分组寿命有限（MSL）**；check2 的 unwrap 取「离 checkpoint 最近」正是在窗口跨度 < $2^{31}$ 的前提下消歧。
(3) first_unacceptable = bytes_pushed + available_capacity = capacity + bytes_popped——重组器内部（红）+ ByteStream 缓冲（绿）两块合计不超过 capacity。

**题型 9：最小帧长与 lab 边界**（☆常规 · 「现实边界」怎么用）

【题】CS144 的 EthernetFrame 不做 FCS 校验、不做 64 字节最小帧长填充，照样跑通全部测试。
(1) 真实以太网 64 字节下限是为谁服务的？
(2) 为什么 CS144 可以不做？
(3) 这条「lab 缺席」对 408 意味着什么？

【解】(1) 为 **CSMA/CD 冲突检测**服务：帧太短会在检测到冲突前发完，发送方误判成功——64B 下限的来历 = 争用期内必须还在发送（512 bit 时间），它**不是帧语义的一部分**。
(2) CS144 的链路是虚拟网口/交换式全双工链路，**没有冲突域**，CSMA/CD 整体缺席；FCS 由真实网卡硬件处理，教学栈只管「形状对」。
(3) **lab 缺席 ≠ 考点缺席**：408 照考 64B 的来历与争用期计算——这正是 `CS144.md` §2.8「现实边界清单」的用法：每条 lab 简化都要能反向说出「课本考什么」。

- **复习计划**：R1 @ 2026-10-23 · R2 @ 2026-10-25 · R3 @ 2026-10-29

---

## [CS144③] IP 路由器与最长前缀匹配（check6）

> 2026-10-20 · 来源：CS144 项目重修（learning-408/cs144 实读 + check0–7 官方 PDF）

- **我的理解**（Evidence-based）：路由器只回答两个问题 —— 从**哪个接口**发出去、交给**哪个下一跳**。这两个判断全部来自一张 match-action 路由表，不需要任何 TCP / ARP / 以太网的知识。

- **项目映射**（出处：`cs144` 分支 `origin/check7-startercode:src/router.hh`）：`add_route(route_prefix, prefix_length, optional<Address> next_hop, size_t interface_num)` + `route()` + `interface(N)`；官方例子：`18.47.0.0/16` ⇒ prefix = 18×2^24 + 47×2^16 = 305070080，length = 16。默认路由即 `prefix_length == 0`。

- **核心机制**：① 匹配 = 目的地址的最高 N 位与 prefix 的最高 N 位相同；② 在匹配成功的路由里挑 **prefix_length 最大**的（最长前缀匹配）；③ 无匹配 → 丢；④ TTL：本来就是 0 或减完变 0 都丢；⑤ next_hop 为空（直连路由）→ 用数据报的目的 IP 当下一跳；⑥ 递减 TTL 后**必须重算首部校验和**，再交给 `interface(N)->send_datagram()`。

- **为什么这样设计**（check6 PDF 原文大意）：路由器从不关心 TCP、ARP 或以太网帧，甚至不知道链路层长什么样 —— 它只和 Internet datagram 打交道，只通过 `NetworkInterface` 这一层抽象去碰链路层。这就是 check5 被单独拆成一个零件的原因。

- **考试侧重点**：★网络层核心。路由聚合、最长前缀匹配、TTL、IPv4 首部校验和、直接交付 vs 间接交付。

- **易错点**：① **移位 UB** —— `0xffffffff << (32 - prefix_length)`，当 `prefix_length == 0` 时就是把 32 位整数移 32 位，属未定义行为；官方说测试跑 sanitizer 会抓到，**默认路由必须特判**；② 改了 TTL 忘了重算校验和（下一跳直接丢）；③ 直连路由 next_hop 为空的情况；④ `ipv4_numeric()` / `from_ipv4_numeric()` 用反。

- **待解决问题**：无。check6 代码只要 30–60 行，是全系列性价比最高的一个 check。

- **复习计划**：R1 @ 2026-10-21 · R2 @ 2026-10-23 · R3 @ 2026-10-27

---

## [CS144·验收] 真题对位变式：路由匹配、TTL 与 ARP（§8 题型 5–7）

> 2026-10-22 · 来源：CS144 真题对位变式（自编，题目与解答真源 = `projects/cs144/NOTES.md` §8.2/§8.3；全部答案先手算复核再落盘）

- **用法（对齐 LEARNING.md §六）**：限时作答——选择 2 分钟、大题 15–20 分钟；先遮住【解】自己算，再对答案。卡住的题回 `projects/cs144/NOTES.md` §3.6 / §3.5 回补，并按归因维度记账：概念不清 / 计算失误 / 没记住 / 审题错 / 项目误导 / 存疑待核。
- **归属说明**：教材把 ARP 划在**网络层**（15），而 CS144 check5 的实现视角 cell 已落在 14（[CS144②] 网络接口与 ARP）。两边都算数：本 cell 的题型 7 补的是**教材考点视角**。

**题型 5：最长前缀匹配 + 默认路由 + 直连交付**（★核心 · 一题覆盖 check6 全部语义）

【题】某路由器的路由表：

| 路由 | 下一跳 | 接口 |
|---|---|---|
| 10.0.0.0/8 | （直连） | 0 |
| 10.1.0.0/16 | 10.0.0.5 | 1 |
| 10.1.128.0/17 | 10.0.0.9 | 1 |
| 0.0.0.0/0 | 192.168.1.1 | 2 |

四个目的地址各从哪个接口转发、下一跳是谁？① 10.1.130.5　② 10.1.5.5　③ 10.200.1.1　④ 172.16.0.1

【模板】逐条判 $(\text{dst} \,\&\, \text{mask}) == (\text{prefix} \,\&\, \text{mask})$；在成立的里挑 **prefix_length 最大**的；/0 默认路由永远匹配但优先级最低；**直连路由把目的地址本身当下一跳**。

【解】① 匹配 /8、/16、/17（第三字节 130 ≥ 128，落在 10.1.128.0–10.1.255.255）→ **/17，接口 1，下一跳 10.0.0.9**。
② 匹配 /8、/16（5 < 128，不中 /17）→ **/16，接口 1，下一跳 10.0.0.5**。
③ 匹配 /8（第三字节 200 ≠ 1，不中 /16 与 /17）→ **接口 0，直连，下一跳 = 目的地址 10.200.1.1 本身**。
④ 只有 /0 匹配 → **接口 2，下一跳 192.168.1.1**。

【易错】③ 的「直连时下一跳 = 目的地」与 ④ 的「/0 兜底」各占一半分值；写出 & 掩码比较过程比背结论重要。
【CS144 对位】这正是 `Router::route()` 里 next_hop 为 optional 的语义；掩码构造时 prefix_length == 0 必须特判（32 位移 32 位是 UB，sanitizer 会抓）。

**题型 6：TTL 与首部校验和**（☆常规）

【题】TTL = 1 的分组到达路由器，如何处理？TTL = 2 呢（转发后首部哪个字段变化、还需做什么）？408 视角：前一种情况真实路由器还会做什么（CS144 官方不要求）？

【解】TTL = 1：减 1 后为 0 → **丢弃**；408 还要答：**向源点发 ICMP 时间超时差错报告**（CS144 明说不要求实现，但考点照考——traceroute 正靠它工作）。TTL = 2：正常转发，TTL 变 1，**首部校验和必须重算**（首部任一字段变了都要重算）。

【易错】不是「转发一个 TTL=0 的包」。

**题型 7：ARP 的两种场景**（★核心 · check5 第一号语义坑）

【题】主机 A（192.168.0.10/24，MAC = A）要发数据给同网段 B（192.168.0.20/24）与跨网段 C（10.0.0.1，默认网关 G = 192.168.0.1）。A 的 ARP 缓存为空。
(1) A 要发几个 ARP 请求？请求的「目标 IP 字段」分别是什么？帧的目的 MAC 是什么？谁回应？
(2) A 发往 C 的帧里，目的 IP 与目的 MAC 分别是什么？A 实际解析的是谁的 MAC？
(3) 用 CS144 的接口表述：send_datagram(dgram, next_hop) 的 next_hop 两种场景各取什么？

【模板】**IP 层端到端不变，MAC 层逐跳变；ARP 解析的永远是「下一跳」**（同网段 = 目的主机本身，跨网段 = 默认网关）。

【解】(1) 两个请求：目标 IP 分别为 **192.168.0.20**（B）与 **192.168.0.1**（G）；帧目的 MAC 均为**广播 ff:ff:ff:ff:ff:ff**；只有被询问的那台主机以**单播 reply** 回应（reply 携带自己的 MAC，请求方顺路学习 30 秒）。
(2) 目的 IP = **10.0.0.1（C，端到端不变）**，目的 MAC = **G 的 MAC**；A 解析的是**网关的 MAC**。
(3) 同网段 next_hop = B 的 IP；跨网段 next_hop = G 的 IP——**绝不是 C 的 IP**（check5 官方脚注专门警告的那条混淆）。

- **复习计划**：R1 @ 2026-10-23 · R2 @ 2026-10-25 · R3 @ 2026-10-29

---

## [CS144④] TCP 的三套序号与 ARQ（check2 + check3）

> 2026-10-20 · 来源：CS144 项目重修（learning-408/cs144 实读 + check0–7 官方 PDF）

- **我的理解**（Evidence-based）：TCP 在这套实现里被拆成两个方向的对偶件 —— check2 负责收端（乱序段 → 有序流），check3 负责发端（流 → 段 + 重传）。两端之间只靠 `TCPSenderMessage` / `TCPReceiverMessage` 两个纯数据结构接缝，所以能各自单测。

- **三套编号必须分清**（check2 PDF 的 'cat' 例子，★分清就是得分点）：seqno（32 位、从随机 ISN 起、**含** SYN/FIN、会回绕）/ absolute seqno（64 位、从 0 起、含 SYN/FIN）/ stream index（64 位、从 0 起、**不含** SYN/FIN）。换算：`stream_index = absolute_seqno - 1`；32↔64 的跨越靠 `Wrap32::wrap / unwrap(zero_point, checkpoint)`，checkpoint 取 first unassembled。

- **receiver 侧的两个信号**（`cs144` 骨架 `util/tcp_receiver_message.hh`）：`ackno`（optional，收到 SYN 之前为空）+ `window_size`（上限 65535 = UINT16_MAX）+ `RST`；window_size 的含义是「从 ackno 起我还愿意收多少个序号」。

- **sender 侧的计时六条**（check3 PDF §2.1）：禁止碰真实时钟（只能用 tick）；发出任何占序号空间的段时若 timer 未开则开；全部被确认则停表；到期重传**最早**那一个；若窗口非零则连续重传计数 +1 且 **RTO 翻倍**；收到新 ACK → RTO 复位回初值、有 outstanding 就重启 timer、连续重传计数清零。

- **考试侧重点**：★必考区。序号针对字节编号、SYN/FIN 各消耗一个序号、确认号的含义、ARQ 与超时重传、RTO 指数退避、**零窗口死锁与零窗口探测**。

- **易错点**：① `unwrap` 里拿有符号的 `abs()` 比距离（应该用无符号 mod 2^32 的距离比较）；② 第二个 SYN 到了就把 ISN 重设（不该）；③ 忘记把 window_size 截断到 65535；④ 零窗口时以为要把「假窗口 1」存进成员（只在 `push()` 内部假装一次，用来「戳」出一个新 ACK）；⑤ 把三段合并成一个大段重传（官方不允许）；⑥ 混淆 —— lab 里没有 cwnd，那里的窗口就是纯 rwnd。

- **边界**：check3 PDF 写 `MAX_PAYLOAD_SIZE` 是 1452，而实际骨架 `util/tcp_config.hh` 里是 1000（`TIMEOUT_DFLT = 1000`、`MAX_RETX_ATTEMPTS = 8`、`CAPACITY = 64000`）。**以自己 merge 到的骨架为准**；这两个数字不同不影响 408 答题。

- **复习计划**：R1 @ 2026-10-21 · R2 @ 2026-10-23 · R3 @ 2026-10-27

---

## [CS144⑤] check4：把你的 TCP 推到真实互联网上

> 2026-10-20 · 来源：CS144 项目重修（learning-408/cs144 实读 + check0–7 官方 PDF）

- **我的理解**（Evidence-based）：check4 几乎不写新代码，它是**验收**而不是开发 —— 回答的是「能不能通」「不通时错在哪」。

- **项目映射**（出处：`cs144/apps/tcp_ipv4.cc`、`cs144/util/tcp_over_ip.cc`、`cs144/src/tcp_minnow_socket.cc`）：调用链 `TunFD('tun144') → TCPOverIPv4OverTunFdAdapter → LossyFdAdapter → TCPMinnowSocket → bidirectional_stream_copy`（最后一层与 `tcp_native` 完全一致）。重点读 `wrap_tcp_in_ip()`：设 src/dst IP → 借 `ip_dgram.header.pseudo_checksum()` 算 TCP 校验和 → 序列化填进 payload → 再 `ip_dgram.header.compute_checksum()`。顺序不能反。

- **关键路径**：`./scripts/tun.sh start 144`（**每次重启 VM 都要重跑**）→ 把 `webget.cc` 里的 `TCPSocket` 换成 `CS144TCPSocket` → `cmake --build build --target check_webget`。

- **调试的黄金三角**：`tcp_ipv4 169.254.144.1 9090`（你的 TCP 做客户端）+ `tcp_native -l 0 9090`（内核 TCP 做服务端，参照组）+ `tshark -i tun144 -vvv`（站在网线上看包）。上层代码是同一套 → **跑不通，错误百分之百在你这边**。

- **考试侧重点**：连接管理（握手 / 挥手 / TIME_WAIT）的实战锚点。另外 check4 还要求一份 2 小时 ping 的统计报告 —— 那正好是课本里「丢包到底是 Bernoulli 还是突发」的一次实证。

- **易错点**：① 忘了跑 `tun.sh`（TUN 设备不存在）；② 调试信息打到 `cout`（污染 HTTP body，必须 `cerr`）；③ 算 TCP 校验和时漏掉伪首部 `pseudo_checksum()` → 对端**静默丢包**；④ ISN 没换成随机（`TCPConfig` 默认 `Wrap32{137}` 是给单测用的确定性值）；⑤ 忽视最后的 lingering（`TCPPeer::active()`：`10 * rt_timeout`，默认 10 s）→ 连接提前销毁、对端收到 RST。

- **待解决问题**：2 小时 ping 报告属复习以外的任务，优先级最低；真要做时按官方 10 问清单跑（丢包率 / 最长连续成功 / 最长突发丢失 / 条件概率 / RTT 时序图 / RTT 分布 / 相邻 RTT 相关性）。

- **复习计划**：R1 @ 2026-10-21 · R2 @ 2026-10-23 · R3 @ 2026-10-27

---

## [CS144·验收] 真题对位变式：连接管理与滑动窗口（§8 题型 1–4）

> 2026-10-22 · 来源：CS144 真题对位变式（自编，题目与解答真源 = `projects/cs144/NOTES.md` §8.1；全部答案先手算复核再落盘）

- **用法（对齐 LEARNING.md §六）**：限时作答——选择 2 分钟、大题 15–20 分钟；先遮住【解】自己算，再对答案。卡住的题回 `projects/cs144/NOTES.md` §3.2 / §3.3 / §3.4 回补，并按归因维度记账：概念不清 / 计算失误 / 没记住 / 审题错 / 项目误导 / 存疑待核。

**题型 1：握手与挥手的序号推算**（★核心 · 对位 check2「三套编号」+ check4 连接管理）

【题】主机 A 与 B 建立 TCP 连接，A 的 ISN = 1000，B 的 ISN = 3000。握手完成后 A 立即发送一段 100 字节的数据。求：
(1) B 的 SYN+ACK 段的 seq 与 ack；
(2) A 的第三次握手的 ACK 段的 seq 与 ack；
(3) A 首个数据段的 seq；B 收到该段后回的 ACK 号。

【模板】SYN 占 1 个号、FIN 占 1 个号、每个数据字节占 1 个号；**ack = 期望收到的下一个序号**；握手后数据起始 seq = 自己的 ISN + 1。

【解】B→A SYN+ACK：seq=**3000**，ack=**1001**｜A 第三条 ACK：seq=**1001**，ack=**3001**｜A 首个数据段：seq=**1001**（100 字节占 1001–1100）｜B 回 ACK：ack=**1101**。

【变式】A 再发 200 字节后关闭（发 FIN），B 不发数据直接关闭。求 A 的 FIN 的 seq、B 对该 FIN 的 ack、B 的 FIN 的 seq、A 对 B 的 FIN 的 ack。
【解】200 字节占 1101–1300 → A 的 FIN seq=**1301**，B 回 ack=**1302**；B 的 SYN 已占 3000 且无数据 → B 的 FIN seq=**3001**，A 回 ack=**3002**。

【易错】B 的 FIN 是 ISN+2 而不是 ISN+1——**SYN 占号**在握手方向上最容易被忽略；纯 ACK（第三次握手）不消耗序号，所以 A 的数据段 seq 与第三条 ACK 的 seq 相同（都是 1001）。

**题型 2：发送窗口 = min(rwnd, cwnd)**（★核心 · lab 与 408 的最大差异点）

【题】A 向 B 发送数据，B 通告 rwnd = 2000 字节。A 当前 snd_una = 1000，snd_nxt = 2500。
(1) 不考虑拥塞控制，A 还能发送多少字节？
(2) 若 B 的 ACK 把 snd_una 推进到 1500（rwnd 仍 2000），A 还能发多少？
(3) 若同时 cwnd = 1500（408 视角），发送窗口与还能发的字节数？

【模板】发送窗口 $= \min(\text{rwnd}, \text{cwnd})$；还能发 = 发送窗口 − 已发未确认 $= \min(\text{rwnd}, \text{cwnd}) - (\text{snd\_nxt} - \text{snd\_una})$。

【解】(1) 2000 − (2500−1000) = **500** 字节。(2) 2000 − (2500−1500) = **1000** 字节。(3) min(2000, 1500) = 1500；1500 − 1500 = **0** 字节。

【CS144 对位】check3 的 TCPSender **没有 cwnd**，lab 里只有 (1)(2) 的算法；408 真题必须先取 min。这是 `CS144.md` §2.8「没有拥塞控制」在考试侧的直接后果——**别把 lab 习惯带进考场**。

**题型 3：RTO 两种考法**（☆常规 · 课本加权平均 vs lab 指数退避）

【题】(1) 课本法：RTT 估计值 RTTs = 100 ms，新样本 SampleRTT = 200 ms，α = 1/8，求新 RTTs。
(2) lab 法：CS144 初始 RTO = 1000 ms，连续两次超时重传（窗口非零），RTO 依次变成多少？之后收到确认新数据的 ACK，RTO 变多少？
(3) 连续重传达到 MAX_RETX_ATTEMPTS = 8 时，上层的 TCPConnection 做什么？

【解】(1) RTTs_new = (1 − 1/8)×100 + (1/8)×200 = 87.5 + 25 = **112.5 ms**。
(2) 1000 → **2000** → **4000**（每次超时翻倍）；新 ACK 后**复位回初始值 1000**（不是减半）。
(3) 判定连接不可救，**放弃连接并把流出错**（对外表现为 RST，对端 stream set_error）。

【易错】(2) 里「RTO 翻倍」仅在窗口非零时伴随「连续重传计数 +1」一起发生；复位目标是**初始值**。课本的 RTO = RTTs + 4×RTTd 公式 408 也要会，但 CS144 没实现它——两边都别混。

**题型 4：零窗口与坚持探测**（★核心 · check3 明文规定）

【题】B 通告 window_size = 0。
(1) 408 术语：A 应启动什么、发什么？为什么不能干等？
(2) CS144 里 push() 怎么处理？这条规定的适用边界是什么？
(3) 接收窗口随后恢复为非零，连接为什么不会自动解锁？

【解】(1) 启动**坚持定时器**，周期性发送**零窗口探测报文**；(2) push() **假装窗口 = 1**，发一个可能被拒收的字节去「戳」出一个携带新窗口通告的 ACK——**假装只发生在本次 push 内部，不能把假窗口 1 存进成员**；(3) 接收方没有「窗口恢复」的主动通知，窗口通告只能**搭 ACK 的顺风车**——不探测就永远等不到新 ACK，死锁。

- **复习计划**：R1 @ 2026-10-23 · R2 @ 2026-10-25 · R3 @ 2026-10-29

---
