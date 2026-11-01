# CS231N · 视觉识别

> **工程线（兴趣向，非考试范围）**。本文件不承担复习任务。
> 斯坦福 CS231N（2026 版口径）：CNN、Transformer、自监督、扩散。
>
> **单向引用约定**：本文提到考点时**只写 KP 号与考点名**，不复制 `exam/` 的正文；
> `exam/` 的文件里也不出现本文件的工程名。两边互不依赖，只共享主键。

## 对位考点（单向引用）

| 本文段落 | 对应 KP |
|---|---|
| — | 与 408 初试**零重叠**，初试前不看 |

---

## 0 怎么读这个文件

- §1 给出**课程定位、历史地位与作业版本现状**——先看清"cs231n 是什么、手里的版本是哪年的"，别拿 2017 年的攻略复习 2026 年的作业。
- §2 是**全局地图 + 关键路径**，回答"三个作业 + 18 讲分别覆盖什么、按什么顺序过"。
- §3 是**贯穿全课程的设计理念**——**这是整个项目最值钱的部分，别跳过**。cs231n 的作业语言从 numpy 换到 PyTorch、模型从 CNN 换到 Transformer/扩散，但"手工推梯度、框架只是放大器"这个底座从不换。
- §4 每个作业一个模板：**抓重点 → 关键路径 → 细节与易错点 → 设计理念**，是**大纲级**。
- §5–§7 是**逐块展开**：真实函数签名（来自 2026 版 zip 解包核对）、数据流、伪代码、逐条易错点。读到具体动手那一节时再回来翻。
- §8 是**讲座层专题补全**：saliency/fooling/风格迁移/GAN/VAE 这些 2025 起已移出作业、但讲座仍在讲、面试仍在考的内容。
- §9 是**自测验收清单**；§10 是**求职视角**（岗位地图、面试真题对照、简历写法、补课路线）——要拿这门课找工作就直接从 §10 倒推。
- §11 是**执行方案**：考研初试 2026-12 前零动手投入的定位与初试后的动手排序。

---

## 1 定位与现状

### 1.1 一句话

> **CS231n 教的不是"怎么用 PyTorch 训模型"，而是"在框架替你求导之前，一个深度网络里到底发生了什么"——先把反向传播当手工微积分做一遍，再把方向盘交给 autograd。**

2017 年代的版本标题更直白：*Convolutional Neural Networks for Visual Recognition*。2024 年起课程更名为 *Deep Learning for Computer Vision*，作业也随之从"CNN 时代经典"换血为"Transformer / 自监督 / 扩散"——但前两个作业的手工反传内核一直没变。

### 1.2 历史地位（一句话版）

Fei-Fei Li 创立此课（她也是 ImageNet 的缔造者，ImageNet 正是这门课叙事的起点）；Andrej Karpathy 2015-2017 年主讲期间的讲课视频与其执笔的 `cs231n.github.io` notes 是**整个深度学习社区公认的入门传世材料**——后来他的 zero-to-hero 系列与 nanoGPT 是这条脉络的延续。Justin Johnson（现 Michigan）接棒后主讲多年，2026 版由 Fei-Fei Li / Ehsan Adeli / Justin Johnson / Zane Durante / Tiange Xiang 联合执教。课程主页明确写着：往年录播在 YouTube 公开（课程官方 playlist）。

### 1.3 本地代码现状（事实）

| 事项 | 状态 |
|---|---|
| `~/develop/learning/learning-408/` 下 | **没有任何 cs231n 相关目录或仓库** |
| 结论 | 本笔记定位 = **纯"指导 + 重建提纲"**。文中不引用任何"我的实现"；要动手时从官方 zip 起步（见 §11） |
| 官方 starter 获取 | `https://cs231n.github.io/assignments/2026/assignment{1,2,3}.zip`（2026 官方 handout 给的就是 zip，官方工作流是 Google Colab） |
| GitHub | **注意：`github.com/cs231n` org 下已无 assignment1/2/3 仓**（GitHub API 核实，org 只剩 `cs231n.github.io` 与 `gcloud`）。网上能搜到的 `cs231n/assignment1` 等都是历史镜像或他人 fork，内容是 2017-2020 年代版本——**版本与 2026 官方 zip 对不上**，只适合当旧专题素材（SVM / 风格迁移 / GAN），不适合当"最新版作业" |

### 1.4 作业版本年表（动手前必须先锁定版本）

cs231n 的 A1/A2 多年稳定、A3 逐年变是社区常识，但**近几年连 A1/A2 也在动**。以下年表来自官方各年 handout 页面逐年抓取比对：

| 作业 | 2023 / 2024 版 | 2025 / 2026 版（现行） | 变化 |
|---|---|---|---|
| A1 | Q1 kNN、Q2 **SVM**、Q3 Softmax、Q4 two-layer net、Q5 image features | Q1 kNN、Q2 **Softmax（SVM 已删）**、Q3 two-layer net、Q4 image features、Q5 **FullyConnectedNets（自 A2 移入）** | SVM notebook 移除；任意深度 FC 网从 A2 前移到 A1 |
| A2 | Q1 **Multi-Layer FC Nets**、Q2 BatchNorm、Q3 Dropout、Q4 ConvNets、Q5 PyTorch on CIFAR-10 | Q1 BatchNorm(+LayerNorm)、Q2 Dropout、Q3 ConvNets、Q4 PyTorch on CIFAR-10、Q5 **RNN Image Captioning（自 A3 移入，PyTorch 实现）** | FC nets 移走；RNN captioning 进入 A2，且从 numpy 改为"PyTorch 里手写 `_numpy` 后缀函数" |
| A3 | 2024 版：Q1 RNN captioning、Q2 Transformer captioning、Q3 **GAN**、Q4 Self-Supervised Learning | Q1 **Transformer captioning**、Q2 **Self-Supervised Learning (SimCLR)**、Q3 **DDPM（扩散）**、Q4 **CLIP and DINO** | **A3 整体换血**：RNN captioning 移到 A2，GAN 出局，DDPM 进场，CLIP/DINO 成为新宠。风格迁移 / 网络可视化 / fooling image 在 2023 及更早版本出现过，2025 起已完全不在作业里 |

两个推论：

1. **看旧攻略要倒扣**：2017-2020 的经典攻略里 "A3 = LSTM captioning + saliency + style transfer + GAN" 的印象，对 2026 版全部失效；那些主题降级为讲座内容 + 面试素材（本文件 §8 单独补全）。
2. **SVM 虽从作业删除，但没从课程删除**：`linear-classify` notes 仍完整讲 hinge loss，2026 版公共库 `layers.py` 里 `svm_loss()` 函数也还在（解包核实），只是不再配 notebook。面试里 hinge loss 与交叉熵的对比仍是高频题（§10.2）。

**旧攻略 → 2026 版映射表**（手里有旧中文攻略时按此换算）：

| 旧攻略里的章节 | 2026 版去处 |
|---|---|
| A1 svm.ipynb | 已删——公式看 `linear-classify` notes，代码可对照库里 `svm_loss()`；面试题仍在（§10.2） |
| A2 Q1 FullyConnectedNets.ipynb | 前移到 A1 Q5 |
| A2 Q6 TensorFlow.ipynb | 已删（2024 起无 TF 题） |
| A3 RNN/LSTM_Captioning.ipynb | 移入 A2 Q5 且 PyTorch 化、只考 vanilla RNN |
| A3 NetworkVisualization.ipynb（saliency/fooling） | 移出作业 → 讲座 L9 + §8.1 |
| A3 StyleTransfer.ipynb | 移出作业 → 讲座 L9 + §8.1 |
| A3 GAN.ipynb / VAE（2024 及以前） | 移出作业 → 讲座 L13 + §8.2 |
| （无对应）DDPM / SimCLR / CLIP-DINO / ViT | 2025 起新增（§7） |

### 1.5 这门课的隐形门槛

官方 Prerequisites 写得很克制：Python 熟练、微积分 + 线代、基础概率统计。真正的隐形门槛是**链式法则的手推能力**——A1/A2 每一个 backward 都要求你在纸上把 Jacobian 理清楚再用 numpy 落地。408 考生不必慌：这恰好是数学三线代/高数的直接应用场景，矩阵求导练熟了反而是考研数学的活习题。

---

## 2 全局地图与关键路径

### 2.1 三个作业一张表（Spring 2026，占分 45%：A1 12% + A2 18% + A3 15%）

| 作业 | Q 清单（zip 解包核实） | 实现语言 | 核心考点 | 截止（2026 学期） |
|---|---|---|---|---|
| A1 | Q1 kNN（双循环/单循环/全向量化）、Q2 Softmax、Q3 Two-Layer Net、Q4 Image Features（HOG/色直方图）、Q5 FullyConnectedNets（任意深度 FC + BatchNorm/Dropout 选项） | **纯 numpy 手写** | 向量化、手工反传、数值梯度检查、train/val/test 纪律 | Apr 16 |
| A2 | Q1 BatchNorm（含 LayerNorm）、Q2 Dropout、Q3 ConvNets（naive conv/pool 正反传 + im2col 加速）、Q4 PyTorch on CIFAR-10、Q5 RNN Captioning（PyTorch 里手写 `_numpy` 函数） | numpy 手写 + **PyTorch 入场** | 归一化层的 train/test 差异、inverted dropout、im2col、nn.Module 基本法、BPTT | May 08 |
| A3 | Q1 Transformer Captioning（attention/PE/decoder/ViT）、Q2 Self-Supervised Learning（SimCLR 对比损失）、Q3 DDPM（扩散）、Q4 CLIP and DINO（预训练模型探索） | **PyTorch 为主** | self-attention 手写、causal mask、位置编码、对比学习、扩散训练目标、zero-shot | May 28 |

公共库 `cs231n/`（每份 zip 自带同一套）：`layers.py`（全部 layer 正反传）、`gradient_check.py`、`optim.py`（sgd/momentum/rmsprop/adam）、`solver.py`（训练驱动）、`classifiers/`。三个作业是**同一个库的渐进填充**：A1 填 affine/relu/softmax 与 FC 网络，A2 填 BN/Dropout/conv/pool 与 RNN 层，A3 换成 PyTorch 模块的 `transformer_layers.py`、`simclr/`、`gaussian_diffusion.py`。

### 2.2 讲座主线（Spring 2026，18 讲）

官方 schedule 的板块划分本身就值得抄下来（这就是 2026 年 CV 的知识地图）：

