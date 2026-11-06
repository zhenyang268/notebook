## 一、它解决什么问题

CUDA 相关的工程事故形态很固定：同一个 kernel 在 A100 上跑 3 ms，换到 H100 反而更慢；同一个算法别人写 0.8 ms、你写 12 ms，除了「慢」说不清慢在哪；浮点归约结果每次运行都不同，被当成 bug 排查三天。这三类问题本质上是同一个：**没有把「瓶颈是什么」变成可测量的量**。

具体场景一：向量加 / 归约。100M 个 float（输入输出合计约 800 MB），在 HBM 带宽 1.5–3 TB/s 的卡上，带宽下界约 $\frac{0.8\text{ GB}}{2\text{ TB/s}}\approx 0.4$ ms（量级示例，需按卡实测）。朴素版实测常高出数倍，差值几乎全部来自访存未合并、block 过小、寄存器溢出到 local memory。对应面试题：为什么归约要两两配对，而不是 `stride=1` 隔一个加一个？

场景二：GEMM。naive 版每个线程算一个 $C_{ij}$，需读 $2K$ 个 float；$N=4096,\ K=4096$ 时全局访存总量比计算量高两个量级，卡在带宽而非 FMA。做完 shared-memory tiling 后复用度上来，才轮到算术强度说话。对应面试题：tiling 之后为什么还要寄存器分块？

这项能力拦住的，是「凭直觉调参」和「只会调库」之间的那段空白：**能否用一个指标（有效带宽、achieved occupancy、stall 归因、算术强度）说明当前瓶颈，并预估下一步优化的上限**。

**入口（本文的读法）**：在 CUDA 的 `cudaLaunchKernel` 配置、SIMT 调度、延迟隐藏/吞吐优先、`gridDim/blockDim/threadIdx/blockIdx` 索引、HBM/L2/shared memory/constant/register 层次、warp 分支与 `__syncthreads`/`atomicAdd` 约束下，本文把“跨卡变慢、归约非确定、GEMM/归约慢”换成可测机制账：`float4`/`ldg` 的 global memory sector 事务、shared tile array 的 32-bank 访问、`__shfl_down_sync`/`atomicAdd` 的归约顺序、register spill 到 local memory、`achieved occupancy`、`stall reason`、`memory throughput`、`arithmetic intensity` 与 roofline；换的是从调 `blockDim`、`__launch_bounds__`、`#pragma unroll`、tile size 的直觉，转为按 Nsight Compute 指标和 PTX/SASS 指令定位瓶颈。

**不换的是什么**：全程不变的是 CUDA 的 SM 资源账本与语义账本——warp scheduler 发射、register file 配额、shared memory 32 bank、global memory sector 事务、`__syncthreads` 全 block 屏障、atomic 内存序与浮点加法不满足结合律；因此看到差异先问 Nsight Compute 的 `achieved occupancy`、`stall reason`、`global memory coalescing efficiency`、`shared bank conflict`、`local memory spill`、`arithmetic intensity` 是否变化，并按“occupancy 未变而 `long scoreboard` 涨查 global load 合并/延迟，`barrier` 涨查 `__syncthreads`/warp divergence，`bank conflict` 涨查 shared 索引 stride，结果非确定查 `atomicAdd`/`__shfl_down_sync` 顺序”决定改 `blockDim`、`__launch_bounds__`、`float4`/`ldg`、shared tile 或 atomic 顺序。

## 二、为什么这样做（方法论设计）

**有口径才算数的**：同卡、同输入规模、同编译选项下的前后对照；roofline 上的算术强度与脊点位置；Nsight Compute 的 Speed of Light（Memory / Compute Throughput 百分比）、Achieved vs Theoretical Occupancy、stall 原因分布、shared memory bank conflict 计数、branch efficiency；CUDA event 计时的 kernel 时间中位数（含 warmup）。这些都能被第三方复现。

**看起来专业但无法证伪的**：「我用了 shared memory 所以更快」「我做了 coalescing 所以更优」「occupancy 拉到 100% 性能就好了」。这类说法没有基线、没有量化差距、没有说明代价，换一张卡就翻车——不是错，是不可证伪，因此在面试里等于没答。

