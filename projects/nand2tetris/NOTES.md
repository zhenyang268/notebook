# nand2tetris · 从与非门到俄罗斯方块

> **工程线（兴趣向，非考试范围）**。本文件不承担复习任务。
> 用 NAND 搭出 CPU、汇编器、VM、编译器和操作系统。
>
> **单向引用约定**：本文提到考点时**只写 KP 号与考点名**，不复制 `exam/` 的正文；
> `exam/` 的文件里也不出现本文件的工程名。两边互不依赖，只共享主键。

## 对位考点（单向引用）

| 本文段落 | 对应 KP |
|---|---|
| Hack 指令格式 | `408-CO-0401` 指令格式 |
| ALU 的六个控制位 | `408-CO-0205` 乘除运算与 ALU |
| 冯·诺依曼 vs 哈佛 | `408-CO-0102` 层次结构 |
| 单周期数据通路 | `408-CO-0503` 数据通路 |
| 内存映射 I/O | `408-CO-0701` I/O 系统概述 |
| ch12 堆管理与 free list | `408-OS-0301` 内存管理基础 |

---

## 0 怎么读这个文件

- **§1 总纲**：回答"这 12 章到底在造什么、先造哪个"。含本地子仓体检结果 —— **动手前必须先看 §1.6，结论会改变你的复习策略**。
- **§2 设计理念 ★**：回答你最关心的那个问题：为什么"从 NAND 出发"这件事在工程上成立，以及每一层的抽象契约是怎么被切出来的。**这是整个项目最值钱的部分，别跳过。**
- **§3 逐层详细设计**：ch1–ch12 每层六件套 —— 交付物（真实路径）/ 核心问题 / 关键路径 / **实现要点（含可直接照做的 HDL、汇编、Jack 片段）** / 易错点清单 / 设计理念 / 验收命令。**这是动手时直接对着抄的一章。**
- **§4 Turing Complete 对照**：同一个"从零造机"命题的另一种解法，它补上了 nand2tetris 缺的那一维。
- **§5 408 对照总表**：把这个项目挂回考研计算机组成原理/OS 的考点上（这是本仓视角）。含 **§5.5 反查表**（408 考点 → nand2tetris 实物记忆锚点，刷题时对着用）。
- **§6 复习执行方案**：时间预算、重建顺序（不是 1→12 顺着做）、验收命令。
- **§8 求职视角**：简历写法（中英模板）、面试高频题（按层给"面试官想听什么"）、与工业界的边界、五条延伸路径 —— **初试（12 月下旬）之后才用，现在先存着**。

---

## 1 总纲：这个项目在造什么

### 1.1 一句话

> **从一只 NAND 门出发，一路造到能跑俄罗斯方块的整机 + 语言栈：门电路 → ALU → 寄存器/RAM → CPU → 汇编 → 汇编器 → 虚拟机 → Jack 语言 → 编译器 → 操作系统。**

关键措辞：它不是"学数字电路"，也不是"学编译器"，它是**一次把抽象层次从下到上完整走一遍**的全程记录。"手写一个 TCP"那类课是"横向替换一个现成系统的某一层"，nand2tetris 是"纵向自己把每一层都造出来"。

### 1.2 分层图（谁站在谁头上）

```
   ============================ 软件栈（Part II, ch7-12）============================
   [12] 操作系统 Jack OS     Math / Memory / Screen / Keyboard / String / Output / Array / Sys
   [11] 编译器 II  代码生成   Jack AST -> VM 字节码（符号表 / 表达式 / 数组 / 对象 / 方法调用）
   [10] 编译器 I   语法分析   Jack 源码 -> XML 语法树（Tokenizer + Parser）
    [9] 高级语言 Jack        面向对象（class/field/static/method/constructor），跑在 VM 上
   --------------------------------------------------------------------------------
    [8] 虚拟机 II  函数调用   call / function / return（栈帧 + calling convention）
    [7] 虚拟机 I   栈运算     push / pop + 算术逻辑 + 内存段（local/argument/this/that/...）
   --------------------------------------------------------------------------------
    [6] 汇编器                Hack asm -> 16-bit 二进制（符号表两遍扫描）
   ============================ 硬件栈（Part I, ch1-5）==============================
    [5] 整机 Computer         CPU + Memory(RAM16K/Screen/Keyboard) + ROM32K 三件套连线
    [4] 机器语言              Hack 汇编：A-指令 / C-指令，只有 D、A 两个寄存器
   --------------------------------------------------------------------------------
    [3] 时序逻辑              DFF -> Bit -> Register -> RAM8/64/.../16K -> PC
    [2] 布尔运算              HalfAdder / FullAdder / Add16 / Inc16 / ALU
    [1] 布尔逻辑              Nand -> Not/And/Or/Xor/Mux/DMux（唯一的公理）
   ============================ 唯一公理 ==========================================
    [0] Nand                  由硬件模拟器直接提供，不再往下拆
```

图上数一数：从 Nand 到"屏幕上有个方块在弹"，中间隔了 **11 次"接口定义"**。nand2tetris 的整套教学就是让你亲手签下这 11 份契约。

### 1.3 建造顺序 = 运行顺序（和"先上层后下层"的课相反，这是它最大的不同）

| 项目 | 建造顺序 vs 运行顺序 | 含义 |
|---|---|---|
| **先上层后下层的课**（如手写 TCP） | **相反**：先竖起 TCP，再回头补以太网/ARP | 上层可先用"假下层"单测 |
| **Nand2Tetris** | **相同**：严格自底向上，ch N 只用 ch < N 的成品 | 下层是上层**唯一**的实现材料 |

为什么它敢这样造？因为**每一层的"下层替身"就是官方给的内建实现**：你在写 ch2 的 ALU 时，ch1 的 Mux16 可以用官方 `builtInChips/Mux16.hdl` 顶着；写 ch12 的 OS 时，VM Emulator 自带完整的 OS 实现，你写好的那个类会**短路（shortcut）掉内建版本**（官方 project12 原话）。

**教学含义**：任何一层挂掉，都**只会**是这一层自己的 bug（下层已被官方实现保证正确）。这是它比"先竖上层再补下层"更适合"零基础一路推到底"的原因，也是它最容易被"照抄规范"糊弄过去的原因。

### 1.4 十二章全景表

> 本地文件名经 `ls` / `grep` 核实；"本地状态"一列的含义见 §1.6。

| 章 | 主题 | 你交付什么 | 最硬的一个概念 | 408 对应 | 本地状态 |
|---|---|---|---|---|---|
| 1 | 布尔逻辑 | 15 个 `.hdl`（Not/And/Or/Xor/Mux/DMux 及 16 位/多路版） | **NAND 的函数完备性** | 01-数据表示与编码 | 骨架（15/15 未实现） |
| 2 | 布尔运算 | HalfAdder / FullAdder / Add16 / Inc16 / **ALU** | **补码让加减法共用一套电路**；ALU 的 6 个控制位 | 02-运算与ALU | 骨架（5/5） |
| 3 | 时序逻辑 | Bit / Register / RAM8→RAM16K / PC | **DFF 是唯一的"时间"来源**；反馈回路 | 04-内存（存储元件）、07-CPU（PC） | 骨架（8/8） |
| 4 | 机器语言 | `Mult.asm` / `Fill.asm` | **内存映射 I/O**（键盘/屏幕当内存读写） | 06-指令系统与汇编 | 骨架（2/2） |
| 5 | 计算机体系 | CPU.hdl / Memory.hdl / Computer.hdl | **指令译码 = 把 16 位拆成字段去控数据通路** | 07-CPU与数据通路、00-概述 | 骨架（3/3） |
| 6 | 汇编器 | 任意语言的 assembler（Python/Java 均可） | **两遍扫描**（先建符号表，再翻译） | 06-指令系统与汇编 | 源码不在库 |
| 7 | 虚拟机 I | VMTranslator 前半：栈运算 + 内存段 | **栈式 VM 是"中间语言"的祖宗**（JVM 的简化版） | 06（过程调用/运行时栈） | 源码不在库 |
| 8 | 虚拟机 II | VMTranslator 后半：程序流 + **函数调用** | **calling convention：栈帧约定是软件契约，不是硬件规定** | 06（栈帧）、10（运行时栈） | 源码不在库 |
| 9 | Jack 语言 | 一个 Jack 应用（书里建议写游戏） | **对象 = 一块内存 + 一个方法表（无继承无多态）** | 06 / 23 | **有实现**（8 个程序） |
| 10 | 编译器 I | Tokenizer + Parser，输出 XML | **语法分析 = 递归下降**（文法即代码结构） | 06 / 23 | 有 .xml 输出，源码不在库 |
| 11 | 编译器 II | 代码生成：Jack → VM | **表达式求值用栈，控制流用标签** | 06 / 23 | 同上 |
| 12 | 操作系统 | 8 个 OS 类（Jack 写） | **语言运行时 = OS 的一部分**（`*` `/` 就是 OS 函数） | 04-内存（堆管理）、09-总线与IO | 骨架（8/8） |

**最值钱的三章（复习 ROI 排序）**：**ch5（整机）> ch8（calling convention）> ch12（堆管理 + 内存映射 I/O）**。理由见 §6.1。

### 1.5 关键路径（复习按这个顺序走，不要 1→12）

```
第一梯队（必做，重建"整机"这条主心骨）
  ch1 (选 5 个门, 别全做) -> ch2 (ALU 是重点, 加法器可跳过细节)
      -> ch3 (Register/PC 必做, RAM 层级做 RAM8 即可, 上面是递归复制)
      -> ch5 (CPU + Memory + Computer) ★ 全项目最高价值点

第二梯队（把"软件栈为什么长这样"讲通）
  ch4 (只写 Mult.asm) -> ch7 (VM 栈运算) -> ch8 (call/function/return) ★
      -> ch6 (汇编器, 可与 ch7/8 并行, 独立性强)

第三梯队（编译器与 OS，量大但概念密度低）
  ch12 (Memory.alloc + Output 字形位图 + Screen 位操作) ★ 命中 408 最多
      -> ch9/10/11 (Jack 应用与编译器, 有 ch8 打底就可推进)
```

**为什么 ch5 排在最前**：它是**唯一一处你必须同时面对"指令编码、数据通路、时序、内存映射"四件事**的地方。做完 ch5，408 组成原理的 CPU 数据通路、指令周期、微操作序列基本就不需要背了。

### 1.6 本地子仓体检结果 ★（动手前先看这块）

这个必须说清楚，否则你会按错误的起点开跑：

