# linux-api · 分章详细

## 第 1 章 文件 IO 与文件描述符语义

**要解决的问题**：给所有 IO 对象（普通文件、管道、终端、socket、设备）一个统一的、进程私有的句柄——非负整数 fd，并把「偏移量、打开标志、权限」这些状态放在内核里，让 `read/write/lseek/close` 五个系统调用就能覆盖全部对象。没有这层抽象，每种对象都要一套 API，后面的管道、socket、多路复用全部无从谈起。

**机制**：内核里是三张表。

- **进程 fd 表**：`fd` 就是这个数组的下标。表项里存两样东西——指向 open file description 的指针，以及**fd 标志**（目前实际只有一个：`FD_CLOEXEC`）。fd 表是进程私有的，`fork` 复制一份。
- **open file description（打开文件描述）**：系统级对象，保存**文件偏移量 offset** 和**文件状态标志**（`O_APPEND`、`O_NONBLOCK`、`O_RDWR` 那套）。它有一个引用计数，被几个 fd 指向就计几。
- **inode**：真正的文件元数据与数据块，被所有打开同一文件的 description 共享。

判定语义只需问一句：**这两个 fd 是否指向同一个 description**。

| 操作 | 结果 |
|---|---|
| `open` 同一路径两次 | 两个 description，offset 独立 |
| `dup`/`dup2`/`fcntl(F_DUPFD)` | 同一 description，共享 offset 与状态标志 |
| `fork` | 子进程 fd 表复制，指向同一 description，共享 offset |

两个易混点：

1. **fd 标志 vs 状态标志**：`fcntl(fd, F_GETFD/F_SETFD)` 操作的是 fd 表项里的 `FD_CLOEXEC`（决定 `exec` 时是否关闭）；`fcntl(fd, F_GETFL/F_SETFL)` 操作的是 description 里的状态标志。后者能被 dup/fork 后的所有 fd 看到，前者不能。
2. **原子性**：`O_APPEND` 的「移动到末尾 + 写入」由内核作为一步完成，多进程追加日志不会互相覆盖。而 `lseek(fd,0,SEEK_END)` 后再 `write` 是两步，中间可被抢占。所以「两个进程各自 `open(O_APPEND)`」已经是安全的，不需要共享 description。

读写语义：`read` 返回 0 表示 EOF，返回小于请求长度是**合法的短读**（终端、管道、socket 常见），返回 -1 且 `errno == EINTR` 表示被信号打断、可重试。`write` 同样可能部分写，正确写法是循环：

```c
ssize_t write_all(int fd, const char *p, size_t n) {
    size_t off = 0;
    while (off < n) {
        ssize_t w = write(fd, p + off, n - off);
        if (w < 0) { if (errno == EINTR) continue; return -1; }
        off += (size_t)w;
    }
    return (ssize_t)off;
}
```

`lseek` 对管道、socket、终端返回 -1 且 `errno == ESPIPE`。持久化语义另有开关：`O_SYNC` 每次 `write` 等到数据与元数据落盘，`fsync(fd)` / `fdatasync(fd)` 手动刷，二者只保证「到设备」，不保证设备内部缓存。

**最小例子**：验证 offset 归属。

```c
int fd = open("f", O_RDWR | O_CREAT | O_TRUNC, 0644);
write(fd, "hello", 5);          /* fd.offset = 5 */
int d = dup(fd);                /* 同一 description */
lseek(fd, 0, SEEK_SET);         /* fd.offset = 0，d 也是 0 */
char buf[8];
read(d, buf, 5);                /* 读到 "hello"，共享 offset 变成 5 */
/* 换 open("f", O_RDONLY) 则得到独立 offset=0 的 description */
```

若把上面改成 `fork` 后子进程 `read`，父进程的 offset 同样前进——这正是「父进程读了一半，子进程接着读后半段」现象的来源。

**面试高频问法**

- 问：fd 到底是什么？→ 考点是三层结构。→ 答：fd 是进程 fd 表的下标，表项指向系统级的打开文件描述，描述里有偏移量和状态标志，再往下才是 inode；所以 fd 只在进程内有意义，跨进程要传得靠 socket 传描述符或继承。
- 问：`dup` 和再 `open` 一次有什么区别？→ 考点是共享 offset。→ 答：`dup` 让两个 fd 指向同一个打开文件描述，共享偏移量和状态标志；再 `open` 一次得到独立描述，各自从 0 开始偏移。
- 问：`O_APPEND` 为什么能保证多进程写日志不串？→ 考点是原子性边界。→ 答：内核把「定位到末尾」和「写入」合成一个原子步骤，所以哪怕 offset 不共享也不会覆盖；但先 `lseek` 再 `write` 就没有这个保证。
- 问：`write` 返回小于请求长度算错误吗？→ 考点是短写。→ 答：不算，是正常情况，可能因为缓冲空间不足或被信号打断，必须循环写到全部完成；`read` 返回 0 才是 EOF。
- 问：`FD_CLOEXEC` 和 `O_NONBLOCK` 是一类东西吗？→ 考点是两级标志。→ 答：不是，`FD_CLOEXEC` 存在 fd 表项上、只影响本 fd 的 `exec` 行为；`O_NONBLOCK` 存在打开文件描述上，dup 和 fork 出来的 fd 都会继承。

## 第 2 章 标准 IO 与缓冲区

**要解决的问题**：把「每次读写都陷内核」的成本摊薄，同时让调用方不再手写 `write_all` 这种循环——用用户态缓冲区 + `FILE *` 把短读短写和格式化拼装都藏起来。不解决的话，逐字符处理文件会变成逐字符系统调用，`printf` 也无从实现。

**机制**：`FILE` 是不透明结构，内部至少持有：关联的 fd、用户态缓冲区指针与大小、当前读写位置、缓冲模式、错误标志与 EOF 标志、一把用于线程安全的锁。`fopen` 时按对象决定缓冲模式：

- `_IOFBF` 全缓冲：默认用于普通文件，缓冲区满或 `fflush` 才落到内核。缓冲区大小按实现而定，通常取块大小量级。
- `_IOLBF` 行缓冲：默认用于连到终端的流，遇到 `\n` 就刷。所以调试时 `printf("x\n")` 能看到，去掉 `\n` 就看不到。
- `_IONBF` 无缓冲：`stderr` 默认如此，保证错误信息即使程序崩溃也已输出。

可以在任何 IO 之前用 `setvbuf` 改，之后调用行为未定义。

刷新（flush）的触发点：缓冲区满、行缓冲遇换行、调用 `fflush`、`fclose`、`exit`（遍历所有流并 flush），以及 `main` 正常 return。注意 `abort` 和 `_exit` **不**刷新。