```
Deep Learning Basics              L1 Intro | L2 线性分类器+softmax | L3 正则化+优化
                                   L4 神经网络与反向传播
Perceiving & Understanding Visual L5 CNN | L6 CNN 架构史(BN/迁移学习/AlexNet-VGG-ResNet)
World                             L7 RNN/LSTM/GRU | L8 Attention 与 Transformer(ViT)
                                   L9 检测+分割+可解释性(saliency/对抗/DeepDream)
                                   L10 视频理解 | L11 大规模分布式训练
Generative & Interactive          L12 自监督学习(对比学习) | L13 生成模型 I(VAE/GAN/自回归)
Visual Intelligence               L14 生成模型 II(扩散) | L15 3D 视觉 | L16 Vision+Language
                                   L17 World Modeling | L18 Human-Centered AI
```

与 2020 年代旧主线对比的差异（值得注意）：硬件/软件讲座（旧 L6）取消；**新增** L11 大规模分布式训练（parallelism / activation checkpointing）与 L17 World Modeling——课程在向"大模型时代的 CV"对齐。旧讲座里的检测/分割合并进了 L9 一讲讲完。

### 2.3 关键路径：动手顺序

推荐顺序 **A1 → A2 → A3**，理由是概念依赖而不是难度：

1. **A1 建立"手推梯度"的肌肉**。kNN 是反直觉热身（无参数模型的代价），Softmax/两层网/FC 网把"forward 定义损失、backward 定义学习"这个循环走完整。没有这一步，A2 的 BN 反传会变成"抄公式"。
2. **A2 把肌肉用到卷积和序列上**，同时完成 PyTorch 转场。BN/Dropout/conv 的手工反传是面试手写题的重灾区（§10.2），投入回报最高。
3. **A3 是现代 CV 的三张门票**：Transformer（多模态/LLM 通用底座）、对比学习（表征学习范式）、扩散（生成式主线）。CLIP/DINO 那份是探索型，最轻。

顺序之外的一个裁剪原则：**时间不够时 A3 按 §11 的求职方向裁剪，A1/A2 不可裁**。

### 2.4 一条贯穿全部作业的方法论

```
1. forward   写出每层的前向，cache 住反传需要的东西（x、w、mask、running stats）
2. loss      softmax_loss / temporal_softmax_loss 收口，得到标量
3. backward  从 dscores 出发，逐层手推 dL/dx，链式法则 + 形状检查
4. check     eval_numerical_gradient 对拍，rel_error < 1e-6~1e-4 才继续
5. train     Solver / captioning_solver 驱动，overfit 小数据是第一验收标准
```

**"先 overfit 一个小批次，再谈泛化"** 是这门课（也是整个深度学习工程）的第一训练纪律。每个作业 notebook 里都有 "Overfit on small data" 一节，这不是练习题，是流程规定。

---

## 3 设计理念（最值钱的一节）

### 3.1 手工微积分：作业全用 numpy 的用意，autograd 最后才登场

A1/A2 的每一个函数都是 `xxx_forward` + `xxx_backward` 成对出现，`cache` 是它们之间的契约。这套设计的潜台词：

- **反向传播不是"框架的功能"，是微积分本身。** `dL/dW` 长什么样、为什么 ReLU 的反向是一个 0/1 mask、为什么 max pool 的反向是"赢家通吃"——这些你在 numpy 里写一遍之后，autograd 对你来说就不再是魔法，而是"我手推过的这些式子的自动展开"。
- **框架是放大器不是理解器。** 所以课程的排布是：先让你被 `conv_backward_naive` 的双循环折磨两小时（A2 Q3），再给你 im2col 把它变成一次矩阵乘，最后才在 A2 Q4 交给 PyTorch `nn.Conv2d`。每一层加速都发生在"你已经理解了它在算什么"之后。
- **接口设计是工程训练**。`loss(X, y=None)` 的双模式（给 y 返回 `(loss, grads)`，不给 y 返回 scores）、每个 layer 统一返回 `(out, cache)`、Solver 与 model 解耦——这是 2015 年由这门课定型、后来被无数课程和库模仿的 API 范式。PyTorch 的 `nn.Module` 的 `forward`/`backward` 对偶几乎就是它的直系后代。

一句话：**这门课的作业在教你"当 autograd 的作者"，而不是"当 autograd 的用户"。**

### 3.2 图像分类是深度学习的 hello world

"给一张 32x32x3 的图片，输出它属于 10 个类中的哪一个"——cs231n 把这个任务选作整门课的主线，因为它小到可以在浏览器里跑（课程主页那个 ConvNetJS 实时演示至今还在），又完整包含了深度学习的全部要素：数据集切分、参数化打分函数、损失函数、优化器、正则化、调参。**kNN → 线性分类器 → 两层网 → 深网 → CNN → Transformer** 这条主线的每一步都在回答同一个问题（"怎么让机器看懂图"），只是假设越来越强、先验越来越少。学完这条线，再看任何新架构（检测头、扩散 UNet、ViT patch embedding）都只是"同一个 pipeline 换了打分函数"。

### 3.3 特征工程 → 表示学习：一场范式转移的现场教学

A1 的 Q4（Image Features）是整门课最"复古"也最点题的一题：先别用神经网络，用 HOG、颜色直方图这类**手工特征**喂给线性分类器，看能涨多少分。然后 Q5 的深网直接吃原始像素，把手工特征拍在沙滩上。

这一题的用意不是教 HOG（2026 年没人靠 HOG吃饭），而是让你**亲手复现历史**：2012 年之前 CV 的主流是"SIFT/HOG 特征 + SVM 分类器"，特征是人设计的、分类器只学最后一层；AlexNet 之后，"特征"变成了网络自己学的中间层表示，人只负责搭结构。`understanding-cnn` notes 里那句"CNN 的每一层就是在学一个层级化的特征提取器"——只有先做过 Q4 才真正懂它的分量。**这是从"人定义表示"到"网络学习表示"的范式转移，也是这门课名字里 *deep* 的本义。**

### 3.4 共同底座：为什么整个深度学习社区都欠这门课

cs231n 的历史贡献远超一门课的体量：

- **notes 是公共教材**。`cs231n.github.io` 的 backprop / neural-networks / convnets 三篇 notes 是中文技术社区引用率最高的深度学习入门材料，"CS231n 笔记翻译"至今仍是新人的标配阅读。Karpathy 写这些 notes 时确立的讲法（"real-valued circuits"、"patterns in gradient flow"、用 CIFAR-10 贯穿始终）塑造了后来几乎所有入门材料的叙事。
- **作业是行业练兵场**。从这门课作业里走出来的直觉（log-sum-exp 数值稳定、BN 的 running mean、inverted dropout、overfit 小数据）就是今天面试题库的原文出处。
- **人事上，它是节点**。Karpathy（Tesla/OpenAI）、Justin Johnson（Michigan）、Fei-Fei Li（ImageNet/AI 以人为本学派）——这门课的讲师名单本身就是半部深度学习叙事史。Karpathy 后来的 zero-to-hero 系列第一课，讲的就是他当年在 cs231n 讲 micrograd 的思路：**手写 backprop 是理解一切的开端**。

### 3.5 2025 大改版本身就是一个信号

作业从 "RNN/GAN/风格迁移"（2024 及以前）换成 "Transformer/自监督/扩散/CLIP"（2025 起），对应的是 CV 行业自身的换血：-captioning 的主流模型从 LSTM 变成 Transformer，生成的主流从 GAN 变成扩散，表征的主流从 ImageNet 监督预训练变成自监督/图文对比。**课程在告诉你：CNN 时代经典（A2 为止）是地基，但 2026 年的门票在 A3。** 复习时按这个分层投入，别把时间平均撒。

### 3.6 与「框架优先」路线的自觉对照

必须诚实地说出另一条路线：CMU 11-785 那类课程第一周就从 autograd/框架入手，靠框架的梯度检查兜底，把时间花在更多模型族和理论上。cs231n 的 numpy 路线牺牲了"模型数量"，换来"每个 grad 都是自己的手推"。两条路线都能到岸，但**面试白板题只奖励 cs231n 这条**。这也是 §12 三门课互位的核心分歧点。

---

## 4 各作业大纲（抓重点 / 关键路径 / 易错点 / 设计理念）

> 本节是大纲层。逐块展开（函数签名、数据流、伪代码、逐条易错点）见 §5–§7。

### 4.1 A1 · Image Classification / kNN / Softmax / FC Nets（纯 numpy）

**抓重点**
1. kNN 的三种距离实现是**向量化训练**：双循环 → 单循环 → 全向量化（broadcasting + 矩阵恒等式），一个 5000x500 距离矩阵从秒级到微秒级。
2. Softmax 损失 + 数值梯度检查是一切后续作业的地基：**先让 rel_error < 1e-6，再相信你的 backward**。
3. Two-Layer Net 是第一个"端到端"：forward → loss → backward → SGD → 验证集调参，完整走通。
4. Q5 FullyConnectedNets（2025 起从 A2 移入）：任意深度 FC + 可选 BatchNorm/Dropout，第一次用"层组合"而不是"一坨 forward"组织代码。
5. Q4 Image Features：手工特征 vs 学习表示的对照实验（§3.3）。

**关键路径**
kNN（热身 + 向量化）→ Softmax（log-sum-exp）→ 梯度检查（方法论）→ two-layer net（端到端闭环）→ FullyConnectedNets（层抽象）→ features（历史课，可后置）。

**细节与易错点**
- kNN 全向量化版本的内存爆炸（§5.1）；predict_labels 的并列处理。
- softmax 不减 max 会溢出；正则化梯度 `reg*W` 与损失里 `0.5*reg*||W||^2` 的 0.5 配套。
- 梯度检查遇 kink（max/ReLU）失效；dropout/BN 要先固定随机性。
- FC 网里正则化只加在权重上，不加 bias/gamma/beta。

**设计理念**
没有参数的模型（kNN）让"参数化 + 优化"这个范式的好处显形；双模式 `loss()` 接口与 `(out, cache)` 契约在此定型；features 一题把"表示学习为什么赢"变成实验结论而不是口号。

### 4.2 A2 · BatchNorm / Dropout / ConvNets / PyTorch / RNN Captioning

**抓重点**
1. BatchNorm 的 **train/test 行为分裂**（batch 统计 vs running 统计）——面试第一高频。
2. inverted dropout：train 除 keep_prob、test 原样——为什么必须这样设计。
3. ConvNets：naive 双循环实现先把语义写对，im2col 再把它变成矩阵乘；conv/pool 的反向都要在纸上画一遍。
4. PyTorch on CIFAR-10：nn.Module 三步曲 + 调参冲分，autograd 的第一次正式上岗。
5. RNN captioning（2025 起移入、PyTorch 化）：手写 `_numpy` 后缀的 rnn_step/word_embedding/temporal 层正反传，BPTT 的现场。

**关键路径**
BatchNorm（含 LayerNorm 对照）→ Dropout → ConvNets（naive → im2col）→ PyTorch 转场 → RNN captioning。

