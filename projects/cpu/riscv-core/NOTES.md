# riscv-core · 分章详细

> 这是**动手文档**，每一步都以"能跑一条命令、能看到一个结果"为单元。
> 不写排期，不写进度；只写要解决的问题、机制、可直接照做的片段、以及验收判据。
> 与 `cpu-microarchitecture/` 的分工：那边讲"怎么读别人的核并归因"，这边讲"怎么自己造一个核并证明它对"。

---

## S0 工具链与最小验证台

### 要解决的问题

在写第一行有用的 RTL 之前，必须先有一条**几十秒内跑完的回路**：改一行 → 编译 → 运行 → 看波形。这条回路不通，后面每遇到一个 bug 都要先把环境修一遍，调试成本会被放大成"项目本身"。

同时要挡住一个常见陷阱：**先把整套 PDK、OpenROAD、OpenLane 装齐再写代码**。安装链路动辄几小时且容易断，而 S1–S8 一个都用不到它们——时序工具到 S9 才需要。

### 机制

分两批装，中间隔着一个能跑通的里程碑。

**第一批（S1 就要）**：Verilator（仿真）、RISC-V 交叉编译器（出测试程序）、Spike（参考模型）。

```bash
# macOS，两条都能直接装
brew install verilator icarus-verilog gtkwave

# RISC-V bare-metal GCC：xPack 提供 darwin-arm64 预编译包，解压即用
#   https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases
# 解压后把 bin/ 加进 PATH，验证：
riscv-none-elf-gcc --version

# Spike：RISC-V 官方 ISA 模拟器，需要自己编（依赖 device-tree 库）
git clone https://github.com/riscv-software-src/riscv-isa-sim
cd riscv-isa-sim && mkdir -p build && cd build
../configure --prefix="$HOME/.local"
make -j"$(sysctl -n hw.ncpu)" && make install
spike --isa=rv32i --help | head
```

**第二批（S9 才要）**：Yosys（综合）、OpenSTA（时序）、sky130（工艺库）。brew 里 Yosys 有包，OpenSTA 与 PDK 在 macOS 上直接编容易断，**建议用容器**：OpenROAD-flow-scripts 或 OpenLane 2 的镜像里三样都齐。

```bash
brew install yosys            # 综合；版本以 brew 当前为准
yosys -V
# OpenSTA + sky130：走容器，不要在本机硬编
#   docker run --rm -v "$PWD":/work openroad/flow-ubuntu22.04-builder:latest
# PDK 另一种拿法（只需 liberty 时最省事）：
#   pip install volare && volare ls-remote | head && volare enable --pdk sky130 <ver>
```

工具版本与包名会变，装之前以各自 `--help` / release 页为准；**这一段的目的不是安装完美，而是拿到三件东西：`verilator`、`riscv-none-elf-gcc`、`spike` 可用**。

### 最小例子

一个只做计数的最小 DUT 与 testbench，作用是**验证回路**，不是验证功能。

```systemverilog
// rtl/Top.sv —— 只为一个目的：让 Verilator 有东西可编、有信号可看
module Top (
  input  logic clk,
  input  logic rst_n,
  output logic [7:0] cnt
);
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) cnt <= '0;
    else        cnt <= cnt + 8'd1;
endmodule
```

```cpp
// sim/sim_main.cpp
#include <cstdio>
#include "VTop.h"
#include "verilated.h"
#include "verilated_vcd_c.h"

int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv);
  auto* dut = new VTop;
  auto* tfp = new VerilatedVcdC;
  Verilated::traceEverOn(true);
  dut->trace(tfp, 99);
  tfp->open("wave.vcd");

  dut->clk = 0; dut->rst_n = 0;
  for (vluint64_t t = 0; t < 40; ++t) {
    dut->clk = 0; dut->eval(); tfp->dump(10 * t + 0);
    dut->clk = 1; dut->eval(); tfp->dump(10 * t + 5);
    if (t == 2) dut->rst_n = 1;
    if (t % 4 == 3) printf("t=%2llu cnt=%u\n", (unsigned long long)t, dut->cnt);
  }
  tfp->close();
  delete dut;
  return 0;
}
```

```bash
# 编译 + 运行（--timing 在现代 Verilator 上不是必需，但建议打开以支持 #delay）
verilator --cc --exe --build -j 0 --trace -Wall \
          --top-module Top -Mdir obj_dir \
          rtl/Top.sv sim/sim_main.cpp -o sim
./obj_dir/sim
gtkwave wave.vcd &      # 若 X11 麻烦，换 Surfer 或只看 printf
```

**验收判据**：`verilator --lint-only -Wall --top-module Top rtl/*.sv` 零告警；`cnt` 在复位后从 1 开始递增；VCD 能打开且时钟有翻转。

### 面试高频问法

- **"你为什么用 Verilator 而不是 Icarus/VCS？"** → 考点是仿真器的定位。答法：Verilator 把 Verilog 编译成 C++ 模型，跑得快，适合长测试与 difftest；代价是只支持可综合性子集（无 `#delay`、部分四态语义靠 `--x-assign` 近似）。Icarus 更宽松、更慢，适合小模块和快速试探。**difftest 要跑百万条指令，只能选 Verilator。**
- **"testbench 为什么用 C++ 写，不用 Verilog testbench？"** → 考点是验证与仿真分离。答法：C++ 侧可以读文件、接 Spike 日志、做随机生成、统计覆盖率；Verilog testbench 做这些很别扭。Verilator 的模型就是这个思路。
- **"组合逻辑里有 X 怎么办？"** → 考点是对四态的理解。答法：Verilator 默认二态，X 会被折叠成 0/1，靠 `--x-assign unique` 与 `--x-initial unique` 才能暴露部分未初始化问题；真正抓 X 要靠 lint 与复位覆盖率，不能指望仿真。

---

## S1 单周期 RV32I

### 要解决的问题

