## 一、它解决什么问题

这项能力解决的是**「代码生成这一层出了事，你能不能定位到具体是哪一步、并且用别人能复现的方式说清楚」**。它拦住的不是「不会写编译器」，而是三类具体事故：

**事故一：优化收益无法归因。** 有人提 PR 说「加一个循环相关的 pass，热点函数快 15%」。评审时问：基线是什么？噪声多大？改的是动态指令数、IPC 还是 cache miss？`llvm-mca` 的建模和真机差多少？答不上来。结果是合入后线上没变化，或者只在某个 microbench 上有效。这类 PR 的返工成本通常是几天到两周，因为要重建测量环境。

**事故二：-O2 才崩，-O0 正常。** 一个跨模块调用在开了优化后返回值错乱，堆栈看起来「被踩了」。此时需要的能力是：用 `opt -opt-bisect-limit=N` 在优化管线里二分出是哪一次变换引入的，用 `opt -print-after=<pass> -print-changed` 看 IR 前后差异，再判断这是 pass 的 bug 还是源码 UB（严格别名、有符号溢出、越界）被优化放大。没有这套手段，团队只能靠「关掉某个 pass」上线，把问题埋着。

**事故三：跨语言 / 跨编译器边界。** C 侧按 SysV AMD64 传一个 24 字节结构体，Rust 侧按值接收，链接不报错、运行崩。这要求能读 IR 里的 `sret` / `byval` 属性、能读反汇编里 `sub rsp, N` 的栈帧、能说清「大于 16 字节的聚合体走内存返回」这条规则。

对应到面试，它拦的是这几类题：「SSA 是什么，phi 干什么用」「mem2reg 之后 alloca 去哪了」「寄存器不够时怎么办」「内联是不是越多越好」「这段代码为什么 -O2 和 -O0 结果不一样」。这些题的共同点是：**背名词能过一半，讲不清判据就露馅**。

**入口（本文的读法）**：在源码语义、`target triple`、SysV AMD64 调用约定、`opt`/`llc`/`llvm-mca`/`perf` 接口不变的前提下，把「代码生成层出了事」换成可复现定位：优化收益归因、只有 `-O2` 才崩、C/Rust ABI 边界、SSA/phi/mem2reg/寄存器溢出/内联，都要落到 `opt -print-after=<pass>`、`-opt-bisect-limit`、IR 属性（sret/byval/nonnull/align）或反汇编上。换的是 pass 与后端，不换的是「先定位到 pass，再定位到指令」这条顺序。

**不换的是什么**：全程不变的是 C/Rust 源码语义与 UB 规则、`target triple` 与 SysV AMD64 调用约定（`sret`、`byval`、`rsp`、`rdi/rsi/rdx/rcx/r8/r9`）、以及同一 `opt`/`llc`/`llvm-mca`/`perf` 可观测管线；所以看到 `-O0` 与 `-O2`、C 与 Rust、PR 与基线差异，先问 pass 顺序、优化级别、寄存器分配结果、结构体返回路径、cache/TLB 条件是否一致，而不是先问“是不是优化器坏了”。

**积木**：① SysV AMD64 调用约定规定整数参数依次进入 rdi/rsi/rdx/rcx/r8/r9、返回值进入 rax、rsp 在 call 前 16 字节对齐；它能独立验证 24 字节结构体跨 C/Rust 边界是否落到 sret/byval 与 sub rsp, N。② LLVM IR SSA 规定每个值单一定义、控制流汇合点用 phi 节点携带前驱边输入；它能独立验证 mem2reg 后 alloca/load/store 是否被 phi 与寄存器值替代。③ x86-64 指令语义规定 cmp/test 写入 ZF/SF/OF/CF、jne/je 读取条件标志、add/sub 可置 OF，且 C 语言把有符号溢出和越界访问定义为 UB；它能独立验证 -O0 与 -O2 反汇编里分支翻转是否来自同一 cmp 指令和标志寄存器。

**最小情形**：单线程执行一个 C 函数调用，target triple x86_64-unknown-linux-gnu，-O0，一条 call 指令从 caller 进入 callee，参数只走 rdi，返回值走 rax，栈帧只有 push rbp、mov rbp,rsp、sub rsp,N、leave、ret；它能独立验证 ABI 寄存器与 rsp 偏移，此时多核 cache/TLB、内联跨模块、寄存器分配溢出、循环优化、跨语言链接都不起作用，因为只有一个函数、一个线程、一次 call 指令、没有 pass 改写 IR。

