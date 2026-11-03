# cuda · 分章详细

## 第 1 章 GPU 与 CPU 的结构差异：SIMT、延迟隐藏与吞吐优先

**要解决的问题**：建立一套判断标准，让读者能说明某段计算放到 GPU 上会快还是慢、快在哪里、被什么限制。没有这套标准，后面所有优化（分块、合并访存、提高占用率）都靠猜测；算法对了也可能只跑到峰值的几个百分点，还不知道该修改哪里。

**机制**：

CPU 和 GPU 的晶体管分配策略相反。CPU 把大部分面积花在乱序执行、分支预测、寄存器重命名和多级大缓存上，目标是**压低单条指令流的延迟**；所以它有几个到几十个大核，单线程性能强。GPU 把面积花在**大量简单的 ALU 和庞大的寄存器堆**上，控制逻辑由一组线程共享，缓存小而多级，目标是**单位时间完成更多指令**。所以 GPU 的单线程性能通常弱于 CPU，它的优势来自并发度。

SIMT（Single Instruction, Multiple Threads）是这套设计的执行抽象：硬件把 32 个线程（一个 warp）绑定在一起，同一条指令同时驱动 32 个 lane。程序员写的是标量代码，向量化由硬件完成，这和需要显式 intrinsics 的 SIMD 不同。这样做的代价是：warp 内的线程如果走不同分支，硬件只能把两条路径串行各执行一遍，用掩码屏蔽掉不参与的 lane，也就是分支分歧，有效吞吐按路径数打折。

延迟隐藏是理解 GPU 性能的核心。GPU 不靠缓存命中来消除延迟，而靠“同时在飞的请求足够多”把延迟摊薄。用 Little 定律估算：要打满带宽 $B$，内存延迟为 $L$，则同时在飞的字节数约为 $B \times L$。若 $B$ 在 1–3 TB/s 量级、$L$ 在几百纳秒量级（量级示例，需按卡实测），在飞数据量就是 MB 级；如果每个线程一次只发出一个 4 字节 load，需要几十万个线程同时处于等待状态才能填满。这就是“占用率”和“每线程指令级并行”为什么重要：它们决定在飞请求数。

推论有三条，贯穿全书：（1）优化目标是吞吐，不是单线程快；（2）访存延迟靠并发隐藏，不靠缓存；（3）warp 是最小效率单位，凑不满 32 个 lane 就是浪费。

**最小例子**：一个纯拷贝 kernel `out[i] = in[i]`，$N = 2^{26}$ 个 float（256 MB），读加写共 512 MB 流量。

- 满配置：`block = 256`，`grid = N/256 = 262144`。在 1.5 TB/s 量级带宽下，$512\text{ MB} / 1.5\text{ TB/s} \approx 0.34\text{ ms}$（量级示例，需按卡实测），达到硬件的 roofline。
- 朴素版：`grid = 1, block = 1`，一个线程串行循环 6700 万次。每次 load 的延迟只能靠循环里的下一次迭代部分重叠，有效在飞字节数极小，等效带宽会掉到几十 MB/s 量级，耗时到秒级。加速比 $10^3$–$10^4$（量级示例，需按卡实测）。

同一段代码、同样的访存总量，差别全部来自“同时在飞的请求数”。这里的瓶颈是延迟隐藏不足，并未卡在算力。

**面试高频问法**：

1. 问法：“GPU 为什么快？核多吗？”→ 考点：是否理解吞吐优先而非单核性能。答法：“核多只是表面原因。GPU 把晶体管从控制逻辑和缓存挪到了 ALU 和寄存器，靠大量并发线程把内存延迟摊薄，追求单位时间吞吐；单线程性能反而不如 CPU，所以判断一段代码适不适合 GPU，要看它有没有足够多的独立并行工作。”
2. 问法：“什么是 SIMT？和 SIMD 有什么区别？”→ 考点：warp 的执行模型。答法：“SIMT 是硬件把 32 个线程绑成一个 warp，同一条指令驱动 32 个 lane，程序员写标量代码；SIMD 要程序员显式写向量指令。SIMT 的代价是 warp 内出现分支时只能串行执行各条路径，也就是分歧。”
3. 问法：“GPU 为什么需要那么多线程？少一点不行吗？”→ 考点：延迟隐藏的定量直觉。答法：“在飞请求数要满足带宽乘延迟。带宽在 TB/s 量级、延迟几百纳秒，在飞数据量是 MB 级；每个线程一次只发一个 4 字节请求的话，就得几十万线程同时在等，线程少了带宽根本填不满。”
4. 问法：“给一段代码，你怎么判断它在 GPU 上是算力受限还是带宽受限？”→ 考点：roofline 思路与算术密度。答法：“算每字节访存对应多少次浮点运算，和这台卡的 flop/byte 比值比较。比值低说明无论怎么优化算力都用不上，瓶颈在带宽，优化方向就是减少访存和合并访问；比值高才去优化计算。”

## 第 2 章 CUDA 编程模型：grid / block / warp、索引计算与执行配置怎么选

**要解决的问题**：把计算映射到线程层级上，并确定 launch 配置（grid 和 block 的维度和大小）。相同的 kernel 代码，配置选错就会白白损失一部分性能——占用率不够、尾部效应、跨步访存，全都在这一步决定，而且这些问题在代码逻辑上完全看不出来。

**机制**：

三级结构：**grid** 是一次 kernel launch 的全部线程；grid 被切成 **block**（CTA），一个 block 独占一个 SM 的资源，被调度到该 SM 上执行，block 之间不能通信、没有执行顺序保证；block 内再按 32 个线程分成 **warp**，warp 是 SIMT 执行和调度的实际单位。所以 `__syncthreads()` 只能同步一个 block，跨 block 的同步要靠 kernel 边界或原子操作。

索引计算是基本功。一维情形下全局线程号

```cuda
int idx = blockIdx.x * blockDim.x + threadIdx.x;
```

二维情形（矩阵）用 `blockIdx.y * blockDim.y + threadIdx.y` 作为行，`x` 作为列，并约定 **`x` 维对应内存中连续的方向**，这样相邻 `threadIdx.x` 落在相邻地址，访存才能合并。

线程数常常不等于元素数，标准写法是 **grid-stride loop**，让配置与问题规模解耦：

```cuda
__global__ void add(const float* a, const float* b, float* c, int n) {
    int stride = blockDim.x * gridDim.x;
    for (int i = blockIdx.x * blockDim.x + threadIdx.x; i < n; i += stride)
        c[i] = a[i] + b[i];
}
```

配置选择的约束是硬的：**block 最多 1024 线程**；每个 SM 能常驻的 block 数受寄存器、共享内存和硬件上限共同限制，这直接决定 occupancy。几个经验规则：block 取 128–256 起步；block 大小取 32 的倍数，否则最后一个 warp 有空闲 lane，浪费比例最大可达 $1 - 0.5/1$（例如 33 线程的 block 里 31 个 lane 空转）；grid 取 SM 数乘以每 SM 常驻 block 数的整数倍，以减轻尾部效应——如果 grid 比这个数多出一点点，最后一批里只有极少数 block 在跑，其余 SM 空等。

**最小例子**：向量加法，$N = 2^{26}$。

