# virtualization · QEMU/KVM、容器与 WSL 的同一张成本表

> 本文只回答一个问题：**一台机器是怎么被"切开"的，切开之后每一次跨界要付多少钱。**
> 主角是 QEMU + KVM（硬件虚拟化），配角是容器（namespace/cgroup）与 WSL（ABI 翻译 vs 真内核），
> 因为它们是同一个问题的另外三种答案，不是三个不相干的产品。
> 与 `../jos/`、`../kernel-compare/` 共用页表、特权级、陷入这套词汇；与 `../drivers/` 的分界：
> 那边管"设备怎么被接进内核"，这边管"设备怎么被接进一台虚拟机"；性能方法学不在这里重复，见 `eng/perf-engineering/`。

## 一、它在做什么

把"虚拟机"三个字拆成一句可验证的话：

> **VMM（Virtual Machine Monitor）是一个普通的用户态进程。它靠 CPU 提供的虚拟化扩展获得"切换世界"的能力，
> 靠 OS 提供的接口（`/dev/kvm`、`mmap`、`eventfd`、`vfio`）获得内存、线程与设备，
> 然后在这套硬件与内核给的护栏内，尽量让"客户机直接跑在 CPU 上"，只在必须由软件说话的那一刻才接管。**

这句话里每个词都是可以落地的：**普通用户态进程**（`ps` 能看到 qemu-system-x86_64，被 OOM killer 杀过的人都知道）、
**虚拟化扩展**（VT-x/AMD-V/ARM EL2）、**接口**（`ioctl` 协议 + 共享内存）、
**护栏**（guest 不能碰 host 的内存与设备，靠 EPT 与 IOMMU）、**尽量直接跑**（所以有了整条 I/O 优化谱系）。

由此得到全篇唯一的成本单位：

> **一次 VM exit（从 guest 掉回 VMM 的那一次跨界）就是一次税。**
> 所有虚拟化技术都在回答四个问题之一：**能不能不交**（硬件接管：EPT、APICv）／**能不能一次多干点**（批处理：virtio 环）／
> **能不能换个更便宜的人来收**（下沉：vhost、内核内 `ioeventfd`）／**能不能干脆不跨界**（直通：VFIO、SR-IOV）。

| 材料 | 谁提供 | 具体是什么 | 缺了会怎样 |
|---|---|---|---|
| 世界切换 | CPU | VMX root/non-root、VMCS、`VMLAUNCH`/`VMRESUME`；ARM 的 EL2 与 `HCR_EL2` | 只能靠二进制翻译（TCG）或改客户机内核（半虚拟化） |
| 内存隔离 | CPU + MMU | EPT/NPT 二维页表、VPID/ASID | 只能影子页表：guest 每次改页表都要陷出 |
| 设备隔离 | 芯片组 | IOMMU（VT-d/AMD-Vi）+ 中断重映射 | 直通等于把 DMA 交给不可信代码 |
| 控制接口 | OS | `/dev/kvm` 的 `ioctl` 协议、`mmap` 一块内存当 guest RAM | 没有 KVM 就没有"用户态 VMM"这个形态 |
| 通知与旁路 | OS | `eventfd`、`irqfd`、`ioeventfd`、`userfaultfd`、`vfio` | 每次中断、每次 MMIO 都要绕回用户态 |
| 设备模型 | 用户态 | QEMU 的 QOM 设备、块层、迁移 | 没有"机器"可启动：CPU 有了，板子没有 |

**为什么容器要和 VM 写在同一份文档里**：它们不是两种技术，是**把隔离边界画在不同层**的两个取值。
VM 把边界画在"CPU 的世界切换"上（guest 内核完全不知道自己被虚拟化，硬件负责拦住它）；
容器把边界画在"内核对象的视图"上（同一个内核，用 namespace 换视角、用 cgroup 换配额）。
面试里那句"容器为什么不如 VM 安全"，答案就在这张对照上：**前者的边界由硬件强制，后者由内核软件强制，而内核是共享的。**

**入口（本文的读法）**：在"特权级 + 页表 + 设备 DMA + 通知路径"这四类约束下，把任意一个性能现象归因到
「哪一次跨界、跨界几次、每次带多少活、由谁在 host 侧执行」。换的是产品名（QEMU / Firecracker / runc / WSL），
不换的是同一条链：**指令 → 是否需要 host 帮忙 → 怎么通知 host → host 用哪块内存/哪个 fd 干活 → 怎么把结果送回 guest。**