**生成**：累加 opt 管线中 mem2reg/GVN/内联/寄存器分配多个 pass 对同一 IR 的改写，新增约束是 -opt-bisect-limit=N 必须能停在首个改变 alloca/phi 或 call 属性的 pass；覆盖 target triple、SysV AMD64 调用约定、C/Rust 链接符号与 IR 属性 sret/byval/nonnull/align，新增约束是 caller/callee 对 rdi/rsi/rdx/rcx/r8/r9、rax、rsp 偏移、结构体返回隐藏指针必须一致；最坏情形是寄存器不够触发 spill/reload 到 rsp 栈帧、内联放大 UB 使 -O0 正常 -O2 崩溃，新增约束是必须用 opt -print-after=<pass>、llc 反汇编、perf stat 的 cycles/instructions 或 llvm-mca 的 uops/cycle 定位到具体指令或 IR 属性。

**两边**：同一份调用现场在 LLVM IR 里是 call 指令、参数类型、sret/byval/align 属性与 alloca/load/store，在 x86-64 机器码里是 rdi/rsi/rdx/rcx/r8/r9、rax、sub rsp, N、mov [rsp+K]；LLVM pass 持有 IR 与 -opt-bisect-limit 停止点，CPU 与内核持有寄存器文件、rsp 指向的栈页、trapframe 中的 rip/rsp。

## 二、为什么这样做（方法论设计）

**有口径才算数 vs 看起来专业但无法证伪。**

算数的口径必须满足三条：可复现（同样的输入、同样的编译选项、同样的 target triple）、有对照（改动前后各跑一次，而不是和历史印象比）、有量纲（说「动态指令数从 A 降到 B」而不是「变快了」）。具体来说：pass 是否真的触发，看 `opt -stats` 的计数；IR 层面的变换看 `-print-changed` 的 diff；运行时看 `perf stat` 的 instructions / cycles / branch-misses；代码生成质量看 spill/reload 数量与栈帧大小（从 `llc -stats` 或反汇编的函数序言读，具体计数项名字按版本而定）。

无法证伪的说法有共同句式：「用了 SSA 所以更快」「走了 GVN 所以消除了冗余」「寄存器分配用图着色」。它们的问题是**没有失败条件**——你无法设想一个观测结果会推翻它。工程文档里出现这类句子，等价于没写。

**指标怎么定。** 分四层，不要混用：正确性（`llvm-lit` + `FileCheck` 的用例通过率、`opt -verify-each` 不报错）；变换效果（IR 指令数、pass 触发次数）；运行时（动态指令数、IPC、分支预测失败率）；成本（编译时间、目标文件体积、峰值内存）。一层指标好不代表另一层好——IR 指令数降了 20% 而动态指令数不变，通常说明降的是不热的那条路径。

**边界怎么划。** 单个 pass 的局部改动是可以证伪的最小单元；整条 `-O2` 管线的调优很难归因，因为 pass 之间存在顺序耦合——前一个 pass 的输出是后一个的输入，canonicalize 形式变了，后面的匹配规则就失效。所以方法论上要求：**改管线必须能指出「我依赖前序哪个 pass 的哪种输出形式」**，否则改动是脆弱的。跨 target 的结论不通用，x86-64 上的 spill 结论不能直接搬到 AArch64。

**这套方法什么时候失效。** 输入分布不匹配真实负载时，microbench 的收益不迁移；测量噪声大于效应量时（小函数上的个位数百分比基本不可信）；开了 PGO/LTO 后，函数边界和调用图都变了，模块级结论失效；`-O3` 相对 `-O2` 不一定更快，因为代码体积增大导致 icache 压力上升，这个方向性结论依赖具体负载。

**常见错误做法及其代价。** ① 直接跳到 `-O3` 当优化手段：编译时间和目标文件体积显著上升，热点以外的代码膨胀，可能整体变慢，而且掩盖了真正该改的算法问题。② 在 IR 层写业务逻辑：IR 的 API 与类型系统随版本演进（例如指针类型从不透明化到 `ptr` 的迁移），一次升级就要重写，维护成本远超收益。③ 手写汇编做微优化：可维护性归零，破坏 debug info 与 sanitizer 插桩，且把 target 绑死。④ 把「指令数更少」当作唯一判据：memory-bound 的循环里减少指令数几乎不影响耗时，真正该看的是访存模式和 cache 行为。⑤ 没有 `-verify-each` 就提交 pass 改动：错误 IR 会以「下游 pass 崩溃」的形式暴露，排查成本翻倍。

