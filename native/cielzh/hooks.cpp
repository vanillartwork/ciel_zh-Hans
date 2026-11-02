// Verifying the executable, and replacing vtable slots.
//
// Three slots are hooked, not four.  ac::ACText is abstract: its slot 2 is pure
// virtual and leads to MSVC's _purecall, shared with 435 other pure-virtual
// slots in the image.  There is no ACText::SetText to observe, so it is checked
// and left alone -- hooking it would turn an abort into a silent success.  An
// earlier cut treated it as a second setter implementation and a synthetic test
// with a working stub at that address agreed, which is how a test can end up
// describing something the game does not do.
//
// Nothing in the shipped .text calls the getter or setter implementation
// directly; each has one thunk and no `call` sites.  That is a fact about this
// build, not a guarantee.  Stage one only recorded; the display layer now
// replaces text on the way into the setter (display.h), and still records what
// the game asked for, so a run can be read the same way as before.
#include <windows.h>
#include <intrin.h>
#include <atomic>
#include <cstdio>
#include <string>
#include "version.h"
#include "hooks.h"
#include "trace.h"
#include "display.h"

#pragma intrinsic(_ReturnAddress)

namespace cielzh {

namespace {

using SetTextFn = void(*)(void* self, const char* text);
using GetTextFn = const char*(*)(void* self);

SetTextFn g_sprite_set = nullptr;
GetTextFn g_sprite_get = nullptr;
GetTextFn g_text_get = nullptr;

// Every field is set BEFORE the write it describes, so a failure anywhere
// leaves a record of what was attempted.  Registering after a successful write
// loses exactly the case that matters: pointer written, protection not
// restored, entry never registered, hook left in the game's vtable with nothing
// remembering it.
//
// `original_prot` means something only once `prot_changed` is set.  When the
// very first VirtualProtect fails, nothing about the page or the slot changed
// and there is nothing to undo; an earlier version still recorded
// original_prot = 0 and then tried to "restore" 0, which is not a valid page
// protection, so that entry could never be cleaned up and held the whole
// rollback hostage.
struct Installed {
    void** slot;
    void* original;
    void* ours;
    DWORD original_prot;   // valid only if prot_changed
    bool prot_changed;     // our first VirtualProtect on this slot succeeded
    bool wrote;            // the slot held `ours` at some point
    bool restored;         // the pointer is back
    bool prot_restored;    // the page protection is back
    bool done;             // nothing further to do for this entry
};
Installed g_installed[4];
size_t g_installed_n = 0;
bool g_hooked = false;
bool g_touched = false;

// Three slots are not one atomic transaction.  A thread can be inside the first
// hook while the third is still being written -- the stage-one run showed the
// first SetText and GetText arriving on a background thread the main thread had
// not created yet at the install point, so "nobody is calling this during
// startup" is not something to lean on.
//
// Until `g_armed` is published, a hook forwards to the game's own function and
// records nothing: an event from a half-installed state would be a sample whose
// conditions we cannot describe.  Those calls are counted instead, so a run can
// say whether its sample is complete.  Release/acquire because the originals
// and the trace table must be visible to a thread that sees the flag.
std::atomic<bool> g_armed{false};
std::atomic<unsigned long> g_early_calls{0};

ProtectFn g_protect = nullptr;

BOOL Protect(void* addr, size_t len, DWORD want, DWORD* old)
{
    if (g_protect)
        return g_protect(addr, len, want, old) ? TRUE : FALSE;
    return VirtualProtect(addr, len, want, old);
}

inline const uint8_t* At(const void* base, uint32_t rva)
{
    return static_cast<const uint8_t*>(base) + rva;
}

// Little-endian reads, so nothing here depends on the alignment of a header
// field inside a mapped image.
inline uint16_t Word(const uint8_t* p)
{
    return static_cast<uint16_t>(p[0] | (p[1] << 8));
}
inline uint32_t Dword(const uint8_t* p)
{
    uint32_t v = 0;
    for (int i = 0; i < 4; ++i)
        v |= static_cast<uint32_t>(p[i]) << (8 * i);
    return v;
}
inline uint64_t Qword(const uint8_t* p)
{
    uint64_t v = 0;
    for (int i = 0; i < 8; ++i)
        v |= static_cast<uint64_t>(p[i]) << (8 * i);
    return v;
}

inline bool Armed()
{
    if (g_armed.load(std::memory_order_acquire))
        return true;
    g_early_calls.fetch_add(1, std::memory_order_relaxed);
    return false;
}

// TraceRecord and the display layer each take their own lock and give it back
// before returning, so no hook ever calls into the game while holding one.
// Keep it that way: the game's setter allocates.
//
// What is recorded is what the game asked for -- the Japanese -- not what the
// widget was handed.  The trace is evidence about the game; the dump header
// says separately what the display layer did with it.
void HookSpriteSet(void* self, const char* text)
{
    const char* out = text;
    std::string scratch;      // empty until a name inside the text is replaced
    if (Armed()) {
        TraceRecord(Op::kSet, Klass::kSpriteText, self, _ReturnAddress(), text);
        out = DisplayOnSet(self, text, scratch);
    }
    g_sprite_set(self, out);
}

const char* HookSpriteGet(void* self)
{
    const char* got = g_sprite_get(self);
    if (!Armed())
        return got;
    void* caller = _ReturnAddress();
    TraceRecord(Op::kGet, Klass::kSpriteText, self, caller, got);
    return DisplayOnGet(self, got, caller);
}

const char* HookTextGet(void* self)
{
    const char* got = g_text_get(self);
    if (!Armed())
        return got;
    void* caller = _ReturnAddress();
    TraceRecord(Op::kGet, Klass::kText, self, caller, got);
    return DisplayOnGet(self, got, caller);
}

// --- verification -----------------------------------------------------------

// `size` 0 means "consult the OS for this range".  A single VirtualQuery at the
// module base says nothing about a vtable 13 MB further in, so each range is
// asked about separately.
bool Readable(const void* base, size_t size, uint32_t rva, size_t need)
{
    if (static_cast<uint64_t>(rva) + need < need)   // overflow
        return false;
    if (size != 0)
        return static_cast<uint64_t>(rva) + need <= size;

    const uint8_t* p = At(base, rva);
    size_t left = need;
    while (left) {
        MEMORY_BASIC_INFORMATION mbi = {};
        if (!VirtualQuery(p, &mbi, sizeof(mbi)))
            return false;
        if (mbi.State != MEM_COMMIT)
            return false;
        DWORD prot = mbi.Protect & 0xFF;
        if (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS))
            return false;
        if (prot == PAGE_NOACCESS)
            return false;
        size_t in_region = static_cast<size_t>(
            reinterpret_cast<const uint8_t*>(mbi.BaseAddress) + mbi.RegionSize - p);
        size_t step = in_region < left ? in_region : left;
        p += step;
        left -= step;
    }
    return true;
}

bool CheckThunk(const void* base, size_t size, uint32_t thunk, uint32_t impl,
                const char* what, char* why, size_t why_len)
{
    if (!Readable(base, size, thunk, 5)) {
        std::snprintf(why, why_len, "%s thunk RVA 0x%X is not readable", what, thunk);
        return false;
    }
    const uint8_t* p = At(base, thunk);
    if (p[0] != 0xE9) {
        std::snprintf(why, why_len, "%s thunk at 0x%X is not a jmp (0x%02X)",
                      what, thunk, p[0]);
        return false;
    }
    int32_t rel = 0;
    for (int i = 0; i < 4; ++i)
        rel |= static_cast<int32_t>(p[1 + i]) << (8 * i);
    uint32_t target = thunk + 5 + static_cast<uint32_t>(rel);
    if (target != impl) {
        std::snprintf(why, why_len, "%s thunk at 0x%X jumps to 0x%X, expected 0x%X",
                      what, thunk, target, impl);
        return false;
    }
    return true;
}

bool CheckBytes(const void* base, size_t size, uint32_t rva, const uint8_t* want,
                size_t n, const char* what, char* why, size_t why_len)
{
    if (!Readable(base, size, rva, n)) {
        std::snprintf(why, why_len, "%s at 0x%X is not readable", what, rva);
        return false;
    }
    const uint8_t* p = At(base, rva);
    for (size_t i = 0; i < n; ++i) {
        if (p[i] != want[i]) {
            std::snprintf(why, why_len,
                          "%s at 0x%X does not match this build "
                          "(byte %zu is 0x%02X, expected 0x%02X)",
                          what, rva, i, p[i], want[i]);
            return false;
        }
    }
    return true;
}

}  // namespace

