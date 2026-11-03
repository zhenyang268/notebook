# jos · 分章详细

## 第 1 章 引导与 Boot Loader

**要解决的问题**：机器加电后 CPU 处于 16 位实模式、物理地址 0 处没有内核，内核镜像还躺在磁盘上。这一章负责把控制权从 BIOS 手里接管过来，把内核 ELF 载入内存并跳进 C 代码。不解决它，后面所有章节的代码都跑不起来。

**机制**：JOS 的启动是一条三级链条，每一级的运行环境都不同，关键在于理解「为什么必须分成三级」。

第一级是 `boot/boot.S`，被 BIOS 从磁盘第一个扇区（512 字节，末尾必须是魔数 `0xAA55`）加载到物理地址 `0x7c00`，此时 CPU 在实模式，只能寻址 1MB，段寄存器语义是 `segment << 4 + offset`。它做三件事：

1. 关中断 `cli`、清方向标志 `cld`，保证串口输出和后续 rep 指令行为确定；
2. 打开 A20 地址线，否则第 21 位地址被强制为 0，无法访问 1MB 以上；
3. 建一张最小的 GDT，把 `%cs` 从实模式代码段切成 `0x08`（内核代码段），`ljmp` 到 32 位代码；再把数据段寄存器都设为 `0x10`，设好 `%esp`（`bootstack`）后 `call bootmain`。

第二级是 `boot/main.c:bootmain()`，此时已在 32 位保护模式，可以用 C 写。它把磁盘当 ELF 读：先读第一页（512 字节）到 `0x10000`，检查 ELF 头魔数 `0x464c457f`，再从 ELF program header 表里取出每个 `PT_LOAD` 段，用 `readseg`（本质是对磁盘端口 `0x1F0`–`0x1F7` 做 `insl`）把各段搬到 `p_paddr`。最后取 ELF header 里的 `e_entry`，强转函数指针跳过去。

第三级是内核的 `entry.S`，`_start` 处先设好 `%esp` 指向 `entrystack`，然后 `call i386_init`。这一级存在的原因是内核入口不能假设 boot loader 留下的栈还在——boot loader 只是「借」了内存，内核需要自己掌控栈。

关键数据结构是 ELF 头与 program header（`struct Elf`、`struct Proghdr`，定义在 `inc/elf.h`），boot loader 只关心 `PT_LOAD` 段和 `e_entry`，不需要符号表、不需要 `PT_DYNAMIC`。

```c
// boot/main.c 的核心循环（简化）
for (i = 0; i < ph->p_filesz; i += SECTSIZE) {
    readseg((uint32_t)ELFHDR, SECTSIZE, 0);        // 先读 ELF 头
    ph = (struct Proghdr *)((uint8_t *)ELFHDR + elf->e_phoff);
    for (; ph < ph_end; ph++)
        if (ph->p_type == ELF_PROG_LOAD) {
            readseg(ph->p_paddr, ph->p_memsz, ph->p_offset);
            // 注意 p_memsz > p_filesz 的部分（.bss）要清零
        }
    ((void (*)(void))elf->e_entry)();
}
```

容易踩的坑：`readseg` 一次读的扇区数超过 128 会导致 BIOS 的 `int 13h` 扩展读失败，所以实现里要分段读；`p_memsz > p_filesz` 的尾部（BSS）必须显式清零，否则内核里未初始化的全局变量是垃圾值。

**最小例子**：一次实际启动。BIOS 把第一个扇区读到 `0x7c00`，`boot.S` 执行到 `ljmp $PROT_MODE_CSEG, $protcseg` 时 CR0 的 `PE` 位已置 1，`%cs` 变为 `0x08`，基址 0、限长 4GB。`bootmain` 读入 ELF 头，发现第一个 `PT_LOAD` 段 `p_paddr = 0x100000`（1MB 处，因为 0–640KB 属于低内存、640KB–1MB 被 BIOS/VGA 占用），把内核代码搬过去。`e_entry` 通常是 `0x10000c`，跳转后 `entry.S` 的 `_start` 设 `%esp` 到 `entrystack` 顶端，`call i386_init`，后者在控制台打印 `6828 decimal is XXX octal!` 那句经典内核横幅——看到这行输出就说明三级链条全部打通。

**面试高频问法**：

1. **「BIOS 把 boot sector 放在 `0x7c00`，这个地址怎么来的？」** 考点是引导链的历史约束。答法：`0x7c00` 是 IBM PC 时代的约定，要避开低端中断向量表和 BIOS 数据区，同时保证加载的 512 字节加上栈空间不超过 640KB 低内存上限，JOS 沿用该约定，`boot.S` 里用 `.org` 保证大小恰好符合。

2. **「为什么要先开 A20？」** 考点是实模式地址回绕。答法：不开 A20 时第 21 位地址被硬件清零，访问 1MB 以上会回绕到低地址；内核要加载到 `0x100000`，不打开 A20 就等于把内核搬到别处，机器必然先崩。

3. **「为什么 boot loader 用 `p_paddr` 而不是虚拟地址？」** 考点是分页尚未开启。答法：boot loader 阶段 `CR0.PG = 0`，所有地址就是物理地址，所以直接按 ELF 的物理地址装载；虚拟地址映射是内核在 `entry.S` 之后调 `mem_init` 才建立的。

4. **「内核为什么需要自己的入口 `entry.S`，不能直接从 `bootmain` 调 `i386_init`？」** 考点是栈与运行环境的移交。答法：`bootmain` 用的是临时栈，且它自己还躺在低内存里；内核需要一个新的、可控的栈顶 `entrystack`，并确保后续 C 代码不依赖 boot loader 遗留的任何状态。

5. **「如果 ELF 的 `p_memsz` 大于 `p_filesz` 会怎样？」** 考点是 BSS 语义。答法：多出的是未初始化数据段，文件里没有内容，loader 必须清零，否则内核全局变量初值是随机垃圾，属于典型难查的启动 bug。

---

## 第 2 章 物理内存分配与页表

**要解决的问题**：内核跑起来之后要能回答两个问题——「还有哪些物理页可用」「虚拟地址 X 对应哪个物理页」。前者决定能不能给进程分配内存，后者决定 CPU 开了分页之后能不能正确访存。不解决它，任何 `malloc`、任何用户进程的地址空间都无从谈起。

**机制**：JOS 把这两件事拆成两层。

**第一层：物理页分配器（`kern/pmap.c`）**。启动时 `i386_init` 调 `mem_init()`，先用 `nvram`/BIOS 提供的信息或 `i386_detect_memory` 得到物理内存总量，把内核 `[KERNBASE, KERNBASE + ...]` 之外的空闲物理页用一个链表串起来：

```c
struct PageInfo {
    struct PageInfo *pp_link;   // 空闲链表指针
    uint16_t pp_ref;            // 引用计数，0 且 pp_link != NULL 才算空闲
};
static struct PageInfo *page_free_list;
```

