# compiler · 分章详细

## 第 1 章 编译器在工具链里的位置：前端 / 中端 / 后端的职责分界

**要解决的问题**：把“源码变机器码”拆成三段各自可替换的职责。分界划错了，语言语义的坑就会漏到优化器里，或者指望后端去补救前端本该做完的降级，结果是优化莫名其妙地失效、bug 定位不到层。

**机制**：三段之间只用 IR 做接口，谁也不看对方的内部表示。

- **前端**：词法、语法、语义分析产出 AST，再由 CodeGen 把 AST 降成 IR。它要负责所有与源语言绑定的工作，包括类型布局、名字查找、模板实例化、vtable 生成、异常展开表的构造，以及把语言层面的 UB 建模成 IR 里可推理的形式（`nsw`/`nuw`、`noalias`、`!range` 元数据等）。
- **中端**：只依赖 IR 的语义契约做与源语言无关的变换，包括内联、GVN、LICM、循环变换、向量化。它不知道 `std::vector` 是什么，只知道 `load`/`store`/`phi` 代表什么。
- **后端**：只依赖 `TargetMachine` 和调用约定，依次做指令选择、寄存器分配、指令调度，最后发射汇编或目标文件。

关键在于边界为什么画在 IR 而不是 AST 上：IR 是三地址码且满足 SSA，每条指令的效果都能局部推理，所以分析代价低。代价是信息单向流动：如果前端降级时丢掉了 `nsw` 或 `noalias`，中端就再也推不出来；反过来，后端也不能回头去“理解”源语言。

一条命令能看到三段：

```bash
clang -O0 -S -emit-llvm -o a.ll x.c   # 前端：源码 → IR
opt -passes='mem2reg,instcombine' -S a.ll -o b.ll  # 中端：IR → IR
llc -march=x86-64 b.ll -o b.s         # 后端：IR → 汇编
```

`clang -c` 相当于把这三段串起来跑完。`clang -cc1` 是前端驱动本身，`-emit-llvm` 走 BC、加 `-S` 出文本。

**最小例子**：`int add(int a, int b){ return a + b; }`

- 前端 `clang -O0 -S -emit-llvm` 出的是“没收拾过”的 IR：入口三条 `alloca` 加 `store`，再从栈槽 `load` 回来——因为 -O0 保留变量地址，便于调试。
- 中端跑 `opt -passes=mem2reg` 后，栈槽被删掉，函数体只剩 `%3 = add nsw i32 %0, %1` 和 `ret i32 %3`。这一步之所以能做，是因为前端把“参数按值传递”这条语义已经完整编码进了 IR。
- 后端 `llc -march=x86-64` 出汇编，形如 `leal (%rdi,%rsi), %eax; retq`——`%edi`/`%esi` 传参、`%eax` 返回，直接来自 x86-64 SysV 的调用约定，不是 IR 里写的。

**面试高频问法**：

1. 问：为什么不让优化器直接跑在 AST 上？→ 考点是 IR 的表达能力与分析成本。→ 答：AST 保留了语言结构但不利于数据流分析，IR 是 SSA 三地址码，def-use 链显式、每条指令效果局部可知，做支配树和活跃性分析都是多项式代价；代价是前端必须把语义降级干净，丢了信息中端补不回来。
2. 问：一个语言级别的优化（比如把 `for` 循环里的数组边界检查消掉）该放哪一段？→ 考点是职责边界。→ 答：如果靠源语言语义，就放前端，作为降级时插入 IR 的判断或者附加元数据；中端只做能由 IR 语义证明的消除。中端不认识数组和边界检查，它看到的是 `icmp` 加 `br`。
3. 问：后端能不能做常量折叠这类事？→ 考点是中端后端重叠。→ 答：能，而且会做，但后端做的是指令选择阶段的局部窥孔和折叠，受目标约束驱动；跨函数的、需要全局数据流的折叠属于中端。
4. 问：`-O2` 到底改了哪一段？→ 考点是管线认知。→ 答：主要改中端，`PassBuilder` 按优化级别拼出 pipeline；前端只被 `-O` 影响少量代码生成细节（如 `optnone` 属性、内联阈值提示），后端受影响的是调度与寄存器分配策略。

## 第 2 章 LLVM 的三件套：IR、Pass、Target 各自管什么

**要解决的问题**：LLVM 不是一个编译器而是一个库加一套约定，概念上只有三样东西在动：数据（IR）、变换（Pass）、目标知识（Target）。分不清“这件事该问谁”，就会在 Pass 里写死寄存器名，或者指望 IR 携带机器信息。

**机制**：

**IR 是数据**。所有权层级是 `LLVMContext` → `Module` → `Function` → `BasicBlock` → `Instruction`，全部继承自 `Value`，通过 `Use` 边连成 def-use 图。`LLVMContext` 负责类型与常量的唯一化，所以 `i32` 在进程内只有一个实例。SSA 保证每个 `Value` 单次定义，控制流汇合处用 `phi`。类型系统里有整数、浮点、向量、结构体、数组和 `ptr`；从 LLVM 15 起默认不透明指针，指针不再带被指类型，地址空间和对齐改由 `addrspace` 和 `align` 承载（按版本而定）。文本 `.ll` 与位码之间用 `llvm-as` / `llvm-dis` 互转，`llvm-link` 做模块级链接。

**Pass 是变换**。一个 Pass 只做两件事：从 `AnalysisManager` 取事实，改 IR；返回 `PreservedAnalyses` 声明哪些分析还有效——返回 `all()` 却改了 IR 是最常见的错误来源。新 PassManager 从 LLVM 14 起成为默认，legacy PassManager 在 17 被移除（按版本而定）。层级上 `ModulePassManager` 由 `PassBuilder` 从 pipeline 字符串解析出来，内联这类跨函数变换必须在模块或 CGSCC 层做，函数 Pass 看不到别的函数。

**Target 是参数**。`TargetMachine` 提供数据布局和调用约定；`TargetLowering` 负责把 IR 降到 SelectionDAG / GlobalISel；MC 层管汇编输出和重定位。寄存器、指令、调度模型由 TableGen 的 `.td` 文件描述。

三者的正确耦合方式是：中端不“知道”目标，而是“问”目标——通过 `TargetTransformInfo`（`TargetIRAnalysis`）拿到向量化宽度、指令代价这类参数。这就是为什么同一个 `-passes=loop-vectorize` 在 x86 和 AArch64 上行为不同，而 Pass 代码里没有一行目标相关逻辑。

**最小例子**：同一条链路，看三件套各自的产物。

```bash
clang -O0 -S -emit-llvm -o a.ll x.c
opt -passes='print<domtree>' -disable-output a.ll      # 只读分析，不改 IR
opt -passes='mem2reg,instcombine' -S a.ll -o b.ll      # 变换
llc -march=aarch64 -mcpu=generic b.ll -o b.s           # 换目标，同一份 IR
```

- 第一条命令后 `a.ll` 里 `%a.addr` 这类 `alloca` 还在。
- 第二条 `mem2reg` 删掉 `alloca`/`load`/`store`，换成 `phi`；`instcombine` 再把 `add nsw i32 %x, 0` 折成 `%x`。
- 第三条把同一份 `b.ll` 编成 AArch64 汇编：参数进 `w0`/`w1`，返回进 `w0`。IR 一个字没改，变的只有 Target。

**面试高频问法**：