**细节与易错点**
- BN backward 的完整公式（两条路径：x_hat 与 mu/var 直接项）。
- 卷积反向的"梯度散射回感受野"；pool 反向只走 argmax。
- im2col 的 col2im 是散射加法（np.add.at），不是赋值。
- RNN 的 temporal_softmax_loss 要 mask 掉 NULL 位。
- PyTorch 的 `zero_grad()` 忘调会梯度累积。

**设计理念**
归一化与 Dropout 都在回答"训练时与推理时网络该不该一样"——BN 是"统计量换算"，dropout 是"期望保持"。im2col 则是"卷积 = 稀疏矩阵乘"的工程兑现，为后来 CUDA/Tensor Core 的做法做了心智铺垫。

### 4.3 A3 · Transformer Captioning / SimCLR / DDPM / CLIP-DINO（PyTorch 为主）

**抓重点**
1. 手写 scaled dot-product attention、多头拆分、causal mask、位置编码、decoder block（self-attn → cross-attn → FFN），最后拼出 CaptioningTransformer，**外加实现一个 ViT**。
2. SimCLR：对比损失 naive 与 vectorized 两版（sim 矩阵技巧），投影头 + 线性探针微调。
3. DDPM：前向一步加噪公式、训练目标"预测 eps"、p_sample 逐步去噪、beta schedule、classifier-free guidance。
4. CLIP/DINO：预训练模型探索——zero-shot 分类、图文检索、DINO attention map 的分割涌现。

**关键路径**
Transformer（第一优先，多模态/LLM 双栖）→ SimCLR（表征学习范式）→ DDPM（生成主线）→ CLIP/DINO（最轻，探索型）。

**细节与易错点**
- attention 里忘记除 `sqrt(d_k)` 或 mask 放在 softmax 之后。
- 多头的 reshape 顺序（N,T,H,hd → N,H,T,hd）。
- SimCLR 的分母要排除自身。
- DDPM 的 `alpha_bar_t` 连乘与 `extract()` 按批索引。

**设计理念**
A3 的四个主题分别是 2020 年代 CV 的四条主线：序列建模统一到 attention、自监督解决"标注贵"、生成从对抗转向迭代去噪、多模态对齐与自蒸馏。它们共享同一个底层动作——**把"结构先验"（卷积、循环）替换为"规模 + 简单目标"（attention、对比、去噪）**。

---

## 5 A1 逐块展开（可动手级 · 纯 numpy）

> 以下函数签名全部来自 2026 版 `assignment1.zip` 解包核对（`cs231n/classifiers/k_nearest_neighbor.py`、`cs231n/layers.py`、`cs231n/classifiers/fc_net.py`）。

### 5.1 kNN：三种距离实现（向量化三连跳）

**任务**：`KNearestNeighbor` 类里填 4 个方法。

```python
def train(self, X, y):                 # 只存数据：self.X_train, self.y_train
def predict(self, X, k=1, num_loops=0) # 按 num_loops 分派 0/1/2 三种距离实现
def compute_distances_two_loops(self, X)
def compute_distances_one_loop(self, X)
def compute_distances_no_loops(self, X)
def predict_labels(self, dists, k=1)   # dists: (num_test, num_train)
```

**三种实现**（X_test: (num_test, D)，X_train: (num_train, D)，L2 距离）：

```python
# 双循环：最朴素，语义基准（作业里还要求顺带画出 dists 图检查）
for i in range(num_test):
    for j in range(num_train):
        diff = X_test[i] - X_train[j]        # (D,)
        dists[i, j] = sqrt(sum(diff * diff))

# 单循环：一次 broadcasting 减掉整个 train
for i in range(num_test):
    diff = X_train - X_test[i]               # (num_train, D) 广播
    dists[i] = sqrt(sum(diff * diff, axis=1))

# 零循环：用恒等式 ||a - b||^2 = ||a||^2 + ||b||^2 - 2 a.b
# 注意 sqrt 前先 clip(dist, 0)：浮点误差可能造出 -1e-12
dists = sqrt(clip(
    sum(X_test**2, axis=1, keepdims=True)    # (num_test, 1)
    + sum(X_train**2, axis=1)                # (num_train,)
    - 2 * X_test @ X_train.T, 0))            # 核心是一次 GEMM
```

**性能与内存的取舍**（notebook 里实测对比的那种）：

| 实现 | 时间复杂度 | 实测相对耗时 | 内存 |
|---|---|---|---|
| 双循环 | O(T*N*D) 纯 Python 循环 | ~100x 慢 | O(T*N) |
| 单循环 | broadcasting 中间量 O(N*D)/次 | ~10x 慢 | O(N*D) 临时 |
| 零循环 | 一次矩阵乘 O(T*N*D) 但全在 BLAS | 1x | **O(T*N) 且常数大**：500x5000 的 f64 距离矩阵本身才 20MB，但 broadcast 差值矩阵若显式造出来是 T*N*D = 500x5000x3072 ≈ 7.5 GB——这就是为什么必须用恒等式而不是 `(X_test[:,None,:] - X_train[None,:,:])**2` |

**predict_labels 的易错点**：

1. `np.argsort(dists[i])[:k]` 取最近 k 个的**索引**，再用 `y_train[closest_y]` 换成标签。
2. `np.bincount(closest_y)` 找众数：`np.argmax(bincount)` 遇并列取最小标签值——测试集上可接受，但要知道这个并列规则是任意的。
3. k=1 与 k=5 的验证集准确率对比是 notebook 的核心实验：**k 越大边界越平滑**，这是超参数与泛化的第一课。

**设计理念**：kNN 是"训练 O(1)、预测 O(N)"的反参数化标本——所有计算推迟到预测时，和后续所有"训练贵、预测便宜"的参数化模型正好相反。它还顺便演示了**语义鸿沟**：图像的像素距离和视觉相似性几乎无关（背景主导），逼出"我们需要学出来的表示"这个动机。

### 5.2 Softmax 与交叉熵（2026 版 A1 的第二个手写损失）

**任务**：`cs231n/layers.py` 里的 `softmax_loss(x, y)` + `cs231n/classifiers/softmax.py` 的 `Softmax(LinearClassifier)`（训练壳直接可用，重心在 loss 函数）。

**推导**（scores = x W + b，x: (N, D)，W: (D, C)）：

```
s = x @ W + b                      # (N, C)
p = softmax(s)                     # p_ij = exp(s_ij) / sum_c exp(s_ic)
loss = -sum_i log p_i[y_i] / N     # 交叉熵；再 += 0.5 * reg * sum(W*W)
ds = (p - onehot(y)) / N           # 这一行就是全部的反向
dW = x.T @ ds + reg * W            # 注意 reg*W 与损失的 0.5 配套
```

**数值稳定（log-sum-exp）——本作业最重要的工程细节**：

```python
shifted = s - max(s, axis=1, keepdims=True)   # 每行减去该行最大 score
logZ = log(sum(exp(shifted), axis=1))          # 减 max 后 exp 不会溢出
log_prob = shifted[range(N), y] - logZ
loss = -mean(log_prob)
```

- 不减 max：`exp(1000)` 直接 inf，loss 变 nan。**面试原题：为什么减 max 不改变结果？** 因为 `softmax(z) == softmax(z + c)` 对任意常数 c 成立（分子分母同乘 exp(c)）。
- 一个容易忽略的坑：**验证 loss 的"理论下限"**。初始随机权重时 loss 应约等于 `log(C)`（CIFAR-10 上是 log(10) ≈ 2.30）——这是 sanity check 的标准之一（见 neural-networks-3 notes 的 "Babysitting" 一节）。
- ds 的推导：softmax 与交叉熵**必须合并求导**才是 `(p - onehot)/N` 这一行；分开推会在 Jacobian 里绕远路。这是"layer 契约"设计的第一个案例——为什么 `softmax_loss` 是一个函数而不是两层。

**SVM 对照（作业已删、面试仍考）**：hinge loss `sum_j!=yi max(0, s_j - s_yi + delta)` 对 margin 内的样本梯度是"死区"（恰好落在边界外则梯度为 0），softmax 的梯度永远非零；hinge 关心"赢多少"，交叉熵关心"概率分布"。库里的 `svm_loss(x, y)` 2026 版仍在 `layers.py` 中，可自读。

### 5.3 数值梯度检查（每个 backward 的验收标准）

**工具**：`cs231n/gradient_check.py` 的 `eval_numerical_gradient(f, x, h)`（标量损失版）、`eval_numerical_gradient_array(f, x, df)`（逐元素版，df 是上游梯度）、`rel_error(a, b) = |a-b| / (|a|+|b| + 1e-12)`。

**中心差分**：`(f(x+h) - f(x-h)) / (2h)`，比前向差分 `(f(x+h)-f(x))/h` 精度高一个数量级（O(h^2) vs O(h)）。h 取 `1e-5`~`1e-7`。

**判读阈值**（neural-networks-3 notes 给的经验值，记住这张表）：

| rel_error | 判读 |
|---|---|
| < 1e-4 | 没问题（矩阵大、误差会累积；1e-6~1e-8 才是"完美"） |
| 1e-4 ~ 1e-2 | 可疑，缩小网络规模重查 |
| > 1e-2 | 基本可断定有 bug |

**逐条易错点**：

1. **kink 问题**：`max(0, x)`、hinge、ReLU 在拐点处不可导。如果检查点恰好落在 kink 附近（x+h 或 x-h 跨过 0），数值梯度就是错的。对策：用小网络 + 固定 seed，或把 `x` 的初始值整体偏移避开 0。
2. **随机层要冻结**：dropout / BN 检查梯度前必须固定 mode（dropout 的 mask、BN 的 batch 统计每次前向都变），否则数值梯度采到的是不同函数。
3. **h 与 eps 的相互作用**：h 太小会撞 float32 精度地板（建议临时升 `np.float64` 再查），h 太大则截断误差占主导。
4. **只检查有限维度**：全参数数值检查是 O(参数量 x 2) 次前向，只能对小网络做——这也是为什么"先小规模 overfit + 梯度检查"是标准流程。
5. **正则项也参与检查**：忘了把 reg 加进 loss 就检查"数据项"，等打开 reg 又崩——检查时的 loss 必须和训练时完全同构。

**设计理念**：数值梯度是"定义"，解析梯度是"定理"，rel_error 是"定理的证明"。这套对拍流程就是后来所有人写自定义 op 的标配（PyTorch 的 `torch.autograd.gradcheck` 是它的直系后代）。

### 5.4 Two-Layer Net：第一个端到端闭环

**结构**：`{affine - relu} - affine - softmax`，hidden_size 可调（默认 100）。

```python
class TwoLayerNet(object):
    def __init__(self, input_dim=3*32*32, hidden_dim=100, num_classes=10,
                 weight_scale=1e-3, reg=0.0)   # W = randn(...) * weight_scale
    def loss(self, X, y=None):
        # y=None -> return scores；y 给定 -> return (loss, grads)
```

