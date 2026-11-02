# python-basics · 分章详细

## 第 1 章 对象模型与可变性

**要解决的问题**：搞清楚「变量、对象、引用」三者的关系。如果搞不清，后面所有关于别名、传参、默认参数、`is` 与 `==` 的问题都会答错，这也是面试官用来判断一个候选人是否真的写过 Python 的第一道分水岭。

**机制**：Python 里变量是名字到对象的绑定，不是装值的盒子。赋值 `b = a` 只增加一个指向同一对象的引用，不复制对象。每个对象有三个要素：`id()`（生命周期内唯一，CPython 里就是内存地址，但语言层面不保证）、`type()`、值。可变对象（`list`、`dict`、`set`、自定义类实例）允许原地修改；不可变对象（`int`、`str`、`tuple`、`frozenset`）的「修改」都是新建对象再重新绑定。

函数传参是**传对象引用**（call by object reference / call by sharing）：形参和实参绑定同一个对象。函数内对形参重新赋值不影响调用方，但对可变对象做原地修改会影响调用方。

```python
def f(x, acc=[]):        # 默认值在 def 执行时求值一次，存进 f.__defaults__
    acc.append(x)
    return acc

a = [1, 2]
b = a
b += [3]                 # list.__iadd__ 原地扩展，a 和 b 仍是同一对象
print(a)                 # [1, 2, 3]
c = a + [4]              # __add__ 新建列表，a 不变
print(a, c)              # [1, 2, 3] [1, 2, 3, 4]
print(f(1), f(2))        # [1] [1, 2] —— 第二次调用复用了同一个列表
```

`+=` 与 `+` 的区别来自 `__iadd__`：可变类型实现了 `__iadd__` 就原地改，没有则退化为 `__add__` 再赋值。所以 `t = (1, 2); t += (3,)` 是新建元组，而 `l += [3]` 是原地改。

不可变对象要参与哈希：`dict` 的键要求可哈希，规则是「`__hash__` 稳定，且 `a == b` 时 `hash(a) == hash(b)`」。自定义类默认按 `id` 哈希；一旦你重写 `__eq__` 而没重写 `__hash__`，该类实例就变成不可哈希（`__hash__` 被置为 `None`）。

**最小例子**：`a = (1, [2]); a[1].append(3)` 能成功，元组不可变指的是它保存的**引用**不可变，不代表引用指向的对象冻结。要真正只读，得自己保证不泄漏内部可变对象（或用 `tuple` + `frozenset` 之类的组合）。

**面试高频问法**：

1. 「Python 是值传递还是引用传递？」→ 考点是别掉进二选一陷阱 → 答法：都不是，是传对象引用；形参和实参绑定同一对象，重新赋值只改本地名字，原地修改才会影响调用方。
2. 「`is` 和 `==` 什么区别？」→ 考点是身份 vs 相等 → 答法：`is` 比 `id`，`==` 走 `__eq__`；只该用 `is` 和 `None`、`True`、`False` 这类单例比较。
3. 「`1 is 1`、`'ab' is 'ab'` 一定为 True 吗？」→ 考点是能否区分语言规范和 CPython 实现细节 → 答法：不一定。CPython 缓存了小整数和部分字符串（驻留），这是实现细节，代码不能依赖；`256 is 256` 与 `257 is 257` 在交互式环境里结果可能不同。
4. 「可变默认参数为什么是坑？」→ 考点是默认值求值时机 → 答法：默认值在 `def` 执行时求值一次并存进 `__defaults__`，之后每次调用共享；正确写法是默认 `None`，函数内 `if acc is None: acc = []`。
5. 「元组真的不可变吗？」→ 考点是浅不可变 → 答法：元组只保证自身保存的引用不变，元素若可变仍可原地修改；所以含 `list` 的元组不可哈希。

## 第 2 章 容器、切片与推导式

**要解决的问题**：在正确的地方用正确的容器与构造方式，避免「用 `list` 做成员判断」「用 `*` 复制嵌套结构」「以为切片是视图」这三类高频错误。

**机制**：`list` 是动态数组，尾部 `append`/`pop` 摊销 $O(1)$，按实现而定地做超额分配，扩容时整体搬移；头部插入是 $O(n)$。`dict` 与 `set` 是哈希表，平均 $O(1)$ 查找，代价是额外内存和键必须可哈希。`dict` 自 Python 3.7 起由语言规范保证插入有序。`tuple` 定长、内存紧凑，适合当记录用。

切片 `s[start:stop:step]` 的规则：三个参数都可省，越界不报错（会被截断），负索引从尾部算，`step` 为负表示反向。对 `list` 切片**返回新列表（浅拷贝）**；切片赋值可以改变长度：

```python
a = [0, 1, 2, 3, 4]
print(a[1:4], a[::-1], a[10:])      # [1, 2, 3] [4, 3, 2, 1, 0] []
a[1:3] = [9]                        # 切片赋值：删除 2 个、插入 1 个
print(a)                            # [0, 9, 3, 4]

grid = [[0] * 3] * 3                # 错：内层列表只创建一次
grid[0][0] = 1
print(grid)                         # [[1, 0, 0], [1, 0, 0], [1, 0, 0]]
grid = [[0] * 3 for _ in range(3)]  # 对：每次迭代新建
```