先把**语义**做对：40 条指令每条都要能改变架构状态（PC、32 个寄存器、内存），且结果与规范逐位一致。这一阶段完全不考虑性能，目标是拿到一个"可以当参考答案"的基线——后面所有流水线改造都要拿它比对。

### 机制

RV32I 基础集 40 条：`LUI AUIPC JAL JALR`、6 条分支（`BEQ BNE BLT BGE BLTU BGEU`）、8 条访存（`LB LH LW LBU LHU SB SH SW`）、9 条立即数运算（`ADDI SLTI SLTIU XORI ORI ANDI SLLI SRLI SRAI`）、10 条寄存器运算（`ADD SUB SLL SLT SLTU XOR SRL SRA OR AND`）、以及 `FENCE ECALL EBREAK`。

三个必须一开始就写对的细节：

1. **`x0` 恒零**。不是"初始化成 0"，而是**所有写口都要屏蔽**（含未来的转发、乱序写回、difftest hook）。这是最常见的遗留 bug。
2. **立即数拼接**。五种格式的位段与符号扩展：

```systemverilog
// RV32I 立即数生成（注意 B/J 型的 bit0 恒为 0，且 J 型位序是乱的）
logic [31:0] imm_i = {{20{instr[31]}}, instr[31:20]};
logic [31:0] imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
logic [31:0] imm_b = {{19{instr[31]}}, instr[31], instr[7],
                      instr[30:25], instr[11:8], 1'b0};
logic [31:0] imm_u = {instr[31:12], 12'b0};
logic [31:0] imm_j = {{11{instr[31]}}, instr[31], instr[19:12],
                      instr[20], instr[30:21], 1'b0};
```

3. **分支比较分有符号/无符号**：`BLT/BGE` 用 `$signed`，`BLTU/BGEU` 用无符号；`SLT/SLTU` 同理。混用会在负数测试上挂。

数据通路是教科书那条：PC → I-Mem → 译码/立即数 → 寄存器堆读 → ALU（或地址计算）→ D-Mem → 写回。控制单元按 `opcode/funct3/funct7` 出控制信号。

### 最小例子

用 riscv-tests 的裸机测试作输入。它们自带自检逻辑：通过就往 `tohost` 写 1，失败写 `(测试号<<1)|1`。

```bash
git clone https://github.com/riscv-software-src/riscv-tests
cd riscv-tests && git submodule update --init --recursive
autoconf && ./configure --prefix="$PWD/install"
make -j"$(sysctl -n hw.ncpu)" RISCV_PREFIX=riscv-none-elf-
ls isa/rv32ui-p-*.elf | head      # rv32ui-p-add, -sub, -lw, -jal ...
```

ELF 转成 `$readmemh` 能吃的格式：

```bash
riscv-none-elf-objcopy -O binary isa/rv32ui-p-add isa/rv32ui-p-add.bin
# 或者用 riscv-isa-sim 自带的 elf2hex（宽度 4 字节、深度按内存大小，基址选项以 --help 为准）
elf2hex 4 65536 isa/rv32ui-p-add > imem.hex
# 基址不是 0x80000000 时，用它的 base-addr 选项，或直接 $readmemh + 手算偏移
```

testbench 侧加一个"停机监视"：盯着对 `0x80001000`（tohost）的写，值非零即结束并按值判 pass/fail。

```cpp
// 在每次 D-Mem 写之后
if (dut->mem_we && dut->mem_addr == 0x80001000u) {
  uint32_t v = dut->mem_wdata;
  printf("%s (code=%u)\n", v == 1 ? "PASS" : "FAIL", v);
  break;
}
```

**验收判据**：`rv32ui-p-*` 全部 PASS。挂在 `-jal`/`-jalr` 上多半是 J 型立即数位序错；挂在 `-sll` 上是移位量取错（应取 `rs2[4:0]` 而非整个 `rs2`）；挂在 `-lb`/`-lh` 上是字节选择与符号扩展错。

### 面试高频问法

- **"为什么 `x0` 要特殊处理？它不就是个恒零寄存器？"** → 考点是写口屏蔽的覆盖面。答法：恒零是靠"任何写口都不写它"实现的，不是靠初值；一旦漏掉一个写口（转发旁路、乱序写回、difftest hook），程序里 `x0` 就会变成普通寄存器，而且症状是随机的。RV32I 里 `x0` 同时被用作"零值"与"丢弃结果"的约定，破坏它会让大量指令静默出错。
- **"单周期实现的最长路径在哪？"** → 考点是关键路径分析。答法：`load` 那条：PC → I-Mem → 译码 → 寄存器堆读 → ALU 算地址 → D-Mem 读 → 写回。所以时钟周期被 `load` 钉死，`add` 这类只过 ALU 的指令全程在浪费——这正是流水线的动机。
- **"`auipc` 和 `lui` 有什么区别？"** → 考点是 PC 相对寻址。答法：`lui` 只把立即数放高位；`auipc` 放的是 `pc + imm<<12`，配合 `jalr` 实现任意 32 位 PC 相对跳转，是 `-mcmodel=medany` 与 PIC 代码的基础。

---

## S2 五级流水线

### 要解决的问题

单周期把时钟周期锁在最长路径上。切成五级后，每级只承担一部分延迟，时钟由**最慢一级 + 级间寄存器开销**决定，稳态每拍完成一条。代价是引入三类冒险（下一节处理）和更复杂的控制。

### 机制

五级：IF（取指、PC+4）、ID（译码、读寄存器堆）、EX（ALU、分支判定）、MEM（访存）、WB（写回）。级间寄存器四组：`IF/ID`、`ID/EX`、`EX/MEM`、`MEM/WB`。

关键点是**级间寄存器里存什么**：不只是数据，还有**后续级需要的控制信号**（`regwrite/dest/memread/memwrite/mem2reg/alu_op`）。这些信号在 ID 级生成，然后随指令一起往下流——它们必须和指令同步打拍，否则会出现"用后面指令的控制信号"的经典 bug。

