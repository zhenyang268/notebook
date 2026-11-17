# xv6 · 分章详细

> 编排，不是教材：每章四段——**要解决的问题 / 机制 / 最小例子 / 面试高频问法**。
> 口径：**功能视图优先**。先回答「它让我能干什么」，结构只在解释「为什么这次访问会/不会失败」时展开。
> 每章末尾的「下钻」只在被追问时翻；平时停在功能层。
> 机制因果与三内核对照见 `../kernel-compare/`，驱动四步见 `../drivers/`，本文不重写。
> lab 任务名与骨架以你 clone 的那一版为准（2023/2024 骨架任务名一致，函数签名可能微调）。

## 怎么用

三条线并行，缺一条就变成背书：

| 线 | 动作 | 产出 |
|---|---|---|
| 读 | 只读该 lab 涉及的两三个函数，不读全仓 | 能说出「这函数替谁做了什么」 |
| 停 | 断在入口，`info registers` + 打结构体 | 一张「这一刻各寄存器是什么」的表 |
| 改 | 按 lab 判据改，改坏一次再修好 | 能说出「哪三行、为什么必须这样」 |

一张总表，先把位置钉住：

| lab | 主要源码 | 第一断点 | 判据 |
|---|---|---|---|
| pgtbl | `vm.c`（`walk`/`mappages`/`kvmmap`）、`proc.c`（`proc_pagetable`） | `b walk` | `vmprint` 能读；共享页写一下会 fault |
| traps | `trampoline.S`、`trap.c`、`syscall.c`、`proc.h` | `b usertrap` | 单步走完 `ecall→sret`；`a0` 不被 handler 破坏 |
| cow | `kalloc.c`、`vm.c`（`uvmcopy`）、`trap.c` | `b cowfault` | 空闲页数回初值 |
| fs | `bio.c`、`log.c`、`fs.c` | `b commit` | 写大文件中途断电，长度不半截 |
| net | `e1000.c`、`net.c` | `b e1000_recv` | ping 通；`RDT` 按序推进 |

---

## 第 0 章 环境与三个固定动作

**要解决的问题**：让「看内核状态」变成一条命令，而不是一次折腾。这一章不学机制，只把工具链和三个动作练成肌肉记忆。

**机制**：

**工具链（macOS）**。xv6 需要 RISC-V 交叉编译器、对应的 gdb、以及 QEMU 的 riscv64 系统模拟器。Homebrew 里有对应的 formula（`riscv64-elf-gcc` / `riscv64-elf-gdb` / `qemu`；名字对不上就 `brew search riscv`）；xv6 的 Makefile 默认前缀是 `riscv64-unknown-elf-`，所以要么装前缀匹配的 `riscv-tools`，要么每次覆盖：

```bash
make TOOLPREFIX=riscv64-elf- qemu
```

装完先验一句 `riscv64-elf-gcc --version`，再看 `qemu-system-riscv64 --version`。**版本不重要，能编出 `kernel/kernel` 才重要**。

**三个固定动作**：

1. **跑起来**：`make qemu`。`Ctrl-a x` 退出，`Ctrl-a c` 进 QEMU monitor（看 `info registers`、`xp` 物理内存）。默认 `CPUS=3`；凡是「单核下才成立」的推理，一律 `make CPUS=1 qemu`。
2. **停下来**：`make qemu-gdb` 挂起等连接，另开一个终端跑 `riscv64-elf-gdb`。仓库自带 `.gdbinit` 已经把 `set architecture riscv:rv64` 和 `target remote localhost:26000` 写好，**不要在仓库外启动 gdb**，否则连不上。
3. **打出来**：内核里最值钱的三条打印是 `vmprint(p->pagetable)`（页表）、`backtrace()`（调用链）、`procdump()`（进程表）。前两个是 lab 让你写的，第三个 xv6 自带。

**gdb 里最常用的六条**（当前进程用 `myproc()`，gdb 不展开 C 里的局部宏）：

```text
p/x $satp                      # 当前页表基址（低位是 PPN）
p/x $sepc                      # 陷入时保存的返回地址
p/x $scause                    # 陷入原因：8=ecall 15=写缺页 13=读缺页
p/x $stval                     # 出错地址（page fault 时）
p *myproc()                    # 当前进程
x/36gx myproc()->trapframe     # 288 字节 = 5 个簿记字段 + 31 个寄存器
```

**最小例子**（一次完整的「停住—看清—继续」）：

```bash
make CPUS=1 qemu-gdb          # 终端 1
riscv64-elf-gdb               # 终端 2
(gdb) b usertrap
(gdb) c                       # 在 shell 敲一条 ls，命中断点
(gdb) p/x $scause             # 8 → 这条是 ecall
(gdb) p/x myproc()->trapframe->a7   # 系统调用号
(gdb) x/36gx myproc()->trapframe    # 现场
(gdb) c
```

**面试高频问法**：

1. **「你怎么证明自己真的跑过，而不是看了讲义？」** → 考点：可复现的动作。答法：说出三个断点分别停在哪、命中时哪一个寄存器的值是什么；比如 `b usertrap` 命中时 `$scause==8`、`p->trapframe->a7` 就是系统调用号。**不要**说「我看完了 xv6 book」。
2. **「为什么要单核跑？」** → 考点：并发是不是干扰项。答法：这一轮学的是单进程机制，多核只会让「同一个断点被三个 hart 抢着命中」，干扰观察；而且 `CPUS=3` 时有些单核下看不见的错（引用计数、`e1000` 寄存器竞争）才会暴露——所以要**两种都跑**，单核看路径，多核看竞争。

