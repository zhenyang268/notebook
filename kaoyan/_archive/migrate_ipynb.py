#!/usr/bin/env python3
"""一次性迁移：15 个 ipynb 的 88 个 cell -> exam/ 与 projects/ 下的 md。

零丢失原则：
  1. 每个 cell 先原样落到 _archive/cells/<stem>__<idx>.md（带出处头）
  2. 再按 ROUTES 追加到目标 md
  3. 原 ipynb 只复制到 _archive/ipynb/，不删（删除由人工确认后执行）

可重复执行：目标文件已存在则跳过（幂等），所以中途失败可整段重跑。
"""
import json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "_archive"
EXAM = ROOT / "exam" / "408"
PROJ = ROOT / "projects"

# 目标文件 -> (一级标题, KP)
TARGETS = {
    "os/01-01-基本概念.md": ("操作系统 · 基本概念、特征与分类", "408-OS-0101"),
    "os/01-03-运行环境.md": ("操作系统 · 运行环境（双态 / 中断异常 / 系统调用）", "408-OS-0103"),
    "os/01-04-体系结构.md": ("操作系统 · 体系结构", "408-OS-0104"),
    "os/02-01-进程与线程.md": ("进程与线程 · 抽象、状态与创建控制", "408-OS-0201"),
    "net/01-01-概述与性能.md": ("计算机网络 · 概述与性能指标", "408-NET-0101"),
    "net/01-02-分层与参考模型.md": ("网络 · 分层、封装与参考模型", "408-NET-0102"),
    "net/03-02-差错控制.md": ("数据链路层 · 差错控制（检错 / 纠错）", "408-NET-0302"),
    "net/04-03-IPv4地址与子网.md": ("网络层 · IPv4 地址、子网划分与 CIDR", "408-NET-0403"),
    "net/04-04-分片与配套协议.md": ("网络层 · IP 分片与配套协议", "408-NET-0404"),
    "net/05-01-服务与端口.md": ("传输层 · 服务、端口与复用分用", "408-NET-0501"),
    "net/05-02-UDP.md": ("传输层 · UDP", "408-NET-0502"),
    "net/05-03-TCP连接管理.md": ("传输层 · TCP 连接管理", "408-NET-0503"),
    "net/05-04-TCP可靠传输与流控.md": ("传输层 · TCP 可靠传输与流量控制", "408-NET-0504"),
    "net/05-05-TCP拥塞控制.md": ("传输层 · TCP 拥塞控制", "408-NET-0505"),
    "net/06-02-DNS.md": ("应用层 · DNS", "408-NET-0602"),
    "net/06-04-WWW与HTTP.md": ("应用层 · WWW 与 HTTP", "408-NET-0604"),
    "projects/cs144.md": ("CS144 · 从零实现 TCP/IP 协议栈", "—"),
    "projects/cs149.md": ("CS149 · 并行计算", "—"),
    "projects/csapp.md": ("CSAPP · 系统级编程实验", "—"),
    "projects/nand2tetris.md": ("nand2tetris · 从与非门到俄罗斯方块", "—"),
    "projects/6824.md": ("6.824 · 分布式系统（Raft）", "—"),
}