推导式在 Python 3 有独立作用域，循环变量不会泄漏到外层，但可以读取外层变量。列表推导会立刻构造整个列表；生成器表达式 `(x for x in ...)` 惰性产出，适合只遍历一次或数据量大。`sorted()` 返回新列表且稳定，`list.sort()` 原地排序并返回 `None`——这也是「为什么我写了 `a = a.sort()` 结果变 None」的答案。

**最小例子**：`a = [[1, 2], [3, 4]]`，`b = a[:]` 后 `b[0].append(9)`，`a` 也会变，因为浅拷贝只复制了外层列表，内层元素仍是同一批对象。需要独立副本时用 `copy.deepcopy(a)`，它用 `memo` 字典记录已拷贝对象，能处理循环引用。

**面试高频问法**：

1. 「`a[:]`、`copy.copy`、`copy.deepcopy` 区别？」→ 考点是浅拷贝边界 → 答法：前两者都只复制顶层容器、内部元素共享引用；`deepcopy` 递归复制并用 `memo` 处理循环引用，代价高。
2. 「`[[0]*3]*3` 错在哪？」→ 考点是 `*` 复制的是引用 → 答法：内层列表只求值一次，三行指向同一对象；要用推导式或 `[[0]*3 for _ in range(3)]`。
3. 「`list.append` 是 $O(1)$ 吗？」→ 考点是摊销分析 → 答法：摊销 $O(1)$，扩容时单次是 $O(n)$，因为要搬移元素，但摊到每次 append 上是常数；具体扩容倍数按实现而定。
4. 「`list` 切片和 NumPy 切片一样吗？」→ 考点是拷贝 vs 视图 → 答法：不一样。`list` 切片是新列表（浅拷贝），NumPy 基本切片返回共享内存的视图，改视图会影响原数组。
5. 「`in` 操作用在 `list` 和 `set` 上有什么区别？」→ 考点是复杂度意识 → 答法：`list` 是线性扫描 $O(n)$，`set`/`dict` 是哈希查找平均 $O(1)$；频繁成员判断要换 `set`。

## 第 3 章 迭代器与生成器

**要解决的问题**：理解 `for` 到底做了什么，以及如何用生成器把「一次性、惰性、可暂停」的计算写出来。这是后面 `asyncio`、上下文管理器、流式处理的地基。

**机制**：迭代协议分两层。**可迭代对象**实现 `__iter__`，返回一个**迭代器**；迭代器实现 `__next__`，每次返回下一个值，耗尽时抛 `StopIteration`。迭代器自身也实现 `__iter__` 且返回 `self`，所以 `iter(it) is it`。`for` 循环等价于：

```python
it = iter(obj)
while True:
    try:
        x = next(it)
    except StopIteration:
        break
    # 循环体
```

生成器函数是含 `yield` 的函数，调用它不执行函数体，而是返回一个生成器对象（本身就是迭代器）。每次 `next` 执行到下一个 `yield` 挂起，局部变量和执行位置保存在帧里。`send(v)` 把 `v` 作为**当前挂起的 `yield` 表达式的值**送进去，所以首次必须用 `next()` 或 `send(None)` 启动。`throw` 在挂起点抛异常，`close` 抛 `GeneratorExit`。生成器里 `return x` 会变成 `StopIteration(x)`，值挂在 `.value` 上。

`yield from sub` 做三件事：把迭代委托给子迭代器、把 `send`/`throw` 透传下去、捕获子生成器的 `StopIteration` 并把 `value` 作为 `yield from` 表达式的值。

```python
def take(n, iterable):
    it = iter(iterable)
    for _ in range(n):
        yield next(it)          # 惰性：不提前消费整个 iterable

def chain(*iterables):
    for it in iterables:
        yield from it           # 委托 + 透传 send/throw

g = (x * x for x in range(10**6))   # 生成器表达式，不建列表
print(take(3, g))                   # <generator object take>
print(list(take(3, g)))             # [0, 1, 4]
```

**最小例子**：`it = iter([1, 2]); next(it) → 1; next(it) → 2; next(it)` 抛 `StopIteration`。此时再 `list(it)` 得到 `[]`——迭代器是一次性的，耗尽后不会重置。生成器同理，这也是「生成器表达式不能重复遍历」的原因。

**面试高频问法**：

1. 「可迭代对象和迭代器的区别？」→ 考点是协议分层 → 答法：可迭代对象只需 `__iter__`，每次能产出新迭代器（如 `list`）；迭代器还要 `__next__`，且 `iter(it) is it`，状态只能前进一次。
2. 「生成器为什么省内存？」→ 考点是惰性求值 + 帧挂起 → 答法：不一次性构造所有结果，只在 `next` 时计算到下一个 `yield`，帧里保存局部状态；代价是只能顺序访问、只能遍历一次。
3. 「`yield from` 和 `for x in sub: yield x` 有什么不同？」→ 考点是委托语义 → 答法：`yield from` 还会透传 `send`/`throw`/`close`，并捕获子生成器的 `return` 值作为表达式结果；单纯 `for` 循环丢掉返回值也不支持双向通信。
4. 「生成器能不能重复用？耗尽了怎么办？」→ 考点是一次性语义 → 答法：不能。耗尽后再 `next` 一直抛 `StopIteration`，要重来得重新调用生成器函数或重建表达式。
5. 「没有 `__iter__` 的类能被 `for` 遍历吗？」→ 考点是旧式序列协议回退 → 答法：可以。Python 会退化为用 `__getitem__(0)`、`__getitem__(1)`……直到抛 `IndexError`，这是历史遗留的兼容路径；新代码应显式实现 `__iter__`。