两个高频陷阱：

1. **`fflush` ≠ 落盘**：`fflush(fp)` 只是把用户态缓冲交给内核的 `write`；要抗掉电还得 `fsync(fileno(fp))`。层级是「用户缓冲 → 内核页缓存 → 磁盘」。
2. **`fork` 复制缓冲区**：子进程拿到父进程 `FILE` 缓冲区的**副本**，父子退出时各刷一次，重定向到文件时就能看到内容重复。正确做法是 `fork` 前 `fflush(NULL)`，子进程用 `_exit` 而不是 `exit`。

与裸 fd 混用：`FILE` 把位置缓存在自己那边，直接 `read/write` 同一个 fd 会让两者错位。要么 `fflush` 后 `lseek(fd, 0, SEEK_CUR)` 把内核位置同步回来，要么干脆不要混。

**最小例子**：经典的双份输出。

```c
int main(void) {
    printf("hello");        /* 无换行，重定向到文件 → 全缓冲，留在用户态 */
    if (fork() == 0) {
        /* 子进程复制了含 "hello" 的缓冲区 */
        _exit(0);           /* _exit 不 flush */
    }
    return 0;               /* 父进程 exit 时 flush 一次 */
}
```

`./a.out > out.txt` 后文件里是 `hello` 一份；若把 `_exit(0)` 改成 `exit(0)`，就是两份——两个进程各刷了一次同一个缓冲区副本。若输出到终端（行缓冲，遇 `\n` 已刷），则不会重复。

**面试高频问法**

- 问：`fflush` 和 `fsync` 差在哪？→ 考点是两层缓冲。→ 答：`fflush` 把用户态 `FILE` 缓冲区交给内核的 `write`，`fsync` 才是让内核把页缓存刷到设备；要保证掉电不丢必须两个都做，顺序是先 `fflush` 再 `fsync`。
- 问：为什么 `fork` 之后 printf 会输出两遍？→ 考点是缓冲区被复制。→ 答：`fork` 复制的是整个进程地址空间，包括 `FILE` 里的用户态缓冲；父子各自正常退出就各刷一次，用 `_exit` 或 `fork` 前 `fflush(NULL)` 可避免。
- 问：为什么 `printf` 不加换行在终端能看到、重定向到文件就看不到？→ 考点是缓冲模式选择。→ 答：连终端默认行缓冲，遇 `\n` 就刷；连普通文件默认全缓冲，要等缓冲区满或退出才刷。
- 问：`stderr` 为什么通常不缓冲？→ 考点是设计意图。→ 答：错误信息往往紧跟着崩溃，需要立即出现在终端上，所以默认 `_IONBF`，代价是每次调用一次系统调用。
- 问：`fread` 返回的字节数比请求少，能直接用吗？→ 考点是返回值与 EOF 判定。→ 答：能，返回的是实际读到的完整对象个数，短读可能来自 EOF 或错误，要再用 `feof` / `ferror` 区分；这和 `read` 的短读语义是同一件事。

## 第 3 章 文件、目录与链接

**要解决的问题**：在 fd 之外，还需要「不打开就查看」「按名字遍历命名空间」「让一个文件有多个名字」这三类能力，对应 `stat` 家族、目录流和链接机制。不解决的话，`ls`、`cp -r`、`find` 这类工具就写不出来，也解释不了「删了文件磁盘没空」。

**机制**：

**inode 存什么**：文件类型与权限位、uid/gid、大小、时间戳（访问/修改/状态变更）、链接计数 `st_nlink`、数据块索引。**不存文件名**——文件名在目录里。

**目录是什么**：一个特殊文件，内容是「名字 → inode 号」的映射表，只能通过 `opendir/readdir/closedir` 读，不能 `read`。

**stat 家族**：`stat` 跟符号链接（拿目标的信息），`lstat` 不跟（拿链接本身的信息），`fstat` 用已打开的 fd（避免 TOCTOU 竞态），`fstatat` 多一个「是否跟随」标志和目录 fd 参数。

**链接**：

- 硬链接 `link(old, new)`：在目录里加一条新名字指向**同一 inode**，`st_nlink` 加一。限制是不能跨文件系统、不能指向目录（防止成环）。
- 符号链接 `symlink(target, name)`：新建一个独立 inode，内容是 target 这个**路径字符串**，类型是 `S_IFLNK`。可以跨文件系统、可以指向目录、可以悬空。`readlink` 读内容（不加 `\0`）。

**删除的真实语义**：`unlink` 只做两件事——把目录项删掉、`st_nlink` 减一。inode 和数据块真正释放要满足 `st_nlink == 0` **且**没有进程还持有打开的 fd（内核引用计数为 0）。所以「删掉一个正在写的日志文件，`df` 不降」是正常现象，空间要等持有者 `close` 或退出才回收。

**目录链接计数的由来**：每个目录至少被自己里的 `.` 和父目录里的一条名字引用，所以 `st_nlink` 起点是 2，每多一个子目录（子目录里的 `..` 指回来）就加一。这是判断「有没有子目录」的老技巧。

**rename**：同一文件系统内是原子的，要么全成要么全不成，常用来做「写临时文件再改名」的原子替换。

**最小例子**：遍历并打印，同时演示 `lstat` 与悬空链接。

```c
DIR *d = opendir(".");
struct dirent *e;
struct stat st;
while ((e = readdir(d)) != NULL) {
    if (lstat(e->d_name, &st) < 0) continue;      /* 不跟随链接 */
    if (S_ISLNK(st.st_mode)) {
        char buf[256];
        ssize_t n = readlink(e->d_name, buf, sizeof buf - 1);
        if (n > 0) { buf[n] = '\0'; printf("%s -> %s\n", e->d_name, buf); }
    } else {
        printf("%s %lld\n", e->d_name, (long long)st.st_size);
    }
}
closedir(d);
```

对 `ln -s /nonexistent ghost` 建出的悬空链接：`lstat` 成功、`stat` 返回 `ENOENT`——这就是 `find -type l` 能列出它而 `-type f` 列不出的原因。

**面试高频问法**