- 方案 A：`block = 256`，`grid = N / 256 = 262144`，每个线程处理一个元素。kernel 耗时在 0.3 ms 量级，受限于带宽（量级示例，需按卡实测）。
- 方案 B：`block = 256`，`grid = SM 数 × 32`（例如 100 多个 SM 时约 4000 个 block），同一个 kernel 体配 grid-stride loop，每个线程循环约 64 次。吞吐与 A 基本持平，但 block 调度开销和索引计算开销按元素分摊得更低，且配置与 $N$ 无关。
- 反面例子：把 $N$ 缩到 $2^{16}$ 还沿用方案 A 的配置，`grid = 256`，块数少于 SM 数，部分 SM 空闲，带宽用不满；或者 `block = 100`，每 32 个线程里最后一个 warp 只有 4 个有效 lane，等效浪费约 20% 的 warp 发射槽。这两类损失和算法无关，纯粹来自配置。

**面试高频问法**：

1. 问法：“grid、block、warp 是什么关系？`__syncthreads()` 能同步哪些线程？”→ 考点：层级与同步边界。答法：“grid 被切成 block，block 独占一个 SM 的资源，block 内再按 32 线程分成 warp。`__syncthreads()` 只同步同一个 block 内的线程；跨 block 没有块内同步原语，只能靠 kernel 边界或原子操作。”
2. 问法：“block 大小怎么定？为什么常取 128 或 256？”→ 考点：占用率与资源约束的权衡。答法：“先保证是 32 的倍数，避免 warp 空转；再看寄存器用量，block 太大可能让每 SM 常驻 block 数掉下来，反而降低占用率；block 太小则每个 block 的调度与同步开销占比高。128–256 是常见的折中起点，最终要按卡实测。”
3. 问法：“grid-stride loop 有什么用？直接一个线程一个元素不好吗？”→ 考点：配置与规模的解耦。答法：“它让 grid 大小不再依赖数据量，可以把 grid 固定成 SM 数乘常驻 block 数，减少块调度与索引计算的分摊开销，也方便处理跨多个设备的规模；元素数不等于线程数时也不用加边界判断之外的额外逻辑。”
4. 问法：“为什么二维索引里要让 `threadIdx.x` 对应列？”→ 考点：访存合并的方向。答法：“同一个 warp 的 32 个线程的 `threadIdx.x` 连续，如果 x 对应内存连续方向，一次访存就覆盖连续 128 字节，能合并成少数几个内存事务；反过来让 x 对应行，就会变成跨步访问，事务数按 stride 倍增。”
5. 问法：“尾部效应是什么？”→ 考点：grid 与 SM 数量的匹配。答法：“当一个 grid 的 block 数不是每 SM 常驻 block 数的整数倍时，最后一波只有部分 SM 有 block 在跑，其余空转，整体利用率下降；把 grid 取成 SM 数乘常驻块数的整数倍，或者用 grid-stride loop 让每个 block 的工作量均匀，可以缓解。”

## 第 3 章 内存层次：全局、共享、常量、寄存器，bank conflict 与本地内存溢出

**要解决的问题**：前两章把并行度做出来了，但同一个 kernel 只改「数据放在哪一层内存、按什么布局放」，端到端时间能差好几倍。这一章解决的是：给定一份计算，哪些数据该留在寄存器、哪些该显式搬进共享内存、哪些该走常量内存，以及怎么避免编译器把数据悄悄丢进本地内存，或者共享内存访问撞成 bank conflict。不解决这层问题，前面所有并行度都会被访存延迟和串行化抵消掉。

**机制**：

| 层次 | 作用域 | 典型容量（量级，按架构） | 谁来管 |
|---|---|---|---|
| 寄存器 | 每线程 | 每 SM 65536 个 32-bit；每线程上限 255 | 编译器分配 |
| 共享内存 | 每 block | 每 SM 数十 KB 到 200+ KB，可 carveout | 代码显式 `__shared__` |
| 常量内存 | grid 全局只读 | 64 KB | `__constant__` + host 拷贝 |
| 全局内存 | grid 全局 | HBM，GB 级 | `cudaMalloc` |
| 本地内存 | 每线程私有 | 物理位于全局内存 | 编译器在溢出时生成 |

关键点有几条：

1. **共享内存按 bank 切分**。多数架构把 shared 切成 32 个 bank、每个 bank 4 字节宽，地址到 bank 的映射是 $bank=\lfloor addr/4\rfloor \bmod 32$。一个 warp 的 32 个线程如果访问落在同一 bank 的不同 4 字节字上，就产生冲突，硬件把它们拆成多次事务串行完成；如果落在同一个字上，则走广播，一拍完成。
2. **共享内存需要显式同步**。写 shared 与读 shared 之间必须有 `__syncthreads()`，它是 block 粒度屏障，不能跨 block。这也是为什么 tile 的尺寸必须和 block 尺寸绑死。
3. **常量内存的收益来自广播**。一个 warp 内所有线程读同一地址时，一次事务就完成，相当于免费；一旦 32 个线程读 32 个不同地址，就退化成 32 次串行事务，比全局内存还差。
4. **本地内存不是「本地」**。寄存器不够用、或者对数组做运行期下标索引时，编译器会生成 local memory 访问，物理上落在全局内存，只靠 L1/L2 兜底。用 `-Xptxas -v` 能看到每线程寄存器数和 spill 的字节数，这是排查它的第一手段。

**最小例子**：

```cuda
#define TILE 32
__global__ void transpose(const float* __restrict__ in, float* __restrict__ out, int n) {
    __shared__ float tile[TILE][TILE + 1];      // +1 是 padding，打散 bank
    int x = blockIdx.x * TILE + threadIdx.x;
    int y = blockIdx.y * TILE + threadIdx.y;
    if (x < n && y < n) tile[threadIdx.y][threadIdx.x] = in[y * n + x];

    __syncthreads();                            // 写读之间必须同步

    x = blockIdx.y * TILE + threadIdx.x;        // 交换 block 坐标
    y = blockIdx.x * TILE + threadIdx.y;
    if (x < n && y < n) out[y * n + x] = tile[threadIdx.x][threadIdx.y];
}
```

配置：`dim3 block(32, 32); dim3 grid((n+31)/32, (n+31)/32);`，$n=4096$ 时是 $128\times128$ 个 block。三次对照：

- **朴素版**（直接 `out[x*n+y] = in[y*n+x]`）：读是合并的，写是跨步 $n$ 的，一个 warp 的 32 次写散到 32 条 128B 事务上，写带宽降到理论值的约 $1/32$ 量级。
- **shared 版（无 padding）**：读、写两侧都变成合并访问，但回读 `tile[threadIdx.x][threadIdx.y]` 时 stride 是 32 个 float，$bank=(tx\cdot 32+ty)\bmod 32=ty$，同一 warp 的 32 个线程全部撞进同一个 bank，形成 32-way conflict，这一段又被串行化 32 次。
- **shared + padding 版**：stride 变成 33，$bank=(tx\cdot33+ty)\bmod 32=(tx+ty)\bmod 32$ 随 `tx` 遍历 32 个 bank，冲突消失。