## 第 4 章 装饰器与闭包

**要解决的问题**：在不改函数体、不改调用方写法的前提下，给函数附加横切行为（计时、日志、缓存、鉴权、重试），并且让「函数 + 它依赖的外部变量」能像普通值一样被传递。不解决的话，这些逻辑只能复制到每个函数里，或者被迫用继承/包装类把简单函数对象搞复杂。

**机制**：

- 函数是一等对象，`def f()` 只是「创建函数对象并绑定到名字 f」。所以函数可以当参数传、当返回值返。
- 装饰器就是接受可调用对象、返回可调用对象的高阶函数。`@deco` 是语法糖，等价于 `f = deco(f)`，**在函数定义时执行一次**，不是每次调用都执行。
- 闭包：内层函数引用了外层函数的局部变量（free variable）。外层返回后，这些变量不会随栈帧销毁，而是被搬进 cell 对象，挂在 `f.__closure__` 上，名字列表在 `f.__code__.co_freevars`。
- 内层函数要给外层变量**重新绑定**，必须 `nonlocal`；不加就是新建一个内层局部变量，外层那个纹丝不动（只读引用则不需要）。
- 多个装饰器叠加：应用顺序自下而上（离函数近的先包），调用时进入顺序自上而下。
- `functools.wraps` 把 `__module__/__name__/__qualname__/__doc__/__dict__` 复制到 wrapper 上，并写入 `__wrapped__`，`inspect.signature` 会顺着 `__wrapped__` 找到原函数签名。

```python
import functools, time

def timed(label):                      # 第 1 层：装饰器参数
    def deco(fn):                      # 第 2 层：被装饰的函数
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):  # 第 3 层：实际调用
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                print(f"{label}:{fn.__name__} {time.perf_counter() - t0:.3f}s")
        return wrapper
    return deco

def counter():
    n = 0
    def inc():
        nonlocal n                     # 没有它 n += 1 会报 UnboundLocalError
        n += 1
        return n
    return inc
```

**最小例子**：

```python
@timed("db")
def query(sql, limit=10):
    return [sql] * limit

query("select 1")        # 打印 db:query 0.000s，返回长度 10 的列表
query.__name__           # 'query'，靠 wraps 保住
query.__wrapped__("x")   # 绕过装饰器直接调原函数

c = counter(); c(), c()  # 1, 2
c.__closure__[0].cell_contents   # 2
```

`@timed("db")` 的执行过程是：先算 `timed("db")` 得到 `deco`，再用 `deco(query)` 得到 wrapper 并绑定回 `query`。

**面试高频问法**：

1. **「装饰器的本质是什么，`@` 做了什么？」** → 考点是「定义时求值、返回可调用对象」。答法：装饰器是 `f = deco(f)` 的语法糖，在函数定义时执行一次，把原函数替换成返回值；所以它既能返回函数，也能返回类或任意可调用对象。
2. **「为什么要 `functools.wraps`，不加会怎样？」** → 考点是元信息与自省。答法：不加的话 `__name__` 变成 `wrapper`、`__doc__` 丢失、签名变成 `*args, **kwargs`，日志、文档生成、依赖签名的框架（如 FastAPI 注入、`inspect.signature`）都会出错；wraps 负责拷贝元信息并设置 `__wrapped__`。
3. **「闭包变量存在哪，为什么需要 `nonlocal`？」** → 考点是 cell 与作用域规则。答法：自由变量存在函数的 `__closure__` cell 里；作用域规则是「内层赋值即视为局部变量」，所以重新绑定外层变量必须显式 `nonlocal`。
4. **「循环里创建闭包，为什么都拿到最后一个值？」** → 考点是延迟绑定。答法：闭包捕获的是变量本身而不是当时的值，循环结束后变量已是最后一个值；修复用默认参数 `lambda i=i: ...` 或 `functools.partial` 把值提前固定。
5. **「带参数的装饰器为什么要写三层？」** → 考点是求值层次。答法：最外层收装饰器参数，中间层收被装饰函数，最内层收调用参数；因为 `@deco(arg)` 先执行 `deco(arg)`，它必须返回一个真正能接收函数的装饰器。

## 第 5 章 上下文管理器与 with

**要解决的问题**：把「获取资源 → 使用 → 无论发生什么都释放」这个模式从业务代码里抽出来，保证异常、`return`、`break` 路径下释放都发生，而且释放逻辑只写一次。不解决的话，就是满屏 `try/finally`，漏一个就是文件句柄或锁泄漏。

**机制**：

- 协议两个方法：`__enter__(self)` 的返回值绑定给 `as` 后面的名字；`__exit__(self, exc_type, exc, tb)` 在退出时被调用，正常退出时三个参数都是 `None`。
- `__exit__` 返回**真值**表示异常已被处理，`with` 块内的异常不再向外传播；返回 `None`/`False` 则原样抛出。所以清理型管理器应显式 `return False`（或干脆不 return），吞异常必须是刻意的。
- `with a() as x, b() as y:` 等价于两层嵌套 `with`，退出顺序与进入顺序相反，`b` 先退出。
- `contextlib.contextmanager` 把生成器函数变成上下文管理器：`yield` 之前是 `__enter__`，`yield` 出去的值就是 `as` 的目标，`yield` 之后是 `__exit__`。块内抛异常时，`__exit__` 用 `gen.throw()` 把异常抛回 `yield` 那一行，所以**必须用 `try/finally` 包住 `yield`**，否则清理代码不执行。
- 需要动态数量时用 `contextlib.ExitStack`，`enter_context` 注册，退出时逆序回调。

