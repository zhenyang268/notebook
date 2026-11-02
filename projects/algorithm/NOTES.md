# algorithm · 408 数据结构代码基座

> **工程线（兴趣向，非考试范围）**。这里是代码仓的体检、bug 记录、验证方法论。
> 408 的代码在考场上**不写模板也能拿分**（采分点是手算表格），所以这个仓的定位是
> **理解素材 + 反例库**，不是得分来源。考点对位只写 KP 号，正文在 `exam/408/ds/`。
> 代码真源：`~/develop/learning/learning-408/algorithm/`（独立子仓）。

## 对位考点（单向引用）

| 仓内模块 | 对应 KP |
|---|---|
| `tree/` 五种遍历与建树 | `408-DS-0402` 二叉树与遍历 |
| `tree/` 线索树 | `408-DS-0403` 线索二叉树 |
| `tree/` 哈夫曼、并查集 | `408-DS-0405` 哈夫曼树、`408-DS-0406` 并查集 |
| `RBTree.hpp` / `B+Tree.hpp` | `408-DS-0605` 红黑树、`408-DS-0606` B 树与 B+ 树 |
| `sort/` 快排与堆排 | `408-DS-0703` 交换排序、`408-DS-0704` 选择排序与堆 |
| `kmp.hpp` | `408-DS-0204` 串与 KMP |
| `leetcode/` 24 题 | 覆盖 `DS-02`–`DS-05` 各区 |

---

## 一、代码基座体检（原 `数据结构.md` §1）

## 1. 代码基座体检（2026-10-24 第二轮 · HEAD `7313598`）

> **本节已随远端代码重测**。旧结论（547 行代码）已全部作废，以下是 2026-10-24 07:30 拉取  
> `origin/master`（`7313598 test`，10 个新提交，+2884 行）后的**实测结果**。  
> 方法：逐文件 `wc -l` + `clang++ -std=c++17 -Wall -Wextra` 编译 + 实际运行 +  
> **独立校验器**（不依赖仓内自带 test 的断言）+ 随机对拍 + ASan 定位。  
> 编译器 Apple clang 17.0.0（arm64）。复现命令见 §1.6。

> ### ⚠️ 修复状态（2026-10-24 08:30 更新 · 本节 bug 已全部修完）
>
> 用户在体检后直接要求「直接改」，因此 §1.2–§1.5 记录的 **9 个 bug 现已全部修复并验证**。
> **下面各节保留的是「修复前的现场记录」** —— 这是反例素材，不要当成现状。
>
> | 编号 | 内容 | 状态 |
> |---|---|---|
> | BUG-1 | KMP `j=next[j]` 应为 `next[j-1]` | ✅ 已修（`AAB` 不再死循环；next 20000 组 + 搜索 30000 组全过） |
> | BUG-2 | 并查集 `unite` 缺同根守卫 | ✅ 已修（重复 unite 后 weight 2→2 不再翻倍） |
> | BUG-3 | 哈夫曼 `leaf` 未初始化 | ✅ 已修（加构造函数，`MallocScribble=1` 下也正确） |
> | BUG-4 | `tree.hpp` 缺 guard；`DFS/BFS` 无定义 | ✅ 已修（双重 include 零错误；两个函数已实现） |
> | BUG-5 | 红黑树 `deleteFixup` 空指针 SEGV | ✅ 已修（nil 自指 + CLRS 重写；原崩溃例 SURVIVED，ASan 零报错） |
> | BUG-6 | 红黑树删除破坏黑高/BST 序 | ✅ 已修（n≤7 全排列×全删除位 全过；压力 100+200+50 组全过） |
> | BUG-7 | B+ 树删除 container-overflow + 结构错 | ✅ 已修（合并时对合并后的结点也 refreshKeys；插入 2100 组 + 删除 900 组全过） |
> | BUG-8 | 快排全等元素退化（深度=n，n≈8万爆栈） | ✅ 已修（改三路划分；n=200000 全等 2ms）。**旧二路版保留为 `sort_binary()`** |
> | BUG-9 | `HeapSort` 建堆 O(n log n) 口径错 | ✅ 已修（改自底向上 O(n)、下标 0 起）。**旧版保留为 `buildByInsert()`** |
>
> **保留的两个反例**（故意不删）：`QuickSort::sort_binary()` 全等仍深度=n；`HeapSort::buildByInsert()` 仍是 O(n log n)。
> 演示「最坏 O(n²)」和「两种建堆代价」时用它们。
>
> 另外补了两个原来空着的实现：`createTree.cpp` 的**中+后**、**中+层**建树（三种还原现全部可用）。

