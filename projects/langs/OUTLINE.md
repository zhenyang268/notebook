# langs/ · 语言与并行执行模型

> 分组目录：两门主力语言的「运行时真相」，加一个数据并行的执行模型。三个子项目各自两件套，本文只做路由。

## 一、这个目录是什么

| 子项目 | 回答什么 | 一句话 |
|---|---|---|
| `langs/cpp-basics/` | 对象模型、RAII、移动语义、模板、并发、UB | 编译期决定的东西（布局、vtable、内联）与运行期决定的东西（生命周期、异常、内存序）怎么分工 |
| `langs/python-basics/` | 数据模型、迭代协议、GIL、asyncio、GC | 一门"一切皆对象"的语言，为什么在 CPU 密集、并发、内存三处各有各的瓶颈 |
| `langs/cuda/` | SIMT 与延迟隐藏、内存层次与 bank conflict、占用率、归约/扫描/矩阵乘 tiling、Nsight 归因 | 一个 kernel 从朴素到分块的优化链路，每一步都要有指标支撑 |

**一句话定位**：这三份都在回答同一个问题的不同侧面——**「这段代码为什么慢/为什么错」**。C++ 的答案是"你踩了 UB 或对象生命周期"，Python 的答案是"GIL/引用计数/解释执行"，CUDA 的答案是"占用率与访存模式"。它们共同点在于：**只靠写代码和跑工具就能验证**，不需要额外的硬件、内核或分布式环境。

**入口（本文的读法）**：在 langs 项目只用源码、objdump、dis、strace、Nsight 可重放指标、不引入额外硬件、内核模块、分布式集群的约束下，解决 C++ 对象布局、vtable、RAII 析构顺序、移动构造、模板实例化符号、std::atomic 内存序、UB 指令、Python PyObject、tp_iter、tp_iternext、GIL、PyThreadState、asyncio 任务状态、PyGC_Head、CUDA SIMT warp、__shared__、bank conflict、occupancy、归约、扫描、矩阵乘 tiling、Nsight 指标为什么慢、为什么错。

**不换的是什么**：全程不变的是同一输入下可由 `objdump` 指令流、`dis` 字节码、`strace` 的 `futex`/`ioctl`、`asyncio.Task.__step` 状态、`cudaOccupancyMaxActiveBlocksPerMultiprocessor` 计数和 Nsight 访存指标重放的观测序列，所以看到差异先问是 ABI/对象头/内存序/事件循环/launch config 中哪一项变了。

**积木**：① C++ Itanium ABI 的 vtable 指针与 `.eh_frame` 展开表；它能独立验证 `objdump` 中虚调用加载 `%rax` 指向 vtable 项、异常展开按 `.eh_frame` FDE 调用析构；② CPython `PyObject` 的 `ob_refcnt`/`ob_type` 与 `tp_iter`/`tp_iternext` 槽位；它能独立验证 `dis` 中 `GET_ITER`/`FOR_ITER` 调用槽位、引用计数在 `Py_INCREF`/`Py_DECREF` 处变化；③ CUDA SM 的 warp 锁步与 `__shared__` 32 bank 地址映射；它能独立验证 `Nsight` 的 `l1tex__data_bank_conflicts` 和 PTX `bar.sync`/`__syncthreads` 指令。

**最小情形**：单核单线程执行一次 `std::vector` 构造析构、一次 `dis` 的 `FOR_ITER`、一次 CUDA 单线程写读 `__shared__`；此时 `std::atomic` 的 `LOCK` 指令、`PyThreadState` 切换、`asyncio` 任务队列、多 warp 的 `bar.sync` 与 `l1tex__data_bank_conflicts` 都不参与。

**生成**：累加多个 `std::unique_ptr` 析构、多个 `PyObject` 引用、多个 CUDA lane 访问同一 `__shared__` 数组；覆盖 `.eh_frame` FDE、`tp_dealloc`、`asyncio.Task.__step`、`cudaOccupancyMaxActiveBlocksPerMultiprocessor`、`l1tex__data_bank_conflicts`；最坏情形 `std::atomic` 内存序错用导致 `LOCK`/`MFENCE` 缺失、`Py_DECREF` 提前归零触发 `tp_free`、32 个 lane 命中同一 bank 导致 `l1tex` 冲突计数上升。