**手推两条链**（这是 A1 的核心考题，纸上要能默写）：

```
forward:  h = max(0, X @ W1 + b1)        # (N, H)
          scores = h @ W2 + b2           # (N, C)
backward: dscores = (softmax(scores) - onehot(y)) / N
          dW2 = h.T @ dscores + reg*W2 ; db2 = sum(dscores, axis=0)
          dh = dscores @ W2.T
          dh[scores 那层 h <= 0 的位置] = 0    # ReLU 反向：0/1 mask
          dW1 = X.T @ dh + reg*W1 ; db1 = sum(dh, axis=0)
```

**训练纪律**（notebook 的实验序列就是调参方法论）：

1. 先无正则跑一轮看 train/val 曲线——确认"能学"。
2. 加大 `reg`（1e-5 → 1e-3 → 1e-1）看 val 准确率的变化。
3. 调 hidden_size（10 → 100 → 500）观察容量-过拟合关系。
4. 学习率网格：1e-4（太小吃不动）~ 1e0（loss 发散成 nan）——**"lr 大了 loss 变 nan"是必踩一次的坑**。
5. 最终目标（notebook 口径）：val 准确率约 48-52%（含手工特征可更高，见 §5.6）。

**Solver 的角色**：`cs231n/solver.py` 负责 epoch/iteration 循环、train/val 切分、check_acc——**model 只管 loss(X, y) 的纯函数**，训练逻辑全部外包。这是"模型与优化解耦"的接口设计，PyTorch 的 `Trainer`/Lightning 的 `LightningModule` 分层与之同构。

### 5.5 FullyConnectedNets：从"一坨 forward"到"层组合"（2025 起从 A2 移入 A1）

**任务**：先在 `layers.py` 填 `affine_forward/backward`、`relu_forward/backward`（5.3/5.4 已推），然后在 `layer_utils.py` 组合出 sandwich 层，最后组装任意深度的 `FullyConnectedNet`。

```python
# sandwich：cache 串联是唯一技巧
def affine_relu_forward(x, w, b):
    a, fc_cache = affine_forward(x, w, b)
    out, relu_cache = relu_forward(a)
    return out, (fc_cache, relu_cache)

def affine_relu_backward(dout, cache):
    fc_cache, relu_cache = cache
    da = relu_backward(dout, relu_cache)
    return affine_backward(da, fc_cache)
```

```python
class FullyConnectedNet(object):
    # hidden_dims: [100, 100, ...]；normalization: 'batchnorm'/'layernorm'/None
    # dropout: keep_prob 或 None；默认 reg 只作用于 W
    def loss(self, X, y=None):
        # [affine-relu] * (L-1) -> affine -> softmax
        # 反向：softmax_loss 回来的 ds 逐层穿过 affine_relu_backward
        # 反传到第 1 层后：grads['W1'] += reg * W1（bias 不加 reg）
```

**逐条易错点**：

1. **cache 顺序**：forward 存什么、backward 按什么顺序拆——tuple 对不上是新手第一大 bug 源。
2. **参数命名**：`params['W1']...` 与 `grads['W1']...` 的键必须一一对应，Solver 按键传参。
3. **BN/Dropout 开启时的前向链路**：`[affine - norm - relu - dropout] * (L-1) - affine - softmax`——顺序是 norm 在 relu 前（dropout 在 relu 后），2026 版要求你在 A1 就把这个组合骨架搭好（BN/Dropout 的实现在 A2 完成）。
4. **梯度检查合格线**：开 reg 后 rel_error 仍应 < 1e-4；分不清哪个参数错，就单独对一个 `W` 检查。
5. **He 初始化**：`weight_scale = sqrt(2/fan_in)` 配 ReLU（neural-networks-2 notes 的推荐）；用默认 1e-3 时深网会训不动——notebook 有专门实验让你对比初始化的影响。

**设计理念**：这一题的教学对象不是"深网"本身，而是**可组合性的接口设计**——layer 是原子、sandwich 是分子、model 是组装件。一旦 `(out, cache)` 契约成立，深度就变成了 for 循环，A2 的 conv/BN/Dropout 只是往原子库里加成员。这是"架构即代码组织"的思想，PyTorch `nn.Sequential` 就是它的官方版。

### 5.6 Image Features：HOG 的黄昏（Q4）

**任务**：`cs231n/features.py` 提供色直方图与 HOG 的采样骨架，你主要是**使用**特征喂给 two-layer net，对比原始像素。

**核心实验结论**（notebook 口径）：像素输入 val ~50% 上下，手工特征能把小网络的 val 推到 ~57-60%——**在"模型很弱"的前提下，好特征确实值十几个点**。但 Q5 的深网直接超过这个水平且还在吃像素。

**设计理念**（§3.3 的现场版）：特征工程时代的分工是"人负责表示、机器负责分类"；深学习把两件事合并成一个可微 pipeline，于是"改进特征"变成了"改进架构 + 加数据"。这也是为什么 2026 版还要留这道题：**不亲手量一次"手工特征的天花板"，就无法体会 AlexNet 在 2012 年砸下来的东西是什么。**

### 5.7 训练驱动与优化器：Solver + optim.py（贯穿 Q3-Q5）

A1 的三个训练题共用同一套驱动（zip 核实：`solver.py` + `optim.py`，学生要填 `optim.py` 里的升级公式）：

```python
# LinearClassifier.train / Solver 的骨架：mini-batch SGD
num_batches = N / batch_size
for epoch in range(num_epochs):
    for batch in sampling_permutation:
        loss, grads = model.loss(X_batch, y_batch)     # 双模式 loss() 的用武之地
        for p in model.params:                          # 对每个参数套优化器
            config = optim_configs[p]
            next_p, next_config = optim_func(params[p], grads[p], config)
```

**optim.py 四连**（neural-networks-3 notes 的公式，Adam 是面试手写高频）：

```
sgd:          x -= lr * dx
momentum:     v = mu * v - lr * dx ; x += v            # mu 常取 0.9
rmsprop:      cache = decay*cache + (1-decay)*dx^2 ; x -= lr*dx/sqrt(cache+eps)
adam:         m = b1*m + (1-b1)*dx ; v = b2*v + (1-b2)*dx^2
              mt = m/(1-b1^t) ; vt = v/(1-b2^t)         # 偏差修正，t 从 1 计
              x -= lr * mt / (sqrt(vt) + eps)          # 默认 b1=0.9, b2=0.999
```

**易错点**：
1. momentum 的 `mu` 存在 config 里且**随 step 更新**（cs231n 的实现里每步乘 decay 衰减）——读一遍 solver 的调用链再写。
2. rmsprop/adam 的 `eps` 在 sqrt **外面**（cs231n 实现），与某些教材写在里面不同——跟 handout 注释走。
3. Adam 的偏差修正是为什么：m/v 初始化为 0，前几步被 0 拉偏，除以 (1-b^t) 把它除回来——被追问时能写出这一句。

**设计理念**：model 只管 `(loss, grads)`、Solver 只管循环、optim 只管"拿梯度更新参数"——三层解耦后，换优化器、换模型都是单点替换。这是 cs231n 接口设计的收官：**PyTorch 的 `nn.Module` + `DataLoader` + `optim.Optimizer` 三件套与它一一对应**，所以 A2 的 PyTorch 转场才显得毫无违和。

---

## 6 A2 逐块展开（可动手级 · numpy 手写 + PyTorch 转场）

> 函数签名来自 2026 版 `assignment2.zip` 解包核对（`cs231n/layers.py`、`cs231n/im2col.py`、`cs231n/rnn_layers_pytorch.py`）。

### 6.1 BatchNorm 与 LayerNorm：train/test 行为分裂

**任务**：`batchnorm_forward/backward`、`batchnorm_backward_alt`（另一种推导路线）、`layernorm_forward/backward`（借 BN 的结论换归一化轴）、`spatial_batchnorm_forward/backward`（对 conv 特征图做 BN）。

**前向（train mode）**：

```
mu = mean(x, axis=0)                    # 对 batch 维求均值 (D,)
var = mean((x - mu)^2, axis=0)
x_hat = (x - mu) / sqrt(var + eps)      # eps ~ 1e-5，防除零
out = gamma * x_hat + beta              # gamma/beta 可学
# 同时维护 running 统计（bn_param 里的 mode/momentum）：
running_mean = momentum * running_mean + (1 - momentum) * mu
```

**test mode**：**不再用当前 batch 统计**，直接 `x_hat = (x - running_mean) / sqrt(running_var + eps)`。

**为什么必须有两套行为**（面试标准答案的三段式）：
1. 推理时 batch 可能是 1 张图，batch 统计无意义；
2. 推理要确定性——同一输入必须同输出，统计量必须冻结；
3. 训练/推理的不一致是 BN 的"设计缺陷"，LayerNorm/GroupNorm 用"不依赖 batch"根治了它（这正是 Transformer 选 LayerNorm 的原因之一）。

**反向（本作业最难的一推，两条路径都要推）**：

```
dbeta  = sum(dout, axis=0)
dgamma = sum(dout * x_hat, axis=0)

# 完整式（对 batch 维 B 求平均的 compact form）：
inv_std = 1 / sqrt(var + eps)
dx = gamma * inv_std * (dout - mean(dout, axis=0)
                        - x_hat * mean(dout * x_hat, axis=0))
```

直觉：x_hat 里的每个元素既通过"自己"影响输出，也通过 mu/var（它们是全体 x 的函数）间接影响输出——第二项就是大多数人漏掉的修正项。**用 `batchnorm_backward_alt` 的"先算 dx_hat/dgamma/dbeta 再套链式"路线推一遍，再用 compact 式推一遍，两条路线对拍**是这题的设计用意。

**LayerNorm**：归一化轴从 batch 维换到特征维（对单个样本的 D 维向量归一化），**没有 running stats，train/test 一致**。实现技巧：把 LN 看成"batch=1 的 BN 的转置版本"，复用 BN 公式（x 转置后代入、gamma/beta 的广播方向换轴）。

**Spatial BatchNorm**：conv 输出 (N, C, H, W)，BN 要对**每个通道**在 (N, H, W) 上归一化。实现就是两次 reshape：

```python
# forward
N, C, H, W = x.shape
x_flat = x.transpose(0, 2, 3, 1).reshape(N*H*W, C)   # 通道拉到最后一维
out_flat, cache = batchnorm_forward(x_flat, gamma, beta, bn_param)
out = out_flat.reshape(N, H, W, C).transpose(0, 3, 1, 2)
```

**易错点汇总**：
1. running 统计更新放在 train 分支里，test 分支忘了写（或反之）——检查函数的 autograder 会专门测这个。
2. `var` 用的是有偏（除 N）版本，与 running_var 保持同口径。
3. LN 的 gamma/beta 形状是 (D,)，但广播发生在最后一维——reshape 后再广播。
4. eps 加在 sqrt 里而不是外。