### 1.1 代码量对比：从"几乎全空"到"骨架齐全"

| 模块                       | 上一轮     | 本轮                    | 变化          |
| ------------------------ | ------- | --------------------- | ----------- |
| 源码总量                     | 547 行   | **2959 行**            | ×5.4        |
| `sort/`                  | 14 行空壳  | **156 + 57 行**        | 堆排序 / 快排已实现 |
| `tree/RBTree/`           | **不存在** | **390 + 150 行**       | 红黑树从零到完整    |
| `tree/BPlusTree/`        | **不存在** | **271 + 107 行**       | B+ 树从零到完整   |
| `leetcode/`              | 空目录     | **24 个文件 / 约 1500 行** | 刷题库已建立      |
| `graph/`                 | 0 行     | **0 行**               | **仍是空的**    |
| `calculator/`            | 1 字节    | **1 字节**              | **仍是空的**    |
| `tree/ThreadBinaryTree/` | 0 行     | **0 行**               | **仍是空的**    |

**一句话结论**：**块6（树型查找）从"全无"变成"最强项"，块9（排序）从空壳变成可用，  
但块7（图）与块2（栈）仍然是零。** 上一轮体检里"三块全空"的判断，现在只剩两块。

### 1.2 十五个模块的逐文件实测

| 文件                                     | 行数        | 编译   | **实测结论**                                                  |
| -------------------------------------- | --------- | ---- | --------------------------------------------------------- |
| `tree/BinaryTree/tree.hpp`             | 36        | ✅    | 无 include guard；`DFSTraversal`/`BFSTraversal` **仍只声明无定义** |
| `tree/BinaryTree/traversalTree.cpp`    | 62        | ✅    | 前/中序栈迭代 + 后序递归，三序输出全对（未改动）                                |
| `tree/BinaryTree/createTree.cpp`       | 37        | ⚠️   | 前+中 ✅；**中+后 / 中+层仍空函数体**（`-Wreturn-type`）                 |
| `tree/HuffmanTree/huffmanTree.cpp`     | 140       | ✅    | WPL 892 / 231 正确；`leaf` 未初始化、O(n²) 选最小（**均未修**）           |
| `tree/Uiniset/uniset.hpp`              | 33        | ❌    | **仍不自包含**（`cout` 未声明，实例化即失败）                              |
| `tree/Uiniset/uniset.cpp`              | 59        | ✅    | 路径压缩 + 按 weight；**`unite` 仍缺同根守卫**（weight 翻倍）             |
| `tree/ThreadBinaryTree/threadTree.cpp` | **0**     | —    | 线索二叉树**仍未写**                                              |
| **`tree/RBTree/RBTree.hpp`**           | **390**   | ⚠️   | **新增**。插入 ✅ 100/100 组过；**删除大面积错 + 会 SEGV**；缺 `<cassert>`  |
| **`tree/BPlusTree/BPlustree.hpp`**     | **271**   | ✅    | **新增**。**插入 ✅ 2100/2100 组过**；**删除结构性错误 + 会 SIGBUS**       |
| **`sort/sort.hpp`**                    | **156**   | ✅    | **重写**。堆排序 ✅ 全过；快排 ✅ 正确但**全等元素 O(n²) 爆栈**                 |
| **`sort/test_sort.cpp`**               | **57**    | ✅    | **新增**。Heap / Quick 两个测试，12 个字符串全排序正确                     |
| `strkmp/kmp.cpp`                       | 76        | ✅    | **逻辑未改**：`build()` 第 32 行仍是 `j=next[j]`，`AAB` **仍死循环**    |
| `strkmp/kmp.hpp`                       | 24        | ✅    | **已修**：补了 `#include <vector>`（自包含问题解决）                    |
| `graph/graph.hpp` `graph/dij.cpp`      | **0 / 0** | —    | **仍全空**                                                   |
| `calculator/calculator.cpp`            | **1**     | —    | **仍是 1 字节**                                               |
| **`leetcode/` 24 个文件**                 | ~1500     | ✅ 全部 | **新增**。24 个全部编译通过；22 个可运行且有输出                             |