**不换的是什么**：全程不变的是四条落点——
①**世界的划分**（VMX root vs non-root；或同一内核下的 namespace 视图）；
②**地址翻译**（GVA→GPA→HPA 两级；容器里只有一级，但这正是它便宜的原因）；
③**通知机制**（VM exit / `eventfd` / 中断注入 / futex 唤醒，本质都是"跨执行上下文说一句"）；
④**所有权**（共享内存环的 head/tail 由谁推进、`ioeventfd` 注册在哪个地址、脏页位图由谁清）。

**积木**：①`VMCS` 的 guest-state / host-state / VM-execution controls 三组字段；
它能独立验证"一次 `VMRESUME` 之后 RIP 来自 guest-state 还是 host-state"。
②`EPTE`（EPT 页表项）与 `KVM_SET_USER_MEMORY_REGION` 的 `{slot, guest_phys_addr, userspace_addr, memory_size}`；
它能独立验证"guest 访问 0xFEE00000（APIC）为什么必然退出而访问 RAM 不会"。
③`eventfd` 的计数语义 + `ioeventfd`/`irqfd` 的注册关系；
它能独立验证"一次 virtio kick 有没有经过 QEMU 进程"。

**最小情形**：单 vCPU、单 virtqueue、一个 `virtio-blk` 读请求。
guest 驱动把描述符写进环、更新 `avail->idx`、对 `QueueNotify`（一个 MMIO/PIO 地址）写一次 →
这次写命中 `ioeventfd` → 内核直接 `eventfd_signal` 唤醒 vhost 工作线程，**QEMU 主循环不参与** →
vhost 用 `pread` 读镜像、把结果写进描述符指向的 guest 内存（同一块用户态 `mmap`）、更新 `used->idx` →
`irqfd` 向 guest 注入中断 → guest 中断处理里看到 `used->idx` 推进。
此情形下 EPT violation 不触发（内存已在内存槽里）、`KVM_RUN` 只退出一次（甚至零次，取决于通知合并）、
影子页表、TLB shootdown、迁移脏页跟踪均不参与。

**生成**：把单队列单请求累加成多队列（`num-queues`）+ 多线程（iothread）+ 多次请求（环满才 kick），
新增 `VIRTIO_F_RING_EVENT_IDX` 的中断抑制、`ioeventfd` 的 `wildcard` 与 `datamatch`、多 vCPU 下的 IPI 与 `posted interrupt`；
覆盖把 `virtio-blk` 换成 `virtio-net`（多了收包方向与 `GSO`）、换成 `VFIO 直通`（多了一次 IOMMU 翻译、少了一次 host 拷贝）；
最坏情形是环被写满但 host 没有取（guest 空转）、`ioeventfd` 未命中（每次 kick 一次 VM exit）、
后端进程被调度延迟（尾延迟直接打进 guest 的 `p99`）。

**两边**：同一份"请求完成"的现场有两种表示。
guest 侧看到的是 `used->idx` 推进与一次中断（`virtio_blk_req->status` 字节被写成 `OK`）；
host 侧看到的是 `eventfd` 计数增加、`vhost_worker` 的一次 `pread` 返回、以及 `irqfd` 的一次 `eventfd_signal`。
持有者不同：**guest 拥有描述符缓冲区的内容，host 拥有物理页的映射与完成通知的权力。**

## 二、为什么这样做（功能设计）

**取舍一：以"一次跨界"为组织轴，而不是以产品为轴。**
按产品讲会得到四份互不相干的说明书（QEMU 手册、Docker 文档、WSL 发行说明、Firecracker README），
它们之间没有可迁移的东西。按跨界讲才有迁移性：**每个产品都只是"把边界画在哪一层 + 谁来收这次税"的一组选择**。
于是新东西也能被解释：Kata 是"每 pod 一个 VM"，gVisor 是"把系统调用这一层也变成一次跨界"，
WSL2 是"把整个 Linux 内核搬进 VM，从而消灭 syscall 翻译这一次跨界"。

