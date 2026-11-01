#!/usr/bin/env python3
"""第三步迁移：modules/ 下的考试向文档 -> exam/，工程向内容 -> projects/algorithm.md。

- 操作系统.md + 进程.md        -> exam/408/os/ROADMAP.md
- 网络.md                     -> exam/408/net/ROADMAP.md
- 数据结构.md  §1 代码体检     -> projects/algorithm.md
- 数据结构.md  其余（路线/排期）-> exam/408/ds/ROADMAP.md
- 树型查找-讲义.md  §1/§5/§6   -> exam/408/ds/06-00-树型查找总览.md
                     §2/§3     -> exam/408/ds/06-06-B树与B+树.md
                     §4        -> exam/408/ds/06-05-红黑树.md
                     §7 + 附    -> projects/algorithm.md
- 外部排序-讲义.md  §1–§8      -> exam/408/ds/07-07-外部排序.md
                     附        -> projects/algorithm.md
- Math1/高等数学.md + 概率论.md -> exam/math1/ROADMAP.md
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "modules"
EXAM = ROOT / "exam"
PROJ = ROOT / "projects"


def read(p):
    return Path(p).read_text(encoding="utf-8").split("\n")


def find(lines, prefix, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    raise SystemExit(f"找不到标题：{prefix}")


def drop_title(block):
    """去掉开头的一级标题与其后的引用块。"""
    i = 0
    while i < len(block) and (block[i].startswith("# ") or block[i].strip() == ""):
        i += 1
    while i < len(block) and block[i].startswith(">"):
        i += 1
    return "\n".join(block[i:]).strip()


ROADMAP_HEAD = """# {title}

> **本文件只回答「先学什么、学到什么程度、ROI 怎么排」，不装知识点正文。**
> 知识点正文：一个 KP 节一个文件（`{prefix}<章>-<节>-<名>.md`）；考点清单见 `syllabus/408.md`。
> 学习与验收方法见 `LEARNING.md`；进度真源见 `PROGRESS.md`（本文件不记进度）。
> 工程锚点只写 `projects/` 的文件名，不复述代码。

---