```python
import time
from contextlib import contextmanager

class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self                      # as 拿到的是 self
    def __exit__(self, exc_type, exc, tb):
        self.elapsed = time.perf_counter() - self.t0
        return False                     # 不吞异常

@contextmanager
def tx(conn):
    conn.begin()
    try:
        yield conn                       # as 拿到 conn
    except Exception:
        conn.rollback()
        raise                            # 决定不吞，继续抛
    else:
        conn.commit()
```

**最小例子**：

```python
with Timer() as t:
    sum(range(1000))
print(t.elapsed > 0)          # True，__exit__ 已执行

class Swallow:
    def __enter__(self): return self
    def __exit__(self, *exc): return True

with Swallow():
    raise ValueError("boom")  # 不会向外抛，因为 __exit__ 返回 True
print("continued")            # 会执行

with open("a.txt") as f:      # 块内异常也保证 close
    raise RuntimeError
```

**面试高频问法**：

1. **「with 等价于什么，`__exit__` 一定会执行吗？」** → 考点是协议的展开形式。答法：等价于 `m = expr; x = m.__enter__()` 加 `try: ... finally: m.__exit__(...)`；只要 `__enter__` 成功返回，`__exit__` 在异常、`return`、`break` 下都会执行——但如果 `__enter__` 自己抛异常，`__exit__` 不会被调用。
2. **「`__exit__` 返回 True 会发生什么？」** → 考点是异常抑制语义。答法：块内异常被吞掉，控制流从 `with` 之后继续；只应在确实处理了异常时返回真值，清理型管理器返回假值以免掩盖 bug。
3. **「`@contextmanager` 内部怎么实现的，异常怎么进去的？」** → 考点是生成器协议。答法：装饰器把生成器函数包成一个实现了 `__enter__/__exit__` 的类，`__enter__` 调 `next(gen)` 跑到 `yield`，`__exit__` 正常时 `next(gen)`、异常时 `gen.throw(exc)`；因此清理必须写在 `try/finally` 里，且 `yield` 只能出现一次。
4. **「多个 with 的退出顺序，怎么管理不确定数量的资源？」** → 考点是嵌套与栈式释放。答法：进入顺序从左到右、退出逆序；数量动态时用 `ExitStack`，`enter_context` 注册的回调在 `with` 结束时逆序执行。
5. **「with 能替代 try/except 吗？」** → 考点是职责区分。答法：不能。上下文管理器管的是「作用域边界的资源释放」，不是「就地处理某个异常」；它可以把异常信息拿到手做记录或回滚，但要不要吞异常是显式设计决策。

## 第 6 章 GIL 与多线程

**要解决的问题**：解释 CPython 里 `threading` 到底能带来什么、不能带来什么。不解决的话，就会写出「多线程跑 CPU 密集任务以为能提速」，或者反过来「以为有 GIL 就不用加锁」——两个方向都错。

**机制**：

- GIL（Global Interpreter Lock）是 CPython 解释器进程内的一把互斥锁：线程必须持有它才能执行 Python 字节码、修改对象引用计数等解释器状态。结果是**同一进程内同一时刻只有一个线程在跑字节码**。
- 释放时机有三类：字节码之间的切换检查（间隔由 `sys.setswitchinterval()` 控制，默认值按版本而定）；阻塞式 I/O 与 `time.sleep` 期间主动释放；部分 C 扩展在长计算中主动释放（是否释放由该扩展决定）。
- 关键推论：切换只发生在字节码边界，所以**单条字节码**看起来原子，但一条 Python 语句通常编译成多条字节码。`n += 1` 是「读 → 加 → 写」三步，中间可能被切走，因此不是原子操作。
- 所以：I/O 密集型任务多线程有效（等待时让出 GIL，别的线程能跑）；CPU 密集型任务多线程不提速，还会因切换与锁竞争变慢，应该用多进程或把计算下沉到会释放 GIL 的 C 实现。
- GIL 不等于你的数据结构的锁：它保护的是解释器内部状态，不保护「检查再修改」这种复合逻辑，共享可变状态仍然要 `threading.Lock`。
- 无 GIL 的 free-threaded 构建（PEP 703）在部分版本作为**可选构建**存在，默认构建仍带 GIL；具体可用状态按版本而定。

```python
import sys, threading
sys.setswitchinterval(1e-6)          # 把切换间隔调小，放大竞态

n = 0
def work():
    global n
    for _ in range(200_000):
        n += 1                        # LOAD / ADD / STORE，可被打断

ts = [threading.Thread(target=work) for _ in range(4)]
for t in ts: t.start()
for t in ts: t.join()
print(n)                              # 常小于 800000，具体值每次不同

lock = threading.Lock()
def safe():
    global n
    for _ in range(200_000):
        with lock:
            n += 1
```

**最小例子**：