**设计理念**：BN 把"输入分布漂移"（internal covariate shift，原始动机）变成可优化的统计量；但它真正的贡献是**平滑了损失面、允许大学习率**（后来的理论解释）。BN/Dropout/归一化家族共同的深层主题：**训练态与推理态的网络必须被明确地区分对待**——这个"两态性"是部署推理引擎（TorchScript/ONNX 的 freeze 流程）时所有坑的来源。

### 6.2 Dropout：inverted 是唯一正确姿势

**任务**：`dropout_forward(x, dropout_param)` / `dropout_backward(dout, cache)`，mode 和 p 存在 `dropout_param`，mask 进 cache。

```python
# train：除 p（keep_prob 的倒数）——"inverted"就invert在这一步
mask = (rand(*x.shape) < p) / p         # p 是 keep_prob
out = x * mask
# test：identity，直接返回 x
```

**为什么不 inverted（老式）会死**：老式在 **test 时乘 p**。问题有三：推理路径被污染（同一权重要区分两态）；下游层收到的期望虽然一致但 BN 的 running 统计会对不上；微调/蒸馏时尺度来回跳。inverted 把缩放挪到 train，**test 路径纯 identity**——推理引擎零成本。

**数学论证**（面试可写）：E_train[x_i * mask_i] = p * (x_i / p) = x_i，期望不变，方差变化可被 BN 吸收。

**易错点**：
1. `p` 的语义是 keep_prob 不是丢弃率（cs231n 口径；PyTorch 的 `nn.Dropout(p)` 里 p 是**丢弃率**——两套约定相反，写代码前先确认）。
2. 梯度检查时要 mode='test' 或固定 seed（§5.3）。
3. 反向就是 `dx = dout * mask`——mask 除过 p 了，别再除一次。

**设计理念**：Dropout 是"训练时给网络注入噪声换取鲁棒性"这一家族（与数据增强、标签平滑、 stochastic depth 同族）最简单的成员。理解它的关键不是 mask 本身，而是**train 期望 = test 数值**这个不变式——所有噪声正则化方法都在找自己的方式维持它。

### 6.3 ConvNets：naive 正反传 → im2col 加速

**任务**：`conv_forward_naive/backward_naive`、`max_pool_forward_naive/backward_naive`、`ThreeLayerConvNet` 组装、im2col 加速版（`im2col.py` 提供 utils，`fast_layers.py` 是 cython 参考实现）。

**前向语义**（x: (N, C, H, W)，w: (F, C, HH, WW)，输出 (N, F, H', W')）：

```
H' = 1 + (H + 2*pad - HH) / stride      # 必须整除，否则程序错
out[n, f, i, j] = sum over (c, ii, jj) of
                  x_padded[n, c, i*stride+ii, j*stride+jj] * w[f, c, ii, jj] + b[f]
```

**卷积反向的三件事**（每个都要单独推）：

```
dw[f, c, ii, jj] = sum over (n, i, j) of dout[n, f, i, j] * x_padded[n, c, i*s+ii, j*s+jj]
db[f]            = sum over (n, i, j) of dout[n, f, i, j]
dx_padded[n, c, i*s+ii, j*s+jj] += dout[n, f, i, j] * w[f, c, ii, jj]   # 散射！
```

- dx 是**加法散射**（一个输入位置被多个输出位置的感受野覆盖，梯度相加）——用 `+=` 落在零初始化的 dx_padded 上，最后把 padding 区域切掉。
- "kernel 翻转"的说法：`dw` 在数学上是" dout 与 x 的互相关"；用纯卷积视角看 dW 时会看到翻转的 kernel。naive 双循环实现里这层不显式，**到 im2col/矩阵视角就自然消失**（见下）。
- **max_pool 反向**：前向记下每个窗口的 argmax（cache 住 (x, pool_param) 后反向重算 argmax 或直接缓存索引），梯度只进赢家位置，其余为 0。"winner-take-all"。

**im2col：把卷积变成一次 GEMM**（`im2col.py` 的 `im2col_indices` / `col2im_indices`）：

```
x: (N, C, H, W) --im2col--> x_col: (C*HH*WW, N*H'*W')   # 每列是一个感受野
w: (F, C, HH, WW) --reshape--> w_row: (F, C*HH*WW)
out = w_row @ x_col + b       # (F, N*H'W') -> reshape 回 (N, F, H', W')
反向：dw_row = dout_flat @ x_col.T ; dx_col = w_row.T @ dout_flat -> col2im 散射加法
```

`col2im` 是 im2col 的逆散射：同一原像素出现在多个列里，梯度**相加**——实现上必须 `np.add.at`（fancy index 的 += 不累积，是经典 bug）。

**为什么 im2col 赢**：naive 版的 6 层循环里乘加无法连续；im2col 把数据重排成稠密矩阵后用 BLAS 的 GEMM，吞吐差 1-2 个数量级。代价是内存放大（感受野重叠部分被复制）。**这正是 GPU 上 cuDNN 的实际做法之一**——A2 这题是在为"读懂真实框架"打地基。

**ThreeLayerConvNet**：`{conv - relu - pool} - affine - relu - affine - softmax`。**数一数参数量**：conv(3→32, 5x5) 只有 32*(3*5*5+1) ≈ 2.4k 个参数，却替代了 32x32x3→100 全连接层的 30 万参数——**参数共享 + 局部连接**的收益在数字上显形（convolutional-networks notes 的"computational considerations"一节的原话案例）。

**易错点汇总**：
1. 输出尺寸公式除不尽——先 assert。
2. padding 用 `np.pad` 只 pad H/W 两维，别把 N/C 也 pad 了。
3. pool 反向忘了"重算 argmax 时窗口可能与前向不同"——必须用前向同一套窗口参数。
4. spatial BN 的 reshape 轴序（§6.1）。
5. im2col 版与 naive 版对拍（`rel_error < 1e-8` 量级）而不是只看 shape。

### 6.4 PyTorch on CIFAR-10：autograd 正式上岗

**任务**：`PyTorch.ipynb`——跟着走完 Tensor 基本法 → `nn.Module` → `optim` → 自设计一个 CNN 在 CIFAR-10 冲分（notebook 给的基线是 AlexNet 式结构，要求你调到 **65%+**）。

**nn.Module 三步曲（必须形成肌肉记忆）**：

```python
class MyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 32, 5, padding=2)   # 子模块在 __init__ 注册
        ...
    def forward(self, x):                              # 只写数据流
        x = F.relu(self.conv1(x))
        return self.classifier(x)

# 训练循环三行（全框架通用）：
optimizer.zero_grad()   # 忘了 -> 梯度跨 batch 累积，loss 不降
loss.backward()         # autograd 从这里替你写 §5-§6 的所有 backward
optimizer.step()
```

**cs231n 视角的转场意义**：你刚在 numpy 里写过 `conv_backward`，现在 `loss.backward()` 一行全部完成——**此刻你获得了"知道它在算什么"的框架用户身份**。notebook 要求你手调 lr/结构/训练轮数冲分，体验的是"优化策略 > 手写正确性"的另一种工作模式。

**nn.Module 的机制三问**（notebook 之外的加分理解，面试可能问）：

1. **参数怎么被找到的**：`__init__` 里赋值 `self.conv1 = nn.Conv2d(...)` 时，基类 `__setattr__` 拦截并登记到 `_modules`；`model.parameters()` 递归遍历——所以**在 `__init__` 之外（如 forward 里）new 一个带参模块，optimizer 不会看到它**。
2. **autograd 怎么知道图**：PyTorch 是动态图——每跑一次 forward 用 Tape 模式记录实际执行路径，`backward()` 沿这一次的图反传。与 TF1 静态图的本质区别（旧版 cs231n 的 L6 专讲这个对比，2026 已删但面试还问）。
3. **`zero_grad()` 为什么存在**：PyTorch 的梯度是累加语义（方便多 loss/多卡梯度累计），不清零就跨 batch 累积。

**CIFAR-10 冲分三板斧**（notebook 目标 65%+ 的实际路径）：加 BatchNorm；数据增强（flip/crop）；lr 阶梯衰减（每 10 个 epoch 乘 0.1）。三板斧对应的三条原理——优化面平滑化、输入扰动正则化、训练后期小步精修——全部能落回 A2 的手写题。

**易错点**：`model.train()` / `model.eval()` 忘切换（BN/Dropout 两态性，呼应 §6.1/6.2）；`.to(device)` 漏了模型或数据一方；浮点数 detach 时机。

### 6.5 RNN Image Captioning（2025 起移入 A2，PyTorch 里手写）

**任务**：`RNN_Captioning_pytorch.ipynb`，学生实现集中在带 `_numpy` 后缀的函数（PyTorch 张量进出、手工反传，autograd 不许用）：

```python
def rnn_step_forward_numpy(x, h, Wx, Wh, b):     # h' = tanh(x @ Wx + h @ Wh + b)
def rnn_forward_numpy(x, h0, Wx, Wh, b):          # 沿 T 展开，cache 每个 h
def word_embedding_forward_numpy(x, W):           # out = W[x]；反向是 scatter
def temporal_affine_forward_numpy(x, w, b):       # (N, T, D) x (D, V) -> (N, T, V)
# 加 temporal_softmax_loss（mask 掉 <NULL>）与对应 backward
```

**数据流**（CaptioningRNN，COCO 数据）：

```
图像 -> CNN 特征 (N, D_input) -> 线性映射 -> 初始 hidden h0
词序列 (N, T) -> word embedding (N, T, W) -> RNN 逐步展开 -> (N, T, H)
-> temporal affine -> scores (N, T, V) -> temporal_softmax_loss（mask）
```

**BPTT 的核心认识**：`rnn_forward` 沿时间展开成 T 个共享 Wx/Wh 的单元——**梯度沿时间倒流且反复乘同一个 Wh**。这就是梯度消失/爆炸的来源（谱半径 > 1 爆、< 1 消），也是 LSTM 门控的动机（乘法门控的加法路径 `c_t = f*c_{t-1} + i*g` 让梯度有"高速公路"）。库里仍保留 `lstm_step_forward/lstm_forward`（`rnn_layers_pytorch.py`）可自读，但 2026 版 notebook 只要求 vanilla RNN。

**逐条易错点**：
1. `temporal_softmax_loss` 的 mask：`mask = (y >= 0)`，loss 按 mask 求均值——**分母是 sum(mask) 不是 N*T**，否则 NULL 位污染损失。
2. embedding backward：`dW` 用 `np.add.at(dW, x.flatten(), dout_reshaped)`——同一个词在序列里重复出现，梯度要累积（与 col2im 同一个坑）。
3. h 的维度约定：cs231n 里 recurrent dim 是 H，别和 hidden_dim of FC 混。
4. **测试时采样**是自回归：h0 -> 预测第一个词 -> 作为下一步输入，与训练的 teacher forcing（并行喂全序列）路径不同——notebook 里 "Sampling at Test Time" 单独考这个。
5. **Overfit 小数据**是第一验收：小语料上 loss 要压到接近 0、生成的 caption 要和 ground truth 逐字一致，否则反传必有错。