`page_alloc(&pp)` 从头摘一个，`page_free(pp)` 挂回去。关键设计是**引用计数**而不是布尔占用位：一个物理页可能被多个虚拟地址映射（共享内存、fork 的 COW），只有 `pp_ref` 归零才真正可回收。`page_insert` 增加引用，`page_remove` 减少引用，`page_decref` 封装了「减到 0 就 free」。

**第二层：两级页表**。x86 的 32 位分页用 4KB 页 + 两级页表：虚拟地址 `[31:22]` 是页目录索引、`[21:12]` 是页表索引、`[11:0]` 是页内偏移。JOS 的 `pde_t` 指向页表物理帧，对应数据结构是 `pgdir_walk(pde_t *pgdir, const void *va, int create)`：查 PDE，不存在且 `create` 为真就 `page_alloc` 一张页表、清零、填进 PDE 并加引用；再查 PTE，返回 PTE 指针。所有页表操作围绕 `pgdir_walk` 展开：

```c
pte_t *pgdir_walk(pde_t *pgdir, const void *va, int create) {
    pde_t *pde = &pgdir[PDX(va)];
    if (!(*pde & PTE_P)) {
        if (!create) return NULL;
        struct PageInfo *pp = page_alloc(0);
        if (!pp) return NULL;
        page_insert(pgdir, pp, 0, PTE_P|PTE_W|PTE_U); // 或用 KADDR 填 pde
        pp->pp_ref++;
    }
    pte_t *pt = (pte_t *)KADDR(PTE_ADDR(*pde));
    return &pt[PTX(va)];
}
```

`KADDR(pa)`/`PADDR(va)` 这对宏是整章的核心技巧：JOS 把物理内存 `[0, 物理内存上限)` 线性映射到内核虚拟地址 `[KERNBASE, KERNBASE + 上限)`，于是内核可以「直接」访问任意物理页。`PADDR` 把内核虚拟地址减 `KERNBASE` 得到物理地址，`KADDR` 反向加。这样 `page_alloc` 返回的 `struct PageInfo*` 和它描述的物理页内容都能被内核直接读写。

`boot_map_region` 用来把一段虚拟地址映射到指定物理地址，`mem_init` 用它建立内核的恒等映射（虚拟 `KERNBASE+x` → 物理 `x`）。

**最小例子**：`mem_init()` 中调用 `boot_map_region(kern_pgdir, UPAGES, PTSIZE, PADDR(pages), PTE_U)`，把存 `PageInfo` 数组的那片物理内存映射到虚拟地址 `UPAGES`（`0xef000000`），并带上 `PTE_U`，这样用户态也能读到页面元数据（JOS 用它做 `sys_page_alloc` 检查）。传入 `kern_pgdir`、虚拟地址 `UPAGES`、大小 `PTSIZE`（4MB）、物理地址 `PADDR(pages)`，最终在页表里写入 1024 个 PTE，每个指向一页，全部带 `PTE_P|PTE_W|PTE_U`。之后任意进程访问 `0xef000000` 都能拿到第一页 `PageInfo`。

**面试高频问法**：

1. **「为什么用引用计数而不是简单的占用标志？」** 考点是共享与回收语义。答法：一个物理页可以被多个页表映射，比如 fork 时父子共享只读页、共享内存；只有所有映射都撤销时才能回收，`pp_ref` 精确表达了「还有几个人指着这一页」。

2. **「`pgdir_walk` 的 `create` 参数为什么必须存在？」** 考点是查询与创建的区分。答法：`page_lookup`、`page_remove` 只想要查询，缺页时不该偷偷分配页表；`page_insert` 才需要创建。用同一个函数加参数，避免两份几乎相同的遍历代码。

3. **「`KADDR` 和 `PADDR` 为什么能这么简单？」** 考点是内核线性映射的前提。答法：`mem_init` 建立了 `[KERNBASE, KERNBASE + 物理内存上限)` 到物理内存 `[0, 上限)` 的恒等映射，且内核虚拟地址空间里没有别的映射与它重叠，所以两者就是个常数偏移 `KERNBASE`；这也意味着内核不能访问超过 `KERNBASE` 以上线性映射窗口的物理内存，超出的部分要按实现另行处理。

4. **「页表项里的 `PTE_U` 是谁在用？」** 考点是特权级与地址空间隔离。答法：CPU 在 CPL=3 时只允许访问 `PTE_U` 置位的页，内核映射时不带 `PTE_U`，用户就摸不到内核；`UPAGES` 那片特意带 `PTE_U` 是为了让用户态能读页面元数据。

5. **「`pp_ref` 归零和 `pp_link` 非空这两个条件为什么要同时判断？」** 考点是空闲链表的正确性。答法：`pp_ref == 0` 只说明「没人用」，但那一页可能已经在空闲链表上（`pp_link != NULL`），重复 `page_free` 会造成链表成环；两个条件一起判才是「可回收且未在链上」。

---

## 第 3 章 用户环境与异常处理

**要解决的问题**：内核不能永远只跑自己。它需要一种「受控地进入用户代码、并在出问题时安全退回内核」的机制——用户态不能直接调内核函数，出错（缺页、除零、系统调用）时 CPU 要能把控制权交回内核并保留现场。这一章就是 JOS 的进程抽象 `Env` 加异常/中断的分发骨架，后面的系统调用、fork、调度全建在它上面。

**机制**：三个部分。

**一、`struct Env`（`inc/env.h`）**。JOS 的「进程」叫 environment，核心字段：`env_tf`（`struct Trapframe`，保存陷入时的寄存器现场，包括通用寄存器、`%eip`、`%cs`、`%eflags`、`%esp`、`%ss`）、`env_pgdir`（该环境的页目录，实现地址空间隔离）、`env_status`（`ENV_FREE`/`ENV_RUNNABLE`/`ENV_RUNNING`/`ENV_NOT_RUNNABLE`）、`env_id`（唯一 ID，`env_alloc` 里用递增计数器或 `env_free_list` 生成）、`env_parent_id`、`env_runs`。

`env_alloc` 从 `env_free_list` 摘一个，初始化 `env_tf`（尤其 `tf_cs` 设成用户代码段、`tf_eflags` 置 `FL_IF` 开中断）、把 `env_pgdir` 指向新建的页目录并复制内核映射、`pp_ref` 加一。`env_free` 是逆过程：释放页目录及其所有用户页、把 `Env` 挂回空闲链表。

**二、临界区与 `env_run`**。切换环境要保证 `curenv` 的一致性，JOS 用 `cli`/`sti` 包住临界区（`inc/x86.h` 的 `lock` 宏思路）。`env_run(e)` 把 `curenv` 指向 `e`、`env_status` 置 `ENV_RUNNING`、`env_runs++`，切 `%cr3` 到 `e->env_pgdir` 的物理地址，然后调 `env_pop_tf(&e->env_tf)` 恢复寄存器现场并 `iret` 回到用户态。

