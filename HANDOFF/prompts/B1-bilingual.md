# 任务 B1 · 项目文档双语化（只做大纲，不做细节）

## 范围（用户已定边界）

用户原话：「只双语化**关键的大纲、系统设计**那些，**不要双语化细节部分**，边界你自己感觉。」

具体到本仓：

| 文件 | 做不做 | 理由 |
|---|---|---|
| `OUTLINE.md`（大纲 + 目标功能设计） | **做** | 要精读、要对照课程原版 |
| `NOTES.md`（1 万–8 万字细节记录） | **不做** | 成本极高，几乎不会回头读 |
| 已删除的 `QUICK.md` | — | 命令与操作步骤，双语无价值 |

## 产出

每个项目一个 `<项目>/OUTLINE.bi.md`，**不覆盖原中文文件**。

共 9 个：`kaoyan/projects/{csapp,6824,algorithm,nand2tetris}/` +
`projects/{cs231n,cs336,cs149,cmu11785,pku-cg}/`。

## 格式（严格）

原文标题原样保留；标题下**每一句一对引用块**，英文在前、中文照抄在后：

```markdown
## 一、这个项目在做什么

> This project is the self-built implementation of four CMU 15-213 labs.
>
> 本项目是 CMU 15-213 四个 lab 的自建实现。

> Each lab verifies one abstraction that textbooks only describe in prose.
>
> 每个 lab 验证一个教材只用文字描述的抽象。
```

规则：
1. **中文一个字都不许改**，按句断开即可。
2. 一句一对，不许两句合成一对。
3. 列表、表格、代码块、命令、变量名**不翻译**，原样保留。
4. 术语首次出现，中文补英文原词：空闲链表（free list）。
5. 每块末尾 `### 生词`，8–15 个词：`- word 词性. 中文释义`。

## 切块（这里最容易失败）

- 原文按 `## ` 小节累积切，**每块不超过 3000 字符原文**（输出约为原文 1.8 倍）
- 一个 `OUTLINE.md`（2000–3500 字）通常切成 **2 块**
- 超过 3000 字符不切，末段会丢句

## 生成方式

按 `SCHEDULING.md`：异步派发，`MAXPAR=3`，用 `--messages-file` 传长 prompt。
`deepseek-v4.1-flash-1017` 即可，不需要第二个模型。

## 交付检查

```bash
cd notebook
for p in projects/*/ kaoyan/projects/*/; do
  n=$(basename "$p")
  bi="$p/OUTLINE.bi.md"
  if [ -f "$bi" ]; then
    pairs=$(grep -c "^> " "$bi")
    printf "%-12s %3s 引用行  生词表 %s\n" "$n" "$pairs" \
      "$(grep -q '### 生词' "$bi" && echo 有 || echo 缺)"
  else
    printf "%-12s 未生成\n" "$n"
  fi
done
```

**判据**：10 个都有 `OUTLINE.bi.md`；引用行数为偶数（成对）；每份都有生词表。

## 一个容易忽略的点

双语版是**给阅读用的**，不是给背诵用的。所以：
- 英文要地道，不要逐字直译（"把某事做" 写成 "do something" 而不是 "carry out the matter"）
- 中文保持原文的专业表达，不要为了"对得上"而简化
- 如果原句太长（超过 40 字），拆成两句分别对照，不要硬凑成一对