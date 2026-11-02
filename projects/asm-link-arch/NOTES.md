# asm-link-arch · 分章详细

## 第 1 章 从 C 到机器码：预处理、编译、汇编、链接各自产出什么

**要解决的问题**：把“一段 C 源码”到“能跑的可执行文件”之间的黑盒拆成四段可验证的产物。不解决这个，后面讨论符号解析、栈帧、PLT 都缺一个立足点——你无法说清“undefined reference”到底是哪个阶段的哪张表没配上。

**机制**

四步各有一个明确的输入输出契约，产物都是磁盘上可观察的文件：

| 阶段 | 工具 | 输入 | 输出 | 关键动作 |
|---|---|---|---|---|
| 预处理 | `cpp`（`gcc -E`） | `.c` / `.h` | `.i` 纯 C 文本 | 展开 `#include`、宏替换、条件编译、去注释 |
| 编译 | `cc1`（`gcc -S`） | `.i` | `.s` 汇编文本 | 词法/语法/语义分析 → IR → 优化 → 指令选择与寄存器分配 |
| 汇编 | `as`（`gcc -c`） | `.s` | `.o` 可重定位目标文件 | 汇编指令编码成机器码，未定地址留重定位项 |
| 链接 | `ld` | 多个 `.o` + `.a`/`.so` | 可执行文件 / `.so` | 符号解析 + 重定位 + 段合并 |

三个必须记住的事实：

1. **预处理是纯文本替换**，不理解 C 语法。宏没有类型，`#define SQR(x) x*x` 在 `SQR(1+2)` 上展开成 `1+2*1+2`，这是替换而非求值。
2. **编译器只保证“单个翻译单元内可见”的东西**。一个 `.c` 加上它 include 的头文件构成一个翻译单元（TU）。函数体没写、只有声明，编译阶段完全合法——编译器只需知道签名来生成调用序列，地址填 0 占位，把填地址的活留给链接器。这就是为什么 `gcc -c` 能成功而 `gcc` 整体失败。
3. **`.o` 里的符号分强弱**。`.text` 中定义的函数是强符号（`STB_GLOBAL` + 已定义），只有声明的是未定义符号（`SHN_UNDEF`）；`static` 函数是局部符号（`STB_LOCAL`），不参与跨文件解析；`__attribute__((weak))` 产生弱符号（`STB_WEAK`）。

链接器的符号解析规则（ELF / GNU ld 语义）：

```text
对每个未定义符号 U：
  在输入的所有 .o 与 .a 中找同名强符号定义
  - 恰好一个强定义        → 绑定到它
  - 零个，但有弱定义      → 绑定到弱定义（弱符号可被强符号覆盖）
  - 零个，什么都没有      → undefined reference to `U'
  - 两个及以上强定义      → multiple definition of `U'（符号冲突）
```

`undefined reference` 的真实原因只有两种：**（a）确实没有任何目标文件提供该符号定义**——最常见是漏了库或库顺序错（`-lfoo` 必须放在引用它的 `.o` 之后，因为 ld 对 `.a` 是单遍扫描）；**（b）符号存在但名字对不上**——C++ 名字修饰（mangling）、`extern "C"` 缺失、或者符号在 `.o` 里是 `STB_LOCAL`（`static`）所以对链接器不可见。

`multiple definition` 的真实原因：同一个强符号在两个 TU 中被定义。典型是头文件里写了函数定义或全局变量定义（而非 `extern` 声明），被两个 `.c` include。注意 GCC 历史上有 `-fcommon` 让未初始化全局变量进 `COMMON` 段从而允许多个“暂定定义”合并，GCC 10 起默认 `-fno-common`，所以老代码升级后突然报符号冲突——这是面试里很常见的追问点。

**最小例子**

```c
// a.c
int shared = 1;
int helper(void);        // 只有声明
int main(void) { return helper() + shared; }
```

```bash
gcc -E a.c -o a.i      # 纯文本，仍含 int helper(void);
gcc -S a.i -o a.s      # 生成 call helper，地址留 0
gcc -c a.s -o a.o      # 成功！a.o 中有 U helper、D shared、T main
gcc a.o -o a.out       # 失败：undefined reference to `helper'
```

`nm a.o` 输出形如：

```text
0000000000000000 T main
0000000000000000 D shared
                 U helper
```

`U` 就是「未定义、待别人填」。补上 `b.c` 定义 `int helper(void){return 41;}` 后 `gcc a.o b.o -o a.out` 成功，`main` 返回 42。

**面试高频问法**

- **问法**：`gcc -c` 成功但 `gcc` 链接失败，说明什么？→ **考点**：编译与链接的职责边界。→ **答法**：编译阶段只需要函数签名就能生成调用序列，地址先填 0 并把符号标成未定义；链接阶段才做符号解析，找不到定义就报 undefined reference，所以失败点必然在链接，不在编译。
- **问法**：`undefined reference` 有哪几种真实成因？→ **考点**：是否会背“没链接库”这一种就完事。→ **答法**：两类：一是目标文件或库里确实没有这个符号的定义，常见是漏库或 `-l` 顺序在引用者之前导致单遍扫描错过；二是符号存在但名字不匹配，比如 C++ 名字修饰、缺 `extern "C"`、或者定义是 `static` 属于局部符号，链接器根本看不到。
- **问法**：为什么头文件里定义全局变量会报 multiple definition？→ **考点**：强符号/弱符号与 `-fcommon`。→ **答法**：头文件里的是定义不是声明，被两个翻译单元 include 就产生两个强符号，链接器见到多个强定义就报冲突；旧 GCC 默认 `-fcommon` 把未初始化全局变量放进 COMMON 段允许合并，GCC 10 起默认 `-fno-common`，所以这类代码会突然报错，正确写法是头文件里 `extern` 声明、单个 `.c` 里定义。
- **问法**：预处理器做了什么、没做什么？→ **考点**：是否把预处理当编译器。→ **答法**：只做文本层面的 `#include` 展开、宏替换、条件编译和去注释，不理解类型和语法；宏是文本替换所以有括号陷阱，语义检查和优化全在编译阶段。
- **问法**：`static` 函数为什么不会引起符号冲突？→ **考点**：符号绑定的可见性。→ **答法**：`static` 让符号成为 `STB_LOCAL`，只在本目标文件内可见，不进入全局符号解析，多个文件可以有同名 static 函数，链接器不会认为冲突。

## 第 2 章 x86-64 汇编基础：寄存器、寻址模式与常用指令

**要解决的问题**：给出读 x86-64 反汇编所需的最小知识集——16 个通用寄存器的分工、操作数写在指令里的方式（寻址模式）、以及编译器实际会生成的十来条指令。不解决，后面读栈帧、读 PLT 跳转、读内联汇编约束都只能靠猜。本章与第 3 章 AArch64 逐条对照着记，效果最好。

**机制**

**寄存器**：x86-64 有 16 个 64 位通用寄存器，命名体现“历史包袱”——同一寄存器可按宽度取不同名字：

| 64 位 | 32 位 | 16 位 | 8 位 | 约定用途（SysV） |
|---|---|---|---|---|
| `rax` | `eax` | `ax` | `al` | 返回值 / 累加 |
| `rbx` | `ebx` | `bx` | `bl` | 被调用者保存 |
| `rcx` | `ecx` | `cx` | `cl` | 第 4 参数 / 移位计数 |
| `rdx` | `edx` | `dx` | `dl` | 第 3 参数 / 乘除高位 |
| `rsi` | `esi` | `si` | `sil` | 第 2 参数 / 源串 |
| `rdi` | `edi` | `di` | `dil` | 第 1 参数 / 目的串 |
| `rbp` | `ebp` | `bp` | `bpl` | 帧指针（可选） |
| `rsp` | `esp` | `sp` | `spl` | 栈指针 |
| `r8`–`r15` | `r8d`–`r15d` | `r8w`–`r15w` | `r8b`–`r15b` | 参数 5、6 用 `r8`、`r9`，其余易失 |

两个关键坑：**写 32 位寄存器会零扩展清掉高 32 位**（`mov eax, 1` 把 `rax` 高半清零），而写 16 位或 8 位**不会**（`mov al, 1` 保留其余位）。这是 x86 独有的行为，AArch64 的 `w0` 写同理清零高 32 位，但 AArch64 没有 16/8 位子寄存器别名。

**寻址模式**：x86-64 的内存操作数是通用公式

