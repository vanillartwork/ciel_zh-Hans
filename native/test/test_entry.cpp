// The whole chain, not just CielZhInitializeV1.
//
//   a stand-in for the call site at 0x7B7F05
//     -> the emitted entry, byte for byte as it will go into the executable
//        -> a fake IAT whose stubs behave like the real APIs, including
//           scribbling over every stack slot the ABI lets a seven-argument
//           callee write
//     -> a probe standing in for the original target, which records what
//        actually arrived
//
// Calling the DLL export directly would have missed the bug this is built
// around: a saved RCX parked at [rsp+0x20] is WriteFile's fifth argument, and a
// five-argument callee overwrites it with NULL whether or not it cares.
#include <windows.h>
#include <intrin.h>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <initializer_list>
#include <string>
#include "../loader/entrycode.h"

#pragma intrinsic(_AddressOfReturnAddress)

using namespace cielzh;

namespace {

int g_fail = 0;

void Check(const char* what, bool ok)
{
    std::printf("  %-56s %s\n", what, ok ? "ok" : "FAILED");
    if (!ok)
        ++g_fail;
}

// ---------------------------------------------------------------- the image --
// One allocation holding code, data and a fake IAT, so every rip-relative
// displacement the emitter produces stays in range.
constexpr size_t kImageSize = 0x10000;
constexpr uint32_t kCodeRva = 0x1000;
constexpr uint32_t kDataRva = 0x3000;
constexpr uint32_t kIatRva  = 0x4000;
constexpr uint32_t kProbeRva = 0x5000;

uint8_t* g_img = nullptr;
EmitResult g_emit;

// The exact pointer the call site hands over as its first argument, published
// on the way in so the probe's RCX can be compared against a value rather than
// merely "not the scribble pattern".  Same for the address the original target
// must return to.
void* g_expected_rcx = nullptr;
void* g_expected_return = nullptr;

enum IatSlot {
    kIatGetModuleFileNameW = 0,
    kIatLoadLibraryExW,
    kIatGetProcAddress,
    kIatCreateFileW,
    kIatWriteFile,
    kIatCloseHandle,
    kIatGetLastError,
    kIatCount,
};

void** Iat() { return reinterpret_cast<void**>(g_img + kIatRva); }
uint32_t IatRva(IatSlot s) { return kIatRva + uint32_t(s) * 8; }

// --- what the probe saw ------------------------------------------------------
struct Seen {
    int calls;
    void* rcx;
    void* rdx;
    uint64_t rsp_mod16;
    void* return_address;
    uint64_t result;
};
Seen g_seen;

// --- fake APIs --------------------------------------------------------------
// Each one scribbles over the caller's [rsp+0x00 .. rsp+0x37] on entry: the
// shadow space the caller hands it, plus the slots for arguments five to seven.
// That is exactly the region the calling convention lets a callee use, so
// anything the entry parks there is fair game -- and anything above it must
// come back intact.
//
// The scribbling lives in its own noinline function, taking the address as an
// argument.  Written inline it destroyed itself: with /O2 the pointer spilled
// into the shadow space the caller had provided -- which the loop was busy
// filling with the pattern -- and the second iteration reloaded 0xDEADBEEF as
// the destination.  Which is the same lesson from the other side: the shadow
// space belongs to the callee, so [rsp+0x00..0x1F] is no safer a hiding place
// than [rsp+0x20..0x37].
constexpr uint64_t kScribble = 0xDEADBEEFDEADBEEFull;

__declspec(noinline) void ScribbleCallerArgArea(void* return_address_slot)
{
    volatile uint64_t* p =
        static_cast<volatile uint64_t*>(return_address_slot);
    for (int i = 7; i >= 1; --i)        // p[0] is the return address
        p[i] = kScribble;
}

// `args` is how many the real API takes.  A callee owns the shadow space plus
// the slots for its own arguments five and up, and no more, so each fake
// scribbles exactly that much.  Claiming every callee owns seven slots would
// describe an API surface that does not exist; the wider sweep is kept as a
// separate stress case instead.
__declspec(noinline) void ScribbleForArity(void* ret_slot, int args)
{
    volatile uint64_t* p = static_cast<volatile uint64_t*>(ret_slot);
    int slots = args > 4 ? args : 4;            // shadow space is always 4
    for (int i = slots; i >= 1; --i)
        p[i] = kScribble;
}

bool g_stress_seven = false;

#define CLOBBER(args) \
    ScribbleForArity(_AddressOfReturnAddress(), g_stress_seven ? 7 : (args))

// Every parameter is taken through this before the scribble runs.  A plain
// assignment is not enough: at /O2 the compiler is entitled to leave the load
// until the value is used, because nothing is supposed to write a parameter's
// home slot behind its back -- so `creation` was being read after the scribble
// and arrived as 0xDEADBEEF.  A volatile read pins the load to this point.
//
// That is also the honest model of a real callee: it consumes its arguments and
// only then treats the area as scratch.
#define TAKE(x) (*static_cast<volatile decltype(x)*>(&(x)))

// Parameters are parked in globals before the scribble runs, and everything
// afterwards reads only those.  A local would not do: at /O2 the compiler may
// spill it into the parameter home slot, which is inside the very area being
// scribbled, and the reload then yields 0xDEADBEEF.  Globals live elsewhere.
LPWSTR g_p_out = nullptr;
DWORD g_p_n = 0;
LPCWSTR g_p_path = nullptr;
DWORD g_p_flags = 0;
LPCSTR g_p_name = nullptr;
LPCWSTR g_p_name_w = nullptr;
DWORD g_p_access = 0, g_p_share = 0, g_p_creation = 0, g_p_flags2 = 0;
LPSECURITY_ATTRIBUTES g_p_sa = nullptr;
HANDLE g_p_templ = nullptr, g_p_h = nullptr;
LPCVOID g_p_buf = nullptr;
DWORD g_p_len = 0;
LPDWORD g_p_written = nullptr;
LPOVERLAPPED g_p_ov = nullptr;

bool g_gmfn_fail = false;
wchar_t g_module_path[512];
DWORD WINAPI FakeGetModuleFileNameW(HMODULE, LPWSTR out_p, DWORD n_p)
{
    g_p_out = TAKE(out_p);
    g_p_n = TAKE(n_p);
    CLOBBER(3);
    LPWSTR out = g_p_out;
    DWORD n = g_p_n;
    if (g_gmfn_fail)
        return 0;
    const wchar_t* path = g_module_path;
    size_t len = wcslen(path);
    if (len + 1 > n) {
        // What the real one does: fill the buffer, terminate it, and return the
        // size that was passed in.  Returning 0 instead -- which this used to do
        // -- meant the truncation branch was never reached, and deleting the
        // stub's `cmp eax, 280` check did not fail a single test.
        std::memcpy(out, path, (n - 1) * sizeof(wchar_t));
        out[n - 1] = L'\0';
        SetLastError(ERROR_INSUFFICIENT_BUFFER);
        return n;
    }
    std::memcpy(out, path, (len + 1) * sizeof(wchar_t));
    return DWORD(len);
}

bool g_load_fail = false;
int g_load_calls = 0;
wchar_t g_asked_path[300];
HMODULE WINAPI FakeLoadLibraryExW(LPCWSTR path_p, HANDLE, DWORD flags_p)
{
    g_p_path = TAKE(path_p);
    g_p_flags = TAKE(flags_p);
    CLOBBER(3);
    ++g_load_calls;
    wcsncpy_s(g_asked_path, g_p_path, _TRUNCATE);
    if (g_load_fail)
        return nullptr;
    (void)g_p_flags;
    return reinterpret_cast<HMODULE>(0x1234);
}

uint32_t g_abi = 0x00010000;
int g_init_rc = 0;
bool g_hide_abi = false;
bool g_hide_init = false;
char* g_why_seen = nullptr;
int g_why_len_seen = 0;
int g_init_calls = 0;

uint32_t __cdecl FakeAbiVersion() { return g_abi; }

int __cdecl FakeInitialize(char* why, int why_len)
{
    ++g_init_calls;
    g_why_seen = why;
    g_why_len_seen = why_len;
    if (why && why_len > 0)
        std::snprintf(why, size_t(why_len), "fake init said %d", g_init_rc);
    return g_init_rc;
}

FARPROC WINAPI FakeGetProcAddress(HMODULE, LPCSTR name_p)
{
    g_p_name = TAKE(name_p);
    CLOBBER(2);
    if (std::strcmp(g_p_name, "CielZhAbiVersion") == 0)
        return g_hide_abi ? nullptr : reinterpret_cast<FARPROC>(&FakeAbiVersion);
    if (std::strcmp(g_p_name, "CielZhInitializeV1") == 0)
        return g_hide_init ? nullptr : reinterpret_cast<FARPROC>(&FakeInitialize);
    return nullptr;
}

DWORD g_last_error = 0x57;
DWORD WINAPI FakeGetLastError() { return g_last_error; }

// The log path is a real file, and CreateFileW really has seven arguments.
wchar_t g_log_path[300];
int g_create_calls = 0;
int g_write_calls = 0;
bool g_write_fail = false;    // WriteFile returns FALSE
bool g_write_short = false;   // returns TRUE but reports fewer bytes
int g_create_bad = 0;
HANDLE g_create_ret = nullptr;
char g_log_text[512];
size_t g_log_len = 0;

// Arguments five to seven arrive in the caller's stack area, which the scribble
// is about to fill, so they are read out first.  Validating them afterwards
// would only ever have found 0xDEADBEEF.
HANDLE WINAPI FakeCreateFileW(LPCWSTR name, DWORD access, DWORD share,
                              LPSECURITY_ATTRIBUTES sa, DWORD creation,
                              DWORD flags, HANDLE templ)
{
    g_p_name_w = TAKE(name);
    g_p_access = TAKE(access);
    g_p_share = TAKE(share);
    g_p_creation = TAKE(creation);
    g_p_flags2 = TAKE(flags);
    g_p_sa = TAKE(sa);
    g_p_templ = TAKE(templ);
    CLOBBER(7);
    LPCWSTR l_name = g_p_name_w;
    DWORD l_access = g_p_access, l_share = g_p_share;
    DWORD l_creation = g_p_creation, l_flags = g_p_flags2;
    LPSECURITY_ATTRIBUTES l_sa = g_p_sa;
    HANDLE l_templ = g_p_templ;

    ++g_create_calls;
    wcsncpy_s(g_log_path, l_name, _TRUNCATE);
    g_create_bad = 0;
    if (l_access != GENERIC_WRITE) g_create_bad = 1;
    else if (l_share != FILE_SHARE_READ) g_create_bad = 2;
    else if (l_sa != nullptr) g_create_bad = 3;
    else if (l_creation != CREATE_ALWAYS) g_create_bad = 4;
    else if (l_flags != FILE_ATTRIBUTE_NORMAL) g_create_bad = 5;
    else if (l_templ != nullptr) g_create_bad = 6;
    g_create_ret = g_create_bad ? INVALID_HANDLE_VALUE
                                : reinterpret_cast<HANDLE>(0x99);
    return g_create_ret;
}

BOOL WINAPI FakeWriteFile(HANDLE h, LPCVOID buf, DWORD len, LPDWORD written,
                          LPOVERLAPPED ov)
{
    g_p_h = TAKE(h);
    g_p_buf = TAKE(buf);
    g_p_len = TAKE(len);
    g_p_written = TAKE(written);
    g_p_ov = TAKE(ov);
    CLOBBER(5);
    HANDLE l_h = g_p_h;
    LPCVOID l_buf = g_p_buf;
    DWORD l_len = g_p_len;
    LPDWORD l_written = g_p_written;
    LPOVERLAPPED l_ov = g_p_ov;

    ++g_write_calls;
    if (l_h != reinterpret_cast<HANDLE>(0x99) || l_ov != nullptr)
        return FALSE;
    if (g_write_fail)
        return FALSE;
    if (g_write_short) {
        if (l_written)
            *l_written = l_len > 1 ? l_len - 1 : 0;
        return TRUE;
    }
    g_log_len = l_len < sizeof(g_log_text) - 1 ? l_len : sizeof(g_log_text) - 1;
    std::memcpy(g_log_text, l_buf, g_log_len);
    g_log_text[g_log_len] = '\0';
    if (l_written)
        *l_written = l_len;
    return TRUE;
}

BOOL WINAPI FakeCloseHandle(HANDLE) { CLOBBER(1); return TRUE; }

// --- the probe standing in for the original target --------------------------
// Emitted, not compiled, so the entry's tail jump lands on something whose
// stack layout is known exactly.
extern "C" uint64_t ProbeTarget(void* rcx, void* rdx);

uint64_t ProbeImpl(void* rcx, void* rdx, void* ret, uint64_t rsp)
{
    ++g_seen.calls;
    g_seen.rcx = rcx;
    g_seen.rdx = rdx;
    g_seen.return_address = ret;
    // On entry the return address has just been pushed, so rsp is 8 mod 16 when
    // the caller was aligned.
    g_seen.rsp_mod16 = rsp % 16;
    return 0xC0FFEE;
}

// --- building the image -----------------------------------------------------
void BuildProbe()
{
    // mov r8, [rsp]        ; the return address
    // lea r9, [rsp+8]      ; rsp as the caller left it
    // sub rsp, 0x28
    // call ProbeImpl
    // add rsp, 0x28
    // ret
    uint8_t* p = g_img + kProbeRva;
    size_t n = 0;
    auto put = [&](std::initializer_list<uint8_t> bs) {
        for (uint8_t b : bs) p[n++] = b;
    };
    put({0x4C, 0x8B, 0x04, 0x24});              // mov r8, [rsp]
    put({0x49, 0x89, 0xE1});                    // mov r9, rsp
    put({0x48, 0x83, 0xEC, 0x28});              // sub rsp, 0x28
    put({0x48, 0xB8});                          // mov rax, imm64
    void* fn = reinterpret_cast<void*>(&ProbeImpl);
    std::memcpy(p + n, &fn, 8); n += 8;
    put({0xFF, 0xD0});                          // call rax
    put({0x48, 0x83, 0xC4, 0x28});              // add rsp, 0x28
    put({0xC3});
}

// Stands in for the intercepted call site:
//     mov rdx, r14 ; lea rcx, [rsp+0x40] ; call <entry>
// with a frame big enough that [rsp+0x40] is inside it.
using SiteFn = uint64_t (*)(void* entry, void* rdx_value);
SiteFn g_site = nullptr;
uint32_t kSiteRva = 0x6000;

void BuildSite()
{
    uint8_t* p = g_img + kSiteRva;
    size_t n = 0;
    auto put = [&](std::initializer_list<uint8_t> bs) {
        for (uint8_t b : bs) p[n++] = b;
    };
    // rcx = entry, rdx = value to pass through as the call's second argument
    put({0x48, 0x83, 0xEC, 0x68});              // sub rsp, 0x68
    put({0x48, 0x89, 0x4C, 0x24, 0x60});        // mov [rsp+0x60], rcx (entry)
    put({0x48, 0x89, 0xD1});                    // mov rcx, rdx  (stash value)
    put({0x48, 0x89, 0xCA});                    // mov rdx, rcx  -> arg 2
    put({0x48, 0x8D, 0x4C, 0x24, 0x40});        // lea rcx, [rsp+0x40] -> arg 1
    // Publish what is about to be passed, so the probe's RCX and the return
    // address can be compared against exact values.
    put({0x48, 0xB8});
    void* pexp = &g_expected_rcx;
    std::memcpy(p + n, &pexp, 8); n += 8;
    put({0x48, 0x89, 0x08});                    // mov [rax], rcx
    put({0x48, 0x8B, 0x44, 0x24, 0x60});        // mov rax, [rsp+0x60]
    put({0xFF, 0xD0});                          // call rax
    // The instruction after the call: what the original target must return to.
    g_expected_return = p + n;
    put({0x48, 0x83, 0xC4, 0x68});              // add rsp, 0x68
    put({0xC3});
    g_site = reinterpret_cast<SiteFn>(p);
}

void ResetFakes()
{
    std::memset(&g_seen, 0, sizeof(g_seen));
    wcscpy_s(g_module_path, L"C:\\game\\CielnosurgeDX.exe");
    g_stress_seven = false;
    std::memset(g_img + kDataRva, 0, data::kSize);
    g_gmfn_fail = g_load_fail = g_hide_abi = g_hide_init = false;
    g_abi = 0x00010000;
    g_init_rc = 0;
    g_init_calls = 0;
    g_create_calls = 0;
    g_load_calls = 0;
    g_write_calls = 0;
    g_write_fail = false;
    g_write_short = false;
    g_create_bad = 0;
    g_create_ret = nullptr;
    g_log_len = 0;
    g_log_text[0] = '\0';
    g_log_path[0] = 0;
    g_asked_path[0] = 0;
}

uint64_t RunChain(void* rdx_value)
{
    return g_site(g_img + kCodeRva + g_emit.entry_offset, rdx_value);
}

bool LogHas(const char* needle)
{
    return std::strstr(g_log_text, needle) != nullptr;
}

uint32_t ReadData(uint32_t off)
{
    uint32_t v;
    std::memcpy(&v, g_img + kDataRva + off, 4);
    return v;
}
uint32_t Status() { return ReadData(data::kStatus); }
uint32_t LogResult() { return ReadData(data::kLogResult); }
uint32_t Repeats() { return ReadData(data::kRepeats); }

}  // namespace

