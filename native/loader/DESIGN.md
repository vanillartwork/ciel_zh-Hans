# 加载入口设计（只记录阶段）

本文保留早期设计和当时的待验证项。当前版本的显示层及诊断开关见[安装说明](../../docs/install.md)，PE 自检见[自动校验](../../docs/validation.md)。

把 `CielnosurgeDX.exe` 里 `0x7B7F05` 那条 call 改指向新增节内的一小段代码，
由它同步加载 `cielzh.dll`、调用 `CielZhInitialize`，然后尾调用原目标。
本轮交付「可靠加载并取得可分析日志」，**不做文字替换**。

适用版本：原版 sha256 `04b755ab2eb26f26…`（Steam 2025-07）。

## 1. 已核实的前提

| 项 | 实测 |
|---|---|
| 原调用 | `0x7B7F05: E8 33 8C C5 FF` → `0x410B3D` → `0x97CE50`，返回 `0x7B7F0A` |
| 需要的导入 | `LoadLibraryExW` `0x1413E34D0`、`GetProcAddress` `0x1413E3268`、`GetModuleFileNameW` `0x1413E3528`，均已在 IAT |
| 节数 | 12 |
| 节表余量（实测） | 节表止于文件偏移 `0x458`，第一个节数据始于 `0x600` → **424 字节连续零**，两个新节需 80 字节。已加过 `.fontex` 的输入必须重新测量 |
| 异常目录 | RVA `0x137E000`，大小 `0x5B980`；所在节 vsz `0x64D34`，**目录后有 `0x93B4` 字节全零余量** |
| 数组末条 | `0xC13EF4–0xC13F56`；新节 RVA ≥ `0x145C000`，追加即保持升序 |
| ASLR/DEP | `DllCharacteristics = 0x8160`：HIGH_ENTROPY_VA、DYNAMIC_BASE、NX_COMPAT 全部保留 |

数据目录一律按**索引**解析并先检查 `NumberOfRvaAndSizes`，不再手算偏移：
`Exception` = 索引 3（`opt+136`）、`LoadConfig` = 索引 10（`opt+192`）、
`IAT` = 索引 12（`opt+208`）、`DelayImport` = 索引 13（`opt+216`）。
我先前把 `opt+208` 当成延迟导入，实为 IAT。

**当前版本下 CFG 不会拦截钩子。** `GuardFlags = 0x100`（`CF_INSTRUMENTED`），
但 `DllCharacteristics` 的 `GUARD_CF` **未置位**、`GuardCFFunctionTable` 为空，
与反汇编里的裸 `call qword ptr [rax+0x20]` 一致。

理由写成：**CFG 配置或相关调用路径一旦变化，本兼容性结论即失效，拒绝安装钩子，
等待重新验证。** 不写成「必然崩溃」——是否拒绝还取决于调用点是否真的执行检查、
目标是否登记在 GFID 元数据里，以及进程实际策略；置位映像标志并不会把已有的裸
间接调用改成带检查的调用。

**已落到代码**：`VerifyModule` 现在核对 Optional Header 的 magic 与长度、
数据目录数量、`DllCharacteristics`、Load Config 的 `GuardFlags` 与 GFID 表，
任何一项与上表不符即拒绝。自检里改动这些字段、**保持槽位与函数字节不动**，
确认确实被拒（7 项）。原版与已打补丁的 EXE 都实测通过。

## 2. 入口流程

原调用点带着参数，必须原样交给原目标：

```
0x7B7EFD  mov  rdx, r14
0x7B7F00  lea  rcx, [rsp+0x40]
0x7B7F05  call 0x410B3D            ← 改这条的位移
0x7B7F0A  lea  rcx, [rip+0x96711F]
```

保存槽的位置由**入口调用过的 API 里参数最多的那个**决定，不能随便挑一个偏移。
x64 约定里第 5 个及以后的参数放在调用时的 `[rsp+0x20]`、`[rsp+0x28]`……
所以把原 `RCX` 存在 `[rsp+0x20]` 会被 `WriteFile`（5 个参数）的第 5 个参数覆盖——
即便那个参数是 `NULL` 也照样要写进去，恢复出来的 `RCX` 就变成了 0。
`CreateFileW`（7 个参数）还会用到 `[rsp+0x28]`、`[rsp+0x30]`。

入口用到的最大参数数是 7（`CreateFileW`），于是：

```
[rsp+0x00 .. 0x1F]  shadow space
[rsp+0x20 .. 0x37]  第 5–7 参数
[rsp+0x38]          保存原 RCX
[rsp+0x40]          保存原 RDX
                    → sub rsp, 0x48（0x48 mod 16 = 8，加上返回地址后 16 字节对齐）
```