```text
[ base + index * scale + disp ]     scale ∈ {1,2,4,8}
```

一条指令里最多一个 base、一个 index、一个位移，`lea` 还能在不访存的情况下算出这个地址。

**指令形态**：x86 是**变长 CISC**，指令 1–15 字节；大多数算术指令是“读-改-写”双操作数（`add rax, rbx` 把 rbx 加到 rax），**操作数可以直接是内存**（`add [rdi], eax` 一条指令完成 load-add-store）——这正是与 AArch64 load/store 架构最大的分野：AArch64 只有 `ldr/str` 能碰内存，算术指令的操作数必须是寄存器。

**标志位与条件执行**：x86 通过 `rflags` 的 ZF/SF/CF/OF 传递比较结果，条件跳转 `je/jne/jl/jg` 读这些位。AArch64 则有 `cset`、`csel`、条件分支 `b.eq`，也能在一条指令上带条件后缀。x86 的 `cmov` 是有限的条件传送，绝大多数条件逻辑还是要靠分支或 `setcc`。

**常用指令最小集**：

```asm
mov  rax, rbx          # 寄存器传送
mov  rax, [rdi+8]      # 访存：读 rdi+8 处的 8 字节
lea  rax, [rdi+rsi*4]  # 只算地址不访存，常用作乘加
add/sub/imul  rax, rbx
cmp  rax, rbx          # 做减法只置标志位
test rax, rax          # 与运算只置标志位，判零常用
je/jne/jl/jg  label    # 条件跳转
push/pop rax           # 隐含 rsp -=/+8
call/ret               # 隐含压栈/弹栈返回地址
movzx/movsx eax, byte [rdi]   # 零扩展 / 符号扩展加载
```

**最小例子**

C 代码 `int get(int *a, int i) { return a[i] + 1; }`，GCC `-O2` 生成（SysV，`a` 在 `rdi`、`i` 在 `esi`）：

```asm
get:
    movslq %esi, %rsi        # i 符号扩展到 64 位，作 index
    mov    (%rdi,%rsi,4), %eax   # eax = a[i]，scale=4 因 int 是 4 字节
    add    $1, %eax
    ret
```

这里 `(%rdi,%rsi,4)` 就是 `[base + index*scale]`，`disp` 为 0。一条 `mov` 完成了地址计算 + 访存，这是 x86 寻址模式的价值。对照 AArch64 同样的函数会是 `ldr w0, [x0, x1, lsl #2]` 再 `add w0, w0, #1`——**同样一条 load 带缩放索引，但加法必须是独立的寄存器操作**。

再看 `lea` 的经典用法：`int f(int x){ return x*5; }`，`-O2` 下常编译成 `lea eax, [rdi+rdi*4]`——一次地址计算当乘法用，不访存，延迟低。

**面试高频问法**

- **问法**：`mov eax, 1` 和 `mov al, 1` 有什么区别？→ **考点**：x86 部分寄存器写入的零扩展规则。→ **答法**：写 32 位寄存器会把高 32 位清零，所以 `mov eax,1` 之后 `rax` 整个变成 1；写 8 位的 `al` 只改最低字节，`rax` 其余 63 位保留原值，后续读 `rax` 会产生对旧值的依赖，编译器有时要额外指令打破这个依赖。
- **问法**：`[base + index*scale + disp]` 里 scale 能取哪些值，为什么？→ **考点**：是否理解寻址模式是为数组下标设计的。→ **答法**：只能是 1、2、4、8，正好对应 1/2/4/8 字节的元素宽度，编码里 scale 占 2 个 bit；这使得 `a[i]` 这类访问一条指令就能完成地址计算加访存。
- **问法**：`lea` 和 `mov` 都能算地址，区别在哪？→ **考点**：lea 不访存、不读标志位。→ **答法**：`lea` 只把有效地址算出来写进目的寄存器，完全不访问内存也不影响标志位，所以编译器常拿它做常数乘加；`mov` 带方括号时是真的去读内存。
- **问法**：x86 的算术指令能直接操作内存，AArch64 为什么不能？→ **考点**：CISC 读-改-写 vs load/store 架构。→ **答法**：x86 是变长 CISC，`add [rdi], eax` 一条指令完成读内存、加、写回；AArch64 是 load/store 架构，只有 `ldr/str` 能碰内存，算术指令操作数必须是寄存器，所以同样的语义需要三条指令，但流水线更规整、指令定长 4 字节、译码简单。
- **问法**：`call` 和 `ret` 隐含做了什么？→ **考点**：返回地址的传递方式。→ **答法**：`call` 把下一条指令地址压栈再跳转，`ret` 从栈顶弹出地址跳回去；所以返回地址在栈上而不是在某个寄存器里，这也是栈溢出能劫持控制流的原因。

## 第 3 章 ARM64 汇编基础：load/store 架构、条件执行与 x86 的逐条对照

**要解决的问题**：把「内存可以直接当操作数」的 x86 直觉换成「只有 load/store 碰内存」的 RISC 直觉，并建立 x86-64 ↔ AArch64 的一对一映射。不解决这件事，你读 ARM64 反汇编时会把 `ldr x1, [x0, x1, lsl #3]` 当成三条指令，写内联汇编时会生成非法寻址，性能分析时会把访存次数数错。

**机制**

**寄存器堆对照**。这是两套架构最直观的差别：

| | x86-64 | AArch64 |
|---|---|---|
| 通用寄存器 | 16 个（rax…r15） | 31 个（X0–X30），另有 W0–W30 作 32 位视图 |
| 零寄存器 | 无 | XZR / WZR（读恒 0，写丢弃） |
| 栈指针 | rsp（普通寄存器） | SP（独立编码，X31 在不同指令里表示 SP 或 XZR） |
| PC | rip，可用 `lea rax,[rip+disp]` 取 | 不能当通用寄存器读，用 `adr` / `adrp` 取页内/页基地址 |
| 指令长度 | 变长 1–15 字节 | 定长 4 字节 |

寄存器多带来的直接后果：AArch64 的参数寄存器有 8 个而 x86-64 只有 6 个，且 x86-64 的部分寄存器还有历史包袱（ah/al 不能和 REX 前缀共存）。定长指令带来的后果：PC 相对跳转范围有限的只有 `b`/`bl`（±128MB），更远要经链接器插入 veneer，走 X16/X17。

**load/store 架构**。AArch64 的算术指令只能吃寄存器，访存只认 `LDR/STR/LDP/STP/LDUR/STUR` 一族；x86-64 则允许绝大多数 ALU 指令带一个内存操作数。同一个「数组求和加」的语义：

```asm
; x86-64：一条指令，读内存 + 加寄存器
add rax, [rdi + rsi*8]

; AArch64：必须两条
ldr x1, [x0, x1, lsl #3]
add x0, x0, x1
```

**寻址方式对照**。x86-64 是 `[base + index*scale + disp]`，scale 只能是 1/2/4/8；AArch64 是 `[base, #imm]`（无符号偏移按访问宽度缩放，12 位）、`[base, Xm, LSL #s]`（寄存器偏移，可带 extend）、以及 x86 没有的两种自动更新：

```asm
ldr x0, [x1, #8]!     ; pre-index：先 x1+=8，再取
ldr x0, [x1], #8      ; post-index：先取，再 x1+=8
```

后两种加上 `LDP/STP`，就是 AArch64 没有 `push/pop` 却能一条指令完成入栈出栈的原因——`stp x29, x30, [sp, #-16]!` 抵得上 x86 的两条 push。

**条件执行**。两边都不是「每条指令带谓词」：ARMv7 的谓词执行在 AArch64 里已被裁掉，只保留条件分支 `b.cond` 和条件选择/条件比较家族 `CSEL / CSINC / CSINV / CSNEG / CCMP / CCMN`；x86-64 对应的是 `jcc / cmovcc / setcc / adc-sbb`。第二处差别在标志位怎么产生：x86 的 ALU 指令默认写 rflags，AArch64 默认**不写** PSTATE，必须加 `S` 后缀（`ADDS/SUBS/ANDS`），而 `CMP` 就是 `SUBS XZR, ...`、`TST` 就是 `ANDS XZR, ...`。这意味着 AArch64 的指令调度更自由——编译器可以把不相关的指令塞进 `cmp` 和 `b.eq` 之间而不破坏标志。

**最小例子**