结论：shared 版能不能真正拿到收益，取决于 padding 这一格有没有加。端到端转置带宽的变化是数倍量级（量级示例，需按卡实测），而且没有哪一版是「绝对最优」，取决于 $n$ 是否整除 TILE、是否需要边界判断。

同一套判断也适用于本地内存：把 `float acc[8]` 用运行期变化的 `i` 去索引，编译器无法把它放进寄存器，整块搬进 local memory，每线程多出 8 次全局内存往返。改成 `#pragma unroll` 让下标在编译期确定，或者手工展开成 8 个标量，才是正解。

**面试高频问法**：

1. **问法**：shared memory 为什么能加速？什么时候反而更慢？
   **考点**：片上带宽与容量的取舍，以及同步和 tile 边界带来的额外开销。
   **答法**：shared 提供远高于 HBM 的片上带宽和确定性延迟，条件是同一份数据被 block 内多个线程复用、并且访问不冲突；如果每个数据只被用一次，或者加了 `__syncthreads` 之后复用度不够、又或者 tile 尺寸导致边界分支变多，搬这一趟就是净亏。

2. **问法**：怎么判断有没有 bank conflict，怎么消？
   **考点**：bank 映射公式和 padding 手法。
   **答法**：按 $bank=\lfloor addr/4\rfloor \bmod 32$ 算出同一 warp 32 个地址的 bank 编号，只要有多个线程落在同一 bank 的不同字上就冲突；消除手段是 padding 把 stride 从 32 的倍数改成互质数、或者把访问顺序重排成按列，也可以用 8 字节宽的 bank 配置（按架构支持情况）。

3. **问法**：什么情况下变量会掉进 local memory？怎么发现？
   **考点**：寄存器溢出的触发条件和排查工具。
   **答法**：寄存器需求超过每线程上限、数组用运行期下标索引、或者取局部数组地址传给函数时，编译器会放到 local memory；用 `-Xptxas -v` 看 spill 的字节数、用 Nsight Compute 看 local memory 的读写流量，两个数不为零就说明在付这份代价。

4. **问法**：常量内存适合放什么？为什么同一个地址访问快？
   **考点**：广播机制与退化条件。
   **答法**：适合放 kernel 参数衍生出的、整个 grid 只读且被高频访问的小表（滤波核系数、变换矩阵这类）；warp 内所有线程读同一地址时硬件做一次事务广播，但如果 32 个线程读 32 个不同地址，就会串行成 32 次，比走全局内存还慢。

## 第 4 章 线程束与分歧：warp divergence、占用率（occupancy）的真实取舍

**要解决的问题**：并行度铺够了、数据也放对了，kernel 还是只跑到理论峰值的一半。两个典型原因：warp 内的分支把 32 路并行拆成了串行；或者 occupancy 配错，可用来隐藏延迟的 warp 数不够。这一章解决的是「怎么判断当前瓶颈是分歧还是占用率，以及为了修一个愿意付另一个的什么代价」——这两件事经常互相拉扯。

**机制**：

一个 warp 是 32 个线程，共享一个指令流。遇到分支时，硬件用执行掩码依次跑完每条路径，其余线程被屏蔽。所以一个 warp 如果分成两条路径，时间约等于两条路径时长之和，而不是取最大值。Volta 之后有独立线程调度，warp 内可以交错推进，但分歧的指令发射成本并没有消失，只是调度更灵活。

分歧的判定标准不是「代码里有 if」，而是「同一个 warp 内 32 个线程的分支结果是否一致」。$i\ \&\ 1$ 这种按 lane 分派的条件必然分歧；`(threadIdx.x >> 5) & 1` 这种按 warp 分派的条件则整个 warp 同进同退，没有分歧代价。

occupancy 是同一时刻每 SM 上的活跃 warp 数除以硬件上限（多数架构每 SM 最多 64 个 warp，量级，按架构）。它被三类资源中最早耗尽的那个卡住：

- 寄存器：每 block 用量 = 每线程寄存器数 × block 线程数，按分配粒度向上取整；
- 共享内存：每 block 的 `__shared__` 用量，同样向上取整；
- block 槽位：每 SM 能同时驻留的 block 数有上限。

可以调用 `cudaOccupancyMaxActiveBlocksPerMultiprocessor` 直接算，也可以用 `__launch_bounds__(maxThreadsPerBlock, minBlocksPerMultiprocessor)` 让编译器按目标反推寄存器预算。

**取舍的本质**：occupancy 只回答「有多少 warp 可以用来隐藏延迟」。按 Little's Law，打满带宽需要的在途字节数约为 $\text{带宽}\times\text{延迟}$。以 A100 量级估算：$1.5\ \text{TB/s}\times 500\ \text{ns}\approx 750\ \text{KB}$（量级示例，需按卡实测），若每线程只发一个 4 字节 load，需要十几万个在途线程——正好是整卡满 occupancy 的量级。这就说明：单靠 occupancy 刚好够用，想再往上只能靠每线程的 ILP（一条线程发多条独立 load）。反过来，把寄存器从 64 压到 32 能把 occupancy 从 50% 拉到 100%，但压出来的 spill 会变成 local memory 流量，很可能整体更慢。

**最小例子**：

```cuda
__global__ void branchy(const float* __restrict__ x, float* __restrict__ y, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    float v = x[i];
    // 按 lane 分派：同一 warp 内奇偶各一半，两条路径串行
    y[i] = (i & 1) ? sqrtf(v) : v * 2.0f;
}

__global__ void warpUniform(const float* __restrict__ x, float* __restrict__ y, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    float v = x[i];
    // 按 warp 分派：整个 warp 只走一条路径
    y[i] = ((threadIdx.x >> 5) & 1) ? sqrtf(v) : v * 2.0f;
}
```

配置：`block = 256`（8 个 warp），$n=2^{24}$。`branchy` 版本每个 warp 两条路径都执行，发射的指令数约为 `warpUniform` 的两倍，实测耗时通常接近 2 倍（量级示例，需按卡实测）；`warpUniform` 版本耗时基本回到「完全无分支」的基准线，因为分支条件在 warp 粒度上一致。

occupancy 侧的对照（A100 量级，需按实测算）：每线程 64 个寄存器、block 256 线程 → 每 block 16384 个寄存器，SM 65536 个寄存器只能放 4 个 block = 1024 线程 = 32 个 warp，占 64 个 warp 上限的 50%。改写成 `__launch_bounds__(256, 8)` 后寄存器被压到 32，达到 8 个 block、64 个 warp、100% occupancy。这两步在 Nsight Compute 里要一起看：如果 occupancy 提升后 `Warps Eligible` 没涨、local memory 流量却涨了，说明这笔买卖亏了。

**面试高频问法**：

1. **问法**：warp divergence 的代价怎么估？
   **考点**：SIMT 下掩码串行执行的模型。
   **答法**：代价约等于分歧后各路径执行时间的总和，而不是最大值，所以一个 warp 分成两条等长路径就接近 2 倍；关键是看分支条件在 warp 内是否一致，而不是看代码里有没有 if。

2. **问法**：occupancy 是不是越高越好？
   **考点**：occupancy 只是延迟隐藏的手段，不是目标。
   **答法**：不是，它只决定有多少 warp 能用来盖住访存延迟；只要在途请求足够打满带宽，50% 也可能跑满峰值，而为了冲 100% 去压寄存器导致 spill，反而会用 local memory 流量把收益吃回去。