void SetProtectForTest(ProtectFn fn) { g_protect = fn; }
bool HooksInstalled() { return g_hooked; }
bool HooksTouched() { return g_touched; }
bool HooksArmed() { return g_armed.load(std::memory_order_acquire); }
unsigned long HooksEarlyCalls()
{
    return g_early_calls.load(std::memory_order_relaxed);
}

bool VerifyModule(const void* base, size_t size, char* why, size_t why_len)
{
    if (!base) {
        std::snprintf(why, why_len, "no module base");
        return false;
    }
    if (!Readable(base, size, 0, 0x40)) {
        std::snprintf(why, why_len, "the module base is not readable");
        return false;
    }
    if (At(base, 0)[0] != 'M' || At(base, 0)[1] != 'Z') {
        std::snprintf(why, why_len, "not a PE image");
        return false;
    }
    uint32_t lfanew = 0;
    for (int i = 0; i < 4; ++i)
        lfanew |= static_cast<uint32_t>(At(base, 0x3C)[i]) << (8 * i);
    if (lfanew < 0x40 || !Readable(base, size, lfanew, 0x78)) {
        std::snprintf(why, why_len, "the PE header is not where it should be");
        return false;
    }
    const uint8_t* nt = At(base, lfanew);
    if (nt[0] != 'P' || nt[1] != 'E' || nt[2] || nt[3]) {
        std::snprintf(why, why_len, "no PE signature");
        return false;
    }
    uint16_t machine = Word(nt + 4);
    if (machine != kMachineAmd64) {
        std::snprintf(why, why_len, "machine 0x%04X, expected x64", machine);
        return false;
    }
    // Header shape before any field inside it is read.  Offsets were hand-
    // computed once before and one of them was wrong, so nothing is indexed
    // without first checking the header is long enough to hold it.
    uint16_t opt_size = Word(nt + 20);
    const uint8_t* opt = nt + 24;
    if (!Readable(base, size, lfanew + 24, opt_size)) {
        std::snprintf(why, why_len, "the optional header is not readable");
        return false;
    }
    if (Word(opt) != kOptMagicPe32Plus) {
        std::snprintf(why, why_len, "optional header magic 0x%04X, expected PE32+",
                      Word(opt));
        return false;
    }
    if (opt_size < 112 + (kLoadConfigDirIndex + 1) * 8) {
        std::snprintf(why, why_len,
                      "the optional header is too short (0x%X) for the data "
                      "directories this needs", opt_size);
        return false;
    }
    uint32_t dirs = Dword(opt + 108);
    if (dirs <= kLoadConfigDirIndex) {
        std::snprintf(why, why_len,
                      "only %u data directories; no load config to check", dirs);
        return false;
    }
    uint32_t image = Dword(opt + 56);
    if (image < kSizeOfImage) {
        std::snprintf(why, why_len,
                      "SizeOfImage 0x%X is smaller than this build's 0x%X",
                      image, kSizeOfImage);
        return false;
    }

    uint16_t dllchar = Word(opt + 70);
    if (dllchar != kDllCharacteristics) {
        std::snprintf(why, why_len,
                      "DllCharacteristics 0x%04X, expected 0x%04X%s",
                      dllchar, kDllCharacteristics,
                      (dllchar & kDllCharGuardCf)
                          ? " (GUARD_CF is now set; the hook compatibility "
                            "argument needs re-verifying)" : "");
        return false;
    }

    uint32_t lc_rva = Dword(opt + 112 + kLoadConfigDirIndex * 8);
    uint32_t lc_size = Dword(opt + 112 + kLoadConfigDirIndex * 8 + 4);
    if (lc_rva == 0 || lc_size < kLoadConfigMinSize
        || !Readable(base, size, lc_rva, kLoadConfigMinSize)) {
        std::snprintf(why, why_len,
                      "the load config directory is missing or too short "
                      "(RVA 0x%X, size 0x%X)", lc_rva, lc_size);
        return false;
    }
    const uint8_t* lc = At(base, lc_rva);
    if (Dword(lc) < kLoadConfigMinSize) {
        std::snprintf(why, why_len,
                      "the load config says it is 0x%X bytes, too short to hold "
                      "GuardFlags", Dword(lc));
        return false;
    }
    uint32_t gflags = Dword(lc + 0x90);
    uint64_t gtable = Qword(lc + 0x80);
    uint64_t gcount = Qword(lc + 0x88);
    if (gflags != kGuardFlags || gtable != 0 || gcount != 0) {
        std::snprintf(why, why_len,
                      "CFG configuration changed (GuardFlags 0x%X, table %p, "
                      "count %llu; expected 0x%X, null, 0) -- refusing to hook "
                      "until this is re-verified",
                      gflags, (void*)gtable, (unsigned long long)gcount,
                      kGuardFlags);
        return false;
    }
    // Note what is NOT here: `size` is never widened to `image`.  A one-page
    // buffer can claim any SizeOfImage it likes; believing it is how a bad
    // module turns a refusal into a read 13 MB past the end.

    struct Slot { uint32_t vtable; int slot; uint32_t thunk; const char* what; };
    const Slot slots[] = {
        { kRvaSpriteTextVtable, kSlotSetText, kRvaSpriteSetThunk, "ACSpriteText::SetText" },
        { kRvaSpriteTextVtable, kSlotGetText, kRvaGetThunk,       "ACSpriteText::GetText" },
        { kRvaTextVtable,       kSlotGetText, kRvaGetThunk,       "ACText::GetText" },
        { kRvaTextVtable,       kSlotSetText, kRvaPurecallThunk,  "ACText slot 2 (_purecall)" },
    };
    for (const Slot& s : slots) {
        size_t need = static_cast<size_t>(s.slot + 1) * sizeof(void*);
        if (!Readable(base, size, s.vtable, need)) {
            std::snprintf(why, why_len, "%s vtable 0x%X is not readable",
                          s.what, s.vtable);
            return false;
        }
        const void* const* vt =
            reinterpret_cast<const void* const*>(At(base, s.vtable));
        if (static_cast<const uint8_t*>(vt[s.slot]) != At(base, s.thunk)) {
            std::snprintf(why, why_len,
                          "%s is not where this build expects it "
                          "(vtable 0x%X slot %d)", s.what, s.vtable, s.slot);
            return false;
        }
    }

    if (!CheckThunk(base, size, kRvaSpriteSetThunk, kRvaSpriteSetImpl,
                    "ACSpriteText::SetText", why, why_len))
        return false;
    if (!CheckThunk(base, size, kRvaGetThunk, kRvaGetImpl, "GetText", why, why_len))
        return false;
    if (!CheckThunk(base, size, kRvaPurecallThunk, kRvaPurecallImpl,
                    "_purecall", why, why_len))
        return false;
    if (!CheckBytes(base, size, kRvaGetImpl, kBodyGet, sizeof(kBodyGet),
                    "GetText body", why, why_len))
        return false;
    if (!CheckBytes(base, size, kRvaSpriteSetImpl, kPrefixSpriteSet,
                    sizeof(kPrefixSpriteSet), "ACSpriteText::SetText opening",
                    why, why_len))
        return false;
    // The display layer decides who gets the Chinese by these ranges, so they
    // have to be the functions they were read from, not whatever sits there in
    // some other build.
    for (const UiReader& r : kUiReaders)
        if (!CheckBytes(base, size, r.begin, r.prefix, sizeof(r.prefix),
                        "ACUIText reader opening", why, why_len))
            return false;
    return true;
}