---

## 第 1 章 能力地图

**要解决的问题**：把「进程能干什么」变成一张可以背下来、可以画在白板上的图，而不是一堆页表位。

**机制**：

**先划两条线。** 功能视图回答四个问题：**有哪些段、每段什么权限、每段上的读/写/执行分别发生什么、这条权限由谁在什么时候改**。结构视图回答另外四个：页表几级、每级多少项、PTE 的哪一位是什么、物理帧从哪来。**本轮只常驻功能视图**；结构视图是「下钻」，只有当你需要解释某次访问为什么失败时才翻。

**init 进程的能力地图**（xv6，单核）：

```text
0x0                  ┌────────────────────┐
                     │ text      R-X  U   │  执行 OK；写 → scause 15（PTE_W=0）
                     ├────────────────────┤
                     │ data/bss  RW-  U   │  读 OK；写 OK
                     ├────────────────────┤
                     │ heap      RW-  U   │  sbrk 一页一页往上推，边界是 p->sz
                     │   ...              │
                     ├────────────────────┤
                     │ stack     RW-  U   │  向下长；栈底有一页没映射（越界即 fault）
                     └────────────────────┘
TRAMPOLINE            │ trampoline R-X ─   │  U=0：只有陷入瞬间 CPU 用
TRAPFRAME             │ trapframe RW-  ─   │  U=0：用户碰 → scause 13
KERNBASE..PHYSTOP     │ 内核直接映射        │  text 是 R-X、data 是 RW；U=0
```

三条从图上直接读出来的结论：

1. **「能不能访问」= 页表项存在 + `U=1` + 对应 `R/W/X`**，不是「代码里检查了」。所以用户态碰 `TRAMPOLINE` 一定 fault，哪怕它就在用户的页表里。
2. **「写一下会怎样」由 `PTE_W` 与 COW 组合决定**：`W=1` 直接写；`W=0` 且是 COW 页 → 缺页后复制；`W=0` 且不是 COW 页（代码段）→ 杀进程。
3. **「访问一段新的会怎样」由「有没有映射」决定**：xv6 没有 lazy allocation，`sbrk`/`uvmalloc` 在推高 `p->sz` 的同时就把物理页建好，所以「边界推高」和「可访问」在 xv6 里是同步的；Linux 里两者分开，才有 minor fault 这一步。

**谁在什么时候改这些权限**（这张表比 PTE 位图有用）：

| 时刻 | 谁改 | 改什么 |
|---|---|---|
| `exec` | `exec.c` → `proc_pagetable` / `loadseg` / `uvmalloc` | 换掉整张用户页表：代码 R-X、数据 RW、栈 RW |
| `sbrk` | `sys_sbrk` → `growproc` → `uvmalloc` | 把 `p->sz` 推高并建映射 |
| `fork` | `uvmcopy` | 父子两边都清 `PTE_W`（COW lab 改这里） |
| 写 COW 页 | `cowfault` | 新页映射成 `RW`，旧页计数减一 |
| 每次陷入/返回 | `usertrapret` / `userret` | 换 `satp`；不改编页内容 |

**三种快照各回答什么**（别混用）：

| 快照 | 回答 | 看不到 |
|---|---|---|
| `vmprint`（xv6） | 内核眼里的页表树：哪些虚拟页映射到了哪些物理页 | 权限位、段名 |
| `pmap` / `/proc/PID/maps`（Linux） | 用户眼里的段：起始、长度、权限、来源文件 | 物理页、页表层级 |
| `backtrace`（xv6） | 调用链：谁调了谁 | 数据、页表 |

xv6 里没有 `pmap`；等价物是 `vmprint`（结构）+ 一个三行用户程序打印 `sbrk(0)` 与栈上变量地址（边界）。两者一对，就是「结构 + 功能」的完整静态快照。

**下钻表**（只在被追问时翻）：

| 问题 | 翻哪里 |
|---|---|
| 用户态为什么不能访问内核页？ | `PTE_U=0`，`trap.c` 不参与，是硬件拒绝 |
| 为什么改页表后要 `sfence.vma`？ | TLB 缓存了旧翻译；换 `satp` 或改 PTE 后必须刷 |
| 三级页表每级多少项？ | 512 项、9 位索引、4KB 页；`riscv.h` 的 `PX` 宏 |
| 物理帧从哪来？ | `kalloc.c` 的 freelist，页大小固定 4KB |

**最小例子**：跑起来之后，在 `exec.c` 里临时加一行 `if(p->pid==1) vmprint(p->pagetable);`，然后对照上面的地图读输出：用户段的项集中在最下面，`KERNBASE` 附近一大段连续的直接映射，顶端两项是 trampoline 与 trapframe。**判据**：能指着任何一项说出「这是哪一段、能不能被用户访问」。

**面试高频问法**：