**两边**：同一份 C++ 对象状态由编译器持有为 `.eh_frame`、`.data.rel.ro` vtable 与 `this` 寄存器约定，由运行期持有为栈帧 `%rsp`/`%rbp` 和 `call` 目标；同一份 Python 对象状态由解释器持有为 `PyObject` 的 `ob_refcnt`/`ob_type`/`tp_iternext`，由字节码持有为 `dis` 中 `GET_ITER`/`FOR_ITER` 的操作数栈；同一份 CUDA 数据状态由源码持有为 `__shared__` 下标，由 SM 持有为 `l1tex` bank 事务与 `bar.sync` 屏障。

## 二、为什么这样分组（功能设计）

**取舍一：语言与 GPU 放一起，而不是把 CUDA 塞进并行计算。** 表面上看 CUDA 更像"并行/性能"话题，但它在面试里的问法与 `cs149` 那类课程完全不同：`cs149` 问的是"加速比从哪来、访存层次怎么影响 roofline"，而 CUDA 岗位问的是"你这个 kernel 为什么 30% 占用率""共享内存 bank conflict 怎么消""为什么加了 `__syncthreads()` 反而更慢"。**后者是写代码的人直接踩的坑，与 C++ 的 UB、Python 的 GIL 是同一类问题**：语言/执行模型的约束如何变成性能与正确性。

**取舍二：不把 `cpu/` 拉进来。** 虽然 CUDA 与"体系结构"天然相邻，但 `cpu/` 的核心判据是 RTL、difftest、STA，与这里的"写代码 + 跑 profiler"完全不同。两者的连接点只有一处——GPU 的内存层次与 CPU 的 cache 层次是同一套"局部性"逻辑，各讲一次即可，不重复。

**取舍三：三份而不是一份。** 判据不同：C++ 要能指出 UB 并用工具证实（ASan/valgrind/反汇编），Python 要能用运行时解释行为（`dis`、引用计数、事件循环），CUDA 要能用 profiler 指标归因（占用率、bank conflict、访存效率）。混在一份里会退化成"语言特性列表"。

**分组只做路由**：三个子项目仍各自五段。

## 三、推荐顺序与判据

按面试权重排序，**不按语言难度**。

| 阶段 | 内容 | 判据 | 成本 |
|---|---|---|---|
| 1（必做） | `cpp-basics/`：对象模型（vtable、布局）、拷贝/移动、RAII、智能指针 | 能对着 `objdump`/`-fdump-lang-class` 说清一个类的布局与虚调用路径；能指出一段代码的 UB 并用 ASan 复现 | 中 |
| 2（必做） | `cpp-basics/`：并发与内存序 | 能说清 `memory_order_relaxed/acquire/release` 各自阻止了什么重排，并能举一个只在弱序机器上错的例子 | 中 |
| 3（建议） | `python-basics/`：数据模型、可变性陷阱、迭代/生成器 | 能解释"为什么默认参数是可变对象会出 bug"、"生成器为什么省内存" | 小 |
| 4（建议） | `python-basics/`：GIL、asyncio、GC | 能判"这段 I/O 密集该用线程还是协程"、"循环引用为什么需要分代回收" | 小 |
| 5（看条件） | `cuda/`：SIMT 模型、内存层次、占用率 | **没有 GPU 也能讲模型**：能说出为什么分支发散、bank conflict、未合并访存分别损失什么 | 中 |
| 6（加分） | `cuda/`：归约/扫描/矩阵乘 tiling、Nsight 归因 | 有卡时：能给出一个 kernel 的 profiler 关键指标与改进前后的对比 | 大 |

**一条硬判据**：三份文档的结论都必须能落到**工具输出**上——C++ 对 ASan/objdump，Python 对 `dis`/`sys.getrefcount`/事件循环日志，CUDA 对 `ncu` 的核心指标。落不上去的，是语言教程而不是能力。

## 四、不做什么 · 必要性 · 失效点

### 必要性：删掉会怎样

