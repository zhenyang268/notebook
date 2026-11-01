## PS-03 多维随机变量及其分布

### PS-03.1 条件分布与独立性

条件分布刻画在已知一个变量取值的条件下另一个变量的分布。离散情形下，当 $p_{\cdot j}=P(Y=y_j)>0$ 时，$P(X=x_i\mid Y=y_j)=p_{ij}/p_{\cdot j}$，且对每个固定的 $y_j$，这些条件概率关于 $i$ 求和为 $1$。连续情形下，当 $f_Y(y)>0$ 时，条件密度为 $f_{X\mid Y}(x\mid y)=f(x,y)/f_Y(y)$，条件分布函数由 $F_{X\mid Y}(x\mid y)=\int_{-\infty}^{x}f_{X\mid Y}(t\mid y)\,dt$ 给出。随机变量 $X$ 与 $Y$ 独立当且仅当联合分布函数满足 $F(x,y)=F_X(x)F_Y(y)$ 对所有 $x,y$ 成立；离散时等价于 $p_{ij}=p_{i\cdot}p_{\cdot j}$，连续时等价于 $f(x,y)=f_X(x)f_Y(y)$ 几乎处处成立。易错点是把“$P(X=Y)=0$”误当作独立：若 $X=Y$ 且 $X$ 连续，则 $P(X=Y)=0$，但 $X$ 与 $Y$ 明显不独立。判断独立性应回到联合分布能否分解。

### PS-03.2 二维函数的分布

设 $Z=g(X,Y)$，求 $Z$ 的分布的基本方法是分布函数法：先写 $F_Z(z)=P(g(X,Y)\le z)=\iint_{g(x,y)\le z}f(x,y)\,dx\,dy$，再对 $z$ 求导得密度。离散型只需枚举所有满足 $g(x_i,y_j)=z_k$ 的取值并合并概率。连续型中，若 $X,Y$ 独立，则和的密度由卷积给出：$f_{X+Y}(z)=\int_{-\infty}^{+\infty}f_X(x)f_Y(z-x)\,dx$。若变换 $(X,Y)\mapsto(U,V)$ 可逆，可用雅可比公式 $f_{U,V}(u,v)=f_{X,Y}(x(u,v),y(u,v))\left|\frac{\partial(x,y)}{\partial(u,v)}\right|$。极值情形常用：若 $X_1,\dots,X_n$ 独立同分布，分布函数为 $F$，则 $M=\max X_i$ 满足 $F_M(z)=[F(z)]^n$，$N=\min X_i$ 满足 $F_N(z)=1-[1-F(z)]^n$。典型计算如两个独立 $U(0,1)$ 之和的密度为三角形；易错点是未独立时不能把联合密度拆成乘积，也不能直接套卷积。

## PS-04 数字特征

### PS-04.1 数学期望

数学期望是随机变量取值的加权平均。离散型 $X$ 的分布为 $P(X=x_i)=p_i$ 时，若 $\sum_i |x_i|p_i<+\infty$，则 $E(X)=\sum_i x_ip_i$；连续型 $X$ 的密度为 $f(x)$ 时，若 $\int_{-\infty}^{+\infty}|x|f(x)\,dx<+\infty$，则 $E(X)=\int_{-\infty}^{+\infty}xf(x)\,dx$。更一般地，$E[g(X,Y)]$ 可直接用联合分布计算：离散时 $\sum_{i,j}g(x_i,y_j)p_{ij}$，连续时 $\iint g(x,y)f(x,y)\,dx\,dy$，不必先求 $g(X,Y)$ 的分布。期望具有线性性：$E(aX+bY+c)=aE(X)+bE(Y)+c$，此式不要求独立；若 $X,Y$ 独立且期望存在，则 $E(XY)=E(X)E(Y)$。典型计算如 $X\sim U(0,1)$ 时 $E(e^X)=\int_0^1e^x\,dx=e-1$。易错点是误用 $E(1/X)=1/E(X)$，该式一般无此关系。

### PS-04.2 方差与协方差

方差度量随机变量围绕均值的离散程度，定义为 $D(X)=E[(X-E(X))^2]$，常用计算公式为 $D(X)=E(X^2)-[E(X)]^2$。它满足 $D(aX+b)=a^2D(X)$，常数方差为零。协方差刻画两个变量的线性关联：$\operatorname{Cov}(X,Y)=E[(X-E(X))(Y-E(Y))]=E(XY)-E(X)E(Y)$，且 $\operatorname{Cov}(X,X)=D(X)$。方差的和差公式为 $D(X\pm Y)=D(X)+D(Y)\pm2\operatorname{Cov}(X,Y)$，因此仅当协方差为零时才有 $D(X\pm Y)=D(X)+D(Y)$。相关系数 $\rho_{XY}=\frac{\operatorname{Cov}(X,Y)}{\sqrt{D(X)}\sqrt{D(Y)}}$ 满足 $|\rho_{XY}|\le1$。若 $X,Y$ 独立且方差存在，则 $\operatorname{Cov}(X,Y)=0$，即独立蕴涵不相关；反之不成立，例如 $X\sim U(-1,1)$，$Y=X^2$，二者协方差为零但并不独立。典型计算：$D(2X-3Y+1)=4D(X)+9D(Y)-12\operatorname{Cov}(X,Y)$。

