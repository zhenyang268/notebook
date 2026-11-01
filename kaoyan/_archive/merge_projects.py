#!/usr/bin/env python3
"""第二步迁移：modules/408 下的工程文档 -> projects/，并补「对位考点」单向引用表。

规则：projects/*.md 里只允许出现 KP 号与考点名称，不复制 exam/ 的正文；
exam/ 的正文里不允许出现工程仓名（由 tools/lint.py 检查）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules" / "408"
PROJ = ROOT / "projects"

# 目标 -> (原文件, 标题, 一句话定位, 对位考点表行)
JOBS = [
    ("cs144.md", "CS144.md", "CS144 · 从零实现 TCP/IP 协议栈",
     "斯坦福 CS144：在用户态用 C++ 重写一个能跑通真实互联网的 TCP。",
     [("滑动窗口 / 可靠传输 / 重传", "`408-NET-0504` TCP 可靠传输与流量控制"),
      ("连接建立与释放、状态机", "`408-NET-0503` TCP 连接管理"),
      ("链路层 ARP 与网络接口", "`408-NET-0404` 分片与配套协议"),
      ("路由表与最长前缀匹配", "`408-NET-0403` IPv4 地址与子网划分"),
      ("分层、封装与解封装", "`408-NET-0102` 分层与参考模型"),
      ("检错与校验和", "`408-NET-0302` 差错控制")]),
    ("cs149.md", "CS149.md", "CS149 · 并行计算",
     "CMU CS149：并行算法、work-span 模型、GPU 与多核性能分析。",
     [("多核与共享内存模型", "`408-CO-0507` 多处理器基本概念"),
      ("Cache 一致性与 false sharing", "`408-CO-0305` Cache"),
      ("线程池与锁", "`408-OS-0203` 同步与互斥"),
      ("任务调度与负载均衡", "`408-OS-0202` CPU 调度"),
      ("并行 BFS / 图处理", "`408-DS-0503` 图的遍历")]),
    ("csapp.md", "CSAPP.md", "CSAPP · 系统级编程实验",
     "《深入理解计算机系统》八个 lab：从位运算到代理服务器。",
     [("datalab 位运算", "`408-CO-0201` 数制与定点编码"),
      ("IEEE 754 边界值", "`408-CO-0206` 浮点数表示"),
      ("cachelab 映射与分块", "`408-CO-0305` Cache"),
      ("malloclab 与隐式空闲链表", "`408-OS-0301` 内存管理基础"),
      ("栈帧与缓冲区溢出", "`408-CO-0403` 机器级代码表示"),
      ("archlab 数据通路", "`408-CO-0503` 数据通路"),
      ("shlab 信号与进程回收", "`408-OS-0201` 进程与线程"),
      ("proxylab HTTP 代理", "`408-NET-0604` WWW 与 HTTP")]),
    ("nand2tetris.md", "NAND2TETRIS.md", "nand2tetris · 从与非门到俄罗斯方块",
     "用 NAND 搭出 CPU、汇编器、VM、编译器和操作系统。",
     [("Hack 指令格式", "`408-CO-0401` 指令格式"),
      ("ALU 的六个控制位", "`408-CO-0205` 乘除运算与 ALU"),
      ("冯·诺依曼 vs 哈佛", "`408-CO-0102` 层次结构"),
      ("单周期数据通路", "`408-CO-0503` 数据通路"),
      ("内存映射 I/O", "`408-CO-0701` I/O 系统概述"),
      ("ch12 堆管理与 free list", "`408-OS-0301` 内存管理基础")]),
    ("6824.md", "6824.md", "6.824 · 分布式系统（Raft）",
     "MIT 6.824：Raft 一致性、KV 服务与分片。",
     [("一把大锁与通道同步", "`408-OS-0203` 同步与互斥"),
      ("goroutine 与线程模型", "`408-OS-0201` 进程与线程"),
      ("超时与定时器", "`408-OS-0202` CPU 调度")]),
]

# 只有模块文档、没有 cell 的四份：新建 projects 文件
NEW_ONLY = [
    ("cs336.md", "CS336.md", "CS336 · 语言模型从零实现",
     "斯坦福 CS336：BPE、Transformer、FlashAttention、分布式训练。",
     [("—", "与 408 初试**零重叠**，初试前不看")]),
    ("cs231n.md", "CS231N.md", "CS231N · 视觉识别",
     "斯坦福 CS231N（2026 版口径）：CNN、Transformer、自监督、扩散。",
     [("—", "与 408 初试**零重叠**，初试前不看")]),
    ("cmu11785.md", "CMU11785.md", "11-785 · 深度学习导论",
     "CMU 11-785：MyTorch 层式实现 + 语音任务受控实验。",
     [("—", "与 408 初试**零重叠**，初试前不看")]),
    ("pku-cg.md", "PKU-CG.md", "北大图形学 · 渲染与游戏",
     "李胜《计算机图形学》：变换/投影/光栅化 → 引擎 → 联网。",
     [("变换矩阵与齐次坐标", "`M1-LA-0503` 实对称矩阵 / 相似对角化"),
      ("投影与正交基", "`M1-LA-0303` 内积与正交"),
      ("光照与梯度", "`M1-HS-0503` 方向导数与梯度")]),
]

PROJ_HEAD = """# {title}

> **工程线（兴趣向，非考试范围）**。本文件不承担复习任务。
> {blurb}
>
> **单向引用约定**：本文提到考点时**只写 KP 号与考点名**，不复制 `exam/` 的正文；
> `exam/` 的文件里也不出现本文件的工程名。两边互不依赖，只共享主键。

## 对位考点（单向引用）

| 本文段落 | 对应 KP |
|---|---|
{rows}

---

"""


def compose(dst_name, src_name, title, blurb, rows, keep_existing_cells=True):
    dst = PROJ / dst_name
    src = MOD / src_name
    body = ""
    if src.exists():
        text = src.read_text(encoding="utf-8").split("\n")
        # 去掉原文件的一级标题及其后的引用块（保留正文）
        i = 0
        while i < len(text) and (text[i].startswith("# ") or text[i].strip() == ""):
            i += 1
        # 跳过紧随标题的 > 引用块
        while i < len(text) and text[i].startswith(">"):
            i += 1
        body = "\n".join(text[i:]).strip()

    cells = ""
    if keep_existing_cells and dst.exists():
        old = dst.read_text(encoding="utf-8")
        parts = old.split("\n---\n\n", 1)
        if len(parts) == 2 and parts[1].strip():
            cells = ("\n---\n\n## 迁移归档：来自旧 ipynb 的工程笔记（2026-10-28）\n\n"
                     + parts[1].strip() + "\n")

    rows_md = "\n".join(f"| {a} | {b} |" for a, b in rows)
    head = PROJ_HEAD.format(title=title, blurb=blurb, rows=rows_md)
    out = head + (body + "\n" if body else "") + cells
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding="utf-8")
    n = len(out.split("\n"))
    print(f"  {dst_name:22s} {n:5d} 行" + ("  (含迁移 cell)" if cells else ""))


if __name__ == "__main__":
    print("合并工程文档 + 迁移笔记：")
    for dst, src, title, blurb, rows in JOBS:
        compose(dst, src, title, blurb, rows)
    print("新建仅文档的工程文件：")
    for dst, src, title, blurb, rows in NEW_ONLY:
        compose(dst, src, title, blurb, rows, keep_existing_cells=False)