1. **「给你一个地址，你怎么判断用户态能不能访问？」** → 考点：功能视图的最小单元。答法：先看有没有映射（`walk` 返回非空且 `PTE_V`），再看 `PTE_U`，再看操作对应的 `R/W/X`。三者缺一就 fault。边界：内核态访问用户地址还要过 `copyin`/`copyout` 的检查，不能直接解引用。
2. **「为什么代码段可执行不可写，数据段可写不可执行？」** → 考点：权限位不是「性能优化」。答法：这是 W^X，把「改指令」这条攻击路径关掉；xv6 里直接体现为内核页表 `text` 映射成 `R-X`，用户代码段同理。边界：xv6 没有 NX 的完整生态，讲的时候说清这是最小实现。
3. **「进程的内存为什么不是一次分完的？」** → 考点：虚拟与驻留的区别。答法：`p->sz` 是「能访问到哪」，物理页是按需建的；`sbrk` 只改前者。判据：`/proc/PID/statm` 的 vsize 与 rss 之比（Linux 侧）。
4. **「你说 `TRAMPOLINE` 在用户页表里，那用户能执行它吗？」** → 考点：`U=0` 比「在不在页表里」更本质。答法：不能，因为 `PTE_U=0`；它在用户页表里只是为了让「换 `satp` 那一刻」的取指地址在两个页表里都有效。

---

## 第 2 章 pgtbl：把「能看见的世界」划出来

**要解决的问题**：进程凭什么只能看见自己那一段内存；一次访问凭什么成功或失败。

**机制**：

**功能层**。内核启动时先给自己建一张页表，把物理内存**恒等映射**（虚拟地址 = 物理地址），于是 `kalloc` 返回的指针可以直接用，不需要地址转换；代码段映射成 `R-X`、数据段 `RW`，所以写内核代码会 fault。每个进程再有自己的一张页表，内容是「用户段 + 同一份内核直接映射 + 顶端 trampoline/trapframe 两页」。**内核映射在每张用户页表里都有一份，但 `U=0`**——这就是为什么用户态看不见内核，而陷入时不用换页表也能继续跑（xv6 不做 KPTI）。

**结构层（必要最小）**。Sv39：三级，每级 512 项，`va` 切成 9/9/9/12 位。`walk(pagetable, va, alloc)` 从顶层往下走，返回最后一级 PTE 的指针；中间级不存在且 `alloc=1` 时就 `kalloc` 一页并挂上。`mappages` 按页循环调 `walk` 并写 PTE，**重复映射会 panic**——这是有意的，它把「两个虚拟页指向同一物理页但权限不同」这种 bug 挡在早期。

`kvmmap` 只做一件事：把 `(va, pa, size, perm)` 交给 `mappages`。`kvminit` 用它建内核页表：内核 text → `R-X`；内核 data → `RW`；UART / PLIC / virtio 的 MMIO → `RW`；trampoline → `R-X`。

`proc_pagetable` 建用户页表：先 `uvmcreate`，再映射 trampoline（`PTE_R|PTE_X`）与 trapframe（`PTE_R|PTE_W`），都**不带** `PTE_U`。lab 的 USYSCALL 任务在这里再加一页 `PTE_R|PTE_U`。

**三个 lab 任务各自补哪条功能**（这是本章的重点：不是「三个练习」，是三条能力）：

| 任务 | 功能 | 为什么必须这样做 |
|---|---|---|
| USYSCALL（只读共享页） | 让用户读一个内核维护的值（如 `pid`）而不用系统调用 | 必须**只读**。若可写，用户能改一个内核会信的值，等于提权 |
| `vmprint` | 把「结构快照」变成人能读的东西 | 它是 pgtbl 的验收工具，也是后面 COW、`exec` 调试的唯一视图 |
| `pgaccess` | 让内核知道「这一页被碰过」 | 靠页表项的 A 位；内核的活是**读出 + 清零**，不清零就永远是「访问过」 |

`pgaccess` 的边界值得单独说：A 位由地址翻译过程置位（Rv64 允许硬件置位，QEMU 的具体行为以你跑的那版为准），内核不能假设「置位时机」精确到某条指令，只能得到「这期间碰过」这种粗粒度结论——这正是页回收/工作集估计要的粒度，不是精确追踪。

**下钻表**：

| 问题 | 翻哪里 |
|---|---|
| PTE 里到底有哪几位？ | `riscv.h` 的 `PTE_V/R/W/X/U/G/A/D`；本章只用到 `V/R/W/X/U` |
| 三级索引怎么算？ | `PX(level, va)`；顶层是 2，底层是 0 |
| 为什么内核映射是恒等的？ | 省一次转换，`kalloc` 的返回值可以直接当指针用 |
| 换页表之后为什么不会崩？ | 内核映射在每张页表里都在，且 trampoline 同址 |

**最小例子**：

```text
(gdb) b walk
(gdb) c
(gdb) p/x va                       # 这次要翻译的地址
(gdb) finish                       # 返回最后一级 PTE 的指针（在 $a0）
(gdb) p/x $a0                      # 非 0 说明路径存在
(gdb) p/x (*$a0) & 0x1f            # 低 5 位 = V/R/W/X/U
```

判据有三条，缺一条都不算过：

1. `vmprint` 的输出能分段解释（用户段 / 直接映射 / 顶端两页）。
2. 写一下 USYSCALL 那页，能看到 `scause=15` 而不是「成功」。
3. `pgaccess` 第一次报「访问过」，第二次（未再访问）报「没访问过」——说明清零生效。