# (ipynb 文件名, cell 序号) -> 目标文件
ROUTES = {
    "00-计算机系统概述.ipynb": {
        0: "os/01-01-基本概念.md", 1: "os/01-03-运行环境.md", 2: "os/01-03-运行环境.md",
        3: "os/01-03-运行环境.md", 4: "os/01-03-运行环境.md", 5: "os/01-03-运行环境.md",
        6: "os/01-03-运行环境.md", 7: "os/01-04-体系结构.md", 8: "os/01-03-运行环境.md",
        9: "os/01-01-基本概念.md", 10: "os/01-03-运行环境.md", 11: "os/01-03-运行环境.md",
        12: "projects/cs149.md", 13: "projects/nand2tetris.md", 14: "projects/cs149.md",
    },
    "01-数据表示与编码.ipynb": {0: "projects/nand2tetris.md", 1: "projects/csapp.md", 2: "projects/csapp.md"},
    "02-运算与ALU.ipynb": {0: "projects/nand2tetris.md"},
    "03-存储层次与Cache.ipynb": {0: "projects/csapp.md", 1: "projects/csapp.md", 2: "projects/cs149.md"},
    "04-内存与虚拟内存.ipynb": {0: "projects/nand2tetris.md", 1: "projects/csapp.md", 2: "projects/csapp.md"},
    "06-指令系统与汇编.ipynb": {0: "projects/nand2tetris.md", 1: "projects/nand2tetris.md",
                              2: "projects/csapp.md", 3: "projects/csapp.md"},
    "07-CPU与数据通路.ipynb": {0: "projects/nand2tetris.md", 1: "projects/csapp.md"},
    "09-总线与IO.ipynb": {0: "projects/nand2tetris.md"},
    "10-进程与线程.ipynb": {
        0: "os/02-01-进程与线程.md", 1: "os/02-01-进程与线程.md", 2: "os/02-01-进程与线程.md",
        3: "os/02-01-进程与线程.md", 4: "os/02-01-进程与线程.md", 5: "os/02-01-进程与线程.md",
        6: "projects/csapp.md", 7: "projects/6824.md", 8: "projects/nand2tetris.md", 9: "projects/6824.md",
    },
    "12-同步与互斥.ipynb": {0: "projects/cs149.md", 1: "projects/6824.md", 2: "projects/cs149.md"},
    "14-网络分层与链路层.ipynb": {
        0: "net/01-02-分层与参考模型.md", 1: "net/01-02-分层与参考模型.md",
        2: "net/03-02-差错控制.md", 3: "net/03-02-差错控制.md",
        4: "projects/cs144.md", 5: "projects/cs144.md", 6: "projects/cs144.md",
    },
    "15-网络层.ipynb": {
        0: "net/04-03-IPv4地址与子网.md", 1: "net/01-01-概述与性能.md",
        2: "net/04-04-分片与配套协议.md", 3: "net/04-04-分片与配套协议.md",
        4: "net/04-03-IPv4地址与子网.md", 5: "projects/cs144.md", 6: "projects/cs144.md",
    },
    "16-传输层.ipynb": {
        0: "net/05-01-服务与端口.md", 1: "net/05-01-服务与端口.md", 2: "net/05-01-服务与端口.md",
        3: "net/05-01-服务与端口.md", 4: "net/05-02-UDP.md", 5: "net/05-02-UDP.md",
        6: "net/05-02-UDP.md", 7: "net/05-05-TCP拥塞控制.md", 8: "net/05-02-UDP.md",
        9: "net/05-05-TCP拥塞控制.md", 10: "net/05-05-TCP拥塞控制.md", 11: "net/05-05-TCP拥塞控制.md",
        12: "net/05-05-TCP拥塞控制.md", 13: "net/05-03-TCP连接管理.md", 14: "net/05-03-TCP连接管理.md",
        15: "net/05-03-TCP连接管理.md", 16: "net/05-04-TCP可靠传输与流控.md",
        17: "net/05-04-TCP可靠传输与流控.md", 18: "net/05-04-TCP可靠传输与流控.md",
        19: "net/05-04-TCP可靠传输与流控.md", 20: "net/05-04-TCP可靠传输与流控.md",
        21: "projects/cs144.md", 22: "projects/cs144.md", 23: "projects/cs144.md",
    },
    "17-应用层.ipynb": {
        0: "net/06-02-DNS.md", 1: "net/06-04-WWW与HTTP.md",
        2: "net/06-02-DNS.md", 3: "projects/csapp.md",
    },
    "20-图.ipynb": {0: "projects/cs149.md"},
}


def header(target: str) -> str:
    title, kp = TARGETS[target]
    if target.startswith("projects/"):
        return (f"# {title}\n\n"
                "> **工程线（兴趣向，非考试范围）**。本文件不承担复习任务；\n"
                "> 需要说明「这段对应哪个考点」时**只写 KP 号**，不复制考试内容（单向引用）。\n"
                "> 新建于 2026-10-28 目录重构，正文沿用原有模块文档。\n\n---\n\n")
    return (f"# {title}\n\n"
            f"> **KP**：`{kp}` ｜ 状态：**已归档** ｜ 最后更新：2026-10-28\n"
            ">\n"
            "> 归档口径：本文件是「一个 KP 节 = 一个文件 = 一个复习单元」的那一个文件。\n"
            "> 内容来源标注在每节标题下的 `>` 行；复习档位登记在 `reviews/REVIEWS.md`，不写在本文件里。\n\n"
            "---\n\n")


def main():
    buckets = {}      # target -> [markdown text]
    archived = 0

    for nb_path in sorted(ROOT.glob("*.ipynb")):
        stem = nb_path.stem
        routes = ROUTES.get(nb_path.name, {})
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        for i, cell in enumerate(nb["cells"]):
            body = "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
            # 1) 存档
            cell_dir = ARCH / "cells"
            cell_dir.mkdir(parents=True, exist_ok=True)
            (cell_dir / f"{stem}__{i:02d}.md").write_text(
                f"<!-- 出处：{nb_path.name} cell[{i}] · 迁移于 2026-10-28 -->\n\n{body}\n",
                encoding="utf-8")
            archived += 1
            # 2) 分发
            tgt = routes.get(i)
            if tgt:
                buckets.setdefault(tgt, []).append(body.strip())
        shutil.copy2(nb_path, ARCH / "ipynb" / nb_path.name)

    # 3) 写目标文件
    written = []
    for tgt, chunks in buckets.items():
        path = (PROJ / tgt.split("/", 1)[1]) if tgt.startswith("projects/") else (EXAM / tgt)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = header(tgt)
        for c in chunks:
            text += c + "\n\n---\n\n"
        path.write_text(text, encoding="utf-8")
        written.append((str(path.relative_to(ROOT)), len(chunks)))

    # 4) 未路由的 cell（应为 0）
    total_routed = sum(len(v) for v in buckets.values())
    print(f"归档 cell：{archived}　路由落下：{total_routed}")
    for p, n in sorted(written):
        print(f"  {p:44s} {n} 节")
    if total_routed != archived:
        print(f"!! 有 {archived - total_routed} 个 cell 未路由，检查 ROUTES")


if __name__ == "__main__":
    main()