### PS-04.3 矩与常用数字特征

矩是数字特征的统一描述。$k$ 阶原点矩为 $E(X^k)$，$k$ 阶中心矩为 $E[(X-E(X))^k]$，其中一阶原点矩是期望，二阶中心矩是方差。常用分布的数字特征必须能直接调用，见下表。

| 分布 | $E(X)$ | $D(X)$ |
|---|---|---|
| $B(1,p)$ | $p$ | $p(1-p)$ |
| $B(n,p)$ | $np$ | $np(1-p)$ |
| $P(\lambda)$ | $\lambda$ | $\lambda$ |
| $U(a,b)$ | $\frac{a+b}{2}$ | $\frac{(b-a)^2}{12}$ |
| $\operatorname{Exp}(\lambda)$ | $\frac1\lambda$ | $\frac1{\lambda^2}$ |
| $N(\mu,\sigma^2)$ | $\mu$ | $\sigma^2$ |

例如若 $X\sim N(\mu,\sigma^2)$，则 $E(aX+b)=a\mu+b$，$D(aX+b)=a^2\sigma^2$。易错点集中在参数约定：指数分布的参数 $\lambda$ 是速率，均值为 $1/\lambda$ 而非 $\lambda$；二项分布的方差含因子 $1-p$。此外，$E(X^2)=D(X)+[E(X)]^2$ 是连接二阶矩与方差的常用桥梁。

## PS-05 大数定律与中心极限定理

### PS-05.1 切比雪夫与大数定律

切比雪夫不等式给出偏差概率的上界：若 $E(X)=\mu$，$D(X)=\sigma^2$，则对任意 $\varepsilon>0$，$P(|X-\mu|\ge\varepsilon)\le\frac{\sigma^2}{\varepsilon^2}$，等价地 $P(|X-\mu|<\varepsilon)\ge1-\frac{\sigma^2}{\varepsilon^2}$。它只要求期望和方差存在，不要求分布具体形式。大数定律说明样本均值在什么意义下稳定于期望。切比雪夫大数定律：若 $X_1,\dots,X_n$ 两两不相关且方差一致有界，则 $\frac1n\sum_{i=1}^n(X_i-E(X_i))$ 依概率收敛于 $0$。辛钦大数定律：若 $X_i$ 独立同分布且 $E(X_i)=\mu$ 存在，则 $\frac1n\sum_{i=1}^nX_i$ 依概率收敛于 $\mu$。伯努利大数定律是其特例，频率依概率收敛于概率 $p$。典型计算：$P(|X-\mu|\ge3\sigma)\le1/9$。易错点是混淆“依概率收敛”与“几乎处处收敛”，以及忽略方差存在或一致有界条件。

### PS-05.2 中心极限定理

中心极限定理说明大量独立随机变量之和的标准化分布趋于标准正态分布。若 $X_1,\dots,X_n$ 独立同分布，$E(X_i)=\mu$，$D(X_i)=\sigma^2>0$，则对任意实数 $x$，有
$$P\left(\frac{\sum_{i=1}^nX_i-n\mu}{\sigma\sqrt n}\le x\right)\longrightarrow\Phi(x),$$
其中 $\Phi$ 为标准正态分布函数。等价地，当 $n$ 充分大时，$\sum X_i$ 近似服从 $N(n\mu,n\sigma^2)$，样本均值 $\bar X$ 近似服从 $N(\mu,\sigma^2/n)$。德莫佛—拉普拉斯定理是其特例：若 $X\sim B(n,p)$，则 $\frac{X-np}{\sqrt{np(1-p)}}$ 近似服从 $N(0,1)$，即 $P(a\le X\le b)\approx\Phi\left(\frac{b-np}{\sqrt{np(1-p)}}\right)-\Phi\left(\frac{a-np}{\sqrt{np(1-p)}}\right)$。典型计算中常作连续性修正，把端点改为 $a-0.5$、$b+0.5$。易错点是把中心极限定理误解为随机变量本身依概率收敛于正态变量；它给出的是标准化和依分布收敛，且分母为 $\sigma\sqrt n$。
