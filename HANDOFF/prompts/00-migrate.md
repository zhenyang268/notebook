# 任务 00 · 结构迁移（先做，一次性）

你是接手 `notebook/` 笔记仓的工程师。这个仓有三套内容：`math/`（LaTeX 数学笔记，**不动**）、
`kaoyan/`（考研）、`projects/`（工程笔记）。

在开始写任何新内容前，先把目录调成目标结构。**这是纯结构调整，不写内容。**

## 要做的动作

```bash
cd notebook/kaoyan

# 1. 删掉两个"按考点详解"的合并版（与新口径冲突）
rm -f quick/408.md quick/math1.md quick/english1.md quick/politics.md

# 2. 口语层并入 quick，删除独立目录
#    内容不丢：talk/ 的四份会被后续 K1–K9 重写覆盖，先移动到 .gen/archive/
mkdir -p .gen/archive && mv ../talk .gen/archive/talk-old 2>/dev/null || true

# 3. 干掉全部 QUICK.md（用户判定无意义）
rm -f projects/*/QUICK.md ../projects/*/QUICK.md

# 4. note/ 改为配题层，旧的"考场速查"归档
mkdir -p .gen/archive && mv note .gen/archive/note-old 2>/dev/null || true
mkdir -p note
```

## 要改的校验

`tools/lint.py` 里有两处假设已经失效，必须改：

1. `check_quick()`：现在检查 9 个固定文件名，改为按科检查新命名
   （`408-ds.md` `408-co.md` `408-os.md` `408-net.md` `math-hs.md` `math-la.md` `math-ps.md` `english.md` `politics.md`）
2. `check_projects()`：现在要求三件套，改为**两件套**
   （`OUTLINE.md` + `NOTES.md`；`QUICK.md` 不再要求，存在也不报错）

## 不能碰的

- `kaoyan/syllabus/` —— 唯一坐标系，后续 K0 只增强不重写
- `math/` 整个目录
- 任何 `_archive/` 下的历史文件

## 交付

改完后跑一次 `python3 tools/lint.py`，把输出贴出来。此时会报"缺 quick 九份 / 缺 note 章节"
——**这是预期的**，后续任务会填。你要保证的是：脚本能正常运行、不再检查已删除的文件。