| 机制 | 删掉会怎样 | 判定 |
|---|---|---|
| `RAII` | 删掉 `RAII` 后，“生命周期怎么分工”承诺破；异常展开时 `std::vector`/`std::unique_ptr` 析构不执行，堆内存与文件描述符泄漏。 | 必需 |
| `GIL` | 删掉 `GIL` 后，“CPU 密集线程串行”承诺破；多线程同时执行 `Py_INCREF`/`Py_DECREF`，`PyObject` 引用计数可能提前归零并触发 `tp_free`。 | 必需 |
| `bank conflict` | 删掉 `bank conflict` 后，“访存模式决定延迟隐藏”承诺破；warp 内多个 lane 访问同一 32-bit bank 的 `__shared__` 数组时，`l1tex` 冲突计数上升但无法归因。 | 选择 |
| `Nsight` | 删掉 `Nsight` 后，“每一步都要有指标支撑”承诺破；无法采集 `occupancy`、`memory throughput`、`shared memory bank conflicts`，tiling 只能靠代码猜测。 | 必需 |
| `RTL` / `difftest` / `STA` | 删掉“不把 `cpu/` 拉进来”的边界后，`分组只做路由` 承诺破；`langs` 判据会从 `ASan`/`dis`/`Nsight` 扩到波形、指令级差分、时序报告，但三份语言/GPU 结论不破。 | 选择 |

### 失效点：哪条前提一破，结论就变

- Python 3.13 free-threaded build 移除 `GIL` → “GIL 导致 CPU 密集线程串行”结论变；瓶颈转为 `PyObject` 引用计数原子操作、`pymalloc` 分配器锁和 `tp_dealloc` 竞争。
- CUDA warp 内分支使 `__syncthreads()` 只在部分 lane 执行 → “加同步能修复共享内存可见性”结论变；行为变成未定义/死锁，`Nsight` 的 bank conflict 指标不再解释主要停顿。
- `taskset -c 0` 把进程绑定到单核 → “多 `std::thread`/`asyncio` 并发收益来自核数”结论变；`epoll_wait`、`GIL` 切换和 `pthread_cond_wait` 的调度开销成为主因。
- Nsight Compute 缺少 `--metrics` 权限或 GPU 被 `CUDA_VISIBLE_DEVICES` 外进程独占 → “占用率、bank conflict、访存效率可归因”结论变；只能回退 `cudaEventElapsedTime`、`cudaDeviceGetAttribute` 和 `sm__warps_active.avg.pct_of_peak_sustained_active` 估算。
- C++ 编译单元使用 `-fno-exceptions` 或 `noexcept` 路径 → “RAII 在异常展开中兜底”结论变；资源释放只依赖正常析构、显式 `close()`/`munmap()` 或 `std::optional::reset()`。

### 不做什么（范围）

**不做语言教程。** 语法、标准库 API 大全、第三方生态（Django/Flask/Numpy 用法）一律不涉及；只写"编译器/运行时替你做了什么，以及它在哪里露馅"。

**不做框架与库的调优。** cuBLAS/cuDNN/Thrust 的用法不展开；CUDA 的优化链路只到"自己写 kernel 并归因"。

**不做绑定层工程。** pybind11/ctypes/Cython 只到"GIL 与边界开销"的判断，不做完整工程实践。

**不做编译器的实现。** 模板实例化、内联、代码生成的内幕在 `cpu/compiler/`；这里只到"生成出来的代码/布局长什么样"。

**不做多机与分布式。** 那是 `6824/` 与 `eng/system-design/` 的地盘。

## 五、面试怎么讲

**30 秒版本**（开场直接说，120–170 字）

> 这三块我按"运行时真相"来准备：C++ 我能说清一个类的布局与虚调用路径、移动语义在什么情况下不生效、以及一段代码的 UB 用哪个工具能证实；Python 我能解释可变性陷阱、GIL 存在时线程/协程/多进程各自适合什么负载、循环引用为什么要分代回收；CUDA 我能说清一个 kernel 的性能瓶颈在占用率、访存合并还是同步，并给出对应的 profiler 指标。共同点是：每条结论都能落到工具输出上。

**可能被追问的 7 个点**