| 检查项 | 结果 |
|---|---|
| `git log` | 只有 1 次 commit `ab4b9b0 init`（2024-04-18），**没有任何"实现"提交** |
| `projects/1,2,3,5` 共 31 个 `.hdl` | **全部仍是官方骨架**，每个文件都留着 `//// Replace this comment with your code.` |
| `projects/4/{Mult,Fill}.asm` | 同样是骨架（10–11 行，只有注释） |
| `projects/12/*.jack`（8 个 OS 类） | 骨架，只有类与函数签名（Math.jack 49 行全是空函数体） |
| `projects/6/*.asm`（Add/Max/Rect/**Pong**） | **是官方提供的参考汇编，不是你的作业**：Pong.asm 28378 行，文件头注释写明"由 Jack → VM → ASM 全链自动生成，仅作第 6 章汇编器的测试输入" |
| `projects/7,8` | 只有官方测试的 `.vm` 与 `.tst/.cmp`，**VMTranslator 源码不在库** |
| `projects/9` | **有实际 Jack 代码**：Average / ComplexArrays / ConvertToBin / Fraction / HelloWorld / List / Pong / Square（含 `List.jack` 的递归 `dispose()`） |
| `projects/10,11` | 有官方测试 `.jack` 与编译器产物 `.xml`，**编译器源码不在库** |
| `tools/` | 官方工具链齐全：HardwareSimulator / CPUEmulator / VMEmulator / Assembler / JackCompiler（均为 `.sh`，需 Java 运行时）+ `builtInChips/`（内建芯片）+ `builtInVMCode/`（内建 OS） |

**结论（重要，别绕）**：**当年的实现代码没有留在这个仓里**，库里保存的是"官方原始包 + 第 9 章的 Jack 应用"。所以这次复习的正确姿势不是"翻旧代码回忆"，而是：

1. **硬件层（ch1-5）当作重做**：骨架就在 `projects/` 里，直接用 HardwareSimulator 跑 `.tst` 验收。好消息是这部分量小（每个芯片平均 7 个 part，官方 CACM 论文口径）。
2. **ch6/7/8/10/11 的工具源码缺失**：这四章的交付物是"你用 Python/Java 写的翻译器"，不在库就无法"回忆"，只能**重写或与官方方案对读**。冲刺期建议只重写 **ch7+ch8 的 VMTranslator**（约 400–600 行 Python，概念密度最高），汇编器与编译器只做**设计复盘不动手**。
3. **ch12 命中 408 考点最密**（堆管理 ↔ 内存管理、字形位图 ↔ 显示 I/O），骨架在 `projects/12/`，值得真写。
4. 第 9 章的 Jack 代码是这次**唯一可复盘的旧资产**，`List.jack` 的递归 dispose 尤其值得重看（它直接暴露 Jack 的对象模型）。

---

## 2 设计理念 ★

### 2.1 唯一公理：NAND 完备性

`Nand(a,b) = !(a & b)`。从它出发能造出一切的根据是两条：

1. **Not**：`Not(x) = Nand(x, x)` —— 把两个输入短接。
2. **And**：`And(a,b) = Not(Nand(a,b))`。
3. 有了 Not + And，布尔代数的 **{And, Or, Not}** 完备集就齐了，于是任意布尔函数（真值表）都能造出来 —— 这就是 Mux、DMux、加法器、ALU 全部可构造的根据。

**换个角度看**：NAND 完备性告诉你"计算能力"只需要一个起点；而后面 11 层做的全部是**同一件事的重复**：**用已经造好的东西，定义出更强的接口，然后忘掉实现**。

### 2.2 抽象-实现契约（stub + tst + cmp）—— nand2tetris 的教学核心

官方 CACM 论文把这件事讲得很直白：

> "Before implementing a chip, one can load a **built-in chip implementation** into the hardware simulator and experiment with it."

每一层的交付仪式都一样：

```
[1] 官方给出 stub 文件（只有芯片签名 + 注释说明功能）   <- 你要填的部分
[2] 官方给出 .tst 测试脚本（驱动输入、比对输出）
[3] 官方给出 .cmp 正确输出文件
[4] 你写实现 -> HardwareSimulator 跑 .tst -> 与 .cmp 比对
[5] 在此之前，你可以先加载 builtInChips 里的成品，"玩"一遍它的行为
```

**这就是"先理解契约再实现"的工业化版本**：规范精确到"每个时钟周期每个引脚的电平"，学生没有设计自由，也就没有"我不知道该做成什么样"的焦虑。

**代价（必须点出来）**：你会丧失两个能力 —— **自己提需求**和**自己定接口**。Turing Complete（§4）正好补这一块。

### 2.3 极简主义：Hack 只有两个寄存器、两种指令

| 设计选择 | Hack 的做法 | 为什么这样 | 代价 |
|---|---|---|---|
| 寄存器 | 只有 **D**（数据）和 **A**（地址/数据） | 寻址与计算分离，A 兼作"地址寄存器"和"立即数寄存器" | 做一次 `RAM[i] = RAM[i]+1` 要好几条指令 |
| 指令格式 | 只有 2 种：A-指令 `0vvv...(15位)`、C-指令 `111a cccccc ddd jjj` | 译码极简：`i[15]==0` 就是 A-指令 | 无立即数运算、无多操作数指令 |
| comp 表 | 用 1 个 **a 位**在 A 和 M(=RAM[A]) 之间切换 | 一张 18 项的表覆盖两种数据源，省掉一整组操作码 | 想同时用 A 和 M 做运算做不到（必须先 `D=M`） |
| 标志位 | **没有标志寄存器**，跳转直接看 ALU 输出的 `zr` / `ng` | 组合逻辑直通，无状态残留 | 无法"先算再判断别的事" |
| 跳转 | 无条件跳转 = 先把地址装进 A，再 `0;JMP` | 复用 A 寄存器，不新增指令 | 跳转前必须先写 A（**这是汇编编程最大的坑**） |

**设计理念一句话**：**指令集的设计目标不是"好用"，而是"译码电路最小"**。Hack 是一本反面教材式的"最小 ISA"，正因为小，你才能在一个下午里把它从门电路一路连到 CPU —— 这叫**可完成性优先于优雅性**。

### 2.4 哈佛架构：指令内存与数据内存分开

Hack 的 ROM32K（指令）和 RAM16K+（数据）是**两条独立的地址空间**：

- 好处：取指令和读数据不冲突，单周期就能完成"取指 + 执行"；CPU 里不用做总线仲裁。
- 代价：**没有"把指令当数据改"的能力**（无自修改代码、也无法从磁盘加载程序 —— ROM 是只读的，程序烧进去）。
- 408 考点连接：这正是"冯·诺依曼结构 vs 哈佛结构"的实物对照。考研里考"冯·诺依曼的核心思想是**指令与数据同等地位、共存于同一存储器**"，而 Hack 明确**不是**这个结构 —— 记住这个反例，选择题不会错。

### 2.5 内存映射 I/O（Memory-Mapped I/O）—— 一个设计解决三个问题

Hack 把外设做成"一段内存地址"：

| 地址 | 用途 | 宽度 |
|---|---|---|
| `0..15` | R0–R15 虚拟寄存器（SP=R0, LCL=R1, ARG=R2, THIS=R3, THAT=R4 都在里面） | 16 字 |
| `16..255` | 静态变量区（VM 的 static 段） | |
| `256..2047` | **全局栈**（VM 的栈，SP 从 256 起） | |
| `2048..16383` | **堆**（Jack 对象与数组，`Memory.alloc` 管这一块） | 14336 字 |
| `16384..24575` | **屏幕**：512×256 像素，每行 32 个 16 位字 → 8192 字 | 8K 字 |
| `24576` | **键盘**：一个字，存当前按键的 ASCII/扫描码，无按键时为 0 | 1 字 |

**设计理念**：CPU 不需要"输入/输出指令"。`Screen.drawPixel` 和 `Keyboard.readChar` 在 OS 层被实现成 `Memory.poke(16384 + ..., ...)` 与 `Memory.peek(24576)` —— **编址统一，就不需要两套指令**。这是 408 "统一编址 vs 独立编址"（I/O 端口编址）的直接实物。

**顺带一个必考的细节**：屏幕是 **1 bit = 1 像素**，一个 16 位字管 16 个水平像素。所以：

- 画**水平线**很快（同一个字里改几个 bit，或者算掩码一次搞定）；
- 画**竖直线**要访问 32 个字（每行一个字，行间距 32 字）—— 官方论坛经验：竖线算法与横线算法必须分开写。

### 2.6 为什么要在中间插一层栈式 VM（ch7-8）

这是整个软件栈里最"多余"、也最精妙的一层。它的存在理由有两条：

1. **跨平台**：VM 代码不知道自己在什么机器上跑。同一份 `.vm`，翻译成 Hack 汇编能在你的 CPU 上跑，理论上翻译成 x86 也能跑（JVM 干的就是这事）。
2. **让编译器变简单**：Jack 编译器只需要输出"栈操作"，不用管 Hack 只有两个寄存器、不用做寄存器分配。**寄存器分配的难题被下推给了 VMTranslator** —— 而 VMTranslator 用的是"永远用栈顶 + R13-R15 三个临时寄存器"这种笨办法，简单到不会出错。

**这就是"用一层间接性换取每一层的简单"**。设计理念一句话：**当你发现某一层同时要做两件难事（翻译语言 + 管理寄存器），就再插一层，让每层只做一件。**

### 2.7 编译器的两遍结构（ch10 → ch11）

```
Jack 源码 -> [ch10] Tokenizer -> Parser -> XML 语法树（看得见的结构）
         -> [ch11] SymbolTable + VMWriter -> VM 字节码
```

- **ch10 只做语法**：输出 XML，可以肉眼比对（官方给 `.xml` 参考）。这一层的价值是**让你确信"解析对了"**，不必等到代码生成才发现括号错位。
- **ch11 只做语义与代码生成**：符号表分两层（class 级放 static/field，subroutine 级放 local/argument），**作用域就是这张表的 push/pop**。

**设计理念**：**把"我读懂了"和"我翻译了"拆成两个可单独验收的产物**。这和 §2.2 的 stub/tst/cmp 是同一个思路：**任何一步都要有能独立验证的中间结果**。

### 2.8 OS 就是语言运行时（ch12 最反直觉的一点）

在 Jack 里写 `x * y` 和 `a[3]`：

- `x * y` → 编译器**直接生成 `call Math.multiply`**（没有乘法指令，电路里也没乘法器）；
- `a[3]` → 编译器生成 `call Memory.alloc`（`Array.new`）与指针加法；

**所以 OS 不是"跑在应用之下的服务"，它是语言的一部分**。官方原话：OS "can also be viewed as an **extension of a high-level programming language**"。

推论（这条最容易在复习时漏掉）：**`Math.multiply` 必须用 O(n) 的移位加法实现，不能用循环加 y 次**（那是 O(y)，y=30000 时卡死）。同理 `divide` 用二分/长除，`sqrt` 用牛顿或二分。**性能约束直接决定了算法选择** —— 这是 nand2tetris 里少有的"性能"维度。

### 2.9 故意的简化清单 —— 这是最有价值的"现实边界"素材

nand2tetris 不做这些（不是忘了，是故意的）：

| 不做 | 现实里是什么 | 408 考点 |
|---|---|---|
| 流水线 | 单周期，取指-执行一步到位 | 08-流水线（结构/数据/控制冒险） |
| Cache / 存储层次 | 直接连 RAM，无命中率概念 | 03-存储层次与Cache |
| 虚拟内存 / 页表 / TLB | 裸物理地址 | 04-内存与虚拟内存 |
| 中断 / DMA | 键盘只能靠轮询（`Keyboard.keyPressed` 反复读 24576） | 09-总线与IO |
| 特权级 / 系统调用陷入 | OS 函数就是普通函数调用，无用户态内核态之分 | 00-概述、10-进程 |
| 多进程 / 文件系统 / shell | 单程序跑到底 | 10/11/05 |
| 浮点 | 只有 16 位补码整数 | 01/02 |

**这份清单比课程本身更值钱**：它精确地画出了"为了在一个学期内做完，我们砍掉了什么"。复习时对照着看，你立刻知道 408 里哪些知识点**不能**靠这个项目覆盖（流水线、Cache、虚存、中断、浮点 —— 全是 408 的重头戏）。

### 2.10 一句话总结这个设计理念

> **每一层只做一件事，每层都用"上一层的接口"而不是"上一层的实现"来思考；接口定得越窄，上层越自由，下层越容易验证。**

nand2tetris 把这条原则执行得极端彻底 —— 彻底到它宁可让 Hack 只有 2 个寄存器、没有乘法指令、没有中断，也要保证**每一层都能在一个下午里被一个人做完并且验证通过**。

---

## 3 逐层详细设计（12 层全展开）

> **本轮起 §3 是完整设计文档**，每层六件套：**交付物（真实路径）/ 核心问题 / 关键路径 / 实现要点（含可直接照做的片段）/ 易错点清单 / 设计理念 / 验收命令**。
> 片段里的 HDL 语法是 nand2tetris 官方 HDL：`CHIP X { IN ...; OUT ...; PARTS: <芯片名>(引脚=连线, ...); }`；`true/false` 是常量；`x[0..7]` 是子总线。
> **给的是关键片段与实现方案，不是逐字答案** —— 目的是让你在骨架上 10 分钟内重建，而不是替你做。

### 3.1 [ch1] 布尔逻辑

**交付物**：`projects/1/` 下 15 个芯片 —— `Not / Not16 / And / And16 / Or / Or16 / Or8Way / Xor / Mux / Mux16 / Mux4Way16 / Mux8Way16 / DMux / DMux4Way / DMux8Way`
**核心问题**：从一只 Nand 出发，怎么把"选择"这件事（Mux/DMux）造出来 —— 因为它后面会出现在 CPU 的每一个角落。

#### 关键路径（这个顺序做，每一步都能单测）

1. `Not` → `And` → `Or` → `Xor`（四个基本门，各自有 `.tst`）
2. `Mux` → `DMux`（**这一对是重点**，地址译码与数据选择的祖先）
3. 16 位版：`Not16 / And16 / Or16 / Mux16` —— 同一芯片复制 16 份，引脚用总线一次性连（`a=a` 即可，不必逐位写）
4. 多路版：`Mux4Way16` → `Mux8Way16`、`DMux4Way` → `DMux8Way`（**两级级联**）
5. `Or8Way`（8 输入或，树形结构，ch2 的 zr 判定要用）

#### 实现要点

```hdl
// Not：把两个输入短接
CHIP Not {
    IN in;
    OUT out;
    PARTS:
    Nand(a=in, b=in, out=out);
}

// And：Nand 取反
CHIP And {
    IN a, b;
    OUT out;
    PARTS:
    Nand(a=a, b=b, out=w1);
    Not(in=w1, out=out);      // 或 Nand(a=w1, b=w1, out=out)
}

// Or：德摩根  a|b = !(!a & !b)
CHIP Or {
    IN a, b;
    OUT out;
    PARTS:
    Nand(a=a, b=a, out=na);
    Nand(a=b, b=b, out=nb);
    Nand(a=na, b=nb, out=out);
}

// Xor：a 或 b，但不能同时（Nand 就是"不同时为 1"）
CHIP Xor {
    IN a, b;
    OUT out;
    PARTS:
    Not(in=a, out=na);
    Not(in=b, out=nb);
    And(a=a,  b=nb, out=w1);
    And(a=na, b=b,  out=w2);
    Or(a=w1, b=w2, out=out);
}

// Mux：数据通路上的 if —— 整个计算机里最重要的一个门
CHIP Mux {
    IN a, b, sel;
    OUT out;
    PARTS:
    Not(in=sel, out=ns);
    And(a=a, b=ns, out=w1);
    And(a=b, b=sel, out=w2);
    Or(a=w1, b=w2, out=out);
}

// DMux：Mux 的反向 —— 把 1 路输入按 sel 分配到 2 路（地址译码的祖先）
CHIP DMux {
    IN in, sel;
    OUT a, b;
    PARTS:
    Not(in=sel, out=ns);
    And(a=in, b=ns, out=a);
    And(a=in, b=sel, out=b);
}

// Mux4Way16：两级级联（sel=00->a, 01->b, 10->c, 11->d；sel[0] 是低位）
CHIP Mux4Way16 {
    IN a[16], b[16], c[16], d[16], sel[2];
    OUT out[16];
    PARTS:
    Mux16(a=a, b=b, sel=sel[0], out=lo);   // 低组：sel[0] 决定 a/b
    Mux16(a=c, b=d, sel=sel[0], out=hi);   // 高组：sel[0] 决定 c/d
    Mux16(a=lo, b=hi, sel=sel[1], out=out);// 再由 sel[1] 选组
}

// Mux8Way16：三片 Mux4Way16? 不 —— 两片 Mux4Way16 + 一片 Mux16（sel[0..1] 组内，sel[2] 选组）
```

**16 位版偷懒写法**：`Not16` 里 16 个 `Not(in=a[i], out=out[i])`（i=0..15）。`Mux16` 里 16 个 `Mux(a=a[i], b=b[i], sel=sel, out=out[i])`。官方不评分门数，写清楚就行。

#### 易错点清单

1. ★ **内部引脚必须先声明后使用**：HDL 里 `w1`、`ns` 这类中间连线不用显式声明类型，但**必须先在某个 part 的输出端出现**（不能被两个 part 同时驱动，也不能没被驱动就被读）。
2. ★ **一个内部引脚只能被一个 part 驱动**：两个 part 的 `out=w1` 会报 "pin may only be fed by one chip part"。
3. **子总线的位序**：`sel[2]` 表示 2 位总线，其中 `sel[0]` 是**最低位**。真值表 00→a、01→b、10→c、11→d 时，`sel[0]` 管组内选择 —— 顺序搞反 `.tst` 会直接红。
4. **多路芯片用级联，不要写分支**：Mux8Way16 = 2 片 Mux4Way16（sel[0..1]）+ 1 片 Mux16（sel[2]）；DMux8Way = 3 级 DMux。
5. `Or8Way` 是**唯一的 8 输入门**，ch2 判断 16 位全零要靠它拼。
6. 芯片名与文件名必须一致，且 `CHIP` 里的引脚名要与 `.tst` 一致（照 stub 抄，不要自己改名）。

#### 设计理念

**Mux 与 DMux 是这台计算机里"选择"的唯一载体**。往下看你会发现：RAM 选哪一行 = DMux；CPU 里"要不要跳转"= Mux；ALU 选加还是与 = Mux。**整台机器其实就是一堆 Mux 加上少量算术** —— 理解了这一点，ch5 的 CPU 就只是连线练习。

#### 验收

```bash
cd ~/develop/learning/learning-408/nand2tetris
bash tools/HardwareSimulator.sh projects/1/Mux.tst
bash tools/HardwareSimulator.sh projects/1/Mux4Way16.tst
# 全部 15 个各有 .tst，一次跑完即可；GUI 里 Load Script -> Run -> 与 .cmp 比对
```

---

### 3.2 [ch2] 布尔运算与 ALU

**交付物**：`projects/2/` —— `HalfAdder / FullAdder / Add16 / Inc16 / ALU`
**核心问题**：如何把 **18 种运算**塞进一块 ALU，并且只用 6 个控制位。

#### 关键路径

1. `HalfAdder`（sum = a Xor b，carry = a And b）
2. `FullAdder`（两个半加器：先加 a+b，再把进位与 c 相加；两个 carry 取 Or）
3. `Add16`（**行波进位**链：16 个 FullAdder 串起来；最低位可用 HalfAdder，因为没有 carry-in）
4. `Inc16`（**别再做加法器链**）
5. `ALU`（6 控制位两级变换 + Add16/And16 二选一 + 取反 + zr/ng）

#### 实现要点

```hdl
CHIP HalfAdder {
    IN a, b;              // 两个 1 位输入
    OUT sum, carry;
    PARTS:
    Xor(a=a, b=b, out=sum);
    And(a=a, b=b, out=carry);
}

CHIP FullAdder {
    IN a, b, c;           // c = 来自低位的进位
    OUT sum, carry;
    PARTS:
    HalfAdder(a=a, b=b, sum=s1, carry=c1);
    HalfAdder(a=s1, b=c, sum=sum, carry=c2);
    Or(a=c1, b=c2, out=carry);
}

// Add16：行波进位（ripple carry）—— 慢，但这是教学取舍（性能维度见 §4.3）
// 写法：16 个 FullAdder，第 0 位用 HalfAdder，carry 逐级向上串

CHIP Inc16 {
    IN in[16];
    OUT out[16];
    PARTS:
    Add16(a=in, b[0]=true, b[1..15]=false, out=out);   // 常量 1：b[0]=true，其余 false
}
```

**ALU 的实现（本章核心）**：

```hdl
CHIP ALU {
    IN  x[16], y[16], zx, nx, zy, ny, f, no;
    OUT out[16], zr, ng;

    PARTS:
    // 第 1 级：改造 x（先置零，再取反）
    Mux16(a=x,   b=false, sel=zx, out=x1);
    Not16(in=x1, out=nx1);
    Mux16(a=x1,  b=nx1,  sel=nx, out=x2);

    // 第 2 级：改造 y（同上）
    Mux16(a=y,   b=false, sel=zy, out=y1);
    Not16(in=y1, out=ny1);
    Mux16(a=y1,  b=ny1,  sel=ny, out=y2);

    // 第 3 级：f 选"加"还是"与"
    Add16(a=x2, b=y2, out=addxy);
    And16(a=x2, b=y2, out=andxy);
    Mux16(a=andxy, b=addxy, sel=f, out=o1);

    // 第 4 级：no 决定是否取反
    Not16(in=o1, out=no1);
    Mux16(a=o1, b=no1, sel=no, out=out, out[15]=ng);   // ng = 最终 out 的符号位

    // zr：16 位全零判定（官方芯片库只有 Or8Way，需两片拼 16 路）
    Or8Way(in=out[0..7],  out=or1);
    Or8Way(in=out[8..15], out=or2);
    Or(a=or1, b=or2, out=orout);
    Not(in=orout, out=zr);
}
```

**控制位速查（背这张表，ALU 就通了）**：

| 想要 | zx | nx | zy | ny | f | no | 原理（补码恒等式 `!z = -z-1`） |
|---|---|---|---|---|---|---|---|
| `0` | 1 | 0 | 1 | 0 | 0 | 0 | `0 & 0` |
| `1` | 1 | 1 | 1 | 1 | 1 | 1 | `(-1)+(-1) = -2`，取反得 `1` |
| `-1` | 1 | 1 | 1 | 1 | 0 | 0 | `(-1) & (-1) = -1` |
| `x` | 0 | 0 | 1 | 1 | 0 | 0 | y=-1，`x & (-1) = x` |
| `y` | 1 | 1 | 0 | 0 | 0 | 0 | x=-1，`(-1) & y = y` |
| `!x` | 0 | 1 | 1 | 1 | 0 | 0 | `!x & (-1) = !x` |
| `!y` | 1 | 1 | 0 | 1 | 0 | 0 | `(-1) & !y = !y` |
| `-x` | 0 | 0 | 1 | 1 | 1 | 1 | `x + (-1) = x-1`，取反 = `-x` |
| `-y` | 1 | 1 | 0 | 0 | 1 | 1 | `(-1) + y = y-1`，取反 = `-y` |
| `x+1` | 0 | 1 | 1 | 1 | 1 | 1 | `!x + (-1) = -x-2`，取反 = `x+1` |
| `y+1` | 1 | 1 | 0 | 1 | 1 | 1 | `(-1) + !y = -y-2`，取反 = `y+1` |
| `x-1` | 0 | 0 | 1 | 1 | 1 | 0 | `x + (-1)` |
| `y-1` | 1 | 1 | 0 | 0 | 1 | 0 | `(-1) + y` |
| `x+y` | 0 | 0 | 0 | 0 | 1 | 0 | 直接相加 |
| `x-y` | 0 | 1 | 0 | 0 | 1 | 1 | `!x + y = y-x-1`，取反 = `x-y` |
| `y-x` | 0 | 0 | 0 | 1 | 1 | 1 | `x + !y = x-y-1`，取反 = `y-x` |
| `x&y` | 0 | 0 | 0 | 0 | 0 | 0 | 直接相与 |
| `x|y` | 0 | 1 | 0 | 1 | 0 | 1 | 德摩根：`!(!x & !y)` |

> 推导法（别死记）：**先令 x/y 变成你想要的常量或取反值，再用 `f` 选加/与，最后用 `no` 收尾**。唯一需要记住的恒等式是 `!z = -z - 1`。对着 `ALU.tst` 的真值表跑一遍比背表有用。

#### 易错点清单

1. ★ **`zr` 与 `ng` 必须取自最终的 `out`**（即 `no` 取反之后）—— 顺序错了 `!0` 会被判成"非零"，跳转指令全错。
2. ★ **官方芯片库里没有 `Or16Way`**，只有 `Or8Way`：必须两片 `Or8Way` + 一片 `Or`。
3. **补码溢出不检测**：`32767 + 1 = -32768` 静默回绕，ALU 没有溢出标志位（这是教学取舍，也是 408 考点"溢出判断"的反面教材）。
4. `Inc16` 用 `Add16` + 常量 `true/false`，别再手搓一条进位链。
5. HDL 的子总线赋值 `b[1..15]=false` 是合法写法，不用写 15 行。
6. `Add16` 的 carry 链方向：从最低位 `[0]` 向 `[15]` 传，接反了加法结果错。
7. `out[15]=ng` 这种"从总线抽一位接外部引脚"的写法合法（一个 part 的输出可以同时连多处）。

#### 设计理念

**ALU 的 6 个控制位就是一套"微指令"**。它把"运算种类"从"每种运算一条电路"压缩成"6 个正交开关的组合"—— 这正是 RISC 思想的雏形：**用少量正交控制位组合出丰富操作，而不是堆专用电路**。

顺带记住第二条：**补码让加法和减法共用一套电路**（`x-y = x + (-y)`，`-y = !y + 1`），所以机器里只有一个加法器，没有减法器。这是 408 "运算方法与运算器"的核心结论。

#### 验收

```bash
bash tools/HardwareSimulator.sh projects/2/ALU-basic.tst   # 只测 6 个基础函数，先跑这个
bash tools/HardwareSimulator.sh projects/2/ALU.tst         # 全 18 种 + zr/ng
```

---

### 3.3 [ch3] 时序逻辑

**交付物**：`projects/3/a/` —— `Bit / Register / RAM8 / RAM64 / PC`；`projects/3/b/` —— `RAM512 / RAM4K / RAM16K`
**核心问题**：组合逻辑没有记忆。如何用 DFF（唯一的"时间"来源）造出"能选择记住自己"的电路。

#### 关键路径

1. `Bit`（**本章唯一难点**：`load` 控制 + 反馈回路）
2. `Register`（16 个 Bit 并联，共用 load）
3. `RAM8`（地址 DMux 选"哪个寄存器被写"，Mux8Way16 选"读哪个"）
4. `PC`（inc/load/reset 三路优先级 Mux + Register）
5. `RAM64 / RAM512 / RAM4K / RAM16K`（**递归构造**，只做 RAM8 的构造逻辑即可往上抄）

#### 实现要点

```hdl
// Bit：核心是"输出可以选择来自输入，还是来自上一刻的自己"
CHIP Bit {
    IN in, load;
    OUT out;
    PARTS:
    Mux(a=loop, b=in, sel=load, out=dffin);
    DFF(in=dffin, out=out, out=loop);      // DFF 的输出同时连 out 与反馈线
}

// Register：16 个 Bit 并联
//   Register(in=in[0], load=load, out=out[0]) × 16

// RAM8：DMux8Way 把 load 分给 8 个寄存器；Mux8Way16 把 8 路输出汇成一路
CHIP RAM8 {
    IN in[16], load, address[3];
    OUT out[16];
    PARTS:
    DMux8Way(in=load, sel=address, out=l0, out=l1, ..., out=l7);
    Register(in=in, load=l0, out=r0); ... Register(in=in, load=l7, out=r7);
    Mux8Way16(a=r0, b=r1, ..., h=r7, sel=address, out=out);
}

// RAM64 = 8 个 RAM8：address[0..2] 块内，address[3..5] 选块
// RAM512 = 8 个 RAM64：address[0..5] 块内，address[6..8] 选块
// RAM4K  = 8 个 RAM512：address[0..8] 块内，address[9..11] 选块
// RAM16K = 4 个 RAM4K：address[0..11] 块内，address[12..13] 选块   ★ 注意是 4 片不是 8 片

// PC：三个控制的优先级是 reset > load > inc（Mux 级联顺序：inc 最内层，reset 最外层）
CHIP PC {
    IN in[16], inc, load, reset;
    OUT out[16];
    PARTS:
    Inc16(in=pred, out=incout);
    Mux16(a=pred,  b=incout, sel=inc,  out=o1);
    Mux16(a=o1,    b=in,     sel=load, out=o2);
    Mux16(a=o2,    b=false,  sel=reset, out=din);
    Register(in=din, load=true, out=out, out=pred);   // load 恒 1：每周期都可能变
}
```

#### 易错点清单

1. ★ **组合环路（combinatorial loop）**：`Bit` 里 Mux 的输出**必须经 DFF**才能回灌给自己。直接 `Mux(a=out, ...)` 会被模拟器判定为非法回路。
2. ★ **PC 的 Register `load` 必须恒为 `true`**（它不是"要不要写"，而是"值是什么"由前面的 Mux 决定）。
3. ★ **PC 的优先级顺序**：`inc` 在最内层、`reset` 在最外层（写反了 reset 失效）。
4. ★ **RAM16K = 4 × RAM4K，不是 8 × RAM4K**（16K = 4 × 4K）。位宽分配：`address[12..13]` 选块。
5. RAM 的 `out` 在**不写的时候也必须有效**（Mux 一直在选），不能只在 load 时输出。
6. 时序语义：`DFF` 的输出在**下一个周期**才变。写 `.tst` 时是 `tick`/`tock` 对，别指望同周期读到新值。
7. 反馈引线 `out=out, out=loop` 是合法写法（同一输出扇出多路）。

#### 设计理念

**"记住状态"这个能力，在整个项目里只来自一个地方：DFF**。其它所有时序行为（RAM 保持数据、PC 自增、CPU 取指推进）都是同一个模式的复制 —— **"让输出可以在'新输入'和'上一刻的自己'之间选择"**。

这条规律对 408 的价值：寄存器、存储器、计数器在电路层面是**同一种东西**（DFF + 选择逻辑），差别只在"选择逻辑长什么样"。

#### 验收

```bash
bash tools/HardwareSimulator.sh projects/3/a/Bit.tst
bash tools/HardwareSimulator.sh projects/3/a/Register.tst
bash tools/HardwareSimulator.sh projects/3/a/PC.tst
bash tools/HardwareSimulator.sh projects/3/b/RAM16K.tst
```

---

### 3.4 [ch4] 机器语言（Hack 汇编）

**交付物**：`projects/4/mult/Mult.asm`、`projects/4/fill/Fill.asm`
**核心问题**：只有两个寄存器（A/D）、两种指令，怎么写出"乘法"和"响应键盘刷屏"。

#### 关键路径

1. 先背下三条铁律（见下），再动手
2. `Mult.asm`：重复加法（`R2 = R0 * R1`）
3. `Fill.asm`：无限循环 + 轮询键盘 + 按字刷屏（**状态机要一次刷完再回查**）

#### 实现要点

**三条铁律**（Hack 汇编的全部难点就这三条）：

1. **要读/写内存，必须先把地址装进 A**：`M` 永远指 `RAM[A]`。
2. **要跳转，必须先把目标地址装进 A**：`@LABEL` 之后才能 `0;JMP`。
3. **一条 C-指令里 A 和 M 不能同时当运算源**（被 `a` 位二选一限制）。想用 `M` 参与运算，先 `D=M`。

```asm
// Mult.asm: R2 = R0 * R1（重复加法）
    @R2
    M=0              // 结果清零
(LOOP)
    @R0
    D=M
    @END
    D;JLE            // while (R0 > 0)
    @R1
    D=M
    @R2
    M=D+M            // R2 = R2 + R1
    @R0
    M=M-1            // R0--
    @LOOP
    0;JMP
(END)
    @END
    0;JMP            // 死循环收尾：不写会跑飞
```

```asm
// Fill.asm: 有按键 -> 全屏黑；无按键 -> 全屏白
// 技巧：把"要写的值"放进一个变量 color，循环体只有一份
    @SCREEN
    D=A
    @addr
    M=D              // addr = 16384
(LOOP)
    @KBD
    D=M
    @PRESSED
    D;JGT            // 键盘非零 -> 按下
    @color
    M=0              // 白
    @FILL
    0;JMP
(PRESSED)
    @color
    M=-1             // 黑（16 位全 1 = 32 个像素全黑）
(FILL)
    @SCREEN
    D=A
    @addr
    M=D              // 从屏幕首地址重新开始
(FILLLOOP)
    @24576
    D=A
    @addr
    D=M-D
    @LOOP
    D;JGE            // addr >= 24576 -> 刷完了，回主循环查键盘
    @color
    D=M
    @addr
    A=M
    M=D              // RAM[addr] = color
    @addr
    M=M+1
    @FILLLOOP
    0;JMP
```

#### 易错点清单

1. ★ **跳转前忘了 `@LABEL`**：`0;JMP` 跳的是 `A` 里的值，不是"上一行写的标签"。
2. ★ **`M=D+M` 之外，A 和 M 不能同时参与**：想算 `RAM[i]+RAM[j]` 必须 `D=M` 之后再处理。
3. ★ **A-指令装不了负数**：`@-1` 非法。负常量只能出现在 C-指令的 comp 里（`M=-1`、`D=-1`）或 `D=A` 之后再 `D=-D`。
4. **程序结尾必须死循环**（`@END; 0;JMP`），否则 PC 会跑进 ROM 的垃圾区。
5. **屏幕是 512×256，每行 32 个字，共 8192 字**（16384..24575）。刷屏循环要跑 8192 次，不是 65536 次（那是像素数）。
6. **`Fill.asm` 的状态机**：先决定 color，再一次性刷完整屏，然后回主循环。每画一个像素就查一次键盘会导致"按下的瞬间只刷了一半屏幕"—— 这是官方 `.cmp` 最容易挂的地方。
7. 符号名：`R0..R15`、`SP`、`LCL`、`ARG`、`THIS`、`THAT`、`SCREEN`(16384)、`KBD`(24576) 是汇编器预定义的，不需要自己定义。

#### 设计理念

**内存映射 I/O 让"设备驱动"退化成"读写内存"**。Hack 没有 IN/OUT 指令，键盘和屏幕只是两个地址 —— 这段汇编就是最原始的"显卡驱动 + 键盘驱动"，而它只用了 40 行。

这正是 408 "I/O 端口编址：统一编址 vs 独立编址"的实物：统一编址下，**访存指令就是 I/O 指令**，代价是占用地址空间。

#### 验收

```bash
bash tools/CPUEmulator.sh projects/4/mult/Mult.tst
bash tools/CPUEmulator.sh projects/4/fill/FillAutomatic.tst
```

---

### 3.5 [ch5] 计算机体系 ★ 全项目最高价值点

**交付物**：`projects/5/` —— `Memory.hdl`、`CPU.hdl`、`Computer.hdl`
**核心问题**：把一条 16 位指令拆成控制信号，让 CPU 在一个周期内完成「取指 → 译码 → 执行 → 决定下一条」。

#### 关键路径（严格按这个顺序）

1. **`Memory.hdl`**（先做，它是 CPU 的"外接设备"）：把 RAM16K / Screen / Keyboard 用地址高位拼成一个地址空间
2. **`CPU.hdl`**：按信号流连 —— ① 指令类型判定 → ② A 寄存器（输入 + load 条件）→ ③ ALU（x/y/控制位）→ ④ 结果写回（A/D/M）→ ⑤ PC（跳转判定）
3. **`Computer.hdl`**：CPU + Memory + ROM32K 三件套闭环

#### 实现要点

**（1）Memory.hdl —— 地址译码**

官方 stub 注释已经把规则写死了：`0x0000-0x3FFF` RAM，`0x4000-0x5FFF` 屏幕，`0x6000` 键盘，`>0x6000` 无效。

```hdl
CHIP Memory {
    IN in[16], load, address[15];
    OUT out[16];
    PARTS:
    // 地址区间判定（16384 = 2^14，24576 = 0x6000 = 2^13 + 2^14）
    Not(in=address[14], out=n14);
    Not(in=address[15], out=n15);
    And(a=n14, b=n15, out=isRAM);              // address < 16384
    And(a=address[14], b=n15, out=isScreen);   // 16384..24575
    And(a=address[14], b=address[13], out=k1);
    And(a=k1, b=n15, out=isKey);               // 24576

    // 把 load 路由到对应芯片
    And(a=load, b=isRAM,    out=ramL);
    And(a=load, b=isScreen, out=scrL);

    RAM16K(in=in, load=ramL, address=address[0..13], out=ramOut);
    Screen(in=in, load=scrL, address=address[0..12], out=scrOut);   // 8K = 2^13，只吃低 13 位
    Keyboard(out=keyOut);

    // 输出三选一
    Mux16(a=ramOut, b=scrOut, sel=isScreen, out=o1);
    Mux16(a=o1, b=keyOut, sel=isKey, out=out);
}
```

**（2）CPU.hdl —— 指令位段 → 控制线**

先把 16 位指令的字段刻在脑子里：

```
bit:  15 14 13  12   11 10 9 8 7 6   5  4  3   2  1  0
A指令: 0  v  v   v    v  v  v v v v   v  v  v   v  v  v      (15 位常量)
C指令: 1  1  1   a    c1..c6(6 位)    d1 d2 d3  j1 j2 j3
                 |         |            |  |  |   |  |  |
                 |         comp         A  D  M   <0 =0 >0
                 +-- a=0 用 M(=RAM[A])，a=1 用 A
```

```hdl
CHIP CPU {
    IN  inM[16], instruction[16], reset;
    OUT outM[16], writeM, addressM[15], pc[15];

    PARTS:
    // ---- ① 指令类型 & 字段抽取 ----
    Not(in=instruction[15], out=isA);          // i[15]=0 -> A-指令

    // ---- ② A 寄存器：装立即数 还是 装 ALU 结果 ----
    Mux16(a=instruction, b=aluOut, sel=instruction[15], out=aIn);
    Or(a=isA, b=instruction[5], out=loadA);    // loadA = 是A指令 或 dest 里有 A 位
    ARegister(in=aIn, load=loadA, out=aReg, out=addressM);

    // ---- ③ ALU：x 恒为 D，y 由 a 位在 A/M 之间选 ----
    Mux16(a=aReg, b=inM, sel=instruction[12], out=aluY);
    ALU(x=dReg, y=aluY,
        zx=instruction[11], nx=instruction[10],
        zy=instruction[9],  ny=instruction[8],
        f=instruction[7],   no=instruction[6],
        out=aluOut, out=outM, zr=zr, ng=ng);

    // ---- ④ 写回：D 与 M ----
    And(a=instruction[15], b=instruction[4], out=loadD);
    DRegister(in=aluOut, load=loadD, out=dReg);
    And(a=instruction[15], b=instruction[3], out=writeM);

    // ---- ⑤ PC：跳还是不跳 ----
    And(a=ng, b=instruction[2], out=jlt);                  // out < 0
    And(a=zr, b=instruction[1], out=jeq);                  // out = 0
    Or(a=ng, b=zr, out=ngz);
    Not(in=ngz, out=pos);
    And(a=pos, b=instruction[0], out=jgt);                 // out > 0
    Or(a=jlt, b=jeq, out=j1);
    Or(a=j1, b=jgt, out=wantJump);
    And(a=instruction[15], b=wantJump, out=pcLoad);        // A-指令永不跳转
    PC(in=aReg, load=pcLoad, inc=true, reset=reset, out=pc);
}
```

**（3）Computer.hdl**

```hdl
CHIP Computer {
    IN reset;
    PARTS:
    ROM32K(address=cpuPc, out=ins);
    CPU(inM=memOut, instruction=ins, reset=reset,
        outM=cpuOutM, writeM=cpuWriteM, addressM=cpuAddrM, pc=cpuPc);
    Memory(in=cpuOutM, load=cpuWriteM, address=cpuAddrM, out=memOut);
}
```

#### 易错点清单（本章坑最多，逐条对照）

1. ★ **A 寄存器的 load 条件漏了 dest 的 A 位**：只写 `Not(i[15])`（"是 A-指令就装载"）是不够的 —— C-指令 `AMD` 组合里也要写 A。正确条件：`isA OR i[5]`。
2. ★ **`writeM` 必须与 `i[15]` 相与**：A-指令的 bit5..3 不是 dest 字段（它们是常量的一部分），不屏蔽会导致 A-指令误写内存。
3. ★ **`addressM` = A 寄存器的输出**（不是 PC、不是指令里的地址字段）。
4. ★ **跳转目标必须先装进 A**：这是 ch4 那个坑的硬件根源 —— PC 的输入只有 A 寄存器这一条路。
5. ★ **`PC` 的 `inc` 恒为 `true`**，`load` = 跳转条件成立（load 优先于 inc，PC 内部已按 reset>load>inc 排好）。
6. ★ **ALU 的 `x` 恒接 D 寄存器**：官方约定就是这样，`x+y` 里的 x 永远是 D。
7. **Screen 只吃 13 位地址**（8K = 2^13），送进去的是 `address[0..12]`，不是原地址。
8. **`outM` 恒等于 `aluOut`**（不写内存时值无意义，但连着无害）；`writeM=0` 时 `outM` 可以是任意值（stub 注释明确写了）。
9. **`reset` 只连 PC**，不要接到 A/D 寄存器。
10. **CPU 里的反馈是合法的**：`ALU 输出 → A 寄存器 → ALU 的 y` 这条环路中间有 A 寄存器（含 DFF），不是组合环。
11. **时序**：stub 注释说得很清楚 —— `outM`/`writeM` 是**组合**的（当周期有效），`addressM`/`pc` 是**时钟**的（下周期才生效）。这决定了为什么"写入内存"要等到下一条指令才看得见结果。

#### 设计理念

**"译码"就是把指令字的位段接到不同控制线上**。这台 CPU 没有微程序、没有状态机，它就是一堆 Mux 加上"哪些寄存器该被写入"的组合逻辑。

做完这一章你会获得一个非常值钱的认识：**ISA（指令集架构）与微架构（数据通路）的分界，就在这些控制位上**。同一份 ISA 可以有不同的数据通路（单周期 / 多周期 / 流水线），而 Hack 是**最极端的单周期**：取指与执行在一个周期内完成，代价是完全没有流水线（对照 408 的流水线吞吐率与冒险）。

#### 验收（四个层次，逐级加码）

```bash
bash tools/HardwareSimulator.sh projects/5/CPU.tst              # 只测 CPU 内部
bash tools/HardwareSimulator.sh projects/5/CPU-external.tst     # 只测外部接口
bash tools/HardwareSimulator.sh projects/5/Memory.tst
bash tools/CPUEmulator.sh projects/5/ComputerAdd.tst            # 整机跑 Add.hack
bash tools/CPUEmulator.sh projects/5/ComputerMax.tst            # 整机跑 Max.hack
bash tools/CPUEmulator.sh projects/5/ComputerRect.tst           # 整机跑 Rect.hack（会画屏幕）
# ComputerRect 跑通 = 你的 CPU + Memory + 屏幕 I/O 全链路正确，值得截图留念
```

---

### 3.6 [ch6] 汇编器

**交付物**：一门高级语言写的 assembler（**源码不在库**，建议 `learning-408/nand2tetris/tools/` 旁边新建 `mytools/assembler.py`，或直接 `projects/6/assembler.py`）
**核心问题**：把符号（`@LOOP`、`@R5`、`@i`）变成数字，以及为什么必须**扫两遍**。

#### 关键路径

1. `Parser`：清注释与空白 → 判指令类型（A_INSTRUCTION / C_INSTRUCTION / L_INSTRUCTION）→ 切字段（dest / comp / jump / symbol）
2. `SymbolTable`：预定义符号表（`R0..R15`=0..15、`SP`=0、`LCL`=1、`ARG`=2、`THIS`=3、`THAT`=4、`SCREEN`=16384、`KBD`=24576）
3. **第一遍**：只建标签表 —— 遇 `(LABEL)` 记 `symbol=当前 ROM 地址`，A/C 指令时 ROM 地址 +1
4. **第二遍**：翻译 —— 未知符号当作**变量**，从 RAM 地址 16 起分配
5. `Code`：三张查找表（comp 28 项 / dest / jump）→ 拼成 16 位二进制

#### 实现要点

```python
# 骨架：两遍扫描的核心
def first_pass(lines):
    rom = 0
    table = {}
    for raw in lines:
        line = strip(raw)                 # 去掉 // 注释与首尾空白，跳过空行
        if line.startswith('('):          # (LABEL) 不产生指令，不推进 ROM 地址
            table[line[1:-1]] = rom
        else:
            rom += 1                      # A 或 C 指令各占一条
    return table

def second_pass(lines, table):
    next_var = 16                         # 变量从 RAM[16] 开始分配
    out = []
    for raw in lines:
        line = strip(raw)
        if line.startswith('('):  continue
        if line.startswith('@'):
            sym = line[1:]
            if not sym.isdigit():
                if sym not in table:
                    table[sym] = next_var; next_var += 1
                sym = str(table[sym])
            out.append('0' + format(int(sym), '015b'))   # 补零到 16 位
        else:
            out.append('111' + code.comp(line) + code.dest(line) + code.jump(line))
    return out
```

**comp 表的关键（28 项，含 a 位）**：含 `M` 的那一组 `a=1`，其余 `a=0`：

| a=0 | 0 1 -1 D A !D !A -D -A D+1 A+1 D-1 A-1 D+A D-A A-D D&A D\|A |
|---|---|
| a=1 | M !M -M M+1 M-1 D+M D-M M-D D&M D\|M |

#### 易错点清单

1. ★ **两遍的 ROM 地址计数器必须各自从 0 重新计**：第一遍只为标签服务，第二遍不再加标签。
2. ★ **变量符号从 RAM 16 开始分配**，且只在第二遍"第一次遇到"时分配（不是第一遍）。
3. ★ **A-指令的常量要补零到 16 位**（`'0' + 15 位`），漏了高位补零会导致解析错位。
4. **先清注释与空白再判类型**：否则空行/纯注释行会被当成指令。
5. `(LABEL)` 行不生成任何输出。
6. `dest` 为空时输出 `000`，`jump` 为空时输出 `000`（不能省略）。
7. 符号可以重复定义吗？**不能** —— 重复标签应报错，别静默覆盖。

#### 设计理念

**两遍扫描是"前向引用"问题的最小解**：第一遍只知道名字不知道值，第二遍才知道值。同样的模式在链接器里还会再出现一次（重定位也是两遍）。

另一个值得记住的点：**符号表是编译器最古老也最有用的数据结构之一**，它的本质就是"名字 → 位置"的映射，ch10/11 的符号表、链接器的重定位表、OS 的动态符号表，都是它的后裔。

#### 验收

```bash
python3 assembler.py projects/6/max/Max.asm          # 生成 Max.hack
bash tools/CPUEmulator.sh projects/6/max/Max.tst     # 官方 .tst 会加载 .hack 并比对
# 更狠的测试：projects/6/pong/Pong.asm（28378 行），跑通说明你的汇编器能扛住真实规模
```


---

### 3.7 [ch7] 虚拟机 I：栈运算与内存段

**交付物**：VMTranslator 前半（**源码不在库**，建议 `projects/7/vmtranslator.py`）
**核心问题**：编译器眼里的八个"段"（local/argument/this/that/...）怎么落到 Hack 那 32K 字 RAM 上。

#### 关键路径

1. `Parser`：命令类型（`C_PUSH` / `C_POP` / `C_ARITHMETIC`）+ 参数（段名、索引）
2. **段的基址映射表**（本节核心，见下表）
3. `push` 模板、`pop` 模板
4. 算术逻辑命令：二元（add/sub/and/or）、一元（neg/not）、比较（eq/gt/lt，**要生成唯一标签**）
5. 用 `projects/7` 的官方 `.tst/.cmp` 验收

#### 实现要点

**段 → RAM 的映射（必须背下来，ch8 也靠它）**：

| VM 段 | 基址 | 说明 |
|---|---|---|
| `local` | `LCL` = RAM[1] | 被调用函数的局部变量 |
| `argument` | `ARG` = RAM[2] | 实参 |
| `this` | `THIS` = RAM[3] | 当前对象的基址 |
| `that` | `THAT` = RAM[4] | 数组/另一对象的基址 |
| `pointer 0/1` | RAM[3] / RAM[4] | **直接读写 THIS/THAT**，只有 2 个 |
| `temp` | RAM[5]..RAM[12] | **只有 8 个**，VMTranslator 的临时区 |
| `static i` | RAM[16] 起（符号 `文件名.i`） | **全局**，跨函数共享 |
| `constant i` | 无 | 直接把 i 推入栈 |

```asm
// push local 2        （addr = LCL + 2，把 RAM[addr] 推入栈）
    @LCL
    D=M
    @2
    A=D+A          // A = LCL + 2
    D=M            // D = RAM[LCL+2]
    @SP
    A=M
    M=D            // *SP = D
    @SP
    M=M+1          // SP++

// pop argument 3     （addr = ARG + 3，栈顶弹出写入 RAM[addr]）
    @ARG
    D=M
    @3
    D=D+A
    @R13
    M=D            // R13 = 目标地址（暂存）
    @SP
    AM=M-1         // SP-- 且 A 指向栈顶
    D=M            // D = 栈顶值
    @R13
    A=M
    M=D            // RAM[目标] = D

// add：弹栈顶到 D，与新的栈顶相加，结果留在栈顶
    @SP
    AM=M-1
    D=M
    A=A-1
    M=M+D

// eq：比较，结果必须是 -1(真) / 0(假)，需要唯一标签
    @SP
    AM=M-1
    D=M
    A=A-1
    D=M-D
    @EQ_TRUE_<n>   // <n> 是全局递增计数器，保证唯一
    D;JEQ
    @SP
    A=M-1
    M=0            // 假
    @EQ_END_<n>
    0;JMP
(EQ_TRUE_<n>)
    @SP
    A=M-1
    M=-1           // 真 = -1（16 位全 1）
(EQ_END_<n>)
```

#### 易错点清单

1. ★ **`that` 的基址是 RAM[4]，不是 RAM[3]`**：`pointer 0` → THIS(R3)，`pointer 1` → THAT(R4)。这两个极易对调。
2. ★ **`temp` 只有 8 个（R5–R12）**：越界会踩到 R13–R15，那是 VMTranslator 自己用的临时寄存器，踩了就诡异崩溃。
3. ★ **比较的结果是 `-1` 不是 `1`**（Jack 里 `true` 是全 1 的补码）。写成 1 会让 `if` 判断失效。
4. ★ **SP 指向"下一个空位"**：push 是 `*SP = v; SP++`；pop 是 `SP--; v = *SP`（用 `AM=M-1` 一步到位）。
5. **处理 `pointer` 与 `temp` 时不要走"基址 + 偏移"的通用路径**（它们没有基址寄存器），直接 `@R5`/`@THIS`。
6. `static` 的符号名要带文件名（`Foo.3`），否则多文件会撞名。
7. `constant i` 的 push 是 `D=i; *SP=D; SP++`；**`pop constant` 是非法命令**。

#### 设计理念

**八个内存段是"编译器的视图"，底层只有一块 RAM 加四个基址寄存器（LCL/ARG/THIS/THAT）**。这一层的价值在于把"变量放在哪里"这个决定从编译期推迟到运行期 —— 编译器只需要说"第 2 个局部变量"，物理地址由 VM 运行时算。

这也解释了为什么**函数调用可以递归**：每个栈帧都有自己的 LCL/ARG，段名不变、基址随帧而变。

#### 验收

```bash
python3 vmtranslator.py projects/7/StackArithmetic/SimpleAdd
bash tools/CPUEmulator.sh projects/7/StackArithmetic/SimpleAdd/SimpleAdd.tst
python3 vmtranslator.py projects/7/MemoryAccess/StaticTest
bash tools/CPUEmulator.sh projects/7/MemoryAccess/StaticTest/StaticTest.tst
```

---

### 3.8 [ch8] 虚拟机 II：程序流与函数调用 ★

**交付物**：VMTranslator 后半 + **bootstrap 代码**
**核心问题**：硬件完全没有"调用"概念（没有 push 多寄存器指令、没有帧指针），如何靠**约定**实现函数调用。

#### 关键路径

1. `label` / `goto` / `if-goto`：标签加**函数名前缀**保证全局唯一（`函数名$label`）
2. `function f n`：发标签 + 把 n 个 local 压 0
3. `call f k`：压返回地址 → 压 LCL/ARG/THIS/THAT → 重设 ARG → 重设 LCL → 跳
4. `return`：**这一节最容易写错**，见下面"五步法"
5. **bootstrap**（`Sys.init`）：`SP=256` 然后 `call Sys.init`

#### 实现要点

**栈帧长这样（调用者视角，`call` 执行完的瞬间）**：

```
     ... 上上帧 ...
     argument 0      <- ARG 指向这里（第一个实参）
     argument 1
     ...
     argument k-1
     returnAddress   <- FRAME-5
     saved LCL       <- FRAME-4
     saved ARG       <- FRAME-3
     saved THIS      <- FRAME-2
     saved THAT      <- FRAME-1
     local 0         <- LCL 指向这里（FRAME）
     local 1
     ...
     local n-1
     工作栈 ...       <- SP 指向下一个空位
```

```asm
// ---------- call f k ----------
    @<f>$ret.<n>        // 1. 压返回地址（唯一标签）
    D=A
    @SP
    A=M
    M=D
    @SP
    M=M+1
    @LCL                // 2. 依次压 LCL/ARG/THIS/THAT
    D=M
    @SP
    A=M
    M=D
    @SP
    M=M+1
    @ARG
    D=M
    @SP
    A=M
    M=D
    @SP
    M=M+1
    @THIS
    D=M
    @SP
    A=M
    M=D
    @SP
    M=M+1
    @THAT
    D=M
    @SP
    A=M
    M=D
    @SP
    M=M+1
    @SP                 // 3. ARG = SP - 5 - k
    D=M
    @5
    D=D-A
    @k
    D=D-A
    @ARG
    M=D
    @SP                 // 4. LCL = SP
    D=M
    @LCL
    M=D
    @<f>                // 5. 无条件跳转
    0;JMP
(<f>$ret.<n>)           // 6. 返回后从这里继续
```

```asm
// ---------- return（五步法，顺序不能错）----------
    @LCL                // ① FRAME = LCL，存 R13
    D=M
    @R13
    M=D
    @5                  // ② RET = *(FRAME-5)，存 R14
    D=A
    @R13
    A=M-D
    D=M
    @R14
    M=D                 // ★ 必须在写返回值之前取走！
    @SP                 // ③ *ARG = 返回值，SP = ARG+1
    A=M-1
    D=M
    @ARG
    A=M
    M=D
    @ARG
    D=M+1
    @SP
    M=D
    @R13                // ④ 依次恢复 THAT/THIS/ARG/LCL
    A=M-1
    D=M
    @THAT
    M=D
    @2
    D=A
    @R13
    A=M-D
    D=M
    @THIS
    M=D
    @3
    D=A
    @R13
    A=M-D
    D=M
    @ARG
    M=D
    @4
    D=A
    @R13
    A=M-D
    D=M
    @LCL
    M=D
    @R14                // ⑤ 跳回返回地址
    A=M
    0;JMP
```

```asm
// ---------- bootstrap：整个 VM 程序的第一段代码 ----------
    @256
    D=A
    @SP
    M=D
    // （可选）压入 5 个 0 作为 Sys.init 的调用者帧占位：
    // 虽然 Sys.init 永不返回，但压了可以让 return 的实现读到合法数据
    @LCL
    M=0
    @ARG
    M=0
    @THIS
    M=0
    @THAT
    M=0
    @Sys.init
    0;JMP
```

#### 易错点清单（官方论坛血泪榜）

1. ★★ **`RET = *(FRAME-5)` 必须在"把返回值写到 `*ARG`"之前取走**。当函数**没有参数**时，`ARG` 就是 `FRAME-5` —— 晚一步，返回地址就被返回值覆盖，程序立刻飞到一个随机地址。这是本章第一号杀手。
2. ★ **`function f n` 的标签不要加文件名/类名前缀**（官方要求照 VM 里的原名写 `f`），而 `goto/label` **必须**加 `当前函数名$` 前缀。两者规则相反。
3. ★ **翻译 `return` 时不要重置"当前函数名"**：一个函数里有两个 `return` 时，重置会让第二个 `return` 之后的标签丢前缀（官方论坛明确记录的 bug）。
4. ★ **R13/R14/R15 是易失的**：任何被调用函数都可能改掉它们，用完即弃，不能跨调用保存。
5. **`call` 里 `ARG = SP - 5 - k` 必须在压完 5 个槽之后算**（顺序错就指向错误的实参位置）。
6. **每个 `call` 的返回标签必须唯一**（用全局递增计数器，不能用函数名，因为同一函数可能被调多次、也可能递归）。
7. **`function f n` 必须把 n 个 local 压 0**（生成 n 次 `push constant 0`），否则局部变量是垃圾值。
8. **bootstrap 必须把 SP 初始化为 256**，忘了整个栈从 0 开始，会覆盖 R0–R15 的虚拟机寄存器。
9. **Sys.init 永不返回**，所以 bootstrap 末尾通常是 `call Sys.init` 后接一个死循环（或依赖 OS 的 `Sys.halt`）。

#### 设计理念

**栈帧是软件契约，不是硬件规定**。Hack 里没有任何东西强迫你按这套顺序压栈 —— 是 VMTranslator 生成的一段固定汇编，把"调用者保存什么、被调用者恢复什么"写成了代码。

想通这一点，x86 的 caller-save / callee-save 约定就不用背了：**它们是同一个问题的另一种答案**。区别只在于"这份契约由谁履行" —— x86 里由编译器按 ABI 生成，Hack 里由你写的 VMTranslator 生成。

**另外一个非常值钱的推论**：正因为调用约定是软件定的，所以"函数"这个概念可以完全脱离硬件存在。这就是为什么高级语言的函数能递归、能嵌套、能当作值传递 —— 硬件只看到一个栈在长长短短地变化。

#### 验收（四个测试，逐个升级）

```bash
python3 vmtranslator.py projects/8/ProgramFlow/BasicLoop
bash tools/CPUEmulator.sh projects/8/ProgramFlow/BasicLoop/BasicLoop.tst
python3 vmtranslator.py projects/8/FunctionCalls/SimpleFunction
bash tools/CPUEmulator.sh projects/8/FunctionCalls/SimpleFunction/SimpleFunction.tst
bash tools/CPUEmulator.sh projects/8/FunctionCalls/NestedCall/NestedCall.tst      # ★ 递归调用，最狠
bash tools/CPUEmulator.sh projects/8/FunctionCalls/FibonacciElement/FibonacciElement.tst
```

---

### 3.9 [ch9] Jack 语言

**交付物**：`projects/9/` 下的 Jack 应用（**本地已有实现**：`Average / ComplexArrays / ConvertToBin / Fraction / HelloWorld / List / Pong / Square`）
**核心问题**：在没有继承、没有多态、没有 GC 的语言里，对象到底是什么。

#### 关键路径

1. 三个 subroutine 类型分清楚：`constructor` / `method` / `function`
2. 对象 = 一块连续内存；`this` = 这块内存的基址
3. 数组 = `Memory.alloc(n+1)`，`a[0]` 存长度
4. 手动内存管理：`dispose()`（看本地 `projects/9/List/List.jack` 的递归版本）

#### 实现要点

```jack
class List {
    field int data;      // 字段：存在对象内存的第 0 个字
    field List next;     // 第 1 个字

    constructor List new(int car, List cdr) {
        let data = car;
        let next = cdr;
        return this;                 // ★ constructor 必须返回 this
    }

    method int getData() { return data; }   // method 隐含 this = argument 0

    method void dispose() {                 // ★ 手动释放，且必须递归
        if (~(next = null)) {
            do next.dispose();
        }
        do Memory.deAlloc(this);
        return;
    }
}
```

**三种 subroutine 的对照**：

| 类型 | `this` | 谁来调 | 第一步干什么 |
|---|---|---|---|
| `constructor` | 未初始化 | `List.new(...)` 展开成 `Memory.alloc(size)` + 调用 | 分配内存、`let this = ...`、返 `this` |
| `method` | 隐含 `argument 0` | `obj.m(...)` | 通过 `this` 访问字段（字段 = `this[k]`） |
| `function` | 没有 | `Class.f(...)` | 纯静态，不能碰字段 |

**对象在内存里的样子**（`Point p = Point.new(3, 5)`）：

```
RAM[x+0] : 3        <- p.x（field int x）
RAM[x+1] : 5        <- p.y（field int y）
p 本身   : x        <- 变量 p 只存基址（引用！）
```

#### 易错点清单

1. ★ **对象变量是引用（地址）**：`let a = b` 不复制对象，两个变量指向同一块内存。
2. ★ **没有 GC、没有 null 检查**：`dispose()` 必须自己写，且对复合结构要**递归释放**（`List.jack` 就是范例）；重复 dispose 会破坏堆。
3. ★ **`~(x = null)` 是 Jack 的标准惯用法**（`~` 是按位取反当逻辑非用），不是笔误。
4. **一个文件 = 一个类**，文件名必须等于类名；`Main.main()` 是程序入口。
5. **字符串常量会隐式调用 `String.new`**，产生堆分配 —— 频繁拼接字符串会很快吃光堆。
6. **没有继承、没有多态、没有接口**：想"复用"只能靠组合（field 里放另一个对象）。
7. **`var` 声明必须在函数体最前面**（Jack 语法要求），不能随用随声明。
8. **整数除法与乘法走 OS**：`x * y` 会变成 `call Math.multiply`，在循环里大量使用会明显变慢。

#### 设计理念

**把"面向对象"还原成内存布局，它就一点都不神秘了**：对象 = 一块连续内存（字段按声明顺序排），方法 = 一段以 `this` 为第 0 个参数的普通函数。**没有虚表、没有继承、没有运行时类型信息** —— 正因为砍掉了这些，你才能看清 OO 的最小骨架是什么。

顺带一条对 408 有用的：**"方法调用"在机器层面就是"函数指针 + 一个隐含参数"**。C++ 的 `thiscall`、Python 的 `self`、Java 的 `invokevirtual`，底层都是这个模式。

#### 验收

```bash
bash tools/JackCompiler.sh projects/9/Fraction        # 用官方编译器编
bash tools/VMEmulator.sh                              # 加载目录，跑 Fraction 的 .tst
```

---

### 3.10 [ch10] 编译器 I：语法分析

**交付物**：`JackTokenizer` + `CompilationEngine`，输出 XML（**源码不在库**；`projects/10/*/` 下有官方测试 jack 与参考 `.xml`）
**核心问题**：把字符流变成树，并且每一步都能**肉眼验证**。

#### 关键路径

1. `JackTokenizer`：五类 token（keyword / symbol / identifier / integerConstant / stringConstant）
2. `CompilationEngine`：**递归下降**，一个非终结符一个函数
3. 输出 XML，与官方参考 `.xml` 逐字节比对

#### 实现要点

```
Jack 文法（精简版，照它写递归下降）：
    class          : 'class' className '{' classVarDec* subroutineDec* '}'
    classVarDec    : ('static'|'field') type varName (',' varName)* ';'
    subroutineDec  : ('constructor'|'function'|'method') (void|type) subName
                     '(' parameterList ')' subroutineBody
    parameterList  : ((type varName) (',' type varName)*)?
    subroutineBody : '{' varDec* statements '}'
    varDec         : 'var' type varName (',' varName)* ';'
    statements     : statement*
    statement      : let | if | while | do | return
    letStatement   : 'let' varName ('[' expression ']')? '=' expression ';'
    ifStatement    : 'if' '(' expression ')' '{' statements '}' ('else' '{' statements '}')?
    whileStatement : 'while' '(' expression ')' '{' statements '}'
    doStatement    : 'do' subroutineCall ';'
    returnStatement: 'return' expression? ';'
    expression     : term (op term)*
    term           : integerConstant | stringConstant | keywordConstant | varName
                     | varName '[' expression ']' | subroutineCall
                     | '(' expression ')' | unaryOp term
    subroutineCall : subName '(' expressionList ')' | (varName|className) '.' subName '(' expressionList ')'