3. **问法**：怎么提高 occupancy？代价是什么？
   **考点**：三类限制资源和反向代价。
   **答法**：降每线程寄存器数（`__launch_bounds__` 或 `maxrregcount`）、减共享内存用量、调小 block 尺寸，三者取最紧的那个松；代价是寄存器压力变大会 spill、共享内存变小会导致 tile 复用度下降。

4. **问法**：什么情况下会主动降低 occupancy？
   **考点**：ILP 与 TLP 的互换。
   **答法**：当每线程能做足够多的独立加载（寄存器分块、多元素展开）时，少量 warp 就能提供足够的在途请求，这时候把寄存器留给数据复用比留给更多 warp 更划算。

5. **问法**：不改分支逻辑，怎么减少分歧？
   **考点**：重排数据或改分派粒度。
   **答法**：把分支条件改成按 warp 或按 block 分派（用 `threadIdx.x >> 5`、`blockIdx` 决定路径），或者对数据做预排序/分桶让同一 warp 的线程走同一分支；实在不行就把两条路径都算出来再 select，用计算换掉串行。

## 第 5 章 同步与原子：__syncthreads、原子操作、浮点归约的非确定性

**要解决的问题**：一个 block 内的 256/1024 个线程要把各自的局部结果合并时，需要一个所有线程都能看到的中间缓冲区（shared memory）和一道屏障；而跨 block 合并时，硬件并不提供全局屏障，只能靠原子操作或拆成两个 kernel 来完成。如果这一章不解决，写出来的 kernel 会“大部分时候对、偶尔错”（竞态），或者因为所有线程都原子操作同一地址而性能下降一个数量级。

**机制**：
- `__syncthreads()` 是 **block 级**屏障，同时充当 block 内 shared/global 访存的内存栅栏：它保证该 block 所有线程此前对 shared 的写对之后所有线程可见。它**不能**跨 block。grid 级同步只有两条路：拆 kernel（两次 launch 之间有隐式全局屏障），或用 cooperative groups 的 `grid.sync()`（要求 cooperative launch 且 grid 规模不超过同时驻留的上限）。
- 调用约束：`__syncthreads()` 必须被 block 内**所有**线程在**同一控制流位置**执行。写成 `if (t < stride) { ...; __syncthreads(); }` 是否安全取决于条件是否对全体线程一致；如果只有部分线程进入，就会死锁或未定义。正确写法是把 `__syncthreads()` 放在 `if` 外面，或者只让 `if` 包住计算。
- 原子操作（`atomicAdd` 等）的原子性由硬件在 L2 的原子单元保证，只保证“单次读-改-写不可分割”，**不保证**它与其他内存操作的顺序；需要顺序时配 `__threadfence()`。同一个地址上的原子请求会被串行化，这正是性能瓶颈所在。
- 浮点非确定性：`(a+b)+c ≠ a+(b+c)`，浮点加法不满足结合律。`atomicAdd` 到同一地址的到达顺序由调度决定，所以同一份输入跑两次，结果的 bit 位可能不同。树形归约在固定 grid/block 下顺序固定，是确定性的。

**最小例子**：`n = 16M` 个 float，`block = 256` 线程，对比两种合并方式。

```cuda
// A. 每线程一次全局原子：65536 次 atomicAdd 打同一个地址
__global__ void red_atomic(const float* in, float* out, int n) {
    float v = 0.f;
    for (int i = blockIdx.x*blockDim.x+threadIdx.x; i < n; i += gridDim.x*blockDim.x)
        v += in[i];
    atomicAdd(out, v);              // 串行化热点
}

// B. block 内 shared 归约，每 block 只做一次原子
__global__ void red_shared(const float* in, float* out, int n) {
    __shared__ float s[256];
    int t = threadIdx.x;
    int i = blockIdx.x*blockDim.x*2 + t;
    float v = (i < n) ? in[i] : 0.f;
    if (i + blockDim.x < n) v += in[i + blockDim.x];
    s[t] = v;
    __syncthreads();
    for (int st = blockDim.x/2; st > 0; st >>= 1) {
        if (t < st) s[t] += s[t+st];
        __syncthreads();            // 屏障在 if 外，全体线程都到
    }
    if (t == 0) atomicAdd(out, s[0]);   // 每个 block 一次
}
```

在 16M 元素、约 65536 个 block 的配置下，B 把全局原子从“每线程一次”降到“每 block 一次”，原子次数下降三个数量级；A 的耗时主要由 L2 上同一地址的串行化决定，量级示例可能比 B 慢 5–10 倍，需按卡实测。代价是 B 引入了一次 block 内屏障和 shared 往返。

**面试高频问法**：
1. `__syncthreads()` 能同步整个 grid 吗？→ 考点是同步作用域。→ 不能，它只保证同一个 block 内的线程到达同一点；grid 级只能拆 kernel 或用 cooperative launch 的 `grid.sync()`。
2. 为什么 `__syncthreads()` 不能写在只有部分线程进入的分支里？→ 考点是屏障的到达语义。→ 屏障要求 block 内所有线程都到达，条件不一致时未到达的线程永远等不到，会挂死或行为未定义；把屏障移到分支外，只让计算进分支。
3. 原子操作为什么慢，怎么优化？→ 考点是串行化热点与分层归约。→ 同一地址的原子被硬件串行化；先把竞争压到 block 内（shared 归约或 warp shuffle），每 block 只发一次原子，或分散到多个桶再二次归约。
4. 同样的输入，浮点归约结果每次不一样，是 bug 吗？→ 考点是浮点结合律与调度顺序。→ 不是 bug，是 `atomicAdd` 到达顺序不定导致的舍入差异；要确定性就用固定顺序的树形归约，并按 block 下标顺序做第二阶段，或改用整数/定点。
5. `atomicAdd` 能替代 `__threadfence()` 吗？→ 考点是原子性与可见性/顺序是两件事。→ 不能；原子只保证单次读改写不可分割，跨地址的写顺序仍需 `__threadfence()` 保证别的线程能看到。

## 第 6 章 归约与扫描：两个经典 kernel 的逐步优化

**要解决的问题**：归约（sum）和扫描（prefix sum）是所有“把 N 个元素压成 1 个或 N 个前缀”的算子底座。它们的朴素写法能跑对，但会被三件事依次卡住：bank conflict、warp divergence、每线程工作量太少导致访存延迟藏不住。这一章的价值是给出“每一步优化消掉了哪个瓶颈”的完整链条，面试里几乎是必问的推理题。

**机制**：
- **归约的四步演进**（以 block=256 为例）：

| 版本 | 做法 | 被什么卡住 | 优化掉什么 |
|---|---|---|---|
| v0 | shared 数组，`stride` 从 1 开始倍增，`s[t] += s[t+stride]` | 第一轮 32 路 bank conflict + warp 内一半线程立刻空闲 | — |
| v1 | `stride` 从 `blockDim/2` 递减 | 前几轮无冲突，但每轮活跃线程减半，divergence 严重 | 消除 bank conflict |
| v2 | 前 32 个线程把剩余部分完全展开（unroll），不再进循环 | 仍有 shared 往返 | 消除 divergence 与循环开销 |
| v3 | `__shfl_down_sync` 做 warp 内归约，shared 只存 8 个 warp 结果 | 需要 Volta+ 的 sync 语义 | 消除大部分 shared 流量 |

