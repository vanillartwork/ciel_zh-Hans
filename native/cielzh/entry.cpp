#include <windows.h>
#include <atomic>
#include <cstdio>
#include "entry.h"
#include "hooks.h"
#include "trace.h"
#include "display.h"

namespace cielzh {

namespace {

// One word, changed only by compare-and-exchange, so whoever wins the exchange
// owns the transition and everybody else is told what is going on instead of
// running a second install.  A plain bool could not tell "in progress" from
// "not started", and two callers would both have read false.
std::atomic<State> g_state{State::kIdle};
ReentryFn g_reentry = nullptr;

// Claims the exclusive state.  `from` is updated to whatever was actually
// there, so the caller can say why it failed.
bool Claim(State& from)
{
    State seen = from;
    if (g_state.compare_exchange_strong(seen, State::kBusy,
                                        std::memory_order_acq_rel,
                                        std::memory_order_acquire))
        return true;
    from = seen;
    return false;
}

}  // namespace

const wchar_t kTraceFileName[] = L"cielzh-trace.txt";
const wchar_t kTraceMarkerName[] = L"cielzh-trace.on";
const wchar_t kStatusFileName[] = L"cielzh-status.txt";

bool WriteStatus(void* module, int rc, const char* why)
{
    wchar_t path[560];
    if (!PathBesideModule(module, kStatusFileName, path, 560))
        return false;
    const DisplayStats s = DisplayGetStats();
    char text[512];
    const int n = std::snprintf(text, sizeof(text),
                                "rc=%d\r\nwhy=%s\r\ndisplay=%s\r\nentries=%u\r\n",
                                rc, why ? why : "", s.on ? "on" : "off",
                                static_cast<unsigned>(s.entries));
    if (n <= 0)
        return false;
    const DWORD len = static_cast<DWORD>(n < static_cast<int>(sizeof(text))
                                         ? n : sizeof(text) - 1);
    HANDLE h = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE)
        return false;
    DWORD put = 0;
    const BOOL ok = WriteFile(h, text, len, &put, nullptr);
    CloseHandle(h);
    return ok && put == len;
}

bool TraceWanted(void* module)
{
    wchar_t marker[560];
    if (!PathBesideModule(module, kTraceMarkerName, marker, 560))
        return false;
    return GetFileAttributesW(marker) != INVALID_FILE_ATTRIBUTES;
}

bool PathBesideModule(void* module, const wchar_t* name, wchar_t* out,
                      size_t cap)
{
    if (!out || cap == 0)
        return false;
    out[0] = L'\0';
    if (!name || cap < 2)
        return false;

    const DWORD got = GetModuleFileNameW(static_cast<HMODULE>(module), out,
                                         static_cast<DWORD>(cap));
    // Truncation is reported as "I filled the whole buffer", not as an error.
    if (got == 0 || got >= cap) {
        out[0] = L'\0';
        return false;
    }

    size_t cut = 0;
    for (size_t i = 0; i < got; ++i)
        if (out[i] == L'\\' || out[i] == L'/')
            cut = i + 1;
    if (cut == 0) {
        out[0] = L'\0';
        return false;              // no folder in it; nothing to write beside
    }

    size_t n = 0;
    while (name[n])
        ++n;
    if (cut + n + 1 > cap) {
        out[0] = L'\0';
        return false;
    }
    for (size_t i = 0; i <= n; ++i)
        out[cut + i] = name[i];
    return true;
}

void SetReentryForTest(ReentryFn fn) { g_reentry = fn; }
State CurrentState() { return g_state.load(std::memory_order_acquire); }
bool IsReady() { return CurrentState() == State::kReady; }

