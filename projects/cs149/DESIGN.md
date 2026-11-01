# CS149 · 并行计算 · 设计文档

> 本文是该项目的设计说明，不是教程。
> 大纲见 `OUTLINE.md`，一小时上手见 `QUICK.md`，详细记录见 `NOTES.md`。

## 一、定位与边界

本项目是实验型性能分析工程：用固定 workload 和可复现计时，测串行基线、SIMD、CPU 多线程与 GPU 的加速比，并用伪共享实验把缓存一致性从概念变成可测现象。它解决“会写并行代码但说不清加速比来源”的问题，输出数据与归因，不输出 API 教程。

不解决：不实现编译器自动向量化，不做 CPU 微体系结构模拟，不覆盖多机 MPI 与分布式一致性；GPU 只到 CUDA 内存层次与占用率的基本验证，不展开 PTX/SASS 调优。

与相邻项目分工：体系结构项目负责 cache 组织与 MESI 理论推导，本项目负责实测一致性流量与伪共享；GPU 深入项目负责 tiling 与 occupancy 调优，本项目只做 CPU-GPU 基线对比与端到端开销核算。

## 二、整体架构

模块划分与职责：

- `harness`：配置解析、绑核、warmup、重复计时、统计输出。
- `workloads`：向量加、点积、归约、矩阵乘、stencil，统一提供 `run(config)` 与 checksum。
- `cpu_backends`：scalar、AVX2、OpenMP、std::thread；每个后端只实现 workload 接口。
- `gpu_backends`：CUDA kernel 与 host-device 拷贝封装。
- `analysis`：加速比、效率、Amdahl/Gustafson 拟合、roofline 点、一致性实验对比。
- `report`：CSV 与图表。

调用方向：`harness → workloads → backend`；`analysis` 只读 `harness` 产出的 `TimingSample` 与 `Result`，不反向调用 backend；`report` 只读 `analysis`。`RunConfig` 由 `harness` 构造，backend 不得修改全局状态。

## 三、技术选型与理由

C++17：SIMD intrinsics、std::thread、CUDA 互操作在同一语言内，避免跨语言计时边界；不用 Python 是因为解释器与 GIL 干扰计时。OpenMP：用 `parallel for` 与 `reduction` 快速得到数据并行基线，减少线程样板；但保留 std::thread 后端，因为伪共享实验需要精确控制对齐、padding 与线程亲和。AVX2 intrinsics：显式控制向量宽度、对齐与尾部，替代依赖 auto-vectorization，保证不同编译选项下可复现；不用 ISPC 是因为多一套工具链且调试成本高。CUDA：课程 GPU 部分的标准工具链，`cudaEvent` 与 Nsight 可脚本化；替代 OpenCL 是因为 NVIDIA 环境成熟。计时自写 harness 而非 Google Benchmark：需要绑核、固定重复次数与统一 CSV 字段；`perf stat` 仅作 cache-misses 佐证，不进入主计时。

## 四、数据流

输入 `RunConfig{workload, N, backend, threads, repeats, pin, seed}` → harness 按 seed 生成对齐到 64B 的输入数组，计算串行基线 $T_1$ 并校验 checksum → 调用目标 backend，warmup 3 次后重复 `repeats` 次，得到 `TimingSample{t, bytes, flops, cache_misses}` → backend 回写 `Result{checksum, output}` → analysis 计算 $S=T_1/T_p$、效率 $S/p$，与 Amdahl 上界

$$S_{\max}=\frac{1}{(1-f)+f/p}$$

比较，并用 bytes/flops 算 arithmetic intensity → report 输出 CSV 与图。伪共享实验走同一数据流，只把 workload 换成“两线程各累加计数器”，通过 `alignas(64)` 与相邻布局生成两组 `RunConfig`。

## 五、章节目录与知识点映射