**三、中断/异常分发（`trap.c` + `trapentry.S`）**。IDT 在 `trap_init` 里填，每个向量都指向 `trapentry.S` 里生成的一小段桩代码。关键设计是**每个向量一个桩、统一调用 C 的 `trap`**：桩把错误码（有些向量硬件会压）和向量号压栈，再 `pushal` 保存通用寄存器，把 `%esp` 作为参数传给 C 函数（`struct Trapframe *` 就是从这来的），返回时 `popal` + `addl $8, %esp` + `iret`。

```asm
# trapentry.S 里每个向量的桩（用宏生成）
vector\name:
    pushl $0            /* 无错误码的向量补一个 0，统一栈布局 */
    pushl $\name
    jmp _alltraps
_alltraps:
    pushl %ds; pushl %es
    pushal
    movl $GD_KD, %ax; movw %ax, %ds; movw %ax, %es
    pushl %esp          /* Trapframe* 作为参数 */
    call trap
```

`trap(struct Trapframe *tf)` 根据向量号分派：`T_SYSCALL` 交给 `syscall()`，缺页 `T_PGFLT` 交给 `page_fault_handler()`，其余打印信息并销毁环境。**注意 `T_SYSCALL` 访问用户指针前必须调 `user_mem_assert`**：内核和用户共享地址空间，直接解引用用户传的指针等于让用户借内核之手读写任意内存。

**最小例子**：写一个用户进程，让它执行除零。`env_create(0, ENV_TYPE_USER)` 分配环境，`env_run` 后 `iret` 进入用户态，执行 `1/0` 触发向量 0 的处理器——这个向量的错误码由硬件压入，`Trapframe` 里能看到 `tf_trapno == T_DIVIDE`。`trap` 走到 `default: env_destroy(curenv)`，打印寄存器 dump，进程被回收。整个过程用户态没有机会执行任何内核指令，现场完整保存在栈上。

**面试高频问法**：

1. **「为什么每个中断向量都要一个独立的汇编桩，不能共用一个？」** 考点是硬件栈布局差异。答法：有些向量硬件会压错误码、有些不压，还有的压的数值无意义；如果共用一个桩，C 代码看到的栈布局就不统一，`Trapframe` 直接错位。所以每个向量配一个桩，不压错误码的补 `pushl $0` 占位。

2. **「`env_pop_tf` 为什么要用 `iret` 而不是普通 `ret`？」** 考点是特权级切换。答法：普通 `ret` 只弹 `%eip`，不会恢复 `%cs`/`%eflags`/`%esp`/`%ss`，也没法从 ring 0 切到 ring 3；`iret` 恰好按硬件陷阱帧格式弹出这五个值，是唯一正确的返回用户态方式。

3. **「用户进程能不能读到内核内存？如果用户传了个内核指针给系统调用呢？」** 考点是地址空间隔离与 `user_mem_assert`。答法：内核映射不带 `PTE_U`，用户态直接访存会被 CPU 拒绝；但在系统调用里是内核态在跑，`PTE_U` 不再生效，所以必须用 `user_mem_assert` 逐页检查 `va` 落在用户可访问范围且 `PTE_U` 置位，否则用户能借内核读写任意地址。

4. **「`env_pgdir` 里为什么要复制内核映射？」** 考点是陷入内核时不切页表。答法：JOS 采用「内核与用户共享地址空间」模型，进入内核时 `%cr3` 不变，所以每个用户页目录的上半部分必须包含和 `kern_pgdir` 一致的内核映射；否则一旦 `int`/`syscall` 进内核，`%eip` 指向的代码立刻不可访问。

5. **「`env_run` 的 `env_runs` 和 `env_status` 什么时候被改？」** 考点是状态机正确性。答法：`env_run` 里把新环境置 `ENV_RUNNING`、旧环境按原因置 `ENV_RUNNABLE`（被抢占）或保持 `ENV_NOT_RUNNABLE`（在等某个事件）；`env_runs` 是调度用的计数，每次真正上 CPU 加一。状态机错一次就会出现「环境永远不跑」或「同一环境被两个 CPU 上跑」的问题。

## 第 4 章 中断、系统调用与陷入内核

**要解决的问题**：用户态的程序想读写文件、发 IPC、拿自己的 env id，都必须进内核；硬件出错（缺页、除零、时钟到期）也必须让内核接管。这一章解决「从用户态或硬件事件切到内核的第一跳」：Trap frame 怎么建、IDT 怎么填、`int $0x30` 和 `iret` 怎么把控制权来回传，以及为什么这条路径上必须不信任用户栈。不解决它，后面所有 syscall（`sys_exit`、`sys_fork`、`sys_ipc_recv`）都没有落点。

**机制**：

三样东西配合：IDT（中断描述符表）、TSS、trap entry 汇编桩。

- **IDT**：内核在 `trap_init()` 里对 0–255 每个向量填一个 gate。CPU 异常（0–31）用 `SETGATE(idt[T_DIVIDE], 0, GD_KT, divide_error, 0)` 这类，DPL=0，用户态不能 `int` 进来；系统调用用 `SETGATE(idt[T_SYSCALL], 1, GD_KT, syscall, 3)`，DPL=3 才允许用户执行 `int $0x30`。JOS 还注册了 `IRQ_OFFSET + IRQ_TIMER` 等硬件中断。
- **TSS**：`ltr(GD_TSS)` 装载，`ts_esp0`/`ts_ss0` 指向内核栈。用户态进中断时 CPU 不会自动换栈——它必须靠 TSS 里的 `ss0:esp0` 找到内核栈，把用户态的 `ss, esp, eflags, cs, eip` 依序压进去，再压 error code（若有）。**只有从低特权级（CPL=3）进高特权级（CPL=0）时才压栈并换栈**；内核态自己的异常只压 `eflags,cs,eip`，不换栈——这点是面试常问的坑。
- **trap entry**：`trapentry.S` 里每个向量一个桩，统一套路是「没有 error code 的压一个 0 → push 向量号 → jmp alltraps」。这样 `alltraps` 看到的栈帧形状永远一致：

```asm
# trapentry.S 片段（示意）
vector64:
    pushl $0          # 无 error code，占位
    pushl $T_SYSCALL
    jmp alltraps
alltraps:
    pushal            # 压 edi,esi,ebp,oesp,ebx,edx,ecx,eax
    movw $(GD_KD), %ax
    movw %ax, %ds
    movw %ax, %es
    pushl %esp        # Trapframe *tf
    call trap
```

`trap()` 收到 `struct Trapframe *tf`，用 `tf->tf_trapno` 分派：`< 32` 走 `trap_dispatch`（缺页、断点等），`== T_SYSCALL` 走 `syscall()`，`>= IRQ_OFFSET` 走 `irq_handler` 再把 EOI 写给 PIC（从机先写）。返回时 `iret` 依序弹出 `eip,cs,eflags`，若特权级变化再弹 `esp,ss`。

