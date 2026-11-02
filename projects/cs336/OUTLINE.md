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

## 五、面试怎么讲

**30 秒版本**

> 这个项目是把 decoder-only 语言模型的整条链路自己搭一遍：字节级 BPE、Transformer、预训练、SFT/DPO，以及带 KV cache 的推理，全程不调 `transformers`、`tiktoken`。卡点基本都在“错了也不容易报错”的地方，比如 mask 加在 softmax 前还是后、scale 有没有除 `√head_dim`、cache 的 position offset 从几开始、SFT 的 mask 有没有跟着标签一起右移。所以我的验证口径是一组可判定的检查：分词器对任意 UTF-8 往返一致，且在固定语料上逐 id 对齐参考实现；同一 prompt 开/关 cache 的 logits 在数值误差内相等；改未来 token 后，过去位置的 logits 逐位不变；对齐效果看留出偏好对的胜率，不看训练 loss。

**可能被追问的点**

1. **“你这分词器和 `tiktoken` 结果一样吗？”**
   → 考点：是否真理解 byte-level BPE 的确定性，而不是只会调包。
   → 答法：先说清一致的**口径**是“同一份语料、同一套预分词正则、逐 id 对照”，再说差异只可能出在四个地方：GPT-2 正则对缩写/数字/空白的切分方式、special token 是否先切分再走 BPE、是否做 Unicode 规范化、并列频次怎么 tie-break。我的实现里 tie-break 用 `(count, pair)` 的确定序，保证同一语料训两次得到同一份 merge 列表；编码时是**按 rank 升序反复合并当前序列里 rank 最小的相邻 pair**，不是最长匹配。不一致时用逐块 dump 字节对比来定位：byte-level 之后任何块都编得出来，所以差异必然在预分词或合并顺序，不会是“未登录词”。

2. **“为什么非得 byte-level？用字符级不行吗？”**
   → 考点：OOV 与可逆性的因果链。
   → 答法：byte-level 把词表基座钉死成 256 个字节，任意 UTF-8 字符串都可编码，没有 UNK，可逆性由“每步合并只是拼接、从不丢信息”保证。代价是非 ASCII 字符被拆成 3–4 个字节 token，序列变长。`byte-to-unicode` 只是一张双射表，把 0–255 里不可打印的部分映射到可见码位，方便放进 vocab 和调试，不改变语义。一个边界：decode 必须**整体**把 token 映射回字节串再 `utf-8` 解码，逐 token 单独解码遇到跨 token 的多字节字符会出替换符——所以往返测试要覆盖中文和 emoji。

3. **“mask 为什么必须加在 softmax 之前？”**
   → 考点：理解 `-inf` 与归一化的关系，而不是背 API。
   → 答法：如果在 softmax 之后乘 0/1 矩阵，被遮位置仍然进了分母，过去位置的输出会被未来 token 的数值稀释；某行全被遮时还会除出 NaN。正确做法是 softmax 前给未来位置加 `-inf`（实践里用 dtype 的极小值或 `-inf` + fp32 softmax），exp 后严格为 0。这条的验证不是“看起来对”，而是断言“改未来 token，过去位置 logits 逐位不变”。

4. **“除 `√d` 是为什么？不除会怎样？”**
   → 考点：缩放点积的方差分析，以及 `d` 到底指哪个维度。
   → 答法：q·k 是 `head_dim` 个近似独立项之和，分量方差为 1 时点积方差约等于 `head_dim`、标准差 `√head_dim`；不除的话 logits 量级随 head 维度增长，softmax 饱和到近似 one-hot，梯度趋近 0。常错点是把 `d` 写成 `d_model`，应该是 `head_dim`。