**取舍二：软件模拟与硬件虚拟化必须成对讲。**
2005 年之前的 x86 根本不能直接 trap-and-emulate（有一批"敏感但不特权"的指令，在 ring1 上不陷出、静默做错事），
所以 VMware 用二进制翻译 + ring compression，QEMU 用 TCG。**VT-x 不是"让虚拟化成为可能"，是把"每次都要翻译"变成"只在必要时陷出"。**
不讲前一代，就讲不清"为什么 KVM 只有一万多行"这句话的分量，也讲不清 TCG 为什么今天还在（跨架构、无扩展、调试与安全研究）。

**取舍三：容器必须进来，而且必须放在同一张谱系上。**
只说"容器是轻量级虚拟机"是错的（没有内核、没有引导、边界完全不同），只说"Docker 就是个进程"也不对（它确实做了隔离与配额）。
正确讲法是给一张**边界位置表**：硬件强制 vs 内核软件强制、翻译几级地址、共享什么、攻击面在哪。
这张表同时解释了"为什么 K8s 最后要在容器外面再套一层 VM"（Fargate 用 Firecracker、GKE Sandbox 用 gVisor）。

**取舍四：WSL 的两个版本必须成对讲，因为它是教科书里最干净的一次自然实验。**
同一份 Linux ABI、同一家公司、同一个产品名，WSL1 用**系统调用翻译**（`lxcore` 在内核里把 Linux syscall 翻成 NT syscall），
WSL2 用**真内核 + 硬件虚拟化**。差异全部来自"截在哪一层"，别的变量几乎都控制住了——
这种对照在别处买不到，讲虚拟化不讲它等于浪费现成教材。

**取舍五：安全不单列一章，而是作为每一章的"边界"落点。**
因为安全在这里不是一个独立话题，而是**每个机制的另一面**：EPT 决定 guest 能不能碰宿主内存，
IOMMU 决定直通设备能不能乱写，`seccomp` 决定 guest 逃出 QEMU 之后还能做什么，迁移的脏页位图决定内存里有没有别人的残留。
把它抽成一章会变成"虚拟化安全 checklist"，反而看不出"安全就是那条边界画在哪"这个统一事实。
唯一的例外是**机密计算**（SEV-SNP/TDX）：它把 hypervisor 自己也移出信任边界，属于"边界往下挪一层"，放在第 3 章末尾点一笔。

**取舍六：必须有量化一章（第 10 章）。**
这一块的公共话语全是形容词："virtio 比全模拟快"、"容器比 VM 轻"、"vhost-user 延迟更低"。
不给口径就是口号。所以最后一章只做一件事：**把每个形容词换成一个可复现的数**（`vmexit/s`、`IOPS`、`p99`、启动到第一个 syscall 的毫秒数、迁移停机时间）。

## 三、章节大纲

**第 1 章 边界：一台机器有哪些"可以被截走"的东西。**
把"程序直接跑在硬件上"这个默认假设拆开：CPU 状态、地址空间、中断、设备寄存器、DMA、时间、特权级。
Popek & Goldberg 三条件（等价 / 性能 / 资源控制）与敏感指令分类（特权 / 控制敏感 / 行为敏感 / 无害）；
x86 的原罪与 ring compression。**判据：任给一条指令（`MOV CR3`、`POPF`、`SGDT`、`IN`、`HLT`），能说出它在无 VT 时代属于哪一类、被哪种手段处理、代价是多少。**

**第 2 章 两种引擎：陷出模拟与二进制翻译。**
`trap-and-emulate` 的最小闭环；行为敏感指令的两条出路（翻译 vs 半虚拟化）；
QEMU TCG 的翻译块、直接块链接、自修改代码检测（页保护 + 失效重译）；
Xen 的 hypercall 与"改客户机内核"这条路线为什么在 Linux 里留下了 `pv_ops`。
**判据：能解释"为什么 KVM 不能跨架构"以及"为什么 TCG 跑 x86 程序在 ARM 上慢一到两个数量级"，并说出慢在哪个环节。**

**第 3 章 硬件辅助：把控制权交给 CPU。**
VMX 的两个世界、VMCS 的字段分组、`VMLAUNCH`/`VMRESUME`/`VMEXIT` 的状态机；
退出原因分类与单次成本（固定部分 + 可变部分，缓解措施如何把它变贵）；
APICv 与 posted interrupt（连中断都不用退出）；ARM 的 EL2 / `HCR_EL2` / VHE / VGIC 为什么设计上更干净；
嵌套虚拟化为什么贵（VMCS shadowing）。**判据：用"退出次数 × 单次成本"解释任意一个虚拟化性能现象，而不是背结论。**