系统调用参数约定：eax 传号，edx/ecx/ebx/edi/esi 依次传 1–5 个参数，返回值放 eax。用户侧是 `lib/syscall.c` 的 inline asm，例如 `syscall(SYS_envid)` 就是 `int $0x30`。

**最小例子**：用户调用 `sys_env_destroy(0)`（即 `sys_exit`）。`lib/syscall.c` 把 `SYS_env_destroy` 放 eax、0 放 edx，执行 `int $0x30`。CPU 从 IDT[0x30] 取到 DPL=3 的 gate，经 TSS 换到内核栈，压 5 个字，跳 `vector48` → 压 0 和 0x30 → `alltraps` → `trap(tf)`。`trap()` 判 `tf_trapno == T_SYSCALL`，调 `syscall(tf->tf_regs.reg_eax, ...)`，进 `sys_env_destroy(0)` 走 `env_destroy`，状态转 `ENV_DYING` 并 `env_run` 到调度器。注意：**内核不直接 return 回用户**，而是从 `env_run` 切走，这条 trap 路径的 `iret` 永远不会执行——这就是 `sys_exit` 不需要「返回用户态」的原因。

**面试高频问法**：

1. **「用户态 `int` 进内核，CPU 怎么知道用哪个栈？」** → 考点：TSS 与栈切换条件。→ 答法：特权级从 3 变 0 时 CPU 读 TSS 的 `ss0:esp0` 换栈并压用户 `ss/esp/eflags/cs/eip`；同特权级不换栈。
2. **「为什么每个中断向量都要单独写汇编桩，不能一个桩打天下？」** → 考点：error code 有无不一致。→ 答法：有些异常 CPU 自动压 error code、有些没有，桩不统一栈帧就没法共用 `alltraps`，所以无 error code 的桩先 `pushl $0` 占位。
3. **「为什么 `SETGATE` 对 syscall 要传 dpl=3？」** → 考点：IDT gate 的 DPL 与 CPL 比较。→ 答法：`int n` 是软件中断，CPU 检查 `DPL >= CPL` 才放行；系统调用要用户可触发，必须 DPL=3，异常门保持 0 防止用户伪造缺页。
4. **「trap 返回为什么用 `iret` 而不是 `ret`？」** → 考点：iret 恢复特权级。→ 答法：`iret` 会恢复 `cs:eip` 和 `eflags`，并在 CPL 变化时恢复 `ss:esp`，`ret` 只弹返回地址。
5. **「用户传的指针在内核里能直接用吗？」** → 考点：用户指针校验。→ 答法：不能，必须先 `user_mem_check` 验证落在 `UTOP` 以下且可读/可写，否则内核会被用户指针带到任意地址。

---

## 第 5 章 进程创建与调度

**要解决的问题**：JOS 启动后只有内核，需要一个「用户进程」的抽象和执行环境的容器：env 怎么分配、地址空间怎么建、第一次怎么「跳进用户态」而不从 `iret` 之外的地方进去，以及多个 env 就绪时谁跑。不解决它，第 4 章的 trap 没有接收方，第 6 章的 fork 无从谈起。

**机制**：

**Env 结构**（`inc/env.h`）：`env_id`（全局唯一，不复用）、`env_parent_id`、`env_status`（`ENV_FREE/FREEING/RUNNABLE/RUNNING/NOT_RUNNABLE/DYING`）、`env_tf`（Trapframe，保存「下次进用户态」的全部寄存器）、`env_pgfault_upcall`、`env_runs`、以及 `env_addr` 指向的**每进程页目录**（注意：JOS 的页表是 per-env 的，不是 per-CPU）。

**分配**：`env_alloc(&e, parent_id)` 从 `env_free_list` 弹一个，清空 `env_tf`，调 `env_setup_vm` 建页目录：

```c
// env_setup_vm 核心
e->env_pgdir = page2kva(p);
memcpy(e->env_pgdir, boot_pgdir, PGSIZE);   // 复制内核映射
e->env_pgdir[PDX(UVPT)] = PADDR(e->env_pgdir) | PTE_P | PTE_U;
e->env_cr3 = PADDR(e->env_pgdir);
```

关键点：**复制内核页目录项**，让 `UTOP` 以上的内核映射在每个进程里都可见（但 PTE_U=0，用户碰不到）；`UVPT` 指向自身页目录形成只读的页表映射，用户态 `pgdir_walk` 可以读自己的页表。

**第一次进用户态**：`env_run(e)` 设置 `curenv`、`e->env_runs++`、`lcr3(e->env_cr3)`，然后**从 `env_pop_tf(&e->env_tf)` 开始执行**。`env_pop_tf` 是一段汇编：`movl 0(%esp),%esp`（恢复 Trapframe 里的 esp）→ `popal` → `popl %es` → `popl %ds` → `addl $8,%esp`（跳过 tf_trapno 和 tf_err）→ `iret`。所以创建新进程时必须在 `env_tf` 里**手工填好** `tf_cs = GD_UT | 3`、`tf_eip = 入口地址`、`tf_esp = USTACKTOP`、`tf_eflags = FL_IF`。这就是为什么新进程不是「函数调用进去的」，而是「伪装成一次中断返回」。

**从内核建进程**：内核不能直接 C 调用用户函数，`load_icode` 用 `region_alloc` 在用户地址空间逐段分配并 `memcpy`，然后设 `tf->tf_eip = elf->e_entry`，并**手工压一个假的返回栈**：

```c
// 让用户程序 _start 的 ret 掉到 exit
tf->tf_esp -= 4;
user_mem_check(...); // 或直接校验后写
*((uint32_t *)tf->tf_esp) = 0;   // 返回地址 0
```

`_start` 在 `lib/entry.S` 里是 `pushl $0; pushl $0; call libmain`，即 `main` 返回后回落到 0，触发 page fault，进而 `sys_exit`。

**调度**：`sched_yield()` 从 `curenv+1`（或列表头）环形扫描 `env_free_list -> env_list` 链表，跳过 `RUNNABLE` 以外的，找到第一个 `RUNNABLE` 就 `env_run`；没有则 `env_run(curenv)` 原地重跑，`curenv==NULL` 时从头。

**最小例子**：加载 binary `icode`。`env_create(icode, ENV_TYPE_USER)` → `env_alloc`（拿到 `env 0x1000` 号）→ `env_setup_vm`（复制内核页目录，UVPT 自指）→ `load_icode`（`e_entry=0x800020` 映入代码段）→ `tf_eip=0x800020`、`tf_esp=0xeebff000`（`USTACKTOP` 之上预留）、`tf_cs` 带 RPL 3 → `env_run` → `lcr3` → `env_pop_tf` → `iret` 到 `0x800020`。用户首次执行 `_start`，栈上已有假的返回地址 0，`libmain` → `umain` 跑起来。