### 1.3 新发现的三个致命 bug（比上一轮严重得多）

> 下面三条**都不是"潜在 UB"，而是"已经实测出错/崩溃"**。判定方法写在每条里。

**BUG-5【致命·新增】红黑树 `deleteFixup` 空指针解引用（SEGV）**

- 位置：`tree/RBTree/RBTree.hpp:286` —— `if (b->l->color == BLACK && b->r->color == BLACK)`
- 根因：走到这一行时 `b`（兄弟结点）可能就是 `nil` 哨兵本身，而哨兵的 `l/r` 是 **`nullptr`**  
  （见 `Node` 构造：`l(nullptr), r(nullptr)`）。于是 `b->l->color` 直接解引用空指针。
- **实测复现（最小例）**：插入 `68 70 14 36 10 119 9 107 33 87 21 38 115 62 35 55 60 23 29 31 106 81 47 48 22`，  
  依次删 `14 47 31 48 107 21` → **第 6 步 `remove(21)` SIGSEGV**。
- ASan 栈：`RBTree.hpp:286 in deleteFixup` ← `RBTree.hpp:241 in deleteNode`
- 更广的结论：**删除压力测试第一轮就崩**（`tr 0` 的 `delete 1/3` 阶段 SIGSEGV，后续统计根本没打印出来）。

**BUG-6【致命·新增】红黑树删除后的树结构大面积不合性质**

即使不崩，性质也不成立。100 组随机删除的失败形态：

- `inorder mismatch: got 10 want 9` —— **删多了或删少了**
- `inorder mismatch: got 24 want 26` —— 反向，**丢了自己的 key**
- `black height mismatch: 5 vs 3` —— **黑高不等**（红黑树最核心的不变式被破坏）
- `BST right order violated` —— **中序不再有序**

> ⚠️ 对照：**插入 100 组全过**（五条性质逐条查：根黑 / 红叶不红 / 黑高相等 / BST 有序 / 父子指针一致）。  
> 所以结论要分清：**这棵红黑树的"建"是对的，"删"是错的。** 408 只考性质与旋转方向，不考写删除代码 ——  
> 但如果你拿它当"我实现过红黑树"的依据，**删除这块等于没做对**。

**BUG-7【致命·新增】B+ 树删除会崩（container-overflow → SIGBUS）**

- 现象一：`remove(3)` 直接 ASan 报 **container-overflow**（在 `std::shared_ptr::get` 上，  
  即对 `vector<shared_ptr>` 越界读到了已释放的槽位），进程 exit 134（ASan 下的 SIGBUS）。  
  **逐 key 实测（同一次插入 `5,3,7,1,9,2,8,4,6`，每次只删一个）**：  
  `remove(5)` 正常 / **`remove(3)` 崩** / `remove(7)` 正常 / `remove(1)` 正常 /  
  **`remove(9)` 崩** / `remove(2)` 正常 / **`remove(8)` 崩** / **`remove(4)` 崩** / `remove(6)` 正常  
  —— **9 个里 4 个崩**，且崩不崩取决于删哪个（说明是特定形状/位置的边界，不是普遍性失败）。
- 现象二：**树结构坏掉**，`children != keys + 1`。最小复现：  
  插入 `3 8 6 10 5 15 11 1`，删 `6` → 根结点变成 `keys={11} child(3)`（该是 2 个 child）。  
  拆开看是**合并时只 `erase` 了 key、没 `erase` 对应的 child 指针**（`BPlustree.hpp:225` 与 `:233` 两处）——  
  代码只删了一个，另一个漏了。
- **实测规模**：随机删一半，M=3 时 **98/200 组失败**、M=4 **94/200**、M=5 **72/200**。
- 现象三：**静默失败**。`M=3` 插入 `5,3,7,1,9,2,8,4,6` 后单删某个 key，出现  
  `删 3 → got=11 want=8`、`删 7 → got=0 want=8`、`删 1 → got=19 want=8` —— **数量完全失控**。
- 对照：**插入 2100/2100 组全过**（M=3/4/5/6 × 无重复 300 组 + 有重复 300 组，  
  逐条查：key 升序 / 叶子深度一致 / 阶数上下界 / 兄弟有序 / 中序等于排序后输入）。

### 1.4 上一轮 4 个 bug 的现状（3 个仍在，1 个已修）