路径缓冲、`why` 缓冲、写入长度**不放栈上**，放进 `.cielzhd`：只在 `Interlocked`
置位后的那一次执行里使用，栈帧因此不必再扩。若将来改成放栈上，`0x48` 必须重算——
它是从「最大 7 个参数 + 两个保存槽」推出来的，不是一个固定答案。

```
入口:
    sub  rsp, 0x48
    mov  [rsp+0x38], rcx           ; 在参数区之上，任何被调用函数都碰不到
    mov  [rsp+0x40], rdx
    <状态字 Interlocked 置位，已尝试过则跳到 done>
    GetModuleFileNameW / 改名 / LoadLibraryExW
    GetProcAddress("CielZhAbiVersion")  → 比对版本
    GetProcAddress("CielZhInitializeV1") → 调用，记返回码与 why
    写 cielzh-loader.log（CreateFileW / WriteFile / CloseHandle）
done:
    mov  rcx, [rsp+0x38]
    mov  rdx, [rsp+0x40]
    add  rsp, 0x48
    jmp  0x410B3D                  ; 尾调用原目标，它返回到 0x7B7F0A
```

另一种同样可行的写法是把写日志挪进一个**自带栈帧的辅助函数**，外层保存槽就不会
和辅助函数内部的 API 参数区重叠。哪种都行，但不能两者都不做。

`rcx` 是指向调用者栈帧的绝对指针，不受我们改 `rsp` 影响；但它和 `rdx` 都是
易失寄存器，被任何 API 调用破坏，所以必须显式保存。

**完整链条测试必须真的走一次写日志的路径。** 只模拟三参数以内的 API，
正好漏掉这个问题。

**全部路径**（missing / abi / ready / failed / dirty / busy）都走同一个 `done`，
恢复参数与栈，并且**恰好执行一次**原调用。展开信息描述最终生成的真实序言与尾声，
不是这段示意。

入口在**主线程**同步执行，不起新线程：主线程自己就是文字写入者之一
（实测 SET=12，写的是时钟），异步安装等于自己和自己赛跑。

状态字用 `InterlockedCompareExchange` 置位，保证「已尝试过」只判一次，
重复进入不会反复 `LoadLibraryExW`。DLL 内部另有自己的状态机（`kIdle/kBusy/
kReady/kCleanupPending`），两层各管各的。

## 3. 可选加载：失败绝不静默

| 情况 | 行为 | 记录 |
|---|---|---|
| 取不到主程序路径／路径被截断／目录太长放不下文件名 | 执行原调用 | **无日志**（没有目录就没有落点），只写 `kStatus = kStatusPathBad` |
| DLL 不存在 / `LoadLibraryExW` 失败 | 执行原调用 | `loader=missing` + GetLastError |
| `CielZhAbiVersion` 缺失或版本不认识 | 执行原调用，不卸载 | `loader=abi` |
| `CielZhInitializeV1` 缺失 | 执行原调用，不卸载 | `loader=abi` |
| 返回 0 | 继续 | `loader=ready` |
| 返回 3 或 4（校验失败；或安装失败且**已彻底回滚**） | 继续，行为同原版 | `loader=failed` + why |
| 返回 5（**仍有残留**，首次失败也算） | 继续，**保留 DLL 不卸载、不重试** | `loader=dirty` + why |
| 返回 6（Busy） | 继续 | `loader=busy` |

返回码 4 与 5 的分界是**进程里还有没有我们的东西**，不是「第几次尝试」。
先前 `InitializeAt` 对任何首次失败都返回 4，而本表把 4 解释成「已回滚」——
恰好在虚表里还留着钩子时给出错误结论。现已改为：`HooksTouched()` 为真即返回 5。

本阶段已进入初始化的 DLL **一律常驻到进程退出**，不把返回码当作可以卸载的充分证据。

记录落到 `cielzh.dll` 旁边的 `cielzh-loader.log`（仅这几行，不是采样日志）。
入口自身用 `WriteFile` 写，不依赖 CRT。

**路径每一步都有界。** `GetModuleFileNameW` 用返回容量表示截断，不是返回 0，
所以三条检查缺一不可：返回 0 是取不到，返回值 ≥ 容量是被截断，
目录长度 + 最长文件名 + 终止符 > 容量是放不下。截断的路径既会认错目录，
也会让拼接越界。`CopyW` 另带容量参数作为兜底。