- 问：硬链接和符号链接的本质区别？→ 考点是「名字还是内容」。→ 答：硬链接是同一 inode 的另一个目录项，地位完全对等，删掉任一个只是计数减一；符号链接是独立 inode，内容是路径字符串，解析时重新走一遍路径，所以能跨文件系统、能指向目录、也能悬空。
- 问：删除一个正在被写的日志文件，为什么磁盘空间没释放？→ 考点是 unlink 语义。→ 答：`unlink` 只删目录项并减 `st_nlink`，inode 要等链接计数为 0 且没有打开的 fd 才释放；进程还开着就一直占着，`close` 或进程退出后才回收。
- 问：`stat` 和 `lstat` 什么时候必须用后者？→ 考点是跟不跟链接。→ 答：要拿链接本身的信息（类型、大小、目标字符串）时用 `lstat`，比如实现 `ls -l` 或 `find -type l`；要拿目标的信息才用 `stat`。
- 问：目录的链接数为什么一般比子目录数多 2？→ 考点是 `.` 和 `..`。→ 答：目录自己被 `.` 引用一次、被父目录中的名字引用一次，共 2；每个子目录的 `..` 又指回来一次，所以是 2 加子目录数。
- 问：怎么做到配置文件原子更新？→ 考点是 `rename` 的原子性。→ 答：同目录下写临时文件、`fflush` + `fsync`、`close`，再 `rename` 覆盖目标；同文件系统内 `rename` 原子，读者要么看到旧内容要么看到新内容，不会看到半截。

## 第 4 章 进程环境与程序启动

**要解决的问题**：从 `execve` 把可执行文件加载进内存，到 `main` 第一行被执行，中间发生了什么；进程的地址空间长什么样；进程退出时缓冲区、`atexit` 注册函数、退出状态如何收尾。不解决这些，后面 `fork` 的缓冲区复制、`wait` 拿到的状态码含义、`_exit` 与 `exit` 的取舍全是模糊的。

**机制**：

内核在 `execve` 里按 ELF 头建立地址空间，把 `argv`/`envp` 字符串和指针数组铺到用户栈顶，然后跳到 ELF 入口（通常叫 `_start`，由 C 运行时提供）。`_start` 从栈上取 `argc`、`argv`，调用 `__libc_start_main`，后者做 libc 自身初始化，再调用 `main(argc, argv, envp)`，拿到返回值后转给 `exit()`。所以 **`main` 的返回等价于 `exit(返回值)`**，而不是返回到某个"调用者"。

存储布局自上而下：text（只读代码）、data（已初始化全局/静态）、bss（未初始化，内核清零）、堆（向高地址增长）、栈（向低地址增长），`argv`/`envp` 在栈顶之上。

环境表是 `extern char **environ`。`getenv` 只读查找；`setenv` 复制字符串并可触发 `environ` 重新分配，`putenv` 直接把传入的字符串挂进环境表（不复制，所以传栈上数组会变成悬垂指针）。注意 `setenv` 之后，之前 `getenv` 拿到的指针可能失效。

终止有两条路：`exit(status)` 先以 LIFO 顺序跑 `atexit` 注册的函数（POSIX 要求至少支持 32 个），再把所有 stdio 流 flush，最后调 `_exit`；`_exit`/`_Exit` 直接进内核，不跑任何用户态清理。退出状态只有低 8 位对父进程可见。

`setjmp`/`longjmp` 用于跨多层栈帧跳转，但跳回一个已经返回的栈帧是未定义行为；被 `longjmp` 修改后又使用的自动变量必须声明为 `volatile`。

资源限制用 `getrlimit`/`setrlimit`，软限制可调至硬限制，硬限制只能降（非特权）。

**最小例子**：

```c
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static void h1(void) { printf("h1\n"); }
static void h2(void) { printf("h2\n"); }

int main(void) {
    atexit(h1);
    atexit(h2);
    printf("no newline");   /* 无换行，缓冲区里 */
    if (getenv("USE__EXIT")) _exit(0);
    return 3;
}
```

正常运行：输出 `no newlineh2\nh1\n`，退出状态 3（`atexit` 逆序）。设 `USE__EXIT=1`：输出为空——缓冲区没被 flush，`atexit` 也没跑。

**面试高频问法**：

1. **问法**：`main` 是谁调用的？`return 0` 和 `exit(0)` 有区别吗？
   **考点**：启动例程的存在，`main` 不是入口。
   **一句话答法**：`main` 由 C 运行时的启动例程（`_start` → `__libc_start_main`）调用，`return` 和 `exit` 完全等价，都会跑 `atexit` 并 flush 缓冲区。

2. **问法**：`exit` 和 `_exit` 什么时候必须用后者？
   **考点**：`fork` 出来的子进程不应重复 flush 父进程的缓冲区。
   **一句话答法**：子进程里 `exit` 会把继承来的 stdio 缓冲区再刷一遍造成重复输出，所以在 `fork` 后、`exec` 失败的分支里应该用 `_exit`。

3. **问法**：`exit(300)`，父进程 `wait` 拿到什么？
   **考点**：状态码只有 8 位有效。
   **一句话答法**：拿不到 300，父进程看到的是 $300 \bmod 256 = 44$，而且要用 `WEXITSTATUS` 取。

4. **问法**：`putenv` 和 `setenv` 的坑？
   **考点**：所有权与指针失效。
   **一句话答法**：`putenv` 不复制字符串，传进来的内存必须长期有效；`setenv` 会复制，但可能重新分配 `environ`，之前保存的 `getenv` 指针不能再用。

---

## 第 5 章 fork / exec / wait 与进程控制

**要解决的问题**：如何创建新进程、在子进程里换掉程序映像、父进程如何回收子进程并解释它的退出状态。不解决：僵尸进程堆积、文件描述符意外泄漏给子进程、`fork` 与缓冲区的交互造成重复输出、`SIGCHLD` 漏收。

**机制**：

`fork` 复制父进程的地址空间（现代实现用写时复制，`fork` 本身不复制物理页）、文件描述符表、信号处理方式、当前工作目录、`umask` 等。不继承：进程 ID、父进程的未决信号与定时器、`fcntl` 记录锁。关键点：子进程的 fd 复制的只是描述符表项，父子指向**同一个 open file description**，因此共享文件偏移量和文件状态标志；`FD_CLOEXEC` 标记则在每个描述符上独立。

返回值三态：`0` 在子进程、子进程 PID 在父进程、`-1` 失败。`fork` 之前未 flush 的 stdio 缓冲区会被整份复制到子进程，父子各自 flush 一次——这是"输出两次"的根源。

`vfork` 让子进程共享父进程地址空间并阻塞父进程，只适合"立刻 `exec`"的场景；现在更推荐 `posix_spawn`。

`exec` 家族只有一个系统调用 `execve(path, argv, envp)`，其余都是库函数包装：`l` 是变长参数列表，`v` 是 `char *const argv[]`，`p` 用 `PATH` 搜索，`e` 显式传环境表。成功后不返回；失败返回 `-1` 并设置 `errno`。保留的东西：PID、父进程、进程组、会话、打开的文件描述符（标了 `FD_CLOEXEC` 的除外）、`umask`；被重置的：所有信号处理函数变回默认（`SIG_IGN` 保持忽略）。

