# CS231N · 视觉识别 · 设计文档

> 本文是该项目的设计说明，不是教程。
> 大纲见 `OUTLINE.md`，一小时上手见 `QUICK.md`，详细记录见 `NOTES.md`。

## 一、定位与边界

本项目是视觉识别的**从零实现层**：用 NumPy 手写前向与反向传播，覆盖 kNN、SVM、Softmax、两层全连接网络、卷积与池化（im2col）、BatchNorm、Dropout，以及检测与分割的最小闭环。它的价值在于把 CS231n 的公式变成可梯度校验、可复现实验的代码，而非调包跑分。

不解决：大规模训练与分布式、工程部署与推理优化、RNN/Transformer/自监督、框架级自动微分。与《机器学习理论》项目的分工是：后者负责推导与泛化分析，本项目负责数值实现与梯度正确性；与后续 PyTorch 项目的分工是：本项目暴露“手写”的代价（显存、速度、数值稳定），后者验证工程化替代方案。

## 二、整体架构

模块划分与职责：

- `layers/`：`Linear`、`ReLU`、`SVM`、`Softmax`、`Conv`、`MaxPool`、`BatchNorm`、`Dropout`，每个类提供 `forward` 返回 `(out, cache)`、`backward` 返回 `(dx, dW, db)`。
- `models/`：`TwoLayerNet`、`SmallConvNet`，只做层组合与前向/反向调度，不含更新逻辑。
- `solvers/`：SGD、Momentum、Adam，按 `param, grad` 更新并维护状态。
- `utils/`：`im2col/col2im`、数值梯度检查器、CIFAR-10 数据加载、可视化。
- `tasks/`：分类训练脚本、检测（IoU/NMS/mAP）、分割（像素交叉熵/IoU）。

调用方向单向：`data → model.forward → loss → model.backward → solver.step`，梯度检查器独立包裹任意 `layer` 或 `model`，不进入训练主链。

## 三、技术选型与理由

- **Python 3.10 + NumPy**：手写反向传播必须显式持有计算图，NumPy 只提供张量与 BLAS；用 PyTorch 会自动微分，训练目标被消解。
- **im2col + GEMM 而非朴素多重循环**：把卷积转成 $(N\cdot H_{out}W_{out},\,C k_h k_w)$ 的矩阵乘，直接调用 BLAS；代价是显存放大 $k_h k_w$ 倍，用分块 batch 控制。
- **pytest 而非 unittest**：梯度检查需要对每层参数化断言相对误差，`pytest.mark.parametrize` 更直接。
- **CIFAR-10 子集而非 MNIST**：MNIST 上线性模型接近饱和，无法区分 BatchNorm、Dropout 的收益。
- **固定随机种子 + 单一配置文件**：保证梯度检查与准确率判据可复现，避免“换台机器结论反转”。

## 四、数据流

一次典型训练步：

1. 输入 `X`：形状 $(N,C,H,W)$，CIFAR-10 为 $(128,3,32,32)$。
2. `Conv.forward`：`im2col` 得到 `cols` $(N H_{out}W_{out},\,C k_h k_w)$，与 `W` $(F,\,C k_h k_w)$ 做 GEMM，reshape 为 $(N,F,H_{out},W_{out})$；`cache` 保存 `cols`、`X.shape`、超参。
3. `ReLU → MaxPool`：池化 `cache` 保存 argmax 掩码，反向按掩码路由梯度。
4. `Linear → BatchNorm → ReLU → Dropout`：BN 训练时用 batch 统计量并更新 running mean/var；Dropout 用 inverted 缩放。
5. 输出 `scores` $(N,10)$，接 Softmax 交叉熵得标量 `loss`。
6. `backward` 逐层回传，`col2im` 把 `dcols` 散射回 `dX`（重叠位置用 `+=`）。
7. `solver.step` 更新参数，记录 `loss` 与训练/验证准确率。

关键数据结构：`X`、`W`、`cols`、`cache` 元组、`running_mean/var`、`mask`。

## 五、章节目录与知识点映射

