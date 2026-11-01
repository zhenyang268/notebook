#!/usr/bin/env python3
"""第四步：全库路径改写。旧 ipynb / modules 引用 -> 新 md 路径。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 块级精确映射（只用于 ds/ROADMAP.md 的十个子块标题）
BLOCK = {
    "块1": "`ds/02-01`…`ds/02-03`（顺序表 / 链表）",
    "块2": "`ds/03-01`…`ds/03-03`（栈 / 队列 / 数组）",
    "块3": "`ds/02-04-串与KMP.md`",
    "块4": "`ds/04-01`…`ds/04-06`（树与二叉树六节）",
    "块6": "`ds/06-03`…`ds/06-06`（BST / AVL / 红黑树 / B 与 B+）",
    "块7": "`ds/05-01`…`ds/05-07`（图七节）",
    "块8": "`ds/06-01`、`ds/06-02`、`ds/06-07`（顺序 / 折半 / 散列）",
    "块9": "`ds/07-01`…`ds/07-08`（排序八节）",
    "块10": "无独立 KP —— 41 题专项散落在各章 ③ 验收层",
}

# 通用映射
MAP = {
    "00-计算机系统概述.ipynb": "`os/01-01`…`os/01-05`",
    "01-数据表示与编码.ipynb": "`co/02-01`…`co/02-03`",
    "02-运算与ALU.ipynb": "`co/02-05-乘除运算与ALU.md`",
    "03-存储层次与Cache.ipynb": "`co/03-05-Cache.md`",
    "04-内存与虚拟内存.ipynb": "`os/03-01`、`os/03-02`",
    "05-磁盘与文件系统.ipynb": "`os/04-01`…`os/04-03`",
    "06-指令系统与汇编.ipynb": "`co/04-01`…`co/04-04`",
    "07-CPU与数据通路.ipynb": "`co/05-01`…`co/05-05`",
    "08-流水线.ipynb": "`co/05-06-指令流水线.md`",
    "09-总线与IO.ipynb": "`co/06-01`、`co/06-02`、`co/07-01`…`co/07-04`",
    "10-进程与线程.ipynb": "`os/02-01-进程与线程.md`",
    "11-调度.ipynb": "`os/02-02-调度.md`",
    "12-同步与互斥.ipynb": "`os/02-03-同步与互斥.md`",
    "13-死锁.ipynb": "`os/02-04-死锁.md`",
    "14-网络分层与链路层.ipynb": "`net/01-02`、`net/03-01`…`net/03-06`",
    "15-网络层.ipynb": "`net/04-01`…`net/04-06`",
    "16-传输层.ipynb": "`net/05-01`…`net/05-05`",
    "17-应用层.ipynb": "`net/06-01`…`net/06-04`",
    "18-线性结构.ipynb": "`ds/02-01`…`ds/03-03`",
    "19-树与堆.ipynb": "`ds/04-01`…`ds/06-06`",
    "20-图.ipynb": "`ds/05-01`…`ds/05-07`",
    "21-查找与排序.ipynb": "`ds/06-01`…`ds/07-08`",
    "22-算法设计与复杂度.ipynb": "`ds/ROADMAP.md` §块10（无独立 KP）",
    "23-计算机数学基础.ipynb": "（已取消：与 408 大纲无对应章节）",
    "临时问题.ipynb": "`temp.md`",
    # modules 文档
    "modules/408/CS144.md": "`projects/cs144.md`",
    "modules/408/CS149.md": "`projects/cs149.md`",
    "modules/408/CSAPP.md": "`projects/csapp.md`",
    "modules/408/NAND2TETRIS.md": "`projects/nand2tetris.md`",
    "modules/408/6824.md": "`projects/6824.md`",
    "modules/408/CS336.md": "`projects/cs336.md`",
    "modules/408/CS231N.md": "`projects/cs231n.md`",
    "modules/408/CMU11785.md": "`projects/cmu11785.md`",
    "modules/408/PKU-CG.md": "`projects/pku-cg.md`",
    "modules/408/数据结构.md": "`exam/408/ds/ROADMAP.md`",
    "modules/408/操作系统.md": "`exam/408/os/ROADMAP.md`",
    "modules/408/进程.md": "`exam/408/os/ROADMAP.md`",
    "modules/408/网络.md": "`exam/408/net/ROADMAP.md`",
    "modules/408/树型查找-讲义.md": "`exam/408/ds/06-00-树型查找总览.md`",
    "modules/408/外部排序-讲义.md": "`exam/408/ds/07-07-外部排序.md`",
    "modules/Math1/高等数学.md": "`exam/math1/ROADMAP.md`",
    "modules/Math1/概率论与数理统计.md": "`exam/math1/ROADMAP.md`",
    "modules/408/": "`exam/408/`",
    "modules/<科目>/<模块>.md": "`exam/<科目>/<子科>/ROADMAP.md`",
}

TARGET_FILES = (
    list((ROOT / "exam").rglob("*.md"))
    + list((ROOT / "syllabus").rglob("*.md"))
    + list((ROOT / "projects").rglob("*.md"))
)


def main():
    total = 0
    for p in TARGET_FILES:
        s = orig = p.read_text(encoding="utf-8")
        # 1) 块级标题先处理（ds/ROADMAP.md 专用）
        if p.name == "ROADMAP.md" and p.parent.name == "ds":
            def fix_block(m):
                blk = m.group(1)
                return f"{m.group(0).split('→')[0].rstrip()} → {BLOCK[blk]}" if blk in BLOCK else m.group(0)
            s = re.sub(r"^(### 块\d+ [^\n]*?→\s*`[^`]+`)$", fix_block, s, flags=re.M)
        # 2) 通用替换（长键优先，避免 modules/408/ 提前吃掉子路径）
        for old in sorted(MAP, key=len, reverse=True):
            s = s.replace(f"`{old}`", MAP[old]).replace(old, MAP[old])
        if s != orig:
            p.write_text(s, encoding="utf-8")
            total += 1
    print(f"改写文件数：{total}")


if __name__ == "__main__":
    main()