```c
long idx(long *a, long i) { return a[i]; }
long myabs(long x)        { return x < 0 ? -x : x; }
```

```asm
; ---- x86-64 (SysV) ----
idx:    mov  rax, [rdi + rsi*8]      ; rdi=a, rsi=i
        ret
myabs:  mov  rax, rdi
        neg  rax                     ; 若 x<0 则 -x>0，SF=0
        cmovs rax, rdi               ; 原值为正时 SF=1，取回 x
        ret

; ---- AArch64 (AAPCS64) ----
idx:    ldr  x0, [x0, x1, lsl #3]    ; 一条 load，缩放由 lsl #3 完成
        ret
myabs:  cmp  x0, #0
        cneg x0, x0, lt              ; lt 成立则 x0 = -x0，无分支
        ret
```

数一下差别：`idx` 两边都是 2 条指令，因为 x86 的 scale 和 ARM 的 LSL 都在寻址里编码了；`myabs` 两边都做到了无分支，但 x86 靠「标志位 + cmov」，ARM 靠「比较 + 条件选择」。如果换成一个 5 分支的 switch，x86 会生成跳转表 `.rodata` + `jmp [rax*8+L]`，AArch64 生成 `adrp/add` 算出表基址再 `ldr x1,[x0, w2, sxtw #3]; br x1`——注意这里必须用 `adrp` 两三条指令才能拼出 64 位地址，这就是定长指令的代价。

**面试高频问法**

1. **「ARM 是不是 load/store 架构？举一个 x86 能写、ARM 写不了的指令。」** → 考点是是否真理解「运算不碰内存」。答法：是，AArch64 只有 LDR/STR 一族访存；`add rax, [rdi]` 在 AArch64 里必须拆成 `ldr x1,[x0]` 加 `add x0,x0,x1`，所以 ARM 的指令数通常更多但每条更规整、更易流水。

2. **「AArch64 有没有条件执行？和 ARMv7 差在哪？」** → 考点是版本演进，别把 ARM32 的印象套过来。答法：AArch64 取消了逐指令谓词执行，只剩条件分支和 CSEL/CSINC/CSINV/CSNEG/CCMP 这套条件选择家族，好处是解码简单、不占用编码里的 4 位条件域。

3. **「`cmp` 在 AArch64 里是什么？为什么不写 `adds` 就没有标志位？」** → 考点是标志位生成规则。答法：`cmp x0,#0` 就是 `subs xzr, x0, #0`，结果丢弃只留 PSTATE 的 N/Z/C/V；AArch64 的 ALU 指令默认不更新标志，必须显式加 `S`，这是和 x86 每指令默认写 rflags 的关键区别。

4. **「AArch64 没有 push/pop，函数序言怎么写？比 x86 快还是慢？」** → 考点是 LDP/STP + pre/post-index。答法：`stp x29, x30, [sp, #-16]!` 一条完成「减栈 + 存两个寄存器」，`ldp x29, x30, [sp], #16` 一条完成出栈，指令数不比 x86 的两次 push 多，而且是单条指令单次访存对齐。

5. **「两个架构的指令长度差异对性能和链接有什么影响？」** → 考点是变长解码 vs 定长。答法：x86 变长（1–15 字节）代码密度高、缓存友好，但解码要串行判定长度；AArch64 定长 4 字节解码简单、可取指即对齐，代价是立即数和跳转范围受限，远跳要链接器插 veneer（用 X16/X17）。

---

## 第 4 章 调用约定与 ABI：SysV 与 AArch64、参数传递、调用者与被调用者保存

**要解决的问题**：函数调用不是语言特性，是编译器、链接器、操作系统、调试器共同遵守的二进制契约。不解决这件事，你无法解释「为什么第 7 个参数突然跑到栈上」「为什么改一个寄存器就段错误」「为什么 C++ 调用 C 必须 `extern "C"`」，也无法在 gdb 里手工构造一次调用。

**机制**

**参数传递对照**。整数/指针按序吃寄存器，吃完上栈：

| | x86-64 SysV | AArch64 AAPCS64 |
|---|---|---|
| 整数参数 | rdi, rsi, rdx, rcx, r8, r9（6 个） | x0–x7（8 个） |
| 浮点参数 | xmm0–xmm7 | v0–v7 |
| 整数返回 | rax（128 位用 rdx:rax） | x0（x1 辅助） |
| 浮点返回 | xmm0 / xmm1 | v0 |
| 被调用者保存 | rbx, rbp, r12–r15, rsp | x19–x28, x29(FP), x30(LR), sp, 以及 v8–v15 的低 64 位 |
| 调用者保存 | rax, rcx, rdx, rsi, rdi, r8–r11, 全部 xmm | x0–x18, 全部 v0–v7 与 v16–v31 |

x86-64 里 r10/r11 明确是调用者保存的临时寄存器，r12–r15 才需要压栈；AArch64 里 x16/x17 是 IP0/IP1，专供链接器插入的 veneer 使用，编译器一般不当通用临时寄存器用；x18 是平台寄存器（Darwin/Windows 上保留，Linux 用户态可用但通常被保留作 OS 用途）。

**返回地址放在哪，决定了栈帧形状**。x86 的 `call` 把返回地址压栈，于是「函数入口处 rsp ≡ 8 (mod 16)」，SysV 要求**调用指令执行前** rsp 16 字节对齐。AArch64 的 `bl` 把返回地址放进 X30，叶函数可以完全不碰栈；非叶函数才 `stp x29,x30,[sp,#-16]!` 把它落盘。另一个实打实的差别是红区：SysV 给了叶函数 rsp 以下 128 字节的红区，信号处理不会踩；AAPCS64 **没有**红区，所以 AArch64 叶函数一旦要临时空间就得老老实实调整 SP。

**聚合类型与变参**。两边都不是「结构体一律走栈」：SysV 把 ≤16 字节的聚合按八字节分类成 INTEGER/SSE，拆进寄存器，>16 字节则调用者在栈上开空间并把地址当隐藏第一参数（返回值同理，`rdi` 传隐藏指针）；AAPCS64 把 ≤16 字节的复合类型装进 x 寄存器，同构浮点聚合（HFA，最多 4 个同类型浮点成员）走 v 寄存器。变参的差异更明显：SysV 要求调用者在 `al` 里填「本次用了几个向量寄存器」，`va_start` 靠它决定要不要存 xmm 寄存器堆；AAPCS64 的匿名参数直接从栈上取，不需要这个计数。

**最小例子**

```c
long f(long a, long b, long c, long d, long e, long g, long h, long i);
long r = f(1,2,3,4,5,6,7,8);
```

x86-64：前 6 个进 rdi=1, rsi=2, rdx=3, rcx=4, r8=5, r9=6；编译器倒序压栈 `push $8; push $7`，再 `call`。进入 `f` 后：

```asm
f:
    mov rax, [rsp+16]   ; 第 8 个参数 = 8
    add rax, [rsp+8]    ; 第 7 个参数 = 7
    add rax, rdi        ; = 1
    ret                 ; 结果 16
```

AArch64：x0–x7 正好装下 1..8，栈一个字都不用动：

```asm
f:
    add x0, x0, x7      ; 1 + 8
    add x0, x0, x6      ; + 7
    ret                 ; 结果 16
```

第 9 个参数才会出现在 AArch64 的 `[sp]`。这就是「多两个参数寄存器」在真实代码里的价值：8 参数以内的函数在 AArch64 上完全无栈帧，而在 x86-64 上已经要读写栈。

**面试高频问法**

1. **「第 7 个参数在 x86-64 和 AArch64 上分别在哪？」** → 考点是参数寄存器数量。答法：x86-64 只有 6 个整数参数寄存器（rdi/rsi/rdx/rcx/r8/r9），第 7 个在栈上 `[rsp+8]`（`[rsp]` 是返回地址）；AArch64 有 x0–x7，第 7 个仍在 x6，第 9 个才上栈。

2. **「调用者保存和被调用者保存怎么分？为什么不全保存？」** → 考点是性能取舍。答法：调用者保存的是「调用前后可能被改写、需要调用者自己负责的」临时寄存器（x86 的 rax/rcx/rdx/rsi/rdi/r8–r11，ARM 的 x0–x18），被调用者保存的是跨越调用仍需保持的（rbx/rbp/r12–r15，x19–x28/x29/x30）。全保存会让每次调用多出十几次访存，分工后只有真正用到 callee-saved 的函数才付压栈代价。