```

```python
def compileExpression(self):
    self.compileTerm()
    while self.tokenizer.symbol() in ('+','-','*','/','&','|','<','>','='):
        op = self.tokenizer.symbol()
        self.advance()
        self.compileTerm()          # ★ 循环往右吃，不是递归进右子树
        self.write_op(op)

def compileTerm(self):
    t = self.tokenizer.token_type()
    if t == INT_CONST:    ...
    elif t == STRING_CONST: ...
    elif t == KEYWORD:    ...       # true / false / null / this
    elif self.tokenizer.symbol() == '(':
        self.expect('('); self.compileExpression(); self.expect(')')
    elif self.tokenizer.symbol() in ('-', '~'):
        self.advance(); self.compileTerm()
    else:                           # 标识符：变量 / 数组 / 子程序调用
        name = self.advance()
        if self.peek() == '[':      ...   # a[i]
        elif self.peek() in ('(', '.'): ...  # f(x) 或 a.f(x)
        else: ...                         # 普通变量
```

#### 易错点清单

1. ★ **表达式是左递归的**：不能用"递归下降进右子树"的写法，必须"先编译一个 term，然后 while(op) 循环往右吃"。
2. ★ **XML 里符号要转义**：`<` → `&lt;`，`>` → `&gt;`，`&` → `&amp;`，`"` → `&quot;`。
3. **关键字 vs 标识符靠关键字表判断**，不能靠首字母（否则 `class` 会被当成变量名）。
4. **`(expression)` 与 `subroutineCall` 都属于 `term`**，括号层级漏一层 XML 就错。
5. 标识符要先"吃掉"（advance）再判断后面是 `[` 还是 `(` 还是 `.` —— 需要 **lookahead**。
6. `unaryOp term`（`-x`、`~flag`）也在 `term` 里，别放到 `expression` 层。
7. **输出格式要严格照官方 `.xml`**：标签名、缩进、换行，逐字节比对才能过（这也是这一章的价值 —— 把"解析对不对"变成可机械验证的事）。