namespace {

// Registers first, then writes.  `e` is left describing whatever actually
// happened, success or not.
bool Apply(Installed& e, void** slot, void* ours, char* why, size_t why_len)
{
    e.slot = slot;
    e.original = *slot;
    e.ours = ours;
    e.original_prot = 0;
    e.prot_changed = false;
    e.wrote = false;
    e.restored = false;
    e.prot_restored = false;
    e.done = false;

    DWORD old = 0;
    if (!Protect(slot, sizeof(void*), PAGE_READWRITE, &old)) {
        // Nothing changed.  There is no protection to put back and no pointer
        // to restore, so this entry is finished as it stands.
        e.done = true;
        std::snprintf(why, why_len, "VirtualProtect failed (%lu)", GetLastError());
        return false;
    }
    e.original_prot = old;
    e.prot_changed = true;
    g_touched = true;

    // Compare-and-exchange rather than a plain store: another thread may be
    // reading this slot to make a virtual call right now, and if something else
    // has hooked it since we read `e.original`, overwriting would drop them
    // silently.  A single aligned pointer store would be atomic on x64 anyway;
    // the exchange is here for the check, not the atomicity.
    void* was = InterlockedCompareExchangePointer(slot, ours, e.original);
    if (was != e.original) {
        DWORD ignored = 0;
        if (Protect(slot, sizeof(void*), old, &ignored))
            e.prot_restored = true;
        e.done = e.prot_restored;
        std::snprintf(why, why_len,
                      "the slot changed under us while installing "
                      "(expected %p, found %p)", e.original, was);
        return false;
    }
    e.wrote = true;
    FlushInstructionCache(GetCurrentProcess(), slot, sizeof(void*));

    DWORD ignored = 0;
    if (!Protect(slot, sizeof(void*), old, &ignored)) {
        std::snprintf(why, why_len,
                      "the hook is installed but the page is still writable (%lu)",
                      GetLastError());
        return false;
    }
    e.prot_restored = true;
    return true;
}

}  // namespace