**面试高频问法**：

1. **「虚拟地址到物理地址怎么走？」** → 考点：三级索引 + 页内偏移。答法：`va` 切 9/9/9/12，逐级查表，最后一级 PTE 的高位是物理页号，拼上 12 位偏移。判据：`vmprint` 里能对上某一项。边界：走表本身是访存，所以有 TLB；TLB 命中时不会走这三步。
2. **「为什么每次改页表都要 `sfence.vma`？」** → 考点：TLB 一致性。答法：TLB 缓存了旧翻译，改 PTE 不会自动失效；xv6 在换 `satp` 之后刷一次全量。边界：xv6 图省事全刷，真实内核按地址刷（`sfence.vma vaddr`）。
3. **「多级页表省了什么？」** → 考点：稀疏映射。答法：省的是「为没用到的地址预留页表页」；代价是每次翻译多几次访存。边界：这也是大页存在的原因——同一段连续映射用大页能砍掉层级。
4. **「共享一页给用户，为什么必须只读？」** → 考点：内核信任边界。答法：任何「内核会读、用户能写」的内存都是提权原语；只读把这条路径关掉。判据：写它触发 15，说明页表项确实没有 `W`。

---

## 第 3 章 traps：一条 `ecall` 的六步

**要解决的问题**：用户进程怎么把控制权交给内核，又怎么能原样回来。

**机制**：

**功能层**。一条 `ecall` 让「我的进程」暂停，内核代表它做事（读文件、分配内存），然后从**下一条指令**继续，寄存器看起来没被动过。要做到这一点，必须有三个东西：一个**用户态不能改的入口地址**（`stvec`）、一个**用户态不能改的现场存放处**（trapframe，`U=0`）、一个**硬件提供的返回地址**（`sepc`）。

**六步，每步的寄存器状态**（这张表就是「状态查看器」的核心，建议背下来）：

| 时刻 | `pc` | `sp` | `satp` | `stvec` | `sscratch` |
|---|---|---|---|---|---|
| U 态执行 `ecall` 前 | 用户下一条 | 用户栈 | 用户页表 | `TRAMPOLINE+uservec` | `TRAPFRAME` |
| `uservec` 第一条 `csrrw` 后 | trampoline | 用户栈 | 用户页表 | 同上 | 用户的 `a0` |
| 存完 31 个寄存器、取 `kernel_sp` 后 | trampoline | 内核栈顶 | 用户页表 | 同上 | 用户的 `a0` |
| `csrw satp` + `sfence.vma` 后 | trampoline | 内核栈顶 | **内核页表** | 同上 | 用户的 `a0` |
| `jr t0` 进 `usertrap` 后 | `usertrap` | 内核栈 | 内核页表 | **`kernelvec`** | 用户的 `a0` |
| `sret` 之后 | 用户下一条 | 用户栈 | 用户页表 | `TRAMPOLINE+uservec` | `TRAPFRAME` |

**逐步说明**：

1. **硬件只做三件事**：`pc → sepc`、原因 `→ scause`、`pc → stvec`。**不换栈、不存寄存器**。所以 `uservec` 的第一条必须是「拿到 trapframe 地址」，而 trapframe 地址只能藏在 `sscratch` 里。
2. **`csrrw a0, sscratch, a0`** 一条指令完成两件事：`a0` 变成 `TRAPFRAME`，用户的 `a0` 进了 `sscratch`。少一条指令就少一个中断窗口。随后 `csrr t0, sscratch; sd t0, 112(a0)` 把用户 `a0` 补存到偏移 112。
3. **存完 31 个寄存器**，才敢用寄存器：从 trapframe 取 `kernel_sp`（偏移 8）、`kernel_satp`（偏移 0）、`kernel_trap`（偏移 16）。
4. **`csrw satp` 必须在跳 `usertrap` 之前**：约定是「内核代码永远跑在内核页表下」。xv6 不做 KPTI，用户页表里也有一份内核映射，所以顺序写反有时**侥幸**能跑——这比直接崩更坏，因为它把「巧合」当成了「正确」，加 KPTI 或改映射立刻崩。
5. **`usertrap` 第一句把 `stvec` 换成 `kernelvec`**：否则内核里再发生一次中断，会又跳回 `uservec`，把内核现场当用户现场存，直接毁掉。
6. **`scause==8` 时 `myproc()->trapframe->epc += 4`**：`sepc` 指向 `ecall` 本身，不 `+4` 就会原地打转。这一条最容易漏，症状是「系统调用无限重复」。

**trapframe 布局**（`proc.h`；前 40 字节不是寄存器）：

| 偏移 | 字段 | 谁写 |
|---|---|---|
| 0 | `kernel_satp` | `usertrapret` |
| 8 | `kernel_sp` | `usertrapret` |
| 16 | `kernel_trap` | `usertrapret`（= `usertrap` 地址） |
| 24 | `epc` | 硬件写 `sepc` 后由 `usertrap` 同步；`syscall` 的返回值也走这里 |
| 32 | `kernel_hartid` | `usertrapret` |
| 40 起 | 31 个通用寄存器，每个 8 字节 | `uservec` |

`a0` 在 112、`a7` 在 168（`40 + 16*8`）、`ra` 在 40、`sp` 在 48、`s0` 在 96。**改字段顺序 = 改所有偏移 = 一定崩**，这不是概率问题。

