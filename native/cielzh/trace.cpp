#include <windows.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include "trace.h"
#include "hooks.h"
#include "display.h"

namespace cielzh {

namespace {

// An hour of play filled 8192 (7039 held, 13186 calls dropped).  Recording is
// now something turned on to look into a problem, and that is exactly the
// session that runs long, so the table is sized for several hours.  The dump
// only walks the records actually held.
constexpr size_t kEvents = 32768;   // power of two
constexpr size_t kObjects = 8192;   // power of two
constexpr size_t kProbe = 24;       // give up after this many steps
constexpr size_t kFullHashMax = 1 << 16;   // longer than this: never folded

CRITICAL_SECTION g_lock;
// A second lock, held for a whole dump.  The dump copies the table into one
// static buffer, so two dumps at once -- an automatic one from a hook and the
// one at exit -- would be filling the same buffer.
CRITICAL_SECTION g_dump_lock;
bool g_init = false;
const uint8_t* g_base = nullptr;

constexpr size_t kPathMax = 520;     // MAX_PATH is not the limit on NTFS
wchar_t g_auto_path[kPathMax];
bool g_auto_on = false;
bool g_atexit_set = false;
uint32_t g_auto_every = 1;
uint32_t g_auto_gap = 0;
uint32_t g_auto_new = 0;
uint64_t g_auto_last = 0;
uint32_t g_auto_writes = 0;
uint32_t g_auto_failures = 0;

Event g_events[kEvents];
uint64_t g_seq = 0;
uint64_t g_calls = 0;
uint64_t g_dropped = 0;
uint64_t g_live = 0;

struct ObjSlot {
    uint64_t addr;
    uint64_t obs;
};
ObjSlot g_objects[kObjects];
uint64_t g_obs_next = 0;
uint64_t g_objects_lost = 0;
std::atomic<Entry> g_entry{Entry::kUnknown};
std::atomic<bool> g_recording{true};

// Both defined further down, beside the dump they drive.  TraceRecord is the
// only caller: a record that is new decides there, under the lock, and writes
// after letting it go.
bool AutoDumpDueLocked();
void AutoDumpNow();

inline uint64_t Mix(uint64_t x)
{
    x ^= x >> 33;
    x *= 0xFF51AFD7ED558CCDull;
    x ^= x >> 33;
    x *= 0xC4CEB9FE1A85EC53ull;
    x ^= x >> 33;
    return x;
}

// Copies up to cap-1 bytes and reports whether anything was left behind.  When
// it truncates it backs up to a UTF-8 lead byte, so a snapshot never ends in
// half a character -- the log is read by people looking at Japanese.
bool CopyText(char* dst, size_t cap, const char* src)
{
    size_t k = 0;
    for (; k + 1 < cap && src[k]; ++k)
        dst[k] = src[k];
    bool truncated = src[k] != '\0';
    if (truncated) {
        while (k > 0 && (static_cast<unsigned char>(dst[k - 1]) & 0xC0) == 0x80)
            --k;
        if (k > 0 && (static_cast<unsigned char>(dst[k - 1]) & 0x80))
            --k;   // drop the lead byte whose continuation bytes were cut
    }
    dst[k] = '\0';
    return truncated;
}

bool SameText(const char* a, const char* b)
{
    for (size_t i = 0;; ++i) {
        if (a[i] != b[i])
            return false;
        if (!a[i])
            return true;
    }
}

uint64_t ObserveLocked(uint64_t addr)
{
    uint64_t h = Mix(addr);
    for (size_t i = 0; i < kProbe; ++i) {
        ObjSlot& s = g_objects[(h + i) & (kObjects - 1)];
        if (s.addr == addr)
            return s.obs;
        if (s.addr == 0) {
            s.addr = addr;
            s.obs = ++g_obs_next;
            return s.obs;
        }
    }
    ++g_objects_lost;
    return 0;
}

}  // namespace

void TraceSetEntry(Entry how)
{
    g_entry.store(how, std::memory_order_relaxed);
}

const char* EntryName(Entry how)
{
    switch (how) {
    case Entry::kExportV1: return "export-v1";
    case Entry::kSelfTest: return "selftest";
    case Entry::kUnknown:  break;
    }
    return "unknown";
}

void TraceInit(const void* module_base)
{
    if (g_init)
        return;
    InitializeCriticalSection(&g_lock);
    InitializeCriticalSection(&g_dump_lock);
    g_base = static_cast<const uint8_t*>(module_base);
    for (size_t i = 0; i < kEvents; ++i)
        g_events[i].first_seq = 0;
    for (size_t i = 0; i < kObjects; ++i)
        g_objects[i].addr = 0;
    g_init = true;
}

uint64_t TraceObserveId(const void* object)
{
    if (!g_init)
        return 0;
    EnterCriticalSection(&g_lock);
    uint64_t id = ObserveLocked(reinterpret_cast<uint64_t>(object));
    LeaveCriticalSection(&g_lock);
    return id;
}

void TraceEnable(bool on)
{
    g_recording.store(on, std::memory_order_release);
}

bool TraceEnabled()
{
    return g_recording.load(std::memory_order_acquire);
}

void TraceRecord(Op op, Klass klass, const void* object, const void* caller,
                 const char* text)
{
    if (!g_init || !g_recording.load(std::memory_order_relaxed))
        return;

    char snap[sizeof(Event::text)];
    const bool truncated = CopyText(snap, sizeof(snap), text ? text : "<null>");
    const uint32_t thread = GetCurrentThreadId();

    const uint64_t addr = reinterpret_cast<uint64_t>(object);
    const uint64_t caller_rva = caller
        ? static_cast<uint64_t>(static_cast<const uint8_t*>(caller) - g_base)
        : 0;

    // Fold the text into the key so a changed string is a new record.  Folding
    // only identical repeats is what keeps a redrawing menu from evicting the
    // one-off calls without hiding the changes we are here to see.
    //
    // The WHOLE text is hashed, not the snapshot.  Keying on the 95-byte prefix
    // and refusing to fold anything truncated put every repeat of one long
    // string on the same probe chain as a new record: the first real run filled
    // 24 slots per long line and then counted 1999 calls as dropped with the
    // table a third full.  A full hash lets the same long string fold, and
    // keeps two long strings that share a prefix on different keys.
    uint64_t full = 0x9E3779B97F4A7C15ull;
    const char* src = text ? text : "<null>";
    size_t len = 0;
    for (; src[len] && len < kFullHashMax; ++len)
        full = Mix(full ^ static_cast<uint8_t>(src[len]));
    if (src[len])
        full = 0;                    // too long to be sure: never fold it
    full = full ? (full | 1) : 0;    // 0 is reserved for "not hashed"
    uint64_t h = Mix(addr ^ Mix(caller_rva));
    h ^= Mix((static_cast<uint64_t>(op) << 1) | static_cast<uint64_t>(klass));
    h ^= Mix(thread);
    h ^= Mix(full);
    if (!full)
        for (size_t i = 0; snap[i]; ++i)
            h = Mix(h ^ static_cast<uint8_t>(snap[i]));

    EnterCriticalSection(&g_lock);
    ++g_calls;
    uint64_t obs = ObserveLocked(addr);

    for (size_t i = 0; i < kProbe; ++i) {
        Event& e = g_events[(h + i) & (kEvents - 1)];
        if (e.first_seq == 0) {
            e.first_seq = e.last_seq = ++g_seq;
            e.object = addr;
            e.obs = obs;
            e.caller_rva = caller_rva;
            e.thread = thread;
            e.hits = 1;
            e.op = op;
            e.klass = klass;
            e.truncated = truncated;
            e.full = full;
            CopyText(e.text, sizeof(e.text), snap);
            ++g_live;
            // Decided while the lock is held, written after it is released: the
            // dump takes the same lock.  Only a new record gets here, so a menu
            // redrawing the same text writes nothing.
            const bool due = AutoDumpDueLocked();
            LeaveCriticalSection(&g_lock);
            if (due)
                AutoDumpNow();
            return;
        }
        // Equal snapshots fold only when the whole texts hash the same: equal
        // prefixes are not equal strings, and merging them would report text
        // nobody finished reading.  A text too long to hash (full == 0) never
        // folds at all.
        if (full && e.full == full && e.truncated == truncated
            && e.op == op && e.klass == klass
            && e.object == addr && e.obs == obs && e.thread == thread
            && e.caller_rva == caller_rva && SameText(e.text, snap)) {
            e.last_seq = ++g_seq;
            if (e.hits != 0xFFFFFFFFu)
                ++e.hits;
            LeaveCriticalSection(&g_lock);
            return;
        }
    }
    // Full: counted, not silently discarded.  A missing line in the dump has to
    // be distinguishable from a call that never happened.
    ++g_dropped;
    LeaveCriticalSection(&g_lock);
}

TraceStats TraceGetStats()
{
    TraceStats s = {};
    if (!g_init)
        return s;
    EnterCriticalSection(&g_lock);
    s.events = g_live;
    s.calls = g_calls;
    s.dropped = g_dropped;
    s.objects = g_obs_next;
    s.objects_lost = g_objects_lost;
    LeaveCriticalSection(&g_lock);
    return s;
}

size_t TraceDrain(Event* out, size_t max)
{
    if (!g_init)
        return 0;
    EnterCriticalSection(&g_lock);
    size_t n = 0;
    for (size_t i = 0; i < kEvents && n < max; ++i)
        if (g_events[i].first_seq)
            out[n++] = g_events[i];
    LeaveCriticalSection(&g_lock);
    return n;
}

namespace {

bool Put(HANDLE h, const char* s, size_t n)
{
    DWORD wrote = 0;
    if (!WriteFile(h, s, static_cast<DWORD>(n), &wrote, nullptr))
        return false;
    return wrote == n;
}

bool PutCsvText(HANDLE h, const char* s)
{
    // RFC 4180: double the quotes.  Newlines and stray control bytes are turned
    // into spaces so one field cannot become two rows.
    char buf[sizeof(Event::text) * 2 + 4];
    size_t k = 0;
    buf[k++] = '"';
    for (size_t i = 0; s[i] && k + 2 < sizeof(buf); ++i) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        if (c == '"') {
            buf[k++] = '"';
            buf[k++] = '"';
        } else if (c < 0x20 || c == 0x7F) {
            buf[k++] = ' ';
        } else {
            buf[k++] = static_cast<char>(c);
        }
    }
    buf[k++] = '"';
    return Put(h, buf, k);
}

}  // namespace