"""


def write(path, text, note):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"  {str(path.relative_to(ROOT)):44s} {len(text.split(chr(10))):5d} 行  {note}")


def main():
    # ---------- 1. OS / NET 路线 ----------
    os_txt = []
    for f in ("操作系统.md", "进程.md"):
        os_txt.append(drop_title(read(MOD / "408" / f)))
    body = "\n\n---\n\n## 附：模块细则（原 `modules/408/操作系统.md` 与 `进程.md` 合并）\n\n" + \
           "\n\n---\n\n".join(os_txt)
    write(EXAM / "408/os/ROADMAP.md", ROADMAP_HEAD.format(title="操作系统 · 学习路线（ROADMAP）", prefix="os/") + body,
          "合并 操作系统.md + 进程.md")
    write(EXAM / "408/net/ROADMAP.md",
          ROADMAP_HEAD.format(title="计算机网络 · 学习路线（ROADMAP）", prefix="net/") +
          drop_title(read(MOD / "408/网络.md")), "原 网络.md")

    # ---------- 2. 数据结构：工程 / 考试 切分 ----------
    ds = read(MOD / "408/数据结构.md")
    i_s1 = find(ds, "## 1. 代码基座体检")
    i_s2 = find(ds, "## 2. 总纲地图")
    algo_body = "\n".join(ds[i_s1:i_s2]).strip()
    ds_rest = "\n".join(ds[:i_s1]).strip() + "\n\n---\n\n" + "\n".join(ds[i_s2:]).strip()
    # 去掉原一级标题与引用块
    write(EXAM / "408/ds/ROADMAP.md",
          ROADMAP_HEAD.format(title="数据结构 · 学习路线（ROADMAP）", prefix="ds/")
          + drop_title(ds_rest.split("\n")),
          "原 数据结构.md 去掉 §1 代码体检")

    # ---------- 3. 树型查找讲义按节切 ----------
    st = read(MOD / "408/树型查找-讲义.md")
    h1, h2, h3 = find(st, "## 1."), find(st, "## 2."), find(st, "## 3.")
    h4, h5, h6 = find(st, "## 4."), find(st, "## 5."), find(st, "## 6.")
    h7, hz = find(st, "## 7."), find(st, "## 附")

    overview = "\n\n".join(["\n".join(st[h1:h2]), "\n".join(st[h5:h6]), "\n".join(st[h6:h7])]).strip()
    write(EXAM / "408/ds/06-00-树型查找总览.md",
          "# 树型查找 · 总览（BST / AVL / 红黑树 / B 树 / B+ 树）\n\n"
          "> **KP**：`408-DS-0600`（章导览，不对应单独考题）｜来源：`modules/408/树型查找-讲义.md` §1/§5/§6\n\n---\n\n"
          + overview, "§1 共同问题 + §5 主线 + §6 顺序")

    bt = "\n\n".join(["\n".join(st[h2:h3]), "\n".join(st[h3:h4])]).strip()
    write(EXAM / "408/ds/06-06-B树与B+树.md",
          "# B 树与 B+ 树\n\n> **KP**：`408-DS-0606`｜来源：`modules/408/树型查找-讲义.md` §2/§3\n\n---\n\n" + bt,
          "§2 B 树 + §3 B+ 树")

    rb = "\n".join(st[h4:h5]).strip()
    write(EXAM / "408/ds/06-05-红黑树.md",
          "# 红黑树\n\n> **KP**：`408-DS-0605`｜来源：`modules/408/树型查找-讲义.md` §4\n\n---\n\n" + rb, "§4")

    algo_extra = "\n\n".join([
        "## 附一：树型查找讲义的代码对应（§7）\n\n" + "\n".join(st[h7:hz]).strip(),
        "## 附二：树型查找讲义的数值校验记录\n\n" + "\n".join(st[hz:]).strip(),
    ])

    # ---------- 4. 外部排序讲义 ----------
    es = read(MOD / "408/外部排序-讲义.md")
    e8 = find(es, "## 8.")
    ez = find(es, "## 附")
    write(EXAM / "408/ds/07-07-外部排序.md",
          "# 外部排序\n\n> **KP**：`408-DS-0707`｜来源：`modules/408/外部排序-讲义.md`\n\n---\n\n"
          + "\n".join(es[1:e8]).strip(), "§1–§7")
    algo_extra += "\n\n" + "## 附三：外部排序讲义的数值校验记录\n\n" + "\n".join(es[ez:]).strip()

    # algorithm.md
    write(PROJ / "algorithm.md",
          "# algorithm · 408 数据结构代码基座\n\n"
          "> **工程线（兴趣向，非考试范围）**。这里是代码仓的体检、bug 记录、验证方法论。\n"
          "> 408 的代码在考场上**不写模板也能拿分**（采分点是手算表格），所以这个仓的定位是\n"
          "> **理解素材 + 反例库**，不是得分来源。考点对位只写 KP 号，正文在 `exam/408/ds/`。\n"
          "> 代码真源：`~/develop/learning/learning-408/algorithm/`（独立子仓）。\n\n"
          "## 对位考点（单向引用）\n\n"
          "| 仓内模块 | 对应 KP |\n|---|---|\n"
          "| `tree/` 五种遍历与建树 | `408-DS-0402` 二叉树与遍历 |\n"
          "| `tree/` 线索树 | `408-DS-0403` 线索二叉树 |\n"
          "| `tree/` 哈夫曼、并查集 | `408-DS-0405` 哈夫曼树、`408-DS-0406` 并查集 |\n"
          "| `RBTree.hpp` / `B+Tree.hpp` | `408-DS-0605` 红黑树、`408-DS-0606` B 树与 B+ 树 |\n"
          "| `sort/` 快排与堆排 | `408-DS-0703` 交换排序、`408-DS-0704` 选择排序与堆 |\n"
          "| `kmp.hpp` | `408-DS-0204` 串与 KMP |\n"
          "| `leetcode/` 24 题 | 覆盖 `408-DS-02`–`408-DS-05` 各区 |\n\n"
          "---\n\n"
          "## 一、代码基座体检（原 `数据结构.md` §1）\n\n" + algo_body + "\n\n" + algo_extra,
          "§1 代码体检 + 讲义代码附注")

    # ---------- 5. Math1 路线 ----------
    hs = drop_title(read(MOD / "Math1/高等数学.md"))
    ps = drop_title(read(MOD / "Math1/概率论与数理统计.md"))
    write(EXAM / "math1/ROADMAP.md",
          "# 数学一 · 学习路线（ROADMAP）\n\n"
          "> 考点清单见 `syllabus/math1.md`（高数 8 章 / 线代 6 章 / 概率统计 8 章，共 72 个复习单元）。\n"
          "> **线代目前没有任何模块文档**——这是本线最大的空洞（33 分）。\n\n---\n\n"
          "## 一、高等数学\n\n" + hs + "\n\n---\n\n## 二、概率论与数理统计\n\n" + ps,
          "合并两份 Math1 模块文档")


if __name__ == "__main__":
    main()