- **扫描的两种范式**：
  - Hillis-Steele（inclusive）：第 $d$ 步 `x[i] += x[i - 2^d]`，共 $\log_2 n$ 步，总工作量 $O(n\log n)$。
  - Blelloch（up-sweep + down-sweep）：先树上归约再自顶向下分发，总工作量 $2n$，步数 $2\log n$。
  - 关键取舍：GPU 线程极便宜，**工作高效（work-efficient）通常比步高效更重要**，n 越大越明显。n=16M 时 Hillis-Steele 的工作量约是 Blelloch 的 $\log_2 n \approx 24$ 倍（量级示例，需按卡实测）。
  - 大数组的通用做法是**三段式**：每 block 内先做 local scan 并把 block 总和写出去 → 对 block 总和数组做一次 scan（元素数已缩小 blockDim 倍）→ 各 block 加回前缀偏移。

**最小例子**：v3 的 warp-shuffle 归约，16M 元素、256 线程、每线程处理 2 个元素：

```cuda
__device__ __forceinline__ float warpRed(float v) {
    for (int off = 16; off > 0; off >>= 1)
        v += __shfl_down_sync(0xffffffffu, v, off);
    return v;
}
__global__ void reduce_v3(const float* in, float* out, int n) {
    float v = 0.f;
    int i = blockIdx.x*blockDim.x*2 + threadIdx.x;
    int g = gridDim.x*blockDim.x*2;
    for (; i < n; i += g) {                 // 每线程多元素，摊薄访存延迟
        v += in[i];
        if (i + blockDim.x < n) v += in[i + blockDim.x];
    }
    __shared__ float ws[32];
    v = warpRed(v);
    if ((threadIdx.x & 31) == 0) ws[threadIdx.x >> 5] = v;
    __syncthreads();
    if (threadIdx.x < 32) {
        v = (threadIdx.x < (blockDim.x >> 5)) ? ws[threadIdx.x] : 0.f;
        v = warpRed(v);
        if (threadIdx.x == 0) out[blockIdx.x] = v;
    }
}
```

从 v0 到 v3，同一 16M 输入的相对耗时量级示例大致是 3–4 倍差距，最终受限于全局内存带宽（读 64MB，HBM 带宽量级几百 GB/s → 理论下界在百微秒级），需按卡实测；这时 kernel 已经从“同步开销受限”翻转到“带宽受限”，再优化就只能上向量化访存。

**面试高频问法**：
1. 归约为什么用 `stride = blockDim/2` 递减，而不是从 1 开始倍增？→ 考点是 bank conflict 与早期 warp 活跃度。→ 从 1 开始时相邻线程访问相邻 bank、同一轮里 32 个线程打在少数 bank 上，且第一轮就有一半线程无事可做；递减版本第一轮 128 个线程两两配对，冲突和空转都更少。
2. Hillis-Steele 和 Blelloch 该选哪个？→ 考点是步数 vs 总工作量。→ 小 n 或延迟敏感选 Hillis-Steele（$\log n$ 步、实现简单）；大 n 选 Blelloch，工作量 $2n$ 而非 $n\log n$，在带宽受限时优势明显。
3. 大数组怎么做 scan，为什么要三段式？→ 考点是层级化与全局依赖。→ 单 block 只能覆盖 blockDim 个元素，必须先做 block 内 scan 得到 block 总和，再对总和数组做一次 scan，最后把偏移加回去；跨 block 的前缀依赖无法在一个 kernel 内廉价解决，这就是三段式的由来。
4. 归约最后一步怎么省掉第二次 kernel launch？→ 考点是 last-block-done 技巧。→ 每个 block 写完后用 `__threadfence()` 保证可见，再 `atomicInc` 一个计数器，计数到 `gridDim.x` 的那个 block 独自完成最终归约，避免额外 launch 的开销。
5. 扫描里的 bank conflict 出现在哪？→ 考点是 2 的幂步长的地址模式。→ up-sweep/down-sweep 中固定步长访问会让多个线程命中同一 bank，可用 shared 数组 padding（如 `s[2*i]`）或重排索引缓解；现代卡上 shared 带宽通常不是首要瓶颈，先确认是不是真的卡在这里。

## 第 7 章 矩阵乘：从 naive 到 shared-memory tiling 再到寄存器分块

**要解决的问题**：矩阵乘是唯一能把「访存 vs 计算」这条主线完整走完的 kernel——朴素实现只用得到峰值算力的百分之几，后面两档优化各自还清一笔具体的限制。不解决它，就说不清「算术强度」为什么是 kernel 优化的第一性原理。

**机制**。先算账。$C = AB$，三个 $N\times N$ 的 float 矩阵。

- **朴素版**：一个线程算一个 $c_{ij}$，读 $A$ 的第 $i$ 行 $N$ 个、$B$ 的第 $j$ 列 $N$ 个，做 $N$ 次 FMA。全局访存 $2N$ 个 float、计算 $2N$ FLOP，算术强度

$$\frac{2N\ \text{FLOP}}{8N\ \text{B}} = 0.25\ \text{FLOP/B}$$

  这个数远低于任何现代 GPU 的机器平衡点（每秒 FLOP 除以每秒字节，量级在 10 以上），所以朴素版一定受限于带宽，跟优化写得好不好无关。
- **shared tiling**：block 负责 $C$ 的一个 $T\times T$ 子块，沿 $k$ 维滑动。每个 k-step 把 $A$ 的 $T\times T$ 与 $B$ 的 $T\times T$ 搬进 shared memory，block 内所有线程复用。全局流量降 $T$ 倍，算术强度升到 $O(T)$。
- **寄存器分块**：每线程不只算 1 个输出，算 $TM\times TN$ 个。从 shared 读一个 `a`、一个 `b`，可以更新 $TM\times TN$ 个累加器，把 shared load per FMA 从 2 降到 $2/TM$（$TM=TN$ 时）。瓶颈于是从 LSU（load/store 单元）推回 FMA 流水。

三级流水是 global → shared → register，两级 `__syncthreads()` 切分。核心循环（16×16 线程的 block，block tile 32×32，每线程 2×2 输出）：