1. 问：Pass 能不能直接改 `DataLayout` 或调用约定？→ 考点是分层。→ 答：不能。`DataLayout` 属于 `Module`，由前端或 `-mtriple`/`-data-layout` 决定；调用约定写在函数和调用点上，由前端或 ABI 降低阶段产生。Pass 只能读这些信息来判断能不能变换，不能为了让某个优化通过就去改它们。
2. 问：为什么 `PreservedAnalyses` 这么重要？→ 考点是分析失效的正确性。→ 答：分析结果缓存挂在 `AnalysisManager` 上，Pass 返回的集合决定哪些缓存被丢弃。谎报保留会导致后续 Pass 拿到过期支配树，生成错误 IR。删了基本块就必须不保留 `DominatorTreeAnalysis`。
3. 问：`TargetTransformInfo` 解决的是什么问题？→ 考点是中端与后端解耦。→ 答：它把目标相关的代价和容量以查询接口形式注入中端，让向量化、内联、展开这些 Pass 做决策时不硬编码目标知识。加一个新后端不需要改中端 Pass。
4. 问：把同一份 `.ll` 编到两个架构，结果一定等价吗？→ 考点是 IR 语义与目标语义的缝隙。→ 答：IR 层面语义一致，但浮点收缩（`fmuladd`）、`align` 假设、超长整型、原子操作的内存序在不同目标上可能有不同实现代价甚至不可用，所以通常不保证性能等价，个别构造还会被目标拒绝。
5. 问：Pass 能跨函数优化吗？→ 考点是 PassManager 层级。→ 答：函数 Pass 只能看一个 `Function`；跨函数的必须写在模块层或 CGSCC 层。内联之所以在 CGSCC 层，是因为它改调用图，需要自底向上重跑。

## 第 3 章 LLVM IR 精读：模块、函数、基本块、SSA、phi 与类型系统

**要解决的问题**：IR 是 LLVM 里唯一同时被前端、优化器和后端读写的中间产物；如果读不精 IR，就判断不了某个优化到底做没做、写 Pass 时也无从下手，后面关于优化管线和后端的两章也就完全无法展开。

**机制**：

IR 的容器分为四层：`Module`（一个编译单元，持有全局变量、函数声明与定义、元数据）→ `Function`（含 `Argument` 列表与基本块列表）→ `BasicBlock`（有序指令序列，只有一个入口，并以终结指令 `br`/`switch`/`ret`/`invoke`/`unreachable` 结尾）→ `Instruction`。这四层里的所有东西都是 `Value`；值与被使用者的关系用 `Use` 边表示，一个 `Value` 持有使用者列表。`users()`、`replaceAllUsesWith()` 就是在 `Use` 链上操作。

SSA 的约束可以概括成一句话：每个 `Value` 只被定义一次，并且定义点支配所有使用点。局部变量要进入 SSA，必须靠 phi 汇合 —— `mem2reg`（`PromoteMemoryToRegister`）把 `alloca`/`load`/`store` 提升成寄存器值，phi 的插入位置由定义点的**支配边界**迭代求出（iterated dominance frontier）。这也是 IR 里唯一非 SSA 的部分：内存没有 SSA 形式，`load`/`store` 的依赖走别名分析；需要内存级 SSA 时用 `MemorySSA` 分析（成熟度按版本而定）。

phi 的语义是**并行赋值**：`%p = phi i32 [ %a, %bb1 ], [ %b, %bb2 ]` 表示从 `%bb1` 跳来时取 `%a`，从 `%bb2` 跳来时取 `%b`，所有 phi 同时求值，所以交换两个变量只需两条互相引用旧值的 phi，不需要临时变量。代价是：如果某个前驱有多个后继（critical edge，关键边），就必须在边上插入一个只含 phi/`br` 的块，否则无法为这对（前驱，后继）单独指定 incoming 值 —— `SplitCriticalEdge` 做的就是这件事。

类型系统：基础类型 `void/i1/i8/i16/i32/i64/i128/half/float/double/fp128/x86_fp80`，再加 `ptr`、定长数组 `[N x T]`、结构体 `{...}`（可 `packed`）、固定与可伸缩向量 `<N x T>` / `<vscale x N x T>`。指针自 LLVM 15 起默认不透明（`ptr`，不再有 `i8*`/`i32*`），元素类型信息改由 `getelementptr` 的源类型操作数携带 —— 这是读老 IR 与新 IR 最大的差别，具体默认行为按版本而定。

关键取舍：IR 保持 typed（算术与内存访问都带类型），但指针不透明，于是 GEP 成了唯一“带类型地做地址算术”的指令；`inbounds` 是一个承诺（结果不越出对象），优化器据此推断无 UB，写 Pass 时误加 `inbounds` 是经典错误来源。

**最小例子**：

```c
int sum(int *a, int n) { int s = 0; for (int i=0;i<n;i++) s += a[i]; return s; }
```

`clang -O1 -S -emit-llvm` 之后（略去向量化与属性），循环体形如：

```llvm
for.body:
  %iv      = phi i64 [ 0, %for.body.preheader ], [ %iv.next, %for.body ]
  %s       = phi i32 [ 0, %for.body.preheader ], [ %add, %for.body ]
  %addr    = getelementptr inbounds i32, ptr %a, i64 %iv
  %v       = load i32, ptr %addr, align 4
  %add     = add nsw i32 %s, %v
  %iv.next = add nuw nsw i64 %iv, 1
  %exit    = icmp eq i64 %iv.next, %wide.trip.count
  br i1 %exit, label %exit.block, label %for.body
```

带数字读一遍：设 `%a = 0x1000`、`%iv = 3`，则 `%addr = 0x1000 + 3*4 = 0x100c`；两个 phi 各有两条 incoming，回边 `%for.body → %for.body` 对应自引用那一项；`nsw`（no signed wrap）是给后端的礼物 —— 溢出即 UB，于是 `add`+比较可以折叠成一条带条件码的 `cmp`。

**面试高频问法**：

1. 「为什么需要 phi？没有它能不能表达循环携带的值？」→ 考点：SSA 的支配性质与汇合点 → 一句话：同一变量在两条路径上各有一个定义、又要在汇合点被使用，而只能有一个定义点支配全部使用，phi 就是那个“按来路选值”的定义点；没有 phi 就只能退回内存，等于放弃 SSA。
2. 「phi 到了机器码里怎么落地？」→ 考点：并行赋值与 critical edge → 一句话：通常翻成前驱末尾的 move，互相赋值的 phi 组要么并行拷贝、要么靠临时寄存器解环；有 critical edge 时先拆边再放 move，否则那条边上会多走一次不该走的 move。
3. 「`getelementptr` 为什么不直接返回整数地址？」→ 考点：类型携带与指针算术的可组合性 → 一句话：GEP 只算偏移、不访问内存，它带着源元素类型与逐级索引类型，所以在不透明指针下仍能还原数组/结构体步长，`inbounds` 也能单独标注。
4. 「`mem2reg` 之后 IR 一定更好吗？」→ 考点：SSA 提升的前提条件 → 一句话：它只消掉可证明未被取址的局部 `alloca`，收益是让几乎所有机器无关优化看见值流；对地址已逃逸或被 `volatile` 访问的 `alloca` 它不会动，那时该看 SROA 与别名分析。
5. 「IR 里内存为什么不是 SSA，后果是什么？」→ 考点：别名分析为何不可省 → 一句话：`store`/`load` 的副作用无法用“每个地址一个定义”表示，只能靠 `AliasAnalysis` 判断两次访问是否同一对象，这正是 GVN/LICM 依赖 `MemorySSA`、`!tbaa` 等元数据的原因。