int main(int argc, char** argv)
{
    setvbuf(stdout, nullptr, _IONBF, 0);

    g_img = static_cast<uint8_t*>(VirtualAlloc(
        nullptr, kImageSize, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
    if (!g_img) {
        std::printf("VirtualAlloc failed\n");
        return 1;
    }

    EntryLayout L;
    L.code_rva = kCodeRva;
    L.data_rva = kDataRva;
    L.orig_target_rva = kProbeRva;
    L.iat_get_module_file_name_w = IatRva(kIatGetModuleFileNameW);
    L.iat_load_library_ex_w = IatRva(kIatLoadLibraryExW);
    L.iat_get_proc_address = IatRva(kIatGetProcAddress);
    L.iat_create_file_w = IatRva(kIatCreateFileW);
    L.iat_write_file = IatRva(kIatWriteFile);
    L.iat_close_handle = IatRva(kIatCloseHandle);
    L.iat_get_last_error = IatRva(kIatGetLastError);

    Check("发射器拒绝不完整的布局",
          !EmitEntry(EntryLayout{}, g_img + kCodeRva, kEntryCodeMax, &g_emit));
    Check("发射入口代码",
          EmitEntry(L, g_img + kCodeRva, kEntryCodeMax, &g_emit));

    // Capacity: the header promises `out` is untouched on failure, and the PE
    // side will size a section from this.  Half a stub in a section is worse
    // than none, so the promise gets tested rather than assumed.
    {
        const size_t need = g_emit.code_bytes;
        static uint8_t canary[kEntryCodeMax];
        std::memset(canary, 0x5A, sizeof(canary));
        EmitResult r2 = {};
        bool any_wrote = false;
        for (size_t c : {size_t(0), size_t(1), size_t(7), size_t(64),
                         need - 1, need}) {
            std::memset(canary, 0x5A, sizeof(canary));
            bool ok = EmitEntry(L, canary, c, &r2);
            bool clean = true;
            for (size_t i = 0; i < sizeof(canary); ++i)
                if (canary[i] != 0x5A) { clean = false; break; }
            if (c < need) {
                if (ok || !clean) any_wrote = true;
            } else {
                if (!ok) any_wrote = true;
            }
        }
        Check("容量不足时立即失败且不改动输出（0/1/7/64/n-1 字节）", !any_wrote);
        Check("容量刚好等于产物时成功",
              EmitEntry(L, canary, need, &r2) && r2.code_bytes == need);
        std::memset(canary, 0, sizeof(canary));
    }

    // A rip-relative target too far away has to be refused, not wrapped.
    {
        EntryLayout far_layout = L;
        far_layout.orig_target_rva = 0xF0000000u;
        EmitResult r3 = {};
        static uint8_t tmp[kEntryCodeMax];
        Check("位移超出 int32 范围时拒绝发射",
              !EmitEntry(far_layout, tmp, sizeof(tmp), &r3));
    }

    Check("重新发射到映像中", EmitEntry(L, g_img + kCodeRva, kEntryCodeMax, &g_emit));
    std::printf("      代码 %zu 字节，入口 +0x%X (%u 字节)，日志 +0x%X (%u 字节)\n",
                g_emit.code_bytes, g_emit.entry_offset, g_emit.entry_size,
                g_emit.log_offset, g_emit.log_size);

    // --dump <file>: write the emitted block out so it can be disassembled.
    // Reading the bytes beats guessing when the chain crashes.
    if (argc >= 3 && std::strcmp(argv[1], "--dump") == 0) {
        FILE* f = nullptr;
        if (fopen_s(&f, argv[2], "wb") == 0 && f) {
            std::fwrite(g_img + kCodeRva, 1, g_emit.code_bytes, f);
            std::fclose(f);
            std::printf("dumped code_rva=0x%X data_rva=0x%X iat_rva=0x%X "
                        "probe_rva=0x%X entry=+0x%X log=+0x%X copyw_end=+0x%X\n",
                        kCodeRva, kDataRva, kIatRva, kProbeRva,
                        g_emit.entry_offset, g_emit.log_offset,
                        g_emit.unwind_entry_offset);
            return 0;
        }
        return 1;
    }

    void** iat = Iat();
    iat[kIatGetModuleFileNameW] = reinterpret_cast<void*>(&FakeGetModuleFileNameW);
    iat[kIatLoadLibraryExW] = reinterpret_cast<void*>(&FakeLoadLibraryExW);
    iat[kIatGetProcAddress] = reinterpret_cast<void*>(&FakeGetProcAddress);
    iat[kIatCreateFileW] = reinterpret_cast<void*>(&FakeCreateFileW);
    iat[kIatWriteFile] = reinterpret_cast<void*>(&FakeWriteFile);
    iat[kIatCloseHandle] = reinterpret_cast<void*>(&FakeCloseHandle);
    iat[kIatGetLastError] = reinterpret_cast<void*>(&FakeGetLastError);

    BuildProbe();
    BuildSite();
    FlushInstructionCache(GetCurrentProcess(), g_img, kImageSize);

    // --- the happy path -----------------------------------------------------
    ResetFakes();
    void* marker = reinterpret_cast<void*>(static_cast<uintptr_t>(0xABCDEF01));
    uint64_t rv = RunChain(marker);

    Check("原目标被调用恰好一次", g_seen.calls == 1);
    Check("RDX 原样到达原目标（经过五、七参数 API 之后）", g_seen.rdx == marker);
    Check("RCX 与调用点交出的指针逐值相等", g_seen.rcx == g_expected_rcx);
    Check("原目标入口处栈对齐正确（rsp ≡ 8 mod 16）", g_seen.rsp_mod16 == 8);
    Check("返回值原样传回调用点", rv == 0xC0FFEE);
    Check("返回地址精确等于调用指令之后的地址",
          g_seen.return_address == g_expected_return);

    Check("DLL 路径取自主程序目录",
          wcscmp(g_asked_path, L"C:\\game\\cielzh.dll") == 0);
    Check("日志路径同目录", wcscmp(g_log_path, L"C:\\game\\cielzh-loader.log") == 0);
    Check("初始化被调用一次", g_init_calls == 1);
    Check("why 缓冲区在数据块内且长度正确",
          g_why_seen == reinterpret_cast<char*>(g_img + kDataRva + data::kWhy)
          && g_why_len_seen == int(data::kWhyBytes));
    if (g_log_len == 0)
        std::printf("      诊断: create=%d bad=%d ret=%p write=%d len=%zu\n",
                    g_create_calls, g_create_bad, g_create_ret,
                    g_write_calls, g_log_len);
    Check("日志写了返回码 0", LogHas("loader=rc=00000000"));
    Check("日志以 CRLF 结尾",
          g_log_len >= 2 && g_log_text[g_log_len - 2] == '\r'
          && g_log_text[g_log_len - 1] == '\n');
    Check("模拟 CreateFileW 收到的七个参数全部正确",
          g_create_calls == 1 && g_create_bad == 0);
    Check("状态字记为已到达 DLL，日志确实写成",
          Status() == data::kStatusInit && LogResult() == data::kLogOk);

    // --- only once ----------------------------------------------------------
    uint64_t rv2 = RunChain(marker);
    Check("重复进入仍执行原调用", g_seen.calls == 2 && rv2 == 0xC0FFEE);
    Check("重复进入不再调用 LoadLibraryExW", g_load_calls == 1);
    Check("重复进入不再初始化", g_init_calls == 1);
    Check("重复进入不再写日志", g_create_calls == 1);
    Check("重复进入的两次参数都完好",
          g_seen.rcx == g_expected_rcx && g_seen.rdx == marker);
    Check("重复进入不改写首次结果（成功）",
          Status() == data::kStatusInit && LogResult() == data::kLogOk
          && Repeats() == 1);

    // The same after a failure: the first verdict is the only record there is,
    // and an earlier version wrote "busy" over it on the second entry.
    ResetFakes();
    g_load_fail = true;
    RunChain(marker);
    uint32_t first_status = Status();
    uint32_t first_log = LogResult();
    RunChain(marker);
    Check("重复进入不改写首次结果（失败）",
          Status() == first_status && first_status == data::kStatusMissing
          && LogResult() == first_log && Repeats() == 1
          && g_load_calls == 1);

    // --- logging that does not reach the disk -------------------------------
    ResetFakes();
    g_write_fail = true;
    RunChain(marker);
    Check("WriteFile 返回失败：记为 kLogBadWrite",
          LogResult() == data::kLogBadWrite && Status() == data::kStatusInit
          && g_write_calls == 1 && g_seen.calls == 1
          && g_seen.rcx == g_expected_rcx);

    ResetFakes();
    g_write_short = true;
    RunChain(marker);
    Check("WriteFile 少写一个字节：同样记为 kLogBadWrite",
          LogResult() == data::kLogBadWrite && Status() == data::kStatusInit
          && g_write_calls == 1 && g_seen.calls == 1);

    // --- path length --------------------------------------------------------
    // GetModuleFileNameW reports truncation by returning the buffer size, so
    // "did it return zero" is not the check.  A truncated path would also pick
    // the wrong directory before running off the end of the buffer.
    struct PathCase { const char* name; int dir_chars; bool expect_ok; };
    auto set_path = [&](int dir_chars) {
        // "C:\" + (dir_chars-3) filler + "\x.exe" is awkward to size exactly, so
        // build "C:\<pad>\n.exe" with the directory part exactly dir_chars long
        // (counting the trailing backslash).
        std::wstring p2 = L"C:\\";
        while (int(p2.size()) < dir_chars - 1)
            p2 += L'a';
        p2 += L'\\';
        p2 += L"n.exe";
        wcscpy_s(g_module_path, p2.c_str());
        return int(p2.size());
    };

    ResetFakes();
    set_path(int(kMaxDirChars));                 // exactly the largest allowed
    RunChain(marker);
    Check("目录长度恰好达到上限：仍然加载",
          g_load_calls == 1 && Status() == data::kStatusInit
          && g_seen.calls == 1 && g_seen.rcx == g_expected_rcx);

    ResetFakes();
    set_path(int(kMaxDirChars) + 1);             // one character too long
    RunChain(marker);
    Check("目录长度超出一个字符：拒绝加载，仍执行原调用",
          g_load_calls == 0 && Status() == data::kStatusPathBad
          && g_seen.calls == 1 && g_seen.rcx == g_expected_rcx
          && g_seen.rdx == marker);
    Check("  ……没有向空路径写日志",
          g_create_calls == 0 && LogResult() == data::kLogNotTried);

    ResetFakes();
    {
        std::wstring longp(data::kPathChars + 40, L'a');
        longp[0] = L'C'; longp[1] = L':'; longp[2] = L'\\';
        wcscpy_s(g_module_path, longp.c_str());
    }
    RunChain(marker);
    // The truncated path still holds "C:\", so a stub that missed the
    // truncation would find a backslash, pass the room check and cheerfully
    // load C:\cielzh.dll from the wrong directory.  Hence g_load_calls.
    Check("路径被截断（返回值等于容量）：拒绝加载",
          g_load_calls == 0 && Status() == data::kStatusPathBad
          && g_seen.calls == 1 && g_seen.rcx == g_expected_rcx);
    Check("  ……没有从错误目录加载",
          g_asked_path[0] == 0 && g_create_calls == 0);

    // --- the failure paths --------------------------------------------------
    struct Case {
        const char* name;
        void (*arm)();
        const char* expect;
        int inits;
    };
    const Case cases[] = {
        {"加载失败 → missing 且带 GetLastError",
         [] { g_load_fail = true; }, "loader=missing err=00000057", 0},
        {"缺少 CielZhAbiVersion → abi", [] { g_hide_abi = true; },
         "loader=abi", 0},
        {"ABI 版本不符 → abi 且带实际版本",
         [] { g_abi = 0x00020000; }, "loader=abi ver=00020000", 0},
        {"缺少 CielZhInitializeV1 → abi", [] { g_hide_init = true; },
         "loader=abi", 0},
        {"初始化返回 5 → rc=00000005", [] { g_init_rc = 5; },
         "loader=rc=00000005", 1},
    };
    for (const Case& c : cases) {
        ResetFakes();
        c.arm();
        uint64_t r = RunChain(marker);
        bool ok = g_seen.calls == 1 && r == 0xC0FFEE
                  && g_seen.rdx == marker && g_seen.rcx == g_expected_rcx
                  && g_seen.return_address == g_expected_return
                  && g_seen.rsp_mod16 == 8 && LogHas(c.expect)
                  && g_init_calls == c.inits
                  && LogResult() == data::kLogOk;
        Check(c.name, ok);
        if (!ok)
            std::printf("      日志=%s calls=%d inits=%d status=%u logres=%u\n",
                        g_log_text, g_seen.calls, g_init_calls,
                        Status(), LogResult());
    }

    // GetModuleFileNameW returning zero is a path failure, not a missing DLL:
    // there is no directory, so there is nowhere to put a log either.  An
    // earlier version called it "missing" and the fake CreateFileW happily
    // accepted the empty file name, so the log looked fine.
    ResetFakes();
    g_gmfn_fail = true;
    RunChain(marker);
    Check("取不到主程序路径：记为 path-bad，不写日志，仍执行原调用",
          Status() == data::kStatusPathBad
          && LogResult() == data::kLogNotTried && g_create_calls == 0
          && g_load_calls == 0 && g_seen.calls == 1
          && g_seen.rcx == g_expected_rcx && g_seen.rdx == marker);

    // The same five, with every fake sweeping all seven slots regardless of how
    // many arguments it really takes.  Deliberately harsher than the ABI, kept
    // separate so the runs above still describe real callees.
    int before = g_fail;
    for (const Case& c : cases) {
        ResetFakes();
        g_stress_seven = true;
        c.arm();
        RunChain(marker);
        if (!(g_seen.calls == 1 && g_seen.rdx == marker
              && g_seen.rcx == g_expected_rcx && LogHas(c.expect)))
            ++g_fail;
    }
    Check("压力用例：所有被调用者都涂满七槽时参数仍完好", g_fail == before);

    // --- a log file that really reaches the disk ----------------------------
    // The fakes above prove what the entry passes, not that a file appears.
    // Here CreateFileW, WriteFile and CloseHandle are the real ones and the
    // module path points at a real directory.
    {
        wchar_t tmp[MAX_PATH];
        GetTempPathW(MAX_PATH, tmp);
        std::wstring dir = std::wstring(tmp) + L"cielzh_entry\\";
        CreateDirectoryW(dir.c_str(), nullptr);
        std::wstring exe = dir + L"fake.exe";
        std::wstring log = dir + L"cielzh-loader.log";
        DeleteFileW(log.c_str());

        ResetFakes();
        wcscpy_s(g_module_path, exe.c_str());
        iat[kIatCreateFileW] = reinterpret_cast<void*>(&CreateFileW);
        iat[kIatWriteFile] = reinterpret_cast<void*>(&WriteFile);
        iat[kIatCloseHandle] = reinterpret_cast<void*>(&CloseHandle);
        g_init_rc = 3;
        RunChain(marker);

        HANDLE h = CreateFileW(log.c_str(), GENERIC_READ, FILE_SHARE_READ,
                               nullptr, OPEN_EXISTING, 0, nullptr);
        char disk[256] = {};
        DWORD got = 0;
        if (h != INVALID_HANDLE_VALUE) {
            ReadFile(h, disk, sizeof(disk) - 1, &got, nullptr);
            CloseHandle(h);
        }
        Check("日志文件真的出现在主程序目录里", h != INVALID_HANDLE_VALUE);
        Check("文件内容是这次的返回码",
              std::strstr(disk, "cielzh loader=rc=00000003") != nullptr);
        Check("入口自报写入成功", LogResult() == data::kLogOk);
        Check("真实 API 下参数同样完好",
              g_seen.calls == 1 && g_seen.rcx == g_expected_rcx
              && g_seen.rdx == marker);

        // A directory that is not there: CreateFileW really fails, and the
        // entry has to notice rather than report a log it never wrote.
        ResetFakes();
        wcscpy_s(g_module_path, L"C:\\no_such_dir_cielzh\\fake.exe");
        RunChain(marker);
        Check("真实 CreateFileW 失败时记为 kLogNoFile",
              LogResult() == data::kLogNoFile
              && Status() == data::kStatusInit
              && g_seen.calls == 1 && g_seen.rcx == g_expected_rcx);

        DeleteFileW(log.c_str());
        RemoveDirectoryW(dir.c_str());
        iat[kIatCreateFileW] = reinterpret_cast<void*>(&FakeCreateFileW);
        iat[kIatWriteFile] = reinterpret_cast<void*>(&FakeWriteFile);
        iat[kIatCloseHandle] = reinterpret_cast<void*>(&FakeCloseHandle);
    }

    // --- unwind information -------------------------------------------------
    // Registered for real, then walked through: an unwind record that describes
    // the wrong frame size sends the walk somewhere else, and stage one's whole
    // purpose is stack walks that can be trusted.
    // The table has to be sorted by BeginAddress, and Log comes first in the
    // block.  RtlAddFunctionTable succeeds either way, so "it registered" is
    // not evidence that the order is right; the PE patcher must sort too.
    struct Fn {
        uint32_t begin, end, unwind, body, epilogue, tail;
        const char* name;
    };
    Fn fns[2] = {
        {kCodeRva + g_emit.entry_offset,
         kCodeRva + g_emit.entry_offset + g_emit.entry_size,
         kCodeRva + g_emit.unwind_entry_offset,
         kCodeRva + g_emit.entry_body, kCodeRva + g_emit.entry_epilogue,
         kCodeRva + g_emit.entry_tail, "Entry"},
        {kCodeRva + g_emit.log_offset,
         kCodeRva + g_emit.log_offset + g_emit.log_size,
         kCodeRva + g_emit.unwind_log_offset,
         kCodeRva + g_emit.log_body, kCodeRva + g_emit.log_epilogue,
         kCodeRva + g_emit.log_tail, "Log"},
    };
    if (fns[1].begin < fns[0].begin) {
        Fn t = fns[0]; fns[0] = fns[1]; fns[1] = t;
    }
    Check("展开表按起始地址升序（Log 在 Entry 之前）",
          fns[0].begin < fns[1].begin && std::strcmp(fns[0].name, "Log") == 0);

    RUNTIME_FUNCTION rf[2] = {};
    for (int i = 0; i < 2; ++i) {
        rf[i].BeginAddress = fns[i].begin;
        rf[i].EndAddress = fns[i].end;
        rf[i].UnwindData = fns[i].unwind;
    }
    Check("注册展开信息",
          RtlAddFunctionTable(rf, 2, reinterpret_cast<DWORD64>(g_img)) != FALSE);

    // Three points in each function: inside the prolog before the allocation,
    // in the body, and after the epilogue has released it.  A record that
    // describes the wrong size passes at one of these and fails the others.
    struct Spot { uint32_t off; const char* where; DWORD64 expect_add; };
    for (int i = 0; i < 2; ++i) {
        // Offsets come from the emitter, not from counting bytes here.  "+8"
        // used to stand in for "past the prologue" and was the last byte of a
        // five-byte mov, so the unwinder was being asked about an address that
        // is not an instruction.
        //
        // At the `add rsp` the frame is still up and the unwinder emulates the
        // rest of the epilogue, so the allocation still counts; one instruction
        // later it is gone.  The epilogue is recognised by decoding, not from
        // the unwind codes, which is why it needs its own case.
        const Spot spots[] = {
            {0, "栈分配之前", 0},
            {fns[i].body - fns[i].begin, "序言之后", 0x58},
            {fns[i].epilogue - fns[i].begin, "恢复栈之前", 0x58},
            {fns[i].tail - fns[i].begin, "恢复栈之后", 0},
        };
        for (const Spot& sp_case : spots) {
            DWORD64 base = 0;
            DWORD64 pc = reinterpret_cast<DWORD64>(g_img) + fns[i].begin
                         + sp_case.off;
            PRUNTIME_FUNCTION found = RtlLookupFunctionEntry(pc, &base, nullptr);
            char label[128];
            std::snprintf(label, sizeof(label), "%s %s：查到记录并正确展开",
                          fns[i].name, sp_case.where);
            if (!found || base != reinterpret_cast<DWORD64>(g_img)
                || found->BeginAddress != fns[i].begin) {
                Check(label, false);
                continue;
            }
            DWORD64 add = sp_case.expect_add;
            CONTEXT ctx = {};
            uint8_t stack[0x200] = {};
            DWORD64 sp = reinterpret_cast<DWORD64>(stack + 0x80);
            ctx.Rip = pc;
            ctx.Rsp = sp;
            DWORD64 ret = 0x1122334455667788ull;
            std::memcpy(reinterpret_cast<void*>(sp + add), &ret, 8);
            PVOID hd = nullptr;
            DWORD64 est = 0;
            RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                             reinterpret_cast<DWORD64>(g_img), ctx.Rip, found,
                             &ctx, &hd, &est, nullptr);
            Check(label, ctx.Rsp == sp + add + 8 && ctx.Rip == ret);
        }
    }
    RtlDeleteFunctionTable(rf);

    std::printf("\n");
    if (g_fail) {
        std::printf("%d 项未通过\n", g_fail);
        return 1;
    }
    std::printf("入口链条测试全部通过\n");
    return 0;
}