bool InstallTraceHooks(void* base, char* why, size_t why_len)
{
    if (g_hooked) {
        std::snprintf(why, why_len, "already installed");
        return true;
    }
    // Records left by an attempt that did not finish undoing itself.  Wiping
    // them and starting over would read each page's CURRENT protection -- which
    // may still be the RW we set -- as its original, and the read-only value
    // would be lost for good.  So: finish that cleanup first, or refuse.  The
    // public entry checks the same thing; this is the layer that owns the
    // records, so it must not rely on its caller having done so.
    if (g_installed_n != 0) {
        char w[256];
        if (!RemoveTraceHooks(w, sizeof(w))) {
            std::snprintf(why, why_len,
                          "an earlier install is not fully undone (%s); "
                          "refusing to overwrite its records", w);
            return false;
        }
    }
    void** sprite = reinterpret_cast<void**>(
        static_cast<uint8_t*>(base) + kRvaSpriteTextVtable);
    void** text = reinterpret_cast<void**>(
        static_cast<uint8_t*>(base) + kRvaTextVtable);

    g_sprite_set = reinterpret_cast<SetTextFn>(sprite[kSlotSetText]);
    g_sprite_get = reinterpret_cast<GetTextFn>(sprite[kSlotGetText]);
    g_text_get = reinterpret_cast<GetTextFn>(text[kSlotGetText]);

    struct Plan { void** slot; void* ours; };
    const Plan plan[] = {
        { &sprite[kSlotSetText], reinterpret_cast<void*>(&HookSpriteSet) },
        { &sprite[kSlotGetText], reinterpret_cast<void*>(&HookSpriteGet) },
        { &text[kSlotGetText],   reinterpret_cast<void*>(&HookTextGet) },
        // ACText slot 2 is _purecall; see version.h.  Deliberately absent.
    };

    g_installed_n = 0;
    for (const Plan& p : plan) {
        Installed& e = g_installed[g_installed_n];
        ++g_installed_n;                       // counted before it can fail
        if (!Apply(e, p.slot, p.ours, why, why_len)) {
            char first[256];
            std::snprintf(first, sizeof(first), "%s", why);
            char rollback[256];
            if (!RemoveTraceHooks(rollback, sizeof(rollback))) {
                std::snprintf(why, why_len,
                              "install failed (%s) AND rollback failed (%s) -- "
                              "keep this DLL loaded", first, rollback);
            } else {
                std::snprintf(why, why_len, "install failed (%s); rolled back",
                              first);
            }
            return false;
        }
    }
    g_hooked = true;
    // Last, and only once every slot is in and every page is back to read-only.
    // Release: a thread that sees this must also see the originals and the
    // initialised trace table.
    g_armed.store(true, std::memory_order_release);
    return true;
}