## 三、章节大纲

**1. 编译器在工具链里的位置：前端 / 中端 / 后端的职责分界**
讲 `.c → .i → .ll → .s → .o → 可执行` 每一跳由谁负责，`clang -emit-llvm -S`、`llc`、`llvm-link`、`llvm-as/dis` 各自在哪一步；前端保证语言语义、中端保证与 target 无关的等价变换、后端保证 target 约束（寄存器、指令合法性、ABI）。学完能答：「为什么要分三段，中端不做 target 相关的优化是出于什么考虑」。

**2. LLVM 的三件套：IR、Pass、Target 各自管什么**
讲三者的契约：IR 是数据模型与不变量（SSA、类型、`Value`/`User` 继承体系），Pass 是在不变量之上的变换与分析的集合，Target 通过 `TargetMachine` + TableGen 描述提供指令、寄存器、调度模型。学完能答：「LLVM 的可复用性到底来自哪里，为什么换个 target 不用重写优化」。

**3. LLVM IR 精读：模块、函数、基本块、SSA、phi 与类型系统**
讲 `Module → Function → BasicBlock → Instruction` 的层级；SSA 的定义-使用约束与支配关系；phi 在合流块按前驱选值；`i32`/`ptr`/`<4 x i32>`/`StructType` 与不透明指针；`getelementptr` 为什么不表示访存。学完能答：「为什么要 phi，不用 phi 怎么做同样的表达」「`getelementptr` 和 `load` 的区别」。

**4. 写第一个 Pass：Analysis 与 Transform 的区别、PassManager 的组织**
讲 `PassInfoMixin::run(Function&, FunctionAnalysisManager&)`；Analysis 只读、结果被缓存、需要 `PreservedAnalyses` 显式声明保留；Transform 必须声明未保留则后续分析重算；`ModulePassManager` / `FunctionPassManager` / `LoopPassManager` 的嵌套与 adaptor；`PassBuilder` 注册使 `opt -passes=` 可见。学完能答：「新 PassManager 相比 legacy 好在哪，`PreservedAnalyses::none()` 写错的后果是什么」。

**5. 从源码到 IR：Clang 的 AST 与 CodeGen 如何分工**
讲 `Sema` 做语义检查、`ASTContext` 持有 AST、`CodeGenModule`/`CodeGenFunction` 负责下降；`-Xclang -ast-dump` 看树；`-emit-llvm -O0` 看未优化的 alloca 风格 IR，与 `mem2reg` 之后的 SSA 形式对照。学完能答：「为什么 -O0 的 IR 全是 alloca，不直接生成 SSA」。

**6. 优化管线：内联、GVN、LICM、循环优化、向量化各自的适用条件**
讲每个变换的前置条件与代价：内联受 `InlineCost` 与阈值控制（阈值按 target 与版本而定），受递归与间接调用限制；GVN 依赖支配关系与冗余消除，需要 AA（别名分析）判定等价；LICM 要求被提升的计算无副作用且循环内必执行；循环优化依赖 `ScalarEvolution` 求行程数、依赖分析判可变换性；向量化依赖无跨迭代依赖、对齐与 trip count 可判。学完能答：「为什么这个循环没被向量化」「内联的收益和代价分别是什么」。

**7. 后端：SelectionDAG 与 GlobalISel、指令选择、寄存器分配、指令调度**
讲两种指令选择路径的分工与现状（GlobalISel 覆盖面按版本与 target 而定）；`llc -stop-after=` / `-stop-before=` 逐阶段看 MIR；寄存器分配以 greedy 为默认，另有 basic/fast 等可选（可用项按版本而定），核心是活跃区间干涉；指令调度分前 RA 与后 RA。学完能答：「寄存器不够时为什么 spill，spill 的代价是什么」「SelectionDAG 的 DAG 阶段解决了什么问题」。

**8. 目标描述与 ABI：调用约定、栈帧布局、重定位**
讲 TableGen 的 `.td` 描述指令与寄存器；SysV AMD64 的整数参数寄存器序列 `rdi/rsi/rdx/rcx/r8/r9`、浮点 `xmm0–7`、返回值 `rax:rdx` / `xmm0:xmm1`、调用点 16 字节栈对齐、`sret`/`byval`/`zeroext` 属性；重定位类型（如 `R_X86_64_PC32`、`R_X86_64_PLT32`）与 `-fPIC` 下的 GOT/PLT。学完能答：「大结构体返回发生了什么」「PIC 下调用外部函数为什么要经过 PLT」。