## 第 4 章 写第一个 Pass：Analysis 与 Transform 的区别、PassManager 的组织

**要解决的问题**：看懂 IR 之后，下一个问题是“改 IR 的代码怎么组织、怎么挂进管线、怎么不被框架反过来坑”。Analysis/Transform 的划分与 PassManager 的层级，决定了 pass 之间的依赖、缓存与失效责任。

**机制**：

只有两类 pass：Transform 修改 IR 并返回 `PreservedAnalyses`；Analysis 不修改 IR，返回一个结果对象，由 `AnalysisManager` 缓存、按需重算。

新 PM（New Pass Manager，Clang 12 起为默认）用 CRTP 做分派：Transform 继承 `PassInfoMixin<Derived>`，实现 `run(IRUnitT &, AnalysisManagerT &)`；Analysis 继承 `AnalysisInfoMixin<Derived>`，在其中定义 `using Result = ...` 并实现 `run()`。`PassInfoMixin` 提供 `name()` 与 `isRequired()` —— 后者返回 true 时，即使函数带 `optnone` 也会跑（`optnone` 是 `-O0` 打上的）。

层级是嵌套的：`ModulePassManager` → `CGSCCPassManager`（调用图上的强连通分量，内联住在这一层）→ `FunctionPassManager` → `LoopPassManager`。`opt -passes='function(mem2reg)'` 这种 DSL 直接对应嵌套结构，`require<loops>` / `print<loops>` 用来取分析结果。

失效契约才是这一章真正的重点：`PreservedAnalyses::all()` 表示什么都没坏，`none()` 表示全失效，`preserve<DominatorTreeAnalysis>()`、`preserveSet<CFGA

## 第 5 章 从源码到 IR：Clang 的 AST 与 CodeGen 如何分工

**要解决的问题**：Clang 要把 C/C++ 的语言语义降到 LLVM IR，但 AST 与 CodeGen 必须分工。不解决，语言特性和 ABI 细节会漏进优化器，或 CodeGen 过早优化、难维护。

**机制**：Clang 流程是预处理 → Parser → Sema → AST → CodeGen → `llvm::Module` → 优化/后端。AST 是语义树，不是 SSA：`FunctionDecl`、`CompoundStmt`、`ReturnStmt`、`BinaryOperator`、`DeclRefExpr`、`ImplicitCastExpr`、`IntegerLiteral` 等节点保留类型、作用域、重载决议和隐式转换。Sema 把隐式转换显式化，CodeGen 不再猜语义。

CodeGen 以 Translation Unit 为单位：`CodeGenModule` 拥有 `llvm::Module`，管全局变量/函数、常量、类型与 ABI lowering、全局构造/析构、debug info；每个函数由 `CodeGenFunction` 用 `IRBuilder` 生成基本块和指令。局部变量先落成 `alloca` 还是直接 SSA，取决于是否可取地址、生命周期和 cleanup；前端通常选简单形式，交给 `mem2reg` 提升。短路求值、三目、异常/cleanup、虚调用、结构体拷贝都在这里降成 IR。ABI 的关键部分也在这里：Clang 的 target `ABIInfo` 决定参数/返回如何分类，IR 里可能出现 `sret`、`byval` 等属性；LLVM 后端再把调用约定映射到机器层。

关键取舍：CodeGen 生成“直白、可优化”的 IR，而不是在 AST 上做复杂优化。这样前端简单，优化器只面对 IR；代价是 O0 IR 冗余，依赖中端清理。

**最小例子**：`int f(int x){ return x*2+1; }`。`clang -Xclang -ast-dump -fsyntax-only f.c` 可见 `FunctionDecl` 下的 `ParmVarDecl`、`CompoundStmt`、`ReturnStmt`、`BinaryOperator '+'`，其左是 `BinaryOperator '*'`，叶子是 `ImplicitCastExpr`/`DeclRefExpr` 和 `IntegerLiteral`。`clang -S -emit-llvm -O0 f.c -o f.ll` 的函数体通常是 `alloca i32`、`store` 参数、`load`、`mul`、`add`、`ret`；`opt -passes=mem2reg` 后 alloca/load/store 被消掉，得到类似 `%1 = mul i32 %0, 2`、`%2 = add i32 %1, 1`、`ret i32 %2`。调用 `f(3)` 返回 7；IR 里的常量 2、1 就是 AST 的 `IntegerLiteral` 降下来的。

**面试高频问法**：
- 问：AST 和 LLVM IR 的职责边界？→ 考点：语义分析 vs lowering。答：AST 保留语言级声明、类型和隐式转换，CodeGen 按

## 第 6 章 优化管线：内联、GVN、LICM、循环优化、向量化各自的适用条件

**要解决的问题**：中端把 IR 从“能跑”变成“跑得快”，但每个优化都是一条「前提不满足就静默跳过」的规则。面试里问的从来不是“GVN 是什么”，而是“这个场景为什么没有生效”。这一章按管线里的实际顺序，把每个优化各自的适用条件展开说明。

**机制**

**（一）管线骨架**。新 PM（New PassManager）里默认管线由 `PassBuilder` 拼装，层级靠 adaptor 表达：Module → CGSCC → Function → Loop，每层有自己的 `AnalysisManager`，跨层时下层分析会被清掉、回到上层时模块级分析仍在。伪代码如下：

```cpp
// buildPerModuleDefaultPipeline 的骨架（近年顺序有调整，名称按版本而定）
MPM.addPass(buildModuleSimplificationPipeline(Level, Phase));
//   GlobalOpt、IPSCCP、删不可达
//   ModuleToPostOrderCGSCCPassAdaptor( 内联 + 函数简化 )  ← 跑到 CGSCC 不动点
//   ModuleToFunctionPassAdaptor( EarlyFPM: SROA、EarlyCSE、SimplifyCFG )
MPM.addPass(buildModuleOptimizationPipeline(Level, Phase));
//   LoopSimplify、LCSSA、LoopRotate（向量化的规范化前提）
//   FunctionToLoopPassAdaptor( LICM、IndVarSimplify、LoopVectorize、LoopUnroll )
//   收尾 InstCombine、GVN、SimplifyCFG、ADCE，然后再来一轮
```

两个结构性事实要记住：一是**迭代不一定是固定点**，`InstCombine` 在管线里出现多次，因为一轮替换会暴露新的匹配模式；二是**内联在 CGSCC 层**，内联之后必须重新跑一遍函数级简化，否则内联进来的 `alloca`、`load` 不会被 SROA、GVN 处理掉。

**（二）内联（InlinerPass）**。前提：调用点能看到被调函数的**函数体**（`external` 声明没定义就不行），函数没有 `noinline`，调用者没有 `optnone`。核心是 `getInlineCost` 成本模型：逐条指令按 `InstrCost` 累加，加上 `CallPenalty`；实参是常量、`alloca`、可确定参数时打折；被调函数是 static/internal 且**只有这一个调用点**时给一个很大的奖励（`LastCallToStaticBonus`），因为内联后原函数可以被删掉。阈值随优化级别变化（-O3 高于 -Os、-Oz），具体数值按版本而定。`alwaysinline` 直接越过成本模型，`optnone`、`noinline` 直接否决。

**（三）GVN**。条件是：能被证明“等价”的表达式。对纯指令，靠值编号（value numbering）算出表达式签名，在支配树上找已算过的同签名值；对 `load`，还要靠 MemorySSA/AliasAnalysis 证明两次 load 之间没有可能别名（may-alias）的写、且指针没被 invalidate。所以 `volatile`、atomic 不参与；循环里跨基本块的冗余 load 需要支配关系支持；`invariant.load` 元数据可以帮助消除。GVN 的另一项工作是消除“同值 phi”，它比 InstCombine 强的地方在于全局等价类，弱的地方在于不做 peephole。

**（四）LICM**。前提链条最长：循环必须是 loop-simplify 形式（有唯一的 preheader、单一的 latch、dedicated exits），且在 LCSSA 形式下；指令要 `isSafeToExecuteUnconditionally`（不会新引入 trap）并且循环内没有定义、没有副作用。对 `load` 额外要求：要么这条 load 在循环里必然被执行，要么指针 `dereferenceable`（可推测执行），**并且**循环内没有任何可能别名（may-alias）的写。最后一条是实战里最常见的失败点：函数参数是 `float *` 而不是 `float *restrict`，别名分析没法证明 `*y` 和 `*a` 不重叠，就只能放弃提升。

**（五）循环优化家族**。`LoopSimplify`、`LCSSA` 是**规范化**而不是优化，它们把循环变成其他 pass 能识别的形状（LCSSA 让循环外使用都经过 phi，`LoopUnswitch`、向量化才能安全改写）。`LoopRotate` 把 while 形状旋转成 do-while，减少一次条件跳转，同时是后续 unswitch、unroll 的前提。`IndVarSimplify` 用 ScalarEvolution 把归纳变量整理成标准形式，识别可计算的 trip count `{$start,+,$step}<$btc>`，这是向量化的前提条件。`LoopUnswitch` 要求分支条件循环不变、且不会把循环变成可能无限执行。`LoopIdiom` 需要识别出内存操作的模式。`LoopInterchange`、`LoopFusion`、`LoopDistribute` 默认不开启，需要显式打开。

**（六）向量化**。`LoopVectorize` 要同时满足三项条件：trip count 能被 SceV 算出或能生成运行时的检查（runtime check，对应 IR 中的 `vector.memcheck` 块），`LoopAccessAnalysis` 能证明没有跨迭代依赖，TTI 的成本模型判定收益为正（向量宽度由目标寄存器宽度和 `getMaxInterleaveFactor` 决定）。任一条不满足就有两种结局：生成带运行时检查的**分版本循环**（检查通过走向量路径，否则走标量路径，`vector.memcheck` 就是干这个的），或者完全放弃。`SLPVectorize` 是另一条路径，面向**基本块内**多条同构指令，不需要循环，只要求打包后有收益。

**最小例子**

```c
// axpy.c
void axpy(float *restrict y, const float *restrict x, float a, int n) {
  for (int i = 0; i < n; i++) y[i] += a * x[i];
}
```

```bash
clang -O2 -S -emit-llvm axpy.c -o axpy.ll
clang -O2 -march=haswell -S -emit-llvm axpy.c -o axpy_avx2.ll
opt -passes='default<O2>' -print-pipeline-passes -disable-output axpy.ll | head -c 800
```

在 `-O2` 下（x86-64 默认 SSE2 目标），`axpy.ll` 的循环大体长这样（符号名按版本而异）：

```llvm
vector.ph:
  %n.vec = and i64 %wide.trip.count, -4        ; VF = 4