```cuda
#define BM 32
__global__ void mm_tiled(const float* A, const float* B, float* C, int N) {
    __shared__ float As[BM][BM + 1], Bs[BM][BM + 1];   // +1 消 bank conflict
    int tx = threadIdx.x, ty = threadIdx.y;             // blockDim = (16,16)
    int r0 = blockIdx.y * BM + ty * 2, c0 = blockIdx.x * BM + tx * 2;
    float acc[2][2] = {};
    for (int k0 = 0; k0 < N; k0 += BM) {
        for (int i = 0; i < 2; ++i) for (int j = 0; j < 2; ++j) {
            As[ty*2+i][tx + j*16] = A[(r0 + i) * N + k0 + tx + j*16];
            Bs[ty*2+i][tx + j*16] = B[(k0 + ty*2+i) * N + c0 + tx + j*16];
        }
        __syncthreads();                                // 搬完才能算
        for (int k = 0; k < BM; ++k) {
            float a0 = As[ty*2][k], a1 = As[ty*2+1][k];
            float b0 = Bs[k][tx*2], b1 = Bs[k][tx*2+1];
            acc[0][0] += a0*b0; acc[0][1] += a0*b1;
            acc[1][0] += a1*b0; acc[1][1] += a1*b1;     // 4 FMA / 4 shared load
        }
        __syncthreads();                                // 算完才能覆盖
    }
    C[(r0)*N + c0] = acc[0][0]; C[(r0)*N + c0+1] = acc[0][1];
    C[(r0+1)*N + c0] = acc[1][0]; C[(r0+1)*N + c0+1] = acc[1][1];
}
```

注意搬运那两行：`tx + j*16` 让一个 warp 内 32 个线程读连续的 32 个 float，读 $A$ 读 $B$ 都是合并的——这一步做错，tiling 的收益会被不成比例的访存事务浪费掉一部分。

**最小例子**。$N=1024$ 的 SGEMM，RTX 4090 级别卡（FP32 峰值约 80 TFLOPS、HBM 约 1 TB/s，量级示例，需按卡实测）。

| 版本 | 全局流量 | 算术强度 | 实测（量级示例，需按卡实测） |
|---|---|---|---|
| naive | $2N^3\times4\text{ B}\approx 8.6$ GB | 0.25 FLOP/B | 1–2 TFLOPS，峰值利用率 ~2% |
| shared tiling $T{=}32$，每线程 1 输出 | ~270 MB（降 32×） | ~8 FLOP/B | 10–15 TFLOPS，卡在 shared 带宽与指令发射 |
| 寄存器分块 8×8 | 同上 | 同上 | 接近 FP32 峰值，转为受限于 FMA 发射与寄存器压力 |

8×8 时每线程 64 个累加器加 16 个操作数，寄存器用量上百，occupancy 掉到 25% 上下仍然划算——这是第 4 章「占用率不是目标」最标准的反例。

**面试高频问法**。

1. 「矩阵乘为什么必须用 shared memory？」→ 考点是算术强度而非「shared 更快」→ 「朴素版每读 2 个 float 只做 1 次 FMA，算术强度 0.25 FLOP/B，注定受限于带宽；tiling 让 block 内 $T$ 个线程复用同一份数据，全局流量降 $T$ 倍，把瓶颈挪到别处。」
2. 「寄存器分块又解决了 shared 的什么问题？」→ shared 带宽与指令数 → 「每读一个 a、一个 b 更新 $TM\times TN$ 个累加器，shared load per FMA 从 2 降到 $2/TM$，LSU 不再是瓶颈，FMA 流水才能跑满。」
3. 「tile 大小怎么定？」→ 寄存器压力 vs 复用 vs occupancy 的三角 → 「累加器占 $TM\times TN$ 个寄存器，加上操作数与地址，8×8 附近常是 FP32 的甜点；再大就 spill 到 local memory，性能会大幅下降，必须按卡实测。」
4. 「`As[BM][BM+1]` 那个 +1 干什么？」→ bank conflict → 「按列访问时 `As[k][ty]` 会让 32 个线程落在同一 bank，padding 一个元素让列索引跨 bank 散开，shared 访问从 32 路冲突降到无冲突。」
5. 「为什么循环里要两次 `__syncthreads()`？」→ 数据依赖与缓冲区复用 → 「第一次保证整块搬完再开始算，第二次保证所有线程算完才能覆盖 shared 缓冲区进入下一个 k-step，少任何一个都会读到半成品。」

## 第 8 章 访存与合并：coalescing、对齐、向量化 load 与跨步访问

**要解决的问题**：同一份数据、同样的 FLOP，只改索引写法，有效带宽能差一个数量级。这一章回答「什么时候值得为 vectorized load 付对齐和尾部处理的复杂度」，以及一个跨步 kernel 该怎么改。

**机制**。

- **合并（coalescing）**：以 warp 为单位看地址。硬件把 32 个线程的地址聚合到 32 B 的 sector 上（sector 大小与 L1 事务粒度按架构而定）。32 个线程各取 4 B 连续 float = 128 B = 4 个 sector，一次事务拿满，利用率 100%。若步长是 32 个 float，32 个线程各落在一个不同 sector，取回 32×32 B 却只用 4 B，浪费 32 倍。
- **对齐**：`float4` 要求 16 B 对齐、`float2` 要求 8 B，编译器据此决定能否发射 128-bit load。`cudaMalloc` 返回的指针是对齐的，但 `&arr[1]` 不是。AoS 布局（`struct {float x, y, z;}`，12 B）会让每第 3 个元素的地址破坏 16 B 对齐，向量化直接失效；补 padding 到 16 B 或改 SoA 才行。
- **向量化 load**：一条 128-bit load 顶四条 32-bit，省的不只是事务数，还有地址计算指令和 LSU 流水占用。代价：必须对齐、元素数是向量宽度整数倍、尾部单独处理。在 LSU 受限的 kernel 上收益最大，在已经受限于 FMA 的 kernel 上可能测不出来。
- **跨步访问**：`data[i * stride]` 在 stride > 1 时立刻分散合并。典型受害者是按列求和、转置、AoS 里只取某一字段。两种修法：换布局（AoS → SoA），或用 shared memory 做「合并读 + 合并写」的转置中转。

**最小例子**。读 4 MB float 数组（$10^6$ 个元素），block 256，grid 覆盖全长：

```cuda
// A：warp 内地址连续 4 B —— 一个 warp 恰好 128 B
__global__ void good(const float* a, float* out, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = a[i] * 2.f;
}
// B：warp 内地址间隔 32 个 float = 128 B —— 32 个独立 sector
__global__ void bad(const float* a, float* out, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) out[i] = a[i * 32] * 2.f;
}
// C：A 的向量化版本，指令数降到 1/4
__global__ void good_vec4(const float4* a, float4* out, int n4) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n4) { float4 v = a[i]; v.x*=2; v.y*=2; v.z*=2; v.w*=2; out[i] = v; }
}
```

对照（量级示例，需按卡实测）：卡带宽 1 TB/s 量级时，C 接近 800 GB/s，A 约 600–700 GB/s，B 掉到 30 GB/s 上下——B 的有效带宽被 32 倍 sector 浪费固定住，跟线程数、grid 大小都无关。C 相对 A 的增益通常在 1.2–2 倍，取决于 kernel 是 LSU 受限还是带宽受限：带宽真打满了，减少指令数也不会更快。

转置是另一半：naive 转置读合并、写必然跨步（或反之），两遍里总有一遍浪费。用 `__shared__ float tile[32][33]` 中转，读时合并、写时合并，padding 的 +1 同时消掉 shared 的 bank conflict。

**面试高频问法**。