#### 设计理念

**文法即代码结构**。递归下降之所以好写，是因为每个非终结符恰好对应一个函数 —— 这是"规范驱动实现"的又一次体现（和 §2.2 的 stub/tst/cmp 是同一思路）。

**先做语法分析并输出一个"看得见的中间产物"（XML），再做代码生成** —— 这是工程上的大智慧：它把"我没读懂"和"我没翻对"这两类 bug 彻底分开。

#### 验收

```bash
python3 jackanalyzer.py projects/10/Square            # 生成 *.xml
bash tools/TextComparer.sh projects/10/Square/Main.xml projects/10/Square/MainRef.xml
# 或者直接用 GUI 打开官方提供的参考 xml 做目测比对
```

---

### 3.11 [ch11] 编译器 II：代码生成

**交付物**：`SymbolTable` + `VMWriter`，Jack → VM（**源码不在库**）
**核心问题**：把语法树变成栈式 VM 指令，且表达式、控制流、对象/数组三件事各有各的套路。

#### 关键路径

1. 两级符号表：class 级（static/field）+ subroutine 级（argument/local），各自从 0 编号
2. 表达式：栈式后缀生成
3. 控制流：`if` / `while` 用唯一标签
4. `do`：调用后**丢弃返回值**（`pop temp 0`）
5. 对象：构造（`Memory.alloc` + `pointer 0 = base`）、方法调用（`push this` + `call C.m n+1`）
6. 数组：`Array.new` + 指针加法 + `that` 段访问
7. 字符串常量：`String.new(len)` + 逐字符 `appendChar`