vector.body:
  %wide.load  = load <4 x float>, ptr %x, align 4
  %wide.load1 = load <4 x float>, ptr %y, align 4
  %mul = fmul <4 x float> %broadcast.splat, %wide.load
  %add = fadd <4 x float> %wide.load1, %mul
  store <4 x float> %add, ptr %y, align 4
```

加上 `-march=haswell` 后变成 `<8 x float>`（AVX2 的 256 位寄存器）。**去掉 `restrict` 后再编译**，向量化通常仍然发生，但会多出一个 `vector.memcheck` 块做指针区间重叠检查，不通过就跳转到标量循环，这就是“条件不满足时的降级路径”。

关于 LICM 的对比实验：把 `a` 从函数参数改成 `float a = *ap;`，再把 `a` 提到循环外。如果 `ap` 是 `const float *` 且循环里只写 `y`，`basic-aa` 因为类型不同、或因为 `const` 声明不能作为别名依据，结论会随目标与别名规则变化；把 `ap` 和 `y` 都设成 `float *` 时，循环内的写与 `*ap` 可能别名，LICM 就提升不了这条 load。循环执行 1000 次，代价就是 1000 次 load 和 999 次 load 的差别。用 `-debug-pass-manager` 能看到 `LICM` 是否被跳过。

**面试高频问法**

1. **“`-O2` 都开了，为什么循环里还有一条不变的 `load`？”** → 考点是 LICM 的别名前提。答法：“LICM 提升一条 load 要求循环内没有可能别名的写，还要么保证必执行、要么指针 dereferenceable。只拿到 `float *` 时别名分析证明不了不重叠，它就放弃。加 `restrict`、或者把值拷到局部变量，才能提升。”

2. **“`-O2` 和 `-O3` 差在哪？”** → 考点是管线级别差异不在“优化开关”，而在阈值和追加 pass。答法：“主要是内联阈值更高、循环展开和向量化更激进（循环向量化和 SLP 在 -O2 起也开，具体起始版本按版本而定）、-O3 追加一些偏重代码体积的循环变换。功能不是开关式差异，是成本模型参数不同。”

3. **“内联的成本模型怎么算？为什么这个小函数没内联，那个大的反而内联了？”** → 考点是成本不只是指令数。答法：“逐条指令累加代价，加调用开销，实参是常量或可确定的打折；如果被调函数是 internal/static 且只有这一个调用点，会给一个很大的奖励，因为内联后原函数能删掉。所以单调用点的‘大’函数常常被内联，多调用点的小函数反而被拒。”

4. **“GVN 和 InstCombine 有什么区别？为什么管线里 InstCombine 出现好几次？”** → 考点是局部 peephole 与全局等价类的分工。答法：“InstCombine 是模式匹配式的局部化简，GVN 是在支配树上做值编号，找全局冗余表达式并做冗余 load 消除。多次出现是因为前一轮替换会暴露新的模式，要反复跑到稳定，不一定是一次就能到不动点。”

5. **“向量化器什么时候放弃？`vector.memcheck` 是什么？”** → 考点是三条前提。答法：“trip count 可算或可运行时检查、没有跨迭代依赖、成本模型判定有收益。别名不确定时会分版本：先做运行时区间检查，通过走向量路径，否则走标量路径，`vector.memcheck` 就是这段检查；连检查都不划算，就整条循环不向量化。”

## 第 7 章 后端：SelectionDAG 与 GlobalISel、指令选择、寄存器分配、指令调度

**要解决的问题**：IR 仍是目标无关的三地址码，后端要把它变成某颗 CPU 能执行的机器指令；不解决就没有合法指令、寄存器分配和栈帧，LLVM 只能停在分析层。

**机制**：后端入口是 `TargetMachine`，函数级容器是 `MachineFunction`。两条指令选择路径：

- **SelectionDAG**：`SelectionDAGBuilder` 把基本块建成 DAG，节点是 `SDNode`；边除数据依赖外还有 **chain**（内存/副作用顺序）和 **glue**（多返回值必须一起发射）。随后做类型/操作合法化（promote、expand、custom），`DAGCombine` 做目标相关合并，`SelectionDAGISel` 用 TableGen 生成的模式匹配选中指令，再按调度模型排成 `MachineInstr`。
- **GlobalISel**：`IRTranslator` 先降到通用 MIR，再 `Legalizer` → `RegBankSelect` → `InstructionSelect`，把合法化、选寄存器组、选指令拆开，减少 DAG 构造开销；覆盖度按目标和版本而定，不支持时可回退 SelectionDAG。

```text
IR -> SelectionDAGBuilder -> 类型/操作合法化 -> DAGCombine
   -> SelectionDAGISel(TableGen matcher) -> MachineInstr
   -> MachineScheduler -> RegAllocGreedy -> PostMachineScheduler
   -> PrologEpilogInserter -> AsmPrinter