**第 4 章 内存虚拟化：从影子页表到二维走表。**
GVA→GPA→HPA 两级翻译；影子页表的写保护与缺页重同步（为什么 guest 每建一个 PTE 都要陷出）；
EPT/NPT 的二维走表与 EPT violation 的三种用途（MMIO、脏页跟踪、宿主页不在）；
TLB 与 VPID/ASID、大页为什么在虚拟化里收益更大；
超分与回收：balloon、KSM、overcommit、hugepage、内存热插。
**判据：能算清一次缺页在影子页表与 EPT 下各要多少次内存访问，并说明为什么 TLB 命中率决定一切。**

**第 5 章 I/O 虚拟化：四级台阶与它们的税。**
0 级全模拟（每次寄存器访问一次退出）、1 级 virtio（split/packed ring、通知抑制、批处理、indirect）、
2 级数据面下沉（vhost-net 在内核、vhost-user 在另一个进程，`ioeventfd`/`irqfd` 让快路径不进 QEMU）、
3 级直通（VFIO + IOMMU + SR-IOV + mdev/vGPU）。
旁支：`virtio-fs`/9P 为什么天生比本地文件慢（协议往返 × 元数据操作数）。
**判据：给定负载（64B 小包 / 4K 随机写 / 大文件顺序读 / 共享目录编译），能选出该用哪一级，并指出瓶颈在哪个环。**

**第 6 章 KVM 的接口面：一个用户态 VMM 的最小骨架。**
`/dev/kvm` 的 `ioctl` 协议（建 VM、建 vCPU、注册内存槽、设寄存器与段、设 CPUID、建中断控制器、`KVM_RUN`）；
vCPU = 线程，`KVM_RUN` 的返回码就是事件循环；
三条旁路（`irqfd`、`ioeventfd`、coalesced MMIO）如何把工作从用户态挪走。
**判据：能画出"guest 写串口 → 你在宿主机终端看到字符"的完整路径，并指出哪几步在同一个线程、哪几步换了上下文。**

**第 7 章 QEMU 的工程形态：设备模型、块层、迁移。**
QOM（类型注册 + 属性 + 总线）与"设备 = 状态机 + 寄存器 + 定时器"；
主循环 / `AioContext` / iothread / BQL（大锁为什么是扩展性天花板）；
块层节点图与 qcow2（L1/L2、refcount、快照、backing chain）、cache 模式与 `O_DIRECT`；
迁移（脏页位图 → pre-copy 迭代 → 停机窗口 → post-copy + `userfaultfd`）与"钉住机器类型"的兼容性契约；
攻击面（设备模拟就是解析器，CVE 分布，`seccomp` 与最小设备模型）。
**判据：说清"一次热迁移的停机时间由什么决定"，以及"为什么跨版本迁移必须先钉机器类型"。**

**第 8 章 容器：把边界画在 namespace 上。**
八种 namespace、cgroup v2 的四个控制器（cpu/memory/io/pids）与 PSI、overlayfs 的 copy-up 与 whiteout；
capabilities / `seccomp` / `no_new_privs` / LSM / user namespace（rootless）；
启动路径 `dockerd → containerd → shim → runc`，OCI 的 image spec 与 runtime spec；
为什么快（成本 = 建 namespace + 展开 overlay，没有内核与引导）、为什么不是安全边界（共享内核、页缓存、侧信道、`/proc`、设备节点）。
**判据：能解释"容器里的 PID 1 为什么不是 init"与"容器里 `top` 为什么看到宿主机的核数"，并说出它俩不是 bug 的原因。**

**第 9 章 同一问题的四种答案：WSL1 / WSL2 / gVisor / Firecracker。**
四个"截住点"：ABI 翻译（WSL1、Wine）、真内核进 VM（WSL2、Kata）、用户态内核（gVisor）、砍掉设备模型（Firecracker/Cloud Hypervisor）。
WSL2 的工程细节（utility VM、9P/virtiofs、interop 通道、localhost 转发、WSLg）；
一张五维对照表：截住点 / 兼容性 / 性能 / 攻击面 / 启动成本。
**判据：给一个需求（跑 Docker、跑 GPU、跑不可信代码、要毫秒级启动），能选型并说出代价与失效条件。**