必须打通的两条控制通路：

- **stall**：冻结 PC 与 `IF/ID`，同时把 `ID/EX` 清空（插 bubble）。load-use 与结构冒险用。
- **flush**：清空 `IF/ID` 与 `ID/EX`（分支在 EX 解析时，已取入 2 条年轻指令要丢弃）。

### 最小例子

5 条互不依赖指令的空图（每格一拍）：

| 指令 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| i1 | IF | ID | EX | MEM | WB | | | | |
| i2 | | IF | ID | EX | MEM | WB | | | |
| i3 | | | IF | ID | EX | MEM | WB | | |
| i4 | | | | IF | ID | EX | MEM | WB | |
| i5 | | | | | IF | ID | EX | MEM | WB |

总拍数 $= 5 + (n-1)$，含填充的 CPI $= 9/5 = 1.8$，稳态 CPI $= 1$。

**验收判据**：① S1 的全部 riscv-tests 仍然全过（改造后一次不挂）；② 波形上能指出"i5 在 IF 时 i1 在 WB"；③ 在 DUT 里加一个周期计数器，跑同一程序，周期数 ≈ 指令数 + 4 + 停顿数，且停顿数与第三节手算一致。

### 面试高频问法

- **"流水线级数越多越快吗？"** → 考点是级间寄存器开销与惩罚放大。答法：$T_{clk}=\max_i T_i + t_{reg}$，级数增加时固定开销 $t_{reg}$ 占比上升；且误预测要冲刷的级数变多，惩罚从"深度 × 宽度"增长；净收益递减，拐点按实现而定。
- **"为什么把写回放在最后一级而不是算完就写？"** → 考点是级间一致性与冒险检测。答法：写成统一在 WB 完成，可以让所有指令有同一个写回点，冒险检测与转发逻辑只需要盯一个阶段；这也让"顺序写回"成为后续乱序核的基础。
- **"级间寄存器里为什么要带控制信号？"** → 考点是控制随指令流动。答法：控制信号在 ID 生成，但要用在 EX/MEM/WB，必须和该指令一起打拍流下去；不带着走就会用到后面指令的控制信号，出现"上一条指令本该不写回却写了"。

---

## S3 冒险与转发

### 要解决的问题

重叠执行让相邻指令互相踩资源（结构冒险）、踩寄存器（数据冒险）、踩取指流（控制冒险）。不处理，要么算错，要么退化到接近串行。这一节的目标是把 $CPI = 1 + \text{每指令停顿拍数}$ 里的加数压到最小，并且**能算清每一项的来路**。

### 机制

**结构冒险**：单端口存储器会让 IF 与 MEM 冲突。做法是 I-Mem/D-Mem 分开（Harvard 化），或用一块存储器 + 指令/数据仲裁。教学核一律分开——真实核也基本分开 L1I/L1D。

**数据冒险（RAW）**：转发单元比较 EX 级源寄存器与 `EX/MEM.rd`、`MEM/WB.rd`，命中就旁路。**优先级：`EX/MEM` 高于 `MEM/WB`**（更年轻的写者更新）。转发解决不了 load-use：load 的数据在 MEM 末才可用，消费者在 EX 就要，必须停一拍。

**控制冒险**：分支在 EX 解析，已取入的 2 条年轻指令要冲刷，惩罚 2 拍。

```systemverilog
// 转发选择（EX 级）：只有 regwrite 且 rd != 0 才可转发
always_comb begin
  fwd_a = 2'b00;                       // 00: 寄存器堆 01: EX/MEM 10: MEM/WB
  if (exmem_regwrite && exmem_rd != 5'd0 && exmem_rd == idex_rs1) fwd_a = 2'b01;
  else if (memwb_regwrite && memwb_rd != 5'd0 && memwb_rd == idex_rs1) fwd_a = 2'b10;

  fwd_b = 2'b00;
  if (exmem_regwrite && exmem_rd != 5'd0 && exmem_rd == idex_rs2) fwd_b = 2'b01;
  else if (memwb_regwrite && memwb_rd != 5'd0 && memwb_rd == idex_rs2) fwd_b = 2'b10;
end

// load-use 检测：当前在 EX 的是 load，下一条在 ID 就要用它的结果
wire load_use = idex_memread && (idex_rd == ifid_rs1 || idex_rd == ifid_rs2) && (idex_rd != 0);
```

注意 `idex_rd != 0` 这个条件：漏掉它就会出现"`x0` 看起来被转发"的诡异行为，且只在特定指令序列上暴露。

### 最小例子

```asm
lw   x1, 0(x2)      # 数据在 MEM 末可用
add  x4, x1, x5     # EX 需要 x1 → 必须停 1 拍，然后从 MEM/WB 转发
```

时间线：`lw` 在 MEM 时 `add` 停在 ID；下一拍 `lw` 进 WB，`add` 进 EX 并从 `MEM/WB` 转发拿到值。**停 1 拍**。

对比 `add x1,x2,x3` 后接 `sub x4,x1,x5`：`sub` 在 EX 时 `add` 在 MEM，从 `EX/MEM` 直接转发，**零停顿**。

**验收判据**：写一段刻意依赖的汇编，用 DUT 的周期计数与停顿计数对照手算；误预测冲刷后所有寄存器与顺序模型一致（用 S6 的 difftest 全量兜底）。

### 面试高频问法