GlobalISel: IR -> IRTranslator -> Legalizer -> RegBankSelect -> InstructionSelect
```

指令选择的核心是 `.td` 里的指令定义与匹配模式，TableGen 生成 matcher；复杂寻址

## 第 8 章 目标描述与 ABI：调用约定、栈帧布局、重定位

**要解决的问题**：IR 是 target 无关的，它只说「调用函数 f，参数是这 7 个 i64」。要把这句变成 x86-64 上合法的机器码，必须回答三个问题：参数放进哪几个寄存器、多出来的放栈上哪个偏移；函数体里 rsp/rbp 怎么动、被调用者保存寄存器由谁保存；`.o` 里那些「地址待定」的字节由谁来填。这一章管的就是 IR 到具体 ISA 之间那层「物理契约」。不解决它，后端生成的代码一进入 callee-saved 寄存器、一调用外部函数就崩。

**机制**

**三份描述，三个抽象层。** 后端不硬编码 x86，而是从 TableGen 的 `.td` 文件生成描述：`Target.td` 的 `RegisterInfo`（寄存器类）、`InstrInfo`（指令编码与 pattern）、`CallingConv.td`（ABI 规则）、`SchedMachineModel`（调度模型）。`TargetMachine::getSubtargetImpl(const Function &F)` 允许 per-function 的 subtarget，这就是 `__attribute__((target("avx2")))` 能在一个 TU 里混用的原因。

**调用约定写在 TableGen 里，不在 C++ 里。** `CC_X86_64_SysV` 大致长这样：

```tablegen
def CC_X86_64_C : CallingConv<[
  CCIfType<[i32], CCAssignToReg<[EDI, ESI, EDX, ECX, R8D, R9D]>>,
  CCIfType<[i64], CCAssignToReg<[RDI, RSI, RDX, RCX, R8,  R9 ]>>,
  CCIfType<[f32], CCAssignToReg<[XMM0,XMM1,XMM2,XMM3,XMM4,XMM5,XMM6,XMM7]>>,
  CCAssignToStack<8, 8>            // 溢出参数：8 字节槽，8 字节对齐
]>;
```

`CCState::AnalyzeFormalArguments` 拿这份规则跑一遍，得到每个实参的 `CCValAssign`（LocInfo：寄存器或栈偏移）。`TargetLowering::LowerFormalArguments` 据此为寄存器参数发 `ISD::CopyFromReg`，为栈参数发基于 frame index 的 load。`LowerCall` 是镜像操作：先 `ISD::CALLSEQ_START` 拿到一个「即将出现的返回地址 + 出参区」的 frame index，把参数 `CopyToReg`，发 `CALL`，再 `CALLSEQ_END`。

**IR 层能看见的 ABI 痕迹。** Clang 前端并不决定寄存器，但它把 ABI 中「IR 必须表达」的部分提前写进函数签名：大结构体返回用 `sret` 指针、按值传大结构体用 `byval`、`inreg`、小整型的 `signext`/`zeroext`、变参函数的 `...`。所以你在 IR 里看到的 `ptr sret(%struct.S) align 8 %agg.result` 就是 ABI 的投影，后端 `LowerCall` 再把它降级成具体的 RDI 传递。这也是为什么 ABI 不能全部压在 Clang 里：IR 是 target 无关的，同一份 `.ll` 可以喂给 `llc -mtriple=aarch64`；真正的寄存器分配必须留在 target 层。

**栈帧由 PEI（PrologEpilogInserter）统一收口。** `MachineFrameInfo` 记录所有对象（spill 槽、局部变量、出参区、已保存寄存器），PEI 先调 `getCalleeSavedRegs()`/`getCallPreservedMask()` 算出哪些寄存器跨调用必须保存（在 x86-64 SysV 下是 RBX、RBP、R12–R15），调 `determineCalleeSaves()` 按需插入 spill，最后调 `TargetFrameLowering::emitPrologue/emitEpilogue` 吐出真实的 `push/mov/sub`。帧对象在 `TargetRegisterInfo::eliminateFrameIndex` 阶段被替换成 `[rsp+N]` 或 `[rbp-N]`；有 VLA 或动态 `alloca` 时不可能用静态 rsp 偏移，只能锁帧指针。

**重定位：汇编器留洞，链接器填。** MC 层在发射时，若操作数含不可解析符号，就产生一个 `MCFixup`（`MCFixupKind` + 字节偏移 + `MCExpr`）。object writer 再把它映射成 ELF 的重定位类型：`X86ELFObjectWriter::getRelocType` 把 `X86::reloc_riprel_4byte` 映射到 `R_X86_64_PC32`，把对函数的 `call` 映射到 `R_X86_64_PLT32`。链接器统一按 $S + A - P$ 求值（$S$ 符号地址，$A$ addend，$P$ 重定位字段自身的地址）。`R_X86_64_PC32` 和 `R_X86_64_PLT32` 在 x86-64 上算出来的值一样，差别只在语义：后者告诉链接器「这是个 call，如果目标在共享库里，可以走 PLT 蹦床」，AArch64 上同样的区分是有真实代码差异的（`BL` vs `ADRP+ADD`）。

**最小例子**

```c
extern long g(long);
long f(long a, long b, long c, long d, long e, long h, long i) {
    return g(a + i) + b;
}
```

`clang -O1 -S -fno-omit-frame-pointer` 得到的形状（省略 `.cfi_*`）：

```asm
f:
        pushq   %rbp
        movq    %rsp, %rbp
        pushq   %rbx
        subq    $8, %rsp          # 对齐桩，见下
        movq    %rsi, %rbx        # b：要跨 call 存活 → callee-saved
        movq    16(%rbp), %rax    # i：第 7 个参数在栈上
        addq    %rdi, %rax        # a + i
        movq    %rax, %rdi
        callq   g@PLT
        addq    %rbx, %rax
        addq    $8, %rsp
        popq    %rbx
        popq    %rbp
        retq