3. **「x86-64 的栈对齐规则具体是什么？为什么 `printf` 会崩？」** → 考点是对齐时机。答法：SysV 要求 `call` 执行前 rsp 是 16 的倍数，所以函数入口 rsp ≡ 8 (mod 16)；手写汇编或改编译选项后忘了 `sub rsp,8` 补齐，`printf` 内部用到 `movaps`（要求 16 字节对齐）就会触发 SIGSEGV。

4. **「红区是什么？AArch64 有吗？」** → 考点是 ABI 细节。答法：SysV 允许叶函数直接用 rsp 以下 128 字节而不调整 SP，因为信号处理保证不覆盖；AAPCS64 没有红区，AArch64 叶函数要用临时空间必须先 `sub sp`。

5. **「`extern "C"` 到底做了什么？和链接错误什么关系？」** → 考点是把 ABI 和符号名连起来。答法：C++ 会对函数名做 name mangling，把参数类型编进符号（`_Z3fooi`），而 C 没有；不加 `extern "C"` 去调用一个 C 库函数，链接器按 `_Z3fooi` 找不到定义，报 `undefined reference`——问题不在 ABI 参数传递，而在符号名。

> 补一条常被追问的延伸：**「undefined reference 和符号冲突的真实原因」**——前者是「有声明无定义」：定义所在的目标文件没被加入链接、静态库顺序错（链接器从左到右扫，只为「当前未定义」的符号抽取成员）、`inline`/模板没实例化、或者上面说的名字不匹配；后者是「同名强符号出现两次」，链接器规则是强符号只能有一个定义，弱符号与 COMDAT 组（`inline` 函数、模板实例、C++17 `inline` 变量）可以多份由链接器挑一份。GCC 10 起 `-fno-common` 成为默认，把原来的 tentative definition 从可合并的 COMMON 符号改成强符号，于是「两个 .c 里都写了 `int g;`」从静默合变成了 `multiple definition`——这是升级编译器后突然报错的真实原因。

## 第 5 章 栈帧与局部变量：帧指针、红区、可变参数、栈对齐

**要解决的问题**：函数调用时，返回地址、保存的寄存器、局部变量和溢出参数到底落在内存的哪里？栈帧就是把这套约定固化成实际内存布局。如果不弄清它，调试器里看到的 backtrace 链、崩溃时保存的调用栈、可变参数为什么能把值读出来、`movaps` 为什么因对齐问题崩溃，全都无法解释。

**机制**

两个架构的栈帧形状不同，根本原因在调用指令本身：

- x86-64 的 `call` 先把 8 字节返回地址压栈（`rsp -= 8`）再跳转，返回地址天然位于被调用者的栈帧内。
- AArch64 的 `bl` 只把返回地址写进 `x30`（LR），完全不动 `sp`；返回地址必须由被调用者自己保存（通常与 FP 一起 `stp`）。

于是 prologue（函数序言）形成对照：

```asm
# x86-64 SysV                    # AArch64 AAPCS64
push rbp                         stp  x29, x30, [sp, #-16]!
mov  rbp, rsp                    mov  x29, sp
sub  rsp, 0x30                   sub  sp, sp, #0x30
```

帧链因此也不同：x86-64 上是 `[rbp]=调用者的 rbp`、`[rbp+8]=返回地址`、第一个溢出栈参数在 `[rbp+16]`；AArch64 上是 `[x29]=调用者 fp`、`[x29+8]=返回地址`（一条 `stp` 存下），回溯算法必须按各自的布局来写。`-fno-omit-frame-pointer` 的意义就在这里：牺牲一个通用寄存器换取可靠的 unwind（`perf`、`gdb`、采样 profiler 都依赖它）。

**红区（red zone）**：x86-64 SysV 在 `[rsp-128, rsp)` 划出 128 字节，叶子函数可以不调整 `sp` 就直接使用；代价是内核在投递信号时必须跳过这 128 字节，否则会覆盖用户数据。AArch64 的 AAPCS64 **没有红区**，而且没有 `push/pop` 指令，叶子函数要用栈就得老实调整 `sp`。取舍是：红区省两条指令、省一次 `sp` 更新，但让信号处理和栈探测变复杂。

**栈对齐**：x86-64 规定“进入函数时 `rsp+8` 是 16 的倍数”，即入口 `rsp ≡ 8 (mod 16)`，所以 `push rbp` 之后恰好 16 对齐；`movaps`/`movdqa` 崩溃基本都是有人手动改了 `rsp` 破坏了这个不变式。AArch64 反过来，要求更严格：只要 `sp` 参与访存，就必须 `sp mod 16 = 0`，这是公共接口的硬性约束，不是“进函数时”的约定。

**可变参数**是两条 ABI 差异最明显的地方。x86-64 用寄存器传匿名参数，所以 callee 必须先把 6 个 GP 寄存器和 8 个 XMM 寄存器整体“倾倒”到 176 字节的 register save area（6×8 + 8×16），`va_list` 是四元组 `{gp_offset, fp_offset, overflow_arg_area, reg_save_area}`，并且调用方要在 `al` 里填“用了几个向量寄存器”。AArch64 简单得多：AAPCS64 规定匿名参数一律走栈，`va_list` 基本就是一个指向栈上参数区的游标结构。

**最小例子**

```c
long f(long a1, long a2, long a3, long a4, long a5, long a6, long a7)
{ return a1 + a7; }
```

x86-64：`a1..a6 → rdi, rsi, rdx, rcx, r8, r9`，`a7` 走栈。设入口 `rsp = 0x7ffd_0000_5ff8`（满足 ≡8 mod 16），`push rbp` 后为 `0x…5ff0`（16 对齐），`sub rsp,0x30` 后为 `0x…5fc0`；调用前把 `a7` 写入 `[rsp]`，`rsp` 仍 16 对齐，callee 里读 `[rbp+16]` 拿到就是 `a7`。

AArch64：`a1..a7 → x0..x6`，因为 GP 参数寄存器有 8 个，`a7` 根本不占栈，栈帧只剩 `stp x29,x30,[sp,#-16]!` 这 16 字节。

**面试高频问法**

1. 问：为什么 AArch64 的栈帧里返回地址位置和 x86-64 不一样？
   → 考点在调用指令语义：`call` 隐含压栈，`bl` 只写 LR。
   → 答：x86-64 的 `call` 把返回地址压在栈上，所以它在被调函数的帧里；AArch64 的 `bl` 只写 `x30`，返回地址是被调函数用 `stp x29,x30` 主动存的，位置由编译器约定，不由指令决定。

2. 问：红区是什么，为什么 AArch64 没有？
   → 考点在 ABI 取舍与信号处理的耦合。
   → 答：红区是 x86-64 SysV 给叶子函数的 128 字节免调整栈空间，省两条指令；代价是内核投信号要跳过它。AArch64 没有 `push/pop`，也没定义红区，用栈就得显式改 `sp`。

3. 问：`printf` 这类可变参数函数怎么知道去哪里取参数？
   → 考点在寄存器保存区与 `va_list` 实现。
   → 答：x86-64 上 callee 把 6 个 GP 和 8 个 XMM 寄存器倾倒到 176 字节保存区，`va_list` 记录 gp/fp 偏移和溢出区指针；AArch64 上匿名参数本来就全在栈上，`va_list` 基本就是栈游标。

4. 问：程序在 `movaps` 上 SIGSEGV，最可能是什么原因？
   → 考点在栈对齐不变式。
   → 答：x86-64 要求调用点 `rsp mod 16 = 0`（入口 ≡8），某处手写汇编或 `alloca` 破坏了它，导致 16 字节对齐的 SSE 访存落到奇数 8 字节地址上。

5. 问：`-fomit-frame-pointer` 优化掉 rbp 后，backtrace 还怎么走？
   → 考点在帧指针与 unwind 信息的替代关系。
   → 答：靠 `.eh_frame`/CFI 里记录的 CFA 规则做表驱动展开，`gdb`、`perf` 都能用，但代价是体积变大、采样时更慢，内核和部分发行版因此强制保留帧指针。

## 第 6 章 目标文件与 ELF：段与节、符号表、重定位表

**要解决的问题**：编译器一次只看得见一个 TU（编译单元），跨文件的函数地址、全局变量位置它根本不知道。ELF 就是把这份“未完成的半成品”连同“哪里还欠一个数”的清单交给链接器。不理解它，`undefined reference` 和 `multiple definition` 就只能靠猜。