**设计理念**：captioning 是"视觉特征 + 语言模型"的第一个多模态组合体——CNN 当编码器、RNN 当解码器，这一"encoder-decoder"骨架后来平移成 "CNN + Transformer"（A3 Q1）、再平移成今天所有图文/视频生成模型。cs231n 把它放在 A2 的用意：**在见 Transformer 之前，先用 RNN 把"序列生成的训练（teacher forcing）与推理（自回归采样）不一致"这个麻烦亲历一遍**——你会立刻明白 A3 的 causal mask 与 decoding 策略在解决什么。

---

## 7 A3 逐块展开（可动手级 · PyTorch 为主 · 2026 版）

> 函数与类名来自 2026 版 `assignment3.zip` 解包核对（`cs231n/transformer_layers.py`、`cs231n/classifiers/transformer.py`、`cs231n/simclr/contrastive_loss.py`、`cs231n/gaussian_diffusion.py`）。A3 无 numpy 手写反传——**autograd 时代，你写 forward，梯度是框架的事**；这一作业考的是"把结构写对"。

### 7.1 Transformer Captioning（Q1，含 ViT）

**要实现的积木**（`transformer_layers.py`）：

```python
class PositionalEncoding(nn.Module):        # PE(pos, 2i)   = sin(pos / 10000^(2i/d))
    # PE(pos, 2i+1) = cos(pos / 10000^(2i/d));  out = x + PE[:, :T]
class MultiHeadAttention(nn.Module):        # forward(query, key, value, attn_mask=None)
class FeedForwardNetwork(nn.Module):        # Linear -> ReLU -> Dropout -> Linear
class TransformerDecoderLayer(nn.Module):   # forward(tgt, memory, tgt_mask=None)
    # 结构：self-attn(causal) -> residual+LN -> cross-attn(K/V=memory) -> residual+LN
    #       -> FFN -> residual+LN
# classifiers/transformer.py 里组装：
class CaptioningTransformer(nn.Module)     # visual特征投影 + embedding + PE + decoder + 词表
class VisionTransformer(nn.Module)         # patch切分 -> 线性嵌入 -> +PE -> encoder -> 分类
```

**scaled dot-product attention 的手写核心**：

```
attn = softmax(Q @ K^T / sqrt(d_k) + mask, dim=-1)
out  = attn @ V
# 多头：Q/K/V 先 Linear 到 d，再 reshape (N, T, H, d/H) -> (N, H, T, d/H)
#       各头独立算 attn，最后 concat 回 (N, T, d) 再一个输出 Linear
```

**逐条易错点**：

1. **忘记除 `sqrt(d_k)`**：点积随维度增长，softmax 进饱和区、梯度消失。原论文给的理由：d_k 大时点积方差 ~ d_k，除 sqrt(d_k) 把方差归一。（notebook Inline Question 就是考这个。）
2. **causal mask 方向**：`tgt_mask` 是加性 mask（上三角填 -inf），加在 softmax **之前**。写成乘 0/1 mask 或填在 softmax 之后都是错的。位置 i 只能看 <= i——这是 decoder 自回归约束的矩阵表达。
3. **多头 reshape 顺序**：`(N, T, H, d/H)` 后必须 `transpose(1, 2)` 成 `(N, H, T, d/H)`——在错误的轴上分头，loss 不会崩但模型学不动（overfit 小数据通不过）。
4. **cross-attention 的接线**：Q 来自当前词序列，K/V 来自图像特征（memory）。Q/K/V 全来自词序列就变成了 self-attn——这是概念性错误，不是 bug。
5. **PE 的奇偶下位**：`exp(log(10000) * (2i/d) * -1)` 的向量化写法，`[:, 0::2]` / `[:, 1::2]` 切错列不报错——靠 rel_error 单测抓。
6. **训练 vs 采样**（与 §6.5 完全同构）：训练 teacher forcing 全序列并行 + causal mask；采样自回归逐词，`torch.no_grad()` 包住。
7. **ViT 部分**（2026 新增）：`patch_size` 把 224x224 切块（如 16x16 -> 196 块），`reshape(N, C, H/p, p, W/p, p)` 后轴序调整是最大的坑；cls token 或 mean-pool 的聚合别漏。

**设计理念**：这一题把 L8 讲座的论文（Attention is All You Need + ViT）变成代码。注意它的考核形态变了——**A1/A2 考"你会不会求导"，A3 考"你会不会组装"**。这是行业分工变迁的镜像：模型创新从"设计新的可微算子"变成了"搭更聪明的结构 + 配数据"。A3 的 autograd 依赖不是偷懒，是"到此为止你该会的东西已经会了"。

### 7.2 Self-Supervised Learning：SimCLR（Q2）

**任务**（`simclr/contrastive_loss.py`）：

```python
def sim(z_i, z_j):                  # 余弦相似度 u.v / ||u|| ||v||
def sim_positive_pairs(out_left, out_right):   # 对角位置的正样本相似度 (N,)
def compute_sim_matrix(out):        # 全体 2N x 2N 相似度矩阵
def simclr_loss_naive(out_left, out_right, tau)
def simclr_loss_vectorized(out_left, out_right, tau, device='cuda')
```

**损失**（batch 内 2N 个增广视图，l 与它的增广 r 互为正样本）：

```
L = -1/N * sum_i log( exp(sim(z_i_l, z_i_r)/tau)
                      / sum_{a != i} exp(sim(z_i_l, z_a)/tau) )
```

分母遍历同一侧其余样本 + 另一侧全部（共 2N-1 个），**排除自身**（sim=1 的自比会压塌分布）。

**流程四段**（notebook 顺序）：数据增强（crop/color jitter/blur 等组合）→ encoder（ResNet）+ projection head（MLP，**损失算在投影后的空间**——这是 SimCLR 论文的关键消融）→ 对比预训练 → **冻结 encoder + 只训线性层**（linear probe）在 CIFAR-10 分类，与"无 SSL 直接训"的 baseline 对比。

**逐条易错点**：
1. naive 版双循环跑得慢是故意的——vectorized 版用 `compute_sim_matrix` 一次算全，**两版对拍**（rel_error < 1e-7）才算过。
2. `tau` 的作用：温度越小分布越尖锐，对难负样本惩罚越重——调大调小实验在 notebook 里能直接看到。
3. 增强弱（只用一种变换）时对比学习收益骤减——**多样性增强是正样本构造的一半**。
4. 别把 projection head 输出当最终特征做下游——**probe 用 encoder 输出**。

**设计理念**：监督学习的瓶颈是标注，SSL 的回答是"让数据自己造标签"（同一图的两个增广=正对）。这一题同时给了 CLIP/DINO（Q4）的语义铺垫：**对比目标是当代表征学习的公共损失函数**——图文对（CLIP）、student/teacher（DINO）只是换了正负样本的定义。

### 7.3 DDPM 扩散模型（Q3）

**任务**（`gaussian_diffusion.py`，学生填核心方法；`unet.py` 与 `ddpm_trainer.py` 给定）：

```python
def extract(a, t, x_shape)            # 把 (T,) 的系数按 batch 的 t 索引成 (N,1,1,1)
def q_sample(self, x_start, t, noise) # 前向一步到位加噪
def p_losses(self, x_start, model_kwargs)  # 训练损失：MSE(eps_pred, eps)
def p_sample(self, x_t, t, model_kwargs)   # 反向去噪一步
def predict_start_from_noise(self, x_t, t, noise)   # x0_hat = (x_t - sqrt(1-ab_t) eps)/sqrt(ab_t)
# beta schedules: linear / cosine / sigmoid 三选一对比
```

**三条公式撑起全部**（alpha_t = 1 - beta_t，alpha_bar_t = prod alpha_s）：

```
前向（训练用，解析可得任意 t 的加噪结果）：
  x_t = sqrt(alpha_bar_t) * x_0 + sqrt(1 - alpha_bar_t) * eps,   eps ~ N(0, I)
训练目标（为什么是预测噪声）：
  L = E || eps_theta(x_t, t) - eps ||^2          # 采样 t、eps 全随机，无对抗结构
反向（推理用，从 x_T 到 x_0 迭代 T 步）：
  每步：eps_hat <- UNet(x_t, t)；算均值 mu_t；x_{t-1} = mu_t + sigma_t * z
```

**逐条易错点**：
1. `q_sample` 里 noise 若没传要自己 `randn_like`——前向是随机过程，**复现要固定 seed**。
2. `extract` 的 reshape 目标是 `(N, 1, 1, 1)`：让 per-sample 的 t 系数与 (N, C, H, W) 广播对齐。
3. `p_sample` 的方差项：最后一步（t=0）通常不加噪（z=0）。
4. **训练/采样不对称**：训练一步到位（随机 t），采样必须走完全部 T 步——想清楚为什么可行（每步的训练目标都在学"这一步的去噪"，合起来覆盖整条链）。
5. notebook 末尾的 **Classifier-Free Guidance**：`eps = eps_uncond + w * (eps_cond - eps_uncond)`——无条件与条件网络输出按 w 外推，w>1 强化条件引导；这是把 GAN 的"可控性"平移进扩散的标准做法（Stable Diffusion 同款机制）。

**设计理念**：DDPM 与 GAN 的对照就是 L13/L14 两讲的对照——GAN 用对抗拟合分布但训练不稳定、模式崩塌；扩散把生成拆成 T 个"高斯去噪"小问题，每个都稳、都好算，代价是推理要迭代 T 步。**"把困难问题分解成海量简单可微问题"是这个时代生成模型的共同心法**（也是 autoregressive 的心法）。

### 7.4 CLIP and DINO（Q4，探索型）

**任务**（`CLIP_DINO.ipynb`）：无大量手写实现，主体是**跑预训练模型做实验**——这一份的定位是"会用大模型资产"：

1. **CLIP zero-shot 分类**：图像过 image encoder、`"a photo of a {label}"` 过 text encoder，比余弦相似度——**没有梯度、没有微调，纯检索式分类**。
2. **图文检索**：一张图在文本集里找最近邻（反之亦然）。
3. **DINO attention map**：取 self-attention 的 [CLS]-to-patch 权重 reshape 成热图——**没有人教分割，注意力自己"长出"了物体轮廓**（DINO 论文的著名涌现现象）。
4. **DINO 特征上的简单分割**：冻结特征 + 轻量头，验证"预训练表征的可迁移性"。