**`backtrace`：栈帧规则**。RISC-V 的帧指针 `s0`（gdb 里叫 `fp`）指向当前帧，`fp-8` 是返回地址、`fp-16` 是上一帧的 `fp`。因为内核栈是一页且向下增长，**越老的帧地址越高**，所以循环上界是 `PGROUNDUP(fp)`。`backtrace` 的价值不是「能打印」，而是**它证明了 trapframe 与调用链是同一套栈**——你在 `usertrap` 里打出来的链，就是 `syscall → sys_write → filewrite` 那一条。

**`sigalarm`：为什么必须整份保存 trapframe**。定时器 handler 是在用户态执行的，返回时必须回到「被打断的那条指令」。做法：tick 到点 → 把当前 trapframe 整份复制一份存起来 → 把 `epc` 改成 handler 地址 → handler 返回时走 `sigreturn` → 把副本整份写回。**只要漏存一个寄存器就错**：lab 的 `test3` 专门检查 `a0` 等寄存器在 handler 之后是否原值，漏存 `a0` 会让「handler 里调了 printf」变成「主流程的 `a0` 被改」。这也是「保存现场要全量」最直观的一次教训。

**最小例子**：

```text
(gdb) b usertrap
(gdb) c
(gdb) p/x $scause                       # 8
(gdb) p/x myproc()->trapframe->epc      # 指向 ecall
(gdb) p/x $satp                         # 内核页表
(gdb) b syscall
(gdb) c
(gdb) p myproc()->trapframe->a7         # 系统调用号
(gdb) p/x myproc()->trapframe->a0       # 返回值
```

判据：能不看书说出表中六行的 `satp`/`stvec`/`sscratch` 三个值，并解释每一次变化是**谁**改的。

**面试高频问法**：

1. **「`ecall` 之后，内核怎么知道该用哪个栈？」** → 考点：谁换栈。答法：硬件不换，`uservec` 从 trapframe 的 `kernel_sp` 取（这个值是上次返回时 `usertrapret` 填的）。边界：x86-32 由 TSS 硬件换，对比见 `../kernel-compare/` 第 3 章。
2. **「trapframe 为什么要放在用户页表里，不是内核里？」** → 考点：换 `satp` 之前还得能写内存。答法：`uservec` 的第一条指令发生时 `satp` 还是用户页表，trapframe 必须在那个页表里可见；`U=0` 保证用户碰不到。边界：KPTI 之后这个安排变成必需，不再是「省事」。
3. **「系统调用号和参数怎么传？」** → 考点：ABI 与 trapframe。答法：`a7` 是号，`a0`–`a5` 是参数，`syscall()` 按 `a7` 查表，返回值写回 `a0`。判据：`b syscall` 时 `p->trapframe->a7` 就是 `SYS_write` 的编号。
4. **「中断和异常在入口上有什么不同？」** → 考点：`scause` 的最高位。答法：中断的最高位是 1，异常是 0；`usertrap` 里先判 8，再用 `devintr()` 认中断（时钟 → `yield`）。边界：内核态发生的中断走 `kernelvec`，不经过 `usertrap`。

---

## 第 4 章 cow：看起来各有一份，写的时候才分

**要解决的问题**：`fork` 之后父子「各有一份内存」是假象，真复制太贵；要在**写的那一刻**才复制，且不能复制错、不能漏减。

**机制**：

**功能层**。`fork` 返回后，父子读到的是同一份数据，任何一方写，**只有它自己**看到变化。这是「延迟复制」：fork 时只把两边的 PTE 都改成只读并打标记，谁写谁触发缺页，缺页处理里才真复制。

**三块改动**：

1. **引用计数**（`kalloc.c`）：一张按页号索引的表，`kalloc` 置 1，`kfree` 减 1、减到 0 才真回收。索引用 `(pa - KERNBASE)/PGSIZE`，表长 `(PHYSTOP-KERNBASE)/PGSIZE`（128MB → 32768 项）。**不要**用 `pa/PGSIZE` 直接索引却又只开 32768 项——那会越界，症状是随机踩坏别的全局变量。
2. **`uvmcopy` 不再复制**（`vm.c`）：遍历父页表，把父的 PTE 清 `PTE_W` 并打 `PTE_COW`，子页表用同样的权限映射同一个物理页，计数加一。
3. **写缺页处理**（`trap.c`）：`usertrap` 看到 `scause==15` 调 `cowfault(PGROUNDDOWN(r_stval()))`。

**`cowfault` 的顺序**（顺序错就是 bug）：

```c
pte_t *pte = walk(p->pagetable, va, 0);
if(pte == 0 || (*pte & PTE_V) == 0) goto bad;   // 未映射：非法
if(*pte & PTE_W) return;                        // 已经可写：不是 COW
if((*pte & PTE_COW) == 0) goto bad;             // 只读但不是 COW：代码段，非法
uint64 pa = PTE2PA(*pte);
char *mem = kalloc();
memmove(mem, (char*)pa, PGSIZE);
uint64 flags = (PTE_FLAGS(*pte) | PTE_W) & ~PTE_COW;
uvmunmap(p->pagetable, va, 1, 0);               // 先拆旧映射，do_free=0
mappages(p->pagetable, va, PGSIZE, (uint64)mem, flags);
kfree((void*)pa);                               // 旧页计数减一
```

