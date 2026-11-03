#!/usr/bin/env python3
"""结构校验：KP 主键一致性、文件头、双线边界、失效路径。

用法：
    python3 tools/lint.py            # 全部检查
    python3 tools/lint.py --strict   # 把提示级也当成失败

退出码：0 = 无错误；1 = 有错误。提示级（⚠）不影响退出码，除非 --strict。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KP_RE = re.compile(r"^(408-(DS|CO|OS|NET)|M1-(HS|LA|PS)|E1-(VO|LS|RC|NT|TR|WR|CZ)|P1-(MY|MZ|XS|SG|SF|SZ))-(\d{2}|\d{2}\d{2}|\d{4})$")
ENGINE_WORDS = ("CS144", "CS149", "CSAPP", "nand2tetris", "6.824", "6824", "jos", "craft", "cachelab",
                "malloclab", "shlab", "datalab", "bomblab", "proxylab", "xv6", "lab3", "check2")
STATUS_OK = ("未开始", "已归档", "已验收")
errors, warns = [], []


def err(m): errors.append(m)
def warn(m): warns.append(m)


def collect_kps():
    """只有四个科目的主键表「定义」KP；tiers.md / README.md / ROADMAP 只是引用。"""
    DEF_FILES = {"408.md", "math1.md", "english1.md", "politics.md"}
    kps = {}
    for p in sorted((ROOT / "syllabus").glob("*.md")):
        if p.name not in DEF_FILES:
            continue
        for m in re.finditer(r"`((?:408|M1|E1|P1)-[A-Z]{2,3}-[\d]{2,8})`", p.read_text(encoding="utf-8")):
            kp = m.group(1)
            kps.setdefault(kp, set()).add(p.name)
            if not KP_RE.match(kp):
                err(f"[syllabus] KP 格式不合法：{kp}（{p.name}）")
    for k, v in kps.items():
        if len(v) > 1:
            err(f"[syllabus] 同一 KP 在两个科目表里重复定义：{k} -> {sorted(v)}")
    return {k: sorted(v) for k, v in kps.items()}


def check_kp_refs(kps):
    """引用一致性：tiers.md 与 exam/ 里提到的 KP 必须在主键表里存在。"""
    n = 0
    refs = [p for p in sorted((ROOT / "syllabus").glob("*.md"))
            if p.name not in {"408.md", "math1.md", "english1.md", "politics.md"}]
    for p in refs + sorted((ROOT / "exam").rglob("*.md")):
        if not p.exists():
            continue
        for m in re.finditer(r"`((?:408|M1|E1|P1)-[A-Z]{2,3}-[\d]{2,8})`", p.read_text(encoding="utf-8")):
            n += 1
            if m.group(1) not in kps:
                err(f"[ref] 引用了主键表里不存在的 KP：{m.group(1)}（{p.relative_to(ROOT)}）")
    return n


def check_exam(kps):
    n = 0
    for p in sorted((ROOT / "exam").rglob("*.md")):
        rel = p.relative_to(ROOT)
        text = p.read_text(encoding="utf-8")
        # 真题库与真题专项不按 KP 组织，豁免
        if "真题" in p.parts or "真题专项" in p.parts:
            continue
        if p.name in ("ROADMAP.md", "README.md"):
            continue
        n += 1
        # 一章一文件：NN-章名.md
        if not re.match(r"^\d{2}-.+\.md$", p.name):
            err(f"[exam] 文件名不合规（应为一章一文件 NN-章名.md）：{rel}")
        # 章内必须至少引用一个合法 KP，且不得引用 syllabus 里没有的 KP
        refs = set(re.findall(r"`((?:408|M1|E1|P1)-[A-Z]{2,3}(?:-\d{2,8})?)`", text))
        if not refs:
            err(f"[exam] 全章没有引用任何 KP：{rel}")
        for kp in sorted(refs):
            if kp.startswith(("E1-", "P1-")):
                # 英政按题型/模块建主键，只有前缀两级，允许不带数字
                if not re.match(r"^(E1-[A-Z]{2}|P1-[A-Z]{2})(-\d{2,8})?$", kp):
                    err(f"[exam] KP 格式不合法：{rel} -> {kp}")
                continue
            if not KP_RE.match(kp):
                err(f"[exam] KP 格式不合法：{rel} -> {kp}")
            elif kp not in kps:
                err(f"[exam] KP 不在 syllabus 中：{rel} -> {kp}")
        for seg in ("## 一、本章考点", "## 二、正文", "## 三、真题落点", "## 四、易错"):
            if seg not in text:
                err(f"[exam] 缺「{seg}」段：{rel}")
        if "复习计划" in text:
            err(f"[exam] 正文里仍有复习档位行（应进 reviews/REVIEWS.md）：{rel}")
        hits = sorted({w for w in ENGINE_WORDS if w in text})
        if hits:
            warn(f"[exam] 出现工程词 {hits}：{rel}")
    return n


DRILL_408 = ["41-树与图手算.md", "42-算法设计（手写 C 代码）.md", "43-存储系统与地址划分.md",
             "44-数据通路与流水线.md", "45-调度与死锁.md", "46-同步互斥与地址翻译.md",
             "47-子网与 TCP 计算.md"]
DRILL_MATH = ["01-极限与一元微分.md", "02-一元积分与定积分应用.md", "03-多元微分与重积分.md",
              "04-曲线曲面积分与三大公式.md", "05-级数与微分方程.md", "06-线性代数综合.md",
              "07-概率统计综合.md"]
DRILL_TIERS = ("## 二、L1", "## 三、L2", "## 四、L3")
DRILL_FIELDS = ("题干", "题眼", "卡在哪", "分步", "拿分骨架", "结果锚点", "变式")


def check_drill(kps):
    """drill/ 第六层：难度阶梯题库（2026-11-03 起）。

    判据：408 七条题号线 + 数一七条题型线一个不少；每份三档齐、每档 ≥2 题；
    每题六字段齐；不得出现四位年份（本层是原创变式题，出现年份即编造）。
    """
    d = ROOT / "drill"
    if not d.exists():
        err("[drill] 缺 drill/ 目录")
        return 0
    if not (d / "README.md").exists():
        err("[drill] 缺 README.md")
    n = 0
    for sub, want in (("408", DRILL_408), ("math1", DRILL_MATH)):
        got = sorted(p.name for p in (d / sub).glob("*.md"))
        miss = [w for w in want if w not in got]
        extra = [g for g in got if g not in want]
        if miss:
            err(f"[drill] {sub}/ 缺 {miss}")
        if extra:
            err(f"[drill] {sub}/ 多出白名单外的文件 {extra}")
        for name in want:
            p = d / sub / name
            if not p.exists():
                continue
            n += 1
            text = p.read_text(encoding="utf-8")
            if re.search(r"(?:19|20)\d{2}\s*年", text):
                err(f"[drill] 出现四位年份（本层是原创变式题）：{sub}/{name}")
            for seg in ("## 一、", "## 五、") + DRILL_TIERS:
                if seg not in text:
                    err(f"[drill] 缺「{seg}」段：{sub}/{name}")
            for tier in ("L1", "L2", "L3"):
                qs = re.findall(rf"^### {tier}-\d+ ", text, re.M)
                if len(qs) < 2:
                    err(f"[drill] {tier} 少于 2 题（{len(qs)}）：{sub}/{name}")
            for i, body in enumerate(re.split(r"^### ", text, flags=re.M)[1:], 1):
                for f in DRILL_FIELDS:
                    if f"**{f}**" not in body:
                        err(f"[drill] 第 {i} 题缺 **{f}**：{sub}/{name}")
                        break
            for m in re.finditer(r"`((?:408|M1)-[A-Z]{2,3}-\d{2,8})`", text):
                if m.group(1) not in kps:
                    err(f"[drill] KP 不在 syllabus 中：{sub}/{name} -> {m.group(1)}")
    return n


def check_projects():
    """工程线全部在仓根的 `projects/`（2026-11-02 起，kaoyan/projects 已并入）。

    每个项目一个目录，两件套 `OUTLINE.md` + `NOTES.md`（英文版 `OUTLINE.bi.md` 可选成对）。
    `QUICK.md` / `DESIGN.md` 已废除。
    """
    d = ROOT.parent / "projects"
    if not d.exists():
        return 0
    n = 0
    for sub in sorted(x for x in d.iterdir() if x.is_dir()):
        n += 1
        for name in ("OUTLINE.md", "NOTES.md"):
            if not (sub / name).exists():
                err(f"[projects] {sub.name}/ 缺 {name}")
        for dead in ("QUICK.md", "DESIGN.md"):
            if (sub / dead).exists():
                err(f"[projects] {sub.name}/ 仍有已废除的 {dead}")
    return n


QUICK_FILES = ["408-ds.md", "408-co.md", "408-os.md", "408-net.md",
               "math-hs.md", "math-la.md", "math-ps.md", "english.md", "politics.md"]


def check_quick():
    """quick/ 一层：九份三合一口语稿（2026-11-02 起：408 分四科、数三分三科）。"""
    d = ROOT / "quick"
    if not d.exists():
        err("[quick] 缺 quick/ 目录")
        return 0
    n = 0
    for w in QUICK_FILES:
        p = d / w
        if not p.exists():
            err(f"[quick] 缺 {w}")
            continue
        n += 1
        text = p.read_text(encoding="utf-8")
        if len(text) < 5000:
            err(f"[quick] {w} 过短（{len(text)} 字符），一口气讲完一科不应少于 5000 字符")
        for seg in ("第一部分", "第二部分", "第三部分"):
            if seg not in text:
                err(f"[quick] {w} 缺「{seg}」（三合一结构不完整）")
    return n


def check_reviews(kps):
    p = ROOT / "reviews" / "REVIEWS.md"
    if not p.exists():
        err("[reviews] 缺 REVIEWS.md")
        return 0
    rows = 0
    for line in p.read_text(encoding="utf-8").split("\n"):
        if not line.startswith("| `"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 8:
            err(f"[reviews] 列数不足：{line[:60]}")
            continue
        rows += 1
        kp = cols[0].strip("`")
        if kp not in kps:
            err(f"[reviews] KP 不在 syllabus 中：{kp}")
        f = cols[2].strip("`")
        if not (ROOT / "exam" / "408" / f).exists() and not list((ROOT / "exam").rglob(Path(f).name)):
            err(f"[reviews] 指向的文件不存在：{f}")
        if not re.search(r"R[123]\s*(待|已过)", cols[-1]):
            err(f"[reviews] 状态写法不合规（应为 `Rn 待` / `R3 已过`）：{line[:50]}")
    return rows


TAGS = {"高频", "常考", "低频", "可能不考"}


def check_syllabus_tables():
    """主键表必须是 6 列且标签列取值合法（LaTeX 里的 | 会吃列，这里兜住）。"""
    n = 0
    for f in ("408.md", "math1.md"):
        p = ROOT / "syllabus" / f
        if not p.exists():
            continue
        for i, ln in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            if not re.match(r"^\| `(?:408|M1)-", ln):
                continue
            n += 1
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) != 6:
                err(f"[table] {f}:{i} 列数 {len(cells)}（应为 6，检查 LaTeX 里的裸 |）")
                continue
            if cells[4] not in TAGS:
                err(f"[table] {f}:{i} 标签「{cells[4]}」不合法（应为 {'/'.join(sorted(TAGS))}）")
    return n


def check_links():
    """检查 md 里反引号包裹的 exam/... 路径是否存在（只查明确写成路径的）。

    跳过两类：
      1. `>` 引用块（历史记录 / 来源说明）—— 旧路径是当时的真实状态，不改。
      2. 文件内自指的旧扁平路径（`projects/x.md` 已改为 `projects/x/NOTES.md`）。
    """
    bad = []
    for p in list(ROOT.rglob("*.md")):
        if "_archive" in p.parts or ".workbuddy" in p.parts:
            continue
        for line in p.read_text(encoding="utf-8").split("\n"):
            if line.lstrip().startswith(">"):
                continue
            for m in re.finditer(r"`(exam/[^`]+?\.md|projects/[^`]+?\.md)`", line):
                t = m.group(1)
                if (ROOT / t).exists() or (ROOT.parent / t).exists():
                    continue
                if "*" in t or "…" in t or "<" in t or "xxx" in t or "名.md" in t:
                    continue      # 通配符 / 占位示例，不当作真实路径
                bad.append(f"{p.relative_to(ROOT)} -> {t}")
    for b in sorted(set(bad))[:20]:
        warn(f"[link] 指向不存在的文件：{b}")
    return len(set(bad))


def main():
    strict = "--strict" in sys.argv
    kps = collect_kps()
    n_exam = check_exam(kps)
    n_drill = check_drill(kps)
    n_proj = check_projects()
    n_quick = check_quick()
    n_rev = check_reviews(kps)
    n_tab = check_syllabus_tables()
    n_link = check_links()
    n_ref = check_kp_refs(kps)

    print(f"syllabus KP 数：{len(kps)}　exam 文件：{n_exam}　drill 文件：{n_drill}　quick 文件：{n_quick}　"
          f"projects 目录：{n_proj}　复习行：{n_rev}　主键表行：{n_tab}　"
          f"KP 引用：{n_ref}　失效路径：{n_link}")
    for w in warns:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")
    print(f"{'FAIL' if errors or (strict and warns) else 'PASS'}："
          f"{len(errors)} 错误 / {len(warns)} 提示")
    sys.exit(1 if errors or (strict and warns) else 0)


if __name__ == "__main__":
    main()