```python
# CPU 密集：多线程 vs 串行，耗时往往相近甚至更慢
def burn(k):
    x = 0
    for i in range(k): x += i * i
    return x

# I/O 密集：多线程明显快于串行
import time
from concurrent.futures import ThreadPoolExecutor

def fetch(_):
    time.sleep(0.1)                   # 睡眠期间释放 GIL
    return 1

t0 = time.perf_counter()
list(ThreadPoolExecutor(8).map(fetch, range(16)))   # 约 0.2s 量级
print(time.perf_counter() - t0)
```

用 `dis.dis(work)` 能直接看到 `n += 1` 对应的多条字节码，这是解释「为什么不原子」最直接的证据。

**面试高频问法**：

1. **「GIL 是什么，为什么 CPython 要有它？」** → 考点是设计动机。答法：解释器级互斥锁，保证同一时刻只有一个线程执行字节码；主要目的是用最简单的方式保护引用计数等解释器状态、避免细粒度加锁带来的复杂度和开销，也让单线程性能受益。
2. **「有 GIL 了，为什么还要自己加锁？」** → 考点是保护粒度。答法：GIL 只在字节码边界切换，不保证多条字节码组成的复合操作原子；`n += 1`、先查后改的字典逻辑都可能交错，共享可变状态必须用 `Lock` 保护。
3. **「多线程什么时候有用，什么时候该换多进程？」** → 考点是任务类型判断。答法：I/O 密集、会阻塞等待的任务用线程（等待时释放 GIL，并发度高、开销小）；CPU 密集用多进程绕开 GIL，或用释放 GIL 的 C 扩展/向量化实现。
4. **「GIL 会不会被移除？」** → 考点是对 Python 演进的了解程度。答法：已有 PEP 703 的无 GIL 可选构建在推进，默认构建目前仍带 GIL；即使去掉 GIL，也不代表不用加锁——只是把并行能力放开，内存模型与锁语义仍要自己负责。
5. **「线程切换开不开、`setswitchinterval` 调小会怎样？」** → 考点是对调度开销的理解。答法：调小使切换更频繁，竞态更容易复现，但上下文切换开销上升、吞吐下降；切换间隔按版本有默认值，不应在生产里随手改。

## 第 7 章 多进程与并发选型

**要解决的问题**：GIL 让同一时刻只有一个线程执行字节码，纯 Python 的 CPU 密集任务无法靠多线程加速。多进程提供真正并行的执行单元；但进程模型带来了启动开销、序列化边界和共享状态难题，所以还需要一套「什么任务用什么并发模型」的选型判断。不解决这块，面试官一问「你这个爬虫为什么开 8 个线程而不是 8 个进程」就答不上来。

**机制**：

- 进程 = 独立解释器 + 独立地址空间 + 独立 GIL，因此是并行（parallel）而非并发（concurrent）。代价是启动要重新初始化解释器，内存不共享。
- 启动方式由 `multiprocessing.set_start_method()` 决定：`fork` 复制父进程内存（Linux 传统默认），`spawn` 起一个全新解释器只导入必要模块（Windows 默认，macOS 新版默认），`forkserver` 用一个干净的服务进程来 fork。`fork` 快但会继承父进程的锁、连接、线程状态，在多线程程序里 fork 是不安全的；`spawn` 干净但慢，且要求被调用的函数和参数可 pickle。
- 跨进程传参和返回值走序列化：`Queue` / `Pipe` 底层把对象 pickle 成字节流。所以 lambda、闭包、本地类实例、打开的文件句柄、数据库连接都传不过去。
- `spawn` 会重新导入主模块，所以建进程的代码必须放在 `if __name__ == "__main__":` 下，否则子进程导入时又建进程，无限递归。
- 共享状态三条路：`Value`/`Array`（共享内存 + 锁）、`Manager`（代理对象，每次读写都走 IPC，慢）、或者干脆不共享——让每个进程算完返回结果，由父进程聚合。工程上最后一种最常见。
- 池化：`ProcessPoolExecutor` / `multiprocessing.Pool` 复用已启动的进程，摊薄启动成本。

```python
from concurrent.futures import ProcessPoolExecutor

def work(n):                      # 必须是模块顶层函数，才能按限定名 pickle
    return sum(i * i for i in range(n))

if __name__ == "__main__":        # spawn 会重新导入主模块，缺这行会递归建进程
    with ProcessPoolExecutor(max_workers=4) as ex:
        print(list(ex.map(work, [10**6] * 4)))
```

**最小例子**：把上面 `work` 换成 `lambda n: n * 2` 扔进 `ex.map`，在 `spawn` 下会在把任务送进队列时抛 pickle 相关异常（`AttributeError: Can't pickle local object` 一类，具体类型按版本与对象而定）。这解释了「为什么进程池的函数必须定义在模块顶层」——序列化只传函数名和模块路径，子进程靠导入还原，闭包捕获的变量不在其中。而 `threading` 版同样代码能跑，因为线程共享地址空间，压根不需要序列化。

选型口径：CPU 密集 → 多进程；少量连接的高延迟 IO（数据库、内部 RPC）→ 多线程足够，代码心智负担小；上万并发连接、每连接大部分时间在等网络 → asyncio；混合负载用「进程池外套线程池/asyncio」两层结构，别在一个池里指望两头兼顾。

**面试高频问法**：