#### 实现要点

```python
# 变量 -> VM 段
kind_to_segment = {'static': 'static', 'field': 'this',
                   'argument': 'argument', 'local': 'local', 'var': 'local'}

# ---- let a[i] = expr 的生成顺序（★ 先算地址，再算右值）----
#   push a; push i; add;            # 栈顶 = a+i
#   <编译 expr>                      # 栈顶 = 右值
#   pop temp 0; pop pointer 1; push temp 0; pop that 0

# ---- 方法调用 obj.m(x) ----
#   push obj            # this 作为 argument 0
#   <编译 x>
#   call Class.m 2      # n+1：参数个数要 +1

# ---- if ----
#   <编译条件>
#   not
#   if-goto IF_FALSE0
#   <then 语句>
#   goto IF_END0
#   label IF_FALSE0
#   <else 语句>          # 若没有 else，这里空着
#   label IF_END0

# ---- return ----
#   <编译 expression>    # void 函数则 push constant 0（栈上必须有返回值位）
#   return
```

#### 易错点清单

1. ★ **方法调用的参数个数要 +1**（`this` 占 `argument 0`），漏了栈就错位。
2. ★ **`let a[i] = expr` 的顺序**：先算 `a+i` 压栈，再编译右值，然后 `pop temp 0; pop pointer 1; push temp 0; pop that 0`。顺序反了会写到错误地址。
3. ★ **`void` 函数的 `return` 也要 `push constant 0`**（栈上必须留一个返回值的槽位，否则 `return` 的 `*ARG = 返回值` 会吃掉调用者的数据）。
4. **字符串常量**要展开成 `String.new(长度)` + 逐字符 `appendChar`，不能直接 push。
5. **对象构造**：`Memory.alloc(字段数)` → `pop pointer 0`（把返回的地址写进 THIS）→ 然后字段赋值。
6. **`this` 的段是 `pointer 0`**（不是 `this` 段的索引）。
7. **符号表要按 subroutine 重置**：每个函数开始时清空 subroutine 级表；`method` 要先把 `this` 登记为 `argument 0`。
8. **`field` 的访问**：在 method 里通过 `this k` 访问；在 constructor 里也一样（构造时 `pointer 0` 已指向新对象）。