**「试过记录」和「记录成功」是两回事。** `kLogResult` 区分未尝试、成功、
`CreateFileW` 失败、`WriteFile` 失败或短写；入口检查返回值与实际写入长度。**加载器不向 DLL 回传状态**：那样要多一个
导出接口去保持同步。DLL 的导出头里 `entry=` 只说它自己是怎么被进入的。

正式汉化包由安装器校验 DLL 完整性；玩家不应在无提示的情况下跑不完整的汉化。

## 4. PE 修改范围

- 新增一节 `.cielzh`，`CODE | EXECUTE | READ`（`0x60000020`）。
  可变状态放在另一节 `.cielzhd`，`INIT_DATA | READ | WRITE`。**不用 RWX。**
- 异常展开：`RUNTIME_FUNCTION` 与 `UNWIND_INFO` 都可以放进 `.pdata` 目录之后的
  全零余量，但**目录 `Size` 只能涵盖函数表条目**：

  ```
  新 Size = 原 Size + 12 × 新增条目数
  ```

  `UNWIND_INFO` 必须落在目录范围**之外**，由条目里的 `UnwindInfoAddress` 引用。
  把它算进 `Size` 会被当成更多函数条目。入口 RVA 高于一切现有条目，升序自然保持。
- 只改写 `0x7B7F05` 处 `E8` 之后的 4 字节位移；改前核对原 5 字节。
- 重复安装**不能只认节名**。要核对自有标识（magic + 布局版本）、容量，以及
  `0x7B7F05` 处的位移当前指向哪里，确保既不追加重复的展开条目，
  也不覆盖已有的展开数据。节名相同而布局不同时拒绝，不猜。
- `SizeOfImage` 相应增大，校验和清零（与 `.fontex` 同法）。
- `.fontex` 是只读数据节，这是本项目第一次新增**可执行**节；两者的验证不能互相替代。

## 5. ABI 契约

导出全部带版本后缀，另加一个可查询的版本号——**找到符号不等于 ABI 一致**：

```
CielZhAbiVersion()  -> uint32，高 16 位 major、低 16 位 minor（当前 0x00010000）
CielZhInitializeV1(char* why, int why_len) -> int
CielZhDumpTraceV1(const wchar_t* path)     -> int
CielZhShutdownV1(char* why, int why_len)   -> int
```

加载器先取 `CielZhAbiVersion`，缺失或 **major** 不认识即判 `abi` 并执行原调用。
比较的是高 16 位，不是整字——否则兼容的 1.1 会被拒绝。日志里记录的仍是完整版本号。
改签名、改返回码含义、删导出 → 新后缀（`…V2`）并递增 major，旧导出不改语义复用：
旧加载器必须在版本检查处失败，而不是调进一个悄悄变了的东西。

`TraceSetEntry()` 保持**内部函数、不导出**。加载器写自己的日志，DLL 在初始化里
设自己的 `entry=`。

## 6. 记录器同期要补的

- `TraceDump` 的表头已补 `entry / armed / early_calls`，与
  `calls / events / dropped / objects / objects_lost` 一起输出。
  「计数存在但报告看不到」已经犯过两次（`$t19`、`early_calls`）。
- 导出改成**取快照 → 释放锁 → 写文件**，并提供清空选项；
  目前 `TraceDrain` 只复制不清空，8192 个槽位不会释放。
- 加**场景标记**：调试版按名牌／任务状态／分类菜单分段采样，
  由导出接口带入标记，否则三类界面混在一份日志里分不开。
- `caller_rva` 只有直接调用者。`0x9627A0` 是公共属性加载，服务多个界面，
  **单凭这一层地址区分不了三类界面**；对首次出现的调用点按需保存有限深度的栈。
- 「几乎无开销」尚未测量：每次调用仍有复制文字、算哈希、取锁。
  需要在菜单刷新、列表滚动这类高频场景实测帧耗时。

## 7. 验证顺序

1. 测试程序里走**完整链条**，而不是只直接调 `CielZhInitializeV1`：

   ```
   模拟原调用点 → 实际生成的入口机器码 → 原目标探针
   ```

   检查参数（RCX/RDX）、栈对齐、返回位置、返回值、展开信息，以及六条失败路径。
   首轮重点：首次失败残留即报 dirty、真实入口的参数恢复、异常展开、
   重复进入不重复安装。
2. 原版游戏只记录验证：先确认 `loader=ready`、`early_calls`、armed 状态。
3. 分三段采样三类界面，得出消费者归属。
4. 据此决定原文与显示副本是否分开，再实现替换。

首次正式装机前，另需完成安装器对 DLL 的创建、升级、失败撤销与卸载管理。
