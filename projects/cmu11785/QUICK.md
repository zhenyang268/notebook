# 11-785 · 一小时上手

> **前提**：NumPy 熟练；知道链式法则。
> **这一小时的产出**：一个**手写反向传播的两层 MLP**（numpy，不用 autograd），在 XOR 上收敛。

---

## 1 这一小时只做一件事

**手写一次完整的反向传播，不用任何自动微分。**

因为调库的人永远不知道梯度从哪来。手写一遍，`loss.backward()` 就不再是魔法。

---

## 2 最小可跑（50 分钟）

### 2.1 前向（15 分钟）

```python
import numpy as np

def forward(X, W1, b1, W2, b2):
    # X:(N,2) W1:(2,H) W2:(H,1)
    z1 = X @ W1 + b1          # (N,H)
    a1 = np.maximum(0, z1)    # ReLU
    z2 = a1 @ W2 + b2         # (N,1)
    return z1, a1, z2
```

### 2.2 反向（25 分钟）—— 手动推

```
loss = mean((z2 - y)^2)                      # 平方损失，最直观
∂loss/∂z2 = 2*(z2 - y)/N                     # (N,1)
∂loss/∂W2 = a1ᵀ · dz2                        # (H,1)
∂loss/∂b2 = sum(dz2, axis=0)
dz1 = (dz2 @ W2ᵀ) * (z1 > 0)                 # ReLU 的导数：>0 才传
∂loss/∂W1 = Xᵀ · dz1                         # (2,H)
∂loss/∂b1 = sum(dz1, axis=0)
```

```python
def backward(X, y, z1, a1, z2, W2):
    N = X.shape[0]
    dz2 = 2*(z2 - y)/N
    dW2 = a1.T @ dz2;  db2 = dz2.sum(0)
    dz1 = (dz2 @ W2.T) * (z1 > 0)
    dW1 = X.T @ dz1;   db1 = dz1.sum(0)
    return dW1, db1, dW2, db2
```

### 2.3 验证（10 分钟）

```python
# 数值梯度对比某一个 W1[i,j]
eps = 1e-6
W1[i,j] += eps; l1 = loss(...)
W1[i,j] -= 2*eps; l2 = loss(...)
W1[i,j] += eps
num = (l1 - l2)/(2*eps)
assert abs(num - dW1[i,j]) < 1e-6
```

---

## 3 三个核心难点

### 3.1 梯度是"累加"不是"覆盖"

一个参数被多条路径用到时，梯度是**所有路径贡献之和**。
代码里表现为 `+=`（PyTorch 也是 `grad += ...`）。**写成 `=` 会丢一半梯度**。

### 3.2 ReLU 的导数就是"开关"

`(z1 > 0)` 是 0/1 掩码。**负半轴梯度为 0**，这就是"死亡 ReLU"的来源。

### 3.3 形状先写注释

```
X(N,2)·W1(2,H) → z1(N,H) → a1(N,H) → z2(N,1)
dW1 形状 = W1 形状 = (2,H)
```
**形状对了，`transpose` 就不会放错位置**（这是反向传播最常见的 bug）。

---

## 4 卡住怎么办

| 现象 | 原因 | 修法 |
|---|---|---|
| 梯度对不上 | `dz1` 忘了乘 ReLU 掩码 | 加 `* (z1 > 0)` |
| loss 不降 | 学习率太大或没归一化 | 输入减均值除标准差；lr 从 1e-2 试 |
| loss 变 nan | 学习率过大导致爆炸 | 降到 1e-3，加梯度裁剪 |
| 形状报错 | `W2ᵀ` 写成 `W2` | 按形状注释逐项核对 |

---

## 5 这一小时之后

- 通了 → 加第二隐藏层，验证"层数增加但梯度仍能传播"。
- 想深入 → `OUTLINE.md` 的 HW3（RNN + CTC）。

## 6 通向

| 你要什么 | 去哪 |
|---|---|
| 完整 5 个 HW | `OUTLINE.md` |
| 详细实验记录 | `NOTES.md` |