# Stage one: runtime breakpoints

[中文](README.md) | English

This diagnostic observes the original game without loading `cielzh.dll` or changing game logic. It asks whether candidate initialization point RVA `0x7B7F05` precedes the first text-object construction, SetText, and GetText; which threads exist then; and whether initialization repeats. Identifying the nameplate, status, and category-menu consumers requires a separate trace.

Software breakpoints temporarily modify process instructions. Window/input observations are on game call instructions: `0x92858E` calls `CreateWindowExA`, and `0x928016` calls `DirectInput8Create`. `CREATE_WINDOW_CALL` and `DIRECT_INPUT_CALL` mean the call is about to happen, not that it succeeded, and do not count other components' calls.

Do not restore software breakpoints at the `user32!CreateWindowExA` or `dinput8!DirectInput8Create` entry points. In one observed failure, DirectInput's first byte was still `40` while the following four bytes had become a Steam-overlay jump displacement, followed by `c0000096`. That is consistent with breakpoint restoration colliding with an overlay hook. End that debugging session and restart rather than sampling the damaged process.

## Setup and use

Install Debugging Tools for Windows from the Windows SDK installer. The expected debugger is `C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe`.

Exit the game. From the repository root:

```powershell
cd native/stage1
py -3 swap_original.py check
py -3 swap_original.py in
```

`check` is read-only. `in` swaps four resources to their original versions, using range replacement for the font archive. `Backup/` is read, not modified.

In an elevated **64-bit PowerShell**, from `native/stage1`:

```powershell
.\debug.ps1 -Enable
```

Start the game normally through Steam. A cdb window opens. Reach the title screen, load a save, view dialogue with a nameplate, and exit normally. IFEO remains active for every launch of `CielnosurgeDX.exe` until disabled.

Scripts read the actual image base from the x64 PEB and add original RVAs; they do not depend on debugger module names. The log lists the main module by address, prints `breakpoints set:` and the breakpoint list, then executes `g`.

After updating scripts, exit the game and run `-Disable` followed by `-Enable` (or `-Enable -Threads`). Enable copies scripts into its working directory; editing repository files does not update that deployed copy.

For `.cdb` maintenance, avoid semicolons in `$$` comments: CDB treats following text as another command. Keep line-by-line `$$<` loading. `-Enable` writes CRLF without BOM; CDB 10.0.28000 was observed misreading comment tails in LF files. Do not manually deploy an LF copy.

If cdb stops at a second-chance exception, `q` exits the debugging session; the log remains. Always finish with:

```powershell
.\debug.ps1 -Disable
py -3 swap_original.py out
```

`out` restores the swapped patch files and checks hashes. Logs are under `%LOCALAPPDATA%\cielzh_stage1\stage1-*.log`.

## Reading breakpoint logs

From `native/stage1`, replacing the timestamp:

```powershell
py -3 summarize.py "$env:LOCALAPPDATA\cielzh_stage1\stage1-<timestamp>.log"
```

The summary reports first-event ordering, `INIT_CALL` hits, and per-thread reads/writes. Quota-limited samples are lower bounds, not total calls.

`-Enable -Threads` uses `stage1_threads.cdb` and stops at every SetText/GetText, slowing the game substantially. Keep the session short. It tracks up to four thread IDs, including the main thread, with 12 sampled calls and stacks per thread. Fifth and later threads are counted separately in `$t19`; use the exit summary to establish totals. Missing summaries do not establish zero overflow.

## UI text sampling without a debugger

The current DLL includes display replacement. For text sampling, start normally through Steam; cdb is unnecessary. Tracing is off by default. With the game closed, create an empty `cielzh-trace.on` in its directory, then launch. Remove it and restart after diagnosis. Display replacement works with tracing on or off.

Whole-table exports can stall the game thread; a previous hour-long measurement saw roughly 50 ms pauses about every 12 seconds. That observation is not a performance guarantee for other sessions.

| File | Writer | Meaning |
|---|---|---|
| `cielzh-loader.log` | EXE loader entry | Launch result; `loader=rc=00000000` means DLL initialization succeeded |
| `cielzh-status.txt` | DLL | Initialization/display-table status, independent of trace collection |
| `cielzh-trace.txt` | DLL | Samples exported when new events appear, no more often than every 1.5 seconds, and on exit |

A crash may leave the last successful automatic export, not necessarily the final calls. `reason=auto` is a running snapshot, `exit` an exit export, and `export` an explicit request.

From the repository root:

```powershell
py -3 native\stage1\read_trace.py "<game-directory>\cielzh-trace.txt"
```

The reader reports limitations (`dropped`, `objects_lost`, `early_calls`, `auto_failures`, `armed=0`) before thread/caller statistics, read-back controls, and text changes. A read event does not establish whether text participates in logic; inspect the consumer. `obs=` identifies an observed address, not an object lifetime: address reuse shares that identifier.