#### 设计理念

**编译 = 树的后序遍历 + 一个栈**。表达式求值的本质就是"操作数压栈、运算符弹栈运算再压回"，所以当目标语言是栈式 VM 时，代码生成几乎是机械翻译。

**选对中间表示，后端就只剩体力活** —— 这也是为什么现代编译器（Java → 字节码、C# → IL、WebAssembly）普遍选择栈式或寄存器式的中间层，而不是直接从 AST 生成机器码。

#### 验收

```bash
python3 jackcompiler.py projects/11/Pong              # 生成 *.vm
python3 vmtranslator.py projects/11/Pong              # VM -> asm
bash tools/CPUEmulator.sh projects/11/Pong/Pong.tst
# 终极验收：projects/11/Pong 能玩起来 = 编译器 + VM + OS + 硬件全链路通
```

---

### 3.12 [ch12] 操作系统 ★ 命中 408 考点最密

**交付物**：`projects/12/` 的 8 个类 —— `Math / Memory / Screen / Output / Keyboard / String / Array / Sys`（本地均为骨架）
**核心问题**：在 16 位、无乘法器、无 GPU、无时钟、无中断的机器上，提供"现代语言"的服务。

> **复盘素材**：`tools/OS/` 下有官方 OS 的**编译产物 `.vm`**（Array/Math/Memory/Screen/Keyboard/Output/String/Sys）。**先把自己的实现写完再去看它**，否则这一章就白做了。

#### 关键路径（推荐顺序，每个类可独立单测）

```
① Memory.peek/poke -> Memory.init -> Memory.alloc/deAlloc     ★ 命中 408 内存管理
② Math.init(powersOfTwo) -> multiply -> divide -> sqrt
③ Screen.drawPixel -> drawLine（横竖分开）-> drawRectangle -> drawCircle
④ Output 字形位图 -> printChar -> printString/printInt
⑤ Keyboard.keyPressed -> readChar -> readLine -> readInt
⑥ String / Array / Sys（Sys.init 串起全部）
```

#### 实现要点

**（1）Memory：堆管理（本章最有价值的一块）**

Jack 里把 int 当 Array 用是合法的，这是 OS 实现"指针"的标准技巧：

```jack
class Memory {
    static Array heap;      // 堆基址（2048）
    static Array freeList;  // 空闲链表头

    function void init() {
        let heap = 2048;
        let freeList = heap;
        let freeList[0] = 0;              // next = null
        let freeList[1] = 14334;          // length = 14336 - 2（块头占 2 字）
        return;
    }

    function int peek(int address) {
        var Array a;
        let a = address;
        return a[0];
    }

    function void poke(int address, int value) {
        var Array a;
        let a = address;
        let a[0] = value;
        return;
    }

    // Coursera 版算法：块 = [next][length][data...]，length = 数据字数
    // 关键简化：**总是切块**，所以 freeList 永不为空
    function int alloc(int size) {
        var Array blk, prev, next;
        let blk = freeList;
        let prev = 0;
        while (~(blk = 0)) {
            if (blk[1] > (size + 1)) {          // 剩余空间够切出一个新块
                let next = blk + size + 2;      // 新空闲块起点
                let next[0] = blk[0];           // 继承 next 指针
                let next[1] = blk[1] - size - 2;// 剩余长度
                let blk[0] = 0;                 // 已分配块的 next 置空
                let blk[1] = size;
                if (prev = 0) {
                    let freeList = next;        // 摘的是头节点
                } else {
                    let prev[0] = next;         // 摘的是中间节点
                }
                return blk + 2;                 // 返回数据区基址
            }
            let prev = blk;
            let blk = blk[0];
        }
        do Sys.error(6);    // 堆耗尽
        return 0;
    }

    function void deAlloc(Array o) {
        var Array blk;
        let blk = o - 2;            // 从数据区回推块头
        let blk[0] = freeList;      // 头插法挂回空闲链表（length 字段本来就还在）
        let freeList = blk;
        return;
    }
}
```

**（2）Math：不能用 `*` 和 `/`**（否则递归调用自己）

```jack
class Math {
    static int n;              // 16
    static Array powersOfTwo;  // 2^0 .. 2^15

    function void init() {
        var int i;
        let n = 16;
        let powersOfTwo = Array.new(n);
        let powersOfTwo[0] = 1;
        let i = 1;
        while (i < n) {                              // 2^i = 2^(i-1) + 2^(i-1)
            let powersOfTwo[i] = powersOfTwo[i-1] + powersOfTwo[i-1];
            let i = i + 1;
        }
        return;
    }

    // O(n) 移位累加：逐位检查 y，累加对应的 x<<i
    function int multiply(int x, int y) {
        var int sum, shiftedX, i, neg;
        let neg = ((x < 0) = (y < 0));   // 同号为正
        let x = Math.abs(x);
        let y = Math.abs(y);
        let sum = 0;
        let shiftedX = x;
        let i = 0;
        while (i < n) {
            if (~((y & powersOfTwo[i]) = 0)) {
                let sum = sum + shiftedX;
            }
            let shiftedX = shiftedX + shiftedX;   // 左移一位 = 乘 2
            let i = i + 1;
        }
        if (neg) { return sum; } else { return -sum; }
    }
}
```

**（3）Screen：位操作（硬件没有 GPU）**

```jack
function void drawPixel(int x, int y) {
    var int addr, mask, v;
    let addr = 16384 + (32 * y) + (x / 16);   // 每行 32 字；x/16 定位字，x%16 定位位
    let mask = powersOfTwo[x & 15];           // 或用 Math 的 powersOfTwo
    let v = Memory.peek(addr);
    if (color) { do Memory.poke(addr, v | mask);  }   // 读-改-写整个字
    else       { do Memory.poke(addr, v & ~mask); }
    return;
}
```

**（4）Output：8×11 字形位图**

每个字符 = 11 个字（每字低 8 位是一行像素），需要一张 95 个字符 × 11 字的字模表（通常用 `Array` 硬编码，或用官方 `tools/OS/Output.vm` 里的做法）。`printInt` 要先转字符串算长度，`printString` 按当前光标位置逐字符画。

**（5）Sys：启动与停机**

```jack
function void init() {
    do Math.init();      // 必须先建 powersOfTwo，后面全靠它
    do Memory.init();    // 再建堆
    do Screen.init();
    do Output.init();
    do Keyboard.init();
    do String.init();
    do Array.init();
    do Main.main();
    do Sys.halt();
    return;
}
```

#### 易错点清单

1. ★★ **`Math` 的实现里绝对不能出现 `*` 和 `/`** —— 它们会被编译器翻译成 `call Math.multiply` / `call Math.divide`，造成无限递归。只能用 `+`、`-`、`&`、`|`、比较和 `powersOfTwo`。
2. ★ **`-32768` 的 `abs` 仍是 `-32768`**（补码不对称，取负溢出回自身）。
3. ★ **堆块头的定义要先定死**：书版（块 = `length` + 数据，alloc 时可能整块拿出）与 Coursera 版（块 = `next` + `length` + 数据，**总是切块**）**不能混用**。推荐 Coursera 版：freeList 永不为空，省掉"删除链表中间节点"的双指针逻辑。
4. **摘除头节点是特例**：如果用书版算法，`alloc` 找到的是链表头时没有前驱，必须单独处理（或加一个哨兵节点）。
5. ★ **改一个像素是"读-改-写整个 16 位字"**，不是只写一位。忘了读就会擦掉同行相邻 15 个像素。
6. **水平线与竖直线算法必须分开**：同一行的 16 个像素在一个字里（可批量算掩码），竖直线要访问 32 个字（行间距 32 字）。
7. **`Output` 的字模偏移要按字符的 ASCII 码算**（通常减去 32，因为 32 是空格）。
8. **`Keyboard.readChar` 必须等松键**（先 `readChar` 拿到字符，再循环等 `keyPressed() = 0`），否则按住一次会重复输入。
9. **`Sys.wait` 没有硬件时钟**：靠实测标定一个常数做忙等循环（换机器/换模拟器速度就不准）。
10. **`String` 构造时避免创建长度为 0 的 Array**（会让堆管理出现零长块，破坏链表）。
11. **`Math.divide` 里 `y * powersOfTwo[i]` 可能溢出**（y 较大时左移越界），需要先判断符号或限制 i 的起点。

#### 设计理念

**OS 是"补上硬件没做的事"的那一层**，这条线索串起了全部 8 个类：

| 硬件缺口 | OS 补丁 |
|---|---|
| 没有乘法器/除法器 | `Math.multiply` / `divide`（移位算法） |
| 没有浮点与开方 | `Math.sqrt`（二分） |
| 没有 GPU | `Screen.drawPixel` / `drawLine`（CPU 画点） |
| 没有字符发生器（字库 ROM） | `Output` 的字形位图 |
| 没有中断 | `Keyboard` 靠轮询 24576 |
| 没有 MMU / 没有 malloc 指令 | `Memory.alloc` / `deAlloc`（空闲链表） |
| 没有引导程序 ROM | `Sys.init`（bootstrap） |
| 没有硬件时钟 | `Sys.wait`（忙等 + 标定常数） |

**这就是 OS 的本质定义**：操作系统 = 硬件抽象 + 资源管理的那层软件。nand2tetris 把它做到了极简，但每一处缺口都对应着现实 OS 里的一个子系统（内存管理、文件系统、设备驱动、进程调度）。

**对 408 的直接命中**：`Memory.alloc` 的空闲链表、first-fit / best-fit、碎片与拼接 —— 这就是"动态分区分配"的实物版（408 内存管理章节的核心算法）。

#### 验收

```bash
# 每个 OS 类单独测：把 Xxx.jack 与 XxxTest/ 放同一目录
bash tools/JackCompiler.sh projects/12/MemoryTest     # 用官方编译器编你的 Memory.jack
bash tools/VMEmulator.sh                              # 加载 MemoryTest 目录，跑 .tst
# 终极验收：projects/11/Pong 用你自己的 OS 跑起来
```

---

## 4 与 Turing Complete 的对照（同一个命题的另一种解法）

Turing Complete（Steam，2021，LevelHead）也是"从 NAND 造出一台能跑程序的计算机"，但它的解法在几个关键点上和 nand2tetris 正好互补。

### 4.1 三句话定位差异

| 维度 | Nand2Tetris | Turing Complete |
|---|---|---|
| 起点 | NAND（同） | NAND（同） |
| **终点** | 一路到 **OS 与高级语言**（12 层） | 到 **自己设计的 ISA + 汇编编程**为止（没有 VM/编译器/OS） |
| **谁定规范** | 官方**给死**每一层的接口（stub + tst + cmp） | **你自己定**：指令编码、寻址方式、内存布局全是你的决定 |
| **验收标准** | 功能正确即可 | **门延迟 / 门数 / tick** 三档评分（有优化压力） |
| **时序** | 抽象掉（DFF 就是"一个周期"） | **显式**：延迟线、奇数 tick、循环依赖是正式关卡 |
| 形态 | 教材 + 项目（免费） | 游戏（付费，有剧情/音乐/存档） |

### 4.2 关卡路线与 nand2tetris 章节的映射

```
TC: Basic Logic        NAND -> NOT/AND/OR/XOR/NOR/XNOR/大位宽  <-> nand2tetris ch1
TC: Arithmetic         半加器/全加器/字节加/负数/取负/乘法/除法  <-> ch2（+ ch12 的 Math）
TC: Components         开关/译码器/选择器/寄存器/逻辑引擎/算术引擎 <-> ch3
TC: Architecture       指令译码 / 程序 / 条件 / 立即数 / RAM / 栈  <-> ch4 + ch5 ★
TC: Programming        在自己的 CPU 上写汇编解谜题                <-> ch4（+ ch6 自写汇编器的感觉）
TC [终点]              图灵完备达成（能算一切可计算函数）          <-> nand2tetris 到 ch5 就已是图灵完备
```

**一个有意思的分界线**：nand2tetris 造完 **ch5 的 Computer** 就已经是图灵完备的机器了（能跑任意程序），后面 7 章全是在它上面堆"好用"。Turing Complete 的游戏终点恰好也在这条线上 —— 所以如果你只想理解"计算机为什么能计算"，**TC 通关 ≈ nand2tetris 前 5 章**。

### 4.3 TC 补上了 nand2tetris 缺的那一维：性能与自主设计

nand2tetris 完全不谈"这个 ALU 要几个门延迟"、"这样连会不会形成组合环"—— 它只保证功能对。TC 把这变成核心玩法：

- **延迟（delay）**：你的电路从输入到稳定需要多少 tick，直接影响关卡评分。这是 **408 "CPU 性能 = 指令数 × CPI × 时钟周期"** 里最底下的那一层（关键路径决定主频上限）。
- **门数（gate count）**：社区比的是"谁能用最少的门造出同样的功能"—— 这是**面积优化**，对应硬件设计的成本维度。
- **自己定 ISA**：TC 里你必须决定"这个字节的哪几位是操作码、哪几位是寄存器号"，而 nand2tetris 里 Hack 的指令格式是给定的。**自己决策一遍，你才会明白为什么 Hack 要把 `a` 位放在那里。**

**复习建议**：用 TC 的视角回看 nand2tetris 的 ch5 —— 问自己三个 nand2tetris 不会问的问题：
1. 这条指令的关键路径经过几级 Mux？
2. 如果把 A 寄存器和 D 寄存器的写回做成并行，周期能不能更短？
3. Hack 为什么不做流水线？（答案：做完整机后你会看到，取指和执行共用一条数据通路，切不开 —— 这正好是 408 流水线冒险与吞吐率的反面教材。）

---

## 5 408 对照总表（本仓视角：这个项目能覆盖哪些考点、不能覆盖哪些）