5. **“KV cache 缓存什么？position 从哪算？”**
   → 考点：增量解码的语义，而不是“加了个 cache 变快了”。
   → 答法：每层缓存该层已算过的 K 和 V，形状 `(B, n_head, T_past, head_dim)`，**不缓存 Q**，Q 只用当前步。prefill 一次喂完 prompt 建满缓存，decode 每步喂 1 个 token 并在 T 维 concat。position offset 就是 `T_past`：RoPE 的旋转角按绝对位置算，第二个 decode step 的位置是 `T_prompt` 不是 0。这条错了的典型症状是 shape 全对、输出变胡话。等价性就用“同 prompt，关 cache 与开 cache 跑最后位置 logits 比最大绝对误差”。

6. **“SFT 的 loss mask 怎么加？跟右移一位冲突吗？”**
   → 考点：shift 与 mask 的索引对齐。
   → 答法：`input_ids = tokens[:-1]`、`labels = tokens[1:]` 已经错开一位，所以 mask 必须做**同样的 shift**，含义是“预测第 t+1 个 token 时，只有第 t+1 个位置属于 assistant 段才计损失”。不 shift 直接乘是经典 bug，等价于教模型预测用户提问。另外交叉熵用 `reduction='none'` 乘 mask 后除以 `mask.sum()`，不能用 batch 元素总数当分母，否则短回答被长 prompt 稀释；special token 和 padding 位置一并置 0。

7. **“warmup 在解决什么问题？你怎么确定是它起的作用？”**
   → 考点：优化器状态 + 早期梯度，是否有对照意识。
   → 答法：Adam 的二阶矩在最初几步样本极少、估计噪声大，有效步长会异常大；叠上归一化层尺度参数初期梯度大，就容易在头几百步发散。warmup 是线性把 lr 从 0 拉到峰值，给 v 的估计时间收敛。验证要做**对照**而不是看曲线好看：同 seed 关掉 warmup 跑，观察前若干步的梯度全局范数与 loss 是否出现尖峰；再加上按全局范数的梯度裁剪（超阈值等比缩放），看尖峰是否被压住。这样“warmup 有用”才是可复现的结论。

8. **“DPO 为什么不用奖励模型？beta 是什么？”**
   → 考点：隐式奖励的推导，以及工程上的坑。
   → 答法：KL 约束下的 RLHF 目标有闭式最优策略，代回去后奖励可写成 `β·log(π_θ/π_ref)`，偏好概率就成了 `sigmoid(β·(Δchosen − Δrejected))` 的形式，于是直接用偏好对做二分类，不需要采样、不需要显式 RM。β 控制允许偏离参考模型的程度：大则保守、小则容易过拟合偏好数据。参考模型必须**冻结并置 eval**，否则 `logπ_ref` 也在动，闭式解的前提就没了。评价用留出提示上的成对胜率，同时看输出长度分布和复读率，因为胜率可以靠变长刷出来。

**别说什么**

- **别把「跑通了」说成「实现对了」。** loss 在降、能生成通顺句子，都不能证明 mask、scale、cache 是对的——忘除 `√d`、mask 错一位照样能训出能看的曲线。要说就说出你用哪条断言把语义钉住的。
- **别把框架名当原理讲。** 说“用了 RMSNorm / SwiGLU / RoPE”不算答案；被追问“pre-norm 和 post-norm 的梯度路径差在哪”“SwiGLU 的门控为什么有用”“RoPE 为什么表达相对位置”答不上来，比一开始就说“这块我按论文实现、原理细节还需要再确认”更露怯。
- **别报没测过的数字。** 没跑过 baseline 就不要说“提速 3 倍”“困惑度降 40%”；改成“提速要固定计时口径：是否含 prefill、是否跳过 warmup 步、是否 `torch.cuda.synchronize`，在这个口径下才谈倍数”。胜率同理，要说清判定方式和样本量。
- **别下笼统的完成断言。** “我全部实现了”一旦被追问到某个分支没做就崩；说清做到哪一步、哪块是留了接口没做（比如注意力只用 PyTorch 算子拼、没写 fused kernel；没做动态 batch、量化、beam search），边界清楚反而是加分项。