- **"有了转发为什么还会停？"** → 考点是值的可用时间。答法：转发只能提前已经算出的值；load 的值最早在 MEM 末出来，消费者在 EX 就要，物理上无法提前。乱序核里这条依赖仍在，只是被别的指令填空拍——乱序消除等待，不消除依赖。
- **"WAR/WAW 在五级顺序流水线要处理吗？"** → 考点是冒险分类与寄存器重命名的作用范围。答法：顺序流水线按程序序写回，WAR/WAW 不会造成错误；到乱序多发射才需要重命名来消除。
- **"为什么转发优先级是 EX/MEM 高？"** → 考点是写者年龄。答法：`EX/MEM` 里的指令比 `MEM/WB` 里的更年轻，它写的是更新的值；反过来会拿到旧值。这是最容易写反的一处，症状是长依赖链上偶发错值。

---

## S4 分支预测

### 要解决的问题

分支在 EX 才解析，前端每遇分支就可能空等 2 拍；流水越深、发射越宽，浪费越大。预测把"每分支必停"换成"平时猜，猜错付代价"，让控制冒险从常态变成例外。

### 机制

两件事分开做：**方向**（taken/not taken）与**目标**（target）。

- **BHT（方向）**：2-bit 饱和计数器。`00/01` 预测不跳，`11/10` 预测跳；每次实际结果更新计数器（饱和不回绕）。2 位能抵抗一次噪声，这是它比 1 位强的地方。
- **BTB（目标）**：以分支 PC 的低位索引，存 `{valid, tag, target}`。命中就下一拍从 `target` 取指。
- **误预测恢复**：`flush` 所有年轻指令 + `PC <= 恢复地址`（taken 用 target，not-taken 用 `pc+4`），并更新预测器状态。

进阶（有余力再做）：全局历史 + 局部历史的锦标赛、TAGE-lite（多长度历史 + tag 匹配 + 选择逻辑）。**先不要做 TAGE**——没有 BHT+BTB 的干净基线，TAGE 的收益与 bug 分不开。

### 最小例子

```systemverilog
// 2-bit 饱和计数器：11 强跳, 10 弱跳, 01 弱不跳, 00 强不跳
always_ff @(posedge clk) begin
  if (bht_we) begin
    case (bht[idx])
      2'b00: bht[idx] <= actual_taken ? 2'b01 : 2'b00;
      2'b01: bht[idx] <= actual_taken ? 2'b10 : 2'b00;
      2'b10: bht[idx] <= actual_taken ? 2'b11 : 2'b01;
      2'b11: bht[idx] <= actual_taken ? 2'b11 : 2'b10;
    endcase
  end
end
```

一段循环 `for (i=0;i<1000;i++)` 的分支，稳态预测率接近 100%，但**退出那一次必然误预测**——所以"每千次迭代一次误预测"是这类循环的固有下限，不要指望 predictor 消掉它。

**验收判据**：在 S1 的测试程序与 CoreMark/Dhrystone 上统计 MPKI（每千指令误预测数），从 always-not-taken → BHT → BHT+BTB 三档都要报，同时报 IPC。**只报 IPC 不报 MPKI，等于没有因果**。

### 面试高频问法

- **"误预测的代价由什么决定？"** → 考点是深度与宽度。答法：大致等于"流水深度 × 前端重填宽度"——要冲刷的年轻指令数 × 每拍能取回的指令数；深流水惩罚更大，所以深流水必须配更强的预测器。
- **"2-bit 计数器为什么不换成 1-bit？"** → 考点是噪声容忍。答法：1 位在一次偶然反向就翻转，循环退出与嵌套分支上会连续误预测；2 位要求连续两次反向才改变预测，能吸收单次抖动。
- **"TAGE 比两级自适应强在哪？"** → 考点是历史长度问题。答法：不同的分支需要不同长度的历史（长历史捕捉相关性，短历史抗噪声），TAGE 用多张不同长度历史的表 + tag 匹配 + 带偏置的选择逻辑动态挑一张；判据是 MPKI，不是"准不准"。
- **"预测器会不会成为时序瓶颈？"** → 考点是预测在关键路径上。答法：预测发生在取指级，允许跨拍；但 BTB 的读 + tag 比较 + 选择往往决定前端频率，所以真实核把 BTB 分级、把预测拆到多拍。这是 S9 会真实撞到的问题。

---

## S5 存储：I/D cache 与存储器接口

### 要解决的问题

S2–S4 让核内的指令流跑起来了，但每条 load 都直接打到存储器。真实存储器有延迟，一条慢 load 就能把整个窗口堵死。cache 的作用是把绝大多数访存留在核附近，同时把"缺失时的等待"变成可管理的状态机。

### 机制

三层概念要分清：**结构**（容量/路数/行大小）、**策略**（写回还是写穿、分配还是不分配、替换算法）、**接口**（怎么和后端存储器握手）。

位划分先算清：4KB、16B 行、直接映射 → 256 行 → `offset=4 bit`、`index=8 bit`、`tag=20 bit`。升两路组相联（同样 4KB/16B）→ 128 组 → `index=7 bit`、`tag=21 bit`。**这几个数写错，miss 率会与手算对不上，之后所有性能结论都不可信**。

策略取最常见的一组：**write-back + write-allocate**（写命中只标 dirty，写缺失先取行再写）。需要 `dirty` 位与"替换时回写"的状态。

接口不要一上来就做 AXI。先用一个简单的同步 SRAM 模型：`req_valid / req_ready / req_addr / req_wdata / req_we` + 固定延迟，在 testbench 里可参数化（`+LATENCY=20`）。**延迟可参数化比"总线协议正确"重要得多**——它让你能做"延迟 → IPC"的敏感性分析。

### 最小例子

```systemverilog
// 直接映射 D-cache 的读路径骨架（省略写路径与替换）
logic [255:0] tagv;          // valid
logic [255:0] dirty;
logic [19:0]  tag_q [256];
logic [127:0] data_q [256];  // 16B = 128 bit

wire [3:0]  offset = addr[3:0];
wire [7:0]  index  = addr[11:4];
wire [19:0] tag    = addr[31:12];

wire hit = tagv[index] && (tag_q[index] == tag);
```

