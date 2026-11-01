#!/usr/bin/env python3
"""把 edge.md 的条目溶进 syllabus/408.md 与 syllabus/math1.md。

- 章节表加「标签」列（高频 / 常考 / 低频 / 可能不考）
- 每章表后插入「#### 细节与陷阱」块，逐条带 KP 与标签
- 真题索引与来源并入 syllabus/README.md 附录
- edge.md 归档删除
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYL = ROOT / "syllabus"
EDGE = SYL / "edge.md"

# ── 标签：章节级（节级 KP）──
T_HIGH = """408-CO-0201 408-CO-0204 408-CO-0206 408-CO-0207 408-CO-0303 408-CO-0305
408-CO-0401 408-CO-0402 408-CO-0502 408-CO-0503 408-CO-0506
408-OS-0202 408-OS-0203 408-OS-0204 408-OS-0302 408-OS-0402 408-OS-0403
408-DS-0402 408-DS-0503 408-DS-0504 408-DS-0505 408-DS-0506 408-DS-0507
408-DS-0602 408-DS-0603 408-DS-0604 408-DS-0606 408-DS-0607
408-DS-0703 408-DS-0704 408-DS-0708
408-NET-0201 408-NET-0302 408-NET-0303 408-NET-0304 408-NET-0403 408-NET-0404
408-NET-0503 408-NET-0504 408-NET-0505 408-NET-0602 408-NET-0604
M1-HS-0103 M1-HS-0201 M1-HS-0202 M1-HS-0203 M1-HS-0301 M1-HS-0302
M1-HS-0601 M1-HS-0602 M1-HS-0603 M1-HS-0604 M1-HS-0605 M1-HS-0701 M1-HS-0702
M1-HS-0801 M1-HS-0803
M1-LA-0101 M1-LA-0202 M1-LA-0203 M1-LA-0301 M1-LA-0401 M1-LA-0402
M1-LA-0501 M1-LA-0502 M1-LA-0503 M1-LA-0601 M1-LA-0602
M1-PS-0103 M1-PS-0201 M1-PS-0202 M1-PS-0301 M1-PS-0303 M1-PS-0401
M1-PS-0402 M1-PS-0602 M1-PS-0701 M1-PS-0703 M1-PS-0801""".split()

T_LOW = """408-CO-0101 408-CO-0507 408-CO-0702 408-OS-0102 408-OS-0105
408-DS-0706 408-NET-0202 408-NET-0405 408-NET-0601
M1-HS-0101 M1-HS-0401 M1-HS-0802 M1-LA-0102 M1-LA-0403 M1-LA-0603
M1-PS-0501""".split()

T_MAYBE = """408-CO-0101 408-OS-0105 408-CO-0507 408-CO-0702 408-NET-0405""".split()

# ── 标签：条目级（细节与陷阱）──
D_HIGH_KW = ["混合索引", "ASL", "分片", "三次握手", "拥塞", "Cache 行", "脏位", "TLB",
             "旋转体侧面积", "极坐标", "二次型", "无偏", "置信", "折半判定树", "关键路径",
             "GBN", "窗口", "引脚", "IEEE 754", "溢出", "快排", "败者树", "子网", "NAT"]
D_LOW_KW = ["移动 IP", "HDLC", "令牌", "虚拟机", "通道", "单模", "多模", "Flynn",
            "向量处理器", "微程序", "磁带", "磨损均衡", "IPv6", "SDN", "外核",
            "硬实时", "进位链", "操作码扩展", "DMA", "SPOOLing"]


def tag_of(kp):
    if kp in T_MAYBE:
        return "可能不考"
    if kp in T_LOW:
        return "低频"
    if kp in T_HIGH:
        return "高频"
    return "常考"


def detail_tag(text):
    if any(k in text for k in D_LOW_KW):
        return "低频"
    if any(k in text for k in D_HIGH_KW):
        return "高频"
    return "易错"


def clean(s):
    return s.replace("**", "").replace("\n", " ").strip()


def parse_edge():
    """返回 {chapter_key: [(kp, 要点, 原因)]}，以及真题索引/来源两段原文。"""
    lines = EDGE.read_text(encoding="utf-8").split("\n")
    items = {}
    for ln in lines:
        if not ln.startswith("| ") or ln.startswith("| 要点") or ln.startswith("|---"):
            continue
        cells = [c.strip() for c in ln.strip().rstrip("|").split("|")]
        if len(cells) < 3:
            continue
        kp_m = re.search(r"`((?:408|M1)-[A-Z]{2,3}-\d{4})`", cells[-1])
        if not kp_m:
            continue
        kp = kp_m.group(1)
        a, b = clean(cells[-3]), clean(cells[-2])
        if not a:
            continue
        chap = kp.rsplit("-", 1)[0]
        items.setdefault(chap, []).append((kp, a, b))
    # 真题索引 / 来源
    def grab(start_marker):
        i = next(k for k, l in enumerate(lines) if l.startswith(start_marker))
        j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
        return "\n".join(lines[i:j]).strip(), i, j
    idx, _, _ = grab("## 六、真题实证索引")
    src, _, _ = grab("## 七、来源与可信度")
    return items, idx, src


def add_tag_column(text):
    """给章节表加「标签」列（在「文件」列之前）。"""
    out = []
    for ln in text.split("\n"):
        # 表头
        if ln.strip() == "| KP | 节 | 核心知识点 | 要求 | 文件 |":
            out.append("| KP | 节 | 核心知识点 | 要求 | 标签 | 文件 |")
            continue
        if re.fullmatch(r"\|\s*-{3,}\s*(\|\s*-{3,}\s*){4}\|", ln.strip()):
            out.append("|---|---|---|---|---|---|")
            continue
        m = re.match(r"^\| `((?:408|M1)-[A-Z]{2,3}-[\d]{4})` \|", ln)
        if m and ln.rstrip().endswith("|"):
            kp = m.group(1)
            cells = [c for c in ln.strip().rstrip("|").split("|")]
            if len(cells) == 5:
                out.append("|" + "|".join(cells[:4]) + f"| {tag_of(kp)} " + "|" + cells[4] + "|")
                continue
        out.append(ln)
    return "\n".join(out)


def insert_details(text, items, prefix):
    """在每个 `### <CODE>-NN ...` 章表后插入细节块。"""
    lines = text.split("\n")
    out, pending_chap = [], None

    def flush():
        nonlocal pending_chap
        if pending_chap and pending_chap in items:
            out.append("")
            out.append("#### 细节与陷阱")
            out.append("")
            seen = set()
            for kp, a, b in items[pending_chap]:
                if (kp, a) in seen:
                    continue
                seen.add((kp, a))
                t = detail_tag(a + b)
                tail = f"　原因：{b}" if b else ""
                out.append(f"- `{kp}` 〔{t}〕{a}{tail}")
            out.append("")
        pending_chap = None

    for ln in lines:
        m = re.match(rf"^### ([A-Z]{{2}}-\d\d) ", ln)
        if m:
            flush()
            pending_chap = f"{prefix}-{m.group(1)}"
            out.append(ln)
            continue
        if ln.startswith("## "):
            flush()
            out.append(ln)
            continue
        out.append(ln)
    flush()
    return "\n".join(out)


def main():
    items, idx, src = parse_edge()

    for fname, prefix in (("408.md", "408"), ("math1.md", "M1")):
        p = SYL / fname
        s = p.read_text(encoding="utf-8")
        s = add_tag_column(s)
        s = insert_details(s, items, prefix)
        # 头注：解释标签口径
        s = s.replace(
            "> **本表只负责「有哪些考点、要求到什么程度、落在哪个文件」。**",
            "> **本表只负责「有哪些考点、要求到什么程度、落在哪个文件」。**\n"
            "> **标签是粗判，不是真题统计**：`高频` = 教学材料反复强调的计算/必考项；`常考` = 常规考点；\n"
            "> `低频` = 出现过但权重小；`可能不考` = 大纲有、近十年基本没单独命题，**仍建议读一遍**（成本低、防万一）。\n"
            "> 每章表后的「细节与陷阱」是从历年解析与教学材料里汇总的具体坑，条目级标签同此口径。", 1)
        p.write_text(s, encoding="utf-8")
        print(f"✓ {fname}  {len(s.split(chr(10)))} 行")

    # 真题索引 + 来源 → syllabus/README.md 附录
    rp = SYL / "README.md"
    r = rp.read_text(encoding="utf-8").rstrip()
    idx_body = idx.replace("## 六、真题实证索引", "## 附录 B：真题实证索引").replace(
        "> 只收录**有具体题号或明确考点描述**的，来源见 §7。不做逐年频次统计（没有可靠数据）。",
        "> 只收录**有具体题号或明确考点描述**的；每条在 `408.md` / `math1.md` 的「细节与陷阱」里都能找到对应条目。")
    src_body = src.replace("## 七、来源与可信度", "## 附录 C：来源与可信度")
    r += "\n\n---\n\n## 附录 A：标签口径\n\n"
    r += ("| 标签 | 含义 | 处理 |\n|---|---|---|\n"
          "| `高频` | 教学材料反复强调、计算量大或年年出现的类型 | 必过 ③，限时练 |\n"
          "| `常考` | 常规考点，正常掌握 | 过 ①②③ |\n"
          "| `低频` | 出现过、权重小 | 读到「能认」即可 |\n"
          "| `可能不考` | 大纲有、近十年基本没单独命题 | **读一遍**，不投入练习时间 |\n\n"
          "> 标签来自教学材料的共识口径与真题解析的交叉印证，**不是逐年频次统计**（没有可靠公开数据，不编）。\n")
    r += "\n\n---\n\n" + idx_body + "\n\n---\n\n" + src_body + "\n"
    rp.write_text(r, encoding="utf-8")
    print(f"✓ README.md 追加附录  {len(r.split(chr(10)))} 行")

    shutil.move(str(EDGE), str(ROOT / "_archive" / "edge-v1.md"))
    print("✓ edge.md → _archive/edge-v1.md")


if __name__ == "__main__":
    main()