**机制**

ELF 有两套互相独立的视图，看错视图是新手最常见的困惑：

- **节（section）给链接器**：`.text`、`.data`、`.bss`、`.rodata`、`.symtab`、`.strtab`、`.rela.text`。用 `readelf -S` 看。
- **段（segment）给装载器**：`PT_LOAD`、`PT_DYNAMIC`、`PT_INTERP`，描述“映射哪段、什么权限”。用 `readelf -l` 看。

`.bss` 是 `SHT_NOBITS`，文件里不占字节，只在内存里占（`p_memsz > p_filesz`），这就是“未初始化全局变量不撑大二进制”的原因。

**符号表** `.symtab`，每项 `Elf64_Sym { st_name, st_info, st_other, st_shndx, st_value, st_size }`。`st_info` 高 4 位是 bind（LOCAL/GLOBAL/WEAK），低 4 位是 type（FUNC/OBJECT/SECTION/FILE/NOTYPE）。关键在 `st_shndx`：等于 `SHN_UNDEF` 表示“本文件只引用、没定义”；`SHN_ABS` 是绝对值；`SHN_COMMON` 是老式 tentative definition 的落脚点。

**重定位表** `.rela.text`，每项 `Elf64_Rela { r_offset, r_info, r_addend }`，语义是“把 `r_offset` 处的字段按 $S + A - P$ 或 $S + A$ 算出来填回去”（$S$ 符号地址，$A$ 加数，$P$ 重定位处地址）。两架构在这里差别很直观：

- x86-64 变长指令，一条 `call` 直接吃 32 位 PC 相对位移 → 一个 `R_X86_64_PLT32`；绝对地址用 `R_X86_64_64`；32 位有符号立即数用 `R_X86_64_32S`。
- AArch64 指令定长 4 字节，装不下一整个地址，取地址要 `adrp` + `add` 两条指令配合 → **一次引用产生两条重定位**：`R_AARCH64_ADR_PREL_PG_HI21`（页基址高 21 位）+ `R_AARCH64_ADD_ABS_LO12_NC`（低 12 位）。函数调用是 `R_AARCH64_CALL26`，26 位立即数 ×4 → 可达范围 ±128 MB，超出时链接器必须插入跳转桩（stub）。

**`undefined reference` 的真实原因**：某个 `.rela.*` 里的符号 `st_shndx = SHN_UNDEF`，链接器扫遍所有输入 `.o` 和库后，没有任何一个给出 GLOBAL 或 WEAK 定义。典型成因有四种：漏了 `-l` 或库顺序写反（`-l` 必须在使用者之后，因为链接器单趟扫描）；C++ 名字修饰不匹配（漏写 `extern "C"`）；`inline` 函数没被 emit 出来；只有声明没有定义。

**符号冲突的真实原因**：链接器维护一张全局符号表，遇到第二个同名强定义（GLOBAL、非 COMMON）立刻报 multiple definition。C 里写 `int x;` 是 tentative definition，老 GCC 默认 `-fcommon` 会把它丢进 `SHN_COMMON` 允许链接期合并（取最大 size）；GCC 10 起默认 `-fno-common`，它变成 `.bss` 里的强定义，于是两个 `.c` 各写一句 `int x;` 立刻冲突——这是近年大量老项目突然编不过的主因。解法：头文件只放 `extern` 声明，定义只留一处；或 `static` / `__attribute__((weak))`。

**最小例子**

```c
// a.c
extern int foo(int);
int main(void) { return foo(1); }
```

```text
$ gcc -c a.c && readelf -s a.o
  3: 0000000000000000     0 NOTYPE  GLOBAL DEFAULT  UND foo      ← 未定义
  4: 0000000000000000    27 FUNC    GLOBAL DEFAULT    1 main
$ readelf -r a.o
Offset          Info           Type            Sym.Name + Addend
0000000000000015 000300000004 R_X86_64_PLT32   foo - 4
```

`r_offset = 0x15` 指向 `call` 指令后面那个 4 字节位移字段；此时它是 `-4`（占位），链接器算出 `S + A - P` 后回填。若不提供 `b.o`，`foo` 的 `st_shndx` 一直是 `UND` → 报 `undefined reference to 'foo'`。同源代码在 AArch64 上会产出一行 `R_AARCH64_CALL26` 而不是 `PLT32`。

**面试高频问法**

1. 问：`undefined reference` 到底是编译错误还是链接错误，根因是什么？
   → 考点在符号表 `SHN_UNDEF` 与链接器解析职责。
   → 答：链接错误。`a.o` 的重定位表引用了一个 `st_shndx = SHN_UNDEF` 的符号，链接器在所有输入文件和库里找不到对应的 GLOBAL/WEAK 定义，只能报未定义引用。

2. 问：为什么 `-lm` 必须写在 `.c` 文件后面？
   → 考点在链接器的单趟扫描与库的顺序敏感性。
   → 答：链接器按命令行顺序扫，到 `-lm` 时才会去归档里取成员，此前未解析的符号才会被拉进来；写在前面则扫库时符号表还是空的，等于没链。

3. 问：两个 `.c` 里都写 `int x;` 为什么有时能过有时报错？
   → 考点在 COMMON 与 `-fno-common`。
   → 答：`int x;` 是 tentative definition，`-fcommon` 下进 `SHN_COMMON` 允许合并；GCC 10 默认 `-fno-common`，它成了 `.bss` 强定义，两个强定义相遇即 multiple definition。

4. 问：段和节有什么区别？
   → 考点在链接视图 vs 装载视图。
   → 答：节是给链接器用的细粒度分类（`.text`/`.rodata`/`.rela.text`），段是给装载器用的映射单元（`PT_LOAD` 带权限），多个节会被合并进一个段。

5. 问：AArch64 上为什么要两条重定位才能取一个全局变量地址？
   → 考点在定长指令编码与地址分段。
   → 答：指令只有 32 位，装不下完整地址，所以 `adrp` 算页基址高 21 位（`ADR_PREL_PG_HI21`），`add` 补低 12 位（`ADD_ABS_LO12_NC`），两处各一条重定位，必须成对出现。

## 第 7 章 静态链接与动态链接：符号解析、PLT/GOT、延迟绑定

**要解决的问题**：把若干目标文件里「我引用了 `f`」和「我定义了 `f`」对上号，并决定这个绑定在什么时候发生。静态链接在链接期一次算死，动态链接推迟到装载或首次调用。不解决这件事，程序就无法拆成多个模块编译，`libc` 也无法被所有进程共用一份物理页。

**机制**

符号表是这一切的输入。ELF 的 `.symtab` 每项是 `{st_name, st_value, st_size, st_info(绑定,类型), st_shndx}`；`STB_LOCAL` 只在本文件可见（`static` 函数就落在这里），`STB_GLOBAL` 全局，`STB_WEAK` 弱。`st_shndx == SHN_UNDEF` 表示「本文件引用、但没定义」，这就是重定位要填的洞。

**静态链接**分两步：符号解析 + 重定位。解析规则是：多个 `STB_GLOBAL` 同名定义 → `multiple definition`（GCC 10 起默认 `-fno-common`，以前的 tentative definition 合并行为没了）；强 + 弱 → 取强；多个弱 → 取链接器先遇到的那个。

`undefined reference` 的真实原因只有三类，面试要能说清是哪一类：
1. 库里确实没有这个定义（漏了 `-l`、拼错、C++ 忘了 `extern "C"` 导致名字被 mangle 成 `_Z3foov`）。
2. 定义在 `.a` 里，但归档文件**只按命令行顺序扫描一遍**，且只拉取「当前还有未解析符号」的成员。`gcc -lfoo main.o` 时 `main.o` 还没进来，`libfoo.a` 被整包跳过 → 后面全成 undefined。修法是把 `-lfoo` 放后面，或用 `--start-group/--end-group` 让链接器反复扫。
3. 只声明未定义：头文件里 `extern int x;` 但没有哪个 `.c` 真的给出定义。

重定位表 `.rela.text` 每条是 `(r_offset, r_type, r_sym, r_addend)`，链接器算出符号最终地址后回填。两个架构在这里形态差异最明显：

