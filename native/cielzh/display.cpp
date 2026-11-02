#include <windows.h>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <new>
#include <vector>
#include "display.h"
#include "version.h"

namespace cielzh {

const wchar_t kTextTableName[] = L"cielzh-text.bin";

namespace {

// --- the table ---------------------------------------------------------------
//
//   0   "CZT1"
//   4   u32 version (1)
//   8   u32 count
//   12  u32 pool bytes
//   16  count x { u64 hash; u32 jp_len; u32 zh_off; u32 zh_len; u32 flags }
//   ..  pool: the Chinese strings, UTF-8, not terminated
//   ..  u64 FNV-1a over everything before it
//
// Sorted by (hash, jp_len), no two entries equal.  Everything is checked before
// any of it is used: a table that does not hold together is refused whole.
constexpr uint32_t kVersion = 1;
constexpr size_t kHeader = 16;
constexpr size_t kEntry = 24;
constexpr size_t kMaxTable = 4u << 20;
constexpr size_t kMaxText = 1u << 16;    // longer texts are not examined

struct Entry {
    uint64_t hash;
    uint32_t jp_len;
    uint32_t flags;
    const char* zh;      // terminated copy, owned by g_pool
};

std::vector<Entry> g_entries;
std::vector<char> g_pool;          // terminated Chinese strings
std::atomic<bool> g_on{false};
char g_status[96] = "off: no table loaded";
const uint8_t* g_base = nullptr;

// --- the widgets showing our Chinese -----------------------------------------
//
// Open addressing on the widget address, with tombstones.  `orig` is the
// Japanese the game set, handed back to readers that are not the widget system.
//
// A freed original goes into a ring and is released only when it falls out of
// the end.  The game's own std::string may keep its buffer when a new text fits
// in it, so a reader still holding the old pointer reads stale but mapped
// memory; ours must not be less forgiving than the thing it stands in for.
constexpr size_t kGuards = 4096;           // power of two
constexpr size_t kProbe = 32;
constexpr uintptr_t kTomb = 1;
constexpr size_t kGrave = 1024;

struct Guard {
    uintptr_t self;
    char* orig;
    uint64_t disp_hash;
    uint32_t disp_len;
};
Guard g_guards[kGuards];
char* g_grave[kGrave];
size_t g_grave_next = 0;
std::atomic<uint32_t> g_guarded{0};
CRITICAL_SECTION g_lock;
std::atomic<bool> g_lock_ready{false};

constexpr size_t kCallers = 32;
uint32_t g_callers[kCallers];
size_t g_callers_n = 0;

std::atomic<uint64_t> g_whole{0}, g_names{0}, g_hits{0}, g_full{0}, g_long{0};

inline uint32_t Le32(const uint8_t* p)
{
    return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8)
         | (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}
inline uint64_t Le64(const uint8_t* p)
{
    return static_cast<uint64_t>(Le32(p)) | (static_cast<uint64_t>(Le32(p + 4)) << 32);
}

void Lock()
{
    // The lock is set up the first time anything needs it.  Two threads racing
    // here is the one case a flag cannot settle, so it is settled before the
    // hooks are armed: DisplayInit calls this once, on the installing thread.
    if (!g_lock_ready.load(std::memory_order_acquire)) {
        InitializeCriticalSection(&g_lock);
        g_lock_ready.store(true, std::memory_order_release);
    }
    EnterCriticalSection(&g_lock);
}
void Unlock() { LeaveCriticalSection(&g_lock); }

void Bury(char* p)       // with the lock held
{
    if (!p)
        return;
    delete[] g_grave[g_grave_next];
    g_grave[g_grave_next] = p;
    g_grave_next = (g_grave_next + 1) % kGrave;
}

size_t Slot(uintptr_t self, size_t i)
{
    uint64_t x = self;
    x ^= x >> 33;
    x *= 0xFF51AFD7ED558CCDull;
    x ^= x >> 33;
    return static_cast<size_t>((x + i) & (kGuards - 1));
}

Guard* FindLocked(uintptr_t self)
{
    for (size_t i = 0; i < kProbe; ++i) {
        Guard& g = g_guards[Slot(self, i)];
        if (g.self == 0)
            return nullptr;
        if (g.self == self)
            return &g;
    }
    return nullptr;
}

Guard* InsertLocked(uintptr_t self)
{
    Guard* free_slot = nullptr;
    for (size_t i = 0; i < kProbe; ++i) {
        Guard& g = g_guards[Slot(self, i)];
        if (g.self == self)
            return &g;
        if ((g.self == 0 || g.self == kTomb) && !free_slot)
            free_slot = &g;
        if (g.self == 0)
            break;
    }
    if (free_slot) {
        free_slot->self = self;
        free_slot->orig = nullptr;
        g_guarded.fetch_add(1, std::memory_order_relaxed);
    }
    return free_slot;
}

void DropLocked(Guard* g)
{
    Bury(g->orig);
    g->orig = nullptr;
    g->self = kTomb;
    g_guarded.fetch_sub(1, std::memory_order_relaxed);
}

const Entry* Find(const char* p, size_t n, uint32_t flag)
{
    if (n == 0)
        return nullptr;
    const uint64_t h = TextHash(p, n);
    size_t lo = 0, hi = g_entries.size();
    while (lo < hi) {
        const size_t mid = lo + (hi - lo) / 2;
        const Entry& e = g_entries[mid];
        if (e.hash < h || (e.hash == h && e.jp_len < n))
            lo = mid + 1;
        else
            hi = mid;
    }
    if (lo < g_entries.size()) {
        const Entry& e = g_entries[lo];
        if (e.hash == h && e.jp_len == n && (e.flags & flag))
            return &e;
    }
    return nullptr;
}

bool IsUiReader(const void* caller)
{
    if (!g_base || !caller)
        return false;
    const uint8_t* c = static_cast<const uint8_t*>(caller);
    if (c < g_base)
        return false;
    const uint64_t rva = static_cast<uint64_t>(c - g_base);
    for (const UiReader& r : kUiReaders)
        if (rva >= r.begin && rva < r.end)
            return true;
    return false;
}

size_t BoundedLen(const char* s, size_t max)
{
    size_t n = 0;
    while (n < max && s[n])
        ++n;
    return n;
}

void SetStatus(const char* s)
{
    std::snprintf(g_status, sizeof(g_status), "%s", s);
}

}  // namespace

uint64_t TextHash(const char* p, size_t n)
{
    uint64_t h = 0xCBF29CE484222325ull;
    for (size_t i = 0; i < n; ++i) {
        h ^= static_cast<uint8_t>(p[i]);
        h *= 0x100000001B3ull;
    }
    return h;
}

void DisplayInit(const void* module_base)
{
    g_base = static_cast<const uint8_t*>(module_base);
    Lock();
    Unlock();
}

int DisplayLoadBytes(const uint8_t* d, size_t n, char* why, size_t why_len)
{
    auto refuse = [&](int rc, const char* what) {
        std::snprintf(why, why_len, "%s", what);
        char s[96];
        std::snprintf(s, sizeof(s), "off: %s", what);
        SetStatus(s);
        return rc;
    };
    if (g_on.load(std::memory_order_acquire))
        return refuse(9, "a table is already loaded");
    if (!d || n < kHeader + 8)
        return refuse(2, "table too short");
    if (n > kMaxTable)
        return refuse(2, "table too large");
    if (std::memcmp(d, "CZT1", 4) != 0)
        return refuse(3, "not a text table (magic)");
    if (Le32(d + 4) != kVersion)
        return refuse(3, "text table version not understood");
    const uint64_t count = Le32(d + 8);
    const uint64_t pool = Le32(d + 12);
    const uint64_t body = kHeader + count * kEntry + pool;
    if (body + 8 != n)
        return refuse(4, "text table size does not add up");
    if (TextHash(reinterpret_cast<const char*>(d), static_cast<size_t>(body))
        != Le64(d + body))
        return refuse(5, "text table checksum does not match");

    std::vector<Entry> entries;
    std::vector<char> strings;
    std::vector<size_t> offsets;
    entries.reserve(static_cast<size_t>(count));
    const uint8_t* pool_at = d + kHeader + count * kEntry;
    for (uint64_t i = 0; i < count; ++i) {
        const uint8_t* e = d + kHeader + i * kEntry;
        Entry x = {};
        x.hash = Le64(e);
        x.jp_len = Le32(e + 8);
        const uint32_t off = Le32(e + 12);
        const uint32_t len = Le32(e + 16);
        x.flags = Le32(e + 20);
        if (static_cast<uint64_t>(off) + len > pool || len == 0 || x.jp_len == 0
            || x.jp_len > kMaxText)
            return refuse(6, "a text table entry points outside the table");
        if (x.flags == 0 || (x.flags & ~(kMatchWhole | kMatchName)))
            return refuse(6, "a text table entry has unknown flags");
        if (std::memchr(pool_at + off, 0, len) || std::memchr(pool_at + off, '<', len))
            return refuse(6, "a replacement holds a NUL or a tag");
        if (!entries.empty()) {
            const Entry& p = entries.back();
            if (p.hash > x.hash || (p.hash == x.hash && p.jp_len >= x.jp_len))
                return refuse(7, "text table is not sorted or holds a duplicate");
        }
        offsets.push_back(strings.size());
        strings.insert(strings.end(), pool_at + off, pool_at + off + len);
        strings.push_back('\0');
        entries.push_back(x);
    }

    g_pool.swap(strings);
    g_entries.swap(entries);
    for (size_t i = 0; i < g_entries.size(); ++i)
        g_entries[i].zh = g_pool.data() + offsets[i];
    char s[96];
    std::snprintf(s, sizeof(s), "on: %u strings", static_cast<unsigned>(g_entries.size()));
    SetStatus(s);
    std::snprintf(why, why_len, "%s", s);
    g_on.store(true, std::memory_order_release);
    return 0;
}

int DisplayLoad(const wchar_t* path, char* why, size_t why_len)
{
    if (!path) {
        std::snprintf(why, why_len, "no path for the text table");
        SetStatus("off: no path for the text table");
        return 1;
    }
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (h == INVALID_HANDLE_VALUE) {
        std::snprintf(why, why_len, "text table missing (error %lu)", GetLastError());
        char s[96];
        std::snprintf(s, sizeof(s), "off: %s", why);
        SetStatus(s);
        return 1;
    }
    LARGE_INTEGER size = {};
    std::vector<uint8_t> buf;
    bool ok = GetFileSizeEx(h, &size) && size.QuadPart > 0
              && static_cast<uint64_t>(size.QuadPart) <= kMaxTable;
    if (ok) {
        buf.resize(static_cast<size_t>(size.QuadPart));
        DWORD got = 0;
        ok = ReadFile(h, buf.data(), static_cast<DWORD>(buf.size()), &got, nullptr)
             && got == buf.size();
    }
    CloseHandle(h);
    if (!ok) {
        std::snprintf(why, why_len, "text table could not be read");
        SetStatus("off: text table could not be read");
        return 2;
    }
    return DisplayLoadBytes(buf.data(), buf.size(), why, why_len);
}

const char* DisplayOnSet(void* self, const char* text, std::string& scratch)
{
    if (!text || !g_on.load(std::memory_order_acquire))
        return text;
    const size_t len = BoundedLen(text, kMaxText + 1);
    if (len > kMaxText) {
        g_long.fetch_add(1, std::memory_order_relaxed);
        return text;
    }

    const char* out = text;
    bool whole = false;
    if (const Entry* e = Find(text, len, kMatchWhole)) {
        out = e->zh;
        whole = true;
    } else {
        // Names inside <CLY2>...: a nameplate is exactly that, and the message
        // log carries one per line.  The span runs to the next tag or the end.
        static const char kTag[] = "<CLY2>";
        const size_t tl = sizeof(kTag) - 1;
        size_t last = 0;
        bool any = false;
        for (size_t i = 0; i + tl <= len; ++i) {
            if (std::memcmp(text + i, kTag, tl) != 0)
                continue;
            const size_t j = i + tl;
            size_t k = j;
            while (k < len && text[k] != '<')
                ++k;
            if (const Entry* n = Find(text + j, k - j, kMatchName)) {
                if (!any) {
                    scratch.clear();
                    scratch.reserve(len + 16);
                }
                scratch.append(text + last, j - last);
                scratch.append(n->zh);
                last = k;
                any = true;
            }
            i = k - 1;           // the loop steps past the span
        }
        if (any) {
            scratch.append(text + last, len - last);
            out = scratch.c_str();
        }
    }

    const uintptr_t key = reinterpret_cast<uintptr_t>(self);
    if (out == text) {
        // Not ours.  If this widget was showing our Chinese, it either still is
        // (the widget writing back what it read -- ACUIText slot 24 does that)
        // or it has moved on, and the Japanese we kept no longer applies.
        if (g_guarded.load(std::memory_order_relaxed) == 0)
            return text;
        const uint64_t h = TextHash(text, len);
        Lock();
        if (Guard* g = FindLocked(key))
            if (!(g->disp_hash == h && g->disp_len == len))
                DropLocked(g);
        Unlock();
        return text;
    }

    // Ours.  Remember the Japanese before handing over the Chinese, or do not
    // replace at all.
    const size_t out_len = std::strlen(out);
    char* orig = new (std::nothrow) char[len + 1];
    if (!orig) {
        g_full.fetch_add(1, std::memory_order_relaxed);
        return text;
    }
    std::memcpy(orig, text, len + 1);
    Lock();
    Guard* g = InsertLocked(key);
    if (!g) {
        Unlock();
        delete[] orig;
        g_full.fetch_add(1, std::memory_order_relaxed);
        return text;
    }
    Bury(g->orig);
    g->orig = orig;
    g->disp_hash = TextHash(out, out_len);
    g->disp_len = static_cast<uint32_t>(out_len);
    Unlock();
    (whole ? g_whole : g_names).fetch_add(1, std::memory_order_relaxed);
    return out;
}

const char* DisplayOnGet(void* self, const char* got, const void* caller)
{
    if (!got || !g_on.load(std::memory_order_acquire))
        return got;
    if (g_guarded.load(std::memory_order_relaxed) == 0 || IsUiReader(caller))
        return got;
    const size_t len = BoundedLen(got, kMaxText + 1);
    if (len > kMaxText)
        return got;
    const uint64_t h = TextHash(got, len);
    const char* out = got;
    Lock();
    if (Guard* g = FindLocked(reinterpret_cast<uintptr_t>(self))) {
        if (g->disp_hash == h && g->disp_len == len && g->orig) {
            out = g->orig;
            g_hits.fetch_add(1, std::memory_order_relaxed);
            const uint8_t* c = static_cast<const uint8_t*>(caller);
            const uint32_t rva = (g_base && c >= g_base)
                ? static_cast<uint32_t>(c - g_base) : 0;
            bool known = false;
            for (size_t i = 0; i < g_callers_n; ++i)
                known = known || g_callers[i] == rva;
            if (!known && g_callers_n < kCallers)
                g_callers[g_callers_n++] = rva;
        }
    }
    Unlock();
    return out;
}

DisplayStats DisplayGetStats()
{
    DisplayStats s = {};
    s.on = g_on.load(std::memory_order_acquire);
    s.entries = static_cast<uint32_t>(s.on ? g_entries.size() : 0);
    s.whole = g_whole.load();
    s.names = g_names.load();
    s.guard_hits = g_hits.load();
    s.guard_full = g_full.load();
    s.too_long = g_long.load();
    s.guarded = g_guarded.load();
    std::snprintf(s.status, sizeof(s.status), "%s", g_status);
    return s;
}

size_t DisplayGuardCallers(uint32_t* out, size_t max)
{
    if (!g_lock_ready.load(std::memory_order_acquire))
        return 0;
    Lock();
    size_t n = g_callers_n < max ? g_callers_n : max;
    for (size_t i = 0; i < n; ++i)
        out[i] = g_callers[i];
    Unlock();
    return n;
}

void DisplayResetForTest()
{
    g_on.store(false, std::memory_order_release);
    Lock();
    for (Guard& g : g_guards) {
        delete[] g.orig;
        g = Guard{};
    }
    for (char*& p : g_grave) {
        delete[] p;
        p = nullptr;
    }
    g_grave_next = 0;
    g_callers_n = 0;
    g_guarded.store(0);
    Unlock();
    g_entries.clear();
    g_pool.clear();
    g_whole = 0;
    g_names = 0;
    g_hits = 0;
    g_full = 0;
    g_long = 0;
    SetStatus("off: no table loaded");
}

}  // namespace cielzh