| 编号    | 内容                                         | 现状                                    |
| ----- | ------------------------------------------ | ------------------------------------- |
| BUG-1 | KMP `build()` 的 `j=next[j]` 应为 `next[j-1]` | ✅ **已修**（见本节开头修复记录）。原状：`AAB` 死循环 |
| BUG-2 | 并查集 `unite` 缺同根守卫 → weight 翻倍              | ✅ **已修**。原状：`unite(0,1)` 两次 → weight 2→4 |
| BUG-3 | 哈夫曼内部结点 `leaf` 未初始化                        | ✅ **已修**（加构造函数）。原状：潜在 UB，本机跑不出 |
| BUG-4 | `tree.hpp` 缺 include guard；`DFS/BFS` 无定义   | ✅ **已修**（补 guard + 实现两个函数）          |
| —     | `uniset.hpp` 不自包含                          | ❌ **仍在**（`cout` 未声明）                  |
| —     | `kmp.hpp` 缺 `<vector>`                     | ✅ **已修**（补上了）                         |

### 1.5 排序的两个实测结论（**均已修，旧版保留为反例**）

> 以下是**修复前**的现场记录，保留作反例素材。现状见本节末尾「修复后」。

**堆排序 `HeapSort`：逻辑全对，但建堆口径错**

- 对拍 `std::sort`（n = 0/1/2/5/10/50/200 × 30 组 × 4 种数据形态含全等）= **210 组全过**。
- 两个容易踩的点**都处理对了**：①同一对象连调两次 `sort()` 不会残留上次的 `_priq`；  
  ②不修改输入 `vec`（值语义）。
- 但**与 408 口径有距离**：它用 `shared_ptr` + `_priq` 从下标 1 开始（`emplace_back(nullptr)` 占位）。  
  408 要的是**数组下标 0 起的原地堆排序**，且**建堆必须自底向上 O(n)**（这里是一个个 `insert` 插进去的，  
  等于 O(n log n)）。→ **不能直接当 408 堆排序的答案，会丢掉"建堆 O(n)"这个采分点。**

**快速排序 `QuickSort`：正确，但边界处理有 O(n²) 隐患**

- 对拍 210 组**全过**，值完全正确。
- **但全等元素会退化**：实测 n=1000/5000 时**递归深度 = n**（正好等于元素个数），  
  调用次数 ≈ 2n。（源码 `sort.hpp:128-129` 的 `while (l < r && *vec[r] >= *partition) r--;` 用 `>=`，  
  全等时 `r` 一路退到 `l`，划分成 `[1 个][n-1 个]`。）
- **后果**：n ≈ 80000 时**栈溢出 SIGSEGV**（实测门槛：60000 过、80000 崩）。
- **408 视角**：这个 bug 恰好是「快排最坏 O(n²)」的**真实物理证据** —— 比任何教材分析都直观。  

**修复后（2026-10-24 08:30）**

| | 改了什么 | 验证 |
|---|---|---|
| `QuickSort` | 二路划分 → **三路划分**（`< pivot / == pivot / > pivot`）+ 中位值枢轴 + 尾递归消除 | 全等 n=200000 **2ms、正确**（原版此处必崩）；对拍 210 组仍全过 |
| `HeapSort` | 逐次 insert 建堆 → **自底向上 O(n)**；下标 1 起 → **0 起**；`std::find` 删除 → 末元素顶替+下沉 | 对拍 210 组仍全过；`buildHeap()` 与 `buildByInsert()` 并存可对比 |
| 反例保留 | `QuickSort::sort_binary()`（旧二路，全等仍深度=n）<br>`HeapSort::buildByInsert()`（旧 O(n log n) 建堆） | **故意不删**，演示「最坏 O(n²)」与「两种建堆代价」时用它们 |

### 1.6 复现命令（换机器 / 下一轮体检先跑这一组）

> **这轮的校验器已存进仓里**：`algorithm/.verify/`（5 个程序 + 一份 README）。  
> 下次重测**直接跑它们**，不用重写。单独用法见 `algorithm/.verify/README.md`。

