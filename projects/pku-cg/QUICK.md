# 北大图形学 · 一小时上手

> **前提**：线性代数（矩阵乘法、齐次坐标）；会用 Python 或 C++。
> **这一小时的产出**：一个**纯 CPU、无库**的渲染器，把三个 3D 三角形画进 PPM 图。

---

## 1 这一小时只做一件事

**不调任何图形库，把 3D 点投影到 2D 像素并填成三角形。**

因为所有图形库（OpenGL / Vulkan / Metal）内部就是这一件事。绕过它们一次，你就再也不怕"黑屏"。

---

## 2 最小可跑（50 分钟）

### 2.1 画布（5 分钟）

```python
W, H = 400, 400
img = [[(0,0,0)]*W for _ in range(H)]        # RGB
```

### 2.2 MVP 变换（15 分钟）

```python
import math
def matmul(A, B): ...
def perspective(fov, aspect, near, far):
    f = 1/math.tan(fov/2)
    return [[f/aspect,0,0,0],[0,f,0,0],
            [0,0,(far+near)/(near-far),2*far*near/(near-far)],
            [0,0,-1,0]]

def look_at(eye, target, up): ...             # 视图矩阵
def model(angle): ...                          # 旋转矩阵
```

**顺序**：`MVP = P · V · M`，**从右往左作用**（先模型、再视图、最后投影）。

### 2.3 齐次除法 + 视口（10 分钟）

```python
def project(v, MVP):
    x = sum(MVP[0][i]*v[i] for i in range(4))
    y = sum(MVP[1][i]*v[i] for i in range(4))
    w = sum(MVP[3][i]*v[i] for i in range(4))
    ndc_x, ndc_y = x/w, y/w                   # ← 齐次除法
    px = int((ndc_x+1)*0.5*W)
    py = int((1-(ndc_y+1)*0.5)*H)             # 屏幕 y 向下
    return px, py, 1/w                        # 1/w 用于深度
```

**命门**：`w` 除必须在这里做，且**保留 `1/w` 做深度插值**（屏幕空间线性的是 $1/z$，不是 $z$）。

### 2.4 填三角形（20 分钟）

```python
def fill(p0, p1, p2):
    # 包围盒 + 重心坐标
    minx = min(p0[0],p1[0],p2[0]); maxx = max(...)
    miny = ...; maxy = ...
    area = (p1[0]-p0[0])*(p2[1]-p0[1]) - (p2[0]-p0[0])*(p1[1]-p0[1])
    if area == 0: return
    for y in range(max(0,miny), min(H,maxy+1)):
        for x in range(max(0,minx), min(W,maxx+1)):
            w0 = ((p1[0]-x)*(p2[1]-y) - (p2[0]-x)*(p1[1]-y))/area
            w1 = ((p2[0]-x)*(p0[1]-y) - (p0[0]-x)*(p2[1]-y))/area
            w2 = 1 - w0 - w1
            if w0 >= 0 and w1 >= 0 and w2 >= 0:
                img[y][x] = (255, 128, 0)      # 橙色
```

**重心坐标三个都 $\ge0$ 才在三角形内**。这就是"点是否在三角形内"的标准判据。

### 2.5 存图（5 分钟）

```python
with open("out.ppm", "w") as f:
    f.write(f"P3\n{W} {H}\n255\n")
    for row in img:
        for r,g,b in row: f.write(f"{r} {g} {b} ")
        f.write("\n")
```

---

## 3 三个核心难点

### 3.1 齐次除法必须在裁剪之后

如果先除 $w$ 再裁剪，$w<0$（相机背后的点）会被"投影到屏幕上"，产生诡异的三角形。
**正确顺序：变换 → 裁剪（在齐次空间）→ 齐次除法**。这一小时为了简单可以先不裁剪（数据都在相机前）。

### 3.2 深度用 $1/w$ 插值

屏幕空间里**线性变化的是 $1/z$**，不是 $z$。所以深度缓冲存 `1/w`，比较时越大越近（或统一取反）。

### 3.3 重心坐标同时给你三件事

`(w0,w1,w2)` 三个数：
- **判断内外**（都 $\ge0$）
- **插值属性**（颜色/纹理/深度 = $w_0 A + w_1 B + w_2 C$）
- **透视校正**（要除以 $w$ 再加权）

**一个 `(w0,w1,w2)` 顶三次用**，这是光栅化的全部秘密。

---

## 4 卡住怎么办

| 现象 | 原因 | 修法 |
|---|---|---|
| 全黑 | 三角形绕序反了（`area<0`） | 取绝对值或换顶点顺序 |
| 图像上下颠倒 | 屏幕 y 方向没翻 | `py = (1 - ndc_y)/2 * H` |
| 三角形扭曲 | 忘了 `w` 除 | 加 `/w` |
| 边缘有洞 | 包围盒没取整 | `int(floor())` / `int(ceil())` |

---

## 5 这一小时之后

- 出图了 → 加深度缓冲（两张三角形互相遮挡），验证 $1/z$ 的作用。
- 想深入 → `OUTLINE.md` 的 M5（光线追踪），换一条完全不同的路子。

## 6 通向

| 你要什么 | 去哪 |
|---|---|
| 完整 6 个里程碑 | `OUTLINE.md` |
| 详细实验记录 | `NOTES.md` |