1. 「coalescing 以什么为单位判定？」→ 考点是 warp + sector，而非「地址连续就行」→ 「以 warp 为单位，看 32 个线程的地址落在几个 32 B sector 里，理想是 32×4 B 恰好 128 B、4 个 sector 一次拿满。」
2. 「float4 为什么能加速？什么时候不加速？」→ 指令数 / LSU 吞吐 → 「一条 128-bit load 顶四条 32-bit，省事务也省地址计算指令；但如果 kernel 已经打满带宽而不是卡在 LSU，减少指令数不会变快，这时候测出来就没差别。」
3. 「跨步访问除了浪费带宽还有什么代价？」→ cache 污染 + 可能的 bank conflict → 「取回 128 B 只用 4 B，L2 里塞满用不上的行，把后续真正有用的数据挤出去，有效容量也一起掉。」
4. 「拿到一个跨步的 kernel 怎么改？」→ 换布局 / shared 中转 → 「要么把 AoS 改成 SoA 让 warp 内自然连续，要么用 shared memory 做合并读 + 合并写的转置，两种都要求改完之后 warp 内地址连续。」
5. 「AoS 转 SoA 值不值？」→ 权衡一次性成本 → 「转换本身是一次全量读写，只有当这个数组被 kernel 反复遍历、或者转换能在数据生成侧顺手做掉时才划算；只读一遍的数组不值得。」

## 第 9 章 性能分析：Nsight Compute 的关键指标、stall 归因与 roofline

**要解决的问题**：让「这个 kernel 慢」变成「它被什么卡住、离硬件上限还差多少、改哪一行有收益」。没有这一步，前八章的优化手法就只能靠猜——tiling、向量化、提高占用率都可能白做，甚至互相抵消。

**机制**

Nsight Compute（ncu）以 replay 方式采集：同一 kernel 反复跑多遍，每遍打开一组硬件计数器（per-warp 采样 + PMU 事件），因此计数是分趟取的，不能当一次真实运行的时序看。采集粒度是 kernel launch，用 `ncu --set full ./app` 或 `ncu -k regex -c 1` 只抓某个 kernel；`--metrics` 可精确指定计数器名，避免全量 set 带来的巨大开销。

看指标要按三层顺序走，跳过任何一层都会误判：

1. **Speed of Light（SOL）**：`sm__throughput.avg.pct_of_peak_sustained_elapsed`（计算管线利用率）与 `gpu__dram_throughput.avg.pct_of_peak_sustained_elapsed`（显存带宽利用率），两者取大者即「离 roofline 的距离」。通常一个接近 100%，另一个很低——这就是 roofline 的横轴位置：Dram% 高是 memory bound，SM% 高是 compute bound，两个都低说明既没吃满带宽也没吃满算力，问题在延迟未隐藏（占用率、依赖链、指令数）。
2. **Warp State / stall 归因**：`smsp__average_warps_issue_stalled_*_per_issue_active.ratio` 系列，把「每个发射周期里 warp 为什么没发出指令」拆成若干桶：`long_scoreboard`（等全局内存返回）、`short_scoreboard`（等 shared/纹理）、`barrier`（等 `__syncthreads`）、`mio_throttle`（shared/特殊功能单元排队）、`lg_throttle`（load/store 队列满）、`math_pipe_throttle`（算力管线排队）、`not_selected`（有 warp 就绪但调度器选了别人，说明占用率过剩）、`wait`（固定延迟依赖）。
3. **Occupancy 与 Achieved Occupancy**：`sm__warps_active.avg.pct_of_peak_sustained_active`（理论上限，由寄存器和 shared 用量决定）与 `smsp__warps_active.avg.pct_of_peak_sustained_active`（实际达到）。两者差距大 = tail effect 或 block 粒度不均；两者都低且 stall 是 long_scoreboard = 需要提高并行度或做数据复用。

roofline 的用法：横轴是 arithmetic intensity（FLOP/Byte），纵轴是可达 FLOP/s，屋顶取 `min(峰值算力, 带宽 × AI)`。kernel 的 AI 由算法和分块决定（第 7 章 shared-memory tiling 不改 AI，寄存器分块与复用才改），所以 roofline 上的点会随实现移动——它诊断的是「这个算法在这个数据规模下有没有必要继续优化算力」。

```bash
ncu --set full -k matmul_naive -c 1 ./matmul
# 关注输出中的：
#   Memory Throughput [%]      -> DRAM 利用率
#   Compute (SM) Throughput    -> 计算管线利用率
#   Achieved Occupancy         -> 实际占用率
#   Warp Stall: Long Scoreboard-> 等全局内存
```

**最小例子**

同一 1024×1024 的 SGEMM，两块卡之外的对照只看相对关系（量级示例，需按卡实测）：

| 版本 | DRAM% | SM% | achieved occ | 主 stall | 结论 |
|---|---|---|---|---|---|
| naive（每线程读一列） | ~70% | ~15% | 高 | long_scoreboard | 重复读，纯带宽浪费，AI≈0.25 |
| shared tiling 32×32 | ~45% | ~55% | 中 | short_scoreboard / barrier | 已过 crossover，开始受算力限制 |
| 寄存器分块 8×8 + 向量化 | ~35% | ~85% | 低（寄存器压力大） | math_pipe_throttle | compute bound，接近 roofline 屋顶 |

一次具体判断：naive 版看到 DRAM 70% + long_scoreboard 主导，说明它在等内存而不是在算——此时提高占用率没用（已经很高），唯一有效的是减少访存量（tiling）。反过来寄存器分块版 achieved occupancy 掉到 30%，但 SM% 85%，此时「提高占用率」是错误方向，因为瓶颈是算力管线排队，砍寄存器只会让每线程算得更少、访存更多，AI 反而下降。

**面试高频问法**

1. **「你怎么判断一个 kernel 是 memory bound 还是 compute bound？」→ 考点是 roofline 的实际用法而不是背定义。→ 答法：先用 ncu 的 SOL 段看 DRAM 与 SM 两个 throughput 百分比谁高，谁高谁就是瓶颈方向；再用 arithmetic intensity 对照 roofline 的屋顶拐点，确认这个 AI 下理论上限是多少，判断还有多少空间。两个都低就不是 bound，是延迟没藏住，去看 stall 和 occupancy。**
2. **「long_scoreboard stall 高，怎么办？」→ 考点是能否区分「访存太多」和「访存等待没被隐藏」。→ 答法：先看 DRAM 利用率，如果已经很高，说明访存量本身大，要做数据复用（tiling、寄存器分块、合并访存）；如果 DRAM 不高但 long_scoreboard 高，是延迟没藏住，要提高占用率或做指令级并行（一个线程发多个独立 load）。这两种情况的解法方向相反，不能一律「加 occupancy」。**
3. **「achieved occupancy 只有 30%，是不是要优化到 60%？」→ 考点是占用率的真实取舍（第 4 章）。→ 答法：不必然。占用率只是为了隐藏延迟的手段，如果 SM throughput 已经 85% 且主 stall 是 math_pipe_throttle，说明算力已经吃满，提高占用率无收益；反过来如果 stall 是 long_scoreboard 且 occupancy 低，才值得降寄存器/shared 用量去换。**
4. **「`not_selected` stall 高说明什么？」→ 考点是理解 warp 调度器与占用率过剩。→ 答法：说明有 warp 就绪但发射端口被别的 warp 占了，是占用率过高、指令发射带宽成为瓶颈的信号，通常伴随 math_pipe_throttle 或 lg_throttle，此时降低占用率、提高每线程工作量反而更好。**