| 场景 | x86-64 | AArch64 |
|---|---|---|
| 调用函数 | `R_X86_64_PLT32`（call 的 32 位位移） | `R_AARCH64_CALL26`（bl 的 26 位、±128MB） |
| 取全局变量地址 | `R_X86_64_PC32`（一条 `lea`） | `R_AARCH64_ADR_PREL_PG_HI21` + `R_AARCH64_ADD_ABS_LO12_NC`（`adrp` + `add` 两条，页相对） |

**动态链接**在链接期只写两样东西进产物：`.dynamic` 里的 `DT_NEEDED`（库的 SONAME）和未定义符号名，地址一个都不填。装载时 ld.so 建全局符号表，按 **BFS 顺序**查找：可执行文件 → 它的直接依赖 → 依赖的依赖，**先遇到的胜出**。这就是**符号冲突**的真实机制——后装载的库即使也导出了同名全局符号，也永远轮不到，这被称为 interposition。`LD_PRELOAD` 正是利用它劫持 `malloc`。要躲开就三招：`-fvisibility=hidden` 少导出、`-Bsymbolic` 让库内引用优先绑自己、version script 隔离。

位置无关代码的落地是 GOT + PLT 两张表：
- **GOT**（`.got` / `.got.plt`）是数据段里的指针数组，代码只写「从 GOT 第 n 项取地址」，装载时由 ld.so 填真值。
- **PLT** 是代码段里每个外部函数一小段跳板。x86-64 上 PLT0 负责 `push link_map; jmp *GOT[2]` 进 `_dl_runtime_resolve`；每个 stub 的 GOT 项初值指回自己 stub 内那条 `push reloc_index` 指令。
- **延迟绑定**：首次调用走 `push 索引 → PLT0 → _dl_runtime_resolve`，解析完把真实地址**写回该 GOT 项**，第二次起就是一次间接跳转。`-z lazy` 是默认，`-z now` + `BIND_NOW` 在装载时全解析，配合 RELRO 把 GOT 变只读。
- AArch64 结构同构（同样是 `.got.plt` + `.rela.plt` + `_dl_runtime_resolve`），差异只在 stub 用 `adrp/ldr/add/br` 而非 `jmp *`，且 x16/x17 被 ABI 预留为链接器 scratch 寄存器。

**取舍**：静态链接无重定位开销、启动即跑、符号集合封闭（不会被子库插桩），代价是体积、内存不共享、库漏洞必须重链；动态链接换来代码段跨进程共享和独立升级，代价是启动重定位、符号冲突、版本问题（`foo@GLIBC_2.2.5` 这种版本化符号），以及 copy relocation——可执行文件引用 `.so` 里的数据符号时，链接器在可执行文件 `.bss` 里复制一份，运行时拷贝初值，`.so` 内部若用绝对寻址访问自己的变量就会与副本不一致。`-fPIC` 编译的库自己访问全局变量也走 GOT，才避得开。

**最小例子**

```c
// main.c
extern int g;
int f(int);
int main(void) { return f(1) + g; }
```

`gcc -c main.c -o main.o && readelf -r main.o`，`.rela.text` 里能看到形如 `R_X86_64_PLT32 f - 4` 和 `R_X86_64_PC32 g - 8` 两条；`objdump -d` 里 `call` 之后跟 4 个字节 `00 00 00 00`，就是待填的洞。同一份源码在 AArch64 上汇编，`bl f` 留 `R_AARCH64_CALL26`，取 `g` 变成 `adrp x0, g` + `ldr w0, [x0, #:lo12:g]` 两条重定位。

链接阶段用 `gcc main.o -L. -lfoo`：若目录里是 `libfoo.so`，`readelf -d` 只剩一行 `NEEDED libfoo.so`，`objdump -d` 里调用点变成 `<f@plt>`；若只有 `libfoo.a` 且命令写成 `gcc -lfoo main.o`，直接报 `undefined reference to 'f'`——就是上面第 2 类原因。

**面试高频问法**

1. **「`undefined reference` 是怎么产生的？」** → 考点是符号解析时机和 `.a` 的拉取语义，不是「没包含头文件」。一句话答法：「链接器扫完所有输入后仍有 `SHN_UNDEF` 符号没被任何 `STB_GLOBAL` 定义填上；最常见是 `.a` 只按命令行顺序扫一遍，库放在了引用它的目标文件前面，或者 C++ 名字被 mangle 了而声明侧没加 `extern "C"`。」

2. **「两个 `.so` 都定义了同名全局符号，用哪个？」** → 考点是 BFS 查找顺序与 interposition。一句话答法：「按装载顺序广度优先找，先遇到的胜出，后加载的那个永远被遮蔽；要避免就用 `-fvisibility=hidden`、`-Bsymbolic` 或 version script，`LD_PRELOAD` 就是故意利用这个规则。」

3. **「PLT 和 GOT 为什么是两张表，合成一张不行吗？」** → 考点是段权限与位置无关。一句话答法：「GOT 在数据段、可写、装的是地址；PLT 在代码段、只读、装的是跳板。代码段不能改，所以跳转目标必须从可写的数据段间接取；而首次解析需要一段能执行又能携带重定位索引的代码，只能放在 PLT 里。」

4. **「延迟绑定具体怎么实现的？第一次调用跳到哪？」** → 考点是 GOT 初值。一句话答法：「GOT 项初值不是函数地址，而是指回本 stub 里那条 `push 重定位索引` 的指令，接着跳到 PLT0，PLT0 把 `link_map` 压栈后跳 `_dl_runtime_resolve`；解析器算完地址写回 GOT 项，之后每次调用就是一次间接跳

## 第 9 章 内联汇编与 intrinsics：约束、clobber、内存屏障

**要解决的问题**：C 语言无法表达特殊寄存器、系统指令、精确指令序列和内存序语义；如果直接把这些指令交给编译器而不讲清输入输出和副作用，优化器就会在它不知道的地方重排、缓存或删除代码，导致“单测通过、上线乱序”的错误。这一章要解决的问题是：**如何把一段汇编安全地嵌入 C，并让编译器的优化假设保持成立**。

**机制**

GCC/Clang 的扩展内联汇编形式是：

```c
asm volatile ("模板" : 输出 : 输入 : clobber);
```

- **约束**决定操作数放在哪里：`"r"` 通用寄存器，`"m"` 内存，`"i"` 立即数，`"x"` SSE 寄存器，`"w"` 向量寄存器；`"=r"` 只写，`"+r"` 读写，`"=&r"` 是 early clobber，声明输出在输入被读完之前就可能被写，防止模板先覆盖输入。
- **clobber** 声明这条 asm 会破坏什么：`"cc"` 表示标志寄存器，`"memory"` 表示内存内容可能改变。`"memory"` 是**编译器屏障**：它让编译器不能把跨这条 asm 的内存访问缓存到寄存器，也不能随意重排内存读写，但它**不生成任何 CPU 指令**。
- **volatile** 只约束这条 asm 本身不被删除、不被移到与之有数据依赖的访问之外；它不等于内存屏障，也不等于原子性。

内存屏障分两层：编译屏障 `asm volatile("" ::: "memory")` 只限制编译器；CPU 屏障才限制硬件。x86 用 `mfence`、`lfence`、`sfence`，AArch64 用 `dmb ish`、`dsb`，以及带获取/释放语义的 `ldar`/`stlr`。实际工程中优先用 C11 `atomic_thread_fence` 或 `__atomic_*`，让编译器按目标选择指令。

**intrinsics 的取舍**：intrinsics 是编译器内建函数，例如 x86 的 `_mm256_loadu_si256`、AArch64 NEON 的 `vld1q_u8`。优点是类型安全、优化器理解语义、可参与调度和常量折叠；缺点是把代码绑定到 ISA 和头文件。内联汇编灵活，但优化器把它当黑盒，约束写错就是静默错误。原则：**能用 intrinsics 就不写 asm，intrinsics 覆盖不到才写 asm**。

**最小例子**

```c
static inline int xchg_int(int *p, int v) {
    int old;
    asm volatile("xchgl %0, %1"
                 : "=r"(old), "+m"(*p)
                 : "0"(v)
                 : "memory");
    return old;
}
```

调用 `int x = 42; int old = xchg_int(&x, 7);`，结果 `old = 42`、`x = 7`。`"0"(v)` 让 `v` 与 `old` 共用同一个寄存器作为输入；`"+m"` 表示内存既读又写；`"memory"` 阻止编译器把 `x` 的其他访问提到交换之前。x86 上 `xchg` 对内存操作数隐含锁语义，所以这里没有再加 `lock` 前缀。