**三个必错点**：

- **只改子不改父**：父进程写会直接写穿共享页，子进程莫名看到变化。两边都必须清 `PTE_W`。
- **`mappages` 之前不 `uvmunmap`**：xv6 的 `mappages` 遇到已存在的映射直接 panic。拆的时候 `do_free=0`，物理页由后面的 `kfree` 管。
- **把一个正常只读页当 COW**：代码段也是 `W=0`，但它是合法的只读。必须有 `PTE_COW` 这个标记来区分，否则 `cowfault` 会给代码段也复制一页，浪费且掩盖真正的非法访问。

**为什么是 `scause==15` 而不是 13**：13 是读缺页，读不需要分裂；把 13 也交给 COW，会在「读一个未映射地址」时错误地分配页，把段错误变成静默成功。

**最小例子**：

```text
(gdb) b cowfault
(gdb) c
(gdb) p/x $stval                 # 出错地址
(gdb) p/x *(uint64*)walk(myproc()->pagetable, $stval & ~0xfff, 0)   # 旧 PTE：W=0、COW 位=1
(gdb) p kcount.count[(pa - KERNBASE)/PGSIZE]                # 计数 > 1
```

判据（比 `forktest` 更狠的一条）：跑完 `forktest` 后 `p kcount.count[...]` 全为 0、空闲页数回到启动时的值。`forktest` 只保证没立刻崩，不保证没漏。

**面试高频问法**：

1. **「fork 那一刻，父子的页表项是什么状态？」** → 考点：COW 的静态快照。答法：同一个物理页、两边 `W=0`、都带 COW 标记、计数为 2。判据：`/proc/PID/smaps` 的 `Shared_Clean` 与 `Private_Dirty` 随写变化（Linux 侧）。
2. **「为什么不在 `uvmunmap` 里减计数？」** → 考点：释放路径不止一条。答法：`uvmunmap`、`uvmcopy` 的回滚、`cowfault` 换页都要释放；收敛到 `kfree` 只有一处要验。边界：计数表要锁，多核下先崩的是计数。
3. **「COW 复制的是哪一页，怎么保证不复制错？」** → 考点：地址对齐。答法：`r_stval()` 给出的地址要在页内，必须 `PGROUNDDOWN` 后查 PTE；不对齐会用错页。
4. **「COW 和 `vfork`/`posix_spawn` 什么关系？」** → 考点：不复制路径。答法：`vfork` 干脆共享地址空间、父阻塞，完全不复制；`posix_spawn` 在 Linux 上常走 `CLONE_VM|CLONE_VFORK`。不要混着讲。

---

## 第 5 章 fs：断电之后文件还在，且不半截

**要解决的问题**：一次写操作会改好几处磁盘结构（数据块、inode、位图、目录），断电可能停在任意一步。要有「要么全做、要么全不做」。

**机制**：

**功能层**。文件系统给两个承诺：**持久**（写成功的，重启后还在）和**原子**（一次系统调用要么完整生效，要么完全没发生）。这两条不是靠硬件，是靠**先写日志再改原位**。

**三层，各管一件事**：

| 层 | 管什么 | 关键函数 |
|---|---|---|
| `bio.c` | 块缓存：同一块只读一次盘，写先落在缓存 | `bget` / `bread` / `bwrite` / `brelse` |
| `log.c` | 事务：把一组块修改打包，原子提交 | `begin_op` / `log_write` / `end_op` / `commit` |
| `fs.c` | 命名空间：inode、目录、路径解析、块映射 | `namei` / `ilock` / `bmap` / `itrunc` |

**写路径**：`begin_op` 预留空间 → 改缓存里的块 → `log_write` 登记（不是立刻写盘）→ `end_op` 触发 `commit`：`write_log`（把块复制进日志区）→ `write_head`（写日志头，记录块号）→ `install_trans`（装回原位）→ `write_head`（`n=0`，清空头）。

**提交点是第二次 `write_head`**，不是第一次。三种崩溃时机的结果：

| 崩在哪 | 重启看到 | 恢复动作 | 用户看到 |
|---|---|---|---|
| `write_log` 中途 | 头 `n=0` | 什么都不做 | 旧内容（事务没提交） |
| `install_trans` 中途 | 头 `n≠0` | 重放一遍（幂等） | 新内容 |
| 第二次 `write_head` 之后 | 头 `n=0` | 什么都不做 | 新内容 |

**吸收（absorption）**：同一事务里同一块被写多次，`log_write` 只登记一次（扫 `log.lh.block[]` 找重复）。没有它，一个事务可能因为重复登记而撑爆日志。

**为什么 `begin_op` 要预留**：日志区固定 30 块，一个事务最多动 10 块。`begin_op` 检查 `log.lh.n + (log.outstanding+1)*MAXOPBLOCKS > LOGSIZE` 就睡等。不预留的话，写到一半发现日志满，没法原子收尾——只能 panic。

**大文件**：`dinode.addrs[]` 是 12 个直接块 + 1 个一级间接（256 项）+ lab 加的一个双间接（256×256）。`bmap` 按 `bn` 分段走，缺项就 `balloc`。容量公式 `(12 + 256 + 256*256) * 1024` 字节 ≈ 64MB 量级。**注意 `itrunc` 要按同样结构逆着释放**，只改 `bmap` 不改 `itrunc` 就是漏块。