---

## 第 10 章 工程边界：什么时候不该用 CUDA，CUDA 与 HIP / OpenCL / 推理框架的关系

**要解决的问题**：把「CUDA 很快」变成「这笔迁移划不划算」。前九章都在讲怎么把 kernel 写快，这一章讲什么情况下根本不该写 kernel、什么情况下必须换运行时——判断错方向，优化做得再好也是负收益。

**机制**

决策本质是三个量的乘积：**可并行度 × 单次数据量 × 调用频次**，再除以**迁移与维护成本**。GPU 的收益来自把固定开销摊薄，固定开销包括 kernel launch（量级示例：几微秒，需按卡与驱动实测）、host-device 拷贝（PCIe 上量级示例：十几 GB/s，NVLink 高一个数量级）、以及每次 launch 的同步等待。

由此得到几条硬边界：

- **数据量太小不值得**：单次计算量小于 launch + 拷贝开销时，GPU 版本可能比 CPU 慢。粗略门槛是「传输时间 ≫ 计算时间节省」不成立即可；可用 roofline 反推：如果 AI 极低且总数据只有几 MB，带宽根本跑不满。
- **调用频次高、每次数据小是最坏情况**：典型是逐元素小算子、逐样本推理、控制流密集的分支计算。解法不是优化 kernel，而是**批处理（batching）**——把 N 次小调用合成一次大调用，把固定开销摊薄。
- **控制流密集 / 分歧严重**：warp divergence（第 4 章）让有效吞吐按分支数下降，图算法、解析、稀疏不规则访问往往在 CPU 上更快，或在 GPU 上需要完全不同的数据布局（CSR/CSC、按度排序）。
- **必须在 device 上常驻数据**：如果数据本来就在 GPU 上（前一个 kernel 的输出），就没有拷贝开销，边界整体右移。

跨平台运行时的关系要分清层次：**CUDA** 是 NVIDIA 专有的编程模型 + 运行时 + 工具链（nvcc、cuBLAS、Nsight），**HIP** 是 AMD 的对位抽象，源码级兼容 CUDA（多数 kernel 只需改头文件与少量 API 名），能编译到 ROCm 或再经 HIP-CUDA 层回到 NVIDIA；**OpenCL** 是更底层的跨厂商标准（Khronos），表达力更接近「设备 + 命令队列 + kernel 字符串」，没有 warp/block 之外的 NVIDIA 特有假设，因此可移植性好但缺少 CUDA 生态里的库与工具；**SYCL** 是建立在 OpenCL/其他后端之上的单源 C++ 抽象层。选择逻辑是：只在 NVIDIA 上跑且要生态 → CUDA；要多厂商且能接受工具链落差 → HIP（AMD 卡）或 SYCL/OpenCL；已有大量 CUDA 代码要移植 AMD → HIP 的源码兼容是成本最低路径。

与推理框架的关系要摆正：TensorRT / ONNX Runtime / vLLM 这类是**图级/服务级**的引擎，它们内部会调用高度调优的 kernel（多为 cuBLAS/cuDNN/CUTLASS 或自研），并提供算子融合、量化、KV cache 管理、批调度。工程含义是：**绝大多数场景不该手写 kernel，而应把融合和批处理交给框架**；只有当框架里没有你需要的那类算子（新算子、特殊量化、特殊 attention 变体）时才落到 kernel 层，写完后以自定义算子形式接回框架。这一层的性能问题通常是调度和批大小，不是单个 kernel 的 stall——用第 9 章的工具前先确认瓶颈层级。

**最小例子**

同一段 elementwise 计算（`y[i] = sin(a[i]) * b[i] + c`），N 个 float：

| 场景 | N | 传输 | 计算 | 端到端 | 结论 |
|---|---|---|---|---|---|
| 单次调用 | 1e4（40 KB） | 量级 µs 级拷贝 + launch | 远小于开销 | 比 CPU 慢 | 不该上 GPU |
| 单次调用 | 1e8（400 MB） | 量级 几十 ms（PCIe） | 量级 ms | 与 CPU 相当或略优 | 边界附近，看是否已在 device 上 |
| 已在 device、批处理 | 1e8，100 次连续 launch 无回拷 | 0 | 量级 ms | 明显优于 CPU | 正确用法 |

具体执行配置对照：单次 1e4 元素，grid = 40 blocks × 256 threads（每线程 1 个元素，量级示例），kernel 本体只有几十条指令，launch + 拷贝占端到端 90% 以上——此时任何 kernel 级优化（向量化、提高占用率）最多改善剩下那 10%。正确动作是把 1000 次这种小调用在 host 侧攒成一次 1e7 元素的调用，或直接把数据留在 device 上链式调用。

**面试高频问法**

1. **「什么时候不该用 CUDA？」→ 考点是能否量化边界而不是喊口号。→ 答法：看三个量的乘积——可并行度、单次数据量、调用频次。数据小到 kernel launch 和拷贝开销盖过计算收益时不该用；调用频次高且每次数据小，要先做批处理而不是优化 kernel；控制流密集、分歧严重、访存不规则的场景在 GPU 上有效吞吐会按分支数打折，往往 CPU 更快或需要换数据布局。**
2. **「HIP 和 CUDA 是什么关系？」→ 考点是分清抽象层与厂商实现。→ 答法：HIP 是 AMD 的对位编程模型，源码级兼容 CUDA，多数 kernel 改头文件和少量 API 名就能编译到 ROCm；它是同一个抽象在不同硬件上的实现，不是更高层的封装，所以性能调优的手法和 warp/占用率概念基本一致，差别在硬件参数和工具链（rocprof 对 Nsight）。**
3. **「有了 TensorRT/vLLM 还需要写 CUDA kernel 吗？」→ 考点是知道框架解决的是哪一层问题。→ 答法：框架解决图级优化——算子融合、量化、批调度、KV cache 管理，内部调用的都是已调优的 kernel，绝大多数场景不该手写。只有框架里不存在你需要的那类算子（新算子、特殊量化、特殊 attention 变体）时才下沉到 kernel 层，写完以自定义算子接回框架；而且这一层的瓶颈常在调度和批大小，不是单个 kernel 的 stall。**
4. **「移植到别的厂商，路径怎么选？」→ 考点是成本与生态的权衡。→ 答法：已有大量 CUDA 代码且目标是 AMD，走 HIP 的源码兼容成本最低；要多厂商可移植、能接受工具链和库的落差，走 SYCL/OpenCL；只在 NVIDIA 且重度依赖 cuBLAS/cuDNN/Nsight，就留在 CUDA。关键成本不在改语法，而在重写依赖厂商库的那部分和对性能重新做一遍 profile。**
5. **「一个 kernel 优化到 roofline 屋顶了，端到端还是慢，为什么？」→ 考点是能否跳出 kernel 层看系统。→ 答法：说明瓶颈不在这个 kernel。要么固定开销（launch、拷贝、同步）占比大，要对小调用做批处理或让数据常驻 device；要么瓶颈在图级调度、批大小、通信或 IO；要么这个 kernel 只占端到端的一小部分。先用 profiler 做时间归因找到占比最大的那段，再决定是否继续做 kernel 级优化。**
