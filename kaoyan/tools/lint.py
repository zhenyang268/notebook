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
        n += 1
        rel = p.relative_to(ROOT)
        text = p.read_text(encoding="utf-8")
        if p.name == "ROADMAP.md":
            continue
        # 文件名：<章2>-<节2>-<名>.md 或 <序2>-<名>.md
        if not re.match(r"^\d{2}-\d{2}-.+\.md$", p.name) and not re.match(r"^\d{2}-.+\.md$", p.name):
            err(f"[exam] 文件名不合规（应为 NN-NN-名.md）：{rel}")
        # 头部
        head = "\n".join(text.split("\n")[:12])
        m = re.search(r">\s*\*\*KP\*\*：`([^`]+)`", head)
        if not m:
            err(f"[exam] 缺 KP 头：{rel}")
        else:
            kp = m.group(1)
            if kp not in kps:
                err(f"[exam] KP 不在 syllabus 中：{rel} -> {kp}")
            if not KP_RE.match(kp):
                err(f"[exam] KP 格式不合法：{rel} -> {kp}")
        if not any(s in head for s in STATUS_OK):
            err(f"[exam] 缺状态字段（未开始/已归档/已验收）：{rel}")
        if "复习计划" in text:
            err(f"[exam] 正文里仍有复习档位行（应进 reviews/REVIEWS.md）：{rel}")
        # 双线边界
        hits = sorted({w for w in ENGINE_WORDS if w in text})
        if hits:
            warn(f"[exam] 出现工程词 {hits}：{rel}")
    return n


def check_projects():
    n = 0
    for p in sorted((ROOT / "projects").glob("*.md")):
        n += 1
        text = p.read_text(encoding="utf-8")
        if "## 对位考点" not in text:
            err(f"[projects] 缺「对位考点（单向引用）」一节：{p.name}")
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
    """检查 md 里反引号包裹的 exam/... 路径是否存在（只查明确写成路径的）。"""
    bad = []
    for p in list(ROOT.rglob("*.md")):
        if "_archive" in p.parts or ".workbuddy" in p.parts:
            continue
        for m in re.finditer(r"`(exam/[^`]+?\.md|projects/[^`]+?\.md)`", p.read_text(encoding="utf-8")):
            t = m.group(1)
            if (ROOT / t).exists():
                continue
            if "*" in t or "…" in t or "<" in t or "xxx" in t or "名.md" in t:
                continue          # 通配符 / 占位示例，不当作真实路径
            bad.append(f"{p.relative_to(ROOT)} -> {t}")
    for b in sorted(set(bad))[:20]:
        warn(f"[link] 指向不存在的文件：{b}")
    return len(set(bad))


def main():
    strict = "--strict" in sys.argv
    kps = collect_kps()
    n_exam = check_exam(kps)
    n_proj = check_projects()
    n_rev = check_reviews(kps)
    n_tab = check_syllabus_tables()
    n_link = check_links()
    n_ref = check_kp_refs(kps)

    print(f"syllabus KP 数：{len(kps)}　exam 文件：{n_exam}　projects 文件：{n_proj}　"
          f"复习行：{n_rev}　主键表行：{n_tab}　KP 引用：{n_ref}　失效路径：{n_link}")
    for w in warns:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")
    print(f"{'FAIL' if errors or (strict and warns) else 'PASS'}："
          f"{len(errors)} 错误 / {len(warns)} 提示")
    sys.exit(1 if errors or (strict and warns) else 0)


if __name__ == "__main__":
    main()