namespace {

// One dump.  `wait` is false only on the way out of the process, where a lock
// held by a thread the OS has already killed is never released: give up with a
// distinct code rather than hang the game's exit.
int DumpTo(const wchar_t* path, const char* reason, bool wait)
{
    if (!g_init)
        return 1;
    if (wait)
        EnterCriticalSection(&g_dump_lock);
    else if (!TryEnterCriticalSection(&g_dump_lock))
        return 4;

    static Event buf[kEvents];
    size_t n = 0;
    TraceStats st = {};
    if (wait) {
        EnterCriticalSection(&g_lock);
    } else if (!TryEnterCriticalSection(&g_lock)) {
        LeaveCriticalSection(&g_dump_lock);
        return 4;
    }
    for (size_t i = 0; i < kEvents && n < kEvents; ++i)
        if (g_events[i].first_seq)
            buf[n++] = g_events[i];
    st.events = g_live;
    st.calls = g_calls;
    st.dropped = g_dropped;
    st.objects = g_obs_next;
    st.objects_lost = g_objects_lost;
    const bool auto_on = g_auto_on;
    const uint32_t auto_writes = g_auto_writes;
    const uint32_t auto_failures = g_auto_failures;
    LeaveCriticalSection(&g_lock);

    HANDLE h = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) {
        LeaveCriticalSection(&g_dump_lock);
        return 2;
    }