**第 10 章 度量与归因：把"快"变成一个数。**
口径（`vmexit/s`、IPC、IOPS、`p99`、启动到第一个 syscall、迁移停机）；工具链（`kvm` tracepoint、`perf kvm stat`、QEMU `-trace`、guest 内 `perf`、`/sys/kernel/debug/kvm`）；
五个可复现的最小实验；四类常见归因陷阱（把 cache 影响算成虚拟化开销、把超分算成 CPU 问题、guest 内测量的偏差、`benchmark` 自己就在跨界）。
**判据：任何"X 比 Y 快"都要带口径 + 复现命令 + 一个反例（什么条件下结论会反过来）。**

## 四、不做什么 · 必要性 · 失效点

### 必要性：删掉会怎样

| 机制 | 删掉会怎样 | 判定 |
|---|---|---|
| VMCS 与 VM exit | 没有"世界切换"的硬件契约，客户机内核的 `MOV CR3`/`HLT` 无法被拦下，隔离边界不存在；只能退回二进制翻译或改客户机内核 | 必需 |
| EPT/NPT | 影子页表要求 guest 每次写页表都陷出，进程创建/缺页路径成本放大一个数量级；且无法用 EPT violation 做脏页跟踪与 MMIO 退出 | 必需 |
| `ioeventfd` / `irqfd` | 每次 virtio kick 与每次中断注入都要回到用户态，`vmexit/s` 与线程唤醒次数同比例上升，小包场景吞吐直接掉一个台阶 | 必需 |
| IOMMU | 直通设备的 DMA 不经过页表翻译，guest 可读写任意物理内存；"直通"从性能优化变成隔离漏洞 | 必需 |
| namespace | 容器与宿主机共享同一份视图（PID、网络、挂载），"容器"退化成"另一个进程"，隔离承诺破 | 必需 |
| binfmt/interop 通道 | WSL 里无法执行 Windows 程序，也无法把 Linux 路径映射到 `\\wsl$`；跨 OS 的"无缝"承诺破 | 选择 |
| balloon / KSM | 内存不能回收与去重，超分比例只能靠预留，单机部署密度下降（这是成本取舍，不是正确性必需） | 选择 |

### 失效点：哪条前提一破，结论就变

- **CPU 没有虚拟化扩展**（或被困在关闭 VT 的 BIOS 里）→ "VM exit 是唯一成本单位"这条前提破，成本单位变成"翻译块命中率"，第 3 章之后的所有结论都要按 TCG 重算。
- **EPT 的 A/D 位由硬件维护**（`EPT_AD` 未开）→ 脏页跟踪必须靠写保护 + violation，迁移的 pre-copy 迭代次数显著上升，"停机窗口可控"的结论要重新测。
- **`ioeventfd` 未命中（地址没注册或 `datamatch` 不匹配）** → "一次 kick 不进 QEMU"前提破，virtio 的快路径退化回全模拟，第 5 章的台阶表要按 0 级重算。
- **后端线程被调度延迟（CPU 超分、`cgroup` 限流、NUMA 远访）** → "台阶越高越快"前提破，vhost-user 的 `p99` 可能比全模拟更差，此时该看的是唤醒延迟而不是退出次数。
- **容器与宿主机共享页缓存** → "隔离 = 内存不可见"前提破，跨容器计时侧信道成立；机密计算/VM 级隔离才有意义。
- **客户机内核版本高于宿主 `KVM` 支持的 `CPUID`/`MSR`** → "同一份镜像可任意迁移"前提破，迁移要么被拒（`FAIL_ENTRY`），要么在 guest 里表现为 `#GP`；机器类型钉住正是为此存在。

### 不做什么（范围）

**不做 hypervisor 的完整实现。** 第 6 章的最小 VMM 只到"能跑一段 16 位代码并从端口拿到输出"，不做设备模型、不做启动流程、不做多 vCPU 调度。
完整实现属于"另一个项目"级别（那是 `../jos/` 的十倍工作量），这里只到"能证明每一条 `ioctl` 都在干什么"。