| 408 章节（ipynb） | nand2tetris 覆盖点 | 覆盖强度 |
|---|---|---|
| 00-计算机系统概述 | 冯·诺依曼 vs **哈佛（Hack 是哈佛）**、性能指标的实物对照、层次结构 | ★★★ |
| 01-数据表示与编码 | 16 位补码、符号扩展、位运算（屏幕位掩码） | ★★ |
| 02-运算与ALU | HalfAdder→行波进位、补码加减统一、ALU 控制位与标志（zr/ng） | ★★★ |
| 03-存储层次与Cache | **不覆盖**（无 Cache、无命中率），但"RAM 层级递归构造"可助理解存储器扩展 | ☆ |
| 04-内存与虚拟内存 | **堆管理（freeList / first-fit / best-fit / 碎片）** ★、地址空间布局（256 栈 / 2048 堆） | ★★★（ch12） |
| 05-磁盘与文件系统 | 不覆盖（无文件系统） | ☆ |
| 06-指令系统与汇编 | A/C 指令格式、**寻址方式（立即/直接/间接 M=RAM[A]）**、符号表与两遍汇编、**栈帧与调用约定** | ★★★★（ch4/6/7/8） |
| 07-CPU与数据通路 | **指令译码 → 控制信号、单周期数据通路、PC 装载条件、寄存器写回** | ★★★★★（ch5） |
| 08-流水线 | **不覆盖**（单周期，无冒险概念） | ☆ |
| 09-总线与IO | **内存映射 I/O / 统一编址**、键盘轮询（对比中断/DMA）、显示位图 | ★★★（ch4/12） |
| 10-进程与线程 | 运行时栈与栈帧（对比进程地址空间）、OS 的角色（对比进程管理） | ★★ |
| 11-调度 / 12-同步 / 13-死锁 | 不覆盖（单程序、无并发） | ☆ |
| 14-17 网络 | 不覆盖 | ☆ |
| 18-22 数据结构与算法 | 链表（Jack List）、堆管理算法、位运算技巧 | ★★ |
| 23-计算机数学基础 | 编译原理相关（递归下降、符号表、栈式求值）可归此处或 06 | ★★ |

**一句话**：nand2tetris 是 **00 / 01 / 02 / 04 / 06 / 07 / 09** 这七块的实物教程，**03 Cache、08 流水线、11-13 OS 并发、14-17 网络**它完全不碰。冲刺期别指望它替代这几块的刷题。

### 5.5 反查表：408 考点 → nand2tetris 实物记忆锚点 ★

> 用法：这张表是给**刷题时**用的 —— 遇到下面任何一个考点，先回忆右边那个实物，再答题。
> 实物记忆比背诵牢靠一个数量级，因为它带因果（"为什么这样"）而不只是结论（"是什么"）。

| 408 考点 | nand2tetris 实物 | 记忆锚点（一句话） |
|---|---|---|
| 补码表示与溢出 | `-32768` 取负回自身 | 补码区间不对称 $[-2^{15},\ 2^{15}-1]$，**负数比正数多一个**，最小值取负必溢出 |
| 加法器（串行进位） | `Add16` 行波进位链 | 进位像波浪逐位传：简单但慢；**超前进位 = 用更多门换更短关键路径**（空间换时间） |
| ALU 与标志位 | `zr`/`ng` 直通跳转逻辑 | Hack **没有标志寄存器**；x86 的 PSW 本质就是把 `zr`/`ng` **存下来复用**（为了"先算后判"） |
| 寻址方式 | `@100`（立即）、`D=M`（间接） | 立即寻址 = 常量在**指令里**；`M = RAM[A]` 就是**间接寻址**（地址在寄存器里）—— 两种指令覆盖三种寻址 |
| 指令周期与微操作 | ch5 单周期数据通路 | 取指（`ROM[pc]`）→ 译码（位段拆开）→ 执行（ALU）→ 写回（dest 三位）—— **一个周期内做完，没有流水** |
| CISC vs RISC | Hack 的 2 格式 ISA | RISC 三要素：少指令、定长、load-store。Hack 有前两条但**不是** load-store（`M` 直接参与运算）—— 用它记住 load-store 的判据 |
| 统一编址 vs 独立编址 | 屏幕键盘就是 RAM 地址 | 统一编址：访存指令即 I/O 指令，**不需要 IN/OUT**，代价是吃地址空间；独立编址反之 |
| 程序查询 / 中断 / DMA | 键盘轮询 `RAM[24576]` | 轮询 = CPU 全程盯着（烧算力）；中断 = 设备主动叫人（CPU 能睡）；DMA = 连搬运都外包。**nand2tetris 停在第一级**，后两级正是为解决它的痛点而生 |
| 动态分区分配 | `Memory.alloc` 空闲链表 | first-fit 快但碎片、best-fit 碎片小但慢；**总是切块**（Coursera 版）⇒ freeList 永不空，省双指针删除 |
| 内碎片 vs 外碎片 | 切块产生的"边角料" | **外碎片** = 空闲块太碎凑不出大块（空闲却不可用）；**内碎片** = 分给它的比要的大（已分配却浪费） |
| 进程/程序地址空间布局 | RAM 布局：static 16 起、栈 256 起、堆 2048 起 | 真实进程 = 代码段 + 数据段 + **堆向上长 + 栈向下长**；Hack 的布局是它的微缩模型（栈只向上长，因为没有开线程/递归深到碰头） |
| 栈帧与过程调用 | call/return 五槽 | 返回地址在 `FRAME-5`（帧底），`LCL` 就是**帧指针**（x86 的 rbp），`ARG` 是参数指针；无参调用时 `*ARG` 会覆盖返回地址 —— 这就是为什么真实 ABI 在返回地址下面还留对齐槽 |
| caller-save vs callee-save | call 保存 LCL/ARG/THIS/THAT | call **无条件保存 4 个**（全 caller-save 的极端版）；真实 ABI 是**混合**：热寄存器 callee-save、冷寄存器 caller-save —— 省保存次数 |
| 虚拟内存 / 页表 / TLB | **完全缺席**（裸物理地址） | 反面锚点：MMU 解决的是"多程序隔离 + 程序大于内存"，Hack 单程序 32K 两个都不需要 —— **缺什么才造什么** |
| 流水线与冒险 | 单周期切不开 | 取指与执行**共用一条数据通路**（A 寄存器既当地址又当数据），物理上没法重叠 —— 对照：流水线要求**取指部件与执行部件物理分离**（I-Mem / D-Mem 分开或 Harvard 化） |
| 冯·诺依曼 vs 哈佛 | ROM32K 与 RAM 两条空间 | Hack 是**哈佛**：取指与取数并行、单周期可行；代价是**不能自修改代码、程序必须预烧** —— 冯·诺依曼的"指令数据同空间"换来的是**可加载程序**（这正是操作系统引导的物理前提） |
| 存储层次 | 完全平坦（无 Cache） | 反面锚点：Cache 吃的是"局部性"红利；Hack 没有 Cache 不是不需要，而是 32K 字一次性放得下 —— **层次结构的每一层都是为了"下一层太慢"而存在** |
| 指令系统设计权衡 | Hack 的 `a` 位与 2 寄存器 | 一切极简的代价都转嫁给了**软件**（编译器/汇编程序员）：`RAM[i]+RAM[j]` 要 6 条指令 —— 记住"ISA 是硬件与软件的**合同**，简化谁谁买单" |

---

## 6 复习执行方案

### 6.1 ROI 排序与理由

| 优先级 | 章节 | 时间预算 | 为什么值 |
|---|---|---|---|
| P0 | **ch5 整机** | 3–4 h | 408 组成原理 CPU 数据通路一击命中；做完后"指令周期"不用背 |
| P0 | **ch8 函数调用** | 4–6 h | calling convention 是 06/10 的核心难点，也是唯一能反哺 x86 栈帧理解的部分 |
| P1 | ch1–ch3 硬件基础 | 3–4 h | 量小、有官方 tst 自动验收，是 ch5 的前置 |
| P1 | **ch12 Memory + Screen** | 4–6 h | 堆管理 ↔ 04 内存管理；位图显示 ↔ 09 I/O（408 命中率最高的一章） |
| P2 | ch7 VM I | 2–3 h | ch8 的前置，且"段映射"能解释编译器视角的内存 |
| P2 | ch4 汇编 | 1–2 h | 只写 Mult.asm 即可，Fill.asm 选做 |
| P3 | ch6 汇编器 | 3–4 h | 独立性强可随时做；两遍扫描是通用技能 |
| P3 | ch9–ch11 编译器与 Jack | 6–10 h | 量大，概念密度低；第 9 章有旧代码可复盘（看 `List.jack`） |
| — | ch12 的 Output 字形位图 | 2 h | 有意思但与 408 关系小，冲刺期可跳过 |

**冲刺期建议总量**：约 **20–30 h** 覆盖 P0–P2（ch1-5 + ch7-8 + ch12 部分），P3 只做设计复盘不动手。

### 6.2 重建顺序（执行级）

```
[step 0] 环境体检：确认 Java 可用（tools/*.sh 都依赖 Java）
         $ cd ~/develop/learning/learning-408/nand2tetris && java -version
         $ bash tools/HardwareSimulator.sh          # 能弹出 GUI 才算通

[step 1] ch1：只挑 5 个做（Not / And / Or / Mux / DMux），16 位与多路版用官方 builtIn 顶着
         $ bash tools/HardwareSimulator.sh projects/1/And.tst

[step 2] ch2：HalfAdder -> FullAdder -> Add16 -> Inc16 -> ALU（ALU 必做，前面可用 builtIn）
         $ bash tools/HardwareSimulator.sh projects/2/ALU.tst

[step 3] ch3：Bit -> Register -> PC（必做）；RAM 只做 RAM8，64/512/4K/16K 直接抄官方 builtIn 思路
         $ bash tools/HardwareSimulator.sh projects/3/a/Register.tst

[step 4] ch5：Memory.hdl -> CPU.hdl -> Computer.hdl ★ 用 CPU-external.tst / ComputerAdd.tst / ComputerMax.tst / ComputerRect.tst 验收
         $ bash tools/HardwareSimulator.sh projects/5/CPU.tst
         $ bash tools/CPUEmulator.sh projects/5/ComputerAdd.tst

[step 5] ch7+ch8：新开一个目录写 VMTranslator（Python 推荐），用 projects/7,8 的官方 .tst/.cmp 验收
         $ python3 vmtranslator.py projects/8/FunctionCalls/NestedCall
         $ bash tools/CPUEmulator.sh projects/8/FunctionCalls/NestedCall/NestedCall.tst

[step 6] ch12：先 Memory（只有它命中 408），再 Screen.drawPixel/drawLine，Output 与 Keyboard 选做
         $ bash tools/JackCompiler.sh projects/12/MemoryTest      # 用官方编译器编你的 OS
         $ bash tools/VMEmulator.sh                                # 加载目录跑 MemoryTest.tst

[step 7] ch4/ch6/ch9-11：冲刺期只做设计复盘（读 §3 对应小节 + 官方规范），不新写
```

### 6.3 验收命令速查

| 层 | 工具 | 命令（在 `learning-408/nand2tetris/` 下执行） |
|---|---|---|
| ch1-3, ch5 | HardwareSimulator | `bash tools/HardwareSimulator.sh projects/<章>/<名>.tst` |
| ch5 整机 | CPUEmulator | `bash tools/CPUEmulator.sh projects/5/ComputerAdd.tst` |
| ch6 汇编器 | 自写 + CPUEmulator | 先生成 `.hack`，再用 `bash tools/CPUEmulator.sh` 载 `.tst` |
| ch7-8 VM | 自写 translator + CPUEmulator | `bash tools/CPUEmulator.sh projects/8/.../NestedCall.tst` |
| ch12 OS | 官方 JackCompiler + VMEmulator | 把 `Xxx.jack` 与 `XxxTest/` 放同一目录 → `bash tools/JackCompiler.sh <dir>` → VMEmulator 载 `.tst` |
| 文本比对 | TextComparer | `bash tools/TextComparer.sh out.cmp ref.cmp` |

### 6.4 三条冲刺期纪律

1. **不要 1→12 顺着做。** ch6（汇编器）和 ch10/11（编译器）是纯工程量，概念在 §3 里读完即可；把时间留给 ch5 / ch8 / ch12。
2. **每层做完立刻跑官方 `.tst` 与 `.cmp`。** nand2tetris 的契约精确到引脚电平，比对通过就是真的对，不需要你自己判卷 —— 这是它相对刷题的最大效率优势。
3. **做完 ch5 回头补一张"408 反查表"**：把你在 CPU.hdl 里连的每一根线，对应到 408 的一个名词（取指/译码/执行/写回、微操作、数据通路、控制信号）。这张表比任何笔记都好用。

---

## 7 附：动手前的检查清单

- [ ] `java -version` 有输出（否则 `tools/*.sh` 全部跑不起来）
- [ ] `bash tools/HardwareSimulator.sh` 能弹出 GUI（macOS 上需要允许 Java 的辅助功能权限）
- [ ] 确认 `projects/` 里的骨架文件是**官方原始状态**（§1.6），不要误以为自己写过又找不到了
- [ ] 决定 ch6/7/8/10/11 的翻译器用哪种语言写（建议 Python 3，本次复习统一）
- [ ] 决定 ch12 的堆管理用**书版**还是**Coursera 版**算法（先定死，不要中途改 —— 两者块头定义不同）
- [ ] 每完成一层，按 `AGENTS.md` 把知识点**追加**到对应 ipynb（01 / 02 / 04 / 06 / 07 / 09 / 10），并更新 `PROGRESS.md` 的实践线行

---

## 8 求职视角：这个项目怎么帮你找工作

> **时间线先说清**：现在（2026-10）到初试（12 月下旬）**一切以考研为重**，这一节是"素材预存"—— 初试结束到春招/暑期实习之间有大约两个月的窗口，届时按本节直接取用，不用回忆。
> 适用对象：系统/基础架构/嵌入式/编译器方向的开发岗与实习。算法岗与业务岗帮助有限。

### 8.1 简历怎么写（一句话 + 三条 bullet）

**定位原则**：这是**教学项目**，别包装成工程项目。面试官一眼能认出 nand2tetris —— 但他们真正想看的不是"你做完了"（烂大街），而是**你理解到什么深度、能不能讲出权衡**。所以 bullet 要写"理解"而不是"完成"。

```
Nand to Tetris：从 NAND 门到操作系统的全栈计算机系统（个人项目，2024；2026 年系统重修）
- 从 NAND 门起逐层构建 16 位计算机：ALU / 时序电路 / 单周期 CPU / 汇编器 / 栈式 VM /
  编译器 / Jack OS，贯通硬件到软件的 12 层抽象
- 实现 Hack CPU 的指令译码与单周期数据通路（A/C 双指令格式、内存映射 I/O、
  无标志寄存器的条件跳转），并用官方测试脚本逐层验收
- 用 Python 重写 VM 翻译器：基于栈帧 calling convention 生成 call/return 代码序列，
  理解 caller-save/callee-save 与真实 ABI（System V）的对应
```

英文版（投外企/实习用）：

```
Nand to Tetris: full-stack computer system from NAND gates (personal project)
- Built a 16-bit computer bottom-up across 12 abstraction layers: ALU, sequential
  logic, single-cycle CPU, assembler, stack-based VM, compiler, and a Jack OS
- Implemented instruction decoding and the single-cycle datapath of the Hack CPU
  (dual instruction format, memory-mapped I/O, flagless conditional jumps),
  verified layer by layer against official test scripts
- Rewrote the VM translator in Python: emits call/return sequences based on the
  stack-frame calling convention; mapped it onto caller/callee-save registers in
  real ABIs (System V AMD64)
```

**写法红线**：不要写"实现了 30+ 芯片""代码量 X 行"（教学项目的量不加分）；**要写你做出的非默认选择**（比如"堆管理选择了 always-split 策略以简化空闲链表删除"）。

### 8.2 面试高频题与"面试官想听什么"

**硬件 / 体系结构（5 题）**

