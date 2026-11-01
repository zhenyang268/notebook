# CS231N · 一小时上手

> **前提**：NumPy 会广播与 `reshape`；知道链式法则。
> **这一小时的产出**：一个**向量化 softmax 分类器**，含解析梯度，与数值梯度对上。

---

## 1 这一小时只做一件事

**把 softmax + 交叉熵的梯度推出来，并用代码验证。**

因为它是所有深度学习的**最小可验证单元**：
```
线性打分 → softmax → 交叉熵 → 反向传播 → 参数更新
```
这一条链通了，后面加层、加卷积都是"复制这个模式"。

---

## 2 最小可跑（50 分钟）

### 2.1 前向（15 分钟）

```python
def softmax_loss(W, X, y, reg):
    # X: (N, D)  W: (D, C)  y: (N,) 整数标签
    scores = X @ W                       # (N, C)
    scores -= scores.max(axis=1, keepdims=True)   # 数值稳定
    exp = np.exp(scores)
    probs = exp / exp.sum(axis=1, keepdims=True)  # (N, C)
    N = X.shape[0]
    loss = -np.log(probs[np.arange(N), y]).mean() + reg * np.sum(W * W)
    return loss, probs
```

**两个命门**：
1. **减最大值**（防止 `exp` 溢出），不改变结果。
2. `probs[np.arange(N), y]` 是"取出每个样本的正确类概率"，**别写成双重循环**。

### 2.2 反向（25 分钟）

**结论：`dscores = probs; dscores[range(N), y] -= 1; dscores /= N`**

推导（只需三步）：
```
L = -log p_y,  p = softmax(s)
∂L/∂s_j = p_j - 1{j == y}          ← 这就是"概率减 one-hot"
∂L/∂W = Xᵀ · dscores + 2·reg·W
```

**为什么这么干净**：softmax 的雅可比与交叉熵的梯度**恰好抵消**，只剩 `p - y`。
这不是巧合，是"指数族 + 对数似然"的共轭性质。

### 2.3 验证（10 分钟）

```python
# 数值梯度
def numerical(W, X, y, reg, eps=1e-5):
    grad = np.zeros_like(W)
    for i in range(W.shape[0]):
        for j in range(W.shape[1]):
            W[i,j] += eps; l1,_ = softmax_loss(W,X,y,reg)
            W[i,j] -= 2*eps; l2,_ = softmax_loss(W,X,y,reg)
            W[i,j] += eps
            grad[i,j] = (l1-l2)/(2*eps)
    return grad
```
**判据**：`relative_error = |a-b| / max(1e-8, |a|+|b|)`，要求 **< 1e-7**。

---

## 3 三个核心难点

### 3.1 形状永远先写注释

```
X (N,D) · W (D,C) → scores (N,C) → probs (N,C) → loss 标量
dW 形状 = W 形状 (D,C)
```
**形状对了，90% 的 bug 不会发生。** 每次写函数先写这行注释。

### 3.2 数值稳定不是可选项

`exp(1000)` 溢出成 `inf`，`inf/inf` 变成 `nan`。
**减最大值是标准做法**，且数学上严格等价（分子分母同乘 $e^{-c}$）。

### 3.3 正则项只加到 loss 和 dW

`reg * sum(W*W)` 加到 loss；`2*reg*W` 加到 dW。**不要加到 scores 或 probs 里**。

---

## 4 卡住怎么办

| 现象 | 原因 | 修法 |
|---|---|---|
| loss = nan | 没减最大值 | `scores -= scores.max(1, keepdims=True)` |
| 梯度对不上 | 忘了 `/N` | `dscores /= N` |
| 相对误差 ~1e-3 | 用了 `float32` | 转 `float64` |
| 训练不收敛 | 学习率太大 | 从 `1e-3` 试起，看 loss 曲线 |

---

## 5 这一小时之后

- 通了 → 加一层隐藏层（ReLU），重复"前向-反向-梯度检查"的流程。
- 想深入 → `OUTLINE.md` 的 A2（卷积的 `im2col`）。

## 6 通向

| 你要什么 | 去哪 |
|---|---|
| 完整 3 个 assignment | `OUTLINE.md` |
| 详细实验记录 | `NOTES.md` |