一段能暴露集合冲突的 microbench：以 4KB 为步长访问数组（`a[i*1024]`），直接映射下每次必 miss，两路组相联仍必 miss（同组），四路开始缓解——**这条曲线能同时验证你的位划分和你的路数**。

**验收判据**：① 顺序/跨步/随机三种模式的 miss 率与手算一致（直接映射与两路各算一遍）；② 加 cache 后同一 microbench 的 IPC 上升，且上升幅度能归因到 miss 数下降；③ 关掉 cache（直通）结果仍正确——**正确性不能被 cache 掩盖**。

### 面试高频问法

- **"cache 的容量、路数、行大小各自影响什么？"** → 考点是 AMAT 三项。答法：容量降 miss 率，路数降冲突缺失，行大小影响空间局部性收益与缺失代价（行越大，单次 miss 搬得越多，可能浪费带宽）；三者都会抬高命中时间或面积，所以是权衡。
- **"L1 为什么常见 VIPT？"** → 考点是并行启动翻译与索引。答法：页内偏移在翻译前后不变，所以 index 可以取自虚拟地址，与 TLB 并行；tag 用物理地址比较。只要 index 位宽不超过页偏移，VIPT 等价于 PIPT，天然无别名。
- **"write-back 与 write-through 怎么选？"** → 考点是写放大与一致性复杂度。答法：write-back 省带宽但需要 dirty 位与回写路径，未见一致性复杂度（单核无影响）；write-through 简单但每次写都打后端，写密集负载下带宽压力大。多核下 write-back 还需要一致性协议配合。
- **"为什么要做延迟可参数化？"** → 考点是性能实验的方法。答法：核的性能结论必须能对"存储器变慢"做出可预测的响应；延迟固定时，你无法区分"IPC 低是因为结构不好"还是"因为后端太慢"。

---

## S6 difftest 与随机测试

### 要解决的问题

到这一步你有几个版本（顺序、流水线、有预测、有 cache），每一版都可能引入"看起来对"的错误。人写的测试覆盖度等于自己的想象力，而 CPU 的 bug 集中在想不到的组合里。这一节建立**机器判定**：每条提交的指令与官方参考模型逐条比对。

### 机制

核心是"提交日志"（commit log）对齐：

- Spike 侧：`--log-commits` 输出每一条提交指令的 PC、指令编码、以及对寄存器的写回。
- DUT 侧：在提交点（顺序核就是 WB，乱序核是 ROB 提交）导出同样的三元组。
- 比对器：C++ 里逐条 diff，第一处不一致就打印上下文（前 10 条 + 当前 PC/寄存器）并停机。

随机程序生成器不要一上来就通用。**约束在能被验证的范围内**：只用 RV32I 的 40 条指令、寄存器随机、访存限制在测试内存段、循环用固定次数、避免无限跳转。几百行的生成器就够，关键是"能跑很多次、每次都能对齐"。

**最关键的一步是注入故障测试**：故意改坏一处（把 `x0` 的写屏蔽去掉、把 J 型立即数的 `instr[20]` 换成 `instr[21]`），确认 difftest 一定报错。**报不出来的 difftest 等于没有**——这是判断验证是否真实有效的唯一方法。

### 最小例子

```bash
spike --isa=rv32i -l --log-commits rv32ui-p-add 2>&1 | head -5
# core   0: 0x0000000080000000 (0x00000297) auipc t0, 0x0
# core   0: 0x0000000080000004 (0x00028613) addi  a2, t0, 0
# ... 每行含 pc / 指令编码 / 汇编文本；寄存器写回在行尾 x<N> <- 0x...
```

```cpp
// 比对器核心：每提交一条，取一行 spike 日志比对
struct Commit { uint32_t pc, instr; int rd; uint32_t value; };
while (dut_step(&c)) {
  if (!spike_next(&ref)) { fail("spike 提前结束"); }
  if (c.pc != ref.pc || c.instr != ref.instr) fail_at(c, ref);
  if (c.rd != 0 && c.value != ref.value) fail_at(c, ref);
}
```

为了让"提交"可观察，乱序核需要在 ROB 提交时把 `{pc, instr, rd, value}` 打到一个 debug port 上。**这个 debug port 是验证的基础设施，不是可选装饰**——一开始就设计它，比事后补要省得多。

**验收判据**：① 至少几百万条随机指令零分歧；② 注入的每个故障都能被抓到并定位到具体提交序号；③ 覆盖率达到你关心的几类指令/冒险组合（自己定义覆盖率，不要迷信行覆盖）。

### 面试高频问法

- **"你怎么保证 CPU 是对的？"** → 考点是验证方法学。答法：riscv-tests 功能自检 + Spike 逐提交 difftest + 注入故障测试三层；**第三层最关键**，它证明前两层真的会报错。
- **"difftest 比对什么？为什么不只比最终内存？"** → 考点是错误传播。答法：只比最终结果会让大量错误互相抵消（错值被后续指令覆盖），且无法定位。逐提交比对能把错误钉在"第 N 条提交、PC=0x…、x7 期望/实际"。
- **"随机测试会不会生成非法指令？"** → 考点是激励约束。答法：生成器只从合法编码模板出指令，且限制访存范围与跳转目标；遇到非法编码要在生成阶段拒绝，而不是让 DUT 去处理（那会引入异常路径，扩大验证面）。
- **"覆盖率怎么定？"** → 考点是验证目标的可度量性。答法：按"指令类型 × 冒险类型 × cache 命中/缺失 × 分支取/不取"定义交叉覆盖，比行覆盖有意义；目标是每类组合都至少命中一次。

---

## S7 乱序前端：重命名 + ROB + 保留站

### 要解决的问题

顺序流水线仍然按程序序发射与完成：一条等 cache 的 load、一条多周期除法，会把后面所有无关指令堵住。乱序把"程序顺序"和"执行顺序"解耦，让窗口内操作数就绪的指令先跑；同时必须**保持外部可见的顺序语义**（精确异常、顺序提交）。