**面试高频问法**：

1. **「新进程第一次怎么进用户态，为什么不能直接调用？」** → 考点：`env_pop_tf` 与伪造 Trapframe。→ 答法：靠 `env_pop_tf` 执行 `popal + iret`，所以创建时要把 `eip/esp/cs/eflags` 填进 `env_tf`，`iret` 就是「从内核切回用户」的唯一入口。
2. **「JOS 的调度器是什么算法？够用吗？」** → 考点：轮转与就绪队列。→ 答法：环形轮转，`env_run` 里从不主动保存，靠 trap 进内核时 `env_tf` 已被 `alltraps` 压好；没有优先级也无时间片语义，时钟中断只提供抢占点。
3. **「`env_setup_vm` 为什么要 `memcpy` 内核页目录项，直接共享一个页目录不行？」** → 考点：per-env 页表与地址空间隔离。→ 答法：用户映射必须各自独立（`UPAGES`、`USTACKTOP`、`UVPT` 都不同），内核映射复制一份是廉价做法，`UTOP` 以上 PTE_U=0 所以安全。
4. **「进程退出后 `env_free_list` 怎么回收？」** → 考点：`env_free` 与引用计数。→ 答法：`env_free` 释放页目录和物理页，`env_id` 不复用（靠 `env_id` 递增），这正是第 6 章 COW 必须能区分「谁是最后一个引用者」的原因。
5. **「为什么 `env_tf` 里 `eflags` 要设 `FL_IF`？」** → 考点：中断使能。→ 答法：新进程在用户态必须能接收时钟中断，否则永远不产生抢占；`iret` 会把它写回 `eflags`。

---

## 第 6 章 fork 与写时复制

**要解决的问题**：`fork` 要让子进程拿到和父进程一模一样的地址空间，但如果每个页都真的复制，代价是 O(内存)——`sh` 里 fork 一个只 exec 的进程尤其冤。这一章解决「怎么让两个 env 在写之前共享同一批物理页、谁负责在第一次写时偷偷复制」。

**机制**：

三部分：`PTE_COW` 标记、`fork` 时只复制映射、缺页处理器里做实际复制。

**`fork`（`sys_exofork`）**：`env_alloc(&e, curenv->env_id)` 建子 env，然后**把父的 `env_tf` 整个拷给子**，`e->env_status = ENV_NOT_RUNNABLE`，返回 `e->env_id` 给父、0 给子（靠「子进程从 `env_pop_tf` 返回时 eax 里是 0」实现）。然后 `duppage` 遍历 `[0, USTACKTOP)` 的每一页：

```c
// duppage 对每个可写页
if (perm & PTE_W) {
    pte = pte | PTE_COW;
    perm = (perm | PTE_COW) & ~PTE_W;   // 父子两侧都去掉 W、加上 COW
    sys_page_map(0, addr, envid, addr, perm);
} else {
    sys_page_map(0, addr, envid, addr, perm);  // 只读页直接共享
}
```

关键：**父进程自己的 PTE 也要改**，否则父写的时候直接写穿，子进程看到不该看的内容。所以 `duppage` 先 `sys_page_map` 把映射装进子页表，再 `sys_page_map(0, addr, 0, addr, newperm)` 改自己（或者用 `page_insert` 重设）。

**缺页处理**：写一个 COW 页触发 `T_PFAULT`，`trap_dispatch` 调 `page_fault_handler`，判断 `(tf->tf_err & FEC_WR)` 且 PTE 带 `PTE_COW`：

```c
// 伪代码
if ((err & FEC_WR) && (pte & PTE_COW)) {
    pa = PTE_ADDR(pte);
    if (page_refcount[pa] == 1) {        // 最后一个引用者：直接翻回可写
        page_insert(pgdir, pa, va, pte|PTE_W & ~PTE_COW);
    } else {
        newpa = page_alloc(ALLOC_ZERO);
        memcpy(page2kva(newpa), page2kva(pa), PGSIZE);
        page_decref(pa);
        page_insert(pgdir, newpa, va, pte | PTE_W & ~PTE_COW);
    }
}
```

**引用计数**是这一章的暗线：`page_alloc` 初始化 `pp_ref=1`，`page_insert` 每次映射 `pp_ref++`，`page_remove`/`page_decref` 减到 0 才真正 `page_free`。没有它就无法知道「还剩几个 env 在共享这页」——只用 COW 位而不用 refcount，会在父子都写时提前释放或永远不释放。

用户态缺页回调：`sys_env_set_pgfault_upcall` 让 env 在用户态自己处理缺页，trap 时把 `tf` 复制到 **异常栈** `UXSTACKTOP`，改 `tf_eip` 指向 upcall，用 `iret` 回到用户态执行 handler——这是「缺页不一定要内核处理」的伏笔。

**最小例子**：父 env 0x1000 在 `0x802000` 有一页可写、内容 `"hi"`。`fork` 后子 env 0x1001 的页表也映射到同一物理页 `pa`，双方 PTE 都是 `COW|U`（无 W）。父写 `0x802000`：`page_fault_handler` 见 `FEC_WR` + `PTE_COW`，`pp_ref==2`，`page_alloc` 出新页、`memcpy`、`page_decref(pa)`（变 1）、`page_insert(newpa, PTE_W)`。子进程读 `0x802000` 仍是 `"hi"`，写时再复制一次。**没写过的页始终只有一份**。

**面试高频问法**：

1. **「COW 的『时』到底在哪一刻？fork 时做了什么、没做什么？」** → 考点：映射复制 vs 内容复制。→ 答法：fork 只复制页表项（`sys_page_map` 同一物理页，去 W 加 COW），不复制内容；第一次写触发 page fault 才 `page_alloc + memcpy`。
2. **「为什么 `duppage` 必须同时改父进程的 PTE？」** → 考点：双向标记的原子性。→ 答法：只改子进程的话，父进程仍持有可写 PTE，写时会绕过缺页直接改共享页，子进程就看到了不属于它的修改。
3. **「没有引用计数，只靠 COW 位能行吗？」** → 考点：`pp_ref` 与释放时机。→ 答法：不行。`page_free` 需要知道最后一个引用者；`pp_ref==1` 时还能省掉一次 `memcpy` 直接把页翻回可写。
4. **「父子同时写同一页会怎样？」** → 考点：缺页处理的幂等性。→ 答法：先写的一方 `pp_ref>1` 走复制、`page_decref` 降 ref；后写的一方看到自己 PTE 仍带 COW（原生页已被别人 `decref`），此时若 ref 已为 1 直接改权限，否则再复制一次。每次缺页只操作「当前 env 的 PTE」。
5. **「COW 页在 `page_insert` 时权限怎么算？」** → 考点：PTE 位组合。→ 答法：必须同时清 `PTE_W`、置 `PTE_COW`，并保留 `PTE_P|PTE_U`；漏掉 U 位用户态会直接 fault，漏掉 COW 位缺页处理器认不出来。