**指标怎么定**：每章统一四步节奏——朴素版基线 → 用 profiler 定位瓶颈 → 只改一个变量 → 再测、再定位。基线必须写清：卡型号、输入规模、编译选项、计时方式。判据用「是否逼近该卡的 roofline 上限」而不是「是否比上一版快」，因为后者在抖动范围内可能只是噪声。

**边界与失效条件**：单 kernel 时间接近启动开销（微秒量级，量级示例）时，kernel 内优化收益被 launch 开销吃掉；数据规模低于饱和点（并行度填不满 SM）时，讨论占用率无意义；分支密集、强数据依赖的算法（稀疏、图遍历、递归）本就不适合；跨架构迁移时 SM 数、shared memory 上限、寄存器文件大小都变，昨天的结论不成立。

**常见错误做法的代价**：盲目压寄存器抬 occupancy → 变量溢出到 local memory，实际访存变多，通常更慢；把所有数据塞进 shared memory → 每 SM 能驻留的 block 数下降，占用率反降；用 `atomicAdd` 做全局归约 → 冲突线程串行化，代价随冲突度上升，按实现而定；不 warmup 直接计时 → 首次包含模块加载与上下文开销。

## 三、章节大纲

1. **GPU 与 CPU 的结构差异：SIMT、延迟隐藏与吞吐优先**：SM 内大量轻量线程、靠切换而非缓存隐藏延迟的模型。回答：为什么 GPU 的核数不能直接类比 CPU 主频？
2. **CUDA 编程模型：grid / block / warp**：三层映射与「block 内可同步、block 间不可同步」的硬约束。回答：为什么不能假设两个 block 的执行顺序？
3. **索引计算与执行配置怎么选**：`blockDim` 取 32 的倍数、grid 规模覆盖数据并处理尾巴。回答：`blockDim=1024` 一定比 `128` 好吗，代价是什么？
4. **内存层次：全局、共享、常量、寄存器**：各级容量、带宽、作用域差异与访问代价排序。回答：什么数据该放常量内存，什么该放 shared memory？
5. **bank conflict 与本地内存溢出**：32 个 bank 的映射、跨步访问导致串行化、寄存器超限溢出到 local。回答：怎么判断一个 kernel 的局部变量被放进了 local memory？
6. **线程束与分歧：warp divergence**：同一 warp 内分支串行执行，代价是路径数倍的指令发射。回答：怎么用数据布局把分支变成无分歧？
7. **占用率（occupancy）的真实取舍**：占用率是隐藏延迟的手段而非目标，与寄存器/shared memory 的三角权衡。回答：为什么 occupancy 提高 30% 反而变慢？
8. **同步与原子：__syncthreads、原子操作、浮点归约的非确定性**：屏障语义、原子冲突、浮点加法不满足结合律。回答：为什么并行归约每次结果不一样，怎么让它可复现？
9. **归约与扫描：两个经典 kernel 的逐步优化**：从交错访问到两两配对、shared memory 树形归约、`__shfl_down_sync`、扫描的 Blelloch / 分块两段式。回答：归约到最后一个 warp 时为什么还要处理？
10. **矩阵乘：从 naive 到 shared-memory tiling 再到寄存器分块**：每级优化各自把瓶颈从带宽推向计算、再推向寄存器压力。回答：每一步优化后，profiler 上哪个指标应该变化？
11. **访存与合并：coalescing、对齐、向量化 load 与跨步访问**：一个 warp 的 32 次访问如何合并成若干 128 B 事务；`float4` 的对齐前提。回答：结构体数组 vs 数组结构体，选哪个、为什么？
12. **性能分析：Nsight Compute 的关键指标、stall 归因与 roofline**：从 SOL 到 stall 采样再到 SASS 级定位的完整链路。回答：给你一个慢 kernel，你的前三个 ncu 动作是什么？
13. **工程边界：什么时候不该用 CUDA，CUDA 与 HIP / OpenCL / 推理框架的关系**：移植成本、库覆盖度、团队能力。回答：这个任务该手写 kernel 还是调库？

## 四、不做什么 · 必要性 · 失效点

### 必要性：删掉会怎样