回收用 `wait(&st)` / `waitpid(pid, &st, options)`。状态要用宏解：`WIFEXITED`+`WEXITSTATUS`、`WIFSIGNALED`+`WTERMSIG`、`WIFSTOPPED`+`WSTOPSIG`。子进程退出但父进程还没回收时是僵尸（只留一个 task 结构）；父进程先死，子进程被 init 或 subreaper 收养，成为孤儿，不再是僵尸。

`system(cmd)` 内部是 `fork` + `exec` `/bin/sh -c cmd`，执行期间忽略 `SIGINT`/`SIGQUIT` 并屏蔽 `SIGCHLD`，返回 shell 的终止状态，需要自己 `WEXITSTATUS` 解读；返回 127 通常表示 shell 找不到命令。

以 `#!` 开头的脚本由内核识别，实际 `execve` 的参数会变成 `[解释器, 脚本路径, 原有 argv[1..]]`。

**最小例子**：

```c
#include <stdio.h>
#include <unistd.h>
#include <sys/wait.h>

int main(void) {
    printf("before");                 /* 无换行，留在缓冲区 */
    pid_t p = fork();
    if (p == 0) {
        execlp("echo", "echo", "hi", (char *)0);
        _exit(127);                   /* exec 失败才到这里 */
    }
    int st;
    waitpid(p, &st, 0);
    printf(" status=%d\n", WEXITSTATUS(st));
    return 0;
}
```

若 stdout 是终端（行缓冲），输出 `beforehi\n status=0`；若重定向到文件（全缓冲），`before` 被复制两份，`before` 会出现在子进程 `execve` 前被刷新一次的位置——这正是"为什么子进程要用 `_exit`"的现场。

**面试高频问法**：

1. **问法**：`fork` 之后父子进程共享什么？
   **考点**：地址空间 COW 与文件描述符表两个层面要分开答。
   **一句话答法**：内存是写时复制、写时各自独立；文件描述符表是复制的，但表项指向同一个 open file description，所以共享文件偏移量和状态标志。

2. **问法**：为什么 `fork` 之后 `printf` 的内容出现了两次？
   **考点**：缓冲区被复制，父子各 flush 一次。
   **一句话答法**：`fork` 复制了整个用户态缓冲区，`fork` 前没 flush 的数据在父子进程里各有一份，各自退出时各写一次；`fork` 前 `fflush` 或子进程用 `_exit` 可以避免。

3. **问法**：`exec` 之后哪些东西还留着？
   **考点**：区分"进程属性保留"和"程序映像重置"。
   **一句话答法**：PID、父进程、进程组、会话、工作目录、`umask`、已打开且没标 `FD_CLOEXEC` 的 fd 都保留，信号处理函数被重置为默认（`SIG_IGN` 例外）。

4. **问法**：僵尸进程怎么来的，怎么防？
   **考点**：回收责任在父进程，`SIGCHLD` 不排队。
   **一句话答法**：子进程退出后父进程没 `wait` 就会留僵尸；父进程应装 `SIGCHLD` 处理函数并在里面用 `while (waitpid(-1, &st, WNOHANG) > 0)` 循环回收，不能只 `wait` 一次。

5. **问法**：`system()` 的返回值怎么解释？
   **考点**：它返回的是 shell 的状态，不是命令的直接状态。
   **一句话答法**：要用 `WIFEXITED`/`WEXITSTATUS` 解，且 127 表示 shell 层面没找到命令，不能和命令自身返回 127 区分开。

---

## 第 6 章 信号

**要解决的问题**：进程如何被异步事件打断并做出反应，以及如何在不引入竞态的前提下等待信号。不解决：`EINTR` 处理、信号处理函数里的可重入问题、`pause` 的经典竞态、`SIGCHLD` 漏收。

**机制**：

信号的生命周期是：产生（内核、`kill`、终端、硬件异常）→ 挂到目标进程的 pending 集合 → 若被 block 就等着，否则递送（执行处理函数、忽略、或默认动作）。每个进程有两张位图：pending 和 blocked，用 `sigset_t` 表示。**标准信号不排队**：同一信号在未决期间再来多次，只记一次；实时信号才排队并带值。

注册接口有 `signal` 和 `sigaction`。`signal` 在不同历史实现里语义不一致（SysV 会重置 handler、慢系统调用不重启），`sigaction` 则全部显式可控：`sa_handler`/`sa_sigaction`、`sa_mask`（处理函数执行期间额外屏蔽的信号，原 mask 自动加入）、`sa_flags`（`SA_RESTART` 让被中断的慢系统调用自动重启、`SA_SIGINFO` 启用三参数版本、`SA_RESETHAND`、`SA_NODEFER`）。

屏蔽与等待：`sigprocmask(SIG_BLOCK/SIG_UNBLOCK/SIG_SETMASK, &set, &old)` 改屏蔽字，`sigpending` 查未决集合。`sigsuspend(&mask)` 原子地"换上这个屏蔽字并挂起进程"，是消除 `pause` 竞态的标准手段——`pause` 的问题在于"检查条件"和"进入睡眠"之间有窗口，信号若落在这个窗口里就永远等不到。

发送：`kill(pid, sig)`、`raise(sig)`、`alarm(n)`、`setitimer`。

可重入性：信号处理函数可能在任意指令处插入执行，因此只能调用 async-signal-safe 的函数（`write`、`_exit`、`sigaction`、`kill` 等），`printf`、`malloc` 都不在列表里。处理函数入口应保存并恢复 `errno`，否则会破坏主流程的 `errno`。

慢系统调用（`read` 在管道/终端上、`accept`、`wait` 等）被信号中断时返回 `-1` 且 `errno == EINTR`，除非设了 `SA_RESTART`。是否自动重启按实现和调用而定，稳妥写法是显式循环判断 `EINTR`。

**最小例子**（消除 `pause` 竞态）：

```c
#include <signal.h>
#include <unistd.h>

static volatile sig_atomic_t got = 0;
static void on_int(int s) { (void)s; got = 1; }

int main(void) {
    struct sigaction sa = {0};
    sa.sa_handler = on_int;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, NULL);

    sigset_t blk, old;
    sigemptyset(&blk);
    sigaddset(&blk, SIGINT);
    sigprocmask(SIG_BLOCK, &blk, &old);   /* 先屏蔽 */

    while (!got)
        sigsuspend(&old);                 /* 原子地解除屏蔽并睡眠 */

    sigprocmask(SIG_SETMASK, &old, NULL);
    return 0;
}
```