## 第 7 章 并发与自旋锁

**要解决的问题**：Lab 1–3 的内核隐含一个假设——任意时刻只有一个执行流在读写内核全局数据。Lab 4 要打开多处理器（`boot_aps` 启动 AP）并支持抢占式调度，于是两个 CPU 可能同时修改 `envs[]`、空闲页链表、`struct cpu` 里的 `curenv`。不引入锁，多核一开机就会随机改坏数据结构；同时也就解释不了为什么 `env_run` 在跳回用户态之前必须放锁。

**机制**：

JOS 的并发模型是“单一内核大锁 + 局部自旋锁”，单核与多核走同一套代码。

- 锁的数据结构：`struct spinlock { uint32_t locked; const char *name; struct cpu *cpu; }`。`locked` 非 0 表示已被持有。`spinlock_init` 把它清零。
- 原子性靠 `xchg`：带 `lock` 前缀的原子读改写，一次完成“读出旧值、写入 1、返回旧值”。返回 0 表示抢锁成功。没有它，`if (lk->locked == 0) lk->locked = 1;` 在两条流水线之间就能同时成立。
- 内存序靠 `__sync_synchronize()`。抢到锁后、释放前各插一次屏障，防止编译器或 CPU 把临界区内的访存重排到锁外——否则锁保护的是“代码位置”而不是“访存顺序”。
- 每个 CPU 有一份 `struct cpu`，`cpunum()` 通过 `%gs` 段基址读本 CPU 的 LAPIC id 来索引。凡是“当前 CPU 的状态”（`curenv`、时钟计数、`ts`）都必须从全局变量搬进 per-CPU 结构，否则加锁也救不了数据竞争。
- 全局大锁 `kernel_lock`：CPU0 在 `i386_init` 里先拿住，再 `boot_aps()`；每个 AP 在 `mp_main` 里初始化 LAPIC、段寄存器、IDT 之后立刻 `lock_kernel()` 并自旋，直到 CPU0 调度进第一个用户进程、在 `env_run` 的 `lcr3` 之后 `unlock_kernel()`。结果是：内核态同一时刻只有一个 CPU 在跑，用户态可以真正并行。
- 使用约束：临界区短、不睡眠、不阻塞、不触发调度；持有大锁时进用户态会造成“用户进程被抢占、其他 CPU 永远等锁”的死锁。

```c
/* kern/spinlock.c，DEBUG 版本另有持有者断言 */
void spin_lock(struct spinlock *lk) {
    if (holding(lk)) panic("spin_lock: already held");
    while (xchg(&lk->locked, 1) != 0)
        ;                    /* 自旋等别人放 */
    __sync_synchronize();    /* 临界区访存不得上浮 */
    lk->cpu = cpunum();      /* 记持有者，供 holding() 用 */
}

void spin_unlock(struct spinlock *lk) {
    __sync_synchronize();    /* 临界区访存不得下沉 */
    lk->cpu = NULL;
    xchg(&lk->locked, 0);    /* 原子释放 */
}

/* kern/sched.c: env_run 的收尾 */
lcr3(PADDR(e->env_pgdir));
unlock_kernel();             /* 进用户态前必须放掉大锁 */
env_pop_tf(&e->env_tf);      /* 此后不再碰内核共享数据 */
```

**最小例子**：双 CPU 启动时序。CPU0 执行 `i386_init`：`lock_kernel()` → `boot_aps()` → 把 `mpentry` 拷到 `MPENTRY_PADDR`，逐个 `lapic_startap(apicid, MPENTRY_PADDR)`。AP0 从实模式进入 `mp_main`，初始化完毕后在 `lock_kernel()` 上自旋。CPU0 继续做完 `env_init`、`trap_init_percpu`，然后 `sched_yield()` 选中第一个 `RUNNABLE` 用户环境，进入 `env_run`，`lcr3` 切换页表后 `unlock_kernel()`，AP0 的 `xchg` 返回 0 拿到锁，进入自己的 `sched_yield`。之后每当一个 CPU 要进内核，都在 `kernel_lock` 上排队，用户态两端并发执行。

**面试高频问法**：

1. 问：单核加锁有意义吗？→ 考点：SMP 与抢占、关中断的区别。→ 答法：锁解决的是 CPU 之间的并发，`cli` 只关本 CPU 的中断；单核上保护临界区主要靠关中断或不可抢占，但这份代码要在 SMP 上跑，所以统一用 `xchg` 锁，成本只有一条原子指令。
2. 问：`xchg` 为什么够，还需要内存屏障吗？→ 考点：原子性不等于顺序性。→ 答法：`xchg` 只保证“只有一个 CPU 读到 0”，但临界区里的 load/store 可能被重排到加锁前或解锁后，所以两侧要 `__sync_synchronize()` 把顺序钉死。
3. 问：为什么 `env_pop_tf` 之前一定要 `unlock_kernel`？→ 考点：锁的生命周期与调度。→ 答法：用户态不访问内核共享结构，不需要持锁；若持锁进用户态，该进程被抢占后别的 CPU 会永远自旋，整机死锁。
4. 问：持锁时能 `sched_yield` 或睡眠吗？→ 考点：自旋锁不是睡眠锁。→ 答法：不能，自旋锁要求持有者一定在跑；持锁阻塞会让等待方永远烧 CPU，还可能形成锁序环，所以临界区内只做内存操作与短循环。
5. 问：per-CPU 变量和锁是什么关系？→ 考点：消除共享 vs 保护共享。→ 答法：per-CPU 是把“共享”改成“私有”，从根本上消除竞争；锁只能用在必须共享的数据上，两者常一起用——`cpu` 数组本身由大锁保护，`curenv` 则私有到每个 CPU。

## 第 8 章 文件系统

**要解决的问题**：用户进程需要持久化、有名字、可增长的文件，shell 和管道也要挂在文件抽象上。JOS 的做法不是把文件系统塞进内核，而是把它做成一个独立的用户态进程（FS 进程），其他进程通过 IPC 请求它。不解决这一层，用户态就没有 `open/read/write/close`，Lab 5 之后的 shell 无法重定向，也演示不了“故障隔离 + 日志保证崩溃一致性”。

**机制**：

