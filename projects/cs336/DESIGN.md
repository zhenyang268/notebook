# CS336 · 语言模型从零实现 · 设计文档

> 本文是该项目的设计说明，不是教程。
> 大纲见 `OUTLINE.md`，一小时上手见 `QUICK.md`，详细记录见 `NOTES.md`。

## 一、定位与边界

本项目以尽量少的依赖复现 decoder-only 语言模型的完整链路：字节级 BPE、Transformer、训练循环、KV cache 推理。解决“知道公式但没写过”的问题：张量形状、因果 mask、位置编码、缓存增量全部自己实现，并用测试固定数值语义。

不解决：分布式训练、RLHF/对齐、SOTA 困惑度、CUDA kernel、大规模数据清洗。与相邻项目分工：`nanoGPT` 偏训练脚本复现，`minGPT` 偏教学；本项目把分词器与 KV cache 作为一等模块，强调可测试性与数值等价。

## 二、整体架构

模块划分：

- `tokenizer`：`train_bpe(corpus, vocab_size)` 产出 `vocab.json`、`merges.txt`；`encode(str) -> list[int]`；`decode(list[int]) -> str`。
- `model`：`Transformer(cfg)` 内含 Embedding、$N$ 个 Block（RMSNorm、CausalMHA、RoPE、SwiGLU）、LM Head；`forward(tokens, kv_cache=None) -> logits`。
- `train`：DataLoader 产出 `(B,T)` int64；损失为 `cross_entropy(logits[:, :-1], tokens[:, 1:])`；优化器、调度器、checkpoint。
- `infer`：`generate(prompt, max_new_tokens, cache)` 逐 token 解码。
- `common`：配置、日志、随机种子、路径。

调用方向：`config -> tokenizer -> dataset -> model -> train -> checkpoint -> infer`。`infer` 复用 `model` 与 `tokenizer`，不反向依赖 `train`。

## 三、技术选型与理由

- Python 3.11 + PyTorch 2.x：自动微分与 GPU 张量成熟；不用 JAX 是避免函数式 purity 与静态 shape 的额外成本；不用 NumPy 是因为无 GPU 与自动求导。
- 不引入 `transformers`、`tokenizers`、`tiktoken`：核心目标是从零；Rust 实现会隐藏合并循环与缓存细节。
- 预切分用 `regex` 而非标准库 `re`：GPT-2 正则含 `\p{L}`、`\p{N}`，标准库不支持 Unicode 属性。
- pytest：便于参数化数值用例与近似断言。
- 配置用 dataclass + JSON：避免 Hydra 的额外抽象；日志用 CSV/TensorBoard，不依赖云端。
- 精度以 fp32 为数值基准，bf16 仅在支持硬件上做吞吐对照；不开 fp16 以免 loss scaling 干扰教学。

## 四、数据流

原始文本 → 可选规范化 → BPE 训练得到 `vocab.json`、`merges.txt` → 编码为 `int32` 数组落盘 `tokens.bin` → 训练按 `(B,T)` 取样，输入 `tokens[:, :-1]`，标签 `tokens[:, 1:]` → Embedding `(B,T,d)` → 每层：RMSNorm → QKV `(B,T,3d)` → reshape `(B,H,T,d_h)` → 加 RoPE → 因果 mask → softmax → `(B,T,d)` → 残差 → SwiGLU `(B,T,4d)` → 残差 → 最终 RMSNorm → LM Head `(B,T,V)` → 交叉熵标量 → 反向 → AdamW。

推理：prefill 一次写入 K/V cache `(B,H,T,d_h)`；decode 每步只算新 token，cache 长度递增。

## 五、章节目录与知识点映射

| 章 | 内容 | 涉及的知识点 | 与考纲或前置项目的关系 |
|---|---|---|---|
| 1 | BPE 训练 | 字节级合并、pair 统计、增量计数、字节回退 | 前置：哈希表与堆；考纲：时间复杂度分析 |
| 2 | 分词器编解码 | GPT-2 预切分正则、特殊 token、UTF-8 解码、round-trip 不变式 | 前置：字符串处理 |
| 3 | 注意力 | 缩放点积、因果 mask、多头拆分、$1/\sqrt{d_h}$ 缩放 | 考纲：矩阵乘法复杂度 |
| 4 | 位置编码 | RoPE 旋转矩阵、相对位置、分半/交错约定、外推 | 前置：线性代数 |
| 5 | FFN 与归一化 | SwiGLU 门控、RMSNorm、pre-norm 残差、初始化尺度 | 前置：概率与优化 |
| 6 | 模型组装 | embedding、权重绑定、参数量估计、形状推导 | 前置：PyTorch `nn.Module` |
| 7 | 训练循环 | 交叉熵、梯度裁剪、梯度累积、混合精度 | 考纲：数值稳定性 |
| 8 | 优化器与调度 | AdamW 解耦权重衰减、偏差修正、warmup+cosine | 前置：凸优化基础 |
| 9 | KV cache | prefill/decode、增量注意力、显存 $O(BHLTd_h)$、位置偏移 | 前置：注意力实现 |
| 10 | 小规模训练与评测 | 单批过拟合、困惑度、checkpoint、采样 | 前置：实验方法 |

## 六、验收判据

- 分词器：10k 条随机 Unicode 字符串 `encode -> decode` 完全一致，10000/10000；特殊 token 不被合并；10MB 语料训练 `vocab=16k` 单核 ≤ 10 min。
- 数值：注意力与手写三重循环参考实现最大绝对误差 < 1e-5（fp32，$T=16$）；数值梯度与解析梯度相对误差 < 1e-4（10 个随机参数）。
- KV cache：`B=8`、prompt 128、生成 256 token，相对无 cache 加速比 ≥ 5x；输出 logits 最大绝对误差 < 1e-4；显存增量与 $O(BHLTd_h)$ 估算误差 < 10%。
- 训练：单 batch 过拟合 200 步内 loss < 0.1；10M 参数模型 2000 步后验证困惑度低于初始值 40% 以上。
- 测试：pytest 16/16 通过，覆盖 tokenizer、attention、cache、optimizer。

## 七、风险与已知坑

- BPE 增量 pair 计数删除旧 pair 时容易漏减，合并顺序会错；用全量重算作对照测试。
- 因果 mask 方向与广播易错；全掩码行会产生 NaN，需行级保护。
- RoPE 分半与交错两种维度排列不通用，训练与 cache 必须同一约定。
- 权重绑定与初始化尺度不匹配会导致 logits 爆炸。
- AdamW 对 bias、LayerNorm 参数不做 weight decay，容易漏。
- warmup+cosine 的 step 计数与梯度累积耦合，实际曲线会偏移。
- KV cache 的 position offset 与 mask 长度不一致，decode 第一步就错。
- 小数据训练易过拟合，验证集与训练集同源会泄漏。

## 八、与其他项目的关系

前置：PyTorch 基础、线性代数、概率。可复用模块：`model` 的 attention/RMSNorm 可迁移到多模态项目；`tokenizer` 可独立用于数据管道；`train` 的调度器与 checkpoint 可复用到微调项目。后续：分布式训练、量化推理、对齐。不依赖 `transformers`，但可作为数值对照。
