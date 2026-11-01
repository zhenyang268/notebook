# nand2tetris · 一小时上手

> **前提**：无。会一点布尔代数的与或非即可。
> **这一小时的产出**：用 NAND 搭出 `Not / And / Or / Xor / Mux / DMux` 六个门，通过 P1 全部测试。
> **不碰**：加法器、ALU、CPU。

---

## 1 这一小时只做一件事

**接受"一切从 NAND 开始"这个设定，然后把六个门搭出来。**

这不是练习，是**世界观的切换**：你平时用的所有位运算，最后都落在这一个门上。

---

## 2 最小可跑（50 分钟）

### 2.1 先记住 NAND 的真值表（5 分钟）

| a | b | NAND |
|---|---|---|
| 0 | 0 | 1 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | **0** |

**规则：只有全 1 才出 0。** 其余全 1。

### 2.2 六个门（35 分钟，每个 5–6 分钟）

```hdl
// Not: a NAND a 就是非
CHIP Not { IN in; OUT out;
  PARTS: Nand(a=in, b=in, out=out);
}

// And: 非(非 a 与 b) = a AND b
CHIP And { IN a, b; OUT out;
  PARTS:
    Nand(a=a, b=b, out=n);
    Not(in=n, out=out);
}

// Or: 非 a NAND 非 b
CHIP Or { IN a, b; OUT out;
  PARTS:
    Not(in=a, out=na); Not(in=b, out=nb);
    Nand(a=na, b=nb, out=out);
}

// Xor: (a Or b) And Not(a And b)
CHIP Xor { IN a, b; OUT out;
  PARTS:
    Or(a=a, b=b, out=o);
    And(a=a, b=b, out=an);
    Not(in=an, out=nand);
    And(a=o, b=nand, out=out);
}

// Mux: sel=0 出 a，sel=1 出 b
CHIP Mux { IN a, b, sel; OUT out;
  PARTS:
    Not(in=sel, out=nsel);
    And(a=a, b=nsel, out=x);
    And(a=b, b=sel, out=y);
    Or(a=x, b=y, out=out);
}

// DMux: sel=0 时 a 通，sel=1 时 b 通
CHIP DMux { IN in, sel; OUT a, b;
  PARTS:
    Not(in=sel, out=nsel);
    And(a=in, b=nsel, out=a);
    And(a=in, b=sel, out=b);
}
```

### 2.3 跑测试（10 分钟）

用官方 `HardwareSimulator` 加载 `.tst`，看输出是否与 `.cmp` 一致。**全绿才算过。**

---

## 3 三个核心难点

### 3.1 为什么 Mux 是"CPU 的心脏"

Mux（多路选择）在 CPU 里就是**"根据控制信号选数据来源"**。
408 里的"数据通路"图，本质上就是**一堆 Mux + 一堆寄存器 + 一条 ALU**。
**看懂 Mux，就看懂了数据通路的一半。**

### 3.2 DMux 是"译码器"的原型

`DMux` 把一路输入分到两路，按 `sel` 选。
**扩展到 $n$ 位 sel 就是 2-to-4、3-to-8 译码器**——408 里"地址译码"就是这个。

### 3.3 NAND 是"功能完备"的

**任何布尔函数都能只用 NAND 实现**。这不是巧合，是"完备集"的定义。
所以"从 NAND 开始"不是简化，是**理论上最省的起点**。

---

## 4 卡住怎么办

| 现象 | 原因 | 修法 |
|---|---|---|
| `Or` 输出不对 | 用了 `Nand(a,b)` 而不是 `Nand(na,nb)` | 先取非再与非 |
| `Xor` 测试挂 | 漏了 `a And b` 的取反 | 按公式逐项拼 |
| HDL 报"未连接" | 引脚名拼错 | 检查 `IN`/`OUT` 与内部 wire 名 |

**调试方法**：先用真值表手算一行，再对 HDL 的输出。**不要盲改。**

---

## 5 这一小时之后

- 通了 → 进 P2：用 Xor 和 And 拼半加器 → 全加器 → 16 位 ALU。
- 想看全貌 → `OUTLINE.md` 的 P5（CPU），那是这个项目的分水岭。

## 6 通向

| 你要什么 | 去哪 |
|---|---|
| 完整 12 个项目 | `OUTLINE.md` |
| 详细实验记录 | `NOTES.md` |
| 门电路与 ALU 考点 | `exam/408/co/ROADMAP.md` |