int InitializeAt(void* base, size_t size, char* why, int why_len)
{
    if (!why || why_len < 64)
        return 1;
    const size_t wl = static_cast<size_t>(why_len);

    State from = State::kIdle;
    if (!Claim(from)) {
        if (from == State::kReady) {
            std::snprintf(why, wl, "already initialised");
            return 0;
        }
        if (from == State::kBusy) {
            std::snprintf(why, wl,
                          "another caller is initialising or shutting down");
            return 6;
        }
        // kCleanupPending: finishing the cleanup is allowed, starting a new
        // install is not.  Take the state so nobody else does it at the same
        // time, and hand it back exactly as we found it if it cannot finish.
        from = State::kCleanupPending;
        if (!Claim(from)) {
            std::snprintf(why, wl, "another caller is working on the cleanup");
            return 6;
        }
        char w[256];
        if (!RemoveTraceHooks(w, sizeof(w))) {
            g_state.store(State::kCleanupPending, std::memory_order_release);
            std::snprintf(why, wl,
                          "an earlier install is not fully undone (%s); "
                          "refusing to start another", w);
            return 5;
        }
    }

    // From here the state is kBusy and this call owns it.
    if (!base) {
        g_state.store(State::kIdle, std::memory_order_release);
        std::snprintf(why, wl, "no module base");
        return 2;
    }

    // Records may still be pending even when the state said kIdle -- for
    // instance after a failed install whose rollback finished the slots but not
    // the page protections.  Same rule: finish it or refuse.  This has to come
    // before VerifyModule, because a slot still holding our hook would fail
    // verification and report "wrong build" for what is really our own mess.
    if (HooksTouched()) {
        char w[256];
        if (!RemoveTraceHooks(w, sizeof(w))) {
            g_state.store(State::kCleanupPending, std::memory_order_release);
            std::snprintf(why, wl,
                          "an earlier install is not fully undone (%s); "
                          "refusing to start another", w);
            return 5;
        }
    }

    if (!VerifyModule(base, size, why, wl)) {
        g_state.store(State::kIdle, std::memory_order_release);
        return 3;
    }

    // Everything the hooks read must be in place before the first slot is
    // written: a background thread can be inside a hook before the third slot
    // is even touched.
    TraceInit(base);

    // Armed before the hooks, so the very first record can already be written
    // out.  A run that dies a second later is one this has to survive.
    wchar_t trace[560];
    if (TraceEnabled() && PathBesideModule(base, kTraceFileName, trace, 560))
        TraceAutoDump(trace, kTraceDumpEvery, kTraceDumpGapMs);

    // The replacement table.  Missing or broken is not a reason to refuse: the
    // hooks still record, the game still shows its own text, and the dump
    // header says why nothing was replaced.  Loaded before the hooks go in, so
    // the first text any thread sets already sees it.
    DisplayInit(base);
    char table_why[160] = "";
    wchar_t table[560];
    if (PathBesideModule(base, kTextTableName, table, 560))
        DisplayLoad(table, table_why, sizeof(table_why));
    else
        DisplayLoad(nullptr, table_why, sizeof(table_why));

    if (g_reentry)
        g_reentry();

    if (!InstallTraceHooks(base, why, wl)) {
        // 4 and 5 are not "first failure" versus "retry": they are "nothing of
        // ours is left" versus "something is".  An earlier version returned 4
        // for any first failure, and the loader's table read that as "rolled
        // back, behaves like the original" -- which would have been wrong
        // exactly when a hook was still sitting in a vtable.  What the caller
        // needs to decide is whether the process is clean, so that is what the
        // code says.
        // Nothing will record, so an armed dump would only leave an empty file
        // beside the game for somebody to puzzle over.
        TraceAutoDump(nullptr, 0, 0);
        if (HooksTouched()) {
            g_state.store(State::kCleanupPending, std::memory_order_release);
            return 5;
        }
        g_state.store(State::kIdle, std::memory_order_release);
        return 4;
    }

    g_state.store(State::kReady, std::memory_order_release);
    std::snprintf(why, wl, "display %s; recording %s",
                  DisplayGetStats().status,
                  TraceEnabled() ? "on" : "off (cielzh-trace.on turns it on)");
    return 0;
}

int ShutdownAll(char* why, int why_len)
{
    if (!why || why_len < 64)
        return 1;
    const size_t wl = static_cast<size_t>(why_len);

    State from = State::kReady;
    if (!Claim(from)) {
        if (from == State::kBusy) {
            std::snprintf(why, wl,
                          "another caller is initialising or shutting down");
            return 6;
        }
        from = State::kCleanupPending;
        if (!Claim(from)) {
            from = State::kIdle;
            if (!Claim(from)) {
                std::snprintf(why, wl, "state changed under us; try again");
                return 6;
            }
        }
    }

    // Not being initialised is not the same as not having written anything.
    if (!HooksTouched()) {
        g_state.store(State::kIdle, std::memory_order_release);
        std::snprintf(why, wl, "nothing of ours is in the game's vtables");
        return 0;
    }
    if (!RemoveTraceHooks(why, wl)) {
        g_state.store(State::kCleanupPending, std::memory_order_release);
        return 2;
    }
    g_state.store(State::kIdle, std::memory_order_release);
    return 0;
}

}  // namespace cielzh
