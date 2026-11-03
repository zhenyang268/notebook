# langs/ · 路径手册

> 编排，不是教材：规定「读到哪、用哪个工具验证、判据是什么」。

## 0 怎么用

- 选路径：§2。
- 三份文档的判据差异：§1 的口径表。
- 准备追问：§4。
- 避坑：§3。

## 1 三条判据链（别混用）

| | `cpp-basics` | `python-basics` | `cuda` |
|---|---|---|---|
| 回答的问题 | 这段代码为什么会崩/会错 | 这段代码为什么慢在这 | 这个 kernel 为什么跑不满 |
| 主判据 | 能指出 UB 或生命周期错误，并用工具证实 | 能用运行时机制解释行为差异 | 能用 profiler 指标定位瓶颈类 |
| 工具 | `-fsanitize=address,undefined`、`objdump`、`-fdump-lang-class`、`valgrind` | `dis`、`sys.getrefcount`、`tracemalloc`、`-X importtime`、事件循环日志 | `ncu`/`nsys`：占用率、bank conflict、访存效率、stall reason |
| 失效条件 | 优化等级改变后行为不同（正是 UB 的证据） | 换了实现（PyPy/free-threading）结论不同 | 换了架构（SM 数、共享内存大小）结论不同 |
| 一句话口径 | 编译器假设了什么 | 运行时替你做了什么 | 硬件等着什么 |

**一条铁律**：三个方向都**不接受"感觉更快"**。C++ 要能复现崩溃或差异，Python 要能给出耗时/内存的分项，CUDA 要能给出指标名与数值。

## 2 推荐顺序

### 第一段：C++ 对象模型（必做）

```bash
clang++ -std=c++20 -fdump-lang-class t.cpp    # 看类的布局与 vtable
clang++ -g -O2 -S -o - t.cpp | c++filt | head -40
objdump -d a.out | grep -A3 'call.*\*'        # 虚调用是间接跳转
```

**判据**：给定一个含虚函数、多继承、空基类优化的类，能画出内存布局并解释每个填充字节的来由；能说清"为什么这个虚调用无法内联"。

### 第二段：C++ 生命周期与 UB（必做）

```bash
clang++ -g -fsanitize=address,undefined t.cpp -o t && ./t
```

**判据**：能构造三类最小复现——悬垂指针/引用、越界、有符号溢出被优化放大；并解释 `-O0` 与 `-O2` 行为不同的原因。

### 第三段：C++ 并发与内存序（必做）

**判据**：能写出一个只在弱序机器上错的例子（例如缺少 acquire/release 的发布-订阅），并说明 `seq_cst` 多挡掉了什么重排、代价在哪。

### 第四段：Python 语义与运行时（建议）

```bash
python3 -c "import sys; a=[]; f=lambda x=a: x; print(sys.getrefcount(a))"
python3 -X importtime -c "import json"
python3 -m dis - <<< 'def f(x): return x+1'
```

**判据**：能解释默认参数可变陷阱的机制（默认值在定义时求值一次）、生成器的惰性与内存优势、以及 `is` 与 `==` 在整数缓存上的差异边界。

### 第五段：Python 并发（建议）

**判据**：同一段 CPU 密集代码分别用线程、协程、多进程跑，能解释三者耗时差异的来源；能指出"协程里放 `time.sleep` 会怎样"的实验现象与原因。

### 第六段：CUDA 模型（看条件）

**没有 GPU 也能走**：用文档里的模型讲清三件事——warp 是锁步的（分支发散会串行）、共享内存按 bank 编址（同 bank 不同地址串行）、显存访问要合并（不合并一次请求拆成多次）。

**有卡时**：

```bash
ncu --set full ./kernel            # 占用率、访存效率、bank conflict、stall reason
nsys profile ./app                 # 时间线：kernel 与拷贝各占多少
```

**判据**：任给一个朴素 kernel，能说出最可能的三处瓶颈并给出验证方式；改完之后指标确实朝预期移动。

## 3 常见误配

| 误配 | 后果 | 正确做法 |
|---|---|---|
| 把这三份当语法书通读 | 读完不会答任何追问 | 只读"编译器/运行时/硬件替你做了什么"那部分 |
| C++ 只背概念不跑 sanitizer | 讲不出证据，被追问"你见过吗"就退 | 每类 UB 至少留一个最小复现命令 |
| Python 用"解释执行"解释一切 | 分不清解释开销/GIL/分配/缓存 | 按瓶颈分项，用 `dis`/`tracemalloc` 定位 |
| CUDA 只看占用率 | 会被 stall reason 打穿 | 占用率 + stall 分布 + 访存效率一起看 |
| 把 `cs149` 的 roofline 当 CUDA 章的全部 | 少了 bank conflict 与同步这些"写代码才踩"的坑 | 并行理论归 `cs149`，工程坑归 `langs/cuda` |

## 4 跨项目追问

1. **「Python 慢，能不能用 C++ 扩展解决？」** → 要区分瓶颈在 Python 层（解释、对象开销）还是在算法/内存层；边界是 GIL 与跨语言调用开销。
2. **「你的 CUDA kernel 为什么在 A 卡快、B 卡慢？」** → 共享内存容量、SM 数、寄存器数不同；这也是 DSL（`cpu/compiler` 第 11 章）存在的理由。
3. **「`memory_order_relaxed` 什么时候够用？」** → 计数、统计类场景；但一旦有"发布数据"的语义就必须 release/acquire。
4. **「僵尸进程、孤儿进程、`wait` 的时机」** → 属于 `os/`，但 `cpp-basics` 的 RAII 与析构顺序会决定"资源到底什么时候放"。
5. **「为什么同样一份 C++ 代码在 ARM64 上偶发崩溃？」** → 弱内存模型与对齐要求，主战场在 `cpu/asm-link-arch` 第 10 章。

## 5 一句话收口

**C++ 考的是"编译器替你假设了什么"，Python 考的是"运行时替你做了什么"，CUDA 考的是"硬件在等什么"。** 三者共同的要求是：结论必须落到一次工具输出。
