# -*- coding: utf-8 -*-
"""修补 math1.md：标题点号、重复章、标题错位、补 HS-03 与 HS-07。"""
import re
from pathlib import Path

P = Path(__file__).parent.parent / 'kaoyan' / 'quick' / 'math1.md'
t = P.read_text(encoding='utf-8')

# 1) #### M1-HS-08.01 一阶方程 -> #### M1-HS-0801 一阶方程
def fix_num(m):
    a, b, c = m.group(1), m.group(2), m.group(3)
    return f'#### M1-{a}-{b}{int(c):02d} '
t = re.sub(r'^#### M1-([A-Z]{2})-(\d+)\.(\d+)\s+', fix_num, t, flags=re.M)

# 2) 第二个 ### PS-03 标题重复：删掉第二次出现的那行
parts = t.split('### PS-03 多维随机变量及其分布')
if len(parts) == 3:
    t = parts[0] + '### PS-03 多维随机变量及其分布' + parts[1] + parts[2].lstrip('\n')
    # 3) 第二处标题错位：0301->0302，0302->0303
    i = t.index('### PS-03 多维随机变量及其分布')
    head, tail = t[:i], t[i:]
    tail = tail.replace('#### M1-PS-0301 联合与边缘', '#### M1-PS-0302 条件分布与独立性', 1)
    tail = tail.replace('#### M1-PS-0302 条件分布与独立性', '#### M1-PS-0303 二维函数的分布', 1)
    t = head + tail

HS03 = r"""
### HS-03 一元函数积分学

#### M1-HS-0301 不定积分

不定积分是求导的逆运算，$\int f(x)dx=F(x)+C$ 当且仅当 $F'=f$。方法有三条主线：**凑微分**（把 $\int f(\varphi(x))\varphi'(x)dx$ 写成 $\int f(u)du$）、**分部积分**（$\int u\,dv=uv-\int v\,du$，选 $u$ 的口诀是"反对幂三指"，即反三角、对数、幂函数、三角、指数依次优先）、**有理函数分解**（先因式分解分母，再拆成部分分式）。典型计算：$\int xe^x dx$ 取 $u=x,dv=e^xdx$，得 $xe^x-e^x+C$。易错点有两个：一是**不定积分必须写 $+C$**，漏掉即错；二是换元后必须**回代**原变量，且若用 $u=\varphi(x)$ 还要检查 $\varphi$ 是否单调，否则反函数不存在。

#### M1-HS-0302 定积分与性质

定积分由牛顿-莱布尼茨公式计算：$\int_a^b f(x)dx=F(b)-F(a)$，其中 $F$ 是 $f$ 的任一原函数。常用性质有：线性、区间可加（$\int_a^b=\int_a^c+\int_c^b$）、保号性（$f\ge0\Rightarrow\int f\ge0$）、估值定理（$m(b-a)\le\int f\le M(b-a)$）与积分中值定理（存在 $\xi$ 使 $\int_a^b f=f(\xi)(b-a)$）。对称区间上**奇函数积分为零**，偶函数可折半。变上限积分的导数：$\frac{d}{dx}\int_a^{x}f(t)dt=f(x)$。易错点：**换元必须同时换上下限**，若保留原变量只换 $dx$ 则整题作废；另外变上限求导时上下限都要导（$\frac{d}{dx}\int_{a(x)}^{b(x)}=f(b)b'-f(a)a'$）。

#### M1-HS-0303 反常积分

反常积分有两类：**无穷限**（$\int_a^{+\infty}$）与**无界函数**（被积函数在端点趋于无穷）。判敛的基本尺子是 $p$ 积分：$\int_1^{+\infty}x^{-p}dx$ 在 $p>1$ 时收敛，$\int_0^1x^{-p}dx$ 在 $p<1$ 时收敛——**两个方向相反**，这是最容易记混的一处。判敛工具是比较判别法（与 $p$ 积分比阶）、极限比较法（$\lim f/g=c\in(0,\infty)$ 时同敛散）、以及 Dirichlet 与 Abel 判别法（处理振荡型）。典型计算：$\int_1^{+\infty}\frac{dx}{x^{3/2}}$ 收敛且等于 $2$。易错点：收敛的定义是**部分积分有极限**，不能只看被积函数趋于零（$\int_1^\infty\frac{dx}{x}$ 也趋于零但发散）。

#### M1-HS-0304 定积分应用

几何应用有四类公式：**面积** $S=\int_a^b|f-g|dx$；**体积**绕 $x$ 轴为 $V=\pi\int_a^b y^2dx$，绕 $y$ 轴用柱壳法 $V=2\pi\int_a^b x|f(x)|dx$；**弧长** $L=\int_a^b\sqrt{1+y'^2}dx$；**旋转体侧面积** $S=2\pi\int_a^b y\sqrt{1+y'^2}dx$。物理应用包括变力做功、水压力、质心与平均值。典型计算：$y=x^2$ 在 $[0,1]$ 绕 $x$ 轴的体积为 $\pi\int_0^1x^4dx=\pi/5$。易错点有两个：柱壳法的**半径是 $x$ 而非 $y$**；**侧面积与表面积不是一回事**，表面积还要加上两个底面，而侧面积公式里必须带弧长微元 $\sqrt{1+y'^2}$。

"""