```

逐项核对 ABI：

- 参数映射：a→RDI、b→RSI、c→RDX、d→RCX、e→R8、h→R9，第 7 个 i 落在栈上。进入函数时 `[rsp]` 是返回地址，`[rsp+8]` 是 i；`push rbp` 后 `rbp = rsp_entry - 8`，所以 `i` 在 `[rbp+16]`。
- 对齐：SysV 要求「控制转移到函数入口时 $rsp + 8 \equiv 0 \pmod{16}$」，即 entry 时 $rsp \equiv 8$。`push rbp` → 0，`push rbx` → 8，再 `sub $8` → 0，此时执行 `call` 才合规。callee 入口又回到 8。这就是那条看起来莫名其妙的 `subq $8` 的来源——它不是给变量留地方，纯粹是对齐桩（也可以 `push` 一个废寄存器或 `andq $-16, %rsp`）。
- callee-saved：`b` 活过 `call g`，所以必须进 RBX 而不是 RCX；`pushq %rbx` 同时完成了「保存调用者的值」和「给自己腾出存储」，`popq %rbx` 恢复。
- 重定位：`callq g@PLT` 处的 rel32 字段在指令第 2 字节，`.o` 里生成 `R_X86_64_PLT32`，addend = $-4$，因为 x86 的 PC 相对位移以下一条指令为基准，而 $P$ 指向字段本身，差 4 字节。

**面试高频问法**

1. **「调用约定到底是在 Clang 里实现的还是 LLVM 后端里实现的？」** → 考点是 ABI 信息在 IR/后端的分层。一句话答法：分两层——Clang 只负责 IR 必须表达的那部分（`sret`/`byval`/`inreg`/`signext`），寄存器与栈槽的分配由 `CallingConv.td` + `TargetLowering::LowerCall/LowerFormalArguments` 完成，因为 IR 要保持 target 无关，同一份 `.ll` 要能喂给任何 `-mtriple`。

2. **「为什么函数入口处 $rsp$ 是 8 而不是 16 的倍数？」** → 考点是 call 指令压返回地址这件事。一句话答法：ABI 要求的是「`call` 执行前 $rsp$ 16 字节对齐」，`call` 把 8 字节返回地址压栈，所以被调用方一进来看到的是 $rsp \equiv 8 \pmod{16}$，编译器要在 prologue 里补一个 8 字节的桩才能再次安全地 `call`。

3. **「callee-saved 寄存器是编译器在哪一步决定要保存的？」** → 考点是 PEI 在流水线里的位置。一句话答法：寄存器分配之后，PEI 用 `TargetRegisterInfo::getCalleeSavedRegs()` 和活跃性算出真正被用到的 callee-saved 寄存器，`determineCalleeSaves()` 插 spill，再由 `TargetFrameLowering::emitPrologue` 一次性生成 push 序列——不是每遇到一次调用就存一次。

4. **「`R_X86_64_PC32` 和 `R_X86_64_PLT32` 有什么区别？既然算出来的值一样，为什么不用一个？」** → 考点是重定位语义与链接器行为。一句话答法：数值上两者都是 $S+A-P$，区别在语义标注——`PLT32` 声明「这是对函数的过程调用，目标可能在共享库里，可以经 PLT 跳转」，在 x86-64 上链接器为了兼容把 `PLT32` 当 `PC32` 处理，但在 AArch64 这类「直调只有 ±128MB 范围」的架构上，这个区分直接决定要不要生成跳板代码。

5. **「什么时候 LLVM 不能省略帧指针？」** → 考点是 frame index 消除的约束。一句话答法：栈上对象大小在编译期固定时可以用 rsp 相对寻址、省掉 RBP；一旦出现 VLA、动态 `alloca` 或需要动态调整栈的场合，偏移不再是常量，必须保留帧指针（`-fno-omit-frame-pointer` 强制保留，同时它也是 perf/采样型 profiler 的栈回溯基础）。

6. （可选）**「红区是什么，为什么叶函数可以不要栈帧？」** → x86-64 SysV 在 `[rsp-128, rsp)` 划了 128 字节红区，信号处理不会踩坏它；不调用其它函数的叶函数可以直接用红区存局部变量，prologue/epilogue 全省。

## 第 9 章 可观测性：debug info、sanitizer 插桩、opt 的调试开关

**要解决的问题**：编译器出错时没有这三样东西，你只能靠猜。debug info 决定你能不能把崩溃地址映射回源码行和变量；sanitizer 决定内存与并发错误是在测试阶段暴露，还是留到线上；opt 的调试开关决定一个优化 bug 对你来说是「可疑」还是「已定位」。缺了它们，编译器的正确性无法验证，性能回归也无法归因。

**机制**

三条链路都在 IR 层，但作用点不同。

**debug info 是元数据，不是指令。** 结构是 `DICompileUnit` → `DISubprogram` → `DILocation(line, col, scope)`，局部变量是 `DILocalVariable` + `DIExpression`。指令通过 `!dbg !N` 挂到 `DILocation` 上；模块级由 `!llvm.dbg.cu` 列出编译单元，`llvm.module.flags` 里的 `Dwarf Version` / `Debug Info Version` 保证链接时版本一致。变量位置的表达方式在变：旧版是 `llvm.dbg.declare` / `llvm.dbg.value` intrinsic，较新版本（LLVM 19 起）改用 `#dbg_declare` / `#dbg_value` 这类记录，按版本而定；`DIBuilder` 是构造这些元数据的 C++ 接口。

关键取舍在优化下：变量被提升到寄存器、被拆成多个 SSA 值、被内联改变行号，debug info 必然失真。LLVM 的应对是赋值追踪和 salvage，尽量在删除指令时把 `dbg.value` 迁移到等价值上，代价是编译时间。只要符号化栈回溯，可以用 `-gline-tables-only`：`DICompileUnit` 的 `emissionKind` 设为 `LineTablesOnly`，没有变量和类型，体积小得多，也是 release 构建常见的选择。

**sanitizer 是 Pass，插桩发生在 IR 上。** ASan 的核心是影子内存：应用地址 `a` 的 8 个字节对应影子里的 1 个字节，

$$\text{shadow}(a) = (a \gg 3) + \text{offset}$$

x86-64 Linux 上 offset 常见是 `0x7fff8000`（按平台而定）。每次 load/store 前读一个影子字节，非零就走慢路径调 `__asan_report_load4` / `__asan_report_store8` 这类函数。堆越界、栈越界、全局越界、use-after-free 全都归约为「影子被毒化」，所以检查是 $O(1)$，开销是常数倍（ASan 官方文档给的量级是 2 倍，实际按程序而定）。free 不真正归还内存，而是整块毒化后进隔离区延迟复用——这是它能抓 UAF 的原因。栈对象走 `__asan_stack_malloc_N` 重排栈帧加 redzone，全局对象走 `__asan_register_globals`。

UBSan 是纯检查，命中调 `__ubsan_handle_add_overflow` 之类，默认 recover（打印后继续），`-fno-sanitize-recover=all` 才变成 trap。TSan 在每个访存处记录向量时钟到影子单元做 happens-before 判定（`__tsan_read4`），开销明显高于 ASan。MSan 的影子记录每个 bit 是否已初始化，要求全程序插桩（含 libc），否则误报。插桩时机上，ASan 要在大部分优化跑完之后、指令选择之前插入，插入后只跑少量必须的清理 pass，否则检查会被优化掉或与重排后的内存布局错位。

**opt 的调试开关分四类**：看 IR（`-print-after-all`、`-print-before-all`、只打变化的 `-print-changed`）；看 pass 调度（`-debug-pass-manager`）；看 pass 内部日志（`-debug-only=<type>`，需要非 `NDEBUG` 构建，即 `LLVM_ENABLE_ASSERTIONS=ON`，否则 `LLVM_DEBUG` 展开为空）；定位引入 bug 的 pass（`-opt-bisect-limit=N`，只执行前 N 个 pass 实例，二分）。另有两个低成本高回报的：`-verify-each` 每个 pass 后跑 verifier，早崩早发现；`-Rpass=inline` / `-pass-remarks=inline` 直接告诉你某个调用点为什么没内联。

**最小例子**

```c
int f(int *p) { return *p; }
```

`clang -O1 -fsanitize=address -S -emit-llvm` 出的 IR（简化）：

```llvm
define dso_local i32 @f(ptr noundef %p) {
entry:
  %0 = ptrtoint ptr %p to i64
  %1 = lshr i64 %0, 3
  %2 = add i64 %1, 2147450880        ; 0x7FFF8000
  %3 = inttoptr i64 %2 to ptr
  %4 = load i8, ptr %3
  %5 = icmp ne i8 %4, 0
  br i1 %5, label %check, label %load
check:
  call void @__asan_report_load4(i64 %0)
  unreachable
load:
  %r = load i32, ptr %p, align 4, !dbg !12
  ret i32 %r
}
```