| 机制 | 删掉会怎样 | 判定 |
|---|---|---|
| CUDA event 计时的 kernel 时间中位数（含 warmup） | 删掉 warmup 与中位数，首个 `cudaLaunchKernel` 的 module load / context init / DVFS 爬坡进入样本，10 μs 级 kernel 的 A/B 差值会被 launch overhead 与计时抖动覆盖，无法判定是否超过 profiler 阈值 | 必需 |
| Nsight Compute 的 Speed of Light（Memory / Compute Throughput 百分比） | 删掉 Memory / Compute Throughput 百分比，只保留总时间，GEMM 无法区分卡在 DRAM 读 $A/B$ tile 还是卡在 FMA pipe，roofline 脊点是否到达不可判定 | 必需 |
| shared memory tiling | 删掉 shared memory tiling，GEMM 每个线程仍从 global memory 读 $2K$ 个 float，Memory Throughput 先饱和，Compute Throughput 无法接近峰值 | 必需 |
| register blocking | 删掉 register blocking，shared memory 载入的 tile 仍反复经 `ld.shared` / `st.shared` 喂给 FMA，LSU 指令占比与 shared memory bank conflict 计数上升，FMA pipe utilization 被 load/store 挤占 | 必需 |
| Achieved vs Theoretical Occupancy | 删掉 Achieved / Theoretical Occupancy，压寄存器导致 spill 到 local memory 时，只能看到 local `ld/st` 增加，无法判断是 warp 驻留不足还是寄存器文件限制，下一步优化上限不可估 | 必需 |
| branch efficiency | 删掉 branch efficiency，向量加 / GEMM 的 warp 分支均匀，结论不变；稀疏或图遍历 kernel 中 divergent 分支会被平均成低 IPC，无法区分 FMA 不足还是分支串行化 | 选择 |

### 失效点：哪条前提一破，结论就变

- 输入/输出数组驻留 HBM 且单次 kernel 时间 ≥ 100 μs → 若数组走 pageable host memory 或 kernel < 10 μs，`cudaMemcpy` / `cudaLaunchKernel` 开销进入 CUDA event 时间，Memory Throughput 百分比不再代表 kernel 瓶颈。
- grid block 数 ≥ 4 × SM 数且每 SM 可驻留 ≥ 2 block → 若换到 SM 数更低或 block 数不足，Achieved Occupancy 受 grid 并行度限制而非 register file / shared memory 限制，占用率结论失效。
- 每 SM shared memory 上限 ≥ 48 KB 且 tile 不触发 `cudaFuncAttributeMaxDynamicSharedMemorySize` 失败 → 若迁移到旧架构或 MIG 分区导致 shared memory per SM 下降，block 驻留数下降，bank conflict 计数与 occupancy 结论变化。
- Nsight Compute 可读取 hardware performance counters（profiling permission 开启、driver / GPU 支持） → 若云实例禁用 counters 或 MIG 分区不支持，Speed of Light 与 stall 归因不可得，只能退回 CUDA event，无法判定瓶颈。
- GPU 时钟源稳定且 CUDA event 采样间隔小于被测 kernel 时间 → 若 DVFS 降频、MPS 共享 GPU 或 kernel 时间接近 1 μs 量级，kernel time median 漂移，A/B 差值可能低于时钟抖动，优化收益判定失效。

### 不做什么（范围）

- **不写语言与工程语法**：C++ 模板、pybind11、CMake 交叉编译属于别的层，只在 `extern "C"` 影响 kernel 签名时提一句。
- **不写 408 类体系结构考点**：Cache 映射、TLB、进程调度不展开；只在解释「为什么 GPU 用切换而非缓存隐藏延迟」时对照一句。
- **不写深度学习训练框架与推理框架的用法**：cuBLAS/cuDNN API、分布式训练、图优化、量化部署属于 `ai/`；本目录只讨论 kernel 本身与它的性能。
- **不做 API 手册**：每个 API 只在它解决某个具体瓶颈时出现，罗列参数不是目标。
- **不写 PTX / SASS 手写与驱动级调优**：只在 stall 归因时读 profiler 给出的 SASS 采样。
- **不给固定硬件参数表**：带宽、SM 数、寄存器文件大小随卡与功耗墙变化，一律标「量级示例，需按卡实测」；不确定处写「按实现而定」。

## 五、面试怎么讲

**30 秒版本（120–180 字）**