发一次 `SIGINT`，进程被唤醒退出；无论信号落在 `while` 判断之前还是 `sigsuspend` 内部，都不会丢。

**面试高频问法**：

1. **问法**：信号处理函数里能做什么、不能做什么？
   **考点**：异步插入导致的可重入问题。
   **一句话答法**：只能调 async-signal-safe 的函数，`write`、`_exit`、`sigaction` 可以，`printf`、`malloc`、`free` 不行；入口要保存恢复 `errno`。

2. **问法**：`pause` 有什么问题，`sigsuspend` 怎么解决？
   **考点**：检查条件与睡眠之间的竞态窗口。
   **一句话答法**：`pause` 是"先检查再睡"，信号落在这个窗口里就丢失导致永久阻塞；`sigsuspend` 把"换屏蔽字"和"挂起"做成一个原子操作，先屏蔽信号再检查条件就没有窗口。

3. **问法**：为什么 `read` 有时返回 `-1` 且 `errno == EINTR`？
   **考点**：慢系统调用被信号中断，以及 `SA_RESTART`。
   **一句话答法**：信号处理函数返回后内核不自动重启某些被中断的慢系统调用；可以给 `sigaction` 加 `SA_RESTART`，或者在代码里判断 `EINTR` 后重试。

4. **问法**：多个子进程同时退出，`SIGCHLD` 会收到几次？
   **考点**：标准信号不排队。
   **一句话答法**：可能只收到一次，未决期间重复产生会被合并；所以处理函数里必须用 `while (waitpid(-1, &st, WNOHANG) > 0)` 循环回收直到没有子进程可收。

5. **问法**：`signal` 和 `sigaction` 该用哪个？
   **考点**：历史语义差异与可控性。
   **一句话答法**：用 `sigaction`，它能明确控制 `sa_mask`、是否重启系统调用、是否带 `siginfo`，而 `signal` 的行为在不同 Unix 上不一致。

## 第 7 章 线程与同步原语

**要解决的问题**：把并发单位从进程缩小到线程——同一地址空间、共享文件描述符表，创建开销远小于 `fork`。代价是共享可变状态天然存在数据竞争；不解决，同一个变量上会出现丢失更新，条件等待中会出现丢失唤醒，锁的获取顺序不一致时会出现死锁。

**机制**

线程生命周期接口是 `pthread_create` / `pthread_join` / `pthread_detach` / `pthread_exit`。`pthread_t` 是**不透明类型**，不能像整数一样打印或直接 `==` 比较，必须用 `pthread_equal`；要拿系统级 tid 得靠 `gettid`（Linux）。未 detach 也未 join 的线程结束后，其栈和 TCB 仍被保留，这就是线程泄漏。线程栈大小用 `pthread_attr_setstacksize` 设定；默认值按实现而定，Linux glibc 上通常与进程栈上限一致，所以几百个线程就会吃掉大量虚拟地址空间。

互斥量 `pthread_mutex_t` 的关键在于：无竞争时完全在用户态用原子指令完成加解锁，只有在发生竞争时才用 futex 进入内核挂起，因此临界区极短时开销很低。属性通过 `pthread_mutexattr_settype` 设置，可取 `PTHREAD_MUTEX_NORMAL`（默认）/ `RECURSIVE` / `ERRORCHECK`；`NORMAL` 在同一线程重复加锁的行为是未定义的，需要可重入就必须显式设 `RECURSIVE`。

条件变量的全部要点集中在这段：

```c
pthread_mutex_lock(&m);
while (!ready)                  /* 必须 while，不能 if */
    pthread_cond_wait(&cv, &m); /* 原子地：解锁 + 睡眠；被唤醒返回时重新加锁 */
consume();
pthread_mutex_unlock(&m);
```

`pthread_cond_wait` 必须绑定一个互斥量，原因是「检查谓词」和「进入睡眠」这两步必须相对于通知方是原子的；否则 `signal` 可能恰好落在两者之间，通知方发现没有等待者就直接返回，等待方随后永远睡下去——这就是丢失唤醒。`while` 而非 `if` 覆盖两种情形：虚假唤醒（POSIX 允许），以及被唤醒后重新拿到锁之前谓词又被别的线程改掉。对应的发信号侧也要先持锁改谓词再 `pthread_cond_signal` / `broadcast`，`broadcast` 用于多个等待者等同一谓词（如「队列非空」有多个消费者）。

其余原语按场景选择：`pthread_rwlock_t` 读多写少；`pthread_spinlock_t` 临界区只有几条指令且不允许睡眠；`pthread_barrier_t` 做多阶段并行同步；一次性初始化用 `pthread_once`；线程私有数据用 `pthread_key_create` 一族（`__thread` 更轻但语义不同）。

与进程模型的交叉点常被考：`fork` 之后子进程**只有调用 fork 的那个线程**，其它线程在子进程中消失，但它们持有的锁状态被原样复制——子进程若在 `exec` 之前碰这些锁就可能永久死锁。所以 `fork` 后到 `exec` 之间只允许调用 async-signal-safe 函数，`pthread_atfork` 用于在 fork 前后加锁/解锁以缓解。信号方面，`kill` 发给整个进程，内核从**未阻塞该信号**的线程中任选一个递送；要定向递送用 `pthread_kill`。取消默认是 deferred 模式，只在取消点（`read`、`write`、`accept`、`pthread_cond_wait`、`nanosleep` 等）生效，被取消线程用 `pthread_cleanup_push/pop` 释放锁和内存。

**最小例子**

两个线程各对同一全局变量执行 100 万次自增，分别加锁与不加锁：

```c
static pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
static long counter = 0;
static void *worker(void *arg) {
    for (int i = 0; i < 1000000; i++) {
        pthread_mutex_lock(&m);
        counter++;                 /* 非原子：load → add → store */
        pthread_mutex_unlock(&m);
    }
    return NULL;
}
```

`pthread_create` 两次再 `pthread_join` 两次，`counter` 精确等于 `2000000`。把 lock/unlock 注释掉重跑，结果**小于** 200 万且每次不同——两条指令序列交错覆盖了对方的写。这个例子的价值在于：它证明了「C 语句看起来是一条，实际不是原子的」，从而说明所有跨线程共享的可变状态都必须由某个同步原语或原子类型守护。

**面试高频问法**

1. **问法**：`pthread_cond_wait` 为什么必须传互斥量？为什么外面要套 `while`？
   **考点**：丢失唤醒的原子性论证，以及虚假唤醒。
   **答法**：传互斥量是为了让「判断谓词」和「睡眠」对通知方原子，否则 signal 可能落在两步之间而丢失；用 while 是因为可能虚假唤醒，且被唤醒到重新持锁之间谓词可能已被别的线程改变，必须重新检查。