一个反例：生产者写 `data = 42; flag = 1;`，只在两句之间放 `asm volatile("" ::: "memory")`。这能阻止编译器把 `data` 的写挪到 `flag` 之后，但**不能阻止 CPU 乱序**；跨核可见性仍需 release 存储或屏障指令。

**面试高频问法**

1. **问法**：`asm volatile` 里的 `volatile` 和 `"memory"` clobber 是一回事吗？
   **考点**：编译器屏障与指令屏障的区别。
   **一句话答法**：不是；`volatile` 只让这条 asm 不被删掉、不被随意移动，`"memory"` 才告诉编译器内存可能变了、跨它不能缓存和重排内存访问，两者都不产生 CPU 屏障。

2. **问法**：输出约束 `"=r"` 和 `"=&r"` 差在哪？
   **考点**：early clobber。
   **一句话答法**：`=` 允许编译器让输出和某个输入共用寄存器，因为它假设输入先读完；`=&` 声明输出在输入读完前就可能被写，模板先写输出时不会覆盖输入。

3. **问法**：intrinsics 和内联汇编怎么选？
   **考点**：优化器可见性与可移植性。
   **一句话答法**：优先 intrinsics，编译器能调度、折叠并理解依赖；只有特殊寄存器、系统指令或必须精确控制指令序列时才用内联汇编。

4. **问法**：`asm volatile("" ::: "memory")` 能当跨线程同步吗？
   **考点**：编译期约束不等于硬件内存序。
   **一句话答法**：不能，它只约束编译器；CPU 仍可乱序，跨核同步要用 acquire/release 原子操作或目标架构的屏障指令。

5. **问法**：内联汇编最常见的线上事故是什么？
   **考点**：约束和 clobber 写漏。
   **一句话答法**：漏写 `"memory"` 导致内存访问被重排、漏写 `"cc"` 或 early clobber 导致寄存器被覆盖，表现为优化级别一换就错。

## 第 10 章 两个架构的差异清单：什么时候必须看汇编

**要解决的问题**：面试和调试时需要快速判断“这段 C 在 x86-64 和 AArch64 上会变成什么、为什么行为不同、值不值得读汇编”。这一章给出一张可背诵的对照清单，并说明哪些场景下必须看汇编而不能停留在 C 层。

**机制**

**寄存器与参数传递**。x86-64 SysV 有 16 个通用寄存器，整数/指针参数依次用 `rdi, rsi, rdx, rcx, r8, r9`，返回在 `rax`；第 7 个参数起走栈。AArch64 有 31 个 64 位通用寄存器 `x0`–`x30`，参数用 `x0`–`x7`，返回在 `x0`；第 9 个参数起走栈。关键差别是返回地址：x86 的 `call` 把返回地址压栈，进入函数时第 7 个参数在 `8(%rsp)`；AArch64 把返回地址放 `x30`（LR），不在栈上，所以第 9 个参数就在 `[sp]`，函数返回用 `ret` 跳 `x30`。被调用者保存集也不同：x86 是 `rbx, rbp, r12`–`r15`，AArch64 是 `x19`–`x29`。

**寻址与指令形态**。x86-64 是变长指令（1–15 字节），内存操作数可写成 `disp(base, index, scale)`，算术指令可直接读改写内存；AArch64 是固定 4 字节指令、4 字节对齐，采用 load/store 架构，算术只作用于寄存器，访存必须 `ldr`/`str`，寻址是基址加 12 位缩放立即数（8 字节访问时 $\text{offset}=\text{imm12}\times 8$）或寄存器偏移。C 的 `p[i] + 1` 在 x86 上可能是一条“访存再加法”的融合序列，在 AArch64 上至少是 `ldr` 加 `add` 两条。

**条件执行**。x86 依赖标志位 `ZF/CF/SF/OF`，用 `setcc`、`cmovcc`、`jcc`；AArch64 用 `NZCV`，几乎每条指令可带条件后缀，`csel`、`csinc`、`ccmp` 可直接做三操作数选择。两者都能避免分支，但 x86 的 `cmov` 受标志依赖链限制，AArch64 的条件选择更灵活。

**栈与内存模型**。两者都要求调用边界 16 字节栈对齐。x86-64 SysV 有 128 字节红区，叶函数可使用 `rsp` 以下而不调整栈；AArch64 没有红区。内存模型差异更大：x86 是较强的一致性模型，普通 load/store 基本不乱序，只有 StoreLoad 需要 `mfence` 或 locked 指令；AArch64 是弱内存模型，跨核共享数据通常需要 `dmb ish`、`ldar`/`stlr` 或 C11 原子。

**什么时候必须看汇编**：性能热点（编译器没向量化、生成了意外的 spill 或分支）、未定义行为导致代码被优化掉、ABI 不匹配导致的崩溃（参数寄存器/栈对齐/结构体传参）、原子与屏障的正确性、逆向与安全分析、系统调用和特殊指令、以及怀疑编译器 bug 时。普通业务逻辑不应靠读汇编理解。

**最小例子**

```c
long f(long *p, long i) { return p[i] + 1; }
```

取 `long a[4] = {10,20,30,40}; f(a, 2)`，期望返回 `31`。

x86-64 可能是：

```asm
movq 16(%rdi), %rax
addq $1, %rax
ret
```

AArch64 可能是：

```asm
ldr x1, [x0, #16]
add x0, x1, #1
ret
```

两者都用“基址 + 16 字节偏移”一次取到 `a[2]`，但 x86 可以直接对内存做后续运算，AArch64 必须先装入寄存器。再看条件选择 `x > 0 ? 1 : 2`：x86 用 `cmp` 加 `cmovg`，AArch64 用 `cmp` 加 `csel`；若分支可预测，两边编译器也可能都生成普通跳转。

**面试高频问法**

1. **问法**：x86-64 和 AArch64 各有几个参数寄存器？第 7 个参数在哪？
   **考点**：调用约定与返回地址位置。
   **一句话答法**：x86-64 有 6 个，第 7 个在栈上、进入函数时位于 `8(%rsp)`；AArch64 有 8 个，第 9 个才在 `[sp]`，因为返回地址在 `x30` 而不占栈。

2. **问法**：为什么同一段无锁 C 代码在 x86 上压测没问题，换 ARM 就出问题？
   **考点**：TSO 与弱内存模型。
   **一句话答法**：x86 的普通 load/store 基本不乱序，ARM 允许更多重排；共享数据的发布必须用 release/acquire 或屏障，不能依赖 x86 的偶然顺序。

3. **问法**：什么时候必须看汇编？
   **考点**：C 抽象泄漏的边界。
   **一句话答法**：性能热点、UB 被优化、ABI/栈对齐崩溃、原子与屏障、逆向和系统指令这些场景必须看；普通业务逻辑先信 C。

4. **问法**：x86 的 `cmov` 和 ARM 的 `csel` 是一回事吗？
   **考点**：标志位依赖与条件选择。
   **一句话答法**：目的都是免分支选择，但 x86 依赖 flags 且受依赖链限制，AArch64 条件后缀更自由、三操作数直接选，编译器按可预测性决定用不用。

5. **问法**：为什么 ARM 反汇编里函数结尾常见 `ret`，x86 是 `ret` 弹栈？
   **考点**：返回地址存放位置。
   **一句话答法**：名字像但语义不同；x86 的 `ret` 从栈顶弹出返回地址，AArch64 的 `ret` 默认跳 `x30`，返回地址在链接寄存器里。

## 第 8 章 装载与运行时：动态加载器、地址空间布局、PIE 与 ASLR

**要解决的问题**：链接器交出的 ELF 文件里，仍然有一批地址没有确定：共享库符号的最终位置不知道、主程序被放到哪里也不知道。这一章要回答的是“从 `execve` 返回到进入 `main` 之间，谁把 ELF 变成进程内存中可运行的映像，以及 PIE 和 ASLR 如何介入”。不解决它，PLT/GOT 就只能背下来而说不出为什么需要，`undefined reference` 和运行时 `symbol lookup error` 就会混为一谈。

**机制**

分工如下：内核只做“映射”，不做“符号解析”。

