## 一、它在做什么

本项目要做的事很具体：把一条 decoder-only 语言模型的完整链路，从原始文本一直搭到能按指令回答的小模型，中间不调用 `transformers`、`tokenizers`、`tiktoken` 这类现成组件。输入是纯文本语料：预训练用短篇故事或通用文本，对齐用指令-回答对和偏好对；输出包括三样东西：一个自己训练出来的字节级 BPE 分词器（词表与合并规则）、一个 Transformer 检查点（含配置与训练日志）、一个能加载检查点做逐 token 生成的推理脚本。验收不看“模型多大”，而看四件事：分词器对任意 UTF-8 文本可逆，且在固定样本上的 token id 序列与参考实现一致；模型前向满足形状契约，关闭缓存与开启缓存时短序列 logits 等价；预训练损失稳定下降，生成的短句语法通顺；经过 SFT/DPO 后，在留出指令集上的偏好胜率相对基座有可测提升。规模控制在单卡可训，目标是“链路完整、数值可信”，不是刷榜。

## 二、为什么这样做（功能设计）

**1. 分词器：替换掉 `tiktoken`/`tokenizers`，接口放在“文本 ↔ id”这一层。** 自己实现 byte-level BPE：先把文本按 GPT-2 风格正则切成预分词块，再把每块转成 UTF-8 字节并用 byte-to-unicode 映射成可见字符，统计相邻 pair、按频次合并、把合并规则按 rank 固定下来；编码时按 rank 从小到大应用合并，遇到未登录字符回退到字节。替换点不在训练脚本里，而在 `encode/decode` 与 `train_bpe` 的函数边界：上层只看见 `list[int]`，看不见 Rust 或缓存。不可靠性主要来自 Unicode 规范化、正则对空白/标点的切分、special token 边界和合并时的并列频次；对策是字节回退保证任意字符串可编码、合并排序用确定性 tie-break、special token 先切分再走 BPE、用固定语料做逐 id 对照和往返校验。更简单的做法是直接装 `tiktoken`，代价是合并循环、缓存和字节映射全部被藏起来，后面排查“为什么同一个词 id 不同”时没有抓手。

**2. 模型：替换掉 `nn.Transformer`/`nn.MultiheadAttention`，接口放在 `forward(tokens, kv_cache=None) -> logits`。** 内部自己写 QKV 投影、多头 reshape、`QK^T/√d`、因果 mask、softmax、输出投影；结构采用 pre-norm 的 RMSNorm、RoPE、SwiGLU、残差和 tied embedding，整体是一个现代 Llama 式 decoder，而不是 2017 年原版。形状契约写死：输入 `(B,T)` 整数，输出 `(B,T,V)`；每层缓存是 `(B, n_head, T, head_dim)` 的 K/V 列表。为什么不用库：库会把 mask 加在 softmax 前还是后、scale 除不除、cache 的 position offset 怎么处理全部隐藏，而这三处正是语言模型最容易错的地方。代价是自己写的注意力更慢、显存更粗，所以只在接口层保留“以后可替换成 fused attention”的余地，不在第一版追求吞吐。

**3. 数据：把文本压成扁平 token 流，而不是一条条样本。** 预训练数据先编码成 `int32` 的 `tokens.bin`，训练时用 memmap 随机取 `(B,T)` 窗口，标签是输入右移一位；SFT 阶段才引入对话模板和 loss mask，只对 assistant 段计损失。不可靠性来自重复文本、文档边界和特殊 token：用 EOD token 切文档、去重、固定随机种子采样来压。更简单的做法是每条样本单独 padding，代价是浪费大量算力，而且 padding 位置如果忘了 mask 会直接教模型生成填充符。

**4. 训练：用 warmup + cosine、梯度裁剪和 AdamW 把“能训”变成“稳定能训”。** 语言模型早期梯度大，恒定学习率容易在头几百步发散；warmup 把更新幅度压小，cosine 让后期细调；裁剪处理偶发尖峰。数值上以 fp32 为基准，bf16 只作为吞吐选项，不碰 fp16 的 loss scaling，避免教学阶段被数值问题干扰。更简单的做法是“Adam + 固定 lr”，代价是要花更多时间调参，而且不同规模下不可复用。

**5. 对齐：SFT 之后接 DPO，不碰 PPO/GRPO。** SFT 用指令-回答对做 next-token，但只对回答段计损失；DPO 用偏好对，冻结一个参考模型，直接优化“chosen 相对 rejected 的隐式奖励差”。接口在“对话模板 + 损失函数”这一层：模型本身不变，变的是数据组织和 loss。为什么不用 RLHF：奖励模型 + 采样 + PPO 的链路太长，且采样方差会掩盖实现错误；DPO 是静态分类式目标，容易复现。代价是 DPO 对 beta、长度偏置和数据质量敏感，所以验收必须用留出 prompt 的胜率，而不是训练集 loss。