1. 「什么时候用多进程，什么时候用多线程？」→ 考点是 GIL 的边界在哪。→ 答法：「任务瓶颈在 CPU 就用多进程，因为 GIL 让线程拿不到并行；瓶颈在等 IO 就用多线程，因为等 IO 时线程会释放 GIL。判断标准是任务时间花在算还是花在等。」
2. 「多进程为什么一定要写 `if __name__ == '__main__'`？」→ 考点是 spawn 的导入语义。→ 答法：「spawn 启动子进程时会重新导入主模块，模块顶层的建进程代码会被再执行一遍。加这个守卫让它在子进程里不执行，否则就是无限递归建进程。」
3. 「多进程之间怎么共享一个 dict？」→ 考点是序列化与共享内存的取舍。→ 答法：「普通 dict 不共享，传过去是 pickle 的副本。要么用 `Manager().dict()`，它是代理对象，每次读写走 IPC，慢；要么用 `Value`/`Array` 这类共享内存加锁；实践里更常见的是不共享，各进程算完把结果回传给父进程合并。」
4. 「fork 和 spawn 有什么区别，有什么坑？」→ 考点是进程创建语义。→ 答法：「fork 复制父进程当前内存，快，但会继承锁和连接状态，父进程里若有多线程，子进程可能死锁；spawn 起全新解释器，干净但慢且要求可 pickle。Linux 传统默认 fork，Windows 和 macOS 新版默认 spawn，所以跨平台代码要假设 spawn 来写。」
5. 「进程池开多少个进程合适？」→ 考点是有没有工程感。→ 答法：「CPU 密集按 `os.cpu_count()` 量级取，略大于核数意义不大；进程有独立内存和启动成本，不是越多越好，还要看单进程内存占用和下游连接数限制。」

## 第 8 章 asyncio 与事件循环

**要解决的问题**：面对上万条同时存在、但每条大部分时间在等网络的长连接，线程模型的内存占用和上下文切换成本撑不住。asyncio 用「单线程 + 协作式调度」把「等」这件事从线程转移到一个数据结构上，代价是任何一处阻塞调用都会拖死全部并发。

**机制**：

- 事件循环是三个东西的组合：一个就绪回调队列（`call_soon` 入队）、一个定时器堆（`call_later`/`sleep`）、一个 IO 多路复用器（`selectors`，Linux 上是 epoll，BSD/macOS 是 kqueue，Windows 是 IOCP，按实现而定）。
- 一轮循环：算出最近的定时器超时 → `selector.select(timeout)` 阻塞到有 fd 就绪或超时 → 把就绪 fd 对应的回调塞进就绪队列 → 依次执行就绪回调 → 处理到期的定时器 → 下一轮。整个过程单线程，没有抢占，只有「你主动让出」。
- 协程函数调用后返回的是协程对象，本身不执行。`await` 是让出点：它把「我还需要什么」告诉循环，然后 return 回调度器。可等待对象靠 `__await__` 协议（本质是生成器协议）暴露自己的挂起点。
- `Task` 是协程的驱动器：把协程包起来，用 `call_soon` 把它推上就绪队列；协程 yield 出 `Future` 就挂起，`Future.set_result()` 时把 Task 的唤醒回调重新入队。所以 `Future` 就是「结果的占位符 + 回调挂载点」。
- 取消不是杀线程，是把 `CancelledError` 抛进协程当前的 `await` 点，所以清理逻辑要写在 `finally` 里。
- 组合原语：`create_task` 单飞、`gather` 批量等待（默认第一个异常向上抛，但其余任务继续跑）、`TaskGroup`（3.11+）结构化并发（任一子任务失败会取消兄弟任务）、`asyncio.Queue` 做生产者消费者。
- 阻塞的库（`time.sleep`、`requests`、同步数据库驱动）必须用 `loop.run_in_executor()` 或 `asyncio.to_thread()`（3.9+）挪到线程池，否则整个循环停摆。

```python
import asyncio, time

async def fetch(i):
    await asyncio.sleep(1)      # 只注册定时器并让出控制权，不占线程
    return i

async def main():
    t = time.perf_counter()
    print(await asyncio.gather(*(fetch(i) for i in range(3))))
    print(time.perf_counter() - t)   # 接近 1s，不是 3s

asyncio.run(main())             # 建循环、跑、收尾关循环
```

**最小例子**：上例三个任务各等 1s，总墙钟接近 1s，因为它们挂起的是同一个线程里的三个定时器。把 `asyncio.sleep(1)` 换成 `time.sleep(1)`，结果变成约 3s——而且如果是被 `gather` 并发的三个 Task，第一个 `time.sleep` 期间另外两个连启动的机会都没有，因为它们排队等着同一根线程。这一行替换就是「异步代码为什么会被一个同步库毁掉」的全部。

**面试高频问法**：

