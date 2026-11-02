# 阶段一：运行时断点

只观察原版游戏，不加载 `cielzh.dll`，也不改游戏逻辑。这一轮要回答：

- 初始化候选点（`0x7B7F05`）是否早于第一个文字对象的构造、第一次 SetText 和第一次 GetText；
- 它执行时有哪些线程，各自在做什么；
- 它会不会执行不止一次。

名牌、任务状态、分类菜单各自走哪个调用点，要另跑一轮，本轮不涉及。

这里使用软件断点，会临时改写被调试进程的指令字节。窗口、输入观察点放在游戏 EXE
内的调用指令上：`0x92858E` 调用 `CreateWindowExA`，`0x928016` 调用
`DirectInput8Create`。日志中的 `CREATE_WINDOW_CALL` / `DIRECT_INPUT_CALL` 表示
即将调用，不表示 API 已成功返回，也不统计其他组件对这些 API 的调用。

不要恢复原来的 `user32!CreateWindowExA` / `dinput8!DirectInput8Create` 入口软件断点。
一次现场中，DirectInput 入口首字节仍是原始的 `40`，后四字节已经变成跳往 Steam
覆盖层的跳转位移，随后触发 `c0000096`。这高度吻合断点恢复旧字节与覆盖层挂钩冲突。
发生这种异常后，应退出此次调试并重新启动游戏，不在已损坏的进程里继续采样。

## 一次性准备

安装 **Debugging Tools for Windows**：在 Windows SDK 安装程序中只勾选这一项即可。
装好后应有 `C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe`。

## 步骤

先退出游戏，然后依次执行：

```
py -3 swap_original.py check
py -3 swap_original.py in
```

`check` 只做核对，不改文件；`in` 把四个文件换成原版。`Backup/` 只读取、不写入。

用**管理员身份**打开 64 位 PowerShell，执行：

```
.\debug.ps1 -Enable
```

之后从 Steam 正常启动游戏，会弹出一个 cdb 控制台窗口。进到标题画面，读取存档，看到一段带名牌的对话，然后正常退出游戏。

脚本从 x64 PEB 读取主程序的实际加载基址，再加原版 RVA 设置断点，不依赖
`CielnosurgeDX` 或 `Ciel_x64_MasterSteam` 这样的调试器模块名。启动日志会按地址列出
主模块，随后打印 `breakpoints set:` 和断点列表，并执行 `g` 继续游戏。

更新脚本后，如果之前已经启用 IFEO，请先退出游戏，再运行 `-Disable`、`-Enable`
（线程版则用 `-Enable -Threads`）。启用时会把脚本复制到工作目录，修改仓库里的
脚本不会自动更新之前复制的版本。

维护 `.cdb` 文件时，`$$` 注释内不要使用分号：CDB 会把分号后的内容当成命令。
继续使用按行执行的 `$$<` 加载方式。
`debug.ps1 -Enable` 会把部署副本统一写成 CRLF 换行、无 BOM。CDB 10.0.28000
读取 LF 文件时，实测会把注释尾部再次作为命令执行，因此不要直接复制 LF 文件到工作目录。

如果 cdb 窗口停下来等待输入（第二次机会异常），输入 `q` 回车即可，日志照样保留。

收尾，缺一步都不行：

```
.\debug.ps1 -Disable
py -3 swap_original.py out
```

启用期间，**每一次**启动 `CielnosurgeDX.exe` 都会经过 cdb。`out` 会把补丁原样换回，并逐个文件核对哈希。

最后把 `%LOCALAPPDATA%\cielzh_stage1\stage1-*.log` 发回来。

## 读日志

```
py -3 summarize.py %LOCALAPPDATA%\cielzh_stage1\stage1-<时间戳>.log
```

输出首次发生顺序、`INIT_CALL` 命中次数、按线程的读写统计。**配额用尽的线程会标注出来**——那一行的数字是下限，不是实际调用数。

## 线程版

`.\debug.ps1 -Enable -Threads` 会改用 `stage1_threads.cdb`：每次 SetText / GetText 都会停一下。游戏会明显变慢，进到标题画面、翻一两个菜单、看一段带名牌的对话就退出。

记录方式是**每个线程独立配额**：最多记住 4 个线程 ID，每个 12 次调用，各带一次调用栈，**主线程也在内**。第 5 个及以后的线程只计数（`$t19`）。

上一版是「非主线程的前 40 次」，一个忙碌的后台线程就能把额度吃光，而且主线程根本不在记录范围内——「主线程后来有没有加入」在设计上就看不到。这一版是为回答那个问题改的。

## 用显示层记录界面文字（不用调试器）

早期只记录版用来定位谁在读写 UI 文本。0.9.7 的 DLL 已包含显示替换；要采样文字调用，正常从 Steam 启动即可，不需要 cdb 断点。

**记录默认关闭**：在游戏目录放一个名为 `cielzh-trace.on` 的空文件才会记录。原因是自动写出整张表
要在游戏线程里停约 50 ms（实测一小时游戏里约每 12 秒一次），玩家不该为一份自己不看的日志付出卡顿。
显示层不受影响，开不开记录都照常替换。

开启记录后游戏目录里会出现两个文件：

| 文件 | 谁写的 | 说明 |
|---|---|---|
| `cielzh-loader.log` | EXE 里的加载入口 | 每次启动都写。`loader=rc=00000000` 表示 DLL 已加载且初始化成功 |
| `cielzh-trace.txt` | `cielzh.dll` | 每出现一条新记录就写（最快 1.5 秒一次），退出时再写一次 |

`cielzh-trace.txt` 是自动写出的，因此**崩溃也能留下记录**——只在退出时写的话，最需要
证据的那次运行恰好什么都没有。表头的 `reason=` 说明这份文件是哪一种：`auto`（游戏还在
运行时写的，之后的记录不在里面）、`exit`（写到进程结束）、`export`（有人主动调用导出）。

读记录：

```powershell
py -3 native\stage1\read_trace.py "<游戏目录>\cielzh-trace.txt"
```

它先说样本是否被截断（`dropped`、`objects_lost`、`early_calls`、`auto_failures`、
`armed=0`），再给出按线程、按调用点的统计、哪些控件被读回、哪些控件的文字变过。

**它不回答**读到的值是否参与逻辑。记录只能指出是哪个调用点读的；要确定，得去反汇编那个
调用点。同样，`obs=` 是地址的编号，不是对象的生命周期：被释放后在同一地址新建的控件与
原来的共用一个编号。