2. **问法**：互斥锁和自旋锁怎么选？递归锁有什么坑？
   **考点**：睡眠 vs 忙等，锁类型语义。
   **答法**：临界区只有几条指令且确定不会睡眠时用自旋，否则用互斥让出 CPU；递归锁要显式设 `PTHREAD_MUTEX_RECURSIVE`，默认类型重复加锁是未定义行为，而且递归锁常掩盖「加解锁不配对」的设计错误。

3. **问法**：线程安全和可重入是一回事吗？举一个线程安全但不可重入的例子。
   **考点**：共享状态与调用栈状态的区别。
   **答法**：不是。可重入要求不依赖任何全局/静态可变状态，线程安全只需用锁保护共享状态。加锁的 `strtok` 是线程安全但不可重入的，重入版本是 `strtok_r`；`errno` 靠线程局部存储做到线程安全，但它本身就是典型的全局状态。

4. **问法**：多线程进程 `fork` 之后，子进程里有哪些线程？能做什么？
   **考点**：fork 与线程模型的冲突。
   **答法**：只有调用 `fork` 的那一个线程，其它线程消失但锁的状态被复制过来，所以子进程在 `exec` 之前只能调 async-signal-safe 函数，通常做法是 fork 后立刻 exec，或用 `pthread_atfork` 在 fork 前后加解锁。

5. **问法**：`kill` 发给多线程进程，哪个线程收到？怎么只打断某个线程？
   **考点**：信号递送的线程选择规则。
   **答法**：内核在未阻塞该信号的线程里任选一个，因此想在指定线程处理就要在其它所有线程屏蔽它、只在目标线程解除屏蔽，想定向打断用 `pthread_kill`。

## 第 8 章 IPC 一：管道、FIFO 与消息队列

**要解决的问题**：进程地址空间彼此隔离，必须有一条内核中转的通路才能交换数据。管道给出最小的单向字节流通道（限有亲缘的进程），FIFO 给它一个文件系统名字从而支持无亲缘进程，消息队列则在同样的内核中转之上补上「消息边界」和「优先级」。没有这一层，进程间通信只能靠临时文件加轮询。

**机制**

`pipe(int fd[2])` 返回两个文件描述符，`fd[0]` 只读、`fd[1]` 只写，是**半双工**的；要双向就 `pipe` 两次或直接用 `socketpair`。内核里是一段环形缓冲区，容量按实现而定，Linux 上可用 `fcntl(fd[0], F_GETPIPE_SZ)` 查询、`F_SETPIPE_SZ` 调整（受 `/proc/sys/fs/pipe-max-size` 限制）。因为管道也是文件描述符，所以 `read`/`write`/`close`/`dup2`/`poll` 全套语义都能直接用，`ls | wc -l` 就是 shell 做了 `pipe` + 两次 `fork` + `dup2` + `exec` + 关掉多余端的结果。

三条语义必须背下来：

- **原子性**：写不超过 `PIPE_BUF` 字节的请求是原子的，多个写者不会交错；超过则不保证。POSIX 只要求 `PIPE_BUF` 至少 512，Linux 上是 4096。
- **EOF**：所有写端描述符都关闭后，`read` 返回 0。
- **SIGPIPE**：所有读端都关闭后继续 `write`，内核向写进程发 `SIGPIPE`，默认动作是终止进程；若忽略或捕获，`write` 返回 -1 并置 `errno = EPIPE`。

最常见的 bug 就出在 EOF 上：`fork` 出的子进程继承了管道的两端，父进程若不 `close(fd[1])`，写端的引用计数永不归零，读端就永远等不到 0。管道无数据且写端仍在时，`read` 阻塞（除非 `O_NONBLOCK`，此时返回 -1/`EAGAIN`）。

FIFO（命名管道）用 `mkfifo(path, mode)` 创建，之后双方用普通 `open` 打开。它与匿名管道的差别只在「有名字、可被无亲缘进程打开」；数据通路仍是内核缓冲，进程退出后数据不保留。`open` 的阻塞语义是关键细节：以只读打开会阻塞到有写者打开，以只写打开会阻塞到有读者打开；`O_NONBLOCK` 下只读打开立即成功，只写打开在没有读者时失败并置 `errno = ENXIO`。所以「服务器用只读打开 FIFO 循环读、客户端用只写打开发请求」是标准写法，但要处理客户端在服务器未起时的 `ENXIO`。以 `O_RDWR` 打开 FIFO 在 Linux 上不会阻塞，但这属于实现行为，依赖它会让代码不可移植。

POSIX 消息队列换了抽象：不再是无结构的字节流，而是一条条带长度和优先级的消息。接口是 `mq_open` / `mq_send` / `mq_receive` / `mq_close` / `mq_unlink`，名字形如 `"/myq"`（必须以 `/` 开头且只含一个 `/`），属性 `struct mq_attr` 里的 `mq_maxmsg` 和 `mq_msgsize` 在创建时定死。`mq_send(mq, buf, len, prio)` 的 `prio` 是优先级，队列**按优先级从高到低出队，同优先级 FIFO**——这是它相对管道唯一无法替代的能力。队列本身驻留在内核（Linux 上可见于 `/dev/mqueue`），进程退出不消失，必须 `mq_unlink` 或重启才清理，这也是「消息队列」与「管道」在生命周期上的根本区别。`mq_notify` 可注册 `SIGEV_THREAD` 通知，在空队列收到第一条消息时回调，避免轮询。System V 那一套（`msgget` / `msgsnd` / `msgrcv` / `msgctl`，key 常由 `ftok` 生成）语义相近但用整数 ID 而非路径名，且需要显式 `IPC_RMID` 删除。

**最小例子**

```c
int fd[2];
char buf[8];
pipe(fd);                       /* fd[0] 读, fd[1] 写 */
if (fork() == 0) {
    close(fd[0]);
    write(fd[1], "hi", 2);
    close(fd[1]);
    _exit(0);
}
close(fd[1]);                   /* 父必须关写端，否则下面第二次 read 不返回 */
ssize_t n = read(fd[0], buf, sizeof buf);   /* n == 2, buf = "hi" */
n = read(fd[0], buf, sizeof buf);           /* 子已退出且写端全关 → n == 0，EOF */
```

如果把父进程那句 `close(fd[1])` 删掉，第一次 `read` 仍返回 2，第二次 `read` 会**永久阻塞**——因为父进程自己还持有一个写端，引用计数不为零。一条 `close` 决定程序是正常退出还是挂死，这就是引用计数语义的实际重量。