| 章 | 内容 | 涉及的知识点 | 与考纲或前置项目的关系 |
|---|---|---|---|
| 1 | 性能度量与 Amdahl | 强/弱扩展、加速比与效率、Amdahl 上界、Gustafson 修正、计时噪声 | 前置：CPI 与存储层次；考纲：并行性能 |
| 2 | SIMD 向量化 | 向量宽度、对齐、strip mining、尾部掩码、内存带宽上限 | 前置：数据表示；考纲：数据级并行 |
| 3 | OpenMP 数据并行 | `parallel for`、reduction、static/dynamic 调度、竞争与负载均衡 | 前置：线程基础；考纲：共享内存并行 |
| 4 | std::thread 与同步 | mutex、条件变量、原子操作、内存序、线程生命周期 | 前置：操作系统线程；考纲：同步与互斥 |
| 5 | 伪共享与缓存一致性 | cache line 64B、MESI 状态迁移、写无效、一致性流量、padding | 前置：cache 组织；本项目核心实验 |
| 6 | 归约与扫描 | 树形归约、并行前缀和、工作/深度、原子归约瓶颈 | 前置：算法分析；考纲：并行算法 |
| 7 | GPU 与 CUDA | SIMT、warp 分歧、合并访存、共享内存 bank conflict、occupancy、H2D/D2H 开销 | 前置：SIMD；后续：GPU 优化项目 |
| 8 | 综合归因 | roofline、arithmetic intensity、memory-bound 与 compute-bound、性能计数器校验 | 前置：第 1、2、7 章；考纲：性能建模 |

## 六、验收判据

1. 单元与集成测试 16/16 通过，覆盖 $N$ 非 8 倍数尾部、$N=1$ 边界与 checksum 容差。
2. 强扩展：double 矩阵乘 $N=1024$，OpenMP 8 线程相对单线程标量 $S\ge5.0$，效率 $\ge0.62$；AVX2 后端相对标量 $S\ge3.2$。
3. 弱扩展：每线程规模增加 25%，8 线程耗时增长 $\le1.15$ 倍。
4. 伪共享：相邻计数器版本比 `alignas(64)` 隔离版本慢 $\ge2.0$ 倍，`perf stat` cache-misses $\ge2$ 倍，重复 5 次方向一致。
5. GPU：float 向量加 $N=2^{24}$，kernel 相对单线程 CPU $S\ge10$，含 H2D/D2H 端到端 $S\ge4$；CUDA tiled 矩阵乘 $N=1024$ 相对 8 线程 OpenMP $S\ge3$。
6. 数值：double 归约/点积相对误差 $<1e-7$，float $<1e-4$，不要求逐位一致。
7. 计时：每配置重复 10 次取中位数，95% 置信区间半宽 $\le5\%$。
8. Amdahl：$f$ 由代码分段估计，模型与实测加速比 $R^2\ge0.9$，并报告偏离原因。

## 七、风险与已知坑

- 死代码消除：编译器删掉未使用结果；用 checksum 写回并打印，输入运行时生成。
- 计时噪声：turbo、频率缩放、NUMA、线程迁移；用线程亲和与绑核，重复取中位数并记录环境。
- 伪共享实验被预取与原子操作干扰；确保两计数器同 cache line 且由不同核写，对照用 padding，不要用 atomic 加掩盖竞争。
- SIMD 尾部与对齐：$N$ 非向量宽度倍数会越界；用 maskload 或标量尾，ASan 验证。
- OpenMP 超订：线程数超过物理核导致效率骤降；设 `OMP_PROC_BIND` 并扫描线程数。
- CUDA 异步：未同步计时偏小；kernel 前后 `cudaDeviceSynchronize`，warmup，页锁定内存单独报告。
- 浮点归约顺序变化导致 checksum 不一致；用容差，不比较逐位。
- Amdahl 的 $f$ 若由实测反推再声称验证会循环论证；$f$ 必须来自代码分段或关闭并行的实测。

## 八、与其他项目的关系

前置：C++、体系结构中的 cache line、CPI 与存储层次，以及线性代数。后续：GPU 优化项目可复用 CUDA 基线；分布式项目可把强/弱扩展定义迁移到 MPI；性能工程项目复用 harness 与报告。可复用模块：计时与绑核 harness、CSV/图表脚本、SIMD 尾部工具、CUDA 错误检查宏、伪共享对照 workload。