    bool ok = true;
    char line[320];
    // Everything the reader needs to size up the sample.  A counter that exists
    // but never reaches the report has now cost us two rounds -- the cdb
    // overflow register and early_calls -- so each one that can mean "this log
    // is incomplete" is printed whether or not it is zero.
    int k = std::snprintf(line, sizeof(line),
                          "# entry=%s armed=%d early_calls=%lu\n"
                          "# reason=%s auto=%s auto_writes=%lu "
                          "auto_failures=%lu\n"
                          "# calls=%llu events=%llu dropped=%llu objects=%llu "
                          "objects_lost=%llu  (text is UTF-8)\n",
                          EntryName(g_entry.load(std::memory_order_relaxed)),
                          HooksArmed() ? 1 : 0,
                          HooksEarlyCalls(),
                          reason,
                          auto_on ? "on" : "off",
                          static_cast<unsigned long>(auto_writes),
                          static_cast<unsigned long>(auto_failures),
                          (unsigned long long)st.calls,
                          (unsigned long long)st.events,
                          (unsigned long long)st.dropped,
                          (unsigned long long)st.objects,
                          (unsigned long long)st.objects_lost);
    ok = ok && Put(h, line, static_cast<size_t>(k));

    // What the display layer did.  guard_hits is the number to read first: each
    // one is a read of a widget showing our Chinese from outside the widget
    // system, handed the Japanese back -- evidence of a reader the stage-one
    // runs never reached.  Its call sites follow.
    const DisplayStats ds = DisplayGetStats();
    k = std::snprintf(line, sizeof(line),
                      "# display=%s whole=%llu names=%llu guarded=%lu "
                      "guard_hits=%llu guard_full=%llu too_long=%llu\n",
                      ds.status,
                      (unsigned long long)ds.whole,
                      (unsigned long long)ds.names,
                      static_cast<unsigned long>(ds.guarded),
                      (unsigned long long)ds.guard_hits,
                      (unsigned long long)ds.guard_full,
                      (unsigned long long)ds.too_long);
    ok = ok && Put(h, line, static_cast<size_t>(k));
    // 32 call sites at up to 11 characters each do not fit in `line`, so this
    // one gets a buffer sized for the worst case rather than a truncation check.
    uint32_t callers[32];
    const size_t nc = DisplayGuardCallers(callers, 32);
    char cl[32 * 11 + 32];
    size_t cn = static_cast<size_t>(std::snprintf(cl, sizeof(cl), "# guard_callers="));
    for (size_t i = 0; i < nc; ++i)
        cn += static_cast<size_t>(std::snprintf(cl + cn, sizeof(cl) - cn, "%s0x%X",
                                                i ? "," : "", callers[i]));
    cl[cn++] = '\n';
    ok = ok && Put(h, cl, cn);