### 机制

三条正交的机制，别混在一起想：

1. **寄存器重命名**：架构寄存器（32 个）→ 物理寄存器（一池，例如 64/96/128）。每条写指令分配一个新 Preg，并更新映射表。效果：WAR/WAW 假依赖消失，旧读者仍指向旧 Preg。RAW 真依赖保留，靠 Preg 编号匹配。
2. **保留站 / 发射队列**：指令在此等待，记录 `{src1_preg, src2_preg, ready1, ready2}`。功能单元算完把 `{preg, value}` 广播到总线上，等待该 preg 的项被唤醒，按就绪（不按程序序）发射。
3. **ROB**：所有指令按程序序分配项，执行完标 `done`，**只有到 ROB 头部才提交**（写架构寄存器、释放旧 Preg）。异常只在头部判定，误预测时丢弃头部之后全部——精确异常的基础。

关键取舍是**窗口大小**：ROB 深度决定能同时在飞多少指令。收益受程序固有 ILP 限制、边际递减；代价是面积近似线性、唤醒/选择逻辑延迟超线性（fmax 会掉），以及误预测时清空的项数。

实现顺序建议：先做**顺序发射 + 乱序完成 + 顺序提交**（有了 ROB 就能跑通精确异常），再加保留站做乱序发射。**一步到位写乱序发射，bug 无法归因**。

### 最小例子

```text
每拍：
  fetch/decode      (in order) ：最多取 W 条
  rename            (in order) ：alloc Preg + alloc ROB entry，读映射表得 src_preg
  dispatch → RS               ：写 {src_preg, ready=busy_table[src_preg]}
  issue             (out of order)：所有 src ready 且功能单元空闲 → 发射
  execute + broadcast         ：结果写回 Preg，清 busy 位，唤醒 RS 中等待者
  writeback / mark done       ：ROB 项标 done
  commit            (in order) ：ROB 头部 done → 写架构寄存器，释放 old_preg 到 free list
```

```systemverilog
// ROB 项字段（最小集）
typedef struct packed {
  logic [31:0] pc;
  logic [31:0] instr;
  logic [4:0]  rd_arch;
  logic [5:0]  rd_phys;
  logic [5:0]  old_phys;   // 提交时释放回 free list
  logic        done;
  logic        is_store;   // store 必须在提交时才写 cache
} rob_entry_t;
```

参数化（`ROB_DEPTH`、`RS_DEPTH`、`NUM_PREG`）从第一天就做。**参数化不是为了省事，是为了 S9 能扫曲线**。

**验收判据**：① 顺序版与乱序版跑同一批测试结果一致，difftest 零分歧；② 扫 `ROB_DEPTH ∈ {16,32,64,128,256}`，画出 IPC 随窗口的曲线，能看到饱和段；③ 能在波形上指出"两条无关指令乱序完成、但按程序序提交"。

### 面试高频问法

- **"重命名到底消除了什么？RAW 呢？"** → 考点是真假依赖。答法：WAR/WAW 是寄存器名字复用造成的假依赖，换 Preg 即消失；RAW 是真依赖，重命名不解决，只能靠转发或等待。所以乱序的收益来自"填掉真依赖造成的空拍"，不是"消除依赖"。
- **"ROB 满了和保留站满了有什么区别？"** → 考点是两种停顿的位置。答法：ROB 满说明提交跟不上（后端长延迟把头部卡住），前端必须停派；RS 满说明某类功能单元长期拥塞（例如访存端口不足），表现为该类指令排队。Top-down 里前者偏后端资源受限、后者偏执行端口受限。
- **"窗口越大越好吗？"** → 考点是边际收益与频率代价。答法：IPC 随窗口上升并在某点饱和；面积线性增长、唤醒与选择逻辑延迟超线性增长导致 fmax 下降。所以最优窗口是在给定频率目标下使 `IPC × f` 最大的那个点——**答案是曲线，不是数字**。
- **"精确异常怎么保证？"** → 考点是提交点唯一。答法：执行阶段不改架构状态，只写 ROB 与 Preg；异常在 ROB 头部判定，此时它之前的已全部提交、之后的全部丢弃，现场精确。store 同理，必须等提交才真正写 cache。

---

## S8 乱序访存：LSQ + 消歧

### 要解决的问题

重命名为寄存器提供了"可换的名字"，**内存没有名字可换**。`store [r1], x` 与 `load r2, [r3]` 是否同址，发射时 `r3` 可能还没算出来。放任 load 越过更老的 store 会读脏；一律不许越又退化成顺序瓶颈。这一节要在两端之间找一个可回滚的折中。

### 机制

- **LQ/SQ**：访存指令按程序序登记。load 可提前发射，但提交前要验证没有被更老的 store 覆盖；store 在提交前**不写 cache**，数据先躺 store buffer。
- **消歧三策略**：保守（地址未知的更老 store 存在就等）→ 激进（预测不别名，先跑，事后验证，错了 replay）→ 折中（地址/依赖预测器记住历史冲突）。
- **store-to-load forwarding**：store 数据还在 buffer 时，后来的 load 命中同址直接从 buffer 取。难点是**部分重叠**：要按字节偏移与掩码拼接；跨多条 store 或跨 cache line 时通常只能停。

### 最小例子

```asm
sw   x11, 0(x10)     # [0x1000] = 0x11223344（小端：44 33 22 11）
lh   x12, 2(x10)     # 读 [0x1002] 2 字节 → 期望 0x1122
```

转发逻辑必须按偏移取高两字节拼出 `0x1122`；若 load 是 `lw x12, 2(x10)`（4 字节，跨出这条 store 的覆盖范围），就只能停顿或合并下一条 store——**这类"部分重叠"是 LSQ 里最大的 bug 源**。