`2147450880 = 0x7FFF8000`，正是影子偏移；被检查的是 `p>>3 + offset` 处的 1 个字节。加 `-g` 后 `%r` 那行带 `!dbg !12`，`!12 = !DILocation(line: 1, column: 28, scope: !9)`，崩溃时 `llvm-symbolizer` 就能把地址还原成 `f` 的第 1 行第 28 列。

**面试高频问法**

- **ASan 怎么检测越界，为什么开销能压到常数倍？** → 考点：影子映射的复杂度。→ 把地址右移 3 位加固定偏移得到影子字节，每次访存只多读 1 字节，越界和 UAF 都表现为影子非零，慢路径才调 `__asan_report_*`，所以是 $O(1)$ 而不是查边界表。
- **为什么 ASan 能抓到 use-after-free？** → 考点：free 的语义被改了。→ free 时把整块影子写成毒化值，内存进隔离区延迟复用，再访问读到的影子非零就报错；代价是内存占用上升。
- **`-debug-only=foo` 什么都不输出，怎么回事？** → 考点：这是编译期开关。→ `LLVM_DEBUG` 在定义了 `NDEBUG` 的 release 构建里是空操作，得用 `LLVM_ENABLE_ASSERTIONS=ON` 的构建，而且 pass 里确实写了该 type 的调试输出。
- **开了优化以后调试器看不到变量，是谁的问题？** → 考点：debug info 在优化下的存活。→ 优化把变量拆成多个 SSA 值或提升到寄存器，LLVM 靠赋值追踪和 salvage 尽力保留，剩下的失真属于设计取舍；只要行号就上 `-gline-tables-only`。
- **线上崩溃只给了一个地址，怎么定位？** → 考点：符号化链路。→ release 也要留 `-g` 或至少行号表的二进制，用 `llvm-symbolizer` / `addr2line` 把地址映射回 `file:line`，函数名从符号表来，缺 DWARF 就只能看汇编。

## 第 10 章 什么时候不该用 LLVM：教学编译器、JIT、DSL 的取舍

**要解决的问题**：LLVM 是「所有语言、所有目标」的重型基础设施，选错场景的代价是构建时间、产物体积、API 迁移成本和团队认知。这一章的作用是划边界：什么情况下接 LLVM 是纯亏损，以及不用它时用什么。

**机制**

判断不看「LLVM 好不好」，看三个变量：目标平台数量、优化需求强度、单段代码的执行次数。

**教学编译器。** 课程目标是前端（词法、语法、语义、类型检查）和 IR 设计。接 LLVM 等于把中后端整段跳过，学生只写一个 AST→IR 的翻译器，指令选择、寄存器分配、调用约定一个都碰不到；而 LLVM 的构建成本（CMake、数十 GB 磁盘、链接时间）和 C++ API 的版本波动会吃掉课程时间。替代路径是自己写树遍历解释器 → 栈式字节码 VM → 简单寄存器机，或者用 QBE、Cranelift 这类小后端。

**JIT。** LLVM 的 JIT 接口是 ORC：`llvm::orc::LLJIT`、`ExecutionSession`、`JITDylib`、`ThreadSafeModule`、`DynamicLibrarySearchGenerator`。把函数编译到 `-O0`/`-O2` 通常是毫秒到几十毫秒量级（按实现和函数大小而定），对冷启动敏感的进程（CLI 工具、serverless）摊不平。常见做法是 tier-up：先解释执行或模板 JIT 保证启动，用计数器或回边计数识别热点，再对热点函数生成 IR 交给 ORC 优化。tier-up 的额外工程量在 OSR——在循环入口构造新栈帧跳进优化代码，以及代码内存的 W^X 管理、GC 栈图协作（`gc.statepoint` / `gc.root`）、异常展开表和调试信息。

JIT 的回本点可以直接算。设一次编译成本 $T_c$，解释执行一次 $T_i$，编译后执行一次 $T_j$，则执行 $N$ 次才回本：

$$N^* = \frac{T_c}{T_i - T_j}$$

**DSL。** 如果 DSL 只是表达式求值加少量控制流，字节码 VM 更划算：解析成 `enum Op` 数组，switch 分发，几百行代码，对配置、规则这类场景性能足够。只有需要跟宿主语言零拷贝互操作、需要 SIMD、需要跨多种 CPU 时，LLVM 才是正解。折中方案是先解释，再对热点子集生成 IR。

**几条硬约束**

## 第 11 章 面向计算与域特定语言的编译：GPU 后端、Triton、TVM、XLA 与 dialect 分层

**要解决的问题**：前九章讲的是「一条指令流怎么变成更快的指令流」。但张量程序的问题不在指令层：一个 matmul 或 attention，真正决定性能的是**线程怎么映射到数据、数据在显存层次里怎么搬、延迟怎么用流水线盖住**。这三件事在 CUDA 里全由人手写死在代码里，于是「算法」和「调度」被绑死：换个 GPU 要重调，换个形状要重调，换家公司要重写。DSL 编译器要解决的就是这个绑定——**让用户只描述算什么，把线程映射、显存布局、流水线级数交给编译器或搜索**。代价是控制力下降，所以极端 kernel 仍然手写。

**机制**

**先说清分层，这是所有讨论的前提。** 从高层到底层是四段，每一段解决不同的问题：

| 层 | 典型表示 | 决定什么 | 代表系统 |
|---|---|---|---|
| 图 / 算子层 | XLA 的 HLO、TVM 的 Relay/Relax | 算子怎么融合、张量布局怎么分配、内存复用 | XLA、TVM（图侧）、`torch.compile` 的图捕获 |
| tile / 循环层 | TVM 的 TIR 与 schedule、Halide 的 schedule、MLIR 的 `linalg`/`affine` | 循环怎么切、分块多大、哪一维向量化、哪块进共享内存 | TVM、Halide、MLIR |
| 线程 / 显存层 | Triton 的 block 模型、MLIR 的 `gpu` dialect | 一个 tile 怎么切给线程/warp、同步点放哪、共享内存如何编址 | Triton、MLIR `gpu`、NVVM/ROCDL |
| 机器码层 | PTX / SASS、目标 ISA | 指令选择、寄存器分配、调度 | LLVM 后端、ptxas |

**核心变换只有三类半，认清它们比认清产品名有用**：

1. **融合（fusion）**——把多个算子合成一个 kernel，省掉中间结果落显存。这是图层的头号收益来源；判断依据是「融合后是否重复计算或破坏并行度」。
2. **tiling 与布局（layout）**——切块使之适配共享内存与寄存器容量，同时保证访存合并（coalescing）与避免 bank conflict。同一份数学，布局不同可以差出数倍。
3. **流水线化（software pipelining）**——把后续迭代的 load 提前发出，用多级 staging 掩盖显存延迟；Triton 里暴露为 `num_stages`，本质与 CPU 上的软件流水同一件事。
4. **（半类）自动调优**——把上面三类的参数当搜索空间，用代价模型 + 实测挑一组；搜什么、代价模型估什么，决定这条路值不值得走。