```bash
cd ~/develop/learning/learning-408/algorithm

# 0) 确认代码版本（本文件结论对应这个哈希）
git rev-parse --short HEAD        # 应为 7313598

# 1) 全量编译（-Wall -Wextra 必开）
clang++ -std=c++17 -Wall -Wextra -o /tmp/bt   tree/BinaryTree/*.cpp
clang++ -std=c++17 -Wall -Wextra -o /tmp/hf   tree/HuffmanTree/huffmanTree.cpp
clang++ -std=c++17 -Wall -Wextra -o /tmp/uf   tree/Uiniset/uniset.cpp
clang++ -std=c++17 -Wall -Wextra -o /tmp/kmp  strkmp/kmp.cpp
clang++ -std=c++17 -Wall -Wextra -o /tmp/srt  sort/test_sort.cpp
clang++ -std=c++17 -Wall -Wextra -o /tmp/rb   tree/RBTree/test_rbtree.cpp
clang++ -std=c++17 -Wall -Wextra -o /tmp/bp   tree/BPlusTree/test_BPlustree.cpp

# 2) 独立校验（.verify 五个 —— 这才是能挖出 bug 的那一套，仓内的 test 只跑 happy path）
clang++ -std=c++17 -O1 -include cassert -Itree/RBTree  .verify/rb_check2.cpp  -o /tmp/rbchk  && /tmp/rbchk
clang++ -std=c++17 -O1 -Itree/BPlusTree                .verify/bp_check2.cpp  -o /tmp/bpchk  && /tmp/bpchk
clang++ -std=c++17 -O1 -Isort                          .verify/sort_check.cpp -o /tmp/srtchk && /tmp/srtchk
clang++ -std=c++17 -Itree/BPlusTree                    .verify/bp_tree.cpp    -o /tmp/bptree && /tmp/bptree
clang++ -std=c++17 -O2                                 .verify/qs_depth.cpp   -o /tmp/qsd    && /tmp/qsd

# 3) 头文件自包含性（**必须带模板实例化**，否则模板体不检查，测不出问题）
printf '#include "tree/RBTree/RBTree.hpp"\ntemplate class RBTree<int>;\nint main(){}\n' > /tmp/p1.cpp
clang++ -std=c++17 -I. -c /tmp/p1.cpp -include cassert   # ← 去掉 -include cassert 就报 assert 未声明

# 4) B+ 树删除崩溃（ASan，最快的一条）
printf '#include "BPlustree.hpp"\nint main(){BPlusTree<int> t(3);for(int k:{5,3,7,1,9,2,8,4,6})t.insert(k);t.remove(3);}\n' > /tmp/p2.cpp
clang++ -std=c++17 -g -fsanitize=address -Itree/BPlusTree /tmp/p2.cpp -o /tmp/p2 && /tmp/p2
#   ← 预期 AddressSanitizer: container-overflow，exit 134
#   换成 remove(9) / remove(8) / remove(4) 同样崩；remove(5)/(7)/(1)/(2)/(6) 正常

# 5) 红黑树删除崩溃（ASan）—— 最小例
#   .verify/rb_min 的思路：插入 68 70 14 36 10 119 9 107 33 87 21 38 115 62 35 55 60 23 29 31 106 81 47 48 22
#   依次删 14 47 31 48 107 21 → 第 6 步 SEGV at RBTree.hpp:286

# 6) 快排全等退化（深度 = n 的证明）
#   用 n=1000/5000 的全等数组跑 QuickSort，观察递归深度与调用次数

# 7) 空文件清点（现在只剩两块）
wc -c calculator/calculator.cpp graph/*.cpp graph/*.hpp tree/ThreadBinaryTree/threadTree.cpp
```

> **踩坑记录（跑测试前必读）**：`leetcode/43_strMultiply.cpp` 的 `main` 里 `cin >>` 等输入，  
> **批量跑 leetcode 全部文件时必须先排除它**，否则整个脚本卡在 stdin 上（本轮踩过一次，需 SIGTERM 强杀）。

### 1.7 结论怎么用（仍然不是"先修 bug 再学"）

**这轮 bug 比上轮多且严重，但纪律不变：不预先修。** 理由分两层：

1. **考试收益**：408 不考"你能不能写出无 bug 的红黑树删除"。采分点是**手画旋转、手算分裂合并**。
2. **反例收益**：本轮新增的 5 个 bug，每一个都恰好对应一个考点 —— 见下表。