**9. 可观测性：debug info、sanitizer 插桩、opt 的调试开关**
讲 `-g` 产生的 `DICompileUnit` 与 `llvm.dbg.value` 内联函数、`llvm-dwarfdump` 读 `.debug_info`/`.debug_line`；ASan/UBSan/TSan 是插桩 pass 而非运行时魔法，`-fsanitize=` 与 `-fsanitize-recover` 的差别；`opt -print-after=`、`-print-changed`、`-debug-pass-manager`、`-opt-bisect-limit`、`-verify-each` 的用途与前提（部分 debug 开关只在带断言的构建里生效）。学完能答：「-O2 下断点打不准是为什么」「怎么二分出是哪个 pass 引入的问题」。

**10. 什么时候不该用 LLVM：教学编译器、JIT、DSL 的取舍**
讲引入 LLVM 的成本：构建体积、编译时间、API 演进、链接依赖；DSL 用 tree-walking 解释器或轻量后端更快落地；JIT 场景走 ORC 的 `LLJIT` 而非自己拼 MC；教学场景用 LLVM 会跳过语义与类型检查的理解。学完能答：「什么情况下不该上 LLVM，判据是什么」。

**11. 面向计算与域特定语言的编译：GPU 后端、Triton、TVM、XLA 与 dialect 分层**
讲「算法」与「调度」为什么要拆开：手写 CUDA 把线程映射、共享内存、流水线全钉死在代码里，换硬件或换形状就得重写；DSL 编译器把这几件事交给编译器或搜索。分层是四段——图/算子层（XLA 的 HLO、TVM 的 Relay/Relax）→ tile/循环层（TVM 的 TIR 与 schedule 原语、Halide 的 algorithm/schedule 分离、MLIR 的 `linalg`/`affine`）→ 线程与显存层（Triton 的 block 模型、MLIR 的 `gpu` dialect、NVVM/ROCDL）→ 机器码（PTX/SASS）。核心变换只有三类半：**融合**（少起 kernel、少访存）、**tiling 与布局**（切块、合并访存、共享内存与 bank）、**流水线化**（多级 staging 隐藏延迟），外加自动调优（搜索 + cost model）。学完能答：「Triton 替你决定了什么、代价是什么」「TVM 的 schedule 原语和 LLVM 的 pass 差在哪一层」「为什么 XLA 能做整图融合而 LLVM 做不了」。

## 四、不做什么 · 必要性 · 失效点

### 必要性：删掉会怎样

| 机制 | 删掉会怎样 | 判定 |
|---|---|---|
| `opt -opt-bisect-limit=N` | 承诺破：`-O2` 才崩时无法二分出首个错误 pass，只能整条管线关 pass 上线 | 必需 |
| `opt -print-after=<pass> -print-changed` | 错误发生：GVN / mem2reg 是否改变 `alloca` / `phi` 无法被 IR diff 证伪，评审只剩口头声称 | 必需 |
| `sret` / `byval` | 错误发生：24 字节结构体跨 C / Rust 边界时隐藏指针与 `sub rsp, N` 栈帧不可判定，链接通过但运行崩 | 必需 |
| `llvm-lit` + `FileCheck` | 承诺破：`ptr` 迁移或 canonicalize 改变 IR 形态后，pass 触发与期望 `phi` / `alloca` 无断言，错误静默进入下游 | 必需 |
| `opt -verify-each` | 错误发生：非法 SSA / `phi` 或越界 `alloca` 要等 `llc` 崩溃才暴露，排查从 pass diff 变成后端堆栈 | 必需 |
| `llvm-mca` | 承诺破：无法在真机前比较 uops / cycle 建模与 `perf stat` 的 cycles / instructions 偏差，但可用 `perf stat` 替代 | 选择 |

### 失效点：哪条前提一破，结论就变