**设计理念**：Q4 与 Q2 是一体两面——SimCLR 是"从零体会对比学习"，Q4 是"看工业级对比/蒸馏模型能兑现什么"。它教的是**新的工作方式**：预训练模型当特征提取器，下游只做轻量适配（linear probe / prompt / LoRA 的前身）。这也解释了为什么它最轻：**考核点是判断力（知道用什么、何时用），不是手速。**

---

## 8 讲座层专题补全（作业已不考 / 面试仍在考）

> 以下主题在 2017-2024 版作业里曾是实练题，2025 起移出作业，但 Spring 2026 讲座（L9/L13）仍在讲、面试里出现频率不减。**它们的公式都极短，性价比极高，别因为"不在作业里"就跳过。**

### 8.1 网络可视化与对抗样本（L9 后半；旧 A3 的 Network Visualization）

- **Saliency map**：`dL/dx` 对输入像素求导取绝对值/平方——"网络看哪里"。一行 autograd，一个面试手写题。
- **Fooling image / adversarial example**：固定 W，对**输入 x 做梯度上升** `x += lr * d(target_class)/dx` 直到误分类——人类视觉毫无察觉、网络置信度 99%。对抗鲁棒性的入门（FGM/FGSM 的前身）。
- **DeepDream**：放大某层激活的梯度上升，产生标志性的"狗眼纹理"。
- **特征反演 / Style transfer**：
  - 内容损失 `L_c = ||F(x) - F(p)||^2`（某层特征直接对齐）；
  - 风格损失用 **Gram matrix** `G = F F^T`（通道两两相关，丢空间布局只留"风格统计"），`L_s = sum_l ||G(F(x)) - G(F(s))||^2`；
  - 优化变量是**图像本身**，网络全程冻结——"网络当特征提取器/损失函数用"这个思路后来长成了 CLIP guidance、diffusion 的 classifier guidance。
  - 快速版（perCEPTual feed-forward）就是后来所有实时风格化的做法。

### 8.2 VAE 与 GAN（L13；旧 A3 的 GAN 题）

- **VAE**：encoder 输出 mu/sigma，**重参数化** `z = mu + sigma * eps`（eps~N(0,I)）让采样可微；损失 = **ELBO** = 重构项 - KL(q(z|x) || p(z))。一句话本质：**训练一个"编码到分布"的自编码器，换取潜在空间的生成能力**。KL 项的解析式 `0.5 * sum(mu^2 + sigma^2 - log sigma^2 - 1)` 可现场推。
- **GAN**：min-max 博弈 `min_G max_D E[log D(x)] + E[log(1 - D(G(z)))]`；训练是**交替优化两个目标相反的网络**——不稳定性是结构性的（模式崩塌、震荡），所以工程上全是补丁（谱归一、梯度惩罚、TTUR）。理解 GAN 的价值一半在历史（2020 前的生成主力），一半在对比（为什么扩散赢了：把"一次生成"拆成"千次去噪"，每个子问题都好训）。
- **面试高频对照**："VAE 和 GAN 各自的失败模式？""为什么扩散比 GAN 稳？"——§7.3 的设计理念就是标准答案。

### 8.3 检测与分割（L9；从未做过作业题但属讲座核心）

```
两阶段：R-CNN(候选框+逐框CNN) -> Fast R-CNN(共享卷积) -> Faster R-CNN(RPN 端到端)
单阶段：YOLO / SSD（一次前向直接出框，换精度换速度）
Transformer：DETR（集合预测 + 二分图匹配损失，去 NMS）
分割：FCN(全卷积) -> U-Net(编解码+跳连，医学影像标准) -> Mask R-CNN(实例) -> Panoptic
```

考研 408 不考这些，但 CV 岗 JD 里的"检测/分割经验"指的就是这条线。复习深度建议：**名词 + 一句机制**即可（例如"Faster 的贡献是把候选框生成也变成网络的一个头"），论文级细节按岗位再补。

### 8.4 2026 新增讲座的一句话索引

- **L11 大规模分布式训练**：数据/张量/流水线并行 + activation checkpointing——与 CS149 的 PA5、LLM 训练工程直接接壤，想走训推优化岗重点看。
- **L15 3D 视觉**：NeRF/神经隐式表示（notes 站有 NeRF 学生报告 PDF）。
- **L16 Vision+Language / L17 World Modeling**：多模态与世界模型的前沿入口，按求职方向选读。

### 8.5 训练神经网络的实操清单（L3 讲座的 notes 原典：neural-networks-1/2/3）

这三篇 notes 是整门课被引用最多的材料，其"实操清单"部分等于一份训练故障排查手册，面试聊"你怎么调模型"时的标准答案库：

**架构三选择**（neural-networks-1）：
- 激活函数：**ReLU 是默认**（sigmoid 两端饱和 + 非零中心，tanh 好于 sigmoid 但仍不如 ReLU 家族）；Leaky ReLU 防神经元死亡，GELU 是 Transformer 时代默认。
- 预处理：**零中心化**（减均值）是底线；图像场景不做 PCA/白化（A1 的 CIFAR 均值减一次贯穿全流程）；**权重与输入的尺度要匹配**（大权重配大激活的连锁反应）。
- 初始化：**全零初始化 = 同层神经元永远相同**（对称性问题，必须随机打破）；小随机数配 tanh，He 初始化 `sqrt(2/fan_in)` 配 ReLU（§5.5 已用）。

**babysitting 的数量级表**（neural-networks-3，记住这张比背调参口诀有用）：

| 现象 | 诊断 |
|---|---|
| loss 不降（训练初期就是平线） | lr 太小，或初始化/梯度通道断了 |
| loss 变 nan / 爆炸 | lr 太大（最先查这个）；后期的 nan 优先查 lr、再查除零 |
| train 降、val 不动 | 过拟合——正则/数据增强/early stopping（容量已够） |
| train 也降不动 | 容量不足 / 预处理错误 / lr 不当 |
| 起步 loss 应等于多少 | 分类任务 = log(C)（softmax 的随机基线，§5.2 的 sanity check） |

**超参搜索顺序**：lr 永远第一个（对结果最敏感、log 尺度网格如 1e-4~1e0 采样）；正则强度次之；批量大小与优化器超参最后。随机搜索优于网格搜索（高维时覆盖更均匀，Bergstra & Bengio 的经典结论）。

---

## 9 自测验收清单（③ 验收层）

A1 通过线（全部能独立默写）：

- [ ] 三种 kNN 距离实现都能写，能说清零循环为什么不会爆内存（恒等式）、为什么还要 `clip(..., 0)`。
- [ ] softmax_loss 正反传一次写对，能解释减 max 不改变结果的代数原因；初始 loss ≈ log(C) 的 sanity check。
- [ ] 中心差分公式 + rel_error 判读表（<1e-4 过 / >1e-2 错）；kink、随机层、正则项三坑。
- [ ] two-layer net 六条梯度（dW2/db2/dh/dW1/db1）纸上推完；lr 过大 loss 变 nan 的机理。
- [ ] FullyConnectedNet 的 sandwich 组合、双模式 loss()、reg 不进 bias 的理由。

A2 通过线：

- [ ] BN 前向两态公式 + backward compact 式，能白板推；running stats 更新式；spatial BN 的两步 reshape。
- [ ] inverted dropout 三行代码 + "test 路径必须 identity"的三条理由。
- [ ] conv backward 三件事（dw/db/dx 散射）；pool 反向 winner-take-all；im2col 前后矩阵形状全程说得清；col2im 为什么是加法。
- [ ] PyTorch 三步曲（zero_grad/backward/step）+ train/eval 两态切换。
- [ ] RNN step 公式 + temporal_softmax_loss 的 mask 分母 + teacher forcing 与自回归采样的差异。

A3 通过线（按方向裁剪，默认 CV/多模态全过）：

- [ ] attention 公式（含 sqrt(d_k) 与加性 causal mask）、多头 reshape 顺序、cross-attn 的 Q/K/V 接线。
- [ ] SimCLR 损失分子分母各是什么、projection head 的位置、linear probe 流程。
- [ ] DDPM 三公式（前向一步到位 / 训练预测 eps / 反向逐步去噪）+ CFG 外推式。
- [ ] CLIP zero-shot 分类流程 + DINO attention map 为什么"涌现"分割。

讲座层（面试线）：

- [ ] saliency / fooling 一行梯度上升 + Gram matrix 风格损失。
- [ ] VAE 重参数化 + ELBO 两项；GAN min-max + 两种失败模式。
- [ ] 检测两阶段/单阶段/DETR、分割 FCN/U-Net/Mask R-CNN 各一句机制。

---

## 10 求职视角

### 10.1 岗位地图

| 方向 | 与 cs231n 的关系 | 投入建议 |
|---|---|---|
| CV 算法（检测/分割/3D） | 直接对口：A2 的 conv 手写 + L9 检测分割线 + L15 3D | A1+A2 全做；A3 做 SimCLR；L9/§8.3 补检测分割 |
| 多模态（图文/VLM） | 直接对口：A3 的 captioning + CLIP/DINO 就是岗位日常 | A1+A2 全做；A3 全做且 Transformer/CLIP 精做 |
| LLM / 大模型 | 间接但高价值：attention 手写、LN、对比学习、扩散 CFG 都是 LLM 多模态侧的通用件 | A1+A2 做到 PyTorch 转场即可；A3 只精做 Transformer captioning；再接 CS336 |
| 训推工程/Infra | 部分对口：L11 分布式 + A2 im2col/BN 推理行为是推理引擎的真实考点 | A2 精做（BN/Dropout/conv 推理语义），A1 快过，A3 略读；主力换 CS149/CS336 |

### 10.2 面试高频题对照表（题 -> 本笔记出处）

| 面试题 | 出处 |
|---|---|
| BN 推理时怎么算？为什么两套统计？ | §6.1 |
| 手写 conv 的反向（白板级） | §6.3 |
| dropout 为什么 inverted？train/test 期望论证 | §6.2 |
| softmax 为什么要减 max？写数值稳定的交叉熵 | §5.2 |
| hinge loss 和交叉熵的梯度行为差异 | §5.2 |
| 数值梯度怎么检查？阈值多少？kink 怎么办 | §5.3 |
| kNN 为什么不适合图像分类（两个结构性理由） | §5.1 |
| LSTM 四门公式；梯度消失怎么被缓解 | §6.5 |
| attention 为什么要除 sqrt(d_k)？复杂度多少 O(T^2 d) | §7.1 |
| LN vs BN：Transformer 为什么选 LN | §6.1 + §7.1 |
| 对比学习的损失长什么样，正负样本怎么构造 | §7.2 |
| 扩散为什么训练时预测噪声？和 GAN 比优势 | §7.3 |
| CLIP 怎么做 zero-shot？DINO 的注意力涌现 | §7.4 |
| 训练 loss 降但 val 不降，你的排查顺序 | §2.4 + §5.4 调参纪律 |

