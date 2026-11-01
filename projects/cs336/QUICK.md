# CS336 · 一小时上手

> **前提**：会 Python + 一点 PyTorch；知道 softmax 是什么。
> **这一小时的产出**：一个**能跑的 BPE tokenizer**（训练 + 编码 + 解码）。

---

## 1 这一小时只做一件事

**把文本变成整数序列，且能原样还原。**

为什么先做这个？因为 tokenizer 是**唯一不能用梯度优化的部分**——它必须精确、可逆、与参考实现逐 id 一致。
**它错了，后面全错**（loss 看着降，生成全是乱码）。

---

## 2 最小可跑（50 分钟）

### 2.1 训练 BPE（25 分钟）

```python
from collections import Counter

def train_bpe(text, vocab_size):
    # 1. 按字节初始化
    tokens = list(text.encode('utf-8'))       # 每个字节一个 token
    # 2. 反复找最高频相邻对，合并
    while len(set(tokens)) < vocab_size:      # 简化版：用 set 计唯一 token 数
        pairs = Counter(zip(tokens, tokens[1:]))
        if not pairs: break
        (a, b), _ = pairs.most_common(1)[0]
        # 3. 合并 a,b 为新 token（用一个递增的 id 表示）
        new = [a, b]                           # 实际实现要维护 merge 表
        tokens = merge(tokens, a, b)
    return build_merges(tokens)
```

**真实实现的两个关键**：
1. **按词预切分**（用正则把文本切成词/标点），再在词内做 BPE——否则跨词合并会出问题。
2. **维护 merge 表** `(a,b) -> new_id`，编码时**按 merge 顺序依次应用**。

### 2.2 编码（15 分钟）

```python
def encode(text, merges):
    ids = list(text.encode('utf-8'))
    for (a, b), new_id in merges:     # 按训练顺序
        i = 0
        out = []
        while i < len(ids):
            if i + 1 < len(ids) and ids[i] == a and ids[i+1] == b:
                out.append(new_id); i += 2
            else:
                out.append(ids[i]); i += 1
        ids = out
    return ids
```

**命门**：merge 必须**按训练时的先后顺序**应用，不能乱序（否则结果不同）。

### 2.3 验证（10 分钟）

```python
assert decode(encode(s, merges), merges) == s      # 可逆
```
再拿同一段文本，与 `tiktoken` 的 id 序列**逐项比对**（不等就是实现有偏差）。

---

## 3 三个核心难点

### 3.1 预切分决定一切

不做预切分，BPE 会把"the cat"里的 "e c" 合并，导致**同一个词在不同上下文里被切成不同 token**。
标准做法：先用正则切成 `\w+|\s+|[^\w\s]+`，**在每段内部做 BPE**。

### 3.2 字节级 vs 字符级

字节级（UTF-8）的好处：**任何文本都能编码，不会 OOV**。代价：中文一个字符占 3 字节，序列变长。

### 3.3 可逆性是硬判据

`decode(encode(s)) == s` 必须**严格相等**（不是"差不多"）。这是 tokenizer 唯一的正确性标准。

---

## 4 卡住怎么办

| 现象 | 原因 | 修法 |
|---|---|---|
| 解码出乱码 | merge 顺序错了 | 按训练顺序重放 |
| 中文变很多 token | 字节级 + 没做中文预切分 | 加中文词表或按字符切 |
| 与 tiktoken 不一致 | 预切分正则不同 | 对齐参考实现的正则 |

---

## 5 这一小时之后

- 通了 → 进 M2（Transformer）：先写**单头注意力**，再扩成多头。
- 想验证 → 用同一份语料训练两个不同 `vocab_size`，看压缩率变化。

## 6 通向

| 你要什么 | 去哪 |
|---|---|
| 完整里程碑 | `OUTLINE.md` |
| 详细实验记录 | `NOTES.md` |