| 章 | 内容 | 涉及的知识点 | 与考纲或前置项目的关系 |
|---|---|---|---|
| 1 | kNN 分类器 | 用 $\|x-y\|^2=\|x\|^2-2x\cdot y+\|y\|^2$ 展开距离矩阵；`argpartition` 取 top-k；交叉验证选 k | 前置：距离度量；对应考纲的分类器基础 |
| 2 | 多类 SVM | hinge loss $L_i=\sum_{j\ne y_i}\max(0,s_j-s_{y_i}+\Delta)$；次梯度；$\lambda$ 与学习率的耦合 | 前置：线性模型；与 Softmax 对照 |
| 3 | Softmax 与交叉熵 | log-sum-exp 数值稳定；梯度 $\hat p-y$；概率校准 | 对应考纲的损失函数 |
| 4 | 两层全连接网络 | 链式法则手写反向；解析梯度对数值梯度的相对误差；ReLU 死区与 Xavier 初始化 | 前置：微积分；为卷积反向做铺垫 |
| 5 | 卷积与池化 | 输出尺寸 $\lfloor (H+2p-k)/s\rfloor+1$；im2col 与 col2im 的索引重叠；max pooling 的 argmax 路由 | 对应考纲的卷积；检测与分割的基元 |
| 6 | BatchNorm 与 Dropout | 训练/推理双模式；running mean/var 的动量更新；inverted dropout 的缩放；BN 反向的 batch 维求和 | 对应考纲的归一化与正则化 |
| 7 | 检测最小闭环 | IoU 计算；NMS 的排序与抑制阈值；mAP 的积分定义；区域提议简化为 selective search | 后续检测项目的前置 |
| 8 | 分割最小闭环 | 转置卷积/反池化上采样；逐像素交叉熵；像素准确率与 mIoU | 后续分割项目的前置 |
| 9 | 梯度检查与调参 | 中心差分 $(f(x+h)-f(x-h))/2h$；相对误差判据；学习率扫描与早停 | 全项目的质量闸门 |

## 六、验收判据

- 梯度检查：SVM、Softmax、两层网络、Conv、MaxPool、BatchNorm、Dropout 共 **16/16** 项通过，相对误差 $<1\times10^{-7}$。
- 正确性：im2col 卷积与朴素循环实现的输出最大绝对差 $<1\times10^{-9}$；`col2im(im2col(X))` 与 `X` 逐元素相等。
- 性能：batch=128、$3\times32\times32$ 输入、$16$ 个 $3\times3$ 卷积核时，im2col 相对四重循环加速 $\ge 20\times$；单步峰值内存 $<2$ GB。
- 分类：CIFAR-10 每类 500 张训练、100 张验证，两层网络验证准确率 $\ge 38\%$；SmallConvNet（含 BN）验证准确率 $\ge 55\%$。
- 正则化：同配置下加 BatchNorm 使达到 50% 验证准确率的 epoch 数减少 $\ge 30\%$；Dropout $p=0.5$ 使训练-验证准确率差缩小 $\ge 3$ 个百分点。
- 检测/分割：IoU 阈值 0.5 下 NMS 输出框数误差 $\le 1$；分割验证集像素准确率 $\ge 0.70$、mIoU $\ge 0.40$。

## 七、风险与已知坑

梯度检查最易失败在不可微点：ReLU 在 0 附近、max pooling 平局、BN 的 batch 统计量参与反向。Softmax 未减最大值会溢出为 `nan`。`col2im` 忘记用 `+=` 会丢失重叠梯度；卷积输出尺寸向下取整写错会差一个像素。Dropout 推理未关闭、BN 推理误用 batch 统计量，会让验证准确率骤降。kNN 的 $N\times N$ 距离矩阵在 5 万样本时约 20 GB，必须分块。检测的 NMS 阈值与 mAP 积分口径不统一会导致指标不可比。

## 八、与其他项目的关系

前置：线性代数、概率论、微积分与 Python/NumPy；可与机器学习理论项目并行，互为推导与实现的验证。后续：目标检测项目复用 IoU/NMS/mAP 与本章的卷积特征提取；分割项目复用上采样与像素级损失；PyTorch 项目复用同一套数据管线与验收数字，作为“手写 vs 框架”的对照基线。可复用模块：`im2col/col2im`、数值梯度检查器、`Solver`、CIFAR-10 加载与可视化。