**不做云平台与编排。** 不讲 OpenStack/K8s 调度、不讲 CRI/CNI/CSI 的实现、不讲多租户计费。容器只讲到 `runc` 为止（`containerd` 只做路径上的一个名字）。

**不做 CPU 微架构细节。** 流水线、乱序、分支预测在 `cpu/cpu-microarchitecture/`；这里只在"VM exit 为什么贵"这个点上借用结论。

**不做性能工程方法论。** 火焰图怎么读、benchmark 怎么防自欺，见 `eng/perf-engineering/`；第 10 章只做本主题特有的口径。

**不做具体发行版与桌面运维。** 不写"怎么装 Docker Desktop"、不调 WSL 的 `.wslconfig` 参数清单、不给 KVM 的调优参数大全——参数会过时，机制不会。

**不做漏洞利用。** 讲 CVE 面只到"哪类设备是解析器、为什么最小设备模型是安全策略"，不给逃逸利用步骤，实验限定在自己搭的 guest 里。

## 五、面试怎么讲

**30 秒版本**（开场直接说，150–190 字）

> 我是把虚拟化理解成一张成本表，而不是一堆产品名。QEMU 是个普通用户态进程，它靠 CPU 的世界切换（VT-x/ARM EL2）拿到控制权，靠内核给的两个东西活着：一块 `mmap` 出来的内存当客户机物理内存、一个 `/dev/kvm` 的 `ioctl` 协议当"跑一步"的开关。客户机大部分指令直接跑在硬件上，只有必须由软件说话时才陷出来——所以整个性能问题可以归成一句话：**一次退出要不要发生、发生几次、每次带多少活、由谁在宿主侧干**。EPT 砍掉页表相关的退出，virtio 把"每次寄存器一次退出"变成"一次环通知传一批"，`ioeventfd`/`vhost` 把数据面直接挪进内核避开 QEMU。容器是同一个问题的另一个取值：边界不画在 CPU 上而画在内核对象的视图上，所以它便宜但不构成安全边界。

**可能被追问的 8 个点**

1. **「QEMU 和 KVM 到底谁在干活？」** → 考点：职责边界。
   → 答法：KVM 是内核模块，只负责 CPU、MMU、中断控制器（VT-x 的封装 + `ioctl` 接口），**不模拟任何设备**；QEMU 是用户态进程，负责设备模型、机器模型、块层、迁移。所以"虚拟机"是两者合起来的产品：KVM 提供"跑得快"，QEMU 提供"像台机器"。边界：也正因为 QEMU 在用户态且设备模型是 C 写的解析器，它才是 CVE 大户；Firecracker 的做法是把设备模型砍到只剩 virtio 的四个。

2. **「为什么 x86 在 2005 年前不能直接跑虚拟机？」** → 考点：敏感指令 vs 特权指令。
   → 答法：`trap-and-emulate` 要求"所有敏感的指令都是特权指令"。x86 有一批指令**读特权状态但不陷出**（`SGDT`/`SIDT` 能读到宿主 GDT 基址，`POPF` 在 CPL=1 时静默忽略 IF），于是在 ring1 上跑客户机内核会"不报错但做错事"。VMware 用 ring compression（客户机内核降到 ring1）+ 二进制翻译把这类指令换掉；Intel 2005 年的 VT-x 与 AMD 2006 年的 AMD-V 才从根上解决。

3. **「VM exit 到底多贵，为什么要拿它当成本单位？」** → 考点：量级与构成。
   → 答法：单次退出在数百到上千周期量级（几十到几百纳秒），取决于退出原因和缓解措施（`L1D` flush 这类会让它更贵）。它贵在**固定部分**：保存/恢复一整组寄存器与 VMCS 状态、换栈、切页表基址、污染分支预测与 cache。所以判据不是"退出几次"，而是"退出次数 × 每次要搬多少数据"：一次退出搬 4KB 是划算的（virtio 批处理），一次退出搬 1 字节是灾难（PIO 拷字节）。**具体数字用 `perf kvm stat live` 自己在机型上测，别背别人的。**