- SysV AMD64 ABI 对大于 16 字节聚合体使用隐藏指针 / `sret` 返回的前提 → 换成 Windows x64 或 AArch64 后，返回值寄存器与栈参数规则改变，C 侧 24 字节结构体与 Rust 侧按值接收不再等价。
- `perf stat` 的 cycles / instructions 来自同一稳定时钟源（绑核、无 DVFS / SMI）的前提 → 若时钟源漂移或 `taskset` 丢失，IPC 与 15% 加速比被噪声淹没，pass 收益不可复现。
- 单核或固定核数下 L1 / L2 cache 争用可忽略的前提 → 若超线程或多核共享 cache，branch-misses 和 cycles 波动大于 IR 指令数下降，microbench 收益不迁移。
- 源码满足 C 严格别名、无有符号溢出、无越界的前提 → 若 UB 存在，`-O0` 正常而 `-O2` 错值，`opt -print-changed` 会显示 GVN / 循环变换放大错误，归因从 pass bug 变成源码契约破。
- PGO / LTO 关闭或 profile 与二进制同版本的前提 → 若开启 PGO / LTO 后函数边界和调用图变化，模块级 spill / reload 与 inline 结论失效。

### 不做什么（范围）

- **不做 408 / 编译原理课的考点覆盖**：正则到 NFA/DFA、LL/LR 分析表构造、语法制导翻译，属于另一层，这里不重讲。
- **不做语言语法与语义**：C/C++/Rust 的具体语法、模板、所有权规则不在此文档范围。
- **不做完整 target 移植 walkthrough**：不逐步教如何为全新 ISA 写 `.td`、接 `TargetLowering`。
- **不做 MLIR 全栈教程、不写 GCC 内部**：第 11 章只讲 dialect 分层**在哪一层解决什么问题**、以及 Triton/TVM/XLA 的选型判据；不教怎么写一个 dialect，不展开 `linalg` 的完整变换集。GCC 内部结构完全不涉及。
- **不做 GPU kernel 的手写调优**：线程映射、bank conflict、访存合并、Nsight 归因属于 `langs/cuda/`；这里只从编译器角度讲「高层表示怎么降到 GPU」，不教怎么写最快的 kernel。
- **不做自动调优的搜索算法细节**：AutoTVM/Ansor 一类只讲「搜什么、代价模型估什么、为什么要付这个时间」，不推导具体搜索策略。
- **不写 JIT 运行时与 GC 设计**：只到「用 ORC 还是自己拼 MC」的选型为止。
- **不给版本相关参数打保票**：pass 名、`-stats` 计数项名、默认寄存器分配器、GlobalISel 覆盖度都写「按版本而定」，不编造具体数值。
- **不做通用性能调优方法论**：那是 profiling 层的内容，这里只谈「编译产物怎么变、怎么观测」。

## 五、面试怎么讲

**30 秒版本（约 150 字）**

> 我的口径是「能读、能改、能证」。能读：给我一段 `-O2` 的 IR，我能说出哪个基本块是循环、phi 在哪合流、`sret` 说明什么调用约定。能改：我写过 Analysis 和 Transform 两类 pass，知道 `PreservedAnalyses` 写错的后果。能证：我会用 `opt -print-changed` 看变换、用 `-stats` 看是否触发、用 `-opt-bisect-limit` 二分归因、用 `llvm-lit` + `FileCheck` 锁行为。具体到某个 pass 的收益数字，我按实测口径给，没测过就说没测过。

**可能被追问的 8–10 个点**

1. **「SSA 是什么，phi 干什么用？」** 考点：数据模型是否真懂。答：每个值只有一个定义点，使用必须被定义支配；合流块里同一变量有多个来源时用 phi 按前驱选值。`mem2reg` 把 `alloca` 提升成 SSA 值，在合流处插 phi，必要时 split 临界边。退化情形：`alloca` 地址逃逸或被 `volatile` 修饰时无法提升，`-passes=mem2reg` 后仍会留着。

2. **「Analysis 和 Transform 区别，PassManager 怎么组织？」** 考点：是否真写过。答：Analysis 只读、结果进 `AnalysisManager` 缓存、由 `PreservedAnalyses` 决定是否失效；Transform 若返回 `none()` 则下游分析全部重算。新 PM 是嵌套的：`ModulePassManager` 里挂 `FunctionPassManager`，循环层用 `LoopPassManager` + adaptor；用 `PassBuilder` 注册才能在 `opt -passes=` 里调到。

3. **「写 pass 怎么保证不 break IR？」** 考点：工程纪律。答：三道闸——开发时 `opt -verify-each`，用例用 `llvm-lit` + `FileCheck` 锁住 IR 形态，InstCombine 这类等价变换可用 Alive2 做形式化验证。不写闸的代价是错误 IR 在下游 pass 崩溃，排查成本翻倍。