**验收判据**：① 三个 microbench（`memcpy`、链表遍历、随机访存）的 IPC 分别变化，且"保守 vs 投机"的差值能归因到假依赖次数；② difftest 在含大量别名访存的随机程序上零分歧；③ 注入一个"store 提前写 cache"的 bug，确认 difftest 在误预测/异常路径上能抓到。

### 面试高频问法

- **"load 能越过更老的 store 吗？"** → 考点是可回滚性。答法：能，前提是能判断别名或能事后验证并回滚；地址未知时靠预测器猜，猜错触发 memory order clear 重放。
- **"为什么 store 要等提交才写 cache？"** → 考点是精确异常。答法：一旦写了 cache 就无法撤销，误预测或异常后内存已脏；放 store buffer 等 ROB 提交，清流水时才能一并丢弃。
- **"为什么乱序访存比乱序算术难？"** → 考点是地址的运行时性。答法：算术指令的源寄存器编号译码时已知，依赖可静态匹配；访存地址要等地址计算执行完才存在，别名关系动态且不可静态判定，因此必须靠队列 + 运行时比较 + 预测。

---

## S9 时序与面积闭环

### 要解决的问题

到这里核"能跑"且"能对"，但还没有任何**物理约束**的证据。这一节要拿到两个可归因的数字：关键路径的 ns 数、综合后的面积；并且做一次真实的取舍实验，证明你能把 STA 报告翻译成结构改动。

### 机制

流程是三段：**综合**（Yosys：RTL → 门级网表 + 面积）→ **时序**（OpenSTA：网表 + liberty + 时钟约束 → 关键路径与 slack）→ **回去改 RTL**。

三件事必须先想清楚：

1. **约束怎么给**。`create_clock -period <T>`，T 从 2 ns 或 5 ns 起步（sky130 上教学核一般在这个量级，具体按实现），逐步收紧直到违例，那个点就是你的 fmax 估计。
2. **面积报什么**。`stat` 给的单元面积（μm²）与门数，前者可比，后者只是 proxy。
3. **看什么路径**。不是只看 slack 数值，而是看报告的起点/终点与经过的逻辑级数（`report_checks -path_delay max -digits 3`）。

常见三处瓶颈与改法：ALU 进位链（拆流水级 / 超前进位 / 降低位宽换并行）、保留站的唤醒+选择（分 bank、用 age matrix 替优先级编码）、重命名读端口（减发射宽度或分批读）。每改一次都要重报四个数。

### 最小例子

```bash
# 综合 + 面积
yosys -p "read_verilog -sv rtl/*.sv; synth -top Top; stat; write_verilog -noattr netlist.v"

# 时序（OpenSTA，需要 sky130 的 liberty）
cat > sta.tcl <<'EOF'
read_liberty sky130_fd_sc_hd__tt_025C_1v80.lib
read_verilog netlist.v
link_design Top
create_clock -name clk -period 5.0 [get_ports clk]
report_checks -path_delay max -digits 3
report_tns
report_wns
EOF
sta -exit sta.tcl | tee sta.log
```

判读方式：`slack` 为正说明还有余量，收紧周期直到负；`report_checks` 里起点是 `clk`、终点是 `clk`（寄存器到寄存器）的路径才是真正的关键路径，输入到输出的组合路径不算 fmax。

**验收判据**：① 综合无 latch、无未驱动、无多驱动（`yosys` 的 `check` 干净）；② 报出一条具体的关键路径（起点寄存器 → 经过哪些单元 → 终点寄存器）；③ 做一次取舍实验并给出四数表（IPC / 面积 / fmax / 结论）。

### 面试高频问法

- **"你怎么知道能跑到多少频率？"** → 考点是时序分析而不是猜。答法：综合出网表后用 STA 在给定 liberty 与约束下报 slack，收紧周期到违例的那个点就是 fmax 估计；同时要说明这是综合后估计，不含布局布线、时钟树与 PVT 角。
- **"综合后面积大，怎么降？"** → 考点是结构层面的优化。答法：先看 `stat` 里谁占大头——通常是寄存器堆、ROB/RS 的 CAM 与优先编码、多路选择网络。手段是减宽度、参数化裁剪（窗口/RS 深度）、共享功能单元、把大 mux 换成树形结构。**面积换性能永远是一笔交易，要报两边。**
- **"为什么教学核的频率不能和商用核比？"** → 考点是工艺与后端。答法：工艺不同（sky130 vs 先进节点差几代）、流程不同（综合后估计 vs 完整后端 + 时钟树 + PVT 签核）、结构不同（教学核没有手工优化关键路径）。可比的是"同工艺下面积-性能点"。

---

## S10 性能归因（可选，收口章）

### 要解决的问题

S7–S9 给出了结构、IPC 与频率，但没回答"这个核现在卡在哪"。没有归因，下一次改动就只能试。这一节把自研核的 CPI 分解开，与 `cpu-microarchitecture/` 的 Top-down 四分类对齐，形成闭环。

### 机制

在核里埋最少的计数器：`cycles`、`instret`、`fetch_stall`（前端无指令可派）、`rob_full`、`rs_full`、`lsq_full`、`branch_mispredict`、`icache_miss`、`dcache_miss`。然后按 Top-down 归类：

- **retiring**：正常提交；
- **bad speculation**：误预测与错误路径浪费；
- **front-end bound**：取指/icache/队列空；
- **back-end bound**：执行端口拥塞或访存等待。

四个桶的和应能解释总周期数——**解释不了的部分就是你还缺的计数器**，这本身就是一条判据。

### 最小例子

```bash
# 跑同一 microbench 的两版参数，比较四桶占比
./obj_dir/sim +rob=32  +bench=memcpy
./obj_dir/sim +rob=128 +bench=memcpy
# 输出：cycles, ipc, front%, badspec%, backend%, retiring%
```

**验收判据**：四桶之和与总周期的偏差在可解释范围内；且"改一处结构 → 桶的占比按预期移动"能被实测印证（例如加深 ROB 应降 backend bound、提高 BTB 命中应降 bad speculation）。