**面试高频问法**

1. **问法**：管道的读端全部关闭后，写端再 `write` 会怎样？
   **考点**：SIGPIPE 与 EPIPE 的区别，默认处置。
   **答法**：内核向写进程发 `SIGPIPE`，默认动作是终止进程；如果忽略或捕获了它，`write` 返回 -1 且 `errno` 为 `EPIPE`，所以健壮的服务器会屏蔽 SIGPIPE 再判断 EPIPE。

2. **问法**：父进程读了子进程写的数据，为什么第二次 `read` 不返回 0？
   **考点**：文件描述符引用计数决定 EOF。
   **答法**：EOF 的条件是所有写端描述符都被关闭，`fork` 后父子各持一份写端，父进程不 `close(fd[1])` 引用计数就不归零；每个进程都必须关掉自己不用的一端。

3. **问法**：匿名管道和 FIFO 有什么区别？FIFO 用 `O_NONBLOCK` 打开写端会发生什么？
   **考点**：命名与阻塞打开语义。
   **答法**：通路和内核缓冲一样，差别是 FIFO 有文件系统路径、可被无亲缘进程打开、生命周期跟路径走；`O_NONBLOCK` 只写打开时若没有读者会直接失败返回 -1 并置 `ENXIO`，不会阻塞等待。

4. **问法**：`PIPE_BUF` 是干什么的？超过它写会出什么问题？
   **考点**：写原子性的边界。
   **答法**：它是不超过该长度的 `write` 保证原子的上限，多个写者不会交错；超过后内核可能分片，多个进程并发写时字节流会互相穿插，所以协议设计要么把单条消息控制在 `PIPE_BUF` 内，要么改用消息队列或自己加长度头和分帧。

5. **问法**：消息队列比管道多了什么？为什么它需要 `mq_unlink`？
   **考点**：消息边界、优先级与内核持久性。
   **答法**：多了消息边界（一次 `mq_receive` 正好取一条，不会读到半条）和优先级（高优先级先出队），并且它以名字驻留在内核、不随进程退出消失，所以必须显式 `mq_unlink` 或用 `O_EXCL` 之外的方式管理生命周期，否则会残留。

## 第 9 章 IPC 二：共享内存与信号量

**要解决的问题**：管道、FIFO、消息队列传数据都要「用户态 → 内核 → 用户态」拷贝两次，而且内核里还占一块缓冲。共享内存把同一段物理页映射进两个进程的地址空间，让两边直接读写同一份内存；代价是内核不再替你排序，多个进程同时写就会互相覆盖，所以必须配一套跨进程的信号量做互斥与计数。不解决这一对（映射 + 同步），要么性能被拷贝拖住，要么数据被竞态写坏。

**机制**：

POSIX 路径是「fd 语义」，四步：

```c
int fd = shm_open("/demo", O_CREAT | O_RDWR, 0600); /* 名字落在 /dev/shm 下 */
ftruncate(fd, size);                                 /* 新建的共享内存对象大小为 0，必须先定长 */
void *p = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
/* ... 使用 ... */
munmap(p, size); close(fd);
shm_unlink("/demo");   /* 删名字；已映射的进程仍可用，最后一个引用释放才真正回收 */
```

关键点：`shm_open` 返回的是文件描述符，因此可以 `dup`、可以参与 `select`/`poll`，对象出现在 `/dev/shm` 下（Linux 上是 tmpfs，不落盘）。`MAP_SHARED` 才是共享，`MAP_PRIVATE` 是写时复制。`munmap`、`close` 不会销毁对象，名字要显式 `shm_unlink`，否则进程退出后泄漏。

同步原语两种口径：

- **POSIX 信号量**：有名 `sem_open("/s", O_CREAT, 0600, 1)`，无名 `sem_init(&sem, pshared, value)`。`pshared != 0` 时要把信号量本身放在共享内存里，才能跨进程用。`sem_wait` 是 P（减一，为 0 则阻塞），`sem_post` 是 V（加一，唤醒一个等待者）。有名信号量是持久的（`/dev/shm/sem.*`），需要 `sem_unlink`。
- **System V 信号量**：`semget` 得到一个**信号量集合**（数组）而不是单个，`semop` 用 `struct sembuf` 数组做一次原子批量操作，`semctl(..., SETVAL/GETVAL, ...)` 设初值，`IPC_RMID` 销毁，`SEM_UNDO` 让内核在进程异常退出时撤销该进程做过但没撤销的操作。SysV 对象的生命周期跟着内核走，程序退出不会自动删。

共享内存本身没有同步能力，跨进程互斥还得注意：放在共享内存里的 `pthread_mutex_t` 必须用 `PTHREAD_PROCESS_SHARED` 属性初始化，默认属性只在本进程内有效。

**最小例子**：父子进程各对计数器加 1000 次，信号量初值 1。

```c
struct shared { sem_t lock; int n; };
int fd = shm_open("/cnt", O_CREAT | O_RDWR, 0600);
ftruncate(fd, sizeof(struct shared));
struct shared *s = mmap(NULL, sizeof *s, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
sem_init(&s->lock, 1, 1);           /* pshared=1：跨进程 */
s->n = 0;
if (fork() == 0) { for (int i = 0; i < 1000; i++) { sem_wait(&s->lock); s->n++; sem_post(&s->lock); } _exit(0); }
for (int i = 0; i < 1000; i++) { sem_wait(&s->lock); s->n++; sem_post(&s->lock); }
wait(NULL);
printf("%d\n", s->n);               /* 2000 */
```

把 `sem_wait`/`sem_post` 去掉，结果通常小于 2000，且每次运行不同——`s->n++` 在机器码层面是读-改-写三步，两个进程都可能读到同一个旧值。

**面试高频问法**：

1. 「共享内存为什么被称为最快的 IPC？」→ 考点是拷贝次数与同步代价 → 管道/消息队列是用户→内核→用户两次拷贝，共享内存映射后双方直接访问同一物理页，零拷贝；但它不提供任何同步，必须自己配信号量或进程共享互斥量。
2. 「POSIX 共享内存和 System V 共享内存怎么选？」→ 考点是两套 API 的模型差异 → POSIX 是 fd 语义，能 `dup`、能进 `select`/`epoll`、用 `mmap` 统一管理、名字在 `/dev/shm`；SysV 用 `key_t`/`ftok` 标识、`shmctl` 管理、生命周期依附内核且不会自动清理。新代码一般选 POSIX。
3. 「共享内存里能存指针吗？」→ 考点是映射地址不一定相同 → 不能存绝对地址，两个进程 `mmap` 到的虚拟地址可能不同，要存相对于映射起点的偏移量；同步对象还要显式设成进程共享属性。
4. 「持有信号量的进程崩溃了会怎样？」→ 考点是死锁与撤销机制 → POSIX 信号量没有撤销，进程没 `sem_post` 就死掉，其他进程永久阻塞；SysV 可用 `SEM_UNDO` 让内核回滚，POSIX 侧要靠健壮互斥量（`pthread_mutex_consistent` 一类）自己处理。
5. 「`sem_wait` 返回 -1 需要处理什么？」→ 考点是 EINTR → 可能被信号中断返回 `EINTR`，要循环重试，不能当成拿到锁。

