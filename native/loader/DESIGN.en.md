# Loader entry design

[中文](DESIGN.md) | English

This page describes the current implementation. The Chinese page also retains the earlier recording-only proposal; its pseudocode, log labels, and pending tasks are historical. Player-facing controls are documented in [installation](../../docs/install.en.md); test coverage is in [validation](../../docs/validation.en.md).

## Version-specific prerequisites

The supported original executable is `steam-2025-07`, with SHA-256 prefix `04b755ab2eb26f26`.

| Item | Recorded value |
|---|---|
| Call site | RVA `0x7B7F05`: `E8 33 8C C5 FF` → `0x410B3D` → `0x97CE50` |
| Original return address | RVA `0x7B7F0A` |
| Original section count | 12 |
| Original section-header space | Table ends at file offset `0x458`; first raw section starts at `0x600`: 424 zero bytes |
| Exception directory | RVA `0x137E000`, size `0x5B980`; host section virtual size `0x64D34` |
| Original final function range | `0xC13EF4–0xC13F56` |
| DLL characteristics | `0x8160`; retain HIGH_ENTROPY_VA, DYNAMIC_BASE, and NX_COMPAT |

Recheck capacity for inputs with `.fontex`. Parse data directories by index after validating `NumberOfRvaAndSizes`: exception = 3, load config = 10, IAT = 12, delay import = 13. The patcher checks each required IAT slot's RVA, DLL, and function name against `tools/pe_loader.py`.

The recorded executable has `CF_INSTRUMENTED` but no `GUARD_CF` image flag and no GFID table. This is a version-specific compatibility result, not proof that CFG can never affect hooks. `VerifyModule` checks the expected headers and CFG configuration and refuses changed configurations. Setting an image flag alone does not rewrite bare indirect calls into guarded calls.

## Entry and calling convention

The original call receives RCX pointing into the caller's frame and RDX copied from R14. The entry saves both, loads the DLL synchronously on the calling main thread, then restores the arguments and tail-jumps to the original target. Every path invokes the original target exactly once, returning to `0x7B7F0A` with its result intact.

`entrycode.cpp` emits the same bytes used in native tests and the patched executable. Both Entry and Log allocate `0x58` bytes:

```text
Caller's RSP after allocation:
+0x00 .. +0x1F   Shadow space for callees
+0x20 .. +0x37   Stack arguments 5–7
+0x38           Saved RCX (Entry) / tag (Log)
+0x40           Saved RDX (Entry) / number (Log)
+0x48           Directory length (Entry) / line length (Log)
+0x50           Module handle (Entry) / file handle (Log)
```

Do not store live values in shadow space or the outgoing stack-argument slots. `CreateFileW` uses seven arguments. RCX remains an absolute pointer when RSP changes, but RCX and RDX are volatile across API calls, which is why they must be saved.

The stub uses only volatile registers; unwind information describes the allocation alone. Both unwind records are `01 04 01 00 04 A2 00 00`. `EmitResult` reports instruction boundaries for tests before allocation, after the prologue, before stack restoration, and after restoration.

An interlocked claim permits one initialization attempt. Later entries increment `kRepeats` and continue to the original target without changing the first result, loading again, or logging again. The entry has no `kStatusBusy`; the DLL has a separate idle/busy/ready/cleanup-pending state machine.

## Paths, ABI, and failures

The DLL and loader log paths are derived from the executable directory. Path handling rejects a zero `GetModuleFileNameW` return, a return at least as large as the buffer capacity, and insufficient room for the directory plus the longest filename and terminator. `CopyW` also takes a capacity. An unusable path sets `kStatusPathBad` and continues without a file log.

The entry loads with `LoadLibraryExW`, resolves `CielZhAbiVersion`, compares its high 16-bit major version, and resolves `CielZhInitializeV1`. Minor changes do not fail the major check. Signature or return-code contract changes require a new major/versioned export rather than silently reusing V1.

```text
CielZhAbiVersion()                       -> uint32
CielZhInitializeV1(char* why, int length)  -> int
CielZhDumpTraceV1(const wchar_t* path)    -> int
CielZhShutdownV1(char* why, int length)   -> int
```

Actual loader log forms are:

| Result | Log |
|---|---|
| DLL load failed | `loader=missing err=<hex>` |
| ABI/export unavailable or incompatible | `loader=abi ver=<hex>` |
| Initialization called | `loader=rc=<hex>` |

Return 0 is success (`loader=rc=00000000`). Return 3 means verification failed; 4 means installation failed with rollback complete; 5 means cleanup is incomplete and hooks may remain; 6 is Busy. The DLL remains loaded until process exit. Restoring vtable slots is necessary but not sufficient evidence that unloading is safe.

The data block includes a 256-byte `why` buffer, but the entry's log records the numeric result, not that text. `kLogResult` distinguishes unattempted logging, success, file-creation failure, and failed/short writes. A reached-DLL status is not proof the log reached disk. `TraceSetEntry()` is internal; the loader does not write DLL trace state through another export.

## PE construction and ownership

Python chooses the layout first, then calls `emit_entry.exe`. Its JSON output includes format version, echoed layout, binary size/hash, data-block size, ABI major, and emission offsets. The patcher checks these before use; machine code for another layout must not be reused.

- `.cielzh`: RX, `0x60000020`, with a 64-byte ownership header before the emitted block.
- `.cielzhd`: RW, `0xC0000040`, zero-filled at load time; no RWX section.
- Append two sorted `RUNTIME_FUNCTION` entries to the existing exception table. Directory size covers entries only, not `UNWIND_INFO`; the latter is inside the emitted block.
- Verify the original five call bytes, then change the four-byte displacement to the emitted entry, not the block's literals.
- Update `SizeOfImage` and clear the checksum; preserve ASLR/DEP settings.

Repeated application verifies old contents before modifying them: magic, layout version, sizes/addresses, machine code re-emitted for that layout, current call target, and both complete Begin/End/Unwind triples at the table tail. Section names alone do not establish ownership. Installer upgrades rebuild from the original base instead of relaxing this check for an older emitter.

Input and output must not name the same file, including aliases. Output is constructed and verified in memory, written to an exclusively created temporary file in the output directory, read back and verified, then replaced into place. Failure preserves the input and any existing output and cleans up this operation's temporary file.

## Tests and runtime evidence

The native chain test drives a simulated original call site through the actual emitted bytes to an original-target probe. It checks argument preservation through five- and seven-argument APIs, alignment, return address/value, repeat-entry state, failures, and unwind behavior. It also tests real file logging. The synthetic PE suite checks file layout and output transactions in CI without game data.

The current DLL performs display replacement; trace collection is off unless `cielzh-trace.on` is present at startup. Capacity is 32,768 events. `TraceDrain` does not imply clearing. Aggregated events, a single `caller_rva`, and observation IDs cannot establish chronology, UI ownership, logical use of a read, or object lifetime by themselves.

Installation now covers the EXE, DLL, replacement table, and range writes in one recoverable transaction. Runtime coverage, threading, and display behavior still require game tests; passing synthetic tests does not establish them.