1. **「虚函数调用为什么慢，虚表指针存在哪？」** → 考点：对象布局与间接跳转。
   → 答法：每个多态对象头部有 vptr，指向该类的 vtable；调用是"取 vptr → 按索引取函数指针 → 间接跳转"，代价是**无法内联**与一次间接跳转（可能预测失败）。判据：`objdump -d` 看 `call *(%rax)`；`clang -fdump-lang-class` 看布局。边界：单继承虚调用索引固定，多继承与虚继承要 thunk，成本更高。

2. **「`std::move` 到底做了什么？」** → 考点：它只是类型转换。
   → 答法：`std::move` 只是把左值转成右值引用，**不移动任何东西**；真正的移动发生在被选中的移动构造/赋值里。所以"move 了但还是拷贝"的典型原因是：类型没有移动构造、或者移动构造不是 `noexcept` 而容器要求强异常保证、或者对象是 `const`。判据：在移动构造里打日志，或看 `-fno-elide-constructors`。

3. **「UB 为什么危险，举一个优化放大 UB 的例子？」** → 考点：编译器假设与真实行为。
   → 答法：编译器按"无 UB"做假设，于是有符号溢出会被当成不会发生、空指针解引用后的分支会被删掉、严格别名会重排访存。典型例子：`if (p) ...` 之后对 `p` 的解引用被提前，因为"解引用过就说明非空"。判据：`-fsanitize=undefined,address` 复现，`-O0` 与 `-O2` 对比。边界：`-fwrapv`/`-fno-strict-aliasing` 能规避一部分，但那是改语义，不是修 bug。

4. **「GIL 存在，多线程还有意义吗？」** → 考点：GIL 保护的是什么、不保护什么。
   → 答法：GIL 让**同一时刻只有一个线程执行 Python 字节码**，所以纯 CPU 密集的 Python 代码多线程没有加速；但 I/O 等待、`numpy` 之类的 C 扩展（会释放 GIL）、以及 `time.sleep` 这类阻塞调用期间 GIL 是释放的，所以 I/O 密集场景仍然有效。判据：`threading` 与 `multiprocessing` 跑同一段 CPU 密集代码对比耗时。边界：不同解释器实现（如 free-threading 的构建）行为不同，按版本来。

5. **「asyncio 比线程快在哪？」** → 考点：切换成本与调度语义。
   → 答法：不是"更快"，是**单线程内切换更便宜、且没有锁的竞争**；协程切换在用户态完成，不需要陷入内核。代价是**一个阻塞调用就会卡住整个事件循环**，且 CPU 密集任务必须交给进程池。判据：`asyncio` 里混入 `time.sleep` 会让所有任务停摆——这个实验最能说明问题。

6. **「CUDA 里为什么共享内存能加速，代价是什么？」** → 考点：显存层次与 bank。
   → 答法：共享内存是片上、延迟远低于全局内存，但容量小（按架构数十 KB 量级）、且按 bank 组织，**同一 warp 内访问同一 bank 的不同地址会串行化**（bank conflict）；此外还要自己处理同步（`__syncthreads()`）与边界。判据：`ncu` 里的 shared load/store 效率与 bank conflict 计数。边界：不同架构的 bank 宽度与数量不同，按实现而定。

7. **「占用率越高越好吗？」** → 考点：占用率与延迟隐藏的关系。
   → 答法：占用率是"活跃 warp 数 / 上限"，它提供的是**用并行掩盖延迟的能力**；当 kernel 本身访存密集、延迟长时，高占用率有用；当寄存器用量大、算术密集且指令级并行足够时，低占用率也能跑满。判据：`ncu` 的 achieved occupancy 与 stall reason 分布——**要看 stall 原因，而不是只看占用率数字**。

**别说什么**

- **「我精通 C++/Python。」** 这句话之后必然被问细节；改成"这条链我能讲到工具输出"。
- **「Python 慢是因为解释执行。」** 太粗：要分是解释开销、动态类型分派、GIL 争用还是内存分配。
- **「CUDA 就是多线程。」** 混淆 SIMT 与多核线程；warp 内是锁步执行、分支会串行化，这是最本质的差别。
- **报没测过的加速比。** 没有基线（同一张卡、同一 shape、同一编译选项）就不要说"提升 X 倍"。