**Triton：block 级编程模型。** 你写的是「一个 tile 怎么算」，不写线程号。编译器负责把 block 切给 warp、决定共享内存分配、合并访存、插入流水线；暴露的旋钮很少，主要是 `num_warps` 与 `num_stages`。下降路径是 Triton IR（MLIR 体系）→ LLVM IR → PTX/cubin，另有 AMD 后端走 ROCm。**取舍**：控制力介于 CUDA 与整图编译器之间——常规 kernel 几行就有接近手写的性能，极端布局（手写 swizzle、特殊 tensor core 映射）仍要回 CUDA/CUTLASS。

**TVM：schedule 与实现分离，加自动调优。** 图侧是 Relay/Relax（新版本重心逐步转到 Relax/TIR，以当前版本文档为准），计算用 TE 描述，性能靠 schedule 原语显式控制：`split`/`reorder`/`tile`/`bind`/`fuse`/`compute_at`。再往上叠自动调优（AutoTVM/Ansor 一类：定义搜索空间 + 代价模型 + 实测），以及 BYOC（把子图交给别的后端）。**取舍**：后端最多（CUDA/OpenCL/Metal/ROCm/CPU，另有 microTVM），代价是调优时间长、版本演进快，写出来的 schedule 与版本绑定。

**XLA：整图视角。** HLO 图进来，做算子融合、layout assignment、内存分配，再降到 GPU/CPU/TPU 后端；由 JAX/TF 驱动，`jit` 的边界就是编译的边界。**取舍**：整模型优化能力强（融合与布局是全局决策），但控制粒度粗——你很难指定"这个循环用 128 个线程"；动态形状的支持程度按版本而定，图外的 Python 控制流会打断优化。

**MLIR：不是编译器，是分层下降的基础设施。** 它提供的是 dialect 机制与可复用的 pass 基础设施，让「高层语义 → 低层语义」可以分成多步、每步都可验证：`tensor` → `linalg`（结构化算子）→ `scf`/`affine`（循环）→ `vector`/`gpu`（并行与线程）→ `llvm`（机器层），中间还有 bufferization（值语义转缓冲语义）。Triton、IREE、部分 TVM 组件都建在这套机制上。**理解 dialect 的价值不在名词，而在「每一层只暴露该层该管的信息」**——这与第 1 章的前端/中端/后端分工是同一条原则，只是粒度更细。

**生态位补一句现实**：`torch.compile` 是这条链的典型组合——Dynamo 把 Python 字节码捕获成图（带 guard，形状/类型变了就重编译），Inductor 再把图降到 Triton kernel（GPU）或 C++/OpenMP（CPU）。**这正是"图 DSL 与 kernel DSL 在同一栈里共存"的现实样本**：图侧做融合，kernel 侧做线程与访存。

**判据（四个，缺一不可）**：① 数值正确——与 eager 或参考实现逐元素对拍，注意低精度与归约顺序带来的差异；② 性能——报**相对基准的百分比**（cuBLAS/cuDNN/手写 kernel），不报绝对 TFLOPS；③ 可移植性——支持几个后端，换后端要不要重写 schedule/kernel；④ 编译与调优时间——自动调优可能要跑几百上千个配置，这个成本必须计入。

**最小例子**

同一个 elementwise add，两种写法对比"谁决定线程映射"：

```python
# CUDA：线程映射、边界判断、访存合并全由人写
# __global__ void add(const float* x, const float* y, float* o, int n) {
#   int i = blockIdx.x * blockDim.x + threadIdx.x;
#   if (i < n) o[i] = x[i] + y[i];
# }

# Triton：只描述一个 block 算什么，线程切分交给编译器
import triton, triton.language as tl

@triton.jit
def add_kernel(x_ptr, y_ptr, out_ptr, n, BLOCK: tl.constexpr):
    pid  = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < n
    x = tl.load(x_ptr + offs, mask=mask)
    y = tl.load(y_ptr + offs, mask=mask)
    tl.store(out_ptr + offs, x + y, mask=mask)

add_kernel[(triton.cdiv(n, BLOCK),)](x, y, out, n, BLOCK=1024)
```

TVM 侧则是"计算不变、只改 schedule"：

```python
from tvm import te
A = te.placeholder((M, N), name="A")
B = te.placeholder((N, K), name="B")
kk = te.reduce_axis((0, N), name="kk")
C  = te.compute((M, K), lambda i, j: te.sum(A[i, kk] * B[kk, j], axis=kk), name="C")

s = te.create_schedule(C.op)
xo, yo, xi, yi = s[C].tile(C.op.axis[0], C.op.axis[1], 32, 32)  # 分块
s[C].vectorize(yi)                                              # 内层向量化
# 变性能不动上面的计算式：换 tile 大小、换 reorder、绑到 GPU 的 block/thread 轴
```

**同一个 `C` 的定义可以生成几十种性能不同的实现**——这就是 Halide 提出的 algorithm/schedule 分离，也是 TVM 与 CUDA 最根本的差别。

**面试高频问法**

1. **「Triton 和 CUDA 差在哪？为什么它能让普通人写出接近手写的 kernel？」** → 考点是"谁决定线程与访存"。答法：CUDA 里线程映射、共享内存、同步、合并访存都由人写；Triton 只要求描述一个 block 的计算，编译器负责把这些决定下来（block 到 warp 的切分、共享内存分配、访存布局、以及 `num_stages` 控制的软件流水线）。所以它对**常规形态**的 kernel 极有效，对需要非常规布局的 kernel 仍然要回 CUDA。判据是相对 cuBLAS/cuDNN 的百分比，不是"能跑"。
2. **「TVM 的 schedule 和 LLVM 的 pass 是同一种东西吗？」** → 考点是分层。答法：不是一层。schedule 作用在**张量计算的定义**上，改变并行与访存结构（切块、绑定、向量化、放共享内存）；pass 作用在**指令级 IR** 上，改变指令序列（化简、指令选择、寄存器分配）。前者决定"算什么形状的并行"，后者决定"用哪条指令算"。
3. **「为什么 XLA 能做整图融合，LLVM 做不了？」** → 考点是编译单元。答法：融合是**图的变换**——把两个算子的循环体合成一个 kernel，需要看到算子级的语义与形状；LLVM 看到的是一条指令流，算子边界已经消失，没有这个自由度。反过来说，XLA 也做不了 LLVM 那层的寄存器分配与指令调度，因为它降到后端就把活交出去了。
4. **「自动调优（AutoTVM/Ansor）到底在搜什么？」** → 考点是知不知道代价在哪。答法：搜的是 schedule 的参数空间——tile 大小、循环顺序、绑到哪个轴、是否向量化、是否 unroll；用代价模型先筛，再实测确认。代价是真金白银的编译时间（可能几百上千个配置），所以实践中会缓存、会剪枝，也只对热点算子做。
5. **「MLIR 到底是什么，为什么大家都在用它？」** → 考点是分清基础设施与产品。答法：它不是编译器，是"多级 IR + 可复用 pass 基础设施"的框架，价值在于允许**渐进下降**：每一层只暴露该层该管的语义（`linalg` 管结构化算子、`scf` 管循环、`gpu` 管线程），于是每层都能独立优化与验证。代价是栈更长、调试要跨多层 IR——这与第 1 章"分三段"的取舍是同一个道理，只是粒度更细。
6. **「同一个模型，为什么换 GPU 之后性能掉一半？」** → 考点是调度与硬件的耦合。答法：schedule/kernel 里写死的参数（tile 大小、共享内存容量、warp 数、流水级数）是针对某代硬件的容量与延迟调的；换卡后 SM 数、共享内存大小、寄存器数变了，原来的配置要么装不下、要么并行度不足。所以 DSL 的价值不是"自动变快"，而是**把重新调参的成本降下来**。