1. `execve` 读 ELF header；若存在 `PT_INTERP` 段，就把 `/lib64/ld-linux-x86-64.so.2`（AArch64 上是 `ld-linux-aarch64.so.1`）也映射进来，并把控制权交给它的入口，而不是交给程序自己的入口。
2. 内核按 `PT_LOAD` 段建立映射。`ET_EXEC`（非 PIE）按文件里写死的 vaddr 映射；`ET_DYN`（PIE 或 `.so`）由内核挑一个随机基址，各段按 `p_vaddr` 平移。
3. 内核在栈上压入 `argc/argv/envp` 和**辅助向量**：`AT_PHDR`（重定位需要的程序头表地址）、`AT_ENTRY`（真正入口）、`AT_BASE`（解释器基址）、`AT_RANDOM`、`AT_PAGESZ` 等。动态加载器靠这些信息接手。
4. `ld.so` 自举：它自己也是 `ET_DYN`，在 GOT 可用之前的那段引导代码必须不依赖重定位。随后按 `DT_NEEDED` 广度优先加载依赖、建全局符号作用域（主程序在前，`LD_PRELOAD` 插在主程序之后，其余按加载顺序）、逐条处理重定位表、设置 TLS、跑 `DT_INIT`/`DT_INIT_ARRAY`，最后跳到 `AT_ENTRY`。

重定位在两种模式下差别很大。**非 PIE** 时符号地址在链接期已定，动态重定位几乎为零；**PIE** 时链接器把“`基址 + 常量`”这种形式写成相对重定位：

```text
x86-64 : R_X86_64_RELATIVE   value = load_base + addend
AArch64: R_AARCH64_RELATIVE  value = load_base + addend
```

加载器只需加一个基址，无需查符号表；只有跨模块的符号才走 `R_*_GLOB_DAT`/`R_*_JUMP_SLOT` 这类需要查符号表的类型。

**x86-64 与 AArch64 的关键对照在这里**：PIC 的取址方式不同。x86-64 有 RIP 相对寻址，一条指令就能拿到“当前指令附近”的符号地址：

```asm
lea rax, [rip + foo]        ; 与基址无关，链接期就能定
```

AArch64 没有“PC 相对的数据寻址”，只有 `ADR`/`ADRP` 给出页基址，所以 PIC 必须两步：

```asm
adrp x0, foo                ; 取 foo 所在 4KB 页基址（±4GB 范围，立即数左移 12）
add  x0, x0, :lo12:foo      ; 加页内偏移，得到最终地址
```

`ADRP` 的立即数以 4KB 为粒度编码，所以 AArch64 的 PIC 天然是“页相对”的，链接器和加载器都按页对齐处理，这也是为什么 AArch64 上 `-fPIC` 比 x86-64 更依赖“两步取址”。

**延迟绑定**把符号解析推迟到首次调用。以 x86-64 为例，`call puts@plt` 落到：

```asm
plt_puts:
    jmp  *GOT_puts(%rip)    ; 首次指回下一条 push
    push $reloc_index
    jmp  plt0               ; plt0 里 push GOT[1]，再 jmp *GOT[2]
```

`GOT[0]` 指向 `_DYNAMIC`，`GOT[1]` 是 `link_map`，`GOT[2]` 是 `_dl_runtime_resolve`。解析器解析完成后会把真实地址写回 `GOT_puts`，第二次调用就直达。AArch64 没有 x86 那样开销很低的单条“把索引压栈”指令，PLT 用 `stp` 把 `x16/x17` 存栈、寄存器传索引与 `link_map` 跳进解析器；具体指令序列随 binutils 版本变化，但“`GOT[0..2]` 三个特殊槽 + 首次回跳 + 写回”的语义一致。`-z now`（`BIND_NOW`）在加载时一次解析完所有 `JUMP_SLOT`，配合 `RELRO` 把 `.got` 设为只读——这正是 ASLR 之外的另一道防线。

**ASLR** 由 `/proc/sys/kernel/randomize_va_space` 控制（0 关、1 部分、2 全开）。它随机化：栈顶、`mmap` 基址（共享库落在这一区）、`brk` 起始（堆）、以及 PIE 主程序的基址。非 PIE 的主程序基址恒为 `0x400000`，无法随机化，只剩库和栈在动。随机化粒度为页对齐，具体取值范围按内核与架构实现而定：x86-64 用户空间是 47 位 VA，AArch64 常见 48 位（可选 52 位），这决定了两边 `mmap` 区和栈的相对距离不一样，但不改变布局次序：低地址程序映像 → 堆向上 → `mmap` 区向下 → 栈在高地址向下。

**最小例子**

同一个 PIE 程序，两次运行：

```text
$ readelf -h a.out | grep Type
  Type: DYN (Position-Independent Executable file)
$ readelf -r a.out | grep -m1 RELATIVE
0000000011a9  000000000008 R_X86_64_RELATIVE  11a9

run1: &main=0x5555_5555_51a9   puts@libc=0x7fff_f7e0_8e50
run2: &main=0x5f3c_2b91_21a9   puts@libc=0x7f2a_4c05_2e50
```

两件事可以当场验证：一，`main` 的地址等于 `基址 + 0x11a9`，两次基址不同，但**低 12 位始终是 `0x1a9`**，因为页内偏移不随机；二，`puts` 属于 libc，落在 `mmap` 区，和主程序不在同一段。换成 `-no-pie` 编译，`main` 两次都是 `0x4011a9`，而 `puts` 依旧每次不同——这说明 ASLR 生效与否要分段看。

对应的 AArch64 二进制里，同一条重定位叫 `R_AARCH64_RELATIVE`，`main` 的取址是 `adrp/add` 两条，页内偏移的低 12 位同样不变。

**面试高频问法**

1. **“`execve` 到 `main` 之间发生了什么？”** → 考点是内核态与用户态加载器的分工边界。答法：内核按 `PT_LOAD` 映射主程序和 `PT_INTERP` 指定的 `ld.so`，压好辅助向量就跳 `ld.so` 入口；`ld.so` 加载依赖、建符号作用域、做重定位、跑 `init_array`。符号解析完全在用户态完成，内核不知道符号是什么。注意 `exit` 时 `fini_array` 与 `atexit` 也不是内核做的。

2. **“PIE 和 ASLR 是什么关系？”** → 考点是“随机化需要位置无关作为前提”。答法：PIE 让主程序变成 `ET_DYN`、代码用相对寻址、链接期用 `RELATIVE` 重定位，因此加载器可以把它放在任意基址；没有 PIE 的 `ET_EXEC` 必须落在固定 `0x400000`，ASLR 只能随机化库、栈、堆。反过来，PIE 不开 ASLR 也能跑，只是基址固定。

3. **“延迟绑定到底省了什么，代价是什么？”** → 考点是 PLT/GOT 三槽语义与安全取舍。答法：省的是启动时对所有 `JUMP_SLOT` 的符号查找，首次调用多一次 `_dl_runtime_resolve`；代价是 `.got` 必须可写，给 GOT 覆写类攻击留了口子。`-z now` 用启动时间换 `RELRO` 只读，现代发行版默认全量绑定。

4. **“为什么 AArch64 做 PIC 要用 `ADRP` + `ADD` 两条，而 x86-64 一条就够？”** → 考点是 ISA 对“PC 相对数据寻址”的支持差异。答法：x86-64 的 `RIP` 相对寻址在指令里直接编码 32 位位移；AArch64 的 `ADR/ADRP` 只能给出页基址（`ADRP` 立即数左移 12、范围 ±4GB），页内偏移得再补一条 `ADD` 或 `LDR :lo12:`。

5. **“开了 ASLR 为什么还会被 ROP 打穿？”** → 考点是随机化的信息边界。答法：ASLR 只随机化**基址**，不隐藏内容；任何一处地址泄露（格式化字符串、越界读）就把相对偏移换算回绝对地址，而代码段内部各 gadget 的相对位置是链接期固定的，所以一次泄露往往就能全段利用。它的定位是提高利用门槛，不是消除漏洞。

6. **“运行时 `symbol lookup error` 和链接时 `undefined reference` 是一回事吗？”** → 考点是解析发生在哪个阶段。答法：`undefined reference` 是静态链接阶段在本次链接的输入里找不到定义；`symbol lookup error` 是加载器在运行时按作用域（主程序 → `LD_PRELOAD` → `DT_NEEDED`）找不到，或找到的版本不匹配（`GLIBC_2.34` 之类符号版本）。前者能靠加库解决，后者常要靠 `LD_LIBRARY_PATH`/`patchelf` 或重编。