1. 「asyncio 是并发还是并行？」→ 考点是协作式调度的定位。→ 答法：「是并发不是并行，只有一个线程在跑，同一时刻只有一段代码执行。它的价值是在单线程里容纳大量同时挂起的 IO 等待，靠的是把等待交给 selector，而不是靠多核。」
2. 「协程里调了 `requests.get` 会怎样？」→ 考点是阻塞调用的传染性。→ 答法：「整个事件循环卡住，所有其他任务、包括定时器全部停摆，因为循环本身在等这个函数返回，回不到 `select` 那一层。要换成异步客户端，或者用 `asyncio.to_thread` / `run_in_executor` 丢到线程池里。」
3. 「`create_task`、`gather`、`TaskGroup` 有什么区别？」→ 考点是任务生命周期与异常语义。→ 答法：「`create_task` 是立刻把协程排进循环，你得自己保存引用防止被 GC，也要自己 await 拿异常；`gather` 是批量等待，默认第一个异常向上抛但其他任务不会停；`TaskGroup` 是结构化并发，一个子任务失败会把兄弟任务全部取消，退出时保证所有子任务都已结束。」
4. 「事件循环底层怎么做到一个线程等几千个 fd？」→ 考点是有没有看过实现。→ 答法：「就是 IO 多路复用，Linux 下 epoll。循环把关心的 fd 注册进去，调 `select(timeout)` 阻塞，有事件就返回就绪列表，然后逐个执行回调把对应 Future 设结果，唤醒挂着它的 Task。没事件就按最近的定时器超时醒来处理定时任务。」
5. 「`await` 一个对象，Python 内部做了什么？」→ 考点是 `__await__` 协议。→ 答法：「`await` 要求对象实现 `__await__`，它返回一个迭代器。Task 驱动这个迭代器往前走，遇到 yield 出来的 Future 就挂起自己，并把唤醒回调挂到那个 Future 上；Future 完成时回调入队，Task 被重新推进，把结果 send 回协程，协程从 `await` 处继续。」

## 第 9 章 内存管理与垃圾回收

**要解决的问题**：对象什么时候被释放、循环引用由谁收拾、为什么进程内存降不下来——这三个问题决定了你能否在真实项目里诊断“内存泄漏”，也是 CPython 实现细节最常被追问的一块。

**机制**

CPython 的内存管理是三层配合：

1. **引用计数为主**。每个对象头有 `ob_refcnt`，`Py_INCREF`/`Py_DECREF` 成对增减；减到 0 立即调用类型的 `tp_dealloc` 释放。好处是即时、可预测——`with` 块退出就关文件，靠的就是这个；代价是每次赋值一次计数写、并且天然处理不了环。
2. **分代循环 GC 为辅**。只有“可能装别的对象”的容器类型带 `Py_TPFLAGS_HAVE_GC`，它们被串进按代划分的双向链表（`gc.get_objects()` 能看到的就是这些）。默认阈值 `(700, 10, 10)`：第 0 代净增 700 个容器触发一次，活下来的晋升到第 1 代，以此类推，越老扫描越少。判定算法是标记-清除的变体：
   - 对每个候选对象算 `gc_refs = ob_refcnt - 被候选集内部引用的次数`；
   - `gc_refs > 0` 的是有外部引用的根，从根出发能走到的全部标记为存活；
   - 剩下没被标记的就是不可达环，先跑 finalizer 再释放。
3. **pymalloc 小对象分配器**。请求 ≤512 字节走 size class（16 字节对齐）→ pool（约 4 KiB）→ arena（256 KiB）；更大的直接交给系统 `malloc`。释放的小对象块回收到 pool 的空闲链表，arena 只要还有一个块在用就不还给 OS。**这是“内存泄漏”误判的头号来源**：对象早被回收了，RSS 却不降。

关键工具：`sys.getrefcount`（返回的是真实计数 +1，因为传参本身临时加了一次）、`gc.get_objects()` / `gc.garbage` / `gc.set_debug`、`weakref`、`tracemalloc`（按分配点做快照 diff，定位泄漏最有效）。

**最小例子**

```python
import gc, sys, weakref

class Node:
    def __init__(self, name):
        self.name = name
        self.peer = None

a, b = Node("a"), Node("b")
a.peer, b.peer = b, a
w = weakref.ref(a)

print(sys.getrefcount(a))   # 3: 全局 a、b.peer、getrefcount 的临时参数
del a, b
print(w() is None)          # False: 环没有被引用计数解开
n = gc.collect()            # 返回 >= 2，两个 Node 都在其中
print(n >= 2, w() is None)  # True True
```

一次具体执行：删掉 `a`、`b` 后两个对象互相持有，计数各为 1，谁也到不了 0；只有 `gc.collect()` 把它们判为不可达环才真正释放，弱引用随之变成 `None`。注意弱引用不增加计数，所以它是观察“到底有没有被回收”的正确手段，而 `obj in gc.get_objects()` 之类的判断会被你自己的临时引用干扰。

**面试高频问法**

1. **“Python 的内存管理是怎么做的？”**
   → 考点：是否知道这是三层而不是一句话。答法：“以引用计数为主做即时回收，用分代循环 GC 兜住循环引用，底层用 pymalloc 管 512 字节以下的小对象，按 size class/pool/arena 分层。”
2. **“都有引用计数了，为什么还要垃圾回收？”**
   → 考点：引用计数的根本缺陷。答法：“引用计数解不开环——互相引用的对象计数永远不归零；另外它每次赋值都有开销，环只能靠周期性扫描容器对象来兜。”
3. **“循环 GC 怎么判断一组对象已经死了？”**
   → 考点：是不是只会背“标记清除”四个字。答法：“先把每个对象的引用计数减去来自候选集内部的引用，剩下的就是外部引用；有外部引用的当根做可达性标记，标记不到的才回收。”