## 第 10 章 socket 与 IO 多路复用

**要解决的问题**：socket 也是文件描述符，读写默认阻塞。一个连接一个线程的模型在连接数上千时线程开销和上下文切换就顶不住；而单线程又要避免卡在任何一个 `accept`/`read`/`write` 上。IO 多路复用让一个线程等待「多个 fd 中任意一个就绪」，把「等待」和「处理」解耦。同时 TCP 是字节流，没有消息边界，`read` 还可能一次只返回一部分，这决定了服务端必须有应用层缓冲。

**机制**：

服务端骨架：`socket` → `setsockopt(SO_REUSEADDR)` → `bind` → `listen` → `accept`。监听 fd 只负责接新连接，`accept` 返回一个新的已连接 fd，两者要分开管理。`SO_REUSEADDR` 主要解决服务重启时旧连接处于 TIME_WAIT 导致 `bind` 失败；`SO_REUSEPORT` 是另一件事，让多个进程/线程各自 `bind` 同一端口做负载分担。

三代的差别在「谁来记住哪些 fd 有事件」：

- `select`：`fd_set` 是位图，上限 `FD_SETSIZE`，每次调用都要把集合从用户态拷进内核、内核线性扫描，返回后还得自己遍历并重建集合。水平触发。
- `poll`：`struct pollfd` 数组，没有固定上限，但每次仍是全量拷贝 + 线性扫描。
- `epoll`：`epoll_ctl` 把 fd 注册进内核（Linux 上是一棵红黑树 + 一条就绪链表），fd 上的回调在事件到来时把它挂到就绪链表，`epoll_wait` 只返回就绪的那些。注册一次，长期有效。

触发模式是必考点。LT（水平触发，默认）：只要缓冲区还有数据可读，每次 `epoll_wait` 都会报。ET（`EPOLLET`）：只在状态变化时通知一次。ET 配非阻塞 fd，且必须循环 `read` 到返回 `-1` 且 `errno == EAGAIN`，否则剩余数据永远不会再触发事件。

```c
int ep = epoll_create1(0);
struct epoll_event ev = { .events = EPOLLIN, .data.fd = lfd };
epoll_ctl(ep, EPOLL_CTL_ADD, lfd, &ev);
for (;;) {
    int n = epoll_wait(ep, evs, MAXEV, -1);
    for (int i = 0; i < n; i++) {
        int fd = evs[i].data.fd;
        if (fd == lfd) {
            int c = accept(lfd, NULL, NULL);
            set_nonblock(c);
            struct epoll_event ce = { .events = EPOLLIN | EPOLLET, .data.fd = c };
            epoll_ctl(ep, EPOLL_CTL_ADD, c, &ce);
        } else {
            ssize_t r;
            while ((r = read(fd, buf, sizeof buf)) > 0) append(inbuf[fd], buf, r);
            if (r == 0) { close(fd); epoll_ctl(ep, EPOLL_CTL_DEL, fd, NULL); }
            else if (errno != EAGAIN && errno != EWOULDBLOCK) { close(fd); epoll_ctl(ep, EPOLL_CTL_DEL, fd, NULL); }
        }
    }
}
```

`write` 同理：非阻塞下可能只写出去一部分或返回 `EAGAIN`，所以每个连接要有输出缓冲，注册 `EPOLLOUT` 等可写再续写；一直开着 `EPOLLOUT` 会让 `epoll_wait` 空转。

**最小例子**：上面代码跑起来后，用一个客户端连上并一次 `send` 200 字节。ET 模式下若把内层 `while` 换成只 `read` 一次，假设这次只返回了 100 字节（内核缓冲区里的数据分几次交付是正常的），剩下的 100 字节因为没有新的「不可读→可读」跳变，不会再产生事件，服务端就永远卡在等一个不会来的通知上。改成循环读到 `EAGAIN`，200 字节一次事件内取完，问题消失。同理，客户端的两次 `send` 可能被合并成一次 `read`，也可能被拆开，所以要在 `inbuf` 里按长度字段或分隔符切分消息。

**面试高频问法**：

1. 「select / poll / epoll 的区别？」→ 考点是数据结构与每次调用的代价 → select 是位图、有 `FD_SETSIZE` 上限、每次都要重设集合并全量拷贝+线性扫描；poll 换成数组去掉上限但仍全量拷贝；epoll 用 `epoll_ctl` 注册一次、内核维护就绪链表，`epoll_wait` 的返回量与就绪数相关而不是总 fd 数。
2. 「ET 为什么必须配非阻塞 fd 并读到 EAGAIN？」→ 考点是事件不再重发的后果 → ET 只报一次状态变化，不读到空就会把剩余数据永久晾在缓冲区；而循环读若 fd 是阻塞的，最后一次 `read` 会把整个事件循环挂住。
3. 「TCP 粘包/半包怎么处理？」→ 考点是字节流没有边界 → 应用层缓冲区 + 显式边界（长度前缀或分隔符），把「读到的字节」和「完整消息」分开，用状态机解析，不能假设一次 `read` 等于一条消息。
4. 「epoll 是同步还是异步？LT 和 ET 各适合什么场景？」→ 考点是对就绪通知模型的理解 → epoll 本身是同步就绪通知，真正的读写还要自己发起；LT 写起来简单、不容易丢事件，ET 事件次数少但要严格遵守「读空/写空」纪律，高并发常用 ET 或 LT + 非阻塞。
5. 「多个进程/线程等同一个 listen fd 会有什么问题？SO_REUSEADDR 是干什么的？」→ 考点是惊群与端口复用 → 多等待者会被同时唤醒但只有一个能 `accept` 成功，其余白跑（`EPOLLEXCLUSIVE` 或单 accept 线程分发可缓解）；`SO_REUSEADDR` 解决 TIME_WAIT 下的 `bind` 失败，和 `SO_REUSEPORT` 的多进程负载分担不是一回事。
