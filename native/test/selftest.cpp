// Checks on the recorder and the hook mechanics, with no game involved.
//
// A synthetic image stands in for CielnosurgeDX.exe: PE headers, both vtables,
// the thunks, and real code at the implementation addresses.  The getter is
// byte-for-byte the game's, because that function is only 15 bytes and ends in
// ret, so "the getter hands back the game's own pointer" is observed here
// rather than asserted.
//
// What this must NOT do is invent behaviour the game does not have.  An earlier
// version put a working setter at the _purecall address and then "proved" that
// ACText::SetText forwards correctly -- a test describing a path that does not
// exist.  That address now holds an int3, and nothing calls it.
#include <windows.h>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <cstdint>
#include <string>
#include <vector>
#include "../cielzh/version.h"
#include "../cielzh/hooks.h"
#include "../cielzh/trace.h"
#include "../cielzh/entry.h"
#include "../cielzh/display.h"

using namespace cielzh;

namespace {

int g_fail = 0;

void Check(const char* what, bool ok)
{
    std::printf("  %-58s %s\n", what, ok ? "ok" : "FAILED");
    if (!ok)
        ++g_fail;
}

struct FakeText {          // enough of ac::ACSpriteText for the real getter
    void* vtable;
    const char* str;       // +8
    char pad[0x10];
    size_t capacity;       // +0x20
};

uint8_t* g_image = nullptr;

// Inside ACUIText slot 5's range (version.h), past its pinned opening.
constexpr uint32_t kRvaUiReadStub = 0x00962F80;

// The text table, written the way tools/build_text_table.py writes it, so the
// parser is tested against the format rather than against itself.
struct Row {
    std::string jp, zh;
    uint32_t flags;
};

void PutLe32(std::vector<uint8_t>& v, uint32_t x)
{
    for (int i = 0; i < 4; ++i)
        v.push_back(static_cast<uint8_t>(x >> (8 * i)));
}
void PutLe64(std::vector<uint8_t>& v, uint64_t x)
{
    PutLe32(v, static_cast<uint32_t>(x));
    PutLe32(v, static_cast<uint32_t>(x >> 32));
}

std::vector<uint8_t> MakeTable(std::vector<Row> rows, bool sort = true)
{
    if (sort)
        std::sort(rows.begin(), rows.end(), [](const Row& a, const Row& b) {
            uint64_t ha = TextHash(a.jp.data(), a.jp.size());
            uint64_t hb = TextHash(b.jp.data(), b.jp.size());
            return ha != hb ? ha < hb : a.jp.size() < b.jp.size();
        });
    std::vector<uint8_t> pool, t;
    t.insert(t.end(), {'C', 'Z', 'T', '1'});
    PutLe32(t, 1);
    PutLe32(t, static_cast<uint32_t>(rows.size()));
    size_t pool_size = 0;
    for (const Row& r : rows)
        pool_size += r.zh.size();
    PutLe32(t, static_cast<uint32_t>(pool_size));
    for (const Row& r : rows) {
        PutLe64(t, TextHash(r.jp.data(), r.jp.size()));
        PutLe32(t, static_cast<uint32_t>(r.jp.size()));
        PutLe32(t, static_cast<uint32_t>(pool.size()));
        PutLe32(t, static_cast<uint32_t>(r.zh.size()));
        PutLe32(t, r.flags);
        pool.insert(pool.end(), r.zh.begin(), r.zh.end());
    }
    t.insert(t.end(), pool.begin(), pool.end());
    PutLe64(t, TextHash(reinterpret_cast<const char*>(t.data()), t.size()));
    return t;
}

// The checksum is the last eight bytes; after editing a table to make it bad in
// some other way, it is recomputed so the check under test is the one that fires.
void Reseal(std::vector<uint8_t>& t)
{
    t.resize(t.size() - 8);
    PutLe64(t, TextHash(reinterpret_cast<const char*>(t.data()), t.size()));
}

// Where the headers this build checks live, in the synthetic image.
constexpr uint32_t kLfanew = 0x100;
constexpr uint32_t kOptRva = kLfanew + 24;
constexpr uint32_t kLoadCfgRva = 0x2000;

// `bytes` is how much of `img` is actually there.  The load config sits at
// kLoadCfgRva, past the end of a one-page buffer, and writing it there is how
// the "pretends to be 21 MB" test crashed before it could run.
void WriteHeaders(uint8_t* img, size_t bytes = kSizeOfImage)
{
    img[0] = 'M';
    img[1] = 'Z';
    uint32_t lfanew = kLfanew;
    std::memcpy(img + 0x3C, &lfanew, 4);
    std::memcpy(img + kLfanew, "PE\0\0", 4);
    uint16_t machine = kMachineAmd64;
    std::memcpy(img + kLfanew + 4, &machine, 2);
    uint16_t opt_size = 240;                       // enough for 16 directories
    std::memcpy(img + kLfanew + 20, &opt_size, 2);
    uint16_t magic = kOptMagicPe32Plus;
    std::memcpy(img + kOptRva, &magic, 2);
    uint32_t image = kSizeOfImage;
    std::memcpy(img + kOptRva + 56, &image, 4);
    uint16_t dllchar = kDllCharacteristics;
    std::memcpy(img + kOptRva + 70, &dllchar, 2);
    uint32_t dirs = 16;
    std::memcpy(img + kOptRva + 108, &dirs, 4);

    uint32_t lc_rva = kLoadCfgRva, lc_size = kLoadConfigMinSize;
    std::memcpy(img + kOptRva + 112 + kLoadConfigDirIndex * 8, &lc_rva, 4);
    std::memcpy(img + kOptRva + 112 + kLoadConfigDirIndex * 8 + 4, &lc_size, 4);
    if (bytes < kLoadCfgRva + kLoadConfigMinSize)
        return;
    uint32_t self_size = kLoadConfigMinSize;
    std::memcpy(img + kLoadCfgRva, &self_size, 4);
    uint32_t gflags = kGuardFlags;
    std::memcpy(img + kLoadCfgRva + 0x90, &gflags, 4);
    // GuardCFFunctionTable / Count stay zero, as in the shipped build.
}

void PutJmp(uint32_t from, uint32_t to)
{
    uint8_t* p = g_image + from;
    p[0] = 0xE9;
    int32_t rel = static_cast<int32_t>(to) - static_cast<int32_t>(from + 5);
    std::memcpy(p + 1, &rel, 4);
}

void BuildImage()
{
    g_image = static_cast<uint8_t*>(VirtualAlloc(
        nullptr, kSizeOfImage, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
    WriteHeaders(g_image);

    // The getter, whole.
    std::memcpy(g_image + kRvaGetImpl, kBodyGet, sizeof(kBodyGet));

    // The setter: the game's opening bytes, then a body that stores the pointer
    // so a set/get round trip is observable.
    //   ...mov rbx,rcx ; mov [rbx+8],rdx ; add rsp,0x20 ; pop rbx ; ret
    static const uint8_t kSetTail[] = {
        0x48, 0x89, 0x53, 0x08, 0x48, 0x83, 0xC4, 0x20, 0x5B, 0xC3,
    };
    std::memcpy(g_image + kRvaSpriteSetImpl, kPrefixSpriteSet,
                sizeof(kPrefixSpriteSet));
    std::memcpy(g_image + kRvaSpriteSetImpl + sizeof(kPrefixSpriteSet),
                kSetTail, sizeof(kSetTail));

    // _purecall: an abort, and nothing here ever calls it.
    g_image[kRvaPurecallImpl] = 0xCC;

    // The widget system's own readers: their opening bytes, as VerifyModule
    // pins them, and inside the slot-5 range a stub that reads a widget through
    // its vtable -- so a read can arrive with a return address that really is
    // inside the range, through the real hook.
    for (const UiReader& r : kUiReaders)
        std::memcpy(g_image + r.begin, r.prefix, sizeof(r.prefix));
    static const uint8_t kUiReadStub[] = {
        0x48, 0x83, 0xEC, 0x28,    // sub  rsp, 0x28
        0x48, 0x8B, 0x01,          // mov  rax, [rcx]
        0xFF, 0x50, 0x20,          // call [rax+0x20]   (slot 4, the getter)
        0x48, 0x83, 0xC4, 0x28,    // add  rsp, 0x28
        0xC3,                      // ret
    };
    std::memcpy(g_image + kRvaUiReadStub, kUiReadStub, sizeof(kUiReadStub));

    PutJmp(kRvaSpriteSetThunk, kRvaSpriteSetImpl);
    PutJmp(kRvaGetThunk, kRvaGetImpl);
    PutJmp(kRvaPurecallThunk, kRvaPurecallImpl);

    void** sprite = reinterpret_cast<void**>(g_image + kRvaSpriteTextVtable);
    sprite[kSlotSetText] = g_image + kRvaSpriteSetThunk;
    sprite[kSlotGetText] = g_image + kRvaGetThunk;
    void** text = reinterpret_cast<void**>(g_image + kRvaTextVtable);
    text[kSlotSetText] = g_image + kRvaPurecallThunk;   // pure virtual
    text[kSlotGetText] = g_image + kRvaGetThunk;

    // The real vtables live in .rdata.  Leaving these pages RWX, as the rest of
    // the synthetic image is, would make "the page went back to read-only" and
    // "the page was left writable" look identical.
    DWORD old = 0;
    VirtualProtect(sprite, 8 * sizeof(void*), PAGE_READONLY, &old);
    VirtualProtect(text, 8 * sizeof(void*), PAGE_READONLY, &old);
}

DWORD ProtOf(const void* p)
{
    MEMORY_BASIC_INFORMATION mbi = {};
    VirtualQuery(p, &mbi, sizeof(mbi));
    return mbi.Protect;
}

// Writes into a read-only vtable page the way a third party hooking after us
// would, and puts the page back as it found it.
void Poke(void** slot, void* value)
{
    DWORD old = 0;
    VirtualProtect(slot, sizeof(void*), PAGE_READWRITE, &old);
    *slot = value;
    VirtualProtect(slot, sizeof(void*), old, &old);
}

size_t CountSet(const Event* ev, size_t n, const char* want)
{
    size_t k = 0;
    for (size_t i = 0; i < n; ++i)
        if (ev[i].op == Op::kSet && std::strcmp(ev[i].text, want) == 0)
            ++k;
    return k;
}

// --- a VirtualProtect that fails on demand ----------------------------------
// Calls are numbered from 1 after each Arm().  With three slots, an install
// makes them in this order, so a bit picks exactly which step breaks:
//   1 slot0 ->RW   2 slot0 restore   3 slot1 ->RW   4 slot1 restore   ...
// and a rollback continues the numbering from wherever the install stopped.
int g_protect_calls = 0;
uint64_t g_protect_fail_mask = 0;   // bit n: fail call n
int g_protect_fail_from = 0;        // fail this call and every one after it
unsigned long g_protect_fail_want = 0;  // fail calls asking for this value...
uintptr_t g_protect_fail_page = 0;      // ...on this page only (0: any page)
void (*g_protect_callback)() = nullptr; // run at this call number, then carry on
int g_protect_callback_on = 0;

int FlakyProtect_(void* addr, size_t len, unsigned long want, unsigned long* old);

uintptr_t PageOf(const void* p)
{
    return reinterpret_cast<uintptr_t>(p) & ~static_cast<uintptr_t>(0xFFF);
}

void Arm(uint64_t mask, int from, unsigned long want = 0, const void* page = nullptr)
{
    g_protect_calls = 0;
    g_protect_fail_mask = mask;
    g_protect_fail_from = from;
    g_protect_fail_want = want;
    g_protect_fail_page = page ? PageOf(page) : 0;
    SetProtectForTest(&FlakyProtect_);
}

void Disarm()
{
    SetProtectForTest(nullptr);
    g_protect_fail_mask = 0;
    g_protect_fail_from = 0;
    g_protect_fail_want = 0;
    g_protect_fail_page = 0;
    g_protect_callback = nullptr;
    g_protect_callback_on = 0;
}

int FlakyProtect_(void* addr, size_t len, unsigned long want, unsigned long* old)
{
    ++g_protect_calls;
    if (g_protect_callback && g_protect_calls == g_protect_callback_on) {
        DWORD o = 0;
        BOOL r = VirtualProtect(addr, len, want, &o);   // do the real call first
        if (old)
            *old = o;
        g_protect_callback();                           // then change the slot
        return r ? 1 : 0;
    }
    if (g_protect_calls < 64 && (g_protect_fail_mask >> g_protect_calls) & 1)
        return 0;
    if (g_protect_fail_from && g_protect_calls >= g_protect_fail_from)
        return 0;
    if (g_protect_fail_want && want == g_protect_fail_want
        && (!g_protect_fail_page || PageOf(addr) == g_protect_fail_page))
        return 0;
    DWORD o = 0;
    BOOL r = VirtualProtect(addr, len, want, &o);
    if (old)
        *old = o;
    return r ? 1 : 0;
}

// --- a shared-content record from another thread -----------------------------
void* g_fake_obj = reinterpret_cast<void*>(static_cast<uintptr_t>(0xABCD0000));
void* g_fake_caller = reinterpret_cast<void*>(static_cast<uintptr_t>(0x41414141));
const char* g_shared = "same content";

bool FileThere(const wchar_t* path)
{
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

bool Slurp(const wchar_t* path, char* out, size_t cap)
{
    out[0] = '\0';
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                           nullptr, OPEN_EXISTING, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE)
        return false;
    DWORD got = 0;
    BOOL ok = ReadFile(h, out, static_cast<DWORD>(cap - 1), &got, nullptr);
    CloseHandle(h);
    out[got] = '\0';
    return ok != FALSE;
}

// A path that cannot fit in the recorder's buffer, to check that too long is
// refused rather than cut down to something that would be written to.
wchar_t g_long_path[4096];
struct MakeLongPath {
    MakeLongPath()
    {
        for (size_t i = 0; i < 4095; ++i)
            g_long_path[i] = L'x';
        g_long_path[4095] = L'\0';
    }
} g_make_long_path;

// Holds the recorder's lock until told to let go, so the exit dump's "give up
// rather than hang" can be checked.
HANDLE g_locked = CreateEventW(nullptr, TRUE, FALSE, nullptr);
HANDLE g_release = CreateEventW(nullptr, TRUE, FALSE, nullptr);

DWORD WINAPI LockHolder(LPVOID)
{
    TraceLockForTest();
    SetEvent(g_locked);
    WaitForSingleObject(g_release, 10000);
    TraceUnlockForTest();
    return 0;
}

// Two of these run at once against the display layer, each on its own widgets:
// the game sets text from the main thread and from a background thread.
struct Hammer {
    uintptr_t base;
    const char* key;
    const char* other;
    void* caller;
    int bad;
};

DWORD WINAPI DisplayHammer(LPVOID arg)
{
    Hammer* h = static_cast<Hammer*>(arg);
    std::string scratch;
    for (int i = 0; i < 20000; ++i) {
        void* self = reinterpret_cast<void*>(h->base + (i % 64) * 64);
        const char* out = DisplayOnSet(self, (i & 1) ? h->other : h->key, scratch);
        if ((i & 1) == 0) {
            const char* back = DisplayOnGet(self, out, h->caller);
            if (out != h->key && std::strcmp(back, h->key) != 0)
                ++h->bad;   // a replaced text must read back as the Japanese
        }
    }
    return 0;
}

DWORD WINAPI OtherThread(LPVOID)
{
    TraceRecord(Op::kSet, Klass::kSpriteText, g_fake_obj, g_fake_caller, g_shared);
    return 0;
}

// --- probes that run from inside an install ---------------------------------
int g_probe_hits = 0;
int g_probe_init_rc = -1;
int g_probe_shutdown_rc = -1;
State g_probe_state = State::kIdle;

void MidInstallProbe()
{
    ++g_probe_hits;
    g_probe_state = CurrentState();
    char w[256];
    g_probe_init_rc = InitializeAt(g_image, kSizeOfImage, w, sizeof(w));
    g_probe_shutdown_rc = ShutdownAll(w, sizeof(w));
}

void** g_hijack_slot = nullptr;
void* g_hijack_with = nullptr;

// Writes into a page the caller has already made writable.
void HijackNow()
{
    DWORD old = 0;
    VirtualProtect(g_hijack_slot, sizeof(void*), PAGE_READWRITE, &old);
    *g_hijack_slot = g_hijack_with;
    VirtualProtect(g_hijack_slot, sizeof(void*), old, &old);
}

// Calls through a slot that IS installed while the install as a whole is not
// finished -- the half-installed window a background thread can walk into.
void** g_early_slot = nullptr;
void* g_early_self = nullptr;
const char* g_early_text = "early";
unsigned long g_early_before = 0;
unsigned long g_early_after = 0;
size_t g_early_events_before = 0;
size_t g_early_events_after = 0;

void CallWhileInstalling()
{
    static Event ev[256];
    g_early_before = HooksEarlyCalls();
    g_early_events_before = TraceDrain(ev, 256);
    reinterpret_cast<void(*)(void*, const char*)>(*g_early_slot)(
        g_early_self, g_early_text);
    g_early_after = HooksEarlyCalls();
    g_early_events_after = TraceDrain(ev, 256);
}

}  // namespace

int main(int argc, char** argv)
{
    // Unbuffered: a crash used to take the whole log with it, leaving an exit
    // code and no idea which check was running.
    setvbuf(stdout, nullptr, _IONBF, 0);

    // selftest.exe --load-table <cielzh-text.bin>
    //
    // Reads a table tools/build_text_table.py wrote, with the DLL's own parser.
    // The two sides share a format and a hash and check the same known answers,
    // but only this shows that a real table from a real build is accepted.
    if (argc == 3 && std::strcmp(argv[1], "--load-table") == 0) {
        wchar_t path[MAX_PATH];
        MultiByteToWideChar(CP_ACP, 0, argv[2], -1, path, MAX_PATH);
        char lwhy[160];
        const int rc = DisplayLoad(path, lwhy, sizeof(lwhy));
        std::printf("rc=%d  %s\n", rc, DisplayGetStats().status);
        return rc;
    }

    char why[256];
    BuildImage();

    // --- verification -------------------------------------------------------
    Check("合成映像通过校验", VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    Check("空指针被拒绝", !VerifyModule(nullptr, 16, why, sizeof(why)));

    uint8_t tiny[8] = { 'M', 'Z', 0, 0, 0, 0, 0, 0 };
    Check("过小的缓冲区被拒绝", !VerifyModule(tiny, sizeof(tiny), why, sizeof(why)));

    // One page that looks like a 21 MB image.  Believing SizeOfImage here is a
    // read 13 MB past the end of the allocation.
    uint8_t* liar = static_cast<uint8_t*>(
        VirtualAlloc(nullptr, 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    WriteHeaders(liar, 0x1000);
    uint16_t m64 = kMachineAmd64;
    Check("一页缓冲区谎称 21MB 映像被拒绝（size 是硬边界）",
          !VerifyModule(liar, 0x1000, why, sizeof(why)));
    Check("同一缓冲区在 size=0 时也被拒绝（逐区间查询）",
          !VerifyModule(liar, 0, why, sizeof(why)));
    VirtualFree(liar, 0, MEM_RELEASE);

    g_image[0] = 'X';
    Check("非 PE 被拒绝", !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    g_image[0] = 'M';
    uint16_t x86 = 0x014C;
    std::memcpy(g_image + kLfanew + 4, &x86, 2);
    Check("架构不符被拒绝", !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    std::memcpy(g_image + kLfanew + 4, &m64, 2);

    // --- CFG: the slots and function bytes stay untouched throughout --------
    uint16_t guarded = kDllCharacteristics | kDllCharGuardCf;
    std::memcpy(g_image + kOptRva + 70, &guarded, 2);
    Check("GUARD_CF 置位后被拒绝（槽位与函数字节未动）",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    uint16_t dllchar = kDllCharacteristics;
    std::memcpy(g_image + kOptRva + 70, &dllchar, 2);

    uint32_t gflags2 = kGuardFlags | 0x400;   // CF_FUNCTION_TABLE_PRESENT
    std::memcpy(g_image + kLoadCfgRva + 0x90, &gflags2, 4);
    Check("GuardFlags 变化后被拒绝",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    uint32_t gflags = kGuardFlags;
    std::memcpy(g_image + kLoadCfgRva + 0x90, &gflags, 4);

    uint64_t table = 0x1000;
    std::memcpy(g_image + kLoadCfgRva + 0x80, &table, 8);
    Check("GFID 函数表非空后被拒绝",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    uint64_t zero = 0;
    std::memcpy(g_image + kLoadCfgRva + 0x80, &zero, 8);

    uint16_t bad_magic = 0x010B;               // PE32, not PE32+
    std::memcpy(g_image + kOptRva, &bad_magic, 2);
    Check("Optional Header 不是 PE32+ 被拒绝",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    uint16_t magic = kOptMagicPe32Plus;
    std::memcpy(g_image + kOptRva, &magic, 2);

    uint32_t few = kLoadConfigDirIndex;         // one short of what we index
    std::memcpy(g_image + kOptRva + 108, &few, 4);
    Check("数据目录数量不足被拒绝（不越界读）",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    uint32_t dirs = 16;
    std::memcpy(g_image + kOptRva + 108, &dirs, 4);

    uint32_t no_lc = 0;
    std::memcpy(g_image + kOptRva + 112 + kLoadConfigDirIndex * 8, &no_lc, 4);
    Check("缺少 Load Config 被拒绝",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    uint32_t lc_rva = kLoadCfgRva;
    std::memcpy(g_image + kOptRva + 112 + kLoadConfigDirIndex * 8, &lc_rva, 4);
    Check("CFG 字段复原后重新通过",
          VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));

    PutJmp(kRvaGetThunk, kRvaGetImpl + 1);
    Check("跳板目标改变被拒绝（仅查槽位会放过）",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    PutJmp(kRvaGetThunk, kRvaGetImpl);

    PutJmp(kRvaPurecallThunk, kRvaSpriteSetImpl);
    Check("_purecall 跳板改变被拒绝",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    PutJmp(kRvaPurecallThunk, kRvaPurecallImpl);

    g_image[kRvaSpriteSetImpl + 3] ^= 0xFF;
    Check("实现首字节改变被拒绝",
          !VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));
    g_image[kRvaSpriteSetImpl + 3] ^= 0xFF;
    Check("恢复后重新通过", VerifyModule(g_image, kSizeOfImage, why, sizeof(why)));

    // --- a failed install must leave nothing behind -------------------------
    TraceInit(g_image);
    void** sprite = reinterpret_cast<void**>(g_image + kRvaSpriteTextVtable);
    void** text = reinterpret_cast<void**>(g_image + kRvaTextVtable);
    void* orig_sprite_set = sprite[kSlotSetText];
    void* orig_sprite_get = sprite[kSlotGetText];
    void* orig_text_get = text[kSlotGetText];
    void* orig_text_set = text[kSlotSetText];

    const DWORD ro = ProtOf(&sprite[kSlotSetText]);
    Check("合成虚表页为只读（与真实 .rdata 一致）", ro == PAGE_READONLY);

    auto untouched = [&]() {
        return sprite[kSlotSetText] == orig_sprite_set
            && sprite[kSlotGetText] == orig_sprite_get
            && text[kSlotGetText] == orig_text_get
            && ProtOf(&sprite[kSlotSetText]) == ro
            && ProtOf(&text[kSlotGetText]) == ro;
    };

    // (a) The very first VirtualProtect fails.  Nothing was changed, so there
    // is nothing to undo -- but a record that stores "original protection = 0"
    // and then tries to restore 0 can never be cleaned up.
    Arm(1ull << 1, 0);
    Check("首个槽首次改保护失败：安装被判失败",
          !InstallTraceHooks(g_image, why, sizeof(why)));
    Disarm();
    Check("  ……随后回滚可以完成（无须恢复从未改过的保护）",
          RemoveTraceHooks(why, sizeof(why)));
    Check("  ……虚表与页保护都未改变", untouched() && !HooksTouched());

    // (b) The same, on a later slot: slot 0 was fully installed first.
    Arm(1ull << 3, 0);
    Check("后续槽首次改保护失败：安装被判失败",
          !InstallTraceHooks(g_image, why, sizeof(why)));
    Disarm();
    Check("  ……随后回滚可以完成", RemoveTraceHooks(why, sizeof(why)));
    Check("  ……已装好的前一个槽被还原，页保护仍为只读",
          untouched() && !HooksTouched());

    // (c) The restore after writing fails once; the rollback inside Install can
    // still finish.
    Arm(1ull << 2, 0);
    Check("写槽后恢复页保护失败：安装被判失败",
          !InstallTraceHooks(g_image, why, sizeof(why)));
    Disarm();
    Check("  ……回滚已在安装内完成，虚表无残留", untouched() && !HooksTouched());

    // (d) VirtualProtect stays broken, so the rollback cannot finish.  This is
    // the state the loader must not read as "safe to unload".
    Arm(0, 2);
    Check("回滚无法完成时安装失败",
          !InstallTraceHooks(g_image, why, sizeof(why)));
    Check("  ……HooksTouched 保持为真（不得卸载）", HooksTouched());
    Disarm();
    Check("  ……恢复后重试回滚成功", RemoveTraceHooks(why, sizeof(why)));
    Check("  ……槽与页保护都已还原", untouched() && !HooksTouched());

    // (e) Pointer back, page still writable, then a second install.  The old
    // code wiped its records and read the page's CURRENT protection -- writable
    // -- as the original, so the read-only state was lost for good.
    //   call 1 slot0 ->RW   2 restore FAILS   3 rollback ->RW   4 rollback restore FAILS
    Arm((1ull << 2) | (1ull << 4), 0);
    Check("制造「指针已还原、页仍可写」：安装失败",
          !InstallTraceHooks(g_image, why, sizeof(why)));
    Check("  ……确实处于该状态",
          sprite[kSlotSetText] == orig_sprite_set
          && ProtOf(&sprite[kSlotSetText]) == PAGE_READWRITE
          && HooksTouched());
    // Only "put the SPRITE page back to read-only" is broken.  With the guard,
    // the pending cleanup stops there and the install is refused.  Without it,
    // a fresh install succeeds -- it reads that page as RW and "restores" RW,
    // and the ACText page, still read-only, restores fine -- and the read-only
    // value is gone.  Two earlier versions of this check failed every call, or
    // every restore to read-only on any page; both made the unguarded install
    // fail too, so the check passed on the very code it was meant to catch.
    Arm(0, 0, PAGE_READONLY, &sprite[kSlotSetText]);
    Check("  ……底层再次安装被拒绝，不覆盖旧记录",
          !InstallTraceHooks(g_image, why, sizeof(why)) && HooksTouched()
          && sprite[kSlotSetText] == orig_sprite_set);
    Disarm();
    Check("  ……修好后底层安装先续做清理再装",
          InstallTraceHooks(g_image, why, sizeof(why)));
    Check("  ……卸载后页保护回到只读，而非可写",
          RemoveTraceHooks(why, sizeof(why)) && untouched());

    // (f) The same through the public entry, which the self-test used to skip.
    // First attempt, rollback could not finish: 5 on that very call.  The
    // loader must not be told "clean" because it is the first failure.
    Arm((1ull << 2) | (1ull << 4), 0);
    Check("公开入口：首次失败且回滚未完成即返回 5（dirty）",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 5
          && CurrentState() == State::kCleanupPending && HooksTouched());
    Arm(0, 0, PAGE_READONLY, &sprite[kSlotSetText]);
    Check("公开入口：清理未完成时再次初始化被拒绝（返回 5）",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 5
          && !IsReady() && HooksTouched());
    Disarm();
    Check("公开入口：修好后再次初始化成功",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 0 && IsReady());
    Check("公开入口：重复初始化是明确的空操作",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 0 && IsReady());
    Check("公开入口：Shutdown 后槽与页保护都已还原",
          ShutdownAll(why, sizeof(why)) == 0 && !IsReady() && untouched());
    Check("公开入口：未写入任何东西时 Shutdown 是空操作",
          ShutdownAll(why, sizeof(why)) == 0);

    // (g) Initialisation failed but something was written: Shutdown must not
    // report "nothing to do".
    Arm(0, 2);
    InitializeAt(g_image, kSizeOfImage, why, sizeof(why));
    Check("初始化失败且有写入时，Shutdown 不报告成功",
          ShutdownAll(why, sizeof(why)) != 0 && HooksTouched());
    Check("  ……此时状态为「清理未完成」",
          CurrentState() == State::kCleanupPending);
    Disarm();
    Check("  ……修好后 Shutdown 完成清理",
          ShutdownAll(why, sizeof(why)) == 0 && untouched()
          && CurrentState() == State::kIdle);

    // (h) Re-entry while an install is in progress.  The stage-one log found
    // the first text traffic on a background thread that did not exist at the
    // install point, so "one caller, one thread" is not something to assume.
    // The probe runs from inside the install, after the trace table is up and
    // before the first slot is written.
    g_probe_hits = 0;
    SetReentryForTest(&MidInstallProbe);
    Check("安装过程中状态为 kBusy 且拒绝重入（返回 6）",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 0
          && g_probe_hits == 1
          && g_probe_init_rc == 6 && g_probe_shutdown_rc == 6
          && g_probe_state == State::kBusy);
    SetReentryForTest(nullptr);
    Check("安装完成后状态为 kReady 且钩子已 armed",
          CurrentState() == State::kReady && HooksArmed());
    Check("重复初始化返回成功且不重装",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 0
          && HooksArmed());
    Check("Shutdown 后 armed 归假",
          ShutdownAll(why, sizeof(why)) == 0 && !HooksArmed() && untouched());

    // (i) A slot that changes between "read the original" and "write the hook"
    // must not be overwritten.  The window is exactly that, so the change has
    // to land inside the VirtualProtect for that slot -- doing it any earlier
    // and the install would simply read the new value as the original.
    // Call 5 is slot 2 (ACText::GetText) going writable.
    g_hijack_slot = &text[kSlotGetText];
    g_hijack_with = reinterpret_cast<void*>(&main);
    Arm(0, 0);
    g_protect_callback = &HijackNow;
    g_protect_callback_on = 5;
    // Here the rollback DOES finish, so the same failure reports 4, not 5.
    Check("安装中槽位被他人改写时不覆盖，回滚完成则返回 4",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 4
          && !HooksTouched());
    Disarm();
    Check("  ……被他人改写的槽保持对方的值",
          text[kSlotGetText] == reinterpret_cast<void*>(&main));
    Check("  ……未 armed", !HooksArmed());
    Poke(&text[kSlotGetText], orig_text_get);
    Check("  ……归还后可完成清理",
          ShutdownAll(why, sizeof(why)) == 0 && untouched());

    // (j) A call arriving through an already-installed slot while the rest of
    // the install is still running: forward it, do not record it, count it.
    // Recording from a half-installed state would be a sample whose conditions
    // we cannot describe.
    FakeText early = {};
    early.vtable = sprite;
    early.capacity = 0x20;
    g_early_slot = &sprite[kSlotSetText];
    g_early_self = &early;
    Arm(0, 0);
    g_protect_callback = &CallWhileInstalling;
    g_protect_callback_on = 5;          // slot 0 and 1 are in, slot 2 is not
    Check("安装未完成时通过已装槽的调用仍被转发",
          InitializeAt(g_image, kSizeOfImage, why, sizeof(why)) == 0
          && early.str == g_early_text);
    Disarm();
    Check("  ……该调用未被记录，但被计入 early",
          g_early_after == g_early_before + 1
          && g_early_events_after == g_early_events_before);
    Check("  ……安装完成后同一控件的调用会被记录", HooksArmed());
    Check("Shutdown 清理 (j)", ShutdownAll(why, sizeof(why)) == 0 && untouched());

    // --- install, call, remove ---------------------------------------------
    Check("安装钩子", InstallTraceHooks(g_image, why, sizeof(why)));
    Check("ACSpriteText 两槽与 ACText 读取槽被替换",
          sprite[kSlotSetText] != orig_sprite_set
          && sprite[kSlotGetText] != orig_sprite_get
          && text[kSlotGetText] != orig_text_get);
    Check("ACText 槽 2 未被挂钩（纯虚，通往 _purecall）",
          text[kSlotSetText] == orig_text_set);

    using SetFn = void(*)(void*, const char*);
    using GetFn = const char*(*)(void*);

    FakeText w = {};
    w.vtable = sprite;
    w.capacity = 0x20;

    const char* kNero = "\xE3\x83\x8D\xE3\x83\xAD";               // ネロ
    const char* kQ = "\xEF\xBC\x9F\xEF\xBC\x9F\xEF\xBC\x9F";      // ？？？
    const char* kUru = "\xE3\x82\xA6\xE3\x83\xAB";                // ウル

    SetFn set = reinterpret_cast<SetFn>(sprite[kSlotSetText]);
    GetFn get = reinterpret_cast<GetFn>(sprite[kSlotGetText]);

    Check("安装完成后 armed 为真", HooksArmed());
    set(&w, kNero);
    Check("读取钩子原样返回原指针", get(&w) == kNero);

    set(&w, kQ);
    // One call site, twice: two separate statements would be two callers.
    for (int i = 0; i < 2; ++i)
        set(&w, kUru);

    Event ev[128];
    size_t n = TraceDrain(ev, 128);
    Check("同一控件的文字变化各自成条（ネロ/？？？/ウル）",
          CountSet(ev, n, kNero) == 1 && CountSet(ev, n, kQ) == 1
          && CountSet(ev, n, kUru) == 1);
    size_t folded = 0;
    for (size_t i = 0; i < n; ++i)
        if (ev[i].op == Op::kSet && std::strcmp(ev[i].text, kUru) == 0)
            folded = ev[i].hits;
    Check("内容相同的重复只累计次数", folded == 2);

    // --- long text sharing a prefix -----------------------------------------
    char longa[200], longb[200];
    std::memset(longa, 'a', sizeof(longa));
    std::memcpy(longb, longa, sizeof(longb));
    longa[sizeof(longa) - 1] = '\0';
    longb[sizeof(longb) - 1] = '\0';
    longb[150] = 'b';          // differs only past the snapshot
    TraceRecord(Op::kSet, Klass::kSpriteText, &w, g_fake_caller, longa);
    TraceRecord(Op::kSet, Klass::kSpriteText, &w, g_fake_caller, longb);
    n = TraceDrain(ev, 128);
    size_t trunc = 0;
    for (size_t i = 0; i < n; ++i)
        if (ev[i].truncated)
            ++trunc;
    Check("同前缀的长文本不被当作同一条", trunc == 2);

    // The same long text, over and over -- what the first real run did with a
    // log window redrawing a long line every frame.  Never folding truncated
    // records filled one probe chain with copies of it and then counted every
    // further call as dropped, with the table a third full.
    TraceStats st0 = TraceGetStats();
    for (int k = 0; k < 200; ++k)
        TraceRecord(Op::kSet, Klass::kSpriteText, &w, g_fake_caller, longa);
    TraceStats st1 = TraceGetStats();
    n = TraceDrain(ev, 128);
    uint32_t longa_hits = 0;
    size_t longa_rows = 0;
    for (size_t i = 0; i < n; ++i)
        if (ev[i].truncated && std::strncmp(ev[i].text, longa, 40) == 0) {
            // longa and longb share the snapshot (two rows); longa is the one
            // that was repeated, so it is the one with the large count
            if (ev[i].hits > longa_hits)
                longa_hits = ev[i].hits;
            ++longa_rows;
        }
    Check("同一段长文本反复出现：折叠成一条，次数照计",
          longa_rows == 2 && longa_hits == 201);
    Check("  ……不占满探测链，不记作丢弃",
          st1.dropped == st0.dropped && st1.events == st0.events);

    // A multi-byte character must not be cut in half.
    char wide[300];
    for (size_t i = 0; i + 3 <= sizeof(wide); i += 3)
        std::memcpy(wide + i, "\xE3\x83\x8D", 3);   // ネ, over and over
    wide[sizeof(wide) - 1] = '\0';
    TraceRecord(Op::kSet, Klass::kSpriteText, &w, g_fake_caller, wide);
    n = TraceDrain(ev, 128);
    bool clean_cut = true;
    for (size_t i = 0; i < n; ++i) {
        const char* t = ev[i].text;
        size_t len = std::strlen(t);
        if (len >= 3 && std::memcmp(t, "\xE3\x83\x8D", 3) == 0 && len % 3 != 0)
            clean_cut = false;
    }
    Check("截断落在 UTF-8 字符边界上", clean_cut);

    // --- another thread, same everything else -------------------------------
    TraceRecord(Op::kSet, Klass::kSpriteText, g_fake_obj, g_fake_caller, g_shared);
    HANDLE th = CreateThread(nullptr, 0, &OtherThread, nullptr, 0, nullptr);
    WaitForSingleObject(th, INFINITE);
    CloseHandle(th);
    n = TraceDrain(ev, 128);
    size_t shared_rows = 0;
    DWORD seen_thread = 0;
    bool two_threads = false;
    for (size_t i = 0; i < n; ++i) {
        if (std::strcmp(ev[i].text, g_shared) != 0)
            continue;
        ++shared_rows;
        if (seen_thread && seen_thread != ev[i].thread)
            two_threads = true;
        seen_thread = ev[i].thread;
    }
    Check("另一线程的相同内容不被并进同一条", shared_rows == 2 && two_threads);

    // --- dump ---------------------------------------------------------------
    TraceSetEntry(Entry::kSelfTest);
    set(&w, "say \"hi\"\nthen more");
    Check("写入失败被如实报告", TraceDump(L"Z:\\nope\\trace.csv") != 0);

    wchar_t tmp[MAX_PATH], path[MAX_PATH];
    GetTempPathW(MAX_PATH, tmp);
    swprintf_s(path, MAX_PATH, L"%scielzh_selftest.csv", tmp);
    Check("导出成功", TraceDump(path) == 0);

    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr,
                           OPEN_EXISTING, 0, nullptr);
    static char csv[1 << 18];
    DWORD got = 0;
    if (h != INVALID_HANDLE_VALUE) {
        ReadFile(h, csv, sizeof(csv) - 1, &got, nullptr);
        CloseHandle(h);
    }
    csv[got] = '\0';
    Check("CSV 中的双引号被转义", std::strstr(csv, "say \"\"hi\"\"") != nullptr);
    Check("文字中的换行不会拆成两行", std::strstr(csv, "hi\"\"\nthen") == nullptr);
    Check("统计行记录了丢弃数", std::strstr(csv, "dropped=") != nullptr);
    Check("CSV 含 truncated 列", std::strstr(csv, ",truncated,text") != nullptr);
    Check("统计行记录了 entry / armed / early_calls",
          std::strstr(csv, "entry=selftest") != nullptr
          && std::strstr(csv, "armed=") != nullptr
          && std::strstr(csv, "early_calls=") != nullptr);
    Check("统计行包含显示层的状态与读回计数",
          std::strstr(csv, "# display=") != nullptr
          && std::strstr(csv, "guard_hits=") != nullptr
          && std::strstr(csv, "# guard_callers=") != nullptr);
    Check("统计行说明这次是谁写的，以及自动导出是否开着",
          std::strstr(csv, "reason=export") != nullptr
          && std::strstr(csv, "auto=off") != nullptr);
    DeleteFileW(path);

    // --- writing itself out without being asked -----------------------------
    // A recorder nothing reads is no evidence, and the run that matters most is
    // the one that ends in a crash, where a dump written only at exit is empty.
    wchar_t apath[MAX_PATH];
    swprintf_s(apath, MAX_PATH, L"%scielzh_selftest_auto.csv", tmp);
    DeleteFileW(apath);

    Check("未开启自动导出时，新记录不会写文件",
          !TraceAutoDumpInfo().on
          && (set(&w, "auto: nothing yet"), !FileThere(apath)));

    Check("开启自动导出", TraceAutoDump(apath, 1, 0) == 0
          && TraceAutoDumpInfo().on);
    set(&w, "auto: first new record");
    Check("  ……一条新记录就写出来了",
          FileThere(apath) && TraceAutoDumpInfo().writes == 1);
    Check("  ……文件里就有这条记录，并注明是自动写的",
          Slurp(apath, csv, sizeof(csv))
          && std::strstr(csv, "auto: first new record") != nullptr
          && std::strstr(csv, "reason=auto") != nullptr
          && std::strstr(csv, "auto=on") != nullptr);

    // Through TraceRecord, not through set(): the caller address is part of the
    // key, and two set() statements are two call sites, so they are two records
    // however identical the text is.  What is being checked here is that a
    // genuinely folded repeat does not write, which is a recorder question.
    const char* kFolded = "auto: a genuinely identical repeat";
    TraceRecord(Op::kSet, Klass::kSpriteText, g_fake_obj, g_fake_caller, kFolded);
    uint32_t before_writes = TraceAutoDumpInfo().writes;
    TraceRecord(Op::kSet, Klass::kSpriteText, g_fake_obj, g_fake_caller, kFolded);
    Check("重复的同一条不再触发写出",
          TraceAutoDumpInfo().writes == before_writes && before_writes >= 2);

    Check("按条数节流：不足条数不写", TraceAutoDump(apath, 3, 0) == 0
          && (DeleteFileW(apath), set(&w, "auto: one of three"),
              set(&w, "auto: two of three"), !FileThere(apath)));
    set(&w, "auto: three of three");
    Check("  ……凑满条数才写", FileThere(apath));

    // The gap is measured in real time, so this only checks the direction: a
    // second burst inside a long gap must not write again.
    TraceAutoDump(apath, 1, 60000);
    set(&w, "auto: right after arming");        // g_auto_last == 0, so it writes
    before_writes = TraceAutoDumpInfo().writes;
    set(&w, "auto: inside the gap");
    Check("时间间隔内不重复写出",
          TraceAutoDumpInfo().writes == before_writes);

    Check("写不进去时记为失败，并且不留下文件",
          TraceAutoDump(L"Z:\\nope\\auto.csv", 1, 0) == 0
          && (before_writes = TraceAutoDumpInfo().failures,
              set(&w, "auto: nowhere to write"),
              TraceAutoDumpInfo().failures == before_writes + 1)
          && !FileThere(L"Z:\\nope\\auto.csv"));

    Check("路径过长：拒绝开启，而不是截断",
          TraceAutoDump(g_long_path, 1, 0) == 2);

    // --- the exit dump must never wait for the lock -------------------------
    // At exit the other threads are already gone; one of them may have been
    // holding the lock when it was killed, and that lock is never released.
    TraceAutoDump(nullptr, 0, 0);
    HANDLE holder = CreateThread(nullptr, 0, &LockHolder, nullptr, 0, nullptr);
    WaitForSingleObject(g_locked, 5000);
    DWORD t0 = GetTickCount();
    int nowait = TraceDumpNoWait(path);
    DWORD spent = GetTickCount() - t0;
    SetEvent(g_release);
    WaitForSingleObject(holder, 5000);
    CloseHandle(holder);
    Check("锁被别的线程持有时，退出导出立刻放弃而不是挂住",
          nowait != 0 && spent < 2000);
    Check("  ……而普通导出仍然可以写出", TraceDump(path) == 0);
    DeleteFileW(path);
    DeleteFileW(apath);

    // --- the path beside the module ----------------------------------------
    wchar_t beside[MAX_PATH], mine[MAX_PATH];
    GetModuleFileNameW(nullptr, mine, MAX_PATH);
    size_t cut = 0;
    for (size_t i = 0; mine[i]; ++i)
        if (mine[i] == L'\\')
            cut = i + 1;
    mine[cut] = L'\0';
    Check("记录写在主程序旁边",
          PathBesideModule(nullptr, kTraceFileName, beside, MAX_PATH)
          && std::wcsncmp(beside, mine, cut) == 0
          && std::wcscmp(beside + cut, kTraceFileName) == 0);
    Check("放不下就拒绝，并且不留下半个路径",
          !PathBesideModule(nullptr, kTraceFileName, beside, cut + 2)
          && beside[0] == L'\0');
    Check("容量为 0 或没有名字时同样拒绝",
          !PathBesideModule(nullptr, kTraceFileName, beside, 0)
          && !PathBesideModule(nullptr, nullptr, beside, MAX_PATH));

    // --- the display layer --------------------------------------------------
    // The hash has to match tools/build_text_table.py byte for byte; both sides
    // check the same published FNV-1a 64 answers.
    Check("文字摘要与 FNV-1a 64 的标准答案一致",
          TextHash("", 0) == 0xCBF29CE484222325ull
          && TextHash("a", 1) == 0xAF63DC4C8601EC8Cull
          && TextHash("foobar", 6) == 0x85944171F73967E8ull);

    const std::string kIon = "\xE3\x82\xA4\xE3\x82\xAA\xE3\x83\xB3";          // イオン
    const std::string kIonZh = "\xE4\xBE\x9D\xE6\x81\xA9";                    // 依恩
    const std::string kTitle = "\xE3\x80\x90\xE3\x82\xA2\xE3\x82\xA4\xE3\x83\x86"
                               "\xE3\x83\xA0\xE3\x80\x91";                    // 【アイテム】
    const std::string kTitleZh = "\xE3\x80\x90\xE9\x81\x93\xE5\x85\xB7\xE3\x80\x91"; // 【道具】
    const std::string kSave = "\xE3\x82\xBB\xE3\x83\xBC\xE3\x83\x96";          // セーブ
    const std::string kSaveZh = "\xE5\xAD\x98\xE6\xA1\xA3";                    // 存档
    const std::vector<Row> rows = {
        { kIon, kIonZh, kMatchWhole | kMatchName },     // a speaker: both
        { kTitle, kTitleZh, kMatchWhole | kMatchName },
        { kSave, kSaveZh, kMatchWhole },                // kept in the exe: whole only
    };
    char dwhy[160];
    DisplayInit(g_image);

    // A table that does not hold together is refused whole, and leaves the
    // display layer off: the text goes through untouched.
    struct Bad { const char* what; void (*spoil)(std::vector<uint8_t>&); };
    const Bad bads[] = {
        { "坏的魔数", [](std::vector<uint8_t>& t) { t[0] = 'X'; } },
        { "版本不认识", [](std::vector<uint8_t>& t) { t[4] = 2; Reseal(t); } },
        { "长度对不上", [](std::vector<uint8_t>& t) { t.push_back(0); } },
        { "校验和不符", [](std::vector<uint8_t>& t) { t[t.size() - 9] ^= 1; } },
        { "条目指到表外", [](std::vector<uint8_t>& t) { t[16 + 12] = 0xFF; Reseal(t); } },
        { "未知标志", [](std::vector<uint8_t>& t) { t[16 + 20] = 8; Reseal(t); } },
    };
    for (const Bad& b : bads) {
        DisplayResetForTest();
        std::vector<uint8_t> t = MakeTable(rows);
        b.spoil(t);
        std::string sc;
        char what[96];
        std::snprintf(what, sizeof(what), "替换表%s：拒绝，替换保持关闭", b.what);
        Check(what, DisplayLoadBytes(t.data(), t.size(), dwhy, sizeof(dwhy)) != 0
                    && !DisplayGetStats().on
                    && DisplayOnSet(&w, kIon.c_str(), sc) == kIon.c_str());
    }
    DisplayResetForTest();
    {
        std::vector<Row> twice = rows;
        twice.push_back(rows[0]);
        std::vector<uint8_t> t = MakeTable(twice);
        Check("替换表含重复条目：拒绝",
              DisplayLoadBytes(t.data(), t.size(), dwhy, sizeof(dwhy)) != 0);
        DisplayResetForTest();
        std::vector<Row> rev = rows;
        std::sort(rev.begin(), rev.end(), [](const Row& a, const Row& b) {
            return TextHash(a.jp.data(), a.jp.size()) > TextHash(b.jp.data(), b.jp.size());
        });
        t = MakeTable(rev, false);
        Check("替换表未排序：拒绝",
              DisplayLoadBytes(t.data(), t.size(), dwhy, sizeof(dwhy)) != 0);
        DisplayResetForTest();
        std::vector<Row> tag = { { kIon, "<CLBU>x", kMatchWhole } };
        t = MakeTable(tag);
        Check("译文里带标签：拒绝（不许借替换插入标签）",
              DisplayLoadBytes(t.data(), t.size(), dwhy, sizeof(dwhy)) != 0);
    }

    DisplayResetForTest();
    std::vector<uint8_t> tbl = MakeTable(rows);
    Check("合格的替换表：载入，替换开启",
          DisplayLoadBytes(tbl.data(), tbl.size(), dwhy, sizeof(dwhy)) == 0
          && DisplayGetStats().on && DisplayGetStats().entries == 3);

    void* const inside = g_image + kRvaUiReadStub + 10;   // a UI reader's return address
    void* const outside = g_image + 0x100000;             // somewhere else in the game
    std::string sc;
    FakeText wa = {}, wb = {}, wc = {};

    const char* out = DisplayOnSet(&wa, kIon.c_str(), sc);
    Check("整句是日文键：换成中文", std::strcmp(out, kIonZh.c_str()) == 0);
    Check("  ……界面自己读，拿到中文",
          DisplayOnGet(&wa, out, inside) == out);
    Check("  ……别处的代码读，拿回日文原文",
          std::strcmp(DisplayOnGet(&wa, out, outside), kIon.c_str()) == 0);
    uint32_t seen[32];
    size_t nseen = DisplayGuardCallers(seen, 32);
    Check("  ……而且记下了是哪个调用点",
          nseen == 1 && seen[0] == 0x100000 && DisplayGetStats().guard_hits == 1);

    // The widget writing back what it read (ACUIText slot 24): still ours.
    DisplayOnSet(&wa, out, sc);
    Check("控件把读到的中文写回去：仍按原文回答别处的读取",
          std::strcmp(DisplayOnGet(&wa, out, outside), kIon.c_str()) == 0);
    // Then something else entirely: the Japanese we kept no longer applies.
    const char* plain = "plain text";
    Check("控件换成别的文字：不再改写读取",
          DisplayOnSet(&wa, plain, sc) == plain
          && DisplayOnGet(&wa, plain, outside) == plain
          && DisplayGetStats().guarded == 0);

    // The widget's text changing WITHOUT passing through the setter we hook --
    // a freed widget's address taken by a new one, or the game writing its
    // string some other way.  The read must not be answered from a memory of
    // a different text.
    DisplayOnSet(&wa, kIon.c_str(), sc);
    const char* elsewise = "set by a path we do not see";
    Check("文字绕过钩子变了：读取原样返回，不拿旧原文顶替",
          DisplayOnGet(&wa, elsewise, outside) == elsewise);
    DisplayOnSet(&wa, plain, sc);

    std::string plate = "<CLY2>" + kIon;
    out = DisplayOnSet(&wb, plate.c_str(), sc);
    Check("名牌 <CLY2>イオン：只换名字，保留标签",
          std::string(out) == "<CLY2>" + kIonZh);
    std::string log = "<CLY2>" + kIon + "<CLNA> hello  <CLY2>" + kTitle + "<CLNA> bye <CLY2>"
                      + kSave;
    std::string log_zh = "<CLY2>" + kIonZh + "<CLNA> hello  <CLY2>" + kTitleZh
                         + "<CLNA> bye <CLY2>" + kSave;
    out = DisplayOnSet(&wc, log.c_str(), sc);
    Check("日志里的多个名字都换掉，正文原样",
          std::string(out) == log_zh);
    Check("  ……只在整句时替换的词（EXE 保留词）不在名字位置上替换",
          std::string(out).find(kSave) != std::string::npos);
    Check("  ……别处读这条日志拿回日文原文",
          std::strcmp(DisplayOnGet(&wc, out, outside), log.c_str()) == 0);

    const char* zh_in = kIonZh.c_str();
    Check("已经是中文：原样放行（重复经过也不变）",
          DisplayOnSet(&wa, zh_in, sc) == zh_in);
    std::string huge(70000, 'x');
    uint64_t long_before = DisplayGetStats().too_long;
    Check("超长文字：不检查，原样放行并计数",
          DisplayOnSet(&wa, huge.c_str(), sc) == huge.c_str()
          && DisplayGetStats().too_long == long_before + 1);

    // No replacement without somewhere to remember it.
    DisplayResetForTest();
    DisplayLoadBytes(tbl.data(), tbl.size(), dwhy, sizeof(dwhy));
    size_t replaced = 0, kept = 0;
    for (uintptr_t i = 0; i < 6000; ++i) {
        void* self = reinterpret_cast<void*>(0x10000000 + i * 64);
        if (DisplayOnSet(self, kSave.c_str(), sc) == kSave.c_str())
            ++kept;
        else
            ++replaced;
    }
    DisplayStats fs = DisplayGetStats();
    Check("记不下的替换一律不做：被替换的都有原文可还",
          fs.guard_full == kept && fs.guarded == replaced && kept > 0
          && replaced + kept == 6000);

    // Two threads at once, as in the game.
    DisplayResetForTest();
    DisplayLoadBytes(tbl.data(), tbl.size(), dwhy, sizeof(dwhy));
    Hammer ha = { 0x20000000, kIon.c_str(), "a", outside, 0 };
    Hammer hb = { 0x30000000, kTitle.c_str(), "b", outside, 0 };
    HANDLE t1 = CreateThread(nullptr, 0, &DisplayHammer, &ha, 0, nullptr);
    HANDLE t2 = CreateThread(nullptr, 0, &DisplayHammer, &hb, 0, nullptr);
    WaitForSingleObject(t1, 30000);
    WaitForSingleObject(t2, 30000);
    CloseHandle(t1);
    CloseHandle(t2);
    Check("两个线程同时写读：每次替换都能还原成原文", ha.bad == 0 && hb.bad == 0);

    // Through the real hooks.  Only the whole-text case: the synthetic setter
    // stores the pointer instead of copying it as the game's std::string does,
    // and a whole-text replacement points into the table, which stays put.
    DisplayResetForTest();
    DisplayLoadBytes(tbl.data(), tbl.size(), dwhy, sizeof(dwhy));
    FakeText wh = {};
    wh.vtable = sprite;
    wh.capacity = 0x20;
    set(&wh, kIon.c_str());
    Check("经过真钩子：控件里存的是中文",
          std::strcmp(wh.str, kIonZh.c_str()) == 0);
    using UiReadFn = const char* (*)(void*);
    UiReadFn ui_read = reinterpret_cast<UiReadFn>(g_image + kRvaUiReadStub);
    Check("  ……从界面读取函数的范围内读：中文",
          std::strcmp(ui_read(&wh), kIonZh.c_str()) == 0);
    Check("  ……从游戏别处读：日文原文",
          std::strcmp(get(&wh), kIon.c_str()) == 0);

    DisplayResetForTest();
    set(&wh, kIon.c_str());
    Check("替换关闭时经过钩子：原样", wh.str == kIon.c_str());

    // --- recording is opt-in ------------------------------------------------
    // The automatic dump is a ~50 ms pause on the game's thread, so players do
    // not get the recorder at all; a marker file beside the executable turns
    // it on.  This executable stands in for the game's.
    wchar_t marker[MAX_PATH];
    PathBesideModule(nullptr, kTraceMarkerName, marker, MAX_PATH);
    DeleteFileW(marker);
    Check("没有标记文件：不记录", !TraceWanted(nullptr));
    HANDLE mk = CreateFileW(marker, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                            FILE_ATTRIBUTE_NORMAL, nullptr);
    if (mk != INVALID_HANDLE_VALUE)
        CloseHandle(mk);
    Check("  ……放上 cielzh-trace.on：记录", TraceWanted(nullptr));
    DeleteFileW(marker);

    // --- the status file install.py --verify reads ---------------------------
    {
        wchar_t st[MAX_PATH];
        PathBesideModule(nullptr, kStatusFileName, st, MAX_PATH);
        DeleteFileW(st);
        Check("状态文件：写入成功", WriteStatus(nullptr, 3, "wrong build"));
        char buf[512] = {};
        DWORD sgot = 0;
        HANDLE sh = CreateFileW(st, GENERIC_READ, FILE_SHARE_READ, nullptr,
                                OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (sh != INVALID_HANDLE_VALUE) {
            ReadFile(sh, buf, sizeof(buf) - 1, &sgot, nullptr);
            CloseHandle(sh);
        }
        Check("  ……记下返回码与原因",
              std::strstr(buf, "rc=3\r\n") && std::strstr(buf, "why=wrong build\r\n"));
        Check("  ……记下显示层状态与条目数",
              std::strstr(buf, "display=") && std::strstr(buf, "entries="));
        DeleteFileW(st);
    }

    DisplayLoadBytes(tbl.data(), tbl.size(), dwhy, sizeof(dwhy));
    TraceEnable(false);
    TraceStats off0 = TraceGetStats();
    set(&wh, kIon.c_str());
    get(&wh);
    TraceRecord(Op::kSet, Klass::kSpriteText, g_fake_obj, g_fake_caller,
                "recorded while off?");
    TraceStats off1 = TraceGetStats();
    Check("记录关闭：一条都不记，调用数也不变",
          off1.calls == off0.calls && off1.events == off0.events);
    Check("  ……显示层照常替换", std::strcmp(wh.str, kIonZh.c_str()) == 0);
    TraceEnable(true);
    TraceRecord(Op::kSet, Klass::kSpriteText, g_fake_obj, g_fake_caller,
                "recorded again");
    Check("  ……重新打开后照常记录", TraceGetStats().calls == off1.calls + 1);
    DisplayResetForTest();

    // --- rollback -----------------------------------------------------------
    void* ours = text[kSlotGetText];
    Poke(&text[kSlotGetText], reinterpret_cast<void*>(&main));
    Check("槽位被他人接管时拒绝回滚并保留现状",
          !RemoveTraceHooks(why, sizeof(why))
          && text[kSlotGetText] == reinterpret_cast<void*>(&main));
    Poke(&text[kSlotGetText], ours);

    Check("部分回滚后重试可续做，不误判为被接管",
          RemoveTraceHooks(why, sizeof(why)));
    Check("三个槽与页保护都已还原", untouched());
    Check("回滚后状态为未安装", !HooksInstalled() && !HooksTouched());

    std::printf("\n");
    if (g_fail) {
        std::printf("%d 项未通过\n", g_fail);
        return 1;
    }
    std::printf("原生自检全部通过\n");
    return 0;
}