- 磁盘布局（`fs/fs.h`，块大小 4096）：块 0 引导块，块 1 superblock（magic、磁盘块数、根 inode 号等），块 2 位图，记录哪些块已分配；其后是 inode 区与数据区，具体块编号的分配按实现而定。
- inode 用 `struct File` 表示：文件名、大小、类型，`f_direct[10]` 十个直接块指针，外加一个 `f_indirect` 单级间接块，间接块里放 1024 个 4 字节块号。所以单文件最大约 $10 + 1024$ 个块，约 4 MB——教学系统用单级间接把多级寻址代码省掉。
- 客户端/服务端接口：请求类型 `FSREQ_OPEN`、`FSREQ_MAP`、`FSREQ_SET_SIZE`、`FSREQ_CLOSE`、`FSREQ_STAT`、`FSREQ_UNLINK`、`FSREQ_FLUSH`。客户端 `lib/file.c` 把请求打包成 `struct Fsreq_*`，用 `ipc_send`/`ipc_recv` 发到 FS 进程；FS 进程在 `serve_open` 等处理函数里改内存中的块缓存，再回结果。`open` 返回的 `struct Fd`（`fd_dev_id`、`fd_offset`、`fd_omode`）交给用户侧；`FSREQ_MAP` 则让客户端把文件的某一页映射进自己的地址空间，之后直接读内存。
- 为什么放用户态：文件系统逻辑与块缓存都在 FS 进程里，崩了不会拖垮内核；代价是每次操作两次调度加一次 IPC。生产里的对应形态是 FUSE——同一取舍，同一代价。

**最小例子**：`file_read(fd, buf, n)` 展开成三步：先 `fsipc(FSREQ_MAP, ...)` 让 FS 把目标页映射到临时地址，再 `memmove` 到用户缓冲，最后更新 `fd_offset`。对比内核内路径（xv6：一次 `read` → `readi` → `bread`），**JOS 多付两次上下文切换，换来崩溃隔离与"文件系统不进内核"**。

> 设备层细节（ATA PIO 端口与状态位、块缓存的哈希 + LRU + 引用计数、磁盘布局与单级间接的容量上限）在 `../drivers/` 第 2–4 章。

**面试高频问法**：

1. **「为什么把文件系统放在用户态？」** → 考点：故障域与路径长度。答法：崩溃隔离（FS 崩了内核还在）、实现自由（用户态用普通指针与内存分配）；代价是每次操作两次调度加一次 IPC，以及客户端必须处理"服务端繁忙/超时"。
2. **「`FSREQ_MAP` 为什么比 `FSREQ_READ` 更重要？」** → 考点：零拷贝。答法：`READ` 是把数据拷进一个固定大小的载荷；`MAP` 是把文件页直接映射到客户端地址空间，大文件读取与 `spawn` 加载 ELF 都靠它，避免逐字节拷贝。
3. **「用户态文件服务在真实系统里怎么落地？」** → 考点：FUSE。答法：Linux 的 FUSE 就是内核转发请求、用户态守护进程处理；代价同样是延迟（每次操作多次切换），收益是隔离与开发效率。

## 第 9 章 IPC 与管道

**要解决的问题**：JOS 的每个 Env 有独立页表，一个 Env 看不到另一个 Env 的地址空间。文件系统 lab 里的 file server 要响应其他 Env 的请求，shell 要支持 `|`，都必须有受控的跨 Env 传值/传页机制。没有 IPC，就只能让内核开全局缓冲区，或者让双方裸共享页，缺少“谁在等、等到没有、失败怎么重试”的语义。

**机制**：JOS 的 IPC 是一对同步 rendezvous 原语，不是内核消息队列。

- `sys_ipc_try_send(envid, value, srcva, perm)`：非阻塞。检查目标 Env 的 `env_ipc_recving`；没在收就返回 `-E_IPC_NOT_RECV`。在收则可选地把 `srcva` 指向的物理页映射到接收方事先登记的 `env_ipc_dstva`，把 `value/from/perm` 写进目标 `struct Env`，清 `env_ipc_recving`，把目标置 `ENV_RUNNABLE`。
- `sys_ipc_recv(dstva)`：阻塞。登记 `env_ipc_recving=1`、`env_ipc_dstva=dstva`，把自己置 `ENV_NOT_RUNNABLE`，再 `sys_yield()`。被发送方唤醒后，从 `thisenv` 的 `env_ipc_value/from/perm` 取结果。
- lib 层 `ipc_send` 在 `-E_IPC_NOT_RECV` 时循环 `sys_yield()` 重试；`ipc_recv` 封装 `sys_ipc_recv` 并回填 from/perm。

关键点是“先登记再睡眠”的顺序：如果先睡眠后登记，发送方可能看到 `recving=0` 而放弃；如果登记后不关中断/不原子地切换，又可能丢失唤醒。JOS 用“置标志 → 置不可运行 → yield”保证发送方要么看见未接收，要么能唤醒接收方。

```c
// 伪代码：kern/syscall.c
int sys_ipc_try_send(envid_t envid, uint32_t value, void *srcva, int perm) {
    struct Env *e;
    if (envid2env(envid, &e, 0) < 0) return -E_BAD_ENV;
    if (!e->env_ipc_recving) return -E_IPC_NOT_RECV;
    if (srcva < (void *)UTOP) {
        struct PageInfo *pg = page_lookup(curenv->env_pgdir, srcva, &pte);
        if (!pg) return -E_INVAL;
        if ((perm & PTE_W) && !(*pte & PTE_W)) return -E_INVAL;
        if (page_insert(e->env_pgdir, pg, e->env_ipc_dstva, perm) < 0)
            return -E_NO_MEM;
    }
    e->env_ipc_recving = 0;
    e->env_ipc_from = curenv->env_id;
    e->env_ipc_value = value;
    e->env_ipc_perm = perm;
    e->env_status = ENV_RUNNABLE;
    return 0;
}
```

管道不是 JOS 的内核系统调用。JOS 只给到“一条消息 + 可选一页”的 IPC，pipe 要在其上自己搭：在内核或 file server 里放一个有界环形缓冲，读空/写满时让调用者睡眠，close 时唤醒对端。xv6 则把 pipe 直接做成文件类型：`struct pipe` 里有 `char data[PIPESIZE]`、`nread/nwrite`、读写端打开计数，`pipewrite` 满时 `sleep`，`piperead` 空时 `sleep`，`pipeclose` 唤醒等待者。这是“消息语义”和“字节流语义”的分层差异。

**最小例子**：Env A 执行 `ipc_send(B, 42, NULL, 0)`，此时 B 还没 `ipc_recv`，`sys_ipc_try_send` 返回 `-E_IPC_NOT_RECV`，A 在 `ipc_send` 里 `sys_yield` 重试。B 随后 `ipc_recv(&from, NULL, NULL)`，登记 `recving=1` 后睡眠。A 下一次重试成功：B 被置 `ENV_RUNNABLE`，醒来返回 `42`，`from` 为 A 的 envid。带页版本：A 把 `srcva` 处一页以 `perm=PTE_W|PTE_U` 映射到 B 的 `dstva`，B 醒来即可读写该页；若 A 请求写但源页只读，返回 `-E_INVAL`，B 仍保持等待状态。