4. **「内联一定好吗？」** 考点：是否有代价意识。答：不。收益是消去调用开销、把调用方上下文暴露给后续优化；代价是代码体积、icache 压力、编译时间、可能抬高 register pressure。是否内联由 `InlineCost` 与阈值决定（阈值按 target 与版本而定），递归和间接调用通常不内联。可以看 `-Rpass=inline` 的决策理由，也能用 `always_inline`/`noinline` 属性强制。

5. **「寄存器分配为什么 spill？」** 考点：是否理解约束。答：物理寄存器数量固定（x86-64 GPR 16 个，可用数还受 ABI 与保留寄存器限制），活跃区间相交就产生干涉，干涉图着色失败或线性扫描溢出时只能 spill。代价是每条 spill 多一次 store、每条 reload 多一次 load，栈帧变大。观测方式是 spill/reload 计数与反汇编里的帧大小，计数项名按版本而定。

6. **「这段代码 -O2 和 -O0 行为不同，怎么查？」** 考点：归因能力。答：先判是不是 UB——严格别名、有符号溢出、越界访问在优化后会被放大，用 `-fsanitize=undefined` 和 `-fno-strict-aliasing` 做对照。确认是编译器侧再用 `-opt-bisect-limit=N` 二分出具体 pass，用 `-print-after=<pass> -print-changed` 看 IR diff，用 `-debug-pass-manager` 看管线实际执行顺序。

7. **「ABI 层怎么排查跨语言调用崩溃？」** 考点：边界知识。答：先看 IR 的函数签名有没有 `sret`/`byval`/`zeroext`；SysV AMD64 整数参数走 `rdi/rsi/rdx/rcx/r8/r9`、浮点走 `xmm0–7`、返回值 `rax:rdx`、调用点栈 16 字节对齐、大于 16 字节的聚合体走内存返回；再看反汇编里序言的 `sub rsp, N` 与实参是否有 8 字节错位；重定位层面用 `llvm-readelf -r` 看是否该走 PLT 却写了直接引用。

8. **「什么时候不该用 LLVM？」** 考点：选型判断。答：DSL 或原型阶段，构建体积与编译时间不划算，tree-walking 解释器几天能落地；只需要表达式求值时不必上完整后端；JIT 场景优先 ORC 的 `LLJIT` 而不是自己拼 MC 层；教学场景用 LLVM 会跳过语义检查与类型系统的理解，属于绕路。

9. **「Triton 和直接写 CUDA 差在哪？」** 考点：是否知道 DSL 替你决定了什么。答：CUDA 里线程映射、共享内存分配、同步点、访存合并都是你自己写；Triton 用 **block 级编程模型**，你只描述「一个 tile 怎么算」，线程与 warp 的切分、共享内存的分配、合并访存的布局由编译器决定，`num_warps` 与 `num_stages` 是暴露给用户的少数旋钮（`num_stages` 对应软件流水线的级数）。代价是**失去细粒度控制**：极端 kernel（手写 tensor core 的 swizzle、非常规 shared memory 布局）仍然要回到 CUDA/CUTLASS。判据是对比基准——不是"能不能跑"，而是"相对 cuBLAS/cuDNN 达到多少比例"。

10. **「TVM 的 schedule 和 LLVM 的 pass 是同一种东西吗？」** 考点：分层意识。答：不是同一层。LLVM 的 pass 作用在**指令级 IR** 上，做的是常量折叠、GVN、指令选择、寄存器分配；TVM 的 schedule 作用在**张量计算的定义**上，决定循环怎么切、分块怎么绑到线程、哪一维向量化、哪个 buffer 放共享内存——它改变的是**并行与访存结构**，而不是机器指令。一句话：schedule 决定"算什么形状的并行"，pass 决定"用哪条指令把这步算出来"。

**别说什么**

- 「我实现了一个 LLVM 后端。」——除非真做过 target 移植，否则说明只做到哪一层（写 pass / 改 lowering / 只读 IR），被追问 `.td` 和 `TargetLowering` 就崩。
- 「-O3 一定比 -O2 快。」——方向性反例太多（代码膨胀、icache），说完这句后面所有性能讨论都不可信。
- 「LLVM 用图着色做寄存器分配。」——只报名词不报实现（greedy / basic / fast，可用项按版本而定），等于承认没看过 MIR。
- 「我优化了 30%。」——没有基线、没有指标名、没有噪声范围的百分比，是这套方法论里最先被扣分的句式。