**符号链接**：新类型 `T_SYMLINK`，内容是目标路径字符串；`open` 时若 `O_NOFOLLOW` 没给就一直跟，**必须设深度上限（10）**，否则环会让内核栈溢出——这是「不信任用户输入」的最小例子。

**最小例子**：

```text
(gdb) b begin_op
(gdb) b commit
(gdb) b write_head
(gdb) p log.outstanding          # 正在并发的事务数
(gdb) p log.lh.n                 # 本事务登记了几块
```

断电验证：写大文件时在宿主机 `Ctrl-a x` 杀掉 QEMU（不是 `Ctrl-C` 杀 make），重启后 `ls`/读文件长度。判据：长度是旧值或新值，**不是半截**。

**面试高频问法**：

1. **「日志什么时候算提交？」** → 考点：提交点。答法：第二次 `write_head(n=0)` 之前都还可能回滚；`n≠0` 的记录是「重放」的依据。判据：`b write_head` 命中两次，第二次参数是 0。
2. **「为什么不直接写原位，反正也要写？」** → 考点：多处修改的原子性。答法：一次写要改数据块、inode、位图，原位写会在中间断电时留下自相矛盾的状态；日志把「多处」变成一个「头」。边界：代价是每块写两次，所以有 `data=journal` / `ordered` / `writeback` 这类折衷。
3. **「缓冲区缓存和 page cache 是一回事吗？」** → 考点：层次。答法：xv6 的 `bio` 是**块**缓存（按块号），Linux 的 page cache 是**页**缓存且统一管文件与匿名页；`bio` 更接近 `buffer_head` 那一层。边界：说「缓存」必须带口径。
4. **「大文件 lab 改 `bmap` 就够了吗？」** → 考点：分配与释放对称。答法：不够，`itrunc` 也要能释放双间接的两级表，否则删文件漏块。判据：反复建删大文件后空闲块数回初值。

---

## 第 6 章 net：网卡把包放进内存，内核被告知

**要解决的问题**：网卡是异步设备，包什么时候来不知道；内核不能轮询等，也不能让 DMA 写到已经交出去的 buffer。

**机制**：

**功能层**。驱动做四件事：**找设备**（PCI 枚举拿到 MMIO 基址）、**配置**（写控制寄存器、环的基址与长度）、**搬数据**（描述符环 + DMA，CPU 不碰包体）、**处理完成**（中断 + `DD` 位）。这四步与 `../drivers/` 的 JOS 版是同一套，只是寄存器名和环布局不同。

**寄存器与环**。`regs[...]` 是 MMIO 映射的窗口，读写它就是读写设备寄存器。发送环 `tx_ring`、接收环 `rx_ring` 各 16 项，每项是一个描述符（buffer 地址 + 长度 + 状态/命令）。`TDT`/`RDT` 是「软件写到哪」，`TDH`/`RDH` 是「硬件读到哪」。

**所有权时间线**（这一张图比代码重要）：

```text
发送：CPU 填描述符 → 推进 TDT → 网卡读到该槽 → DMA 取走数据 → 置 DD → 槽可复用
接收：网卡写数据 → 置 DD → 发中断 → 内核取 buffer → 换新 buffer → 清 DD → 推进 RDT
```

**`e1000_transmit` 的顺序**（下面是骨架，字段名以你 clone 那版的 `mbuf.h` / `e1000.c` 为准）：

```c
acquire(&lock);
idx = regs[E1000_TDT];
if((tx_ring[idx].status & E1000_TXD_STAT_DD) == 0) { release(&lock); return -1; }  // 环满
if(tx_mbufs[idx]) mbuffree(tx_mbufs[idx]);
tx_ring[idx].addr = (uint64)m->head;
tx_ring[idx].length = m->len;
tx_ring[idx].cmd = E1000_TXD_CMD_EOP | E1000_TXD_CMD_RS;
tx_mbufs[idx] = m;
regs[E1000_TDT] = (idx + 1) % TX_RING_SIZE;   // 最后一步：把所有权交给网卡
release(&lock);
```

**环满返回错误，不等待**：这条路径持有自旋锁，不能睡；丢一个包交给上层重传，比在锁里等安全。**不要在持有自旋锁时调用可能睡眠的函数**——这是 xv6 驱动的通用约束，不是 e1000 特有。

**`e1000_recv` 的顺序**（顺序错就是 DMA 写坏 buffer）：

```c
while(1) {
  idx = (regs[E1000_RDT] + 1) % RX_RING_SIZE;
  if((rx_ring[idx].status & E1000_RXD_STAT_DD) == 0) return;   // 没有了
  rx_mbufs[idx]->len = rx_ring[idx].length;
  net_rx(rx_mbufs[idx]);                    // 交给协议层
  rx_mbufs[idx] = mbufalloc(0);             // 换新 buffer
  rx_ring[idx].addr = (uint64)rx_mbufs[idx]->head;
  rx_ring[idx].status = 0;                  // 清 DD
  regs[E1000_RDT] = idx;                    // 最后一步：还给网卡
}
```

**为什么「最后一步」都是推进游标**：游标是所有权声明。提前推进，等于告诉硬件「这个槽我不用了」，硬件就会往里写，而你还在用里面的数据。