**面试高频问法**：

- 问：JOS IPC 为什么设计成 try_send + 阻塞 recv，而不是内核里放消息队列？→ 考点：同步 rendezvous 与异步队列的取舍。→ 答：省掉内核缓冲区和消息生命周期管理，接收方睡眠、发送方重试，语义简单；代价是发送方要主动让出，吞吐不如队列。
- 问：`sys_ipc_recv` 为什么先置 `ENV_NOT_RUNNABLE` 再 `yield`？→ 考点：阻塞的原子性与丢失唤醒。→ 答：保证发送方看到的要么是“还没登记接收”，要么是“已登记且可被唤醒”，不会出现登记后、睡眠前被抢占导致唤醒丢失。
- 问：IPC 传页时权限检查查什么？→ 考点：PTE_W/PTE_U、`page_insert` 失败路径。→ 答：源页必须存在，请求写则源页必须可写，目标地址必须用户可写且未映射；失败返回 `E_INVAL/E_NO_MEM`，不改接收方状态。
- 问：pipe 和 IPC 的本质区别？→ 考点：消息 vs 字节流。→ 答：IPC 一次一条消息、无内核缓冲、收发双方直接会合；pipe 是有界字节流，读空写满都睡眠，生命周期由 fd 引用计数管。
- 问：在 JOS 上实现 pipe 要补什么？→ 考点：环形缓冲 + 等待队列。→ 答：共享页放 ring buffer，读写端用 IPC 传 offset/长度，空/满时阻塞，close 时唤醒对端并处理 EOF。

## 第 10 章 JOS 与 xv6 / Linux 的对照

**要解决的问题**：面试不会只问“JOS 里 `sys_ipc_try_send` 怎么实现”，而是问“同样的问题，xv6 和 Linux 为什么选另一条路”。这一章把 JOS 放回操作系统谱系，用几个维度把设计取舍说清楚，避免背完 lab 却答不出对比。

> 深度版在 `../kernel-compare/`：那份额外讲清"CPU 架构给了什么材料 → 内核形状 → API 形状"的因果链，以及三者的系统调用 API 对照表。本章只保留最短的对照骨架。

**机制**：按维度对照。

地址空间：JOS 每个 Env 一个 `env_pgdir`，用户区到 `UTOP` 为止，内核在 `UPAGES/UVPT` 等固定位置有映射；xv6 内核在 `KERNBASE` 直接映射，用户进程有独立页表但内核页共享；Linux 用 `mm_struct` 加 VMA 红黑树管理用户地址空间，缺页时按 VMA 决定匿名页、文件页或 COW。JOS 的页表操作是教学级“显式 `page_insert/page_remove`”，Linux 是“缺页异常驱动”。

进程与上下文：JOS 的 Env 不区分进程线程，`env_run` 保存/恢复 `Trapframe`；xv6 的 `struct proc` 有独立内核栈和 `trapframe`，`swtch` 切换内核上下文；Linux 的 `task_struct` 加 `thread_info`，用户态/内核态栈分离，调度器只切内核上下文。

系统调用入口：JOS 用 `int $0x30` 进 `T_SYSCALL`，从 `Trapframe` 取 `eax` 等寄存器分发；xv6 用 `int $64`，`usys.S` 把系统调用号放进 `%eax`；Linux x86-64 用 `syscall` 指令进 `entry_SYSCALL_64`，再查 `sys_call_table`。

调度与并发：JOS 早期是协作式，时钟中断后轮转，临界区常用关中断/自旋；xv6 有 `scheduler()` 轮转、`sleep/wakeup` 睡眠唤醒、`spinlock` 与 `sleeplock` 分层；Linux 有 CFS/EEVDF、per-CPU 数据、RCU、抢占式内核。JOS 的锁粒度粗，胜在好验证；Linux 的复杂度是为了多核扩展性。

文件系统：JOS 把文件系统放在用户态 file server，客户端通过 IPC 发请求，内核只做页映射和调度；xv6 把 inode、block cache、log 放内核里，系统调用直接进内核；Linux 用 VFS 抽象加页缓存，底层是 ext4/xfs 等具体文件系统。JOS 的路径最能说明“微内核式 file server”长什么样，xv6 最能说明“单体内核最小闭环”。

IPC：JOS 是同步 rendezvous 加可选页映射；xv6 是 pipe + `sleep/wakeup`；Linux 是 pipe/socket/shm 多套接口，语义和缓冲策略各不同。

```text
JOS:   int 0x30 -> T_SYSCALL -> syscall() -> sys_*
xv6:   int 64   -> syscall() -> sys_*
Linux: syscall  -> entry_SYSCALL_64 -> sys_call_table[nr]
```

**最小例子**：同一个“父进程写、子进程读”的场景。JOS 里父 Env 调 `ipc_send(child, value, page, perm)`，子 Env 调 `ipc_recv` 阻塞等待，页随消息映射过去；xv6 里父进程 `pipe()` 得到两个 fd，`write(fd[1], buf, n)` 进内核 `pipewrite`，子进程 `read(fd[0], ...)` 在 `piperead` 里被唤醒；Linux 用户态同样 `pipe()`/`write`/`read`，但内核走 VFS 的 pipefs，缓冲区和等待队列由内核统一管。三条路径解决同一件事，暴露的抽象层级不同。

**面试高频问法**：

- 问：JOS、xv6、Linux 的系统调用入口有什么差别？→ 考点：中断/指令入口与寄存器约定。→ 答：JOS 和 xv6 都是软中断进内核，JOS 是 `int 0x30`，xv6 是 `int 64`；Linux x86-64 用 `syscall` 指令，入口后查系统调用表。
- 问：为什么 JOS 把文件系统放用户态，xv6 放内核？→ 考点：微内核 vs 单体内核。→ 答：JOS 用 IPC 加页映射把 file server 隔离开，故障域小但路径长；xv6 追求最小可运行闭环，直接内核里做 inode 和块缓存。
- 问：JOS 的 IPC 和 xv6 的 pipe 能互相替代吗？→ 考点：消息语义与流语义。→ 答：不能直接替代；IPC 是同步消息会合，pipe 是有界字节流和 fd 生命周期，pipe 可以建在 IPC 上，反过来会丢消息边界。
- 问：xv6 的 `sleep/wakeup` 和 Linux 的等待队列差在哪？→ 考点：丢失唤醒与条件检查。→ 答：xv6 用“持有锁检查条件再 sleep”避免丢失唤醒；Linux 把等待队列项挂到队列上，唤醒方持锁摘链，扩展性和公平性更好。
- 问：JOS 的页表操作和 Linux 的缺页处理思路差异？→ 考点：显式映射 vs 按需缺页。→ 答：JOS 在系统调用里显式 `page_insert`，错了立刻返回错误；Linux 先建 VMA，真正访问时缺页再分配/映射，策略更灵活。