HS07 = r"""
### HS-07 无穷级数

#### M1-HS-0701 数项级数判敛

正项级数判敛按"由弱到强"的顺序试：**比较判别法**（找已知敛散的参照级数）、**极限比较法**（与 $1/n^p$、$q^n$ 比阶）、**比值法**（$\lim a_{n+1}/a_n=\rho$，$\rho<1$ 收敛、$\rho>1$ 发散）、**根值法**（$\lim\sqrt[n]{a_n}=\rho$）、**积分判别法**（$a_n=f(n)$ 且 $f$ 单调递减）。交错级数用**莱布尼茨判别法**：$a_n$ 单调递减且 $\lim a_n=0$ 时收敛，且余项 $|r_n|\le a_{n+1}$。绝对收敛必然收敛，条件收敛则是收敛但取绝对值后发散。易错点：**比值法与根值法在 $\rho=1$ 时失效**，必须改用比较法，不能就此下结论；莱布尼茨的两个条件缺一不可（漏掉"单调递减"会判错）。

#### M1-HS-0702 幂级数

幂级数 $\sum a_n(x-x_0)^n$ 的核心是收敛半径：$R=\lim\left|\frac{a_n}{a_{n+1}}\right|$ 或 $R=1/\lim\sqrt[n]{|a_n|}$，在 $(x_0-R,x_0+R)$ 内绝对收敛、外部发散、**端点必须单独代入判敛**。求和函数的套路是"逐项求导或逐项积分，把系数凑成熟知的展开"：$\frac{1}{1-x}=\sum x^n$、$e^x=\sum\frac{x^n}{n!}$、$\ln(1+x)=\sum\frac{(-1)^{n-1}x^n}{n}$、$\sin x$、$\cos x$、$(1+x)^\alpha$。逐项求导与积分**不改变收敛半径**，但端点敛散性可能改变。典型计算：$\sum nx^n$ 由 $\left(\sum x^n\right)'=\frac{1}{(1-x)^2}$ 得和函数 $\frac{x}{(1-x)^2}$。易错点：把 $R$ 直接当作收敛区间（漏判端点）；逐项求导后仍沿用原端点的敛散结论。

#### M1-HS-0703 傅里叶级数

周期为 $2\pi$ 的函数展开为 $f(x)\sim\frac{a_0}{2}+\sum_{n=1}^{\infty}(a_n\cos nx+b_n\sin nx)$，系数由 $a_n=\frac1\pi\int_{-\pi}^{\pi}f\cos nx\,dx$、$b_n=\frac1\pi\int_{-\pi}^{\pi}f\sin nx\,dx$ 给出。收敛性由**狄利克雷条件**保证：$f$ 在一个周期内连续或只有有限个第一类间断点、且只有有限个极值时，级数在连续点收敛于 $f(x)$，在间断点收敛于 $\frac{f(x^-)+f(x^+)}{2}$。**奇函数只含正弦项**（正弦级数），**偶函数只含余弦项**（余弦级数），这就是"奇延拓"与"偶延拓"的用途；周期为 $2l$ 时把 $nx$ 换成 $\frac{n\pi x}{l}$。典型计算：$f(x)=x$ 在 $(-\pi,\pi)$ 上展开得 $2\sum\frac{(-1)^{n-1}}{n}\sin nx$。易错点：**间断点的值是左右极限的平均，不是函数值**；用错延拓方式会导致系数全错。
"""

# 4) 插入 HS-03（在 HS-04 之前）
t = t.replace('\n### HS-04 向量代数与空间解析几何', HS03.rstrip() + '\n\n### HS-04 向量代数与空间解析几何', 1)

# 5) 插入 HS-0605（在 HS-07 之前，属 HS-06 章末）与 HS-07（在 HS-08 之前）
HS0605 = r"""
#### M1-HS-0605 三大公式与场论

三大公式把边界积分与区域积分互相转换：**格林公式** $\oint_L Pdx+Qdy=\iint_D\left(\frac{\partial Q}{\partial x}-\frac{\partial P}{\partial y}\right)dxdy$（平面闭曲线 ↔ 二重积分）；**高斯公式** $\oiint_\Sigma P\,dydz+Q\,dzdx+R\,dxdy=\iiint_\Omega\left(\frac{\partial P}{\partial x}+\frac{\partial Q}{\partial y}+\frac{\partial R}{\partial z}\right)dV$（闭曲面 ↔ 三重积分）；**斯托克斯公式** $\oint_\Gamma Pdx+Qdy+Rdz=\iint_\Sigma(\nabla\times\vec F)\cdot\vec n\,dS$（空间闭曲线 ↔ 曲面积分）。三者的前提都是**闭 + 正向**（格林取逆时针、高斯取外侧）且偏导连续。场论三算子：梯度 $\mathrm{grad}$ 把标量变向量、散度 $\mathrm{div}$ 把向量变标量、旋度 $\mathrm{curl}$ 把向量变向量。保守场有三个等价刻画：$\oint=0$、$\mathrm{curl}\vec F=0$、路径无关且有势函数。易错点：不闭合时要**补线或补面再减去**；有奇点（如 $\frac{1}{r^2}$ 型）要**挖去小球**再套公式。

### HS-07 无穷级数
"""
t = t.replace('\n### HS-08 常微分方程', HS0605.rstrip().rsplit('\n### HS-07 无穷级数', 1)[0] + '\n\n' + HS07.rstrip() + '\n\n### HS-08 常微分方程', 1)

P.write_text(t, encoding='utf-8')
print('done', len(t))