### 10.3 简历写法

- **写产出，别写"学过"**。模板：*"完成 Stanford CS231n 全部 3 个作业（2026 版）：numpy 手写 kNN/Softmax/任意深度 FC 网的反向传播并全部通过数值梯度检查（rel_error<1e-6）；手写 BatchNorm/Dropout/卷积正反传与 im2col 加速；PyTorch 实现 Transformer captioning（COCO）与 SimCLR 对比预训练，线性探针较基线提升 X 个点。"*——每个分号都是一条可被追问的实练。
- **别写**"精通深度学习/熟悉 PyTorch"这种没有验证物的空话；作业指标（val acc、probe 提升、overfit 收敛）就是验证物。
- cs231n 的名字在国内简历上辨识度极高（HR 与技术面都认），一行 "Stanford CS231n（2026 版作业全部完成）" 顶三行自我评价。

### 10.4 延伸路线（按目标岗位）

- **LLM 方向**：Karpathy **zero-to-hero**（micrograd 起步，与 cs231n 手工反传完全同频）→ **nanoGPT**（读代码）→ **CS336**（从零造 LM 全栈，互位见 §12）。
- **CV/多模态**：**d2l（动手学深度学习）**补系统理论 → CLIP/BLIP/LLaVA 论文线 → 目标岗位的领域模型（检测/分割/生成按 JD）。
- **理论补强**：CMU **11-785**（autograd 内功 + 理论面最广，互位见 §12）；公式级参考书就是 Goodfellow《Deep Learning》+ cs231n notes 本身。
- 视频/讲义资产：2017 版 Karpathy 录播（YouTube 官方 playlist，社区公认入门最佳）+ cs231n.github.io notes（中文翻译版流传极广，但**以英文原文为准**，翻译版年份参差）。

---

## 11 执行方案（ROI 排序）

### 11.1 总原则

**初试 2026-12 之前：本项目零动手投入。** cs231n 与 408 四门课（数据结构/组成原理/OS/网络）在初试没有任何交集，动手训练周期长达数周，属于纯粹的复试/求职资产。初试前唯一允许的接触是：睡前刷 cs231n notes 当"轻松读物"（尤其 backprop 与 neural-networks 三篇——它们同时是考研数学矩阵求导的活习题）。

**零动手期间的纯阅读路线**（每篇 30-60 分钟，按此顺序）：

| 顺序 | notes | 读什么 |
|---|---|---|
| 1 | python-numpy-tutorial | 只读 broadcasting/vectorization 两节（写 408 无关，为 A1 热身） |
| 2 | classification | 图像分类 pipeline + kNN 的三个教训 |
| 3 | linear-classify | 线性分类器三视角（代数/视觉/几何）+ hinge vs softmax |
| 4 | optimization-1 | 数值/解析梯度、SGD——与 §5.3 对照 |
| 5 | optimization-2（backprop） | **全课最核心一篇**：链式法则、circuits、梯度流模式（add/copy/max/门控） |
| 6 | neural-networks-1/2/3 | 1=架构；2=预处理/初始化/BN/Dropout；3=梯度检查/调参/优化器 |
| 7 | convolutional-networks | 卷积/池化/尺寸公式/参数量账本 |
| 8 | understanding-cnn / transfer-learning | 可视化直觉 + 微调三板斧（冻结/finetune/特征复用） |

**初试后（12 月底 - 3 月复试窗口）动手，推荐顺序与工时**：

| 阶段 | 内容 | 预估工时 | 验收 |
|---|---|---|---|
| 第 1 周 | A1：kNN → Softmax → 梯度检查 → two-layer net | 15-20h | §9 A1 清单 |
| 第 2 周 | A1 收尾：FullyConnectedNets + features；A2 的 BN/LayerNorm | 15h | 梯度检查全绿 |
| 第 2-3 周 | A2：Dropout → ConvNets(naive+im2col) → PyTorch on CIFAR-10 | 20-25h | val 65%+ |
| 第 3-4 周 | A2：RNN captioning（含 overfit 与采样） | 10-12h | 小数据 overfit 逐字复现 |
| 第 4 周+ | A3 按方向裁剪（见下） | 15-30h | §9 A3 清单 |

A3 裁剪规则：**CV/多模态方向全做**（顺序 Transformer → SimCLR → DDPM → CLIP/DINO）；**LLM 方向只精做 Transformer captioning**（与 zero-to-hero 的 GPT 实现互为印证），DDPM/CLIP 读 notebook + §7 讲义级即可；**Infra 方向 A3 可整体略过**，把时间还给 CS149/分布式。

### 11.2 动手起步清单

```bash
# 官方 starter（2026 版，勿用网上旧 fork——版本对不上，见 §1.3/§1.4）
mkdir -p ~/develop/learning/learning-408/cs231n && cd ~/develop/learning/learning-408/cs231n
curl -LO https://cs231n.github.io/assignments/2026/assignment1.zip
curl -LO https://cs231n.github.io/assignments/2026/assignment2.zip
curl -LO https://cs231n.github.io/assignments/2026/assignment3.zip
# 官方工作流是 Google Colab（A3 明确 GPU 必需）；本地不装依赖也完全可以：
# 把 zip 上传到 Colab 直接开做，A1/A2 的 CPU 部分本地 Jupyter 亦可。
```

- 环境零配置：A1/A2 用 Colab CPU 即可，A3 的 SimCLR/DDPM 需要 GPU（Colab 免费档够用）。
- **每天开工前先跑一遍昨天的 notebook**（Colab 会断连丢状态，官方 handout 提醒的第一件事）。
- 遇到卡壳：先 §2.4 的五步流程定位（多半是 cache 顺序/reshape 轴/reg 忘加三巨头），再用梯度检查二分定位是 forward 还是 backward 的错。

### 11.3 与本仓库其他笔记的联动

- 反向传播的矩阵求导细节 → 对应考研数学线代复习（互为练习）。
- A2 的 BN/Dropout/conv 推理语义 → 与训推工程面试题（CS149 PA5 的邻域）共享弹药。
- A3 的 Transformer → CS336/11-785 的共同前置（§12）。

---

## 12 与另两门课的互位（一句话版）

- **cs231n** = 深度学习共同底座：手工反传 + CNN 时代经典 + （2026 版）Transformer/对比/扩散的现代三件套。**先做。**
- **CS336** = LLM 全栈：从数据、tokenizer、注意力实现到训练系统，把"造一个 LM"完整走一遍。**cs231n 的 A3 Transformer 是它的热身。**
- **CMU 11-785** = autograd 内功 + 理论面最广：第一周就从反向传播框架写起，覆盖模型族最全。**理论补强/学术向选它。**
- 三者的公约数恰好是 §3.1 的那句话：**反向传播是手工微积分，框架只是它的自动展开**——谁先让你亲手推一遍 `dL/dW`，谁就是你的第一门课。

---

## 13 证据来源（本次调研实际访问，2026-10-22）

**官方课程站（Spring 2026 现行口径）**

1. `https://cs231n.stanford.edu/` —— Spring 2026 主页：讲师名单（Fei-Fei Li / Ehsan Adeli / Justin Johnson / Zane Durante / Tiange Xiang）、成绩构成（Assignments 45% / Midterm 20% / Final Project 35% / Participation 3% extra）、先修要求、late policy、"往年录播在 YouTube 公开"的官方说明。
2. `https://cs231n.stanford.edu/schedule.html` —— Spring 2026 完整 18 讲 schedule（含每讲 slides 链接与作业发布/截止日期：A1 out 4/2 due 4/16；A2 out 4/23 due 5/8；A3 out 5/14 due 5/28）。
3. `https://cs231n.stanford.edu/assignments.html` —— A1/A2/A3 官方构成与分值（12%/18%/15%）、协作与 AI 使用政策。
4. `https://cs231n.stanford.edu/2017/`、`/2024/`、`/2025/`、`/2020/syllabus.html` —— 历年页面标题与大纲（2017 仍名 "Convolutional Neural Networks for Visual Recognition"，2024 起已更名 "Deep Learning for Computer Vision"；2020 syllabus 用于对照旧讲座主线）。

**Notes 站与作业 handout（cs231n.github.io）**

5. `http://cs231n.github.io/` —— notes 导航主页（2026 口径）：Module 0 Python/Numpy；Module 1 classification / linear-classify / optimization-1 / optimization-2(backprop) / neural-networks-1/2/3 / neural-networks-case-study；Module 2 convolutional-networks / understanding-cnn / transfer-learning；学生贡献帖（RNN 等）。页面同时列出 2026 三个作业的官方摘要。
6. `https://cs231n.github.io/assignments2026/assignment1/`、`assignment2/`、`assignment3/` —— 2026 版三份 handout 的 Q 清单、截止日期、zip 下载链接、提交方式。
7. `https://cs231n.github.io/assignments/2026/assignment1.zip`、`assignment2.zip`、`assignment3.zip` —— **实际下载并解包**，核对了全部 notebook 文件名与 `cs231n/` 库的函数/类签名（kNN 三方法、layers.py 22 个函数含 svm_loss/batchnorm/dropout/conv/pool/spatial/groupnorm、TwoLayerNet/FullyConnectedNet/ThreeLayerConvNet/CaptioningRNN、rnn_layers_pytorch 的 `_numpy` 系、transformer_layers 的 5 个类、simclr/contrastive_loss 的 5 个函数、gaussian_diffusion 的 q_sample/p_losses/p_sample 及三种 beta schedule）。
8. `https://cs231n.github.io/assignments2025/assignment1/`（及 2/3）、`assignments2024/...`、`assignments2023/...` —— 逐年 handout 页面抓取比对，构成 §1.4 版本年表（2024→2025 的 A1 删 SVM、A2 换入 RNN captioning、A3 从 RNN+GAN 换成 DDPM+CLIP/DINO）。

**GitHub**

9. `https://github.com/cs231n/cs231n.github.io` —— notes 源文件仓（11.1k stars；文件列表含 transformers.md / attention.md / generative-modeling.md / nerf.md / adversary-attacks.md / convnet-tips.md 等延伸 notes）。
10. `https://api.github.com/orgs/cs231n/repos` —— org 仓库清单：仅 `cs231n.github.io` 与 `gcloud` 两仓，**assignment1/2/3 仓已不存在**（`/repos/cs231n/assignment1` 返回 404）——§1.3 "旧仓已下架"的依据。

**未采用/存疑项声明**

- 网上流传的 `cs231n/assignment1` 等第三方 fork、各年中文翻译版 notes：**未**作为事实来源引用（版本年份不明）。
- 讲座内部 slides 内容未逐页核对（仅以 schedule 页标题为准）；2017 Karpathy 录播的具体年份期次以课程主页"previous years"指引为准，未逐一验看。