    k = std::snprintf(line, sizeof(line),
                      "first_seq,last_seq,op,class,thread,object,obs,"
                      "caller_rva,hits,truncated,text\n");
    ok = ok && Put(h, line, static_cast<size_t>(k));

    for (size_t i = 0; i < n && ok; ++i) {
        const Event& e = buf[i];
        k = std::snprintf(line, sizeof(line),
                          "%llu,%llu,%s,%s,%u,0x%llX,%llu,0x%llX,%u,%d,",
                          (unsigned long long)e.first_seq,
                          (unsigned long long)e.last_seq,
                          e.op == Op::kSet ? "set" : "get",
                          e.klass == Klass::kSpriteText ? "ACSpriteText" : "ACText",
                          e.thread,
                          (unsigned long long)e.object,
                          (unsigned long long)e.obs,
                          (unsigned long long)e.caller_rva,
                          e.hits, e.truncated ? 1 : 0);
        ok = ok && Put(h, line, static_cast<size_t>(k));
        ok = ok && PutCsvText(h, e.text);
        ok = ok && Put(h, "\n", 1);
    }

    if (ok && !FlushFileBuffers(h))
        ok = false;
    CloseHandle(h);
    LeaveCriticalSection(&g_dump_lock);
    if (!ok) {
        DeleteFileW(path);   // a truncated dump would read as a short one
        return 3;
    }
    return 0;
}