CUDA 这块我能证明的是「给定一个慢 kernel，我能定位它卡在哪」。做法是固定一套口径：同卡、同输入、同编译选项，先用朴素版做基线，再用 Nsight Compute 看 Speed of Light 判断是带宽还是计算受限，对照 roofline 的脊点确认上限，然后看 stall 归因——是等全局内存、等 shared memory、还是分支发散。每轮只改一个变量，用 CUDA event 取 kernel 时间中位数验证。归约、扫描、GEMM tiling、访存合并这几类经典 kernel 我都能说清每一步优化预期改哪个指标、代价是什么。

**可能被追问的 6–8 个点**

1. **「你怎么判断一个 kernel 是带宽受限还是计算受限？」** → 考点：roofline 与算术强度。→ 答：算 $\text{AI}=\text{FLOPs}/\text{Bytes}$，与该卡的脊点（峰值 FMA ÷ HBM 带宽，量级示例，需按卡实测）比较定上界；再用 ncu 的 Speed of Light 看 Memory Throughput% 与 Compute Throughput% 哪个先顶到高位，两个都低说明是延迟或并行度问题，转而看 Achieved Occupancy 和 stall 分布。
2. **「occupancy 是不是越高越好？」** → 考点：延迟隐藏与资源权衡。→ 答：不是。对比 ncu 的 Achieved 与 Theoretical Occupancy，再看 stall 是否仍是 Long Scoreboard（等全局内存）；若是，加并行度无效。用 `__launch_bounds__` 或 `maxrregcount` 试点时，必须同时看 local memory 用量有没有上升——溢出换来的占用率通常净亏。
3. **「shared memory 怎么用才不亏？」** → 考点：bank conflict 与容量换占用率。→ 答：看 ncu 的 shared memory wavefronts / bank conflict 计数；经典判据是 $32\times 32$ 的 tile 加一列 padding 变成 $33$ 后冲突计数应显著下降（按实现而定）。同时确认每 block 的 shared memory 需求有没有把占用率压低一档。
4. **「归约怎么写，结果为什么不稳定？」** → 考点：warp shuffle 与浮点非结合性。→ 答：路径是全局交错访问 → 两两配对 → shared memory 树形 → 最后一个 warp 用 `__shfl_down_sync` 收尾，每步用有效带宽对照 naive 版。浮点加法不满足结合律，求和顺序随调度变化结果就变；要可复现就固定归约顺序、或用 Kahan 补偿求和、或直接用双精度累加。
5. **「矩阵乘怎么一步步优化？」** → 考点：分块复用与寄存器压力。→ 答：naive → shared-memory tiling（block tile 内复用 A、B）→ 每线程算 $T_m\times T_n$ 个输出的寄存器分块。判据不是「更快」，而是 ncu 上算术强度上升、stall 主因从 Long Scoreboard 转向 MIO / Short Scoreboard 或计算吞吐顶到高位。
6. **「warp divergence 怎么量化？」** → 考点：分歧的串行化代价。→ 答：用 ncu 的 branch efficiency 与每 warp 实际发射指令数，分歧时同一 warp 要跑完所有路径；验证手法是把边界对齐到 32 线程看差异是否消失。
7. **「怎么证明你的优化真的有效？」** → 考点：实验设计。→ 答：同卡同输入、warmup 后多次取中位数、只改一个变量、用 CUDA event 测 kernel 时间而非 host 端墙钟；判据是前后差异大于 run-to-run 抖动，且能对应到某个 profiler 指标的变化。
8. **「什么时候不该用 CUDA？」** → 考点：工程边界。→ 答：数据量小到启动开销（微秒量级）占比显著、分支或数据依赖密集、cuBLAS/cuDNN 已经覆盖且手工打不过、团队没有 profiling 能力；跨厂商可移植性优先时看 HIP / OpenCL（它们与 CUDA 的编程模型映射关系需要单独评估）。

**别说什么**

- 「所有 kernel 我都手写优化过」——一追问 ncu 指标和 stall 归因就露怯。
- 「occupancy 调到 100% 就快了」——把手段当目标，且回避寄存器溢出代价。
- 「用了 shared memory 就比全局内存快」——不提 bank conflict 与占用率代价。
- 「实测提升 N 倍」却说不出基线、卡型号、输入规模和计时方法。
