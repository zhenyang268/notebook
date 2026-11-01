# algorithm · 一小时上手

> **前提**：C 的指针与 `struct` 熟练（这是硬门槛）。
> **这一小时的产出**：**白纸默写**出单链表逆置 + 非递归中序遍历 + 快排划分，三段都能编译。
> **不碰**：图算法、堆、KMP。

---

## 1 这一小时只做一件事

**用"默写"代替"看懂"。**

408 综合题要求的是**考场手写**，所以标准不是"我理解了"，而是"**15 分钟内能写对**"。
这一小时练三段最常考的代码。

---

## 2 最小可跑（50 分钟）

### 2.1 单链表逆置（15 分钟）

```c
// O(n) time, O(1) space
void Reverse(Node** head) {
    Node *prev = NULL, *cur = *head, *next = NULL;
    while (cur) {
        next = cur->next;   // ① 先存后继
        cur->next = prev;   // ② 再改指向
        prev = cur;         // ③ 前进
        cur = next;
    }
    *head = prev;
}
```

**命门在顺序**：**先接后继，再断前驱**。写反了直接断链。

### 2.2 非递归中序遍历（20 分钟）

```c
// O(n) time, O(h) space
void InOrder(Node* root) {
    Node* stack[100]; int top = 0;
    Node* p = root;
    while (p || top > 0) {
        while (p) { stack[top++] = p; p = p->left; }  // 一路向左
        p = stack[--top];                              // 弹栈
        visit(p);                                      // 访问
        p = p->right;                                  // 转右
    }
}
```

**命门**：`while (p || top > 0)` 两个条件缺一不可——`p` 为空但栈不空时还要继续弹。

### 2.3 快排划分（15 分钟）

```c
// 一次划分：返回枢轴最终位置
int Partition(int a[], int lo, int hi) {
    int pivot = a[lo];              // 取首元素（考场上够用）
    while (lo < hi) {
        while (lo < hi && a[hi] >= pivot) hi--;
        a[lo] = a[hi];
        while (lo < hi && a[lo] <= pivot) lo++;
        a[hi] = a[lo];
    }
    a[lo] = pivot;
    return lo;
}
```

**命门**：内层两个 `while` 都**必须先判 `lo < hi`**，否则越界。

---

## 3 三个核心难点

### 3.1 边界用例

每个操作都要想四种情况：**空表、单结点、首元素即满足、全相同元素**。
408 批卷常在这些地方扣分（"只写主干逻辑"是最常见的失分原因）。

### 3.2 不用 STL

`std::vector`、`std::stack`、`std::sort` **一律不能出现**。栈要自己用数组实现。

### 3.3 复杂度注释

每个函数头上写 `// O(n) time, O(1) space`。**这不是形式主义**——408 题常要求"并说明时间复杂度"，
写代码时就标好，考场上不用再想。

---

## 4 卡住怎么办

| 现象 | 原因 | 修法 |
|---|---|---|
| 逆置后链表断了 | 先改了 `cur->next` 再存 `next` | 严格按 ①②③ 顺序 |
| 中序死循环 | `p = p->right` 漏了 | 弹栈后必须转右 |
| 快排越界 | 内层 while 没判 `lo < hi` | 两个 while 都加 |
| 编译错：`Node` 未定义 | 没写 `typedef struct Node {...} Node;` | 先定义结构 |

---

## 5 这一小时之后

- 三段都能默写 → 去 `OUTLINE.md` 的 M2（树：层次遍历、线索化）。
- 还想练 → 把单链表逆置改成**递归版**，体会"栈在递归里"。

## 6 通向

| 你要什么 | 去哪 |
|---|---|
| 完整代码库 | `NOTES.md` |
| 四个里程碑 | `OUTLINE.md` |
| 链表考点 | `exam/408/ds/ROADMAP.md` |