**6. 推理：KV cache 是一等模块，不是事后优化。** 生成分 prefill 和 decode 两段：prefill 吃完整 prompt 建缓存，decode 每步只喂一个新 token，把历史 K/V 接上。采样支持 temperature、top-k、top-p。更简单的做法是每步重算全序列，代价是生成长度一长就平方级变慢；cache 的代价是状态变多，必须用“短序列 cache 输出与无 cache 输出一致”来固定语义。

## 三、章节大纲

1. **工程底座与数值契约**：配置 dataclass、随机种子、日志、形状断言、设备管理。知识点：可复现性、张量形状、配置与代码分离。做完能验证：同一 seed 下两次前向的 loss 一致，所有模块的输入输出形状符合契约。
2. **字节级 BPE 分词器**：UTF-8 字节、byte-to-unicode、GPT-2 正则预分词、pair 统计与合并、special token。知识点：BPE 训练算法、rank 编码、可逆性。做完能验证：任意 UTF-8 文本 encode/decode 往返；固定语料上的 token id 与参考实现逐 id 一致。
3. **数据管线与训练样本**：token bin 落盘、memmap、随机窗口、文档边界 EOD、SFT 的 loss mask。知识点：扁平 token 流、采样、padding 与 mask。做完能验证：batch 形状正确；跨文档样本不会把不同文档拼成一句；SFT 只对回答段回传梯度。
4. **Transformer 骨架**：Embedding、Block 堆叠、pre-norm 残差、LM Head、初始化。知识点：残差流、参数共享、深层初始化。做完能验证：前向输出 `(B,T,V)`；小批量过拟合到接近零损失；参数量与配置吻合。
5. **注意力与位置编码**：QKV、多头 reshape、`QK^T/√d`、因果 mask、softmax、RoPE、KV cache 接口。知识点：缩放点积注意力、因果性、旋转位置编码、缓存增量。做完能验证：改未来 token 不影响过去 logits；短序列 cache 与无 cache 的 logits 在数值误差内一致。
6. **现代组件与训练稳定性**：RMSNorm、SwiGLU、weight tying、AdamW、warmup+cosine、梯度裁剪、bf16 对照。知识点：归一化位置、激活函数、优化器超参、混合精度。做完能验证：训练若干千步不出现 NaN；loss 曲线无持续发散；关掉 warmup 能看到早期尖峰。
7. **小规模预训练与评测**：TinyStories 级数据、交叉熵/困惑度、生成样例、采样策略。知识点：next-token 目标、评测集划分、生成质量判断。做完能验证：模型能生成语法通顺的短句；留出集困惑度随训练下降；温度/top-p 改变输出多样性。
8. **推理优化与生成边界**：prefill/decode、KV cache 管理、top-k/top-p、批处理边界。知识点：自回归解码、缓存生命周期、采样。做完能验证：开启 cache 后生成速度明显高于逐步重算；固定 prompt 与 seed 下输出可复现。
9. **对齐：SFT 与 DPO**：对话模板、SFT loss mask、偏好对构造、参考模型冻结、DPO loss、beta。知识点：指令微调、偏好优化、隐式奖励。做完能验证：SFT 后模型能按模板回答；DPO 后留出偏好对的胜率相对 SFT 基座提升，且不出现明显长度堆叠或复读。

## 四、不做什么

边界写清：

- 不做分布式训练、DDP/ZeRO、多卡通信；单卡能跑通是前提。
- 不手写 CUDA/FlashAttention kernel；注意力先用 PyTorch 算子拼，允许后续替换 fused 实现，但不作为验收项。
- 不做完整 RLHF：不训练奖励模型、不写 PPO/GRPO；对齐上限是 SFT + DPO。
- 不追求 SOTA 困惑度或大规模数据清洗；不做 Common Crawl 全流程，数据以小型公开语料为主。
- 不做生产级 serving：不要求动态批处理、量化、投机解码、beam search；采样到 top-p 即可。
- 实现自由度：层数、宽度、头数、词表大小、是否 weight tying、是否用 bf16，均可按算力调整；但 `encode/decode` 的可逆性、`forward` 的形状契约、cache 等价性、loss 只对目标段计算这四条不能变。
- 常见跑偏：用 `transformers` 的 tokenizer 或模型“省事”；标签忘了右移一位；mask 加在 softmax 之后；忘了除 `√d`；KV cache 的 position 从 0 重新开始；DPO 的参考模型没有冻结；在训练 prompt