// Called with the lock held, from the one place a record becomes new.
//
// The count is not reset when the gap has not passed: the next new record tries
// again, so a burst arriving faster than the gap is written as soon as it may
// be, rather than needing `every` more records first.
bool AutoDumpDueLocked()
{
    if (!g_auto_on)
        return false;
    if (++g_auto_new < g_auto_every)
        return false;
    const uint64_t now = GetTickCount64();
    if (g_auto_last && now - g_auto_last < g_auto_gap)
        return false;
    g_auto_new = 0;
    g_auto_last = now ? now : 1;
    return true;
}

void AutoDumpNow()
{
    wchar_t path[kPathMax];
    EnterCriticalSection(&g_lock);
    if (!g_auto_on) {
        LeaveCriticalSection(&g_lock);
        return;
    }
    for (size_t i = 0; i < kPathMax; ++i)
        path[i] = g_auto_path[i];
    LeaveCriticalSection(&g_lock);

    const int rc = DumpTo(path, "auto", true);

    EnterCriticalSection(&g_lock);
    ++g_auto_writes;
    if (rc)
        ++g_auto_failures;
    LeaveCriticalSection(&g_lock);
}

// Registered with atexit, which the static CRT runs on the way out.  It writes
// the last records, and it must not wait for a lock -- see TraceDumpNoWait.
void AutoDumpAtExit()
{
    wchar_t path[kPathMax];
    EnterCriticalSection(&g_lock);
    const bool on = g_auto_on;
    for (size_t i = 0; i < kPathMax; ++i)
        path[i] = g_auto_path[i];
    LeaveCriticalSection(&g_lock);
    if (on)
        DumpTo(path, "exit", false);
}

}  // namespace

int TraceDump(const wchar_t* path)
{
    return DumpTo(path, "export", true);
}

int TraceDumpNoWait(const wchar_t* path)
{
    return DumpTo(path, "export", false);
}

int TraceAutoDump(const wchar_t* path, uint32_t every, uint32_t gap_ms)
{
    if (!g_init)
        return 1;
    size_t n = 0;
    if (path) {
        while (path[n] && n + 1 < kPathMax)
            ++n;
        if (path[n])
            return 2;            // it does not fit; better off than guessing
    }

    EnterCriticalSection(&g_lock);
    if (!path) {
        g_auto_on = false;
        g_auto_path[0] = L'\0';
    } else {
        for (size_t i = 0; i <= n; ++i)
            g_auto_path[i] = path[i];
        g_auto_on = true;
        g_auto_every = every ? every : 1;
        g_auto_gap = gap_ms;
        g_auto_new = 0;
        g_auto_last = 0;         // the first new record writes straight away
    }
    const bool arm = g_auto_on && !g_atexit_set;
    if (arm)
        g_atexit_set = true;
    LeaveCriticalSection(&g_lock);

    if (arm && std::atexit(&AutoDumpAtExit) != 0) {
        EnterCriticalSection(&g_lock);
        g_atexit_set = false;
        LeaveCriticalSection(&g_lock);
        // Still on: the periodic dumps are the ones that survive a crash, and
        // they are the reason this exists.  The header reports the count, so a
        // missing tail is visible rather than assumed.
    }
    return 0;
}

AutoDumpInfo TraceAutoDumpInfo()
{
    AutoDumpInfo info = {};
    if (!g_init)
        return info;
    EnterCriticalSection(&g_lock);
    info.on = g_auto_on;
    info.writes = g_auto_writes;
    info.failures = g_auto_failures;
    LeaveCriticalSection(&g_lock);
    return info;
}

void TraceLockForTest()
{
    if (g_init)
        EnterCriticalSection(&g_lock);
}

void TraceUnlockForTest()
{
    if (g_init)
        LeaveCriticalSection(&g_lock);
}

}  // namespace cielzh