| 问题 | 面试官想听什么（按此顺序答） |
|---|---|
| 为什么 NAND 是（函数）完备的？ | `Not = Nand(x,x)`，`And = Not(Nand)`，而 {And, Or, Not} 完备 ⇒ 任意真值表可实现。加分项：**物理上 NAND 晶体管实现最省**（4 管），所以工程与数学在这里相遇 |
| 行波进位与超前进位的区别？ | 行波 = 进位逐位串行（关键路径 O(n) 级门延迟）；超前进位 = 用递推式 $c_{i+1} = g_i + p_i c_i$ 展开并行算进位 —— **空间换时间**，n 大时硬件爆炸，所以有分组超前进位（16 位 = 4 组 4 位） |
| 你的 ALU 怎么设计的？ | 6 控制位（zx/nx/zy/ny/f/no）两级变换 + Add/And 二选一 + 终态取反；18 种运算 = 6 位的组合。**落点**：这就是"用正交控制位组合出操作"，是 RISC 微指令思想的雏形 |
| 单周期为什么不能流水化？你打算怎么改？ | 取指与执行**共用 A 寄存器与数据通路**，物理切不开。改造：取指部件独立（I/D 分离或 Harvard 化）→ 按取指/译码/执行/写回切段加流水寄存器 → 然后依次处理结构/数据/控制冒险（转发、停顿、分支预测）。**这题答好 = 半个体系结构岗 offer** |
| CISC 和 RISC 的区别？ | 别背"复杂 vs 精简"。答权衡：指令密度 vs 译码复杂度；变长 vs 定长；**内存操作数 vs load-store**。用 Hack 反证：它定长、双格式，但 `M` 直接参与运算所以不算严格 RISC —— 说明 load-store 才是本质判据 |

**编译 / 运行时（4 题）**

| 问题 | 面官想听什么 |
|---|---|
| 函数调用在机器层面发生了什么？ | 按栈帧五槽讲：压返回地址 + 保存寄存器 → 重定位参数指针与帧指针 → 跳转；返回时**先抢救返回地址**（无参调用时 ARG 与返回地址重叠）、写返回值、恢复现场、跳回。**落点**：栈帧是软件契约，硬件只看到栈伸缩 |
| caller-save 和 callee-save 是什么？为什么两种都要？ | 谁保存谁买单。全 caller-save（Hack）太浪费（每次 call 存 4 个）；全 callee-save 也浪费（叶子函数被迫保存）。混合策略 = 热寄存器（跨调用常驻）callee-save，冷寄存器 caller-save —— **ABI 是性能与简洁的折中** |
| 为什么需要 VM / 中间字节码这层？ | 1) 解耦：编译器不必知道目标机（跨平台，JVM/LLVM IR 同理）；2) 降复杂度：编译器只管生成栈操作，寄存器分配下推给 VM 翻译器；3) 语言的运行时服务（GC、安全检查）可以集中在一层实现 |
| 表达式 `a + b * c` 怎么编译成代码的？ | AST 后序遍历 + 栈：`push a; push b; push c; mul; add`。**落点**：中缀→后缀的机械性正是栈式 VM 存在的理由；寄存器机上才需要指令调度与寄存器分配 |

**操作系统（4 题）**

| 问题 | 面官想听什么 |
|---|---|
| malloc 怎么实现？（高频！） | 用 ch12 堆管理答：空闲链表 + first-fit/best-fit + 切块与合并；再升级谈真实世界：glibc 的 bins（fastbin/smallbin/largebin 分级）、slab/tcmalloc 的线程本地缓存、**内碎片 vs 外碎片**的对策（边界标记、size class）。nand2tetris 给的是"骨架"，真实 malloc 是"骨架 + 三层优化" |
| 内碎片和外碎片？ | 外 = 空闲但凑不出大块（对策：合并、伙伴系统）；内 = 已分配但用不满（对策：size class 按 2 的幂/16B 对齐）。**用切块策略举例**：always-split 天然制造外碎片 |
| 中断是什么？没有中断行不行？ | 行 —— 轮询（Hack 键盘）。代价：CPU 空转、响应延迟不稳定。中断的价值 = **把"等设备"变成事件驱动**，CPU 可以睡（省电）或干别的（并发）。DMA 再进一步：连"搬运完成前的每次中断"都省了 |
| 操作系统的本质是什么？ | 用 ch12 的"硬件缺口补丁表"答：**OS = 硬件抽象 + 资源管理**。缺乘法器 → Math 库；缺 MMU → 自己管堆；缺中断 → 轮询。真实 OS 的每个子系统（进程/文件/网络栈）都对应一类缺口 —— 这个回答会让面试官记住你 |

### 8.3 与工业界的差距（主动讲出来反而加分）

面试最忌被追问"这和真实的有何不同"时哑火。主动亮出边界：

1. **HDL 不可综合**：nand2tetris 的 HDL 只用于仿真（门级结构描述、无时序约束），不是 Verilog/VHDL —— 拿它写的 CPU 上不了 FPGA。
2. **无流水线 / 无 Cache / 无虚存 / 无中断**：这四块恰好是现代 CPU 设计的四大主战场（对照 CS149 与《计算机体系结构：量化研究方法》）。
3. **OS 是"语言运行时"**（类似 libc + JVM），不是管理多道程序与并发的内核 —— **没有调度、没有隔离、没有系统调用陷入**。
4. **单地址空间单程序**：没有进程抽象，也就没有保护。

**话术模板**："这个项目给我的地图上有四块空白（流水线/Cache/虚存/中断），我已经知道它们各自解决什么问题，接下来准备用 ×× 补上。" —— 诚实的边界感 + 明确的下一步 = 加分项。

### 8.4 五条延伸路径（把教学项目升级成简历亮点）

按性价比排序，初试后挑**一条**深挖即可：

1. **加流水线**（最推荐）：给 Hack 加 5 级流水 + 转发 + 分支预测，量化 IPC 提升。与 CS149 的 ILP 主题直接衔接，面试故事完整（"我知道单周期为什么不行 → 我改了 → 我测出来了"）。
2. **Verilog/Chisel 重写 + FPGA**：把 ch1–5 的设计翻译成可综合的 Verilog 上板（iCE40/Arty 大约几百元）。嵌入式岗的直接敲门砖。
3. **换 RISC-V RV32I 子集**：用开源工具链（riscv-gcc/Spike）替代自制工具链，学的是真实 ISA 与真实 ABI。
4. **写全套测试**：给自己 12 层的每一层写回归测试 + fuzzing（汇编器喂随机符号表）。测试能力在所有岗位都被低估且稀缺。
5. **性能测量**：统计自己 CPU 的门数 / 关键路径 / 指令周期数，做 CPI 分析 —— Turing Complete 的评分维度（门数/延迟/tick）就是现成的 metric 框架。

### 8.5 系统设计面试的连接点

三个高频系统设计话题可以直接调用本项目的实物经验：

- **"设计一个内存分配器"**：ch12 的空闲链表是标准答案的骨架，往上加 size class / 分级 bins / 线程缓存就是满分结构。
- **"跨语言调用 / FFI 为什么慢"**：本质是两套 calling convention 的翻译（ch8 的五槽在两边长得不一样，要 thunk/胶水层）。
- **"零拷贝 / 高性能网络 I/O"**：内存映射 I/O 的思路延展 —— 把"数据搬运"从 CPU 指令流里拿掉（MMIO → DMA → user-space driver/DPDK 是同一条进化线）。

### 8.6 一句话总结

> **nand2tetris 在简历上的价值不是"你做完了什么"，而是它给了你一张 12 层的地图 + 每层的实物记忆**。面试时你能从任何一个上层概念（malloc、虚函数、系统调用）向下钻到底层门电路，也能从任何一个底层细节向上讲出它服务的抽象 —— **这种"全栈穿透力"恰恰是系统岗最难从别的项目里获得的。**

---

## 迁移归档：来自旧 ipynb 的工程笔记（2026-10-28）

## 冯·诺依曼 vs 哈佛：Hack 是一个活的反例

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- 冯·诺依曼的核心：**指令与数据同等地位、共存于同一存储器** → 程序可以被当作数据加载与修改（这是「操作系统引导程序」的物理前提）
- nand2tetris 的 Hack 是**哈佛结构**：ROM32K（指令）与 RAM（数据）是**两条独立地址空间**，CPU 用 `pc` 取指、用 `A` 取数
- 哈佛的收益：取指与取数**并行**，单周期可行（天然无取指/访存的结构冒险）
- 哈佛的代价：**不能自修改代码，程序必须预先烧入 ROM** —— 没有「把程序加载进内存再执行」这回事
- 408 判断题套路：「指令存储器与数据存储器分开」→ 哈佛；「指令与数据共用同一存储器」→ 冯·诺依曼；「Von Neumann 机上取指与访存会争用总线」→ 对
- 记忆锚点：**冯氏换来的「可加载性」，恰好是 Hack 缺的东西** —— 两者的取舍是同一枚硬币的两面

---

## 补码与位掩码：nand2tetris 里的两个硬事实

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- Hack 是 **16 位补码整数**，没有浮点。补码不对称：`-32768` 取负仍是 `-32768`（溢出回自身），`Math.abs` 必须单独处理这个边界
- 屏幕内存 `16384–24575` 共 8K 字，**1 bit = 1 像素**：512×256 像素、每行 32 字 → 由 `x/16` 定位字、`x%16` 定位位
- **改一个像素必须「读-改-写整个 16 位字」**：`v | mask` 置黑、`v & ~mask` 置白；只写一位会擦掉同行相邻 15 个像素
- 由此推出：水平线与竖直线算法必须分开写 —— 同行 16 个像素在同一字里（可批量算掩码），竖直线要跨 32 个字（行间距 32 字）

---

## ALU 的 6 个控制位：一套「微指令」

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- ALU 用 `zx nx zy ny f no` 六个控制位组合出 **18 种运算**：先改造 x/y（置零/取反），再用 `f` 选「加 or 与」，最后 `no` 取反
- 只需记住一个恒等式 $!z = -z - 1$：`x-1` = y 置 0 再取反得 $-1$ 后相加；`x-y` = `!x + y` 再取反；`x|y` = 德摩根 $!(!x \& !y)$
- **补码让加减共用一套电路**：机器里只有加法器、没有减法器（$-y = \,!y + 1$）
- 标志 `zr`/`ng` 必须**对最终 out 判定**（即 `no` 取反之后）；顺序错了 $!0$ 会被判成非零，跳转全错
- Hack 的 ALU **不检测溢出**：`32767+1` 静默回绕成 `-32768`。与 408 「溢出判断」考点互为对照（教学取舍，非疏漏）

---

## 堆管理：空闲链表与切块策略（ch12 ↔ 动态分区分配）

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- 堆范围 `2048–16383`；块头 = `[next][length]`，`length` 计数据字数，块总长 = `length + 2`
- `alloc`：遍历空闲链表找够大的块 → **总是切块**（Coursera 版算法），剩余部分留在链表上，因此 `freeList` 永不为空，省掉「删除链表中间节点」的双指针逻辑
- 摘除头节点是特例（无前驱），必须单独分支或加哨兵；书版算法（可能整块拿出）与 Coursera 版（总切块）**块头定义不同，不能混用**
- `deAlloc`：从数据区地址回推 `blk = o - 2`，头插法挂回链表（`length` 字段本来就还在）
- 碎片：切块策略天然产生外碎片；改进 = 按地址有序插入 + 相邻块合并（defrag）
- 对应 408：动态分区分配、首次适应 / 最佳适应、碎片与拼接 —— 这就是「内存管理」那一章算法的实物版

---

## Hack 指令格式：两种指令、两个寄存器

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- A-指令 = `0` + 15 位常量（装入 A）；C-指令 = `111a cccccc ddd jjj`（`a` 位在 A/M 之间选运算源，comp 6 位，dest 3 位 = A/D/M，jump 3 位 = <0 / =0 / >0）
- 只有 **D（数据）** 与 **A（地址/数据）** 两个寄存器，`M` 恒指 `RAM[A]`
- **一条 C-指令里 A 与 M 不能同时当运算源**（被 `a` 位二选一限制）：想用 `M` 参与运算必须先 `D=M`
- **跳转目标必须先装进 A**：硬件上 PC 的输入只有 A 寄存器这一条路
- **没有标志寄存器**：跳转直接看 ALU 输出的 `zr`/`ng` 组合，不做「先算再判断别的事」
- 汇编器两遍扫描的根因是前向引用：第一遍只建标签表（`(LABEL)` 不推进 ROM 地址），第二遍才翻译并把变量从 RAM 16 起分配

---

## 栈帧是软件契约：call / return 的五个槽

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- `call f k` 压入 5 槽：返回地址、LCL、ARG、THIS、THAT → 再令 `ARG = SP-5-k`、`LCL = SP`
- `return` 五步：`FRAME = LCL` → `RET = *(FRAME-5)` → `*ARG = 返回值`、`SP = ARG+1` → 恢复 THAT/THIS/ARG/LCL → 跳 RET
- ★ **无参数调用时 `ARG[0]` 就是 `FRAME-5`**：`RET` 必须在写返回值之前取走，否则返回地址被返回值覆盖（本章第一号杀手）
- 标签规则：`goto/label` 要加 `函数名$` 前缀，`function` 定义标签**不加**前缀；翻译 `return` 时不要重置当前函数名（一个函数可能有两个 return）
- `R13/R14/R15` 是易失的临时寄存器，任何被调用函数都可能改掉它们
- 对比 408 / x86：caller-save 与 callee-save 是同一问题的另一种答案；**硬件只看到栈在长长短短地变化，「函数」这个概念完全由软件约定支撑**

---

## 单周期数据通路：把指令位段接到控制线上

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- CPU 接口：`inM`（= `RAM[A]`）、`instruction`、`reset` → `outM`、`writeM`、`addressM`、`pc`
- **A 寄存器的 load = 「是 A 指令」OR「dest 含 A 位」**；只写前者会导致 C-指令的 `AMD` 组合写不进 A
- `writeM = i[15] AND dest 的 M 位`：A-指令没有 dest 字段（那几位是常量），不屏蔽会误写内存
- ALU 的 `x` 恒接 D 寄存器，`y` 由 `a` 位在 A/M 间选；`addressM` = A 寄存器的输出（不是 PC）
- PC：`inc` 恒 1，`load` = 跳转条件成立，优先级 `reset > load > inc`
- 时序：`outM`/`writeM` 是**组合**的（当周期有效），`addressM`/`pc` 是**时钟**的（下周期生效）
- 这台 CPU **没有微程序、没有状态机**：译码 = 位段直连控制线。代价是完全没有流水线 —— 取指与执行共用一条数据通路，切不开

---

## 内存映射 I/O：把设备做成一段地址

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- Hack 地址空间：`0–16383` RAM，`16384–24575` 屏幕，`24576` 键盘，`>24576` 无效；译码只看 `address[14]/[15]/[13]` 三位
- Screen 芯片只吃 **13 位地址**（8K = $2^{13}$），送进去的是 `address[0..12]` 而不是原地址
- **统一编址的收益**：不需要 IN/OUT 指令，访存指令即 I/O 指令；代价是占用地址空间
- **键盘没有中断**：只能轮询 `RAM[24576]`；`readChar` 必须等松键（先取字符再等 `keyPressed() = 0`），否则按住一次重复输入
- 对比 408：程序查询方式 vs 中断方式 vs DMA —— nand2tetris 只有第一种，正因如此才能看清后两种被发明出来是为了解决什么

---

## OS 的本质：硬件缺口的补丁（nand2tetris ch12 的两句话定义）

> 2026-10-22 · 来源：nand2tetris 项目复习（`projects/nand2tetris/NOTES.md`）
- Jack OS 的 8 个类**逐一对应一个硬件缺口**：无乘法器 → Math 库；无 MMU/malloc 指令 → Memory.alloc 堆管理；无 GPU → Screen 位图绘制；无字库 ROM → Output 字形；无中断 → Keyboard 轮询；无引导程序 → Sys.init
- 由此得到 OS 的两句话定义：**硬件抽象 + 资源管理**（把「硬件不会做的事」补上，把「有限的硬件」分好）
- 但 Jack OS **不是现代内核**：单程序、单地址空间、无并发、无隔离、无系统调用陷入 —— **没有「进程」这个抽象**
- 对照真实 OS：每一类缺口长大后都变成了子系统（调度器、文件系统、网络栈、驱动模型）
- 与本模块的连接：**「进程」补的是「并发 + 隔离」这两个缺口** —— Hack 的单程序时代不需要它；多道程序一出现，进程（与线程、调度、同步）就全被逼出来了

---
