# 2026-11-04: 输出名固定为 math.pdf（入口仍是 main.tex，\input 路径不变）
# 这样三册不再都叫 main.pdf。清理用 latexmk -C main.tex。
$jobname = 'math';
