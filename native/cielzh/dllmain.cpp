// Exported entry points for the Chinese display layer.
//
// DllMain does nothing.  It runs under the loader lock, where calling into
// another DLL, starting a thread or waiting on one is a documented way to
// deadlock, so every real step waits for CielZhInitializeV1, which the game's
// own code calls once it is past early startup.
//
// DisableThreadLibraryCalls is deliberately absent: this DLL links the static
// CRT, which needs the thread notifications that call would suppress.
//
// The logic behind these exports is in entry.cpp, where the self-test can reach
// it; the only thing added here is GetModuleHandleW(nullptr).
//
// The loader does NOT tell us how it went -- it has its own log for that, and
// an export for it would be one more piece of ABI to keep in step.  What the
// dump header reports is how the DLL itself was entered, which is something
// this side actually knows.
#include <windows.h>
#include "abi.h"
#include "entry.h"
#include "trace.h"

extern "C" BOOL APIENTRY DllMain(HMODULE, DWORD, LPVOID)
{
    return TRUE;
}

extern "C" uint32_t __cdecl CielZhAbiVersion(void)
{
    return cielzh::kAbiVersion;
}

extern "C" int __cdecl CielZhInitializeV1(char* why, int why_len)
{
    cielzh::TraceSetEntry(cielzh::Entry::kExportV1);
    // Decided before anything is installed, so the first hook call already
    // knows.  Players have no marker file and pay nothing for the recorder.
    HMODULE exe = GetModuleHandleW(nullptr);
    cielzh::TraceEnable(cielzh::TraceWanted(exe));
    return cielzh::InitializeAt(exe, 0, why, why_len);
}

extern "C" int __cdecl CielZhDumpTraceV1(const wchar_t* path)
{
    if (!cielzh::IsReady())
        return 1;
    return cielzh::TraceDump(path);
}

// Unloading is only safe once every slot and page is back.  A non-zero result
// means "keep this DLL loaded"; stage one keeps it resident until exit anyway.
extern "C" int __cdecl CielZhShutdownV1(char* why, int why_len)
{
    return cielzh::ShutdownAll(why, why_len);
}