4. **「virtio 到底优化了什么？它不就是个模拟设备吗？」** → 考点：一次退出的"摊薄"。
   → 答法：它把"每次寄存器访问一次退出"改成"一次环通知传一批请求"。机制是三件事：**共享内存环**（描述符表 + avail/used 环，双方只推进索引，数据本身不跨界）、**通知抑制**（`EVENT_IDX`：对方说"我暂时不需要通知"就不 kick）、**批处理**（多个描述符一次处理，可选 indirect 描述符）。它仍然是软件设备，只是把交税频率降低了两个数量级。边界：`virtio` 的前提是客户机里有驱动并知道自己是虚拟机——这就是"半虚拟化"。

5. **「`ioeventfd` 和 `irqfd` 解决了什么？」** → 考点：把快路径移出用户态。
   → 答法：`ioeventfd` 把"guest 往某个 MMIO/PIO 地址写一次"这个动作直接绑到一个 `eventfd` 上，写下去就在内核里 `signal`，QEMU 根本不参与；`irqfd` 反过来，往 `eventfd` 写一次就等于向 guest 注入一个中断。两个方向合起来，`vhost-net` 的数据面可以完全在内核里闭环（guest → 内核 → 网卡），QEMU 只剩控制面。边界：控制面（设备热插、迁移、错误处理）仍在 QEMU，所以"QEMU 挂了 VM 也挂了"这件事没变。

6. **「容器为什么不是轻量级虚拟机？」** → 考点：边界的位置与强制者。
   → 答法：容器没有自己的内核、没有引导、没有地址翻译的第二级——它只是**同一个内核用不同的 namespace 视图 + cgroup 配额**跑起来的进程。快的原因不是"优化得好"，而是"要做的事本来就少"：建几个 namespace、挂一次 overlayfs、`pivot_root`、`exec`。不安全的原因也在同一句：**内核是共享的**，一个内核漏洞就是逃逸，`/proc`、页缓存、CPU 侧信道都跨容器可见。所以真正的多租户平台会再套一层 VM（Fargate 的 Firecracker、GKE Sandbox 的 gVisor）。

7. **「WSL1 和 WSL2 差在哪，为什么 WSL2 要背一个真内核？」** → 考点：截住点决定一切。
   → 答法：WSL1 在 NT 内核里放了一个 `lxcore` 驱动，把 Linux 系统调用**翻译**成 NT 系统调用——语义对不上的地方（`fork`、`inotify`、`iptables`、`io_uring`）就只能缺或者凑，Docker 直接跑不起来。WSL2 换成一台轻量 Hyper-V 虚拟机，里面跑**真的 Linux 内核**，于是 ABI 天然完整；代价是跨 OS 文件访问要过 9P/virtiofs（所以 `git status` 在 `/mnt/c` 上特别慢，在 `~/` 下就正常）。**同一个产品、同一个 ABI，一次是翻译、一次是虚拟化，性能与兼容性的账完全不同——这是我能给出的最干净的一组对照。**

8. **「你怎么证明你说的'更快'？」** → 考点：口径与反例。
   → 答法：先定口径——`vmexit/s` 用 `perf kvm stat live`，吞吐/延迟用 guest 内的固定 workload，启动时间用"到第一个 syscall"而不是"到登录提示符"；再说反例——vhost-user 在 CPU 超分时 `p99` 会比全模拟更差，EPT 在随机访存大工作集下会输给大页，容器在元数据密集型负载（大量小文件 `stat`）上会被 overlayfs 的 copy-up 拖死。**能说出反例才算测过，只会说"更快"的是背的。**

**别说什么**

- **「虚拟化就是装个 VMware。」** 一句话暴露没碰过机制层；至少要能说清"谁在切世界、谁在模拟设备"。
- **「容器是轻量级虚拟机。」** 边界位置完全不同的两样东西，这句话会让后面所有追问都答错。
- **「KVM 是个 hypervisor。」** 严格说 KVM 是内核里的虚拟化**能力**（`/dev/kvm`），hypervisor 是 KVM + 用户态 VMM 合起来的系统；这个区分在追问"QEMU 挂了会怎样"时会立刻见真章。
- **报没测过的数字。** "virtio 比全模拟快 10 倍"这种话必须带负载、包长、核数、后端位置；否则不如说"我能给出复现路径"。
- **把"安全"说成"隔离够不够"这种程度副词。** 要说清**谁强制**（硬件/内核软件/约定）、**跨的是哪条边界**、**共享了什么**。