### 面试高频问法

- **"你怎么知道瓶颈在哪？"** → 考点是有没有可证伪的判断。答法：埋计数器做 Top-down 四分类，看哪一类占比最高；然后写下"如果改 X 则 Y 桶应下降"的预测，改完实测验证。**能被推翻的判断才算分析。**
- **"自研核的 IPC 低，是结构问题还是程序问题？"** → 考点是两者分离。答法：先看前端桶——如果前端受限，是取指带宽/缓存问题；再看错误投机桶——如果高，是预测器问题；两者都低才轮到后端结构。分离靠计数器，不靠感觉。

---

## S11 上板与功耗（可选，纯加分）

### 要解决的问题

用真实 FPGA 跑一次，获得"真的在跑"的体感与一个真实 fmax；但必须清楚它与 S9 的数字**不可换算**。

### 机制

板子选逻辑资源够 RV32I 带 cache 的规模（Arty A7 一类即可）。流程：Vivado/Quartus 综合实现 → 引脚与时序约束 → 下载 → 用 UART 打印 CoreMark 结果。判据是**板上跑出的周期数与 Verilator 仿真一致**（同一程序、同一参数），这才说明实现没有引入行为差异。

功耗只做量级估算：门数 × 单位功耗，或看工具报的静态/动态估计；**不做签核**，也不要说"功耗是 X 瓦"。

### 面试高频问法

- **"FPGA 上跑通了说明什么？"** → 考点是边界。答法：说明设计可综合、时序可收敛、行为与仿真一致；不说明面积效率、不说明在 ASIC 上的频率，也不说明功耗。
- **"仿真和上板结果不一致，先怀疑什么？"** → 考点是复位与初始化。答法：先查未初始化寄存器（仿真二态、板上四态/上电随机）、再查跨时钟域与复位释放时序，最后才是逻辑错误——前两类在仿真里天然不暴露。

---

## 附录 A 判据表模板（每个改动都要填）

| 改动 | IPC | 面积 (μm²) | fmax (MHz) | 关键路径变化 | 结论 |
|---|---|---|---|---|---|
| 基线（五级 + BHT） | | | | | |
| + BTB | | | | | |
| + D-cache 4KB 直接映射 | | | | | |
| ROB 32 → 128 | | | | | |

**填不满这张表的改动不要做**——它的意思是"这个改动无法被评价"。

## 附录 B 坑清单（按出现频率排序）

1. `x0` 只做了初值置零，没屏蔽写口 —— 症状随机、难定位。
2. J 型立即数位序错（`instr[20]` 与 `instr[30:21]` 顺序颠倒）—— `jal` 跳飞。
3. 分支立即数漏掉 `bit0 = 0` —— 跳到奇数地址，取指错位。
4. 级间寄存器没带控制信号 —— 用到后一条指令的 `regwrite`。
5. 转发漏 `rd != 0` 判断 —— 特定序列上 `x0` 变成可变寄存器。
6. 转发优先级写反（`MEM/WB` 高于 `EX/MEM`）—— 长依赖链上偶发错值。
7. `stall` 只冻结 PC 没清 `ID/EX` —— bubble 没插进去，重复执行。
8. `flush` 时保留站/ROB 残留 —— 错误路径的指令后来又被提交。
9. store 在 EX/MEM 就写 cache —— 误预测后内存脏。
10. load 的字节选择用 `addr[1:0]` 之外的方式 —— `lb/lh` 取错字节。
11. cache index/tag 位宽算错 —— miss 率与手算不符，性能结论全废。
12. difftest 只在最终内存比对 —— 错误互相抵消，无法定位。
13. 乱序提交宽度 > 1 但异常判定仍按单条 —— 异常现场不精确。
14. 参数化深度用 `localparam` 写死后又手动改多处 —— 曲线扫的不是同一个设计。
15. 用自写测试替代 difftest —— 覆盖面等于想象力。
16. CoreMark/Dhrystone 裸机跑不起来就放弃 —— 它们需要自己补 `core_portme.c`（计时与输出）；**在 Verilator 里计时就是数仿真周期，比上板更干净**，只要把周期数打出来即可。

## 附录 C 命令速查

```bash
# lint / 仿真
verilator --lint-only -Wall --top-module Top rtl/*.sv
verilator --cc --exe --build -j 0 --trace --top-module Top -Mdir obj_dir rtl/*.sv sim/sim_main.cpp -o sim

# 测试程序
make -j RISCV_PREFIX=riscv-none-elf-            # riscv-tests
elf2hex 4 65536 <elf> 0x80000000 > imem.hex     # 或 objcopy -O binary

# 参考模型
spike --isa=rv32i -l --log-commits <elf>

# 综合 / 时序
yosys -p "read_verilog -sv rtl/*.sv; synth -top Top; stat; write_verilog -noattr netlist.v"
sta -exit sta.tcl

# 波形
gtkwave wave.vcd &
```

## 附录 D 读开源核的路线（读什么、不读什么）

**先读 Rocket（顺序、5 级 + 可选乱序访存）**：它的 `IBuf/ID/EX/MEM/WB` 与 Hazard 逻辑能直接对上 S2–S3，是最短的对照路径。

**再读 BOOM/SonicBOOM（乱序）**：只看四块——重命名与 free list、ROB 提交与回滚、保留站唤醒、LSQ 消歧。其余（TLB、浮点、向量、多核一致性）**此时一律跳过**，它们会把注意力从微架构拉到别处。

**读的方式**：先看模块端口与参数（结构规模），再看状态机的几个关键 case（stall/flush/rollback），最后才看具体逻辑。不要从第一行读到最后一行。

**不读**：任何涉及 MMU/特权级/一致性的实现细节——那些是另一条线的知识，在这里读只会增加负担而不增加能力。