**中断**：`e1000_intr()` 先读 `E1000_ICR` 清中断原因（不清会一直进中断），再调 `e1000_recv()`。

**最小例子**：

```text
(gdb) b e1000_recv
(gdb) c
(gdb) p/x regs[E1000_RDT]        # 软件已处理到哪
(gdb) p/x regs[E1000_RDH]        # 硬件写到哪
(gdb) p rx_ring[(regs[E1000_RDT]+1)%16]
```

判据：宿主机 `ping` 通；`RDT` 每处理一个包前进一格，且与 `RDH` 保持「差一格」的关系（环形缓冲的经典不变式）。

**面试高频问法**：

1. **「为什么用描述符环而不是每次读写寄存器搬数据？」** → 考点：DMA 与批量。答法：寄存器只传「控制」，包体由 DMA 直接进内存；环让「一批」操作只写一次游标。边界：环的深度是延迟与内存的折衷。
2. **「环满了怎么办？」** → 考点：不能阻塞的上下文。答法：返回错误、丢包、上层重传；中断上下文里睡眠是 bug。判据：`transmit` 返回 `-1` 的那条路径能被构造出来（狂发）。
3. **「`DD` 位是谁置的？」** → 考点：所有权。答法：硬件置、软件清（接收侧），发送侧也是硬件置、软件查。两边都「只碰自己该碰的」。
4. **「Linux 里这段代码在哪？」** → 考点：分层。答法：xv6 的 `e1000_recv` 在 Linux 里被拆成硬中断上半部 + NAPI poll 两段，`net_rx` 对应 `napi_gro_receive` 之后的那一层；对照见 `../drivers/` 第 7 章。

---

## 第 7 章 收口：五个 lab 怎么变成面试里的三句话

**要解决的问题**：五个 lab 是五段孤立代码，还是一条能讲清的线。收口只做一件事——**把每个 lab 映射到一个会被追问的问题上**。

**机制**：三列映射。

| lab | 面试会怎么问 | 408 对应章节 |
|---|---|---|
| pgtbl | 虚拟地址怎么翻译、页表项权限、为什么用户碰不到内核 | 内存管理：分页、页表、地址变换 |
| traps | 系统调用/中断/异常的区别、进内核做了什么、现场存在哪 | 进程管理：系统调用、中断与异常、CPU 态切换 |
| cow | `fork` 后页表状态、缺页处理、为什么 minor fault 便宜 | 内存管理：缺页中断、写时复制、虚拟内存 |
| fs | 目录与索引节点、文件分配、缓冲区、崩溃一致性 | 文件管理：目录、文件分配、缓冲区、一致性 |
| net | 中断驱动、DMA、设备驱动分层、环满丢包 | I/O 管理：中断、DMA、设备驱动 |

**一格三答**（详细因果只在 `../kernel-compare/`，这里只标位置）：

| 格 | xv6 | JOS | Linux | 位置 |
|---|---|---|---|---|
| 陷入 | `ecall` + `stvec`/`sscratch` | `int $0x30` + TSS 换栈 | `syscall` + `swapgs` / IDT | `kernel-compare` 第 3 章 |
| 进程结构 | `struct proc`（`kstack`/`pagetable`/`tf`/`chan`） | `struct Env`（`env_tf`/`env_pgdir`） | `task_struct`（`mm`/`files`/`cred`） | 第 4 章 |
| 地址空间 | 每进程页表 + 内核同址映射 | 每 env 页目录 + `UVPT` 自映射 | `mm_struct` + VMA + 多级页表 | 第 5 章 |
| 文件系统 | 内核内 `bio`/`log`/`inode` | 用户态 `fs` 进程 + IPC | VFS + 各具体 FS | 第 8 章 |

**能讲的三句话**（背这三句，不要背 lab 步骤）：

1. **「我的进程能访问哪段内存」** = 页表项存在 + `U=1` + 对应权限位；写只读页触发 `scause=15`，读未映射触发 13。
2. **「一次系统调用怎么进出」** = `ecall` → `uservec`（`sscratch` 换出 trapframe、存 31 个寄存器、切 `satp`）→ `usertrap`（`scause=8`、`epc+=4`）→ `syscall`（`a7` 查表）→ `usertrapret` → `sret`。
3. **「数据怎么从设备进内核且断电不坏」** = 描述符环的所有权（最后一步才推进游标）+ 日志的提交点（第二次 `write_head`）。

**断点速查**：

| 想看什么 | 断点 | 看什么 |
|---|---|---|
| 这条访问是哪一段 | `b walk` | `va`、返回的 PTE 指针、低 5 位 |
| 现场怎么存的 | `b usertrap` | `$scause`、`$satp`、`p->trapframe` |
| 系统调用分到哪 | `b syscall` | `p->trapframe->a7` |
| COW 有没有真复制 | `b cowfault` | `$stval`、旧 PTE 的 `W`/COW 位、计数 |
| 事务提交到哪一步 | `b commit` / `b write_head` | `log.lh.n`、第几次写头 |
| 包的所有权在哪 | `b e1000_recv` | `RDT`、`RDH`、当前描述符 `DD` |

**一句收口**：xv6 的价值不是「我实现过」，而是**任何一个 OS 结论，我都能指到一行代码或一次断点**。指不到的，就是背来的。