4. **“`__del__` 什么时候调用？能拿它释放资源吗？”**
   → 考点：finalizer 语义。答法：“引用计数归零或循环 GC 判定不可达时调用；解释器退出时不保证调用，所以不能拿它关文件或连接——用 `with`、`try/finally` 或 `weakref.finalize`。”
5. **“线上内存一直涨，怎么查？”**
   → 考点：区分真泄漏和分配器行为。答法：“先用 tracemalloc 取两个时间点的快照做 diff，看增长集中在哪个分配点；再排查缓存、全局注册表、闭包和异常 traceback 持有的帧；如果对象数稳定但 RSS 不降，那是 arena 没归还，不算泄漏。”

## 第 10 章 类型标注、打包与工程化

**要解决的问题**：让代码能被静态检查、能被别人 `pip install`、能在一个团队里稳定跑起来——面试里问“你怎么保证代码质量”，答案要落在这三件具体的事上，而不是“我写单元测试”。

**机制**

**标注本质是运行时可求值的表达式，默认不做任何校验。** 函数注解存在 `__annotations__` 里（类、模块同理），局部变量注解只在编译期记录、不进 `__annotations__`。所以 `def f(x: int) -> int` 传字符串照样跑，除非某个框架主动解析（`typing.get_type_hints` 会解析字符串前向引用）或做校验（pydantic 那一类）。

工程上常用的几块：

- 泛型容器：`list[int]`、`dict[str, int]` 从 3.9 起内置可用，之前要 `typing.List`；
- 联合类型：`X | Y` 是 3.10 起（PEP 604），等价 `Union[X, Y]`，且 `isinstance(v, int | str)` 可用；
- `from __future__ import annotations`（PEP 563）让所有注解变成字符串、不求值——既省导入也天然支持前向引用，副作用是运行时拿不到真类型，得快照式解析；较新版本已转向默认延迟求值（PEP 649），具体版本按实现而定；
- `Protocol` 做结构化子类型：不要求继承，只要方法签名匹配就算符合，是“给鸭子类型加上可检查的接口”；
- `TypedDict` 标注字典字面量、`Literal` 收窄取值、`Annotated` 挂元数据、`@overload` 表达重载。

**打包**：`pyproject.toml`（PEP 621 的 `[project]` 表）+ 构建后端（PEP 517）。`python -m build` 产出两种东西：**sdist** 是源码包，装的时候要在目标机上跑构建后端；**wheel** 是预构建产物，装得快、不需要编译器。所以“为什么 CI 里要产 wheel”是有标准答案的。

**工程化**：venv 做隔离、锁文件钉版本、ruff 一把抓 lint + format、mypy/pyright 做类型检查、pytest + coverage、pre-commit 把前几件事挂到提交钩子、CI 跑多版本矩阵。包布局优先 `src/` 而不是把包名目录摆在仓库根，避免“测试时导入的是工作目录而不是装好的包”。

**最小例子**

```python
from typing import Protocol

class Reader(Protocol):
    def read(self, n: int = -1) -> bytes: ...

def head(r: Reader, n: int = 8) -> bytes:
    return r.read(n)

head(open("data.bin", "rb"))   # 通过：文件对象结构上满足 Reader
head("not a reader")           # mypy 报错；运行时直接 AttributeError
```

一次具体执行：`open(..., "rb")` 返回的对象没有继承 `Reader`，但因为 `read` 签名匹配，静态检查放行；第二个调用说明标注**在运行时完全不设防**，错误发生在 `r.read` 属性查找那一刻。

配套的 `pyproject.toml`：

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mypkg"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest", "mypy", "ruff"]

[project.scripts]
mypkg = "mypkg.cli:main"
```

`[project.scripts]` 就是 console script 的入口声明，安装后生成同名命令，指向 `mypkg/cli.py` 的 `main`。

**面试高频问法**

1. **“类型标注在运行时生效吗？”**
   → 考点：是否清楚“标注 ≠ 校验”。答法：“不生效，注解只是存在 `__annotations__` 里的对象或字符串，除非有人显式调 `get_type_hints` 解析、或框架做运行时校验，否则传错类型该跑还是跑。”
2. **“`list[int]` 和 `List[int]`、`X | Y` 和 `Union[X, Y]` 什么区别？”**
   → 考点：版本演进。答法：“语义一样，前者是 3.9 起的内置泛型和 3.10 起的联合语法，后者是 `typing` 里的老写法；老版本要靠 `from __future__ import annotations` 才能在不求值的前提下写新语法。”
3. **“Protocol 和 ABC 怎么选？”**
   → 考点：名义 vs 结构化子类型。答法：“ABC 要求显式继承、是名义子类型；Protocol 只看方法签名，不需要改被适配的类，适合给第三方类型或测试替身定义接口。”
4. **“wheel 和 sdist 的区别？为什么装 wheel 快？”**
   → 考点：是否真打过包。答法：“sdist 是源码包，安装时要在本机跑构建后端、可能要编译扩展；wheel 是预构建产物，解压即装，所以 CI 里应该两种都产、优先分发 wheel。”
5. **“新项目你怎么把工程化搭起来？”**
   → 考点：能不能给出可执行的清单。答法：“`src/` 布局 + `pyproject.toml` 声明元数据和可选依赖，ruff 管 lint 和格式、mypy 管类型、pytest 管测试，pre-commit 挂上去，CI 跑多 Python 版本矩阵。”