bool RemoveTraceHooks(char* why, size_t why_len)
{
    // Stop recording first.  A call already inside a hook keeps forwarding to
    // the game's own function, which is why the DLL stays resident: the slots
    // going back does not mean every hook has returned.
    g_armed.store(false, std::memory_order_release);
    bool all = true;
    for (size_t i = g_installed_n; i-- > 0;) {
        Installed& e = g_installed[i];
        if (e.done)
            continue;                       // finished, now or by an earlier attempt
        if (!e.prot_changed) {
            e.done = true;                  // never changed anything
            continue;
        }

        if (e.wrote && !e.restored) {
            if (*e.slot != e.ours) {
                // Somebody else owns it now.  Putting the original back would
                // silently drop whoever hooked after us.
                std::snprintf(why, why_len,
                              "slot %zu no longer holds our hook; leaving it alone",
                              i);
                all = false;
                continue;
            }
            DWORD old = 0;
            if (!Protect(e.slot, sizeof(void*), PAGE_READWRITE, &old)) {
                std::snprintf(why, why_len,
                              "could not make slot %zu writable to restore it (%lu)",
                              i, GetLastError());
                all = false;
                continue;
            }
            void* was = InterlockedCompareExchangePointer(e.slot, e.original, e.ours);
            FlushInstructionCache(GetCurrentProcess(), e.slot, sizeof(void*));
            if (was != e.ours) {
                std::snprintf(why, why_len,
                              "slot %zu changed while being restored", i);
                all = false;
                continue;
            }
            e.restored = true;
            e.prot_restored = false;        // we just made it writable again
        }

        if (!e.prot_restored) {
            DWORD ignored = 0;
            if (!Protect(e.slot, sizeof(void*), e.original_prot, &ignored)) {
                std::snprintf(why, why_len,
                              "slot %zu is restored but its page is still "
                              "writable (%lu)", i, GetLastError());
                all = false;
                continue;
            }
            e.prot_restored = true;
        }
        e.done = true;
    }
    if (all) {
        g_installed_n = 0;
        g_hooked = false;
        g_touched = false;
        std::snprintf(why, why_len, "all slots and page protections restored");
    }
    return all;
}

}  // namespace cielzh