| bug                   | 对应考点                          | 怎么用                               |
| --------------------- | ----------------------------- | --------------------------------- |
| 红黑树 `deleteFixup` 空指针 | **兄弟是 NIL 的边界情况**             | 408 考"删除后如何调"时的经典陷阱；NIL 必须当作真结点处理 |
| 红黑树删除破坏黑高             | **五条性质逐条校验**                  | 拿它练"给一棵树，判断是不是红黑树"的题型             |
| B+ 树合并只删 key 不删 child | **`children = keys + 1` 不变式** | B 树/B+ 树一切"分裂/合并"题的核心校验式          |
| 快排全等 O(n²) + 爆栈       | **快排最坏 O(n²)**                | 比教材分析直观：深度真的等于 n                  |
| 堆排序逐个 insert 建堆       | **建堆 O(n) vs O(n log n)**     | 正好用来区分"建堆"与"插入建堆"两种代价             |


> **代码改动归你**（分工：agent 只做工程与文档，不写实现代码）。  
> 本文档负责把"哪里错、错在哪行、怎么验、对应哪个考点"钉死。

---

## 附一：树型查找讲义的代码对应（§7）

## 7. 与你代码的对应

| 你要练的 | 仓里能用的 | 注意 |
|---|---|---|
| B+ 树插入分裂 | `tree/BPlusTree/BPlustree.hpp` | 已修好，可对答案 |
| B+ 树删除借/并 | 同上 | 已修好（900 组测试过） |
| 红黑树五性质判断 | `.verify/rb_check2.cpp` 的 `walk()` | **这就是「逐条查五条性质」的代码版** |
| 红黑树插入调整 | `tree/RBTree/RBTree.hpp` 的 `insertFixup` | 已修好 |
| AVL 四旋转 | **仓里没有** | 需要自己写/手算 |
| B 树（非 B+） | **仓里没有** | 只考手算，不必写代码 |

> **纪律：B 树 / 图的代码不必写**。408 采分点在表格法手算。你已有的 B+ 树代码
> 足够用来「对答案」，不需要再写一个 B 树。

---

## 附二：树型查找讲义的数值校验记录

## 附：本文档的数值校验记录

所有数字都用代码/脚本实算过，不是凭记忆：

- m=3/4/5/6/100 的四个上下界 → `python3` 实算
- m=100 三层最多 999999 个关键字 → `99 × (1+100+10000)` 实算
- 高度公式 h ≤ log_⌈m/2⌉((n+1)/2)+1 → 代入 m=3,n=100 得 6.66；m=100,n=999999 得 4.35
- 3 阶 B+ 树插 1..8 的完整形状 → 用仓里 `BPlustree.hpp` 实际跑出来
- 红黑树插 10,20,30,15,25,5,1 的形状 → 用仓里 `RBTree.hpp` 实际跑出来
- 该树的五条性质与黑高 → 脚本逐路径验算，黑高全为 2，最长/最短 = 4/2

## 附三：外部排序讲义的数值校验记录

## 附：本文档的数值校验记录

| 项 | 结果 | 验证方式 |
|---|---|---|
| 1GB / 4KB 的总块数 | 262144 | python 实算 |
| m=1000 时各 k 的趟数与 I/O | k=2→10 趟/5242880；k=4→5 趟/2621440；k=8→4 趟；k=16→3 趟；k=64→2 趟 | python 实算 |
| 置换-选择平均段长倍数 | 内存 100→1.98×；500→1.90×；1000→1.82×；2000→1.67× | **独立 python 实现**，N=20000 随机数据实测 |
| 置换-选择 vs 段数减半对趟数的影响 | k=4 时：**有时省 1 趟、有时持平**（log 台阶效应） | 同上实测 |
| 经典题 9 段 k=3 | 补 0 虚段；哈夫曼 **223**；平衡归并 242；省 7.9% | python 逐次合并验算 |
| 虚段公式 (n=2..11, k=3/4) | 全表列出，与公式 `(k-1)-(n-1) mod (k-1)` 一致 | python 穷举 |
| B+ 树 4KB 块的分支因子 | 内部（8B key + 8B 指针）→ **255 个 key**；叶子（+100B 数据）→ 37 条记录 | python 实算 |
| 1 亿记录 B+ 树树高 | 分支因子 510 → **3 层** | python 实算 |

**注意**：§3.2 的置换-选择实现我第一版写错过（内存限制没生效，全部数据挤进一段），
修正后才得到 1.67~1.98× 的结果。**这类「看起来对但没生效」的 bug 只能靠实测发现** ——
和 §2 讲的不变量验证是同一个道理。
